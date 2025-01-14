    #TODO: Add imports for these if you want to use them.
    
    
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