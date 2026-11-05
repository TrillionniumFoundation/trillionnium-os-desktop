#!/usr/bin/env python3
"""Pocket4 fixed-input Java compile only; no APK tools, Android or UI calls."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import struct
import subprocess
import time


ROOT = Path('/home/alex/work/pocket4-qa-window-fix-20261105-r12')
ORIGINAL = Path('/home/alex/work/pocket4-owned-bili-qa-r3-source-01/source')
ORIGINAL_BUILD = Path('/home/alex/work/pocket4-owned-bili-qa-r3-build-01')
JDK = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86')
ANDROID_JAR = JDK.parents[2] / 'sdk/31/public/android.jar'
RELATIVE = 'src/org/droidloom/qa/bili/r3/ActionRunner.java'
MANIFEST_SHA = '91af9446dc2e749ecf3ef75967bfa2154eae8a94a73d9b4149e0574789a5d422'
BUILD_SHA = 'caa1b720b76e319580a912e7b66f2437747c0f8850c753d037bc91127c18f597'
BEFORE_SHA = '374c4b3ba1d83a97a376613b2ab2e015006019a61dd36970b27c64693d5bcef5'
AFTER_SHA = 'd43660d0a3ccfd4226ed8619a52e8d7cf160cf84ec11450a35a03af768a0eb97'
OLD = '''                need(finalWindow.windowId == current.windowId && finalWindow.json.getString("tree_sha256").equals(current.json.getString("tree_sha256")), "FOCUS_CHANGED_BEFORE_ACTION");'''
NEW = '''                need(finalWindow.windowId == current.windowId
                     && finalWindow.json.getString("tree_sha256").equals(current.json.getString("tree_sha256"))
                     && finalWindow.json.getString("window_sha256").equals(current.json.getString("window_sha256")), "FOCUS_CHANGED_BEFORE_ACTION");'''
LIMITS = {'cpu.max': '100000 100000', 'memory.max': '536870912',
          'memory.swap.max': '0', 'pids.max': '128'}
EXPECTED_TOOLS = {'javac': '18351d7a271f6b8bd17f9e8fef6bb04baa7cf008cbc8a3a782a93a2f5c48ecfa',
                  'java': 'cfa21aeadd00925925c9e1287f5c08f3e04ee7f26a9e23d9dbfb16149153d842',
                  'android_jar': '2e71327d66d43cb85a6ac11029376c19067ccc0f15e73c90f2f6777f3be70fb5'}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def metadata(s):
    return tuple(getattr(s, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_nlink',
                                        'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def pin(path, maximum=268435456):
    declared = Path(path)
    path = declared.resolve(strict=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and 0 < first.st_size <= maximum, 'bounded regular input: ' + str(path))
        hasher = hashlib.sha256()
        count = 0
        while True:
            raw = os.read(fd, 65536)
            if not raw:
                break
            count += len(raw)
            need(count <= maximum, 'input size changed')
            hasher.update(raw)
        need(count == first.st_size and metadata(first) == metadata(os.fstat(fd)), 'input changed during read')
        return {'declared_path': str(declared), 'resolved_path': str(path),
                'bytes': count, 'sha256': hasher.hexdigest()}
    finally:
        os.close(fd)


def read_exact(path, expected, maximum=1048576):
    record = pin(path, maximum)
    need(record['sha256'] == expected, 'fixed input changed: ' + str(path))
    raw = Path(path).read_bytes()
    need(len(raw) == record['bytes'] and sha(raw) == expected, 'read changed after pin')
    return raw


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'bytes': len(raw), 'sha256': sha(raw)}


def own_cgroup():
    rows = Path('/proc/self/cgroup').read_text().splitlines()
    need(len(rows) == 1 and rows[0].startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'),
         'own runtime job cgroup required')
    cg = Path('/sys/fs/cgroup') / rows[0][3:].lstrip('/')
    need(cg.name.endswith('.service') and str(os.getpid()) in (cg / 'cgroup.procs').read_text().split(),
         'current process must own this runtime job scope')
    return cg


def resources(cg):
    need(own_cgroup() == cg, 'current job cgroup changed')
    result = {'path': str(cg), 'affinity': sorted(os.sched_getaffinity(0))}
    for name in [*LIMITS, 'memory.current', 'memory.peak', 'memory.events',
                 'memory.swap.current', 'memory.swap.peak', 'cpu.stat']:
        result[name] = (cg / name).read_text().strip()
    need(all(result[name] == value for name, value in LIMITS.items()), 'job resource limit drift')
    return result


def tool_inputs():
    paths = {'javac': JDK / 'bin/javac', 'java': JDK / 'bin/java', 'android_jar': ANDROID_JAR,
             'jdk_release': JDK / 'release', 'jdk_modules': JDK / 'lib/modules',
             'libjli': JDK / 'lib/libjli.so', 'libjvm': JDK / 'lib/server/libjvm.so',
             'libjava': JDK / 'lib/libjava.so', 'libjimage': JDK / 'lib/libjimage.so',
             'jvm_cfg': JDK / 'lib/jvm.cfg', 'java_security': JDK / 'conf/security/java.security'}
    result = {name: pin(path) for name, path in paths.items()}
    for name, expected in EXPECTED_TOOLS.items():
        need(result[name]['sha256'] == expected, 'historical compiler/SDK pin changed: ' + name)
    return result


def classes(path):
    result = {}
    for p in sorted(path.rglob('*.class')):
        row = pin(p, 262144)
        raw = p.read_bytes()
        need(raw[:4] == b'\xca\xfe\xba\xbe', 'class header required')
        minor, major = struct.unpack('>HH', raw[4:8])
        need(major == 52, 'Java 8 target bytecode required')
        result[p.relative_to(path).as_posix()] = {'bytes': row['bytes'], 'sha256': row['sha256'],
                                                'major_version': major, 'minor_version': minor}
    need(len(result) == 6, 'exact original six-class output expected')
    return result


def javac(arm, source, result):
    output = ROOT / (arm + '-classes')
    output.mkdir(mode=0o700)
    argv = [str(JDK / 'bin/javac'), '-J-XX:ActiveProcessorCount=1', '-J-XX:+UseSerialGC', '-J-Xmx256m',
            '-proc:none', '-Xmaxerrs', '20', '-Xmaxwarns', '20', '-source', '8', '-target', '8',
            '-bootclasspath', str(ANDROID_JAR), '-d', str(output), str(source / RELATIVE)]
    environment = {'PATH': str(JDK / 'bin') + ':/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'JAVA_HOME': str(JDK)}
    stdout = ROOT / (arm + '-javac.stdout')
    stderr = ROOT / (arm + '-javac.stderr')
    process = None
    row = {'arm': arm, 'argv': argv, 'environment': environment, 'returncode': None,
           'owned_child_joined': False, 'timed_out': False}
    result['commands'].append(row)
    began = time.monotonic()
    with stdout.open('xb') as out, stderr.open('xb') as err:
        try:
            process = subprocess.Popen(argv, cwd=ROOT, env=environment, stdout=out, stderr=err,
                                       close_fds=True, start_new_session=True)
            row['child_pid'] = process.pid
            row['returncode'] = process.wait(timeout=60)
            row['owned_child_joined'] = True
        except BaseException as exc:
            row['timed_out'] = isinstance(exc, subprocess.TimeoutExpired)
            if process is not None:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                row['returncode'] = process.wait(timeout=5)
                row['owned_child_joined'] = True
            raise
        finally:
            row['elapsed_ms'] = int((time.monotonic() - began) * 1000)
            for stream in (out, err):
                stream.flush()
                os.fsync(stream.fileno())
    row['stdout'] = {'bytes': stdout.stat().st_size, 'sha256': sha(stdout.read_bytes())}
    row['stderr'] = {'bytes': stderr.stat().st_size, 'sha256': sha(stderr.read_bytes()),
                     'text': stderr.read_text()}
    need(row['returncode'] == 0 and row['owned_child_joined'] and not row['timed_out'], 'actual javac failed: ' + arm)
    return classes(output)


def main():
    need(os.getuid() == os.geteuid() == 1000, 'unprivileged build login required')
    need(ROOT.parent.resolve() == ROOT.parent and not os.path.lexists(ROOT), 'fresh exact root required')
    allowed = sorted(os.sched_getaffinity(0))
    need(0 in allowed, 'requested CPU0 not available')
    os.sched_setaffinity(0, {0})
    os.nice(10)
    cg = own_cgroup()
    need(int((cg / 'memory.current').read_text()) < 134217728, 'own job too large before bounded compile')
    for name, value in LIMITS.items():
        (cg / name).write_text(value)
    before_resources = resources(cg)
    available = next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines()
                     if line.startswith('MemAvailable:'))
    need(available >= 805306368, 'insufficient available memory for bounded Java build')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    write_new(ROOT / 'compile-driver.py', SUBMITTED_SOURCE)
    result = {'schema': 1, 'state': 'SDK_COMPILE_FAILED', 'error': None, 'commands': [],
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'own_before': before_resources, 'source_manifest_sha256': MANIFEST_SHA,
              'historical_build_receipt_sha256': BUILD_SHA, 'actual_Android_actions': 0,
              'APK_packaged': False, 'signed': False, 'installed': False,
              'existing_source_modified': False, 'whole_app_production_ready': False}
    try:
        original_manifest = read_exact(ORIGINAL / 'SOURCE_PINS.json', MANIFEST_SHA)
        manifest = json.loads(original_manifest)
        original_build = read_exact(ORIGINAL_BUILD / 'build-result.json', BUILD_SHA)
        build = json.loads(original_build)
        need(build['state'] == 'BUILT_STATIC_VERIFIED_ANDROID_UNRUN' and
             build['source_manifest_sha256'] == MANIFEST_SHA and len(manifest['files']) == 9,
             'actual original build and exact nine-file source required')
        result['dependencies_before'] = tool_inputs()
        write_new(ROOT / 'original-source-manifest.json', original_manifest)
        source_maps = {'preimage': {}, 'candidate': {}}
        for name, expected in manifest['files'].items():
            relative = Path(name)
            need(not relative.is_absolute() and '..' not in relative.parts, 'source manifest relative path required')
            raw = read_exact(ORIGINAL / name, expected['sha256'])
            need(len(raw) == expected['bytes'], 'source byte count changed')
            candidate = raw
            if name == RELATIVE:
                text = raw.decode('utf-8')
                need(sha(raw) == BEFORE_SHA and text.count(OLD) == 1, 'exact Java preimage required')
                candidate = text.replace(OLD, NEW, 1).encode('utf-8')
                need(sha(candidate) == AFTER_SHA, 'exact reviewed Java candidate required')
            source_maps['preimage'][name] = write_new(ROOT / 'preimage-source' / name, raw)
            source_maps['candidate'][name] = write_new(ROOT / 'source' / name, candidate)
        need([name for name in source_maps['preimage'] if source_maps['preimage'][name] != source_maps['candidate'][name]] == [RELATIVE],
             'only ActionRunner may change')
        result['source_files'] = source_maps
        write_new(ROOT / 'preimage-source/SOURCE_PINS.json', original_manifest)
        write_new(ROOT / 'source/SOURCE_PINS.json', {'schema': 1, 'files': source_maps['candidate'],
                  'lineage_source_manifest_sha256': MANIFEST_SHA, 'APK_built': False, 'installed': False})
        result['classes_preimage'] = javac('preimage', ROOT / 'preimage-source', result)
        result['classes_candidate'] = javac('candidate', ROOT / 'source', result)
        need(set(result['classes_preimage']) == set(result['classes_candidate']), 'class membership changed')
        result['changed_classes'] = [name for name in result['classes_preimage']
                                     if result['classes_preimage'][name] != result['classes_candidate'][name]]
        result['unchanged_classes'] = [name for name in result['classes_preimage'] if name not in result['changed_classes']]
        result['historical_classes_currently_observed'] = classes(ORIGINAL_BUILD / 'classes')
        result['preimage_classes_match_historical_current_bytes'] = result['historical_classes_currently_observed'] == result['classes_preimage']
        for name, expected in manifest['files'].items():
            read_exact(ORIGINAL / name, expected['sha256'])
        read_exact(ORIGINAL / 'SOURCE_PINS.json', MANIFEST_SHA)
        read_exact(ORIGINAL_BUILD / 'build-result.json', BUILD_SHA)
        for arm, directory in [('preimage', 'preimage-source'), ('candidate', 'source')]:
            for name, expected in source_maps[arm].items():
                read_exact(ROOT / directory / name, expected['sha256'])
        result['dependencies_after'] = tool_inputs()
        need(result['dependencies_before'] == result['dependencies_after'], 'compiler/SDK dependencies changed')
        result['dependencies_and_sources_unchanged'] = True
        result['state'] = 'COMPLETE_ACTIONRUNNER_SDK_COMPILE_PASS_ANDROID_UNRUN'
    except BaseException as exc:
        result['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        result['own_after'] = resources(cg)
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        receipt = write_new(ROOT / 'result.json', result)
        print(json.dumps({'state': result['state'], 'error': result['error'], 'receipt': receipt,
                          'path': str(ROOT / 'result.json'), 'changed_classes': result.get('changed_classes'),
                          'actual_Android_actions': 0}, sort_keys=True), flush=True)
    return 0 if result['error'] is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
