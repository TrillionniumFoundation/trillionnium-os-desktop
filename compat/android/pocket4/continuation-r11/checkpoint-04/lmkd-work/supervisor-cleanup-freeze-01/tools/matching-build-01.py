#!/usr/bin/env python3
"""Create-only bound-source copy, owned controls and candidate build; no deployment."""
from pathlib import Path, PurePosixPath
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time

SOURCE = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/production-media-term-candidate')
ROOT = Path('/home/alex/work/pocket4-supervisor-cleanup-r11-build-01')
ARCHIVE = Path('/home/alex/work/pocket4-supervisor-cleanup-r11-input-01.tar.gz')
ARCHIVE_SHA = '2dcb8bd08fe643bbd8b67d8a18211c6d41874272a7d820561ebaec8b2fb4026c'
MANIFEST_SHA = '9da94754fd2170cfb7f708e3371f2a5cdfb21d6b1f2a118e6c2df73f0457b23c'
INVENTORY_SHA = 'c50e4a1e2b28ee60497f649b2bf4457ad7255e868407bed59522f2597131333b'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def exclusive(path, raw, mode=0o600):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, mode)


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def safe_name(name):
    path = PurePosixPath(name)
    return name and not path.is_absolute() and '..' not in path.parts and str(path) == name


def inventory(root, expected):
    result = {}
    for name, entry in expected.items():
        require(safe_name(name), 'noncanonical source path')
        path = root / name
        metadata = path.lstat()
        mode = oct(stat.S_IMODE(metadata.st_mode))
        if entry['kind'] == 'directory':
            require(stat.S_ISDIR(metadata.st_mode), 'source directory type mismatch: ' + name)
            result[name] = {'kind': 'directory', 'mode': mode}
        else:
            require(entry['kind'] == 'file' and stat.S_ISREG(metadata.st_mode), 'source file type mismatch: ' + name)
            raw = path.read_bytes()
            result[name] = {'kind': 'file', 'mode': mode, 'bytes': len(raw), 'sha256': sha(raw)}
    return result


def copy_source(destination, expected):
    destination.mkdir(mode=0o700)
    for name, entry in sorted(expected.items(), key=lambda pair: (len(PurePosixPath(pair[0]).parts), pair[0])):
        path = destination / name
        mode = int(entry['mode'], 8)
        if entry['kind'] == 'directory':
            path.mkdir(mode=mode)
            os.chmod(path, mode)
        else:
            exclusive(path, (SOURCE / name).read_bytes(), mode)
    require(inventory(destination, expected) == expected, 'copied source does not match original inventory')


def main():
    receipt = {'schema': 1, 'started_at': utc(), 'success': False, 'commands': [],
               'source_root': str(SOURCE), 'build_root': str(ROOT),
               'source_inventory_sha256': INVENTORY_SHA, 'overlay_manifest_sha256': MANIFEST_SHA,
               'archive_sha256': ARCHIVE_SHA, 'installed_files_changed': False,
               'android_or_main_started': False, 'host_network_effects_executed': False}
    created = False
    try:
        own = Path('/proc/self/cgroup').read_text()
        require(own.startswith('0::/') and own.count('\n') == 1, 'unified own cgroup required')
        cgroup = Path('/sys/fs/cgroup') / own[3:].strip().lstrip('/')
        memory = (cgroup / 'memory.max').read_text().strip()
        cpu = (cgroup / 'cpu.max').read_text().strip()
        nice = os.getpriority(os.PRIO_PROCESS, 0)
        require(memory == '536870912' and cpu.split()[0] == cpu.split()[1] and nice >= 5, '1 CPU/512 MiB/nice5 gate failed')
        event_before = (cgroup / 'memory.events').read_text()
        receipt['resources'] = {'memory_max': memory, 'cpu_max': cpu, 'nice': nice, 'memory_events_before': event_before}
        packed = ARCHIVE.read_bytes()
        require(len(packed) == 70389 and sha(packed) == ARCHIVE_SHA, 'archive pin differs')
        contents = {}
        with tarfile.open(fileobj=io.BytesIO(packed), mode='r:gz') as archive:
            members = archive.getmembers()
            require(len(members) == 6, 'archive member count')
            for member in members:
                require(member.isfile() and safe_name(member.name) and member.name not in contents and member.size < 1048576, 'archive member rejected')
                raw = archive.extractfile(member).read()
                require(len(raw) == member.size and b'\0' not in raw, 'text archive member invalid')
                raw.decode('utf-8')
                contents[member.name] = raw
        require(sha(contents['overlay-manifest.json']) == MANIFEST_SHA, 'overlay manifest pin differs')
        require(sha(contents['source-inventory.json']) == INVENTORY_SHA, 'source inventory pin differs')
        manifest = json.loads(contents['overlay-manifest.json'])
        expected = json.loads(contents['source-inventory.json'])
        require(len(expected) == 561 and manifest['original_source'] == str(SOURCE), 'bound source identity differs')
        require(set(contents) == {'overlay/' + name for name in manifest['files']} | {'overlay-manifest.json', 'source-inventory.json'}, 'archive set differs')
        for name, entry in manifest['files'].items():
            raw = contents['overlay/' + name]
            require(safe_name(name) and len(raw) == entry['bytes'] and sha(raw) == entry['sha256'], 'overlay bytes differ: ' + name)
            require(expected[name]['sha256'] == entry['preimage_sha256'] and expected[name]['bytes'] == entry['preimage_bytes'], 'overlay preimage differs')
        require(inventory(SOURCE, expected) == expected, 'retained source no longer matches 561-entry installed binding')
        ROOT.mkdir(mode=0o700)
        created = True
        (ROOT / 'logs').mkdir(mode=0o700)
        exclusive(ROOT / 'source-inventory.json', contents['source-inventory.json'])
        exclusive(ROOT / 'overlay-manifest.json', contents['overlay-manifest.json'])
        baseline = ROOT / 'baseline'
        candidate = ROOT / 'candidate'
        copy_source(baseline, expected)
        copy_source(candidate, expected)
        for name, entry in manifest['files'].items():
            path = candidate / name
            path.write_bytes(contents['overlay/' + name])
            os.chmod(path, int(expected[name]['mode'], 8))
        cargo = shutil.which('cargo') or '/home/alex/.cargo/bin/cargo'
        rustfmt = shutil.which('rustfmt') or '/home/alex/.cargo/bin/rustfmt'
        require(Path(cargo).is_file() and Path(rustfmt).is_file(), 'existing Rust toolchain required')
        env = os.environ.copy()
        for key in ['RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_BUILD_TARGET', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER']:
            env.pop(key, None)
        env.update(CARGO_TARGET_DIR=str(ROOT / 'target'), CARGO_BUILD_JOBS='1', RUST_TEST_THREADS='1',
                   CARGO_INCREMENTAL='0', CARGO_PROFILE_DEV_DEBUG='0', CARGO_PROFILE_TEST_DEBUG='0')
        receipt['environment_controls'] = {key: env.get(key) for key in ['CARGO_BUILD_JOBS', 'RUST_TEST_THREADS', 'CARGO_INCREMENTAL', 'CARGO_PROFILE_DEV_DEBUG', 'CARGO_PROFILE_TEST_DEBUG']}

        def command(name, argv, cwd, timeout=150, expected_code=0):
            begin = time.monotonic()
            completed = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=timeout)
            require(len(completed.stdout) < 262144 and len(completed.stderr) < 262144, 'command output bound exceeded')
            exclusive(ROOT / 'logs' / (name + '.stdout'), completed.stdout)
            exclusive(ROOT / 'logs' / (name + '.stderr'), completed.stderr)
            row = {'name': name, 'argv': argv, 'cwd': str(cwd), 'returncode': completed.returncode,
                   'elapsed_seconds': time.monotonic() - begin, 'stdout': completed.stdout.decode(errors='replace'),
                   'stderr': completed.stderr.decode(errors='replace'), 'stdout_sha256': sha(completed.stdout),
                   'stderr_sha256': sha(completed.stderr)}
            receipt['commands'].append(row)
            print(json.dumps({'command': name, 'returncode': completed.returncode}), flush=True)
            require(completed.returncode == expected_code, name + ' unexpected exit')
            return row

        rust_files = [name for name in manifest['files'] if name.endswith('.rs')]
        command('rustfmt', [rustfmt, '--edition', '2024', *rust_files], candidate, 30)
        build_inputs = inventory(candidate, expected)
        exclusive(ROOT / 'candidate-source-inventory.json', encode(build_inputs))
        receipt['candidate_source_inventory_sha256'] = sha(encode(build_inputs))
        receipt['formatted_overlays'] = {name: build_inputs[name] for name in manifest['files']}
        with tarfile.open(ROOT / 'formatted-overlay.tar.gz', 'w:gz') as archive:
            for name in sorted(manifest['files']):
                raw = (candidate / name).read_bytes()
                member = tarfile.TarInfo(name)
                member.size = len(raw)
                member.mode = 0o600
                member.mtime = 0
                archive.addfile(member, io.BytesIO(raw))
        receipt['formatted_overlay_archive'] = {'bytes': (ROOT / 'formatted-overlay.tar.gz').stat().st_size,
            'sha256': sha((ROOT / 'formatted-overlay.tar.gz').read_bytes())}

        # One additional test is appended to the exact original production
        # source, without changing its cleanup implementation. It must expose
        # the prior false-success on a real owned child + runtime-directory error.
        candidate_development = (candidate / 'runtime/droidloom-supervisor/src/development.rs').read_text()
        helper_start = candidate_development.index('#[cfg(test)]\npub(crate) fn owned_cleanup_test_spec')
        helper_end = candidate_development.index('/// Start a development cell', helper_start)
        helper = candidate_development[helper_start:helper_end]
        control = '''
#[cfg(test)]
mod cleanup_regression_control {
    use super::*;
    #[test]
    fn repeated_owned_cleanup_must_not_report_success() {
        let directory = tempfile::tempdir().unwrap();
        let spec = owned_cleanup_test_spec(directory.path());
        fs::create_dir(&spec.runtime_dir).unwrap();
        fs::create_dir(spec.runtime_dir.join("android-cmdline")).unwrap();
        let mut child = std::process::Command::new("/bin/true").spawn().unwrap();
        assert!(child.wait().unwrap().success());
        let mut cell = DevelopmentCell {spec, child, network: None, cleaned: false};
        assert!(cell.try_wait().is_err(), "the first real cleanup must fail");
        assert!(cell.try_wait().is_err(), "cleanup failure became false success on the second poll");
    }
}
'''
        original_path = baseline / 'runtime/droidloom-supervisor/src/development.rs'
        original = original_path.read_bytes()
        require(sha(original) == expected['runtime/droidloom-supervisor/src/development.rs']['sha256'], 'baseline production preimage differs')
        append = ('\n' + helper + control).encode()
        original_path.write_bytes(original + append)
        exclusive(ROOT / 'baseline-appended-control.rs', append)
        receipt['baseline_test_only_append_sha256'] = sha(append)
        baseline_row = command('preimage-negative-control', [cargo, 'test', '--locked', '--offline', '-j', '1', '-p', 'droidloom-supervisor', '--lib', '--', '--exact', 'development::cleanup_regression_control::repeated_owned_cleanup_must_not_report_success', '--test-threads=1'], baseline, 150, 101)
        require('cleanup failure became false success on the second poll' in baseline_row['stdout'] and 'test result: FAILED. 0 passed; 1 failed;' in baseline_row['stdout'], 'preimage did not fail for the expected real cleanup defect')
        receipt['preimage_false_success_reproduced'] = True
        row = command('candidate-tests', [cargo, 'test', '--locked', '--offline', '-j', '1', '-p', 'droidloom-supervisor', '--', '--test-threads=1'], candidate, 150)
        passed = sum(map(int, re.findall(r'test result: ok\. (\d+) passed;', row['stdout'])))
        require(passed == 91 and '0 ignored;' in row['stdout'] and 'test result: FAILED' not in row['stdout'], 'expected 91 supervisor tests not observed')
        receipt['candidate_tests_passed'] = passed
        command('candidate-binaries', [cargo, 'build', '--locked', '--offline', '-j', '1', '-p', 'droidloom-supervisor', '--bins'], candidate, 150)
        require(inventory(candidate, expected) == build_inputs, 'candidate inputs changed during actual build/tests')
        require(inventory(SOURCE, expected) == expected, 'original retained source changed')
        receipt['candidate_inputs_unchanged'] = True
        receipt['original_561_entries_unchanged'] = True
        receipt['binaries'] = {}
        for name in ['droidloomd', 'droidloomctl', 'droidloom-supervisor']:
            path = ROOT / 'target/debug' / name
            raw = path.read_bytes()
            require(raw.startswith(b'\x7fELF'), 'missing built ELF: ' + name)
            receipt['binaries'][name] = {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}
        event_after = (cgroup / 'memory.events').read_text()
        receipt['resources']['memory_events_after'] = event_after
        before = dict(line.split() for line in event_before.splitlines())
        after = dict(line.split() for line in event_after.splitlines())
        require(all(before[key] == after[key] for key in ['max', 'oom', 'oom_kill', 'oom_group_kill']), 'build memory event changed')
        receipt['success'] = True
    except Exception as error:
        receipt['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        receipt['finished_at'] = utc()
        raw = encode(receipt)
        if created:
            exclusive(ROOT / 'build-result.json', raw)
        print(json.dumps({'success': receipt['success'], 'error': receipt.get('error'),
                          'receipt': str(ROOT / 'build-result.json') if created else None,
                          'receipt_sha256': sha(raw) if created else None,
                          'preimage_false_success_reproduced': receipt.get('preimage_false_success_reproduced'),
                          'candidate_tests_passed': receipt.get('candidate_tests_passed')}), flush=True)
    return 0 if receipt['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
