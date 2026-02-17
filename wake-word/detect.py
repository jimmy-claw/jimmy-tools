#!/usr/bin/env python3
"""
Wake word detection using openWakeWord.

Listens on microphone and triggers a callback when the wake word is detected.

Usage:
    # Test with pre-trained model
    python detect.py --model hey_jarvis

    # Use custom "hey jimmy" model
    python detect.py --model models/hey_jimmy.onnx

    # With callback script
    python detect.py --model models/hey_jimmy.onnx --callback scripts/on_wake.sh

    # Pipe mode — outputs "WAKE" on stdout when triggered (for integration)
    python detect.py --model models/hey_jimmy.onnx --pipe
"""

import argparse
import sys
import subprocess
import time
import numpy as np

try:
    import pyaudio
except ImportError:
    print("pip install pyaudio")
    sys.exit(1)

try:
    import openwakeword
    from openwakeword.model import Model
except ImportError:
    print("pip install openwakeword")
    sys.exit(1)


# Audio settings
CHUNK = 1280  # 80ms at 16kHz (openWakeWord expects this)
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

# Detection settings
THRESHOLD = 0.5
COOLDOWN_SECONDS = 2.0  # Don't re-trigger within this window


def main():
    parser = argparse.ArgumentParser(description="Wake word detection")
    parser.add_argument("--model", type=str, default="hey_jarvis",
                        help="Model name (pre-trained) or path to .onnx file")
    parser.add_argument("--threshold", type=float, default=THRESHOLD,
                        help="Detection threshold (0.0-1.0)")
    parser.add_argument("--callback", type=str, default=None,
                        help="Script/command to run on detection")
    parser.add_argument("--pipe", action="store_true",
                        help="Output WAKE to stdout on detection (for piping)")
    parser.add_argument("--device", type=int, default=None,
                        help="PyAudio input device index")
    parser.add_argument("--list-devices", action="store_true",
                        help="List available audio input devices")
    args = parser.parse_args()

    # List devices
    pa = pyaudio.PyAudio()

    if args.list_devices:
        print("Available input devices:")
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                print(f"  [{i}] {info['name']} (channels: {info['maxInputChannels']})")
        pa.terminate()
        return

    # Load model
    if args.model.endswith(".onnx"):
        # Custom model file
        print(f"Loading custom model: {args.model}")
        oww_model = Model(wakeword_models=[args.model])
    else:
        # Pre-trained model name
        print(f"Loading pre-trained model: {args.model}")
        openwakeword.utils.download_models()
        oww_model = Model(wakeword_models=[args.model])

    model_names = list(oww_model.models.keys())
    print(f"Models loaded: {model_names}")
    print(f"Threshold: {args.threshold}")
    print(f"Listening... (Ctrl+C to stop)")
    print()

    # Open audio stream
    stream = pa.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
        input_device_index=args.device,
    )

    last_trigger = 0

    try:
        while True:
            # Read audio chunk
            audio_data = stream.read(CHUNK, exception_on_overflow=False)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)

            # Run prediction
            prediction = oww_model.predict(audio_array)

            # Check each model
            for model_name in model_names:
                score = prediction[model_name]

                if score > args.threshold:
                    now = time.time()
                    if now - last_trigger < COOLDOWN_SECONDS:
                        continue
                    last_trigger = now

                    print(f"🎤 WAKE [{model_name}] score={score:.3f}")

                    if args.pipe:
                        print("WAKE", flush=True)

                    if args.callback:
                        try:
                            subprocess.Popen(
                                args.callback,
                                shell=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                        except Exception as e:
                            print(f"  ✗ Callback failed: {e}")

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


if __name__ == "__main__":
    main()
