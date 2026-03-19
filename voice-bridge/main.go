package main

import (
	"embed"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"

	"github.com/gorilla/websocket"
)

//go:embed index.html
var static embed.FS

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

var (
	piperBin     string
	piperModel   string
	openclawBin  string
	listenAddr   string
	sessionID    string
	whisperModel string
)

func init() {
	home := os.Getenv("HOME")
	piperBin     = getenv("PIPER_BIN",      home+"/.local/bin/piper")
	piperModel   = getenv("PIPER_MODEL",    home+"/.local/share/piper/en_GB-alan-medium.onnx")
	openclawBin  = getenv("OPENCLAW_BIN",   home+"/.npm-global/bin/openclaw")
	listenAddr   = getenv("LISTEN_ADDR",    "127.0.0.1:5001")
	sessionID    = getenv("OPENCLAW_SESSION", "")
	whisperModel = getenv("WHISPER_MODEL",  "tiny")
}

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
}

// wsMessage is the JSON envelope for all WebSocket frames.
type wsMessage struct {
	Type string `json:"type"`           // "audio_start","audio_chunk","audio_end","transcript","response","audio_response","state","error"
	Data string `json:"data,omitempty"` // text payload or base64 data URI
}

func main() {
	http.HandleFunc("/", serveIndex)
	http.HandleFunc("/ws", handleWS)
	log.Printf("voice-bridge listening on %s", listenAddr)
	log.Fatal(http.ListenAndServe(listenAddr, nil))
}

func serveIndex(w http.ResponseWriter, r *http.Request) {
	data, err := static.ReadFile("index.html")
	if err != nil {
		http.Error(w, "index.html not found", 500)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Write(data)
}

func handleWS(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("upgrade error: %v", err)
		return
	}
	defer conn.Close()

	var mu sync.Mutex
	send := func(msg wsMessage) {
		mu.Lock()
		defer mu.Unlock()
		conn.WriteJSON(msg)
	}

	var chunks [][]byte

	for {
		mt, raw, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure) {
				log.Printf("ws read error: %v", err)
			}
			return
		}

		// Binary frame = audio chunk
		if mt == websocket.BinaryMessage {
			chunks = append(chunks, raw)
			continue
		}

		// Text frame = JSON control message
		var msg wsMessage
		if err := json.Unmarshal(raw, &msg); err != nil {
			log.Printf("bad json: %v", err)
			continue
		}

		switch msg.Type {
		case "audio_start":
			chunks = nil
		case "audio_end":
			go processAudio(chunks, send)
			chunks = nil
		}
	}
}

func processAudio(chunks [][]byte, send func(wsMessage)) {
	send(wsMessage{Type: "state", Data: "processing"})

	tmpDir, err := os.MkdirTemp("", "vb-*")
	if err != nil {
		sendErr(send, "failed to create temp dir: %v", err)
		return
	}
	defer os.RemoveAll(tmpDir)

	// 1. Save webm
	webmPath := filepath.Join(tmpDir, "input.webm")
	f, err := os.Create(webmPath)
	if err != nil {
		sendErr(send, "create webm: %v", err)
		return
	}
	for _, c := range chunks {
		f.Write(c)
	}
	f.Close()

	// 2. Convert to WAV with ffmpeg
	wavPath := filepath.Join(tmpDir, "input.wav")
	out, err := exec.Command("ffmpeg", "-y", "-i", webmPath,
		"-ar", "16000", "-ac", "1", "-f", "wav", wavPath).CombinedOutput()
	if err != nil {
		sendErr(send, "ffmpeg: %v\n%s", err, out)
		return
	}

	// 3. STT via faster-whisper
	transcript, err := runSTT(wavPath)
	if err != nil {
		sendErr(send, "stt: %v", err)
		return
	}
	transcript = strings.TrimSpace(transcript)
	if transcript == "" {
		send(wsMessage{Type: "state", Data: "ready"})
		return
	}
	log.Printf("STT: %q", transcript)
	send(wsMessage{Type: "transcript", Data: transcript})

	// 4. Send to Jimmy via openclaw
	reply, err := askJimmy(transcript)
	if err != nil {
		sendErr(send, "jimmy: %v", err)
		return
	}
	log.Printf("Jimmy: %q", reply)
	send(wsMessage{Type: "response", Data: reply})

	// 5. TTS via piper
	ttsPath := filepath.Join(tmpDir, "response.wav")
	if err := runTTS(reply, ttsPath); err != nil {
		sendErr(send, "tts: %v", err)
		return
	}

	// 6. Stream WAV back as base64 data URI
	send(wsMessage{Type: "state", Data: "playing"})
	wavData, err := os.ReadFile(ttsPath)
	if err != nil {
		sendErr(send, "read tts wav: %v", err)
		return
	}
	b64 := base64.StdEncoding.EncodeToString(wavData)
	send(wsMessage{Type: "audio_response", Data: "data:audio/wav;base64," + b64})
	send(wsMessage{Type: "state", Data: "ready"})
}

func runSTT(wavPath string) (string, error) {
	script := fmt.Sprintf(`
import sys
from faster_whisper import WhisperModel
model = WhisperModel("%s", device="cpu", compute_type="int8")
segments, _ = model.transcribe(sys.argv[1])
print(" ".join(s.text for s in segments))
`, whisperModel)
	cmd := exec.Command("python3", "-c", script, wavPath)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("%v: %s", err, out)
	}
	return strings.TrimSpace(string(out)), nil
}

func askJimmy(text string) (string, error) {
	cmd := exec.Command(openclawBin, "agent", "--agent", "main", "--session-id", sessionID, "--message", text, "--json")
	cmd.Env = os.Environ()
	out, err := cmd.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("%v: %s", err, out)
	}

	var resp struct {
		Result struct {
			Payloads []struct {
				Text string `json:"text"`
			} `json:"payloads"`
		} `json:"result"`
	}
	if err := json.Unmarshal(out, &resp); err != nil {
		return "", fmt.Errorf("parse json: %v\nraw: %s", err, out)
	}
	if len(resp.Result.Payloads) == 0 {
		return "", fmt.Errorf("no payloads in response")
	}
	var parts []string
	for _, p := range resp.Result.Payloads {
		if p.Text != "" {
			parts = append(parts, p.Text)
		}
	}
	return strings.Join(parts, "\n"), nil
}

func runTTS(text, outPath string) error {
	cmd := exec.Command(piperBin, "--model", piperModel, "--output_file", outPath)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return err
	}
	go func() {
		io.WriteString(stdin, text)
		stdin.Close()
	}()
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%v: %s", err, out)
	}
	return nil
}

func sendErr(send func(wsMessage), format string, args ...interface{}) {
	msg := fmt.Sprintf(format, args...)
	log.Printf("ERROR: %s", msg)
	send(wsMessage{Type: "error", Data: msg})
	send(wsMessage{Type: "state", Data: "ready"})
}
