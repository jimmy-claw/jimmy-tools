#!/usr/bin/env python3
"""STT server using faster-whisper. Accepts audio via HTTP POST, returns transcript.

Endpoints:
    POST /transcribe  - multipart/form-data with 'audio' file field
                       Optional query params: language (default: en), model (default: medium)
    GET  /health      - Health check

Usage:
    python stt_server.py [--host 0.0.0.0] [--port 5006] [--model medium]

Note: If firewall blocks port 5006, open it:
    sudo firewall-cmd --add-port=5006/tcp --permanent && sudo firewall-cmd --reload
Or use SSH tunnel from client:
    ssh -L 5006:127.0.0.1:5006 jimmy@192.168.0.125 -N
"""

import argparse
import io
import os
import tempfile
import time

from flask import Flask, request, jsonify

app = Flask(__name__)
whisper_model = None


def get_model():
    global whisper_model
    if whisper_model is None:
        from faster_whisper import WhisperModel
        model_size = os.environ.get("STT_MODEL", "medium")
        print(f"[stt] Loading faster-whisper model: {model_size}", flush=True)
        whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
        print(f"[stt] Model ready", flush=True)
    return whisper_model


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model_loaded": whisper_model is not None})


@app.route("/transcribe", methods=["POST"])
def transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "No 'audio' file in request"}), 400

    audio_file = request.files["audio"]
    language = request.args.get("language", "en")

    # Save to temp file (faster-whisper needs a file path)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        audio_file.save(f)
        tmp_path = f.name

    try:
        t0 = time.time()
        model = get_model()
        segments, info = model.transcribe(tmp_path, language=language)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        elapsed = time.time() - t0
        print(f"[stt] Transcribed {info.duration:.1f}s audio in {elapsed:.1f}s: {text[:80]}", flush=True)
        return jsonify({
            "text": text,
            "language": info.language,
            "duration": info.duration,
            "processing_time": elapsed,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5006)
    parser.add_argument("--model", default="medium")
    args = parser.parse_args()
    os.environ["STT_MODEL"] = args.model
    # Pre-load model
    get_model()
    app.run(host=args.host, port=args.port)
