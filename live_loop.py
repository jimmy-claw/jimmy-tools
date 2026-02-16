#!/usr/bin/env python3
"""Live meeting loop: capture audio → transcribe → respond via TTS into meeting."""

import subprocess
import numpy as np
import soundfile as sf
import tempfile
import os
import sys
import time

# Settings
CHUNK_SEC = 8
SAMPLE_RATE = 16000
SILENCE_RMS = 0.005
MONITOR = "meeting-sink.monitor"
TTS_SINK = "virtual-mic"
PIPER_MODEL = os.path.join(os.path.dirname(__file__), "models", "en_GB-alan-medium.onnx")

# Load whisper once
print("[loop] Loading Whisper model...", flush=True)
from faster_whisper import WhisperModel
whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
print("[loop] Whisper ready", flush=True)

transcript_buffer = []
last_response_time = 0
MIN_RESPONSE_INTERVAL = 15  # Don't respond more than once per 15s


def capture_audio(duration=CHUNK_SEC):
    """Capture audio from meeting sink monitor."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    subprocess.run([
        "ffmpeg", "-f", "pulse", "-i", MONITOR,
        "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-t", str(duration), path, "-y",
        "-loglevel", "error"
    ], timeout=duration + 5)
    data, sr = sf.read(path, dtype="float32")
    os.unlink(path)
    return data


def transcribe(audio):
    """Transcribe audio with Whisper."""
    segments, _ = whisper.transcribe(audio, language="en")
    text = " ".join(seg.text.strip() for seg in segments)
    return text.strip()


def speak(text):
    """Generate TTS and play into virtual mic sink."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tts_path = f.name

    # Use piper for TTS
    proc = subprocess.run(
        ["piper", "--model", PIPER_MODEL, "--output_file", tts_path],
        input=text.encode(),
        capture_output=True,
        timeout=30
    )
    if proc.returncode != 0:
        print(f"[tts] piper error: {proc.stderr.decode()}", flush=True)
        os.unlink(tts_path)
        return

    # Play into virtual mic
    subprocess.run([
        "paplay", "--device", TTS_SINK, tts_path
    ], timeout=30)
    os.unlink(tts_path)


def should_respond(text):
    """Check if we should respond to this chunk."""
    global last_response_time
    now = time.time()
    if now - last_response_time < MIN_RESPONSE_INTERVAL:
        return False
    # Simple heuristic: respond if there's a question or enough content
    if len(text.split()) < 3:
        return False
    return True


def generate_response(transcript):
    """Generate a simple response. For now, just echo back what was heard."""
    # TODO: Wire to actual LLM (Claude via OpenClaw)
    return f"I heard you say: {transcript}"


def main():
    print("[loop] Starting live meeting loop", flush=True)
    print(f"[loop] Capturing {CHUNK_SEC}s chunks from {MONITOR}", flush=True)
    print(f"[loop] TTS output to {TTS_SINK}", flush=True)
    print("[loop] Press Ctrl+C to stop\n", flush=True)

    global last_response_time

    while True:
        try:
            # Capture
            audio = capture_audio()
            rms = np.sqrt(np.mean(audio ** 2))
            peak = np.max(np.abs(audio))

            if rms < SILENCE_RMS:
                print(f"[loop] silence (rms={rms:.6f})", flush=True)
                continue

            # Transcribe
            text = transcribe(audio)
            if not text:
                print(f"[loop] no speech (rms={rms:.4f}, peak={peak:.4f})", flush=True)
                continue

            print(f"[hear] {text}", flush=True)
            transcript_buffer.append(text)

            # Respond
            if should_respond(text):
                full_transcript = " ".join(transcript_buffer[-5:])  # Last 5 chunks
                response = generate_response(full_transcript)
                print(f"[say] {response}", flush=True)
                speak(response)
                last_response_time = time.time()
                transcript_buffer.clear()

        except KeyboardInterrupt:
            print("\n[loop] Stopped", flush=True)
            break
        except Exception as e:
            print(f"[loop] error: {e}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
