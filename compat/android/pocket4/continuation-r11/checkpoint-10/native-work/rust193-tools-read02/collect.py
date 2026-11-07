#!/usr/bin/env python3
"""Read the repository-selected installed toolchain; never install or update it."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import stat
import subprocess

ROOT=Path('/home/alex/work/pocket4-blueprint-streaming-builder-rust193-tools-readonly-02-20261105')
RUSTUP=Path('/home/alex/.cargo/bin/rustup')
REPOSITORY_TOOLCHAIN=Path('/home/alex/work/pocket4-signal-mask-r11-build-memory-01/builder-source/rust-toolchain.toml')
TOOLCHAIN='1.93.0'
RUSTUP_SHA='4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10'
CONFIG_SHA='8bc51ecab82415fddd8489604f2424e137d71856e7f65cbdcfaa48850d794b46'
ENV={'HOME':'/home/alex','PATH':'/usr/bin:/bin','CARGO_HOME':'/home/alex/.cargo',
     'RUSTUP_HOME':'/home/alex/.rustup','RUSTUP_TOOLCHAIN':TOOLCHAIN,
     'RUSTUP_SKIP_UPDATE_CHECK':'1','CARGO_NET_OFFLINE':'true','LC_ALL':'C'}

def identity(st):
    return [st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns]

def pin(path,resolve=True):
    original=Path(path)
    resolved=original.resolve(strict=True) if resolve else original
    allowed=[Path('/home/alex/.rustup/toolchains'),Path('/usr/bin'),Path('/usr/lib')]
    if not (any(resolved.is_relative_to(root) for root in allowed) or resolved in [RUSTUP,REPOSITORY_TOOLCHAIN,Path('/usr/libexec/gcc/x86_64-linux-gnu/15/collect2')]):
        raise RuntimeError('unexpected fixed query path: '+str(resolved))
    fd=os.open(resolved,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size>256*1024*1024:
            raise RuntimeError('bounded regular tool/config required')
        sha=hashlib.sha256();total=0
        while True:
            raw=os.read(fd,65536)
            if not raw: break
            total+=len(raw);sha.update(raw)
            if total>256*1024*1024: raise RuntimeError('tool grew beyond bound')
        if total!=before.st_size or identity(before)!=identity(os.fstat(fd)) or identity(before)!=identity(resolved.lstat()):
            raise RuntimeError('held tool/config changed')
        if resolve and original.resolve(strict=True)!=resolved:
            raise RuntimeError('tool resolution changed')
        return {'requested_path':str(original),'resolved_path':str(resolved),'bytes':total,
                'sha256':sha.hexdigest(),'held_before':identity(before),'held_after':identity(os.fstat(fd))}
    finally:
        os.close(fd)

def query(argv):
    proc=subprocess.run(argv,cwd='/',env=ENV,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,timeout=5,check=False)
    if len(proc.stdout)>32768 or len(proc.stderr)>32768:
        raise RuntimeError('query output exceeds bound')
    return {'argv':argv,'returncode':proc.returncode,'stdout':proc.stdout.decode(),'stderr':proc.stderr.decode()}

def main():
    if os.getuid()!=1000 or os.geteuid()!=1000:
        raise RuntimeError('operator UID1000 required')
    for p in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(p.lstat().st_mode):raise RuntimeError('evidence parent aliases non-directory')
    os.umask(0o077);ROOT.mkdir(mode=0o700)
    result={'schema':1,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'repository_channel':TOOLCHAIN,'Main_actions':0,'builds_started':0,'install_update_actions':0,
            'queries':[],'tools':[],'complete':False}
    try:
        config=pin(REPOSITORY_TOOLCHAIN,False)
        if config['sha256']!=CONFIG_SHA:raise RuntimeError('repository toolchain source changed')
        result['repository_toolchain']=config
        rustup=pin(RUSTUP)
        if rustup['sha256']!=RUSTUP_SHA:raise RuntimeError('observed rustup changed')
        result['tools'].append(rustup)
        selected={}
        for name in ['cargo','rustc']:
            row=query([str(RUSTUP),'which','--toolchain',TOOLCHAIN,name]);result['queries'].append(row)
            if row['returncode']!=0:raise RuntimeError('repository toolchain is not already installed: '+name)
            path=Path(row['stdout'].strip())
            if not path.is_absolute() or path.name!=name or path.parent.parent.name!=TOOLCHAIN+'-x86_64-unknown-linux-gnu' or not path.is_relative_to('/home/alex/.rustup/toolchains'):
                raise RuntimeError('unexpected selected repository tool path')
            selected[name]=path;result['tools'].append(pin(path))
        for argv in [[str(selected['cargo']),'--version'],[str(selected['rustc']),'-vV'],
                     [str(selected['rustc']),'--print','sysroot'],[str(selected['rustc']),'--print','target-libdir']]:
            row=query(argv);result['queries'].append(row)
            if row['returncode']!=0:raise RuntimeError('fixed tool metadata query failed')
        for path in ['/usr/bin/cc','/usr/bin/ld','/usr/bin/ar','/usr/bin/as','/usr/bin/git','/usr/bin/ninja','/usr/bin/cp','/usr/bin/ldd']:
            result['tools'].append(pin(path))
        row=query(['/usr/bin/cc','-print-prog-name=collect2']);result['queries'].append(row)
        if row['returncode']!=0 or not Path(row['stdout'].strip()).is_absolute():
            raise RuntimeError('unresolved compiler linker helper')
        result['tools'].append(pin(row['stdout'].strip()))
        for before in result['tools']:
            if pin(before['requested_path'])!=before:raise RuntimeError('tool changed after bounded query')
        if pin(REPOSITORY_TOOLCHAIN,False)!=config:raise RuntimeError('repository channel changed')
        result['complete']=True
    except Exception as error:
        result['error']=repr(error)
    result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    raw=(json.dumps(result,indent=2)+'\n').encode()
    fd=os.open(ROOT/'result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    print(json.dumps({'complete':result['complete'],'result':{'path':str(ROOT/'result.json'),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}}),flush=True)
    return 0 if result['complete'] else 1

if __name__=='__main__':
    raise SystemExit(main())
