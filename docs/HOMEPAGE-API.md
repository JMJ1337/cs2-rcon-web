# GrohLAN Spielservermanager – Homepage-API

Mit dieser API kann die GrohLAN-Homepage folgende Dinge nutzen:

- **Turnier:** Status, Spielplan, Ergebnisse und Live-Spielstände lesen. Spieler an- und abmelden, Teams gründen, beitreten und verlassen.
- **Zuschauen:** Live-Stream und CSTV-Adressen der laufenden Spiele abrufen, außerdem fertige Seiten zum Einbetten (iframe).
- **Steam-Bot „GrohLan“:** Nachrichten, Einladungen zu Spielen und Freundschaftsanfragen, z. B. für das Finalturnier.

---

## 1. Zugang

| | |
|---|---|
| **Basis-URL** | `https://<tool-adresse>/api/v1`, z. B. `http://185.44.4.220:8090/api/v1`. Im Betrieb empfehlen wir HTTPS, siehe Abschnitt 6. |
| **Schlüssel** | Wird im Spielservermanager unter **🔌 API** erzeugt und nur einmal angezeigt. |
| **Header** | `X-API-Key: gsm_…`, alternativ `Authorization: Bearer gsm_…` |
| **Format** | JSON hin und zurück (`Content-Type: application/json`) |

Jeder Schlüssel hat eines oder mehrere Rechte:

| Recht | erlaubt |
|---|---|
| `tournament` | Turnier lesen, Spieler an- und abmelden, Teams verwalten, Serverliste lesen |
| `stream` | Stream-Status lesen |
| `bot` | Steam-Bot: Status, Freunde, Freundschaftsanfrage, Nachricht, Einladung |

> **Wichtig:** Den Schlüssel nur **serverseitig** benutzen, also im PHP- oder Node-Backend der Homepage, und nie im Browser-JavaScript.
> Wer den Schlüssel hat, kann in fremdem Namen Spieler anmelden und über den Bot schreiben.

**Ohne Schlüssel lesbar:** Ist unter 🔌 API die Option „ohne Schlüssel lesbar“ an, gehen `GET /tournament`, `GET /tournament/player/{steamid}`, `GET /servers` und `GET /stream` auch ohne Schlüssel. Damit kann der Browser diese Daten direkt abrufen. Erlaubte Homepage-Adressen für den Browserzugriff (CORS) werden dort ebenfalls eingetragen. Standard: `https://www.groh-lan.de` und `https://groh-lan.de`.

**Fehler:** HTTP-Status plus `{"detail": "Text"}`.

| Status | Bedeutung |
|---|---|
| 400 | ungültige Eingabe |
| 401 | Schlüssel fehlt oder ist falsch |
| 403 | Schlüssel hat dieses Recht nicht |
| 404 | nicht gefunden |
| 409 | Anmeldung geschlossen |
| 502 | Steam-Bot nicht erreichbar |

**Spieler-ID:** Spieler werden immer über ihre **SteamID64** angegeben (17 Ziffern, z. B. `76561197960287930`). Die Homepage bekommt sie über „Mit Steam anmelden“ (Steam OpenID). Am Ende der Antwort steht `claimed_id = https://steamcommunity.com/openid/id/<SteamID64>`.

---

## 2. Turnier

### `GET /tournament` – alles auf einen Blick

```json
{
  "active": true, "name": "Groh LAN Wingman-Turnier", "mode": "groups", "mode_label": "Gruppen + K.-o.",
  "status": "setup | waiting | running | done", "registration": true, "start": 1792500000,
  "teams":   [{"id": "t1a2b3", "name": "Die Lianen", "players": ["Anna", "Ben"], "steamids": ["7656…01", "7656…02"]}],
  "players": [{"steamid": "7656…01", "name": "Anna", "avatar": "https://…", "team": "t1a2b3"}],
  "matches": [{
      "id": "m5", "no": 5, "stage": "K", "round": 4, "label": "K.-o. · Halbfinale",
      "t1": "Die Lianen", "t2": "Jaguar", "p1": null, "p2": "Sieger #3",
      "s1": 7, "s2": 4, "status": "wait | ready | live | done", "winner": null, "walkover": false,
      "planned": 1792503600, "started": null, "map": "de_inferno", "server_name": "Groh CS #2",
      "tv_url": "steam://run/730//+connect%20185.44.4.220:27120", "tv_address": "185.44.4.220:27120"
  }],
  "groups": {"A": [{"team": "t1a2b3", "name": "Die Lianen", "played": 2, "won": 2, "lost": 0, "rf": 18, "ra": 9}]},
  "embed": "https://…/embed/tournament", "stream": "https://…/api/v1/stream"
}
```

**Status eines Turniers:**

| Status | Bedeutung |
|---|---|
| `setup` | Vorbereitung, Anmeldung möglich, wenn `registration` true ist |
| `waiting` | wartet, bis alle Server bereit sind |
| `running` | läuft |
| `done` | beendet |

**Felder eines Spiels:**

- **Ergebnis:** `s1`/`s2` sind die gewonnenen Runden. Während `status = live` steht dort der Live-Stand.
- **Platzhalter:** `p1`/`p2` stehen, solange ein Gegner noch nicht feststeht, z. B. „Sieger #3“ oder „1. Gruppe A“.
- **Zuschauen:** `tv_url` ist der CSTV-Link zum Zuschauen in CS2, nur bei laufenden Spielen. Zeitzonen-freie Zeiten sind Unix-Sekunden.

### `GET /tournament/player/{steamid}` – Status eines Spielers

```json
{"steamid": "7656…01", "registered": true, "registration_open": true, "status": "running",
 "team": {"id": "t1a2b3", "name": "Die Lianen", "players": ["7656…01", "7656…02"]},
 "next_match": {"id": "m5", "label": "K.-o. · Halbfinale", "status": "ready", "planned": 1792503600, "map": "de_inferno",
                "opponent": "Jaguar", "server": "Groh CS #2",
                "join": "Verbinden: 192.168.200.27:27115\nKlick zum Beitreten: http://192.168.200.27:8090/j/abc123"}}
```

Bei `join` stehen LAN-Spieler mit der LAN-Adresse drin und Spieler aus dem Internet mit der öffentlichen. Entscheidend ist die zuletzt gesehene Verbindung.

### Anmeldung und Teams

Das geht nur, solange `status = setup` und `registration = true` ist, sonst kommt `409`.

| Methode | Pfad | Body | Ergebnis |
|---|---|---|---|
| POST | `/tournament/register` | `{"steamid": "7656…", "name": "Anna", "avatar": "https://…"}` | Spieler angemeldet. Ist er schon angemeldet, wird nur der Name aktualisiert. |
| POST | `/tournament/unregister` | `{"steamid": "7656…"}` | abgemeldet und aus seinem Team entfernt |
| POST | `/tournament/teams` | `{"steamid": "7656…", "name": "Die Lianen"}` | Team gegründet, Antwort `{"id": "t…"}`. Der Name ist eindeutig und darf höchstens 24 Zeichen haben. |
| POST | `/tournament/teams/{id}/join` | `{"steamid": "7656…"}` | Spieler tritt bei. Ein Team hat 2 Spieler (Wingman). |
| POST | `/tournament/teams/leave` | `{"steamid": "7656…"}` | Spieler verlässt sein Team. Ein leeres Team wird gelöscht. |

Ablauf auf der Homepage:

1. Der Nutzer meldet sich mit Steam an.
2. Das Backend ruft `register` auf.
3. Der Nutzer gründet ein Team mit `teams` oder tritt einem bei mit `teams/{id}/join`. Teams mit freiem Platz sind die mit weniger als 2 Einträgen in `GET /tournament` → `teams[].steamids`.
4. `GET /tournament/player/{steamid}` zeigt dem Nutzer seinen Stand.

Den Spielplan erstellen und das Turnier starten macht die Turnierleitung im Spielservermanager.

### `GET /servers` – Server-Übersicht

`{"servers": [{"id", "name", "game", "online", "players", "max", "map", "address", "tv_address"}]}`

Die Adressen sind die öffentlichen.

---

## 3. Zuschauen und Stream

### `GET /stream`

```json
{"enabled": true, "on_air": true, "title": "GrohLAN Turnier – live",
 "match": "Die Lianen vs Jaguar · Halbfinale", "id": "m5", "tv": "192.168.200.27:27120",
 "hls": "https://…/stream/live/index.m3u8", "embed": "https://…/embed/stream"}
```

| Feld | Bedeutung |
|---|---|
| `on_air` | Es wird gerade gesendet. |
| `hls` | HLS-Adresse für eigene Player, z. B. hls.js oder Video.js. |
| `embed` | fertige Player-Seite, siehe unten |

### Seiten zum Einbetten (iframe)

Diese Seiten brauchen keinen Schlüssel und aktualisieren sich selbst.

```html
<!-- Turnierbaum im GrohLAN-Look: Live-Spiele, gespiegelter K.-o.-Baum mit Pokal, Gruppen -->
<iframe src="https://<tool-adresse>/embed/tournament" style="width:100%;height:900px;border:0"></iframe>

<!-- Live-Stream: zeigt "Gerade kein Live-Stream", wenn nichts läuft -->
<iframe src="https://<tool-adresse>/embed/stream" style="width:100%;aspect-ratio:16/9;border:0" allowfullscreen></iframe>
```

Wie der Stream entsteht: Ein Stream-PC hängt per CSTV am laufenden Spiel und folgt automatisch dem aktuellen Turnierspiel, die Kamera führt der Auto-Director. OBS sendet das Bild an den Stream-Server im Tool. Die Verzögerung beträgt etwa 35 Sekunden, das ist so gewollt und verhindert Ghosting.

**Stream zusätzlich auf Twitch oder YouTube:** Das geht über OBS auf dem Stream-PC, z. B. mit dem Plugin „Multiple RTMP Outputs“. Dann geht dasselbe Bild an den Stream-Server und parallel an Twitch oder YouTube. Auf der Homepage kann dann auch der Twitch-Player eingebettet werden.

---

## 4. Steam-Bot „GrohLan“

> Steam-Regel: Nachrichten gehen nur an **Freunde** des Bots. Wer noch kein Freund ist, bekommt zuerst eine Freundschaftsanfrage (`/bot/friend`) und muss sie annehmen. Spieler auf der LAN fragt der Bot automatisch an, wenn das im Tool eingeschaltet ist.

| Methode | Pfad | Body | Antwort |
|---|---|---|---|
| GET | `/bot` | – | `{"enabled", "state": "angemeldet", "steamid", "name", "can_invite", "friends": 42, "error"}` |
| GET | `/bot/friends` | – | `{"friends": [{"steamid", "name", "rel": "Friend", "online", "game"}]}` |
| POST | `/bot/friend` | `{"steamid": "7656…"}` | Freundschaftsanfrage gesendet |
| POST | `/bot/message` | `{"steamids": ["7656…"], "text": "Hallo!"}` | `{"sent": […], "failed": […], "not_friends": […]}` |
| POST | `/bot/invite` | siehe unten | wie `/bot/message` |

### `POST /bot/invite` – Einladung zu einem Spiel (z. B. Finalturnier)

```json
// auf einen unserer Server: jeder bekommt die passende Adresse (LAN/Internet) und einen klickbaren Beitritts-Link
{"steamids": ["7656…01", "7656…02"], "text": "🏆 Finale: Die Lianen vs Jaguar startet jetzt!", "server_id": "abc123"}

// auf einen fremden Server (z. B. Final-Server woanders): Adresse + optional Passwort
{"steamids": ["7656…01"], "text": "🏆 Finale startet jetzt!", "address": "203.0.113.5:27015", "password": "geheim"}
```

`server_id` steht in `GET /servers`. Der Bot schickt höchstens 2–3 Nachrichten pro Sekunde, damit Steam ihn nicht als Spam einstuft. Bei 100 Empfängern dauert der Aufruf also etwa 40 Sekunden.

---

## 5. Beispiele

```bash
KEY=gsm_xxxxxxxx
API=http://185.44.4.220:8090/api/v1

curl -s $API/tournament -H "X-API-Key: $KEY"
curl -s -X POST $API/tournament/register -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"steamid":"76561197960287930","name":"Anna"}'
curl -s -X POST $API/bot/message -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"steamids":["76561197960287930"],"text":"Dein Match beginnt in 10 Minuten!"}'
```

```php
<?php // PHP (Homepage-Backend)
function grohlan_api($method, $path, $body = null) {
  $ch = curl_init("http://185.44.4.220:8090/api/v1" . $path);
  curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_CUSTOMREQUEST => $method,
    CURLOPT_HTTPHEADER => ["X-API-Key: " . getenv("GROHLAN_API_KEY"), "Content-Type: application/json"],
    CURLOPT_POSTFIELDS => $body ? json_encode($body) : null, CURLOPT_TIMEOUT => 60]);
  $res = json_decode(curl_exec($ch), true);
  $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
  if ($code >= 400) throw new Exception($res["detail"] ?? "Fehler $code");
  return $res;
}
grohlan_api("POST", "/tournament/register", ["steamid" => $steamid, "name" => $nick]);
```

```js
// Node (Homepage-Backend)
const api = (path, body) => fetch("http://185.44.4.220:8090/api/v1" + path, {
  method: body ? "POST" : "GET",
  headers: {"X-API-Key": process.env.GROHLAN_API_KEY, "Content-Type": "application/json"},
  body: body ? JSON.stringify(body) : undefined,
}).then(async r => { const j = await r.json(); if (!r.ok) throw new Error(j.detail); return j; });
```

---

## 6. Betrieb

**HTTPS:** Eine https-Homepage darf keine http-Seiten einbetten, das blockiert der Browser als „Mixed Content“. Auch der API-Schlüssel sollte nicht unverschlüsselt durchs Internet gehen. Empfehlung: einen Reverse-Proxy mit Let's-Encrypt-Zertifikat vor das Tool setzen, z. B. Nginx Proxy Manager oder Caddy, mit einer Subdomain wie `live.groh-lan.de` auf Port 8090. Dann lauten die Adressen `https://live.groh-lan.de/api/v1` und `https://live.groh-lan.de/embed/…`.

**Schlüssel tauschen:** Unter 🔌 API einen neuen Schlüssel erzeugen und in der Homepage eintragen, dann den alten löschen.
