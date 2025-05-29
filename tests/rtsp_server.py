#!/usr/bin/python3

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

from picamera2 import Picamera2
import signal
import sys
import socket # To get local IP

# Initialize GStreamer
Gst.init(None)

# --- Picamera2 Configuration ---
picam2 = Picamera2()
# Adjust resolution and framerate as needed
video_config = picam2.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"},
                                                 lores={"size": (640, 360), "format": "YUV420"}, # LoRes stream for encoding
                                                 controls={"FrameRate": 30})
picam2.configure(video_config)

# Start picam2 briefly to ensure configuration is applied and to allow metadata/stride retrieval
picam2.start()
picam2.stop()

# Extract necessary parameters from the configuration
# Picamera2's "YUV420" for lores stream is often I420 for GStreamer
gst_format = "I420"
width = video_config['lores']['size'][0]
height = video_config['lores']['size'][1]
framerate = int(video_config['controls']['FrameRate'])
# Stride is important for correct buffer interpretation if there's padding.
# libcamerasrc should ideally handle this, but good to have the correct value.
stride = video_config['lores']['stride']

# IMPORTANT: Close the Picamera2 instance to release libcamera resources
# before libcamerasrc tries to use them.
picam2.close()
print("Picamera2 instance closed.")

print(f"Camera parameters for GStreamer: {width}x{height} @{framerate}fps, Format: {gst_format}, Stride: {stride}")


# --- GStreamer RTSP Server Configuration ---
class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)
        self.launch_string = (
            f"libcamerasrc ! "
            f"video/x-raw,format={gst_format},width={width},height={height},framerate={framerate}/1 ! "
            f"videoconvert ! "
            f"x264enc speed-preset=ultrafast tune=zerolatency bitrate=1500 ! "
            f"rtph264pay name=pay0 pt=96"
        )
        print(f"Using GStreamer launch string: {self.launch_string}")

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

class GstServer():
    def __init__(self):
        self.server = GstRtspServer.RTSPServer()
        self.factory = SensorFactory()
        self.factory.set_shared(True)

        mounts = self.server.get_mount_points()
        mounts.add_factory("/stream", self.factory)
        self.server.attach(None)

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self.ip_address = s.getsockname()[0]
            s.close()
        except Exception as e:
            print(f"Could not automatically determine IP address: {e}")
            self.ip_address = "<your_pi_ip>"

        print(f"RTSP server started on rtsp://{self.ip_address}:8554/stream")
        print("Press Ctrl+C to stop the server.")

loop = GLib.MainLoop()

def signal_handler(sig, frame):
    print("\nStopping RTSP server...")
    loop.quit()
    # Picamera2 object is already closed if initialization was successful.
    # No need to call picam2.stop() here again on a closed object.
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    server = GstServer()
    try:
        loop.run()
    except Exception as e:
        print(f"Error during main loop: {e}")
    # finally:
        # Picamera2 object should be closed before loop.run() if this point is reached
        # No specific picam2 cleanup needed here anymore as it's closed after configuration.