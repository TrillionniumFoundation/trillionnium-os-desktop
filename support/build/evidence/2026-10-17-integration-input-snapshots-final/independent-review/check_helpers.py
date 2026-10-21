#!/usr/bin/env python3
"""Limited source-closure/collision/stat probes; never execute QEMU or GDB."""
import hashlib,importlib.util,json,os,shutil,sys,tempfile
from pathlib import Path
from unittest import mock
ROOT=Path('/workspace/scratch/ae1a8cf05419');SRC=ROOT/'trillionnium-os-desktop/support/build/osdk-integration/record-qemu.py';SHARED=SRC.parent.parent/'record-qemu.py'
rows=[]
with tempfile.TemporaryDirectory(prefix='a01-snapshot-helper-review-') as d:
 p=Path(d);m=p/'support/build/osdk-integration/record-qemu.py';m.parent.mkdir(parents=True);shutil.copyfile(SRC,m)
 shared=m.parent.parent/'record-qemu.py';raw=SHARED.read_bytes();shared.write_bytes(raw)
 module_raw=m.read_bytes()
 spec=importlib.util.spec_from_file_location('review_snapshot_inputs',m);r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
 source=p/'source';source.write_bytes(b'fixed captured bytes\n');bios=p/'bios';bios.write_bytes(b'firmware bytes\n');record={}
 with mock.patch.dict(os.environ,{'A01_QEMU_BIOS':str(bios)},clear=True):
  selected=r.select_private_inputs(['-kernel',str(source),'-bios',str(bios)],record)
  h=r.snapshot_helpers(record)
 rows.append({'check':'same_shared_source_accepted','passed':callable(h.capture_artifact)})
 shared.write_bytes(raw+b'\n')
 try:r.snapshot_helpers(record)
 except ValueError as e:rows.append({'check':'changed_shared_source_rejected','passed':'source changed' in str(e),'error':str(e)})
 else:raise RuntimeError('changed shared source accepted')
 shared.write_bytes(raw)
 existing=p/'preexisting';existing.write_bytes(b'foreign preserved\n')
 try:r.snapshot_input(source,existing,h)
 except FileExistsError:rows.append({'check':'existing_snapshot_never_overwritten','passed':existing.read_bytes()==b'foreign preserved\n'})
 else:raise RuntimeError('existing target overwritten')
 original=source.read_bytes();artifact,provenance,snapshot=r.snapshot_input(source,p/'copy',h)
 source.write_bytes(b'later mutable build output\n')
 r.verify_input_snapshots({'artifact_snapshots':{'-kernel':snapshot}},h)
 rows.append({'check':'later_source_change_does_not_change_copy','passed':Path(artifact['path']).read_bytes()==original and artifact['sha256']==hashlib.sha256(original).hexdigest()})
 Path(artifact['path']).chmod(0o600)
 try:r.verify_input_snapshots({'artifact_snapshots':{'-kernel':snapshot}},h)
 except ValueError as e:rows.append({'check':'copy_stat_only_mutation_rejected','passed':'snapshot changed' in str(e),'error':str(e)})
 else:raise RuntimeError('snapshot mode change accepted')
result={'scope':'Actual production Python helpers with owned temporary files only; no native tool, QEMU, GDB or Cargo execution.',
 'recorder_sha256':hashlib.sha256(module_raw).hexdigest(),'production_sha256_after':hashlib.sha256(SRC.read_bytes()).hexdigest(),'shared_recorder_sha256':hashlib.sha256(raw).hexdigest(),'checks':rows,'passed':len(rows)==5 and all(x['passed'] for x in rows)}
if not result['passed']:raise RuntimeError(result)
print(json.dumps(result,indent=2))
