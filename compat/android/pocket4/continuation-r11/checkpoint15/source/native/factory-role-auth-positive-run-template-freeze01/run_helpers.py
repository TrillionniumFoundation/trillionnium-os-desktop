def verify_rows(rows):
    changed=[]
    for row in rows:
        try:
            requested=Path(row['requested_path']);resolved=requested.resolve(strict=True)
            current=hash_held(resolved)
            if str(resolved)!=row['resolved_path'] or current!={k:row[k] for k in ['path','bytes','sha256','identity']}:
                changed.append(str(requested))
        except Exception as error:changed.append({'path':row['requested_path'],'error':str(error)})
    return changed

def held_executable(path,expected):
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd);require(stat.S_ISREG(st.st_mode) and st.st_mode&0o111 and st.st_size<=8*1024*1024,'bounded regular executable required')
        digest=hashlib.sha256();total=0;magic=None
        while True:
            raw=os.read(fd,65536)
            if not raw:break
            if magic is None:magic=raw[:4]
            total+=len(raw);digest.update(raw)
        pin={'path':str(path),'bytes':total,'sha256':digest.hexdigest(),'identity':identity(st)}
        require(magic==b'\x7fELF' and pin==expected and identity(st)==identity(os.fstat(fd))==identity(path.lstat()),
                'held runtime executable differs from actual matching build')
        require(fcntl.fcntl(fd,fcntl.F_GETFD)&fcntl.FD_CLOEXEC,'held ELF must close across exec')
        return fd,pin
    except BaseException:os.close(fd);raise
