#!/usr/bin/env python3
"""One independent, read-only Main FD diagnostic; never publish QA source.

The frozen worker/core/reader/generator are loaded by their actual source pins.
Only the existing native status/applications APIs and the frozen scope reader
are invoked. Generator acquisition and rendering stay in memory. A descriptor
difference stops subsequent work; only explicitly tracked descriptors close.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import base64
import errno
import fcntl
import hashlib
import json
import os
import re
import stat
import time
import types

OLD_NONCE = '77fe9d36efe51cf69813f3411099f049'
ORIGINAL_WORKER = {
    'path': '/home/alex/work/pocket4-beike-qa-source-preparation-worker-20261106-'+OLD_NONCE+'/prepare_beike_bound_source.py',
    'bytes': 22148, 'sha256': '9db3af14e7f2903e3b94bc45ed43f202f2ceb243e95f904dcab3c363aa55cbde'}
FAILED_RESULT = {
    'path': '/home/alex/work/pocket4-beike-successor-qa-input-20261106-'+OLD_NONCE+'/result.json',
    'bytes': 28348, 'sha256': '518c1b9bcef120ec80a1a5e46cce36b6c0f4fe3d489652f21bf4bbc14f60ac1e'}
STAT = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
        'st_rdev', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
IDENTITY = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_rdev')


class Rejected(RuntimeError):
    pass


class DescriptorDifference(Rejected):
    pass


def need(value, code):
    if not value:
        raise Rejected(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def parse(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def invalid(_):
        raise Rejected('NONFINITE_JSON_NUMBER')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def error_record(error):
    value = {'type': type(error).__name__}
    if isinstance(error, OSError):
        value['errno'] = error.errno
    elif isinstance(error, RuntimeError) and re.fullmatch('[A-Z0-9_]{1,120}', str(error)):
        value['code'] = str(error)
    else:
        value['code'] = 'DETAILS_NOT_ASSUMED_TO_PROVE_DESCRIPTOR_CAUSE'
    return value


def root_pin(pin, limit=262144):
    need(type(pin) is dict and set(pin) == {'path', 'bytes', 'sha256'}, 'CLOSED_PIN')
    path = pin['path']
    need(type(path) is str and path.startswith('/') and
         all(x not in ('', '.', '..') for x in path[1:].split('/')), 'CANONICAL_PIN_PATH')
    need(type(pin['bytes']) is int and 0 < pin['bytes'] <= limit and
         re.fullmatch('[0-9a-f]{64}', pin['sha256']), 'EXACT_PIN_BOUND')
    descriptors = []
    try:
        d = os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC); descriptors.append(d)
        parts = path[1:].split('/')
        for name in parts[:-1]:
            d = os.open(name, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=d)
            descriptors.append(d)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=d)
        descriptors.append(fd)
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_uid == 0 and first.st_nlink == 1 and
             first.st_size == pin['bytes'], 'ROOT_PIN_FILE_IDENTITY')
        raw, deadline = bytearray(), time.monotonic()+10
        while len(raw) <= limit:
            need(time.monotonic() < deadline, 'PIN_READ_DEADLINE')
            block = os.read(fd, min(65536, limit+1-len(raw)))
            if not block:
                break
            raw.extend(block)
        again = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=d)
        descriptors.append(again)
        need(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'] and
             all(getattr(first, k) == getattr(os.fstat(fd), k) == getattr(os.fstat(again), k) for k in STAT),
             'PIN_PATH_OR_CONTENT_CHANGED')
        return bytes(raw)
    finally:
        errors = []
        for fd in reversed(descriptors):
            try:
                os.close(fd)
            except OSError as error:
                errors.append(error_record(error))
        need(not errors, 'BOOTSTRAP_OWNED_FD_CLOSE_FAILED')


def module(pin, name):
    raw = root_pin(pin)
    value = types.ModuleType(name)
    value.__file__ = pin['path']
    exec(compile(raw, pin['path'], 'exec'), value.__dict__)
    return value


def fd_row(fd):
    path = '/proc/self/fd/'+str(fd)
    first = os.fstat(fd)
    link = os.readlink(path)
    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    last = os.fstat(fd)
    need(all(getattr(first, k) == getattr(last, k) for k in IDENTITY) and
         os.readlink(path) == link and fcntl.fcntl(fd, fcntl.F_GETFD) == flags,
         'FD_CHANGED_DURING_IDENTITY_READ')
    return {'fd': fd, 'link': link, 'descriptor_flags': flags,
            'fstat': {k: getattr(last, k) for k in STAT}}


def identity(row):
    return {'link': row['link'], 'descriptor_flags': row['descriptor_flags'],
            'fstat': {k: row['fstat'][k] for k in IDENTITY}}


def snapshot_once():
    # listdir has returned and closed its directory before any fstat. No new
    # descriptor is opened in this loop. The single disappeared listdir entry
    # is recorded, never counted as a lasting FD or adopted as owned.
    need(len(os.listdir('/proc/self/task')) == 1, 'SINGLE_THREAD_REQUIRED_FOR_FD_DIAGNOSIS')
    names = os.listdir('/proc/self/fd')
    need(len(names) <= 512 and all(x.isdecimal() for x in names), 'PROCESS_FD_BOUND')
    rows, vanished = {}, []
    for fd in sorted(map(int, names)):
        try:
            rows[fd] = fd_row(fd)
        except OSError as error:
            if error.errno == errno.EBADF:
                vanished.append(fd)
            else:
                raise
    need(len(vanished) == 1 and vanished[0] not in rows, 'AMBIGUOUS_LISTDIR_FD_RETIREMENT')
    return rows, vanished


def fd_snapshot():
    first, gone1 = snapshot_once()
    second, gone2 = snapshot_once()
    need(set(first) == set(second) and gone1 == gone2 and
         all(identity(first[fd]) == identity(second[fd]) for fd in first),
         'FD_REUSE_OR_CONCURRENT_CHANGE_AMBIGUOUS')
    return {'descriptors': second, 'closed_collection_entries': gone2,
            'persistent_count': len(second), 'two_pass_identity_stable': True,
            'same_inode_reopen_without_observed_change_not_claimed_detectable': True}


class FDMonitor:
    def __init__(self):
        self.baseline = fd_snapshot()
        self.owned = {}
        self.sequence = 0
        self.events = []
        self.first_problem = None

    def acquire(self, fd, owner):
        need(fd >= 3 and fd not in self.owned and fd not in self.baseline['descriptors'],
             'NEW_OWNED_FD_MUST_NOT_ALIAS_BASELINE')
        self.sequence += 1
        self.owned[fd] = {'owner': owner, 'generation': self.sequence, 'identity': identity(fd_row(fd))}

    def verify_owned(self, fd, owner):
        need(fd in self.owned and self.owned[fd]['owner'] == owner, 'OWNERSHIP_REQUIRED_BEFORE_CLOSE')
        need(identity(fd_row(fd)) == self.owned[fd]['identity'], 'OWNED_FD_IDENTITY_CHANGED_NO_CLOSE')

    def release(self, fd, owner):
        need(fd in self.owned and self.owned[fd]['owner'] == owner, 'EXPLICIT_OWNED_RELEASE_REQUIRED')
        del self.owned[fd]

    def check(self, phase):
        need(len(self.events) < 96, 'DIAGNOSTIC_PHASE_BOUND')
        observed = fd_snapshot()
        actual = observed['descriptors']
        expected = {fd: identity(row) for fd, row in self.baseline['descriptors'].items()}
        expected.update({fd: row['identity'] for fd, row in self.owned.items()})
        missing = sorted(set(expected)-set(actual))
        added = sorted(set(actual)-set(expected))
        changed = sorted(fd for fd in set(actual)&set(expected) if identity(actual[fd]) != expected[fd])
        event = {'phase': phase, 'monotonic_ns': time.monotonic_ns(), **observed,
                 'active_owned': {fd: {'owner': row['owner'], 'generation': row['generation']}
                                  for fd, row in self.owned.items()},
                 'unexpected_fds': added, 'missing_expected_fds': missing, 'changed_identity_fds': changed}
        self.events.append(event)
        if added or missing or changed:
            if self.first_problem is None:
                self.first_problem = {'phase': phase, 'unexpected': [actual[fd] for fd in added],
                    'missing_expected': missing, 'changed': [
                        {'fd': fd, 'expected': expected[fd], 'actual': actual[fd]} for fd in changed]}
            raise DescriptorDifference('DESCRIPTOR_DIFFERENCE_STOP_BEFORE_NEXT_PHASE')
        return observed


def traced_pool(core, monitor, label):
    class Traced(core.FDs):
        def own(self, fd):
            value = super().own(fd)
            monitor.acquire(fd, label)
            return value

        def close(self, fd):
            # Identity disagreement deliberately prevents close. This cannot
            # turn an unexpected descriptor into something the diagnostic owns.
            monitor.verify_owned(fd, label)
            super().close(fd)
            monitor.release(fd, label)
    return Traced()


def run(request):
    need(os.getuid() == os.geteuid() == 0, 'ACTUAL_ROOT_REQUIRED')
    monitor = FDMonitor()
    deadline = time.monotonic()+900
    core = pool = leases = lock = root = root_identity = None
    result = {'schema': 'pocket4-beike-source-fd-diagnostic-v1', 'ok': False,
              'automatic_retry': False, 'UI_actions': 0, 'installs': 0, 'builds': 0,
              'permission_changes': 0, 'direct_namespace_entries': 0, 'ADB_commands': 0,
              'lifecycle_commands': 0, 'generator_generate_calls': 0,
              'QA_source_publications': 0, 'production_ready': False,
              'UI_or_install_runtime_admitted': False, 'commands': [], 'errors': [],
              'unknown_descriptors_closed': 0, 'old_source_nonce_reused': False}

    def step(label, operation):
        need(time.monotonic() < deadline, 'DIAGNOSTIC_DEADLINE')
        try:
            return operation()
        finally:
            # This gate runs even if the operation raises. Nothing after this
            # boundary runs when an unowned or changed descriptor is observed.
            monitor.check(label)

    def write(name, raw):
        need(root is not None and '/' not in name and name not in ('', '.', '..'), 'OWN_HOST_OUTPUT_ONLY')
        return core.write_new(root+'/'+name, raw)

    try:
        worker = step('load_original_worker', lambda: module(ORIGINAL_WORKER, 'fd_diagnostic_frozen_worker'))
        worker.validate_request(request)
        nonce = request['generation_nonce']
        need(nonce != OLD_NONCE, 'FAILED_SOURCE_NONCE_MUST_REMAIN_UNUSED')
        root = '/home/alex/work/pocket4-beike-source-fd-diagnostic-20261106-'+nonce
        need(not os.path.lexists(root) and not os.path.lexists(request['output_root']) and
             not os.path.lexists('/home/alex/work/pocket4-successor-qa-source-'+nonce), 'NEW_DIAGNOSTIC_NONCE_REQUIRED')
        step('pin_original_failed_result', lambda: worker.read_root_pin(FAILED_RESULT))
        guard = step('load_guard', lambda: worker.module(worker.GUARD, 'fd_diagnostic_actual_guard'))
        core = step('load_and_configure_frozen_core', guard._core)
        reader = step('load_reader', lambda: worker.module(worker.READER, 'fd_diagnostic_frozen_reader'))
        native = step('load_native_identity_helpers', lambda: worker.module(worker.NATIVE_HELPERS, 'fd_diagnostic_native_helpers'))
        generator = step('load_generator', lambda: worker.module(worker.GENERATOR, 'fd_diagnostic_generator'))
        step('pin_generator_manifest', lambda: worker.read_root_pin(worker.GENERATOR_MANIFEST))
        pool, leases = traced_pool(core, monitor, 'observation'), traced_pool(core, monitor, 'lease')
        lock, result['action_lock_identity'] = step('acquire_existing_action_lock',
            lambda: core.acquire_lock(leases, core.ACTION_LOCK))
        before = step('guard_before', guard.current_guard)
        need(before['schema'] == 'pocket4-successor-main-guard-v1' and
             before['runtime_epoch_sha256'] == worker.RUNTIME_EPOCH, 'EXACT_SUCCESSOR_GUARD')
        result['guard_before'] = before
        baseline = step('read_current_baseline', guard.current_baseline)
        binding = baseline['runtime']['held']['process_snapshot']['binding']
        held = step('hold_exact_eight_roles', lambda: core.HeldProcesses(pool,
            {name: row['host_pid'] for name, row in binding['processes'].items()}))
        need(held.before['binding'] == binding, 'EXACT_EIGHT_ROLES_REQUIRED')
        step('verify_runtime_before', lambda: core.verify_runtime(pool, held, baseline['runtime']))
        scope = step('read_final_46_scope', lambda: worker.parse(worker.read_root_pin(request['app_scope'])))
        need(scope['schema'] == 'pocket4-versioned-app-scope-v1' and
             scope['runtime_epoch_sha256'] == worker.RUNTIME_EPOCH and
             set(scope['apps']) == set(worker.LAUNCHERS)|{worker.EXISTING_ACTIONS}, 'EXACT_FINAL_46_SCOPE')
        packages = sorted(scope['apps'])
        step('guard_full_app_scope_before', lambda: guard.check_app_scope(request['app_scope'], packages))
        step('current_46_apps_before', lambda: core.app_scope(pool, held, packages, scope['apps'], False))
        for index, pin in enumerate(request['install_or_signature_evidence']):
            step('pin_upgrade_evidence_'+str(index), lambda pin=pin: core.pinned_record(pin))
        step('old_Bili_unknown_before', lambda: native.original_unknown(core))
        location = step('protected_Meituan_before', lambda: native.protected_location(core, pool, held, scope['apps']))
        files, pins = step('bind_native_files', lambda: native.native_bind(core, pool, held))
        owner = binding['processes']['launcher']['host_pid']
        step('create_new_diagnostic_host_root', lambda: core.create_private_root(root))
        root_fd = step('hold_new_diagnostic_root', lambda: core.open_host(pool, root, os.O_RDONLY|os.O_DIRECTORY))
        root_identity = core.metadata(root_fd)
        result['request'] = step('write_diagnostic_request', lambda: write('request.json', canonical(request)+b'\n'))

        def native_read(operation):
            need(operation in ('status', 'applications'), 'READ_ONLY_NATIVE_OPERATION')
            index = len(result['commands'])+1
            prefix = 'native_%02d_%s' % (index, operation)
            step(prefix+'_identity_before', lambda: native.recheck_native(core, pool, held, files, pins))
            argv = core.as_user([native.CLI_PATH, '--socket', native.SOCKET_PATH, '--json', operation])
            command_record = {'operation': operation}
            def invoke():
                raw, stderr, command = core.bounded_child(argv, seconds=30, limit=262144)
                # Save the exact child outcome in memory before the FD gate:
                # even a leak at this boundary must not erase command evidence.
                command_record.update(command=command, streams_inline={
                    'stdout_base64': base64.b64encode(raw).decode('ascii'),
                    'stderr_base64': base64.b64encode(stderr).decode('ascii')})
                result['commands'].append(command_record)
                return raw, stderr, command
            raw, stderr, command = step(prefix+'_bounded_child', invoke)
            streams = command_record['streams_inline']
            saved = step(prefix+'_write_streams', lambda: write(prefix+'.streams.json', canonical(streams)+b'\n'))
            command_record['streams'] = saved
            del command_record['streams_inline']
            value = core.native_running(raw, command)
            need(value['host_pid'] == owner, 'NATIVE_OWNER_CHANGED')
            step(prefix+'_identity_after', lambda: native.recheck_native(core, pool, held, files, pins))
            need(step(prefix+'_guard_after', guard.current_guard) == before, 'NATIVE_READ_GUARD_CHANGED')
            return value, raw

        native_read('status')
        catalog, raw = native_read('applications')
        component, comparison = worker.select_catalog(catalog, owner)
        result['fresh_catalog'] = comparison
        need(comparison['added_packages'] == [] and comparison['missing_packages'] == [], 'FRESH_RESOLVER_SET_CHANGED')
        catalog_pin = step('write_fresh_catalog', lambda: write('native-catalog.json', raw))
        native_read('status')
        observed_request = {'schema': 'pocket4-successor-app-observation-request-v1', 'guard': worker.GUARD,
            'packages': sorted([worker.TARGET, worker.EXISTING_ACTIONS]), 'parent_app_scope': request['app_scope'],
            'install_or_signature_evidence': request['install_or_signature_evidence'],
            'output_scope': root+'/observed-app-scope.private.json', 'output_binding': root+'/qa-input.private.json'}
        observed = step('frozen_reader_run', lambda: reader.run(observed_request))
        need(observed['ok'] is True and observed['observation_fds']['remaining'] == 0 and
             observed['observation_fds']['errors'] == [] and
             observed['observation_fds']['acquired'] == observed['observation_fds']['closed'], 'READER_FDS_NOT_CLOSED')
        result['reader_result'] = observed
        observed_scope = step('read_observed_scope', lambda: core.parse(core.pinned_record(observed['app_scope'])))
        need(core.app_bytes(observed_scope['apps']) == core.app_bytes({name: scope['apps'][name]
            for name in (worker.TARGET, worker.EXISTING_ACTIONS)}), 'FRESH_OBSERVATION_CHANGED_APPS')
        gen_request = {'schema': 'pocket4-successor-qa-source-request-v1', 'qa_build_input': observed['qa_build_input'],
            'launcher_catalog': catalog_pin, 'package': worker.TARGET, 'component': component,
            'generation_nonce': nonce, 'public_text': worker.PUBLIC_TEXT, 'allowed_operations': worker.OPERATIONS,
            'output_root': '/home/alex/work/pocket4-successor-qa-source-'+nonce}
        generator.validate_request(gen_request)
        sources = step('generator_reference_closure', lambda: generator.reference_closure(worker.GENERATOR_MANIFEST['sha256']))
        derived, actual_guard, initial = step('generator_acquire_binding', lambda: generator.acquire_binding(gen_request))
        host, host_manifest = step('generator_render_host_only', lambda: generator.render_host(sources, derived))
        helper, helper_manifest, helper_name = step('generator_render_helper_only', lambda:
            generator.render_helper(sources, derived, sha(host_manifest), 'pocket4-successor-qa-build-'+nonce))
        result['pure_render'] = {'host_files': len(host), 'helper_files': len(helper),
            'host_manifest_bytes': len(host_manifest), 'host_manifest_sha256': sha(host_manifest),
            'helper_manifest_bytes': len(helper_manifest), 'helper_manifest_sha256': sha(helper_manifest),
            'helper_package_unpublished': helper_name, 'source_directory_created': False,
            'build_plan_published': False, 'generate_invoked': False}
        need(step('pure_render_guard_after', actual_guard.current_guard) == initial, 'RENDER_GUARD_CHANGED')
        step('pure_render_app_guard_after', lambda: actual_guard.check_app_scope(derived['app_scope'], sorted(derived['packages'])))
        step('generator_reference_closure_after', lambda: generator.reference_closure(worker.GENERATOR_MANIFEST['sha256']))
        step('old_Bili_unknown_after', lambda: native.original_unknown(core))
        need(step('protected_Meituan_after', lambda: native.protected_location(core, pool, held, scope['apps'])) == location,
             'MEITUAN_LOCATION_STATE_CHANGED')
        native_read('status')
        step('guard_full_app_scope_after', lambda: guard.check_app_scope(request['app_scope'], packages))
        step('current_46_apps_after', lambda: core.app_scope(pool, held, packages, scope['apps'], False))
        step('verify_runtime_after', lambda: core.verify_runtime(pool, held, baseline['runtime']))
        need(step('guard_after', guard.current_guard) == before, 'FINAL_RUNTIME_GUARD_CHANGED')
        step('original_failed_result_unchanged', lambda: worker.read_root_pin(FAILED_RESULT))
        for index, pin in enumerate((ORIGINAL_WORKER, worker.GUARD, worker.READER, worker.NATIVE_HELPERS,
                                     worker.GENERATOR, worker.GENERATOR_MANIFEST)):
            step('frozen_source_repin_'+str(index), lambda pin=pin: worker.read_root_pin(pin))
        need(not os.path.lexists(gen_request['output_root']) and not os.path.lexists(request['output_root']),
             'SOURCE_PUBLICATION_MUST_NOT_OCCUR')
        result['guard_after'] = before
        result['original_failed_result_unchanged'] = True
        result['ok'] = True
    except BaseException as error:
        result['errors'].append(error_record(error))
    finally:
        if lock is not None:
            try:
                monitor.verify_owned(lock, 'lease')
                fcntl.flock(lock, fcntl.LOCK_UN)
                result['action_lock_released'] = True
            except BaseException as error:
                result['ok'] = False; result['errors'].append({'stage': 'unlock', **error_record(error)})
        for label, group in (('observation_fds', pool), ('lease_fds', leases)):
            if group is not None:
                try:
                    group.close_all()
                except BaseException as error:
                    result['ok'] = False; result['errors'].append({'stage': label, **error_record(error)})
                result[label] = group.summary()
        try:
            monitor.check('after_explicit_owned_cleanup')
        except BaseException as error:
            result['ok'] = False; result['errors'].append({'stage': 'cleanup_check', **error_record(error)})
        result['baseline_descriptors'] = monitor.baseline
        result['first_descriptor_problem'] = monitor.first_problem
        result['phase_observations'] = monitor.events
        result['still_tracked_owned'] = monitor.owned
        result['status'] = ('FD_DIAGNOSTIC_COMPLETE_NO_QA_SOURCE_OR_RUNTIME_PASS' if result['ok'] else
                            'FD_DIAGNOSTIC_STOPPED_EVIDENCE_RETAINED_NO_RETRY')
    # Publication is host-only. The unknown descriptor, if any, remains open;
    # no diagnostic path attempts to close it or declares it harmless.
    if core is not None and root_identity is not None:
        try:
            final_before = fd_snapshot()
            raw = canonical(result)+b'\n'
            need(len(raw) <= 4*1024*1024, 'FD_REPORT_BOUND')
            report_fds = core.FDs()
            try:
                keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')
                current = core.open_host(report_fds, root, os.O_PATH|os.O_DIRECTORY)
                need(all(core.metadata(current)[k] == root_identity[k] for k in keys), 'REPORT_ROOT_CHANGED')
                report_pin = core.write_new(root+'/result.json', raw)
                need(core.pinned_record(report_pin, 4*1024*1024) == raw, 'FD_REPORT_READBACK')
                again = core.open_host(report_fds, root, os.O_PATH|os.O_DIRECTORY)
                need(all(core.metadata(again)[k] == root_identity[k] for k in keys), 'REPORT_ROOT_REPLACED')
            finally:
                report_fds.close_all()
            final_after = fd_snapshot()
            need({fd: identity(row) for fd, row in final_before['descriptors'].items()} ==
                 {fd: identity(row) for fd, row in final_after['descriptors'].items()}, 'REPORT_PUBLICATION_FD_DIFFERENCE')
            return {'schema': result['schema'], 'ok': result['ok'], 'status': result['status'],
                'result': report_pin, 'first_descriptor_problem': monitor.first_problem,
                'errors': result['errors'], 'phase_count': len(monitor.events),
                'observation_fds': result.get('observation_fds'), 'lease_fds': result.get('lease_fds'),
                'report_publication_FDs_unchanged': True, 'unknown_descriptors_closed': 0,
                'automatic_retry': False, 'generator_generate_calls': 0,
                'UI_actions': 0, 'installs': 0, 'builds': 0, 'production_ready': False}
        except BaseException as error:
            result['ok'] = False
            result['status'] = 'FD_DIAGNOSTIC_REPORT_INCOMPLETE_NO_RETRY'
            result['errors'].append({'stage': 'report_publication', **error_record(error)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnose-readonly-once', action='store_true', required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--request-sha256', required=True)
    parser.add_argument('--request-bytes', type=int, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        request = parse(root_pin({'path': args.request, 'bytes': args.request_bytes, 'sha256': args.request_sha256}))
        result = run(request)
    except BaseException as error:
        result = {'schema': 'pocket4-beike-source-fd-diagnostic-entry-rejection-v1', 'ok': False,
                  'error': error_record(error), 'automatic_retry': False, 'Main_commands': 0,
                  'UI_actions': 0, 'installs': 0, 'builds': 0, 'generator_generate_calls': 0}
    output = canonical(result)
    need(len(output) <= 4*1024*1024, 'STDOUT_BOUND')
    print(output.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
