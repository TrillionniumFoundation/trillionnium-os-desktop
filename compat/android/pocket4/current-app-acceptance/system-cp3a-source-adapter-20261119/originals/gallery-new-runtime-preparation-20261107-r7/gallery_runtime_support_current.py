"""Private fresh-Main Gallery ART/install transport.

The public capture and lifecycle helpers are used byte-for-byte. Extra file
descriptors are explicit held verifier inputs or two newly created outputs.
The package install has one durable intent and one O_RDONLY APK stdin dispatch.
Import performs no admission, namespace entry, package or UI action.
"""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import resource
import stat
import subprocess
import time
import types

FINAL = Path('/home/alex/work/pocket4-android-final')
ACTION_LOCK = '/run/lock/android-digitalis-actions.lock'
COMMON_REF = {'path': '/home/alex/work/pocket4-android-final/qualification/business-app-runtime-inputs-20261108-8b88-r2/source/app_common.py', 'bytes': 38256, 'sha256': '6003e96be02cd0c6328340865bbb2962d39967f2b823656af258ed5a48f598d0'}
APP_PREPARATION_REF = {'path': '/home/alex/work/pocket4-android-final/qualification/business-app-runtime-inputs-20261108-8b88-r2/preparation.json', 'bytes': 9820, 'sha256': '84eb5b4270846c65c199274e25309f8e7402332b21b53cbe3e8cfe445c30057f'}
APP_SOURCE_CONTROLS_REF = {'path': '/home/alex/work/pocket4-android-final/qualification/app-runtime-dependencies-20261108-8b88-r2/controls/result.json', 'bytes': 150113, 'sha256': '98aa2728d3463746a7f56afd948e6d780bc2f7c5210ab8eb7d6d89bea6c39815'}
APP_SOURCE_PUBLICATION_REF = {'path': '/home/alex/work/pocket4-android-final/qualification/app-runtime-dependencies-20261108-8b88-r2/publication-result.json', 'bytes': 8439, 'sha256': 'eb9a82f9efdcb810ef0ce74d2e285cb9d3e7ddd698188c912a90ddc33cf70d80'}
LEGACY_COMMON_PREPARATION_REF = {'bytes': 18468, 'path': '/home/alex/work/pocket4-android-final/qualification/business-app-preparation-frozen-resume-20261108-r4/preparation.json', 'sha256': 'e647e5dbb778ea1b22547b20776666ad2ad5c07f50ac7931953a3270b8644e3e'}
HELD_REF = {'path': str(FINAL / 'qualification/held_runtime.py'), 'bytes': 22691,
    'sha256': '72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4'}
ORIGINALS = {'install': {'bytes': 14935, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/source/gallery_qpr1_artifacts.py', 'sha256': '0ed255b0f6668fcb6f3feae6c8ad2456e3540fbb184fa4522e2d8b58b0d961b8'}, 'identity': {'bytes': 15822, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/source/gallery_identity_qpr1.py', 'sha256': '77a4468baa0adfe88fbd0d9b2e74a66137e4f7a59f10e1de5d5a2549a9b0e3ee'}, 'stdin': {'bytes': 9258, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/source/gallery_stdin_qpr1.py', 'sha256': '26a5667f2d2fb62545a6e7b222fdeb313748e7e2590373ae69f6eeb36b1b3d3c'}, 'context': {'bytes': 2940, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/source/gallery_context_qpr1.py', 'sha256': 'fb91989c0081a6ddbd08ab5f61cff86db529c9729d6ed2fad9f7f90b3f06d8f3'}, 'dex': {'bytes': 2108, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/source/dex_class_table_qpr1.py', 'sha256': 'c636141cef2cb709360c0b085b4bc18e0654cc78641d188931892c69f553be48'}}
PACKAGE = 'com.android.gallery3d'
DEX2OAT = '/apex/com.android.art/bin/dex2oat64'
OATDUMP = '/apex/com.android.art/bin/oatdump'
ANALYZER = '/apex/com.android.art/bin/dexoptanalyzer'
APK_SHA = '6677d382076f10f0502c813c7614c32127ccf3cd8f02756b75a8c3574980e87e'
APK_BYTES = 7493022
PM_ARGV = ['/system/bin/pm', 'install', '-r', '--restrict-permissions', '--user', '0',
           '-S', str(APK_BYTES), '-']
READS = (
    ['/system/bin/dumpsys', 'package', PACKAGE],
    ['/system/bin/pm', 'path', '--user', '0', PACKAGE],
    ['/system/bin/pm', 'path', PACKAGE],
    ['/system/bin/cmd', 'activity', 'stack', 'list'],
    ['/system/bin/cmd', 'package', 'resolve-activity', '--brief', '--user', '0',
     '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.HOME'],
    ['/system/bin/cmd', 'overlay', 'lookup', '--user', '0', 'android',
     'android:array/config_sharedLibrariesLoadedAfterApp'],
)
META_KEYS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
             'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def metadata(value):
    return {key: getattr(value, key) for key in META_KEYS}


def bootstrap():
    fd = os.open(COMMON_REF['path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd); raw = os.pread(fd, COMMON_REF['bytes'] + 1, 0)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and len(raw) == COMMON_REF['bytes'] and sha(raw) == COMMON_REF['sha256']
             and metadata(before) == metadata(os.fstat(fd)) == metadata(os.lstat(COMMON_REF['path'])),
             'FROZEN_COMMON_SOURCE_CHANGED')
    finally:
        os.close(fd)
    common = types.ModuleType('gallery_current_final_common'); common.__file__ = COMMON_REF['path']
    exec(compile(raw, COMMON_REF['path'], 'exec'), common.__dict__)
    prep = common.parse(common.read_ref(APP_PREPARATION_REF))
    legacy = common.parse(common.read_ref(LEGACY_COMMON_PREPARATION_REF))
    legacy_common = [ref for ref in legacy['files'] if Path(ref['path']).name == 'app_common.py']
    need(legacy['schema'] == 'pocket4-final-app-preparation-source-v1'
         and legacy['code_entrypoints_complete'] is True and legacy['host_controls_qualified'] is True
         and len(legacy_common) == 1 and legacy_common[0]['bytes'] == COMMON_REF['bytes']
         and legacy_common[0]['sha256'] == COMMON_REF['sha256']
         and common.read_ref(legacy_common[0]) == raw,
         'ORIGINAL_QUALIFIED_COMMON_BYTES_MUST_REMAIN_IDENTICAL')
    need(prep['schema'] == 'pocket4-final-app-preparation-source-v1'
         and prep['code_entrypoints_complete'] is True and COMMON_REF in prep['files']
         and prep['source_graph_generation'] == '20261108-8b88-r2'
         and prep['host_controls_qualified'] is False and prep['prior_host_control_credit_transferred'] is False
         and prep['historical_runtime_authority_transferred'] is False
         and prep['runtime_qualified'] is False and prep['whole_app_accepted_count'] == 0,
         'EXACT_CURRENT_SOURCE_PREPARATION_WITH_NO_TRANSFERRED_RUNTIME_CREDIT')
    publication = common.parse(common.read_ref(APP_SOURCE_PUBLICATION_REF))
    selected = [row for row in publication['preparations'] if row['kind'] == 'app']
    controls = common.parse(common.read_ref(APP_SOURCE_CONTROLS_REF))
    app_cases = [row for row in controls['cases'] if row['kind'] == 'app']
    need(publication['schema'] == 'runtime-source-migration-publication-v1'
         and len(selected) == 1 and selected[0]['new_preparation'] == APP_PREPARATION_REF
         and controls['schema'] == 'actual-current-source-Witness-controls-v1'
         and controls['publication'] == APP_SOURCE_PUBLICATION_REF
         and controls['passed'] is True and controls['total'] == controls['passed_count'] == 30
         and controls['old_root_opens'] == 0
         and controls['source_subtrees_use_actual_frozen_source_and_unmodified_Witness'] is True
         and controls['full_Main_execute_or_full_runtime_seed_executed'] is False
         and controls['actual_Main_receipts_fabricated'] is False
         and controls['Main_actions'] == controls['Android_actions'] == controls['runtime_acceptance_count'] == 0
         and len(app_cases) == 5 and all(row['passed'] is True and row['exit_code'] == 0
             and row['old_root_opens'] == 0 and not row['denied'] for row in app_cases)
         and {row['mode'] for row in app_cases} == {'bootstrap_and_module_import',
             'wrong_external_preparation_pin', 'Witness_actual_source_subtree',
             'Witness_wrong_actual_input_pin', 'business_required_proof_leaves'},
         'ACTUAL_SELECTED_R2_CURRENT_SOURCE_CLOSURE_CONTROLS_REQUIRED')
    for reference in prep['files'] + prep['origins']:
        common.read_ref(reference)
    originals = {name: common.module(ref, 'gallery_current_original_' + name)
                 for name, ref in ORIGINALS.items()}
    held = common.module(HELD_REF, 'gallery_current_held_namespace')
    return common, originals, held


def resources():
    current = Path('/proc/self/cgroup').read_text().strip()
    need(current.startswith('0::/') and current != '0::/', 'OWN_BOUNDED_RESOURCE_SCOPE_REQUIRED')
    group = Path('/sys/fs/cgroup') / current[3:].lstrip('/')
    values = {key: (group / key).read_text().strip()
              for key in ('cpu.max', 'memory.max', 'memory.swap.max', 'pids.max')}
    quota, period = map(int, values['cpu.max'].split())
    need(0 < quota <= 2 * period and values['memory.max'].isdigit()
         and 0 < int(values['memory.max']) <= 2 * 1024**3 and values['memory.swap.max'] == '0'
         and values['pids.max'] == '64' and (group / 'memory.swap.current').read_text().strip() == '0'
         and os.sched_getaffinity(0) <= {20, 21}
         and resource.getrlimit(resource.RLIMIT_CORE) == (0, 0), 'OWN_RESOURCE_LIMIT_CHANGED')
    events = {key: int(value) for key, value in
              (line.split() for line in (group / 'memory.events').read_text().splitlines())}
    need(all(events.get(key, 0) == 0 for key in ('oom', 'oom_kill', 'oom_group_kill')),
         'OWN_GALLERY_RESOURCE_OOM')
    return {'cgroup': current, 'limits': values, 'affinity': sorted(os.sched_getaffinity(0)),
        'memory_events': events, 'memory_peak_bytes': int((group / 'memory.peak').read_text()),
        'swap_current_bytes': int((group / 'memory.swap.current').read_text())}


def pin_fd(fd, *, maximum=256 * 1024 * 1024, contents=False):
    before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum,
         'REGULAR_BOUNDED_HELD_FILE_REQUIRED')
    digest = hashlib.sha256(); offset = 0; chunks = []
    while offset < before.st_size:
        part = os.pread(fd, min(1048576, before.st_size - offset), offset)
        need(part, 'HELD_FILE_SHORT_READ'); offset += len(part); digest.update(part)
        if contents:
            chunks.append(part)
    need(os.pread(fd, 1, offset) == b'' and metadata(os.fstat(fd)) == metadata(before),
         'HELD_FILE_CHANGED_DURING_READ')
    result = {'bytes': offset, 'sha256': digest.hexdigest(), 'identity': metadata(before)}
    return (result, b''.join(chunks)) if contents else result


class Session:
    """Current baseline, held init and system_server; fixed commands only."""
    def __init__(self, common, held, request, root, deadline):
        self.common = common; self.held = held; self.root = Path(root); self.deadline = deadline
        self.view = self.peer = None; self.closed = False; self.plans = {}; self.claimed = set()
        self.install_attempted = False; self.install_pending = False; self.outcome_unknown = False
        self.sequence = 0; self.records = []
        qualification = common.parse(common.read_ref(request['qualification'], 131072))
        need(qualification['source_manifest'] == common.SUPPORT_REF, 'EXACT_R5_BUSINESS_COHORT_REQUIRED')
        journal = self.root / 'journal'; common.private_dir(journal, create=True)

        def admit(argv, timeout, root_read, private):
            need(argv in READS and not root_read and not private and 5 < timeout <= 20,
                 'EXACT_GALLERY_METADATA_QUERY_ONLY')

        try:
            self.view = common.MainView(request['baseline'], request['qualification'], journal, admit,
                                        support_ref=common.SUPPORT_REF)
            self.target = self.view.target; self.environment = self.view.environment
            self.baseline = self.view.baseline; self.commands = self.view.commands
            identity = self.baseline.value['framework_epoch']['binding']['processes']['system_server']
            self.peer = held.HeldZygoteRoot(identity, deadline)
            self.guard()
        except BaseException:
            self.close()
            raise

    def guard(self, *, action_attempted=False):
        need(not self.closed and time.monotonic() < self.deadline, 'GALLERY_ABSOLUTE_DEADLINE_OR_CLOSED')
        result = self.view.guard(action_attempted=action_attempted)
        if self.peer is not None:
            self.peer.verify()
        need(time.monotonic() < self.deadline, 'GALLERY_GUARD_EXHAUSTED_DEADLINE')
        return result

    def android(self, argv, timeout=15):
        self.guard()
        remaining = self.deadline - time.monotonic() - 8
        bounded = min(timeout, remaining)
        need(5 < bounded <= 20, 'NO_METADATA_TIME_BEFORE_RETIRED_TAIL')
        raw, record = self.view.command(argv, bounded)
        self.records.append({'metadata_query': record})
        self.guard()
        return raw

    def paired_file(self, path, *, contents=False, maximum=256 * 1024 * 1024):
        self.peer.verify()
        # The fixed Android tool paths can be symlinks to toybox. The original
        # held reader resolves them with IN_ROOT | NO_MAGICLINKS in each root.
        fd = self.target.open_root(path, os.O_RDONLY)
        other = -1
        try:
            other = self.peer.open_root(path, os.O_RDONLY)
            value = pin_fd(fd, maximum=maximum, contents=contents)
            row = value[0] if contents else value
            need(metadata(os.fstat(other)) == row['identity'], 'INIT_SYSTEMSERVER_CODE_BACKING_DIFFERS')
            again = self.target.open_root(path, os.O_RDONLY)
            try:
                need(metadata(os.fstat(again)) == row['identity'], 'GUEST_CODE_PATH_REPLACED')
            finally:
                os.close(again)
            self.peer.verify()
            need(time.monotonic() < self.deadline, 'GALLERY_PAIRED_READ_EXHAUSTED_DEADLINE')
            return value
        finally:
            if other >= 0:
                os.close(other)
            os.close(fd)

    def register(self, kind, argv, *, extras=(), writable=(), timeout=40, expected_rc=0,
                 stdin_held=None):
        allowed = {'flatten', 'verifier-fd-proof', 'compiler', 'all-class-status',
                   'method-exif', 'method-operation', 'install'}
        need(kind in allowed and kind not in self.plans and kind not in self.claimed,
             'EXACT_SINGLE_COMMAND_KIND')
        need(type(argv) is list and argv and all(type(x) is str and x and '\0' not in x for x in argv),
             'CONSTRUCTED_FIXED_COMMAND_ARGV_REQUIRED')
        need(5 < timeout <= 90 and expected_rc == (50 if kind == 'flatten' else 0),
             'FIXED_COMMAND_RETURN_AND_TIME_CONTRACT')
        if kind == 'flatten':
            need(argv[:2] == [ANALYZER, '--flatten-class-loader-context'] and len(argv) == 3
                 and argv[2].startswith('--class-loader-context=PCL[]{') and not extras,
                 'EXACT_CONTEXT_FLATTEN_COMMAND')
        elif kind == 'compiler':
            need(argv[0] == DEX2OAT and '--compiler-filter=verify' in argv
                 and '--abort-on-hard-verifier-error' in argv and '--abort-on-soft-verifier-error' in argv
                 and '--copy-dex-files=always' in argv and argv[-1] == '-j2',
                 'EXACT_CANDIDATE_VERIFIER_FLAGS')
        elif kind in {'all-class-status', 'method-exif', 'method-operation'}:
            need(argv[0] == OATDUMP and '--no-disassemble' in argv and '--no-dump:vmap' in argv,
                 'EXACT_READ_ONLY_OATDUMP_FLAGS')
            selector = {'all-class-status': '--list-classes',
                'method-exif': '--class-filter=com.android.gallery3d.exif.ExifInterface',
                'method-operation': '--class-filter=com.android.gallery3d.ui.MenuExecutor$MediaOperation'}[kind]
            need(argv[-1] == selector and sum(a.startswith('--class-filter=') for a in argv)
                 == (0 if kind == 'all-class-status' else 1), 'EXACT_OATDUMP_SELECTOR')
        elif kind == 'verifier-fd-proof':
            need(argv[:2] == ['/system/bin/sh', '-c'] and len(argv) == 3
                 and argv[2].startswith('set -eu\n/system/bin/id -u\n/system/bin/toybox stat '),
                 'EXACT_INHERITED_FD_PROOF')
        else:
            need(argv == PM_ARGV and timeout == 60 and not extras and not writable
                 and stdin_held is not None and stdin_held.verify()['sha256'] == APK_SHA,
                 'EXACT_SINGLE_PM_STDIN_INSTALL_REQUIRED')
        need(len(extras) == len(set(extras)) and set(writable) <= set(extras)
             and len(writable) in (0, 2) and len(extras) <= 64,
             'EXPLICIT_DISTINCT_VERIFIER_DESCRIPTOR_SET')
        rows = []
        for fd in extras:
            need(type(fd) is int and fd > 2, 'OWN_EXTRA_DESCRIPTOR_REQUIRED')
            info = os.fstat(fd); access = fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE
            need(access == (os.O_RDWR if fd in writable else os.O_RDONLY), 'EXTRA_FD_ACCESS_CHANGED')
            if fd in writable:
                need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == 2000,
                     'NEW_OWNED_VERIFIER_OUTPUT_ONLY')
            rows.append({'fd': fd, 'identity': metadata(info), 'writable': fd in writable,
                         'access': access})
        self.plans[kind] = {'argv': tuple(argv), 'extras': tuple(extras), 'writable': tuple(writable),
            'timeout': timeout, 'expected_rc': expected_rc, 'stdin': stdin_held, 'fd_rows': rows}

    def run(self, kind):
        need(kind in self.plans and kind not in self.claimed, 'COMMAND_NOT_REGISTERED_OR_ALREADY_CLAIMED')
        plan = self.plans[kind]; mutation = kind == 'install'; before = self.guard()
        self.claimed.add(kind); self.sequence += 1
        name = '%03d-%s' % (self.sequence, kind); journal = self.root / 'journal'
        now = time.monotonic(); execution_end = min(now + plan['timeout'], self.deadline - 30)
        need(execution_end > now + 5, 'NO_COMMAND_TIME_BEFORE_RETIRED_TAIL')
        chain = ['/system/bin/env', '-i'] + [k + '=' + self.environment[k] for k in sorted(self.environment)]
        chain += ['/system/xbin/su', '2000', '/system/bin/timeout', '-k', '2',
                  str(max(1, int(execution_end - now) - 5)), *plan['argv']]
        result = {'schema': 'pocket4-gallery-current-owned-command-v1', 'kind': kind,
            'android_argv': list(plan['argv']), 'before': before, 'after': None,
            'mutation': mutation, 'automatic_retry': False, 'lease_released': False,
            'host_retirement_proved': False, 'complete': False, 'errors': []}
        capture = self.commands.load_capture()
        reaper = capture.OwnChildReaper(protected_pids=self.baseline.protected_pids)
        cancel = self.commands.Cancellation(); began = False; first = None; finish_error = None
        record = {}; stdout = stderr = None
        try:
            with self.target.entry(chain) as (physical, authority):
                descriptors = (*authority, *plan['extras'])
                need(len(authority) == 7 and len(descriptors) == len(set(descriptors)), 'HELD_AUTHORITY_FD_ALIAS')
                for row in plan['fd_rows']:
                    actual = metadata(os.fstat(row['fd']))
                    if row['writable']:
                        need(all(actual[k] == row['identity'][k] for k in
                            ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink')),
                             'OWNED_OUTPUT_FD_REPLACED')
                    else:
                        need(actual == row['identity'], 'READ_ONLY_INPUT_FD_CHANGED')
                held = plan['stdin']
                stdin_proof = held.verify() if held is not None else None
                if mutation:
                    need(not self.install_attempted and not self.install_pending and not self.outcome_unknown,
                         'INSTALL_ALREADY_ATTEMPTED_OR_UNKNOWN')
                    self.install_attempted = self.install_pending = self.outcome_unknown = True
                    self.common.write_new(self.root / 'install-pending.json', {
                        'schema': 'pocket4-gallery-current-install-pending-v1',
                        'candidate_sha256': APK_SHA, 'stdin': stdin_proof, 'argv': PM_ARGV,
                        'main_guard': before, 'single_dispatch': True, 'automatic_retry': False})
                self.common.write_new(journal / (name + '.intent.json'), {
                    'kind': kind, 'argv': list(physical), 'android_argv': list(plan['argv']),
                    'authority_fds': list(authority), 'extra_fds': plan['fd_rows'],
                    'stdin': stdin_proof, 'execution_deadline_monotonic': execution_end,
                    'retirement_deadline_monotonic': execution_end + 8,
                    'output_bound_per_stream': 16 * 1024 * 1024, 'before': before,
                    'public_capture_sha256': self.commands.CAPTURE_SHA, 'automatic_retry': False})
                cancel.begin(); reaper.begin(); began = True

                def factory(input_fd, output_fd, error_fd, bound):
                    need(time.monotonic() < execution_end, 'SPAWN_AFTER_ABSOLUTE_DEADLINE')
                    if held is not None:
                        need(held.verify() == stdin_proof, 'INSTALL_STDIN_CHANGED_BEFORE_SPAWN')
                        os.lseek(held.fd, 0, os.SEEK_SET)
                    def core_only():
                        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                    return subprocess.Popen(list(physical), stdin=held.fd if held is not None else input_fd,
                        stdout=output_fd, stderr=error_fd, env=self.common.HOST_ENV,
                        close_fds=True, pass_fds=descriptors, start_new_session=True, preexec_fn=core_only)

                record, stdout, stderr, first = capture.invoke_owned(reaper, factory, b'', execution_end,
                    execution_end + 8, output_bound=16 * 1024 * 1024,
                    cleanup_enter=cancel.enter_retirement, retirement_grace=5)
                cancel.enter_retirement()
                try:
                    reaper.finish()
                except BaseException as error:
                    finish_error = error
                began = False
                result['host_retirement_proved'] = self.commands.retirement_complete(record, reaper.record, finish_error)
                if not result['host_retirement_proved']:
                    self.target.poison_unjoined_command()
                    raise RuntimeError('OWN_COMMAND_TREE_NOT_RETIRED')
                if held is not None:
                    need(held.verify() == stdin_proof, 'INSTALL_STDIN_CHANGED_AFTER_COMMAND')
                    result['stdin_after'] = held.verify()
                    result['stdin_offset_after'] = os.lseek(held.fd, 0, os.SEEK_CUR)
            result['lease_released'] = True
        except BaseException as error:
            first = first or error
            result['errors'].append({'stage': 'held_command', 'type': type(error).__name__, 'message': str(error)})
        finally:
            cancel.enter_retirement()
            if began:
                try:
                    reaper.finish()
                except BaseException as error:
                    finish_error = finish_error or error
                    result['errors'].append({'stage': 'reaper_finish', 'type': type(error).__name__, 'message': str(error)})
            try:
                cancel.restore()
            except BaseException as error:
                finish_error = finish_error or error
                result['errors'].append({'stage': 'signal_restore', 'type': type(error).__name__, 'message': str(error)})
            result['host_retirement_proved'] = self.commands.retirement_complete(record, reaper.record, finish_error)
            if record.get('child_started') and not result['host_retirement_proved']:
                self.target.poison_unjoined_command()
            try:
                result['after'] = self.guard(action_attempted=mutation and record.get('child_started', False))
            except BaseException as error:
                result['errors'].append({'stage': 'post_guard', 'type': type(error).__name__, 'message': str(error)})
            result.update(lifecycle=record, subreaper=dict(reaper.record),
                cancellation={'count': cancel.count, 'signals': cancel.signals})
        for label, raw in (('stdout', stdout), ('stderr', stderr)):
            if type(raw) is bytes:
                result[label] = self.common.write_new(journal / (name + '.' + label), raw)
        expected_exit_only = (record.get('returncode') == plan['expected_rc']
            and (record.get('first_error') or {}).get('stage') == 'child_exit'
            and not record.get('secondary_errors') and record.get('output_capture', {}).get('complete') is True)
        if first is not None and not expected_exit_only:
            result['errors'].append({'stage': 'first_error', 'type': type(first).__name__, 'message': str(first)})
        result['complete'] = (result['host_retirement_proved'] and result['lease_released']
            and result['after'] == before and not result['errors'] and cancel.count == 0
            and record.get('returncode') == plan['expected_rc'] and not record.get('timed_out')
            and type(stdout) is bytes and type(stderr) is bytes)
        ref = self.common.write_new(journal / (name + '.result.json'), result)
        self.records.append({'kind': kind, 'receipt': ref, 'complete': result['complete']})
        need(result['complete'], 'CURRENT_GALLERY_COMMAND_FAILED:' + kind)
        return stdout, stderr, ref

    def close(self):
        if self.closed:
            return
        failures = []
        if self.peer is not None:
            try:
                self.peer.close()
            except BaseException as error:
                failures.append('peer:' + repr(error))
        if self.view is not None:
            try:
                self.view.close()
            except BaseException as error:
                failures.append('MainView:' + repr(error))
        self.closed = not failures
        need(not failures, 'CURRENT_GALLERY_HELD_FD_CLOSE_FAILED:' + repr(failures))
