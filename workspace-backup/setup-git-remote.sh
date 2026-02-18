#!/bin/bash
# setup-git-remote.sh
# Run this on the backup machine (Ollama/Immich server) to set up a bare git remote
# for Jimmy's workspace backup.
#
# Usage: bash setup-git-remote.sh
# Then follow the instructions printed at the end to wire up pi5.

set -e

BACKUP_DIR="${BACKUP_DIR:-$HOME/jimmy-workspace-backup.git}"

echo "=== Jimmy Workspace Backup Setup ==="
echo "Setting up bare git repo at: $BACKUP_DIR"

git init --bare "$BACKUP_DIR"

echo ""
echo "=== Done! ==="
echo ""
echo "Now run the following on pi5 to connect:"
echo ""
echo "  BACKUP_HOST=<this-machine-ip-or-hostname>"
echo "  BACKUP_USER=<your-username-on-this-machine>"
echo ""
echo "  git -C ~/.openclaw/workspace remote add backup ssh://\${BACKUP_USER}@\${BACKUP_HOST}${BACKUP_DIR}"
echo "  git -C ~/.openclaw/workspace push backup master"
echo ""
echo "Or just tell Jimmy the IP/hostname and username and he'll wire it up automatically."
