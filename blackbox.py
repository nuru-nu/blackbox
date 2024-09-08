import asyncio
import collections
import datetime
import glob
import json
import os
import os.path
import platform
import shlex
import threading
import time

import aiohttp
from aiohttp import web
import colorama
import paho.mqtt.client as mqtt
import pygame


shelly = '3494546EF893'
device_name = 'HID 0e8f:2517'
data_dir = '/tmp/blackbox_data'
os.makedirs(data_dir, exist_ok=True)
running = True

colorama.init()

broker = '127.0.0.1'
port = 1883

client = mqtt.Client()
client.username_pw_set('guest', 'guest')

client.connect(broker, port, 60)

connected = False


loop = asyncio.get_event_loop()

def syncify(f, *arg, **kw):
  asyncio.run_coroutine_threadsafe(f(*arg, **kw), loop)

async def asyncify(f, *arg, **kw):
  return await loop.run_in_executor(None, lambda: f(*arg, **kw))

queues = {}
queues_lock = threading.Lock()

async def add_event(event):
  with queues_lock:
    for queue in queues.values():
      await queue.put(event)


logs = collections.deque(maxlen=100)
logs_lock = threading.Lock()


def log(level, msg):
  tsfmt = colorama.Fore.BLUE
  fmt0 = colorama.Style.RESET_ALL
  ts = datetime.datetime.now().strftime('%H:%M:%S')
  log_event = (ts, level, msg)
  if level != 'debug':
    with logs_lock:
      logs.append(log_event)
  syncify(add_event, ('log', log_event))
  msgfmt = {
      'debug': '',
      'info': '',
      'warning': '',
      'error': colorama.Fore.RED,
  }[level]
  print(f'[{tsfmt}{ts}{fmt0}] {msgfmt}{msg}{fmt0}')


def on_connect(client, userdata, flags, reason_code):
  log('info', f"Connected with result code {reason_code}")
  global connected
  connected = True

# def on_publish(client, userdata, mid):
#     print('on_publish', mid)
# client.on_publish = on_publish

client.on_connect = on_connect

# client.loop_forever()

client.loop_start()

def shelly_set(value: int):
  msg = client.publish(f'shellies/ShellyVintage-{shelly}/light/0/set', json.dumps({
      'turn': 'on',
      'brightness': int(value / 255 * 100),
      'transition': 0,
  }))
  # print(msg.mid)


pygame.mixer.init()

state_lock = threading.Lock()
state = dict(

    base_dir=None,
    sub_dir='monolog',
    index=-1,
    monolog_paths=[],
    dialog_paths=[],
    play_dialog=False,

    visemes_count=-1,
    visemes_index=-1,
)

def get_paths(directory):
  paths = []
  for mp3_path in sorted(glob.glob(f'{directory}/*.mp3')):
    viseme_path = mp3_path[:-3] + 'json'
    if os.path.exists(viseme_path):
      paths.append((mp3_path, viseme_path))
    else:
      print(f'Missing "{viseme_path}"')
  log('info', f'Found {len(paths)} mp3s in "{directory}"')
  return sorted(paths)


def init_paths():
  paths = sorted(glob.glob(f'{data_dir}/*/monolog/*.mp3'))
  if paths:
    state['base_dir'] = '/'.join(paths[-1].split('/')[:-2])
    state['monolog_paths'] = get_paths(f'{state["base_dir"]}/monolog')
    state['dialog_paths'] = get_paths(f'{state["base_dir"]}/dialog')

init_paths()

def set(key, value):
  with state_lock:
    state[key] = value
  syncify(add_event, ('set', (key, value)))
  # print('set', key, value)


def get(key):
  return state[key]


def transition():

  index = get('index')

  if get('sub_dir') == 'monolog':
    paths = get('monolog_paths')
    new_index = (index + 1) % len(paths)
    log('info', f'monolog index={index}->{new_index}')
    set('index', new_index)
    return paths[new_index]

  log('info', f'dialog index={index} -> wait')
  set('play_dialog', False)
  paths = get('dialog_paths')
  new_index = get('index') + 1
  while not get('play_dialog') or new_index >= len(paths):
    if get('sub_dir') == 'monolog':
      log('info', 'switch to monolog index=0')
      set('index', 0)
      return get('monolog_paths')[0]
    time.sleep(0.1)
  log('info', f'-> dialog index={new_index}')
  set('index', new_index)
  return paths[new_index]


def player():

  while get('base_dir') is None:
    log('info', 'base_dir not set')
    time.sleep(1)

  base_dir = get('base_dir')
  log('info', f'initializing with base_dir={base_dir}')

  while True:
    play_one(*transition())


def play_one(mp3_path, viseme_path):
  log('info', f'play {mp3_path}')
  pygame.mixer.music.load(mp3_path)
  pygame.mixer.music.play()

  visemes = json.load(open(viseme_path))
  set('visemes_count',  len(visemes))

  for i, (offset, viseme_id) in enumerate(visemes):
    set('visemes_index', i)
    pos = pygame.mixer.music.get_pos()
    sleep = max(0, offset / 1e7 - pos / 1000)
    value = 40 + viseme_id
    log('debug', f'viseme {i} - sleeping {int(sleep*1000)}ms -> set to {value}')
    time.sleep(sleep)
    shelly_set(value)
  finish_player()


def finish_player():
  t0 = time.time()
  while pygame.mixer.music.get_busy():
    time.sleep(0.01)
  dt = time.time() - t0
  if dt > 1:
    log('warning', f'played for extra {dt:.1f}s at end')


player_thread = threading.Thread(target=player)
player_thread.start()


def press(key):
  log('info', f'pressed {key}')
  if key == 'right':
    set('play_dialog', True)
  if key == 'up':
    set('sub_dir', 'monolog')
  if key == 'down':
    set('sub_dir', 'dialog')


if platform.system() == 'Darwin':
  log('warning', 'running OS X - no support for evdev!')

else:
  import evdev

  def get_device(device_name):
    i = 0
    while True:
      device_path = f'/dev/input/event{i}'
      try:
        device = evdev.InputDevice(device_path)
      except FileNotFoundError:
        return None
      if device.name == device_name:
        print(f'Found device "{device_name}" at "{device_path}"')
        return device
      i += 1

  device = get_device(device_name)
  assert device is not None, f'missing device "{device_name}"'

  def events():
    for event in device.read_loop():
      if event.type == evdev.ecodes.EV_KEY:
        key_event = evdev.categorize(event)
        #print(key_event, key_event.keystate, key_event.keycode)
        if key_event.keystate == key_event.key_down and key_event.keycode == 'KEY_B':
          press('up')
        if key_event.keystate == key_event.key_down and key_event.keycode == 'KEY_UP':
          press('left')
        if key_event.keystate == key_event.key_down and key_event.keycode == 'KEY_DOWN':
          press('right')
        if key_event.keystate == key_event.key_down and key_event.keycode in ('KEY_F5', 'KEY_ESC'):
          press('down')

  events_thread = threading.Thread(target=events)
  events_thread.start()


def update_from_zip(file_path):
  ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
  base_dir = f'{data_dir}/{ts}'

  # if os.path.exists(f'{data_dir}/monolog'): shutil.rmtree(f'{data_dir}/monolog')
  # if os.path.exists(f'{data_dir}/dialog'): shutil.rmtree(f'{data_dir}/dialog')

  os.system(f'unzip -d {shlex.quote(base_dir)} {shlex.quote(file_path)}')
  set('monolog_paths', get_paths(f'{base_dir}/monolog'))
  set('dialog_paths', get_paths(f'{base_dir}/dialog'))
  set('base_dir', base_dir)


def get_index(request: web.Request):
  return web.Response(text=open('index.html').read(), content_type='text/html')


async def post_upload(request: web.Request):
  reader = await request.multipart()

  field = await reader.next()

  if field.name == 'file':
    filename = field.filename
    mime_type = field.headers[aiohttp.hdrs.CONTENT_TYPE]
    if mime_type not in ('application/zip', 'application/x-zip-compressed'):
      raise web.HTTPUnprocessableEntity(text=f'Cannot process mime_type="{mime_type}"')
    file_path = os.path.join(data_dir, filename)

    with open(file_path, 'wb') as f:
      while True:
        chunk = await field.read_chunk()
        if not chunk:
          break
        f.write(chunk)

  await asyncify(update_from_zip, file_path)

  return web.json_response(dict(status='ok'))



async def get_ws(request: web.Request):
  with queues_lock:
    id_ = (max(queues) if queues else 0) + 1
    queue = queues[id_] = asyncio.Queue()

  ws = web.WebSocketResponse()
  await ws.prepare(request)

  await ws.send_json(('state', state))
  for log_event in logs:
    await ws.send_json(('log', log_event))

  print('ws START')
  try:
    while True:
      try:
        await ws.send_json(await queue.get())
      except (asyncio.CancelledError, ConnectionResetError) as e:
        print('caught', type(e), e)
        break
  finally:
    with queues_lock:
      del queues[id_]
    print('ws STOP ->', len(queues), 'left')

  return ws


async def post_set(request: web.Request):
  data = await request.json()
  if data['key'] == 'quit':
    log('warning', 'shutting down!')
    await asyncio.sleep(0.1)
    os._exit(0)  # oops
  elif data['key'] == 'key':
    press(data['value'])
  else:
    set(data['key'], data['value'])
  return web.json_response(dict(status='ok'))


app = web.Application()
app.add_routes([
    web.get('/', get_index),
    web.post('/upload', post_upload),
    web.post('/set', post_set),
    web.get('/ws', get_ws)
])

web.run_app(app, loop=loop)
