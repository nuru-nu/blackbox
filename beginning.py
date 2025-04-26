
import json
import sys

beginning = open('beginning.txt').read()
paragraphs = beginning.split('\n\n')
paragraphs = [p.replace('\n', ' ') for p in paragraphs if p.strip()]
beginning = '\n\n'.join(paragraphs)

ts = json.load(open(sys.argv[1]))

t = ts[0]
t = t[len(beginning):]
t = t[t.index('\n'):]
t = beginning + t

print(len(ts[0]), '->', len(t))

ts[0] = t

with open(sys.argv[1] + '.modified', 'w') as f:
  json.dump(ts, f)
