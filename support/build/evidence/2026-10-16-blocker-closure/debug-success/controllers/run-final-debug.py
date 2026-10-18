"""Preserve a foreign generated manifest before a new isolated debug retry."""
import ctypes
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile

root=Path('/workspace/scratch/ae1a8cf05419')
base=root/'a01-next9-native'
manifest=base/'kernel/asterinas/kernel/OSDK.toml'
receipt={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'source':str(manifest),'purpose':'Preserve the pre-existing untracked generated entry; do not delete it or attribute its writer'}
with (base/'support/build/out-kernel.lock').open('r+') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if os.path.lexists(manifest):
        custody=Path(tempfile.mkdtemp(prefix='preserved-manifest-',dir=root/'blocker-closure'))
        dest=custody/'OSDK.toml'
        libc=ctypes.CDLL(None,use_errno=True)
        rename=libc.renameat2
        rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        rename.restype=ctypes.c_int
        if rename(-100,os.fsencode(manifest),-100,os.fsencode(dest),1):
            code=ctypes.get_errno()
            raise OSError(code,os.strerror(code))
        info=dest.lstat()
        receipt.update(outcome='preserved_with_RENAME_NOREPLACE',custody=str(dest),
                       device=info.st_dev,inode=info.st_ino,mode=info.st_mode,
                       bytes=info.st_size,sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
    else:
        receipt['outcome']='no_existing_entry'
root.joinpath('blocker-closure/debug3-manifest-preservation.json').write_text(json.dumps(receipt,indent=2)+'\n')
sys.argv=[str(root/'blocker-closure/run-validation.py'),'debug3']
runpy.run_path(sys.argv[0],run_name='__main__')
