#!/usr/bin/env bash
# Baut aus dem offiziellen Debian-netinst-ISO ein Installations-ISO mit automatischer Einrichtung des Spielservermanagers.
# Nutzung: iso/build-iso.sh <ausgabe.iso>   (braucht xorriso, curl)
set -euo pipefail
OUT=${1:-gsm-debian-amd64.iso}
HERE=$(cd "$(dirname "$0")" && pwd)
W=$(mktemp -d)
BASE=${DEBIAN_ISO_BASE:-https://cdimage.debian.org/debian-cd/current/amd64/iso-cd}
NAME=$(curl -fsSL "$BASE/SHA256SUMS" | awk '/netinst\.iso$/ && !/edu|mac/ {print $2; exit}')
[ -n "$NAME" ] || { echo "netinst-ISO nicht gefunden"; exit 1; }
echo "Basis: $NAME"
curl -fsSL -o "$W/base.iso" "$BASE/$NAME"
(cd "$W" && curl -fsSL "$BASE/SHA256SUMS" | grep " $NAME\$" | sed "s| $NAME| base.iso|" | sha256sum -c -)

ENTRY_ARGS="auto=true priority=high preseed/file=/cdrom/preseed.cfg locale=de_DE.UTF-8 keymap=de language=de country=DE"
xorriso -osirrox on -indev "$W/base.iso" -extract /boot/grub/grub.cfg "$W/grub.cfg" 2>/dev/null
chmod u+w "$W/grub.cfg"
# eigener Menüeintrag ganz oben + Standard mit 10 s Wartezeit (UEFI)
python3 - "$W/grub.cfg" "$ENTRY_ARGS" <<'PY'
import sys, re
p, args = sys.argv[1], sys.argv[2]
s = open(p).read()
entry = ('set default=0\nset timeout=10\n'
         'menuentry --hotkey=s "Spielservermanager – automatische Installation" {\n'
         '    set background_color=black\n'
         f'    linux    /install.amd/vmlinuz {args} --- quiet\n'
         '    initrd   /install.amd/initrd.gz\n}\n')
i = s.find("menuentry")
s = s[:i] + entry + s[i:]
open(p, "w").write(s)
PY
MAPS=(-map "$W/grub.cfg" /boot/grub/grub.cfg)
# BIOS-Start (isolinux), falls vorhanden
if xorriso -osirrox on -indev "$W/base.iso" -extract /isolinux/txt.cfg "$W/txt.cfg" 2>/dev/null; then
  chmod u+w "$W/txt.cfg"
  { printf 'default gsm\nlabel gsm\n\tmenu label ^Spielservermanager - automatische Installation\n\tmenu default\n\tkernel /install.amd/vmlinuz\n\tappend vga=788 initrd=/install.amd/initrd.gz %s --- quiet\n' "$ENTRY_ARGS"
    sed 's/^\(\s*\)menu default/\1# menu default/; s/^default .*//' "$W/txt.cfg"; } > "$W/txt2.cfg"
  MAPS+=(-map "$W/txt2.cfg" /isolinux/txt.cfg)
  for f in gtk.cfg menu.cfg; do          # andere „menu default“-Einträge entfernen, damit unserer vorausgewählt ist
    if xorriso -osirrox on -indev "$W/base.iso" -extract "/isolinux/$f" "$W/$f" 2>/dev/null; then
      chmod u+w "$W/$f"; sed -i 's/^\(\s*\)menu default/\1# menu default/' "$W/$f"; MAPS+=(-map "$W/$f" "/isolinux/$f")
    fi
  done
  if xorriso -osirrox on -indev "$W/base.iso" -extract /isolinux/isolinux.cfg "$W/isolinux.cfg" 2>/dev/null; then
    chmod u+w "$W/isolinux.cfg"; sed -i 's/^timeout .*/timeout 100/; s/^prompt .*/prompt 0/' "$W/isolinux.cfg"
    grep -q '^timeout' "$W/isolinux.cfg" || echo 'timeout 100' >> "$W/isolinux.cfg"
    MAPS+=(-map "$W/isolinux.cfg" /isolinux/isolinux.cfg)
  fi
fi
xorriso -indev "$W/base.iso" -outdev "$OUT" \
  -map "$HERE/preseed.cfg" /preseed.cfg \
  -map "$HERE/../install.sh" /gsm/install.sh \
  -map "$HERE/gsm-firstboot" /gsm/gsm-firstboot \
  -map "$HERE/gsm-firstboot.service" /gsm/gsm-firstboot.service \
  "${MAPS[@]}" \
  -boot_image any replay
rm -rf "$W"
ls -lh "$OUT"
