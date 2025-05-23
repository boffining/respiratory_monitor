#!/usr/bin/python3
import time
import logging
import subprocess
import signal
import sys
import os
from picamera2 import Picamera2
# Removed FileOutput and Quality as they are not used in the current approach

# --- Configuration ---
TARGET_HIGH_FPS = 60
GST_ENCODER = "v4l2h264enc"
GST_BITRATE_KBPS = 8000
GST_TARGET_HOST = "192.169.50.173"  # <<< CHANGE THIS TO YOUR VLC CLIENT'S IP!
GST_TARGET_PORT = 5004
DEFAULT_CAPTURE_FORMAT = "YUV420" # Request this from Picamera2

# --- Logging Setup ---
# (Same as before)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MaxPerfStreamer")

# --- Global Variables ---
# (Same as before)
gst_process = None
capture_running_flag = True
python_read_fd = -1
python_write_file_obj = None
picam2_instance = None


def select_optimal_camera_mode(picam2_select):
    # (Same as before - ensure it returns selected_mode_info which has 'size')
    sensor_modes = picam2_select.sensor_modes
    if not sensor_modes:
        logger.error("No sensor modes found!")
        return None, None

    logger.info("Available sensor modes (showing size, format, bit_depth):")
    for i, mode_info in enumerate(sensor_modes):
        logger.info(f"  Mode {i}: {mode_info.get('size')}, Format: {mode_info.get('format', 'N/A')}, BitDepth: {mode_info.get('bit_depth')}")

    candidate_modes_at_target_fps = []
    for mode_info in sensor_modes:
        if mode_info["size"][0] >= 1280:
            candidate_modes_at_target_fps.append(mode_info)

    if candidate_modes_at_target_fps:
        candidate_modes_at_target_fps.sort(key=lambda m: m["size"][0] * m["size"][1], reverse=True)
        best_mode_at_target_fps = candidate_modes_at_target_fps[0]
        logger.info(f"Selected mode for ~{TARGET_HIGH_FPS} FPS target: {best_mode_at_target_fps['size']} (Format: {best_mode_at_target_fps.get('format', 'N/A')})")
        return best_mode_at_target_fps, TARGET_HIGH_FPS

    logger.info(f"Could not definitively pick a mode for {TARGET_HIGH_FPS} FPS among common high-res modes. Falling back to max resolution mode.")
    if sensor_modes:
        best_mode_overall = max(sensor_modes, key=lambda m: m["size"][0] * m["size"][1])
        logger.info(f"Selected mode based on max resolution: {best_mode_overall['size']} (Format: {best_mode_overall.get('format', 'N/A')}), will request {TARGET_HIGH_FPS} FPS.")
        return best_mode_overall, TARGET_HIGH_FPS
    
    logger.error("Could not select any camera mode.")
    return None, None

# MODIFIED FUNCTION SIGNATURE TO ACCEPT actual_frame_buffer_size
def start_gstreamer_pipeline(input_fd_gst, width, height, fps, picam2_format_str_in_script, actual_frame_buffer_size):
    global gst_process

    if picam2_format_str_in_script == 'YUV420':
        gst_source_format = 'I420'
    elif picam2_format_str_in_script == 'BGR888':
        gst_source_format = 'BGR'
    elif picam2_format_str_in_script == 'RGB888':
        gst_source_format = 'RGB'
    elif picam2_format_str_in_script == 'XRGB8888':
        gst_source_format = 'XRGB'
    else:
        logger.warning(f"Unsupported Picamera2 format {picam2_format_str_in_script} for GStreamer. Defaulting to BGR.")
        gst_source_format = 'BGR'

    framerate_str_gst = f"{int(fps)}/1" if fps and fps > 0 else "30/1"
    target_bitrate_bps_gst = GST_BITRATE_KBPS * 1000

    # This caps string describes the *active* video data within the buffer
    caps_from_fdsrc_gst = f"video/x-raw,format={gst_source_format},width={width},height={height},framerate={framerate_str_gst}"
    # If stride information is available and GStreamer elements can use it, it would be added here:
    # e.g., ",pixel-aspect-ratio=1/1,interlace-mode=progressive,colorimetry=bt709"
    # For stride: ",stride={actual_stride_value_if_known}" (but GStreamer videoconvert usually handles this if input buffer is larger)

    caps_for_encoder_input_gst = f"video/x-raw,format=NV12,width={width},height={height},framerate={framerate_str_gst}"
    caps_after_encoder_gst = "video/x-h264"

    pipeline_elements = [
        "gst-launch-1.0", "-v",
        # --- MODIFICATION: Add blocksize to fdsrc ---
        "fdsrc", f"fd={input_fd_gst}", f"blocksize={actual_frame_buffer_size}",
        "!", caps_from_fdsrc_gst,
        "!", "videoconvert",
        "!", "queue",
        "!", caps_for_encoder_input_gst,
        "!", GST_ENCODER
    ]

    if GST_ENCODER == "v4l2h264enc":
        extra_controls = (
            f'extra-controls="controls,'
            f'video_bitrate_mode=1,'
            f'video_bitrate={target_bitrate_bps_gst},'
            f'h264_profile=4,'
            f'h264_level=12,'
            f'h264_i_frame_period=60'
            f'"'
        )
        pipeline_elements.append(extra_controls)

    pipeline_elements.extend([
        "!", caps_after_encoder_gst,
        "!", "h264parse", "config-interval=-1",
        "!", "queue",
        "!", "rtph264pay", "pt=96", "mtu=1400", "config-interval=1",
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

# (signal_handler_main remains the same as previous version)
def signal_handler_main(sig, frame):
    global capture_running_flag, gst_process, python_read_fd, python_write_file_obj, picam2_instance
    logger.info(f"Shutdown signal {signal.Signals(sig).name} received. Cleaning up...")
    capture_running_flag = False
    time.sleep(0.5)
    if gst_process and gst_process.poll() is None:
        logger.info(f"Signal handler: Terminating GStreamer process {gst_process.pid}...")
        gst_process.terminate()
        try: gst_process.wait(timeout=1)
        except subprocess.TimeoutExpired: logger.warning("Signal handler: GStreamer kill."); gst_process.kill()
    if python_write_file_obj and not python_write_file_obj.closed:
        logger.warning("Signal handler: python_write_file_obj open, closing.");_
        try: python_write_file_obj.close()
        except: pass
    if picam2_instance:
        logger.warning("Signal handler: Picamera2 active, stopping/closing.");_
        try:
            if picam2_instance.started: picam2_instance.stop()
        except: pass
        try: picam2_instance.close()
        except: pass
    if python_read_fd != -1:
        logger.warning(f"Signal handler: Parent's read_fd ({python_read_fd}) open, closing.");_
        try: os.close(python_read_fd)
        except OSError: pass
    sys.exit(0)

def main():
    global capture_running_flag, gst_process, python_read_fd, python_write_file_obj, picam2_instance

    signal.signal(signal.SIGINT, signal_handler_main)
    signal.signal(signal.SIGTERM, signal_handler_main)

    selected_capture_format_from_config = DEFAULT_CAPTURE_FORMAT

    try:
        logger.info("Initializing Picamera2...")
        picam2_instance = Picamera2()

        selected_mode_info, requested_fps = select_optimal_camera_mode(picam2_instance)
        if not selected_mode_info:
            logger.error("Could not determine optimal camera mode. Exiting."); return

        main_stream_config = {"size": selected_mode_info["size"], "format": selected_capture_format_from_config}
        controls_for_picam2 = {}
        if requested_fps: controls_for_picam2["FrameRate"] = float(requested_fps)

        video_config = picam2_instance.create_video_configuration(
            main=main_stream_config, controls=controls_for_picam2, raw=selected_mode_info,
            queue=True, buffer_count=6
        )
        logger.info(f"Requesting Picamera2 configuration: {video_config}")
        picam2_instance.configure(video_config)

        actual_camera_config = picam2_instance.camera_configuration()
        actual_main_stream_config = actual_camera_config['main']
        final_width = actual_main_stream_config['size'][0]
        final_height = actual_main_stream_config['size'][1]
        final_format_from_picam2 = actual_main_stream_config['format']
        actual_fps = actual_camera_config['controls'].get('FrameRate', TARGET_HIGH_FPS if requested_fps else 30)
        
        # --- MODIFICATION: Get actual buffer size (framesize) from Picamera2 config ---
        # 'framesize' should be the total size of the buffer including padding.
        actual_frame_buffer_size = actual_main_stream_config.get('framesize')
        if not actual_frame_buffer_size:
            # Fallback if 'framesize' is not present (older Picamera2 or unusual config)
            # This fallback is less reliable and might lead to the original error.
            logger.warning("'framesize' not found in Picamera2 stream config. Attempting calculation (less reliable).")
            if final_format_from_picam2 == 'YUV420':
                actual_frame_buffer_size = int(final_width * final_height * 1.5) # This is likely too small
            elif final_format_from_picam2 in ['BGR888', 'RGB888']:
                actual_frame_buffer_size = final_width * final_height * 3
            elif final_format_from_picam2 == 'XRGB8888':
                actual_frame_buffer_size = final_width * final_height * 4
            else:
                logger.error(f"Cannot determine buffer size for format '{final_format_from_picam2}'. Exiting.")
                return
            logger.warning(f"Using calculated buffer size: {actual_frame_buffer_size}. If errors persist, 'framesize' from Picamera2 config is preferred.")
        
        logger.info(f"Picamera2 configured. Actual output stream: {final_width}x{final_height} Format: {final_format_from_picam2} @ ~{actual_fps} FPS. Actual frame buffer size from Picamera2: {actual_frame_buffer_size} bytes.")

        fd_for_gst_read, write_fd_int = os.pipe()
        python_read_fd = fd_for_gst_read
        python_write_file_obj = os.fdopen(write_fd_int, 'wb')
        logger.info(f"Created pipe: GStreamer reads from fd {fd_for_gst_read}, Python writes to wrapped fd {write_fd_int}")

        # Pass actual_frame_buffer_size to GStreamer setup
        gst_process = start_gstreamer_pipeline(fd_for_gst_read, final_width, final_height, actual_fps, final_format_from_picam2, actual_frame_buffer_size)

        if gst_process and gst_process.poll() is None:
            logger.info(f"GStreamer process launched. Closing parent's copy of fd_for_gst_read: {fd_for_gst_read}")
            os.close(fd_for_gst_read)
            python_read_fd = -1
        else:
            if python_read_fd != -1: os.close(python_read_fd); python_read_fd = -1
            if python_write_file_obj and not python_write_file_obj.closed: python_write_file_obj.close()
            raise RuntimeError("GStreamer process failed to launch or exited immediately.")

        logger.info("Starting Picamera2 capture loop...")
        picam2_instance.start()

        logger.info(f"🚀 Streaming active! Target: udp://{GST_TARGET_HOST}:{GST_TARGET_PORT}")
        logger.info("Press Ctrl+C to stop.")

        frame_count = 0
        while capture_running_flag:
            buffer_data = picam2_instance.capture_buffer("main") # This returns the full buffer
            if buffer_data is None:
                logger.warning("capture_buffer returned None from Picamera2, stopping capture loop."); capture_running_flag = False; break
            
            # --- MODIFICATION: Compare len(buffer_data) with actual_frame_buffer_size from Picamera2 config ---
            if actual_frame_buffer_size > 0 and len(buffer_data) != actual_frame_buffer_size:
                logger.error(f"CRITICAL: Buffer size mismatch on frame {frame_count}! Picamera2 config said {actual_frame_buffer_size}, capture_buffer returned {len(buffer_data)}. Stopping.")
                capture_running_flag = False; break
            # The original "expected_buffer_size vs got" check is now redundant if actual_frame_buffer_size is used for fdsrc.
            # What we write (len(buffer_data)) MUST be what fdsrc expects via its blocksize.
            
            try:
                python_write_file_obj.write(buffer_data)
                python_write_file_obj.flush()
                frame_count += 1
            except BrokenPipeError:
                logger.warning(f"Broken pipe writing to GStreamer (frame {frame_count}). GStreamer likely exited."); capture_running_flag = False; break
            except Exception as e:
                logger.error(f"Error writing to pipe (frame {frame_count}): {e}"); capture_running_flag = False; break

            if frame_count > 0 and frame_count % (int(actual_fps or 30) * 5) == 0: # Log every 5 seconds approx
                 logger.info(f"Streamed {frame_count} frames...")

            if gst_process.poll() is not None:
                logger.error(f"GStreamer process exited unexpectedly during capture (frame {frame_count}) with code {gst_process.returncode}."); capture_running_flag = False; break
        
        logger.info(f"Exited capture loop after {frame_count} frames.")

    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}", exc_info=True)
    finally:
        # (Cleanup logic remains largely the same, ensure python_read_fd is handled based on its -1 status)
        logger.info("Performing final cleanup in main()...")
        capture_running_flag = False 

        if picam2_instance:
            if picam2_instance.started:
                try: logger.info("Stopping Picamera2 (main finally)..."); picam2_instance.stop()
                except Exception as e: logger.error(f"Error stopping Picamera2 (main finally): {e}")
            try: logger.info("Closing Picamera2 (main finally)..."); picam2_instance.close()
            except Exception as e: logger.error(f"Error closing Picamera2 (main finally): {e}")
        picam2_instance = None

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
        
        if python_read_fd != -1: 
            logger.warning(f"Main finally: Parent's read_fd ({python_read_fd}) seems open, attempting close.")
            try: os.close(python_read_fd)
            except OSError as e: logger.error(f"Error closing python_read_fd in main finally: {e}")
        python_read_fd = -1
        
        logger.info("Main cleanup complete.")

if __name__ == '__main__':
    if GST_TARGET_HOST == "127.0.0.1" or GST_TARGET_HOST == "localhost":
        logger.warning(f"GST_TARGET_HOST is '{GST_TARGET_HOST}'. Stream will only be viewable on this Raspberry Pi.")
    elif not GST_TARGET_HOST or len(GST_TARGET_HOST.split('.')) != 4 :
         logger.error(f"GST_TARGET_HOST ('{GST_TARGET_HOST}') does not look like a valid IP address. Please configure it.")
         sys.exit(1)
    main()