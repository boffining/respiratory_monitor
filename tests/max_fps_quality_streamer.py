#!/usr/bin/python3
import time
import logging
import subprocess
import signal
import sys
import os
from picamera2 import Picamera2

# --- Configuration ---
TARGET_HIGH_FPS = 60
GST_ENCODER = "v4l2h264enc"
GST_BITRATE_KBPS = 8000
GST_TARGET_HOST = "192.169.50.173"  # <<< REPLACE THIS! Example: "192.168.1.101"
GST_TARGET_PORT = 5004
DEFAULT_CAPTURE_FORMAT = "YUV420" # Request this from Picamera2

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MaxPerfStreamer")

# --- Global Variables for Graceful Shutdown ---
gst_process = None
capture_running_flag = True
python_read_fd = -1
python_write_file_obj = None
picam2_instance = None

def select_optimal_camera_mode(picam2_select):
    sensor_modes = picam2_select.sensor_modes
    if not sensor_modes:
        logger.error("No sensor modes found!"); return None, None
    logger.info("Available sensor modes (showing size, format, bit_depth):")
    for i, mode_info in enumerate(sensor_modes):
        logger.info(f"  Mode {i}: {mode_info.get('size')}, Fmt: {mode_info.get('format', 'N/A')}, Depth: {mode_info.get('bit_depth')}")

    candidate_modes = [m for m in sensor_modes if m["size"][0] >= 1280]
    if candidate_modes:
        candidate_modes.sort(key=lambda m: m["size"][0] * m["size"][1], reverse=True)
        best_mode = candidate_modes[0]
        logger.info(f"Selected mode for ~{TARGET_HIGH_FPS} FPS: {best_mode['size']} (Fmt: {best_mode.get('format', 'N/A')})")
        return best_mode, TARGET_HIGH_FPS
    
    if sensor_modes:
        best_mode_overall = max(sensor_modes, key=lambda m: m["size"][0] * m["size"][1])
        logger.info(f"Fallback: Max res mode: {best_mode_overall['size']} (Fmt: {best_mode_overall.get('format', 'N/A')}), req FPS {TARGET_HIGH_FPS}.")
        return best_mode_overall, TARGET_HIGH_FPS
    logger.error("Could not select any camera mode."); return None, None

def start_gstreamer_pipeline(input_fd_gst, width, height, fps, picam2_format_str_in_script, 
                             actual_frame_buffer_size, actual_stride_from_picam2):
    global gst_process
    gst_source_format = 'BGR' 
    if picam2_format_str_in_script == 'YUV420': gst_source_format = 'I420'
    elif picam2_format_str_in_script == 'BGR888': gst_source_format = 'BGR'
    elif picam2_format_str_in_script == 'RGB888': gst_source_format = 'RGB'
    elif picam2_format_str_in_script == 'XRGB8888': gst_source_format = 'XRGB'
    else: logger.warning(f"Unsupported Picamera2 format {picam2_format_str_in_script} for GStreamer. Defaulting to BGR.")

    framerate_str_gst = f"{int(fps)}/1" if fps and fps > 0 else "30/1"
    target_bitrate_bps_gst = GST_BITRATE_KBPS * 1000

    caps_from_fdsrc_gst = (
        f"video/x-raw,format={gst_source_format},width={width},height={height},"
        f"framerate={framerate_str_gst},stride={actual_stride_from_picam2}"
    )
    logger.info(f"GStreamer caps_from_fdsrc_gst: {caps_from_fdsrc_gst}")
    caps_for_encoder_input_gst = f"video/x-raw,format=NV12,width={width},height={height},framerate={framerate_str_gst}"
    caps_after_encoder_gst = "video/x-h264"

    pipeline_elements = [
        "gst-launch-1.0", "-v",
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
            f'video_bitrate_mode=1,video_bitrate={target_bitrate_bps_gst},'
            f'h264_profile=4,h264_level=12,h264_i_frame_period=60"'
        )
        pipeline_elements.append(extra_controls)

    pipeline_elements.extend([
        "!", caps_after_encoder_gst,
        "!", "h264parse", "config-interval=-1",
        "!", "queue",
        "!", "rtph264pay", "pt=96", "mtu=1400", "config-interval=1",
        "!", "udpsink", f"host={GST_TARGET_HOST}", f"port={GST_TARGET_PORT}", "sync=false"
    ])
    logger.info(f"Launching GStreamer with: {' '.join(pipeline_elements)}")
    try:
        # Capture stderr for debugging
        gst_process = subprocess.Popen(
            pipeline_elements, 
            pass_fds=(input_fd_gst,),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.info(f"GStreamer process started with PID: {gst_process.pid}")
    except Exception as e:
        logger.error(f"Failed to start GStreamer: {e}"); gst_process = None
    return gst_process

def signal_handler_main(sig, frame):
    global capture_running_flag, gst_process, python_read_fd, python_write_file_obj, picam2_instance
    logger.info(f"Shutdown signal {signal.Signals(sig).name} received. Initiating cleanup sequence...")
    capture_running_flag = False  # Signal the main capture loop to stop

    # Allow a brief moment for the main loop to naturally exit and start its finally block
    time.sleep(0.5) 

    # Terminate GStreamer process
    if gst_process and gst_process.poll() is None:
        logger.info(f"Signal handler: Terminating GStreamer process {gst_process.pid}...")
        gst_process.terminate()
        try:
            gst_process.wait(timeout=1) # Short wait for graceful termination
            logger.info("Signal handler: GStreamer process terminated.")
        except subprocess.TimeoutExpired:
            logger.warning("Signal handler: GStreamer process did not terminate in time, killing.")
            gst_process.kill()
            logger.info("Signal handler: GStreamer process killed.")
    
    # Close Picamera2 instance (attempt stop if started)
    if picam2_instance:
        logger.warning("Signal handler: Picamera2 instance might still be active, attempting stop/close.")
        try:
            if picam2_instance.started:
                logger.info("Signal handler: Stopping Picamera2...")
                picam2_instance.stop()
        except Exception as e:
            logger.error(f"Signal handler: Error stopping Picamera2: {e}")
        try:
            logger.info("Signal handler: Closing Picamera2...")
            picam2_instance.close()
        except Exception as e:
            logger.error(f"Signal handler: Error closing Picamera2: {e}")
            
    # Close the write end of the pipe
    if python_write_file_obj and not python_write_file_obj.closed:
        logger.warning("Signal handler: python_write_file_obj still open, attempting close.")
        try:
            python_write_file_obj.close()
        except Exception as e:
            logger.error(f"Signal handler: Error closing python_write_file_obj: {e}")
            
    # Close parent's copy of read_fd if it wasn't already closed
    if python_read_fd != -1:
        logger.warning(f"Signal handler: Parent's read_fd ({python_read_fd}) for GStreamer pipe seems open, attempting close.")
        try:
            os.close(python_read_fd)
        except OSError as e:
            logger.error(f"Signal handler: Error closing read_fd {python_read_fd}: {e}")
            
    logger.info("Signal handler: Cleanup attempt finished. Exiting.")
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
            logger.error("Could not determine optimal camera mode. Exiting.")
            return

        main_stream_config = {"size": selected_mode_info["size"], "format": selected_capture_format_from_config}
        controls_for_picam2 = {"FrameRate": float(requested_fps)} if requested_fps else {}
        video_config = picam2_instance.create_video_configuration(
            main=main_stream_config, controls=controls_for_picam2, queue=True)
        logger.info(f"Requesting Picamera2 configuration: {video_config}")
        picam2_instance.configure(video_config)

        actual_camera_config = picam2_instance.camera_configuration()
        actual_main_stream_config = actual_camera_config['main']
        final_width = actual_main_stream_config['size'][0]
        final_height = actual_main_stream_config['size'][1]
        final_format_from_picam2 = actual_main_stream_config['format']
        actual_fps = actual_camera_config['controls'].get('FrameRate', TARGET_HIGH_FPS if requested_fps else 30)
        actual_frame_buffer_size = actual_main_stream_config.get('framesize')
        actual_stride = actual_main_stream_config.get('stride')

        logger.info(f"Picamera2 actual config: width={final_width}, height={final_height}, format={final_format_from_picam2}, stride={actual_stride}, framesize={actual_frame_buffer_size}, fps={actual_fps}")
        logger.info(f"Picamera2 reports format: {final_format_from_picam2}")

        if not actual_frame_buffer_size or not actual_stride:
            logger.error(f"CRITICAL: 'framesize' ({actual_frame_buffer_size}) or 'stride' ({actual_stride}) is missing from Picamera2 config for format {final_format_from_picam2}. Cannot reliably configure GStreamer. Exiting.")
            return
        
        fd_for_gst_read, write_fd_int = os.pipe()
        python_read_fd = fd_for_gst_read
        python_write_file_obj = os.fdopen(write_fd_int, 'wb')
        logger.info(f"Created pipe: GStreamer reads fd {fd_for_gst_read}, Python writes to wrapped fd {write_fd_int}")

        gst_process = start_gstreamer_pipeline(
            fd_for_gst_read, final_width, final_height, actual_fps, 
            final_format_from_picam2, actual_frame_buffer_size, actual_stride
        )

        # Print GStreamer stderr in a separate thread for live debugging
        def gst_stderr_printer(proc):
            for line in proc.stderr:
                print(f"[GStreamer STDERR] {line}", end="")
        if gst_process and gst_process.stderr:
            import threading
            threading.Thread(target=gst_stderr_printer, args=(gst_process,), daemon=True).start()

        if gst_process and gst_process.poll() is None:
            logger.info(f"GStreamer process launched. Closing parent's copy of fd {fd_for_gst_read}")
            os.close(fd_for_gst_read); python_read_fd = -1
        else:
            if python_read_fd != -1: os.close(python_read_fd); python_read_fd = -1
            if python_write_file_obj and not python_write_file_obj.closed: python_write_file_obj.close()
            logger.error("GStreamer process failed to launch or exited immediately.")
            if gst_process and gst_process.stderr:
                logger.error("GStreamer stderr output:")
                for line in gst_process.stderr:
                    print(line, end="")
            raise RuntimeError("GStreamer process failed to launch or exited immediately.")

        logger.info("Starting Picamera2 capture loop...")
        picam2_instance.start()
        logger.info(f"🚀 Streaming active! Target: udp://{GST_TARGET_HOST}:{GST_TARGET_PORT}"); print("Press Ctrl+C to stop.")
        frame_count = 0
        while capture_running_flag:
            buffer_data = picam2_instance.capture_buffer("main")
            if buffer_data is None: 
                logger.warning("capture_buffer None, stopping."); capture_running_flag = False; break
            if len(buffer_data) != actual_frame_buffer_size:
                logger.error(f"CRITICAL: Buffer size mismatch frame {frame_count}! Picamera2 config said {actual_frame_buffer_size}, capture_buffer returned {len(buffer_data)}. Stopping.")
                capture_running_flag = False; break
            try:
                python_write_file_obj.write(buffer_data)
                python_write_file_obj.flush()
                frame_count += 1
            except BrokenPipeError: 
                logger.warning(f"Broken pipe frame {frame_count}. GStreamer exited?"); capture_running_flag = False; break
            except Exception as e: 
                logger.error(f"Error writing pipe frame {frame_count}: {e}"); capture_running_flag = False; break
            if frame_count > 0 and frame_count % (int(actual_fps or 30) * 5) == 0: 
                logger.info(f"Streamed {frame_count} frames...")
            if gst_process.poll() is not None: 
                logger.error(f"GStreamer exited frame {frame_count} code {gst_process.returncode}."); capture_running_flag = False; break
        logger.info(f"Exited capture loop after {frame_count} frames.")

    except Exception as e:
        logger.critical(f"Critical error in main: {e}", exc_info=True)
        if gst_process and gst_process.stderr:
            logger.error("GStreamer stderr output (on exception):")
            for line in gst_process.stderr:
                print(line, end="")
    finally:
        logger.info("Performing final cleanup in main()...")
        capture_running_flag = False # Ensure any other loops stop

        if picam2_instance: # Use local var first if available, fallback to global
            if picam2_instance.started:
                try: logger.info("Stopping Picamera2 (main finally)..."); picam2_instance.stop()
                except Exception as e: logger.error(f"Err stop Picamera2 (main finally): {e}")
            try: logger.info("Closing Picamera2 (main finally)..."); picam2_instance.close()
            except Exception as e: logger.error(f"Error closing Picamera2 (main finally): {e}")
        
        if python_write_file_obj: # Use local var first
            if not python_write_file_obj.closed:
                try: logger.info("Closing write_file_obj (main finally)..."); python_write_file_obj.close()
                except Exception as e: logger.error(f"Err close write_file_obj (main finally): {e}")
        
        if gst_process: # Use local var first
            if gst_process.poll() is None:
                logger.info(f"Main finally: GStreamer {gst_process.pid} running, terminating..."); gst_process.terminate()
                try: gst_process.wait(timeout=1)
                except subprocess.TimeoutExpired: gst_process.kill()
        
        if python_read_fd != -1: # Check parent's copy status
            logger.warning(f"Main finally: Parent's read_fd ({python_read_fd}) still marked as open by main, attempting close.")
            try: os.close(python_read_fd)
            except OSError as e: logger.error(f"Err close python_read_fd (main finally): {e}")
        
        # Clear globals for sanity if script were to be re-run in same process (not typical for this script)
        picam2_instance = None
        python_write_file_obj = None
        gst_process = None
        python_read_fd = -1
        logger.info("Main cleanup complete.")

if __name__ == '__main__':
    if GST_TARGET_HOST == "127.0.0.1" or GST_TARGET_HOST == "localhost" or GST_TARGET_HOST == "YOUR_VLC_CLIENT_IP_ADDRESS":
        logger.warning(f"GST_TARGET_HOST is '{GST_TARGET_HOST}'. Ensure this is the correct IP of your VLC client or 127.0.0.1 for local Pi testing.")
        if GST_TARGET_HOST == "YOUR_VLC_CLIENT_IP_ADDRESS":
             logger.error("CRITICAL: You MUST replace 'YOUR_VLC_CLIENT_IP_ADDRESS' in the script with the actual IP address of your VLC viewing computer.")
             sys.exit(1)
    elif not GST_TARGET_HOST or len(GST_TARGET_HOST.split('.')) != 4 : # Basic sanity check for IP format
         logger.error(f"GST_TARGET_HOST ('{GST_TARGET_HOST}') does not look like a valid IPv4 address. Please configure it.")
         sys.exit(1)
    main()