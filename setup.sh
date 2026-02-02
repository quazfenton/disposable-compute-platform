#!/bin/bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "This script must be run as root."
  exit 1
fi

echo "Setting up Disposable Compute Platform..."

# Create system user
if ! id "disposable-compute" &>/dev/null; then
    echo "Creating system user..."
    useradd -r -s /bin/false disposable-compute
fi

# Create necessary directories
echo "Creating directories..."
mkdir -p /var/lib/disposable-compute/pods
mkdir -p /var/lib/disposable-compute/snapshots
mkdir -p /var/lib/disposable-compute/containers
mkdir -p /opt/disposable-compute-platform

# Set permissions
chown -R disposable-compute:disposable-compute /var/lib/disposable-compute
chown -R disposable-compute:disposable-compute /opt/disposable-compute-platform

# Install Python dependencies
echo "Installing Python dependencies..."
python3 -m venv /opt/disposable-compute-platform/venv
source /opt/disposable-compute-platform/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Copy application files
echo "Copying application files..."
rm -rf /opt/disposable-compute-platform/src
cp -r src /opt/disposable-compute-platform/
cp requirements.txt /opt/disposable-compute-platform/
cp -r deployment /opt/disposable-compute-platform/

chown -R disposable-compute:disposable-compute /opt/disposable-compute-platform

# Copy service file
echo "Installing systemd service..."
cp deployment/disposable-compute-platform.service /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable and start service
systemctl enable --now disposable-compute-platform

echo "Setup complete!"
echo "The Disposable Compute Platform is now running."
echo "Check status with: systemctl status disposable-compute-platform"