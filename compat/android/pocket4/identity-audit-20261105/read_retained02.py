#!/usr/bin/python3 -I
"""Export only retained identity-audit gaps; no Android, verifier, or UI command."""
from pathlib import Path
import argparse, datetime, gzip, hashlib, json, os, re, stat, time

ROOT = Path('/home/alex/work/pocket4-app-identities-20261105-r12-01')
BASE = ROOT / 'result-01'
OUT = ROOT / 'readback-02'
EXPECTED = '750cd5e2b690d8c7a881c88bb067e18ea7c3ad8cd48cca1470314f789c628a45'
DEADLINE = 0


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, limit=1048576):
    need(time.monotonic() < DEADLINE, 'READ_DEADLINE')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        a = os.fstat(fd)
        need(stat.S_ISREG(a.st_mode) and a.st_nlink == 1 and a.st_size <= limit, 'READ_FILE_BOUND')
        with os.fdopen(os.dup(fd), 'rb') as source:
            raw = source.read(limit + 1)
        b = os.fstat(fd)
        need(len(raw) == a.st_size and (a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns, a.st_ctime_ns) ==
             (b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns, b.st_ctime_ns), 'INPUT_CHANGED')
        return raw
    finally:
        os.close(fd)


def write(name, raw):
    fd = os.open(OUT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o640)
    os.fchown(fd, 0, 1000)
    with os.fdopen(fd, 'wb') as target:
        target.write(raw); target.flush(); os.fsync(target.fileno())
    return {'path': str(OUT / name), 'bytes': len(raw), 'sha256': sha(raw)}


def permissions(raw, package):
    sections = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', raw.decode('utf-8', 'strict'), re.M | re.S)
    need(len(sections) == 1 and re.findall(r'^  Package \[([^]]+)\]', sections[0], re.M) == [package], 'PACKAGE_SCOPE')
    block = sections[0]
    starts = list(re.finditer(r'^    User (\d+): .*$', block, re.M))
    chosen = [i for i, m in enumerate(starts) if m[1] == '0']
    need(len(chosen) == 1, 'USER_ZERO_SCOPE')
    i = chosen[0]
    user = block[starts[i].start():starts[i + 1].start() if i + 1 < len(starts) else len(block)]
    runtime = re.findall(r'^        ([A-Za-z0-9_.]+): granted=(true|false), flags=\[(.*?)\]$', user, re.M)
    need(len(runtime) == len({p for p, _, _ in runtime}), 'DUPLICATE_RUNTIME_PERMISSION')
    requested = re.findall(r'^    requested permissions:\n(.*?)(?=^    \S|\Z)', block, re.M | re.S)
    installed = re.findall(r'^    install permissions:\n(.*?)(?=^    \S|\Z)', block, re.M | re.S)
    need(len(requested) <= 1 and len(installed) <= 1, 'PERMISSION_SECTION_COUNT')
    return {'runtime_permissions': {p: {'granted': g == 'true', 'flags': f} for p, g, f in runtime},
            'requested_permissions': [s.strip() for s in requested[0].splitlines()] if requested else [],
            'install_permissions': {p: g == 'true' for p, g in re.findall(
                r'^      ([A-Za-z0-9_.]+): granted=(true|false)(?:,.*)?$', installed[0], re.M)} if installed else {},
            'dump_sha256': sha(raw)}


def main():
    global DEADLINE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-once', action='store_true')
    args = parser.parse_args()
    if not args.export_once:
        print(json.dumps({'state': 'INERT', 'Main_queries': 0, 'ART_or_APK_verifier_runs': 0})); return
    DEADLINE = time.monotonic() + 35
    need(os.geteuid() == 0, 'ROOT_PRIVATE_RECEIPT_READER_REQUIRED')
    raw = read(BASE / 'result.json'); need(sha(raw) == EXPECTED, 'ORIGINAL_RESULT_CHANGED')
    original = json.loads(raw)
    journal = BASE / 'private/commands'
    value = {'original_result_sha256': EXPECTED, 'original_exit2_preserved': True,
             'Main_queries': 0, 'ART_or_APK_verifier_runs': 0, 'UI_actions': 0,
             'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'gaps': [], 'existing_permissions': {}}
    for index, app in enumerate(original['apps']):
        if app['identity_complete']:
            continue
        matches = list(journal.glob('*-p%02d-a00-badging.result.json' % index))
        need(len(matches) == 1, 'ONE_RETAINED_BADGING_RESULT')
        stem = str(matches[0])[:-len('.result.json')]
        status = json.loads(read(matches[0], 65536))
        out, err = read(stem + '.stdout'), read(stem + '.stderr', 65536)
        apk = app['apks'][0]
        need('manifest_stdout_sha256' not in apk or sha(out) == apk['manifest_stdout_sha256'], 'BADGING_STDOUT_CHANGED')
        need('manifest_stderr_sha256' not in apk or sha(err) == apk['manifest_stderr_sha256'], 'BADGING_STDERR_CHANGED')
        record = json.loads(read(BASE / ('private/app-%02d.json' % index)))
        value['gaps'].append({'index': index, 'package': app['package'], 'retained_record': record,
                              'badging': {'status': status, 'stdout': out.decode('utf-8', 'strict'),
                                          'stderr': err.decode('utf-8', 'strict'),
                                          'stdout_sha256': sha(out), 'stderr_sha256': sha(err)}})
    for path in sorted(journal.glob('*-android.intent.json')):
        intent = json.loads(read(path, 65536))
        argv = intent['argv']
        for package in ('com.android.calendar', 'com.android.gallery3d'):
            if argv[-3:] == ['/system/bin/dumpsys', 'package', package]:
                stem = str(path)[:-len('.intent.json')]
                status = json.loads(read(stem + '.result.json', 65536))
                need(status['rc'] == 0 and status['joined'] and status['guard_after'] and not status['timed_out'], 'PACKAGE_DUMP_COMMAND_NOT_COMPLETE')
                value['existing_permissions'].setdefault(package, []).append(permissions(read(stem + '.stdout'), package))
    need(set(value['existing_permissions']) == {'com.android.calendar', 'com.android.gallery3d'} and
         all(len(v) == 2 for v in value['existing_permissions'].values()), 'TWO_EXISTING_PERMISSION_OBSERVATIONS_REQUIRED')
    os.umask(0o077); OUT.mkdir(mode=0o750); os.chown(OUT, 0, 1000); os.chmod(OUT, 0o750)
    encoded = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    receipt = write('result.json', encoded); packed = write('result.json.gz', gzip.compress(encoded, mtime=0))
    print(json.dumps({'state': 'RETAINED_OUTPUTS_EXPORTED', 'result': receipt, 'compressed_result': packed,
                      'Main_queries': 0, 'verifier_runs': 0, 'UI_actions': 0}))


if __name__ == '__main__':
    main()
