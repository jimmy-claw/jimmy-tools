#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Meeting Bot Setup ==="

# --- System packages (need sudo) ---
echo "[1/5] Installing system packages..."
sudo apt-get update
sudo apt-get install -y \
    pulseaudio \
    pulseaudio-utils \
    chromium \
    ffmpeg \
    libportaudio2 \
    python3-venv \
    python3-dev \
    build-essential

# --- Python venv ---
echo "[2/5] Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt

# --- Install Playwright Chromium ---
echo "[3/5] Installing Playwright browsers..."
playwright install chromium
playwright install-deps chromium 2>/dev/null || true

# --- Download Piper TTS model ---
echo "[4/5] Downloading Piper TTS model..."
PIPER_DIR="$SCRIPT_DIR/piper-models"
mkdir -p "$PIPER_DIR"
MODEL_NAME="en_US-amy-medium"
if [ ! -f "$PIPER_DIR/${MODEL_NAME}.onnx" ]; then
    echo "Downloading ${MODEL_NAME}..."
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx" \
        -o "$PIPER_DIR/${MODEL_NAME}.onnx"
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json" \
        -o "$PIPER_DIR/${MODEL_NAME}.onnx.json"
else
    echo "Piper model already downloaded."
fi

# --- Setup virtual audio ---
echo "[5/5] Setting up virtual audio devices..."
bash "$SCRIPT_DIR/virtual_audio.sh" start

echo ""
echo "=== Setup complete ==="
echo "Activate venv: source venv/bin/activate"
echo "Test: python join_meeting.py https://meet.jit.si/test-room"
