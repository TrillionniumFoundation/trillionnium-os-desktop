#!/usr/bin/env python3
"""Offline admission and owned-process cleanup checks; never prepare/build."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from unittest import mock


def main():
    source = Path(sys.argv[1])
    raw = source.read_bytes()
    scope = {"__name__": "controller_under_review", "__file__": str(source)}
    exec(compile(raw, str(source), "exec"), scope, scope)
    checks = []

    def record(name, assertion):
        if not assertion:
            raise RuntimeError(name)
        checks.append({"name": name, "pass": True})

    def forbidden(*args, **kwargs):
        raise AssertionError("preparation or build unexpectedly called")

    with mock.patch.dict(scope, {"prepare": forbidden, "build": forbidden}):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = scope["main"]([])
        plan = json.loads(out.getvalue())
        record("default_plan_no_action", code == 0 and plan["state"] == "PLAN_ONLY" and
               plan["argv"][3:5] == ["--jobs", "1"] and not plan["feature_default_enabled"])
        for name, arguments in (
                ("build_requires_receipt", ["--build"]),
                ("prepare_cannot_reuse_receipt", ["--prepare", "--preparation-sha256", "a" * 64]),
                ("plan_cannot_consume_receipt", ["--preparation-sha256", "a" * 64]),
                ("exclusive_modes", ["--prepare", "--build"])):
            rejected = False
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    scope["main"](arguments)
            except (RuntimeError, SystemExit):
                rejected = True
            record(name, rejected)

    for value in ("", ".", "../x", "a/../b", "/x", "a//b", "a/.git/b"):
        rejected = False
        try:
            scope["relative"](value)
        except RuntimeError:
            rejected = True
        record("reject_relative_" + repr(value), rejected)
    record("valid_relative", str(scope["relative"]("kernel_api/Android.bp")) == "kernel_api/Android.bp")

    with tempfile.TemporaryDirectory(prefix="combined-controller-path-") as directory:
        base = Path(directory)
        (base / "real").mkdir()
        (base / "alias").symlink_to(base / "real", target_is_directory=True)
        rejected = False
        try:
            scope["no_alias"](base / "alias" / "new")
        except RuntimeError:
            rejected = True
        record("reject_symlink_ancestor", rejected and list((base / "real").iterdir()) == [])

    with mock.patch.dict(scope, {"child_ids": mock.Mock(side_effect=OSError("enumeration seam"))}):
        result = scope["cleanup_children"]()
        record("cleanup_enumeration_failure_not_pass", not result["complete"] and
               result["errors"][0]["operation"] == "enumerate")

    def open_pidfd(pid, flags):
        if pid == 41:
            raise PermissionError("pidfd seam")
        return 502
    with mock.patch.dict(scope, {"child_ids": mock.Mock(side_effect=[[41, 42], []])}), \
            mock.patch.object(os, "pidfd_open", side_effect=open_pidfd), \
            mock.patch.object(signal, "pidfd_send_signal"), \
            mock.patch.object(os, "waitpid", return_value=(42, signal.SIGKILL)), \
            mock.patch.object(os, "close"):
        result = scope["cleanup_children"]()
        record("cleanup_one_failure_continues_next_owned_child", not result["complete"] and
               result["children"] == [{"pid": 42, "wait_status": signal.SIGKILL, "reaped": True}] and
               result["errors"][0]["pid"] == 41)

    child_code = r'''
import ctypes,json,os,select,signal,sys,time
source=sys.argv[1]
s={"__name__":"under_test"}
exec(compile(open(source,"rb").read(),source,"exec"),s,s)
s["subreaper"]()
r,w=os.pipe2(os.O_CLOEXEC)
root=os.getpid()
pid=os.fork()
if pid==0:
    os.close(r)
    libc=ctypes.CDLL(None,use_errno=True)
    libc.prctl.argtypes=[ctypes.c_int,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong]
    libc.prctl.restype=ctypes.c_int
    assert libc.prctl(1,signal.SIGKILL,0,0,0)==0 and os.getppid()==root
    own=os.getpid()
    nested=os.fork()
    if nested==0:
        assert libc.prctl(1,signal.SIGKILL,0,0,0)==0 and os.getppid()==own
        os.close(w)
        while True: signal.pause()
    os.write(w,(str(nested)+"\n").encode());os.close(w)
    while True: signal.pause()
os.close(w)
assert select.select([r],[],[],2)[0]
nested=int(os.read(r,64));os.close(r)
# The local executor mounts a different proc PID view and does not expose
# task/children. Keep that real limitation visible; only the exact known owned
# PID set is substituted in this isolated syscall/reaping control.
enumeration_seam=False
try: s["child_ids"]()
except (OSError,RuntimeError):
    enumeration_seam=True
    def own_known_children():
        result=[]
        for child in [pid,nested]:
            try: os.waitid(os.P_PID,child,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            except ChildProcessError: continue
            result.append(child)
        return result
    s["child_ids"]=own_known_children
result=s["cleanup_children"]()
seen={item["pid"] for item in result["children"] if item["reaped"]}
assert result["complete"] and seen=={pid,nested} and not s["child_ids"](),result
for child in [pid,nested]:
    try: os.waitpid(child,os.WNOHANG)
    except ChildProcessError: pass
    else: raise AssertionError("child not exclusively reaped")
print(json.dumps({"complete":True,"direct_reaped":1,"nested_reaped":1,"remaining":0,
                  "enumeration_seam":enumeration_seam}))
'''
    process = subprocess.Popen([sys.executable, "-I", "-c", child_code, str(source)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=15)
    except BaseException:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=3)
        raise
    if process.returncode != 0:
        sys.stderr.write(stderr.decode("utf-8", errors="replace"))
        sys.stderr.write(stdout.decode("utf-8", errors="replace"))
    own_tree = json.loads(stdout) if stdout else {}
    record("actual_owned_tree_pidfd_stop_and_exact_reap", process.returncode == 0 and not stderr and
           own_tree.get("complete") and own_tree.get("direct_reaped") == 1 and
           own_tree.get("nested_reaped") == 1 and own_tree.get("remaining") == 0)

    print(json.dumps({"schema": 1, "controller_sha256": hashlib.sha256(raw).hexdigest(),
                      "controller_bytes": len(raw), "all_pass": True, "checks": checks,
                      "scope": "offline admission; local own child tree only; explicit failure seams",
                      "owned_tree_control": own_tree,
                      "actual_remote_proc_children_enumeration": "NOT_PERFORMED; preflight must pass before build",
                      "remote_called": False, "prepare_executed": False, "build_executed": False,
                      "Android_executed": False, "factory_executed": False}, indent=2))


if __name__ == "__main__":
    main()
