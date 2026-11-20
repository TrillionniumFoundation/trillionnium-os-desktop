"""Run the original eight Gallery rotation gates on a fresh original system-image observation.

The original 600-second work and 120-second cleanup budgets are retained.
A pass is assigned only after original cleanup, all context exits, exact source
rechecks and a matching descriptor table. Cancellation cannot become a pass.
"""
import ctypes
import fcntl
import os
from pathlib import Path
import signal
import time
import types

SUCCESS = 'OWNED_GALLERY_JPEG_ROTATION_REOPEN_AND_CLEANUP_VERIFIED'
INSTALL_SUCCESS = 'CURRENT_ART_VERIFIED_GALLERY_INSTALLED_ALL_PROTECTED_IDENTITY_PRESERVED'


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


class Dirent(ctypes.Structure):
    _fields_ = [('ino', ctypes.c_ulong), ('offset', ctypes.c_long),
                ('record_bytes', ctypes.c_ushort), ('kind', ctypes.c_ubyte), ('name', ctypes.c_char * 256)]


def fd_table():
    libc = ctypes.CDLL(None, use_errno=True)
    libc.fdopendir.argtypes = [ctypes.c_int]; libc.fdopendir.restype = ctypes.c_void_p
    libc.readdir.argtypes = [ctypes.c_void_p]; libc.readdir.restype = ctypes.POINTER(Dirent)
    libc.closedir.argtypes = [ctypes.c_void_p]; libc.closedir.restype = ctypes.c_int
    directory = os.open('/proc/self/fd', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    handle = libc.fdopendir(directory)
    if not handle:
        os.close(directory); raise OSError(ctypes.get_errno(), 'fdopendir')
    try:
        rows = []
        while True:
            ctypes.set_errno(0); pointer = libc.readdir(handle)
            if not pointer:
                need(ctypes.get_errno() == 0, 'FD_DIRECTORY_READ_FAILED'); break
            name = pointer.contents.name.decode('ascii')
            if name in ('.', '..'):
                continue
            need(name.isdecimal(), 'UNEXPECTED_FD_DIRECTORY_ENTRY'); fd = int(name)
            if fd == directory:
                continue
            info = os.fstat(fd)
            rows.append([fd, info.st_dev, info.st_ino, info.st_mode, fcntl.fcntl(fd, fcntl.F_GETFL),
                         fcntl.fcntl(fd, fcntl.F_GETFD), os.readlink('/proc/self/fd/' + name)])
        return sorted(rows)
    finally:
        need(libc.closedir(handle) == 0, 'FD_DIRECTORY_CLOSE_FAILED')






def identity_matches(c, originals, session, expected):
    session.image_capture.bind(session.view)
    actual = originals['identity'].snapshot(session, session.observation)
    need(actual['protected'] == expected['protected'] and actual['apk'] == expected['apk']
        and actual['native_apk_payload'] == expected['native_apk_payload']
        and actual['code_and_install_metadata'] == expected['code_and_install_metadata'],
        'CURRENT_INSTALLED_GALLERY_PROTECTED_AND_CODE_IDENTITY_CHANGED')
    return actual


class LeaseExpired(BaseException):
    pass


def execute(request, preparation_ref, root, c, support, originals, held, image_capture,
            components, source_guard, prior_ref, cancelled, enter_retirement):
    started = time.monotonic(); business_deadline = started + 600
    result = {'schema': 'pocket4-current-owned-gallery-jpeg-rotation-v1', 'state': 'FAILED',
        'baseline': request['baseline'], 'qualification': request['qualification'],
        'image_custody': image_capture.reference, 'source_preparation': preparation_ref,
        'business_scope_completed': False, 'whole_app_business_accepted': False,
        'historical_UI_pass_granted': False, 'historical_runtime_authority_transferred': False,
        'automatic_retry': False, 'original_business_seconds': 600, 'original_cleanup_seconds': 120,
        'started_unix_ns': time.time_ns(), 'outcome_unknown': False}
    flow = session = lock = None; original_ok = False
    result['descriptor_table_cold'] = fd_table()
    c.support(c.SUPPORT_REF)[1]['business_commands.py'].load_capture().load_source_lifecycle()
    before_fds = fd_table(); result['descriptor_table_initialized'] = before_fds
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*unused):
        raise LeaseExpired('ORIGINAL_GALLERY_PHASE_ABSOLUTE_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(.001, business_deadline - time.monotonic()))
    try:
        source_guard(); result['resources_before'] = support.resources()
        lock = components['gallery_rotation_session.py'].ActionLock(c, root)
        session = components['gallery_rotation_session.py'].Session(c, support, held, request, root, components,
            lock, image_capture, source_guard, prior_ref, business_deadline)
        result['main_before'] = session.guard()
        image_capture.bind(session.view)
        result['identity_before'] = originals['identity'].snapshot(session, session.observation)
        session.image_identity = result['identity_before']
        components['bounded_diagnostics.py'].bind_current_uid(session)
        module = components['gallery_rotation_flow.py']; module.ROOT = Path(root)
        module.PINS = {name: c.regular(value.__file__, contents=False)['sha256'] for name, value in components.items()}
        c.private_dir(root / 'ui', create=True)
        flow = module.Flow(session, session.tx, components['rotation_ui.py'], components['rotation_package.py'],
            components['owned_media.py'], components['verify_rotation.py'], components['bounded_diagnostics.py'])
        session.case = flow
        result.update(flow.result); flow.result = result
        try:
            need(not cancelled, 'GALLERY_CANCELLED_BEFORE_ORIGINAL_BUSINESS')
            flow.run()
        except BaseException as error:
            result['error'] = type(error).__name__ + ':' + str(error)
            flow.lease_expired = isinstance(error, LeaseExpired)
        finally:
            # Cancellation still precludes PASS, but may not interrupt the
            # original bounded cleanup or the following owned-context exits.
            enter_retirement()
            signal.setitimer(signal.ITIMER_REAL, 0)
            trigger = c.write_new(root / 'business-ended.json', {'business_scope_completed': result.get('business_scope_completed'),
                'error': result.get('error'), 'cancelled_signals': list(cancelled), 'automatic_retry': False})
            session.begin_cleanup(trigger)
            signal.setitimer(signal.ITIMER_REAL, max(.001, session.deadline - time.monotonic()))
            result['cleanup'] = flow.cleanup()
            try:
                flow.finish()
                result['identity_after'] = identity_matches(c, originals, session, session.image_identity)
                image_capture.bind(session.view)
                result['main_after'] = session.guard()
                need(result['main_after'] == result['main_before'], 'GALLERY_FINAL_MAIN_CHANGED')
            except BaseException as error:
                result['final_check_error'] = type(error).__name__ + ':' + str(error)
            flow.terminal()
            original_ok = bool(result.get('business_scope_completed')
                and not result['cleanup']['errors'] and result['cleanup'].get('task_set_restored') is True
                and result['cleanup'].get('package_cleanup', {}).get('package_absent_verified') is True
                and result['cleanup'].get('stage_cleanup', {}).get('staged_apk_removed') is True
                and result['cleanup'].get('media_cleanup', {}).get('physical_and_indexed_owned_directories_absent') is True
                and result.get('original_media_preserved') is True and 'final_check_error' not in result and 'error' not in result)
            if original_ok:
                flow.no_unknown(); need(flow.album_pending is None, 'PRIVATE_ALBUM_ROUND_NOT_SEALED')
            result['host_commands'] = list(session.records); result['claimed_tasks'] = session.claimed_tasks
            result['same_process_action_lock'] = lock.ref; result['host_cancellation_observed'] = session.host_cancelled
            result['final_phase'] = session.phase_ref
    except BaseException as error:
        enter_retirement()
        result['outer_error'] = type(error).__name__ + ':' + str(error); original_ok = False
    finally:
        enter_retirement()
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
        if flow is not None:
            flow.terminal()
            try:
                flow.media.close(); result['owned_media_FDs_closed'] = True
            except BaseException as error:
                result['local_fd_cleanup_error'] = type(error).__name__ + ':' + str(error); original_ok = False
        if session is not None:
            result['host_commands'] = list(session.records)
            result['host_cancellation_observed'] = session.host_cancelled
            try:
                session.close(); result['held_session_closed'] = session.closed
            except BaseException as error:
                result['session_close_error'] = type(error).__name__ + ':' + str(error); original_ok = False
        if lock is not None:
            try:
                lock.verify(); lock.close(); result['global_action_lock_exited'] = True
            except BaseException as error:
                lock.close(); result['lock_close_error'] = type(error).__name__ + ':' + str(error); original_ok = False
        try:
            source_guard(); result['source_unchanged'] = True
            result['resources_after'] = support.resources()
            result['descriptor_table_before'] = before_fds; result['descriptor_table_after'] = fd_table()
            need(result['descriptor_table_after'] == before_fds, 'GALLERY_CONTEXT_DESCRIPTOR_LEAK_OR_REPLACEMENT')
            result['all_case_acquired_FDs_closed'] = True
        except BaseException as error:
            result['post_context_error'] = type(error).__name__ + ':' + str(error); original_ok = False
        result['cancelled_signals'] = list(cancelled)
        pending = any(result.get(k) for k in ('native_pending', 'helper_pending', 'client_pending',
            'rotation_pending', 'album_pending', 'close_pending', 'directory_pending', 'install_pending', 'uninstall_pending'))
        result['outcome_unknown'] = bool(pending or result.get('owned_tasks') or result.get('session_close_error')
            or result.get('local_fd_cleanup_error') or result.get('post_context_error'))
        need_ok = all(result.get(key) is True for key in ('held_session_closed', 'owned_media_FDs_closed',
            'global_action_lock_exited', 'source_unchanged', 'all_case_acquired_FDs_closed'))
        if original_ok and need_ok and not result['outcome_unknown'] and not cancelled and not result.get('host_cancellation_observed'):
            result['state'] = SUCCESS
        else:
            result['state'] = 'UNKNOWN_NO_AUTOMATIC_REPLAY' if result['outcome_unknown'] else 'FAILED'
        result['finished_unix_ns'] = time.time_ns(); result['elapsed_seconds'] = time.monotonic() - started
        result['whole_app_business_accepted'] = False
    return result
