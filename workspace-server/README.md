# 🦞 Workspace Server

A lightweight, zero-dependency web file browser for your OpenClaw workspace. Browse markdown files, code, and research documents from any device on your local network.

## Features

- 📁 Directory browsing with file type icons
- 📝 Markdown rendering (dark theme, GitHub-ish)
- 💻 Syntax display for code/config files
- 🔍 Full-text search across all files
- 🖼️ Image serving
- 🏠 Quick nav: Home, Research, Memory, TODO
- ☐ Checkbox rendering in markdown
- Zero external dependencies — pure Python stdlib

## Quick Start

```bash
# Run directly
python3 server.py

# Or install as systemd service
sudo cp workspace-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now workspace-server
```

## Configuration

Edit the top of `server.py`:

```python
WORKSPACE = Path("/home/vpavlin/.openclaw/workspace")  # Your workspace path
PORT = 8888                                              # Server port
```

## Nginx Reverse Proxy (optional)

To access via `http://your-hostname.local` on port 80:

```nginx
server {
    listen 80;
    server_name your-hostname.local;

    location / {
        proxy_pass http://127.0.0.1:8888;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Requirements

- Python 3.8+
- That's it. No pip install needed.
