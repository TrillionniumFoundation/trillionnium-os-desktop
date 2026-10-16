#!/usr/bin/env python3
"""Independent HOS2 2.0 golden bytes, using Python stdlib struct (not Rust codec).

--check compares the committed fixture without changing it; --write regenerates.
These are N0 single-CPU temporal examples, not kernel behavior.
"""
import argparse
import json
from pathlib import Path
import struct

PERIOD = 100_000_000
I11, SPACE, BOOT, OBJECT = (bytes([c]) * 16 for c in (0x11, 0x22, 0x33, 0x44))
SEQ1 = struct.pack('<Q', 1) + bytes(8)
HERE = Path(__file__).with_name('hos2.json')


def request(op, payload=b'', *, request_id=I11, slot=0, generation=0):
    return struct.pack('<4sHHHHIII16sQQQ', b'HOS2', 2, 0, op, 0,
                       64, len(payload), 0, request_id, slot, generation, 0) + payload


def response(op, payload=b'', *, request_id=I11, status=0, revision=0):
    return struct.pack('<4sHHHHIII16s16sQ', b'HOSR', 2, 0, op, status,
                       64, len(payload), 0, request_id, BOOT, revision) + payload


def vector(name, kind, op, data, expected=None, status=None):
    result = dict(name=name, kind=kind, hex=data.hex(), bytes=len(data), opcode=op)
    if status is not None:
        result['status'] = status
    result['expected'] = expected if expected is not None else {}
    return result


def build_document():
    # Keep the original lowered-cap consumption (35ms > 20ms) while moving
    # the observation/effect times far enough into the current 100ms window.
    # This preserves real post-demotion over-cap evidence without claiming
    # more CPU time than the elapsed wall-clock window permits.
    sample, read_consumed, effective, apply_consumed = (150_000_000, 35_000_000,
                                                        140_000_000, 33_000_000)
    assert read_consumed <= sample % PERIOD
    assert apply_consumed <= effective % PERIOD
    assert 20_000_000 < read_consumed
    history = BOOT + SPACE + struct.pack('<Q', 1)
    usage = struct.pack('<8Q', sample, 90_000_000, 100_000_000, read_consumed,
                        20_000_000, PERIOD, 77, 2)
    budget = struct.pack('<4Q', 10, PERIOD, 40_000_000, 0)
    applied = struct.pack('<3Q', 10, effective, apply_consumed)
    terminal = struct.pack('<HHIQ16sQQQQ', 1, 0, 0, 1, OBJECT, 11, 10,
                           effective, apply_consumed)
    retired = struct.pack('<HHIQ16sQQQQ', 2, 0, 0, 1, bytes(16), 0, 0, 0, 0)
    result = [
        vector('query_abi', 'request', 1, request(1)),
        vector('query_abi_ok', 'response', 1, response(1,
            struct.pack('<16sIIIIQQ', SPACE, 4096, 65536, 65536, 0, 62, 0)),
            dict(page_size=4096, supported_ops=62), 0),
        vector('read_usage', 'request', 2, request(2, slot=7, generation=9)),
        vector('read_usage_lowered_cap', 'response', 2, response(2, usage, revision=11),
            dict(window_consumed_ns=read_consumed, active_cap_ns=20_000_000,
                 consumed_over_cap_is_valid=True), 0),
        vector('install_budget', 'request', 3, request(3, budget, request_id=SEQ1,
            slot=7, generation=9), dict(sequence=1, expected_revision=10,
                                         cap_ns=40_000_000)),
        vector('install_budget_ok', 'response', 3, response(3, applied,
            request_id=SEQ1, revision=11), status=0),
        vector('query_delivery_with_new_view', 'request', 4,
            request(4, history, slot=80, generation=3)),
        vector('query_delivery_terminal', 'response', 4,
            response(4, terminal), status=0),
        vector('query_delivery_retired', 'response', 4,
            response(4, retired), status=0),
        vector('retire_through', 'request', 5,
            request(5, history, slot=80, generation=3)),
        vector('retire_through_ok', 'response', 5,
            response(5, struct.pack('<QQ', 1, 2)), status=0),
        vector('install_cas_rejection', 'response', 3,
            response(3, request_id=SEQ1, status=5), status=5),
    ]
    return dict(protocol='HOS2 2.0 proposed',
                generator='tests/golden/generate_hos2.py (independent Python struct)',
                vectors=result, codec_tested=True)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--write', action='store_true')
    args = parser.parse_args()
    data = build_document()
    if args.write:
        HERE.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    else:
        actual = json.loads(HERE.read_text(encoding='utf-8'))
        if actual != data:
            parser.error('committed HOS2 golden vectors differ from independent generator')
        print(f'{len(data["vectors"])} golden HOS2 vectors verified')


if __name__ == '__main__':
    main()
