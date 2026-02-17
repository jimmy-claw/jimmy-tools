#!/bin/bash
# Manage virtual audio devices for meeting bot
# Usage: ./virtual_audio.sh start|stop|status

set -euo pipefail

SINK_NAME="meeting-sink"
VMIC_NAME="virtual-mic"

start_audio() {
    echo "Starting PulseAudio if not running..."
    pulseaudio --check 2>/dev/null || pulseaudio --start --daemonize

    echo "Creating virtual audio devices..."

    # Sink where Chromium will output audio (we monitor this for transcription)
    if ! pactl list sinks short | grep -q "$SINK_NAME"; then
        pactl load-module module-null-sink sink_name="$SINK_NAME" \
            sink_properties=device.description="Meeting-Bot-Output"
        echo "Created sink: $SINK_NAME"
    else
        echo "Sink $SINK_NAME already exists"
    fi

    # Virtual microphone: a null sink whose monitor we remap as a source
    # Chromium will use this as its microphone input
    if ! pactl list sinks short | grep -q "$VMIC_NAME"; then
        pactl load-module module-null-sink sink_name="$VMIC_NAME" \
            sink_properties=device.description="Meeting-Bot-Virtual-Mic"
        echo "Created virtual mic sink: $VMIC_NAME"
    else
        echo "Virtual mic $VMIC_NAME already exists"
    fi

    # Remap the virtual-mic's monitor as a proper source so apps can select it
    if ! pactl list sources short | grep -q "vmic-source"; then
        pactl load-module module-remap-source \
            source_name="vmic-source" \
            master="${VMIC_NAME}.monitor" \
            source_properties=device.description="Meeting-Bot-Microphone"
        echo "Created remapped source: vmic-source"
    else
        echo "vmic-source already exists"
    fi

    echo ""
    echo "Audio devices ready:"
    echo "  Browser output sink: $SINK_NAME"
    echo "  Monitor (for capture): ${SINK_NAME}.monitor"
    echo "  Virtual mic sink (play TTS here): $VMIC_NAME"
    echo "  Virtual mic source (browser reads): vmic-source"
}

stop_audio() {
    echo "Removing virtual audio devices..."
    # Unload by name - find module IDs
    for module_id in $(pactl list modules short | grep "sink_name=$VMIC_NAME\|source_name=vmic-source\|sink_name=$SINK_NAME" | awk '{print $1}'); do
        pactl unload-module "$module_id" 2>/dev/null || true
        echo "Unloaded module $module_id"
    done
    echo "Virtual audio devices removed."
}

status_audio() {
    echo "=== Sinks ==="
    pactl list sinks short
    echo ""
    echo "=== Sources ==="
    pactl list sources short
    echo ""
    echo "=== Meeting Bot Devices ==="
    pactl list sinks short | grep -E "$SINK_NAME|$VMIC_NAME" || echo "(none)"
    pactl list sources short | grep -E "vmic-source|$SINK_NAME" || echo "(none)"
}

case "${1:-status}" in
    start)  start_audio ;;
    stop)   stop_audio ;;
    status) status_audio ;;
    *)      echo "Usage: $0 start|stop|status" ;;
esac
