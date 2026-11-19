"""Fresh final Main, one action-lock OFD and original Gallery task ownership.

All children use the unchanged qualified bounded capture and OwnChildReaper.
The old CameraSession, activation and numeric process IDs are never executed.
"""
import base64
import copy
import fcntl
import inspect
import os
from pathlib import Path
import re
import stat
import time
import types

ACTION_LOCK = '/run/lock/android-digitalis-actions.lock'
GALLERY = 'com.android.gallery3d'
PACKAGE = 'org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03'
NATIVE = 'local.pocket4.actions.v2'
GALLERY_SHA = '6677d382076f10f0502c813c7614c32127ccf3cd8f02756b75a8c3574980e87e'
NATIVE_SHA = 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'


def birth(info):
    return {k: getattr(info, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink')}


class ActionLock:
    def __init__(self, c, root):
        self.c = c; self.fd = None; self.closed = False; self.owner = os.getpid()
        try:
            self.fd = os.open(ACTION_LOCK, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
            self.identity = birth(os.fstat(self.fd)); self._check()
            self.ref = c.write_new(root / 'action-lock.json', {'schema': 'pocket4-gallery-rotation-action-lock-v1',
                'path': ACTION_LOCK, 'owner_pid': self.owner, 'file': self.identity,
                'same_process_one_open_file_description': True, 'transferred_descriptors': 0,
                'automatic_retry': False})
        except BaseException:
            self.close(); raise

    def _check(self):
        self.c.need(not self.closed and self.fd is not None and os.getpid() == self.owner,
                    'SAME_GALLERY_ACTION_LOCK_OWNER_REQUIRED')
        info = os.fstat(self.fd)
        self.c.need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
            and self.identity == birth(info) == birth(os.lstat(ACTION_LOCK))
            and not os.get_inheritable(self.fd), 'SAME_GALLERY_ACTION_LOCK_OFD_REQUIRED')
        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def verify(self):
        self._check(); self.c.read_ref(self.ref)

    def close(self):
        if self.fd is not None:
            os.close(self.fd); self.fd = None
        self.closed = True


class Evidence:
    def __init__(self, session):
        self.s = session; self.ALEX_PREFIX = list(session.c.NATIVE_PREFIX)
        self.MAIN_HOST = session.baseline.docs['final_baseline']['daemon_status']['host_pid']

    def write_new(self, path, value, **options):
        s = self.s; path = Path(path)
        s.c.need(not set(options) - {'alex_readable'} and path.is_relative_to(s.root)
            and path.parent.resolve() == path.parent, 'ONLY_THIS_FRESH_GALLERY_CASE_EVIDENCE')
        raw = value if type(value) is bytes else s.c.canonical(value)
        s.c.need(len(raw) <= (33554432 if path.suffix == '.png' else 16777216), 'ORIGINAL_EVIDENCE_BOUND')
        ref = s.c.write_new(path, raw)
        if type(value) is dict:
            s.note_original_record(ref, value)
        return ref

    def read_regular(self, path, expected, maximum):
        s = self.s; package = s.components['rotation_package.py']
        s.c.need(Path(path) == package.APK and expected == package.APK_SHA and maximum == 1048576,
                 'ONLY_ORIGINAL_OWNED_HELPER_APK_HOST_READ')
        raw, ref = s.c.regular(path, maximum)
        s.c.need(ref['sha256'] == expected and len(raw) == 24780, 'ORIGINAL_FIXTURE_APK_CHANGED')
        return raw


class TargetReads:
    def __init__(self, session):
        self.s = session

    def read_file(self, path, maximum, **options):
        s = self.s; s.guard(); policy = s.components['gallery_rotation_policy.py']
        media = s.components['owned_media.py']; package = s.components['rotation_package.py']
        wanted = [(pkg, value) for pkg, value in s.apk_paths.items() if value == path]
        expected = None
        if wanted:
            s.c.need(len(wanted) == 1 and maximum == 16777216, 'ONE_ACTUAL_ORIGINAL_INSTALLED_APK_PATH')
            expected = {GALLERY: GALLERY_SHA, NATIVE: NATIVE_SHA, PACKAGE: package.APK_SHA}[wanted[0][0]]
        elif path == media.PROVIDER_APK:
            s.c.need(maximum == 16777216, 'ORIGINAL_PROVIDER_APK_BOUND'); expected = media.PROVIDER_SHA
        elif path == policy.STAGE:
            s.c.need(maximum == 1048576 and s.case is not None and s.case.pkg.staged is not None,
                     'ONLY_THIS_CREATE_ONLY_STAGED_HELPER_APK'); expected = package.APK_SHA
        else:
            s.c.need(path == '/data/user/0/' + PACKAGE + '/shared_prefs/owned-rotation-' + policy.RUN + '.xml'
                and maximum == 65536 and s.case is not None and s.case.pkg.installed is not None,
                'ONLY_ORIGINAL_OWNED_FIXTURE_PRIVATE_STATE')
        s.c.need(options == {'single_link': True}, 'ORIGINAL_SINGLE_LINK_DATA_READ_REQUIRED')
        raw, metadata = s.view.target.read_file(path, maximum, **options)
        if expected is not None:
            s.c.need(s.c.sha(raw) == expected, 'EXACT_ORIGINAL_OR_CURRENT_GALLERY_APK_BYTES_REQUIRED')
        if path == media.PROVIDER_APK:
            s.c.need(len(raw) == media.PROVIDER_BYTES, 'ORIGINAL_MEDIA_PROVIDER_SIZE')
        s.guard(); return raw, metadata

    def open_root(self, path, flags):
        s = self.s; s.guard()
        paths = {'/storage/emulated/0/DCIM', '/data/media/0/DCIM', '/data/local/tmp'}
        paths |= {'/data/' + prefix + '/0/' + pkg for pkg in (GALLERY, PACKAGE, NATIVE)
                  for prefix in ('user', 'user_de')}
        s.c.need(path in paths and flags == os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                 'ONLY_ORIGINAL_EXACT_DIRECTORY_FD_SCOPE')
        return s.view.target.open_root(path, flags | os.O_CLOEXEC)


class Session:
    def __init__(self, c, support, held, request, root, components, action_lock, install,
                 source_guard, prior_ref, business_deadline):
        self.c = self.common = c; self.support = support; self.held = held
        self.request = request; self.root = Path(root); self.components = components
        self.action_lock = action_lock; self.install = install; self.install_ref = request['installation']
        self.source_guard = source_guard; self.prior_ref = prior_ref
        self.business_deadline = self.deadline = business_deadline; self.phase = 'business'
        self.closed = False; self.view = self.peer = self.helper = self.case = None
        self.command_index = self.api_sequence = 0; self.records = []; self.intents = []; self.used_intents = set()
        self.active_api = None; self.ui_owner = None; self.last_focus = self.last_stacks = None
        self.claimed_tasks = {}; self.launch_receipts = {}; self.native_launches = 0
        self.apk_paths = {GALLERY: install['gallery_after']['apk']['path']}
        self.pm_help_ref = None; self.pm_help_reading = False; self.possible_effect = False
        self.allowed_ui_packages = {GALLERY, PACKAGE}; self.host_cancelled = False; self.host_retirement_unknown = False
        self.source_paths = {key: value.__file__ for key, value in components.items()}
        self.journal = c.private_dir(self.root / 'commands', create=True)
        self.api_root = c.private_dir(self.root / 'api', create=True)
        self.phase_ref = c.write_new(self.root / 'phase-business.json', {
            'schema': 'pocket4-gallery-rotation-phase-v1', 'phase': self.phase,
            'baseline': request['baseline'], 'qualification': request['qualification'],
            'installation': self.install_ref, 'owner_pid': os.getpid(),
            'deadline_monotonic': self.deadline, 'business_seconds': 600, 'cleanup_seconds': 120})
        try:
            def no_view_dispatch(*unused):
                raise RuntimeError('ALL_GALLERY_COMMANDS_REQUIRE_PRIVATE_TYPED_TRANSPORT')
            self.view = c.MainView(request['baseline'], request['qualification'], self.journal,
                                   no_view_dispatch, support_ref=c.SUPPORT_REF)
            self.baseline = self.view.baseline; self.environment = self.view.environment
            self.commands = self.view.commands; self.scope_module = self.view.scope
            identity = self.baseline.value['framework_epoch']['binding']['processes']['system_server']
            self.peer = held.HeldZygoteRoot(identity, self.deadline)
            self.target = TargetReads(self); self.tx = Evidence(self)
            self.policy = components['gallery_rotation_policy.py'].Policy(self)
            self.guard()
            self.helper = components['gallery_rotation_api.py'].OriginalAPIs(self)
        except BaseException:
            self.close(); raise

    def guard(self, *, action_attempted=False):
        self.c.need(not self.closed and not self.host_retirement_unknown and time.monotonic() < self.deadline,
                    'GALLERY_ORIGINAL_PHASE_EXPIRED_CLOSED_OR_UNRETIRED')
        self.action_lock.verify(); self.source_guard()
        value = self.view.guard(action_attempted=action_attempted)
        if self.peer is not None:
            self.peer.verify()
        self.c.need(time.monotonic() < self.deadline, 'GALLERY_GUARD_EXHAUSTED_ORIGINAL_PHASE')
        return value

    def begin_cleanup(self, trigger):
        self.c.need(self.phase == 'business' and self.active_api is None, 'ONCE_GALLERY_FINAL_CLEANUP_PHASE')
        self.phase = 'final_cleanup'; self.deadline = min(time.monotonic() + 120, self.business_deadline + 120)
        self.c.need(time.monotonic() < self.deadline, 'NO_GALLERY_CLEANUP_AFTER_ABSOLUTE_BOUND')
        self.peer.deadline = self.deadline
        self.phase_ref = self.c.write_new(self.root / 'phase-final-cleanup.json', {
            'schema': 'pocket4-gallery-rotation-phase-v1', 'phase': self.phase,
            'trigger': trigger, 'owner_pid': os.getpid(), 'business_deadline_monotonic': self.business_deadline,
            'deadline_monotonic': self.deadline, 'cleanup_seconds': 120, 'automatic_retry': False})

    def original_caller(self, names, methods=None, skip=()):
        frame = inspect.currentframe()
        try:
            for _ in range(18):
                frame = frame.f_back
                if frame is None:
                    break
                for name in names:
                    if frame.f_code.co_filename == self.source_paths.get(name) and frame.f_code.co_name not in skip:
                        self.c.need(methods is None or frame.f_code.co_name in methods, 'EXACT_ORIGINAL_GALLERY_METHOD_REQUIRED')
                        return {'source': name, 'function': frame.f_code.co_name}
            raise RuntimeError('GALLERY_API_CALLER_IS_NOT_FROZEN_ORIGINAL_CASE')
        finally:
            del frame

    def note_original_record(self, ref, value):
        caller = self.original_caller(['rotation_ui.py', 'gallery_rotation_flow.py', 'owned_media.py', 'rotation_package.py', 'bounded_diagnostics.py'], skip=('record',))
        if caller == {'source': 'rotation_ui.py', 'function': 'focus'} and set(value) == {'focus', 'raw'}:
            self.last_focus = copy.deepcopy(value['focus'])
        if caller == {'source': 'rotation_ui.py', 'function': 'bind_gallery_route'} and 'actual_activity_block' in value:
            self.record_route_claim(ref, value)
        if value.get('automatic_retry') is False and (type(value.get('argv')) is list
                or type(value.get('request')) is dict or value.get('method') == 'normal exact owned leaf remove'
                or value.get('package') == PACKAGE and 'identity' in value):
            self.intents.append({'ref': ref, 'value': copy.deepcopy(value), 'caller': caller, 'phase': self.phase_ref})

    def consume_intent(self, kind, argv_or_request):
        matches = []
        for item in self.intents:
            if item['ref']['path'] in self.used_intents or item['phase'] != self.phase_ref:
                continue
            value = item['value']; wanted = value.get('argv', value.get('request'))
            if kind == 'task-remove' and value.get('method') == 'normal exact owned leaf remove':
                wanted = ['/system/bin/cmd', 'activity', 'stack', 'remove', str(value['task'])]
            if kind == 'helper-uninstall' and value.get('package') == PACKAGE and 'identity' in value:
                wanted = ['/system/bin/pm', 'uninstall', PACKAGE]
            if wanted == argv_or_request:
                matches.append(item)
        self.c.need(len(matches) == 1, 'ONE_CURRENT_ORIGINAL_DURABLE_INTENT_REQUIRED:' + kind)
        item = matches[0]; self.c.read_ref(item['ref']); self.used_intents.add(item['ref']['path'])
        self.c.write_new(self.journal / ('once-%04d.json' % len(self.used_intents)), {
            'kind': kind, 'intent': item['ref'], 'original_caller': item['caller'],
            'phase': self.phase_ref, 'automatic_retry': False})
        return item

    def _transport(self, label, logical, timeout, *, mutation=False, image=False, root=False):
        self.guard(); remaining = self.deadline - time.monotonic() - 8
        if mutation or root:
            self.c.need(remaining >= timeout, 'FULL_ORIGINAL_MUTATION_OR_ROOT_TIME_REQUIRED')
            bounded = timeout
        else:
            bounded = min(timeout, remaining)
        self.c.need(bounded > 5, 'NO_COMMAND_AFTER_ORIGINAL_RETIREMENT_TAIL')
        self.command_index += 1; name = 'command-%05d' % self.command_index
        inner = 10 if root else bounded - 4
        command = ['/system/bin/env', '-i'] + [k + '=' + self.environment[k] for k in sorted(self.environment)]
        if not root:
            command += ['/system/xbin/su', '2000']
        command += ['/system/bin/timeout', '-k', '2', str(inner), *logical]
        self.c.write_new(self.journal / (name + '.logical.json'), {'argv': logical,
            'original_timeout': timeout, 'actual_timeout': bounded, 'inner_timeout': inner,
            'original_camera_T_minus_4_preserved': not root, 'original_root_10_plus_2_over_14': root,
            'Android_mutation': mutation, 'phase': self.phase_ref, 'label': label, 'automatic_retry': False})
        entered = released = False; completed = primary = None; post = None
        manager = self.view.target.entry(command)
        try:
            physical, fds = manager.__enter__(); entered = True
            self.c.need(len(fds) == len(set(fds)) == 7, 'EXACT_CURRENT_HELD_AUTHORITY_FDS')
            completed = self.commands.run_recorded(name, physical, bounded, self.journal, self.guard,
                protected_pids=self.baseline.protected_pids, mutation=mutation, pass_fds=fds,
                host_env=self.c.HOST_ENV, check=False, deferred_post_guard=True,
                private_output=image, image_channel=image, output_bound=33554432 if image else 16777216)
        except BaseException as error:
            primary = error; observation = getattr(error, 'command_observation', {})
            if observation.get('host_retirement_proved') is not True:
                self.host_retirement_unknown = True
                self.view.target.poison_unjoined_command()
        finally:
            try:
                if entered:
                    manager.__exit__(None if primary is None else type(primary), primary,
                                     None if primary is None else primary.__traceback__)
                    released = True
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note('GALLERY_HELD_LEASE_EXIT:' + type(error).__name__)
            try:
                post = self.guard(action_attempted=mutation and entered)
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note('GALLERY_POST_LEASE_GUARD:' + type(error).__name__)
        observation = completed.command_observation if completed is not None else getattr(primary, 'command_observation', {})
        self.possible_effect |= mutation and bool(observation.get('spawned'))
        self.host_cancelled |= bool(observation.get('cancellation', {}).get('count'))
        record = self.c.write_new(self.journal / (name + '.transport.json'), {
            'schema': 'pocket4-gallery-original-held-transport-v1', 'logical': logical,
            'phase': self.phase_ref, 'mutation': mutation, 'lease_entered': entered, 'lease_released': released,
            'host_retirement_proved': observation.get('host_retirement_proved') is True,
            'post_guard': post, 'error': None if primary is None else type(primary).__name__ + ':' + str(primary),
            'capture': None if completed is None else self.c.regular(self.journal / (name + '.result.json'), contents=False),
            'automatic_retry': False})
        self.records.append(record)
        if primary is not None:
            raise primary
        self.c.need(completed is not None and released and completed.host_tree_retired and not completed.host_timed_out
            and completed.returncode == 0 and not completed.recorder_errors,
            'ORIGINAL_GALLERY_HOST_COMMAND_FAILED_OR_UNRETIRED')
        return {'rc': completed.returncode, 'timed_out': completed.host_timed_out,
            'joined': completed.host_tree_retired, 'guard_after': post is not None,
            'stdout': completed.stdout, 'stderr': completed.stderr}

    def android(self, argv, timeout=20):
        self.guard(); argv = list(argv); mutation = self.policy.command(argv, timeout)
        value = self._transport('original-android', argv, timeout, mutation=mutation)
        self.policy.observe(argv, value['stdout']); return value['stdout']

    def root_query(self, label, command, timeout):
        self.original_caller(['owned_media.py'], {'query'})
        command = self.policy.root_sql(label, command, timeout)
        return self._transport('original-media-' + label, command[-5:], 14, root=True)

    def _host(self, label, argv, timeout, mutation=False):
        self.guard(); self.c.need(self.deadline - time.monotonic() >= timeout + 8, 'HOST_COMMAND_FULL_RETIREMENT_TAIL')
        self.command_index += 1; name = 'command-%05d' % self.command_index
        try:
            result = self.commands.run_recorded(name, argv, timeout, self.journal, self.guard,
                protected_pids=self.baseline.protected_pids, mutation=mutation, host_env=self.c.HOST_ENV,
                check=False, output_bound=16777216)
        except BaseException as error:
            observation = getattr(error, 'command_observation', {})
            self.host_cancelled |= bool(observation.get('cancellation', {}).get('count'))
            self.possible_effect |= mutation and bool(observation.get('spawned'))
            if observation.get('host_retirement_proved') is not True:
                self.host_retirement_unknown = True; self.view.target.poison_unjoined_command()
            raise
        self.possible_effect |= mutation and result.command_observation['spawned']
        self.host_cancelled |= bool(result.command_observation.get('cancellation', {}).get('count'))
        self.records.append(self.c.regular(self.journal / (name + '.result.json'), contents=False))
        self.c.need(result.returncode == 0 and result.host_tree_retired and not result.host_timed_out
            and not result.recorder_errors, 'EXACT_ORIGINAL_GALLERY_HOST_RESULT_REQUIRED')
        return {'rc': result.returncode, 'timed_out': result.host_timed_out,
            'joined': result.host_tree_retired, 'guard_after': True, 'stdout': result.stdout, 'stderr': result.stderr}

    def run_host(self, label, argv, timeout=20, pass_fds=()):
        self.original_caller(['rotation_ui.py'], {'launch'})
        f = self.case; expected = list(self.c.NATIVE_PREFIX) + ['launch', PACKAGE, '--component', PACKAGE + '/.RotationActivity', '--json']
        self.c.need(not pass_fds and self.phase == 'business' and self.active_api is None and timeout == 45
            and argv == expected and self.native_launches < 2 and label == 'launch-' + str(self.native_launches + 1)
            and f.ui.launches == self.native_launches + 1 and label in f.ui.pending
            and not f.ui.owned and self.last_stacks is not None and self.last_stacks[1] == f.ui.baseline,
            'ONCE_ORIGINAL_HELPER_LAUNCH_FROM_RESTORED_TASK_SET')
        self.consume_intent('launch', argv); self.native_launches += 1
        value = self._host(label, argv, timeout, True); decoded = self.c.parse(value['stdout'])
        match = re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)', decoded.get('launch', ''))
        self.c.need(decoded.get('ok') is True and decoded.get('state') == 'running'
            and decoded.get('host_pid') == self.tx.MAIN_HOST and decoded.get('outcome_unknown') is not True
            and match and match[3] == '0' and int(match[4]) not in self.last_stacks[0]
            and int(match[4]) not in self.last_stacks[1], 'ACTUAL_NEW_HELPER_TASK_FROM_NATIVE_RECEIPT')
        task = int(match[4]); self.launch_receipts[label] = self.c.write_new(self.root / (label + '-scope.json'), {
            'schema': 'pocket4-gallery-current-owned-launch-v1', 'baseline': self.request['baseline'],
            'qualification': self.request['qualification'], 'installation': self.install_ref,
            'phase': self.phase_ref, 'native': decoded, 'task': task, 'prelaunch_tasks': sorted(self.last_stacks[1]),
            'component': [PACKAGE, PACKAGE + '.RotationActivity'], 'automatic_retry': False})
        return value

    def observe_owned_tasks(self):
        if self.case is None:
            return
        for task, item in self.case.ui.owned.items():
            if task in self.claimed_tasks:
                continue
            label = item['source']; self.c.need(label in self.launch_receipts, 'TASK_NEEDS_ACTUAL_CURRENT_NATIVE_LAUNCH_SCOPE')
            ref = self.launch_receipts[label]; claim = self.c.parse(self.c.read_ref(ref))
            self.c.need(claim['task'] == task and tuple(item['component']) == tuple(claim['component'])
                and self.components['rotation_ui.py'].leaf(self.last_stacks[0], task, tuple(claim['component'])),
                'ACTUAL_NEW_HELPER_LEAF_NOT_MATCHING_LAUNCH_RECEIPT')
            self.claimed_tasks[task] = {**claim, 'source_ref': ref}

    def record_route_claim(self, ref, value):
        self.c.need(self.case is not None and self.last_stacks is not None and value['task'] in self.last_stacks[1]
            and value['caller_package'] == PACKAGE and value['caller_uid'] == self.case.pkg.installed['uid']
            and value['component'] == [GALLERY, GALLERY + '.app.GalleryActivity']
            and self.case.client_pending is not None and self.case.client_pending in self.case.ui.pending
            and self.case.ui.pending[self.case.client_pending]['input_acknowledged'] is True,
            'ONLY_ORIGINAL_VERIFIED_ALBUM_CALLER_ROUTE_CLAIM')
        task = value['task']; self.c.need(task not in self.case.ui.baseline, 'ROUTED_TASK_WAS_PREEXISTING')
        self.claimed_tasks[task] = {'task': task, 'component': value['actual_stack_component'],
            'source_ref': ref, 'route': copy.deepcopy(value), 'baseline': self.request['baseline'],
            'phase': self.phase_ref, 'prelaunch_tasks': sorted(self.case.ui.baseline)}

    def caller_status(self, label):
        self.original_caller(['gallery_rotation_flow.py'], {'finish'})
        self.c.need(label == 'rotation-final-caller' and self.phase == 'final_cleanup', 'ONLY_ORIGINAL_FINAL_CALLER_STATUS')
        value = self.c.parse(self._host(label, list(self.c.NATIVE_PREFIX) + ['status', '--json'], 10)['stdout'])
        self.c.need(value.get('ok') is True and value.get('state') == 'running' and value.get('host_pid') == self.tx.MAIN_HOST
            and 'cell u1000 ' in value.get('message', ''), 'SAME_FINAL_MAIN_AND_CALLER_UID_REQUIRED')
        return value

    def prior_cleanup(self):
        previous = self.c.parse(self.c.read_ref(self.prior_ref))
        self.c.need(previous.get('schema') == 'pocket4-gallery-prior-fixture-cleanup-readonly-v1'
            and previous.get('state') == 'PRIOR_OWNED_FIXTURE_AND_HELPER_ABSENCE_CONFIRMED'
            and previous.get('prior_fixture_cleanup_prerequisite_closed') is True
            and previous.get('original_rotation_functional_failure_resolved') is False
            and previous.get('data_image_unchanged') is True and previous.get('owned_commands_retired') is True
            and previous.get('Android_commands') == previous.get('cleanup_actions_taken') == 0,
            'SAVED_PRIOR_OWNED_FIXTURE_RECONCILIATION_REQUIRED')
        return {'reconciliation': self.prior_ref, 'state': previous['state'],
            'previous_failed_receipts_preserved': True, 'historical_runtime_authority_transferred': False,
            'new_trial_after_verified_cleanup': True, 'fresh_namespace_absence_still_required': True}

    def match_installed_identity(self, value):
        expected = self.install['gallery_after']; protected = expected['protected']
        self.c.need(value['package'] == GALLERY and value['uid'] == protected['uid'] == 10064
            and value['version_code'] == protected['version_code'] == 40030
            and value['apk_path'] == expected['apk']['path'] and value['apk_sha256'] == expected['apk']['sha256'] == GALLERY_SHA
            and value['apk_bytes'] == expected['apk']['bytes'] == 7488378
            and value['directories'] == protected['directories']
            and value['permissions']['permission_rows'] == protected['all_permission_rows'],
            'EXACT_ACTUALLY_VERIFIED_NEW_GALLERY_IDENTITY_REQUIRED')

    def pm_no_replace_proof(self):
        self.original_caller(['rotation_package.py'], {'install'})
        self.c.need(self.pm_help_ref is None and not self.pm_help_reading, 'ONE_FRESH_PM_HELP_QUERY')
        before = self.guard(); self.pm_help_reading = True
        try:
            raw = self.android(['/system/bin/pm', 'help'], 15)
        finally:
            self.pm_help_reading = False
        text = raw.decode('utf-8', 'strict'); lines = [x for x in text.splitlines() if re.match(r'\s*-R:', x)]
        self.c.need([x.strip() for x in lines] == ['-R: disallow replacement of existing application'],
            'CURRENT_PM_CREATE_ONLY_FLAG_NOT_VERIFIED')
        proof = {'state': 'ACTUAL_NO_REPLACE_FLAG_VERIFIED', 'no_replace_flag': '-R',
            'guard_before': before, 'guard_after': self.guard(), 'actual_flag_lines': lines,
            'ui_actions': 0, 'package_mutations': 0, 'actual_help': self.c.write_new(self.root / 'pm-help.stdout', raw),
            'historical_runtime_authority_transferred': False}
        self.c.need(proof['guard_before'] == proof['guard_after'], 'MAIN_CHANGED_DURING_CREATE_ONLY_FLAG_OBSERVATION')
        self.pm_help_ref = self.c.write_new(self.root / 'pm-create-only-proof.json', proof); return proof

    def verify_final_consumers(self, app, backend):
        self.c.need(self.c.regular(app['path'], contents=False) == app
            and self.c.regular(backend['path'], contents=False) == backend, 'ACTUAL_QUALIFIED_FINAL_UI_CONSUMERS_REQUIRED')
        self.guard()

    def verify_original_callback(self, kind, callback, previous):
        fn = getattr(callback, '__func__', None); owner = getattr(callback, '__self__', None)
        self.c.need(kind == 'foreground' and fn is not None and owner is not None and owner.s is self
            and fn.__code__.co_filename == self.source_paths['rotation_ui.py']
            and fn.__code__.co_name == 'helper_foreground' and self.ui_owner is None,
            'ONE_ORIGINAL_GALLERY_OWNED_FOREGROUND_CALLBACK')
        self.ui_owner = owner

    def begin_ui_api(self, api, request):
        c = self.c; f = self.case
        c.need(api in ('capture', 'ui', 'dispatch', 'window_state') and f is not None
            and self.ui_owner is f.ui and self.active_api is None, 'BOUND_ORIGINAL_GALLERY_API_ONLY')
        caller = self.original_caller(['rotation_ui.py'])
        package = request.get('package', request.get('expected_package'))
        c.need(package in self.allowed_ui_packages and request.get('display') == 0
            and request.get('accessibility_mode') == 'none', 'EXACT_ORIGINAL_GALLERY_API_PACKAGE_DISPLAY')
        mutation = api == 'ui' and request.get('op') == 'click' or api == 'dispatch' and request.get('op') == 'snapshot-tap'
        if api in ('capture', 'window_state'):
            c.need('op' not in request and set(request) <= {'package', 'display', 'accessibility_mode', 'window_token',
                'frame_sha256', 'scope_sha256', 'context_token'} and 'window_token' in request,
                'ORIGINAL_WINDOW_BOUND_CAPTURE_OR_STATE')
        elif api == 'ui' and not mutation:
            c.need(request == {'op': 'dump', 'expected_package': package, 'display': 0, 'accessibility_mode': 'none'},
                'ONLY_ORIGINAL_NATIVE_DUMP')
        elif not mutation:
            c.need(api == 'dispatch' and request == {'op': 'observe', 'package': package,
                'display': 0, 'accessibility_mode': 'none', 'window_token': request.get('window_token'), 'with_png': True},
                'ONLY_ORIGINAL_FULL_OBSERVE_DISPATCH')
        else:
            c.need(self.phase == 'business' and len(f.ui.pending) == 1 and 1 <= f.ui.actions <= 20,
                'ORIGINAL_GALLERY_ONE_PENDING_INPUT_AND_RESERVED_CLEANUP_BUDGET')
            token = next(iter(f.ui.pending))
            c.need(token in {'open-owned-album-1', 'open-owned-album-2', 'open-owned-thumbnail-1',
                'open-owned-thumbnail-2', 'show-owned-photo-bars', 'rotation-more-options', 'rotate-right'},
                'ONLY_ORIGINAL_GALLERY_ROTATION_ACTIONS')
            if api == 'ui':
                c.need(token == 'rotation-more-options' and caller['function'] == 'open_more_options'
                    and request.get('method') == 'accessibility' and request.get('expected_package') == GALLERY
                    and set(request) == {'op', 'method', 'expected_package', 'display', 'accessibility_mode', 'selector'},
                    'ONLY_ORIGINAL_OBSERVED_MORE_OPTIONS_CLICK')
            else:
                c.need(caller['function'] in ('input', 'tap_pattern') and set(request) == {'op', 'package',
                    'display', 'accessibility_mode', 'window_token', 'frame_sha256', 'scope_sha256',
                    'context_token', 'coords', 'input_source'} and request['input_source'] == 'touch',
                    'ONLY_ORIGINAL_OBSERVED_GALLERY_TOUCH')
        self.guard(); f.ui.check_tasks('api-current-owned-tasks')
        actual = self.helper.foreground_callback(); focus = self.last_focus
        c.need(focus is not None and focus['task'] in f.ui.owned and focus['task'] in self.claimed_tasks,
               'CURRENT_TASK_HAS_NEW_ACTUAL_OWNERSHIP_CLAIM')
        self.api_sequence += 1
        context = {'schema': 'pocket4-gallery-current-original-api-context-v1', 'api': api, 'request': copy.deepcopy(request),
            'phase': self.phase_ref, 'owned_task': focus['task'], 'claim': self.claimed_tasks[focus['task']]['source_ref'],
            'caller': caller, 'api_sequence': self.api_sequence, 'mutation_sent': False, 'native_returns': 0,
            'automatic_retry': False,
            'observed_focus': copy.deepcopy(focus) if api == 'ui' and mutation else None}
        self.validate_ui_foreground(actual, context)
        if mutation:
            item = self.consume_intent('ui', request); context['original_intent'] = item['ref']
            self._validate_pointer_intent(request, item['value'])
        context['output'] = str(self.c.private_dir(self.api_root / ('api-%04d' % self.api_sequence), create=True))
        self.c.write_new(Path(context['output']) / 'context.json', context)
        self.active_api = context; return context

    def _validate_pointer_intent(self, request, value):
        if request['op'] == 'click':
            self.c.need(type(value.get('focus')) is dict and value['focus'] == self.last_focus,
                'ORIGINAL_MORE_OPTIONS_OBSERVED_FOCUS_CHANGED')
            return
        if request['op'] != 'snapshot-tap':
            return
        if 'node' in value:
            box = value['node'].get('bounds_array')
            self.c.need(type(box) is list and len(box) == 4 and all(type(v) is int for v in box)
                and box[0] < box[2] and box[1] < box[3]
                and request['coords'] == [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2],
                'POINTER_ONLY_FROM_ORIGINAL_OBSERVED_NODE')
        else:
            proof = value['pattern_proof']; shot = self.case.ui.last['screenshot']; box = proof['scope_pattern_bounds']
            self.c.need(proof['scope_sha256'] == request['scope_sha256'] == shot['scope_sha256']
                and proof['context_token'] == request['context_token'] == shot['context_token']
                and proof['scope_size'] == [shot['scope_width'], shot['scope_height']]
                and request['coords'] == [shot['scope_bounds'][0] + (box[0] + box[2]) // 2,
                                          shot['scope_bounds'][1] + (box[1] + box[3]) // 2],
                'POINTER_ONLY_FROM_ACTUAL_ORIGINAL_OWNED_PHOTO_PATTERN')

    def validate_ui_foreground(self, value, context):
        focus = self.last_focus
        self.c.need(type(value) is dict and set(value) == {'package', 'activity', 'window_token'}
            and focus is not None and focus['task'] == context['owned_task']
            and focus['task'] in self.case.ui.owned and (focus['package'], focus['activity']) in self.case.ui.allowed
            and value == {k: focus[k] for k in ('package', 'activity', 'window_token')}
            and value['package'] == context['request'].get('package', context['request'].get('expected_package')),
            'ACTUAL_ORIGINAL_GALLERY_OWNED_FOREGROUND_REQUIRED')
        if not context['mutation_sent'] and context.get('observed_focus') is not None:
            self.c.need(focus == context['observed_focus'],
                'ORIGINAL_GALLERY_OBSERVED_FOCUS_CHANGED_BEFORE_INPUT')
        if not context['mutation_sent'] and 'window_token' in context['request']:
            self.c.need(value['window_token'] == context['request']['window_token'], 'ORIGINAL_GALLERY_WINDOW_CHANGED')

    def ui_guard(self, *, action_attempted=False):
        self.guard(action_attempted=action_attempted)
        self.c.need(self.active_api is None or self.active_api['phase'] == self.phase_ref,
                    'GALLERY_API_PHASE_CHANGED')

    def validate_internal_capture(self, request, context):
        expected = context['request']
        self.c.need(type(request) is dict and request.get('package') == expected.get('package', expected.get('expected_package'))
            and request.get('display') == 0 and request.get('accessibility_mode') == 'none', 'EXACT_GALLERY_CAPTURE_SCOPE')
        self.c.need(request == expected if not context['mutation_sent'] else
            set(request) <= {'package', 'display', 'accessibility_mode', 'crop'}, 'UNCHANGED_FINAL_BACKEND_CAPTURE_FIELDS')

    def validate_native_request(self, request, context, action_used):
        return self.components['gallery_rotation_policy.py'].native_request(self.c, context['request'], request, action_used)

    def admit_ui_android(self, argv, timeout, context, action_used):
        self.c.need(context is self.active_api, 'CURRENT_GALLERY_API_CONTEXT_REQUIRED')
        return self.components['gallery_rotation_policy.py'].backend_android(self.c, context['request'], argv, timeout, action_used)

    def ui_android(self, argv, timeout, context, *, mutation=False, image=False):
        self.c.need(context is self.active_api, 'CURRENT_GALLERY_TYPED_BACKEND_COMMAND_REQUIRED')
        if mutation:
            self.c.need(not context['mutation_sent'], 'NO_SECOND_GALLERY_UI_EFFECT'); context['mutation_sent'] = True
        return self._transport('original-backend', argv, timeout, mutation=mutation, image=image)['stdout']

    def ui_readiness(self, argv, options, context):
        self.c.need(context is self.active_api and argv == ['/usr/bin/droidloomctl', 'readiness', '--json'],
            'ORIGINAL_READONLY_FINAL_BACKEND_DISCOVERY')
        value = self._host('readiness', argv, 8)
        return types.SimpleNamespace(stdout=value['stdout'], stderr=value['stderr'], returncode=value['rc'])

    def record_native_return(self, request, value, context):
        self.c.need(context is self.active_api, 'ACTUAL_NATIVE_RETURN_CONTEXT')
        context['native_returns'] += 1
        self.c.write_new(Path(context['output']) / ('native-return-%03d.json' % context['native_returns']), {
            'request': request, 'native_response': value, 'phase': self.phase_ref,
            'recorded_before_post_action_screenshot': True, 'automatic_retry': False})

    def validate_snapshot_request(self, request, frame):
        self.c.need(request.get('package') in self.allowed_ui_packages and request.get('display') == 0
            and request.get('accessibility_mode') == 'none' and request.get('window_token') == frame['meta']['scope']['window_token'],
            'THIS_ORIGINAL_GALLERY_WINDOW_CAPTURE_ONLY')

    def finish_ui_api(self, context, api, request, value, first, *, action_attempted):
        try:
            self.c.need(context is self.active_api, 'SAME_ORIGINAL_GALLERY_API_COMPLETION')
            result = value
            if api == 'capture' and value is not None:
                result = {'meta': value['meta'], 'image': {'mode': value['image'].mode,
                    'width': value['image'].width, 'height': value['image'].height,
                    'pixel_sha256': self.helper.module.image_sha(value['image'])}}
            elif type(value) is dict and 'screenshot_png_base64' in value:
                raw = base64.b64decode(value['screenshot_png_base64'], validate=True)
                self.c.need(len(raw) <= 33554432, 'ORIGINAL_GALLERY_OBSERVATION_PNG_BOUND')
                result = dict(value); result.pop('screenshot_png_base64')
                result['recorded_png'] = self.c.write_new(Path(context['output']) / 'observation.png', raw)
            self.c.write_new(Path(context['output']) / 'result.json', {
                'schema': 'pocket4-gallery-current-original-api-result-v1', 'context': context,
                'api': api, 'request': request, 'result': result, 'action_attempted': action_attempted,
                'original_error': None if first is None else {'type': type(first).__name__, 'message': str(first),
                    'details': getattr(first, 'details', None)}, 'automatic_retry': False,
                'whole_app_business_accepted': False})
        finally:
            self.active_api = None

    def close(self):
        errors = []
        for obj in (self.helper, self.peer, self.view):
            if obj is not None:
                try:
                    obj.close()
                except BaseException as error:
                    errors.append(error)
        self.closed = True
        if errors:
            first = errors[0]
            for error in errors[1:]:
                first.add_note('GALLERY_CONTEXT_CLOSE:' + type(error).__name__)
            raise first
