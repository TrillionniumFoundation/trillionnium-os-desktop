#!/usr/bin/env python3
"""One nonblocking admission on the exact existing action lock; no Android action."""
import argparse
import fcntl
import hashlib
import json
import os
import stat
import sys
import time

LOCK = '/run/lock/android-digitalis-actions.lock'
LOCK_DEV, LOCK_INO = 28, 8312
LOCK_MODE = stat.S_IFREG | 0o600
PRIOR_SHA = '13179fb6aa36a1fde53892cc6287994ae269e492199a94eb12eeafe83fe290cc'
PRIOR_BYTES = 6053
PRIOR_NONCE = 'c398efeb8c07781670825f5ad68e13af'
PRIOR_SOURCE = '16f371bda457b830b11536f977a11f8dcce3347eded286605400a9162ba079a8'
DEADLINE_SECONDS = 15.0
OUTPUT_MAX = 131072


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def error_record(phase, error):
    # No rejected /proc/locks line or unrelated process data enters errors.
    return dict(phase=phase, type=type(error).__name__, errno=getattr(error, 'errno', None),
                message=str(error)[:512],
                close_notes=[str(note)[:160] for note in getattr(error, '_lock_close_notes', ())[:8]])


class OwnedFDs:
    """Register ownership before any later operation can fail; close once."""
    def __init__(self):
        self.values = []
        self.close_errors = []

    def take(self, fd):
        need(type(fd) is int and fd >= 0 and fd not in self.values, 'NEW_OWNED_FD')
        self.values.append(fd)
        return fd

    def close(self, fd):
        need(fd in self.values, 'CLOSE_ONLY_OWNED_FD')
        self.values.remove(fd)
        primary = sys.exc_info()[1]
        try:
            os.close(fd)
        except OSError as error:
            # Do not retry an ambiguous close; the numeric FD may be reused.
            self.close_errors.append(error_record('owned_fd_close', error))
            if primary is None:
                raise
            primary._lock_close_notes = tuple(getattr(primary, '_lock_close_notes', ())) + (
                'owned FD close: ' + type(error).__name__ + ' errno=' + str(error.errno),)

    def finish(self):
        for fd in list(reversed(self.values)):
            try:
                self.close(fd)
            except OSError:
                pass


def open_fixed(fds, support, path, flags, deadline):
    """No-follow component walk; all temporary FDs belong to the outer scope."""
    need(type(path) is str and path.startswith('/') and '//' not in path, 'FIXED_ABSOLUTE_PATH')
    parts = path[1:].split('/')
    need(parts and all(p not in ('', '.', '..') for p in parts), 'FIXED_PATH_COMPONENT')
    current = fds.take(os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC))
    for part in parts[:-1]:
        support.check_time(deadline)
        child = fds.take(os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                                 dir_fd=current))
        parent, current = current, child
        fds.close(parent)
    support.check_time(deadline)
    leaf = fds.take(os.open(parts[-1], flags | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=current))
    fds.close(current)
    return leaf


def read_input(fds, support, path, digest, length, deadline, anchor=None):
    fd = open_fixed(fds, support, path, os.O_RDONLY | os.O_NONBLOCK, deadline)
    try:
        before = support.metadata(fd)
        need(stat.S_ISREG(before['mode']) and before['nlink'] == 1 and
             0 < before['size'] <= support.INPUT_MAX, 'ORIGINAL_INPUT_SHAPE_BOUND')
        if anchor is not None:
            need(before == support.metadata(anchor['fd']) == anchor['metadata'], 'INPUT_NAMED_HELD_CHANGED')
        raw = support.read_bounded(fd, support.INPUT_MAX, deadline)
        after = support.metadata(fd)
        need(before == after and len(raw) == before['size'], 'ORIGINAL_INPUT_CHANGED')
        need((length is None or len(raw) == length) and sha(raw) == digest, 'ORIGINAL_INPUT_SIZE_SHA')
        return raw, dict(path=path, bytes=len(raw), sha256=sha(raw), before=before, after=after)
    finally:
        fds.close(fd)


def read_boot(fds, support, deadline):
    fd = open_fixed(fds, support, support.BOOT_ID, os.O_RDONLY | os.O_NONBLOCK, deadline)
    try:
        before = support.metadata(fd)
        need(stat.S_ISREG(before['mode']), 'BOOT_REGULAR_PROC_FILE')
        raw = support.read_bounded(fd, support.PSEUDO_MAX, deadline)
        need(raw and before == support.metadata(fd), 'BOOT_FILE_CHANGED')
        return dict(value=raw.decode('ascii').strip(), bytes=len(raw), sha256=sha(raw), metadata=before)
    finally:
        fds.close(fd)


def validate_prior(raw):
    need(type(raw) is bytes and len(raw) == PRIOR_BYTES and sha(raw) == PRIOR_SHA, 'EXACT_TICKET_LAUNCH')
    value = json.loads(raw)
    need(value['nonce'] == PRIOR_NONCE and value['source_manifest_sha256'] == PRIOR_SOURCE and
         value['package'] == 'com.MobileTicket' and value['uid'] == 10121 and
         value['helper_uid'] == 10190 and value['phase'] == 'launch', 'TICKET_FAILURE_SCOPE')
    lock = value['action_lock_admission']
    need(lock['path'] == LOCK and lock['opened_identity'] ==
         dict(device=LOCK_DEV, inode=LOCK_INO, mode=LOCK_MODE, uid=0, gid=0, nlink=1), 'TICKET_LOCK_IDENTITY')
    need(lock['acquired'] is False and lock['errno'] == 11 and lock['fd_closed_on_error'] is True and
         lock['attempts'] == lock['busy_attempts'] == 100 and lock['wait_limit_seconds'] == 5.0 and
         value['error']['phase'] == 'action_lock' and value['error']['errno'] == 11 and
         value['action_attempted'] is False and value['outcome_unknown'] is False and
         value['flow_lock_released'] is True and value['Main_before_lock'] == value['Main_after'],
         'ORIGINAL_TICKET_ZERO_ACTION_FAILURE')
    return value


def exact_lock(metadata):
    need((metadata['device'], metadata['inode'], metadata['mode'], metadata['uid'],
          metadata['gid'], metadata['nlink']) ==
         (LOCK_DEV, LOCK_INO, LOCK_MODE, 0, 0, 1), 'EXACT_EXISTING_ROOT0600_SINGLE_LOCK_INODE')


def named_lock(fds, support, deadline):
    fd = open_fixed(fds, support, LOCK, os.O_PATH, deadline)
    try:
        value = support.metadata(fd)
        exact_lock(value)
        return value
    finally:
        fds.close(fd)


def admit_once(fds, support, anchor, before, observation, deadline):
    """One own new OFD, one EX|NB call, immediate UN on success, then close."""
    fd = None
    try:
        # No O_CREAT, truncate, rename, replacement, reopen loop or retries.
        fd = open_fixed(fds, support, LOCK, os.O_RDWR, deadline)
        observation['opened_existing'] = True
        observation['held_before'] = support.metadata(fd)
        observation['named_before'] = named_lock(fds, support, deadline)
        exact_lock(observation['held_before'])
        need(before == support.metadata(anchor) == observation['held_before'] ==
             observation['named_before'], 'PRE_ADMISSION_HELD_AND_NAMED_LOCK_CHANGED')
        need(not os.get_inheritable(fd), 'OWN_ADMISSION_FD_CLOEXEC')
        support.check_time(deadline)
        observation['exclusive_calls'] += 1
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            observation['exclusive_errno'] = error.errno
            raise
        else:
            observation['exclusive_errno'] = 0
            observation['acquired'] = True
            # No identity reads, sleeps, subprocesses or UI while holding it.
            observation['unlock_calls'] += 1
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError as error:
                observation['unlock_errno'] = error.errno
                raise
            observation['unlock_errno'] = 0
            observation['unlocked'] = True
        observation['held_after_unlock'] = support.metadata(fd)
        need(observation['held_after_unlock'] == before == support.metadata(anchor),
             'POST_UNLOCK_HELD_LOCK_CHANGED')
    finally:
        if fd is not None:
            observation['close_attempted'] = True
            errors_before = len(fds.close_errors)
            try:
                fds.close(fd)
            finally:
                observation['close_confirmed'] = len(fds.close_errors) == errors_before


def collect(support, prior_raw):
    prior = validate_prior(prior_raw)
    started = time.monotonic()
    deadline = started + DEADLINE_SECONDS
    result = dict(schema=1, success=False, error=None, secondary_errors=[],
                  scope='single nonblocking admission on one exact existing action lock',
                  prior_failure=dict(bytes=PRIOR_BYTES, sha256=PRIOR_SHA, nonce=PRIOR_NONCE),
                  expected_lock=dict(path=LOCK, device=LOCK_DEV, inode=LOCK_INO,
                                     mode=LOCK_MODE, uid=0, gid=0, nlink=1),
                  inputs={}, final_inputs={}, main_guard_before=None, main_guard_after=None,
                  lock_operation=dict(opened_existing=False, exclusive_calls=0,
                                      exclusive_errno=None, acquired=False, unlock_calls=0,
                                      unlock_errno=None, unlocked=False, close_attempted=False,
                                      close_confirmed=False),
                  original_Main_guard_unchanged=True, original_five_limit_equality_required=True,
                  output_is_sequential_not_atomic=True, deadline_seconds=DEADLINE_SECONDS,
                  maximum_exclusive_attempts=1, retry_attempts=0, wait_seconds=0,
                  runtime_authorized=False, future_UI_requires_own_normal_lock_admission=True,
                  historical_holder_identified=False, unlocked_at_future_admission_proven=False,
                  observation_grants_kill_or_cleanup_authority=False,
                  Android_actions=0, Android_contexts_opened=0, process_starts=0,
                  process_signals=0, namespace_entries=0, lock_content_reads=0,
                  lock_content_writes=0, lock_file_creation=0, lock_replacement_or_deletion=0,
                  proc_lock_table_reads=0, PID_or_FD_directory_scans=0,
                  owned_fds_closed=False)
    fds = OwnedFDs()
    anchors = {}
    activation = reference = epoch = None
    anchor = None

    def remember(phase, error):
        row = error_record(phase, error)
        if result['error'] is None:
            result['error'] = row
        else:
            result['secondary_errors'].append(row)

    def guard(label):
        support.check_time(deadline)
        value = reference.main_guard(activation, epoch)
        support.check_time(deadline)
        result[label] = value
        need(value == prior['Main_before_lock'], 'ORIGINAL_MAIN_GUARD_RESULT_CHANGED')

    try:
        need(os.getuid() == os.geteuid() == 0, 'ROOT_SINGLE_ADMISSION_REQUIRED')
        bodies = {}
        for name, path, digest, length in support.INPUTS:
            raw, record = read_input(fds, support, path, digest, length, deadline)
            fd = open_fixed(fds, support, path, os.O_RDONLY | os.O_NONBLOCK, deadline)
            need(support.metadata(fd) == record['before'], 'ORIGINAL_INPUT_ANCHOR_CHANGED')
            anchors[name] = dict(fd=fd, metadata=record['before'])
            bodies[name], result['inputs'][name] = raw, record
        activation = json.loads(bodies['activation'])
        need(activation['framework_epoch']['sha256'] == support.EPOCH_SHA, 'ORIGINAL_MAIN_EPOCH')
        reference = support.load_exact_source(bodies['reference_source'], support.REFERENCE,
                                              'original_single_lock_Main_reference')
        epoch = support.load_exact_source(bodies['epoch_source'], support.EPOCH_SOURCE,
                                          'original_single_lock_Main_epoch')
        need(str(reference.ACTIVATION) == support.ACTIVATION and str(reference.VERIFIED) == support.VERIFIED and
             str(reference.EPOCH_SOURCE) == support.EPOCH_SOURCE and str(reference.MAIN_CGROUP) == support.CGROUP and
             reference.EPOCH == support.EPOCH_SHA and reference.ACTIVATION_SHA == support.INPUTS[0][2] and
             reference.VERIFIED_SHA == support.INPUTS[1][2] and reference.CELL_SHA == support.INPUTS[2][2] and
             reference.EPOCH_SOURCE_SHA == support.INPUTS[4][2], 'EXACT_ORIGINAL_REFERENCE_CONSTANTS')
        guard('main_guard_before')
        result['boot_before'] = read_boot(fds, support, deadline)
        need(result['boot_before']['value'] == activation['framework_epoch']['binding']['boot_id'],
             'ORIGINAL_BOOT_ID')
        anchor = open_fixed(fds, support, LOCK, os.O_PATH, deadline)
        result['lock_before'] = support.metadata(anchor)
        exact_lock(result['lock_before'])
        admit_once(fds, support, anchor, result['lock_before'], result['lock_operation'], deadline)
    except Exception as error:
        remember('single_lock_admission', error)
    finally:
        if anchor is not None:
            try:
                result['lock_after'] = support.metadata(anchor)
                result['lock_named_after'] = named_lock(fds, support, deadline)
                need(result['lock_before'] == result['lock_after'] == result['lock_named_after'],
                     'FINAL_ORIGINAL_LOCK_HELD_NAMED_CHANGED')
            except Exception as error:
                remember('final_lock_identity', error)
        if activation is not None:
            try:
                result['boot_after'] = read_boot(fds, support, deadline)
                need(result['boot_after']['value'] == activation['framework_epoch']['binding']['boot_id'] ==
                     result.get('boot_before', {}).get('value'), 'ORIGINAL_BOOT_CHANGED_OR_MISSING')
            except Exception as error:
                remember('final_boot', error)
        if reference is not None and epoch is not None:
            try:
                guard('main_guard_after')
            except Exception as error:
                remember('final_original_Main_guard', error)
        for name, path, digest, length in support.INPUTS:
            if name in anchors:
                try:
                    _, result['final_inputs'][name] = read_input(fds, support, path, digest, length,
                                                                 deadline, anchors[name])
                except Exception as error:
                    remember('final_original_input:' + name, error)
        fds.finish()
        if fds.close_errors:
            result['secondary_errors'].extend(fds.close_errors)
        result['owned_fds_closed'] = not fds.values and not fds.close_errors
        lock = result['lock_operation']
        result['success'] = (result['error'] is None and not result['secondary_errors'] and
            result['owned_fds_closed'] and lock['exclusive_calls'] == lock['unlock_calls'] == 1 and
            lock['acquired'] and lock['unlocked'] and lock['close_confirmed'] and
            len(result['inputs']) == len(result['final_inputs']) == 5 and
            result['main_guard_before'] == result['main_guard_after'] == prior['Main_before_lock'])
        result['elapsed_ms'] = int((time.monotonic() - started) * 1000)
    return result


def main(support, prior_raw, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admit-once', action='store_true')
    args = parser.parse_args(argv)
    if args.admit_once:
        result = collect(support, prior_raw)
    else:
        result = dict(state='PLAN_ONLY', lock_path=LOCK, lock_device=LOCK_DEV, lock_inode=LOCK_INO,
                      root_mode=LOCK_MODE, single_link_required=True,
                      existing_open_flags=['O_RDWR', 'O_NOFOLLOW', 'O_CLOEXEC'],
                      exclusive_attempts=1, exclusive_flags=['LOCK_EX', 'LOCK_NB'],
                      unlock_only_after_success=True, close_own_fd_on_all_paths=True,
                      original_Main_guard_calls=2, original_five_inputs=5,
                      deadline_seconds=DEADLINE_SECONDS, output_maximum_bytes=OUTPUT_MAX,
                      wait_seconds=0, retry_attempts=0, Android_actions=0,
                      runtime_authorized=False, PID_or_FD_directory_scans=0)
    raw = (json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
    need(len(raw) <= OUTPUT_MAX, 'COMPLETE_OUTPUT_BOUND_NO_TRUNCATION')
    print(raw.decode('ascii'), end='', flush=True)
    return 0 if not args.admit_once or result['success'] else 1
