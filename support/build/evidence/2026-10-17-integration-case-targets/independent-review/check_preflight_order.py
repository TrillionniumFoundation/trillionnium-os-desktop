#!/usr/bin/env python3
"""Probe actual public runner call order with no Cargo/guest execution."""
import hashlib,importlib.util,json,os,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
sys.dont_write_bytecode=True
source=Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location('review_runner',source)
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
result={'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'scope':'No Cargo/VM execution; command collaborator records whether production Cargo was reached with foreign symlink present.'}
with tempfile.TemporaryDirectory(prefix='a01-target-preflight-') as t:
 root=Path(t);project=root/'project';here=project/'support/build/osdk-integration';here.mkdir(parents=True)
 prior=project/'support/build/out/prior';prior.mkdir(parents=True)
 for name in ['harness-adaptation.patch','harness-lock.json']:(prior/name).write_text('fixture\n')
 cache=prior/'target';cache.mkdir()
 foreign=root/'foreign';foreign.mkdir();(foreign/'keep').write_text('foreign unchanged\n')
 (cache/'debug').symlink_to(foreign,target_is_directory=True)
 output=root/'new-output';output.mkdir()
 calls=[]
 def checked(*args,**kw):return 'commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48\n'
 def prepare(*args,**kw):
  calls.append({'operation':'prepare_harness','foreign_debug_symlink':(cache/'debug').is_symlink()})
  harness=output/'harness';fixed=output/'fixed';harness.mkdir();fixed.mkdir();return harness,fixed
 def command(argv,cwd,env,log,timeout):
  calls.append({'operation':'production_cargo','argv':argv,'target':env['CARGO_TARGET_DIR'],'foreign_debug_symlink':(cache/'debug').is_symlink()})
  return {'raw_exit_code':42}
 args=SimpleNamespace(coverage_gdb=False,local_tcp=False,target_dir=cache,case=[],case_timeout=10)
 try:
  with mock.patch.object(r,'checked_output',side_effect=checked),mock.patch.object(r,'prepare_harness',side_effect=prepare),mock.patch.object(r,'command',side_effect=command):
   r.run_locked(args,here,project,project/'kernel/asterinas',output)
 except BaseException as e:
  result['terminal_exception']={'type':type(e).__name__,'message':str(e)}
 result.update(calls=calls,production_cargo_reached=any(c['operation']=='production_cargo' for c in calls),
               foreign_keep=(foreign/'keep').read_text(),foreign_entries=sorted(p.name for p in foreign.iterdir()))
print(json.dumps(result,indent=2))
