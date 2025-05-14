#!/bin/bash

# Script to install the correct version of the Acconeer SDK
# This script will install the Acconeer SDK in a virtual environment

set -e

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}Installing Acconeer SDK...${NC}"
echo "Repository directory: $REPO_DIR"

# Check if virtual environment exists
if [ ! -d "$REPO_DIR/respmon" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv "$REPO_DIR/respmon"
fi

# Activate virtual environment
source "$REPO_DIR/respmon/bin/activate"

# Install dependencies
echo -e "${GREEN}Installing dependencies...${NC}"
pip install --upgrade pip
pip install wheel

# Try to detect which radar is connected
echo -e "${YELLOW}Detecting radar type...${NC}"

# Check if A121 radar is connected
if lsusb | grep -q "2886:802d"; then
    echo -e "${GREEN}Acconeer A121 radar detected!${NC}"
    echo "Installing A121 SDK..."
    pip install acconeer-python-a121
elif lsusb | grep -q "0483:a121"; then
    echo -e "${GREEN}Acconeer A121 radar detected!${NC}"
    echo "Installing A121 SDK..."
    pip install acconeer-python-a121
elif lsusb | grep -q "0483:5740"; then
    echo -e "${GREEN}Acconeer A111 radar detected!${NC}"
    echo "Installing A111 SDK (exptool)..."
    pip install acconeer-exptool==3.4.7
else
    echo -e "${YELLOW}No Acconeer radar detected. Installing both SDKs...${NC}"
    echo "Installing A111 SDK (exptool)..."
    pip install acconeer-exptool==3.4.7
    echo "Installing A121 SDK..."
    pip install acconeer-python-a121
fi

# Install other dependencies
echo -e "${GREEN}Installing other dependencies...${NC}"
pip install numpy scipy matplotlib pykalman picamera2 pillow

# Deactivate virtual environment
deactivate

echo -e "${GREEN}Installation complete!${NC}"
echo -e "${YELLOW}To use the virtual environment, run:${NC}"
echo "source $REPO_DIR/respmon/bin/activate"