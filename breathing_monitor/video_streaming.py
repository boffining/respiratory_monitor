import socket
import struct
import threading
import io
from picamera2 import Picamera2

class ReliableVideoServer:
    def __init__(self, host="192.168.50.175", port=9999, resolution=(1920, 1080), framerate=30):
        self.host = host
        self.port = port
        self.resolution = resolution
        self.framerate = framerate
        self.camera = None
        self.is_running = True
        self.lock = threading.Lock()

    def start_camera(self):
        """Initialize and start the camera."""
        print("Initializing the camera...")
        self.camera = Picamera2()
        video_config = self.camera.create_video_configuration(
            main={"size": self.resolution},
            controls={
                "FrameRate": self.framerate,
                #"NoiseReductionMode": 0,
                #"Brightness": 0.5,
                #"Contrast": 1.0,
                #"Saturation": 1.0
            }
        )
        self.camera.configure(video_config)
        self.camera.start()
        print(f"Camera started with resolution {self.resolution} at {self.framerate} FPS.")

    def handle_client(self, client_socket):
        """Stream video frames to the connected client."""
        try:
            print(f"Client connected: {client_socket.getpeername()}")
            stream = io.BytesIO()
            while self.is_running:
                stream.seek(0)
                self.camera.capture_file(stream, format="jpeg")
                frame_data = stream.getvalue()
                frame_size = len(frame_data)

                # Send frame size and the frame data
                with self.lock:
                    client_socket.sendall(struct.pack(">L", frame_size) + frame_data)
        except (BrokenPipeError, ConnectionResetError):
            print("Client disconnected.")
        except Exception as e:
            print(f"Error during streaming: {e}")
        finally:
            with self.lock:
                client_socket.close()
                print("Connection closed. Waiting for new connection...")

    def start_server(self):
        """Start the video streaming server."""
        video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        video_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        video_socket.bind((self.host, self.port))
        video_socket.listen(1)
        print(f"Video server started on {self.host}:{self.port}. Waiting for connections...")

        self.start_camera()

        while self.is_running:
            try:
                client_socket, _ = video_socket.accept()
                threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()
            except Exception as e:
                print(f"Error accepting connection: {e}")
        video_socket.close()

    def stop(self):
        """Stop the server and clean up resources."""
        self.is_running = False
        if self.camera:
            self.camera.stop()
            print("Camera stopped.")

if __name__ == "__main__":
    server = ReliableVideoServer(host="192.168.50.175", port=9999, resolution=(1920, 1080), framerate=30)
    threading.Thread(target=server.start_server, daemon=True).start()

    try:
        while True:
            pass  # Keep the main thread running
    except KeyboardInterrupt:
        print("Shutting down server...")
        server.stop()
