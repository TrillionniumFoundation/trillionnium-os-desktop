#!/usr/bin/env python3
"""Offline verification of fixed Root-collected source observations only."""
import hashlib
import json
from pathlib import Path

ROOT = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/art-role-ingress-exit-read01')
raw = (ROOT / 'reader-report.json').read_bytes()
assert len(raw) == 130603
assert hashlib.sha256(raw).hexdigest() == '07547751719bfb04d4707bef758868bb16e76811c95e3716dbf8a3f8682ba0e1'
report = json.loads(raw)
assert report['all_five_complete'] is True and len(report['files']) == 5
assert report['Main_actions'] == 0 and report['source_execution'] is False
assert report['compiled451_source_bound'] is False and report['installed_ART_binary_bound'] is False
for row in report['files']:
    source = (ROOT / 'originals' / row['relative']).read_bytes()
    assert row['complete'] is True and source == row['text'].encode()
    assert len(source) == row['bytes'] <= row['maximum_bytes']
    assert hashlib.sha256(source).hexdigest() == row['sha256']
    assert row['held_before'] == row['held_after'] == row['named_before'] == row['named_after']
print(json.dumps({'all_five_complete': True, 'bytes_and_held_named_identities_reconciled': True,
                  'source_execution': False, 'installed_ART_binary_bound': False,
                  'compiled451_source_bound': False}))
