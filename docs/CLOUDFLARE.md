# HTTPS von außen mit Cloudflare-Tunnel

Mit einem **Cloudflare-Tunnel** ist der Spielservermanager aus dem Internet per **HTTPS** erreichbar, z. B. unter
`https://live.eure-lan.de` – **ohne Portfreigabe im Router**. Der kleine Container `cloudflared` baut die Verbindung
von innen nach außen zu Cloudflare auf, das Zertifikat kommt automatisch von Cloudflare.

Von außen erreichbar sind nur:

- öffentliche Seite und Steam-Anmeldung/Registrierung
- Homepage-API (`/api/v1`)
- eingebetteter Turnierbaum, Stream-Seite, OBS-Overlays
- Beitreten-Links und Map-Schnelldownload (FastDL)

Die **Verwaltung** (Login, Server steuern, Einstellungen) bleibt im LAN. Wer sie auch von unterwegs braucht:
*Automatik & Einstellungen* → „Verwaltung auch von außen über den Tunnel erlauben“ (dann gilt die normale Anmeldung mit
Login-Sperre nach Fehlversuchen – noch sicherer ist Cloudflare Access davor, siehe unten).

## 1. Domain zu Cloudflare

Der Tunnel braucht eine Domain, deren DNS bei Cloudflare liegt (kostenloses Konto reicht).
Geht die Firmendomain nicht, einfach eine eigene kleine Domain für die LAN nehmen (ca. 5–15 €/Jahr) und bei Cloudflare
hinzufügen – die Nameserver beim Domain-Anbieter auf die von Cloudflare angezeigten umstellen.

## 2. Tunnel anlegen

1. Cloudflare-Dashboard → **Zero Trust** → **Networks** → **Tunnels** → **Create a tunnel** → **Cloudflared**.
2. Namen vergeben (z. B. `spielserver`).
3. Bei **Install connector** den langen Token hinter `--token` kopieren (beginnt meist mit `eyJ…`).
4. **Public Hostname** hinzufügen:
   - Subdomain: z. B. `live`, Domain: eure Domain
   - Service: **HTTP**, URL: **`localhost:8090`** (Port eurer Weboberfläche)

## 3. Tunnel-Container starten

**Neuinstallation:** Das Installationsskript fragt danach („HTTPS von außen“) – Token einfügen, fertig.

**Bestehende Installation:** Portainer → **Stacks** → **Add stack**

- Name: `spielservermanager-tunnel`
- **Repository**: URL dieses Repos, Compose path `tunnel-stack.yml` – oder **Web editor** mit dem Inhalt von `tunnel-stack.yml`
- Environment variable: `TUNNEL_TOKEN` = der kopierte Token
- **Deploy the stack**

Im Cloudflare-Dashboard steht der Tunnel danach auf **Healthy**.

## 4. Im Spielservermanager

*Automatik & Einstellungen* → „Öffentliche HTTPS-Adresse“: `https://live.eure-lan.de` eintragen.
Die Homepage-API-Seite (🔌) zeigt dann diese Adresse. Unter 🔌 API die **erlaubten Homepage-Adressen** (CORS) prüfen.

Auf eurer Homepage die API-Adresse umstellen: `https://live.eure-lan.de/api/v1`.

## 5. Router aufräumen

Die bisherige Portfreigabe auf **8090 schließen** – sonst ist die Verwaltung weiter unverschlüsselt aus dem Internet erreichbar.
Für Spieler aus dem Internet bleiben nur die **Spielports** freigegeben (die laufen nicht über Cloudflare).

## Hinweise

- **Live-Video:** Im kostenlosen Cloudflare-Tarif ist das Ausliefern von Videostreams nicht erlaubt
  ([Richtlinie](https://developers.cloudflare.com/fundamentals/reference/policies-compliances/delivering-videos-with-cloudflare/)).
  API, Turnierbaum, Overlays und Spielstände sind kein Problem – den Livestream fürs Publikum besser über Twitch/YouTube.
- **Uploads** sind über Cloudflare auf 100 MB pro Anfrage begrenzt (große Maps im LAN hochladen).
- **Cloudflare Access** (Zero Trust → Access → Applications, kostenlos bis 50 Personen) kann die Verwaltung zusätzlich mit
  einem Login per E-Mail-Code schützen, wenn „Verwaltung von außen“ eingeschaltet ist.
- Fehlersuche: `docker logs spielservermanager-tunnel`.
