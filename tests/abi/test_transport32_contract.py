"""Separate Python struct oracle for the native x86_64 HOS2 transport descriptor."""

import struct
from pathlib import Path
import unittest


FIXTURE = Path(__file__).resolve().parents[1] / "golden" / "transport32.hex"
FORMAT = "<QQIIQ"


class TransportGoldenContract(unittest.TestCase):
    def test_fixed_descriptor_is_32_bytes_and_little_endian(self) -> None:
        raw = bytes.fromhex(FIXTURE.read_text(encoding="ascii").strip())
        self.assertEqual(len(raw), struct.calcsize(FORMAT))
        self.assertEqual(len(raw), 32)
        self.assertEqual(
            raw,
            struct.pack(FORMAT, 0x0102030405060708, 0x1112131415161718, 96, 128, 0),
        )
        self.assertEqual(raw[:8], bytes.fromhex("0807060504030201"))
        self.assertEqual(raw[8:16], bytes.fromhex("1817161514131211"))
        self.assertEqual(raw[24:32], bytes(8))

    def test_descriptor_fields_are_not_memory_native_layout(self) -> None:
        raw = bytes.fromhex(FIXTURE.read_text(encoding="ascii").strip())
        request_addr, response_addr, request_bytes, response_capacity, reserved = (
            struct.unpack(FORMAT, raw)
        )
        self.assertEqual(request_addr, 0x0102030405060708)
        self.assertEqual(response_addr, 0x1112131415161718)
        self.assertEqual(request_bytes, 96)
        self.assertEqual(response_capacity, 128)
        self.assertEqual(reserved, 0)
        self.assertNotEqual(raw, struct.pack(">QQIIQ", *struct.unpack(FORMAT, raw)))


if __name__ == "__main__":
    unittest.main()
