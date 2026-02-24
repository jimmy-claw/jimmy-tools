#!/usr/bin/env python3
"""Lightweight workspace file browser with markdown rendering.
Zero external dependencies — uses only Python stdlib.
Serves the OpenClaw workspace directory with directory listings and markdown preview.
"""

import os
import re
import html
import json
import subprocess
import mimetypes
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, quote

WORKSPACE = Path("/home/vpavlin/.openclaw/workspace")
PORT = 8888
CRIB_HOST = "jimmy@192.168.0.152"
SSH_OPTS = ['-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=5']

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
    # Emoji shortcodes (common ones)
    emojis = {'🔴': '🔴', '🟡': '🟡', '🟢': '🟢', '📝': '📝'}
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


def get_crib_status():
    """Gather crib (192.168.0.152) system status via SSH."""
    status = {"host": "Crib", "ts": datetime.now().isoformat()}
    status["uptime"] = _parse_uptime(_run_ssh("uptime"))
    status["memory"] = _parse_memory(_run_ssh("free -h"))
    status["disk"] = _parse_disk(_run_ssh("df -h /"))

    # Claude processes
    claude = _run_ssh("ps aux | grep -i claud[e]")
    if claude.startswith("error:") or not claude:
        status["claude_processes"] = {"running": False, "detail": claude or "none found"}
    else:
        procs = [l for l in claude.splitlines() if l.strip()]
        status["claude_processes"] = {"running": True, "count": len(procs), "detail": claude}

    return status


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

    h += '</div>'
    return h


def render_status_page(pi5, crib):
    """Build the full status dashboard HTML."""
    body = '<h1>System Status</h1>'
    body += f'<div class="status-grid">{_render_host_card(pi5)}{_render_host_card(crib)}</div>'
    body += '<div class="refresh-note">Auto-refreshes every 30s</div>'

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>System Status — Jimmy's Workspace</title>
<style>{CSS}{STATUS_DASHBOARD_CSS}</style>
<meta http-equiv="refresh" content="30">
</head><body>
<div class="nav">🦞 <strong>Jimmy's Workspace</strong> &nbsp;|&nbsp;
<a href="/">Home</a> <a href="/status">Status</a>
<a href="/TODO.md">TODO</a></div>
{body}
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
<title>{html.escape(title)} — Jimmy's Workspace</title>
<style>{CSS}</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/tokyo-night-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>hljs.highlightAll();</script>
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
        path = unquote(self.path).rstrip('/')
        if not path:
            path = '/'
        
        # Coding agent status endpoint
        if path == '/coding-agent-status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                result = subprocess.run(
                    ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=5',
                     'jimmy@192.168.0.152', 'cat', '~/coding-agent-status.json'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    self.wfile.write(result.stdout.encode())
                else:
                    self.wfile.write(b'{"error": "SSH failed"}')
            except Exception as e:
                self.wfile.write(f'{{"error": "{str(e)}"}}'.encode())
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
                        import re as _re
                        highlighted = _re.sub(
                            _re.escape(html.escape(query)),
                            f'<mark style="background:var(--accent);color:var(--bg)">{html.escape(query)}</mark>',
                            html.escape(line), flags=_re.IGNORECASE)
                        body += f'<li><span style="color:var(--dim)">L{lineno}:</span> {highlighted}</li>'
                    if len(matches) > 5:
                        body += f'<li style="color:var(--dim)">...and {len(matches)-5} more matches</li>'
                    body += '</ul>'
            self.send_html(page(f'Search: {query}', body, '/search'))
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
