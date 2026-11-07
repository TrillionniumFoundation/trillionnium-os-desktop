#!/usr/bin/env python3
"""Create-only matched host source03 and build03; no service, namespace or Android execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

SOURCE = Path('/home/alex/work/pocket4-owned-factory-v2-host-source-03')
OUT = Path('/home/alex/work/pocket4-owned-factory-v2-host-build-03')
EXPECTED = {'client_control.cc': {'sha256': 'bcfbc01d02c089d01f8bcd34fb939655055b51611dfde7621e31747948c962fb', 'bytes': 19946}, 'bionic_branch_view.cc': {'sha256': '0eaf591282192e3675c44be6ad8ecb37441237082013cd8743b4f5d8ad664857', 'bytes': 784}, 'audit_worker_binary.py': {'sha256': 'bda5819b28745571a9a236199052e047b806a96a7d094e0f61732d3858e71bc9', 'bytes': 5841}, 'build_fixture.py': {'sha256': '856cc25f68bc6c782f15517e12aba7f88ae3a6db7de7d91999dfa2e57a14c4f7', 'bytes': 13411}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-once', action='store_true')
    args = parser.parse_args()
    if not args.execute_once:
        print(json.dumps({'state': 'PLAN_ONLY', 'source': str(SOURCE), 'output': str(OUT),
                          'service_started': False, 'Android_execution': False}))
        return 0
    if os.geteuid() == 0:
        raise RuntimeError('existing unprivileged operator required')
    packet = globals().get('PACKET')
    if not isinstance(packet, dict) or packet.get('schema') != 1 or set(packet.get('files', {})) != set(EXPECTED):
        raise RuntimeError('verified four-file packet required')
    raw_files = {}
    for name, wanted in EXPECTED.items():
        row = packet['files'][name]
        raw = row['text'].encode()
        if len(raw) != wanted['bytes'] or hashlib.sha256(raw).hexdigest() != wanted['sha256']:
            raise RuntimeError('source packet pin differs: ' + name)
        if row['sha256'] != wanted['sha256'] or row['bytes'] != wanted['bytes']:
            raise RuntimeError('source packet declaration differs: ' + name)
        if name.endswith('.py'):
            compile(raw, name, 'exec')
        raw_files[name] = raw
    if SOURCE.parent != Path('/home/alex/work') or OUT.parent != SOURCE.parent:
        raise RuntimeError('fixed task roots required')
    if SOURCE.exists() or SOURCE.is_symlink() or OUT.exists() or OUT.is_symlink():
        raise RuntimeError('source03 or build03 already exists; do not overwrite or retry')
    build = raw_files['build_fixture.py']
    scope = {'__name__': '_verified_host_build03_preflight', '__file__': str(SOURCE / 'build_fixture.py')}
    exec(compile(build, str(SOURCE / 'build_fixture.py'), 'exec'), scope, scope)
    scope['inventory']()
    if scope['pin'](scope['COMPILER'])['sha256'] != scope['COMPILER_SHA']:
        raise RuntimeError('compiler changed before source creation')
    SOURCE.mkdir(mode=0o700)
    for name, raw in raw_files.items():
        descriptor = os.open(SOURCE / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    for name, wanted in EXPECTED.items():
        raw = (SOURCE / name).read_bytes()
        if len(raw) != wanted['bytes'] or hashlib.sha256(raw).hexdigest() != wanted['sha256']:
            raise RuntimeError('created source differs')
    sys.argv = [str(SOURCE / 'build_fixture.py'), '--execute', '--out', str(OUT)]
    return scope['main']()


if __name__ == '__main__':
    raise SystemExit(main())
