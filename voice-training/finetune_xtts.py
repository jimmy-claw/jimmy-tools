#!/usr/bin/env python3
"""
XTTS v2 fine-tuning for Jimmy's voice.
Uses the official XTTS trainer recipe.

Run: python3 finetune_xtts.py
"""

import os
import sys

os.environ["COQUI_TOS_AGREED"] = "1"

from trainer import Trainer, TrainerArgs
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

# Paths
MODEL_DIR = os.path.expanduser(
    "~/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2"
)
TRAINING_DATA = os.path.expanduser(
    "~/jimmy-tools/voice-training/training_data"
)
OUTPUT_DIR = os.path.expanduser(
    "~/jimmy-tools/voice-training/jimmy_model"
)

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load base config from pretrained model
config = XttsConfig()
config.load_json(os.path.join(MODEL_DIR, "config.json"))

# Override training settings
config.output_path = OUTPUT_DIR
config.epochs = 10
config.batch_size = 2
config.eval_batch_size = 2
config.num_loader_workers = 2
config.print_step = 5
config.save_step = 100
config.save_n_checkpoints = 2
config.save_checkpoints = True
config.run_eval = False  # skip eval to avoid complexity
config.test_delay_epochs = -1

# Build sample list manually from metadata.csv
import csv

def load_samples(data_dir, metadata_file="metadata.csv"):
    samples = []
    wavs_dir = os.path.join(data_dir, "wavs")
    with open(os.path.join(data_dir, metadata_file), newline="") as f:
        reader = csv.reader(f, delimiter="|")
        for row in reader:
            if len(row) < 2:
                continue
            filename, text = row[0], row[1]
            wav_path = os.path.join(wavs_dir, f"{filename}.wav")
            if os.path.exists(wav_path):
                samples.append({
                    "audio_file": wav_path,
                    "text": text,
                    "speaker_name": "jimmy",
                    "language": "en",
                    "root_path": data_dir,
                })
    return samples

all_samples = load_samples(TRAINING_DATA)
print(f"Loaded {len(all_samples)} samples")

# Split 90/10
split = int(len(all_samples) * 0.9)
train_samples = all_samples[:split]
eval_samples = all_samples[split:]
print(f"Train: {len(train_samples)}, Eval: {len(eval_samples)}")

# Init model
model = Xtts.init_from_config(config)
model.load_checkpoint(
    config,
    checkpoint_dir=MODEL_DIR,
    eval=False,
)
print("Model loaded. Starting fine-tuning...")

# Train
trainer = Trainer(
    TrainerArgs(restore_path=None, skip_train_epoch=False),
    config,
    output_path=OUTPUT_DIR,
    model=model,
    train_samples=train_samples,
    eval_samples=eval_samples,
)

trainer.fit()
print(f"\nDone! Model saved to {OUTPUT_DIR}")
