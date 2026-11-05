#!/usr/bin/python3 -I
"""Read saved delete output and fresh exact row/directory state; no action replay."""
from pathlib import Path
import argparse,hashlib,json,os,types
OUT=Path('/home/alex/work/pocket4-gallery-cleanup-reconcile-20261105-r12-04')
FLOW=Path('/home/alex/work/pocket4-gallery-tools-20261105-r12-01/run_gallery01.py')
FLOW_SHA='1373820f8c1a39203bb764d3b5f5859b1ef91387cc4b04fb564d4d4d3cd7f40e'
OLD=Path('/home/alex/work/pocket4-gallery-cleanup-20261105-r12-03')
def need(ok,why):
    if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,pin,name):
    raw=path.read_bytes();need(sha(raw)==pin,'SOURCE_CHANGED')
    m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--collect',action='store_true');args=ap.parse_args()
    if not args.collect:print('INERT');return 0
    need(os.geteuid()==0 and OUT.parent.resolve()==OUT.parent,'ROOT_CANONICAL_REQUIRED')
    f=load(FLOW,FLOW_SHA,'gallery_read04');tx,base,doc,diag=[load(Path(p),pin,'g04_'+str(i)) for i,(p,pin) in enumerate(f.PINS.items())]
    old=json.loads(tx.read_regular(OLD/'result.json','f1315f0d0c57c18cd47691acc487fe982fcf70dd856cf2f92b6917eb0b614424',16384))
    OUT.mkdir(mode=0o750);os.chmod(OUT,0o750);os.chown(OUT,0,1000);(OUT/'ui').mkdir(mode=0o700)
    base.ROOT=OUT/'ui';base.PACKAGE=f.GALLERY;base.COMPONENT=f.COMPONENT;doc.PACKAGE=f.PACKAGE;doc.RUN=f.RUN
    result={'state':'FAILED','UI_actions':0,'provider_writes':0,'installs':0,'uninstalls':0,'old_result_preserved':True}
    try:
        receipts={}
        for suffix in ['exact-empty-directory-delete-intent','directory-delete-ack']:
            paths=list((OLD/'ui').glob('[0-9][0-9][0-9]-'+suffix+'.json'));need(len(paths)==1,'ONE_EXACT_SAVED_RECEIPT')
            raw=tx.read_regular(paths[0],maximum=32768);receipts[suffix]={'sha256':sha(raw),'name':paths[0].name,'value':json.loads(raw)}
        result['saved_receipts']=receipts
        with tx.CameraSession(OUT/'commands') as s:
            result['guard_before']=s.guard();need(result['guard_before']==old['guard_before'],'EPOCH_CHANGED')
            g=f.Gallery(s,tx,base,doc,diag,None)
            result['namespace']=g.namespace('namespace-now')
            result['children']=g.query('children-now',"SELECT _id FROM files WHERE parent=60 OR _data GLOB '"+f.GUEST_FOLDER+"/*' ORDER BY _id")
            result['original_media']=g.original_media('original-now')
            result['prefs']=g.prefs();result['installed_identity']=doc.identity(s,f.PACKAGE,f.APK_SHA)
            roots,tasks=g.ui.stacks('tasks-now');result['tasks']=sorted(tasks)
            result['old_owned_tasks_absent']=not bool({944,945}&(set(roots)|tasks))
            result['content_query']=s.android(['/system/bin/content','query','--user','0','--uri','content://media/external_primary/file/60',
                '--projection','_id:_data:_display_name:media_type:relative_path:owner_package_name'],15).decode()
            parent=s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                try:st=os.stat(f.FOLDER,dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:result['directory_absent']=True
                else:
                    result['directory_absent']=False;result['directory_identity']=f.fp(st)
                    fd=os.open(f.FOLDER,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                    try:result['directory_entries']=os.listdir(fd);need(f.fp(os.fstat(fd))==f.fp(st),'DIRECTORY_CHANGED')
                    finally:os.close(fd)
            finally:os.close(parent)
            result['guard_after']=s.guard();s.caller_status('gallery-reconcile-final')
        result['state']='EXACT_CLEANUP_OUTCOME_READBACK_COMPLETE'
    except BaseException as exc:result['error']=type(exc).__name__+':'+str(exc)
    tx.write_new(OUT/'result.json',result,alex_readable=True)
    print(json.dumps({'state':result['state'],'output':str(OUT/'result.json'),'error':result.get('error')}))
    return 0 if result['state']=='EXACT_CLEANUP_OUTCOME_READBACK_COMPLETE' else 1
if __name__=='__main__':raise SystemExit(main())
