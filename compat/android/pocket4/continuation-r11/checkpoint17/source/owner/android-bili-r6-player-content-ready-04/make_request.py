#!/usr/bin/env python3
"""Generate a create-only exact request. This program never dispatches it."""
import argparse
import hashlib
import json
import os
import types
from pathlib import Path

HERE=Path(__file__).resolve().parent
KEY='pocket4-bilibili-r6-player-content-ready04-20261105'
ROOT='/home/alex/work/pocket4-bilibili-r6-pause-resume-04'
NONCE='a14743fa3566f851b6724a54b0509744'


def sha(raw):
 return hashlib.sha256(raw).hexdigest()


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--write-once',action='store_true')
 parser.add_argument('--source-manifest-sha256')
 parser.add_argument('--output',type=Path)
 args=parser.parse_args()
 if not args.write_once:
  print(json.dumps({'state':'PLAN_ONLY','stable_key':KEY,'remote_actions':0}))
  return 0
 raw=(HERE/'SOURCE_PINS.json').read_bytes()
 assert sha(raw)==args.source_manifest_sha256
 manifest=json.loads(raw);files={}
 for name,row in manifest['files'].items():
  data=(HERE/name).read_bytes()
  assert row=={'bytes':len(data),'sha256':sha(data)}
  files[name]=data.decode('utf-8')
 files['SOURCE_PINS.json']=raw.decode('utf-8')
 entry=types.ModuleType('owned_r2_inspect_admission');entry.__file__=str(HERE/'owned_navigation.py')
 exec(compile(files['owned_navigation.py'],entry.__file__,'exec'),entry.__dict__)
 entry.require_actual_install_binding()
 entry.fixed_plan()
 packet={'schema':1,'source_manifest_sha256':args.source_manifest_sha256,'nonce':NONCE,'files':files}
 payload=(json.dumps(packet,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode()
 assert 0<len(payload)<=131072
 stage_sha=manifest['files']['stage_execute.py']['sha256']
 wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(131073)\n"
 wrapper+="assert hashlib.sha256(raw).hexdigest()=="+repr(sha(payload))+"\n"
 wrapper+="p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n"
 wrapper+="assert hashlib.sha256(src).hexdigest()=="+repr(stage_sha)+"\n"
 wrapper+="scope={'__name__':'owned_bili_inspect_stage','__file__':"+repr(ROOT+'/source/stage_execute.py')+"}\n"
 wrapper+="exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n"
 request={'host':'pocket4','executable':'/usr/bin/sudo',
  'args':['-n','/usr/bin/python3','-I','-c',wrapper],
  'cwd':'/home/alex/work','env':{'PYTHONDONTWRITEBYTECODE':'1'},
  'stdin':payload.decode('utf-8'),'idempotency_key':KEY,'timeout_seconds':600,
  'cpu_quota_percent':100,'memory_max_bytes':536870912,'nice':10}
 encoded=(json.dumps(request,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode()
 assert args.output is not None
 fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'wb',closefd=False)as stream:
   stream.write(encoded);stream.flush();os.fsync(fd)
 finally:
  os.close(fd)
 print(json.dumps({'state':'EXACT_REQUEST_NOT_SUBMITTED','path':str(args.output),
  'bytes':len(encoded),'sha256':sha(encoded),'stdin_bytes':len(payload),
  'stdin_sha256':sha(payload),'stable_key':KEY}))
 return 0


if __name__=='__main__':
 raise SystemExit(main())
