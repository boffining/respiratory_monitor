import socket
import signal
import sys
import time
from threading import Thread
import numpy as np
import acconeer.exptool as et
from acconeer.exptool.a121.algo.breathing import AppState, RefApp
from acconeer.exptool.a121.algo.breathing._ref_app import (
    BreathingProcessorConfig,
    RefAppConfig,
    get_sensor_config,
)
from acconeer.exptool.a121.algo.presence import ProcessorConfig as PresenceProcessorConfig

def cleanup_socket(server_socket):
    server_socket.close()
    print("Socket cleaned up and closed.")

def handle_exit(server_socket):
    def signal_handler(sig, frame):
        print("Exiting...")
        cleanup_socket(server_socket)
        sys.exit(0)
    return signal_handler

def create_server_socket(host="192.168.50.175", port=32345):
    while True:
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(1)
            print("Server socket created and listening...")
            return server
        except Exception as e:
            print(f"Socket creation failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)

def wait_for_connection(server):
    while True:
        try:
            print("Waiting for connection from Android app...")
            conn, addr = server.accept()
            print(f"Connected to {addr}")
            return conn
        except Exception as e:
            print(f"Error accepting connection: {e}. Retrying...")

def interpret_breathing_rate(breathing_rate):
    if breathing_rate is None:
        return "No Data"
    elif breathing_rate == 0:
        return "No Presence Detected"
    elif 6 <= breathing_rate <= 20:
        return "Normal Breathing"
    elif breathing_rate > 20:
        return "Fast Breathing Detected"
    elif breathing_rate < 6:
        return "Slow Breathing Detected"
    else:
        return "Unknown Status"

def start_breathing_monitoring(conn):
    args = et.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    sensor = 1
    breathing_processor_config = BreathingProcessorConfig(
        lowest_breathing_rate=6,
        highest_breathing_rate=60,
        time_series_length_s=20,
    )
    presence_config = PresenceProcessorConfig(
        intra_detection_threshold=4,
        intra_frame_time_const=0.15,
        inter_frame_fast_cutoff=20,
        inter_frame_slow_cutoff=0.2,
        inter_frame_deviation_time_const=0.5,
    )
    ref_app_config = RefAppConfig(
        use_presence_processor=True,
        num_distances_to_analyze=3,
        distance_determination_duration=5,
        breathing_config=breathing_processor_config,
        presence_config=presence_config,
    )

    sensor_config = get_sensor_config(ref_app_config=ref_app_config)
    client = a121.Client.open(**a121.get_client_args(args))
    client.setup_session(sensor_config)

    ref_app = RefApp(client=client, sensor_id=sensor, ref_app_config=ref_app_config)
    ref_app.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    last_status = None

    try:
        while not interrupt_handler.got_signal:
            try:
                ref_app_result = ref_app.get_next()
                app_state = ref_app_result.app_state
                displayed_breathing_rate = None

                if app_state == AppState.ESTIMATE_BREATHING_RATE:
                    if ref_app_result.breathing_result:
                        _bpm_history = ref_app_result.breathing_result.extra_result.breathing_rate_history
                        _filtered_bpm_history = [i for i in _bpm_history if not np.isnan(i)]
                        if _filtered_bpm_history:
                            displayed_breathing_rate = f"{_filtered_bpm_history[-1]:.1f}"

                status_message = interpret_breathing_rate(
                    ref_app_result.breathing_result.breathing_rate if ref_app_result.breathing_result else None
                )

                conn.sendall(f"{status_message}\n".encode("utf-8"))
                if status_message != last_status:
                    last_status = status_message
                    print(status_message)
            except Exception as e:
                print(f"Error during monitoring: {e}")
                break

    except KeyboardInterrupt:
        print("Monitoring stopped.")
    finally:
        ref_app.stop()
        conn.close()
        client.close()

def main():
    server = create_server_socket("192.168.50.175", 32345)
    signal.signal(signal.SIGINT, handle_exit(server))
    signal.signal(signal.SIGTERM, handle_exit(server))

    while True:
        conn = wait_for_connection(server)
        try:
            start_breathing_monitoring(conn)
        except Exception as e:
            print(f"Error in session: {e}. Restarting...")
            conn.close()

if __name__ == "__main__":
    main()
