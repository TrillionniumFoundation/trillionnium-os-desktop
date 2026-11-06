#!/usr/bin/env python3
"""Create a fixed, read-only packet locally; never collect or submit it."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'action-lock-main-fds-readonly-01'
PREVIOUS = HERE.parent / 'action-lock-owner-readonly-01'
RUNTIME_NAMES = ('read_main_lock_fds.py', 'read_main_identity.py', 'prior-ticket-launch.json')
EXPECTED = {
    'read_main_lock_fds.py': (36349, 'db4916ebee6e6094482236e10ed2ecd3030d7f245de18f53c8a0cfd9c50a2cb0'),
    'read_main_identity.py': (18537, '4b955afce019418e98282aa4af549ab1089afc040a5c8990b7713be5f8b4585e'),
    'prior-ticket-launch.json': (6053, '13179fb6aa36a1fde53892cc6287994ae269e492199a94eb12eeafe83fe290cc'),
}
PACKET_LIMIT = 131072


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def dump(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + '\n').encode('ascii')


def record(path, raw):
    return dict(path=path, bytes=len(raw), sha256=sha(raw), git_blob_sha1=git_blob(raw),
                mode='100644', encoding='utf-8')


def put(name, raw):
    raw.decode('utf-8', 'strict')
    with (OUT / name).open('xb') as stream:
        stream.write(raw)


def main():
    files = {}
    for name in RUNTIME_NAMES:
        raw = (HERE / name).read_bytes()
        assert (len(raw), sha(raw)) == EXPECTED[name], name
        raw.decode('utf-8', 'strict')
        files[name] = raw
    assert not OUT.exists()
    OUT.mkdir(mode=0o700)
    for name in RUNTIME_NAMES + ('check_controls.py', 'controls01.stdout.json', 'controls01.stderr.txt',
                                  'controls01-receipt.json', 'make_request.py'):
        put(name, (HERE / name).read_bytes())
    put('source-manifest.json', dump(dict(schema=1, scope='seven fixed Main PID action-lock FD metadata only',
                                        files=[record(name, files[name]) for name in RUNTIME_NAMES])))
    packet_raw = dump(dict(schema=1, files={name: body.decode('utf-8') for name, body in files.items()}))
    assert len(packet_raw) <= PACKET_LIMIT
    put('request-stdin.json', packet_raw)
    wrapper = '''import hashlib,json,sys,types
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
reader = load('read_main_lock_fds.py', 'fixed_Main_lock_FD_metadata_reader')
raise SystemExit(reader.main(support, bodies['prior-ticket-launch.json'], ['--collect-once']))
'''.replace('EXPECTED_LITERAL', repr(EXPECTED)).replace('PACKET_BYTES', str(len(packet_raw))).replace('PACKET_SHA', repr(sha(packet_raw)))
    wrapper_raw = wrapper.encode('utf-8')
    ast.parse(wrapper_raw)
    put('wrapper.py', wrapper_raw)
    request = dict(host='pocket4', executable='/usr/bin/sudo',
                   args=['-n', '/usr/bin/python3', '-I', '-B', '-c', wrapper],
                   cwd='/', env={'PYTHONDONTWRITEBYTECODE': '1'}, stdin=packet_raw.decode('utf-8'),
                   idempotency_key='p4-action-lock-main-fds-readonly01-' + sha(packet_raw)[:16],
                   cpu_quota_percent=100, memory_max_bytes=134217728, nice=10, timeout_seconds=30)
    put('exact-request.json', dump(request))
    original = (PREVIOUS / 'read_lock_owner.py').read_bytes()
    assert len(original) == 21531 and sha(original) == 'c19d8a6ff875ee26e0754a91799d6bd901a50efc9b7fe2069a84a127b9e27019'
    delta = ''.join(difflib.unified_diff(original.decode().splitlines(True), files['read_main_lock_fds.py'].decode().splitlines(True),
                    fromfile='previous/read_lock_owner.py', tofile='candidate/read_main_lock_fds.py')).encode()
    put('lock-table-to-fixed-Main-FD.patch', delta)
    put('README.md', '''# Fixed seven-process action-lock FD observation

This request prepares one read-only diagnostic after Ticket's retained zero-action
launch failure. It is not a new UI attempt. Root alone submits the exact request
after review. The earlier Amazon/Ticket failures and the two empty lock-table
observations remain unchanged.

## Reads and bounds

The exact lock is `/run/lock/android-digitalis-actions.lock`, device 28, inode
8312, root UID/GID, regular mode 0600 and one link. It is held with O_PATH and
checked again by a no-follow named walk. Its contents are never read.

The process list is exactly the existing Main daemon, launcher, presenter, init,
surfaceflinger, system_server and zygote64. Numeric PIDs and birth ticks are fixed
in source. Parent PID, UID, namespace-PID list, PID/mount namespace, executable
and cgroup must match the unchanged SHA-pinned activation input. Each process is
sampled around its FD enumeration using a held proc directory and held pidfd;
the pidfd is only polled for liveness and is never used for signaling/getfd.

Only the seven fixed `/proc/PID/fd` directories are enumerated: at most 4,096
entries each and 16,384 total. Each entry receives a target stat only. No
unrelated FD content or link target is read or exported. Only exact device/inode
matches may open the corresponding numeric `fdinfo` entry; those reads are at
most 16 KiB each, with at most 64 matching FDs and 32 lock rows per FD. Filtered
output contains regular-file fdinfo scalars and exact-inode lock records. A
malformed/changed entry or unavailable metadata remains explicit and prevents
complete collection. There is no whole-/proc scan and no /proc/locks reread.

Fixed self PID/mount namespace metadata and the one `/proc` mountinfo record
provide context. Unrelated mountinfo rows are not exported. Namespace labels are
evidence, never paths used to enter or read another namespace. The `/proc` record
does not establish the superblock's PID namespace by itself.

The original 18,537-byte Main support source and all five existing input hashes
are unchanged. The exact original guard runs before/after and still requires
pids.max 12288. Boot, five held/named inputs and lock identity are checked at the
end. The collector has a 15-second cooperative deadline and 2 MiB output bound;
the original outer contract remains 30 seconds, one CPU and 128 MiB.

## Meaning of the result

This is sequential sampling, not an atomic process/FD/lock snapshot. Matching
inode metadata does not prove the same open file description, who acquired a
lock, or who historically transferred an FD. FDinfo numeric PID 0/-1 or another
PID is reported without probing that PID or granting birth/cleanup authority.
No matches do not prove no holder. Collection never grants a retry, signal,
cleanup or runtime authorization. All such qualification fields remain false.

There is no flock/lockf, pidfd_getfd, SCM_RIGHTS, signal, subprocess, namespace
entry, lock write/replacement/deletion or Android action. Only the process's
stdout is emitted. Opened descriptors are registered before later failures;
close is attempted once, close errors remain explicit, and a first error is not
replaced by cleanup errors.

## Local verification

Ten actual local controls cover the production parsers, exact retained Ticket
failure binding, numeric names and bounded owned-directory enumeration. They
also use real local owned directory/pipe descriptors to check first/last parent
close failures, iterator-close failures and preservation of an earlier error.
They do not call collect, read /proc/Main or execute Hepta. PLAN is the source
default; the separately reviewed exact request explicitly asks for collect-once.
These controls are not device or kernel qualification.

The transport has exactly three UTF-8 members: new reader, unchanged original
support source, and the retained 6,053-byte Ticket failure. The in-memory wrapper
checks full packet length/SHA and every member before loading either module.
Python -I -B preserves isolated imports and disables bytecode writes. The input
transport bound is 128 KiB; this does not change any observed-data bound above.
'''.encode('utf-8'))
    print(json.dumps(dict(output=str(OUT), request=record('exact-request.json', (OUT/'exact-request.json').read_bytes()),
                          stdin=record('request-stdin.json', packet_raw), wrapper=record('wrapper.py', wrapper_raw),
                          idempotency_key=request['idempotency_key']), sort_keys=True))


if __name__ == '__main__':
    main()
