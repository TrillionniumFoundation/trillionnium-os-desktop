import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

root=Path('/workspace/scratch/ae1a8cf05419')
out=root/'round2-restore'
env=dict(os.environ)
env.update(CARGO_HOME=str(root/'toolchains/cargo'),RUSTUP_HOME=str(root/'toolchains/rustup'),
           CARGO_BUILD_JOBS='2',CARGO_NET_GIT_FETCH_WITH_CLI='true')
env['PATH']=env['CARGO_HOME']+'/bin:'+env['PATH']
installer=out/'rustup-init'
expected='dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71'
if hashlib.sha256(installer.read_bytes()).hexdigest()!=expected:
    raise RuntimeError('downloaded installer differs from retained official input')
installer.chmod(0o755)
rows=[]
def run(name,argv,cwd=root):
    row={'name':name,'argv':list(map(str,argv)),'cwd':str(cwd),
         'start':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'selected_environment':{k:env.get(k) for k in ('CARGO_HOME','RUSTUP_HOME','CARGO_BUILD_JOBS','CARGO_NET_GIT_FETCH_WITH_CLI')},
         'returncode':None}
    rows.append(row);out.joinpath('rust-commands.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({'stage':'start','name':name}),flush=True)
    with out.joinpath(name+'.log').open('wb') as log:
        result=subprocess.run(argv,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
    row.update(returncode=result.returncode,end=datetime.datetime.now(datetime.timezone.utc).isoformat())
    out.joinpath('rust-commands.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({'stage':'finish','name':name,'returncode':result.returncode}),flush=True)
    if result.returncode:raise SystemExit(result.returncode)
run('rustup-install',[installer,'-y','--no-modify-path','--default-toolchain','none'])
run('fixed-toolchain-install',['rustup','toolchain','install','nightly-2026-07-21','--profile','minimal',
    '--component','rust-src,rustc-dev,llvm-tools-preview,rustfmt,clippy','--target','x86_64-unknown-none'])
run('rustc-version',['rustc','+nightly-2026-07-21','-Vv'])
if '87e5904f5eb6398af6b22eac2802c78934260c48' not in (out/'rustc-version.log').read_text():
    raise RuntimeError('compiler commit mismatch')
run('cargo-version',['cargo','+nightly-2026-07-21','-Vv'])
run('clippy-version',['cargo','+nightly-2026-07-21','clippy','--version'])
run('cargo-binutils-install',['cargo','+nightly-2026-07-21','install','--locked','--version','0.4.0','cargo-binutils'])
repo=root/'trillionnium-os-desktop'
vdso=repo/'support/build/out/linux-vdso'
vdso.parent.mkdir(parents=True,exist_ok=True)
run('vdso-clone',['git','clone','https://github.com/asterinas/linux_vdso.git',vdso])
run('vdso-checkout',['git','-C',vdso,'checkout','--detach','8af571775a3d3a1df3e84fc9709b9d6b160c771a'])
if hashlib.sha256((vdso/'vdso_x86_64.so').read_bytes()).hexdigest()!='27cd7bf576a92fa48a891c05988f52fac35b7374d5b9650d6b035e477c5d93a3':
    raise RuntimeError('fixed vDSO digest mismatch')
print('fixed Rust and vDSO restored',flush=True)
