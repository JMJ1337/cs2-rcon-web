# Spielservermanager

Weboberfläche für die Spielserver auf unserer LAN – als Docker-Container mit Portainer-Stack und Auto-Update.
(Repository-/Image-Name ist aus historischen Gründen `cs2-rcon-web`.)

| Spiel | Status & Spieler | Konsole / Befehle | Extras |
|---|---|---|---|
| **Counter-Strike 2** | RCON | RCON | Maps & Workshop-Suche, MatchZy-Wettkampf (Wingman/Competitive), Auto-Slots, Cvars |
| **Factorio** | RCON | RCON (`/players`, `/save` …) | Spiel speichern |
| **Satisfactory** | offizielle HTTPS-API (Port 7777) | `RunCommand` | Spiel speichern, Server beanspruchen |
| **Valheim** | Steam-Query (A2S, Spielport + 1) | – (hat keine Remote-Konsole) | Neustart/Logs über Docker |
| **Wreckfest** | Steam-Query (A2S, Query-Port) | – (Webkonsole des ich777-Images verlinkbar) | Neustart/Logs über Docker |

Außerdem:
- **Lancache-Metriken** in der Übersicht: aus dem Cache vs. aus dem Internet (24 h), Trefferquote, aktueller Durchsatz,
  Cache-Speicher, Aufteilung nach Dienst (Steam, Epic …). Liest das `access.log` des `lancachenet/monolithic`-Containers
  per Docker (wird automatisch erkannt, sonst Namen unter „Automatik & Einstellungen“ eintragen).
- **Spiele-Basisordner:** Neue Server landen unter `/mnt/grohlan/<spiel>/<name>` (einstellbar). Das NAS dafür auf dem
  Docker-Host dauerhaft mounten, z. B. per `/etc/fstab`:
  `192.168.200.13:/volume1/Grohlan  /mnt/grohlan  nfs  defaults,_netdev,nofail  0  0`
- **Beitreten:** Knopf „▶ Beitreten“ startet das Spiel über Steam und verbindet direkt (CS2/Wreckfest per `steam://connect`,
  Factorio/Valheim per Steam-Startparameter). Satisfactory hat keinen Link – dort Adresse kopieren.
- **Namen wie im Spiel:** Die Server heißen in der Liste automatisch so wie im Spiel (abschaltbar je Server).
- **Benutzerkonten** mit Rollen *Administrator*, *Spielleiter* (bedienen) und *Nur ansehen*. Sie liegen im Volume
  `cs2-rcon-data` und bleiben bei Updates erhalten. Erster Login: Benutzer `admin` + `ADMIN_PASSWORD`
  (funktioniert auch später noch als Notfall-Login).
- **Docker-Steuerung:** Container starten/stoppen/neu starten, Logs, CPU/RAM – pro Server einen Container verknüpfen.
- **Neue Server anlegen:** CS2, Factorio, Satisfactory, Valheim, Wreckfest als Container mit Datenordner auf dem NAS
  (Ordner wird angelegt und für den Container beschreibbar gemacht).
- **Netzwerk-Scan:** findet CS2/Valheim (A2S), Satisfactory (UDP-Query) im LAN und Spiel-Container in Docker,
  automatisch alle 15 Minuten (einstellbar) – gefundene Server mit einem Klick übernehmen.

Docker-Funktionen brauchen den Docker-Socket im Stack (`/var/run/docker.sock`, ist in `portainer-stack.yml` drin).
**Das gibt dem Tool volle Kontrolle über den Docker-Host** – im LAN mit Login vertretbar; wer das nicht will,
nimmt die Zeile raus, alles andere funktioniert weiter.

### CS2-Funktionen



**Funktionen:** Serververwaltung · Live-Status & Spielerliste (inkl. Kick) · Schnellaktionen
(Warmup, Restart, Pause, Teams tauschen, Bots …) · Map-/Modus-Wechsel & Workshop-Maps ·
Live-Konsole mit Verlauf · Server-Einstellungen (Cvars lesen & ändern) · Befehle an mehrere Server gleichzeitig ·
Login per Admin-Passwort. Läuft komplett offline (keine CDNs), also auch in LANs ohne Internet.

**Neu in v2:**
- **Übersicht aller Server** (Dashboard) mit Map, Modus, Spielern, MatchZy-Status
- **Automatische Spieleranzahl** je Modus und Map (`sv_visiblemaxplayers`), z. B. Wingman 4, Competitive 10, `aim_*` 2 –
  einstellbar unter „Automatik & Modi“. Obergrenze ist `SLOTS` im CS2-Stack (Standard jetzt 20).
- **Workshop-Maps suchen** (Steam Workshop, ohne API-Key), Vorschaubilder, Favoriten, Laden mit Modus
- **Wettkampfmodus mit MatchZy:** Presets Wingman 2v2 / Competitive 5v5, PUG-Schnellstart ohne Teamliste,
  Match mit Teams (SteamID64), Bo1/Bo3/Bo5, Veto oder feste Reihenfolge, Match-Steuerung, Verlauf
- **Spieler & SteamIDs:** SteamID64, `STEAM_0:…`, `[U:1:…]`, Profil-Link oder Steam-Kurzname – Name/Avatar werden geladen

Für Workshop-Suche und SteamID-Auflösung braucht der Docker-Host Internet. Die CS2-Server laden Match-Configs
per `matchzy_loadmatch_url` direkt von diesem Tool – unter „Automatik & Modi“ die LAN-Adresse eintragen
(z. B. `http://192.168.200.27:8090`).

## Repository-Aufbau

| Datei | Zweck |
|---|---|
| `app/` | Backend (FastAPI + RCON-Client) und Weboberfläche |
| `Dockerfile` | Image-Definition |
| `.github/workflows/docker.yml` | baut bei jedem Push auf `main` bzw. Tag `v*` ein Image (amd64 + arm64) nach `ghcr.io` |
| `portainer-stack.yml` | Stack für Portainer (zieht das fertige Image) |
| `stack.env` | Vorlage für die Stack-Variablen |
| `docker-compose.yml` | lokal selbst bauen ohne Registry (`docker compose up -d --build`) |

## 1. Repo auf GitHub anlegen

1. Auf GitHub ein neues, leeres Repository `cs2-rcon-web` anlegen (privat oder öffentlich, **ohne** README).
2. Lokal:
   ```bash
   git remote add origin https://github.com/<NAME>/cs2-rcon-web.git
   git push -u origin main
   ```
3. Unter **Actions** läuft „Docker-Image bauen“ (~3–5 Min.). Danach gibt es das Image
   `ghcr.io/<name>/cs2-rcon-web:latest` (Name immer kleingeschrieben).
4. **Image-Sichtbarkeit:** Neue Pakete auf ghcr.io sind privat. Entweder
   - unter *Profil → Packages → cs2-rcon-web → Package settings → Change visibility* auf **Public** stellen, oder
   - privat lassen und in Portainer eine Registry hinterlegen (siehe unten).

Versionen: `git tag v1.0.0 && git push --tags` erzeugt zusätzlich die Tags `1.0.0` und `1.0`.

## 2. Stack in Portainer

**Variante A – Repository (empfohlen, Updates per Klick):**
*Stacks → Add stack → Repository*
- Repository URL: `https://github.com/<NAME>/cs2-rcon-web`
- Reference: `refs/heads/main` · Compose path: `portainer-stack.yml`
- Bei privatem Repo: *Authentication* aktivieren, GitHub-Benutzer + Personal Access Token (Scope `repo`)
- *Environment variables* → „Load variables from .env file“ → `stack.env` hochladen und anpassen,
  mindestens **`IMAGE`** und **`ADMIN_PASSWORD`**
- Optional *GitOps updates* aktivieren (Polling oder Webhook), dann deployt Portainer Änderungen selbst.

**Variante B – Web editor:** Inhalt von `portainer-stack.yml` einfügen, Variablen wie oben setzen.

**Privates Image:** *Registries → Add registry → Custom registry* – URL `ghcr.io`, Benutzer = GitHub-Name,
Passwort = Personal Access Token mit Scope `read:packages`.

Danach: `http://<Docker-Host>:8080` (bzw. `WEB_PORT`).

### Stack-Variablen

| Variable | Standard | Bedeutung |
|---|---|---|
| `IMAGE` | `ghcr.io/dein-github-name/cs2-rcon-web:latest` | Image (z. B. `:1.0.0` zum Festpinnen) |
| `ADMIN_PASSWORD` | – (Pflicht) | Login-Passwort der Weboberfläche |
| `WEB_PORT` | `8080` | Port auf dem Docker-Host |
| `SESSION_HOURS` | `24` | Gültigkeit eines Logins |
| `RCON_TIMEOUT` | `4` | Timeout pro RCON-Befehl (Sek.) |
| `TZ` | `Europe/Berlin` | Zeitzone |

### Automatische Updates

Nach jedem Image-Build setzt die GitHub Action einen Build-Stempel in `portainer-stack.yml`. Damit Portainer das
automatisch übernimmt, beim RCON-Stack (Repository-Stack) einschalten:
*GitOps updates* → Mechanism **Polling**, Intervall z. B. `5m`, **Re-pull image** an.

Die CS2-Server-Stacks (`cs2-server/`) besser **ohne** GitOps-Polling betreiben, sonst startet Portainer sie bei
Repo-Änderungen evtl. mitten im Match neu – dort Updates per Hand („Pull and redeploy“).

### Update von Hand

Code pushen → Action baut neues Image → in Portainer beim Stack **Update the stack** mit
**„Re-pull image and redeploy“** (bzw. *Pull and redeploy* bei Repository-Stacks).
Die Serverliste bleibt im Volume `cs2-rcon-data` erhalten.

## CS2-Server vorbereiten

RCON ist bei CS2 standardmäßig aus. Der Dedicated Server braucht:

- Startparameter **`-usercon`**
- in der `server.cfg` (oder per Startparameter `+rcon_password ...`): `rcon_password "geheim"`
- TCP-Port 27015 (bzw. euer `-port`) muss vom Docker-Host aus erreichbar sein (Firewall!).

In der Weboberfläche dann „+ Server hinzufügen“ → IP, Port, RCON-Passwort → „Verbindung testen“.

## Hinweise

- Die Serverliste liegt im Volume unter `/data/servers.json`. RCON-Passwörter stehen dort im Klartext –
  für ein LAN okay, die Weboberfläche aber nicht ins Internet freigeben.
- Laufen die CS2-Server auf demselben Host mit `network_mode: host`, im Tool die Host-IP eintragen.
- Spielmodus-Wechsel nutzt `game_type`/`game_mode` + `map` (lädt die Map neu). Ohne Modus wird `changelevel` verwendet.
- Workshop-Maps (`host_workshop_map`) brauchen Internet am CS2-Server.

## Lokal entwickeln

```bash
pip install -r requirements.txt
DATA_DIR=./data ADMIN_PASSWORD=test uvicorn app.main:app --reload --port 8080
```
