# Jimmy Voice Training

Custom TTS voice for Jimmy using Qwen3-TTS → Piper fine-tuning pipeline.

## Overview

1. **Generate samples** — Use Qwen3-TTS to create 200-500 voice samples with a consistent character
2. **Prepare dataset** — Convert to LJSpeech format for Piper training
3. **Fine-tune Piper** — Train from `en_US-lessac-medium` checkpoint
4. **Deploy** — Drop ONNX model on Pi5, real-time CPU inference

## Hardware Requirements

- **Sample generation (Qwen3-TTS):** GPU with 4GB+ VRAM, or GMKTec K11 (Radeon 780M + ROCm)
- **Piper fine-tuning:** GPU with 4GB+ VRAM (same machine)
- **Inference:** Any CPU (Pi5 ARM64 works great)

## Quick Start

```bash
# 1. Install dependencies (on GPU machine)
pip install -r requirements.txt

# 2. Generate voice samples with Qwen3-TTS
python scripts/generate_samples.py \
  --voice-description "A warm, friendly male voice with a slight Irish accent. Clear and articulate." \
  --num-samples 300 \
  --output-dir samples/

# 3. Prepare dataset for Piper
python scripts/prepare_dataset.py \
  --samples-dir samples/ \
  --output-dir dataset/

# 4. Fine-tune Piper (uses Docker)
./scripts/train_piper.sh dataset/ models/jimmy-voice

# 5. Copy model to Pi5
scp models/jimmy-voice.onnx pi5:~/.local/share/piper/voices/
```

## Directory Structure

```
voice-training/
├── scripts/
│   ├── generate_samples.py   # Qwen3-TTS sample generation
│   ├── prepare_dataset.py    # Convert to LJSpeech format
│   ├── train_piper.sh        # Piper fine-tuning via Docker
│   └── test_voice.py         # Test generated voice
├── samples/                  # Generated WAV files (gitignored)
├── dataset/                  # LJSpeech-formatted training data (gitignored)
├── models/                   # Trained Piper models (gitignored)
├── corpus.txt                # Text corpus for sample generation
└── requirements.txt
```
