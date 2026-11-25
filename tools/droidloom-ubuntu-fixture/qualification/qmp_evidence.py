#!/usr/bin/env python3
"""Qualification-only QMP evidence. Does not start, continue, stop or reap a VM."""
import argparse
import array
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import select
import socket
import stat
import struct
import subprocess
import sys
import time

ROOT = Path("/var/lib/droidloom-qualification")
MAX_JSON = 2 * 1024 * 1024
MAX_PPM = 64 * 1024 * 1024
KEYS = {"tab": 15, "left": 105, "right": 106, "up": 103, "down": 108}
SANDBOX = "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny"
FOCUS = re.compile(r"^Droidloom focus trace: pid=(\d+) object=(\d+) serial=(\d+) observed_ns=(\d+) focus=(enter|leave)$")
FRAME = re.compile(r"^Droidloom frame trace: pid=(\d+) seq=(\d+) stage=presented object=(\d+) frame=(\d+) buffer=(\d+) observed_ns=(\d+) display_ns=(\d+) refresh_ns=(\d+) display_sequence=(\d+) dropped_total=(\d+)$")
KEY = re.compile(r"^Droidloom key trace: stage=wayland serial=(\d+) object=(\d+) action=(Down|Up) scan_code=(\d+) repeat=(\d+)$")

class Rejected(RuntimeError):
    pass

class NotReady(Rejected):
    """A missing live observation may be polled; identity failures may not."""
    pass

def require_observation(value, message):
    if not value:
        raise NotReady(message)

def need(value, message):
    if not value:
        raise Rejected(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def identity(s):
    return {"dev": s.st_dev, "ino": s.st_ino, "mode": s.st_mode,
            "uid": s.st_uid, "gid": s.st_gid, "nlink": s.st_nlink,
            "size": s.st_size, "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns}

def node(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink]

def canonical(path):
    p = Path(path)
    need(p.is_absolute() and str(p) == path and ".." not in p.parts, "noncanonical path")
    return p

def directory(path, private=False):
    p = canonical(str(path))
    fd = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in p.parts[1:]:
            nxt = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = nxt
            s = os.fstat(fd)
            need(s.st_uid == 0 and s.st_gid == 0 and not s.st_mode & 0o022, "unprotected directory")
        if private:
            need(stat.S_IMODE(os.fstat(fd).st_mode) == 0o700, "directory must remain 0700")
        return fd
    except BaseException:
        os.close(fd)
        raise

def read_file(path, expected=None, limit=MAX_JSON, owner=0):
    p = canonical(str(path))
    parent = directory(p.parent)
    try:
        fd = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                 and before.st_uid == owner and before.st_gid == 0 and not before.st_mode & 0o022
                 and 0 <= before.st_size <= limit, "unsafe or oversized file")
            data = bytearray()
            while len(data) <= limit:
                chunk = os.read(fd, min(1024 * 1024, limit + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            after = os.fstat(fd)
            named = os.stat(p.name, dir_fd=parent, follow_symlinks=False)
            need(len(data) <= limit and identity(before) == identity(after) == identity(named), "file changed")
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    result = {"path": str(p), "bytes": len(data), "sha256": digest(data), "identity": identity(after)}
    if expected:
        need(result["bytes"] == expected["bytes"] and result["sha256"] == expected["sha256"], "file pin changed")
    return bytes(data), result

def json_file(path, expected=None):
    raw, pin = read_file(path, expected)
    return json.loads(raw), pin

def write_new(root, name, data, mode=0o600):
    need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", name), "invalid evidence basename")
    d = directory(root, private=True)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=d)
        try:
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                need(count > 0, "short output write")
                view = view[count:]
            os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(d)
    return read_file(Path(root) / name, limit=max(MAX_JSON, len(data)))[1]

def write_json(root, name, value):
    return write_new(root, name, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())

def proc_stat(pid):
    raw = Path(f"/proc/{pid}/stat").read_text()
    cut = raw.rfind(")")
    need(cut > 0 and raw[:raw.find(" ")].isdigit(), "invalid proc stat")
    parts = raw[cut + 2:].split()
    need(len(parts) >= 20 and int(raw.split(" ", 1)[0]) == pid, "proc PID changed")
    return {"pid": pid, "ppid": int(parts[1]), "start_ticks": int(parts[19])}

def pidfd_live(fd):
    p = select.poll()
    p.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
    need(not p.poll(0), "original process ended")

def status(pid):
    values = dict(line.split(":", 1) for line in Path(f"/proc/{pid}/status").read_text().splitlines() if ":" in line)
    values = {k: v.strip() for k, v in values.items()}
    for name in ("Uid", "Gid"):
        need(values[name].split() == ["65534"] * 4, "QEMU credentials changed")
    need(values["Groups"] == "", "QEMU supplementary groups changed")
    for name in ("CapEff", "CapPrm", "CapInh", "CapAmb"):
        need(int(values[name], 16) == 0, "QEMU capability appeared")
    need(values["NoNewPrivs"] == "1" and values["Seccomp"] == "2", "QEMU sandbox changed")
    s = os.stat(f"/proc/{pid}/status")
    need(s.st_uid == s.st_gid == 0, "QEMU became dumpable")
    return {k: values[k] for k in ("Pid", "Uid", "Gid", "Groups", "CapEff", "CapPrm", "CapInh", "CapAmb", "CapBnd", "NoNewPrivs", "Seccomp")}

def unit_properties(unit):
    need(re.fullmatch(r"p4-[A-Za-z0-9_.@-]+\.(service|scope)", unit), "not an explicit qualification unit")
    command = ["/usr/bin/systemctl", "show", "--no-pager",
               "--property=Id,InvocationID,ControlGroup,ActiveState,SubState", "--", unit]
    result = subprocess.run(command, capture_output=True, timeout=3, check=True)
    need(len(result.stdout) <= 16384 and len(result.stderr) <= 16384, "oversized unit reply")
    fields = dict(line.split("=", 1) for line in result.stdout.decode().splitlines() if "=" in line)
    need(fields["Id"] == unit and fields["ActiveState"] == "active", "owner unit is not active")
    need(re.fullmatch("[0-9a-f]{32}", fields["InvocationID"]) and int(fields["InvocationID"], 16), "missing InvocationID")
    need(fields["ControlGroup"].startswith("/") and ".." not in fields["ControlGroup"].split("/"), "invalid cgroup")
    return fields

def process_snapshot(running, admitted, fixture):
    pid = running["pid"]
    need(type(pid) is int and 1 < pid < 2**31, "invalid original QEMU PID")
    fd = os.pidfd_open(pid, 0)
    try:
        pidfd_live(fd)
        before = proc_stat(pid)
        st = status(pid)
        exe = os.stat(f"/proc/{pid}/exe")
        expected = admitted["launcher"]["private_qemu_identity"]
        need((exe.st_dev, exe.st_ino) == (expected["dev"], expected["ino"])
             and exe.st_uid == exe.st_gid == 0 and exe.st_nlink == 1
             and stat.S_IMODE(exe.st_mode) == 0o511, "QEMU private executable changed")
        private, private_pin = read_file(admitted["launcher"]["private_qemu"]["path"],
                                         admitted["launcher"]["private_qemu"], limit=64 * 1024 * 1024)
        fixed = {k: expected[k] for k in ("dev","ino","mode","uid","gid","nlink","size")}
        fixed["mtime_ns"] = expected["mtime_sec"] * 1_000_000_000 + expected["mtime_nsec"]
        fixed["ctime_ns"] = expected["ctime_sec"] * 1_000_000_000 + expected["ctime_nsec"]
        need(private[:4] == b"\x7fELF" and identity(exe) == private_pin["identity"] == fixed,
             "private QEMU original F9 changed")
        parent = before["ppid"]
        pfd = os.pidfd_open(parent, 0)
        try:
            pidfd_live(pfd)
            parent_stat = proc_stat(parent)
            f = os.stat(f"/proc/{parent}/exe")
            fbytes, fp = read_file(fixture["path"], fixture, limit=64 * 1024 * 1024)
            need(fbytes[:4] == b"\x7fELF" and (f.st_dev, f.st_ino) ==
                 (fp["identity"]["dev"], fp["identity"]["ino"]), "QEMU no longer has its original fixture owner")
            need(proc_stat(parent) == parent_stat, "fixture owner changed")
            pidfd_live(pfd)
        finally:
            os.close(pfd)
        need(proc_stat(pid) == before, "QEMU start identity changed")
        pidfd_live(fd)
        return {"stat": before, "pidfd_node": node(os.fstat(fd)), "status": st,
                "executable_node": node(exe), "owner_stat": parent_stat,
                "cgroup": Path(f"/proc/{pid}/cgroup").read_text()}, fd
    except BaseException:
        os.close(fd)
        raise

def original_inputs(run):
    d = directory(run, private=True)
    try:
        for leaf in ("RUN-ENDED.json", "RUN-FAILED.json"):
            try:
                os.stat(leaf, dir_fd=d, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise Rejected("VM run is retired")
        root_identity = node(os.fstat(d))
    finally:
        os.close(d)
    running, rp = json_file(run / "RUNNING.json")
    admitted, ap = json_file(run / "QEMU-ADMITTED.json")
    plan, pp = json_file(run / "RUN-INPUTS.json")
    prepared, prepared_pin = json_file(plan["prepared"]["path"], plan["prepared"])
    need(plan["schema"] == "droidloom.full-ubuntu-run-plan.v1"
         and prepared["schema"] == "droidloom.full-ubuntu-boot-prepared.v1"
         and prepared["calibration_requested"] is False, "only the explicitly selected normal VM is admitted")
    need(run == Path(prepared["boot_directory"]) / plan["run_name"], "run root differs from original plan")
    need(admitted["schema"] == "droidloom.qemu-paused-launch-admitted.v1"
         and admitted["launcher"] == running["fixed_descriptor_launcher"]
         and admitted["launcher"]["sandbox"] == SANDBOX
         and admitted["actual_process"]["process_status"]["Pid"] == str(running["pid"]), "original launch admission mismatch")
    need(running["private_qmp"] == str(run / "qmp.sock"), "monitor path differs")
    ss = os.lstat(run / "qmp.sock")
    need(stat.S_ISSOCK(ss.st_mode) and ss.st_uid == ss.st_gid == 0 and ss.st_nlink == 1, "unsafe original monitor")
    return running, admitted, plan, {"run_node": root_identity, "socket_node": node(ss),
             "running": rp, "admitted": ap, "plan": pp, "prepared": prepared_pin}

def bind(args):
    run = canonical(args.run_directory)
    need(ROOT in run.parents, "run is outside qualification root")
    out = canonical(args.output)
    need(out.parent == ROOT, "evidence directory must be a new direct qualification child")
    parent = directory(out.parent)
    try:
        os.mkdir(out.name, 0o700, dir_fd=parent)
    finally:
        os.close(parent)
    running, admitted, plan, original = original_inputs(run)
    fixture_bytes, fixture = read_file(args.fixture, limit=64 * 1024 * 1024)
    need(digest(fixture_bytes) == args.fixture_sha256, "fixture source pin differs")
    stage, stage_pin = json_file(args.host_stage)
    need(stage_pin["sha256"] == args.host_stage_sha256, "host manifest pin differs")
    wayland = [x for x in stage["files"] if x["path"] == "usr/bin/droidloom-wayland"]
    need(len(wayland) == 1, "normal presenter source missing")
    client = [x for x in stage["files"] if x["path"] == "usr/bin/droidloomctl"]
    need(len(client) == 1, "normal inspection client source missing")
    presenter_unit = [x for x in stage["files"] if x["path"] == "usr/lib/systemd/user/droidloom-production-desktop.service"]
    need(len(presenter_unit) == 1, "normal presenter unit source missing")
    snap, pfd = process_snapshot(running, admitted, fixture)
    try:
        unit = unit_properties(args.unit)
        need(unit["InvocationID"] == args.invocation, "selected owner InvocationID differs")
        need(snap["cgroup"] == "0::" + unit["ControlGroup"] + "\n", "QEMU is outside original owner unit")
        now = time.clock_gettime(time.CLOCK_BOOTTIME)
        expires = snap["stat"]["start_ticks"] / os.sysconf("SC_CLK_TCK") + plan["duration_seconds"] - 25
        need(expires - now > 30, "too close to original owner shutdown")
        private_key = known = ssh_tool = None
        if plan["ssh_port"] is not None:
            need(plan["network"] is True and 50000 <= plan["ssh_port"] <= 59999, "unsafe SSH forwarding")
            _, private_key = read_file(running["fresh_client_key"], limit=16384)
            _, known = read_file(running["known_hosts"]["path"], running["known_hosts"], limit=4096)
            need(stat.S_IMODE(private_key["identity"]["mode"]) == 0o600, "fresh client key is not private")
            ssh_bytes, ssh_tool = read_file("/usr/bin/ssh", limit=64*1024*1024)
            need(ssh_bytes[:4] == b"\x7fELF" and not ssh_tool["identity"]["mode"] & 0o6022,
                 "SSH tool is not the original ordinary root executable")
        value = {"schema": "p4-qmp-evidence-binding-v1", "run_directory": str(run),
                 "original": original, "original_process": snap, "fixture": fixture,
                 "owner_unit": unit, "host_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                 "expires_boottime": expires, "host_stage": stage_pin, "presenter": wayland[0], "presenter_unit": presenter_unit[0], "inspection_client": client[0],
                 "ssh_port": plan["ssh_port"], "fresh_client_key": private_key, "known_hosts": known, "ssh_tool": ssh_tool,
                 "controller": read_file(str(Path(__file__).absolute()), limit=512*1024)[1],
                 "original_owner_retains_shutdown_and_reap": True,
                 "guest_qualified": False, "production_ready": False}
        pidfd_live(pfd)
        return write_json(out, "BINDING.json", value)
    finally:
        os.close(pfd)

class Authority:
    def __init__(self, path, sha):
        self.binding, self.pin = json_file(path)
        b = self.binding
        need(self.pin["sha256"] == sha and b["schema"] == "p4-qmp-evidence-binding-v1", "binding pin differs")
        need(b["controller"]["sha256"] == read_file(str(Path(__file__).absolute()), limit=512*1024)[1]["sha256"],
             "controller differs from binding")
        self.root = Path(path).parent
        self.run = Path(b["run_directory"])
        self.pidfd = None
        self.validate()
    def validate(self):
        b = self.binding
        need(Path("/proc/sys/kernel/random/boot_id").read_text().strip() == b["host_boot_id"], "host rebooted")
        need(time.clock_gettime(time.CLOCK_BOOTTIME) + 16 < b["expires_boottime"], "owner deadline is too close")
        running, admitted, plan, original = original_inputs(self.run)
        need(original == b["original"], "original run documents or socket changed")
        unit = unit_properties(b["owner_unit"]["Id"])
        need(unit == b["owner_unit"], "owner InvocationID or state changed")
        snap, fd = process_snapshot(running, admitted, b["fixture"])
        try:
            need(snap == b["original_process"] and snap["cgroup"] == "0::" + unit["ControlGroup"] + "\n",
                 "original process identity changed")
            if self.pidfd is None:
                self.pidfd = os.dup(fd)
            pidfd_live(self.pidfd)
            need(node(os.fstat(self.pidfd)) == snap["pidfd_node"], "original PIDFD inode changed")
        finally:
            os.close(fd)
    @property
    def peer(self):
        return self.binding["original_process"]["stat"]["pid"], 65534, 65534
    def close(self):
        if self.pidfd is not None:
            os.close(self.pidfd)
            self.pidfd = None

class Qmp:
    """One bounded connection; every received byte has actual sender credentials."""
    ALLOWED = {"query-status", "add-fd", "screendump", "remove-fd", "input-send-event"}
    def __init__(self, path, peer, deadline, guard=lambda: None):
        self.peer, self.deadline, self.guard = peer, deadline, guard
        self.buf = bytearray()
        self.count = self.serial = 0
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        self.sock.settimeout(min(2, max(0.001, deadline - time.monotonic())))
        try:
            self.sock.connect(str(path))
            greeting = self.line()
            need(isinstance(greeting, dict) and isinstance(greeting.get("QMP"), dict), "missing QMP greeting")
            self.command("qmp_capabilities", internal=True)
        except BaseException:
            self.sock.close()
            raise
    def line(self):
        while b"\n" not in self.buf:
            left = self.deadline - time.monotonic()
            need(left > 0 and len(self.buf) <= 65536, "QMP deadline or line bound")
            self.sock.settimeout(min(2, left))
            raw, anc, flags, _ = self.sock.recvmsg(8192, socket.CMSG_SPACE(12) + socket.CMSG_SPACE(16))
            need(raw and not flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC), "truncated QMP stream")
            creds = []
            unexpected = False
            for level, kind, body in anc:
                if level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS and len(body) == 12:
                    creds.append(struct.unpack("3i", body))
                elif level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    fds = array.array("i");fds.frombytes(body[:len(body)//fds.itemsize*fds.itemsize])
                    for fd in fds: os.close(fd)
                    unexpected = True
                else:
                    unexpected = True
            need(not unexpected and creds == [self.peer], "QMP actual sender changed")
            self.count += len(raw)
            need(self.count <= MAX_JSON, "QMP total output bound")
            self.buf.extend(raw)
        raw, _, rest = self.buf.partition(b"\n")
        self.buf = bytearray(rest)
        need(len(raw) <= 65536, "oversized QMP line")
        return json.loads(raw)
    def command(self, name, arguments=None, fd=None, internal=False):
        need(name in self.ALLOWED or internal and name == "qmp_capabilities", "unsupported QMP operation")
        if name != "remove-fd":
            self.guard()
        self.serial += 1
        request = {"execute": name, "id": self.serial}
        if arguments is not None: request["arguments"] = arguments
        raw = (json.dumps(request, separators=(",", ":")) + "\n").encode()
        self.sock.settimeout(max(.001, min(2, self.deadline - time.monotonic())))
        if fd is not None:
            need(name == "add-fd", "descriptor can only be added for capture")
            count = self.sock.sendmsg([raw], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))])
            need(count > 0, "QMP descriptor send failed")
            self.sock.sendall(raw[count:])
        else:
            self.sock.sendall(raw)
        for _ in range(32):
            answer = self.line()
            if answer.get("id") == self.serial:
                need("error" not in answer and "return" in answer, "QMP command rejected: " + str(answer.get("error", ""))[:256])
                return answer["return"]
        raise Rejected("QMP bounded event count exceeded")
    def close(self):
        self.sock.close()

def ppm(data):
    m = re.match(rb"P6\n([1-9][0-9]{0,3}) ([1-9][0-9]{0,3})\n255\n", data[:64])
    need(m is not None, "not QEMU's exact P6 PPM header")
    w, h = int(m[1]), int(m[2])
    need(1 <= w <= 4096 and 1 <= h <= 4096 and len(data) == m.end() + w*h*3 <= MAX_PPM,
         "PPM dimensions or complete pixel length differ")
    return {"format": "P6", "width": w, "height": h, "maxval": 255, "header_bytes": m.end(), "pixel_bytes": w*h*3}

def capture(qmp, root, name):
    d = directory(root, private=True)
    fd = os.open(name + ".ppm", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=d)
    started = time.monotonic_ns()
    added = None
    removal = False
    try:
        start_node = node(os.fstat(fd))
        added = qmp.command("add-fd", {"opaque": "p4-bounded-screen-evidence"}, fd=fd)
        need(isinstance(added, dict) and set(added) == {"fdset-id", "fd"} and all(type(added[k]) is int and added[k] >= 0 for k in added),
             "invalid added descriptor identity")
        need(added["fdset-id"] not in (1, 2), "capture unexpectedly joined a VM input set")
        qmp.command("screendump", {"filename": "/dev/fdset/" + str(added["fdset-id"]), "format": "ppm"})
        qmp.command("remove-fd", added)
        removal = True
        os.fsync(fd)
        need(node(os.fstat(fd)) == start_node, "capture inode metadata changed")
        data, pin = read_file(Path(root)/(name+".ppm"), limit=MAX_PPM)
        need(node(os.stat(pin["path"], follow_symlinks=False)) == start_node, "capture pathname replaced")
        need(stat.S_IMODE(pin["identity"]["mode"]) == 0o600, "capture file mode changed")
        return {"image": pin, "ppm": ppm(data), "removed_original_fdset_entry": True,
                "qmp_fd": added, "display_console_only": True, "task_first_frame_qualified": False,
                "host_monotonic_ns_start": started, "host_monotonic_ns_end": time.monotonic_ns()}
    finally:
        if isinstance(added, dict) and not removal and set(added) == {"fdset-id", "fd"}:
            with contextlib.suppress(Exception):
                qmp.command("remove-fd", added)
        os.close(fd);os.close(d)

# Fixed, read-only fresh-guest probe. No arbitrary remote command is accepted.
GUEST_PROBE = r"""
import hashlib,json,os,pathlib,re,stat,subprocess,time
assert os.getuid()==1000
env=os.environ.copy();env['XDG_RUNTIME_DIR']='/run/user/1000';env['DBUS_SESSION_BUS_ADDRESS']='unix:path=/run/user/1000/bus';env['LC_ALL']='C'
UNIT='droidloom-production-desktop.service'
UNIT_PATH='/usr/lib/systemd/user/'+UNIT
PROPERTIES='Id,MainPID,ExecMainPID,InvocationID,ActiveState,SubState,FragmentPath,DropInPaths,NeedDaemonReload,Transient,Type,NotifyAccess,NoNewPrivileges'
def props():
 r=subprocess.run(['/usr/bin/systemctl','--user','--no-pager','show',UNIT,'--property='+PROPERTIES],env=env,capture_output=True,timeout=2,check=True)
 assert len(r.stdout)<=16384 and len(r.stderr)<=16384
 p=dict(x.split('=',1) for x in r.stdout.decode().splitlines() if '=' in x)
 assert p['Id']==UNIT and p['FragmentPath']==UNIT_PATH and p['DropInPaths']==''
 assert p['NeedDaemonReload']=='no' and p['Transient']=='no'
 assert p['Type']=='notify' and p['NotifyAccess']=='main' and p['NoNewPrivileges']=='yes'
 assert p['ActiveState']=='active' and p['SubState']=='running'
 assert re.fullmatch('[0-9a-f]{32}',p['InvocationID']) and int(p['InvocationID'],16)
 assert p['MainPID']==p['ExecMainPID'] and 1<int(p['MainPID'])<2**31
 return p
def F(x):
 return dict(dev=x.st_dev,ino=x.st_ino,mode=x.st_mode,uid=x.st_uid,gid=x.st_gid,nlink=x.st_nlink,size=x.st_size,mtime_ns=x.st_mtime_ns,ctime_ns=x.st_ctime_ns)
def public(path,maximum,elf=False):
 parts=path.split('/');assert parts[0]=='' and all(x and x not in ('.','..') for x in parts[1:])
 parent=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC)
 try:
  for part in parts[1:-1]:
   child=os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
   os.close(parent);parent=child
   s=os.fstat(parent);assert s.st_uid==s.st_gid==0 and not s.st_mode&0o022
  fd=os.open(parts[-1],os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent)
  try:
   s=os.fstat(fd);assert stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and s.st_nlink==1 and 0<s.st_size<=maximum and not s.st_mode&0o6022
   h=hashlib.sha256();total=0;head=b''
   while True:
    x=os.read(fd,min(65536,maximum+1-total))
    if not x:break
    if not total:head=x[:4]
    total+=len(x);assert total<=s.st_size
    h.update(x)
   assert total==s.st_size and (not elf or head==b'\x7fELF')
   assert F(os.fstat(fd))==F(os.stat(parts[-1],dir_fd=parent,follow_symlinks=False))==F(s)
   return dict(path=path,bytes=total,sha256=h.hexdigest(),identity=F(s))
  finally:os.close(fd)
 finally:os.close(parent)
def pinned(value,expected):
 assert value['sha256']==expected['sha256'] and value['bytes']==expected['size']
 assert stat.S_IMODE(value['identity']['mode'])==expected['mode']
def journal(p,kind,count):
 fields='__CURSOR,__MONOTONIC_TIMESTAMP,_BOOT_ID,_PID,_UID,_SYSTEMD_USER_UNIT,_SYSTEMD_INVOCATION_ID,MESSAGE'
 r=subprocess.run(['/usr/bin/journalctl','--user','--no-pager','-u',UNIT,'-o','json','--output-fields='+fields,
                   '--grep=^Droidloom '+kind+' trace:','-n',str(count),'_PID='+p['MainPID'],'_SYSTEMD_INVOCATION_ID='+p['InvocationID']],
                  env=env,capture_output=True,timeout=2,check=True)
 assert len(r.stdout)<=1048576 and len(r.stderr)<=16384
 rows=[json.loads(x) for x in r.stdout.splitlines()];assert len(rows)<=count
 return rows
start=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
p=props()
unit=public(UNIT_PATH,65536);pinned(unit,UNIT_PIN)
presenter=public('/usr/bin/droidloom-wayland',32*1024*1024,True);pinned(presenter,PRESENTER_PIN)
identity_rows=journal(p,'identity',2)
assert len(identity_rows)==1
row=identity_rows[0];boot=row['_BOOT_ID'];assert re.fullmatch('[0-9a-f]{32}',boot)
boot=boot[:8]+'-'+boot[8:12]+'-'+boot[12:16]+'-'+boot[16:20]+'-'+boot[20:]
client=public('/usr/bin/droidloomctl',32*1024*1024,True);pinned(client,CLIENT_PIN)
inspection_run=subprocess.run(['/usr/bin/droidloomctl','--json','inspect',PACKAGE,'--user','0'],env=env,capture_output=True,timeout=4,check=True)
assert len(inspection_run.stdout)<=1048576 and len(inspection_run.stderr)<=1048576
inspection_response=json.loads(inspection_run.stdout)
assert inspection_response['ok'] is True and inspection_response['inspection']['package']==PACKAGE and inspection_response['inspection']['user']==0
rows=journal(p,'(focus|key|frame)',512)
assert props()==p
for path,proof in [(UNIT_PATH,unit),('/usr/bin/droidloom-wayland',presenter),('/usr/bin/droidloomctl',client)]:
 assert F(os.stat(path,follow_symlinks=False))==proof['identity']
end=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
print(json.dumps({'schema':'p4-native-focus-observation-v2','guest_clock':'CLOCK_MONOTONIC','guest_boot_id':boot,'guest_monotonic_ns_start':start,'guest_monotonic_ns_end':end,'unit':p,'public_presenter':presenter,'public_unit':unit,'identity_journal':identity_rows,'inspection_response':inspection_response,'inspection_stdout_sha256':hashlib.sha256(inspection_run.stdout).hexdigest(),'inspection_stdout_bytes':len(inspection_run.stdout),'journal':rows},separators=(',',':')))
"""


def bounded_subprocess(command, stdin, deadline, max_output=MAX_JSON):
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8"})
    output = bytearray(); errors = bytearray()
    try:
        child.stdin.write(stdin);child.stdin.close()
        fds = {child.stdout.fileno(): output, child.stderr.fileno(): errors}
        for fd in fds: os.set_blocking(fd, False)
        while fds:
            left = deadline-time.monotonic()
            need(left > 0, "fresh-guest probe deadline")
            ready, _, _ = select.select(list(fds), [], [], min(left, .25))
            for fd in ready:
                chunk = os.read(fd, 65536)
                if not chunk: del fds[fd];continue
                fds[fd].extend(chunk)
                need(len(output)+len(errors) <= max_output, "fresh-guest output exceeded bound")
        need(child.wait(timeout=max(.001, deadline-time.monotonic())) == 0,
             "fresh-guest read-only probe failed: " + errors.decode(errors="replace")[:512])
        return bytes(output)
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=3)
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream is not None: stream.close()

def journal_sender(row, presenter, boot_id):
    need(re.fullmatch("[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot_id) is not None,
         "invalid original guest boot ID")
    need(row.get("_PID") == str(presenter["pid"]) and row.get("_UID") == "1000"
         and row.get("_SYSTEMD_USER_UNIT") == "droidloom-production-desktop.service"
         and row.get("_SYSTEMD_INVOCATION_ID") == presenter["invocation_id"]
         and row.get("_BOOT_ID") == boot_id.replace("-", ""), "foreign journal sender or invocation")
    raw = row.get("__MONOTONIC_TIMESTAMP")
    need(type(raw) is str and re.fullmatch("[0-9]{1,20}", raw) is not None, "invalid trusted journal clock")
    return int(raw) * 1000

def validate_presenter_identity(observation, binding):
    """Match actual self measurement to trusted journal, the live unit and public files."""
    unit = observation["unit"]
    name = "droidloom-production-desktop.service"
    unit_path = "/usr/lib/systemd/user/" + name
    required = {"Id": name, "FragmentPath": unit_path, "DropInPaths": "",
                "NeedDaemonReload": "no", "Transient": "no", "Type": "notify",
                "NotifyAccess": "main", "NoNewPrivileges": "yes",
                "ActiveState": "active", "SubState": "running"}
    need(all(unit.get(k) == v for k, v in required.items()), "original presenter unit changed")
    need(type(unit.get("MainPID")) is str and unit["MainPID"].isdigit()
         and 1 < int(unit["MainPID"]) < 2**31 and unit.get("ExecMainPID") == unit["MainPID"],
         "presenter unit has no original main process")
    invocation = unit.get("InvocationID")
    need(type(invocation) is str and re.fullmatch("[0-9a-f]{32}", invocation) is not None
         and int(invocation, 16) != 0, "presenter unit invocation is absent")
    f9_keys = {"dev", "ino", "mode", "uid", "gid", "nlink", "size", "mtime_ns", "ctime_ns"}
    for proof, expected, path in (
            (observation["public_presenter"], binding["presenter"], "/usr/bin/droidloom-wayland"),
            (observation["public_unit"], binding["presenter_unit"], unit_path)):
        measured = proof["identity"]
        need(proof["path"] == path and expected["path"] == path[1:]
             and proof["bytes"] == expected["size"] and proof["sha256"] == expected["sha256"]
             and set(measured) == f9_keys and all(type(v) is int for v in measured.values()),
             "normal public source proof changed")
        need(stat.S_ISREG(measured["mode"]) and stat.S_IMODE(measured["mode"]) == expected["mode"]
             and measured["uid"] == measured["gid"] == 0 and measured["nlink"] == 1
             and measured["dev"] >= 0 and measured["ino"] > 0
             and measured["size"] == expected["size"] and not measured["mode"] & 0o6022,
             "normal public source inode is not protected")
    rows = observation["identity_journal"]
    need(type(rows) is list and len(rows) == 1, "exactly one original identity trace is required")
    row = rows[0]
    message = row.get("MESSAGE")
    prefix = "Droidloom identity trace: "
    need(type(message) is str and message.startswith(prefix) and len(message.encode()) <= 4200,
         "missing bounded self identity record")
    measured = json.loads(message[len(prefix):])
    need(set(measured) == {"schema", "pid", "uid", "gid", "start_ticks", "clk_tck",
                          "observed_ns", "invocation_id", "elf_sha256", "executable", "selinux", "apparmor"}
         and measured["schema"] == "p4-presenter-self-identity-v1", "unknown self identity schema")
    need(all(type(measured[k]) is int for k in ("pid", "uid", "gid", "start_ticks", "clk_tck", "observed_ns"))
         and measured["pid"] == int(unit["MainPID"]) and measured["uid"] == measured["gid"] == 1000
         and measured["invocation_id"] == invocation, "self identity differs from original unit")
    need(type(measured["executable"]) is dict and set(measured["executable"]) == f9_keys
         and all(type(v) is int for v in measured["executable"].values())
         and measured["elf_sha256"] == binding["presenter"]["sha256"]
         and measured["executable"] == observation["public_presenter"]["identity"],
         "actual self executable differs from the normal public inode")
    need(measured["selinux"] == "u:system_r:droidloom_presenter:s0"
         and type(measured["apparmor"]) is str and 0 < len(measured["apparmor"]) <= 1024
         and all(0x20 <= ord(c) <= 0x7e for c in measured["apparmor"]), "actual self MAC record differs")
    presenter = {"pid": measured["pid"], "invocation_id": invocation,
                 "start_ticks": measured["start_ticks"], "clk_tck": measured["clk_tck"],
                 "elf_sha256": measured["elf_sha256"], "elf_bytes": measured["executable"]["size"],
                 "elf_dev": measured["executable"]["dev"], "elf_ino": measured["executable"]["ino"],
                 "executable": measured["executable"], "selinux": measured["selinux"],
                 "apparmor": measured["apparmor"], "self_observed_ns": measured["observed_ns"],
                 "identity_journal_cursor": row.get("__CURSOR")}
    journal_ns = journal_sender(row, presenter, observation["guest_boot_id"])
    need(0 < presenter["start_ticks"] < 2**63 and 0 < presenter["clk_tck"] <= 1_000_000
         and presenter["start_ticks"] * 1_000_000_000 // presenter["clk_tck"]
             <= measured["observed_ns"] <= journal_ns + 999
         and 0 < journal_ns <= observation["guest_monotonic_ns_end"], "self identity clock is inconsistent")
    return presenter

def focus_probe(authority, event):
    b = authority.binding
    need(b["ssh_port"] is not None and b["fresh_client_key"] is not None, "explicit fresh guest SSH is required")
    for p in (b["fresh_client_key"], b["known_hosts"]): read_file(p["path"], p, limit=16384)
    read_file(b["ssh_tool"]["path"], b["ssh_tool"], limit=64*1024*1024)
    command = ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-oControlMaster=no", "-oControlPath=none", "-oBatchMode=yes", "-oIdentitiesOnly=yes", "-oIdentityAgent=none",
               "-oPasswordAuthentication=no", "-oKbdInteractiveAuthentication=no", "-oPreferredAuthentications=publickey",
               "-oStrictHostKeyChecking=yes", "-oUserKnownHostsFile="+b["known_hosts"]["path"],
               "-oGlobalKnownHostsFile=/dev/null", "-oConnectTimeout=3", "-oConnectionAttempts=1",
               "-oLogLevel=ERROR", "-i", b["fresh_client_key"]["path"], "-p", str(b["ssh_port"]),
               "alex@127.0.0.1", "/usr/bin/python3", "-I", "-"]
    started = time.monotonic_ns()
    client = b["inspection_client"]
    fixed = "PACKAGE=" + repr(event["package"]) + "\nCLIENT_PIN=" + repr(client) + "\nPRESENTER_PIN=" + repr(b["presenter"]) + "\nUNIT_PIN=" + repr(b["presenter_unit"]) + "\n"
    raw = bounded_subprocess(command, (fixed+GUEST_PROBE).encode(), time.monotonic()+8)
    finished = time.monotonic_ns()
    value = json.loads(raw)
    need(value["schema"] == "p4-native-focus-observation-v2" and value["guest_clock"] == "CLOCK_MONOTONIC",
         "invalid actual focus probe")
    value["presenter"] = validate_presenter_identity(value, b)
    inspection = value["inspection_response"]["inspection"]
    need(value["inspection_response"]["ok"] is True and inspection["package"] == event["package"]
         and inspection["user"] == 0 and inspection["epoch"] == event["epoch"], "actual Android generation changed")
    value["host_collection_started_monotonic_ns"] = started
    value["host_collection_finished_monotonic_ns"] = finished
    return value

def launch_event(path, sha):
    event, pin = json_file(path)
    need(pin["sha256"] == sha and event["schema"] == "p4-selected39-launch-event-v1", "selected launch event pin differs")
    need(event["guest_clock"] == "CLOCK_MONOTONIC", "event clock is not guest monotonic")
    need(type(event["guest_monotonic_ns_start"]) is int and type(event["guest_monotonic_ns_end"]) is int
         and 0 <= event["guest_monotonic_ns_start"] <= event["guest_monotonic_ns_end"], "invalid event time interval")
    b = event["binding"]
    need(set(b) == {"object", "composer_display", "android_display", "task"}
         and all(type(v) is int for v in b.values()) and b["object"] > 0 and b["composer_display"] > 0
         and b["android_display"] == 0 and 0 < b["task"] < 2**31, "invalid original task binding")
    need(all(k in event["epoch"] for k in ("boot_id", "cell_host_pid", "framework_host_pid", "framework_start_ticks")),
         "original runtime epoch missing")
    need(len(event["package"]) <= 255 and re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", event["package"]), "invalid reviewed package")
    return event, pin

def validate_focus(event, observation, maximum_launch_age_ns=30_000_000_000):
    need(observation["inspection_response"]["inspection"]["epoch"] == event["epoch"], "actual Android generation changed")
    need(event["guest_boot_id"] == observation["guest_boot_id"] and event["epoch"]["boot_id"] == observation["guest_boot_id"], "guest boot changed")
    start, end = observation["guest_monotonic_ns_start"], observation["guest_monotonic_ns_end"]
    need(type(start) is int and type(end) is int and 0 <= end-start <= 8_000_000_000, "unbounded focus observation")
    need(0 <= end-event["guest_monotonic_ns_end"] <= maximum_launch_age_ns, "launch event is stale")
    p = observation["presenter"]
    if event.get("presenter") is not None:
        need(event["presenter"]["pid"] == p["pid"] and event["presenter"]["invocation_id"] == p["invocation_id"],
             "presenter changed since selected launch")
    current = None;last_enter = None;previous_time = 0
    need(len(observation["journal"]) <= 512, "journal bound exceeded")
    for row in observation["journal"]:
        t = journal_sender(row, p, observation["guest_boot_id"])
        need(t >= previous_time, "journal order changed");previous_time=t
        if t < p["start_ticks"]*1_000_000_000//p["clk_tck"]: continue
        text = row["MESSAGE"]
        if not text.startswith("Droidloom focus trace:"): continue
        m = FOCUS.fullmatch(text);need(m is not None, "malformed focus trace")
        pid, obj, serial, observed = map(int, m.groups()[:4])
        need(pid == p["pid"] and 0 <= observed <= end, "invalid native focus identity/time")
        if m[5] == "enter":
            current = obj if obj else None
            last_enter = observed if obj else None
        elif obj == 0 or current == obj:
            current = last_enter = None
    require_observation(current == event["binding"]["object"] and last_enter is not None and end-last_enter <= 15_000_000_000,
             "no recent actual focus for this original task object")
    return {"object": current, "presenter_pid": p["pid"], "presenter_invocation": p["invocation_id"],
            "focus_observed_guest_monotonic_ns": last_enter, "launch_event_epoch": event["epoch"]}

def presented_feedback(event, observation):
    """Native sampled wp_presentation evidence, never a claim of the first ever frame."""
    need(event["guest_boot_id"] == observation["guest_boot_id"], "presentation guest boot differs")
    p = observation["presenter"]; found = []
    for row in observation["journal"]:
        journal_sender(row, p, observation["guest_boot_id"])
        m = FRAME.fullmatch(row.get("MESSAGE", ""))
        if not m: continue
        pid, seq, obj, frame, buffer, observed, displayed, refresh, display_seq, dropped = map(int, m.groups())
        if obj != event["binding"]["object"]: continue
        need(pid == p["pid"] and 0 < seq <= 65536 and frame > 0 and frame % 8 == 1 and buffer > 0
             and 0 < displayed <= observed <= observation["guest_monotonic_ns_end"],
             "invalid native presentation feedback")
        if displayed < event["guest_monotonic_ns_start"]: continue
        found.append({"presenter_pid": pid, "presenter_invocation": p["invocation_id"], "object": obj,
                      "frame": frame, "buffer": buffer, "display_guest_monotonic_ns": displayed,
                      "callback_guest_monotonic_ns": observed, "display_sequence": display_seq,
                      "refresh_ns": refresh, "trace_sequence": seq, "dropped_total": dropped,
                      "journal_cursor": row.get("__CURSOR")})
    return {"observed": bool(found), "frames": found, "sampling": "frame modulo 8 equals 1",
            "first_ever_frame_proven": False, "pixel_to_task_binding_proven": False}

def wayland_key_pair(before, after, event, key):
    p = before["presenter"]
    need(after["presenter"] == p and after["guest_boot_id"] == before["guest_boot_id"], "presenter changed after input")
    rows = []
    for row in after["journal"]:
        if journal_sender(row, p, after["guest_boot_id"]) < before["guest_monotonic_ns_end"]:
            continue
        m = KEY.fullmatch(row.get("MESSAGE", ""))
        if m and int(m[2]) == event["binding"]["object"] and int(m[4]) == KEYS[key] and int(m[5]) == 0:
            rows.append((int(m[1]), m[3]))
    return len(rows) == 2 and rows[0][1] == "Down" and rows[1] == (rows[0][0]+1, "Up")


# This is a live exchange only. Saved launch events are never close authority.
PUBLIC_STAGE = "/var/lib/droidloom-public-apks/u1000"
REGISTRY_SHA256 = "0b21f963898308b082f3808dd48165c1397badd1fa8a753c3a766e135b3cb3c8"
LIFECYCLE_SECONDS = 600
WINDOW_PREFIX = "Droidloom window trace: "

def fresh_lifecycle_inputs(prepared, package):
    need(type(package) is str and len(package) <= 255
         and re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", package), "invalid selected package")
    need(prepared["schema"] == "droidloom.full-ubuntu-boot-prepared.v1"
         and prepared["calibration_requested"] is False
         and prepared["boot_phase"] == "android_runtime", "not a normal fresh Android guest")
    staged = prepared["public_apk_import"]
    need(staged["schema"] == "droidloom.public-apks-staged.v1"
         and staged["original_userdata_imported"] is False
         and staged["package_count"] == 39 and staged["apk_file_count"] == 65
         and staged["applications_installed"] == 0, "fresh complete public import is required")
    files = staged["files"]
    need(type(files) is list and len(files) == 69, "complete 65 APK and four JSON import required")
    paths = [v["guest_path"] for v in files]
    need(len(set(paths)) == 69 and all(type(p) is str and str(Path(p).parent) == PUBLIC_STAGE for p in paths),
         "public import paths differ")
    expected_json = {"selected39-execution.json", "selected39-source-selection.json",
                     "selected39-signature-receipt.json", "app-release-gates.json"}
    metadata = [v for v in files if v["package"] is None]
    apks = [v for v in files if v["package"] is not None]
    need(len(apks) == 65 and {Path(v["guest_path"]).name for v in metadata} == expected_json,
         "public import membership differs")
    for v in files:
        source = v["source"]
        need(type(source["bytes"]) is int and source["bytes"] > 0
             and re.fullmatch("[0-9a-f]{64}", source["sha256"]), "invalid public file pin")
        if v["package"] is not None:
            need(Path(v["guest_path"]).name == source["sha256"] + ".apk", "APK digest filename differs")
    prep = staged["runtime_preparation_inputs"]
    for key, name in (("selection", "selected39-source-selection.json"),
                      ("source_receipt", "selected39-signature-receipt.json"),
                      ("gate_registry", "app-release-gates.json")):
        pin = prep[key]
        matches = [v for v in metadata if v["guest_path"] == pin["path"]]
        need(pin["path"] == PUBLIC_STAGE + "/" + name and len(matches) == 1
             and all(pin[k] == matches[0]["source"][k] for k in ("bytes", "sha256")),
             "runtime source pin differs from actual imported material")
    need(prep["gate_registry"]["bytes"] == 27878 and prep["gate_registry"]["sha256"] == REGISTRY_SHA256,
         "canonical full gate registry differs")
    rows = staged["applications"]
    names = [v["package"] for v in rows]
    need(len(names) == len(set(names)) == 39 and set(prep["required_gates"]) == set(names)
         and package in names, "reviewed selected39 package missing")
    required = prep["required_gates"][package]
    need(type(required) is list and len(required) >= 6 and len(set(required)) == len(required),
         "complete required gates missing")
    members = [v for v in apks if v["package"] == package]
    need(members and sum(v["split"] is None for v in members) == 1
         and len({v["split"] for v in members}) == len(members), "selected base/split set differs")
    return {"selection": prep["selection"], "required_gates": required,
            "application": rows[names.index(package)],
            "apks": [{"bytes": v["source"]["bytes"], "sha256": v["source"]["sha256"], "split": v["split"]}
                     for v in members]}

def selected_application(row, inspection, inputs, package):
    need(row["package"] == inspection["package"] == inputs["application"]["package"] == package
         and inspection["user"] == 0 and type(inspection["uid"]) is int and inspection["uid"] > 0
         and inspection["version_code"] == row["version_code"] == inputs["application"]["version_code"],
         "actual installed package/UID/version differs")
    epoch = inspection["epoch"]
    need(set(epoch) == {"boot_id", "cell_host_pid", "framework_host_pid", "framework_start_ticks"}
         and re.fullmatch("[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", epoch["boot_id"])
         and all(type(epoch[k]) is int and epoch[k] > 0 for k in
                 ("cell_host_pid", "framework_host_pid", "framework_start_ticks")), "actual epoch missing")
    expected = sorted((v["sha256"], v["bytes"]) for v in inputs["apks"])
    actual = inspection["apks"]
    need(type(actual) is list and len(actual) == len(expected)
         and sorted((v["sha256"], v["bytes"]) for v in actual) == expected
         and len({v["path"] for v in actual}) == len(actual)
         and len({v["name"] for v in actual}) == len(actual)
         and sum(v["name"] == "base.apk" for v in actual) == 1,
         "complete PM-returned APK bytes differ from signed selection")
    need(sorted((v["sha256"], v["bytes"]) for v in row["material_files"]) == expected,
         "live source selection APK set differs")
    component = row["preferred_manifest_component"]
    need(type(component) is str and component.startswith(package + "/") and len(component) <= 512
         and re.fullmatch(r"[A-Za-z0-9_.$/]+", component)
         and row["runtime_plan_application_binding"]["launch"] ==
             {"component": component, "specification": None}, "reviewed launcher component differs")
    return component

def actual_control(observation, name, expected=None):
    command = observation["commands"][name]
    need(command["returncode"] == 0 and type(command["started_ns"]) is int
         and type(command["ended_ns"]) is int and 0 < command["started_ns"] <= command["ended_ns"],
         "actual public command failed or has invalid timing")
    response = command["response"]
    need(response["ok"] is True and response["state"] == "running"
         and response["host_pid"] == response["inspection"]["epoch"]["cell_host_pid"],
         "original Android owner is not Running")
    if expected is not None:
        need(response["inspection"] == expected, "installed identity or actual epoch changed")
    return response

def actual_tasks(observation, expected=None):
    response = actual_control(observation, "tasks", expected)
    snapshot = json.loads(response["diagnostics"])
    need(snapshot["schema"] == "droidloom.application-task-snapshot.v1"
         and snapshot["application"] == response["inspection"]
         and type(snapshot["listing_bytes"]) is int and 0 <= snapshot["listing_bytes"] <= 65536
         and re.fullmatch("[0-9a-f]{64}", snapshot["listing_sha256"])
         and type(snapshot["tasks"]) is list and len(snapshot["tasks"]) <= 256,
         "actual typed task snapshot differs")
    ids = []
    for task in snapshot["tasks"]:
        need(set(task) == {"task", "root_task", "display", "user", "name", "visible", "top_activity"}
             and all(type(task[k]) is int and 0 <= task[k] < 2**31 for k in ("task", "root_task", "display", "user"))
             and task["user"] == 0 and task["name"].split("/", 1)[0] == snapshot["application"]["package"]
             and type(task["visible"]) is bool, "foreign or malformed observed task")
        ids.append(task["task"])
    need(ids == sorted(set(ids)), "repeated or unordered observed task")
    return snapshot

def actual_launch_event(observation, expected):
    response = actual_control(observation, "launch", expected)
    raw = response["launch"]
    need(type(raw) is str and 0 < len(raw) <= 256 and raw.isascii(), "missing bounded actual launch response")
    binding = {}
    for part in raw.split():
        key, sep, value = part.partition("=")
        need(sep and key not in binding and key in ("object", "composer_display", "android_display", "task")
             and re.fullmatch("[0-9]{1,20}", value), "malformed actual launch binding")
        binding[key] = int(value)
    need(set(binding) == {"object", "composer_display", "android_display", "task"}
         and 0 < binding["object"] < 2**64 and 0 < binding["composer_display"] < 2**64
         and binding["android_display"] == 0 and 0 < binding["task"] < 2**31, "invalid actual launch binding")
    command = observation["commands"]["launch"]
    return {"schema": "p4-selected39-launch-event-v1", "guest_clock": "CLOCK_MONOTONIC",
            "guest_boot_id": observation["guest_boot_id"], "package": expected["package"], "epoch": expected["epoch"],
            "guest_monotonic_ns_start": command["started_ns"], "guest_monotonic_ns_end": command["ended_ns"],
            "binding": binding, "presenter": observation["presenter"]}

def native_window_events(observation, event):
    presenter = observation["presenter"]
    need(presenter == event["presenter"] and observation["guest_boot_id"] == event["guest_boot_id"],
         "original presenter changed")
    result = []; previous = 0; previous_sequence = 0
    need(len(observation["window_journal"]) <= 512, "window journal bound exceeded")
    for row in observation["window_journal"]:
        stamp = journal_sender(row, presenter, observation["guest_boot_id"])
        need(stamp >= previous, "window journal order changed"); previous = stamp
        text = row["MESSAGE"]
        need(type(text) is str and text.startswith(WINDOW_PREFIX) and len(text) <= 2048,
             "malformed window journal")
        value = json.loads(text[len(WINDOW_PREFIX):])
        need(set(value) == {"schema", "pid", "sequence", "creation_sequence", "object", "surface",
                           "package", "android_task", "observed_ns", "stage"}
             and value["schema"] == "p4-presenter-window-event-v1" and value["pid"] == presenter["pid"]
             and all(type(value[k]) is int and value[k] > 0 for k in
                     ("sequence", "creation_sequence", "object", "surface", "observed_ns"))
             and value["creation_sequence"] <= value["sequence"] <= 65536
             and value["sequence"] > previous_sequence
             and value["object"] < 2**64 and value["surface"] < 2**32
             and (value["android_task"] is None or type(value["android_task"]) is int and 0 <= value["android_task"] < 2**31)
             and type(value["package"]) is str and len(value["package"]) <= 255
             and re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", value["package"])
             and presenter["start_ticks"]*1_000_000_000//presenter["clk_tck"] <= value["observed_ns"] <= stamp + 999
             and stamp <= observation["guest_monotonic_ns_end"]
             and value["stage"] in ("created", "bound", "close_sent", "unmapped"),
             "invalid actual window event")
        previous_sequence = value["sequence"]
        if value["object"] == event["binding"]["object"]:
            need(value["package"] == event["package"]
                 and (value["android_task"] is None or value["android_task"] == event["binding"]["task"]),
                 "window object belongs to a different package/task")
            result.append(dict(value, journal_cursor=row.get("__CURSOR")))
    return result

def created_window(event, observation):
    events = native_window_events(observation, event)
    created = [v for v in events if v["stage"] == "created"]
    require_observation(created, "actual window creation has not arrived")
    need(len(created) == 1, "exactly one actual window creation required")
    creation = created[0]
    need(creation["android_task"] is None and creation["sequence"] == creation["creation_sequence"]
         and event["guest_monotonic_ns_start"] <= creation["observed_ns"] <= observation["guest_monotonic_ns_end"],
         "window was not created during this live launch exchange")
    need(all(v["creation_sequence"] == creation["sequence"] and v["surface"] == creation["surface"] for v in events),
         "window creation identity changed")
    bound = [v for v in events if v["stage"] == "bound" and v["android_task"] == event["binding"]["task"]
             and v["sequence"] > creation["sequence"] and v["observed_ns"] >= creation["observed_ns"]]
    need(not any(v["stage"] in ("close_sent", "unmapped") for v in events), "window has already closed")
    require_observation(bound, "actual window task binding has not arrived")
    return {"created": creation, "bound": bound,
            "exclusive_android_task_creation_proven": False}

def closed_window(event, observation, created, before_ns):
    events = native_window_events(observation, event)
    creation = created["created"]
    need(all(v["creation_sequence"] == creation["sequence"] and v["surface"] == creation["surface"] for v in events),
         "original window token changed")
    sent = [v for v in events if v["stage"] == "close_sent" and v["observed_ns"] >= before_ns
            and v["android_task"] == event["binding"]["task"]]
    unmapped = [v for v in events if v["stage"] == "unmapped" and v["observed_ns"] >= before_ns]
    tasks = actual_tasks(observation, event["inspection"])["tasks"]
    need(len(sent) <= 1 and len(unmapped) <= 1, "repeated native close or unmap event")
    require_observation(sent and unmapped, "normal close-send and unmap not both observed")
    need(sent[0]["sequence"] < unmapped[0]["sequence"]
         and sent[0]["observed_ns"] <= unmapped[0]["observed_ns"], "native close/unmap order differs")
    require_observation(not tasks, "selected package still has an actual task")
    return {"close_sent": sent[0], "unmapped": unmapped[0], "task_absence_observed": True,
            "close_message_alone_is_not_removal_ack": True}

def normal_close_events():
    return [{"type": "key", "data": {"down": down, "key": {"type": "qcode", "data": key}}}
            for key, down in (("alt", True), ("f4", True), ("f4", False), ("alt", False))]


# Reuse only the fixed public-file/unit/journal readers above. Launch is a closed
# verb in this guest program, never a caller-supplied command or object selector.
GUEST_LIFECYCLE = GUEST_PROBE.split("start=time.clock_gettime_ns(time.CLOCK_MONOTONIC)", 1)[0] + r"""
def selected_source():
 base='/var/lib/droidloom-public-apks'
 parent=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC)
 try:
  for part in base.split('/')[1:]:
   child=os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
   os.close(parent);parent=child
   s=os.fstat(parent);assert s.st_uid==s.st_gid==0 and not s.st_mode&0o022
  child=os.open('u1000',os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
  os.close(parent);parent=child;s=os.fstat(parent)
  assert s.st_uid==s.st_gid==1000 and stat.S_IMODE(s.st_mode)==0o700
  assert SELECTION_PIN['path']==base+'/u1000/selected39-source-selection.json'
  fd=os.open('selected39-source-selection.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
  try:
   before=os.fstat(fd);assert stat.S_ISREG(before.st_mode) and before.st_uid==before.st_gid==1000
   assert stat.S_IMODE(before.st_mode)==0o400 and before.st_nlink==1 and 0<before.st_size<=2*1024*1024
   raw=b''
   while len(raw)<=before.st_size:
    part=os.read(fd,min(65536,before.st_size+1-len(raw)))
    if not part:break
    raw+=part
   assert len(raw)==before.st_size==SELECTION_PIN['bytes'] and hashlib.sha256(raw).hexdigest()==SELECTION_PIN['sha256']
   assert F(before)==F(os.fstat(fd))==F(os.stat('selected39-source-selection.json',dir_fd=parent,follow_symlinks=False))
   selection=json.loads(raw);rows=selection['applications']
   assert len(rows)==39 and len({v['package'] for v in rows})==39
   matches=[v for v in rows if v['package']==PACKAGE];assert len(matches)==1
   return matches[0],dict(SELECTION_PIN,identity=F(before))
  finally:os.close(fd)
 finally:os.close(parent)
result={'schema':'p4-native-lifecycle-observation-v1','guest_clock':'CLOCK_MONOTONIC',
        'action':ACTION,'commands':{},'success':False,'exchange_started_ns':time.clock_gettime_ns(time.CLOCK_MONOTONIC)}
def ctl(name,argv,limit=130):
 assert name in ('tasks','inspect','catalog','launch')
 assert F(os.stat('/usr/bin/droidloomctl',follow_symlinks=False))==client['identity']
 start=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
 run=subprocess.run(['/usr/bin/droidloomctl','--json']+argv,env=env,capture_output=True,timeout=limit)
 assert len(run.stdout)<=1048576 and len(run.stderr)<=65536
 rec={'argv':['/usr/bin/droidloomctl','--json']+argv,'returncode':run.returncode,
      'started_ns':start,'ended_ns':time.clock_gettime_ns(time.CLOCK_MONOTONIC),
      'stdout_bytes':len(run.stdout),'stdout_sha256':hashlib.sha256(run.stdout).hexdigest(),
      'stderr':run.stderr.decode(errors='replace'),'response':None}
 result['commands'][name]=rec
 try:rec['response']=json.loads(run.stdout)
 except ValueError:rec['unparsed_stdout']=run.stdout.decode(errors='replace')[:65536]
 assert run.returncode==0 and rec['response']['ok'] is True and rec['response']['state']=='running'
 assert F(os.stat('/usr/bin/droidloomctl',follow_symlinks=False))==client['identity']
 return rec['response']
try:
 assert ACTION in ('tasks','focus','launch') and re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+',PACKAGE)
 p=props();result['unit']=p
 unit=public(UNIT_PATH,65536);pinned(unit,UNIT_PIN);result['public_unit']=unit
 presenter=public('/usr/bin/droidloom-wayland',32*1024*1024,True);pinned(presenter,PRESENTER_PIN);result['public_presenter']=presenter
 client=public('/usr/bin/droidloomctl',32*1024*1024,True);pinned(client,CLIENT_PIN);result['public_client']=client
 identity_rows=journal(p,'identity',2);assert len(identity_rows)==1;result['identity_journal']=identity_rows
 boot=identity_rows[0]['_BOOT_ID'];assert re.fullmatch('[0-9a-f]{32}',boot)
 result['guest_boot_id']=boot[:8]+'-'+boot[8:12]+'-'+boot[12:16]+'-'+boot[16:20]+'-'+boot[20:]
 selected,source_pin=selected_source();result['selected_application']=selected;result['selection_pin']=source_pin
 command='tasks' if ACTION=='tasks' else 'inspect'
 inspection_response=ctl(command,[command,PACKAGE,'--user','0'])
 inspection=inspection_response['inspection']
 assert inspection['package']==PACKAGE and inspection['user']==0
 assert inspection_response['host_pid']==inspection['epoch']['cell_host_pid']
 assert inspection['epoch']['boot_id']==result['guest_boot_id']
 if EXPECTED is not None:assert inspection==EXPECTED
 result['inspection_response']=inspection_response
 if ACTION=='launch':
  assert EXPECTED is not None
  component=selected['preferred_manifest_component']
  assert component==COMPONENT and selected['runtime_plan_application_binding']['launch']=={'component':component,'specification':None}
  catalog=ctl('catalog',['applications','--user','0'])
  matches=[v for v in catalog['applications'] if v['package']==PACKAGE and v['component']==component]
  assert len(matches)==1 and catalog['host_pid']==inspection['epoch']['cell_host_pid']
  response=ctl('launch',['launch',PACKAGE,'--component',component,'--user','0'])
  assert response['inspection']==inspection and response['host_pid']==inspection['epoch']['cell_host_pid']
 if ACTION=='focus':
  setting=subprocess.run(['/usr/bin/gsettings','get','org.gnome.desktop.wm.keybindings','close'],env=env,capture_output=True,timeout=3,check=True)
  assert len(setting.stdout)<=4096 and len(setting.stderr)<=4096
  result['normal_close_keybinding']=setting.stdout.decode().strip()
 result['guest_monotonic_ns_start']=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
 result['journal']=journal(p,'(focus|key|frame)',512)
 result['window_journal']=journal(p,'window',512)
 assert props()==p
 for path,proof in [(UNIT_PATH,unit),('/usr/bin/droidloom-wayland',presenter),('/usr/bin/droidloomctl',client)]:
  assert F(os.stat(path,follow_symlinks=False))==proof['identity']
 row_after,pin_after=selected_source();assert row_after==selected and pin_after==source_pin
 result['guest_monotonic_ns_end']=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
 result['success']=True
except BaseException as error:
 result['error']=(type(error).__name__+': '+str(error))[:1024]
finally:
 result['exchange_ended_ns']=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
 print(json.dumps(result,separators=(',',':')))
"""

def lifecycle_probe(authority, action, package, inputs, deadline, expected=None, component=None):
    need(action in ("tasks", "focus", "launch"), "unsupported lifecycle verb")
    b = authority.binding
    authority.validate()
    need(b["ssh_port"] is not None and b["fresh_client_key"] is not None, "explicit fresh guest SSH required")
    for pin in (b["fresh_client_key"], b["known_hosts"]): read_file(pin["path"], pin, limit=16384)
    read_file(b["ssh_tool"]["path"], b["ssh_tool"], limit=64*1024*1024)
    command = ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-oControlMaster=no", "-oControlPath=none",
               "-oBatchMode=yes", "-oIdentitiesOnly=yes", "-oIdentityAgent=none",
               "-oPasswordAuthentication=no", "-oKbdInteractiveAuthentication=no",
               "-oPreferredAuthentications=publickey", "-oStrictHostKeyChecking=yes",
               "-oUserKnownHostsFile="+b["known_hosts"]["path"], "-oGlobalKnownHostsFile=/dev/null",
               "-oConnectTimeout=3", "-oConnectionAttempts=1", "-oLogLevel=ERROR",
               "-i", b["fresh_client_key"]["path"], "-p", str(b["ssh_port"]),
               "alex@127.0.0.1", "/usr/bin/python3", "-I", "-"]
    values = {"ACTION": action, "PACKAGE": package, "EXPECTED": expected, "COMPONENT": component,
              "SELECTION_PIN": inputs["selection"], "CLIENT_PIN": b["inspection_client"],
              "PRESENTER_PIN": b["presenter"], "UNIT_PIN": b["presenter_unit"]}
    fixed = "".join(key+"="+repr(value)+"\n" for key, value in values.items())
    started = time.monotonic_ns()
    # One global owner deadline, with the original broker's bounded commands.
    # Closing this SSH transport is never a request to kill or clean up a task.
    raw = bounded_subprocess(command, (fixed+GUEST_LIFECYCLE).encode(),
                             min(deadline, time.monotonic()+290))
    value = json.loads(raw)
    value["host_collection_started_monotonic_ns"] = started
    value["host_collection_finished_monotonic_ns"] = time.monotonic_ns()
    return value

def checked_lifecycle_probe(value, authority, inputs, package, expected=None):
    need(value["schema"] == "p4-native-lifecycle-observation-v1"
         and value["success"] is True and value["guest_clock"] == "CLOCK_MONOTONIC",
         "live guest exchange failed: " + str(value.get("error", ""))[:512])
    value["presenter"] = validate_presenter_identity(value, authority.binding)
    response = actual_control(value, "tasks" if value["action"] == "tasks" else "inspect", expected)
    need(value["inspection_response"] == response, "duplicated actual inspection response differs")
    inspection = response["inspection"]
    need(value["guest_boot_id"] == inspection["epoch"]["boot_id"], "actual guest/Android boot differs")
    if expected is not None: need(inspection == expected, "actual installed identity or runtime epoch changed")
    pin = value["selection_pin"]
    need(all(pin[k] == inputs["selection"][k] for k in ("path", "bytes", "sha256")),
         "actual source selection pin differs")
    selected_application(value["selected_application"], inspection, inputs, package)
    authority.validate()
    return inspection


def lifecycle_exchange(args, authority, qmp, result, deadline):
    prepared, _ = json_file(authority.binding["original"]["prepared"]["path"],
                            authority.binding["original"]["prepared"])
    inputs = fresh_lifecycle_inputs(prepared, args.package)
    result.update({"schema": "p4-qmp-application-lifecycle-v1", "package": args.package,
                   "scope": "fresh_isolated_public_apk_guest", "source_inputs": inputs,
                   "exchanges": {}, "exchange_receipts": {}, "close_observed": False,
                   "reopen_observed": False, "fresh_task_proven": False,
                   "common_gate_accepted": False, "data_preservation_qualified": False,
                   "application_business_accepted": False, "business_pending": True})

    def record(name, action, expected=None, component=None):
        need(time.monotonic() < deadline, "lifecycle deadline reached")
        value = lifecycle_probe(authority, action, args.package, inputs, deadline, expected, component)
        # Persist the actual response, including a launch that later failed a
        # check, before any next mutating operation. Never retry a launch.
        result["exchanges"][name] = value
        result["exchange_receipts"][name] = write_json(authority.root, args.name+"-"+name+".json", value)
        checked_lifecycle_probe(value, authority, inputs, args.package, expected)
        return value

    initial = record("initial", "tasks")
    baseline = actual_tasks(initial)
    expected = baseline["application"]
    need(not baseline["tasks"], "selected package already has tasks; leave them untouched")
    component = selected_application(initial["selected_application"], expected, inputs, args.package)
    result["expected_installed_identity"] = expected
    result["requested_component"] = component

    launched = record("launch", "launch", expected, component)
    event = actual_launch_event(launched, expected)
    event["inspection"] = expected
    need(event["presenter"] == initial["presenter"], "presenter changed during launch")
    result["actual_launch_event"] = event
    running = record("launched-tasks", "tasks", expected)
    listed = actual_tasks(running, expected)
    need(any(t["task"] == event["binding"]["task"] and t["display"] == 0 and t["visible"]
             for t in listed["tasks"]), "launch binding is absent from the actual selected package task list")
    result["screen_launched"] = capture(qmp, authority.root, args.name+"-launched")

    def focused(name, launch):
        for attempt in range(8):
            value = record(name+"-"+str(attempt), "focus", expected)
            need(value["presenter"] == initial["presenter"], "original presenter changed")
            need(value["normal_close_keybinding"] == "['<Alt>F4']", "normal desktop close binding differs")
            try:
                created = created_window(launch, value)
                focus = validate_focus(launch, value, maximum_launch_age_ns=LIFECYCLE_SECONDS*1_000_000_000)
                feedback = presented_feedback(launch, value)
                require_observation(feedback["observed"], "actual presented callback has not arrived")
                return value, created, focus, feedback
            except NotReady:
                if attempt == 7: raise
                need(time.monotonic()+.15 < deadline, "lifecycle observation deadline")
                time.sleep(.15)
        raise Rejected("bounded focus observation ended")

    before, creation, focus, feedback = focused("before-close", event)
    result["window_created"] = creation
    result["focus_before_normal_close"] = focus
    result["sampled_wp_presentation_feedback"] = feedback
    # One fixed OS gesture on the presently authenticated focused window. There
    # is no task ID/object ID close API, control socket, or synthetic denial.
    original_guard = qmp.guard
    def close_guard():
        original_guard()
        need(time.monotonic_ns()-before["host_collection_finished_monotonic_ns"] < 1_000_000_000,
             "actual focus became stale before the normal OS close gesture")
    qmp.guard = close_guard
    result["normal_close_request_attempted"] = True
    try:
        result["normal_close_qmp_reply"] = qmp.command("input-send-event", {"events": normal_close_events()})
        result["normal_close_qmp_acknowledged"] = True
    finally:
        qmp.guard = original_guard
    for attempt in range(8):
        after = record("after-close-"+str(attempt), "tasks", expected)
        need(after["presenter"] == initial["presenter"], "presenter changed after normal close")
        try:
            result["normal_close_evidence"] = closed_window(event, after, creation, before["guest_monotonic_ns_end"])
            break
        except NotReady:
            if attempt == 7: raise
            need(time.monotonic()+.15 < deadline, "close observation deadline")
            time.sleep(.15)
    result["close_observed"] = True
    result["screen_closed"] = capture(qmp, authority.root, args.name+"-closed")

    reopened = record("reopen", "launch", expected, component)
    reopen = actual_launch_event(reopened, expected)
    reopen["inspection"] = expected
    result["actual_reopen_event"] = reopen
    need(reopen["presenter"] == initial["presenter"]
         and reopen["binding"]["task"] != event["binding"]["task"],
         "reopen did not yield a distinct actual task in the same presenter generation")
    running_again = record("reopened-tasks", "tasks", expected)
    again = actual_tasks(running_again, expected)
    need(any(t["task"] == reopen["binding"]["task"] and t["display"] == 0 and t["visible"]
             for t in again["tasks"]), "reopened binding is absent from actual package tasks")
    observed, second_creation, second_focus, second_feedback = focused("reopened-focus", reopen)
    need(second_creation["created"]["creation_sequence"] > creation["created"]["creation_sequence"],
         "reopen has no later actual native window creation")
    result["reopened_window"] = second_creation
    result["reopened_focus"] = second_focus
    result["reopened_presented_feedback"] = second_feedback
    result["reopen_observed"] = True
    result["screen_reopened"] = capture(qmp, authority.root, args.name+"-reopened")
    result["observation_limitations"] = [
        "Before/after task absence plus native creation is not exclusive Android launch causality.",
        "Screenshots show the actual guest console; pixel-to-task identity and content are unqualified.",
        "Close/reopen alone does not verify retained application data or any complete common/business gate."]
    authority.validate()

def operation(args):
    need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", args.name), "invalid capture name")
    authority = Authority(args.binding, args.binding_sha256)
    root = authority.root
    lockdir = directory(root, private=True)
    lock = os.open("controller.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=lockdir)
    os.close(lockdir)
    result = {"schema": "p4-qmp-evidence-v1", "action": args.action, "binding": authority.pin,
              "guest_qualified": False, "production_ready": False, "android_input_consumed": False,
              "application_business_accepted": False, "task_first_frame_qualified": False}
    qmp = None
    try:
        need(stat.S_ISREG(os.fstat(lock).st_mode) and os.fstat(lock).st_nlink == 1
             and os.fstat(lock).st_uid == os.fstat(lock).st_gid == 0
             and stat.S_IMODE(os.fstat(lock).st_mode) == 0o600, "unsafe evidence lock")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        seconds = LIFECYCLE_SECONDS if args.action == "lifecycle" else 28
        if args.action == "lifecycle":
            need(authority.binding["expires_boottime"]-time.clock_gettime(time.CLOCK_BOOTTIME) > seconds+16,
                 "the original owner has insufficient lifetime for one bounded lifecycle exchange")
        deadline = time.monotonic()+seconds
        qmp = Qmp(authority.run/"qmp.sock", authority.peer, deadline, authority.validate)
        status = qmp.command("query-status")
        need(status.get("running") is True and status.get("status") == "running", "original guest is not running")
        if args.action == "lifecycle":
            lifecycle_exchange(args, authority, qmp, result, deadline)
        else:
            result["screen_before"] = capture(qmp, root, args.name+"-before")
            event = event_pin = before = None
            if getattr(args, "event", None):
                need(getattr(args, "event_sha256", None), "event SHA is required")
                event, event_pin = launch_event(args.event, args.event_sha256)
                before = focus_probe(authority, event)
                result.update({"launch_event": event_pin, "native_observation_before": before,
                               "sampled_wp_presentation_feedback": presented_feedback(event, before)})
            if args.action == "key":
                need(event is not None and before is not None, "key requires the original launch event")
                need(result["sampled_wp_presentation_feedback"]["observed"],
                     "no actual presented callback for this task before input")
                focus = validate_focus(event, before)
                result.update({"launch_event": event_pin, "focus_before": before, "focus_binding": focus, "key": args.key})
                authority.validate()
                need(time.monotonic_ns()-before["host_collection_finished_monotonic_ns"] < 1_000_000_000,
                     "focus probe became stale before key request")
                events = [{"type":"key","data":{"down":down,"key":{"type":"qcode","data":args.key}}} for down in (True,False)]
                qmp.command("input-send-event", {"events": events})
                result["qmp_paired_key_request_acknowledged"] = True
                result["screen_after"] = capture(qmp, root, args.name+"-after")
                after = focus_probe(authority, event)
                result["focus_after"] = after
                result["actual_wayland_key_pair_observed"] = wayland_key_pair(before, after, event, args.key)
                need(result["actual_wayland_key_pair_observed"], "QMP ACK lacked the matching actual Wayland key pair")
        authority.validate()
        result["success"] = True
    except BaseException as error:
        result["success"] = False
        result["error"] = (type(error).__name__ + ": " + str(error))[:1024]
    finally:
        if qmp is not None: qmp.close()
        authority.close();os.close(lock)
    pin = write_json(root, args.name+".json", result)
    return pin, result["success"]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("bind")
    for name in ("run-directory","unit","invocation","fixture","fixture-sha256","host-stage","host-stage-sha256","output"):
        p.add_argument("--"+name, required=True)
    for action in ("capture", "key", "lifecycle"):
        p = sub.add_parser(action)
        for name in ("binding","binding-sha256","name"):
            p.add_argument("--"+name, required=True)
        if action == "lifecycle":
            p.add_argument("--package", required=True)
        else:
            p.add_argument("--event", required=action=="key")
            p.add_argument("--event-sha256", required=action=="key")
            if action == "key":
                p.add_argument("--key", choices=sorted(KEYS), required=True)
    args = parser.parse_args()
    need(os.geteuid() == os.getegid() == 0, "requires an existing root controller")
    script = Path(__file__).absolute()
    need(ROOT in script.parents, "execute only the root-protected imported controller")
    read_file(str(script), limit=512*1024)
    if args.action == "bind":
        print(json.dumps({"binding": bind(args), "connected_to_qmp": False}))
        return 0
    pin, ok = operation(args)
    print(json.dumps({"receipt": pin, "success": ok, "production_ready": False}))
    return 0 if ok else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Rejected, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps({"success":False,"error":(type(error).__name__+": "+str(error))[:1024],"production_ready":False}), file=sys.stderr)
        sys.exit(1)
