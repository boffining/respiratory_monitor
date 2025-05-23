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
DEFAULT_CAPTURE_FORMAT = "YUV420" # Request this from Picamera2 (corresponds to I420 in GStreamer)

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
    
    if sensor_modes: # Fallback to overall max resolution
        best_mode_overall = max(sensor_modes, key=lambda m: m["size"][0] * m["size"][1])
        logger.info(f"Fallback: Max res mode: {best_mode_overall['size']} (Fmt: {best_mode_overall.get('format', 'N/A')}), req FPS {TARGET_HIGH_FPS}.")
        return best_mode_overall, TARGET_HIGH_FPS
    logger.error("Could not select any camera mode."); return None, None

# ADDED actual_stride_from_picam2 argument
def start_gstreamer_pipeline(input_fd_gst, width, height, fps, picam2_format_str_in_script, 
                             actual_frame_buffer_size, actual_stride_from_picam2):
    global gst_process
    gst_source_format = 'BGR' # Default
    if picam2_format_str_in_script == 'YUV420': gst_source_format = 'I420'
    elif picam2_format_str_in_script == 'BGR888': gst_source_format = 'BGR'
    elif picam2_format_str_in_script == 'RGB888': gst_source_format = 'RGB'
    elif picam2_format_str_in_script == 'XRGB8888': gst_source_format = 'XRGB'
    else: logger.warning(f"Unsupported Picamera2 format {picam2_format_str_in_script} for GStreamer. Defaulting to BGR.")

    framerate_str_gst = f"{int(fps)}/1" if fps and fps > 0 else "30/1"
    target_bitrate_bps_gst = GST_BITRATE_KBPS * 1000

    # --- MODIFICATION: Added stride to caps_from_fdsrc_gst ---
    caps_from_fdsrc_gst = (
        f"video/x-raw,format={gst_source_format},width={width},height={height},"
        f"framerate={framerate_str_gst},stride={actual_stride_from_picam2}"
    )
    
    caps_for_encoder_input_gst = f"video/x-raw,format=NV12,width={width},height={height},framerate={framerate_str_gst}"
    caps_after_encoder_gst = "video/x-h264" # Kept simple

    pipeline_elements = [
        "gst-launch-1.0", "-v",
        "fdsrc", f"fd={input_fd_gst}", f"blocksize={actual_frame_buffer_size}",
        "!", caps_from_fdsrc_gst, # Now includes stride
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
    logger.info(f"Starting GStreamer pipeline: {' '.join(pipeline_elements)}")
    try:
        gst_process = subprocess.Popen(pipeline_elements, pass_fds=(input_fd_gst,))
        logger.info(f"GStreamer process started with PID: {gst_process.pid}")
    except Exception as e:
        logger.error(f"Failed to start GStreamer: {e}"); gst_process = None
    return gst_process

def signal_handler_main(sig, frame):
    # (Same robust signal handler as previous version)
    global capture_running_flag, gst_process, python_read_fd, python_write_file_obj, picam2_instance
    logger.info(f"Shutdown signal {signal.Signals(sig).name} received. Cleaning up...")
    capture_running_flag = False; time.sleep(0.5)
    if gst_process and gst_process.poll() is None:
        logger.info(f"SignalH: Terminating GStreamer {gst_process.pid}..."); gst_process.terminate()
        try: gst_process.wait(timeout=1)
        except subprocess.TimeoutExpired: logger.warning("SignalH: GStreamer kill."); gst_process.kill()
    if python_write_file_obj and not python_write_file_obj.closed:
        logger.warning("SignalH: python_write_file_obj open, closing.");_ = [python_write_file_obj.close() try_close else None for try_close in [1]]
    if picam2_instance:
        logger.warning("SignalH: Picamera2 active, stopping/closing.");_
        try:
            if picam2_instance.started: picam2_instance.stop()
        except: pass
        try: picam2_instance.close()
        except: pass
    if python_read_fd != -1:
        logger.warning(f"SignalH: Parent's read_fd ({python_read_fd}) open, closing.");_
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
        if not selected_mode_info: logger.error("Could not determine optimal camera mode. Exiting."); return

        main_stream_config = {"size": selected_mode_info["size"], "format": selected_capture_format_from_config}
        controls_for_picam2 = {"FrameRate": float(requested_fps)} if requested_fps else {}
        video_config = picam2_instance.create_video_configuration(
            main=main_stream_config, controls=controls_for_picam2, raw=selected_mode_info,
            queue=True, buffer_count=6)
        logger.info(f"Requesting Picamera2 configuration: {video_config}")
        picam2_instance.configure(video_config)

        actual_camera_config = picam2_instance.camera_configuration()
        actual_main_stream_config = actual_camera_config['main']
        final_width = actual_main_stream_config['size'][0]
        final_height = actual_main_stream_config['size'][1]
        final_format_from_picam2 = actual_main_stream_config['format']
        actual_fps = actual_camera_config['controls'].get('FrameRate', TARGET_HIGH_FPS if requested_fps else 30)
        
        actual_frame_buffer_size = actual_main_stream_config.get('framesize')
        actual_stride = actual_main_stream_config.get('stride') # Get stride

        if not actual_frame_buffer_size or not actual_stride:
            logger.error(f"CRITICAL: 'framesize' ({actual_frame_buffer_size}) or 'stride' ({actual_stride}) is missing from Picamera2 config for format {final_format_from_picam2}. Cannot reliably configure GStreamer. Exiting.")
            return
        
        logger.info(f"Picamera2 configured. Stream: {final_width}x{final_height} Fmt: {final_format_from_picam2} FPS: ~{actual_fps}. BufSize: {actual_frame_buffer_size}, Stride: {actual_stride} bytes.")

        fd_for_gst_read, write_fd_int = os.pipe()
        python_read_fd = fd_for_gst_read
        python_write_file_obj = os.fdopen(write_fd_int, 'wb')
        logger.info(f"Created pipe: GStreamer reads fd {fd_for_gst_read}, Python writes to wrapped fd {write_fd_int}")

        gst_process = start_gstreamer_pipeline(
            fd_for_gst_read, final_width, final_height, actual_fps, 
            final_format_from_picam2, actual_frame_buffer_size, actual_stride # Pass stride
        )

        if gst_process and gst_process.poll() is None:
            logger.info(f"GStreamer process launched. Closing parent's copy of fd {fd_for_gst_read}")
            os.close(fd_for_gst_read); python_read_fd = -1
        else:
            if python_read_fd != -1: os.close(python_read_fd); python_read_fd = -1
            if python_write_file_obj and not python_write_file_obj.closed: python_write_file_obj.close()
            raise RuntimeError("GStreamer process failed to launch or exited immediately.")

        logger.info("Starting Picamera2 capture loop..."); picam2_instance.start()
        logger.info(f"🚀 Streaming active! Target: udp://{GST_TARGET_HOST}:{GST_TARGET_PORT}"); print("Press Ctrl+C to stop.")
        frame_count = 0
        while capture_running_flag:
            buffer_data = picam2_instance.capture_buffer("main")
            if buffer_data is None: logger.warning("capture_buffer None, stopping."); capture_running_flag = False; break
            if len(buffer_data) != actual_frame_buffer_size: # Check against the known full buffer size
                logger.error(f"CRITICAL: Buffer size mismatch frame {frame_count}! Picamera2 config said {actual_frame_buffer_size}, capture_buffer returned {len(buffer_data)}. Stopping.")
                capture_running_flag = False; break
            try:
                python_write_file_obj.write(buffer_data); python_write_file_obj.flush(); frame_count += 1
            except BrokenPipeError: logger.warning(f"Broken pipe frame {frame_count}. GStreamer exited?"); capture_running_flag = False; break
            except Exception as e: logger.error(f"Error writing pipe frame {frame_count}: {e}"); capture_running_flag = False; break
            if frame_count > 0 and frame_count % (int(actual_fps or 30) * 5) == 0: logger.info(f"Streamed {frame_count} frames...")
            if gst_process.poll() is not None: logger.error(f"GStreamer exited frame {frame_count} code {gst_process.returncode}."); capture_running_flag = False; break
        logger.info(f"Exited capture loop after {frame_count} frames.")
    except Exception as e:
        logger.critical(f"Critical error in main: {e}", exc_info=True)
    finally:
        # (Robust cleanup logic from previous version)
        logger.info("Performing final cleanup in main()..."); capture_running_flag = False
        if picam2_instance:
            if picam2_instance.started: try: logger.info("Stopping Picamera2 (mainF)..."); picam2_instance.stop()
            except Exception as e: logger.error(f"Err stop Picamera2 (mainF): {e}")
            try: logger.info("Closing Picamera2 (mainF)..."); picam2_instance.close()
            except Exception as e: logger.error(f"Err close Picamera2 (mainF): {e}")
        picam2_instance = None
        if python_write_file_obj and not python_write_file_obj.closed:
            try: logger.info("Closing write_file_obj (mainF)..."); python_write_file_obj.close()
            except Exception as e: logger.error(f"Err close write_file_obj (mainF): {e}")
        python_write_file_obj = None
        if gst_process and gst_process.poll() is None:
            logger.info(f"MainF: GStreamer {gst_process.pid} running, terminating..."); gst_process.terminate()
            try: gst_process.wait(timeout=1)
            except subprocess.TimeoutExpired: gst_process.kill()
        gst_process = None
        if python_read_fd != -1:
            logger.warning(f"MainF: Parent's read_fd ({python_read_fd}) open, closing.");_
            try: os.close(python_read_fd)
            except OSError as e: logger.error(f"Err close python_read_fd (mainF): {e}")
        python_read_fd = -1
        logger.info("Main cleanup complete.")

if __name__ == '__main__':
    if GST_TARGET_HOST == "127.0.0.1" or GST_TARGET_HOST == "localhost" or GST_TARGET_HOST == "YOUR_VLC_CLIENT_IP_ADDRESS":
        logger.warning(f"GST_TARGET_HOST is '{GST_TARGET_HOST}'. Ensure this is the correct IP of your VLC client or 127.0.0.1 for local Pi testing.")
        if GST_TARGET_HOST == "YOUR_VLC_CLIENT_IP_ADDRESS":
             logger.error("CRITICAL: You MUST replace 'YOUR_VLC_CLIENT_IP_ADDRESS' in the script with the actual IP address.")
             sys.exit(1)
    elif not GST_TARGET_HOST or len(GST_TARGET_HOST.split('.')) != 4:
         logger.error(f"GST_TARGET_HOST ('{GST_TARGET_HOST}') does not look like a valid IP address. Please configure it.")
         sys.exit(1)
    main()