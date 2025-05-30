#!/bin/bash

# Respiratory Monitor Installation Script
# This script installs and configures the respiratory monitor on a Raspberry Pi

set -e

# Function to display messages
echo_message() {
    echo -e "\e[32m$1\e[0m"
}

# Update and upgrade system
echo_message "Updating system packages..."
sudo apt-get update -y && sudo apt-get upgrade -y

# Install required dependencies
echo_message "Installing required packages..."
sudo apt-get install -y python3 python3-pip git build-essential cmake libatlas-base-dev

# Install Python dependencies
echo_message "Installing Python dependencies..."
pip3 install -r requirements.txt

# Set up Acconeer SDKs based on radar hardware
echo_message "Setting up Acconeer SDKs..."

# For A111 radar (using exptool)
if [ ! -d "acconeer-python-exploration" ]; then
    echo_message "Setting up Acconeer Exploration Tools for A111 radar..."
    git clone https://github.com/acconeer/acconeer-python-exploration.git
    cd acconeer-python-exploration
    pip3 install -r requirements.txt
    
    # Build the C++ package for radar connections
    echo_message "Building Acconeer radar C++ tools for A111..."
    cd cpp_server
    mkdir -p build && cd build
    cmake .. && make
    cd ../../..
fi

# For A121 radar (using acconeer-python-sdk)
echo_message "Installing Acconeer Python SDK for A121 radar..."
pip3 install acconeer-python-sdk

# Detect connected radar hardware
echo_message "Detecting connected radar hardware..."
python3 -c "
import importlib.util
import os

a121_available = importlib.util.find_spec('acconeer.a121') is not None
a111_available = importlib.util.find_spec('acconeer.exptool') is not None

if a121_available:
    print('A121 SDK detected')
if a111_available:
    print('A111 SDK (exptool) detected')
if not a121_available and not a111_available:
    print('No Acconeer SDK detected. Please check your installation.')
"

# Create environment variables
echo_message "Configuring environment variables..."
cat << EOF >> ~/.bashrc
# Acconeer environment variables
export PYTHONPATH=\$PYTHONPATH:$(pwd)
export ACCONEER_SERVER_PATH=$(pwd)/acconeer-python-exploration/cpp_server/build/server
EOF
source ~/.bashrc

# Make scripts executable
echo_message "Making scripts executable..."
chmod +x scripts/*.sh

# Install systemd service
echo_message "Installing systemd service..."
sudo cp scripts/respiratory_monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable respiratory_monitor.service

# Start the service
echo_message "Starting the respiratory monitor service..."
sudo systemctl start respiratory_monitor.service

# Display service status
echo_message "Service status:"
sudo systemctl status respiratory_monitor.service

# Provide instructions
echo_message "Installation complete!"
echo_message "The respiratory monitor service is now running and will start automatically on boot."
echo_message "To check the status of the service, run: sudo systemctl status respiratory_monitor.service"
echo_message "To view logs, run: sudo journalctl -u respiratory_monitor.service -f"
echo_message "To stop the service, run: sudo systemctl stop respiratory_monitor.service"
echo_message "To start the service, run: sudo systemctl start respiratory_monitor.service"
echo_message "To restart the service, run: sudo systemctl restart respiratory_monitor.service"
echo_message ""
echo_message "Android app configuration:"
echo_message "Make sure to update the server IP address in the Android app to match your Raspberry Pi's IP address."
echo_message "The default ports are: 9999 for video streaming and 32345 for breathing data."