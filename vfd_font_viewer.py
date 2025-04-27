"""
VFD Font Viewer

Visualizes all glyphs from a VFD font JSON file.
Displays characters in a grid with their binary bitmap representation.
"""

import json
import pygame
import sys
import argparse
import math
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description='Visualize VFD font glyphs')
    parser.add_argument('--input', default='vfd_font.json', help='Input JSON font file path')
    parser.add_argument('--scale', type=int, default=2, help='Display scale factor')
    parser.add_argument('--bg-color', default='#000000', help='Background color (hex)')
    parser.add_argument('--fg-color', default='#00FF00', help='Foreground color (hex)')
    parser.add_argument('--grid-color', default='#333333', help='Grid line color (hex)')
    parser.add_argument('--cols', type=int, default=16, help='Number of columns in the grid')
    parser.add_argument('--spacing', type=int, default=4, help='Spacing between characters')
    return parser.parse_args()


def load_font_data(file_path):
    """Load the VFD font data from a JSON file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading font file: {e}")
        sys.exit(1)


def hex_to_rgb(hex_color):
    """Convert hex color string to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def draw_character(surface, bitmap, x, y, scale, fg_color):
    """Draw a character bitmap at the specified position with scaling"""
    for row_idx, row in enumerate(bitmap):
        for col_idx, pixel in enumerate(row):
            if pixel:
                pygame.draw.rect(
                    surface,
                    fg_color,
                    (x + col_idx * scale, y + row_idx * scale, scale, scale)
                )


def draw_grid(surface, grid_color, char_width, char_height, cols, rows, scale, spacing):
    """Draw grid lines between characters"""
    width, height = surface.get_size()

    # Draw vertical lines
    for col in range(cols + 1):
        x = col * (char_width * scale + spacing)
        pygame.draw.line(surface, grid_color, (x, 0), (x, height))

    # Draw horizontal lines
    for row in range(rows + 1):
        y = row * (char_height * scale + spacing)
        pygame.draw.line(surface, grid_color, (0, y), (width, y))


def main():
    args = parse_args()

    # Load font data
    font_data = load_font_data(args.input)
    metadata = font_data.get("metadata", {})
    characters = font_data.get("characters", {})

    if not characters:
        print("Error: No character data found in the font file")
        return 1

    # Get font properties
    char_height = metadata.get("char_height", 24)
    font_name = metadata.get("font", "Unknown")
    font_size = metadata.get("size", 0)
    char_count = metadata.get("char_count", len(characters))

    # Calculate layout
    cols = args.cols
    rows = math.ceil(len(characters) / cols)

    # Find the maximum character width
    max_width = max(char.get("width", 0) for char in characters.values())

    # Calculate window dimensions
    scale = args.scale
    spacing = args.spacing
    window_width = cols * (max_width * scale + spacing) + spacing
    window_height = rows * (char_height * scale + spacing) + spacing

    # Convert colors
    bg_color = hex_to_rgb(args.bg_color)
    fg_color = hex_to_rgb(args.fg_color)
    grid_color = hex_to_rgb(args.grid_color)

    # Initialize Pygame
    pygame.init()
    pygame.display.set_caption(f"VFD Font Viewer - {font_name} ({font_size}px)")
    screen = pygame.display.set_mode((window_width, window_height))
    clock = pygame.time.Clock()

    # Create a font for character labels
    label_font = pygame.font.SysFont("monospace", 10)

    # Characters that need baseline adjustment
    baseline_adjustments = {
        ',': 6,  # Move comma down by 6 pixels
        '.': 6,  # Move period down by 6 pixels
        ';': 6,  # Move semicolon down by 6 pixels
        ':': 3,  # Move colon down by 3 pixels
        '_': 6,  # Move underscore down by 6 pixels
        'g': 2,  # Adjust for characters with descenders
        'j': 2,
        'p': 2,
        'q': 2,
        'y': 2
    }

    # Main loop
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_s:
                    # Save screenshot
                    screenshot_path = f"vfd_font_preview_{Path(args.input).stem}.png"
                    pygame.image.save(screen, screenshot_path)
                    print(f"Screenshot saved to {screenshot_path}")

        # Clear screen
        screen.fill(bg_color)

        # Draw grid
        draw_grid(screen, grid_color, max_width, char_height, cols, rows, scale, spacing)

        # Draw characters
        char_index = 0
        for char, char_data in characters.items():
            row = char_index // cols
            col = char_index % cols

            x = col * (max_width * scale + spacing) + spacing

            # Apply baseline adjustment if needed
            baseline_offset = baseline_adjustments.get(char, 0) * scale
            y = row * (char_height * scale + spacing) + spacing + baseline_offset

            # Draw character bitmap
            bitmap = char_data.get("bitmap", [])
            draw_character(screen, bitmap, x, y, scale, fg_color)

            # Draw character code
            try:
                char_code = f"{ord(char):X}"
                code_surf = label_font.render(char_code, True, grid_color)
                screen.blit(code_surf, (x, y + char_height * scale + 2))
            except:
                pass  # Skip if character can't be encoded

            char_index += 1

        # Update display
        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())