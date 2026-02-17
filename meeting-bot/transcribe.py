#!/usr/bin/env python3
"""Capture meeting audio from virtual sink and transcribe with Whisper."""

import subprocess
import sys
import io
import time
import numpy as np
from faster_whisper import WhisperModel
import config


def create_whisper_model():
    """Initialize faster-whisper model."""
    print(f"[transcribe] Loading Whisper model: {config.WHISPER_MODEL}")
    model = WhisperModel(
        config.WHISPER_MODEL,
        device=config.WHISPER_DEVICE,
        compute_type="int8",  # Optimized for CPU/Pi
    )
    print("[transcribe] Model loaded.")
    return model


def capture_audio_chunk(duration_sec: int = None) -> np.ndarray:
    """Capture raw PCM audio from the meeting sink's monitor source.
    
    Uses parec (PulseAudio record) to grab audio from the monitor.
    Returns numpy array of float32 samples.
    """
    duration = duration_sec or config.CHUNK_DURATION_SEC
    
    cmd = [
        "parec",
        "--device", config.MONITOR_SOURCE,
        "--format", config.SAMPLE_FORMAT,
        "--rate", str(config.SAMPLE_RATE),
        "--channels", str(config.CHANNELS),
        "--latency-msec", "100",
    ]

    # Calculate expected bytes: sample_rate * channels * bytes_per_sample * duration
    expected_bytes = config.SAMPLE_RATE * config.CHANNELS * 2 * duration

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=duration + 2,
        )
        raw = proc.stdout
    except subprocess.TimeoutExpired:
        # parec doesn't stop on its own, timeout is expected
        raw = b""

    # Alternative: run with timeout using dd or head to limit bytes
    # This is more reliable:
    cmd_with_limit = (
        f"parec --device={config.MONITOR_SOURCE} "
        f"--format={config.SAMPLE_FORMAT} "
        f"--rate={config.SAMPLE_RATE} "
        f"--channels={config.CHANNELS} "
        f"| head -c {expected_bytes}"
    )
    
    proc = subprocess.run(
        cmd_with_limit, shell=True, capture_output=True, timeout=duration + 5
    )
    raw = proc.stdout

    if len(raw) == 0:
        return np.zeros(config.SAMPLE_RATE * duration, dtype=np.float32)

    # Convert s16le PCM to float32
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def is_silence(audio: np.ndarray, threshold: float = None) -> bool:
    """Check if audio chunk is silence."""
    threshold = threshold or config.SILENCE_THRESHOLD / 32768.0
    rms = np.sqrt(np.mean(audio ** 2))
    return rms < threshold


def transcribe_loop(model, callback=None):
    """Continuously capture and transcribe meeting audio.
    
    Args:
        model: WhisperModel instance
        callback: Optional function called with (text, segments) for each transcription
    """
    print(f"[transcribe] Listening on {config.MONITOR_SOURCE}...")
    print(f"[transcribe] Chunk duration: {config.CHUNK_DURATION_SEC}s")
    print("[transcribe] Press Ctrl+C to stop.\n")

    while True:
        try:
            audio = capture_audio_chunk()

            if is_silence(audio):
                continue

            # Transcribe
            segments, info = model.transcribe(
                audio,
                language=config.WHISPER_LANGUAGE,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200,
                ),
            )

            full_text = ""
            for segment in segments:
                text = segment.text.strip()
                if text:
                    full_text += text + " "
                    print(f"[{segment.start:.1f}s-{segment.end:.1f}s] {text}")

            if full_text.strip() and callback:
                callback(full_text.strip())

        except KeyboardInterrupt:
            print("\n[transcribe] Stopped.")
            break
        except Exception as e:
            print(f"[transcribe] Error: {e}")
            time.sleep(1)


def main():
    """Run standalone transcription."""
    model = create_whisper_model()
    
    def on_transcription(text):
        print(f"\n>>> TRANSCRIBED: {text}\n")

    transcribe_loop(model, callback=on_transcription)


if __name__ == "__main__":
    main()
