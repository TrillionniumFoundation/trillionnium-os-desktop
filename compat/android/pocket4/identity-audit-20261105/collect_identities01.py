#!/usr/bin/python3 -I
"""Read 45 installed launcher identities and verify their actual APK signatures.

Inert by default. No UI, install, signing, account or private-key operation.
The held Main is fixed; host verifier outputs belong only to this new run.
"""
from pathlib import Path
import argparse, datetime, gzip, hashlib, json, os, re, stat, time, types

HERE = Path(__file__).resolve().parent
OUT = HERE / 'result-01'
TX = Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
UNIT = 'pocket4-app-identities01-r12.service'
LIMITS = {'memory.max': '805306368', 'memory.swap.max': '0',
          'cpu.max': '100000 100000', 'pids.max': '64'}
DEADLINE = 0.0
HASHED = 0
MAX_APK = 1024 * 1024 * 1024
MAX_TOTAL = 24 * MAX_APK
ATTRS = ('st_dev', 'st_ino', 'st_size', 'st_mode', 'st_uid', 'st_gid',
         'st_nlink', 'st_mtime_ns', 'st_ctime_ns')


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def budget(seconds=0):
    need(time.monotonic() + seconds < DEADLINE, 'COLLECTION_DEADLINE')


def meta(fd):
    value = os.fstat(fd)
    return {key: getattr(value, key) for key in ATTRS}


def pin_fd(fd, maximum=MAX_APK, count_total=False):
    global HASHED
    before = meta(fd)
    need(stat.S_ISREG(before['st_mode']) and 0 < before['st_size'] <= maximum,
         'REGULAR_FILE_SIZE_BOUND')
    digest, offset = hashlib.sha256(), 0
    while offset < before['st_size']:
        budget()
        part = os.pread(fd, min(1048576, before['st_size'] - offset), offset)
        need(part, 'SHORT_FILE_READ')
        digest.update(part)
        offset += len(part)
        if count_total:
            HASHED += len(part)
            need(HASHED <= MAX_TOTAL, 'TOTAL_APK_HASH_BYTES_BOUND')
    need(meta(fd) == before, 'FILE_CHANGED_DURING_HASH')
    return {'bytes': offset, 'sha256': digest.hexdigest(), 'stat': before}


def pin_host(path, maximum=256 * 1024 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        return pin_fd(fd, maximum)
    finally:
        os.close(fd)


def dependencies(expected):
    result = {}
    for name, row in expected.items():
        path = Path(row['declared_path']).resolve(strict=True)
        need(str(path) == row['resolved_path'], 'DEPENDENCY_RESOLUTION_CHANGED')
        p = pin_host(path)
        need(p['bytes'] == row['bytes'] and p['sha256'] == row['sha256'],
             'DEPENDENCY_HASH_CHANGED')
        result[name] = p
    return result


def packages(raw):
    need(len(raw) <= 262144 and raw.endswith(b'\n'), 'PACKAGE_LIST_BOUND')
    result = {}
    for line in raw.decode('utf-8', 'strict').splitlines():
        m = re.fullmatch(r'package:([A-Za-z0-9_.]+) versionCode:(\d+) uid:(\d+)', line)
        need(m and m[1] not in result, 'PACKAGE_LIST_GRAMMAR')
        result[m[1]] = {'uid': int(m[3]), 'version_code': int(m[2])}
    need(result, 'EMPTY_PACKAGE_LIST')
    return result


def launchers(raw):
    need(len(raw) <= 65536 and raw.endswith(b'\n'), 'LAUNCHER_LIST_BOUND')
    rows = raw.decode('utf-8', 'strict').splitlines()
    m = re.fullmatch(r'(\d+) activities found:', rows[0]) if rows else None
    need(m and 0 < int(m[1]) <= 4096 and len(rows) == 1 + 3 * int(m[1]),
         'LAUNCHER_BLOCK_COUNT')
    result = []
    for i in range(int(m[1])):
        head, fields, component = rows[1 + i * 3:4 + i * 3]
        need(head == '  Activity #' + str(i) + ':' and re.fullmatch(
            r'    priority=-?\d+ preferredOrder=-?\d+ match=0x[0-9a-fA-F]+ '
            r'specificIndex=-?\d+ isDefault=(?:true|false)', fields), 'LAUNCHER_METADATA')
        m = re.fullmatch(r'    ([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)', component)
        need(m, 'LAUNCHER_COMPONENT')
        result.append(m[1])
    need(len(result) == len(set(result)), 'DUPLICATE_LAUNCHER_COMPONENT')
    return result


def paths(raw):
    result = []
    for line in raw.decode('utf-8', 'strict').splitlines():
        need(line.startswith('package:/') and line.endswith('.apk'), 'APK_PATH_GRAMMAR')
        p = line[len('package:'):]
        need(not any(c in p for c in ('\0', '\n', '\r')) and len(p) <= 4096,
             'APK_PATH_BOUND')
        result.append(p)
    need(1 <= len(result) <= 64 and len(result) == len(set(result)), 'APK_PATH_COUNT')
    return result


def one(pattern, text, optional=False):
    values = re.findall(pattern, text, re.M)
    need(len(values) == 1 or (optional and not values), 'IDENTITY_FIELD_GRAMMAR')
    return values[0] if values else None


def active_identity(raw, package):
    text = raw.decode('utf-8', 'strict')
    sections = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', text, re.M | re.S)
    need(len(sections) == 1, 'ACTIVE_PACKAGE_SECTION')
    block = sections[0]
    need(re.findall(r'^  Package \[([^]]+)\]', block, re.M) == [package],
         'ACTIVE_PACKAGE_SELECTION')
    version = one(r'^    versionCode=(\d+) minSdk=(\d+) targetSdk=(\d+)(?: .*)?$', block)
    appid = one(r'^    (?:appId|userId)=(\d+)$', block)
    user = one(r'^    User 0: (.*)$', block)
    user_fields = dict(re.findall(r'(?:^| )(installed|hidden|suspended|stopped|enabled)=([^ ]+)', user))
    need(set(user_fields) == {'installed', 'hidden', 'suspended', 'stopped', 'enabled'},
         'USER_ZERO_FIELDS_MISSING')
    abis = {key: one(r'^    ' + key + r'=(.*)$', block, True)
            for key in ('primaryCpuAbi', 'secondaryCpuAbi', 'cpuAbiOverride')}
    return {'package': package, 'android_user': 0, 'app_id': int(appid),
            'uid': int(appid), 'version_code': int(version[0]),
            'min_sdk': int(version[1]), 'target_sdk': int(version[2]),
            'version_name': one(r'^    versionName=(.*)$', block, True),
            'cpu_abi': abis, 'user_state': user_fields,
            'code_path': one(r'^    codePath=(.*)$', block)}


def immutable_identity(row):
    return {k: v for k, v in row.items() if k != 'user_state'}


def badging(raw):
    text = raw.decode('utf-8', 'strict')
    line = one(r'^package: (.*)$', text)
    attrs = dict(re.findall(r"([A-Za-z][A-Za-z0-9_-]*)='([^']*)'", line))
    need('name' in attrs and 'versionCode' in attrs and attrs['versionCode'].isdigit(),
         'AAPT_PACKAGE_FIELDS')
    native = one(r'^native-code: (.*)$', text, True)
    code = int(attrs['versionCode'])
    if 'versionCodeMajor' in attrs:
        need(attrs['versionCodeMajor'].isdigit(), 'AAPT_VERSION_MAJOR')
        code |= int(attrs['versionCodeMajor']) << 32
    return {'package': attrs['name'], 'version_code': code,
            'version_name': attrs.get('versionName'), 'split_name': attrs.get('split'),
            'declared_min_sdk': one(r"^sdkVersion:'([^']+)'$", text, True),
            'declared_target_sdk': one(r"^targetSdkVersion:'([^']+)'$", text, True),
            'embedded_native_abis': re.findall(r"'([^']+)'", native) if native else []}


def signature(raw, rc):
    text = raw.decode('utf-8', 'strict')
    rows = re.findall(r'^Signer #(\d+) certificate SHA-256 digest: ([0-9a-fA-F]{64})\r?$', text, re.M)
    count = re.findall(r'^Number of signers: (\d+)\r?$', text, re.M)
    schemes = re.findall(r'^Verified using (v[0-9.]+) scheme \([^\r\n]+\): (true|false)\r?$', text, re.M)
    valid = (rc == 0 and 'Verifies' in text.splitlines() and len(count) == 1
             and 1 <= int(count[0]) <= 16 and len(rows) == int(count[0])
             and sorted(int(x[0]) for x in rows) == list(range(1, int(count[0]) + 1))
             and len(schemes) == len({x[0] for x in schemes})
             and any(x[1] == 'true' for x in schemes))
    return {'verified': bool(valid), 'tool_exit_code': rc,
            'signer_certificate_sha256': [v.lower() for _, v in sorted(rows, key=lambda x: int(x[0]))],
            'verified_schemes': {k: v == 'true' for k, v in schemes},
            'status': 'VERIFIED' if valid else 'VERIFICATION_FAILED_OR_UNRECOGNIZED_OUTPUT'}


def own_resources():
    lines = Path('/proc/self/cgroup').read_text().splitlines()
    need(len(lines) == 1 and lines[0] == '0::/system.slice/' + UNIT, 'OWN_UNIT_REQUIRED')
    cg = Path('/sys/fs/cgroup/system.slice') / UNIT
    need(str(os.getpid()) in (cg / 'cgroup.procs').read_text().split(), 'OWN_CGROUP_PID')
    values = {k: (cg / k).read_text().strip() for k in LIMITS}
    need(values == LIMITS and os.sched_getaffinity(0) == {20}, 'RESOURCE_LIMIT_MISMATCH')
    return {'limits': values, 'affinity': [20],
            'memory_peak_bytes': int((cg / 'memory.peak').read_text()),
            'memory_events': {k: int(v) for k, v in (x.split() for x in (cg / 'memory.events').read_text().splitlines())}}


def collect(expected_source):
    global DEADLINE
    DEADLINE = time.monotonic() + 690
    need(os.getuid() == os.geteuid() == 0, 'ROOT_HELD_READER_REQUIRED')
    raw = (HERE / 'SOURCE_PINS.json').read_bytes()
    need(sha(raw) == expected_source, 'SOURCE_MANIFEST_CHANGED')
    pins = json.loads(raw)['files']
    need(set(pins) == {'collect_identities01.py', 'targets.json', 'dependencies.json'}, 'SOURCE_MEMBERSHIP')
    for name, expect in pins.items():
        actual = pin_host(HERE / name)
        need(actual['bytes'] == expect['bytes'] and actual['sha256'] == expect['sha256'], 'SOURCE_CHANGED')
    targets = json.loads((HERE / 'targets.json').read_bytes())
    need(len(targets['packages']) == len(set(targets['packages'])) == 45, 'EXACT_45_TARGETS')
    expected_deps = json.loads((HERE / 'dependencies.json').read_bytes())['files']
    tx_raw = TX.read_bytes()
    need(sha(tx_raw) == TX_SHA, 'TRANSPORT_CHANGED')
    tx = types.ModuleType('app_identity_transport'); tx.__file__ = str(TX)
    exec(compile(tx_raw, str(TX), 'exec'), tx.__dict__)
    os.umask(0o077); OUT.mkdir(mode=0o750); os.chown(OUT, 0, 1000); os.chmod(OUT, 0o750)
    (OUT / 'private').mkdir(mode=0o700); (OUT / 'tmp').mkdir(mode=0o700)
    result = {'schema': 'pocket4-current-apk-identities-v1', 'state': 'INCOMPLETE',
              'read_only': True, 'UI_actions': 0, 'installs': 0, 'signing_operations': 0,
              'private_keys_read': False, 'account_or_user_content_read': False,
              'source_manifest_sha256': expected_source, 'source_session_sha256': TX_SHA,
              'started_utc': utc(), 'expected_package_count': 45, 'apps': [],
              'whole_app_production_ready': False, 'engine_runtime_qualification_inferred': False,
              'snapshot_scope': 'Bounded per-app observation windows; not one atomic 45-package snapshot.',
              'system_native_shared_libraries_fully_frozen': False}
    private = {'apps': []}
    try:
        result['own_resources_before'] = own_resources()
        before_deps = dependencies(expected_deps)
        dep = {k: v['resolved_path'] for k, v in expected_deps.items()}
        java = [dep['java'], '-XX:ActiveProcessorCount=1', '-XX:+UseSerialGC',
                '-XX:-UsePerfData', '-Xmx384m', '-XX:MaxDirectMemorySize=128m',
                '-Djava.io.tmpdir=' + str(OUT / 'tmp'), '-Duser.home=' + str(OUT / 'tmp'),
                '-XX:ErrorFile=' + str(OUT / 'private/java-error-%p.log')]
        with tx.CameraSession(OUT / 'private/commands') as session:
            result['guard_before'] = session.guard()
            need(session.epoch_sha256 == targets['epoch_sha256'], 'INVENTORY_MAIN_EPOCH_DIFFERS')
            pm_args = ['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--show-versioncode', '--user', '0']
            launch_args = ['/system/bin/cmd', 'package', 'query-activities', '--brief', '--user', '0',
                           '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER']
            before_packages = packages(session.android(pm_args))
            before_launchers = launchers(session.android(launch_args))
            sdk_raw = session.android(['/system/bin/getprop', 'ro.build.version.sdk'])
            need(re.fullmatch(rb'\d+\n', sdk_raw), 'RUNTIME_SDK_GRAMMAR')
            result['runtime_sdk'] = int(sdk_raw.strip())
            result['launcher_before'] = before_launchers
            for index, package in enumerate(targets['packages']):
                budget(10); session.guard()
                row = {'package': package, 'android_user': 0, 'started_utc': utc(), 'apks': [],
                       'identity_complete': False, 'signature_complete': False,
                       'engine': {'status': 'PENDING_RUNTIME_MAPPING',
                                  'reason': 'Install ABI and certificate observations do not prove a running ARM engine.'}}
                priv = {'package': package, 'apks': []}; result['apps'].append(row); private['apps'].append(priv)
                held = []
                try:
                    need(package in before_packages, 'TARGET_NOT_CURRENTLY_INSTALLED')
                    path_args = ['/system/bin/pm', 'path', '--user', '0', package]
                    guest_paths = paths(session.android(path_args))
                    identity = active_identity(session.android(['/system/bin/dumpsys', 'package', package]), package)
                    need(identity['uid'] == before_packages[package]['uid'] and
                         identity['version_code'] == before_packages[package]['version_code'], 'PM_IDENTITY_DISAGREES')
                    need(identity['user_state']['installed'] == 'true', 'USER_ZERO_NOT_INSTALLED')
                    row['identity'] = {k: v for k, v in identity.items() if k != 'code_path'}
                    row['prior_inventory_identity_equal'] = before_packages[package] == targets['baseline'][package]
                    priv['identity_before'] = identity
                    for guest in guest_paths:
                        need(guest.startswith(identity['code_path'].rstrip('/') + '/') or
                             guest == identity['code_path'], 'PM_PATH_OUTSIDE_ACTIVE_CODE_PATH')
                        fd = session.target.open_root(guest, os.O_RDONLY | os.O_NOFOLLOW)
                        held.append((guest, fd))
                    for split_index, (guest, fd) in enumerate(held):
                        budget(10); session.guard()
                        first = pin_fd(fd, count_total=True)
                        label = 'p%02d-a%02d' % (index, split_index)
                        apk = {'ordinal': split_index, 'bytes': first['bytes'], 'sha256': first['sha256']}
                        row['apks'].append(apk)
                        record = {'guest_path': guest, 'before': first}; priv['apks'].append(record)
                        command = java + ['-jar', dep['apksigner_jar'], 'verify', '--verbose', '--print-certs', '/proc/self/fd/' + str(fd)]
                        verified = session.run_host(label + '-verify', command, min(60, max(10, int(DEADLINE - time.monotonic() - 5))), (fd,))
                        apk['signature'] = signature(verified['stdout'], verified['rc'])
                        apk['signature'].update(stdout_sha256=sha(verified['stdout']), stderr_sha256=sha(verified['stderr']),
                                                joined=verified['joined'], timed_out=verified['timed_out'])
                        badge = session.run_host(label + '-badging', [dep['aapt'], 'dump', 'badging', '/proc/self/fd/' + str(fd)],
                                                 min(30, max(10, int(DEADLINE - time.monotonic() - 5))), (fd,))
                        if badge['rc'] == 0 and not badge['timed_out']:
                            apk['manifest'] = badging(badge['stdout'])
                            need(apk['manifest']['package'] == package and apk['manifest']['version_code'] == identity['version_code'],
                                 'APK_MANIFEST_AND_PM_DIFFER')
                        else:
                            apk['manifest_error'] = 'AAPT_BADGING_FAILED'
                        apk['manifest_stdout_sha256'] = sha(badge['stdout'])
                        apk['manifest_stderr_sha256'] = sha(badge['stderr'])
                        after = pin_fd(fd, count_total=True)
                        need(after == first, 'APK_CHANGED_DURING_VERIFICATION')
                        record['after'] = after
                        apk['held_file_unchanged'] = True
                    need(paths(session.android(path_args)) == guest_paths, 'ACTIVE_APK_PATH_SET_CHANGED')
                    after_identity = active_identity(session.android(['/system/bin/dumpsys', 'package', package]), package)
                    need(immutable_identity(after_identity) == immutable_identity(identity), 'ACTIVE_PACKAGE_IDENTITY_CHANGED')
                    priv['identity_after'] = after_identity
                    for (guest, fd), record in zip(held, priv['apks']):
                        fresh = session.target.open_root(guest, os.O_RDONLY | os.O_NOFOLLOW)
                        try:
                            need(meta(fresh) == meta(fd) == record['before']['stat'], 'CURRENT_APK_PATH_NO_LONGER_HELD_INODE')
                        finally:
                            os.close(fresh)
                    bases = [a for a in row['apks'] if a.get('manifest', {}).get('split_name') in (None, '') and 'manifest' in a]
                    need(len(bases) == 1 and all('manifest' in a for a in row['apks']), 'BASE_SPLIT_MANIFEST_COVERAGE')
                    split_names = [a['manifest']['split_name'] for a in row['apks']]
                    need(len(split_names) == len(set(split_names)), 'DUPLICATE_SPLIT_NAME')
                    certs = [a['signature']['signer_certificate_sha256'] for a in row['apks']]
                    row['base_split_certificates_equal'] = all(v == certs[0] for v in certs)
                    row['identity_complete'] = True
                    row['signature_complete'] = (all(a['signature']['verified'] and a['signature']['joined'] and
                                                         not a['signature']['timed_out'] for a in row['apks'])
                                                 and row['base_split_certificates_equal'])
                    row['current_path_inode_readback_equal'] = True
                except Exception as exc:
                    row['error_code'] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                    priv['error'] = {'type': type(exc).__name__, 'message': str(exc)}
                finally:
                    for _, fd in held:
                        os.close(fd)
                    row['finished_utc'] = utc()
                    tx.write_new(OUT / ('app-%02d.json' % index), row, alex_readable=True)
                    tx.write_new(OUT / ('private/app-%02d.json' % index), priv)
                session.guard()
            after_packages = packages(session.android(pm_args))
            result['launcher_after'] = launchers(session.android(launch_args))
            result['selected_pm_identity_before_after_equal'] = all(before_packages.get(p) == after_packages.get(p) for p in targets['packages'])
            result['launcher_set_unchanged'] = result['launcher_before'] == result['launcher_after']
            current = sorted({p.split('/')[0] for p in result['launcher_after']})
            result['expected_45_launcher_set_equal'] = current == targets['packages']
            result['launcher_added_since_prior'] = sorted(set(current) - set(targets['packages']))
            result['launcher_missing_since_prior'] = sorted(set(targets['packages']) - set(current))
            session.caller_status('identity-caller-after')
            result['guard_after'] = session.guard()
        after_deps = dependencies(expected_deps)
        need(before_deps == after_deps, 'VERIFICATION_TOOL_DEPENDENCY_DRIFT')
        result['tools_unchanged'] = True
        result['tools'] = {k: {'bytes': v['bytes'], 'sha256': v['sha256']} for k, v in before_deps.items()}
        result['identity_complete_count'] = sum(r['identity_complete'] for r in result['apps'])
        result['signature_complete_count'] = sum(r['signature_complete'] for r in result['apps'])
        result['apk_count'] = sum(len(r['apks']) for r in result['apps'])
        result['state'] = ('ALL_45_IDENTITIES_AND_APK_SIGNATURES_VERIFIED' if
            result['identity_complete_count'] == result['signature_complete_count'] == 45
            and result['selected_pm_identity_before_after_equal'] and result['launcher_set_unchanged']
            and result['expected_45_launcher_set_equal'] else 'COMPLETED_WITH_GAPS_OR_VERIFICATION_FAILURES')
    except BaseException as exc:
        result['error_code'] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        private['fatal_error'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        try:
            result['own_resources_after'] = own_resources()
        except Exception as exc:
            result['resource_error'] = type(exc).__name__
            result['state'] = 'INCOMPLETE'
        result['finished_utc'] = utc(); result['streamed_apk_hash_bytes'] = HASHED
        tx.write_new(OUT / 'private/retained.json', private)
        receipt = tx.write_new(OUT / 'result.json', result, alex_readable=True)
        encoded = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
        need(sha(encoded) == receipt['sha256'], 'RESULT_SERIALIZATION_CHANGED')
        compressed = tx.write_new(OUT / 'result.json.gz', gzip.compress(encoded, mtime=0), alex_readable=True)
    print(json.dumps({'state': result['state'], 'result': receipt,
                      'compressed_result': compressed,
                      'identity_complete_count': result.get('identity_complete_count'),
                      'signature_complete_count': result.get('signature_complete_count'),
                      'UI_actions': 0, 'installed': False, 'whole_app_production_ready': False}))
    return 0 if result['state'] == 'ALL_45_IDENTITIES_AND_APK_SIGNATURES_VERIFIED' else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-once', action='store_true')
    parser.add_argument('--source-manifest-sha256')
    args = parser.parse_args()
    if not args.collect_once:
        print(json.dumps({'state': 'INERT', 'expected_packages': 45, 'UI_actions': 0,
                          'installs': 0, 'signing_operations': 0, 'maximum_seconds': 720}))
        return 0
    need(re.fullmatch('[0-9a-f]{64}', args.source_manifest_sha256 or ''), 'SOURCE_PIN_REQUIRED')
    return collect(args.source_manifest_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
