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
# We need to get the stride and format for the GStreamer pipeline
# Start picam2 to get the actual stream properties
picam2.start() # Start temporarily to get stream info
stream_metadata = picam2.capture_metadata() # Get metadata after first frame
picam2.stop() # Stop it, GStreamer will handle the feed later

# If using lores stream for encoding:
sensor_format = picam2.camera_controls['ColourSpace'].value # e.g. "sYCC" or "Jpeg"
# For GStreamer, we need a raw format like I420 or NV12 if YUV420 is from lores
# Picamera2's "YUV420" for lores stream is often I420
gst_format = "I420" # Common for YUV420 from picam2 lores
width = video_config['lores']['size'][0]
height = video_config['lores']['size'][1]
framerate = int(video_config['controls']['FrameRate'])
stride = video_config['lores']['stride'] # Stride for the lores stream

print(f"Camera configured: {width}x{height} @{framerate}fps, Format: {gst_format}, Stride: {stride}")

# --- GStreamer RTSP Server Configuration ---
class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)
        # Pipeline for picam2 using appsrc (more complex to feed directly)
        # Using fdkaac for audio (optional, remove if no mic)
        # For video, using libcamerasrc is often simpler if available and configured correctly.
        # However, to integrate with picam2 object directly for more control,
        # one might typically use appsrc. For simplicity with standard GStreamer elements,
        # we'll assume libcamerasrc or a similar direct plugin.
        # If direct plugin is an issue, picam2's `start_recording` with a custom output
        # that feeds GStreamer is another advanced route.

        # Let's try with libcamerasrc first as it's cleaner if it works directly for the stream.
        # Note: libcamerasrc might take control from the picam2 object if not careful.
        # A safer bet for picam2 integration is often to have picam2 output to a file or fd
        # and have GStreamer read that, or use appsrc.

        # Using a pipeline that directly invokes libcamera via libcamerasrc
        # This pipeline assumes you want to encode H.264
        # The `! queue !` elements are good for buffering between threads
        self.launch_string = (
            f"libcamerasrc ! "
            f"video/x-raw,format={gst_format},width={width},height={height},framerate={framerate}/1 ! "
            f"videoconvert ! " # Converts to a format x264enc can use
            f"x264enc speed-preset=ultrafast tune=zerolatency bitrate=1500 ! " # Adjust bitrate as needed
            f"rtph264pay name=pay0 pt=96"
        )

        # Alternative if picam2 object should manage the camera and feed GStreamer:
        # This would involve picam2 writing to a file descriptor or using appsrc,
        # which is more complex to show in a basic script.
        # For now, we rely on libcamerasrc to re-configure the camera similarly.
        # If you have issues with libcamerasrc fighting picam2,
        # you might need to ensure picam2 is stopped or use a different approach.

        print(f"Using GStreamer launch string: {self.launch_string}")

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

    # This function would be used if you were feeding frames from picam2 into appsrc
    # def do_configure(self, rtsp_media):
    #     self.appsrc = rtsp_media.get_element().get_child_by_name('source')
    #     # Start picam2 and attach frame feeder here
    #     # picam2.start()
    #     # GLib.timeout_add(1000 // framerate, self.feed_frames, rtsp_media) # Example
    #     pass

    # def feed_frames(self, rtsp_media):
    #    if not rtsp_media.get_element() or not self.appsrc:
    #        return False # Stop feeding
    #    frame = picam2.capture_array("lores") # Capture from the lores stream
    #    buf = Gst.Buffer.new_wrapped(frame.tobytes())
    #    if self.appsrc.push_buffer(buf) != Gst.FlowReturn.OK:
    #        print("Error pushing buffer to appsrc")
    #        return False # Stop feeding
    #    return True


class GstServer():
    def __init__(self):
        self.server = GstRtspServer.RTSPServer()
        self.factory = SensorFactory()
        self.factory.set_shared(True) # Allow multiple clients to connect to the same stream

        # Set up the mount point
        mounts = self.server.get_mount_points()
        mounts.add_factory("/stream", self.factory)

        # Attach the server to the GObject main loop
        self.server.attach(None) # Use default main context

        # Get local IP address
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80)) # Connect to a public DNS server to find local IP
            self.ip_address = s.getsockname()[0]
            s.close()
        except Exception as e:
            print(f"Could not automatically determine IP address: {e}")
            self.ip_address = "<your_pi_ip>"

        print(f"RTSP server started on rtsp://{self.ip_address}:8554/stream")
        print("Press Ctrl+C to stop the server.")

# --- Main Loop and Signal Handling ---
loop = GLib.MainLoop()

def signal_handler(sig, frame):
    print("\nStopping RTSP server and Picamera2...")
    loop.quit()
    if 'picam2' in globals() and picam2.started:
        picam2.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    # Start picam2 if not using appsrc (libcamerasrc will handle it)
    # If you were using appsrc, you'd picam2.start() here or in do_configure
    # For libcamerasrc, it's better to let it initialize the camera.
    # Ensure picam2 is not actively holding the camera if libcamerasrc is used.
    # The initial picam2.start()/stop() was just to get metadata.

    server = GstServer()
    try:
        loop.run()
    except Exception as e:
        print(f"Error during main loop: {e}")
    finally:
        if 'picam2' in globals() and picam2.started:
            picam2.stop()