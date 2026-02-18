#!/usr/bin/env python3
"""
Generate voice samples using Qwen3-TTS for Piper fine-tuning.

Supports two modes:
1. Voice Design — describe the voice in natural language (no reference audio needed)
2. Voice Cloning — clone from a reference audio clip (3+ seconds)

Usage:
    # Voice design mode
    python generate_samples.py \
        --mode design \
        --voice-description "A warm, friendly male voice with a slight Scottish accent. Clear and articulate." \
        --max-samples 300 \
        --output-dir samples/

    # Voice cloning mode
    python generate_samples.py \
        --mode clone \
        --reference-audio reference.wav \
        --max-samples 300 \
        --output-dir samples/
"""

import argparse
import os
import json
import time
import soundfile as sf
from pathlib import Path


def load_model(mode="design"):
    """Load the appropriate Qwen3-TTS model via qwen-tts package."""
    try:
        from qwen_tts import Qwen3TTSModel
    except ImportError:
        print("Installing qwen-tts...")
        os.system("pip install -U qwen-tts")
        from qwen_tts import Qwen3TTSModel

    import torch

    if mode == "design":
        model_name = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
    else:
        model_name = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"

    print(f"Loading model: {model_name}")
    print("This may take a few minutes on first run (downloading weights)...")

    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    device = "cuda:0" if torch.cuda.is_available() else "cpu"

    model = Qwen3TTSModel.from_pretrained(
        model_name,
        device_map=device,
        dtype=dtype,
    )
    return model


def generate_sample(model, text, output_path, voice_description=None, reference_audio=None, mode="design"):
    """Generate a single speech sample."""
    if mode == "design":
        # VoiceDesign: speaker is a name, instruct describes the voice character
        wavs, sr = model.generate_custom_voice(
            text=text,
            language="English",
            speaker="Jimmy",
            instruct=voice_description,
        )
    else:
        # CustomVoice: clone from reference audio
        wavs, sr = model.generate_custom_voice(
            text=text,
            language="English",
            speaker="Jimmy",
            instruct="Clone the voice from the reference audio exactly.",
            reference_audio=reference_audio,
        )

    sf.write(output_path, wavs[0], sr)
    return len(wavs[0]) / sr  # duration in seconds


def load_corpus(corpus_path):
    """Load text lines from corpus file, skipping comments and blanks."""
    lines = []
    with open(corpus_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
    return lines


def main():
    parser = argparse.ArgumentParser(description="Generate voice samples with Qwen3-TTS")
    parser.add_argument("--mode", choices=["design", "clone"], default="design",
                        help="Voice design (from description) or voice cloning (from reference)")
    parser.add_argument("--voice-description", type=str,
                        default="A warm, friendly male voice with a slight Scottish accent. Clear, articulate, and confident.",
                        help="Voice description for design mode")
    parser.add_argument("--reference-audio", type=str, help="Reference WAV for clone mode")
    parser.add_argument("--corpus", type=str, default="corpus.txt", help="Text corpus file")
    parser.add_argument("--output-dir", type=str, default="samples/", help="Output directory")
    parser.add_argument("--start-from", type=int, default=0, help="Resume from sample N")
    parser.add_argument("--max-samples", type=int, default=None, help="Max samples to generate")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Load corpus
    lines = load_corpus(args.corpus)
    if args.max_samples:
        lines = lines[:args.max_samples]
    print(f"Loaded {len(lines)} text lines from {args.corpus}")

    # Load reference audio if cloning
    reference_audio = None
    if args.mode == "clone":
        if not args.reference_audio:
            print("ERROR: --reference-audio required for clone mode")
            return
        import librosa
        reference_audio, _ = librosa.load(args.reference_audio, sr=24000)
        print(f"Loaded reference audio: {len(reference_audio)/24000:.1f}s")

    # Load model
    model = load_model(args.mode)

    # Generate samples
    manifest = []
    total_duration = 0
    start_time = time.time()

    for i, text in enumerate(lines):
        if i < args.start_from:
            continue

        filename = f"sample_{i:04d}.wav"
        output_path = os.path.join(args.output_dir, filename)

        print(f"[{i+1}/{len(lines)}] Generating: {text[:60]}...")

        try:
            duration = generate_sample(
                model, text, output_path,
                voice_description=args.voice_description,
                reference_audio=reference_audio,
                mode=args.mode,
            )

            total_duration += duration
            manifest.append({
                "id": f"sample_{i:04d}",
                "file": filename,
                "text": text,
                "duration": round(duration, 2),
            })
            print(f"  -> {duration:.1f}s audio")

        except Exception as e:
            print(f"  Failed: {e}")
            continue

    # Save manifest
    manifest_path = os.path.join(args.output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump({
            "mode": args.mode,
            "voice_description": args.voice_description if args.mode == "design" else None,
            "reference_audio": args.reference_audio if args.mode == "clone" else None,
            "total_samples": len(manifest),
            "total_duration_seconds": round(total_duration, 1),
            "generation_time_seconds": round(time.time() - start_time, 1),
            "samples": manifest,
        }, f, indent=2)

    print(f"\nDone! Generated {len(manifest)} samples ({total_duration:.0f}s total audio)")
    print(f"   Time: {time.time() - start_time:.0f}s")
    print(f"   Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
