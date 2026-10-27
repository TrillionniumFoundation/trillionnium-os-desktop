#!/usr/bin/env python3
"""Own-child actual read-one signal/exec/cancel cleanup; no product authority."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(BASE/"support/ui"))
with tempfile.TemporaryDirectory(prefix="trill-issuer-cleanup-source-") as _source_cache:
    _old_cache = sys.pycache_prefix
    try:
        sys.pycache_prefix = _source_cache
        from notes_fault_contract import Refused, require
        from notes_fault_linux import LIBC, HeldProcess, proc_identity, SEIZE
        from notes_issuer_gate_linux import IssuerTrace, snapshot
    finally:
        sys.pycache_prefix = _old_cache


def child(scenario,inputfd,lifefd,directory):
    root=Path(directory); count=[0]
    def received(*_):
        count[0]+=1; (root/"signal.json").write_text(json.dumps(dict(count=count[0])))
    signal.signal(signal.SIGUSR1,received)
    def worker():
        (root/"ready.json").write_text(json.dumps(dict(tid=threading.get_native_id())))
        raw=os.read(inputfd,1)
        if scenario=="exec":
            os.execve(sys.executable,[sys.executable,"-B",str(Path(__file__).resolve()),"--after-exec",str(lifefd),directory],
                      dict(os.environ,PYTHONDONTWRITEBYTECODE="1"))
        (root/"completed.json").write_text(json.dumps(dict(raw_hex=raw.hex())))
        os.read(lifefd,1)
    thread=threading.Thread(target=worker); thread.start()
    while thread.is_alive(): thread.join(.01)
    return 0


def wait_file(path):
    until=time.monotonic()+3
    while time.monotonic()<until:
        if path.exists(): return json.loads(path.read_text())
        time.sleep(.002)
    raise RuntimeError("own fixture marker absent: "+path.name)


def one(scenario):
    with tempfile.TemporaryDirectory(prefix="trill-own-issuer-cleanup-") as directory:
        root=Path(directory); inputr,inputw=os.pipe(); lifer,lifew=os.pipe(); pid=os.fork()
        if pid==0:
            os.close(inputw); os.close(lifew)
            for fd in (inputr,lifer): os.set_inheritable(fd,True)
            os.execve(sys.executable,[sys.executable,"-B",str(Path(__file__).resolve()),"--child",scenario,
                                     str(inputr),str(lifer),directory],dict(os.environ,PYTHONDONTWRITEBYTECODE="1"))
        os.close(inputr); os.close(lifer); held=trace=None
        result=dict(scenario=scenario,product_qualified=False,uid=os.getuid(),euid=os.geteuid())
        try:
            tid=wait_file(root/"ready.json")["tid"]
            identity=proc_identity(pid); executable=Path(f"/proc/{pid}/exe").resolve(strict=True)
            held=HeldProcess(dict(pid=pid,start_ticks=identity["start_ticks"],uid=os.getuid(),gid=os.getgid(),
                                 executable=str(executable),sha256=hashlib.sha256(executable.read_bytes()).hexdigest()))
            idle=None; end=time.monotonic()+2
            while time.monotonic()<end:
                idle=snapshot(held,tid)
                if idle: break
                time.sleep(.001)
            require(idle is not None and idle[0] in (0,45) and idle[1][2]==1,"own_original_read_one")
            trace=IssuerTrace(held,tid,idle,proc_identity(pid,tid)["start_ticks"])
            if scenario=="attach-signal":
                original_ptrace=trace.ptrace
                def send_after_seize(request,*args,**kwargs):
                    value=original_ptrace(request,*args,**kwargs)
                    if request==SEIZE:
                        require(LIBC.syscall(ctypes.c_long(234),pid,tid,signal.SIGUSR1)==0,"own_tgkill")
                        until=time.monotonic()+.25
                        while time.monotonic()<until:
                            if proc_identity(pid,tid)["state"]=="t": break
                            time.sleep(.001)
                    return value
                trace.ptrace=send_after_seize
                try: trace.attach(time.monotonic()+2)
                except Refused as error: result["refusal"]=str(error)
                trace.close()
                result["delivered_signal_count"]=wait_file(root/"signal.json")["count"]
                os.write(inputw,b"x"); result["completed"]=wait_file(root/"completed.json")
            else:
                trace.attach(time.monotonic()+2); trace.resume()
                if scenario=="exec":
                    os.write(inputw,b"x")
                    try:
                        until=time.monotonic()+3
                        while time.monotonic()<until:
                            trace.wait(until); trace.resume(trace.deliver)
                    except Refused as error: result["refusal"]=str(error)
                    trace.close(); result["after_exec"]=wait_file(root/"after-exec.json")
                else:
                    try: trace.wait(time.monotonic()+2,cancelled=lambda:True)
                    except Refused as error: result["refusal"]=str(error)
                    trace.close(); os.write(inputw,b"x"); result["completed"]=wait_file(root/"completed.json")
            result["passed"]=not trace.attached and not trace.cleanup_failed and (
                scenario=="attach-signal" and result.get("delivered_signal_count")==1
                and result.get("completed")==dict(raw_hex="78")
                or scenario=="exec" and result.get("refusal")=="effect_thread_exec_invalidates_boundary"
                and result.get("after_exec")==dict(pid=pid)
                or scenario=="cancel" and result.get("refusal")=="controller_cancelled"
                and result.get("completed")==dict(raw_hex="78"))
        finally:
            if trace is not None:
                trace.close(); result["tracing"]=dict(events=trace.events,detached=not trace.attached,
                                                     stops=trace.stops,max_stop_seconds=trace.max_pause)
            if held is not None: held.close()
            os.close(inputw); os.close(lifew)
            result["owned_child_wait_status"]=os.waitpid(pid,0)[1]
            result["passed"]=result.get("passed",False) and result["owned_child_wait_status"]==0
        return result


def source_snapshot():
    source=BASE/"support/ui"
    paths=sorted(source.glob("notes_issuer_gate*.py"))+[source/"test_notes_issuer_gate.py",
        source/"notes_fault_linux.py",source/"notes_fault_contract.py",
        source/"qualification/notes_issuer_gate_kernel_fixture.py",
        source/"qualification/notes_issuer_gate_cleanup_fixture.py"]
    return {str(path.relative_to(BASE)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--child":
        raise SystemExit(child(sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),sys.argv[5]))
    if len(sys.argv)>1 and sys.argv[1]=="--after-exec":
        Path(sys.argv[3],"after-exec.json").write_text(json.dumps(dict(pid=os.getpid())))
        os.read(int(sys.argv[2]),1); raise SystemExit(0)
    import argparse
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    require(args.output.is_absolute() and args.output.parent.resolve(strict=True)==args.output.parent
            and not args.output.is_relative_to(BASE),"fixture_new_external_output")
    args.output.mkdir(mode=0o700)
    before=source_snapshot()
    result=dict(product_qualified=False,cases=[])
    for scenario in ("attach-signal","exec","cancel"):
        try: result["cases"].append(one(scenario))
        except BaseException as error: result["error"]=str(error); break
    result["passed"]=len(result["cases"])==3 and all(case["passed"] for case in result["cases"])
    result.update(source_before=before,source_after=source_snapshot())
    result["source_unchanged"]=result["source_before"]==result["source_after"]
    result["passed"]=result["passed"] and result["source_unchanged"]
    (args.output/"result.json").write_text(json.dumps(result,indent=2)+"\n"); print(json.dumps(result),flush=True)
    raise SystemExit(0 if result["passed"] else 1)
