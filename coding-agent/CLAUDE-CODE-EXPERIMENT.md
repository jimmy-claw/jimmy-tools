# Claude Code + MiniMax Experiment

## Overview
Experiment combining MiniMax M2.5 as the "brain" (main conversation model) with Claude Code as the "hands" (code execution on remote hosts).

## Motivation
- MiniMax is cheap and capable for conversation/planning
- Claude Code is best-in-class for complex coding tasks
- Want to delegate code work without doing it manually

## Current Setup

### Brain (MiniMax M2.5)
- Configured in openclaw.json as `venice/minimax-m25`
- Context window: 202,752 tokens (config), 131K (TUI display - discrepancy unclear)
- Reasoning enabled
- Running on Venice API

### Hands (Claude Code on Crib)
- Host: 192.168.0.152 (jimmy-crib)
- Installed via npm to `~/.npm-global/bin`
- Credentials copied from Pi5 (`~/.claude/.credentials.json`)
- Key flag: `--dangerously-skip-permissions` (required for non-interactive)

### Scripts (jimmy-tools/scripts/)
- `run-claude-code.sh` - Spawn Claude Code on remote host
- `monitor-claude.sh` - Monitor running Claude Code processes
- `setup-coding-agent.sh` - Setup new device for coding agent

## Findings

### What Works
- Setting up Claude Code on remote host was smooth
- `nohup ... &` keeps it alive after SSH disconnect
- `--dangerously-skip-permissions` is required for non-interactive mode

### Issues / Lessons Learned
- **Max turns**: Default 15 is too low for complex tasks. Use 100+
- **Tool permissions**: Claude Code blocks bash by default - need the skip flag
- **Monitoring**: Need to poll logs, can't just set and forget
- **Simple tasks**: Sometimes faster to do manually (rebase, fmt) than delegate

### Observations
- Claude Code on PR #5: stuck on permissions → did manually in 5 min
- PR #18 rebase: hit max turns (15) → rebase actually worked, just couldn't push
- e2e fix: hit max turns (25) → didn't solve the problem
- Context matters: Better prompts = better results

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
   - Kill if stuck (same command repeated)

4. **Avoid low max-turns**:
   - Use 100+ for anything non-trivial
   - Or don't set it at all and kill manually

## Open Questions
- How to pick up where Claude left off if it hits max-turns?
- Better stuck detection (not just command repetition)?
- How to handle SSH auth for git push (HTTPS vs SSH)?
- What's the actual context window discrepancy (202K vs 131K)?

## TODO
- [ ] Improve monitor script with progress detection
- [ ] Add auto-kill for stuck processes
- [ ] Test git push with SSH key on crib
- [ ] Document setup in README