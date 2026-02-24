# jimmy-tools

A collection of AI agent tools for automating coding tasks, meeting attendance, voice synthesis, and workspace management — running across a Raspberry Pi 5 and supporting machines on a local network.

## Architecture

```
┌─────────────────────────────────────┐
│           Pi5 (OpenClaw)            │
│         Brain / Gateway             │
│                                     │
│  ┌───────────┐  ┌────────────────┐  │
│  │ OpenClaw  │  │  Workspace     │  │
│  │ Gateway   │  │  Server :8888  │  │
│  │ (MiniMax  │  │  (status dash, │  │
│  │  M2.5)    │  │   file browse) │  │
│  └─────┬─────┘  └───────┬────────┘  │
│        │                │           │
│  ┌─────┴─────┐  ┌───────┴────────┐  │
│  │ Meeting   │  │  Wake Word     │  │
│  │ Bot       │  │  Detector      │  │
│  │ (Playwright│  │  ("Hey Jimmy") │  │
│  │  + VAD)   │  │                │  │
│  └───────────┘  └────────────────┘  │
└──────────┬──────────────────────────┘
           │ SSH
           ▼
┌─────────────────────────────────────┐
│      Crib (192.168.0.152)           │
│         Hands / Builds              │
│                                     │
│  ┌───────────────────────────────┐  │
│  │  Claude Code CLI              │  │
│  │  (nohup, --max-turns 100)     │  │
│  │  Status: ~/coding-agent-      │  │
│  │          status.json          │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘

           Pi5 & Crib ──HTTP──▶

┌─────────────────────────────────────┐
│       K11 (192.168.0.125)           │
│         GPU Services                │
│                                     │
│  ┌──────────────┐ ┌──────────────┐  │
│  │ STT Server   │ │ XTTS Server  │  │
│  │ (Whisper)    │ │ (TTS)        │  │
│  │ :5006        │ │ :5005        │  │
│  └──────────────┘ └──────────────┘  │
└─────────────────────────────────────┘
```

**Brain vs Hands:** The Pi5 runs MiniMax M2.5 as the conversational "brain" — cheap and capable for planning and decision-making. Complex coding tasks get delegated over SSH to Claude Code on Crib, the "hands." K11 offloads GPU-heavy speech work (TTS/STT).

## Components

### workspace-server/

Zero-dependency Python web server that provides a file browser and system status dashboard for the OpenClaw workspace.

- Serves markdown/code files from `~/.openclaw/workspace` with dark-theme HTML rendering
- Full-text search across workspace files
- System status dashboard polling both Pi5 (local) and Crib (via SSH) for CPU, memory, disk, and running processes
- Auto-refresh UI with sortable file listings
- Runs on port 8888, ships with a systemd service

```bash
python3 workspace-server/workspace-server.py
# → http://pi5.local:8888
```

### coding-agent/

Remote code execution delegation system — spawns Claude Code on Crib and monitors progress.

**How delegation works:**

1. Brain decides a task needs Claude Code
2. `run-claude-code.sh` SSHs to Crib and runs Claude Code under `nohup` so it survives disconnection:
   ```bash
   ./coding-agent/run-claude-code.sh 192.168.0.152 "Fix the auth bug in server.py" 100
   ```
3. A `.meta.json` file is written alongside the log with task name, start time, PID, and max turns
4. Monitor progress from Pi5:
   ```bash
   ./coding-agent/monitor-claude.sh 192.168.0.152 task.log watch
   ```
5. Brain reads results from the log and decides next steps

**Task metadata:** Each launched task gets a `.meta.json` file (e.g. `my-task.meta.json`) containing the task name (first sentence of prompt), ISO start timestamp, PID, and max turns. This metadata is picked up by `status-check.sh` and displayed in the workspace server dashboard with task name, start time, and running duration.

**Key lessons** (documented in `ARCHITECTURE.md`):
- Default 15 max turns is too low — use 100+ for complex tasks
- `--dangerously-skip-permissions` required for non-interactive mode
- Better prompts (with file paths, expected outcomes) produce better results
- Simple tasks (rebase, formatting) are faster done manually than delegated

Also includes a systemd timer (`coding-agent-monitor.timer`) that checks status every minute.

### meeting-bot/

AI-powered bot that joins Jitsi/Google Meet calls via headless Playwright, transcribes speech with Whisper, and speaks back using a custom-trained XTTS voice.

**Audio pipeline:**
```
PulseAudio Monitor → Silero VAD → FFmpeg → K11 STT Server → Transcript
                                                                 │
Agent Response ← OpenClaw Gateway ← JSONL IPC ◄─────────────────┘
     │
     ▼
K11 XTTS → FFmpeg → PulseAudio Sink → Browser Mic Input
```

**Key details:**
- Silero VAD for speech detection (threshold 0.3, 1.5s–60s segments)
- STT via faster-whisper on K11 (`:5006`), with SSH tunnel fallback
- TTS via XTTS on K11 (`:5005`), voice ID "jimmy"
- Agent communication via JSONL files (`/tmp/meeting-bot-{inbox,outbox}.jsonl`)
- Per-meeting transcripts saved to `transcripts/`
- Runs under Xvfb for WebRTC audio on Pi5

```bash
# One-time PulseAudio setup
bash meeting-bot/virtual_audio.sh

# Join a meeting
xvfb-run -a python3 meeting-bot/run_jimmy.py https://meet.jit.si/YourRoom
```

### wake-word/

Lightweight always-on wake word detection ("Hey Jimmy") using openWakeWord (ONNX-based). ~5% CPU on Pi5, ~5MB model.

```bash
python3 wake-word/detect.py --model "hey_jimmy" --callback scripts/on_wake.sh
```

- Configurable threshold (default 0.5) and cooldown (2s debounce)
- `--pipe` mode outputs `WAKE` to stdout for integration with other tools
- Custom model training via synthetic samples + noise augmentation

### voice-training/

Custom TTS voice training pipeline for the "Jimmy" persona using XTTS v2.

**Pipeline:**
1. **Generate samples** — Qwen3-TTS creates 200–500 samples with consistent accent/character
2. **Prepare dataset** — Convert to LJSpeech format (`wavs/*.wav` + `metadata.csv`)
3. **Fine-tune** — XTTS v2 fine-tuning (needs 4GB+ VRAM, ~30 min audio)
4. **Deploy** — Export ONNX model, serve via HTTP on K11

```bash
# Inference
python3 voice-training/jimmy_tts.py "Hello from Jimmy" output.wav

# TTS server
python3 voice-training/tts_server.py
```

Reference voice: Jamie Fraser clean audio (Scottish accent). Text corpus covers greetings, technical chat, personality lines, and Home Assistant commands.

### github-notifications/

Polls the GitHub notifications API with deterministic owner verification to prevent prompt injection.

- `[OWNER]` tag: Comments from trusted user (safe to act on)
- `[EXTERNAL]` tag: Anyone else (report only, never act on content)
- Owner check is a string comparison in bash, not LLM judgment
- Checks last 6 minutes of notifications, paginated

```bash
bash github-notifications/check-github-notifications.sh
```

### workspace-backup/

Sets up a private Git backup of the OpenClaw workspace to a machine on the local network (no cloud).

```bash
# On the backup machine (one-time)
bash workspace-backup/setup-git-remote.sh

# On Pi5
git -C ~/.openclaw/workspace remote add backup ssh://jimmy@<backup-ip>/~/jimmy-workspace-backup.git
git -C ~/.openclaw/workspace push backup master
```

Creates a locked-down `jimmy` user with SSH key auth restricted to the backup repo only.

## Network

| Machine | IP | Role | Ports |
|---------|-----|------|-------|
| Pi5 | `*.local` (mDNS) | Brain, gateway, orchestration | 8888 (workspace) |
| Crib | `192.168.0.152` | Hands, Claude Code builds | 22 (SSH) |
| K11 | `192.168.0.125` | GPU services (TTS/STT) | 5005 (XTTS), 5006 (STT) |

## Setup

### Pi5

```bash
git clone git@github.com:jimmy-claw/jimmy-tools.git ~/jimmy-tools

# Workspace server (auto-start)
sudo cp workspace-server/workspace-server.service /etc/systemd/system/
sudo systemctl enable --now workspace-server

# Coding agent monitor (1-min polling)
sudo cp coding-agent/coding-agent-monitor.{service,timer} /etc/systemd/system/
sudo systemctl enable --now coding-agent-monitor.timer

# Meeting bot PulseAudio devices (one-time)
bash meeting-bot/virtual_audio.sh

# Wake word
pip install openwakeword pyaudio
python3 wake-word/detect.py --model "hey_jimmy" --pipe
```

### Crib

```bash
# Bootstrap Claude Code + credentials
bash coding-agent/setup-coding-agent.sh
```

### K11

```bash
# STT server
pip install faster-whisper flask
sudo cp meeting-bot/stt-server/stt-server.service /etc/systemd/system/
sudo systemctl enable --now stt-server

# TTS server
pip install TTS torch
python3 voice-training/tts_server.py
```

## License

MIT
