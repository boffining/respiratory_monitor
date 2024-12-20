# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import numpy as np

import socket
import signal
import sys
from threading import Thread
import acconeer.exptool as et
from acconeer.exptool import a121
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

def socket_server_thread():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("0.0.0.0", 12345))  # Bind to all interfaces on port 12345
    server.listen(1)
    print("Waiting for connection from Android app...")
    conn, addr = server.accept()
    print(f"Connected to {addr}")
    return conn

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

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Allow reuse of the port
    server.bind(("192.168.50.175", 32345))
    server.listen(1)

    # Ensure proper cleanup on exit
    signal.signal(signal.SIGINT, handle_exit(server))
    signal.signal(signal.SIGTERM, handle_exit(server))
    
    print("Waiting for connection...")
    conn, addr = server.accept()
    print(f"Connected to {addr}")
    
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    # Setup the configurations
    # Detailed at https://docs.acconeer.com/en/latest/exploration_tool/algo/a121/ref_apps/breathing.html

    # Sensor selections
    sensor = 1

    # Ref App Configurations
    breathing_processor_config = BreathingProcessorConfig(
        lowest_breathing_rate=6,
        highest_breathing_rate=60,
        time_series_length_s=20,
    )

    # Presence Configurations
    presence_config = PresenceProcessorConfig(
        intra_detection_threshold=4,
        intra_frame_time_const=0.15,
        inter_frame_fast_cutoff=20,
        inter_frame_slow_cutoff=0.2,
        inter_frame_deviation_time_const=0.5,
    )

    # Breathing Configurations
    ref_app_config = RefAppConfig(
        use_presence_processor=True,
        num_distances_to_analyze=3,
        distance_determination_duration=5,
        breathing_config=breathing_processor_config,
        presence_config=presence_config,
    )

    # End setup configurations

    # Preparation for client
    sensor_config = get_sensor_config(ref_app_config=ref_app_config)
    client = a121.Client.open(**a121.get_client_args(args))
    client.setup_session(sensor_config)

    # Preparation for reference application processor
    ref_app = RefApp(client=client, sensor_id=sensor, ref_app_config=ref_app_config)
    ref_app.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    #breathing rate log file
    # f = open('breathing_log.txt','w')
    
    #conn = socket_server_thread()
    try:
        while not interrupt_handler.got_signal:
            ref_app_result = ref_app.get_next()
            displayed_breathing_rate = None
            try:
                _breathing_rate = ref_app_result.breathing_result
                if _breathing_rate:
                    # try:
                    breathing_result = ref_app_result.breathing_result.extra_result
                    _bpm_history = breathing_result.breathing_rate_history
                    _filtered_bpm_history = [i for i in _bpm_history if not np.isnan(i)]
                    if len(_filtered_bpm_history) > 0:
                        displayed_breathing_rate = "{:.1f}".format(_filtered_bpm_history[-1])
                        # f.write("{:.1f}".format(_bpm_history[-1]) + '\n')
                    # except:
                        # continue
                    # print("Breathing result " + str(_breathing_rate.breathing_rate))
                    # status_message = interpret_breathing_rate(_breathing_rate.breathing_rate)
                    # conn.sendall(f"{status_message}\n".encode("utf-8"))

            except et.PGProccessDiedException:
                print("PGProcess Died.")
                break
            
            app_state = ref_app_result.app_state
            
            # Presence text
            if app_state == AppState.NO_PRESENCE_DETECTED:
                status_message = "No presence detected"
            elif app_state == AppState.DETERMINE_DISTANCE_ESTIMATE:
                status_message = "Determining distance with presence"
            elif app_state == AppState.ESTIMATE_BREATHING_RATE:
                status_message = "Presence detected"
            elif app_state == AppState.INTRA_PRESENCE_DETECTED:
                status_message = "Motion detected"
            else:
                status_message = ""
                
            # Breathing text
            if app_state == AppState.ESTIMATE_BREATHING_RATE:
                if (
                    ref_app_result.breathing_result is not None
                    and ref_app_result.breathing_result.breathing_rate is None
                    ):
                    status_message = "Initializing breathing detection"
                elif displayed_breathing_rate is not None:
                    status_message = "Breathing rate: " + displayed_breathing_rate + " bpm"
            # else:
                # breathing_text = "Waiting for distance"
            
            # Send the status message.
            conn.sendall(f"{status_message}\n".encode("utf-8"))
            print(status_message)
        
    
    except KeyboardInterrupt:
        print("Stopping...")
    except Exception as e:
        print(f"Server Error: {e}")
    finally:
        # f.close()
        cleanup_socket(server)
        ref_app.stop()
        conn.close()


if __name__ == "__main__":
    main()