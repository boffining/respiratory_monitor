#!/usr/bin/python3
import time
import logging
import subprocess
import signal
import sys
import os
from picamera2 import Picamera2

# --- Configuration ---
# Temporarily hardcode for testing encoder limits.
# Once this works, you can try to make TARGET_RESOLUTION and TARGET_FPS dynamic again,
# but within the known limits of v4l2h264enc (e.g., 1080p60, or try 4Kp30 if on Pi 4/5).
TEST_RESOLUTION_WIDTH = 1920
TEST_RESOLUTION_HEIGHT = 1080
TEST_FPS = 30.0 # Use float for Picamera2 FrameRate control

GST_ENCODER = "v4l2h264enc"  # Hardware encoder for Raspberry Pi
GST_BITRATE_KBPS = 6000     # Target bitrate (e.g., 6 Mbps for 1080p30 is reasonable)
GST_TARGET_HOST = "192.168.50.183"  # <<< REPLACE THIS! Example: "192.168.1.101"
GST_TARGET_PORT = 5004
# Picamera2 output format. YUV420 (GStreamer I420) is efficient.
REQUESTED_PICAM2_FORMAT = "YUV420" 

# --- Logging Setup ---
logging.basicConfig(
    level=logging.DEBUG, # More verbose for debugging
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PiStreamer")

# --- Global Variables for Graceful Shutdown ---
gst_process = None
capture_running_flag = True
python_read_fd = -1          # Parent's copy of the read end of the pipe for GStreamer
python_write_file_obj = None # File object for the write end of the pipe for Picamera2
picam2_instance = None       # Picamera2 object

def start_gstreamer_pipeline(input_fd_gst, width, height, fps, 
                             picam2_actual_format_str, 
                             actual_frame_buffer_size, actual_stride_from_picam2):
    global gst_process

    # Determine GStreamer format string from Picamera2's actual output format
    gst_source_format = 'BGR' # Default if mapping fails
    if picam2_actual_format_str == 'YUV420': gst_source_format = 'I420'
    elif picam2_actual_format_str == 'BGR888': gst_source_format = 'BGR'
    elif picam2_actual_format_str == 'RGB888': gst_source_format = 'RGB'
    elif picam2_actual_format_str == 'XRGB8888': gst_source_format = 'XRGB'
    else: logger.warning(f"Unsupported Picamera2 format '{picam2_actual_format_str}' for GStreamer caps. Defaulting to BGR.")

    framerate_str_gst = f"{int(fps)}/1" if fps and fps > 0 else "30/1"
    target_bitrate_bps_gst = GST_BITRATE_KBPS * 1000

    # Caps for fdsrc output: describes the raw data from Picamera2
    caps_from_fdsrc_gst = (
        f"video/x-raw,format={gst_source_format},width={width},height={height},"
        f"framerate={framerate_str_gst},stride={actual_stride_from_picam2},"
        f"pixel-aspect-ratio=1/1,interlace-mode=progressive"
    )
    
    # Caps for encoder input: what videoconvert should output to the encoder
    caps_for_encoder_input_gst = f"video/x-raw,format=NV12,width={width},height={height},framerate={framerate_str_gst}"
    
    # Caps after encoder: very simple, let h264parse figure out details
    caps_after_encoder_gst = "video/x-h264"

    pipeline_elements = [
        "gst-launch-1.0", "-v",  # Enable verbose GStreamer logging
        "fdsrc", f"fd={input_fd_gst}", f"blocksize={actual_frame_buffer_size}", "num-buffers=-1",
        "!", "queue", # Queue after fdsrc
        "!", caps_from_fdsrc_gst,
        "!", "videoconvert",
        "!", "queue",  # Queue after videoconvert
        "!", caps_for_encoder_input_gst,
        "!", GST_ENCODER
    ]

    if GST_ENCODER == "v4l2h264enc":
        extra_controls = (
            f'extra-controls="controls,'
            f'video_bitrate_mode=1,'        # 1 = Constant Bitrate (CBR)
            f'video_bitrate={target_bitrate_bps_gst},'
            f'h264_profile=4,'            # High Profile
            f'h264_level=11,'              # Level 4.1 (1920x1080@30.1fps, 1920x1080@60fps if B frames are limited) -> 12 for 4.2 is safer for 1080p60
                                           # For 1080p30, level 4.0 (h264_level=10) or 4.1 (h264_level=11) is fine.
                                           # Let's use 11 for 1080p30. If going to 1080p60 later, 12 (Level 4.2) is better.
            f'h264_i_frame_period=60'     # Keyframe interval (e.g., 2 seconds at 30fps)
            f'"'
        )
        if TEST_FPS >= 50: # If testing higher FPS for 1080p
            extra_controls = extra_controls.replace('h264_level=11', 'h264_level=12') # Use Level 4.2 for 1080p60
        pipeline_elements.append(extra_controls)

    pipeline_elements.extend([
        "!", caps_after_encoder_gst,
        "!", "h264parse", "config-interval=-1",
        "!", "queue", # Queue before payloader
        "!", "rtph264pay", "pt=96", "mtu=1400", "config-interval=1",
        "!", "udpsink", f"host={GST_TARGET_HOST}", f"port={GST_TARGET_PORT}", "sync=false"
    ])

    logger.debug("--- GStreamer Launch Parameters ---")
    logger.debug(f"  Input FD for GStreamer: {input_fd_gst}")
    logger.debug(f"  Resolution: {width}x{height}")
    logger.debug(f"  FPS: {fps} (GStreamer framerate: {framerate_str_gst})")
    logger.debug(f"  Picamera2 Format (GStreamer equivalent): {gst_source_format}")
    logger.debug(f"  Actual Frame Buffer Size (blocksize for fdsrc): {actual_frame_buffer_size}")
    logger.debug(f"  Stride from Picamera2 (for fdsrc caps): {actual_stride_from_picam2}")
    logger.debug(f"  Full GStreamer pipeline string to be launched:\n{' '.join(pipeline_elements)}")
    logger.debug("------------------------------------")
    
    gst_env = os.environ.copy()
    gst_env["GST_DEBUG"] = ("3,fdsrc:5,basesrc:5,GST_CAPS:5,negotiation:5,GST_PIPELINE:4,"
                           "videoconvert:4,v4l2h264enc:4,h264parse:4,queue:4,default:2")
    # For DOT file generation (visualize pipeline states):
    # dot_dir = "/tmp/gst_dot_files_streamer"
    # os.makedirs(dot_dir, exist_ok=True)
    # gst_env["GST_DEBUG_DUMP_DOT_DIR"] = dot_dir
    # logger.debug(f"GST_DEBUG set to: {gst_env['GST_DEBUG']}. DOT files will be in {dot_dir if 'GST_DEBUG_DUMP_DOT_DIR' in gst_env else 'disabled'}")


    try:
        gst_process = subprocess.Popen(
            pipeline_elements, 
            pass_fds=(input_fd_gst,),
            env=gst_env,
            stdout=subprocess.PIPE, # Capture GStreamer's stdout
            stderr=subprocess.PIPE, # Capture GStreamer's stderr
            text=True # Decode as text
            )
        logger.info(f"GStreamer process started with PID: {gst_process.pid}")
    except Exception as e:
        logger.error(f"Failed to start GStreamer: {e}"); gst_process = None
    return gst_process

def signal_handler_main(sig, frame):
    global capture_running_flag, gst_process, python_read_fd, python_write_file_obj, picam2_instance
    logger.info(f"Shutdown signal {signal.Signals(sig).name} received. Initiating cleanup sequence...")
    capture_running_flag = False
    time.sleep(0.5) 
    if gst_process and gst_process.poll() is None:
        logger.info(f"SignalH: Terminating GStreamer {gst_process.pid}...")
        gst_process.terminate()
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
        
        # --- USING TEMPORARY HARDCODED MODE FOR TESTING ---
        logger.warning(f"<<<< USING TEMPORARY HARDCODED MODE: {TEST_RESOLUTION_WIDTH}x{TEST_RESOLUTION_HEIGHT} @ {TEST_FPS} FPS >>>>")
        picam2_target_size = (TEST_RESOLUTION_WIDTH, TEST_RESOLUTION_HEIGHT)
        picam2_target_fps = TEST_FPS
        picam2_capture_format = REQUESTED_PICAM2_FORMAT

        main_stream_config = {"size": picam2_target_size, "format": picam2_capture_format}
        controls_for_picam2 = {"FrameRate": float(picam2_target_fps)}
        
        video_config = picam2_instance.create_video_configuration(
            main=main_stream_config, 
            controls=controls_for_picam2,
            queue=True, buffer_count=6 
        )
        logger.info(f"Requesting Picamera2 configuration (TEST MODE): {video_config}")
        picam2_instance.configure(video_config)
        # --- END TEMPORARY MODE ---

        actual_camera_config = picam2_instance.camera_configuration()
        actual_main_stream_config = actual_camera_config['main']
        final_width = actual_main_stream_config['size'][0]
        final_height = actual_main_stream_config['size'][1]
        final_format_from_picam2 = actual_main_stream_config['format'] # Actual format from Picamera2
        actual_fps = actual_camera_config['controls'].get('FrameRate', picam2_target_fps)
        actual_frame_buffer_size = actual_main_stream_config.get('framesize')
        actual_stride = actual_main_stream_config.get('stride')

        logger.info(f"Picamera2 actual config: {final_width}x{final_height} Fmt: '{final_format_from_picam2}' Stride: {actual_stride} Framesize: {actual_frame_buffer_size} FPS: ~{actual_fps}")

        assert actual_frame_buffer_size is not None, "CRITICAL: 'framesize' MUST be present in Picamera2 stream config."
        assert actual_stride is not None, "CRITICAL: 'stride' MUST be present in Picamera2 stream config for raw formats."
        assert final_width > 0 and final_height > 0, "CRITICAL: Final width/height from Picamera2 invalid."
        assert actual_fps > 0, "CRITICAL: Actual FPS from Picamera2 invalid."
        assert actual_frame_buffer_size > 0 and actual_stride > 0, "CRITICAL: Framesize/stride must be positive."

        fd_for_gst_read, write_fd_int = os.pipe()
        python_read_fd = fd_for_gst_read
        python_write_file_obj = os.fdopen(write_fd_int, 'wb', buffering=0) # Unbuffered binary write
        logger.info(f"Created pipe: GStreamer reads fd {fd_for_gst_read}, Python writes to wrapped fd {write_fd_int} (unbuffered).")

        gst_process = start_gstreamer_pipeline(
            fd_for_gst_read, final_width, final_height, actual_fps, 
            final_format_from_picam2, actual_frame_buffer_size, actual_stride
        )
        
        # Thread to print GStreamer's stdout (if any) and stderr (for GST_DEBUG logs)
        def gst_output_reader(pipe, pipe_name):
            try:
                for line in iter(pipe.readline, ''):
                    logger.info(f"[{pipe_name}] {line.strip()}")
            except Exception as e:
                logger.error(f"Error reading GStreamer {pipe_name}: {e}")
            finally:
                pipe.close()

        if gst_process:
            if gst_process.stdout:
                threading.Thread(target=gst_output_reader, args=(gst_process.stdout, "GST-STDOUT"), daemon=True).start()
            if gst_process.stderr:
                threading.Thread(target=gst_output_reader, args=(gst_process.stderr, "GST-STDERR"), daemon=True).start()

        if gst_process and gst_process.poll() is None:
            logger.info(f"GStreamer process launched. Closing parent's copy of fd {fd_for_gst_read}")
            os.close(fd_for_gst_read); python_read_fd = -1
        else:
            if python_read_fd != -1: os.close(python_read_fd); python_read_fd = -1
            if python_write_file_obj and not python_write_file_obj.closed: python_write_file_obj.close()
            logger.error("GStreamer process failed to launch or exited immediately. Check GST_DEBUG logs if enabled.")
            # Attempt to read any immediate stderr/stdout from GStreamer if it failed quickly and Popen didn't error
            if gst_process:
                # Give threads a moment to print
                time.sleep(0.2)
                if gst_process.poll() is not None: # Check if it exited
                    logger.error(f"GStreamer exit code on immediate failure: {gst_process.returncode}")
            raise RuntimeError("GStreamer process failed to launch or exited immediately.")

        logger.info("Starting Picamera2 capture loop..."); picam2_instance.start()
        logger.info(f"🚀 Streaming active! Target: udp://{GST_TARGET_HOST}:{GST_TARGET_PORT}"); print("Press Ctrl+C to stop.")
        frame_count = 0
        capture_start_time = time.monotonic()

        while capture_running_flag:
            buffer_data = picam2_instance.capture_buffer("main")
            if buffer_data is None: 
                logger.warning("capture_buffer None from Picamera2, stopping."); capture_running_flag = False; break
            
            if len(buffer_data) != actual_frame_buffer_size:
                logger.error(f"CRITICAL: Buffer size mismatch frame {frame_count}! Picamera2 config said {actual_frame_buffer_size}, capture_buffer returned {len(buffer_data)}. Stopping.")
                capture_running_flag = False; break
            try:
                bytes_written = python_write_file_obj.write(buffer_data)
                if bytes_written != actual_frame_buffer_size: # Should not happen with unbuffered pipe to OS
                    logger.warning(f"Short write to pipe on frame {frame_count}. Wrote {bytes_written} of {actual_frame_buffer_size}")
                frame_count += 1
            except BrokenPipeError: 
                logger.warning(f"Broken pipe frame {frame_count}. GStreamer likely exited."); capture_running_flag = False; break
            except Exception as e: 
                logger.error(f"Error writing pipe frame {frame_count}: {e}"); capture_running_flag = False; break
            
            if frame_count > 0 and frame_count % (int(actual_fps or 30) * 10) == 0: # Log every 10 seconds approx
                 current_time = time.monotonic()
                 avg_fps = frame_count / (current_time - capture_start_time)
                 logger.info(f"Streamed {frame_count} frames... (avg capture FPS: {avg_fps:.2f})")

            if gst_process.poll() is not None: 
                logger.error(f"GStreamer exited during capture (frame {frame_count}) with code {gst_process.returncode}."); capture_running_flag = False; break
        
        logger.info(f"Exited capture loop after {frame_count} frames.")

    except Exception as e:
        logger.critical(f"Critical error in main: {e}", exc_info=True)
    finally:
        logger.info("Performing final cleanup in main()..."); capture_running_flag = False
        local_picam2 = picam2_instance; local_write_obj = python_write_file_obj
        local_gst_proc = gst_process; local_read_fd = python_read_fd
        picam2_instance = None; python_write_file_obj = None; gst_process = None; python_read_fd = -1

        if local_picam2:
            if local_picam2.started:
                try: logger.info("Stopping Picamera2 (mainF)..."); local_picam2.stop()
                except Exception as e: logger.error(f"Err stop Picamera2 (mainF): {e}")
            try: logger.info("Closing Picamera2 (mainF)..."); local_picam2.close()
            except Exception as e: logger.error(f"Error closing Picamera2 (mainF): {e}")
        if local_write_obj and not local_write_obj.closed:
            try: logger.info("Closing write_file_obj (mainF)..."); local_write_obj.close()
            except Exception as e: logger.error(f"Err close write_file_obj (mainF): {e}")
        if local_gst_proc and local_gst_proc.poll() is None:
            logger.info(f"MainF: GStreamer {local_gst_proc.pid} running, terminating..."); local_gst_proc.terminate()
            try: local_gst_proc.wait(timeout=1)
            except subprocess.TimeoutExpired: local_gst_proc.kill()
        if local_read_fd != -1: # Should have been closed and set to -1 if GStreamer launched
            logger.warning(f"MainF: Parent's read_fd ({local_read_fd}) still marked as open by main, attempting close.")
            try: os.close(local_read_fd)
            except OSError as e: logger.error(f"Err close local_read_fd (mainF): {e}")
        logger.info("Main cleanup complete.")

if __name__ == '__main__':
    if GST_TARGET_HOST == "127.0.0.1" or GST_TARGET_HOST == "localhost" or GST_TARGET_HOST == "YOUR_VLC_CLIENT_IP_ADDRESS":
        logger.warning(f"GST_TARGET_HOST is '{GST_TARGET_HOST}'. Ensure this is the correct IP of your VLC client or 127.0.0.1 for local Pi testing.")
        if GST_TARGET_HOST == "YOUR_VLC_CLIENT_IP_ADDRESS":
            logger.error("CRITICAL: You MUST replace 'YOUR_VLC_CLIENT_IP_ADDRESS' in the script with the actual IP address of your VLC viewing computer.")
            sys.exit(1)
    elif not GST_TARGET_HOST or len(GST_TARGET_HOST.split('.')) != 4:
        logger.error(f"GST_TARGET_HOST ('{GST_TARGET_HOST}') does not look like a valid IPv4 address. Please configure it.")
        sys.exit(1)
    main()