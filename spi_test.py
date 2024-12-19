import spidev

def test_spi(device):
    try:
        # Open the SPI device (bus 0, device `device`)
        spi = spidev.SpiDev()
        spi.open(0, device)  # Bus 0, Device 0 or 1
        spi.max_speed_hz = 500000  # Set SPI speed (500 kHz as a starting point)
        spi.mode = 0b00  # SPI mode 0

        # Send and receive data (example: send [0xAA, 0xBB], read back response)
        test_data = [0xAA, 0xBB]
        print(f"Sending test data to /dev/spidev0.{device}: {test_data}")
        response = spi.xfer2(test_data)
        print(f"Received response: {response}")

        # Close the SPI device
        spi.close()
    except FileNotFoundError:
        print(f"/dev/spidev0.{device} not found. Make sure SPI is enabled.")
    except Exception as e:
        print(f"Error communicating with /dev/spidev0.{device}: {e}")

if __name__ == "__main__":
    print("Testing SPI connection...")
    for dev in [0, 1]:  # Test both /dev/spidev0.0 and /dev/spidev0.1
        test_spi(dev)

