"""Original silent-video business sequence on the verified current Gallery.

Work is bounded to 600 seconds and cleanup to 120 seconds. PASS follows actual
business observations, exact cleanup, source rechecks and every context exit.
This scope does not claim audio, seek, album enumeration or whole-app acceptance.
"""
import os
from pathlib import Path
import signal
import time

SUCCESS = 'CURRENT_MAIN_VIDEO_PLAY_PAUSE_RESUME_REOPEN_CLEANUP_VERIFIED'
SCHEMA = 'pocket4-gallery-current-owned-video-v1'
MOVIE_SOURCE = {'bytes': 24856, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/inputs/current-movie-source.json', 'sha256': 'ac4dee6dda805bd163fc0a4274e5c15a173b9fb2224e65113852aa51676d670f'}
TASK_PROOF = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/legacy-inputs/fixtures/9cb008b7050d3bb0-task-option-proof.json',
    'bytes': 17797, 'sha256': '9cb008b7050d3bb0b8da2221140c02b39ebde973833b5ee24039932e266e90a5'}


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


class LeaseExpired(BaseException):
    pass


def construct(session, root, c, components):
    base = components['video_base.py']; mod = components['video_flow.py']; package = components['video_fixture.py']
    base.ROOT = mod.ROOT = Path(root)
    for name in ('RUN', 'PACKAGE', 'FOLDER', 'NAME', 'RELATIVE', 'GUEST_FOLDER', 'GUEST_FILE'):
        setattr(base, name, getattr(mod, name))
    for name in ('APK', 'APK_SHA', 'CERT_SHA'):
        setattr(base, name, getattr(package, name))
    base.GALLERY_SHA = session.support.APK_SHA
    ui = components['video_ui.py']; ui.ROOT = c.private_dir(Path(root) / 'ui', create=True)
    video = components['verify_video.py']; video.verify_pattern = components['verify_pattern.py'].verify_pattern
    cls = mod.make_class(base)
    flow = cls(session, session.tx, ui, components['video_identity.py'], components['video_diagnostics.py'],
               components['verify_pattern.py'], video, package, components['video_runtime.py'])
    session.case = flow
    return flow


def verify_current_movie_source(movie, artifacts, support):
    need(movie['schema'] == 'QPR1-Gallery-current-movie-source-v1'
        and movie['state'] == 'QPR1_MOVIE_CODE_SOURCE_INSPECTED_NOT_INSTALLED'
        and movie['official_APK_sha256'] == artifacts.OLD_SHA
        and movie['candidate_APK_sha256'] == support.APK_SHA == artifacts.NEW_SHA
        and movie['actual_DEX_sha256'] == artifacts.DEX_SHA
        and movie['all_movie_classes_unchanged_by_current_port'] is True
        and movie['installed'] is False and movie['runtime_credit'] == 0
        and len(artifacts.MODIFIED_METHODS) == 2
        and all('Movie' not in str(method) for method in artifacts.MODIFIED_METHODS)
        and movie['modified_methods'] == [list(row) for row in artifacts.MODIFIED_METHODS],
        'ACTUAL_CURRENT_QPR1_MOVIE_SOURCE_AND_REPAIR_SCOPE_MUST_MATCH')
    return {'source_only': True, 'runtime_credit': 0, 'candidate_sha256': support.APK_SHA}


def execute(request, preparation_ref, root, c, support, originals, held, current_preparation,
            current_modules, components, source_guard, prior_ref, cancelled, enter_retirement):
    shared_case = components['shared_case']; shared_session = components['shared_session']
    started = time.monotonic(); business_deadline = started + 600
    result = {'schema': SCHEMA, 'state': 'FAILED', 'baseline': request['baseline'],
        'qualification': request['qualification'], 'installation': request['installation'],
        'source_preparation': preparation_ref, 'business_scope_completed': False,
        'whole_app_business_accepted': False, 'whole_app_production_ready': False,
        'historical_runtime_authority_transferred': False, 'automatic_retry': False,
        'original_business_seconds': 600, 'original_cleanup_seconds': 120,
        'audio_output_qualified': False, 'seek_qualified': False, 'album_enumeration_qualified': False,
        'started_unix_ns': time.time_ns(), 'outcome_unknown': False}
    flow = session = lock = None; original_ok = False
    result['descriptor_table_cold'] = shared_case.fd_table()
    c.support(c.SUPPORT_REF)[1]['business_commands.py'].load_capture().load_source_lifecycle()
    before_fds = shared_case.fd_table(); result['descriptor_table_initialized'] = before_fds
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*unused):
        raise LeaseExpired('ORIGINAL_VIDEO_PHASE_ABSOLUTE_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(.001, business_deadline - time.monotonic()))
    try:
        installation, code_closure = shared_case.verify_install(c, request, current_preparation, support, current_modules)
        source_guard(); result['resources_before'] = support.resources()
        host_inputs = originals['install'].host_evidence()
        need(host_inputs == installation['host_inputs_after'], 'EXACT_SAME_CERT_AND_TWO_METHOD_GALLERY_BUILD_PROVENANCE')
        movie = c.parse(c.read_ref(MOVIE_SOURCE)); c.read_ref(TASK_PROOF)
        verify_current_movie_source(movie, originals['install'], support)
        result['static_movie_code_scope'] = {'original_receipt': MOVIE_SOURCE, 'task_option_source': TASK_PROOF,
            'current_candidate_sha256': support.APK_SHA, 'only_two_reviewed_non_movie_methods_changed': True,
            'current_build_provenance': host_inputs, 'historical_runtime_authority_transferred': False}
        lock = shared_session.ActionLock(c, root)
        cls = components['video_session.py'].make_session_class(shared_session, components['shared_api'])
        session = cls(c, support, held, request, root, components, lock, installation, source_guard, prior_ref, business_deadline)
        result['main_before'] = session.guard()
        need(result['main_before'] == installation['main_after'], 'EXACT_ART_AND_ONCE_INSTALL_QUALIFIED_MAIN')
        result['runtime_before'] = c.write_new(Path(root) / 'runtime-before.json',
            current_modules['closure'].recheck_runtime_code(shared_case.runtime_facade(session), code_closure))
        result['identity_before'] = shared_case.identity_matches(c, originals, session, installation['gallery_after'])
        flow = construct(session, root, c, components)
        result.update(flow.result); result['schema'] = SCHEMA; flow.result = result
        try:
            need(not cancelled, 'CANCELLED_BEFORE_ORIGINAL_VIDEO_BUSINESS')
            # This is the exact original execute() business order. Every pixel,
            # provider, file and native-control predicate stays in the original
            # business classes and is not replaced by helper acknowledgements.
            flow.setup()
            flow.media = flow.instrument('seed')['media']
            flow.verify_media('after-seed')
            for index in range(2):
                flow.video_round(index)
            after = flow.diagnostics.diagnostics('after', 10064)
            diag = components['video_diagnostics.py']
            result['diagnostics'] = diag.fresh_crashes(flow.before_diag, after, 10064, flow.before_diag['guest_seconds'])
            need(result['diagnostics']['clear'], 'FRESH_GALLERY_CRASH_OR_ANR')
            result['gallery_after'] = flow.gallery_identity()
            need(result['gallery_after'] == result['gallery_before'], 'GALLERY_IDENTITY_CHANGED')
            result['native_actions_after'] = components['video_identity.py'].identity(session, 'local.pocket4.actions.v2',
                'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058', 10125, 2)
            need(result['native_actions_after'] == result['native_actions_before'], 'NATIVE_ACTIONS_APK_CHANGED')
            result['business_scope_completed'] = True
        except BaseException as error:
            result['error'] = type(error).__name__ + ':' + str(error)
        finally:
            enter_retirement(); signal.setitimer(signal.ITIMER_REAL, 0)
            trigger = c.write_new(Path(root) / 'business-ended.json', {
                'business_scope_completed': result.get('business_scope_completed'), 'error': result.get('error'),
                'cancelled_signals': list(cancelled), 'automatic_retry': False})
            session.begin_cleanup(trigger)
            signal.setitimer(signal.ITIMER_REAL, max(.001, session.deadline - time.monotonic()))
            result['cleanup'] = flow.cleanup()
            try:
                result['guard_after'] = session.guard()
                if hasattr(flow, 'original_rows'):
                    result['original_media_preserved'] = flow.original_media('original-final') == flow.original_rows
                result['caller_after'] = session.caller_status('gallery-video-final')
                result['identity_after'] = shared_case.identity_matches(c, originals, session, installation['gallery_after'])
                result['runtime_after'] = c.write_new(Path(root) / 'runtime-after.json',
                    current_modules['closure'].recheck_runtime_code(shared_case.runtime_facade(session), code_closure))
                result['main_after'] = session.guard()
                need(result['main_after'] == result['main_before'], 'CURRENT_VIDEO_MAIN_CHANGED')
                need(originals['install'].host_evidence() == host_inputs, 'CURRENT_GALLERY_HOST_PROVENANCE_CHANGED')
            except BaseException as error:
                result['final_check_error'] = type(error).__name__ + ':' + str(error)
            result.update(owned_tasks=flow.native_launches, normal_closed_tasks=flow.closed,
                pending_effect=flow.pending, close_pending=flow.close_pending,
                install_pending=flow.fixture.install_pending, uninstall_pending=flow.fixture.uninstall_pending,
                instrument_calls=flow.instrument_calls, view_intent_calls=flow.intent_calls, ui_input_decisions=flow.inputs)
            original_ok = bool(result.get('business_scope_completed') and not result['cleanup']['errors']
                and result.get('guard_before') == result.get('guard_after') and result.get('original_media_preserved')
                and 'error' not in result and 'final_check_error' not in result
                and result['cleanup']['video_deleted'] and result['cleanup']['package_absent']
                and result['cleanup']['staged_apk_removed'] and result.get('owned_directory_removed')
                and flow.native_launches == flow.closed and len(flow.closed) == 2
                and flow.pending is None and flow.close_pending is None
                and not flow.fixture.install_pending and not flow.fixture.uninstall_pending)
            result['claimed_tasks'] = session.claimed_tasks
            result['same_process_action_lock'] = lock.ref; result['final_phase'] = session.phase_ref
    except BaseException as error:
        enter_retirement(); result['outer_error'] = type(error).__name__ + ':' + str(error); original_ok = False
    finally:
        enter_retirement(); signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
        if flow is not None:
            result.update(owned_tasks=flow.native_launches, normal_closed_tasks=flow.closed,
                pending_effect=flow.pending, close_pending=flow.close_pending,
                install_pending=flow.fixture.install_pending, uninstall_pending=flow.fixture.uninstall_pending,
                instrument_calls=flow.instrument_calls, view_intent_calls=flow.intent_calls, ui_input_decisions=flow.inputs)
            try:
                components['video_fixture.py'].close_handles(flow, ('folder_fd', 'folder_parent'))
                # Folder contexts close even when the bounded business cleanup
                # was interrupted. Unknown disk effects are retained verbatim.
                if flow.fixture.staged is not None:
                    components['video_fixture.py'].close_stage_handles(flow.fixture, flow.fixture.staged)
                need(flow.runtime is None or flow.runtime.thread is None, 'VIDEO_OBSERVER_CREATED_A_BACKGROUND_THREAD')
                result['owned_local_contexts_closed'] = True
            except BaseException as error:
                result['local_context_close_error'] = type(error).__name__ + ':' + str(error); original_ok = False
        if session is not None:
            result['host_commands'] = list(session.records); result['host_cancellation_observed'] = session.host_cancelled
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
            source_guard(); result['source_unchanged'] = True; result['resources_after'] = support.resources()
            result['descriptor_table_before'] = before_fds; result['descriptor_table_after'] = shared_case.fd_table()
            need(result['descriptor_table_after'] == before_fds, 'VIDEO_CONTEXT_DESCRIPTOR_LEAK_OR_REPLACEMENT')
            result['all_case_acquired_FDs_closed'] = True
        except BaseException as error:
            result['post_context_error'] = type(error).__name__ + ':' + str(error); original_ok = False
        outstanding_tasks = sorted(set(result.get('owned_tasks', [])) - set(result.get('normal_closed_tasks', [])))
        result['outstanding_owned_tasks'] = outstanding_tasks
        result['outcome_unknown'] = bool(result.get('pending_effect') or result.get('close_pending')
            or result.get('install_pending') or result.get('uninstall_pending') or outstanding_tasks
            or result.get('local_context_close_error') or result.get('session_close_error') or result.get('post_context_error'))
        complete = all(result.get(k) is True for k in ('owned_local_contexts_closed', 'held_session_closed',
            'global_action_lock_exited', 'source_unchanged', 'all_case_acquired_FDs_closed'))
        if original_ok and complete and not result['outcome_unknown'] and not cancelled and not result.get('host_cancellation_observed'):
            result['state'] = SUCCESS
        else:
            result['state'] = 'UNKNOWN_NO_AUTOMATIC_REPLAY' if result['outcome_unknown'] else 'FAILED'
        result['cancelled_signals'] = list(cancelled); result['finished_unix_ns'] = time.time_ns()
        result['elapsed_seconds'] = time.monotonic() - started
        result.update(whole_app_business_accepted=False, whole_app_production_ready=False,
            audio_output_qualified=False, seek_qualified=False, album_enumeration_qualified=False,
            continuous_runtime_sampling_qualified=False, long_duration_stability_qualified=False)
    return result
