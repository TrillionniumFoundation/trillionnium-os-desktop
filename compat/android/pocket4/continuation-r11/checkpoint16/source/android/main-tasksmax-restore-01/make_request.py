#!/usr/bin/env python3
"""Offline sealing only. This program never submits a remote job."""
import base64
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = ('binding.json', 'prior-main-identity-original.json', 'read_main_identity.py',
         'restore_main.py', 'stage_execute.py')


def raw_json(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('ascii')


def create(name, body):
    with (HERE / name).open('xb') as stream:
        stream.write(body)


def main():
    files = {name: (HERE / name).read_bytes() for name in NAMES}
    manifest = dict(schema=1, revision=1, purpose='restore-original-main-tasksmax-only', files={
        name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) for name, body in files.items()})
    manifest_raw = raw_json(manifest)
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    packet = dict(schema=1, manifest=manifest_raw.decode('ascii'),
                  files={name: base64.b64encode(body).decode('ascii') for name, body in files.items()})
    stdin = raw_json(packet)
    stage_sha = manifest['files']['stage_execute.py']['sha256']
    wrapper = (
        "import base64,hashlib,json,sys;raw=sys.stdin.buffer.read(" + str(len(stdin) + 1) + ");"
        "assert len(raw)==" + str(len(stdin)) + " and hashlib.sha256(raw).hexdigest()=='" +
        hashlib.sha256(stdin).hexdigest() + "';p=json.loads(raw);"
        "s=base64.b64decode(p['files']['stage_execute.py'],validate=True);"
        "assert len(s)==" + str(len(files['stage_execute.py'])) +
        " and hashlib.sha256(s).hexdigest()=='" + stage_sha + "';"
        "g={'__name__':'fixed_main_restore_stage','__file__':'<verified-in-memory-main-restore-stage>'};"
        "exec(compile(s,g['__file__'],'exec'),g);raise SystemExit(g['main'](p,'" + manifest_sha + "',True))"
    )
    request = dict(host='pocket4', executable='/usr/bin/sudo',
                   args=['-n', '/usr/bin/python3', '-I', '-B', '-c', wrapper],
                   cwd='/home/alex/work', env={'PYTHONDONTWRITEBYTECODE': '1'}, stdin=stdin.decode('ascii'),
                   cpu_quota_percent=100, memory_max_bytes=134217728, nice=10,
                   timeout_seconds=90, idempotency_key='pocket4-main-tasksmax-restore-01-20261105')
    create('source-manifest.json', manifest_raw)
    create('request-stdin.json', stdin)
    create('exact-request.json', raw_json(request))
    create('wrapper.py', (wrapper + '\n').encode('ascii'))
    print(json.dumps({name: dict(bytes=(HERE / name).stat().st_size,
                                 sha256=hashlib.sha256((HERE / name).read_bytes()).hexdigest())
                      for name in ('source-manifest.json', 'request-stdin.json', 'exact-request.json', 'wrapper.py')},
                     sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
