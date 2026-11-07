def read_exact_file(path,limit,pin=None,expected_identity=None):
    path=str(path)
    need(path.startswith('/') and not path.startswith('//') and '\0' not in path and
         all(x not in ('','.','..') for x in path[1:].split('/')),'EXACT_FILE_PATH_GRAMMAR')
    fds=[]
    first=None
    errors=[]
    deadline=time.monotonic()+10
    try:
        directory=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC)
        fds.append(directory)
        parts=path[1:].split('/')
        for component in parts[:-1]:
            need(time.monotonic()<deadline,'FIXED_FILE_DEADLINE')
            directory=os.open(component,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                              dir_fd=directory)
            fds.append(directory)
        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
        fds.append(fd)
        before=os.fstat(fd)
        keys=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and
             0<=before.st_size<=limit,'FIXED_REGULAR_FILE_BOUND')
        if expected_identity is not None:
            actual={k:getattr(before,v) for k,v in {
                'device':'st_dev','inode':'st_ino','mode':'st_mode','uid':'st_uid',
                'gid':'st_gid','nlink':'st_nlink','bytes':'st_size',
                'mtime_ns':'st_mtime_ns','ctime_ns':'st_ctime_ns'}.items()}
            need(type(expected_identity) is dict and actual==expected_identity,
                 'FIXED_ACTUAL_INPUT_IDENTITY_CHANGED')
        chunks=[]
        count=0
        while True:
            need(time.monotonic()<deadline,'FIXED_FILE_DEADLINE')
            part=os.read(fd,min(65536,limit+1-count))
            if not part:
                break
            count+=len(part)
            need(count<=limit,'FIXED_FILE_GREW')
            chunks.append(part)
        raw=b''.join(chunks)
        after=os.fstat(fd)
        named=os.stat(parts[-1],dir_fd=directory,follow_symlinks=False)
        need(len(raw)==before.st_size and
             all(getattr(x,k)==getattr(before,k) for x in (after,named) for k in keys),
             'FIXED_HELD_NAMED_FILE_CHANGED')
        if pin is not None:
            need(set(pin)=={'bytes','sha256'} and len(raw)==pin['bytes'] and sha(raw)==pin['sha256'],
                 'FIXED_WHOLE_FILE_PIN_CHANGED')
        return raw
    except BaseException as error:
        first=error
        raise
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except BaseException as close_error:
                errors.append(type(close_error).__name__)
        if errors:
            if first is None:
                raise RuntimeError('FIXED_FILE_FD_CLOSE_FAILED')
            first.add_note('FIXED_FILE_FD_CLOSE_FAILED')
