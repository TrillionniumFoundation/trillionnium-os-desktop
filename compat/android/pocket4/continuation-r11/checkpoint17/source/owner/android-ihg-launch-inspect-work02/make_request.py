#!/usr/bin/env python3
"""Freeze an exact owned IHG launch/inspect request; never dispatch."""
import argparse,hashlib,json,os
from pathlib import Path
HERE=Path(__file__).resolve().parent
MANIFEST_SHA='abb667a93f1e55b916da3b04bcebe05b28904655ff18cff1a1f1ef8b66a7b845'
STAGE_SHA='e857c5a50a821f72fb2de0637df894673bd8560851f31c8e192e4b4ec3470200'
STAGE_BYTES=4915
NONCE='399444a5b72d53139b880a4afefdb31a'
KEY='pocket4-ihg-owned-launch-inspect-01-20261105'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--write-once',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
    if not a.write_once:
        print(json.dumps({'state':'PLAN_ONLY','stable_key':KEY,'nonce':NONCE,'device_calls':0,'submitted':False}));return 0
    raw=(HERE/'SOURCE_PINS.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==MANIFEST_SHA
    manifest=json.loads(raw);assert set(manifest['files'])=={'owned_inspect.py','ihg_task_context.py','INPUTS.json'}
    files={'SOURCE_PINS.json':raw.decode()}
    for name,pin in manifest['files'].items():
        data=(HERE/name).read_bytes();assert 0<len(data)<=65536 and len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256'];files[name]=data.decode('utf-8')
    stage=(HERE/'stage_execute.py').read_bytes();assert len(stage)==STAGE_BYTES and hashlib.sha256(stage).hexdigest()==STAGE_SHA
    packet=(json.dumps({'schema':1,'nonce':NONCE,'files':files},ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    assert 0<len(packet)<=131072 and a.output is not None
    wrapper=('import hashlib,json,sys;raw=sys.stdin.buffer.read(131073);assert len(raw)=='+str(len(packet))+' and hashlib.sha256(raw).hexdigest()=='+repr(hashlib.sha256(packet).hexdigest())+';stage='+repr(stage.decode())+';assert hashlib.sha256(stage.encode()).hexdigest()=='+repr(STAGE_SHA)+';scope={"__name__":"amazon_fixed_task_stage","__file__":"<verified-amazon-task-stage>"};exec(compile(stage,"stage_execute.py","exec"),scope);raise SystemExit(scope["main"](json.loads(raw),'+repr(MANIFEST_SHA)+'))')
    request={'host':'pocket4','executable':'/usr/bin/sudo','args':['-n','/usr/bin/python3','-I','-c',wrapper],'cwd':'/home/alex/work','env':{'PYTHONDONTWRITEBYTECODE':'1'},'stdin':packet.decode(),'idempotency_key':KEY,'timeout_seconds':600,'cpu_quota_percent':100,'memory_max_bytes':536870912,'nice':10}
    encoded=(json.dumps(request,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        view=memoryview(encoded)
        while view:
            count=os.write(fd,view);assert count>0;view=view[count:]
        os.fsync(fd)
    finally:os.close(fd)
    print(json.dumps({'state':'EXACT_REQUEST_NOT_SUBMITTED','path':str(a.output),'bytes':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest(),'stdin_bytes':len(packet),'stdin_sha256':hashlib.sha256(packet).hexdigest(),'source_manifest_sha256':MANIFEST_SHA,'stable_key':KEY,'device_calls':0}))
    return 0
if __name__=='__main__':raise SystemExit(main())
