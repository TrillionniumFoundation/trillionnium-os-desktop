"""Run only the exact test peer script, never Rust/Owner/Android or namespaces."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess

ROOT = Path(__file__).resolve().parent
source = ROOT / 'candidate/runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs'
raw = source.read_bytes()
text = raw.decode()
prefix = '    const RETIREMENT_PEER: &str = r#"'
assert text.count(prefix) == 1
script = text.split(prefix, 1)[1].split('"#;', 1)[0]
compile(script, '<exact-Rust-test-peer>', 'exec')


def actual_case(name, frames, code, request=b'', hold=False):
    parent, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    control, peer_control = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    for sock in (parent, peer, control, peer_control):
        sock.settimeout(2)
    stdin = os.memfd_create('owned-retirement-peer-input', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    child = None
    try:
        data = (str(code) + '\n' + request.hex() + '\n' + str(int(hold)) + '\n'
                + ''.join(frame.hex() + '\n' for frame in frames)).encode()
        assert len(data) <= 32768
        assert os.write(stdin, data) == len(data)
        os.lseek(stdin, 0, os.SEEK_SET)
        fcntl.fcntl(stdin, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        child = subprocess.Popen(['/usr/bin/python3', '-I', '-B', '-c', script,
                                  str(peer.fileno()), str(peer_control.fileno())],
                                 stdin=stdin, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                 pass_fds=(peer.fileno(), peer_control.fileno()))
        peer.close(); peer_control.close()
        assert control.recv(2) == b'R'
        assert control.send(b'G') == 1
        if request:
            assert parent.send(request) == len(request)
        observed = [parent.recv(len(frame) + 1) for frame in frames]
        assert observed == frames
        if hold:
            assert child.poll() is None
            assert control.send(b'X') == 1
        assert child.wait(timeout=2) == code
        assert parent.recv(1) == b''
        stderr = child.stderr.read(4097)
        assert stderr == b''
        return {'case': name, 'frame_sizes': [len(frame) for frame in frames],
                'exact_exit': code, 'reaped': True, 'peer_EOF': True, 'forced_kill': False,
                'Rust_retire_called': False}
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)
            if child.stderr is not None:
                child.stderr.close()
        os.close(stdin)
        for sock in (parent, peer, control, peer_control):
            sock.close()


results = [
    actual_case('queued-two-frames-exit-zero', [bytes(range(256)) * 10, b'Z' * 160], 0),
    actual_case('queued-fault-exit-one', [b'A' * 2560, b'R' * 160], 1),
    actual_case('one-exact-request', [b'A' * 2560, b'R' * 160], 0, request=b'Q' * 48),
    actual_case('terminal-frames-while-child-held', [b'A' * 2560, b'R' * 160], 0, hold=True),
    actual_case('bare-EOF', [], 0),
]
report = {'schema': 1, 'verdict': 'LOCAL_EXACT_TEST_PEER_MECHANICS_PASS_ONLY',
          'source': {'path': str(source), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()},
          'script_sha256': hashlib.sha256(script.encode()).hexdigest(), 'actual_cases': results,
          'Rust_compiled_or_tests_executed': False, 'production_protocol_qualified': False,
          'actual_Owner_or_Android_or_namespaces_executed': False, 'Hepta_calls': 0}
body = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
with (ROOT / 'owned-peer-fixture-result.json').open('xb') as stream:
    stream.write(body)
print(json.dumps({'path': str(ROOT / 'owned-peer-fixture-result.json'), 'bytes': len(body),
                  'sha256': hashlib.sha256(body).hexdigest(), 'actual_cases': len(results)}))
