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

# # 2K resolution
# video_config = picam2.create_video_configuration(main={"size": (1920, 1080), "format": "RGB888"},
#                                                  lores={"size": (1920, 1080), "format": "YUV420"},
#                                                  controls={"FrameRate": 60})

# 2K resolution and 30fps framerate
video_config = picam2.create_video_configuration(main={"size": (2560, 1440), "format": "RGB888"},
                                                 lores={"size": (2560, 1440), "format": "YUV420"},
                                                 controls={"FrameRate": 30})


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
            #f"x264enc speed-preset=ultrafast tune=zerolatency bitrate=1500 ! "
            f"x264enc speed-preset=ultrafast tune=zerolatency bitrate=25000 ! "
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
        
        
        
        
        
        
        
"""        
>>> print(picam2.sensor_modes)
[0:37:10.598495807] [3754]  INFO Camera camera.cpp:1205 configuring streams: (0) 640x480-XBGR8888 (1) 1280x720-SRGGB10_CSI2P
[0:37:10.599166783] [3757]  INFO RPI vc4.cpp:630 Sensor: /base/soc/i2c0mux/i2c@1/imx519@1a - Selected sensor format: 1280x720-SRGGB10_1X10 - Selected unicam format: 1280x720-pRAA
[0:37:10.610757188] [3754]  INFO Camera camera.cpp:1205 configuring streams: (0) 640x480-XBGR8888 (1) 1920x1080-SRGGB10_CSI2P
[0:37:10.611407739] [3757]  INFO RPI vc4.cpp:630 Sensor: /base/soc/i2c0mux/i2c@1/imx519@1a - Selected sensor format: 1920x1080-SRGGB10_1X10 - Selected unicam format: 1920x1080-pRAA
[0:37:10.624355021] [3754]  INFO Camera camera.cpp:1205 configuring streams: (0) 640x480-XBGR8888 (1) 2328x1748-SRGGB10_CSI2P
[0:37:10.624982942] [3757]  INFO RPI vc4.cpp:630 Sensor: /base/soc/i2c0mux/i2c@1/imx519@1a - Selected sensor format: 2328x1748-SRGGB10_1X10 - Selected unicam format: 2328x1748-pRAA
[0:37:10.641492270] [3754]  INFO Camera camera.cpp:1205 configuring streams: (0) 640x480-XBGR8888 (1) 3840x2160-SRGGB10_CSI2P
[0:37:10.642125209] [3757]  INFO RPI vc4.cpp:630 Sensor: /base/soc/i2c0mux/i2c@1/imx519@1a - Selected sensor format: 3840x2160-SRGGB10_1X10 - Selected unicam format: 3840x2160-pRAA
[0:37:10.666010754] [3754]  INFO Camera camera.cpp:1205 configuring streams: (0) 640x480-XBGR8888 (1) 4656x3496-SRGGB10_CSI2P
[0:37:10.666663786] [3757]  INFO RPI vc4.cpp:630 Sensor: /base/soc/i2c0mux/i2c@1/imx519@1a - Selected sensor format: 4656x3496-SRGGB10_1X10 - Selected unicam format: 4656x3496-pRAA
[
{'format': SRGGB10_CSI2P, 'unpacked': 'SRGGB10', 'bit_depth': 10, 'size': (1280, 720), 'fps': 80.01, 'crop_limits': (1048, 1042, 2560, 1440), 'exposure_limits': (287, 120729139, 20000)}, 
{'format': SRGGB10_CSI2P, 'unpacked': 'SRGGB10', 'bit_depth': 10, 'size': (1920, 1080), 'fps': 60.05, 'crop_limits': (408, 674, 3840, 2160), 'exposure_limits': (282, 118430097, 20000)}, 
{'format': SRGGB10_CSI2P, 'unpacked': 'SRGGB10', 'bit_depth': 10, 'size': (2328, 1748), 'fps': 30.0, 'crop_limits': (0, 0, 4656, 3496), 'exposure_limits': (305, 127960311, 20000)}, 
{'format': SRGGB10_CSI2P, 'unpacked': 'SRGGB10', 'bit_depth': 10, 'size': (3840, 2160), 'fps': 18.0, 'crop_limits': (408, 672, 3840, 2160), 'exposure_limits': (491, 206049113, 20000)}, 
{'format': SRGGB10_CSI2P, 'unpacked': 'SRGGB10', 'bit_depth': 10, 'size': (4656, 3496), 'fps': 9.0, 'crop_limits': (0, 0, 4656, 3496), 'exposure_limits': (592, 248567756, 20000)}]

"""