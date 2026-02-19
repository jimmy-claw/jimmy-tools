#!/usr/bin/env python3
"""
Jimmy TTS Server v2 - ElevenLabs-compatible API wrapper around XTTS v2
Returns MP3 (what OpenClaw ElevenLabs provider expects).
"""

import os
import sys
import io
import subprocess
import torch
import soundfile as sf
import numpy as np
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

MODEL_PATH = os.path.expanduser("~/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2")
CHECKPOINT = os.path.expanduser("~/jimmy-tts/models/best_model_507.pth")
REF_AUDIO = os.path.expanduser("~/jimmy-tts/models/jamie_fraser_vocal.wav")

model = None
gpt_cond_latent = None
speaker_embedding = None


def load_model():
    global model, gpt_cond_latent, speaker_embedding
    if model is not None:
        return

    print("Loading XTTS model...", flush=True)
    sys.path.insert(0, os.path.expanduser("~/xtts-venv/lib/python3.11/site-packages"))
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    config = XttsConfig()
    config.load_json(os.path.join(MODEL_PATH, "config.json"))

    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=MODEL_PATH, use_deepspeed=False)

    checkpoint_data = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    model_state = checkpoint_data.get("model", checkpoint_data)
    model.load_state_dict(model_state, strict=False)
    model.eval()

    print("Computing speaker embedding...", flush=True)
    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=[REF_AUDIO],
        gpt_cond_len=30,
        gpt_cond_chunk_len=4,
        max_ref_length=60
    )
    print("Model ready!", flush=True)


def chunk_text(text, max_len=230):
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) + 1 <= max_len:
            current = (current + " " + s).strip()
        else:
            if current:
                chunks.append(current)
            current = s
    if current:
        chunks.append(current)
    return chunks or [text]


def wav_to_mp3(wav_bytes):
    """Convert WAV bytes to MP3 using ffmpeg."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "wav", "-i", "pipe:0",
         "-codec:a", "libmp3lame", "-b:a", "128k", "-f", "mp3", "pipe:1"],
        input=wav_bytes,
        capture_output=True,
        timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()}")
    return result.stdout


def generate_audio_mp3(text):
    load_model()
    chunks = chunk_text(text)
    all_audio = []
    silence = np.zeros(int(0.3 * 24000), dtype=np.float32)

    for chunk in chunks:
        if not chunk.strip():
            continue
        out = model.inference(
            text=chunk,
            language="en",
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            temperature=0.2,
            repetition_penalty=10.0,
            top_k=50,
            top_p=0.85,
        )
        all_audio.append(np.array(out["wav"], dtype=np.float32))
        all_audio.append(silence)

    combined = np.concatenate(all_audio) if all_audio else np.array([], dtype=np.float32)

    wav_buf = io.BytesIO()
    sf.write(wav_buf, combined, 24000, format='WAV')
    wav_bytes = wav_buf.getvalue()

    return wav_to_mp3(wav_bytes)


@app.route("/v1/text-to-speech/<voice_id>", methods=["POST"])
def text_to_speech(voice_id):
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "no text"}), 400

    print(f"TTS request: voice={voice_id} text={text[:60]}...", flush=True)

    try:
        mp3_data = generate_audio_mp3(text)
        return Response(mp3_data, mimetype="audio/mpeg",
                       headers={"Content-Type": "audio/mpeg"})
    except Exception as e:
        print(f"Error: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/v1/voices", methods=["GET"])
def voices():
    return jsonify({"voices": [{"voice_id": "jimmy", "name": "Jimmy"}]})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model_loaded": model is not None})


if __name__ == "__main__":
    print("Starting Jimmy TTS server v2 on port 5005...", flush=True)
    load_model()
    app.run(host="0.0.0.0", port=5005, threaded=False)
