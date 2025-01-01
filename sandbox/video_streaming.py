import cv2
import socket
import struct
import threading

class VideoStreaming:
    def __init__(self, host="192.168.50.175", port=9999, camera_index=0, width=1920, height=1080, fps=30):
        self.host = host  # Use the same IP as the breathing data script
        self.port = port  # Port for video streaming
        self.camera_index = camera_index  # Camera index for MIPI camera
        self.width = width
        self.height = height
        self.fps = fps
        self.server_socket = None
        self.camera = None
        self.connection = None

    def _setup_camera(self):
        """Initialize the MIPI camera on Raspberry Pi."""
        self.camera = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.camera.set(cv2.CAP_PROP_FPS, self.fps)
        if not self.camera.isOpened():
            raise RuntimeError("Failed to open camera. Ensure the camera is connected and configured.")

    def start_streaming(self):
        """Start the video streaming server."""
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
        """Stream video frames to the connected client."""
        try:
            while True:
                ret, frame = self.camera.read()
                if not ret:
                    break

                # Encode the frame as JPEG
                _, buffer = cv2.imencode('.jpg', frame)
                data = buffer.tobytes()
                size = len(data)

                # Send the size and frame data
                self.connection.sendall(struct.pack(">L", size) + data)
        except Exception as e:
            print(f"Error during streaming: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        if self.connection:
            self.connection.close()
        if self.camera:
            self.camera.release()
        if self.server_socket:
            self.server_socket.close()
        print("Resources cleaned up.")

if __name__ == "__main__":
    # Use the same IP as the breathing data script (e.g., 192.168.50.175)
    video_streamer = VideoStreaming(host="192.168.50.175", port=9999)
    video_streamer.start_streaming()
