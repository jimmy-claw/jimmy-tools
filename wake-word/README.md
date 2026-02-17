# Wake Word Detection — "Hey Jimmy"

Custom wake word detection using [openWakeWord](https://github.com/dscripka/openWakeWord).

## Overview

Lightweight always-on wake word detection that triggers the full voice pipeline:

```
[Microphone] → openWakeWord ("Hey Jimmy") → Whisper (transcribe) → Claude (think) → Piper (respond)
```

Runs on Pi5 CPU with minimal resources (~5MB model, <5% CPU).

## Use Cases

- **Meeting bot** — Only process speech directed at Jimmy, ignore cross-talk
- **Home Assistant** — "Hey Jimmy, turn off the lights"
- **Phone (S6)** — Wake word triggers voice command mode
- **Always-on assistant** — Low-power listening on Pi5 with USB mic

## Setup

```bash
pip install openwakeword pyaudio

# Test with pre-trained "hey jarvis" model first
python detect.py --model hey_jarvis

# Train custom "hey jimmy" model (see training section)
python detect.py --model models/hey_jimmy.onnx
```

## Training Custom Wake Word

openWakeWord supports training custom models via a [Colab notebook](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb).

Steps:
1. Generate synthetic "hey jimmy" samples using TTS (Piper/Qwen3)
2. Augment with noise/room impulse responses
3. Train the small detection model (~30 min on Colab)
4. Export to ONNX

Or use the automated script:
```bash
python scripts/train_wake_word.py --phrase "hey jimmy" --output models/hey_jimmy.onnx
```

## Integration

### Standalone detection
```bash
python detect.py --model models/hey_jimmy.onnx --callback scripts/on_wake.sh
```

### Meeting bot integration
```python
from wake_word import WakeWordDetector

detector = WakeWordDetector(model_path="models/hey_jimmy.onnx")
detector.on_wake(lambda: start_listening())
detector.start()
```

### Home Assistant
openWakeWord integrates natively with Home Assistant's voice pipeline.
See: https://www.home-assistant.io/voice_control/create_wake_word/
