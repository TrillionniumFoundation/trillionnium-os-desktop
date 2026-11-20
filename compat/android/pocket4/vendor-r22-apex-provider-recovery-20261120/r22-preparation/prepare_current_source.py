"""Create only a complete new producer from exact previously verified sources.

This performs no compilation, source materialization, install, or Android start.
The original 2359 producer and four reviewed remote postimages stay unchanged.
"""
from pathlib import Path
import hashlib, json, os, resource, signal, stat, sys, types, zipfile

ROOT=Path('/home/qq/work/current2367-cli-preparation-20261120-3b9d-r1')
OLD=Path('/home/qq/work/current2359-cli-preparation-20261120-9907-r1')
VENDOR=Path('/home/qq/work/p4-apex-test-provider-successor-20261120-3b9d-r1/candidate')
CURRENT={'tree':'fd0ef624e436d1eb5c8d2c4083335088811a6a42','files':2367,'bytes':45262277}
OLD_CURRENT={'tree':'4d78aae1aba2ec9952c37153069cca85c5a87953','files':2359,'bytes':44737433}
SOURCE_HELPER_SHA='e6a14326b1aa1ccc17d606c60bfc9bdf525f47bb2ccafffc86a054c55dd06219'
REMOTE_NAMES={'tools/droidloom-update/src/android.rs','tools/droidloom-update/src/framework_asb_security.rs',
              'tools/droidloom-update/src/settings_asb_security_tests.rs','tools/droidloom-update/src/wm_security.rs'}
def f9(s):return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def read(p, cap=8*1024**2):
    p=Path(p);assert p.resolve()==p
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=f9(os.fstat(fd))
        assert stat.S_ISREG(before[2]) and before[5]==1 and 0<=before[6]<=cap
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(cap+1)
        assert len(raw)==before[6] and before==f9(os.fstat(fd))==f9(p.lstat())
        return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'identity':before},raw
    finally:os.close(fd)
def write(p, raw, mode=0o600):
    assert p.parent.resolve()==p.parent and mode in (0o600,0o644,0o755)
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'wb') as out:
        out.write(raw);out.flush();os.fchmod(out.fileno(),mode);os.fsync(out.fileno())
    return read(p)[0]
def save(p,value):return write(p,(json.dumps(value,indent=2,sort_keys=True)+'\n').encode())

assert os.getuid()==os.geteuid()==os.getgid()==1000
cpus=os.sched_getaffinity(0);assert 18 in cpus and len(cpus)>=3
os.sched_setaffinity(0,{18})
resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
resource.setrlimit(resource.RLIMIT_CPU,(120,120))
resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
signal.alarm(150)
assert len(sys.argv)==4
archive=Path(sys.argv[1]);archive_ref,archive_raw=read(archive)
assert archive_ref['bytes']==int(sys.argv[2]) and archive_ref['sha256']==sys.argv[3]
with zipfile.ZipFile(archive) as z:
    names=z.namelist();assert len(names)==len(set(names))==28
    assert sum(i.file_size for i in z.infolist())<3*1024**2 and z.testzip() is None
    payload={}
    for info in z.infolist():
        p=Path(info.filename)
        assert not p.is_absolute() and str(p)==info.filename and all(v not in ('.','..') for v in p.parts)
        assert not info.is_dir() and not stat.S_ISLNK(info.external_attr>>16)
        payload[info.filename]=z.read(info.filename)
assert hashlib.sha256(payload['source_helpers.py']).hexdigest()==SOURCE_HELPER_SHA
helper=types.ModuleType('actual_original_source_helpers');helper.__file__=str(ROOT/'source_helpers.py')
exec(compile(payload['source_helpers.py'],helper.__file__,'exec'),helper.__dict__)
rows=json.loads(payload['SOURCE-ROWS.json']);assert len(rows)==CURRENT['files']
assert sum(r['bytes'] for r in rows)==CURRENT['bytes'] and helper.tree_id(rows)==CURRENT['tree']
old_rows_ref,raw=read(OLD/'SOURCE-ROWS.json')
assert (old_rows_ref['bytes'],old_rows_ref['sha256'])==(702120,'2aa08ae6144216b65beb2bc014f8a07e7436022fcca0c754fc86e0a1bcf663bd')
old_rows=json.loads(raw)
assert len(old_rows)==OLD_CURRENT['files'] and sum(r['bytes'] for r in old_rows)==OLD_CURRENT['bytes']
old_before=helper.source_snapshot(OLD/'producer',old_rows,OLD_CURRENT['tree'])
old_map={r['path']:r for r in old_rows};new_map={r['path']:r for r in rows}
assert set(old_map)<=set(new_map) and len(set(new_map)-set(old_map))==8
changed={name for name,row in new_map.items() if old_map.get(name)!=row}
assert len(changed)==28 and REMOTE_NAMES<=changed
assert set(payload)=={'source_helpers.py','SOURCE-ROWS.json','PUBLISHED-SOURCE.json','prepare_current_source.py'}|{
    'postimages/'+name for name in changed-REMOTE_NAMES}
published=json.loads(payload['PUBLISHED-SOURCE.json'])
assert published['source']==CURRENT and published['production_ready'] is published['runtime_qualified'] is False
remote_refs={}
for name in REMOTE_NAMES:
    ref,raw=read(VENDOR/name);helper.need(helper.digest(raw)=={k:new_map[name][k] for k in ('bytes','sha256')},'exact remote postimage')
    assert helper.object_id('blob',raw)==new_map[name]['git_blob'];remote_refs[name]=ref
helper.fresh_destination(ROOT,[OLD,VENDOR,archive])
ROOT.mkdir(mode=0o700);producer=ROOT/'producer';producer.mkdir(mode=0o700)
for name in ('source_helpers.py','SOURCE-ROWS.json','PUBLISHED-SOURCE.json'):
    write(ROOT/name,payload[name])
for row in rows:
    name=row['path'];target=producer/name
    if name not in changed:raw=helper.check(OLD/'producer'/name,row)
    elif name in REMOTE_NAMES:
        pin,raw=read(VENDOR/name);assert pin==remote_refs[name]
    else:raw=payload['postimages/'+name]
    assert helper.digest(raw)=={k:row[k] for k in ('bytes','sha256')} and helper.object_id('blob',raw)==row['git_blob']
    target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    write(target,raw,int(row['mode'],8)&0o777)
new_snapshot=helper.source_snapshot(producer,rows,CURRENT['tree'])
assert helper.source_snapshot(OLD/'producer',old_rows,OLD_CURRENT['tree'])==old_before
assert read(OLD/'SOURCE-ROWS.json')[0]==old_rows_ref and read(archive)[0]==archive_ref
for ref in remote_refs.values():assert read(ref['path'])[0]==ref
result={'schema':'p4-current2367-complete-source-preparation-v1','source':CURRENT,
        'source_path':str(producer),'original_source':OLD_CURRENT,'original_source_path':str(OLD/'producer'),
        'original_rows':old_rows_ref,'archive':archive_ref,'published_source':published,
        'all_original_source_members_unchanged':True,'whole_new_source_verified':True,
        'changed_from_2359':sorted(changed),'added_from_2359':sorted(set(new_map)-set(old_map)),
        'remote_postimages':remote_refs,'source_snapshot':new_snapshot,
        'original_snapshot':old_before,'current_ci_consumed':False,'binaries_executed':0,
        'compilation_performed':False,'Android_builds':0,'Android_starts':0,
        'runtime_qualified':False,'production_ready':False}
pin=save(ROOT/'SOURCE_FREEZE.json',result)
print(json.dumps({'source':CURRENT,'freeze':pin,'all_original_source_unchanged':True,
                  'current_ci_consumed':False,'runtime_qualified':False,'production_ready':False}),flush=True)
