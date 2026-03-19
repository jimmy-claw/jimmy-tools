#!/bin/bash
# Summarize session files into daily logs
DAYS=${1:-7}
SESSION_DIR="$HOME/.openclaw/agents/main/sessions"
LOG_DIR="$HOME/.openclaw/workspace/memory/daily"
VENICE_KEY=$(cat ~/.openclaw/agents/main/agent/auth-profiles.json | jq -r '.profiles[] | select(.provider == "venice") | .key')

echo "Summarizing last $DAYS days..."

for ((i=1; i<=DAYS; i++)); do
    DATE=$(date -d "$i days ago" +%Y-%m-%d)
    LOG_FILE="$LOG_DIR/$DATE.md"
    
    if [ -f "$LOG_FILE" ] && grep -q "Session Summary" "$LOG_FILE" 2>/dev/null; then
        echo "Skip $DATE"
        continue
    fi
    
    echo "Processing $DATE..."
    
    # Collect events - use process substitution instead of pipeline
    TEMP=$(mktemp)
    {
        for f in $(find "$SESSION_DIR" -name "*.jsonl" -type f 2>/dev/null); do
            MTIME=$(stat -c %Y "$f" 2>/dev/null)
            DAY_START=$(date -d "$DATE 00:00" +%s)
            DAY_END=$(date -d "$DATE 23:59" +%s)
            if [ "$MTIME" -ge "$DAY_START" ] && [ "$MTIME" -le "$DAY_END" ]; then
                cat "$f" | jq -r 'select(.type=="message") | select(.message.role=="user") | .message.content[0].text // empty' 2>/dev/null
            fi
        done
    } | head -50 > "$TEMP"
    
    EVENTS=$(cat "$TEMP" | tr '\n' ' ' | sed 's/"/\\"/g' | head -c 3000)
    rm -f "$TEMP"
    
    if [ -z "$EVENTS" ] || [ "$EVENTS" = " " ]; then
        echo "No events for $DATE"
        continue
    fi
    
    PROMPT="Summarize this day in 3-5 bullet points about what was worked on, decisions made, problems solved. Be concise."
    
    SUMMARY=$(curl -s https://api.venice.ai/api/v1/chat/completions \
        -H "Authorization: Bearer $VENICE_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"minimax-m27\",\"messages\":[{\"role\":\"user\",\"content\":\"$PROMPT\n\n$EVENTS\"}],\"max_tokens\":500,\"venice_parameters\":{\"disable_thinking\":true}}" \
        | jq -r '.choices[0].message.content // empty')
    
    if [ -n "$SUMMARY" ] && [ "$SUMMARY" != "null" ]; then
        echo "## Session Summary ($DATE)" >> "$LOG_FILE"
        echo "$SUMMARY" >> "$LOG_FILE"
        echo "" >> "$LOG_FILE"
        echo "OK $DATE"
    else
        echo "FAIL $DATE"
    fi
done

echo "Done!"
