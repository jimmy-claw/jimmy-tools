#!/usr/bin/env python3
"""All-in-one: launch browser, join meeting, live transcribe + respond."""

import subprocess, numpy as np, soundfile as sf, os, time, json, urllib.request, sys, asyncio
from playwright.async_api import async_playwright

MEETING_URL = sys.argv[1] if len(sys.argv) > 1 else "https://meet.jit.si/WithJimmyClawTest1"
MONITOR = "meeting-sink.monitor"
TTS_SINK = "virtual-mic"
PIPER_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "en_GB-alan-medium.onnx")
CHUNK_SEC = 8
GAIN = 1  # No amplification - raw audio works best with Whisper
VENICE_KEY = "VENICE-INFERENCE-KEY-99xGJuyfeaxX4LIJu0fzrd7fexih-BYWDEZ9m-SWhY"
MODEL = "llama-3.3-70b"
BOT_NAME = "Jimmy"


async def join_meeting():
    """Launch browser and join Jitsi meeting."""
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
        name_input = page.locator('input[placeholder*="name" i]').first
        await name_input.fill(BOT_NAME)
    except: pass
    await asyncio.sleep(0.5)
    
    try:
        btn = page.locator('[data-testid="prejoin.joinMeeting"]').first
        await btn.click(timeout=5000)
        print("[bot] Joined!", flush=True)
    except Exception as e:
        print(f"[bot] Join issue: {e}", flush=True)
    
    await asyncio.sleep(5)
    return pw, browser, page


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


conversation = [
    {"role": "system", "content": "You are Jimmy, a helpful and witty AI assistant with a bit of Irish charm. You are in a voice meeting with Vaclav (a software engineer at Logos). Keep responses SHORT - max 1-2 sentences. Be natural and conversational. No markdown, no formatting, no asterisks."}
]


FALLBACK_MODELS = ["llama-3.3-70b", "venice-uncensored", "llama-3.2-3b", "qwen3-4b", "zai-org-glm-4.7-flash"]

def llm_respond(user_text):
    conversation.append({"role": "user", "content": user_text})
    if len(conversation) > 12:
        conversation[:] = conversation[:1] + conversation[-10:]
    
    for model in FALLBACK_MODELS:
        try:
            payload = json.dumps({
                "model": model, "messages": conversation,
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
            if "error" in data:
                print(f"  [{model}] {data['error']}", flush=True)
                continue
            reply = data["choices"][0]["message"]["content"]
            if "<think>" in reply:
                reply = reply.split("</think>")[-1].strip()
            if len(reply.strip()) < 3:
                print(f"  [{model}] too short: '{reply}'", flush=True)
                continue
            conversation.append({"role": "assistant", "content": reply})
            print(f"  [model: {model}]", flush=True)
            return reply
        except Exception as e:
            print(f"  [{model}] err: {e}", flush=True)
    
    return f"I heard you say: {user_text[:100]}"


def speak(text):
    proc = subprocess.run(["piper", "--model", PIPER_MODEL, "--output_file", "/tmp/reply.wav"],
                          input=text.encode(), capture_output=True, timeout=30)
    if proc.returncode == 0:
        subprocess.run(["paplay", "--device", TTS_SINK, "/tmp/reply.wav"], timeout=30)


async def main():
    print("[bot] Loading Whisper...", flush=True)
    from faster_whisper import WhisperModel
    whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
    
    pw, browser, page = await join_meeting()
    print(f"[loop] Live conversation mode with {MODEL}. Listening...", flush=True)
    
    last_speak_time = 0
    round_num = 0
    
    try:
        while True:
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
            if now - last_speak_time > 10:
                try:
                    response = llm_respond(text)
                    print(f"[say #{round_num}] {response}", flush=True)
                    speak(response)
                    last_speak_time = time.time()
                except Exception as e:
                    print(f"[llm err] {e}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        await browser.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
