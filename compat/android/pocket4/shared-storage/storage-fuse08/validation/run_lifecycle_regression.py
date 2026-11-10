#!/usr/bin/env python3
"""Compile verbatim production Java methods; substitute only Android/native boundaries.

This is a host unit regression, not a framework build, binder/kernel/FUSE test,
or proof of the installed device cause. Original methods are extracted from
complete, Git-blob-verified AOSP files and their byte ranges are recorded.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
JAVA = '/usr/lib/jvm/java-17-openjdk-amd64/bin/java'
SSC = 'frameworks/base/services/core/java/com/android/server/storage/StorageSessionController.java'
SUC = 'frameworks/base/services/core/java/com/android/server/storage/StorageUserConnection.java'
ESS = 'frameworks/base/core/java/android/service/storage/ExternalStorageService.java'
IMP = 'packages/providers/MediaProvider/src/com/android/providers/media/fuse/ExternalStorageServiceImpl.java'
FUS = 'packages/providers/MediaProvider/src/com/android/providers/media/fuse/FuseDaemon.java'
CASES = ['waits_for_exit', 'rapid_remount', 'duplicate_start', 'remove_without_wait',
         'only_target_session', 'unsupported_and_reset', 'missing_connection',
         'error_restores_identity', 'clone_parent_connection']
NEGATIVE = {'waits_for_exit': 'END_SESSION_NOT_SENT', 'rapid_remount': 'NEW_DEVICE_FD_NOT_CONSUMED'}


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def extract(text, signature):
    """Return the exact declaration/body, ignoring braces in comments/strings."""
    assert text.count(signature) == 1, signature
    at = text.index(signature)
    start = text.rfind('\n', 0, at) + 1
    opening = text.index('{', at)
    level, state, i = 0, 'code', opening
    while i < len(text):
        c, pair = text[i], text[i:i+2]
        if state == 'line':
            if c == '\n': state = 'code'
        elif state == 'block':
            if pair == '*/': state, i = 'code', i + 1
        elif state in ('"', "'"):
            if c == '\\': i += 1
            elif c == state: state = 'code'
        elif pair == '//': state, i = 'line', i + 1
        elif pair == '/*': state, i = 'block', i + 1
        elif c in ('"', "'"): state = c
        elif c == '{': level += 1
        elif c == '}':
            level -= 1
            if level == 0:
                return text[start:i+1] + '\n', text.count('\n', 0, start) + 1
        i += 1
    raise AssertionError('unterminated method: ' + signature)


def render(variant, out):
    sources = {p: (ROOT / ('candidate' if variant == 'candidate' and p == SSC else 'upstream') / p).read_text()
               for p in (SSC, SUC, ESS, IMP, FUS)}
    records = []
    def methods(path, signatures):
        parts = []
        for sig in signatures:
            body, first = extract(sources[path], sig)
            records.append({'path': path, 'signature': sig, 'first_line': first,
                            'sha256': hashlib.sha256(body.encode()).hexdigest(), 'bytes': len(body.encode())})
            parts.append(body)
        return '\n'.join(parts)
    blocks = {
        'CONTROLLER': methods(SSC, ['public int getConnectionUserIdForVolume(', 'public void onVolumeMount(',
            'public StorageUserConnection onVolumeRemove(', 'public void onVolumeUnmount(',
            'public static boolean isEmulatedOrPublic(', 'private static boolean isSupportedVolume(',
            'private boolean shouldHandle(']),
        'CONNECTION': methods(SUC, ['public void startSession(String sessionId,', 'public Session removeSession(',
            'public void removeSessionAndWait(', 'private static final class Session {',
            'interface AsyncStorageServiceCall {']),
        'ACTIVE': methods(SUC, ['private void waitForAsyncVoid(', 'private <T> T waitForAsync(',
            'public void startSession(Session session,', 'public void endSession(Session session)',
            'private void setResult(']),
        'WRAPPER': methods(ESS, ['public void startSession(String sessionId,',
            'public void endSession(String sessionId,', 'private void sendResult(']),
        'SERVICE': methods(IMP, ['public void onStartSession(', 'public void onEndSession(',
            'public FuseDaemon onExitSession(', 'public static FuseDaemon getFuseDaemon(']),
        'DAEMON': methods(FUS, ['public FuseDaemon(', 'public void run()', 'public synchronized void start()',
            'private void initializeDeviceId()', 'private void waitForStart()', 'public void waitForExit()']),
    }
    template = (ROOT / 'validation/LifecycleHarness.java.in').read_text()
    for key, value in blocks.items():
        assert template.count('/*__' + key + '__*/') == 1
        template = template.replace('/*__' + key + '__*/', value)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'LifecycleHarness.java').write_text(template)
    stub = out / 'android/os/ParcelableException.java'
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text('package android.os; public class ParcelableException extends RuntimeException {\n'
                    ' public ParcelableException(Throwable cause) { super(cause); }\n}\n')
    (out / 'extracted-methods.json').write_text(json.dumps(records, indent=2) + '\n')
    return [str(stub), str(out / 'LifecycleHarness.java')]


def run(argv, prefix):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40)
    prefix.with_suffix('.stdout').write_bytes(result.stdout)
    prefix.with_suffix('.stderr').write_bytes(result.stderr)
    return {'argv': argv, 'rc': result.returncode,
            'stdout': result.stdout.decode('utf-8'), 'stderr': result.stderr.decode('utf-8')}


def main():
    for entry in json.loads((ROOT / 'upstream-sources.json').read_text()):
        data = (ROOT.parent / entry['path']).read_bytes()
        assert blob(data) == entry['git_blob'], entry['path']
        assert hashlib.sha256(data).hexdigest() == entry['sha256'], entry['path']
    results = {'kind': 'verbatim-production-method-host-regression', 'device_actions': 0,
               'framework_or_kernel_integration': False, 'variants': {}}
    for variant in ('upstream', 'candidate'):
        out = ROOT / 'validation/results' / variant
        files = render(variant, out)
        compile_result = run([JAVA, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-encoding', 'UTF-8',
                              '-d', str(out / 'classes'), *files], out / 'compile')
        assert compile_result['rc'] == 0, compile_result
        runs = {}
        for case in CASES:
            result = run([JAVA, '-cp', str(out / 'classes'), 'LifecycleHarness', case], out / case)
            expected_failure = variant == 'upstream' and case in NEGATIVE
            expected_rc = 2 if expected_failure else 0
            result['expected_rc'] = expected_rc
            result['expected_result'] = result['rc'] == expected_rc
            if expected_failure:
                result['expected_result'] &= NEGATIVE[case] in result['stderr']
            runs[case] = result
            print(variant, case, 'rc=' + str(result['rc']), 'expected=' + str(expected_rc), flush=True)
        results['variants'][variant] = {'compile': compile_result, 'cases': runs}
    results['passed'] = all(r['expected_result'] for v in results['variants'].values() for r in v['cases'].values())
    (ROOT / 'validation/results/result.json').write_text(json.dumps(results, indent=2) + '\n')
    assert results['passed'], 'regression mismatch; inspect retained results'


if __name__ == '__main__':
    main()
