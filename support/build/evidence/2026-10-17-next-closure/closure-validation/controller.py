from pathlib import Path
import subprocess,sys,json,datetime,hashlib
root=Path('/workspace/scratch/ae1a8cf05419');repo=root/'trillionnium-os-desktop';phase=repo/'support/build/evidence/2026-10-17-next-closure';logs=root/'next-closure-validation';logs.mkdir(exist_ok=True)
rows=[]
for name,flags in [('I',['-I']),('IO',['-I','-O']),('I-live-repo',['-I'])]:
 argv=[sys.executable,*flags,str(phase/'verify.py')]+(['--repo',str(repo)] if name=='I-live-repo' else [])
 row={'name':name,'argv':argv,'cwd':str(repo),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'input_sha256sums_sha256':hashlib.sha256((phase/'SHA256SUMS').read_bytes()).hexdigest(),'verifier_sha256':hashlib.sha256((phase/'verify.py').read_bytes()).hexdigest()}
 result=subprocess.run(argv,cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (logs/(name+'.log')).write_bytes(result.stdout)
 row.update(finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),raw_exit_code=result.returncode,log=name+'.log',log_bytes=len(result.stdout),log_sha256=hashlib.sha256(result.stdout).hexdigest());rows.append(row)
 print(name,result.returncode,flush=True)
(logs/'validation.json').write_text(json.dumps({'scope':'Actual final closure portable offline checks; live option checks current selected source/lock/kernel Git tree; no underlying phase verifier, compiler or guest rerun. These observations precede their addition to closure checksums to avoid circular receipts.','commands':rows,'all_zero':all(x['raw_exit_code']==0 for x in rows)},indent=2)+'\n')
raise SystemExit(int(any(x['raw_exit_code']!=0 for x in rows)))
