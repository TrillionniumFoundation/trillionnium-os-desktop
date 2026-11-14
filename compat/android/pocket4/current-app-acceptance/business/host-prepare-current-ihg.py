"""Prepare the current official IHG identity for the existing app acceptance source.

This creates an isolated successor and exercises its real parsers on host data.
It never installs an APK, starts Android, changes the selected preparation, or
claims a runtime result. Run as root on the configured pocket4 host.
"""
from pathlib import Path
import ast
import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import types

OUT = Path(__file__).resolve().parent
SOURCE = Path('/home/alex/work/pocket4-android-final/qualification/business-app-runtime-inputs-20261108-8b88-r2/preparation.json')
SOURCE_SHA = '84eb5b4270846c65c199274e25309f8e7402332b21b53cbe3e8cfe445c30057f'
COVERAGE = Path('/home/alex/work/p4-app-release-inventory-20261113-e2a3-r1/APP-COVERAGE-r4.json')
COVERAGE_SHA = '922cdfbfa445af6bdd96284be62cec2eb51e154dbd698d988f818fb70023bf36'
STATIC = Path('/home/alex/work/p4-Play-official-collected-static-Hyatt-National-IHG-01a1ca08-r2/RESULT.json')
STATIC_SHA = '626030207071dc356760ef86b9899cab90c754270482069d9d9e1d4d5d61a340'
PACKAGE = 'com.ihg.apps.android'


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def f9(s):
    return [getattr(s, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
        'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')]


def read(path, expected=None, maximum=128 * 1024 * 1024):
    path = Path(path)
    need(path.is_absolute() and path.resolve(strict=True) == path, 'canonical path required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             0 < before.st_size <= maximum, 'bounded single regular file required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(maximum + 1)
        need(len(raw) == before.st_size and
             f9(before) == f9(os.fstat(fd)) == f9(path.lstat()), 'input changed during read')
        need(expected is None or sha(raw) == expected, 'input digest changed: ' + str(path))
        return raw, {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}
    finally:
        os.close(fd)


def write(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def module(raw, path):
    value = types.ModuleType(Path(path).stem)
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def command(label, argv):
    completed = subprocess.run(argv, capture_output=True, timeout=45)
    stdout = write(OUT / (label + '.stdout'), completed.stdout)
    stderr = write(OUT / (label + '.stderr'), completed.stderr)
    result = {'argv': argv, 'returncode': completed.returncode, 'stdout': stdout,
              'stderr': stderr, 'Android_actions': 0}
    write(OUT / (label + '.json'), result)
    need(completed.returncode == 0, label + ' failed')
    return completed.stdout.decode('utf-8', 'strict')


def main():
    need(os.getuid() == os.geteuid() == 0, 'root file reader required')
    os.umask(0o077)
    raw, source_ref = read(SOURCE, SOURCE_SHA)
    original = json.loads(raw)
    coverage_raw, coverage_ref = read(COVERAGE, COVERAGE_SHA)
    coverage = json.loads(coverage_raw)
    static_raw, static_ref = read(STATIC, STATIC_SHA)
    static_result = json.loads(static_raw)
    selected = [r for r in coverage['rows'] if r['package'] == PACKAGE]
    need(len(selected) == 1 and len(coverage['rows']) == coverage['selected_count'] == 42,
         'exact current selection required')
    selected = selected[0]
    need(selected['status'] == 'OFFICIAL_PLAY_COMPLETE_STATIC_QUALIFIED' and
         selected['version_code'] == 50023496 and selected['version_name'] == '5.110.0',
         'selected official current IHG identity required')
    need(len(selected['files']) == 1 and selected['splits'] == [None], 'one current base APK required')
    need(selected['signers'] == selected['recorded_installed_identity']['signers'] and
         selected['recorded_installed_identity']['uid'] == 10137, 'recorded signer/UID continuity required')
    apk = selected['files'][0]
    apk_raw, apk_ref = read(apk['path'], apk['sha256'])
    need(len(apk_raw) == apk['bytes'] == 47668450, 'complete current APK bytes required')
    del apk_raw
    static_apps = [r for r in static_result['apps'] if r['package'] == PACKAGE]
    need(len(static_apps) == 1 and len(static_apps[0]['APK_results']) == 1, 'exact official static record required')
    static_apk = static_apps[0]['APK_results'][0]
    need(static_apk['file']['sha256'] == apk_ref['sha256'] and
         static_apk['identity']['versionCode'] == selected['version_code'] and
         static_apk['signature']['effective_signer_cert_SHA256'] == selected['signers'],
         'independent actual static result must match selected payload')
    originals = {}
    for row in original['files'] + original['origins']:
        value, ref = read(row['path'], row['sha256'])
        need(ref['bytes'] == row['bytes'], 'complete source input required')
        if row in original['files']:
            name = Path(row['path']).name
            need(name not in originals, 'distinct source file names required')
            originals[name] = value
    need(len(originals) == 31, 'original complete 31-source packet required')
    source_dir = OUT / 'source'
    source_dir.mkdir(mode=0o700)
    transformations = {
        'app_profiles.py': [('50023219', '50023496'), ('44999052', '47668450'),
            ('c12bb3bae3514c94caaca0a4ef6e8f1ad4491cbce57fd2a15be48b83b4c85b90', apk_ref['sha256'])],
        'ihg_artifacts.py': [('VERSION = 50023219', 'VERSION = 50023496')],
    }
    successor_files = []
    changed = []
    for name, value in originals.items():
        text = value.decode('utf-8')
        for before, after in transformations.get(name, []):
            need(text.count(before) == 1 and after not in text, 'exact unique source edit required')
            text = text.replace(before, after, 1)
        rewritten = text.encode()
        reverse = text
        for before, after in reversed(transformations.get(name, [])):
            reverse = reverse.replace(after, before, 1)
        need(reverse.encode() == value, 'undeclared source change')
        ast.parse(rewritten, filename=name)
        successor_files.append(write(source_dir / name, rewritten))
        if rewritten != value:
            changed.append(name)
    need(changed == ['app_profiles.py', 'ihg_artifacts.py'], 'only two stale IHG identity sources may change')
    badging = command('actual-current-badging', ['/usr/bin/aapt2', 'dump', 'badging', apk['path']])
    need("package: name='com.ihg.apps.android' versionCode='50023496' versionName='5.110.0'" in badging and
         "launchable-activity: name='com.ihg.apps.android.activity.MainActivity'" in badging,
         'actual current manifest and unchanged launcher required')
    signature = command('actual-current-api37-signature', ['/usr/bin/apksigner', 'verify',
        '--min-sdk-version', '37', '--max-sdk-version', '37', '--verbose', '--print-certs', apk['path']])
    certs = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([a-fA-F0-9]{64})$', signature, re.M)
    need([x.lower() for x in certs] == selected['signers'] and
         'Verified using v3 scheme (APK Signature Scheme v3): true' in signature,
         'fresh API37 actual signature and same signer required')
    read(apk['path'], apk_ref['sha256'])
    rows = []
    def yes(name, fn):
        need(fn() is not False, name)
        rows.append({'name': name, 'passed': True})
    def no(name, fn):
        try:
            fn()
        except RuntimeError:
            rows.append({'name': name, 'passed': True})
            return
        raise RuntimeError('negative accepted: ' + name)
    common = module(originals['app_common.py'], source_dir / 'app_common.py')
    profiles = module((source_dir / 'app_profiles.py').read_bytes(), source_dir / 'app_profiles.py')
    old_profiles = module(originals['app_profiles.py'], SOURCE.parent / 'source/app_profiles.py')
    artifacts = module((source_dir / 'ihg_artifacts.py').read_bytes(), source_dir / 'ihg_artifacts.py')
    current_raw = b'package:com.ihg.apps.android versionCode:50023496 uid:10137\n'
    old_raw = b'package:com.ihg.apps.android versionCode:50023219 uid:10137\n'
    yes('actual_current_metadata_accepted', lambda: common.package_metadata(current_raw, profiles.IHG))
    no('old_source_rejects_current_metadata_reproduces_blocker', lambda: common.package_metadata(current_raw, old_profiles.IHG))
    no('successor_rejects_old_metadata', lambda: common.package_metadata(old_raw, profiles.IHG))
    no('successor_rejects_wrong_uid', lambda: common.package_metadata(current_raw.replace(b'10137', b'10138'), profiles.IHG))
    candidate_artifacts = [{**{k: apk_ref[k] for k in ('bytes', 'sha256')},
        'held_file': {'fixture': 'host-only'}, 'stat_file': {'fixture': 'host-only', 'ctime_ns': 0}}]
    yes('actual_current_digest_and_size_accepted', lambda: common.validate_artifacts(candidate_artifacts, profiles.IHG))
    no('old_source_rejects_current_digest_reproduces_blocker', lambda: common.validate_artifacts(candidate_artifacts, old_profiles.IHG))
    altered = copy.deepcopy(candidate_artifacts); altered[0]['sha256'] = '0' * 64
    no('successor_rejects_modified_apk_digest', lambda: common.validate_artifacts(altered, profiles.IHG))
    altered = copy.deepcopy(candidate_artifacts); altered[0]['bytes'] += 1
    no('successor_rejects_wrong_apk_size', lambda: common.validate_artifacts(altered, profiles.IHG))
    no('successor_rejects_missing_apk', lambda: common.validate_artifacts([], profiles.IHG))
    no('successor_rejects_extra_apk', lambda: common.validate_artifacts(candidate_artifacts * 2, profiles.IHG))
    target = {'package': PACKAGE, 'uid': 10137, 'user': 0, 'version_code': 50023496}
    yes('artifact_guard_accepts_current_target', lambda: artifacts.ArtifactSet(None, {'target': target}, None))
    no('artifact_guard_rejects_old_target', lambda: artifacts.ArtifactSet(None, {'target': {**target, 'version_code': 50023219}}, None))
    yes('existing_clock_helper_limits_unchanged', lambda: all(getattr(profiles, k) == getattr(old_profiles, k)
        for k in ('CLOCK', 'CLOCK_HELPER', 'CLOCK_LIMITS', 'IHG_LIMITS')))
    yes('existing_ihg_non_version_identity_unchanged', lambda: all(profiles.IHG[k] == old_profiles.IHG[k]
        for k in profiles.IHG if k not in ('version_code', 'apks')))
    successor = copy.deepcopy(original)
    successor['files'] = successor_files
    successor['origins'] += [source_ref, coverage_ref, static_ref]
    successor['source_graph_generation'] = '20261114-e6ac-ihg-current-r1'
    successor['source_dependency_scope'] += ' IHG target identity updated from exact current official payload; all runtime gates retained.'
    preparation = write(OUT / 'preparation.json', successor)
    planner = module(originals['app_plan.py'], source_dir / 'app_plan.py')
    yes('real_preparation_validator_reads_complete_successor', lambda: planner.preparation(common, preparation))
    for path, digest in [(SOURCE, SOURCE_SHA), (COVERAGE, COVERAGE_SHA), (STATIC, STATIC_SHA)]:
        read(path, digest)
    for row in original['files'] + original['origins']:
        read(row['path'], row['sha256'])
    result = {'schema': 'pocket4-current-ihg-identity-source-repair-v1',
        'state': 'CURRENT_IHG_IDENTITY_SOURCE_AND_HOST_CONTROLS_PASSED_RUNTIME_PENDING',
        'source_preparation': source_ref, 'successor_preparation': preparation,
        'selection_evidence': coverage_ref, 'official_static_evidence': static_ref,
        'current_apk': apk_ref, 'current_version_code': 50023496,
        'source_files': len(successor_files), 'byte_identical_source_files': 29,
        'changed_source_files': changed, 'exact_literal_changes': 4,
        'host_controls': rows, 'host_controls_passed': len(rows),
        'synthetic_guard_controls_not_runtime_evidence': True,
        'fresh_actual_manifest_and_api37_signature_checked': True,
        'original_source_and_selection_unchanged': True, 'canonical_selection_changed': False,
        'Android_actions': 0, 'apps_installed': 0, 'runtime_accepted': 0,
        'runtime_qualified': False, 'production_ready': False}
    result_ref = write(OUT / 'RESULT.json', result)
    print(json.dumps({'result': result_ref, 'successor_preparation': preparation,
        'host_controls_passed': len(rows), 'runtime_qualified': False}, sort_keys=True))


if __name__ == '__main__':
    main()

