#!/usr/bin/env python3
"""One externally admitted, fresh host-prefix contract and exact retirement.

This controller creates one nonce-bound network namespace and one bounded
systemd unit. It never creates routes/veths, changes existing resource limits,
loads Android images, or acts on Main. Three modes require three separately
pinned plans. A failed, ambiguous, or already claimed plan cannot be replayed.
The internal --gate keeps the original unit MainPID alive until its actual
InvocationID, cgroup identity, and namespace identity have been captured.
"""
import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
BASE = Path("/home/alex/work/pocket4-relay-prefix-r11-owned")
SCOPE = "OWNED_HOST_PREFIX_ONLY_NO_ANDROID"
LIMITS = {"memory.max": str(256 * 1024 * 1024), "memory.swap.max": "0",
          "cpu.max": "100000 100000", "pids.max": "32"}
TOOLS = {"/usr/bin/ip", "/usr/bin/unshare", "/usr/bin/python3", "/usr/bin/systemctl", "/usr/bin/systemd-run"}
SOURCE_NAMES = {"coordinator", "actor", "probe"}
PROPERTIES = ("LoadState", "ActiveState", "SubState", "Description", "InvocationID", "ControlGroup",
              "MainPID", "ExecMainPID", "ExecMainCode", "ExecMainStatus", "Result", "Transient",
              "ExecMainStartTimestampMonotonic", "ExecMainExitTimestampMonotonic", "MemoryPeak", "MemorySwapPeak")
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"}

def need(value, message):
    if not value: raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def hex_value(value, length):
    return isinstance(value, str) and len(value) == length and set(value) <= set("0123456789abcdef") and set(value) != {"0"}

def counters(text):
    values = {}
    for line in text.splitlines():
        fields = line.split()
        need(len(fields) == 2 and fields[0] not in values and fields[1].isdigit(), "malformed/duplicate numeric counter")
        values[fields[0]] = fields[1]
    return values

def read_pinned(path, digest, maximum=65536):
    need(hex_value(digest, 64), "external file digest malformed")
    path = Path(path)
    need(path.is_absolute() and ".." not in path.parts, "external authority path malformed")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
             and before.st_mode & 0o6022 == 0 and 0 < before.st_size <= maximum,
             "external artifact owner/type/size/privilege differs")
        raw = bytearray()
        while True:
            part = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not part: break
            raw.extend(part); need(len(raw) <= maximum, "external file grew beyond bound")
        after = os.fstat(fd)
        fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mode, s.st_uid, s.st_gid, s.st_nlink, s.st_mtime_ns, s.st_ctime_ns)
        need(fields(before) == fields(after) and sha(raw) == digest, "external pinned bytes changed")
        return bytes(raw)
    finally:
        os.close(fd)

def read_json_at(directory, name, maximum=65536):
    need(name and "/" not in name and name not in (".", ".."), "not a single owned filename")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
             and info.st_mode & 0o6022 == 0 and 0 < info.st_size <= maximum,
             "owned record metadata differs")
        raw = os.read(fd, maximum + 1)
        need(len(raw) == info.st_size and len(raw) <= maximum, "owned record length changed")
        after = os.fstat(fd)
        need((info.st_size, info.st_mtime_ns, info.st_ctime_ns) ==
             (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "owned record changed while read")
        return json.loads(raw), sha(raw)
    finally:
        os.close(fd)

def atomic_json(directory, name, value):
    """Create-only atomic publication; never truncate an old claim or receipt."""
    need(os.uname().machine == "x86_64" and "/" not in name, "atomic record ABI/name differs")
    temporary = "." + name + ".pending"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=directory)
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    libc = ctypes.CDLL(None, use_errno=True)
    method = libc.renameat2
    method.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    method.restype = ctypes.c_int
    if method(directory, temporary.encode(), directory, name.encode(), 1):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), name)
    os.fsync(directory)
    return sha(raw)

def names(plan):
    prefix = "p4-relay-prefix-" + plan["nonce"][:24]
    leaf = prefix + "-" + plan["mode"]
    return {"namespace": prefix, "leaf": leaf, "unit": leaf + ".service",
            "group": "/system.slice/" + leaf + ".service", "evidence": str(BASE / leaf),
            "description": leaf + " nonce=" + plan["nonce"] + " owned-host-prefix-no-android"}

def load_plan(args):
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, "exact root caller required")
    need(sys.flags.optimize == 0, "optimized Python is forbidden")
    plan = json.loads(read_pinned(args.plan, args.plan_sha256))
    need(set(plan) == {"schema", "scope", "mode", "nonce", "sources", "tools", "limits", "main", "predecessor"},
         "unknown/missing external plan fields")
    need(plan["schema"] == 1 and plan["scope"] == SCOPE and hex_value(plan["nonce"], 64)
         and plan["mode"] in ("normal", "owner-kill", "controller-loss") and plan["limits"] == LIMITS,
         "external plan is not this finite, owned prefix contract")
    need(set(plan["sources"]) == SOURCE_NAMES and set(plan["tools"]) == TOOLS, "complete source/tool closure required")
    for row in plan["sources"].values():
        need(set(row) == {"path", "sha256"} and Path(row["path"]).is_absolute()
             and ".." not in Path(row["path"]).parts and hex_value(row["sha256"], 64), "source binding malformed")
    need(Path(plan["sources"]["coordinator"]["path"]).resolve() == Path(__file__).resolve(), "coordinator source differs")
    read_pinned(plan["sources"]["coordinator"]["path"], plan["sources"]["coordinator"]["sha256"], 262144)
    raw = read_pinned(plan["sources"]["actor"]["path"], plan["sources"]["actor"]["sha256"], 262144)
    actor = {"__name__": "pinned_prefix_actor", "__file__": plan["sources"]["actor"]["path"]}
    exec(compile(raw, actor["__file__"], "exec"), actor)
    self_pidfd = os.pidfd_open(os.getpid())
    try:
        need(actor["pidfd_pid"](self_pidfd) == os.getpid(), "initial host PID/procfs view required")
    finally:
        os.close(self_pidfd)
    for path, digest in plan["tools"].items():
        os.close(actor["current_interpreter"](digest) if path == "/usr/bin/python3" else actor["pinned"](path, digest, True))
    os.close(actor["pinned"](plan["sources"]["probe"]["path"], plan["sources"]["probe"]["sha256"], True))
    main = plan["main"]
    need(set(main) == {"framework_binding", "framework_sha256", "retained_processes", "daemon", "resources", "artifacts"},
         "Main read-only fence schema differs")
    need(set(main["framework_binding"]) == {"boot_id", "processes"}
         and set(main["framework_binding"]["processes"]) == {"init", "zygote64", "system_server", "surfaceflinger"},
         "complete framework generation fence required")
    need(sha(json.dumps(main["framework_binding"], sort_keys=True, separators=(",", ":")).encode()) == main["framework_sha256"],
         "framework fence digest is not its canonical original binding")
    need(set(main["retained_processes"]) == {"daemon_process", "launcher_process", "presenter_process"},
         "complete original host process fence required")
    need(set(main["daemon"]) == {"MainPID", "InvocationID", "ControlGroup"}
         and main["daemon"]["ControlGroup"] == "/system.slice/droidloomd.service"
         and hex_value(main["daemon"]["InvocationID"], 32), "Main unit identity malformed")
    need(set(main["resources"]) == {"memory.high", "memory.max", "memory.swap.max", "cpu.max", "pids.max"},
         "complete Main resource fence required")
    need(set(main["artifacts"]) == {"/etc/droidloom/cell.json", "/usr/bin/droidloomd", "/usr/bin/droidloom-supervisor"},
         "complete installed contract fence required")
    predecessor = plan["predecessor"]
    if plan["mode"] == "normal":
        need(predecessor is None, "normal attempt cannot reuse another attempt")
    else:
        need(isinstance(predecessor, dict) and set(predecessor) == {"path", "sha256"}, "external predecessor pin required")
        prior = json.loads(read_pinned(predecessor["path"], predecessor["sha256"], 262144))
        expected = "normal" if plan["mode"] == "owner-kill" else "owner-kill"
        need(prior.get("whole_attempt_qualified") is True and prior.get("scope") == SCOPE
             and prior.get("mode") == expected and prior.get("nonce") != plan["nonce"]
             and prior.get("sources") == plan["sources"] and prior.get("tools") == plan["tools"]
             and prior.get("Android_operations") == 0, "same-source complete predecessor not proven")
    return plan, actor

def call(argv, timeout=5, allowed=(0,)):
    value = subprocess.run(argv, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    need(len(value.stdout) <= 65536 and len(value.stderr) <= 65536, "bounded owned command output exceeded")
    need(value.returncode in allowed, "owned command failed: " + repr(argv) + " : " + value.stderr.decode(errors="replace")[-1000:])
    return value

def props(unit):
    result = call(["/usr/bin/systemctl", "show", unit, *["--property=" + key for key in PROPERTIES]], allowed=(0, 1))
    value = dict(line.split("=", 1) for line in result.stdout.decode().splitlines() if "=" in line)
    need(result.returncode == 0 or value.get("LoadState") == "not-found", "unit observation failed")
    return value

def artifact_contract(plan, actor):
    for name, row in plan["sources"].items():
        os.close(actor["pinned"](row["path"], row["sha256"], name == "probe"))
    for path, digest in plan["tools"].items():
        os.close(actor["current_interpreter"](digest) if path == "/usr/bin/python3" else actor["pinned"](path, digest, True))
    return {"sources": plan["sources"], "tools": plan["tools"], "all_pinned_bytes_match": True}

class MainFence:
    """Read-only original process/cgroup authorities; never signals or enters Main."""
    def __init__(self, plan, actor):
        self.expected = plan["main"]; self.actor = actor; self.processes = {}; self.group = None
        try:
            rows = dict(self.expected["framework_binding"]["processes"])
            rows.update(self.expected["retained_processes"])
            for role, value in rows.items():
                fd = os.pidfd_open(value["host_pid"])
                self.processes[role] = fd
            self.group = os.open("/sys/fs/cgroup/system.slice/droidloomd.service",
                                 os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
            actor["require_cgroup2"](self.group)
            s = os.fstat(self.group); self.identity = (s.st_dev, s.st_ino)
            self.check()
        except BaseException:
            self.close(); raise

    def capture(self, fd):
        value, directory = self.actor["identity"](fd)
        try:
            return {"host_pid": value["pid"], "parent_host_pid": value["parent"], "start_ticks": value["birth"],
                    "uids": value["uids"], "namespace_pids": value["nspid"],
                    # Match the pinned framework epoch representation of argv padding
                    # only for this read-only Main view; actor/launch argv stays strict.
                    "cmdline": [argument for argument in value["cmdline"] if argument],
                    "cgroup": value["cgroup"], "executable": os.readlink("exe", dir_fd=directory),
                    "namespaces": {name: os.readlink("ns/" + name, dir_fd=directory) for name in ("mnt", "pid")}}
        finally:
            os.close(directory)

    def check(self):
        e = self.expected
        current = props("droidloomd.service")
        need(current.get("ActiveState") == "active" and all(current.get(k) == v for k, v in e["daemon"].items()),
             "original Main unit generation changed")
        need(Path("/proc/sys/kernel/random/boot_id").read_text().strip() == e["framework_binding"]["boot_id"], "boot identity changed")
        expected = dict(e["framework_binding"]["processes"]); expected.update(e["retained_processes"])
        for role, value in expected.items():
            need(self.capture(self.processes[role]) == value, "Main original process changed: " + role)
        path = os.stat("/sys/fs/cgroup/system.slice/droidloomd.service", follow_symlinks=False)
        need((path.st_dev, path.st_ino) == self.identity, "Main cgroup generation changed")
        for key, value in e["resources"].items():
            need(self.actor["bounded"](self.group, key, 128).decode().strip() == value, "Main resource changed: " + key)
        for path, digest in e["artifacts"].items():
            os.close(self.actor["pinned"](path, digest, path.startswith("/usr/bin/")))
        return {"framework_sha256": e["framework_sha256"], "daemon": e["daemon"],
                "held_cgroup_identity": list(self.identity), "resources": e["resources"],
                "original_processes_alive_and_unchanged": True, "installed_contract_unchanged": True}

    def close(self):
        for fd in self.processes.values(): os.close(fd)
        self.processes.clear()
        if self.group is not None: os.close(self.group); self.group = None

def actor_input(plan, invocation, group_identity, namespace_identity):
    n = names(plan)
    return {"schema": 1, "scope": SCOPE, "mode": plan["mode"], "nonce": plan["nonce"],
            "network_namespace": {"name": n["namespace"], "identity": namespace_identity},
            "evidence": n["evidence"], "once_claim": n["evidence"] + "/once.claim.json",
            "tools": {path: plan["tools"][path] for path in ("/usr/bin/ip", "/usr/bin/unshare", "/usr/bin/python3")},
            "controller": plan["sources"]["actor"], "probe": plan["sources"]["probe"],
            "unit": {"name": n["unit"], "cgroup": n["group"], "invocation": invocation,
                     "cgroup_identity": group_identity, "limits": LIMITS}}

def open_evidence(plan):
    p = Path(names(plan)["evidence"])
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    info = os.fstat(fd)
    if info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o077:
        os.close(fd); raise RuntimeError("evidence directory is not root-private")
    return fd

def gate(args, plan, actor):
    directory = open_evidence(plan)
    try:
        claim, _ = read_json_at(directory, "coordinator-claim.json")
        need(claim["nonce"] == plan["nonce"] and claim["plan_sha256"] == args.plan_sha256,
             "gate does not own this original attempt claim")
        end = time.monotonic() + 15
        while True:
            try: admission, _ = read_json_at(directory, "actor-admission.json"); break
            except FileNotFoundError:
                need(time.monotonic() < end, "finite external admission deadline")
                time.sleep(0.02)
        need(set(admission) == {"schema", "plan_sha256", "nonce", "actor_input_sha256", "original_main_pid"}
             and admission["schema"] == 1 and admission["plan_sha256"] == args.plan_sha256
             and admission["nonce"] == plan["nonce"] and admission["original_main_pid"] == os.getpid(),
             "gate admission is not the original exact unit process")
        value, digest = read_json_at(directory, "actor-input.json")
        need(digest == admission["actor_input_sha256"] and value == actor_input(plan, value["unit"]["invocation"],
             value["unit"]["cgroup_identity"], value["network_namespace"]["identity"]), "admitted actor input differs from the pinned plan")
        request = argparse.Namespace(input=names(plan)["evidence"] + "/actor-input.json", input_sha256=digest)
        actor["config"](request)  # Independently checks actual unit/cgroup/netns/tools.
        artifact_contract(plan, actor)
        invocation = os.environ.get("INVOCATION_ID")
        need(invocation == value["unit"]["invocation"] and hex_value(invocation, 32), "gate actual invocation differs")
        interpreter = actor["current_interpreter"](plan["tools"]["/usr/bin/python3"])
        os.close(directory); directory = None
        os.execve("/proc/self/fd/" + str(interpreter),
                  ["/usr/bin/python3", "-I", plan["sources"]["actor"]["path"], "--execute", "--input", request.input,
                   "--input-sha256", digest], dict(ENV, INVOCATION_ID=invocation))
    finally:
        if directory is not None: os.close(directory)

def bind_unit(current, plan, invocation=None, retired_group_proven=False):
    n = names(plan)
    need(current.get("LoadState") == "loaded" and current.get("Transient") == "yes"
         and current.get("Description") == n["description"]
         and (current.get("ControlGroup") == n["group"] or (retired_group_proven and current.get("ControlGroup") == ""))
         and hex_value(current.get("InvocationID"), 32), "unit is not the exact owned transient invocation")
    if invocation is not None: need(current["InvocationID"] == invocation, "owned unit invocation changed")

def empty_original_group(actor, fd, path, identity):
    current = None
    try: current = os.stat(path, follow_symlinks=False)
    except FileNotFoundError: pass
    held = os.fstat(fd)
    need((held.st_dev, held.st_ino) == tuple(identity), "original held cgroup changed")
    if current is not None:
        need((current.st_dev, current.st_ino) == tuple(identity), "cgroup path was replaced")
    try: events = actor["bounded"](fd, "cgroup.events").decode()
    except FileNotFoundError:
        need(current is None, "counter vanished while group path exists")
        try: actor["bounded"](fd, "cgroup.procs")
        except FileNotFoundError: return {"empty": True, "removed": True, "identity": identity,
                                        "proof": "path absent and both original cgroupfs counters deactivated"}
        raise RuntimeError("only one original cgroup counter disappeared")
    fields = counters(events)
    need(fields.get("populated") == "0" and actor["bounded"](fd, "pids.current").strip() == b"0"
         and not actor["bounded"](fd, "cgroup.procs").strip(), "original hierarchy is still populated")
    return {"empty": True, "removed": False, "identity": identity, "proof": "original hierarchical population and pids.current are zero"}

def qualify(result, value, terminal, original_pid):
    need(result.get("success") is True and result.get("scope") == SCOPE and result.get("mode") == value["mode"]
         and result.get("nonce") == value["nonce"] and result.get("Android_operations") == 0
         and result.get("actual_Rust_Owner_executed") is False and result.get("declared_prefix_standin") is True,
         "actor result is not this successful declared host-prefix stand-in")
    need("error" not in result and "cleanup_error" not in result, "actor retains an execution or cleanup failure")
    unit = value["unit"]
    need(terminal.get("InvocationID") == unit["invocation"] and terminal.get("ExecMainPID") == str(original_pid)
         and terminal.get("MainPID") == "0" and terminal.get("Result") == "success"
         and terminal.get("ExecMainCode") == "1" and terminal.get("ExecMainStatus") == "0",
         "terminal is not this original successful main process")
    start = int(terminal["ExecMainStartTimestampMonotonic"]); end = int(terminal["ExecMainExitTimestampMonotonic"])
    need(0 < start < end and end - start < 60_000_000, "terminal monotonic lifetime outside bounded unit")
    need(0 < int(terminal["MemoryPeak"]) < int(LIMITS["memory.max"]) and terminal["MemorySwapPeak"] == "0",
         "terminal memory/swap envelope differs")
    final = result["outer_final"]
    need(final["nonce"] == value["nonce"] and final["actor_pid"] == original_pid and final["unit"] == unit
         and final.get("sole_remaining_actor") is True and final.get("sampled_before_unit_exit") is True,
         "outer final audit is not bound to the first held unit identity")
    values = final["counters"]
    need(all(values.get(k) == v for k, v in LIMITS.items()) and values["pids.current"] == "1"
         and values["cgroup.procs"].split() == [str(original_pid)], "outer-final budget/descendant census differs")
    events = counters(values["memory.events"])
    need(all(events.get(key) == "0" for key in ("max", "oom", "oom_kill")) and values["memory.swap.current"] == "0"
         and 0 < int(values["memory.peak"]) <= int(terminal["MemoryPeak"]), "outer-final pressure/swap envelope differs")
    p = result["actual_prefix"]
    need(p["nonce"] == value["nonce"] and p["scope"] == SCOPE
         and p.get("inherited_owner_pidfd_matches_exact_child") is True
         and p["private_pid1"]["parent"] == p["owner"]["pid"]
         and p["owner"]["parent"] == p["controller_pid"] and p["private_pid1"]["nspid"][-1] == 1
         and p["namespace_identity"]["net"] == value["network_namespace"]["identity"], "actual prefix ownership report differs")
    expected_argv = ["/usr/bin/ip", "netns", "exec", value["network_namespace"]["name"], "/usr/bin/unshare",
                     "--mount", "--pid", "--mount-proc", "--ipc", "--uts", "--fork", "--kill-child=TERM",
                     "--propagation=private", "/proc/self/fd/201", "development-enter", "--spec",
                     value["evidence"] + "/actor-input.json"]
    need(p["prefix"] == expected_argv, "actual complete prefix argv differs")
    proof = result["terminal"]
    if value["mode"] == "normal":
        need(proof.get("normal_exit") is True and proof.get("next_exec_no_fixed_FDs") is True, "normal exec/closure contract absent")
    else:
        need(proof.get("probe_control_held_open") is True and proof.get("native_deadline_not_used") is True
             and 0 <= proof["elapsed_from_probe_start_ms"] < 10000 and p["probe_lifetime_ms"] == 15000,
             "death may be explained by HUP or native timeout")
        required = ("exact_owner_killed", "private_pid1_dead") if value["mode"] == "owner-kill" else (
                    "exact_controller_killed", "exact_owner_dead", "exact_private_pid1_dead")
        need(all(proof.get(k) is True for k in required), "exact death chain absent")
    return {"first_cgroup_identity": unit["cgroup_identity"], "invocation": unit["invocation"],
            "original_main_pid": original_pid, "actor_outer_final_and_terminal_bound": True,
            "full_prefix_contract_observed": True, "Android_operations": 0, "actual_Rust_Owner_executed": False}

class Attempt:
    def __init__(self, args, plan, actor):
        self.args, self.plan, self.actor = args, plan, actor
        self.n = names(plan); self.directory = self.nsfd = self.groupfd = self.mainfd = None
        self.invocation = self.group_identity = self.main_pid = None
        self.unit_attempted = self.unit_stop_attempted = self.namespace_attempted = self.namespace_created = False
        self.result = {"schema": 1, "scope": SCOPE, "nonce": plan["nonce"], "mode": plan["mode"],
                       "plan_sha256": args.plan_sha256, "sources": plan["sources"], "tools": plan["tools"],
                       "Android_operations": 0, "Main_actions": 0, "production_ready": False,
                       "whole_attempt_qualified": False, "automatic_retry": False}

    def observe_unit(self):
        current = props(self.n["unit"])
        bind_unit(current, self.plan, self.invocation)
        if self.invocation is None: self.invocation = current["InvocationID"]
        if self.groupfd is None:
            self.groupfd = os.open("/sys/fs/cgroup" + self.n["group"], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
            self.actor["require_cgroup2"](self.groupfd)
            info = os.fstat(self.groupfd); self.group_identity = [info.st_dev, info.st_ino]
        if self.mainfd is None and int(current.get("MainPID", "0")) > 0:
            self.main_pid = int(current["MainPID"])
            self.mainfd = os.pidfd_open(self.main_pid)
            identity, proc = self.actor["identity"](self.mainfd)
            try:
                expected = ["/usr/bin/python3", "-I", self.plan["sources"]["coordinator"]["path"], "--gate",
                            "--plan", self.args.plan, "--plan-sha256", self.args.plan_sha256]
                need(identity["pid"] == self.main_pid and identity["cmdline"] == expected
                     and identity["cgroup"] == ["0::" + self.n["group"]], "initial gate process differs")
            finally: os.close(proc)
        return current

    def bind_current(self, current):
        retired = False
        if current.get("ControlGroup") == "":
            need(self.groupfd is not None and self.mainfd is not None and self.actor["dead"](self.mainfd),
                 "empty systemd group name has no original dead-process authority")
            retired = empty_original_group(self.actor, self.groupfd, "/sys/fs/cgroup" + self.n["group"], self.group_identity)["removed"]
            need(retired, "systemd forgot a group which has not been independently removed")
        bind_unit(current, self.plan, self.invocation, retired)

    def start(self):
        need(props(self.n["unit"]).get("LoadState") == "not-found", "unit was not fresh before creation")
        need(not os.path.lexists("/sys/fs/cgroup" + self.n["group"])
             and not os.path.lexists("/run/netns/" + self.n["namespace"])
             and not os.path.lexists("/etc/netns/" + self.n["namespace"]), "owned group/netns/config already exists")
        netns_parent = os.stat("/run/netns", follow_symlinks=False)
        need(stat.S_ISDIR(netns_parent.st_mode) and netns_parent.st_uid == 0 and netns_parent.st_mode & 0o022 == 0,
             "existing host namespace registry is not root-protected")
        base = os.open(BASE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(base)
            need(info.st_uid == info.st_gid == 0 and info.st_mode & 0o077 == 0, "root-private prefix base must be provisioned first")
            os.mkdir(self.n["leaf"], 0o700, dir_fd=base)
            self.directory = os.open(self.n["leaf"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=base)
            os.fsync(base)
        finally: os.close(base)
        atomic_json(self.directory, "coordinator-claim.json", {"schema": 1, "nonce": self.plan["nonce"],
                    "plan_sha256": self.args.plan_sha256, "unit": self.n["unit"], "namespace": self.n["namespace"],
                    "state": "PERMANENT_ONCE_CLAIM_NO_AUTOMATIC_RETRY"})
        self.namespace_attempted = True
        call(["/usr/bin/ip", "netns", "add", self.n["namespace"]])
        self.namespace_created = True
        self.nsfd = os.open("/run/netns/" + self.n["namespace"], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        import fcntl
        need(fcntl.ioctl(self.nsfd, 0xb703) == 0x40000000, "new namespace is not a network namespace")
        ns = os.fstat(self.nsfd); ns_identity = [ns.st_dev, ns.st_ino]
        self.result["original_namespace_identity"] = ns_identity
        atomic_json(self.directory, "namespace-created.json", {"schema": 1, "nonce": self.plan["nonce"],
                    "plan_sha256": self.args.plan_sha256, "name": self.n["namespace"], "identity": ns_identity,
                    "no_routes_veth_or_address_changes": True})
        command = ["/usr/bin/systemd-run", "--unit=" + self.n["unit"], "--property=Type=exec",
                   "--property=Description=" + self.n["description"], "--property=Restart=no", "--property=RemainAfterExit=yes",
                   "--property=RuntimeMaxSec=60", "--property=TimeoutStopSec=8", "--property=KillMode=control-group",
                   "--property=OOMPolicy=stop", "--property=CPUQuota=100%", "--property=CPUQuotaPeriodSec=100ms",
                   "--property=MemoryMax=256M", "--property=MemorySwapMax=0", "--property=TasksMax=32",
                   "--property=Nice=10", "--property=UMask=0077", "--setenv=PATH=/usr/bin:/bin", "--setenv=LANG=C",
                   "--", "/usr/bin/python3", "-I", self.plan["sources"]["coordinator"]["path"], "--gate",
                   "--plan", self.args.plan, "--plan-sha256", self.args.plan_sha256]
        self.result["unit_launch_argv"] = command
        self.unit_attempted = True  # Owner exists before the fallible dispatch observation.
        launch_error = None
        try: call(command, timeout=5)
        except BaseException as error:
            launch_error = repr(error); self.result["launch_observation_error"] = launch_error
        current = self.observe_unit()  # Same unit/name/nonce; never re-dispatch.
        need(self.mainfd is not None and not self.actor["dead"](self.mainfd), "original gate was not captured alive")
        atomic_json(self.directory, "unit-first-observation.json", {"schema": 1, "nonce": self.plan["nonce"],
                    "plan_sha256": self.args.plan_sha256, "properties": current,
                    "cgroup_identity": self.group_identity, "original_main_pid": self.main_pid,
                    "namespace_identity": ns_identity})
        need(launch_error is None, "ambiguous launch reconciled for retirement only; execution remains failed")
        for key, expected in LIMITS.items():
            need(self.actor["bounded"](self.groupfd, key, 128).decode().strip() == expected, "new immutable unit budget differs")
        value = actor_input(self.plan, self.invocation, self.group_identity, ns_identity)
        digest = atomic_json(self.directory, "actor-input.json", value)
        self.result["first_unit"] = {"properties": current, "cgroup_identity": self.group_identity, "main_pid": self.main_pid}
        self.result["actor_input"] = {"value": value, "sha256": digest}
        atomic_json(self.directory, "actor-admission.json", {"schema": 1, "nonce": self.plan["nonce"],
                    "plan_sha256": self.args.plan_sha256, "actor_input_sha256": digest, "original_main_pid": self.main_pid})
        end = time.monotonic() + 35
        while not self.actor["dead"](self.mainfd):
            need(time.monotonic() < end, "finite actor terminal deadline")
            time.sleep(0.1)
        terminal = props(self.n["unit"])
        self.bind_current(terminal)
        self.result["actual_terminal"] = terminal
        actual, actual_digest = read_json_at(self.directory, "prefix-result.json")
        self.result["actor_result_sha256"] = actual_digest
        self.result["qualification"] = qualify(actual, value, terminal, self.main_pid)

    def cleanup(self):
        errors = []; retired = {}
        if self.unit_attempted:
            try:
                current = props(self.n["unit"])
                if self.invocation is None:
                    self.observe_unit(); current = props(self.n["unit"])
                stop_error = None
                if current.get("LoadState") != "not-found":
                    self.bind_current(current)
                    need(not self.unit_stop_attempted, "stop was already dispatched")
                    self.unit_stop_attempted = True
                    try: call(["/usr/bin/systemctl", "stop", self.n["unit"]], timeout=10)
                    except BaseException as error: stop_error = repr(error)
                else:
                    need(self.mainfd is not None and self.groupfd is not None,
                         "disappeared unit has no retained original process/group authority")
                if self.mainfd is not None: self.actor["await_dead"](self.mainfd)
                need(self.groupfd is not None, "original unit cgroup was never retained")
                proof = empty_original_group(self.actor, self.groupfd, "/sys/fs/cgroup" + self.n["group"], self.group_identity)
                current = props(self.n["unit"])
                if current.get("LoadState") != "not-found":
                    # A failed unit may remain loaded. Only the same captured
                    # invocation may have its failed state reset after empty.
                    self.bind_current(current)
                    need(current.get("MainPID") == "0" and current.get("ActiveState") in ("inactive", "failed"),
                         "unit did not stop")
                    if current.get("ActiveState") == "failed":
                        call(["/usr/bin/systemctl", "reset-failed", self.n["unit"]], allowed=(0, 1))
                end = time.monotonic() + 4
                while props(self.n["unit"]).get("LoadState") != "not-found":
                    need(time.monotonic() < end, "retired transient unit was not unloaded")
                    time.sleep(0.1)
                proof = empty_original_group(self.actor, self.groupfd, "/sys/fs/cgroup" + self.n["group"], self.group_identity)
                need(proof["removed"], "original unit cgroup not removed")
                retired["unit"] = {"name": self.n["unit"], "invocation": self.invocation,
                                   "original_pidfd_dead": self.mainfd is not None and self.actor["dead"](self.mainfd),
                                   "cgroup": proof, "final_load_state": "not-found", "stop_observation_error": stop_error}
                need(stop_error is None, "stop observation was ambiguous despite independently proven retirement")
            except BaseException as error: errors.append({"unit": repr(error), "traceback": traceback.format_exc()})
        if self.namespace_attempted and not self.namespace_created:
            try:
                need(not os.path.lexists("/run/netns/" + self.n["namespace"]),
                     "namespace creation outcome unknown; unbound residue is retained and blocks replay")
                retired["namespace"] = {"name": self.n["namespace"], "name_absent_after_failed_creation": True,
                                        "delete_not_attempted": True}
            except BaseException as error: errors.append({"namespace": repr(error), "traceback": traceback.format_exc()})
        if self.namespace_created:
            try:
                need(not self.unit_attempted or "unit" in retired, "cannot retire namespace before exact unit retirement")
                need(self.nsfd is not None, "created namespace identity was never retained")
                original = os.fstat(self.nsfd)
                path = "/run/netns/" + self.n["namespace"]
                current = os.stat(path, follow_symlinks=False)
                need((current.st_dev, current.st_ino) == (original.st_dev, original.st_ino), "namespace mountpoint was replaced")
                members = call(["/usr/bin/ip", "netns", "pids", self.n["namespace"]]).stdout.strip()
                need(not members, "original namespace still has live process members")
                call(["/usr/bin/ip", "netns", "delete", self.n["namespace"]])
                need(not os.path.lexists(path), "original namespace name remains")
                retired["namespace"] = {"name": self.n["namespace"], "identity": [original.st_dev, original.st_ino],
                                        "no_live_members_before_delete": True, "name_removed": True}
            except BaseException as error: errors.append({"namespace": repr(error), "traceback": traceback.format_exc()})
        self.result["retirement"] = retired; self.result["cleanup_errors"] = errors
        self.result["exact_cleanup_complete"] = (not errors and (not self.unit_attempted or "unit" in retired)
                                                  and (not self.namespace_attempted or "namespace" in retired))
        return not errors

    def close(self):
        for name in ("directory", "nsfd", "groupfd", "mainfd"):
            fd = getattr(self, name)
            if fd is not None: os.close(fd); setattr(self, name, None)

def execute(args, plan, actor):
    attempt = Attempt(args, plan, actor); fence = None
    try:
        fence = MainFence(plan, actor)
        attempt.result["main_before"] = fence.check()
        attempt.result["source_before"] = artifact_contract(plan, actor)
        attempt.start()
    except BaseException as error:
        attempt.result["primary_error"] = repr(error)
        attempt.result["traceback"] = traceback.format_exc()
    finally:
        # Each independent audit is attempted even if another audit or output
        # publication fails. Resource retirement precedes final receipt I/O.
        try: attempt.cleanup()
        except BaseException as error:
            attempt.result["exact_cleanup_complete"] = False
            attempt.result["cleanup_internal_error"] = repr(error)
            attempt.result["cleanup_internal_traceback"] = traceback.format_exc()
        try:
            need(fence is not None, "Main fence was not acquired")
            attempt.result["main_after"] = fence.check()
            need(attempt.result["main_after"] == attempt.result["main_before"], "Main original fence changed")
        except BaseException as error: attempt.result["main_fence_error"] = repr(error)
        try: attempt.result["source_after"] = artifact_contract(plan, actor)
        except BaseException as error: attempt.result["source_after_error"] = repr(error)
        attempt.result["whole_attempt_qualified"] = ("qualification" in attempt.result and
            attempt.result.get("exact_cleanup_complete") is True and not any(key in attempt.result for key in
            ("primary_error", "main_fence_error", "source_after_error", "cleanup_internal_error")))
        if fence is not None: fence.close()
        try:
            need(attempt.directory is not None, "no owned evidence directory acquired; no receipt can be published")
            digest = atomic_json(attempt.directory, "coordinator-result.json", attempt.result)
            print(json.dumps({"whole_attempt_qualified": attempt.result["whole_attempt_qualified"],
                              "result": names(plan)["evidence"] + "/coordinator-result.json", "sha256": digest,
                              "Android_operations": 0, "production_ready": False}), flush=True)
        finally: attempt.close()
    return 0 if attempt.result["whole_attempt_qualified"] else 1

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True); parser.add_argument("--plan-sha256", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true"); action.add_argument("--execute", action="store_true")
    action.add_argument("--gate", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(); plan, actor = load_plan(args)
    if args.gate: return gate(args, plan, actor)
    if args.check:
        fence = MainFence(plan, actor)
        try:
            artifact_contract(plan, actor)
            need(props(names(plan)["unit"]).get("LoadState") == "not-found", "unit is not fresh")
            need(not os.path.lexists(names(plan)["evidence"]) and not os.path.lexists("/run/netns/" + names(plan)["namespace"])
                 and not os.path.lexists("/sys/fs/cgroup" + names(plan)["group"]), "owned paths are not fresh")
            print(json.dumps({"read_only_plan_checked": True, "nonce": plan["nonce"], "Main": fence.check(),
                              "runtime_started": False, "Android_operations": 0}))
        finally: fence.close()
        return 0
    return execute(args, plan, actor)

if __name__ == "__main__":
    raise SystemExit(main())
