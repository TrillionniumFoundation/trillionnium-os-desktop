import hashlib,json,os,stat,sys,time
EXPECTED_BYTES=728003
EXPECTED_SHA="5cc813715a261701cad3be931b9e53145229dec7c803d828a1097e4fe4ad166b"
DEADLINE=time.monotonic()+8
def need(value,code):
    if not value:raise RuntimeError(code)
def stamp(s):
    return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def check():
    need(time.monotonic()<DEADLINE,"FIXED_READ_DEADLINE")
fds=[];first=None;close_errors=[];raw=None
try:
    need(os.getuid()==os.geteuid()==0,"OWN_STATIC_RESULT_ROOT_READ_REQUIRED")
    d=os.open("/",os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC);fds.append(d)
    for name in ("opt","p4-owner20-sdk-visibility-android-20261106-build-02"):
        check();parent=d
        d=os.open(name,os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent);fds.append(d)
        meta=os.fstat(d)
        need(stat.S_ISDIR(meta.st_mode) and meta.st_uid==0 and not(meta.st_mode&0o022),"OWN_STATIC_RESULT_DIRECTORY")
    fd=os.open("build-result.json",os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d);fds.append(fd)
    before=os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and before.st_uid==0 and before.st_nlink==1 and not(before.st_mode&0o6022) and before.st_size==EXPECTED_BYTES,"OWN_STATIC_RESULT_FILE")
    parts=[];count=0
    while True:
        check();part=os.read(fd,min(131072,EXPECTED_BYTES+1-count))
        if not part:break
        count+=len(part);need(count<=EXPECTED_BYTES,"FIXED_RESULT_BYTE_BOUND");parts.append(part)
    raw=b"".join(parts)
    need(len(raw)==EXPECTED_BYTES and hashlib.sha256(raw).hexdigest()==EXPECTED_SHA,"EXACT_ORIGINAL_BUILD_RESULT")
    need(stamp(before)==stamp(os.fstat(fd))==stamp(os.stat("build-result.json",dir_fd=d,follow_symlinks=False)),"RESULT_HELD_AND_NAMED_UNCHANGED")
except BaseException as error:
    first=error
finally:
    for fd in reversed(fds):
        try:os.close(fd)
        except BaseException as error:close_errors.append(type(error).__name__)
if first is not None:raise first
need(not close_errors,"RESULT_DESCRIPTOR_CLOSE_FAILED")
check()
meta={"schema":1,"state":"EXACT_STATIC_RESULT_HELD_AND_NAMED_READ_PASS","bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"file":{k:getattr(before,k) for k in ("st_dev","st_ino","st_mode","st_uid","st_gid","st_nlink","st_size","st_mtime_ns","st_ctime_ns")},"fds_closed":len(fds),"filesystem_writes":0,"Main_actions":0,"Android_actions":0}
os.write(sys.stderr.fileno(),(json.dumps(meta,sort_keys=True)+"\n").encode())
check();offset=0
while offset<len(raw):
    check();written=os.write(sys.stdout.fileno(),raw[offset:])
    need(written>0,"RESULT_STDOUT_SHORT_WRITE");offset+=written
