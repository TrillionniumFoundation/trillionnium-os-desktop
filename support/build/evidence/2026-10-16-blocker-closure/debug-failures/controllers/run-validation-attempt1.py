import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path('/workspace/scratch/ae1a8cf05419')
repo = root / 'trillionnium-os-desktop'
mode = sys.argv[1]
if mode == 'integration':
    cwd = repo
    output = cwd / 'support/build/out/closure-tcp-full-01'
    argv = [sys.executable, '-I', 'support/build/osdk-integration/run.py',
            '--local-tcp', '--coverage-gdb', '--output', str(output),
            '--target-dir', str(cwd / 'support/build/out/osdk-capture-v2-02/target')]
elif mode == 'debug':
    cwd = root / 'a01-next9-native'
    output = cwd / 'support/build/out/closure-debug-01'
    argv = [sys.executable, '-I', 'support/build/debug/run.py', '--output', str(output)]
else:
    raise SystemExit('unknown validation mode')
env = dict(os.environ)
env.pop('CARGO_ENCODED_RUSTFLAGS', None)
env.update(CARGO_HOME=str(root / 'toolchains/cargo'),
           RUSTUP_HOME=str(root / 'toolchains/rustup'),
           RUSTUP_TOOLCHAIN='nightly-2026-07-21',
           CARGO_NET_OFFLINE='true', CARGO_BUILD_JOBS='2',
           VDSO_LIBRARY_DIR=str(root / 'linux-vdso'))
env['PATH'] = env['CARGO_HOME'] + '/bin:' + env['PATH']
destination = root / 'blocker-closure' / (mode + '-controller')
destination.mkdir(exist_ok=False)
record = {'argv': argv, 'cwd': str(cwd), 'output': str(output),
          'start': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'git_head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=cwd,text=True).strip(),
          'git_tree': subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=cwd,text=True).strip(),
          'environment': {k:env.get(k) for k in ['CARGO_HOME','RUSTUP_HOME','RUSTUP_TOOLCHAIN',
              'CARGO_NET_OFFLINE','CARGO_BUILD_JOBS','VDSO_LIBRARY_DIR','CARGO_ENCODED_RUSTFLAGS','PATH']},
          'returncode': None}
receipt = destination / 'result.json'
receipt.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'stage':'starting', 'mode':mode, 'output':str(output)}),flush=True)
with (destination / 'console.log').open('wb') as log:
    result = subprocess.run(argv,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
record.update(returncode=result.returncode,end=datetime.datetime.now(datetime.timezone.utc).isoformat())
receipt.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'stage':'finished','mode':mode,'returncode':result.returncode}),flush=True)
raise SystemExit(result.returncode)
