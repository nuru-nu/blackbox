"""
VFD Font Generator

Creates a JSON file mapping characters to their binary bitmaps for use with VFD displays.
Each character is rendered to a bitmap with consistent height but variable width.
"""

import pygame
import pygame.freetype
import json
import argparse
import os
import sys
from pathlib import Path


def parse_args():
  parser = argparse.ArgumentParser(description='Generate VFD font bitmap mapping')
  parser.add_argument('--output', default='vfd_font.json', help='Output JSON file path')
  parser.add_argument('--font', default='./KodeMono.ttf', help='Path to font file or name of system font')
  parser.add_argument('--font-size', type=int, default=18, help='Font size in pixels')
  parser.add_argument('--char-height', type=int, default=24, help='Fixed height for all character bitmaps')
  parser.add_argument('--chars', default=None, help='Specific characters to include (if not specified, includes ASCII 32-126 plus common symbols)')
  parser.add_argument('--chars-file', default=None, help='JSON file that contains characters to include')
  parser.add_argument('--padding', type=int, default=0, help='Horizontal padding for each character')
  return parser.parse_args()


def load_font(font_path, font_size):
  """Load the specified font or try to find a suitable default"""
  try:
    if os.path.exists(font_path):
      print(f"Loading font from file: {font_path} ({font_size}px)")
      return pygame.freetype.Font(font_path, font_size)
    else:
      print(f"Loading system font: {font_path} ({font_size}px)")
      return pygame.freetype.SysFont(font_path, font_size)
  except Exception as e:
    print(f"Warning: Could not load specified font '{font_path}': {e}")

  # Fallback fonts
  for font_name in ["DejaVu Sans Mono", "Consolas", "Monaco", "Courier New", "Courier", "monospace"]:
    try:
      print(f"Trying fallback font: {font_name} ({font_size}px)")
      return pygame.freetype.SysFont(font_name, font_size)
    except Exception:
      continue  # Try next font

  print("Error: No suitable font found!")
  return None


def get_default_charset():
  """Return the default character set (ASCII 32-126 plus common symbols)"""
  # Basic ASCII (space through ~)
  chars = [chr(i) for i in range(32, 127)]

  # Add common symbols and accented characters
  additional = "°±²³µ¶·¹º¼½¾¿ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿ"
  chars.extend(additional)

  return ''.join(chars)


def render_char_to_bitmap(font, char, height, padding=0):
  """Render a character to a bitmap with fixed height but variable width"""
  # Set antialiasing to False for sharper edges
  font.antialiased = False

  # Render the character to get its dimensions
  try:
    text_surf, text_rect = font.render(char, (255, 255, 255))
  except pygame.error:
    print(f"Warning: Could not render character '{char}' (code: {ord(char)})")
    return None, 0

  # Create a surface with the character's width (plus padding) and fixed height
  width = text_rect.width + (padding * 2)
  if width == 0:  # Handle zero-width characters
    width = font.size // 2  # Use a reasonable minimum width

  # Create a new surface for the character
  char_surf = pygame.Surface((width, height), pygame.SRCALPHA)
  char_surf.fill((0, 0, 0, 0))  # Transparent background

  # Center the character vertically
  y_pos = (height - text_rect.height) // 2

  # Position the character with padding
  char_surf.blit(text_surf, (padding, y_pos))

  # Convert to bitmap
  bitmap = []
  for y in range(height):
    row = []
    for x in range(width):
      try:
        pixel = char_surf.get_at((x, y))
        # Check if pixel is not transparent/black
        is_on = pixel[0] > 0 or pixel[1] > 0 or pixel[2] > 0
        row.append(1 if is_on else 0)
      except IndexError:
        row.append(0)
    bitmap.append(row)

  return bitmap, width


def generate_font_mapping(font, charset, height, padding=0):
  """Generate a mapping of characters to their bitmaps"""
  char_map = {}
  max_width = 0
  min_width = float('inf')

  print(f"Generating bitmaps for {len(charset)} characters...")

  for char in charset:
    bitmap, width = render_char_to_bitmap(font, char, height, padding)
    if bitmap:
      char_map[char] = {
        "bitmap": bitmap,
        "width": width,
        "height": height
      }
      max_width = max(max_width, width)
      min_width = min(min_width, width)
    else:
      print(f"Skipping character '{char}' (code: {ord(char)}) due to rendering error")

  print(f"Generated {len(char_map)} character bitmaps")
  print(f"Character width range: {min_width} to {max_width} pixels")

  return char_map


def save_font_mapping(mapping, output_path, font_name, font_size, char_height, padding):
  """Save the character mapping to a JSON file"""
  # Create metadata
  font_data = {
    "metadata": {
      "font": font_name,
      "size": font_size,
      "char_height": char_height,
      "padding": padding,
      "char_count": len(mapping),
      "generated": pygame.time.get_ticks()
    },
    "characters": mapping
  }

  # Ensure output directory exists
  output_dir = os.path.dirname(output_path)
  if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir)

  # Save to JSON file
  with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(font_data, f, ensure_ascii=False)#, indent=2)

  print(f"Font mapping saved to {output_path}")
  print(f"File size: {os.path.getsize(output_path) / 1024:.2f} KB")


def main():
  # Parse command line arguments
  args = parse_args()

  # Initialize Pygame
  pygame.init()

  try:
    # Load font
    font = load_font(args.font, args.font_size)
    if not font:
      print("Error: Failed to load any suitable font.")
      return 1

    assert not (args.chars and args.chars_file)

    # Get character set
    if args.chars_file:
      def rek(x, charset=None):
        if charset is None:
          charset = set()
        if isinstance(x, dict):
          for v in x.values():
            rek(v, charset)
        elif isinstance(x, list):
          for v in x:
            rek(v, charset)
        elif isinstance(x, str):
          charset |= {*x}
        return charset
      charset = ''.join(sorted(rek(json.load(open(args.chars_file)))))
    elif args.chars:
      charset = args.chars
    else:
      charset = get_default_charset()

    print('charset size', len(charset), charset)

    # Generate character mapping
    char_map = generate_font_mapping(font, charset, args.char_height, args.padding)

    # Save mapping to JSON file
    font_name = args.font
    if os.path.exists(args.font):
      font_name = Path(args.font).name

    save_font_mapping(char_map, args.output, font_name, args.font_size, args.char_height, args.padding)

    return 0

  except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    return 1

  finally:
    pygame.quit()


if __name__ == "__main__":
  sys.exit(main())