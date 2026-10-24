# Installation auf einem frischen Linux

Ein Befehl richtet alles ein: **Docker**, **Portainer** und den **Spielservermanager** (als Portainer-Stack), auf Wunsch auch **Lancache**.

```bash
curl -fsSL https://github.com/JMJ1337/cs2-rcon-web/releases/latest/download/install.sh | sudo bash
```

Getestet für **Debian 12/13** und **Ubuntu 22.04/24.04** (64 Bit, x86 oder ARM). Der Rechner braucht Internet.

## Alles in einem: Installations-ISO (Debian + Spielservermanager)

Am Release hängt `gsm-debian-<version>-amd64.iso` – auf einen USB-Stick schreiben (z. B. mit balenaEtcher/Rufus im DD-Modus)
oder in einer VM (Proxmox, VMware, VirtualBox) einbinden und davon starten:

1. Im Startmenü ist **„Spielservermanager – automatische Installation“** vorausgewählt (startet nach 10 s).
2. Der Debian-Installer fragt nur noch: **Passwort für den Benutzer `gsm`** (hat sudo) und die **Festplatte** –
   die ausgewählte Platte wird **komplett gelöscht**.
3. Nach dem Neustart startet auf dem Bildschirm automatisch die Einrichtung (gleiche Fragen wie unten:
   Benutzer, Passwörter, Ordner, Lancache) und richtet Docker, Portainer und den Spielservermanager ein.

**VM unter Hyper-V/VirtualBox:** Die VM muss an einem **externen Switch / einer Netzwerkbrücke** hängen. Der Hyper-V-„Default Switch“
(Adressen 172.16–31.x) und VirtualBox-NAT (10.0.2.x) sind interne NAT-Netze – darüber ist die VM aus dem LAN nicht erreichbar.
Hyper-V-Manager → *Manager für virtuelle Switches* → *Externes Netzwerk* mit der echten Netzwerkkarte, VM darauf umstellen, neu starten.
Das Skript erkennt solche Adressen und weist darauf hin.

Sprache Deutsch, Tastatur deutsch, Zeitzone Europe/Berlin, Netzwerk per DHCP, Rechnername `spielserver`, SSH-Server an.
Internet wird während der Installation gebraucht (Debian-Pakete, Docker-Images).

## Geführte Einrichtung

Das Skript läuft als geführte Oberfläche (Menüs, Pfeiltasten/Tab/Enter). Die **IP-Adresse wird automatisch erkannt**.

### Speicherort für Spielserver und Lancache

| Auswahl | Was passiert |
|---|---|
| **Lokal – im Benutzerordner** | `/home/<benutzer>/spielserver` bzw. `/home/<benutzer>/lancache` |
| **Lokal – eigener Ordner** | beliebiger Pfad, z. B. eine zweite Platte |
| **Netzwerk – iSCSI** (empfohlen) | installiert `open-iscsi`, sucht die Ziele am NAS, meldet sich an (optional CHAP), formatiert eine **leere** LUN nach Rückfrage (ext4) und hängt sie dauerhaft unter `/mnt/gsm-…` ein. Block-Zugriff – deutlich schneller als NFS/SMB, ideal für den Lancache |
| **Netzwerk – NFS** | installiert `nfs-common`, Eintrag in `/etc/fstab`, eingehängt unter `/mnt/gsm-…` |
| **Netzwerk – SMB/CIFS** | installiert `cifs-utils`, Zugangsdaten in `/etc/gsm-*.cred`, eingehängt unter `/mnt/gsm-…` (langsamer, ohne Linux-Rechte) |

Für iSCSI am NAS (z. B. Synology: SAN Manager → LUN + Ziel) den **Initiator des Servers** erlauben – den Namen zeigt das Skript bei einem Fehler an
(`/etc/iscsi/initiatorname.iscsi`).

**Später ändern:** Weboberfläche → *Automatik & Einstellungen* → „Basisordner für neue Spielserver“ und „Lancache-Ordner“
(stellt den Lancache-Container auf den neuen Ordner um). Netzwerkspeicher dafür vorher einhängen – *Speicher (iSCSI)* erzeugt das Skript,
oder das Installationsskript erneut ausführen.

## Was das Skript fragt

| Frage | Vorgabe | Wozu |
|---|---|---|
| IP-Adresse im LAN | automatisch erkannt, zum Bestätigen | Adresse, unter der Spieler und Browser den Rechner erreichen. Im Router fest vergeben (DHCP-Reservierung) |
| Port der Weboberfläche | `8090` | `http://<IP>:8090` |
| Name der Veranstaltung | `LAN` | erscheint in Servernamen („LAN CS #1 Wingman“), Titeln, Benachrichtigungen |
| Benutzername + Passwort Spielservermanager | `admin` | dein Admin-Konto (mind. 8 Zeichen) |
| Benutzername + Passwort Portainer | `admin` | mind. 12 Zeichen (Vorgabe von Portainer), gleiches Passwort möglich |
| Speicherort Spielserver | lokal im Benutzerordner | lokal / eigener Ordner / iSCSI / NFS / SMB |
| Lancache mitinstallieren? | nein | lokaler Download-Cache für Steam, Epic, Battle.net … |
| Speicherort + Größe für den Cache | lokal im Benutzerordner, `1000g` | nur mit Lancache. Ist der Cache voll, fliegen die am längsten unbenutzten Spiele raus |
| Upstream-DNS | `1.1.1.1 8.8.8.8` | nur mit Lancache: Der Lancache ist DNS-Server der Spieler-PCs; alles, was er nicht cacht (Webseiten, Logins …), fragt er bei diesen „vorgelagerten“ Servern nach. Cloudflare `1.1.1.1`, Google `8.8.8.8`, Quad9 `9.9.9.9` – oder die Router-IP, damit lokale Namen (NAS, Drucker) auflösbar bleiben |
| HTTPS von außen (Cloudflare-Tunnel)? | nein | Token aus Cloudflare Zero Trust, siehe [CLOUDFLARE.md](CLOUDFLARE.md) – ohne Portfreigabe |

Am Ende steht eine Zusammenfassung – erst nach „j“ wird installiert.

**Standard-Passwörter:** Neue Spielserver bekommen bei einer Neuinstallation das Beitritts- und RCON-Passwort `123456789`.
Bitte unter *Automatik & Einstellungen* ändern, wenn die Server aus dem Internet erreichbar sind.

## Was danach läuft

| Dienst | Adresse |
|---|---|
| Spielservermanager | `http://<IP>:8090` |
| Portainer | `https://<IP>:9443` |
| Lancache (optional) | DNS auf `<IP>:53`, Cache auf Port 80/443 |

Mit Lancache im DHCP/Router den **DNS-Server der Clients auf `<IP>`** stellen.
Läuft auf dem Rechner `systemd-resolved` (Ubuntu), schaltet das Skript dessen DNS-Stub auf Port 53 ab, damit lancache-dns ihn nutzen kann.

## Ohne Rückfragen (z. B. automatisiert)

Alle Antworten als Umgebungsvariablen übergeben und `GSM_YES=1` setzen:

```bash
curl -fsSL https://github.com/JMJ1337/cs2-rcon-web/releases/latest/download/install.sh | \
  sudo GSM_YES=1 LAN_IP=192.168.1.10 GSM_PORT=8090 GSM_USER=mj GSM_PASSWORD='geheim123' \
       PORTAINER_USER=admin PORTAINER_PASSWORD='mindestens12zeichen' GAMES_KIND=custom GAMES_DIR=/srv/gameserver \
       WITH_CACHE=1 CACHE_KIND=custom CACHE_DIR=/srv/lancache CACHE_SIZE=2000g UPSTREAM_DNS='1.1.1.1 8.8.8.8' bash
```

Weitere Variablen: `WITH_TUNNEL=1` + `TUNNEL_TOKEN` + `EXTERNAL_URL` (Cloudflare-Tunnel), `BRAND` (Name der Veranstaltung), `GSM_VERSION` (z. B. `1.0.0`, Standard `latest`), `GSM_IMAGE`, `PORTAINER_IMAGE`.

## Update

- **Portainer** → Stacks → `spielservermanager` → *Update the stack* mit *Re-pull image*, oder
- das Installationsskript einfach **erneut ausführen** – vorhandene Stacks werden aktualisiert, Daten bleiben erhalten.

## Daten & Sicherung

- Einstellungen, Benutzer, Spieler, Turniere: Docker-Volume `spielservermanager-data`
- Spielserver: der gewählte Spielserver-Ordner (Standard `/srv/gameserver`), darin `_bibliothek/` mit allen über die Oberfläche hinzugefügten Maps und Mods
- Notzugang: Benutzer `admin` mit dem Passwort aus der Stack-Variable `ADMIN_PASSWORD` (Portainer → Stack → Environment variables) –
  standardmäßig **nur aus dem LAN** (änderbar unter *Automatik & Einstellungen*); ein gelöschter `admin` wird dabei wieder angelegt

## Spieler aus dem Internet

Spielports im Router auf `<IP>` weiterleiten. Den Port-Bereich für neue Server stellst du unter *Automatik & Einstellungen* ein.
