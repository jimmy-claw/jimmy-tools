#!/bin/bash
# Monitor Claude Code - supports both tmux and raw nohup processes
# Usage: 
#   ./monitor-claude.sh <host>                    # Check all Claude processes
#   ./monitor-claude.sh <host> <log-file>         # Check specific log
#   ./monitor-claude.sh <host> <log-file> watch   # Continuous watch mode

HOST="${1:-192.168.0.152}"
LOG_FILE="$2"
WATCH_MODE="$3"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

get_claude_status() {
    ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$HOST" "
        echo '=== Claude Code Processes ==='
        
        # Check for claude processes (excluding grep)
        CLAUDE_PIDS=\$(ps aux | grep claude | grep -v grep | grep -v 'bash -c' || true)
        
        if [ -z \"\$CLAUDE_PIDS\" ]; then
            echo -e '${RED}No Claude Code processes running${NC}'
            exit 0
        fi
        
        echo \"\$CLAUDE_PIDS\" | while read line; do
            PID=\$(echo \"\$line\" | awk '{print \$2}')
            CPU=\$(echo \"\$line\" | awk '{print \$3}')
            MEM=\$(echo \"\$line\" | awk '{print \$4}')
            TIME=\$(echo \"\$line\" | awk '{print \$10}')
            
            echo -e \"PID: \${GREEN}\${PID}\${NC} | CPU: \${CPU}% | MEM: \${MEM}% | Time: \${TIME}\"
        done
        
        # Check latest debug log
        if [ -d ~/.claude/debug ]; then
            LATEST_LOG=\$(ls -t ~/.claude/debug/*.txt 2>/dev/null | head -1)
            if [ -n \"\$LATEST_LOG\" ]; then
                echo ''
                echo '=== Latest Activity ==='
                # Get last non-DEBUG lines (actual Claude output)
                grep -v DEBUG \"\$LATEST_LOG\" | tail -10 | sed 's/^/  /'
            fi
        fi
        
        # Check specific log if provided
        if [ -n '$LOG_FILE' ]; then
            echo ''
            echo '=== Log: $LOG_FILE ==='
            tail -20 ~/$LOG_FILE 2>/dev/null | sed 's/^/  /'
        fi
    "
}

check_stuck() {
    # Check if process is stuck (same command repeated, no progress)
    local log="$1"
    if [ ! -f "$log" ]; then
        return 0  # Not stuck if no log
    fi
    
    # Get last 20 commands
    local last_cmds=$(tail -40 "$log" 2>/dev/null | grep -oP 'Bash.*claude.*' | tail -10)
    local unique_cmds=$(echo "$last_cmds" | sort -u | wc -l)
    
    # If same command repeated 3+ times, might be stuck
    if [ "$unique_cmds" -le 1 ] && [ $(echo "$last_cmds" | wc -l) -ge 3 ]; then
        echo -e "${YELLOW}WARNING: Possible stuck - same command repeated${NC}"
        return 1
    fi
    
    return 0
}

if [ "$WATCH_MODE" = "watch" ]; then
    echo "Watching Claude Code on $HOST (Ctrl+C to exit)..."
    while true; do
        clear
        echo "=== $(date) ==="
        get_claude_status
        sleep 10
    done
else
    get_claude_status
fi