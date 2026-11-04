#!/usr/bin/env python3
"""Actual FD/root-view controls, no namespace entry or Android action."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).parent
parser=argparse.ArgumentParser();parser.add_argument("--r4-source",required=True)
args=parser.parse_args();R4=Path(args.r4_source)
assert hashlib.sha256((R4/"source-manifest.json").read_bytes()).hexdigest()=="b51efedefd1c458fae0cdf0fe1b353cf9c69db3429fa3c07bdc549d10dec0ed4"
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
H=module("paired_root_r5_control",HERE/"held_runtime.py")
OLD=module("paired_root_r4_negative",R4/"held_runtime.py")
ROWS=[]
def record(name,detail):ROWS.append({"name":name,"passed":True,"detail":detail})
def reject(operation,match):
 try:operation()
 except (H.BindingError,OSError) as error:
  assert match in str(error),repr(error)
  return repr(error)
 raise AssertionError("expected rejection")
class Root:
 def __init__(self,path):self.fd=os.open(path,os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC)
 def open_root(self,path,flags=os.O_RDONLY):return H.open_in_root(self.fd,path,flags)
 def close(self):os.close(self.fd)
def epoch_identity(pid):
 proc=os.open("/proc/"+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
 try:i=H.proc_identity_at(proc,pid,time.monotonic()+5)
 finally:os.close(proc)
 return {"host_pid":pid,"start_ticks":int(i["start"]),"uids":[int(v) for v in i["uid"]],
  "namespaces":{key:i["ns"][key] for key in ("mnt","pid")},"executable":i["exe"],
  "parent_host_pid":i["ppid"],"namespace_pids":[int(v) for v in i["nspid"]],"cgroup":i["cgroup"].splitlines()}
with tempfile.TemporaryDirectory(prefix="r5-paired-root-",dir=HERE.parent) as temp:
 root=Path(temp);a=root/"init";b=root/"zygote"
 for p in (a,b):
  (p/"system/framework").mkdir(parents=True);(p/"apex/real").mkdir(parents=True)
  (p/"apex/com.android.art").symlink_to("/apex/real")
 (a/"system/framework/a.jar").write_bytes(b"owned-a-jar-fixture")
 (a/"apex/real/b.jar").write_bytes(b"owned-b-jar-fixture")
 os.link(a/"system/framework/a.jar",b/"system/framework/a.jar")
 os.link(a/"apex/real/b.jar",b/"apex/real/b.jar")
 values={"BOOTCLASSPATH":"/system/framework/a.jar:/apex/com.android.art/b.jar",
         "DEX2OATBOOTCLASSPATH":"/system/framework/a.jar"}
 left,right=Root(a),Root(b)
 try:
  rows,total=H.hash_classpaths_paired(left,right,values,time.monotonic()+5)
  assert len(rows)==2 and all(x["same_backing_verified_by_held_fds"] for x in rows)
  assert total==len(b"owned-a-jar-fixture")+len(b"owned-b-jar-fixture")
  record("different-root-paths-and-absolute-apex-links-resolve-same-held-backing",
         {"jars":2,"streamed_backing_bytes":total,"simultaneous_fd_identity_proved":True})
  original=(b/"system/framework/a.jar").read_bytes()
  (b/"system/framework/a.jar").unlink();(b/"system/framework/a.jar").write_bytes(original)
  before_fds=set(os.listdir("/proc/self/fd"))
  error=reject(lambda:H.hash_classpaths_paired(left,right,values,time.monotonic()+5),"different backing")
  assert set(os.listdir("/proc/self/fd"))==before_fds
  record("same-path-and-identical-bytes-on-different-backing-fail-closed",
         {"error":error,"no_fd_leak":True,"same_content_is_not_implicitly_qualified":True})
  (b/"system/framework/a.jar").write_bytes(b"other-mount-contents")
  old_rows,old_total=OLD.hash_classpaths(left,values,time.monotonic()+5)
  assert len(old_rows)==2 and old_total==total
  error=reject(lambda:H.hash_classpaths_paired(left,right,values,time.monotonic()+5),"different backing")
  record("r4-init-only-hash-accepts-while-actual-r5-paired-view-rejects",
         {"r4_helper_returned_success":True,"r5_error":error,"scope":"actual hash helpers; not a replayed Android run"})
 finally:left.close();right.close()

 before_fds=set(os.listdir("/proc/self/fd"))
 expected=epoch_identity(os.getpid())
 view=H.HeldZygoteRoot(expected,time.monotonic()+5)
 try:
  view.verify()
  assert view.root_record["inode"]==os.stat("/").st_ino and len(view.fds)==4
  record("actual-owned-process-procdir-pidfd-mnt-root-view",
         {"held_fd_count":4,"namespace_entries":0,"command_entries":0})
 finally:view.close()
 assert set(os.listdir("/proc/self/fd"))==before_fds
 changed={**expected,"namespaces":{**expected["namespaces"],"mnt":"mnt:[1]"}}
 error=reject(lambda:H.HeldZygoteRoot(changed,time.monotonic()+5),"differs from the fixed epoch")
 assert set(os.listdir("/proc/self/fd"))==before_fds
 record("mismatched-fixed-mount-identity-rejected-with-all-fds-closed",{"error":error})
 child=subprocess.Popen([sys.executable,"-I","-c","import time;time.sleep(30)"])
 view=None
 try:
  expected=epoch_identity(child.pid)
  view=H.HeldZygoteRoot(expected,time.monotonic()+5)
  child.terminate();child.wait(timeout=5)
  error=reject(view.verify,"fixed zygote generation")
  record("dead-original-process-pidfd-rejects-held-root-admission",
         {"error":error,"exact_owned_child_reaped":True})
 finally:
  if child.poll() is None:child.kill();child.wait(timeout=5)
  if view is not None:view.close()
 assert set(os.listdir("/proc/self/fd"))==before_fds

print(json.dumps({"schema":1,"state":"PAIRED_ROOT_FD_CONTROLS_PASS","passed":len(ROWS),"controls":ROWS,
 "Android_operations":0,"namespace_entries":0,"Main_actions":0,
 "real_mechanisms":["actual openat2 rooted file resolution","hard-linked identical backing","different backing with identical bytes",
                    "actual own procdir/pidfd/mount/root descriptors","owned child exit/reap"],
 "different_actual_Android_mount_namespace_test":"NOT_RUN; fresh private qualification still required",
 "production_ready":False,"source_pins":{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
  for name in ("held_runtime.py","verify_paired_roots_r5.py")}},sort_keys=True,indent=2))
