#!/bin/bash
# Gather Claude Code process status and write to ~/coding-agent-status.json
# Designed to be run by systemd timer every minute on Crib

exec python3 - "$HOME/coding-agent-status.json" <<'PYEOF'
import json
import subprocess
import sys
import os
from datetime import datetime

output_path = sys.argv[1]

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return ""

def get_claude_processes():
    pids_raw = run("pgrep -f 'claud[e]'")
    if not pids_raw:
        return []

    procs = []
    for pid_str in pids_raw.splitlines():
        pid = int(pid_str.strip())
        cmd = run(f"ps -o args= -p {pid}")
        # Skip bash wrapper processes
        if cmd.startswith("bash ") or cmd.startswith("/bin/bash "):
            continue

        cpu = run(f"ps -o %cpu= -p {pid}").strip()
        mem = run(f"ps -o %mem= -p {pid}").strip()
        etime = run(f"ps -o etime= -p {pid}").strip()

        # Find log file from stdout fd
        logfile = ""
        try:
            logfile = os.readlink(f"/proc/{pid}/fd/1")
        except Exception:
            pass

        log_tail = []
        if logfile and os.path.isfile(logfile):
            try:
                tail = run(f"tail -5 '{logfile}'")
                log_tail = tail.splitlines() if tail else []
            except Exception:
                pass

        procs.append({
            "pid": pid,
            "cpu": cpu,
            "mem": mem,
            "etime": etime,
            "cmd": cmd,
            "log": logfile,
            "log_tail": log_tail,
        })
    return procs

procs = get_claude_processes()
data = {
    "timestamp": datetime.now().isoformat(),
    "running": len(procs) > 0,
    "count": len(procs),
    "processes": procs,
}

with open(output_path, "w") as f:
    json.dump(data, f, indent=2)
PYEOF
