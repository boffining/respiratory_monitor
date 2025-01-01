import cv2
import socket
import struct
import threading

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
        self.connection = None

    def _setup_camera(self):
        self.camera = cv2.VideoCapture(self.camera_index)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.camera.set(cv2.CAP_PROP_FPS, self.fps)
        if not self.camera.isOpened():
            raise RuntimeError("Failed to open camera")

    def start_streaming(self):
        self._setup_camera()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        print(f"Streaming server started on {self.host}:{self.port}")

        while True:
            print("Waiting for a connection...")
            self.connection, client_address = self.server_socket.accept()
            print(f"Connection from {client_address}")
            threading.Thread(target=self._stream_video).start()

    def _stream_video(self):
        try:
            while True:
                ret, frame = self.camera.read()
                if not ret:
                    break

                _, buffer = cv2.imencode('.jpg', frame)
                data = buffer.tobytes()
                size = len(data)
                self.connection.sendall(struct.pack(">L", size) + data)
        except Exception as e:
            print(f"Error during streaming: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        if self.connection:
            self.connection.close()
        if self.camera:
            self.camera.release()
        print("Cleaned up resources.")
