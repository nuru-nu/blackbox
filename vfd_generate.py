"""Sends animated typing text to VFD.

Hardware description + ESP32 firmware:
https://github.com/BorisBegemann/Futaba-VFD

NOTE: You need the updated firmware with the UDP handler!
"""

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
    parser.add_argument('--start', default=(datetime.now() + timedelta(seconds=5)).strftime("%Y%m%d-%H%M%S"),
                        help='Start time for animation in YYYYMMDD-HHMMSS format (defaults to current time + 10 seconds)')
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

            # Print statistics for each text
            print_text_statistics(text_array)

            return text_array
    except Exception as e:
        print(f"Error loading text file: {e}")
        return [f"""Error loading text file: {e}"""]

def print_text_statistics(text_array):
    """Print statistics about each text in the array"""
    print("\n=== Text Statistics ===")
    print(f"Total texts: {len(text_array)}")

    total_seconds = 0
    for i, text in enumerate(text_array):
        # Count characters (excluding whitespace)
        char_count = sum(1 for c in text if not c.isspace())

        # Count words
        words = [w for w in text.split() if w]
        word_count = len(words)

        # Count paragraphs (text separated by newlines)
        paragraph_count = text.count('\n') + 1

        # Calculate reading metrics
        # Average reading speed is about 200-250 words per minute
        wpm = 200
        reading_time_minutes = word_count / wpm

        # Calculate typing metrics based on the VFDGenerator settings
        chars_per_second = 0
        if i == 0:
            hours = args.first_hours
        elif i == len(text_array) - 1:
            hours = args.last_hours
        else:
            hours = args.default_hours

        seconds = hours * 3600
        total_seconds += seconds
        chars_per_second = len(text) / (seconds * 0.9) if seconds > 0 else 0
        chars_per_minute = chars_per_second * 60
        words_per_minute = chars_per_minute / 5  # Assuming average word length of 5 chars

        print(f"\nText #{i}:")
        print(f"  Characters: {len(text)} ({char_count} non-whitespace)")
        print(f"  Words: {word_count}")
        print(f"  Paragraphs: {paragraph_count}")
        print(f"  Typing speed: {chars_per_minute:.1f} chars/min, {words_per_minute:.1f} words/min")
        print(f"  Reading time: {reading_time_minutes:.1f} minutes")
        print(f"  Display time: {hours:.1f} hours")

        # Print a preview of the text (first 50 chars)
        preview = text[:50].replace('\n', '\\n')
        if len(text) > 50:
            preview += "..."
        print(f"  Preview: \"{preview}\"")

    # Calculate and display start/end information
    try:
        start_datetime = datetime.strptime(args.start, "%Y%m%d-%H%M%S")
        current_datetime = datetime.now()

        # Calculate end time
        end_datetime = start_datetime + timedelta(seconds=total_seconds)

        # Determine which text we'll start with and at what position
        if current_datetime < start_datetime:
            print(f"\nAnimation will start at: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Animation will start with text #0 at position 0 (beginning)")
        else:
            # Calculate elapsed time and determine current position
            elapsed_seconds = (current_datetime - start_datetime).total_seconds()

            if elapsed_seconds >= total_seconds:
                print(f"\nStart time was in the past. Animation has already completed.")
            else:
                # Find which text we're in
                current_text_index = 0
                seconds_remaining = elapsed_seconds

                while current_text_index < len(text_array):
                    if current_text_index == 0:
                        text_seconds = args.first_hours * 3600
                    elif current_text_index == len(text_array) - 1:
                        text_seconds = args.last_hours * 3600
                    else:
                        text_seconds = args.default_hours * 3600

                    if seconds_remaining < text_seconds:
                        # We're in this text
                        fraction = seconds_remaining / text_seconds
                        char_position = int(len(text_array[current_text_index]) * fraction)
                        print(f"\nAnimation will start at: {current_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"Animation will start with text #{current_text_index} at approximately {fraction:.1%} through")
                        print(f"Estimated character position: {char_position} of {len(text_array[current_text_index])}")

                        # Show text that was just displayed and text that will be shown next
                        if char_position > 0:
                            context_before = text_array[current_text_index][max(0, char_position-50):char_position]
                            context_before = context_before.replace('\n', '\\n')
                            print(f"Text just displayed: \"...{context_before}\"")

                        context_after = text_array[current_text_index][char_position:char_position+50]
                        context_after = context_after.replace('\n', '\\n')
                        print(f"Text coming next: \"{context_after}...\"")
                        break

                    seconds_remaining -= text_seconds
                    current_text_index += 1

                    if current_text_index >= len(text_array):
                        # We've gone through all texts, must be a calculation error
                        print(f"\nStart time was in the past. Animation has already completed.")
                        break

        print(f"Animation end: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")

    except ValueError:
        print(f"\nInvalid start time format: {args.start}. Using format YYYYMMDD-HHMMSS")
        # Calculate end time based on current time
        end_time = datetime.now() + timedelta(seconds=total_seconds)
        print(f"Animation will start now and end at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

    print("=====================\n")

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

        # Parse start time
        self.start_time = None
        try:
            self.start_time = datetime.strptime(args.start, "%Y%m%d-%H%M%S")
        except ValueError:
            print(f"Invalid start time format: {args.start}. Using format YYYYMMDD-HHMMSS")
            self.start_time = datetime.now()  # Fallback to current time if format is invalid

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

        # Check if we need to fast forward based on start time
        current_datetime = datetime.now()
        if current_datetime < self.start_time:
            return

        if self.char_index == 0 and self.current_text_index == 0:
            # Calculate how much time has passed since the start time
            elapsed_seconds = (current_datetime - self.start_time).total_seconds()
            if elapsed_seconds > 0:
                self.fast_forward(elapsed_seconds)

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
                # All texts have been displayed, just keep the cursor blinking
                # Don't reset or restart - we're done typing
                self.char_index = len(self.current_text)  # Ensure we stay at the end

                # Keep the cursor at its final position
                # No need to reset text or positions

                # We'll still toggle the cursor in the toggle_cursor method
                # but won't type any more characters

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

            # Move to next character
            self.char_index += 1
            self.last_type_time = current_time

            # Look ahead for newline to apply longer pause before it
            if self.char_index < len(self.current_text) and self.current_text[self.char_index] == '\n':
                # Apply longer pause before newline (3x period pause)
                base_rate = self.chars_per_second[self.current_text_index]
                base_delay = 1.0 / base_rate if base_rate > 0 else 10.0
                variation = random.uniform(-0.1, 0.1)
                adjusted_delay = base_delay * (1 + variation)
                self.current_delay = adjusted_delay * 9.0  # 3x the period pause (which is 3.0)
            else:
                # Normal adjustment for other characters
                self.adjust_typing_speed(next_char)

    def adjust_typing_speed(self, current_char):
        """Adjust typing speed based on context for more realistic effect"""
        # Get base typing rate for current text
        base_rate = self.chars_per_second[self.current_text_index]
        base_delay = 1.0 / base_rate if base_rate > 0 else 10.0

        # Add small random variation (±10%)
        variation = random.uniform(-0.1, 0.1)
        adjusted_delay = base_delay * (1 + variation)

        # Adjust for specific characters
        if current_char == '\n':
            # Much longer pause before new paragraphs (3x longer than period)
            # With multiple newlines this makes the cursor blink on an empty line...
            self.current_delay = adjusted_delay * 9.0
            self.in_word = False
        elif current_char == '.':
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

            clock.tick(20)  # fps

        pygame.quit()
        sys.exit()

    def fast_forward(self, elapsed_seconds):
        """Fast forward the animation to the position it would be at after elapsed_seconds"""
        remaining_seconds = elapsed_seconds
        text_index = 0
        char_index = 0

        # Process each text in the array
        while text_index < len(TEXT_ARRAY) and remaining_seconds > 0:
            current_text = TEXT_ARRAY[text_index]
            # Get typing rate for this text
            char_rate = self.chars_per_second[text_index] if text_index < len(self.chars_per_second) else 0.1

            if char_rate <= 0:
                char_rate = 0.1  # Prevent division by zero

            # Calculate how many characters we can type in the remaining time
            # Account for average delay factor (approximation of the various pauses)
            avg_delay_factor = 1.5  # Average of all the delay factors
            chars_possible = int(remaining_seconds * char_rate / avg_delay_factor)

            if chars_possible >= len(current_text) - char_index:
                # We can complete this text, move to the next one
                chars_typed = len(current_text) - char_index
                time_used = (chars_typed * avg_delay_factor) / char_rate
                remaining_seconds -= time_used
                text_index += 1
                char_index = 0
            else:
                # We can only type part of this text
                char_index += chars_possible
                break

        # Set the current state to where we fast-forwarded to
        self.current_text_index = text_index
        if text_index < len(TEXT_ARRAY):
            self.current_text = TEXT_ARRAY[text_index]
            self.char_index = char_index

            # Simply set the cursor at the starting position and begin typing from char_index
            # No need to pre-render text or calculate scroll positions
            self.text = ""
            self.text_x = PADDING // SCALE_FACTOR
            self.cursor_x = PADDING // SCALE_FACTOR

            # Update typing rate for the current text
            if text_index < len(self.chars_per_second):
                base_rate = self.chars_per_second[text_index]
                self.current_delay = 1.0 / base_rate if base_rate > 0 else 10.0

if __name__ == "__main__":
    generator = VFDGenerator()
    generator.run()