#!/usr/bin/python3
import time
import logging
import subprocess
import signal
import sys
import os
from picamera2 import Picamera2

# --- Configuration ---
TEST_RESOLUTION_WIDTH = 1920
TEST_RESOLUTION_HEIGHT = 1080
TEST_FPS = 30.0 

GST_ENCODER = "v4l2h264enc"
GST_BITRATE_KBPS = 6000
GST_TARGET_HOST = "192.168.50.183"  # <<< REPLACE THIS!
GST_TARGET_PORT = 5004
REQUESTED_PICAM2_FORMAT = "YUV420" # Crucial for this test

# --- Logging Setup ---
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PiStreamer")

# --- Global Variables ---
gst_process = None
capture_running_flag = True
python_read_fd = -1
python_write_file_obj = None
picam2_instance = None

def select_optimal_camera_mode(picam2_select):
    # This function is currently bypassed by hardcoded TEST_RESOLUTION/FPS in main()
    # For actual dynamic selection, it would need to be re-enabled and potentially made
    # aware of encoder limitations. For now, we focus on making the hardcoded mode work.
    sensor_modes = picam2_select.sensor_modes
    if not sensor_modes:
        logger.error("No sensor modes found!"); return None, None
    # Simplified: just find a mode that can provide the TEST_RESOLUTION
    # This is a placeholder if not hardcoding in main
    for mode_info in sensor_modes:
        if mode_info.get('size') == (TEST_RESOLUTION_WIDTH, TEST_RESOLUTION_HEIGHT):
            logger.info(f"Found sensor mode matching test resolution: {mode_info.get('size')}")
            return mode_info, TEST_FPS
    logger.warning(f"Could not find exact sensor mode for {TEST_RESOLUTION_WIDTH}x{TEST_RESOLUTION_HEIGHT}. Will let Picamera2 attempt to configure.")
    # Return a dummy mode_info that just contains the size, Picamera2 will use it.
    return {"size": (TEST_RESOLUTION_WIDTH, TEST_RESOLUTION_HEIGHT)}, TEST_FPS


def start_gstreamer_pipeline(input_fd_gst, width, height, fps, 
                             picam2_actual_format_str, 
                             actual_frame_buffer_size, actual_stride_from_picam2):
    global gst_process
    gst_source_format_from_picam2 = 'UNKNOWN' # Renamed for clarity
    if picam2_actual_format_str == 'YUV420': gst_source_format_from_picam2 = 'I420'
    elif picam2_actual_format_str == 'BGR888': gst_source_format_from_picam2 = 'BGR'
    elif picam2_actual_format_str == 'RGB888': gst_source_format_from_picam2 = 'RGB'
    elif picam2_actual_format_str == 'XRGB8888': gst_source_format_from_picam2 = 'XRGB'
    else: 
        logger.error(f"Unsupported Picamera2 format '{picam2_actual_format_str}' for GStreamer. Cannot proceed.")
        return None

    framerate_str_gst = f"{int(fps)}/1" if fps and fps > 0 else "30/1"
    target_bitrate_bps_gst = GST_BITRATE_KBPS * 1000

    # Base caps from fdsrc - MUST accurately describe the data Picamera2 outputs
    caps_from_fdsrc_gst = (
        f"video/x-raw,format={gst_source_format_from_picam2},width={width},height={height},"
        f"framerate={framerate_str_gst},stride={actual_stride_from_picam2},"
        f"pixel-aspect-ratio=1/1,interlace-mode=progressive"
    )
    
    # Caps for H.264 after encoding
    caps_after_encoder_gst = "video/x-h264" 

    pipeline_elements = [
        "gst-launch-1.0", "-v",
        "fdsrc", f"fd={input_fd_gst}", f"blocksize={actual_frame_buffer_size}", "num-buffers=-1",
        "!", "queue", # Queue immediately after fdsrc
        "!", caps_from_fdsrc_gst
    ]

    # --- MODIFICATION: Conditional videoconvert ---
    # If Picamera2 output is I420 and v4l2h264enc can take I420, try direct connection.
    # Otherwise, use videoconvert to NV12 (common preferred format for v4l2h264enc).
    # You should check `gst-inspect-1.0 v4l2h264enc` sink caps.
    # For this test, we assume YUV420 (I420) from Picamera2 and will try direct first.
    # If other formats like BGR888 are used, videoconvert is essential.
    
    if gst_source_format_from_picam2 == 'I420':
        logger.info("Picamera2 output is I420. Attempting to connect directly to v4l2h264enc.")
        # (No videoconvert, no NV12 capsfilter before encoder)
    else:
        # For other formats (e.g., BGR, RGB), videoconvert to NV12 is necessary
        logger.info(f"Picamera2 output is {gst_source_format_from_picam2}. Using videoconvert to NV12.")
        caps_for_encoder_input_gst = f"video/x-raw,format=NV12,width={width},height={height},framerate={framerate_str_gst}"
        pipeline_elements.extend([
            "!", "videoconvert",
            "!", "queue", 
            "!", caps_for_encoder_input_gst
        ])

    pipeline_elements.append("!")
    pipeline_elements.append(GST_ENCODER)

    if GST_ENCODER == "v4l2h264enc":
        h264_level_for_encoder = 11 # Level 4.1 for 1080p30
        if TEST_FPS >= 50: h264_level_for_encoder = 12
        extra_controls = (
            f'extra-controls="controls,'
            f'video_bitrate_mode=1,video_bitrate={target_bitrate_bps_gst},'
            f'h264_profile=4,h264_level={h264_level_for_encoder},h264_i_frame_period=60"'
        )
        pipeline_elements.append(extra_controls)

    pipeline_elements.extend([
        "!", caps_after_encoder_gst,
        "!", "h264parse", "config-interval=-1",
        "!", "queue", 
        "!", "rtph264pay", "pt=96", "mtu=1400", "config-interval=1",
        "!", "udpsink", f"host={GST_TARGET_HOST}", f"port={GST_TARGET_PORT}", "sync=false"
    ])

    logger.debug("--- GStreamer Launch Parameters ---")
    # (Same detailed logging of parameters as before)
    logger.debug(f"  Input FD for GStreamer: {input_fd_gst}")
    logger.debug(f"  Resolution: {width}x{height}")
    logger.debug(f"  FPS: {fps} (GStreamer framerate: {framerate_str_gst})")
    logger.debug(f"  Picamera2 Format (GStreamer equivalent): {gst_source_format_from_picam2}")
    logger.debug(f"  Actual Frame Buffer Size (blocksize for fdsrc): {actual_frame_buffer_size}")
    logger.debug(f"  Stride from Picamera2 (for fdsrc caps): {actual_stride_from_picam2}")
    logger.debug(f"  Full GStreamer pipeline string to be launched:\n{' '.join(pipeline_elements)}")
    logger.debug("------------------------------------")
    
    gst_env = os.environ.copy()
    gst_env["GST_DEBUG"] = ("3,fdsrc:3,basesrc:3,GST_CAPS:3,negotiation:3,GST_PIPELINE:3," # Increased verbosity
                           "videoconvert:3,v4l2h264enc:3,h264parse:3,queue:3,default:3")
    # dot_dir = "/tmp/gst_dot_files_streamer"; os.makedirs(dot_dir, exist_ok=True)
    # gst_env["GST_DEBUG_DUMP_DOT_DIR"] = dot_dir
    logger.debug(f"GST_DEBUG set to: {gst_env['GST_DEBUG']}")

    try:
        gst_process = subprocess.Popen(
            pipeline_elements, pass_fds=(input_fd_gst,), env=gst_env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logger.info(f"GStreamer process started with PID: {gst_process.pid}")
    except Exception as e:
        logger.error(f"Failed to start GStreamer: {e}"); gst_process = None
    return gst_process

# (signal_handler_main remains the same robust version)
def signal_handler_main(sig, frame):
    global capture_running_flag, gst_process, python_read_fd, python_write_file_obj, picam2_instance
    logger.info(f"Shutdown signal {signal.Signals(sig).name} received. Initiating cleanup sequence...")
    capture_running_flag = False; time.sleep(0.5) 
    if gst_process and gst_process.poll() is None:
        logger.info(f"SignalH: Terminating GStreamer {gst_process.pid}..."); gst_process.terminate()
        try: gst_process.wait(timeout=1)
        except subprocess.TimeoutExpired: logger.warning("SignalH: GStreamer kill."); gst_process.kill()
    if picam2_instance:
        logger.debug("SignalH: Picamera2 instance active, attempting stop/close.")
        try:
            if picam2_instance.started: logger.debug("SignalH: Stopping Picamera2..."); picam2_instance.stop()
        except Exception as e: logger.error(f"SignalH: Error stopping Picamera2: {e}")
        try: logger.debug("SignalH: Closing Picamera2..."); picam2_instance.close()
        except Exception as e: logger.error(f"SignalH: Error closing Picamera2: {e}")
    if python_write_file_obj and not python_write_file_obj.closed:
        logger.debug("SignalH: python_write_file_obj open, closing.")
        try: python_write_file_obj.close()
        except Exception as e: logger.error(f"SignalH: Error closing write_file_obj: {e}")
    if python_read_fd != -1:
        logger.debug(f"SignalH: Parent's read_fd ({python_read_fd}) open, closing.")
        try: os.close(python_read_fd)
        except OSError as e: logger.error(f"SignalH: Error closing read_fd {python_read_fd}: {e}")
    logger.info("SignalH: Cleanup attempt finished. Exiting."); sys.exit(0)


def main():
    global capture_running_flag, gst_process, python_read_fd, python_write_file_obj, picam2_instance
    signal.signal(signal.SIGINT, signal_handler_main)
    signal.signal(signal.SIGTERM, signal_handler_main)

    try:
        logger.info("Initializing Picamera2...")
        picam2_instance = Picamera2()
        
        logger.warning(f"<<<< USING TEMPORARY HARDCODED MODE: {TEST_RESOLUTION_WIDTH}x{TEST_RESOLUTION_HEIGHT} @ {TEST_FPS} FPS >>>>")
        picam2_target_size = (TEST_RESOLUTION_WIDTH, TEST_RESOLUTION_HEIGHT)
        picam2_target_fps = TEST_FPS
        # Ensure REQUESTED_PICAM2_FORMAT is YUV420 for the direct-to-encoder test path
        picam2_capture_format = "YUV420" # Explicitly set for this test
        if REQUESTED_PICAM2_FORMAT != "YUV420":
            logger.warning(f"Overriding REQUESTED_PICAM2_FORMAT. Using YUV420 for direct encoder test.")


        main_stream_config = {"size": picam2_target_size, "format": picam2_capture_format}
        controls_for_picam2 = {"FrameRate": float(picam2_target_fps)}
        
        video_config = picam2_instance.create_video_configuration(
            main=main_stream_config, controls=controls_for_picam2, queue=True, buffer_count=6)
        logger.info(f"Requesting Picamera2 configuration (TEST MODE): {video_config}")
        picam2_instance.configure(video_config)

        actual_camera_config = picam2_instance.camera_configuration()
        if not actual_camera_config or 'main' not in actual_camera_config:
            logger.error("Failed to get valid camera configuration from Picamera2."); return

        actual_main_stream_config = actual_camera_config['main']
        final_width = actual_main_stream_config.get('size', (0,0))[0]
        final_height = actual_main_stream_config.get('size', (0,0))[1]
        final_format_from_picam2 = actual_main_stream_config.get('format') # Actual format from Picamera2
        actual_fps = actual_camera_config.get('controls', {}).get('FrameRate', picam2_target_fps)
        actual_frame_buffer_size = actual_main_stream_config.get('framesize')
        actual_stride = actual_main_stream_config.get('stride')

        logger.info(f"Picamera2 actual config: {final_width}x{final_height} Fmt: '{final_format_from_picam2}' Stride: {actual_stride} Framesize: {actual_frame_buffer_size} FPS: ~{actual_fps}")

        assert actual_frame_buffer_size is not None, "CRITICAL: 'framesize' MUST be present in Picamera2 stream config."
        assert actual_stride is not None, "CRITICAL: 'stride' MUST be present in Picamera2 stream config for raw formats."
        assert final_format_from_picam2 == "YUV420", f"CRITICAL: Expected Picamera2 format to be YUV420 for this test, but got {final_format_from_picam2}"


        # --- ADDED: Detailed check for YUV420 (I420) buffer size consistency ---
        if final_format_from_picam2 == 'YUV420':
            # For I420, Y plane: W_stride * H. U/V planes: (W_stride/2) * (H/2) each.
            # GStreamer often expects stride to be even. Picamera2 stride should be.
            # If stride for U/V is half of Y stride (common for I420):
            y_plane_size = actual_stride * final_height
            uv_plane_width_stride = actual_stride // 2 # Assuming Y stride is multiple of 2
            uv_plane_height = final_height // 2
            u_plane_size = uv_plane_width_stride * uv_plane_height
            v_plane_size = uv_plane_width_stride * uv_plane_height
            calculated_i420_size = y_plane_size + u_plane_size + v_plane_size
            
            logger.debug(f"For YUV420 (I420) from Picamera2:")
            logger.debug(f"  W={final_width}, H={final_height}, Y-Stride={actual_stride}")
            logger.debug(f"  Y-plane: {actual_stride}x{final_height} = {y_plane_size}")
            logger.debug(f"  UV-planes (assumed stride {uv_plane_width_stride}): {uv_plane_width_stride}x{uv_plane_height} (x2) = {u_plane_size * 2}")
            logger.debug(f"  Calculated total I420 size based on Y-stride: {calculated_i420_size}")
            logger.debug(f"  Picamera2 reported framesize: {actual_frame_buffer_size}")
            if calculated_i420_size != actual_frame_buffer_size:
                logger.warning(
                    f"Calculated I420 size ({calculated_i420_size}) does NOT exactly match "
                    f"Picamera2 framesize ({actual_frame_buffer_size}). "
                    f"Difference: {abs(calculated_i420_size - actual_frame_buffer_size)} bytes. "
                    "This might indicate non-standard packing or subtle differences in how planes are arranged in the buffer Picamera2 provides. "
                    "Using Picamera2's framesize for fdsrc blocksize is generally correct."
                )
        # --- END ADDED ---


        fd_for_gst_read, write_fd_int = os.pipe()
        python_read_fd = fd_for_gst_read
        python_write_file_obj = os.fdopen(write_fd_int, 'wb', buffering=0)
        logger.info(f"Created pipe: GStreamer reads fd {fd_for_gst_read}, Python writes to wrapped fd {write_fd_int} (unbuffered).")

        gst_process = start_gstreamer_pipeline(
            fd_for_gst_read, final_width, final_height, actual_fps, 
            final_format_from_picam2, actual_frame_buffer_size, actual_stride
        )
        
        def gst_output_reader(pipe_to_read, pipe_name_str): # Corrected variable names
            try:
                for line in iter(pipe_to_read.readline, ''):
                    print(f"[{pipe_name_str}] {line.strip()}", file=sys.stderr)
            except Exception as e:
                logger.error(f"Error reading GStreamer {pipe_name_str}: {e}")
            finally:
                if pipe_to_read:
                    try:
                        pipe_to_read.close()
                    except Exception:
                        pass

        if gst_process:
            if gst_process.stdout:
                threading.Thread(target=gst_output_reader, args=(gst_process.stdout, "GST-STDOUT"), daemon=True).start()
            if gst_process.stderr:
                threading.Thread(target=gst_output_reader, args=(gst_process.stderr, "GST-STDERR"), daemon=True).start()

        if gst_process and gst_process.poll() is None:
            logger.info(f"GStreamer process launched. Closing parent's copy of fd {fd_for_gst_read}")
            os.close(fd_for_gst_read); python_read_fd = -1
        else: # GStreamer failed to launch
            if python_read_fd != -1: os.close(python_read_fd); python_read_fd = -1
            if python_write_file_obj and not python_write_file_obj.closed: python_write_file_obj.close()
            logger.error("GStreamer process failed to launch or exited immediately. Check GST_DEBUG logs via [GST-STDERR].")
            if gst_process: time.sleep(0.2); logger.error(f"GStreamer exit code on immediate failure: {gst_process.returncode if gst_process.poll() is not None else 'still running?'}")
            raise RuntimeError("GStreamer process failed to launch or exited immediately.")

        logger.info("Starting Picamera2 capture loop..."); picam2_instance.start()
        logger.info(f"🚀 Streaming active! Target: udp://{GST_TARGET_HOST}:{GST_TARGET_PORT}"); print("Press Ctrl+C to stop.")
        frame_count = 0; capture_start_time = time.monotonic()
        while capture_running_flag:
            buffer_data = picam2_instance.capture_buffer("main")
            if buffer_data is None: logger.warning("capture_buffer None, stopping."); capture_running_flag = False; break
            if len(buffer_data) != actual_frame_buffer_size:
                logger.error(f"CRITICAL: Buffer size mismatch frame {frame_count}! Picamera2 config said {actual_frame_buffer_size}, capture_buffer returned {len(buffer_data)}. Stopping.")
                capture_running_flag = False; break
            try:
                bytes_written = python_write_file_obj.write(buffer_data)
                if bytes_written is None or bytes_written != actual_frame_buffer_size: 
                    logger.warning(f"Short write to pipe frame {frame_count}. Wrote {bytes_written} of {actual_frame_buffer_size}")
                frame_count += 1
            except BrokenPipeError: logger.warning(f"Broken pipe frame {frame_count}. GStreamer exited?"); capture_running_flag = False; break
            except Exception as e: logger.error(f"Error writing pipe frame {frame_count}: {e}"); capture_running_flag = False; break
            if frame_count > 0 and frame_count % (int(actual_fps or 30) * 10) == 0: 
                 current_time = time.monotonic()
                 if current_time > capture_start_time:
                    avg_fps_capture = frame_count / (current_time - capture_start_time)
                    logger.info(f"Streamed {frame_count} frames... (avg capture FPS: {avg_fps_capture:.2f})")
            if gst_process.poll() is not None: 
                logger.error(f"GStreamer exited frame {frame_count} code {gst_process.returncode}."); capture_running_flag = False; break
        logger.info(f"Exited capture loop after {frame_count} frames.")
    except Exception as e:
        logger.critical(f"Critical error in main: {e}", exc_info=True)
    finally:
        # (Robust cleanup logic from previous version)
        logger.info("Performing final cleanup in main()..."); capture_running_flag = False
        local_picam2 = picam2_instance; local_write_obj = python_write_file_obj
        local_gst_proc = gst_process; local_read_fd = python_read_fd
        picam2_instance = None; python_write_file_obj = None; gst_process = None; python_read_fd = -1
        if local_picam2:
            if local_picam2.started:
                try:
                    logger.info("Stopping Picamera2 (mainF)...")
                    local_picam2.stop()
                except Exception as e:
                    logger.error(f"Err stop Picamera2 (mainF): {e}")
            try:
                logger.info("Closing Picamera2 (mainF)...")
                local_picam2.close()
            except Exception as e:
                logger.error(f"Error closing Picamera2 (mainF): {e}")
        if local_write_obj and not local_write_obj.closed:
            try: logger.info("Closing write_file_obj (mainF)..."); local_write_obj.close()
            except Exception as e: logger.error(f"Err close write_file_obj (mainF): {e}")
        if local_gst_proc and local_gst_proc.poll() is None:
            logger.info(f"MainF: GStreamer {local_gst_proc.pid} running, terminating..."); local_gst_proc.terminate()
            try: local_gst_proc.wait(timeout=1)
            except subprocess.TimeoutExpired: local_gst_proc.kill()
        if local_read_fd != -1: 
            logger.warning(f"MainF: Parent's read_fd ({local_read_fd}) was not -1, attempting close.")
            try: os.close(local_read_fd)
            except OSError as e: logger.error(f"Err close local_read_fd (mainF): {e}")
        logger.info("Main cleanup complete.")

if __name__ == '__main__':
    # (IP Address check from previous version)
    if GST_TARGET_HOST == "127.0.0.1" or GST_TARGET_HOST == "localhost" or GST_TARGET_HOST == "YOUR_VLC_CLIENT_IP_ADDRESS":
        logger.warning(f"GST_TARGET_HOST is '{GST_TARGET_HOST}'. Ensure this is the correct IP of your VLC client or 127.0.0.1 for local Pi testing.")
        if GST_TARGET_HOST == "YOUR_VLC_CLIENT_IP_ADDRESS":
             logger.error("CRITICAL: You MUST replace 'YOUR_VLC_CLIENT_IP_ADDRESS' in the script with the actual IP address of your VLC viewing computer.")
             sys.exit(1)
    elif not GST_TARGET_HOST or len(GST_TARGET_HOST.split('.')) != 4 : 
         logger.error(f"GST_TARGET_HOST ('{GST_TARGET_HOST}') does not look like a valid IPv4 address. Please configure it.")
         sys.exit(1)
    main()