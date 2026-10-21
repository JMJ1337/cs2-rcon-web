#!/usr/bin/env bash
# ============================================================================================
#  GrohLAN Spielservermanager – Installer für ein frisches Linux (Debian / Ubuntu)
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

# Eingaben auch bei "curl | bash" von der Tastatur lesen
TTY=/dev/tty
ask() {          # ask VAR "Frage" "Vorgabe"
  local __var=$1 __q=$2 __def=${3:-} __ans
  if [ -n "${!__var:-}" ]; then return; fi
  if [ "${GSM_YES:-}" = "1" ] || [ ! -r $TTY ]; then printf -v "$__var" '%s' "$__def"; return; fi
  read -r -p "  $__q${__def:+ [$__def]}: " __ans < $TTY || true
  printf -v "$__var" '%s' "${__ans:-$__def}"
}
ask_pw() {       # ask_pw VAR "Frage" Mindestlänge
  local __var=$1 __q=$2 __min=${3:-8} __a __b
  if [ -n "${!__var:-}" ]; then return; fi
  [ -r $TTY ] || die "$__q: bitte als Umgebungsvariable $__var übergeben"
  while true; do
    read -r -s -p "  $__q (mind. $__min Zeichen): " __a < $TTY; echo
    [ ${#__a} -ge "$__min" ] || { warn "zu kurz"; continue; }
    read -r -s -p "  wiederholen: " __b < $TTY; echo
    [ "$__a" = "$__b" ] || { warn "stimmt nicht überein"; continue; }
    printf -v "$__var" '%s' "$__a"; return
  done
}
yesno() {        # yesno VAR "Frage" j|n
  local __yv=$1 __yq=$2 __yd=${3:-n} __ya=""
  if [ -n "${!__yv:-}" ]; then return; fi
  if [ "${GSM_YES:-}" = "1" ] || [ ! -r $TTY ]; then __ya=$__yd
  else read -r -p "  $__yq (j/n) [$__yd]: " __ya < $TTY || true; __ya=${__ya:-$__yd}; fi
  case "${__ya,,}" in j|ja|y|yes) printf -v "$__yv" 1 ;; *) printf -v "$__yv" 0 ;; esac
}

# ---------------------------------------------------------------- Voraussetzungen
[ "$(id -u)" = 0 ] || die "Bitte als root ausführen (… | sudo bash)"
. /etc/os-release 2>/dev/null || true
case "${ID:-}${ID_LIKE:-}" in
  *debian*|*ubuntu*) ;;
  *) warn "Getestet für Debian/Ubuntu – ${PRETTY_NAME:-unbekanntes System} wird trotzdem versucht" ;;
esac

echo
printf '%s\n' "${c_b}GrohLAN Spielservermanager – Installation${c_0}"
printf '%s\n' "${c_dim}Docker · Portainer · Spielservermanager · optional Lancache${c_0}"
echo

# ---------------------------------------------------------------- Fragen
LAN_IP_DEF=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' || true)
say "Netzwerk"
ask LAN_IP "IP-Adresse dieses Rechners im LAN" "${LAN_IP_DEF:-}"
[ -n "$LAN_IP" ] || die "Keine IP angegeben"
ask GSM_PORT "Port der Weboberfläche" "8090"

say "Benutzer"
ask GSM_USER "Benutzername für den Spielservermanager" "admin"
GSM_USER=$(printf '%s' "$GSM_USER" | tr 'A-Z' 'a-z' | tr -cd 'a-z0-9._-')
ask_pw GSM_PASSWORD "Passwort für $GSM_USER" 8
ask PORTAINER_USER "Benutzername für Portainer" "admin"
if [ -z "${PORTAINER_PASSWORD:-}" ] && [ ${#GSM_PASSWORD} -ge 12 ]; then
  yesno SAME_PW "Für Portainer dasselbe Passwort nehmen?" "j"
  [ "${SAME_PW:-0}" = 1 ] && PORTAINER_PASSWORD=$GSM_PASSWORD
fi
ask_pw PORTAINER_PASSWORD "Passwort für Portainer" 12

say "Ordner"
ask GAMES_DIR "Ordner für die Spielserver (Spieldateien, Spielstände, Bibliothek)" "/srv/gameserver"
case "$GAMES_DIR" in /*) ;; *) die "Bitte einen absoluten Pfad angeben" ;; esac

say "Lancache (lokaler Download-Cache für Steam, Epic, Battle.net …)"
yesno WITH_CACHE "Lancache mitinstallieren?" "n"
if [ "$WITH_CACHE" = 1 ]; then
  ask CACHE_DIR "Ordner für den Cache (viel Platz einplanen)" "/srv/lancache"
  case "$CACHE_DIR" in /*) ;; *) die "Bitte einen absoluten Pfad angeben" ;; esac
  ask CACHE_SIZE "Maximale Cache-Größe (z. B. 500g, 2000g)" "1000g"
  ask UPSTREAM_DNS "Upstream-DNS (Leerzeichen-getrennt)" "1.1.1.1 8.8.8.8"
fi

echo
say "Zusammenfassung"
printf '  Weboberfläche:  http://%s:%s  (Benutzer %s)\n' "$LAN_IP" "$GSM_PORT" "$GSM_USER"
printf '  Portainer:      https://%s:9443  (Benutzer %s)\n' "$LAN_IP" "$PORTAINER_USER"
printf '  Spielserver:    %s\n' "$GAMES_DIR"
[ "$WITH_CACHE" = 1 ] && printf '  Lancache:       %s (max. %s), DNS auf %s:53\n' "$CACHE_DIR" "$CACHE_SIZE" "$LAN_IP"
if [ "${GSM_YES:-}" != "1" ] && [ -r $TTY ]; then
  yesno GO "Jetzt installieren?" "j"; [ "$GO" = 1 ] || die "Abgebrochen"
fi

# ---------------------------------------------------------------- Pakete + Docker
say "Pakete"
if command -v apt-get >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq curl ca-certificates jq iproute2 >/dev/null
fi
command -v jq >/dev/null || die "jq fehlt und konnte nicht installiert werden"
ok "curl, jq"

say "Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh >/dev/null
fi
systemctl enable --now docker >/dev/null 2>&1 || true
docker info >/dev/null 2>&1 || die "Docker läuft nicht"
ok "Docker $(docker version -f '{{.Server.Version}}')"

mkdir -p "$GAMES_DIR"
ok "Ordner $GAMES_DIR"

# ---------------------------------------------------------------- Port 53 für Lancache-DNS frei machen
if [ "$WITH_CACHE" = 1 ]; then
  mkdir -p "$CACHE_DIR/data" "$CACHE_DIR/logs"
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
P="https://127.0.0.1:9443/api"
for _ in $(seq 1 60); do curl -ksf "$P/system/status" >/dev/null && break; sleep 2; done
curl -ksf "$P/system/status" >/dev/null || die "Portainer startet nicht (docker logs portainer)"
INIT=$(curl -ks -o /dev/null -w '%{http_code}' -X POST "$P/users/admin/init" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg u "$PORTAINER_USER" --arg p "$PORTAINER_PASSWORD" '{Username:$u,Password:$p}')")
[ "$INIT" = 200 ] && ok "Portainer-Admin $PORTAINER_USER angelegt" || warn "Portainer war schon eingerichtet – melde mich mit den angegebenen Daten an"
JWT=$(curl -ksf -X POST "$P/auth" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg u "$PORTAINER_USER" --arg p "$PORTAINER_PASSWORD" '{Username:$u,Password:$p}')" | jq -r .jwt) \
  || die "Anmeldung bei Portainer fehlgeschlagen (Benutzer/Passwort?)"
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
curl -sf -c "$JAR" -X POST "$G/api/login" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg p "$GSM_PASSWORD" '{username:"admin",password:$p}')" >/dev/null || die "Anmeldung am Spielservermanager fehlgeschlagen"
curl -sf -b "$JAR" -X PUT "$G/api/settings" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg g "$GAMES_DIR" '{games_base:$g}')" >/dev/null && ok "Spielserver-Ordner: $GAMES_DIR"
if [ "$GSM_USER" != "admin" ]; then
  curl -sf -b "$JAR" -X POST "$G/api/users" -H 'Content-Type: application/json' \
    -d "$(jq -n --arg u "$GSM_USER" --arg p "$GSM_PASSWORD" '{username:$u,password:$p,role:"admin"}')" >/dev/null \
    && ok "Benutzer $GSM_USER angelegt (Administrator)" || warn "Benutzer $GSM_USER gibt es schon"
  # Start-Benutzer „admin“ entfernen (Notzugang mit dem Stack-Passwort ADMIN_PASSWORD bleibt trotzdem möglich)
  JAR2=$(mktemp)
  if curl -sf -c "$JAR2" -X POST "$G/api/login" -H 'Content-Type: application/json' \
       -d "$(jq -n --arg u "$GSM_USER" --arg p "$GSM_PASSWORD" '{username:$u,password:$p}')" >/dev/null; then
    curl -sf -b "$JAR2" -X DELETE "$G/api/users/admin" >/dev/null 2>&1 || true
  fi
  rm -f "$JAR2"
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
