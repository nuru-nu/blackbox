"""Sends timed marquee text (with glitch!) to VFD.

Hardware description + ESP32 firmware:
https://github.com/BorisBegemann/Futaba-VFD

NOTE: You probably want to use vfd_generate.py and the updated firmware instead.
"""

import http.client
import time
import sys
from urllib.parse import urlencode

def send_get_request_with_params(host, path="/", params=None, port=80):
  if 'dryrun' in sys.argv:
    print(time.strftime('%H:%M:%S', time.localtime()), params)
    return

  if params:
    query_string = urlencode(params)
    full_path = f"{path}?{query_string}"
  else:
    full_path = path

  conn = http.client.HTTPConnection(host, port)
  try:
    conn.request("GET", full_path)
    response = conn.getresponse()
    data = response.read().decode('utf-8', errors='replace')
    return {
        'status': response.status,
        'reason': response.reason,
        'headers': response.getheaders(),
        'data': data
    }
  finally:
    conn.close()

text = open('text.txt').read()
print('Read', len(text), 'characters')
text = text.replace('?', '~').encode('ascii', errors='replace').decode('ascii').replace('?', ' ').replace('\n', ' ').replace('~', '?')
print(text)

Y0 = 4
SIZE = 2
PERIOD_SECS = 16.0
DISPLAY_WIDTH = 28
BUFFER_LENGTH = 85

text = ' ' * DISPLAY_WIDTH + text
pos = 0

def write(text, scroll=1):
  return send_get_request_with_params('10.20.30.234', '/write', dict(
      text=text,
      scroll=scroll,
      y=Y0,
      size=SIZE,
  ))

while pos < len(text):
  t0 = time.time()
  t = (text + ' ' * BUFFER_LENGTH)[pos: pos + BUFFER_LENGTH]
  write(t, scroll=0)
  write(t, scroll=1)
  pos += BUFFER_LENGTH - DISPLAY_WIDTH
  dt = time.time() - t0
  time.sleep(PERIOD_SECS * (1 - DISPLAY_WIDTH / BUFFER_LENGTH) - dt)
