#!/usr/bin/env python3
"""Meeting bot v2: routes through OpenClaw agent, speaker detection, interleaved transcript, faster TTS."""

import subprocess, numpy as np, soundfile as sf, os, time, json, sys, asyncio, datetime
from playwright.async_api import async_playwright
from pathlib import Path

# --- Config ---
MEETING_URL = sys.argv[1] if len(sys.argv) > 1 else "https://meet.jit.si/TestWithJimmy2"
MONITOR = "meeting-sink.monitor"
TTS_SINK = "virtual-mic"
PIPER_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "en_GB-alan-medium.onnx")
CHUNK_SEC = 6  # Shorter chunks for faster response
TTS_SPEED = 1.15  # Speed up TTS (1.0 = normal)
BOT_NAME = "Jimmy"
TRANSCRIPT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transcript.md")
# Agent communication via files
AGENT_INBOX = "/tmp/meeting-bot-inbox.jsonl"   # Bot writes heard text here
AGENT_OUTBOX = "/tmp/meeting-bot-outbox.jsonl"  # Agent writes responses here

# --- Transcript ---
transcript_lines = []

def ts():
    return datetime.datetime.now().strftime("%H:%M:%S")

def log_transcript(speaker, text, action=False):
    prefix = "*" if action else ""
    line = f"[{ts()}] {prefix}{speaker}{prefix}: {text}"
    transcript_lines.append(line)
    # Write to file continuously
    with open(TRANSCRIPT_FILE, "w") as f:
        f.write("# Meeting Transcript\n\n")
        f.write(f"**Meeting:** {MEETING_URL}\n")
        f.write(f"**Date:** {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n")
        f.write("---\n\n")
        for l in transcript_lines:
            f.write(l + "\n")
    print(line, flush=True)


# --- Speaker Detection ---
async def get_active_speaker(page):
    """Get the dominant speaker name from Jitsi DOM."""
    try:
        # Jitsi shows the dominant speaker's name in various places
        # Try the large video display name first
        name = await page.evaluate("""() => {
            // Method 1: Dominant speaker indicator
            const dominant = document.querySelector('.dominant-speaker-name, [class*="dominantSpeaker"] .displayname');
            if (dominant && dominant.textContent.trim()) return dominant.textContent.trim();
            
            // Method 2: Large video display name  
            const large = document.querySelector('#largeVideoContainer .displayname, #localDisplayName');
            if (large && large.textContent.trim()) return large.textContent.trim();
            
            // Method 3: Active speaker class on filmstrip
            const active = document.querySelector('.active-speaker .displayname, [class*="activeSpeaker"] .displayname');
            if (active && active.textContent.trim()) return active.textContent.trim();
            
            // Method 4: Any visible speaker indicator
            const indicators = document.querySelectorAll('[class*="speaker"] .displayname, .videocontainer .displayname');
            for (const ind of indicators) {
                const name = ind.textContent.trim();
                if (name && name !== 'Jimmy' && name !== 'me') return name;
            }
            
            return null;
        }""")
        return name
    except:
        return None


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
    # De-duplicate (Whisper sometimes repeats)
    words = text.split()
    if len(words) > 6:
        half = len(words) // 2
        if " ".join(words[:half]) == " ".join(words[half:half*2]):
            return ""
    return text


def speak(text):
    """TTS with speed adjustment via sox."""
    # Generate with piper
    proc = subprocess.run(["piper", "--model", PIPER_MODEL, "--output_file", "/tmp/reply_raw.wav"],
                          input=text.encode(), capture_output=True, timeout=30)
    if proc.returncode != 0:
        print(f"[tts] piper failed: {proc.stderr.decode()[:100]}", flush=True)
        return
    
    # Speed up with sox
    if TTS_SPEED != 1.0:
        subprocess.run(["sox", "/tmp/reply_raw.wav", "/tmp/reply.wav", "tempo", str(TTS_SPEED)],
                       capture_output=True, timeout=30)
    else:
        os.rename("/tmp/reply_raw.wav", "/tmp/reply.wav")
    
    # Play into virtual mic
    subprocess.run(["paplay", "--device", TTS_SINK, "/tmp/reply.wav"], timeout=30)


# --- Agent Communication ---
def write_to_agent(speaker, text, round_num):
    """Write heard text to inbox for the main agent to pick up."""
    msg = json.dumps({
        "type": "heard",
        "speaker": speaker,
        "text": text,
        "round": round_num,
        "timestamp": ts(),
    })
    with open(AGENT_INBOX, "a") as f:
        f.write(msg + "\n")


def read_agent_response():
    """Check if the agent wrote a response."""
    if not os.path.exists(AGENT_OUTBOX):
        return None
    try:
        with open(AGENT_OUTBOX, "r") as f:
            lines = f.readlines()
        if not lines:
            return None
        # Take the last response and clear the file
        last = json.loads(lines[-1].strip())
        # Clear outbox
        open(AGENT_OUTBOX, "w").close()
        return last.get("text", None)
    except:
        return None


# --- Venice Fallback (if agent doesn't respond in time) ---
VENICE_KEY = "VENICE-INFERENCE-KEY-99xGJuyfeaxX4LIJu0fzrd7fexih-BYWDEZ9m-SWhY"
FALLBACK_MODELS = ["llama-3.3-70b", "gemini-3-flash-preview", "llama-3.2-3b"]

conversation = [
    {"role": "system", "content": "You are Jimmy, a helpful and witty AI assistant. You are in a voice meeting. Keep responses SHORT - max 1-2 sentences. Be natural and conversational. No markdown, no formatting, no asterisks."}
]

def llm_fallback(user_text):
    """Fallback to Venice if agent doesn't respond."""
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
                continue
            reply = data["choices"][0]["message"]["content"]
            if "<think>" in reply:
                reply = reply.split("</think>")[-1].strip()
            if len(reply.strip()) < 3:
                continue
            conversation.append({"role": "assistant", "content": reply})
            print(f"  [fallback: {model}]", flush=True)
            return reply
        except:
            continue
    return None


# --- Browser Join ---
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


# --- Main Loop ---
async def main():
    # Clean up communication files
    for f in [AGENT_INBOX, AGENT_OUTBOX]:
        open(f, "w").close()
    
    print("[bot] Loading Whisper...", flush=True)
    from faster_whisper import WhisperModel
    whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
    
    pw, browser, page = await join_meeting()
    log_transcript("System", f"Bot joined {MEETING_URL}", action=True)
    
    last_speak_time = 0
    round_num = 0
    use_agent = True  # Try agent first, fall back to Venice
    
    try:
        while True:
            # Check for agent response (async from previous round)
            agent_resp = read_agent_response()
            if agent_resp:
                log_transcript(BOT_NAME, agent_resp)
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
            
            # Detect speaker
            speaker = await get_active_speaker(page) or "Unknown"
            log_transcript(speaker, text)
            
            now = time.time()
            if now - last_speak_time < 8:
                continue  # Don't interrupt ourselves
            
            # Write to agent inbox
            write_to_agent(speaker, text, round_num)
            
            # Wait briefly for agent response, fall back to Venice
            await asyncio.sleep(2)
            agent_resp = read_agent_response()
            
            if agent_resp:
                log_transcript(BOT_NAME, agent_resp)
                speak(agent_resp)
                last_speak_time = time.time()
            else:
                # Fallback to Venice
                response = llm_fallback(text)
                if response:
                    log_transcript(BOT_NAME, response)
                    speak(response)
                    last_speak_time = time.time()
                    
    except KeyboardInterrupt:
        pass
    finally:
        log_transcript("System", "Bot left the meeting", action=True)
        print(f"\n[bot] Transcript saved to {TRANSCRIPT_FILE}", flush=True)
        await browser.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
