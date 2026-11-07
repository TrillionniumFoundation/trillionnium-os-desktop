#!/usr/bin/env python3
"""Freeze the bounded visible-PID read-only request locally; never submit it."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'action-lock-visible-pids-readonly-01'
EXPECTED = {
    'read_visible_lock_fds.py': (41061, '8fed4dffbfb67467571189895f6dc56e8bd13aba0fba094107260526a697200e'),
    'read_main_identity.py': (18537, '4b955afce019418e98282aa4af549ab1089afc040a5c8990b7713be5f8b4585e'),
    'prior-ticket-launch.json': (6053, '13179fb6aa36a1fde53892cc6287994ae269e492199a94eb12eeafe83fe290cc'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + '\n').encode('ascii')


def record(name, raw):
    return dict(path=name, bytes=len(raw), sha256=sha(raw),
        git_blob_sha1=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),mode='100644',encoding='utf-8')


def put(name, raw):
    raw.decode('utf-8', 'strict')
    with (OUT/name).open('xb') as stream:
        stream.write(raw)


def main():
    bodies={name:(HERE/name).read_bytes() for name in EXPECTED}
    for name,body in bodies.items():
        assert (len(body),sha(body))==EXPECTED[name]
        body.decode('utf-8','strict')
    assert not OUT.exists()
    OUT.mkdir(mode=0o700)
    for name in tuple(EXPECTED)+('check_new_controls.py','controls01.stdout.json','controls01.stderr.txt',
                                'controls01-receipt.json','main7-to-visible-PIDs.patch','README.md','make_request.py'):
        put(name,(HERE/name).read_bytes())
    put('source-manifest.json',dump(dict(schema=1,scope='one bounded visible numeric-PID exact lock-FD metadata scan',
                                       files=[record(name,body) for name,body in bodies.items()])))
    packet=dump(dict(schema=1,files={name:body.decode('utf-8') for name,body in bodies.items()}))
    assert len(packet)<=131072
    put('request-stdin.json',packet)
    wrapper='''import hashlib,json,sys,types
EXPECTED = EXPECTED_LITERAL
raw = sys.stdin.buffer.read(131073)
if len(raw) != PACKET_BYTES or hashlib.sha256(raw).hexdigest() != PACKET_SHA:
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
reader = load('read_visible_lock_fds.py', 'fixed_visible_PID_lock_FD_metadata_reader')
raise SystemExit(reader.main(support, bodies['prior-ticket-launch.json'], ['--collect-once']))
'''.replace('EXPECTED_LITERAL',repr(EXPECTED)).replace('PACKET_BYTES',str(len(packet))).replace('PACKET_SHA',repr(sha(packet)))
    ast.parse(wrapper)
    put('wrapper.py',wrapper.encode())
    request=dict(host='pocket4',executable='/usr/bin/sudo',args=['-n','/usr/bin/python3','-I','-B','-c',wrapper],
                 cwd='/',env={'PYTHONDONTWRITEBYTECODE':'1'},stdin=packet.decode(),
                 idempotency_key='p4-action-lock-visible-fds-readonly01-'+sha(packet)[:16],
                 cpu_quota_percent=100,memory_max_bytes=134217728,nice=10,timeout_seconds=30)
    put('exact-request.json',dump(request))
    print(json.dumps(dict(directory=str(OUT),request=record('exact-request.json',(OUT/'exact-request.json').read_bytes()),
                          stdin=record('request-stdin.json',packet),wrapper=record('wrapper.py',wrapper.encode()),
                          idempotency_key=request['idempotency_key']),sort_keys=True))


if __name__=='__main__':
    main()
