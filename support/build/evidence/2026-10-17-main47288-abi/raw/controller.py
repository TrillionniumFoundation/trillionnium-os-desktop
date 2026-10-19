import datetime, hashlib, json, os, pathlib, subprocess, sys

ROOT = pathlib.Path('/workspace/scratch/ae1a8cf05419/main47288-abi-validation')
REPO = pathlib.Path('/tmp/trillionnium-a01-main47288-abi')
SHA = '47288c4465720d125658b392efc655b333c90868'
ENV = os.environ.copy()
ENV.update(CARGO_HOME='/workspace/scratch/ae1a8cf05419/toolchains/cargo',
           RUSTUP_HOME='/workspace/scratch/ae1a8cf05419/toolchains/rustup',
           RUSTUP_TOOLCHAIN='nightly-2026-07-21',
           PATH='/workspace/scratch/ae1a8cf05419/toolchains/cargo/bin:' + ENV.get('PATH', ''),
           CARGO_NET_OFFLINE='true', PYTHONDONTWRITEBYTECODE='1')
records = []

def run(label, command):
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print('BEGIN ' + label, flush=True)
    with (ROOT / (label + '.stdout.log')).open('xb') as stdout, (ROOT / (label + '.stderr.log')).open('xb') as stderr:
        result = subprocess.run(command, cwd=REPO, env=ENV, stdout=stdout, stderr=stderr)
    row = dict(label=label, command=command, cwd=str(REPO), start_utc=start,
               finish_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), exit_code=result.returncode)
    records.append(row)
    with (ROOT / (label + '.command.json')).open('x') as stream:
        json.dump(row, stream, indent=2); stream.write('\n')
    print('END ' + label + ' ' + str(result.returncode), flush=True)
    return result.returncode

with (ROOT / 'environment.json').open('x') as stream:
    json.dump({name:ENV.get(name) for name in ['CARGO_HOME','RUSTUP_HOME','RUSTUP_TOOLCHAIN','PATH','CARGO_NET_OFFLINE']},stream,indent=2)
commands = [
    ('source-head', ['git','rev-parse','HEAD']),
    ('source-status-before', ['git','status','--porcelain']),
    ('source-trees', ['git','rev-parse','HEAD^{tree}','HEAD:kernel/asterinas','HEAD:libs/os-abi','HEAD:tests/abi','HEAD:tests/golden']),
    ('changed-input-blobs', ['git','ls-tree',SHA,'libs/os-abi/src/lib.rs','libs/os-abi/tests/response_snapshot.rs','tests/abi/A02_RESPONSE_SNAPSHOT_ACCEPTANCE_2026-10-17.md','tests/abi/run_acceptance.py']),
    ('rustc-identity', ['rustup','run','nightly-2026-07-21','rustc','-Vv']),
    ('cargo-identity', ['rustup','run','nightly-2026-07-21','cargo','-Vv']),
    ('acceptance', [sys.executable,'-I','tests/abi/run_acceptance.py','--repo-root',str(REPO),'--output-dir',str(ROOT/'acceptance'),'--timeout','60','--mutation-timeout','900']),
    ('source-status-after', ['git','status','--porcelain']),
    ('source-head-after', ['git','rev-parse','HEAD']),
]
exit_code = 0
for label, command in commands:
    result = run(label, command)
    if label == 'source-head' and (ROOT/'source-head.stdout.log').read_text().strip() != SHA:
        raise SystemExit('source HEAD differs')
    if label.startswith('source-status') and (ROOT/(label+'.stdout.log')).read_bytes():
        raise SystemExit('source worktree is dirty')
    if result:
        exit_code = result
        if label != 'acceptance':
            break
with (ROOT/'controller-result.json').open('x') as stream:
    json.dump(dict(source_commit=SHA, records=records, exit_code=exit_code, new_kernel_or_guest_test=False), stream, indent=2);stream.write('\n')
sys.exit(exit_code)
