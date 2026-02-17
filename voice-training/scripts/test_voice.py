#!/usr/bin/env python3
"""
Test a trained Piper voice model.

Generates test audio from various sentences and saves them for review.

Usage:
    python test_voice.py --model models/jimmy-voice.onnx --output-dir test_output/

    # Or with piper CLI directly:
    echo "Hello, I'm Jimmy!" | piper --model models/jimmy-voice.onnx --output_file test.wav
"""

import argparse
import os
import subprocess
import sys

TEST_SENTENCES = [
    "Hello! I'm Jimmy, your AI assistant.",
    "The deployment was successful. All systems are running normally.",
    "Could you tell me more about the delivery options for this item?",
    "That's a brilliant idea! Let me start working on it right away.",
    "I'm sorry, but I don't think that approach will work. Here's an alternative.",
    "The transaction has been confirmed and included in block four thousand two hundred.",
    "Good morning! The weather today is twelve degrees with partly cloudy skies.",
    "I've found three issues in the code review that we should discuss.",
    "Three hundred and fifty Czech crowns for the RAM module sounds reasonable.",
    "Let me check the server status. One moment please.",
]


def main():
    parser = argparse.ArgumentParser(description="Test a Piper voice model")
    parser.add_argument("--model", type=str, required=True, help="Path to .onnx model")
    parser.add_argument("--output-dir", type=str, default="test_output/", help="Output directory")
    parser.add_argument("--play", action="store_true", help="Play audio after generation (requires aplay)")
    args = parser.parse_args()

    if not os.path.exists(args.model):
        print(f"❌ Model not found: {args.model}")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    # Check piper is available
    try:
        subprocess.run(["piper", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        print("❌ piper not found. Install with: pip install piper-tts")
        sys.exit(1)

    print(f"🎤 Testing voice model: {args.model}")
    print(f"   Output: {args.output_dir}")
    print()

    for i, text in enumerate(TEST_SENTENCES):
        output_path = os.path.join(args.output_dir, f"test_{i:02d}.wav")
        print(f"  [{i+1}/{len(TEST_SENTENCES)}] {text[:60]}...")

        result = subprocess.run(
            ["piper", "--model", args.model, "--output_file", output_path],
            input=text,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"    ✗ Failed: {result.stderr.strip()}")
            continue

        print(f"    → {output_path}")

        if args.play:
            subprocess.run(["aplay", output_path], capture_output=True)

    print(f"\n✅ Generated {len(TEST_SENTENCES)} test samples in {args.output_dir}")
    print("Listen to them and iterate on the training if needed!")


if __name__ == "__main__":
    main()
