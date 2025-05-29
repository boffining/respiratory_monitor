#!/usr/bin/python3

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

from picamera2 import Picamera2
# from libcamera import controls # For AF, if needed

import signal
import sys
import socket

Gst.init(None)

# --- Picamera2 Configuration ---
picam2 = Picamera2()

# Target resolution and framerate
target_width = 1920
target_height = 1080
target_fps = 60
# Example target bitrate for 1080p60 (e.g., 8 Mbps)
target_bitrate_kbps = 8000 # This will be used in GStreamer in bps
target_bitrate_bps = target_bitrate_kbps * 1000

# Configure Picamera2 - using main stream for encoding
video_config = picam2.create_video_configuration(
    main={"size": (target_width, target_height), "format": "YUV420"}, # YUV420 for encoder
    controls={"FrameRate": target_fps}
    # You can add a lores stream if you need it for other purposes
    # lores={"size": (640, 480), "format": "YUV420"}
)
picam2.configure(video_config)
picam2.start() # Picamera2 needs to be running if libcamerasrc isn't used,
               # or started briefly to get parameters if libcamerasrc is used.
               # For libcamerasrc, we primarily use Picamera2 for config discovery.
picam2.stop()

# Parameters for GStreamer (derived from the 'main' stream configuration now)
gst_format = "I420" # YUV420 from Picamera2 is often I420 for GStreamer raw caps
width = video_config['main']['size'][0]
height = video_config['main']['size'][1]
framerate = int(video_config['controls']['FrameRate'])
# Stride can be important, ensure it's from the correct stream config
stride = video_config['main']['stride']


picam2.close() # Release Picamera2 if libcamerasrc will take over
print("Picamera2 instance closed.")
print(f"Camera parameters for GStreamer: {width}x{height} @{framerate}fps, Format: {gst_format}, Stride: {stride}")


# --- GStreamer RTSP Server Configuration ---
class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)

        # Autofocus controls if your libcamerasrc supports them directly (example)
        af_mode_val = 2  # continuous
        af_speed_val = 0 # normal
        af_range_val = 2 # full

        self.launch_string = (
            # Using libcamerasrc with direct AF properties (if supported, adapt as per previous discussions)
            # If your libcamerasrc is very old and doesn't support these, AF might not work via GStreamer props
            f"libcamerasrc af-mode={af_mode_val} af-speed={af_speed_val} af-range={af_range_val} ! "
            f"video/x-raw,format={gst_format},width={width},height={height},framerate={framerate}/1 ! "
            f"videoconvert ! "
            # Use the hardware H.264 encoder: v4l2h264enc
            # Bitrate is set in bps for v4l2h264enc
            f"v4l2h264enc bitrate={target_bitrate_bps} ! "
            # Optional: specify H.264 profile/level if needed, e.g., for 1080p60 level 4.2 might be appropriate
            # f"video/x-h264,level=(string)4.2 ! "
            f"rtph264pay name=pay0 pt=96"
        )
        # Fallback if v4l2h264enc is not found, you might try omxh264enc (older)
        # self.launch_string = (
        #     f"libcamerasrc ! video/x-raw,format={gst_format},width={width},height={height},framerate={framerate}/1 ! "
        #     f"videoconvert ! omxh264enc target-bitrate={target_bitrate_bps} control-rate=variable ! "
        #     f"rtph264pay name=pay0 pt=96"
        # )

        print(f"Using GStreamer launch string: {self.launch_string}")

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

# ... (Rest of your GstServer, signal_handler, and main block)
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