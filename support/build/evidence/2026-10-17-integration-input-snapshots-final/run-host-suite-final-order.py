#!/usr/bin/env python3
from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys
root=Path('/workspace/scratch/ae1a8cf05419');repo=root/'trillionnium-os-desktop';out=Path(__file__).resolve().parent/'full-host-suite-final-order';out.mkdir(exist_ok=False)
here=repo/'support/build/osdk-integration';files=sorted([p for p in here.iterdir() if p.is_file() and p.suffix in ('.py','.md')]+[here.parent/'record-qemu.py'])
def inputs():return {str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
before=inputs();rows=[];prefix=root/'native-tools/root';env=os.environ.copy();env.update(PATH=str(prefix/'usr/bin')+':'+env.get('PATH',''),LD_LIBRARY_PATH=':'.join(str(prefix/x) for x in ('usr/lib/x86_64-linux-gnu','lib/x86_64-linux-gnu','usr/lib/llvm-18/lib')),A01_GDB_REAL=str(prefix/'usr/bin/gdb'))
for key in ('A01_INTEGRATION_RECORDER_SOURCE','A01_ENTRY_GUARDS_SOURCE'):env.pop(key,None)
for tag,flags in [('I',['-I']),('I-O',['-I','-O'])]:
 current=env.copy()
 for key,folder in [('A01_CAPTURE_LIFECYCLE_OUT','capture'),('A01_PRIVATE_TOOLS_OUT','private'),('A01_INPUT_SNAPSHOTS_OUT','snapshots'),('A01_CASE_TARGET_OUT','case-targets'),('A01_ENTRY_GUARDS_OUT','entry')]:current[key]=str(out/(tag+'-'+folder))
 argv=['python3',*flags,'-m','unittest','discover','-s','support/build/osdk-integration','-p','test*.py','-v'];log=out/(tag+'.log');row={'mode':tag,'argv':argv,'cwd':str(repo),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'selected_environment':{k:current[k] for k in current if k.startswith('A01_') or k in ('PATH','LD_LIBRARY_PATH')},'log':str(log)}
 rows.append(row);(out/'commands.json').write_text(json.dumps(rows,indent=2)+'\n')
 with log.open('wb') as stream:result=subprocess.run(argv,cwd=repo,env=current,stdout=stream,stderr=subprocess.STDOUT,timeout=300)
 row.update(returncode=result.returncode,ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),log_bytes=log.stat().st_size,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
 (out/'commands.json').write_text(json.dumps(rows,indent=2)+'\n');print(tag,result.returncode,flush=True)
 if result.returncode:break
after=inputs();report={'schema':1,'source_before':before,'source_after':after,'source_stable':before==after,'commands':rows,'passed':len(rows)==2 and all(x['returncode']==0 for x in rows) and before==after}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':report['passed'],'source_stable':report['source_stable']}),flush=True)
raise SystemExit(0 if report['passed'] else 1)
