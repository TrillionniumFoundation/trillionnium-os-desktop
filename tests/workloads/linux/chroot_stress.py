#!/usr/bin/env python3
"""Repeated ORIGINAL Linux chroot stress for the same pinned A04 application probes.

This is not Asterinas, Hepta, CPU scheduling qualification or an S1 crash test.
Only synthetic /tmp test directories are writable. The fixed 17-file rootfs
is verified and extracted to a disposable location, then each child drops to
uid/gid 65534. A failing case or timeout is preserved as a failure, never a
skip or ABI diagnosis. Per-case assertions compare complete observable facts.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
# Process-group timeout cleanup is centralized in chroot.bounded_run.
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = load('a04_stress_capture', ROOT / 'support/rootfs/capture.py')
chroot = load('a04_stress_chroot', HERE / 'chroot_replay.py')
guest = load('a04_stress_guest', HERE / 'guest.py')

STRESS_KINDS = frozenset(('threads_futex', 'async_fd', 'robust_owner_death',
                          'uds_peercred', 'scm_rights', 'file_lock', 'process',
                          'mmap_cow', 'sqlite_wal_elf'))


def selected_cases(reference):
    """Use only already-proven, hash-pinned Linux C ELF application behaviors."""
    cases = [(name, stem, case) for name, stem, case in guest.reference_elf_cases(reference)
             if case in STRESS_KINDS]
    stems = {'static', 'dynamic', 'sqlite_static', 'sqlite_dynamic'}
    if {stem for _, stem, _ in cases} != stems or len(cases) != 18:
        raise ValueError('missing a required stress workload in the pinned Linux reference')
    for name, _, _ in cases:
        obs = reference['cases'][name]
        if obs.get('status') != 'pass' or obs.get('exit_code') != 0 or obs.get('facts', {}).get('ok') is not True:
            raise ValueError(f'Linux reference has not proven {name}')
    return cases


def run_case(command, *, root, scratch, timeout):
    """Use the same bounded descendant/pipe cleanup as one-shot chroot."""
    return chroot.bounded_run(
        command, env={'LC_ALL': 'C', 'TZ': 'UTC', 'PATH': '/usr/local/bin/a04',
                      'HOME': scratch}, timeout=timeout,
        preexec_fn=lambda: chroot.enter_chroot(root))


def run(tar_path, manifest_path, reference, *, rounds=8, timeout=12):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('only x86_64 original Linux can establish this baseline')
    if os.geteuid() != 0:
        raise PermissionError('disposable host root/CAP_SYS_CHROOT required')
    if rounds < 1 or rounds > 40 or timeout < 1 or timeout > 30:
        raise ValueError('rounds must be 1..40, timeout must be 1..30 seconds')
    selected = selected_cases(reference)
    manifest = json.loads(Path(manifest_path).read_text())
    pinned = {entry['name']: entry for entry in manifest['elf']}
    for _, stem, _ in selected:
        record = pinned[guest.BINARY_FOR[stem]]
        if record['sha256'] != reference['binaries'][stem]['sha256']:
            raise ValueError('ELF SHA in rootfs manifest differs from pinned Linux baseline')
    results = []
    with tempfile.TemporaryDirectory(prefix='a04-linux-stress-') as td:
        root = Path(td) / 'root'
        count = capture.extract_verified_tar(tar_path, manifest_path, root)
        guest.verify_binary_identity(root, manifest, reference,
                                     required_stems=reference['binaries'])
        root.chmod(0o755)
        (root / 'tmp').mkdir(mode=0o1777)
        (root / 'tmp').chmod(0o1777)
        (root / 'tmp/a04').mkdir(mode=0o711)
        (root / 'tmp/a04').chmod(0o711)
        for iteration in range(rounds):
            for name, stem, case in selected:
                scratch = f'/tmp/a04/r{iteration:02d}-{name}'
                scratch_dir = root / scratch.lstrip('/')
                scratch_dir.mkdir(mode=0o700)
                os.chown(scratch_dir, 65534, 65534)
                binary = pinned[guest.BINARY_FOR[stem]]['path']
                command = [binary] + ([scratch] if stem.startswith('sqlite_') else [case, scratch])
                result = run_case(command, root=root, scratch=scratch, timeout=timeout)
                expected = reference['cases'][name]
                facts, passed, failure_reason = chroot.exact_observation(result, expected)
                results.append({'case':name, 'round':iteration,
                                'status':'pass' if passed else 'fail',
                                'exit_code':result['exit_code'],
                                'timed_out':result['timed_out'],
                                'facts_equal_reference':facts == expected['facts'],
                                'error':'none' if passed else failure_reason})
                if not passed:
                    # Preserve failure and stop rather than hiding it in later successes.
                    break
            if results[-1]['status'] == 'fail':
                break
    passed = sum(x['status'] == 'pass' for x in results)
    return {'schema':1, 'suite':'a04-original-linux-chroot-app-stress',
            'platform':{'system':'Linux', 'architecture':'x86_64', 'chroot_uid_gid':65534,
                        'guest_kernel':'NOT_RUN', 'guest_execution_verified':False},
            'rounds_requested':rounds, 'cases_per_round':len(selected),
            'executions_expected':rounds*len(selected),
            'executions_completed':len(results), 'passed':passed,
            'failed':len(results)-passed, 'rootfs_verified_files':count,
            'rootfs_tar_sha256':capture.sha(tar_path),
            'rootfs_manifest_sha256':capture.sha(manifest_path),
            'fixed_elf_sha256':{stem:reference['binaries'][stem]['sha256']
                                for stem in guest.BINARY_FOR},
            'results':results, 'hepta_e2e_verified':False,
            's1_crash_durability_verified':False}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tar',type=Path,required=True)
    ap.add_argument('--manifest',type=Path,required=True)
    ap.add_argument('--reference',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--rounds',type=int,default=8)
    ap.add_argument('--timeout',type=int,default=12)
    args=ap.parse_args()
    if args.output.exists() or args.output.is_symlink():
        ap.error('refusing to overwrite previous evidence')
    try:
        report=run(args.tar.resolve(),args.manifest.resolve(),json.loads(args.reference.read_text()),
                   rounds=args.rounds,timeout=args.timeout)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
        print(json.dumps({k:report[k] for k in ('executions_expected','executions_completed','passed','failed')}))
        return 0 if report['failed'] == 0 and report['executions_completed'] == report['executions_expected'] else 1
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        ap.exit(2,'original Linux chroot stress blocked: '+type(exc).__name__+': '+str(exc)+'\n')


if __name__ == '__main__':
    sys.exit(main())
