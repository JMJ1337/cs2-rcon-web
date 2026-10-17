"""iSCSI-Einbindung planen: Einstellungen speichern, Host-Skript erzeugen, Ergebnis (Mount) nur lesend prüfen.

Das Tool führt bewusst KEINE Befehle als root auf dem Host aus – das Skript wird einmal per SSH auf dem Docker-Host gestartet.
"""
import os
import re
import shlex

from . import store

FILE = "storage.json"
HOST_PROC1 = os.getenv("HOST_PROC1", "/host/proc/1")
DEFAULTS = {"portal": "", "target": "", "chap_user": "", "chap_pw": "", "fs": "ext4", "mountpoint": "/mnt/lancache",
            "format": True, "label": "lancache", "purpose": "lancache", "old_path": "/mnt/cachenew"}
IQN_RE = re.compile(r"^(iqn\.|eui\.|naa\.)[A-Za-z0-9.:\-_]+$")
HOST_RE = re.compile(r"^[A-Za-z0-9.\-]+(:\d{1,5})?$")
PATH_RE = re.compile(r"^/mnt/[A-Za-z0-9._\-/]+$")


def settings() -> dict:
    return {**DEFAULTS, **store.load(FILE, {})}


def save(data: dict) -> dict:
    s = settings()
    for k in DEFAULTS:
        if k in data:
            s[k] = data[k]
    errs = []
    if s["portal"] and not HOST_RE.match(s["portal"]):
        errs.append("Portal: IP oder Name, optional :Port")
    if s["target"] and not IQN_RE.match(s["target"]):
        errs.append("Ziel (IQN) muss mit iqn. beginnen")
    if not PATH_RE.match(s["mountpoint"] or "") or ".." in s["mountpoint"]:
        errs.append("Mountpunkt muss unter /mnt/ liegen")
    if s["fs"] not in ("ext4", "xfs"):
        errs.append("Dateisystem ext4 oder xfs")
    if errs:
        raise ValueError("; ".join(errs))
    s["label"] = re.sub(r"[^A-Za-z0-9_\-]", "", s.get("label") or "")[:12] or "lancache"
    store.save(FILE, s)
    return s


def script(s: dict) -> str:
    """Bash-Skript für den Docker-Host (Debian/Ubuntu). Formatiert nur nach ausdrücklicher Bestätigung."""
    portal = s["portal"] or "<NAS-IP>"
    port = portal if ":" in portal else portal + ":3260"
    t = s["target"]
    q = shlex.quote
    lines = [
        "#!/bin/bash",
        "# iSCSI-LUN einbinden – erzeugt vom Spielservermanager. Auf dem Docker-Host als root ausführen:",
        "#   sudo bash iscsi-einbinden.sh",
        "set -euo pipefail",
        f"PORTAL={q(port)}",
        f"TARGET={q(t) if t else '\"\"   # leer = erstes gefundenes Ziel'}",
        f"MNT={q(s['mountpoint'])}",
        f"FS={s['fs']}",
        f"LABEL={q(s['label'])}",
        "",
        "echo '== 1. open-iscsi installieren'",
        "command -v iscsiadm >/dev/null || { apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y open-iscsi; }",
        "systemctl enable --now iscsid open-iscsi 2>/dev/null || systemctl enable --now iscsid",
        "echo \"Initiator (auf der Synology erlauben): $(grep -v '^#' /etc/iscsi/initiatorname.iscsi)\"",
        "",
        "echo '== 2. Ziele suchen'",
        "iscsiadm -m discovery -t sendtargets -p \"$PORTAL\"",
        "[ -n \"$TARGET\" ] || TARGET=$(iscsiadm -m discovery -t sendtargets -p \"$PORTAL\" | head -1 | awk '{print $2}' || true)",
        "echo \"Ziel: $TARGET\"",
    ]
    if s.get("chap_user"):
        lines += [
            "",
            "echo '== CHAP-Anmeldung'",
            "iscsiadm -m node -T \"$TARGET\" -p \"$PORTAL\" --op update -n node.session.auth.authmethod -v CHAP",
            f"iscsiadm -m node -T \"$TARGET\" -p \"$PORTAL\" --op update -n node.session.auth.username -v {q(s['chap_user'])}",
            f"iscsiadm -m node -T \"$TARGET\" -p \"$PORTAL\" --op update -n node.session.auth.password -v {q(s.get('chap_pw') or '')}",
        ]
    lines += [
        "",
        "echo '== 3. Anmelden und beim Booten automatisch verbinden'",
        "iscsiadm -m node -T \"$TARGET\" -p \"$PORTAL\" --op update -n node.startup -v automatic",
        "iscsiadm -m node -T \"$TARGET\" -p \"$PORTAL\" --login || true",
        "sleep 3; udevadm settle",
        "DEV=$(ls -1 /dev/disk/by-path/ | grep -F \"$TARGET\" | grep -v part | head -1 || true)",
        "[ -n \"$DEV\" ] || { echo 'LUN nicht gefunden – Rechte/Initiator auf dem NAS prüfen'; exit 1; }",
        "DEV=/dev/disk/by-path/$DEV",
        "echo \"Datenträger: $DEV -> $(readlink -f $DEV)  ($(lsblk -ndo SIZE $DEV))\"",
        "",
    ]
    if s.get("format"):
        lines += [
            "echo '== 4. Formatieren (löscht alles auf der LUN!)'",
            "if blkid \"$DEV\" >/dev/null 2>&1; then",
            "  echo \"Auf $DEV ist schon ein Dateisystem: $(blkid -s TYPE -o value $DEV) – wird NICHT formatiert.\"",
            "else",
            "  read -r -p \"$DEV wirklich formatieren? Zum Bestätigen JA eingeben: \" OK",
            "  [ \"$OK\" = JA ] || { echo abgebrochen; exit 1; }",
            "  if [ \"$FS\" = xfs ]; then mkfs.xfs -f -L \"$LABEL\" \"$DEV\"; else mkfs.ext4 -F -m 0 -L \"$LABEL\" \"$DEV\"; fi",
            "fi",
            "",
        ]
    lines += [
        "echo '== 5. Dauerhaft einhängen (fstab mit _netdev)'",
        "UUID=$(blkid -s UUID -o value \"$DEV\")",
        "mkdir -p \"$MNT\"",
        "grep -q \"UUID=$UUID\" /etc/fstab || echo \"UUID=$UUID $MNT $FS _netdev,noatime,nofail 0 2\" >> /etc/fstab",
        "systemctl daemon-reload",
        "mountpoint -q \"$MNT\" || mount \"$MNT\"",
        "df -h \"$MNT\"",
    ]
    if s.get("purpose") == "lancache":
        lines += [
            "",
            "echo '== 6. Lancache umstellen'",
            "echo \"Im Portainer-Stack des Lancache den Cache-Pfad von " + s.get("old_path", "") + " auf $MNT/cache umstellen\"",
            "echo \"(z. B. CACHE_ROOT=$MNT oder Volume '$MNT/cache:/data/cache'), dann den Stack neu deployen.\"",
            "mkdir -p \"$MNT/cache\" \"$MNT/logs\"",
            "chown -R 33:33 \"$MNT/cache\" \"$MNT/logs\" 2>/dev/null || true   # www-data im monolithic-Container",
        ]
    lines += ["", "echo 'Fertig.'"]
    return "\n".join(lines) + "\n"


def mount_status(path: str) -> dict:
    """Nur lesend: ist der Mountpunkt auf dem Host eingehängt? (aus /host/proc/1/mounts)"""
    try:
        with open(f"{HOST_PROC1}/mounts") as f:
            for line in f:
                p = line.split()
                if len(p) >= 4 and p[1] == path:
                    return {"mounted": True, "device": p[0], "fstype": p[2], "options": p[3]}
    except OSError:
        return {"mounted": None, "error": "Host-/proc nicht eingebunden"}
    return {"mounted": False}


def iscsi_disks() -> list[dict]:
    """Nur lesend: Mounts unter /mnt mit Gerät und Typ – zeigt u. a. eingebundene iSCSI-LUNs (/dev/sdX)."""
    out = []
    try:
        with open(f"{HOST_PROC1}/mounts") as f:
            for line in f:
                p = line.split()
                if len(p) >= 3 and p[1].startswith("/mnt"):
                    out.append({"path": p[1], "device": p[0], "fstype": p[2],
                                "network": p[2].startswith("nfs") or p[2] in ("cifs", "smb3")})
    except OSError:
        pass
    return out
