from pathlib import Path
from datetime import datetime, timezone
import subprocess,json,hashlib,os,sys
repo=Path('/workspace/scratch/ae1a8cf05419/trillionnium-os-desktop');out=repo.parent/'next9-root-host-recheck'
assert not out.exists();out.mkdir()
h=lambda b:hashlib.sha256(b).hexdigest()
source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip();assert source=='ff040c6d5afbc4e26a249022093b8090181f6176'
files=['support/build/kernel.sh','support/build/tests/test_kernel_runner.py','support/build/kernel-supervisor.py','support/build/tests/test_kernel_supervisor.py','support/build/ktest/run.py','support/build/ktest/test_runner_lifecycle.py']
inputs={p:h((repo/p).read_bytes()) for p in files}
env=dict(os.environ);removed=[]
for key in list(env):
 if key.startswith(('A01_','CARGO_','RUSTUP_','MOCK_','FIXTURE_')) or key in ('MAKEFLAGS','MFLAGS','GNUMAKEFLAGS','MAKEFILES','MAKEOVERRIDES','MAKELEVEL'):
  removed.append(key);env.pop(key,None)
receipts=[]
for mode in (['-I'],['-I','-O']):
 for suite,count in [('support/build/tests/test_kernel_runner.py',30),('support/build/tests/test_kernel_supervisor.py',9),('support/build/ktest/test_runner_lifecycle.py',17)]:
  name=Path(suite).stem+('-IO' if '-O' in mode else '-I');argv=[sys.executable,*mode,suite]
  start=datetime.now(timezone.utc).isoformat();r=subprocess.run(argv,cwd=repo,env=env,capture_output=True,timeout=120)
  raw=r.stdout+r.stderr;log=out/(name+'.log');log.write_bytes(raw)
  receipt={'argv':argv,'cwd':str(repo),'started_utc':start,'completed_utc':datetime.now(timezone.utc).isoformat(),'actual_exit':r.returncode,'stdout_stderr_combined':True,'log':log.name,'log_sha256':h(raw),'log_bytes':len(raw),'expected_tests':count,'source_commit':source,'removed_environment_keys':sorted(removed)}
  receipts.append(receipt);(out/(name+'.invocation.json')).write_text(json.dumps(receipt,indent=2)+'\n')
  assert r.returncode==0 and f'Ran {count} tests'.encode() in raw and b'\nOK\n' in raw,(name,r.returncode)
  print(json.dumps({'suite':name,'actual_exit':r.returncode,'tests':count}),flush=True)
assert {p:h((repo/p).read_bytes()) for p in files}==inputs
summary={'kind':'additional_integrated_host_recheck_to_retain_explicit_invocation_receipts','source_commit':source,'source_tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=repo,text=True).strip(),'all_passed':True,'host_executions':112,'distinct_tests':56,'modes':['-I','-I -O'],'source_inputs_sha256':inputs,'inputs_unchanged_after':True,'receipts':receipts,'kernel_or_vm_run':False,'prior_agent_runs_are_separate':True}
(out/'report.json').write_text(json.dumps(summary,indent=2)+'\n');(out/'controller.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'host_executions':112,'all_passed':True}),flush=True)
