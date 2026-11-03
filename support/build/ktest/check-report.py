#!/usr/bin/env python3
"""Recheck a complete default ktest report against each raw QEMU guest.

The required crate inventory comes from the exact checkout's runner. Every
crate retains the full, unfiltered per-test checks in check.py; aggregate
success alone never qualifies missing, duplicated, or unexecuted suites.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


runner = module("aggregate_ktest_runner", HERE / "run.py")
checker = module("aggregate_ktest_checker", HERE / "check.py")


def read_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("missing, linked, or oversized ktest JSON: " + str(path))
    return json.loads(path.read_text())


def check_report(directory):
    report = read_json(directory / "result.json")
    if not isinstance(report, dict) or report.get("passed") is not True:
        raise ValueError("complete ktest report is not passed")
    entries = report.get("crates")
    if not isinstance(entries, list) or len(entries) != len(runner.CRATES):
        raise ValueError("complete ktest report must contain every required crate exactly once")
    observed = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("passed") is not True:
            raise ValueError("ktest crate report is incomplete")
        guests = entry.get("guests")
        if (not isinstance(guests, list) or not guests
                or not all(isinstance(guest, dict) for guest in guests)):
            raise ValueError("ktest crate has no complete guest records")
        crates = {guest.get("crate") for guest in guests}
        if len(crates) != 1:
            raise ValueError("ktest crate mixes guest identities")
        crate = next(iter(crates))
        if crate not in runner.CRATES or crate in observed:
            raise ValueError("unknown or repeated ktest crate: " + str(crate))
        observed[crate] = entry
    if set(observed) != set(runner.CRATES):
        raise ValueError("complete ktest crate inventory differs from the runner")
    for crate in runner.CRATES:
        target = directory / crate
        guest_paths = sorted((target / "guests").glob("guest-*"))
        if not guest_paths:
            raise ValueError("no raw QEMU guests for " + crate)
        replayed = []
        for guest in guest_paths:
            if guest.is_symlink() or not guest.is_dir():
                raise ValueError("QEMU guest must be a regular directory")
            for name in ("qemu.json", "serial.log"):
                path = guest / name
                if path.is_symlink() or not path.is_file():
                    raise ValueError("missing or linked raw QEMU record: " + str(path))
            replayed.append(checker.check_guest(guest, crate))
        expected = {"passed": True, "guests": replayed}
        if read_json(target / "result.json") != expected or observed[crate] != expected:
            raise ValueError("ktest report differs from the raw QEMU evidence for " + crate)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        report = check_report(args.directory)
    except (ValueError, KeyError, OSError, TypeError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps({"passed": True, "required_crates": list(runner.CRATES),
                      "guests_rechecked": sum(len(entry["guests"]) for entry in report["crates"])}, indent=2))


if __name__ == "__main__":
    main()
