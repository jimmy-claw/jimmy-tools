#!/bin/bash
# Run Claude Code on a remote host without getting killed on SSH disconnect
# Usage:
#   ./run-claude-code.sh [--replace] <host> "<prompt>" [max-turns] [log-file]
# Example:
#   ./run-claude-code.sh 192.168.0.152 "Fix the bug" 50 my-task.log
#   ./run-claude-code.sh --replace 192.168.0.152 "Fix the bug" 50

set -e

REPLACE=false
if [ "$1" = "--replace" ]; then
    REPLACE=true
    shift
fi

HOST="${1:-192.168.0.152}"
PROMPT="$2"
MAX_TURNS="${3:-100}"
LOG_FILE="${4:-claude-$(date +%s).log}"

if [ -z "$PROMPT" ]; then
    echo "Usage: $0 [--replace] <host> <prompt> [max-turns=100] [log-file]"
    echo ""
    echo "Options:"
    echo "  --replace   Kill existing claude processes before starting"
    echo ""
    echo "Examples:"
    echo "  $0 192.168.0.152 'Fix the bug in foo.rs' 50"
    echo "  $0 --replace 192.168.0.152 'Rebase PR #5' 30 pr5-rebase.log"
    echo "  $0 192.168.0.152 'Check cargo test output' 20 test.log"
    exit 1
fi

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

echo "Starting Claude Code on $HOST..."
echo "  Prompt: ${PROMPT:0:50}..."
echo "  Max turns: $MAX_TURNS"
echo "  Log file: ~/$LOG_FILE"
echo ""

# Escape prompt for shell
ESCAPED_PROMPT=$(printf '%s' "$PROMPT" | sed 's/"/\\"/g' | tr '\n' ' ')

# Only kill existing processes if --replace flag is passed
if [ "$REPLACE" = true ]; then
    echo "Replacing existing claude processes..."
    ssh $SSH_OPTS "$HOST" "pkill -f 'claude -p' 2>/dev/null || true"
    sleep 1
fi

# Extract task name from first meaningful sentence of prompt
TASK_NAME=$(printf '%s' "$PROMPT" | tr '\n' ' ' | sed 's/^[[:space:]]*//' | sed 's/\([.!?]\) .*/\1/' | head -c 120)

# Derive meta file path from log file (e.g. my-task.log -> my-task.meta.json)
META_FILE="${LOG_FILE%.log}.meta.json"

# Start Claude Code with --dangerously-skip-permissions (required for non-interactive)
# Use nohup to survive SSH disconnect
ssh $SSH_OPTS "$HOST" "
    export PATH=\$HOME/.npm-global/bin:\$PATH

    nohup claude -p \"$ESCAPED_PROMPT\" \
        --dangerously-skip-permissions \
        --max-turns $MAX_TURNS \
        > ~/$LOG_FILE 2>&1 &

    CLAUDE_PID=\$!
    echo \"Claude Code started in background, PID: \$CLAUDE_PID\"
    echo \"Log: ~/$LOG_FILE\"

    # Write task metadata file
    cat > ~/$META_FILE <<METAEOF
{
  \"name\": \"$(printf '%s' "$TASK_NAME" | sed 's/"/\\\\"/g')\",
  \"started\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
  \"log_file\": \"$HOME/$LOG_FILE\",
  \"max_turns\": $MAX_TURNS,
  \"pid\": \$CLAUDE_PID
}
METAEOF
    echo \"Metadata: ~/$META_FILE\"
"

echo ""
echo "Started! Monitor with:"
echo "  ./monitor-claude.sh $HOST $LOG_FILE"
echo ""
echo "Or continuous watch:"
echo "  ./monitor-claude.sh $HOST $LOG_FILE watch"
echo ""
echo "Metadata file:"
echo "  ~/$META_FILE"
echo ""
echo "To kill:"
echo "  ssh $HOST 'pkill -f \"claude -p\"'"
