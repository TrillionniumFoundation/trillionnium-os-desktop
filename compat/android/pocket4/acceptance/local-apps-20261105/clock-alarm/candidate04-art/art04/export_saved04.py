"""Export only metadata saved by the completed Clock ART04 job; no Main access."""
from pathlib import Path
import gzip,hashlib,json,os,stat
ROOT=Path('/home/alex/work/pocket4-clock-alarm-art-20261105-r12-04')
OUT=ROOT/'publication-export01'
RESULT_SHA='cb6ebadca9c9736ce9e60877f13d33698d5f7a1bb918ae178e37d7c6da697ac9'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(name):
    p=ROOT/name
    assert p.resolve(strict=True)==p
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        st=os.fstat(fd)
        assert stat.S_ISREG(st.st_mode) and st.st_uid==0 and st.st_nlink==1 and 0<st.st_size<=2*1024*1024
        raw=b''
        while len(raw)<st.st_size:
            part=os.read(fd,min(65536,st.st_size-len(raw)));assert part;raw+=part
        after=os.fstat(fd)
        assert (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
        return raw
    finally:os.close(fd)
def put(name,raw):
    fd=os.open(OUT/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno());os.fchown(stream.fileno(),0,1000);os.fchmod(stream.fileno(),0o640)
assert os.geteuid()==0 and not os.path.lexists(OUT)
raw=read('result.json');assert sha(raw)==RESULT_SHA
r=json.loads(raw)
assert r['state']=='ALL_FOUR_MODIFIED_CLOCK_CLASSES_ART_VERIFIED_NOT_INSTALLED' and not r['installed']
names=['before.json','after.json','shared-before.json','shared-after.json','target-statuses.json']
assets={n:read(n) for n in names}
assert assets['before.json']==assets['after.json'] and assets['shared-before.json']==assets['shared-after.json']
assert json.loads(assets['target-statuses.json'])==r['target_status_proof']
bundle={'source_result_sha256':RESULT_SHA,'files':{n:{'sha256':sha(v),'bytes':len(v),'utf8':v.decode('utf-8','strict')} for n,v in assets.items()}}
data=(json.dumps(bundle,sort_keys=True,separators=(',',':'))+'\n').encode();compressed=gzip.compress(data,mtime=0)
assert len(data)<=2*1024*1024 and len(compressed)<=65536
os.umask(0o077);OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
put('metadata.json.gz',compressed)
receipt={'state':'COMPLETED_ART_SAVED_METADATA_EXPORTED','source_result_sha256':RESULT_SHA,
    'files':{n:{'bytes':len(v),'sha256':sha(v)} for n,v in assets.items()},
    'compressed_bytes':len(compressed),'compressed_sha256':sha(compressed),
    'path':str(OUT/'metadata.json.gz'),'Android_commands':0,'UI_actions':0,'Main_reads':0}
put('receipt.json',(json.dumps(receipt,indent=2,sort_keys=True)+'\n').encode())
print(json.dumps(receipt,sort_keys=True))
