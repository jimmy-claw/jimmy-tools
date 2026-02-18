#!/usr/bin/env python3
"""
XTTS v2 fine-tuning for Jimmy's voice.
Based on the official Coqui recipe using GPTTrainer.

Run: python3 finetune_xtts.py
"""

import os
import csv

os.environ["COQUI_TOS_AGREED"] = "1"

from trainer import Trainer, TrainerArgs
from TTS.config.shared_configs import BaseDatasetConfig
from TTS.tts.datasets import load_tts_samples
from TTS.tts.layers.xtts.trainer.gpt_trainer import GPTArgs, GPTTrainer, GPTTrainerConfig, XttsAudioConfig
from TTS.utils.manage import ModelManager

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
CHECKPOINTS_DIR = os.path.join(OUTPUT_DIR, "xtts_base")
os.makedirs(CHECKPOINTS_DIR, exist_ok=True)

# Use already-downloaded model files
DVAE_CHECKPOINT = os.path.join(MODEL_DIR, "dvae.pth")
MEL_NORM_FILE   = os.path.join(MODEL_DIR, "mel_stats.pth")
XTTS_CHECKPOINT = os.path.join(MODEL_DIR, "model.pth")
TOKENIZER_FILE  = os.path.join(MODEL_DIR, "vocab.json")

# Speaker reference for test generation
SPEAKER_REFERENCE = ["/tmp/jamie_fraser_denoised.wav"]

# Dataset config
config_dataset = BaseDatasetConfig(
    formatter="ljspeech",
    dataset_name="jimmy",
    path=TRAINING_DATA,
    meta_file_train=os.path.join(TRAINING_DATA, "metadata.csv"),
    language="en",
)

def main():
    model_args = GPTArgs(
        max_conditioning_length=132300,  # 6 secs
        min_conditioning_length=66150,   # 3 secs
        debug_loading_failures=False,
        max_wav_length=255995,           # ~11.6 seconds
        max_text_length=200,
        mel_norm_file=MEL_NORM_FILE,
        dvae_checkpoint=DVAE_CHECKPOINT,
        xtts_checkpoint=XTTS_CHECKPOINT,
        tokenizer_file=TOKENIZER_FILE,
        gpt_num_audio_tokens=1026,
        gpt_start_audio_token=1024,
        gpt_stop_audio_token=1025,
        gpt_use_masking_gt_prompt_approach=True,
        gpt_use_perceiver_resampler=True,
    )

    audio_config = XttsAudioConfig(
        sample_rate=22050,
        dvae_sample_rate=22050,
        output_sample_rate=24000,
    )

    config = GPTTrainerConfig(
        epochs=30,
        output_path=OUTPUT_DIR,
        model_args=model_args,
        run_name="jimmy_xtts_ft",
        project_name="jimmy_voice",
        run_description="Fine-tuning XTTS v2 on Jimmy's voice",
        dashboard_logger="tensorboard",
        logger_uri=None,
        audio=audio_config,
        batch_size=2,
        eval_batch_size=2,
        num_loader_workers=2,
        eval_split_max_size=10,
        eval_split_size=0.1,
        print_step=25,
        plot_step=100,
        log_model_step=1000,
        save_step=500,
        save_n_checkpoints=2,
        save_checkpoints=True,
        target_loss="loss",
        print_eval=False,
        optimizer="AdamW",
        optimizer_wd_only_on_weights=True,
        optimizer_params={"betas": [0.9, 0.96], "eps": 1e-8, "weight_decay": 1e-2},
        lr=5e-06,
        lr_scheduler="MultiStepLR",
        lr_scheduler_params={"milestones": [50000 * 18, 150000 * 18, 300000 * 18], "gamma": 0.5, "last_epoch": -1},
        test_sentences=[
            {
                "text": "Hello, I am Jimmy. A voice from the Highlands, running on a Raspberry Pi.",
                "speaker_wav": SPEAKER_REFERENCE,
                "language": "en",
            },
            {
                "text": "Right then, let us get to work. I have fixed the bug and the tests are passing.",
                "speaker_wav": SPEAKER_REFERENCE,
                "language": "en",
            },
        ],
    )

    # Load samples
    train_samples, eval_samples = load_tts_samples(
        [config_dataset],
        eval_split=True,
        eval_split_max_size=config.eval_split_max_size,
        eval_split_size=config.eval_split_size,
    )
    print(f"Train: {len(train_samples)}, Eval: {len(eval_samples)}")

    model = GPTTrainer.init_from_config(config)

    trainer = Trainer(
        TrainerArgs(
            restore_path=None,
            skip_train_epoch=False,
            start_with_eval=False,
            grad_accum_steps=84,
        ),
        config,
        output_path=OUTPUT_DIR,
        model=model,
        train_samples=train_samples,
        eval_samples=eval_samples,
    )

    trainer.fit()
    print(f"\nDone! Model saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
