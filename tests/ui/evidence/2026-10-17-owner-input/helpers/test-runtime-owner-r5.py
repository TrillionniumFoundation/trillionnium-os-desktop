#!/usr/bin/env python3
"""Exercise old/new actual scripts as the existing non-root sudo-capable user."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
base = Path('/workspace/scratch/98f315e377b2')
desktop = base / 'next-native-ci'
evidence = base / 'next-tools/ui-r5-runtime-owner'
evidence.mkdir(mode=0o700)
stage = Path(tempfile.mkdtemp(prefix='trill-runtime-owner-r5-', dir='/tmp'))
uid = 1000
for directory in [stage, stage / 'bin', stage / 'fixtures']:
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chown(directory, uid, uid)
build = json.loads((base / 'next-tools/ui-r5-build-02/receipt.json').read_text())
assert build['status'] == 'passed' and build['source_commit'] == '35f379101c0863027e971ccb91faf8da71cf929c'
source_binary = Path(build['binaries']['trill-session']['path'])
binary = stage / 'bin/trill-session'
shutil.copy2(source_binary, binary)
assert hashlib.sha256(binary.read_bytes()).hexdigest() == build['binaries']['trill-session']['sha256']
spec = importlib.util.spec_from_file_location('runtime_owner_r5_guard', desktop / 'tests/integration/hepta/run_original_agentd.py')
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)
record = {'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'qualification': 'actual_nonroot_caller_and_root_session_runtime_owner_regression',
          'caller_user': 'vscode', 'caller_uid': uid, 'system_policy_modified': False,
          'source_commit': build['source_commit'], 'source_tree': build['source_tree'],
          'session_sha256': build['binaries']['trill-session']['sha256'], 'stage': str(stage), 'attempts': []}
for label, revision in [('before','45552fbd8f79ea713509908ac4b08a3fd44a95bc'), ('after',build['source_commit'])]:
    script_bytes = subprocess.check_output(['git','show',revision+':tests/ui/test-runtime-owner.sh'],cwd=desktop)
    script = stage / (label + '.sh')
    script.write_bytes(script_bytes)
    script.chmod(0o644)
    out_dir = evidence / label
    out_dir.mkdir(mode=0o700)
    (out_dir / 'executed-script.sh').write_bytes(script_bytes)
    command = ['sudo','-n','-u','vscode','env','-i','PATH=/usr/bin:/bin','TMPDIR='+str(stage/'fixtures'),
               '/usr/bin/bash','-c','id -u; exec bash "$1" "$2"','bash',str(script),str(stage/'bin')]
    attempt = {'label': label, 'script_revision': revision,
               'script_sha256': hashlib.sha256(script_bytes).hexdigest(), 'command':command,
               'started_at_utc': datetime.now(timezone.utc).isoformat(), 'copied_logs': []}
    started = time.monotonic()
    with (out_dir / 'console.log').open('xb') as output:
        process = subprocess.Popen(command,cwd=stage,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        group = gate.ChildGroup(process)
        try:
            while True:
                for live in (stage/'fixtures').glob('a10-runtime-owner.*/*.log'):
                    try:
                        content = live.read_bytes()
                    except FileNotFoundError:
                        continue
                    if len(content) > 65536:
                        raise RuntimeError('unexpected oversized private fixture log')
                    (out_dir/live.name).write_bytes(content)
                state = group.observe_exit()
                if state is not None:
                    attempt['exit_code'] = group.reap() if state.si_code == os.CLD_EXITED and state.si_status == 0 else gate.terminate_group(group)
                    break
                if time.monotonic()-started>20:
                    raise RuntimeError('nonroot regression deadline')
                time.sleep(0.01)
        finally:
            if group.armed:
                gate.terminate_group(group)
    console = (out_dir/'console.log').read_text(errors='replace')
    attempt['caller_uid_line_observed'] = '1000' in console.splitlines()
    attempt['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
    attempt['copied_logs'] = [{'path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
                              for p in sorted(out_dir.glob('*.log'))]
    if label=='before':
        attempt['expected_result_observed'] = attempt['exit_code'] != 0 and 'Permission denied' in console and 'foreign_subdir/trillionnium-ui' in console
    else:
        attempt['expected_result_observed'] = attempt['exit_code'] == 0 and 'A10 REAL RUNTIME OWNERSHIP PASS:' in console
    record['attempts'].append(attempt)
    with (out_dir/'receipt.json').open('x') as out:
        json.dump(attempt,out,indent=2);out.write('\n')
record['status'] = 'passed' if all(x['expected_result_observed'] and x['caller_uid_line_observed'] for x in record['attempts']) else 'failed'
record['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
record['fixture_directories_remaining'] = [str(p) for p in (stage/'fixtures').iterdir()]
with (evidence/'receipt.json').open('x') as out:
    json.dump(record,out,indent=2);out.write('\n')
print(json.dumps(record),flush=True)
sys.exit(0 if record['status']=='passed' and not record['fixture_directories_remaining'] else 1)
