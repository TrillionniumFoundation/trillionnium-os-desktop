#!/usr/bin/env python3
"""Independent single-case red/green replay: fake QEMU/capture only."""
import datetime,hashlib,json,os,subprocess,sys
from pathlib import Path
BASE=Path('/workspace/scratch/ae1a8cf05419');OUT=BASE/'input-snapshot-source-review'
TEST=BASE/'trillionnium-os-desktop/support/build/osdk-integration/test_input_snapshots.py'
OLD=BASE/'coverage-freeze-timing-review/test_capture_cli_uses_private_em62_after_original_symbol_and_kernel_change/fixture project/support/build/osdk-integration/record-qemu.py'
NEW=TEST.with_name('record-qemu.py')
CASE='InputSnapshotCliTests.test_capture_cli_freezes_valid_symbols_before_qemu_version_probe'
rows=[]
for label,source,expect in [('red-bc1225',OLD,1),('green-67f576',NEW,0)]:
 env=dict(os.environ);env.update(A01_INTEGRATION_RECORDER_SOURCE=str(source),A01_INPUT_SNAPSHOTS_OUT=str(OUT/label))
 (OUT/label).mkdir(exist_ok=False)
 argv=[sys.executable,'-I','-B',str(TEST),CASE,'-v']
 source_hash=hashlib.sha256(source.read_bytes()).hexdigest();test_hash=hashlib.sha256(TEST.read_bytes()).hexdigest()
 row={'label':label,'argv':argv,'cwd':str(BASE),'selected_environment':{k:env[k] for k in ('A01_INTEGRATION_RECORDER_SOURCE','A01_INPUT_SNAPSHOTS_OUT')},
 'source_sha256_before':source_hash,'test_sha256_before':test_hash,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'scope':'Actual production recorder under one host-only regression case using executable fake QEMU/fake capture; no VM or GDB.'}
 p=subprocess.run(argv,cwd=BASE,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
 log=OUT/(label+'.log');log.write_bytes(p.stdout)
 row.update(raw_exit_code=p.returncode,expected_test_exit_code=expect,expected_result=p.returncode==expect,log=log.name,
 source_sha256_after=hashlib.sha256(source.read_bytes()).hexdigest(),test_sha256_after=hashlib.sha256(TEST.read_bytes()).hexdigest(),
 finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 invocations=list((OUT/label).rglob('invocation-*.json'))
 if len(invocations)!=1:raise RuntimeError('expected one real recorder invocation')
 actual=json.loads(invocations[0].read_text());record=actual['record'];sym=record.get('capture',{}).get('symbol_elf')
 row['retained_invocation']=str(invocations[0].relative_to(OUT))
 row['observed_recorder']={'wrapper_exit':record.get('wrapper_exit_code'),'qemu_raw_exit':record.get('raw_exit_code'),
 'capture_raw_exit':record.get('capture',{}).get('raw_exit_code'),'capture_finalized':record.get('capture',{}).get('finalized'),
 'snapshot_verification':record.get('snapshot_verification'),'symbol_copy':sym,'error':record.get('error')}
 rows.append(row);(OUT/'version-case-replay.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
 if p.returncode!=expect or source_hash!=row['source_sha256_after'] or test_hash!=row['test_sha256_after']:raise RuntimeError('unexpected replay result/source drift')
