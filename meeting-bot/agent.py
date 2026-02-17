#!/usr/bin/env python3
"""
Full autonomous meeting agent.

Joins a meeting, listens, transcribes, and can respond.
This ties together join_meeting, transcribe, and speak modules.
"""

import asyncio
import sys
import os
import time
import threading
from collections import deque

from join_meeting import launch_browser_and_join, detect_platform
from transcribe import create_whisper_model, capture_audio_chunk, is_silence
from speak import speak
import config


class MeetingAgent:
    """Autonomous meeting participant."""

    def __init__(self, meeting_url: str):
        self.meeting_url = meeting_url
        self.platform = detect_platform(meeting_url)
        self.transcript = deque(maxlen=100)  # Last 100 utterances
        self.running = False
        self.whisper_model = None

    def on_transcription(self, text: str):
        """Called when new speech is transcribed."""
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {text}"
        self.transcript.append(entry)
        print(f"\n📝 {entry}")

        # Save transcript to file
        with open("transcript.txt", "a") as f:
            f.write(entry + "\n")

        # TODO: Hook into an LLM here to decide if/how to respond
        # Example: if someone says "hey bot" or asks a question
        text_lower = text.lower()
        if any(trigger in text_lower for trigger in ["hey bot", "hey assistant", "ai assistant"]):
            self.respond("Hello! I'm here and listening. How can I help?")

    def respond(self, text: str):
        """Speak a response into the meeting."""
        print(f"\n🔊 Responding: {text}")
        try:
            speak(text)
        except Exception as e:
            print(f"[agent] TTS error: {e}")

    def transcription_loop(self):
        """Run transcription in a thread."""
        print("[agent] Starting transcription loop...")
        self.whisper_model = create_whisper_model()

        while self.running:
            try:
                audio = capture_audio_chunk()
                if is_silence(audio):
                    continue

                segments, info = self.whisper_model.transcribe(
                    audio,
                    language=config.WHISPER_LANGUAGE,
                    beam_size=5,
                    vad_filter=True,
                )

                full_text = ""
                for segment in segments:
                    text = segment.text.strip()
                    if text:
                        full_text += text + " "

                if full_text.strip():
                    self.on_transcription(full_text.strip())

            except Exception as e:
                print(f"[agent] Transcription error: {e}")
                time.sleep(1)

    async def run(self):
        """Main agent loop: join meeting + transcribe concurrently."""
        self.running = True

        # Start transcription in background thread
        transcription_thread = threading.Thread(
            target=self.transcription_loop, daemon=True
        )
        transcription_thread.start()

        # Give transcription a moment to initialize
        await asyncio.sleep(2)

        # Join the meeting (this blocks while browser is open)
        print(f"\n[agent] Joining {self.platform} meeting: {self.meeting_url}")
        try:
            await launch_browser_and_join(self.meeting_url, keep_open=True)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            print("\n[agent] Meeting ended. Transcript saved to transcript.txt")
            print(f"[agent] Total utterances captured: {len(self.transcript)}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python agent.py <meeting-url>")
        print("Example: python agent.py https://meet.jit.si/my-test-room")
        sys.exit(1)

    url = sys.argv[1]
    agent = MeetingAgent(url)
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
