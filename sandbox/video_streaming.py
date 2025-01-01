import cv2
import socket
import struct
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
        """Initialize the MIPI camera on Raspberry Pi."""
        print("Initializing the camera...")
        self.camera = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.camera.set(cv2.CAP_PROP_FPS, self.fps)
        if not self.camera.isOpened():
            raise RuntimeError("Failed to open camera. Ensure it is connected and configured properly.")

    def start_streaming(self):
        """Start the video streaming server."""
        try:
            print("Setting up the camera...")
            self._setup_camera()

            print("Setting up the server socket...")
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            print(f"Server socket created, bound, and listening on {self.host}:{self.port}")

            while True:
                print("Waiting for a connection...")
                try:
                    self.connection, client_address = self.server_socket.accept()
                    print(f"Connection established with {client_address}")
                    self._stream_video()
                except Exception as e:
                    print(f"Error accepting connection: {e}")
                    traceback.print_exc()
                finally:
                    if self.connection:
                        try:
                            self.connection.close()
                            print("Connection closed.")
                        except Exception as close_err:
                            print(f"Error closing connection: {close_err}")
        except Exception as e:
            print(f"Error in start_streaming: {e}")
            traceback.print_exc()
        finally:
            self.cleanup()

    def _stream_video(self):
        """Stream video frames to the connected client."""
        try:
            print("Starting video stream...")
            while True:
                # Read a frame from the camera
                ret, frame = self.camera.read()
                if not ret:
                    print("Failed to read frame from camera.")
                    break

                # Encode frame to JPEG
                _, buffer = cv2.imencode('.jpg', frame)
                data = buffer.tobytes()
                size = len(data)

                # Debug: Print the size of the frame being sent
                print(f"Frame size: {size} bytes")

                # Send frame size and data to the client
                try:
                    self.connection.sendall(struct.pack(">L", size) + data)
                except BrokenPipeError as e:
                    print(f"Client disconnected: {e}")
                    break
                except Exception as e:
                    print(f"Error during sendall: {e}")
                    traceback.print_exc()
                    break
        except Exception as e:
            print(f"Error in _stream_video: {e}")
            traceback.print_exc()
        finally:
            print("Exiting _stream_video.")
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        print("Cleaning up resources...")
        if self.connection:
            try:
                self.connection.close()
                print("Connection closed.")
            except Exception as e:
                print(f"Error closing connection: {e}")
        if self.camera:
            try:
                self.camera.release()
                print("Camera released.")
            except Exception as e:
                print(f"Error releasing camera: {e}")
        if self.server_socket:
            try:
                self.server_socket.close()
                print("Server socket closed.")
            except Exception as e:
                print(f"Error closing server socket: {e}")
        print("Resources cleaned up.")


if __name__ == "__main__":
    video_streamer = VideoStreaming(host="192.168.50.175", port=9999)
    video_streamer.start_streaming()
