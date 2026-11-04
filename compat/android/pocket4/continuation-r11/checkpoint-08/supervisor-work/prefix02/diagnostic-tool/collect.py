"""Compare the two pinned read-only captures of one original Main system_server."""
import hashlib
import json
import os
import stat
import time
import types

ROOT = "/home/alex/work/pocket4-relay-prefix-r11-source-05-01"
PLAN = ROOT + "/normal-plan-01.json"
PLAN_SHA = "dd9c420ae36678e3dc6fc4cbac4b08730a133a6b4b37ae11496c6f4b46babaef"
ACTOR = ROOT + "/source/full_prefix_control.py"
ACTOR_SHA = "1432b761fbc289877465c0a167b7ff213cd9c87f0086495ddfeecf7b55e65745"
COORDINATOR = ROOT + "/source/prefix_coordinator.py"
COORDINATOR_SHA = "05bf5f46240b303b1af7f3850b5d683dcaa295fd4ee94a973c2b104eb08641ba"
GUARD = "/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py"
GUARD_SHA = "f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288"
PID = 3589120
BIRTH = 80797249

def need(value, message):
    if not value:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def fields(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_size,
            s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)

def read_pinned(path, digest, maximum=65536):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_mode & 0o6022 == 0
             and 0 < before.st_size <= maximum, "fixed source metadata/bound differs")
        data = bytearray()
        while True:
            part = os.read(fd, min(8192, maximum + 1 - len(data)))
            if not part:
                break
            data.extend(part)
            need(len(data) <= maximum, "fixed source grew")
        need(fields(before) == fields(os.fstat(fd)) and len(data) == before.st_size
             and sha(data) == digest, "fixed source changed or SHA differs")
        return bytes(data)
    finally:
        os.close(fd)

def module(path, digest, name):
    value = {"__name__": name, "__file__": path}
    exec(compile(read_pinned(path, digest), path, "exec"), value)
    return value

def differences(value, expected):
    return {key: {"expected": expected.get(key), "observed": value.get(key)}
            for key in sorted(set(value) | set(expected)) if value.get(key) != expected.get(key)}

need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, "exact root reader required")
plan = json.loads(read_pinned(PLAN, PLAN_SHA))
expected = plan["main"]["framework_binding"]["processes"]["system_server"]
need(expected["host_pid"] == PID and expected["start_ticks"] == BIRTH
     and plan["main"]["framework_sha256"] == "48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f"
     and plan["sources"]["actor"] == {"path": ACTOR, "sha256": ACTOR_SHA}
     and plan["sources"]["coordinator"] == {"path": COORDINATOR, "sha256": COORDINATOR_SHA},
     "fixed original Main/source contract differs")
actor = module(ACTOR, ACTOR_SHA, "pinned_read_only_prefix_actor")
coordinator = module(COORDINATOR, COORDINATOR_SHA, "pinned_read_only_prefix_coordinator")
guard = module(GUARD, GUARD_SHA, "pinned_read_only_epoch_guard")
pidfd = os.pidfd_open(PID)
directory = None
try:
    before, directory = actor["identity"](pidfd)
    need(before["pid"] == PID and before["birth"] == BIRTH and before["parent"] == expected["parent_host_pid"]
         and before["uids"] == expected["uids"] and before["nspid"] == expected["namespace_pids"]
         and {name: os.readlink("ns/" + name, dir_fd=directory) for name in ("mnt", "pid")} == expected["namespaces"],
         "original generation/namespace no longer matches; no replacement accepted")
    started = time.monotonic_ns()
    raw_before = actor["bounded"](directory, "cmdline", 8192)
    capture = coordinator["MainFence"].capture(types.SimpleNamespace(actor=actor), pidfd)
    canonical = guard["process_identity"](PID)
    raw_after = actor["bounded"](directory, "cmdline", 8192)
    after_birth = int(actor["bounded"](directory, "stat").decode().rsplit(")", 1)[1].split()[19])
    need(raw_before == raw_after and after_birth == BIRTH and not actor["dead"](pidfd)
         and actor["pidfd_pid"](pidfd) == PID, "held original identity/raw observation changed")
    legacy_argv = raw_before.decode("utf-8", "strict").split("\0")[:-1]
    canonical_argv = [item.decode("utf-8", "strict") for item in raw_before.split(b"\0") if item]
    need(capture["cmdline"] == legacy_argv and canonical["cmdline"] == canonical_argv,
         "pinned parsers did not observe the retained raw cmdline")
    source_again = {path: sha(read_pinned(path, digest)) for path, digest in
                    ((PLAN, PLAN_SHA), (ACTOR, ACTOR_SHA), (COORDINATOR, COORDINATOR_SHA), (GUARD, GUARD_SHA))}
    delta = differences(capture, expected)
    result = {"schema": 1, "scope": "ONE_ORIGINAL_MAIN_SYSTEM_SERVER_READ_ONLY_DIAGNOSIS",
              "plan_sha256": PLAN_SHA, "source_pins": source_again,
              "host_pid": PID, "start_ticks": BIRTH, "pidfd_alive_after": True,
              "expected_original": expected, "actual_prefix_capture": capture,
              "actual_epoch_guard_capture": canonical, "prefix_differences": delta,
              "epoch_guard_differences": differences(canonical, expected),
              "raw_cmdline_bytes": len(raw_before), "raw_cmdline_sha256": sha(raw_before),
              "raw_cmdline_hex": raw_before.hex(), "raw_cmdline_stable": True,
              "tail_nul_bytes": len(raw_before) - len(raw_before.rstrip(b"\0")),
              "only_cmdline_parser_difference_observed": canonical == expected and set(delta) == {"cmdline"},
              "observation_elapsed_ns": time.monotonic_ns() - started,
              "runtime_started": False, "namespace_actions": 0, "Main_actions": 0,
              "original_plan_replaced": False, "runtime_qualified": False}
    output = (json.dumps(result, sort_keys=True, ensure_ascii=True) + "\n").encode()
    need(len(output) <= 65536, "fixed diagnosis output exceeded")
    print(output.decode("ascii"), end="", flush=True)
finally:
    if directory is not None:
        os.close(directory)
    os.close(pidfd)
