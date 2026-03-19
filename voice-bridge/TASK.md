Build a push-to-talk voice web app in Go that lets the user talk to Jimmy (OpenClaw AI agent).

## Target directory
Work in THIS directory: ~/jimmy-tools/voice-bridge/

## Architecture
- Go HTTP + WebSocket server (use gorilla/websocket)
- Single HTML page embedded in binary via `embed`
- Port: 5001

## PTT Flow
1. User opens http://pi5.local:5001 on phone
2. Big "HOLD TO TALK" button
3. While held: browser records audio (MediaRecorder API, audio/webm), streams chunks via WebSocket
4. On release: server saves audio chunks to temp .webm file, converts to WAV with ffmpeg, runs STT, sends text to Jimmy, gets TTS audio, streams WAV back
5. Browser auto-plays response, returns to ready state

## STT
Use faster-whisper via Python (already installed):
```go
cmd := exec.Command("python3", "-c", `
from faster_whisper import WhisperModel
import sys
model = WhisperModel("tiny", device="cpu", compute_type="int8")
segments, _ = model.transcribe(sys.argv[1])
print(" ".join(s.text for s in segments))
`, wavFile)
```

## Jimmy Integration
First check what flags are available:
```bash
openclaw message send --help
```
Then use something like:
```go
cmd := exec.Command("openclaw", "message", "send", "--text", text)
out, _ := cmd.Output()
// parse response from out
```
Note: openclaw binary is at /home/vpavlin/.npm-global/bin/openclaw
The HOME for vpavlin is /home/vpavlin, and openclaw config is at ~/.openclaw/

## TTS
Find piper model first:
```bash
find /home/vpavlin -name "en_GB-alan-medium.onnx" 2>/dev/null
```
Then:
```go
piperCmd := exec.Command("sh", "-c",
    fmt.Sprintf(`echo %q | /home/vpavlin/.local/bin/piper --model MODEL_PATH --output_file %s`,
    text, outWav))
```

## Frontend (embedded in main.go)
- Mobile-first, dark theme: bg=#0d0d0d, accent=#7b68ee, text=#e0e0e0 (Jimmy's color scheme)
- Font: monospace (JetBrains Mono, Courier New)
- Big round PTT button (hold to talk)
- States with visual feedback: Ready / 🔴 Recording / ⚙️ Processing / 🔊 Playing
- Show transcription + Jimmy's text response below button
- Reconnect automatically on disconnect

## Files to create
- `main.go` — full server (200-300 lines)
- `go.mod` — use module name `voice-bridge`
- `Makefile` — targets: build, run, clean
- `README.md` — setup + usage

## Platform
- Linux ARM64 (Raspberry Pi 5), run as vpavlin
- Go 1.21+ available
- ffmpeg available
- piper at /home/vpavlin/.local/bin/piper

When completely done and compiling, run:
openclaw system event --text "Done: voice-bridge Go app built successfully, ready to run at ~/jimmy-tools/voice-bridge/" --mode now
