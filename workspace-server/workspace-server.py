#!/usr/bin/env python3
"""Lightweight workspace file browser with markdown rendering.
Zero external dependencies — uses only Python stdlib.
Serves the OpenClaw workspace directory with directory listings and markdown preview.
"""

import re
import html
import json
import subprocess
import mimetypes
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, quote
import shlex

WORKSPACE = Path("/home/vpavlin/.openclaw/workspace")
PORT = 8888
CRIB_HOST = "jimmy@192.168.0.152"
SSH_OPTS = ['-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=5']

# Load favicon once at startup
FAVICON_PATH = Path("/home/vpavlin/public/jimmy-avatar.png")
try:
    FAVICON_DATA = FAVICON_PATH.read_bytes()
except Exception:
    FAVICON_DATA = b''

# Simple markdown-to-HTML (covers 90% of common markdown)
def is_table_separator(line):
    """Check if a line is a markdown table separator like |---|---|"""
    return bool(re.match(r'^\|[\s\-:]+(\|[\s\-:]+)+\|?\s*$', line.strip()))

def parse_table_row(line):
    """Parse a markdown table row into cells."""
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    return [cell.strip() for cell in line.split('|')]

def md_to_html(text):
    lines = text.split('\n')
    out = []
    in_code = False
    in_list = False
    in_table = False
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Code blocks
        if line.strip().startswith('```'):
            if in_table:
                out.append('</tbody></table>')
                in_table = False
            if in_code:
                out.append('</code></pre>')
                in_code = False
            else:
                lang = line.strip()[3:]
                out.append(f'<pre><code class="language-{html.escape(lang)}">')
                in_code = True
            i += 1
            continue
        if in_code:
            out.append(html.escape(line))
            i += 1
            continue
        
        # Table detection: current line has pipes and next line is separator
        if not in_table and '|' in line and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            if in_list:
                out.append('</ul>')
                in_list = False
            headers = parse_table_row(line)
            out.append('<table><thead><tr>')
            for h in headers:
                out.append(f'<th>{inline_format(h)}</th>')
            out.append('</tr></thead><tbody>')
            in_table = True
            i += 2  # skip header + separator
            continue
        
        # Table rows
        if in_table:
            if '|' in line and line.strip():
                cells = parse_table_row(line)
                out.append('<tr>')
                for cell in cells:
                    out.append(f'<td>{inline_format(cell)}</td>')
                out.append('</tr>')
                i += 1
                continue
            else:
                out.append('</tbody></table>')
                in_table = False
                # fall through to process this line normally
        
        # Close list if not a list item
        if in_list and not re.match(r'^[\s]*[-*+]\s|^[\s]*\d+\.\s', line) and line.strip():
            out.append('</ul>')
            in_list = False
        
        # Headers
        m = re.match(r'^(#{1,6})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            content = inline_format(m.group(2))
            out.append(f'<h{level}>{content}</h{level}>')
            i += 1
            continue
        
        # Horizontal rule
        if re.match(r'^[-*_]{3,}\s*$', line):
            out.append('<hr>')
            i += 1
            continue
        
        # Unordered list
        m = re.match(r'^[\s]*[-*+]\s+(.*)', line)
        if m:
            if not in_list:
                out.append('<ul>')
                in_list = True
            # Checkbox
            item = m.group(1)
            if item.startswith('[ ] '):
                out.append(f'<li>☐ {inline_format(item[4:])}</li>')
            elif item.startswith('[x] ') or item.startswith('[X] '):
                out.append(f'<li>☑ {inline_format(item[4:])}</li>')
            else:
                out.append(f'<li>{inline_format(item)}</li>')
            i += 1
            continue
        
        # Empty line
        if not line.strip():
            if in_list:
                out.append('</ul>')
                in_list = False
            out.append('<br>')
            i += 1
            continue
        
        # Regular paragraph
        out.append(f'<p>{inline_format(line)}</p>')
        i += 1
    
    if in_list:
        out.append('</ul>')
    if in_table:
        out.append('</tbody></table>')
    if in_code:
        out.append('</code></pre>')
    
    return '\n'.join(out)

def inline_format(text):
    # First convert URLs and markdown links to placeholders to avoid html.escape mangling them
    placeholders = {}
    def save_md_link(m):
        idx = f'__MDLINK{len(placeholders)}__'
        placeholders[idx] = f'<a href="{m.group(2)}" target="_blank">{html.escape(m.group(1))}</a>'
        return idx
    # Save markdown links [text](url) first so URLs inside aren't caught by bare URL regex
    text = re.sub(r'\[(.+?)\]\((https?://[^\s\)]+)\)', save_md_link, text)
    def save_url(m):
        idx = f'__URL{len(placeholders)}__'
        url = m.group(0)
        placeholders[idx] = f'<a href="{url}" target="_blank">{html.escape(url)}</a>'
        return idx
    text = re.sub(r'https?://[^\s<>\)]+', save_url, text)
    text = html.escape(text)
    # Restore all placeholders (already contain safe HTML)
    for idx, replacement in placeholders.items():
        text = text.replace(idx, replacement)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
    # Inline code
    text = re.sub(r'`(.+?)`', r'<code class="inline">\1</code>', text)
    # Links
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2" target="_blank">\1</a>', text)
    return text

CSS = """
:root { --bg: #1a1b26; --fg: #c0caf5; --accent: #7aa2f7; --dim: #565f89;
        --card: #24283b; --border: #3b4261; --green: #9ece6a; --red: #f7768e; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif;
       background: var(--bg); color: var(--fg); line-height: 1.6;
       max-width: 900px; margin: 0 auto; padding: 20px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
h1, h2, h3, h4 { color: var(--accent); margin: 1em 0 0.5em; }
h1 { border-bottom: 1px solid var(--border); padding-bottom: 0.3em; }
p { margin: 0.3em 0; }
pre { background: var(--card); padding: 16px; border-radius: 8px;
      overflow-x: auto; margin: 1em 0; border: 1px solid var(--border); }
code { font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 0.9em; }
code.inline { background: var(--card); padding: 2px 6px; border-radius: 4px; }
ul { padding-left: 1.5em; margin: 0.5em 0; }
li { margin: 0.2em 0; }
hr { border: none; border-top: 1px solid var(--border); margin: 1.5em 0; }
.breadcrumb { padding: 10px 0; color: var(--dim); font-size: 0.9em; margin-bottom: 1em; }
.breadcrumb a { color: var(--accent); }
.dir-list { list-style: none; padding: 0; }
.dir-list li { padding: 8px 12px; border-bottom: 1px solid var(--border); }
.dir-list li:hover { background: var(--card); }
.dir-list .icon { margin-right: 8px; }
.file-meta { color: var(--dim); font-size: 0.85em; float: right; }
.sort-bar { background: var(--card); padding: 8px 16px; border-radius: 8px; margin-bottom: 12px; font-size: 0.9em; color: var(--dim); }
.sort-bar a { color: var(--accent); margin: 0 4px; }
.sort-bar a:hover { text-decoration: underline; }
.nav { background: var(--card); padding: 12px 20px; border-radius: 8px;
       margin-bottom: 20px; border: 1px solid var(--border); }
.nav a { margin-right: 16px; }
strong { color: var(--green); }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid var(--border); padding: 8px 12px; text-align: left; }
th { background: var(--card); color: var(--accent); font-weight: 600; }
tr:nth-child(even) { background: rgba(36, 40, 59, 0.5); }
tr:hover { background: var(--card); }
"""

def _run_local(cmd, timeout=5):
    """Run a local command, return stdout or error string."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else f"error: {r.stderr.strip()}"
    except Exception as e:
        return f"error: {e}"


def _run_ssh(cmd_str, timeout=10):
    """Run a command on crib via SSH, return stdout or error string."""
    try:
        r = subprocess.run(
            ['ssh'] + SSH_OPTS + [CRIB_HOST, cmd_str],
            capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip() if r.returncode == 0 else f"error: {r.stderr.strip()}"
    except Exception as e:
        return f"error: {e}"


def _parse_uptime(raw):
    """Extract uptime string and load averages from `uptime` output."""
    info = {"raw": raw}
    m = re.search(r'up\s+(.+?),\s+\d+\s+user', raw)
    if m:
        info["uptime"] = m.group(1).strip()
    m = re.search(r'load average:\s*(.+)', raw)
    if m:
        info["load_avg"] = m.group(1).strip()
    return info


def _parse_memory(raw):
    """Parse `free -h` output into dict."""
    info = {"raw": raw}
    for line in raw.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            info["total"] = parts[1]
            info["used"] = parts[2]
            info["available"] = parts[6] if len(parts) > 6 else parts[3]
    return info


def _parse_disk(raw):
    """Parse `df -h /` output into dict."""
    info = {"raw": raw}
    lines = raw.strip().splitlines()
    if len(lines) >= 2:
        parts = lines[1].split()
        info["total"] = parts[1]
        info["used"] = parts[2]
        info["available"] = parts[3]
        info["use_pct"] = parts[4]
    return info


def get_pi5_status():
    """Gather local Pi5 system status."""
    status = {"host": "Pi5", "ts": datetime.now().isoformat()}
    status["uptime"] = _parse_uptime(_run_local(["uptime"]))
    status["memory"] = _parse_memory(_run_local(["free", "-h"]))
    status["disk"] = _parse_disk(_run_local(["df", "-h", "/"]))

    # OpenClaw gateway status
    gw = _run_local(["pgrep", "-fa", "openclaw"])
    if gw.startswith("error:") or not gw:
        status["openclaw_gateway"] = {"running": False, "detail": gw or "not found"}
    else:
        status["openclaw_gateway"] = {"running": True, "detail": gw}

    return status


def _clean_debug_line(line):
    """Shorten a claude debug log line for dashboard display.
    '2026-02-24T12:11:48.120Z [DEBUG] executePreToolHooks called for tool: Bash'
    becomes '12:11:48 Tool: Bash'
    """
    # Extract time HH:MM:SS from ISO timestamp
    m = re.match(r'\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}:\d{2})\.\d+Z\s+\[(\w+)\]\s+(.*)', line)
    if not m:
        return line.strip()
    time_str, level, msg = m.group(1), m.group(2), m.group(3)
    # Simplify common patterns
    tool_m = re.search(r'called for tool:\s*(\w+)', msg)
    if tool_m:
        return f"{time_str} Tool: {tool_m.group(1)}"
    if '[API:' in msg:
        return f"{time_str} API request"
    if level == 'ERROR':
        return f"{time_str} ERROR: {msg[:80]}"
    if level == 'WARN':
        return f"{time_str} WARN: {msg[:80]}"
    return f"{time_str} {msg[:60]}"


# Python script that runs on crib via SSH to parse JSONL conversation logs
JSONL_PARSER_SCRIPT = r'''
import json, glob, os, sys, time
from collections import deque

files = []
for pattern in [
    os.path.expanduser("~/.claude/projects/*/*.jsonl"),
    os.path.expanduser("~/.claude/projects/*/*/*.jsonl"),
]:
    files.extend(glob.glob(pattern))

if not files:
    sys.exit(0)

files.sort(key=os.path.getmtime, reverse=True)
jf = files[0]

if time.time() - os.path.getmtime(jf) > 7200:
    sys.exit(0)

task = ""
try:
    with open(jf) as f:
        for raw in f:
            s = raw.strip()
            if not s:
                continue
            try:
                o = json.loads(s)
                t = o.get("type", "")
                if t == "human" or o.get("role") == "user":
                    c = o.get("message", o.get("content", ""))
                    if isinstance(c, dict):
                        c = c.get("content", c.get("text", ""))
                    if isinstance(c, list):
                        for b in c:
                            if isinstance(b, dict) and b.get("type") == "text":
                                c = b["text"]
                                break
                            elif isinstance(b, str):
                                c = b
                                break
                    if isinstance(c, str) and c.strip():
                        first = c.strip().split("\n")[0]
                        for end in [". ", "! ", "? "]:
                            idx = first.find(end)
                            if 0 < idx < 100:
                                first = first[:idx+1]
                                break
                        task = first[:120]
                        break
            except Exception:
                continue
except Exception:
    pass

acts = []
try:
    recent = deque(maxlen=200)
    with open(jf) as f:
        for line in f:
            recent.append(line)
    for raw in reversed(list(recent)):
        if len(acts) >= 10:
            break
        s = raw.strip()
        if not s:
            continue
        try:
            o = json.loads(s)
            t = o.get("type", "")
            if t == "assistant" or o.get("role") == "assistant":
                c = o.get("message", o.get("content", []))
                if isinstance(c, dict):
                    c = c.get("content", [])
                if isinstance(c, list):
                    tus = [b for b in c if isinstance(b, dict) and b.get("type") == "tool_use"]
                    for b in reversed(tus):
                        if len(acts) >= 10:
                            break
                        n = b.get("name", "?")
                        inp = b.get("input", {})
                        if n == "Read":
                            p = inp.get("file_path", "?")
                            sp = "/".join(p.split("/")[-2:]) if "/" in p else p
                            d = "\U0001f50d Read " + sp
                        elif n in ("Write", "Edit"):
                            p = inp.get("file_path", "?")
                            sp = "/".join(p.split("/")[-2:]) if "/" in p else p
                            d = "\u270f\ufe0f  " + n + " " + sp
                        elif n == "Bash":
                            cm = inp.get("command", "?")
                            d = "\u26a1 Bash: " + cm[:60]
                        elif n == "Grep":
                            pa = inp.get("pattern", "?")
                            d = "\U0001f50d Grep: " + pa[:50]
                        elif n == "Glob":
                            pa = inp.get("pattern", "?")
                            d = "\U0001f4c2 Glob: " + pa[:50]
                        elif n == "Task":
                            td = inp.get("description", "?")
                            d = "\U0001f916 Task: " + td[:50]
                        elif n == "WebFetch":
                            u = inp.get("url", "?")
                            d = "\U0001f310 Fetch: " + u[:50]
                        elif n == "TodoWrite":
                            d = "\U0001f4cb Updated todo list"
                        elif n == "WebSearch":
                            q = inp.get("query", "?")
                            d = "\U0001f50e Search: " + q[:50]
                        else:
                            d = "\U0001f527 " + n
                        acts.append(d)
        except Exception:
            continue
except Exception:
    pass

acts.reverse()
print(json.dumps({"task": task, "activities": acts, "file": os.path.basename(jf)}))
'''


def _get_jsonl_data():
    """Parse latest JSONL conversation log from crib via SSH."""
    try:
        raw = _run_ssh(f"python3 -c {shlex.quote(JSONL_PARSER_SCRIPT)}", timeout=10)
        if raw and not raw.startswith("error:"):
            return json.loads(raw)
    except (json.JSONDecodeError, Exception):
        pass
    return None


def _extract_task_from_cmd(cmd):
    """Extract task description from claude command line as fallback."""
    m = re.search(r'-p\s+"([^"]+)"', cmd)
    if m:
        return m.group(1)[:120]
    m = re.search(r"-p\s+'([^']+)'", cmd)
    if m:
        return m.group(1)[:120]
    return ""


def _parse_claude_processes(raw):
    """Parse structured claude process output into a list of process dicts."""
    procs = []
    if not raw or raw.startswith("error:"):
        return procs
    current = None
    tail_lines = []
    in_tail = False
    for line in raw.splitlines():
        if line == "---PROC---":
            if current:
                current["log_tail"] = tail_lines
                procs.append(current)
            current = {}
            tail_lines = []
            in_tail = False
        elif line == "---TAIL---":
            in_tail = True
        elif line == "---ENDTAIL---":
            in_tail = False
        elif in_tail:
            tail_lines.append(_clean_debug_line(line))
        elif current is not None and ":" in line:
            key, _, val = line.partition(":")
            current[key.strip().lower()] = val.strip()
    if current:
        current["log_tail"] = tail_lines
        procs.append(current)
    # Filter out bash wrappers and transient processes with no command
    procs = [p for p in procs if p.get("cmd") and not p["cmd"].startswith("bash") and not p["cmd"].startswith("/bin/bash")]
    return procs


def _get_meta_files():
    """Fetch all .meta.json files from crib via SSH, returned as {pid: metadata_dict}."""
    meta_script = (
        'for f in ~/*.meta.json; do '
        '  [ -f "$f" ] || continue; '
        '  echo "---META---"; '
        '  cat "$f" 2>/dev/null; '
        'done'
    )
    try:
        raw = _run_ssh(meta_script, timeout=10)
        if not raw or raw.startswith("error:"):
            return {}
        result = {}
        for block in raw.split("---META---"):
            block = block.strip()
            if not block:
                continue
            try:
                meta = json.loads(block)
                pid = meta.get("pid")
                if pid is not None:
                    result[str(pid)] = meta
            except (json.JSONDecodeError, Exception):
                continue
        return result
    except Exception:
        return {}


def get_crib_status():
    """Gather crib (192.168.0.152) system status via SSH."""
    status = {"host": "Crib", "ts": datetime.now().isoformat()}
    status["uptime"] = _parse_uptime(_run_ssh("uptime"))
    status["memory"] = _parse_memory(_run_ssh("free -h"))
    status["disk"] = _parse_disk(_run_ssh("df -h /"))

    # Claude processes — gather detailed info per process (skip bash wrappers)
    # Read logs from ~/.claude/debug/ (latest .txt) instead of nohup stdout (which buffers)
    claude_script = (
        'for pid in $(pgrep -f "claud[e]" 2>/dev/null); do '
        '  cmd=$(ps -o args= -p $pid 2>/dev/null); '
        '  [ -z "$cmd" ] && continue; '
        '  case "$cmd" in bash*|/bin/bash*) continue;; esac; '
        '  echo "---PROC---"; '
        '  echo "PID:$pid"; '
        '  echo "CPU:$(ps -o %cpu= -p $pid 2>/dev/null)"; '
        '  echo "MEM:$(ps -o %mem= -p $pid 2>/dev/null)"; '
        '  echo "ETIME:$(ps -o etime= -p $pid 2>/dev/null)"; '
        '  echo "CMD:$cmd"; '
        '  debuglog=$(ls -t ~/.claude/debug/*.txt 2>/dev/null | head -1); '
        '  echo "LOG:${debuglog:-none}"; '
        '  if [ -n "$debuglog" ] && [ -f "$debuglog" ]; then '
        '    echo "---TAIL---"; '
        '    tail -50 "$debuglog" 2>/dev/null | grep -E "called for tool:|\\[API:|\\[ERROR\\]|\\[WARN\\]" | tail -8; '
        '    echo "---ENDTAIL---"; '
        '  fi; '
        'done'
    )
    claude_raw = _run_ssh(claude_script, timeout=15)
    procs = _parse_claude_processes(claude_raw)
    # Enrich with JSONL conversation data (task name + activity feed)
    if procs:
        jsonl_data = _get_jsonl_data()
        meta_files = _get_meta_files()
        if jsonl_data:
            procs[0]["task_name"] = jsonl_data.get("task", "")
            procs[0]["activities"] = jsonl_data.get("activities", [])
        # Enrich with .meta.json data (task name, start time)
        for p in procs:
            pid_str = p.get("pid", "")
            meta = meta_files.get(pid_str, {})
            if meta:
                p["meta"] = meta
                if not p.get("task_name") and meta.get("name"):
                    p["task_name"] = meta["name"]
                if meta.get("started"):
                    p["started"] = meta["started"]
                if meta.get("max_turns"):
                    p["max_turns"] = meta["max_turns"]
            if not p.get("task_name"):
                p["task_name"] = _extract_task_from_cmd(p.get("cmd", ""))
        status["claude_processes"] = {"running": True, "count": len(procs), "processes": procs}
    else:
        status["claude_processes"] = {"running": False, "count": 0, "processes": []}

    return status


AGENT_BINARY = "/home/vpavlin/openclaw-coding-agent/target/release/openclaw-agent"
TASKS_META_DIR = Path("/home/vpavlin/.local/share/openclaw/tasks")


def _run_agent_cmd(args, timeout=8):
    """Run openclaw-agent locally (native arm64 build on Pi5)."""
    return subprocess.run([AGENT_BINARY] + args, capture_output=True, text=True, timeout=timeout)


def _load_task_meta_remote(task_id):
    """Load .meta.json for a task from local tasks dir."""
    meta_file = TASKS_META_DIR / f"{task_id}.meta.json"
    try:
        if meta_file.exists():
            return json.loads(meta_file.read_text())
    except Exception:
        pass
    return {}


def _check_executor_reachable(executor):
    """Quick reachability check for an executor."""
    etype = executor.get("type", "")
    host = executor.get("host")
    if etype == "ssh" and host:
        try:
            r = subprocess.run(
                ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=3',
                 '-o', 'BatchMode=yes', f'jimmy@{host}', 'echo ok'],
                capture_output=True, text=True, timeout=4
            )
            return r.returncode == 0 and r.stdout.strip() == "ok"
        except Exception:
            return False
    elif etype == "local":
        return True  # always reachable
    elif etype == "container":
        # Check if docker/podman is available
        try:
            r = subprocess.run(['docker', 'info'], capture_output=True, timeout=5)
            return r.returncode == 0
        except Exception:
            try:
                r = subprocess.run(['podman', 'info'], capture_output=True, timeout=5)
                return r.returncode == 0
            except Exception:
                return False
    return False


def _load_task_meta(task_id):
    """Load prompt and extra info from .meta.json for a task (tries remote crib first)."""
    return _load_task_meta_remote(task_id)


def get_coding_agent_status():
    """Get coding agent tasks and executor status."""
    result = {
        "executors": [],
        "tasks": [],
        "summary": {"running": 0, "completed": 0, "failed": 0, "total": 0},
        "ts": datetime.now().isoformat(),
    }

    # Get executors
    try:
        r = _run_agent_cmd(["executors", "--json"])
        if r.returncode == 0:
            executors = json.loads(r.stdout)
            for ex in executors:
                ex["reachable"] = _check_executor_reachable(ex)
            result["executors"] = executors
    except Exception as e:
        result["executors_error"] = str(e)

    # Get tasks
    try:
        r = _run_agent_cmd(["list", "--jsonl"])
        if r.returncode == 0:
            tasks = []
            for line in r.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    task = json.loads(line)
                    tid = task.get("task_id", "")
                    meta = _load_task_meta(tid)
                    # Enrich with prompt/command and task_type from meta
                    prompt = meta.get("prompt", "")
                    task["prompt"] = prompt[:120] if prompt else ""
                    if not task.get("task_type") and meta.get("task_type"):
                        task["task_type"] = meta["task_type"]
                    if not task.get("workspace") and meta.get("workspace"):
                        task["workspace"] = meta["workspace"]
                    # Runtime calculation
                    started = task.get("started_at") or meta.get("started_at")
                    finished = task.get("finished_at") or meta.get("finished_at")
                    if started:
                        try:
                            from datetime import timezone
                            start_dt = datetime.fromisoformat(started.replace('Z', '+00:00'))
                            if finished:
                                end_dt = datetime.fromisoformat(finished.replace('Z', '+00:00'))
                            else:
                                end_dt = datetime.now(timezone.utc)
                            delta = int((end_dt - start_dt).total_seconds())
                            if delta < 60:
                                task["runtime"] = f"{delta}s"
                            elif delta < 3600:
                                task["runtime"] = f"{delta // 60}m {delta % 60}s"
                            else:
                                task["runtime"] = f"{delta // 3600}h {(delta % 3600) // 60}m"
                        except Exception:
                            task["runtime"] = ""
                    else:
                        task["runtime"] = ""
                    tasks.append(task)
                    # Count by status
                    status = task.get("status", "")
                    if status in result["summary"]:
                        result["summary"][status] += 1
                    result["summary"]["total"] += 1
                except Exception:
                    continue
            result["tasks"] = tasks
    except Exception as e:
        result["tasks_error"] = str(e)

    return result


STATUS_DASHBOARD_CSS = """
.status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }
@media (max-width: 800px) { .status-grid { grid-template-columns: 1fr; } }
.host-card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; }
.host-card h2 { margin-top: 0; font-size: 1.3em; }
.stat-row { display: flex; justify-content: space-between; padding: 8px 0;
            border-bottom: 1px solid var(--border); font-size: 0.9em; }
.stat-row:last-child { border-bottom: none; }
.stat-label { color: var(--dim); }
.stat-value { text-align: right; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: 600; }
.badge-up { background: rgba(158,206,106,0.2); color: var(--green); }
.badge-down { background: rgba(247,118,142,0.2); color: var(--red); }
.refresh-note { color: var(--dim); font-size: 0.8em; text-align: center; margin-top: 16px; }
.pct-bar { background: var(--bg); border-radius: 4px; height: 8px; margin-top: 4px; }
.pct-fill { height: 100%; border-radius: 4px; background: var(--accent); }
.proc-details { margin-top: 8px; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.proc-details summary { padding: 10px 14px; cursor: pointer; color: var(--fg);
                         background: var(--bg); list-style: none; }
.proc-details summary::-webkit-details-marker { display: none; }
.proc-details summary::before { content: '\u25b6 '; font-size: 0.7em; }
.proc-details[open] summary::before { content: '\u25bc '; }
.proc-info { padding: 8px 12px; font-size: 0.82em; }
.proc-cmd { color: var(--dim); word-break: break-all; margin-bottom: 4px; }
.proc-log-path { color: var(--dim); font-size: 0.9em; margin-bottom: 6px; }
.proc-log-tail { background: #0d1117; padding: 10px 14px; border-radius: 6px; font-size: 0.82em;
                  overflow-x: auto; margin: 0; border: 1px solid var(--border); white-space: pre-wrap;
                  word-break: break-all; font-family: 'JetBrains Mono', 'Fira Code', monospace;
                  line-height: 1.6; color: #8b949e; }
.proc-none { color: var(--dim); font-size: 0.85em; padding: 8px 0; font-style: italic; }
.proc-task { font-weight: 600; color: var(--fg); display: block; margin-bottom: 2px;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.proc-stats { font-size: 0.8em; color: var(--dim); }
.proc-activity { background: #0d1117; border: 1px solid var(--border); border-radius: 6px;
                 padding: 10px 14px; font-family: 'JetBrains Mono', 'Fira Code', monospace;
                 font-size: 0.82em; line-height: 1.8; overflow-x: auto; }
.activity-line { white-space: nowrap; color: #8b949e; }
.proc-start-time { color: var(--dim); font-size: 0.85em; padding: 4px 0 8px 0; font-style: italic; }
"""

AGENT_PANEL_CSS = """
.agent-panel { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-top: 20px; }
.agent-panel h2 { margin-top: 0; font-size: 1.3em; }
.executor-list { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }
.executor-chip { display: flex; align-items: center; gap: 8px; background: var(--bg); border: 1px solid var(--border);
                  border-radius: 8px; padding: 8px 14px; font-size: 0.85em; }
.executor-chip .ex-name { font-weight: 600; color: var(--fg); }
.executor-chip .ex-type { color: var(--dim); font-size: 0.9em; }
.executor-chip .ex-host { color: var(--dim); font-size: 0.85em; margin-left: 2px; }
.reach-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.reach-dot.up { background: var(--green); box-shadow: 0 0 6px rgba(158,206,106,0.5); }
.reach-dot.down { background: var(--red); }
.reach-dot.unknown { background: var(--dim); }
.agent-summary { display: flex; gap: 16px; margin: 10px 0 14px; font-size: 0.85em; color: var(--dim); }
.agent-summary .s-item { display: flex; align-items: center; gap: 5px; }
.task-table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
.task-table th { background: var(--bg); color: var(--accent); font-weight: 600; padding: 8px 10px;
                  text-align: left; border-bottom: 2px solid var(--border); }
.task-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.task-table tr:last-child td { border-bottom: none; }
.task-table tr:hover td { background: rgba(36,40,59,0.5); }
.task-id { font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 0.9em; color: var(--dim); }
.task-prompt { color: var(--fg); max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.task-prompt.empty { color: var(--dim); font-style: italic; }
.dim { color: var(--dim); font-size: 0.85em; }
.badge-running { background: rgba(224,175,104,0.2); color: #e0af68; }
.badge-completed { background: rgba(158,206,106,0.2); color: var(--green); }
.badge-failed { background: rgba(247,118,142,0.2); color: var(--red); }
.task-runtime { color: var(--dim); font-size: 0.85em; white-space: nowrap; }
.no-tasks { color: var(--dim); font-style: italic; padding: 14px 0; text-align: center; }
"""


def _render_host_card(data):
    """Render one host card as HTML."""
    host = html.escape(data.get("host", "?"))
    h = f'<div class="host-card"><h2>{host}</h2>'

    # Uptime + load
    up = data.get("uptime", {})
    uptime_str = html.escape(up.get("uptime", up.get("raw", "?")))
    load_str = html.escape(up.get("load_avg", "?"))
    h += f'<div class="stat-row"><span class="stat-label">Uptime</span><span class="stat-value">{uptime_str}</span></div>'
    h += f'<div class="stat-row"><span class="stat-label">Load Avg</span><span class="stat-value">{load_str}</span></div>'

    # Memory
    mem = data.get("memory", {})
    mem_str = f'{html.escape(mem.get("used", "?"))} / {html.escape(mem.get("total", "?"))}'
    h += f'<div class="stat-row"><span class="stat-label">Memory</span><span class="stat-value">{mem_str}</span></div>'

    # Disk
    disk = data.get("disk", {})
    disk_str = f'{html.escape(disk.get("used", "?"))} / {html.escape(disk.get("total", "?"))}'
    pct = disk.get("use_pct", "0%")
    pct_num = int(pct.replace('%', '')) if pct.replace('%', '').isdigit() else 0
    bar_color = 'var(--green)' if pct_num < 70 else ('var(--accent)' if pct_num < 90 else 'var(--red)')
    h += f'<div class="stat-row"><span class="stat-label">Disk</span><span class="stat-value">{disk_str} ({html.escape(pct)})</span></div>'
    h += f'<div class="pct-bar"><div class="pct-fill" style="width:{pct_num}%;background:{bar_color}"></div></div>'

    # Service status (OpenClaw or Claude)
    if "openclaw_gateway" in data:
        gw = data["openclaw_gateway"]
        running = gw.get("running", False)
        badge = '<span class="badge badge-up">RUNNING</span>' if running else '<span class="badge badge-down">STOPPED</span>'
        h += f'<div class="stat-row"><span class="stat-label">OpenClaw GW</span><span class="stat-value">{badge}</span></div>'

    if "claude_processes" in data:
        cp = data["claude_processes"]
        running = cp.get("running", False)
        count = cp.get("count", 0)
        if running:
            badge = f'<span class="badge badge-up">{count} RUNNING</span>'
        else:
            badge = '<span class="badge badge-down">NONE</span>'
        h += f'<div class="stat-row"><span class="stat-label">Claude Procs</span><span class="stat-value">{badge}</span></div>'

        procs = cp.get("processes", [])
        if procs:
            for p in procs:
                pid = html.escape(p.get("pid", "?"))
                cpu = html.escape(p.get("cpu", "?"))
                mem = html.escape(p.get("mem", "?"))
                etime = html.escape(p.get("etime", "?"))
                task_name = html.escape(p.get("task_name", ""))
                started = p.get("started", "")
                max_turns = p.get("max_turns", "")
                activities = p.get("activities", [])
                header = task_name if task_name else f"PID {pid}"
                h += f'<details class="proc-details" open>'
                h += f'<summary><span class="proc-task">{header}</span>'
                h += f'<span class="proc-stats">CPU {cpu}% · MEM {mem}% · up {etime}'
                if task_name:
                    h += f' · PID {pid}'
                if max_turns:
                    h += f' · max {html.escape(str(max_turns))} turns'
                h += '</span></summary>'
                h += '<div class="proc-info">'
                if started:
                    # Calculate running duration from start time
                    try:
                        start_dt = datetime.fromisoformat(started.replace('Z', '+00:00'))
                        from datetime import timezone
                        now_utc = datetime.now(timezone.utc)
                        delta = now_utc - start_dt
                        hours, remainder = divmod(int(delta.total_seconds()), 3600)
                        minutes, secs = divmod(remainder, 60)
                        if hours > 0:
                            duration_str = f"{hours}h {minutes}m"
                        elif minutes > 0:
                            duration_str = f"{minutes}m {secs}s"
                        else:
                            duration_str = f"{secs}s"
                        start_display = start_dt.strftime("%H:%M:%S UTC")
                        h += f'<div class="proc-start-time">Started {html.escape(start_display)} · Running for {html.escape(duration_str)}</div>'
                    except Exception:
                        h += f'<div class="proc-start-time">Started {html.escape(started)}</div>'
                if activities:
                    h += '<div class="proc-activity">'
                    for a in activities:
                        h += f'<div class="activity-line">{html.escape(a)}</div>'
                    h += '</div>'
                else:
                    tail = p.get("log_tail", [])
                    if tail:
                        h += '<pre class="proc-log-tail">' + html.escape('\n'.join(tail)) + '</pre>'
                    else:
                        h += '<div class="proc-none">No activity yet</div>'
                h += '</div></details>'
        elif not running:
            h += '<div class="proc-none">No active tasks</div>'

    h += '</div>'
    return h


def _render_agent_panel(agent_data):
    """Render the Coding Agent Tasks panel as HTML."""
    err = agent_data.get("executors_error") or agent_data.get("tasks_error")
    h = '<div class="agent-panel" id="agent-panel">'
    h += '<h2>🤖 Coding Agent Tasks</h2>'

    if err and not agent_data.get("executors") and not agent_data.get("tasks"):
        h += f'<p style="color:var(--red)">Error: {html.escape(str(err))}</p>'
        h += '</div>'
        return h

    # Executors
    executors = agent_data.get("executors", [])
    if executors:
        h += '<div class="executor-list">'
        for ex in executors:
            name = html.escape(ex.get("name", "?"))
            etype = html.escape(ex.get("type", "?"))
            host = ex.get("host")
            reachable = ex.get("reachable")
            if reachable is True:
                dot_cls = "up"
                dot_title = "Reachable"
            elif reachable is False:
                dot_cls = "down"
                dot_title = "Unreachable"
            else:
                dot_cls = "unknown"
                dot_title = "Unknown"
            h += f'<div class="executor-chip">'
            h += f'<span class="reach-dot {dot_cls}" title="{dot_title}"></span>'
            h += f'<span class="ex-name">{name}</span>'
            h += f'<span class="ex-type">{etype}</span>'
            if host:
                h += f'<span class="ex-host">({html.escape(host)})</span>'
            h += '</div>'
        h += '</div>'

    # Summary
    s = agent_data.get("summary", {})
    total = s.get("total", 0)
    running = s.get("running", 0)
    completed = s.get("completed", 0)
    failed = s.get("failed", 0)
    h += '<div class="agent-summary">'
    h += f'<span class="s-item"><span class="badge badge-running">{running} running</span></span>'
    h += f'<span class="s-item"><span class="badge badge-completed">{completed} completed</span></span>'
    h += f'<span class="s-item"><span class="badge badge-failed">{failed} failed</span></span>'
    h += f'<span class="s-item" style="margin-left:auto">{total} total</span>'
    h += '</div>'

    # Tasks table
    tasks = agent_data.get("tasks", [])
    if not tasks:
        h += '<div class="no-tasks">No tasks yet</div>'
    else:
        h += '<table class="task-table"><thead><tr>'
        h += '<th>ID</th><th>Type</th><th>Executor</th><th>Status</th><th>Runtime</th><th>Command / Prompt</th>'
        h += '</tr></thead><tbody>'
        for task in tasks[:20]:  # limit to 20 most recent
            tid = task.get("task_id", "?")
            short_id = tid[:8] if len(tid) >= 8 else tid
            executor = html.escape(task.get("executor", "?"))
            executor_type = task.get("executor_type", "")
            task_type = task.get("task_type", "claude_code")
            type_icon = "⚙️" if task_type == "shell_command" else "🤖"
            type_label = "shell" if task_type == "shell_command" else "claude"
            status = task.get("status", "?")
            runtime = html.escape(task.get("runtime", ""))
            prompt = task.get("prompt", "")
            workspace = task.get("workspace", "")
            if status == "running":
                badge_cls = "badge-running"
                status_label = "running"
            elif status == "completed":
                badge_cls = "badge-completed"
                status_label = "done"
            elif status == "failed":
                badge_cls = "badge-failed"
                status_label = "failed"
            else:
                badge_cls = "badge"
                status_label = html.escape(status)
            prompt_cls = "task-prompt" if prompt else "task-prompt empty"
            prompt_display = html.escape(prompt) if prompt else "no prompt"
            tooltip = html.escape(prompt)
            if workspace:
                tooltip = html.escape(f"[{workspace}] {prompt}")
            executor_display = executor
            if executor_type:
                executor_display = f'{executor} <span class="dim">({html.escape(executor_type)})</span>'
            h += '<tr>'
            h += f'<td><span class="task-id">{html.escape(short_id)}</span></td>'
            h += f'<td><span title="{html.escape(task_type)}">{type_icon} {type_label}</span></td>'
            h += f'<td>{executor_display}</td>'
            h += f'<td><span class="badge {badge_cls}">{status_label}</span></td>'
            h += f'<td><span class="task-runtime">{runtime}</span></td>'
            h += f'<td><span class="{prompt_cls}" title="{tooltip}">{prompt_display}</span></td>'
            h += '</tr>'
        h += '</tbody></table>'

    h += '</div>'
    return h


def get_subagent_status():
    """Read active sub-agent sessions from OpenClaw sessions.json index."""
    import time
    index_file = Path("/home/vpavlin/.openclaw/agents/main/sessions/sessions.json")
    if not index_file.exists():
        return {"agents": [], "error": "no sessions index"}

    try:
        with open(index_file) as f:
            all_sessions = json.load(f)
    except Exception as e:
        return {"agents": [], "error": str(e)}

    agents = []
    now = time.time()
    for key, rec in all_sessions.items():
        if "subagent" not in key:
            continue
        label = rec.get("label") or key.split(":")[-1][:32]
        updated_ms = rec.get("updatedAt", 0)
        age_s = int(now - updated_ms / 1000) if updated_ms else -1
        # Consider active if updated within last 30 minutes
        active = age_s >= 0 and age_s < 1800
        total_tokens = rec.get("totalTokens", 0)
        model = rec.get("model", "")
        agents.append({
            "key": key,
            "label": label,
            "active": active,
            "age_s": age_s,
            "model": model,
            "total_tokens": total_tokens,
        })

    # Sort: active first, then by recency
    agents.sort(key=lambda a: (not a["active"], a["age_s"]))
    # Return only last 20
    return {"agents": agents[:20]}


def render_status_page(pi5, crib):
    """Build the full status dashboard HTML."""
    body = '<h1>System Status <span id="spinner" style="display:none">⟳</span> <button id="refresh-btn" onclick="manualRefresh()" title="Refresh Now">Refresh Now</button></h1>'
    body += f'<div id="status-grid" class="status-grid">{_render_host_card(pi5)}{_render_host_card(crib)}</div>'

    # Coding agent panel — placeholder, filled by JS via /coding-agent-status
    body += '<div class="agent-panel" id="agent-panel"><h2>🤖 Coding Agent Tasks</h2><div class="no-tasks" id="agent-loading">Loading…</div></div>'

    # Sub-agents panel — placeholder, filled by JS via /subagent-status
    body += '<div class="agent-panel" id="subagent-panel"><h2>🧠 Active Sub-Agents</h2><div class="no-tasks" id="subagent-loading">Loading…</div></div>'

    body += '<div class="refresh-note" id="refresh-note">Last refreshed: just now · Auto-refreshes every 30s</div>'

    status_js = """
<script>
(function() {
  let lastRefreshTime = Date.now();
  const spinner = document.getElementById('spinner');
  const grid = document.getElementById('status-grid');
  const note = document.getElementById('refresh-note');

  function esc(s) {
    return String(s==null?'?':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  function renderHostCard(data) {
    var host = esc(data.host);
    var h = '<div class="host-card"><h2>' + host + '</h2>';
    var up = data.uptime || {};
    h += '<div class="stat-row"><span class="stat-label">Uptime</span><span class="stat-value">' + esc(up.uptime || up.raw) + '</span></div>';
    h += '<div class="stat-row"><span class="stat-label">Load Avg</span><span class="stat-value">' + esc(up.load_avg) + '</span></div>';
    var mem = data.memory || {};
    h += '<div class="stat-row"><span class="stat-label">Memory</span><span class="stat-value">' + esc(mem.used) + ' / ' + esc(mem.total) + '</span></div>';
    var disk = data.disk || {};
    var pct = disk.use_pct || '0%';
    var pctNum = parseInt(pct) || 0;
    var barColor = pctNum < 70 ? 'var(--green)' : (pctNum < 90 ? 'var(--accent)' : 'var(--red)');
    h += '<div class="stat-row"><span class="stat-label">Disk</span><span class="stat-value">' + esc(disk.used) + ' / ' + esc(disk.total) + ' (' + esc(pct) + ')</span></div>';
    h += '<div class="pct-bar"><div class="pct-fill" style="width:' + pctNum + '%;background:' + barColor + '"></div></div>';
    if (data.openclaw_gateway) {
      var gw = data.openclaw_gateway;
      var badge = gw.running
        ? '<span class="badge badge-up">RUNNING</span>'
        : '<span class="badge badge-down">STOPPED</span>';
      h += '<div class="stat-row"><span class="stat-label">OpenClaw GW</span><span class="stat-value">' + badge + '</span></div>';
    }
    if (data.claude_processes) {
      var cp = data.claude_processes;
      var badge = cp.running
        ? '<span class="badge badge-up">' + (cp.count || 0) + ' RUNNING</span>'
        : '<span class="badge badge-down">NONE</span>';
      h += '<div class="stat-row"><span class="stat-label">Claude Procs</span><span class="stat-value">' + badge + '</span></div>';
      var procs = cp.processes || [];
      if (procs.length > 0) {
        for (var i = 0; i < procs.length; i++) {
          var p = procs[i];
          var taskName = p.task_name || '';
          var activities = p.activities || [];
          var started = p.started || '';
          var maxTurns = p.max_turns || '';
          var header = taskName ? esc(taskName) : ('PID ' + esc(p.pid));
          h += '<details class="proc-details" open>';
          h += '<summary><span class="proc-task">' + header + '</span>';
          h += '<span class="proc-stats">CPU ' + esc(p.cpu) + '% \u00b7 MEM ' + esc(p.mem) + '% \u00b7 up ' + esc(p.etime);
          if (taskName) h += ' \u00b7 PID ' + esc(p.pid);
          if (maxTurns) h += ' \u00b7 max ' + esc(maxTurns) + ' turns';
          h += '</span></summary>';
          h += '<div class="proc-info">';
          if (started) {
            try {
              var startDate = new Date(started);
              var now = new Date();
              var diffMs = now - startDate;
              var diffS = Math.floor(diffMs / 1000);
              var hrs = Math.floor(diffS / 3600);
              var mins = Math.floor((diffS % 3600) / 60);
              var secs = diffS % 60;
              var dur = hrs > 0 ? (hrs + 'h ' + mins + 'm') : (mins > 0 ? (mins + 'm ' + secs + 's') : (secs + 's'));
              var timeStr = startDate.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'});
              h += '<div class="proc-start-time">Started ' + esc(timeStr) + ' \u00b7 Running for ' + esc(dur) + '</div>';
            } catch(e) {
              h += '<div class="proc-start-time">Started ' + esc(started) + '</div>';
            }
          }
          if (activities.length > 0) {
            h += '<div class="proc-activity">';
            for (var j = 0; j < activities.length; j++) {
              h += '<div class="activity-line">' + esc(activities[j]) + '</div>';
            }
            h += '</div>';
          } else {
            var tail = p.log_tail || [];
            if (tail.length > 0) h += '<pre class="proc-log-tail">' + tail.map(esc).join('\\n') + '</pre>';
            else h += '<div class="proc-none">No activity yet</div>';
          }
          h += '</div></details>';
        }
      } else if (!cp.running) {
        h += '<div class="proc-none">No active tasks</div>';
      }
    }
    h += '</div>';
    return h;
  }

  function esc2(s) { return esc(s); }

  function renderAgentPanel(data) {
    var h = '';
    var executors = data.executors || [];
    if (executors.length > 0) {
      h += '<div class="executor-list">';
      for (var i = 0; i < executors.length; i++) {
        var ex = executors[i];
        var dotCls = ex.reachable === true ? 'up' : (ex.reachable === false ? 'down' : 'unknown');
        var dotTitle = ex.reachable === true ? 'Reachable' : (ex.reachable === false ? 'Unreachable' : 'Unknown');
        h += '<div class="executor-chip">';
        h += '<span class="reach-dot ' + dotCls + '" title="' + dotTitle + '"></span>';
        h += '<span class="ex-name">' + esc(ex.name) + '</span>';
        h += '<span class="ex-type">' + esc(ex.type) + '</span>';
        if (ex.host) h += '<span class="ex-host">(' + esc(ex.host) + ')</span>';
        h += '</div>';
      }
      h += '</div>';
    }
    var s = data.summary || {};
    h += '<div class="agent-summary">';
    h += '<span class="s-item"><span class="badge badge-running">' + (s.running||0) + ' running</span></span>';
    h += '<span class="s-item"><span class="badge badge-completed">' + (s.completed||0) + ' completed</span></span>';
    h += '<span class="s-item"><span class="badge badge-failed">' + (s.failed||0) + ' failed</span></span>';
    h += '<span class="s-item" style="margin-left:auto">' + (s.total||0) + ' total</span>';
    h += '</div>';
    var tasks = data.tasks || [];
    if (tasks.length === 0) {
      h += '<div class="no-tasks">No tasks yet</div>';
    } else {
      h += '<table class="task-table"><thead><tr><th>ID</th><th>Type</th><th>Executor</th><th>Status</th><th>Runtime</th><th>Command / Prompt</th></tr></thead><tbody>';
      var limit = Math.min(tasks.length, 20);
      for (var j = 0; j < limit; j++) {
        var t = tasks[j];
        var tid = t.task_id || '';
        var shortId = tid.length >= 8 ? tid.substr(0,8) : tid;
        var status = t.status || '?';
        var badgeCls = status === 'running' ? 'badge-running' : (status === 'completed' ? 'badge-completed' : (status === 'failed' ? 'badge-failed' : 'badge'));
        var statusLabel = status === 'running' ? 'running' : (status === 'completed' ? 'done' : (status === 'failed' ? 'failed' : status));
        var taskType = t.task_type || 'claude_code';
        var typeIcon = taskType === 'shell_command' ? '⚙️' : '🤖';
        var typeLabel = taskType === 'shell_command' ? 'shell' : 'claude';
        var executorType = t.executor_type || '';
        var executorDisplay = esc(t.executor || '?');
        if (executorType) executorDisplay += ' <span class="dim">(' + esc(executorType) + ')</span>';
        var prompt = t.prompt || '';
        var workspace = t.workspace || '';
        var tooltip = workspace ? '[' + esc(workspace) + '] ' + esc(prompt) : esc(prompt);
        var promptCls = prompt ? 'task-prompt' : 'task-prompt empty';
        var promptDisplay = prompt ? esc(prompt) : 'no prompt';
        h += '<tr>';
        h += '<td><span class="task-id">' + esc(shortId) + '</span></td>';
        h += '<td><span title="' + esc(taskType) + '">' + typeIcon + ' ' + typeLabel + '</span></td>';
        h += '<td>' + executorDisplay + '</td>';
        h += '<td><span class="badge ' + badgeCls + '">' + statusLabel + '</span></td>';
        h += '<td><span class="task-runtime">' + esc(t.runtime||'') + '</span></td>';
        h += '<td><span class="' + promptCls + '" title="' + tooltip + '">' + promptDisplay + '</span></td>';
        h += '</tr>';
      }
      h += '</tbody></table>';
    }
    return h;
  }

  function fmtAge(s) {
    if (s < 0) return '?';
    if (s < 60) return s + 's ago';
    if (s < 3600) return Math.floor(s/60) + 'm ago';
    return Math.floor(s/3600) + 'h ago';
  }

  function refreshSubagentPanel() {
    fetch('/subagent-status')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var panel = document.getElementById('subagent-panel');
        if (!panel) return;
        var h2 = panel.querySelector('h2');
        var content = '';
        if (data.error && (!data.agents || !data.agents.length)) {
          content = '<div class="no-tasks">' + esc(data.error) + '</div>';
        } else if (!data.agents || !data.agents.length) {
          content = '<div class="no-tasks">No sub-agents found</div>';
        } else {
          var active = data.agents.filter(function(a) { return a.active; });
          var inactive = data.agents.filter(function(a) { return !a.active; });
          content += '<div class="agent-summary"><span class="s-item">🟢 ' + active.length + ' active</span><span class="s-item">⏹ ' + inactive.length + ' recent</span></div>';
          content += '<table style="width:100%;border-collapse:collapse;font-size:0.85em">';
          content += '<thead><tr style="color:var(--dim);text-align:left"><th style="padding:4px 8px">Label</th><th style="padding:4px 8px">Status</th><th style="padding:4px 8px">Updated</th><th style="padding:4px 8px">Tokens</th></tr></thead><tbody>';
          data.agents.forEach(function(a) {
            var statusBadge = a.active
              ? '<span class="badge badge-up">RUNNING</span>'
              : '<span class="badge" style="background:var(--dim);color:var(--bg)">DONE</span>';
            var tok = a.total_tokens >= 1000000 ? '1M' : (a.total_tokens >= 1000 ? Math.round(a.total_tokens/1000) + 'k' : a.total_tokens);
            content += '<tr style="border-top:1px solid var(--border)">';
            content += '<td style="padding:5px 8px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + esc(a.key) + '">' + esc(a.label) + '</td>';
            content += '<td style="padding:5px 8px">' + statusBadge + '</td>';
            content += '<td style="padding:5px 8px;color:var(--dim)">' + fmtAge(a.age_s) + '</td>';
            content += '<td style="padding:5px 8px;color:var(--dim)">' + tok + '</td>';
            content += '</tr>';
          });
          content += '</tbody></table>';
        }
        if (h2) {
          panel.innerHTML = h2.outerHTML + content;
        } else {
          panel.innerHTML = '<h2>&#x1F9E0; Active Sub-Agents</h2>' + content;
        }
      })
      .catch(function() {});
  }

  function refreshAgentPanel() {
    fetch('/coding-agent-status')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var panel = document.getElementById('agent-panel');
        if (!panel) return;
        // Keep h2 header, replace content after it
        var h2 = panel.querySelector('h2');
        var newContent = renderAgentPanel(data);
        if (h2) {
          panel.innerHTML = h2.outerHTML + newContent;
        } else {
          panel.innerHTML = '<h2>&#x1F916; Coding Agent Tasks</h2>' + newContent;
        }
      })
      .catch(function() {});
  }

  function refreshStatus() {
    spinner.style.display = 'inline';
    fetch('/system-status')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.error) return;
        grid.innerHTML = renderHostCard(data.pi5) + renderHostCard(data.crib);
        lastRefreshTime = Date.now();
      })
      .catch(function() {})
      .finally(function() { spinner.style.display = 'none'; });
    refreshAgentPanel();
    refreshSubagentPanel();
  }

  function updateCounter() {
    const secs = Math.floor((Date.now() - lastRefreshTime) / 1000);
    let ago;
    if (secs < 5) ago = 'just now';
    else if (secs < 60) ago = secs + 's ago';
    else ago = Math.floor(secs / 60) + 'm ' + (secs % 60) + 's ago';
    note.textContent = 'Last refreshed: ' + ago + ' \\u00b7 Auto-refreshes every 30s';
  }

  window.manualRefresh = function() {
    refreshStatus();
  };

  setInterval(refreshStatus, 30000);
  setInterval(updateCounter, 1000);
  // Initial agent panel load (async, doesn't block page render)
  refreshAgentPanel();
  refreshSubagentPanel();
})();
</script>"""

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/png" href="/favicon.ico">
<title>System Status — Jimmy's Workspace</title>
<style>{CSS}{STATUS_DASHBOARD_CSS}{AGENT_PANEL_CSS}
#spinner {{ display: inline-block; animation: spin 1s linear infinite; color: var(--accent); font-size: 0.8em; }}
@keyframes spin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
#refresh-btn {{ background: var(--card); color: var(--accent); border: 1px solid var(--border); padding: 4px 14px;
  border-radius: 6px; font-size: 0.5em; cursor: pointer; vertical-align: middle; margin-left: 8px;
  font-family: inherit; transition: background 0.15s, border-color 0.15s; }}
#refresh-btn:hover {{ background: var(--border); border-color: var(--accent); }}
#refresh-btn:active {{ background: var(--accent); color: var(--bg); }}
</style>
</head><body>
<div class="nav">🦞 <strong>Jimmy's Workspace</strong> &nbsp;|&nbsp;
<a href="/">Home</a> <a href="/status">Status</a>
<a href="/TODO.md">TODO</a></div>
{body}
{status_js}
</body></html>"""


def breadcrumb(path):
    parts = path.strip('/').split('/')
    crumbs = ['<a href="/">🏠 workspace</a>']
    for i, part in enumerate(parts):
        if part:
            href = '/' + '/'.join(parts[:i+1])
            crumbs.append(f'<a href="{href}">{html.escape(part)}</a>')
    return ' / '.join(crumbs)

def search_files(query, root=WORKSPACE):
    """Search all text/markdown files for a query string (case-insensitive)."""
    results = []
    query_lower = query.lower()
    exts = {'.md', '.markdown', '.txt', '.json', '.yaml', '.yml', '.py', '.rs',
            '.ts', '.js', '.sh', '.toml', '.cfg', '.ini', '.log'}
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        if any(part.startswith('.') for part in path.relative_to(root).parts):
            continue
        try:
            text = path.read_text(errors='replace')
        except Exception:
            continue
        lines = text.split('\n')
        matches = []
        for i, line in enumerate(lines, 1):
            if query_lower in line.lower():
                matches.append((i, line.strip()[:120]))
        if matches:
            rel = str(path.relative_to(root))
            results.append((rel, matches))
    return results

def page(title, body, path='/'):
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/png" href="/favicon.ico">
<title>{html.escape(title)} — Jimmy's Workspace</title>
<style>{CSS}</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/tokyo-night-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>hljs.highlightAll();</script>
<script>
// Add copy buttons to code blocks
document.querySelectorAll('pre').forEach(pre => {{
  const btn = document.createElement('button');
  btn.textContent = 'Copy';
  btn.style.cssText = 'position:absolute;top:8px;right:8px;padding:3px 10px;font-size:12px;border:1px solid var(--border,#444);border-radius:4px;background:var(--card,#1a1a1a);color:var(--text,#eee);cursor:pointer;opacity:0.7;';
  btn.addEventListener('click', () => {{
    const code = pre.querySelector('code');
    navigator.clipboard.writeText(code ? code.innerText : pre.innerText).then(() => {{
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = 'Copy', 1500);
    }});
  }});
  pre.style.position = 'relative';
  pre.appendChild(btn);
}});
</script>
<script>
// Make all external links open in new tab
document.querySelectorAll('a[href^="http"]').forEach(a => {{
  a.target = '_blank';
}});
</script>
<script>
let sortCol = 'mtime', sortAsc = false;
function sortDir(e, col) {{
  e.preventDefault();
  if (sortCol === col) {{ sortAsc = !sortAsc; }} 
  else {{ sortCol = col; sortAsc = false; }}
  document.getElementById('sort-dir').textContent = sortAsc ? '↑' : '↓';
  const ul = document.querySelector('.dir-list');
  const lis = Array.from(ul.querySelectorAll('li'));
  lis.sort((a, b) => {{
    let av = a.dataset[sortCol], bv = b.dataset[sortCol];
    if (sortCol === 'name') {{ av = av.toLowerCase(); bv = bv.toLowerCase(); return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av); }}
    return sortAsc ? av - bv : bv - av;
  }});
  lis.forEach(li => ul.appendChild(li));
}}
</script>
</head><body>
<div class="nav">🦞 <strong>Jimmy's Workspace</strong> &nbsp;|&nbsp;
<a href="/">Home</a> <a href="/research">Research</a> <a href="/memory">Memory</a>
<a href="/status">Status</a> <a href="/TODO.md">TODO</a>
<form style="display:inline; margin-left:16px" method="GET" action="/search">
<input name="q" placeholder="Search files..." value="" 
 style="background:var(--bg);color:var(--fg);border:1px solid var(--border);padding:4px 8px;border-radius:4px;width:200px">
<button type="submit" style="background:var(--accent);color:var(--bg);border:none;padding:4px 12px;border-radius:4px;cursor:pointer">🔍</button>
</form></div>
<div class="breadcrumb">{breadcrumb(path)}</div>
{body}
</body></html>"""


class WorkspaceHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        # Strip query string before path processing, but keep self.path intact for raw check
        raw_path = self.path.split('?')[0]
        path = unquote(raw_path).rstrip('/')
        if not path:
            path = '/'
        
        # Favicon
        if path == '/favicon.ico':
            if FAVICON_DATA:
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.end_headers()
                self.wfile.write(FAVICON_DATA)
            else:
                self.send_error(404, "No favicon")
            return

        # Coding agent status endpoint
        if path == '/subagent-status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                data = get_subagent_status()
                self.wfile.write(json.dumps(data).encode())
            except Exception as e:
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        if path == '/coding-agent-status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                data = get_coding_agent_status()
                self.wfile.write(json.dumps(data).encode())
            except Exception as e:
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        # System status JSON endpoint
        if path == '/system-status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                data = {"pi5": get_pi5_status(), "crib": get_crib_status()}
            except Exception as e:
                data = {"error": str(e)}
            self.wfile.write(json.dumps(data, indent=2).encode())
            return

        # Status dashboard HTML
        if path == '/status':
            try:
                pi5 = get_pi5_status()
                crib = get_crib_status()
            except Exception as e:
                pi5 = {"host": "Pi5", "error": str(e)}
                crib = {"host": "Crib", "error": str(e)}
            self.send_html(render_status_page(pi5, crib))
            return

        # Search handler
        if path.startswith('/search'):
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            query = params.get('q', [''])[0]
            if not query:
                self.send_html(page('Search', '<h1>Search</h1><p>Enter a search term above.</p>', '/search'))
                return
            results = search_files(query)
            body = f'<h1>Search: "{html.escape(query)}"</h1>'
            if not results:
                body += '<p style="color:var(--dim)">No results found.</p>'
            else:
                total = sum(len(m) for _, m in results)
                body += f'<p style="color:var(--dim)">{total} matches in {len(results)} files</p>'
                for rel_path, matches in results:
                    body += f'<h3><a href="/{quote(rel_path)}">{html.escape(rel_path)}</a></h3><ul>'
                    for lineno, line in matches[:5]:
                        highlighted = html.escape(line).replace(
                            html.escape(query), f'<mark style="background:var(--accent);color:var(--bg)">{html.escape(query)}</mark>')
                        # case-insensitive highlight
                        highlighted = re.sub(
                            re.escape(html.escape(query)),
                            f'<mark style="background:var(--accent);color:var(--bg)">{html.escape(query)}</mark>',
                            html.escape(line), flags=re.IGNORECASE)
                        body += f'<li><span style="color:var(--dim)">L{lineno}:</span> {highlighted}</li>'
                    if len(matches) > 5:
                        body += f'<li style="color:var(--dim)">...and {len(matches)-5} more matches</li>'
                    body += '</ul>'
            self.send_html(page(f'Search: {query}', body, '/search'))
            return
        
        if path.startswith('/rag-search'):
            from urllib.parse import parse_qs, urlparse, quote as url_quote
            import urllib.request
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            query = params.get('q', [''])[0]
            top_k = params.get('top_k', ['10'])[0]
            collection = params.get('collection', ['all'])[0]
            if not query:
                self.send_html(page('RAG Search', '<h1>🧠 RAG Semantic Search</h1><p>Search across memory and repos using AI embeddings.</p><form method="GET" action="/rag-search"><input name="q" placeholder="semantic query..." style="padding:8px;width:400px;background:var(--bg);color:var(--fg);border:1px solid var(--dim)"><button style="padding:8px 16px;margin-left:8px">Search</button></form>', '/rag-search'))
                return
            try:
                rag_url = f'http://127.0.0.1:8766/search?q={url_quote(query)}&top_k={top_k}&collection={collection}'
                req = urllib.request.Request(rag_url, headers={'Accept': 'application/json'})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read())
                results = data.get('results', [])
                body = f'<h1>🧠 RAG: "{html.escape(query)}"</h1>'
                body += f'<form method="GET" action="/rag-search"><input name="q" value="{html.escape(query)}" style="padding:8px;width:400px;background:var(--bg);color:var(--fg);border:1px solid var(--dim)"><button style="padding:8px 16px;margin-left:8px">Search</button></form>'
                if not results:
                    body += '<p style="color:var(--dim)">No results found.</p>'
                else:
                    body += f'<p style="color:var(--dim)">{len(results)} semantic matches</p>'
                    for r in results:
                        score = 1 - r.get('distance', 0)
                        rpath = r.get('path', '')
                        col = r.get('collection', '')
                        lines = f"L{r.get('line_start','')}-{r.get('line_end','')}"
                        body += f'<div style="margin:16px 0;padding:12px;border-left:3px solid var(--accent);background:rgba(255,255,255,0.03)">'
                        body += f'<div><strong>[{html.escape(col)}]</strong> <a href="/{url_quote(rpath)}">{html.escape(rpath)}</a> <span style="color:var(--dim)">{lines} (score: {score:.2f})</span></div>'
                        body += f'<pre style="margin:8px 0;white-space:pre-wrap;font-size:0.85em">{html.escape(r.get("text","")[:500])}</pre>'
                        body += '</div>'
                self.send_html(page(f'RAG: {query}', body, '/rag-search'))
            except Exception as e:
                body = f'<h1>🧠 RAG Search Error</h1><p style="color:red">Could not reach RAG server on K11: {html.escape(str(e))}</p><p>Make sure <code>jimmy-rag-server.py</code> is running on 192.168.0.125:8766</p>'
                self.send_html(page('RAG Error', body, '/rag-search'))
            return
        
        fs_path = WORKSPACE / path.lstrip('/')
        
        # Security: don't escape workspace
        try:
            fs_path.resolve().relative_to(WORKSPACE.resolve())
        except ValueError:
            self.send_error(403, "Forbidden")
            return
        
        if fs_path.is_dir():
            self.serve_directory(path, fs_path)
        elif fs_path.is_file():
            if fs_path.suffix.lower() in ('.md', '.markdown'):
                self.serve_markdown(path, fs_path)
            elif fs_path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'):
                self.serve_file(fs_path)
            elif fs_path.suffix.lower() in ('.json', '.yaml', '.yml', '.toml', '.sh', '.py',
                                              '.rs', '.ts', '.js', '.txt', '.cfg', '.ini', '.log'):
                self.serve_text(path, fs_path)
            else:
                self.serve_file(fs_path)
        else:
            self.send_error(404, "Not found")
    
    def serve_directory(self, url_path, fs_path):
        entries = sorted(fs_path.iterdir(), key=lambda p: (not p.is_dir(), -p.stat().st_mtime))
        items = []
        
        # Check for README
        readme = None
        for name in ('README.md', 'readme.md', 'INDEX.md'):
            r = fs_path / name
            if r.exists():
                readme = r
                break
        
        for entry in entries:
            if entry.name.startswith('.'):
                continue
            name = entry.name
            icon = '📁' if entry.is_dir() else '📄'
            if entry.suffix.lower() in ('.md', '.markdown'):
                icon = '📝'
            elif entry.suffix.lower() in ('.py', '.rs', '.ts', '.js', '.sh'):
                icon = '💻'
            elif entry.suffix.lower() in ('.json', '.yaml', '.yml'):
                icon = '⚙️'
            elif entry.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif'):
                icon = '🖼️'
            
            href = f"{url_path}/{name}".replace('//', '/')
            size = ''
            mtime = ''
            mtime_val = entry.stat().st_mtime
            sz = entry.stat().st_size if entry.is_file() else 0
            if entry.is_file():
                if sz < 1024:
                    size = f'{sz}B'
                elif sz < 1024*1024:
                    size = f'{sz//1024}KB'
                else:
                    size = f'{sz//(1024*1024)}MB'
            # Format mtime as relative or absolute (for both files and folders)
            mt = datetime.fromtimestamp(mtime_val)
            now = datetime.now()
            diff = now - mt
            if diff.days == 0:
                mtime = mt.strftime('%H:%M')
            elif diff.days == 1:
                mtime = 'yesterday'
            elif diff.days < 7:
                mtime = f'{diff.days}d ago'
            else:
                mtime = mt.strftime('%b %d')
            
            items.append(f'<li data-name="{html.escape(name)}" data-size="{sz}" data-mtime="{mtime_val}"><span class="icon">{icon}</span>'
                        f'<a href="{quote(href)}">{html.escape(name)}</a>'
                        f'<span class="file-meta">{mtime} {size}</span></li>')
        
        body = f'<h1>{html.escape(url_path or "workspace")}</h1>\n'
        body += """<div class="sort-bar"><span>Sort by:</span> 
<a href="#" onclick="sortDir(event, 'name')">Name</a> | 
<a href="#" onclick="sortDir(event, 'size')">Size</a> | 
<a href="#" onclick="sortDir(event, 'mtime')">Modified</a> |
<span id="sort-dir">↓</span></div>
"""
        body += f'<ul class="dir-list">{"".join(items)}</ul>'
        
        if readme:
            body += '<hr><div class="readme">'
            body += md_to_html(readme.read_text(errors='replace'))
            body += '</div>'
        
        self.send_html(page(url_path or 'workspace', body, url_path))
    
    def serve_markdown(self, url_path, fs_path):
        text = fs_path.read_text(errors='replace')
        body = f'<div class="markdown">{md_to_html(text)}</div>'
        raw_link = f'<p style="margin-top:2em"><a href="{quote(url_path)}?raw=1">📋 View raw</a></p>'
        if '?raw=1' in self.path:
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(text.encode())
            return
        self.send_html(page(fs_path.name, body + raw_link, url_path))
    
    def serve_text(self, url_path, fs_path):
        text = fs_path.read_text(errors='replace')
        body = f'<h1>{html.escape(fs_path.name)}</h1>\n<pre><code>{html.escape(text)}</code></pre>'
        self.send_html(page(fs_path.name, body, url_path))
    
    def serve_file(self, fs_path):
        mime, _ = mimetypes.guess_type(str(fs_path))
        self.send_response(200)
        self.send_header('Content-Type', mime or 'application/octet-stream')
        self.end_headers()
        self.wfile.write(fs_path.read_bytes())
    
    def send_html(self, content):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode())
    
    def log_message(self, format, *args):
        pass  # Silence logs


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), WorkspaceHandler)
    print(f"🦞 Jimmy's Workspace running on http://0.0.0.0:{PORT}")
    print(f"   Local: http://pi5.local:{PORT}")
    print(f"   Serving: {WORKSPACE}")
    server.serve_forever()
# Note: RAG search requires SSH tunnel to K11:
# ssh -f -N -L 8766:localhost:8766 jimmy@192.168.0.125
