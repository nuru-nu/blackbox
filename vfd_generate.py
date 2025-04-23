import pygame
import pygame.freetype
import sys
import time
import os
import socket
import struct
import argparse
import json
import random
from datetime import datetime, timedelta

# Parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description='VFD Generator')
    parser.add_argument('--ip', default='127.0.0.1', help='UDP destination IP address')
    parser.add_argument('--port', type=int, default=31337, help='UDP destination port')
    parser.add_argument('--font-size', type=int, default=12, help='Font size (before scaling)')
    parser.add_argument('--font', default='./KodeMono.ttf', help=
                        'Path to font file or name of system font (some examples: "Courier New", "Courier", '
                        '"Lucida Console", "Monaco" [12], "DejaVu Sans Mono") ... '
                        'see `fc-list` or `pygame.font.get_fonts()`')
    parser.add_argument('--text', default='20250421_100208.json', help='Path to JSON file containing text array')
    parser.add_argument('--first-hours', type=float, default=24, help='Hours to spend on first text')
    parser.add_argument('--last-hours', type=float, default=24, help='Hours to spend on last text')
    parser.add_argument('--default-hours', type=float, default=24, help='Hours to spend on each text between first and last')
    return parser.parse_args()

# Get command line arguments
args = parse_args()

# Initialize Pygame
pygame.init()

# Constants for the display
SCALE_FACTOR = 2
ORIGINAL_WIDTH, ORIGINAL_HEIGHT = 336, 24
DISPLAY_WIDTH = ORIGINAL_WIDTH * SCALE_FACTOR
DISPLAY_HEIGHT = ORIGINAL_HEIGHT * SCALE_FACTOR
PADDING = 8 * SCALE_FACTOR
FONT_SIZE = args.font_size * SCALE_FACTOR
# Scale cursor with font size
BASE_CURSOR_WIDTH = 10
BASE_CURSOR_HEIGHT = 18
CURSOR_WIDTH = int(BASE_CURSOR_WIDTH * (args.font_size / 18) * SCALE_FACTOR)
CURSOR_HEIGHT = int(BASE_CURSOR_HEIGHT * (args.font_size / 18) * SCALE_FACTOR)
CHARS_PER_MINUTE = 250
DELAY = 60 / CHARS_PER_MINUTE  # Delay in seconds
# Add variation to typing speed
WORD_BURST_FACTOR = 0.7  # Type words faster (lower delay)
PERIOD_PAUSE = 1.2  # Longer pause after periods
COMMA_PAUSE = 0.8  # Pause after commas
RANDOM_VARIATION = 0.2  # Random variation in typing speed

# VFD-like colors
VFD_BG_COLOR = (26, 26, 26)  # Dark VFD background
VFD_TEXT_COLOR = (0, 221, 221)  # Cyan-like color
GRID_COLOR = (50, 50, 50, 75)  # Grid line color with transparency

# Network settings
UDP_IP = args.ip
UDP_PORT = args.port

# Load text from JSON file
def load_text_from_json(file_path):
    try:
        with open(file_path, 'r') as f:
            text_array = json.load(f)
            if not isinstance(text_array, list):
                print(f"Error: JSON file should contain an array of strings")
                return ["""Error loading text. JSON file should contain an array of strings."""]
            return text_array
    except Exception as e:
        print(f"Error loading text file: {e}")
        return [f"""Error loading text file: {e}"""]

# Load the text array
TEXT_ARRAY = load_text_from_json(args.text)

class VFDGenerator:
    def __init__(self):
        # Create a hidden surface for rendering
        self.surface = pygame.Surface((ORIGINAL_WIDTH, ORIGINAL_HEIGHT))

        # Set up UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Set up font
        self.font = self.load_font()

        # Set font rendering mode to mono for crisp text on monochrome display
        self.font.antialiased = False
        self.font.origin = True

        # Initialize text properties
        self.text = ""
        self.char_index = 0
        self.cursor_x = PADDING // SCALE_FACTOR
        self.text_x = PADDING // SCALE_FACTOR
        self.last_type_time = 0
        self.cursor_visible = True
        self.cursor_last_toggle = 0

        # Text array management
        self.current_text_index = 0
        self.current_text = TEXT_ARRAY[0] if TEXT_ARRAY else ""

        # Timing management
        self.setup_timing()

        # Add variables for realistic typing
        self.in_word = False

        # Set up the grid texture
        self.grid_texture = self.create_grid_texture()

        # Initialize random seed with current time for consistent but varied typing
        random.seed(int(time.time()))

    def load_font(self):
        """Load the specified font or try to find a suitable default"""
        # If user specified a font, try to load it
        if args.font:
            try:
                if os.path.exists(args.font):
                    # Load from file path
                    return pygame.freetype.Font(args.font, FONT_SIZE // SCALE_FACTOR)
                else:
                    # Try as system font name
                    return pygame.freetype.SysFont(args.font, FONT_SIZE // SCALE_FACTOR)
            except:
                print(f"Could not load font: {args.font}")
                # Fall through to defaults

        # Try other good monospace fonts
        for font_name in ["Courier New", "Courier", "Lucida Console", "Monaco", "DejaVu Sans Mono"]:
            try:
                return pygame.freetype.SysFont(font_name, FONT_SIZE // SCALE_FACTOR)
            except:
                pass

        # Last resort - system monospace
        return pygame.freetype.SysFont("monospace", FONT_SIZE // SCALE_FACTOR)

    def create_grid_texture(self):
        """Create a semi-transparent grid texture for the VFD background"""
        grid_size = 8
        texture = pygame.Surface((ORIGINAL_WIDTH, ORIGINAL_HEIGHT), pygame.SRCALPHA)

        # Draw vertical lines
        for x in range(0, ORIGINAL_WIDTH, grid_size):
            pygame.draw.line(texture, GRID_COLOR, (x, 0), (x, ORIGINAL_HEIGHT), 1)

        # Draw horizontal lines
        for y in range(0, ORIGINAL_HEIGHT, grid_size):
            pygame.draw.line(texture, GRID_COLOR, (0, y), (ORIGINAL_WIDTH, y), 1)

        return texture

    def toggle_cursor(self):
        """Toggle cursor visibility for blinking effect"""
        current_time = time.time()
        if current_time - self.cursor_last_toggle >= 0.5:  # Toggle every 0.5 seconds
            self.cursor_visible = not self.cursor_visible
            self.cursor_last_toggle = current_time

    def setup_timing(self):
        """Calculate typing speeds based on text lengths and time allocations"""
        if not TEXT_ARRAY:
            self.chars_per_second = 0
            return

        # Calculate total characters and time allocation for each text
        text_times = []
        text_chars = []

        for i, text in enumerate(TEXT_ARRAY):
            chars = len(text)
            text_chars.append(chars)

            # Determine hours for this text
            if i == 0:
                hours = args.first_hours
            elif i == len(TEXT_ARRAY) - 1:
                hours = args.last_hours
            else:
                hours = args.default_hours

            text_times.append(hours * 3600)  # Convert hours to seconds

        # Calculate characters per second for each text
        self.chars_per_second = []
        for chars, seconds in zip(text_chars, text_times):
            if seconds > 0 and chars > 0:
                # Leave some buffer for pauses and variations
                self.chars_per_second.append(chars / (seconds * 0.9))
            else:
                self.chars_per_second.append(0.1)  # Default slow rate

        # Initialize current typing rate
        self.current_delay = 1.0 / self.chars_per_second[0] if self.chars_per_second[0] > 0 else 10.0

    def type_character(self):
        """Type the next character if enough time has passed"""
        current_time = time.time()

        # Check if we need to move to the next text
        if self.char_index >= len(self.current_text):
            self.current_text_index += 1
            if self.current_text_index < len(TEXT_ARRAY):
                self.current_text = TEXT_ARRAY[self.current_text_index]
                self.char_index = 0
                self.text = ""
                self.text_x = PADDING // SCALE_FACTOR
                self.cursor_x = PADDING // SCALE_FACTOR
                self.in_word = False

                # Update typing rate for the new text
                if self.current_text_index < len(self.chars_per_second):
                    base_rate = self.chars_per_second[self.current_text_index]
                    self.current_delay = 1.0 / base_rate if base_rate > 0 else 10.0
            else:
                # All texts have been displayed, restart from the beginning
                self.current_text_index = 0
                self.current_text = TEXT_ARRAY[0] if TEXT_ARRAY else ""
                self.char_index = 0
                self.text = ""
                self.text_x = PADDING // SCALE_FACTOR
                self.cursor_x = PADDING // SCALE_FACTOR
                self.in_word = False

                # Reset to first text typing rate
                if self.chars_per_second:
                    base_rate = self.chars_per_second[0]
                    self.current_delay = 1.0 / base_rate if base_rate > 0 else 10.0

        if current_time - self.last_type_time >= self.current_delay and self.char_index < len(self.current_text):
            next_char = self.current_text[self.char_index]

            # Check for newline character
            if next_char == '\n':
                # Clear text and reset positions
                self.text = ""
                self.text_x = PADDING // SCALE_FACTOR
                self.cursor_x = PADDING // SCALE_FACTOR
                self.in_word = False
            else:
                # Add character to text
                self.text += next_char

                # Calculate text width
                text_rect = self.font.get_rect(self.text)
                text_width = text_rect.width

                # Update cursor position
                self.cursor_x = PADDING // SCALE_FACTOR + text_width

                # Handle scrolling if text exceeds display width
                if self.cursor_x + (CURSOR_WIDTH // SCALE_FACTOR) > ORIGINAL_WIDTH - (PADDING // SCALE_FACTOR):
                    scroll_offset_cursor = ORIGINAL_WIDTH - (PADDING // SCALE_FACTOR) - (CURSOR_WIDTH // SCALE_FACTOR)
                    scroll_offset_text = scroll_offset_cursor - text_width
                    self.text_x = scroll_offset_text
                    self.cursor_x = scroll_offset_cursor
                else:
                    # Reset text position if not scrolling and not already scrolled
                    if self.text_x >= PADDING // SCALE_FACTOR:
                        self.text_x = PADDING // SCALE_FACTOR

            # Adjust typing speed based on context
            self.adjust_typing_speed(next_char)

            # Move to next character
            self.char_index += 1
            self.last_type_time = current_time

    def adjust_typing_speed(self, current_char):
        """Adjust typing speed based on context for more realistic effect"""
        # Get base typing rate for current text
        base_rate = self.chars_per_second[self.current_text_index]
        base_delay = 1.0 / base_rate if base_rate > 0 else 10.0

        # Add small random variation (±10%)
        variation = random.uniform(-0.1, 0.1)
        adjusted_delay = base_delay * (1 + variation)

        # Adjust for specific characters
        if current_char == '.':
            # Longer pause after periods
            self.current_delay = adjusted_delay * 3.0
            self.in_word = False
        elif current_char == ',':
            # Medium pause after commas
            self.current_delay = adjusted_delay * 2.0
            self.in_word = False
        elif current_char == ' ':
            # Slight pause between words
            self.current_delay = adjusted_delay * 1.2
            self.in_word = False
        else:
            # Characters within words are typed slightly faster
            if self.in_word:
                self.current_delay = adjusted_delay * 0.9
            else:
                self.current_delay = adjusted_delay
                self.in_word = True

    def render_frame(self):
        """Render the current frame to the surface"""
        # Draw VFD background
        self.surface.fill(VFD_BG_COLOR)

        # Draw grid texture
        self.surface.blit(self.grid_texture, (0, 0))

        # Draw text
        if self.text:
            # Use STYLE_DEFAULT for monochrome rendering
            text_surf, text_rect = self.font.render(self.text, VFD_TEXT_COLOR, style=pygame.freetype.STYLE_DEFAULT)
            text_rect.topleft = (self.text_x, (ORIGINAL_HEIGHT - text_rect.height) // 2)
            self.surface.blit(text_surf, text_rect)

        # Draw cursor (if visible)
        if self.cursor_visible:
            cursor_y = (ORIGINAL_HEIGHT - (CURSOR_HEIGHT // SCALE_FACTOR)) // 2
            pygame.draw.rect(self.surface, VFD_TEXT_COLOR,
                            (self.cursor_x, cursor_y,
                             CURSOR_WIDTH // SCALE_FACTOR,
                             CURSOR_HEIGHT // SCALE_FACTOR))

    def convert_to_bitmap(self):
        """Convert the surface to a 1-bit bitmap (336x24 = 8064 bits = 1008 bytes)"""
        # Calculate the number of bytes needed
        num_bytes = (ORIGINAL_WIDTH * ORIGINAL_HEIGHT + 7) // 8
        bitmap = bytearray(num_bytes)

        # Process each pixel
        for y in range(ORIGINAL_HEIGHT):
            for x in range(ORIGINAL_WIDTH):
                # Get pixel color
                pixel = self.surface.get_at((x, y))

                # Check if pixel is "on" (non-black)
                # Use a higher threshold to avoid background pixels being detected as "on"
                is_on = pixel[0] > 50 or pixel[1] > 50 or pixel[2] > 50

                if is_on:
                    # Calculate position in the bitmap
                    pixel_index = y * ORIGINAL_WIDTH + x
                    byte_index = pixel_index // 8
                    bit_index = pixel_index % 8

                    # Set the corresponding bit
                    bitmap[byte_index] |= (1 << (7 - bit_index))

        return bitmap

    def send_frame(self):
        """Send the current frame over UDP"""
        bitmap = self.convert_to_bitmap()
        self.sock.sendto(bitmap, (UDP_IP, UDP_PORT))

    def run(self):
        """Main loop for generating and sending frames"""
        running = True
        clock = pygame.time.Clock()

        while running:
            # Handle events (just for quitting)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False

            # Type characters
            self.type_character()

            # Toggle cursor for blinking effect
            self.toggle_cursor()

            # Render the frame
            self.render_frame()

            # Send the frame
            self.send_frame()

            # Cap at 60 fps
            clock.tick(60)

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    generator = VFDGenerator()
    generator.run()