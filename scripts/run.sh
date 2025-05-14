#!/bin/bash

# Script to run the combined server with the correct environment

set -e

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Default configuration
HOST="0.0.0.0"
VIDEO_PORT=8000
BREATHING_PORT=8001
RADAR_HOST="192.168.50.175"
RADAR_PORT=32345
RANGE_START=0.2
RANGE_END=0.5
UPDATE_RATE=10
VIDEO_WIDTH=640
VIDEO_HEIGHT=480
VIDEO_FPS=30
VIDEO_QUALITY=23  # Lower is better quality (23 is good balance)

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --host)
            HOST="$2"
            shift
            shift
            ;;
        --video-port)
            VIDEO_PORT="$2"
            shift
            shift
            ;;
        --breathing-port)
            BREATHING_PORT="$2"
            shift
            shift
            ;;
        --radar-host)
            RADAR_HOST="$2"
            shift
            shift
            ;;
        --radar-port)
            RADAR_PORT="$2"
            shift
            shift
            ;;
        --range-start)
            RANGE_START="$2"
            shift
            shift
            ;;
        --range-end)
            RANGE_END="$2"
            shift
            shift
            ;;
        --update-rate)
            UPDATE_RATE="$2"
            shift
            shift
            ;;
        --video-width)
            VIDEO_WIDTH="$2"
            shift
            shift
            ;;
        --video-height)
            VIDEO_HEIGHT="$2"
            shift
            shift
            ;;
        --video-fps)
            VIDEO_FPS="$2"
            shift
            shift
            ;;
        --video-quality)
            VIDEO_QUALITY="$2"
            shift
            shift
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --host HOST                  Host to bind server to (default: 0.0.0.0)"
            echo "  --video-port PORT            Port for video streaming (default: 8000)"
            echo "  --breathing-port PORT        Port for breathing data (default: 8001)"
            echo "  --radar-host HOST            Radar host (default: 192.168.50.175)"
            echo "  --radar-port PORT            Radar port (default: 32345)"
            echo "  --range-start METERS         Start of range in meters (default: 0.2)"
            echo "  --range-end METERS           End of range in meters (default: 0.5)"
            echo "  --update-rate HZ             Update rate in Hz (default: 10)"
            echo "  --video-width PIXELS         Video width (default: 640)"
            echo "  --video-height PIXELS        Video height (default: 480)"
            echo "  --video-fps FPS              Video frames per second (default: 30)"
            echo "  --video-quality QUALITY      Video quality (0-51, lower is better, default: 23)"
            echo "  --help                       Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Check if virtual environment exists
if [ ! -d "$REPO_DIR/respmon" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating it now...${NC}"
    "$SCRIPT_DIR/install_acconeer_sdk.sh"
fi

# Activate virtual environment
source "$REPO_DIR/respmon/bin/activate"

# Run the combined server
echo -e "${GREEN}Starting combined server...${NC}"
python -m breathing_monitor.combined_server \
    --host "$HOST" \
    --video-port "$VIDEO_PORT" \
    --breathing-port "$BREATHING_PORT" \
    --radar-host "$RADAR_HOST" \
    --radar-port "$RADAR_PORT" \
    --range-start "$RANGE_START" \
    --range-end "$RANGE_END" \
    --update-rate "$UPDATE_RATE" \
    --video-width "$VIDEO_WIDTH" \
    --video-height "$VIDEO_HEIGHT" \
    --video-fps "$VIDEO_FPS" \
    --video-quality "$VIDEO_QUALITY"

# Deactivate virtual environment
deactivate