# Respiratory Monitor

A high-performance respiratory monitoring system using Raspberry Pi and Acconeer radar, with real-time video streaming and breathing waveform visualization on an Android app.

## Features

- **High-FPS Video Streaming**: Streams video at 60 FPS with HD resolution (1280x720)
- **Real-time Breathing Waveform**: Displays a live, breathing waveform alongside the video stream
- **Motion Detection**: Detects and reports child movement status
- **Alert System**: Provides alerts when breathing patterns are abnormal
- **Optimized Performance**: Efficient data processing and transmission for smooth operation

## System Requirements

### Raspberry Pi
- Raspberry Pi 4 (recommended) or Raspberry Pi 3B+
- Picamera2 module
- Acconeer radar sensor (XE121 or compatible)
- Stable network connection

### Android Device
- Android 7.0 or higher
- Stable network connection to the Raspberry Pi

## Installation

### Raspberry Pi Setup

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/respiratory_monitor.git
   cd respiratory_monitor
   ```

2. Run the installation script:
   ```
   ./install.sh
   ```

   This script will:
   - Install all required dependencies
   - Set up the Acconeer radar tools
   - Configure the system to start the monitoring service on boot
   - Start the service immediately

3. Verify the service is running:
   ```
   sudo systemctl status respiratory_monitor.service
   ```

### Android App Setup

1. Open the project in Android Studio:
   ```
   cd android/breathingmonitor2
   ```

2. Update the server IP address in `MainActivity.kt` to match your Raspberry Pi's IP address:
   ```kotlin
   private val serverIP = "192.168.50.175" // Replace with your Raspberry Pi's IP
   ```

3. Build and install the app on your Android device.

## Usage

1. Start the Raspberry Pi and ensure it's connected to the same network as your Android device.
2. The monitoring service should start automatically on boot.
3. Launch the Android app on your device.
4. The app will automatically connect to the Raspberry Pi and display the video stream with the breathing waveform.

## Troubleshooting

### Server Connection Issues
- Ensure the Raspberry Pi and Android device are on the same network
- Check that the IP address in the Android app matches the Raspberry Pi's IP
- Verify the service is running on the Raspberry Pi: `sudo systemctl status respiratory_monitor.service`

### Video Quality Issues
- Adjust the resolution and framerate in `combined_server.py` if needed
- Ensure adequate lighting for the camera

### Breathing Waveform Issues
- Check the radar sensor connection
- Adjust the `range_start` and `range_end` parameters in `combined_server.py` to match your setup

## Advanced Configuration

### Adjusting Video Quality
Edit `/breathing_monitor/combined_server.py` and modify the resolution and framerate parameters:

```python
server = CombinedServer(
    resolution=(1280, 720),  # Change resolution here
    framerate=60,            # Change framerate here
    ...
)
```

### Adjusting Breathing Monitoring Parameters
Edit `/breathing_monitor/combined_server.py` and modify the radar parameters:

```python
server = CombinedServer(
    range_start=0.2,         # Minimum detection range (meters)
    range_end=0.5,           # Maximum detection range (meters)
    update_rate=30,          # Breathing data update rate (Hz)
    ...
)
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
