#!/usr/bin/env python3
"""Owned host-prefix contract. Caller must provision one fresh bounded unit/netns.

No Android images, init, service, network route, veth, cgroup setting, or Main
operation is performed here. --check only reads. --execute is one-shot and must
be separately admitted after source review. The native ELF is a declared probe,
not Android init. The prefix and FD layout mirror the reviewed producer source;
this controller does not claim to execute Rust Owner::configure_command itself.
"""
import argparse
import array
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
FIXED = (198, 199, 200, 201)
PARENT_CHANNEL = 197
SCM_PIDFD = getattr(socket, "SCM_PIDFD", 0x04)  # Linux bits/socket.h ABI.
NAMES = ("pid", "pid_for_children", "mnt", "cgroup", "user", "net", "ipc", "uts", "time", "time_for_children")
TYPES = (0x20000000, 0x20000000, 0x00020000, 0x02000000, 0x10000000,
         0x40000000, 0x08000000, 0x04000000, 0x80, 0x80)
ROOT = Path("/sys/fs/cgroup")

def need(value, message):
    if not value:
        raise RuntimeError(message)

def stamp(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_nlink)

def require_cgroup2(fd):
    need(os.uname().machine == "x86_64", "prefix control filesystem ABI is qualified only for x86_64")
    libc = ctypes.CDLL(None, use_errno=True)
    buffer = ctypes.create_string_buffer(512)
    libc.fstatfs.argtypes = (ctypes.c_int, ctypes.c_void_p)
    libc.fstatfs.restype = ctypes.c_int
    need(libc.fstatfs(fd, buffer) == 0 and ctypes.c_long.from_buffer(buffer).value == 0x63677270,
         "unit directory is not cgroup2")

def bounded(fd, name, limit=16384):
    current = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
    try:
        result = bytearray()
        while True:
            part = os.read(current, min(8192, limit + 1 - len(result)))
            if not part:
                break
            result.extend(part)
            need(len(result) <= limit, "bounded read exceeded: " + name)
        return bytes(result)
    finally:
        os.close(current)

def verify_fd(fd, digest, executable=False):
    need(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "invalid artifact digest")
    before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
         and before.st_mode & 0o6022 == 0 and 0 < before.st_size <= 128 * 1024 * 1024,
         "artifact ownership/type/size/privilege differs")
    if executable:
        need(before.st_mode & 0o111, "artifact is not executable")
        try:
            value = os.getxattr(fd, "security.capability")
        except OSError as error:
            need(error.errno in (errno.ENODATA, errno.ENOTSUP), "file capability inspection failed")
        else:
            need(not value, "privileged file capability can clear parent-death")
    h = hashlib.sha256()
    offset = 0
    while True:
        part = os.pread(fd, 65536, offset)
        if not part:
            break
        h.update(part)
        offset += len(part)
        need(offset <= 128 * 1024 * 1024, "artifact grew beyond limit")
    need(h.hexdigest() == digest and stamp(os.fstat(fd)) == stamp(before), "artifact content changed")
    return before

def pinned(path, digest, executable=False):
    path = Path(path)
    need(path.is_absolute() and ".." not in path.parts, "invalid artifact authority path")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        verify_fd(fd, digest, executable)
        return fd
    except BaseException:
        os.close(fd)
        raise

def current_interpreter(digest):
    # /usr/bin/python3 may be a packaging symlink. The current process's
    # kernel-owned exe link pins the actual interpreter rather than guessing
    # a versioned pathname or treating a symlink as a regular artifact.
    fd = os.open("/proc/self/exe", os.O_RDONLY | os.O_CLOEXEC)
    try:
        verify_fd(fd, digest, True)
        return fd
    except BaseException:
        os.close(fd)
        raise

def dead(fd):
    poller = select.poll()
    poller.register(fd, select.POLLIN)
    result = poller.poll(0)
    need(not any(flags & (select.POLLERR | select.POLLNVAL) for _, flags in result), "pidfd poll fault")
    return bool(result)

def await_dead(fd, seconds=4):
    end = time.monotonic() + seconds
    while not dead(fd):
        need(time.monotonic() < end, "original pidfd remains alive")
        time.sleep(0.01)

def pidfd_pid(fd):
    data = Path(f"/proc/self/fdinfo/{fd}").read_text()
    fields = [line.split(":", 1)[1].strip() for line in data.splitlines() if line.startswith("Pid:")]
    need(len(fields) == 1 and fields[0].isdigit() and int(fields[0]) > 0, "pidfd has no live host PID")
    return int(fields[0])

def identity(fd):
    need(not dead(fd), "process dead before identity")
    pid = pidfd_pid(fd)
    proc = os.open(f"/proc/{pid}", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        first = bounded(proc, "stat").decode().rsplit(")", 1)[1].split()[19]
        fields = dict(line.split(":", 1) for line in bounded(proc, "status").decode().splitlines() if ":" in line)
        value = {"pid": pid, "birth": int(first), "parent": int(fields["PPid"]),
                 "uids": [int(x) for x in fields["Uid"].split()],
                 "gids": [int(x) for x in fields["Gid"].split()],
                 "nspid": [int(x) for x in fields["NSpid"].split()],
                 "cmdline": bounded(proc, "cmdline").decode().split("\0")[:-1],
                 "cgroup": bounded(proc, "cgroup").decode().splitlines()}
        second = bounded(proc, "stat").decode().rsplit(")", 1)[1].split()[19]
        need(first == second and not dead(fd) and pidfd_pid(fd) == pid, "process identity changed")
        return value, proc
    except BaseException:
        os.close(proc)
        raise

def seqpair():
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
    a.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
    b.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
    return a, b

def send(channel, payload, fds=()):
    rights = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))] if fds else []
    need(channel.sendmsg([payload], rights, socket.MSG_NOSIGNAL) == len(payload), "short seqpacket send")

def receive(channel, maximum, count, peer_pid=None, timeout=5):
    end = time.monotonic() + timeout
    while True:
        wait = end - time.monotonic()
        need(wait > 0, "finite packet deadline")
        if select.select([channel], [], [], min(wait, 0.1))[0]:
            break
    data, ancillary, flags, _ = channel.recvmsg(maximum, socket.CMSG_SPACE(16 * 4) + socket.CMSG_SPACE(12)
                                             + socket.CMSG_SPACE(4), socket.MSG_CMSG_CLOEXEC)
    owned = []
    try:
        credentials = []
        errors = []
        for level, kind, value in ancillary:
            if level == socket.SOL_SOCKET and kind in (socket.SCM_RIGHTS, SCM_PIDFD):
                rights = array.array("i")
                rights.frombytes(value[:len(value) - len(value) % 4])
                owned.extend(rights)
                if len(value) % 4:
                    errors.append("malformed rights length")
                if kind == SCM_PIDFD:
                    # This protocol never enables SO_PASSPIDFD. If the kernel
                    # nevertheless delivers one, own and close it on reject;
                    # unknown ancillary handling must not leak capabilities.
                    errors.append("unexpected SCM_PIDFD capability")
            elif level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
                if len(value) != 12:
                    errors.append("malformed kernel credentials")
                else:
                    credentials.append(struct.unpack("3i", value))
            else:
                errors.append("unexpected ancillary control")
        # Every delivered SCM_RIGHTS descriptor is owned before any rejection,
        # including malformed credentials or a preceding unknown cmsg.
        need(not errors, "; ".join(errors))
        need(data and not flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC), "EOF/truncated packet")
        need(len(owned) == count and len(credentials) == 1, "rights/credentials count differs")
        peer, uid, gid = credentials[0]
        need(uid == gid == 0 and peer > 0 and (peer_pid is None or peer == peer_pid), "exact root peer differs")
        need(all(fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC for fd in owned), "received capability not CLOEXEC")
        return data, owned, peer
    except BaseException:
        for fd in owned:
            os.close(fd)
        raise

def safe_stop(child, fd):
    if child is None:
        return
    if child.poll() is None:
        if fd is not None and not dead(fd):
            signal.pidfd_send_signal(fd, signal.SIGTERM)
        else:
            child.terminate()  # Exact retained unreaped subprocess.Child only.
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            if fd is not None and not dead(fd):
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            else:
                child.kill()
            child.wait(timeout=3)
    if fd is not None:
        await_dead(fd)

def config(args):
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, "root owned caller required")
    self_pidfd = os.pidfd_open(os.getpid())
    try:
        need(pidfd_pid(self_pidfd) == os.getpid(), "host PID namespace and procfs view required")
    finally:
        os.close(self_pidfd)
    fd = pinned(args.input, args.input_sha256)
    try:
        raw = os.read(fd, 32769)
        need(len(raw) <= 32768, "input too large")
        value = json.loads(raw)
    finally:
        os.close(fd)
    need(set(value) == {"schema", "scope", "mode", "nonce", "network_namespace", "evidence", "once_claim",
                        "tools", "controller", "probe", "unit"}, "unknown/missing input fields")
    need(value["schema"] == 1 and value["scope"] == "OWNED_HOST_PREFIX_ONLY_NO_ANDROID"
         and value["mode"] in ("normal", "owner-kill", "controller-loss"), "wrong prefix contract scope")
    name, nonce = value["network_namespace"]["name"], value["nonce"]
    need(len(nonce) == 64 and set(nonce) <= set("0123456789abcdef") and set(nonce) != {"0"}, "nonce format")
    need(name == "p4-relay-prefix-" + nonce[:24], "namespace name is not nonce-bound")
    need(value["once_claim"] == str(Path(value["evidence"]) / "once.claim.json")
         and Path(value["evidence"]).is_absolute(), "claim/evidence binding")
    evidence = Path(value["evidence"])
    need(evidence.name == "p4-relay-prefix-" + nonce[:24] + "-" + value["mode"]
         and evidence.parent == Path("/home/alex/work/pocket4-relay-prefix-r11-owned"),
         "evidence is not a fresh exact owned prefix path")
    info = evidence.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0 and info.st_mode & 0o077 == 0,
         "evidence parent is not root-private")
    need(set(value["tools"]) == {"/usr/bin/ip", "/usr/bin/unshare", "/usr/bin/python3"}, "complete tool pins required")
    for path, digest in value["tools"].items():
        os.close(current_interpreter(digest) if path == "/usr/bin/python3" else pinned(path, digest, True))
    need(Path(value["controller"]["path"]).resolve() == Path(__file__).resolve(), "controller path differs")
    os.close(pinned(value["controller"]["path"], value["controller"]["sha256"]))
    os.close(pinned(value["probe"]["path"], value["probe"]["sha256"], True))
    group = value["unit"]["cgroup"]
    expected_unit = "p4-relay-prefix-" + nonce[:24] + "-" + value["mode"] + ".service"
    need(group == "/system.slice/" + expected_unit and value["unit"]["name"] == expected_unit,
         "unit is not an exact owned prefix scope")
    need(value["unit"]["invocation"] and os.environ.get("INVOCATION_ID") == value["unit"]["invocation"],
         "actual service invocation differs")
    need(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + group], "actor cgroup differs")
    parent = os.open(ROOT / group[1:], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        require_cgroup2(parent)
        observed = os.fstat(parent)
        need([observed.st_dev, observed.st_ino] == value["unit"]["cgroup_identity"], "first cgroup identity differs")
        for key, expected in value["unit"]["limits"].items():
            need(bounded(parent, key, 128).decode().strip() == expected, "unit budget changed: " + key)
        limits = value["unit"]["limits"]
        need(set(limits) == {"memory.max", "memory.swap.max", "cpu.max", "pids.max"}
             and 0 < int(limits["memory.max"]) <= 256 * 1024 * 1024 and limits["memory.swap.max"] == "0"
             and 2 <= int(limits["pids.max"]) <= 32, "prefix budget exceeds finite bound")
        cpu = limits["cpu.max"].split()
        need(len(cpu) == 2 and all(x.isdigit() for x in cpu) and 1000 <= int(cpu[0]) <= int(cpu[1]) <= 1000000,
             "prefix CPU budget is not bounded to one CPU")
    finally:
        os.close(parent)
    nsfd = os.open("/run/netns/" + name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        observed = os.fstat(nsfd)
        need([observed.st_dev, observed.st_ino] == value["network_namespace"]["identity"]
             and fcntl.ioctl(nsfd, 0xb703) == 0x40000000, "original owned network namespace changed")
    finally:
        os.close(nsfd)
    return value

def child_controller(args, c):
    # The outer controller retains this exact Child. No services are launched.
    parent = socket.socket(fileno=PARENT_CHANNEL)
    parent.setblocking(False)
    os.set_inheritable(PARENT_CHANNEL, False)
    creator, uid, gid = struct.unpack("3i", parent.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    need(creator == os.getppid() and uid == gid == 0, "controller channel is not the exact parent")
    a, b = seqpair()
    child = None
    ownerfd = None
    received = []
    handles = []
    try:
        directory = os.open(c["evidence"], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        probe = pinned(c["probe"]["path"], c["probe"]["sha256"], True)
        placeholder = os.pidfd_open(os.getpid())
        handles.extend((directory, probe, placeholder))
        for target in FIXED:
            try:
                os.fstat(target)
            except OSError as error:
                need(error.errno == errno.EBADF, "fixed slot inspection failed")
            else:
                raise RuntimeError("fixed slot was already owned")
        for source, target in zip((b.fileno(), directory, placeholder, probe), FIXED):
            os.dup2(source, target, inheritable=True)
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong)
        libc.prctl.restype = ctypes.c_int
        controller = os.getpid()
        need(len(list(Path("/proc/self/task").iterdir())) == 1, "preexec controller is multithreaded")
        def before_exec():
            if libc.prctl(1, signal.SIGKILL, 0, 0, 0) or os.getppid() != controller:
                raise RuntimeError("lifecycle parent died before exec")
            actual = os.pidfd_open(os.getpid())
            try:
                os.dup2(actual, 200, inheritable=True)
            finally:
                if actual != 200:
                    os.close(actual)
        argv = ["/usr/bin/ip", "netns", "exec", c["network_namespace"]["name"], "/usr/bin/unshare",
                "--mount", "--pid", "--mount-proc", "--ipc", "--uts", "--fork", "--kill-child=TERM",
                "--propagation=private", "/proc/self/fd/201", "development-enter", "--spec", args.input]
        env = {"PATH": "/usr/bin:/bin", "LANG": "C", "DROIDLOOM_RELAY_ENTRY_ABI": "droidloom-relay-entry-v1",
               "DROIDLOOM_RELAY_ENTRY_NONCE": c["nonce"], "DROIDLOOM_RELAY_ENTRY_SPEC_SHA256": args.input_sha256}
        try:
            child = subprocess.Popen(argv, env=env, pass_fds=FIXED, preexec_fn=before_exec)
        finally:
            for target in FIXED:
                os.close(target)
        b.close()
        ownerfd = os.pidfd_open(child.pid)
        raw, received, sender = receive(a, 128, 12)
        need(len(raw) == 128 and raw[:8] == b"P4PX01!!" and struct.unpack_from("<Q", raw, 8)[0] == 1
             and raw[16:48].hex() == c["nonce"] and raw[120:] == bytes(8), "probe frame nonce/layout")
        probe_start, lifetime = struct.unpack_from("<2Q", raw, 104)
        need(lifetime == 15000 and 0 <= time.monotonic_ns() // 1000000 - probe_start < 2000,
             "probe HELLO is too old for an independent death observation")
        init, proc = identity(received[0])
        try:
            owner, owner_proc = identity(ownerfd)
            try:
                image = os.open("exe", os.O_RDONLY | os.O_CLOEXEC, dir_fd=owner_proc)
                try:
                    verify_fd(image, c["tools"]["/usr/bin/unshare"], True)
                finally:
                    os.close(image)
            finally:
                os.close(owner_proc)
            need(init["pid"] == sender and init["parent"] == owner["pid"] == child.pid
                 and init["nspid"][-1] == 1 and init["uids"] == init["gids"] == [0] * 4,
                 "actual Child to private PID1 relationship differs")
            need(owner["parent"] == os.getpid() and owner["uids"] == owner["gids"] == [0] * 4,
                 "exact Child is not the direct root-owned lifecycle child")
            inherited_owner, inherited_proc = identity(received[11])
            try:
                need(inherited_owner == owner,
                     "inherited FD 200 does not designate the retained exact Child")
            finally:
                os.close(inherited_proc)
            need(owner["cgroup"] == init["cgroup"] == ["0::" + c["unit"]["cgroup"]],
                 "owned prefix process escaped the exact unit")
            image = os.open("exe", os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc)
            try:
                verify_fd(image, c["probe"]["sha256"], True)
            finally:
                os.close(image)
            namespace_identity = {}
            for name, kind, fd in zip(NAMES, TYPES, received[1:11]):
                actual = os.open("ns/" + name, os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc)
                try:
                    need(fcntl.ioctl(fd, 0xb703) == kind
                         and (os.fstat(fd).st_dev, os.fstat(fd).st_ino) == (os.fstat(actual).st_dev, os.fstat(actual).st_ino),
                         "held namespace rights differ: " + name)
                    namespace_identity[name] = [os.fstat(fd).st_dev, os.fstat(fd).st_ino]
                finally:
                    os.close(actual)
            network = os.fstat(received[1 + NAMES.index("net")])
            need([network.st_dev, network.st_ino] == c["network_namespace"]["identity"],
                 "ip did not enter the original owned network namespace")
            for name in ("time", "time_for_children", "user", "cgroup", "mnt", "pid", "ipc", "uts"):
                original = os.open("/proc/self/ns/" + name, os.O_RDONLY | os.O_CLOEXEC)
                try:
                    supplied = os.fstat(received[1 + NAMES.index(name)])
                    current = os.fstat(original)
                    same = (supplied.st_dev, supplied.st_ino) == (current.st_dev, current.st_ino)
                    need(same == (name in ("time", "time_for_children", "user", "cgroup")),
                         "prefix namespace creation/preservation differs: " + name)
                finally:
                    os.close(original)
            need(namespace_identity["pid"] == namespace_identity["pid_for_children"],
                 "private PID1 children would enter a different PID namespace")
            ds, ps = os.fstat(directory), os.fstat(probe)
            values = struct.unpack_from("<7Q", raw, 48)
            need(values == (ds.st_dev, ds.st_ino, ps.st_dev, ps.st_ino, signal.SIGKILL, 1, 0), "fixed-FD object/death report differs")
        finally:
            os.close(proc)
        report = {"nonce": c["nonce"], "scope": c["scope"], "prefix": argv, "controller_pid": os.getpid(),
                  "owner": owner, "private_pid1": init, "fixed_FD_observation": list(values),
                  "inherited_owner_pidfd_matches_exact_child": True,
                  "namespace_identity": namespace_identity,
                  "probe_start_monotonic_ms": probe_start, "probe_lifetime_ms": lifetime}
        ownfd = os.pidfd_open(os.getpid())
        try:
            # The outer observer keeps this actual control endpoint alive
            # across controller loss. HUP must not masquerade as PDEATHSIG.
            send(parent, json.dumps(report, separators=(",", ":")).encode(), (ownfd, ownerfd, received[0], a.fileno()))
        finally:
            os.close(ownfd)
        command, nofds, _ = receive(parent, 1, 0, creator, timeout=8)
        need(not nofds and command in (b"Q", b"K"), "parent command differs")
        if command == b"Q":
            send(a, b"E")
            check, nofds, peer = receive(a, 128, 0, sender)
            need(check == b"P4PX01!!" + struct.pack("<Q", 2) + bytes.fromhex(c["nonce"]) + bytes(80),
                 "post-exec capability closure reply differs")
            send(a, b"Q")
            need(child.wait(timeout=4) == 0, "normal unshare exit differs")
            await_dead(received[0])
            terminal = {"normal_exit": True, "next_exec_no_fixed_FDs": True}
        else:
            signal.pidfd_send_signal(ownerfd, signal.SIGKILL)
            need(child.wait(timeout=4) == -signal.SIGKILL, "owner kill terminal differs")
            await_dead(received[0])
            terminal = {"exact_owner_killed": True, "private_pid1_dead": True}
        send(parent, json.dumps({"nonce": c["nonce"], "terminal": terminal}).encode())
    finally:
        a.close(); b.close()
        try:
            safe_stop(child, ownerfd)
        finally:
            if ownerfd is not None:
                os.close(ownerfd)
            for fd in received + handles:
                os.close(fd)
            parent.close()

def outer_sample(c):
    """Sample while this sole remaining actor still keeps its unit cgroup alive."""
    fd = os.open(ROOT / c["unit"]["cgroup"][1:], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        require_cgroup2(fd)
        info = os.fstat(fd)
        need([info.st_dev, info.st_ino] == c["unit"]["cgroup_identity"], "outer cgroup replaced")
        values = {name: bounded(fd, name).decode().strip() for name in (
            "cgroup.procs", "cgroup.events", "pids.current", "memory.current", "memory.peak",
            "memory.events", "memory.swap.current", "memory.max", "memory.swap.max", "cpu.max", "pids.max")}
        for name, expected in c["unit"]["limits"].items():
            need(values[name] == expected, "outer limit changed before final sample")
        need(values["pids.current"] == "1" and values["cgroup.procs"].split() == [str(os.getpid())],
             "unknown descendant or child remains at outer final sample")
        events = dict(line.split() for line in values["memory.events"].splitlines())
        need(all(events.get(key) == "0" for key in ("max", "oom", "oom_kill")), "outer max/OOM event occurred")
        need(values["memory.swap.current"] == "0"
             and int(values["memory.peak"]) < int(values["memory.max"]), "outer memory/swap envelope violated")
        current = os.fstat(fd)
        need((info.st_dev, info.st_ino) == (current.st_dev, current.st_ino), "held outer identity changed")
        return {"nonce": c["nonce"], "actor_pid": os.getpid(), "unit": c["unit"], "counters": values,
                "sole_remaining_actor": True, "sampled_before_unit_exit": True}
    finally:
        os.close(fd)

def outer(args, c):
    claim = os.open(c["once_claim"], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(claim, "w") as stream:
        json.dump({"nonce": c["nonce"], "input_sha256": args.input_sha256, "mode": c["mode"]}, stream)
        stream.flush(); os.fsync(stream.fileno())
    directory = os.open(c["evidence"], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    a, b = seqpair()
    process = None
    childfd = None
    owned = []
    result = {"schema": 1, "scope": c["scope"], "mode": c["mode"], "nonce": c["nonce"],
              "Android_operations": 0, "production_ready": False, "success": False,
              "actual_Rust_Owner_executed": False, "declared_prefix_standin": True}
    try:
        need(not os.path.exists(f"/proc/self/fd/{PARENT_CHANNEL}") and not os.path.exists("/proc/self/fd/196"),
             "parent/interpreter channel slot exists")
        os.dup2(b.fileno(), PARENT_CHANNEL, inheritable=True)
        interpreter = current_interpreter(c["tools"]["/usr/bin/python3"])
        os.dup2(interpreter, 196, inheritable=True)
        os.close(interpreter)
        try:
            process = subprocess.Popen(["/proc/self/fd/196", "-I", __file__, "--child", "--input", args.input,
                                        "--input-sha256", args.input_sha256], pass_fds=(196, PARENT_CHANNEL))
        finally:
            os.close(PARENT_CHANNEL)
            os.close(196)
        b.close()
        childfd = os.pidfd_open(process.pid)
        raw, owned, sender = receive(a, 16384, 4, process.pid, 10)
        report = json.loads(raw)
        need(report["nonce"] == c["nonce"] and report["controller_pid"] == process.pid
             and pidfd_pid(owned[0]) == process.pid and pidfd_pid(owned[1]) == report["owner"]["pid"]
             and pidfd_pid(owned[2]) == report["private_pid1"]["pid"], "forwarded exact process rights differ")
        channel_copy = socket.socket(fileno=os.dup(owned[3]))
        try:
            need(channel_copy.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_SEQPACKET,
                 "held probe-control endpoint is not seqpacket")
        finally:
            channel_copy.close()
        need(report["probe_lifetime_ms"] == 15000
             and 0 <= time.monotonic_ns() // 1000000 - report["probe_start_monotonic_ms"] < 2000,
             "native deadline too close to distinguish death from expiry")
        result["actual_prefix"] = report
        if c["mode"] == "controller-loss":
            signal.pidfd_send_signal(childfd, signal.SIGKILL)
            need(process.wait(timeout=4) == -signal.SIGKILL, "controller death terminal differs")
            for fd in owned[:3]:
                await_dead(fd)
            result["terminal"] = {"exact_controller_killed": True, "exact_owner_dead": True,
                                  "exact_private_pid1_dead": True, "probe_control_held_open": True,
                                  "native_deadline_not_used": True}
        else:
            send(a, b"Q" if c["mode"] == "normal" else b"K")
            raw, none, _ = receive(a, 4096, 0, process.pid, 10)
            final = json.loads(raw)
            need(final["nonce"] == c["nonce"] and not none, "terminal nonce differs")
            need(process.wait(timeout=4) == 0, "controller terminal failed")
            for fd in owned[:3]:
                await_dead(fd)
            result["terminal"] = final["terminal"]
        if c["mode"] != "normal":
            elapsed = time.monotonic_ns() // 1000000 - report["probe_start_monotonic_ms"]
            need(0 <= elapsed < 10000, "death observation approached the independent 15-second native deadline")
            result["terminal"]["elapsed_from_probe_start_ms"] = elapsed
            result["terminal"]["probe_control_held_open"] = True
            result["terminal"]["native_deadline_not_used"] = True
        result["success"] = True
    except BaseException as error:
        result["error"] = repr(error)
        result["traceback"] = traceback.format_exc()
    finally:
        # FD closure causes the probe to stop; process cleanup precedes receipt IO.
        a.close(); b.close()
        try:
            safe_stop(process, childfd)
            for fd in owned[:3]:
                await_dead(fd)
            result["outer_final"] = outer_sample(c)
        except BaseException as error:
            result["success"] = False
            result["cleanup_error"] = repr(error)
        if childfd is not None:
            os.close(childfd)
        for fd in owned:
            os.close(fd)
        result["external_exact_unit_and_netns_retirement_required"] = True
        output = Path(c["evidence"]) / "prefix-result.json"
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(result, stream, indent=2); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({"prefix_contract_observed": result["success"], "result": str(output),
                      "whole_attempt_qualified": False, "Android_operations": 0}))
    return 0 if result["success"] else 1

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--input-sha256", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    need(sys.flags.optimize == 0, "optimized Python is forbidden")
    c = config(args)
    if args.check:
        print(json.dumps({"state": "READ_ONLY_CONTRACT_CHECKED", "nonce": c["nonce"], "runtime_started": False}))
        return 0
    if args.child:
        os.close(196)
        child_controller(args, c)
        return 0
    return outer(args, c)

if __name__ == "__main__":
    raise SystemExit(main())
