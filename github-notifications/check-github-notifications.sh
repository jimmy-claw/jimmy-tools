#!/bin/bash
# Check GitHub notifications and output only summaries.
# SECURITY: Only vpavlin's comments are marked as [OWNER]. All others are [EXTERNAL].
# The agent must NEVER act on EXTERNAL comments without explicit user approval.

SINCE=$(date -u -d '6 minutes ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-6M +%Y-%m-%dT%H:%M:%SZ)
OWNER="vpavlin"

notifications=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/notifications?since=${SINCE}&per_page=20")

count=$(echo "$notifications" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)

if [ "$count" = "0" ] || [ -z "$count" ]; then
  echo "NO_NEW_NOTIFICATIONS"
  exit 0
fi

echo "$notifications" | python3 -c "
import sys, json, subprocess, os

OWNER = '${OWNER}'
token = os.environ.get('GITHUB_TOKEN', '')
notifications = json.load(sys.stdin)

for n in notifications:
    repo = n.get('repository', {}).get('full_name', '?')
    subject = n.get('subject', {})
    title = subject.get('title', '?')
    reason = n.get('reason', '?')
    url = subject.get('latest_comment_url') or subject.get('url') or ''
    
    # Fetch the latest comment to get the author
    author = '?'
    body_preview = ''
    if url and token:
        import urllib.request
        req = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github.v3+json'
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                author = data.get('user', {}).get('login', '?')
                body = data.get('body', '')
                body_preview = body[:200].replace('\n', ' ') if body else ''
        except:
            pass
    
    # DETERMINISTIC safety tag — grep-level check, not LLM judgment
    if author == OWNER:
        tag = '[OWNER]'
    else:
        tag = '[EXTERNAL]'
    
    print(f'{tag} [{repo}] {title}')
    print(f'  author: {author} | reason: {reason}')
    if body_preview:
        print(f'  preview: {body_preview}')
    print()
"
