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
    text = html.escape(text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
    # Inline code
    text = re.sub(r'`(.+?)`', r'<code class="inline">\1</code>', text)
    # Links
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)
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
</head><body>
<div class="nav">🦞 <strong>Jimmy's Workspace</strong> &nbsp;|&nbsp;
<a href="/">Home</a> <a href="/research">Research</a> <a href="/memory">Memory</a>
<a href="/TODO.md">TODO</a>
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
        entries = sorted(fs_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
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
            if entry.is_file():
                sz = entry.stat().st_size
                if sz < 1024:
                    size = f'{sz}B'
                elif sz < 1024*1024:
                    size = f'{sz//1024}KB'
                else:
                    size = f'{sz//(1024*1024)}MB'
                # Format mtime as relative or absolute
                mt = datetime.fromtimestamp(entry.stat().st_mtime)
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
            
            items.append(f'<li><span class="icon">{icon}</span>'
                        f'<a href="{quote(href)}">{html.escape(name)}</a>'
                        f'<span class="file-meta">{mtime} {size}</span></li>')
        
        body = f'<h1>{html.escape(url_path or "workspace")}</h1>\n'
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
