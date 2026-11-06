import hashlib,json,sys,types
EXPECTED = {'probe_lock.py': (35329, 'caad07035d43dd0e76d8cb0af33b455b2e77eff2aceb90d90c80f0162ee9a49d'), 'read_main_identity.py': (18537, '4b955afce019418e98282aa4af549ab1089afc040a5c8990b7713be5f8b4585e'), 'prior-ticket-launch.json': (6053, '13179fb6aa36a1fde53892cc6287994ae269e492199a94eb12eeafe83fe290cc'), 'prior-admission.json': (8816, 'cdbd347f32d7a48ec5e95106580208171f45fd3883c008c2e8aab30fa980624e')}
raw = sys.stdin.buffer.read(131073)
if len(raw) != 71354 or hashlib.sha256(raw).hexdigest() != '97b28aa84b98ea22f7fd394530118d2d3d5d085c5744f5fe74d5cc93aabf800a':
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
probe = load('probe_lock.py', 'fixed_two_arm_lock_differential')
raise SystemExit(probe.main(support, bodies['prior-ticket-launch.json'], bodies['prior-admission.json'], ['--admit-once']))
