"""Disposable Claude/Codex simulator using an actual subprocess. No API keys."""
import json
import sys

kind = sys.argv[1]
payload = json.load(sys.stdin)
if payload.get('fail'): sys.exit(9)
if kind == 'IMPLEMENT':
 print(json.dumps({'artifact': payload['text'].strip().lower().replace(' ','-')}))
elif kind == 'REVIEW':
 print(json.dumps({'verdict':'APPROVE' if payload['artifact']==payload['expected'] else 'REQUEST_CHANGES'}))
else: sys.exit(2)
