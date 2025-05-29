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

target_width = 1920
target_height = 1080
target_fps = 60
target_bitrate_kbps = 8000
target_bitrate_bps = target_bitrate_kbps * 1000

video_config = picam2.create_video_configuration(
    main={"size": (target_width, target_height), "format": "YUV420"},
    controls={"FrameRate": target_fps}
)
picam2.configure(video_config)
picam2.start()
picam2.stop()

gst_format = "I420"
width = video_config['main']['size'][0]
height = video_config['main']['size'][1]
framerate = int(video_config['controls']['FrameRate'])
stride = video_config['main']['stride']

picam2.close()
print("Picamera2 instance closed.")
print(f"Camera parameters for GStreamer: {width}x{height} @{framerate}fps, Format: {gst_format}, Stride: {stride}")


# --- GStreamer RTSP Server Configuration ---
class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)

        # Autofocus controls for libcamerasrc
        af_mode_val = 2
        af_speed_val = 0
        af_range_val = 2

        # V4L2 controls for v4l2h264enc based on your v4l2-ctl output
        # Ensure 'framerate' and 'target_bitrate_bps' are correctly defined and accessible
        # For example, if they are accessible as global variables:
        # global framerate, target_bitrate_bps

        keyframe_interval = framerate  # Sets keyframe interval to 'framerate' frames (e.g., 60 for 1-second interval at 60fps)
        
        # From v4l2-ctl: video_bitrate_mode default 0 (VBR). If you want CBR, and 1 means CBR:
        bitrate_mode_val = 1
        
        # From v4l2-ctl: h264_level default 11 (Level 4.0). For 1080p@60fps, Level 4.2 is better.
        # Level 4.0 = 11, Level 4.1 = 12, Level 4.2 = 13. (These are typical V4L2 enum values)
        h264_level_val = 13 # Corresponds to H.264 Level 4.2

        # From v4l2-ctl: h264_profile default 4 (High). We can set it explicitly if desired.
        h264_profile_val = 4 # High Profile

        v4l2_encoder_controls = (
            f"controls,"  # Name of the GstStructure
            f"video_bitrate_mode={bitrate_mode_val},"
            f"video_bitrate={target_bitrate_bps},"    # Add this back!
            f"h264_i_frame_period={keyframe_interval}," # Add this back!
            f"h264_level={h264_level_val},"
            f"h264_profile={h264_profile_val}"
        )

        self.launch_string = (
            f"libcamerasrc af-mode={af_mode_val} af-speed={af_speed_val} af-range={af_range_val} ! "
            f"video/x-raw,format={gst_format},width={width},height={height},framerate={framerate}/1 ! "
            f"videoconvert ! "
            f"v4l2h264enc extra-controls=\"{v4l2_encoder_controls}\" ! "
            # Explicitly set H.264 caps based on encoder settings for SDP generation
            f"video/x-h264,stream-format=byte-stream,alignment=au,level=(string)4.2,profile=(string)high ! "
            f"rtph264pay name=pay0 pt=96"
        )
        print(f"Using GStreamer launch string: {self.launch_string}")

    def do_create_element(self, url):
        try:
            return Gst.parse_launch(self.launch_string)
        except GLib.Error as e:
            print(f"Fatal error parsing GStreamer launch string: {e}")
            print(f"Problematic launch string: {self.launch_string}")
            return None


# Picamera2 instance closed.
# Camera parameters for GStreamer: 640x360 @30fps, Format: I420, Stride: 640
# Using GStreamer launch string: libcamerasrc af-mode=2 af-speed=0 af-range=2 ! video/x-raw,format=I420,width=640,height=360,framerate=30/1 ! videoconvert ! x264enc speed-preset=ultrafast tune=zerolatency bitrate=1500 ! rtph264pay name=pay0 pt=96
# RTSP server started on rtsp://192.168.50.173:8554/stream


# Picamera2 instance closed.
# Camera parameters for GStreamer: 1920x1080 @60fps, Format: I420, Stride: 1920
# Using GStreamer launch string: libcamerasrc af-mode=2 af-speed=0 af-range=2 ! video/x-raw,format=I420,width=1920,height=1080,framerate=60/1 ! videoconvert ! v4l2h264enc extra-controls="controls,video_bitrate=8000000" ! rtph264pay name=pay0 pt=96
# RTSP server started on rtsp://192.168.50.173:8554/stream


# ... (Rest of your GstServer, signal_handler, and main block) ...
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