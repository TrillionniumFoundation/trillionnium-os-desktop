#!/usr/bin/env python3
"""Explicit one-shot full host suite, first frozen R16 then the new build.

check is read-only. run executes only receipt-bound owned host tests, in a
fresh copy of their fixture. It never starts or changes Android. A failure or
unknown outcome leaves its claim and evidence in place; no retry path exists.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import resource
import signal
import stat
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PREP_SHA = "3f12e8bcde951712a20208aaeed04f1125bac58993ce1a3f5a93e4f950a9b103"
R16_ROOT = Path("/home/alex/work/pocket4-proc-maps-offset-r16-20261104/frozen-build-01")
R16_BINARY_SHA = "35433eb0e466dd24387b0fcfbe933bcc0477b7fea193ad474e68e1c0a9d5141d"
R16_ENGINE_SHA = "c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d"
R16_LAYOUT_SHA = "e369b6bce365bd2553be7193bdeea22975d0e26d13d4bb73e826f10b6be78cd2"
DATA = ("decoder/arm64_test/arm64_decoder_encodings.txt",
        "decoder/arm64_test/arm64_decoder_undefined_baseline.txt",
        "heavy_optimizer/arm64/arm64_tier_coverage.txt")
LIBRARIES = ("libbase.so", "liblog.so", "libc++.so")
LIMITS = {"cpu.max": "100000 100000", "memory.max": "1073741824",
          "memory.high": "max", "memory.swap.max": "0", "pids.max": "128"}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def unique_object(items):
    result = {}
    for key, value in items:
        need(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def json_bytes(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def read_pin(row):
    path = Path(row["path"])
    need(path.is_absolute() and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]), "absolute input and explicit SHA required")
    need(path.is_file() and sha(path) == row["sha256"], "input pin differs: " + str(path))
    return json_bytes(path.read_bytes())


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def verify_source(path, expected):
    path = Path(path)
    need(path.parent.resolve() == HERE, "host wrapper source manifest directory differs")
    manifest = read_pin({"path": str(path), "sha256": expected})
    need(manifest["artifact"] == "isolated-signal-canary-runtime-r1" and
         {"run.py", "host_suite.py", "host-test-contract.json"}.issubset(manifest["files"]), "incomplete host wrapper source manifest")
    for relative, row in manifest["files"].items():
        name = Path(relative)
        need(not name.is_absolute() and ".." not in name.parts, "bad source path")
        need(sha(HERE / name) == row["sha256"], "host wrapper source changed: " + relative)
    return manifest


def preparation(directory):
    root = Path(directory)
    manifest = read_pin({"path": str(root / "source-manifest.json"), "sha256": PREP_SHA})
    for name, row in manifest["files"].items():
        need(sha(root / name) == row["sha256"], "preparation source changed")
    spec = importlib.util.spec_from_file_location("host_suite_pinned_preparation", root / "prepare.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract():
    value = json_bytes((HERE / "host-test-contract.json").read_bytes())
    need(value["schema"] == 1 and value["registered_count"] == 3793 and
         value["executed_count"] == 3791 and len(value["registered"]) == 3793 and
         len(set(value["registered"])) == 3793 and len(value["disabled"]) == 2 and
         len(value["skipped"]) == 3, "reference suite contract differs")
    return value


def registration(raw):
    suite, names = None, []
    for line in raw.decode("utf-8", errors="strict").splitlines():
        text = line.split("#", 1)[0].rstrip()
        if not text:
            continue
        if not text[0].isspace():
            need(text.endswith(".") and not any(c.isspace() for c in text), "unexpected registration suite line")
            suite = text[:-1]
        else:
            name = text.strip()
            need(suite is not None and line.startswith("  ") and name and not any(c.isspace() for c in name),
                 "unexpected registration test line")
            names.append(suite + "." + name)
    need(len(names) == len(set(names)), "duplicate registered test")
    return sorted(names)


def assess_xml(raw, reference):
    need(b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(), "XML entities are prohibited")
    root = ET.fromstring(raw)
    need(root.tag == "testsuites", "missing completed GTest suite root")
    need(int(root.attrib["tests"]) == 3793 and int(root.attrib["disabled"]) == 2 and
         int(root.attrib["failures"]) == 0 and int(root.attrib["errors"]) == 0, "full suite XML totals differ")
    need(not list(root.iter("failure")) and not list(root.iter("error")), "test failure in XML")
    names, skipped, disabled, completed = [], {}, [], []
    for suite in root:
        need(suite.tag == "testsuite", "unexpected XML top-level child")
        cases = list(suite.findall("testcase"))
        need(len(cases) == int(suite.attrib["tests"]) and int(suite.attrib["failures"]) == 0 and
             int(suite.attrib["errors"]) == 0, "suite XML summary differs")
        suite_skipped, suite_disabled = 0, 0
        for case in cases:
            name = case.attrib["classname"] + "." + case.attrib["name"]
            need(case.attrib["classname"] == suite.attrib["name"], "test belongs to another XML suite")
            names.append(name)
            state = (case.attrib["status"], case.attrib["result"])
            if state == ("notrun", "suppressed"):
                need(not list(case), "suppressed case has unexpected outcome")
                disabled.append(name); suite_disabled += 1
            elif state == ("run", "skipped"):
                children = list(case)
                need(len(children) == 1 and children[0].tag == "skipped", "skip outcome is incomplete")
                message = children[0].attrib["message"]
                # Keep the actual reason, independent of source line numbers.
                reason = message.split("\n", 1)[-1]
                skipped[name] = reason; suite_skipped += 1
            else:
                need(state == ("run", "completed") and not list(case), "test did not complete")
                completed.append(name)
        need(int(suite.attrib["disabled"]) == suite_disabled and
             int(suite.attrib.get("skipped", "0")) == suite_skipped, "suite skip/disabled totals differ")
    need(len(names) == len(set(names)) and sorted(names) == reference["registered"], "XML test set differs from full registration")
    need(sorted(disabled) == reference["disabled"] and skipped == reference["skipped"], "disabled or skipped contract differs")
    need(len(completed) == 3788 and len(completed) + len(skipped) == 3791, "executed count differs")
    return {"registered_count": len(names), "executed_count": len(completed) + len(skipped),
            "completed_count": len(completed), "disabled": sorted(disabled), "skipped": skipped,
            "failed_cases": [], "all_expected_registered_executed": True}


def file_identity(path, digest, root, elf=False):
    path, root = Path(path), Path(root)
    need(path.is_absolute() and path.is_relative_to(root) and path.resolve(strict=True).is_relative_to(root),
         "artifact outside exact selected source tree")
    metadata = path.stat()
    need(stat.S_ISREG(metadata.st_mode) and sha(path) == digest, "artifact bytes changed: " + str(path))
    if elf:
        with path.open("rb") as stream:
            header = stream.read(20)
        need(len(header) == 20 and header[:6] == b"\x7fELF\x02\x01" and int.from_bytes(header[18:20], "little") == 62,
             "host artifact is not x86_64 ELF64")
    return {"path": str(path), "sha256": digest, "bytes": metadata.st_size,
            "device": metadata.st_dev, "inode": metadata.st_ino}


def artifact_binding(config, prep):
    selected = config["binding"]
    arm = config["arm"]
    if arm == "candidate":
        receipt = prep.candidate_binding(selected)
        out = Path(receipt["output_directory"])
        host = receipt["host_tests"]
        directory = out / "host/linux-x86/nativetest64/berberis_arm64_host_tests"
        libs = out / "host/linux-x86/lib64"
        need(host["directory"] == str(directory) and host["binary_path"] == str(directory / "berberis_arm64_host_tests") and
             host["shared_library_directory"] == str(libs), "candidate host fixture layout differs")
        need(host["built"] is True and host["executed"] is False and host["variant"] == "linux_glibc_x86_64" and
             host["guest_architecture"] == "arm64", "candidate build is not the complete unrun host fixture")
        binary_sha, data, libraries = host["binary"]["sha256"], host["data"], host["shared_libraries"]
        engine = selected["engine"]
        receipt_binding = selected["candidate_build_receipt"]
    else:
        need(arm == "baseline", "unknown arm")
        need(selected["layout"]["sha256"] == R16_LAYOUT_SHA, "baseline layout is not the reviewed exact seven-file inventory")
        layout = read_pin(selected["layout"])
        need(layout["schema"] == 1 and layout["kind"] == "frozen-r16-host-layout" and
             layout["root"] == str(R16_ROOT), "unknown frozen baseline layout")
        out = R16_ROOT
        directory = out / "host/linux-x86/testcases/berberis_arm64_host_tests/x86_64"
        libs = Path(layout["shared_library_directory"])
        need(layout["binary"]["path"] == str(directory / "berberis_arm64_host_tests") and
             layout["binary"]["sha256"] == R16_BINARY_SHA, "historical baseline binary differs")
        binary_sha, data, libraries = R16_BINARY_SHA, layout["data"], layout["shared_libraries"]
        # This arm executes the exact historical host binary. The Android
        # engine label is historical context, not an Android artifact test.
        engine = None
        receipt_binding = selected["layout"]
    need(out.resolve(strict=True) == out and libs.is_relative_to(out), "selected tree is aliased")
    need(set(data) == set(DATA) and set(libraries) == set(LIBRARIES), "full three-corpus / three-library set required")
    records = [{"kind": "binary", "relative": "bin/berberis_arm64_host_tests",
                **file_identity(directory / "berberis_arm64_host_tests", binary_sha, out, True)}]
    for name in DATA:
        records.append({"kind": "data", "relative": "bin/" + name, **file_identity(directory / name, data[name], out)})
    for name in LIBRARIES:
        records.append({"kind": "library", "relative": "lib/" + name,
                        **file_identity(libs / name, libraries[name]["sha256"], out, True)})
    engine_identity = (file_identity(engine["path"], engine["sha256"], out, True) if engine is not None else
                       {"sha256": R16_ENGINE_SHA, "qualification": "historical_R16_label_not_executed_by_host_suite"})
    return {"arm": arm, "source_receipt": receipt_binding, "engine": engine_identity, "records": records}


def resources(config):
    text = Path("/proc/self/cgroup").read_text().strip()
    expected = "/system.slice/" + config["unit"]
    need(text == "0::" + expected, "host tests require their exact independent controller unit")
    root = Path("/sys/fs/cgroup") / expected.lstrip("/")
    limits = {name: (root / name).read_text().strip() for name in LIMITS}
    need(limits == LIMITS, "host test resource limits differ")
    events = {name: int(value) for name, value in (line.split() for line in (root / "memory.events").read_text().splitlines())}
    need(all(events.get(name) == 0 for name in ("max", "oom", "oom_kill", "oom_group_kill")), "host suite resource admission already failed")
    processes = sorted(int(pid) for pid in (root / "cgroup.procs").read_text().split())
    need(processes == [os.getpid()] and int((root / "pids.current").read_text()) == 1,
         "host test controller is not alone; owned descendants remain")
    return {"cgroup": expected, "limits": limits, "memory_events": events,
            "memory_current": int((root / "memory.current").read_text()), "affinity": sorted(os.sched_getaffinity(0)),
            "processes": processes, "controller_pid": os.getpid(), "threads": 1}


def validate(config, source_sha, live=True):
    need(config["schema"] == 1 and config["kind"] == "owned-full-host-suite-r1" and
         config["arm"] in ("baseline", "candidate"), "unexpected host suite inputs")
    nonce = config["nonce"]
    need(re.fullmatch(r"[0-9a-f]{32}", nonce or ""), "explicit unique host attempt nonce required")
    need(config["unit"] == "p4-signal-host-" + config["arm"] + "-" + nonce[:12] + ".service", "owned controller name differs")
    evidence = Path(config["evidence"])
    need(evidence.parent == Path("/home/alex/work") and
         re.fullmatch(r"pocket4-signal-host-(baseline|candidate)-[a-z0-9_-]{8,64}", evidence.name), "fresh owned evidence path required")
    need(evidence.parent.resolve(strict=True) == evidence.parent and type(config["cpu"]) is int and 0 <= config["cpu"] < 24,
         "host CPU/path contract differs")
    need(set(config["tools"]) == {"/usr/bin/python3", "/usr/bin/systemctl"}, "host controller tool set differs")
    for path, digest in config["tools"].items():
        need(sha(path) == digest, "host tool changed")
    need(os.stat("/proc/self/exe").st_ino == os.stat("/usr/bin/python3").st_ino and
         os.stat("/proc/self/exe").st_dev == os.stat("/usr/bin/python3").st_dev, "controller Python executable differs")
    prep = preparation(config["preparation_source"])
    binding = artifact_binding(config, prep)
    if config["arm"] == "baseline":
        need("baseline_result" not in config, "baseline may not inherit a suite result")
    else:
        previous = verify_report(Path(config["baseline_result"]["path"]), config["baseline_result"]["sha256"],
                                 None, None, source_sha, expected_arm="baseline")
        need(previous["cpu"] == config["cpu"] and previous["main_config"] == config["main"] and
             previous["tools"] == config["tools"], "baseline execution environment differs")
    if live:
        need(os.geteuid() == 0 and os.getegid() == 0 and sys.flags.optimize == 0, "root/non-optimized qualification required")
        need(config["cpu"] in os.sched_getaffinity(0), "selected CPU not available to controller")
        need(not evidence.exists() and not evidence.is_symlink(), "host suite attempt already exists; no retry")
        prep.main_snapshot(config["main"])
    return prep, binding


def copy_fixture(binding, evidence):
    fixture = evidence / "fixture"
    fixture.mkdir(mode=0o700)
    rows = []
    for record in binding["records"]:
        target = fixture / record["relative"]
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o500 if record["kind"] == "binary" else 0o400)
        with Path(record["path"]).open("rb") as source, os.fdopen(descriptor, "wb") as destination:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                destination.write(block)
            destination.flush(); os.fsync(destination.fileno())
        copied = file_identity(target, record["sha256"], fixture, record["kind"] != "data")
        need(copied["bytes"] == record["bytes"], "staged fixture size differs")
        rows.append({"kind": record["kind"], "relative": record["relative"], **copied})
    save(evidence / "tested-fixture.json", rows)
    return rows


def mapped_fixture(pid, rows):
    text = Path("/proc", str(pid), "maps").read_text()
    mapped = []
    for row in rows:
        if row["kind"] == "data":
            continue
        matches = []
        for line in text.splitlines():
            fields = line.split(None, 5)
            if len(fields) < 5:
                continue
            major, minor = fields[3].split(":")
            if (os.makedev(int(major, 16), int(minor, 16)) == row["device"] and
                    int(fields[4]) == row["inode"] and "x" in fields[1]):
                matches.append(line)
        if not matches:
            return None
        mapped.append({"relative": row["relative"], "sha256": row["sha256"], "device": row["device"],
                       "inode": row["inode"], "executable_mappings": matches})
    start = Path("/proc", str(pid), "stat").read_text().rsplit(")", 1)[1].split()[19]
    return {"pid": pid, "start_ticks": start, "mapped": mapped}


def execute(label, arguments, environment, directory, evidence, rows, timeout):
    argv = [str(directory / "berberis_arm64_host_tests"), *arguments]
    item = {"label": label, "argv": argv, "cwd": str(directory), "environment": environment,
            "started_utc": now(), "timeout_seconds": timeout, "invocations_allowed": 1}
    save(evidence / (label + "-claim.json"), item)
    stdout, stderr = evidence / (label + ".stdout"), evidence / (label + ".stderr")
    mapping = None
    with stdout.open("xb") as out, stderr.open("xb") as err:
        child = subprocess.Popen(argv, cwd=directory, env=environment, stdin=subprocess.DEVNULL,
                                 stdout=out, stderr=err, close_fds=True, start_new_session=True)
        item["pid"] = child.pid
        deadline = time.monotonic() + timeout
        try:
            while child.poll() is None:
                if label == "full-suite" and mapping is None:
                    try:
                        mapping = mapped_fixture(child.pid, rows)
                    except (FileNotFoundError, ProcessLookupError):
                        pass
                if time.monotonic() >= deadline:
                    item["timed_out"] = True
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                    break
                time.sleep(.01)
        except BaseException:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            item["controller_interrupted"] = True
            raise
        finally:
            out.flush(); os.fsync(out.fileno()); err.flush(); os.fsync(err.fileno())
            item.update(returncode=child.returncode, finished_utc=now(), actual_mapped_fixture=mapping,
                        stdout_sha256=sha(stdout), stderr_sha256=sha(stderr))
            save(evidence / (label + "-terminal.json"), item)
    need(child.returncode == 0 and not item.get("timed_out"), label + " did not complete successfully")
    if label == "full-suite":
        need(mapping is not None and len(mapping["mapped"]) == 4, "complete actual binary/library mapping not observed")
    return item


def expected_command(label, evidence):
    if label == "registration":
        return ["--gtest_list_tests", "--gtest_color=no"]
    return ["--gtest_filter=*", "--gtest_repeat=1", "--gtest_color=no", "--gtest_output=xml:" + str(evidence / "results.xml")]


def verify_report(path, expected, candidate_build, engine, source_sha, expected_arm="candidate"):
    verify_source(HERE / "source-manifest.json", source_sha)
    report = read_pin({"path": str(path), "sha256": expected})
    need(report["schema"] == 1 and report["state"] == "PASS_FULL_HOST_SUITE" and report["arm"] == expected_arm and
         report["wrapper_manifest_sha256"] == source_sha and report["main_preserved"] is True and
         report["resources_complete"] is True and report["filter"] == "*" and report["sharding"] is False and
         report["repeat"] == 1 and report["automatic_retry"] is False, "host suite receipt is not a complete matching execution")
    config = read_pin(report["inputs"])
    need(config["arm"] == expected_arm and Path(config["evidence"]) == path.parent and path.name == "result.json",
         "host suite receipt belongs to another attempt")
    prep, binding = validate(config, source_sha, live=False)
    need(report["binding_before"] == report["binding_after"] == binding, "host artifact binding changed")
    need(report["main_before"] == report["main_after"] and report["main_config"] == config["main"], "Main host suite epoch differs")
    need(report["resources_before"]["limits"] == report["resources_after"]["limits"] == LIMITS and
         report["resources_before"]["cgroup"] == report["resources_after"]["cgroup"] == "/system.slice/" + config["unit"], "host suite resource receipt differs")
    for item in (report["resources_before"], report["resources_after"]):
        need(all(item["memory_events"].get(k) == 0 for k in ("max", "oom", "oom_kill", "oom_group_kill")), "host suite encountered resource failure")
        need(item["processes"] == [item["controller_pid"]] and item["threads"] == 1, "test descendants remain in the host controller")
    need(report["resources_before"]["controller_pid"] == report["resources_after"]["controller_pid"] and
         report["resources_after"]["affinity"] == [config["cpu"]], "host controller process / CPU affinity differs")
    evidence = path.parent
    need(sha(evidence / "claim.json") == report["claim_sha256"], "host suite attempt claim changed")
    claim = json_bytes((evidence / "claim.json").read_bytes())
    need(claim["nonce"] == config["nonce"] and claim["inputs"] == report["inputs"] and
         claim["wrapper_manifest_sha256"] == source_sha, "host suite claim differs")
    rows = json_bytes((evidence / "tested-fixture.json").read_bytes())
    need(sha(evidence / "tested-fixture.json") == report["tested_fixture_sha256"] and len(rows) == 7,
         "host tested fixture incomplete")
    current = []
    for wanted, row in zip(binding["records"], rows):
        target = evidence / "fixture" / wanted["relative"]
        need(row["kind"] == wanted["kind"] and row["relative"] == wanted["relative"] and row["path"] == str(target) and
             row["sha256"] == wanted["sha256"], "copied fixture differs from build artifacts")
        current.append({"kind": row["kind"], "relative": row["relative"],
                        **file_identity(target, row["sha256"], evidence / "fixture", row["kind"] != "data")})
    need(current == rows == report["tested_fixture_after"], "tested fixture changed during/after execution")
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "HOME": str(evidence / "home"),
                   "TMPDIR": str(evidence / "tmp"), "LD_LIBRARY_PATH": str(evidence / "fixture/lib")}
    for label in ("registration", "full-suite"):
        terminal = json_bytes((evidence / (label + "-terminal.json")).read_bytes())
        need(sha(evidence / (label + "-terminal.json")) == report["terminals"][label] and terminal["returncode"] == 0 and
             not terminal.get("timed_out") and not terminal.get("controller_interrupted"), "test process did not finish successfully")
        need(terminal["argv"] == [str(evidence / "fixture/bin/berberis_arm64_host_tests"), *expected_command(label, evidence)] and
             terminal["cwd"] == str(evidence / "fixture/bin") and terminal["environment"] == environment and
             terminal["invocations_allowed"] == 1, "test command/environment differs")
        for extension in ("stdout", "stderr"):
            need(sha(evidence / (label + "." + extension)) == terminal[extension + "_sha256"], "raw host test output changed")
        if label == "full-suite":
            mapping = terminal["actual_mapped_fixture"]
            need(mapping["pid"] == terminal["pid"] and len(mapping["mapped"]) == 4, "actual mapped fixture evidence missing")
            expected_rows = [r for r in rows if r["kind"] != "data"]
            for observed, row in zip(mapping["mapped"], expected_rows):
                need(all(observed[k] == row[k] for k in ("relative", "sha256", "device", "inode")) and
                     observed["executable_mappings"], "actual library/binary map binding differs")
    reference = contract()
    need(sha(HERE / "host-test-contract.json") == report["test_contract_sha256"], "host suite contract changed")
    need(registration((evidence / "registration.stdout").read_bytes()) == reference["registered"], "full registration differs")
    need(sha(evidence / "results.xml") == report["xml_sha256"], "host XML changed")
    need(assess_xml((evidence / "results.xml").read_bytes(), reference) == report["assessment"], "host XML assessment differs")
    if expected_arm == "candidate":
        need(candidate_build == config["binding"]["candidate_build_receipt"] and engine == config["binding"]["engine"],
             "host suite does not qualify this exact candidate build and engine")
    return {"receipt": str(path), "sha256": expected, "arm": expected_arm, "cpu": config["cpu"], "tools": config["tools"],
            "main_config": config["main"], "assessment": report["assessment"], "engine_sha256": binding["engine"]["sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("check", "run"))
    for name in ("inputs", "inputs-sha256", "source-manifest", "source-manifest-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    need(sys.flags.optimize == 0, "optimized Python is prohibited")
    verify_source(args.source_manifest, args.source_manifest_sha256)
    inputs = {"path": args.inputs, "sha256": args.inputs_sha256}
    config = read_pin(inputs)
    prep, binding = validate(config, args.source_manifest_sha256)
    if args.phase == "check":
        print(json.dumps({"state": "HOST_SUITE_INPUTS_CHECKED_NO_TEST_EXECUTION", "arm": config["arm"]}))
        return 0
    # Refuse arbitrary/root/Main launch before creating evidence or a child.
    before_resources = resources(config)
    os.sched_setaffinity(0, {config["cpu"]})
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    evidence = Path(config["evidence"])
    evidence.mkdir(mode=0o700)
    save(evidence / "claim.json", {"started_utc": now(), "nonce": config["nonce"], "inputs": inputs,
         "wrapper_manifest_sha256": args.source_manifest_sha256, "automatic_retry": False})
    result = {"schema": 1, "state": "INCOMPLETE_NO_RETRY", "arm": config["arm"], "inputs": inputs,
              "wrapper_manifest_sha256": args.source_manifest_sha256, "claim_sha256": sha(evidence / "claim.json"),
              "test_contract_sha256": sha(HERE / "host-test-contract.json"), "cpu": config["cpu"],
              "main_config": config["main"], "binding_before": binding, "resources_before": before_resources,
              "filter": "*", "sharding": False, "repeat": 1, "automatic_retry": False,
              "production_ready": False, "Android_runtime_qualification": False, "terminals": {}}
    try:
        result["main_before"] = prep.main_snapshot(config["main"])
        rows = copy_fixture(binding, evidence)
        result["tested_fixture_sha256"] = sha(evidence / "tested-fixture.json")
        for name in ("home", "tmp"):
            (evidence / name).mkdir(mode=0o700)
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "HOME": str(evidence / "home"),
                       "TMPDIR": str(evidence / "tmp"), "LD_LIBRARY_PATH": str(evidence / "fixture/lib")}
        reference = contract()
        for label, timeout in (("registration", 30), ("full-suite", 600)):
            execute(label, expected_command(label, evidence), environment, evidence / "fixture/bin", evidence, rows, timeout)
            result["terminals"][label] = sha(evidence / (label + "-terminal.json"))
            if label == "registration":
                need(registration((evidence / "registration.stdout").read_bytes()) == reference["registered"],
                     "registration differs; full suite was not invoked")
        result["xml_sha256"] = sha(evidence / "results.xml")
        result["assessment"] = assess_xml((evidence / "results.xml").read_bytes(), reference)
        result["binding_after"] = artifact_binding(config, prep)
        need(result["binding_after"] == binding, "source build artifacts changed")
        result["tested_fixture_after"] = [{"kind": row["kind"], "relative": row["relative"],
            **file_identity(row["path"], row["sha256"], evidence / "fixture", row["kind"] != "data")} for row in rows]
        need(result["tested_fixture_after"] == rows, "tested fixture changed")
        result["tests_complete"] = True
    except BaseException as error:
        result["error"] = repr(error)
        result["traceback"] = traceback.format_exc()
    finally:
        try:
            result["main_after"] = prep.main_snapshot(config["main"])
            result["main_preserved"] = result["main_after"] == result.get("main_before")
            result["resources_after"] = resources(config)
            result["resources_complete"] = True
            verify_source(args.source_manifest, args.source_manifest_sha256)
            need(read_pin(inputs) == config, "host execution inputs changed")
        except BaseException as error:
            result["postcheck_error"] = repr(error)
        complete = (result.get("tests_complete") and result.get("main_preserved") and result.get("resources_complete") and
                    not result.get("error") and not result.get("postcheck_error"))
        result["state"] = "PASS_FULL_HOST_SUITE" if complete else "INCOMPLETE_OR_FAILED_NO_RETRY"
        result["finished_utc"] = now()
        save(evidence / "result.json", result)
    print(json.dumps({key: result.get(key) for key in ("state", "arm", "assessment", "error", "postcheck_error")}))
    return 0 if complete else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"state": "ADMISSION_OR_CONTROLLER_ERROR_NO_RETRY", "error": repr(error),
                          "automatic_retry": False, "action_outcome": "CHECK_OWNED_DURABLE_CLAIM_BEFORE_ANY_FOLLOWUP"}))
        raise SystemExit(1)
