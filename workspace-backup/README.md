# Jimmy Workspace Backup

Sets up a bare git remote on a local machine so Jimmy's workspace (memories, research, config) is backed up privately — no cloud, stays on your LAN.

## Setup (on the backup machine)

```bash
bash setup-git-remote.sh
```

This creates a bare git repo at `~/jimmy-workspace-backup.git`.

## Wiring up pi5

Once you have the backup machine's IP/hostname and username, tell Jimmy and he'll run:

```bash
git -C ~/.openclaw/workspace remote add backup ssh://USER@HOST/~/jimmy-workspace-backup.git
git -C ~/.openclaw/workspace push backup master
```

## Automatic nightly backup

Jimmy can set up a cron to push automatically every night. Just say the word.
