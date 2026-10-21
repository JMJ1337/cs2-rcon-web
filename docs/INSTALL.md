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

Sprache Deutsch, Tastatur deutsch, Zeitzone Europe/Berlin, Netzwerk per DHCP, Rechnername `spielserver`, SSH-Server an.
Internet wird während der Installation gebraucht (Debian-Pakete, Docker-Images).

## Was das Skript fragt

| Frage | Vorgabe | Wozu |
|---|---|---|
| IP-Adresse im LAN | wird erkannt | Adresse für Spieler, Lancache-DNS |
| Port der Weboberfläche | `8090` | `http://<IP>:8090` |
| Benutzername + Passwort Spielservermanager | `admin` | dein Admin-Konto (mind. 8 Zeichen) |
| Benutzername + Passwort Portainer | `admin` | mind. 12 Zeichen (Vorgabe von Portainer), gleiches Passwort möglich |
| Ordner für die Spielserver | `/srv/gameserver` | Spieldateien, Spielstände, Bibliothek (Maps/Mods) |
| Lancache mitinstallieren? | nein | lokaler Download-Cache für Steam, Epic, Battle.net … |
| Ordner + Größe für den Cache | `/srv/lancache`, `1000g` | nur mit Lancache |
| Upstream-DNS | `1.1.1.1 8.8.8.8` | nur mit Lancache |

Am Ende steht eine Zusammenfassung – erst nach „j“ wird installiert.

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
       PORTAINER_USER=admin PORTAINER_PASSWORD='mindestens12zeichen' GAMES_DIR=/srv/gameserver \
       WITH_CACHE=1 CACHE_DIR=/srv/lancache CACHE_SIZE=2000g UPSTREAM_DNS='1.1.1.1 8.8.8.8' bash
```

Weitere Variablen: `GSM_VERSION` (z. B. `1.0.0`, Standard `latest`), `GSM_IMAGE`, `PORTAINER_IMAGE`.

## Update

- **Portainer** → Stacks → `spielservermanager` → *Update the stack* mit *Re-pull image*, oder
- das Installationsskript einfach **erneut ausführen** – vorhandene Stacks werden aktualisiert, Daten bleiben erhalten.

## Daten & Sicherung

- Einstellungen, Benutzer, Spieler, Turniere: Docker-Volume `spielservermanager-data`
- Spielserver: der gewählte Spielserver-Ordner (Standard `/srv/gameserver`), darin `_bibliothek/` mit allen über die Oberfläche hinzugefügten Maps und Mods
- Notzugang: Benutzer `admin` mit dem Passwort aus der Stack-Variable `ADMIN_PASSWORD` (Portainer → Stack → Environment variables)

## Spieler aus dem Internet

Spielports im Router auf `<IP>` weiterleiten. Den Port-Bereich für neue Server stellst du unter *Automatik & Einstellungen* ein.
