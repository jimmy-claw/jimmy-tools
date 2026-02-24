# Coding Agent Architecture

## Overview
Sonnet (via OpenClaw) acts as the "brain" for planning and conversation, while Claude Code runs as the "hands" for code execution on remote hosts. A systemd timer on Crib gathers process status every minute, and the Pi5 workspace server displays it in a live dashboard.

## Architecture

```
┌─────────────────────────────────┐
│  Pi5 (OpenClaw — "Brain")       │
│                                 │
│  Sonnet ← planning/conversation │
│  Workspace Server (:8888)       │
│    ├── /status  (dashboard)     │
│    ├── /system-status  (JSON)   │
│    └── /coding-agent-status     │
│                                 │
│  Reads ~/coding-agent-status.json│
│  from Crib via SSH              │
└──────────┬──────────────────────┘
           │ SSH
           ▼
┌─────────────────────────────────┐
│  Crib (192.168.0.152 — "Hands") │
│                                 │
│  Claude Code CLI (nohup)        │
│  status-check.sh (systemd timer)│
│    → ~/coding-agent-status.json │
│                                 │
│  Repos: logos-scaffold,         │
│         lez-framework, etc.     │
└──────────┬──────────────────────┘
           │ HTTP
           ▼
┌─────────────────────────────────┐
│  Workspace Server (:8888)       │
│  File browser + status dashboard│
└─────────────────────────────────┘
```

## Components

### Brain (Sonnet via OpenClaw)
- Configured in openclaw.json
- Handles planning, conversation, task delegation
- Running on Pi5

### Hands (Claude Code on Crib)
- Host: 192.168.0.152 (jimmy-crib)
- Installed via npm to `~/.npm-global/bin`
- Credentials: `~/.claude/.credentials.json`
- Key flag: `--dangerously-skip-permissions` (required for non-interactive)

### Scripts (coding-agent/)
- `run-claude-code.sh` — Spawn Claude Code on remote host via SSH with nohup
  - `--replace` flag to kill existing processes first
  - Default: runs alongside existing processes
  - Writes a `.meta.json` file alongside the log with task metadata
- `monitor-claude.sh` — Monitor running Claude Code processes (terminal)
- `setup-coding-agent.sh` — Bootstrap a new device for coding agent
- `status-check.sh` — Gather process status, write JSON (run by systemd timer)
  - Includes `.meta.json` metadata when available

### Task Metadata
When `run-claude-code.sh` launches a task, it writes a `.meta.json` file alongside the log:
```json
{
  "name": "Fix the auth bug in server.py",
  "started": "2026-02-24T12:00:00Z",
  "log_file": "/home/jimmy/my-task.log",
  "max_turns": 100,
  "pid": 12345
}
```
- File naming: `<log-basename>.meta.json` (e.g. `my-task.log` → `my-task.meta.json`)
- Task name is extracted from the first sentence of the prompt
- Used by `status-check.sh` and the workspace server dashboard for richer display

### Status Monitoring Flow
1. **systemd timer** runs `status-check.sh` every 60s on Crib
2. `status-check.sh` finds claude processes, reads their log tails, merges `.meta.json` metadata, writes `~/coding-agent-status.json`
3. **Workspace server** on Pi5 reads this JSON via SSH (or queries processes directly via SSH, including `.meta.json` files)
4. **/status** dashboard renders process cards with task name, start time, running duration, CPU, memory, and last 5 activities
5. Dashboard auto-refreshes every 30s via JavaScript fetch to `/system-status`

### systemd Units (install on Crib)
- `coding-agent-monitor.service` — oneshot service running status-check.sh
- `coding-agent-monitor.timer` — triggers service every 1 minute

Install:
```bash
cp coding-agent-monitor.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now coding-agent-monitor.timer
```

## Findings

### What Works
- Setting up Claude Code on remote host was smooth
- `nohup ... &` keeps it alive after SSH disconnect
- `--dangerously-skip-permissions` is required for non-interactive mode
- Status monitoring via systemd timer + JSON file is reliable

### Lessons Learned
- **Max turns**: Default 15 is too low for complex tasks. Use 100+
- **Tool permissions**: Claude Code blocks bash by default — need the skip flag
- **Monitoring**: Must actively monitor logs — Claude can get stuck on same command repeated
- **Simple tasks**: Sometimes faster to do manually (rebase, fmt) than delegate

### Observations
- Claude Code on PR #5: stuck on permissions → did manually in 5 min
- PR #18 rebase: hit max turns (15) → rebase actually worked, just couldn't push
- e2e fix: hit max turns (25) → didn't solve the problem
- Context matters: Better prompts with file paths and expected outcomes = better results

## Workflow Recommendations

1. **Know when to delegate vs do**:
   - Complex debugging with file exploration → Claude Code
   - Simple rebase, fmt fix, one-liner → do it manually

2. **Prompt better**:
   - Include file paths
   - Include expected outcome
   - Give more context

3. **Monitor actively**:
   - Use `monitor-claude.sh watch` to see progress
   - Check /status dashboard for live updates
   - Kill if stuck (same command repeated)

4. **Avoid low max-turns**:
   - Use 100+ for anything non-trivial
   - Or don't set it at all and kill manually

## Open Questions
- How to pick up where Claude left off if it hits max-turns?
- Better stuck detection (not just command repetition)?
- How to handle SSH auth for git push (HTTPS vs SSH)?
