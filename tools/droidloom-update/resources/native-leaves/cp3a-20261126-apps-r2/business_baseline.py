"""Current native leaf comparison facade.

Actual Main/PM/data custody stays in the normal Rust owner. This fixed source
facade replaces the historical deployment-document factory; saved documents are
comparison data only and cannot create a Rust observation or a business gate.
"""
import hashlib
import os
from pathlib import Path
import stat
import types

ROOT=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2')
SOURCE=ROOT/'source/main/kernel_native_observation.py'
SOURCE_SHA='b61fdf6e13325a2e131f23314da51ca77e927b43a1d73875efaa3d4e526827e4'
META=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
def _load():
    for parent in SOURCE.parents:
        m=parent.lstat()
        if not stat.S_ISDIR(m.st_mode) or m.st_uid!=0 or m.st_gid!=0 or m.st_mode&0o022:
            raise RuntimeError('ROOT_PROTECTED_NORMAL_COMPARISON_SOURCE_REQUIRED')
    fd=os.open(SOURCE,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd);identity=tuple(getattr(before,k) for k in META)
        if not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_gid!=0 or \
           before.st_nlink!=1 or stat.S_IMODE(before.st_mode)!=0o444 or not 0<before.st_size<=1024*1024:
            raise RuntimeError('EXACT_NORMAL_COMPARISON_SOURCE_REQUIRED')
        raw=os.pread(fd,1024*1024+1,0)
        if len(raw)!=before.st_size or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA or \
           identity!=tuple(getattr(os.fstat(fd),k) for k in META) or \
           identity!=tuple(getattr(SOURCE.lstat(),k) for k in META):
            raise RuntimeError('NORMAL_COMPARISON_SOURCE_CHANGED')
    finally:os.close(fd)
    module=types.ModuleType('native_leaf_kernel_comparisons');module.__file__=str(SOURCE)
    exec(compile(raw,str(SOURCE),'exec'),module.__dict__)
    return module
_current=_load()
SCHEMA=_current.SCHEMA
QUAL_SCHEMA=_current.QUAL_SCHEMA
BusinessBaseline=_current.BusinessBaseline

def current_channel():
    return _current.channel()
