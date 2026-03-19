# voice-bridge

Push-to-talk voice web app for talking to Jimmy (OpenClaw AI agent).

## Prerequisites

- Go 1.21+
- ffmpeg
- Python 3 with `faster-whisper` (`pip install faster-whisper`)
- [piper](https://github.com/rhasspy/piper) TTS at `/home/vpavlin/.local/bin/piper`
- [openclaw](https://docs.openclaw.ai/cli) CLI configured with a running gateway

## Build & Run

```bash
make build   # compile binary
make run     # build + start server
make clean   # remove binary
```

The server listens on **port 5001**. Open `http://pi5.local:5001` on your phone.

## How It Works

1. Hold the **HOLD TO TALK** button and speak
2. Audio is streamed to the server via WebSocket
3. Server pipeline: webm → WAV (ffmpeg) → text (faster-whisper) → Jimmy (openclaw agent) → speech (piper)
4. Response audio plays automatically in the browser

## Architecture

Single Go binary with the HTML page embedded via `//go:embed`. No external static files needed.

```
Phone Browser  ←WebSocket→  Go Server  →  faster-whisper (STT)
                                        →  openclaw agent (Jimmy)
                                        →  piper (TTS)
```
