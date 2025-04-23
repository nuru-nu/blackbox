import pygame
import sys
import socket
import struct
import argparse

# Parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description='VFD Display')
    parser.add_argument('--ip', default='0.0.0.0', help='UDP listen IP address')
    parser.add_argument('--port', type=int, default=31337, help='UDP listen port')
    parser.add_argument('--scale', type=int, default=2, help='Display scale factor')
    return parser.parse_args()

# Get command line arguments
args = parse_args()

# Initialize Pygame
pygame.init()

# Constants for the display
SCALE_FACTOR = args.scale
ORIGINAL_WIDTH, ORIGINAL_HEIGHT = 336, 24
DISPLAY_WIDTH = ORIGINAL_WIDTH * SCALE_FACTOR
DISPLAY_HEIGHT = ORIGINAL_HEIGHT * SCALE_FACTOR

# VFD-like colors
VFD_BG_COLOR = (26, 26, 26)  # Dark VFD background
VFD_TEXT_COLOR = (0, 221, 221)  # Cyan-like color

# Network settings
UDP_IP = args.ip
UDP_PORT = args.port
BUFFER_SIZE = 1024  # Should be enough for our bitmap

class VFDDisplay:
    def __init__(self):
        # Create the display
        self.screen = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT))
        pygame.display.set_caption("VFD Display")

        # Set up UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((UDP_IP, UDP_PORT))
        self.sock.setblocking(False)  # Non-blocking mode

        # Create a surface for the bitmap
        self.bitmap_surface = pygame.Surface((ORIGINAL_WIDTH, ORIGINAL_HEIGHT))

        # Last received bitmap data
        self.bitmap_data = None

    def receive_bitmap(self):
        """Try to receive a bitmap from the UDP socket"""
        try:
            data, addr = self.sock.recvfrom(BUFFER_SIZE)
            self.bitmap_data = data
            return True
        except BlockingIOError:
            # No data available
            return False
        except Exception as e:
            print(f"Error receiving data: {e}")
            return False

    def render_bitmap(self):
        """Render the bitmap data to the surface"""
        if not self.bitmap_data:
            return

        # Clear the surface
        self.bitmap_surface.fill(VFD_BG_COLOR)

        # Process each byte in the bitmap
        for byte_index, byte in enumerate(self.bitmap_data):
            # Process each bit in the byte
            for bit_index in range(8):
                # Check if this bit is set
                if byte & (1 << (7 - bit_index)):
                    # Calculate the corresponding pixel position
                    pixel_index = byte_index * 8 + bit_index
                    x = pixel_index % ORIGINAL_WIDTH
                    y = pixel_index // ORIGINAL_WIDTH

                    # Make sure we're within bounds
                    if x < ORIGINAL_WIDTH and y < ORIGINAL_HEIGHT:
                        # Set the pixel
                        self.bitmap_surface.set_at((x, y), VFD_TEXT_COLOR)

    def draw(self):
        """Draw the bitmap to the screen, scaled up"""
        # Clear the screen
        self.screen.fill(VFD_BG_COLOR)

        # Scale and draw the bitmap surface
        scaled_surface = pygame.transform.scale(self.bitmap_surface, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
        self.screen.blit(scaled_surface, (0, 0))

        # Update the display
        pygame.display.flip()

    def run(self):
        """Main loop for the VFD display"""
        running = True
        clock = pygame.time.Clock()

        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False

            # Try to receive a new bitmap
            if self.receive_bitmap():
                # If we got a new bitmap, render it
                self.render_bitmap()

            # Draw the current bitmap
            self.draw()

            # Cap at 60 fps
            clock.tick(60)

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    display = VFDDisplay()
    display.run()