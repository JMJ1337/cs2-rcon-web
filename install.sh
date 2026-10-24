#!/usr/bin/env bash
# ============================================================================================
#  Spielservermanager – Installer für ein frisches Linux (Debian / Ubuntu)
#
#  Installiert Docker, Portainer und den Spielservermanager (als Portainer-Stack),
#  auf Wunsch auch Lancache (Download-Cache + DNS). Fragt Benutzer, Passwörter und Ordner ab.
#
#  Aufruf (als root oder mit sudo):
#    curl -fsSL https://github.com/JMJ1337/cs2-rcon-web/releases/latest/download/install.sh | sudo bash
#
#  Ohne Rückfragen (z. B. für Skripte) alle Werte als Umgebungsvariablen setzen, siehe "Vorgaben" unten,
#  und GSM_YES=1 übergeben.
# ============================================================================================
set -euo pipefail

REPO="JMJ1337/cs2-rcon-web"   # Quelle, für Hinweise
export REPO
GSM_IMAGE="${GSM_IMAGE:-ghcr.io/jmj1337/cs2-rcon-web:${GSM_VERSION:-latest}}"
PORTAINER_IMAGE="${PORTAINER_IMAGE:-portainer/portainer-ce:lts}"
STACK_GSM="spielservermanager"
STACK_CACHE="lancache"

# ---------------------------------------------------------------- Ausgabe
c_ok=$'\e[32m'; c_warn=$'\e[33m'; c_err=$'\e[31m'; c_dim=$'\e[2m'; c_b=$'\e[1m'; c_0=$'\e[0m'
say()  { printf '%s\n' "${c_b}==>${c_0} $*"; }
ok()   { printf '%s\n' "${c_ok}  ✓${c_0} $*"; }
warn() { printf '%s\n' "${c_warn}  !${c_0} $*"; }
die()  { printf '%s\n' "${c_err}  ✗ $*${c_0}" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "Bitte als root ausführen (… | sudo bash)"
. /etc/os-release 2>/dev/null || true
case "${ID:-}${ID_LIKE:-}" in
  *debian*|*ubuntu*) ;;
  *) warn "Getestet für Debian/Ubuntu – ${PRETTY_NAME:-unbekanntes System} wird trotzdem versucht" ;;
esac

# ---------------------------------------------------------------- Geführte Oberfläche (whiptail), sonst Textfragen
TTY=/dev/tty
INTERACTIVE=0
if [ "${GSM_YES:-}" != "1" ] && [ -r $TTY ] && [ -w $TTY ]; then INTERACTIVE=1; fi
apt_q() { DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" >/dev/null 2>&1; }
if command -v apt-get >/dev/null; then
  echo "  Vorbereitung …"
  DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null 2>&1 || true
  apt_q curl ca-certificates jq iproute2 whiptail || true
fi
command -v jq >/dev/null || die "jq fehlt und konnte nicht installiert werden"
WT=0; [ "$INTERACTIVE" = 1 ] && command -v whiptail >/dev/null && WT=1
BT="Spielservermanager – Einrichtung"
ROWS=$(stty size <"$TTY" 2>/dev/null | awk '{print $1}' || true); COLS=$(stty size <"$TTY" 2>/dev/null | awk '{print $2}' || true)
ROWS=${ROWS:-24}; COLS=${COLS:-80}; [ "$ROWS" -ge 12 ] 2>/dev/null || ROWS=24; [ "$COLS" -ge 40 ] 2>/dev/null || COLS=80
W=$(( COLS - 4 )); [ $W -gt 78 ] && W=78
H=$(( ROWS - 4 )); [ $H -gt 22 ] && H=22
hgt() {   # hgt "Text" Zusatzzeilen -> passende Fensterhöhe (Text umbrochen auf die Breite)
  local n; n=$(printf '%b\n' "$1" | fold -s -w $(( W - 4 )) | wc -l)
  n=$(( n + $2 )); [ $n -gt $(( ROWS - 2 )) ] && n=$(( ROWS - 2 )); [ $n -lt 8 ] && n=8; echo $n
}

wt() { whiptail --backtitle "$BT" --ok-button "OK" --cancel-button "Abbrechen" "$@" 3>&1 1>"$TTY" 2>&3 <"$TTY"; }
msg() {   # msg "Titel" "Text"
  if [ "$WT" = 1 ]; then wt --title "$1" --msgbox "$2" $(hgt "$2" 7) $W || true
  elif [ "$INTERACTIVE" = 1 ]; then printf '\n%s\n%s\n' "${c_b}$1${c_0}" "$2"; fi
}
ask() {   # ask VAR "Titel" "Frage" "Vorgabe"
  local v=$1 t=$2 q=$3 d=${4:-} a=""
  [ -n "${!v:-}" ] && return
  if [ "$INTERACTIVE" != 1 ]; then printf -v "$v" '%s' "$d"; return; fi
  if [ "$WT" = 1 ]; then a=$(wt --title "$t" --inputbox "$q" $(hgt "$q" 8) $W "$d") || die "Abgebrochen"
  else printf '\n%b\n' "$q"; read -r -p "  > ${d:+[$d] }" a < $TTY || true; a=${a:-$d}; fi
  printf -v "$v" '%s' "$a"
}
ask_pw() {  # ask_pw VAR "Titel" "Frage" Mindestlänge
  local v=$1 t=$2 q=$3 m=${4:-8} a b
  [ -n "${!v:-}" ] && return
  [ "$INTERACTIVE" = 1 ] || die "$q: bitte als Umgebungsvariable $v übergeben"
  while true; do
    if [ "$WT" = 1 ]; then
      a=$(wt --title "$t" --passwordbox "$q\n\n(mindestens $m Zeichen)" $(hgt "$q\n\n." 8) $W) || die "Abgebrochen"
      b=$(wt --title "$t" --passwordbox "Passwort wiederholen" 9 $W) || die "Abgebrochen"
    else
      read -r -s -p "  $q (mind. $m Zeichen): " a < $TTY; echo; read -r -s -p "  wiederholen: " b < $TTY; echo
    fi
    if [ ${#a} -lt "$m" ]; then msg "$t" "Das Passwort ist zu kurz (mindestens $m Zeichen)."; continue; fi
    if [ "$a" != "$b" ]; then msg "$t" "Die Passwörter stimmen nicht überein."; continue; fi
    printf -v "$v" '%s' "$a"; return
  done
}
yesno() {   # yesno VAR "Titel" "Frage" j|n
  local v=$1 t=$2 q=$3 d=${4:-n} a=""
  [ -n "${!v:-}" ] && return
  if [ "$INTERACTIVE" != 1 ]; then [ "$d" = j ] && printf -v "$v" 1 || printf -v "$v" 0; return; fi
  if [ "$WT" = 1 ]; then
    if wt --title "$t" --yes-button "Ja" --no-button "Nein" $([ "$d" = n ] && echo --defaultno) --yesno "$q" $(hgt "$q" 7) $W; then printf -v "$v" 1; else printf -v "$v" 0; fi
  else
    read -r -p "  $q (j/n) [$d]: " a < $TTY || true; a=${a:-$d}
    case "${a,,}" in j|ja|y|yes) printf -v "$v" 1 ;; *) printf -v "$v" 0 ;; esac
  fi
}
menu() {   # menu VAR "Titel" "Text" Vorgabe tag "Beschreibung" tag "Beschreibung" …
  local v=$1 t=$2 q=$3 d=$4 a=""; shift 4
  [ -n "${!v:-}" ] && return
  if [ "$INTERACTIVE" != 1 ]; then printf -v "$v" '%s' "$d"; return; fi
  if [ "$WT" = 1 ]; then
    a=$(wt --title "$t" --default-item "$d" --menu "$q" $(hgt "$q" $(( $# / 2 + 8 ))) $W $(( $# / 2 )) "$@") || die "Abgebrochen"
  else
    printf '\n  %s\n' "$q"; local i=1 tags=(); while [ $# -gt 0 ]; do printf '   %d) %s\n' $i "$2"; tags+=("$1"); shift 2; i=$((i+1)); done
    read -r -p "  Auswahl [$d]: " a < $TTY || true
    if [[ "$a" =~ ^[0-9]+$ ]] && [ "$a" -ge 1 ] && [ "$a" -le ${#tags[@]} ]; then a=${tags[$((a-1))]}; else a=$d; fi
  fi
  printf -v "$v" '%s' "$a"
}

# ---------------------------------------------------------------- Netzwerk: IP automatisch
IP_GIVEN=${LAN_IP:-}
DET_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' || true)
[ -n "$DET_IP" ] || DET_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
VIRT=$(systemd-detect-virt 2>/dev/null || true)
if [ -z "$IP_GIVEN" ] && [ -n "$DET_IP" ]; then
  ALL_IPS=$(ip -4 -o addr show scope global 2>/dev/null | awk '{split($4,a,"/"); printf "%s (%s)  ", a[1], $2}' || true)
  IPQ="Erkannte IP-Adresse dieses Rechners: $DET_IP\nAlle Adressen: ${ALL_IPS:-$DET_IP}\n\nUnter dieser Adresse müssen Spieler und Weboberfläche den Rechner im LAN erreichen. Bitte prüfen und ggf. ändern."
  case "$DET_IP" in 172.1[6-9].*|172.2[0-9].*|172.3[01].*|10.0.2.*|192.168.122.*)
    if [ "$VIRT" = microsoft ] || [ "$VIRT" = oracle ] || [ "$VIRT" = kvm ] || [ "$VIRT" = qemu ]; then
      msg "Netzwerk – Achtung" "Erkannte IP: $DET_IP\n\nDas sieht nach einem internen NAT-Netz der VM aus (Hyper-V „Default Switch“, VirtualBox-NAT, libvirt default). Darüber ist die VM aus dem LAN NICHT erreichbar – Spieler können nicht joinen.\nAbhilfe: Die VM an einen externen Switch / eine Netzwerkbrücke hängen (Hyper-V-Manager → Manager für virtuelle Switches → Externes Netzwerk mit der echten Netzwerkkarte), dann die VM neu starten und das Skript erneut ausführen.\n\nIm nächsten Schritt kannst du die IP trotzdem übernehmen oder ändern."
    fi ;;
  esac
  LAN_IP=$DET_IP
  [ "$INTERACTIVE" = 1 ] && { LAN_IP=""; ask LAN_IP "Netzwerk" "$IPQ" "$DET_IP"; }
fi
LAN_IP=${LAN_IP:-$DET_IP}
[ -n "$LAN_IP" ] || ask LAN_IP "Netzwerk" "Die IP-Adresse konnte nicht automatisch erkannt werden.\n\nGib die Adresse ein, unter der dieser Rechner im LAN erreichbar ist (z. B. 192.168.1.10). Über diese Adresse erreichen Spieler die Server und du die Weboberfläche.\n\nTipp: Im Router eine feste IP für diesen Rechner einstellen, sonst ändert sie sich evtl. nach einem Neustart." ""
[ -n "$LAN_IP" ] || die "Keine IP-Adresse"
GSM_PORT=${GSM_PORT:-8090}

# Benutzer, in dessen Ordner „lokal (automatisch)“ landet: sudo-Aufrufer, sonst erster normaler Benutzer (z. B. gsm vom ISO)
HOME_USER=${SUDO_USER:-}
if [ -z "$HOME_USER" ] || [ "$HOME_USER" = root ]; then
  HOME_USER=$(getent passwd | awk -F: '$3>=1000 && $3<60000 {print $1; exit}')
fi
HOME_DIR=$( [ -n "$HOME_USER" ] && getent passwd "$HOME_USER" | cut -d: -f6 || true)
HOME_DIR=${HOME_DIR:-/srv}

# ---------------------------------------------------------------- Fragen
msg "Willkommen" "Dieser Assistent richtet ein:\n\n  • Docker\n  • Portainer (Container-Verwaltung)\n  • den Spielservermanager (Weboberfläche)\n  • optional Lancache (lokaler Download-Cache)\n\nErkannte IP-Adresse: $LAN_IP\nWeboberfläche später: http://$LAN_IP:$GSM_PORT\n\nTipp: Diese IP sollte sich nicht ändern – im Router eine feste Adresse (DHCP-Reservierung) für diesen Rechner einstellen.\n\nNavigation: Pfeiltasten wählen, Tab wechselt zu den Knöpfen, Enter bestätigt, Esc bricht ab. Alles lässt sich später in der Weboberfläche ändern."

ask GSM_USER "Benutzer" "Benutzername für den Spielservermanager\n\nMit diesem Konto meldest du dich an der Weboberfläche an (Administrator mit allen Rechten). Weitere Benutzer, Profile und Steam-Anmeldung richtest du später unter „Benutzer“ ein.\n\nErlaubt: Kleinbuchstaben, Ziffern, Punkt, Minus, Unterstrich." "admin"
GSM_USER=$(printf '%s' "$GSM_USER" | tr 'A-Z' 'a-z' | tr -cd 'a-z0-9._-'); GSM_USER=${GSM_USER:-admin}
ask BRAND "Veranstaltung" "Name eurer LAN / Veranstaltung\n\nErscheint in den Servernamen (z. B. „LAN CS #1 Wingman“), in Titeln und Benachrichtigungen. Kurz halten – später änderbar unter „Automatik & Einstellungen“." "LAN"
BRAND=$(printf '%s' "$BRAND" | tr -d '"\\;{}'); BRAND=${BRAND:-LAN}
ask_pw GSM_PASSWORD "Benutzer" "Passwort für „$GSM_USER“ an der Weboberfläche des Spielservermanagers." 8
ask PORTAINER_USER "Portainer" "Benutzername für Portainer\n\nPortainer ist die Verwaltungsoberfläche für Docker (https://$LAN_IP:9443). Darin läuft der Spielservermanager als „Stack“ – dort siehst du Container, Logs und kannst Updates einspielen. Für den Alltag brauchst du Portainer meist nicht." "admin"
if [ -z "${PORTAINER_PASSWORD:-}" ] && [ ${#GSM_PASSWORD} -ge 12 ]; then
  yesno SAME_PW "Portainer" "Für Portainer dasselbe Passwort wie für den Spielservermanager nehmen?\n\n(Portainer verlangt mindestens 12 Zeichen – dein Passwort ist lang genug.)" j
  [ "${SAME_PW:-0}" = 1 ] && PORTAINER_PASSWORD=$GSM_PASSWORD
fi
ask_pw PORTAINER_PASSWORD "Portainer" "Passwort für Portainer.\n\nPortainer verlangt mindestens 12 Zeichen." 12

# Speicherort wählen: lokal (Benutzerordner / eigener Ordner) oder Netzwerk (NFS, SMB, iSCSI)
choose_storage() {   # choose_storage PREFIX "Bezeichnung" lokaler_Standardordner Mountpunkt
  local P=$1 L=$2 DEF=$3 MNT=$4 kind
  local KV="${P}_KIND"
  menu "$KV" "$L" "Wo sollen die Daten für $L liegen?\n\nLokal = Platte in diesem Rechner (schnell, einfach). Netzwerk = NAS: iSCSI bindet ein virtuelles Laufwerk (LUN) ein und ist deutlich schneller als die Dateifreigaben NFS/SMB – besonders für den Lancache. Später änderbar." local \
    local "Lokal – im Benutzerordner ($DEF)" \
    custom "Lokal – eigenen Ordner angeben" \
    iscsi "Netzwerk – iSCSI (empfohlen, schnell)" \
    nfs "Netzwerk – NFS-Freigabe" \
    smb "Netzwerk – SMB/CIFS-Freigabe (Windows/NAS)"
  kind=${!KV}
  case "$kind" in
    local)  local cur; cur=$(eval echo "\${${P}_DIR:-}"); printf -v "${P}_DIR" '%s' "${cur:-$DEF}" ;;
    custom) ask "${P}_DIR" "$L" "Ordner für $L (absoluter Pfad, beginnt mit /).\n\nZ. B. eine zweite Platte unter /srv/… oder /mnt/… – der Ordner wird angelegt, falls er fehlt." "$DEF" ;;
    nfs)
      ask "${P}_NFS" "$L – NFS" "NFS-Freigabe im Format Server:/Pfad\n\nZ. B. 192.168.1.5:/volume1/spielserver (Synology: Systemsteuerung → Freigegebener Ordner → NFS-Berechtigungen, diesen Rechner $LAN_IP mit Lese-/Schreibzugriff und „Keine Zuordnung“ erlauben).\n\nEingehängt wird unter $MNT." ""
      printf -v "${P}_DIR" '%s' "$MNT" ;;
    smb)
      ask "${P}_SMB" "$L – SMB" "SMB/CIFS-Freigabe (Windows-/NAS-Freigabe) im Format //Server/Freigabe\n\nZ. B. //192.168.1.5/spielserver\n\nHinweis: SMB kennt keine Linux-Dateirechte und ist am langsamsten – für Spielserver geht es, für den Lancache besser iSCSI nehmen.\n\nEingehängt wird unter $MNT." ""
      ask "${P}_SMBUSER" "$L – SMB" "Benutzername für die Freigabe (Konto auf dem NAS/Windows-Rechner):" ""
      ask_pw "${P}_SMBPW" "$L – SMB" "Passwort des Freigabe-Benutzers.\n\nWird nur lesbar für root in /etc/gsm-*.cred gespeichert." 1
      printf -v "${P}_DIR" '%s' "$MNT" ;;
    iscsi)
      apt_q open-iscsi || true
      ask "${P}_PORTAL" "$L – iSCSI" "IP-Adresse des NAS mit dem iSCSI-Ziel\n\nVorher am NAS anlegen (Synology: SAN Manager → LUN + iSCSI-Ziel). Die LUN sollte leer sein – sie wird nach Rückfrage mit ext4 formatiert und unter $MNT dauerhaft eingehängt.\n\nEine LUN darf immer nur von EINEM Rechner benutzt werden." ""
      local tg=() t
      if command -v iscsiadm >/dev/null; then
        while read -r t; do [ -n "$t" ] && tg+=("$t" ""); done < <(iscsiadm -m discovery -t sendtargets -p "$(eval echo \${${P}_PORTAL})" 2>/dev/null | awk '{print $2}' | sort -u)
      fi
      if [ ${#tg[@]} -gt 0 ]; then menu "${P}_IQN" "$L – iSCSI" "Auf dem NAS gefundene iSCSI-Ziele (IQN). Wähle das Ziel mit der LUN für $L:" "${tg[0]}" "${tg[@]}"
      else ask "${P}_IQN" "$L – iSCSI" "Kein Ziel automatisch gefunden.\n\nZiel-Namen (IQN) eingeben, z. B. iqn.2000-01.com.synology:nas.Target-1.abc123 – steht am NAS beim iSCSI-Ziel." ""; fi
      ask "${P}_CHAPUSER" "$L – iSCSI" "CHAP-Benutzer (leer lassen = ohne Anmeldung)\n\nCHAP ist ein Passwortschutz für das iSCSI-Ziel. Nur eintragen, wenn am NAS beim Ziel „CHAP aktivieren“ eingeschaltet ist." ""
      if [ -n "$(eval echo \${${P}_CHAPUSER})" ]; then ask_pw "${P}_CHAPPW" "$L – iSCSI" "CHAP-Passwort (wie am NAS beim iSCSI-Ziel eingetragen).\n\nCHAP verlangt 12–16 Zeichen." 12; fi
      printf -v "${P}_DIR" '%s' "$MNT" ;;
  esac
  local d; d=$(eval echo \${${P}_DIR})
  case "$d" in /*) ;; *) die "$L: bitte einen absoluten Pfad angeben" ;; esac
}
GAMES_KIND=${GAMES_KIND:-}; [ -n "${GAMES_DIR:-}" ] && GAMES_KIND=${GAMES_KIND:-custom}
choose_storage GAMES "die Spielserver" "$HOME_DIR/spielserver" /mnt/gsm-spiele

yesno WITH_CACHE "Lancache" "Lancache mitinstallieren?\n\nLokaler Download-Cache für Steam, Epic, Battle.net, Riot … – Spiele werden nur einmal aus dem Internet geladen, danach mit LAN-Geschwindigkeit.\n\nWie es funktioniert: Die Spieler-PCs fragen diesen Rechner als DNS-Server. Download-Adressen von Steam & Co. leitet er auf den Cache um, alles andere reicht er normal ins Internet weiter. Dafür im Router/DHCP den DNS-Server auf $LAN_IP stellen.\n\nBraucht viel Speicherplatz (empfohlen 500 GB+) und belegt die Ports 53, 80 und 443." n
if [ "$WITH_CACHE" = 1 ]; then
  CACHE_KIND=${CACHE_KIND:-}; [ -n "${CACHE_DIR:-}" ] && CACHE_KIND=${CACHE_KIND:-custom}
  choose_storage CACHE "den Lancache" "$HOME_DIR/lancache" /mnt/gsm-lancache
  ask CACHE_SIZE "Lancache" "Maximale Größe des Caches\n\nIst er voll, werden die am längsten nicht benutzten Spiele automatisch gelöscht. Etwas kleiner wählen als der freie Platz am Speicherort.\n\nEinheit: g = Gigabyte (z. B. 500g, 2000g = 2 TB)." "1000g"
  ask UPSTREAM_DNS "Lancache" "Upstream-DNS (mehrere durch Leerzeichen getrennt)\n\nDer Lancache ist der DNS-Server für die Spieler-PCs. Alles, was nicht gecacht wird (Webseiten, Spiele-Logins …), fragt er bei diesen „vorgelagerten“ DNS-Servern nach.\n\n  1.1.1.1 = Cloudflare, 8.8.8.8 = Google, 9.9.9.9 = Quad9\n  oder die IP deines Routers (z. B. 192.168.1.1), wenn lokale Namen (NAS, Drucker) auflösbar bleiben sollen." "1.1.1.1 8.8.8.8"
fi

storage_text() {   # storage_text PREFIX
  local k d; k=$(eval echo \${${1}_KIND}); d=$(eval echo \${${1}_DIR})
  case "$k" in
    nfs) echo "$d (NFS $(eval echo \${${1}_NFS}))" ;;
    smb) echo "$d (SMB $(eval echo \${${1}_SMB}))" ;;
    iscsi) echo "$d (iSCSI $(eval echo \${${1}_PORTAL}))" ;;
    *) echo "$d" ;;
  esac
}
SUMMARY="Weboberfläche:  http://$LAN_IP:$GSM_PORT  (Benutzer $GSM_USER)
Portainer:      https://$LAN_IP:9443  (Benutzer $PORTAINER_USER)
Spielserver:    $(storage_text GAMES)
Veranstaltung:  $BRAND
Neue Spielserver bekommen Beitritts- und RCON-Passwort 123456789
                (ändern unter Automatik & Einstellungen)"
[ "$WITH_CACHE" = 1 ] && SUMMARY="$SUMMARY
Lancache:       $(storage_text CACHE), max. $CACHE_SIZE
                DNS auf $LAN_IP:53"
if [ "$INTERACTIVE" = 1 ]; then
  yesno GO "Zusammenfassung" "$SUMMARY\n\nJetzt installieren?" j
  [ "$GO" = 1 ] || die "Abgebrochen"
fi
clear 2>/dev/null || true
echo; printf '%s\n' "${c_b}Spielservermanager – Installation${c_0}"; printf '%s\n\n' "$SUMMARY"

# ---------------------------------------------------------------- Speicher einrichten (Netzwerk einhängen)
fstab_add() {   # fstab_add "Zeile" Mountpunkt
  grep -qsE "[[:space:]]$2[[:space:]]" /etc/fstab || echo "$1" >> /etc/fstab
}
setup_storage() {   # setup_storage PREFIX "Bezeichnung"
  local P=$1 L=$2 k d
  k=$(eval echo \${${P}_KIND}); d=$(eval echo \${${P}_DIR})
  case "$k" in
    nfs)
      say "$L: NFS einhängen"; apt_q nfs-common || die "nfs-common konnte nicht installiert werden"
      mkdir -p "$d"
      fstab_add "$(eval echo \${${P}_NFS}) $d nfs defaults,_netdev,nofail,noatime 0 0" "$d"
      mount "$d" 2>/dev/null || mount -a || die "NFS-Freigabe lässt sich nicht einhängen"
      ok "$d eingehängt" ;;
    smb)
      say "$L: SMB einhängen"; apt_q cifs-utils || die "cifs-utils konnte nicht installiert werden"
      mkdir -p "$d"; local cred="/etc/gsm-$(basename "$d").cred"
      printf 'username=%s\npassword=%s\n' "$(eval echo \${${P}_SMBUSER})" "$(eval echo \${${P}_SMBPW})" > "$cred"; chmod 600 "$cred"
      fstab_add "$(eval echo \${${P}_SMB}) $d cifs credentials=$cred,file_mode=0777,dir_mode=0777,noperm,_netdev,nofail,vers=3.0 0 0" "$d"
      mount "$d" 2>/dev/null || mount -a || die "SMB-Freigabe lässt sich nicht einhängen"
      ok "$d eingehängt"; warn "SMB ist für Spielserver/Cache langsamer als iSCSI und kennt keine Linux-Rechte – im Zweifel iSCSI nehmen" ;;
    iscsi)
      say "$L: iSCSI verbinden"; apt_q open-iscsi || die "open-iscsi konnte nicht installiert werden"
      systemctl enable --now iscsid open-iscsi >/dev/null 2>&1 || true
      local portal iqn cu cp dev
      portal=$(eval echo \${${P}_PORTAL}); iqn=$(eval echo \${${P}_IQN}); cu=$(eval echo \${${P}_CHAPUSER:-}); cp=$(eval echo \${${P}_CHAPPW:-})
      iscsiadm -m discovery -t sendtargets -p "$portal" >/dev/null 2>&1 || true
      if [ -n "$cu" ]; then
        iscsiadm -m node -T "$iqn" -p "$portal" -o update -n node.session.auth.authmethod -v CHAP
        iscsiadm -m node -T "$iqn" -p "$portal" -o update -n node.session.auth.username -v "$cu"
        iscsiadm -m node -T "$iqn" -p "$portal" -o update -n node.session.auth.password -v "$cp"
      fi
      iscsiadm -m node -T "$iqn" -p "$portal" -o update -n node.startup -v automatic
      iscsiadm -m node -T "$iqn" -p "$portal" --login >/dev/null 2>&1 || true
      for _ in $(seq 1 20); do dev=$(ls /dev/disk/by-path/*"${iqn}"-lun-* 2>/dev/null | grep -v -- -part | head -1); [ -n "$dev" ] && break; sleep 1; done
      [ -n "$dev" ] || die "iSCSI-Ziel $iqn liefert keine LUN (Initiator am NAS freigegeben? $(cat /etc/iscsi/initiatorname.iscsi 2>/dev/null | cut -d= -f2))"
      dev=$(readlink -f "$dev")
      if ! blkid "$dev" >/dev/null 2>&1; then
        local FMT=""; yesno FMT "iSCSI" "Die LUN $dev ($(lsblk -dno SIZE "$dev")) ist leer.\n\nJetzt mit ext4 formatieren? (Alle Daten darauf gehen verloren.)" j
        [ "$FMT" = 1 ] || die "Ohne Dateisystem geht es nicht weiter"
        mkfs.ext4 -F -L "gsm-$(basename "$d" | sed 's/^gsm-//')" "$dev" >/dev/null
      fi
      mkdir -p "$d"
      fstab_add "UUID=$(blkid -s UUID -o value "$dev") $d $(blkid -s TYPE -o value "$dev") defaults,_netdev,nofail,noatime 0 2" "$d"
      mount "$d" 2>/dev/null || mount -a || die "LUN lässt sich nicht einhängen"
      ok "$d eingehängt ($dev)" ;;
    *) mkdir -p "$d"; ok "Ordner $d" ;;
  esac
}

# ---------------------------------------------------------------- Docker
say "Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh >/dev/null
fi
systemctl enable --now docker >/dev/null 2>&1 || true
docker info >/dev/null 2>&1 || die "Docker läuft nicht"
ok "Docker $(docker version -f '{{.Server.Version}}')"

setup_storage GAMES "Spielserver"
GAMES_DIR=$GAMES_DIR
if [ "$WITH_CACHE" = 1 ]; then setup_storage CACHE "Lancache"; mkdir -p "$CACHE_DIR/data" "$CACHE_DIR/logs"; fi

# ---------------------------------------------------------------- Port 53 für Lancache-DNS frei machen
if [ "$WITH_CACHE" = 1 ]; then
  if ss -lunp 2>/dev/null | grep -q ':53 .*systemd-resolve'; then
    say "systemd-resolved belegt Port 53 – DNS-Stub abschalten"
    mkdir -p /etc/systemd/resolved.conf.d
    printf '[Resolve]\nDNSStubListener=no\n' > /etc/systemd/resolved.conf.d/lancache.conf
    ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
    systemctl restart systemd-resolved
    ok "Port 53 frei"
  fi
fi

# ---------------------------------------------------------------- Portainer
say "Portainer"
if ! docker ps -a --format '{{.Names}}' | grep -qx portainer; then
  docker volume create portainer_data >/dev/null
  docker run -d --name portainer --restart=always -p 9443:9443 -p 8000:8000 \
    -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data "$PORTAINER_IMAGE" >/dev/null
fi
docker start portainer >/dev/null 2>&1 || true
P="https://127.0.0.1:9443/api"
pt_wait() { for _ in $(seq 1 60); do curl -ksf "$P/system/status" >/dev/null && return 0; sleep 2; done; return 1; }
pt_wait || die "Portainer startet nicht (docker logs portainer)"
pt_body() { jq -n --arg u "$PORTAINER_USER" --arg p "$PORTAINER_PASSWORD" '{Username:$u,Password:$p}'; }
pt_auth() { curl -ks -X POST "$P/auth" -H 'Content-Type: application/json' -d "$(pt_body)" | jq -r '.jwt // empty' 2>/dev/null; }
pt_has_admin() { [ "$(curl -ks -o /dev/null -w '%{http_code}' "$P/users/admin/check")" = 204 ]; }
# Neuere Portainer-Versionen verlangen bei der Ersteinrichtung ein Setup-Token (Header X-Setup-Token),
# das beim Start ins Log geschrieben wird („no administrator account configured … setup_token=…“). Ältere ignorieren den Header.
pt_token() {
  local t="" i
  for i in 1 2 3 4 5; do   # Token steht direkt nach dem Start im Log; ältere Versionen haben keins
    t=$(docker logs portainer 2>&1 | grep -i 'setup.token' | grep -oE '[0-9a-fA-F]{64}' | tail -1 || true)
    [ -n "$t" ] && break
    sleep 1
  done
  printf '%s' "$t"
}
pt_init() {
  local tok; tok=$(pt_token)
  curl -ks -o /tmp/pt_init.out -w '%{http_code}' -X POST "$P/users/admin/init" -H 'Content-Type: application/json' \
    ${tok:+-H "X-Setup-Token: $tok"} -d "$(pt_body)"
}

if ! pt_has_admin; then
  code=$(pt_init)
  if [ "$code" != 200 ]; then
    # Portainer sperrt die Ersteinrichtung 5 Minuten nach dem Start („timed out for security purposes“) – neu starten
    warn "Portainer-Ersteinrichtung gesperrt ($code: $(head -c 120 /tmp/pt_init.out 2>/dev/null)) – starte Portainer neu"
    docker restart portainer >/dev/null; sleep 3; pt_wait || die "Portainer startet nicht"
    code=$(pt_init)
  fi
  [ "$code" = 200 ] || die "Portainer-Admin konnte nicht angelegt werden ($code: $(head -c 200 /tmp/pt_init.out 2>/dev/null))"
  ok "Portainer-Admin $PORTAINER_USER angelegt"
fi
JWT=$(pt_auth)
tries=0
while [ -z "$JWT" ]; do
  tries=$((tries+1))
  [ "$INTERACTIVE" = 1 ] || die "Anmeldung bei Portainer fehlgeschlagen – Portainer war schon eingerichtet. PORTAINER_USER/PORTAINER_PASSWORD des bestehenden Portainer angeben."
  CH=""
  menu CH "Portainer" "Anmeldung bei Portainer als „$PORTAINER_USER“ fehlgeschlagen.\n\nPortainer war auf diesem Rechner schon eingerichtet – vermutlich mit einem anderen Passwort (z. B. von einem früheren Versuch)." retry \
    retry "Zugangsdaten des bestehenden Portainer eingeben" \
    reset "Portainer zurücksetzen (Portainer-Einstellungen löschen, Container laufen weiter)" \
    quit "Abbrechen"
  case "$CH" in
    retry)
      PORTAINER_USER=""; PORTAINER_PASSWORD=""
      ask PORTAINER_USER "Portainer" "Benutzername des bestehenden Portainer:" "admin"
      ask_pw PORTAINER_PASSWORD "Portainer" "Passwort des bestehenden Portainer" 1 ;;
    reset)
      docker rm -f portainer >/dev/null 2>&1 || true; docker volume rm portainer_data >/dev/null 2>&1 || true
      docker volume create portainer_data >/dev/null
      docker run -d --name portainer --restart=always -p 9443:9443 -p 8000:8000 \
        -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data "$PORTAINER_IMAGE" >/dev/null
      pt_wait || die "Portainer startet nicht"
      [ ${#PORTAINER_PASSWORD} -ge 12 ] || { PORTAINER_PASSWORD=""; ask_pw PORTAINER_PASSWORD "Portainer" "Neues Passwort für Portainer" 12; }
      code=$(pt_init); [ "$code" = 200 ] || die "Portainer-Admin konnte nicht angelegt werden ($code)"
      ok "Portainer zurückgesetzt, Admin $PORTAINER_USER angelegt" ;;
    *) die "Abgebrochen" ;;
  esac
  JWT=$(pt_auth)
  [ $tries -lt 5 ] || die "Anmeldung bei Portainer fehlgeschlagen"
done
AUTH="Authorization: Bearer $JWT"
EP=$(curl -ksf -H "$AUTH" "$P/endpoints" | jq -r '[.[] | select(.Type==1)][0].Id // empty')
if [ -z "$EP" ]; then
  EP=$(curl -ksf -H "$AUTH" -X POST "$P/endpoints" -F Name=local -F EndpointCreationType=1 | jq -r .Id)
fi
[ -n "$EP" ] || die "Keine Docker-Umgebung in Portainer"
ok "Portainer läuft – Umgebung $EP"

deploy_stack() {   # deploy_stack NAME COMPOSE ENV_JSON
  local name=$1 compose=$2 env=$3 id
  id=$(curl -ksf -H "$AUTH" "$P/stacks" | jq -r --arg n "$name" '.[] | select(.Name==$n) | .Id' | head -1)
  if [ -n "$id" ]; then
    curl -ksf -H "$AUTH" -X PUT "$P/stacks/$id?endpointId=$EP" -H 'Content-Type: application/json' \
      -d "$(jq -n --arg c "$compose" --argjson e "$env" '{stackFileContent:$c, env:$e, prune:true, pullImage:true}')" >/dev/null \
      || die "Stack $name konnte nicht aktualisiert werden"
    ok "Stack $name aktualisiert"
    return
  fi
  local body; body=$(jq -n --arg n "$name" --arg c "$compose" --argjson e "$env" '{name:$n, stackFileContent:$c, env:$e}')
  curl -ksf -H "$AUTH" -X POST "$P/stacks/create/standalone/string?endpointId=$EP" -H 'Content-Type: application/json' -d "$body" >/dev/null \
    || curl -ksf -H "$AUTH" -X POST "$P/stacks?type=2&method=string&endpointId=$EP" -H 'Content-Type: application/json' -d "$body" >/dev/null \
    || die "Stack $name konnte nicht angelegt werden"
  ok "Stack $name angelegt"
}

# ---------------------------------------------------------------- Lancache
if [ "$WITH_CACHE" = 1 ]; then
  say "Lancache"
  CACHE_COMPOSE=$(cat <<'YML'
services:
  lancache-dns:
    image: lancachenet/lancache-dns:latest
    container_name: lancache-dns
    restart: unless-stopped
    ports:
      - "${LANCACHE_IP}:53:53/udp"
      - "${LANCACHE_IP}:53:53/tcp"
    environment:
      USE_GENERIC_CACHE: "true"
      LANCACHE_IP: ${LANCACHE_IP}
      UPSTREAM_DNS: ${UPSTREAM_DNS}
  monolithic:
    image: lancachenet/monolithic:latest
    container_name: lancache
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ${CACHE_DIR}/data:/data/cache
      - ${CACHE_DIR}/logs:/data/logs
    environment:
      CACHE_DISK_SIZE: ${CACHE_SIZE}
      CACHE_INDEX_SIZE: 500m
      CACHE_MAX_AGE: 3650d
      UPSTREAM_DNS: ${UPSTREAM_DNS}
YML
)
  deploy_stack "$STACK_CACHE" "$CACHE_COMPOSE" "$(jq -n --arg ip "$LAN_IP" --arg d "$CACHE_DIR" --arg s "$CACHE_SIZE" --arg u "$UPSTREAM_DNS" \
    '[{name:"LANCACHE_IP",value:$ip},{name:"CACHE_DIR",value:$d},{name:"CACHE_SIZE",value:$s},{name:"UPSTREAM_DNS",value:$u}]')"
fi

# ---------------------------------------------------------------- Spielservermanager
say "Spielservermanager"
GSM_COMPOSE=$(cat <<'YML'
services:
  spielservermanager:
    image: ${IMAGE}
    container_name: spielservermanager
    user: "0:0"                     # Zugriff auf den Docker-Socket (legt Spielserver-Container an)
    restart: unless-stopped
    pull_policy: always
    ports:
      - "${WEB_PORT}:8080"
    environment:
      ADMIN_PASSWORD: ${ADMIN_PASSWORD}
      TOOL_PORT: ${WEB_PORT}
      SESSION_HOURS: "24"
      RCON_TIMEOUT: "4"
      TZ: ${TZ}
    volumes:
      - gsm-data:/data
      - /var/run/docker.sock:/var/run/docker.sock
      - /proc:/host/proc:ro
volumes:
  gsm-data:
    name: spielservermanager-data
YML
)
TZ_HOST=$(cat /etc/timezone 2>/dev/null || timedatectl show -p Timezone --value 2>/dev/null || echo Europe/Berlin)
deploy_stack "$STACK_GSM" "$GSM_COMPOSE" "$(jq -n --arg i "$GSM_IMAGE" --arg p "$GSM_PASSWORD" --arg w "$GSM_PORT" --arg t "${TZ_HOST:-Europe/Berlin}" \
  '[{name:"IMAGE",value:$i},{name:"ADMIN_PASSWORD",value:$p},{name:"WEB_PORT",value:$w},{name:"TZ",value:$t}]')"

G="http://127.0.0.1:$GSM_PORT"
for _ in $(seq 1 90); do curl -sf "$G/api/version" >/dev/null && break; sleep 2; done
curl -sf "$G/api/version" >/dev/null || die "Spielservermanager startet nicht (docker logs spielservermanager)"
ok "Weboberfläche erreichbar"

# ---------------------------------------------------------------- Einrichten: Benutzer + Ordner
JAR=$(mktemp); trap 'rm -f "$JAR"' EXIT
gsm_login() { curl -sf -c "$JAR" -X POST "$G/api/login" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg u "$1" --arg p "$GSM_PASSWORD" '{username:$u,password:$p}')" >/dev/null; }
if ! gsm_login "$GSM_USER" && ! gsm_login admin; then
  warn "Anmeldung am Spielservermanager nicht möglich – vermutlich von einer früheren Installation mit anderem Passwort."
  warn "Stack ist aktualisiert; Benutzer und Ordner bitte in der Weboberfläche prüfen (Notzugang aus dem LAN: admin + ADMIN_PASSWORD aus dem Stack)."
  GSM_SKIP_SETUP=1
fi
if [ "${GSM_SKIP_SETUP:-0}" != 1 ]; then
  curl -sf -b "$JAR" -X PUT "$G/api/settings" -H 'Content-Type: application/json' \
    -d "$(jq -n --arg g "$GAMES_DIR" --arg b "$BRAND" --arg c "${CACHE_DIR:-}" '{games_base:$g, brand:$b} + (if $c != "" then {cache_dir:$c} else {} end)')" >/dev/null \
    && ok "Spielserver-Ordner: $GAMES_DIR" || warn "Spielserver-Ordner konnte nicht gesetzt werden"
fi
if [ "$GSM_USER" != "admin" ] && [ "${GSM_SKIP_SETUP:-0}" != 1 ]; then
  curl -sf -b "$JAR" -X POST "$G/api/users" -H 'Content-Type: application/json' \
    -d "$(jq -n --arg u "$GSM_USER" --arg p "$GSM_PASSWORD" '{username:$u,password:$p,role:"admin"}')" >/dev/null \
    && ok "Benutzer $GSM_USER angelegt (Administrator)" || warn "Benutzer $GSM_USER gibt es schon"
  # Start-Benutzer „admin“ entfernen (Notzugang aus dem LAN mit dem Stack-Passwort ADMIN_PASSWORD bleibt möglich)
  JAR2=$(mktemp)
  if curl -sf -c "$JAR2" -X POST "$G/api/login" -H 'Content-Type: application/json' \
       -d "$(jq -n --arg u "$GSM_USER" --arg p "$GSM_PASSWORD" '{username:$u,password:$p}')" >/dev/null; then
    curl -sf -b "$JAR2" -X DELETE "$G/api/users/admin" >/dev/null 2>&1 || true
  fi
  rm -f "$JAR2"
fi

# Hinweis am Anmeldebildschirm der Konsole (agetty: \4 = aktuelle IPv4-Adresse)
if [ -d /etc/issue.d ] || mkdir -p /etc/issue.d 2>/dev/null; then
  cat > /etc/issue.d/gsm.issue <<ISSUE || true

  Spielservermanager:  http://\\4:$GSM_PORT   (Bedienung im Browser)
  Portainer:                   https://\\4:9443
  Diese Konsolen-Anmeldung ist nur für Linux-Wartung (Benutzer mit sudo, z. B. gsm).

ISSUE
fi

echo
printf '%s\n' "${c_ok}${c_b}Fertig!${c_0}"
echo
printf '  Spielservermanager:  %shttp://%s:%s%s   (Benutzer %s)\n' "$c_b" "$LAN_IP" "$GSM_PORT" "$c_0" "$GSM_USER"
printf '  Portainer:           https://%s:9443   (Benutzer %s)\n' "$LAN_IP" "$PORTAINER_USER"
[ "$WITH_CACHE" = 1 ] && printf '  Lancache:            DNS-Server der Clients/DHCP auf %s stellen\n' "$LAN_IP"
echo
printf '%s\n' "  Updates: Portainer → Stacks → $STACK_GSM → „Update the stack“ mit „Re-pull image“ (oder dieses Skript erneut ausführen)."
printf '%s\n' "  Für Spieler aus dem Internet die Spielports im Router freigeben (Bereich unter Automatik & Einstellungen)."
