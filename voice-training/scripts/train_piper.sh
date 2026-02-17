#!/usr/bin/env bash
#
# Fine-tune Piper TTS with a custom voice dataset.
#
# Uses the piper-train Docker image for reproducible training.
# Alternatively can run locally with piper-phonemize + training scripts.
#
# Usage:
#   ./train_piper.sh <dataset_dir> <output_dir> [epochs]
#
# Example:
#   ./train_piper.sh dataset/ models/jimmy-voice 1000
#
# Prerequisites:
#   - Docker installed
#   - Dataset prepared in LJSpeech format (run prepare_dataset.py first)
#   - ~4GB disk space for training artifacts

set -euo pipefail

DATASET_DIR="${1:?Usage: $0 <dataset_dir> <output_dir> [epochs]}"
OUTPUT_DIR="${2:?Usage: $0 <dataset_dir> <output_dir> [epochs]}"
EPOCHS="${3:-1000}"

DATASET_DIR="$(realpath "$DATASET_DIR")"
OUTPUT_DIR="$(realpath "$OUTPUT_DIR")"
mkdir -p "$OUTPUT_DIR"

CHECKPOINT_URL="https://huggingface.co/datasets/rhasspy/piper-checkpoints/resolve/main/en/en_US/lessac/medium/epoch=2164-step=1355540.ckpt"
CHECKPOINT_FILE="$OUTPUT_DIR/base-checkpoint.ckpt"

echo "🎤 Piper TTS Fine-Tuning"
echo "========================"
echo "  Dataset:    $DATASET_DIR"
echo "  Output:     $OUTPUT_DIR"
echo "  Epochs:     $EPOCHS"
echo ""

# ── Step 1: Download base checkpoint ──────────────────────────────

if [ ! -f "$CHECKPOINT_FILE" ]; then
    echo "📥 Downloading base checkpoint (en_US-lessac-medium)..."
    wget -q --show-progress -O "$CHECKPOINT_FILE" "$CHECKPOINT_URL"
else
    echo "✅ Base checkpoint exists"
fi

# ── Step 2: Check for Docker or local training ────────────────────

if command -v docker &>/dev/null; then
    echo ""
    echo "🐳 Using Docker for training..."

    # Check if piper-train image exists, build if not
    if ! docker image inspect piper-train &>/dev/null 2>&1; then
        echo "Building piper-train Docker image..."
        # Use the community Dockerfile
        TMP_DIR=$(mktemp -d)
        cat > "$TMP_DIR/Dockerfile" << 'DOCKERFILE'
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libsndfile1 \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    piper-phonemize \
    pytorch-lightning==1.9.5 \
    torch \
    torchaudio \
    librosa \
    numpy \
    matplotlib

RUN git clone https://github.com/rhasspy/piper.git /opt/piper

WORKDIR /opt/piper/src/python
RUN pip install -e .

WORKDIR /workspace
DOCKERFILE
        docker build -t piper-train "$TMP_DIR"
        rm -rf "$TMP_DIR"
    fi

    # ── Step 3: Preprocess dataset ────────────────────────────────

    echo ""
    echo "🔄 Preprocessing dataset..."

    docker run --rm \
        -v "$DATASET_DIR:/dataset" \
        -v "$OUTPUT_DIR:/output" \
        piper-train \
        python -m piper_train.preprocess \
            --language en \
            --input-dir /dataset \
            --output-dir /output/training \
            --dataset-format ljspeech \
            --single-speaker \
            --sample-rate 22050

    # ── Step 4: Train ─────────────────────────────────────────────

    echo ""
    echo "🏋️ Training for $EPOCHS epochs..."
    echo "   This will take a while. Check $OUTPUT_DIR/training/ for progress."

    GPU_FLAG=""
    if command -v nvidia-smi &>/dev/null; then
        GPU_FLAG="--gpus all"
    fi

    docker run --rm $GPU_FLAG \
        -v "$OUTPUT_DIR:/output" \
        piper-train \
        python -m piper_train \
            --dataset-dir /output/training \
            --accelerator gpu \
            --devices 1 \
            --batch-size 16 \
            --validation-split 0.0 \
            --num-test-examples 0 \
            --max_epochs "$EPOCHS" \
            --resume_from_checkpoint /output/base-checkpoint.ckpt \
            --checkpoint-epochs 100 \
            --precision 32

    # ── Step 5: Export to ONNX ────────────────────────────────────

    echo ""
    echo "📦 Exporting to ONNX..."

    # Find the latest checkpoint
    LATEST_CKPT=$(ls -t "$OUTPUT_DIR/training/lightning_logs/version_0/checkpoints/"*.ckpt 2>/dev/null | head -1)

    if [ -z "$LATEST_CKPT" ]; then
        echo "❌ No training checkpoint found!"
        exit 1
    fi

    docker run --rm \
        -v "$OUTPUT_DIR:/output" \
        piper-train \
        python -m piper_train.export_onnx \
            "/output/training/lightning_logs/version_0/checkpoints/$(basename "$LATEST_CKPT")" \
            /output/jimmy-voice.onnx

    echo ""
    echo "✅ Training complete!"
    echo "   Model: $OUTPUT_DIR/jimmy-voice.onnx"
    echo ""
    echo "Test with:"
    echo "   echo 'Hello, I am Jimmy!' | piper --model $OUTPUT_DIR/jimmy-voice.onnx --output_file test.wav"

else
    echo ""
    echo "❌ Docker not found. Install Docker or use the manual training steps:"
    echo "   See: https://github.com/rhasspy/piper/blob/master/TRAINING.md"
    echo ""
    echo "Or use Google Colab:"
    echo "   1. Upload dataset/ to Colab"
    echo "   2. Follow the Piper training notebook"
    echo "   3. Download the .onnx model"
    exit 1
fi
