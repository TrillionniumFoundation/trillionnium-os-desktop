# SPDX-License-Identifier: MPL-2.0
"""Strict, complete original-kernel signal probe evidence."""
import re

NAMES = ('fault_siginfo', 'kill_reap', 'tgkill_reap', 'group_kill_reap',
         'pidfd_dynamic_reap', 'original_permissions', 'dynamic_realtime_fifo',
         'dynamic_signalfd', 'ptrace_fault_owner')


def check(raw, code, timed_out):
    clean = re.sub(r'\x1b\[[0-9;]*m', '', raw).replace('\r\n', '\n')
    lines = clean.splitlines()
    cases = re.findall(r'^INLINE_SIGNAL_PASS (\S+)$', clean, re.M)
    required = ['INLINE_SIGNAL_BEGIN', *(f'INLINE_SIGNAL_PASS {name}' for name in NAMES),
                'INLINE_SIGNAL_COMPLETE cases=9', 'INLINE_SIGNAL_PROBE_EXIT=0',
                'TRILLIONNIUM_A01_BOOT_OK']
    valid = (code == 33 and not timed_out and tuple(cases) == NAMES and
             all(lines.count(marker) == 1 for marker in required) and
             all(lines.index(a) < lines.index(b) for a, b in zip(required, required[1:])) and
             'INLINE_SIGNAL_FAIL' not in clean and
             not re.search(r'(?i)(panicked at|kernel panic|INLINE_SIGNAL_PROBE_EXIT=[1-9])', clean))
    return dict(passed=valid, guest_complete=valid, cases=cases)
