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
import argparse
import json
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
    # Default start time slightly in the future for easier testing
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
WAITING_MESSAGE = ""

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
                print(f"Error: JSON file '{file_path}' should contain an array of strings")
                return [f"""Error loading text. JSON file '{file_path}' should contain an array of strings."""]
            return text_array
    except FileNotFoundError:
        print(f"Error: Text file not found: {file_path}")
        return [f"""Error: Text file not found: {file_path}"""]
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON file: {e}")
        return [f"""Error decoding JSON file: {e}"""]
    except Exception as e:
        print(f"Error loading text file: {e}")
        return [f"""Error loading text file: {e}"""]

def print_text_statistics(text_array, start_datetime):
    """Print statistics about each text in the array and calculate timing"""
    print("\n=== Text Statistics & Timing ===")
    print(f"Total texts: {len(text_array)}")
    if not text_array:
        print("No texts loaded.")
        print("=====================\n")
        return [], 0.0 # Return empty timings and zero total duration

    text_durations = []
    total_duration_seconds = 0
    text_start_times = [] # Absolute datetime start for each text

    current_start_time = start_datetime

    for i, text in enumerate(text_array):
        # Count characters
        char_count = len(text)
        non_whitespace_count = sum(1 for c in text if not c.isspace())
        words = [w for w in text.split() if w]
        word_count = len(words)
        paragraph_count = text.count('\n') + 1

        # Determine hours for this text
        if len(text_array) == 1: # Special case: only one text
             hours = args.first_hours # Use first_hours if only one text exists
        elif i == 0:
            hours = args.first_hours
        elif i == len(text_array) - 1:
            hours = args.last_hours
        else:
            hours = args.default_hours

        seconds = hours * 3600
        text_durations.append(seconds)
        text_start_times.append(current_start_time)
        total_duration_seconds += seconds

        chars_per_second = char_count / seconds if seconds > 0 else 0
        chars_per_minute = chars_per_second * 60
        words_per_minute = chars_per_minute / 5  # Assuming average word length of 5 chars

        print(f"\nText #{i}:")
        print(f"  Characters: {char_count} ({non_whitespace_count} non-whitespace)")
        print(f"  Words: {word_count}")
        print(f"  Paragraphs: {paragraph_count}")
        print(f"  Allocated Time: {hours:.2f} hours ({seconds:.0f} seconds)")
        if seconds > 0:
            print(f"  Implied Speed: {chars_per_minute:.1f} chars/min, {words_per_minute:.1f} words/min")
        else:
            print(f"  Implied Speed: Infinite (duration is 0)")
        print(f"  Scheduled Start: {current_start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        preview = text[:50].replace('\n', '\\n')
        if len(text) > 50:
            preview += "..."
        print(f"  Preview: \"{preview}\"")

        # Update start time for the next text
        current_start_time += timedelta(seconds=seconds)

    end_datetime = start_datetime + timedelta(seconds=total_duration_seconds)
    print(f"\nOverall Animation:")
    print(f"  Start Time: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  End Time:   {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Total Duration: {total_duration_seconds / 3600:.2f} hours")

    # Determine which text we'll start with based on current time
    current_datetime = datetime.now()
    if current_datetime < start_datetime:
        print(f"\nStatus: Animation will start in the future.")
        print(f"        Waiting until {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"        Will start with text #0 at position 0.")
    else:
        elapsed_seconds = (current_datetime - start_datetime).total_seconds()
        if elapsed_seconds >= total_duration_seconds:
            print(f"\nStatus: Animation completed at {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}.")
            print(f"        Display will show the end of the last text.")
        else:
            # Find which text and position corresponds to the current time
            cumulative_seconds = 0
            start_text_index = -1
            start_char_index = -1
            start_fraction = 0.0

            for i in range(len(text_array)):
                text_duration = text_durations[i]
                if elapsed_seconds < cumulative_seconds + text_duration or i == len(text_array) - 1: # Check if within this text OR if it's the last text
                    start_text_index = i
                    time_into_text = elapsed_seconds - cumulative_seconds
                    current_text_len = len(text_array[i])

                    if text_duration > 0 and current_text_len > 0 :
                        start_fraction = max(0.0, min(1.0, time_into_text / text_duration))
                        start_char_index = int(current_text_len * start_fraction)
                         # Ensure char_index doesn't exceed length
                        start_char_index = min(start_char_index, current_text_len)
                    elif current_text_len > 0: # Duration is zero, but text has length -> show end
                         start_char_index = current_text_len
                         start_fraction = 1.0
                    else: # Zero length text or zero duration
                         start_char_index = 0
                         start_fraction = 0.0

                    print(f"\nStatus: Animation in progress.")
                    print(f"        Current Time: {current_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"        Should be displaying text #{start_text_index} at character {start_char_index} ({start_fraction:.1%})")

                    # Show context
                    context_before = text_array[start_text_index][max(0, start_char_index-50):start_char_index]
                    context_after = text_array[start_text_index][start_char_index:min(len(text_array[start_text_index]), start_char_index+50)]
                    print(f"        Context around target: \"...{context_before.replace(chr(10), '/')}<-CURSOR->{context_after.replace(chr(10), '/')}...\"")
                    break
                cumulative_seconds += text_duration

    print("=============================\n")
    return text_durations, total_duration_seconds

# Load the text array
TEXT_ARRAY = load_text_from_json(args.text)

# Parse start time AFTER loading text
start_datetime = None
try:
    start_datetime = datetime.strptime(args.start, "%Y%m%d-%H%M%S")
except ValueError:
    print(f"Error: Invalid start time format: {args.start}. Use YYYYMMDD-HHMMSS.")
    print("Using current time as fallback.")
    start_datetime = datetime.now()

# Calculate timings and print stats
TEXT_DURATIONS, TOTAL_DURATION_SECONDS = print_text_statistics(TEXT_ARRAY, start_datetime)


class VFDGenerator:
    def __init__(self):
        # Create a hidden surface for rendering
        self.surface = pygame.Surface((ORIGINAL_WIDTH, ORIGINAL_HEIGHT))

        # Set up UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Set up font
        self.font = self.load_font()
        self.font.antialiased = False # Better for monochrome? Test this.
        self.font.origin = True

        # Animation state variables
        self.current_text_index = 0
        self.char_index = 0         # Index of the *next* character to be potentially revealed
        self.current_text = ""      # The actual text currently being processed
        self.display_text = ""      # The text currently visible on the display line
        self.text_x = PADDING // SCALE_FACTOR # X position for drawing display_text
        self.cursor_x = PADDING // SCALE_FACTOR # X position for drawing cursor

        # Cursor blinking
        self.cursor_visible = True
        self.cursor_last_toggle = time.monotonic() # Use monotonic clock for intervals

        # Timing
        self.start_time = start_datetime
        self.text_durations = TEXT_DURATIONS
        self.total_duration_seconds = TOTAL_DURATION_SECONDS
        self.animation_finished = False

        # Set up the grid texture
        self.grid_texture = self.create_grid_texture()

        # Initialize state based on current time - NOW USES DIRECT CALCULATION
        self.initialize_state_directly()


    def load_font(self):
        """Load the specified font or try to find a suitable default"""
        font_to_load = args.font
        font_size_px = FONT_SIZE // SCALE_FACTOR
        try:
            if os.path.exists(font_to_load):
                print(f"Loading font from file: {font_to_load} ({font_size_px}px)")
                return pygame.freetype.Font(font_to_load, font_size_px)
            else:
                print(f"Loading system font: {font_to_load} ({font_size_px}px)")
                return pygame.freetype.SysFont(font_to_load, font_size_px)
        except Exception as e:
            print(f"Warning: Could not load specified font '{font_to_load}': {e}")

        # Fallback fonts
        for font_name in ["DejaVu Sans Mono", "Consolas", "Monaco", "Courier New", "Courier", "monospace"]:
            try:
                print(f"Trying fallback font: {font_name} ({font_size_px}px)")
                return pygame.freetype.SysFont(font_name, font_size_px)
            except Exception:
                continue # Try next font

        print("Error: No suitable monospace font found! Pygame default will be used.")
        return pygame.freetype.Font(None, font_size_px) # Pygame's default

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

    def calculate_target_state(self, elapsed_seconds):
        """Calculate the target text index and character index based on elapsed time."""
        if not TEXT_ARRAY or not self.text_durations:
            return 0, 0 # No text, stay at beginning

        # Handle edge case where elapsed time is negative (before start)
        if elapsed_seconds < 0:
             # Special case: if start time is slightly in the future due to rounding/init delay
             # treat it as exactly zero to avoid issues. Show state at time 0.
             elapsed_seconds = 0
             # return 0, 0 # Before start time


        cumulative_seconds = 0
        for i in range(len(TEXT_ARRAY)):
            text_duration = self.text_durations[i] if i < len(self.text_durations) else 0
            text_length = len(TEXT_ARRAY[i])

            # Check if the elapsed time falls within this text's duration OR
            # if it's the last text (handle overshoot) OR
            # if the duration is zero (instant text)
            is_last_text = (i == len(TEXT_ARRAY) - 1)
            time_at_text_end = cumulative_seconds + text_duration

            # Determine if time falls within this segment or beyond
            # Need <= for time_at_text_end check to correctly include the end point
            if elapsed_seconds <= time_at_text_end or is_last_text:
                if text_duration <= 0 and text_length > 0:
                    # If duration is zero or negative, show the whole text immediately
                    target_char_index = text_length
                elif text_length == 0:
                    target_char_index = 0 # No characters in this text
                else:
                    # Calculate position within this text
                    time_into_text = max(0, elapsed_seconds - cumulative_seconds)
                    # Prevent division by zero if text_duration is somehow <= 0 here but length > 0
                    fraction = min(1.0, time_into_text / text_duration) if text_duration > 0 else 1.0
                    target_char_index = int(text_length * fraction)
                    # Ensure index is within bounds [0, text_length]
                    target_char_index = max(0, min(text_length, target_char_index))

                # If time has exceeded total duration, clamp to the very end of the last text
                if elapsed_seconds >= self.total_duration_seconds and self.total_duration_seconds > 0:
                     last_text_index = len(TEXT_ARRAY) - 1
                     last_text_length = len(TEXT_ARRAY[last_text_index]) if last_text_index >= 0 else 0
                     return last_text_index, last_text_length

                return i, target_char_index # Return text index and char index

            cumulative_seconds += text_duration

        # Fallback: Should ideally be caught by the checks above, but just in case...
        # This usually means elapsed_seconds exceeds total duration.
        last_text_index = len(TEXT_ARRAY) - 1 if TEXT_ARRAY else 0
        last_text_length = len(TEXT_ARRAY[last_text_index]) if last_text_index >= 0 and TEXT_ARRAY else 0
        return last_text_index, last_text_length


    def _simulate_typing_step(self):
        """Simulates one step of typing: reveals one character or handles newline/end of text."""
        if self.animation_finished:
             return False # Nothing more to simulate

        # Check if we need to move to the next text *before* processing character
        if self.char_index >= len(self.current_text):
            # Move to the next text
            self.current_text_index += 1
            if self.current_text_index < len(TEXT_ARRAY):
                self.current_text = TEXT_ARRAY[self.current_text_index]
                self.char_index = 0
                # Reset display for the new text
                self.display_text = ""
                self.text_x = PADDING // SCALE_FACTOR
                self.cursor_x = PADDING // SCALE_FACTOR
                # Check if the new text is empty, if so, advance again immediately in next step
                if len(self.current_text) == 0:
                     # Don't process character this step, let next step handle transition again
                     return True # State potentially changed (index advanced)
            else:
                # Reached the end of all texts
                self.animation_finished = True
                # Keep cursor at the end of the last line
                # Ensure indices reflect the finished state
                self.current_text_index = len(TEXT_ARRAY) # Signal one past the last index
                self.char_index = 0
                return False # No more state changes possible

        # If we are finished after the index update, return false
        if self.animation_finished:
            return False

        # Ensure current_text_index is valid before accessing TEXT_ARRAY
        if self.current_text_index >= len(TEXT_ARRAY):
             print(f"Error: Tried to access text index {self.current_text_index} which is out of bounds.")
             self.animation_finished = True
             return False

        # Process the character at the current char_index
        # Ensure char_index is valid for current_text (can happen with empty texts)
        if self.char_index >= len(self.current_text):
             # This case handles empty texts correctly by advancing index in the next call
             # No character processing happens, but state did change (text index potentially)
             return True


        next_char = self.current_text[self.char_index]

        if next_char == '\n':
            # Newline: Clear display line, reset positions
            self.display_text = ""
            self.text_x = PADDING // SCALE_FACTOR
            self.cursor_x = PADDING // SCALE_FACTOR
        else:
            # Regular character: Add to display text and update positions/scrolling
            self.display_text += next_char

            # Calculate new text width and cursor position
            try:
                # Use get_rect for potentially more accurate width than render
                text_rect = self.font.get_rect(self.display_text)
                new_text_width = text_rect.width
            except pygame.error as e:
                 print(f"Warning: Pygame error getting rect for '{self.display_text}': {e}. Using width 0.")
                 new_text_width = 0

            new_cursor_x = PADDING // SCALE_FACTOR + new_text_width

            # --- Scrolling Logic ---
            available_width = ORIGINAL_WIDTH - (PADDING // SCALE_FACTOR) # Width available for text + cursor
            cursor_space = CURSOR_WIDTH // SCALE_FACTOR + (PADDING // SCALE_FACTOR) # Cursor width + right padding

            if new_cursor_x + cursor_space > ORIGINAL_WIDTH: # If cursor hits the right edge
                # Start scrolling: Cursor stays fixed, text moves left
                self.cursor_x = ORIGINAL_WIDTH - cursor_space
                self.text_x = self.cursor_x - new_text_width
            else:
                # Not scrolling (or finished scrolling back)
                self.cursor_x = new_cursor_x
                # Keep text anchored to the left padding unless scrolled
                # If text_x was negative (scrolled), keep it, otherwise reset to padding
                if self.text_x >= PADDING // SCALE_FACTOR:
                     self.text_x = PADDING // SCALE_FACTOR
                # Handle case where text fits entirely after scrolling ends
                elif self.text_x < PADDING // SCALE_FACTOR and new_cursor_x + cursor_space <= ORIGINAL_WIDTH:
                     self.text_x = PADDING // SCALE_FACTOR
                     self.cursor_x = PADDING // SCALE_FACTOR + new_text_width


        # Move to the next character index *after* processing the current one
        self.char_index += 1
        return True # Indicate state changed


    def initialize_state_directly(self):
        """Sets the initial animation state based on the current time using direct calculation."""
        print("Initializing display state directly...")
        current_datetime = datetime.now()
        elapsed_seconds = (current_datetime - self.start_time).total_seconds()

        # Calculate the target state based on current time
        target_text_index, target_char_index = self.calculate_target_state(elapsed_seconds)

        print(f"Target state: Text #{target_text_index}, Char #{target_char_index}")

        # Clamp target index if needed (e.g., if TEXT_ARRAY is empty)
        if not TEXT_ARRAY:
            target_text_index = 0
            target_char_index = 0
        else:
            target_text_index = max(0, min(len(TEXT_ARRAY) - 1, target_text_index))
            target_char_index = max(0, min(len(TEXT_ARRAY[target_text_index]), target_char_index))


        # Set the main state variables
        self.current_text_index = target_text_index
        self.char_index = target_char_index
        self.current_text = TEXT_ARRAY[self.current_text_index] if TEXT_ARRAY else ""
        self.animation_finished = (elapsed_seconds >= self.total_duration_seconds and self.total_duration_seconds > 0)

        # --- Direct Calculation of Visual State ---
        if not TEXT_ARRAY:
             self.display_text = ""
             self.text_x = PADDING // SCALE_FACTOR
             self.cursor_x = PADDING // SCALE_FACTOR
             print("Initialization complete (No text).")
             return

        current_full_text = self.current_text

        # Find the start of the current line based on the last newline before char_index
        last_newline_index = current_full_text.rfind('\n', 0, self.char_index)
        line_start_index = last_newline_index + 1

        # Extract the content of the line up to the target character
        self.display_text = current_full_text[line_start_index : self.char_index]

        # Calculate the width and positions based on this line content
        if not self.display_text:
            # If the line is empty (e.g., right after a newline or at char 0)
            self.text_x = PADDING // SCALE_FACTOR
            self.cursor_x = PADDING // SCALE_FACTOR
        else:
            try:
                 text_rect = self.font.get_rect(self.display_text)
                 current_line_width = text_rect.width
            except pygame.error as e:
                 print(f"Warning: Pygame error getting rect for '{self.display_text}' during init: {e}. Using width 0.")
                 current_line_width = 0

            naive_cursor_x = PADDING // SCALE_FACTOR + current_line_width

            # Apply the same scrolling logic used in _simulate_typing_step
            available_width = ORIGINAL_WIDTH - (PADDING // SCALE_FACTOR) # Width available for text + cursor
            cursor_space = CURSOR_WIDTH // SCALE_FACTOR + (PADDING // SCALE_FACTOR) # Cursor width + right padding

            if naive_cursor_x + cursor_space > ORIGINAL_WIDTH:
                 # Scrolling should be active
                 self.cursor_x = ORIGINAL_WIDTH - cursor_space
                 self.text_x = self.cursor_x - current_line_width
            else:
                 # Not scrolling
                 self.cursor_x = naive_cursor_x
                 self.text_x = PADDING // SCALE_FACTOR

        # Final check: If animation is finished, place cursor at the end of the displayed text
        if self.animation_finished:
            # Recalculate position based on the *entire* last line if finished
            last_newline_index = current_full_text.rfind('\n', 0)
            line_start_index = last_newline_index + 1
            self.display_text = current_full_text[line_start_index:] # Full last line
            try:
                text_rect = self.font.get_rect(self.display_text)
                current_line_width = text_rect.width
            except pygame.error as e:
                print(f"Warning: Pygame error getting rect for finished line '{self.display_text}': {e}. Using width 0.")
                current_line_width = 0

            naive_cursor_x = PADDING // SCALE_FACTOR + current_line_width
            available_width = ORIGINAL_WIDTH - (PADDING // SCALE_FACTOR)
            cursor_space = CURSOR_WIDTH // SCALE_FACTOR + (PADDING // SCALE_FACTOR)

            if naive_cursor_x + cursor_space > ORIGINAL_WIDTH:
                 self.cursor_x = ORIGINAL_WIDTH - cursor_space
                 self.text_x = self.cursor_x - current_line_width
            else:
                 self.cursor_x = naive_cursor_x
                 self.text_x = PADDING // SCALE_FACTOR
            # Ensure char_index reflects the true end
            self.char_index = len(current_full_text)


        print(f"Initialization complete. State: Text #{self.current_text_index}, Char #{self.char_index}, Finished: {self.animation_finished}")
        print(f"Initial display line: '{self.display_text}'")
        print(f"Initial text_x: {self.text_x}, cursor_x: {self.cursor_x}")

    def toggle_cursor(self):
        """Toggle cursor visibility for blinking effect"""
        now = time.monotonic()
        if now - self.cursor_last_toggle >= 0.5:  # Toggle every 0.5 seconds
            self.cursor_visible = not self.cursor_visible
            self.cursor_last_toggle = now

    def update_animation(self):
        """Update animation state based on absolute time."""
        current_datetime = datetime.now()

        # Don't start animating before the designated start time
        if current_datetime < self.start_time:
             # Display "Waiting..." message centered
             wait_text = "Waiting..."
             try:
                 text_rect = self.font.get_rect(wait_text)
                 wait_width = text_rect.width
             except pygame.error:
                 wait_width = 8 * len(wait_text) # Estimate if font fails

             self.display_text = wait_text
             self.text_x = (ORIGINAL_WIDTH - wait_width) // 2
             self.cursor_x = self.text_x + wait_width # Position cursor after text
             self.cursor_visible = False # Hide cursor while waiting
             self.animation_finished = False # Ensure not marked finished while waiting
             return # Don't process further

        elapsed_seconds = (current_datetime - self.start_time).total_seconds()

        # If already marked as finished, only update cursor blink, don't recalculate
        if self.animation_finished: # and elapsed_seconds >= self.total_duration_seconds: # Removed second check, finished flag is enough
             # Ensure cursor is visible if animation just finished
             if not self.cursor_visible: self.cursor_last_toggle = 0 # Force toggle check
             return

        # Calculate where we *should* be right now
        target_text_index, target_char_index = self.calculate_target_state(elapsed_seconds)

        # Clamp target index if needed (safety check)
        if not TEXT_ARRAY:
             target_text_index = 0
             target_char_index = 0
        else:
             # Allow target_text_index to be len(TEXT_ARRAY) to signal end
             if target_text_index >= len(TEXT_ARRAY):
                  target_text_index = len(TEXT_ARRAY) -1
                  target_char_index = len(TEXT_ARRAY[target_text_index])
                  self.animation_finished = True # Mark finished if target calculation goes past end
             else:
                  target_text_index = max(0, target_text_index)
                  target_char_index = max(0, min(len(TEXT_ARRAY[target_text_index]), target_char_index))

        # Advance the simulation step-by-step until the current state matches the target state
        steps_taken_this_frame = 0
        # Safety limit increased slightly, but direct init should prevent hitting it.
        max_steps_per_frame = 250

        # Condition to check if we are behind the target state
        is_behind = False
        if not self.animation_finished:
            if self.current_text_index < target_text_index:
                 is_behind = True
            elif self.current_text_index == target_text_index and self.char_index < target_char_index:
                 is_behind = True

        while is_behind and not self.animation_finished:
             if not self._simulate_typing_step():
                  # Simulation step indicated no change possible (likely hit end prematurely)
                  print("Warning: Simulation step returned False unexpectedly during update.")
                  break
             steps_taken_this_frame += 1
             if steps_taken_this_frame > max_steps_per_frame:
                  print(f"Warning: Exceeded max steps ({max_steps_per_frame}) in single update frame. Target: Txt {target_text_index} Char {target_char_index}. Current: Txt {self.current_text_index} Char {self.char_index}")
                  # Force state to target to prevent getting stuck (will cause visual jump)
                  self.initialize_state_directly() # Resync completely
                  break # Exit loop after resync

             # Re-evaluate if we are still behind after the step
             if self.current_text_index > target_text_index: # Overshot text index?
                   is_behind = False
             elif self.current_text_index == target_text_index and self.char_index >= target_char_index: # Reached target char index
                   is_behind = False
             # else: is_behind remains True


    def render_frame(self):
        """Render the current frame to the surface"""
        self.surface.fill(VFD_BG_COLOR)
        self.surface.blit(self.grid_texture, (0, 0))

        # Draw the visible portion of the text
        if self.display_text:
            try:
                text_surf, text_rect = self.font.render(self.display_text, VFD_TEXT_COLOR) # Default AA
                # Adjust vertical alignment based on rendered height
                text_rect.top = (ORIGINAL_HEIGHT - text_rect.height) // 2
                text_rect.left = self.text_x
                self.surface.blit(text_surf, text_rect)
            except pygame.error as e:
                 print(f"Warning: Pygame error rendering text '{self.display_text}': {e}", end='\r')
            except Exception as e:
                 print(f"Non-pygame error rendering text: {e}", end='\r')


        # Draw cursor if it should be visible
        # Show blinking cursor if animation is running OR if it's finished
        if self.cursor_visible: #and (not self.animation_finished or elapsed_seconds >= self.total_duration_seconds):
             # Determine Y position for cursor
             cursor_y = (ORIGINAL_HEIGHT - (CURSOR_HEIGHT // SCALE_FACTOR)) // 2
             # Clamp cursor_x to be within bounds, accounting for padding
             max_cursor_x = ORIGINAL_WIDTH - (PADDING // SCALE_FACTOR) - (CURSOR_WIDTH // SCALE_FACTOR)
             draw_cursor_x = max(PADDING // SCALE_FACTOR, min(max_cursor_x, self.cursor_x))
             # Draw the rectangle
             try:
                  pygame.draw.rect(self.surface, VFD_TEXT_COLOR,
                                 (draw_cursor_x, cursor_y,
                                  CURSOR_WIDTH // SCALE_FACTOR,
                                  CURSOR_HEIGHT // SCALE_FACTOR))
             except Exception as e:
                  print(f"Error drawing cursor: {e}", end='\r')


    def convert_to_bitmap(self):
        """Convert the surface to a 1-bit bitmap (336x24 = 8064 bits = 1008 bytes)"""
        num_bytes = (ORIGINAL_WIDTH * ORIGINAL_HEIGHT + 7) // 8
        bitmap = bytearray(num_bytes)
        threshold = 80 # Adjust this threshold based on VFD_TEXT_COLOR intensity vs BG

        for y in range(ORIGINAL_HEIGHT):
            for x in range(ORIGINAL_WIDTH):
                try:
                    pixel = self.surface.get_at((x, y))
                except IndexError:
                     print(f"Error: get_at({x}, {y}) out of bounds for surface ({ORIGINAL_WIDTH}x{ORIGINAL_HEIGHT})")
                     continue # Skip faulty pixel

                # Check if luminance is above threshold (simple brightness check)
                # Using direct component check might be faster
                is_on = pixel[0] > threshold or pixel[1] > threshold or pixel[2] > threshold

                if is_on:
                    pixel_index = y * ORIGINAL_WIDTH + x
                    byte_index = pixel_index // 8
                    bit_index = 7 - (pixel_index % 8) # VFD hardware might expect MSB first
                    # Ensure byte_index is valid
                    if 0 <= byte_index < num_bytes:
                         bitmap[byte_index] |= (1 << bit_index)
                    # else:
                    #      print(f"Error: Calculated byte_index {byte_index} out of bounds (0-{num_bytes-1}) for pixel {x},{y}")

        return bitmap

    def send_frame(self):
        """Send the current frame over UDP"""
        try:
            bitmap = self.convert_to_bitmap()
            self.sock.sendto(bitmap, (UDP_IP, UDP_PORT))
        except socket.gaierror:
             print(f"Error: Cannot resolve hostname/IP: {UDP_IP}. Check network settings.", end='\r')
             time.sleep(5) # Prevent spamming errors
        except OSError as e:
             # Catch specific errors like Network is unreachable more gracefully
             if e.errno == 101: # Network is unreachable
                  print(f"Network Error: Network is unreachable for {UDP_IP}:{UDP_PORT}. Retrying...", end='\r')
             else:
                  print(f"Network Error: {e}. Check IP/Port ({UDP_IP}:{UDP_PORT}) and network connection.", end='\r')
             time.sleep(5)
        except Exception as e:
            print(f"Error sending frame: {e}")


    def run(self):
        """Main loop for generating and sending frames"""
        running = True
        clock = pygame.time.Clock()
        frame_count = 0

        while running:
            # Handle events (just for quitting)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False

            # Update animation state based on absolute time
            self.update_animation()

            # Toggle cursor for blinking effect
            self.toggle_cursor()

            # Render the frame
            self.render_frame()

            # Send the frame (only send if needed, maybe add check for changes?)
            self.send_frame()

            frame_count += 1
            # Optional: Print status periodically for debugging
            # if frame_count % 60 == 0: # Print once per second approx
            #     current_datetime = datetime.now()
            #     elapsed_seconds = (current_datetime - self.start_time).total_seconds()
            #     tgt_txt, tgt_char = self.calculate_target_state(elapsed_seconds)
            #     print(f"[{current_datetime.strftime('%H:%M:%S')}] State: Txt {self.current_text_index}, Char {self.char_index} / Target: Txt {tgt_txt}, Char {tgt_char}, Finished: {self.animation_finished}      ", end='\r')

            clock.tick(30)  # Aim for ~30 fps, adjust as needed

        print("\nExiting.")
        pygame.quit()
        if self.sock:
            self.sock.close()
        sys.exit()


if __name__ == "__main__":
    if not TEXT_ARRAY or not TEXT_DURATIONS:
         print("Error: No text loaded or durations calculated. Cannot start animation.")
         # Ensure pygame is quit if it was initialized
         if pygame.get_init():
              pygame.quit()
         sys.exit(1)

    # Add basic check for font loading success if possible
    try:
        generator = VFDGenerator()
        if not generator.font: # Check if font loading failed completely
             raise RuntimeError("Font loading failed, cannot proceed.")
        generator.run()
    except RuntimeError as e:
         print(f"Runtime Error: {e}")
         if pygame.get_init():
              pygame.quit()
         sys.exit(1)
    except KeyboardInterrupt:
         print("\nCaught Ctrl+C, exiting.")
         # Try to cleanup pygame and socket gracefully
         if 'generator' in locals() and generator:
              if pygame.get_init():
                  pygame.quit()
              if generator.sock:
                  generator.sock.close()
         sys.exit(0)
    except Exception as e:
         print(f"\nAn unexpected error occurred: {e}")
         import traceback
         traceback.print_exc()
         if pygame.get_init():
             pygame.quit()
         sys.exit(1)