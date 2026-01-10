#!/bin/bash

set -e

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
cp -r src /opt/disposable-compute-platform/
cp -r types /opt/disposable-compute-platform/
cp -r utils /opt/disposable-compute-platform/
cp -r orchestrator /opt/disposable-compute-platform/
cp -r scheduler /opt/disposable-compute-platform/
cp -r streaming /opt/disposable-compute-platform/
cp -r storage /opt/disposable-compute-platform/
cp -r networking /opt/disposable-compute-platform/
cp -r api /opt/disposable-compute-platform/
cp src/main.py /opt/disposable-compute-platform/

# Copy service file
echo "Installing systemd service..."
cp deployment/disposable-compute-platform.service /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable and start service
systemctl enable disposable-compute-platform
systemctl start disposable-compute-platform

echo "Setup complete!"
echo "The Disposable Compute Platform is now running."
echo "Check status with: systemctl status disposable-compute-platform"