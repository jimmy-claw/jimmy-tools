#!/bin/bash
# Run Claude Code on a remote host (crib) without getting killed on SSH disconnect
# Usage: ./run-claude-code.sh <host> "<prompt>" [--max-turns N]
# Example: ./run-claude-code.sh 192.168.0.152 "Fix the bug" --max-turns 30

set -e

HOST="$1"
shift || { echo "Usage: $0 <host> <prompt> [args...]"; exit 1; }
PROMPT="$1"
shift
ARGS="$@"

# Check for required tools
if ! command -v tmux &> /dev/null && ! command -v screen &> /dev/null; then
    echo "ERROR: Need tmux or screen installed"
    exit 1
fi

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

# Get the path to npm global
NPM_PATH=$(ssh $SSH_OPTS "$HOST" 'echo $HOME/.npm-global/bin')

SESSION_NAME="claude-$$"

echo "Starting Claude Code on $HOST in tmux session '$SESSION_NAME'..."

# Start a detached tmux session with Claude Code
ssh $SSH_OPTS "$HOST" "
    export PATH=\$HOME/.npm-global/bin:\$PATH
    
    # Create a new detached tmux session
    tmux new-session -d -s $SESSION_NAME '
        claude -p \"$PROMPT\" $ARGS
    '
    
    echo 'Claude Code started in tmux session: $SESSION_NAME'
    echo 'To attach: tmux attach -t $SESSION_NAME'
    echo 'To check logs: tmux capture-pane -t $SESSION_NAME -p'
"

echo "Done! Claude Code is running on $HOST in tmux session '$SESSION_NAME'"
echo ""
echo "Monitor with:"
echo "  ssh $HOST 'tmux attach -t $SESSION_NAME'"
echo "  ssh $HOST 'tmux capture-pane -t $SESSION_NAME -p' | tail -20'"
echo ""
echo "Or use the helper:"
echo "  ./monitor-claude.sh $HOST $SESSION_NAME"