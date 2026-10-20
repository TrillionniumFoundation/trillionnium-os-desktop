from pathlib import Path
import hashlib,json,os,subprocess
repo=Path('/workspace/scratch/ae1a8cf05419/trillionnium-os-desktop');root=Path(__file__).resolve().parent;script=repo/'support/build/kernel.sh';expected='4ee3118990158bb93be6ffe191cac8de5399f507973af6adc3a05e3614407f83'
if hashlib.sha256(script.read_bytes()).hexdigest()!=expected:raise SystemExit('source differs')
rows=[]
for source in ('explicit-cargo-home','default-home'):
 for target in ('kernel','run_kernel','gdb_server','terminal-dotdot'):
  name=source+'-'+target;destination=root/(name+'-retry-uncreated-parent/evidence');env=dict(os.environ,A01_RUN_DIR=str(destination));value=str(root)+'/..' if target=='terminal-dotdot' else str(root)+'/placeholder/../home'
  if source=='explicit-cargo-home':env['CARGO_HOME']=value
  else:env.pop('CARGO_HOME',None);env['HOME']=value
  command=['/bin/bash',str(script),'kernel' if target=='terminal-dotdot' else target];p=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True)
  rows.append({'name':name,'command':command,'CARGO_HOME':env.get('CARGO_HOME'),'HOME':env.get('HOME'),'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'output_parent_absent':not destination.parent.exists(),'passed':p.returncode==2 and "must not contain '..' components" in p.stderr and not destination.parent.exists()})
report={'source_sha256':expected,'cases':rows,'all_passed':all(r['passed'] for r in rows),'supersedes':'actual-guard-results.json checker incorrectly expected substring must-not-contain-a; all actual executions already rejected2 correctly','scope':'actual wrapper invalid-environment ingress only; no SDK/compiler/kernel/QEMU'};(root/'actual-guard-results-v2.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'source':expected,'checks':len(rows),'all_passed':report['all_passed']}));raise SystemExit(0 if report['all_passed'] else 1)
