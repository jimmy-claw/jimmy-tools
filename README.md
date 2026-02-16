# Meeting Bot - AI Agent for Browser-Based Video Meetings

An autonomous agent that joins browser-based video meetings (Google Meet, Jitsi), captures audio for transcription, and speaks back via TTS — all on a Raspberry Pi 5 with no physical audio hardware.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Meeting Bot Agent                     │
│                                                         │
│  ┌──────────┐   ┌─────────────┐   ┌──────────────────┐ │
│  │ Chromium  │──▶│ Virtual Sink│──▶│ transcribe.py    │ │
│  │ (meeting) │   │ (monitor)   │   │ (Whisper/faster- │ │
│  │           │◀──│ Virtual Src │◀──│  whisper)         │ │
│  └──────────┘   └─────────────┘   └──────────────────┘ │
│       ▲                                    │            │
│       │              ┌─────────────┐       ▼            │
│       └──────────────│ speak.py    │◀── AI Response     │
│                      │ (TTS→vmic)  │                    │
│                      └─────────────┘                    │
└─────────────────────────────────────────────────────────┘

Audio Flow:
  Meeting Audio → PulseAudio Null Sink → Monitor Source → parec → Whisper
  TTS Audio → paplay → Virtual Source (remapped) → Chromium mic input
```

## Components

### Virtual Audio (PulseAudio)

Two virtual devices:
1. **meeting-sink** — Chromium outputs audio here. We monitor it for transcription.
2. **virtual-mic** — We play TTS audio here. Chromium reads it as microphone input.

The trick: Chromium's `--use-fake-device-for-media-stream` with `--use-fake-ui-for-media-stream` auto-accepts mic/camera permissions. Combined with `PULSE_SINK` and `PULSE_SOURCE` env vars, we route audio through our virtual devices.

### Browser Automation (Playwright)

Playwright with Chromium handles:
- Navigating to the meeting URL
- Dismissing popups / joining the meeting
- Platform-specific logic (Google Meet join flow vs Jitsi)

### Transcription (Whisper)

`faster-whisper` (CTranslate2-based) runs locally on the Pi 5. Audio is captured from the virtual sink's monitor source via `parec`, piped as raw PCM, and transcribed in real-time chunks.

### TTS Response

`speak.py` takes text, generates speech (via piper-tts for local, or OpenAI/ElevenLabs API), and plays it into the virtual microphone source so the meeting hears it.

## Prerequisites

- Raspberry Pi 5 (arm64, 8GB recommended)
- Debian/Ubuntu-based OS (Raspberry Pi OS Bookworm)
- PulseAudio (default on RPi OS Desktop) or PipeWire with pipewire-pulse
- Python 3.11+
- ~2GB free disk for Whisper model

## Quick Start

```bash
# 1. Install everything (needs sudo for system packages)
chmod +x setup.sh
./setup.sh

# 2. Activate the virtual environment
source venv/bin/activate

# 3. Join a meeting
python join_meeting.py "https://meet.jit.si/my-test-room"

# 4. In another terminal, start transcription
source venv/bin/activate
python transcribe.py

# 5. In another terminal, test TTS injection
source venv/bin/activate
python speak.py "Hello, I am an AI assistant joining this meeting."
```

## Full Auto Mode

```bash
source venv/bin/activate
python agent.py "https://meet.jit.si/my-test-room"
```

This runs join + transcribe + respond in one process.

## Chromium Flags Reference

| Flag | Purpose |
|------|---------|
| `--use-fake-device-for-media-stream` | Use fake (virtual) audio/video devices |
| `--use-fake-ui-for-media-stream` | Auto-accept mic/camera permission prompts |
| `--use-file-for-fake-audio-capture=/path/to/file.wav` | Use a WAV file as mic input (alternative to virtual source) |
| `--autoplay-policy=no-user-gesture-required` | Allow autoplay without user interaction |
| `--disable-gpu` | Disable GPU (useful for headless on Pi) |
| `--no-sandbox` | Required when running as root (avoid if possible) |

## Platform-Specific Notes

### Google Meet
- Requires a Google account login (or guest access if enabled)
- Join flow: dismiss "ready to join" dialog, click "Ask to join" or "Join now"
- May require cookies/profile for authenticated access
- Consider using a persistent Chromium profile with pre-authenticated Google session

### Jitsi Meet
- No account required — easiest to test with
- Just navigate to URL, set display name, join
- Open source, self-hostable

### Zoom Web Client
- Flaky, often redirects to desktop app download
- Requires `?pwd=` in URL for passworded meetings
- Lower priority target

## Packages Requiring sudo

- `pulseaudio` (usually pre-installed)
- `chromium-browser` (usually pre-installed on RPi OS)
- `ffmpeg`
- `libportaudio2`
- System Python packages for building wheels

## File Structure

```
meeting-bot/
├── README.md           # This file
├── setup.sh            # Install deps, configure virtual audio
├── virtual_audio.sh    # Create/destroy virtual audio devices
├── join_meeting.py     # Playwright browser automation
├── transcribe.py       # Capture audio → Whisper transcription
├── speak.py            # TTS → virtual microphone injection
├── agent.py            # Full autonomous agent (join+listen+respond)
├── requirements.txt    # Python dependencies
└── config.py           # Shared configuration
```
