#!/usr/bin/env python3
# Fixed create-only package preparation; this entry does not run the canary.
import base64, hashlib, json, sys, types
PACKET_SHA256 = __PACKET_SHA256__
PACKET_BASE64 = __PACKET_BASE64__
raw = base64.b64decode(PACKET_BASE64, validate=True)
if hashlib.sha256(raw).hexdigest() != PACKET_SHA256:
    raise RuntimeError('fixed preparation packet digest differs')
packet = json.loads(raw)
for name, row in packet['sources'].items():
    body = row['content'].encode('utf-8')
    if len(body) != row['bytes'] or hashlib.sha256(body).hexdigest() != row['sha256']:
        raise RuntimeError('fixed source packet member differs: ' + name)
for name in ('pinned_support', 'owned', 'prepare'):
    row = packet['sources'][name + '.py']
    module = types.ModuleType(name)
    module.__file__ = '<frozen-owner07-normal01>/' + name + '.py'
    sys.modules[name] = module
    exec(compile(row['content'], module.__file__, 'exec'), module.__dict__)
raise SystemExit(sys.modules['prepare'].main(json.loads(packet['plan_utf8']), packet['sources']))
