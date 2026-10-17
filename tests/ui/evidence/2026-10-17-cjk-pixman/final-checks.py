#!/usr/bin/env python3
import ast
import json
from pathlib import Path
import subprocess
import tomllib

ROOT = Path('/workspace/scratch/98f315e377b2/next-ui')
WRAPPER = '/workspace/scratch/98f315e377b2/next-tools/run-host-rust.py'


def run(arguments):
    print(json.dumps({'command': arguments}), flush=True)
    subprocess.run(arguments, cwd=ROOT, check=True)


run(['python3', WRAPPER, 'rustc', '-Vv'])
run(['python3', WRAPPER, 'cargo', '-Vv'])
run(['python3', WRAPPER, 'cargo', 'fmt', '--manifest-path', 'ui/Cargo.toml', '--all', '--', '--check'])
run(['git', 'diff', '--exit-code', 'HEAD', '--', 'ui/Cargo.lock'])
run(['git', 'diff', '--check', '--', 'ui', 'support/ui', 'tests/ui'])
for path in ['tests/ui/headless-weston.sh', 'tests/ui/compositor-restart.sh']:
    run(['bash', '-n', path])
source = ROOT / 'tests/ui/probe-cjk-pixels.py'
ast.parse(source.read_text(), filename=str(source))
assert (ROOT / 'README.md').stat().st_size == 0
before = tomllib.loads(subprocess.check_output(['git', 'show', '6aa6cd40642b573c02a7253ca03302e9a42f552d:ui/Cargo.lock'], cwd=ROOT, text=True))
after = tomllib.loads((ROOT / 'ui/Cargo.lock').read_text())
identity = lambda package: (package['name'], package['version'], package.get('source'), package.get('checksum'))
assert set(map(identity, before['package'])) == set(map(identity, after['package']))
print(json.dumps({'python_syntax': 'passed_without_bytecode', 'README_bytes': 0,
    'registry_package_identity_change_count': 0, 'direct_edges_added': ['trill-shell -> ab_glyph', 'trill-app-window -> ab_glyph']}))
