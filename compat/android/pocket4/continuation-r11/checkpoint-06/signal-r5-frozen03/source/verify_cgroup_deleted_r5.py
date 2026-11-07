#!/usr/bin/env python3
"""One empty cgroup under this exact owned job; no processes are moved."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location("cgroup_deleted_r5_actual",HERE/"cleanup_owned.py")
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
group=Path("/proc/self/cgroup").read_text().strip().split("0::",1)[1]
assert re.fullmatch(r"/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-[0-9a-f]+-fc05-[0-9a-f]+\.service",group),group
name="r5-empty-cgroup-source-control-01"
child=Path("/sys/fs/cgroup"+group)/name
result={"schema":1,"scope":"one empty child of this exact owned Hepta job cgroup","own_cgroup":group,
        "processes_moved":0,"controller_or_limit_changes":0,"Android_operations":0,"Main_actions":0,
        "source_sha256":hashlib.sha256((HERE/"cleanup_owned.py").read_bytes()).hexdigest()}
proof=None;identity=None
try:
 child.mkdir()
 s=child.stat();identity=(s.st_dev,s.st_ino)
 proof=C.CgroupProof(Path("/sys/fs/cgroup"),group+"/"+name)
 result["before"]={"events":C.read_at(proof.fd,"cgroup.events",4096),
                   "root_processes":C.read_at(proof.fd,"cgroup.procs"),
                   "filesystem_type":proof.fs_type,"identity":proof.identity}
 assert result["before"]["root_processes"]=="" and C.parse_events(result["before"]["events"])["populated"]==0
 assert proof.fs_type==C.CGROUP2_SUPER_MAGIC
 child.rmdir()
 result["after"]=proof.sample()
 assert result["after"]["absent"] is True and C.CgroupProof.empty(result["after"])
 assert result["after"]["held_identity"]==result["before"]["identity"]
 result["state"]="ACTUAL_CGROUP2_DELETION_PROOF_PASS"
finally:
 if proof is not None:proof.close()
 if child.exists():
  s=child.stat();assert identity==(s.st_dev,s.st_ino)
  assert (child/"cgroup.procs").read_text()==""
  child.rmdir()
 result["exact_child_absent"]=not child.exists()
print(json.dumps(result,sort_keys=True,indent=2))
