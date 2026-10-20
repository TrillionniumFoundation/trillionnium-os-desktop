#!/usr/bin/env python3
"""Capture actual offline verifier stdout/status; no restoration or guest launch."""
import datetime, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CWD=Path('/workspace/scratch/ae1a8cf05419')
rows=[]
for mode,flags in [('I',['-I']),('IO',['-I','-O'])]:
 argv=[sys.executable,*flags,str(ROOT/'verify.py')]
 row={'mode':mode,'argv':argv,'cwd':str(CWD),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'verifier_sha256':hashlib.sha256((ROOT/'verify.py').read_bytes()).hexdigest(),
      'scope':'Offline archive verification only; validates retained native/Rust results rather than rerunning them.'}
 result=subprocess.run(argv,cwd=CWD,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120,check=False)
 log=ROOT/('verification-'+mode+'.log');log.write_bytes(result.stdout)
 row.update(raw_exit_code=result.returncode,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            log=log.name,log_bytes=len(result.stdout),log_sha256=hashlib.sha256(result.stdout).hexdigest())
 rows.append(row)
 (ROOT/'verification.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(json.dumps(row),flush=True)
 if result.returncode:raise SystemExit(result.returncode)
