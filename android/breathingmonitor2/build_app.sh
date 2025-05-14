#!/bin/bash

# Script to build the Android app

set -e

# Navigate to the Android project directory
cd "$(dirname "$0")/breathingmonitor2"

# Check if gradlew exists and is executable
if [ ! -x "./gradlew" ]; then
    chmod +x ./gradlew
    echo "Made gradlew executable"
fi

# Clean and build the project
echo "Building Android app..."
./gradlew clean build

# Check if build was successful
if [ $? -eq 0 ]; then
    echo "Build successful!"
    
    # Find the APK file
    APK_PATH=$(find ./app/build/outputs/apk -name "*.apk" | head -n 1)
    
    if [ -n "$APK_PATH" ]; then
        echo "APK file created at: $APK_PATH"
        
        # Copy APK to a more accessible location
        mkdir -p ../apk
        cp "$APK_PATH" "../apk/BreathingMonitor-$(date +%Y%m%d).apk"
        echo "APK copied to: ../apk/BreathingMonitor-$(date +%Y%m%d).apk"
    else
        echo "No APK file found in build outputs"
    fi
else
    echo "Build failed!"
    exit 1
fi