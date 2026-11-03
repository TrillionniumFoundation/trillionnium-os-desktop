# SPDX-License-Identifier: MPL-2.0
"""Exact six-case DAC oracle; host transcript shapes are not guest qualification."""
import re

EXPECTED = [
    'SUPPLEMENTARY_DAC_CHILD uid=60001 gid=60001 group_count=1 group=60002 caps=0 nnp=1',
    'SUPPLEMENTARY_DAC_CHECK name=supplementary_file_read actual=1 expected=1 errno=0',
    'SUPPLEMENTARY_DAC_CHECK name=supplementary_directory_search actual=1 expected=1 errno=0',
    'SUPPLEMENTARY_DAC_CHECK name=member_write_refused actual=1 expected=1 errno=13',
    'SUPPLEMENTARY_DAC_REAP member=1 exited=1 code=0',
    'SUPPLEMENTARY_DAC_CHILD uid=60001 gid=60001 group_count=0 group=0 caps=0 nnp=1',
    'SUPPLEMENTARY_DAC_CHECK name=nonmember_file_refused actual=0 expected=0 errno=13',
    'SUPPLEMENTARY_DAC_CHECK name=nonmember_directory_refused actual=0 expected=0 errno=13',
    'SUPPLEMENTARY_DAC_CHECK name=nonmember_write_refused actual=1 expected=1 errno=13',
    'SUPPLEMENTARY_DAC_REAP member=0 exited=1 code=0',
    'SUPPLEMENTARY_DAC_COMPLETE pass=1 reaped=2 production_ready=0',
    'SUPPLEMENTARY_DAC_PROBE_EXIT=0',
]


def check(raw, code, timed_out):
    passed = False
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', errors='replace')
    if type(raw) is str and len(raw.encode()) <= 2 * 1024 * 1024:
        lines = re.sub(r'\x1b\[[0-9;]*m', '', raw).replace('\r', '').splitlines()
        selected = [line for line in lines if line.startswith('SUPPLEMENTARY_DAC_')]
        boot = [i for i, line in enumerate(lines) if 'TRILLIONNIUM_A01_BOOT_OK' in line]
        passed = (type(code) is int and code == 33 and timed_out is False and selected == EXPECTED
                  and len(boot) == 1 and lines[boot[0]] == 'TRILLIONNIUM_A01_BOOT_OK'
                  and lines.index(EXPECTED[-1]) < boot[0]
                  and not any(token in raw.lower() for token in ['panicked at', 'kernel panic']))
    return {'passed': passed, 'cases': EXPECTED[1:4] + EXPECTED[6:9] if passed else [],
            'all_children_reaped': passed, 'raw_qemu_exit': code, 'timed_out': timed_out,
            'production_qualification': False}
