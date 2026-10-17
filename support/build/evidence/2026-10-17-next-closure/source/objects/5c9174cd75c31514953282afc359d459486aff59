"""Independent N0 boundary checks using the existing Python byte oracle.

The production implementation and corresponding exhaustive tests are Rust.
These cases alter independent fixed golden bytes, never a Rust encoding.
"""

import struct
import unittest

from test_golden_contract import PERIOD, read_frame, read_vector


# Enumerated from NATIVE_ABI's advertised-operation dependency table.
PROFILES = ((0x02, 0, 48), (0x06, 0, 64), (0x12, 40, 64),
            (0x16, 40, 64), (0x32, 40, 64), (0x36, 40, 64),
            (0x3E, 40, 64))


def accepts(frame):
    try:
        read_frame(bytes(frame), "response")
        return True
    except ValueError:
        return False


class ProfileBoundaries(unittest.TestCase):
    def test_advertised_operation_sets_match_the_explicit_profile_table(self):
        original = bytes.fromhex(read_vector("query_abi_ok")["hex"])
        valid = {mask for mask, _, _ in PROFILES}
        for mask in range(128):
            frame = bytearray(original)
            struct.pack_into("<II", frame, 84, 40, 64)
            struct.pack_into("<Q", frame, 96, mask)
            self.assertEqual(accepts(frame), mask in valid, f"ops={mask:#x}")
        for bit in range(6, 64):
            frame = bytearray(original)
            struct.pack_into("<Q", frame, 96, 0x3E | (1 << bit))
            self.assertFalse(accepts(frame), f"unknown bit={bit}")

    def test_every_profile_enforces_both_exact_payload_minima(self):
        original = bytes.fromhex(read_vector("query_abi_ok")["hex"])
        checked = 0
        for mask, minimum_request, minimum_response in PROFILES:
            for request in range(42):
                for response in range(66):
                    frame = bytearray(original)
                    struct.pack_into("<II", frame, 84, request, response)
                    struct.pack_into("<Q", frame, 96, mask)
                    expected = request >= minimum_request and response >= minimum_response
                    self.assertEqual(accepts(frame), expected,
                                     f"ops={mask:#x}, request={request}, response={response}")
                    checked += 1
            for request, response in ((65536, 65536), (65537, 65536),
                                      (65536, 65537)):
                frame = bytearray(original)
                struct.pack_into("<II", frame, 84, request, response)
                struct.pack_into("<Q", frame, 96, mask)
                self.assertEqual(accepts(frame), request <= 65536 and response <= 65536)
        self.assertEqual(checked, 19_404)

    def test_n0_usage_accepts_closed_bounds_and_rejects_misaligned_windows(self):
        original = bytes.fromhex(read_vector("read_usage_lowered_cap")["hex"])
        for sample in (0, 1, PERIOD - 1, PERIOD, PERIOD + 1, 2**64 - 1):
            start, elapsed = divmod(sample, PERIOD)
            start *= PERIOD
            for cap in (0, PERIOD):
                for consumed in (0, elapsed):
                    frame = bytearray(original)
                    struct.pack_into("<6Q", frame, 64, sample, consumed, start,
                                     consumed, cap, PERIOD)
                    self.assertTrue(accepts(frame), (sample, cap, consumed))
                    impossible = bytearray(frame)
                    struct.pack_into("<Q", impossible, 72, elapsed + 1)
                    struct.pack_into("<Q", impossible, 88, elapsed + 1)
                    self.assertFalse(accepts(impossible), (sample, "elapsed+1"))
                    if start:
                        misaligned = bytearray(frame)
                        struct.pack_into("<Q", misaligned, 80, start - 1)
                        self.assertFalse(accepts(misaligned), (sample, "start-1"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
