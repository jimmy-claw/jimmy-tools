"""Shared configuration for meeting bot."""

# Virtual audio device names
SINK_NAME = "meeting-sink"          # Browser outputs audio here
VIRTUAL_MIC_NAME = "virtual-mic"    # We play TTS here; browser reads as mic

# PulseAudio monitor source (auto-created when sink exists)
MONITOR_SOURCE = f"{SINK_NAME}.monitor"

# Audio format for capture/playback
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_FORMAT = "s16le"  # 16-bit signed little-endian PCM

# Whisper settings
WHISPER_MODEL = "base"  # tiny, base, small, medium, large-v3
WHISPER_LANGUAGE = "en"
WHISPER_DEVICE = "cpu"  # cpu on Pi 5 (no CUDA)

# Transcription chunking
CHUNK_DURATION_SEC = 5   # Process audio in N-second chunks
SILENCE_THRESHOLD = 500  # RMS threshold for silence detection

# TTS settings
TTS_ENGINE = "piper"  # piper (local) or openai
PIPER_MODEL = "models/en_GB-alan-medium.onnx"  # British male, closest to Irish available
# For OpenAI TTS (needs OPENAI_API_KEY env var):
OPENAI_TTS_MODEL = "tts-1"
OPENAI_TTS_VOICE = "alloy"

# Browser settings
HEADLESS = True  # Set False for debugging
BROWSER_TIMEOUT_MS = 30000
USER_AGENT = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Agent settings
BOT_NAME = "AI Assistant"
RESPOND_TO_SILENCE_SEC = 30  # Don't respond if no speech for this long
