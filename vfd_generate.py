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
    parser.add_argument('--font-size', type=int, default=18, help='Font size (before scaling)')
    parser.add_argument('--font', default='./KodeMono.ttf', help=
                        'Path to font file or name of system font (some examples: "Courier New", "Courier", '
                        '"Lucida Console", "Monaco" [12], "DejaVu Sans Mono") ... '
                        'see `fc-list` or `pygame.font.get_fonts()`')
    parser.add_argument('--text', default='20250424_044729.json', help='Path to JSON file containing text array')
    parser.add_argument('--first-hours', type=float, default=5, help='Hours to spend on first text')
    parser.add_argument('--last-hours', type=float, default=24, help='Hours to spend on last text')
    parser.add_argument('--default-hours', type=float, default=19, help='Hours to spend on each text between first and last')
    # parser.add_argument('--start', default=(datetime.now() + timedelta(seconds=5)).strftime("%Y%m%d-%H%M%S"),
    parser.add_argument('--start', default='20250424-190000',
                        help='Start time for animation in YYYYMMDD-HHMMSS format (defaults to current time + 10 seconds)')
    parser.add_argument('--rotate-180', action='store_true', help='Rotate the display output by 180 degrees')
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
        if not self.font: # Added check here after load_font call
            raise RuntimeError("Failed to load any suitable font.")
        self.font.antialiased = False # Better for monochrome? Test this.
        self.font.origin = True

        # Animation state variables - These will be set by _set_visual_state_from_target
        self.current_text_index = 0
        self.char_index = 0
        self.current_text = ""
        self.display_text = ""
        self.text_x = PADDING // SCALE_FACTOR
        self.cursor_x = PADDING // SCALE_FACTOR
        self.animation_finished = False

        # Cursor blinking
        self.cursor_visible = True
        self.cursor_last_toggle = time.monotonic() # Use monotonic clock for intervals

        # Timing
        self.start_time = start_datetime
        self.text_durations = TEXT_DURATIONS
        self.total_duration_seconds = TOTAL_DURATION_SECONDS


        # Set up the grid texture
        self.grid_texture = self.create_grid_texture()

        # Log rotation setting
        if args.rotate_180:
            print("Display rotation: 180 degrees (upside down)")
        else:
            print("Display rotation: 0 degrees (normal)")

        # === INITIALIZATION ===
        # Calculate the initial target state based on current time
        print("Calculating initial display state...")
        initial_elapsed_seconds = (datetime.now() - self.start_time).total_seconds()
        initial_target_text_index, initial_target_char_index = self.calculate_target_state(initial_elapsed_seconds)

        # Set the initial visual state directly using the new method
        print(f"Setting initial state to: Text #{initial_target_text_index}, Char #{initial_target_char_index}")
        self._set_visual_state_from_target(initial_target_text_index, initial_target_char_index)
        print("Initialization complete.")


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
             # Treat time before start as being exactly at the beginning (0 seconds elapsed)
             elapsed_seconds = 0

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
                target_char_index = 0 # Default if calculation fails
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
                # Check total_duration_seconds first to avoid division by zero later if it's 0
                if self.total_duration_seconds > 0 and elapsed_seconds >= self.total_duration_seconds:
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



    def _set_visual_state_from_target(self, target_text_index, target_char_index):
        """
        Sets the visual animation state (display text, positions) directly
        based on the calculated target text and character index.
        This replaces the step-by-step simulation for updating the display.
        """
        # --- Update Core State Variables ---
        # Clamp target index to valid range [0, len(TEXT_ARRAY)-1] or handle empty array
        if not TEXT_ARRAY:
            target_text_index = 0
            target_char_index = 0
            self.current_text_index = 0
            self.char_index = 0
            self.current_text = ""
            self.animation_finished = True # No text means finished
        else:
            # Ensure target_text_index is within bounds
            target_text_index = max(0, min(len(TEXT_ARRAY) - 1, target_text_index))

            # Update internal state
            self.current_text_index = target_text_index
            self.current_text = TEXT_ARRAY[self.current_text_index]

            # Ensure target_char_index is within bounds for the current text
            target_char_index = max(0, min(len(self.current_text), target_char_index))
            self.char_index = target_char_index

            # Determine if animation is finished based on whether we are at the end of the last text
            # Needs elapsed time check as well, in case total duration is 0
            current_datetime = datetime.now()
            elapsed_seconds = (current_datetime - self.start_time).total_seconds()
            is_at_end_of_last_text = (self.current_text_index == len(TEXT_ARRAY) - 1 and
                                     self.char_index == len(self.current_text))
            has_exceeded_duration = (self.total_duration_seconds > 0 and
                                     elapsed_seconds >= self.total_duration_seconds)

            self.animation_finished = is_at_end_of_last_text or has_exceeded_duration


        # --- Direct Calculation of Visual Display ---
        if not self.current_text:
             # Handle empty text case
             self.display_text = ""
             self.text_x = PADDING // SCALE_FACTOR
             self.cursor_x = PADDING // SCALE_FACTOR
             # print("Visual state set (Empty text).") # Debug
             return

        # Find the start of the current line based on the last newline before char_index
        last_newline_index = self.current_text.rfind('\n', 0, self.char_index)
        line_start_index = last_newline_index + 1

        # Extract the content of the line up to the target character
        current_line_content = self.current_text[line_start_index : self.char_index]
        self.display_text = current_line_content # This is what should be visible

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
                 print(f"Warning: Pygame error getting rect for '{self.display_text}' during visual state set: {e}. Using width 0.")
                 current_line_width = 0

            # Calculate where the cursor would be if there was infinite space
            naive_cursor_x = PADDING // SCALE_FACTOR + current_line_width

            # Apply scrolling logic
            cursor_space = CURSOR_WIDTH // SCALE_FACTOR + (PADDING // SCALE_FACTOR) # Cursor width + right padding

            if naive_cursor_x + cursor_space > ORIGINAL_WIDTH:
                 # Scrolling should be active: Cursor fixed near right, text shifts left
                 self.cursor_x = ORIGINAL_WIDTH - cursor_space
                 self.text_x = self.cursor_x - current_line_width
            else:
                 # Not scrolling: Text starts at left padding, cursor follows text
                 self.cursor_x = naive_cursor_x
                 self.text_x = PADDING // SCALE_FACTOR

        # --- Handle Animation Finished State ---
        # If the animation is marked as finished, ensure the display shows the
        # end of the *last* line of the *last* text, potentially scrolled.
        if self.animation_finished and TEXT_ARRAY:
            # Ensure we are definitely using the last text
            self.current_text_index = len(TEXT_ARRAY) - 1
            self.current_text = TEXT_ARRAY[self.current_text_index]
            self.char_index = len(self.current_text) # Ensure char_index is at the very end

            # Recalculate display based on the *entire* last line
            last_newline_index = self.current_text.rfind('\n', 0)
            line_start_index = last_newline_index + 1
            self.display_text = self.current_text[line_start_index:] # Full last line

            try:
                text_rect = self.font.get_rect(self.display_text)
                current_line_width = text_rect.width
            except pygame.error as e:
                print(f"Warning: Pygame error getting rect for finished line '{self.display_text}': {e}. Using width 0.")
                current_line_width = 0

            # Recalculate positions for the finished state
            naive_cursor_x = PADDING // SCALE_FACTOR + current_line_width
            cursor_space = CURSOR_WIDTH // SCALE_FACTOR + (PADDING // SCALE_FACTOR)

            if naive_cursor_x + cursor_space > ORIGINAL_WIDTH:
                 # Scroll if last line is too long
                 self.cursor_x = ORIGINAL_WIDTH - cursor_space
                 self.text_x = self.cursor_x - current_line_width
            else:
                 # Position normally if last line fits
                 self.cursor_x = naive_cursor_x
                 self.text_x = PADDING // SCALE_FACTOR

        # print(f"Visual state set: Txt {self.current_text_index} Ch {self.char_index} Fin={self.animation_finished} Disp='{self.display_text}' Tx={self.text_x} Cx={self.cursor_x}") # Debug

    def toggle_cursor(self):
        """Toggle cursor visibility for blinking effect"""
        now = time.monotonic()
        if now - self.cursor_last_toggle >= 0.5:  # Toggle every 0.5 seconds
            self.cursor_visible = not self.cursor_visible
            self.cursor_last_toggle = now

    def update_animation(self):
        """Update animation state based on absolute time using direct calculation."""
        current_datetime = datetime.now()

        # --- Handle Waiting State ---
        if current_datetime < self.start_time:
             # Display is blank while waiting before the start time
             self.display_text = ''
             self.text_x = PADDING // SCALE_FACTOR
             self.cursor_x = PADDING // SCALE_FACTOR # Show cursor at start pos while waiting
             self.animation_finished = False # Ensure not marked finished
             # Reset internal state to the beginning for when it starts
             self.current_text_index = 0
             self.char_index = 0
             if TEXT_ARRAY:
                 self.current_text = TEXT_ARRAY[0]
             else:
                 self.current_text = ""
             self.cursor_visible = True # Keep cursor solid while waiting? Or let it blink? Blinking is fine.
             return # Don't do further calculations until start time

        # --- Calculate Target State ---
        elapsed_seconds = (current_datetime - self.start_time).total_seconds()
        target_text_index, target_char_index = self.calculate_target_state(elapsed_seconds)

        # --- Set Visual State Directly ---
        # No simulation loop needed. Just calculate the visual state based on the target indices.
        # The _set_visual_state_from_target function handles updating self.current_text_index,
        # self.char_index, self.animation_finished, self.display_text, self.text_x, self.cursor_x.
        self._set_visual_state_from_target(target_text_index, target_char_index)

        # Cursor blinking is handled separately and still needs to run.
        # self.toggle_cursor() # This is called in the main loop already


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
                 # Reduce console spam by only printing distinct errors
                 if not hasattr(self, '_last_render_error') or self._last_render_error != str(e):
                      print(f"\nWarning: Pygame error rendering text '{self.display_text[:20]}...': {e}")
                      self._last_render_error = str(e)
            except Exception as e:
                 if not hasattr(self, '_last_render_error') or self._last_render_error != str(e):
                      print(f"\nNon-pygame error rendering text: {e}")
                      self._last_render_error = str(e)


        # Draw cursor if it should be visible
        # Show blinking cursor if animation is running OR if it's finished
        # Also show cursor if we are waiting before the start time
        if self.cursor_visible:
             # Determine Y position for cursor
             cursor_y = (ORIGINAL_HEIGHT - (CURSOR_HEIGHT // SCALE_FACTOR)) // 2
             # Clamp cursor_x to be within bounds, accounting for padding
             max_cursor_x = ORIGINAL_WIDTH - (PADDING // SCALE_FACTOR) - (CURSOR_WIDTH // SCALE_FACTOR)
             # Use max(PADDING // SCALE_FACTOR, ...) to prevent cursor going into left padding
             draw_cursor_x = max(PADDING // SCALE_FACTOR, min(max_cursor_x, self.cursor_x))

             # Draw the rectangle
             try:
                  pygame.draw.rect(self.surface, VFD_TEXT_COLOR,
                                 (draw_cursor_x, cursor_y,
                                  CURSOR_WIDTH // SCALE_FACTOR,
                                  CURSOR_HEIGHT // SCALE_FACTOR))
             except Exception as e:
                  # Reduce console spam
                  if not hasattr(self, '_last_cursor_error') or self._last_cursor_error != str(e):
                      print(f"\nError drawing cursor: {e}")
                      self._last_cursor_error = str(e)


    def convert_to_bitmap(self):
        """Convert the surface to a 1-bit bitmap (336x24 = 8064 bits = 1008 bytes)"""
        num_bytes = (ORIGINAL_WIDTH * ORIGINAL_HEIGHT + 7) // 8
        bitmap = bytearray(num_bytes)
        threshold = 80 # Adjust this threshold based on VFD_TEXT_COLOR intensity vs BG

        for y in range(ORIGINAL_HEIGHT):
            for x in range(ORIGINAL_WIDTH):
                try:
                    # If rotation is enabled, flip the coordinates
                    if args.rotate_180:
                        pixel = self.surface.get_at((ORIGINAL_WIDTH - 1 - x, ORIGINAL_HEIGHT - 1 - y))
                    else:
                        pixel = self.surface.get_at((x, y))
                except IndexError:
                     # This should ideally not happen with correct surface/coords
                     if not hasattr(self, '_last_pixel_error_pos') or self._last_pixel_error_pos != (x,y):
                          print(f"\nError: get_at({x}, {y}) out of bounds for surface ({ORIGINAL_WIDTH}x{ORIGINAL_HEIGHT})")
                          self._last_pixel_error_pos = (x,y)
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
                    # else: # This check might be too verbose if it ever happens
                    #      print(f"Error: Calculated byte_index {byte_index} out of bounds (0-{num_bytes-1}) for pixel {x},{y}")

        return bitmap

    def send_frame(self):
        """Send the current frame over UDP"""
        try:
            bitmap = self.convert_to_bitmap()
            self.sock.sendto(bitmap, (UDP_IP, UDP_PORT))
            # Clear previous error state on success
            if hasattr(self, '_last_send_error'):
                del self._last_send_error
        except socket.gaierror as e:
             # Log error only if it's new
             if not hasattr(self, '_last_send_error') or self._last_send_error != str(e):
                 print(f"\nError: Cannot resolve hostname/IP: {UDP_IP}. Check network settings. ({e})")
                 self._last_send_error = str(e)
             time.sleep(2) # Prevent spamming errors, shorter sleep
        except OSError as e:
             # Catch specific errors like Network is unreachable more gracefully
             log_msg = ""
             if e.errno == 101: # Network is unreachable
                  log_msg = f"Network Error: Network is unreachable for {UDP_IP}:{UDP_PORT}. Retrying..."
             else:
                  log_msg = f"Network Error: {e}. Check IP/Port ({UDP_IP}:{UDP_PORT}) and network connection."

             if not hasattr(self, '_last_send_error') or self._last_send_error != str(e):
                 print(f"\n{log_msg}")
                 self._last_send_error = str(e)
             time.sleep(2) # Shorter sleep
        except Exception as e:
            if not hasattr(self, '_last_send_error') or self._last_send_error != str(e):
                print(f"\nError sending frame: {e}")
                self._last_send_error = str(e)
            time.sleep(1) # Short sleep for general errors


    def run(self):
        """Main loop for generating and sending frames"""
        running = True
        clock = pygame.time.Clock()
        frame_count = 0
        last_log_time = time.monotonic()  # Track when we last logged

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

            # Send the frame
            self.send_frame()

            # Log status every 10 seconds
            current_time = time.monotonic()
            if current_time - last_log_time >= 10:  # Log every 10 seconds
                self.log_status()
                last_log_time = current_time

            frame_count += 1
            # Aim for ~20-30 fps. Lower FPS might be fine for VFD and reduce CPU load.
            # Test what looks acceptable. Start with 20.
            clock.tick(20)

        print("\nExiting.")
        pygame.quit()
        if self.sock:
            self.sock.close()
        sys.exit()

    def log_status(self):
        """Log current status information"""
        current_datetime = datetime.now()

        # Calculate time difference from start
        elapsed_seconds = (current_datetime - self.start_time).total_seconds()

        time_diff_str = ""
        if elapsed_seconds < 0:
             time_diff_str = f"Starts in {-elapsed_seconds:.0f}s"
        else:
             days, remainder = divmod(elapsed_seconds, 86400)
             hours, remainder = divmod(remainder, 3600)
             minutes, seconds = divmod(remainder, 60)
             time_diff_str = f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds):.0f}s"


        # Get current text information
        if not TEXT_ARRAY:
            text_info = "No text loaded"
            context = "N/A"
        elif self.current_text_index >= len(TEXT_ARRAY): # Should not happen with new logic, but safety check
            text_info = f"Index Error (Index: {self.current_text_index}, Max: {len(TEXT_ARRAY)-1})"
            context = "N/A"
        else:
            # These are now updated directly by _set_visual_state_from_target
            current_text_idx = self.current_text_index
            current_char_idx = self.char_index
            current_text = self.current_text # TEXT_ARRAY[current_text_idx]

            total_chars = len(current_text)
            relative_pos = f"{current_char_idx}/{total_chars}" if total_chars > 0 else "0/0"
            percentage = f"{(current_char_idx / total_chars * 100):.1f}%" if total_chars > 0 else "N/A"

            text_info = f"Text #{current_text_idx}/{len(TEXT_ARRAY)-1}, Char {relative_pos} ({percentage})"

            # Get context around cursor
            context_before = current_text[max(0, current_char_idx-30):current_char_idx]
            context_after = current_text[current_char_idx:min(len(current_text), current_char_idx+30)]
            context = f"Context: \"...{context_before.replace(chr(10), '/')}<-CURSOR->{context_after.replace(chr(10), '/')}...\""

        # Print the log
        print(f"\n--- Status @ {current_datetime.strftime('%Y-%m-%d %H:%M:%S')} ---")
        print(f"Time State: {time_diff_str} from start ({self.start_time.strftime('%H:%M:%S')})")
        print(f"Position:   {text_info}")
        print(f"State:      Animation {'finished' if self.animation_finished else 'in progress' if elapsed_seconds >= 0 else 'waiting to start'}")
        print(f"{context}")
        print(f"Display:    '{self.display_text}' (TxtX: {self.text_x}, CrsrX: {self.cursor_x}, CrsrVis: {self.cursor_visible})")
        print("-" * (len(f"--- Status @ {current_datetime.strftime('%Y-%m-%d %H:%M:%S')} ---")))


if __name__ == "__main__":
    if not TEXT_ARRAY or not TEXT_DURATIONS:
         print("Error: No text loaded or durations calculated. Cannot start animation.")
         if pygame.get_init():
              pygame.quit()
         sys.exit(1)

    generator = None # Define generator outside try block for cleanup
    try:
        generator = VFDGenerator()
        generator.run()
    except RuntimeError as e:
         print(f"\nRuntime Error during setup: {e}")
         if pygame.get_init():
              pygame.quit()
         sys.exit(1)
    except KeyboardInterrupt:
         print("\nCaught Ctrl+C, exiting.")
         # Cleanup handled in finally block
    except Exception as e:
         print(f"\nAn unexpected error occurred: {e}")
         import traceback
         traceback.print_exc()
         # Cleanup handled in finally block
    finally:
        # Ensure cleanup happens regardless of how we exit
        print("Cleaning up resources...")
        if generator and generator.sock:
            generator.sock.close()
            print("Socket closed.")
        if pygame.get_init():
            pygame.quit()
            print("Pygame quit.")
        print("Cleanup finished.")
        sys.exit(0 if isinstance(sys.exc_info()[1], KeyboardInterrupt) else 1)
