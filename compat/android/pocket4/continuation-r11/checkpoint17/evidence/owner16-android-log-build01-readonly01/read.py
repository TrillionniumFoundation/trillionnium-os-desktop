import hashlib, os, stat, sys
ROOT = "/opt/p4-owner16-init-log-android-20261105-build-01"
LEAF = "build-result.json"
EXPECTED_BYTES = 661519
EXPECTED_SHA = "2c53bba3ab02b396d2698dfd6e04d870ce69cc55724c6077003dca81ae9a2e0b"
def need(value, message):
    if not value: raise RuntimeError(message)
def stamp(s):
    return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
need(os.geteuid()==0 and os.getegid()==0,"read requires original root owner")
parent = fd = None
try:
    parent=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    root_before=os.fstat(parent)
    need(stat.S_ISDIR(root_before.st_mode) and root_before.st_uid==0 and not root_before.st_mode&0o22,"protected directory changed")
    fd=os.open(LEAF,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent)
    before=os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and before.st_uid==0 and before.st_nlink==1 and before.st_size==EXPECTED_BYTES,"fixed result metadata differs")
    chunks=[]; count=0
    while True:
        part=os.read(fd,min(65536,EXPECTED_BYTES+1-count))
        if not part:break
        chunks.append(part);count+=len(part)
        need(count<=EXPECTED_BYTES,"fixed result exceeds exact bound")
    raw=b"".join(chunks)
    need(len(raw)==EXPECTED_BYTES and hashlib.sha256(raw).hexdigest()==EXPECTED_SHA,"actual result pin differs")
    need(stamp(before)==stamp(os.fstat(fd))==stamp(os.stat(LEAF,dir_fd=parent,follow_symlinks=False)),"held or named result changed")
    need(stamp(root_before)==stamp(os.fstat(parent))==stamp(os.stat(ROOT,follow_symlinks=False)),"protected directory changed during read")
finally:
    if fd is not None:os.close(fd)
    if parent is not None:os.close(parent)
sys.stdout.buffer.write(raw)
sys.stdout.buffer.flush()
