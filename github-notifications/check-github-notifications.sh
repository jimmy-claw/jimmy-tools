#!/bin/bash
# Check GitHub notifications and output only summaries.
# SECURITY: Only vpavlin's comments are marked as [OWNER]. All others are [EXTERNAL].
# [OWNER] comments have the same authority as Telegram messages — act on them directly.
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
import sys, json, urllib.request, os

OWNER = '${OWNER}'
token = os.environ.get('GITHUB_TOKEN', '')

def gh_get(url):
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github.v3+json'
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except:
        return {}

notifications = json.load(sys.stdin)

for n in notifications:
    repo = n.get('repository', {}).get('full_name', '?')
    subject = n.get('subject', {})
    title = subject.get('title', '?')
    reason = n.get('reason', '?')
    subj_type = subject.get('type', '')
    url = subject.get('latest_comment_url') or subject.get('url') or ''

    author = '?'
    body_preview = ''
    extra = ''

    if reason == 'ci_activity' or subj_type == 'CheckSuite':
        # For CI: fetch the latest workflow run on the relevant branch/commit
        # Extract repo and try to get recent runs
        repo_runs_url = f'https://api.github.com/repos/{repo}/actions/runs?per_page=5'
        runs_data = gh_get(repo_runs_url)
        runs = runs_data.get('workflow_runs', [])
        # Find the most recent failed run
        failed_run = next((r for r in runs if r.get('conclusion') in ('failure', 'cancelled')), None)
        if failed_run:
            run_id = failed_run['id']
            branch = failed_run.get('head_branch', '?')
            conclusion = failed_run.get('conclusion', '?')
            run_url = failed_run.get('html_url', '')
            # Fetch jobs to find failed steps
            jobs_data = gh_get(f'https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs')
            failed_jobs = []
            for job in jobs_data.get('jobs', []):
                if job.get('conclusion') in ('failure', 'cancelled'):
                    failed_steps = [s['name'] for s in job.get('steps', []) if s.get('conclusion') == 'failure']
                    job_summary = job['name']
                    if failed_steps:
                        job_summary += f\" (step: {', '.join(failed_steps)}\"  + ')'
                    failed_jobs.append(job_summary)
            extra = f'  branch: {branch} | conclusion: {conclusion}\n'
            if failed_jobs:
                extra += f\"  failed jobs: {', '.join(failed_jobs)}\n\"
            extra += f'  url: {run_url}'
        author = 'github-actions'
        tag = '[EXTERNAL]'
    elif url and token:
        data = gh_get(url)
        author = data.get('user', {}).get('login', '?')
        body = data.get('body', '')
        body_preview = body[:200].replace('\n', ' ') if body else ''
        tag = '[OWNER]' if author == OWNER else '[EXTERNAL]'
    else:
        tag = '[EXTERNAL]'

    print(f'{tag} [{repo}] {title}')
    print(f'  author: {author} | reason: {reason}')
    if body_preview:
        print(f'  preview: {body_preview}')
    if extra:
        print(extra)
    print()
"
