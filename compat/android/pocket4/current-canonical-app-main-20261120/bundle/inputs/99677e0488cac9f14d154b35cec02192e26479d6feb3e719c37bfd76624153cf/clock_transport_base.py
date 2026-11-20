"""Exact frozen transport/OFD methods with Clock-specific receipt labels.

Constructor, commands, task/source policy and result admission are separate.
No old case or Main is constructed; no action occurs on import.
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

def birth(info):
    return {k: getattr(info, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink')}
ACTION_LOCK = '/run/lock/android-digitalis-actions.lock'

class ActionLock:

    def __init__(self, c, root):
        self.c = c
        self.fd = None
        self.closed = False
        self.owner = os.getpid()
        try:
            self.fd = os.open(ACTION_LOCK, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
            self.identity = birth(os.fstat(self.fd))
            self._check()
            self.ref = c.write_new(root / 'action-lock.json', {'schema': 'pocket4-clock-rotation-action-lock-v1', 'path': ACTION_LOCK, 'owner_pid': self.owner, 'file': self.identity, 'same_process_one_open_file_description': True, 'transferred_descriptors': 0, 'automatic_retry': False})
        except BaseException:
            self.close()
            raise

    def _check(self):
        self.c.need(not self.closed and self.fd is not None and (os.getpid() == self.owner), 'SAME_CLOCK_ACTION_LOCK_OWNER_REQUIRED')
        info = os.fstat(self.fd)
        self.c.need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and (info.st_nlink == 1) and (self.identity == birth(info) == birth(os.lstat(ACTION_LOCK))) and (not os.get_inheritable(self.fd)), 'SAME_CLOCK_ACTION_LOCK_OFD_REQUIRED')
        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def verify(self):
        self._check()
        self.c.read_ref(self.ref)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.closed = True

class ClockTransportBase:

    def guard(self, *, action_attempted=False):
        self.c.need(not self.closed and (not self.host_retirement_unknown) and (time.monotonic() < self.deadline), 'CLOCK_ORIGINAL_PHASE_EXPIRED_CLOSED_OR_UNRETIRED')
        self.action_lock.verify()
        self.source_guard()
        value = self.view.guard(action_attempted=action_attempted)
        if self.peer is not None:
            self.peer.verify()
        self.c.need(time.monotonic() < self.deadline, 'CLOCK_GUARD_EXHAUSTED_ORIGINAL_PHASE')
        return value

    def original_caller(self, names, methods=None, skip=()):
        frame = inspect.currentframe()
        try:
            for _ in range(18):
                frame = frame.f_back
                if frame is None:
                    break
                for name in names:
                    if frame.f_code.co_filename == self.source_paths.get(name) and frame.f_code.co_name not in skip:
                        self.c.need(methods is None or frame.f_code.co_name in methods, 'EXACT_ORIGINAL_CLOCK_METHOD_REQUIRED')
                        return {'source': name, 'function': frame.f_code.co_name}
            raise RuntimeError('CLOCK_API_CALLER_IS_NOT_FROZEN_ORIGINAL_CASE')
        finally:
            del frame

    def _transport(self, label, logical, timeout, *, mutation=False, image=False, root=False):
        self.guard()
        remaining = self.deadline - time.monotonic() - 8
        if mutation or root:
            self.c.need(remaining >= timeout, 'FULL_ORIGINAL_MUTATION_OR_ROOT_TIME_REQUIRED')
            bounded = timeout
        else:
            bounded = min(timeout, remaining)
        self.c.need(bounded > 5, 'NO_COMMAND_AFTER_ORIGINAL_RETIREMENT_TAIL')
        self.command_index += 1
        name = 'command-%05d' % self.command_index
        inner = 12 if root else bounded - 4
        command = ['/system/bin/env', '-i'] + [k + '=' + self.environment[k] for k in sorted(self.environment)]
        if not root:
            command += ['/system/xbin/su', '2000']
        command += ['/system/bin/timeout', '-k', '2', str(inner), *logical]
        self.c.write_new(self.journal / (name + '.logical.json'), {'argv': logical, 'original_timeout': timeout, 'actual_timeout': bounded, 'inner_timeout': inner, 'original_camera_T_minus_4_preserved': not root, 'original_root_12_plus_2_over_16': root, 'Android_mutation': mutation, 'phase': self.phase_ref, 'label': label, 'automatic_retry': False})
        entered = released = False
        completed = primary = None
        post = None
        manager = self.view.target.entry(command)
        try:
            physical, fds = manager.__enter__()
            entered = True
            self.c.need(len(fds) == len(set(fds)) == 7, 'EXACT_CURRENT_HELD_AUTHORITY_FDS')
            completed = self.commands.run_recorded(name, physical, bounded, self.journal, self.guard, protected_pids=self.baseline.protected_pids, mutation=mutation, pass_fds=fds, host_env=self.c.HOST_ENV, check=False, deferred_post_guard=True, private_output=image, image_channel=image, output_bound=33554432 if image else 16777216)
        except BaseException as error:
            primary = error
            observation = getattr(error, 'command_observation', {})
            if observation.get('host_retirement_proved') is not True:
                self.host_retirement_unknown = True
                self.view.target.poison_unjoined_command()
        finally:
            try:
                if entered:
                    manager.__exit__(None if primary is None else type(primary), primary, None if primary is None else primary.__traceback__)
                    released = True
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note('CLOCK_HELD_LEASE_EXIT:' + type(error).__name__)
            try:
                post = self.guard(action_attempted=mutation and entered)
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note('CLOCK_POST_LEASE_GUARD:' + type(error).__name__)
        observation = completed.command_observation if completed is not None else getattr(primary, 'command_observation', {})
        self.possible_effect |= mutation and bool(observation.get('spawned'))
        self.host_cancelled |= bool(observation.get('cancellation', {}).get('count'))
        record = self.c.write_new(self.journal / (name + '.transport.json'), {'schema': 'pocket4-clock-original-held-transport-v1', 'logical': logical, 'phase': self.phase_ref, 'mutation': mutation, 'lease_entered': entered, 'lease_released': released, 'host_retirement_proved': observation.get('host_retirement_proved') is True, 'post_guard': post, 'error': None if primary is None else type(primary).__name__ + ':' + str(primary), 'capture': None if completed is None else self.c.regular(self.journal / (name + '.result.json'), contents=False), 'automatic_retry': False})
        self.records.append(record)
        if primary is not None:
            raise primary
        self.c.need(completed is not None and released and completed.host_tree_retired and (not completed.host_timed_out) and (completed.returncode == 0) and (not completed.recorder_errors), 'ORIGINAL_CLOCK_HOST_COMMAND_FAILED_OR_UNRETIRED')
        return {'rc': completed.returncode, 'timed_out': completed.host_timed_out, 'joined': completed.host_tree_retired, 'guard_after': post is not None, 'stdout': completed.stdout, 'stderr': completed.stderr}

    def _host(self, label, argv, timeout, mutation=False):
        self.guard()
        self.c.need(self.deadline - time.monotonic() >= timeout + 8, 'HOST_COMMAND_FULL_RETIREMENT_TAIL')
        self.command_index += 1
        name = 'command-%05d' % self.command_index
        try:
            result = self.commands.run_recorded(name, argv, timeout, self.journal, self.guard, protected_pids=self.baseline.protected_pids, mutation=mutation, host_env=self.c.HOST_ENV, check=False, output_bound=16777216)
        except BaseException as error:
            observation = getattr(error, 'command_observation', {})
            self.host_cancelled |= bool(observation.get('cancellation', {}).get('count'))
            self.possible_effect |= mutation and bool(observation.get('spawned'))
            if observation.get('host_retirement_proved') is not True:
                self.host_retirement_unknown = True
                self.view.target.poison_unjoined_command()
            raise
        self.possible_effect |= mutation and result.command_observation['spawned']
        self.host_cancelled |= bool(result.command_observation.get('cancellation', {}).get('count'))
        self.records.append(self.c.regular(self.journal / (name + '.result.json'), contents=False))
        self.c.need(result.returncode == 0 and result.host_tree_retired and (not result.host_timed_out) and (not result.recorder_errors), 'EXACT_ORIGINAL_CLOCK_HOST_RESULT_REQUIRED')
        return {'rc': result.returncode, 'timed_out': result.host_timed_out, 'joined': result.host_tree_retired, 'guard_after': True, 'stdout': result.stdout, 'stderr': result.stderr}

    def verify_final_consumers(self, app, backend):
        self.c.need(self.c.regular(app['path'], contents=False) == app and self.c.regular(backend['path'], contents=False) == backend, 'ACTUAL_QUALIFIED_FINAL_UI_CONSUMERS_REQUIRED')
        self.guard()

    def ui_guard(self, *, action_attempted=False):
        self.guard(action_attempted=action_attempted)
        self.c.need(self.active_api is None or self.active_api['phase'] == self.phase_ref, 'CLOCK_API_PHASE_CHANGED')

    def validate_internal_capture(self, request, context):
        expected = context['request']
        self.c.need(type(request) is dict and request.get('package') == expected.get('package', expected.get('expected_package')) and (request.get('display') == 0) and (request.get('accessibility_mode') == 'none'), 'EXACT_CLOCK_CAPTURE_SCOPE')
        self.c.need(request == expected if not context['mutation_sent'] else set(request) <= {'package', 'display', 'accessibility_mode', 'crop'}, 'UNCHANGED_FINAL_BACKEND_CAPTURE_FIELDS')

    def ui_android(self, argv, timeout, context, *, mutation=False, image=False):
        self.c.need(context is self.active_api, 'CURRENT_CLOCK_TYPED_BACKEND_COMMAND_REQUIRED')
        if mutation:
            self.c.need(not context['mutation_sent'], 'NO_SECOND_CLOCK_UI_EFFECT')
            context['mutation_sent'] = True
        return self._transport('original-backend', argv, timeout, mutation=mutation, image=image)['stdout']

    def ui_readiness(self, argv, options, context):
        self.c.need(context is self.active_api and argv == ['/usr/bin/droidloomctl', 'readiness', '--json'], 'ORIGINAL_READONLY_FINAL_BACKEND_DISCOVERY')
        value = self._host('readiness', argv, 8)
        return types.SimpleNamespace(stdout=value['stdout'], stderr=value['stderr'], returncode=value['rc'])

    def record_native_return(self, request, value, context):
        self.c.need(context is self.active_api, 'ACTUAL_NATIVE_RETURN_CONTEXT')
        context['native_returns'] += 1
        self.c.write_new(Path(context['output']) / ('native-return-%03d.json' % context['native_returns']), {'request': request, 'native_response': value, 'phase': self.phase_ref, 'recorded_before_post_action_screenshot': True, 'automatic_retry': False})

    def validate_snapshot_request(self, request, frame):
        self.c.need(request.get('package') in self.allowed_ui_packages and request.get('display') == 0 and (request.get('accessibility_mode') == 'none') and (request.get('window_token') == frame['meta']['scope']['window_token']), 'THIS_ORIGINAL_CLOCK_WINDOW_CAPTURE_ONLY')

    def finish_ui_api(self, context, api, request, value, first, *, action_attempted):
        try:
            self.c.need(context is self.active_api, 'SAME_ORIGINAL_CLOCK_API_COMPLETION')
            result = value
            if api == 'capture' and value is not None:
                result = {'meta': value['meta'], 'image': {'mode': value['image'].mode, 'width': value['image'].width, 'height': value['image'].height, 'pixel_sha256': self.helper.module.image_sha(value['image'])}}
            elif type(value) is dict and 'screenshot_png_base64' in value:
                raw = base64.b64decode(value['screenshot_png_base64'], validate=True)
                self.c.need(len(raw) <= 33554432, 'ORIGINAL_CLOCK_OBSERVATION_PNG_BOUND')
                result = dict(value)
                result.pop('screenshot_png_base64')
                result['recorded_png'] = self.c.write_new(Path(context['output']) / 'observation.png', raw)
            self.c.write_new(Path(context['output']) / 'result.json', {'schema': 'pocket4-clock-current-original-api-result-v1', 'context': context, 'api': api, 'request': request, 'result': result, 'action_attempted': action_attempted, 'original_error': None if first is None else {'type': type(first).__name__, 'message': str(first), 'details': getattr(first, 'details', None)}, 'automatic_retry': False, 'whole_app_business_accepted': False})
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
                first.add_note('CLOCK_CONTEXT_CLOSE:' + type(error).__name__)
            raise first
