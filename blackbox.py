# pip install paho-mqtt pygame colorama

import os.path
mp3_path = os.path.expanduser('~/Downloads/audio.mp3')
viseme_path = os.path.expanduser('~/Downloads/visemes.json')
shelly = '3494546EF893'

import json
visemes = json.load(open(viseme_path))

import paho.mqtt.client as mqtt
import colorama
colorama.init()

broker = '127.0.0.1'
port = 1883

# Create an MQTT client instance
client = mqtt.Client()
client.username_pw_set('guest', 'guest')

# Connect to the MQTT broker
client.connect(broker, port, 60)

connected = False


import datetime

def log(msg, fg=None):
  tsfmt = colorama.Fore.BLUE
  fmt0 = colorama.Style.RESET_ALL
  ts = datetime.datetime.now().strftime('%H:%M:%S')
  msgfmt = {
      None: "",
      "red": colorama.Fore.RED,
      "blue": colorama.Fore.BLUE,
      "green": colorama.Fore.GREEN,
  }[fg]
  print(f'[{tsfmt}{ts}{fmt0}] {msgfmt}{msg}{fmt0}')


def on_connect(client, userdata, flags, reason_code):
  log(f"Connected with result code {reason_code}", fg='green')
  global connected
  connected = True

# def on_publish(client, userdata, mid):
#     print('on_publish', mid)
# client.on_publish = on_publish

client.on_connect = on_connect

# client.loop_forever()

import time
client.loop_start()
while True:
  time.sleep(0.11)
  if connected:
    break


def shelly_set(value: int):
  msg = client.publish(f'shellies/ShellyVintage-{shelly}/light/0/set', json.dumps({
      'turn': 'on',
      'brightness': int(value / 255 * 100),
      'transition': 0,
  }))


import pygame
import time

pygame.mixer.init()
pygame.mixer.music.load(mp3_path)
pygame.mixer.music.play()

for offset, viseme_id in visemes:
  pos = pygame.mixer.music.get_pos()
  sleep = max(0, offset / 1e7 - pos / 1000)
  value = 40 + viseme_id
  log(f'sleeping {int(sleep*1000)}ms -> set to {value}')
  time.sleep(sleep)
  shelly_set(value)

t0 = time.time()
while pygame.mixer.music.get_busy():
  time.sleep(0.01)
dt = time.time() - t0
if dt > 1:
  log(f'played for extra {dt:.1f}s at end')

client.loop_stop()
