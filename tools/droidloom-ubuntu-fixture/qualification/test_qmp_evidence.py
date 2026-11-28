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


class LifecycleTests(unittest.TestCase):
    def fresh(self, split_apps=26):
        names=sorted(q.SELECTED_PACKAGES)
        files=[]
        for i,name in enumerate(names):
            parts=[None,"config.arm64_v8a"] if i<split_apps else [None]
            for split in parts:
                sha=q.digest((name+str(split)).encode())
                files.append({"guest_path":q.PUBLIC_STAGE+"/"+sha+".apk","package":name,"split":split,
                              "source":{"path":"/source/"+sha+".apk","bytes":100,"sha256":sha}})
        pins={}
        for key,name in (("execution","selected39-execution.json"),("selection","selected39-source-selection.json"),
                         ("source_receipt","selected39-signature-receipt.json"),("gate_registry","app-release-gates.json")):
            pin={"path":q.PUBLIC_STAGE+"/"+name,"bytes":27878 if key=="gate_registry" else 200,
                 "sha256":q.REGISTRY_SHA256 if key=="gate_registry" else q.digest(name.encode())}
            pins[key]=pin
            files.append({"guest_path":pin["path"],"package":None,"split":None,
                          "source":dict(pin,path="/source/"+name)})
        staged={"schema":"droidloom.public-apks-staged.v1","original_userdata_imported":False,
                "package_count":39,"apk_file_count":39+split_apps,"applications_installed":0,"files":files,
                "applications":[{"package":name,"version_code":7} for name in names],
                "runtime_preparation_inputs":dict({k:v for k,v in pins.items() if k!="execution"},
                    required_gates={name:["common."+str(i) for i in range(6)] for name in names})}
        return {"schema":"droidloom.full-ubuntu-boot-prepared.v1","calibration_requested":False,
                "boot_phase":"android_runtime","public_apk_import":staged},names[0]

    def test_lifecycle_requires_exact_fresh_import_and_original_registry(self):
        import copy
        prepared,package=self.fresh()
        inputs=q.fresh_lifecycle_inputs(prepared,package)
        self.assertEqual(len(inputs["apks"]),2)
        for mutate in [
            lambda x:x.update(calibration_requested=True),
            lambda x:x["public_apk_import"].update(original_userdata_imported=True),
            lambda x:x["public_apk_import"]["files"].pop(),
            lambda x:x["public_apk_import"]["files"][0].update(guest_path="/home/alex/arbitrary.apk"),
            lambda x:x["public_apk_import"]["runtime_preparation_inputs"]["gate_registry"].update(sha256="f"*64),
            lambda x:x["public_apk_import"]["runtime_preparation_inputs"]["required_gates"][package].pop(),
            lambda x:x["public_apk_import"].update(applications_installed=39)]:
            bad=copy.deepcopy(prepared);mutate(bad)
            with self.assertRaises(q.Rejected):q.fresh_lifecycle_inputs(bad,package)

    def test_lifecycle_counts_follow_exact_changed_split_sets(self):
        import copy
        for count in [0, 25, 27, 39]:
            prepared, package = self.fresh(count)
            inputs = q.fresh_lifecycle_inputs(prepared, package)
            self.assertEqual(len(inputs["apks"]), 1 if count == 0 else 2)
            for mutate in [
                lambda x: x["public_apk_import"].update(apk_file_count=39+count+1),
                lambda x: x["public_apk_import"].update(apk_file_count=q.MAX_APKS+1),
                lambda x: x["public_apk_import"]["files"][0].update(package="org.example.replacement"),
                lambda x: x["public_apk_import"]["files"][0].update(split="missing_base"),
                lambda x: x["public_apk_import"]["files"][0]["source"].update(bytes=q.MAX_APP_BYTES+1),
                lambda x: x["public_apk_import"]["applications"][0].update(package="org.example.replacement")]:
                bad = copy.deepcopy(prepared)
                mutate(bad)
                with self.assertRaises(q.Rejected):
                    q.fresh_lifecycle_inputs(bad, package)
        # A missing unrelated application's base must also fail this selected app's exchange.
        prepared, package = self.fresh()
        prepared["public_apk_import"]["files"][-5]["split"] = "unexpected_split"
        with self.assertRaises(q.Rejected):
            q.fresh_lifecycle_inputs(prepared, package)

    def facts(self):
        boot="01234567-89ab-cdef-0123-456789abcdef"
        presenter={"pid":55,"invocation_id":"a"*32,"start_ticks":1,"clk_tck":100}
        inspection={"package":"org.example.app","user":0,"uid":10042,"version_code":7,
                    "epoch":{"boot_id":boot,"cell_host_pid":100,"framework_host_pid":101,"framework_start_ticks":50},
                    "apks":[{"name":"base.apk","path":"/data/app/example/base.apk","bytes":100,"sha256":"c"*64}]}
        event={"package":inspection["package"],"inspection":inspection,"epoch":inspection["epoch"],
               "presenter":presenter,"guest_boot_id":boot,"guest_clock":"CLOCK_MONOTONIC",
               "guest_monotonic_ns_start":1_000_000_000,"guest_monotonic_ns_end":1_050_000_000,
               "binding":{"object":7,"composer_display":8,"android_display":0,"task":9}}
        def row(stage,sequence,stamp,task=9):
            value={"schema":"p4-presenter-window-event-v1","pid":55,"sequence":sequence,
                   "creation_sequence":2,"object":7,"surface":15,"package":inspection["package"],
                   "android_task":task,"observed_ns":stamp,"stage":stage}
            return {"_PID":"55","_UID":"1000","_SYSTEMD_USER_UNIT":"droidloom-production-desktop.service",
                    "_SYSTEMD_INVOCATION_ID":"a"*32,"_BOOT_ID":boot.replace("-",""),
                    "__MONOTONIC_TIMESTAMP":str(stamp//1000+1),"__CURSOR":"window-"+str(sequence),
                    "MESSAGE":q.WINDOW_PREFIX+json.dumps(value)}
        snapshot={"schema":"droidloom.application-task-snapshot.v1","application":inspection,
                  "listing_bytes":0,"listing_sha256":q.digest(b""),"tasks":[]}
        response={"ok":True,"state":"running","host_pid":100,"inspection":inspection,"diagnostics":json.dumps(snapshot)}
        observation={"presenter":presenter,"guest_boot_id":boot,"guest_monotonic_ns_end":2_000_000_000,
                     "commands":{"tasks":{"returncode":0,"started_ns":1_400_000_000,"ended_ns":1_500_000_000,"response":response}},
                     "window_journal":[row("created",2,1_010_000_000,None),row("bound",3,1_020_000_000)]}
        return event,observation,row

    def test_created_window_is_same_native_token_and_never_exclusive_launch_causality(self):
        import copy
        event,observation,row=self.facts()
        creation=q.created_window(event,observation)
        self.assertFalse(creation["exclusive_android_task_creation_proven"])
        self.assertEqual(creation["created"]["surface"],15)
        for mutate in [
            lambda o:o["window_journal"][0].update(_PID="56"),
            lambda o:o["window_journal"].append(row("created",4,1_100_000_000,None)),
            lambda o:o["window_journal"].pop(),
            lambda o:o["window_journal"].append(row("close_sent",4,1_100_000_000))]:
            bad=copy.deepcopy(observation);mutate(bad)
            with self.assertRaises(q.Rejected):q.created_window(event,bad)
        stale=copy.deepcopy(event);stale["guest_monotonic_ns_start"]=1_030_000_000
        with self.assertRaises(q.Rejected):q.created_window(stale,observation)

    def test_close_needs_actual_send_unmap_task_absence_and_same_epoch(self):
        import copy
        event,observation,row=self.facts()
        creation=q.created_window(event,observation)
        observation["window_journal"] += [row("close_sent",4,1_200_000_000),row("unmapped",5,1_210_000_000)]
        self.assertTrue(q.closed_window(event,observation,creation,1_100_000_000)["task_absence_observed"])
        only_sent=copy.deepcopy(observation);only_sent["window_journal"].pop()
        with self.assertRaises(q.Rejected):q.closed_window(event,only_sent,creation,1_100_000_000)
        still=copy.deepcopy(observation)
        snap=json.loads(still["commands"]["tasks"]["response"]["diagnostics"])
        snap["tasks"]=[{"task":9,"root_task":0,"display":0,"user":0,"name":event["package"],"visible":True,"top_activity":None}]
        still["commands"]["tasks"]["response"]["diagnostics"]=json.dumps(snap)
        with self.assertRaises(q.Rejected):q.closed_window(event,still,creation,1_100_000_000)
        stale=copy.deepcopy(observation)
        stale["commands"]["tasks"]["response"]["inspection"]["epoch"]["framework_start_ticks"]+=1
        with self.assertRaises(q.Rejected):q.closed_window(event,stale,creation,1_100_000_000)

    def test_selected_identity_requires_complete_pm_apks_and_bound_component(self):
        import copy
        event,_,_=self.facts();inspection=event["inspection"];package=event["package"]
        part={"sha256":"c"*64,"bytes":100,"split":None}
        inputs={"application":{"package":package,"version_code":7},"apks":[part]}
        component=package+"/Main"
        row={"package":package,"version_code":7,"material_files":[part],"preferred_manifest_component":component,
             "runtime_plan_application_binding":{"launch":{"component":component,"specification":None}}}
        self.assertEqual(q.selected_application(row,inspection,inputs,package),component)
        for mutate in [
            lambda x:x["apks"][0].update(sha256="d"*64),
            lambda x:x["apks"].append(dict(x["apks"][0],name="split_extra.apk")),
            lambda x:x.update(version_code=8),
            lambda x:x.update(user=10)]:
            bad=copy.deepcopy(inspection);mutate(bad)
            with self.assertRaises(q.Rejected):q.selected_application(row,bad,inputs,package)

    def test_only_fixed_os_close_gesture_and_closed_guest_program(self):
        events=q.normal_close_events()
        self.assertEqual([(v["data"]["key"]["data"],v["data"]["down"]) for v in events],
                         [("alt",True),("f4",True),("f4",False),("alt",False)])
        self.assertNotIn("alt",q.KEYS)
        self.assertNotIn("f4",q.KEYS)
        self.assertEqual(set(q.Qmp.ALLOWED),{"query-status","add-fd","screendump","remove-fd","input-send-event"})
        compile(q.GUEST_LIFECYCLE,"fixed guest lifecycle","exec")


if __name__=="__main__":
    unittest.main(verbosity=2)
