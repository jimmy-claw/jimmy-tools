#!/bin/bash
# setup-git-remote.sh
# Run this on the backup machine (e.g. Ollama/Immich server) with sudo.
# Creates a limited 'jimmy' user and sets up a bare git repo for workspace backups.
#
# Usage: sudo bash setup-git-remote.sh

set -e

JIMMY_USER="${JIMMY_USER:-jimmy}"
BACKUP_DIR="/home/$JIMMY_USER/jimmy-workspace-backup.git"
PI5_PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAING7LJ4v9bLqyRHOJOZZvKqeqlSuMY0i2b1p0/ODI/Ko openclaw@pi5"

echo "=== Jimmy Workspace Backup Setup ==="
echo "Creating user: $JIMMY_USER"
echo "Backup dir:    $BACKUP_DIR"
echo ""

# Create jimmy user (no sudo, no password login)
if id "$JIMMY_USER" &>/dev/null; then
    echo "User $JIMMY_USER already exists, skipping creation."
else
    useradd -m -s /bin/bash "$JIMMY_USER"
    passwd -l "$JIMMY_USER"  # disable password login
    echo "User $JIMMY_USER created."
fi

# Set up SSH key
mkdir -p /home/$JIMMY_USER/.ssh
echo "$PI5_PUBKEY" > /home/$JIMMY_USER/.ssh/authorized_keys
chown -R $JIMMY_USER:$JIMMY_USER /home/$JIMMY_USER/.ssh
chmod 700 /home/$JIMMY_USER/.ssh
chmod 600 /home/$JIMMY_USER/.ssh/authorized_keys
echo "SSH key installed."

# Init bare git repo
sudo -u $JIMMY_USER git init --bare "$BACKUP_DIR"
echo "Bare git repo created at $BACKUP_DIR"

echo ""
echo "=== Done! ==="
echo ""
echo "Now tell Jimmy the IP/hostname of this machine."
echo "He will run:"
echo ""
echo "  git -C ~/.openclaw/workspace remote add backup ssh://${JIMMY_USER}@<THIS_MACHINE_IP>${BACKUP_DIR}"
echo "  git -C ~/.openclaw/workspace push backup master"
echo ""
echo "Jimmy only has write access to $BACKUP_DIR — nothing else."
