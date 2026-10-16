"""HOS2 fixed-vector structural and adversarial tests (stdlib; not a Rust codec)."""
import json
from pathlib import Path
import struct
import unittest

GOLDEN = Path(__file__).resolve().parents[1] / 'golden' / 'hos2.json'
PERIOD = 100_000_000
SIZES = {1: (0, 48), 2: (0, 64), 3: (32, 24), 4: (40, 64), 5: (40, 16)}


def read_vector(name):
    return next(v for v in json.loads(GOLDEN.read_text())['vectors'] if v['name'] == name)


def read_frame(raw, kind):
    if len(raw) < 64:
        raise ValueError('truncated header')
    if raw[:4] != (b'HOS2' if kind == 'request' else b'HOSR'):
        raise ValueError('magic')
    major, minor, opcode, flags, hdr, count, reserved = struct.unpack_from('<HHHHIII', raw, 4)
    if (major, minor) != (2, 0):
        raise ValueError('version')
    if opcode not in SIZES:
        raise ValueError('opcode')
    if hdr != 64 or reserved or count > 65536 or count != len(raw) - 64:
        raise ValueError('length or reserved')
    if kind == 'request':
        if flags:
            raise ValueError('request flags')
        slot, generation, tail = struct.unpack_from('<QQQ', raw, 40)
        if tail or (opcode == 1 and (slot or generation)) or (opcode != 1 and (not slot or not generation)):
            raise ValueError('target/reserved')
        if opcode == 3 and (raw[32:40] != bytes(8) or not 0 < struct.unpack_from('<Q', raw, 24)[0] < 2**64 - 1):
            raise ValueError('ordered sequence')
        if count != SIZES[opcode][0]:
            raise ValueError('request payload size')
        if opcode == 3:
            expected, period, cap, trailing = struct.unpack_from('<4Q', raw, 64)
            if not 0 < expected < 2**64 - 1 or period != PERIOD or cap > period or trailing:
                raise ValueError('budget')
        if opcode in (4, 5):
            if not any(raw[64:80]) or not any(raw[80:96]) or not struct.unpack_from('<Q', raw, 96)[0]:
                raise ValueError('history')
    else:
        if flags > 11 or not any(raw[40:56]):
            raise ValueError('status or boot')
        revision = struct.unpack_from('<Q', raw, 56)[0]
        if flags != 0:
            if count or revision:
                raise ValueError('error payload or revision')
        elif count != SIZES[opcode][1] or ((opcode in (2, 3)) != (revision != 0)):
            raise ValueError('success response')
    if not any(raw[24:40]):
        raise ValueError('request id')
    return opcode, raw[24:40], raw[40:56], raw[64:]


def same_canonical_install_request(a, b):
    """Format-layer equality, not the A03 kernel reservation implementation."""
    if read_frame(a, 'request')[0] != 3 or read_frame(b, 'request')[0] != 3:
        raise ValueError('not InstallBudget')
    return a == b


class GoldenContract(unittest.TestCase):
    def test_all_fixtures_frame_layout(self):
        doc = json.loads(GOLDEN.read_text())
        self.assertEqual(len(doc['vectors']), 12)
        for v in doc['vectors']:
            with self.subTest(v=v['name']):
                raw = bytes.fromhex(v['hex'])
                self.assertEqual(len(raw), v['bytes'])
                self.assertEqual(read_frame(raw, v['kind'])[0], v['opcode'])
                if v['kind'] == 'response':
                    self.assertEqual(struct.unpack_from('<H', raw, 10)[0], v['status'])

    def test_sample_single_cpu_elapsed_time(self):
        raw = bytes.fromhex(read_vector('read_usage_lowered_cap')['hex'])
        sample, cumulative, start, used, cap, period, events, dropped = struct.unpack_from('<8Q', raw, 64)
        self.assertEqual(start, (sample // PERIOD) * PERIOD)
        self.assertLessEqual(used, sample - start)
        self.assertLessEqual(used, cumulative)
        self.assertEqual(period, PERIOD)
        self.assertLessEqual(dropped, events)
        self.assertGreater(used, cap)
        self.assertEqual(used, 25_000_000)

    def test_install_and_history_share_valid_effect_time(self):
        applied = bytes.fromhex(read_vector('install_budget_ok')['hex'])
        history = bytes.fromhex(read_vector('query_delivery_terminal')['hex'])
        previous, effective, consumed = struct.unpack_from('<3Q', applied, 64)
        state, status, reserved, sequence = struct.unpack_from('<HHIQ', history, 64)
        object_id = history[80:96]
        saved_revision, prior, history_time, history_used = struct.unpack_from('<4Q', history, 96)
        self.assertEqual((state, status, reserved, sequence), (1, 0, 0, 1))
        self.assertNotEqual(object_id, bytes(16))
        self.assertEqual(saved_revision, previous + 1)
        self.assertEqual(prior, previous)
        self.assertEqual((history_time, history_used), (effective, consumed))
        self.assertEqual(struct.unpack_from('<Q', applied, 56)[0], saved_revision)
        self.assertLessEqual(consumed, effective % PERIOD)
        self.assertEqual(consumed, 23_000_000)

    def test_cap_and_revision_mutations_are_not_idempotent_retransmissions(self):
        original = bytes.fromhex(read_vector('install_budget')['hex'])
        self.assertTrue(same_canonical_install_request(original, original))
        for offset, value in ((64, 9), (80, 39_000_000)):
            with self.subTest(field=('revision' if offset == 64 else 'cap')):
                mutated = bytearray(original)
                struct.pack_into('<Q', mutated, offset, value)
                self.assertEqual(mutated[24:56], original[24:56])
                self.assertFalse(same_canonical_install_request(original, bytes(mutated)))

    def test_malformed_requests_rejected_before_effect(self):
        original = bytes.fromhex(read_vector('install_budget')['hex'])
        variants = []
        for offset, replacement in ((0, ord('X')), (6, 1), (10, 1), (12, 63),
                                    (20, 1), (32, 1), (56, 1)):
            b = bytearray(original); b[offset] = replacement
            variants.append(bytes(b))
        variants += [original[:-1], original + b'\0', original[:8] + b'\xff\xff' + original[10:]]
        for raw in variants:
            with self.subTest(raw=raw[:12].hex(), length=len(raw)):
                with self.assertRaises(ValueError):
                    read_frame(raw, 'request')

    def test_unknown_status_and_nonempty_error_rejected(self):
        failure = bytes.fromhex(read_vector('install_cas_rejection')['hex'])
        self.assertEqual(read_frame(failure, 'response')[0], 3)
        b = bytearray(failure); b[10] = 12
        with self.assertRaises(ValueError): read_frame(bytes(b), 'response')
        b = bytearray(failure); struct.pack_into('<Q', b, 56, 1)
        with self.assertRaises(ValueError): read_frame(bytes(b), 'response')
        b = bytearray(failure); b[16] = 1; b.append(1)
        with self.assertRaises(ValueError): read_frame(bytes(b), 'response')


if __name__ == '__main__':
    unittest.main()
