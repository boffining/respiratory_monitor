# src/breathing_monitor/video_streaming.py

import cv2
import socket
import struct
import time

class VideoStreaming:
    def __init__(self, host="0.0.0.0", port=9999, camera_index=0, width=1920, height=1080, fps=30):
        self.host = host
        self.port = port
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self.server_socket = None
        self.camera = None
        self.connection, self.client_address = None, None

    def _setup_camera(self):
        self.camera = cv2.VideoCapture(self.camera_index)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.camera.set(cv2.CAP_PROP_FPS, self.fps)
        if not self.camera.isOpened():
            raise RuntimeError("Failed to open camera")

    def _setup_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        print(f"Video streaming server started on {self.host}:{self.port}")

    def _accept_connection(self):
        print("Waiting for a connection...")
        self.connection, self.client_address = self.server_socket.accept()
        print(f"Connection established with {self.client_address}")

    def stream_video(self):
        while True:
            try:
                self._setup_camera()
                self._setup_server()
                self._accept_connection()

                while True:
                    ret, frame = self.camera.read()
                    if not ret:
                        print("Failed to capture video frame")
                        break

                    # Encode frame to JPEG
                    _, encoded_frame = cv2.imencode('.jpg', frame)
                    data = encoded_frame.tobytes()

                    # Send frame size and data over the network
                    self.connection.sendall(struct.pack('>L', len(data)) + data)
            except Exception as e:
                print(f"Error during streaming: {e}")
                self.cleanup()
                print("Restarting video streaming service...")
                time.sleep(5)  # Wait before restarting
            finally:
                self.cleanup()

    def cleanup(self):
        print("Cleaning up resources...")
        if self.connection:
            try:
                self.connection.close()
            except Exception as e:
                print(f"Error closing connection: {e}")
        if self.camera:
            self.camera.release()
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception as e:
                print(f"Error closing server socket: {e}")
        print("Resources cleaned up.")

if __name__ == "__main__":
    video_streamer = VideoStreaming()
    video_streamer.stream_video()
