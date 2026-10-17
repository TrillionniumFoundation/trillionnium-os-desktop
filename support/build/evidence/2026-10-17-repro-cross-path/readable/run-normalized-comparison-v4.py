#!/usr/bin/python3
"""Retain actual comparator argv, complete output, exit and source hash."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path('/workspace/scratch/ae1a8cf05419')
output = root / 'normalized-cloud/controller-comparison-v4'
output.mkdir(mode=0o700, exist_ok=False)
script = root / 'compare-normalized-cloud-v4.py'
before = script.read_bytes()
record = {'argv': ['python3', '-I', str(script),
    '4e8c7083575cec69efabe8d2250dfdd040c8dee8'],
    'cwd': str(root), 'start': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'script_sha256': hashlib.sha256(before).hexdigest()}
(output / script.name).write_bytes(before)
(output / 'command.json').write_text(json.dumps(record, indent=2) + '\n')
with (output / 'output.log').open('xb') as log:
    record['actual_returncode'] = subprocess.run(record['argv'], cwd=root,
        stdout=log, stderr=subprocess.STDOUT).returncode
record.update(end=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    output_sha256=hashlib.sha256((output / 'output.log').read_bytes()).hexdigest(),
    output_size=(output / 'output.log').stat().st_size,
    script_unchanged=script.read_bytes() == before)
(output / 'command.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
raise SystemExit(record['actual_returncode'] if record['script_unchanged'] else 125)
