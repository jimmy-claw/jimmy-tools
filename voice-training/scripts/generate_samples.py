#!/usr/bin/env python3
"""
Generate voice samples using Qwen3-TTS for Piper fine-tuning.

Supports two modes:
1. Voice Design — describe Jimmy's voice in natural language (no reference audio needed)
2. Voice Cloning — clone from a reference audio clip (3+ seconds)

Usage:
    # Voice design mode (recommended for creating Jimmy's unique voice)
    python generate_samples.py \
        --mode design \
        --voice-description "A warm, friendly male voice with a slight Irish accent" \
        --corpus corpus.txt \
        --output-dir samples/

    # Voice cloning mode (clone an existing voice)
    python generate_samples.py \
        --mode clone \
        --reference-audio reference.wav \
        --corpus corpus.txt \
        --output-dir samples/
"""

import argparse
import os
import json
import time
import soundfile as sf
import torch
from pathlib import Path


def load_model(mode="design"):
    """Load the appropriate Qwen3-TTS model."""
    from transformers import AutoModelForCausalLM, AutoTokenizer, AutoProcessor

    if mode == "design":
        model_name = "Qwen/Qwen3-TTS-12Hz-0.6B-VoiceDesign"
    else:
        model_name = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

    print(f"Loading model: {model_name}")
    print("This may take a few minutes on first run (downloading weights)...")

    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        trust_remote_code=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",
    )

    return model, processor


def generate_design(model, processor, text, voice_description, output_path):
    """Generate speech using voice design mode."""
    messages = [
        {"role": "system", "content": f"You are a speech synthesizer. Voice: {voice_description}"},
        {"role": "user", "content": text},
    ]

    inputs = processor(messages, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=2048,
            temperature=0.7,
            do_sample=True,
        )

    audio = processor.decode_audio(outputs[0])
    sf.write(output_path, audio, samplerate=24000)
    return len(audio) / 24000  # duration in seconds


def generate_clone(model, processor, text, reference_audio, output_path):
    """Generate speech using voice cloning mode."""
    messages = [
        {"role": "system", "content": "You are a speech synthesizer. Clone the provided voice."},
        {"role": "user", "content": text},
    ]

    inputs = processor(
        messages,
        audio=reference_audio,
        return_tensors="pt",
    ).to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=2048,
            temperature=0.7,
            do_sample=True,
        )

    audio = processor.decode_audio(outputs[0])
    sf.write(output_path, audio, samplerate=24000)
    return len(audio) / 24000


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
                        default="A warm, friendly male voice with a slight Irish accent. Clear, articulate, and confident.",
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
    model, processor = load_model(args.mode)

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
            if args.mode == "design":
                duration = generate_design(model, processor, text, args.voice_description, output_path)
            else:
                duration = generate_clone(model, processor, text, reference_audio, output_path)

            total_duration += duration
            manifest.append({
                "id": f"sample_{i:04d}",
                "file": filename,
                "text": text,
                "duration": round(duration, 2),
            })
            print(f"  → {duration:.1f}s audio")

        except Exception as e:
            print(f"  ✗ Failed: {e}")
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

    print(f"\n✅ Done! Generated {len(manifest)} samples ({total_duration:.0f}s total audio)")
    print(f"   Time: {time.time() - start_time:.0f}s")
    print(f"   Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
