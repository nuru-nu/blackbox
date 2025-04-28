"""Sends animated typing text to VFD.

Hardware description + ESP32 firmware:
https://github.com/BorisBegemann/Futaba-VFD

NOTE: You need the updated firmware with the UDP handler!
"""

import time
import socket
import argparse
import json
import datetime
import re


# Parse command line arguments
def parse_args():
  parser = argparse.ArgumentParser(description='VFD Generator')
  parser.add_argument('--dst', default='127.0.0.1', help='UDP destination address')
  parser.add_argument('--port', type=int, default=31337, help='UDP destination port')
  parser.add_argument('--text', default='20250424_122832.json', help='Path to JSON file containing text array')
  parser.add_argument('--font', default='vfd_font.json', help='Font file in JSON format')
  parser.add_argument('--first-hours', type=float, default=5, help='Hours to spend on first text')
  parser.add_argument('--last-hours', type=float, default=19, help='Hours to spend on last text')
  parser.add_argument('--default-hours', type=float, default=24, help='Hours to spend on each text between first and last')
  parser.add_argument('--start', default='20250424-190000',
                      help='Start time for animation in YYYYMMDD-HHMMSS format (defaults to current time + 10 seconds)')
  parser.add_argument('--rotate-180', action='store_true', help='Rotate the display output by 180 degrees')
  parser.add_argument('--debug-interval', type=int, default=0,
                      help='Interval in seconds between debug status logs (0 = disabled)')
  return parser.parse_args()

args = parse_args()

# Constants for the display
DISPLAY_WIDTH, DISPLAY_HEIGHT = 336, 24
PADDING = 0

# Scale cursor with font size
CURSOR_WIDTH = 10
CURSOR_HEIGHT = 20
CURSOR_SECS = 0.5
WAITING_MESSAGE = ""

SENTENCE_RE = re.compile(r'([^.!?]+[.!?]+\s*)')


def convert_to_bitmap(disp):
  num_bytes = (DISPLAY_HEIGHT * DISPLAY_WIDTH + 7) // 8
  bitmap = bytearray(num_bytes)

  for y in range(DISPLAY_HEIGHT):
    for x in range(DISPLAY_WIDTH):
      if args.rotate_180:
        pixel = disp[DISPLAY_HEIGHT - 1 - y][DISPLAY_WIDTH - 1 - x]
      else:
        pixel = disp[y][x]

      if pixel:
        pixel_index = y * DISPLAY_WIDTH + x
        byte_index = pixel_index // 8
        bit_index = 7 - (pixel_index % 8) # VFD hardware might expect MSB first
        bitmap[byte_index] |= (1 << bit_index)

  return bitmap


sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
def send(disp):
  bitmap = convert_to_bitmap(disp)
  try:
    sock.sendto(bitmap, (args.dst, args.port))
  except socket.gaierror as e:
    print(f"\nError: Cannot resolve hostname/IP: {args.dst}. Check network settings. ({e})")
    time.sleep(2) # Prevent spamming errors, shorter sleep
  except OSError as e:
      if e.errno == 101: # Network is unreachable
        log_msg = f"Network Error: Network is unreachable for {args.dst}:{args.port}. Retrying..."
      else:
        log_msg = f"Network Error: {e}. Check IP/Port ({args.dst}:{args.port}) and network connection."
      print(f"\n{log_msg}")
      time.sleep(2) # Shorter sleep
  except Exception as e:
    print(f"\nError sending frame: {e}")
    time.sleep(1) # Short sleep for general errors


def parse_sentences(start, texts):
  t = start
  t0 = time.monotonic()
  all_sentences = []
  for i, text in enumerate(texts):
    if i == 0:
      hours = args.first_hours
    elif i == len(texts) - 1:
      hours = args.last_hours
    else:
      hours = args.default_hours

    cpm = len(text) / (hours * 60)
    day = start + datetime.timedelta(days=i)
    print(f'day {i:2} - {day.strftime("%Y-%m-%d")} {len(text):6} chars / {hours:2} hours = {cpm:5.1f} cpm')

    matches = SENTENCE_RE.findall(text)
    if matches:
      sentences = matches
    else:
      sentences = [text]

    for j, sentence in enumerate(sentences):
      t1 = t + datetime.timedelta(minutes=len(sentence) / cpm)
      sentences[j] = (sentence, t, t1)
      t = t1

    all_sentences.extend(sentences)

  print(f'Parsed {len(all_sentences)} sentences in {((time.monotonic() - t0) * 1000):.1f} ms')
  print(f'from {all_sentences[0][1]} to {all_sentences[-1][2]}')
  return all_sentences


class Cursor:

  def __init__(self):
    self.state = 0
    self.secs = CURSOR_SECS

  def sleep(self, disp, secs, x0, y0):
    def set(value):
      for y in range(CURSOR_HEIGHT):
        for x in range(CURSOR_WIDTH):
          disp[y0 + y][x0 + x] = value
    remaining = secs
    set(self.state)
    while remaining > 0:
      secs = min(remaining, self.secs)
      remaining -= secs
      self.secs -= secs
      send(disp)
      time.sleep(secs)
      if self.secs <= 0:
        self.secs = CURSOR_SECS
        self.state = 1 - self.state
        set(self.state)
    set(0)

def play_sentence(sentence, t1, t2, font):
  ts = []
  for i, c in enumerate(sentence):
    if c in '.!?;':
      # pause after punctuation
      ts.append(5)
    elif c in (' ', '\n'):
      # pause before whitespace
      j = i - 1
      while j > 0:
        if ts[j]:
          ts[j] += {' ': 1.2, '\n': 5}[c]
          break
        j -= 1
      ts.append(0)
    else:
      ts.append(1)
  f = (t2.timestamp() - t1.timestamp()) / sum(ts)
  ts = [(t * f) for t in ts]

  disp = [[0 for _ in range(DISPLAY_WIDTH)] for _ in range(DISPLAY_HEIGHT)]

  x0, y0 = PADDING, PADDING
  fc = font['characters']
  t = 0
  cursor = Cursor()
  for i, c in enumerate(sentence):
    c = {'\n': ' '}.get(c, c)
    w = fc[c]['width']
    x0 += w
    scroll = x0 - (DISPLAY_WIDTH - PADDING - CURSOR_WIDTH)
    if scroll > 0:
      disp = [row[scroll:] + [0] * (DISPLAY_WIDTH - scroll) for row in disp]
      x0 -= scroll
    for y in range(fc[c]['height']):
      for x in range(fc[c]['width']):
        disp[y0 + y][x0 - w + x] = fc[c]['bitmap'][y][x]

    t += ts[i]
    dt = t - (time.time() - t1.timestamp())
    if dt > 0:
      cursor.sleep(disp, dt, x0, y0)


def main():
  start = datetime.datetime.strptime(args.start, '%Y%m%d-%H%M%S')
  texts = json.load(open(args.text))
  sentences = parse_sentences(start, texts)

  font = json.load(open(args.font))
  now = datetime.datetime.now()
  for i, (sentence, t1, t2) in enumerate(sentences):
    if now >= t1 and now < t2:
      print(f'{now} - sentence {i} {repr(sentence)}')
      play_sentence(sentence, t1, t2, font)
      now = datetime.datetime.now()


if __name__ == '__main__':
  main()
