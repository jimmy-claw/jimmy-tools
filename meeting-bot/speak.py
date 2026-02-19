#!/usr/bin/env python3
"""Generate TTS audio and inject it into the virtual microphone for the meeting."""

import subprocess
import sys
import os
import tempfile
import wave
import struct
import config


def speak_piper(text: str, output_path: str = None) -> str:
    """Generate speech using Piper TTS (local, fast on Pi 5).
    
    Returns path to generated WAV file.
    """
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".wav")

    model_path = os.path.join(
        os.path.dirname(__file__),
        "piper-models",
        f"{config.PIPER_MODEL}.onnx"
    )

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"Piper model not found at {model_path}. Run setup.sh first."
        )

    # Piper reads text from stdin, outputs WAV
    cmd = [
        sys.executable, "-m", "piper",
        "--model", model_path,
        "--output_file", output_path,
    ]

    proc = subprocess.run(
        cmd,
        input=text.encode(),
        capture_output=True,
        timeout=60,
    )

    if proc.returncode != 0:
        # Fallback: try piper command directly
        cmd = [
            "piper",
            "--model", model_path,
            "--output_file", output_path,
        ]
        proc = subprocess.run(cmd, input=text.encode(), capture_output=True, timeout=60)

    if proc.returncode != 0:
        raise RuntimeError(f"Piper TTS failed: {proc.stderr.decode()}")

    return output_path


def speak_xtts(text: str, output_path: str = None) -> str:
    """Generate speech using Jimmy's custom XTTS voice server on K11.

    Supports sentence-level chunking: if config.XTTS_SENTENCE_CHUNK is True,
    splits text into sentences and plays each one as it's ready, reducing
    perceived latency in live meetings.

    Returns path to last generated WAV file (or None if chunked+played inline).
    """
    import re
    import urllib.request
    import json

    def _generate_and_play(sentence: str, path: str):
        payload = json.dumps({
            "text": sentence,
            "model_id": "mp3_44100",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }).encode()
        req = urllib.request.Request(
            f"{config.XTTS_SERVER_URL}/v1/text-to-speech/{config.XTTS_VOICE_ID}",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "xi-api-key": config.XTTS_API_KEY,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            with open(path, "wb") as f:
                f.write(resp.read())

    if config.XTTS_SENTENCE_CHUNK:
        # Split into sentences and play each as it's ready
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        sentences = [s for s in sentences if s.strip()]
        for sentence in sentences:
            chunk_path = tempfile.mktemp(suffix=".mp3")
            try:
                print(f"[speak_xtts] Generating: '{sentence[:60]}'")
                _generate_and_play(sentence, chunk_path)
                # Convert mp3 → wav at correct sample rate for paplay
                wav_path = tempfile.mktemp(suffix=".wav")
                subprocess.run([
                    "ffmpeg", "-y", "-i", chunk_path,
                    "-ar", str(config.SAMPLE_RATE), "-ac", "1", "-f", "wav", wav_path,
                ], capture_output=True, timeout=30)
                inject_audio_to_meeting(wav_path)
                os.unlink(wav_path)
            finally:
                if os.path.exists(chunk_path):
                    os.unlink(chunk_path)
        return None
    else:
        # Generate full text in one shot
        if output_path is None:
            output_path = tempfile.mktemp(suffix=".mp3")
        _generate_and_play(text, output_path)
        # Convert to wav for paplay
        wav_path = tempfile.mktemp(suffix=".wav")
        subprocess.run([
            "ffmpeg", "-y", "-i", output_path,
            "-ar", str(config.SAMPLE_RATE), "-ac", "1", "-f", "wav", wav_path,
        ], capture_output=True, timeout=60)
        os.unlink(output_path)
        return wav_path


def speak_openai(text: str, output_path: str = None) -> str:
    """Generate speech using OpenAI TTS API.
    
    Requires OPENAI_API_KEY environment variable.
    Returns path to generated WAV file.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package required. pip install openai")

    if output_path is None:
        output_path = tempfile.mktemp(suffix=".wav")

    client = OpenAI()
    response = client.audio.speech.create(
        model=config.OPENAI_TTS_MODEL,
        voice=config.OPENAI_TTS_VOICE,
        input=text,
        response_format="wav",
    )
    response.stream_to_file(output_path)
    return output_path


def inject_audio_to_meeting(wav_path: str):
    """Play a WAV file into the virtual microphone sink.
    
    This makes the meeting hear our TTS output.
    Uses paplay to route audio to the virtual-mic sink.
    """
    cmd = [
        "paplay",
        "--device", config.VIRTUAL_MIC_NAME,
        wav_path,
    ]

    print(f"[speak] Playing audio to virtual mic: {wav_path}")
    proc = subprocess.run(cmd, capture_output=True, timeout=120)

    if proc.returncode != 0:
        # Try with ffmpeg conversion first (in case of format mismatch)
        converted = tempfile.mktemp(suffix=".wav")
        subprocess.run([
            "ffmpeg", "-y", "-i", wav_path,
            "-ar", str(config.SAMPLE_RATE),
            "-ac", str(config.CHANNELS),
            "-f", "wav",
            converted,
        ], capture_output=True, timeout=30)

        proc = subprocess.run(
            ["paplay", "--device", config.VIRTUAL_MIC_NAME, converted],
            capture_output=True, timeout=120,
        )
        os.unlink(converted)

    if proc.returncode != 0:
        raise RuntimeError(f"paplay failed: {proc.stderr.decode()}")

    print("[speak] Audio injected successfully.")


def speak(text: str):
    """Generate TTS and inject into meeting.
    
    High-level function: text in → meeting hears it.
    """
    print(f"[speak] Generating TTS: '{text[:80]}...' " if len(text) > 80 else f"[speak] Generating TTS: '{text}'")

    if config.TTS_ENGINE == "openai":
        wav_path = speak_openai(text)
    elif config.TTS_ENGINE == "xtts":
        # XTTS handles inject_audio_to_meeting internally when chunking
        wav_path = speak_xtts(text)
        if wav_path is None:
            return  # Already played sentence by sentence
    else:
        wav_path = speak_piper(text)

    try:
        inject_audio_to_meeting(wav_path)
    finally:
        if wav_path and os.path.exists(wav_path):
            os.unlink(wav_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python speak.py 'Hello, I am an AI assistant.'")
        sys.exit(1)

    text = " ".join(sys.argv[1:])
    speak(text)
