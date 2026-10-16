"""Dense, dependency-free negative checks over independently generated HOS2 vectors.

The source bytes come from tests/golden/hos2.json, not from a Rust encoder.
The parser is the existing independent Python wire oracle in this directory.
Rust-side exhaustive checks live in libs/os-abi/tests/golden_vectors.rs.
"""

import json
import struct
import unittest

from test_golden_contract import GOLDEN, read_frame


class DenseGoldenBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = json.loads(GOLDEN.read_text(encoding="utf-8"))["vectors"]
        if len(cls.vectors) != 12:
            raise AssertionError("unexpected independent golden vector count")

    def test_all_golden_prefixes_are_truncated_not_valid_frames(self):
        cuts = 0
        for vector in self.vectors:
            frame = bytes.fromhex(vector["hex"])
            with self.subTest(vector=vector["name"]):
                self.assertEqual(len(frame), vector["bytes"])
                self.assertEqual(read_frame(frame, vector["kind"])[0], vector["opcode"])
                for limit in range(len(frame)):
                    with self.assertRaises(ValueError):
                        read_frame(frame[:limit], vector["kind"])
                    cuts += 1
        self.assertEqual(cuts, 1160)

    def test_golden_frames_reject_trailing_bytes(self):
        for vector in self.vectors:
            frame = bytes.fromhex(vector["hex"])
            for extra in (b"\x00", b"\xff", b"\x00" * 64):
                with self.subTest(vector=vector["name"], tail=extra):
                    with self.assertRaises(ValueError):
                        read_frame(frame + extra, vector["kind"])

    def test_common_version_reserved_and_id_mutations_are_rejected(self):
        invalid_fields = ((4, 3), (6, 1), (20, 1))
        checks = 0
        for vector in self.vectors:
            valid = bytes.fromhex(vector["hex"])
            for offset, value in invalid_fields:
                broken = bytearray(valid)
                broken[offset] = value
                with self.subTest(vector=vector["name"], offset=offset):
                    with self.assertRaises(ValueError):
                        read_frame(bytes(broken), vector["kind"])
                checks += 1
            missing_id = bytearray(valid)
            missing_id[24:40] = bytes(16)
            with self.subTest(vector=vector["name"], zero_request_id=True):
                with self.assertRaises(ValueError):
                    read_frame(bytes(missing_id), vector["kind"])
            checks += 1
        self.assertEqual(checks, 48)

    def test_sequence_high_half_is_zero_even_in_error_response(self):
        budget_vectors = (v for v in self.vectors if v["opcode"] == 3)
        checked = 0
        for vector in budget_vectors:
            frame = bytearray.fromhex(vector["hex"])
            frame[32] = 0x01
            with self.subTest(vector=vector["name"]):
                with self.assertRaises(ValueError):
                    read_frame(bytes(frame), vector["kind"])
            checked += 1
        self.assertEqual(checked, 3)

    def test_success_apply_and_terminal_history_share_elapsed_cpu_bounds(self):
        vectors = {v["name"]: bytes.fromhex(v["hex"]) for v in self.vectors}
        usage = vectors["read_usage_lowered_cap"]
        applied = vectors["install_budget_ok"]
        history = vectors["query_delivery_terminal"]
        sample, _, start, used, cap, period, _, _ = struct.unpack_from("<8Q", usage, 64)
        previous, effective, consumed = struct.unpack_from("<3Q", applied, 64)
        state, saved_status, reserved, seq = struct.unpack_from("<HHIQ", history, 64)
        revision, prior, history_time, history_used = struct.unpack_from("<4Q", history, 96)
        self.assertEqual(period, 100_000_000)
        self.assertEqual(start, sample // period * period)
        self.assertLessEqual(used, sample - start)
        self.assertGreater(used, cap, "lowered cap must not erase consumed CPU")
        self.assertLessEqual(consumed, effective % period)
        self.assertEqual((state, saved_status, reserved, seq), (1, 0, 0, 1))
        self.assertEqual((revision, prior), (previous + 1, previous))
        self.assertEqual((history_time, history_used), (effective, consumed))


if __name__ == "__main__":
    unittest.main()
