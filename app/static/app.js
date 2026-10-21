"use strict";
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

const MAPS = ["de_dust2","de_mirage","de_inferno","de_nuke","de_ancient","de_anubis","de_train",
  "de_overpass","de_vertigo","de_whistle","cs_office","cs_italy","ar_baggage","ar_shoots","ar_pool_day"];

const QUICK = [
  ["Warmup beenden","mp_warmup_end","primary"], ["Warmup starten","mp_warmup_start"],
  ["Restart","mp_restartgame 1"], ["Pause","mp_pause_match"], ["Fortsetzen","mp_unpause_match"],
  ["Teams tauschen","mp_swapteams"], ["Teams mischen","mp_scrambleteams"],
  ["Bot T +","bot_add_t"], ["Bot CT +","bot_add_ct"], ["Bots kicken","bot_kick","danger"],
];

const MZ_ACTIONS = [
  ["Force-Start","css_start","primary"], ["Match neu starten","css_restart"],
  ["Pause erzwingen","css_forcepause"], ["Pause beenden","css_forceunpause"],
  ["Messerrunde","css_roundknife"], ["Match abbrechen","get5_endmatch","danger"],
  ["Match-Config neu laden","exec MatchZy/config.cfg"],
];

const SETTINGS = [
  ["Allgemein", [
    ["hostname","Servername","text"], ["sv_password","Server-Passwort","text"],
    ["sv_visiblemaxplayers","Sichtbare Slots (-1 = alle)","number"],
    ["sv_cheats","Cheats","bool"], ["sv_alltalk","Alltalk","bool"],
    ["sv_deadtalk","Tote können mit Lebenden reden","bool"], ["sv_full_alltalk","Voller Alltalk (inkl. Gegner)","bool"],
  ]],
  ["Match", [
    ["mp_maxrounds","Max. Runden","number"], ["mp_roundtime","Rundenzeit (Min.)","number"],
    ["mp_roundtime_defuse","Rundenzeit Defuse (Min.)","number"], ["mp_freezetime","Freezetime (Sek.)","number"],
    ["mp_buytime","Kaufzeit (Sek.)","number"], ["mp_c4timer","C4-Timer (Sek.)","number"],
    ["mp_warmuptime","Warmup-Zeit (Sek.)","number"], ["mp_halftime","Halbzeit","bool"],
    ["mp_match_can_clinch","Vorzeitiger Sieg möglich","bool"], ["mp_overtime_enable","Overtime","bool"],
    ["mp_overtime_maxrounds","Overtime-Runden","number"], ["mp_overtime_startmoney","Overtime-Startgeld","number"],
  ]],
  ["Wirtschaft", [
    ["mp_startmoney","Startgeld","number"], ["mp_maxmoney","Max. Geld","number"],
    ["mp_afterroundmoney","Geld nach jeder Runde","number"], ["mp_buy_anywhere","Überall kaufen","bool"],
    ["mp_free_armor","Gratis-Rüstung","select",[["0","Keine"],["1","Weste"],["2","Weste + Helm"]]],
  ]],
  ["Teams", [
    ["mp_friendlyfire","Friendly Fire","bool"], ["mp_autoteambalance","Auto-Teamausgleich","bool"],
    ["mp_limitteams","Max. Team-Unterschied (0 = aus)","number"], ["mp_autokick","Auto-Kick (Idle/TK)","bool"],
    ["mp_solid_teammates","Mitspieler solide","select",[["0","Nein"],["1","Ja"],["2","Nur bei Bewegung"]]],
    ["mp_teammates_are_enemies","Jeder gegen jeden","bool"],
  ]],
  ["Bots", [
    ["bot_quota","Anzahl Bots","number"],
    ["bot_quota_mode","Bot-Modus","select",[["normal","normal"],["fill","fill"],["competitive","competitive"]]],
    ["bot_difficulty","Schwierigkeit","select",[["0","Leicht"],["1","Normal"],["2","Schwer"],["3","Experte"]]],
    ["bot_join_after_player","Bots erst nach Spieler","bool"],
  ]],
  ["MatchZy", [
    ["matchzy_kick_when_no_match_loaded","Kicken, wenn kein Match geladen","bool"],
    ["matchzy_minimum_ready_required","Spieler nötig für Start (.ready)","number"],
    ["matchzy_knife_enabled_default","Messerrunde standardmäßig","bool"],
    ["matchzy_autostart_mode","Autostart-Modus","select",[["0","Aus"],["1","Ready-System"],["2","Warmup"]]],
  ]],
];

let servers = [], current = null, tab = "overview", view = "dash";
let GAMES = {}, dockerOn = false, me = null, ctTimer = null;
const gameOf = s => (s && GAMES[s.game] ? s.game : "cs2");
// Eigene, schlichte Symbole je Spiel (keine offiziellen Logos)
const ICONS = {
  cs2: '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2v5M12 17v5M2 12h5M17 12h5"/>',
  factorio: '<circle cx="12" cy="12" r="3.5"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/><circle cx="12" cy="12" r="6.5"/>',
  satisfactory: '<path d="M3 21V11l5 3v-3l5 3V8h3V4h3v17z"/><path d="M3 21h18"/>',
  valheim: '<path d="M6 21L17 6"/><path d="M14 3c3 0 6 3 6 6-2 0-3-1-4.5-2.5S14 5 14 3z"/>',
  cache: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  wreckfest: '<path d="M3 15l2-5c.4-1 1.2-1.5 2.2-1.5h6.3c.9 0 1.7.4 2.2 1.1L18 12l2.5.8c.8.3 1.5 1 1.5 1.9V15"/><path d="M2 15h20v2H2z"/><circle cx="7" cy="17.5" r="2"/><circle cx="17" cy="17.5" r="2"/><path d="M9 5l1.5 2M14 4l-1 3"/>',
  prefill: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 19h16"/>',
  minecraft: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
  teamspeak: '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="13" width="4" height="7" rx="1.5"/><rect x="17" y="13" width="4" height="7" rx="1.5"/>',
  tf2: '<circle cx="12" cy="12" r="8.5"/><path d="M8 8.5h8M12 8.5V17"/><path d="M9.5 13h4"/>',
  _: '<rect x="3" y="7" width="18" height="10" rx="4"/><path d="M8 10v4M6 12h4"/><circle cx="16" cy="11" r="1"/><circle cx="18" cy="13" r="1"/>',
};
const gicon = (g, size=16) => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[g] || ICONS._}</svg>`;
// Originalbilder der Spiele (live von Steam geladen; offline -> eigenes Symbol)
const STEAM_APPS = {tf2: 440, cs2: 730, factorio: 427520, satisfactory: 526870, valheim: 892970, wreckfest: 228380};
const appOf = g => STEAM_APPS[g] || (GAMES[g] && GAMES[g].appid) || null;
const steamImg = (g, file) => appOf(g) ? `https://cdn.cloudflare.steamstatic.com/steam/apps/${appOf(g)}/${file}` : "";
var ICONS_URL = {apps: {}, games: {}};
const OTHER_LOGOS = {minecraft: "/api/logo/minecraft", teamspeak: "/api/logo/teamspeak"};
function gameLogo(g){
  const src = steamImg(g, "capsule_sm_120.jpg") || OTHER_LOGOS[g] || "";
  return src ? `<span class="glogo"><img src="${src}" alt="${esc(GAMES[g]?.label || g)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.classList.add('fail')">${gbadge(g)}</span>` : gbadge(g);
}
// Map-Vorschaubilder: CS2 aus cs2-map-icons, Source-Spiele über GameTracker (fehlt ein Bild -> Spielbild)
const GT_MAPS = {tf2: "tf2", garrysmod: "garrysmod", l4d2: "left4dead2", quakelive: "ql", insurgency: "ins",
  cs16: "cs", czero: "czero", dod: "dod", dods: "dods", tfc: "tfc", hldm: "hl", hl2dm: "hl2dm", l4d: "l4d"};
const MAP_GAMES = new Set(["cs2", "wreckfest", "killingfloor2", ...Object.keys(GT_MAPS), "nmrih", "zps", "fof", "pvkii", "svencoop", "asrd"]);
function mapThumb(o, g){
  let src = o.map_image || "", title = o.map_title || o.track_name || o.map || "";
  if (!src && GT_MAPS[g] && o.map && o.map !== "–"){
    const base = String(o.map).split("/").pop().replace(/\.(bsp|vpk)$/, "").toLowerCase();
    if (/^[a-z0-9_\-]+$/.test(base)) src = `https://image.gametracker.com/images/maps/160x120/${GT_MAPS[g]}/${base}.jpg`;
    title = o.map;
  }
  if (g === "cs2" && !src){
    if (o.workshop && o.workshop.preview) { src = o.workshop.preview; title = o.workshop.title; }
    else if (o.map) {
      const base = String(o.map).split("/").pop().replace(/\.vpk$/, "").toLowerCase();
      if (/^[a-z0-9_]+$/.test(base)) src = `https://raw.githubusercontent.com/MurkyYT/cs2-map-icons/main/images/thumbs/${base}_1_png.png`;
      title = o.map;
    }
  }
  if (g === "teamspeak" && !src)    // kein Spielbild: eigenes Motiv mit dem TeamSpeak-Logo
    return `<div class="mthumb tsart" title="TeamSpeak"><img src="/api/logo/teamspeak" alt="" onerror="this.remove()"><span>Voice-Chat</span></div>`;
  // ohne Map: großes Steam-Titelbild (Landschaft), sonst Kopfbild
  const hero = steamImg(g, "library_hero.jpg"), fallback = steamImg(g, "header.jpg");
  if (!src) src = hero || fallback;
  if (!src) return "";
  const lay = o.map_layout ? `<img class="mlayout" src="${esc(o.map_layout)}" alt="" loading="lazy" referrerpolicy="no-referrer" title="Streckenverlauf" onerror="this.remove()">` : "";
  return `<div class="mthumb" title="${esc(title || GAMES[g]?.label || "")}"><img src="${esc(src)}" alt="" loading="lazy" referrerpolicy="no-referrer"
    onerror="if(this.dataset.fb!=='1'&&'${fallback}'){this.dataset.fb='1';this.src='${fallback}'}else{(this.closest('.pubthumb')||this.parentNode).remove()}">${lay}</div>`;
}
// echtes Spiel-Icon (Steam bzw. Favicon) in der Kachel, eigenes Symbol nur als Ersatz
function gameTile(g, size = 16){
  const src = (ICONS_URL.games || {})[g] || OTHER_LOGOS[g] || "";
  const svg = gicon(g, size);
  if (!src) return `<span class="gtile" style="background:${GAMES[g]?.color || "#888"}">${svg}</span>`;
  return `<span class="gtile gimg" style="background:${GAMES[g]?.color || "#888"}"><img src="${src}" alt="" referrerpolicy="no-referrer" onerror="this.parentNode.classList.remove('gimg');this.remove()">${svg}</span>`;
}
const gbadge = g => GAMES[g] ? `<span class="gbadge" style="background:${GAMES[g].color}">${gicon(g, 12)} ${esc(GAMES[g].short)}</span>` : "";
const collapsed = (() => { try { return JSON.parse(localStorage.getItem("gsmCollapsed") || "{}"); } catch { return {}; } })();
let pollTimer = null, dashTimer = null;
let settings = {modes: [], map_rules: []}, presets = {}, players = [], favs = [];
let loadedSettings = {};
let lastStatus = null;
const cmdHistory = (() => { try { return JSON.parse(sessionStorage.getItem("cmdHistory") || "[]"); } catch { return []; } })();
let histIdx = -1;

function toast(msg, err=false){
  const el = document.createElement("div");
  el.className = "toast" + (err ? " err" : "");
  el.textContent = msg;
  $("#toast").appendChild(el);
  setTimeout(() => el.remove(), err ? 7000 : 3000);
}

async function api(path, opts={}){
  const res = await fetch(path, {
    method: opts.method || (opts.body ? "POST" : "GET"),
    headers: opts.body ? {"Content-Type":"application/json"} : {},
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    credentials: "same-origin",
  });
  if (res.status === 401 && path !== "/api/login"){
    // nur aus der laufenden App zur öffentlichen Liste wechseln – nie das offene Login-Fenster schließen
    if (!$("#app").classList.contains("hidden")) showPublic();
    throw new Error("Nicht angemeldet");
  }
  let data = null;
  try { data = await res.json(); } catch {}
  if (!res.ok){
    const d = data && data.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join(", ") : res.statusText);
  }
  return data;
}

function modeOptions(withKeep){
  return (withKeep ? `<option value="">– Modus beibehalten –</option>` : "") +
    settings.modes.map(m => `<option value="${esc(m.key)}">${esc(m.label)} · ${m.players} Spieler</option>`).join("");
}
const fmtDate = t => new Date(t*1000).toLocaleString("de-DE", {day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});

/* ================= Login ================= */
function showLogin(){ stopPoll(); clearInterval(dashTimer); clearInterval(pubTimer); $("#app").classList.add("hidden"); $("#pub").classList.add("hidden"); $("#login").classList.remove("hidden"); $("#loginPw").focus(); }

/* ================= Öffentliche Serverliste (ohne Login) ================= */
let pubTimer = null, pubData = null, pubIconsLoaded = false;
let pubLoggedIn = false, pubOnly = null;
function showPublic(loggedIn = false){
  stopPoll(); clearInterval(dashTimer);
  pubLoggedIn = loggedIn === true;
  pubOnly = loggedIn && loggedIn.public_only ? loggedIn : null;     // Konto ohne Rechte: nur öffentliche Seite
  if (!pubLoggedIn) me = null;
  $("#btnPubLogin").textContent = pubLoggedIn ? "← Zur Verwaltung" : pubOnly ? `Abmelden (${pubOnly.username})` : "Anmelden";
  $("#btnPubLogin").title = pubOnly ? "Dein Konto hat noch keine Verwaltungsrechte – ein Admin kann sie unter „Benutzer“ vergeben" : "";
  $("#btnPubRegister").classList.toggle("hidden", !!(pubLoggedIn || pubOnly));
  $("#pubPending").classList.toggle("hidden", !(pubOnly && pubOnly.pending));
  if (pubOnly && pubOnly.pending) $("#pubPending").innerHTML = `⏳ Hallo <b>${esc(pubOnly.steam_name || pubOnly.username)}</b> – dein Konto ist angelegt und wartet auf Freigabe durch einen Admin. Bis dahin siehst du die öffentliche Übersicht.`;
  $("#app").classList.add("hidden"); $("#login").classList.add("hidden"); $("#pub").classList.remove("hidden");
  refreshPublic();
  clearInterval(pubTimer); pubTimer = setInterval(() => { if (!document.hidden) refreshPublic(); }, 10000);
}
async function refreshPublic(){
  try {
    const r = await (await fetch("/api/public", {cache: "no-store"})).json();
    pubData = r;
    if (!Object.keys(GAMES).length) GAMES = r.games;
    if (!pubIconsLoaded){ pubIconsLoaded = true; loadGameIcons().then(renderPublic); }
    renderPublic();
  } catch { $("#pubGrid").innerHTML = `<div class="hint">Serverliste gerade nicht erreichbar …</div>`; }
}
function reachPill(r){
  if (!r) return "";
  const ic = r.kind === "online" ? "🌐" : r.kind === "direct" ? "🔗" : "🏠";
  return `<span class="pill reach ${esc(r.kind)}" title="${esc(r.detail || "")}">${ic} ${esc(r.label)}</span>`;
}
function pubNetHtml(n){
  if (!n || n.down_bps == null) return "";
  return `<span class="pubcache net" title="Was die Server gerade aus dem Internet laden (Spielserver-Downloads + Lancache)"><i class="cdot"></i>Internet ↓ ${fmtRate(n.down_bps)}</span>`;
}
function pubCacheHtml(c){
  if (!c || !c.found) return "";
  if (!c.running) return `<span class="pubcache off" title="Lancache-Container läuft nicht – Downloads gehen direkt ins Internet"><i class="cdot"></i>Lancache aus</span>`;
  const tx = c.tx_bps || 0;
  return `<span class="pubcache" title="Lancache: was gerade an die Spieler im LAN ausgeliefert wird${c.hit_ratio != null ? ` · Trefferquote letzte Stunde ${c.hit_ratio} %` : ""}"><i class="cdot"></i>Lancache · ↓ ${fmtRate(tx)}${c.hit_ratio != null ? ` · ${Math.round(c.hit_ratio)} % aus dem Cache` : ""}</span>`;
}
function matchHtml(m){
  const t1 = m.team1 || {}, t2 = m.team2 || {}, when = m.ended || m.updated || m.started;
  const pl = t => (t.players || []).slice(0, 5).map(p => `<tr><td>${esc(p.name)}</td><td class="mono">${p.kills ?? "–"}</td><td class="mono">${p.deaths ?? "–"}</td><td class="mono">${p.assists ?? "–"}</td></tr>`).join("");
  const has = (t1.players || []).length || (t2.players || []).length;
  return `<details class="mcard"><summary>
      <span class="mstate ${m.live ? "live" : m.finished ? "" : "warm"}">${m.live ? "LIVE" : m.finished ? "Ende" : "läuft an"}</span>
      <b>${esc(t1.name || "Team 1")}</b> <span class="mscore">${t1.score ?? 0} : ${t2.score ?? 0}</span> <b>${esc(t2.name || "Team 2")}</b>
      <span class="hint">${esc(m.map || "")} · ${esc(m.server || "")} · ${when ? new Date(when * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}) : ""}</span></summary>
    ${has ? `<div class="mteams">${[t1, t2].map(t => `<table class="cachetable"><thead><tr><th>${esc(t.name || "")}</th><th>K</th><th>D</th><th>A</th></tr></thead><tbody>${pl(t)}</tbody></table>`).join("")}</div>` : `<div class="hint">Noch keine Spielerwerte.</div>`}
  </details>`;
}
function renderPublic(){
  const r = pubData; if (!r) return;
  refreshPubTour(); refreshPubStream(); refreshPubDm(); refreshPubHof();
  const on = r.servers.filter(x => x.online), pl = on.reduce((a, x) => a + (x.players || 0), 0);
  $("#pubStat").innerHTML = `<b>${on.length}</b> von ${r.servers.length} Servern online · <b>${pl}</b> Spieler · ` +
    (r.net === "internet" ? `<span class="pill" title="Du kommst aus dem Internet – Adressen zeigen die öffentliche IP">🌐 Internet${r.address ? " · " + esc(r.address) : ""}</span>`
                          : `<span class="pill ok" title="Du bist im LAN – Adressen zeigen die LAN-IP">LAN</span>`) + pubNetHtml(r.internet) + pubCacheHtml(r.cache);
  $("#pubCache").innerHTML = cacheGamesHtml(r.cached_games);
  if (!r.servers.length){ $("#pubGrid").innerHTML = `<div class="hint">Noch keine Server eingerichtet.</div>`; return; }
  // nach Spielen gruppieren: Spiele mit laufenden Servern zuerst, innerhalb der Gruppe die gewohnte Reihenfolge
  const groups = {};
  r.servers.forEach(x => (groups[x.game] = groups[x.game] || []).push(x));
  const glabel = k => (GAMES[k] || r.games[k] || {label: k}).label;
  const order = Object.keys(groups).sort((a, b) => (groups[b].some(x => x.online) - groups[a].some(x => x.online)) || glabel(a).localeCompare(glabel(b)));
  $("#pubGrid").innerHTML = order.map(k => {
    const list = groups[k], g0 = GAMES[k] || r.games[k] || {label: k, color: "#888"};
    const on = list.filter(x => x.online), pls = on.reduce((a, x) => a + (x.players || 0), 0);
    return `<div class="pubgroup" style="--gc:${g0.color}">${gameTile(k, 22)}<b>${esc(g0.label)}</b>
      <span class="hint">${on.length}/${list.length} online${pls ? ` · ${pls} Spieler` : ""}</span></div>` + list.map(pubCard).join("");
  }).join("");
  function pubCard(x){
    const g = GAMES[x.game] || r.games[x.game] || {label: x.game, color: "#888"};
    const j = x.join || {};
    const meta = [x.mode ? esc(x.mode) : "", x.version ? "v" + esc(x.version) : ""].filter(Boolean).join(" · ");
    const thumb = mapThumb({map: MAP_GAMES.has(x.game) && x.online ? x.map : "", workshop: x.workshop, map_image: x.map_image, map_title: x.map_label, map_layout: x.online ? x.map_layout : null}, x.game);
    return `<div class="pubcard${x.online || x.sleeping || x.install ? "" : " off"}" style="--gc:${g.color}" ${x.pending ? `title="wird gerade angelegt"` : `data-pub="${esc(x.id)}" tabindex="0" title="Details: Spieler, Rotation"`}>
      ${thumb ? `<div class="pubthumb">${thumb}<span class="pubmap">${MAP_GAMES.has(x.game) && x.online ? esc(x.map_label || x.map || "") : ""}</span></div>` : ""}
      <div class="pubtop">${gameTile(x.game, 18)}<div class="pubname"><b title="${esc(x.name)}">${esc(x.name)}</b>${x.online && reachPill(x.reach) ? `<span class="hint">${reachPill(x.reach)}</span>` : ""}</div>
        <span class="pill ${x.online ? "ok" : ""}">${x.online ? `● ${x.players ?? 0}${x.max_players ? "/" + x.max_players : ""} Spieler${x.bots ? ` · ${x.bots} Bots` : ""}` : x.sleeping ? "💤 schläft" : x.install ? "⬇ wird installiert" : "offline"}</span></div>
      ${x.install ? `<div class="pubinst"><div class="bar"><i style="width:${Math.min(100, x.install.pct)}%"></i></div><span>${esc(x.install.label)} · ${Math.round(x.install.pct)} %${x.install.rate_bps ? ` · ${x.install.rate_kind === "Kopieren" ? "⇄" : "↓"} ${fmtRate(x.install.rate_bps)}` : ""}${x.install.eta ? ` · fertig ca. ${etaClock(x.install.eta)} Uhr` : ""}</span></div>` : ""}
      ${x.sleeping ? `<div class="pubjoin"><button class="small primary" data-pwake="${esc(x.id)}">Aufwecken</button><span class="hint">Server ruht, weil niemand drauf war – startet in ${x.sleeping === "pause" ? "1–2 Sekunden" : "ca. 1–3 Minuten"}.</span></div>` : ""}
      ${x.map && x.map !== "–" && x.online ? `<div class="pubmapline">${esc(x.map_label || x.map)}</div>` : ""}
      ${meta ? `<div class="hint pubmeta">${meta}</div>` : ""}
      <div class="pubjoin">
        ${j.address ? `<button class="small" data-pcopy="${esc(j.address)}" title="Adresse kopieren">⧉ <span class="mono">${esc(j.address)}</span></button>` : ""}
        ${x.join_password ? `<button class="small" data-pcopy="${esc(x.join_password)}" title="Passwort kopieren">🔑 <span class="mono">${esc(x.join_password)}</span></button>` : ""}
        ${j.url && x.online ? `<a class="btn primary small" href="${esc(j.url)}">▶ Beitreten</a>` : ""}
        ${j.tv_url && x.online ? `<a class="btn small tvbtn" href="${esc(j.tv_url)}" title="Startet CS2 und verbindet als Zuschauer (CSTV). Läuft CS2 schon: Konsole öffnen und connect ${esc(j.tv_address || "")} eingeben">👁 Zusehen</a>` : ""}
      </div>
      ${j.hint ? `<div class="hint pubhint">${esc(j.hint)}</div>` : ""}
    </div>`;
  }
  $("#pubMatches").innerHTML = (r.matches || []).length ? `<h3 class="pdsec" style="margin-top:22px">Letzte Matches</h3><div class="mlist">${r.matches.map(matchHtml).join("")}</div>` : "";
  $$("#pubGrid [data-pcopy]").forEach(b => b.onclick = e => { e.stopPropagation(); copyText(b.dataset.pcopy); });
  $$("#pubGrid a.btn").forEach(a => a.onclick = e => e.stopPropagation());
  $$("#pubGrid [data-pwake]").forEach(b => b.onclick = async e => {
    e.stopPropagation(); b.disabled = true; b.textContent = "weckt …";
    try { const r = await fetch(`/api/public/${encodeURIComponent(b.dataset.pwake)}/wake`, {method: "POST"}); if (!r.ok) throw new Error((await r.json()).detail || r.statusText); toast("Server wird geweckt – gleich beitreten"); }
    catch (err){ toast(err.message, true); }
    setTimeout(refreshPublic, 2500);
  });
  $$("#pubGrid [data-pub]").forEach(c => {
    c.onclick = () => openPubDetail(c.dataset.pub);
    c.onkeydown = e => { if (e.key === "Enter") openPubDetail(c.dataset.pub); };
  });
}
let pubDetailId = null, pubDetailTimer = null;
async function openPubDetail(id){
  pubDetailId = id;
  const dlg = $("#dlgPub");
  if (!dlg.open) dlg.showModal();
  await renderPubDetail();
  clearInterval(pubDetailTimer);
  pubDetailTimer = setInterval(() => { if (dlg.open) renderPubDetail(); else clearInterval(pubDetailTimer); }, 10000);
}
async function renderPubDetail(){
  const x = (pubData && pubData.servers || []).find(s => s.id === pubDetailId);
  if (!x) return;
  let d = null;
  try { d = await (await fetch(`/api/public/${encodeURIComponent(x.id)}`, {cache: "no-store"})).json(); } catch {}
  const g = GAMES[x.game] || {label: x.game, color: "#888"}, j = x.join || {};
  const thumb = mapThumb({map: MAP_GAMES.has(x.game) && x.online ? x.map : "", workshop: x.workshop, map_image: x.map_image, map_title: x.map_label, map_layout: x.online ? x.map_layout : null}, x.game);
  const players = (d && d.players) || [];
  const rot = (d && d.rotation) || [];
  const cur = (d && d.map) || x.map_label || x.map;
  $("#pubDetail").innerHTML = `
    <div class="pdhead" style="--gc:${g.color}">${gameTile(x.game, 22)}<div style="min-width:0"><h2 style="margin:0">${esc(x.name)}</h2>
      <div class="hint">${esc(g.label)}${x.version ? " · v" + esc(x.version) : ""} · ${x.online ? `<span style="color:var(--ok)">online</span>` : "offline"}</div></div></div>
    <div class="pdgrid">
      ${thumb ? `<div class="pdthumb">${thumb}</div>` : ""}
      <div class="kvtable">
        ${cur && cur !== "–" ? `<span>${x.game === "wreckfest" ? "Strecke" : "Map"}</span><span>${esc(cur)}</span>` : ""}
        ${(d && d.mode) || x.mode ? `<span>Modus</span><span>${esc((d && d.mode) || x.mode)}</span>` : ""}
        <span>Spieler</span><span>${x.online ? `${x.players ?? 0}${x.max_players ? " / " + x.max_players : ""}${x.bots ? ` · ${x.bots} Bots` : ""}` : "–"}</span>
        ${j.address ? `<span>Adresse</span><span class="mono">${esc(j.address)}</span>` : ""}
        ${x.join_password ? `<span>Passwort</span><span class="mono">${esc(x.join_password)}</span>` : ""}
      </div>
    </div>
    <div class="pubjoin" style="margin:12px 0">
      ${j.address ? `<button class="small" data-pdcopy="${esc(j.address)}">⧉ Adresse kopieren</button>` : ""}
      ${x.join_password ? `<button class="small" data-pdcopy="${esc(x.join_password)}">🔑 Passwort kopieren</button>` : ""}
      ${j.url && x.online ? `<a class="btn primary small" href="${esc(j.url)}">▶ Beitreten</a>` : ""}
      ${j.tv_url && x.online ? `<a class="btn small tvbtn" href="${esc(j.tv_url)}">👁 Zusehen (CSTV)</a> <span class="hint">läuft CS2 schon: Konsole → <span class="mono">connect ${esc(j.tv_address || "")}</span></span>` : ""}
    </div>
    ${j.hint ? `<div class="hint" style="margin-bottom:12px">${esc(j.hint)}</div>` : ""}
    ${(d && d.matches || []).length ? `<h3 class="pdsec">Letzte Matches</h3><div class="mlist">${d.matches.map(matchHtml).join("")}</div>` : ""}
    <h3 class="pdsec">Spieler ${players.length ? `<span class="hint">(${players.length})</span>` : ""}</h3>
    ${players.length ? `<table class="cachetable"><thead><tr><th>Name</th><th>Zeit</th>${players.some(p => p.score != null) ? "<th>Punkte</th>" : ""}${players.some(p => p.ping != null) ? "<th>Ping</th>" : ""}</tr></thead><tbody>
      ${players.map(p => `<tr><td>${esc(p.name)}${p.bot ? ' <span class="pill">Bot</span>' : ""}</td><td class="mono">${esc(p.time || "")}</td>${players.some(q => q.score != null) ? `<td class="mono">${esc(p.score ?? "")}</td>` : ""}${players.some(q => q.ping != null) ? `<td class="mono">${esc(p.ping ?? "")}</td>` : ""}</tr>`).join("")}
      </tbody></table>` : `<div class="hint">${x.online ? "Gerade niemand drauf – oder das Spiel meldet keine Namen." : "Server ist offline."}</div>`}
    ${rot.length ? `<h3 class="pdsec">${x.game === "wreckfest" ? "Rotation" : "Mapcycle"} <span class="hint">(${rot.length})</span></h3>
      <ol class="pdrot${rot.some(r => r.layout || r.image) ? " withimg" : ""}">${rot.map(r => `<li class="${r.name === cur ? "cur" : ""}">${r.layout || r.image ? wfThumb(r.image, r.layout, r.name) : ""}<span><b>${esc(r.name)}</b>${r.sub ? ` <span class="hint">${esc(r.sub)}</span>` : ""}</span></li>`).join("")}</ol>` : ""}`;
  $$("#pubDetail [data-pdcopy]").forEach(b => b.onclick = () => copyText(b.dataset.pdcopy));
}
$("#btnPubLogin").onclick = async () => {
  if (pubOnly){ await api("/api/logout", {method: "POST"}).catch(() => {}); return showPublic(); }
  pubLoggedIn ? start() : showLogin();
};
async function afterLogin(){
  const m = await api("/api/me").catch(() => ({authenticated: false}));
  if (!m.authenticated) return showPublic();
  if (m.user && m.user.public_only){ showPublic(m.user); toast("Angemeldet – dein Konto sieht (noch) nur die öffentliche Übersicht"); return; }
  start();
}
$("#btnPubView").onclick = () => showPublic(true);
$("#btnBackPub").onclick = () => showPublic();
$("#loginForm").addEventListener("submit", async e => {
  e.preventDefault(); $("#loginErr").textContent = "";
  try { await api("/api/login", {body:{username: $("#loginUser").value.trim() || "admin", password: $("#loginPw").value}}); $("#loginPw").value = ""; afterLogin(); }
  catch(err){ $("#loginErr").textContent = err.message; }
});
function toMobile(){ try { localStorage.setItem("gsmView", "mobile"); } catch {} clearInterval(dashTimer); $("#app").classList.add("hidden"); startMobile(); }
$("#btnLogout").onclick = async () => { await api("/api/logout", {method:"POST"}); showPublic(); };

/* ================= Navigation ================= */
$$(".nav [data-view]").forEach(b => b.onclick = () => showView(b.dataset.view));
function showView(v){
  view = v; wfLoadedFor = null;
  if (v !== "server"){ current = null; stopPoll(); stopCt(); }
  $$(".nav [data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === v));
  VIEWS.forEach(x => $("#view-"+x).classList.toggle("hidden", x !== v));
  if (v === "scan") loadScan();
  if (v === "create") initCreate();
  if (v === "users") loadUsers();
  renderServerList();
  if (v === "dash"){ refreshDash(); refreshCache(); }
  if (v === "players") loadPlayers();
  if (v === "auto"){ renderAuto(); loadGslt(); loadNotify(); loadBackup(); }
  if (v === "cache"){ loadCacheLive(); loadCacheHistory(); loadDnsCheck(); }
  if (v === "prefill"){ pfLoaded = false; showPfSvc(pfSvc); }
  if (v === "storage"){ loadStorage(true); loadFolders(); loadDocker().then(() => loadSysDisk()); }
  if (v === "game") renderGameView();
  if (v === "bot"){ botLoaded = false; loadBot(); }
  if (v === "api") loadApi();
  if (v === "tour"){ tourLoaded = false; loadTour(); stLoaded = false; loadStream(); loadTourLib(); loadTourHof(); }
}

/* ================= Serverliste ================= */
let overview = [];
let gvGame = null, gvSel = new Set();   // Spiel-Übersicht
async function loadServers(){
  servers = await api("/api/servers");
  if (current) current = servers.find(s => s.id === current.id) || null;
  renderServerList();
  $("#plImportSrv").innerHTML = servers.map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("");
}
function stateOf(id){ return overview.find(o => o.server.id === id) || {}; }
function renderServerList(){
  if (!servers.length){ $("#serverList").innerHTML = `<div class="muted" style="padding:10px 16px">Keine Server angelegt.</div>`; return; }
  const order = Object.keys(GAMES).length ? Object.keys(GAMES) : ["cs2"];
  const groups = order.map(g => [g, servers.filter(s => gameOf(s) === g)]).filter(([, l]) => l.length);
  $("#serverList").innerHTML = groups.map(([g, list]) => {
    const on = list.filter(s => stateOf(s.id).online).length;
    const players = list.reduce((a, s) => a + (stateOf(s.id).online ? (stateOf(s.id).humans || 0) : 0), 0);
    const open = !collapsed[g] || (current && gameOf(current) === g);
    return `<div class="sgroup ${open ? "open" : ""}">
      <div class="sghead${view === "game" && gvGame === g ? " active" : ""}" data-group="${g}">
        <button class="sgopen" data-gview="${g}" title="Alle ${esc(GAMES[g]?.label || g)}-Server anzeigen und gemeinsam steuern">${gameTile(g, 18)}
        <span class="sgname">${esc(GAMES[g]?.short || g)}</span>
        <span class="sgcount">${on}/${list.length}${players ? ` · ${players} ☺` : ""}</span></button>
        <button class="chev" data-gtoggle="${g}" title="ein-/ausklappen">▾</button>
      </div>
      <div class="sgbody">${list.map(s => {
        const st = stateOf(s.id);
        const lim = st.visible_players > 0 ? st.visible_players : st.max_players;
        const cnt = st.online ? `${st.humans ?? 0}${lim ? "/" + lim : ""}${st.bots ? ` +${st.bots}🤖` : ""}` : "";
        return `<div class="srv ${current && current.id===s.id ? "active":""}" data-id="${esc(s.id)}">
          ${led(st)}
          <div class="meta"><div class="n">${esc(s.name)}</div><div class="h">${esc(st.map || s.host+":"+s.port)}</div></div>
          <span class="cnt">${esc(cnt)}</span></div>`;
      }).join("")}</div></div>`;
  }).join("");
  $$(".srv").forEach(el => el.onclick = () => selectServer(servers.find(s => s.id === el.dataset.id)));
  $$("[data-gtoggle]").forEach(b => b.onclick = () => {
    const g = b.dataset.gtoggle, grp = b.closest(".sgroup");
    collapsed[g] = grp.classList.contains("open");
    try { localStorage.setItem("gsmCollapsed", JSON.stringify(collapsed)); } catch {}
    grp.classList.toggle("open");
  });
  $$("[data-gview]").forEach(b => b.onclick = () => { gvGame = b.dataset.gview; gvSel = new Set(); showView("game"); });
  if (view === "game") renderGameView();
}

/* ================= Status-LED ================= */
const CSTATE = {running: "läuft", exited: "gestoppt", restarting: "startet neu", created: "angelegt", paused: "pausiert", dead: "defekt", removing: "wird entfernt"};
function ledOf(o){
  if (o && o.sleeping) return {cls: "sleep", tip: o.sleeping === "pause" ? "schläft – pausiert (Ruhemodus)" : "schläft – angehalten (Ruhemodus)"};
  const c = o && o.load && !o.load.error ? o.load.state : null;
  if (o && o.online) return {cls: "on", tip: "Server online" + (c ? " · Container " + (CSTATE[c] || c) : "")};
  if (c === "running" || c === "restarting") return {cls: "warn", tip: "Container " + (CSTATE[c] || c) + ", aber das Spiel antwortet (noch) nicht – startet/aktualisiert vermutlich"};
  if (c) return {cls: "off", tip: "Container " + (CSTATE[c] || c)};
  if (o && o.online === false) return {cls: "off", tip: "Server nicht erreichbar"};
  return {cls: "", tip: "noch nicht abgefragt"};
}
const led = o => { const l = ledOf(o); return `<span class="dot ${l.cls}" title="${esc(l.tip)}"></span>`; };

/* ================= Last ================= */
const lvl = p => p >= 85 ? "crit" : p >= 60 ? "warn" : "ok";
const fmtMem = mb => mb == null ? "–" : mb >= 1024 ? (mb/1024).toFixed(1) + " GB" : mb + " MB";
// Zahlen weich animieren statt springen
function tween(el, target, fmt, ms = 800){
  if (!el) return;
  if (target == null || isNaN(target)){ el.textContent = fmt(null); el._v = null; return; }
  const from = el._v == null ? target : el._v, t0 = performance.now();
  el._v = target;
  cancelAnimationFrame(el._raf);
  const step = now => {
    const k = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt(from + (target - from) * e);
    if (k < 1) el._raf = requestAnimationFrame(step);
  };
  el._raf = requestAnimationFrame(step);
}
// weich gerundete Kurve (monotone kubische Interpolation, kein Überschwingen)
function smoothPath(pts){
  if (pts.length < 2) return pts.length ? `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}` : "";
  const n = pts.length, d = [], m = [];
  for (let i = 0; i < n - 1; i++) d.push((pts[i+1][1] - pts[i][1]) / ((pts[i+1][0] - pts[i][0]) || 1));
  m[0] = d[0]; m[n-1] = d[n-2];
  for (let i = 1; i < n - 1; i++) m[i] = d[i-1] * d[i] <= 0 ? 0 : (d[i-1] + d[i]) / 2;
  for (let i = 0; i < n - 1; i++){
    if (d[i] === 0){ m[i] = 0; m[i+1] = 0; continue; }
    const a = m[i] / d[i], b = m[i+1] / d[i], h = a*a + b*b;
    if (h > 9){ const t = 3 / Math.sqrt(h); m[i] = t * a * d[i]; m[i+1] = t * b * d[i]; }
  }
  let p = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < n - 1; i++){
    const [x0, y0] = pts[i], [x1, y1] = pts[i+1], dx = (x1 - x0) / 3;
    p += `C${(x0+dx).toFixed(1)},${(y0+m[i]*dx).toFixed(1)} ${(x1-dx).toFixed(1)},${(y1-m[i+1]*dx).toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
  }
  return p;
}
async function refreshHost(){
  let h;
  try { h = await api("/api/host"); } catch { return; }
  $("#hlHost").textContent = h.cores ? h.cores + " Kerne" : "";
  const g = h.games || {};
  $("#hlSub").innerHTML = `${fmtMem(h.mem_used_mb)} von ${fmtMem(h.mem_total_mb)} · Load ${h.load ? h.load.map(x => x.toFixed(2)).join(" ") : "–"}` +
    (g.containers ? `<br>Spielserver: ${g.running}/${g.containers} laufen · ${g.cpu_host} % CPU · ${fmtMem(g.mem_mb)}` +
      "" : "") +
    (h.local_disk ? `<br><span title="Interne Platte des Servers (Docker)">💽 Interne Platte: <b>${fmtBytes(h.local_disk.free)}</b> frei von ${fmtBytes(h.local_disk.total)}</span>` : "") +
    (h.cs2_template ? `<br><span title="Lokale Kopie von ${esc(h.cs2_template.src_name || "CS #1")} – neue CS-Server kopieren von hier">CS-Vorlage: ${h.cs2_template.busy ? "wird aktualisiert" + (h.cs2_template.progress != null ? " " + h.cs2_template.progress + " %" : " …") : h.cs2_template.last ? fmtBytes(h.cs2_template.bytes || 0) + " · Stand " + new Date(h.cs2_template.last * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}) : "noch keine"}${h.cs2_template.error ? " · ⚠ " + esc(h.cs2_template.error.slice(0, 60)) : ""}</span>${!h.cs2_template.busy && me && me.role === "admin" ? ` · <a href="#" onclick="tplRefresh();return false" title="CS-Dateien von ${esc(h.cs2_template.src_name || "CS #1")} jetzt auf die interne Platte kopieren (sonst automatisch um 05:00)${esc(durText("tpl", h.cs2_template.last ? "update" : "first") ? "\n" + durText("tpl", h.cs2_template.last ? "update" : "first") : "")}">${h.cs2_template.last ? "aktualisieren" : "jetzt erstellen"}</a>` : ""}` : "");
}
function problemsHtml(list){
  if (!list || !list.length) return "";
  return list.map(p => `<div class="problem ${p.level === "info" ? "info" : ""}" title="${esc(p.line || "")}">
    <b>${p.level === "info" ? "ℹ" : "⚠"} ${esc(p.title)}</b><div>💡 ${esc(p.solution)}</div></div>`).join("");
}
function loadHtml(l){
  if (!l) return "";
  if (l.error) return `<div class="loadrow"><span>Container</span><span class="hint">${esc(/no such container/i.test(l.error) ? "nicht gefunden – unter „Bearbeiten“ neu zuordnen" : l.error)}</span><span></span></div>`;
  if (l.state !== "running") return `<div class="loadrow"><span>Container</span><span style="color:var(--bad)">${esc(CSTATE[l.state] || l.state || "?")}</span><span></span></div>`;
  const c = l.cpu_host || 0;
  const nb = v => v > 0 ? Math.max(2, Math.min(100, v / LINK_BPS * 100)) : 0;
  return `<div class="loadrow" title="CPU bezogen auf den ganzen Host"><span>Last</span>
    <div class="bar"><i class="lr-cpu ${lvl(c)}" style="width:${Math.min(100, c)}%"></i></div>
    <span><b class="lr-cpuv">${c.toFixed(1)} %</b> CPU · <b class="lr-mem">${fmtMem(l.mem_mb)}</b></span></div>
    <div class="loadrow" title="Netzwerk des Containers: blau = Download, orange = Upload"><span>Netz</span>
    ${l.net_host ? `<span class="hint">Host-Netzwerk – pro Server nicht messbar</span><span></span>` :
      `<div class="bar dbar"><i class="lr-rx" style="width:${nb(l.rx_bps)}%"></i><i class="lr-tx" style="width:${nb(l.tx_bps)}%"></i></div>
       <span><b class="lr-rxv" style="color:${C_DOWN}">↓ ${l.rx_bps != null ? fmtRate(l.rx_bps) : "–"}</b> <b class="lr-txv" style="color:${C_UP}">↑ ${l.tx_bps != null ? fmtRate(l.tx_bps) : "–"}</b></span>`}</div>`;
}
// Sekundenwerte direkt in die vorhandenen Zeilen schreiben (weich animiert, ohne Neuaufbau)
function updateLoadRow(el, d){
  if (!el || !d) return;
  const nb = v => v > 0 ? Math.max(2, Math.min(100, v / LINK_BPS * 100)) : 0;
  const q = c => el.querySelector(c);
  if (q(".lr-cpu") && d.cpu_host != null){ q(".lr-cpu").style.width = Math.min(100, d.cpu_host) + "%"; q(".lr-cpu").className = "lr-cpu " + lvl(d.cpu_host); tween(q(".lr-cpuv"), d.cpu_host, v => v.toFixed(1) + " %"); }
  if (q(".lr-mem") && d.mem_mb != null) q(".lr-mem").textContent = fmtMem(d.mem_mb);
  if (q(".lr-rx") && d.rx_bps != null){ q(".lr-rx").style.width = nb(d.rx_bps) + "%"; tween(q(".lr-rxv"), d.rx_bps, v => "↓ " + fmtRate(v)); }
  if (q(".lr-tx") && d.tx_bps != null){ q(".lr-tx").style.width = nb(d.tx_bps) + "%"; tween(q(".lr-txv"), d.tx_bps, v => "↑ " + fmtRate(v)); }
}
// Antwortzeiten als ein Balken: der am stärksten belastete Teil (NAS, lokale Platte, Netz) bestimmt die Füllung.
// 100 % = deutlich überlastet (NAS 50 ms, Platte 100 ms, 2 % TCP-Wiederholungen).
const LAT_LIMIT = {nas: 50, disk: 100, tcp: 2};
let latHold = {};
function latencyRow(io){
  const bar = $("#hlLatBar"), val = $("#hlLat"), row = $("#hlLatRow");
  if (!bar) return;
  if (!io || !io.available){ row.classList.add("hidden"); return; }
  row.classList.remove("hidden");
  const now = Date.now(), parts = [];
  // NAS: nach Anfragen gewichteter Schnitt; ohne Anfragen den letzten Wert 10 s halten
  let ops = 0, sum = 0;
  for (const m of io.mounts || []) if (m.rtt_ms != null && m.ops_s > 0){ ops += m.ops_s; sum += m.rtt_ms * m.ops_s; }
  if (ops > 0) latHold.nas = {v: sum / ops, t: now};
  const nas = latHold.nas && now - latHold.nas.t < 10000 ? latHold.nas.v : null;
  if (nas != null) parts.push({k: "NAS", ms: nas, s: nas / LAT_LIMIT.nas});
  const busy = (io.disks || []).filter(d => d.await_ms != null && d.iops > 0.5);
  if (busy.length){ const d = busy.reduce((a, b) => b.await_ms > a.await_ms ? b : a); latHold.disk = {v: d.await_ms, n: d.name, u: d.util, t: now}; }
  const dk = latHold.disk && now - latHold.disk.t < 10000 ? latHold.disk : null;
  if (dk) parts.push({k: "Platte " + dk.n, ms: dk.v, s: Math.max(dk.v / LAT_LIMIT.disk, (dk.u || 0) / 100 * 0.9), extra: ` · ${Math.round(dk.u || 0)} % belegt`});
  const rt = io.tcp ? io.tcp.retrans_pct : null;
  if (rt != null) parts.push({k: "TCP-Wiederholungen", pct: rt, s: rt / LAT_LIMIT.tcp});
  if (!parts.length){ bar.style.width = "0%"; bar.className = "ok"; val.textContent = "ruhig"; row.title = "Antwortzeiten: gerade keine Zugriffe auf NAS/Platte"; return; }
  const worst = parts.reduce((a, b) => b.s > a.s ? b : a);
  const pct = Math.max(2, Math.min(100, worst.s * 100));
  bar.style.width = pct + "%"; bar.className = lvl(pct);
  const msParts = parts.filter(p => p.ms != null);
  const shown = (worst.ms != null ? worst : msParts.reduce((a, b) => !a || b.ms > a.ms ? b : a, null));
  if (shown) tween(val, shown.ms, v => (v < 10 ? v.toFixed(1) : Math.round(v)) + " ms"); else val.textContent = worst.pct.toFixed(1) + " %";
  val.style.color = pct >= 85 ? "var(--bad)" : pct >= 60 ? "var(--accent)" : "";
  row.title = "Antwortzeiten (Balken = am stärksten belasteter Teil)\n" + parts.map(p =>
    `${p === worst ? "▶ " : "   "}${p.k}: ${p.ms != null ? p.ms.toFixed(1) + " ms" : p.pct.toFixed(2) + " %"}${p.extra || ""}`).join("\n")
    + `\nGrenzen für vollen Balken: NAS ${LAT_LIMIT.nas} ms, Platte ${LAT_LIMIT.disk} ms, TCP ${LAT_LIMIT.tcp} %`;
}
let liveBusy = false, lastLive = null;
// Seitenleiste: Spitzenwert der letzten 5 Minuten als Marke im Balken
const PEAK = {};
function peakMark(barId, pct, scale){
  const bar = document.getElementById(barId); if (!bar) return;
  const now = Date.now(), h = (PEAK[barId] = (PEAK[barId] || []).filter(x => now - x[0] < 300000));
  h.push([now, pct || 0]);
  const pk = Math.max(...h.map(x => x[1]));
  const box = bar.parentNode;
  let m = box.querySelector(".pk");
  if (!m){ m = document.createElement("span"); m.className = "pk"; box.appendChild(m); }
  m.style.left = `calc(${Math.min(100, pk)}% - 1px)`;
  box.title = scale ? `Spitze der letzten 5 Minuten: ${fmtRate(pk / 100 * scale)} · Balken voll = ${fmtRate(scale)} (Höchstwert 24 h)` : `Spitze der letzten 5 Minuten: ${Math.round(pk)} %`;
}
async function liveTick(){
  if (liveBusy || document.hidden || !me || $("#app").classList.contains("hidden")) return;
  liveBusy = true;
  try {
    const L = await api("/api/live");
    lastLive = L;
    const memPct = L.mem_total_mb ? L.mem_used_mb / L.mem_total_mb * 100 : null;
    if (L.cpu != null){ peakMark("hlCpuBar", L.cpu); $("#hlCpuBar").style.width = L.cpu + "%"; $("#hlCpuBar").className = lvl(L.cpu); tween($("#hlCpu"), L.cpu, v => v.toFixed(0) + " %"); }
    if (memPct != null){ peakMark("hlMemBar", memPct); $("#hlMemBar").style.width = memPct + "%"; $("#hlMemBar").className = lvl(memPct); tween($("#hlMem"), memPct, v => Math.round(v) + " %"); }
    // Skala der Netz-Balken: höchster Wert der letzten 24 h (mind. 1 MB/s), nicht die Leitung
    const P = L.peak24 || {}, sc = k => niceMax(Math.max(1e6, P[k] || 0));
    const n = L.net || {}, bwk = (v, k) => v > 0 ? Math.max(2, Math.min(100, v / sc(k) * 100)) : 0, bw = v => bwk(v, "rx");
    if (n.rx_bps != null){
      $("#hlNetDownBar").style.width = bwk(n.rx_bps, "rx") + "%"; $("#hlNetUpBar").style.width = bwk(n.tx_bps, "tx") + "%";
      peakMark("hlNetDownBar", bwk(n.rx_bps, "rx"), sc("rx")); peakMark("hlNetUpBar", bwk(n.tx_bps, "tx"), sc("tx"));
      if (n.nic_rx_bps != null){
        const tot = (n.nic_rx_bps || 0) + (n.nic_tx_bps || 0), tp = bwk(tot, "nic");
        $("#hlNicBar").style.width = tp + "%"; peakMark("hlNicBar", tp, sc("nic")); tween($("#hlNic"), tot, v => fmtRate(v));
        $("#hlNicRow").title = `Netzwerkkarte gesamt inkl. LAN: ${fmtRate(tot)}\n↓ ${fmtRate(n.nic_rx_bps)} · ↑ ${fmtRate(n.nic_tx_bps)}\nBalken voll = ${fmtRate(sc("nic"))} (Höchstwert der letzten 24 h)`;
      }
      tween($("#hlNetDown"), n.rx_bps, v => fmtRate(v)); tween($("#hlNetUp"), n.tx_bps, v => fmtRate(v));
      const tt = `Internet-Durchsatz (geschätzt): ↓ was Lancache und Spielserver empfangen, ↑ was die Spielserver senden – ohne LAN-Verkehr (Cache → Clients, NAS)` + (n.nic_rx_bps != null ? `\nNetzwerkkarte gesamt inkl. LAN: ↓ ${fmtRate(n.nic_rx_bps)} · ↑ ${fmtRate(n.nic_tx_bps)}` : "");
      $("#hlNetTotRow").title = tt; $("#hlNetTotRow").nextElementSibling.title = tt;
    }
    latencyRow(L.io);
    if (L.cache && L.cache.tx_bps != null && !$("#hlNetRow").classList.contains("hidden")){
      $("#hlNetBar").style.width = bwk(L.cache.tx_bps, "cache") + "%"; peakMark("hlNetBar", bwk(L.cache.tx_bps, "cache"), sc("cache")); tween($("#hlNet"), L.cache.tx_bps, v => fmtRate(v));
    }
    if (view === "dash") for (const [sid, d] of Object.entries(L.servers || {})) updateLoadRow(document.querySelector(`[data-ld="${sid}"]`), d);
  } catch {} finally { liveBusy = false; }
}
setInterval(liveTick, 1000);
// Live-Diagramme (Bereich „Live“) alle 2 s nachzeichnen
setInterval(async () => {
  if (document.hidden || view !== "dash" || metricsRange > 10) return;
  await loadMetrics(true);
  $("#hostPanel").innerHTML = hostPanelHtml();
  $$("[data-mwl]").forEach(el => { el.innerHTML = metricsLine(el.dataset.mwl); });
}, 2000);

/* ================= Lancache ================= */
// Größen binär wie „df -h“ und der Lancache (1 GB = 1024³ Byte), damit die Zahlen übereinstimmen
const fmtBytes = b => b == null ? "–" : b >= 2**40 ? (b/2**40).toFixed(2) + " TB" : b >= 2**30 ? (b/2**30).toFixed(1) + " GB" : b >= 2**20 ? (b/2**20).toFixed(0) + " MB" : Math.round(b/2**10) + " KB";
const LINK_BPS = 125e6;   // 1 Gbit/s als 100 % für den Durchsatz-Balken
const fmtRate = bps => bps == null ? "–" : bps >= 1e9 ? (bps/1e9).toFixed(2) + " GB/s" : bps >= 1e6 ? (bps/1e6).toFixed(1) + " MB/s" : bps >= 1e4 ? Math.round(bps/1e3) + " KB/s" : bps >= 1e3 ? (bps/1e3).toFixed(1) + " KB/s" : Math.round(bps) + " B/s";
let cacheData = null;
const CACHE_NAMES = {steam: "Steam", epicgames: "Epic Games", origin: "EA App / Origin", blizzard: "Battle.net (Blizzard)",
  riot: "Riot Games", wsus: "Windows Update (WSUS)", windowsupdates: "Windows Update (WSUS)", uplay: "Ubisoft Connect",
  xboxlive: "Xbox / Microsoft Store", nintendo: "Nintendo", sony: "PlayStation", wargaming: "Wargaming",
  frontier: "Frontier", arenanet: "ArenaNet (Guild Wars)", rockstar: "Rockstar", apple: "Apple-Updates",
  daybreak: "Daybreak", neverwinter: "Neverwinter", renegadex: "Renegade X", teso: "Elder Scrolls Online",
  warframe: "Warframe", cityofheroes: "City of Heroes", hirez: "Hi-Rez", pathofexile: "Path of Exile",
  bsg: "Escape from Tarkov", test: "Test", generic: "Sonstiges"};
const cacheName = id => id === "_other" ? "Weitere Dienste" : CACHE_NAMES[(id || "").toLowerCase()] || id || "?";
// eigene, schlichte Symbole je Dienst (keine offiziellen Logos)
const SVC_ICONS = {
  steam: ['<rect x="2.5" y="7" width="19" height="11" rx="5"/><path d="M7.5 10.5v4M5.5 12.5h4"/><circle cx="15.5" cy="11.5" r="1"/><circle cx="18" cy="14" r="1"/>', "#5b8fd6"],
  wsus: ['<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="8" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/><path d="M17 13v8M14 18l3 3 3-3"/>', "#4fb3e8"],
  epicgames: ['<path d="M5 3h14v14l-7 4-7-4z"/><path d="M9 8h6M9 12h4"/>', "#b8b8b8"],
  origin: ['<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>', "#f57c3a"],
  blizzard: ['<path d="M12 2v20M3.3 7l17.4 10M3.3 17L20.7 7"/>', "#4aa3ff"],
  riot: ['<path d="M4 18l2-12 12-2 2 14z"/><path d="M8 18l1-7"/>', "#e84a4a"],
  uplay: ['<circle cx="12" cy="12" r="8"/><path d="M8 13a4 4 0 1 0 4-5"/>', "#4f7bff"],
  xboxlive: ['<circle cx="12" cy="12" r="8.5"/><path d="M7 6c3 3 7 9 9 13M17 6c-3 3-7 9-9 13"/>', "#4cbb5f"],
  sony: ['<path d="M4 15h16M6 11h12M8 7h8"/>', "#3d6ee0"],
  nintendo: ['<rect x="4" y="4" width="7" height="16" rx="3"/><rect x="13" y="4" width="7" height="16" rx="3"/>', "#e85454"],
  apple: ['<path d="M12 7c-4-2-8 1-7 6s4 8 7 6c3 2 6-1 7-6s-3-8-7-6z"/><path d="M12 7c0-2 1-3 3-4"/>', "#c8c8c8"],
  _: ['<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 19h16"/>', "#9aa3ad"],
};
SVC_ICONS.windowsupdates = SVC_ICONS.wsus;
// Originalsymbole der Anbieter (deren eigenes Favicon, wird live geladen; offline -> eigenes Ersatzsymbol)
const SVC_FAVICON = {steam: "store.steampowered.com", wsus: "www.microsoft.com", windowsupdates: "www.microsoft.com",
  epicgames: "store.epicgames.com", origin: "www.ea.com", blizzard: "www.blizzard.com", riot: "www.riotgames.com",
  uplay: "www.ubisoft.com", xboxlive: "www.xbox.com", sony: "www.playstation.com", nintendo: "www.nintendo.com",
  apple: "www.apple.com", wargaming: "wargaming.net", rockstar: "www.rockstargames.com", frontier: "www.frontier.co.uk",
  arenanet: "www.arena.net", pathofexile: "www.pathofexile.com", warframe: "www.warframe.com", hirez: "www.hirezstudios.com",
  bsg: "www.escapefromtarkov.com", teso: "www.elderscrollsonline.com"};
function svcIcon(id, size = 16){
  const key = (id || "").toLowerCase(), dom = SVC_FAVICON[key];
  const own = svcIconOwn(key, size);
  if (!dom) return own;
  return `<span class="svcorig"><img src="https://www.google.com/s2/favicons?domain=${dom}&sz=32" width="${size + 4}" height="${size + 4}" alt="" loading="lazy" referrerpolicy="no-referrer"
    onerror="this.parentNode.classList.add('fail')">${own}</span>`;
}
function svcIconOwn(key, size){
  const [path, color] = SVC_ICONS[key] || SVC_ICONS._;
  return `<span class="gtile svctile" style="background:${color}"><svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg></span>`;
}
function svcRows(list){
  return (list || []).map(x => {
    const tot = x.hit + x.miss, p = tot ? Math.round(x.hit / tot * 100) : 0;
    return `<tr><td><div class="row" style="gap:8px;flex-wrap:nowrap">${svcIcon(x.name, 15)}<b>${esc(cacheName(x.name))}</b> <span class="hint mono">${esc(x.name)}</span></div></td>
      <td class="mono" style="color:var(--ok)">${fmtBytes(x.hit)}</td><td class="mono">${fmtBytes(x.miss)}</td><td class="mono">${fmtBytes(tot)}</td>
      <td style="min-width:140px"><div class="cachebar" title="${p} % aus dem Cache"><i style="width:${p}%"></i></div></td><td class="mono">${p} %</td></tr>`;
  }).join("");
}
// Cache-Ordner (du im Lancache-Container) statt der ganzen NAS-Freigabe
function storageCard(st, disk){
  st = st || {};
  const logs = (st.logs || []).reduce((a, x) => a + x.bytes, 0);
  const measured = st.cache_bytes != null && st.measured;
  const val = measured ? st.cache_bytes : st.estimate;
  const lim = st.limit, pct = lim && val != null ? Math.min(100, Math.round(val / lim * 100)) : null;
  const du = st.du || {}, iv = st.inventory || {};
  const how = st.method === "du" ? "genau gezählt" : st.method === "df" ? "gemessen" : "";
  const when = measured ? new Date(st.measured * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}) : "";
  const duBar = du.active ? (() => {
    const p = du.total ? Math.min(100, du.done / du.total * 100) : 0;
    return `<div class="dubar" title="Zählt Ordner für Ordner (${du.done}/${du.total || "?"}) mit niedrigster Priorität${du.stalled ? " – seit über 30 min kein Fortschritt" : ""}">
      <div class="bar"><i style="width:${p.toFixed(1)}%;background:${du.stalled ? "var(--accent)" : "var(--ct)"}"></i></div>
      <div class="hint">wird genau gezählt … ${p.toFixed(0)} % · bisher ${fmtBytes(du.bytes)}${du.started ? " · seit " + new Date(du.started * 1000).toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"}) : ""}${du.stalled ? " · ⚠ hängt?" : ""}</div></div>`;
  })() : "";
  return `<div class="card" title="${measured ? `${how}, ${when}` : "Geschätzt aus den Logs (alles, was in den Cache geladen wurde) – ohne Festplattenzugriff"}">
    <div class="k">Cache-Ordner${lim ? " (Limit " + esc(st.limit_raw || fmtBytes(lim)) + ")" : ""}</div><div class="v">${val != null ? (measured ? "" : "≈ ") + fmtBytes(val) : "–"}</div>
    ${pct != null ? `<div class="bar" style="margin-top:6px"><i class="${lvl(pct)}" style="width:${pct}%"></i></div>` : ""}
    <div class="s">${pct != null ? pct + " % vom Limit · " : ""}${measured ? `${st.method === "df" ? "per df, jede Minute" : how} · ${when} · ` : ""}Logs ${fmtBytes(logs)} · ${st.busy ? "misst …" : du.active ? "" : `<a href="#" onclick="measureCache();return false" title="Belegung des Cache-Datenträgers messen (dauert eine Sekunde – der Cache liegt auf eigenem Datenträger)">messen</a>`}</div>
    ${duBar}${iv.running ? `<div class="dubar" title="Liest eine gleichmäßig verteilte Stichprobe der Cache-Dateien (1/256) und erkennt daran, welche Spiele wirklich im Cache liegen">
      <div class="bar"><i style="width:${(iv.done / (iv.total || 256) * 100).toFixed(1)}%;background:var(--ct)"></i></div>
      <div class="hint">Inhalt wird abgeglichen … ${iv.done}/${iv.total || 256} Ordner</div></div>`
      : iv.last ? `<div class="hint" style="font-size:11px;margin-top:4px">Inhalt abgeglichen ${new Date(iv.last * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"})} (Stichprobe ${esc(iv.sample || "")}, ${iv.files || 0} Dateien)${iv.error ? " · ⚠ " + esc(iv.error) : ""}</div>` : ""}</div>`;
}
/* ---- Dauer früherer Läufe (vor dem Start anzeigen) ---- */
let TIMINGS = {}, timingsAt = 0;
async function loadTimings(force){
  if (!force && Date.now() - timingsAt < 60000) return TIMINGS;
  try { TIMINGS = await api("/api/timings"); timingsAt = Date.now(); } catch {}
  return TIMINGS;
}
const fmtDur = s => s == null ? "–" : s < 90 ? Math.round(s) + " s" : s < 5400 ? Math.round(s / 60) + " min" : (s / 3600).toFixed(1).replace(".", ",") + " h";
// „dauerte zuletzt 12 min (Ø 15 min aus 3 Läufen)“ – leer, wenn noch nie gemessen
function durText(op, key, label){
  const t = TIMINGS[`${op}:${key || "-"}`];
  if (!t) return "";
  return `${label ? label + " " : ""}dauerte zuletzt ${fmtDur(t.last)}${t.n > 1 ? ` (Ø ${fmtDur(t.avg)} aus ${t.n} Läufen)` : ""}${t.info ? " – " + t.info : ""}, am ${new Date(t.when * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"})}`;
}
loadTimings();
async function tplRefresh(){
  await loadTimings(true);
  const d = durText("tpl", "update", "Letzte Aktualisierung") || durText("tpl", "first", "Erste Erstellung");
  if (!confirm("CS2-Vorlage jetzt auf die interne Platte kopieren?\n" + (d || "Noch nie gemessen – erste Erstellung kopiert ca. 60 GB, das dauert einige Minuten."))) return;
  try { await api("/api/cs2-template/refresh", {method: "POST"}); toast("Vorlage wird erstellt – Fortschritt steht links unter „CS-Vorlage“"); } catch (e) { toast(e.message, true); }
}
async function measureCache(){
  await loadTimings(true);

  try {
    const r = await api("/api/cache/measure", {method: "POST"});
    const st = r.storage || {};
    toast(`Cache belegt ${fmtBytes(st.cache_bytes)} – Inhalt wird jetzt per Stichprobe abgeglichen (einige Minuten)`);
  } catch (e) { toast(e.message, true); }
  refreshCache(); if (view === "cache") loadCacheHistory();
  clearInterval(window._duTimer);
  window._duTimer = setInterval(async () => {          // Fortschritt nachziehen, bis fertig
    if (view === "cache") await loadCacheHistory();
    await refreshCache();
    const c = cacheData && cacheData.storage;
    if (!c || !(c.inventory && c.inventory.running)) { clearInterval(window._duTimer); if (view === "cache") loadCacheHistory(); }
  }, 15000);
}
async function loadGameIcons(extra = []){
  try { const r = await api("/api/gameicons?apps=" + extra.join(",")); ICONS_URL.apps = {...ICONS_URL.apps, ...r.apps}; ICONS_URL.games = r.games; } catch {}
}
function appIcon(app, size = 28){
  const fb = svcIconOwn("steam", size - 10).replace(/'/g, "&#39;").replace(/"/g, "&quot;");
  if (app) return `<img class="gicon" src="/api/appicon/${app}" width="${size}" height="${size}" style="object-fit:cover" alt="" loading="lazy" onerror="this.outerHTML='${fb}'">`;
  return svcIconOwn("steam", size - 10);
}
function gamesTable(list, label){
  if (!list || !list.length) return "";
  const missing = list.filter(g => g.app && !(String(g.app) in ICONS_URL.apps)).map(g => g.app);
  if (missing.length) loadGameIcons(missing);
  const max = Math.max(1, ...list.map(g => g.hit + g.miss));
  return `<div class="panel" style="padding:12px 16px;margin-bottom:14px"><h2 style="margin-bottom:6px">Welche Spiele wurden geladen? <span class="hint">(Steam, Epic, Battle.net · ${esc(label)})</span></h2>
    <div style="overflow:auto"><table class="cachetable"><thead><tr><th>Spiel</th><th>Traffic</th><th>aus dem Cache</th><th>aus dem Internet</th><th style="min-width:180px">Im Cache</th></tr></thead><tbody>
    ${list.map(g => { const tot = g.hit + g.miss, p = tot ? Math.round(g.hit / tot * 100) : 0;
      const cp = g.cached_pct;
      return `<tr><td><div class="row" style="gap:8px;flex-wrap:nowrap">${g.service ? svcIcon(g.service, 18) : appIcon(g.app)}
        <div><b>${esc(g.name)}</b>${g.app ? `<div class="hint mono">App ${g.app}${g.depots > 1 ? " · " + g.depots + " Depots" : ""}</div>` : g.service ? `<div class="hint">${esc(cacheName(g.service))}</div>` : `<div class="hint">Spiel wird ermittelt …</div>`}</div></div></td>
        <td class="mono" title="${p} % davon aus dem Cache">${fmtBytes(tot)}<div class="cachebar" style="margin-top:3px"><i style="width:${(tot / max * 100).toFixed(1)}%;background:linear-gradient(90deg,var(--ok) ${p}%,#8a7a66 ${p}%)"></i></div></td>
        <td class="mono" style="color:var(--ok)">${fmtBytes(g.hit)}</td><td class="mono">${fmtBytes(g.miss)}</td>
        <td>${cp != null ? `<div class="cachebar" title="${fmtBytes(g.stored)} von ${fmtBytes(g.size)} (größter Download des Spiels${g.steam_size ? "; Steam gesamt mit allen Sprachen/DLCs " + fmtBytes(g.steam_size) : ""})${g.evicted ? "\nVerdrängt (geschätzt): " + fmtBytes(g.evicted) : ""}${g.last_used ? "\nZuletzt benutzt: " + new Date(g.last_used * 1000).toLocaleString("de-DE") : ""}"><i style="width:${cp}%;background:${cp < 50 ? "var(--accent)" : "var(--ct)"}"></i></div>
          <div class="hint mono">${cp.toFixed(0)} % · ${fmtBytes(g.stored)} / ${fmtBytes(g.size)}${g.evicted > 1e9 ? ` · <span style="color:var(--accent)">${fmtBytes(g.evicted)} verdrängt</span>` : ""}</div>` : g.app ? `<span class="hint">Größe wird ermittelt …</span>` : `<span class="hint">–</span>`}</td></tr>`; }).join("")}
    </tbody></table></div>
    <div class="hint" style="margin-top:6px">„Im Cache“ = Schätzung, was vom Spiel noch im Cache liegt, bezogen auf seinen größten Download (so viel lädt der Prefill wirklich). Ist der Cache voll, löscht er die am längsten nicht mehr benutzten Daten (nicht die ältesten) – das wird hier nachgerechnet und abgezogen.</div></div>`;
}
function evictHtml(m){
  if (!m) return "";
  const lim = m.limit, ev = m.evictions || [];
  return `<div class="panel" style="padding:12px 16px;margin-bottom:14px"><h2 style="margin-bottom:6px">Was hat der Cache gelöscht? <span class="hint">Schätzung · belegt ≈ ${fmtBytes(m.total)}${lim ? " von " + fmtBytes(lim) : ""}${m.measured ? ` · gemessen ${fmtBytes(m.measured)} am ${new Date(m.measured_at * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"})}` : " · noch nicht genau gemessen"}${m.offset > 1e9 ? ` · davon ${fmtBytes(m.offset)} ältere Daten von vor der Aufzeichnung` : ""}${m.inventory_at ? ` · Inhalt abgeglichen ${new Date(m.inventory_at * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"})}` : ""}</span></h2>
    <div class="hint" style="margin-bottom:8px">Der Lancache löscht still (ohne Logeintrag), sobald das Limit erreicht ist – und zwar die Daten, die am längsten <b>nicht mehr benutzt</b> wurden (LRU), nicht einfach die ältesten. Jedes Laden aus dem Cache zählt als Benutzung. ${m.max_age ? `Außerdem fliegt alles, was ${esc(m.max_age)} lang nicht benutzt wurde. ` : ""}Hier wird das aus dem Verlauf nachgerechnet und mit der genauen Messung abgeglichen (Daten, die der Verlauf nicht kennt, gelten als die ältesten).</div>
    ${ev.length ? `<table class="cachetable"><thead><tr><th>Spiel</th><th>gelöscht</th><th>Grund</th><th>wann (etwa)</th></tr></thead><tbody>${ev.map(e => `<tr><td><div class="row" style="gap:8px;flex-wrap:nowrap">${e.app ? appIcon(e.app, 20) : ""}<b>${esc(e.name)}</b></div></td><td class="mono">${fmtBytes(e.bytes)}</td><td class="hint">${e.why === "abgelaufen" ? "zu lange unbenutzt" : e.why === "nicht mehr im Cache" ? "beim Abgleich nicht gefunden" : "Cache voll"}</td><td class="hint">${new Date(e.t * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"})}</td></tr>`).join("")}</tbody></table>`
      : `<div class="hint">Bisher nichts – ${lim && m.total < lim ? `es sind noch ≈ ${fmtBytes(lim - m.total)} frei` : "der Cache war laut Verlauf noch nicht voll"}.</div>`}</div>`;
}
function savedCard(bytes, label){
  return `<div class="card savedcard"><div class="k">Traffic gespart${label ? " · " + label : ""}</div><div class="v" style="color:var(--ok)">${fmtBytes(bytes || 0)}</div>
    <div class="s">nicht erneut aus dem Internet geladen</div></div>`;
}
async function refreshCache(){
  try { cacheData = await api("/api/cache"); } catch { return; }
  const c = cacheData, h = c.last_hour || {}, liveRange = view === "dash" && metricsRange <= 5;
  const d = (liveRange ? c.last_5m : c.last_day) || {}, rl = liveRange ? "5 Min." : "24 h";
  $("#hlCache").classList.toggle("hidden", !c.container);
  $("#hlNetRow").classList.toggle("hidden", !c.container);
  const cn = c.net || {}, live = cn.tx_bps != null ? cn.tx_bps : (c.rate_bps || 0);
  if (c.container){
    const pct = Math.min(100, live / LINK_BPS * 100);
    if (!lastLive) { tween($("#hlNet"), live, v => fmtRate(v)); $("#hlNetBar").style.width = Math.max(pct, live ? 2 : 0) + "%"; }
    $("#hlNetRow").title = `Lancache an Clients (Netzwerk des Containers, Balken = Anteil an 1 Gbit/s)` + (cn.rx_bps != null ? ` · aus dem Internet ${fmtRate(cn.rx_bps)}` : "");
    const dd = c.last_day || {};
    $("#hlCache").innerHTML = `Lancache: ${dd.hit_ratio != null ? dd.hit_ratio + " % aus dem Cache (24 h)" : "noch keine Daten"}`;
  }
  if (view !== "dash") return;
  if (!c.container){
    $("#cachePanel").innerHTML = `<div class="hint" style="margin-bottom:14px">Lancache: ${esc(c.error || "nicht gefunden")} – Container-Name unter „Automatik &amp; Einstellungen“ eintragen.</div>`;
    return;
  }
  const disk = c.disk ? Math.round(c.disk.used / c.disk.total * 100) : null;
  const svc = svcRows(d.services);
  $("#cachePanel").innerHTML = `<div class="dsect"><h3 class="dhead"><span class="gtile" style="background:#7fb3a6">${gicon("cache", 16)}</span>Lancache <span class="hint">${esc(c.container)}${c.error ? " · " + esc(c.error) : ""}</span></h3>
    <div class="cards cachecards">
      <div class="card"><div class="k">Aus dem Cache (${rl})</div><div class="v" style="color:var(--ok)">${fmtBytes(d.hit_bytes)}</div><div class="s">${d.hit_ratio != null ? d.hit_ratio + " % Trefferquote" : "noch keine Downloads"}</div></div>
      <div class="card"><div class="k">Aus dem Internet (${rl})</div><div class="v">${fmtBytes(d.miss_bytes)}</div><div class="s">${(d.requests || 0).toLocaleString("de-DE")} Anfragen</div></div>
      <div class="card"><div class="k">Durchsatz jetzt</div><div class="v">↑ ${fmtRate(live)}</div><div class="s">${cn.rx_bps != null ? `↓ ${fmtRate(cn.rx_bps)} aus dem Internet · ` : ""}letzte Std. ${fmtBytes((h.hit_bytes||0)+(h.miss_bytes||0))}</div></div>
      ${storageCard(c.storage, c.disk)}
    </div>
    ${svc ? `<div class="panel" style="padding:12px 16px"><h2 style="margin-bottom:6px">Was wurde ausgeliefert? <span class="hint">(letzte ${rl}, nach Dienst)</span> <a href="#" class="hint" style="float:right" onclick="showView('cache');return false">Lancache →</a></h2>
      <div style="overflow:auto"><table class="cachetable"><thead><tr><th>Dienst</th><th>aus dem Cache</th><th>aus dem Internet</th><th>gesamt</th><th>Trefferquote</th><th></th></tr></thead><tbody>${svc}</tbody></table></div></div>`
      : `<div class="hint" style="margin-bottom:14px">In den letzten 24 Stunden wurde nichts über den Lancache geladen.</div>`}
  </div>`;
}

/* ================= Verlaufs-Metriken ================= */
let metricsData = {}, metricsRange = (() => { try { return +localStorage.getItem("gsmRange") || 5; } catch { return 5; } })(), metricsAt = 0;
async function loadMetrics(force){
  if (!force && Date.now() - metricsAt < (metricsRange <= 10 ? 2000 : 30000)) return;
  try { metricsData = await api(`/api/metrics?minutes=${metricsRange}`); metricsAt = Date.now(); } catch {}
}
function spark(vals, color, opts = {}){ return dchart([{vals, color}], opts); }
// „schöne“ Obergrenze für die y-Achse (1/2/2,5/5 × 10^n)
function niceMax(v){
  if (!(v > 0)) return 1;
  const e = Math.pow(10, Math.floor(Math.log10(v))), f = v / e;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * e;
}
function withAxis(svg, max, fmt, h){
  if (!fmt) return svg;
  return `<div class="sparkbox" style="height:${h}px"><div class="yax"><span>${fmt(max)}</span><span>${fmt(max / 2)}</span><span>0</span></div>${svg}</div>`;
}
const AX = {pct: v => Math.round(v) + " %", rate: v => fmtRate(v).replace(" ", "\u202f"), mem: v => fmtMem(Math.round(v)), num: v => String(Math.round(v * 10) / 10), bytes: v => fmtBytes(v)};
// zwei Reihen in einem Diagramm (z. B. Download/Upload) in verschiedenen Farben
function spark2(a, b, colA, colB, opts = {}){ return dchart([{vals: a, color: colA}, {vals: b, color: colB}], opts); }

/* ---- Canvas-Diagramme (Stil D: große Zahl darüber, dünne Spur) – gleiten bei Live-Daten flüssig weiter ---- */
const DCH = {};
let dchSeq = 0;
const cssCol = (() => { const c = {}; return v => {
  if (!String(v).startsWith("var(")) return v;
  return c[v] || (c[v] = getComputedStyle(document.documentElement).getPropertyValue(v.slice(4, -1).trim()).trim() || "#888");
}; })();
function dchart(series, opts = {}){
  const key = opts.key || ("a" + (dchSeq++ % 500));
  const h = opts.h || 34, prev = DCH[key];
  const nums = series.flatMap(x => x.vals).filter(v => v != null);
  const max = niceMax(Math.max(opts.min || 1, ...(nums.length ? nums : [0])));
  const sig = series.map(x => x.vals.length + ":" + x.vals.slice(-3).join(",")).join("|");
  if (!prev || prev.sig !== sig){
    let k = 0;                            // um wie viele Punkte ist die Reihe weitergerückt?
    if (prev && opts.key && prev.series[0]){
      const o = prev.series[0].vals, n = series[0].vals, L = n.length;
      if (o.length === L) for (let j = 1; j <= Math.min(30, L - 3); j++){
        if (o[L - 1] === n[L - 1 - j] && o[L - 2] === n[L - 2 - j] && o[L - 3] === n[L - 3 - j]){ k = j; break; }
      }
    }
    const pre = k ? series.map((x, i) => (prev.series[i] ? prev.series[i].vals.slice(0, k) : [])) : null;
    DCH[key] = {series, pre, max, fmt: opts.fmt, sig, t: performance.now(), shift: k, dur: opts.dur || 2000,
                oldMax: prev ? prev.curMax || prev.max : max, drawn: null};
  } else Object.assign(prev, {series, fmt: opts.fmt});
  return `<div class="dchbox" style="height:${h}px"><canvas class="dch" data-dch="${key}" aria-hidden="true"></canvas></div>`;
}
function dchDraw(cv, now){
  const st = DCH[cv.dataset.dch]; if (!st) return;
  const p = Math.min(1, (now - st.t) / st.dur), e = 1 - Math.pow(1 - p, 2);
  const w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return;
  const tag = st.sig + "|" + w + "x" + h + "|" + (p < 1 ? now : "done");
  if (cv._drawn === tag) return;
  cv._drawn = tag;
  const d = window.devicePixelRatio || 1;
  if (cv.width !== Math.round(w * d) || cv.height !== Math.round(h * d)){ cv.width = Math.round(w * d); cv.height = Math.round(h * d); }
  const x = cv.getContext("2d"); x.setTransform(d, 0, 0, d, 0, 0); x.clearRect(0, 0, w, h);
  const max = st.curMax = st.oldMax + (st.max - st.oldMax) * e;
  const n = Math.max(...st.series.map(s => s.vals.length)), off = st.shift * (1 - p);   // gleichmäßig weiterrücken
  const top = 12, X = i => ((i + off) / Math.max(1, n - 1)) * w, Y = v => h - 2 - (v / max) * (h - top - 3);
  x.strokeStyle = cssCol("var(--line)"); x.lineWidth = 1; x.setLineDash([2, 3]);
  x.beginPath(); x.moveTo(0, Math.round(Y(max / 2)) + .5); x.lineTo(w, Math.round(Y(max / 2)) + .5); x.stroke(); x.setLineDash([]);
  st.series.forEach((sr, si) => {
    const col = cssCol(sr.color); let seg = [], lastPt = null;
    const pre = p < 1 && st.pre ? st.pre[si] || [] : [];
    const flush = () => {
      if (!seg.length) return;
      x.beginPath(); x.moveTo(seg[0][0], seg[0][1]);
      for (let i = 1; i < seg.length; i++){ const a = seg[i - 1], b = seg[i], m = (a[0] + b[0]) / 2; x.bezierCurveTo(m, a[1], m, b[1], b[0], b[1]); }
      x.strokeStyle = col; x.lineWidth = 1.6; x.lineJoin = "round"; x.stroke();
      x.lineTo(seg[seg.length - 1][0], h); x.lineTo(seg[0][0], h); x.closePath();
      x.globalAlpha = .12; x.fillStyle = col; x.fill(); x.globalAlpha = 1;
      lastPt = seg[seg.length - 1]; seg = [];
    };
    pre.forEach((v, i) => v == null ? flush() : seg.push([X(i - pre.length), Y(v)]));
    sr.vals.forEach((v, i) => v == null ? flush() : seg.push([X(i), Y(v)])); flush();
    if (lastPt){ x.beginPath(); x.arc(Math.min(lastPt[0], w - 3), lastPt[1], 3, 0, 7); x.fillStyle = col; x.fill(); }
  });
  if (st.fmt){ x.font = "10px " + (getComputedStyle(cv).fontFamily || "monospace"); x.fillStyle = cssCol("var(--muted)"); x.textAlign = "right"; x.fillText(st.fmt(max), w - 1, 9); }
}
let dchLast = 0;
(function dchLoop(now){
  if (now - dchLast > 33){ dchLast = now; document.querySelectorAll("canvas.dch").forEach(cv => dchDraw(cv, now)); }
  requestAnimationFrame(dchLoop);
})(0);
// Kopfzeile im Stil D: Bezeichnung, große Zahl, kleine Zusatzwerte
function dhead(label, big, sub){
  return `<div class="dhd"><div class="dl">${label}</div><div class="drow"><span class="dbig">${big}</span>${sub ? `<span class="ds">${sub}</span>` : ""}</div></div>`;
}
const C_DOWN = "#4f9dde", C_UP = "#f0a04b";
function netLegend(){ return `<span class="lgd" style="background:${C_DOWN}"></span>Download <span class="lgd" style="background:${C_UP}"></span>Upload`; }
function netPanelCell(m, label){
  const rx = m.rx || [], tx = m.tx || [];
  const rN = rx.filter(v => v != null), tN = tx.filter(v => v != null);
  if (!rN.length && !tN.length) return "";
  const avg = a => a.length ? a.reduce((p, q) => p + q, 0) / a.length : 0;
  return `<div>${dhead(label, `<span style="color:${C_DOWN}">↓ ${fmtRate(rN[rN.length-1] || 0)}</span>`, `<span style="color:${C_UP}">↑ ${fmtRate(tN[tN.length-1] || 0)}</span>`)}
    ${spark2(rx, tx, C_DOWN, C_UP, {min: 100000, h: 64, fmt: AX.rate, key: "net-" + label})}
    <div class="hint" style="font-size:11px">${netLegend()} · Ø ↓ ${fmtRate(avg(rN))} · ↑ ${fmtRate(avg(tN))} · max ↓ ${fmtRate(Math.max(0, ...rN))} · ↑ ${fmtRate(Math.max(0, ...tN))}</div></div>`;
}
const rangeLabel = m => m >= 1440 ? "24 h" : m >= 60 ? (m / 60) + " h" : m <= 10 ? "live " + Math.round(m) + " min" : m + " min";
function hostPanelHtml(){
  const m = metricsData._host;
  if (!m || !m.samples) return "";
  const cpuN = m.cpu.filter(v => v != null), memN = m.mem.filter(v => v != null);
  const avg = a => a.length ? (a.reduce((x, y) => x + y, 0) / a.length).toFixed(1) : "–";
  const mx = a => a.length ? Math.max(...a).toFixed(0) : "–";
  return `<div class="dsect"><h3 class="dhead"><span class="gtile" style="background:#8aa4c8">${gicon("_", 16)}</span>Gesamtlast des Servers <span class="hint">${rangeLabel(m.minutes)}</span></h3>
    <div class="panel"><div class="hostpanel">
      <div>${dhead("CPU", `${cpuN.length ? Math.round(cpuN[cpuN.length-1]) : "–"} %`, `Ø ${avg(cpuN)} % · max ${mx(cpuN)} %`)}${spark(m.cpu, "var(--ct)", {min: 100, h: 64, fmt: AX.pct, key: "h-cpu"})}</div>
      <div>${dhead("RAM belegt", `${memN.length ? Math.round(memN[memN.length-1]) : "–"} %`, `max ${mx(memN)} %`)}${spark(m.mem, "#a78bfa", {min: 100, h: 64, fmt: AX.pct, key: "h-mem"})}</div>
      ${netPanelCell(m, "Internet")}
      ${metricsData._cache && metricsData._cache.samples ? netPanelCell(metricsData._cache, "Lancache") : ""}
      ${ioCells()}
    </div>${ioTable()}${sizesHtml()}</div></div>`;
}
// Größe der installierten Spielserver (vor allem auf der NFS-Freigabe), alle 30 min vom Server neu gemessen
let serverSizes = null, sizesAt = 0;
async function loadSizes(refresh){
  if (!refresh && Date.now() - sizesAt < 60000 && serverSizes && !serverSizes.busy) return;
  sizesAt = Date.now();
  try { serverSizes = await api("/api/serversizes" + (refresh ? "?refresh=1" : "")); } catch {}
}
// kleine Lastbalken je Server (CPU vom Host, RAM-Anteil am Host, Netz an der Leitung) aus den Sekundenwerten
function szLoad(sid){
  const d = lastLive && lastLive.servers && lastLive.servers[sid];
  if (!d || d.running === false) return `<div class="szload off"><span class="hint">läuft nicht${(overview.find(o => o.server.id === sid) || {}).sleeping ? " (Ruhemodus)" : ""}</span></div>`;
  const tot = lastLive.mem_total_mb || 0, net = (d.rx_bps || 0) + (d.tx_bps || 0);
  const cpu = Math.min(100, d.cpu_host || 0), mem = tot && d.mem_mb != null ? Math.min(100, d.mem_mb / tot * 100) : 0, nw = Math.min(100, net / LINK_BPS * 100);
  const bar = (label, pct, txt, cls, tip) => `<div class="szl" title="${esc(tip)}"><span>${label}</span><div class="bar"><i class="${cls}" style="width:${pct > 0 ? Math.max(2, pct) : 0}%"></i></div><b>${txt}</b></div>`;
  return `<div class="szload">
    ${bar("CPU", cpu, (d.cpu_host ?? 0).toFixed(1) + " %", lvl(cpu), "Anteil an der gesamten CPU des Servers")}
    ${bar("RAM", mem, d.mem_mb != null ? fmtMem(d.mem_mb) : "–", lvl(mem), "Arbeitsspeicher des Containers (Balken = Anteil am RAM des Servers)")}
    ${bar("Netz", nw, d.rx_bps != null ? `↓${fmtRate(d.rx_bps)} ↑${fmtRate(d.tx_bps || 0)}` : "–", "net", "Netzwerk des Containers (Balken = Anteil an der Leitung)")}
  </div>`;
}
function sizesHtml(){
  const z = serverSizes;
  if (!z) return "";
  if (!z.items.length) return `<div class="hint" style="margin-top:12px">Größe der Spielserver: ${z.busy || !z.updated ? (z.waiting ? "wartet auf ruhige Phase – " + esc(z.waiting) : "wird mit niedriger Priorität gemessen … (kann einige Minuten dauern)") : "keine Datenordner gefunden"}</div>`;
  const max = Math.max(...z.items.map(x => x.bytes), 1);
  const rows = z.items.map(x => {
    const g = GAMES[x.game] || {};
    const where = x.paths.map(p => `${p.path} (${fmtBytes(p.bytes)}${p.nfs ? ", NFS " + p.device : ", lokal"})`).join("\n");
    return `<div class="szrow" title="${esc(where)}${x.partial ? "\n≈ einige Ordner waren nicht lesbar – Wert eher zu klein" : ""}">
      <span class="szname"><span class="gtile" style="background:${g.color || "#8aa4c8"};width:14px;height:14px">${gicon(x.game, 10)}</span>${esc(x.name)}</span>
      <div class="bar"><i style="width:${Math.max(1, x.bytes / max * 100)}%;background:${x.nfs_bytes ? "var(--ct)" : "#8aa4c8"}"></i></div>
      <b>${x.partial ? "≈ " : ""}${fmtBytes(x.bytes)}</b></div>${szLoad(x.id)}`;
  }).join("");
  const local = z.total - z.nfs_total;
  return `<div class="szbox"><div class="mlab" style="margin-bottom:6px"><span>Installierte Spielserver</span>
      <b>NFS-Freigabe ${fmtBytes(z.nfs_total)}${local > 0 ? ` · lokal ${fmtBytes(local)}` : ""}${z.nfs_free != null ? ` · NAS frei ${fmtBytes(z.nfs_free)}` : ""}</b></div>
    ${rows}
    <div class="hint" style="margin-top:6px">Gemessen ${z.updated ? new Date(z.updated * 1000).toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"}) : "–"} Uhr${z.waiting ? ` · wartet: ${esc(z.waiting)}` : z.busy ? " · misst gerade neu (niedrige Priorität) …" : ""}${!z.busy && z.error ? ` · ${esc(z.error)}` : ""} ·
      <a href="#" id="szRefresh">jetzt neu messen</a> · Balken blau = auf dem NAS, grau = lokal</div></div>`;
}
document.addEventListener("click", async e => {
  const w = e.target.closest && e.target.closest("[data-wake]");
  if (w){
    e.preventDefault(); e.stopPropagation(); w.disabled = true; w.textContent = "weckt …";
    try { await api(`/api/servers/${w.dataset.wake}/wake`, {method: "POST"}); toast("Server wird aufgeweckt"); } catch (err){ toast(err.message, true); }
    setTimeout(refreshDash, 1500); return;
  }
  if (e.target.id !== "szRefresh") return;
  e.preventDefault(); await loadSizes(true); toast("Größen werden neu gemessen – dauert je nach Datenmenge einige Minuten");
  if (view === "dash") $("#hostPanel").innerHTML = hostPanelHtml();
});
AX.ms = v => (v >= 100 ? Math.round(v) : Math.round(v * 10) / 10) + " ms";
AX.pct2 = v => (Math.round(v * 100) / 100) + " %";
function ioCells(){
  const m = metricsData._io;
  if (!m || !m.samples) return "";
  const last = a => { const n = (a || []).filter(v => v != null); return n.length ? n[n.length - 1] : null; };
  const mx = a => { const n = (a || []).filter(v => v != null); return n.length ? Math.max(...n) : null; };
  const cell = (label, vals, color, fmt, min, hint) => `<div title="${esc(hint)}">${dhead(label, last(vals) != null ? fmt(last(vals)) : "–", `max ${mx(vals) != null ? fmt(mx(vals)) : "–"}`)}${spark(vals, color, {min, h: 64, fmt, key: "io-" + label})}</div>`;
  return [
    m.rtt.some(v => v != null) ? cell("NAS-Antwortzeit (NFS)", m.rtt, "#e5a50a", AX.ms, 5, "Durchschnittliche Zeit pro NFS-Anfrage an das NAS. Steigt sie stark (> 20–50 ms), ist das NAS ausgelastet – dann bremsen viele gleichzeitige Zugriffe alles aus.") : "",
    m.nfs.some(v => v != null) ? cell("NAS-Durchsatz", m.nfs, "#4f9dde", AX.rate, 1e6, "Lesen + Schreiben über alle NFS-Mounts") : "",
    m.util.some(v => v != null) ? cell("Lokale Platte ausgelastet", m.util, "#a78bfa", AX.pct, 100, "Anteil der Zeit, in der die lokale Platte beschäftigt ist (100 % = am Limit)") : "",
    m.retrans.some(v => v != null) ? cell("TCP-Wiederholungen", m.retrans, "#e5534b", AX.pct2, 1, "Anteil neu gesendeter TCP-Pakete. Mehr als ~1 % heißt: Verbindung/Switch/NAS überlastet, Pakete gehen verloren.") : "",
  ].join("");
}
function ioTable(){
  const io = lastLive && lastLive.io;
  if (!io || !io.available || !(io.mounts || []).length) return "";
  return `<div style="overflow:auto;margin-top:10px"><table class="cachetable"><thead><tr><th>NAS-Freigabe</th><th>Lesen</th><th>Schreiben</th><th>Anfragen/s</th><th>Antwortzeit</th></tr></thead><tbody>
    ${io.mounts.slice(0, 6).map(m => `<tr><td class="mono" title="${esc(m.src)}">${esc(m.path)}</td><td class="mono">${fmtRate(m.read_bps)}</td><td class="mono">${fmtRate(m.write_bps)}</td><td class="mono">${Math.round(m.ops_s)}</td>
      <td class="mono" style="color:${m.rtt_ms > 50 ? "var(--bad)" : m.rtt_ms > 20 ? "var(--warn,#e5a50a)" : "inherit"}">${m.rtt_ms != null ? m.rtt_ms + " ms" : "–"}</td></tr>`).join("")}
  </tbody></table></div>`;
}
function netCell(m){
  const rx = m.rx || [], tx = m.tx || [];
  const rN = rx.filter(v => v != null), tN = tx.filter(v => v != null);
  if (!rN.length && !tN.length) return "";
  return `<div class="mcell" title="Netzwerk: blau = Download, orange = Upload">${dhead("Netz", `<span style="color:${C_DOWN}">↓ ${fmtRate(rN[rN.length-1] || 0)}</span>`, `<span style="color:${C_UP}">↑ ${fmtRate(tN[tN.length-1] || 0)}</span>`)}${spark2(rx, tx, C_DOWN, C_UP, {min: 20000, h: 44, fmt: AX.rate, key: (m._key || "") + "-net"})}</div>`;
}
function metricsHtml(sid, color){
  const m = metricsData[sid];
  if (!m || !m.samples) return `<div class="hint mstats">Verlauf wird gesammelt …</div>`;
  const cpuNums = m.cpu.filter(v => v != null), memNums = m.mem.filter(v => v != null);
  const cpuAvg = cpuNums.length ? (cpuNums.reduce((a, b) => a + b, 0) / cpuNums.length).toFixed(1) : null;
  return `<div class="mgrid">
      <div class="mcell">${dhead(`Spieler · ${rangeLabel(m.minutes)}`, (m.players || []).filter(v => v != null).slice(-1)[0] ?? 0, `Peak ${m.peak_24h}`)}${spark(m.players, color, {min: 2, h: 44, fmt: AX.num, key: sid + "-pl"})}</div>
      ${cpuNums.length ? `<div class="mcell">${dhead("CPU", `${cpuNums[cpuNums.length-1].toFixed(1)} %`, `Ø ${cpuAvg} %`)}${spark(m.cpu, "var(--ct)", {min: 5, h: 44, fmt: AX.pct, key: sid + "-cpu"})}</div>` : ""}
      ${memNums.length ? `<div class="mcell">${dhead("RAM", fmtMem(memNums[memNums.length-1]), "")}${spark(m.mem, "#a78bfa", {min: 256, h: 44, fmt: AX.mem, key: sid + "-mem"})}</div>` : ""}
      ${netCell({...m, _key: sid})}
    </div>
    ${!cpuNums.length && !memNums.length ? `<div class="hint mstats">CPU/RAM: ${servers.find(x => x.id === sid)?.container ? "Container läuft nicht" : "unter „Bearbeiten“ den Docker-Container zuordnen"}</div>` : ""}
    <div class="hint mstats">Verfügbarkeit 24 h: <b>${m.uptime_24h != null ? m.uptime_24h + " %" : "–"}</b>${m.ping != null ? ` · Ping Ø <b>${m.ping} ms</b>` : ""} · Peak 24 h: <b>${m.peak_24h}</b></div>`;
}

/* ================= Dashboard ================= */
// Sortierung nach Last: Ø CPU im gewählten Zeitraum (ruhiger als der Sekundenwert), dann Spieler; offline ans Ende
function dashScore(o){
  if (!o.online) return -1;
  const m = metricsData[o.server.id], cpu = m && m.cpu ? m.cpu.filter(v => v != null) : [];
  const avg = cpu.length ? cpu.reduce((a, b) => a + b, 0) / cpu.length : ((o.load || {}).cpu_host || 0);
  return Math.round(avg * 2) / 2 + (o.humans || 0) * 0.01;
}
function metricsLine(sid){
  const m = metricsData[sid];
  if (!m || !m.samples) return "";
  return `Verfügbarkeit 24 h <b>${m.uptime_24h != null ? m.uptime_24h + " %" : "–"}</b>${m.ping != null ? ` · Ping Ø <b>${m.ping} ms</b>` : ""} · Spieler-Peak 24 h <b>${m.peak_24h}</b>`;
}
// Logo-Leiste: Spiele, die im Lancache liegen
function cacheGamesHtml(l){
  l = l || [];
  if (!l.length) return "";
  return `<h3 class="pdsec" style="margin-top:22px">Im Lancache <span class="hint">– diese Spiele laden im LAN mit voller Geschwindigkeit</span></h3><div class="cgstrip">${l.map(g => {
    const tip = `${g.name} – ${fmtBytes(g.stored)} im Cache${g.cached_pct != null ? ` (${Math.round(g.cached_pct)} % des Spiels)` : ""}`;
    const pct = g.cached_pct != null ? g.cached_pct : null;
    const img = g.app ? `<img src="/api/applogo/${g.app}" alt="${esc(g.name)}" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'cgname',textContent:this.alt}))">`
      : `<span class="cgsvc">${svcIcon(g.service, 22)}<span class="cgname">${esc(g.name)}</span></span>`;
    return `<span class="cg" title="${esc(tip)}">${img}${pct != null ? `<i style="width:${pct}%"></i>` : ""}</span>`;
  }).join("")}</div>`;
}
async function refreshDash(){
  try { overview = await api("/api/overview"); } catch { return; }
  await Promise.all([loadMetrics(), loadSizes()]);
  if (view === "dash"){ $("#hostPanel").innerHTML = hostPanelHtml(); refreshDashTour(); refreshDashDisk(); }
  renderServerList();
  if (view !== "dash") return;
  $("#dashEmpty").classList.toggle("hidden", overview.length > 0);
  const on = overview.filter(o => o.online).length;
  const pl = overview.reduce((a,o) => a + (o.online ? (o.humans||0) : 0), 0);
  $("#dashSub").textContent = `${on} von ${overview.length} online · ${pl} Spieler gesamt · aktualisiert ${new Date().toLocaleTimeString("de-DE")}`;
  $$("#rangeSeg [data-range]").forEach(b => b.classList.toggle("active", +b.dataset.range === metricsRange));
  const items = [...overview].sort((a, b) => dashScore(b) - dashScore(a) || String(a.server.name).localeCompare(String(b.server.name)));
  $("#dashGrid").innerHTML = `<div class="dsect"><h3 class="dhead"><span class="gtile" style="background:#8aa4c8">${gicon("_", 16)}</span>Server <span class="hint">nach Last sortiert · ${on}/${overview.length} online</span></h3><div class="dash">` + items.map(o => {
    const s = o.server, slots = o.visible_players > 0 ? o.visible_players : (o.max_players || 0);
    const pct = slots ? Math.min(100, Math.round((o.humans||0) / slots * 100)) : 0;
    const mz = o.matchzy && o.matchzy.match ? `${esc(o.matchzy.match.team1||"")} vs ${esc(o.matchzy.match.team2||"")} · ${esc(o.matchzy.match.state||"")}` : (o.matchzy && o.matchzy.unloaded ? "aus (Freizeitmodus)" : o.matchzy && o.matchzy.installed ? "kein Match geladen" : "–");
    return `<div class="dcard" data-id="${esc(s.id)}">
      <div class="top">${gameLogo(gameOf(s))}${led(o)}<b>${esc(s.name)}</b>${o.online ? reachPill(o.reach) : ""}${o.online && o.join ? (o.join.url ? `<a class="joinbtn" href="${esc(o.join.url)}" title="Beitreten: ${esc(o.join.address)}" data-stop>▶ Beitreten</a>` : `<span class="joinbtn" data-copy="${esc(o.join.address)}" title="${esc(o.join.hint)}">⧉ ${esc(o.join.address)}</span>`) : `<span class="hint mono">${esc(s.host)}:${esc(s.port)}</span>`}</div>
      ${o.sleeping ? `<div class="sleeprow"><span class="pill">💤 ${o.sleeping === "pause" ? "pausiert" : "angehalten"} – Ruhemodus</span><button class="small primary opsonly" data-wake="${esc(s.id)}">Aufwecken</button></div>` : ""}
      ${o.online ? `<div class="dbody">${mapThumb(o, gameOf(s))}` + (gameOf(s) === "cs2" ? `
      <div class="kv">
        <span>Map</span><span class="kvmap" title="${esc(o.map)}">${esc((o.workshop && o.workshop.title) || o.map_title || o.map || "?")}</span>
        <span>Modus</span><span>${esc(o.mode ? o.mode.label : "?")}</span>
        <span>Spieler</span><span>${o.humans ?? 0} / ${slots || "?"} · ${o.bots || 0} Bots</span>
        <span>MatchZy</span><span>${mz}</span>
      </div>` : `
      <div class="kv">
        <span>${worldLabel(gameOf(s))}</span><span class="kvmap">${esc(o.track_name || o.map || "–")}</span>
        <span>Spieler</span><span>${o.players_unknown ? "– (Spiel meldet keine Spielerzahl)" : `${o.humans ?? 0}${o.max_players ? " / " + o.max_players : ""}`}</span>
        ${Object.entries(o.extra || {}).filter(([k]) => !["Session","Servername","Strecke"].includes(k)).slice(0, 2).map(([k,v]) => `<span>${esc(k)}</span><span>${esc(v)}</span>`).join("")}
      </div>`) + `</div>
      <div class="bar"><i style="width:${pct}%"></i></div>
      ${problemsHtml(o.problems)}
      <div class="ldwrap" data-ld="${esc(s.id)}">${loadHtml(o.load && lastLive && lastLive.servers[s.id] ? {...o.load, ...lastLive.servers[s.id]} : o.load)}</div>
      ${installHtml(o.install)}
      <div class="hint mstats" data-mwl="${esc(s.id)}">${metricsLine(s.id)}</div>
      ${o.auto && o.auto.capped ? `<span class="pill warn">Slots begrenzt auf ${o.max_players} – SLOTS im Stack erhöhen</span>` : ""}
      ${o.unclaimed ? `<span class="pill warn">Satisfactory: noch nicht beansprucht</span>` : ""}`
      : `${ledOf(o).cls === "warn" ? `<div class="pill warn" style="justify-self:start">Container läuft – Spiel startet oder aktualisiert noch</div>` : ""}<div class="hint">${esc(o.error || (o.online === false ? "offline" : "noch nicht abgefragt"))}</div>${problemsHtml(o.problems)}<div class="ldwrap" data-ld="${esc(s.id)}">${loadHtml(o.load)}</div>${installHtml(o.install)}`}
    </div>`;
  }).join("") + `</div></div>`;
  $$(".dcard").forEach(el => el.onclick = e => {
    if (e.target.closest("[data-stop]")) return;
    const c = e.target.closest("[data-copy]");
    if (c) return copyText(c.dataset.copy);
    selectServer(servers.find(s => s.id === el.dataset.id));
  });
}

/* ================= Server-Ansicht ================= */
const VIEWS = ["dash","players","auto","server","scan","create","users","cache","prefill","storage","game","bot","tour","api"];
function applyGameClasses(s){
  const g = gameOf(s), meta = GAMES[g] || {};
  document.body.classList.toggle("g-other", g !== "cs2");
  document.body.classList.toggle("g-wreckfest", g === "wreckfest");
  document.body.classList.toggle("g-tf2", g === "tf2");
  document.body.classList.toggle("g-ws", g === "cs2" || g === "tf2");
  if (g === "cs2" && typeof wsFavGame !== "undefined" && wsFavGame !== "cs2")
    api("/api/workshop/favorites?game=cs2").then(f => { favs = f; wsFavGame = "cs2"; ["#qMap","#pugMap"].forEach(sel => fillMapSelect(sel)); }).catch(() => {});
  wfLoadedFor = null;
  document.body.classList.toggle("no-console", !meta.console);
  document.body.classList.toggle("no-container", !(dockerOn && s.container));
  try { renderGq(); } catch (e) { console.warn(e); }
}
// Rechte pro Spiel: 1 sehen, 2 bedienen, 3 verwalten, 4 anlegen/löschen
function permFor(game){
  if (!me) return 0;
  if (me.role === "admin") return 4;
  const p = me.perms || {};
  return game in p ? +p[game] : +(p["*"] || 0);
}
const permOf = s => s && s.perm != null ? s.perm : permFor(gameOf(s));
function applyPerm(lvl){
  [2, 3, 4].forEach(n => document.body.classList.toggle("perm-lt" + n, lvl < n));
}
function selectServer(s){
  if (!s) return showView("dash");
  current = s; view = "server"; loadedSettings = {};
  applyPerm(permOf(s));
  { const lv = permOf(s); if ((lv < 2 && ["console", "maps", "match", "settings"].includes(tab)) || (lv < 3 && ["config", "files"].includes(tab))) tab = "overview"; }
  try { resetStatusFields("wird abgefragt …"); $("#playerRows").innerHTML = ""; } catch {}
  $$(".nav [data-view]").forEach(b => b.classList.remove("active"));
  VIEWS.filter(x => x !== "server").forEach(x => $("#view-"+x).classList.add("hidden"));
  $("#view-server").classList.remove("hidden");
  applyGameClasses(s);
  const g = gameOf(s);
  if ((g !== "cs2" && ["match","settings"].includes(tab)) || (!WS_GAMES.has(g) && tab === "maps") || (tab === "container" && !(dockerOn && s.container))) tab = "overview";
  renderServerList();
  $("#svTitle").innerHTML = `${gbadge(gameOf(s))} ${esc(s.name)}`;
  $("#btnWeb").classList.toggle("hidden", !s.web_url);
  setJoin(stateOf(s.id).join);
  $("#svSub").textContent = `${s.host}:${s.port}${s.notes ? " · " + s.notes : ""}${s.auto_slots === false ? " · Automatik aus" : ""}`;
  resetOverview();
  $("#consoleOut").innerHTML = "";
  loadedSettings = {}; $("#settingsBody").innerHTML = "";
  setTab(tab);
}
$$("#tabs [data-tab]").forEach(b => b.onclick = () => setTab(b.dataset.tab));
function setTab(t){
  tab = t;
  $$("#tabs [data-tab]").forEach(b => b.classList.toggle("active", b.dataset.tab===t));
  ["overview","maps","match","console","settings","container","config","files"].forEach(x => $("#tab-"+x).classList.toggle("hidden", x!==t));
  if (t === "files"){ loadSaves(); fbOpen(null); }
  if (t === "config") loadConfigTab();
  stopPoll(); stopCt();
  if (t === "container"){ refreshContainer(); loadSleep(); ctTimer = setInterval(refreshContainer, 5000); }
  if (t === "overview"){ refreshStatus(); pollTimer = setInterval(refreshStatus, 5000); }
  if (t === "maps"){ wsFavGame = wsGame(); renderFavs(); $("#wsResults").innerHTML = ""; $("#wsResHead").classList.add("hidden"); }
  if (t === "match") initMatch();
  if (t === "settings" && !Object.keys(loadedSettings).length) loadSettings();
  if (t === "console"){ renderCmdRef(); if (GAMES[gameOf(current)].console) $("#consoleIn").focus(); }
}
function stopPoll(){ if (pollTimer){ clearInterval(pollTimer); pollTimer = null; } }

/* ---------- Übersicht ---------- */
function resetOverview(){
  ["#stOnline","#stMap","#stPlayers","#stMode","#stMz"].forEach(id => $(id).textContent = "–");
  ["#stVersion","#stMapSub","#stRounds","#stAuto","#stMzSub","#stUpdated","#stHost"].forEach(id => $(id).textContent = "");
  $("#stOnline").style.color = ""; $("#stMapImg").classList.add("hidden");
  $("#playerRows").innerHTML = "";
}
async function refreshStatus(){
  if (!current) return;
  const id = current.id;
  const pr = $("#svProblems"); if (pr) pr.innerHTML = problemsHtml(stateOf(id).problems);
  try {
    const st = await api(`/api/servers/${id}/status`);
    if (!current || current.id !== id) return;
    lastStatus = st;
    setJoin(st.join);
    if (st.hostname && current.name_from_game !== false && st.hostname !== current.name){ current.name = st.hostname; $("#svTitle").innerHTML = `${gbadge(gameOf(current))} ${esc(current.name)}`; }
    if (gqDef()) $("#gqHost").textContent = `${st.hostname || ""} · ${st.map && st.map !== "–" ? "Map " + st.map + " · " : ""}${st.humans ?? "?"} Spieler${st.bots ? " + " + st.bots + " Bots" : ""} / ${st.max_players ?? "?"} Slots`;
    if (gameOf(current) !== "cs2") return renderGeneric(st);
    $("#stMapLabel").textContent = "Map";
    $("#stOnline").textContent = st.hibernating ? "Online (idle)" : "Online";
    $("#stOnline").style.color = "var(--ok)";
    $("#stVersion").textContent = st.version ? "Version " + st.version.split(" ")[0] : "";
    const ws = st.workshop;
    $("#stMap").textContent = (ws && ws.title) || st.map || "?";
    $("#stMap").title = st.map || "";
    $("#stMapSub").textContent = ws ? `Workshop ${ws.id}` : (st.password_set ? "Server-Passwort gesetzt" : "");
    const mimg = (ws && ws.preview) || st.map_image;
    if (mimg){ $("#stMapImg").src = mimg; $("#stMapImg").classList.remove("hidden"); } else $("#stMapImg").classList.add("hidden");
    $("#stMode").textContent = st.mode ? st.mode.label : "?";
    $("#stRounds").textContent = st.maxrounds ? `max. ${st.maxrounds} Runden` : "";
    const slots = st.visible_players > 0 ? st.visible_players : st.max_players;
    $("#stPlayers").textContent = `${st.humans ?? st.players.length} / ${slots ?? "?"}` + (st.bots ? ` · ${st.bots} Bots` : "");
    const a = st.auto || {};
    $("#stAuto").textContent = !a.enabled ? `Automatik aus · max. ${st.max_players}` :
      (a.target ? `Auto: ${a.target} Slots (${a.reason})${a.capped ? " – begrenzt durch SLOTS" : ""}` : `Auto: ${a.reason}`) + (a.bots ? ` · ${a.bots}` : "");
    $("#stAuto").style.color = a.capped ? "var(--accent)" : "";
    const mz = st.matchzy || {};
    $("#stMz").textContent = mz.unloaded ? "aus (Freizeitmodus)" : mz.installed ? (mz.match ? `${mz.match.team1 || "?"} vs ${mz.match.team2 || "?"}` : "bereit") : "nicht erkannt";
    $("#stMzSub").textContent = mz.installed ? (mz.match ? `Status: ${mz.match.state || "?"}${mz.match.score1 != null ? ` · ${mz.match.score1}:${mz.match.score2}` : ""}` : (mz.version ? "v" + mz.version : "kein Match geladen")) : "";
    $("#stHost").textContent = `${st.hostname || ""} · max. ${st.max_players ?? "?"} Slots (Stack) · Bots: ${st.bot_quota ?? "?"}`;
    renderPlayers(st.players);
    renderHistory();
    $("#stUpdated").textContent = "aktualisiert " + new Date().toLocaleTimeString("de-DE");
  } catch(err){
    if (!current || current.id !== id) return;
    const lo = ledOf(stateOf(current.id));
    $("#stOnline").textContent = lo.cls === "warn" ? "Startet …" : "Offline";
    $("#stOnline").style.color = lo.cls === "warn" ? "var(--warn)" : "var(--bad)";
    $("#stVersion").textContent = lo.tip;
    resetStatusFields(err.message);
    $("#stUpdated").textContent = err.message; $("#playerRows").innerHTML = "";
  }
}
// alte Werte eines anderen Servers nicht stehen lassen
function resetStatusFields(msg){
  if (!current) return;
  const g = gameOf(current);
  $("#stMapLabel").textContent = worldLabel(g);
  $("#stMap").textContent = "–"; $("#stMapSub").textContent = ""; $("#stMapImg").classList.add("hidden");
  $("#stMode").textContent = GAMES[g]?.label || ""; $("#stRounds").textContent = "";
  $("#stPlayers").textContent = "–"; $("#stAuto").textContent = "";
  $("#gExtra").innerHTML = `<span class="hint">${esc(msg || "keine Daten")}</span><span></span>`;
  $("#gActHint").textContent = "";
}
function pingClass(p){ return p < 40 ? "ping-good" : p < 90 ? "ping-mid" : "ping-bad"; }
function renderPlayers(list){
  if (!list.length){ $("#playerRows").innerHTML = `<tr><td colspan="8" class="muted">Keine Spieler verbunden.</td></tr>`; return; }
  $("#playerRows").innerHTML = list.map(p => `
    <tr><td class="mono">${p.id}</td>
      <td class="name">${esc(p.name)} ${p.bot ? '<span class="tag">BOT</span>' : ""}</td>
      <td class="mono ${p.bot ? "" : pingClass(p.ping)}">${p.bot ? "–" : p.ping}</td>
      <td class="mono">${p.bot ? "–" : p.loss}</td><td class="mono">${esc(p.time)}</td>
      <td>${esc(p.state)}</td><td class="mono muted">${esc(p.address)}</td>
      <td><button class="small danger" data-kick="${p.id}" data-name="${esc(p.name)}">Kick</button></td></tr>`).join("");
  $$("[data-kick]").forEach(b => b.onclick = async () => {
    if (!confirm(`${b.dataset.name} kicken?`)) return;
    await send(`kickid ${b.dataset.kick}`, `${b.dataset.name} gekickt`);
    setTimeout(refreshStatus, 600);
  });
}

async function send(cmd, okMsg){
  if (!current) return;
  try {
    const r = await api(`/api/servers/${current.id}/command`, {body:{command: cmd}});
    logConsole(cmd, r.output); toast(okMsg || `Gesendet: ${cmd}`);
    return r.output;
  } catch(err){ logConsole(cmd, err.message, true); toast(err.message, true); }
}

$("#quickActions").innerHTML = QUICK.map(([l,c,cls]) => `<button class="${cls||""}" data-cmd="${esc(c)}" title="${esc(c)}">${esc(l)}</button>`).join("");
$$("#quickActions [data-cmd]").forEach(b => b.onclick = () => send(b.dataset.cmd).then(() => setTimeout(refreshStatus, 800)));
$("#mzActions").innerHTML = MZ_ACTIONS.map(([l,c,cls]) => `<button class="${cls||""}" data-cmd="${esc(c)}" title="${esc(c)}">${esc(l)}</button>`).join("");
$$("#mzActions [data-cmd]").forEach(b => b.onclick = () => {
  if (b.classList.contains("danger") && !confirm("Match wirklich abbrechen?")) return;
  send(b.dataset.cmd);
});
$("#btnSay").onclick = async () => {
  const t = $("#sayText").value.trim().replace(/[";]/g, ""); if (!t) return;
  await send(`say ${t}`, "Nachricht gesendet"); $("#sayText").value = "";
};
$("#sayText").addEventListener("keydown", e => { if (e.key === "Enter") $("#btnSay").click(); });
$("#btnExec").onclick = () => { const c = $("#execCfg").value.trim().replace(/[^\w.\-\/]/g, ""); if (c) send(`exec ${c}`); };
$("#btnGoMaps").onclick = () => setTab("maps");

/* ---------- Map wechseln ---------- */
async function changeMap({map, workshop_id, mode}){
  const label = workshop_id ? `Workshop-Map ${workshop_id}` : map;
  if (!confirm(`Map wechseln auf ${label}${mode ? " (" + (settings.modes.find(m => m.key===mode)||{}).label + ")" : ""}?`)) return;
  try {
    const r = await api(`/api/servers/${current.id}/map`, {body:{map, workshop_id, mode: mode || null}});
    logConsole(r.command, r.output);
    toast(`Wechsle auf ${label} …` + (r.expected_players ? ` · ${r.expected_players} Slots` : ""));
    setTimeout(refreshStatus, 6000);
  } catch(err){ toast(err.message, true); }
}
function mapHint(selMap, selMode, el){
  const m = settings.modes.find(x => x.key === selMode);
  const base = (selMap || "").toLowerCase();
  const rule = (settings.map_rules || []).find(r => globMatch(base, r.pattern.toLowerCase()));
  const n = rule ? rule.players : m ? m.players : null;
  el.textContent = n ? `Automatik: ${n} Spieler-Slots (${rule ? "Map-Regel " + (rule.label || rule.pattern) : m.label})` : "Spieleranzahl: wie aktueller Modus";
}
function globMatch(s, p){ return new RegExp("^" + p.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".") + "$").test(s); }

$("#btnChangeMap").onclick = () => {
  const map = ($("#mapCustom").value.trim() || $("#mapSelect").value).replace(/[^\w\-\/]/g, "");
  if (map) changeMap({map, mode: $("#modeSelect").value});
};
["#qMap","#qMode"].forEach(s => $(s).addEventListener("change", () => mapHint($("#qMap").value, $("#qMode").value, $("#qHint"))));
["#mapSelect","#mapCustom","#modeSelect"].forEach(s => $(s).addEventListener("input", () => mapHint($("#mapCustom").value.trim() || $("#mapSelect").value, $("#modeSelect").value, $("#mapHint"))));

/* ---------- Workshop (CS2, TF2 – Server lädt die Map selbst herunter) ---------- */
let wsPage = 1, wsLast = "", wsFavGame = "cs2";
const WS_GAMES = new Set(["cs2", "tf2"]);
const wsGame = () => current && WS_GAMES.has(gameOf(current)) ? gameOf(current) : "cs2";
function wsLoad(id){
  if (wsGame() === "cs2") return changeMap({workshop_id: id, mode: $("#modeSelect").value});
  return send(`changelevel workshop/${String(id).replace(/\D/g, "")}`, `Workshop-Map ${id} wird geladen – der Server lädt sie herunter (kann etwas dauern)`)
    .then(() => setTimeout(refreshStatus, 5000));
}
function wsCard(it, isFav){
  return `<div class="ws">
    ${it.preview ? `<img src="${esc(it.preview)}" loading="lazy" alt="">` : `<img alt="">`}
    <div class="b">
      <div class="t">${esc(it.title)}</div>
      <div class="m">${it.size_mb ? it.size_mb + " MB · " : ""}${it.subscriptions ? it.subscriptions.toLocaleString("de-DE") + " Abos · " : ""}ID ${esc(it.id)}</div>
      <div class="a">
        <button class="small primary" data-wsload="${esc(it.id)}">Laden</button>
        ${isFav ? `<button class="small danger" data-wsunfav="${esc(it.id)}" title="Aus Favoriten entfernen">✕</button>`
                : `<button class="small ${favs.some(f => f.id===it.id) ? "fav" : ""}" data-wsfav="${esc(it.id)}" title="Merken">★</button>`}
        <button class="small" type="button" title="Im Workshop öffnen" data-wsopen="${esc(it.id)}" style="flex:0 0 auto">↗</button>
      </div>
    </div></div>`;
}
function bindWs(root){
  root.querySelectorAll("[data-wsload]").forEach(b => b.onclick = () => wsLoad(b.dataset.wsload));
  root.querySelectorAll("[data-wsfav]").forEach(b => b.onclick = () => addFav(b.dataset.wsfav));
  root.querySelectorAll("[data-wsopen]").forEach(b => b.onclick = () => window.open(`https://steamcommunity.com/sharedfiles/filedetails/?id=${b.dataset.wsopen}`, "_blank", "noopener"));
  root.querySelectorAll("[data-wsunfav]").forEach(b => b.onclick = async () => { favs = await api(`/api/workshop/favorites/${b.dataset.wsunfav}?game=${wsGame()}`, {method:"DELETE"}); renderFavs(true); });
}
async function renderFavs(skipLoad){
  if (!skipLoad){ try { favs = await api(`/api/workshop/favorites?game=${wsGame()}`); } catch {} }
  $("#wsFavs").innerHTML = favs.length ? favs.map(f => wsCard(f, true)).join("") : `<div class="hint">Noch keine Favoriten – über ★ bei einem Suchergebnis merken.</div>`;
  bindWs($("#wsFavs"));
  if (wsGame() === "cs2") ["#qMap","#pugMap"].forEach(sel => fillMapSelect(sel)); else try { gqFillMaps(); } catch {}
}
async function addFav(id){
  try { favs = await api("/api/workshop/favorites", {body:{id, game: wsGame()}}); toast("Gemerkt"); renderFavs(true); $$(`[data-wsfav="${id}"]`).forEach(b => b.classList.add("fav")); }
  catch(err){ toast(err.message, true); }
}
async function wsSearch(more){
  const q = $("#wsQuery").value.trim();
  if (!more){ wsPage = 1; $("#wsResults").innerHTML = `<div class="hint">Suche im Steam Workshop …</div>`; }
  $("#wsResHead").classList.remove("hidden");
  try {
    const res = await api(`/api/workshop/search?q=${encodeURIComponent(q)}&sort=${encodeURIComponent($("#wsSort").value)}&page=${wsPage}&game=${wsGame()}`);
    const html = res.map(it => wsCard(it, false)).join("");
    if (more) $("#wsResults").insertAdjacentHTML("beforeend", html); else $("#wsResults").innerHTML = html || `<div class="hint">Keine Maps gefunden.</div>`;
    bindWs($("#wsResults"));
    $("#wsMore").classList.toggle("hidden", res.length < 10);
  } catch(err){ $("#wsResults").innerHTML = `<div class="hint" style="color:var(--bad)">${esc(err.message)}</div>`; }
}
$("#btnWsSearch").onclick = () => wsSearch(false);
$("#wsQuery").addEventListener("keydown", e => { if (e.key === "Enter") wsSearch(false); });
$("#btnWsMore").onclick = () => { wsPage++; wsSearch(true); };
function wsIdFromInput(){ const v = $("#wsId").value.trim(); const m = v.match(/[?&]id=(\d+)/) || v.match(/^(\d{6,})$/); return m ? m[1] : null; }
$("#btnWsLoadId").onclick = () => { const id = wsIdFromInput(); if (!id) return toast("Bitte Workshop-ID oder Link eingeben", true); wsLoad(id); };
$("#btnWsFavId").onclick = () => { const id = wsIdFromInput(); if (!id) return toast("Bitte Workshop-ID oder Link eingeben", true); addFav(id); };

function fillMapSelect(sel, list){
  const el = $(sel), cur = el.value;
  const maps = list || MAPS;
  el.innerHTML = `<optgroup label="Standard">${maps.map(m => `<option value="${m}">${m}</option>`).join("")}</optgroup>` +
    (favs.length ? `<optgroup label="★ Workshop-Favoriten">${favs.map(f => `<option value="ws:${esc(f.id)}">${esc(f.title)}</option>`).join("")}</optgroup>` : "");
  if (cur) el.value = cur;
}
// Auswahlfelder mit "ws:<id>" verstehen
$("#btnQMap").onclick = () => {
  const v = $("#qMap").value;
  v.startsWith("ws:") ? changeMap({workshop_id: v.slice(3), mode: $("#qMode").value}) : changeMap({map: v, mode: $("#qMode").value});
};

/* ---------- Konsole ---------- */
function logConsole(cmd, out, err=false){
  const box = $("#consoleOut");
  box.insertAdjacentHTML("beforeend",
    `<div><span class="ts">[${new Date().toLocaleTimeString("de-DE")}]</span> <span class="cmd">&gt; ${esc(cmd)}</span></div>` +
    `<div class="${err ? "err" : ""}">${esc(out || (err ? "" : "(keine Ausgabe)"))}</div><br>`);
  box.scrollTop = box.scrollHeight;
}
$("#consoleForm").addEventListener("submit", async e => {
  e.preventDefault();
  const cmd = $("#consoleIn").value.trim(); if (!cmd || !current) return;
  if (cmdHistory[0] !== cmd){ cmdHistory.unshift(cmd); cmdHistory.length = Math.min(cmdHistory.length, 100); try { sessionStorage.setItem("cmdHistory", JSON.stringify(cmdHistory)); } catch {} }
  histIdx = -1; $("#consoleIn").value = "";
  try { const r = await api(`/api/servers/${current.id}/command`, {body:{command: cmd}}); logConsole(cmd, r.output); }
  catch(err){ logConsole(cmd, err.message, true); }
});
$("#consoleIn").addEventListener("keydown", e => {
  if (e.key === "ArrowUp" && histIdx < cmdHistory.length - 1){ histIdx++; $("#consoleIn").value = cmdHistory[histIdx]; e.preventDefault(); }
  if (e.key === "ArrowDown"){ histIdx = Math.max(-1, histIdx - 1); $("#consoleIn").value = histIdx < 0 ? "" : cmdHistory[histIdx]; e.preventDefault(); }
});
$("#btnClear").onclick = () => $("#consoleOut").innerHTML = "";

/* ---------- Einstellungen (Cvars) ---------- */
const TF2_MAPS = ["ctf_2fort","ctf_turbine","ctf_doublecross","ctf_landfall","cp_dustbowl","cp_badlands","cp_granary","cp_process_final","cp_gullywash_final1","cp_snakewater_final1","cp_sunshine","cp_gravelpit","cp_steel","cp_egypt_final","pl_badwater","pl_upward","pl_goldrush","pl_thundermountain","pl_borneo","pl_swiftwater_final1","plr_hightower","plr_pipeline","koth_harvest_final","koth_viaduct","koth_lakeside_final","koth_nucleus","koth_sawmill","arena_well","arena_lumberyard","pd_watergate","sd_doomsday","mvm_decoy","mvm_coaltown","tr_walkway_rc2"];
const TF2_SETTINGS = [
  ["Allgemein", [
    ["hostname","Servername","text"], ["sv_password","Server-Passwort","text"],
    ["sv_visiblemaxplayers","Sichtbare Slots (-1 = alle)","number"], ["sv_alltalk","Alle hören alle (Alltalk)","bool"],
    ["mp_allowspectators","Zuschauer erlaubt","bool"], ["sv_cheats","Cheats","bool"]]],
  ["Runden & Zeit", [
    ["mp_timelimit","Zeitlimit je Map (Min., 0 = aus)","number"], ["mp_winlimit","Siege bis Mapwechsel (0 = aus)","number"],
    ["mp_maxrounds","Max. Runden (0 = aus)","number"], ["mp_waitingforplayers_time","Warten auf Spieler (s)","number"],
    ["mp_enableroundwaittime","Pause zwischen Runden","bool"], ["mp_stalemate_enable","Sudden Death / Patt","bool"]]],
  ["Teams", [
    ["mp_autoteambalance","Automatischer Teamausgleich","bool"], ["mp_teams_unbalance_limit","Max. Teamunterschied","number"],
    ["mp_scrambleteams_auto","Teams automatisch mischen","bool"], ["mp_friendlyfire","Friendly Fire","bool"],
    ["mp_tournament","Turniermodus","bool"]]],
  ["Spiel", [
    ["tf_weapon_criticals","Zufällige Krits","bool"], ["tf_use_fixed_weaponspreads","Feste Waffenstreuung","bool"],
    ["tf_damage_disablespread","Kein zufälliger Schaden","bool"], ["mp_respawnwavetime","Respawn-Welle (s)","number"],
    ["mp_disable_respawn_times","Sofort respawnen","bool"], ["tf_avoidteammates_pushaway","Teamkameraden wegschubsen","bool"]]],
  ["Bots", [
    ["tf_bot_quota","Anzahl Bots","number"], ["tf_bot_difficulty","Bot-Stärke",
      "select", [["0","Leicht"],["1","Normal"],["2","Schwer"],["3","Experte"]]],
    ["tf_bot_quota_mode","Bot-Modus","select", [["normal","fest"],["fill","auffüllen"],["match","je Spieler"]]],
    ["tf_bot_join_after_player","Bots erst mit Spielern","bool"]]],
];
/* ---------- Schnellsteuerung für alle Spiele mit Konsole (live, ohne Neustart) ---------- */
const TF2_MODES = {ctf:"Capture the Flag", cp:"Control Point", pl:"Payload", plr:"Payload Race", koth:"King of the Hill",
  arena:"Arena", pd:"Player Destruction", sd:"Special Delivery", mvm:"Mann vs. Machine", tr:"Training"};
const PFX = {de:"Bombe entschärfen", cs:"Geiselrettung", as:"Assassination", dm:"Deathmatch", dod:"Day of Defeat", gm:"Garry's Mod",
  nmo:"Objective", nms:"Survival", zpo:"Objective", zps:"Survival", fof:"Shootout", bt:"Booty", tw:"Territorial War", lts:"Last Team Standing", ...TF2_MODES};
const GQ_SRC = {limits: [["mp_timelimit","Zeitlimit (Min.)"]]};
const GQ_CSBOTS = {teams: [["","Team: auto"],["t","T"],["ct","CT"]], classes: null,
  diffs: [["","Stärke: Standard"],["0","Leicht"],["1","Normal"],["2","Schwer"],["3","Experte"]],
  add: (n, team, _c, d) => (d ? `bot_difficulty ${d}; ` : "") + Array(n).fill(team ? `bot_add_${team}` : "bot_add").join("; "),
  kick: "bot_quota 0; bot_kick", quota: q => `bot_quota ${q}`,
  hint: "Bots brauchen Wegpunkte (.nav) – auf den Standard-Maps vorhanden."};
const GQ = {
  tf2: {maps: TF2_MAPS, groupBy: TF2_MODES, quick: [
      ["Warten auf Spieler beenden","mp_waitingforplayers_cancel 1","primary"], ["Match neu starten","mp_restartgame 1"],
      ["Runde neu starten","mp_restartround 1"], ["Teams mischen","mp_scrambleteams 1"],
      ["Turniermodus an","mp_tournament 1; mp_tournament_restart"], ["Turniermodus aus","mp_tournament 0; mp_restartgame 1"],
      ["Bots neu spawnen","tf_bot_kill all"]],
    bots: {teams: [["","Team: auto"],["red","RED"],["blue","BLU"]],
      classes: [["","Klasse: zufällig"],...["scout","soldier","pyro","demoman","heavyweapons","engineer","medic","sniper","spy"].map(c => [c,c])],
      diffs: [["","Stärke: Standard"],["easy","Leicht"],["normal","Normal"],["hard","Schwer"],["expert","Experte"]],
      add: (n, t, c, d) => `tf_bot_add ${[n, c, t, d].filter(Boolean).join(" ")}`, kick: "tf_bot_quota 0; tf_bot_kick all",
      quota: q => `tf_bot_quota_mode fill; tf_bot_quota ${q}`,
      hint: "Bots brauchen ein Navmesh – auf allen offiziellen Maps vorhanden, auf Community-Maps oft nicht (dann stehen sie still)."},
    limits: [["mp_timelimit","Zeitlimit (Min.)"],["mp_winlimit","Siege"],["mp_maxrounds","Runden"]],
    hint: "Der Spielmodus ergibt sich bei TF2 aus der Map (ctf_ Capture the Flag, cp_ Control Point, pl_ Payload, koth_ King of the Hill …)."},
  hl2dm: {...GQ_SRC, maps: ["dm_lockdown","dm_overwatch","dm_powerhouse","dm_resistance","dm_runoff","dm_steamlab","dm_underpass","halls3"],
    quick: [["Match neu starten","mp_restartgame 1","primary"]],
    mode: {title: "Spielart", opts: [["0","Deathmatch (jeder gegen jeden)"],["1","Team-Deathmatch (Combine vs. Rebellen)"]], cmd: v => `mp_teamplay ${v}`, reload: true},
    limits: [["mp_timelimit","Zeitlimit (Min.)"],["mp_fraglimit","Fraglimit"]]},
  dods: {...GQ_SRC, maps: ["dod_anzio","dod_argentan","dod_avalanche","dod_colmar","dod_donner","dod_flash","dod_jagd","dod_kalt","dod_palermo"],
    quick: [["Match neu starten","mp_restartgame 1","primary"], ["Teamausgleich an","mp_autoteambalance 1"], ["Teamausgleich aus","mp_autoteambalance 0"]],
    limits: [["mp_timelimit","Zeitlimit (Min.)"],["mp_winlimit","Siege"]]},
  l4d: {maps: ["l4d_hospital01_apartment","l4d_garage01_alleys","l4d_smalltown01_caves","l4d_airport01_greenhouse","l4d_farm01_hilltop","l4d_river01_docks",
      "l4d_vs_hospital01_apartment","l4d_vs_smalltown01_caves","l4d_vs_airport01_greenhouse","l4d_vs_farm01_hilltop"],
    quick: [["Nur-Bot-Spiel erlauben","sb_all_bot_game 1"], ["Nur-Bot-Spiel aus","sb_all_bot_game 0"]],
    mode: {title: "Spielmodus", opts: [["coop","Kampagne (Koop)"],["versus","Versus"],["survival","Survival"]], cmd: v => `mp_gamemode ${v}`, reload: true},
    hint: "Versus-Maps beginnen mit l4d_vs_. Überlebende ohne Spieler übernehmen automatisch Bots."},
  l4d2: {maps: ["c1m1_hotel","c2m1_highway","c3m1_plankcountry","c4m1_milltown_a","c5m1_waterfront","c6m1_riverbank","c7m1_docks","c8m1_apartment",
      "c9m1_alleys","c10m1_caves","c11m1_greenhouse","c12m1_hilltop","c13m1_alpinecreek","c14m1_junkyard"],
    quick: [["Nur-Bot-Spiel erlauben","sb_all_bot_game 1"], ["Nur-Bot-Spiel aus","sb_all_bot_game 0"]],
    mode: {title: "Spielmodus", opts: [["coop","Kampagne (Koop)"],["realism","Realismus"],["versus","Versus"],["survival","Survival"],["scavenge","Scavenge"]],
      cmd: v => `mp_gamemode ${v}`, reload: true},
    hint: "Überlebende ohne Spieler übernehmen automatisch Bots."},
  garrysmod: {maps: ["gm_construct","gm_flatgrass"],
    mode: {title: "Gamemode", opts: [["sandbox","Sandbox"],["terrortown","Trouble in Terrorist Town (falls installiert)"],["prop_hunt","Prop Hunt (falls installiert)"],["murder","Murder (falls installiert)"]],
      cmd: v => `gamemode ${v}`, reload: true},
    bots: {teams: null, classes: null, diffs: null, add: n => Array(n).fill("bot").join("; "),
      kick: 'lua_run for _,b in ipairs(player.GetBots()) do b:Kick("") end', quota: null, hint: "Bots stehen in Sandbox nur herum."}},
  nmrih: {...GQ_SRC, maps: ["nmo_broadway","nmo_chinatown","nmo_toxteth","nmo_suzhou","nmo_cabin","nmo_fema","nmo_junction","nmo_lakeside","nms_isolated","nms_midwest"],
    quick: [["Runde neu starten","mp_restartgame 1","primary"]], hint: "nmo_ = Objective, nms_ = Survival – der Modus ergibt sich aus der Map."},
  zps: {...GQ_SRC, maps: ["zpo_biotec","zps_cinema","zps_harvest"], quick: [["Runde neu starten","mp_restartgame 1","primary"]]},
  fof: {...GQ_SRC, maps: ["fof_fistful","fof_depot","fof_robertlee","fof_tortuga"], quick: [["Runde neu starten","mp_restartgame 1","primary"]],
    bots: {teams: null, classes: null, diffs: null, add: null, kick: "fof_sv_bot_slotpct 0; fof_sv_bot_dynamicjoin 0",
      quota: q => `fof_sv_bot_dynamicjoin ${q ? 1 : 0}; fof_sv_bot_slotpct ${(Math.min(100, q) / 100).toFixed(2)}`,
      quotaLabel: ["Bots füllen", "% der Slots (0 = aus)"], quotaDefault: 40,
      hint: "FoF-Bots kommen, sobald ein Spieler drauf ist, und gehen nach und nach, wenn mehr Spieler joinen."},
    limits: [["mp_timelimit","Zeitlimit (Min.)"],["mp_fraglimit","Fraglimit"]]},
  pvkii: {...GQ_SRC, maps: ["bt_island"], quick: [["Runde neu starten","mp_restartgame 1","primary"]]},
  asrd: {maps: ["lobby"], quick: [], hint: "Missionen startet der Lobby-Leiter im Spiel."},
  cs16: {maps: ["de_dust2","de_dust","de_inferno","de_nuke","de_train","de_aztec","de_cbble","de_prodigy","de_chateau","de_vertigo","de_piranesi","de_torn","de_storm","de_airstrip","de_survivor",
      "cs_office","cs_italy","cs_assault","cs_militia","cs_estate","cs_747","cs_backalley","cs_havana","cs_siege","as_oilrig"],
    quick: [["Runde neu starten","sv_restartround 1","primary"], ["Match neu starten","sv_restart 1"], ["Friendly Fire an","mp_friendlyfire 1"], ["Friendly Fire aus","mp_friendlyfire 0"]],
    bots: GQ_CSBOTS, limits: [["mp_timelimit","Zeitlimit (Min.)"],["mp_maxrounds","Runden"],["mp_winlimit","Siege"]]},
  czero: {maps: ["de_dust2_cz","de_dust_cz","de_aztec_cz","de_cbble_cz","de_chateau_cz","de_inferno_cz","de_piranesi_cz","de_prodigy_cz","de_train_cz",
      "cs_italy_cz","cs_office_cz","cs_militia_cz","cs_havana_cz","cs_siege_cz","as_oilrig"],
    quick: [["Runde neu starten","sv_restartround 1","primary"], ["Match neu starten","sv_restart 1"], ["Friendly Fire an","mp_friendlyfire 1"], ["Friendly Fire aus","mp_friendlyfire 0"]],
    bots: GQ_CSBOTS, limits: [["mp_timelimit","Zeitlimit (Min.)"],["mp_maxrounds","Runden"],["mp_winlimit","Siege"]]},
  dod: {hint: "DoD hat keine eingebauten Bots – die alten Bot-Plugins (Sturmbot …) laufen mit dem heutigen Steam-HLDS nicht mehr.", maps: ["dod_anzio","dod_avalanche","dod_caen","dod_charlie","dod_chemille","dod_donner","dod_escape","dod_falaise","dod_flash","dod_flugplatz","dod_forest",
      "dod_glider","dod_jagd","dod_kalt","dod_kraftstoff","dod_merderet","dod_northbound","dod_saints","dod_sturm","dod_switch","dod_vicenza","dod_zalec"],
    quick: [["Runde neu starten","sv_restartround 1","primary"]], limits: [["mp_timelimit","Zeitlimit (Min.)"]]},
  tfc: {maps: ["2fort","well","rock2","dustbowl","hunted","warpath","cz2","avanti","badlands","crossover2","epicenter","flagrun","push","ravelin","casbah"],
    quick: [], limits: [["mp_timelimit","Zeitlimit (Min.)"],["mp_fraglimit","Fraglimit"]]},
  hldm: {maps: ["crossfire","bounce","datacore","frenzy","gasworks","lambda_bunker","rapidcore","snark_pit","stalkyard","subtransit","undertow","boot_camp"],
    quick: [], mode: {title: "Spielart", opts: [["0","Deathmatch"],["1","Teamplay"]], cmd: v => `mp_teamplay ${v}`, reload: true},
    limits: [["mp_timelimit","Zeitlimit (Min.)"],["mp_fraglimit","Fraglimit"]]},
  svencoop: {maps: ["hl_c00","svencoop1","svencoop2","stadium4"], quick: [], limits: [["mp_timelimit","Zeitlimit (Min.)"]]},
  minecraft: {noMaps: true, noExec: true, quick: [
      ["Tag","time set day","primary"], ["Nacht","time set night"], ["Wetter klar","weather clear"], ["Regen","weather rain"],
      ["Speichern","save-all"], ["Alle heilen","effect give @a minecraft:instant_health 1 10"]],
    mode: {title: "Spielmodus (alle Spieler + Standard)", opts: [["survival","Überleben"],["creative","Kreativ"],["adventure","Abenteuer"],["spectator","Zuschauer"]],
      cmd: v => `defaultgamemode ${v}`, extra: v => `gamemode ${v} @a`},
    mode2: {title: "Schwierigkeit", opts: [["peaceful","Friedlich"],["easy","Leicht"],["normal","Normal"],["hard","Schwer"]], cmd: v => `difficulty ${v}`}},
};
let gqMapsFor = null, gqMapsLive = [];
const gqDef = () => current && GQ[gameOf(current)];
function gqThumb(m){
  const g = gameOf(current);
  const f = /^ws:/.test(m || "") && favs.find(x => "ws:" + x.id === m);
  $("#gqThumb").innerHTML = f ? `<img src="${esc(f.preview || "")}" alt="" referrerpolicy="no-referrer">` : m ? (mapThumb({map: m}, g) || "") : "";
}
function gqFillMaps(){
  const d = gqDef(); if (!d || d.noMaps) return;
  const all = [...new Set([...(d.maps || []), ...gqMapsLive])];
  const groups = {};
  all.forEach(m => { const k = m.includes("_") ? m.split("_")[0] : ""; (groups[k] = groups[k] || []).push(m); });
  const sel = $("#gqMap"), keep = sel.value;
  sel.innerHTML = Object.entries(groups).sort((a, b) => b[1].length - a[1].length).map(([k, ms]) =>
    `<optgroup label="${esc(PFX[k] || k || "Maps")}">${ms.sort().map(m => `<option value="${m}">${m}</option>`).join("")}</optgroup>`).join("") +
    (WS_GAMES.has(gameOf(current)) && favs.length && wsFavGame === gameOf(current) ? `<optgroup label="★ Workshop-Favoriten">${favs.map(f => `<option value="ws:${esc(f.id)}">${esc(f.title)}</option>`).join("")}</optgroup>` : "");
  if (keep && all.includes(keep)) sel.value = keep;
  gqThumb(sel.value);
}
async function gqLoadMaps(quiet){
  if (!current) return;
  try {
    const r = await api(`/api/servers/${current.id}/command`, {body: {command: "maps *"}});
    const found = [...new Set([...(r.output || "").matchAll(/([A-Za-z0-9_\-\.]+)\.bsp\b/g)].map(m => m[1]))];
    gqMapsLive = found; gqMapsFor = current.id; gqFillMaps();
    if (!quiet) toast(`${found.length} Maps auf dem Server gefunden`);
  } catch (e) { if (!quiet) toast("Maps konnten nicht gelesen werden: " + e.message, true); }
}
function gqSend(cmd, msg){ return send(cmd, msg).then(o => { setTimeout(refreshStatus, 1500); return o; }); }
function gqMapNow(){ return lastStatus && lastStatus.map && lastStatus.map !== "–" ? String(lastStatus.map).split("/").pop().replace(/\.bsp$/, "") : ""; }
function renderGq(){
  const d = gqDef(), g = current && gameOf(current);
  const needRcon = !!(d && GAMES[g]?.rcon && !current.has_password);
  document.body.classList.toggle("g-gq", !!(d && (GAMES[g]?.console || GAMES[g]?.rcon)));
  if (!d) return;
  $("#gqNeedRcon").classList.toggle("hidden", !needRcon);
  $$(".gqonly .gqbody").forEach(x => x.classList.toggle("hidden", needRcon));
  if (needRcon) return;
  $("#gqActions").innerHTML = (d.quick || []).map(([l, c, cls]) => `<button class="${cls || ""}" data-cmd="${esc(c)}" title="${esc(c)}">${esc(l)}</button>`).join("");
  $$("#gqActions [data-cmd]").forEach(b => b.onclick = () => gqSend(b.dataset.cmd));
  const md = d.mode;
  $("#gqModeBox").classList.toggle("hidden", !md);
  if (md){
    $("#gqModeTitle").textContent = md.title;
    $("#gqMode").innerHTML = md.opts.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join("") +
      (d.mode2 ? `<optgroup label="${esc(d.mode2.title)}">${d.mode2.opts.map(([v, l]) => `<option value="2:${v}">${esc(l)}</option>`).join("")}</optgroup>` : "");
    $("#gqModeHint").textContent = md.reload ? "Wird mit einem Mapwechsel aktiv (aktuelle Map wird neu geladen, Spieler bleiben verbunden)." : "";
  }
  const b = d.bots;
  $("#gqBotBox").classList.toggle("hidden", !b);
  if (b){
    const opt = (sel, arr) => { $(sel).classList.toggle("hidden", !arr); if (arr) $(sel).innerHTML = arr.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join(""); };
    opt("#gqBotTeam", b.add && b.teams); opt("#gqBotClass", b.add && b.classes); opt("#gqBotDiff", b.add && b.diffs);
    ["#gqBotN", "#btnGqBotAdd"].forEach(x => $(x).classList.toggle("hidden", !b.add));
    $("#gqQuotaRow").classList.toggle("hidden", !b.quota);
    const ql = b.quotaLabel || ["Auffüllen auf", "Spieler (0 = aus)"];
    $("#gqQuotaRow .hint:first-child").textContent = ql[0]; $("#gqQuotaRow .hint:nth-of-type(2)").textContent = ql[1];
    $("#gqBotQuota").max = b.quotaLabel ? 100 : 31; $("#gqBotQuota").value = b.quotaDefault || 10;
    $("#gqBotHint").textContent = b.hint || "";
  }
  $("#gqLimitBox").classList.toggle("hidden", !d.limits);
  $("#gqLimits").innerHTML = (d.limits || []).map(([cv, l]) => `<span class="hint">${esc(l)}</span><input data-gqlim="${cv}" type="number" min="0" style="width:70px" placeholder="–">`).join("") +
    (d.limits ? `<button id="btnGqLimits">Setzen</button>` : "");
  const bl = $("#btnGqLimits");
  if (bl) bl.onclick = () => {
    const cmds = $$("[data-gqlim]").filter(i => i.value !== "").map(i => `${i.dataset.gqlim} ${Math.max(0, parseInt(i.value) || 0)}`);
    if (cmds.length) gqSend(cmds.join("; "), "Limits gesetzt");
  };
  $("#gqExecBox").classList.toggle("hidden", !!d.noExec);
  $("#gqPwBox").classList.toggle("hidden", !(GAMES[g]?.rcon || g === "tf2"));
  $("#gqJoinPw").value = current.join_pw ?? (lastStatus && lastStatus.join_password) ?? "";
  $("#gqMapPanel").classList.toggle("hidden", !!d.noMaps);
  $("#gqMapAdd").classList.toggle("hidden", !GAMES[g]?.rcon || !current.container);
  if (GAMES[g]?.rcon && current.container && window.gqWsPoll) window.gqWsPoll();
  $("#gqMapHint").textContent = d.hint || "";
  if (gqMapsFor !== current.id){
    gqMapsLive = []; gqMapsFor = current.id; if (!d.noMaps) gqLoadMaps(true);
    if (WS_GAMES.has(g) && wsFavGame !== g) api(`/api/workshop/favorites?game=${g}`).then(f => { favs = f; wsFavGame = g; gqFillMaps(); }).catch(() => {});
  }
  gqFillMaps();
}
(function initGq(){
  if (!$("#gqActions")) return;
  const go = m => { if (/^ws:\d+$/.test(m || "")) return wsLoad(m.slice(3)); m = (m || "").replace(/[^\w\-\.\/]/g, ""); if (m) gqSend(`changelevel ${m}`, `Map wechselt zu ${m}`); };
  $("#gqMap").addEventListener("change", () => gqThumb($("#gqMap").value));
  $("#gqMapCustom").addEventListener("input", () => gqThumb($("#gqMapCustom").value.trim() || $("#gqMap").value));
  $("#btnGqMap").onclick = () => go($("#gqMapCustom").value.trim() || $("#gqMap").value);
  $("#btnGqRandMap").onclick = () => { const o = $$("#gqMap option").map(x => x.value).filter(m => !/^(mvm|tr)_/.test(m) && m !== gqMapNow()); if (o.length) go(o[Math.floor(Math.random() * o.length)]); };
  $("#btnGqReload").onclick = () => { const m = gqMapNow(); m ? go(m) : toast("Aktuelle Map unbekannt", true); };
  $("#btnGqMapsLoad").onclick = () => gqLoadMaps(false);
  const mapDone = r => { toast(`${r.maps.length ? "Map " + r.maps.join(", ") : r.files + " Datei(en)"} hinzugefügt${r.note ? " – " + r.note : ""}`, !!r.note);
    gqLoadMaps(true).then(() => { if (r.maps[0]) { $("#gqMap").value = r.maps[0]; gqThumb(r.maps[0]); } }); };
  $("#btnGqMapUrl").onclick = async () => {
    const url = $("#gqMapUrl").value.trim(); if (!url) return toast("Link zur Map (.bsp, .bsp.bz2 oder .zip) einfügen", true);
    $("#btnGqMapUrl").disabled = true; toast("Map wird geladen …");
    try { mapDone(await api(`/api/servers/${current.id}/maps/add`, {body: {url}})); $("#gqMapUrl").value = ""; }
    catch (e) { toast(e.message, true); } finally { $("#btnGqMapUrl").disabled = false; }
  };
  let wsTimer = null;
  const wsPoll = async () => {
    clearTimeout(wsTimer);
    if (!current) return;
    let j; try { j = await api(`/api/servers/${current.id}/maps/workshop`); } catch { return; }
    if (!j.step) { $("#gqWsState").textContent = ""; return; }
    $("#gqWsState").innerHTML = `${esc(j.step)}${j.total ? ` · ${j.done}/${j.total}` : ""}${j.current && j.running ? ` · ${esc(j.current)}` : ""}${j.maps && j.maps.length ? ` · ✓ ${j.maps.length} Map(s)` : ""}${j.errors && j.errors.length ? ` · <span title="${esc(j.errors.join("\n"))}" style="color:var(--bad)">${j.errors.length} Problem(e)</span>` : ""}`;
    if (j.running) wsTimer = setTimeout(wsPoll, 3000); else if (j.maps && j.maps.length) gqLoadMaps(true);
  };
  $("#btnGqWs").onclick = async () => {
    const ids = $("#gqWsIds").value.trim(); if (!ids) return toast("Workshop-Link, ID oder Kollektion einfügen", true);
    try { await api(`/api/servers/${current.id}/maps/workshop`, {body: {ids}}); $("#gqWsIds").value = ""; toast("Workshop-Import läuft im Hintergrund"); wsPoll(); }
    catch (e) { toast(e.message, true); }
  };
  window.gqWsPoll = wsPoll;
  $("#gqMapFile").onchange = async () => {
    const f = $("#gqMapFile").files[0]; if (!f) return;
    toast(`${f.name} wird hochgeladen …`);
    try {
      const r = await fetch(`/api/servers/${current.id}/maps/upload?name=${encodeURIComponent(f.name)}`, {method: "POST", body: f});
      const j = await r.json(); if (!r.ok) throw new Error(j.detail || r.statusText); mapDone(j);
    } catch (e) { toast(e.message, true); }
    $("#gqMapFile").value = "";
  };
  $("#btnGqMode").onclick = async () => {
    const d = gqDef(); let v = $("#gqMode").value;
    if (v.startsWith("2:")) { v = v.slice(2); return gqSend(d.mode2.cmd(v), `${d.mode2.title}: ${v}`); }
    const cmds = [d.mode.cmd(v)];
    if (d.mode.extra) cmds.push(d.mode.extra(v));
    const m = gqMapNow();
    if (d.mode.reload && m) cmds.push(`changelevel ${m}`);
    gqSend(cmds.join("; "), `${d.mode.title}: ${$("#gqMode").selectedOptions[0].textContent}`);
  };
  $("#btnGqBotAdd").onclick = () => {
    const b = gqDef()?.bots; if (!b) return;
    const n = Math.max(1, Math.min(24, parseInt($("#gqBotN").value) || 1));
    gqSend(b.add(n, b.teams ? $("#gqBotTeam").value : "", b.classes ? $("#gqBotClass").value : "", b.diffs ? $("#gqBotDiff").value : ""), `${n} Bot(s) hinzugefügt`);
  };
  $("#btnGqBotKick").onclick = () => { const b = gqDef()?.bots; if (b && confirm("Alle Bots entfernen?")) gqSend(b.kick, "Bots entfernt"); };
  $("#btnGqBotQuota").onclick = () => {
    const b = gqDef()?.bots; if (!b?.quota) return;
    const q = Math.max(0, Math.min(b.quotaLabel ? 100 : 31, parseInt($("#gqBotQuota").value) || 0));
    gqSend(b.quota(q), q ? `Bots: ${q}${b.quotaLabel ? " %" : ""}` : "Bot-Auffüllen aus");
  };
  $("#btnGqSay").onclick = async () => {
    const t = $("#gqSayText").value.trim().replace(/[";]/g, ""); if (!t) return;
    await send(gameOf(current) === "minecraft" ? `say ${t}` : `say ${t}`, "Nachricht gesendet"); $("#gqSayText").value = "";
  };
  $("#gqSayText").addEventListener("keydown", e => { if (e.key === "Enter") $("#btnGqSay").click(); });
  $("#btnGqRcon").onclick = async () => {
    if (!confirm("Steuerung aktivieren? Der Server wird dafür EINMAL neu gestartet (RCON-Passwort + Online-Modus). Danach geht alles live.")) return;
    try {
      await api(`/api/servers/${current.id}/rcon-enable`, {body: {password: ""}});
      current.has_password = true; toast("Steuerung aktiv – Server startet einmal neu"); renderGq();
    } catch (e) { toast(e.message, true); }
  };
  const setPw = async pw => {
    try {
      const r = await api(`/api/servers/${current.id}/join-password`, {body: {password: pw}});
      current.join_pw = r.password; $("#gqJoinPw").value = r.password;
      toast(r.note || (r.password ? `Server-Passwort: ${r.password}` : "Server ohne Passwort"), !!r.note); setTimeout(refreshStatus, 1000);
    } catch (e) { toast(e.message, true); }
  };
  $("#btnGqJoinPw").onclick = () => setPw($("#gqJoinPw").value.trim());
  $("#btnGqJoinPwStd").onclick = () => setPw("hinkel");
  $("#btnGqExec").onclick = () => { const c = $("#gqExecCfg").value.trim().replace(/[^\w.\-\/]/g, ""); if (c) send(`exec ${c}`); };
})();
const settingsFor = () => (current && gameOf(current) === "tf2") ? TF2_SETTINGS : SETTINGS;
let allSettings = SETTINGS.flatMap(([, f]) => f);
function inputFor([name, , type, opts]){
  if (type === "bool") return `<div class="switch"><input type="checkbox" data-cvar="${name}"><span class="muted" style="font-size:12px">aktiv</span></div>`;
  if (type === "select") return `<select data-cvar="${name}"><option value=""></option>${opts.map(([v,l]) => `<option value="${v}">${esc(l)}</option>`).join("")}</select>`;
  return `<input data-cvar="${name}" type="text" ${type==="number"?'inputmode="decimal"':""} spellcheck="false">`;
}
function renderSettings(){
  const S = settingsFor();
  allSettings = S.flatMap(([, f]) => f);
  const tf2 = current && gameOf(current) === "tf2";
  $("#settingsBody").innerHTML = (tf2 ? `<div class="panel"><h2>Map wechseln</h2><div class="row">
      <select id="tf2Map" style="flex:1">${TF2_MAPS.map(m => `<option value="${m}">${m}</option>`).join("")}</select>
      <input id="tf2MapCustom" placeholder="oder eigener Mapname" style="flex:1"><button class="primary" id="btnTf2Map">Map wechseln</button></div>
      <div class="hint" style="margin-top:6px">Der Spielmodus ergibt sich bei TF2 aus der Map (ctf_ = Capture the Flag, cp_ = Control Point, pl_ = Payload, koth_ = King of the Hill …).</div></div>` : "") +
    S.map(([group, fields]) => `
    <div class="panel"><h2>${esc(group)}</h2><div class="settings-grid">
      ${fields.map(f => `<div class="field" id="f-${f[0]}"><label>${esc(f[1])} <code>${f[0]}</code></label>${inputFor(f)}</div>`).join("")}
    </div></div>`).join("");
  $$("[data-cvar]").forEach(el => { el.addEventListener("input", () => markChanged(el)); el.addEventListener("change", () => markChanged(el)); });
  const mb = $("#btnTf2Map");
  if (mb) mb.onclick = async () => {
    const m = ($("#tf2MapCustom").value.trim() || $("#tf2Map").value).replace(/[^\w\-]/g, "");
    if (m) await send(`changelevel ${m}`, `Map wechselt zu ${m}`);
  };
}
function readField(el){ return el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value.trim(); }
function normalize(name, v){
  const f = allSettings.find(x => x[0] === name);
  if (v == null) return v;
  if (f && f[2] === "bool") return (v === "true" || (v !== "false" && parseFloat(v) !== 0 && v !== "")) ? "1" : "0";
  if (f && f[2] === "number" && !isNaN(parseFloat(v))) return String(parseFloat(v));
  return v;
}
function markChanged(el){ const n = el.dataset.cvar; $("#f-"+n).classList.toggle("changed", normalize(n, readField(el)) !== loadedSettings[n]); }
async function loadSettings(){
  if (!current) return;
  renderSettings();
  try {
    const vals = await api(`/api/servers/${current.id}/cvars`, {body:{names: allSettings.map(f => f[0])}});
    loadedSettings = {};
    for (const [n, v] of Object.entries(vals)){
      const el = document.querySelector(`[data-cvar="${n}"]`); if (!el) continue;
      if (v == null){ el.disabled = true; el.title = "Wert konnte nicht gelesen werden"; continue; }
      const nv = normalize(n, v); loadedSettings[n] = nv;
      if (el.type === "checkbox") el.checked = nv === "1"; else el.value = nv;
    }
  } catch(err){ toast("Einstellungen konnten nicht geladen werden: " + err.message, true); }
}
$("#btnReload").onclick = loadSettings;
$("#btnSave").onclick = async () => {
  const cmds = [];
  $$("[data-cvar]").forEach(el => {
    if (el.disabled) return;
    const n = el.dataset.cvar, v = normalize(n, readField(el));
    if (v === loadedSettings[n]) return;
    const f = allSettings.find(x => x[0] === n);
    cmds.push(f[2] === "text" ? `${n} "${v.replace(/[";]/g, "")}"` : `${n} ${v.replace(/[^\w.\-]/g, "")}`);
  });
  if (!cmds.length) return toast("Keine Änderungen");
  await send(cmds.join("; "), `${cmds.length} Einstellung(en) übernommen`);
  await loadSettings();
};

/* ================= Wettkampf ================= */
let preset = "wingman", bo = 1;
const assign = {};            // steamid -> 1 | 2
let mapOrder = [];            // ausgewählte Maps in Reihenfolge
let matchCvars = {};
async function initMatch(){
  try { players = await api("/api/players"); } catch {}
  applyPreset(preset, true);
  loadHistory();
}
$$("#presetSeg [data-preset]").forEach(b => b.onclick = () => applyPreset(b.dataset.preset));
function applyPreset(p, keepAssign){
  preset = p;
  const pr = presets[p]; if (!pr) return;
  $$("#presetSeg [data-preset]").forEach(b => b.classList.toggle("active", b.dataset.preset === p));
  $("#presetHint").innerHTML = `${esc(pr.label)}: ${pr.players_per_team} Spieler pro Team, ${esc(pr.cvars.mp_maxrounds)} Runden (MR${pr.cvars.mp_maxrounds/2}), Overtime ${pr.cvars.mp_overtime_enable === "1" ? "an" : "aus"}, Start ab ${esc(pr.cvars.matchzy_minimum_ready_required)} Spielern mit <code>.ready</code>. Der Server wird dafür auf <code>game_type ${pr.game_type}</code> / <code>game_mode ${pr.game_mode}</code> gestellt.`;
  matchCvars = {...pr.cvars};
  renderCvars();
  mapOrder = pr.maps.slice(0, 1);
  renderMapPool();
  fillMapSelect("#pugMap", pr.maps);
  if (!keepAssign) Object.keys(assign).forEach(k => delete assign[k]);
  renderTeams();
}
function renderTeams(){
  const ppt = presets[preset] ? presets[preset].players_per_team : 5;
  const f = $("#poolFilter").value.trim().toLowerCase();
  const chip = (p, cls) => `<span class="chip ${cls}" data-sid="${esc(p.steamid)}" title="${esc(p.steamid)}">${p.avatar ? `<img src="${esc(p.avatar)}" alt="">` : ""}${esc(p.name)}</span>`;
  for (const t of [1,2]){
    const list = players.filter(p => assign[p.steamid] === t);
    $(`#t${t}Chips`).innerHTML = list.map(p => chip(p, "t"+t)).join("") || `<span class="hint">Noch keine Spieler – unten anklicken</span>`;
    $(`#t${t}Count`).textContent = `${list.length} / ${ppt} Spieler` + (list.length > ppt ? " – zu viele!" : "");
    $(`#t${t}Count`).style.color = list.length > ppt ? "var(--bad)" : "";
  }
  const pool = players.filter(p => p.steamid && (!f || p.name.toLowerCase().includes(f) || p.steamid.includes(f)));
  $("#poolChips").innerHTML = pool.map(p => chip(p, assign[p.steamid] ? "t" + assign[p.steamid] : "")).join("") ||
    `<span class="hint">Keine Spieler gespeichert – unter „Spieler &amp; SteamIDs“ anlegen.</span>`;
  $$("#t1Chips .chip, #t2Chips .chip, #poolChips .chip").forEach(c => c.onclick = () => {
    const id = c.dataset.sid, cur = assign[id];
    if (!cur) assign[id] = 1; else if (cur === 1) assign[id] = 2; else delete assign[id];
    renderTeams();
  });
}
$("#poolFilter").addEventListener("input", renderTeams);
$("#btnPoolClear").onclick = () => { Object.keys(assign).forEach(k => delete assign[k]); renderTeams(); };
$("#btnPoolShuffle").onclick = () => {
  const ids = players.filter(p => assign[p.steamid]).map(p => p.steamid);
  const pick = ids.length ? ids : players.filter(p => p.steamid).map(p => p.steamid);
  pick.sort(() => Math.random() - .5);
  Object.keys(assign).forEach(k => delete assign[k]);
  const ppt = presets[preset].players_per_team;
  pick.slice(0, ppt*2).forEach((id, i) => assign[id] = i % 2 ? 2 : 1);
  renderTeams();
};
$("#btnGoPlayers").onclick = () => showView("players");
$$("#boSeg [data-bo]").forEach(b => b.onclick = () => {
  bo = +b.dataset.bo;
  $$("#boSeg [data-bo]").forEach(x => x.classList.toggle("active", x === b));
  const pool = presets[preset].maps;
  if (mapOrder.length < bo) mapOrder = [...new Set([...mapOrder, ...pool])].slice(0, bo);
  renderMapPool();
});
function renderMapPool(){
  const pool = [...new Set([...presets[preset].maps, ...mapOrder])];
  $("#mMaps").innerHTML = pool.map(m => {
    const i = mapOrder.indexOf(m);
    return `<label><input type="checkbox" data-map="${esc(m)}" ${i >= 0 ? "checked" : ""}> ${esc(m)}${i >= 0 ? ` <span class="pill">${i+1}</span>` : ""}</label>`;
  }).join("");
  $$("#mMaps [data-map]").forEach(c => c.onchange = () => {
    const m = c.dataset.map;
    mapOrder = c.checked ? [...mapOrder, m] : mapOrder.filter(x => x !== m);
    renderMapPool();
  });
  const hint = $("#mSkipVeto").checked ? `${mapOrder.length} Map(s) ausgewählt, gespielt werden die ersten ${bo}` : `Veto aus ${mapOrder.length} Maps`;
  $("#mMaps").insertAdjacentHTML("beforeend", `<div class="hint">${hint}${mapOrder.length < bo ? ` – mindestens ${bo} nötig!` : ""}</div>`);
}
$("#mSkipVeto").onchange = renderMapPool;
$("#btnMMapAdd").onclick = () => { const m = $("#mMapAdd").value.trim().replace(/[^\w\-\/]/g, ""); if (m && !mapOrder.includes(m)) { mapOrder.push(m); $("#mMapAdd").value = ""; renderMapPool(); } };
function renderCvars(){
  $("#mCvars").innerHTML = Object.entries(matchCvars).map(([k,v]) => `<tr>
    <td><input data-ck value="${esc(k)}" class="mono"></td><td><input data-cv value="${esc(v)}" class="mono" style="max-width:120px"></td>
    <td><button class="small danger" data-cdel="${esc(k)}">✕</button></td></tr>`).join("");
  $$("#mCvars [data-cdel]").forEach(b => b.onclick = () => { readCvars(); delete matchCvars[b.dataset.cdel]; renderCvars(); });
}
function readCvars(){
  const out = {};
  $$("#mCvars tr").forEach(tr => { const k = tr.querySelector("[data-ck]").value.trim(), v = tr.querySelector("[data-cv]").value.trim(); if (k) out[k] = v; });
  matchCvars = out; return out;
}
$("#btnCvarAdd").onclick = () => { readCvars(); matchCvars[""] = ""; renderCvars(); };
function matchBody(){
  const team = t => ({name: $(`#t${t}Name`).value.trim() || `Team ${t}`, players: players.filter(p => assign[p.steamid] === t).map(p => p.steamid)});
  return {preset, team1: team(1), team2: team(2), num_maps: bo, maplist: mapOrder, players_per_team: presets[preset].players_per_team,
          skip_veto: $("#mSkipVeto").checked, side_type: $("#mSide").value, clinch_series: $("#mClinch").checked,
          cvars: readCvars(), public_url: settings.public_url || location.origin};
}
$("#btnMatchPreview").onclick = async () => {
  try { const cfg = await api(`/api/servers/${current.id}/match/preview`, {body: matchBody()}); $("#mPreview").textContent = JSON.stringify(cfg, null, 2); $("#mPreview").classList.remove("hidden"); }
  catch(err){ toast(err.message, true); }
};
$("#btnMatchStart").onclick = async () => {
  const b = matchBody(), ppt = b.players_per_team;
  const warn = [];
  if (b.team1.players.length !== ppt || b.team2.players.length !== ppt) warn.push(`Teams haben ${b.team1.players.length} bzw. ${b.team2.players.length} statt ${ppt} Spieler.`);
  if (/localhost|127\.0\.0\.1/.test(b.public_url)) warn.push("Die Adresse des Tools ist „localhost“ – der CS2-Server kann die Config so nicht laden. Unter „Automatik & Modi“ die LAN-Adresse eintragen.");
  if (!confirm(`Match ${b.team1.name} vs ${b.team2.name} auf ${current.name} laden?\n\n${warn.join("\n")}`)) return;
  try {
    const r = await api(`/api/servers/${current.id}/match`, {body: b});
    logConsole(`matchzy_loadmatch_url "${r.url}"`, r.output);
    toast("Match geladen – Spieler können joinen und .ready schreiben");
    $("#mPreview").textContent = JSON.stringify(r.config, null, 2); $("#mPreview").classList.remove("hidden");
    loadHistory();
  } catch(err){ toast(err.message, true); }
};
$("#btnPug").onclick = async () => {
  const v = $("#pugMap").value, pr = presets[preset];
  if (!confirm(`${pr.label}-PUG auf ${v.startsWith("ws:") ? "Workshop-Map" : v} starten?\nMatchZy lässt alle joinen, Start ab ${pr.cvars.matchzy_minimum_ready_required} Spielern mit .ready.`)) return;
  try {
    const r = await api(`/api/servers/${current.id}/pug`, {body: v.startsWith("ws:") ? {preset, map: "x", workshop_id: v.slice(3)} : {preset, map: v}});
    logConsole(r.command, r.output); toast("PUG wird gestartet …");
  } catch(err){ toast(err.message, true); }
};
async function loadHistory(){
  let list = [];
  try { list = await api("/api/matches"); } catch {}
  $("#mHistory").innerHTML = list.length ? list.slice(0, 15).map(m => `<tr>
    <td>${fmtDate(m.created)}</td><td>${esc(m.server_name)}</td><td>${esc(m.team1)} vs ${esc(m.team2)}</td>
    <td class="mono">${esc(m.maps.slice(0, m.num_maps).join(", "))}</td>
    <td><button class="small" data-reload="${esc(m.token)}">auf diesem Server laden</button> <a href="/match/${esc(m.token)}.json" target="_blank"><button class="small" type="button">JSON</button></a></td></tr>`).join("")
    : `<tr><td colspan="5" class="muted">Noch keine Matches.</td></tr>`;
  $$("[data-reload]").forEach(b => b.onclick = async () => {
    try { const r = await api(`/api/matches/${b.dataset.reload}/reload/${current.id}`, {method:"POST"}); logConsole("matchzy_loadmatch_url", r.output); toast("Match erneut geladen"); }
    catch(err){ toast(err.message, true); }
  });
}

/* ================= Spieler-Verwaltung ================= */
let plTimer = null, plMerge = null;
// Mehrfachauswahl in der Spielerliste
const plSel = new Set(); let plVisible = [];
function plSelInfo(){
  $("#plSelCount").textContent = `${plSel.size} ausgewählt`;
  $$("[data-plbulk]").forEach(b => b.disabled = !plSel.size);
  const all = $("#plSelAll"); if (all){ const vis = plVisible.filter(id => plSel.has(id)).length; all.checked = !!plVisible.length && vis === plVisible.length; all.indeterminate = vis > 0 && vis < plVisible.length; }
}
$("#plSelAll").onchange = e => { plVisible.forEach(id => e.target.checked ? plSel.add(id) : plSel.delete(id)); renderPlayerRows(); };
$$("[data-plbulk]").forEach(b => b.onclick = async () => {
  const a = b.dataset.plbulk, n = plSel.size; if (!n) return;
  const txt = {lan: "als „auf der LAN“ markieren", nolan: "als „nicht auf der LAN“ markieren", lanauto: "LAN-Erkennung wieder automatisch (nach IP)",
               delete: "löschen", ignore: "löschen und nicht mehr automatisch erfassen"}[a];
  if (!confirm(`${n} Spieler ${txt}?`)) return;
  try { players = await api("/api/players-bulk", {body: {ids: [...plSel], action: a}}); if (a === "delete" || a === "ignore") plSel.clear(); toast("Erledigt"); }
  catch (e) { toast(e.message, true); }
  renderPlayerRows();
});
$("#plUnignore").onclick = async e => { e.preventDefault(); if (!confirm("Ignorierliste leeren? Gelöschte Spieler werden dann wieder erfasst, sobald sie auftauchen.")) return;
  try { await api("/api/players-ignored/clear", {method: "POST"}); toast("Ignorierliste geleert"); } catch (er) { toast(er.message, true); } };
async function loadPlayers(){
  clearTimeout(plTimer);
  try { players = await api("/api/players"); } catch(err){ toast(err.message, true); }
  renderPlayerRows();
  if (view === "players") plTimer = setTimeout(() => { if (!document.activeElement || !document.activeElement.dataset.rename) loadPlayers(); }, 15000);
}
const agoTxt = t => { if (!t) return "–"; const d = Date.now() / 1000 - t; return d < 120 ? "gerade" : d < 3600 ? `${Math.round(d / 60)} min` : d < 86400 ? `${Math.round(d / 3600)} h` : new Date(t * 1000).toLocaleDateString("de-DE"); };
function renderPlayerRows(){
  const f = $("#plFilter").value.trim().toLowerCase(), onlyOn = $("#plOnlyOn").checked;
  const hay = p => [p.name, p.nick, p.ts_name, p.steamid, p.lan_ip, p.wan_ip, ...(p.names || [])].filter(Boolean).join(" ").toLowerCase();
  const list = players.filter(p => (!f || hay(p).includes(f)) && (!onlyOn || (p.online || []).length));
  const on = players.filter(p => (p.online || []).length);
  $("#plCount").textContent = `${players.length} gesamt · ${on.length} online`;
  // Übersicht: wer ist wo
  const bySrv = {};
  on.forEach(p => p.online.forEach(o => { (bySrv[o.sid] = bySrv[o.sid] || {o, list: []}).list.push(p); }));
  $("#plOnline").innerHTML = Object.values(bySrv).map(({o, list}) => `<div class="plsrv">${gameTile(o.game, 16)}<b>${esc(o.server)}</b><span class="hint">${list.length}</span>
    <div>${list.map(p => `<span class="pill ok" title="${esc([p.steamid, p.lan_ip, p.wan_ip].filter(Boolean).join(" · "))}">${esc(p.name)}</span>`).join(" ")}</div></div>`).join("") || `<div class="hint">Gerade ist niemand auf einem Server.</div>`;
  plVisible = list.map(p => p.id);
  for (const id of [...plSel]) if (!players.some(p => p.id === id)) plSel.delete(id);
  $("#plRows").innerHTML = list.length ? list.map(p => `<tr class="${(p.online || []).length ? "plon" : ""}${plMerge === p.id ? " plmerge" : ""}${plSel.has(p.id) ? " plsel" : ""}">
    <td class="plck"><input type="checkbox" data-plsel="${esc(p.id)}" ${plSel.has(p.id) ? "checked" : ""} style="width:auto"></td>
    <td class="plwho"><div class="plwho-in">${p.avatar ? `<img class="avatar" src="${esc(p.avatar)}" alt="">` : `<span class="avatar"></span>`}
      <div class="plnm"><input value="${esc(p.nick || "")}" placeholder="${esc(p.name)}" data-rename="${esc(p.id)}">
      <div class="hint plalias">${(p.names || []).slice(-3).map(esc).join(", ")}${p.ts_name ? ` <span class="pill" title="TeamSpeak">🎧 ${esc(p.ts_name)}</span>` : ""}</div></div></div></td>
    <td class="plst">${(p.online || []).map(o => `<span class="pill ok">${gameTile(o.game, 12)} ${esc(o.server)}</span>`).join(" ") || `<span class="hint">${esc(Object.values(p.servers || {}).sort((a, b) => b.last - a.last).slice(0, 1).map(x => x.name).join("") || "–")}</span>`}
      <div class="hint" title="${p.last_seen ? new Date(p.last_seen * 1000).toLocaleString("de-DE") : ""}">zuletzt ${agoTxt(p.last_seen)}</div></td>
    <td class="plsteam">${p.steamid ? `<a class="mono" href="https://steamcommunity.com/profiles/${esc(p.steamid)}" target="_blank" rel="noopener">${esc(p.steamid)}</a>` : `<span class="hint">keine SteamID</span>`}
      ${(p.admin_eff || []).length ? `<div><span class="pill warn" title="${esc((p.admin_eff || []).map(g => g === "*" ? "alle Spiele" : (GAMES[g]?.label || g)).join(", "))}${p.user ? " · Konto " + esc(p.user) : ""}">★ Admin ${(p.admin_eff || []).includes("*") ? "alle" : (p.admin_eff || []).map(g => GAMES[g]?.short || g).join(", ")}</span></div>` : ""}</td>
    <td class="plnet"><label class="hint pllan"><input type="checkbox" data-pllan="${esc(p.id)}" ${p.on_lan ? "checked" : ""} style="width:auto" title="${p.lan_manual ? "von Hand gesetzt" : "automatisch nach IP"}"> LAN${p.lan_manual ? ` <a href="#" data-pllanauto="${esc(p.id)}" title="wieder automatisch nach IP">(auto)</a>` : ""}</label>
      <div class="mono hint">${p.lan_ip ? `🏠 ${esc(p.lan_ip)}` : ""}${p.lan_ip && p.wan_ip ? "<br>" : ""}${p.wan_ip ? `🌐 ${esc(p.wan_ip)}` : ""}</div></td>
    <td class="plact"><button class="small" data-pledit="${esc(p.id)}" title="bearbeiten">✎</button><button class="small" data-plmerge="${esc(p.id)}" title="${plMerge ? (plMerge === p.id ? "Zusammenführen abbrechen" : "in den markierten Eintrag übernehmen") : "mit anderem Eintrag zusammenführen"}">⇄</button><button class="small danger" data-pldel="${esc(p.id)}">✕</button></td></tr>`).join("")
    : `<tr><td colspan="6" class="muted">${players.length ? "Keine Treffer." : "Noch keine Spieler – sie erscheinen automatisch, sobald jemand auf einen Server kommt."}</td></tr>`;
  $$("[data-plsel]").forEach(c => c.onchange = () => { c.checked ? plSel.add(c.dataset.plsel) : plSel.delete(c.dataset.plsel); c.closest("tr").classList.toggle("plsel", c.checked); plSelInfo(); });
  plSelInfo();
  $$("[data-rename]").forEach(i => i.onchange = async () => { players = await api(`/api/players/${encodeURIComponent(i.dataset.rename)}`, {method: "PUT", body: {name: i.value.trim()}}); toast("Nickname gespeichert"); renderPlayerRows(); });
  $$("[data-pledit]").forEach(b => b.onclick = () => openPlayerEdit(b.dataset.pledit, b.closest("tr")));
  $$("[data-pllan]").forEach(c => c.onchange = async () => { try { players = await api(`/api/players/${encodeURIComponent(c.dataset.pllan)}/lan`, {body: {lan: c.checked}}); renderPlayerRows(); } catch (e) { toast(e.message, true); } });
  $$("[data-pllanauto]").forEach(a => a.onclick = async e => { e.preventDefault(); try { players = await api(`/api/players/${encodeURIComponent(a.dataset.pllanauto)}/lan`, {body: {lan: null}}); renderPlayerRows(); } catch (er) { toast(er.message, true); } });
  $$("[data-pldel]").forEach(b => b.onclick = async () => { if (!confirm("Spieler löschen? (Taucht er wieder auf einem Server auf, wird er neu erfasst – dauerhaft: Haken setzen und „Löschen + nicht mehr erfassen“.)")) return; players = await api(`/api/players/${encodeURIComponent(b.dataset.pldel)}`, {method: "DELETE"}); renderPlayerRows(); });
  $$("[data-plmerge]").forEach(b => b.onclick = async () => {
    const id = b.dataset.plmerge;
    if (!plMerge || plMerge === id){ plMerge = plMerge === id ? null : id; if (plMerge) toast("Jetzt beim zweiten Eintrag derselben Person auf ⇄ klicken"); return renderPlayerRows(); }
    const a = players.find(p => p.id === plMerge), c = players.find(p => p.id === id);
    if (!confirm(`„${c.name}“ in „${a.name}“ übernehmen? (ein Eintrag bleibt übrig)`)) return;
    try { players = await api(`/api/players/${encodeURIComponent(plMerge)}/merge`, {body: {other: id}}); toast("Zusammengeführt"); } catch (e){ toast(e.message, true); }
    plMerge = null; renderPlayerRows();
  });
}
$("#plOnlyOn").addEventListener("change", renderPlayerRows);
let plUsers = null;
async function openPlayerEdit(id, tr){
  const p = players.find(x => x.id === id); if (!p) return;
  const nx = tr.nextElementSibling;
  if (nx && nx.classList.contains("pledit")) { nx.remove(); return; }
  if (plUsers === null){ try { plUsers = ((await api("/api/users")).users || []).map(u => u.username).filter(Boolean); } catch { plUsers = []; } }
  const games = [...new Set(servers.map(s => gameOf(s)))].filter(g => ["cs2", "wreckfest", "valheim", "tf2"].includes(g) || true);
  const adm = new Set(p.admin || []);
  const row = document.createElement("tr"); row.className = "pledit";
  row.innerHTML = `<td colspan="6"><div class="pleditbox">
    <div><label>Nickname</label><input data-pe="nick" value="${esc(p.nick || "")}" placeholder="${esc(p.name)}"></div>
    <div><label>SteamID (SteamID64, STEAM_0:…, [U:1:…] oder Profil-Link)</label><input data-pe="steamid" class="mono" value="${esc(p.steamid || "")}"></div>
    <div><label>Notiz</label><input data-pe="notes" value="${esc(p.notes || "")}"></div>
    <div><label>Tool-Konto (dessen Rechte gelten als Admin-Rechte)</label><div class="row" style="gap:6px"><select data-pe="user"><option value="">–</option>${(plUsers || []).map(u => `<option ${u === p.user ? "selected" : ""}>${esc(u)}</option>`).join("")}</select><button class="small" data-penew title="Neues Konto (nur ansehen) anlegen und verknüpfen – Passwort wird einmal angezeigt">+ neues Konto</button></div></div>
    <div style="grid-column:1/-1"><label>Admin auf den Servern (braucht SteamID)</label><div class="row" style="flex-wrap:wrap;gap:12px">
      <label class="hint"><input type="checkbox" data-pea="*" ${adm.has("*") ? "checked" : ""} style="width:auto"> alle Spiele</label>
      ${games.map(g => `<label class="hint"><input type="checkbox" data-pea="${esc(g)}" ${adm.has(g) ? "checked" : ""} style="width:auto"> ${esc(GAMES[g]?.label || g)}</label>`).join("")}</div>
      <div class="hint">Wird automatisch eingetragen bei CS2 (CounterStrikeSharp + MatchZy), Wreckfest (admin_steam_ids, ab nächstem Neustart) und Valheim (adminlist.txt).</div></div>
    <div style="grid-column:1/-1" class="row"><button class="primary small" data-pesave>Speichern</button><button class="small" data-pecancel>Abbrechen</button></div></div></td>`;
  tr.after(row);
  row.querySelector("[data-pecancel]").onclick = () => row.remove();
  row.querySelector("[data-penew]").onclick = async () => {
    try {
      const r = await api(`/api/players/${encodeURIComponent(id)}/account`, {body: {}});
      players = r.players; plUsers = null; renderPlayerRows();
      prompt(`Konto angelegt – Zugangsdaten weitergeben (Passwort wird nur jetzt angezeigt).\nRechte unter „Benutzer“ anpassen.`, `Benutzer: ${r.username}  Passwort: ${r.password}`);
    } catch (e){ toast(e.message, true); }
  };
  row.querySelector("[data-pesave]").onclick = async () => {
    const body = {}; row.querySelectorAll("[data-pe]").forEach(i => body[i.dataset.pe] = i.value.trim());
    body.admin = [...row.querySelectorAll("[data-pea]")].filter(c => c.checked).map(c => c.dataset.pea);
    try { players = await api(`/api/players/${encodeURIComponent(id)}`, {method: "PATCH", body}); toast("Spieler gespeichert"); renderPlayerRows(); }
    catch (e){ toast(e.message, true); }
  };
}
$("#btnPlAddName").onclick = async () => {
  const name = $("#plName").value.trim() || $("#plInput").value.trim(); if (!name) return toast("Namen eintragen", true);
  try { players = await api("/api/players/new", {body: {name}}); toast(`${name} angelegt`); $("#plInput").value = ""; $("#plName").value = ""; renderPlayerRows(); }
  catch (e){ toast(e.message, true); }
};
$("#btnPlSyncAdmins").onclick = async () => {
  try { const r = await api("/api/players/sync-admins", {method: "POST"}); $("#plAdminLog").textContent = r.done.length ? r.done.join(" · ") : "alles aktuell"; }
  catch (e){ toast(e.message, true); }
};
$("#plFilter").addEventListener("input", renderPlayerRows);
$("#btnPlAdd").onclick = async () => {
  const input = $("#plInput").value.trim(); if (!input) return;
  $("#btnPlAdd").disabled = true;
  try {
    const r = await api("/api/players", {body:{input, name: $("#plName").value.trim() || null}});
    players = r.players; renderPlayerRows();
    toast(`${r.player.name} (${r.player.steamid}) gespeichert` + (r.offline ? " – Steam nicht erreichbar, Name bitte selbst eintragen" : ""));
    $("#plInput").value = ""; $("#plName").value = "";
  } catch(err){ toast(err.message, true); }
  finally { $("#btnPlAdd").disabled = false; }
};
$("#plInput").addEventListener("keydown", e => { if (e.key === "Enter") $("#btnPlAdd").click(); });
$("#btnPlImport").onclick = async () => {
  const sid = $("#plImportSrv").value; if (!sid) return;
  $("#plImportRes").textContent = "Frage Server ab …";
  try {
    const r = await api(`/api/servers/${sid}/players/import`, {method:"POST"});
    players = r.players; renderPlayerRows();
    $("#plImportRes").textContent = r.found.length ? `${r.found.length} SteamID(s) gefunden, ${r.added} neu gespeichert.`
      : `Der Server hat keine SteamIDs geliefert (versucht: ${r.tried.join(", ")}). Dann bitte Profil-Links eintragen.`;
  } catch(err){ $("#plImportRes").textContent = err.message; }
};

/* ================= Automatik ================= */
function renderAuto(){
  $("#modeRows").innerHTML = settings.modes.map((m, i) => `<tr data-i="${i}">
    <td><input data-f="label" value="${esc(m.label)}"><input data-f="key" type="hidden" value="${esc(m.key)}"></td>
    <td><input data-f="game_type" value="${m.game_type}" inputmode="numeric" style="max-width:70px"></td>
    <td><input data-f="game_mode" value="${m.game_mode}" inputmode="numeric" style="max-width:70px"></td>
    <td><input data-f="players" value="${m.players}" inputmode="numeric" style="max-width:70px"></td>
    <td><button class="small danger" data-mdel="${i}">✕</button></td></tr>`).join("");
  $("#ruleRows").innerHTML = (settings.map_rules || []).map((r, i) => `<tr data-i="${i}">
    <td><input data-f="pattern" value="${esc(r.pattern)}" class="mono"></td>
    <td><input data-f="label" value="${esc(r.label || "")}"></td>
    <td><input data-f="players" value="${r.players}" inputmode="numeric" style="max-width:70px"></td>
    <td><button class="small danger" data-rdel="${i}">✕</button></td></tr>`).join("");
  $("#setPublicUrl").value = settings.public_url || "";
  $("#setPublicUrl").placeholder = "leer = " + location.origin;
  $("#setInterval").value = settings.watch_interval || 10;
  $("#setScanInterval").value = settings.scan_interval ?? 15;
  $("#setScanSubnets").value = settings.scan_subnets || "";
  $("#setGamesBase").value = settings.games_base || "/mnt/grohlan";
  $("#setCacheContainer").value = settings.cache_container || "";
  $("#setHostnamePattern").value = settings.hostname_pattern ?? "Groh CS #{nr} {mode}";
  $("#setNamesPattern").value = settings.names_pattern ?? "Groh {game} #{nr} {mode}";
  $("#setInternetHost").value = settings.internet_host || "";
  $("#setAutoBots").checked = settings.auto_bots !== false; $("#setAutoMz").checked = settings.auto_matchzy !== false;
  $("#setContainerDns").value = settings.container_dns || "";
  $("#setPortRange").value = settings.port_range || "27000-27100";
  $$("[data-mdel]").forEach(b => b.onclick = () => { readAuto(); settings.modes.splice(+b.dataset.mdel, 1); renderAuto(); });
  $$("[data-rdel]").forEach(b => b.onclick = () => { readAuto(); settings.map_rules.splice(+b.dataset.rdel, 1); renderAuto(); });
}
function readAuto(){
  const rows = sel => $$(sel + " tr").map(tr => Object.fromEntries([...tr.querySelectorAll("[data-f]")].map(i => [i.dataset.f, i.value.trim()])));
  settings.modes = rows("#modeRows").map(m => ({...m, key: m.key || m.label.toLowerCase().replace(/[^a-z0-9]/g, "") || "modus"}));
  settings.map_rules = rows("#ruleRows").filter(r => r.pattern);
}
$("#btnModeAdd").onclick = () => { readAuto(); settings.modes.push({key: "modus" + (settings.modes.length+1), label: "Neuer Modus", game_type: 0, game_mode: 0, players: 10}); renderAuto(); };
$("#btnRuleAdd").onclick = () => { readAuto(); settings.map_rules.push({pattern: "", label: "", players: 2}); renderAuto(); };
$("#btnAutoSave").onclick = async () => {
  readAuto();
  try {
    settings = await api("/api/settings", {method:"PUT", body:{modes: settings.modes, map_rules: settings.map_rules,
      public_url: $("#setPublicUrl").value.trim(), watch_interval: parseInt($("#setInterval").value, 10) || 10,
      scan_interval: Math.max(0, parseInt($("#setScanInterval").value, 10) || 0), scan_subnets: $("#setScanSubnets").value.trim(),
      games_base: $("#setGamesBase").value.trim(), cache_container: $("#setCacheContainer").value.trim(),
      hostname_pattern: $("#setHostnamePattern").value.trim(), names_pattern: $("#setNamesPattern").value.trim(), internet_host: $("#setInternetHost").value.trim(), auto_bots: $("#setAutoBots").checked, auto_matchzy: $("#setAutoMz").checked, container_dns: $("#setContainerDns").value.trim(), port_range: $("#setPortRange").value.trim()}});
    renderAuto(); refreshModeSelects(); toast("Gespeichert – wird beim nächsten Prüfen angewendet");
  } catch(err){ toast(err.message, true); }
};
function refreshModeSelects(){
  $("#modeSelect").innerHTML = modeOptions(true);
  $("#qMode").innerHTML = modeOptions(true);
}

/* ================= Server-Dialog ================= */
let editing = null;
function openServerDialog(s){
  editing = s;
  const f = $("#serverForm");
  $("#dlgTitle").textContent = s ? "Server bearbeiten" : "Server hinzufügen";
  f.name.value = s?.name || ""; f.host.value = s?.host || ""; f.port.value = s?.port || 27015;
  f.password.value = ""; f.notes.value = s?.notes || ""; f.auto_slots.checked = s ? s.auto_slots !== false : true;
  $("#dlgGame").innerHTML = Object.entries(GAMES).map(([k,g]) => `<option value="${k}">${esc(g.label)}</option>`).join("");
  f.game.value = gameOf(s);
  f.web_url.value = s?.web_url || "";
  f.name_from_game.checked = s ? s.name_from_game !== false : true;
  f.mode_name.checked = s ? s.mode_name !== false : true;
  f.game_port.value = s?.game_port || "";
  fillContainerSelect(s?.container || "");
  dlgGameChanged(!s);
  $("#pwHint").textContent = s ? "(leer lassen = unverändert)" : "";
  $("#btnDelete").classList.toggle("hidden", !s);
  $("#dlgServer").showModal();
}
$("#btnAdd").onclick = () => openServerDialog(null);
$("#btnEdit").onclick = () => current && openServerDialog(current);
$("#btnCancel").onclick = () => $("#dlgServer").close();
function formData(){
  const f = $("#serverForm");
  return {name: f.name.value.trim(), host: f.host.value.trim(), port: parseInt(f.port.value, 10), password: f.password.value,
          notes: f.notes.value.trim(), auto_slots: f.auto_slots.checked, game: f.game.value, container: f.container.value,
          web_url: f.web_url.value.trim(), name_from_game: f.name_from_game.checked, mode_name: f.mode_name.checked,
          game_port: f.game_port.value ? parseInt(f.game_port.value, 10) : null};
}
$("#serverForm").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    const d = formData();
    const s = editing ? await api(`/api/servers/${editing.id}`, {method:"PUT", body:d}) : await api("/api/servers", {body:d});
    $("#dlgServer").close(); await loadServers();
    selectServer(servers.find(x => x.id === s.id)); toast("Gespeichert");
  } catch(err){ toast(err.message, true); }
});
$("#btnDelete").onclick = () => { if (editing){ $("#dlgServer").close(); openDelete(editing); } };
let delTarget = null;
async function openDelete(s){
  delTarget = s;
  $("#delName").textContent = s.name;
  $("#delPaths").innerHTML = `<span class="hint">Prüfe Container und Datenordner …</span>`;
  $("#delCt").checked = false; $("#delData").checked = false; $("#delConfirm").value = "";
  $("#delCtRow").classList.add("hidden"); $("#delDataRow").classList.add("hidden");
  updDel();
  $("#dlgDel").showModal();
  let plan;
  try { plan = await api(`/api/servers/${s.id}/delete-preview`); } catch(err){ $("#delPaths").innerHTML = `<span style="color:var(--bad)">${esc(err.message)}</span>`; return; }
  const hasCt = !!plan.container;
  $("#delCtRow").classList.toggle("hidden", !hasCt);
  $("#delCtName").textContent = plan.container || "";
  const items = [...plan.paths.map(p => ({label: p.path, blocked: p.blocked})), ...plan.volumes.map(v => ({label: "Volume " + v.name, blocked: v.blocked}))];
  $("#delDataRow").classList.toggle("hidden", !hasCt || !items.length);
  if (hasCt){ $("#delCt").checked = true; $("#delData").checked = items.some(i => !i.blocked); updDel(); }   // Standard: alles weg
  $("#delPaths").innerHTML = !hasCt ? `<span class="hint">${plan.container_error ? "Container nicht gefunden – " : ""}Kein Container verknüpft: Es wird nur der Eintrag in der Liste entfernt.</span>` :
    items.map(i => `<div>${i.blocked ? "🔒" : "🗑"} <span class="mono">${esc(i.label)}</span>${i.blocked ? ` <span class="hint">– bleibt erhalten: ${esc(i.blocked)}</span>` : ""}</div>`).join("") || `<span class="hint">Keine Datenordner gefunden.</span>`;
}
function updDel(){
  const data = $("#delData").checked;
  if (data) $("#delCt").checked = true;
  $("#delCt").disabled = data;
  $("#delConfirmRow").classList.toggle("hidden", !data);
  $("#delGo").disabled = data && $("#delConfirm").value.trim() !== (delTarget ? delTarget.name : "");
  $("#delGo").textContent = data ? "Server und Daten endgültig löschen" : $("#delCt").checked ? "Server und Container löschen" : "Aus der Liste entfernen";
}
["#delCt", "#delData"].forEach(sel => $(sel).addEventListener("change", updDel));
$("#delConfirm").addEventListener("input", updDel);
$("#delCancel").onclick = () => $("#dlgDel").close();
$("#delForm").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    const r = await api(`/api/servers/${delTarget.id}/delete`, {body:{remove_container: $("#delCt").checked, delete_data: $("#delData").checked, confirm: $("#delConfirm").value}});
    $("#dlgDel").close();
    toast(r.id ? "Löschen läuft – Fortschritt links unter der Gesamtlast" : "Server aus der Liste entfernt");
    if (current && current.id === delTarget.id) showView("dash");
    setTimeout(async () => { await loadServers(); refreshDash(); }, r.id ? 2500 : 0);
    refreshActivity();
  } catch(err){ toast(err.message, true); }
});
$("#btnTest").onclick = async () => {
  const d = formData(); if (!d.host) return toast("IP fehlt", true);
  $("#btnTest").disabled = true;
  try { const r = await api("/api/test", {body:{host: d.host, port: d.port, password: d.password, server_id: editing?.id || null}}); toast(`Verbindung OK – ${r.hostname || "Server"} (${r.map || "?"})`); }
  catch(err){ toast("Test fehlgeschlagen: " + err.message, true); }
  finally { $("#btnTest").disabled = false; }
};

/* ================= Broadcast ================= */
$("#btnBroadcast").onclick = () => {
  $("#bcServers").innerHTML = servers.map(s => `<label class="tag" style="padding:5px 9px;cursor:pointer"><input type="checkbox" value="${esc(s.id)}" checked style="width:auto;margin-right:6px">${esc(s.name)}</label>`).join("") || '<span class="muted">Keine Server angelegt.</span>';
  $("#bcResult").innerHTML = ""; $("#dlgBroadcast").showModal();
};
$$("[data-bc]").forEach(b => b.onclick = () => $("#bcCmd").value = b.dataset.bc);
$("#bcClose").onclick = () => $("#dlgBroadcast").close();
$("#broadcastForm").addEventListener("submit", async e => {
  e.preventDefault();
  const ids = $$("#bcServers input:checked").map(i => i.value), cmd = $("#bcCmd").value.trim();
  if (!ids.length || !cmd) return;
  $("#bcResult").innerHTML = '<span class="muted">Sende …</span>';
  try {
    const res = await api("/api/broadcast", {body:{command: cmd, server_ids: ids}});
    $("#bcResult").innerHTML = res.map(r => `<div style="margin-top:8px"><b style="color:${r.ok ? "var(--ok)" : "var(--bad)"}">${r.ok ? "✓" : "✗"} ${esc(r.name)}</b>${r.output ? `<pre class="out">${esc(r.output)}</pre>` : ""}</div>`).join("");
  } catch(err){ $("#bcResult").innerHTML = `<span style="color:var(--bad)">${esc(err.message)}</span>`; }
});


/* ================= Andere Spiele (Factorio, Satisfactory, Valheim) ================= */
const worldLabel = g => ({satisfactory: "Session", wreckfest: "Strecke", tf2: "Map", minecraft: "MOTD", teamspeak: "Server"})[g] || "Welt";
function renderGeneric(st){
  const g = gameOf(current), meta = GAMES[g];
  $("#stOnline").textContent = "Online"; $("#stOnline").style.color = "var(--ok)";
  $("#stVersion").textContent = st.version ? "Version " + st.version : "";
  $("#stMapLabel").textContent = worldLabel(g);
  $("#stMap").textContent = st.track_name || st.map || "–"; $("#stMapSub").textContent = st.hostname || "";
  if (st.map_image){ $("#stMapImg").src = st.map_image; $("#stMapImg").classList.remove("hidden"); } else $("#stMapImg").classList.add("hidden");
  $("#stMode").textContent = meta.label; $("#stRounds").textContent = "";
  $("#stPlayers").textContent = `${st.humans ?? 0}${st.max_players ? " / " + st.max_players : ""}${st.bots ? ` · ${st.bots} Bots` : ""}`;
  $("#stAuto").textContent = ""; $("#stAuto").style.color = "";
  $("#gExtra").innerHTML = Object.entries(st.extra || {}).map(([k,v]) => `<span>${esc(k)}</span><span>${esc(v)}</span>`).join("") || `<span class="hint">Keine weiteren Infos</span><span></span>`;
  const canSave = meta.features.includes("save");
  $("#gSaveRow").classList.toggle("hidden", !canSave);
  $("#gClaim").classList.toggle("hidden", !st.unclaimed);
  $("#gActHint").textContent = g === "valheim" ? "Valheim hat keine Remote-Konsole – Neustart und Logs über den Container-Tab." :
    g === "wreckfest" ? "Wreckfest hat keine Remote-Konsole. Die Server-Konsole erreichst du über „Webkonsole ↗“ oben rechts (beim ich777-Image), Neustart und Logs über den Container-Tab." :
    g === "satisfactory" && st.privilege === "Client" ? "Ohne Admin-Passwort nur Lesezugriff – Passwort unter „Bearbeiten“ eintragen." : "";
  if (g === "wreckfest"){ loadWfConfig(); loadWfRotation(); /* wfLiveInit(): Serverfenster nimmt unter Wine keine Eingaben an */ } else { $("#wfPanel").classList.add("hidden"); $("#wfRotPanel").classList.add("hidden"); $("#wfLivePanel").classList.add("hidden"); }
  const list = st.players || [];
  $("#playerRows").innerHTML = list.length ? list.map(p => `<tr><td></td><td class="name">${esc(p.name)}</td><td colspan="2"></td><td class="mono">${esc(p.time || "")}</td><td colspan="3"></td></tr>`).join("")
    : `<tr><td colspan="8" class="muted">${st.humans ? `${st.humans} Spieler online (Namen liefert dieses Spiel nicht)` : "Keine Spieler verbunden."}</td></tr>`;
  $("#stUpdated").textContent = "aktualisiert " + new Date().toLocaleTimeString("de-DE");
  renderHistory();
}
/* Wreckfest: Live-Steuerung über das Serverfenster (screen) – ohne Neustart */
let wfLiveFor = null;
async function wfCmd(cmd, msg){
  try {
    const r = await api(`/api/servers/${current.id}/wreckfest/console`, {body: {cmd}});
    $("#wfLOut").classList.remove("hidden"); $("#wfLOut").textContent = r.output || "(keine Ausgabe)";
    toast(msg || `Gesendet: ${cmd}`); setTimeout(refreshStatus, 2000);
  } catch (e) { toast(e.message, true); }
}
async function wfLiveInit(){
  if (permOf(current) < 2) return;
  $("#wfLivePanel").classList.remove("hidden");
  if (wfLiveFor === current.id) return;
  wfLiveFor = current.id; $("#wfLOut").classList.add("hidden");
  try {
    const r = await api(`/api/servers/${current.id}/wreckfest/rotation`);
    if (!r.exists) return;
    $("#wfLTrack").innerHTML = ["race", "derby"].map(t => `<optgroup label="${t === "race" ? "Rennstrecken" : "Derby-Arenen"}">${r.tracks.filter(x => x.type === t).map(x => `<option value="${esc(x.id)}" ${x.id === r.current.track ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</optgroup>`).join("");
    $("#wfLMode").innerHTML = r.gamemodes.map(([k, l]) => `<option value="${esc(k)}" ${k === r.current.gamemode ? "selected" : ""}>${esc(l)}</option>`).join("");
    if (r.current.bots !== "") $("#wfLBots").value = r.current.bots;
    if (r.current.laps) $("#wfLLaps").value = r.current.laps;
  } catch {}
}
$("#btnWfLBots").onclick = () => { const n = Math.max(0, Math.min(24, parseInt($("#wfLBots").value) || 0)); wfCmd(`bots ${n}`, `Bots: ${n}`); };
$("#btnWfLTrack").onclick = () => wfCmd(`track ${$("#wfLTrack").value}`, `Strecke: ${$("#wfLTrack").selectedOptions[0]?.textContent || ""}`);
$("#btnWfLMode").onclick = () => wfCmd(`gamemode ${$("#wfLMode").value}`, `Modus: ${$("#wfLMode").selectedOptions[0]?.textContent || ""}`);
$("#btnWfLLaps").onclick = () => { const n = Math.max(1, Math.min(99, parseInt($("#wfLLaps").value) || 3)); wfCmd(`laps ${n}`, `Runden: ${n}`); };
$$("[data-wfl]").forEach(b => b.onclick = () => wfCmd(b.dataset.wfl));
$("#btnWfLCmd").onclick = () => { const c = $("#wfLCmd").value.trim(); if (c) { wfCmd(c); $("#wfLCmd").value = ""; } };
$("#wfLCmd").addEventListener("keydown", e => { if (e.key === "Enter") $("#btnWfLCmd").click(); });
/* Wreckfest: server_config.cfg bearbeiten + LAN-Sichtbarkeit */
let wfLoadedFor = null;
const WF_FIELDS = [["server_name","Servername"],["password","Passwort (leer = keins)"],["max_players","Max. Spieler"],["welcome_message","Begrüßung"],
  ["gamemode","Spielmodus"],["track","Strecke (leer = Rotation)"],["laps","Runden"],["bots","Bots"],
  ["admin_steam_ids","Admin-SteamIDs (SteamID64, kommagetrennt)"],["op_steam_ids","Moderator-SteamIDs"]];
async function loadWfConfig(force){
  if (permOf(current) < 3) return;
  if (!force && wfLoadedFor === current.id) return;
  wfLoadedFor = current.id;
  let r;
  try { r = await api(`/api/servers/${current.id}/wreckfest/config`); } catch (e) { $("#wfPanel").classList.add("hidden"); return; }
  $("#wfPanel").classList.remove("hidden");
  if (!r.exists){ $("#wfFields").innerHTML = `<div class="hint">Server installiert sich noch – Einstellungen erscheinen danach.</div>`; $("#wfLan").innerHTML = ""; return; }
  const v = r.values;
  $("#wfFields").innerHTML = WF_FIELDS.map(([k, l]) => `<div><label>${esc(l)}</label><input data-wf="${k}" value="${esc(v[k] ?? "")}" ${k === "gamemode" ? 'list="wfModes"' : ""}></div>`).join("");
  $("#wfLan").innerHTML = r.host_net
    ? `<div class="pill warn" style="margin-bottom:6px">Host-Netzwerk aktiv</div>
       <div class="hint" style="margin-bottom:6px">Startet der Server im Host-Netz nicht (Neustart-Schleife), zurück ins normale Netz stellen.</div>
       <button class="primary" id="btnWfBridge">Zurück ins normale Netz (Container wird neu erstellt)</button>`
    : r.lan_ok
    ? `<div class="pill warn" style="margin-bottom:6px">Ports stimmen, aber die LAN-Suche findet den Server noch nicht</div>
       <div class="hint" style="margin-bottom:6px">Wreckfest sucht im LAN per Broadcast – den leitet Docker an Container mit Portfreigaben nicht weiter. Der LAN-Weiterleiter (kleiner Container im Host-Netz) empfängt die Suche und reicht sie an den Server durch.</div>
       ${r.relay && r.relay.running
         ? `<span class="pill ok">LAN-Weiterleiter läuft (Port ${esc(r.relay.port)} → ${esc(v.query_port)})</span> <button class="small" id="btnWfRelayOff">Weiterleiter entfernen</button>`
         : `<button class="primary" id="btnWfRelay">LAN-Weiterleiter einrichten</button>${r.relay ? ` <span class="hint">Weiterleiter: ${esc(r.relay.status || "")}</span>` : ""}`}`
    : `<div class="pill warn" style="margin-bottom:6px">Im LAN-Reiter von Wreckfest nicht sichtbar (Query-Port ${esc(v.query_port || "?")})</div>
       <div class="hint" style="margin-bottom:6px">Wreckfest wird in der LAN-Suche nur auf den Query-Ports 26900–26905 bzw. 27015–27020 gefunden – letztere belegen die CS2-Server.</div>
       ${r.managed ? `<button class="primary" id="btnWfLan">LAN-Sichtbarkeit einrichten (Container wird neu erstellt)</button>` : `<span class="hint">Container nicht vom Tool angelegt – query_port in server_config.cfg und Port-Freigabe selbst anpassen.</span>`}`;
  const rb = $("#btnWfRelay"), ro = $("#btnWfRelayOff");
  const relay = async on => {
    try { const x = await api(`/api/servers/${current.id}/wreckfest/lanrelay`, {body: {on}}); toast(on ? `LAN-Weiterleiter läuft auf Port ${x.relay?.port} – im Spiel unter „LAN“ suchen` : "Weiterleiter entfernt"); }
    catch (e) { toast(e.message, true); }
    loadWfConfig(true);
  };
  if (rb) rb.onclick = () => { rb.disabled = true; rb.textContent = "wird eingerichtet …"; relay(true); };
  if (ro) ro.onclick = () => relay(false);
  const bb = $("#btnWfBridge");
  if (bb) bb.onclick = async () => {
    bb.disabled = true; bb.textContent = "wird umgestellt …";
    try { await api(`/api/servers/${current.id}/wreckfest/bridgenet`, {method: "POST"}); toast("Zurück im normalen Netz – Server startet"); }
    catch (e) { toast(e.message, true); }
    loadWfConfig(true);
  };
  const hb = $("#btnWfHost");
  if (hb) hb.onclick = async () => {
    if (!confirm("Wreckfest-Container wird gestoppt und im Host-Netzwerk neu erstellt (Daten bleiben). Fortfahren?")) return;
    hb.disabled = true; hb.textContent = "wird umgestellt …";
    try { await api(`/api/servers/${current.id}/wreckfest/hostnet`, {method: "POST"}); toast("Host-Netzwerk aktiv – Server startet, danach im Spiel unter „LAN“ suchen"); }
    catch (e) { toast(e.message, true); }
    loadWfConfig(true);
  };
  const lb = $("#btnWfLan");
  if (lb) lb.onclick = async () => {
    if (!confirm("Wreckfest-Container wird gestoppt und mit neuen Ports neu erstellt (Daten bleiben). Fortfahren?")) return;
    lb.disabled = true; lb.textContent = "wird eingerichtet …";
    try { const x = await api(`/api/servers/${current.id}/wreckfest/lan`, {method: "POST"}); toast(`LAN-Suche eingerichtet: Query-Port ${x.query_port}`); await loadServers(); }
    catch (e) { toast(e.message, true); }
    loadWfConfig(true);
  };
}
/* Wreckfest-Rotation (Event-Loop) */
let wfRot = null, wfRotFor = null;
const WF_EV_DEFAULT = {gamemode: "racing", laps: "3", bots: "", car_class_restriction: "", num_teams: "", car_reset_disabled: ""};
async function loadWfRotation(force){
  if (permOf(current) < 3) return;
  if (!force && wfRotFor === current.id) return;
  wfRotFor = current.id;
  let r;
  try { r = await api(`/api/servers/${current.id}/wreckfest/rotation`); } catch { $("#wfRotPanel").classList.add("hidden"); return; }
  if (!r.exists){ $("#wfRotPanel").classList.add("hidden"); return; }
  wfRot = r; $("#wfRotPanel").classList.remove("hidden");
  $("#wfRotGlobals").innerHTML = Object.entries(r.global_labels).map(([k, l]) => `<div><label>${esc(l)}</label><input data-wfg="${k}" value="${esc(r.globals[k] ?? "")}"></div>`).join("");
  $("#wfRotName").textContent = r.auto_name ? `Servername wird: ${r.auto_name} …` : "";
  renderWfRot();
}
function wfTrackOpts(sel){
  const grp = (t, label) => `<optgroup label="${label}">${wfRot.tracks.filter(x => x.type === t).map(x => `<option value="${x.id}" ${x.id === sel ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</optgroup>`;
  const known = wfRot.tracks.some(x => x.id === sel);
  return (sel && !known ? `<option value="${esc(sel)}" selected>${esc(sel)} (Mod/unbekannt)</option>` : "") + grp("race", "Rennstrecken") + grp("derby", "Derby-Arenen");
}
function renderWfRot(){
  const ev = wfRot.events;
  $("#wfRotInfo").textContent = ev.length ? `${ev.length} Events` : "Keine Rotation – der Server bleibt auf einer Strecke.";
  $("#wfRotRows").innerHTML = ev.map((e, i) => `<tr data-i="${i}">
    <td class="mono">${i + 1}</td>
    <td>${(t => wfThumb(t && t.photo, t && t.layout, (t && t.name) || e.track, `data-pick="${i}"`))(wfRot.tracks.find(x => x.id === e.track))}</td>
    <td><select data-ef="track">${wfTrackOpts(e.track)}</select></td>
    <td><select data-ef="gamemode">${wfRot.gamemodes.map(([k, l]) => `<option value="${k}" ${k === (e.gamemode || "racing") ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></td>
    <td><input data-ef="laps" value="${esc(e.laps ?? "")}" style="width:60px" placeholder="Std."></td>
    <td><input data-ef="bots" value="${esc(e.bots ?? "")}" style="width:60px" placeholder="Std."></td>
    <td><select data-ef="car_class_restriction">${wfRot.car_classes.map(c => `<option value="${c}" ${c === (e.car_class_restriction || "") ? "selected" : ""}>${c ? c.toUpperCase() : "alle"}</option>`).join("")}</select></td>
    <td><input data-ef="num_teams" value="${esc(e.num_teams ?? "")}" style="width:50px" placeholder="–"></td>
    <td><input type="checkbox" data-ef="car_reset_disabled" ${String(e.car_reset_disabled) === "1" ? "checked" : ""} style="width:auto"></td>
    <td style="white-space:nowrap"><button class="small" data-em="-1" title="nach oben">↑</button><button class="small" data-em="1" title="nach unten">↓</button><button class="small" data-ed title="kopieren">⧉</button><button class="small danger" data-ex title="entfernen">✕</button></td></tr>`).join("") ||
    `<tr><td colspan="10" class="hint">Mit „＋ Event“ oder einer Vorlage oben anfangen.</td></tr>`;
  $$("#wfRotRows tr[data-i]").forEach(tr => {
    const i = +tr.dataset.i;
    tr.querySelectorAll("[data-ef]").forEach(inp => inp.onchange = () => {
      const k = inp.dataset.ef;
      ev[i][k] = inp.type === "checkbox" ? (inp.checked ? "1" : "") : inp.value.trim();
      if (k === "track"){   // Derby-Arena -> Derby-Modus vorschlagen
        const t = wfRot.tracks.find(x => x.id === inp.value);
        if (t && t.type === "derby" && !/derby/.test(ev[i].gamemode || "")) ev[i].gamemode = "derby";
        if (t && t.type === "race" && /derby/.test(ev[i].gamemode || "")) ev[i].gamemode = "racing";
        renderWfRot();
      }
    });
    tr.querySelectorAll("[data-em]").forEach(b => b.onclick = () => { const j = i + +b.dataset.em; if (j < 0 || j >= ev.length) return; [ev[i], ev[j]] = [ev[j], ev[i]]; renderWfRot(); });
    const pk = tr.querySelector("[data-pick]"); if (pk) pk.onclick = () => wfOpenPicker(i);
    tr.querySelector("[data-ed]").onclick = () => { ev.splice(i + 1, 0, {...ev[i]}); renderWfRot(); };
    tr.querySelector("[data-ex]").onclick = () => { ev.splice(i, 1); renderWfRot(); };
  });
}
function wfThumb(photo, layout, name, attr = ""){
  return `<div class="wfth${photo ? "" : " nophoto"}" ${attr} title="${esc(name || "")}${attr ? " – klicken zum Auswählen" : ""}">${photo ? `<img class="ph" src="${esc(photo)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}${layout ? `<img class="ly" src="${esc(layout)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}</div>`;
}
let wfPickIdx = -1;
function wfOpenPicker(i){
  wfPickIdx = i; $("#wfPickFilter").value = "";
  $("#wfPickTitle").textContent = `Strecke für Event ${i + 1} wählen`;
  renderWfPicker(); $("#wfPick").classList.remove("hidden"); $("#wfPickFilter").focus();
}
function renderWfPicker(){
  const q = $("#wfPickFilter").value.trim().toLowerCase(), cur = (wfRot.events[wfPickIdx] || {}).track;
  const sec = (type, label) => { const l = wfRot.tracks.filter(x => x.type === type && (!q || x.name.toLowerCase().includes(q) || x.id.includes(q)));
    return l.length ? `<h3 class="pdsec">${label} <span class="hint">(${l.length})</span></h3><div class="wfpgrid">${l.map(x => `<button class="wfpitem${x.id === cur ? " active" : ""}" data-tid="${esc(x.id)}">${wfThumb(x.photo, x.layout, x.name)}<span>${esc(x.name)}</span></button>`).join("")}</div>` : ""; };
  $("#wfPickGrid").innerHTML = sec("race", "Rennstrecken") + sec("derby", "Derby-Arenen") || `<div class="hint">Nichts gefunden</div>`;
  $$("#wfPickGrid [data-tid]").forEach(b => b.onclick = () => {
    const e = wfRot.events[wfPickIdx], t = wfRot.tracks.find(x => x.id === b.dataset.tid);
    if (!e || !t) return;
    e.track = t.id;
    if (t.type === "derby" && !/derby/.test(e.gamemode || "")) e.gamemode = "derby";
    if (t.type === "race" && /derby/.test(e.gamemode || "")) e.gamemode = "racing";
    $("#wfPick").classList.add("hidden"); renderWfRot();
  });
}
$("#wfPickFilter").addEventListener("input", renderWfPicker);
$("#wfPickClose").onclick = () => $("#wfPick").classList.add("hidden");
$("#wfPick").addEventListener("click", e => { if (e.target.id === "wfPick") $("#wfPick").classList.add("hidden"); });
const wfPreset = type => wfRot.tracks.filter(t => !type || t.type === type).filter(t => !/_rev$/.test(t.id))
  .map(t => ({...WF_EV_DEFAULT, track: t.id, gamemode: t.type === "derby" ? "derby" : "racing", laps: t.type === "derby" ? "" : "3"}));
$("#wfRotAdd").onclick = () => { const last = wfRot.events[wfRot.events.length - 1]; wfRot.events.push(last ? {...last} : {...WF_EV_DEFAULT, track: wfRot.tracks[0].id}); renderWfRot(); };
$("#wfRotRaces").onclick = () => { wfRot.events = wfPreset("race"); renderWfRot(); };
$("#wfRotDerby").onclick = () => { wfRot.events = wfPreset("derby"); renderWfRot(); };
$("#wfRotMix").onclick = () => {
  const r = wfPreset("race").sort(() => Math.random() - .5), d = wfPreset("derby").sort(() => Math.random() - .5), out = [];
  r.forEach((x, i) => { out.push(x); if (i % 3 === 2 && d.length) out.push(d.shift()); });   // nach je 3 Rennen ein Derby
  wfRot.events = out; renderWfRot();
};
$("#wfRotShuffle").onclick = () => { wfRot.events.sort(() => Math.random() - .5); renderWfRot(); };
$("#wfRotClear").onclick = () => { if (confirm("Rotation leeren?")){ wfRot.events = []; renderWfRot(); } };
async function wfRotSave(when){
  const globals = {};
  $$("[data-wfg]").forEach(i => { if (i.value.trim() !== "" || (wfRot.globals[i.dataset.wfg] ?? "") !== "") globals[i.dataset.wfg] = i.value.trim(); });
  try {
    const r = await api(`/api/servers/${current.id}/wreckfest/rotation`, {method: "PUT", body: {events: wfRot.events, globals, restart: when !== "never", when}});
    toast(`Rotation mit ${r.events} Events gespeichert${r.server_name ? " – Name: " + r.server_name : ""} – ` +
      (when === "now" ? "Wreckfest startet neu" : when === "empty" ? "Neustart, sobald niemand mehr drauf ist" : "gilt ab dem nächsten Neustart"));
    loadWfRotation(true); wfLoadedFor = null;
  } catch (e) { toast(e.message, true); }
}
["#btnWfRotSave", "#btnWfRotSaveEmpty", "#btnWfRotSaveOnly"].forEach(id => $(id).onclick = () => wfRotSave($(id).dataset.when));
$("#btnWfSave").onclick = async () => {
  const values = {};
  $$("[data-wf]").forEach(i => values[i.dataset.wf] = i.value.trim());
  try { await api(`/api/servers/${current.id}/wreckfest/config`, {method: "PUT", body: {values, restart: true}}); toast("Gespeichert – Wreckfest startet neu"); }
  catch (e) { toast(e.message, true); }
};
$("#btnGSave").onclick = async () => {
  try { const r = await api(`/api/servers/${current.id}/save`, {body:{name: $("#gSaveName").value.trim()}}); toast(r.output || "Gespeichert"); $("#gSaveName").value = ""; }
  catch(err){ toast(err.message, true); }
};
$("#btnGClaim").onclick = async () => {
  const name = $("#gClaimName").value.trim(), pw = $("#gClaimPw").value;
  if (!name || !pw) return toast("Servername und Admin-Passwort angeben", true);
  try { await api(`/api/servers/${current.id}/claim`, {body:{server_name: name, admin_password: pw}}); toast("Server beansprucht – Passwort gespeichert"); $("#gClaimPw").value = ""; refreshStatus(); }
  catch(err){ toast(err.message, true); }
};

/* ================= Container ================= */
function stopCt(){ if (ctTimer){ clearInterval(ctTimer); ctTimer = null; } }
async function loadSleep(){
  if (!current || !current.container) return;
  let r; try { r = await api(`/api/servers/${current.id}/sleep`); } catch { return; }
  $("#slMode").innerHTML = Object.entries(r.modes).map(([k, l]) => `<option value="${k}" ${k === r.mode ? "selected" : ""}>${esc(l)}</option>`).join("");
  $("#slAfter").value = r.after;
  $("#slHibRow").classList.toggle("hidden", !r.hibernate_supported);
  $("#slHib").value = r.hibernate == null ? "" : r.hibernate ? "1" : "0";
  $("#slState").innerHTML = r.asleep ? `<span class="pill">💤 schläft seit ${fmtDate(r.asleep.since)} (${r.asleep.mode === "pause" ? "pausiert" : "angehalten"})</span>`
    : `<span class="hint">wach · ${r.idle_s >= 60 ? `seit ${Math.round(r.idle_s / 60)} min ohne Spieler` : "Spieler aktiv oder gerade gestartet"}</span>`;
  $("#btnSlNow").classList.toggle("hidden", !!r.asleep); $("#btnSlWake").classList.toggle("hidden", !r.asleep);
}
$("#btnSlSave").onclick = async () => {
  const h = $("#slHib").value;
  try { await api(`/api/servers/${current.id}/sleep/config`, {body: {mode: $("#slMode").value, after: +$("#slAfter").value || 30, hibernate: h === "" ? null : h === "1"}}); toast("Ruhemodus gespeichert"); loadSleep(); }
  catch (e){ toast(e.message, true); }
};
$("#btnSlNow").onclick = async () => { try { await api(`/api/servers/${current.id}/sleep/now`, {method: "POST"}); toast("Server ruht jetzt"); loadSleep(); refreshContainer(); } catch (e){ toast(e.message, true); } };
$("#btnSlWake").onclick = async () => { try { await api(`/api/servers/${current.id}/wake`, {method: "POST"}); toast("Server wird geweckt"); loadSleep(); refreshContainer(); } catch (e){ toast(e.message, true); } };
async function refreshContainer(){
  if (!current) return;
  try {
    const c = await api(`/api/servers/${current.id}/container`);
    $("#ctName").textContent = c.name; $("#ctImage").textContent = c.image || "";
    $("#ctState").textContent = c.state || "?"; $("#ctState").style.color = c.state === "running" ? "var(--ok)" : "var(--bad)";
    $("#ctSince").textContent = c.started && c.state === "running" ? "seit " + new Date(c.started).toLocaleString("de-DE") : (c.restarts ? `${c.restarts} Neustarts` : "");
    $("#ctCpu").textContent = c.stats && c.stats.cpu != null ? c.stats.cpu + " %" : "–";
    $("#ctMem").textContent = c.stats && c.stats.mem_mb != null ? (c.stats.mem_mb >= 1024 ? (c.stats.mem_mb/1024).toFixed(1) + " GB" : c.stats.mem_mb + " MB") : "–";
    $("#ctMemLimit").textContent = c.stats && c.stats.mem_limit_mb ? "von " + (c.stats.mem_limit_mb/1024).toFixed(1) + " GB" : "";
  } catch(err){ $("#ctState").textContent = "Fehler"; $("#ctSince").textContent = err.message; }
  if ($("#ctFollow").checked) loadLogs();
}
async function loadLogs(){
  try {
    const r = await api(`/api/servers/${current.id}/container/logs?tail=300`);
    const box = $("#ctLogs"), atEnd = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
    box.textContent = r.logs.replace(/\x1b\[[0-9;]*m/g, "");
    if (atEnd) box.scrollTop = box.scrollHeight;
  } catch(err){ $("#ctLogs").textContent = err.message; }
}
$("#btnCtLogs").onclick = loadLogs;
$$("[data-ct]").forEach(b => b.onclick = async () => {
  const act = b.dataset.ct, label = {start:"starten", stop:"stoppen", restart:"neu starten"}[act];
  if (act !== "start" && !confirm(`Container ${current.container} wirklich ${label}?`)) return;
  b.disabled = true;
  try { await api(`/api/servers/${current.id}/container/${act}`, {method:"POST"}); toast(`Container wird ${label === "starten" ? "gestartet" : label === "stoppen" ? "gestoppt" : "neu gestartet"}`); setTimeout(refreshContainer, 1500); }
  catch(err){ toast(err.message, true); }
  finally { b.disabled = false; }
});
async function fillContainerSelect(selected){
  const sel = $("#dlgContainer");
  sel.innerHTML = `<option value="">– keiner –</option>` + (selected ? `<option value="${esc(selected)}">${esc(selected)}</option>` : "");
  sel.value = selected || "";
  if (!dockerOn){ sel.disabled = true; sel.title = "Docker-Socket nicht eingebunden"; return; }
  try {
    const list = await api("/api/docker/containers");
    sel.innerHTML = `<option value="">– keiner –</option>` + list.map(c => `<option value="${esc(c.name)}">${esc(c.name)} · ${esc(c.image)} · ${esc(c.state)}</option>`).join("");
    sel.value = selected || "";
  } catch {}
}
function dlgGameChanged(setDefaults){
  const f = $("#serverForm"), g = GAMES[f.game.value] || GAMES.cs2;
  $("#dlgPortLabel").textContent = g.port_label;
  $("#dlgPwLabel").textContent = g.password_label;
  if (setDefaults) f.port.value = g.default_port;
  $("#dlgAutoRow").classList.toggle("hidden", f.game.value !== "cs2");
  $("#dlgModeNameRow").classList.toggle("hidden", f.game.value !== "cs2");
}
$("#dlgGame").addEventListener("change", () => dlgGameChanged(true));

/* ================= Netzwerk-Scan ================= */
let scanTimer = null;
async function loadScan(){
  try { renderScan(await api("/api/scan")); } catch(err){ toast(err.message, true); }
}
function renderScan(r){
  const nets = r.subnets && r.subnets.length ? r.subnets : r.planned;
  $("#scanSub").textContent = r.running ? `Scanne ${nets.join(", ")} …` :
    r.last ? `Letzter Scan ${new Date(r.last*1000).toLocaleTimeString("de-DE")} (${r.duration}s) · Netze: ${nets.join(", ") || "–"}` : `Noch kein Scan · geplante Netze: ${nets.join(", ") || "– (bitte Subnetz eintragen)"}`;
  $("#scanInfo").textContent = `Automatischer Scan: ${settings.scan_interval > 0 ? "alle " + settings.scan_interval + " Minuten" : "aus"} (einstellbar unter „Automatik & Einstellungen“)` + (r.error ? ` · Fehler: ${r.error}` : "");
  const res = r.results || [];
  const neu = res.filter(x => !x.known).length;
  $("#scanBadge").textContent = neu; $("#scanBadge").classList.toggle("hidden", !neu);
  $("#scanRows").innerHTML = res.length ? res.map((x, i) => `<tr>
    <td>${gbadge(x.game)}</td><td>${esc(x.name || "")}</td>
    <td class="mono">${x.host ? esc(x.host) + ":" + x.port : (x.ports || []).map(esc).join(", ") || "–"}</td>
    <td>${esc(x.map || "")}</td><td class="mono">${x.players != null ? x.players + (x.max_players ? "/" + x.max_players : "") : "–"}</td>
    <td><span class="pill">${esc(x.source)}</span></td>
    <td>${x.known ? `<span class="pill ok">bereits in der Liste</span>` : `<button class="small primary adminonly" data-adopt="${i}">Übernehmen</button>`}</td></tr>`).join("")
    : `<tr><td colspan="7" class="muted">${r.running ? "Suche läuft …" : "Nichts gefunden."}</td></tr>`;
  $$("[data-adopt]").forEach(b => b.onclick = () => adopt(res[+b.dataset.adopt]));
  clearTimeout(scanTimer);
  if (r.running && view === "scan") scanTimer = setTimeout(loadScan, 2000);
}
$("#btnScan").onclick = async () => {
  try { renderScan(await api("/api/scan", {method:"POST"})); } catch(err){ toast(err.message, true); }
};
function adopt(x){
  openServerDialog(null);
  const f = $("#serverForm");
  f.game.value = x.game; dlgGameChanged(true);
  f.name.value = x.name || x.container || "";
  if (x.host){ f.host.value = x.host; f.port.value = x.port; }
  else {
    f.host.value = location.hostname;
    const p = (x.ports || []).map(p => p.split("/")).find(([, t]) => t === (x.game === "valheim" ? "udp" : "tcp"));
    if (p) f.port.value = x.game === "valheim" ? (+p[0] + (x.ports.length > 1 ? 0 : 1)) : p[0];
  }
  if (x.container) setTimeout(() => { $("#dlgContainer").value = x.container; }, 600);
  toast(GAMES[x.game].password_label.startsWith("–") ? "Daten prüfen und speichern" : `Bitte noch ${GAMES[x.game].password_label} eintragen`);
}

/* ================= Neuen Server anlegen ================= */
let tpl = null, createGame = "cs2", jobTimer = null, createN = 1, createCountFor = null;
async function initCreate(){
  try { tpl = await api("/api/templates"); } catch(err){ return toast(err.message, true); }
  $("#createNoDocker").classList.toggle("hidden", tpl.docker);
  $("#createNoDocker").innerHTML = `<b style="color:var(--accent)">Docker-Socket nicht eingebunden.</b> <span class="hint">Zum Anlegen und Steuern von Containern muss der Stack <code>/var/run/docker.sock</code> mounten (ist in <code>portainer-stack.yml</code> vorbereitet).</span>`;
  const have = g => servers.filter(s => gameOf(s) === g).length;
  $("#createGameSeg").innerHTML = Object.entries(tpl.templates).sort((a, b) => a[1].label.localeCompare(b[1].label))
    .map(([k,t]) => `<button data-cg="${k}" class="cgtile ${k===createGame?"active":""}" style="--gc:${GAMES[k]?.color || "#888"}">${gameTile(k, 18)}<span class="cglabel">${esc(t.label)}</span>${have(k) ? `<span class="cgcount" title="schon angelegt">${have(k)}</span>` : ""}</button>`).join("");
  const allowed = Object.keys(tpl.templates).filter(k => permFor(k) >= 4);
  if (!allowed.includes(createGame) && allowed.length){ createGame = allowed[0]; return initCreate(); }
  $$("#createGameSeg [data-cg]").forEach(b => { if (permFor(b.dataset.cg) < 4) b.remove(); });
  $$("#createGameSeg [data-cg]").forEach(b => b.onclick = () => { createGame = b.dataset.cg; initCreate(); });
  const t = tpl.templates[createGame];
  let sug = {values: {}, n: servers.filter(s => gameOf(s) === createGame).length + 1, used: []};
  try { sug = await api(`/api/templates/${createGame}/suggest`); } catch {}
  const n = sug.n; createN = n;
  if (createCountFor !== createGame){ $("#createCount").value = 1; createCountFor = createGame; }   // Anzahl nur beim Spielwechsel zurücksetzen
  const fill = (v, k) => sug.values[k] != null ? String(sug.values[k]) : String(v).replace("{n}", n).replace("{port}", 27030 + n).replace("{tvport}", 27020 + n);
  $("#createFields").innerHTML = t.fields.map(([k, label, type, def, hint]) => `<div class="field"><label>${esc(label)}</label>${
    type === "select" ? `<select data-cf="${k}">${hint.split(",").map(o => `<option ${o===def?"selected":""}>${o}</option>`).join("")}</select>`
    : `<input data-cf="${k}" type="${type==="password"?"password":"text"}" value="${esc(fill(def, k))}" ${type==="number"?'inputmode="numeric"':""} autocomplete="off">`
  }${hint && type !== "select" ? `<div class="hint">${esc(hint)}</div>` : ""}</div>`).join("");
  const same = createGame === "cs2" ? servers.filter(s => gameOf(s) === createGame && s.container) : [];   // Kopieren nur bei CS2
  let tplInfo = null;
  if (createGame === "cs2"){ try { tplInfo = await api("/api/cs2-template"); } catch {} }
  const hasTpl = tplInfo && tplInfo.last;
  if (same.length || hasTpl) $("#createFields").insertAdjacentHTML("beforeend", `<div class="field"><label>Spieldateien kopieren von (spart den Download)</label>
    <select data-cf="_copy_from"><option value="">– nicht kopieren, neu herunterladen –</option>${hasTpl ? `<option value="_local" selected>Lokale Vorlage auf der internen Platte (${esc(fmtBytes(tplInfo.bytes || 0))}, Stand ${new Date(tplInfo.last * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"})}) – am schnellsten</option>` : ""}${same.map(s => `<option value="${esc(s.id)}" ${!hasTpl && s === same[0] ? "selected" : ""}>${esc(s.name)} (${esc(s.container)})</option>`).join("")}</select>
    <div class="hint">Kopiert die Installation eines vorhandenen Servers ins neue Datenverzeichnis, bevor er startet. SteamCMD prüft danach nur noch Unterschiede. Quelle sollte fertig installiert sein.</div></div>`);
  const upd = () => { const name = ($('[data-cf="name"]') || {}).value || ""; $("#createDataDir").value = t.data_default.replace("{base}", tpl.games_base || settings.games_base || "/mnt/grohlan").replace("{n}", n).replace("{name}", name); };
  upd(); $('[data-cf="name"]').addEventListener("input", upd);
  // Adresse der Spielserver: LAN-IP – auch wenn die Seite gerade über die Internet-Adresse geöffnet ist
  const isPriv = h => /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|127\.)/.test(h);
  const lanHosts = servers.map(x => x.host).filter(isPriv);
  const common = lanHosts.sort((a, b) => lanHosts.filter(x => x === b).length - lanHosts.filter(x => x === a).length)[0];
  $("#createHost").value = (settings.public_url || "").replace(/^https?:\/\//, "").split(/[:/]/)[0] || (isPriv(location.hostname) ? location.hostname : common || location.hostname);
  $("#createHint").textContent = `Image: ${t.image} · Der Ordner wird auf dem Docker-Host angelegt und für UID ${t.uid} beschreibbar gemacht. Ports: automatisch die nächsten freien gewählt (${sug.used.length} Ports sind bereits belegt) – vor dem Anlegen wird nochmals auf Überschneidungen geprüft.`;
  await loadTimings(true);
  const dtx = [durText("create", createGame, "Anlegen bis spielbereit"), durText("copy", createGame, "Spieldateien kopieren"),
               durText("install", createGame, "Installation")].filter(Boolean);
  if (dtx.length) $("#createHint").textContent = "⏱ " + dtx.join(" · ") + " · " + $("#createHint").textContent;
  else $("#createHint").textContent = "⏱ Für dieses Spiel gibt es noch keine Messung – die Dauer wird beim ersten Anlegen festgehalten. · " + $("#createHint").textContent;
  const pr = sug.port_range;
  if (pr && pr.range){
    const msg = !pr.movable ? `⚠ ${t.label} lässt sich nicht in den freigegebenen Bereich ${pr.range} legen (Ports stehen fest in der Spielkonfiguration bzw. werden sonst falsch gemeldet) – Standardports, aus dem Internet nur mit eigener Weiterleitung erreichbar, im LAN problemlos.`
      : pr.outside.length ? `⚠ Bereich ${pr.range} ist voll – außerhalb liegen: ${pr.outside.map(o => o.port).join(", ")}. Aus dem Internet nur mit eigener Weiterleitung erreichbar.`
      : `✓ Alle Internet-Ports liegen im freigegebenen Bereich ${pr.range}. Verwaltungsports (RCON, Webkonsole) bleiben bewusst außerhalb – die braucht nur das LAN.`;
    $("#createHint").textContent = msg + " · " + $("#createHint").textContent;
  }
  const usedSet = new Set(sug.used);
  $$('[data-cf$="port"]').forEach(i => i.addEventListener("input", () => {
    const v = parseInt(i.value, 10), clash = usedSet.has(v);
    i.style.borderColor = clash ? "var(--bad)" : ""; i.title = clash ? "Port ist bereits belegt" : "";
  }));
}

// Vor dem Anlegen von Servern: Platz auf der Spiele-Partition prüfen (Warnung unter 500 GB)
const fmtGB = b => (b / 1e9).toFixed(b < 1e11 ? 1 : 0) + " GB";
async function diskOkForCreate(n){
  let g; try { g = await api("/api/storage/games?fresh=1"); } catch { return true; }
  if (!g || !g.low) return true;
  return confirm(`⚠ Auf der Spiele-Partition (${g.path}) sind nur noch ${fmtGB(g.free)} von ${fmtGB(g.total)} frei – weniger als 500 GB.\n\nTrotzdem ${n || 1} Server anlegen?`);
}
let dashDiskAt = 0;
async function refreshDashDisk(){
  if (Date.now() - dashDiskAt < 120000) return;
  dashDiskAt = Date.now();
  let g; try { g = await api("/api/storage/games"); } catch { return; }
  const el = $("#dashDisk"); if (!el) return;
  el.innerHTML = g && g.low ? `<div class="srvcheck warn" style="margin-bottom:12px">⚠ Spiele-Partition fast voll: nur noch <b>${fmtGB(g.free)}</b> von ${fmtGB(g.total)} frei auf <code>${esc(g.path)}</code> (Warnung unter 500 GB). Neue Server nur nach Rückfrage.</div>` : "";
}
$("#btnCreate").onclick = async () => {
  const values = Object.fromEntries($$("[data-cf]").map(i => [i.dataset.cf, i.value.trim()]));
  const count = Math.max(1, Math.min(10, parseInt($("#createCount").value, 10) || 1));
  if (!await diskOkForCreate(count)) return;
  if (count > 1){
    if (!confirm(`${count} × ${tpl.templates[createGame].label} anlegen – ab „${values.name}“, Nummern/Ports/Ordner werden hochgezählt, nacheinander?`)) return;
    try {
      const job = await api("/api/create/batch", {body: {game: createGame, values, data_dir: $("#createDataDir").value.trim(), host: $("#createHost").value.trim(), count, n: createN}});
      toast("Lege an: " + job.names.join(", "));
      $("#createJob").classList.remove("hidden"); $("#btnCreateOpen").classList.add("hidden");
      pollJob(job.id);
    } catch(err){ toast(err.message, true); }
    return;
  }
  if (!confirm(`1 × ${tpl.templates[createGame].label}-Server „${values.name}“ anlegen und starten? (Für mehrere: Feld „Anzahl“)\nDaten: ${$("#createDataDir").value}`)) return;
  try {
    const job = await api("/api/create", {body:{game: createGame, values, data_dir: $("#createDataDir").value.trim(), host: $("#createHost").value.trim()}});
    $("#createJob").classList.remove("hidden"); $("#btnCreateOpen").classList.add("hidden");
    pollJob(job.id);
  } catch(err){ toast(err.message, true); }
};
async function cancelJob(id){
  if (!confirm("Anlegen abbrechen?\nLaufende Schritte werden gestoppt, der Container und der neu angelegte Datenordner gelöscht.")) return;
  try { const r = await api(`/api/jobs/${id}/cancel`, {method: "POST"}); toast("Abgebrochen" + (r.log.length ? ": " + r.log.join(" · ") : "")); }
  catch (e){ toast(e.message, true); }
  refreshActivity(); loadServers();
}
function pollJob(id){
  clearTimeout(jobTimer);
  api(`/api/jobs/${id}`).then(async j => {
    $("#createStep").textContent = j.error ? "Fehler: " + j.error : j.done ? "Fertig ✓" : j.step;
    $("#createStep").style.color = j.error ? "var(--bad)" : j.done ? "var(--ok)" : "";
    $("#createLog").textContent = j.log.join("\n");
    const pg = j.progress;
    $("#createProg").classList.toggle("hidden", !pg || j.done);
    if (pg){
      $("#createProg i").style.width = Math.min(100, pg.pct) + "%";
      $("#createProg .s").textContent = `${pg.label} · ${pg.pct.toFixed(1)} %` + (pg.done_bytes != null ? ` · ${fmtBytes(pg.done_bytes)} / ${fmtBytes(pg.total_bytes)}` : pg.total_files ? ` · ${pg.done_files} / ${pg.total_files} Dateien` : "") + (pg.eta ? ` · noch ${fmtEta(pg.eta)} (fertig ca. ${etaClock(pg.eta)} Uhr)` : "");
    }
    if (j.server_id){ await loadServers(); $("#btnCreateOpen").classList.remove("hidden"); $("#btnCreateOpen").onclick = () => selectServer(servers.find(s => s.id === j.server_id)); }
    $("#btnCreateCancel").classList.toggle("hidden", !!j.done);
    $("#btnCreateCancel").onclick = () => cancelJob(id);
    if (!j.done) jobTimer = setTimeout(() => pollJob(id), 2000);
  }).catch(err => { $("#createStep").textContent = err.message; });
}

/* ================= Benutzer & Profile ================= */
let U = {users: [], profiles: [], levels: {}, level_hints: {}, rights: {}, games_used: []}, uSel = new Set(), uProfFilter = "";
const LV_SHORT = {0: "–", 1: "Sehen", 2: "Bedienen", 3: "Verwalten", 4: "Anlegen"};
const LV_COL = {0: "#555c69", 1: "#6b7a8f", 2: "#3e8f5a", 3: "#3e6fa8", 4: "#b5562b"};
const profOf = id => U.profiles.find(p => p.id === id);
const uProfs = u => (u.profiles || []).map(profOf).filter(Boolean);
function mergePerms(ids){       // wie im Backend: je Spiel die höchste Stufe aller Profile
  const prs = ids.map(profOf).filter(Boolean);
  if (!prs.length) return {"*": 0};
  const star = Math.max(...prs.map(p => +(p.perms["*"] ?? 0))), out = {"*": star};
  new Set(prs.flatMap(p => Object.keys(p.perms))).forEach(k => { if (k === "*") return;
    const v = Math.max(...prs.map(p => +(k in p.perms ? p.perms[k] : (p.perms["*"] ?? 0)))); if (v !== star) out[k] = v; });
  return out;
}
function uAvatar(u, adm){
  const ini = esc(u.username.slice(0, 1).toUpperCase());
  return u.avatar ? `<span class="uav img" title="${esc(u.player || "")}${u.steamid ? " · " + esc(u.steamid) : ""}"><img src="${esc(u.avatar)}" alt="" referrerpolicy="no-referrer" onerror="this.parentNode.classList.remove('img');this.parentNode.textContent='${ini}'"></span>`
    : `<span class="uav" title="${u.steamid ? "" : "kein Steam-Konto verknüpft (unter Spieler → ✎ → Tool-Konto)"}">${ini}</span>`;
}
function permChips(perms, max = 6){
  const p = perms || {}, def = +(p["*"] ?? 0);
  const ex = Object.entries(p).filter(([k, v]) => k !== "*" && +v !== def);
  return `<span class="lvchip" style="--c:${LV_COL[def]}">Alle: ${LV_SHORT[def]}</span>` +
    ex.slice(0, max).map(([k, v]) => `<span class="lvchip" style="--c:${LV_COL[+v]}">${esc(GAMES[k]?.short || k)}: ${LV_SHORT[+v]}</span>`).join("") +
    (ex.length > max ? `<span class="hint">+${ex.length - max}</span>` : "");
}
async function loadUsers(){
  try { U = await api("/api/users"); } catch (err) { return toast(err.message, true); }
  renderProfiles(); renderUserCards(); renderPending();
  $("#uBulkProfile").innerHTML = U.profiles.map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
}
function renderProfiles(){
  const cnt = id => U.users.filter(u => (u.profiles || []).includes(id) && u.role !== "admin").length;
  $("#uProfiles").innerHTML = U.profiles.map(p => `<div class="upcard ${uProfFilter === p.id ? "on" : ""}" data-upf="${esc(p.id)}" style="--c:${esc(p.color || "#6b7a8f")}">
      <div class="uph"><b>${esc(p.name)}</b><span class="hint">${cnt(p.id)} Benutzer</span><button type="button" class="small" data-upedit="${esc(p.id)}" title="Profil bearbeiten">✎</button></div>
      <div class="hint">${esc(p.desc || "")}</div>
      <div class="lvchips">${permChips(p.perms, 4)}${(p.rights || []).includes("tournament") ? `<span class="lvchip" style="--c:#d9a441">🏆 Turnier</span>` : ""}</div></div>`).join("") +
    `<div class="upcard upnew" id="uProfAdd"><b>＋ Neues Profil</b><div class="hint">Rechte-Vorlage für mehrere Benutzer</div></div>`;
  $$("[data-upf]").forEach(c => c.onclick = e => { if (e.target.closest("[data-upedit]")) return; uProfFilter = uProfFilter === c.dataset.upf ? "" : c.dataset.upf; renderProfiles(); renderUserCards(); });
  $$("[data-upedit]").forEach(b => b.onclick = () => openProfile(profOf(b.dataset.upedit)));
  $("#uProfAdd").onclick = () => openProfile(null);
}
function renderPending(){
  const pend = U.users.filter(u => u.pending);
  $("#uPendingPanel").classList.toggle("hidden", !pend.length);
  $("#uPendBadge").textContent = pend.length || ""; $("#uPendBadge").classList.toggle("hidden", !pend.length);
  $("#uPending").innerHTML = pend.map(u => `<div class="ucard" style="--c:#d9a441" data-upend="${esc(u.username)}">
    <div class="uch">${uAvatar(u)}<div class="ucn"><b>${esc(u.steam_name || u.username)}</b><div class="hint">Benutzer ${esc(u.username)}${u.steamid ? ` · <a href="https://steamcommunity.com/profiles/${esc(u.steamid)}" target="_blank" rel="noopener">Steam-Profil ↗</a>` : ""} · ${u.created ? fmtDate(u.created) : ""}</div></div></div>
    <div class="lvchips">${U.profiles.filter(p => p.id !== "oeffentlich").map(p => `<label class="lvchip" style="--c:${esc(p.color || "#6b7a8f")};cursor:pointer"><input type="checkbox" data-pp="${esc(p.id)}" style="width:auto;margin-right:4px">${esc(p.name)}</label>`).join("")}</div>
    <div class="ucf"><span class="hint">ohne Auswahl: nur öffentliche Seite</span><span><button class="small primary" data-uapprove="${esc(u.username)}">Freigeben</button><button class="small danger" data-udel="${esc(u.username)}" title="Ablehnen (Konto löschen)">Ablehnen</button></span></div></div>`).join("");
  $$("[data-uapprove]").forEach(b => b.onclick = async () => {
    const card = b.closest("[data-upend]"), profiles = [...card.querySelectorAll("[data-pp]")].filter(c => c.checked).map(c => c.dataset.pp);
    try { await api(`/api/users/${b.dataset.uapprove}/approve`, {body: {profiles}}); toast(`${b.dataset.uapprove} freigegeben`); loadUsers(); } catch (e) { toast(e.message, true); }
  });
  $$("#uPending [data-udel]").forEach(b => b.onclick = async () => {
    if (!confirm(`Registrierung von ${b.dataset.udel} ablehnen und Konto löschen?`)) return;
    try { await api(`/api/users/${b.dataset.udel}`, {method: "DELETE"}); loadUsers(); } catch (e) { toast(e.message, true); }
  });
}
function renderUserCards(){
  const f = $("#uFilter").value.trim().toLowerCase();
  const list = U.users.filter(u => !u.pending && (!f || [u.username, u.note, u.player, ...uProfs(u).map(p => p.name)].filter(Boolean).join(" ").toLowerCase().includes(f))
    && (!uProfFilter || (u.profiles || []).includes(uProfFilter)));
  $("#uCount").textContent = `${U.users.length}${list.length !== U.users.length ? ` · ${list.length} angezeigt` : ""}`;
  for (const n of [...uSel]) if (!U.users.some(u => u.username === n)) uSel.delete(n);
  $("#uCards").innerHTML = list.map(u => {
    const prs = uProfs(u), pr = prs[0], adm = u.role === "admin", own = Object.keys(u.own_perms || {}).length + (u.own_rights || []).length;
    return `<div class="ucard ${uSel.has(u.username) ? "sel" : ""}" style="--c:${adm ? "#e5534b" : esc(pr?.color || "#555c69")}">
      <div class="uch">${adm ? "" : `<input type="checkbox" data-usel="${esc(u.username)}" ${uSel.has(u.username) ? "checked" : ""} style="width:auto">`}
        ${uAvatar(u, adm)}
        <div class="ucn"><b>${esc(u.username)}</b>${me && u.username === me.username ? ' <span class="pill">du</span>' : ""}
          <div class="hint">${esc(u.note || "")}${u.player ? `${u.note ? " · " : ""}🎮 ${esc(u.player)}` : ""}</div></div>
        <span class="ubadges">${adm ? `<span class="ubadge" style="--c:#e5534b">Administrator</span>` : prs.length ? prs.map(p => `<span class="ubadge" style="--c:${esc(p.color || "#6b7a8f")}">${esc(p.name)}</span>`).join("") : `<span class="ubadge">${u.public_only ? "🌐 nur öffentliche Seite" : u.role === "viewer" ? "Nur ansehen" : "ohne Profil"}</span>`}</span></div>
      <div class="lvchips">${adm ? `<span class="lvchip" style="--c:#e5534b">alles</span>` : permChips(u.perms) + ((u.rights || []).includes("tournament") ? `<span class="lvchip" style="--c:#d9a441">🏆 Turnier</span>` : "")}
        ${own && !adm ? `<span class="hint" title="eigene Abweichungen vom Profil">✱ ${own} Abweichung${own > 1 ? "en" : ""}</span>` : ""}</div>
      <div class="ucf"><span class="hint">Login: ${u.last_login ? fmtDate(u.last_login) : "nie"}</span>
        <span><button class="small" data-uedit="${esc(u.username)}">Bearbeiten</button><button class="small danger" data-udel="${esc(u.username)}" title="Löschen">✕</button></span></div></div>`;
  }).join("") || `<div class="hint">Keine Benutzer${uProfFilter ? " mit diesem Profil" : ""}.</div>`;
  $$("[data-usel]").forEach(c => c.onchange = () => { c.checked ? uSel.add(c.dataset.usel) : uSel.delete(c.dataset.usel); c.closest(".ucard").classList.toggle("sel", c.checked); uBulkInfo(); });
  $$("[data-uedit]").forEach(b => b.onclick = () => openUser(U.users.find(x => x.username === b.dataset.uedit)));
  $$("[data-udel]").forEach(b => b.onclick = async () => {
    if (!confirm(`Benutzer ${b.dataset.udel} löschen?`)) return;
    try { await api(`/api/users/${b.dataset.udel}`, {method: "DELETE"}); loadUsers(); } catch (err) { toast(err.message, true); }
  });
  uBulkInfo();
}
function uBulkInfo(){ $("#uSelCount").textContent = `${uSel.size} ausgewählt`; $("#uBulk").classList.toggle("dim", !uSel.size); }
$("#uFilter").addEventListener("input", renderUserCards);
$("#btnUBulk").onclick = async () => {
  if (!uSel.size) return toast("Erst Benutzer auswählen", true);
  try {
    const r = await api("/api/users-bulk", {body: {usernames: [...uSel], profile: $("#uBulkProfile").value, mode: $("#uBulkMode").value, clear_own: $("#uBulkClear").checked}});
    toast(`${r.changed} Benutzer geändert`); uSel.clear(); loadUsers();
  } catch (e) { toast(e.message, true); }
};
// Rechte-Editor: Zeile je Spiel mit Stufen-Buttons; inherit = Wert aus Profil (nur bei Benutzern)
function permEditor(root, values, inherit, allGames){
  const games = Object.entries(GAMES).filter(([k]) => allGames || U.games_used.includes(k) || k in values)
    .sort((a, b) => a[1].label.localeCompare(b[1].label));
  const row = (k, label, icon) => {
    const own = k in values;
    const eff = own ? +values[k] : inherit ? +(k in inherit ? inherit[k] : ("*" in values ? values["*"] : (inherit["*"] ?? 0))) : +(values["*"] ?? 0);
    return `<div class="perow ${own ? "own" : ""}" data-pek="${k}"><span class="pelabel">${icon}${esc(label)}</span><span class="pebtns">
      ${(inherit || k !== "*") ? `<button type="button" class="pe0 ${!own ? "on" : ""}" data-pev="" title="${inherit ? "wie im Profil" : "wie „Alle Spiele“"}">${inherit ? "Profil" : "Standard"}</button>` : ""}
      ${[0, 1, 2, 3, 4].map(v => `<button type="button" data-pev="${v}" class="${eff === v ? (own ? "on" : "inh") : ""}" style="--c:${LV_COL[v]}" title="${esc(U.level_hints[v] || U.levels[v] || "")}">${LV_SHORT[v]}</button>`).join("")}</span></div>`;
  };
  root.innerHTML = row("*", "Alle Spiele", "") + games.map(([k, g]) => row(k, g.label, `<span class="gtile" style="background:${g.color};width:16px;height:16px">${gicon(k, 11)}</span>`)).join("");
  root.querySelectorAll("[data-pev]").forEach(b => b.onclick = () => {
    const k = b.closest("[data-pek]").dataset.pek;
    if (b.dataset.pev === "") delete values[k]; else values[k] = +b.dataset.pev;
    permEditor(root, values, inherit, allGames);
    root.dispatchEvent(new Event("permchange"));
  });
}
const legend = () => Object.entries(U.level_hints).map(([k, h]) => `<b>${LV_SHORT[k]}</b>: ${esc(h)}`).join(" · ");
let ufEdit = null, ufVals = {}, ufKind = "user", ufProfiles = [];
function openUser(u){
  ufEdit = u ? u.username : null; ufVals = {...(u?.own_perms || {})}; ufKind = u?.role === "admin" ? "admin" : "user";
  ufProfiles = u ? [...(u.profiles || [])] : (profOf("oeffentlich") ? ["oeffentlich"] : []);      // neue Benutzer: erst mal nur öffentliche Seite
  $("#uFormTitle").textContent = u ? `Benutzer ${u.username}` : "Neuer Benutzer";
  $("#ufName").value = u?.username || ""; $("#ufName").disabled = !!u;
  $("#ufPw").value = ""; $("#ufPwLabel").textContent = u ? "Neues Passwort (leer = unverändert)" : "Passwort (min. 6 Zeichen)";
  $("#ufNote").value = u?.note || "";
  $("#ufRights").innerHTML = Object.entries(U.rights).map(([k, l]) => `<label><input type="checkbox" data-ufr="${k}" ${(u?.own_rights || []).includes(k) ? "checked" : ""}> ${esc(l)}</label>`).join("");
  $("#ufOwn").open = Object.keys(ufVals).length > 0;
  $("#ufLegend").innerHTML = legend();
  ufRender();
  $("#dlgUser").showModal();
}
function ufRender(){
  $$("#ufKind [data-kind]").forEach(b => b.classList.toggle("active", b.dataset.kind === ufKind));
  $("#ufProfileBox").style.display = ufKind === "admin" ? "none" : "";
  $("#ufAdminHint").style.display = ufKind === "admin" ? "" : "none";
  $("#ufProfiles").innerHTML = U.profiles.map(p =>
    `<button type="button" class="ufpc ${ufProfiles.includes(p.id) ? "on" : ""}" data-ufp="${esc(p.id)}" style="--c:${esc(p.color || "#6b7a8f")}"><b>${ufProfiles.includes(p.id) ? "✓ " : ""}${esc(p.name)}</b><span class="hint">${esc(p.desc || "")}</span></button>`).join("");
  $$("[data-ufp]").forEach(b => b.onclick = () => {
    const id = b.dataset.ufp;
    if (ufProfiles.includes(id)) ufProfiles = ufProfiles.filter(x => x !== id);
    else if (id === "oeffentlich") ufProfiles = ["oeffentlich"];               // „Nur öffentliche Seite“ schließt alles andere aus
    else ufProfiles = [...ufProfiles.filter(x => x !== "oeffentlich"), id];
    ufRender();
  });
  const inherit = mergePerms(ufProfiles);
  permEditor($("#ufPerms"), ufVals, inherit, $("#ufAllGames").checked);
  const n = Object.keys(ufVals).length;
  $("#ufOwnInfo").textContent = n ? `(${n})` : "(keine – es gilt nur das Profil)";
  $("#ufPubOnly").style.display = !Object.values(mergePerms(ufProfiles)).some(v => +v > 0) && !Object.values(ufVals).some(v => +v > 0) ? "" : "none";
}
$("#ufPerms").addEventListener("permchange", () => { const n = Object.keys(ufVals).length; $("#ufOwnInfo").textContent = n ? `(${n})` : "(keine – es gilt nur das Profil)"; });
$$("#ufKind [data-kind]").forEach(b => b.onclick = () => { ufKind = b.dataset.kind; ufRender(); });
$("#ufAllGames").onchange = ufRender;
$("#ufOwnReset").onclick = () => { ufVals = {}; $$("#ufRights [data-ufr]").forEach(c => c.checked = false); ufRender(); };
$("#btnUfCancel").onclick = () => $("#dlgUser").close();
$("#btnUNew").onclick = () => openUser(null);
$("#uForm").addEventListener("submit", async e => {
  e.preventDefault();
  const body = {username: ufEdit || $("#ufName").value.trim(), note: $("#ufNote").value.trim(),
    role: ufKind === "admin" ? "admin" : "user", profiles: ufKind === "admin" ? null : ufProfiles,
    perms: ufKind === "admin" ? null : ufVals, rights: ufKind === "admin" ? null : $$("#ufRights [data-ufr]").filter(c => c.checked).map(c => c.dataset.ufr)};
  const pw = $("#ufPw").value;
  if (pw) body.password = pw;
  if (!ufEdit && !pw) return toast("Passwort fehlt", true);
  try {
    if (ufEdit) await api(`/api/users/${ufEdit}`, {method: "PUT", body}); else await api("/api/users", {body});
    $("#dlgUser").close(); toast(ufEdit ? "Gespeichert" + (pw ? " – Benutzer muss sich neu anmelden" : "") : "Benutzer angelegt"); loadUsers();
  } catch (err) { toast(err.message, true); }
});
let pfEdit = null, pfVals = {};
function openProfile(p){
  pfEdit = p ? p.id : ""; pfVals = {...(p?.perms || {"*": 1})};
  $("#pfTitle").textContent = p ? `Profil ${p.name}` : "Neues Profil";
  $("#pfName").value = p?.name || ""; $("#pfColor").value = p?.color || "#3e8f5a"; $("#pfDesc").value = p?.desc || "";
  $("#pfRights").innerHTML = Object.entries(U.rights).map(([k, l]) => `<label><input type="checkbox" data-pfr="${k}" ${(p?.rights || []).includes(k) ? "checked" : ""}> ${esc(l)}</label>`).join("");
  $("#btnPfDel").style.visibility = p ? "" : "hidden";
  permEditor($("#pfPerms"), pfVals, null, $("#pfAllGames").checked);
  $("#dlgProfile").showModal();
}
$("#pfAllGames").onchange = () => permEditor($("#pfPerms"), pfVals, null, $("#pfAllGames").checked);
$("#btnPfCancel").onclick = () => $("#dlgProfile").close();
$("#btnUNewProfile").onclick = () => openProfile(null);
$("#btnPfDel").onclick = async () => {
  const n = U.users.filter(u => (u.profiles || []).includes(pfEdit)).length;
  if (!confirm(`Profil löschen?${n ? ` ${n} Benutzer verlieren es (behalten nur ihre eigenen Rechte).` : ""}`)) return;
  try { await api(`/api/user-profiles/${pfEdit}`, {method: "DELETE"}); $("#dlgProfile").close(); if (uProfFilter === pfEdit) uProfFilter = ""; loadUsers(); } catch (e) { toast(e.message, true); }
};
$("#pfForm").addEventListener("submit", async e => {
  e.preventDefault();
  if (!("*" in pfVals)) pfVals["*"] = 0;
  try {
    await api("/api/user-profiles", {body: {id: pfEdit, name: $("#pfName").value.trim(), color: $("#pfColor").value, desc: $("#pfDesc").value.trim(),
      perms: pfVals, rights: $$("#pfRights [data-pfr]").filter(c => c.checked).map(c => c.dataset.pfr)}});
    $("#dlgProfile").close(); toast("Profil gespeichert"); loadUsers();
  } catch (err) { toast(err.message, true); }
});
$("#btnMyPw").onclick = async () => {
  $("#pwForm").reset();
  let m = null; try { m = await api("/api/me"); } catch {}
  const u = (m && m.user) || {}, p = (m && m.player) || {};
  $("#accInfo").innerHTML = `<b>${esc(u.username || "")}</b> · ${esc(u.role === "admin" ? "Administrator" : u.role === "viewer" ? "nur ansehen" : "Benutzer")}${p.admin && p.admin.length ? ` · ★ Admin auf: ${esc(p.admin.map(g => g === "*" ? "alle" : (GAMES[g]?.short || g)).join(", "))}` : ""}`;
  $("#accNick").value = p.nick || ""; $("#accNick").placeholder = p.name || "Name im Spiel";
  $("#accSteam").value = p.steamid || "";
  $("#dlgPw").showModal();
};
$("#btnAccSave").onclick = async () => {
  try { await api("/api/me/profile", {method: "PUT", body: {nick: $("#accNick").value.trim(), steamid: $("#accSteam").value.trim() || null}}); toast("Profil gespeichert"); }
  catch (e){ toast(e.message, true); }
};
$("#btnPwCancel").onclick = () => $("#dlgPw").close();
$("#pwForm").addEventListener("submit", async e => {
  e.preventDefault();
  const f = $("#pwForm");
  if (f.new1.value !== f.new2.value) return toast("Neue Passwörter stimmen nicht überein", true);
  try { await api("/api/me/password", {body:{old_password: f.old.value, new_password: f.new1.value}}); $("#dlgPw").close(); toast("Passwort geändert"); }
  catch(err){ toast(err.message, true); }
});

/* ================= Handy-Ansicht ================= */
// Handy erkannt (schmaler Bildschirm/Touch) -> abgespeckte Ansicht; „Vollansicht“ merkt sich die Wahl
const mobPref = () => { try { return localStorage.getItem("gsmView") || ""; } catch { return ""; } };
function isMobile(){
  const q = new URLSearchParams(location.search);
  if (q.has("mobil")) return true;
  if (q.has("voll")) return false;
  if (mobPref() === "full") return false;
  if (mobPref() === "mobile") return true;
  return matchMedia("(max-width: 760px)").matches || /Android|iPhone|iPod|Mobile/i.test(navigator.userAgent);
}
let mobTimer = null, mobLive = null, mobOv = [], mobAct = {items: [], jobs: []}, mobCache = null, mobTick = 0;
async function startMobile(){
  $("#login").classList.add("hidden"); $("#pub").classList.add("hidden"); $("#app").classList.add("hidden"); $("#mob").classList.remove("hidden");
  try { const [m, g] = await Promise.all([api("/api/me"), api("/api/games")]); me = m.user; GAMES = g.games; } catch {}
  const tick = async () => {
    if (document.hidden) return;
    mobTick++;
    try { mobLive = await api("/api/live"); } catch {}
    if (mobTick % 3 === 1){
      const r = await Promise.allSettled([api("/api/overview"), api("/api/activity"), api("/api/cache")]);
      if (r[0].status === "fulfilled") mobOv = r[0].value;
      if (r[1].status === "fulfilled") mobAct = r[1].value;
      if (r[2].status === "fulfilled") mobCache = r[2].value;
    }
    renderMobile();
  };
  clearInterval(mobTimer); mobTimer = setInterval(tick, 2000); tick();
}
function mobTile(label, val, sub, pct, color){
  return `<div class="mobtile"><div class="k">${label}</div><div class="v">${val}</div><div class="s">${sub || "&nbsp;"}</div>
    ${pct != null ? `<div class="bar"><i class="${color ? "" : lvl(pct)}" style="width:${Math.max(pct > 0 ? 2 : 0, Math.min(100, pct))}%;${color ? "background:" + color : ""}"></i></div>` : ""}</div>`;
}
function renderMobile(){
  const L = mobLive || {}, n = L.net || {}, P = L.peak24 || {};
  const memPct = L.mem_total_mb ? L.mem_used_mb / L.mem_total_mb * 100 : null;
  const sc = k => niceMax(Math.max(1e6, P[k] || 0));
  const on = mobOv.filter(o => o.online), pl = on.reduce((a, o) => a + (o.humans || 0), 0);
  $("#mobSum").innerHTML = `<b>${pl}</b> Spieler auf <b>${on.length}</b> von ${mobOv.length} Servern`;
  $("#mobTime").textContent = new Date().toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit", second: "2-digit"});
  const ct = L.cache && L.cache.tx_bps;
  $("#mobLoad").innerHTML =
    mobTile("CPU", L.cpu != null ? Math.round(L.cpu) + " %" : "–", "", L.cpu) +
    mobTile("RAM", memPct != null ? Math.round(memPct) + " %" : "–", L.mem_used_mb ? fmtMem(L.mem_used_mb) + " belegt" : "", memPct) +
    mobTile("Internet", `<span style="color:${C_DOWN}">↓</span> ${fmtRate(n.rx_bps)}`, `↑ ${fmtRate(n.tx_bps)}`, n.rx_bps != null ? n.rx_bps / sc("rx") * 100 : null, C_DOWN) +
    mobTile("Lancache an Clients", fmtRate(ct), mobCache && mobCache.last_day && mobCache.last_day.hit_ratio != null ? `${mobCache.last_day.hit_ratio} % aus dem Cache (24 h)` : "", ct != null ? ct / sc("cache") * 100 : null, "var(--ct)");
  // Gerade los: Downloads, Prefill, Installationen, Anlegen, Probleme
  const items = [];
  (mobAct.jobs || []).forEach(j => items.push(`<div class="mobitem ${j.error ? "bad" : ""}"><div class="t">${gameTile(j.game, 14)}${esc(j.title || "Neuer Server")}</div><div class="s">${esc(j.error || j.step || "…")}</div></div>`));
  (mobAct.items || []).forEach(it => {
    const p = it.progress;
    if (!p) return;
    const lim = p.limit && p.limit.bps ? ` / max ${fmtRate(p.limit.bps)}` : "";
    items.push(`<div class="mobitem"><div class="t">${it.prefill ? "⇩" : gameTile(it.game, 14)} ${esc(it.name)}</div>
      <div class="s">${esc(p.label || "")} · ${(p.pct || 0).toFixed(0)} %${p.rate != null ? " · " + fmtRate(p.rate) + lim : ""}</div>
      <div class="bar"><i style="width:${Math.min(100, p.pct || 0)}%;background:var(--ct)"></i></div></div>`);
  });
  ((mobCache && mobCache.live_downloads) || []).slice(0, 4).forEach(d => items.push(`<div class="mobitem"><div class="t">⬇ ${esc(d.name || cacheName(d.service))}</div>
      <div class="s">${esc(d.player || d.client || d.ip)} · ${fmtRate(d.bps)}${d.hit_pct != null ? ` · ${d.hit_pct} % aus dem Cache` : ""}</div></div>`));
  mobOv.forEach(o => (o.problems || []).filter(p => p.level !== "info").forEach(p => items.push(`<div class="mobitem warn"><div class="t">⚠ ${esc(o.server.name)}</div><div class="s">${esc(p.title)}</div></div>`)));
  $("#mobNow").innerHTML = items.length ? items.join("") : `<div class="hint">Gerade nichts los – keine Downloads, Updates oder Probleme.</div>`;
  // Server: zuerst mit Spielern, dann online, dann offline
  const srv = [...mobOv].sort((a, b) => (b.humans || 0) - (a.humans || 0) || (b.online ? 1 : 0) - (a.online ? 1 : 0) || String(a.server.name).localeCompare(String(b.server.name)));
  $("#mobSrv").innerHTML = srv.map(o => {
    const g = gameOf(o.server), slots = o.visible_players > 0 ? o.visible_players : o.max_players;
    const where = o.online ? (o.track_name || (o.workshop && o.workshop.title) || o.map_title || o.map || "") : (o.sleeping ? "Ruhemodus" : "offline");
    const ld = mobLive && mobLive.servers && mobLive.servers[o.server.id];
    return `<div class="mobsrv ${o.online ? "" : "off"}">${gameTile(g, 18)}
      <div style="min-width:0"><div class="n"><span class="dot" style="background:${o.online ? "var(--ok)" : o.sleeping ? "var(--muted)" : "var(--bad)"}"></span>${esc(o.server.name)}</div>
        <div class="m">${esc(where)}${ld && ld.cpu_host != null ? ` · CPU ${ld.cpu_host.toFixed(1)} %` : ""}</div></div>
      <div class="p">${o.online ? `${o.players_unknown ? "–" : o.humans ?? 0}${slots ? `<small>/${slots}</small>` : ""}${o.bots ? `<small> +${o.bots}🤖</small>` : ""}` : ""}</div></div>`;
  }).join("") || `<div class="hint">Noch keine Server.</div>`;
}
$("#mobFull").onclick = () => { try { localStorage.setItem("gsmView", "full"); } catch {} clearInterval(mobTimer); $("#mob").classList.add("hidden"); start(); };
$("#mobLogout").onclick = async e => { e.preventDefault(); clearInterval(mobTimer); await api("/api/logout", {method: "POST"}); $("#mob").classList.add("hidden"); showPublic(); };

/* ================= Start ================= */
async function start(){
  if (isMobile()) return startMobile();
  clearInterval(pubTimer);
  $("#login").classList.add("hidden"); $("#pub").classList.add("hidden"); $("#app").classList.remove("hidden");
  try {
    const [m, g] = await Promise.all([api("/api/me"), api("/api/games")]);
    me = m.user; GAMES = g.games; dockerOn = g.docker;
    loadGameIcons().then(() => { renderServerList(); if (view === "dash") refreshDash(); });
    document.body.classList.toggle("not-admin", !me || me.role !== "admin");
    document.body.classList.toggle("no-tour", !me || !(me.role === "admin" || (me.rights || []).includes("tournament")));
    const allGames = Object.keys(GAMES);
    document.body.classList.toggle("no-create", !allGames.some(g => permFor(g) >= 4));
    applyPerm(4);
    $("#meName").textContent = me ? `${me.username} · ${me.role_label}` : "";
    [settings, presets, favs] = await Promise.all([api("/api/settings"), api("/api/match/presets"), api("/api/workshop/favorites")]);
  } catch(err){ toast(err.message, true); }
  refreshModeSelects();
  fillMapSelect("#mapSelect"); fillMapSelect("#qMap");
  $("#mapSelect").querySelector("optgroup[label^='★']")?.remove();
  mapHint($("#qMap").value, "", $("#qHint"));
  await loadServers();
  showView("dash");
  clearInterval(dashTimer);
  refreshHost();
  refreshCache();
  refreshActivity();
  let tick = 0;
  dashTimer = setInterval(() => { tick++; refreshCache(); if (tick % 2 === 0){ refreshDash(); refreshActivity(); } if (tick % 4 === 0) refreshHost(); }, 2500);
}
async function showVersion(){
  try {
    const v = await (await fetch("/api/version")).json();
    const d = v.date ? new Date(v.date).toLocaleString("de-DE", {day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit"}) : "";
    const txt = `Version ${v.version}${v.commit && v.commit !== "lokal" ? " (" + v.commit + ")" : ""}${d ? " · " + d : ""}`;
    $("#appVersion").textContent = txt; $("#loginVersion").textContent = txt; $("#pubVersion").textContent = txt;
    if (typeof loadedVersion !== "undefined" && loadedVersion === null) loadedVersion = v.version + v.commit;
  } catch {}
}
showVersion();
(async () => {
  const sq = new URLSearchParams(location.search).get("steam");
  if (sq){
    history.replaceState(null, "", location.pathname + location.hash);
    setTimeout(() => toast(({registriert: "Konto mit Steam angelegt – ein Admin schaltet dich frei", ok: "Mit Steam angemeldet",
      abgebrochen: "Steam-Anmeldung abgebrochen", ungueltig: "Steam-Anmeldung konnte nicht bestätigt werden", fehler: "Steam-Anmeldung fehlgeschlagen"})[sq] || sq,
      !["registriert", "ok"].includes(sq)), 600);
  }
  const me = await api("/api/me").catch(() => ({authenticated:false}));
  me.authenticated ? (me.user && me.user.public_only ? showPublic(me.user) : start()) : showPublic();
})();

$("#btnWeb").onclick = () => { if (current && current.web_url) window.open(current.web_url, "_blank", "noopener"); };

/* ================= Beitreten ================= */
function copyText(t){
  const done = () => toast(`Kopiert: ${t}`);
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t).then(done).catch(() => fallbackCopy(t, done));
  fallbackCopy(t, done);
}
function fallbackCopy(t, done){
  // ohne HTTPS gibt es keine Zwischenablage-API -> über ein unsichtbares Textfeld
  const ta = document.createElement("textarea"); ta.value = t; ta.setAttribute("readonly", "");
  ta.style.cssText = "position:fixed;top:0;left:0;width:1px;height:1px;opacity:0";
  document.body.appendChild(ta); ta.focus(); ta.select(); ta.setSelectionRange(0, t.length);
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  ta.remove();
  if (ok) done(); else prompt("Kopieren mit Strg+C:", t);
}
function copyQuiet(t, msg){
  const done = () => toast(msg || "Kopiert");
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t).then(done).catch(() => fallbackCopy(t, done));
  fallbackCopy(t, done);
}
let currentJoin = null;
function setJoin(j){
  currentJoin = j || null;
  $("#btnJoin").classList.toggle("hidden", !(j && j.url));
  $("#btnCopyAddr").classList.toggle("hidden", !j);
  $("#joinAddr").textContent = j ? j.address : "";
  $("#btnJoin").title = j ? (j.hint || "Beitreten") : "";
  $("#btnCopyAddr").title = j ? "Adresse kopieren" + (j.url ? "" : " – " + j.hint) : "";
}
$("#btnJoin").onclick = () => { if (currentJoin && currentJoin.url) location.href = currentJoin.url; };
$("#btnCopyAddr").onclick = () => { if (currentJoin) copyText(currentJoin.address); };

/* ================= Befehlsreferenz ================= */
function renderCmdRef(){
  if (!current) return;
  const g = gameOf(current), ref = COMMANDS[g] || {groups: {}}, remote = GAMES[g].console;
  $("#consoleForm").classList.toggle("hidden", !remote);
  $("#consoleOut").classList.toggle("hidden", !remote);
  $("#consoleNoRemote").classList.toggle("hidden", remote);
  $("#consoleNoRemote").textContent = remote ? "" : ref.note || "Keine Remote-Konsole.";
  $(".cmdref").classList.toggle("readonly", !remote);
  $("#cmdNote").textContent = remote ? (ref.note || "") + " Klick übernimmt den Befehl." : "Klick kopiert den Befehl.";
  const f = $("#cmdFilter").value.trim().toLowerCase();
  $("#cmdList").innerHTML = Object.entries(ref.groups).map(([grp, list]) => {
    const items = list.filter(([c, d]) => !f || c.toLowerCase().includes(f) || d.toLowerCase().includes(f));
    if (!items.length) return "";
    return `<div class="cmdgroup"><h3>${esc(grp)}</h3>${items.map(([c, d]) => `<button class="cmd" data-cmd-ref="${esc(c)}"><code>${esc(c)}</code><span>${esc(d)}</span></button>`).join("")}</div>`;
  }).join("") || `<div class="hint">Nichts gefunden.</div>`;
  $$("[data-cmd-ref]").forEach(b => b.onclick = () => {
    const c = b.dataset.cmdRef;
    if (!remote) return copyText(c);
    const inp = $("#consoleIn");
    inp.value = c; inp.focus();
    const m = c.match(/<[^>]+>/);   // ersten Platzhalter markieren
    if (m) inp.setSelectionRange(m.index, m.index + m[0].length);
  });
}
$("#cmdFilter").addEventListener("input", renderCmdRef);

/* ================= Update-Hinweis ================= */
let loadedVersion = null;
setInterval(async () => {
  try {
    const v = await (await fetch("/api/version", {cache: "no-store"})).json();
    const key = v.version + v.commit;
    if (loadedVersion === null) loadedVersion = key;
    else if (key !== loadedVersion) $("#updateBar").classList.remove("hidden");
  } catch {}
}, 60000);
$("#btnReloadApp").onclick = () => location.reload();

$$("#rangeSeg [data-range]").forEach(b => b.onclick = async () => {
  metricsRange = +b.dataset.range;
  try { localStorage.setItem("gsmRange", metricsRange); } catch {}
  await loadMetrics(true); refreshDash();
});

async function renderHistory(){
  if (!current) return;
  await loadMetrics();
  $("#svHistory").innerHTML = metricsHtml(current.id, GAMES[gameOf(current)]?.color || "var(--accent)");
}

/* ================= Installation / Update / Fehler ================= */
const fmtEta = s => s == null ? "" : s >= 3600 ? `${Math.floor(s/3600)} h ${Math.round(s%3600/60)} min` : s >= 60 ? `${Math.round(s/60)} min` : `${s} s`;
const etaClock = s => s ? new Date(Date.now() + s * 1000).toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"}) : "";
function progressText(p){
  return `${p.label} · ${p.pct.toFixed(1)} % · ${fmtBytes(p.done)} / ${fmtBytes(p.total)}` +
    (p.rate ? ` · ${fmtRate(p.rate)}` : "") + (p.eta ? ` · noch ${fmtEta(p.eta)} (fertig ca. ${etaClock(p.eta)} Uhr)` : "");
}
function installHtml(inst){
  if (!inst) return "";
  let h = "";
  if (inst.progress){
    const p = inst.progress;
    h += `<div class="instbar" data-stop><div class="bar"><i style="width:${Math.min(100, p.pct)}%"></i></div><div class="s">${esc(progressText(p))}</div></div>`;
  }
  (inst.errors || []).slice(0, 1).forEach(e => { h += `<div class="pill" style="color:var(--bad);border-color:#6b2a27;justify-self:start;white-space:normal" title="${esc(e.line)}">⚠ ${esc(e.text)}</div>`; });
  return h;
}
async function refreshActivity(){
  let a;
  try { a = await api("/api/activity"); } catch { return; }
  const parts = [];
  (a.jobs || []).forEach(j => {
    parts.push(`<div class="act ${j.error ? "err" : ""}" data-act-job="${esc(j.id)}">
      <div class="t">${gicon(j.game, 14)}<span class="n">${esc(j.title || `Neuer ${GAMES[j.game]?.short || j.game}-Server`)}</span></div>
      ${j.error ? `<button class="actx" data-act-jdis="${esc(j.id)}" title="Meldung entfernen">✕</button><div class="e">${esc(j.error)}</div>` : `<div class="bar indet"><i></i></div><div class="s">${esc(j.step || "…")}</div><button class="small danger mgronly" data-act-cancel="${esc(j.id)}" title="Anlegen abbrechen und aufräumen">✕ Abbrechen</button>`}</div>`);
  });
  (a.items || []).forEach(it => {
    const p = it.progress;
    if (!p) return;   // links nur Fortschritt anzeigen, keine Fehlermeldungen
    if (it.prefill){
      parts.push(`<div class="act" data-act-prefill="${esc(it.svc || "steam")}" title="Prefill öffnen">
        <div class="t">${gicon("prefill", 14)}<span class="n">${esc(it.name)}</span></div>
        <div class="bar"><i style="width:${Math.min(100, p.pct)}%"></i></div>
        <div class="s">${p.label && p.label !== "Vorladen" ? esc(p.label) + " · " : ""}${p.pct.toFixed(0)} %${p.rate != null ? " · " + fmtRate(p.rate) : ""}${p.limit ? (p.limit.kind === "gedrosselt" ? ` <span style="color:var(--accent)" title="${esc(p.limit.reason || "")}">🐢 max ${fmtRate(p.limit.bps || 0)}</span>` : p.limit.bps ? ` / max ${fmtRate(p.limit.bps)}` : " / max ∞") : ""}${p.apps_total ? ` · Spiel ${Math.min(p.apps_done + 1, p.apps_total)}/${p.apps_total}` : ""}</div></div>`);
      return;
    }
    parts.push(`<div class="act" data-act-sid="${esc(it.server_id)}" title="${esc(it.container)}">
      <div class="t">${gicon(it.game, 14)}<span class="n">${esc(it.name)}</span></div>
      <div class="bar"><i style="width:${Math.min(100, p.pct)}%"></i></div><div class="s">${esc(progressText(p))}</div>
      <button class="small danger mgronly" data-act-abort="${esc(it.server_id)}" title="Installation abbrechen: Server, Container und alle Spieldaten löschen">✕ Abbrechen</button></div>`);
  });
  $("#activity").innerHTML = parts.join("");
  $("#activity").classList.toggle("hidden", !parts.length);
  $$("[data-act-sid]").forEach(el => el.onclick = e => {
    if (e.target.closest("[data-act-dismiss]")) return;
    const s = servers.find(x => x.id === el.dataset.actSid); if (!s) return;
    selectServer(s); if (dockerOn && s.container) setTab("container");
  });
  $$("[data-act-dismiss]").forEach(b => b.onclick = async e => {
    e.stopPropagation();
    await api(`/api/activity/dismiss/${encodeURIComponent(b.dataset.actDismiss)}`, {method: "POST"}).catch(() => {});
    refreshActivity();
  });
  $$("[data-act-job]").forEach(el => el.onclick = e => { if (!e.target.closest("[data-act-jdis]")) showView("create"); });
  $$("[data-act-jdis]").forEach(b => b.onclick = async e => {
    e.stopPropagation();
    await api(`/api/activity/dismiss-job/${encodeURIComponent(b.dataset.actJdis)}`, {method: "POST"}).catch(() => {});
    refreshActivity();
  });
  $$("[data-act-abort]").forEach(b => b.onclick = async e => {
    e.stopPropagation();
    const s = servers.find(x => x.id === b.dataset.actAbort); if (!s) return;
    if (!confirm(`Installation von „${s.name}“ abbrechen?\nServer, Container und alle Spieldaten werden gelöscht.`)) return;
    try { await api(`/api/servers/${s.id}/delete`, {body: {remove_container: true, delete_data: true, confirm: s.name}}); toast(`${s.name} wird gelöscht`); setTimeout(async () => { await loadServers(); refreshActivity(); }, 2500); }
    catch (err){ toast(err.message, true); }
  });
  $$("[data-act-cancel]").forEach(b => b.onclick = e => { e.stopPropagation(); cancelJob(b.dataset.actCancel); });
  $$("[data-act-prefill]").forEach(el => el.onclick = () => { pfSvc = el.dataset.actPrefill || "steam"; showView("prefill"); });
}

/* ================= Lancache-Verlauf (bis 1 Jahr) ================= */
let cacheRange = (() => { try { return localStorage.getItem("gsmCacheRange") || "30d"; } catch { return "30d"; } })();
const CACHE_RANGES = {"24h": "24 Stunden", "7d": "7 Tage", "30d": "30 Tage", "90d": "90 Tage", "365d": "1 Jahr"};
$$("#cacheRangeSeg [data-crange]").forEach(b => b.onclick = () => {
  cacheRange = b.dataset.crange;
  try { localStorage.setItem("gsmCacheRange", cacheRange); } catch {}
  loadCacheHistory();
});
function fmtBucket(t, stepH){
  const d = new Date(t * 1000);
  if (stepH < 24) return d.toLocaleString("de-DE", {weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"});
  if (stepH === 24) return d.toLocaleDateString("de-DE", {weekday: "short", day: "2-digit", month: "2-digit", year: "numeric"});
  return "Woche ab " + d.toLocaleDateString("de-DE", {day: "2-digit", month: "2-digit", year: "numeric"});
}
// eigene, gut unterscheidbare Farben je Dienst für Diagramme
const SVC_CHART = {steam: "#4f9dde", wsus: "#f2c14e", windowsupdates: "#f2c14e", epicgames: "#d7dae0", blizzard: "#a37bff",
  origin: "#f57c3a", riot: "#e84a4a", uplay: "#2bc4a6", xboxlive: "#6cc04a", sony: "#3d55d6", nintendo: "#ff6fa8",
  apple: "#9aa3ad", wargaming: "#c28a4a", rockstar: "#ffcc00", _other: "#7d7466"};
const svcColor = s => SVC_CHART[(s || "").toLowerCase()] || "#8a7a66";
function cacheChart(points, stepH){
  const w = 900, h = 180, n = points.length || 1, bw = w / n;
  const max = Math.max(1, ...points.map(p => p.hit + p.miss));
  const order = {};       // Dienste nach Gesamtmenge, größter unten
  points.forEach(p => Object.entries(p.svc || {}).forEach(([s, [a, m]]) => { order[s] = (order[s] || 0) + a + m; }));
  const svcs = Object.keys(order).sort((a, b) => order[b] - order[a]);
  const bars = points.map((p, i) => {
    const x = (i * bw).toFixed(2), wd = Math.max(0.6, bw - (bw > 4 ? 1 : 0)).toFixed(2);
    let y = h, rects = "";
    const parts = svcs.length ? svcs.map(s => [s, ...((p.svc || {})[s] || [0, 0])]) : [["_", p.hit, p.miss]];
    for (const [s, a, m] of parts){
      const ha = a / max * (h - 4), hm = m / max * (h - 4);
      if (ha){ y -= ha; rects += `<rect x="${x}" y="${y.toFixed(1)}" width="${wd}" height="${ha.toFixed(1)}" fill="${svcs.length ? svcColor(s) : "var(--ok)"}"/>`; }
      if (hm){ y -= hm; rects += `<rect x="${x}" y="${y.toFixed(1)}" width="${wd}" height="${hm.toFixed(1)}" fill="${svcs.length ? svcColor(s) : "#8a7a66"}" fill-opacity="0.45" stroke="${svcs.length ? svcColor(s) : "#8a7a66"}" stroke-width="0.6" stroke-dasharray="2 2"/>`; }
    }
    const tip = `${fmtBucket(p.t, stepH)}\naus dem Cache (gespart): ${fmtBytes(p.hit)}\naus dem Internet: ${fmtBytes(p.miss)}` +
      parts.filter(([, a, m]) => a + m).map(([s, a, m]) => `\n• ${cacheName(s)}: ${fmtBytes(a + m)}${m ? ` (davon ${fmtBytes(m)} Internet)` : ""}`).join("");
    return `<g><title>${esc(tip)}</title><rect x="${x}" y="0" width="${wd}" height="${h}" fill="transparent"/>${rects}</g>`;
  }).join("");
  const first = points[0], last = points[points.length - 1];
  const legend = svcs.length ? `<div class="row hint" style="gap:12px;flex-wrap:wrap;margin-top:6px">${svcs.map(s => `<span><span class="lgd" style="background:${svcColor(s)}"></span> ${esc(cacheName(s))} ${fmtBytes(order[s])}</span>`).join("")}
      <span><span class="lgd" style="background:transparent;border:1px dashed var(--muted)"></span> blass = aus dem Internet</span></div>` : "";
  return `<svg class="cachechart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${bars}
      <line x1="0" y1="${h - 0.5}" x2="${w}" y2="${h - 0.5}" stroke="var(--line)"/></svg>
    <div class="row hint" style="justify-content:space-between;margin-top:4px"><span>${first ? esc(fmtBucket(first.t, stepH)) : ""}</span>
      <span>max. ${fmtBytes(max)} je ${stepH < 24 ? stepH + " h" : stepH === 24 ? "Tag" : "Woche"}</span><span>${last ? esc(fmtBucket(last.t, stepH)) : ""}</span></div>${legend}`;
}
async function loadCacheHistory(){
  $$("#cacheRangeSeg [data-crange]").forEach(b => b.classList.toggle("active", b.dataset.crange === cacheRange));
  let c;
  try { c = await api(`/api/cache/history?range=${cacheRange}`); } catch (e) { $("#cacheHist").innerHTML = `<div class="hint">${esc(e.message)}</div>`; return; }
  if (view !== "cache") return;
  $("#cacheSub").textContent = c.container ? `${c.container} · ${CACHE_RANGES[c.range]}` + (c.since ? ` · Daten seit ${new Date(c.since * 1000).toLocaleDateString("de-DE")}` : "")
    : (c.error || "kein Lancache gefunden");
  const bf = c.backfill || {};
  const bfHtml = !bf.done && bf.size ? `<div class="panel" style="padding:10px 14px;margin-bottom:14px"><div class="hint" style="margin-bottom:6px">Altes access.log wird einmalig eingelesen … ${Math.floor(bf.pos / bf.size * 100)} % (${fmtBytes(bf.pos)} von ${fmtBytes(bf.size)}, ${(bf.lines || 0).toLocaleString("de-DE")} Downloads)</div>
      <div class="bar"><i style="width:${(bf.pos / bf.size * 100).toFixed(1)}%;background:var(--accent)"></i></div></div>`
    : bf.error ? `<div class="hint" style="margin-bottom:14px">Rückimport: ${esc(bf.error)}</div>` : "";
  const total = c.hit_bytes + c.miss_bytes;
  const dn = c.disk_now, dpct = dn ? Math.round(dn.used / dn.total * 100) : null;
  const diskVals = (c.disk || []).map(d => Math.round(d.used / d.total * 100));
  const cmax = Math.max(1, ...(c.clients || []).map(x => x.bytes));
  const clients = (c.clients || []).map(x => `<tr><td><b>${esc(x.name || "unbekannt")}</b><div class="hint mono">${esc((x.ips || [x.ip]).join(", "))}</div>
      ${(x.games || []).length ? `<div class="hint" style="margin-top:3px">${x.games.map(g => `${esc(g.name)} <span class="mono">${fmtBytes(g.bytes)}</span>`).join(" · ")}</div>` : ""}</td>
    <td style="min-width:120px;width:40%"><div class="cachebar"><i style="width:${(x.bytes / cmax * 100).toFixed(1)}%;background:#4f9dde"></i></div></td>
    <td class="mono">${fmtBytes(x.bytes)}</td></tr>`).join("");
  $("#cacheHist").innerHTML = `${bfHtml}
    <div class="cards">
      <div class="card"><div class="k">Aus dem Internet</div><div class="v">${fmtBytes(c.miss_bytes)}</div><div class="s">${(c.requests || 0).toLocaleString("de-DE")} Anfragen gesamt</div></div>
      <div class="card"><div class="k">Trefferquote</div><div class="v">${c.hit_ratio != null ? c.hit_ratio + " %" : "–"}</div><div class="s">ausgeliefert gesamt ${fmtBytes(total)}</div></div>
      <div class="card"><div class="k">Ø pro Tag</div><div class="v">${fmtBytes(c.per_day)}</div><div class="s">${c.peak.t ? "Spitze " + fmtRate(c.peak.bps) + " (" + new Date(c.peak.t * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}) + ")" : "noch keine Spitze"}</div></div>
      ${storageCard(c.storage, c.disk_now)}
    </div>
    <div class="panel" style="padding:12px 16px;margin-bottom:14px"><h2 style="margin-bottom:8px">Ausgeliefert je ${c.step_h < 24 ? c.step_h + " Stunde(n)" : c.step_h === 24 ? "Tag" : "Woche"}
      <span class="hint">Farbe = Dienst · kräftig = aus dem Cache (gespart), blass = aus dem Internet</span></h2>
      ${total ? cacheChart(c.points, c.step_h) : `<div class="hint">Für diesen Zeitraum liegen noch keine Daten vor.</div>`}</div>
    ${c.points.some(p => p.rx != null) ? `<div class="panel" style="padding:12px 16px;margin-bottom:14px"><h2 style="margin-bottom:8px">Netzwerk des Lancache-Containers
      <span class="hint">${netLegend()} (Download = aus dem Internet, Upload = an Clients; erst ab heute gemessen)</span></h2>
      ${spark2(c.points.map(p => p.rx), c.points.map(p => p.tx), C_DOWN, C_UP, {min: 1e6, h: 120, fmt: AX.bytes, key: "cache-hist"})}
      <div class="row hint" style="justify-content:space-between;margin-top:4px"><span>↓ gesamt ${fmtBytes(c.points.reduce((a, p) => a + (p.rx || 0), 0))}</span><span>↑ gesamt ${fmtBytes(c.points.reduce((a, p) => a + (p.tx || 0), 0))}</span></div></div>` : ""}
    ${c.services.length ? `<div class="panel" style="padding:12px 16px;margin-bottom:14px"><h2 style="margin-bottom:6px">Was wurde gecacht? <span class="hint">(${CACHE_RANGES[c.range]}, nach Dienst)</span></h2>
      <div style="overflow:auto"><table class="cachetable"><thead><tr><th>Dienst</th><th>aus dem Cache</th><th>aus dem Internet</th><th>gesamt</th><th>Trefferquote</th><th></th></tr></thead><tbody>${svcRows(c.services)}</tbody></table></div></div>` : ""}
    ${gamesTable(c.games, CACHE_RANGES[c.range])}
    ${evictHtml(c.model)}
    ${c.depot_backfill && !c.depot_backfill.done && c.depot_backfill.size ? `<div class="hint" style="margin:-8px 0 14px">Spiele aus dem alten Log werden nachgetragen … ${Math.floor(c.depot_backfill.pos / c.depot_backfill.size * 100)} %</div>` : ""}
    ${(c.storage && c.storage.logs && c.storage.logs.length) ? `<div class="panel" style="padding:12px 16px;margin-bottom:14px"><h2 style="margin-bottom:6px">Ordner im Lancache-Container <span class="hint">${c.storage.updated ? "gemessen " + new Date(c.storage.updated * 1000).toLocaleString("de-DE") : ""}</span></h2>
      <table class="cachetable"><tbody>
        <tr><td class="mono">/data/cache</td><td class="mono">${c.storage.measured ? fmtBytes(c.storage.cache_bytes) : "≈ " + fmtBytes(c.storage.estimate)}</td><td class="hint">${c.storage.limit_raw ? "Limit " + esc(c.storage.limit_raw) : ""}</td></tr>
        ${c.storage.logs.map(l => `<tr><td class="mono">/data/logs/${esc(l.name)}</td><td class="mono">${fmtBytes(l.bytes)}</td><td class="hint">${l.name.startsWith("stream") ? "HTTPS-Durchleitung (wird nicht gecacht)" : l.name.startsWith("access") ? "Downloads (Grundlage der Statistik)" : ""}</td></tr>`).join("")}
      </tbody></table></div>` : ""}
    <div class="cgrid">
      ${clients ? `<div class="panel" style="padding:12px 16px"><h2 style="margin-bottom:6px">Top-Clients <span class="hint">(${CACHE_RANGES[c.range]}, Rechnername per DNS/NetBIOS)</span></h2><table class="cachetable"><tbody>${clients}</tbody></table></div>` : ""}

    </div>`;
}
setInterval(() => { if (view === "cache") loadCacheHistory(); }, 30000);
setInterval(() => { if (view === "cache") loadCacheLive(); }, 5000);

/* Live: Durchsatz + letzte Downloads aus dem access.log */
let cacheLiveMetrics = null, cacheLiveAt = 0;
async function loadCacheLive(){
  let c, l;
  try { [c, l] = await Promise.all([api("/api/cache"), api("/api/cache/log?lines=60")]); } catch { return; }
  if (Date.now() - cacheLiveAt > 10000){
    try { cacheLiveMetrics = (await api("/api/metrics?minutes=5"))._cache; cacheLiveAt = Date.now(); } catch {}
  }
  if (view !== "cache") return;
  const rows = (l.log || "").trim().split("\n").reverse().map(line => {
    const m = line.match(/^\[([^\]]*)\] (\S+) .*?\[([^\]]+)\] "(\S+) (\S+)[^"]*" (\d{3}) (\d+) .*"(HIT|MISS|EXPIRED|STALE|UPDATING|REVALIDATED|BYPASS|-)" "([^"]*)"/);
    if (!m) return "";
    const hit = m[8] === "HIT";
    return `<tr><td class="mono hint">${esc(m[3].split(":").slice(1, 4).join(":").split(" ")[0])}</td><td><div class="row" style="gap:6px;flex-wrap:nowrap">${svcIcon(m[1], 13)}${esc(cacheName(m[1]))}</div></td>
      <td>${(l.names || {})[m[2]] ? `<b>${esc(l.names[m[2]])}</b><div class="hint mono" style="font-size:11px">${esc(m[2])}</div>` : `<span class="mono">${esc(m[2])}</span>`}</td><td class="mono">${fmtBytes(+m[7])}</td><td style="color:${hit ? "var(--ok)" : "var(--muted)"}">${hit ? "aus dem Cache" : esc(m[8] === "-" ? "–" : "aus dem Internet")}</td>
      <td class="mono hint" style="max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(m[9] + m[5])}">${esc(m[9])}</td></tr>`;
  }).filter(Boolean).slice(0, 15).join("");
  $("#cacheLive").innerHTML = `<div class="panel" style="padding:12px 16px;margin-bottom:14px">
    <h2 style="margin-bottom:8px">Live <span class="hint">(aktualisiert alle 5 s · Netzwerk des Lancache-Containers)</span>
      <span style="float:right" class="mono"><span style="color:${C_UP}">↑ ${fmtRate((c.net || {}).tx_bps || 0)}</span> an Clients · <span style="color:${C_DOWN}">↓ ${fmtRate((c.net || {}).rx_bps || 0)}</span> aus dem Internet</span></h2>
    ${(() => { const m = cacheLiveMetrics; return m && m.samples ? `<div class="mlab"><span>letzte ${rangeLabel(m.minutes)} · ${netLegend()}</span><b></b></div>${spark2(m.rx, m.tx, C_DOWN, C_UP, {min: 100000, fmt: AX.rate, h: 70, key: "cache-live", dur: 10000})}` : ""; })()}
    ${(c.live_downloads || []).length ? `<h3 class="pdsec">Wird gerade geladen <span class="hint">(letzte 60 s, nach Client und Spiel)</span></h3>
      <div class="livedl">${c.live_downloads.map(d => `<div class="ldrow">
        <span class="ldico">${d.icon ? `<img src="${esc(d.icon)}" alt="" onerror="this.remove()">` : svcIcon(d.service, 16)}</span>
        <span class="ldname"><b title="${esc(d.name || cacheName(d.service))}">${esc(d.name || cacheName(d.service))}</b><span class="hint" title="${esc(d.ip)}">${esc(d.client)}${d.client !== d.ip ? ` <small class="mono">${esc(d.ip)}</small>` : ""}</span></span>
        <span class="mono">${fmtRate(d.bps)}</span>
        <span class="ldhit" title="Anteil aus dem Cache"><i style="width:${d.hit_pct ?? 0}%"></i><em>${d.hit_pct != null ? d.hit_pct + " % Cache" : ""}</em></span></div>`).join("")}</div>` : ""}
    <div class="hint" style="margin:6px 0 8px">Laut Log: ${fmtRate(c.rate_bps || 0)} (davon ${fmtRate(c.hit_rate_bps || 0)} aus dem Cache) – das Log schreibt einen Download erst, wenn er fertig ist.</div>
    ${rows ? `<div style="overflow:auto;max-height:320px"><table class="cachetable"><thead><tr><th>Zeit</th><th>Dienst</th><th>Client</th><th>Größe</th><th></th><th>Server</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="hint">Gerade keine Downloads im access.log.</div>`}</div>`;
}

/* Laufen die Downloads der Spielserver-Container über den Lancache? */
async function loadDnsCheck(){
  const el = $("#cacheDns");
  el.innerHTML = `<div class="hint">Prüfe Spielserver-Container …</div>`;
  let r;
  try { r = await api("/api/cache/dns-check"); } catch (e) { el.innerHTML = `<div class="hint">${esc(e.message)}</div>`; return; }
  const admin = me && me.role === "admin";
  const rows = r.items.map(x => {
    const sid = (servers.find(s => s.container === x.container) || {}).id;
    const st = x.ok === true ? `<span style="color:var(--ok)">✓ über Lancache (${esc(x.resolves)})</span>`
      : x.ok === false || (x.ok === null && !x.note) ? `<span style="color:var(--bad)">✗ ${esc(x.note || "lädt am Cache vorbei")}</span>`
      : `<span class="hint">${esc(x.note || "unbekannt")}</span>`;
    let fix = "";
    if (x.ok === false || (x.ok === null && !x.note)){
      fix = x.managed && admin && sid ? `<button class="small primary" data-dnsfix="${esc(sid)}">Mit Lancache-DNS neu erstellen</button>`
        : x.stack ? `<span class="hint">im Stack „${esc(x.stack)}“ <span class="mono">dns: [${esc((r.dns || ["IP"])[0])}]</span> eintragen</span>` : "";
    }
    return `<tr><td><b>${esc(x.server)}</b><div class="hint mono">${esc(x.container)}</div></td><td>${st}</td>
      <td class="mono hint">${esc((x.dns && x.dns.length ? x.dns : x.nameserver || []).join(", ") || "Standard")}</td><td>${fix}</td></tr>`;
  }).join("");
  el.innerHTML = `<div class="panel" style="padding:12px 16px;margin-top:14px"><h2 style="margin-bottom:6px">Laden die Spielserver über den Cache?
      <span class="hint">Lancache-DNS: ${r.dns ? esc(r.dns.join(", ")) : "nicht gefunden"}</span> <button class="small" id="btnDnsRe" style="float:right">neu prüfen</button></h2>
    <div class="hint" style="margin-bottom:8px">Container fragen sonst den normalen DNS – dann holt SteamCMD Updates direkt aus dem Internet und der Lancache sieht davon nichts. Neue Server bekommen den Lancache-DNS automatisch.</div>
    <div style="overflow:auto"><table class="cachetable"><thead><tr><th>Server</th><th>Status</th><th>DNS</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
  $("#btnDnsRe").onclick = loadDnsCheck;
  $$("[data-dnsfix]").forEach(b => b.onclick = async () => {
    if (!confirm("Container wird kurz gestoppt und mit Lancache-DNS neu erstellt (Daten bleiben erhalten). Fortfahren?")) return;
    b.disabled = true; b.textContent = "wird neu erstellt …";
    try { await api(`/api/servers/${b.dataset.dnsfix}/container/use-lancache`, {method: "POST"}); toast("Container neu erstellt – lädt jetzt über den Lancache"); }
    catch (e) { toast(e.message, true); }
    loadDnsCheck();
  });
}

/* ================= SteamPrefill ================= */
let pfData = null, pfApps = [], pfLoaded = false, pfLastPrompt = null;
const PF_PROMPTS = {user: ["Steam-Anmeldung: Kontoname", "SteamPrefill braucht einmalig ein Steam-Konto (am besten ein eigenes für den Cache).", "text"],
  password: ["Steam-Login: Passwort", "Wird direkt an SteamPrefill im Container weitergegeben und nicht im Tool gespeichert.", "password"],
  code: ["Steam Guard", "Code aus der Steam-App bzw. der E-Mail eingeben.", "text"],
  yesno: ["Rückfrage", "Antwort eingeben (y = ja, n = nein).", "text"]};
let pfCache = {};
function pfCacheBadge(id){
  const c = pfCache[String(id)];
  if (!c) return "";
  if (c.pct == null) return c.stored ? ` <span class="pill" title="Größe noch unbekannt">${fmtBytes(c.stored)} im Cache</span>` : ` <span class="pill" title="Seit dem letzten Zurücksetzen nichts davon geladen">nicht im Cache</span>`;
  if (c.pct >= 85) return ` <span class="pill ok" title="${fmtBytes(c.stored)} von ${fmtBytes(c.size)}">im Cache</span>`;
  return ` <span class="pill ${c.pct > 0 ? "warn" : ""}" title="${fmtBytes(c.stored)} von ${fmtBytes(c.size)}">${c.pct > 0 ? Math.round(c.pct) + " % im Cache" : "nicht im Cache"}</span>`;
}
async function loadPrefill(){
  let d;
  try { d = await api("/api/prefill"); } catch (e) { $("#pfLog").textContent = e.message; return; }
  pfData = d; pfCache = d.cache_status || {};
  const c = d.container, run = c && c.running, s = d.settings;
  if (!pfLoaded){
    pfLoaded = true; pfApps = (s.apps || []).slice();
    $$("[data-pf]").forEach(el => { const v = s.flags[el.dataset.pf]; if (el.type === "checkbox") el.checked = !!v; else el.value = v ?? ""; });
    $("#pfSchedule").value = s.schedule || "";
    loadPfSpeed(s);
    $("#pfServerGames").checked = s.server_games !== false;
    $("#pfSkipCached").checked = s.skip_cached !== false;
    renderPfApps();
  } else if (JSON.stringify(s.apps || []) !== JSON.stringify(pfApps)){ pfApps = (s.apps || []).slice(); renderPfApps(); }
  $("#pfSub").textContent = `Konfiguration: ${d.config_dir}` + (d.dns ? ` · Lancache-DNS ${d.dns.join(", ")}` : " · kein Lancache-DNS gefunden");
  $("#pfCards").innerHTML = `
    <div class="card"><div class="k">Status</div><div class="v" style="color:${d.auto && (d.auto.paused || d.auto.throttled) ? "var(--warn,#e5a50a)" : run ? "var(--ok)" : "inherit"}" title="${esc((d.auto && d.auto.reason) || "")}">${d.auto && d.auto.paused ? "pausiert" : d.auto && d.auto.throttled ? "gedrosselt" : run ? "läuft" : c ? (c.exit === 0 ? "fertig" : "beendet (" + c.exit + ")") : "noch nie gelaufen"}</div><div class="s">${d.auto && d.auto.paused ? esc(d.auto.reason || "") : c && c.finished && !run && !c.finished.startsWith("0001") ? "zuletzt " + new Date(c.finished).toLocaleString("de-DE") : esc(d.job.step || d.job.note || "")}</div></div>
    <div class="card"><div class="k">Steam-Konto</div><div class="v">${d.logged_in ? "angemeldet" : "nicht angemeldet"}</div><div class="s">${d.logged_in ? "Login gespeichert im Config-Ordner" : "beim ersten Lauf wird nach dem Login gefragt"}</div></div>
    <div class="card"><div class="k">Ausgewählte Spiele</div><div class="v">${(s.apps || []).length}</div><div class="s">${[s.flags.recent && "zuletzt gespielt", s.flags.all && "alle", s.flags.top && "Top " + s.flags.top].filter(Boolean).join(" · ") || "nur Auswahl"}</div></div>
    <div class="card"><div class="k">Zeitplan</div><div class="v">${s.schedule ? "täglich " + esc(s.schedule) : "aus"}</div><div class="s">${s.last_run ? "letzter Start " + new Date(s.last_run * 1000).toLocaleString("de-DE") : ""}</div></div>`;
  if (d.job.error) toast(d.job.error, true);
  const pr = d.prompt;
  $("#pfPrompt").classList.toggle("hidden", !run);
  if (run){
    const [t, h, type] = PF_PROMPTS[pr] || ["Eingabe an SteamPrefill", "Falls SteamPrefill unten etwas fragt, hier antworten (Enter = senden).", "text"];
    $("#pfPromptTitle").textContent = t; $("#pfPromptHint").textContent = h; $("#pfInput").type = type;
    if (pfLastPrompt !== pr){ $("#pfInput").value = ""; $("#pfInput").focus(); }
  }
  pfLastPrompt = pr;
  $("#pfState").textContent = run ? "läuft …" + (d.rate != null ? " · " + fmtRate(d.rate) : "") : "";
  const ap = d.apps_progress || [];
  $("#pfAppsProg").innerHTML = ap.length ? `<table class="cachetable"><thead><tr><th>Spiel</th><th style="width:40%">Fortschritt</th><th>Status</th><th></th></tr></thead><tbody>${ap.map(a => `<tr>
      <td><div class="row" style="gap:8px;flex-wrap:nowrap">${appIcon(((s.apps || []).find(x => x.name === a.name) || {}).id, 24)}<b>${esc(a.name)}</b></div></td>
      <td><div class="bar"><i style="width:${Math.min(100, a.pct)}%;background:${d.auto && d.auto.paused && a.state === "läuft" ? "var(--warn,#e5a50a)" : a.state === "Fehler" ? "var(--bad)" : a.state === "läuft" ? "var(--ct)" : "var(--ok)"}"></i></div></td>
      <td class="mono">${a.state === "läuft" ? (d.auto && d.auto.paused && run ? "⏸ " : "") + a.pct.toFixed(0) + " %" : esc(a.state)}</td><td class="hint">${esc(a.info || "")}</td></tr>`).join("")}</tbody></table>`
    : `<div class="hint">Noch kein Lauf in diesem Container.</div>`;
  $("#pfProgWrap").classList.toggle("hidden", !(run && d.progress));
  if (d.progress) $("#pfProg").style.width = Math.min(100, d.progress.pct) + "%";
  const el = $("#pfLog"), atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
  el.textContent = (d.log || "").trim() || "Noch keine Ausgabe – „Jetzt vorladen“ starten.";
  if (atEnd) el.scrollTop = el.scrollHeight;
  $("#pfRun").disabled = !!run; $("#pfStop").disabled = !run;
  const paused = !!(d.auto && d.auto.paused);
  $("#pfPause").disabled = !run;
  $("#pfPause").textContent = paused ? "▶ Fortsetzen" : "⏸ Pausieren";
  $("#pfPause").dataset.on = paused ? "0" : "1";
  const thr = !!(d.auto && d.auto.throttled);
  $("#pfBanner").classList.toggle("hidden", !(run && (paused || thr)));
  if (run && (paused || thr)) $("#pfBanner").innerHTML = `<b>${paused ? "⏸ Prefill pausiert" : `🐢 Prefill gedrosselt auf ${fmtRate(d.auto.rate || 0)}`}</b> – ${esc(d.auto.reason || "")}${d.auto.since ? ` · seit ${new Date(d.auto.since * 1000).toLocaleTimeString("de-DE")}` : ""}${(d.who || []).length ? `<div style="margin-top:4px">Gerade am Laden: ${d.who.map(w => `<b>${esc(w.name || w.ip)}</b> ${fmtRate(w.bps)}`).join(" · ")}</div>` : ""}${d.auto.manual ? "" : `<div class='hint'>${paused ? "Läuft automatisch weiter" : "Wieder volle Geschwindigkeit"}, wenn 30 s lang niemand anderes über den Cache lädt. Der eigene Prefill-Traffic wird dabei herausgerechnet.</div>`}`;
}
function renderPfApps(){
  $("#pfApps").innerHTML = pfApps.length ? pfApps.map((a, i) => `<div class="pfapp"><img src="https://cdn.cloudflare.steamstatic.com/steam/apps/${a.id}/capsule_sm_120.jpg" alt="" referrerpolicy="no-referrer" onerror="this.remove()"><span>${esc(a.name)} <span class="hint mono">${a.id}</span>${a.auto ? ` <span class="pill" title="Von SteamPrefill über die Optionen (zuletzt gespielt, alle …) geladen">über Optionen</span>` : ""}${a.server ? ` <span class="pill" title="Spiel eines eingetragenen Spielservers">Spielserver</span>` : ""}${pfCacheBadge(a.id)}</span><button class="small danger" data-pfdel="${i}">✕</button></div>`).join("")
    : `<div class="hint">Noch keine Spiele ausgewählt.</div>`;
  $$("[data-pfdel]").forEach(b => b.onclick = async () => { pfApps.splice(+b.dataset.pfdel, 1); await savePfApps(); });
}
async function savePfApps(){
  try { const r = await api("/api/prefill/apps", {method: "PUT", body: {apps: pfApps}}); pfApps = r.apps; toast("Spieleliste gespeichert"); }
  catch (e) { toast(e.message, true); }
  renderPfApps();
}
let pfSearchT = null;
$("#pfSearch").addEventListener("input", () => {
  clearTimeout(pfSearchT);
  const q = $("#pfSearch").value.trim();
  if (q.length < 2){ $("#pfResults").innerHTML = ""; return; }
  pfSearchT = setTimeout(async () => {
    let r = [];
    try { r = await api("/api/prefill/search?q=" + encodeURIComponent(q)); } catch (e) { $("#pfResults").innerHTML = `<div class="hint">${esc(e.message)}</div>`; return; }
    $("#pfResults").innerHTML = r.map(a => `<div class="pfapp">${a.img ? `<img src="${esc(a.img)}" alt="" referrerpolicy="no-referrer">` : ""}<span>${esc(a.name)} <span class="hint mono">${a.id}</span></span><button class="small primary" data-pfadd="${a.id}" data-name="${esc(a.name)}">＋</button></div>`).join("") || `<div class="hint">Nichts gefunden.</div>`;
    $$("[data-pfadd]").forEach(b => b.onclick = async () => {
      const id = +b.dataset.pfadd;
      if (!pfApps.some(a => a.id === id)) pfApps.push({id, name: b.dataset.name});
      $("#pfResults").innerHTML = ""; $("#pfSearch").value = "";
      await savePfApps();
    });
  }, 350);
});
// Geschwindigkeit: gemeinsam für alle Prefills
let pfSpeedLoaded = false;
function loadPfSpeed(s){
  if (pfSpeedLoaded && document.activeElement && $("#pfSpeed").contains(document.activeElement)) return;   // nicht beim Tippen überschreiben
  pfSpeedLoaded = true;
  $("#pfYield").checked = s.yield !== false; $("#pfYieldMbs").value = s.yield_mbs ?? 2;
  $("#pfThrottleMbs").value = s.throttle_mbs ?? 5; $("#pfMaxMbs").value = s.max_mbs ?? 0;
}
$("#pfSpeedSave").onclick = async () => {
  try {
    await api("/api/prefill/speed", {method: "PUT", body: {yield: $("#pfYield").checked, yield_mbs: +$("#pfYieldMbs").value || 2,
      throttle_mbs: +$("#pfThrottleMbs").value || 5, max_mbs: Math.max(0, +$("#pfMaxMbs").value || 0)}});
    toast("Geschwindigkeit gespeichert – gilt sofort für alle laufenden Prefills");
  } catch (e) { toast(e.message, true); }
};
$("#pfRun").onclick = async () => {
  await loadTimings(true);
  const d = durText("prefill", "steam", "Letzter Steam-Prefill");
  if (d && !confirm(d + "\nJetzt starten?")) return;
  $("#pfRun").disabled = true;
  try { await api("/api/prefill/run", {body: {mode: "prefill"}}); toast("SteamPrefill gestartet"); } catch (e) { toast(e.message, true); }
  loadPrefill();
};
$("#pfStop").onclick = async () => {
  if (!confirm("Prefill abbrechen? Bereits geladene Daten bleiben im Cache.")) return;
  try { await api("/api/prefill/stop", {method: "POST"}); toast("Prefill abgebrochen"); } catch (e) { toast(e.message, true); } loadPrefill();
};
$("#pfPause").onclick = async () => {
  try { await api("/api/prefill/pause", {body: {on: $("#pfPause").dataset.on === "1"}}); } catch (e) { toast(e.message, true); } loadPrefill();
};
async function pfSend(){
  const v = $("#pfInput").value;
  try { await api("/api/prefill/input", {body: {text: v}}); $("#pfInput").value = ""; } catch (e) { toast(e.message, true); }
  setTimeout(loadPrefill, 800);
}
$("#pfSend").onclick = pfSend;
$("#pfInput").addEventListener("keydown", e => { if (e.key === "Enter") pfSend(); });
$("#pfSaveOpts").onclick = async () => {
  const flags = {};
  $$("[data-pf]").forEach(el => flags[el.dataset.pf] = el.type === "checkbox" ? el.checked : el.type === "number" ? (+el.value || 0) : el.value);
  try { await api("/api/prefill/settings", {method: "PUT", body: {schedule: $("#pfSchedule").value, flags, server_games: $("#pfServerGames").checked, skip_cached: $("#pfSkipCached").checked}}); toast("Gespeichert"); loadPrefill(); }
  catch (e) { toast(e.message, true); }
};
setInterval(() => { if (view === "prefill" && !document.hidden) loadPrefill(); }, 2000);

/* ================= Speicher / iSCSI ================= */
async function loadStorage(fill){
  let d;
  try { d = await api("/api/storage"); } catch (e) { toast(e.message, true); return; }
  const s = d.settings;
  if (fill){
    $("#stoPortal").value = s.portal || ""; $("#stoTarget").value = s.target || ""; $("#stoUser").value = s.chap_user || "";
    $("#stoPw").value = s.chap_pw || ""; $("#stoMnt").value = s.mountpoint || ""; $("#stoFs").value = s.fs || "ext4";
    $("#stoLabel").value = s.label || ""; $("#stoPurpose").value = s.purpose || "lancache"; $("#stoOld").value = s.old_path || "";
    $("#stoFormat").checked = !!s.format;
  }
  const m = d.mount || {}, dk = d.disk;
  $("#stoCards").innerHTML = `
    <div class="card"><div class="k">${esc(s.mountpoint)}</div><div class="v" style="color:${m.mounted ? "var(--ok)" : "inherit"}">${m.mounted ? "eingehängt" : m.mounted === false ? "nicht eingehängt" : "unbekannt"}</div>
      <div class="s">${m.mounted ? esc(m.device + " · " + m.fstype) : esc(m.error || "Skript noch nicht ausgeführt")}</div></div>
    <div class="card"><div class="k">Zugriffszeit (Platte)</div><div class="v">${dk && dk.await_ms != null ? dk.await_ms + " ms" : "–"}</div><div class="s">${dk ? "Auslastung " + dk.util + " %" : "nach dem Einbinden sichtbar"}</div></div>
    <div class="card"><div class="k">Ziel</div><div class="v" style="font-size:14px;white-space:normal">${esc(s.target || "wird gesucht")}</div><div class="s">${esc(s.portal || "Portal fehlt")}</div></div>`;
  $("#stoMounts").innerHTML = (d.mounts || []).length ? `<table class="cachetable"><thead><tr><th>Pfad</th><th>Gerät</th><th>Typ</th><th></th></tr></thead><tbody>${d.mounts.map(x => `<tr><td class="mono">${esc(x.path)}</td><td class="mono">${esc(x.device)}</td><td class="mono">${esc(x.fstype)}</td><td class="hint">${x.network ? "Netzwerkfreigabe (NFS/SMB)" : x.device.startsWith("/dev/") ? "Blockgerät (lokal oder iSCSI)" : ""}</td></tr>`).join("")}</tbody></table>` : `<div class="hint">Keine Daten (Host-/proc im Stack eingebunden?).</div>`;
  $("#stoScript").textContent = d.script;
}
$("#stoSave").onclick = async () => {
  const body = {portal: $("#stoPortal").value.trim(), target: $("#stoTarget").value.trim(), chap_user: $("#stoUser").value.trim(),
    chap_pw: $("#stoPw").value, mountpoint: $("#stoMnt").value.trim(), fs: $("#stoFs").value, label: $("#stoLabel").value.trim(),
    purpose: $("#stoPurpose").value, old_path: $("#stoOld").value.trim(), format: $("#stoFormat").checked};
  try { await api("/api/storage", {method: "PUT", body}); toast("Gespeichert – Skript aktualisiert"); loadStorage(true); } catch (e) { toast(e.message, true); }
};
$("#stoCopy").onclick = () => copyQuiet($("#stoScript").textContent, "Skript kopiert");
setInterval(() => { if (view === "storage" && !document.hidden) loadStorage(false); }, 5000);

/* Container: Steam-Reparatur + Startparameter (SteamCMD-Images) */
let ctEnvFor = null;
async function loadCtEnv(){
  if (!current || !current.container || ctEnvFor === current.id) return;
  ctEnvFor = current.id;
  $("#btnSteamFix").classList.add("hidden"); $("#ctParamsRow").classList.add("hidden");
  $("#btnGsltAssign").classList.toggle("hidden", !(GAMES[gameOf(current)] || {}).gslt);
  ["#btnTvOn","#btnTvOff"].forEach(b => $(b).classList.toggle("hidden", gameOf(current) !== "cs2"));
  $("#btnPorts").classList.toggle("hidden", !["cs2", "wreckfest"].includes(gameOf(current)));
  if (permOf(current) < 3) return;
  try {
    const r = await api(`/api/servers/${current.id}/container/env`);
    const steam = "GAME_ID" in r.env;
    $("#btnSteamFix").classList.toggle("hidden", !steam);
    $("#ctParamsRow").classList.toggle("hidden", !("GAME_PARAMS" in r.env) || !r.managed);
    $("#ctParams").value = r.env.GAME_PARAMS || "";
  } catch {}
}
$("#btnSteamFix").onclick = async () => {
  if (!confirm("Server wird gestoppt, SteamCMD lädt das Spiel einmal als Windows und dann als Linux (kann dauern). Fortfahren?")) return;
  const b = $("#btnSteamFix"); b.disabled = true; b.textContent = "läuft … (Seite offen lassen)";
  try { const r = await api(`/api/servers/${current.id}/container/steamfix`, {method: "POST"}); toast(r.ok ? "Fertig – Server startet" : "SteamCMD meldet Fehler, siehe Log", !r.ok); logConsole("steamfix", r.output || ""); }
  catch (e) { toast(e.message, true); }
  b.disabled = false; b.textContent = "Steam-Installation reparieren";
};
$("#btnCtParams").onclick = async () => {
  if (!confirm("Container mit neuen Startparametern neu erstellen?")) return;
  try { await api(`/api/servers/${current.id}/container/env`, {body: {env: {GAME_PARAMS: $("#ctParams").value.trim()}}}); toast("Übernommen – Server startet neu"); }
  catch (e) { toast(e.message, true); }
};
setInterval(() => { if (view === "server" && current && tab === "container") loadCtEnv(); else if (!current || ctEnvFor !== (current && current.id)) ctEnvFor = null; }, 1500);

/* ================= Konfiguration (Umgebung, Dateien, Satisfactory-API) ================= */
let cfgFiles = [], cfgCur = null;
function cfgInput(f, v, attr){
  const [key, label, type, opts] = f;
  const lock = cfgLocked[key] ? ` disabled title="Wird beim Start durch die Umgebungsvariable ${esc(cfgLocked[key])} gesetzt – oben bei Server-Einstellungen bzw. im Stack ändern"` : "";
  if (type === "bool") return `<div class="chk"><input type="checkbox" ${attr}="${esc(key)}" ${v === true || String(v).toLowerCase() === "true" || v === "1" || v === 1 ? "checked" : ""}${lock}><span>${esc(label)}${cfgLocked[key] ? " 🔒" : ""}</span></div>`;
  if (type === "select") return `<div><label>${esc(label)}${cfgLocked[key] ? " 🔒" : ""}</label><select ${attr}="${esc(key)}"${lock}>${opts.map(o => `<option ${String(v) === o ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></div>`;
  return `<div><label>${esc(label)}${cfgLocked[key] ? " 🔒" : ""}</label><input ${attr}="${esc(key)}" value="${esc(v ?? "")}" ${type === "number" ? 'inputmode="decimal"' : ""} spellcheck="false"${lock}></div>`;
}
let cfgLocked = {};
const readInputs = attr => { const o = {}; $$(`[${attr}]`).forEach(el => { if (!el.disabled) o[el.getAttribute(attr)] = el.type === "checkbox" ? el.checked : el.value; }); return o; };
async function loadConfigTab(){
  if (!current) return;
  const sid = current.id, g = gameOf(current);
  // Satisfactory-API
  $("#cfgSf").classList.toggle("hidden", g !== "satisfactory");
  if (g === "satisfactory"){
    try {
      const r = await api(`/api/servers/${sid}/satisfactory/options`);
      $("#cfgSfFields").innerHTML = cfgInput(["_name", "Servername", "text"], r.name, "data-sf") + cfgInput(["_pw", "Spieler-Passwort (leer lassen = unverändert)", "text"], "", "data-sf")
        + r.fields.map(f => cfgInput([f.key, f.label, f.type], f.value, "data-sf")).join("");
    } catch (e) { $("#cfgSfFields").innerHTML = `<div class="hint">${esc(e.message)}</div>`; }
  }
  // Umgebungsvariablen
  try {
    const r = await api(`/api/servers/${sid}/container/env`);
    const fields = r.fields.filter(f => f.present || r.managed);
    $("#cfgEnv").classList.toggle("hidden", !fields.length);
    $("#cfgEnvHint").textContent = r.managed ? "Container wird beim Übernehmen mit denselben Daten neu erstellt" : "nur lesbar – Container gehört zu einem Portainer-Stack, dort ändern";
    $("#cfgEnvFields").innerHTML = fields.map(f => cfgInput([f.key, f.label, "text"], f.value, "data-env")).join("");
    $$("[data-env]").forEach(el => el.disabled = !r.managed);
    $("#btnEnvSave").classList.toggle("hidden", !r.managed);
  } catch { $("#cfgEnv").classList.add("hidden"); }
  // Dateien
  try {
    const r = await api(`/api/servers/${sid}/config`);
    cfgFiles = r.files;
    $("#cfgFilesPanel").classList.toggle("hidden", !cfgFiles.length);
    $("#cfgFile").innerHTML = cfgFiles.map((f, i) => `<option value="${i}">${esc(f.label)}${f.form ? " – Formular" : ""}</option>`).join("");
    if (cfgFiles.length) await loadCfgFile();
  } catch (e) { $("#cfgHint").textContent = e.message; }
}
async function loadCfgFile(){
  const f = cfgFiles[+$("#cfgFile").value || 0]; if (!f) return;
  $("#cfgHint").textContent = "wird gelesen …"; $("#cfgForm").innerHTML = "";
  try {
    const r = await api(`/api/servers/${current.id}/config/file?path=${encodeURIComponent(f.path)}`);
    cfgCur = {f, r}; cfgLocked = r.locked || {};
    $("#cfgText").value = r.content || "";
    $("#cfgHint").innerHTML = r.exists ? `<span class="mono">${esc(f.path)}</span> · Vor jedem Speichern wird eine Sicherung <span class="mono">.bak</span> angelegt.` : `Datei gibt es noch nicht (<span class="mono">${esc(f.path)}</span>) – entsteht meist beim ersten Start. Du kannst sie hier anlegen.`;
    $("#cfgRaw").open = !f.form;
    if (f.form && r.exists){
      $("#cfgForm").innerHTML = `<div class="cfggrid">${f.fields.map(x => cfgInput(x, r.values[x[0]], "data-cf2")).join("")}</div>
        <div class="row" style="margin-top:10px"><button id="btnCfgForm">Speichern</button><button class="primary" id="btnCfgFormRestart">Speichern &amp; Server neu starten</button></div>`;
      $("#btnCfgForm").onclick = () => saveCfgForm(false);
      $("#btnCfgFormRestart").onclick = () => saveCfgForm(true);
    }
  } catch (e) { $("#cfgHint").textContent = e.message; }
}
async function saveCfgForm(restart){
  try { await api(`/api/servers/${current.id}/config/file`, {method: "PUT", body: {path: cfgCur.f.path, values: readInputs("data-cf2"), restart}}); toast(restart ? "Gespeichert – Server startet neu" : "Gespeichert (wirkt nach Neustart)"); loadCfgFile(); }
  catch (e) { toast(e.message, true); }
}
async function saveCfgRaw(restart){
  try { await api(`/api/servers/${current.id}/config/file`, {method: "PUT", body: {path: cfgCur.f.path, content: $("#cfgText").value, restart}}); toast(restart ? "Gespeichert – Server startet neu" : "Gespeichert"); loadCfgFile(); }
  catch (e) { toast(e.message, true); }
}
$("#cfgFile").onchange = loadCfgFile;
$("#btnCfgReload").onclick = loadCfgFile;
$("#btnCfgSaveRaw").onclick = () => saveCfgRaw(false);
$("#btnCfgSaveRawRestart").onclick = () => saveCfgRaw(true);
$("#btnEnvSave").onclick = async () => {
  if (!confirm("Container mit den neuen Einstellungen neu erstellen? (Daten bleiben erhalten)")) return;
  try { const r = await api(`/api/servers/${current.id}/container/env`, {body: {env: readInputs("data-env")}}); toast(r.changed ? "Übernommen – Server startet neu" : "Keine Änderung"); }
  catch (e) { toast(e.message, true); }
};
$("#btnSfSave").onclick = async () => {
  const v = readInputs("data-sf"), options = {};
  Object.entries(v).forEach(([k, x]) => { if (!k.startsWith("_")) options[k] = typeof x === "boolean" ? (x ? "True" : "False") : x; });
  try { await api(`/api/servers/${current.id}/satisfactory/options`, {method: "PUT", body: {options, server_name: v._name || null, client_password: v._pw ? v._pw : null}}); toast("Übernommen"); loadConfigTab(); }
  catch (e) { toast(e.message, true); }
};

/* ================= Dateien & Spielstände ================= */
let fbPath = null, fbRoots = [];
const fmtTime = t => t ? new Date(t * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit"}) : "";
const dlUrl = p => `/api/servers/${current.id}/files/download?path=${encodeURIComponent(p)}`;
async function fbOpen(path){
  if (!current) return;
  let r;
  try { r = await api(`/api/servers/${current.id}/files` + (path ? `?path=${encodeURIComponent(path)}` : "")); }
  catch (e) { $("#fbList").innerHTML = `<div class="hint">${esc(e.message)}</div>`; return; }
  fbPath = r.path; fbRoots = r.roots;
  $("#fbRoot").innerHTML = r.roots.map(x => `<option ${r.path.startsWith(x) ? "selected" : ""}>${esc(x)}</option>`).join("");
  const root = r.roots.find(x => r.path === x || r.path.startsWith(x.replace(/\/$/, "") + "/")) || "/";
  const rel = r.path.slice(root.length).split("/").filter(Boolean);
  let acc = root;
  $("#fbCrumb").innerHTML = `<a href="#" data-fbgo="${esc(root)}">${esc(root)}</a>` + rel.map(seg => { acc = acc.replace(/\/$/, "") + "/" + seg; return ` / <a href="#" data-fbgo="${esc(acc)}">${esc(seg)}</a>`; }).join("");
  const up = r.path !== root ? `<div class="fbrow"><span>↰</span><span class="n" data-fbgo="${esc(r.path.replace(/\/[^/]*$/, "") || "/")}">..</span><span></span><span></span><span></span></div>` : "";
  $("#fbList").innerHTML = up + (r.items.length ? r.items.map(it => {
    const p = r.path.replace(/\/$/, "") + "/" + it.name;
    return `<div class="fbrow"><span>${it.dir ? "📁" : it.text ? "📄" : "▫"}</span>
      <span class="n" ${it.dir ? `data-fbgo="${esc(p)}"` : it.text ? `data-fbedit="${esc(p)}"` : ""} title="${esc(it.name)}">${esc(it.name)}</span>
      <span class="hint mono">${it.dir ? "" : fmtBytes(it.size)}</span><span class="hint">${fmtTime(it.mtime)}</span>
      <span class="acts">${it.text ? `<button class="small" data-fbedit="${esc(p)}">Bearbeiten</button>` : ""}<a class="small btn-link" href="${dlUrl(p)}" title="${it.dir ? "Ordner als .tar.gz" : "Herunterladen"}">⇩</a><button class="small danger" data-fbdel="${esc(p)}">✕</button></span></div>`;
  }).join("") : `<div class="hint" style="padding:8px">Ordner ist leer.</div>`);
  $$("[data-fbgo]").forEach(el => el.onclick = e => { e.preventDefault(); fbOpen(el.dataset.fbgo); });
  $$("[data-fbedit]").forEach(el => el.onclick = () => fbEdit(el.dataset.fbedit));
  $$("[data-fbdel]").forEach(el => el.onclick = async () => {
    if (!confirm(`„${el.dataset.fbdel}“ endgültig löschen?`)) return;
    try { await api(`/api/servers/${current.id}/files?path=${encodeURIComponent(el.dataset.fbdel)}`, {method: "DELETE"}); toast("Gelöscht"); fbOpen(fbPath); } catch (e) { toast(e.message, true); }
  });
}
async function fbEdit(p){
  try {
    const r = await api(`/api/servers/${current.id}/files/text?path=${encodeURIComponent(p)}`);
    $("#fbEdit").classList.remove("hidden"); $("#fbEditPath").textContent = r.path; $("#fbText").value = r.content;
    $("#fbEdit").scrollIntoView({behavior: "smooth", block: "nearest"});
  } catch (e) { toast(e.message, true); }
}
$("#fbEditClose").onclick = () => $("#fbEdit").classList.add("hidden");
$("#fbEditSave").onclick = async () => {
  try { await api(`/api/servers/${current.id}/files/text`, {method: "PUT", body: {path: $("#fbEditPath").textContent, content: $("#fbText").value}}); toast("Gespeichert"); fbOpen(fbPath); }
  catch (e) { toast(e.message, true); }
};
$("#fbRoot").onchange = () => fbOpen($("#fbRoot").value);
$("#fbRefresh").onclick = () => fbOpen(fbPath);
$("#fbUpload").onchange = async () => {
  const files = [...$("#fbUpload").files];
  for (const f of files){
    try {
      const res = await fetch(`/api/servers/${current.id}/files/upload?dir=${encodeURIComponent(fbPath)}&name=${encodeURIComponent(f.name)}`, {method: "POST", body: f, credentials: "same-origin"});
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      toast(`Hochgeladen: ${f.name}`);
    } catch (e) { toast(`${f.name}: ${e.message}`, true); }
  }
  $("#fbUpload").value = ""; fbOpen(fbPath);
};
async function loadSaves(){
  if (!current) return;
  let r;
  try { r = await api(`/api/servers/${current.id}/saves`); } catch (e) { $("#svSavesList").innerHTML = `<div class="hint">${esc(e.message)}</div>`; return; }
  $("#svSaveRow").classList.toggle("hidden", !r.can_save);
  $("#svSavesHint").textContent = r.error ? r.error : r.files.length || r.sessions ? "" : "keine bekannten Spielstand-Ordner – im Datei-Browser unten suchen";
  let h = "";
  if (r.sessions && r.sessions.length){
    h += r.sessions.map(se => `<div style="margin-bottom:8px"><b>Sitzung ${esc(se.name)}</b>${se.saves.slice(0, 8).map(v => `<div class="fbrow"><span>💾</span><span class="n">${esc(v.name)}</span><span class="hint">${v.playtime ? Math.round(v.playtime / 3600) + " h gespielt" : ""}</span><span class="hint">${esc((v.time || "").replace("T", " ").slice(0, 16))}</span>
      <span class="acts"><button class="small primary" data-load="${esc(v.name)}">Laden</button></span></div>`).join("")}</div>`).join("");
  }
  if (r.files.length){
    h += r.files.slice(0, 40).map(f => `<div class="fbrow"><span>${f.dir ? "🌍" : "💾"}</span><span class="n" title="${esc(f.path)}">${esc(f.name)} <span class="hint mono">${esc(f.dirpath)}</span></span>
      <span class="hint mono">${f.dir ? "" : fmtBytes(f.size)}</span><span class="hint">${fmtTime(f.mtime)}</span>
      <span class="acts">${r.can_load && r.game === "factorio" && f.name.endsWith(".zip") ? `<button class="small primary" data-load="${esc(f.path)}">Laden</button>` : ""}<a class="small btn-link" href="${dlUrl(f.path)}" title="Sichern/Herunterladen">⇩ Sichern</a></span></div>`).join("");
  }
  $("#svSavesList").innerHTML = h || "";
  $$("[data-load]").forEach(b => b.onclick = async () => {
    if (!confirm(`Spielstand „${b.dataset.load}“ laden? Ungespeicherter Fortschritt geht verloren.`)) return;
    try { const x = await api(`/api/servers/${current.id}/saves/load`, {body: {name: b.dataset.load}}); toast(x.output || "Wird geladen"); } catch (e) { toast(e.message, true); }
  });
}
$("#btnSaveNow").onclick = async () => {
  try { const r = await api(`/api/servers/${current.id}/saves/now`, {body: {name: $("#svSaveName").value.trim()}}); toast(r.output || "Gespeichert"); $("#svSaveName").value = ""; setTimeout(loadSaves, 1500); }
  catch (e) { toast(e.message, true); }
};

/* Belegung eigene Platte + /mnt-Mounts in der Seitenleiste */
async function refreshDisks(){
  let r;
  try { r = await api("/api/disks"); } catch { return; }
  $("#hlDisks").innerHTML = (r.items || []).map(d => {
    const pct = d.size ? Math.round(d.used / d.size * 100) : 0;
    const name = d.mount === "/" ? "System" : d.mount.replace(/^\/mnt\//, "");
    return `<div class="hl-row" title="${esc(d.mount)} (${esc(d.device)}): ${fmtBytes(d.used)} von ${fmtBytes(d.size)} belegt, ${fmtBytes(d.avail)} frei"><span>${d.network ? "🗄" : "💽"} ${esc(name)}</span><div class="bar"><i class="${lvl(pct)}" style="width:${pct}%"></i></div><b>${pct} %</b></div>`;
  }).join("");
}


$("#btnCacheReset").onclick = async () => {
  if (!confirm("Gesamten Lancache-Verlauf, Trefferquote und „Welche Spiele wurden geladen“ zurücksetzen?\nDer Cache selbst bleibt unverändert.")) return;
  try { await api("/api/cache/reset", {method: "POST"}); toast("Statistik zurückgesetzt"); if (typeof loadCacheHistory === "function") loadCacheHistory(); refreshCache(); }
  catch (e){ toast(e.message, true); }
};

/* ================= Steam-Tokens (GSLT) ================= */
async function loadGslt(){
  let r; try { r = await api("/api/gslt"); } catch (e) { $("#gsltRows").innerHTML = `<tr><td colspan="6" class="hint">${esc(e.message)}</td></tr>`; return; }
  $("#gsltKey").placeholder = r.has_key ? "•••• gespeichert (neu eintragen zum Ändern)" : "leer lassen = Tokens nur von Hand";
  $("#btnGsltSync").disabled = !r.has_key;
  const gsel = $("#gsltGame"), cur = gsel.value;
  gsel.innerHTML = Object.entries(r.games || {cs2: "Counter-Strike 2", tf2: "Team Fortress 2"}).map(([k, l]) => `<option value="${k}" ${k === cur ? "selected" : ""}>${esc(l)}</option>`).join("");
  const free = r.tokens.filter(t => !t.used_by && !t.assigned && !t.expired && !t.deleted).length;
  $("#gsltRows").innerHTML = r.tokens.length ? r.tokens.map(t => `<tr>
    <td>${esc(t.app)}</td><td>${esc(t.memo || "")}</td><td class="mono">${esc(t.token_short)}</td>
    <td>${t.used_by ? esc(t.used_by) : t.assigned ? `<span class="hint">reserviert: ${esc(t.assigned)}</span>` : `<span class="pill ok">frei</span>`}</td>
    <td>${t.deleted ? '<span class="pill">gelöscht</span>' : t.expired ? '<span class="pill warn">abgelaufen</span>' : '<span class="pill ok">gültig</span>'}</td>
    <td style="white-space:nowrap">${t.expired && t.steamid && r.has_key ? `<button class="small" data-grenew="${esc(t.steamid)}">Erneuern</button>` : ""}<button class="small danger" data-gdel="${esc(t.id)}">✕</button></td></tr>`).join("")
    : `<tr><td colspan="6" class="hint">Noch keine Tokens gespeichert.</td></tr>`;
  $("#gsltHint").textContent = `${free} frei` + (r.unknown_in_use.length ? ` · nicht in der Liste, aber in Benutzung: ${r.unknown_in_use.join(", ")} – „Von Servern übernehmen“ klicken` : "")
    + (r.has_key ? " · Fehlt beim Anlegen ein freier Token, erstellt das Tool automatisch einen neuen." : "");
  $$("[data-grenew]").forEach(b => b.onclick = async () => { try { await api(`/api/gslt/renew/${b.dataset.grenew}`, {method: "POST"}); toast("Token erneuert"); loadGslt(); } catch (e){ toast(e.message, true); } });
  $$("[data-gdel]").forEach(b => b.onclick = async () => { if (!confirm("Token aus der Liste entfernen? (bei Steam bleibt er bestehen)")) return; try { await api(`/api/gslt/${encodeURIComponent(b.dataset.gdel)}`, {method: "DELETE"}); loadGslt(); } catch (e){ toast(e.message, true); } });
}
$("#btnGsltKey").onclick = async () => { try { const r = await api("/api/gslt/key", {method: "PUT", body: {key: $("#gsltKey").value.trim()}}); $("#gsltKey").value = ""; toast(r.synced != null ? `Gespeichert – ${r.synced} Tokens von Steam geholt` : "Gespeichert"); loadGslt(); } catch (e){ toast(e.message, true); } };
$("#btnGsltSync").onclick = async () => { try { const r = await api("/api/gslt/sync", {method: "POST"}); toast(`${r.synced} Tokens von Steam geholt`); loadGslt(); } catch (e){ toast(e.message, true); } };
$("#btnGsltImport").onclick = async () => { try { const r = await api("/api/gslt/import", {method: "POST"}); toast(`${r.imported} Tokens übernommen`); loadGslt(); } catch (e){ toast(e.message, true); } };
$("#btnGsltAdd").onclick = async () => {
  try { await api("/api/gslt/create", {body: {game: $("#gsltGame").value, memo: $("#gsltMemo").value.trim(), token: $("#gsltToken").value.trim()}}); $("#gsltToken").value = ""; $("#gsltMemo").value = ""; toast("Token hinzugefügt"); loadGslt(); }
  catch (e){ toast(e.message, true); }
};

async function setTv(on){
  if (!confirm(on ? "CSTV einschalten (ohne Verzögerung)? Vom Tool angelegte Container werden dafür neu erstellt." : "CSTV ausschalten?")) return;
  try { const r = await api(`/api/servers/${current.id}/cstv`, {method: "POST", body: {on, delay: 0}}); toast(r.how); }
  catch (e){ toast(e.message, true); }
}
$("#btnPorts").onclick = async () => {
  const wf = gameOf(current) === "wreckfest";
  const ask = wf ? "Spielport, Steam-Port, Query-Port (Original: 33540, 27015, 27016)" : "Spielport, CSTV-Port (Schema: CS #n = 2703n, 2702n)";
  const def = wf ? `${current.game_port || 33540}, 27015, 27016` : `${current.port}, `;
  const v = prompt(ask, def); if (!v) return;
  const n = v.split(/[ ,;]+/).map(x => parseInt(x, 10)).filter(x => x > 0);
  const body = wf ? {port: n[0], steam_port: n[1], query_port: n[2]} : {port: n[0], tv_port: n[1]};
  if (!confirm(`Ports setzen: ${n.join(", ")}? Der Container wird neu erstellt. Portweiterleitungen am Router ggf. anpassen.`)) return;
  try { const r = await api(`/api/servers/${current.id}/ports`, {body}); toast("Ports geändert: " + Object.entries(r).filter(([k]) => k !== "ok").map(([k, x]) => `${k} ${x}`).join(", ")); await loadServers(); }
  catch (e){ toast(e.message, true); }
};
$("#btnImgUpdate").onclick = async () => {
  await loadTimings(true);
  const d = durText("image_update", gameOf(current), "Letztes Update");
  if (!confirm("Neueste Version (Image) holen und Server damit neu starten? Spieldaten und Einstellungen bleiben." + (d ? "\n" + d : ""))) return;
  toast("Lade neuestes Image …");
  try { const r = await api(`/api/servers/${current.id}/image-update`, {method: "POST"}); toast(r.result); }
  catch (e){ toast(e.message, true); }
};
$("#btnTvOn").onclick = () => setTv(true);
$("#btnTvOff").onclick = () => setTv(false);

$("#btnGsltAssign").onclick = async () => {
  if (!confirm("Freien Steam-Token einsetzen (oder bei Steam neu erstellen)? Der Container wird dafür neu erstellt.")) return;
  try { const r = await api(`/api/servers/${current.id}/gslt`, {method: "POST"}); toast(`Token${r.memo ? " „" + r.memo + "“" : ""} eingesetzt – Server startet neu`); }
  catch (e){ toast(e.message, true); }
};

/* ================= Ordner im Spieleverzeichnis ================= */
let fld = null, fldTimer = null;
async function loadFolders(refresh){
  clearTimeout(fldTimer);
  try { fld = await api("/api/storage/folders" + (refresh ? "?refresh=1" : "")); } catch (e){ $("#fldRows").innerHTML = `<div class="hint">${esc(e.message)}</div>`; return; }
  renderFolders();
  if ((fld.busy || fld.items.some(f => f.deleting)) && view === "storage") fldTimer = setTimeout(loadFolders, 5000);
}
function renderFolders(){
  if (!fld) return;
  const q = ($("#fldFilter").value || "").trim().toLowerCase();
  $("#fldSub").textContent = `${fld.base || ""}${fld.busy ? " · liest ein (du, niedrige Priorität) …" : fld.updated ? " · Stand " + new Date(fld.updated * 1000).toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"}) : ""}${fld.error ? " · " + fld.error : ""}`;
  const items = fld.items.filter(f => !q || f.rel.toLowerCase().includes(q));
  const max = Math.max(1, ...items.map(f => f.bytes || 0));
  $("#fldRows").innerHTML = items.length ? items.map(f => `<div class="fldrow${f.depth > 1 ? " sub" : ""}">
      <span class="mono" title="${esc(f.path)}">${esc(f.rel)}</span>
      <div class="bar"><i style="width:${f.bytes ? Math.max(1, f.bytes / max * 100) : 0}%"></i></div>
      <b>${f.bytes != null ? fmtBytes(f.bytes) : "–"}</b>
      ${f.used_by.length ? `<span class="pill ok" title="${esc(f.used_by.join(", "))}">genutzt: ${esc(f.used_by.slice(0, 2).join(", "))}${f.used_by.length > 2 ? " …" : ""}</span>`
        : f.deleting ? `<span class="pill warn">wird gelöscht …</span>` : `<span class="pill warn">frei</span><button class="small danger" data-flddel="${esc(f.path)}">Löschen</button>`}
    </div>`).join("") : `<div class="hint">${fld.busy ? "wird eingelesen …" : "keine Ordner" + (q ? " passend zu „" + esc(q) + "“" : "")}</div>`;
  $$("[data-flddel]").forEach(b => b.onclick = async () => {
    const f = fld.items.find(x => x.path === b.dataset.flddel);
    if (!confirm(`Ordner ${f.path} (${f.bytes != null ? fmtBytes(f.bytes) : "Größe unbekannt"}) mit ALLEN Dateien endgültig löschen?\nDas lässt sich nicht rückgängig machen.`)) return;
    try { await api("/api/storage/folders/delete", {body: {path: f.path}}); toast("Löschen läuft im Hintergrund"); loadFolders(); }
    catch (e){ toast(e.message, true); }
  });
}
$("#btnFldRefresh").onclick = () => loadFolders(true);
$("#fldFilter").addEventListener("input", renderFolders);

/* ================= Spiel-Übersicht: alle Server eines Spiels, Sammelaktionen ================= */
function renderGameView(){
  if (view !== "game" || !gvGame) return;
  const g = GAMES[gvGame] || {label: gvGame}, list = servers.filter(s => gameOf(s) === gvGame);
  gvSel = new Set([...gvSel].filter(id => list.some(s => s.id === id)));
  $("#gvTitle").innerHTML = `${gameTile(gvGame, 22)} ${esc(g.label)}`;
  const on = list.filter(s => stateOf(s.id).online).length;
  $("#gvSub").textContent = `${list.length} Server · ${on} online · ${list.reduce((a, s) => a + (stateOf(s.id).online ? (stateOf(s.id).humans || 0) : 0), 0)} Spieler`;
  $("#gvRows").innerHTML = list.map(s => {
    const o = stateOf(s.id), c = o.load && !o.load.error ? o.load.state : null;
    const lim = o.visible_players > 0 ? o.visible_players : o.max_players;
    return `<tr data-gvid="${esc(s.id)}"><td><input type="checkbox" data-gvc="${esc(s.id)}" ${gvSel.has(s.id) ? "checked" : ""} style="width:auto"></td>
      <td>${led(o)}</td><td><a href="#" data-gvopen="${esc(s.id)}"><b>${esc(s.name)}</b></a></td>
      <td class="mono">${esc(s.host)}:${esc(s.port)}</td><td>${esc(o.online ? (gvGame === "wreckfest" ? (o.track_name || o.map || "") : (o.map_title || o.map || "")) : "")}</td>
      <td>${o.online ? `${o.humans ?? 0}${lim ? "/" + lim : ""}${o.bots ? ` <span class="hint">+${o.bots} Bots</span>` : ""}` : "–"}</td>
      <td>${s.container ? `<span class="hint">${esc(CSTATE[c] || c || "?")}</span>` : `<span class="hint">kein Container</span>`}</td>
      <td>${o.online ? reachPill(o.reach) : ""}</td></tr>`;
  }).join("") || `<tr><td colspan="8" class="hint">Keine Server</td></tr>`;
  $("#gvAll").checked = list.length > 0 && gvSel.size === list.length;
  $("#gvSel").textContent = `${gvSel.size} ausgewählt`;
  $$("[data-gvc]").forEach(cb => cb.onchange = () => { cb.checked ? gvSel.add(cb.dataset.gvc) : gvSel.delete(cb.dataset.gvc); renderGameView(); });
  $$("[data-gvopen]").forEach(a => a.onclick = e => { e.preventDefault(); selectServer(servers.find(s => s.id === a.dataset.gvopen)); });
}
$("#gvAll").onchange = () => { const list = servers.filter(s => gameOf(s) === gvGame); gvSel = $("#gvAll").checked ? new Set(list.map(s => s.id)) : new Set(); renderGameView(); };
const GV_LABEL = {start: "starten", stop: "stoppen", restart: "neu starten", pause: "pausieren", unpause: "fortfahren lassen", delete: "löschen"};
$$("[data-gva]").forEach(b => b.onclick = async () => {
  const act = b.dataset.gva, sel = servers.filter(s => gvSel.has(s.id));
  if (!sel.length) return toast("Erst Server auswählen", true);
  let delData = false;
  if (act === "delete"){
    if (!confirm(`${sel.length} Server löschen?\n${sel.map(s => "• " + s.name).join("\n")}\n\nContainer und alle Spieldaten werden entfernt.`)) return;
    delData = true;
    if (delData && prompt(`Zur Bestätigung LÖSCHEN eintippen – ${sel.length} Server samt Daten werden endgültig gelöscht`) !== "LÖSCHEN") return toast("Abgebrochen");
  } else if (!confirm(`${sel.length} Server ${GV_LABEL[act]}?\n${sel.map(s => "• " + s.name).join("\n")}`)) return;
  const log = [];
  $("#gvLog").textContent = "läuft …";
  await Promise.all(sel.map(async s => {
    try {
      if (act === "delete") await api(`/api/servers/${s.id}/delete`, {body: {remove_container: !!s.container, delete_data: delData && !!s.container, confirm: s.name}});
      else if (!s.container) throw new Error("kein Container");
      else await api(`/api/servers/${s.id}/container/${act}`, {method: "POST"});
      log.push(`✓ ${s.name}`);
    } catch (e){ log.push(`✕ ${s.name}: ${e.message}`); }
  }));
  $("#gvLog").textContent = log.join("\n");
  toast(`${GV_LABEL[act]}: ${log.filter(x => x.startsWith("✓")).length}/${sel.length} ok`, log.some(x => x.startsWith("✕")));
  if (act === "delete") gvSel = new Set();
  setTimeout(async () => { await loadServers(); refreshDash(); renderGameView(); }, act === "delete" ? 3000 : 1500);
});

/* ================= Benachrichtigungen ================= */
async function loadNotify(){
  let d; try { d = await api("/api/notify"); } catch { return; }
  $("#ntEnabled").checked = !!d.enabled; $("#ntWhatsapp").value = d.whatsapp || ""; $("#ntNtfy").value = d.ntfy_url || "";
  $("#ntTgToken").value = d.telegram_token || ""; $("#ntTgChat").value = d.telegram_chat || "";
  $("#ntQuietFrom").value = d.quiet_from || ""; $("#ntQuietTo").value = d.quiet_to || ""; $("#ntRepeat").value = d.repeat_min || 360;
  $("#ntEvents").innerHTML = Object.entries(d.event_labels).map(([k, l]) => `<label class="hint" style="display:flex;gap:5px;align-items:center"><input type="checkbox" data-nte="${k}" ${d.events[k] ? "checked" : ""} style="width:auto"> ${esc(l)}</label>`).join("");
  $("#ntHistory").textContent = (d.history || []).slice(-8).reverse().map(h => `${new Date(h.t * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"})} · ${h.text}${h.errors && h.errors.length ? "  ✕ " + h.errors.join(", ") : ""}`).join("\n");
}
async function saveNotify(){
  const events = {}; $$("[data-nte]").forEach(c => events[c.dataset.nte] = c.checked);
  return api("/api/notify", {method: "PUT", body: {enabled: $("#ntEnabled").checked, whatsapp: $("#ntWhatsapp").value, ntfy_url: $("#ntNtfy").value.trim(),
    telegram_token: $("#ntTgToken").value.trim(), telegram_chat: $("#ntTgChat").value.trim(), events,
    quiet_from: $("#ntQuietFrom").value.trim(), quiet_to: $("#ntQuietTo").value.trim(), repeat_min: parseInt($("#ntRepeat").value, 10) || 360}});
}
$("#btnNtSave").onclick = async () => { try { await saveNotify(); toast("Benachrichtigungen gespeichert"); loadNotify(); } catch (e){ toast(e.message, true); } };
$("#btnNtTest").onclick = async () => { try { await saveNotify(); await api("/api/notify/test", {method: "POST"}); toast("Testnachricht gesendet"); loadNotify(); } catch (e){ toast(e.message, true); loadNotify(); } };

/* ================= Sicherungen ================= */
let bkData = null;
async function loadBackup(){
  try { bkData = await api("/api/backup"); } catch { return; }
  const s = bkData.settings;
  $("#bkEnabled").checked = !!s.enabled; $("#bkTime").value = s.time || "04:30"; $("#bkKeep").value = s.keep || 7; $("#bkDir").value = s.dir || "";
  $("#bkRows").innerHTML = bkData.servers.map(x => `<tr><td><input type="checkbox" data-bk="${esc(x.id)}" ${x.supported ? "" : "disabled"} ${x.supported && !(s.skip || []).includes(x.id) ? "checked" : ""} style="width:auto"></td>
    <td>${gameTile(x.game, 14)} ${esc(x.name)}</td><td class="hint mono" style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(x.paths.join("\n"))}">${x.supported ? esc(x.paths.map(p => p.split("/").pop()).join(", ")) : "–"}</td>
    <td>${x.last ? (x.last.ok ? `<span style="color:var(--ok)">✓</span> ${new Date(x.last.t * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"})}${x.last.bytes ? " · " + fmtBytes(x.last.bytes) : ""}` : `<span style="color:var(--bad)" title="${esc(x.last.msg || "")}">✕ ${esc((x.last.msg || "").slice(0, 60))}</span>`) : `<span class="hint">noch nie</span>`}</td>
    <td>${x.supported ? `<button class="small" data-bkrun="${esc(x.id)}">jetzt</button>` : ""}</td></tr>`).join("");
  $("#bkState").textContent = bkData.running ? "Sicherung läuft …" : "";
  $$("[data-bkrun]").forEach(b => b.onclick = async () => { try { await api(`/api/backup/run?sid=${encodeURIComponent(b.dataset.bkrun)}`, {method: "POST"}); toast("Sicherung läuft"); setTimeout(loadBackup, 8000); } catch (e){ toast(e.message, true); } });
  if (bkData.running && view === "auto") setTimeout(loadBackup, 5000);
}
$("#btnBkSave").onclick = async () => {
  const skip = $$("[data-bk]").filter(c => !c.checked && !c.disabled).map(c => c.dataset.bk);
  try { await api("/api/backup", {method: "PUT", body: {enabled: $("#bkEnabled").checked, time: $("#bkTime").value.trim(), keep: parseInt($("#bkKeep").value, 10) || 7, dir: $("#bkDir").value.trim(), skip}}); toast("Sicherung gespeichert"); loadBackup(); }
  catch (e){ toast(e.message, true); }
};
$("#btnBkRun").onmouseenter = async () => { await loadTimings(); $("#btnBkRun").title = Object.entries(TIMINGS).filter(([k]) => k.startsWith("backup:")).map(([k, t]) => `${GAMES[k.slice(7)]?.label || k.slice(7)}: zuletzt ${fmtDur(t.last)}`).join("\n") || "Noch keine Sicherung gemessen"; };
$("#btnBkRun").onclick = async () => { try { await api("/api/backup/run", {method: "POST"}); toast("Sicherung aller Server läuft"); setTimeout(loadBackup, 8000); } catch (e){ toast(e.message, true); } };
$("#btnGsltMaintain").onclick = async () => { try { const r = await api("/api/gslt/maintain", {method: "POST"}); toast(`Erneuert: ${r.renewed.length + r.manual.length}${r.manual.length ? " (von Hand eintragen: " + r.manual.join(", ") + ")" : ""}${r.errors.length ? " · Fehler: " + r.errors.join("; ") : ""}`, !!r.errors.length); loadGslt(); } catch (e){ toast(e.message, true); } };
$("#btnGsltCleanup").onclick = async () => { if (!confirm("Abgelaufene Tokens, die kein Server benutzt, bei Steam und hier löschen?")) return; try { const r = await api("/api/gslt/cleanup", {method: "POST"}); toast(`Gelöscht: ${r.removed.length ? r.removed.join(", ") : "keine"}`); loadGslt(); } catch (e){ toast(e.message, true); } };

$("#btnNamesApply").onclick = async () => {
  if (!confirm("Alle Server nach dem Namensschema umbenennen? (vorher „Speichern“, falls du das Schema geändert hast)")) return;
  try { const r = await api("/api/names/apply", {method: "POST"}); toast(`${r.renamed.length} Server umbenannt: ` + r.renamed.map(x => x.name).join(", ")); await loadServers(); }
  catch (e){ toast(e.message, true); }
};

/* ================= Prefill: Battle.net / Epic Games ================= */
let pfSvc = "steam", pf2Timer = null;
function showPfSvc(svc){
  pfSvc = svc;
  $$("#pfSvcSeg [data-pfsvc]").forEach(b => b.classList.toggle("active", b.dataset.pfsvc === svc));
  $("#pfSteam").classList.toggle("hidden", svc !== "steam"); $("#pfSteamBtns").classList.toggle("hidden", svc !== "steam");
  $("#pfOther").classList.toggle("hidden", svc === "steam");
  clearTimeout(pf2Timer);
  if (svc === "steam") loadPrefill(); else loadPf2(true);
}
$$("#pfSvcSeg [data-pfsvc]").forEach(b => b.onclick = () => showPfSvc(b.dataset.pfsvc));
async function loadPf2(full){
  clearTimeout(pf2Timer);
  if (view !== "prefill" || pfSvc === "steam") return;
  const svc = pfSvc;
  let d; try { d = await api(`/api/prefill2/${svc}`); } catch (e){ $("#pfOther").innerHTML = `<div class="hint">${esc(e.message)}</div>`; return; }
  const st = d.state, run = st && st.running, s = d.settings || {};
  const status = (run ? (d.paused || d.throttled ? `<span class="pill warn" title="${esc(d.pause_reason || "")}">${d.paused ? "⏸ pausiert" : "🐢 gedrosselt"}${d.pause_reason ? " – " + esc(d.pause_reason) : ""}${d.rate ? " · ↓ " + fmtRate(d.rate) : ""}</span>` : `<span class="pill ok">läuft${d.rate ? " · ↓ " + fmtRate(d.rate) : ""}</span>`)
      : d.queued ? `<span class="pill warn">wartet in der Warteschlange</span>` : st ? `<span class="pill">beendet${st.exit ? " (Code " + st.exit + ")" : ""}</span>` : `<span class="pill">noch nie gelaufen</span>`)
    + (d.queue && d.queue.length ? ` <span class="hint">Warteschlange: ${esc(d.queue.map(x => x === "steam" ? "Steam" : x === "battlenet" ? "Battle.net" : "Epic").join(" → "))}</span>` : "");
  if (full || !$("#pf2Box") || $("#pf2Box").dataset.svc !== svc){
    const opts = svc === "battlenet"
      ? `<div class="hint" style="margin-bottom:6px">Battle.net braucht kein Konto – einfach Spiele wählen.</div>
         <div class="row" style="flex-wrap:wrap;gap:10px">${d.products.map(([k, l]) => `<label class="hint" style="display:flex;gap:5px;align-items:center"><input type="checkbox" data-pf2p="${k}" ${(s.products || []).includes(k) ? "checked" : ""} style="width:auto"> ${esc(l)} <span class="mono">${k}</span></label>`).join("")}</div>
         <div class="row" style="gap:8px;margin-top:8px;align-items:center"><label class="hint">weitere Codes (Leerzeichen getrennt)</label><input id="pf2Extra" class="mono" style="max-width:260px" value="${esc((s.products || []).filter(p => !d.products.some(([k]) => k === p)).join(" "))}"></div>`
      : `<div class="hint" style="margin-bottom:6px">Epic braucht einmal eine Anmeldung: Beim ersten Start erscheint unten ein Link – im Browser öffnen, anmelden, den angezeigten Code hier eintragen. Danach merkt sich der Prefill die Anmeldung.</div>
         <div class="row" style="gap:12px"><label class="hint"><input type="radio" name="pf2mode" value="all" ${s.mode !== "selected" ? "checked" : ""} style="width:auto"> alle Spiele des Kontos</label>
         <label class="hint"><input type="radio" name="pf2mode" value="selected" ${s.mode === "selected" ? "checked" : ""} style="width:auto"> nur zuvor ausgewählte</label></div>`;
    $("#pfOther").innerHTML = `<div class="panel" id="pf2Box" data-svc="${svc}">
      <h2>${esc(d.label)} <span id="pf2Status">${status}</span></h2>
      ${opts}
      <div class="row" style="gap:8px;margin-top:12px;flex-wrap:wrap;align-items:center">
        <button class="primary" id="pf2Run">▶ Vorladen</button><button id="pf2Force" title="alles neu laden, auch was schon im Cache ist">Erzwingen</button><button class="danger" id="pf2Stop">✕ Abbrechen</button>
        <label class="hint" style="margin-left:12px">täglich um</label><input id="pf2Sched" value="${esc(s.schedule || "")}" placeholder="z. B. 03:00" style="max-width:90px"><button class="small" id="pf2SchedSave">Zeitplan speichern</button></div>
      ${durText("prefill", svc, "Letzter Lauf") ? `<div class="hint" style="margin-top:6px">⏱ ${esc(durText("prefill", svc, "Letzter Lauf"))}</div>` : ""}
      <div id="pf2Prompt"></div>
      <pre class="out" id="pf2Log" style="max-height:360px;overflow:auto;margin-top:10px"></pre></div>`;
    const collect = () => svc === "battlenet"
      ? {products: [...$$("[data-pf2p]").filter(c => c.checked).map(c => c.dataset.pf2p), ...($("#pf2Extra").value || "").split(/\s+/).filter(Boolean)]}
      : {mode: ($$('input[name="pf2mode"]').find(r => r.checked) || {}).value || "all"};
    const go = async force => { try { const r = await api(`/api/prefill2/${svc}/run`, {body: {...collect(), force}}); toast(r.queued ? `${d.label}-Prefill wartet – startet, wenn der laufende Prefill fertig ist` : `${d.label}-Prefill gestartet`); setTimeout(() => loadPf2(), 2000); } catch (e){ toast(e.message, true); } };
    $("#pf2Run").onclick = () => go(false);
    $("#pf2Force").onclick = () => go(true);
    $("#pf2Stop").onclick = async () => { try { await api(`/api/prefill2/${svc}/stop`, {method: "POST"}); toast("Abgebrochen"); loadPf2(); } catch (e){ toast(e.message, true); } };
    $("#pf2SchedSave").onclick = async () => { try { await api(`/api/prefill2/${svc}`, {method: "PUT", body: {...collect(), schedule: $("#pf2Sched").value.trim()}}); toast("Zeitplan gespeichert"); } catch (e){ toast(e.message, true); } };
  }
  $("#pf2Status").innerHTML = status;
  const lg = $("#pf2Log"), atEnd = lg.scrollTop + lg.clientHeight >= lg.scrollHeight - 20;
  lg.textContent = d.log || "(noch keine Ausgabe)";
  if (atEnd) lg.scrollTop = lg.scrollHeight;
  $("#pf2Prompt").innerHTML = run && (d.prompt || d.login_url) ? `<div class="pfbanner" style="margin-top:10px">${d.login_url ? `1. Link öffnen und anmelden: <a href="${esc(d.login_url)}" target="_blank" rel="noopener"><b>${esc(d.login_url)}</b></a><br>
        2. Auf der Seite danach steht ein Text mit <span class="mono">"authorizationCode":"…"</span> – nur den Code zwischen den Anführungszeichen kopieren und hier einfügen:<br>` : "Der Prefill wartet auf eine Eingabe:<br>"}
      <div class="row" style="gap:8px;margin-top:6px"><input id="pf2Input" class="mono" placeholder="Code / Eingabe" style="max-width:360px"><button class="primary small" id="pf2Send">Senden</button></div></div>` : "";
  if ($("#pf2Send")) $("#pf2Send").onclick = async () => { try { await api(`/api/prefill2/${svc}/send`, {body: {text: $("#pf2Input").value}}); toast("gesendet"); setTimeout(() => loadPf2(), 1500); } catch (e){ toast(e.message, true); } };
  pf2Timer = setTimeout(() => loadPf2(), run ? 3000 : 15000);
}

/* Letzte 10 Matches in der Verwaltung */
let dashMatchesAt = 0;
async function loadDashMatches(){
  if (view !== "dash" || Date.now() - dashMatchesAt < 30000) return;
  dashMatchesAt = Date.now();
  let ms; try { ms = await api("/api/matches?n=10"); } catch { return; }
  $("#dashMatches").classList.toggle("hidden", !ms.length);
  $("#dashMatchList").innerHTML = ms.map(matchHtml).join("");
}
setInterval(loadDashMatches, 5000);

/* ================= Interne Platte & Docker-Reste ================= */
async function loadDocker(){
  $("#dkBody").innerHTML = `<span class="hint">wird gemessen … (kann etwas dauern)</span>`;
  let d; try { d = await api("/api/storage/docker"); } catch (e){ $("#dkBody").innerHTML = `<span class="hint">${esc(e.message)}</span>`; return; }
  const k = d.disk || {};
  $("#dkSub").textContent = k.total ? `${fmtBytes(k.free)} frei von ${fmtBytes(k.total)} (${Math.round(k.used / k.total * 100)} % belegt)` : "";
  const row = (label, bytes, info, btn) => `<tr><td>${label}</td><td class="mono">${fmtBytes(bytes || 0)}</td><td class="hint">${info || ""}</td><td>${btn || ""}</td></tr>`;
  const b = (what, txt, danger) => `<button class="small${danger ? " danger" : ""}" data-prune="${what}">${txt}</button>`;
  $("#dkBody").innerHTML = `${k.total ? `<div class="bar" style="margin:4px 0 10px"><i style="width:${Math.round(k.used / k.total * 100)}%;background:${k.free < 30e9 ? "var(--bad)" : "var(--ct)"}"></i></div>` : ""}
    <table class="cachetable dktable"><colgroup><col style="width:190px"><col style="width:90px"><col><col style="width:170px"></colgroup><thead><tr><th>Was</th><th>Größe</th><th></th><th></th></tr></thead><tbody>
    ${row("Images gesamt", d.images.bytes, `${d.images.count} Images`)}
    ${row("&nbsp;· davon unbenutzt", d.images.unused_bytes, `${d.images.unused_count} Images ohne Container – z. B. alte Versionen nach Updates`, b("images", "Unbenutzte löschen", true))}
    ${row("&nbsp;· davon ohne Namen (Reste)", d.images.dangling_bytes, `${d.images.dangling_count} alte Schichten`, b("dangling", "Reste löschen"))}
    ${row("Gestoppte Container", d.containers.stopped_bytes, `${d.containers.stopped} von ${d.containers.count}${d.containers.stopped_list.some(c => c.helper) ? " · Hilfs-Container des Tools werden gelöscht, Spielserver nicht" : ""}`, b("helpers", "Hilfs-Container löschen"))}
    ${row("Volumes", d.volumes.bytes, `${d.volumes.count} Volumes${d.volumes.unused.length ? ` · ${d.volumes.unused.length} unbenutzt (${fmtBytes(d.volumes.unused.reduce((x, v) => x + (v.bytes || 0), 0))}) – Liste unten` : ""}`, d.volumes.unused.length ? b("anon_volumes", "Unbenannte löschen", true) : "")}
    ${row("Build-Cache", d.build_cache.bytes, `${d.build_cache.count} Einträge`, d.build_cache.bytes ? b("buildcache", "Leeren") : "")}
    </tbody></table>
    ${d.images.unused_list.length ? `<details style="margin-top:8px"><summary class="hint">Unbenutzte Images anzeigen</summary><div class="hint mono dklist">${d.images.unused_list.map(i => esc(i.name) + " · " + fmtBytes(i.bytes)).join("<br>")}</div></details>` : ""}
    ${d.volumes.unused.length ? `<details style="margin-top:6px"><summary class="hint">Unbenutzte Volumes anzeigen</summary><div class="hint mono dklist">${d.volumes.unused.map(v => esc(v.name) + " · " + fmtBytes(v.bytes)).join("<br>")}</div></details>` : ""}
    <h3 class="pdsec" style="margin-top:14px">Systemplatte außerhalb von Docker <button class="small" id="btnSysScan">messen</button></h3><div id="sysDisk" class="hint">…</div>
    <div class="hint" style="margin-top:8px">Nicht von hier messbar: Container-Logs und Dateien außerhalb von Docker (z. B. Home-Verzeichnis). Auf dem Server prüfen mit <span class="mono">sudo du -xh / --max-depth=2 | sort -h | tail -20</span>.</div>`;
  $$("[data-prune]").forEach(btn => btn.onclick = async () => {
    const what = btn.dataset.prune;
    const msg = {images: "Alle Images löschen, die gerade kein Container nutzt? Werden bei Bedarf neu geladen (über den Lancache).", dangling: "Image-Reste löschen?",
      helpers: "Gestoppte Hilfs-Container des Tools löschen?", buildcache: "Build-Cache leeren?", anon_volumes: "Unbenannte, unbenutzte Volumes löschen? Benannte Volumes (Spieldaten) bleiben."}[what];
    if (!confirm(msg)) return;
    btn.disabled = true; btn.textContent = "läuft …";
    try { const r = await api("/api/storage/docker/prune", {body: {what}}); toast(`${fmtBytes(r.freed)} freigegeben (${r.count} entfernt)`); }
    catch (e){ toast(e.message, true); }
    loadDocker();
  });
}
$("#btnDkRefresh").onclick = loadDocker;
let sysTimer = null;
async function loadSysDisk(refresh){
  clearTimeout(sysTimer);
  let r; try { r = await api("/api/storage/systemdisk" + (refresh ? "?refresh=1" : "")); } catch (e){ if ($("#sysDisk")) $("#sysDisk").textContent = e.message; return; }
  if (!$("#sysDisk")) return;
  $("#sysDisk").innerHTML = (r.items || []).length ? `<table class="cachetable"><tbody>${r.items.map(x => `<tr><td class="mono">${esc(x.path)}</td><td class="mono">${x.bytes != null ? fmtBytes(x.bytes) : "?"}</td>
      <td class="hint">${x.kind === "home" ? (x.in_use ? "🔒 genutzt von " + esc((x.used_by || []).join(", ")) : "nicht von Containern genutzt") : esc(x.hint || "")}</td>
      <td>${x.kind === "old_cache" && !x.in_use && x.bytes ? `<button class="small danger" id="btnOldCache">Alten Cache löschen</button>` : ""}</td></tr>`).join("")}</tbody></table>
      <div class="hint">Home-Ordner löschst du selbst per SSH (z. B. <span class="mono">rm -r ~/steam-content</span>) – genutzte (🔒) bitte behalten.</div>`
    : (r.busy ? "wird gemessen … (bei großen Ordnern einige Minuten)" : "noch nicht gemessen");
  if ($("#btnOldCache")) $("#btnOldCache").onclick = async () => {
    if (!confirm("Alten Lancache-Ordner komplett leeren? Der aktuelle Cache liegt auf der iSCSI-LUN und bleibt.")) return;
    try { await api("/api/storage/systemdisk/delete-old-cache", {method: "POST"}); toast("Wird im Hintergrund gelöscht"); } catch (e){ toast(e.message, true); }
  };
  if (r.busy && view === "storage") sysTimer = setTimeout(() => loadSysDisk(), 10000);
}
document.addEventListener("click", e => { if (e.target && e.target.id === "btnSysScan"){ loadSysDisk(true); setTimeout(() => loadSysDisk(), 3000); } });

/* ================= Steam-Bot „GrohLan“ ================= */
let botData = null, botLoaded = false;
const botSel = new Set();
async function loadBot(){
  try { botData = await api("/api/steambot"); } catch (e) { $("#botStatus").innerHTML = `<div class="hint">${esc(e.message)}</div>`; return; }
  const d = botData, s = d.settings, st = d.status || {}, b = st.bot || {};
  if (!botLoaded || !$("#view-bot").contains(document.activeElement)){
    $("#botEnabled").checked = !!s.enabled; $("#botAuto").checked = s.auto_add !== false;
    $("#botName").value = s.bot_name || "GrohLan"; $("#botRecent").value = s.recent_hours || 24; $("#botMaxAge").value = s.max_age_days || 7;
    botLoaded = true;
  }
  $("#botTitle").textContent = s.bot_name || "GrohLan";
  const c = st.container;
  let h = "";
  if (!s.enabled) h = `<div class="hint">Bot ist aus. Einschalten und speichern – dann startet ein kleiner Container für den Bot.</div>`;
  else if (!c || !c.running) h = `<div class="hint">Bot-Container startet …</div>`;
  else if (st.error) h = `<div class="hint">${esc(st.error)}</div>`;
  else {
    const ok = b.state === "angemeldet";
    h = `<div><b style="color:${ok ? "var(--ok)" : "var(--accent)"}">${esc(b.state || "?")}</b>${b.name ? " als " + esc(b.name) : ""}${b.steamid ? ` <span class="hint mono">${esc(b.steamid)}</span>` : ""}${b.error ? `<div class="hint" style="color:var(--bad)">${esc(b.error)}</div>` : ""}</div>`;
    if (ok && (b.limited || b.can_invite === false)) h += `<div class="pill warn" style="margin-top:6px;white-space:normal">Eingeschränktes Steam-Konto – kann keine Freundschaftsanfragen schicken. Auf dem Bot-Konto einmal mind. 5 $ ausgeben (z. B. Guthaben aufladen).</div>`;
    if (b.need_code) h += `<div style="margin-top:8px"><label class="hint">${b.need_code === "email" ? "Code aus der E-Mail von Steam" : "Code aus der Steam-App (Steam Guard)"}${b.last_code_wrong ? " – letzter Code war falsch" : ""}</label>
      <div class="row" style="gap:6px"><input id="botCode" maxlength="12" style="width:120px" autocomplete="one-time-code"><button class="primary" id="botCodeSend">Senden</button></div></div>`;
    else if (!ok && !/meldet an/.test(b.state || "")) h += `<div style="margin-top:8px"><div class="hint">Mit dem Steam-Konto des Bots anmelden (eigenes Konto, nicht dein privates). Das Passwort wird nicht gespeichert – der Bot merkt sich nur ein Anmelde-Token.</div>
      <div class="row" style="gap:6px;margin-top:6px;flex-wrap:wrap"><input id="botUser" placeholder="Steam-Benutzername" autocomplete="off" style="width:180px"><input id="botPw" type="password" placeholder="Passwort" autocomplete="new-password" style="width:160px"><button class="primary" id="botLogin">Anmelden</button></div></div>`;
    if (ok) h += `<div class="hint" style="margin-top:6px">${(b.friends || []).filter(f => f.rel === "Friend").length} Freunde · <a href="#" id="botLogout">abmelden</a></div>`;
  }
  const typing = $("#botStatus").contains(document.activeElement) && document.activeElement.tagName === "INPUT";
  if (!typing) $("#botStatus").innerHTML = h;
  if ($("#botCodeSend")) $("#botCodeSend").onclick = async () => { try { await api("/api/steambot/code", {body: {code: $("#botCode").value.trim()}}); toast("Code gesendet"); setTimeout(loadBot, 2500); } catch (e) { toast(e.message, true); } };
  if ($("#botLogin")) $("#botLogin").onclick = async () => { try { await api("/api/steambot/login", {body: {user: $("#botUser").value.trim(), password: $("#botPw").value}}); $("#botPw").value = ""; toast("Melde an …"); setTimeout(loadBot, 3000); } catch (e) { toast(e.message, true); } };
  if ($("#botLogout")) $("#botLogout").onclick = async e => { e.preventDefault(); if (!confirm("Bot abmelden? Danach muss er sich mit Passwort neu anmelden.")) return; try { await api("/api/steambot/logout", {method: "POST"}); loadBot(); } catch (er) { toast(er.message, true); } };
  // Spieler
  const ago = t => { if (!t) return "–"; const m = (Date.now() / 1000 - t) / 60; return m < 60 ? Math.round(m) + " min" : m < 1440 ? Math.round(m / 60) + " h" : Math.round(m / 1440) + " Tage"; };
  $("#botPlayers").innerHTML = d.players.length ? `<table class="cachetable"><thead><tr><th></th><th>Spieler</th><th>zuletzt gesehen</th><th>Bot</th><th>Steam</th><th></th></tr></thead><tbody>${d.players.map(p => `<tr>
      <td><input type="checkbox" data-botsel="${esc(p.steamid)}" ${botSel.has(p.steamid) ? "checked" : ""} ${p.status === "Freund" ? "" : "disabled title=\"Erst wenn die Freundschaftsanfrage angenommen ist\""} style="width:auto"></td>
      <td><div class="row" style="gap:8px;flex-wrap:nowrap">${p.avatar ? `<img class="avatar" src="${esc(p.avatar)}" alt="">` : `<span class="avatar" style="display:inline-block"></span>`}
        <div><b>${esc(p.name)}</b>${p.recent ? ` <span class="pill ok">gerade auf der LAN</span>` : ""}<div class="hint mono">${esc(p.steamid)}${p.lan_manual ? " · von Hand als LAN markiert" : ""}</div></div></div></td>
      <td class="hint">vor ${ago(p.last_seen)}</td>
      <td>${p.status === "Freund" ? `<span style="color:var(--ok)">✓ Freund</span>` : esc(p.status)}</td>
      <td class="hint">${p.online == null ? "" : p.online ? (p.playing ? "spielt " + esc(p.playing) : "online") : "offline"}</td>
      <td>${p.status === "Freund" || p.status === "angefragt" ? "" : `<button class="small" data-botadd="${esc(p.steamid)}">Anfragen</button>`}</td></tr>`).join("")}</tbody></table>`
    : `<div class="hint">Noch keine LAN-Spieler mit SteamID – sie erscheinen, sobald jemand aus dem LAN auf einem Server spielt (oder unter „Spieler“ von Hand als LAN markiert wird).</div>`;
  $$("[data-botsel]").forEach(c => c.onchange = () => { c.checked ? botSel.add(c.dataset.botsel) : botSel.delete(c.dataset.botsel); $("#botSelN").textContent = botSel.size; });
  $$("[data-botadd]").forEach(btn => btn.onclick = async () => { try { await api(`/api/steambot/add/${btn.dataset.botadd}`, {method: "POST"}); toast("Freundschaftsanfrage gesendet"); loadBot(); } catch (e) { toast(e.message, true); } });
  $("#botSelN").textContent = botSel.size;
  const names = Object.fromEntries(d.players.map(p => [p.steamid, p.name]));
  $("#botMsgs").innerHTML = (d.messages || []).slice().reverse().map(m => `<div>${new Date(m.t * 1000).toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"})} ${m.dir === "in" ? "⬅ <b>" + esc(names[m.from] || m.from) + "</b>" : "➡ " + esc(names[m.to] || m.to)}: ${esc(m.text)}</div>`).join("") || "noch keine";
}
$("#botSave").onclick = async () => {
  try {
    await api("/api/steambot", {method: "PUT", body: {enabled: $("#botEnabled").checked, auto_add: $("#botAuto").checked, bot_name: $("#botName").value.trim() || "GrohLan",
      recent_hours: +$("#botRecent").value || 24, max_age_days: +$("#botMaxAge").value || 7}});
    toast("Gespeichert"); botLoaded = false; setTimeout(loadBot, 1500);
  } catch (e) { toast(e.message, true); }
};
async function botSend(all){
  const text = $("#botText").value.trim();
  if (!text) return toast("Erst eine Nachricht eingeben", true);
  if (!all && !botSel.size) return toast("Erst Spieler auswählen", true);
  if (all && !confirm(`Nachricht an alle Spieler der letzten ${(botData && botData.settings.recent_hours) || 24} h schicken?`)) return;
  try {
    const r = await api("/api/steambot/message", {body: {text, all, steamids: [...botSel]}});
    toast(`Gesendet an ${r.done.length}${r.failed && r.failed.length ? `, ${r.failed.length} fehlgeschlagen` : ""}${r.skipped ? `, ${r.skipped} übersprungen (noch nicht Freund)` : ""}`);
    $("#botText").value = ""; loadBot();
  } catch (e) { toast(e.message, true); }
}
$("#botSendAll").onclick = () => botSend(true);
$("#botSendSel").onclick = () => botSend(false);
setInterval(() => { if (view === "bot" && !document.hidden) loadBot(); }, 5000);

/* ================= Turnier ================= */
const tTime = t => t ? new Date(t * 1000).toLocaleTimeString("de-DE", {hour: "2-digit", minute: "2-digit"}) : "–";
const tStatus = {setup: "Vorbereitung", waiting: "wartet auf Server", running: "läuft", done: "beendet"};
// Turnierbaum/Spielplan: Spalten je Runde, Gruppentabellen, nächste Matches
function tourBoardHtml(v, admin){
  if (!v || !v.matches || !v.matches.length) return `<div class="hint">Noch kein Spielplan.</div>`;
  if (!admin) return glShow(v);
  let h = "";
  const live = v.matches.filter(m => m.status === "live");
  const next = v.matches.filter(m => m.status === "ready" || (m.status === "wait" && m.planned)).sort((a, b) => (a.planned || 0) - (b.planned || 0)).slice(0, 6);
  if (live.length || next.length) h += `<div class="tsec"><h3>${live.length ? "🔴 Läuft gerade &amp; als Nächstes" : "Als Nächstes"}</h3><div class="tnext">${[...live, ...next].map(m => tmCard(m, admin, true)).join("")}</div></div>`;
  const byStage = st => v.matches.filter(m => st.includes(m.stage));
  // Gruppen: Tabelle + Spiele der Gruppe nebeneinander
  const gnames = Object.keys(v.groups || {});
  if (gnames.length) h += `<div class="tsec"><h3>Gruppenphase</h3><div class="tgroups">${gnames.map(g => groupBox("Gruppe " + g, v.groups[g], byStage("G").filter(m => m.group === g), admin)).join("")}</div></div>`;
  if (v.table) h += `<div class="tsec"><h3>Jeder gegen jeden</h3><div class="tgroups">${groupBox("Tabelle", v.table, byStage("R"), admin, true)}</div></div>`;
  // K.-o.-Bäume
  const W = byStage("W"), K = byStage("K"), L = byStage("L"), F = byStage("F");
  if (K.length) h += bracketHtml("K.-o.-Phase", K, [], admin);
  if (W.length) h += bracketHtml(L.length ? "Winner-Bracket" : "K.-o.-Baum", W, F, admin);
  if (L.length) h += bracketHtml("Loser-Bracket", L, [], admin);
  if (v.leaders && v.leaders.length) h += `<div class="tsec"><h3>Beste Spieler</h3><table class="cachetable"><thead><tr><th>#</th><th>Spieler</th><th>Team</th><th title="angelehnt an HLTV Rating 3.0 (1,00 = Durchschnitt)">Rating</th><th>K/D</th><th>Kills</th><th>Tode</th><th>ADR</th><th>KAST</th><th>HS %</th><th>Siege</th></tr></thead><tbody>
    ${v.leaders.map((r, i) => `<tr><td>${i + 1}</td><td><b>${esc(r.name)}</b></td><td>${esc(r.team || "")}</td><td class="mono"><b>${(r.rating ?? 0).toFixed(2)}</b></td><td class="mono">${(r.kd ?? 0).toFixed(2)}</td><td class="mono">${r.kills}</td><td class="mono">${r.deaths}</td><td class="mono">${r.adr ?? "–"}</td><td class="mono">${r.kast_pct ?? "–"}%</td><td class="mono">${r.hs_pct}%</td><td class="mono">${r.wins}/${r.matches}</td></tr>`).join("")}</tbody></table></div>`;
  return h;
}
function groupBox(title, rows, ms, admin, rounds){
  const tbl = `<table class="cachetable"><thead><tr><th>${esc(title)}</th><th title="Spiele">Sp</th><th title="Siege">S</th><th title="Niederlagen">N</th><th title="Runden gewonnen:verloren">Runden</th></tr></thead><tbody>
    ${(rows || []).map((r, i) => `<tr class="${i < 2 && !rounds ? "adv" : ""}"><td>${i + 1}. <b>${esc(r.name)}</b></td><td class="mono">${r.played}</td><td class="mono">${r.won}</td><td class="mono">${r.lost}</td><td class="mono">${r.rf}:${r.ra}</td></tr>`).join("")}</tbody></table>`;
  const list = ms.sort((a, b) => a.round - b.round || (a.no || 0) - (b.no || 0)).map(m => admin ? tmCard(m, true) : tmMini(m)).join("");
  return `<div class="tgroup">${tbl}<div class="${admin ? "tglist adm" : "tglist"}">${list}</div></div>`;
}
function tmMini(m){
  const sc = m.status === "live" || m.status === "done" ? `${m.s1 ?? 0}<i>:</i>${m.s2 ?? 0}` : (m.planned ? tTime(m.planned) : "–");
  const w1 = m.winner && m.winner === m.t1, w2 = m.winner && m.winner === m.t2;
  return `<div class="tmini ${m.status}"><span class="${w1 ? "w" : ""}">${esc(m.t1 || m.p1 || "?")}</span><b>${sc}</b><span class="${w2 ? "w" : ""}">${esc(m.t2 || m.p2 || "?")}</span>${m.status === "live" ? tvBtn(m, true) : ""}</div>`;
}
function tvBtn(m, small){
  return m.tv_url ? `<a class="tvbtn${small ? " sm" : ""}" href="${esc(m.tv_url)}" title="Per CSTV zuschauen (startet CS2)">👁${small ? "" : " Zuschauen"}</a>` : "";
}
function bracketHtml(title, ms, tail, admin){
  const rounds = {};
  ms.forEach(m => (rounds[m.round] = rounds[m.round] || []).push(m));
  const cols = Object.keys(rounds).map(Number).sort((a, b) => a - b).map(r => rounds[r].sort((a, b) => (a.no || 0) - (b.no || 0)));
  if (tail.length) cols.push(tail);
  const name = c => (c[0].label || "").split(" · ").pop();
  return `<div class="tsec"><h3>${esc(title)}</h3><div class="bk">${cols.map((c, i) => {
    const nx = cols[i + 1], cls = !nx ? "" : nx.length * 2 === c.length ? "half" : "same";
    return `<div class="bkcol ${cls} ${i ? "prev" : ""}"><h4>${esc(name(c))}</h4><div class="bkslots">${c.map(m =>
      `<div class="bkslot"><i class="cin"></i>${tmCard(m, admin)}</div>`).join("")}</div></div>`;
  }).join("")}</div></div>`;
}
function tmCard(m, admin, big){
  const show = m.status === "live" || m.status === "done";
  const canSwap = k => admin && m["f" + k] && (m.status === "wait" || m.status === "ready" || m.walkover);
  const row = (t, p, s, win, k) => `<div class="tr ${win ? "win" : ""} ${t ? "" : "tbd"} ${canSwap(k) ? "drag" : ""}"${canSwap(k) ? ` draggable="true" data-sm="${m.id}" data-ss="${k}" title="Ziehen, um mit einem anderen Team zu tauschen"` : ""}><b>${esc(t || p || "noch offen")}</b><span class="sc">${show && !m.walkover ? (s ?? 0) : ""}</span></div>`;
  const meta = m.status === "done" ? (m.walkover ? "Freilos" : "beendet") : m.status === "live" ? `<span class="livedot">LIVE</span> ${esc(m.server_name || "")} · ${esc(m.map || "")}` :
    `${m.planned ? tTime(m.planned) + " Uhr" : ""}${m.server_name ? " · " + esc(m.server_name) : ""}${m.map ? " · " + esc(m.map) : ""}`;
  const bye = m.walkover || m.t1 === "Freilos" || m.t2 === "Freilos";
  return `<div class="tm ${m.status} ${bye ? "bye" : ""}">${big ? `<div class="meta" style="margin:0 0 3px">${esc(m.label)}</div>` : ""}
    ${m.no ? `<span class="tno">#${m.no}</span>` : ""}
    ${row(m.t1, m.p1, m.s1, m.winner && m.winner === m.t1, "1")}${row(m.t2, m.p2, m.s2, m.winner && m.winner === m.t2, "2")}
    <div class="meta tmeta"><span>${meta}</span>${m.status === "live" ? tvBtn(m) : ""}</div>
    ${admin && (m.status === "ready" || m.status === "live" || m.status === "done") && !m.walkover ? `<div class="row" style="gap:4px;margin-top:5px;flex-wrap:nowrap">
      <input type="number" min="0" value="${m.s1 ?? ""}" data-ts1="${m.id}" style="width:48px;padding:2px 4px"><input type="number" min="0" value="${m.s2 ?? ""}" data-ts2="${m.id}" style="width:48px;padding:2px 4px">
      <button class="small" data-tres="${m.id}" title="Ergebnis von Hand eintragen">✓</button>
      ${m.status === "ready" ? `<button class="small" data-tload="${m.id}" title="Jetzt auf dem Server laden">▶</button>` : ""}
      ${m.status !== "ready" ? `<button class="small" data-trst="${m.id}" title="Ergebnis zurücksetzen">↺</button>` : ""}</div>` : ""}</div>`;
}
// --- Übersicht im GrohLAN-Look: gespiegelter Turnierbaum, Pokal in der Mitte, Gruppen darunter
const GL_TROPHY = `<svg viewBox="0 0 120 110" class="gltrophy" aria-hidden="true"><defs><linearGradient id="glg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f3cf47"/><stop offset="1" stop-color="#e39a2f"/></linearGradient></defs>
  <path d="M38 8h44v26c0 16-10 28-22 28S38 50 38 34z" fill="url(#glg)"/><path d="M38 14H22c0 16 8 26 20 28M82 14h16c0 16-8 26-20 28" fill="none" stroke="url(#glg)" stroke-width="5" stroke-linecap="round"/>
  <rect x="54" y="60" width="12" height="16" fill="url(#glg)"/><path d="M42 76h36l4 12H38z" fill="url(#glg)"/><rect x="34" y="88" width="52" height="8" rx="2" fill="url(#glg)"/>
  <path d="M10 70c4-14 10-22 18-26M110 70c-4-14-10-22-18-26" fill="none" stroke="#9fc33a" stroke-width="3" stroke-linecap="round"/>
  <g fill="#9fc33a"><ellipse cx="13" cy="58" rx="3" ry="6" transform="rotate(-30 13 58)"/><ellipse cx="18" cy="49" rx="3" ry="6" transform="rotate(-40 18 49)"/><ellipse cx="107" cy="58" rx="3" ry="6" transform="rotate(30 107 58)"/><ellipse cx="102" cy="49" rx="3" ry="6" transform="rotate(40 102 49)"/></g></svg>`;
function glPill(m, n, side){
  const t = n === 1 ? m.t1 : m.t2, p = n === 1 ? m.p1 : m.p2, sc = n === 1 ? m.s1 : m.s2;
  const show = (m.status === "live" || m.status === "done") && !m.walkover;
  const win = m.winner && m.winner === t, lose = m.status === "done" && m.winner && !win;
  return `<div class="glpill ${side} ${win ? "win" : ""} ${lose ? "lose" : ""} ${t ? "" : "tbd"}"><span class="gln">${esc(t || p || "offen")}</span><span class="gls">${show ? (sc ?? 0) : ""}</span></div>`;
}
function glMatch(m, side){
  const info = m.status === "live" ? `<span class="livedot">LIVE</span>${m.server_name ? " " + esc(m.server_name) : ""}` :
    m.status === "done" ? "" : (m.planned ? tTime(m.planned) + " Uhr" : "");
  return `<div class="glm ${m.status} ${m.walkover ? "bye" : ""}" title="${esc(m.label)}${m.map ? " · " + esc(m.map) : ""}">
    ${glPill(m, 1, side)}${glPill(m, 2, side)}
    ${info || m.status === "live" ? `<div class="glinfo"><span>${info}</span>${m.status === "live" ? tvBtn(m, false) : ""}</div>` : ""}</div>`;
}
function glCols(cols, side){
  // cols: Runden (Listen von Matches) von außen nach innen
  return cols.map((c, i) => {
    const nx = cols[i + 1], cls = !nx ? "last" : nx.length * 2 === c.length ? "half" : "same";
    return `<div class="glcol ${cls}"><div class="glh">${esc((c[0].label || "").split(" · ").pop())}</div><div class="glslots">${c.map(m => `<div class="glslot">${glMatch(m, side)}</div>`).join("")}</div></div>`;
  }).join("");
}
function glTree(ms, finals){
  const rounds = {};
  ms.forEach(m => (rounds[m.round] = rounds[m.round] || []).push(m));
  const cols = Object.keys(rounds).map(Number).sort((a, b) => a - b).map(r => rounds[r].sort((a, b) => (a.no || 0) - (b.no || 0)));
  const fin = cols.length && cols[cols.length - 1].length === 1 ? cols.pop()[0] : null;
  const left = cols.map(c => c.slice(0, c.length / 2)), right = cols.map(c => c.slice(c.length / 2));
  const last = finals.length ? finals[finals.length - 1] : fin;
  const champ = last && last.status === "done" ? last.winner : null;
  return `<div class="gltree cup ${finals.length ? "xf" : ""}">
    ${left.length ? `<div class="glside left">${glCols(left, "left")}</div>` : ""}
    <div class="glcenter"><div class="glh">&nbsp;</div><div class="glslots"><div class="glslot"><div class="glfin">
      <div class="glcup">${champ ? `<div class="glchamp">${esc(champ)}</div>` : ""}${GL_TROPHY}${fin ? `<div class="glh">${esc(fin.label.split(" · ").pop())}</div>` : ""}</div>
      ${fin ? glMatch(fin, "mid") : ""}
      ${finals.length ? `<div class="glextra">${finals.map(f => `<div class="glh">${esc(f.label)}</div>${glMatch(f, "mid")}`).join("")}</div>` : ""}
    </div></div></div></div>
    ${right.length ? `<div class="glside right">${glCols(right, "right")}</div>` : ""}</div>`;
}
// Stream-Player bleibt beim Neuzeichnen erhalten (Video-Element wird nur umgehängt)
let glSt = null;
function glStreamAttach(s){
  const slot = document.getElementById("glStreamSlot");
  if (!s || !s.enabled || !s.on_air || !slot){ if (glSt && !slot){ if (glSt.h) glSt.h.destroy(); glSt = null; } return; }
  if (!glSt || glSt.src !== s.hls){
    if (glSt && glSt.h) glSt.h.destroy();
    const v = document.createElement("video");
    v.controls = true; v.autoplay = true; v.muted = true; v.playsInline = true; v.className = "glvideo";
    glSt = {el: v, src: s.hls, h: null};
    const go = () => {     // hls.js zuerst (Chrome meldet inzwischen „HLS kann ich“, spielt fMP4-Live aber nicht ab)
      if (window.Hls && Hls.isSupported()){ glSt.h = new Hls({liveSyncDurationCount: 2}); glSt.h.loadSource(s.hls); glSt.h.attachMedia(v);
        glSt.h.on(Hls.Events.ERROR, (e, d) => { if (d.fatal && glSt){ glSt.h.destroy(); glSt = null; } }); }
      else if (v.canPlayType("application/vnd.apple.mpegurl")) v.src = s.hls;     // iPhone/Safari
    };
    if (window.Hls) go();
    else { const sc = document.createElement("script"); sc.src = "/static/hls.min.js"; sc.onload = go; sc.onerror = go; document.head.appendChild(sc); }
  }
  slot.appendChild(glSt.el);
  if (glSt.el.paused) glSt.el.play().catch(() => {});
}
function glLeaders(L, n, dm){
  const head = dm ? `<th>#</th><th>Spieler</th><th>Kills</th><th>Tode</th><th title="Kills / Tode">K/D</th><th title="Anteil Kopfschüsse an den Kills">HS %</th>`
    : `<th>#</th><th>Spieler</th><th title="Spielerbewertung angelehnt an HLTV Rating 3.0 – 1,00 = Durchschnitt">Rating</th><th title="Kills / Tode">K/D</th><th>Kills</th><th>Tode</th><th title="Schaden je Runde">ADR</th><th title="Anteil Kopfschüsse an den Kills">HS %</th><th title="Gewonnene / gespielte Matches">Siege</th>`;
  return `<table class="glleaders"><thead><tr>${head}</tr></thead><tbody>
    ${L.slice(0, n).map((r, i) => `<tr class="${i < 3 ? "top" : ""}"><td class="rk">${i + 1}</td><td><b>${esc(r.name)}</b>${r.team ? `<span class="tmn">${esc(r.team)}</span>` : ""}</td>
      ${dm ? `<td class="kd">${r.kills}</td><td>${r.deaths}</td><td>${(r.kd ?? 0).toFixed(2)}</td><td>${r.hs_pct}%</td>`
           : `<td class="kd">${(r.rating ?? 0).toFixed(2)}</td><td>${(r.kd ?? 0).toFixed(2)}</td><td>${r.kills}</td><td>${r.deaths}</td><td>${r.adr ?? "–"}</td><td>${r.hs_pct}%</td><td>${r.wins}/${r.matches}</td>`}</tr>`).join("")}</tbody></table>`;
}
function glShow(v){
  const by = st => v.matches.filter(m => st.includes(m.stage));
  const live = v.matches.filter(m => m.status === "live");
  const next = v.matches.filter(m => m.status === "ready" || (m.status === "wait" && m.planned)).sort((a, b) => (a.planned || 0) - (b.planned || 0)).slice(0, 4);
  let h = "";
  if (live.length || next.length) h += `<div class="glsec"><h3>${live.length ? "Live &amp; als Nächstes" : "Als Nächstes"}</h3><div class="glnext">${[...live, ...next].map(m =>
    `<div class="glcard"><div class="glh">${esc(m.label)}${m.map ? " · " + esc(m.map) : ""}</div>${glMatch(m, "left")}</div>`).join("")}</div></div>`;
  const W = by("W"), K = by("K"), L = by("L"), F = by("F");
  // Live-Stream unter dem Turnierbaum (sonst „Stream offline“ + Hinweis auf CSTV)
  const sv = v.stream, stH = !sv ? "" : sv.enabled && sv.on_air
    ? `<div class="glstream"><div class="glstreamcap"><span class="livedot">LIVE</span> ${esc(sv.match || sv.title || "Live-Stream")}</div><div id="glStreamSlot" class="glstreamslot"></div></div>`
    : `<div class="glstream off">📺 Stream offline${live.length ? " – live zuschauen im Spiel per CSTV: 👁 Zuschauen bei den laufenden Spielen" : ""}</div>`;
  if (K.length) h += `<div class="glsec"><h3>K.-o.-Phase</h3>${glTree(K, [])}</div>`;
  if (W.length) h += `<div class="glsec"><h3>${L.length ? "Winner-Bracket" : "Turnierbaum"}</h3>${glTree(W, F)}</div>`;
  if (L.length){
    const rounds = {};
    L.forEach(m => (rounds[m.round] = rounds[m.round] || []).push(m));
    const cols = Object.keys(rounds).map(Number).sort((a, b) => a - b).map(r => rounds[r]);
    h += `<div class="glsec"><h3>Loser-Bracket</h3><div class="gltree"><div class="glside left">${glCols(cols, "left")}</div></div></div>`;
  }
  if (stH) h += `<div class="glsec"><h3>Live-Stream</h3>${stH}</div>`;     // Stream unter dem Turnierbaum
  const groups = Object.entries(v.groups || {}).map(([g, rows]) => ["Gruppe " + g, rows, by("G").filter(m => m.group === g)]);
  if (v.table) groups.push(["Tabelle", v.table, by("R")]);
  if (groups.length) h += `<div class="glsec"><h3>${v.table ? "Jeder gegen jeden" : "Gruppenphase"}</h3><div class="glgroups">${groups.map(([title, rows, ms]) => `<div class="glgroup">
    <div class="glgh">${esc(title)}</div><div class="glgb">
      ${rows.map((r, i) => `<div class="glrow ${i < 2 && !v.table ? "adv" : ""}"><span class="glrk">${i + 1}</span><b>${esc(r.name)}</b><span title="Siege–Niederlagen">${r.won}–${r.lost}</span><span class="mono" title="Runden">${r.rf}:${r.ra}</span></div>`).join("")}
      <div class="glgm">${ms.sort((a, b) => a.round - b.round || (a.no || 0) - (b.no || 0)).map(tmMini).join("")}</div></div></div>`).join("")}</div></div>`;
  if (v.leaders && v.leaders.length) h += `<div class="glsec"><h3>Beste Spieler</h3>${glLeaders(v.leaders, 10)}</div>`;
  return `<div class="gl">${h}</div>`;
}

function tourSrvCheckHtml(c){
  if (!c || !c.need) return "";
  if (c.ok) return `<div class="srvcheck ok">✓ ${c.online} von ${c.need} nötigen Servern online – genug, damit die erste Runde gleichzeitig läuft.</div>`;
  const parts = [];
  if (c.offline.length) parts.push(`<button class="small" data-tsrv="start">▶ ${c.offline.length} ausgeschaltete starten</button>`);
  if (c.create) parts.push(`<button class="small primary" data-tsrv="create" data-n="${c.create}">+ ${c.create} neue${c.create === 1 ? "n" : ""} Server anlegen</button>`);
  if (c.offline.length && c.create) parts.push(`<button class="small primary" data-tsrv="both" data-n="${c.create}">Beides</button>`);
  if (c.status === "setup" && c.matches) parts.push(`<span style="flex-basis:100%"></span><button class="small" data-tstart="wait">▶ Turnier starten, sobald alle Server da sind</button><button class="small" data-tstart="now">▶ Jetzt mit ${c.online} Server${c.online === 1 ? "" : "n"} starten</button>`);
  if (c.status === "waiting") parts.push(`<span style="flex-basis:100%">⏳ Turnier wartet auf die Server und startet automatisch.</span><button class="small" data-tstart="now">▶ Nicht warten – jetzt mit ${c.online} starten</button>`);
  return `<div class="srvcheck warn">⚠ Nur <b>${c.online}</b> von <b>${c.need}</b> nötigen Servern online${c.offline.length ? ` · ${c.offline.length} aus (${c.offline.map(x => esc(x.name)).join(", ")})` : ""}${c.creating ? ` · ${c.creating} werden gerade angelegt` : ""}.
    Sonst laufen Spiele der ersten Runde nacheinander.
    <div class="row" style="gap:6px;margin-top:6px;flex-wrap:wrap">${parts.join("") || `<span class="hint">warte auf die neuen Server …</span>`}</div></div>`;
}
function bindTourSrvCheck(){
  $$("[data-tstart]").forEach(b => b.onclick = () => tourStartAsk(b.dataset.tstart));
  $$("[data-tsrv]").forEach(b => b.onclick = async () => {
    const a = b.dataset.tsrv, n = +b.dataset.n || 0;
    if ((a === "create" || a === "both") && !confirm(`${n} neue CS2-Server fürs Turnier anlegen? (Spieldateien werden aus der Vorlage kopiert, Ports aus dem freigegebenen Bereich)`)) return;
    if ((a === "create" || a === "both") && !await diskOkForCreate(n)) return;
    b.disabled = true;
    try {
      const r = await api("/api/tournament/servers", {method: "POST", body: {create: a === "start" ? 0 : n, start_offline: a !== "create"}});
      toast([r.started.length ? `${r.started.length} Server gestartet` : "", r.created ? `${r.created} Server werden angelegt` : "", ...r.errors].filter(Boolean).join(" · ") || "Erledigt", !!r.errors.length);
    } catch (e) { toast(e.message, true); }
    loadTour();
  });
}

// --- Turnier: Teams tauschen per Drag & Drop (Spielplan-Karten)
let tDrag = null;
document.addEventListener("dragstart", e => {
  const r = e.target.closest && e.target.closest("[data-sm]");
  if (r){ tDrag = {kind: "team", m: r.dataset.sm, s: r.dataset.ss}; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", "t"); r.classList.add("dragging"); return; }
  const c = e.target.closest && e.target.closest("[data-lm]");
  if (c){ tDrag = {kind: "match", m: c.dataset.lm}; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", "m"); c.classList.add("dragging"); }
});
document.addEventListener("dragend", () => { tDrag = null; $$(".dragging,.dropok").forEach(x => x.classList.remove("dragging", "dropok")); });
document.addEventListener("dragover", e => {
  if (!tDrag) return;
  const t = tDrag.kind === "team" ? e.target.closest("[data-sm]") : (e.target.closest("[data-lm]") || e.target.closest("[data-lane]"));
  if (!t) return;
  e.preventDefault();
  $$(".dropok").forEach(x => x !== t && x.classList.remove("dropok")); t.classList.add("dropok");
});
document.addEventListener("drop", async e => {
  if (!tDrag) return;
  const d = tDrag; tDrag = null;
  if (d.kind === "team"){
    const t = e.target.closest("[data-sm]"); if (!t) return; e.preventDefault();
    if (t.dataset.sm === d.m && t.dataset.ss === d.s) return;
    await tourCall("/api/tournament/swap", {body: {a: d.m, a_slot: d.s, b: t.dataset.sm, b_slot: t.dataset.ss}}, "Teams getauscht");
    return;
  }
  const card = e.target.closest("[data-lm]"), lane = e.target.closest("[data-lane]");
  if (!card && !lane) return; e.preventDefault();
  if (card && card.dataset.lm === d.m) return;
  const server = lane ? lane.dataset.lane : null;
  await tourCall("/api/tournament/move", {body: {mid: d.m, before: card ? card.dataset.lm : "", server: server === "_auto" ? "" : server}}, "Umgeplant");
});

// --- Ablaufplan: Spalten je Server, Spiele nach Zeit
function tourLanesHtml(d){
  const open = d.matches.filter(m => m.status !== "done" && !m.walkover);
  if (!open.length) return `<div class="hint">Keine offenen Spiele.</div>`;
  const lanes = [...d.pool.map(s => ({id: s.id, name: s.name, online: s.online}))];
  open.forEach(m => { if (m.server && !lanes.find(l => l.id === m.server)) lanes.push({id: m.server, name: m.server_name || m.server}); });
  const noSrv = open.filter(m => !m.server);
  const card = m => {
    const mv = m.status === "wait" || m.status === "ready";
    return `<div class="lcard ${m.status}" ${mv ? `draggable="true" data-lm="${m.id}"` : ""} title="${esc(m.label)}">
      <div class="lt">${m.status === "live" ? `<span class="livedot">LIVE</span>` : m.planned ? tTime(m.planned) : "–"} <span class="hint">#${m.no || ""}</span>
        ${m.pin ? `<a href="#" class="pin" data-unpin="${m.id}" title="Feste Zuordnung lösen">📌</a>` : ""}</div>
      <div class="ln">${esc(m.t1 || m.p1 || "?")} <span class="hint">vs</span> ${esc(m.t2 || m.p2 || "?")}</div>
      <div class="hint">${esc((m.label || "").split(" · ").slice(-1)[0])}${m.map ? " · " + esc(m.map) : ""}</div></div>`;
  };
  const col = (id, name, ms, extra) => `<div class="lane" data-lane="${esc(id)}"><div class="lh">${name}${extra || ""}</div>${ms.sort((a, b) => (a.planned || 0) - (b.planned || 0)).map(card).join("") || `<div class="hint" style="padding:8px">hierher ziehen</div>`}</div>`;
  return `<div class="lanes">${lanes.map(l => col(l.id, `${l.online === false ? "⚪" : l.online ? "🟢" : ""} ${esc(l.name)}`, open.filter(m => m.server === l.id))).join("")}
    ${noSrv.length ? col("_auto", "ohne Server", noSrv) : ""}</div>`;
}
document.addEventListener("click", e => {
  const u = e.target.closest && e.target.closest("[data-unpin]");
  if (!u) return; e.preventDefault();
  tourCall("/api/tournament/move", {body: {mid: u.dataset.unpin, server: ""}}, "Server wieder automatisch");
});

// --- Gespeicherte Turniere und Vorlagen
async function loadTourLib(){
  let r; try { r = await api("/api/tournament/library"); } catch { return; }
  const cur = r.current;
  $("#tlSel").innerHTML = r.tournaments.length ? r.tournaments.map(t => `<option value="${esc(t.id)}" ${t.id === cur ? "selected" : ""}>${esc(t.name)}${t.id === cur ? " (aktuell)" : ""} · ${t.teams} Teams${t.matches ? ` · ${t.done}/${t.matches} Spiele` : ""} · ${new Date(t.saved * 1000).toLocaleDateString("de-DE")}</option>`).join("")
    : `<option value="">– noch keine gespeichert –</option>`;
  $("#tlTpl").innerHTML = `<option value="">ohne Vorlage</option>` + r.templates.map(t => `<option value="${esc(t.id)}">Vorlage: ${esc(t.name)}</option>`).join("");
  $("#tlTpls").innerHTML = r.templates.map(t => `<span class="pill">${esc(t.name)} <a href="#" data-tpldel="${esc(t.id)}" title="Vorlage löschen">✕</a></span>`).join(" ") || "keine";
  $$("[data-tpldel]").forEach(a => a.onclick = async e => { e.preventDefault(); if (!confirm("Vorlage löschen?")) return; await api(`/api/tournament/templates/${a.dataset.tpldel}`, {method: "DELETE"}); loadTourLib(); });
}
$("#tlSave").onclick = async () => {
  const name = prompt("Name für das gespeicherte Turnier:", $("#tourName").value || "Turnier"); if (!name) return;
  await tourCall("/api/tournament/library/save", {body: {name}}, "Gespeichert"); tourLoaded = false; loadTourLib();
};
$("#tlLoad").onclick = async () => {
  const id = $("#tlSel").value; if (!id) return;
  if (!confirm("Dieses Turnier laden? Das aktuelle wird vorher automatisch in der Liste gespeichert.")) return;
  await tourCall(`/api/tournament/library/${id}/load`, {method: "POST"}, "Geladen"); tourLoaded = false; loadTourLib();
};
$("#tlDel").onclick = async () => {
  const id = $("#tlSel").value; if (!id) return;
  if (!confirm("Gespeichertes Turnier endgültig löschen? (Das aktuell geöffnete bleibt offen.)")) return;
  try { await api(`/api/tournament/library/${id}`, {method: "DELETE"}); toast("Gelöscht"); } catch (e) { toast(e.message, true); }
  loadTourLib();
};
$("#tlNew").onclick = async () => {
  const name = prompt("Name des neuen Turniers:", "Groh LAN Wingman-Turnier"); if (name === null) return;
  await tourCall("/api/tournament/new", {body: {template: $("#tlTpl").value || null, name: name || null}}, "Neues Turnier angelegt – das vorige ist gespeichert");
  tourLoaded = false; loadTourLib();
};
$("#tlTplSave").onclick = async () => {
  const name = prompt("Name der Vorlage (speichert die aktuellen Einstellungen – vorher „Speichern“ in den Einstellungen klicken):", $("#tourMode").selectedOptions[0].text); if (!name) return;
  try { await api("/api/tournament/templates", {body: {name}}); toast("Vorlage gespeichert"); } catch (e) { toast(e.message, true); }
  loadTourLib();
};
let tourData = null, tourLoaded = false;
const toLocalInput = t => { if (!t) return ""; const d = new Date(t * 1000); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };
async function loadTour(){
  try { tourData = await api("/api/tournament"); } catch (e) { $("#tourBoard").innerHTML = `<div class="hint">${esc(e.message)}</div>`; return; }
  const d = tourData;
  if (!tourLoaded || !$("#view-tour .grid2").contains(document.activeElement)){
    $("#tourActive").checked = !!d.active; $("#tourName").value = d.name || ""; $("#tourMode").value = d.mode || "groups";
    $("#tourStartAt").value = toLocalInput(d.start); $("#tourMatchMin").value = d.match_min || 35; $("#tourPauseMin").value = d.pause_min ?? 10;
    $("#tourMaps").value = (d.settings.maps || []).join(", "); $("#tourReg").checked = !!d.registration;
    $("#tourAuto").checked = d.settings.auto_servers !== false; $("#tourInvite").checked = d.settings.invite !== false;
    $("#tourParQf").checked = d.settings.par_qf !== false; $("#tourParSf").checked = !!d.settings.par_sf;
    tourLoaded = true;
  }
  $("#tourStatus").textContent = "· " + (tStatus[d.status] || d.status) + (d.active ? " · auf der Übersicht sichtbar" : "") + (d.test ? ` · TEST (${d.test === "sim" ? "simuliert" : "Bots"})` : "");
  $("#ttStart").disabled = !!d.test; $("#ttEnd").disabled = !d.test;
  $("#tourMaxSrv").textContent = `(höchstens ${d.max_servers} – Teams / 4)`;
  $("#tourSrvCheck").innerHTML = tourSrvCheckHtml(d.servercheck);
  bindTourSrvCheck();
  $("#tourServers").innerHTML = `Server fürs Turnier: ${d.pool.length ? d.pool.map(s => `${s.online ? "🟢" : "⚪"} ${esc(s.name)}`).join(", ") : "keine (außer CS #1)"}${d.needed ? ` · für die erste Runde gleichzeitig nötig: ${d.needed}` : ""}${d.needed && d.pool.length < d.needed ? (d.settings.auto_servers !== false ? ` – ${d.needed - d.pool.length} werden beim Start angelegt` : ` – zu wenige, Matches laufen nacheinander`) : ""}${d.bot ? "" : " · Steam-Bot ist aus (keine Einladungen)"}`;
  const reg = new Set(d.players.map(p => p.steamid));
  const teamEditing = $("#tourTeams").contains(document.activeElement) || ["tourNewTeam", "tourNewP1", "tourNewP2", "tourAddId", "tourAddName", "tourAddSel", "tourBotN"].includes((document.activeElement || {}).id);
  if (!teamEditing) $("#tourAddSel").innerHTML = `<option value="">– bekannten Spieler hinzufügen –</option>` + d.lan_players.filter(p => !reg.has(p.steamid)).map(p => `<option value="${esc(p.steamid)}">${p.lan ? "🖧 " : ""}${esc(p.name)}</option>`).join("");
  $("#tourPlN").textContent = `(${d.players.length})`;
  const tname = Object.fromEntries(d.teams.map(t => [t.id, t.name]));
  $("#tourPlayers").innerHTML = d.players.length ? d.players.map(p => `<div class="row" style="gap:8px;margin:3px 0;flex-wrap:nowrap">${p.avatar ? `<img class="avatar" src="${esc(p.avatar)}" alt="">` : `<span class="avatar" style="display:inline-block"></span>`}<b style="flex:1">${esc(p.name)}</b><span class="hint">${p.team ? esc(tname[p.team] || "") : "kein Team"}</span><button class="small danger" data-tdelp="${esc(p.steamid)}">✕</button></div>`).join("") : `<div class="hint">Noch niemand angemeldet.</div>`;
  const opts = sel => `<option value="">– Spieler –</option>` + d.players.map(p => `<option value="${esc(p.steamid)}" ${p.steamid === sel ? "selected" : ""}>${esc(p.name)}${p.team && p.steamid !== sel ? " (" + esc(tname[p.team] || "Team") + ")" : ""}</option>`).join("");
  if (!teamEditing){ $("#tourNewP1").innerHTML = opts(""); $("#tourNewP2").innerHTML = opts(""); }
  if (!teamEditing) $("#tourTeams").innerHTML = d.teams.map(t => `<div class="row" style="gap:6px;margin:4px 0;flex-wrap:wrap" data-tteam="${esc(t.id)}">
    <input value="${esc(t.name)}" maxlength="24" style="width:150px" data-tn><select data-tp1>${opts(t.steamids[0])}</select><select data-tp2>${opts(t.steamids[1])}</select>
    <button class="small" data-tsave>Speichern</button><button class="small danger" data-tdel>✕</button>${t.steamids.length < 2 ? ` <span class="pill">solo – Platz frei</span>` : ""}</div>`).join("") || `<div class="hint">Noch keine Teams.</div>`;
  if (tDrag) return;                       // nicht mitten im Ziehen neu zeichnen
  $("#tourBoard").innerHTML = tourBoardHtml(d, true);
  $("#tourLanes").innerHTML = tourLanesHtml(d);
  $("#tourGen").disabled = d.status === "running"; $("#tourStart").disabled = d.status === "running" || !d.matches.length; $("#tourStop").disabled = d.status !== "running";
  // Aktionen
  $$("[data-tdelp]").forEach(b => b.onclick = async () => { await tourCall(`/api/tournament/players/${b.dataset.tdelp}`, {method: "DELETE"}); });
  $$("[data-tteam]").forEach(row => {
    const id = row.dataset.tteam;
    const save = () => tourCall("/api/tournament/teams", {body: {id, name: row.querySelector("[data-tn]").value, players: [row.querySelector("[data-tp1]").value, row.querySelector("[data-tp2]").value].filter(Boolean)}}, "Team gespeichert");
    row.querySelector("[data-tsave]").onclick = save;
    row.querySelectorAll("select").forEach(x => x.onchange = () => { x.blur(); save(); });     // Spieler wählen = gleich speichern
    row.querySelector("[data-tdel]").onclick = () => confirm("Team löschen?") && tourCall(`/api/tournament/teams/${id}`, {method: "DELETE"});
  });
  $$("[data-tres]").forEach(b => b.onclick = () => tourCall(`/api/tournament/match/${b.dataset.tres}/result`, {body: {s1: +$(`[data-ts1="${b.dataset.tres}"]`).value || 0, s2: +$(`[data-ts2="${b.dataset.tres}"]`).value || 0}}));
  $$("[data-tload]").forEach(b => b.onclick = () => tourCall(`/api/tournament/match/${b.dataset.tload}/load`, {method: "POST"}, "Match wird auf dem Server geladen"));
  $$("[data-trst]").forEach(b => b.onclick = () => confirm("Ergebnis zurücksetzen?") && tourCall(`/api/tournament/match/${b.dataset.trst}/reset`, {method: "POST"}));
}
async function tourCall(path, opts, msg){
  try { const r = await api(path, opts); if (msg) toast(msg); loadTour(); return r; } catch (e) { toast(e.message, true); }
}
$("#tourSave").onclick = async () => {
  const st = $("#tourStartAt").value ? new Date($("#tourStartAt").value).getTime() / 1000 : null;
  await tourCall("/api/tournament", {method: "PUT", body: {active: $("#tourActive").checked, name: $("#tourName").value, mode: $("#tourMode").value, start: st,
    match_min: +$("#tourMatchMin").value || 35, pause_min: +$("#tourPauseMin").value || 0, maps: $("#tourMaps").value.split(/[\s,]+/).filter(Boolean),
    registration: $("#tourReg").checked, auto_servers: $("#tourAuto").checked, invite: $("#tourInvite").checked,
    par_qf: $("#tourParQf").checked, par_sf: $("#tourParSf").checked}}, "Gespeichert");
  tourLoaded = false;
};
$("#tourAdd").onclick = () => { if (!$("#tourAddSel").value) return; document.activeElement.blur(); tourCall("/api/tournament/players", {body: {steamid: $("#tourAddSel").value}}); };
$("#tourAddTeam").onclick = async () => {
  const name = $("#tourNewTeam").value.trim();
  if (!name) return toast("Teamname eingeben", true);
  const r = await tourCall("/api/tournament/teams", {body: {name, players: [$("#tourNewP1").value, $("#tourNewP2").value].filter(Boolean)}}, "Team angelegt");
  if (r){ $("#tourNewTeam").value = ""; document.activeElement.blur(); loadTour(); }
};
$("#tourShift").onclick = async () => {
  const cur = tourData && tourData.start ? new Date(tourData.start * 1000) : null;
  const a = prompt(`Turnier verschieben${cur ? ` (Start bisher ${cur.toLocaleString("de-DE", {weekday: "short", hour: "2-digit", minute: "2-digit"})} Uhr)` : ""}:\n\n` +
    "• um Minuten: z. B. 30 (später) oder -15 (früher)\n• oder neue Uhrzeit: z. B. 19:30", "30");
  if (a == null || !a.trim()) return;
  let body;
  const t = a.trim().match(/^(\d{1,2})[:.](\d{2})$/);
  if (t){
    const d = cur ? new Date(cur) : new Date(); d.setHours(+t[1], +t[2], 0, 0);
    if (!cur && d < new Date()) d.setDate(d.getDate() + 1);
    body = {start: d.getTime() / 1000};
  } else if (/^[+-]?\d+$/.test(a.trim())) body = {minutes: parseInt(a.trim(), 10)};
  else return toast("Bitte Minuten (z. B. 30) oder Uhrzeit (z. B. 19:30) eingeben", true);
  const r = await tourCall("/api/tournament/shift", {body});
  if (r){ toast(`Verschoben – neuer Start ${new Date(r.start * 1000).toLocaleString("de-DE", {weekday: "short", hour: "2-digit", minute: "2-digit"})} Uhr`); tourLoaded = false; }
};
$("#tourAddBot").onclick = async () => {
  const n = Math.max(1, Math.min(16, +$("#tourBotN").value || 1));
  const r = await tourCall("/api/tournament/bots", {body: {count: n}}, `${n} Bot${n > 1 ? "s" : ""} hinzugefügt – jetzt einem Team zuordnen`);
};
$("#tourAnnounce").onclick = async e => {
  e.preventDefault();
  if (!confirm("Ankündigung „Gleich geht's los“ jetzt an alle Teilnehmer schicken (Steam-Bot, nur an Freunde des Bots)?")) return;
  const r = await tourCall("/api/tournament/announce", {method: "POST"});
  if (r) toast(`Gesendet an ${r.sent} Spieler${r.skipped ? ` · ${r.skipped} übersprungen (kein Freund des Bots)` : ""}`);
};
$("#tourAddManual").onclick = async () => {
  const id = $("#tourAddId").value.trim(); if (!id) return toast("SteamID64 oder Profil-Link eingeben", true);
  const r = await tourCall("/api/tournament/players", {body: {steamid: id, name: $("#tourAddName").value.trim() || null}}, "Spieler hinzugefügt");
  if (r){ $("#tourAddId").value = ""; $("#tourAddName").value = ""; document.activeElement.blur(); loadTour(); }
};
$("#tourGen").onclick = async () => { if (tourData && tourData.matches.length && !confirm("Spielplan neu erstellen? Bisherige Ergebnisse gehen verloren.")) return; const r = await tourCall("/api/tournament/generate", {method: "POST"}); if (!r) return; toast(`Spielplan erstellt – ${r.needed} Server gleichzeitig nötig, ${r.have} vorhanden`);
  const c = r.servercheck;
  if (c && !c.ok && (c.create || c.offline.length) && (!c.create || await diskOkForCreate(c.create)) && confirm(`Für die erste Runde sind ${c.need} Server nötig, online sind ${c.online}.\n\n${[c.offline.length ? `${c.offline.length} ausgeschaltete starten` : "", c.create ? `${c.create} neue anlegen` : ""].filter(Boolean).join(" und ")}?`)){
    try { const x = await api("/api/tournament/servers", {method: "POST", body: {create: c.create, start_offline: true}}); toast([x.started.length ? `${x.started.length} gestartet` : "", x.created ? `${x.created} werden angelegt` : ""].filter(Boolean).join(" · ") || "Erledigt"); } catch (e) { toast(e.message, true); }
    loadTour();
  } };
$("#tourStart").onclick = () => tourStartAsk();
async function tourStartAsk(force){
  const c = (tourData || {}).servercheck || {};
  let wait = true;
  if (force === "now") wait = false;
  else if (force !== "wait"){
    if (c.need && !c.ok){
      if (confirm(`Es sind erst ${c.online} von ${c.need} nötigen Servern online.\n\nOK = warten, bis alle Server da sind (fehlende werden gestartet/angelegt), dann geht es automatisch los.\nAbbrechen = andere Wahl`)) wait = true;
      else if (confirm(`Jetzt sofort mit den ${c.online} vorhandenen Servern starten? Spiele der ersten Runde laufen dann teils nacheinander.`)) wait = false;
      else return;
    } else if (!confirm("Turnier starten? Die Anmeldung schließt, Matches werden zur geplanten Zeit automatisch auf den Servern geladen.")) return;
  }
  if (wait && c.create && (tourData || {}).settings && tourData.settings.auto_servers !== false && !await diskOkForCreate(c.create)) return;
  const r = await tourCall("/api/tournament/start", {body: {wait}});
  if (r) toast(r.waiting ? `Wartet auf Server (${r.online}/${r.need} online${r.creating ? `, ${r.creating} werden angelegt` : ""}) – startet dann automatisch` : (r.creating ? `Turnier läuft – ${r.creating} Server werden angelegt` : "Turnier läuft"));
}
$("#ttKind").onchange = () => $("#ttSecL").classList.toggle("hidden", $("#ttKind").value !== "sim");
$("#ttStart").onclick = async () => {
  const kind = $("#ttKind").value, n = +$("#ttTeams").value || 8;
  if (!confirm(`Test mit ${n} Bot-Teams starten (${kind === "sim" ? "simuliert" : "Bots auf den Servern"})? Dein Turnier wird gesichert und danach wiederhergestellt.`)) return;
  if (kind === "bots" && !await diskOkForCreate(Math.ceil(n / 4))) return;
  await saveTourSettingsSilently();
  const r = await tourCall("/api/tournament/test", {body: {teams: n, kind, match_sec: +$("#ttSec").value || 60, mode: $("#tourMode").value}});
  if (r) toast(r.waiting ? `Test wartet auf Server: ${r.servers} da, ${r.need} nötig${r.creating ? `, ${r.creating} werden angelegt` : ""} – startet dann automatisch`
                         : `Test läuft: ${r.matches} Matches auf ${r.servers} ${kind === "sim" ? "Testservern" : "Servern"}`);
};
$("#ttEnd").onclick = () => confirm("Test beenden und echtes Turnier wiederherstellen?") && tourCall("/api/tournament/test/end", {method: "POST"}, "Test beendet").then(() => { tourLoaded = false; });
async function saveTourSettingsSilently(){
  try { await api("/api/tournament", {method: "PUT", body: {mode: $("#tourMode").value}}); } catch {}
}
$("#tourStop").onclick = () => tourCall("/api/tournament/stop", {method: "POST"}, "Angehalten");
$("#tourReset").onclick = () => confirm("Spielplan und Ergebnisse löschen? Teilnehmer und Teams bleiben.") && tourCall("/api/tournament/reset", {method: "POST"}, "Spielplan gelöscht");
setInterval(() => { if (view === "tour" && !document.hidden) loadTour(); }, 5000);

// Übersicht (Verwaltung): Turnier oben, wenn der Turniermodus an ist
let dashTourAt = 0;
async function refreshDashTour(){
  if (Date.now() - dashTourAt < 8000) return;
  dashTourAt = Date.now();
  let v; try { v = await api("/api/public/tournament/state"); } catch { return; }
  const el = $("#dashTour"); if (!el) return;
  if (!v.active && v.status !== "running" && v.status !== "waiting"){ el.innerHTML = ""; return; }
  // nur eine Statuszeile – Baum und Ergebnisse stehen unter „🏆 Turnier“ und auf der öffentlichen Seite
  const ms = (v.matches || []).filter(m => !m.walkover), done = ms.filter(m => m.status === "done").length, live = ms.filter(m => m.status === "live");
  const next = ms.filter(m => m.status === "ready" || (m.status === "wait" && m.planned)).sort((a, b) => (a.planned || 0) - (b.planned || 0))[0];
  const parts = [`<b>${tStatus[v.status] || v.status}</b>`];
  if (ms.length) parts.push(`${done}/${ms.length} Spiele`);
  if (live.length) parts.push(`<span class="livedot">LIVE</span> ${live.map(m => `${esc(m.t1 || "?")} ${m.s1 ?? 0}:${m.s2 ?? 0} ${esc(m.t2 || "?")}`).join(" · ")}`);
  if (next) parts.push(`nächstes: ${esc(next.t1 || next.p1 || "?")} vs ${esc(next.t2 || next.p2 || "?")}${next.planned ? " um " + tTime(next.planned) : ""}`);
  if (v.status === "setup" && v.start) parts.push("Start " + new Date(v.start * 1000).toLocaleString("de-DE", {weekday: "short", hour: "2-digit", minute: "2-digit"}));
  if (v.test) parts.push("TEST");
  el.innerHTML = `<div class="tourline">🏆 <b>${esc(v.name)}</b> <span class="hint">${esc(v.mode_label || "")}</span> · ${parts.join(" · ")}
    <a href="#" style="margin-left:auto" onclick="showView('tour');return false">verwalten →</a></div>`;
}

// Öffentliche Seite: Anmeldung, Teams bilden, Spielplan und Ergebnisse
let pubTourData = null;
async function refreshPubTour(){
  try { pubTourData = await (await fetch("/api/public/tournament/state", {cache: "no-store"})).json(); } catch { return; }
  const v = pubTourData;
  try { if (v && v.active) v.stream = await (await fetch("/api/public/stream/state", {cache: "no-store"})).json(); } catch {}
  if (!v || !v.active){ $("#pubTour").innerHTML = ""; return; }
  if ($("#pubTour").contains(document.activeElement) && document.activeElement.tagName === "INPUT") return;   // nicht beim Tippen neu zeichnen
  const me = v.me, myTeam = me && me.team;
  let reg = "";
  if (v.status === "setup" && v.registration){
    reg = `<div class="panel" style="margin-bottom:10px">${me ? `<div class="row" style="gap:8px;align-items:center;flex-wrap:wrap">${me.avatar ? `<img class="avatar" src="${esc(me.avatar)}" alt="">` : ""}<b>${esc(me.name)}</b><span class="hint">${me.via === "steam" ? "per Steam angemeldet" : "erkannt über deinen PC"} · <a href="/api/public/steam/login">nicht du?</a></span>
        ${me.registered ? `<span class="pill ok">angemeldet</span><button class="small" data-pt="unregister">abmelden</button>` : `<button class="primary small" data-pt="register">Zum Turnier anmelden</button>`}</div>
        ${me.registered && !myTeam ? `<div class="row" style="gap:6px;margin-top:8px;flex-wrap:wrap"><input id="ptTeam" placeholder="Teamname" maxlength="24" style="width:180px"><button class="small" data-pt="team">Team gründen</button>
          <span class="hint">oder unten einem Team mit freiem Platz beitreten</span></div>` : ""}
        ${myTeam ? `<div class="hint" style="margin-top:6px">Dein Team: <b>${esc((v.teams.find(t => t.id === myTeam) || {}).name || "")}</b> · <a href="#" data-pt="leave">Team verlassen</a></div>` : ""}`
      : `<div class="row" style="gap:10px;align-items:center;flex-wrap:wrap"><span>Mitspielen? Melde dich mit Steam an, damit wir dich erkennen:</span><a class="btn primary" href="/api/public/steam/login">Mit Steam anmelden</a></div>`}</div>`;
  }
  const teams = v.teams.length ? `<div class="tnext">${v.teams.map(t => `<div class="tm"><div class="tr"><b>${esc(t.name)}</b><span>${t.players.length}/2</span></div><div class="meta">${t.players.map(esc).join(" & ") || "–"}</div>
      ${v.status === "setup" && me && me.registered && !myTeam && t.players.length < 2 ? `<button class="small primary" style="margin-top:5px" data-ptjoin="${esc(t.id)}">Beitreten</button>` : ""}</div>`).join("")}</div>` : "";
  $("#pubTour").innerHTML = `<div class="tourpub"><h3 class="pdsec">🏆 ${esc(v.name)} <span class="hint">${esc(v.mode_label)} · ${tStatus[v.status] || v.status}${v.start ? " · Start " + new Date(v.start * 1000).toLocaleString("de-DE", {weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}) + " Uhr" : ""}</span></h3>
    ${reg}${v.status === "setup" ? `<div class="hint" style="margin-bottom:6px">Teams (${v.teams.length}) · ${v.players.length} Spieler angemeldet</div>${teams}` : ""}
    ${v.matches.length ? tourBoardHtml(v) : ""}</div>`;
  glStreamAttach(v.stream);
  const call = async (path, body) => { try { const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})}); if (!r.ok) throw new Error((await r.json()).detail || r.status); refreshPubTour(); } catch (e) { toast(e.message, true); } };
  $$("[data-pt]").forEach(b => b.onclick = e => { e.preventDefault(); const a = b.dataset.pt;
    if (a === "team") return call("/api/public/tournament/team", {name: $("#ptTeam").value.trim()});
    if (a === "leave") return call("/api/public/tournament/team/leave");
    call(`/api/public/tournament/${a}`); });
  $$("[data-ptjoin]").forEach(b => b.onclick = () => call(`/api/public/tournament/team/${b.dataset.ptjoin}/join`));
}

// --- Live-Stream: Verwaltung
let stLoaded = false;
async function loadStream(){
  let r; try { r = await api("/api/stream"); } catch { return; }
  const st = r.settings;
  if (!stLoaded || !$("#streamPanel").contains(document.activeElement)){
    $("#stOn").checked = !!st.enabled; $("#stTitle").value = st.title || "";
    $("#stServer").innerHTML = `<option value="">automatisch: laufendes Turnierspiel</option>` + r.servers.map(x => `<option value="${esc(x.id)}">${esc(x.name || x.id)}</option>`).join("");
    $("#stServer").value = st.server || "";
    stLoaded = true;
  }
  const c = r.container;
  $("#stStatus").textContent = !st.enabled ? "· aus" : !c || !c.running ? "· Stream-Server startet …" : r.on_air ? "· 🔴 sendet" : "· bereit, wartet auf OBS";
  const t = r.target;
  $("#stInfo").innerHTML = `${st.enabled ? "" : `<div style="margin-bottom:6px">Stream-Server ist aus – Haken oben setzen, damit er Bilder annimmt. Die exe kannst du schon vorher auf dem Stream-PC einrichten.</div>`}<div class="row" style="gap:6px;flex-wrap:wrap;align-items:center">OBS-Server <code>${esc(r.obs.server)}</code> <button class="small" data-copy="${esc(r.obs.server)}">kopieren</button>
      · Streamschlüssel <code>${esc(r.obs.key.replace(/pass=.*/, "pass=••••"))}</code> <button class="small" data-copy="${esc(r.obs.key)}">kopieren</button>
      <button class="small" id="stNewKey" title="Neuen Schlüssel erzeugen (OBS muss angepasst werden)">neuer Schlüssel</button>
      <a class="btn small primary" href="/api/stream/helper.exe" title="Auf dem Stream-PC ausführen: richtet OBS ein, startet CS2 und den Stream, Kamera folgt dem laufenden Spiel">⬇ GrohLAN-Stream.exe</a> <a class="hint" href="/api/stream/helper.cmd">(nur Kamera-Helfer .cmd)</a></div>
      <div style="margin-top:6px">OBS-Overlays (Browserquelle 1920×1080, richtet die exe automatisch ein): <a href="/overlay/game" target="_blank">Spielstand + „Gleich Live“</a> ·
        <a href="/overlay/start" target="_blank">Gleich Live</a> · <a href="/overlay/bracket" target="_blank">Turnierbaum</a></div>
      <div style="margin-top:6px">Kamera geht gerade zu: ${t.tv ? `<b>${esc(t.match || "")}</b> <code>${esc(t.tv)}</code>` : "– kein laufendes Spiel (oder CSTV aus)"}</div>`;
  $$("#stInfo [data-copy]").forEach(b => b.onclick = () => copyQuiet(b.dataset.copy));
  const nk = $("#stNewKey"); if (nk) nk.onclick = () => confirm("Neuen Streamschlüssel erzeugen? OBS muss danach angepasst werden.") && saveStream({new_key: true});
}
async function saveStream(extra){
  try { await api("/api/stream", {method: "PUT", body: {enabled: $("#stOn").checked, title: $("#stTitle").value.trim(), server: $("#stServer").value, ...(extra || {})}}); toast("Gespeichert"); }
  catch (e) { toast(e.message, true); }
  stLoaded = false; loadStream();
}
$("#stOn").onchange = () => saveStream();
$("#stTitle").onchange = () => saveStream();
$("#stServer").onchange = () => saveStream();
setInterval(() => { if (view === "tour" && !document.hidden) loadStream(); }, 10000);

// --- Live-Stream: öffentliche Seite (HLS über das Tool)
let pubHls = null, pubStreamOn = false;
async function refreshPubStream(){
  let r; try { r = await (await fetch("/api/public/stream/state", {cache: "no-store"})).json(); } catch { return; }
  const box = $("#pubStream"); if (!box) return;
  if (pubTourData && pubTourData.active && pubTourData.matches && pubTourData.matches.length) r.on_air = false;   // Stream steht dann im Turnierbaum über dem Pokal
  if (!r.enabled || !r.on_air){
    if (pubStreamOn){ if (pubHls){ pubHls.destroy(); pubHls = null; } box.innerHTML = ""; pubStreamOn = false; }
    return;
  }
  const cap = `<span class="livedot">LIVE</span> ${esc(r.title || "Live-Stream")}${r.match ? ` · <b>${esc(r.match)}</b>` : ""}`;
  if (pubStreamOn){ const c = $("#pubStreamCap"); if (c) c.innerHTML = cap; return; }
  pubStreamOn = true;
  box.innerHTML = `<div class="streambox"><div class="streamcap" id="pubStreamCap">${cap}</div><video id="pubVideo" controls autoplay muted playsinline></video>
    <div class="hint" style="margin-top:4px">Ton ist aus – zum Einschalten auf das Video tippen. ${r.tv ? `Lieber im Spiel zuschauen? <a href="steam://run/730//+connect%20${esc(r.tv)}">In CS2 öffnen</a>` : ""}</div></div>`;
  const v = $("#pubVideo");
  const start = () => {
    if (!(window.Hls && Hls.isSupported()) && v.canPlayType("application/vnd.apple.mpegurl")) { v.src = r.hls; return; }
    if (!window.Hls || !Hls.isSupported()) { box.querySelector(".hint").textContent = "Dein Browser kann den Stream nicht abspielen."; return; }
    pubHls = new Hls({liveSyncDurationCount: 2, lowLatencyMode: false});
    pubHls.loadSource(r.hls); pubHls.attachMedia(v);
    pubHls.on(Hls.Events.ERROR, (e, d) => { if (d.fatal){ pubHls.destroy(); pubHls = null; pubStreamOn = false; } });
  };
  if (window.Hls) start();
  else { const sc = document.createElement("script"); sc.src = "/static/hls.min.js"; sc.onload = start; sc.onerror = start; document.head.appendChild(sc); }
}
setInterval(() => { if (!$("#pub").classList.contains("hidden") && !document.hidden) refreshPubStream(); }, 10000);

// --- Homepage-API: Schlüssel und Optionen
const SCOPE_L = {tournament: "Turnier", stream: "Stream", bot: "Steam-Bot"};
async function loadApi(){
  let r; try { r = await api("/api/apikeys"); } catch (e) { return toast(e.message, true); }
  $("#apiKeys").innerHTML = r.keys.length ? `<table class="tbl"><thead><tr><th>Name</th><th>Schlüssel</th><th>Rechte</th><th>Angelegt</th><th>Zuletzt benutzt</th><th></th></tr></thead><tbody>${r.keys.map(k => `<tr>
      <td><b>${esc(k.name)}</b></td><td class="mono">${esc(k.hint || "")}</td><td>${k.scopes.map(x => SCOPE_L[x] || x).join(", ")}</td>
      <td>${new Date(k.created * 1000).toLocaleDateString("de-DE")}</td><td>${k.last_used ? new Date(k.last_used * 1000).toLocaleString("de-DE") + ` (${k.uses || 0}×)` : "–"}</td>
      <td><button class="small danger" data-apidel="${esc(k.id)}">Löschen</button></td></tr>`).join("")}</tbody></table>` : `<div class="hint">Noch keine Schlüssel.</div>`;
  $$("[data-apidel]").forEach(b => b.onclick = async () => { if (!confirm("Schlüssel löschen? Die Homepage verliert damit den Zugriff.")) return;
    await api(`/api/apikeys/${b.dataset.apidel}`, {method: "DELETE"}); loadApi(); });
  $("#apiPublic").checked = !!r.public_read;
  if (document.activeElement !== $("#apiOrigins")) $("#apiOrigins").value = (r.origins || []).join("\n");
  $("#apiEmbed").innerHTML = `Turnierbaum (GrohLAN-Look, aktualisiert sich selbst): <code>&lt;iframe src="${esc(r.base)}/embed/tournament" style="width:100%;height:900px;border:0"&gt;&lt;/iframe&gt;</code><br>
    Live-Stream: <code>&lt;iframe src="${esc(r.base)}/embed/stream" style="width:100%;aspect-ratio:16/9;border:0" allowfullscreen&gt;&lt;/iframe&gt;</code><br>
    Hinweis: Eine https-Homepage kann nur https-Seiten einbetten – dafür das Tool über einen https-Proxy (z. B. <code>live.groh-lan.de</code>) erreichbar machen.`;
}
$("#apiCreate").onclick = async () => {
  const name = $("#apiName").value.trim() || "Homepage", scopes = $$(".apiScope").filter(x => x.checked).map(x => x.value);
  try {
    const r = await api("/api/apikeys", {body: {name, scopes}});
    $("#apiNew").innerHTML = `<div class="srvcheck ok" style="margin-top:10px">Neuer Schlüssel (nur jetzt sichtbar – an den Homepage-Verwalter geben):<br><code style="user-select:all;word-break:break-all">${esc(r.key)}</code> <button class="small" id="apiCopy">kopieren</button></div>`;
    $("#apiCopy").onclick = () => copyQuiet(r.key, "Schlüssel kopiert");
    loadApi();
  } catch (e) { toast(e.message, true); }
};
$("#apiOptSave").onclick = async () => {
  try { await api("/api/apikeys/options", {method: "PUT", body: {public_read: $("#apiPublic").checked, origins: $("#apiOrigins").value.split(/\s+/).filter(Boolean)}}); toast("Gespeichert"); loadApi(); }
  catch (e) { toast(e.message, true); }
};

// Zuschauen (CSTV): Steam-Link öffnen und zusätzlich den Konsolenbefehl anzeigen (falls CS2 schon läuft oder der Link nicht greift)
document.addEventListener("click", e => {
  const a = e.target.closest && e.target.closest("a.tvbtn");
  if (!a) return;
  const m = decodeURIComponent(a.getAttribute("href") || "").match(/connect\s+([\w.\-]+:\d+)/);
  if (!m) return;
  const addr = m[1];
  let box = document.getElementById("tvHelp");
  if (!box){ box = document.createElement("div"); box.id = "tvHelp"; document.body.appendChild(box); }
  box.innerHTML = `<div class="tvhelp"><b>👁 Zuschauen per CSTV</b><div>CS2 startet und verbindet sich. Läuft CS2 schon oder klappt es nicht:<br>Konsole öffnen (^) und eingeben:</div>
    <div class="row" style="gap:6px;align-items:center;margin-top:6px"><code style="user-select:all">connect ${esc(addr)}</code><button class="small" id="tvHelpCopy">kopieren</button><button class="small" id="tvHelpX">✕</button></div></div>`;
  document.getElementById("tvHelpCopy").onclick = () => copyQuiet("connect " + addr, "Befehl kopiert");
  document.getElementById("tvHelpX").onclick = () => box.remove();
  setTimeout(() => box.isConnected && box.remove(), 30000);
});

// Deathmatch-Bestenliste (CS #1) auf der öffentlichen Seite
let pubDmAt = 0, pubDmTab = "day";
async function refreshPubDm(){
  if (Date.now() - pubDmAt < 15000) return;
  pubDmAt = Date.now();
  let r; try { r = await (await fetch("/api/public/dm/board", {cache: "no-store"})).json(); } catch { return; }
  const box = $("#pubDm"); if (!box) return;
  const tab = pubDmTab, L = tab === "day" ? r.day : r.total;
  box.innerHTML = `<div class="tourpub"><div class="gl"><div class="glsec"><h3>💀 Deathmatch-Bestenliste <span style="font-size:15px;color:var(--gmut)">CS #1</span>
      <span class="glseg"><a href="#" data-dmtab="day" class="${tab === "day" ? "on" : ""}">Heute</a><a href="#" data-dmtab="total" class="${tab === "total" ? "on" : ""}">Gesamt</a></span></h3>
    ${L.length ? glLeaders(L, 15, true) : `<div style="color:var(--gmut);padding:6px 2px">${tab === "day" ? "Heute noch keine Kills auf CS #1 – rauf auf den Deathmatch-Server!" : "Noch keine Kills erfasst."} (ab 5 Kills/Tode erscheint man in der Liste)</div>`}</div></div></div>`;
  $$("[data-dmtab]").forEach(a => a.onclick = e => { e.preventDefault(); pubDmTab = a.dataset.dmtab; pubDmAt = 0; refreshPubDm(); });
}

// Hall of Fame (aufklappbar) auf der öffentlichen Seite
let pubHofAt = 0, hofOpen = false;
function hofHtml(r){
  const T = r.tournaments || [], P = r.players || [];
  const fmtD = t => new Date(t * 1000).toLocaleDateString("de-DE", {day: "2-digit", month: "2-digit", year: "numeric"});
  const pl = t => (t && t.players || []).map(p => esc(p.name)).join(" & ");
  const cards = T.map(e => `<div class="hofcard">
      <div class="hofd">${fmtD(e.date)} · ${esc(e.mode || "")} · ${e.teams} Teams</div>
      <div class="hofn bb">${esc(e.name)}</div>
      <div class="hofw">🏆 <b>${esc((e.winner || {}).name || "?")}</b><span>${pl(e.winner)}</span></div>
      ${e.second ? `<div class="hofs">🥈 ${esc(e.second.name)} <span>${pl(e.second)}</span></div>` : ""}
      ${e.final ? `<div class="hoff">Finale ${esc(e.final.t1)} ${e.final.s1 ?? "–"}:${e.final.s2 ?? "–"} ${esc(e.final.t2)}${e.final.map ? " · " + esc(e.final.map) : ""}</div>` : ""}
      ${e.mvp ? `<div class="hofm">⭐ MVP <b>${esc(e.mvp.name)}</b> · Rating ${(e.mvp.rating ?? 0).toFixed(2)} · K/D ${(e.mvp.kd ?? 0).toFixed(2)}</div>` : ""}</div>`).join("");
  const tab = P.length ? `<table class="glleaders"><thead><tr><th>#</th><th>Spieler</th><th title="Turniersiege">🏆</th><th title="Finalteilnahmen">Finals</th><th title="MVP-Auszeichnungen">⭐</th><th>Turniere</th><th title="Ø-Rating über alle Turniere">Rating</th><th>K/D</th><th>Siege</th></tr></thead><tbody>
    ${P.map((p, i) => `<tr class="${i < 3 ? "top" : ""}"><td class="rk">${i + 1}</td><td><b>${esc(p.name)}</b></td><td class="kd">${p.titles}</td><td>${p.finals}</td><td>${p.mvps}</td><td>${p.tournaments}</td><td>${p.rating != null ? p.rating.toFixed(2) : "–"}</td><td>${(p.kd ?? 0).toFixed(2)}</td><td>${p.wins}/${p.matches}</td></tr>`).join("")}</tbody></table>` : "";
  return {cards, tab, n: T.length};
}
async function refreshPubHof(){
  if (Date.now() - pubHofAt < 60000) return;
  pubHofAt = Date.now();
  let r; try { r = await (await fetch("/api/public/hof/board", {cache: "no-store"})).json(); } catch { return; }
  const box = $("#pubHof"); if (!box) return;
  const h = hofHtml(r);
  if (!h.n){ box.innerHTML = ""; return; }
  box.innerHTML = `<div class="tourpub"><div class="gl"><details class="hof" ${hofOpen ? "open" : ""}><summary><h3>🏛 Hall of Fame <span style="font-size:15px;color:var(--gmut)">${h.n} Turnier${h.n === 1 ? "" : "e"}</span><span class="hoftg">aufklappen ▾</span></h3></summary>
    <div class="hofcards">${h.cards}</div>${h.tab ? `<div class="glsec" style="margin-top:16px"><h3>Ewige Wertung</h3>${h.tab}</div>` : ""}</details></div></div>`;
  box.querySelector("details").addEventListener("toggle", e => { hofOpen = e.target.open; });
}
// Verwaltung: Hall-of-Fame-Einträge
async function loadTourHof(){
  let r; try { r = await (await fetch("/api/public/hof/board", {cache: "no-store"})).json(); } catch { return; }
  $("#tourHof").innerHTML = (r.tournaments || []).length ? (r.tournaments || []).map(e => `<div class="row" style="gap:8px;align-items:center;margin:3px 0">
      <span>${new Date(e.date * 1000).toLocaleDateString("de-DE")}</span><b>${esc(e.name)}</b><span>🏆 ${esc((e.winner || {}).name || "?")}</span>${e.mvp ? `<span>⭐ ${esc(e.mvp.name)}</span>` : ""}
      <button class="small danger" data-hofdel="${esc(e.id)}" style="margin-left:auto">✕</button></div>`).join("") : "Noch keine Einträge.";
  $$("[data-hofdel]").forEach(b => b.onclick = async () => { if (!confirm("Eintrag aus der Hall of Fame löschen?")) return;
    try { await api(`/api/tournament/hof/${b.dataset.hofdel}`, {method: "DELETE"}); loadTourHof(); } catch (e) { toast(e.message, true); } });
}
$("#tourHofAdd").onclick = async () => {
  if (!confirm("Aktuelles Turnier mit dem jetzigen Stand in die Hall of Fame eintragen?")) return;
  try { const r = await api("/api/tournament/hof", {method: "POST"}); toast(`Eingetragen – Sieger: ${(r.entry.winner || {}).name}`); loadTourHof(); } catch (e) { toast(e.message, true); }
};
