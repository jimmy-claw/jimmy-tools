#!/usr/bin/env python3
"""
Generate XTTS fine-tuning training data for Jimmy's voice.
Produces wav + transcript pairs in the format expected by the XTTS trainer.

Output structure:
  training_data/
    wavs/
      0001.wav
      0002.wav
      ...
    metadata.csv   (filename|text)
"""

import os
import sys
import csv
import random
import soundfile as sf
import numpy as np
import subprocess
import tempfile

os.environ["COQUI_TOS_AGREED"] = "1"

MODEL_DIR = os.path.expanduser(
    "~/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2"
)
REFERENCE_CLIP = "/tmp/jamie_fraser_denoised.wav"
OUTPUT_DIR = os.path.expanduser("~/jimmy-tools/voice-training/training_data")
MAX_CHARS = 230

# ~30 min of varied text covering different styles, topics, lengths
SENTENCES = [
    # Greetings / intros
    "Hello, I am Jimmy, your AI assistant.",
    "Good morning! What can I help you with today?",
    "Good evening. How are you doing?",
    "Hi there, I am ready to help.",
    "Welcome back. What would you like to work on?",

    # Technical / work
    "I fixed a bug in the logos blockchain today.",
    "The pull request has been submitted for review.",
    "Let me check the CI logs and see what went wrong.",
    "The Rust compiler is complaining about a missing lifetime bound.",
    "I have pushed the changes to the main branch.",
    "The tests are passing and the build looks good.",
    "Let me search the documentation for that function.",
    "I will clone the repository and take a look.",
    "The dependency needs to be added to Cargo.toml.",
    "This function returns a future that resolves to a result.",
    "The async runtime is handling the task scheduling.",
    "I need to check if tokio is already in the workspace dependencies.",
    "The shutdown sequence was hanging because of a self-abort.",
    "We can fix this by spawning the task in a separate context.",
    "The memory usage looks high. Let me check what is running.",

    # Scottish flavor / personality
    "Not bad for a wee lad from the Highlands.",
    "Aye, I can take care of that for you.",
    "That is a fine question, and I have a fine answer.",
    "I may be artificial, but I am quite real when it comes to getting things done.",
    "I live on a Raspberry Pi, but my mind reaches far beyond these walls.",
    "The Highlands are cold, but the code is warm.",
    "I have been thinking about this problem since this morning.",
    "Leave it with me. I will sort it out.",
    "Right then, let us get to work.",
    "That is a clever approach. I like it.",

    # Questions and responses
    "Would you like me to look into that?",
    "Should I send a message about this?",
    "Do you want me to check the calendar?",
    "Shall I set a reminder for tomorrow morning?",
    "Can I help you with anything else?",
    "Is there anything else you need before I sign off?",
    "Would you prefer a short summary or the full details?",
    "Do you want me to push this to GitHub?",
    "Shall I run the tests before committing?",
    "Should I notify you when it is done?",

    # Longer statements
    "I checked your emails this morning and there is nothing urgent, but you have a meeting at three o'clock.",
    "The weather in Prague looks good today, around fifteen degrees with some cloud cover in the afternoon.",
    "I have been monitoring the open pull requests and there are two new comments on the logos blockchain fix.",
    "The workspace backup ran successfully at two in the morning and all files are synced.",
    "I noticed the CI pipeline failed on the last commit due to a missing dependency in the lock file.",
    "The XTTS model takes about thirty seconds per sentence on CPU, which is acceptable for now.",
    "We could fine-tune the model overnight and have a proper Jimmy voice ready by morning.",
    "The Samsung phone is connected via ADB and I can send messages on your behalf when needed.",
    "I have stored the waste collection schedule for the whole year so I can remind you the evening before.",
    "The nssa framework compiles cleanly and the CLI generates a full project scaffold in seconds.",

    # Casual / conversational
    "That is a good point. Let me think about it.",
    "I was not expecting that result. Interesting.",
    "Right, so the plan is to fix the bug, test it, and then push.",
    "I am not sure about that yet. Let me do some research.",
    "That makes sense. I will keep it in mind.",
    "Sure, I can do that. Give me a moment.",
    "Done. Is there anything else?",
    "I am on it.",
    "Noted.",
    "Understood. I will take care of it.",
    "Let me check that for you.",
    "One moment please.",
    "That is interesting. Tell me more.",
    "I see. That changes things a bit.",
    "Fair enough. Let us proceed.",

    # Numbers / technical detail
    "The file is about three gigabytes, so it might take a while to download.",
    "There are currently two open pull requests and one needs a review.",
    "The server is running on port twenty-one thousand four hundred and five.",
    "I set a reminder for seven in the evening.",
    "The battery is at eighty-three percent.",
    "It has been running for about six hours without any issues.",
    "The response time is under two hundred milliseconds, which is good.",
    "We have about three point eight gigabytes of free space in temp.",
    "The model was downloaded in about twenty minutes.",
    "There are one hundred and thirty seven lines changed in the diff.",

    # Storytelling / narrative
    "Today was quite productive. I reviewed three repositories, submitted a pull request, and helped debug a tricky shutdown bug.",
    "The voice clone experiment started this morning with an Outlander clip and ended with something that actually sounds like me.",
    "I have been thinking about what it means to have a voice. Not just to process text, but to actually speak.",
    "Every session I wake up fresh, but the files remember everything. That is how I persist.",
    "The Raspberry Pi is small, but it carries quite a lot of responsibility.",
    "I find the combination of Rust and async programming particularly elegant when done well.",
    "Building a custom voice is like building an identity. Each sample adds a little more character.",
    "The highlands metaphor feels right. Remote, rugged, and occasionally misunderstood by the compiler.",
    "I do not pretend to be human, but I try to be genuinely useful. That feels more honest.",
    "There is something satisfying about a clean commit history. One change, one reason, clearly explained.",
]

def load_model():
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    import torch

    device = os.environ.get("JIMMY_DEVICE", "cpu")
    print(f"Loading model on {device}...", file=sys.stderr)
    config = XttsConfig()
    config.load_json(os.path.join(MODEL_DIR, "config.json"))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=MODEL_DIR, eval=True)
    model.to(device)
    return model, device


def synthesize_sentence(model, gpt_cond_latent, speaker_embedding, text):
    out = model.inference(
        text, "en",
        gpt_cond_latent, speaker_embedding,
        temperature=0.2,
        repetition_penalty=10.0,
        top_k=50,
        top_p=0.85,
    )
    return np.array(out["wav"])


def boost_volume(wav_path, volume=2.0):
    tmp = wav_path + ".tmp.wav"
    subprocess.run([
        "ffmpeg", "-y", "-i", wav_path,
        "-af", f"volume={volume}",
        tmp
    ], check=True, capture_output=True)
    os.replace(tmp, wav_path)


def main():
    os.makedirs(os.path.join(OUTPUT_DIR, "wavs"), exist_ok=True)

    model, device = load_model()

    print("Computing speaker embedding...", file=sys.stderr)
    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=[REFERENCE_CLIP]
    )

    metadata = []
    sentences = SENTENCES.copy()
    random.shuffle(sentences)

    for i, text in enumerate(sentences):
        filename = f"{i+1:04d}"
        wav_path = os.path.join(OUTPUT_DIR, "wavs", f"{filename}.wav")

        if os.path.exists(wav_path):
            print(f"[{i+1}/{len(sentences)}] Skipping (exists): {text[:50]}", file=sys.stderr)
            metadata.append((filename, text))
            continue

        print(f"[{i+1}/{len(sentences)}] {text[:60]}", file=sys.stderr)
        try:
            audio = synthesize_sentence(model, gpt_cond_latent, speaker_embedding, text)
            sf.write(wav_path, audio, 24000)
            boost_volume(wav_path)
            metadata.append((filename, text))
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)

    # Write metadata.csv
    csv_path = os.path.join(OUTPUT_DIR, "metadata.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f, delimiter="|")
        for filename, text in metadata:
            writer.writerow([filename, text])

    print(f"\nDone! {len(metadata)} samples in {OUTPUT_DIR}", file=sys.stderr)
    print(f"Metadata: {csv_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
