# SPDX-License-Identifier: MPL-2.0
"""Exact Linux-referenced credentials/lifetime transcript oracle, not authority."""
from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
REFERENCES = {
    'lifetime': ('linux-reference-02.jsonl', 'c64055d516c6e7b5b5f9ed0b694aa742def4bfb9282588e117bb1acaea85bb2e', 59, 'SOCKET_CREDENTIAL_PROBE_EXIT'),
    'groups': ('group-linux-reference-01.jsonl', '720e4bd6cb75ead1050d000c005bef9a9cd4ed47e7ff17fe0a58d69818344e98', 16, 'SOCKET_GROUP_PROBE_EXIT'),
}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate key')
        result[key] = value
    return result


def check(raw, code, timed_out, suite):
    passed = False
    count = 0
    try:
        name, digest, count, marker = REFERENCES[suite]
        reference = (HERE/name).read_bytes()
        if hashlib.sha256(reference).hexdigest() != digest: raise ValueError('changed Linux reference')
        expected = [json.loads(line, object_pairs_hook=_object) for line in reference.splitlines()]
        if len(expected) != count or expected[-1]['failures'] != 0: raise ValueError('bad reference')
        if isinstance(raw, bytes): raw = raw.decode('utf-8', errors='strict')
        if type(raw) is not str or len(raw.encode()) > 2*1024*1024: raise ValueError('size/type')
        if type(code) is not int or code != 33 or timed_out is not False: raise ValueError('completion')
        lines = re.sub(r'\x1b\[[0-9;]*m', '', raw).replace('\r','').splitlines()
        selected = [line for line in lines if line.startswith(('{','SOCKET_'))]
        if selected[-1] != marker+'=0': raise ValueError('exit')
        actual = [json.loads(line, object_pairs_hook=_object) for line in selected[:-1]]
        # Canonical JSON preserves bool/int/float distinctions and closed field sets.
        if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True): raise ValueError('observation mismatch')
        boot = [i for i,line in enumerate(lines) if 'TRILLIONNIUM_A01_BOOT_OK' in line]
        if len(boot) != 1 or lines[boot[0]] != 'TRILLIONNIUM_A01_BOOT_OK' or lines.index(selected[-1]) >= boot[0]: raise ValueError('boot/order')
        if any(token in raw.lower() for token in ('panicked at','kernel panic')): raise ValueError('panic')
        passed = True
    except (ValueError, TypeError, IndexError, KeyError, UnicodeError, OSError):
        pass
    return {'passed':passed, 'observations':count if passed else 0,
            'all_children_reaped':passed,'raw_qemu_exit':code,'timed_out':timed_out,
            'production_qualification':False}
