#!/usr/bin/env python3
"""Allow one reviewed observer exponent spelling; preserve every other byte."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys


# Recorded from the actual Desktop 64736996 source and original lock, Rust 1.88.
ORIGINAL_SHA256 = "1e4ced2871836a18177f166de7394b7f32d8de98af6fd6f1b4206ef28b2f85dd"
CASE = "response/resources/f32-7f7fffff"
OLD_TOKEN = b'\\"load_average_1m\\":3.4028235e38'
ALIGNED_TOKEN = b'\\"load_average_1m\\":3.4028235e+38'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compare(original, candidate):
    if digest(original) != ORIGINAL_SHA256:
        raise ValueError("Original corpus is not the recorded original-source/lock output")
    old, new = json.loads(original), json.loads(candidate)
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ValueError("The two corpora must be JSON objects")
    if len(old) != 52 or len(new) != 52 or set(old) != set(new):
        raise ValueError("The exact 52 original cases are required")
    if not all(isinstance(value, str) for corpus in (old, new) for value in corpus.values()):
        raise ValueError("Corpus values must remain the original encoded strings")
    report = {
        "passed": True,
        "original_sha256": digest(original),
        "candidate_sha256": digest(candidate),
        "case_count": 52,
        "exact_stdout_bytes_equal": original == candidate,
        "exact_case_values": 52,
        "allowed_observer_exponent_changes": [],
        "scope": "Bounded observer/IPC corpus; not all JSON inputs, signatures or renderer qualification.",
    }
    if original == candidate:
        return report
    # The comparison is over the complete actual stdout, including JSON order,
    # escaping and whitespace. It is not a generic JSON canonicalizer.
    if original.count(OLD_TOKEN) != 1:
        raise ValueError("Expected exactly one recorded MAX-f32 observer token")
    if candidate != original.replace(OLD_TOKEN, ALIGNED_TOKEN, 1):
        raise ValueError("Bytes differ outside the one reviewed observer exponent spelling")
    different = [name for name in old if old[name] != new[name]]
    if different != [CASE]:
        raise ValueError("A different corpus case changed")
    old_response = json.loads(old[CASE], parse_float=Decimal)
    new_response = json.loads(new[CASE], parse_float=Decimal)
    old_number = old_response["resources"]["load_average_1m"]
    new_number = new_response["resources"]["load_average_1m"]
    if (
        old_response != new_response
        or not isinstance(old_number, Decimal)
        or not isinstance(new_number, Decimal)
        or not old_number.is_finite()
        or old_number != Decimal("3.4028235e38")
        or new_number != old_number
    ):
        raise ValueError("The one observer token is not the same finite decimal value")
    report["exact_case_values"] = 51
    report["allowed_observer_exponent_changes"] = [
        {"case": CASE, "path": "resources.load_average_1m", "original": "3.4028235e38", "candidate": "3.4028235e+38"}
    ]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = compare(args.original.read_bytes(), args.candidate.read_bytes())
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"passed": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
