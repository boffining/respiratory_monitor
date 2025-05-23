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
TARGET_HIGH_FPS = 60  # Target FPS for camera mode selection
GST_ENCODER = "v4l2h264enc"  # Hardware encoder for Raspberry Pi
GST_BITRATE_KBPS = 8000     # Target bitrate (e.g., 8 Mbps). Adjust as needed.
GST_TARGET_HOST = "192.169.50.173"  # <<< IMPORTANT: Change to your VLC client's IP address!
GST_TARGET_PORT = 5004
DEFAULT_CAPTURE_FORMAT = "YUV420"  # Picamera2 output format. Corresponds to I420 in GStreamer.

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MaxPerfStreamer")

# --- Global Variables for Graceful Shutdown ---
gst_process = None
capture_running_flag = True  # For controlling the main capture loop
python_read_fd = -1          # Parent's copy of the read end of the pipe, for GStreamer
python_write_file_obj = None # File object for the write end of the pipe, for Picamera2
picam2_instance = None       # To allow signal handler to access Picamera2 for shutdown

def select_optimal_camera_mode(picam2_select):
    """
    Selects a camera mode aiming for high resolution at TARGET_HIGH_FPS,
    or falls back to highest resolution if high FPS isn't available.
    """
    sensor_modes = picam2_select.sensor_modes
    if not sensor_modes:
        logger.error("No sensor modes found!")
        return None, None

    logger.info("Available sensor modes:")
    for i, mode_info in enumerate(sensor_modes):
        # Log only a subset of info if too verbose, e.g., mode_info['size'], mode_info['format']
        logger.info(f"  Mode {i}: {mode_info.get('size')}, Format: {mode_info.get('format', 'N/A')}, BitDepth: {mode_info.get('bit_depth')}")


    candidate_modes_at_target_fps = []
    for mode_info in sensor_modes:
        # This is a heuristic. A true check involves trying to configure the mode
        # with the target FPS and seeing what Picamera2/libcamera negotiates.
        # We'll pick modes that are at least 1280 width as candidates for high FPS.
        if mode_info["size"][0] >= 1280: # e.g. 720p or 1080p
            candidate_modes_at_target_fps.append(mode_info)

    if candidate_modes_at_target_fps:
        # Among candidates, pick the one with the highest resolution
        # Sort by resolution (area) descending, then by other factors if needed
        candidate_modes_at_target_fps.sort(key=lambda m: m["size"][0] * m["size"][1], reverse=True)
        best_mode_at_target_fps = candidate_modes_at_target_fps[0] # Highest res among these
        logger.info(f"Selected mode for ~{TARGET_HIGH_FPS} FPS target: {best_mode_at_target_fps['size']} (Format: {best_mode_at_target_fps.get('format', 'N/A')})")
        return best_mode_at_target_fps, TARGET_HIGH_FPS

    # Fallback: if no clear high-FPS high-res mode, pick the mode with the largest resolution
    logger.info(f"Could not definitively pick a mode for {TARGET_HIGH_FPS} FPS among common high-res modes. Falling back to max resolution mode.")
    if sensor_modes:
        best_mode_overall = max(sensor_modes, key=lambda m: m["size"][0] * m["size"][1])
        logger.info(f"Selected mode based on max resolution: {best_mode_overall['size']} (Format: {best_mode_overall.get('format', 'N/A')}), will request {TARGET_HIGH_FPS} FPS.")
        return best_mode_overall, TARGET_HIGH_FPS
    
    logger.error("Could not select any camera mode.")
    return None, None

def start_gstreamer_pipeline(input_fd_gst, width, height, fps, picam2_format_str_in_script):
    global gst_process

    # Determine GStreamer format string from Picamera2's output format
    if picam2_format_str_in_script == 'YUV420':
        gst_source_format = 'I420'  # I420 is the GStreamer equivalent of YUV420 planar
    elif picam2_format_str_in_script == 'BGR888':
        gst_source_format = 'BGR'
    elif picam2_format_str_in_script == 'RGB888':
        gst_source_format = 'RGB'
    elif picam2_format_str_in_script == 'XRGB8888':
        gst_source_format = 'XRGB'
    else:
        logger.warning(f"Unsupported Picamera2 format {picam2_format_str_in_script} for GStreamer. Defaulting to BGR. This might cause issues.")
        gst_source_format = 'BGR'

    framerate_str_gst = f"{int(fps)}/1" if fps and fps > 0 else "30/1"
    target_bitrate_bps_gst = GST_BITRATE_KBPS * 1000

    caps_from_fdsrc_gst = f"video/x-raw,format={gst_source_format},width={width},height={height},framerate={framerate_str_gst}"
    caps_for_encoder_input_gst = f"video/x-raw,format=NV12,width={width},height={height},framerate={framerate_str_gst}"
    caps_after_encoder_gst = "video/x-h264"  # Drastically simplified, let h264parse figure out details

    pipeline_elements = [
        "gst-launch-1.0", "-v",  # Verbose GStreamer logging
        "fdsrc", f"fd={input_fd_gst}", # Removed do-timestamp=true
        "!", caps_from_fdsrc_gst,
        "!", "videoconvert",
        "!", "queue",  # Added queue for buffering between videoconvert and encoder input caps
        "!", caps_for_encoder_input_gst,
        "!", GST_ENCODER
    ]

    if GST_ENCODER == "v4l2h264enc":
        extra_controls = (
            f'extra-controls="controls,'
            f'video_bitrate_mode=1,'        # 1 = Constant Bitrate (CBR)
            f'video_bitrate={target_bitrate_bps_gst},'
            f'h264_profile=4,'            # Corresponds to 'high' (GST_VIDEO_H264_PROFILE_HIGH)
            f'h264_level=12,'              # Corresponds to '4.2' (GST_VIDEO_H264_LEVEL_4_2)
            f'h264_i_frame_period=60'     # Keyframe interval (GOP size)
            f'"'
        )
        pipeline_elements.append(extra_controls)

    pipeline_elements.extend([
        "!", caps_after_encoder_gst,
        "!", "h264parse", "config-interval=-1",  # Ensure SPS/PPS are extracted
        "!", "queue",  # Added queue before RTP payloader
        "!", "rtph264pay", "pt=96", "mtu=1400", "config-interval=1",  # Send SPS/PPS with keyframes
        "!", "udpsink", f"host={GST_TARGET_HOST}", f"port={GST_TARGET_PORT}", "sync=false"
    ])

    logger.info(f"Starting GStreamer pipeline: {' '.join(pipeline_elements)}")

    try:
        gst_process = subprocess.Popen(pipeline_elements, pass_fds=(input_fd_gst,))
        logger.info(f"GStreamer process started with PID: {gst_process.pid}")
    except Exception as e:
        logger.error(f"Failed to start GStreamer: {e}")
        gst_process = None
    return gst_process

def signal_handler_main(sig, frame):
    global capture_running_flag, gst_process, python_read_fd, python_write_file_obj, picam2_instance
    logger.info(f"Shutdown signal {signal.Signals(sig).name} received. Cleaning up...")
    capture_running_flag = False  # Signal the main loop to stop

    # Brief pause to allow the main loop's finally block to try cleaning up first
    time.sleep(0.5)

    if gst_process and gst_process.poll() is None:
        logger.info(f"Signal handler: Terminating GStreamer process {gst_process.pid}...")
        gst_process.terminate()
        try:
            gst_process.wait(timeout=1) # Short wait
        except subprocess.TimeoutExpired:
            logger.warning("Signal handler: GStreamer process did not terminate in time, killing.")
            gst_process.kill()
    
    # These resources should ideally be cleaned by main's finally block.
    # This is a fallback.
    if python_write_file_obj and not python_write_file_obj.closed:
        logger.warning("Signal handler: python_write_file_obj still open, attempting close.")
        try: python_write_file_obj.close()
        except Exception: pass

    if picam2_instance:
        logger.warning("Signal handler: Picamera2 instance might still be active, attempting stop/close.")
        try:
            if picam2_instance.started: picam2_instance.stop()
        except Exception: pass
        try: picam2_instance.close()
        except Exception: pass
            
    if python_read_fd != -1: # If parent's copy of read FD was not marked closed
        logger.warning(f"Signal handler: Parent's read_fd ({python_read_fd}) seems open, attempting close.")
        try: os.close(python_read_fd)
        except OSError: pass
            
    sys.exit(0)

def main():
    global capture_running_flag, gst_process, python_read_fd, python_write_file_obj, picam2_instance

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler_main)
    signal.signal(signal.SIGTERM, signal_handler_main)

    selected_capture_format_from_config = DEFAULT_CAPTURE_FORMAT

    try:
        logger.info("Initializing Picamera2...")
        picam2_instance = Picamera2()

        selected_mode_info, requested_fps = select_optimal_camera_mode(picam2_instance)
        if not selected_mode_info:
            logger.error("Could not determine optimal camera mode. Exiting.")
            return

        main_stream_config = {"size": selected_mode_info["size"], "format": selected_capture_format_from_config}
        controls_for_picam2 = {}
        if requested_fps:
            controls_for_picam2["FrameRate"] = float(requested_fps)
        # You could add other controls here, e.g., for exposure, AWB if needed.

        video_config = picam2_instance.create_video_configuration(
            main=main_stream_config,
            controls=controls_for_picam2,
            raw=selected_mode_info, # Use the selected sensor mode to guide configuration
            queue=True,      # Enable Picamera2's internal queueing for manual capture
            buffer_count=6   # Number of buffers in Picamera2's queue
        )
        logger.info(f"Configuring Picamera2 with: {video_config}")
        picam2_instance.configure(video_config)

        actual_camera_config = picam2_instance.camera_configuration()
        actual_main_stream_config = actual_camera_config['main']
        final_width = actual_main_stream_config['size'][0]
        final_height = actual_main_stream_config['size'][1]
        # This is the format Picamera2 will *actually* output to capture_buffer()
        final_format_from_picam2 = actual_main_stream_config['format']
        actual_fps = actual_camera_config['controls'].get('FrameRate', TARGET_HIGH_FPS if requested_fps else 30)
        
        expected_buffer_size = 0
        if final_format_from_picam2 == 'YUV420':
            expected_buffer_size = int(final_width * final_height * 1.5)
        elif final_format_from_picam2 in ['BGR888', 'RGB888']:
            expected_buffer_size = final_width * final_height * 3
        elif final_format_from_picam2 == 'XRGB8888': # Might be output if BGR888 or RGB888 selected
            expected_buffer_size = final_width * final_height * 4
        else: # Add other formats if Picamera2 might output them, e.g. MJPEG, P010 etc.
            logger.warning(f"Cannot accurately determine expected buffer size for actual Picamera2 format '{final_format_from_picam2}'. This could cause fdsrc errors if GStreamer caps mismatch.")

        logger.info(f"Picamera2 configured. Actual output stream: {final_width}x{final_height} Format: {final_format_from_picam2} @ ~{actual_fps} FPS. Expected raw buffer size: {expected_buffer_size or 'Unknown'} bytes.")

        # Create the pipe: python_read_fd for GStreamer, write_fd_int for Python's python_write_file_obj
        fd_for_gst_read, write_fd_int = os.pipe()
        python_read_fd = fd_for_gst_read # Store for potential cleanup, though closed by main logic

        python_write_file_obj = os.fdopen(write_fd_int, 'wb')
        logger.info(f"Created pipe: GStreamer reads from fd {fd_for_gst_read}, Python writes to wrapped fd {write_fd_int}")

        # Pass the actual format from Picamera2 to GStreamer setup
        gst_process = start_gstreamer_pipeline(fd_for_gst_read, final_width, final_height, actual_fps, final_format_from_picam2)

        if gst_process and gst_process.poll() is None: # GStreamer child process started successfully
            logger.info(f"GStreamer process launched. Closing parent's copy of fd_for_gst_read: {fd_for_gst_read}")
            os.close(fd_for_gst_read)
            python_read_fd = -1 # Mark as closed by parent, GStreamer has its own copy
        else:
            # GStreamer failed to start or exited immediately, clean up pipe FDs
            if python_read_fd != -1: os.close(python_read_fd); python_read_fd = -1
            if python_write_file_obj and not python_write_file_obj.closed: python_write_file_obj.close()
            raise RuntimeError("GStreamer process failed to launch or exited immediately.")

        logger.info("Starting Picamera2 capture loop...")
        picam2_instance.start() # Start delivering frames

        logger.info(f"🚀 Streaming active! Target: udp://{GST_TARGET_HOST}:{GST_TARGET_PORT}")
        logger.info("Press Ctrl+C to stop.")

        frame_count = 0
        while capture_running_flag:
            buffer_data = picam2_instance.capture_buffer("main")
            if buffer_data is None:
                logger.warning("capture_buffer returned None from Picamera2, stopping capture loop.")
                capture_running_flag = False; break
            
            if expected_buffer_size > 0 and len(buffer_data) != expected_buffer_size:
                logger.error(f"CRITICAL: Buffer size mismatch from Picamera2 on frame {frame_count}! Expected {expected_buffer_size}, got {len(buffer_data)}. Stopping.")
                capture_running_flag = False; break
            
            try:
                python_write_file_obj.write(buffer_data)
                python_write_file_obj.flush() # Ensure data is sent to the pipe promptly
                frame_count += 1
            except BrokenPipeError:
                logger.warning(f"Broken pipe writing to GStreamer (frame {frame_count}). GStreamer likely exited.")
                capture_running_flag = False; break
            except Exception as e:
                logger.error(f"Error writing to pipe (frame {frame_count}): {e}")
                capture_running_flag = False; break

            if frame_count % (int(actual_fps) * 5) == 0: # Log every 5 seconds approx
                 logger.info(f"Streamed {frame_count} frames...")

            if gst_process.poll() is not None:
                logger.error(f"GStreamer process exited unexpectedly during capture (frame {frame_count}) with code {gst_process.returncode}.")
                capture_running_flag = False; break
        
        logger.info(f"Exited capture loop after {frame_count} frames.")

    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}", exc_info=True)
    finally:
        logger.info("Performing final cleanup in main()...")
        capture_running_flag = False # Ensure loop condition is false for any lingering checks

        if picam2_instance:
            if picam2_instance.started:
                try: logger.info("Stopping Picamera2 (main finally)..."); picam2_instance.stop()
                except Exception as e: logger.error(f"Error stopping Picamera2 (main finally): {e}")
            try: logger.info("Closing Picamera2 (main finally)..."); picam2_instance.close()
            except Exception as e: logger.error(f"Error closing Picamera2 (main finally): {e}")
        picam2_instance = None # Clear global

        if python_write_file_obj and not python_write_file_obj.closed:
            try: logger.info("Closing write_file_obj (main finally)..."); python_write_file_obj.close()
            except Exception as e: logger.error(f"Error closing write_file_obj (main finally): {e}")
        python_write_file_obj = None

        if gst_process and gst_process.poll() is None:
            logger.info(f"Main finally: GStreamer process {gst_process.pid} still running, terminating...")
            gst_process.terminate()
            try: gst_process.wait(timeout=1)
            except subprocess.TimeoutExpired: gst_process.kill()
        gst_process = None
        
        if python_read_fd != -1: # Should be -1 if GStreamer started, but as a fallback
            logger.warning(f"Main finally: Parent's read_fd ({python_read_fd}) still marked as open, attempting close.")
            try: os.close(python_read_fd)
            except OSError as e: logger.error(f"Error closing python_read_fd in main finally: {e}")
        python_read_fd = -1
        
        logger.info("Main cleanup complete.")

if __name__ == '__main__':
    # Ensure GST_TARGET_HOST is set to something other than localhost if not intended for local testing
    if GST_TARGET_HOST == "127.0.0.1":
        logger.warning("GST_TARGET_HOST is 127.0.0.1. Stream will only be viewable on this Raspberry Pi.")
    elif not GST_TARGET_HOST or len(GST_TARGET_HOST.split('.')) != 4 : # Basic IP check
         logger.error(f"GST_TARGET_HOST ('{GST_TARGET_HOST}') does not look like a valid IP address. Please configure it.")
         sys.exit(1)
    main()