#!/bin/bash
# Install Athena systemd services
# Usage: sudo ./deploy/install.sh

set -e

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_DIR="/etc/systemd/system"

echo "=== Athena Service Installer ==="
echo "Deploy dir: $DEPLOY_DIR"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo $0"
    exit 1
fi

# Copy service files
for service in athena-data athena-autonomy athena-web; do
    src="$DEPLOY_DIR/${service}.service"
    dst="$SERVICE_DIR/${service}.service"

    if [ -f "$src" ]; then
        cp "$src" "$dst"
        echo "Installed: $dst"
    else
        echo "WARN: $src not found, skipping"
    fi
done

# Reload systemd
systemctl daemon-reload
echo ""
echo "Services installed. Available commands:"
echo ""
echo "  # Enable services to start on boot"
echo "  sudo systemctl enable athena-data athena-autonomy athena-web"
echo ""
echo "  # Start services"
echo "  sudo systemctl start athena-data"
echo "  sudo systemctl start athena-autonomy"
echo "  sudo systemctl start athena-web"
echo ""
echo "  # Check status"
echo "  sudo systemctl status athena-data athena-autonomy athena-web"
echo ""
echo "  # View logs"
echo "  journalctl -u athena-autonomy -f"
echo "  journalctl -u athena-web -f"
echo ""
echo "  # Stop all"
echo "  sudo systemctl stop athena-data athena-autonomy athena-web"
echo ""
echo "=== Installation complete ==="
