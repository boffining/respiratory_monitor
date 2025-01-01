#!/bin/bash

# Raspberry Pi Breathing Monitor Installation Script
# This script sets up the environment, installs necessary dependencies, and configures the radar array for the breathing monitor.

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
sudo apt-get install -y python3 python3-pip git build-essential cmake

# Clone the repository
echo_message "Cloning the repository..."
git clone <GITHUB_REPO_URL> breathing_monitor
cd breathing_monitor

# Install Python dependencies
echo_message "Installing Python dependencies..."
pip3 install -r requirements.txt

# Set up Acconeer Exploration Tools
echo_message "Setting up Acconeer Exploration Tools..."
if [ ! -d "acconeer-python-exploration" ]; then
    git clone https://github.com/acconeer/acconeer-python-exploration.git
    cd acconeer-python-exploration
    pip3 install -r requirements.txt
    cd ..
fi

# Build and launch the C++ package for radar connections
echo_message "Building Acconeer radar C++ tools..."
cd acconeer-python-exploration/cpp_server
mkdir -p build && cd build
cmake .. && make
cd ../../../

# Create environment variables
echo_message "Configuring environment variables..."
cat << EOF >> ~/.bashrc
# Acconeer environment variables
export PYTHONPATH=
export ACCONEER_SERVER_PATH=$(pwd)/acconeer-python-exploration/cpp_server/build/server
EOF
source ~/.bashrc

# Ensure the server launches on boot
echo_message "Configuring server to start on boot..."
SERVICE_PATH="/etc/systemd/system/radar_server.service"
sudo bash -c "cat > $SERVICE_PATH" << EOF
[Unit]
Description=Acconeer Radar Server
After=network.target

[Service]
ExecStart=\$ACCONEER_SERVER_PATH
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable radar_server.service

# Provide execution instructions
echo_message "Setup complete! To run the application, use the following commands:"
echo_message "cd ~/breathing_monitor && python3 main.py"
