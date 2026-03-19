#!/bin/bash
# Summarize session files into daily logs
# Usage: ./summarize-sessions.sh [days_back]
#   days_back: Number of days to summarize (default: 7)

DAYS=${1:-7}
SESSION_DIR="$HOME/.openclaw/agents/main/sessions"
LOG_DIR="$HOME/.openclaw/workspace/memory/daily"
VENICE_API_KEY="${VENICE_API_KEY:-$(cat ~/.config/venice/api_key 2>/dev/null)}"

if [ -z "$VENICE_API_KEY" ]; then
    echo "Error: VENICE_API_KEY not set"
    exit 1
fi

echo "Summarizing sessions from last $DAYS days..."

# Find sessions modified in last N days
for ((i=0; i<DAYS; i++)); do
    DATE=$(date -d "$i days ago" +%Y-%m-%d)
    TIMESTAMP_START=$(date -d "$DATE 00:00:00" +%s)
    TIMESTAMP_END=$(date -d "$DATE 23:59:59" +%s)
    
    LOG_FILE="$LOG_DIR/$DATE.md"
    
    # Skip if already has today's summary
    if grep -q "## Session Summary" "$LOG_FILE" 2>/dev/null; then
        echo "Skipping $DATE (already summarized)"
        continue
    fi
    
    # Find sessions modified today
    SESSIONS=$(find "$SESSION_DIR" -name "*.jsonl" -type f 2>/dev/null | while read f; do
        MTIME=$(stat -c %Y "$f" 2>/dev/null)
        if [ -n "$MTIME" ] && [ "$MTIME" -ge "$TIMESTAMP_START" ] && [ "$MTIME" -le "$TIMESTAMP_END" ]; then
            echo "$f"
        fi
    done)
    
    if [ -z "$SESSIONS" ]; then
        echo "No sessions for $DATE"
        continue
    fi
    
    echo "Processing $DATE..."
    
    # Extract significant events from sessions
    EVENTS=""
    for SESSION in $SESSIONS; do
        # Extract user messages and assistant actions
        cat "$SESSION" 2>/dev/null | jq -r '
            select(.type == "message") |
            select(.message.role == "user") |
            .message.content[0].text // empty
        ' 2>/dev/null | head -20 >> /tmp/session-temp.txt
    done
    
    if [ -s /tmp/session-temp.txt" ]; then
        EVENTS=$(cat /tmp/session-temp.txt" | head -50 | tr '\n' ' ' | sed 's/"/\\"/g')
        rm -f /tmp/session-temp.txt"
    fi
    
    if [ -z "$EVENTS" ]; then
        echo "No events for $DATE"
        continue
    fi
    
    # Create summary prompt
    PROMPT="Summarize this day in 3-5 bullet points. Focus on: what was worked on, decisions made, problems solved, and any important findings. Be concise but informative.
    
    Events:
    $EVENTS"
    
    # Call LLM for summary
    SUMMARY=$(curl -s https://api.venice.ai/api/v1/chat/completions \
        -H "Authorization: Bearer $VENICE_API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"minimax-m27\",\"messages\":[{\"role\":\"user\",\"content\":\"$PROMPT\"}],\"max_tokens\":500}" \
        | jq -r '.choices[0].message.content // empty' 2>/dev/null)
    
    if [ -n "$SUMMARY" ]; then
        echo "## Session Summary ($DATE)" >> "$LOG_FILE"
        echo "$SUMMARY" >> "$LOG_FILE"
        echo "" >> "$LOG_FILE"
        echo "✓ $DATE summarized"
    else
        echo "✗ Failed to summarize $DATE"
    fi
done

echo "Done!"
