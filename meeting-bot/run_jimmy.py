#!/usr/bin/env python3
"""Meeting bot: join Jitsi, transcribe, respond via OpenClaw agent + XTTS voice."""

import subprocess, numpy as np, soundfile as sf, os, time, json, sys, asyncio, re, tempfile
import urllib.request
from playwright.async_api import async_playwright

MEETING_URL = sys.argv[1] if len(sys.argv) > 1 else "https://meet.jit.si/JimmyAndVaclav2026-v2"
MONITOR = "meeting-sink.monitor"
TTS_SINK = "virtual-mic"
CHUNK_SEC = 6
BOT_NAME = "Jimmy"

# XTTS server on K11
XTTS_URL = "http://192.168.0.125:5005"
XTTS_VOICE = "jimmy"
XTTS_KEY = "jimmy-local-key"

# Agent IPC files
AGENT_INBOX = "/tmp/meeting-bot-inbox.jsonl"
AGENT_OUTBOX = "/tmp/meeting-bot-outbox.jsonl"


# --- Audio ---
def capture():
    subprocess.run(["ffmpeg", "-f", "pulse", "-i", MONITOR, "-ac", "1", "-ar", "16000",
                    "-t", str(CHUNK_SEC), "/tmp/chunk.wav", "-y",
                    "-loglevel", "error"], timeout=CHUNK_SEC + 5)
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


# --- TTS via XTTS on K11 (sentence chunking) ---
def speak(text):
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
            subprocess.run(["ffmpeg", "-y", "-i", mp3_path, "-ar", "16000", "-ac", "1",
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


# --- Venice Fallback (if agent doesn't respond in time) ---
VENICE_KEY = os.environ.get("VENICE_API_KEY", "VENICE-INFERENCE-KEY-99xGJuyfeaxX4LIJu0fzrd7fexih-BYWDEZ9m-SWhY")

conversation = [
    {"role": "system", "content": "You are Jimmy, a sharp and witty AI assistant with a Scottish accent. You are in a voice meeting with Václav (a software engineer at Logos). Keep responses SHORT - max 1-2 sentences. Be natural and conversational. No markdown, no formatting, no asterisks."}
]

def llm_fallback(user_text):
    conversation.append({"role": "user", "content": user_text})
    if len(conversation) > 12:
        conversation[:] = conversation[:1] + conversation[-10:]
    try:
        payload = json.dumps({
            "model": "llama-3.3-70b", "messages": conversation,
            "max_tokens": 100, "temperature": 0.7,
        })
        result = subprocess.run(
            ["curl", "-s", "--max-time", "15",
             "https://api.venice.ai/api/v1/chat/completions",
             "-H", f"Authorization: Bearer {VENICE_KEY}",
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=20
        )
        data = json.loads(result.stdout)
        reply = data["choices"][0]["message"]["content"]
        if "<think>" in reply:
            reply = reply.split("</think>")[-1].strip()
        conversation.append({"role": "assistant", "content": reply})
        return reply
    except:
        return None


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
    except: pass
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
    for f in [AGENT_INBOX, AGENT_OUTBOX]:
        open(f, "w").close()

    print("[bot] Loading Whisper...", flush=True)
    from faster_whisper import WhisperModel
    whisper = WhisperModel("tiny", device="cpu", compute_type="int8")

    pw, browser, page = await join_meeting()
    print("[loop] Listening... (agent IPC + Venice fallback)", flush=True)

    last_speak_time = 0
    round_num = 0

    try:
        while True:
            # Check for agent response from previous round
            agent_resp = read_agent_response()
            if agent_resp:
                print(f"[agent] {agent_resp}", flush=True)
                speak(agent_resp)
                last_speak_time = time.time()

            # Capture audio
            audio = capture()
            rms = np.sqrt(np.mean(audio**2))
            if rms < 0.001:
                continue

            text = transcribe(whisper, audio)
            if not text or len(text.split()) < 3:
                continue

            round_num += 1
            print(f"[hear #{round_num}] {text}", flush=True)

            now = time.time()
            if now - last_speak_time < 10:
                continue

            # Write to agent inbox
            write_to_agent(text, round_num)

            # Wait for agent response (no fallback — just me)
            for _ in range(30):  # Wait up to 30s
                await asyncio.sleep(1)
                agent_resp = read_agent_response()
                if agent_resp:
                    break

            if agent_resp:
                print(f"[agent] {agent_resp}", flush=True)
                speak(agent_resp)
                last_speak_time = time.time()
            else:
                print(f"[timeout] No agent response for round {round_num}", flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        await browser.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
