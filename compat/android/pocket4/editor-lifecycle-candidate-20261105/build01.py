#!/usr/bin/python3 -I
"""Compile an exact installed-DEX lifecycle patch, without signing or Android IO."""
from pathlib import Path
import argparse, datetime, gzip, hashlib, json, os, re, shutil, signal
import subprocess, sys, time, types, zipfile

HERE = Path(__file__).resolve().parent
OUT = Path('/home/alex/work/pocket4-editor-recovery-build-20261105-r12-01')
PARENT_APK = Path('/home/alex/work/pocket4-qa-packages-preflight-20261105-r12-01/org.droidloom.qa.editorcontract.apk')
PARENT_APK_SHA = '0d08f59024e4228e5d5b8f56742aafd1fbc04966d74224acd48542e09482743d'
PARENT_DEX_SHA = '07370b01a50f994d3ff465d1001989e48ff0d5c285564d35b97c81fdb9fa787d'
LIMITS = {'cpu.max': '100000 100000', 'memory.max': '536870912',
          'memory.swap.max': '0', 'pids.max': '128'}


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pin(path):
    path = Path(path).resolve(strict=True)
    before = path.stat()
    value = digest(path)
    after = path.stat()
    keys = ('st_ino', 'st_dev', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(0 < before.st_size <= 268435456 and
         all(getattr(before, k) == getattr(after, k) for k in keys), 'INPUT_CHANGED')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': value}


def write(path, raw):
    if not isinstance(raw, bytes):
        raw = (json.dumps(raw, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.fchown(stream.fileno(), 0, 1000); os.fchmod(stream.fileno(), 0o640)
    return {'bytes': len(raw), 'sha256': sha(raw)}


def load(name, expected):
    path = HERE / (name + '.py')
    raw = path.read_bytes(); need(sha(raw) == expected, 'SOURCE_MODULE_CHANGED:' + name)
    module = types.ModuleType(name); module.__file__ = str(path); sys.modules[name] = module
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def main(source_sha):
    need(os.geteuid() == 0 and OUT.parent.resolve() == OUT.parent
         and not os.path.lexists(OUT), 'FRESH_BUILD_ROOT_REQUIRED')
    raw = (HERE / 'SOURCE_PINS.json').read_bytes()
    need(sha(raw) == source_sha, 'SOURCE_MANIFEST_CHANGED')
    sources = json.loads(raw)['files']
    for name, row in sources.items():
        value = (HERE / name).read_bytes()
        need(len(value) == row['bytes'] and sha(value) == row['sha256'], 'SOURCE_CHANGED:' + name)
    os.umask(0o077); OUT.mkdir(mode=0o750); os.chown(OUT, 0, 1000); os.chmod(OUT, 0o750)
    tmp = OUT / 'tmp'; tmp.mkdir(mode=0o700)
    result = {'schema': 'pocket4-editor-lifecycle-host-build-v1', 'state': 'FAILED',
              'commands': [], 'source_manifest_sha256': source_sha,
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'Android_actions': 0, 'UI_inputs': 0, 'APK_packaged': False, 'signed': False,
              'installed': False, 'original_Java_recovered': False,
              'original_signing_key_located': False, 'device_recreation_qualified': False,
              'process_death_recovery_supported': False, 'whole_app_production_ready': False}
    deadline = time.monotonic() + 165
    dependencies = {}; cg = None

    def run(label, argv, timeout=45):
        budget = min(timeout, deadline - time.monotonic()); need(budget > 0, 'BUILD_DEADLINE')
        row = {'label': label, 'argv': argv, 'rc': None, 'joined': False, 'timed_out': False}
        result['commands'].append(row); process = None; began = time.monotonic()
        with (OUT / (label + '.stdout')).open('xb') as stdout, (OUT / (label + '.stderr')).open('xb') as stderr:
            try:
                process = subprocess.Popen(argv, cwd=OUT, stdout=stdout, stderr=stderr,
                    start_new_session=True, close_fds=True,
                    env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                         'TMPDIR': str(tmp)})
                row['rc'] = process.wait(timeout=budget); row['joined'] = True
            except BaseException as exc:
                row['timed_out'] = isinstance(exc, subprocess.TimeoutExpired)
                if process is not None:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                    row['rc'] = process.wait(timeout=5); row['joined'] = True
                raise
            finally:
                stdout.flush(); stderr.flush(); os.fsync(stdout.fileno()); os.fsync(stderr.fileno())
                row['elapsed_seconds'] = time.monotonic() - began
        for ext in ('stdout', 'stderr'):
            p = OUT / (label + '.' + ext); need(p.stat().st_size <= 1048576, 'LOG_BOUND')
            row[ext] = {'bytes': p.stat().st_size, 'sha256': digest(p)}
        if row['rc'] != 0:
            result['failed_command_stderr'] = (OUT / (label + '.stderr')).read_text(errors='replace')[-32768:]
        need(row['rc'] == 0, 'COMMAND_FAILED:' + label)
        return (OUT / (label + '.stdout')).read_text()

    try:
        rows = [line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')]
        need(len(rows) == 1 and rows[0].endswith('/pocket4-editor-recovery-build-r12-01.service'), 'OWN_BUILD_CGROUP_REQUIRED')
        cg = Path('/sys/fs/cgroup') / rows[0].lstrip('/')
        result['limits'] = {name: (cg / name).read_text().strip() for name in LIMITS}
        result['affinity'] = sorted(os.sched_getaffinity(0))
        need(result['limits'] == LIMITS and result['affinity'] == [20], 'RESOURCE_LIMITS')
        parent_pin = pin(PARENT_APK); need(parent_pin['sha256'] == PARENT_APK_SHA, 'PARENT_APK_CHANGED')
        with zipfile.ZipFile(PARENT_APK) as archive:
            need(len(archive.namelist()) == len(set(archive.namelist())) and archive.testzip() is None, 'PARENT_ZIP_INVALID')
            need(sha(archive.read('classes.dex')) == PARENT_DEX_SHA, 'PARENT_DEX_CHANGED')
            need([n for n in archive.namelist() if re.fullmatch(r'classes\d*\.dex', n)] == ['classes.dex'], 'PARENT_SINGLE_DEX_REQUIRED')
        result['original_apk'] = parent_pin; result['original_dex_sha256'] = PARENT_DEX_SHA
        expected = json.loads((HERE / 'dependencies.json').read_text())
        for name, row in expected['files'].items():
            dependencies[name] = pin(row['path'])
            need(dependencies[name] == row, 'TOOL_PIN_CHANGED:' + name)
        result['dependencies_before'] = dependencies
        patch = load('patch_installed', sources['patch_installed.py']['sha256'])
        load('smali_ir_base', sources['smali_ir_base.py']['sha256'])
        ir = load('smali_roundtrip', sources['smali_roundtrip.py']['sha256'])
        patch.SOURCE = HERE / 'preimage'
        patch.build(OUT / 'candidate-smali')
        patch_report = json.loads((OUT / 'SOURCE_PATCH_REVIEW.json').read_text())
        result['source_patch'] = patch_report
        classes = OUT / 'classes'; classes.mkdir()
        tests = OUT / 'test-classes'; tests.mkdir()
        java = dependencies['java']['path']; javac = dependencies['javac']['path']
        sdk = dependencies['android_jar']['path']
        vm = ['-Xmx256m', '-XX:ActiveProcessorCount=1', '-XX:+UseSerialGC', '-XX:-UsePerfData',
              '-Djava.io.tmpdir=' + str(tmp), '-Duser.home=' + str(tmp)]
        javacvm = ['-J' + value for value in vm]
        run('javac-sdk31', [javac, *javacvm, '-encoding', 'UTF-8', '-g', '-source', '8', '-target', '8',
            '-bootclasspath', dependencies['core_lambda_stubs']['path'] + ':' + sdk,
            '-d', str(classes), *[str(p) for p in sorted((HERE / 'candidate/src').rglob('*.java'))]])
        run('javac-host-tests', [javac, *javacvm, '-encoding', 'UTF-8', '-source', '8', '-target', '8',
            '-cp', str(classes), '-d', str(tests), *[str(p) for p in sorted((HERE / 'tests').rglob('*.java'))]])
        result['host_tests'] = {}
        for name in ('SessionOwnerTest', 'RetainedEditorStateTest'):
            result['host_tests'][name] = run(name, [java, *vm, '-cp', str(tests) + ':' + str(classes),
                'org.droidloom.qa.editorcontract.' + name])
        result['host_test_boundary'] = 'Production ownership/snapshot classes; test-only AtomicFile/JSONArray identity stubs, no Android lifecycle or IO simulation.'
        program = OUT / 'new-program.jar'
        compiled = []
        with zipfile.ZipFile(program, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(classes.rglob('*.class')):
                name = path.relative_to(classes).as_posix(); compiled.append(name)
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
        result['compiled_Java_classes'] = compiled
        dexdir = OUT / 'new-dex'; dexdir.mkdir()
        run('d8', [java, *vm, '-cp', dependencies['r8']['path'], 'com.android.tools.r8.D8',
            '--release', '--min-api', '26', '--lib', sdk, '--output', str(dexdir), str(program)])
        need([p.name for p in dexdir.iterdir()] == ['classes.dex'], 'ONE_HELPER_DEX_REQUIRED')
        j25 = dependencies['jre/bin/java']['path']
        def cp(extra):
            return ':'.join(dependencies['jars/' + n]['path'] for n in
                            ['antlr3-runtime', 'dexlib2', 'guava', 'jcommander', 'smali-util', extra])
        run('disassemble-helpers', [j25, *vm, '-cp', cp('baksmali'), 'org.jf.baksmali.Main',
            'disassemble', '--api', '35', '--jobs', '1', '--output', str(OUT / 'helper-smali'), str(dexdir / 'classes.dex')])
        helper_classes = []
        for path in sorted((OUT / 'helper-smali').rglob('*.smali')):
            name = path.relative_to(OUT / 'helper-smali').as_posix()
            need(name.startswith('org/droidloom/qa/editorcontract/') and not (OUT / 'candidate-smali' / name).exists(), 'HELPER_CLASS_COLLISION')
            helper_classes.append(name); shutil.copyfile(path, OUT / 'candidate-smali' / name)
        need(any(n.endswith('/RetainedEditorState.smali') for n in helper_classes)
             and any(n.endswith('/SessionOwner.smali') for n in helper_classes), 'REQUIRED_HELPER_CLASSES')
        result['new_dex_classes'] = helper_classes
        run('assemble-complete', [j25, *vm, '-cp', cp('smali'), 'org.jf.smali.Main', 'assemble',
            '--api', '35', '--jobs', '1', '--output', str(OUT / 'classes.dex'), str(OUT / 'candidate-smali')])
        run('roundtrip-complete', [j25, *vm, '-cp', cp('baksmali'), 'org.jf.baksmali.Main', 'disassemble',
            '--api', '35', '--jobs', '1', '--output', str(OUT / 'roundtrip'), str(OUT / 'classes.dex')])
        names = sorted(p.relative_to(OUT / 'candidate-smali').as_posix() for p in (OUT / 'candidate-smali').rglob('*.smali'))
        roundtrip_names = sorted(p.relative_to(OUT / 'roundtrip').as_posix() for p in (OUT / 'roundtrip').rglob('*.smali'))
        need(names == roundtrip_names, 'COMPLETE_CLASS_SET_CHANGED')
        proof = []; methods = 0
        for name in names:
            candidate = ir.class_ir((OUT / 'candidate-smali' / name).read_text())
            roundtrip = ir.class_ir((OUT / 'roundtrip' / name).read_text())
            if candidate != roundtrip:
                write(OUT / 'ir-mismatch.json', {'class': name, 'candidate': candidate, 'roundtrip': roundtrip})
                raise RuntimeError('COMPLETE_ROUNDTRIP_IR_CHANGED:' + name)
            methods += len(candidate['methods'])
            proof.append({'class': name, 'candidate_ir_sha256': ir.ir_sha256(candidate),
                          'roundtrip_equal': True, 'method_count': len(candidate['methods'])})
        result['class_ir_proof'] = write(OUT / 'class-ir-proof.json', proof)
        result['complete_class_count'] = len(names); result['complete_method_count'] = methods
        result['complete_roundtrip_equal'] = True
        result['candidate_dex'] = pin(OUT / 'classes.dex')
        result['retained_original_method_bodies'] = len(patch_report['original_methods_wrapped_with_verbatim_body'])
        result['state'] = 'SDK_COMPILED_COMPLETE_DEX_ASSEMBLED_NOT_SIGNED_OR_INSTALLED'
    except BaseException as exc:
        result['error'] = type(exc).__name__ + ':' + str(exc)
    finally:
        try:
            after = {name: pin(row['path']) for name, row in dependencies.items()}
            need(after == dependencies, 'TOOLS_CHANGED_AFTER_BUILD')
            for name, row in sources.items():
                need(digest(HERE / name) == row['sha256'], 'SOURCE_CHANGED_AFTER:' + name)
            need(digest(PARENT_APK) == PARENT_APK_SHA, 'PARENT_CHANGED_AFTER')
            result['dependencies_after_same'] = True; result['source_after_same'] = True
        except BaseException as exc:
            result['state'] = 'FAILED'; result['postcheck_error'] = type(exc).__name__ + ':' + str(exc)
        if cg is not None:
            result['resource_usage'] = {n: (cg / n).read_text().strip() for n in ('memory.peak', 'memory.events', 'cpu.stat')}
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        raw = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
        meta = write(OUT / 'result.json', raw); compressed = write(OUT / 'result.json.gz', gzip.compress(raw, mtime=0))
        fd = os.open(OUT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    print(json.dumps({'state': result['state'], 'error': result.get('error'), 'result': meta,
        'result_path': str(OUT / 'result.json'), 'result_gzip': compressed,
        'classes': result.get('complete_class_count'), 'candidate_dex': result.get('candidate_dex'),
        'Android_actions': 0, 'signed': False, 'installed': False}))
    return 0 if result['state'] == 'SDK_COMPILED_COMPLETE_DEX_ASSEMBLED_NOT_SIGNED_OR_INSTALLED' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--execute', action='store_true'); parser.add_argument('--source-sha')
    args = parser.parse_args()
    if not args.execute:
        print('INERT: real SDK compile/DEX assembly only, no signing or Android operations')
        raise SystemExit(0)
    raise SystemExit(main(args.source_sha))
