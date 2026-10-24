from pathlib import Path
import hashlib, json, os, subprocess, time

BASE=Path(__file__).resolve().parents[1]
DATA=Path('/data/asterinas-audit-build.8tdrjboi')
SOURCE=DATA/'socket-credential-snapshot'
OUT=DATA/'socket-credential-native-22e0-01'
HEAD='22e0a19f8ab95f730e0fedd85462157ed3d9a10e'
OUT.mkdir(mode=0o700,exist_ok=False)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==HEAD
TREE=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=SOURCE,text=True).strip()
env=os.environ.copy()
env.update(CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='2',RUSTUP_TOOLCHAIN='nightly-2026-07-21',
 CARGO_TARGET_DIR=str(DATA/'inline-signal-joint-target'),TMPDIR=str(DATA/'cgroup-memory-tmp'),
 OSDK_LOCAL_DEV='1',VDSO_LIBRARY_DIR=str(BASE/'work/build-cache/linux-vdso'),PYTHONDONTWRITEBYTECODE='1')
report={'schema':'trillionnium.native-kernel-integration.v1','source_head':HEAD,'source_tree':TREE,
 'commands':[],'passed':False,'complete':False,'production_authority':False,'g2_complete':False}
start=time.monotonic()
def save():
 (OUT/'pipeline.json').write_text(json.dumps(report,indent=2)+'\n')
def run(name,command,deadline):
 record={'stage':name,'argv':command,'outer_deadline_seconds':deadline};report['commands'].append(record);save()
 with (OUT/(name+'.log')).open('xb') as log:
  result=subprocess.run(command,cwd=SOURCE,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=deadline)
 record['exit_code']=result.returncode;save();assert result.returncode==0,name
try:
 run('original-four-suites',['python3','-I','-B',str(BASE/'work/run-original-full-ipc.py'),'--source',str(SOURCE),'--head',HEAD,'--out',str(OUT/'full')],15000)
 run('original-ordinary',['python3','-I','-B','tests/kernel/control/run_queryabi_candidate_guest.py','--expected-source-head',HEAD,'--expected-source-tree',TREE,'--target-dir',str(DATA/'inline-signal-joint-target'),'--cc','/usr/bin/gcc-13','--qemu','/usr/bin/qemu-system-x86_64','--output',str(OUT/'ordinary')],7200)
 run('native-sgid30',['python3','-I','-B',str(BASE/'work/run-native-sgid-probe.py'),'--ordinary',str(OUT/'ordinary'),'--source',str(SOURCE),'--out',str(OUT/'sgid30')],300)
 run('native-ownership12',['python3','-I','-B',str(BASE/'work/run-socket-snapshot-ownership-22e0.py')],300)
 receipt=OUT/'ordinary/result.json'
 run('native-proc-privileges12',['python3','-I','-B','tests/kernel/control/run_proc_process_privileges.py','--kernel',str(OUT/'ordinary/product-kernel.elf'),'--ordinary-receipt',str(receipt),'--expected-receipt-sha256',hashlib.sha256(receipt.read_bytes()).hexdigest(),'--initramfs',str(SOURCE/'support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz'),'--output',str(OUT/'proc-privileges12')],300)
 run('native-memfd4',['python3','-I','-B',str(BASE/'work/run-socket-snapshot-memfd-22e0.py')],300)
 run('native-inline-signal22',['python3','-I','-B',str(BASE/'work/run-socket-snapshot-probe-22e0.py')],300)
 for suite in ['lifecycle','stat','traceme']:
  run('native-dumpability-'+suite,['python3','-I','-B',str(BASE/'work/run-socket-snapshot-native-22e0.py'),suite],300)
 run('native-supplementary-dac6',['python3','-I','-B',str(BASE/'work/run-socket-snapshot-six-22e0.py')],300)
 run('native-commoncap16',['python3','-I','-B',str(BASE/'work/run-socket-snapshot-sixteen-22e0.py')],300)
 for suite in ['lifetime','groups']:
  run('native-socket-'+suite,['python3','-I','-B',str(BASE/'work/run-socket-snapshot-credentials-22e0.py'),suite],300)
 report['passed']=True
finally:
 report['elapsed_seconds']=round(time.monotonic()-start,3);report['complete']=True
 report['source_checkout_clean']=not bool(subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=SOURCE))
 save()
