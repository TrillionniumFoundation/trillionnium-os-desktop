"""One reviewed Gallery package update on the actually verified new ART.

No automatic retry, uninstall, rollback, grant/revoke, launch, task removal,
media operation, or private app-file read follows an uncertain installation.
"""
from pathlib import Path
import json
import signal
import time

ART_STATE = 'CURRENT_QPR1_MAIN_ALL_2144_CLASSES_ART_VERIFIED_NOT_INSTALLED'
WORK_SECONDS = 210


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def verify_art_receipt(common, reference, request, preparation_ref, support):
    value = common.parse(common.read_ref(reference, 2 * 1024 * 1024))
    need(value['schema'] == 'pocket4-gallery-qpr1-art-qualification-v2' and value['state'] == ART_STATE
         and value['baseline'] == request['baseline'] and value['qualification'] == request['qualification']
         and value['source_preparation'] == preparation_ref and value['candidate_sha256'] == support.APK_SHA
         and value['candidate_dex_sha256'] == '6a994fabd3494dcbf071d727922351f72ff8fdbee0d3d3c1a46b6ed30ca034ee'
         and value['all_2144_stored_statuses_verified'] is True
         and value['both_modified_methods_verified'] is True
         and value['same_historical_ART17_code_closure_claimed'] is False
         and value['historical_runtime_authority_transferred'] is False
         and value['installed'] is False and value['package_mutations'] == value['UI_actions'] == 0
         and value['session_closed'] is True and value['candidate_fd_closed'] is True
         and value['global_action_lock_exited'] is True and value['verifier_input_and_output_FDs_closed'] is True
         and value['actual_completed_command_counts'] == {'analyzer': 1, 'descriptor_proof': 1,
                                                        'compiler': 1, 'oatdump': 3},
         'ACTUAL_CURRENT_MAIN_COMPLETE_ART_QUALIFICATION_REQUIRED')
    before_raw = common.read_ref(value['closure_before'])
    after_raw = common.read_ref(value['closure_after'])
    need(before_raw == after_raw and value['main_before'] == value['main_after']
         and value['host_inputs_before'] == value['host_inputs_after'],
         'ART_QUALIFICATION_INPUT_OR_EXIT_CLOSURE_CHANGED')
    closure = common.parse(before_raw)
    need(closure['schema'] == 'pocket4-gallery-current-code-closure-v1'
         and closure['main_guard'] == value['main_after']
         and closure['same_historical_ART17_code_closure_claimed'] is False,
         'EXACT_CURRENT_CODE_CLOSURE_REQUIRED')
    status = common.parse(common.read_ref(value['class_status_proof']))
    need(status['schema'] == 'pocket4-gallery-qpr1-art-class-status-v2'
         and status['all_2144_stored_statuses_verified'] is True
         and status['both_modified_method_windows_verified'] is True
         and status['complete_unfiltered_class_status']['parsed_classes'] == 2144
         and len(status['modified_methods']) == 2, 'COMPLETE_CURRENT_STORED_CLASS_PROOF_REQUIRED')
    for descriptor, ref in value['modified_method_windows'].items():
        raw = common.read_ref(ref, 131072); observed = status['modified_methods'][descriptor]
        need(len(raw) == observed['window_bytes'] and common.sha(raw) == observed['window_sha256'],
             'ACTUAL_MODIFIED_METHOD_WINDOW_CHANGED')
    commands = [row for row in value['commands'] if row.get('kind')]
    need(len(commands) == 6 and all(row['complete'] is True for row in commands),
         'ALL_CURRENT_OWNED_ART_COMMANDS_REQUIRED')
    for row in commands:
        command = common.parse(common.read_ref(row['receipt']))
        need(command['complete'] is True and command['host_retirement_proved'] is True
             and command['lease_released'] is True and command['lifecycle']['child_started'] is True
             and command['lifecycle']['returncode'] == (50 if row['kind'] == 'flatten' else 0)
             and command['before'] == command['after'] == value['main_after']
             and not command['errors'], 'CURRENT_ART_COMMAND_RECEIPT_CHANGED')
        for stream in ('stdout', 'stderr'):
            common.read_ref(command[stream], 16 * 1024 * 1024)
    return value, closure


class Deadline(BaseException):
    pass


def execute(request, preparation_ref, root, common, originals, held_reader, support, closure_module):
    result = {'schema': 'pocket4-gallery-current-install-v1', 'state': 'PREINSTALL_REJECTED_NO_DISPATCH',
        'baseline': request['baseline'], 'qualification': request['qualification'],
        'source_preparation': preparation_ref, 'current_art_qualification': request['art_qualification'],
        'package': support.PACKAGE, 'candidate_sha256': support.APK_SHA,
        'automatic_retry': False, 'install_attempts': 0, 'install_pending': False,
        'outcome_unknown': False, 'installed': False, 'UI_actions': 0,
        'uninstall_attempts': 0, 'rollback_attempts': 0, 'explicit_permission_mutations': 0,
        'media_or_provider_operations': 0, 'Gallery_business_credit': False,
        'whole_app_business_accepted': False, 'candidate_fd_closed': False,
        'session_closed': False, 'global_action_lock_exited': False,
        'started_unix_ns': time.time_ns()}
    start = time.monotonic(); deadline = start + WORK_SECONDS; session = None
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*unused):
        raise Deadline('GALLERY_CURRENT_INSTALL_ABSOLUTE_WORK_DEADLINE')
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, WORK_SECONDS)
    try:
        art, qualified_closure = verify_art_receipt(common, request['art_qualification'], request,
                                                   preparation_ref, support)
        result['resources_before'] = support.resources()
        result['host_inputs_before'] = originals['install'].host_evidence()
        with common.locked(support.ACTION_LOCK, wait_seconds=5):
            with originals['stdin'].HeldApk() as candidate:
                result['held_candidate_before'] = candidate.verify()
                result['payload_scope'] = originals['install'].payload_exact(candidate, originals['identity'])
                session = support.Session(common, held_reader, request, root, deadline)
                try:
                    result['main_before'] = session.guard()
                    need(result['main_before'] == art['main_after'], 'EXACT_ART_QUALIFIED_MAIN_REQUIRED')
                    result['home_before'] = originals['identity'].home_snapshot(session, art['home_before']['roots'])
                    current = closure_module.snapshot(session, originals['context'], originals['identity'])
                    result['code_before'] = common.write_new(root / 'code-closure-before-install.json', current)
                    need(current == qualified_closure, 'ACTUAL_CURRENT_ART_CODE_CLOSURE_CHANGED_BEFORE_INSTALL')
                    before = originals['identity'].snapshot(session, originals['identity'].OLD_SHA)
                    result['gallery_before'] = before
                    result['original_protected_identity'] = closure_module.preserve_historical_identity(
                        session, originals['identity'], before)
                    common.write_new(root / 'verified-before-dispatch.json', result)
                    session.register('install', support.PM_ARGV, timeout=60, stdin_held=candidate)
                    stdout, stderr, result['install_command'] = session.run('install')
                    result['install_attempts'] = int(session.install_attempted)
                    result['install_pending'] = session.install_pending
                    result['outcome_unknown'] = session.outcome_unknown
                    need(stdout == b'Success\n' and stderr == b'', 'EXACT_PM_SUCCESS_ACK_REQUIRED_NO_AUTOMATIC_REPLAY')
                    result['ack'] = {'stdout_bytes': len(stdout), 'stdout_sha256': common.sha(stdout),
                                     'stderr_bytes': len(stderr), 'stderr_sha256': common.sha(stderr)}
                    after = originals['identity'].snapshot(session, support.APK_SHA)
                    result['gallery_after'] = after
                    result['preservation'] = originals['identity'].require_preserved(before, after)
                    runtime_after = closure_module.recheck_runtime_code(session, qualified_closure)
                    result['runtime_after'] = common.write_new(root / 'runtime-code-after-install.json', runtime_after)
                    result['home_after'] = originals['identity'].home_snapshot(session, art['home_before']['roots'])
                    need(result['home_before']['roots'] == result['home_after']['roots'],
                         'COMPLETE_HOME_TASK_BASELINE_CHANGED_AFTER_INSTALL')
                    need(candidate.verify() == result['held_candidate_before'], 'SIGNED_HOST_CANDIDATE_CHANGED')
                    result['main_after'] = session.guard()
                    need(result['main_after'] == result['main_before'] == art['main_after'],
                         'CURRENT_MAIN_CHANGED_AFTER_INSTALL')
                    result['commands'] = session.records
                    common.write_new(root / 'verified-before-context-exit.json', result)
                finally:
                    result['install_attempts'] = int(session.install_attempted)
                    result['install_pending'] = session.install_pending
                    result['outcome_unknown'] = session.outcome_unknown
                    session.close(); result['session_closed'] = session.closed
                need(candidate.verify() == result['held_candidate_before'], 'FINAL_HOST_APK_CHANGED')
            result['candidate_fd_closed'] = candidate.closed
            result['host_inputs_after'] = originals['install'].host_evidence()
            need(result['host_inputs_after'] == result['host_inputs_before'], 'SIGNED_BUILD_PROVENANCE_CHANGED')
            current_art, current_closure = verify_art_receipt(common, request['art_qualification'], request,
                                                             preparation_ref, support)
            need(current_art == art and current_closure == qualified_closure, 'CURRENT_ART_RECEIPT_CHANGED')
            result['resources_after'] = support.resources()
            need(result['resources_after']['limits'] == result['resources_before']['limits'],
                 'INSTALL_RESOURCE_BOUNDARY_CHANGED')
        result['global_action_lock_exited'] = True
        need(result['install_attempts'] == 1 and result['session_closed'] and result['candidate_fd_closed']
             and result['global_action_lock_exited'] and result['runtime_after'],
             'COMPLETE_INSTALL_AND_NORMAL_CONTEXT_EXIT_REQUIRED')
        # The pending marker is immutable evidence. Only this final receipt may
        # qualify the outcome, after all contexts and ownerships have exited.
        result['install_pending'] = result['outcome_unknown'] = False
        result['installed'] = True
        result['state'] = 'CURRENT_ART_VERIFIED_GALLERY_INSTALLED_ALL_PROTECTED_IDENTITY_PRESERVED'
    except BaseException as error:
        result['error'] = type(error).__name__ + ':' + str(error)
        if session is not None:
            result['install_attempts'] = int(session.install_attempted)
            result['commands'] = session.records; result['session_closed'] = session.closed
            if session.install_attempted:
                result['install_pending'] = result['outcome_unknown'] = True
                result['state'] = 'INSTALL_ATTEMPTED_OUTCOME_UNKNOWN_NO_AUTOMATIC_REPLAY'
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
        result['finished_unix_ns'] = time.time_ns(); result['elapsed_seconds'] = time.monotonic() - start
    return result
