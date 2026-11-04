#!/usr/bin/env python3
"""Actual old/new fixture plan controls; never invoke a valid execute entry."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).parent
OLD_NONCE="969694d682504cb2ae81bf178474c96e8"
NEW_NONCE="5c53c248004139cd14513e8d88023c18"
OLD_SHA="331a069e658413f8986601b9dd91be5e470f1c8adae8a49533ce5f955eea560b"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec)
 spec.loader.exec_module(value);return value
def reject_nonce(function):
 try:function()
 except Exception as error:
  assert type(error).__name__=="CleanupError" and str(error)=="private unit name or nonce is invalid",repr(error)
  return {"type":type(error).__name__,"message":str(error)}
 raise AssertionError("actual production nonce guard did not reject")
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--old-fixture-source",required=True)
 options=parser.parse_args()
 old=Path(options.old_fixture_source)
 assert hashlib.sha256(old.read_bytes()).hexdigest()==OLD_SHA
 assert len(OLD_NONCE)==33 and len(NEW_NONCE)==32
 rows=[]
 current=load("new_owned_fixture_plan_control",HERE/"owned_cleanup_fixture.py")
 assert current.NONCE==NEW_NONCE
 before=(current.CLAIM.exists(),current.EVIDENCE.exists())
 assert before==(False,False),"fixture02 is already claimed"
 raw=subprocess.run([sys.executable,"-I",str(old)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
     stderr=subprocess.PIPE,timeout=10,check=False,
     env={"PATH":"/usr/bin:/bin","LANG":"C","LC_ALL":"C","PYTHONDONTWRITEBYTECODE":"1"})
 assert raw.returncode==0 and not raw.stderr
 prior=json.loads(raw.stdout);assert prior["nonce"]==OLD_NONCE and "preflight" not in prior
 production=load("actual_production_nonce_control",HERE/"cleanup_owned.py")
 old_row={"role":"bus","unit":prior["unit"],"description":prior["name"]+" "+OLD_NONCE+" bus"}
 rejection=reject_nonce(lambda:production.OwnedCleanup({"NAME":prior["name"],"NONCE":OLD_NONCE}).planned(old_row))
 rows.append({"name":"actual-old-default-plan-accepts-33hex-while-production-guard-rejects",
              "passed":True,"expected_old_negative":True,"default_returncode":raw.returncode,
              "nonce_length":len(OLD_NONCE),"production_rejection":rejection,"unit_started":False})
 output=io.StringIO()
 with contextlib.redirect_stdout(output):assert current.main([])==0
 new=json.loads(output.getvalue())
 assert new["nonce"]==NEW_NONCE and new["preflight"]["nonce_hex_length"]==32
 assert new["preflight"]["state"]=="ACTUAL_PRODUCTION_PLANNED_PREFLIGHT_PASS"
 assert new["preflight"]["claim_created"] is False and new["preflight"]["services_started"]==0
 rows.append({"name":"actual-new-default-plan-invokes-pinned-production-guard-before-output",
              "passed":True,"preflight":new["preflight"]})
 # The declared spies are only forbidden-effect detectors. The production
 # planned() implementation and actual new entry functions are not replaced.
 for label in ("default","execute"):
  tested=load("invalid_nonce_entry_"+label,HERE/"owned_cleanup_fixture.py")
  tested.NONCE=OLD_NONCE
  tested.DESCRIPTION=tested.NAME+" "+OLD_NONCE+" bus"
  tested.PLAN={**tested.PLAN,"nonce":OLD_NONCE}
  effects=[]
  def forbidden(*args,**kwargs):
   effects.append({"args":repr(args),"kwargs":repr(kwargs)})
   raise AssertionError("preflight admitted a forbidden follow-on operation")
  tested.source_contract=forbidden
  tested.write_new=forbidden
  tested.raw=forbidden
  original_mkdir=Path.mkdir
  Path.mkdir=forbidden
  output=io.StringIO()
  try:
   with contextlib.redirect_stdout(output):
    rejected=reject_nonce(lambda:tested.main([]) if label=="default" else tested.execute("0"*64))
  finally:Path.mkdir=original_mkdir
  assert not effects and output.getvalue()==""
  assert (current.CLAIM.exists(),current.EVIDENCE.exists())==before
  rows.append({"name":"old-33hex-rejected-before-"+label+"-claim-directory-source-contract-or-command",
               "passed":True,"actual_entry":label,"rejection":rejected,
               "forbidden_follow_on_calls":0,"claim_created":False,"directory_created":False,
               "systemd_commands":0})
 assert (current.CLAIM.exists(),current.EVIDENCE.exists())==before
 print(json.dumps({"schema":1,"state":"FIXTURE02_ACTUAL_NONCE_PREFLIGHT_CONTROLS_PASS",
  "controls":rows,"passed":len(rows),"actual_production_guard_sha256":
     hashlib.sha256((HERE/"cleanup_owned.py").read_bytes()).hexdigest(),
  "source_pins":{name:{"bytes":(HERE/name).stat().st_size,
    "sha256":hashlib.sha256((HERE/name).read_bytes()).hexdigest()} for name in
    ("owned_cleanup_fixture.py","owned_cleanup_fixture_child.py","cleanup_owned.py","verify_fixture02_preflight.py")},
  "only_subprocess":"actual frozen old default PLAN; never execute-once",
  "effect_spies":"source_contract/write_new/raw/Path.mkdir are forbidden follow-on detectors only",
  "services_started":0,"Android_operations":0,"Main_actions":0,"actual_systemd_fixture":"NOT_RUN",
  "production_ready":False},sort_keys=True,indent=2))
if __name__=="__main__":main()

