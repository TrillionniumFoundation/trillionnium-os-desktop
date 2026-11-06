import os,stat,sys,json,hashlib,base64,zlib
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
def meta(fd):
    s=os.fstat(fd);return {k:getattr(s,k)for k in FIELDS}
def opened(path):
    fs=[]
    try:
        p=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC);fs.append(p)
        parts=path[1:].split('/')
        assert path.startswith('/home/alex/work/pocket4-')and all(x not in ('','.','..')for x in parts)
        for n in parts[:-1]:
            p=os.open(n,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=p);fs.append(p)
        f=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=p);fs.append(f)
        return fs,f
    except BaseException:
        for f in reversed(fs):os.close(f)
        raise
pins=json.loads(sys.stdin.read(65537));assert type(pins)is list and 0<len(pins)<=12
before=len(os.listdir('/proc/self/fd'));total=0
for pin in pins:
    assert set(pin)=={'path','bytes','sha256'}and 0<pin['bytes']<=65536
    total+=pin['bytes'];assert total<=131072
    fs,fd=opened(pin['path'])
    try:
        a=meta(fd);assert stat.S_ISREG(a['st_mode'])and a['st_nlink']==1 and a['st_size']==pin['bytes']
        raw=b''
        while len(raw)<=pin['bytes']:
            b=os.read(fd,min(65536,pin['bytes']+1-len(raw)))
            if not b:break
            raw+=b
        assert meta(fd)==a and len(raw)==pin['bytes']and hashlib.sha256(raw).hexdigest()==pin['sha256']
        other,g=opened(pin['path'])
        try:assert meta(g)==a
        finally:
            for f in reversed(other):os.close(f)
        print(json.dumps({'pin':pin,'stat':a,'zlib_base64':base64.b64encode(zlib.compress(raw,9)).decode('ascii')},sort_keys=True,separators=(',',':')),flush=True)
    finally:
        for f in reversed(fs):os.close(f)
assert len(os.listdir('/proc/self/fd'))==before
print(json.dumps({'schema':'pocket4-fixed-host-source-compressed-read-v1','files':len(pins),'bytes':total,'FDs_before':before,'FDs_after':len(os.listdir('/proc/self/fd')),'Main_reads':0,'writes':0}),flush=True)
