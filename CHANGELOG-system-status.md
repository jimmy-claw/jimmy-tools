# Changelog: jimmy/system-status branch

## Commits (newest first)

1. **b4003dc** — fix: filter bash wrappers and transient processes from claude dashboard
2. **1e300de** — feat: add favicon and fix JS escaping in status dashboard
3. **4035ff2** — feat: parse JSONL conversation logs for task names and activity feed
4. **d47fb93** — fix: read claude logs from ~/.claude/debug/ instead of buffered nohup stdout
5. **29ab6c9** — improve: status monitoring and coding agent scripts
6. **a212786** — fix: escape newline in JS join to prevent syntax error
7. **3d2b857** — Add comprehensive README with architecture diagram and full component docs
8. **c69cf68** — add: CSS styles for Claude process detail cards on status dashboard
9. **2dd85e5** — add: Refresh Now button on status dashboard
10. **c3aba92** — improve: replace meta refresh with JS-based auto-refresh on status dashboard
11. **4fcf3d1** — add: system status dashboard for Pi5 and Crib

## Summary

- **7 files changed**, 1074 insertions, 113 deletions

## Key features added

- **System status dashboard** (`/status`): side-by-side view of Pi5 and Crib showing uptime, load, memory, disk usage, and service health (OpenClaw gateway, Claude processes)
- **JSON API endpoint** (`/system-status`): machine-readable system status for both hosts, fetched by the dashboard via `fetch()` for live updates
- **JSONL conversation log parsing**: extracts task names and last 5 tool-use activities from Claude Code's conversation logs on Crib, displayed as an emoji activity feed in process cards
- **JS-based auto-refresh**: replaced full-page `<meta refresh>` with 30-second `fetch()` polling, live "last refreshed" counter, spinning indicator, and a manual "Refresh Now" button
- **Favicon support**: serves `jimmy-avatar.png` as `/favicon.ico`, cached at startup
- **Hardened JS escaping**: shared `esc()` function for all dynamic values, preventing XSS and JSON injection
- **Bash wrapper filtering**: filters out `bash -c ...` wrapper processes and transient `pgrep` subprocesses from the Claude process list
- **Debug log reading**: reads from `~/.claude/debug/` instead of buffered nohup stdout for real-time log tailing
- **status-check.sh**: new script that gathers Claude process data and writes `~/coding-agent-status.json` for systemd timer consumption
- **run-claude-code.sh changes**: removed auto-kill of existing processes, added `--replace` flag for optional replacement behavior
- **README rewrite**: comprehensive docs with ASCII architecture diagram covering all components (workspace-server, coding-agent, meeting-bot, wake-word, etc.)
- **ARCHITECTURE.md**: replaced `CLAUDE-CODE-EXPERIMENT.md` with updated architecture docs, Sonnet brain model, status monitoring flow, and systemd setup

## Known issues / TODOs

- `import os` at module level in `workspace-server.py` is unused (only referenced inside a string sent to remote SSH)
- `emojis` dict in `inline_format()` (line 193) is defined but never used — looks like an incomplete emoji shortcode feature
- `import re as _re` inside the search handler (line 975) shadows the top-level `re` import unnecessarily
- Hardcoded paths (`/home/vpavlin/...`) and IP addresses (`192.168.0.152`) — not configurable via env vars or config file
- No error handling for SSH timeouts visible to the user on the `/status` page (errors silently produce empty cards)
- The `coding-agent-status` endpoint duplicates SSH logic instead of reusing `_run_ssh()`
