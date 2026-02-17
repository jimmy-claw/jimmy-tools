#!/usr/bin/env bash
#
# Example callback script triggered when wake word is detected.
#
# This is called by detect.py --callback scripts/on_wake.sh
#
# Customize this for your use case:
# - Start recording for Whisper transcription
# - Send a notification
# - Trigger Home Assistant automation
# - Play an acknowledgment sound

echo "🎤 Wake word detected at $(date)"

# Play acknowledgment beep (if aplay available)
if command -v aplay &>/dev/null; then
    # Generate a short beep
    python3 -c "
import struct, math
sr=16000; dur=0.15; freq=880
samples = [int(16000*math.sin(2*math.pi*freq*t/sr)) for t in range(int(sr*dur))]
with open('/tmp/beep.wav','wb') as f:
    import wave
    w=wave.open(f,'w'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes(struct.pack(f'{len(samples)}h',*samples)); w.close()
" 2>/dev/null && aplay -q /tmp/beep.wav 2>/dev/null
fi

# Example: Start a 5-second recording for Whisper
# arecord -d 5 -f S16_LE -r 16000 -c 1 /tmp/command.wav
# whisper /tmp/command.wav --model tiny --language en

# Example: Send to OpenClaw
# curl -s http://localhost:3000/api/message -d '{"text":"Voice command detected"}'

# Example: Home Assistant webhook
# curl -s -X POST http://homeassistant.local:8123/api/webhook/jimmy_wake
