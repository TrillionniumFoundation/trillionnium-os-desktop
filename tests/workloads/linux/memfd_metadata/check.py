# SPDX-License-Identifier: MPL-2.0
"""Strict, complete original-kernel memfd metadata evidence."""
import re

NAMES = ('detached_metadata', 'readonly_four_seals', 'duplicate_lifetime',
         'sealed_mutations_rejected')


def check(raw, code, timed_out):
    clean = re.sub(r'\x1b\[[0-9;]*m', '', raw).replace('\r\n', '\n')
    lines = clean.splitlines()
    cases = re.findall(r'^MEMFD_METADATA_PASS (\S+)$', clean, re.M)
    required = ['MEMFD_METADATA_BEGIN', *(f'MEMFD_METADATA_PASS {name}' for name in NAMES),
                'MEMFD_METADATA_COMPLETE cases=4', 'MEMFD_METADATA_PROBE_EXIT=0',
                'TRILLIONNIUM_A01_BOOT_OK']
    valid = (code == 33 and not timed_out and tuple(cases) == NAMES and
             all(lines.count(marker) == 1 for marker in required) and
             all(lines.index(a) < lines.index(b) for a, b in zip(required, required[1:])) and
             'MEMFD_METADATA_FAIL' not in clean and
             not re.search(r'(?i)(panicked at|kernel panic|MEMFD_METADATA_PROBE_EXIT=[1-9])', clean))
    return dict(passed=valid, guest_complete=valid, cases=cases)
