import hashlib,json,sys,types
EXPECTED = {'probe_lock.py': (16466, 'c98c6031edf12b7984c06553e429afcb4430f6e2dce7a10b143691b39a8a8368'), 'read_main_identity.py': (18537, '4b955afce019418e98282aa4af549ab1089afc040a5c8990b7713be5f8b4585e'), 'prior-ticket-launch.json': (6053, '13179fb6aa36a1fde53892cc6287994ae269e492199a94eb12eeafe83fe290cc')}
raw = sys.stdin.buffer.read(131073)
if len(raw) != 42440 or hashlib.sha256(raw).hexdigest() != 'e3691dba4d0e19974584ce0f03cd075dc18c576c6a0c65b46581c5bde8f39e74':
    raise SystemExit('fixed packet size or SHA256 mismatch')
packet = json.loads(raw)
if type(packet) is not dict or set(packet) != {'schema', 'files'} or type(packet['schema']) is not int or packet['schema'] != 1:
    raise SystemExit('fixed packet schema mismatch')
if type(packet['files']) is not dict or set(packet['files']) != set(EXPECTED):
    raise SystemExit('fixed packet member set mismatch')
bodies = {}
for name, expected in EXPECTED.items():
    value = packet['files'][name]
    if type(value) is not str:
        raise SystemExit('fixed packet member type mismatch')
    body = value.encode('utf-8')
    if len(body) != expected[0] or hashlib.sha256(body).hexdigest() != expected[1]:
        raise SystemExit('fixed packet member size or SHA256 mismatch')
    bodies[name] = body
def load(name, module_name):
    module = types.ModuleType(module_name)
    module.__file__ = '<fixed-packet:' + name + '>'
    exec(compile(bodies[name], module.__file__, 'exec'), module.__dict__)
    return module
support = load('read_main_identity.py', 'fixed_original_Main_identity_support')
probe = load('probe_lock.py', 'fixed_single_lock_admission')
raise SystemExit(probe.main(support, bodies['prior-ticket-launch.json'], ['--admit-once']))
