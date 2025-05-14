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

# Detect which Acconeer SDK is available
A121_AVAILABLE=$(python3 -c "import importlib.util; print(1 if importlib.util.find_spec('acconeer.a121') is not None else 0)")
A111_AVAILABLE=$(python3 -c "import importlib.util; print(1 if importlib.util.find_spec('acconeer.exptool') is not None else 0)")

echo "Acconeer SDK detection: A121=$A121_AVAILABLE, A111=$A111_AVAILABLE"

# Set up for A111 radar if needed
if [ "$A111_AVAILABLE" -eq 1 ] && [ -d "acconeer-python-exploration" ]; then
    export ACCONEER_SERVER_PATH=$(pwd)/acconeer-python-exploration/cpp_server/build/server
    echo "Acconeer A111 server path set to: $ACCONEER_SERVER_PATH"
    
    # Check if Acconeer server is running (for A111 radar)
    if ! pgrep -f "acconeer.*server" > /dev/null; then
        echo "Starting Acconeer A111 server..."
        $ACCONEER_SERVER_PATH &
        SERVER_PID=$!
        echo "Acconeer server started with PID: $SERVER_PID"
        sleep 2  # Give the server time to start
    else
        echo "Acconeer A111 server is already running."
    fi
fi

# Set up for A121 radar if needed
if [ "$A121_AVAILABLE" -eq 1 ]; then
    echo "Acconeer A121 SDK detected, no separate server needed."
fi

# If no SDK is available, warn the user
if [ "$A121_AVAILABLE" -eq 0 ] && [ "$A111_AVAILABLE" -eq 0 ]; then
    echo "WARNING: No Acconeer SDK detected. Breathing monitoring will not be available."
    echo "Please install either acconeer-exptool (for A111) or acconeer-python-sdk (for A121)."
fi

# Start the combined server
echo "Starting combined server for video streaming and breathing monitoring..."
python3 -m breathing_monitor.combined_server

# Cleanup
if [ "$A111_AVAILABLE" -eq 1 ] && [ -n "$ACCONEER_SERVER_PATH" ]; then
    echo "Stopping Acconeer A111 server..."
    pkill -f "acconeer.*server" || true
fi

echo "Respiratory monitor service stopped."