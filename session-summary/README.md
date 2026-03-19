# Session Summary

Summarizes OpenClaw session files into daily logs using LLM.

## Purpose

Instead of relying on manual logging, this tool:
1. Reads session JSONL files from OpenClaw
2. Extracts significant events
3. Uses LLM to summarize the day
4. Appends to `memory/daily/YYYY-MM-DD.md`

## Usage

```bash
# Summarize last 7 days
./summarize-sessions.sh

# Summarize last N days
./summarize-sessions.sh 3
```

## Requirements

- `VENICE_API_KEY` environment variable set
- `jq` installed
- Access to `~/.openclaw/agents/main/sessions/`

## How it works

1. Finds session files modified in the target date range
2. Extracts user messages and significant events
3. Sends to Venice API (minimax-m27) for summarization
4. Appends clean summary to daily log

## Cron Setup

Add to OpenClaw cron or system crontab:

```bash
# Daily at 3 AM
0 3 * * * /home/vpavlin/jimmy-tools/session-summary/summarize-sessions.sh >> /var/log/session-summary.log 2>&1
```

## Why this instead of auto-logging?

- **Auto-logging**: Noisy, tool-call-level detail without context
- **Session summarization**: Meaningful, narrative summary of what was accomplished
- **LLM-powered**: Understands context, connects events, identifies importance

## Example Output

```markdown
## Session Summary (2026-03-19)

- Created 6 OpenClaw skills and pushed to dev-skills repo
- Deep dive into LEZ privacy - analyzed commitment schemes and nullifier keys
- Found Kibby's spel-agent-resources repo with privacy docs
- Discovered missing `wallet account sync-private` step for private transactions
- Set up session cleanup cron to manage 168MB of session files
```
