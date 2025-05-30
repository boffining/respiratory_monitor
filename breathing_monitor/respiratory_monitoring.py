# src/breathing_monitor/respiratory_monitoring.py

from acconeer.exptool import clients
from acconeer.exptool import configs
import numpy as np
from scipy.signal import butter, lfilter, savgol_filter
from scipy.fft import fft, ifft
from pykalman import KalmanFilter
import matplotlib.pyplot as plt
import logging
import requests
import time
import socket
import threading

class RespiratoryMonitoring:
    def __init__(self, host="192.168.50.175", port=32345, range_start=0.2, range_end=0.5, update_rate=10, push_notification_url=None):
        self.host = host
        self.port = port
        self.range_start = range_start
        self.range_end = range_end
        self.update_rate = update_rate
        self.push_notification_url = push_notification_url

        self.client = None
        self.logger = None
        self.server_socket = None
        self.conn = None
        self._setup_logger()

    def _setup_logger(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger("RespiratoryMonitoring")

    def start_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        self.logger.info(f"Server started on {self.host}:{self.port}. Waiting for connections...")

        while True:
            self.conn, addr = self.server_socket.accept()
            self.logger.info(f"Connected to {addr}")
            threading.Thread(target=self.get_breathing_data, daemon=True).start()

    def _setup_client(self):
        self.logger.info("Setting up Acconeer client...")
        client = clients.SocketClient(host="192.168.50.175")
        config = configs.IQServiceConfig()
        config.range_interval = [self.range_start, self.range_end]
        config.update_rate = self.update_rate
        config.gain = 0.5
        self.client = client.setup_session(config)
        self.client.start_session()

    def _create_filter(self, filter_type, cutoff, fs, order=5):
        nyquist = 0.5 * fs
        normal_cutoff = cutoff / nyquist
        b, a = butter(order, normal_cutoff, btype=filter_type, analog=False)
        return b, a

    def _apply_filter(self, data, b, a):
        return lfilter(b, a, data)

    def _apply_kalman_filter(self, data):
        kalman_filter = KalmanFilter(initial_state_mean=0, n_dim_obs=1)
        kalman_filter = kalman_filter.em(np.zeros((100, 1)), n_iter=10)
        filtered_state_means, _ = kalman_filter.filter(data)
        return filtered_state_means.flatten()

    def _apply_savgol_filter(self, data, window_length=11, polyorder=3):
        return savgol_filter(data, window_length, polyorder)

    def _apply_fft_denoising(self, data, threshold=0.1):
        freq_data = fft(data)
        magnitude = np.abs(freq_data)
        freq_data[magnitude < threshold * np.max(magnitude)] = 0
        return np.real(ifft(freq_data))

    def _send_push_notification(self, alert_message):
        if not self.push_notification_url:
            self.logger.warning("Push notification URL not configured. Cannot send alert.")
            return
        try:
            payload = {"alert": alert_message}
            response = requests.post(self.push_notification_url, json=payload)
            if response.status_code == 200:
                self.logger.info("Push notification sent successfully.")
            else:
                self.logger.error(f"Failed to send push notification: {response.status_code}, {response.text}")
        except Exception as e:
            self.logger.error(f"Error while sending push notification: {e}")

    def visualize_waveform(self, raw_waveform, cleaned_waveform):
        self.logger.info("Visualizing waveforms.")
        plt.figure(figsize=(12, 6))
        plt.subplot(2, 1, 1)
        plt.plot(raw_waveform, label="Raw Waveform", color="gray")
        plt.title("Raw Breathing Waveform")
        plt.xlabel("Samples")
        plt.ylabel("Amplitude")
        plt.legend()
        plt.subplot(2, 1, 2)
        plt.plot(cleaned_waveform, label="Cleaned Waveform", color="green")
        plt.title("Processed Breathing Waveform")
        plt.xlabel("Samples")
        plt.ylabel("Amplitude")
        plt.legend()
        plt.tight_layout()
        plt.show()

    def get_breathing_data(self):
        while True:
            try:
                if not self.client:
                    self._setup_client()

                info, sweep = self.client.get_next()
                raw_waveform = np.array(sweep)

                high_pass_filter = self._create_filter('high', 0.5, 10)
                low_pass_filter = self._create_filter('low', 2.5, 10)

                high_passed = self._apply_filter(raw_waveform, *high_pass_filter)
                low_passed = self._apply_filter(high_passed, *low_pass_filter)
                kalman_filtered = self._apply_kalman_filter(low_passed)
                savgol_filtered = self._apply_savgol_filter(kalman_filtered)
                cleaned_waveform = self._apply_fft_denoising(savgol_filtered)

                motion_state = "Child in motion" if np.std(cleaned_waveform) > 0.05 else "Stable breathing waveform"
                alert = "Child not moving" if np.max(np.abs(cleaned_waveform)) < 0.02 else "Normal"

                # Send status first
                status_message = f"{motion_state}|{alert}".encode('utf-8')
                self.client_socket.send(struct.pack('!I', len(status_message)))
                self.client_socket.send(status_message)

                # Then send waveform data
                self.client_socket.send(struct.pack('!I', len(cleaned_waveform)))
                for value in cleaned_waveform:
                    self.client_socket.send(struct.pack('!f', float(value)))

                self.logger.info(f"Motion State: {motion_state}")
                if alert != "Normal":
                    self.logger.warning(f"ALERT: {alert}")
                    self._send_push_notification(alert)

            except Exception as e:
                self.logger.error(f"Error during breathing monitoring: {e}")
                self.cleanup()
                self.logger.info("Waiting for device to reconnect...")
                time.sleep(5)

    def cleanup(self):
        self.logger.info("Cleaning up resources...")
        if self.client:
            try:
                self.client.stop_session()
            except Exception as e:
                self.logger.error(f"Error stopping client session: {e}")
        self.client = None
        if self.conn:
            try:
                self.conn.close()
            except Exception as e:
                self.logger.error(f"Error closing connection: {e}")
        self.conn = None

if __name__ == "__main__":
    monitoring_service = RespiratoryMonitoring(push_notification_url="http://example.com/notify")
    monitoring_service.start_server()
