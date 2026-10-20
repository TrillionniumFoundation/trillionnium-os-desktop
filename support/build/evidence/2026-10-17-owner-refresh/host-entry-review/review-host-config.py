#!/usr/bin/env python3
"""Read only tracked project docs/config for documented dedicated execution hosts.
No credentials, key stores, account discovery, VM execution, or runtime probes.
"""
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = Path('/workspace/scratch/ae1a8cf05419/trillionnium-os-desktop')
OUT = Path(__file__).resolve().parent
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=REPO).decode().split('\0'))
# Inventory uses rg; only explicitly allowed documentation/configuration roots
# are read. Generated run output and historical binary evidence are excluded.
inventory = subprocess.run(['rg', '--files', '--hidden', '-g', '!.git', '-g', '!kernel/asterinas/**',
    '-g', '!support/build/evidence/**', '-g', '!support/build/out/**',
    '-g', '!**/target/**', '-g', '!**/__pycache__/**'], cwd=REPO, text=True,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
roots = ('docs/', '.github/', '.devcontainer/', 'support/build/',
         'infra/', 'infrastructure/', 'deploy/', 'deployment/', 'config/')
suffixes = {'.md', '.txt', '.yaml', '.yml', '.toml', '.json', '.ini', '.cfg', '.conf'}
selected = []
for name in sorted(inventory.stdout.splitlines()):
    p = Path(name)
    if name not in tracked:
        continue
    if name.startswith(('support/build/evidence/', 'support/build/out/')):
        continue
    if p.suffix.lower() not in suffixes:
        continue
    if name.startswith(roots) or len(p.parts) == 1 or name == 'support/upstream-lock.json':
        # No account/auth/key material is included by filename or directory.
        if any(part.lower() in {'credentials', 'secrets', 'keys'} for part in p.parts):
            continue
        selected.append(name)
pattern = re.compile(r'\bKVM\b|/dev/kvm|self[- ]hosted|\bruns-on\b|\bVMX\b|\bEPT\b|'
    r'\bSSH\b|second.{0,18}host|dedicated.{0,24}host|dedicated.{0,24}cloud|'
    r'cloud.{0,24}environment|云环境|专属|第二.{0,8}主机|第二.{0,8}host|远程.{0,8}主机|'
    r'\bhostname\b|\bhost_id\b|runner.{0,18}labels?', re.IGNORECASE)
# SSH is used only as a documented transport word inside the allowlisted
# project docs/config corpus; no key files, client config or accounts are read.
files, hits = [], []
for name in selected:
    raw = (REPO / name).read_bytes()
    item = {'path': name, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    files.append(item)
    lines = raw.decode('utf-8', errors='replace').splitlines()
    for index, line in enumerate(lines):
        if pattern.search(line):
            hit = {'path': name, 'line': index + 1, 'text': line,
                'context': [{'line': j + 1, 'text': lines[j]}
                    for j in range(max(0, index - 1), min(len(lines), index + 2))]}
            hits.append(hit)
metadata = {'schema': 1, 'started_utc': started,
    'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'repo_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
    'scope': 'Tracked docs and allowlisted project configuration only; no historical evidence contents, credentials, keys, cloud accounts, VM or runtime capability probes.',
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'selected_file_count': len(files), 'matched_line_count': len(hits),
    'files': files, 'matches': hits}
(OUT / 'scan.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({key: metadata[key] for key in ('started_utc', 'completed_utc', 'repo_head',
    'script_sha256', 'selected_file_count', 'matched_line_count')}, ensure_ascii=False))
for hit in hits:
    print(f"{hit['path']}:{hit['line']}: {hit['text']}")
