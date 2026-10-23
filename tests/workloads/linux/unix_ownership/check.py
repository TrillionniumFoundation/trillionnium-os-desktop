# SPDX-License-Identifier: MPL-2.0
"""Strict original-kernel UNIX ownership probe evidence validation."""
import re

NAMES = (
    'notes_stream', 'notes_seqpacket', 'listener_pending_stream',
    'listener_pending_seqpacket', 'datagram_future_connect', 'self_stream',
    'self_seqpacket', 'self_datagram', 'seqpacket_empty_slots', 'concurrent_cross_edges',
    'ancillary_multisegment_253', 'ancillary_rejected_inputs_publish_nothing',
)


def check(raw, code, timed_out):
    clean = re.sub(r'\x1b\[[0-9;]*m', '', raw).replace('\r\n', '\n')
    cases = re.findall(r'^UNIX_OWNER_CASE (\S+) PASS$', clean, re.M)
    complete = re.findall(r'^UNIX_OWNER_COMPLETE cases=(\d+) failures=(\d+)$', clean, re.M)
    valid = (code == 33 and not timed_out and tuple(cases) == NAMES and
             complete == [('12', '0')] and
             clean.splitlines().count('UNIX_OWNER_PROBE_EXIT=0') == 1 and
             clean.splitlines().count('TRILLIONNIUM_A01_BOOT_OK') == 1 and
             'UNIX_OWNER_FAIL' not in clean)
    return dict(passed=valid, guest_complete=valid, cases=cases)
