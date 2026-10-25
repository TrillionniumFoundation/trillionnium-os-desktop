from pathlib import Path
import hashlib, json, os, subprocess, time

BASE=Path(__file__).resolve().parents[1]
DATA=Path('/data/asterinas-audit-build.8tdrjboi')
SOURCE=DATA/'inode-sgid-semantics'
OUT=DATA/'inode-sgid-native-15ec-02'
HEAD='15ec98c23edb6ebb1682c959324efb05a201cb9f'
OUT.mkdir(mode=0o700,exist_ok=False)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==HEAD
TREE=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=SOURCE,text=True).strip()
env=os.environ.copy()
env.update(CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='2',RUSTUP_TOOLCHAIN='nightly-2026-07-21',
 CARGO_TARGET_DIR=str(DATA/'inode-sgid-target'),TMPDIR=str(DATA/'proc-boot-tmp'),
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
 run('original-ordinary',['python3','-I','-B','tests/kernel/control/run_queryabi_candidate_guest.py','--expected-source-head',HEAD,'--expected-source-tree',TREE,'--target-dir',str(DATA/'inode-sgid-target'),'--cc','/usr/bin/gcc-13','--qemu','/usr/bin/qemu-system-x86_64','--output',str(OUT/'ordinary')],7200)
 report['passed']=True
finally:
 report['elapsed_seconds']=round(time.monotonic()-start,3);report['complete']=True
 report['source_checkout_clean']=not bool(subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=SOURCE))
 save()
