#!/usr/bin/env python3
# Main entry point for the respiratory monitor

import argparse
import logging
import sys
from breathing_monitor.combined_server import CombinedServer

def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('respiratory_monitor.log')
        ]
    )
    return logging.getLogger("main")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Respiratory Monitor')
    
    # Server configuration
    parser.add_argument('--host', type=str, default='0.0.0.0',
                        help='Host IP to bind the server to (default: 0.0.0.0)')
    parser.add_argument('--video-port', type=int, default=9999,
                        help='Port for video streaming (default: 9999)')
    parser.add_argument('--data-port', type=int, default=32345,
                        help='Port for breathing data (default: 32345)')
    
    # Video configuration
    parser.add_argument('--resolution', type=str, default='1280x720',
                        help='Video resolution in format WIDTHxHEIGHT (default: 1280x720)')
    parser.add_argument('--framerate', type=int, default=60,
                        help='Video framerate (default: 60)')
    
    # Breathing monitoring configuration
    parser.add_argument('--range-start', type=float, default=0.2,
                        help='Minimum detection range in meters (default: 0.2)')
    parser.add_argument('--range-end', type=float, default=0.5,
                        help='Maximum detection range in meters (default: 0.5)')
    parser.add_argument('--update-rate', type=int, default=30,
                        help='Breathing data update rate in Hz (default: 30)')
    
    return parser.parse_args()

def main():
    """Main entry point for the application."""
    logger = setup_logging()
    args = parse_arguments()
    
    # Parse resolution
    try:
        width, height = map(int, args.resolution.split('x'))
        resolution = (width, height)
    except ValueError:
        logger.error(f"Invalid resolution format: {args.resolution}. Using default 1280x720.")
        resolution = (1280, 720)
    
    logger.info("Starting Respiratory Monitor")
    logger.info(f"Video configuration: {resolution} at {args.framerate} FPS")
    logger.info(f"Breathing monitoring configuration: Range {args.range_start}-{args.range_end}m, Update rate: {args.update_rate}Hz")
    
    # Create and start the server
    server = CombinedServer(
        host=args.host,
        video_port=args.video_port,
        data_port=args.data_port,
        resolution=resolution,
        framerate=args.framerate,
        range_start=args.range_start,
        range_end=args.range_end,
        update_rate=args.update_rate
    )
    
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt. Shutting down...")
    except Exception as e:
        logger.error(f"Error during server execution: {e}")
    finally:
        server.stop()
        logger.info("Server stopped. Exiting.")

if __name__ == "__main__":
    main()