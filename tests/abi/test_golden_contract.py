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
    if kind not in ('request', 'response'):
        raise ValueError('unknown fixture kind')
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
    if kind == 'response' and opcode == 3:
        # Independent response-side oracle: even an error response must echo
        # the ordered InstallBudget sequence, never an opaque 128-bit ID.
        sequence = struct.unpack_from('<Q', raw, 24)[0]
        if raw[32:40] != bytes(8) or not 0 < sequence < 2**64 - 1:
            raise ValueError('ordered InstallBudget response ID')
        if flags == 0:
            previous, effective, consumed = struct.unpack_from('<3Q', raw, 64)
            if not 0 < previous < 2**64 - 1 or revision != previous + 1:
                raise ValueError('invalid previous revision')
            if consumed > effective % PERIOD:
                raise ValueError('impossible consumed_at_apply')
    if kind == 'response' and flags == 0:
        # These fixed-payload checks are an independent test oracle only;
        # production decoding and response correlation remain in Rust.
        if opcode == 1:
            space, page, max_request, max_response, spare, ops, features = struct.unpack_from('<16sIIIIQQ', raw, 64)
            if (not any(space) or not page or page & (page - 1) or spare or features
                    or max_request > 65536 or max_response > 65536
                    or ops & ~62 or not ops & 2):
                raise ValueError('ABI advertisement')
            if ops & 8 and ops & 52 != 52 or ops & 32 and not ops & 16:
                raise ValueError('ABI operation dependency')
            declared = [SIZES[op] for op in SIZES if ops & (1 << op)]
            if max_request < max(size[0] for size in declared) or max_response < max(size[1] for size in declared):
                raise ValueError('ABI advertised payload bounds')
        elif opcode == 2:
            sample, cumulative, start, used, cap, period, events, dropped = struct.unpack_from('<8Q', raw, 64)
            if (period != PERIOD or start != sample // PERIOD * PERIOD
                    or used > sample - start or cumulative < used
                    or cumulative - used > start
                    or cumulative > sample
                    or cap > period or dropped > events):
                raise ValueError('usage accounting')
        elif opcode == 4:
            state, saved, spare, sequence, object_id, saved_revision, previous, effective, consumed = struct.unpack_from('<HHIQ16sQQQQ', raw, 64)
            if state > 4 or saved > 11 or spare or not sequence:
                raise ValueError('delivery state/status/sequence/reserved')
            if state == 1 and saved in (10, 11):
                raise ValueError('pre-reservation status cannot be terminal')
            if sequence == 2**64 - 1 and state not in (3, 4):
                raise ValueError('exhausted sequence cannot have a reserved result')
            if state == 1 and saved == 0:
                if (not any(object_id) or not 0 < previous < 2**64 - 1
                        or saved_revision != previous + 1
                        or consumed > effective % PERIOD):
                    raise ValueError('terminal success metadata')
            elif (any(object_id) or saved_revision or previous or effective or consumed
                  or state != 1 and saved):
                raise ValueError('non-success delivery metadata')
        elif opcode == 5:
            retired, next_sequence = struct.unpack_from('<QQ', raw, 64)
            if next_sequence <= retired:
                raise ValueError('retirement frontier')
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
        self.assertTrue(doc['codec_tested'])
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
        self.assertLessEqual(cumulative, sample)
        self.assertEqual(period, PERIOD)
        self.assertLessEqual(dropped, events)
        self.assertGreater(used, cap)
        self.assertEqual(used, 35_000_000)

    def test_cumulative_cpu_cannot_exceed_boot_elapsed_time(self):
        original = bytes.fromhex(read_vector('read_usage_lowered_cap')['hex'])
        mutated = bytearray(original)
        # HOSR offset 72 is the cumulative_cpu_ns field. This is the exact
        # issue #104 counterexample: every other golden field remains valid.
        sample = struct.unpack_from('<Q', original, 64)[0]
        struct.pack_into('<Q', mutated, 72, sample + 1)
        self.assertEqual(mutated[72:80].hex(), '81d1f00800000000')
        with self.assertRaises(ValueError):
            read_frame(bytes(mutated), 'response')

    def test_prior_window_cpu_cannot_exceed_prior_elapsed_time(self):
        original = bytes.fromhex(read_vector('read_usage_lowered_cap')['hex'])
        for sample, start, used in ((150_000_000, PERIOD, 35_000_000),
                                    (50_000_000, 0, 35_000_000)):
            with self.subTest(sample=sample, start=start):
                boundary = bytearray(original)
                # All time before the current window may have been spent
                # running. One additional prior nanosecond is impossible
                # even though cumulative time still fits below sample time.
                struct.pack_into('<4Q', boundary, 64, sample, start + used, start, used)
                self.assertEqual(read_frame(bytes(boundary), 'response')[0], 2)
                impossible = bytearray(boundary)
                struct.pack_into('<Q', impossible, 72, start + used + 1)
                self.assertLess(struct.unpack_from('<Q', impossible, 72)[0], sample)
                with self.assertRaises(ValueError):
                    read_frame(bytes(impossible), 'response')

        # Keep the audit counterexample independent of generated edge vectors:
        # 140ms total - 35ms current = 105ms before a 100ms window start.
        impossible = bytearray(original)
        struct.pack_into('<4Q', impossible, 64, 150_000_000, 140_000_000,
                         PERIOD, 35_000_000)
        with self.assertRaises(ValueError):
            read_frame(bytes(impossible), 'response')

    def test_delivery_status_and_exhausted_sequence_boundaries(self):
        original = bytes.fromhex(read_vector('query_delivery_terminal')['hex'])

        def frame(state, saved, sequence):
            raw = bytearray(original)
            struct.pack_into('<HHIQ', raw, 64, state, saved, 0, sequence)
            if state != 1 or saved != 0:
                raw[80:] = bytes(48)
            return bytes(raw)

        # OutOfOrder and Retired arise before reservation; neither is a saved
        # terminal result. MAX is an exhaustion marker, never a reserved write.
        invalid = ((1, 10, 1), (1, 11, 1),
                   (0, 0, 2**64 - 1), (1, 2, 2**64 - 1), (2, 0, 2**64 - 1))
        for state, saved, sequence in invalid:
            with self.subTest(state=state, saved=saved, sequence=sequence):
                with self.assertRaises(ValueError):
                    read_frame(frame(state, saved, sequence), 'response')

        # The last usable sequence remains valid for all reserved-result
        # states, including terminal success and every saved error 1..9.
        valid = [(0, 0, 2**64 - 2), (2, 0, 2**64 - 2),
                 (3, 0, 2**64 - 1), (4, 0, 2**64 - 1)]
        valid.extend((1, saved, 2**64 - 2) for saved in range(10))
        for state, saved, sequence in valid:
            with self.subTest(state=state, saved=saved, sequence=sequence):
                self.assertEqual(read_frame(frame(state, saved, sequence), 'response')[0], 4)

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
        self.assertEqual(consumed, 33_000_000)

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

    def test_install_response_ordered_id_is_checked_for_success_and_error(self):
        for name in ('install_budget_ok', 'install_cas_rejection'):
            original = bytes.fromhex(read_vector(name)['hex'])
            with self.subTest(vector=name):
                self.assertEqual(read_frame(original, 'response')[0], 3)
                for offset, replacement in ((32, 1), (24, 0xff)):
                    invalid = bytearray(original)
                    if offset == 24:
                        invalid[24:32] = bytes([replacement]) * 8
                    else:
                        invalid[offset] = replacement
                    with self.assertRaises(ValueError):
                        read_frame(bytes(invalid), 'response')
                invalid = bytearray(original)
                invalid[24:32] = bytes(8)
                with self.assertRaises(ValueError):
                    read_frame(bytes(invalid), 'response')

    def test_install_response_requires_existing_revision_and_elapsed_time(self):
        frame = bytes.fromhex(read_vector('install_budget_ok')['hex'])
        zero_revision = bytearray(frame)
        struct.pack_into('<Q', zero_revision, 64, 0)
        struct.pack_into('<Q', zero_revision, 56, 1)
        with self.assertRaises(ValueError):
            read_frame(bytes(zero_revision), 'response')

        impossible_time = bytearray(frame)
        struct.pack_into('<Q', impossible_time, 80, 41_000_000)
        with self.assertRaises(ValueError):
            read_frame(bytes(impossible_time), 'response')

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
