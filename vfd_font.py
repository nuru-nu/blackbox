"""
VFD Font Generator

Creates a JSON file mapping characters to their binary bitmaps for use with VFD displays.
Each character is rendered to a bitmap with consistent height but variable width.
"""

import freetype
import numpy as np
import json
import argparse
import os
import sys
from pathlib import Path
import time


def parse_args():
  parser = argparse.ArgumentParser(description='Generate VFD font bitmap mapping')
  parser.add_argument('--output', default='vfd_font.json', help='Output JSON file path')
  parser.add_argument('--font', default='./KodeMono.ttf', help='Path to font file or name of system font')
  parser.add_argument('--font-size', type=int, default=18, help='Font size in pixels (optional, uses font default if not set)')
  parser.add_argument('--chars', default=None, help='Specific characters to include (if not specified, includes ASCII 32-126 plus common symbols)')
  parser.add_argument('--chars-file', default=None, help='JSON file that contains characters to include')
  parser.add_argument('--padding', type=int, default=0, help='Horizontal padding for each character')
  return parser.parse_args()


def load_font(font_path, font_size):
  """Load the specified font using freetype-py"""
  try:
    if os.path.exists(font_path):
      print(f"Loading font from file: {font_path} ({font_size}px)")
      face = freetype.Face(font_path)
    else:
      raise FileNotFoundError(f"Font file '{font_path}' not found.")
    face.set_pixel_sizes(0, font_size)
    return face
  except Exception as e:
    print(f"Error: Could not load specified font '{font_path}': {e}")
    return None


def get_default_charset():
  """Return the default character set (ASCII 32-126 plus common symbols)"""
  # Basic ASCII (space through ~)
  chars = [chr(i) for i in range(32, 127)]

  # Add common symbols and accented characters
  additional = "°±²³µ¶·¹º¼½¾¿ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿ"
  chars.extend(additional)

  return ''.join(chars)


def render_char_to_bitmap(font, char, padding=0):
  """Render a character to a bitmap with fixed height but variable width using freetype-py"""
  try:
    font.load_char(char, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO)
    bitmap = font.glyph.bitmap
    width = bitmap.width + (padding * 2)
    height = bitmap.rows

    # Convert the bitmap buffer to a 2D numpy array (monochrome)
    arr = np.array(bitmap.buffer, dtype=np.uint8).reshape((height, bitmap.pitch))
    # Unpack bits to get 0/1 per pixel
    arr = np.unpackbits(arr, axis=1)[:, :bitmap.width]
    # Pad horizontally
    if padding > 0:
      arr = np.pad(arr, ((0,0), (padding, padding)), 'constant', constant_values=0)
    # Convert to list of lists
    bitmap_list = arr.tolist()
    return bitmap_list, width
  except Exception as e:
    print(f"Warning: Could not render character '{char}' (code: {ord(char)}): {e}")
    return None, 0


def generate_font_mapping(font, charset, padding=0):
  """Generate a mapping of characters to their bitmaps using freetype-py"""
  char_map = {}
  max_width = 0
  min_width = float('inf')

  print(f"Generating bitmaps for {len(charset)} characters...")

  for char in charset:
    bitmap, width = render_char_to_bitmap(font, char, padding)
    if bitmap:
      char_map[char] = {
        "bitmap": bitmap,
        "width": width,
        "height": len(bitmap)
      }
      max_width = max(max_width, width)
      min_width = min(min_width, width)
    else:
      print(f"Skipping character '{char}' (code: {ord(char)}) due to rendering error")

  print(f"Generated {len(char_map)} character bitmaps")
  print(f"Character width range: {min_width} to {max_width} pixels")

  return char_map


def save_font_mapping(mapping, output_path, font_name, font_size, padding):
  """Save the character mapping to a JSON file"""
  font_data = {
    "metadata": {
      "font": font_name,
      "size": font_size,
      "padding": padding,
      "char_count": len(mapping),
      "generated": int(time.time() * 1000)
    },
    "characters": mapping
  }
  output_dir = os.path.dirname(output_path)
  if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir)
  with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(font_data, f, ensure_ascii=False)
  print(f"Font mapping saved to {output_path}")
  print(f"File size: {os.path.getsize(output_path) / 1024:.2f} KB")


def main():
  # Parse command line arguments
  args = parse_args()

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
    char_map = generate_font_mapping(font, charset, args.padding)

    # Save mapping to JSON file
    font_name = args.font
    if os.path.exists(args.font):
      font_name = Path(args.font).name

    save_font_mapping(char_map, args.output, font_name, args.font_size, args.padding)

    return 0

  except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    return 1


if __name__ == "__main__":
  sys.exit(main())