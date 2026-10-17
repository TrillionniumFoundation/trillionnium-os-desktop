#!/usr/bin/env python3
"""Run the necessary strict and focused checks on the new source-bound UI."""
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
base = Path('/workspace/scratch/98f315e377b2')
desktop = base / 'next-native-ci'
allocation = json.loads((base/'next-tools/ui-r5-target.json').read_text())
target = Path(allocation['target'])
evidence = base/'next-tools/ui-r5-checks'
evidence.mkdir(mode=0o700)
spec=importlib.util.spec_from_file_location('ui_r5_checks_guard',desktop/'tests/integration/hepta/run_original_agentd.py')
gate=importlib.util.module_from_spec(spec);sys.modules[spec.name]=gate;spec.loader.exec_module(gate)
record={'started_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_commit':gate.git(desktop,'rev-parse','HEAD'),'source_tree':gate.git(desktop,'rev-parse','HEAD^{tree}'),
        'qualification':'targeted_ui_checks_not_full_host_suite_or_real_ime',
        'old_target_modified':False,'minimum_free_bytes':32*1024**2,'steps':[]}
assert record['source_commit']=='35f379101c0863027e971ccb91faf8da71cf929c'
env=os.environ.copy()
env.update({'RUSTUP_HOME':str(base/'next-tools/rustup'),'CARGO_HOME':str(base/'next-tools/cargo'),
            'PATH':str(base/'next-tools/cargo/bin')+':'+env.get('PATH',''),
            'RUSTUP_TOOLCHAIN':'1.88.0','CARGO_TARGET_DIR':str(target),'CARGO_INCREMENTAL':'0',
            'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_TEST_DEBUG':'0','CARGO_BUILD_JOBS':'1',
            'TMPDIR':allocation['root']})
cargo=str(base/'next-tools/cargo/bin/cargo')
commands=[
 ('clippy',[cargo,'clippy','--manifest-path','ui/Cargo.toml','--workspace','--all-targets','--locked','--offline','--','-D','warnings']),
 ('shell_focused',[cargo,'test','--manifest-path','ui/Cargo.toml','-p','trill-shell','--bin','trill-shell','--locked','--offline','focused_','--','--nocapture']),
 ('app_focused',[cargo,'test','--manifest-path','ui/Cargo.toml','-p','trill-app-window','--bin','trill-app-window','--locked','--offline','focused_run_button','--','--nocapture']),
 ('fmt',[cargo,'fmt','--manifest-path','ui/Cargo.toml','--all','--check']),
]
code=0
for name,command in commands:
    step={'name':name,'command':command,'started_at_utc':datetime.now(timezone.utc).isoformat(),'samples':[]}
    started=time.monotonic()
    with (evidence/(name+'.log')).open('xb') as out:
        process=subprocess.Popen(command,cwd=desktop,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        group=gate.ChildGroup(process)
        try:
            while True:
                state=group.observe_exit()
                sample={'elapsed_seconds':round(time.monotonic()-started,3),'free_bytes':shutil.disk_usage(target).free}
                step['samples'].append(sample)
                if state is not None:
                    code=group.reap() if state.si_code==os.CLD_EXITED and state.si_status==0 else gate.terminate_group(group)
                    break
                if sample['free_bytes']<record['minimum_free_bytes'] or sample['elapsed_seconds']>180:
                    step['stop_reason']='temporary_resource_or_deadline_bound'
                    code=gate.terminate_group(group)
                    break
                time.sleep(0.2)
        finally:
            if group.armed:gate.terminate_group(group)
    step['exit_code']=code
    step['ended_at_utc']=datetime.now(timezone.utc).isoformat()
    record['steps'].append(step)
    print(json.dumps({k:v for k,v in step.items() if k!='samples'}),flush=True)
    if code or 'stop_reason' in step:break
record['status']='passed' if len(record['steps'])==len(commands) and all(s['exit_code']==0 and 'stop_reason' not in s for s in record['steps']) else 'failed'
record['ended_at_utc']=datetime.now(timezone.utc).isoformat()
record['free_bytes_after']=shutil.disk_usage(target).free
with (evidence/'receipt.json').open('x') as out:json.dump(record,out,indent=2);out.write('\n')
print(json.dumps({'status':record['status'],'free_bytes_after':record['free_bytes_after']}),flush=True)
sys.exit(0 if record['status']=='passed' else 1)
