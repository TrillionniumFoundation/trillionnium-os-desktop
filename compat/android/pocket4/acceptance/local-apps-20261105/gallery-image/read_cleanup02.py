#!/usr/bin/python3 -I
"""Read the exact retained empty test directory, its receipts and one own PNG."""
from pathlib import Path
import argparse,hashlib,json,os,re,stat,types

OUT=Path('/home/alex/work/pocket4-gallery-cleanup-readonly-20261105-r12-02')
OLD=Path('/home/alex/work/pocket4-gallery-image-20261105-r12-01')
FLOW=Path('/home/alex/work/pocket4-gallery-tools-20261105-r12-01/run_gallery01.py')
FLOW_SHA='1373820f8c1a39203bb764d3b5f5859b1ef91387cc4b04fb564d4d4d3cd7f40e'
RESULT_SHA='eab3d43deddcb154e8b4f717761182df9b03f49d68f1b7826e4a5e9457c11f67'

def need(value,reason):
    if not value:raise RuntimeError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,pin,name):
    raw=path.read_bytes();need(sha(raw)==pin,'SOURCE_CHANGED')
    value=types.ModuleType(name);value.__file__=str(path);exec(compile(raw,str(path),'exec'),value.__dict__);return value

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--collect',action='store_true');args=ap.parse_args()
    if not args.collect:print('INERT');return 0
    need(os.geteuid()==0 and OUT.parent.resolve()==OUT.parent,'ROOT_CANONICAL_REQUIRED')
    f=load(FLOW,FLOW_SHA,'gallery_saved')
    tx,base,doc,diag=[load(Path(p),pin,'gallery_read_'+str(i)) for i,(p,pin) in enumerate(f.PINS.items())]
    prior=json.loads(tx.read_regular(OLD/'result.json',RESULT_SHA,65536))
    need(prior['business_scope_completed'] and prior['cleanup']['image_deleted']
        and prior['normal_closed_tasks']==prior['owned_tasks']==[944,945]
        and prior['pending_effect'] is None and prior['close_pending'] is None
        and not prior['install_pending'] and not prior['uninstall_pending'],'PRIOR_UNKNOWN_EFFECT')
    OUT.mkdir(mode=0o750);os.chmod(OUT,0o750);os.chown(OUT,0,1000);(OUT/'ui').mkdir(mode=0o700)
    base.ROOT=OUT/'ui';base.PACKAGE=f.GALLERY;base.COMPONENT=f.COMPONENT
    doc.PACKAGE=f.PACKAGE;doc.RUN=f.RUN
    result={'state':'FAILED','UI_actions':0,'installs':0,'provider_writes':0,'original_result_sha256':RESULT_SHA,
        'selected_receipts':{},'own_synthetic_image_export_only':True}
    try:
        for suffix in ['media-original-before','media-original-final','after-seed-joined-proof',
            'media-after-image-delete','global-owned-namespace-absent','media-namespace-before']:
            paths=list((OLD/'ui').glob('[0-9][0-9][0-9]-'+suffix+'.json'))
            need(len(paths)==1,'ONE_RETAINED_RECEIPT_REQUIRED:'+suffix)
            raw=tx.read_regular(paths[0],maximum=65536)
            result['selected_receipts'][suffix]={'name':paths[0].name,'sha256':sha(raw),'value':json.loads(raw)}
        expected_folder=result['selected_receipts']['after-seed-joined-proof']['value']['folder_identity']
        with tx.CameraSession(OUT/'commands') as s:
            g=f.Gallery(s,tx,base,doc,diag,None)
            result['guard_before']=s.guard();need(result['guard_before']==prior['guard_after'],'EPOCH_CHANGED')
            result['installed_identity']=doc.identity(s,f.PACKAGE,f.APK_SHA)
            need(result['installed_identity']==prior['installed_identity'],'FIXTURE_IDENTITY_CHANGED')
            result['owned_preferences']=g.prefs()
            need(result['owned_preferences']['phase']=='DELETED' and result['owned_preferences']['pending']=='','MEDIA_STATE_CHANGED')
            result['namespace']=g.namespace('current')
            need(result['namespace']==[prior['owned_directory_index_retained']],'EXACT_DIRECTORY_INDEX_CHANGED')
            result['children']=g.query('children',"SELECT _id FROM files WHERE parent=60 OR _data GLOB '"+f.GUEST_FOLDER+"/*' ORDER BY _id")
            need(result['children']==[],'DIRECTORY_CHILD_ROW_PRESENT')
            result['image_absence']=g.query('image61',"SELECT _id FROM files WHERE _id=61")
            need(result['image_absence']==[],'DELETED_IMAGE_ROW_RETURNED')
            g.folder_parent=s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            g.folder_fd=os.open(f.FOLDER,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=g.folder_parent)
            g.folder_birth=expected_folder
            try:need(g.held_folder()==[],'EXACT_OWNED_DIRECTORY_NOT_EMPTY');result['directory_identity']=g.folder_birth
            finally:os.close(g.folder_fd);os.close(g.folder_parent)
            original=g.original_media('original-now')
            need(original==result['selected_receipts']['media-original-before']['value']['rows']
                ==result['selected_receipts']['media-original-final']['value']['rows'],'ORIGINAL_MEDIA_CHANGED')
            result['original_image_video_metadata_unchanged']=True
            roots,tasks=g.ui.stacks('current-task-absence')
            need(not {944,945}&(set(roots)|tasks) and not any(c['component'].split('/')[0] in (f.GALLERY,f.PACKAGE)
                for r in roots.values() for c in r['children']),'OWNED_TASK_RETURNED')
            result['task_ids']=sorted(tasks)
            result['content_query']=s.android(['/system/bin/content','query','--user','0','--uri',
                'content://media/external_primary/file/60','--projection','_id:_data:_display_name:media_type:relative_path:owner_package_name'],15).decode()
            helpcmd=['/system/bin/env','-i']+[k+'='+s.environment[k] for k in sorted(s.environment)]
            helpcmd+=['/system/xbin/su','2000','/system/bin/timeout','-k','2','10','/system/bin/content','--help']
            with s.target.entry(helpcmd) as (argv,fds):help_result=s.run_host('content-help',argv,14,fds)
            result['content_help']={k:help_result[k] for k in ('rc','joined','timed_out')}
            result['content_help'].update(stdout=help_result['stdout'].decode(),stderr=help_result['stderr'].decode())
            result['gallery_identity']=g.gallery_identity();need(result['gallery_identity']==prior['gallery_after'],'GALLERY_IDENTITY_CHANGED')
            result['guard_after']=s.guard();s.caller_status('gallery-readonly-caller')
        picture=tx.read_regular(OLD/'owned-image-0-0.png','1c03ef3592e260453e37b286662f30779d7674013e4bb1648250357f0ea274d4',1048576)
        tx.write_new(OUT/'owned-image.png',picture,alex_readable=True)
        result['own_image_export']={'path':str(OUT/'owned-image.png'),'bytes':len(picture),'sha256':sha(picture)}
        result['state']='EXACT_EMPTY_DIRECTORY_READBACK_COMPLETE'
    except BaseException as exc:result['error']=type(exc).__name__+':'+str(exc)
    tx.write_new(OUT/'result.json',result,alex_readable=True)
    print(json.dumps({'state':result['state'],'result':str(OUT/'result.json'),'error':result.get('error')}))
    return 0 if result['state']=='EXACT_EMPTY_DIRECTORY_READBACK_COMPLETE' else 1

if __name__=='__main__':raise SystemExit(main())
