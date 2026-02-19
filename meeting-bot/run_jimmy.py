#!/usr/bin/env python3
"""Meeting bot v3: Silero VAD + Whisper + XTTS + OpenClaw agent IPC.

Features:
- Silero VAD for speech detection (no fixed chunks — captures full utterances)
- Per-meeting transcript files: transcripts/YYYY-MM-DD_HHMMSS_{meeting-name}.md
- XTTS voice synthesis on K11 with sentence chunking
- Agent IPC via /tmp/meeting-bot-{inbox,outbox}.jsonl
- headless=False required for WebRTC audio in Xvfb
- module-remap-source required for PipeWire mic routing

Usage:
    xvfb-run -a python3 run_jimmy.py https://meet.jit.si/YourMeetingRoom

Prerequisites (run once per boot):
    pactl load-module module-null-sink sink_name=virtual-mic
    pactl load-module module-null-sink sink_name=meeting-sink
    pactl load-module module-remap-source source_name=jimmy-mic master=virtual-mic.monitor
    pactl set-default-source jimmy-mic
    pactl set-default-sink meeting-sink
"""

import subprocess, numpy as np, soundfile as sf, os, time, json, sys, asyncio, re, tempfile, signal
import datetime, urllib.request, io
from pathlib import Path
from playwright.async_api import async_playwright

# --- Config ---
MEETING_URL = sys.argv[1] if len(sys.argv) > 1 else "https://meet.jit.si/JimmyAndVaclav2026-v2"
MONITOR = "meeting-sink.monitor"
TTS_SINK = "virtual-mic"
BOT_NAME = "Jimmy"
SAMPLE_RATE = 16000

# VAD settings
VAD_THRESHOLD = 0.3        # Speech probability threshold
SPEECH_PAD_MS = 600        # Padding around speech segments (ms)
MIN_SPEECH_SEC = 1.0       # Minimum speech duration to transcribe
MAX_SPEECH_SEC = 30.0      # Maximum continuous speech before forced transcription
SILENCE_TIMEOUT_SEC = 1.5  # How long silence before we consider utterance complete
CAPTURE_CHUNK_SEC = 0.5    # Small capture chunks for VAD processing

# STT server on K11
STT_URL = "http://192.168.0.125:5006"

# XTTS server on K11
XTTS_URL = "http://192.168.0.125:5005"
XTTS_VOICE = "jimmy"
XTTS_KEY = "jimmy-local-key"

# Agent IPC files
AGENT_INBOX = "/tmp/meeting-bot-inbox.jsonl"
AGENT_OUTBOX = "/tmp/meeting-bot-outbox.jsonl"

# Transcript & Recording
SCRIPT_DIR = Path(__file__).parent
TRANSCRIPT_DIR = SCRIPT_DIR / "transcripts"
RECORDINGS_DIR = SCRIPT_DIR / "recordings"


# --- Transcript ---
class Transcript:
    def __init__(self, meeting_url):
        TRANSCRIPT_DIR.mkdir(exist_ok=True)
        now = datetime.datetime.now()
        # Extract meeting name from URL
        meeting_name = meeting_url.rstrip("/").split("/")[-1]
        # Sanitize for filename
        meeting_name = re.sub(r'[^a-zA-Z0-9_-]', '_', meeting_name)
        self.filename = TRANSCRIPT_DIR / f"{now.strftime('%Y-%m-%d_%H%M%S')}_{meeting_name}.md"
        self.lines = []
        # Write header
        self._write_header(meeting_url, now)
        print(f"[transcript] Saving to {self.filename}", flush=True)

    def _write_header(self, url, now):
        header = f"""# Meeting Transcript

**Meeting:** {url}
**Date:** {now.strftime('%Y-%m-%d %H:%M')}
**Bot:** {BOT_NAME}

---

"""
        with open(self.filename, "w") as f:
            f.write(header)

    def add(self, speaker, text, action=False):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        prefix = "*" if action else ""
        line = f"[{ts}] {prefix}{speaker}{prefix}: {text}"
        self.lines.append(line)
        # Append to file (not overwrite)
        with open(self.filename, "a") as f:
            f.write(line + "\n")
        print(line, flush=True)


# --- Silero VAD ---
class VADCapture:
    """Capture audio using Silero VAD for intelligent speech segmentation."""

    def __init__(self):
        import torch
        self.torch = torch
        print("[vad] Loading Silero VAD...", flush=True)
        model, utils = torch.hub.load('snakers4/silero-vad', 'silero_vad', trust_repo=True)
        self.model = model
        self.get_speech_timestamps = utils[0]
        print("[vad] Silero VAD ready", flush=True)

        self.audio_buffer = np.array([], dtype=np.float32)
        self.silence_start = None
        self.speech_start = None
        self.is_speaking = False

    def capture_chunk(self):
        """Capture a small chunk of audio from PulseAudio."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            subprocess.run([
                "ffmpeg", "-f", "pulse", "-i", MONITOR,
                "-ac", "1", "-ar", str(SAMPLE_RATE),
                "-t", str(CAPTURE_CHUNK_SEC), path, "-y",
                "-loglevel", "error"
            ], timeout=CAPTURE_CHUNK_SEC + 3, capture_output=True)
            data, _ = sf.read(path, dtype="float32")
            return data
        except Exception as e:
            print(f"[vad] Capture error: {e}", flush=True)
            return np.zeros(int(SAMPLE_RATE * CAPTURE_CHUNK_SEC), dtype=np.float32)
        finally:
            try:
                os.unlink(path)
            except:
                pass

    def has_speech(self, audio):
        """Check if audio chunk contains speech using Silero VAD."""
        try:
            # Silero expects 16kHz mono, 512 samples per chunk
            tensor = self.torch.from_numpy(audio).float()
            # Process in 512-sample windows
            chunk_size = 512
            max_prob = 0.0
            for i in range(0, len(tensor) - chunk_size, chunk_size):
                chunk = tensor[i:i + chunk_size]
                prob = self.model(chunk, SAMPLE_RATE).item()
                max_prob = max(max_prob, prob)
            return max_prob > VAD_THRESHOLD, max_prob
        except Exception as e:
            # Fallback to RMS
            rms = np.sqrt(np.mean(audio ** 2))
            return rms > 0.005, rms

    def get_utterance(self):
        """Capture audio until a complete utterance is detected.

        Returns the full utterance audio, or None if no speech detected.
        Uses VAD to detect speech start/end, with timeouts for safety.
        """
        self.audio_buffer = np.array([], dtype=np.float32)
        self.silence_start = None
        self.speech_start = None
        wait_chunks = 0
        max_wait = int(2.0 / CAPTURE_CHUNK_SEC)  # Wait up to 2s for speech to start

        while True:
            chunk = self.capture_chunk()
            speech_detected, prob = self.has_speech(chunk)

            if not self.speech_start:
                # Waiting for speech to start
                if speech_detected:
                    self.speech_start = time.time()
                    self.audio_buffer = np.concatenate([self.audio_buffer, chunk])
                    self.silence_start = None
                else:
                    wait_chunks += 1
                    if wait_chunks > max_wait:
                        return None  # No speech detected
            else:
                # Speech in progress — accumulate
                self.audio_buffer = np.concatenate([self.audio_buffer, chunk])

                if speech_detected:
                    self.silence_start = None
                else:
                    # Silence during speech — potential end of utterance
                    if self.silence_start is None:
                        self.silence_start = time.time()
                    elif time.time() - self.silence_start > SILENCE_TIMEOUT_SEC:
                        # Utterance complete
                        duration = len(self.audio_buffer) / SAMPLE_RATE
                        if duration >= MIN_SPEECH_SEC:
                            return self.audio_buffer
                        else:
                            # Too short, reset
                            self.audio_buffer = np.array([], dtype=np.float32)
                            self.speech_start = None
                            self.silence_start = None
                            wait_chunks = 0

                # Safety: force transcription if utterance is too long
                duration = len(self.audio_buffer) / SAMPLE_RATE
                if duration >= MAX_SPEECH_SEC:
                    return self.audio_buffer


# --- Meeting Recording ---
class MeetingRecorder:
    """Record full meeting audio from PulseAudio monitor to WAV file."""

    def __init__(self, meeting_url):
        RECORDINGS_DIR.mkdir(exist_ok=True)
        now = datetime.datetime.now()
        meeting_name = meeting_url.rstrip("/").split("/")[-1]
        meeting_name = re.sub(r'[^a-zA-Z0-9_-]', '_', meeting_name)
        self.filename = RECORDINGS_DIR / f"{now.strftime('%Y-%m-%d_%H%M%S')}_{meeting_name}.wav"
        self.proc = None

    def start(self):
        cmd = [
            "ffmpeg", "-f", "pulse", "-i", MONITOR,
            "-ac", "1", "-ar", str(SAMPLE_RATE),
            "-acodec", "pcm_s16le",
            str(self.filename), "-y", "-loglevel", "warning",
        ]
        self.proc = subprocess.Popen(cmd)
        print(f"[rec] Recording to {self.filename}", flush=True)

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=5)
            size = self.filename.stat().st_size / 1024 / 1024 if self.filename.exists() else 0
            print(f"[rec] Stopped. File: {self.filename} ({size:.1f} MB)", flush=True)


# --- Transcription via K11 STT Server ---
def transcribe_remote(audio):
    """Send audio to K11 STT server for transcription."""
    try:
        # Write audio to temp WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f, audio, SAMPLE_RATE)
            tmp_path = f.name

        # Send to K11
        import http.client
        import mimetypes
        boundary = "----AudioBoundary"
        with open(tmp_path, "rb") as f:
            audio_data = f.read()
        os.unlink(tmp_path)

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="audio"; filename="audio.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n"
        ).encode() + audio_data + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            f"{STT_URL}/transcribe",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            text = result.get("text", "").strip()
    except Exception as e:
        print(f"[stt] K11 error, falling back to local: {e}", flush=True)
        return transcribe_local(audio)

    return _filter_text(text)


def transcribe_local(audio):
    """Fallback: transcribe locally with whisper base."""
    try:
        from faster_whisper import WhisperModel
        if not hasattr(transcribe_local, "_model"):
            transcribe_local._model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = transcribe_local._model.transcribe(audio, language="en")
        text = " ".join(seg.text.strip() for seg in segments).strip()
    except Exception as e:
        print(f"[stt] Local transcription failed: {e}", flush=True)
        return ""
    return _filter_text(text)


def _filter_text(text):
    """De-duplicate and filter hallucinations."""
    if not text:
        return ""
    words = text.split()
    if len(words) > 6:
        half = len(words) // 2
        if " ".join(words[:half]) == " ".join(words[half:half * 2]):
            return ""
    hallucinations = [
        "thank you for watching", "thanks for watching", "see you in the next",
        "subscribe", "like and subscribe", "please subscribe",
    ]
    text_lower = text.lower()
    for h in hallucinations:
        if h in text_lower and len(words) < 10:
            return ""
    return text


# --- TTS via XTTS on K11 (sentence chunking) ---
def speak(text, transcript):
    """Generate TTS via K11 XTTS server, play each sentence as it's ready."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s for s in sentences if s.strip()]
    if not sentences:
        sentences = [text]

    for sentence in sentences:
        try:
            payload = json.dumps({
                "text": sentence,
                "model_id": "mp3_44100",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
            }).encode()
            req = urllib.request.Request(
                f"{XTTS_URL}/v1/text-to-speech/{XTTS_VOICE}",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "xi-api-key": XTTS_KEY,
                },
            )
            mp3_path = tempfile.mktemp(suffix=".mp3")
            wav_path = tempfile.mktemp(suffix=".wav")

            print(f"[tts] Generating: '{sentence[:60]}'", flush=True)
            with urllib.request.urlopen(req, timeout=120) as resp:
                with open(mp3_path, "wb") as f:
                    f.write(resp.read())

            # Convert mp3 → wav for paplay
            subprocess.run(["ffmpeg", "-y", "-i", mp3_path, "-ar", str(SAMPLE_RATE), "-ac", "1",
                            "-f", "wav", wav_path], capture_output=True, timeout=30)

            # Play into virtual mic
            subprocess.run(["paplay", "--device", TTS_SINK, wav_path], timeout=60)
            print(f"[tts] Played sentence", flush=True)

            os.unlink(mp3_path)
            os.unlink(wav_path)
        except Exception as e:
            print(f"[tts] Error: {e}", flush=True)


# --- Agent IPC ---
def write_to_agent(text, round_num):
    """Write heard text for OpenClaw agent to pick up."""
    msg = json.dumps({
        "type": "heard",
        "text": text,
        "round": round_num,
        "ts": time.strftime("%H:%M:%S"),
    })
    with open(AGENT_INBOX, "a") as f:
        f.write(msg + "\n")
    print(f"[ipc] Wrote to agent inbox", flush=True)


def read_agent_response():
    """Check if OpenClaw agent wrote a response."""
    if not os.path.exists(AGENT_OUTBOX):
        return None
    try:
        with open(AGENT_OUTBOX, "r") as f:
            lines = f.readlines()
        if not lines:
            return None
        last = json.loads(lines[-1].strip())
        open(AGENT_OUTBOX, "w").close()
        return last.get("text", None)
    except:
        return None


# --- PulseAudio Setup ---
def setup_pulseaudio():
    """Ensure virtual audio devices exist."""
    try:
        sinks = subprocess.run(["pactl", "list", "sinks", "short"],
                               capture_output=True, text=True, timeout=5).stdout

        if "virtual-mic" not in sinks:
            subprocess.run(["pactl", "load-module", "module-null-sink",
                            "sink_name=virtual-mic",
                            "sink_properties=device.description=Virtual-Mic"],
                           capture_output=True, timeout=5)
            print("[audio] Created virtual-mic sink", flush=True)

        if "meeting-sink" not in sinks:
            subprocess.run(["pactl", "load-module", "module-null-sink",
                            "sink_name=meeting-sink",
                            "sink_properties=device.description=Meeting-Sink"],
                           capture_output=True, timeout=5)
            print("[audio] Created meeting-sink sink", flush=True)

        sources = subprocess.run(["pactl", "list", "sources", "short"],
                                 capture_output=True, text=True, timeout=5).stdout

        if "jimmy-mic" not in sources:
            subprocess.run(["pactl", "load-module", "module-remap-source",
                            "source_name=jimmy-mic",
                            "master=virtual-mic.monitor",
                            "source_properties=device.description=Jimmy-Mic"],
                           capture_output=True, timeout=5)
            print("[audio] Created jimmy-mic remap source", flush=True)

        subprocess.run(["pactl", "set-default-source", "jimmy-mic"],
                       capture_output=True, timeout=5)
        subprocess.run(["pactl", "set-default-sink", "meeting-sink"],
                       capture_output=True, timeout=5)
        print("[audio] PulseAudio configured ✓", flush=True)

    except Exception as e:
        print(f"[audio] Setup warning: {e}", flush=True)


# --- Browser ---
async def join_meeting():
    print(f"[bot] Joining {MEETING_URL}", flush=True)
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False, args=[
        "--use-fake-ui-for-media-stream",
        "--disable-gpu", "--no-sandbox",
        "--autoplay-policy=no-user-gesture-required",
    ])
    context = await browser.new_context(
        permissions=["microphone", "camera", "notifications"],
        viewport={"width": 1280, "height": 720},
    )
    page = await context.new_page()
    await page.goto(f"{MEETING_URL}#config.startWithVideoMuted=true", timeout=30000)
    await asyncio.sleep(4)
    try:
        await page.locator('input[placeholder*="name" i]').first.fill(BOT_NAME)
    except:
        pass
    await asyncio.sleep(0.5)
    try:
        await page.locator('[data-testid="prejoin.joinMeeting"]').first.click(timeout=5000)
        print("[bot] Joined!", flush=True)
    except Exception as e:
        print(f"[bot] Join issue: {e}", flush=True)
    await asyncio.sleep(5)
    return pw, browser, page


# --- Main Loop ---
async def main():
    # Setup
    setup_pulseaudio()

    for f in [AGENT_INBOX, AGENT_OUTBOX]:
        open(f, "w").close()

    vad = VADCapture()
    transcript = Transcript(MEETING_URL)
    recorder = MeetingRecorder(MEETING_URL)

    pw, browser, page = await join_meeting()
    recorder.start()
    transcript.add("System", f"Bot joined {MEETING_URL}", action=True)
    print("[loop] Listening with VAD... (agent IPC, no fallback)", flush=True)

    last_speak_time = 0
    round_num = 0

    try:
        while True:
            # Check for agent response from previous round
            agent_resp = read_agent_response()
            if agent_resp:
                print(f"[agent] {agent_resp}", flush=True)
                transcript.add(BOT_NAME, agent_resp)
                speak(agent_resp, transcript)
                last_speak_time = time.time()

            # Capture utterance using VAD
            audio = vad.get_utterance()
            if audio is None:
                continue

            duration = len(audio) / SAMPLE_RATE
            print(f"[vad] Utterance: {duration:.1f}s", flush=True)

            # Transcribe via K11
            text = transcribe_remote(audio)
            if not text or len(text.split()) < 2:
                continue

            round_num += 1
            transcript.add("Speaker", text)

            now = time.time()
            if now - last_speak_time < 8:
                continue  # Don't interrupt ourselves

            # Write to agent inbox
            write_to_agent(text, round_num)

            # Wait for agent response (up to 30s)
            for _ in range(30):
                await asyncio.sleep(1)
                agent_resp = read_agent_response()
                if agent_resp:
                    break

            if agent_resp:
                print(f"[agent] {agent_resp}", flush=True)
                transcript.add(BOT_NAME, agent_resp)
                speak(agent_resp, transcript)
                last_speak_time = time.time()
            else:
                print(f"[timeout] No agent response for round {round_num}", flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop()
        transcript.add("System", "Bot left the meeting", action=True)
        print(f"\n[bot] Transcript saved to {transcript.filename}", flush=True)
        print(f"[bot] Recording saved to {recorder.filename}", flush=True)
        await browser.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
