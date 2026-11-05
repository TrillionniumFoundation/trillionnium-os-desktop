#!/usr/bin/python3 -I
"""Read exact installed system/QA APKs and audit manifest-to-DEX references.

No App code, UI, installs, account operations, or package modifications run.
A missing APK class is a finding for class-loader review, not an automatic
runtime failure. A present class never grants a functional or release gate.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, collections, gzip, hashlib, json, os, re, signal, stat, time, types, zipfile

HERE = Path(__file__).resolve().parent
OUT = Path('/home/alex/work/pocket4-system-component-audit-20261105-r12-01')
TX = Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
COLLECTOR = Path('/home/alex/work/pocket4-app-identities-20261105-r12-01/collect_identities01.py')
COLLECTOR_SHA = '4555d4d5fad1b1cf1fe47d599f5b4c13c6259106958b525aa58bbeecb7c4c869'
ANDROID = '{http://schemas.android.com/apk/res/android}'
DEX_NAME = re.compile(r'classes(?:[2-9]|[1-9][0-9]+)?\.dex')
MAX_MEMBER = 128 * 1024 * 1024


def need(ok, why):
    if not ok: raise RuntimeError(why)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def stamp(): return datetime.now(timezone.utc).isoformat()


def pinned(path, expected, maximum=262144):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        a = os.fstat(fd)
        need(stat.S_ISREG(a.st_mode) and a.st_nlink == 1 and 0 < a.st_size <= maximum,
             'SOURCE_FILE_SCOPE:' + path.name)
        raw = bytearray()
        while len(raw) < a.st_size:
            part = os.read(fd, min(65536, a.st_size - len(raw)))
            need(part, 'SOURCE_TRUNCATED'); raw.extend(part)
        b = os.fstat(fd)
        attrs = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        need(all(getattr(a, k) == getattr(b, k) for k in attrs) and sha(raw) == expected,
             'SOURCE_CHANGED:' + path.name)
        return bytes(raw)
    finally: os.close(fd)


def module(path, expected, name):
    raw = pinned(path, expected)
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def class_name(package, value):
    if not isinstance(value, str) or not value or value.startswith('@'):
        return None
    name = package + value if value.startswith('.') else package + '.' + value if '.' not in value else value
    if not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*', name):
        return None
    return name


def manifest_references(elements, package, ordinal):
    roots = [e for e in elements if e['path'] == 'manifest']
    need(len(roots) == 1 and roots[0]['attributes'].get('package') == package,
         'MANIFEST_PACKAGE_CHANGED')
    refs, aliases, libraries = [], [], []
    declared = {class_name(package, e['attributes'].get(ANDROID + 'name'))
                for e in elements if e['path'] == 'manifest/application/activity'}
    declared.discard(None)
    for element in elements:
        path, attrs = element['path'], element['attributes']
        kind = path.rsplit('/', 1)[-1]
        slots = []
        if path == 'manifest/application':
            slots = ['name', 'backupAgent', 'appComponentFactory', 'manageSpaceActivity', 'zygotePreloadName']
        elif path in ('manifest/application/activity', 'manifest/application/service',
                      'manifest/application/receiver', 'manifest/application/provider', 'manifest/instrumentation'):
            slots = ['name']
            if kind == 'activity': slots.append('parentActivityName')
        elif path == 'manifest/application/activity-alias':
            slots = ['targetActivity', 'parentActivityName']
            target = class_name(package, attrs.get(ANDROID + 'targetActivity'))
            aliases.append({'apk_ordinal': ordinal, 'alias': attrs.get(ANDROID + 'name'),
                'target_activity': target, 'target_declared_in_this_manifest': target in declared,
                'alias_name_is_not_a_class_reference': True})
        elif path in ('manifest/application/uses-library', 'manifest/application/uses-static-library',
                      'manifest/application/uses-sdk-library', 'manifest/uses-split'):
            libraries.append({'apk_ordinal': ordinal, 'kind': kind,
                'name': attrs.get(ANDROID + 'name'), 'required': attrs.get(ANDROID + 'required')})
        for slot in slots:
            key = ANDROID + slot
            if key not in attrs: continue
            value = attrs[key]; name = class_name(package, value)
            refs.append({'apk_ordinal': ordinal, 'element': path, 'attribute': slot,
                'declared_value': value, 'class_name': name,
                'descriptor': 'L' + name.replace('.', '/') + ';' if name else None,
                'declared_enabled': attrs.get(ANDROID + 'enabled'),
                'declared_exported': attrs.get(ANDROID + 'exported'),
                'resource_boolean_values_resolved': False})
    return refs, aliases, libraries, roots[0]['attributes'].get('split')


def resources():
    lines = Path('/proc/self/cgroup').read_text().splitlines()
    need(len(lines) == 1 and lines[0].startswith('0::/'), 'UNIFIED_OWN_CGROUP_REQUIRED')
    relative = lines[0][4:]
    need('..' not in Path(relative).parts, 'OWN_CGROUP_PATH')
    root = Path('/sys/fs/cgroup') / relative
    values = {n: (root / n).read_text().strip() for n in
              ('memory.max', 'memory.swap.max', 'memory.peak', 'memory.events', 'cpu.max', 'pids.max')}
    return {'cgroup': '/' + relative, 'affinity': sorted(os.sched_getaffinity(0)), 'values': values}


def scan_package(s, c, decode, dex, expected):
    package = expected['package']
    row = {'package': package, 'state': 'INCOMPLETE', 'started_utc': stamp(), 'apks': [],
           'class_references': [], 'aliases': [], 'declared_libraries': [],
           'whole_app_production_ready': False, 'functional_or_runtime_gate_granted': False}
    fds = []
    try:
        c.budget(3)
        before = c.active_identity(s.android(['/system/bin/dumpsys', 'package', package], 15), package)
        need(before['uid'] == expected['uid'] and before['version_code'] == expected['version_code']
             and before['android_user'] == 0 and before['min_sdk'] == expected['min_sdk']
             and before['target_sdk'] == expected['target_sdk'], 'INSTALLED_IDENTITY_CHANGED')
        row['identity_before'] = before
        paths = c.paths(s.android(['/system/bin/pm', 'path', '--user', '0', package], 15))
        need(len(paths) == len(expected['apks']), 'ACTIVE_APK_SET_COUNT_CHANGED')
        index = collections.defaultdict(list)
        for ordinal, path in enumerate(paths):
            c.budget(3)
            fd = s.target.open_root(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            fds.append((path, fd))
            initial = c.pin_fd(fd, maximum=256 * 1024 * 1024, count_total=True)
            exp = expected['apks'][ordinal]
            need((initial['sha256'], initial['bytes']) == (exp['sha256'], exp['bytes']),
                 'ACTIVE_APK_BYTES_DIFFER_FROM_REVIEWED_TARGET')
            apk = {'ordinal': ordinal, 'path': path, **initial,
                'prior_verified_certificates_bound_by_identical_whole_APK_bytes': exp['certificates'],
                'signature_verifier_rerun': False, 'dex_files': []}
            row['apks'].append(apk)
            with os.fdopen(os.dup(fd), 'rb') as stream, zipfile.ZipFile(stream) as archive:
                members = archive.infolist(); names = [x.filename for x in members]
                need(1 <= len(members) <= 65536 and len(names) == len(set(names)), 'APK_ZIP_DIRECTORY_SCOPE')
                info = archive.getinfo('AndroidManifest.xml')
                need(0 < info.file_size <= 2 * 1024 * 1024, 'MANIFEST_SIZE_BOUND')
                raw = archive.read(info); elements = decode.decode(raw)
                refs, aliases, libraries, split = manifest_references(elements, package, ordinal)
                apk['manifest'] = {'bytes': len(raw), 'sha256': sha(raw), 'split_name': split,
                                   'element_count': len(elements), 'class_reference_count': len(refs)}
                row['class_references'].extend(refs); row['aliases'].extend(aliases)
                row['declared_libraries'].extend(libraries)
                dex_names = sorted((n for n in names if DEX_NAME.fullmatch(n)),
                    key=lambda n: 1 if n == 'classes.dex' else int(n[7:-4]))
                need(len(dex_names) <= 64, 'DEX_COUNT_BOUND')
                apk['other_dex_members_not_treated_as_default_classpath'] = [
                    n for n in names if n.endswith('.dex') and n not in dex_names]
                need(sum(archive.getinfo(n).file_size for n in dex_names) <= 512 * 1024 * 1024,
                     'TOTAL_DEX_SIZE_BOUND')
                for name in dex_names:
                    c.budget(2); info = archive.getinfo(name)
                    need(112 <= info.file_size <= MAX_MEMBER, 'DEX_MEMBER_SIZE_BOUND')
                    data = archive.read(info); classes = dex.classes(data)
                    digest = sha(data)
                    apk['dex_files'].append({'name': name, 'bytes': len(data), 'sha256': digest,
                        'class_count': len(classes), 'format': data[4:7].decode('ascii'),
                        'class_descriptor_list_sha256': sha(('\n'.join(sorted(classes)) + '\n').encode())})
                    for descriptor in classes:
                        index[descriptor].append({'apk_ordinal': ordinal, 'dex_file': name,
                                                  'dex_sha256': digest})
                    del data, classes
            need(c.meta(fd) == initial['stat'], 'APK_METADATA_CHANGED_DURING_PARSE')
        for ref in row['class_references']:
            descriptor = ref['descriptor']
            ref['definitions'] = index.get(descriptor, []) if descriptor else []
            ref['status'] = ('UNRESOLVED_MANIFEST_CLASS_VALUE' if descriptor is None else
                             'PRESENT_IN_INSTALLED_APK_DEX' if ref['definitions'] else
                             'NOT_IN_APK_DEX_REQUIRES_CLASS_LOADER_REVIEW')
            if descriptor and not ref['definitions']:
                ref['possible_framework_prefix'] = ref['class_name'].startswith(('android.', 'java.', 'javax.'))
        row['total_unique_APK_classes'] = len(index)
        row['duplicate_descriptors_across_APK_DEX'] = [
            {'descriptor': name, 'definitions': value} for name, value in sorted(index.items()) if len(value) > 1]
        row['descriptor_union_sha256'] = sha(('\n'.join(sorted(index)) + '\n').encode())
        row['class_reference_counts'] = dict(collections.Counter(r['status'] for r in row['class_references']))
        after_paths = c.paths(s.android(['/system/bin/pm', 'path', '--user', '0', package], 15))
        after = c.active_identity(s.android(['/system/bin/dumpsys', 'package', package], 15), package)
        need(after_paths == paths and c.immutable_identity(after) == c.immutable_identity(before),
             'INSTALLED_PACKAGE_CHANGED_DURING_AUDIT')
        row['identity_after'] = after
        for (path, fd), apk in zip(fds, row['apks']):
            after_hash = c.pin_fd(fd, maximum=256 * 1024 * 1024, count_total=True)
            need(after_hash == {k: apk[k] for k in ('sha256', 'bytes', 'stat')}, 'HELD_APK_BYTES_CHANGED')
            current = s.target.open_root(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try: need(c.meta(current) == apk['stat'], 'ACTIVE_PATH_REPLACED')
            finally: os.close(current)
            apk['whole_hash_before_after_equal'] = True
            apk['current_path_matches_held_file'] = True
        s.guard()
        row['state'] = 'EXACT_INSTALLED_MANIFEST_AND_DEX_AUDITED'
    except Exception as exc:
        row['error'] = type(exc).__name__ + ':' + str(exc)
    finally:
        for _, fd in fds: os.close(fd)
        row['finished_utc'] = stamp()
    return row


def expired(*unused): raise TimeoutError('READ_ONLY_AUDIT_DEADLINE')


def execute(manifest_sha):
    need(os.geteuid() == 0 and not os.path.lexists(OUT), 'FRESH_OUTPUT_ROOT_REQUIRED')
    manifest = json.loads(pinned(HERE / 'SOURCE_PINS.json', manifest_sha))
    names = {'run_audit01.py', 'targets.json', 'decode_manifest.py', 'dex_classes.py'}
    need(set(manifest['files']) == names, 'EXACT_SOURCE_SET_REQUIRED')
    for name, value in manifest['files'].items(): pinned(HERE / name, value['sha256'])
    targets = json.loads(pinned(HERE / 'targets.json', manifest['files']['targets.json']['sha256']))
    need(len(targets['apps']) == 14 and len({a['package'] for a in targets['apps']}) == 14
         and len(targets['all_launcher_components']) == 45, 'EXPECTED_SCOPE_REQUIRED')
    tx = module(TX, TX_SHA, 'component_audit_transaction')
    c = module(COLLECTOR, COLLECTOR_SHA, 'component_audit_identity')
    decode = module(HERE / 'decode_manifest.py', manifest['files']['decode_manifest.py']['sha256'], 'component_audit_axml')
    dex = module(HERE / 'dex_classes.py', manifest['files']['dex_classes.py']['sha256'], 'component_audit_dex')
    c.DEADLINE = time.monotonic() + 420; c.MAX_TOTAL = 4 * 1024 * 1024 * 1024
    os.umask(0o077); OUT.mkdir(mode=0o750); os.chown(OUT, 0, 1000); os.chmod(OUT, 0o750)
    os.sched_setaffinity(0, {20})
    out = {'schema': 'pocket4-system-manifest-class-audit-v1', 'state': 'INCOMPLETE',
        'started_utc': stamp(), 'source_manifest_sha256': manifest_sha, 'source_transport_sha256': TX_SHA,
        'target_count': 14, 'retained_launcher_scope': 45, 'apps': [],
        'ui_actions': 0, 'package_or_permission_mutations': 0, 'apk_code_executed': False,
        'account_or_user_content_read': False, 'whole_app_production_ready': False,
        'release_gates_granted': 0, 'classpath_scope': 'Default classes*.dex in every current base/split APK.',
        'boot_shared_library_dynamic_classloader_resolution_checked': False,
        'business_behavior_or_empty_method_bodies_checked': False,
        'observation_scope': 'Per-package bounded windows, not an atomic snapshot of all packages.'}
    old_signal = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 450)
    try:
        out['own_resources_before'] = resources()
        with tx.CameraSession(OUT / 'private-commands') as s:
            out['guard_before'] = s.guard(); need(s.epoch_sha256 == targets['epoch_sha256'], 'HELD_MAIN_CHANGED')
            launcher_argv = ['/system/bin/cmd', 'package', 'query-activities', '--brief', '--user', '0',
                             '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER']
            out['launchers_before'] = c.launchers(s.android(launcher_argv, 15))
            need(sorted(out['launchers_before']) == sorted(targets['all_launcher_components']), 'LAUNCHER_SCOPE_CHANGED')
            for expected in targets['apps']:
                c.budget(3); row = scan_package(s, c, decode, dex, expected)
                out['apps'].append(row)
                tx.write_new(OUT / (expected['package'] + '.json'), row, alex_readable=True)
            out['launchers_after'] = c.launchers(s.android(launcher_argv, 15))
            need(sorted(out['launchers_after']) == sorted(out['launchers_before']), 'LAUNCHERS_CHANGED')
            out['guard_after'] = s.guard(); need(out['guard_after'] == out['guard_before'], 'MAIN_CHANGED_AFTER')
            s.caller_status('component-audit-final')
            out['completed_packages'] = sum(a['state'] == 'EXACT_INSTALLED_MANIFEST_AND_DEX_AUDITED' for a in out['apps'])
            out['class_reference_counts'] = dict(sum((collections.Counter(a.get('class_reference_counts', {}))
                for a in out['apps'] if a['state'] == 'EXACT_INSTALLED_MANIFEST_AND_DEX_AUDITED'), collections.Counter()))
            out['state'] = 'READ_ONLY_COMPONENT_AUDIT_COMPLETE' if out['completed_packages'] == 14 else 'READ_ONLY_COMPONENT_AUDIT_INCOMPLETE'
    except BaseException as exc: out['error'] = type(exc).__name__ + ':' + str(exc)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, old_signal)
        try: out['own_resources_after'] = resources()
        except Exception as exc: out['resource_readback_error'] = type(exc).__name__ + ':' + str(exc)
    out['whole_APK_hash_bytes_read'] = c.HASHED; out['finished_utc'] = stamp()
    raw = (json.dumps(out, indent=2, sort_keys=True) + '\n').encode(); packed = gzip.compress(raw, mtime=0)
    need(len(raw) <= 16 * 1024 * 1024 and len(packed) <= 2 * 1024 * 1024, 'RESULT_SIZE_BOUND')
    tx.write_new(OUT / 'result.json', raw, alex_readable=True)
    tx.write_new(OUT / 'result.json.gz', packed, alex_readable=True)
    print(json.dumps({'state': out['state'], 'completed_packages': out.get('completed_packages', 0),
        'class_reference_counts': out.get('class_reference_counts'), 'error': out.get('error'),
        'result_bytes': len(raw), 'result_sha256': sha(raw), 'gzip_bytes': len(packed),
        'gzip_sha256': sha(packed), 'gzip_path': str(OUT / 'result.json.gz'), 'ui_actions': 0}))
    return 0 if out['state'] == 'READ_ONLY_COMPONENT_AUDIT_COMPLETE' else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--execute')
    a = p.parse_args()
    if a.execute: raise SystemExit(execute(a.execute))
    print('INERT: no Android, UI, package, or file mutation')
