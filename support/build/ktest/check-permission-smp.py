#!/usr/bin/env python3
"""Verify the three fixed permission races from genuine two-CPU QEMU evidence.

The command-line entry accepts only the positive candidate. The companion
negative-control runner calls check_guest with one of the two fixed defects;
neither arbitrary expected failures nor reduced test sets are accepted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
PREFIX = "aster_core::fs::fs_impls::ramfs::"
TESTS = {
    "owner_alias": PREFIX + "fs::permission_smp_tests::owner_alias::permission_attr_smp",
    "clear_setid_alias": PREFIX + "fs::permission_smp_tests::clear_setid_alias::permission_attr_smp",
    "memfd_seal": PREFIX + "memfd::permission_smp_tests::permission_attr_smp",
}
FAILURES = {
    None: set(),
    "ramfs-split-lock": {"owner_alias", "clear_setid_alias"},
    "memfd-release-seal": {"memfd_seal"},
}
PROFILE = {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max",
           "vcpus": 2, "memory_mib": 512, "network": False, "data_disks": False}
FATAL = ("An uncaught panic occurred:", "Uncaught panic:", "unknown panic payload!",
         "Non-resettable panic!", "The panic handler panicked", "Panicked in `PanicGuard`")
BOOTSTRAP = "PERMISSION_SMP_BOOTSTRAP scheduler=class runner_cpu=0 runner_thread=true"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_serial(raw, control=None):
    require(control in FAILURES, "unknown permission negative control")
    serial = ANSI.sub("", raw.decode()).replace("\r", "")
    require("[skipped:" not in serial, "permission race was soft-skipped")
    require(not any(marker in serial for marker in FATAL), "fatal or uncaught kernel panic")
    bootstrap = list(re.finditer(r"^" + re.escape(BOOTSTRAP) + r"$", serial, re.M))
    require(serial.count("PERMISSION_SMP_BOOTSTRAP") == 1 and len(bootstrap) == 1,
            "class-scheduled real-thread bootstrap is missing, repeated or malformed")
    require(len(re.findall(r"\[ktest runner\] running \d+ tests in \d+ crates", serial)) == 1,
            "kernel runner start is missing or repeated")
    headers = list(re.finditer(r'^running (\d+) tests in crate "([^"]+)"$', serial, re.M))
    require(len(headers) == 1 and headers[0][2] == "aster-core", "unexpected crate header")
    require(bootstrap[0].end() < serial.index("[ktest runner] running"),
            "real-thread bootstrap must precede the original test runner")
    summaries = list(re.finditer(
        r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) filtered out\.$", serial, re.M))
    require(len(summaries) == 1 and headers[0].end() < summaries[0].start(),
            "kernel summary is missing, repeated or out of order")
    summary = summaries[0]
    section = serial[headers[0].end():summary.start()]
    starts = list(re.finditer(r"^test ([\w:]+) \.\.\.", section, re.M))
    require(len(starts) == len(TESTS) and {start[1] for start in starts} == set(TESTS.values()),
            "the exact three permission race tests did not run once each")
    require(serial.count("PERMISSION_SMP_OBSERVATION") == len(TESTS),
            "permission observations are missing, repeated or outside their test")
    expected_failures = FAILURES[control]
    observations, outcomes = {}, {}
    cases_by_name = {name: case for case, name in TESTS.items()}
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(section)
        body = section[start.end():end]
        terminals = re.findall(r" (ok|FAILED)\n", body)
        terminal = re.search(r" (ok|FAILED)\n\n*\Z", body)
        require(len(terminals) == 1 and terminal is not None and terminals[0] == terminal[1],
                "test terminal outcome is missing or ambiguous: " + start[1])
        case = cases_by_name[start[1]]
        require(terminal[1] == ("FAILED" if case in expected_failures else "ok"),
                "unexpected failed-name set: " + case)
        lines = re.findall(r"^PERMISSION_SMP_OBSERVATION (.+)$", body, re.M)
        require(len(lines) == 1, "test observation is missing or repeated: " + case)
        fields = lines[0].split()
        require(all(re.fullmatch(r"[a-z_]+=[a-z0-9_]+", field) for field in fields),
                "malformed permission observation")
        pairs = [field.split("=", 1) for field in fields]
        require(len({key for key, _ in pairs}) == len(pairs), "repeated permission observation key")
        observed = dict(pairs)
        expected = {"case": case, "cpu_a": "0", "cpu_b": "1", "entered": "1",
                    "lock_busy": "false" if case in expected_failures else "true",
                    "a_rc": "0", "b_rc": "0"}
        if case == "owner_alias":
            mode = "4755" if case in expected_failures else "755"
            expected.update(uid="1002", mode=mode, alias_uid="1002", alias_mode=mode)
        elif case == "clear_setid_alias":
            mode = "755" if case in expected_failures else "600"
            expected.update(uid="1000", mode=mode, alias_uid="1000", alias_mode=mode)
        else:
            expected.update(mode="777", sealed_mode="666" if case in expected_failures else "777",
                            seal_exec="true")
        require(observed == expected, "actual permission outcome differs: " + case)
        observations[case], outcomes[start[1]] = observed, terminal[1]
    status, passed, failed, filtered = summary[1], int(summary[2]), int(summary[3]), int(summary[4])
    require(failed == len(expected_failures) and passed == len(TESTS) - failed,
            "kernel counts differ from the three observed tests")
    declared = int(headers[0][1])
    # The full suite retains 238 baseline, 17 G1-c/G1-d, five permission and two
    # ExFAT tests. This feature adds three races; only they are selected here.
    require(declared >= 265 and passed + failed + filtered == declared,
            "compiled core test denominator was reduced or is inconsistent")
    require(status == ("FAILED" if expected_failures else "ok"), "kernel summary status differs")
    require(serial.count("[ktest runner] All crates tested.") == int(not expected_failures),
            "runner completion differs from the original success/failure path")
    return {"declared": declared, "passed": passed, "failed": failed, "filtered": filtered,
            "tests": outcomes, "observations": observations}


def check_guest(guest, control=None, kernel_path=None):
    require(control in FAILURES, "unknown permission negative control")
    record = json.loads((guest / "qemu.json").read_text())
    raw = (guest / "serial.log").read_bytes()
    require(record.get("serial_sha256") == sha(raw), "raw serial digest differs")
    require(record.get("crate") == "aster-core" and record.get("ktest_profile") == "permission-attr-smp"
            and record.get("profile") == PROFILE, "guest did not use the fixed two-CPU profile")
    expected_exit = 65 if control is not None else 33
    require(record.get("raw_exit_code") == expected_exit and record.get("timed_out") is False,
            "guest exit is not the expected real kernel-test result")
    argv = record["argv"]
    require(isinstance(argv, list) and argv and all(isinstance(arg, str) for arg in argv),
            "actual QEMU command is malformed")
    requested, artifacts = record["requested_osdk_args"], record["artifacts"]
    expected_argv = [argv[0]]
    for option in ("-kernel", "-initrd", "-append"):
        positions = [index for index, arg in enumerate(requested) if arg == option]
        if option == "-initrd" and not positions:
            continue
        require(len(positions) == 1 and positions[0] + 1 < len(requested),
                "OSDK kernel input is missing or repeated: " + option)
        value = requested[positions[0] + 1]
        expected_argv.extend((option, value))
        if option != "-append":
            require(str(Path(value).resolve()) == artifacts[option]["path"],
                    "recorded kernel input path differs: " + option)
    expected_argv.extend(("-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", artifacts["-bios"]["path"],
                          "-m", "512M", "-smp", "2", "-nodefaults", "-no-user-config", "-no-reboot",
                          "-nographic", "-display", "none", "-monitor", "none", "-serial", "chardev:serial",
                          "-chardev", f"stdio,id=serial,signal=off,logfile={guest / 'serial.log'}",
                          "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"))
    require(argv == expected_argv, "actual QEMU arguments differ from the fixed profile")
    for option, artifact in artifacts.items():
        require(option in ("-kernel", "-initrd", "-bios"), "unexpected QEMU artifact")
        path = Path(kernel_path) if option == "-kernel" and kernel_path is not None else Path(artifact["path"])
        data = path.read_bytes()
        require(len(data) == artifact["size"] and len(data) > 0 and sha(data) == artifact["sha256"],
                "QEMU input bytes differ: " + option)
    require(sha(Path(argv[0]).read_bytes()) == record["qemu_sha256"], "QEMU binary digest differs")
    report = parse_serial(raw, control)
    report.update(crate="aster-core", guest=guest.name, raw_qemu_exit=expected_exit, soft_skipped=0,
                  kernel_sha256=artifacts["-kernel"]["sha256"], serial_sha256=sha(raw),
                  control=control, product_qualification=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    guests = sorted(args.directory.resolve().glob("guest-*"))
    try:
        require(len(guests) == 1, "exactly one real permission SMP guest is required")
        result = check_guest(guests[0])
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps({"passed": True, "guests": [result]}, indent=2))


if __name__ == "__main__":
    main()
