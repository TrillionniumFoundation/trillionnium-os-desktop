#!/usr/bin/env python3
"""Build the reviewed ordinary UDP kernel and run its bounded native gates."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import time

ROOT = Path('/home/qian-qi/work/trillionnium-os-20261021-b2da20752f15')
WORK = ROOT / 'os-f1-udp-error-closure-20261023'
OUT = ROOT / 'f1-local-udp-product-build-v1'
BOOT = ROOT / 'f1-local-udp-product-v1'
TARGET = ROOT / 'target-f1-local-udp-20261023-v1'
HEAD = 'c8f0c88ecb640117686ff05f850a73e60688eac7'
TREE = '641c6627ba9aaf79ca3506154831a6c51abe521f'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def git(*args):
    return subprocess.run(['/usr/bin/git', '-C', str(WORK), *args],
                          capture_output=True, check=True, text=True, timeout=30).stdout.strip()


def identity():
    result = {'head': git('rev-parse', 'HEAD'), 'tree': git('rev-parse', 'HEAD^{tree}'),
              'status': git('status', '--porcelain=v1', '--untracked-files=all')}
    assert result == {'head': HEAD, 'tree': TREE, 'status': ''}, result
    return result


def main():
    assert not OUT.exists() and not BOOT.exists() and not TARGET.exists()
    before = identity()
    OUT.mkdir(mode=0o700)
    save(OUT / 'source-before.json', before)
    env = os.environ.copy()
    chosen = {'RUSTUP_HOME': str(ROOT / 'rustup-kernel'),
              'CARGO_HOME': str(ROOT / 'cargo-kernel-e'),
              'RUSTUP_TOOLCHAIN': 'nightly-2026-07-21', 'CARGO_BUILD_JOBS': '3',
              'VDSO_LIBRARY_DIR': str(ROOT / 'os/support/build/out/linux-vdso'),
              'OSDK_LOCAL_DEV': '1', 'PYTHONDONTWRITEBYTECODE': '1',
              'CARGO_TARGET_DIR': str(TARGET), 'A01_RUN_DIR': str(BOOT),
              'HEPTA_G1C_TRUSTED_OBSERVE': '0', 'HEPTA_G1D_TRUSTED_CONTROL': '0'}
    env.update(chosen)
    env['PATH'] = str(ROOT / 'cargo-kernel-e/bin') + ':' + env.get('PATH', '')
    vdso = WORK / 'support/build/out/linux-vdso'
    vdso.parent.mkdir(parents=True, exist_ok=True)
    if not vdso.exists():
        vdso.symlink_to(ROOT / 'os/support/build/out/linux-vdso', target_is_directory=True)
    assert vdso.resolve() == (ROOT / 'os/support/build/out/linux-vdso').resolve()

    def run(name, command, budget):
        argv = ['/usr/bin/timeout', '--signal=TERM', '--kill-after=10s', f'{budget}s',
                '/usr/bin/nice', '-n', '10', *command]
        invocation = {'argv': argv, 'cwd': str(WORK), 'environment': chosen,
                      'source': before, 'started_ns': time.time_ns()}
        save(OUT / (name + '-invocation.json'), invocation)
        start = time.monotonic()
        with (OUT / (name + '.stdout')).open('xb') as stdout, (OUT / (name + '.stderr')).open('xb') as stderr:
            p = subprocess.run(argv, cwd=WORK, env=env, stdin=subprocess.DEVNULL,
                               stdout=stdout, stderr=stderr, check=False)
        result = {'returncode': p.returncode, 'timed_out': p.returncode in (124, 137),
                  'elapsed_seconds': time.monotonic() - start, 'source_head': HEAD, 'source_tree': TREE,
                  'stdout_sha256': sha(OUT / (name + '.stdout')),
                  'stderr_sha256': sha(OUT / (name + '.stderr')),
                  'invocation_sha256': sha(OUT / (name + '-invocation.json'))}
        save(OUT / (name + '-result.json'), result)
        print(json.dumps({'stage': name, **result}), flush=True)
        assert p.returncode == 0, name
        return result

    run('install-osdk', ['make', '-C', str(WORK / 'kernel/asterinas'), '-f', 'Makefile',
                        '-f', str(WORK / 'support/build/minimal.mk'), 'install_osdk',
                        'CARGO_OSDK=' + str(ROOT / 'cargo-kernel-e/bin/cargo-osdk')], 600)
    actual = run('actual-build', ['bash', 'support/build/kernel.sh', 'run_kernel'], 1800)
    after = identity()
    save(OUT / 'source-after.json', after)
    qemu = json.loads((BOOT / 'qemu.json').read_text())
    assert qemu['raw_exit_code'] == 33 and qemu['timed_out'] is False
    assert (BOOT / 'run-exit-code.txt').read_text().strip() == '0'
    item = qemu['artifacts']['-kernel']
    kernel = Path(item['path'])
    if not kernel.is_absolute():
        kernel = Path(qemu['cwd']) / kernel
    assert sha(kernel) == item['sha256'] and kernel.stat().st_size == item['size']
    frozen = OUT / 'product-kernel.elf'
    shutil.copyfile(kernel, frozen)
    assert sha(frozen) == item['sha256']
    frozen.chmod(0o444)
    receipt = {'base_head': 'b824d80d44456c131a6cb9d4fcc84be95c6af273',
               'source_patch_sha256': 'ec6348c6c9428e899b670d293ae65783264cf9fcc024dbd81a15c2f321e01150',
               'source_head': HEAD, 'source_tree': TREE, 'source_clean_before_after': before == after,
               'build_returncode': actual['returncode'], 'build_timed_out': actual['timed_out'],
               'kernel_path': str(frozen), 'kernel_sha256': sha(frozen),
               'actual_build_result_path': str(OUT / 'actual-build-result.json'),
               'actual_build_result_sha256': sha(OUT / 'actual-build-result.json'),
               'ordinary_boot_passed': True, 'ordinary_boot_receipt_sha256': sha(BOOT / 'qemu.json'),
               'no_ktest': True, 'production_ready': False}
    save(OUT / 'build-receipt.json', receipt)
    run('udp-native-regression', ['python3', '-I', '-B', str(Path(__file__).with_name('run_udp_local_error_regression.py')),
                                 '--build-receipt', str(OUT / 'build-receipt.json')], 300)
    run('f1-diagnostic-lifecycle', ['python3', '-I', '-B', str(Path(__file__).with_name('run_f1_local_udp_kernel.py')),
                                   '--build-receipt', str(OUT / 'build-receipt.json')], 720)
    print('ORDINARY_UDP_AND_DIAGNOSTIC_F1_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
