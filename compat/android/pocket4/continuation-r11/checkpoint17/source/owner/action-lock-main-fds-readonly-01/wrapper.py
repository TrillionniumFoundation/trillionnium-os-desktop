import hashlib,json,sys,types
EXPECTED = {'read_main_lock_fds.py': (36349, 'db4916ebee6e6094482236e10ed2ecd3030d7f245de18f53c8a0cfd9c50a2cb0'), 'read_main_identity.py': (18537, '4b955afce019418e98282aa4af549ab1089afc040a5c8990b7713be5f8b4585e'), 'prior-ticket-launch.json': (6053, '13179fb6aa36a1fde53892cc6287994ae269e492199a94eb12eeafe83fe290cc')}
raw = sys.stdin.buffer.read(131073)
if len(raw) != 62709 or hashlib.sha256(raw).hexdigest() != '7ea93adc80cd457641c8c3e4968de42c6fc9720dfe0af5492f72198601f189ea':
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
reader = load('read_main_lock_fds.py', 'fixed_Main_lock_FD_metadata_reader')
raise SystemExit(reader.main(support, bodies['prior-ticket-launch.json'], ['--collect-once']))
