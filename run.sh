#!/bin/bash

# Respiratory Monitor Run Script
# This script runs the combined server for video streaming and breathing monitoring

set -e

# Function to display messages
echo_message() {
    echo -e "\e[32m$1\e[0m"
}

# Set up environment
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Parse command line arguments
HOST="0.0.0.0"
VIDEO_PORT=9999
DATA_PORT=32345
RESOLUTION="1280x720"
FRAMERATE=60
RANGE_START=0.2
RANGE_END=0.5
UPDATE_RATE=30

# Display configuration
echo_message "Starting Respiratory Monitor with the following configuration:"
echo_message "Host: $HOST"
echo_message "Video Port: $VIDEO_PORT"
echo_message "Data Port: $DATA_PORT"
echo_message "Resolution: $RESOLUTION"
echo_message "Framerate: $FRAMERATE FPS"
echo_message "Detection Range: $RANGE_START-$RANGE_END meters"
echo_message "Update Rate: $UPDATE_RATE Hz"

# Run the combined server
echo_message "Starting combined server..."
python3 -m breathing_monitor.main \
    --host "$HOST" \
    --video-port "$VIDEO_PORT" \
    --data-port "$DATA_PORT" \
    --resolution "$RESOLUTION" \
    --framerate "$FRAMERATE" \
    --range-start "$RANGE_START" \
    --range-end "$RANGE_END" \
    --update-rate "$UPDATE_RATE"
