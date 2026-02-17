#!/usr/bin/env python3
"""
Record full meeting audio from PulseAudio monitor sink.

Saves the raw audio stream for later transcription and summarization.
Can run alongside live_loop.py — both read from the same monitor.

Usage:
    # Record until Ctrl+C
    python record.py

    # Record with max duration
    python record.py --max-duration 3600

    # Specify output
    python record.py --output recordings/meeting-2026-02-17.wav

    # Record + auto-transcribe when done
    python record.py --transcribe

    # Record + transcribe + summarize
    python record.py --transcribe --summarize
"""

import argparse
import os
import subprocess
import sys
import signal
import time
from datetime import datetime


MONITOR = "meeting-sink.monitor"
SAMPLE_RATE = 16000
RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "recordings")


def record_meeting(output_path, max_duration=None):
    """Record from meeting sink monitor to WAV file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cmd = [
        "ffmpeg",
        "-f", "pulse",
        "-i", MONITOR,
        "-ac", "1",
        "-ar", str(SAMPLE_RATE),
        "-acodec", "pcm_s16le",
    ]

    if max_duration:
        cmd.extend(["-t", str(max_duration)])

    cmd.extend([output_path, "-y", "-loglevel", "warning"])

    print(f"🎙️ Recording meeting audio...")
    print(f"   Source: {MONITOR}")
    print(f"   Output: {output_path}")
    if max_duration:
        print(f"   Max duration: {max_duration}s")
    print(f"   Press Ctrl+C to stop recording")
    print()

    start_time = time.time()

    proc = subprocess.Popen(cmd)

    def stop(sig, frame):
        proc.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    proc.wait()
    duration = time.time() - start_time

    print(f"\n✅ Recording saved: {output_path}")
    print(f"   Duration: {duration/60:.1f} minutes")
    print(f"   Size: {os.path.getsize(output_path) / 1024 / 1024:.1f} MB")

    return duration


def transcribe_recording(audio_path, output_path=None):
    """Transcribe a recorded meeting using Whisper."""
    if output_path is None:
        output_path = audio_path.replace(".wav", "-transcript.txt")

    print(f"\n📝 Transcribing: {audio_path}")
    print(f"   This may take a while for long recordings...")

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("pip install faster-whisper")
        return None

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, language="en")

    lines = []
    for segment in segments:
        timestamp = f"[{format_time(segment.start)} → {format_time(segment.end)}]"
        lines.append(f"{timestamp} {segment.text.strip()}")

    transcript = "\n".join(lines)

    with open(output_path, "w") as f:
        f.write(f"# Meeting Transcript\n")
        f.write(f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"# Audio: {audio_path}\n")
        f.write(f"# Language: {info.language} (confidence: {info.language_probability:.2f})\n")
        f.write(f"# Duration: {info.duration:.0f}s\n\n")
        f.write(transcript)

    print(f"✅ Transcript saved: {output_path}")
    print(f"   Segments: {len(lines)}")
    return output_path


def summarize_transcript(transcript_path, output_path=None):
    """
    Summarize a meeting transcript.

    For now, creates a prompt file you can feed to Claude/LLM.
    TODO: Wire to OpenClaw API for automatic summarization.
    """
    if output_path is None:
        output_path = transcript_path.replace("-transcript.txt", "-summary-prompt.txt")

    with open(transcript_path) as f:
        transcript = f.read()

    prompt = f"""Please summarize the following meeting transcript. Include:

1. **Key Topics Discussed** — Main subjects covered
2. **Decisions Made** — Any agreements or conclusions
3. **Action Items** — Tasks assigned, with owners if mentioned
4. **Notable Quotes** — Important statements
5. **Follow-ups** — Items that need further discussion

---

{transcript}
"""

    with open(output_path, "w") as f:
        f.write(prompt)

    print(f"\n📋 Summary prompt saved: {output_path}")
    print(f"   Feed this to Claude for a meeting summary:")
    print(f"   cat '{output_path}' | claude")
    return output_path


def format_time(seconds):
    """Format seconds as MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def main():
    parser = argparse.ArgumentParser(description="Record meeting audio")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output WAV path")
    parser.add_argument("--max-duration", type=int, default=None,
                        help="Max recording duration in seconds")
    parser.add_argument("--transcribe", action="store_true",
                        help="Transcribe after recording")
    parser.add_argument("--summarize", action="store_true",
                        help="Generate summary prompt after transcription")
    parser.add_argument("--monitor", type=str, default=MONITOR,
                        help="PulseAudio monitor source")

    # Subcommand for transcribing existing files
    parser.add_argument("--transcribe-file", type=str, default=None,
                        help="Transcribe an existing recording")
    args = parser.parse_args()

    global MONITOR
    MONITOR = args.monitor

    # Transcribe existing file
    if args.transcribe_file:
        t_path = transcribe_recording(args.transcribe_file)
        if t_path and args.summarize:
            summarize_transcript(t_path)
        return

    # Generate output path
    if args.output:
        output_path = args.output
    else:
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        output_path = os.path.join(RECORDINGS_DIR, f"meeting-{timestamp}.wav")

    # Record
    duration = record_meeting(output_path, args.max_duration)

    # Post-processing
    if args.transcribe and duration > 0:
        t_path = transcribe_recording(output_path)
        if t_path and args.summarize:
            summarize_transcript(t_path)


if __name__ == "__main__":
    main()
