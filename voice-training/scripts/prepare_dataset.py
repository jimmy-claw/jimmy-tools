#!/usr/bin/env python3
"""
Prepare generated voice samples for Piper TTS fine-tuning.

Converts samples + manifest into LJSpeech format expected by Piper:
  - WAV files at 22050 Hz, mono, 16-bit
  - metadata.csv with: filename|text|normalized_text

Usage:
    python prepare_dataset.py --samples-dir samples/ --output-dir dataset/
"""

import argparse
import csv
import json
import os
import re
from pathlib import Path

try:
    from pydub import AudioSegment
except ImportError:
    print("pip install pydub")
    exit(1)


def normalize_text(text):
    """Basic text normalization for Piper training."""
    # Expand common abbreviations
    text = re.sub(r'\bAM\b', 'A M', text)
    text = re.sub(r'\bPM\b', 'P M', text)
    text = re.sub(r'\bAPI\b', 'A P I', text)
    text = re.sub(r'\bURL\b', 'U R L', text)
    text = re.sub(r'\bSSH\b', 'S S H', text)
    text = re.sub(r'\bTTS\b', 'T T S', text)
    text = re.sub(r'\bIDL\b', 'I D L', text)
    text = re.sub(r'\bCLI\b', 'C L I', text)
    text = re.sub(r'\bRAM\b', 'ram', text)
    text = re.sub(r'\bONNX\b', 'onyx', text)

    # Remove special characters but keep basic punctuation
    text = re.sub(r'[^\w\s.,!?\'"-]', '', text)

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def convert_audio(input_path, output_path, target_sr=22050):
    """Convert audio to Piper-compatible format: 22050 Hz, mono, 16-bit WAV."""
    audio = AudioSegment.from_file(input_path)

    # Convert to mono
    audio = audio.set_channels(1)

    # Resample to 22050 Hz
    audio = audio.set_frame_rate(target_sr)

    # Set to 16-bit
    audio = audio.set_sample_width(2)

    # Trim silence from start/end (optional but helps quality)
    from pydub.silence import detect_leading_silence
    start_trim = detect_leading_silence(audio, silence_threshold=-40)
    end_trim = detect_leading_silence(audio.reverse(), silence_threshold=-40)
    audio = audio[start_trim:len(audio) - end_trim]

    audio.export(output_path, format="wav")

    return len(audio) / 1000  # duration in seconds


def main():
    parser = argparse.ArgumentParser(description="Prepare dataset for Piper fine-tuning")
    parser.add_argument("--samples-dir", type=str, default="samples/",
                        help="Directory with generated WAV samples")
    parser.add_argument("--output-dir", type=str, default="dataset/",
                        help="Output directory in LJSpeech format")
    parser.add_argument("--min-duration", type=float, default=1.0,
                        help="Minimum sample duration in seconds")
    parser.add_argument("--max-duration", type=float, default=15.0,
                        help="Maximum sample duration in seconds")
    parser.add_argument("--verify-with-whisper", action="store_true",
                        help="Verify transcriptions with Whisper (slower but more accurate)")
    args = parser.parse_args()

    wavs_dir = os.path.join(args.output_dir, "wavs")
    os.makedirs(wavs_dir, exist_ok=True)

    # Load manifest
    manifest_path = os.path.join(args.samples_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"ERROR: No manifest.json found in {args.samples_dir}")
        print("Run generate_samples.py first.")
        return

    with open(manifest_path) as f:
        manifest = json.load(f)

    samples = manifest["samples"]
    print(f"Processing {len(samples)} samples...")

    # Optional Whisper verification
    whisper_model = None
    if args.verify_with_whisper:
        try:
            import whisper
            print("Loading Whisper for transcription verification...")
            whisper_model = whisper.load_model("tiny")
        except ImportError:
            print("WARNING: whisper not installed, skipping verification")

    # Process samples
    metadata = []
    skipped = 0
    total_duration = 0

    for sample in samples:
        input_path = os.path.join(args.samples_dir, sample["file"])
        if not os.path.exists(input_path):
            print(f"  ✗ Missing: {sample['file']}")
            skipped += 1
            continue

        # Convert audio
        output_filename = sample["id"] + ".wav"
        output_path = os.path.join(wavs_dir, output_filename)
        duration = convert_audio(input_path, output_path)

        # Filter by duration
        if duration < args.min_duration or duration > args.max_duration:
            os.remove(output_path)
            print(f"  ✗ Skipped {sample['id']}: {duration:.1f}s (outside {args.min_duration}-{args.max_duration}s)")
            skipped += 1
            continue

        text = sample["text"]
        normalized = normalize_text(text)

        # Optional Whisper verification
        if whisper_model:
            result = whisper_model.transcribe(output_path, language="en")
            whisper_text = result["text"].strip()
            # Simple similarity check
            if len(whisper_text) < len(text) * 0.5:
                print(f"  ⚠ Poor transcription match for {sample['id']}, keeping original")

        metadata.append({
            "id": sample["id"],
            "text": text,
            "normalized": normalized,
            "duration": duration,
        })
        total_duration += duration

    # Write metadata.csv (LJSpeech format: id|text|normalized_text)
    metadata_path = os.path.join(args.output_dir, "metadata.csv")
    with open(metadata_path, "w", newline="") as f:
        writer = csv.writer(f, delimiter="|")
        for entry in metadata:
            writer.writerow([entry["id"], entry["text"], entry["normalized"]])

    # Write dataset info
    info = {
        "name": "jimmy-voice",
        "language": "en",
        "total_samples": len(metadata),
        "total_duration_seconds": round(total_duration, 1),
        "total_duration_minutes": round(total_duration / 60, 1),
        "skipped": skipped,
        "sample_rate": 22050,
        "format": "LJSpeech",
    }
    with open(os.path.join(args.output_dir, "dataset_info.json"), "w") as f:
        json.dump(info, f, indent=2)

    print(f"\n✅ Dataset prepared!")
    print(f"   Samples: {len(metadata)} ({total_duration/60:.1f} minutes)")
    print(f"   Skipped: {skipped}")
    print(f"   Output: {args.output_dir}")
    print(f"   Metadata: {metadata_path}")


if __name__ == "__main__":
    main()
