#!/bin/bash

# Start the combined server for video streaming and breathing monitoring
# This script starts the combined server that handles both video streaming and breathing data

# Navigate to the project directory
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set environment variables
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Start the combined server
echo "Starting combined server for video streaming and breathing monitoring..."
python3 -m breathing_monitor.combined_server

# Keep the script running
wait