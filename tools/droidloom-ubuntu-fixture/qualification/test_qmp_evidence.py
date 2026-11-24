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
        event={"guest_boot_id":"boot","guest_monotonic_ns_end":1_000_000_000,
               "epoch":{"boot_id":"boot"},"binding":{"object":7}}
        def row(text,stamp):
            return {"_PID":"55","_UID":"1000","_SYSTEMD_USER_UNIT":"droidloom-production-desktop.service",
                    "__MONOTONIC_TIMESTAMP":str(stamp),"MESSAGE":text}
        obs={"guest_boot_id":"boot","guest_monotonic_ns_start":1_100_000_000,
             "guest_monotonic_ns_end":1_200_000_000,
             "inspection_response":{"inspection":{"epoch":{"boot_id":"boot"}}},
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
        event={"guest_boot_id":"boot","guest_monotonic_ns_start":900000000,"binding":{"object":7}}
        row={"_PID":"55","_UID":"1000","_SYSTEMD_USER_UNIT":"droidloom-production-desktop.service",
             "__MONOTONIC_TIMESTAMP":"1100000","MESSAGE":
             "Droidloom frame trace: pid=55 seq=1 stage=commit object=7 frame=1 buffer=9 observed_ns=1100000000 display_ns=1050000000 refresh_ns=16000000 display_sequence=1 dropped_total=0"}
        obs={"guest_boot_id":"boot","guest_monotonic_ns_end":1200000000,
             "presenter":{"pid":55,"invocation_id":"a"*32},"journal":[row]}
        self.assertFalse(q.presented_feedback(event,obs)["observed"])
        row["MESSAGE"]=row["MESSAGE"].replace("stage=commit","stage=presented")
        proof=q.presented_feedback(event,obs)
        self.assertTrue(proof["observed"])
        self.assertFalse(proof["first_ever_frame_proven"])
        self.assertFalse(proof["pixel_to_task_binding_proven"])
        event["binding"]["object"]=8
        self.assertFalse(q.presented_feedback(event,obs)["observed"])

    def test_owned_probe_is_bounded_and_reaped(self):
        with self.assertRaises(q.Rejected):
            q.bounded_subprocess(["/usr/bin/python3","-c","import sys;sys.stdout.write('x'*10000)"],b"",time.monotonic()+2,100)
        with self.assertRaises(q.Rejected):
            q.bounded_subprocess(["/usr/bin/python3","-c","import time;time.sleep(30)"],b"",time.monotonic()+.1,100)

if __name__=="__main__":
    unittest.main(verbosity=2)
