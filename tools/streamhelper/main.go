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
	gc, sc := uuid(), uuid()
	scene := map[string]any{
		"name": c.Profile, "current_scene": "CS2", "current_program_scene": "CS2",
		"scene_order": []any{map[string]any{"name": "CS2"}},
		"sources": []any{
			map[string]any{
				"id": "game_capture", "versioned_id": "game_capture", "name": "CS2 Spiel", "uuid": gc, "enabled": true,
				"settings": map[string]any{"capture_mode": "window", "window": "Counter-Strike 2:SDL_app:cs2.exe",
					"priority": 2, "capture_audio": true, "capture_cursor": false, "allow_transparency": false},
			},
			map[string]any{
				"id": "scene", "versioned_id": "scene", "name": "CS2", "uuid": sc, "enabled": true,
				"settings": map[string]any{"id_counter": 1, "custom_size": false, "items": []any{map[string]any{
					"name": "CS2 Spiel", "source_uuid": gc, "visible": true, "locked": true, "id": 1,
					"pos": map[string]any{"x": 0.0, "y": 0.0}, "scale": map[string]any{"x": 1.0, "y": 1.0}, "rot": 0.0, "align": 5,
					"bounds_type": 2, "bounds_align": 0, "bounds": map[string]any{"x": 1920.0, "y": 1080.0},
				}}},
			},
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
	time.Sleep(2 * time.Second)
}

func cs2Running() bool {
	out, _ := exec.Command("tasklist", "/FI", "IMAGENAME eq cs2.exe", "/NH").Output()
	return strings.Contains(strings.ToLower(string(out)), "cs2.exe")
}

func startCS2(steam string, c Config) {
	args := []string{"-applaunch", "730", "-netconport", fmt.Sprint(c.Netcon), "-fullscreen", "-novid", "-console"}
	if err := exec.Command(steam, args...).Start(); err != nil {
		say("CS2 starten fehlgeschlagen: %v", err)
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
	started := time.Time{}
	if steam == "" {
		say("Steam nicht gefunden – bitte Steam installieren und anmelden (Konto mit CS2).")
	} else if cs2Running() {
		if netcon(c, "echo GrohLAN") != nil {
			if ask("CS2 läuft schon, aber ohne Fernsteuerung. Jetzt beenden und richtig neu starten?") {
				closeApp("cs2.exe")
				time.Sleep(5 * time.Second)
				say("Starte CS2 über Steam (Fernsteuerung auf Port %d) …", c.Netcon)
				startCS2(steam, c)
				started = time.Now()
			} else {
				say("Dann bitte CS2 selbst beenden – die exe startet es danach automatisch neu.")
			}
		}
	} else {
		say("Starte CS2 über Steam (Fernsteuerung auf Port %d) …", c.Netcon)
		startCS2(steam, c)
		started = time.Now()
	}

	last, lastStart, warned := "", started, false
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
				if err := netcon(c, "disconnect", "#sleep 2", "connect "+st.TV, "#sleep 15",
					"spec_autodirector 1", "spec_autodirector_cameraman 0", "cl_draw_only_deathnotices 0"); err != nil {
					if !cs2Running() && steam != "" && time.Since(lastStart) > 2*time.Minute {
						say("CS2 läuft nicht – starte es neu …")
						startCS2(steam, c)
						lastStart, warned = time.Now(), false
					} else {
						say("CS2 noch nicht bereit (%v) – nächster Versuch gleich …", err)
						if cs2Running() && time.Since(lastStart) > 2*time.Minute && !warned {
							warned = true
							say("CS2 läuft, aber die Fernsteuerung antwortet nicht. Bitte prüfen:")
							say("  1) Hat Steam ein Fenster „Startoptionen erlauben?“ geöffnet? → bestätigen.")
							say("  2) Sonst in Steam: CS2 → Eigenschaften → Startoptionen:  -netconport %d", c.Netcon)
							say("     eintragen, CS2 beenden – die exe startet es neu.")
						}
					}
				} else {
					say("Zuschauen: %s  (%s)", st.Match, st.TV)
					last = key
				}
			}
		}
		if obs != "" && !obsRunning() {
			say("OBS wurde geschlossen – starte es wieder …")
			startOBS(obs, c)
		}
		time.Sleep(10 * time.Second)
	}
}
