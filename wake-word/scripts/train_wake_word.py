#!/usr/bin/env python3
"""
Train a custom wake word model for openWakeWord.

Generates synthetic training data using TTS, augments it, and trains
a small detection model.

This is a simplified local version. For best results, use the official
Colab notebook: https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb

Usage:
    python train_wake_word.py --phrase "hey jimmy" --output models/hey_jimmy.onnx

    # With custom TTS model for generating samples
    python train_wake_word.py \
        --phrase "hey jimmy" \
        --tts-model ~/.local/share/piper/voices/jimmy-voice.onnx \
        --output models/hey_jimmy.onnx
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def generate_positive_samples(phrase, output_dir, num_samples=200, tts_model=None):
    """Generate positive samples (the wake word) using Piper TTS with variations."""
    os.makedirs(output_dir, exist_ok=True)

    # Variations of the phrase for robustness
    variations = [
        phrase,
        phrase + ".",
        phrase + "!",
        phrase + "?",
        phrase.title(),
        phrase.upper(),
    ]

    print(f"Generating {num_samples} positive samples for '{phrase}'...")

    piper_cmd = ["piper", "--output-raw"]
    if tts_model:
        piper_cmd.extend(["--model", tts_model])
    else:
        # Use default Piper model
        piper_cmd.extend(["--model", "en_US-lessac-medium"])

    generated = 0
    for i in range(num_samples):
        text = variations[i % len(variations)]
        output_path = os.path.join(output_dir, f"positive_{i:04d}.wav")

        try:
            # Generate with slight parameter variations for diversity
            result = subprocess.run(
                piper_cmd + ["--output_file", output_path],
                input=text,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                generated += 1
            else:
                print(f"  ✗ Failed sample {i}: {result.stderr[:100]}")
        except Exception as e:
            print(f"  ✗ Error on sample {i}: {e}")

    print(f"  Generated {generated}/{num_samples} positive samples")
    return generated


def generate_negative_samples(output_dir, num_samples=500):
    """
    Generate negative samples (things that are NOT the wake word).

    For proper training, you need diverse negative examples:
    - General speech
    - Similar-sounding phrases
    - Silence / noise

    This is a simplified version. The Colab notebook uses proper
    noise datasets and room impulse responses.
    """
    os.makedirs(output_dir, exist_ok=True)

    negative_phrases = [
        "hello there",
        "hey",
        "hey buddy",
        "hey siri",
        "hey google",
        "okay",
        "hi there",
        "hey timmy",
        "hey jenny",
        "hey kimmy",
        "good morning",
        "what's up",
        "the weather today",
        "turn on the lights",
        "play some music",
        "set a timer",
        "remind me later",
        "check the calendar",
        "how are you",
        "tell me a joke",
        "what time is it",
        "send a message",
        "open the door",
        "close the window",
        "start the car",
    ]

    print(f"Generating {num_samples} negative samples...")

    generated = 0
    for i in range(num_samples):
        text = negative_phrases[i % len(negative_phrases)]
        output_path = os.path.join(output_dir, f"negative_{i:04d}.wav")

        try:
            result = subprocess.run(
                ["piper", "--model", "en_US-lessac-medium",
                 "--output_file", output_path],
                input=text,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                generated += 1
        except Exception:
            pass

    print(f"  Generated {generated}/{num_samples} negative samples")
    return generated


def main():
    parser = argparse.ArgumentParser(description="Train custom wake word model")
    parser.add_argument("--phrase", type=str, default="hey jimmy",
                        help="Wake word phrase")
    parser.add_argument("--output", type=str, default="models/hey_jimmy.onnx",
                        help="Output model path")
    parser.add_argument("--tts-model", type=str, default=None,
                        help="Custom Piper TTS model for generating samples")
    parser.add_argument("--positive-samples", type=int, default=200,
                        help="Number of positive samples")
    parser.add_argument("--negative-samples", type=int, default=500,
                        help="Number of negative samples")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        pos_dir = os.path.join(tmpdir, "positive")
        neg_dir = os.path.join(tmpdir, "negative")

        # Step 1: Generate training data
        print(f"\n🎤 Training wake word model for: '{args.phrase}'")
        print("=" * 50)

        n_pos = generate_positive_samples(
            args.phrase, pos_dir, args.positive_samples, args.tts_model
        )
        n_neg = generate_negative_samples(neg_dir, args.negative_samples)

        if n_pos < 10:
            print("❌ Not enough positive samples. Check that Piper is installed.")
            sys.exit(1)

        # Step 2: Train
        print(f"\n🏋️ Training model...")
        print("   NOTE: For production-quality models, use the Colab notebook:")
        print("   https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb")
        print()

        try:
            # Use openWakeWord's training utilities
            from openwakeword.train import train_model

            train_model(
                positive_dir=pos_dir,
                negative_dir=neg_dir,
                output_path=args.output,
                # Training params
                epochs=100,
                batch_size=32,
            )
            print(f"\n✅ Model saved to: {args.output}")
            print(f"\nTest with:")
            print(f"  python detect.py --model {args.output}")

        except ImportError:
            print("❌ openWakeWord training utilities not available.")
            print("   The training API may require additional setup.")
            print()
            print("Recommended: Use the official Colab notebook instead:")
            print("  1. Upload the generated samples from this script")
            print("  2. Follow the notebook to train the model")
            print("  3. Download the .onnx model")
            print()
            print(f"Samples saved to: {tmpdir}")
            print("  (Copy them before this script exits!)")
            input("Press Enter to exit...")

        except Exception as e:
            print(f"❌ Training failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
