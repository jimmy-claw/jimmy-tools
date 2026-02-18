#!/bin/bash
set -e

# Fix apt sources
sudo sed -i 's|deb cdrom:|# deb cdrom:|g' /etc/apt/sources.list 2>/dev/null || true
sudo tee /etc/apt/sources.list > /dev/null << 'EOF'
deb http://archive.ubuntu.com/ubuntu noble main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu noble-security main restricted universe multiverse
EOF

# Update and install essentials
sudo apt update
sudo apt install -y wpasupplicant curl git htop tmux build-essential

# Fix WiFi - write proper netplan
sudo tee /etc/netplan/60-wifi.yaml > /dev/null << 'EOF2'
network:
  version: 2
  renderer: networkd
  wifis:
    wlx80afcab1cbfd:
      dhcp4: true
      access-points:
        "Internety":
          password: "LQDDTY02"
EOF2

sudo chmod 600 /etc/netplan/60-wifi.yaml
sudo netplan apply

echo "Done! WiFi connecting..."
sleep 5
ip addr show wlx80afcab1cbfd
