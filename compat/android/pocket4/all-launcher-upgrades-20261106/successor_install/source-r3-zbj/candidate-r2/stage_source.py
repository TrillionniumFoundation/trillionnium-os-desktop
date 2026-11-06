import sys
sys.dont_write_bytecode=True
import os,stat,json,hashlib,subprocess,time,datetime
ROOT='/home/alex/work/pocket4-successor-install-source-20261106-r3-zbj-r2'
NAMES={'install_successor_native.py','s42-failed-result.original.json','s43-result.original.json','s43-terminal.original.json','scope47.original.json','test_install_successor_r3_zbj.py'}
STAT=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
def require(value,reason):
    if not value:raise RuntimeError(reason)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
def meta(fd):
    s=os.fstat(fd);return {k:getattr(s,k)for k in STAT}
def open_directory(path):
    fds=[]
    try:
        d=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fds.append(d)
        for p in path[1:].split('/'):
            require(p not in ('','.','..'),'CANONICAL_PATH')
            d=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=d);fds.append(d)
        for old in fds[:-1]:os.close(old)
        return d
    except BaseException:
        for f in fds:
            try:os.close(f)
            except OSError:pass
        raise
def write(d,name,raw):
    require('/'not in name and name not in ('.','..'),'CLOSED_NAME')
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o400,dir_fd=d)
    try:
        view=memoryview(raw)
        while view:
            n=os.write(fd,view);require(n>0,'WRITE_PROGRESS');view=view[n:]
        os.fsync(fd)
    finally:os.close(fd)
    os.fsync(d)
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=d)
    try:
        before=meta(fd);data=b''
        while True:
            block=os.read(fd,65536)
            if not block:break
            data+=block;require(len(data)<=len(raw),'READ_BOUND')
        require(before==meta(fd)and data==raw,'SOURCE_READBACK')
    finally:os.close(fd)
    return {'path':ROOT+'/'+name,'bytes':len(raw),'sha256':digest(raw)}
require(os.getuid()==os.geteuid()==0,'ROOT_OWNED_SOURCE_ONLY')
os.umask(0o077);count_before=len(os.listdir('/proc/self/fd'))
payload_raw=sys.stdin.buffer.read(1048577);require(len(payload_raw)<=1048576,'PAYLOAD_BOUND')
payload=json.loads(payload_raw)
require(set(payload)=={'files','stager_source'}and set(payload['files'])==NAMES,'EXACT_SOURCE_CLOSURE')
require(all(type(x)is str and 0<len(x.encode())<=100000 for x in payload['files'].values()),'SOURCE_SIZE_BOUND')
parent=open_directory('/home/alex/work')
try:
    os.mkdir(ROOT.rsplit('/',1)[1],0o700,dir_fd=parent);os.fsync(parent)
finally:os.close(parent)
d=open_directory(ROOT)
result={'schema':'pocket4-installer-revision3-zbj-source-host-controls-v1','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'runtime_or_Main_reads':0,'native_commands':0,'Android_commands':0,'UI_actions':0,'installs':0,
    'permission_changes':0,'existing_files_modified':0,'production_ready':False,'files':{},'tests':[],'ok':False}
try:
    result['stager']=write(d,'stage_source.py',payload['stager_source'].encode())
    result['payload']=write(d,'stage_payload.json',payload_raw)
    for name,content in sorted(payload['files'].items()):
        raw=content.encode();result['files'][name]=write(d,name,raw)
        if name.endswith('.py'):compile(raw,ROOT+'/'+name,'exec')
    pins={'schema':'pocket4-installer-revision3-zbj-source-prep-v1','files':{n:{k:r[k]for k in ('bytes','sha256')}for n,r in result['files'].items()}}
    result['manifest']=write(d,'SOURCE_PINS.json',canonical(pins)+b'\n')
    for name in ('test_install_successor_r3_zbj.py',):
        cp=subprocess.run(['/usr/bin/python3','-B','-I',ROOT+'/'+name],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False,cwd=ROOT,
            env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC'},close_fds=True,start_new_session=True)
        require(len(cp.stdout)<=65536 and len(cp.stderr)<=65536,'TEST_OUTPUT_BOUND')
        row={'name':name,'returncode':cp.returncode,'joined':True,
            'stdout':write(d,name+'.stdout',cp.stdout),'stderr':write(d,name+'.stderr',cp.stderr)}
        result['tests'].append(row)
    result['ok']=all(r['returncode']==0 for r in result['tests'])and len(result['tests'])==1
except BaseException as e:
    result['error']={'type':type(e).__name__,'reason':str(e)[:256]}
finally:
    os.close(d)
result['FDs_before']=count_before;result['FDs_after']=len(os.listdir('/proc/self/fd'))
result['ok']=result['ok']and result['FDs_before']==result['FDs_after']
result['ended_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
d=open_directory(ROOT)
try:pin=write(d,'result.json',canonical(result)+b'\n')
finally:os.close(d)
print(json.dumps({'result':result,'result_artifact':pin},sort_keys=True,separators=(',',':')),flush=True)
raise SystemExit(0 if result['ok']else 1)
