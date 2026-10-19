#!/usr/bin/env python3
"""Capture offline phase-verifier results, without invoking a build or guest."""
import datetime,hashlib,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
def main():
 rows=[];outputs=[]
 for mode,flags in [('I',['-I']),('IO',['-I','-O'])]:
  argv=[sys.executable,*flags,str(HERE/'verify.py')];start=datetime.datetime.now(datetime.timezone.utc).isoformat();result=subprocess.run(argv,cwd=HERE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180,check=False)
  rows.append({'mode':mode,'argv':argv,'cwd':str(HERE),'start_utc':start,'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'raw_exit_code':result.returncode,'verifier_sha256':hashlib.sha256((HERE/'verify.py').read_bytes()).hexdigest(),'log':'verification-'+mode+'.log','log_bytes':len(result.stdout),'log_sha256':hashlib.sha256(result.stdout).hexdigest(),'scope':'Original completed N2 offline evidence only; no compilation, SDK, source target or guest access.'});outputs.append(result.stdout)
  if result.returncode:break
 for row,output in zip(rows,outputs):(HERE/row['log']).write_bytes(output)
 (HERE/'verification.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(json.dumps({'modes':[r['mode'] for r in rows],'raw_exits':[r['raw_exit_code'] for r in rows]}))
 if len(rows)!=2 or any(r['raw_exit_code'] for r in rows):raise SystemExit(1)
if __name__=='__main__':main()
