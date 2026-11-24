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
                 "expires_boottime": expires, "host_stage": stage_pin, "presenter": wayland[0], "inspection_client": client[0],
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
import hashlib,json,os,pathlib,stat,subprocess,time
assert os.getuid()==1000
env=os.environ.copy();env['XDG_RUNTIME_DIR']='/run/user/1000';env['DBUS_SESSION_BUS_ADDRESS']='unix:path=/run/user/1000/bus'
def props():
 r=subprocess.run(['/usr/bin/systemctl','--user','show','droidloom-production-desktop.service','--property=MainPID,InvocationID,ActiveState,SubState'],env=env,capture_output=True,timeout=2,check=True)
 return dict(x.split('=',1) for x in r.stdout.decode().splitlines() if '=' in x)
F=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_uid,x.st_gid,x.st_nlink,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
def elf(path,magic_link=False):
 fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|(0 if magic_link else os.O_NOFOLLOW))
 try:
  s=os.fstat(fd);assert stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and s.st_nlink==1 and s.st_size<=32*1024*1024 and not s.st_mode&0o6022
  h=hashlib.sha256()
  while True:
   x=os.read(fd,1024*1024)
   if not x:break
   h.update(x)
  assert F(os.fstat(fd))==F(os.stat(path))==F(s)
  return s,h.hexdigest()
 finally:os.close(fd)
start=time.clock_gettime_ns(time.CLOCK_MONOTONIC);boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip();p=props();pid=int(p['MainPID']);assert pid>1 and p['ActiveState']=='active'
def procstat():
 x=pathlib.Path('/proc/%d/stat'%pid).read_text();a=x[x.rfind(')')+2:].split();return int(a[19])
def context():
 return pathlib.Path('/proc/%d/attr/current'%pid).read_bytes().rstrip(b'\0\n').decode('ascii')
ticks=procstat();selinux=context();assert selinux=='u:system_r:droidloom_presenter:s0'
s,elf_sha=elf('/proc/%d/exe'%pid,True)
client_s,client_sha=elf('/usr/bin/droidloomctl')
assert client_sha==CLIENT_SHA and client_s.st_size==CLIENT_BYTES
inspection_run=subprocess.run(['/usr/bin/droidloomctl','--json','inspect',PACKAGE,'--user','0'],env=env,capture_output=True,timeout=4,check=True)
assert len(inspection_run.stdout)<=1048576 and len(inspection_run.stderr)<=1048576
inspection_response=json.loads(inspection_run.stdout)
assert inspection_response['ok'] is True and inspection_response['inspection']['package']==PACKAGE and inspection_response['inspection']['user']==0
assert F(os.stat('/usr/bin/droidloomctl'))==F(client_s)
r=subprocess.run(['/usr/bin/journalctl','--user','--no-pager','--boot','-u','droidloom-production-desktop.service','-o','json','--output-fields=__CURSOR,__MONOTONIC_TIMESTAMP,_PID,_UID,_SYSTEMD_USER_UNIT,_SYSTEMD_INVOCATION_ID,_SYSTEMD_USER_INVOCATION_ID,MESSAGE','--grep=^Droidloom (focus|key|frame) trace:','-n','512','_PID='+str(pid)],env=env,capture_output=True,timeout=3,check=True)
assert len(r.stdout)<=1048576
rows=[json.loads(x) for x in r.stdout.splitlines()]
assert props()==p and procstat()==ticks and context()==selinux and F(os.stat('/proc/%d/exe'%pid))==F(s)
end=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
print(json.dumps({'schema':'p4-native-focus-observation-v1','guest_clock':'CLOCK_MONOTONIC','guest_boot_id':boot,'guest_monotonic_ns_start':start,'guest_monotonic_ns_end':end,'presenter':{'pid':pid,'invocation_id':p['InvocationID'],'start_ticks':ticks,'clk_tck':os.sysconf('SC_CLK_TCK'),'elf_sha256':elf_sha,'elf_bytes':s.st_size,'elf_dev':s.st_dev,'elf_ino':s.st_ino,'selinux':selinux},'inspection_response':inspection_response,'inspection_stdout_sha256':hashlib.sha256(inspection_run.stdout).hexdigest(),'inspection_stdout_bytes':len(inspection_run.stdout),'journal':rows},separators=(',',':')))

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
               "alex@127.0.0.1", "/usr/bin/python3", "-"]
    started = time.monotonic_ns()
    client = b["inspection_client"]
    fixed = "PACKAGE=" + json.dumps(event["package"]) + "\nCLIENT_SHA=" + json.dumps(client["sha256"]) + "\nCLIENT_BYTES=" + str(client["size"]) + "\n"
    raw = bounded_subprocess(command, (fixed+GUEST_PROBE).encode(), time.monotonic()+8)
    finished = time.monotonic_ns()
    value = json.loads(raw)
    need(value["schema"] == "p4-native-focus-observation-v1" and value["guest_clock"] == "CLOCK_MONOTONIC",
         "invalid actual focus probe")
    p = value["presenter"]
    need(p["elf_sha256"] == b["presenter"]["sha256"] and p["elf_bytes"] == b["presenter"]["size"]
         and re.fullmatch("[0-9a-f]{32}", p["invocation_id"]), "actual presenter source or InvocationID differs")
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

def validate_focus(event, observation):
    need(observation["inspection_response"]["inspection"]["epoch"] == event["epoch"], "actual Android generation changed")
    need(event["guest_boot_id"] == observation["guest_boot_id"] and event["epoch"]["boot_id"] == observation["guest_boot_id"], "guest boot changed")
    start, end = observation["guest_monotonic_ns_start"], observation["guest_monotonic_ns_end"]
    need(type(start) is int and type(end) is int and 0 <= end-start <= 8_000_000_000, "unbounded focus observation")
    need(0 <= end-event["guest_monotonic_ns_end"] <= 30_000_000_000, "launch event is stale")
    p = observation["presenter"]
    if event.get("presenter") is not None:
        need(event["presenter"]["pid"] == p["pid"] and event["presenter"]["invocation_id"] == p["invocation_id"],
             "presenter changed since selected launch")
    current = None;last_enter = None;previous_time = 0
    need(len(observation["journal"]) <= 512, "journal bound exceeded")
    for row in observation["journal"]:
        need(row.get("_PID") == str(p["pid"]) and row.get("_UID") == "1000"
             and row.get("_SYSTEMD_USER_UNIT") == "droidloom-production-desktop.service", "foreign journal sender")
        t = int(row["__MONOTONIC_TIMESTAMP"])*1000
        need(t >= previous_time, "journal order changed");previous_time=t
        if t < p["start_ticks"]*1_000_000_000//p["clk_tck"]: continue
        if row.get("_SYSTEMD_USER_INVOCATION_ID") is not None:
            need(row["_SYSTEMD_USER_INVOCATION_ID"] == p["invocation_id"], "journal invocation differs")
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
    need(current == event["binding"]["object"] and last_enter is not None and end-last_enter <= 15_000_000_000,
         "no recent actual focus for this original task object")
    return {"object": current, "presenter_pid": p["pid"], "presenter_invocation": p["invocation_id"],
            "focus_observed_guest_monotonic_ns": last_enter, "launch_event_epoch": event["epoch"]}

def presented_feedback(event, observation):
    """Native sampled wp_presentation evidence, never a claim of the first ever frame."""
    need(event["guest_boot_id"] == observation["guest_boot_id"], "presentation guest boot differs")
    p = observation["presenter"]; found = []
    for row in observation["journal"]:
        need(row.get("_PID") == str(p["pid"]) and row.get("_UID") == "1000"
             and row.get("_SYSTEMD_USER_UNIT") == "droidloom-production-desktop.service", "foreign presentation journal")
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
        if row.get("_PID") != str(p["pid"]) or int(row["__MONOTONIC_TIMESTAMP"])*1000 < before["guest_monotonic_ns_end"]:
            continue
        m = KEY.fullmatch(row.get("MESSAGE", ""))
        if m and int(m[2]) == event["binding"]["object"] and int(m[4]) == KEYS[key] and int(m[5]) == 0:
            rows.append((int(m[1]), m[3]))
    return len(rows) == 2 and rows[0][1] == "Down" and rows[1] == (rows[0][0]+1, "Up")

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
        qmp = Qmp(authority.run/"qmp.sock", authority.peer, time.monotonic()+28, authority.validate)
        status = qmp.command("query-status")
        need(status.get("running") is True and status.get("status") == "running", "original guest is not running")
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
    for action in ("capture", "key"):
        p = sub.add_parser(action)
        for name in ("binding","binding-sha256","name"):
            p.add_argument("--"+name, required=True)
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
