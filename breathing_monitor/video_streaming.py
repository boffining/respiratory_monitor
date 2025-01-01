import socket
import struct
from picamera2 import Picamera2
import io
import threading

class TCPVideoServer:
    def __init__(self, host="192.168.50.175", port=9999, resolution=(720, 1280), framerate=60):
        self.host = host
        self.port = port
        self.resolution = resolution
        self.framerate = framerate
        self.server_socket = None
        self.camera = None
        self.is_running = True

    def start_camera(self):
        print("Initializing the camera...")
        self.camera = Picamera2()
        video_config = self.camera.create_video_configuration(
            main={"size": self.resolution},
            controls={"FrameRate": self.framerate}
        )
        self.camera.configure(video_config)
        self.camera.start()
        print(f"Camera started with resolution {self.resolution} at {self.framerate} FPS.")

    def handle_client(self, client_socket):
        try:
            print(f"Client connected: {client_socket.getpeername()}")
            stream = io.BytesIO()
            while self.is_running:
                stream.seek(0)
                # Capture a JPEG frame
                self.camera.capture_file(stream, format="jpeg")
                frame_data = stream.getvalue()
                frame_size = len(frame_data)

                # Send frame size and the frame data
                client_socket.sendall(struct.pack(">L", frame_size) + frame_data)
        except (BrokenPipeError, ConnectionResetError):
            print("Client disconnected.")
        except Exception as e:
            print(f"Error during streaming: {e}")
        finally:
            client_socket.close()
            print("Connection closed.")

    def start_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        print(f"Server started on {self.host}:{self.port}. Waiting for connections...")

        self.start_camera()

        try:
            while self.is_running:
                client_socket, _ = self.server_socket.accept()
                threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()
        except KeyboardInterrupt:
            print("Server shutting down.")
        finally:
            self.stop()

    def stop(self):
        self.is_running = False
        if self.camera:
            self.camera.stop()
            print("Camera stopped.")
        if self.server_socket:
            self.server_socket.close()
            print("Server socket closed.")

if __name__ == "__main__":
    video_server = TCPVideoServer(host="192.168.50.175", port=9999, resolution=(720, 1280), framerate=60)
    video_server.start_server()
