#!/usr/bin/env python3
"""Supplement the initial allowlist with remaining tracked project docs/config."""
import datetime,hashlib,json,re,stat,subprocess
from pathlib import Path
REPO=Path('/workspace/scratch/ae1a8cf05419/trillionnium-os-desktop')
OUT=Path(__file__).resolve().parent
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
previous={item['path'] for item in json.loads((OUT/'scan.json').read_text())['files']}
tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode().split('\0'))
paths=subprocess.check_output(['rg','--files','--hidden','-g','!.git','-g','!kernel/asterinas/**','-g','!**/evidence/**','-g','!**/results/**','-g','!**/target/**','-g','!**/out/**','-g','!**/__pycache__/**'],cwd=REPO,text=True).splitlines()
pattern=re.compile(r'\bKVM\b|/dev/kvm|self[- ]hosted|\bruns-on\b|\bVMX\b|\bEPT\b|second.{0,18}host|dedicated.{0,24}host|dedicated.{0,24}cloud|cloud.{0,24}environment|云环境|专属|第二.{0,8}主机|第二.{0,8}host|远程.{0,8}主机|\bhostname\b|\bhost_id\b|runner.{0,18}labels?',re.I)
files,hits=[],[]
for name in sorted(paths):
 p=Path(name)
 if name not in tracked or name in previous or name.startswith('kernel/asterinas/'):
  continue
 if set(p.parts)&{'evidence','results','target','out','__pycache__'}:
  continue
 if any(re.search(r'(^|[._-])(auth|credential|secret|private|account|keys?)([._-]|$)',part,re.I) for part in p.parts):
  continue
 if not (p.suffix.lower() in {'.md','.txt','.toml','.yml','.yaml','.ini','.cfg','.conf'} or p.name in {'Dockerfile','Vagrantfile'} or (name.startswith(('support/','infra/','infrastructure/','.devcontainer/')) and p.suffix.lower()=='.json')):
  continue
 if not stat.S_ISREG((REPO/p).lstat().st_mode):
  continue
 raw=(REPO/p).read_bytes();lines=raw.decode('utf-8',errors='replace').splitlines()
 files.append({'path':name,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
 for i,line in enumerate(lines):
  if pattern.search(line):hits.append({'path':name,'line':i+1,'text':line,'context':[{'line':j+1,'text':lines[j]} for j in range(max(0,i-1),min(len(lines),i+2))]})
result={'schema':1,'started_utc':started,'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'repo_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'selected_file_count':len(files),'matched_line_count':len(hits),'files':files,'matches':hits,'scope':'Remaining tracked project documentation/configuration; no vendored kernel, historical evidence/results, auth/key/account material, execution-host or runtime probes.'}
(OUT/'supplemental-scan.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('started_utc','completed_utc','repo_head','script_sha256','selected_file_count','matched_line_count')}))
for hit in hits:print(f"{hit['path']}:{hit['line']}: {hit['text']}")
