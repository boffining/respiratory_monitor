from acconeer.exptool.a121 import Client
from acconeer.exptool.a121.algo.breathing import RefApp
from acconeer.exptool.a121.algo.breathing._ref_app import (
    BreathingProcessorConfig,
    RefAppConfig,
    get_sensor_config,
)
from acconeer.exptool.a121.algo.presence import ProcessorConfig as PresenceProcessorConfig


def main():
    # Initialize configurations
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

    # Open a connection to the radar via SPI
    client = Client.open(ip_address="192.168.50.175")  # Update this if using a different SPI device
    client.setup_session(get_sensor_config(ref_app_config))
    ref_app = RefApp(client=client, sensor_id=sensor, ref_app_config=ref_app_config)
    ref_app.start()

    try:
        while True:
            data = ref_app.get_next()
            process_breathing_result(data.breathing_result)
            process_presence_result(data.presence_result)
    except KeyboardInterrupt:
        print("Stopping session.")
    finally:
        ref_app.stop()
        client.close()


def process_breathing_result(result):
    if result.breathing_rate < 6 or result.breathing_rate > 60:
        print(f"Alert: Breathing anomaly detected! Rate: {result.breathing_rate}")
    else:
        print(f"Breathing rate: {result.breathing_rate} bpm")


def process_presence_result(result):
    if result.presence_detected:
        print("Presence detected")
    else:
        print("No presence detected")


if __name__ == "__main__":
    main()
