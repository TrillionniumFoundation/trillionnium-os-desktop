#!/usr/bin/env python3
"""Versioned Servo qualification dispatcher.

The original D0A-01 exact-pin interface remains the default.  S07 adds the
explicit ``verify-d3-patch`` command, which delegates to the closed retained-node
patch verifier.  Keeping the dispatcher small makes CLI drift observable while
avoiding a second implementation of either qualification contract.
"""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "verify-d3-patch":
        from verify_d3_servo_patch import main as verify_d3_patch

        return verify_d3_patch(sys.argv[2:])

    from _qualify_servo_exact_pin_v3_impl import main as qualify_exact_pin

    return qualify_exact_pin()


if __name__ == "__main__":
    raise SystemExit(main())
