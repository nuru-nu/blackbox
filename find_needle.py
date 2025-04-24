import json
import sys

ts = json.load(open(sys.argv[1]))
needle = sys.argv[2]

for i, t in enumerate(ts):
  # Find all occurrences of needle in t
  positions = []
  start = 0
  while True:
    pos = t.find(needle, start)
    if pos == -1:
      break
    # Calculate relative position as percentage
    rel_pos = (pos / len(t)) * 100 if len(t) > 0 else 0
    positions.append((pos, f"{rel_pos:.2f}%"))
    start = pos + 1

  # Print all occurrences with their positions
  if positions:
    print(f"Text {i}: Found {len(positions)} occurrences of '{needle}'")
    for abs_pos, rel_pos in positions:
      print(f"  Position: {abs_pos} (relative: {rel_pos})")
