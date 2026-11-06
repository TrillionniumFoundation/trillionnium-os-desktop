#!/usr/bin/python3 -I
"""Read only frozen failed Gallery04 saved album title records; no live device or UI calls."""
from pathlib import Path
import base64,gzip,hashlib,json,os,re,stat
SOURCE=Path('/home/alex/work/pocket4-gallery-rotation-flow-20261105-r12-04')
OUT=Path('/home/alex/work/pocket4-gallery-rotation-saved-title04-20261105-r12-01')
RESULT_SHA='cdfddcb66b2ad720569d97943467f5180f45d5301174af494191daf76d972e66'
PACKAGE='org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03'
GALLERY='com.android.gallery3d'

def sha(raw):return hashlib.sha256(raw).hexdigest()

def need(ok,reason):
    if not ok:raise RuntimeError(reason)

def readat(parent,name,limit):
    fd=os.open(name,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid==0 and before.st_nlink==1
            and 0<=before.st_size<=limit,'SAVED_REGULAR_FILE_BOUND')
        parts=[];left=before.st_size
        while left:
            raw=os.read(fd,min(left,65536));need(raw,'SHORT_SAVED_READ');parts.append(raw);left-=len(raw)
        after=os.fstat(fd)
        need(all(getattr(before,k)==getattr(after,k) for k in ('st_dev','st_ino','st_uid','st_gid',
            'st_mode','st_size','st_nlink','st_mtime_ns','st_ctime_ns')),'SAVED_FILE_CHANGED')
        return b''.join(parts)
    finally:os.close(fd)

def write(name,raw):
    fd=os.open(OUT/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
    with os.fdopen(fd,'wb') as value:
        value.write(raw);value.flush();os.fsync(value.fileno());os.fchown(value.fileno(),0,1000)
        os.fchmod(value.fileno(),0o640)

need(os.geteuid()==0 and not os.path.lexists(OUT),'NEW_SAVED_HOST_OUTPUT_REQUIRED')
root=os.open(SOURCE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
ui=commands=None
artifacts={}
def artifact(parent,directory,name,limit):
    raw=readat(parent,name,limit)
    need(sum(v['bytes'] for v in artifacts.values())+len(raw)<=1048576,'COMBINED_SAVED_ROUTE_BOUND')
    artifacts[directory+'/'+name]={'bytes':len(raw),'sha256':sha(raw),'data_base64':base64.b64encode(raw).decode()}
    return raw
try:
    original=readat(root,'result.json',65536);need(sha(original)==RESULT_SHA,'FIXED_ORIGINAL_RESULT_CHANGED')
    result=json.loads(original)
    need(result['state']=='FAILED' and result['error']=='RuntimeError:EXACT_OWNED_ALBUM_TITLE_REQUIRED'
        and result['normal_closed_tasks']==[1011] and result['rotation_input_calls']==0
        and result['installed_identity']['uid']==10199 and result['temporary_package']==PACKAGE
        and result['client_pending'] is None and result['native_pending']=={} and result['owned_tasks']=={}
        and result['cleanup']['errors']==[] and result['cleanup']['task_set_restored'] is True
        and result['cleanup']['media_cleanup']['owned_image_rows_absent'] is True
        and result['cleanup']['media_cleanup']['physical_and_indexed_owned_directories_absent'] is True
        and result['cleanup']['package_cleanup']['package_absent_verified'] is True,
        'EXACT_CLEAN_FAILED_GALLERY04_RESULT_REQUIRED')
    ui=os.open('ui',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root)
    commands=os.open('commands',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root)
    for fd in (root,ui,commands):
        value=os.fstat(fd);need(stat.S_ISDIR(value.st_mode) and value.st_uid==0 and not value.st_mode&0o022,'OWNED_SAVED_DIRECTORY_REQUIRED')
    ui_names=sorted(os.listdir(ui));command_names=sorted(os.listdir(commands))
    need(len(ui_names)<=512 and len(command_names)<=1024,'SAVED_INVENTORY_BOUND')
    allowed=re.compile(r'[0-9]+-(?:original-task-baseline|before-client-launch|launch-1-(?:intent|receipt)|after-client-launch|client-round-1(?:-tasks)?|focus|album-client-action-intent|open-owned-album-1-(?:intent|response|no-effect)|album-route-before-admission|actual-owned-album-route|owned-album-1(?:-tasks)?)\.json')
    for name in ui_names:
        if allowed.fullmatch(name):artifact(ui,'ui',name,262144)
        elif re.fullmatch(r'[0-9]+-owned-album-1\.png',name):artifact(ui,'ui',name,524288)
    matches=[]
    for name in command_names:
        if not re.fullmatch(r'[0-9]+-android\.intent\.json',name):continue
        raw=readat(commands,name,65536);value=json.loads(raw);argv=value.get('argv',[])
        target=['/system/bin/dumpsys','activity','activities',GALLERY]
        if isinstance(argv,list) and len(argv)>=4 and argv[-4:]==target:
            stem=name[:-len('.intent.json')];matches.append(stem)
            for suffix in ('.intent.json','.result.json','.stdout','.stderr'):
                artifact(commands,'commands',stem+suffix,524288 if suffix=='.stdout' else 65536)
    need(len(matches)==1,'ONE_SAVED_EXACT_GALLERY_ACTIVITIES_QUERY_REQUIRED')
    need(any(n.endswith('-open-owned-album-1-response.json') for n in artifacts)
        and any(n.endswith('-actual-owned-album-route.json') for n in artifacts)
        and sum(n.endswith('-owned-album-1.json') for n in artifacts)==1
        and sum(n.endswith('-owned-album-1.png') for n in artifacts)==1,'SAVED_ACK_ROUTE_AND_OWNED_ALBUM_REQUIRED')
    need(sha(readat(root,'result.json',65536))==RESULT_SHA,'ORIGINAL_RESULT_CHANGED_AFTER_READ')
    report={'schema':'gallery04-saved-owned-title-v1','state':'SAVED_TITLE_RECORDS_EXPORTED',
        'source_result_sha256':RESULT_SHA,'Android_commands':0,'live_device_observations':0,
        'UI_actions':0,'provider_or_package_or_physical_mutations':0,'unknown_effect_reconciled':False,
        'source_query_stems':matches,'ui_file_inventory':ui_names,'artifacts':artifacts}
finally:
    if commands is not None:os.close(commands)
    if ui is not None:os.close(ui)
    os.close(root)
os.umask(0o077);OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
data=(json.dumps(report,indent=2,sort_keys=True)+'\n').encode();need(len(data)<=2097152,'FINAL_ROUTE_EXPORT_BOUND')
packed=gzip.compress(data,mtime=0);need(len(packed)<=262144,'COMPRESSED_ROUTE_EXPORT_BOUND')
write('result.json',data);write('result.json.gz',packed)
print(json.dumps({'state':report['state'],'result_path':str(OUT/'result.json'),
    'result_bytes':len(data),'result_sha256':sha(data),'gzip_path':str(OUT/'result.json.gz'),
    'gzip_bytes':len(packed),'gzip_sha256':sha(packed),'selected_records':len(artifacts),
    'Android_commands':0,'UI_actions':0},sort_keys=True))
