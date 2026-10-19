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
const GT_MAPS = {tf2: "tf2", garrysmod: "garrysmod", l4d2: "left4dead2", quakelive: "ql", insurgency: "ins"};
const MAP_GAMES = new Set(["cs2", "wreckfest", "killingfloor2", ...Object.keys(GT_MAPS)]);
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
let pubLoggedIn = false;
function showPublic(loggedIn = false){
  stopPoll(); clearInterval(dashTimer);
  pubLoggedIn = loggedIn === true;
  if (!pubLoggedIn) me = null;
  $("#btnPubLogin").textContent = pubLoggedIn ? "← Zur Verwaltung" : "Anmelden";
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
  const on = r.servers.filter(x => x.online), pl = on.reduce((a, x) => a + (x.players || 0), 0);
  $("#pubStat").innerHTML = `<b>${on.length}</b> von ${r.servers.length} Servern online · <b>${pl}</b> Spieler · ` +
    (r.net === "internet" ? `<span class="pill" title="Du kommst aus dem Internet – Adressen zeigen die öffentliche IP">🌐 Internet${r.address ? " · " + esc(r.address) : ""}</span>`
                          : `<span class="pill ok" title="Du bist im LAN – Adressen zeigen die LAN-IP">LAN</span>`) + pubNetHtml(r.internet) + pubCacheHtml(r.cache);
  $("#pubCache").innerHTML = cacheGamesHtml(r.cached_games);
  if (!r.servers.length){ $("#pubGrid").innerHTML = `<div class="hint">Noch keine Server eingerichtet.</div>`; return; }
  $("#pubGrid").innerHTML = r.servers.map((x, i) => {
    const g = GAMES[x.game] || r.games[x.game] || {label: x.game, color: "#888"};
    const j = x.join || {};
    const meta = [x.mode ? esc(x.mode) : "", x.version ? "v" + esc(x.version) : ""].filter(Boolean).join(" · ");
    const thumb = mapThumb({map: MAP_GAMES.has(x.game) && x.online ? x.map : "", workshop: x.workshop, map_image: x.map_image, map_title: x.map_label, map_layout: x.online ? x.map_layout : null}, x.game);
    return `<div class="pubcard${x.online || x.sleeping || x.install ? "" : " off"}" style="--gc:${g.color}" ${x.pending ? `title="wird gerade angelegt"` : `data-pub="${esc(x.id)}" tabindex="0" title="Details: Spieler, Rotation"`}>
      ${thumb ? `<div class="pubthumb">${thumb}<span class="pubmap">${MAP_GAMES.has(x.game) && x.online ? esc(x.map_label || x.map || "") : ""}</span></div>` : ""}
      <div class="pubtop">${gameTile(x.game, 18)}<div class="pubname"><b title="${esc(x.name)}">${esc(x.name)}</b><span class="hint">${esc(g.label)} ${x.online ? reachPill(x.reach) : ""}</span></div>
        <span class="pill ${x.online ? "ok" : ""}">${x.online ? `● ${x.players ?? 0}${x.max_players ? "/" + x.max_players : ""} Spieler` : x.sleeping ? "💤 schläft" : x.install ? "⬇ wird installiert" : "offline"}</span></div>
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
  }).join("");
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
        <span>Spieler</span><span>${x.online ? `${x.players ?? 0}${x.max_players ? " / " + x.max_players : ""}` : "–"}</span>
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
$("#btnPubLogin").onclick = () => pubLoggedIn ? start() : showLogin();
$("#btnPubView").onclick = () => showPublic(true);
$("#btnBackPub").onclick = () => showPublic();
$("#loginForm").addEventListener("submit", async e => {
  e.preventDefault(); $("#loginErr").textContent = "";
  try { await api("/api/login", {body:{username: $("#loginUser").value.trim() || "admin", password: $("#loginPw").value}}); $("#loginPw").value = ""; start(); }
  catch(err){ $("#loginErr").textContent = err.message; }
});
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
        const cnt = st.online ? `${st.humans ?? 0}${lim ? "/" + lim : ""}` : "";
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
    (h.cs2_template ? `<br><span title="Lokale Kopie von ${esc(h.cs2_template.src_name || "CS #1")} – neue CS-Server kopieren von hier">CS-Vorlage: ${h.cs2_template.busy ? "wird aktualisiert" + (h.cs2_template.progress != null ? " " + h.cs2_template.progress + " %" : " …") : h.cs2_template.last ? fmtBytes(h.cs2_template.bytes || 0) + " · Stand " + new Date(h.cs2_template.last * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}) : "noch keine"}${h.cs2_template.error ? " · ⚠ " + esc(h.cs2_template.error.slice(0, 60)) : ""}</span>` : "");
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
function peakMark(barId, pct){
  const bar = document.getElementById(barId); if (!bar) return;
  const now = Date.now(), h = (PEAK[barId] = (PEAK[barId] || []).filter(x => now - x[0] < 300000));
  h.push([now, pct || 0]);
  const pk = Math.max(...h.map(x => x[1]));
  const box = bar.parentNode;
  let m = box.querySelector(".pk");
  if (!m){ m = document.createElement("span"); m.className = "pk"; box.appendChild(m); }
  m.style.left = `calc(${Math.min(100, pk)}% - 1px)`;
  box.title = `Spitze der letzten 5 Minuten: ${Math.round(pk)} %` + (barId.includes("Net") ? " der Leitung (1 Gbit/s)" : "");
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
    const n = L.net || {}, bw = v => v > 0 ? Math.max(2, Math.min(100, v / LINK_BPS * 100)) : 0;
    if (n.rx_bps != null){
      $("#hlNetDownBar").style.width = bw(n.rx_bps) + "%"; $("#hlNetUpBar").style.width = bw(n.tx_bps) + "%";
      peakMark("hlNetDownBar", bw(n.rx_bps)); peakMark("hlNetUpBar", bw(n.tx_bps));
      tween($("#hlNetDown"), n.rx_bps, v => fmtRate(v)); tween($("#hlNetUp"), n.tx_bps, v => fmtRate(v));
      const tt = `Internet-Durchsatz (geschätzt): ↓ was Lancache und Spielserver empfangen, ↑ was die Spielserver senden – ohne LAN-Verkehr (Cache → Clients, NAS)` + (n.nic_rx_bps != null ? `\nNetzwerkkarte gesamt inkl. LAN: ↓ ${fmtRate(n.nic_rx_bps)} · ↑ ${fmtRate(n.nic_tx_bps)}` : "");
      $("#hlNetTotRow").title = tt; $("#hlNetTotRow").nextElementSibling.title = tt;
    }
    latencyRow(L.io);
    if (L.cache && L.cache.tx_bps != null && !$("#hlNetRow").classList.contains("hidden")){
      $("#hlNetBar").style.width = bw(L.cache.tx_bps) + "%"; peakMark("hlNetBar", bw(L.cache.tx_bps)); tween($("#hlNet"), L.cache.tx_bps, v => fmtRate(v));
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
const fmtBytes = b => b == null ? "–" : b >= 1e12 ? (b/1e12).toFixed(2) + " TB" : b >= 1e9 ? (b/1e9).toFixed(1) + " GB" : b >= 1e6 ? (b/1e6).toFixed(0) + " MB" : Math.round(b/1e3) + " KB";
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
  return `<div class="card" title="${measured ? "Gemessen " + new Date(st.measured * 1000).toLocaleString("de-DE") : "Geschätzt aus den Logs (alles, was in den Cache geladen wurde) – ohne Festplattenzugriff"}">
    <div class="k">Cache-Ordner${lim ? " (Limit " + esc(st.limit_raw || fmtBytes(lim)) + ")" : ""}</div><div class="v">${val != null ? (measured ? "" : "≈ ") + fmtBytes(val) : "–"}</div>
    ${pct != null ? `<div class="bar" style="margin-top:6px"><i class="${lvl(pct)}" style="width:${pct}%"></i></div>` : ""}
    <div class="s">${pct != null ? pct + " % vom Limit · " : ""}Logs ${fmtBytes(logs)} · ${st.busy ? "wird gemessen …" : `<a href="#" onclick="measureCache();return false" title="Zählt den Ordner einmal genau – mit niedrigster I/O-Priorität, dauert bei vielen TB lange">genau messen</a>`}</div></div>`;
}
async function measureCache(){
  try { await api("/api/cache/measure", {method: "POST"}); toast("Messung läuft im Hintergrund (niedrige Priorität)"); } catch (e) { toast(e.message, true); }
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
        <td>${cp != null ? `<div class="cachebar" title="${fmtBytes(g.stored)} von ${fmtBytes(g.size)} (Download-Größe laut Steam)"><i style="width:${cp}%;background:var(--ct)"></i></div>
          <div class="hint mono">${cp.toFixed(0)} % · ${fmtBytes(g.stored)} / ${fmtBytes(g.size)}</div>` : g.app ? `<span class="hint">Größe wird ermittelt …</span>` : `<span class="hint">–</span>`}</td></tr>`; }).join("")}
    </tbody></table></div>
    <div class="hint" style="margin-top:6px">„Im Cache“ = alles, was für das Spiel je aus dem Internet in den Cache geladen wurde, im Verhältnis zur Download-Größe (Windows, Englisch) – Schätzung, abgelaufene Cache-Einträge sind nicht abgezogen.</div></div>`;
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
  if (view === "dash") $("#hostPanel").innerHTML = hostPanelHtml();
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
        <span>Spieler</span><span>${o.humans ?? 0} / ${slots || "?"}${o.bots ? ` (+${o.bots} Bots)` : ""}</span>
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
const VIEWS = ["dash","players","auto","server","scan","create","users","cache","prefill","storage","game"];
function applyGameClasses(s){
  const g = gameOf(s), meta = GAMES[g] || {};
  document.body.classList.toggle("g-other", g !== "cs2");
  document.body.classList.toggle("g-wreckfest", g === "wreckfest");
  document.body.classList.toggle("g-tf2", g === "tf2");
  wfLoadedFor = null;
  document.body.classList.toggle("no-console", !meta.console);
  document.body.classList.toggle("no-container", !(dockerOn && s.container));
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
  if ((g !== "cs2" && ["maps","match","settings"].includes(tab)) || (tab === "container" && !(dockerOn && s.container))) tab = "overview";
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
  if (t === "maps") renderFavs();
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
    $("#stPlayers").textContent = `${st.humans ?? st.players.length} / ${slots ?? "?"}` + (st.bots ? ` +${st.bots}` : "");
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

/* ---------- Workshop ---------- */
let wsPage = 1, wsLast = "";
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
  root.querySelectorAll("[data-wsload]").forEach(b => b.onclick = () => changeMap({workshop_id: b.dataset.wsload, mode: $("#modeSelect").value}));
  root.querySelectorAll("[data-wsfav]").forEach(b => b.onclick = () => addFav(b.dataset.wsfav));
  root.querySelectorAll("[data-wsopen]").forEach(b => b.onclick = () => window.open(`https://steamcommunity.com/sharedfiles/filedetails/?id=${b.dataset.wsopen}`, "_blank", "noopener"));
  root.querySelectorAll("[data-wsunfav]").forEach(b => b.onclick = async () => { favs = await api(`/api/workshop/favorites/${b.dataset.wsunfav}`, {method:"DELETE"}); renderFavs(true); });
}
async function renderFavs(skipLoad){
  if (!skipLoad){ try { favs = await api("/api/workshop/favorites"); } catch {} }
  $("#wsFavs").innerHTML = favs.length ? favs.map(f => wsCard(f, true)).join("") : `<div class="hint">Noch keine Favoriten – über ★ bei einem Suchergebnis merken.</div>`;
  bindWs($("#wsFavs"));
  ["#qMap","#pugMap"].forEach(sel => fillMapSelect(sel));
}
async function addFav(id){
  try { favs = await api("/api/workshop/favorites", {body:{id}}); toast("Gemerkt"); renderFavs(true); $$(`[data-wsfav="${id}"]`).forEach(b => b.classList.add("fav")); }
  catch(err){ toast(err.message, true); }
}
async function wsSearch(more){
  const q = $("#wsQuery").value.trim();
  if (!more){ wsPage = 1; $("#wsResults").innerHTML = `<div class="hint">Suche im Steam Workshop …</div>`; }
  $("#wsResHead").classList.remove("hidden");
  try {
    const res = await api(`/api/workshop/search?q=${encodeURIComponent(q)}&sort=${encodeURIComponent($("#wsSort").value)}&page=${wsPage}`);
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
$("#btnWsLoadId").onclick = () => { const id = wsIdFromInput(); if (!id) return toast("Bitte Workshop-ID oder Link eingeben", true); changeMap({workshop_id: id, mode: $("#modeSelect").value}); };
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
  $("#plRows").innerHTML = list.length ? list.map(p => `<tr class="${(p.online || []).length ? "plon" : ""}${plMerge === p.id ? " plmerge" : ""}">
    <td>${p.avatar ? `<img class="avatar" src="${esc(p.avatar)}" alt="">` : `<span class="avatar" style="display:inline-block"></span>`}</td>
    <td><input value="${esc(p.nick || "")}" placeholder="${esc(p.name)}" data-rename="${esc(p.id)}" style="max-width:180px"></td>
    <td class="hint">${(p.names || []).slice(-3).map(esc).join(", ")}${p.ts_name ? ` <span class="pill" title="TeamSpeak">🎧 ${esc(p.ts_name)}</span>` : ""}</td>
    <td>${(p.online || []).map(o => `<span class="pill ok">${gameTile(o.game, 12)} ${esc(o.server)}</span>`).join(" ") || `<span class="hint">${esc(Object.values(p.servers || {}).sort((a, b) => b.last - a.last).slice(0, 1).map(x => x.name).join("") || "")}</span>`}</td>
    <td class="mono">${p.steamid ? `<a href="https://steamcommunity.com/profiles/${esc(p.steamid)}" target="_blank" rel="noopener" style="color:inherit">${esc(p.steamid)}</a>` : "–"}</td>
    <td class="mono">${esc(p.lan_ip || "–")}</td><td class="mono">${esc(p.wan_ip || "–")}</td>
    <td>${(p.admin_eff || []).length ? `<span class="pill warn" title="${esc((p.admin_eff || []).map(g => g === "*" ? "alle Spiele" : (GAMES[g]?.label || g)).join(", "))}${p.user ? " · Konto " + esc(p.user) : ""}">★ ${(p.admin_eff || []).includes("*") ? "alle" : (p.admin_eff || []).map(g => GAMES[g]?.short || g).join(", ")}</span>` : ""}</td>
    <td class="hint" title="${p.last_seen ? new Date(p.last_seen * 1000).toLocaleString("de-DE") : ""}">${agoTxt(p.last_seen)}</td>
    <td style="white-space:nowrap"><button class="small" data-pledit="${esc(p.id)}" title="bearbeiten">✎</button><button class="small" data-plmerge="${esc(p.id)}" title="${plMerge ? (plMerge === p.id ? "Zusammenführen abbrechen" : "in den markierten Eintrag übernehmen") : "mit anderem Eintrag zusammenführen"}">⇄</button><button class="small danger" data-pldel="${esc(p.id)}">✕</button></td></tr>`).join("")
    : `<tr><td colspan="10" class="muted">${players.length ? "Keine Treffer." : "Noch keine Spieler – sie erscheinen automatisch, sobald jemand auf einen Server kommt."}</td></tr>`;
  $$("[data-rename]").forEach(i => i.onchange = async () => { players = await api(`/api/players/${encodeURIComponent(i.dataset.rename)}`, {method: "PUT", body: {name: i.value.trim()}}); toast("Nickname gespeichert"); renderPlayerRows(); });
  $$("[data-pledit]").forEach(b => b.onclick = () => openPlayerEdit(b.dataset.pledit, b.closest("tr")));
  $$("[data-pldel]").forEach(b => b.onclick = async () => { if (!confirm("Spieler löschen?")) return; players = await api(`/api/players/${encodeURIComponent(b.dataset.pldel)}`, {method: "DELETE"}); renderPlayerRows(); });
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
  row.innerHTML = `<td colspan="10"><div class="pleditbox">
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
      hostname_pattern: $("#setHostnamePattern").value.trim(), names_pattern: $("#setNamesPattern").value.trim(), internet_host: $("#setInternetHost").value.trim(), auto_bots: $("#setAutoBots").checked, auto_matchzy: $("#setAutoMz").checked, container_dns: $("#setContainerDns").value.trim()}});
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
  $("#stPlayers").textContent = `${st.humans ?? 0}${st.max_players ? " / " + st.max_players : ""}`;
  $("#stAuto").textContent = ""; $("#stAuto").style.color = "";
  $("#gExtra").innerHTML = Object.entries(st.extra || {}).map(([k,v]) => `<span>${esc(k)}</span><span>${esc(v)}</span>`).join("") || `<span class="hint">Keine weiteren Infos</span><span></span>`;
  const canSave = meta.features.includes("save");
  $("#gSaveRow").classList.toggle("hidden", !canSave);
  $("#gClaim").classList.toggle("hidden", !st.unclaimed);
  $("#gActHint").textContent = g === "valheim" ? "Valheim hat keine Remote-Konsole – Neustart und Logs über den Container-Tab." :
    g === "wreckfest" ? "Wreckfest hat keine Remote-Konsole. Die Server-Konsole erreichst du über „Webkonsole ↗“ oben rechts (beim ich777-Image), Neustart und Logs über den Container-Tab." :
    g === "satisfactory" && st.privilege === "Client" ? "Ohne Admin-Passwort nur Lesezugriff – Passwort unter „Bearbeiten“ eintragen." : "";
  if (g === "wreckfest"){ loadWfConfig(); loadWfRotation(); } else { $("#wfPanel").classList.add("hidden"); $("#wfRotPanel").classList.add("hidden"); }
  const list = st.players || [];
  $("#playerRows").innerHTML = list.length ? list.map(p => `<tr><td></td><td class="name">${esc(p.name)}</td><td colspan="2"></td><td class="mono">${esc(p.time || "")}</td><td colspan="3"></td></tr>`).join("")
    : `<tr><td colspan="8" class="muted">${st.humans ? `${st.humans} Spieler online (Namen liefert dieses Spiel nicht)` : "Keine Spieler verbunden."}</td></tr>`;
  $("#stUpdated").textContent = "aktualisiert " + new Date().toLocaleTimeString("de-DE");
  renderHistory();
}
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
  const usedSet = new Set(sug.used);
  $$('[data-cf$="port"]').forEach(i => i.addEventListener("input", () => {
    const v = parseInt(i.value, 10), clash = usedSet.has(v);
    i.style.borderColor = clash ? "var(--bad)" : ""; i.title = clash ? "Port ist bereits belegt" : "";
  }));
}
$("#btnCreate").onclick = async () => {
  const values = Object.fromEntries($$("[data-cf]").map(i => [i.dataset.cf, i.value.trim()]));
  const count = Math.max(1, Math.min(10, parseInt($("#createCount").value, 10) || 1));
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

/* ================= Benutzer ================= */
async function loadUsers(){
  try {
    const r = await api("/api/users");
    $("#uRole").innerHTML = Object.entries(r.roles).map(([k,l]) => `<option value="${k}" ${k==="user"?"selected":""}>${esc(l)}</option>`).join("");
    $("#uRows").innerHTML = r.users.map(u => `<tr>
      <td><b>${esc(u.username)}</b>${me && u.username === me.username ? ' <span class="pill">du</span>' : ""}${u.player ? `<div class="hint">🎮 ${esc(u.player)}</div>` : ""}</td>
      <td><select data-urole="${esc(u.username)}">${Object.entries(r.roles).map(([k,l]) => `<option value="${k}" ${k===u.role?"selected":""}>${esc(l)}</option>`).join("")}</select></td>
      <td>${u.role === "admin" ? `<span class="hint">alles</span>` : `<span class="hint">${esc(permSummary(u.perms, r.levels))}</span> <button class="small" data-uperm="${esc(u.username)}">Rechte …</button>`}</td>
      <td>${u.created ? fmtDate(u.created) : "–"}</td><td>${u.last_login ? fmtDate(u.last_login) : "nie"}</td>
      <td><button class="small" data-upw="${esc(u.username)}">Passwort setzen</button> <button class="small danger" data-udel="${esc(u.username)}">Löschen</button></td></tr>`).join("");
    $$("[data-urole]").forEach(sel => sel.onchange = async () => {
      try { await api(`/api/users/${sel.dataset.urole}`, {method:"PUT", body:{username: sel.dataset.urole, role: sel.value}}); toast("Rolle geändert"); }
      catch(err){ toast(err.message, true); loadUsers(); }
    });
    $$("[data-uperm]").forEach(b => b.onclick = () => openPerms(r.users.find(x => x.username === b.dataset.uperm), r));
    $$("[data-upw]").forEach(b => b.onclick = async () => {
      const pw = prompt(`Neues Passwort für ${b.dataset.upw} (min. 6 Zeichen):`); if (!pw) return;
      try { await api(`/api/users/${b.dataset.upw}`, {method:"PUT", body:{username: b.dataset.upw, password: pw}}); toast("Passwort gesetzt – Benutzer muss sich neu anmelden"); }
      catch(err){ toast(err.message, true); }
    });
    $$("[data-udel]").forEach(b => b.onclick = async () => {
      if (!confirm(`Benutzer ${b.dataset.udel} löschen?`)) return;
      try { await api(`/api/users/${b.dataset.udel}`, {method:"DELETE"}); loadUsers(); } catch(err){ toast(err.message, true); }
    });
  } catch(err){ toast(err.message, true); }
}
function permSummary(p, levels){
  p = p || {};
  const def = +(p["*"] || 0);
  const ex = Object.entries(p).filter(([k, v]) => k !== "*" && +v !== def);
  return `Alle Spiele: ${levels[def]}` + (ex.length ? ` · ${ex.map(([k, v]) => `${GAMES[k]?.short || GAMES[k]?.label || k}: ${levels[v]}`).join(", ")}` : "");
}
let permEditing = null;
function openPerms(u, r){
  if (!u) return;
  permEditing = u.username;
  $("#permUser").textContent = u.username;
  $("#permHints").innerHTML = Object.entries(r.level_hints).map(([k, h]) => `<b>${esc(r.levels[k])}</b>: ${esc(h)}`).join("<br>");
  const p = u.perms || {};
  const opts = (val, withDefault) => (withDefault ? `<option value="" ${val == null ? "selected" : ""}>Standard</option>` : "") +
    Object.entries(r.levels).map(([k, l]) => `<option value="${k}" ${val != null && +val === +k ? "selected" : ""}>${esc(l)}</option>`).join("");
  const games = Object.entries(GAMES).sort((a, b) => a[1].label.localeCompare(b[1].label));
  $("#permGrid").innerHTML = `<label class="permrow permall"><span><b>Alle Spiele (Standard)</b></span><select data-pg="*">${opts(p["*"] ?? 0, false)}</select></label>` +
    games.map(([k, g]) => `<label class="permrow"><span><span class="gtile" style="background:${g.color};width:16px;height:16px">${gicon(k, 11)}</span>${esc(g.label)}</span><select data-pg="${k}">${opts(k in p ? p[k] : null, true)}</select></label>`).join("");
  $("#dlgPerm").showModal();
}
$("#btnPermCancel").onclick = () => $("#dlgPerm").close();
$("#permForm").addEventListener("submit", async e => {
  e.preventDefault();
  const perms = {};
  $$("#permGrid [data-pg]").forEach(sel => { if (sel.value !== "") perms[sel.dataset.pg] = +sel.value; });
  try {
    await api(`/api/users/${permEditing}`, {method: "PUT", body: {username: permEditing, perms}});
    $("#dlgPerm").close(); toast("Rechte gespeichert"); loadUsers();
  } catch(err){ toast(err.message, true); }
});
$("#btnUAdd").onclick = async () => {
  try {
    await api("/api/users", {body:{username: $("#uName").value.trim(), password: $("#uPw").value, role: $("#uRole").value}});
    toast("Benutzer angelegt"); $("#uName").value = ""; $("#uPw").value = ""; loadUsers();
  } catch(err){ toast(err.message, true); }
};
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

/* ================= Start ================= */
async function start(){
  clearInterval(pubTimer);
  $("#login").classList.add("hidden"); $("#pub").classList.add("hidden"); $("#app").classList.remove("hidden");
  try {
    const [m, g] = await Promise.all([api("/api/me"), api("/api/games")]);
    me = m.user; GAMES = g.games; dockerOn = g.docker;
    loadGameIcons().then(() => { renderServerList(); if (view === "dash") refreshDash(); });
    document.body.classList.toggle("not-admin", !me || me.role !== "admin");
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
  const me = await api("/api/me").catch(() => ({authenticated:false}));
  me.authenticated ? start() : showPublic();
})();

$("#btnWeb").onclick = () => { if (current && current.web_url) window.open(current.web_url, "_blank", "noopener"); };

/* ================= Beitreten ================= */
function copyText(t){
  const done = () => toast(`Kopiert: ${t}`);
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t).then(done).catch(() => fallbackCopy(t, done));
  fallbackCopy(t, done);
}
function fallbackCopy(t, done){
  const ta = document.createElement("textarea"); ta.value = t; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); done(); } catch { prompt("Adresse kopieren:", t); }
  ta.remove();
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
      ${j.error ? `<div class="e">${esc(j.error)}</div>` : `<div class="bar indet"><i></i></div><div class="s">${esc(j.step || "…")}</div><button class="small danger mgronly" data-act-cancel="${esc(j.id)}" title="Anlegen abbrechen und aufräumen">✕ Abbrechen</button>`}</div>`);
  });
  (a.items || []).forEach(it => {
    const p = it.progress;
    if (!p) return;   // links nur Fortschritt anzeigen, keine Fehlermeldungen
    if (it.prefill){
      parts.push(`<div class="act" data-act-prefill="${esc(it.svc || "steam")}" title="Prefill öffnen">
        <div class="t">${gicon("prefill", 14)}<span class="n">${esc(it.name)}</span></div>
        <div class="bar"><i style="width:${Math.min(100, p.pct)}%"></i></div>
        <div class="s">${p.label && p.label !== "Vorladen" ? esc(p.label) + " · " : ""}${p.pct.toFixed(0)} %${p.rate != null ? " · " + fmtRate(p.rate) : ""}${p.apps_total ? ` · Spiel ${Math.min(p.apps_done + 1, p.apps_total)}/${p.apps_total}` : ""}</div></div>`);
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
  $$("[data-act-job]").forEach(el => el.onclick = () => showView("create"));
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
    $("#pfYield").checked = s.yield !== false; $("#pfYieldMbs").value = s.yield_mbs ?? 2;
    $("#pfServerGames").checked = s.server_games !== false;
    $("#pfSkipCached").checked = s.skip_cached !== false;
    renderPfApps();
  } else if (JSON.stringify(s.apps || []) !== JSON.stringify(pfApps)){ pfApps = (s.apps || []).slice(); renderPfApps(); }
  $("#pfSub").textContent = `Konfiguration: ${d.config_dir}` + (d.dns ? ` · Lancache-DNS ${d.dns.join(", ")}` : " · kein Lancache-DNS gefunden");
  $("#pfCards").innerHTML = `
    <div class="card"><div class="k">Status</div><div class="v" style="color:${d.auto && d.auto.paused ? "var(--warn,#e5a50a)" : run ? "var(--ok)" : "inherit"}" title="${esc((d.auto && d.auto.reason) || "")}">${d.auto && d.auto.paused ? "pausiert" : run ? "läuft" : c ? (c.exit === 0 ? "fertig" : "beendet (" + c.exit + ")") : "noch nie gelaufen"}</div><div class="s">${d.auto && d.auto.paused ? esc(d.auto.reason || "") : c && c.finished && !run && !c.finished.startsWith("0001") ? "zuletzt " + new Date(c.finished).toLocaleString("de-DE") : esc(d.job.step || d.job.note || "")}</div></div>
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
  $("#pfBanner").classList.toggle("hidden", !(run && paused));
  if (run && paused) $("#pfBanner").innerHTML = `<b>⏸ Prefill pausiert</b> – ${esc(d.auto.reason || "")}${d.auto.since ? ` · seit ${new Date(d.auto.since * 1000).toLocaleTimeString("de-DE")}` : ""}${(d.who || []).length ? `<div style="margin-top:4px">Gerade am Laden: ${d.who.map(w => `<b>${esc(w.name || w.ip)}</b> ${fmtRate(w.bps)}`).join(" · ")}</div>` : ""}${d.auto.manual ? "" : "<div class='hint'>Läuft automatisch weiter, wenn 30 s lang niemand anderes über den Cache lädt. Der eigene Prefill-Traffic wird dabei herausgerechnet.</div>"}`;
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
$("#pfRun").onclick = async () => {
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
  try { await api("/api/prefill/settings", {method: "PUT", body: {schedule: $("#pfSchedule").value, flags, server_games: $("#pfServerGames").checked, skip_cached: $("#pfSkipCached").checked, yield: $("#pfYield").checked, yield_mbs: +$("#pfYieldMbs").value || 2}}); toast("Gespeichert"); loadPrefill(); }
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
$("#stoCopy").onclick = async () => { try { await navigator.clipboard.writeText($("#stoScript").textContent); toast("Skript kopiert"); } catch { toast("Kopieren nicht möglich – bitte herunterladen", true); } };
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
  if (!confirm(on ? "CSTV einschalten (30 s Verzögerung)? Vom Tool angelegte Container werden dafür neu erstellt." : "CSTV ausschalten?")) return;
  try { const r = await api(`/api/servers/${current.id}/cstv`, {method: "POST", body: {on, delay: 30}}); toast(r.how); }
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
  if (!confirm("Neueste Version (Image) holen und Server damit neu starten? Spieldaten und Einstellungen bleiben.")) return;
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
      <td>${o.online ? `${o.humans ?? 0}${lim ? "/" + lim : ""}` : "–"}</td>
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
  const status = (run ? (d.paused ? `<span class="pill warn" title="${esc(d.pause_reason || "")}">⏸ pausiert${d.pause_reason ? " – " + esc(d.pause_reason) : ""}</span>` : `<span class="pill ok">läuft${d.rate ? " · ↓ " + fmtRate(d.rate) : ""}</span>`)
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
