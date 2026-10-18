#!/usr/bin/python3
"""Run actual source-bound debug or kernel-test followups on the N2 target."""
import datetime, hashlib, json, os, signal, subprocess, sys
from pathlib import Path
base=Path('/workspace/scratch/ae1a8cf05419')
worktree=Path('/tmp/trillionnium-a01-private-sdk-N2')
source,action=sys.argv[1:]
if action not in ('debug','ktest'):raise SystemExit('action must be debug or ktest')
outer=base/'native-followup'/action
outer.mkdir(parents=True,mode=0o700)
controller=outer/'controller';controller.mkdir(mode=0o700)
prefix=base/'native-tools/root'
env=os.environ.copy()
env.update(CARGO_HOME=str(base/'toolchains/cargo'),RUSTUP_HOME=str(base/'toolchains/rustup'),
    RUSTUP_TOOLCHAIN='nightly-2026-07-21',CARGO_BUILD_JOBS='1',CARGO_NET_GIT_FETCH_WITH_CLI='true',
    PATH=':'.join(map(str,[base/'toolchains/cargo/bin',prefix/'usr/bin',prefix/'usr/lib/llvm-18/bin']))+':'+env.get('PATH','/usr/bin:/bin'),
    LD_LIBRARY_PATH=':'.join(map(str,[prefix/'usr/lib/x86_64-linux-gnu',prefix/'lib/x86_64-linux-gnu',prefix/'usr/lib/llvm-18/lib'])),
    QEMU_MODULE_DIR=str(prefix/'usr/lib/x86_64-linux-gnu/qemu'),A01_BUSYBOX=str(prefix/'usr/bin/busybox'),
    A01_QEMU_BIOS=str(prefix/'usr/share/seabios/bios-256k.bin'),A01_QEMU_DATA_DIR=str(prefix/'usr/share/qemu'),
    VDSO_LIBRARY_DIR=str(base/'trillionnium-os-desktop/support/build/out/linux-vdso'),
    PKG_CONFIG_LIBDIR=':'.join(map(str,[prefix/'usr/lib/x86_64-linux-gnu/pkgconfig',prefix/'usr/share/pkgconfig'])),
    PKG_CONFIG_SYSROOT_DIR=str(prefix),A01_QEMU_TIMEOUT='300')
for key in ('CARGO_INCREMENTAL','ASTER_BUILD_TIMESTAMP','SOURCE_DATE_EPOCH','OSDK_BUILD_USERNAME','OSDK_BUILD_HOSTNAME',
    'CARGO_ENCODED_RUSTFLAGS','CARGO_TARGET_DIR','RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER',
    'A01_KERNEL_WORKER','A01_REPRO_POLICY','A01_RUN_DIR','MAKEFLAGS','MFLAGS','GNUMAKEFLAGS','MAKEFILES','MAKEOVERRIDES','MAKELEVEL'):
    env.pop(key,None)
records=[]
def run(name,argv,timeout=1800):
    path=controller/(name+'.log')
    row={'name':name,'argv':argv,'cwd':str(worktree),'start':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'environment':{k:v for k,v in env.items() if k.startswith(('CARGO_','RUSTUP_','A01_','QEMU_','VDSO_','PKG_CONFIG_')) or k in ('PATH','LD_LIBRARY_PATH')}}
    records.append(row);(controller/'commands.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps({'stage':'start','action':action,'name':name}),flush=True)
    with path.open('xb') as stream:
        p=subprocess.Popen(argv,cwd=worktree,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            row['timed_out']=True;os.killpg(p.pid,signal.SIGTERM)
            try:code=p.wait(timeout=30)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);code=p.wait()
    row.update(returncode=code,end=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        log_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),log_bytes=path.stat().st_size)
    (controller/'commands.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps({'stage':'finish','action':action,'name':name,'returncode':code}),flush=True)
    if code:raise SystemExit(code if code>0 else 1)
check="import subprocess,sys;from pathlib import Path;head=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip();status=subprocess.check_output(['git','status','--porcelain=v1']);print(head);print(status.decode());sys.exit(0 if head==sys.argv[1] and not status else 1)"
run('source-head-clean',['python3','-I','-c',check,source])
run('source-inputs',['python3','-I','support/build/verify-source.py'])
run('fixed-rustc',['rustc','+nightly-2026-07-21','-Vv'])
if action=='debug':
    argv=['python3','-I','support/build/debug/run.py','--output',str(outer/'run'),
          '--gdb',str(prefix/'usr/bin/gdb'),'--nm',str(prefix/'usr/bin/nm')]
else:
    argv=['python3','-I','support/build/ktest/run.py','--output',str(outer/'run')]
run('actual-'+action,argv)
run('post-source-inputs',['python3','-I','support/build/verify-source.py'])
run('post-source-head-clean',['python3','-I','-c',check,source])
print('actual '+action+' source-bound followup completed',flush=True)
