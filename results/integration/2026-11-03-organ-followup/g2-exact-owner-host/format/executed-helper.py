"""Format private copies with the fixed nightly, preserving the candidate tree."""
from datetime import datetime, timezone
from pathlib import Path
import difflib
import hashlib
import json
import os
import subprocess

BASE = Path('/data/trill-organ-20261103-f1-build')
SOURCE = Path('/home/qian-qi/work/trill-organ-20261103-f1/desktop-owner-host-source')
OUT = BASE / 'kernel-source-format-5d957308'
FMT = BASE / 'rustup-home/toolchains/nightly-2026-07-21-x86_64-unknown-linux-gnu/bin/rustfmt'
FILES = [
    'kernel/asterinas/kernel/core/build.rs',
    'kernel/asterinas/kernel/core/src/process/process/init_proc.rs',
    'kernel/asterinas/kernel/core/src/process/process/init_proc/memory_observation.rs',
    'kernel/asterinas/kernel/core/src/process/process/init_proc/trusted_daemon.rs',
    'kernel/asterinas/kernel/core/src/process/process/init_proc/trusted_launcher.rs',
    'kernel/asterinas/kernel/core/src/process/program_loader/elf/mod.rs',
    'kernel/asterinas/kernel/core/src/process/program_loader/elf/original_owner_profile.rs',
    'kernel/asterinas/kernel/core/src/process/program_loader/elf/trusted_initial.rs',
]
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
       'CARGO_HOME': str(BASE / 'cargo-home'), 'RUSTUP_HOME': str(BASE / 'rustup-home')}
OUT.mkdir(mode=0o700)
record = {'schema': 'hepta.fixed-nightly-source-format.v1', 'passed': False,
          'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'source_head': '5d95730850a13728824fa89511231215f307e4e3',
          'source_tree': 'b799d050b129b11dd4df0d1d0bfe0d8355eb4a3f',
          'original_source_modified': False, 'files': [], 'commands': [],
          'kernel_built': False, 'native_execution_verified': False, 'g2_complete': False}


def run(argv, label):
    result = subprocess.run(argv, cwd=SOURCE, env=ENV, capture_output=True, timeout=120, check=False)
    (OUT / (label + '.stdout')).write_bytes(result.stdout)
    (OUT / (label + '.stderr')).write_bytes(result.stderr)
    record['commands'].append({'argv': [str(x) for x in argv], 'exit_code': result.returncode, 'label': label})
    if result.returncode or b'unknown configuration' in result.stderr.lower():
        raise ValueError(label + ' failed: ' + result.stderr.decode(errors='replace')[-4096:])
    return result.stdout


try:
    identity = run(['/usr/bin/git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], 'source-identity').decode().splitlines()
    if identity != [record['source_head'], record['source_tree']] or run(['/usr/bin/git', 'status', '--porcelain=v1'], 'source-clean'):
        raise ValueError('candidate source identity or clean state differs')
    if FMT.is_symlink() or not FMT.is_file():
        raise ValueError('fixed private nightly rustfmt is absent')
    record['rustfmt_path'] = str(FMT)
    record['rustfmt_sha256'] = hashlib.sha256(FMT.read_bytes()).hexdigest()
    record['rustfmt_version'] = run([str(FMT), '--version'], 'rustfmt-version').decode().strip()
    for relative in FILES:
        raw = (SOURCE / relative).read_bytes()
        original = OUT / 'original' / relative
        candidate = OUT / 'formatted' / relative
        original.parent.mkdir(parents=True, exist_ok=True)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(raw)
        candidate.write_bytes(raw)
    command = [str(FMT), '--edition', '2024', '--config-path', str(SOURCE / 'kernel/asterinas/rustfmt.toml'),
               '--config', 'skip_children=true']
    paths = [str(OUT / 'formatted' / relative) for relative in FILES]
    run(command + paths, 'format-private-copies')
    run(command + ['--check'] + paths, 'check-private-copies')
    differences = []
    for relative in FILES:
        before = (OUT / 'original' / relative).read_bytes()
        after = (OUT / 'formatted' / relative).read_bytes()
        if (SOURCE / relative).read_bytes() != before:
            raise ValueError('formatting changed original source input')
        difference = ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                                  fromfile='a/' + relative, tofile='b/' + relative))
        differences.append(difference)
        record['files'].append({'path': relative, 'input_sha256': hashlib.sha256(before).hexdigest(),
                                'formatted_sha256': hashlib.sha256(after).hexdigest(), 'bytes': len(after),
                                'changed': before != after, 'diff_lines': len(difference.splitlines())})
    (OUT / 'format.diff').write_text(''.join(differences))
    if run(['/usr/bin/git', 'status', '--porcelain=v1'], 'source-after-clean'):
        raise ValueError('candidate source became dirty')
    record['passed'] = True
    record['formatted_copies_pass_check'] = True
    record['source_inputs_already_formatted'] = not any(item['changed'] for item in record['files'])
except Exception as error:
    record['error'] = type(error).__name__ + ': ' + str(error)
finally:
    record['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    (OUT / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({key: record[key] for key in ('passed', 'source_inputs_already_formatted', 'files', 'error') if key in record}))
raise SystemExit(0 if record['passed'] else 1)
