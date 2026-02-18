#!/usr/bin/env python3
"""
Jimmy TTS - XTTS v2 voice synthesis with auto-chunking
Usage: python3 jimmy_tts.py "Your text here" output.wav
       echo "Your text" | python3 jimmy_tts.py - output.wav
"""

import sys
import os
import re
import tempfile
import subprocess
import soundfile as sf
import numpy as np

COQUI_TOS_AGREED = "1"
os.environ["COQUI_TOS_AGREED"] = COQUI_TOS_AGREED

MODEL_DIR = os.path.expanduser(
    "~/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2"
)
REFERENCE_CLIP = "/tmp/jamie_fraser_clean.wav"
DENOISED_CLIP = "/tmp/jamie_fraser_denoised.wav"
MAX_CHARS = 230  # safe limit under 250


def denoise_reference():
    if not os.path.exists(DENOISED_CLIP):
        print("Denoising reference clip...", file=sys.stderr)
        subprocess.run([
            "ffmpeg", "-y", "-i", REFERENCE_CLIP,
            "-af", "anlmdn=s=0.0001:p=0.002:r=0.002",
            DENOISED_CLIP
        ], check=True, capture_output=True)
    return DENOISED_CLIP


def split_text(text, max_chars=MAX_CHARS):
    """Split text at sentence boundaries, keeping chunks under max_chars."""
    # Split on sentence-ending punctuation
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            # Split long sentence at commas/semicolons
            parts = re.split(r'(?<=[,;])\s+', sentence)
            for part in parts:
                if len(current) + len(part) + 1 <= max_chars:
                    current = (current + " " + part).strip()
                else:
                    if current:
                        chunks.append(current)
                    current = part
        elif len(current) + len(sentence) + 1 <= max_chars:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def load_model():
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    import torch

    device = os.environ.get("JIMMY_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
    print(f"Loading XTTS model on {device}...", file=sys.stderr)
    config = XttsConfig()
    config.load_json(os.path.join(MODEL_DIR, "config.json"))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=MODEL_DIR, eval=True)
    model.to(device)
    return model, device


def synthesize(text, output_path, volume=2.0):
    reference = denoise_reference()
    model, device = load_model()

    print(f"Computing speaker embedding on {device}...", file=sys.stderr)
    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=[reference]
    )

    chunks = split_text(text)
    print(f"Generating {len(chunks)} chunk(s)...", file=sys.stderr)

    audio_parts = []
    silence = np.zeros(int(24000 * 0.3))  # 0.3s silence between chunks

    for i, chunk in enumerate(chunks):
        print(f"  [{i+1}/{len(chunks)}] {chunk[:60]}...", file=sys.stderr)
        out = model.inference(
            chunk, "en",
            gpt_cond_latent, speaker_embedding,
            temperature=0.2,
            repetition_penalty=10.0,
            top_k=50,
            top_p=0.85,
        )
        audio_parts.append(np.array(out["wav"]))
        if i < len(chunks) - 1:
            audio_parts.append(silence)

    combined = np.concatenate(audio_parts)

    # Write to temp, then boost volume with ffmpeg
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    sf.write(tmp_path, combined, 24000)

    subprocess.run([
        "ffmpeg", "-y", "-i", tmp_path,
        "-af", f"volume={volume}",
        output_path
    ], check=True, capture_output=True)
    os.unlink(tmp_path)

    print(f"Done! Saved to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <text|-> <output.wav>")
        sys.exit(1)

    text_arg = sys.argv[1]
    output_arg = sys.argv[2]

    if text_arg == "-":
        text = sys.stdin.read().strip()
    else:
        text = text_arg

    synthesize(text, output_arg)
