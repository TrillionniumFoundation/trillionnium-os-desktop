"""Pinned successor guard; no discovery, adoption or action entry."""
import hashlib,os,stat,time,types,json
PINS = {'root': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01', 'manifest_sha': 'b97002660594ad0ef6e7b453927b8c5b19cba49a5873bc133199d790019b1f9f', 'baseline': {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/baseline.private.json', 'sha256': '7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8', 'bytes': 44041}, 'qualification': {'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/qualification.private.json', 'sha256': '4bdfe7dd1e275bc4727f37c630dc2498b3dc31c528b03a4028e42c1cf8fc4fc6', 'bytes': 1587}}
def _read(path,limit,pin):
    parts=path[1:].split('/')
    if not path.startswith('/') or any(x in ('','.','..') for x in parts):raise RuntimeError('GUARD_PATH')
    fds=[]
    try:
        d=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC);fds.append(d)
        for n in parts[:-1]:
            d=os.open(n,os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d);fds.append(d)
        f=os.open(parts[-1],os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d);fds.append(f)
        def meta(fd):
            s=os.fstat(fd)
            return tuple(getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))
        a=os.fstat(f);before=meta(f)
        if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or not 0<a.st_size<=limit:raise RuntimeError('GUARD_FILE')
        data=b'';end=time.monotonic()+5
        while len(data)<=limit:
            if time.monotonic()>end:raise RuntimeError('GUARD_DEADLINE')
            b=os.read(f,min(65536,limit+1-len(data)))
            if not b:break
            data+=b
        if len(data)!=a.st_size or meta(f)!=before or hashlib.sha256(data).hexdigest()!=pin:raise RuntimeError('GUARD_PIN')
        g=os.open(parts[-1],os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d);fds.append(g)
        if meta(g)!=before:raise RuntimeError('GUARD_PATH_REPLACED')
        return data
    finally:
        errors=[]
        for f in reversed(fds):
            try:os.close(f)
            except BaseException:errors.append(f)
        if errors:raise RuntimeError('GUARD_FD_CLOSE')
def _core():
    base=PINS['root']+'/source'
    manifest=json.loads(_read(base+'/SOURCE_PINS.json',65536,PINS['manifest_sha']))
    pin=manifest['files']['successor_runtime.py']
    raw=_read(base+'/successor_runtime.py',65536,pin['sha256'])
    m=types.ModuleType('pinned_successor_core');m.__file__=base+'/successor_runtime.py'
    exec(compile(raw,m.__file__,'exec'),m.__dict__)
    m.configure(base,PINS['manifest_sha'])
    return m
def current_baseline():
    m=_core()
    return m.parse(m.pinned_record(PINS['baseline']))
def current_guard(candidate=None,*,action_attempted=False):
    try:return _core().guard_check(PINS,candidate,action_attempted=action_attempted)
    except BaseException as e:
        e.action_attempted=action_attempted;e.outcome_unknown=action_attempted;e.automatic_retry=False
        raise
def check_app_scope(reference,packages):
    return _core().guard_check_apps(PINS,reference,packages)
