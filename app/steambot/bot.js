// Steam-Bot für die LAN: Freundschaftsanfragen und Nachrichten – gesteuert vom Spielservermanager über HTTP.
// Läuft in einem eigenen Container (node), meldet sich mit einem eigenen Steam-Konto an.
// Das Passwort wird nie gespeichert: nach der ersten Anmeldung merkt sich der Bot nur das Anmelde-Token (refresh token).
const http = require("http");
const fs = require("fs");
const SteamUser = require("steam-user");

const KEY = process.env.BOT_KEY || "";
const PORT = 8091;
const DATA = process.env.BOT_DATA || "/data";
const TOKEN_FILE = DATA + "/refresh_token";
const NAME = process.env.BOT_NAME || "";

const st = {state: "aus", steamid: null, name: null, error: null, need_code: null, last_code_wrong: false,
            limited: null, can_invite: null, account: null, messages: []};
let guardCb = null;

const client = new SteamUser({autoRelogin: true, dataDirectory: DATA + "/steam", renewRefreshTokens: true});

function remember(m) { st.messages.push(m); if (st.messages.length > 100) st.messages.shift(); }

client.on("loggedOn", () => {
  st.state = "angemeldet"; st.error = null; st.need_code = null;
  st.steamid = client.steamID.getSteamID64();
  client.setPersona(SteamUser.EPersonaState.Online, NAME || undefined);
});
client.on("accountInfo", (name) => { st.name = name; });
client.on("refreshToken", (t) => { try { fs.writeFileSync(TOKEN_FILE, t, {mode: 0o600}); } catch (e) {} });
client.on("accountLimitations", (limited, banned, locked, canInvite) => { st.limited = limited; st.can_invite = canInvite; });
client.on("steamGuard", (domain, cb, lastWrong) => {
  guardCb = cb; st.state = "wartet auf Code"; st.need_code = domain ? "email" : "app"; st.last_code_wrong = !!lastWrong;
});
client.on("error", (e) => {
  st.state = "Fehler"; st.error = String(e && e.message || e);
  if (/InvalidPassword|AccessDenied|Expired|Revoked/i.test(st.error)) { try { fs.unlinkSync(TOKEN_FILE); } catch (x) {} }
});
client.on("disconnected", (eresult, msg) => { if (st.state === "angemeldet") st.state = "getrennt – verbindet neu"; });
client.on("friendMessage", (sid, text) => remember({t: Date.now() / 1000, from: sid.getSteamID64(), text, dir: "in"}));
client.on("friendRelationship", () => {});

function login(body) {
  if (body && body.user && body.pass) {
    st.account = body.user; st.state = "meldet an …";
    client.logOn({accountName: body.user, password: body.pass});
    return;
  }
  try {
    const t = fs.readFileSync(TOKEN_FILE, "utf8").trim();
    if (t) { st.state = "meldet an …"; client.logOn({refreshToken: t}); return; }
  } catch (e) {}
  st.state = "nicht angemeldet";
}

function friends() {
  const out = [];
  for (const [sid, rel] of Object.entries(client.myFriends || {})) {
    const p = (client.users || {})[sid] || {};
    out.push({steamid: sid, rel: SteamUser.EFriendRelationship[rel] || String(rel), name: p.player_name || null,
              online: p.persona_state != null ? p.persona_state !== 0 : null, game: p.game_name || null});
  }
  return out;
}

function send(res, code, obj) { res.writeHead(code, {"Content-Type": "application/json"}); res.end(JSON.stringify(obj)); }

http.createServer((req, res) => {
  if (KEY && req.headers["x-bot-key"] !== KEY) return send(res, 403, {error: "forbidden"});
  let raw = "";
  req.on("data", (c) => { raw += c; if (raw.length > 100000) req.destroy(); });
  req.on("end", async () => {
    let body = {};
    try { body = raw ? JSON.parse(raw) : {}; } catch (e) { return send(res, 400, {error: "json"}); }
    try {
      if (req.method === "GET" && req.url === "/status") return send(res, 200, {...st, friends: friends()});
      if (req.method === "POST" && req.url === "/login") { login(body); return send(res, 200, {ok: true}); }
      if (req.method === "POST" && req.url === "/code") {
        if (!guardCb) return send(res, 400, {error: "Kein Code angefordert"});
        const cb = guardCb; guardCb = null; st.need_code = null; st.state = "meldet an …"; cb(String(body.code || "").trim());
        return send(res, 200, {ok: true});
      }
      if (req.method === "POST" && req.url === "/logout") {
        try { fs.unlinkSync(TOKEN_FILE); } catch (e) {}
        client.logOff(); st.state = "nicht angemeldet"; st.steamid = null; return send(res, 200, {ok: true});
      }
      if (st.state !== "angemeldet") return send(res, 409, {error: "Bot ist nicht angemeldet"});
      if (req.method === "POST" && req.url === "/add") {
        const r = await new Promise((ok) => client.addFriend(String(body.steamid), (err, name) => ok(err ? {error: String(err.message || err)} : {ok: true, name})));
        return send(res, r.error ? 502 : 200, r);
      }
      if (req.method === "POST" && req.url === "/msg") {
        const done = [], failed = [];
        for (const sid of body.steamids || []) {
          try { await client.chat.sendFriendMessage(String(sid), String(body.text || "").slice(0, 2000)); done.push(sid);
                remember({t: Date.now() / 1000, to: String(sid), text: String(body.text || ""), dir: "out"}); }
          catch (e) { failed.push({steamid: sid, error: String(e.message || e)}); }
          await new Promise((r) => setTimeout(r, 400));          // nicht als Spam auffallen
        }
        return send(res, 200, {done, failed});
      }
      if (req.method === "POST" && req.url === "/personas") {
        const ids = (body.steamids || []).map(String).slice(0, 100);
        const r = ids.length ? await client.getPersonas(ids) : {personas: {}};
        const out = {};
        for (const [k, v] of Object.entries(r.personas || {})) out[k] = {name: v.player_name, online: v.persona_state !== 0};
        return send(res, 200, out);
      }
      send(res, 404, {error: "unbekannt"});
    } catch (e) { send(res, 500, {error: String(e.message || e)}); }
  });
}).listen(PORT, () => { console.log("Steam-Bot bereit auf Port " + PORT); login(null); });
