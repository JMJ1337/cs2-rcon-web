# Spielservermanager – Homepage-API

Mit dieser API kann eure Homepage folgende Dinge nutzen:

- **Turnier:** Status, Spielplan, Ergebnisse und Live-Spielstände lesen. Spieler an- und abmelden, Teams gründen, beitreten und verlassen.
- **Turniere anlegen:** neues Turnier mit Name, Modus, Startzeit, Maps; Anmeldung öffnen und schließen.
- **Benutzerkonten:** Nutzer der Homepage im Spielservermanager anlegen und aktuell halten – sie sehen zunächst nur die öffentliche Seite.
- **Zuschauen:** Live-Stream und CSTV-Adressen der laufenden Spiele abrufen, außerdem fertige Seiten zum Einbetten (iframe).
- **Steam-Bot:** Nachrichten, Einladungen zu Spielen und Freundschaftsanfragen, z. B. für das Finalturnier.

---

## 1. Zugang

| | |
|---|---|
| **Basis-URL** | `https://<tool-adresse>/api/v1`, z. B. `https://live.example.org/api/v1`. Von außen über HTTPS (Cloudflare-Tunnel), siehe Abschnitt 7. |
| **Schlüssel** | Wird im Spielservermanager unter **🔌 API** erzeugt und nur einmal angezeigt. |
| **Header** | `X-API-Key: gsm_…`, alternativ `Authorization: Bearer gsm_…` |
| **Format** | JSON hin und zurück (`Content-Type: application/json`) |

Jeder Schlüssel hat eines oder mehrere Rechte:

| Recht | erlaubt |
|---|---|
| `tournament` | Turnier lesen, Spieler an- und abmelden, Teams verwalten, Serverliste lesen |
| `organize` | Turniere anlegen und einstellen (Name, Modus, Start, Maps, Anmeldung) |
| `users` | Benutzerkonten anlegen, aktualisieren, abfragen und löschen |
| `stream` | Stream-Status lesen |
| `bot` | Steam-Bot: Status, Freunde, Freundschaftsanfrage, Nachricht, Einladung |

> **Wichtig:** Den Schlüssel nur **serverseitig** benutzen, also im PHP- oder Node-Backend der Homepage, und nie im Browser-JavaScript.
> Wer den Schlüssel hat, kann in fremdem Namen Spieler anmelden und über den Bot schreiben.

**Ohne Schlüssel lesbar:** Ist unter 🔌 API die Option „ohne Schlüssel lesbar“ an, gehen `GET /tournament`, `GET /tournament/player/{steamid}`, `GET /servers` und `GET /stream` auch ohne Schlüssel. Damit kann der Browser diese Daten direkt abrufen. Erlaubte Homepage-Adressen für den Browserzugriff (CORS) werden dort ebenfalls eingetragen. Standard: `https://www.example.org` und `https://example.org`.

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
  "active": true, "name": "LAN Wingman-Turnier", "mode": "groups", "mode_label": "Gruppen + K.-o.",
  "status": "setup | waiting | running | done", "registration": true, "start": 1792500000,
  "teams":   [{"id": "t1a2b3", "name": "Die Lianen", "players": ["Anna", "Ben"], "steamids": ["7656…01", "7656…02"]}],
  "players": [{"steamid": "7656…01", "name": "Anna", "avatar": "https://…", "team": "t1a2b3"}],
  "matches": [{
      "id": "m5", "no": 5, "stage": "K", "round": 4, "label": "K.-o. · Halbfinale",
      "t1": "Die Lianen", "t2": "Jaguar", "p1": null, "p2": "Sieger #3",
      "s1": 7, "s2": 4, "status": "wait | ready | live | done", "winner": null, "walkover": false,
      "planned": 1792503600, "started": null, "map": "de_inferno", "server_name": "LAN CS #2",
      "tv_url": "steam://run/730//+connect%20203.0.113.10:27120", "tv_address": "203.0.113.10:27120"
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
                "opponent": "Jaguar", "server": "LAN CS #2",
                "join": "Verbinden: 192.168.1.10:27115\nKlick zum Beitreten: http://192.168.1.10:8090/j/abc123"}}
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

### `GET /deathmatch` – Deathmatch-Bestenliste (CS #1)

`{"day": [...], "total": [...]}` – je Spieler `steamid, name, kills, deaths, kd, hs_pct, last`. „day“ zählt ab 6 Uhr morgens (LAN-Nächte gehören zum Vortag). Sortiert nach Kills.

### Spielerbewertung im Turnier (`leaders` in `GET /tournament`)

Je Spieler: `rating` (angelehnt an HLTV Rating 3.0, 1,00 = Durchschnitt), `kd`, `kills`, `deaths`, `adr`, `kast_pct`, `hs_pct`, `wins`, `matches`. Die genaue HLTV-Formel ist nicht öffentlich – nachgebildet aus MatchZy-Werten: Rundeneinfluss (Eröffnungs-Kills, Trades, Clutches, Flash-Assists) 33 %, Kills 25 %, Schaden 15 %, Überleben 10 %, KAST 10 %, Multi-Kills 7 %.

### `GET /servers` – Server-Übersicht

`{"servers": [{"id", "name", "game", "online", "players", "max", "map", "address", "tv_address"}]}`

Die Adressen sind die öffentlichen.

---

### Turnier von der Homepage übernehmen (Recht `organize`) – empfohlener Weg

Die Homepage erstellt das Turnier samt Anmeldung und Teams selbst und **schiebt es fertig zu uns**. Gespielt
(Server, MatchZy, Ergebnisse) wird im Spielservermanager; die Homepage holt die Ergebnisse mit
`GET /tournament/results` ab und stellt sie selbst dar.

`PUT /tournament/import`

```json
{
  "external_id": "wintercup-2026",          // Turnier-ID der Homepage (Pflicht)
  "name": "Winter-Cup 2026", "mode": "groups", "start": 1795000000,
  "maps": ["de_inferno", "de_nuke"], "match_min": 35, "pause_min": 10,
  "seeding": "random",                       // random = zufällig gesetzt, given = Reihenfolge der Teams ist die Setzliste
  "generate": true,                          // Spielplan sofort erzeugen
  "teams": [
    {"external_id": "t17", "name": "Die Lianen",
     "players": [{"steamid": "76561197960287930", "name": "Anna", "avatar": "https://…"},
                 {"steamid": "76561197960287931", "name": "Ben"}]}
  ]
}
```

- Neue `external_id`: das bisherige Turnier wandert ins Archiv, das neue wird angelegt.
- Gleiche `external_id`: Teams und Einstellungen werden **ersetzt** (z. B. nach Nachmeldungen) – aber nur, solange
  noch kein Spiel lief. Danach `409`.
- `409` auch, solange ein Turnier im Spielservermanager läuft.
- Die Anmeldung im Spielservermanager bleibt geschlossen (die macht die Homepage).
- Teamnamen bis 24 Zeichen und eindeutig, jeder Spieler nur in einem Team, bis 10 Spieler pro Team, bis 128 Teams.
- Antwort: `{"ok": true, "teams": 8, "matches": 13, "servers_needed": 4, "team_ids": {"t17": "t8fa826", …}}`

Den Start des Turniers (Server bereitstellen, „Turnier starten“) macht die Turnierleitung im Spielservermanager.

### Ergebnisse abrufen: `GET /tournament/results`

Alles für die eigene Grafik der Homepage, Teams immer mit eurer `external_id`:

```json
{"external_id": "wintercup-2026", "name": "Winter-Cup 2026", "mode": "groups", "status": "running", "updated": 1795003600,
 "teams": [{"id": "t8fa826", "external_id": "t17", "name": "Die Lianen", "players": ["7656…30", "7656…31"]}],
 "matches": [{"id": "m5", "no": 5, "stage": "K", "round": 4, "label": "K.-o. · Halbfinale", "group": null,
              "team1": {"id": "t8fa826", "external_id": "t17", "name": "Die Lianen"}, "team2": null,
              "placeholder1": null, "placeholder2": "Sieger #3",
              "score1": 7, "score2": 4, "status": "live", "winner": null, "walkover": false,
              "map": "de_inferno", "planned": 1795003000, "started": 1795003100, "ended": null,
              "server": "LAN CS #2", "tv_url": "steam://…", "stats": [{"side": "1", "steamid": "…", "name": "Anna", "kills": 12, …}]}],
 "groups": {"A": [{"team": {"external_id": "t17", …}, "played": 2, "won": 2, "lost": 0, "rf": 26, "ra": 14}]},
 "leaders": [{"steamid": "…", "name": "Anna", "rating": 1.21, "kd": 1.4, "adr": 88, …}],
 "champion": null}
```

| Feld | Bedeutung |
|---|---|
| `stage` | `G` Gruppe, `K`/`W` K.-o. bzw. Winner-Bracket, `L` Loser-Bracket, `F` großes Finale, `R` Jeder-gegen-jeden |
| `status` | `wait` (Gegner offen), `ready`, `live` (Stand in `score1`/`score2` live), `done` |
| `team2.bye` | `true` = Freilos |
| `placeholder1/2` | solange ein Gegner noch offen ist, z. B. „Sieger #3“ |
| `champion` | Turniersieger, sobald `status = done` |

Empfehlung: alle 15–30 s abrufen (während `live`), sonst seltener.

### Turnier direkt im Spielservermanager anlegen und einstellen (Recht `organize`)

Nur nötig, wenn die Homepage **keine** eigenen Teams schickt (Anmeldung dann über unsere Endpunkte oben).

| Methode | Pfad | Body | Ergebnis |
|---|---|---|---|
| GET | `/tournament/options` | – | `{"modes": {"ko": "K.-o.-System", "double": "Doppel-K.-o.", "groups": "Gruppen + K.-o.", "rr": "Jeder gegen jeden"}, "maps_default": [...], "templates": [{"id", "name"}]}` |
| POST | `/tournament/new` | siehe unten | neues Turnier; das bisherige wird im Archiv gespeichert. `409`, solange ein Turnier läuft. |
| PUT | `/tournament` | dieselben Felder, alle optional | Einstellungen des aktuellen Turniers ändern, z. B. `{"registration": false}` |

```json
{"name": "Winter-Cup 2026", "mode": "groups", "start": 1795000000, "registration": true,
 "maps": ["de_inferno", "de_nuke"], "match_min": 35, "pause_min": 10, "template": null}
```

| Feld | Bedeutung |
|---|---|
| `name` | bis 60 Zeichen |
| `mode` | `ko`, `double`, `groups` oder `rr` |
| `start` | geplanter Start (Unix-Sekunden) |
| `registration` | Anmeldung offen (`true`) oder geschlossen |
| `maps` | Map-Pool, bis 20 Maps |
| `match_min` / `pause_min` | geplante Spieldauer und Pause in Minuten (für den Zeitplan) |
| `template` | optional: ID einer im Spielservermanager gespeicherten Vorlage (nur bei `/tournament/new`) |

Spielplan erstellen und Turnier starten macht weiterhin die Turnierleitung im Spielservermanager.

---

## 3. Benutzerkonten (Recht `users`)

Die Homepage schickt ihre Nutzer an den Spielservermanager. **Neue Konten sehen nur die öffentliche Seite** (Profil
„Nur öffentliche Seite“). Rechte, Profile und Rolle vergebt ihr danach im Spielservermanager unter *Benutzer* –
die API ändert diese bei bestehenden Konten **nie**. Konten von der Homepage tragen dort das Zeichen 🌐 Homepage.

### Datensatz

| Feld | Pflicht | Inhalt |
|---|---|---|
| `external_id` | ja | eindeutige Nutzer-ID auf der Homepage (Buchstaben, Ziffern, `. _ - @ : +`, bis 64 Zeichen) |
| `username` | nein | gewünschter Benutzername; ist er vergeben oder ungültig, wird er automatisch angepasst (Umlaute → ae/oe/ue) |
| `nick` | nein | Anzeigename, bis 64 Zeichen |
| `email` | nein | E-Mail-Adresse |
| `steamid` | nein | SteamID64 (17 Ziffern) – dann klappt „Mit Steam anmelden“, Spieler und Avatar werden verknüpft |
| `avatar` | nein | Bild-Adresse, nur `https://` |
| `password` | nein | mind. 8 Zeichen – Login mit Benutzername + Passwort (wird nur gehasht gespeichert) |
| `note` | nein | Notiz, bis 80 Zeichen |

```json
{"external_id": "17", "username": "anna", "nick": "Anna B.", "email": "anna@example.org",
 "steamid": "76561197960287930", "avatar": "https://example.org/anna.png", "password": "mindestens8"}
```

Weggelassene Felder bleiben unverändert, ein leerer Text `""` löscht `nick`, `email` bzw. `note`.

**Zuordnung und Grenzen:**

- Das Konto wird über `external_id` gefunden. Gibt es sie noch nicht, entsteht ein neues Konto.
- Die API ändert und löscht **nur Konten, die sie selbst angelegt hat** (🌐 Homepage). Konten aus der Steam-Registrierung
  oder von Hand angelegte Konten sind tabu (`403`), ebenso Administrator-Konten.
- Gehört die SteamID schon zu einem anderen Konto im Spielservermanager, kommt `409` – das Konto dann ohne `steamid`
  schicken oder den Admin bitten, die Konten zusammenzuführen.

### Endpunkte

| Methode | Pfad | Body | Antwort |
|---|---|---|---|
| POST | `/users` | Datensatz | Konto (siehe unten), `"created": true` bei neuem Konto |
| POST | `/users/bulk` | `{"users": [Datensatz, …]}` (max. 500) | `{"results": [...], "created": 3, "failed": 0}` – je Eintrag `"ok": true` + Konto oder `"ok": false` + `error` |
| GET | `/users/{external_id}` | – | Konto oder `404` |
| DELETE | `/users/{external_id}` | – | Konto gelöscht – nur selbst angelegte, keine Administratoren (`403`) |

```json
{"external_id": "17", "username": "anna", "nick": "Anna B.", "email": "anna@example.org", "steamid": "76561197960287930",
 "public_only": true, "profiles": ["oeffentlich"], "role": "user", "created_at": 1792872284, "last_login": null, "created": true}
```

`public_only` wird `false`, sobald ihr dem Konto im Spielservermanager Rechte gebt. `409` kommt, wenn die SteamID schon zu
einem anderen Konto gehört.

**Anmeldung der Nutzer im Spielservermanager:** „Mit Steam anmelden“ (wenn `steamid` gesetzt ist) oder Benutzername +
Passwort (wenn `password` mitgeschickt wurde).

**Empfehlung:** bei Registrierung und Profiländerung auf der Homepage `POST /users` aufrufen, beim Löschen des
Homepage-Kontos `DELETE /users/{id}`, und einmalig alle bestehenden Nutzer per `/users/bulk` übertragen.

---

## 4. Zuschauen und Stream

### `GET /stream`

```json
{"enabled": true, "on_air": true, "title": "LAN Turnier – live",
 "match": "Die Lianen vs Jaguar · Halbfinale", "id": "m5", "tv": "192.168.1.10:27120",
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
<!-- Turnierbaum : Live-Spiele, gespiegelter K.-o.-Baum mit Pokal, Gruppen -->
<iframe src="https://<tool-adresse>/embed/tournament" style="width:100%;height:900px;border:0"></iframe>

<!-- Live-Stream: zeigt "Gerade kein Live-Stream", wenn nichts läuft -->
<iframe src="https://<tool-adresse>/embed/stream" style="width:100%;aspect-ratio:16/9;border:0" allowfullscreen></iframe>
```

Wie der Stream entsteht: Ein Stream-PC hängt per CSTV am laufenden Spiel und folgt automatisch dem aktuellen Turnierspiel, die Kamera führt der Auto-Director. OBS sendet das Bild an den Stream-Server im Tool. Die Verzögerung beträgt etwa 35 Sekunden, das ist so gewollt und verhindert Ghosting.

**Stream zusätzlich auf Twitch oder YouTube:** Das geht über OBS auf dem Stream-PC, z. B. mit dem Plugin „Multiple RTMP Outputs“. Dann geht dasselbe Bild an den Stream-Server und parallel an Twitch oder YouTube. Auf der Homepage kann dann auch der Twitch-Player eingebettet werden.

---

## 5. Steam-Bot

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

## 6. Beispiele

```bash
KEY=gsm_xxxxxxxx
API=https://live.example.org/api/v1

curl -s $API/tournament -H "X-API-Key: $KEY"
curl -s -X POST $API/tournament/register -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"steamid":"76561197960287930","name":"Anna"}'
curl -s -X POST $API/users -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"external_id":"17","nick":"Anna","email":"anna@example.org","steamid":"76561197960287930"}'
curl -s -X POST $API/tournament/new -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"name":"Winter-Cup 2026","mode":"groups","registration":true}'
curl -s -X POST $API/bot/message -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"steamids":["76561197960287930"],"text":"Dein Match beginnt in 10 Minuten!"}'
```

```php
<?php // PHP (Homepage-Backend)
function lan_api($method, $path, $body = null) {
  $ch = curl_init("https://live.example.org/api/v1" . $path);
  curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_CUSTOMREQUEST => $method,
    CURLOPT_HTTPHEADER => ["X-API-Key: " . getenv("GSM_API_KEY"), "Content-Type: application/json"],
    CURLOPT_POSTFIELDS => $body ? json_encode($body) : null, CURLOPT_TIMEOUT => 60]);
  $res = json_decode(curl_exec($ch), true);
  $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
  if ($code >= 400) throw new Exception($res["detail"] ?? "Fehler $code");
  return $res;
}
lan_api("POST", "/tournament/register", ["steamid" => $steamid, "name" => $nick]);
```

```js
// Node (Homepage-Backend)
const api = (path, body) => fetch("https://live.example.org/api/v1" + path, {
  method: body ? "POST" : "GET",
  headers: {"X-API-Key": process.env.GSM_API_KEY, "Content-Type": "application/json"},
  body: body ? JSON.stringify(body) : undefined,
}).then(async r => { const j = await r.json(); if (!r.ok) throw new Error(j.detail); return j; });
```

---

## 7. Betrieb

**HTTPS:** Eine https-Homepage darf keine http-Seiten einbetten („Mixed Content“), und der API-Schlüssel sollte nicht unverschlüsselt durchs Internet gehen. Empfehlung: Cloudflare-Tunnel – Anleitung in [`CLOUDFLARE.md`](CLOUDFLARE.md). Dann lauten die Adressen z. B. `https://live.example.org/api/v1` und `https://live.example.org/embed/…`.

**Schlüssel tauschen:** Unter 🔌 API einen neuen Schlüssel erzeugen und in der Homepage eintragen, dann den alten löschen.
