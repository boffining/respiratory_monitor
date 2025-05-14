#!/bin/bash

# Respiratory Monitor Setup Verification Script
# This script verifies that all required components are properly installed and configured

set -e

# Function to display messages
echo_message() {
    echo -e "\e[32m$1\e[0m"
}

echo_error() {
    echo -e "\e[31m$1\e[0m"
}

echo_warning() {
    echo -e "\e[33m$1\e[0m"
}

# Navigate to the project directory
cd "$(dirname "$0")/.."

# Check Python installation
echo_message "Checking Python installation..."
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version)
    echo_message "✓ Python is installed: $python_version"
else
    echo_error "✗ Python 3 is not installed. Please install Python 3."
    exit 1
fi

# Check pip installation
echo_message "Checking pip installation..."
if command -v pip3 &> /dev/null; then
    pip_version=$(pip3 --version)
    echo_message "✓ pip is installed: $pip_version"
else
    echo_error "✗ pip is not installed. Please install pip."
    exit 1
fi

# Check if virtual environment exists
echo_message "Checking virtual environment..."
if [ -d "venv" ]; then
    echo_message "✓ Virtual environment exists."
    source venv/bin/activate
    echo_message "✓ Virtual environment activated."
else
    echo_warning "! Virtual environment not found. Creating one..."
    python3 -m venv venv
    source venv/bin/activate
    echo_message "✓ Virtual environment created and activated."
fi

# Check Python dependencies
echo_message "Checking Python dependencies..."
pip3 install -r requirements.txt
echo_message "✓ Python dependencies installed."

# Check Acconeer SDK installation
echo_message "Checking Acconeer SDK installation..."
if python3 -c "import acconeer.a121" 2>/dev/null; then
    echo_message "✓ Acconeer A121 SDK is installed."
    a121_available=true
else
    echo_warning "! Acconeer A121 SDK is not installed."
    a121_available=false
fi

if python3 -c "import acconeer.exptool" 2>/dev/null; then
    echo_message "✓ Acconeer Exploration Tool (for A111) is installed."
    a111_available=true
else
    echo_warning "! Acconeer Exploration Tool (for A111) is not installed."
    a111_available=false
fi

if [ "$a121_available" = false ] && [ "$a111_available" = false ]; then
    echo_error "✗ No Acconeer SDK is installed. Please install at least one SDK."
    echo_error "  For A121 radar: pip install acconeer-python-sdk"
    echo_error "  For A111 radar: pip install acconeer-exptool"
    exit 1
fi

# Check Acconeer server for A111
if [ "$a111_available" = true ]; then
    echo_message "Checking Acconeer server for A111 radar..."
    if [ -d "acconeer-python-exploration" ]; then
        echo_message "✓ Acconeer Exploration Tool repository exists."
        
        # Check if C++ server is built
        if [ -f "acconeer-python-exploration/cpp_server/build/server" ]; then
            echo_message "✓ Acconeer C++ server is built."
            export ACCONEER_SERVER_PATH=$(pwd)/acconeer-python-exploration/cpp_server/build/server
            echo_message "✓ ACCONEER_SERVER_PATH set to: $ACCONEER_SERVER_PATH"
        else
            echo_warning "! Acconeer C++ server is not built. Building now..."
            cd acconeer-python-exploration/cpp_server
            mkdir -p build && cd build
            cmake .. && make
            cd ../../../
            export ACCONEER_SERVER_PATH=$(pwd)/acconeer-python-exploration/cpp_server/build/server
            echo_message "✓ Acconeer C++ server built successfully."
            echo_message "✓ ACCONEER_SERVER_PATH set to: $ACCONEER_SERVER_PATH"
        fi
    else
        echo_warning "! Acconeer Exploration Tool repository not found. Cloning now..."
        git clone https://github.com/acconeer/acconeer-python-exploration.git
        cd acconeer-python-exploration
        pip3 install -r requirements.txt
        cd cpp_server
        mkdir -p build && cd build
        cmake .. && make
        cd ../../../
        export ACCONEER_SERVER_PATH=$(pwd)/acconeer-python-exploration/cpp_server/build/server
        echo_message "✓ Acconeer Exploration Tool repository cloned and built successfully."
        echo_message "✓ ACCONEER_SERVER_PATH set to: $ACCONEER_SERVER_PATH"
    fi
fi

# Check camera
echo_message "Checking camera..."
if python3 -c "from picamera2 import Picamera2; Picamera2()" 2>/dev/null; then
    echo_message "✓ Camera is accessible."
else
    echo_warning "! Camera is not accessible. This might be normal if you're not running on a Raspberry Pi."
fi

# Check if systemd service is installed
echo_message "Checking systemd service..."
if [ -f "/etc/systemd/system/respiratory_monitor.service" ]; then
    echo_message "✓ Systemd service is installed."
    service_status=$(systemctl is-active respiratory_monitor.service)
    if [ "$service_status" = "active" ]; then
        echo_message "✓ Respiratory monitor service is running."
    else
        echo_warning "! Respiratory monitor service is not running."
        echo_warning "  To start the service, run: sudo systemctl start respiratory_monitor.service"
    fi
else
    echo_warning "! Systemd service is not installed."
    echo_warning "  To install the service, run: sudo cp scripts/respiratory_monitor.service /etc/systemd/system/"
    echo_warning "  Then run: sudo systemctl daemon-reload && sudo systemctl enable respiratory_monitor.service"
fi

# Check if scripts are executable
echo_message "Checking script permissions..."
if [ -x "scripts/start_combined_server.sh" ]; then
    echo_message "✓ start_combined_server.sh is executable."
else
    echo_warning "! start_combined_server.sh is not executable. Making it executable..."
    chmod +x scripts/start_combined_server.sh
    echo_message "✓ start_combined_server.sh is now executable."
fi

if [ -x "run.sh" ]; then
    echo_message "✓ run.sh is executable."
else
    echo_warning "! run.sh is not executable. Making it executable..."
    chmod +x run.sh
    echo_message "✓ run.sh is now executable."
fi

# Final message
echo_message "\nSetup verification complete!"
echo_message "To start the respiratory monitor manually, run: ./run.sh"
echo_message "To start the respiratory monitor as a service, run: sudo systemctl start respiratory_monitor.service"
echo_message "To view logs, run: sudo journalctl -u respiratory_monitor.service -f"