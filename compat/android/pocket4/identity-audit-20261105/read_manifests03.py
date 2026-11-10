#!/usr/bin/python3 -I
"""Fill nine manifest/readback gaps without rerunning any APK signature verifier."""
from pathlib import Path
import argparse, base64, datetime, gzip, hashlib, json, os, stat, time, types, zipfile

ROOT = Path('/home/alex/work/pocket4-app-identities-20261105-r12-01')
OUT = ROOT / 'manifest-03'
ORIGINAL_SHA = '750cd5e2b690d8c7a881c88bb067e18ea7c3ad8cd48cca1470314f789c628a45'
COLLECTOR_SHA = '4555d4d5fad1b1cf1fe47d599f5b4c13c6259106958b525aa58bbeecb7c4c869'
TX_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
UNIT = 'pocket4-app-manifests03-r12.service'
SELECTED = ['com.android.contacts', 'com.android.deskclock', 'com.android.dialer',
            'com.android.messaging', 'com.android.quicksearchbox', 'com.android.settings',
            'com.android.threadnetwork.demoapp', 'local.pocket4.fixture', 'org.chromium.webview_shell']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def module(path, expected, name):
    raw = path.read_bytes(); need(sha(raw) == expected, 'SOURCE_HASH_CHANGED')
    m = types.ModuleType(name); m.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), m.__dict__)
    return m


def resources():
    need(Path('/proc/self/cgroup').read_text().strip() == '0::/system.slice/' + UNIT, 'OWN_UNIT_REQUIRED')
    root = Path('/sys/fs/cgroup/system.slice') / UNIT
    values = {k: (root / k).read_text().strip() for k in ['memory.max', 'memory.swap.max', 'cpu.max', 'pids.max']}
    need(values == {'memory.max': '268435456', 'memory.swap.max': '0', 'cpu.max': '100000 100000', 'pids.max': '32'}
         and os.sched_getaffinity(0) == {20}, 'OWN_RESOURCE_LIMITS')
    return {'limits': values, 'memory_peak_bytes': int((root / 'memory.peak').read_text()),
            'memory_events': {k: int(v) for k, v in (x.split() for x in (root / 'memory.events').read_text().splitlines())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--read-once', action='store_true'); parser.add_argument('--source-sha256')
    args = parser.parse_args()
    if not args.read_once:
        print(json.dumps({'state': 'INERT', 'selected_packages': len(SELECTED), 'signature_verifier_runs': 0, 'UI_actions': 0})); return
    need(os.getuid() == os.geteuid() == 0 and sha(Path(__file__).read_bytes()) == args.source_sha256, 'OWN_SOURCE_AND_ROOT_REQUIRED')
    c = module(ROOT / 'collect_identities01.py', COLLECTOR_SHA, 'frozen_identity_helpers')
    c.DEADLINE = time.monotonic() + 270
    tx = module(c.TX, TX_SHA, 'held_manifest_session')
    raw = tx.read_regular(ROOT / 'result-01/result.json', ORIGINAL_SHA)
    original = json.loads(raw); known = {r['package']: r for r in original['apps']}
    need(all(p in known and not known[p]['identity_complete'] and len(known[p]['apks']) == 1 for p in SELECTED), 'SELECTED_ORIGINAL_GAPS_DIFFER')
    os.umask(0o077); OUT.mkdir(mode=0o750); os.chown(OUT, 0, 1000); os.chmod(OUT, 0o750)
    result = {'state': 'INCOMPLETE', 'source_sha256': args.source_sha256, 'original_result_sha256': ORIGINAL_SHA,
              'original_exit2_preserved': True, 'started_utc': c.utc(), 'UI_actions': 0,
              'signature_verifier_runs': 0, 'installs': 0, 'private_or_account_content_read': False,
              'packages': {}, 'whole_app_production_ready': False}
    try:
        result['resources_before'] = resources()
        # This new, selected technical export was intended to be group-readable;
        # its exporter omitted fchmod after the restrictive umask. No original
        # private journal or Android path receives a permission change.
        export = ROOT / 'readback-02/result.json.gz'
        fd = os.open(export, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            p = c.pin_fd(fd, 65536)
            need(p['bytes'] == 10652 and p['sha256'] == '66a76425a80f0d5f3114035a67119cf101345a0919c4d849a4a71f8cfffc1994'
                 and p['stat']['st_uid'] == 0 and p['stat']['st_gid'] == 1000 and p['stat']['st_nlink'] == 1,
                 'EXACT_NEW_TECHNICAL_EXPORT_REQUIRED')
            before_mode = stat.S_IMODE(p['stat']['st_mode']); need(before_mode in (0o600, 0o640), 'EXPORT_MODE_UNEXPECTED')
            os.fchmod(fd, 0o640)
            need(c.pin_fd(fd, 65536)['sha256'] == p['sha256'], 'EXPORT_BYTES_CHANGED')
            result['owned_export_permission_correction'] = {'sha256': p['sha256'], 'before_mode': oct(before_mode), 'after_mode': '0o640'}
        finally:
            os.close(fd)
        with tx.CameraSession(OUT / 'private-commands') as session:
            result['guard_before'] = session.guard()
            need(session.epoch_sha256 == original['guard_after']['epoch_sha256'], 'ORIGINAL_MAIN_EPOCH_DIFFERS')
            for package in SELECTED:
                c.budget(20); session.guard()
                row = {'started_utc': c.utc()}; result['packages'][package] = row
                path_args = ['/system/bin/pm', 'path', '--user', '0', package]
                paths = c.paths(session.android(path_args)); need(len(paths) == 1, 'ONE_PRIOR_BASE_APK_REQUIRED')
                identity = c.active_identity(session.android(['/system/bin/dumpsys', 'package', package]), package)
                prior = known[package]['identity']
                need(all(identity[k] == prior[k] for k in ['uid', 'version_code', 'min_sdk', 'target_sdk']), 'PRIOR_PM_IDENTITY_CHANGED')
                row['identity_before'] = identity
                fd = session.target.open_root(paths[0], os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    before = c.pin_fd(fd)
                    expected = known[package]['apks'][0]
                    need(before['sha256'] == expected['sha256'] and before['bytes'] == expected['bytes'], 'SIGNATURE_VERIFIED_APK_CONTENT_CHANGED')
                    row['apk_before'] = before; row['guest_path'] = paths[0]
                    with os.fdopen(os.dup(fd), 'rb') as stream, zipfile.ZipFile(stream) as archive:
                        infos = archive.infolist(); names = [i.filename for i in infos]
                        need(1 <= len(names) <= 100000 and len(names) == len(set(names)), 'ZIP_ENTRY_BOUND_OR_DUPLICATE')
                        info = archive.getinfo('AndroidManifest.xml')
                        need(0 < info.file_size <= 2 * 1024 * 1024, 'MANIFEST_SIZE_BOUND')
                        manifest = archive.read(info)
                        need(len(manifest) == info.file_size, 'MANIFEST_LENGTH')
                        row['manifest'] = {'bytes': len(manifest), 'sha256': sha(manifest),
                                           'base64': base64.b64encode(manifest).decode('ascii')}
                        libs = [n for n in names if n.startswith('lib/') and n.endswith('.so') and len(n.split('/')) == 3]
                        row['embedded_native_abis'] = sorted({n.split('/')[1] for n in libs})
                        row['embedded_native_library_count'] = len(libs)
                    after = c.pin_fd(fd); need(after == before, 'APK_CHANGED_DURING_MANIFEST_READ')
                    need(c.paths(session.android(path_args)) == paths, 'CURRENT_APK_PATH_CHANGED')
                    final = c.active_identity(session.android(['/system/bin/dumpsys', 'package', package]), package)
                    need(c.immutable_identity(final) == c.immutable_identity(identity), 'PM_METADATA_CHANGED')
                    fresh = session.target.open_root(paths[0], os.O_RDONLY | os.O_NOFOLLOW)
                    try:
                        need(c.meta(fresh) == c.meta(fd) == before['stat'], 'INSTALLED_PATH_NO_LONGER_HELD_FILE')
                    finally:
                        os.close(fresh)
                    row['apk_after'] = after; row['identity_after'] = final
                    row['same_signature_verified_content'] = True
                finally:
                    os.close(fd)
                row['finished_utc'] = c.utc()
            session.caller_status('manifest-caller-after'); result['guard_after'] = session.guard()
        result['state'] = 'NINE_EXACT_APK_MANIFESTS_AND_CURRENT_READBACK_RETAINED'
    except BaseException as exc:
        result['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        try:
            result['resources_after'] = resources()
        except Exception as exc:
            result['resource_error'] = type(exc).__name__; result['state'] = 'INCOMPLETE'
        result['finished_utc'] = c.utc()
        receipt = tx.write_new(OUT / 'result.json', result, alex_readable=True)
        encoded = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
        need(sha(encoded) == receipt['sha256'], 'RESULT_SERIALIZATION_CHANGED')
        packed = tx.write_new(OUT / 'result.json.gz', gzip.compress(encoded, mtime=0), alex_readable=True)
    print(json.dumps({'state': result['state'], 'result': receipt, 'compressed_result': packed,
                      'signature_verifier_runs': 0, 'UI_actions': 0}))
    raise SystemExit(0 if result['state'] == 'NINE_EXACT_APK_MANIFESTS_AND_CURRENT_READBACK_RETAINED' else 2)


if __name__ == '__main__':
    main()
