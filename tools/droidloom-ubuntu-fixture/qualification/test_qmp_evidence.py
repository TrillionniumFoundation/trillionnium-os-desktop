#!/usr/bin/env python3
"""Offline protocol tests. The server below is Python, never a QEMU or VM."""
import array
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import struct
import tempfile
import time
import unittest

spec = importlib.util.spec_from_file_location("qmp_evidence", Path(__file__).with_name("qmp_evidence.py"))
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)

class PeerServer:
    def __init__(self, directory, behavior="normal"):
        self.path = Path(directory) / "synthetic-control.sock"
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.path))
        self.listener.listen()
        self.pid = os.fork()
        if self.pid == 0:
            try:
                connection, _ = self.listener.accept()
                self.listener.close()
                connection.sendall(b'{"QMP":{"version":{"qemu":{"major":10,"minor":2,"micro":1}}}}\n')
                if behavior == "oversized":
                    connection.sendall(b"x"*65537+b"\n")
                received = None
                buffer = bytearray()
                while True:
                    raw, control, _, _ = connection.recvmsg(8192, socket.CMSG_SPACE(16), socket.MSG_CMSG_CLOEXEC)
                    if not raw:
                        break
                    for level, kind, data in control:
                        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                            values = array.array("i");values.frombytes(data[:len(data)//values.itemsize*values.itemsize])
                            assert len(values) == 1 and received is None
                            received = values[0]
                    buffer.extend(raw)
                    while b"\n" in buffer:
                        line, _, tail = buffer.partition(b"\n");buffer = bytearray(tail)
                        request = json.loads(line)
                        name = request["execute"]
                        reply = {}
                        if name == "add-fd":
                            assert received is not None
                            reply = {"fdset-id": 3, "fd": received}
                        elif name == "screendump":
                            assert received is not None and request["arguments"] == {"filename":"/dev/fdset/3","format":"ppm"}
                            os.ftruncate(received, 0)
                            os.write(received, b"P6\n2 1\n255\n"+bytes([255,0,0,0,255,0]))
                        elif name == "remove-fd":
                            assert request["arguments"] == {"fdset-id":3,"fd":received}
                            os.close(received);received=None
                        elif name == "input-send-event":
                            assert request["arguments"] == {"events":[
                                {"type":"key","data":{"down":True,"key":{"type":"qcode","data":"tab"}}},
                                {"type":"key","data":{"down":False,"key":{"type":"qcode","data":"tab"}}}]}
                        elif name not in ("qmp_capabilities", "query-status"):
                            raise AssertionError(name)
                        connection.sendall((json.dumps({"return":reply,"id":request["id"]})+"\n").encode())
                if received is not None:os.close(received)
                connection.close()
                os._exit(0)
            except BaseException:
                os._exit(72)
        self.listener.close()
    def finish(self, expected=0):
        end = time.monotonic()+3
        while time.monotonic()<end:
            pid, state = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                self.pid=None
                if expected is not None:
                    assert os.waitstatus_to_exitcode(state)==expected, state
                return
            time.sleep(.01)
        os.kill(self.pid, signal.SIGKILL)
        os.waitpid(self.pid, 0);self.pid=None
        raise AssertionError("offline server did not retire")
    def __del__(self):
        if getattr(self, "pid", None):
            with contextlib.suppress(ProcessLookupError):os.kill(self.pid, signal.SIGKILL)
            with contextlib.suppress(ChildProcessError):os.waitpid(self.pid, 0)

class EvidenceTests(unittest.TestCase):
    def test_actual_credentials_and_rights_preserve_original_file(self):
        with tempfile.TemporaryDirectory() as directory:
            server = PeerServer(directory)
            client = q.Qmp(server.path, (server.pid, os.getuid(), os.getgid()), time.monotonic()+5)
            legacy = struct.unpack("3i", client.sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            # This listener was born in the parent, while actual message sender is the child.
            self.assertEqual(legacy[0], os.getpid())
            self.assertNotEqual(legacy[0], server.pid)
            leaf = Path(directory)/"image.ppm"
            fd = os.open(leaf,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            original=q.node(os.fstat(fd))
            added=client.command("add-fd",{"opaque":"test"},fd)
            client.command("screendump",{"filename":"/dev/fdset/3","format":"ppm"})
            client.command("remove-fd",added)
            os.fsync(fd)
            self.assertEqual(q.node(os.fstat(fd)),original)
            self.assertEqual(q.ppm(leaf.read_bytes())["pixel_bytes"],6)
            self.assertEqual(leaf.read_bytes()[-6:],bytes([255,0,0,0,255,0]))
            client.command("input-send-event",{"events":[
                {"type":"key","data":{"down":True,"key":{"type":"qcode","data":"tab"}}},
                {"type":"key","data":{"down":False,"key":{"type":"qcode","data":"tab"}}}]})
            with self.assertRaises(q.Rejected):client.command("system_powerdown")
            with self.assertRaises(q.Rejected):client.command("cont")
            client.close();os.close(fd);server.finish()
    def test_wrong_actual_sender_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            server=PeerServer(directory)
            with self.assertRaises(q.Rejected):
                q.Qmp(server.path,(os.getpid(),os.getuid(),os.getgid()),time.monotonic()+2)
            server.finish(expected=None)
    def test_incomplete_or_oversized_ppm_is_rejected(self):
        good=b"P6\n2 1\n255\n"+bytes(range(6))
        self.assertEqual(q.ppm(good)["width"],2)
        for bad in [good[:-1],good+b"\0",good.replace(b"255",b"256"),
                    b"P6\n4097 1\n255\n"+b"x"*3,b"P3\n2 1\n255\n"+b"x"*6]:
            with self.assertRaises(q.Rejected):q.ppm(bad)
    def test_qmp_line_and_absolute_deadline_are_bounded(self):
        a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        a.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
        obj=q.Qmp.__new__(q.Qmp)
        obj.sock=a;obj.peer=(os.getpid(),os.getuid(),os.getgid())
        obj.deadline=time.monotonic()+1;obj.buf=bytearray();obj.count=0
        b.sendall(b"x"*65537+b"\n")
        with self.assertRaises(q.Rejected):obj.line()
        obj.deadline=time.monotonic()-1;obj.buf=bytearray()
        with self.assertRaises(q.Rejected):obj.line()
        a.close();b.close()
    def test_focus_is_actual_pid_scoped_and_zero_revokes_it(self):
        event={"guest_boot_id":"01234567-89ab-cdef-0123-456789abcdef","guest_monotonic_ns_end":1_000_000_000,
               "epoch":{"boot_id":"01234567-89ab-cdef-0123-456789abcdef"},"binding":{"object":7}}
        def row(text,stamp):
            return {"_PID":"55","_UID":"1000","_SYSTEMD_USER_UNIT":"droidloom-production-desktop.service",
                    "_SYSTEMD_INVOCATION_ID":"a"*32,"_BOOT_ID":"0123456789abcdef0123456789abcdef",
                    "__MONOTONIC_TIMESTAMP":str(stamp),"MESSAGE":text}
        obs={"guest_boot_id":"01234567-89ab-cdef-0123-456789abcdef","guest_monotonic_ns_start":1_100_000_000,
             "guest_monotonic_ns_end":1_200_000_000,
             "inspection_response":{"inspection":{"epoch":{"boot_id":"01234567-89ab-cdef-0123-456789abcdef"}}},
             "presenter":{"pid":55,"invocation_id":"a"*32,"start_ticks":1,"clk_tck":100},
             "journal":[row("Droidloom focus trace: pid=55 object=7 serial=99 observed_ns=1000000000 focus=enter",1000000)]}
        self.assertEqual(q.validate_focus(event,obs)["object"],7)
        obs["inspection_response"]["inspection"]["epoch"]={"boot_id":"another"}
        with self.assertRaises(q.Rejected):q.validate_focus(event,obs)
        obs["inspection_response"]["inspection"]["epoch"]=event["epoch"].copy()
        obs["journal"].append(row("Droidloom focus trace: pid=55 object=0 serial=100 observed_ns=1100000000 focus=leave",1100000))
        with self.assertRaises(q.Rejected):q.validate_focus(event,obs)
        obs["journal"].pop()
        obs["journal"][0]["_PID"]="56"
        with self.assertRaises(q.Rejected):q.validate_focus(event,obs)
    def test_launch_or_commit_is_not_presented_feedback(self):
        event={"guest_boot_id":"01234567-89ab-cdef-0123-456789abcdef","guest_monotonic_ns_start":900000000,"binding":{"object":7}}
        row={"_PID":"55","_UID":"1000","_SYSTEMD_USER_UNIT":"droidloom-production-desktop.service",
                    "_SYSTEMD_INVOCATION_ID":"a"*32,"_BOOT_ID":"0123456789abcdef0123456789abcdef",
             "__MONOTONIC_TIMESTAMP":"1100000","MESSAGE":
             "Droidloom frame trace: pid=55 seq=1 stage=commit object=7 frame=1 buffer=9 observed_ns=1100000000 display_ns=1050000000 refresh_ns=16000000 display_sequence=1 dropped_total=0"}
        obs={"guest_boot_id":"01234567-89ab-cdef-0123-456789abcdef","guest_monotonic_ns_end":1200000000,
             "presenter":{"pid":55,"invocation_id":"a"*32},"journal":[row]}
        self.assertFalse(q.presented_feedback(event,obs)["observed"])
        row["MESSAGE"]=row["MESSAGE"].replace("stage=commit","stage=presented")
        proof=q.presented_feedback(event,obs)
        self.assertTrue(proof["observed"])
        self.assertFalse(proof["first_ever_frame_proven"])
        self.assertFalse(proof["pixel_to_task_binding_proven"])
        event["binding"]["object"]=8
        self.assertFalse(q.presented_feedback(event,obs)["observed"])


    def test_identity_uses_original_unit_journal_and_actual_public_inode(self):
        import copy
        boot = "01234567-89ab-cdef-0123-456789abcdef"
        expected = {"path":"usr/bin/droidloom-wayland","size":4000,"sha256":"b"*64,"mode":0o755}
        expected_unit = {"path":"usr/lib/systemd/user/droidloom-production-desktop.service",
                         "size":571,"sha256":"c"*64,"mode":0o644}
        inode = {"dev":5,"ino":7,"mode":0o100755,"uid":0,"gid":0,"nlink":1,"size":4000,
                 "mtime_ns":1000,"ctime_ns":1000}
        unit_inode = dict(inode,ino=8,mode=0o100644,size=571)
        measured = {"schema":"p4-presenter-self-identity-v1","pid":55,"uid":1000,"gid":1000,
                    "start_ticks":1,"clk_tck":100,"observed_ns":20_000_000,
                    "invocation_id":"a"*32,"elf_sha256":"b"*64,"executable":inode,
                    "selinux":"u:system_r:droidloom_presenter:s0","apparmor":"unconfined"}
        row = {"_PID":"55","_UID":"1000","_SYSTEMD_USER_UNIT":"droidloom-production-desktop.service",
               "_SYSTEMD_INVOCATION_ID":"a"*32,"_BOOT_ID":boot.replace("-",""),
               "__MONOTONIC_TIMESTAMP":"20001","__CURSOR":"actual-journal-cursor"}
        row["MESSAGE"]="Droidloom identity trace: "+json.dumps(measured)
        props = {"Id":"droidloom-production-desktop.service","MainPID":"55","ExecMainPID":"55",
                 "InvocationID":"a"*32,"ActiveState":"active","SubState":"running",
                 "FragmentPath":"/"+expected_unit["path"],"DropInPaths":"","NeedDaemonReload":"no",
                 "Transient":"no","Type":"notify","NotifyAccess":"main","NoNewPrivileges":"yes"}
        observation={"unit":props,"public_presenter":{"path":"/"+expected["path"],"bytes":4000,
                     "sha256":"b"*64,"identity":inode},
                     "public_unit":{"path":"/"+expected_unit["path"],"bytes":571,
                     "sha256":"c"*64,"identity":unit_inode},
                     "guest_boot_id":boot,"guest_monotonic_ns_end":50_000_000,"identity_journal":[row]}
        binding={"presenter":expected,"presenter_unit":expected_unit}
        accepted=q.validate_presenter_identity(observation,binding)
        self.assertEqual(accepted["executable"],inode)
        self.assertEqual(accepted["start_ticks"],1)
        self.assertEqual(accepted["identity_journal_cursor"],"actual-journal-cursor")
        mutations=[
            lambda x:x["unit"].update(MainPID="56"),
            lambda x:x["unit"].update(ExecMainPID="56"),
            lambda x:x["unit"].update(FragmentPath="/home/alex/changed.service"),
            lambda x:x["unit"].update(DropInPaths="/run/user/1000/service.d/override.conf"),
            lambda x:x["unit"].update(NeedDaemonReload="yes"),
            lambda x:x["unit"].update(Transient="yes"),
            lambda x:x["unit"].update(InvocationID="d"*32),
            lambda x:x["identity_journal"][0].update(_PID="56"),
            lambda x:x["identity_journal"][0].pop("_SYSTEMD_INVOCATION_ID"),
            lambda x:x["identity_journal"][0].update(_SYSTEMD_INVOCATION_ID="d"*32),
            lambda x:x["identity_journal"][0].update(_BOOT_ID="0"*32),
            lambda x:x["public_presenter"]["identity"].update(uid=1000),
            lambda x:x["public_presenter"]["identity"].update(ino=99),
            lambda x:x["public_presenter"].update(sha256="d"*64),
            lambda x:x["public_unit"].update(sha256="d"*64),
            lambda x:x["identity_journal"].append(copy.deepcopy(x["identity_journal"][0])),
            lambda x:x.update(guest_monotonic_ns_end=10_000_000),
        ]
        for index,mutate in enumerate(mutations):
            with self.subTest(index=index):
                bad=copy.deepcopy(observation);mutate(bad)
                with self.assertRaises(q.Rejected):q.validate_presenter_identity(bad,binding)
        for key,value in [("elf_sha256","d"*64),("pid",56),("selinux","u:system_r:p4_linux_user_session_t:s0"),
                          ("observed_ns",60_000_000),("start_ticks",1000),("clk_tck",0)]:
            with self.subTest(body=key):
                bad=copy.deepcopy(observation);body=copy.deepcopy(measured);body[key]=value
                bad["identity_journal"][0]["MESSAGE"]="Droidloom identity trace: "+json.dumps(body)
                with self.assertRaises(q.Rejected):q.validate_presenter_identity(bad,binding)
        bad=copy.deepcopy(observation);body=copy.deepcopy(measured);body["executable"]["nlink"]=True
        bad["identity_journal"][0]["MESSAGE"]="Droidloom identity trace: "+json.dumps(body)
        with self.assertRaises(q.Rejected):q.validate_presenter_identity(bad,binding)

    def test_owned_probe_is_bounded_and_reaped(self):
        with self.assertRaises(q.Rejected):
            q.bounded_subprocess(["/usr/bin/python3","-c","import sys;sys.stdout.write('x'*10000)"],b"",time.monotonic()+2,100)
        with self.assertRaises(q.Rejected):
            q.bounded_subprocess(["/usr/bin/python3","-c","import time;time.sleep(30)"],b"",time.monotonic()+.1,100)

if __name__=="__main__":
    unittest.main(verbosity=2)
