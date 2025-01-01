import cv2
import socket
import struct
import threading
import traceback

class VideoStreaming:
    def __init__(self, host="192.168.50.175", port=9999, camera_index=0, width=1920, height=1080, fps=30):
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
        print("Initializing camera...")
        self.camera = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.camera.set(cv2.CAP_PROP_FPS, self.fps)
        if not self.camera.isOpened():
            raise RuntimeError("Failed to open camera. Ensure it is connected and configured properly.")

    def start_streaming(self):
        """Start the video streaming server."""
        try:
            self._setup_camera()
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            print(f"Streaming server started on {self.host}:{self.port}")

            while True:
                print("Waiting for a connection...")
                self.connection, client_address = self.server_socket.accept()
                print(f"Connection established with {client_address}")
                self._stream_video()
        except Exception as e:
            print(f"Error in start_streaming: {e}")
            traceback.print_exc()
        finally:
            self.cleanup()

    def _stream_video(self):
        """Stream video frames to the connected client."""
        try:
            while True:
                ret, frame = self.camera.read()
                if not ret:
                    print("Failed to read frame from camera.")
                    break

                # Encode frame as JPEG
                _, buffer = cv2.imencode('.jpg', frame)
                data = buffer.tobytes()
                size = len(data)

                # Send frame size and data
                self.connection.sendall(struct.pack(">L", size) + data)
        except Exception as e:
            print(f"Error during streaming: {e}")
            traceback.print_exc()
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        print("Cleaning up resources...")
        if self.connection:
            try:
                self.connection.close()
            except Exception as e:
                print(f"Error closing connection: {e}")
        if self.camera:
            try:
                self.camera.release()
            except Exception as e:
                print(f"Error releasing camera: {e}")
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception as e:
                print(f"Error closing server socket: {e}")
        print("Resources cleaned up.")

if __name__ == "__main__":
    video_streamer = VideoStreaming(host="192.168.50.175", port=9999)
    video_streamer.start_streaming()
