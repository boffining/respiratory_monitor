#!/bin/bash

# Script to install the respiratory monitor service

set -e

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root${NC}"
    echo "Use: sudo $0"
    exit 1
fi

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}Installing respiratory monitor service...${NC}"

# Copy service file to systemd directory
echo -e "${YELLOW}Copying service file...${NC}"
cp "$SCRIPT_DIR/respiratory-monitor.service" /etc/systemd/system/

# Reload systemd
echo -e "${YELLOW}Reloading systemd...${NC}"
systemctl daemon-reload

# Enable service
echo -e "${YELLOW}Enabling service...${NC}"
systemctl enable respiratory-monitor.service

echo -e "${GREEN}Installation complete!${NC}"
echo -e "${YELLOW}To start the service, run:${NC}"
echo "sudo systemctl start respiratory-monitor.service"
echo -e "${YELLOW}To check the status, run:${NC}"
echo "sudo systemctl status respiratory-monitor.service"
echo -e "${YELLOW}To view logs, run:${NC}"
echo "sudo journalctl -u respiratory-monitor.service -f"