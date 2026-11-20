#!/usr/bin/env python3
"""Build the exact current 19 normal binaries; no Android or binary execution."""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import time
import traceback

HERE = Path(__file__).resolve().parent
SOURCE_TREE = '7bfb70d7107cb5c95e9aec307124e1369aa735d1'
SOURCE_FILES = 2352
SOURCE_BYTES = 44260146
LEAF_INVENTORY = 'b932f58f5a3eaf7feea4d458fbd67d2e248a29a5aeb45eb940c6f2c7450f6374'
LEAF_VERIFIER = '017c3fa3899f7bc2c1836f1fd748aa333387d3d48d56f9493c87907770b68aef'
LEGACY_INVENTORY = '075affecd123cc60e30eadf70ae95cc9ec34d5686694bedf0914014c36d04c0b'
LEGACY_PINS = {
    'run_ci.py': (38395, '8daf16a61dcdf410088e595f858801e9af1aa40de0f123e76a1f5206136ad488'),
    'verify.py': (30240, '0a669e373aca985a7b3f86b4d5f02782e38fac57ebe098738692897eebf7f0e1'),
    'prepare_ci.sh': (13174, '0efba2cdc98a0c511054e8c8309c0e0a31106ba56734c4d42af7f685099ae181'),
    'EXPECTED-TARGETS.json': (11236, '0e517ed54415a2622b7dfa41d76255ed29774f9aafdc4e684a658131a8225a99'),
    'EXPECTED-BINS.json': (4351, 'd160ba683b67bcae587db4130a38d26735f9cc167fd1c38bddb4e3d3177708fa'),
}
LOCK = (51953, '4eacfb2988079a8f4c10df48aaf649a962cdad0ce94767122c116e15df7d099d')
JOB_INTERVAL_SECONDS = 1680
BUILD_LIMIT_SECONDS = 1200
FINAL_RESERVE_SECONDS = 60


def need(value, message):
    if not value:
        raise ValueError(message)


def f9(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path, cap=64 * 1024**2):
    path = Path(path).absolute()
    need(path.resolve() == path, 'canonical ordinary input required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= cap,
             'bounded regular input required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(before.st_size + 1)
        need(len(raw) == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()),
             'input changed during complete read')
        return raw
    finally:
        os.close(fd)


def fixed(path, pin):
    raw = regular(path)
    need((len(raw), sha(raw)) == tuple(pin), 'fixed input differs: ' + str(path))
    return raw


def verify_packet(inventory_sha256, root=HERE):
    root = Path(root).absolute()
    need(re.fullmatch('[0-9a-f]{64}', inventory_sha256), 'external packet SHA required')
    index = regular(root / 'FILES.sha256', 65536)
    need(sha(index) == inventory_sha256, 'external release packet pin differs')
    wanted = {}
    for line in index.decode('utf-8', 'strict').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        need(match and match[2] != 'FILES.sha256' and match[2] not in wanted,
             'one distinct flat packet member required')
        wanted[match[2]] = match[1]
    names = set()
    for path in root.iterdir():
        need(stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink(),
             'release packet contains an alias or directory')
        names.add(path.name)
    need(names == set(wanted) | {'FILES.sha256'}, 'complete release packet membership differs')
    for name, expected in wanted.items():
        need(sha(regular(root / name)) == expected, 'release packet member differs: ' + name)
    manifest = json.loads(regular(root / 'MANIFEST.json'))
    need(manifest['schema'] == 'p4-current-normal-release19-ci-v1'
         and manifest['source'] == {'tree': SOURCE_TREE, 'files': SOURCE_FILES, 'bytes': SOURCE_BYTES}
         and manifest['required'] == {'workspace_packages': 28, 'metadata_test_targets': 49, 'normal_release_binaries': 19}
         and manifest['leaf_inventory_sha256'] == LEAF_INVENTORY
         and manifest['original_runtime_inventory_sha256'] == LEGACY_INVENTORY,
         'fixed complete source and target contract differs')
    return manifest


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_legacy(root):
    root = Path(root).absolute()
    before = {name: fixed(root / name, pin) for name, pin in LEGACY_PINS.items()}
    module = load_module(root / 'run_ci.py', 'release19_original_ci')
    for name, raw in before.items():
        need(regular(root / name) == raw, 'original helper changed during import')
    return module


def expected_targets(raw, count):
    rows = json.loads(raw)
    need(isinstance(rows, list) and len(rows) == count, 'complete original target roster required')
    mapped = {}
    for row in rows:
        need(set(row) == {'package', 'target', 'kind', 'source_path', 'required_features', 'test'},
             'exact original target fields required')
        key = (row['package'], row['target'])
        need(key not in mapped and row['test'] is True and row['required_features'] == []
             and row['kind'] in (['lib'], ['bin'], ['test']), 'distinct original target required')
        mapped[key] = row
    return mapped


def admitted_budget(started_ns, deadline_ns, now_ns):
    need(type(started_ns) is int and type(deadline_ns) is int and type(now_ns) is int
         and deadline_ns - started_ns == JOB_INTERVAL_SECONDS * 10**9
         and started_ns <= now_ns < deadline_ns, 'original bounded job interval required')
    seconds = min(BUILD_LIMIT_SECONDS, (deadline_ns - now_ns) / 10**9 - FINAL_RESERVE_SECONDS)
    need(seconds >= 180, 'insufficient remaining job interval for release and retirement')
    return seconds


def command_timeout(deadline, maximum, now):
    need(0 < maximum <= 600, 'bounded command interval required')
    seconds = min(maximum, deadline - now - FINAL_RESERVE_SECONDS)
    need(seconds > 0, 'build interval reserved for final retirement and verification')
    return seconds


def clean_environment(original, work, cargo_bin):
    # Same override exclusions as the original release runner, including profiles.
    env = dict(original)
    exact = {'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER',
             'RUSTC', 'RUSTDOC', 'RUSTDOCFLAGS', 'CARGO_ENCODED_RUSTDOCFLAGS', 'LD_LIBRARY_PATH', 'LD_PRELOAD',
             'CARGO_BUILD_TARGET', 'CARGO_BUILD_RUSTFLAGS', 'CARGO_BUILD_RUSTC', 'CARGO_BUILD_RUSTC_WRAPPER',
             'CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER', 'CARGO_BUILD_RUSTDOC', 'CC', 'CXX', 'CPP', 'AR', 'LD', 'RANLIB',
             'CPPFLAGS', 'LDFLAGS', 'PKG_CONFIG', 'BINDGEN_EXTRA_CLANG_ARGS', 'RUSTC_BOOTSTRAP',
             'RUST_TEST_THREADS', 'RUST_TEST_NOCAPTURE', 'MAKEFLAGS', 'MFLAGS', 'CARGO_MAKEFLAGS'}
    prefixes = ('CARGO_TARGET_', 'CARGO_PROFILE_', 'CC_', 'CXX_', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS_',
                'LDFLAGS_', 'AR_', 'LD_', 'PKG_CONFIG_', 'BINDGEN_EXTRA_CLANG_ARGS_', 'CARGO_BUILD_', 'CARGO_NET_')
    for key in list(env):
        if key in exact or key.startswith(prefixes):
            del env[key]
    for key in ('FAKEROOTKEY', 'FAKED_MODE', 'DROIDLOOM_IMAGE_POLICY_TEST', 'DROIDLOOM_GAPPS_EROFS_TEST',
                'DROIDLOOM_TEST_DRM_NODE', 'DBUS_SESSION_BUS_ADDRESS', 'WAYLAND_DISPLAY', 'DISPLAY', 'RUST_MIN_STACK'):
        env.pop(key, None)
    env.update(CARGO_HOME=str(work / 'cargo-home'), CARGO_TARGET_DIR=str(work / 'target'),
               CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS='1', CARGO_TERM_COLOR='never', RAYON_NUM_THREADS='1',
               RUSTUP_TOOLCHAIN='1.93.0', RUSTUP_AUTO_INSTALL='0', LANG='C.UTF-8', LC_ALL='C.UTF-8',
               PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(work / 'tmp'), GIT_CONFIG_NOSYSTEM='1',
               GIT_CONFIG_GLOBAL='/dev/null', GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0',
               GIT_TERMINAL_PROMPT='0', PKG_CONFIG='/usr/bin/pkgconf', CC='/usr/bin/x86_64-linux-gnu-gcc-13',
               PATH=str(cargo_bin) + ':/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin')
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--legacy-packet', type=Path, required=True)
    parser.add_argument('--leaf-packet', type=Path, required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--dependencies', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    manifest = verify_packet(args.inventory_sha256)
    ci = load_legacy(args.legacy_packet)
    v = ci.VERIFY
    producer = args.producer.absolute()
    protected = [HERE, args.legacy_packet.absolute(), args.leaf_packet.absolute(), producer,
                 args.dependencies.absolute().parent]
    work = v.fresh_destination(args.work, protected)
    report = v.fresh_destination(args.report, protected + [work])
    work.mkdir(mode=0o700)
    for name in ('target', 'cargo-home', 'tmp', 'logs', 'artifacts'):
        (work / name).mkdir(mode=0o700)
    result = {'schema': 'p4-current-normal-release19-result-v1', 'state': 'RUNNING',
              'source': manifest['source'], 'required': manifest['required'],
              'packet_inventory_sha256': args.inventory_sha256,
              'leaf_inventory_sha256': LEAF_INVENTORY, 'legacy_inventory_sha256': LEGACY_INVENTORY,
              'started_ns': time.time_ns(), 'commands': [], 'errors': [], 'fresh_release_binaries': {},
              'fresh_ordinary_tests': 0, 'historical_tests_counted_as_fresh': 0,
              'historical_ELFs_reused': False, 'binary_executions': 0, 'jobs': 1,
              'Android_builds': 0, 'Android_starts': 0, 'runtime_qualified': False,
              'production_ready': False, 'full_workspace_qualified': False,
              'Pocket4_runtime_ABI_verified': False, 'activated': False}
    before = None
    leaf = None
    frozen = {}
    deadline = time.monotonic()
    try:
        need(os.geteuid() != 0 and os.uname().machine == 'x86_64', 'ordinary x86_64 CI user required')
        release = Path('/etc/os-release').read_text()
        need(re.search(r'^ID=ubuntu$', release, re.M) and re.search(r'^VERSION_ID="24\.04"$', release, re.M),
             'isolated Ubuntu 24.04 build environment required')
        budget = admitted_budget(int(os.environ['P4_SUCCESSOR_JOB_STARTED_NS']),
                                 int(os.environ['P4_SUCCESSOR_JOB_DEADLINE_NS']), time.time_ns())
        deadline = time.monotonic() + budget
        result.update(whole_limit_seconds=budget, maximum_build_seconds=BUILD_LIMIT_SECONDS,
                      final_reserve_seconds=FINAL_RESERVE_SECONDS,
                      job_deadline_ns=int(os.environ['P4_SUCCESSOR_JOB_DEADLINE_NS']))
        cpus = sorted(os.sched_getaffinity(0))
        need(len(cpus) >= 4, 'two build CPUs and two reserved logical CPUs required')
        os.sched_setaffinity(0, set(cpus[:2]))
        result.update(affinity=cpus[:2], reserved_cpus=cpus[2:])
        need(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0, 'owned-child subreaper required')
        need(not ci.owned_children(), 'unexpected preexisting child')
        signal.signal(signal.SIGTERM, ci.interrupted)
        signal.signal(signal.SIGINT, ci.interrupted)
        signal.signal(signal.SIGALRM, ci.interrupted)
        signal.setitimer(signal.ITIMER_REAL, budget)
        ci.VERIFY.verify_capsule(LEGACY_INVENTORY)
        need(sha(regular(args.leaf_packet / 'verify.py')) == LEAF_VERIFIER, 'fixed leaf verifier required')
        leaf = load_module(args.leaf_packet / 'verify.py', 'release19_leaf_source')
        packet = leaf.verify_packet(LEAF_INVENTORY)
        need(packet['manifest']['successor'] == {'source_tree': SOURCE_TREE, 'source_files': SOURCE_FILES,
                                               'source_bytes': SOURCE_BYTES}, 'complete current source required')
        before = leaf.source_snapshot(producer, packet['after'], SOURCE_TREE)
        fixed(producer / 'Cargo.lock', LOCK)
        expected_tests = expected_targets(fixed(args.legacy_packet / 'EXPECTED-TARGETS.json',
                                               LEGACY_PINS['EXPECTED-TARGETS.json']), 49)
        expected_bins = expected_targets(fixed(args.legacy_packet / 'EXPECTED-BINS.json',
                                              LEGACY_PINS['EXPECTED-BINS.json']), 19)
        dependencies_body = regular(args.dependencies)
        dependencies = json.loads(dependencies_body)
        need(dependencies['state'] == 'DEPENDENCIES_PREPARED' and not dependencies['errors']
             and dependencies['final_retirement'] == [] and dependencies['producer_builds'] == 0
             and dependencies['Android_builds'] == dependencies['Android_starts'] == 0,
             'actual dependency preparation and retirement required')
        result['dependency_receipt'] = {'path': str(args.dependencies), **v.digest(dependencies_body)}
        result['package_versions'] = dependencies['package_versions']
        cargo = shutil.which('cargo')
        need(cargo is not None, 'existing Rust 1.93.0 toolchain required')
        env = clean_environment(os.environ, work, Path(cargo).absolute().parent)
        result['tool_identities'] = {}
        for requested in (cargo, '/usr/bin/x86_64-linux-gnu-gcc-13', '/usr/bin/pkgconf', '/usr/bin/readelf'):
            actual = Path(requested).resolve(strict=True)
            body = regular(actual)
            need(os.access(actual, os.X_OK), 'native tool is not executable')
            result['tool_identities'][requested] = {'resolved_path': str(actual), **v.digest(body),
                                                     'identity': f9(actual.lstat())}

        def run(name, argv, maximum):
            need(not ci.owned_children(), 'previous command owns children')
            need(shutil.disk_usage(work).free >= 8 * 1024**3, 'eight GiB free build reserve required')
            timeout = command_timeout(deadline, maximum, time.monotonic())
            outpath, errpath = work / 'logs' / (name + '.stdout'), work / 'logs' / (name + '.stderr')
            started = time.time_ns()
            with outpath.open('xb') as out, errpath.open('xb') as err:
                execution = ci.execute_child(argv, producer, env, out, err, timeout)
            raw, err = regular(outpath), regular(errpath)
            row = {'name': name, 'argv': argv, 'cwd': str(producer), 'timeout_seconds': timeout,
                   'started_ns': started, 'finished_ns': time.time_ns(), **execution,
                   'stdout': {'path': str(outpath), **v.digest(raw)},
                   'stderr': {'path': str(errpath), **v.digest(err)}}
            result['commands'].append(row)
            need(execution['error'] is None and not execution['cleanup_errors']
                 and execution['exit_code'] == 0 and execution['actual_child_reaped']
                 and execution['original_pidfd_held_until_reaped'] and not ci.owned_children()
                 and not any(x.get('forced') for x in execution['retired_descendants']),
                 'actual command or owned-child retirement failed: ' + name)
            need(time.monotonic() < deadline, 'whole release deadline expired')
            return row, raw

        _, raw = run('rustc-version', ['rustc', '+1.93.0', '--version', '--verbose'], 30)
        need(b'release: 1.93.0\n' in raw, 'exact Rust 1.93.0 compiler required')
        _, raw = run('gcc-version', ['/usr/bin/x86_64-linux-gnu-gcc-13', '-dumpfullversion'], 30)
        need(re.fullmatch(rb'13\.[0-9]+\.[0-9]+\n', raw), 'actual GCC 13 required')
        run('dependency-fetch', ['cargo', '+1.93.0', 'fetch', '--locked'], 120)
        env['CARGO_NET_OFFLINE'] = 'true'
        _, raw = run('workspace-metadata', ['cargo', '+1.93.0', 'metadata', '--offline', '--locked',
                                          '--no-deps', '--format-version=1'], 60)
        ids = ci.metadata_targets(raw, producer, expected_tests, expected_bins)
        packages = sorted(ids.values())
        need(len(set(packages)) == len(packages) == 28, 'complete 28-package workspace required')
        batches = [('updater', ['droidloom-update']),
                   ('remaining27', [p for p in packages if p != 'droidloom-update'])]
        need(len(batches[1][1]) == 27 and set(batches[0][1] + batches[1][1]) == set(packages),
             'two disjoint complete package batches required')
        result.update(actual_workspace_packages=packages, actual_metadata_test_targets=len(expected_tests))
        released, built_by = {}, {}
        for label, selected in batches:
            expected = {k: row for k, row in expected_bins.items() if k[0] in selected}
            flags = [value for package in selected for value in ('-p', package)]
            command, raw = run('normal-release-' + label,
                               ['cargo', '+1.93.0', 'build', '--offline', '--locked', *flags,
                                '--release', '-j1', '--bins', '--message-format=json'], 600)
            actual = ci.artifacts(raw, ids, producer, work / 'target', expected, False)
            need(not set(released) & set(actual), 'release batches overlap')
            released.update(actual)
            built_by.update({key: command for key in actual})
        need(set(released) == set(expected_bins) and len(released) == 19,
             'actual fresh union must contain all original 19 normal targets')
        for key, item in sorted(released.items()):
            ref, body = ci.elf(item['path'], with_body=True)
            command = built_by[key]
            need(command['started_ns'] <= ref['identity'][7] <= command['finished_ns']
                 and command['started_ns'] <= ref['identity'][8] <= command['finished_ns'],
                 'actual release ELF predates its build')
            aliases = ci.aliases(ref, work / 'target' / 'release')
            output = work / 'artifacts' / key[1]
            with output.open('xb') as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            output.chmod(0o500)
            delivered = ci.elf(output)
            need(delivered['sha256'] == ref['sha256'] and delivered['bytes'] == ref['bytes']
                 and delivered['identity'][5] == 1, 'independent complete delivery ELF copy required')
            frozen[key] = (ref, delivered)
            result['fresh_release_binaries'][key[1]] = {'package': key[0], **ref,
                'all_original_aliases': aliases, 'delivery': delivered}
        run('elf-dynamic-and-version-requirements', ['/usr/bin/readelf', '--dynamic', '--version-info',
             *[str(released[key]['path']) for key in sorted(released)]], 30)
        need(len(result['fresh_release_binaries']) == 19, 'all 19 normal binaries required')
        result['state'] = 'ALL19_CURRENT_NORMAL_RELEASE_BUILDS_PASSED'
    except BaseException as error:
        result['state'] = 'FAILED'
        result['errors'].append({'type': type(error).__name__, 'message': str(error),
                                 'traceback': traceback.format_exc()})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        try:
            result['final_retirement'] = ci.reap_descendants()
            need(not result['final_retirement'] and not ci.owned_children(), 'unexpected remaining build children')
            if before is not None:
                need(leaf.source_snapshot(producer, packet['after'], SOURCE_TREE) == before,
                     'complete current source changed during build')
                fixed(producer / 'Cargo.lock', LOCK)
                result['complete_source_bookends_equal'] = True
            for ref, delivered in frozen.values():
                need(ci.elf(ref['path']) == ref and ci.elf(delivered['path']) == delivered,
                     'release or delivery ELF changed before final custody')
                ci.aliases(ref, work / 'target' / 'release')
            if result['state'] == 'ALL19_CURRENT_NORMAL_RELEASE_BUILDS_PASSED':
                need({p.name for p in (work / 'artifacts').iterdir()} == set(result['fresh_release_binaries']),
                     'delivery directory must contain exactly the 19 current binaries')
            verify_packet(args.inventory_sha256)
            for name, pin in LEGACY_PINS.items():
                fixed(args.legacy_packet / name, pin)
            if leaf is not None:
                leaf.verify_packet(LEAF_INVENTORY)
            if 'dependencies_body' in locals():
                need(regular(args.dependencies) == dependencies_body, 'dependency receipt changed')
            if time.monotonic() >= deadline:
                raise TimeoutError('whole release interval expired before complete final verification')
        except BaseException as error:
            result['state'] = 'FAILED'
            result['errors'].append({'final_verification': repr(error)})
    result['finished_ns'] = time.time_ns()
    v.write_report(report, result, protected + [work])
    print(json.dumps({'state': result['state'], 'source_tree': SOURCE_TREE,
                      'fresh_normal_release_count': len(result['fresh_release_binaries']),
                      'report': str(report), 'production_ready': False}, sort_keys=True))
    return 0 if result['state'] == 'ALL19_CURRENT_NORMAL_RELEASE_BUILDS_PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
