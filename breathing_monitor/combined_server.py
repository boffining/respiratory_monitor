import socket
import struct
import threading
import time
import io
import numpy as np
import logging
import json
from picamera2 import Picamera2
import acconeer.exptool.clients.json.client as acc
import acconeer.exptool.configs.configs as configs
from scipy.signal import butter, lfilter, savgol_filter
from scipy.fft import fft, ifft
from pykalman import KalmanFilter

class CombinedServer:
    def __init__(self, 
                 host="0.0.0.0", 
                 video_port=9999, 
                 data_port=32345, 
                 resolution=(1280, 720), 
                 framerate=60,
                 range_start=0.2, 
                 range_end=0.5, 
                 update_rate=30):
        
        # Server configuration
        self.host = host
        self.video_port = video_port
        self.data_port = data_port
        
        # Video configuration
        self.resolution = resolution
        self.framerate = framerate
        self.camera = None
        
        # Breathing monitoring configuration
        self.range_start = range_start
        self.range_end = range_end
        self.update_rate = update_rate
        self.radar_client = None
        
        # Server sockets
        self.video_server_socket = None
        self.data_server_socket = None
        
        # Client connections
        self.video_clients = []
        self.data_clients = []
        
        # Breathing data buffer
        self.waveform_buffer = []
        self.max_buffer_size = 300
        
        # Thread control
        self.is_running = True
        
        # Setup logging
        self._setup_logger()
        
    def _setup_logger(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger("CombinedServer")
        
    def start_camera(self):
        self.logger.info("Initializing the camera...")
        self.camera = Picamera2()
        video_config = self.camera.create_video_configuration(
            main={"size": self.resolution},
            controls={"FrameRate": self.framerate}
        )
        self.camera.configure(video_config)
        self.camera.start()
        self.logger.info(f"Camera started with resolution {self.resolution} at {self.framerate} FPS.")
        
    def _setup_radar_client(self):
        self.logger.info("Setting up Acconeer radar client...")
        try:
            client = acc.Client("192.168.50.175")  # Replace with your radar IP if different
            config = configs.IQServiceConfig()
            config.range_interval = [self.range_start, self.range_end]
            config.update_rate = self.update_rate
            config.gain = 0.5
            self.radar_client = client.setup_session(config)
            self.radar_client.start_session()
            self.logger.info("Radar client started successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to setup radar client: {e}")
            return False
            
    def _create_filter(self, filter_type, cutoff, fs, order=5):
        nyquist = 0.5 * fs
        normal_cutoff = cutoff / nyquist
        b, a = butter(order, normal_cutoff, btype=filter_type, analog=False)
        return b, a

    def _apply_filter(self, data, b, a):
        return lfilter(b, a, data)

    def _apply_kalman_filter(self, data):
        kalman_filter = KalmanFilter(initial_state_mean=0, n_dim_obs=1)
        kalman_filter = kalman_filter.em(np.zeros((100, 1)), n_iter=5)
        filtered_state_means, _ = kalman_filter.filter(data)
        return filtered_state_means.flatten()

    def _apply_savgol_filter(self, data, window_length=11, polyorder=3):
        return savgol_filter(data, window_length, polyorder)

    def _apply_fft_denoising(self, data, threshold=0.1):
        freq_data = fft(data)
        magnitude = np.abs(freq_data)
        freq_data[magnitude < threshold * np.max(magnitude)] = 0
        return np.real(ifft(freq_data))
        
    def process_breathing_data(self):
        if not self._setup_radar_client():
            self.logger.error("Failed to start radar client. Breathing monitoring will not be available.")
            return
            
        self.logger.info("Starting breathing data processing...")
        
        try:
            while self.is_running:
                # Get data from radar
                info, sweep = self.radar_client.get_next()
                raw_waveform = np.array(sweep)
                
                # Process the waveform
                high_pass_filter = self._create_filter('high', 0.5, self.update_rate)
                low_pass_filter = self._create_filter('low', 2.5, self.update_rate)
                
                high_passed = self._apply_filter(raw_waveform, *high_pass_filter)
                low_passed = self._apply_filter(high_passed, *low_pass_filter)
                kalman_filtered = self._apply_kalman_filter(low_passed)
                savgol_filtered = self._apply_savgol_filter(kalman_filtered)
                cleaned_waveform = self._apply_fft_denoising(savgol_filtered)
                
                # Analyze the waveform
                motion_state = "Child in motion" if np.std(cleaned_waveform) > 0.05 else "Stable breathing waveform"
                alert = "Child not moving" if np.max(np.abs(cleaned_waveform)) < 0.02 else "Normal"
                
                # Update the buffer
                self.waveform_buffer.append({
                    "timestamp": time.time(),
                    "waveform": cleaned_waveform.tolist(),
                    "motion_state": motion_state,
                    "alert": alert
                })
                
                # Keep buffer size limited
                if len(self.waveform_buffer) > self.max_buffer_size:
                    self.waveform_buffer.pop(0)
                
                # Send data to all connected clients
                self.send_breathing_data_to_clients()
                
                # Small delay to prevent CPU overload
                time.sleep(0.01)
                
        except Exception as e:
            self.logger.error(f"Error in breathing data processing: {e}")
        finally:
            if self.radar_client:
                try:
                    self.radar_client.stop_session()
                except Exception as e:
                    self.logger.error(f"Error stopping radar client: {e}")
    
    def send_breathing_data_to_clients(self):
        if not self.waveform_buffer or not self.data_clients:
            return
            
        # Get the latest data
        latest_data = self.waveform_buffer[-1]
        
        # Prepare the data packet
        data_packet = {
            "timestamp": latest_data["timestamp"],
            "motion_state": latest_data["motion_state"],
            "alert": latest_data["alert"],
            "waveform": latest_data["waveform"]
        }
        
        # Convert to JSON
        json_data = json.dumps(data_packet).encode('utf-8')
        
        # Send to all connected clients
        disconnected_clients = []
        for client in self.data_clients:
            try:
                # Send data size first
                client.sendall(struct.pack('!I', len(json_data)))
                # Then send the data
                client.sendall(json_data)
            except (BrokenPipeError, ConnectionResetError):
                disconnected_clients.append(client)
            except Exception as e:
                self.logger.error(f"Error sending data to client: {e}")
                disconnected_clients.append(client)
                
        # Remove disconnected clients
        for client in disconnected_clients:
            if client in self.data_clients:
                self.data_clients.remove(client)
                try:
                    client.close()
                except:
                    pass
                self.logger.info(f"Removed disconnected client. Active data clients: {len(self.data_clients)}")
    
    def capture_and_stream_video(self):
        self.logger.info("Starting video capture and streaming...")
        
        try:
            stream = io.BytesIO()
            while self.is_running:
                if not self.video_clients:
                    time.sleep(0.1)  # Don't waste resources if no clients
                    continue
                    
                # Capture frame
                stream.seek(0)
                self.camera.capture_file(stream, format="jpeg", quality=95)
                frame_data = stream.getvalue()
                frame_size = len(frame_data)
                
                # Send to all connected clients
                disconnected_clients = []
                for client in self.video_clients:
                    try:
                        # Send frame size first
                        client.sendall(struct.pack(">L", frame_size))
                        # Then send the frame data
                        client.sendall(frame_data)
                    except (BrokenPipeError, ConnectionResetError):
                        disconnected_clients.append(client)
                    except Exception as e:
                        self.logger.error(f"Error sending video to client: {e}")
                        disconnected_clients.append(client)
                
                # Remove disconnected clients
                for client in disconnected_clients:
                    if client in self.video_clients:
                        self.video_clients.remove(client)
                        try:
                            client.close()
                        except:
                            pass
                        self.logger.info(f"Removed disconnected client. Active video clients: {len(self.video_clients)}")
                
                # Small delay to prevent CPU overload
                time.sleep(0.01)
                
        except Exception as e:
            self.logger.error(f"Error in video streaming: {e}")
    
    def handle_video_client(self, client_socket):
        self.logger.info(f"New video client connected: {client_socket.getpeername()}")
        self.video_clients.append(client_socket)
    
    def handle_data_client(self, client_socket):
        self.logger.info(f"New data client connected: {client_socket.getpeername()}")
        self.data_clients.append(client_socket)
    
    def start_video_server(self):
        self.video_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.video_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.video_server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.video_server_socket.bind((self.host, self.video_port))
        self.video_server_socket.listen(5)
        self.logger.info(f"Video server started on {self.host}:{self.video_port}")
        
        while self.is_running:
            try:
                client_socket, _ = self.video_server_socket.accept()
                threading.Thread(target=self.handle_video_client, args=(client_socket,), daemon=True).start()
            except Exception as e:
                if self.is_running:  # Only log if not shutting down
                    self.logger.error(f"Error accepting video client: {e}")
    
    def start_data_server(self):
        self.data_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.data_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.data_server_socket.bind((self.host, self.data_port))
        self.data_server_socket.listen(5)
        self.logger.info(f"Data server started on {self.host}:{self.data_port}")
        
        while self.is_running:
            try:
                client_socket, _ = self.data_server_socket.accept()
                threading.Thread(target=self.handle_data_client, args=(client_socket,), daemon=True).start()
            except Exception as e:
                if self.is_running:  # Only log if not shutting down
                    self.logger.error(f"Error accepting data client: {e}")
    
    def start(self):
        self.logger.info("Starting combined server...")
        
        # Start camera
        self.start_camera()
        
        # Start server threads
        threading.Thread(target=self.start_video_server, daemon=True).start()
        threading.Thread(target=self.start_data_server, daemon=True).start()
        
        # Start data processing thread
        threading.Thread(target=self.process_breathing_data, daemon=True).start()
        
        # Start video streaming thread
        threading.Thread(target=self.capture_and_stream_video, daemon=True).start()
        
        self.logger.info("All services started successfully.")
        
        try:
            # Keep the main thread alive
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal.")
        finally:
            self.stop()
    
    def stop(self):
        self.logger.info("Shutting down combined server...")
        self.is_running = False
        
        # Close all client connections
        for client in self.video_clients + self.data_clients:
            try:
                client.close()
            except:
                pass
        
        # Close server sockets
        if self.video_server_socket:
            try:
                self.video_server_socket.close()
            except:
                pass
        
        if self.data_server_socket:
            try:
                self.data_server_socket.close()
            except:
                pass
        
        # Stop camera
        if self.camera:
            try:
                self.camera.stop()
            except:
                pass
        
        # Stop radar client
        if self.radar_client:
            try:
                self.radar_client.stop_session()
            except:
                pass
        
        self.logger.info("Server shutdown complete.")

if __name__ == "__main__":
    server = CombinedServer(
        host="0.0.0.0",  # Listen on all interfaces
        video_port=9999,
        data_port=32345,
        resolution=(1280, 720),  # HD resolution
        framerate=60,            # 60 FPS
        update_rate=30           # 30 Hz breathing data update rate
    )
    server.start()