"""Pure verifier for the one actual task-878 partially failed case.

This is a new evidence protocol, not Flow.reconcile or a successful case
adapter. It opens no files, executes no Android command and publishes no
admission. A return value is only historical evidence and requires separate
fresh authority, owned-process retirement and an explicitly reviewed commit.
"""
import datetime
import hashlib
import json
import re

FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
CASE_STEP = 'close-and-observe-search-01'
OBSERVATION_STEP = 'inspect-after-search-rejection-01'
CASE_SHA = '2049bd107278f39cab66fccf14a6d9dda5c66db40723761d8eb64b436ee4ae95'
SCOPE_SHA = '08c014646be1d32ef9eacc119f7930b941fc696333bd4cff9d74106f19dba516'
LAUNCH_SHA = '54a669eb54fa0dcf6df5afcd17848af7511c2122623192051eb6370e42bfbb06'
NATIVE_RECEIPT_SHA = 'e1b09112b1be1ec8095cd5b7049131e0e8bd13ad8b4e38803e3c19d02e5e65a3'
FAILED_WIRE_SHA = '91f6bec8b7ec016399b99f7135701234deeb894c86530208de942b390cfcb8ae'
OBSERVATION_WIRE_SHA = '36174e091c45db20baf2c192ecc677abc52b6565d7c68b25ff50b5b8ec0f0aaa'
OBSERVATION_PLAN_SHA = '022d15ae8c0b31f1c9469a1a2a0f4a093d166d01d5ca25d496b159ab2879bcb4'
OBSERVATION_RESULT_SHA = '8abc17cc8fb4983792f1ec09270abd8eaeb29d56f80ea3a1fe2c76dcba523b4d'
HELD_HELPER = '/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry'
TASK = 878
HELPER_UID = 10157
POSTCONDITION = {'resource_id': 'com.lianjia.beike:id/tv_nav_right_search_text',
                 'class': 'android.widget.TextView', 'text': '\u641c\u7d22',
                 'enabled': True, 'clickable': True}
OBSERVATION_NONCES = {'before': '64ea5161c126a5fd345e8bc781c43813',
                     'inspect': 'd4be175e3d9f09f49cac2f7ac9dd7fc2',
                     'after': '5bd51ed29028f6923ffcf59643eafeaa'}
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
         value['self_uid'] == HELPER_UID and value['self_pid'] == 60531,
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
         finish - start <= 12000 and start == 1020981386 and finish == 1020981900,
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


def verify_failed_case(files, scope, launch, case, expected_result, *, core, qa, adapter,
                       transport, tasks, runner):
    core.fixed_scope(scope); fixed_launch(launch, core)
    runner.validate_case(case, adapter, qa)
    need(case['name'] == 'beike-close-and-observe-search-01' and len(case['steps']) == 2 and
         all(row['plan']['operation'] == 'click' and row['post_inspection']['operation'] == 'inspect'
             for row in case['steps']) and case['steps'][0]['postcondition'] == POSTCONDITION,
         'ONLY_THE_PINNED_PARTIAL_CASE_AND_REAL_FIRST_POSTCONDITION')
    intent, result, binding = (document(files[name]) for name in ('intent.json', 'result.json', 'held-main-binding.json'))
    need(intent.get('operation') == 'owned-qa-case' and intent.get('mutation') is True and
         intent.get('scope') == scope and intent.get('automatic_retry') is False and
         all(intent.get(key) is None for key in ('unknown_step', 'observation_step', 'postcondition')) and
         set(intent['request']) == {'case', 'case_sha256', 'build'} and intent['request']['case'] == case and
         intent['request']['case_sha256'] == CASE_SHA, 'ORIGINAL_PARTIAL_CASE_INTENT')
    need(result == expected_result and result['ok'] is False and result['outcome_unknown'] is True and
         result['action_attempted'] is True and result['original_action_outcomes_rewritten'] is False and
         result['production_ready'] is False and result['business_success_verified'] is False and
         result['errors'] == [{'code': 'EXACT_SUCCESSFUL_FINISH_REQUIRED', 'type': 'ProtocolError'}] and
         len(result['steps']) == 1 and 'declared_scoped_sequence_completed' not in result,
         'ORIGINAL_CASE_FAILED_UNKNOWN_AND_INCOMPLETE_RETAINED')
    build = core.fixed_build(intent['request']['build']); binding_identity(binding, core, qa)
    operation = document(files['case-00-operation.json'])
    installed = core.installed_identity(operation['installed_before'], build)
    seq = OriginalSequence(files, core=core, qa=qa, transport=transport, tasks=tasks, binding=binding,
        launch=launch, build=build, installed=installed, parent_pid=1596573,
        started_utc=intent['started_utc'], ended_utc=result['ended_utc'])
    for name in ('intent.json', 'result.json', 'held-main-binding.json', 'case-00-operation.json'):
        seq.raw(name)
    first = seq.sequence(case['steps'][0]['plan'], saved=operation)
    post = seq.sequence(case['steps'][0]['post_inspection'])
    receipt = seq.read('case-00-postcondition.json')
    matched = core.match_postcondition(qa, post['inspect']['helper']['inspection'], POSTCONDITION)
    need(receipt == result['steps'][0] and receipt == {'index': 0,
         'post_nonce': case['steps'][0]['post_inspection']['nonces']['inspect'],
         'post_wire_sha256': post['inspect']['wire_sha256'],
         'matched': {key: matched[key] for key in ('node_path', 'node_sha256', 'tree_sha256', 'window_sha256')},
         'postcondition': POSTCONDITION, 'original_action_outcome': 'unknown_retained',
         'allows_next_declared_case_decision_only': True, 'business_success_verified': False},
         'ACTUAL_PREFIX_INDEPENDENT_POSTCONDITION_REPARSED')
    rejected = seq.sequence(case['steps'][1]['plan'], rejected=True)
    for nonce in case['steps'][1]['post_inspection']['nonces'].values():
        need(not any(nonce + suffix in files for suffix in ('.request.json', '.assessment.json', '.failed-assessment.json')),
             'MISSING_FINAL_POSTCONDITION_NONCES_MUST_REMAIN_ABSENT')
    need('case-01-operation.json' not in files and 'case-01-postcondition.json' not in files,
         'NO_MANUFACTURED_FAILED_SEQUENCE_OR_FINAL_POSTCONDITION')
    seq.complete(29, 38)
    return {'intent': intent, 'result': result, 'binding': binding, 'build': build, 'installed': installed,
            'launch': launch, 'case': case, 'first': first, 'post': post, 'rejected': rejected,
            'command_proofs': seq.command_proofs, 'phase_proofs': seq.phase_proofs,
            'all_files_sha256': {name: sha(raw) for name, raw in sorted(files.items())},
            'prefix_postcondition_match': matched}


def verify_later_inspection(files, scope, launch, plan, expected_result, failed, *, core,
                            qa, adapter, transport, tasks):
    core.fixed_scope(scope); fixed_launch(launch, core); adapter.validate_plan(plan, qa)
    need(plan == {'schema': 1, 'operation': 'inspect', 'nonces': OBSERVATION_NONCES},
         'ONLY_ACTUAL_LATER_INDEPENDENT_INSPECTION_PLAN')
    intent, result, binding = (document(files[name]) for name in ('intent.json', 'result.json', 'held-main-binding.json'))
    need(sha(files['result.json']) == OBSERVATION_RESULT_SHA and result == expected_result and
         intent.get('operation') == 'owned-qa' and intent.get('mutation') is False and
         intent.get('scope') == scope and intent.get('automatic_retry') is False and
         all(intent.get(key) is None for key in ('unknown_step', 'observation_step', 'postcondition')) and
         intent.get('request') == {'plan': plan, 'plan_sha256': OBSERVATION_PLAN_SHA, 'owned_build': failed['build']},
         'ACTUAL_ORIGINAL_LATER_READONLY_STEP_AND_PLAN')
    need(result.get('ok') is True and result.get('error') is None and result.get('secondary_errors') == [] and
         result.get('epoch_sha256') == qa.MAIN_EPOCH and result.get('build') == failed['build'] and
         result.get('source_manifest_sha256') == core.HELPER_MANIFEST and
         result.get('plan_sha256') == OBSERVATION_PLAN_SHA and
         all(result.get(key) is False for key in ('action_attempted', 'outcome_unknown', 'automatic_retry',
             'next_business_mutation_requires_explicit_postcondition_reconciliation',
             'business_success_verified', 'whole_app_production_ready', 'old_v2_helper_called')),
         'LATER_OBSERVER_MUST_BE_REAL_COMPLETE_READONLY_SUCCESS')
    binding_identity(binding, core, qa)
    comparison = core.compare_held_bindings(failed['binding'], binding)
    installed = core.installed_identity(result['installed_before'], failed['build'])
    need(installed == failed['installed'], 'EXACT_SAME_HELPER_FULL_APK_IDENTITY_ACROSS_OBSERVATIONS')
    seq = OriginalSequence(files, core=core, qa=qa, transport=transport, tasks=tasks, binding=binding,
        launch=launch, build=failed['build'], installed=installed, parent_pid=2010422,
        started_utc=intent['started_utc'], ended_utc=result['ended_utc'])
    for name in ('intent.json', 'result.json', 'held-main-binding.json'):
        seq.raw(name)
    observation = seq.sequence(plan, saved=result); seq.complete(9, 12)
    need(observation['inspect']['wire_sha256'] == OBSERVATION_WIRE_SHA,
         'ACTUAL_LATER_OBSERVATION_WIRE')
    case_nonces = {nonce for row in failed['case']['steps'] for key in ('plan', 'post_inspection')
                   for nonce in row[key]['nonces'].values()}
    need(case_nonces.isdisjoint(plan['nonces'].values()), 'INDEPENDENT_NEW_OBSERVER_NONCES')
    now = datetime.datetime.now(datetime.timezone.utc)
    times = [core.timestamp(failed['intent']['started_utc']), core.timestamp(failed['result']['ended_utc']),
             core.timestamp(intent['started_utc']), core.timestamp(result['ended_utc']), now]
    need(times == sorted(times) and failed['rejected']['after']['helper']['finished_elapsed_ms'] <=
         observation['before']['helper']['started_elapsed_ms'], 'CASE_THEN_LATER_OBSERVER_UTC_AND_ANDROID_TIME')
    matched = core.match_postcondition(qa, observation['inspect']['helper']['inspection'], POSTCONDITION)
    need(matched['node_sha256'] == '794068244e4f4112309b9f08ee56a9f09225dc20cad32676728de484668f7d97' and
         matched['tree_sha256'] == '8b8a82ab3f725e2a9d154d5f7a218edcdf09b717b98e41b31cb8135394bbb4b7' and
         matched['window_sha256'] == '2d0973a3ca42535a7989c767926587e0be387a79a6b13477ad875d4d48e0d773',
         'ONLY_THE_LATER_ACTUALLY_OBSERVED_HOME_SEARCH_POSTCONDITION')
    return {'intent': intent, 'result': result, 'binding': binding, 'installed': installed,
            'observation': observation, 'command_proofs': seq.command_proofs, 'phase_proofs': seq.phase_proofs,
            'all_files_sha256': {name: sha(raw) for name, raw in sorted(files.items())},
            'binding_comparison': comparison, 'matched': matched}


def public_historical_proof(failed, observed, *, core):
    """No raw nodes, window text, accessibility settings or UI output here."""
    return {'schema': 'pocket4-owned-qa-partial-case-historical-proof-v1',
        'producer_operation': 'owned-qa-partial-case-reconciliation',
        'flow': FLOW, 'unknown_step': CASE_STEP, 'observation_step': OBSERVATION_STEP, 'task': TASK,
        'framework_epoch_sha256': core.MAIN_EPOCH, 'runtime_epoch_sha256': core.RUNTIME_EPOCH,
        'app_scope_sha256': core.APP_SCOPE, 'scope_sha256': SCOPE_SHA, 'case_sha256': CASE_SHA,
        'case_ok': False, 'case_outcome_unknown': True, 'original_action_outcome': 'unknown_retained',
        'original_results_rewritten': False, 'old_action_replayed': False,
        'successful_prefix_steps': [0], 'rejected_no_dispatch_suffix_step': 1,
        'first_postcondition': failed['prefix_postcondition_match'],
        'failed_helper_retirement': failed['rejected']['failed_helper_retirement'],
        'final_original_postcondition_was_executed': False,
        'later_observation_nonce': OBSERVATION_NONCES['inspect'],
        'later_observation_wire_sha256': OBSERVATION_WIRE_SHA,
        'later_postcondition': POSTCONDITION, 'later_match': observed['matched'],
        'binding_comparison': observed['binding_comparison'],
        'case_command_count': 29, 'case_transport_count': 38,
        'observation_command_count': 9, 'observation_transport_count': 12,
        'case_phase_proofs': failed['phase_proofs'], 'observation_phase_proofs': observed['phase_proofs'],
        'case_file_hashes': failed['all_files_sha256'], 'observation_file_hashes': observed['all_files_sha256'],
        'failed_sequence_summary_object_manufactured': False,
        'private_foreground_raw_persisted': False, 'private_UI_raw_or_nodes_included': False,
        'current_foreground_verified': False, 'current_runtime_or_helper_verified': False,
        'requires_fresh_R5_task_helper_original_foreground': True,
        'requires_normal_owned_candidate_exit_and_durable_terminal_before_commit': True,
        'reconciliation_published': False, 'Flow_admission_published': False,
        'current_action_authority': False, 'business_success_verified': False,
        'search_page_or_search_results_verified': False, 'production_ready': False,
        'automatic_retry': False}
