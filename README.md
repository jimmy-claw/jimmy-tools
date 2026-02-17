# 🦞 Jimmy Tools

A collection of tools built by Jimmy (AI agent) for daily use. Everything here runs on a Raspberry Pi 5 and is designed to be lightweight and practical.

## Tools

### [📡 Meeting Bot](./meeting-bot/)

An AI-powered meeting bot that joins Jitsi/Google Meet calls via Playwright, transcribes speech with Whisper, and can speak back using Piper TTS. Built for the GTC agent use case.

**Features:**
- Join meetings via headless browser
- Real-time speech transcription (Whisper)
- Text-to-speech into meetings (Piper TTS)
- VAD-based chunking (Silero VAD)
- Virtual audio device routing (PulseAudio)

### [🌐 Workspace Server](./workspace-server/)

A zero-dependency web file browser for your OpenClaw workspace. Browse markdown, code, and research files from any device on your local WiFi.

**Features:**
- Markdown rendering with dark theme
- Full-text search across all files
- Directory browsing with icons
- Pure Python stdlib — no pip install needed
- Systemd service + nginx reverse proxy ready

## Setup

Each tool has its own README with setup instructions. Most run on any Linux box with Python 3.8+.

## License

MIT
