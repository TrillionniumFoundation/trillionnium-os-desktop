#!/usr/bin/env python3
"""Prepare a read-only three-receipt collector using the actual install terminal."""
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path

BASE = Path('/workspace/scratch/94990735b266')
OLD = BASE / 'android-ihg-qa-r1-install-reader-01'
OUT = BASE / 'android-bestbuy-qa-r1-install-reader-01'
EVIDENCE = BASE / 'root-recovery-20261104-02/evidence/bestbuy-r1-install-state01'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def put(name, raw):
    if not isinstance(raw, bytes):
        raw = raw.encode() if isinstance(raw, str) else encode(raw)
    with (OUT / name).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return pin(raw)


def main():
    assert not OUT.exists()
    old = (OLD / 'read_install.py').read_bytes()
    assert pin(old) == {'bytes': 9698, 'sha256': '0048b43a04dd9da6def48e82bee667d7ce09365f05f258e31686c71af8213600'}
    actual = (EVIDENCE / 'stdout.log').read_bytes()
    assert pin(actual) == {'bytes': 684, 'sha256': '1d56c522c38b3ba06da0550056ca5b28e0f2ab0ba970e47abd856314ef72b5ab'}
    lines = [json.loads(line) for line in actual.splitlines()]
    assert len(lines) == 2 and all(x['ok'] and x['error'] is None and x['secondary_errors'] == [] for x in lines)
    c, s = lines[0]['result'], lines[1]['stage_result']
    root = '/home/alex/work/pocket4-owned-bestbuy-qa-r1-install-state-01'
    assert c['path'] == root + '/result.json' and s['path'] == root + '/stage-result.json'
    inputs = json.loads((BASE / 'android-bestbuy-qa-r1-install-state-01/INPUTS.json').read_text())
    replacements = [
        ('com.ihg.apps.android', 'com.bestbuy.android'), ('ihg', 'bestbuy'), ('IHG', 'BESTBUY'),
        ('c815375703e1143b2a8ce8d7d3c44d6e', inputs['nonces']['state_nonce']),
        ('b637e01d62293f5e7c909e75d2b36d50', inputs['nonces']['install_nonce']),
        ('eec0bb01cbc2440918800026c2d1260bdc62fbab1f377776b9fccf7467596902',
         '15d6495c30af3b765c9b4df99d8d170001e66ea54ab23327bfc7d785e192d2a4'),
        ("PINS = {'coordinator.json': (3068, '7487081977233962e2b3c029474313e6f2c306e908ee7d3178e07bd3830bddf0'), 'stage.json': (1614, '396fc6e9642767017331abee562c222a1fd15af2cc68421aabbf3b0d02a9fed1')}",
         'PINS = ' + repr({'coordinator.json': (c['bytes'], c['sha256']), 'stage.json': (s['bytes'], s['sha256'])})),
        ('uid not in (10137,10121,10129,10117,10125,10164,10165,10166,10169,10170,10175,10184,10190)',
         'uid not in (10130,10121,10129,10117,10125,10164,10165,10166,10169,10170,10175,10184,10190,10137,10196)'),
    ]
    text = old.decode()
    for before, after in replacements:
        assert before in text, before
        text = text.replace(before, after)
    ast.parse(text)
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    source_pin = put('read_install.py', text)
    put('IHG-to-BestBuy-reader.patch', ''.join(difflib.unified_diff(old.decode().splitlines(True),
        text.splitlines(True), fromfile='qualified-IHG/read_install.py', tofile='BestBuy/read_install.py')))
    request = json.loads((OLD / 'exact-request.json').read_text())
    request['stdin'] = text
    request['args'][-1] = request['args'][-1].replace(pin(old)['sha256'], source_pin['sha256'])
    request['idempotency_key'] = 'pocket4-owned-bestbuy-qa-r1-install-state-three-receipts-read01-20261105'
    request_pin = put('exact-request.json', request)
    review = {'schema': 1, 'state': 'FIXED_READONLY_THREE_RECEIPTS_NOT_SUBMITTED',
        'baseline_reader': pin(old), 'actual_terminal_stdout': pin(actual),
        'actual_parents': {'coordinator': c, 'stage': s}, 'request': request_pin,
        'source': source_pin, 'literal_replacements': replacements,
        'only_nonbinding_change': 'Known helper/target UID exclusions extended; no scope or bounds relaxed.',
        'worker_pin_derived_only_from_exact_parent': True, 'helper_UID_not_guessed': True,
        'read_only': True, 'Android_or_Hepta_actions': 0, 'whole_app_production_ready': False}
    put('source-review.json', review)
    payloads = {p.name: pin(p.read_bytes()) for p in sorted(OUT.iterdir()) if p.is_file()}
    frozen = put('FROZEN_FILES.json', {'schema': 1, 'files': payloads, 'payload_count': len(payloads)})
    print(json.dumps({'request': request_pin, 'source': source_pin, 'frozen': frozen,
        'key': request['idempotency_key'], 'remote_actions': 0}))


if __name__ == '__main__':
    main()
