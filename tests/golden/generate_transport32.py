#!/usr/bin/env python3
"""Independent x86_64 little-endian HOS2 ioctl transport golden generator.

No Rust dependency or struct-memory casting. Checks a distinct descriptor fixture
without changing the twelve HOS2/HOSR frames in hos2.json.
"""

import argparse
from pathlib import Path
import struct

FIXTURE = Path(__file__).with_name("transport32.hex")


def expected_hex() -> str:
    wire = struct.pack(
        "<QQIIQ",
        0x0102030405060708,
        0x1112131415161718,
        96,
        128,
        0,
    )
    assert len(wire) == 32
    return wire.hex() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    args = parser.parse_args()

    expected = expected_hex()
    if args.write:
        FIXTURE.write_text(expected, encoding="ascii")
    elif FIXTURE.read_text(encoding="ascii") != expected:
        parser.error("transport32.hex differs from independent Python struct.pack")
    else:
        print("1 independent 32-byte HOS2 transport golden verified")


if __name__ == "__main__":
    main()
