"""Compile and run the source-owned host build script on the actual owner bytes."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import stat
import subprocess

BASE = Path('/data/trill-organ-20261103-f1-build')
FORMAT = BASE / 'kernel-source-format-5d957308'
OUT = BASE / 'host-build-script-5dformatted-v1'
OWNER = BASE / 'g2-owner-build-v3/packaged/hepta-g2-native-owner'
OWNER_SHA = '6ce96a0785b2cbb51bb71fabb2973c1e04d93e213d56694b42b4d717ed55a454'
FILE_BYTES = 20138584
RELATIVE = 'kernel/asterinas/kernel/core/build.rs'
PROFILE_RELATIVE = 'kernel/asterinas/kernel/core/src/process/program_loader/elf/original_owner_profile.rs'
CHANNEL = 'nightly-2026-07-21'
RUSTUP = '/home/qian-qi/.cargo/bin/rustup'
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/home/qian-qi', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
       'CARGO_HOME': str(BASE / 'cargo-home'), 'RUSTUP_HOME': str(BASE / 'rustup-home'),
       'TMPDIR': str(OUT / 'tmp')}
OUT.mkdir(mode=0o700)
(OUT / 'tmp').mkdir(mode=0o700)
record = {'schema': 'hepta.exact-owner-host-build-script-check.v1', 'passed': False,
          'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'source_head_before_format_overlay': '5d95730850a13728824fa89511231215f307e4e3',
          'source_components': [], 'commands': [], 'actual_original_owner_executed': False,
          'kernel_built': False, 'native_execution_verified': False, 'g2_complete': False,
          'global_memory_reserve': False, 'legacy_static_profile_passed': False}


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def run(argv, label, environment=ENV, expected=0):
    result = subprocess.run(argv, cwd=OUT, env=environment, capture_output=True, timeout=120, check=False)
    (OUT / (label + '.stdout')).write_bytes(result.stdout)
    (OUT / (label + '.stderr')).write_bytes(result.stderr)
    record['commands'].append({'argv': [str(x) for x in argv], 'label': label,
                               'exit_code': result.returncode, 'expected_exit_code': expected})
    if result.returncode != expected:
        raise ValueError(label + ' returned an unexpected status: ' + result.stderr.decode(errors='replace')[-4096:])
    return result.stdout.decode()


try:
    compiler_path = BASE / 'kernel-toolchain-validation-v1/result.json'
    if sha(compiler_path) != '374708fd1cd2402072f03431379022d6138a762670d339145b77e4f3a1340188':
        raise ValueError('actual fixed compiler observation differs')
    compiler = json.loads(compiler_path.read_bytes())
    if not compiler['passed'] or sha(Path(compiler['actual_tools']['rustc']['path'])) != compiler['actual_tools']['rustc']['sha256']:
        raise ValueError('actual fixed compiler identity changed')
    record['actual_rustc'] = compiler['actual_tools']['rustc']
    record['rustc_verbose'] = compiler['rustc_verbose']
    formatting = json.loads((FORMAT / 'result.json').read_bytes())
    if not formatting['passed'] or not formatting['formatted_copies_pass_check']:
        raise ValueError('fixed-nightly candidate formatting is not complete')
    inputs = {item['path']: item for item in formatting['files']}
    for relative in (RELATIVE, PROFILE_RELATIVE):
        path = FORMAT / 'formatted' / relative
        if sha(path) != inputs[relative]['formatted_sha256']:
            raise ValueError('formatted source component bytes changed')
        path.chmod(0o444)
        record['source_components'].append({'path': relative, 'sha256': sha(path)})
    if OWNER.is_symlink() or not OWNER.is_file() or OWNER.stat().st_size != FILE_BYTES or sha(OWNER) != OWNER_SHA:
        raise ValueError('actual original-owner packaged artifact differs')
    record['owner_sha256'] = OWNER_SHA
    record['owner_bytes'] = FILE_BYTES
    source = FORMAT / 'formatted' / RELATIVE
    executable = OUT / 'source-owned-build-script'
    run([RUSTUP, 'run', CHANNEL, 'rustc', '--edition=2024', str(source), '-o', str(executable)], 'compile')
    record['compiled_build_script_sha256'] = sha(executable)
    ordinary = run([str(executable)], 'ordinary-no-input')
    if ordinary != 'cargo:rerun-if-env-changed=HEPTA_TRUSTED_INITIAL_ELF\n':
        raise ValueError('ordinary build now requires or consumes an extra input')
    frozen_dir = OUT / 'frozen'
    frozen_dir.mkdir(mode=0o700)
    exact_env = {**ENV, 'CARGO_FEATURE_G2_ORIGINAL_OWNER_A39_V1': '1',
                 'HEPTA_TRUSTED_INITIAL_ELF': str(OWNER), 'OUT_DIR': str(frozen_dir)}
    output = run([str(executable)], 'exact-first', exact_env)
    frozen = frozen_dir / 'reviewed-original-owner.elf'
    if sha(frozen) != OWNER_SHA or frozen.stat().st_size != FILE_BYTES or stat.S_IMODE(frozen.stat().st_mode) != 0o444:
        raise ValueError('compiler input was not sealed as the exact original snapshot')
    if ('cargo:rustc-env=HEPTA_REVIEWED_ORIGINAL_OWNER_ELF=' + str(frozen) + '\n') not in output:
        raise ValueError('compiler include input does not point to the reviewed private copy')
    identity = (frozen.stat().st_dev, frozen.stat().st_ino)
    run([str(executable)], 'exact-existing-sealed', exact_env)
    if (frozen.stat().st_dev, frozen.stat().st_ino) != identity or sha(frozen) != OWNER_SHA:
        raise ValueError('the known sealed input was replaced')
    refused_dir = OUT / 'own-existing-writable'
    refused_dir.mkdir(mode=0o700)
    refused = refused_dir / 'reviewed-original-owner.elf'
    refused.write_bytes(OWNER.read_bytes())
    refused.chmod(0o644)
    before = (refused.stat().st_dev, refused.stat().st_ino)
    run([str(executable)], 'existing-writable-refused', {**exact_env, 'OUT_DIR': str(refused_dir)}, expected=101)
    if ((refused.stat().st_dev, refused.stat().st_ino) != before or sha(refused) != OWNER_SHA
            or stat.S_IMODE(refused.stat().st_mode) != 0o644):
        raise ValueError('a refused pre-existing private file was changed')
    if sha(OWNER) != OWNER_SHA or any(sha(FORMAT / 'formatted' / item['path']) != item['sha256'] for item in record['source_components']):
        raise ValueError('reviewed inputs changed during the host check')
    record.update(passed=True, host_build_script_verified=True, same_exact_bytes_frozen=True,
                  ordinary_no_extra_input=True, repeated_sealed_input_preserved=True,
                  writable_existing_input_refused_unchanged=True)
except Exception as error:
    record['error'] = type(error).__name__ + ': ' + str(error)
finally:
    record['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    (OUT / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({key: record[key] for key in ('passed', 'host_build_script_verified', 'source_components', 'error') if key in record}))
raise SystemExit(0 if record['passed'] else 1)
