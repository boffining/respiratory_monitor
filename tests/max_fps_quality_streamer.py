#!/usr/bin/python3

import time
import logging
import subprocess
import signal
import sys
import os
from picamera2 import Picamera2
from picamera2.outputs import FileOutput
from picamera2.encoders import Quality # Though we'll use GStreamer for encoding

# --- Configuration ---
# Target FPS to aim for when selecting a mode.
# The script will try to find the highest resolution at this FPS or higher.
# If no mode supports this, it will pick the highest resolution at its max FPS.
TARGET_HIGH_FPS = 60

# GStreamer Pipeline Configuration
GST_ENCODER = "v4l2h264enc"  # Use 'omxh264enc' for older Pis if v4l2h264enc is not available
GST_BITRATE_KBPS = 20000    # 20 Mbps, very high for local streaming. Adjust if needed.
# For "highest quality" with v4l2h264enc, we can also try to set constant QP
# extra-controls="controls,h264_level=4,h264_profile=4,frame_level_rate_control_enable=0,video_bitrate=0,h264_i_frame_period=30,h264_minimum_qp_value=10,h264_maximum_qp_value=25;"
# The qp-mode for omxh264enc might be 'cqp' for constant QP.
#GST_TARGET_HOST = "127.0.0.1" # Loopback for testing. Change to client IP or multicast.
GST_TARGET_HOST = "192.169.50.173"
# For streaming to any device on the LAN, use a specific client IP or a multicast address.
# If using a specific client IP: GST_TARGET_HOST = "CLIENT_IP_ADDRESS"
# If using multicast: GST_TARGET_HOST = "224.1.1.1" (client needs to join this)
GST_TARGET_PORT = 5004

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MaxPerfStreamer")

# Global variable for GStreamer process
gst_process = None

def select_optimal_camera_mode(picam2):
    """
    Selects the camera mode that offers the highest resolution
    at TARGET_HIGH_FPS or above, or the mode with the highest
    pixel throughput (resolution * fps).
    """
    sensor_modes = picam2.sensor_modes
    if not sensor_modes:
        logger.error("No sensor modes found!")
        return None

    logger.info("Available sensor modes:")
    for i, mode in enumerate(sensor_modes):
        logger.info(f"  Mode {i}: {mode}")

    best_mode = None
    max_pixel_throughput = 0
    highest_res_at_target_fps = (0, 0) # width, height
    actual_fps_for_highest_res = 0

    # Try to find highest resolution at or above TARGET_HIGH_FPS
    for mode_info in sensor_modes:
        width, height = mode_info["size"]
        # Picamera2 mode_info doesn't always directly give max FPS for that specific mode.
        # We configure with the mode and *request* a frame rate.
        # For simplicity in selection, we'll assume FPS can be high if not constrained by mode.
        # A more accurate way would be to test configuration for each mode.

        # Heuristic: prioritize modes that can achieve TARGET_HIGH_FPS
        # If picam2 can achieve TARGET_HIGH_FPS with this mode's resolution:
        current_res = width * height
        if current_res > (highest_res_at_target_fps[0] * highest_res_at_target_fps[1]):
            # Test if this mode *could* support high FPS by a temporary config
            # This is a bit complex, so we'll simplify: assume if not limited by 'fps' field
            # in mode_info (if present, some cameras have it).
            # For now, let's assume any mode *could* run fast unless explicitly limited.
            highest_res_at_target_fps = (width, height)
            # We'll try to set TARGET_HIGH_FPS later with this resolution.

    # If we found a candidate resolution for TARGET_HIGH_FPS
    if highest_res_at_target_fps[0] > 0:
        for mode_info in sensor_modes:
            if mode_info["size"] == highest_res_at_target_fps:
                best_mode = mode_info
                # We will attempt TARGET_HIGH_FPS with this mode
                logger.info(f"Selected mode for high FPS ({TARGET_HIGH_FPS} FPS target): {best_mode} with resolution {best_mode['size']}")
                return best_mode, TARGET_HIGH_FPS # Return mode and desired FPS

    # Fallback: if no mode seems good for TARGET_HIGH_FPS, pick mode with max pixel throughput
    # (or just max resolution if FPS info is unreliable from sensor_modes)
    logger.info(f"Could not definitively pick a mode for {TARGET_HIGH_FPS} FPS. Falling back to max resolution mode.")
    for mode_info in sensor_modes:
        width, height = mode_info["size"]
        # Estimate FPS - this is tricky as sensor_modes might not give a clear FPS range for each mode.
        # We'll just pick the largest resolution and let Picamera2 determine max possible FPS.
        if width * height > max_pixel_throughput:
            max_pixel_throughput = width * height
            best_mode = mode_info

    if best_mode:
        logger.info(f"Selected mode based on max resolution: {best_mode}")
        # For this fallback, we don't know the FPS yet, Picamera2 will set it.
        # We can request a high one and see what we get.
        return best_mode, None # FPS will be determined by camera.configure
    else:
        logger.error("Could not select any camera mode.")
        return None, None


# def start_gstreamer_pipeline(input_fd, width, height, fps, video_format_picam):
#     """
#     Starts the GStreamer pipeline in a subprocess.
#     input_fd: File descriptor from which Picamera2 writes raw frames.
#     """
#     global gst_process

#     # Convert Picamera2 format to GStreamer format string
#     # Common formats: 'YUV420', 'RGB888', 'BGR888', 'XRGB8888'
#     # GStreamer equivalents: I420, RGB, BGR, XRGB/BGRx
#     if video_format_picam == 'YUV420':
#         gst_format = 'I420'
#     elif video_format_picam == 'RGB888':
#         gst_format = 'RGB'
#     elif video_format_picam == 'BGR888': # Common from Picamera2
#         gst_format = 'BGR'
#     elif video_format_picam == 'XRGB8888':
#         gst_format = 'XRGB' # or 'BGRx' depending on actual packing
#     else:
#         logger.warning(f"Unsupported Picamera2 format {video_format_picam} for GStreamer. Defaulting to BGR. Check GStreamer errors.")
#         gst_format = 'BGR' # A common default

#     # Ensure FPS is a valid number for GStreamer
#     framerate_str = f"{int(fps)}/1" if fps and fps > 0 else "30/1" # Default to 30 if unknown

#     # Construct GStreamer pipeline
#     # Using fdsrc to read from the file descriptor Picamera2 is writing to.
#     # The caps for fdsrc are crucial.
#     pipeline = [
#         "gst-launch-1.0",
#         "-v", # Verbose for debugging
#         "fdsrc", f"fd={input_fd}", "do-timestamp=true",
#         "!", f"video/x-raw,format={gst_format},width={width},height={height},framerate={framerate_str}",
#         "!", "videoconvert", # Converts to a format suitable for the encoder if needed
#         "!", GST_ENCODER,
#             f"bitrate={GST_BITRATE_KBPS * 1000}", # Bitrate in bps for omx, maybe 'target-bitrate' for v4l2
#             # For v4l2h264enc, quality can be set via extra-controls and qp values
#             # Example: 'extra-controls="controls,h264_minimum_qp_value=15,h264_maximum_qp_value=25,video_bitrate_mode=0;"' (VBR QP)
#             # For omxh264enc: 'control-rate=variable', 'target-bitrate={GST_BITRATE_KBPS * 1000}'
#             # If using qp-mode for omxh264enc: 'qp-mode=cqp' 'initial-qp=20' 'min-qp=15' 'max-qp=28'
#         "!", "video/x-h264,profile=high", # Ensure H.264 high profile for quality
#         "!", "h264parse", "config-interval=-1", # Send SPS/PPS with every IDR frame
#         "!", "rtph264pay", "pt=96", "mtu=1400", # MTU to avoid IP fragmentation
#         "!", "udpsink", f"host={GST_TARGET_HOST}", f"port={GST_TARGET_PORT}", "sync=false" # "async=false" or "sync=false"
#     ]

#     # Add encoder-specific options if needed (example for v4l2h264enc quality)
#     if GST_ENCODER == "v4l2h264enc":
#         pipeline.insert(pipeline.index(GST_ENCODER) + 1, 'extra-controls="controls,h264_level=12,h264_profile=4,frame_level_rate_control_enable=0,video_bitrate_mode=0,h264_i_frame_period=60,h264_minimum_qp_value=18,h264_maximum_qp_value=28;"') # Constant QP mode (approx)

#     logger.info(f"Starting GStreamer pipeline: {' '.join(pipeline)}")

#     try:
#         # The input_fd must be passed to the child process correctly.
#         # `pass_fds` is not directly available in subprocess.Popen.
#         # However, standard file descriptors (0, 1, 2) are inherited.
#         # For other FDs, they are typically inherited unless CLOEXEC is set.
#         # Picamera2's FileOutput should provide an FD that is inheritable.
#         gst_process = subprocess.Popen(pipeline, pass_fds=(input_fd,)) #stdin=subprocess.PIPE) if feeding directly
#         logger.info(f"GStreamer process started with PID: {gst_process.pid}")
#     except Exception as e:
#         logger.error(f"Failed to start GStreamer: {e}")
#         gst_process = None
#     return gst_process

def start_gstreamer_pipeline(input_fd, width, height, fps, video_format_picam):
    """
    Starts the GStreamer pipeline in a subprocess.
    input_fd: File descriptor from which Picamera2 writes raw frames.
    """
    global gst_process

    # Determine GStreamer format string from Picamera2's output format
    if video_format_picam == 'YUV420':
        gst_picam2_output_format = 'I420' # I420 is the GStreamer equivalent of YUV420 planar
    elif video_format_picam == 'BGR888':
        gst_picam2_output_format = 'BGR'
    elif video_format_picam == 'RGB888':
        gst_picam2_output_format = 'RGB'
    elif video_format_picam == 'XRGB8888':
        gst_picam2_output_format = 'XRGB' # Or BGRx
    else:
        logger.warning(f"Unsupported Picamera2 format {video_format_picam} for GStreamer. Defaulting to BGR.")
        gst_picam2_output_format = 'BGR'

    framerate_str = f"{int(fps)}/1" if fps and fps > 0 else "30/1"
    target_bitrate_bps = GST_BITRATE_KBPS * 1000

    # Define capabilities strings for clarity
    caps_from_fdsrc = f"video/x-raw,format={gst_picam2_output_format},width={width},height={height},framerate={framerate_str}"
    
    # NV12 is often a preferred input format for v4l2h264enc for hardware efficiency
    caps_for_encoder_input = f"video/x-raw,format=NV12,width={width},height={height},framerate={framerate_str}"
    
    # More specific H.264 capabilities after encoding
    # Profile 'high' corresponds to h264_profile=4 in extra-controls.
    # Level '4.2' corresponds to h264_level=12 in extra-controls.
    # caps_after_encoder = (
    #     f"video/x-h264,"
    #     f"profile=high,"
    #     f"level=(string)4.2," # GStreamer often uses string representation for levels
    #     f"width={width},"
    #     f"height={height},"
    #     f"framerate={framerate_str},"
    #     f"stream-format=byte-stream," # Common for raw H.264 streams
    #     f"alignment=au"              # Access Unit alignment
    # )
    caps_after_encoder = "video/x-h264,stream-format=byte-stream,alignment=au"

    pipeline_elements = [
        "gst-launch-1.0", "-v",  # Enable verbose GStreamer logging
        "fdsrc", f"fd={input_fd}", "do-timestamp=true",
        "!", caps_from_fdsrc,
        "!", "videoconvert",  # Converts format if needed (e.g., I420 to NV12)
        "!", caps_for_encoder_input, # Explicitly set the format for the encoder
        "!", GST_ENCODER      # e.g., "v4l2h264enc"
    ]

    # Add encoder-specific controls (this part was corrected in the previous step)
    if GST_ENCODER == "v4l2h264enc":
        extra_controls_str = (
            f'extra-controls="controls,'
            f'video_bitrate_mode=1,'       # 1 = Constant Bitrate (CBR)
            f'video_bitrate={target_bitrate_bps},'
            f'h264_profile=4,'           # Corresponds to 'high' (GST_VIDEO_H264_PROFILE_HIGH)
            f'h264_level=12,'             # Corresponds to '4.2' (GST_VIDEO_H264_LEVEL_4_2)
            f'h264_i_frame_period=60'    # Keyframe interval (GOP size)
            f'"'
        )
        pipeline_elements.append(extra_controls_str)

    # Add the rest of the pipeline elements
    pipeline_elements.extend([
        "!", caps_after_encoder,
        "!", "h264parse", "config-interval=-1", # Ensure SPS/PPS are extracted
        "!", "rtph264pay", "pt=96", "mtu=1400", "config-interval=1", # Send SPS/PPS with keyframes for RTP
        "!", "udpsink", f"host={GST_TARGET_HOST}", f"port={GST_TARGET_PORT}", "sync=false"
    ])

    logger.info(f"Starting GStreamer pipeline: {' '.join(pipeline_elements)}")

    try:
        # Make sure Popen gets the list of arguments directly
        gst_process = subprocess.Popen(pipeline_elements, pass_fds=(input_fd,))
        logger.info(f"GStreamer process started with PID: {gst_process.pid}")
    except Exception as e:
        logger.error(f"Failed to start GStreamer: {e}")
        gst_process = None
    return gst_process


def main():
    global gst_process
    picam2 = None
    # fd_output = None # FileOutput instance is not used in the new loop
    write_file_obj = None # This will be our pipe's write end
    read_fd, write_fd_int = -1, -1

    def signal_handler(sig, frame):
        logger.info("Shutdown signal received. Cleaning up...")
        # Make sure picam2.stop() is called before closing write_file_obj if capture loop is active
        # The capture loop below will handle stopping picam2 on its own exit.
        # Here, we ensure gst_process and file descriptors are handled.

        if gst_process and gst_process.poll() is None:
            logger.info(f"Terminating GStreamer process {gst_process.pid}...")
            gst_process.terminate()
            try:
                gst_process.wait(timeout=5)
                logger.info("GStreamer process terminated.")
            except subprocess.TimeoutExpired:
                logger.warning("GStreamer process did not terminate in time, killing.")
                gst_process.kill()
                logger.info("GStreamer process killed.")

        # Picamera2 object should be stopped and closed by the main loop's finally block
        # write_file_obj will also be closed there.
        if read_fd != -1:
            try:
                os.close(read_fd)
                logger.info(f"Closed read_fd: {read_fd}")
            except OSError as e:
                logger.error(f"Error closing read_fd: {e}")
        
        # The write_file_obj is critical and should be closed by the main try/finally
        # to ensure the GStreamer pipeline's fdsrc gets an EOF.
        # If the signal comes while the capture loop is running, the loop's finally block should handle picam2.stop() and write_file_obj.close().
        # This signal handler is more of a fallback if the main loop is stuck elsewhere.
        # To be safe, attempt to close write_file_obj if it exists and is open.
        global capture_running_flag # Need a flag to coordinate with capture loop
        capture_running_flag = False # Signal the capture loop to stop

        # Delay slightly to allow capture loop to exit and close resources
        time.sleep(0.5) 

        if write_file_obj and not write_file_obj.closed:
            try:
                write_file_obj.close()
                logger.info(f"Closed write_file_obj in signal handler.")
            except Exception as e:
                logger.error(f"Error closing write_file_obj in signal handler: {e}")

        if picam2 and picam2.started: # If picam2 still thinks it's started
             try:
                 picam2.stop()
                 logger.info("Picamera2 explicitly stopped in signal handler.")
             except Exception as e:
                 logger.error(f"Error stopping picam2 in signal handler: {e}")
             finally:
                if picam2: # Check again as stop() might have side effects
                    picam2.close()
                    logger.info("Picamera2 closed in signal handler.")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    global capture_running_flag
    capture_running_flag = True

    try:
        logger.info("Initializing Picamera2...")
        picam2 = Picamera2()

        selected_mode_info, requested_fps = select_optimal_camera_mode(picam2)
        if not selected_mode_info:
            logger.error("Could not determine optimal camera mode. Exiting.")
            return

        capture_format = "YUV420" # Changed to YUV420 for better memory in previous step
        main_stream_config = {"size": selected_mode_info["size"], "format": capture_format}
        
        controls = {}
        if requested_fps:
            controls["FrameRate"] = float(requested_fps)

        video_config = picam2.create_video_configuration(
            main=main_stream_config,
            controls=controls,
            raw=selected_mode_info,
            queue=True, # Enable queueing for smoother manual capture
            buffer_count=6 # Optional: Adjust buffer count if needed (default is often 4 or 6)
        )
        logger.info(f"Configuring Picamera2 with: {video_config}")
        picam2.configure(video_config)

        actual_config = picam2.camera_configuration()
        actual_main_stream = actual_config['main']
        final_width = actual_main_stream['size'][0]
        final_height = actual_main_stream['size'][1]
        final_format = actual_main_stream['format']
        actual_fps_from_controls = actual_config['controls'].get('FrameRate', TARGET_HIGH_FPS if requested_fps else 30)
        logger.info(f"Picamera2 configured. Output stream: {final_width}x{final_height} Format: {final_format} @ ~{actual_fps_from_controls} FPS")

        read_fd, write_fd_int = os.pipe()
        logger.info(f"Created pipe: read_fd={read_fd}, write_fd_int={write_fd_int}")
        write_file_obj = os.fdopen(write_fd_int, 'wb')
        logger.info(f"Wrapped write_fd_int into file object: {write_file_obj}")

        gst_process = start_gstreamer_pipeline(read_fd, final_width, final_height, actual_fps_from_controls, final_format)
        if not gst_process or gst_process.poll() is not None:
            raise RuntimeError("GStreamer process failed to start or exited prematurely.")

        logger.info("Starting Picamera2 for manual frame capture...")
        picam2.start() # Start the camera, but not "recording" in the old sense

        logger.info(f"🚀 Streaming active! Target: udp://{GST_TARGET_HOST}:{GST_TARGET_PORT}")
        logger.info("Press Ctrl+C to stop.")

        # Manual frame capture loop
        while capture_running_flag:
            # This is one way to get the buffer data for the main stream.
            # capture_buffer() is simpler if you only have one stream you care about.
            # It returns the data for the named stream.
            buffer_data = picam2.capture_buffer("main")
            # If capture_buffer returns None, it could mean the stream ended or there was an issue.
            if buffer_data is None:
                logger.warning("capture_buffer returned None, stopping loop.")
                break
            
            try:
                write_file_obj.write(buffer_data)
                write_file_obj.flush() # Ensure data is sent to the pipe promptly
            except BrokenPipeError:
                logger.warning("Broken pipe writing to GStreamer. GStreamer likely exited.")
                capture_running_flag = False # Stop this loop
                break
            except Exception as e:
                logger.error(f"Error writing to pipe: {e}")
                capture_running_flag = False # Stop this loop
                break

            if gst_process.poll() is not None:
                logger.error(f"GStreamer process exited unexpectedly during capture with code {gst_process.returncode}.")
                capture_running_flag = False # Stop this loop
                break
        
        logger.info("Exited capture loop.")

    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}", exc_info=True)
    finally:
        logger.info("Performing final cleanup...")
        capture_running_flag = False # Ensure loop condition is false

        if picam2:
            if picam2.started: # Check if it was started before trying to stop
                try:
                    logger.info("Stopping Picamera2...")
                    picam2.stop()
                    logger.info("Picamera2 stopped.")
                except Exception as e:
                    logger.error(f"Error stopping Picamera2: {e}")
            try:
                logger.info("Closing Picamera2...")
                picam2.close()
                logger.info("Picamera2 closed.")
            except Exception as e:
                logger.error(f"Error closing Picamera2: {e}")


        if write_file_obj and not write_file_obj.closed:
            try:
                logger.info("Closing write_file_obj (pipe to GStreamer)...")
                write_file_obj.close() # This sends EOF to GStreamer's fdsrc
                logger.info("write_file_obj closed.")
            except Exception as e:
                logger.error(f"Error closing write_file_obj: {e}")
        
        # GStreamer process termination is handled by the signal_handler
        # or if it exits on its own, the loop breaks.
        # We can add a check here too if not shutting down via signal.
        if gst_process and gst_process.poll() is None:
            logger.info(f"Main finally: GStreamer process {gst_process.pid} still running, terminating...")
            gst_process.terminate()
            try:
                gst_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                gst_process.kill()
            logger.info("GStreamer process dealt with in main finally.")
        
        # read_fd for GStreamer is trickier. GStreamer takes ownership.
        # Closing it here might be redundant if GStreamer has it, or problematic.
        # The signal handler's attempt to close read_fd is a reasonable fallback.
        # However, if this `finally` block is reached due to normal loop completion (not signal),
        # GStreamer might still be running if it wasn't the cause of the loop exit.

        logger.info("Cleanup complete.")

    # except Exception as e:
    #     logger.critical(f"Critical error in main loop: {e}", exc_info=True)
    # finally:
    #     signal_handler(signal.SIGTERM, None) # Trigger cleanup

if __name__ == '__main__':
    main()