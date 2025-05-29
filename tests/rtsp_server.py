#!/usr/bin/python3

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

from picamera2 import Picamera2
# from libcamera import controls # Not strictly needed if using integer/string values directly

import signal
import sys
import socket

Gst.init(None)

# --- Picamera2 Configuration ---
picam2 = Picamera2()
# Default resolution and framerate, adjust as needed
# video_config = picam2.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"},
                                                #  lores={"size": (640, 360), "format": "YUV420"},
                                                #  controls={"FrameRate": 30})

# 2K resolution
video_config = picam2.create_video_configuration(main={"size": (2560, 1440), "format": "RGB888"},
                                                 lores={"size": (1280, 720), "format": "YUV420"},
                                                 controls={"FrameRate": 60})

# 2K resolution and 60fps framerate
# video_config = picam2.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"},
                                                #  lores={"size": (640, 360), "format": "YUV420"},
                                                #  controls={"FrameRate": 30})


picam2.configure(video_config)
picam2.start()
picam2.stop()

gst_format = "I420"
width = video_config['lores']['size'][0]
height = video_config['lores']['size'][1]
framerate = int(video_config['controls']['FrameRate'])
stride = video_config['lores']['stride']

picam2.close()
print("Picamera2 instance closed.")
print(f"Camera parameters for GStreamer: {width}x{height} @{framerate}fps, Format: {gst_format}, Stride: {stride}")


# --- GStreamer RTSP Server Configuration ---
class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)

        # Define autofocus settings based on your gst-inspect output
        # AfMode: 0=manual, 1=auto, 2=continuous
        # AfSpeed: 0=normal, 1=fast
        # AfRange: 0=normal, 1=macro, 2=full
        
        # Property names from your gst-inspect output appear to be lowercase with hyphens:
        # e.g., af-mode, af-speed, af-range
        
        # Note: GStreamer property values can sometimes be integers or string representations of the enum
        # Check gst-inspect output for default values and accepted types if unsure.
        # For enums, integer values are usually reliable.
        af_mode_val = 2      # continuous
        af_speed_val = 0     # normal
        af_range_val = 2     # full

        # Construct the libcamerasrc element with direct properties
        # Ensure property names match exactly what gst-inspect-1.0 libcamerasrc shows
        self.launch_string = (
            f"libcamerasrc af-mode={af_mode_val} af-speed={af_speed_val} af-range={af_range_val} ! "
            f"video/x-raw,format={gst_format},width={width},height={height},framerate={framerate}/1 ! "
            f"videoconvert ! "
            f"x264enc speed-preset=ultrafast tune=zerolatency bitrate=1500 ! "
            f"rtph264pay name=pay0 pt=96"
        )
        print(f"Using GStreamer launch string: {self.launch_string}")

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

# ... (rest of your GstServer, signal_handler, and main block remains the same) ...
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
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    server = GstServer()
    try:
        loop.run()
    except Exception as e:
        print(f"Error during main loop: {e}")