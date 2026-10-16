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
  _: '<rect x="3" y="7" width="18" height="10" rx="4"/><path d="M8 10v4M6 12h4"/><circle cx="16" cy="11" r="1"/><circle cx="18" cy="13" r="1"/>',
};
const gicon = (g, size=16) => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[g] || ICONS._}</svg>`;
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
  if (res.status === 401 && path !== "/api/login"){ showLogin(); throw new Error("Nicht angemeldet"); }
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
function showLogin(){ stopPoll(); clearInterval(dashTimer); $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); $("#loginPw").focus(); }
$("#loginForm").addEventListener("submit", async e => {
  e.preventDefault(); $("#loginErr").textContent = "";
  try { await api("/api/login", {body:{username: $("#loginUser").value.trim() || "admin", password: $("#loginPw").value}}); $("#loginPw").value = ""; start(); }
  catch(err){ $("#loginErr").textContent = err.message; }
});
$("#btnLogout").onclick = async () => { await api("/api/logout", {method:"POST"}); showLogin(); };

/* ================= Navigation ================= */
$$(".nav [data-view]").forEach(b => b.onclick = () => showView(b.dataset.view));
function showView(v){
  view = v;
  if (v !== "server"){ current = null; stopPoll(); stopCt(); }
  $$(".nav [data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === v));
  VIEWS.forEach(x => $("#view-"+x).classList.toggle("hidden", x !== v));
  if (v === "scan") loadScan();
  if (v === "create") initCreate();
  if (v === "users") loadUsers();
  renderServerList();
  if (v === "dash"){ refreshDash(); refreshCache(); }
  if (v === "players") loadPlayers();
  if (v === "auto") renderAuto();
  if (v === "cache") loadCacheHistory();
}

/* ================= Serverliste ================= */
let overview = [];
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
      <button class="sghead" data-group="${g}" title="${esc(GAMES[g]?.label || g)} ein-/ausklappen">
        <span class="gtile" style="background:${GAMES[g]?.color || "#888"}">${gicon(g, 18)}</span>
        <span class="sgname">${esc(GAMES[g]?.short || g)}</span>
        <span class="sgcount">${on}/${list.length}${players ? ` · ${players} ☺` : ""}</span>
        <span class="chev">▾</span>
      </button>
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
  $$(".sghead").forEach(b => b.onclick = () => {
    const g = b.dataset.group;
    collapsed[g] = b.parentElement.classList.contains("open");
    try { localStorage.setItem("gsmCollapsed", JSON.stringify(collapsed)); } catch {}
    b.parentElement.classList.toggle("open");
  });
}

/* ================= Status-LED ================= */
const CSTATE = {running: "läuft", exited: "gestoppt", restarting: "startet neu", created: "angelegt", paused: "pausiert", dead: "defekt", removing: "wird entfernt"};
function ledOf(o){
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
async function refreshHost(){
  let h;
  try { h = await api("/api/host"); } catch { return; }
  const cpu = h.cpu, memPct = h.mem_total_mb ? Math.round(h.mem_used_mb / h.mem_total_mb * 100) : null;
  $("#hlCpu").textContent = cpu != null ? cpu.toFixed(0) + " %" : "–";
  $("#hlCpuBar").style.width = (cpu || 0) + "%"; $("#hlCpuBar").className = lvl(cpu || 0);
  $("#hlMem").textContent = memPct != null ? memPct + " %" : "–";
  $("#hlMemBar").style.width = (memPct || 0) + "%"; $("#hlMemBar").className = lvl(memPct || 0);
  $("#hlHost").textContent = h.cores ? h.cores + " Kerne" : "";
  const g = h.games || {};
  $("#hlSub").innerHTML = `${fmtMem(h.mem_used_mb)} von ${fmtMem(h.mem_total_mb)} · Load ${h.load ? h.load.map(x => x.toFixed(2)).join(" ") : "–"}` +
    (g.containers ? `<br>Spielserver: ${g.running}/${g.containers} laufen · ${g.cpu_host} % CPU · ${fmtMem(g.mem_mb)}` : "");
}
function loadHtml(l){
  if (!l) return "";
  if (l.error) return `<div class="loadrow"><span>Container</span><span class="hint">${esc(/no such container/i.test(l.error) ? "nicht gefunden – unter „Bearbeiten“ neu zuordnen" : l.error)}</span><span></span></div>`;
  if (l.state !== "running") return `<div class="loadrow"><span>Container</span><span style="color:var(--bad)">${esc(CSTATE[l.state] || l.state || "?")}</span><span></span></div>`;
  const c = l.cpu_host || 0;
  return `<div class="loadrow" title="CPU bezogen auf den ganzen Host (${l.cpu ?? "?"} % eines Kerns)"><span>Last</span>
    <div class="bar"><i class="${lvl(c)}" style="width:${Math.min(100, c)}%"></i></div>
    <span><b>${c.toFixed(1)} %</b> CPU · <b>${fmtMem(l.mem_mb)}</b></span></div>`;
}

/* ================= Lancache ================= */
const fmtBytes = b => b == null ? "–" : b >= 1e12 ? (b/1e12).toFixed(2) + " TB" : b >= 1e9 ? (b/1e9).toFixed(1) + " GB" : b >= 1e6 ? (b/1e6).toFixed(0) + " MB" : Math.round(b/1e3) + " KB";
const LINK_BPS = 125e6;   // 1 Gbit/s als 100 % für den Durchsatz-Balken
const fmtRate = bps => bps >= 1e6 ? (bps/1e6).toFixed(1) + " MB/s" : bps >= 1e3 ? Math.round(bps/1e3) + " KB/s" : "0 KB/s";
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
function svcIcon(id, size = 16){
  const [path, color] = SVC_ICONS[(id || "").toLowerCase()] || SVC_ICONS._;
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
function savedCard(bytes, label){
  return `<div class="card savedcard"><div class="k">Traffic gespart${label ? " · " + label : ""}</div><div class="v" style="color:var(--ok)">${fmtBytes(bytes || 0)}</div>
    <div class="s">nicht erneut aus dem Internet geladen</div></div>`;
}
async function refreshCache(){
  try { cacheData = await api("/api/cache"); } catch { return; }
  const c = cacheData, h = c.last_hour || {}, d = c.last_day || {};
  $("#hlCache").classList.toggle("hidden", !c.container);
  $("#hlNetRow").classList.toggle("hidden", !c.container);
  if (c.container){
    const pct = Math.min(100, (c.rate_bps || 0) / LINK_BPS * 100);
    $("#hlNet").textContent = fmtRate(c.rate_bps || 0);
    $("#hlNetBar").style.width = Math.max(pct, c.rate_bps ? 2 : 0) + "%";
    $("#hlNetRow").title = `Lancache-Durchsatz (Balken = Anteil an 1 Gbit/s) · davon ${fmtRate(c.hit_rate_bps || 0)} aus dem Cache`;
    $("#hlCache").innerHTML = `Lancache: ${d.hit_ratio != null ? d.hit_ratio + " % aus dem Cache (24 h)" : "noch keine Daten"}`;
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
      ${savedCard(d.hit_bytes, "24 h")}
      <div class="card"><div class="k">Aus dem Cache (24 h)</div><div class="v" style="color:var(--ok)">${fmtBytes(d.hit_bytes)}</div><div class="s">${d.hit_ratio != null ? d.hit_ratio + " % Trefferquote" : "noch keine Downloads"}</div></div>
      <div class="card"><div class="k">Aus dem Internet (24 h)</div><div class="v">${fmtBytes(d.miss_bytes)}</div><div class="s">${(d.requests || 0).toLocaleString("de-DE")} Anfragen</div></div>
      <div class="card"><div class="k">Durchsatz jetzt</div><div class="v">${fmtRate(c.rate_bps || 0)}</div><div class="s">davon ${fmtRate(c.hit_rate_bps || 0)} aus dem Cache · letzte Std. ${fmtBytes((h.hit_bytes||0)+(h.miss_bytes||0))}</div></div>
      <div class="card"><div class="k">Cache-Speicher</div><div class="v">${disk != null ? disk + " %" : "–"}</div>
        ${c.disk ? `<div class="bar" style="margin-top:6px"><i class="${lvl(disk)}" style="width:${disk}%"></i></div><div class="s">${fmtBytes(c.disk.used)} von ${fmtBytes(c.disk.total)}</div>` : ""}</div>
    </div>
    ${svc ? `<div class="panel" style="padding:12px 16px"><h2 style="margin-bottom:6px">Was wurde ausgeliefert? <span class="hint">(letzte 24 h, nach Dienst)</span> <a href="#" class="hint" style="float:right" onclick="showView('cache');return false">Verlauf bis 1 Jahr →</a></h2>
      <div style="overflow:auto"><table class="cachetable"><thead><tr><th>Dienst</th><th>aus dem Cache</th><th>aus dem Internet</th><th>gesamt</th><th>Trefferquote</th><th></th></tr></thead><tbody>${svc}</tbody></table></div></div>`
      : `<div class="hint" style="margin-bottom:14px">In den letzten 24 Stunden wurde nichts über den Lancache geladen.</div>`}
  </div>`;
}

/* ================= Verlaufs-Metriken ================= */
let metricsData = {}, metricsRange = (() => { try { return +localStorage.getItem("gsmRange") || 360; } catch { return 360; } })(), metricsAt = 0;
async function loadMetrics(force){
  if (!force && Date.now() - metricsAt < 30000) return;
  try { metricsData = await api(`/api/metrics?minutes=${metricsRange}`); metricsAt = Date.now(); } catch {}
}
function spark(vals, color, opts = {}){
  const w = 200, h = opts.h || 34, pad = 2;
  const nums = vals.filter(v => v != null);
  if (!nums.length) return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><line x1="0" y1="${h-1}" x2="${w}" y2="${h-1}" stroke="var(--line)"/></svg>`;
  const max = Math.max(opts.min || 1, ...nums), n = vals.length;
  const x = i => (i / (n - 1)) * w, y = v => h - pad - (v / max) * (h - pad * 2);
  let d = "", area = "", seg = [];
  const flush = () => {
    if (!seg.length) return;
    d += "M" + seg.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("L");
    area += `M${x(seg[0][0]).toFixed(1)},${h}L` + seg.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("L") + `L${x(seg[seg.length-1][0]).toFixed(1)},${h}Z`;
    seg = [];
  };
  vals.forEach((v, i) => v == null ? flush() : seg.push([i, v])); flush();
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${area}" fill="${color}" opacity=".18"/><path d="${d}" fill="none" stroke="${color}" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>`;
}
const rangeLabel = m => m >= 1440 ? "24 h" : m >= 60 ? (m / 60) + " h" : m + " min";
function hostPanelHtml(){
  const m = metricsData._host;
  if (!m || !m.samples) return "";
  const cpuN = m.cpu.filter(v => v != null), memN = m.mem.filter(v => v != null);
  const avg = a => a.length ? (a.reduce((x, y) => x + y, 0) / a.length).toFixed(1) : "–";
  const mx = a => a.length ? Math.max(...a).toFixed(0) : "–";
  return `<div class="dsect"><h3 class="dhead"><span class="gtile" style="background:#8aa4c8">${gicon("_", 16)}</span>Gesamtlast des Servers <span class="hint">${rangeLabel(m.minutes)}</span></h3>
    <div class="panel"><div class="hostpanel">
      <div><div class="mlab"><span>CPU</span><b>Ø ${avg(cpuN)} % · max ${mx(cpuN)} %</b></div>${spark(m.cpu, "var(--ct)", {min: 100})}</div>
      <div><div class="mlab"><span>RAM belegt</span><b>jetzt ${memN.length ? memN[memN.length-1] : "–"} % · max ${mx(memN)} %</b></div>${spark(m.mem, "#a78bfa", {min: 100})}</div>
    </div></div></div>`;
}
function metricsHtml(sid, color){
  const m = metricsData[sid];
  if (!m || !m.samples) return `<div class="hint mstats">Verlauf wird gesammelt …</div>`;
  const cpuNums = m.cpu.filter(v => v != null), memNums = m.mem.filter(v => v != null);
  const cpuAvg = cpuNums.length ? (cpuNums.reduce((a, b) => a + b, 0) / cpuNums.length).toFixed(1) : null;
  return `<div class="mgrid">
      <div class="mcell"><div class="mlab"><span>Spieler · ${rangeLabel(m.minutes)}</span><b>Peak ${m.peak_24h}</b></div>${spark(m.players, color, {min: 2})}</div>
      ${cpuNums.length ? `<div class="mcell"><div class="mlab"><span>CPU</span><b>Ø ${cpuAvg} %</b></div>${spark(m.cpu, "var(--ct)", {min: 5})}</div>` : ""}
      ${memNums.length ? `<div class="mcell"><div class="mlab"><span>RAM</span><b>${fmtMem(memNums[memNums.length-1])}</b></div>${spark(m.mem, "#a78bfa", {min: 256})}</div>` : ""}
    </div>
    ${!cpuNums.length && !memNums.length ? `<div class="hint mstats">CPU/RAM: ${servers.find(x => x.id === sid)?.container ? "Container läuft nicht" : "unter „Bearbeiten“ den Docker-Container zuordnen"}</div>` : ""}
    <div class="hint mstats">Verfügbarkeit 24 h: <b>${m.uptime_24h != null ? m.uptime_24h + " %" : "–"}</b>${m.ping != null ? ` · Ping Ø <b>${m.ping} ms</b>` : ""} · Peak 24 h: <b>${m.peak_24h}</b></div>`;
}

/* ================= Dashboard ================= */
async function refreshDash(){
  try { overview = await api("/api/overview"); } catch { return; }
  await loadMetrics();
  if (view === "dash") $("#hostPanel").innerHTML = hostPanelHtml();
  renderServerList();
  if (view !== "dash") return;
  $("#dashEmpty").classList.toggle("hidden", overview.length > 0);
  const on = overview.filter(o => o.online).length;
  const pl = overview.reduce((a,o) => a + (o.online ? (o.humans||0) : 0), 0);
  $("#dashSub").textContent = `${on} von ${overview.length} online · ${pl} Spieler gesamt · aktualisiert ${new Date().toLocaleTimeString("de-DE")}`;
  $$("#rangeSeg [data-range]").forEach(b => b.classList.toggle("active", +b.dataset.range === metricsRange));
  const order = Object.keys(GAMES);
  const byGame = order.map(g => [g, overview.filter(o => gameOf(o.server) === g)]).filter(([, l]) => l.length);
  $("#dashGrid").innerHTML = byGame.map(([g, items]) => `<div class="dsect"><h3 class="dhead"><span class="gtile" style="background:${GAMES[g].color}">${gicon(g, 16)}</span>${esc(GAMES[g].label)} <span class="hint">${items.filter(o => o.online).length}/${items.length} online</span></h3><div class="dash">` + items.map(o => {
    const s = o.server, slots = o.visible_players > 0 ? o.visible_players : (o.max_players || 0);
    const pct = slots ? Math.min(100, Math.round((o.humans||0) / slots * 100)) : 0;
    const mz = o.matchzy && o.matchzy.match ? `${esc(o.matchzy.match.team1||"")} vs ${esc(o.matchzy.match.team2||"")} · ${esc(o.matchzy.match.state||"")}` : (o.matchzy && o.matchzy.installed ? "kein Match geladen" : "–");
    return `<div class="dcard" data-id="${esc(s.id)}">
      <div class="top">${led(o)}${gbadge(gameOf(s))}<b>${esc(s.name)}</b>${o.online && o.join ? (o.join.url ? `<a class="joinbtn" href="${esc(o.join.url)}" title="Beitreten: ${esc(o.join.address)}" data-stop>▶ Beitreten</a>` : `<span class="joinbtn" data-copy="${esc(o.join.address)}" title="${esc(o.join.hint)}">⧉ ${esc(o.join.address)}</span>`) : `<span class="hint mono">${esc(s.host)}:${esc(s.port)}</span>`}</div>
      ${o.online ? (gameOf(s) === "cs2" ? `
      <div class="kv">
        <span>Map</span><span title="${esc(o.map)}">${esc((o.workshop && o.workshop.title) || o.map || "?")}</span>
        <span>Modus</span><span>${esc(o.mode ? o.mode.label : "?")}</span>
        <span>Spieler</span><span>${o.humans ?? 0} / ${slots || "?"}${o.bots ? ` (+${o.bots} Bots)` : ""}</span>
        <span>MatchZy</span><span>${mz}</span>
      </div>` : `
      <div class="kv">
        <span>${worldLabel(gameOf(s))}</span><span>${esc(o.map || "–")}</span>
        <span>Spieler</span><span>${o.humans ?? 0}${o.max_players ? " / " + o.max_players : ""}</span>
        ${Object.entries(o.extra || {}).filter(([k]) => !["Session","Servername","Strecke"].includes(k)).slice(0, 2).map(([k,v]) => `<span>${esc(k)}</span><span>${esc(v)}</span>`).join("")}
      </div>`) + `
      <div class="bar"><i style="width:${pct}%"></i></div>
      ${loadHtml(o.load)}
      ${installHtml(o.install)}
      ${metricsHtml(s.id, GAMES[gameOf(s)]?.color || "var(--accent)")}
      ${o.auto && o.auto.capped ? `<span class="pill warn">Slots begrenzt auf ${o.max_players} – SLOTS im Stack erhöhen</span>` : ""}
      ${o.unclaimed ? `<span class="pill warn">Satisfactory: noch nicht beansprucht</span>` : ""}`
      : `${ledOf(o).cls === "warn" ? `<div class="pill warn" style="justify-self:start">Container läuft – Spiel startet oder aktualisiert noch</div>` : ""}<div class="hint">${esc(o.error || (o.online === false ? "offline" : "noch nicht abgefragt"))}</div>${loadHtml(o.load)}${installHtml(o.install)}${metricsHtml(s.id, GAMES[gameOf(s)]?.color || "var(--accent)")}`}
    </div>`;
  }).join("") + `</div></div>`).join("");
  $$(".dcard").forEach(el => el.onclick = e => {
    if (e.target.closest("[data-stop]")) return;
    const c = e.target.closest("[data-copy]");
    if (c) return copyText(c.dataset.copy);
    selectServer(servers.find(s => s.id === el.dataset.id));
  });
}

/* ================= Server-Ansicht ================= */
const VIEWS = ["dash","players","auto","server","scan","create","users","cache"];
function applyGameClasses(s){
  const g = gameOf(s), meta = GAMES[g] || {};
  document.body.classList.toggle("g-other", g !== "cs2");
  document.body.classList.toggle("no-console", !meta.console);
  document.body.classList.toggle("no-container", !(dockerOn && s.container));
}
function selectServer(s){
  if (!s) return showView("dash");
  current = s; view = "server";
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
  ["overview","maps","match","console","settings","container"].forEach(x => $("#tab-"+x).classList.toggle("hidden", x!==t));
  stopPoll(); stopCt();
  if (t === "container"){ refreshContainer(); ctTimer = setInterval(refreshContainer, 5000); }
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
    if (ws && ws.preview){ $("#stMapImg").src = ws.preview; $("#stMapImg").classList.remove("hidden"); } else $("#stMapImg").classList.add("hidden");
    $("#stMode").textContent = st.mode ? st.mode.label : "?";
    $("#stRounds").textContent = st.maxrounds ? `max. ${st.maxrounds} Runden` : "";
    const slots = st.visible_players > 0 ? st.visible_players : st.max_players;
    $("#stPlayers").textContent = `${st.humans ?? st.players.length} / ${slots ?? "?"}` + (st.bots ? ` +${st.bots}` : "");
    const a = st.auto || {};
    $("#stAuto").textContent = !a.enabled ? `Automatik aus · max. ${st.max_players}` :
      a.target ? `Auto: ${a.target} Slots (${a.reason})${a.capped ? " – begrenzt durch SLOTS" : ""}` : `Auto: ${a.reason}`;
    $("#stAuto").style.color = a.capped ? "var(--accent)" : "";
    const mz = st.matchzy || {};
    $("#stMz").textContent = mz.installed ? (mz.match ? `${mz.match.team1 || "?"} vs ${mz.match.team2 || "?"}` : "bereit") : "nicht erkannt";
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
    $("#stUpdated").textContent = err.message; $("#playerRows").innerHTML = "";
  }
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
const allSettings = SETTINGS.flatMap(([, f]) => f);
function inputFor([name, , type, opts]){
  if (type === "bool") return `<div class="switch"><input type="checkbox" data-cvar="${name}"><span class="muted" style="font-size:12px">aktiv</span></div>`;
  if (type === "select") return `<select data-cvar="${name}"><option value=""></option>${opts.map(([v,l]) => `<option value="${v}">${esc(l)}</option>`).join("")}</select>`;
  return `<input data-cvar="${name}" type="text" ${type==="number"?'inputmode="decimal"':""} spellcheck="false">`;
}
function renderSettings(){
  $("#settingsBody").innerHTML = SETTINGS.map(([group, fields]) => `
    <div class="panel"><h2>${esc(group)}</h2><div class="settings-grid">
      ${fields.map(f => `<div class="field" id="f-${f[0]}"><label>${esc(f[1])} <code>${f[0]}</code></label>${inputFor(f)}</div>`).join("")}
    </div></div>`).join("");
  $$("[data-cvar]").forEach(el => { el.addEventListener("input", () => markChanged(el)); el.addEventListener("change", () => markChanged(el)); });
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
  const pool = players.filter(p => !f || p.name.toLowerCase().includes(f) || p.steamid.includes(f));
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
  const pick = ids.length ? ids : players.map(p => p.steamid);
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
async function loadPlayers(){
  try { players = await api("/api/players"); } catch(err){ toast(err.message, true); }
  renderPlayerRows();
}
function renderPlayerRows(){
  const f = $("#plFilter").value.trim().toLowerCase();
  const list = players.filter(p => !f || p.name.toLowerCase().includes(f) || p.steamid.includes(f));
  $("#plRows").innerHTML = list.length ? list.map(p => `<tr>
    <td>${p.avatar ? `<img class="avatar" src="${esc(p.avatar)}" alt="">` : `<span class="avatar" style="display:inline-block"></span>`}</td>
    <td><input value="${esc(p.name)}" data-rename="${esc(p.steamid)}" style="max-width:240px"></td>
    <td class="mono"><a href="https://steamcommunity.com/profiles/${esc(p.steamid)}" target="_blank" rel="noopener" style="color:inherit">${esc(p.steamid)}</a></td>
    <td><button class="small danger" data-pldel="${esc(p.steamid)}">Löschen</button></td></tr>`).join("")
    : `<tr><td colspan="4" class="muted">Noch keine Spieler.</td></tr>`;
  $$("[data-rename]").forEach(i => i.onchange = async () => { players = await api(`/api/players/${i.dataset.rename}`, {method:"PUT", body:{name: i.value.trim() || i.dataset.rename}}); toast("Name gespeichert"); });
  $$("[data-pldel]").forEach(b => b.onclick = async () => { if (!confirm("Spieler löschen?")) return; players = await api(`/api/players/${b.dataset.pldel}`, {method:"DELETE"}); renderPlayerRows(); });
}
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
      games_base: $("#setGamesBase").value.trim(), cache_container: $("#setCacheContainer").value.trim()}});
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
          web_url: f.web_url.value.trim(), name_from_game: f.name_from_game.checked,
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
const worldLabel = g => ({satisfactory: "Session", wreckfest: "Strecke"})[g] || "Welt";
function renderGeneric(st){
  const g = gameOf(current), meta = GAMES[g];
  $("#stOnline").textContent = "Online"; $("#stOnline").style.color = "var(--ok)";
  $("#stVersion").textContent = st.version ? "Version " + st.version : "";
  $("#stMapLabel").textContent = worldLabel(g);
  $("#stMap").textContent = st.map || "–"; $("#stMapSub").textContent = st.hostname || "";
  $("#stMapImg").classList.add("hidden");
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
  const list = st.players || [];
  $("#playerRows").innerHTML = list.length ? list.map(p => `<tr><td></td><td class="name">${esc(p.name)}</td><td colspan="2"></td><td class="mono">${esc(p.time || "")}</td><td colspan="3"></td></tr>`).join("")
    : `<tr><td colspan="8" class="muted">${st.humans ? `${st.humans} Spieler online (Namen liefert dieses Spiel nicht)` : "Keine Spieler verbunden."}</td></tr>`;
  $("#stUpdated").textContent = "aktualisiert " + new Date().toLocaleTimeString("de-DE");
  renderHistory();
}
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
let tpl = null, createGame = "cs2", jobTimer = null;
async function initCreate(){
  try { tpl = await api("/api/templates"); } catch(err){ return toast(err.message, true); }
  $("#createNoDocker").classList.toggle("hidden", tpl.docker);
  $("#createNoDocker").innerHTML = `<b style="color:var(--accent)">Docker-Socket nicht eingebunden.</b> <span class="hint">Zum Anlegen und Steuern von Containern muss der Stack <code>/var/run/docker.sock</code> mounten (ist in <code>portainer-stack.yml</code> vorbereitet).</span>`;
  $("#createGameSeg").innerHTML = Object.entries(tpl.templates).map(([k,t]) => `<button data-cg="${k}" class="${k===createGame?"active":""}">${esc(t.label)}</button>`).join("");
  $$("#createGameSeg [data-cg]").forEach(b => b.onclick = () => { createGame = b.dataset.cg; initCreate(); });
  const t = tpl.templates[createGame];
  let sug = {values: {}, n: servers.filter(s => gameOf(s) === createGame).length + 1, used: []};
  try { sug = await api(`/api/templates/${createGame}/suggest`); } catch {}
  const n = sug.n;
  const fill = (v, k) => sug.values[k] != null ? String(sug.values[k]) : String(v).replace("{n}", n).replace("{port}", 27014 + n).replace("{tvport}", 27020 + n);
  $("#createFields").innerHTML = t.fields.map(([k, label, type, def, hint]) => `<div class="field"><label>${esc(label)}</label>${
    type === "select" ? `<select data-cf="${k}">${hint.split(",").map(o => `<option ${o===def?"selected":""}>${o}</option>`).join("")}</select>`
    : `<input data-cf="${k}" type="${type==="password"?"password":"text"}" value="${esc(fill(def, k))}" ${type==="number"?'inputmode="numeric"':""} autocomplete="off">`
  }${hint && type !== "select" ? `<div class="hint">${esc(hint)}</div>` : ""}</div>`).join("");
  const upd = () => { const name = ($('[data-cf="name"]') || {}).value || ""; $("#createDataDir").value = t.data_default.replace("{base}", tpl.games_base || settings.games_base || "/mnt/grohlan").replace("{n}", n).replace("{name}", name); };
  upd(); $('[data-cf="name"]').addEventListener("input", upd);
  $("#createHost").value = (settings.public_url || "").replace(/^https?:\/\//, "").split(/[:/]/)[0] || location.hostname;
  $("#createHint").textContent = `Image: ${t.image} · Der Ordner wird auf dem Docker-Host angelegt und für UID ${t.uid} beschreibbar gemacht. Ports: automatisch die nächsten freien gewählt (${sug.used.length} Ports sind bereits belegt) – vor dem Anlegen wird nochmals auf Überschneidungen geprüft.`;
  const usedSet = new Set(sug.used);
  $$('[data-cf$="port"]').forEach(i => i.addEventListener("input", () => {
    const v = parseInt(i.value, 10), clash = usedSet.has(v);
    i.style.borderColor = clash ? "var(--bad)" : ""; i.title = clash ? "Port ist bereits belegt" : "";
  }));
}
$("#btnCreate").onclick = async () => {
  const values = Object.fromEntries($$("[data-cf]").map(i => [i.dataset.cf, i.value.trim()]));
  if (!confirm(`${tpl.templates[createGame].label}-Server „${values.name}“ anlegen und starten?\nDaten: ${$("#createDataDir").value}`)) return;
  try {
    const job = await api("/api/create", {body:{game: createGame, values, data_dir: $("#createDataDir").value.trim(), host: $("#createHost").value.trim()}});
    $("#createJob").classList.remove("hidden"); $("#btnCreateOpen").classList.add("hidden");
    pollJob(job.id);
  } catch(err){ toast(err.message, true); }
};
function pollJob(id){
  clearTimeout(jobTimer);
  api(`/api/jobs/${id}`).then(async j => {
    $("#createStep").textContent = j.error ? "Fehler: " + j.error : j.done ? "Fertig ✓" : j.step;
    $("#createStep").style.color = j.error ? "var(--bad)" : j.done ? "var(--ok)" : "";
    $("#createLog").textContent = j.log.join("\n");
    if (j.server_id){ await loadServers(); $("#btnCreateOpen").classList.remove("hidden"); $("#btnCreateOpen").onclick = () => selectServer(servers.find(s => s.id === j.server_id)); }
    if (!j.done) jobTimer = setTimeout(() => pollJob(id), 2000);
  }).catch(err => { $("#createStep").textContent = err.message; });
}

/* ================= Benutzer ================= */
async function loadUsers(){
  try {
    const r = await api("/api/users");
    $("#uRole").innerHTML = Object.entries(r.roles).map(([k,l]) => `<option value="${k}" ${k==="user"?"selected":""}>${esc(l)}</option>`).join("");
    $("#uRows").innerHTML = r.users.map(u => `<tr>
      <td><b>${esc(u.username)}</b>${me && u.username === me.username ? ' <span class="pill">du</span>' : ""}</td>
      <td><select data-urole="${esc(u.username)}">${Object.entries(r.roles).map(([k,l]) => `<option value="${k}" ${k===u.role?"selected":""}>${esc(l)}</option>`).join("")}</select></td>
      <td>${u.created ? fmtDate(u.created) : "–"}</td><td>${u.last_login ? fmtDate(u.last_login) : "nie"}</td>
      <td><button class="small" data-upw="${esc(u.username)}">Passwort setzen</button> <button class="small danger" data-udel="${esc(u.username)}">Löschen</button></td></tr>`).join("");
    $$("[data-urole]").forEach(sel => sel.onchange = async () => {
      try { await api(`/api/users/${sel.dataset.urole}`, {method:"PUT", body:{username: sel.dataset.urole, role: sel.value}}); toast("Rolle geändert"); }
      catch(err){ toast(err.message, true); loadUsers(); }
    });
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
$("#btnUAdd").onclick = async () => {
  try {
    await api("/api/users", {body:{username: $("#uName").value.trim(), password: $("#uPw").value, role: $("#uRole").value}});
    toast("Benutzer angelegt"); $("#uName").value = ""; $("#uPw").value = ""; loadUsers();
  } catch(err){ toast(err.message, true); }
};
$("#btnMyPw").onclick = () => { $("#pwForm").reset(); $("#dlgPw").showModal(); };
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
  $("#login").classList.add("hidden"); $("#app").classList.remove("hidden");
  try {
    const [m, g] = await Promise.all([api("/api/me"), api("/api/games")]);
    me = m.user; GAMES = g.games; dockerOn = g.docker;
    document.body.classList.toggle("not-admin", !me || me.role !== "admin");
    document.body.classList.toggle("viewer", me && me.role === "viewer");
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
  dashTimer = setInterval(() => { refreshDash(); refreshHost(); refreshCache(); refreshActivity(); }, 5000);
}
async function showVersion(){
  try {
    const v = await (await fetch("/api/version")).json();
    const d = v.date ? new Date(v.date).toLocaleString("de-DE", {day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit"}) : "";
    const txt = `Version ${v.version}${v.commit && v.commit !== "lokal" ? " (" + v.commit + ")" : ""}${d ? " · " + d : ""}`;
    $("#appVersion").textContent = txt; $("#loginVersion").textContent = txt;
    if (typeof loadedVersion !== "undefined" && loadedVersion === null) loadedVersion = v.version + v.commit;
  } catch {}
}
showVersion();
(async () => {
  const me = await api("/api/me").catch(() => ({authenticated:false}));
  me.authenticated ? start() : showLogin();
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
function progressText(p){
  return `${p.label} · ${p.pct.toFixed(1)} % · ${fmtBytes(p.done)} / ${fmtBytes(p.total)}` +
    (p.rate ? ` · ${fmtRate(p.rate)}` : "") + (p.eta ? ` · noch ${fmtEta(p.eta)}` : "");
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
      ${j.error ? `<div class="e">${esc(j.error)}</div>` : `<div class="bar indet"><i></i></div><div class="s">${esc(j.step || "…")}</div>`}</div>`);
  });
  (a.items || []).forEach(it => {
    const p = it.progress;
    parts.push(`<div class="act ${!p && it.errors.length ? "err" : ""}" data-act-sid="${esc(it.server_id)}" title="${esc(it.container)}">
      <div class="t">${gicon(it.game, 14)}<span class="n">${esc(it.name)}</span>${it.errors.length ? `<button class="x" data-act-dismiss="${esc(it.container)}" title="Fehler ausblenden">✕</button>` : ""}</div>
      ${p ? `<div class="bar"><i style="width:${Math.min(100, p.pct)}%"></i></div><div class="s">${esc(progressText(p))}</div>` : ""}
      ${it.errors.map(e => `<div class="e" title="${esc(e.line)}">⚠ ${esc(e.text)}</div>`).join("")}</div>`);
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
function cacheChart(points, stepH){
  const w = 900, h = 180, n = points.length || 1, bw = w / n;
  const max = Math.max(1, ...points.map(p => p.hit + p.miss));
  const bars = points.map((p, i) => {
    const hh = p.hit / max * (h - 4), mh = p.miss / max * (h - 4), x = (i * bw).toFixed(2), wd = Math.max(0.6, bw - (bw > 4 ? 1 : 0)).toFixed(2);
    const tip = `${fmtBucket(p.t, stepH)}\naus dem Cache (gespart): ${fmtBytes(p.hit)}\naus dem Internet: ${fmtBytes(p.miss)}`;
    return `<g><title>${esc(tip)}</title><rect x="${x}" y="0" width="${wd}" height="${h}" fill="transparent"/>
      ${mh ? `<rect x="${x}" y="${(h - hh - mh).toFixed(1)}" width="${wd}" height="${mh.toFixed(1)}" fill="#8a7a66"/>` : ""}
      ${hh ? `<rect x="${x}" y="${(h - hh).toFixed(1)}" width="${wd}" height="${hh.toFixed(1)}" fill="var(--ok)"/>` : ""}</g>`;
  }).join("");
  const first = points[0], last = points[points.length - 1];
  return `<svg class="cachechart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${bars}
      <line x1="0" y1="${h - 0.5}" x2="${w}" y2="${h - 0.5}" stroke="var(--line)"/></svg>
    <div class="row hint" style="justify-content:space-between;margin-top:4px"><span>${first ? esc(fmtBucket(first.t, stepH)) : ""}</span>
      <span>max. ${fmtBytes(max)} je ${stepH < 24 ? stepH + " h" : stepH === 24 ? "Tag" : "Woche"}</span><span>${last ? esc(fmtBucket(last.t, stepH)) : ""}</span></div>`;
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
  const clients = (c.clients || []).map(x => `<tr><td class="mono">${esc(x.ip)}</td><td class="mono">${fmtBytes(x.bytes)}</td></tr>`).join("");
  $("#cacheHist").innerHTML = `${bfHtml}
    <div class="cards">
      ${savedCard(c.hit_bytes, CACHE_RANGES[c.range])}
      <div class="card"><div class="k">Aus dem Internet</div><div class="v">${fmtBytes(c.miss_bytes)}</div><div class="s">${(c.requests || 0).toLocaleString("de-DE")} Anfragen gesamt</div></div>
      <div class="card"><div class="k">Trefferquote</div><div class="v">${c.hit_ratio != null ? c.hit_ratio + " %" : "–"}</div><div class="s">ausgeliefert gesamt ${fmtBytes(total)}</div></div>
      <div class="card"><div class="k">Ø pro Tag</div><div class="v">${fmtBytes(c.per_day)}</div><div class="s">${c.peak.t ? "Spitze " + fmtRate(c.peak.bps) + " (" + new Date(c.peak.t * 1000).toLocaleString("de-DE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}) + ")" : "noch keine Spitze"}</div></div>
      <div class="card"><div class="k">Cache-Speicher</div><div class="v">${dpct != null ? dpct + " %" : "–"}</div>
        ${dn ? `<div class="bar" style="margin-top:6px"><i class="${lvl(dpct)}" style="width:${dpct}%"></i></div><div class="s">${fmtBytes(dn.used)} von ${fmtBytes(dn.total)}</div>` : ""}</div>
    </div>
    <div class="panel" style="padding:12px 16px;margin-bottom:14px"><h2 style="margin-bottom:8px">Ausgeliefert je ${c.step_h < 24 ? c.step_h + " Stunde(n)" : c.step_h === 24 ? "Tag" : "Woche"}
      <span class="hint"><span class="lgd" style="background:var(--ok)"></span> aus dem Cache (gespart) <span class="lgd" style="background:#8a7a66"></span> aus dem Internet</span></h2>
      ${total ? cacheChart(c.points, c.step_h) : `<div class="hint">Für diesen Zeitraum liegen noch keine Daten vor.</div>`}</div>
    ${c.services.length ? `<div class="panel" style="padding:12px 16px;margin-bottom:14px"><h2 style="margin-bottom:6px">Was wurde gecacht? <span class="hint">(${CACHE_RANGES[c.range]}, nach Dienst)</span></h2>
      <div style="overflow:auto"><table class="cachetable"><thead><tr><th>Dienst</th><th>aus dem Cache</th><th>aus dem Internet</th><th>gesamt</th><th>Trefferquote</th><th></th></tr></thead><tbody>${svcRows(c.services)}</tbody></table></div></div>` : ""}
    <div class="cgrid">
      ${clients ? `<div class="panel" style="padding:12px 16px"><h2 style="margin-bottom:6px">Top-Clients <span class="hint">(${CACHE_RANGES[c.range]})</span></h2><table class="cachetable"><tbody>${clients}</tbody></table></div>` : ""}
      ${diskVals.length > 1 ? `<div class="panel" style="padding:12px 16px"><h2 style="margin-bottom:6px">Cache-Speicher belegt <span class="hint">(% je Tag)</span></h2>${spark(diskVals, "var(--accent)", {min: 100, h: 60})}</div>` : ""}
    </div>`;
}
setInterval(() => { if (view === "cache") loadCacheHistory(); }, 60000);
