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

        # Autofocus controls for libcamerasrc (ensure these are correct for your libcamerasrc)
        af_mode_val = 2
        af_speed_val = 0
        af_range_val = 2

        # V4L2 controls for v4l2h264enc
        # IMPORTANT: Verify these control names and values using 'v4l2-ctl -d /dev/videoXX --list-ctrls'
        # target_bitrate_bps is already defined globally in your script (e.g., 8000000)

        # Example: Assuming 'v4l2-ctl' confirms:
        # - 'video_bitrate' is the control for bitrate.
        # - 'h264_i_frame_period' is for keyframe interval (e.g., 60 for 1-second interval at 60fps).
        # - 'video_bitrate_mode' exists, and e.g., '1' means CBR (Constant Bitrate).
        #   If 'video_bitrate_mode' is not available or needed, you can omit it.
        
        # Adjust these based on your 'v4l2-ctl' output and needs:
        keyframe_interval = framerate # Set keyframe interval to 1 second (framerate frames)
        bitrate_mode_cbr = 1 # Example value for CBR, check v4l2-ctl for actual values

        v4l2_encoder_controls = (
            f"controls," # This is the structure name
            f"video_bitrate_mode={bitrate_mode_cbr}" # Set bitrate mode (e.g., CBR)
            # f"video_bitrate={target_bitrate_bps},"   # Set target bitrate
            # f"h264_i_frame_period={keyframe_interval}" # Set keyframe interval
        )
        # If video_bitrate_mode is not found or you want to omit it, simplify:
        # v4l2_encoder_controls = (
        #     f"controls,"
        #     f"video_bitrate={target_bitrate_bps},"
        #     f"h264_i_frame_period={keyframe_interval}"
        # )


        self.launch_string = (
            f"libcamerasrc af-mode={af_mode_val} af-speed={af_speed_val} af-range={af_range_val} ! "
            f"video/x-raw,format={gst_format},width={width},height={height},framerate={framerate}/1 ! "
            f"videoconvert ! "
            f"v4l2h264enc extra-controls=\"{v4l2_encoder_controls}\" ! "
            # Adding explicit H.264 caps can help ensure compatibility with the payloader
            f"video/x-h264,stream-format=byte-stream,alignment=au ! "
            f"rtph264pay name=pay0 pt=96"
        )
        print(f"Using GStreamer launch string: {self.launch_string}")

    def do_create_element(self, url):
        # It's good to catch GStreamer parsing errors here for clearer debugging
        try:
            return Gst.parse_launch(self.launch_string)
        except GLib.Error as e:
            print(f"Error parsing GStreamer launch string: {e}")
            print(f"Problematic launch string: {self.launch_string}")
            return None # Or handle error appropriately


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