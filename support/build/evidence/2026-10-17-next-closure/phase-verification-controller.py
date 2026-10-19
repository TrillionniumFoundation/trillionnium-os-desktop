from pathlib import Path
import subprocess, hashlib, json, datetime, sys
repo=Path('/workspace/scratch/ae1a8cf05419/trillionnium-os-desktop')
out=repo/'support/build/evidence/2026-10-17-next-closure'
logs=out/'phase-verification';logs.mkdir(exist_ok=True)
names=['cloud-restore-next','private-sdk','private-sdk-native','debug-private-sdk','debug-private-sdk-native','ktest-private-sdk','ktest-private-sdk-native','main-ci-next','main47288-abi','repro-cross-instance','repro-kernel-c4']
rows=[]
for name in names:
 phase=repo/'support/build/evidence'/('2026-10-17-'+name)
 verifier=phase/'verify.py'
 for mode, flags in [('I',['-I']),('IO',['-I','-O'])]:
  argv=[sys.executable,*flags,str(verifier)]
  row={'phase':str(phase.relative_to(repo)),'mode':mode,'argv':argv,'cwd':str(phase),'verifier_sha256':hashlib.sha256(verifier.read_bytes()).hexdigest(),'phase_sha256sums_sha256':hashlib.sha256((phase/'SHA256SUMS').read_bytes()).hexdigest(),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  result=subprocess.run(argv,cwd=phase,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  log=logs/(name+'-'+mode+'.log');log.write_bytes(result.stdout)
  row.update(finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),raw_exit_code=result.returncode,log=str(log.relative_to(out)),log_bytes=len(result.stdout),log_sha256=hashlib.sha256(result.stdout).hexdigest())
  rows.append(row)
  (out/'phase-verification.json').write_text(json.dumps({'scope':'Actual original portable offline verifier subprocess observations; no SDK installation, compiler, guest, archived script or recovered ELF executed. These22 runs are not additional kernel acceptance.','commands':rows,'completed':len(rows)==22,'all_zero':len(rows)==22 and all(x['raw_exit_code']==0 for x in rows)},indent=2)+'\n')
  print(name,mode,result.returncode,flush=True)
print('COMPLETE',len(rows),'FAILURES',sum(x['raw_exit_code']!=0 for x in rows))
raise SystemExit(int(any(x['raw_exit_code']!=0 for x in rows)))
