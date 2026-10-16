#!/usr/bin/env python3
"""Independent semantic boundary fixtures for the experimental HOS2 2.0 ABI.

Use the existing golden generator's frame packers, never the Rust codec.
These fixtures describe wire acceptance, not kernel execution or authorization.
"""

import argparse
import json
from pathlib import Path
import struct

from generate_hos2 import BOOT, OBJECT, PERIOD, SPACE, request, response, vector


HERE = Path(__file__).with_name('hos2_edges.json')
U64_MAX = (1 << 64) - 1
OPAQUE_ID = bytes.fromhex('0123456789abcdeffedcba9876543210')
LAST_SEQUENCE = struct.pack('<Q', U64_MAX - 1) + bytes(8)
EFFECTIVE_NS = 150_000_000
CONSUMED_NS = 35_000_000


def history(sequence):
    return BOOT + SPACE + struct.pack('<Q', sequence)


def delivery(state, saved_status=0, sequence=1):
    return struct.pack('<HHIQ16sQQQQ', state, saved_status, 0, sequence,
                       bytes(16), 0, 0, 0, 0)


def build_document():
    result = []
    for state, name in ((0, 'reserved'), (2, 'retired'), (3, 'not_seen'),
                        (4, 'history_lost')):
        result.append(vector(
            f'delivery_{name}', 'response', 4,
            response(4, delivery(state), request_id=OPAQUE_ID),
            dict(state=state, saved_status=0, sequence=1,
                 zero_metadata=True), 0))
    for status in range(1, 12):
        result.append(vector(
            f'delivery_terminal_error_{status}', 'response', 4,
            response(4, delivery(1, status), request_id=OPAQUE_ID),
            dict(state=1, saved_status=status, sequence=1,
                 zero_metadata=True), 0))

    budget = struct.pack('<4Q', U64_MAX - 1, PERIOD, 20_000_000, 0)
    applied = struct.pack('<3Q', U64_MAX - 1, EFFECTIVE_NS, CONSUMED_NS)
    terminal = struct.pack('<HHIQ16sQQQQ', 1, 0, 0, U64_MAX - 1, OBJECT,
                           U64_MAX, U64_MAX - 1, EFFECTIVE_NS, CONSUMED_NS)
    assert CONSUMED_NS <= EFFECTIVE_NS % PERIOD
    assert CONSUMED_NS > 20_000_000
    result.extend([
        vector('install_last_sequence', 'request', 3,
               request(3, budget, request_id=LAST_SEQUENCE, slot=7, generation=9),
               dict(sequence=U64_MAX - 1, expected_revision=U64_MAX - 1,
                    cap_ns=20_000_000)),
        vector('install_revision_max', 'response', 3,
               response(3, applied, request_id=LAST_SEQUENCE, revision=U64_MAX),
               dict(previous_revision=U64_MAX - 1, revision=U64_MAX,
                    effective_ns=EFFECTIVE_NS, consumed_ns=CONSUMED_NS), 0),
        vector('query_last_write_sequence', 'request', 4,
               request(4, history(U64_MAX - 1), request_id=OPAQUE_ID,
                       slot=80, generation=3),
               dict(sequence=U64_MAX - 1, opaque_request_id=True)),
        vector('delivery_revision_max', 'response', 4,
               response(4, terminal, request_id=OPAQUE_ID),
               dict(sequence=U64_MAX - 1, saved_revision=U64_MAX,
                    previous_revision=U64_MAX - 1, effective_ns=EFFECTIVE_NS,
                    consumed_ns=CONSUMED_NS), 0),
        vector('query_history_sequence_max', 'request', 4,
               request(4, history(U64_MAX), request_id=OPAQUE_ID,
                       slot=80, generation=3),
               dict(sequence=U64_MAX, opaque_request_id=True)),
        vector('retire_last_write_sequence', 'request', 5,
               request(5, history(U64_MAX - 1), request_id=OPAQUE_ID,
                       slot=80, generation=3),
               dict(sequence=U64_MAX - 1, opaque_request_id=True)),
        vector('retire_next_sequence_max', 'response', 5,
               response(5, struct.pack('<QQ', U64_MAX - 1, U64_MAX),
                        request_id=OPAQUE_ID),
               dict(retired_through=U64_MAX - 1, next_sequence=U64_MAX), 0),
        vector('read_opaque_id', 'request', 2,
               request(2, request_id=OPAQUE_ID, slot=7, generation=9),
               dict(opaque_request_id=True)),
        vector('read_opaque_id_ok', 'response', 2,
               response(2, struct.pack('<8Q', EFFECTIVE_NS, 90_000_000,
                                      100_000_000, CONSUMED_NS, 20_000_000,
                                      PERIOD, 77, 2),
                        request_id=OPAQUE_ID, revision=U64_MAX),
               dict(revision=U64_MAX, window_consumed_ns=CONSUMED_NS,
                    active_cap_ns=20_000_000, consumed_over_cap_is_valid=True), 0),
    ])
    return dict(protocol='HOS2 2.0 experimental',
                generator='tests/golden/generate_hos2_edges.py '
                          '(uses independent generate_hos2.py packers)',
                vectors=result)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--write', action='store_true')
    args = parser.parse_args()
    data = build_document()
    if args.write:
        HERE.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    elif json.loads(HERE.read_text(encoding='utf-8')) != data:
        parser.error('committed semantic edge fixtures differ from independent generator')
    else:
        print(f'{len(data["vectors"])} golden HOS2 semantic edge vectors verified')


if __name__ == '__main__':
    main()
