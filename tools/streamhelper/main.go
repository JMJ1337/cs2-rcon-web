// GrohLAN Stream-PC: richtet OBS ein (Profil + Szene mit CS2-Spielaufnahme, Stream-Ziel), startet CS2 mit
// Fernsteuerung (-netconport) und OBS mit „Stream starten“, und verbindet CS2 danach automatisch per CSTV mit dem
// jeweils laufenden Turnierspiel (Auto-Kamera an).
//
// Die Einstellungen (Tool-Adresse, Stream-Server, Schlüssel) hängt das Tool beim Herunterladen ans Ende der exe.
package main

import (
	"bufio"
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

const marker = "\n#GROHLAN-STREAM-CONFIG#"

type Config struct {
	API     string `json:"api"`
	Server  string `json:"server"`
	Key     string `json:"key"`
	Netcon  int    `json:"netcon"`
	Profile string `json:"profile"`
}

type State struct {
	Enabled bool   `json:"enabled"`
	TV      string `json:"tv"`
	ID      string `json:"id"`
	Match   string `json:"match"`
}

func say(f string, a ...any) { fmt.Printf(time.Now().Format("15:04:05")+"  "+f+"\n", a...) }

func loadConfig() (Config, error) {
	var c Config
	exe, err := os.Executable()
	if err != nil {
		return c, err
	}
	b, err := os.ReadFile(exe)
	if err != nil {
		return c, err
	}
	i := bytes.LastIndex(b, []byte(marker))
	if i < 0 {
		return c, fmt.Errorf("keine Einstellungen in der exe – bitte im Spielservermanager (Turnier → Live-Stream) neu herunterladen")
	}
	err = json.Unmarshal(bytes.TrimSpace(b[i+len(marker):]), &c)
	if c.Netcon == 0 {
		c.Netcon = 2121
	}
	if c.Profile == "" {
		c.Profile = "GrohLAN"
	}
	return c, err
}

func uuid() string {
	b := make([]byte, 16)
	rand.Read(b)
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	h := hex.EncodeToString(b)
	return h[0:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:]
}

// ---------------------------------------------------------------- OBS
func findOBS() string {
	for _, base := range []string{os.Getenv("ProgramFiles"), os.Getenv("ProgramFiles(x86)"), `C:\Program Files`} {
		if base == "" {
			continue
		}
		p := filepath.Join(base, "obs-studio", "bin", "64bit", "obs64.exe")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return ""
}

func installOBS() string {
	say("OBS Studio ist nicht installiert – installiere es mit winget (kann ein paar Minuten dauern) …")
	cmd := exec.Command("winget", "install", "-e", "--id", "OBSProject.OBSStudio", "--accept-source-agreements", "--accept-package-agreements", "--silent")
	cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
	if err := cmd.Run(); err != nil {
		say("winget fehlgeschlagen (%v). Bitte OBS Studio von https://obsproject.com installieren und die exe erneut starten.", err)
		return ""
	}
	return findOBS()
}

func writeIfMissing(path, content string) {
	if _, err := os.Stat(path); err == nil {
		return
	}
	os.MkdirAll(filepath.Dir(path), 0o755)
	os.WriteFile(path, []byte(content), 0o644)
}

// Erst-Start-Assistent von OBS überspringen (sonst blockiert er beim ersten Öffnen)
func skipFirstRun(dir string) {
	for _, f := range []string{"global.ini", "user.ini"} {
		p := filepath.Join(dir, f)
		b, err := os.ReadFile(p)
		if err != nil {
			writeIfMissing(p, "[General]\r\nFirstRun=true\r\n")
			continue
		}
		s := string(b)
		if strings.Contains(s, "FirstRun=") {
			continue
		}
		if strings.Contains(s, "[General]") {
			s = strings.Replace(s, "[General]", "[General]\r\nFirstRun=true", 1)
		} else {
			s = "[General]\r\nFirstRun=true\r\n" + s
		}
		os.WriteFile(p, []byte(s), 0o644)
	}
}

func configureOBS(c Config) error {
	appdata := os.Getenv("APPDATA")
	if appdata == "" {
		return fmt.Errorf("APPDATA nicht gesetzt")
	}
	dir := filepath.Join(appdata, "obs-studio")
	prof := filepath.Join(dir, "basic", "profiles", c.Profile)
	os.MkdirAll(prof, 0o755)
	os.MkdirAll(filepath.Join(dir, "basic", "scenes"), 0o755)
	skipFirstRun(dir)

	svc, _ := json.MarshalIndent(map[string]any{
		"type":     "rtmp_custom",
		"settings": map[string]any{"server": c.Server, "key": c.Key, "use_auth": false, "bwtest": false},
	}, "", "  ")
	if err := os.WriteFile(filepath.Join(prof, "service.json"), svc, 0o644); err != nil {
		return err
	}
	ini := strings.Join([]string{
		"[General]", "Name=" + c.Profile, "",
		"[Output]", "Mode=Simple", "",
		"[SimpleOutput]", "StreamEncoder=x264", "Preset=veryfast", "VBitrate=6000", "ABitrate=160", "UseAdvanced=false", "",
		"[Video]", "BaseCX=1920", "BaseCY=1080", "OutputCX=1920", "OutputCY=1080", "FPSType=0", "FPSCommon=60", "ScaleType=bicubic", "",
		"[Audio]", "SampleRate=48000", "ChannelSetup=Stereo", "",
	}, "\r\n")
	if err := os.WriteFile(filepath.Join(prof, "basic.ini"), []byte(ini), 0o644); err != nil {
		return err
	}
	base := strings.TrimSuffix(c.API, "/api/public/stream/state")
	browser := func(name, path string) (string, map[string]any) {
		id := uuid()
		return id, map[string]any{
			"id": "browser_source", "versioned_id": "browser_source", "name": name, "uuid": id, "enabled": true,
			"settings": map[string]any{"url": base + path, "width": 1920, "height": 1080, "fps": 30, "reroute_audio": false,
				"shutdown": false, "restart_when_active": false,
				"css": "body { background-color: rgba(0,0,0,0); margin: 0px auto; overflow: hidden; }"},
		}
	}
	item := func(id int, name, src string) map[string]any {
		return map[string]any{"name": name, "source_uuid": src, "visible": true, "locked": true, "id": id,
			"pos": map[string]any{"x": 0.0, "y": 0.0}, "scale": map[string]any{"x": 1.0, "y": 1.0}, "rot": 0.0, "align": 5,
			"bounds_type": 2, "bounds_align": 0, "bounds": map[string]any{"x": 1920.0, "y": 1080.0}}
	}
	sceneSrc := func(name string, items ...map[string]any) map[string]any {
		return map[string]any{"id": "scene", "versioned_id": "scene", "name": name, "uuid": uuid(), "enabled": true,
			"settings": map[string]any{"id_counter": len(items), "custom_size": false, "items": items}}
	}
	gc, au := uuid(), uuid()
	ovID, ov := browser("GrohLAN Overlay (Spielstand / Gleich Live)", "/overlay/game")
	stID, stS := browser("GrohLAN Gleich Live", "/overlay/start")
	brID, brS := browser("GrohLAN Turnierbaum", "/overlay/bracket")
	scene := map[string]any{
		"name": c.Profile, "current_scene": "CS2", "current_program_scene": "CS2",
		"scene_order": []any{map[string]any{"name": "CS2"}, map[string]any{"name": "Gleich Live"}, map[string]any{"name": "Turnierbaum"}},
		"sources": []any{
			map[string]any{
				// Fensteraufnahme (Windows Graphics Capture) statt Spielaufnahme: funktioniert ohne
				// -allow_third_party_software, damit CS2 „secure“ bleibt und CSTV/VAC-Server es annehmen
				"id": "window_capture", "versioned_id": "window_capture", "name": "CS2 Spiel", "uuid": gc, "enabled": true,
				"settings": map[string]any{"window": "Counter-Strike 2:SDL_app:cs2.exe", "method": 2, "priority": 2,
					"cursor": false, "client_area": true, "force_sdr": false},
			},
			map[string]any{
				"id": "wasapi_process_output_capture", "versioned_id": "wasapi_process_output_capture", "name": "CS2 Ton", "uuid": au, "enabled": true,
				"settings": map[string]any{"window": "Counter-Strike 2:SDL_app:cs2.exe", "priority": 2},
			},
			ov, stS, brS,
			// CS2: Spielbild, darüber das Overlay (zeigt selbst „Gleich Live“, solange kein Spiel läuft)
			sceneSrc("CS2", item(1, "CS2 Spiel", gc), item(2, "CS2 Ton", au), item(3, "GrohLAN Overlay (Spielstand / Gleich Live)", ovID)),
			sceneSrc("Gleich Live", item(1, "GrohLAN Gleich Live", stID)),
			sceneSrc("Turnierbaum", item(1, "GrohLAN Turnierbaum", brID)),
		},
		"groups": []any{}, "quick_transitions": []any{}, "transitions": []any{},
		"current_transition": "Fade", "transition_duration": 300,
	}
	b, _ := json.MarshalIndent(scene, "", "  ")
	return os.WriteFile(filepath.Join(dir, "basic", "scenes", c.Profile+".json"), b, 0o644)
}

func obsRunning() bool {
	out, _ := exec.Command("tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH").Output()
	return strings.Contains(strings.ToLower(string(out)), "obs64.exe")
}

func startOBS(obs string, c Config) {
	cmd := exec.Command(obs, "--profile", c.Profile, "--collection", c.Profile, "--scene", "CS2", "--startstreaming",
		"--disable-shutdown-check", "--minimize-to-tray")
	cmd.Dir = filepath.Dir(obs) // OBS findet seine Dateien nur aus dem eigenen Ordner
	if err := cmd.Start(); err != nil {
		say("OBS starten fehlgeschlagen: %v", err)
	}
}

// ---------------------------------------------------------------- Steam / CS2
func findSteam() string {
	out, err := exec.Command("reg", "query", `HKCU\Software\Valve\Steam`, "/v", "SteamExe").Output()
	if err == nil {
		for _, ln := range strings.Split(string(out), "\n") {
			if i := strings.Index(ln, "REG_SZ"); i >= 0 {
				p := strings.TrimSpace(ln[i+6:])
				p = strings.ReplaceAll(p, "/", `\`)
				if _, err := os.Stat(p); err == nil {
					return p
				}
			}
		}
	}
	for _, p := range []string{`C:\Program Files (x86)\Steam\steam.exe`, `C:\Program Files\Steam\steam.exe`} {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return ""
}

// Ja/Nein im Fenster fragen – Enter = Ja
func ask(q string) bool {
	fmt.Printf("%s  %s [J/n] ", time.Now().Format("15:04:05"), q)
	line, _ := bufio.NewReader(os.Stdin).ReadString('\n')
	line = strings.ToLower(strings.TrimSpace(line))
	return line == "" || strings.HasPrefix(line, "j") || strings.HasPrefix(line, "y")
}

func closeApp(exe string) {
	say("Beende %s …", exe)
	exec.Command("taskkill", "/IM", exe).Run() // erst freundlich
	for i := 0; i < 10; i++ {
		time.Sleep(time.Second)
		out, _ := exec.Command("tasklist", "/FI", "IMAGENAME eq "+exe, "/NH").Output()
		if !strings.Contains(strings.ToLower(string(out)), exe) {
			return
		}
	}
	exec.Command("taskkill", "/F", "/IM", exe).Run()
	for i := 0; i < 15; i++ {
		time.Sleep(time.Second)
		out, _ := exec.Command("tasklist", "/FI", "IMAGENAME eq "+exe, "/NH").Output()
		if !strings.Contains(strings.ToLower(string(out)), exe) {
			return
		}
	}
}

func cs2Running() bool {
	out, _ := exec.Command("tasklist", "/FI", "IMAGENAME eq cs2.exe", "/NH").Output()
	return strings.Contains(strings.ToLower(string(out)), "cs2.exe")
}

// CS2 nimmt -netconport unter Windows nur mit den Workshop-Tools (-tools) an. Darum steuert die exe CS2 über eine
// Config-Datei: grohlan_tv.cfg wird geschrieben und per Tastendruck (Pause-Taste, Bind aus grohlan_stream.cfg) ausgeführt.
func findCS2Cfg(steam string) string {
	if steam == "" {
		return ""
	}
	sd := filepath.Dir(steam)
	libs := []string{sd}
	if b, err := os.ReadFile(filepath.Join(sd, "steamapps", "libraryfolders.vdf")); err == nil {
		for _, ln := range strings.Split(string(b), "\n") {
			ln = strings.TrimSpace(ln)
			if strings.HasPrefix(ln, "\"path\"") {
				p := strings.Trim(strings.TrimSpace(strings.TrimPrefix(ln, "\"path\"")), "\"")
				libs = append(libs, strings.ReplaceAll(p, `\\`, `\`))
			}
		}
	}
	for _, l := range libs {
		cfg := filepath.Join(l, "steamapps", "common", "Counter-Strike Global Offensive", "game", "csgo", "cfg")
		if st, err := os.Stat(cfg); err == nil && st.IsDir() {
			return cfg
		}
	}
	return ""
}

func writeStreamCfg(cfgDir string) {
	if cfgDir == "" {
		return
	}
	os.WriteFile(filepath.Join(cfgDir, "grohlan_stream.cfg"), []byte(strings.Join([]string{
		"// GrohLAN Stream-PC (von GrohLAN-Stream.exe geschrieben)",
		`bind "PAUSE" "exec grohlan_tv"`,
		"spec_autodirector 1", "spec_autodirector_cameraman 0", "cl_draw_only_deathnotices 0",
		"echo GrohLAN Stream-Steuerung aktiv", ""}, "\n")), 0o644)
	os.WriteFile(filepath.Join(cfgDir, "grohlan_tv.cfg"), []byte("echo GrohLAN\n"), 0o644)
}

// Befehle an CS2: erst Fernsteuerung (netcon), sonst Config + Tastendruck
func send(c Config, cfgDir string, cmds ...string) error {
	if netcon(c, cmds...) == nil {
		return nil
	}
	if cfgDir == "" {
		return fmt.Errorf("CS2-Ordner nicht gefunden und Fernsteuerung aus")
	}
	if !cs2Running() {
		return fmt.Errorf("CS2 läuft nicht")
	}
	if err := os.WriteFile(filepath.Join(cfgDir, "grohlan_tv.cfg"), []byte(strings.Join(cmds, "\n")+"\n"), 0o644); err != nil {
		return err
	}
	if !pressBind() {
		return fmt.Errorf("CS2-Fenster nicht gefunden")
	}
	return nil
}

// -allow_third_party_software: sonst blockiert CS2 die OBS-Spielaufnahme. tv = CSTV-Adresse, mit der CS2 direkt verbindet.
func startCS2(steam string, c Config, tv ...string) {
	game := []string{"-netconport", fmt.Sprint(c.Netcon), "-sw", "-noborder", "-w", "1920", "-h", "1080", "-novid", "-condebug", "+exec", "grohlan_stream"}
	if len(tv) > 0 && tv[0] != "" {
		game = append(game, "+connect", tv[0])
	}
	// Über Steam starten: direkt gestartetes cs2.exe gilt als „insecure“ und wird von VAC-Servern/CSTV abgewiesen
	if err := exec.Command(steam, append([]string{"-applaunch", "730"}, game...)...).Start(); err != nil {
		say("CS2 starten fehlgeschlagen: %v", err)
	}
}

// CS2-Konsole mitlesen (-condebug schreibt game/csgo/console.log): Verbindungsversuche und Fehler im exe-Fenster zeigen
var (
	conMu   sync.Mutex
	conSeen []string // Zeilen mit „onnect“ seit dem letzten Zurücksetzen
)

func conReset() { conMu.Lock(); conSeen = nil; conMu.Unlock() }

// Hat CS2 laut Konsole mit tv verbunden? (true/false = Ergebnis, ok=false = noch nichts)
func conResult(tv string) (bool, bool) {
	conMu.Lock()
	defer conMu.Unlock()
	for _, l := range conSeen {
		if !strings.Contains(l, tv) && !strings.Contains(l, "Disconnect") {
			continue
		}
		low := strings.ToLower(l)
		if strings.Contains(low, "connected to") && strings.Contains(l, tv) || strings.Contains(low, "spectat") {
			return true, true
		}
		if strings.Contains(low, "fail") || strings.Contains(low, "reject") || strings.Contains(low, "timed out") || strings.Contains(low, "disconnect") {
			return false, true
		}
	}
	return false, false
}

func waitConnected(tv string, sec int) bool {
	for i := 0; i < sec; i++ {
		time.Sleep(time.Second)
		if ok, done := conResult(tv); done {
			return ok
		}
	}
	ok, _ := conResult(tv)
	return ok
}

// laufendem CS2 über Steam „verbinde mit …“ schicken
// steam://connect fragt den Port vorher per Steam-Query ab – CSTV antwortet darauf nicht („Anw.-ID ungültig“).
// steam://run/730//+connect … reicht den Befehl dagegen an das laufende CS2 weiter.
func steamConnect(steam, tv string) {
	exec.Command(steam, "steam://run/730//+connect%20"+tv).Start()
}

func watchConsole(steam string) {
	cfg := findCS2Cfg(steam)
	if cfg == "" {
		return
	}
	logf := filepath.Join(cfg, "..", "console.log")
	var off int64 = -1
	keys := []string{"connect", "Connect", "disconnect", "Disconnect", "GOTV", "SourceTV", "CSTV", "spec_", "rejected", "Rejected",
		"timed out", "Timed out", "error", "Error", "failed", "Failed", "GrohLAN"}
	for {
		time.Sleep(2 * time.Second)
		f, err := os.Open(logf)
		if err != nil {
			continue
		}
		st, _ := f.Stat()
		if off < 0 || st.Size() < off {
			off = st.Size() // ab jetzt (bzw. nach CS2-Neustart neu)
			if st.Size() < 4096 {
				off = 0
			}
		}
		f.Seek(off, 0)
		b, _ := io.ReadAll(f)
		f.Close()
		off += int64(len(b))
		for _, ln := range strings.Split(string(b), "\n") {
			ln = strings.TrimSpace(ln)
			if ln == "" || strings.Contains(ln, "QueuePresentAndWait") || strings.Contains(ln, "[Localization") ||
				strings.Contains(ln, "[ResourceSystem]") || strings.Contains(ln, "loopback") {
				continue
			}
			if strings.Contains(ln, "onnect") || strings.Contains(ln, "pectat") {
				conMu.Lock()
				conSeen = append(conSeen, ln)
				conMu.Unlock()
			}
			for _, k := range keys {
				if strings.Contains(ln, k) {
					if len(ln) > 160 {
						ln = ln[:160]
					}
					say("  CS2> %s", ln)
					break
				}
			}
		}
	}
}

func netcon(c Config, lines ...string) error {
	conn, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", c.Netcon), 3*time.Second)
	if err != nil {
		return err
	}
	defer conn.Close()
	w := bufio.NewWriter(conn)
	for _, l := range lines {
		if strings.HasPrefix(l, "#sleep ") {
			w.Flush()
			var s int
			fmt.Sscan(strings.TrimPrefix(l, "#sleep "), &s)
			time.Sleep(time.Duration(s) * time.Second)
			continue
		}
		w.WriteString(l + "\n")
	}
	return w.Flush()
}

func fetchState(api string) (State, error) {
	var st State
	cl := http.Client{Timeout: 6 * time.Second}
	r, err := cl.Get(api)
	if err != nil {
		return st, err
	}
	defer r.Body.Close()
	b, _ := io.ReadAll(r.Body)
	err = json.Unmarshal(b, &st)
	return st, err
}

func main() {
	fmt.Println("==============================================")
	fmt.Println("  GrohLAN Stream-PC – OBS + CS2 automatisch")
	fmt.Println("  Fenster offen lassen. Beenden: Fenster schließen.")
	fmt.Println("==============================================")
	c, err := loadConfig()
	if err != nil {
		say("Fehler: %v", err)
		fmt.Scanln()
		return
	}
	say("Tool: %s", c.API)
	say("Stream-Ziel: %s", c.Server)

	obs := findOBS()
	if obs == "" {
		obs = installOBS()
	}
	if obs != "" {
		if obsRunning() && ask("OBS läuft schon. Jetzt schließen, einrichten und mit Stream neu starten?") {
			closeApp("obs64.exe")
		}
		if obsRunning() {
			say("OBS läuft weiter mit den alten Einstellungen – falls nicht gestreamt wird: OBS schließen und die exe neu starten.")
		} else if err := configureOBS(c); err != nil {
			say("OBS einrichten fehlgeschlagen: %v", err)
		} else {
			say("OBS eingerichtet (Profil und Szene „%s“, Spielaufnahme CS2) – starte OBS und den Stream …", c.Profile)
			startOBS(obs, c)
		}
	}

	steam := findSteam()
	if cfgDir := findCS2Cfg(steam); cfgDir != "" {
		writeStreamCfg(cfgDir) // Auto-Kamera usw. beim CS2-Start (+exec grohlan_stream)
	}
	go watchConsole(steam)
	started, first := time.Time{}, ""
	if steam == "" {
		say("Steam nicht gefunden – bitte Steam installieren und anmelden (Konto mit CS2).")
	} else if cs2Running() {
		say("CS2 läuft schon – beim nächsten Spiel startet die exe es mit der CSTV-Verbindung neu.")
	} else if st0, err := fetchState(c.API); err == nil && st0.Enabled && st0.TV != "" {
		say("Starte CS2 und verbinde gleich mit %s (%s) …", st0.Match, st0.TV)
		startCS2(steam, c, st0.TV)
		started = time.Now()
		_ = st0
	} else {
		say("Starte CS2 (gerade kein Spiel – verbindet beim nächsten) …")
		startCS2(steam, c)
		started = time.Now()
	}
	last, lastStart := first, started
	for {
		st, err := fetchState(c.API)
		switch {
		case err != nil:
			say("Tool nicht erreichbar: %v", err)
		case !st.Enabled:
			say("Stream ist im Tool ausgeschaltet – warte …")
		case st.TV == "":
			if last != "" {
				say("Kein laufendes Spiel – warte auf das nächste …")
				last = ""
			}
		default:
			key := st.TV + "|" + st.ID
			if key != last {
				if time.Since(lastStart) < 60*time.Second && !lastStart.IsZero() {
					break // CS2 lädt noch
				}
				// 1. mit Fernsteuerung (nur mit -tools) ohne Neustart umschalten
				if netcon(c, "connect "+st.TV) == nil {
					time.Sleep(20 * time.Second)
					netcon(c, "spec_autodirector 1", "spec_autodirector_cameraman 0")
					say("Zuschauen: %s  (%s)", st.Match, st.TV)
					last = key
					break
				}
				if steam == "" {
					say("Steam nicht gefunden – kann CS2 nicht steuern.")
					break
				}
				if ok, _ := conResult(st.TV); ok { // schon verbunden (z. B. per +connect beim Start)
					say("Zuschauen: %s  (%s)", st.Match, st.TV)
					last = key
					break
				}
				// 2. laufendes CS2 (Hauptmenü geladen) über Steam verbinden lassen
				if cs2Running() && time.Since(lastStart) > 45*time.Second {
					say("Spielwechsel → verbinde CS2 über Steam mit %s …", st.TV)
					conReset()
					steamConnect(steam, st.TV)
					if waitConnected(st.TV, 25) {
						say("Zuschauen: %s  (%s)", st.Match, st.TV)
						last = key
						break
					}
					say("Verbinden über Steam hat nicht geklappt – starte CS2 neu …")
					closeApp("cs2.exe")
					time.Sleep(4 * time.Second)
				} else if cs2Running() {
					closeApp("cs2.exe")
					time.Sleep(4 * time.Second)
				}
				// 3. CS2 neu starten (+connect) und nach dem Laden des Hauptmenüs noch einmal über Steam verbinden
				conReset()
				startCS2(steam, c, st.TV)
				lastStart = time.Now()
				say("CS2 startet und verbindet mit %s (%s) …", st.Match, st.TV)
				if waitConnected(st.TV, 45) {
					say("Zuschauen: %s  (%s)", st.Match, st.TV)
				} else {
					conReset()
					steamConnect(steam, st.TV)
					if waitConnected(st.TV, 25) {
						say("Zuschauen: %s  (%s)", st.Match, st.TV)
					} else {
						say("CS2 hat sich nicht verbunden – nächster Versuch beim nächsten Spielwechsel (oder exe neu starten).")
					}
				}
				last = key
			} else if !cs2Running() && steam != "" && time.Since(lastStart) > 2*time.Minute {
				say("CS2 wurde beendet – starte es wieder (%s) …", st.TV)
				startCS2(steam, c, st.TV)
				lastStart = time.Now()
			}
		}
		if obs != "" && !obsRunning() {
			say("OBS wurde geschlossen – starte es wieder …")
			startOBS(obs, c)
		}
		time.Sleep(10 * time.Second)
	}
}
