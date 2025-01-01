import socket
import struct
import traceback
from picamera2 import Picamera2, MappedArray
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
import io


class VideoStreaming:
    def __init__(self, host="192.168.50.175", port=9999, width=640, height=480, fps=30):
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.fps = fps
        self.server_socket = None
        self.connection = None
        self.camera = None

    def _setup_camera(self):
        """Initialize the Raspberry Pi camera using picamera2."""
        print("Initializing the camera...")
        self.camera = Picamera2()
        video_config = self.camera.create_video_configuration(main={"size": (self.width, self.height)})
        self.camera.configure(video_config)
        print(f"Camera configured for resolution {self.width}x{self.height} at {self.fps} FPS.")
        self.camera.start()

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
            with io.BytesIO() as output_buffer:
                while True:
                    # Capture JPEG image directly to an in-memory buffer
                    self.camera.capture_file(output_buffer, format="jpeg")
                    data = output_buffer.getvalue()
                    size = len(data)

                    # Debug: Print the size of the frame being sent
                    print(f"Frame size: {size} bytes")

                    # Send frame size and data to the client
                    try:
                        self.connection.sendall(struct.pack(">L", size) + data)
                        output_buffer.seek(0)
                        output_buffer.truncate()
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
                self.camera.stop()
                print("Camera stopped.")
            except Exception as e:
                print(f"Error stopping camera: {e}")
        if self.server_socket:
            try:
                self.server_socket.close()
                print("Server socket closed.")
            except Exception as e:
                print(f"Error closing server socket: {e}")
        print("Resources cleaned up.")


if __name__ == "__main__":
    # Use the same IP as the breathing data script (e.g., 192.168.50.175)
    video_streamer = VideoStreaming(host="192.168.50.175", port=9999, width=640, height=480, fps=30)
    video_streamer.start_streaming()
