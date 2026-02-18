#!/usr/bin/env python3
"""
XTTS v2 fine-tuning script for Jimmy's voice.
Uses the 85 generated training samples.

Run: python3 finetune_xtts.py
"""

import os

os.environ["COQUI_TOS_AGREED"] = "1"

from trainer import Trainer, TrainerArgs
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.datasets import load_tts_samples
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

# Load base config
config = XttsConfig()
config.load_json(os.path.join(MODEL_DIR, "config.json"))

# Fine-tuning overrides
config.output_path = OUTPUT_DIR
config.epochs = 10
config.batch_size = 2
config.eval_batch_size = 2
config.num_loader_workers = 2
config.eval_split_size = 0.1
config.print_step = 5
config.save_step = 50
config.save_n_checkpoints = 2
config.save_checkpoints = True
config.run_eval = True
config.test_delay_epochs = -1

# Dataset config — LJSpeech-style (filename|text)
config.datasets = [
    {
        "formatter": "ljspeech",
        "dataset_name": "jimmy",
        "path": TRAINING_DATA,
        "meta_file_train": "metadata.csv",
        "language": "en",
    }
]

# Load samples
train_samples, eval_samples = load_tts_samples(
    config.datasets,
    eval_split=True,
    eval_split_size=config.eval_split_size,
)

print(f"Train samples: {len(train_samples)}, Eval samples: {len(eval_samples)}")

# Init model from pretrained
model = Xtts.init_from_config(config)
model.load_checkpoint(
    config,
    checkpoint_dir=MODEL_DIR,
    eval=False,
)

# Trainer
trainer = Trainer(
    TrainerArgs(
        restore_path=None,
        skip_train_epoch=False,
    ),
    config,
    output_path=OUTPUT_DIR,
    model=model,
    train_samples=train_samples,
    eval_samples=eval_samples,
)

trainer.fit()
print(f"\nFine-tuning done! Model saved to {OUTPUT_DIR}")
