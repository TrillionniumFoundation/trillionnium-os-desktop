#!/usr/bin/env python3
"""Own child/real socket/syscall fixtures; NEVER a genuine product Root grant.

Runs as the current UID. Tests the SAME tracer/parser scan, using an explicitly
fixture-only SCM_RIGHTS duplicate instead of production Root pidfd_getfd custody.
The production controller never accepts such a descriptor or a fake admin verdict.
"""
import array
import ctypes
import errno
import hashlib
import json
import mmap
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import struct
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(BASE/"support/ui"))
with tempfile.TemporaryDirectory(prefix="trill-issuer-kernel-source-") as _source_cache:
    _old_cache = sys.pycache_prefix
    try:
        sys.pycache_prefix = _source_cache
        from notes_fault_contract import Refused, digest, require
        from notes_fault_linux import HeldProcess, proc_identity, LIBC
        from notes_issuer_gate_linux import IssuerTrace, snapshot, pidfd_target
        from notes_issuer_gate_contract import IssuerTransaction
        from notes_issuer_gate_controller import scan_to_grant
        from test_notes_issuer_gate import original, encode
    finally:
        sys.pycache_prefix = _old_cache


def read_exact(stream,count):
    raw=bytearray()
    while len(raw)<count:
        value=stream.recv(count-len(raw))
        if not value: break
        raw.extend(value)
    return bytes(raw)


def process_binding(pid):
    value=proc_identity(pid); executable=Path(f"/proc/{pid}/exe").resolve(strict=True)
    return dict(pid=pid,start_ticks=value["start_ticks"],uid=value["uid"][0],gid=value["gid"][0],
                executable=str(executable),sha256=hashlib.sha256(executable.read_bytes()).hexdigest())


class Pollfd(ctypes.Structure):
    _fields_=[("fd",ctypes.c_int),("events",ctypes.c_short),("revents",ctypes.c_short)]


class Timespec(ctypes.Structure):
    _fields_=[("seconds",ctypes.c_long),("nanos",ctypes.c_long)]


def original_wait(stream,owner,events,end):
    remaining=end-time.monotonic()
    if remaining<=0: raise TimeoutError("own fixture natural request deadline")
    fds=(Pollfd*2)(Pollfd(stream.fileno(),events,0),Pollfd(owner,1,0))
    timeout=Timespec(int(remaining),int((remaining%1)*1e9))
    result=LIBC.syscall(ctypes.c_long(271),ctypes.byref(fds),ctypes.c_ulong(2),ctypes.byref(timeout),0,0)
    if result<0: raise OSError(ctypes.get_errno(),"own original ppoll")
    if result==0 or fds[1].revents: raise TimeoutError("own fixture owner/deadline")


def root_child(control,listener,shared,scenario):
    # Root is a ROLE NAME ONLY. Actual UID is retained and reported, not faked.
    stream,_=listener.accept(); listener.close()
    peer=struct.unpack("iII",stream.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
    owner=os.pidfd_open(peer[0]); done=threading.Event(); result={}
    def issuer():
        try:
            tid=threading.get_native_id()
            control.sendmsg([encode(dict(tid=tid,fd=stream.fileno(),owner_fd=owner,peer=list(peer)))],
                            [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array("i",[stream.fileno()]))])
            if scenario != "read-one": original_wait(stream,owner,1,time.monotonic()+5)
            first=stream.recv(1); end=time.monotonic()+.5
            rest=read_exact(stream,3); length=int.from_bytes(first+rest,"big")
            request=read_exact(stream,length)
            _,_,response=original()
            body=encode(response); result.update(request_sha256=digest(request),body_sha256=digest(body))
            original_wait(stream,owner,4,end)
            stream.sendall(len(body).to_bytes(4,"big"))
            original_wait(stream,owner,4,end)
            try:
                if scenario=="partial-body":
                    stream.sendall(body[:1]); stream.sendall(body[1:])
                else: stream.sendall(body)
                result["body_write_errno"]=None
            except OSError as error: result["body_write_errno"]=error.errno
            result["natural_deadline_still_live"]=time.monotonic()<end
        except BaseException as error: result["error"]=str(error)
        finally:
            done.set()
            control.sendall(encode(result)+b"\n")
            control.recv(1)  # Own parent alone releases fixture lifetime.
    thread=threading.Thread(target=issuer); thread.start()
    while thread.is_alive():
        count=struct.unpack("Q",shared[:8])[0]; shared[:8]=struct.pack("Q",count+1)
        time.sleep(.001)
    stream.close(); os.close(owner); control.close()
    os._exit(0)


def peer_child(control,path):
    stream=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); stream.connect(str(path)); stream.settimeout(5)
    control.sendall(b"connected\n"); control.recv(1)
    _,request,_=original(); raw=encode(request)
    stream.sendall(len(raw).to_bytes(4,"big")+raw)
    header=read_exact(stream,4); control.sendall(encode(dict(header_bytes=len(header)))+b"\n")
    body=read_exact(stream,int.from_bytes(header,"big")) if len(header)==4 else b""
    control.sendall(encode(dict(body_bytes=len(body),body_sha256=digest(body)))+b"\n")
    control.recv(1); stream.close(); os._exit(0)


class FixtureChannel:
    """Fixture-only injected duplicate. Impossible to select via production CLI."""
    def __init__(self,root,fd,owner,peer_pid,stream):
        self.root,self.fd,self.owner_fd,self.peer_pid,self.socket=root,fd,owner,peer_pid,stream
        self.identity=os.fstat(stream.fileno())
    def observe_owner(self, owner_fd):
        require(owner_fd==self.owner_fd,"fixture_original_owner_fd")
    def verify(self):
        self.root.verify(tracer=os.getpid())
        actual=os.stat(f"/proc/{self.root.pid}/fd/{self.fd}")
        require((actual.st_dev,actual.st_ino)==(self.identity.st_dev,self.identity.st_ino),"fixture_socket_changed")
        require(pidfd_target(self.root.pid,self.owner_fd)==self.peer_pid,"fixture_owner_pidfd")
        peer=struct.unpack("iII",self.socket.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        require(peer[0]==self.peer_pid,"fixture_peer")


def line(stream):
    value=bytearray()
    while True:
        part=stream.recv(1)
        if not part or part==b"\n": break
        value.extend(part)
    return json.loads(value)


def one(scenario):
    directory=Path(tempfile.mkdtemp(prefix="trill-issuer-own-fixture-")); shared=mmap.mmap(-1,8)
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); path=directory/"issuer.sock"
    listener.bind(str(path)); listener.listen(1)
    root_control,root_socket=socket.socketpair(); peer_control,peer_socket=socket.socketpair()
    root_pid=os.fork()
    if root_pid==0:
        root_control.close(); peer_control.close(); peer_socket.close()
        root_child(root_socket,listener,shared,scenario)
    root_socket.close(); listener.close()
    peer_pid=os.fork()
    if peer_pid==0:
        root_control.close(); peer_control.close()
        peer_child(peer_socket,path)
    peer_socket.close(); root_control.settimeout(5); peer_control.settimeout(5)
    held=trace=channel=None; producer=None; released=False
    result=dict(scenario=scenario,uid=os.getuid(),euid=os.geteuid(),product_qualified=False,
                production_pidfd_getfd_identity_path_executed=False)
    try:
        require(peer_control.recv(10)==b"connected\n","fixture_connected")
        raw,ancillary,flags,_=root_control.recvmsg(4096,socket.CMSG_SPACE(4))
        info=json.loads(raw); fds=array.array("i")
        require(flags==0 and len(ancillary)==1,"fixture_fd_message")
        fds.frombytes(ancillary[0][2]); require(len(fds)==1,"fixture_single_fd")
        duplicated=socket.socket(fileno=fds[0]); held=HeldProcess(process_binding(root_pid))
        channel=FixtureChannel(held,info["fd"],info["owner_fd"],peer_pid,duplicated); channel.verify()
        end=time.monotonic()+2; idle=None
        while time.monotonic()<end:
            idle=snapshot(held,info["tid"])
            if idle: break
            time.sleep(.001)
        require(idle is not None and ((scenario=="read-one" and idle[0] in (0,45) and idle[1][2]==1)
                or (scenario!="read-one" and idle[0]==271 and idle[1][1]==2)),"fixture_actual_original_idle")
        result["actual_idle_syscall"]=idle[0]
        trace=IssuerTrace(held,info["tid"],idle,proc_identity(root_pid,info["tid"])["start_ticks"])
        def produce():
            until=time.monotonic()+2
            while time.monotonic()<until:
                if proc_identity(root_pid,info["tid"])["tracer"]==os.getpid():
                    peer_control.sendall(b"g"); return
                time.sleep(.001)
        producer=threading.Thread(target=produce); producer.start()
        chosen,_,_=original()
        class SlowObservation(IssuerTransaction):
            def write_entry(self, raw, length):
                capture = super().write_entry(raw, length)
                if capture is not None:
                    # Actual observer stall; clocks and the original peer keep running.
                    time.sleep(max(0, self.first_byte_monotonic+.503-time.monotonic()))
                return capture
        transaction=(SlowObservation if scenario=="late-parser" else IssuerTransaction)(chosen)
        try:
            capture,deadline=scan_to_grant(trace,channel,transaction,time.monotonic()+3,500,lambda:False)
            result.update(capture={k:v for k,v in capture.items() if not isinstance(v,bytes) and k!="signed"},
                          actual_peer_prefix=line(peer_control))
            before=struct.unpack("Q",shared[:8])[0]
            time.sleep(max(0,deadline-time.monotonic())+.003 if scenario=="deadline-abort" else .02)
            after=struct.unpack("Q",shared[:8])[0]
            result["other_thread_progress_while_issuer_stopped"]=after-before
            if scenario=="deadline-abort":
                require(time.monotonic()>=deadline,"fixture_original_deadline_not_elapsed")
                result["gate_outcome"]="unknown_original_request_deadline"
            else: require(time.monotonic()<deadline,"fixture_original_500ms_deadline")
            if scenario in ("abort","deadline-abort"): channel.socket.shutdown(socket.SHUT_WR)
            trace.close(); released=True
        except Refused as error:
            result["refusal"]=str(error)
            if getattr(trace,"issuer_body_held",False):
                result["selected_capture_preserved"]=getattr(trace,"selected_capture",None) is not None
                result["gate_outcome"]="unknown_original_request_deadline"
                channel.socket.shutdown(socket.SHUT_WR)
            trace.close(); released=True
            result["actual_peer_prefix"]=line(peer_control)
        report=line(root_control); peer=line(peer_control)
        result.update(actual_issuer=report,actual_peer=peer)
        expected=encode(original()[2])
        result["passed"]=(result["actual_peer_prefix"]["header_bytes"]==4
            and (scenario in ("abort","deadline-abort","late-parser") and peer["body_bytes"]==0 and report.get("body_write_errno")==errno.EPIPE
                 or scenario not in ("abort","deadline-abort","late-parser") and peer["body_bytes"]==len(expected) and peer["body_sha256"]==digest(expected))
            and (scenario=="partial-body" and result.get("refusal")=="not_complete_first_grant_body"
                 or scenario=="late-parser" and result.get("refusal")=="original_request_deadline"
                 and result.get("selected_capture_preserved") is True
                 or scenario not in ("partial-body","late-parser") and result.get("other_thread_progress_while_issuer_stopped",0)>0)
            and not trace.attached and not trace.cleanup_failed)
    finally:
        if trace is not None: trace.close()
        if producer is not None: producer.join(timeout=1)
        # Release only owned fixture children; never a product process.
        for stream in (root_control,peer_control):
            try: stream.sendall(b"q")
            except OSError: pass
            stream.close()
        if channel is not None: channel.socket.close()
        if held is not None: held.close()
        result["owned_child_wait_statuses"]=[os.waitpid(pid,0)[1] for pid in (root_pid,peer_pid)]
        result["passed"]=result.get("passed",False) and result["owned_child_wait_statuses"]==[0,0]
        if trace is not None:
            result["trace"]=dict(stops=trace.stops,total_stopped_seconds=trace.total_pause,max_stop_seconds=trace.max_pause,
                                 events=trace.events,detached=not trace.attached)
        shared.close(); shutil.rmtree(directory)
    return result


def source_snapshot():
    source=BASE/"support/ui"
    paths=sorted(source.glob("notes_issuer_gate*.py"))+[source/"test_notes_issuer_gate.py",
        source/"notes_fault_linux.py",source/"notes_fault_contract.py",
        source/"qualification/notes_issuer_gate_kernel_fixture.py",
        source/"qualification/notes_issuer_gate_cleanup_fixture.py"]
    return {str(path.relative_to(BASE)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    require(args.output.is_absolute() and args.output.parent.resolve(strict=True)==args.output.parent
            and not args.output.is_relative_to(BASE),"fixture_new_external_output")
    args.output.mkdir(mode=0o700)
    before=source_snapshot()
    result=dict(scope="own unprivileged child/kernel tracing fixtures only",product_qualified=False,cases=[])
    for scenario in ("release","read-one","abort","deadline-abort","late-parser","partial-body"):
        try: result["cases"].append(one(scenario))
        except BaseException as error:
            result["error"]=str(error); break
    result["passed"]=len(result["cases"])==6 and all(case["passed"] for case in result["cases"])
    result.update(source_before=before,source_after=source_snapshot())
    result["source_unchanged"]=result["source_before"]==result["source_after"]
    result["passed"]=result["passed"] and result["source_unchanged"]
    (args.output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result),flush=True)
    raise SystemExit(0 if result["passed"] else 1)
