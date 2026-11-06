#!/usr/bin/env python3
"""Strict, pure reparser for one actual rejected-before-dispatch owned-QA case.

The OriginalSequence grammar is inherited verbatim. No current authority,
namespace entry, instrumentation or compatibility publication is provided.
"""
import base64
import hashlib
import json
import re
import stat

FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
CASE_STEP = 'search-click-after-partial-commit-01'
TASK = 878
HELPER_UID = 10157
SCOPE_SHA = '08c014646be1d32ef9eacc119f7930b941fc696333bd4cff9d74106f19dba516'
LAUNCH_SHA = '54a669eb54fa0dcf6df5afcd17848af7511c2122623192051eb6370e42bfbb06'
NATIVE_RECEIPT_SHA = 'e1b09112b1be1ec8095cd5b7049131e0e8bd13ad8b4e38803e3c19d02e5e65a3'
HELD_HELPER = '/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry'
CASE_SHA = '15cff75541c2b1219a92ada5ed7c3e38cd736660f848b7c216335b039b0cb58e'
FAILED_JOB = '1a1b30305de-fc05-8072'
FAILED_WIRE_SHA = 'e901b1431e5df17493158a9222f27deaf9b29b0e22f2053fcca2ae4cba1d86ae'
INSPECTION_WIRE_SHA = '3d5cf94834c0a7234b9b0e364ebc35abd1329defada5ee26acc42a867672854e'
BUNDLE = {'bytes': 1102634, 'path': '/home/alex/work/pocket4-beike-search-click-failure-evidence-20261106-r1/bundle.private.json', 'sha256': '85b3b9801685a427a484cc81b80de64e66df49ceb477efa99901ac2dfb01cee4'}
POSTCONDITION = None
PRIOR_JOB = '1a1b2f182c1-fc05-803d'
UI_SOURCE = {'path': '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1/owned_ui_request_once.py', 'bytes': 25377, 'sha256': 'c394598e477f1912378c6c3d582850a196e64f77791d0b7f5c4d498ec9b61e38'}
PRIOR_STDOUT = {'path': '/home/alex/work/pocket4-beike-no-action-runtime-20261106-r1/prior-inspect.stdout.original.jsonl', 'bytes': 13947, 'sha256': '23639dfd1822118c1379e306ba45bf2a1e0d5c8b30ee660c6b50125e8b7cdf84'}
PRIOR_TERMINAL = {'path': '/home/alex/work/pocket4-beike-no-action-runtime-20261106-r1/prior-inspect.terminal.original.json', 'bytes': 733, 'sha256': '8c1b239ea57641d497f59f8f417ec66c663d4290366bb4f2fa008f0460109037'}
STAT_FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_rdev', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
EMPTY_SHA = hashlib.sha256(b'').hexdigest()


class Rejected(RuntimeError):
    pass


def need(value, code):
    if not value:
        raise Rejected(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


def document(raw, maximum=2 * 1024 * 1024):
    need(type(raw) is bytes and 0 < len(raw) <= maximum, 'BOUNDED_ORIGINAL_JSON')
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, 'DUPLICATE_ORIGINAL_JSON_KEY')
            result[key] = value
        return result
    def constant(_):
        raise Rejected('NONFINITE_ORIGINAL_JSON')
    result = json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=pairs,
                        parse_constant=constant)
    need(type(result) is dict, 'ORIGINAL_JSON_OBJECT_REQUIRED')
    return result


def fixed_launch(launch, core):
    need(type(launch) is dict and launch.get('task') == TASK and
         type(launch['task']) is int and launch.get('package') == core.PACKAGE and
         launch.get('epoch_sha256') == core.MAIN_EPOCH and
         launch.get('native_receipt_sha256') == NATIVE_RECEIPT_SHA and
         launch.get('prelaunch_absent') is True and launch.get('cleanup_allowed') is True and
         type(launch.get('prelaunch_task_ids')) is list and
         TASK not in launch['prelaunch_task_ids'], 'EXACT_ACTUAL_TASK878_NATIVE_SCOPE')
    core.name(launch.get('launch_step'))
    return launch


def binding_identity(binding, core, qa):
    core.held_binding_identity(binding)
    need(binding.get('framework_epoch_sha256') == qa.MAIN_EPOCH and
         binding.get('runtime_epoch_sha256') == qa.RUNTIME_EPOCH and
         binding.get('app_scope_sha256') == qa.APP_SCOPE_SHA and
         binding.get('package') == qa.PACKAGE and binding.get('uid') == qa.UID and
         binding.get('ui_actions_performed_by_binding') is False and
         binding.get('production_ready') is False and
         binding['target'].get('pidfd_held') is True and
         binding['target'].get('numeric_target_used_for_entry') is False,
         'ORIGINAL_HELD_R5_RUNTIME_APP_AND_CLASSPATH_IDENTITY')
    return binding


def require_original_failed_suffix(stdout, stderr, returncode, request, before, after, qa):
    """Prove one finish(0) rejection without manufacturing a success assessment.

    The frozen Java source sets actionAttempted and writes action acknowledgements
    only after the exact INSPECTED_TREE_OR_WINDOW_CHANGED check. Its complete
    actual wire, independent states and normal host command are required here.
    """
    need(returncode == 0 and type(returncode) is int and stderr == b'',
         'FAILED_HELPER_STILL_REQUIRES_NORMAL_HOST_COMMAND')
    try:
        qa.parse_completed(stdout, stderr, returncode, request, HELPER_UID)
    except qa.ProtocolError as error:
        need(str(error) == 'EXACT_SUCCESSFUL_FINISH_REQUIRED',
             'ORIGINAL_SUCCESS_PARSER_MUST_KEEP_EXACT_REJECTION')
    else:
        raise Rejected('FAILED_WIRE_CANNOT_BECOME_SUCCESS')
    diagnostic = qa.failure_diagnostic(stdout, request, HELPER_UID)
    text = stdout.decode('utf-8', 'strict')
    need('INSTRUMENTATION_FAILED' not in text and 'INSTRUMENTATION_ABORTED' not in text,
         'NO_FRAMEWORK_INSTRUMENTATION_FAILURE')
    encoded = re.findall(r'^INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64=([^\r\n]+)\r?$', text, re.M)
    finishes = re.findall(r'^INSTRUMENTATION_CODE: (-?[0-9]+)\r?$', text, re.M)
    need(len(encoded) == 1 and finishes == ['0'], 'ONE_ACTUAL_FAILURE_WIRE_AND_FINISH')
    raw = qa.decode_wire(encoded[0]); value = document(raw)
    need(qa.canonical(value) == raw and sha(raw) == FAILED_WIRE_SHA == diagnostic['wire_sha256'],
         'EXACT_ACTUAL_FAILED_HELPER_WIRE_BYTES')
    keys = {'protocol', 'nonce', 'op', 'request_sha256', 'wire_codec', 'self_uid', 'self_pid',
            'started_elapsed_ms', 'host_scope_attestation', 'activity_verified_inside_helper',
            'target_uid_verified', 'accessibility_state_before_connection',
            'claim_persistence_completed', 'action_attempted', 'ok', 'error', 'secondary_errors',
            'automatic_retry', 'outcome_unknown', 'business_success_verified', 'restoration',
            'window_observation', 'tree_observations', 'inspection_idle_observation',
            'accessibility_mode_restoration_verified', 'requires_post_termination_state_check',
            'helper_work_completed', 'finished_elapsed_ms'}
    need(set(value) == keys, 'EXACT_PRE_DISPATCH_FAILURE_FIELDS_NO_ACKNOWLEDGEMENT')
    need(value['protocol'] == qa.PROTOCOL and value['nonce'] == request['nonce'] and
         value['op'] == request['op'] == 'click' and
         value['request_sha256'] == sha(qa.validate_request(request)) and
         value['wire_codec'] == 'gzip-canonical-json-v1' and
         value['self_uid'] == HELPER_UID and value['self_pid'] == 80169,
         'EXACT_ACTUAL_FAILURE_REQUEST_HELPER_IDENTITY')
    need(value['ok'] is False and value['error'] == 'INSPECTED_TREE_OR_WINDOW_CHANGED' and
         value['claim_persistence_completed'] is True and value['helper_work_completed'] is True and
         value['secondary_errors'] == [] and value['action_attempted'] is False and
         value['outcome_unknown'] is False and value['automatic_retry'] is False and
         value['business_success_verified'] is False and
         value['accessibility_mode_restoration_verified'] is None,
         'EXPLICIT_REJECTED_NO_DISPATCH_WITHOUT_SECONDARY_FAILURE')
    start, finish = value['started_elapsed_ms'], value['finished_elapsed_ms']
    need(type(start) is int and type(finish) is int and 0 <= start <= finish and
         finish - start <= 12000 and start == 1030402143 and finish == 1030402433,
         'ACTUAL_FAILED_HELPER_TIME_BOUND')
    need(value['host_scope_attestation'] == request['scope'] and
         value['activity_verified_inside_helper'] is False and value['target_uid_verified'] == qa.UID and
         value['requires_post_termination_state_check'] is True,
         'FAILED_HELPER_REMAINS_BOUND_TO_ORIGINAL_HOST_SCOPE')
    restore = value['restoration']
    need(type(restore) is dict and restore.get('service_info_verified') is True and
         restore.get('service_info_captured') is True and restore.get('connection_flags') == 1,
         'ACTUAL_FAILED_HELPER_OWN_SERVICE_RESTORE')
    fields = ('service_flags_before', 'service_flags_during', 'service_flags_after',
              'service_capabilities_before', 'service_capabilities_after')
    need(all(type(restore.get(key)) is int for key in fields) and
         restore['service_flags_before'] == restore['service_flags_after'] and
         restore['service_capabilities_before'] == restore['service_capabilities_after'] and
         restore['service_flags_during'] == (restore['service_flags_before'] | 16 | 64) and
         all(restore[key] & 4 == 0 for key in fields[:3]),
         'FAILED_HELPER_ACTUAL_FLAGS_CAPABILITIES_AND_NONEXPLORATION')
    qa.state(value['accessibility_state_before_connection'])
    first, last = before['helper'], after['helper']
    need(first['op'] == last['op'] == 'state' and first['self_uid'] == last['self_uid'] == HELPER_UID and
         first['ui_automation_connected'] is False and last['ui_automation_connected'] is False and
         first['state'] == value['accessibility_state_before_connection'] == last['state'] and
         first['finished_elapsed_ms'] <= start <= finish <= last['started_elapsed_ms'],
         'REAL_INDEPENDENT_STATES_BRACKET_FAILED_HELPER_RETIREMENT')
    qa.inspection_idle_observation(value['inspection_idle_observation'], 'click', start, False)
    window = qa.window_observation(value['window_observation'], ready_required=True)
    trees = qa.tree_observations(value['tree_observations'], 'click', complete_required=False)
    need(len(trees) == 1 and trees[0]['purpose'] == 'action_target' and trees[0]['complete'] is True and
         start <= trees[0]['began_elapsed_ms'] <= trees[0]['last_elapsed_ms'] <= finish,
         'ONE_COMPLETE_TARGET_CAPTURE_BEFORE_REJECTION_NO_FINAL_CAPTURE')
    return {'schema': 'pocket4-owned-helper-rejected-before-dispatch-state-proof-v1',
            'wire_sha256': sha(raw), 'instrumentation_finish_code': 0,
            'helper_error': value['error'], 'helper_action_attempted': False,
            'helper_outcome_unknown': False, 'original_success_parser_rejection_preserved': True,
            'successful_instrumentation_claimed': False, 'click_acknowledgement_present': False,
            'complete_original_target_capture_count': 1,
            'selected_connection_window_id': window['selected_window_id'],
            'independent_state_wires': [before['wire_sha256'], after['wire_sha256']],
            'equal_accessibility_state_sha256': sha(qa.canonical(first['state'])),
            'own_service_restore_readback_verified': True, 'secondary_errors': [],
            'helper_started_elapsed_ms': start, 'helper_finished_elapsed_ms': finish,
            'app_autonomous_changes_excluded': False, 'business_success_verified': False}


class OriginalSequence:
    """Reparse the exact existing Session.sequence command/transport grammar."""
    def __init__(self, files, *, core, qa, transport, tasks, binding, launch, build,
                 installed, parent_pid, started_utc, ended_utc):
        need(type(files) is dict and 1 <= len(files) <= 400 and
             all(type(name) is str and '/' not in name and '\\' not in name and
                 type(raw) is bytes and len(raw) <= 2 * 1024 * 1024 for name, raw in files.items()) and
             sum(map(len, files.values())) <= 16 * 1024 * 1024, 'CLOSED_BOUNDED_ORIGINAL_STEP_BYTES')
        self.files, self.used = files, set()
        self.core, self.qa, self.transport, self.tasks = core, qa, transport, tasks
        self.binding, self.launch, self.build, self.installed = binding, launch, build, installed
        self.parent_pid, self.authority = parent_pid, None
        self.command_index = self.transport_index = 0
        self.previous_end = core.timestamp(started_utc); self.ended = core.timestamp(ended_utc)
        need(self.previous_end <= self.ended, 'ACTUAL_STEP_UTC_ORDER')
        self.previous_helper_end = None
        self.command_proofs = []; self.phase_proofs = []

    def raw(self, name):
        need(name in self.files and name not in self.used, 'ONE_EXACT_ORIGINAL_FILE_CONSUMPTION')
        self.used.add(name)
        return self.files[name]

    def read(self, name):
        return document(self.raw(name))

    def command(self, argv, timeout, mutation=False, private=False):
        self.transport_index += 1; stem = 'transport-%03d.' % self.transport_index
        identity = {'sequence': self.transport_index, 'epoch_sha256': self.qa.MAIN_EPOCH,
            'package': self.qa.PACKAGE, 'uid': self.qa.UID,
            'command_sha256': sha(json.dumps(argv, ensure_ascii=False, separators=(',', ':')).encode()),
            'timeout_seconds': timeout, 'inner_timeout_seconds': max(1, timeout - 5),
            'automatic_retry': False, 'numeric_pid_target_used': False}
        ti = self.read(stem + 'intent.json'); tc = self.read(stem + 'command-result.json')
        tv = self.read(stem + 'verified-result.json')
        need(ti == identity and tc == tv and all(tc.get(k) == v for k, v in identity.items()) and
             set(tc) == set(identity) | {'returncode', 'stdout_bytes', 'stderr_bytes', 'stdout_sha256',
                 'stderr_sha256', 'action_attempted', 'outcome_unknown'} and
             type(tc.get('returncode')) is int and tc['returncode'] == 0 and
             tc.get('action_attempted') is True and tc.get('outcome_unknown') is False and
             tc.get('stderr_bytes') == 0 and tc.get('stderr_sha256') == EMPTY_SHA and
             type(tc.get('stdout_bytes')) is int and 0 <= tc['stdout_bytes'] <= 4 * 1024 * 1024 and
             re.fullmatch('[0-9a-f]{64}', tc.get('stdout_sha256', '')),
             'EXACT_COMPLETE_TRANSPORT_LEASE_RELEASE_AND_POST_GUARD')
        if private:
            need(argv == ['/system/bin/dumpsys', 'window', 'displays'] and timeout == 15 and
                 mutation is False and tc['stdout_bytes'] > 0, 'ORIGINAL_PRIVATE_FOREGROUND_TRANSPORT_ONLY')
            return None
        self.command_index += 1; stem = 'command-%03d' % self.command_index
        ci = self.read(stem + '.intent.json'); result_raw = self.raw(stem + '.result.json')
        cr = document(result_raw); out = self.raw(stem + '.stdout'); err = self.raw(stem + '.stderr')
        self.core.command_success(ci, cr, out, err, mutation, timeout)
        route = self.core.command_argv(ci, argv, timeout, HELD_HELPER,
                                      self.binding['classpath']['values'], self.transport)
        need(route['parent_pid'] == self.parent_pid and
             (self.authority is None or route == self.authority), 'ONE_ACTUAL_ORIGINAL_OWNED_CHILD_AUTHORITY')
        self.authority = route
        need(self.previous_end <= self.core.timestamp(ci['started_utc']) <=
             self.core.timestamp(cr['ended_utc']) <= self.ended, 'ORIGINAL_COMMAND_CHRONOLOGY')
        self.previous_end = self.core.timestamp(cr['ended_utc'])
        need(tc['stdout_bytes'] == len(out) and tc['stderr_bytes'] == len(err) and
             tc['stdout_sha256'] == sha(out) and tc['stderr_sha256'] == sha(err),
             'TRANSPORT_AND_RECORDED_COMMAND_ARE_SAME_ACTUAL_BYTES')
        self.command_proofs.append({'index': self.command_index, 'transport': self.transport_index,
            'result_sha256': sha(result_raw), 'stdout_sha256': sha(out), 'stderr_sha256': sha(err),
            'returncode': 0, 'normal_joined': True, 'mutation': mutation})
        return out, err, cr, sha(result_raw)

    def packages(self):
        out, _, _, _ = self.command(['/system/bin/cmd', 'package', 'list', 'packages', '-U',
                                    '--user', '0', self.core.HELPER], 8)
        need(out.decode('utf-8', 'strict').splitlines() ==
             ['package:' + self.core.HELPER + ' uid:' + str(HELPER_UID)], 'ACTUAL_ORIGINAL_HELPER_UID_COMMAND')
        out, _, _, _ = self.command(['/system/bin/cmd', 'package', 'path', '--user', '0', self.core.HELPER], 8)
        need(out.decode('utf-8', 'strict').splitlines() == ['package:' + self.installed['base_apk']],
             'ACTUAL_ORIGINAL_HELPER_APK_PATH_COMMAND')

    def task(self):
        out, _, _, _ = self.command(['/system/bin/cmd', 'activity', 'stack', 'list'], 20)
        roots, _ = self.tasks.parse_stacks(out.decode('utf-8', 'strict'))
        need(self.tasks.exact_leaf(roots, TASK, self.qa.PACKAGE), 'ORIGINAL_TASK878_EXACT_OWNED_LEAF')

    def foreground(self):
        self.command(['/system/bin/dumpsys', 'window', 'displays'], 15, private=True)

    def instrument(self, request, failure=False):
        self.qa.validate_request(request)
        nonce = request['nonce']
        need(self.read(nonce + '.request.json') == request, 'ORIGINAL_NONCE_REQUEST_NOT_RECONSTRUCTED_DIFFERENTLY')
        out, err, cr, cr_sha = self.command(self.qa.instrumentation_argv(request), 20,
                                           mutation=request['op'] == 'click')
        if failure:
            try:
                self.qa.parse_completed(out, err, cr['returncode'], request, HELPER_UID)
            except self.qa.ProtocolError as error:
                need(str(error) == 'EXACT_SUCCESSFUL_FINISH_REQUIRED', 'ORIGINAL_STRICT_FAILURE_REQUIRED')
                primary = {'type': type(error).__name__, 'message': str(error)}
            else:
                raise Rejected('ONLY_THE_ACTUAL_FAILED_SUFFIX_ALLOWED')
            diagnostic = self.qa.failure_diagnostic(out, request, HELPER_UID)
            saved = self.read(nonce + '.failed-assessment.json')
            need(saved == {'request_nonce': nonce, 'operation': 'click', 'qualified_success': False,
                 'command_result_sha256': cr_sha, 'stdout_sha256': sha(out), 'stderr_sha256': sha(err),
                 'primary_error': primary, 'helper_rejection': diagnostic},
                 'COMPLETE_ORIGINAL_FAILED_ASSESSMENT_RECOMPUTED')
            helper = {'started_elapsed_ms': diagnostic['started_elapsed_ms'],
                      'finished_elapsed_ms': diagnostic['finished_elapsed_ms']}
            result = {'failed_stdout': out, 'failed_stderr': err, 'returncode': cr['returncode'],
                      'request': request, 'diagnostic': diagnostic}
            wire_sha = diagnostic['wire_sha256']
        else:
            result = self.qa.parse_completed(out, err, cr['returncode'], request, HELPER_UID)
            result.update(recorder_command_result_sha256=cr_sha, held_transport_returned_after_post_guard=True)
            need(self.read(nonce + '.assessment.json') == result, 'ORIGINAL_SUCCESS_ASSESSMENT_RECOMPUTED')
            helper = result['helper']; wire_sha = result['wire_sha256']
        need(self.previous_helper_end is None or self.previous_helper_end <= helper['started_elapsed_ms'],
             'ORIGINAL_ANDROID_HELPER_MONOTONIC_ORDER')
        self.previous_helper_end = helper['finished_elapsed_ms']
        self.phase_proofs.append({'nonce': nonce, 'operation': request['op'], 'command': self.command_index,
            'wire_sha256': wire_sha, 'successful_instrumentation': not failure,
            'started_elapsed_ms': helper['started_elapsed_ms'], 'finished_elapsed_ms': helper['finished_elapsed_ms']})
        return result

    def sequence(self, plan, *, saved=None, rejected=False):
        qa, names = self.qa, plan['nonces']
        need(plan['operation'] in ('inspect', 'click') and (not rejected or plan['operation'] == 'click'),
             'FIXED_ORIGINAL_SEQUENCE_OPERATIONS')
        scope = document(self.files[names['inspect'] + '.request.json'])['scope']; qa.scope(scope)
        def req(phase, op, **extra):
            return {'protocol': qa.PROTOCOL, 'nonce': names[phase], 'op': op, **extra}
        self.packages(); self.task()
        before = self.instrument(req('before', 'state')); self.foreground()
        inspected = self.instrument(req('inspect', 'inspect', scope=scope)); self.foreground()
        middle = inspected
        if plan['operation'] == 'click':
            node = qa.select_unique_clickable(inspected['helper']['inspection'], plan['selector'])
            action = req('action', 'click', scope=scope, inspection_nonce=names['inspect'],
                         inspection_sha256=inspected['wire_sha256'], **node)
            middle = self.instrument(action, failure=rejected)
        after = self.instrument(req('after', 'state')); self.foreground(); self.task(); self.packages()
        # Inspection is successful in all three actual sequences. This check
        # does not replace the distinct failed-helper retirement proof below.
        inspect_restore = qa.assess_restoration(before, inspected, after)
        if rejected:
            retirement = require_original_failed_suffix(middle['failed_stdout'], middle['failed_stderr'],
                middle['returncode'], middle['request'], before, after, qa)
            restore = None
        else:
            retirement = None
            restore = qa.assess_restoration(before, middle, after)
            if plan['operation'] == 'click':
                need(middle['helper']['action_window'] == inspected['helper']['inspection']['window'],
                     'ORIGINAL_ACKNOWLEDGED_ACTION_WINDOW_MATCH')
        if saved is not None:
            need(not rejected and saved.get('installed_before') == saved.get('installed_after') == self.installed and
                 saved.get('owned_task') == self.launch and saved.get('foreground_before') == scope and
                 saved.get('old_v2_helper_called') is False and saved.get('business_success_verified') is False and
                 saved.get('error') is None and saved.get('secondary_errors') == [] and
                 all(saved.get(key) is True for key in ('after_state_attempted', 'after_state_completed',
                      'post_state_matches_before', 'restoration_qualified')) and
                 saved.get('inspection_wire_sha256') == inspected['wire_sha256'] and
                 saved.get('accessibility_restoration') == restore and
                 saved.get('post_termination_state') == {'nonce': names['after'], 'wire_sha256': after['wire_sha256'],
                      'state': after['helper']['state'], 'helper_uid': HELPER_UID, 'ui_automation_connected': False},
                 'SAVED_COMPLETE_SEQUENCE_MATCHES_ACTUAL_RAW_AND_STATES')
            qa.scope(saved.get('foreground_after'))
            if plan['operation'] == 'inspect':
                need(saved['foreground_after'] == scope, 'ORIGINAL_READONLY_FOREGROUND_UNCHANGED')
            else:
                need(saved.get('click_acknowledged') is True, 'ORIGINAL_SUCCESSFUL_PREFIX_ACKNOWLEDGED')
        return {'before': before, 'inspect': inspected, 'middle': middle, 'after': after,
                'foreground_scope_from_actual_request': scope, 'restoration': restore,
                'successful_inspection_state_check': inspect_restore, 'failed_helper_retirement': retirement}

    def complete(self, commands, transports):
        need(self.command_index == commands and self.transport_index == transports and self.used == set(self.files),
             'ALL_AND_ONLY_ACTUAL_ORIGINAL_STEP_FILES_VALIDATED')


def original_terminal(value, job, byte_count):
    need(value.get('job_id') == job and value.get('state') == 'succeeded' and value.get('exit_code') == 0 and
         all(value.get(key) is True for key in ('audit_recorded', 'output_complete', 'output_durable',
                                               'terminal_publication_confirmed')) and
         all(value.get(key) is False for key in ('timed_out', 'cancelled', 'automatic_retry')) and
         value.get('log_bytes') == {'stdout': {'seen': byte_count, 'stored': byte_count},
                                     'stderr': {'seen': 0, 'stored': 0}} and
         value.get('log_synced') == {'stdout': True, 'stderr': True} and
         value.get('log_truncated') == {'stdout': False, 'stderr': False} and
         value.get('log_errors') == {'stdout': None, 'stderr': None},
         'ACTUAL_AUTHORITATIVE_OBSERVER_DURABLE_COMPLETE_ZERO')


def bundle_originals(raw, reader, core):
    need(len(raw) == BUNDLE['bytes'] and sha(raw) == BUNDLE['sha256'], 'EXACT_ACTUAL_SINGLE_FAILURE_BUNDLE')
    value = document(raw, maximum=2 * 1024 * 1024)
    need(raw == canonical(value) + b'\n' and set(value) == {
        'actual_job', 'approved_for_Git', 'contains_private_UI_evidence', 'files', 'flow',
        'full_original_bytes', 'original_stdout', 'original_terminal', 'schema', 'step', 'step_file_set'} and
        value['schema'] == 'pocket4-task878-failed-case-private-original-bytes-v1' and
        value['actual_job'] == FAILED_JOB and value['flow'] == FLOW and value['step'] == CASE_STEP and
        value['full_original_bytes'] is True and value['contains_private_UI_evidence'] is True and
        value['approved_for_Git'] is False and type(value['files']) is dict and len(value['files']) == 101,
        'CLOSED_ACTUAL_PRIVATE_ARCHIVE_NOT_NEW_UI_EVIDENCE')
    expected_result, lifetime = reader.validate_actual(core)
    for key, encoded_key, digest_key in (('original_stdout', 'actual_stdout_base64', 'actual_stdout_sha256'),
                                         ('original_terminal', 'terminal_base64', 'terminal_sha256')):
        row = value[key]
        need(type(row) is dict and set(row) == {'base64', 'bytes', 'sha256'}, 'EXACT_ORIGINAL_CONTROLLER_ARCHIVE_ROW')
        body = base64.b64decode(row['base64'], validate=True)
        need(body == base64.b64decode(reader.CONFIG[encoded_key], validate=True) and
             len(body) == row['bytes'] and sha(body) == row['sha256'] == reader.CONFIG[digest_key],
             'ARCHIVE_MATCHES_ORIGINAL_FAILED_CONTROLLER_AND_TERMINAL')
    originals, files = {}, {}
    total = 0
    for key, row in sorted(value['files'].items()):
        need(type(key) is str and type(row) is dict and
             set(row) == {'path', 'bytes', 'sha256', 'stat', 'base64'}, 'CLOSED_ORIGINAL_ARCHIVE_FILE_ROW')
        if key.startswith('source/'):
            label = key[7:]
            need(label in reader.CONFIG['sources'], 'ONLY_FROZEN_READER_SOURCE_MEMBERS')
            expected = reader.CONFIG['sources'][label]
        elif key.startswith('input/'):
            label = key[6:]
            need(label in ('case', 'request', 'scope', 'launch'), 'ONLY_FOUR_ORIGINAL_INPUTS')
            expected = reader.CONFIG[label]
        else:
            need(key.startswith('step/') and '/' not in key[5:] and '\\' not in key[5:] and
                 key[5:] in value['step_file_set'], 'ONE_ORIGINAL_FAILED_STEP_MEMBER')
            expected = {'path': FLOW + '/steps/' + CASE_STEP + '/' + key[5:],
                        'bytes': row['bytes'], 'sha256': row['sha256']}
        need(type(row['bytes']) is int and 0 <= row['bytes'] <= 2 * 1024 * 1024 and
             re.fullmatch('[0-9a-f]{64}', row['sha256']) and
             {k: row[k] for k in ('path', 'bytes', 'sha256')} == expected,
             'ORIGINAL_FILE_PATH_SIZE_AND_HASH_NOT_CALLER_SELECTED')
        body = base64.b64decode(row['base64'], validate=True)
        need(len(body) == row['bytes'] and sha(body) == row['sha256'], 'COMPLETE_ORIGINAL_FILE_BYTES')
        metadata = row['stat']
        need(type(metadata) is dict and set(metadata) == set(STAT_FIELDS) and
             all(type(x) is int and x >= 0 for x in metadata.values()) and
             stat.S_ISREG(metadata['st_mode']) and metadata['st_uid'] == 0 and metadata['st_nlink'] == 1 and
             metadata['st_size'] == len(body), 'ORIGINAL_ROOT_OWNED_REGULAR_FULL_IDENTITY')
        need(row['path'] not in originals, 'ONE_ARCHIVED_ORIGINAL_PATH')
        originals[row['path']] = (body, metadata)
        if key.startswith('step/'):
            files[key[5:]] = body
        total += len(body)
    need(total == 782840 and len(files) == 90 and len(originals) == 101 and
         sorted(files) == value['step_file_set'], 'ALL_101_ORIGINALS_AND_EXACT_90_STEP_FILES')
    return value, originals, files, expected_result, lifetime


def prior_installed_identity(raw, terminal_raw, base, core):
    need(len(raw) == PRIOR_STDOUT['bytes'] and sha(raw) == PRIOR_STDOUT['sha256'] and
         len(terminal_raw) == PRIOR_TERMINAL['bytes'] and sha(terminal_raw) == PRIOR_TERMINAL['sha256'],
         'EXACT_PREVIOUS_ACTUAL_INSPECT_IDENTITY_REFERENCE')
    terminal = document(terminal_raw)
    original_terminal(terminal, PRIOR_JOB, len(raw))
    outer = document(raw)
    need(outer['schema'] == 'pocket4-fixed-reusable-owned-ui-result-v1' and outer['ok'] is True and
         outer['errors'] == [] and outer['outcome_unknown'] is False and outer['kind'] == 'plan' and
         outer['step'] == 'inspect-after-partial-commit-01' and outer['flow'] == FLOW and outer['task'] == TASK and
         outer['source'] == UI_SOURCE and outer['all_owned_child_resources_retired_by_normal_pidfd_exit'] is True and
         outer['allows_new_mutation_without_original_Flow_checks'] is False and outer['automatic_retry'] is False and
         outer['original_UNKNOWN_rewritten'] is False and outer['reconciliation_published'] is False,
         'PREVIOUS_INSPECT_COMPLETED_IDENTITY_REFERENCE_NOT_LATER_OBSERVER')
    stderr = outer['child_stderr_original'].encode('utf-8')
    need(stderr == b'' and outer['child_stderr_bytes'] == 0 and outer['child_stderr_sha256'] == sha(b''),
         'PREVIOUS_NORMAL_CHILD_EMPTY_STDERR')
    base.require_owned_exit(outer['child_lifecycle'], stderr)
    need(outer['child_lifecycle']['child_pid'] == 2414622, 'EXACT_PREVIOUS_HELPER_IDENTITY_REFERENCE_CHILD')
    child_raw = outer['child_stdout_original'].encode('utf-8')
    need(len(child_raw) == outer['child_stdout_bytes'] == 10667 and
         sha(child_raw) == outer['child_stdout_sha256'] ==
         '4b0ad68e70e8383c49c11634ac3229b66d438f5a17a9820c1c1ceb3dcad9bc53',
         'PREVIOUS_ACTUAL_OWNED_CHILD_RAW_BYTES')
    child = document(child_raw)
    need(child['schema'] == 'pocket4-fixed-reusable-owned-ui-child-v1' and child['ok'] is True and
         child['errors'] == [] and child['declared_mutation'] is False and child['original_entry_invoked'] is True and
         child['original_returncode'] == 0 and child['outcome_unknown'] is False and child['source'] == UI_SOURCE and
         child['flow'] == FLOW and child['step'] == outer['step'] and child['task'] == TASK and
         child['original_namespace_authority_released'] is True and child['manual_library_close'] is False,
         'PREVIOUS_READONLY_SOURCE_AND_RETIREMENT_QUALIFIED')
    result_raw = child['original_stdout'].encode('utf-8')
    need(len(result_raw) == child['original_stdout_bytes'] == 5752 and
         sha(result_raw) == child['original_stdout_sha256'] ==
         '612ed6e8b154843990feec5ad647727a747e46faa540896c1534f561bd8ebd7d',
         'EXACT_PREVIOUS_ADAPTER_RESULT_IDENTITY_REFERENCE')
    result = document(result_raw)
    need(result['ok'] is True and result['error'] is None and result['secondary_errors'] == [] and
         result['action_attempted'] is False and result['outcome_unknown'] is False and
         result['installed_before'] == result['installed_after'] and result['owned_task'] == fixed_launch(result['owned_task'], core) and
         all(result[k] is True for k in ('restoration_qualified', 'after_state_attempted',
                                        'after_state_completed', 'post_state_matches_before')),
         'PREVIOUS_FULL_INSTALLED_HELPER_REFERENCE_NOT_A_NEW_OBSERVATION')
    build = core.fixed_build(result['build'])
    installed = core.installed_identity(result['installed_before'], build)
    return installed, result['ended_utc'], {'job_id': PRIOR_JOB, 'stdout': PRIOR_STDOUT,
        'terminal': PRIOR_TERMINAL, 'usage': 'previously_qualified_installed_helper_identity_only',
        'is_later_observer_for_failed_click': False, 'no_current_tree_or_action_authority': True}


def verify_failed_single_case(files, scope, launch, case, expected_result, installed, prior_ended,
                              *, core, qa, adapter, transport, tasks, runner):
    core.fixed_scope(scope); fixed_launch(launch, core)
    runner.validate_case(case, adapter, qa)
    need(sha(canonical(case) + b'\n') == CASE_SHA and case['name'] == 'beike-search-click-observe-01' and
         len(case['steps']) == 1 and case['steps'][0]['plan']['operation'] == 'click' and
         case['steps'][0]['post_inspection']['operation'] == 'inspect', 'ONE_ACTUAL_DECLARED_SEARCH_CLICK_ONLY')
    intent, result, binding = (document(files[name]) for name in ('intent.json', 'result.json', 'held-main-binding.json'))
    need(intent.get('operation') == 'owned-qa-case' and intent.get('mutation') is True and
         intent.get('scope') == scope and intent.get('automatic_retry') is False and
         all(intent.get(key) is None for key in ('unknown_step', 'observation_step', 'postcondition')) and
         set(intent['request']) == {'case', 'case_sha256', 'build'} and intent['request']['case'] == case and
         intent['request']['case_sha256'] == CASE_SHA, 'ORIGINAL_SINGLE_CASE_INTENT')
    need(result == expected_result and result['ok'] is False and result['outcome_unknown'] is True and
         result['action_attempted'] is True and result['original_action_outcomes_rewritten'] is False and
         result['production_ready'] is False and result['business_success_verified'] is False and
         result['errors'] == [{'code': 'EXACT_SUCCESSFUL_FINISH_REQUIRED', 'type': 'ProtocolError'}] and
         result['steps'] == [] and 'declared_scoped_sequence_completed' not in result,
         'ORIGINAL_FAILED_UNKNOWN_WITH_NO_COMPLETED_BUSINESS_POSTCONDITION')
    need(core.timestamp(prior_ended) < core.timestamp(intent['started_utc']),
         'PRIOR_HELPER_IDENTITY_REFERENCE_IS_EARLIER_NOT_A_LATER_OBSERVER')
    build = core.fixed_build(intent['request']['build']); binding_identity(binding, core, qa)
    core.installed_identity(installed, build)
    seq = OriginalSequence(files, core=core, qa=qa, transport=transport, tasks=tasks, binding=binding,
        launch=launch, build=build, installed=installed, parent_pid=2441902,
        started_utc=intent['started_utc'], ended_utc=result['ended_utc'])
    for name in ('intent.json', 'result.json', 'held-main-binding.json'):
        seq.raw(name)
    rejected = seq.sequence(case['steps'][0]['plan'], rejected=True)
    need(rejected['inspect']['wire_sha256'] == INSPECTION_WIRE_SHA and
         rejected['middle']['diagnostic']['wire_sha256'] == FAILED_WIRE_SHA,
         'EXACT_ORIGINAL_INSPECT_AND_REJECTING_ACTION_WIRES')
    for nonce in case['steps'][0]['post_inspection']['nonces'].values():
        need(not any(nonce + suffix in files for suffix in ('.request.json', '.assessment.json', '.failed-assessment.json')),
             'UNREQUESTED_POSTCONDITION_NONCES_MUST_REMAIN_ABSENT')
    need('case-00-operation.json' not in files and 'case-00-postcondition.json' not in files,
         'NO_MANUFACTURED_SUCCESSFUL_SEQUENCE_OR_POSTCONDITION')
    seq.complete(10, 13)
    return {'intent': intent, 'result': result, 'binding': binding, 'build': build, 'installed': installed,
            'launch': launch, 'case': case, 'rejected': rejected,
            'command_proofs': seq.command_proofs, 'phase_proofs': seq.phase_proofs,
            'all_files_sha256': {name: sha(body) for name, body in sorted(files.items())}}


def no_action_public_proof(failed, prior, *, reader, source_pin, core):
    rejection = failed['rejected']['failed_helper_retirement']
    need(rejection['helper_action_attempted'] is False and rejection['helper_outcome_unknown'] is False and
         rejection['original_success_parser_rejection_preserved'] is True,
         'ONLY_COMPLETE_PRE_DISPATCH_REJECTION_MAY_PRODUCE_NEW_PROOF')
    return {'schema': 'pocket4-owned-qa-rejected-before-dispatch-history-v1',
        'producer_source': source_pin, 'flow': FLOW, 'task': TASK, 'original_case': CASE_STEP,
        'original_controller_job': FAILED_JOB, 'original_stdout_sha256': reader.CONFIG['actual_stdout_sha256'],
        'original_terminal_sha256': reader.CONFIG['terminal_sha256'], 'private_original_bundle': BUNDLE,
        'case_sha256': CASE_SHA, 'scope_sha256': SCOPE_SHA, 'launch_scope_sha256': LAUNCH_SHA,
        'original_case_ok': False, 'original_case_outcome_unknown': True,
        'original_action_outcome': 'unknown_retained', 'original_results_rewritten': False,
        'helper_requested_click_dispatch_attempted': False, 'helper_claim_persistence_completed': True,
        'claim_deleted_or_reused': False, 'helper_rejection_and_state_retirement': rejection,
        'successful_inspection_state_check': failed['rejected']['successful_inspection_state_check'],
        'original_command_count': 10, 'original_transport_count': 13,
        'original_step_file_count': 90, 'archive_original_file_count': 101,
        'case_file_hashes': failed['all_files_sha256'], 'command_proofs': failed['command_proofs'],
        'phase_proofs': failed['phase_proofs'], 'prior_installed_helper_reference': prior,
        'independent_later_observer_available': False, 'business_postcondition_observed': False,
        'all_declared_postcondition_nonces_unrequested': True, 'app_autonomous_changes_excluded': False,
        'whole_instrumentation_effects_claimed_absent': False,
        'old_action_replayed': False, 'current_action_authority': False,
        'business_success_verified': False, 'production_ready': False, 'automatic_retry': False,
        'private_UI_raw_or_nodes_included': False, 'reconciliation_published': False,
        'original_Flow_reconcile_called': False, 'typed_reason': 'exact_helper_refusal_before_performAction'}
