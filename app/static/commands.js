"use strict";
// Befehlsreferenz je Spiel: [Befehl, Beschreibung]. <…> = Platzhalter zum Ausfüllen.
const COMMANDS = {
  cs2: {
    note: "RCON-Befehle. Mehrere mit ; trennen.",
    groups: {
      "Server & Status": [["status","Spieler, Map, Version"],["hostname \"<name>\"","Servername setzen"],["sv_password \"<passwort>\"","Server-Passwort (leer = keins)"],["sv_visiblemaxplayers <anzahl>","Sichtbare Slots"],["say <text>","Nachricht an alle"],["exec <datei.cfg>","Config ausführen"],["cvarlist <filter>","Cvars suchen"]],
      "Map & Modus": [["changelevel <map>","Map wechseln (Modus bleibt)"],["map <map>","Map neu laden (übernimmt Modus)"],["game_type <0|1>","0 = Classic, 1 = Gungame/DM"],["game_mode <0|1|2>","0 Casual, 1 Competitive, 2 Wingman"],["host_workshop_map <id>","Workshop-Map laden"],["host_workshop_collection <id>","Workshop-Sammlung laden"],["maps *","Verfügbare Maps auflisten"]],
      "Match": [["mp_warmup_end","Warmup beenden"],["mp_warmup_start","Warmup starten"],["mp_restartgame 1","Neustart in 1 s"],["mp_pause_match","Pause (nächste Freezetime)"],["mp_unpause_match","Pause beenden"],["mp_swapteams","Teams tauschen"],["mp_scrambleteams","Teams mischen"],["mp_maxrounds <n>","Max. Runden"],["mp_roundtime <min>","Rundenzeit"],["mp_freezetime <s>","Freezetime"],["mp_startmoney <betrag>","Startgeld"],["mp_overtime_enable 1","Overtime an"]],
      "Spieler & Bots": [["kickid <userid>","Kicken (ID aus status)"],["kick <name>","Kicken per Name"],["banid <min> <userid>","Bannen (0 = permanent)"],["bot_add_t","Bot zu T"],["bot_add_ct","Bot zu CT"],["bot_kick","Alle Bots raus"],["bot_quota <n>","Anzahl Bots"],["bot_difficulty <0-3>","Bot-Stärke"]],
      "MatchZy": [["matchzy_loadmatch_url \"<url>\"","Match-Config laden"],["css_start","Match erzwingen"],["css_restart","Match neu starten"],["css_forcepause","Pause erzwingen"],["css_forceunpause","Pause aufheben"],["get5_endmatch","Match abbrechen"],["get5_status","Match-Status (JSON)"],["css_plugins list","Geladene Plugins"]],
    },
  },
  factorio: {
    note: "RCON-Befehle mit / – Text ohne / geht als Chat-Nachricht raus.",
    groups: {
      "Server": [["/players online","Wer ist online"],["/players","Alle bekannten Spieler"],["/admins","Admins anzeigen"],["/version","Spielversion"],["/time","Spielzeit der Karte"],["/seed","Karten-Seed"],["/evolution","Evolution der Beißer"],["/server-save <name>","Spiel speichern"],["/config get <einstellung>","Server-Einstellung lesen"],["/config set <einstellung> <wert>","Server-Einstellung setzen"]],
      "Spieler": [["/promote <spieler>","Zum Admin machen"],["/demote <spieler>","Admin entziehen"],["/kick <spieler> <grund>","Kicken"],["/ban <spieler> <grund>","Bannen"],["/unban <spieler>","Entbannen"],["/mute <spieler>","Stummschalten"],["/unmute <spieler>","Stummschaltung aufheben"],["/whitelist add <spieler>","Zur Whitelist"],["/whitelist enable","Whitelist aktivieren"],["/purge <spieler>","Chatnachrichten löschen"]],
      "Chat": [["/shout <text>","An alle (auch Teams)"],["/whisper <spieler> <text>","Privatnachricht"]],
      "Achtung": [["/silent-command <lua>","Lua ausführen – deaktiviert Errungenschaften!"]],
    },
  },
  satisfactory: {
    note: "Server-Konsole über die offizielle API.",
    groups: {
      "Server": [["?","Alle verfügbaren Befehle auflisten"],["server.SaveGame \"<name>\"","Spielstand speichern"],["FG.AutosaveInterval <sekunden>","Autosave-Intervall"],["quit","Server sauber beenden"]],
      "Diagnose": [["Stat FPS","Framerate"],["Stat Unit","Performance-Werte"]],
    },
  },
  valheim: {
    note: "Valheim hat keine Remote-Konsole. Diese Befehle gibst du im Spiel als Admin ein (F5, Admin per SteamID in adminlist.txt).",
    readonly: true,
    groups: {
      "Admin (im Spiel, F5)": [["kick <name/ip/userID>","Spieler kicken"],["ban <name/ip/userID>","Spieler bannen"],["unban <ip/userID>","Bann aufheben"],["banned","Gebannte anzeigen"],["save","Welt speichern"],["ping","Ping zum Server"],["info","Systeminfos"],["lodbias <zahl>","Sichtweite (Client)"]],
    },
  },
  wreckfest: {
    note: "Wreckfest hat keine Remote-Konsole. Befehle im Spiel-Chat (T) als Admin oder in der Webkonsole eingeben – mit führendem /.",
    readonly: true,
    groups: {
      "Server": [["/servername <name>","Servername ändern"],["/password <passwort>","Server-Passwort setzen"],["/welcome <text>","Begrüßungstext"],["/message <text>","Nachricht in den Chat"],["/restart","Server neu starten"],["/eventloop","Event-Rotation an/aus"],["/balanceteams","Teams ausgleichen"],["/bot","Bot hinzufügen"]],
      "Spieler": [["/kick <id>","Kicken"],["/ban <id>","Bannen"],["/bansteamid <steamid>","Per SteamID bannen"],["/unban <index>","Bann aufheben"],["/clearbans","Alle Banns löschen"],["/op <id>","Moderator machen"],["/admin <id>","Admin machen"],["/demote <id>","Rechte entziehen"]],
    },
  },
};
