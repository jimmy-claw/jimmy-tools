#!/usr/bin/env python3
"""Meeting bot that relays audio through the main OpenClaw agent via file IPC."""

import subprocess, numpy as np, soundfile as sf, os, time, json, sys, asyncio
from playwright.async_api import async_playwright

MEETING_URL = sys.argv[1] if len(sys.argv) > 1 else "https://meet.jit.si/WithJimmyClawTest1"
MONITOR = "meeting-sink.monitor"
TTS_SINK = "virtual-mic"
PIPER_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "en_GB-alan-medium.onnx")
CHUNK_SEC = 8
BOT_NAME = "Jimmy"

# File IPC paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSCRIPT_FILE = os.path.join(SCRIPT_DIR, "transcript.txt")
RESPONSE_FILE = os.path.join(SCRIPT_DIR, "response.txt")


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
    except: pass
    await asyncio.sleep(0.5)
    try:
        await page.locator('[data-testid="prejoin.joinMeeting"]').first.click(timeout=5000)
        print("[bot] Joined!", flush=True)
    except Exception as e:
        print(f"[bot] Join issue: {e}", flush=True)
    await asyncio.sleep(5)
    return pw, browser, page


def capture():
    subprocess.run(["ffmpeg", "-f", "pulse", "-i", MONITOR, "-ac", "1", "-ar", "16000",
                    "-t", str(CHUNK_SEC), "/tmp/chunk.wav", "-y", "-loglevel", "error"],
                   timeout=CHUNK_SEC + 5)
    data, sr = sf.read("/tmp/chunk.wav", dtype="float32")
    return data


def transcribe(whisper, audio):
    segments, _ = whisper.transcribe(audio, language="en")
    text = " ".join(seg.text.strip() for seg in segments).strip()
    words = text.split()
    if len(words) > 6:
        half = len(words) // 2
        if " ".join(words[:half]) == " ".join(words[half:half*2]):
            return ""
    return text


def speak(text):
    proc = subprocess.run(["piper", "--model", PIPER_MODEL, "--output_file", "/tmp/reply.wav"],
                          input=text.encode(), capture_output=True, timeout=30)
    if proc.returncode == 0:
        subprocess.run(["paplay", "--device", TTS_SINK, "/tmp/reply.wav"], timeout=30)


def write_transcript(text):
    """Write transcript for main agent to read."""
    with open(TRANSCRIPT_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} | {text}\n")


def check_response():
    """Check if main agent wrote a response."""
    if os.path.exists(RESPONSE_FILE):
        with open(RESPONSE_FILE, "r") as f:
            response = f.read().strip()
        os.unlink(RESPONSE_FILE)
        if response:
            return response
    return None


async def main():
    print("[bot] Loading Whisper...", flush=True)
    from faster_whisper import WhisperModel
    whisper = WhisperModel("tiny", device="cpu", compute_type="int8")

    # Clean up old files
    for f in [TRANSCRIPT_FILE, RESPONSE_FILE]:
        if os.path.exists(f):
            os.unlink(f)

    pw, browser, page = await join_meeting()
    print("[loop] Relay mode — transcripts go to main agent. Listening...", flush=True)

    round_num = 0
    try:
        while True:
            # Check for response from main agent first
            response = check_response()
            if response:
                print(f"[say] {response}", flush=True)
                speak(response)

            # Capture and transcribe
            audio = capture()
            rms = np.sqrt(np.mean(audio ** 2))
            if rms < 0.001:
                continue

            text = transcribe(whisper, audio)
            if not text or len(text.split()) < 3:
                continue

            round_num += 1
            print(f"[hear #{round_num}] {text}", flush=True)
            write_transcript(text)

            # Check for response again after writing
            time.sleep(0.5)
            response = check_response()
            if response:
                print(f"[say] {response}", flush=True)
                speak(response)

    except KeyboardInterrupt:
        pass
    finally:
        await browser.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
