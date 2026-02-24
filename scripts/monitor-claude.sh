#!/bin/bash
# Monitor Claude Code running in a tmux session
# Usage: ./monitor-claude.sh <host> <session-name>

HOST="$1"
SESSION="$2"

if [ -z "$HOST" ] || [ -z "$SESSION" ]; then
    echo "Usage: $0 <host> <session-name>"
    echo "Example: $0 192.168.0.152 claude-12345"
    exit 1
fi

echo "=== Claude Code Session: $SESSION on $HOST ==="
echo ""

# Show if session exists and is running
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$HOST" "
    echo '--- Session Status ---'
    if tmux has-session -t $SESSION 2>/dev/null; then
        echo 'Session is RUNNING'
        echo ''
        echo '--- Last 30 lines of output ---'
        tmux capture-pane -t $SESSION -p | tail -30
    else
        echo 'Session NOT FOUND or ended'
        echo ''
        echo '--- Last session logs ---'
        cat ~/claude-*.log 2>/dev/null | tail -30 || echo 'No logs found'
    fi
"