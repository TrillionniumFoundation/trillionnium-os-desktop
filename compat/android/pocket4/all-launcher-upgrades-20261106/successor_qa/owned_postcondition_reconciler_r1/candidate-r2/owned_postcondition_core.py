"""Offline evidence checks for one completed Beike owned-qa action and inspect.

This module neither opens files nor executes commands. It cannot publish a Flow
reconciliation. Callers must supply the exact, externally pinned frozen modules
and complete byte bundles, then independently revalidate live held authority.
No value returned here is Android or production admission.
"""
import copy
import datetime
import hashlib
import json
import math
import re
import stat

PACKAGE = 'com.lianjia.beike'
UID = 10143
HELPER = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1'
HELPER_UID = 10157
TASK = 876
FLOW = '/home/alex/work/pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb'
MAIN_EPOCH = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
RUNTIME_EPOCH = 'a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9'
APP_SCOPE = '2f3ed55a035e64401189cd2afbaded2414c7b0b9a3c641a82308a1c68b96a8eb'
RECORDER_MANIFEST = '646f6e4c7d931bf005ada01a84202a891c95e99e93bbde7a561f3307527008a4'
HELPER_MANIFEST = 'dfb9b6a483f1069847433152b9b2e8b0f1b2cdd571a1dbde3068fc9393ad62c4'
BUILD_RECEIPT = 'c0dd8117cdb7fa8b551e2a59b466c91d48ee2f2d9a98908f69b3d3fb8807bf3d'
APK_SHA = '006b3bdd64fcd8a03a4ceac0d036b3b99906140feadee61d198756cb6c55c8d9'
SIGNER_SHA = 'd48d103342b42791ae4e927d70258062d0de11f9acb9f32b4426aff583f27d6f'
EMPTY_SHA = hashlib.sha256(b'').hexdigest()
STEP_RE = r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}'
MAX_STEP_FILES = 128
MAX_STEP_BYTES = 16 * 1024 * 1024


class Rejected(RuntimeError):
    pass


def need(value, code):
    if not value:
        raise Rejected(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def document(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 2 * 1024 * 1024, 'JSON_BYTE_BOUND')
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def constant(_):
        raise Rejected('NONFINITE_JSON_VALUE')
    value = json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=pairs,
                       parse_constant=constant)
    need(type(value) is dict, 'JSON_OBJECT_REQUIRED')
    return value


# Only these records come from namespace FDs in the pinned R5 producer.
# R5 checks NS_GET_NSTYPE, proc namespace inode links and held process identity.
# fd_record also retains nsfs mtime as an observation, not namespace identity.
HELD_R5_SHA = '72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4'
NAMESPACE_NAMES = ('mnt', 'pid', 'uts', 'ipc', 'net', 'cgroup')
NAMESPACE_FD_KEYS = {'device', 'inode', 'mode', 'uid', 'gid', 'bytes', 'mtime_ns', 'nlink'}


def held_binding_identity(binding):
    """Copy one binding; project mtime only at eight proven namespace-FD sites.

    Original dictionaries and bytes are never changed. All namespace identity
    and metadata other than mtime, and every other binding field, stay exact.
    Type admission was performed by the frozen R5 NS_GET_NSTYPE checks; this
    function verifies their recorded inode links and closed fd_record shape.
    It does not itself acquire or qualify any live namespace.
    """
    need(type(binding) is dict and
         binding.get('schema') == 'pocket4-successor-held-binding-r5-v1' and
         binding.get('held_runtime_r5_sha256') == HELD_R5_SHA,
         'PINNED_R5_NAMESPACE_RECORD_PROVENANCE')
    target, classpath = binding.get('target'), binding.get('classpath')
    need(type(target) is dict and type(classpath) is dict and
         type(target.get('namespaces')) is dict and
         set(target['namespaces']) == set(NAMESPACE_NAMES) and
         type(target.get('init')) is dict and type(target['init'].get('ns')) is dict and
         set(target['init']['ns']) == set(NAMESPACE_NAMES) and
         type(classpath.get('zygote')) is dict and
         type(classpath['zygote'].get('namespaces')) is dict and
         classpath.get('schema') == 2 and classpath.get('main_classpath_read') is True,
         'CLOSED_R5_NAMESPACE_RECORD_LOCATIONS')
    need(classpath['zygote']['namespaces'].get('pid') == target['init']['ns']['pid'],
         'R5_ZYGOTE_INIT_PID_NAMESPACE_IDENTITY')
    projected = copy.deepcopy(binding)
    observations = {}

    def namespace_row(row, name, link, path):
        need(type(row) is dict and set(row) == NAMESPACE_FD_KEYS and
             all(type(value) is int and value >= 0 for value in row.values()) and
             row['inode'] > 0 and row['nlink'] > 0 and stat.S_ISREG(row['mode']),
             'CLOSED_NAMESPACE_FD_METADATA:' + path)
        match = re.fullmatch(re.escape(name) + r':\[(\d+)\]', link) if type(link) is str else None
        need(match is not None and row['inode'] == int(match[1]),
             'NAMESPACE_FD_MATCHES_RECORDED_PROCESS_LINK:' + path)
        observations[path + '/mtime_ns'] = row.pop('mtime_ns')

    for name in NAMESPACE_NAMES:
        namespace_row(projected['target']['namespaces'][name], name, target['init']['ns'][name],
                      '/target/namespaces/' + name)
    namespace_row(projected['classpath'].get('command_mount_namespace'), 'mnt', target['init']['ns']['mnt'],
                  '/classpath/command_mount_namespace')
    namespace_row(projected['classpath'].get('zygote_mount_namespace'), 'mnt',
                  classpath['zygote']['namespaces'].get('mnt'), '/classpath/zygote_mount_namespace')
    need(projected['classpath']['command_mount_namespace'] == projected['target']['namespaces']['mnt'],
         'R5_COMMAND_MOUNT_RECORD_IS_THE_SAME_HELD_INIT_NAMESPACE')
    return projected, observations


def compare_held_bindings(left, right):
    """Exact cross-observation identity under the frozen namespace contract."""
    left_identity, left_times = held_binding_identity(left)
    right_identity, right_times = held_binding_identity(right)
    need(left_identity == right_identity, 'EXACT_R5_IDENTITY_EXCEPT_NAMESPACE_OBSERVATION_MTIME')
    observations = [{'path': path, 'left_mtime_ns': left_times[path], 'right_mtime_ns': right_times[path]}
                    for path in sorted(left_times)]
    return {'schema': 'pocket4-r5-namespace-identity-comparison-v1',
            'held_runtime_r5_sha256': HELD_R5_SHA,
            'canonical_identity_projection_sha256': sha(json.dumps(left_identity, ensure_ascii=True,
                sort_keys=True, separators=(',', ':'), allow_nan=False).encode()),
            'namespace_mtime_observations': observations,
            'namespace_mtime_differences': [row for row in observations if row['left_mtime_ns'] != row['right_mtime_ns']],
            'all_other_binding_fields_exactly_equal': True,
            'namespace_device_inode_mode_uid_gid_size_nlink_exactly_equal': True,
            'original_binding_objects_rewritten': False,
            'live_namespace_qualification_performed_by_comparison': False}


def timestamp(value):
    need(type(value) is str and len(value) <= 64, 'BOUNDED_UTC_TIMESTAMP')
    value = datetime.datetime.fromisoformat(value)
    need(value.tzinfo is not None and value.utcoffset() == datetime.timedelta(0),
         'EXPLICIT_UTC_TIMESTAMP_REQUIRED')
    return value


def name(value):
    need(type(value) is str and re.fullmatch(STEP_RE, value), 'EXACT_STEP_NAME')
    return value


def condition(value):
    allowed = {'resource_id', 'text', 'content_desc', 'class', 'enabled', 'clickable'}
    need(type(value) is dict and value and set(value) <= allowed and
         any(type(value.get(k)) is str and value[k] for k in ('resource_id', 'text', 'content_desc')),
         'EXPLICIT_NONEMPTY_POSTCONDITION_IDENTITY')
    for key, item in value.items():
        need(type(item) is (bool if key in ('enabled', 'clickable') else str) and
             (type(item) is bool or (0 < len(item.encode('utf-8')) <= 256 and '\0' not in item)),
             'POSTCONDITION_TYPE_OR_BOUND')
    return value


def match_postcondition(qa, inspection, expected):
    condition(expected)
    tree = qa.inspect_record(inspection)
    found = [node for node in tree['nodes'] if
             node.get('package') == PACKAGE and node.get('visible') is True and
             node.get('password') is False and node.get('content_redacted') is not True and
             all(node.get(key) == item for key, item in expected.items()) and
             all(node.get(key + '_truncated') is False for key, item in expected.items()
                 if type(item) is str)]
    need(len(found) == 1, 'ONE_VISIBLE_NONPASSWORD_UNTRUNCATED_POSTCONDITION_NODE')
    return {'node_path': found[0]['path'], 'node_sha256': found[0]['node_sha256'],
            'tree_sha256': tree['tree_sha256'], 'window_sha256': tree['window_sha256'],
            'future_stability_proven': False, 'business_success_verified': False}


def fixed_scope(value):
    need(type(value) is dict and value.get('schema') == 'pocket4-successor-recorder-scope-v1' and
         value.get('package') == PACKAGE and type(value.get('uid')) is int and value['uid'] == UID and
         type(value.get('user')) is int and value['user'] == 0 and
         value.get('epoch_sha256') == MAIN_EPOCH and value.get('runtime_epoch_sha256') == RUNTIME_EPOCH and
         value.get('app_scope_sha256') == APP_SCOPE and
         value.get('adapter_manifest_sha256') == RECORDER_MANIFEST and
         value.get('automatic_retry') is False, 'EXACT_EXISTING_BEIKE_FLOW_SCOPE')
    return value


def fixed_launch(value):
    need(type(value) is dict and value.get('package') == PACKAGE and
         type(value.get('task')) is int and value['task'] == TASK and
         value.get('epoch_sha256') == MAIN_EPOCH and value.get('prelaunch_absent') is True and
         value.get('cleanup_allowed') is True and type(value.get('prelaunch_task_ids')) is list and
         TASK not in value['prelaunch_task_ids'] and
         re.fullmatch('[0-9a-f]{64}', value.get('native_receipt_sha256', '')),
         'EXACT_EXISTING_NATIVE_TASK_SCOPE')
    name(value.get('launch_step'))
    return value


def fixed_build(value):
    need(type(value) is dict and value.get('build_receipt_sha256') == BUILD_RECEIPT and
         value.get('source_manifest_sha256') == HELPER_MANIFEST and
         value.get('signer_certificate_sha256') == SIGNER_SHA and
         value.get('self_instrumentation') is True and value.get('old_v2_provenance_inherited') is False,
         'EXACT_ACTUAL_BUILD_PROOF')
    apk = value.get('APK')
    need(type(apk) is dict and apk.get('sha256') == APK_SHA and
         type(apk.get('bytes')) is int and 0 < apk['bytes'] <= 2097152, 'EXACT_INSTALLED_HELPER_APK')
    return value


def installed_identity(value, build):
    need(type(value) is dict and set(value) == {'package', 'uid', 'base_apk', 'apk_sha256',
         'bytes', 'held_file', 'signer_bound_by_exact_signed_apk_bytes'}, 'CLOSED_INSTALLED_HELPER_IDENTITY')
    path = value['base_apk']
    need(value['package'] == HELPER and type(value['uid']) is int and value['uid'] == HELPER_UID and
         value['apk_sha256'] == APK_SHA and value['bytes'] == build['APK']['bytes'] and
         value['signer_bound_by_exact_signed_apk_bytes'] == SIGNER_SHA and
         type(path) is str and re.fullmatch(r'/data/app/[^/\x00]+/[^/\x00]+/base\.apk', path) and
         len(path) <= 1024 and '..' not in path.split('/'), 'ACTUAL_SIGNED_INSTALLED_HELPER_IDENTITY')
    row = value['held_file']
    need(type(row) is dict and row.get('bytes') == value['bytes'] and
         type(row.get('mode')) is int and stat.S_ISREG(row['mode']) and
         type(row.get('inode')) is int and row['inode'] > 0 and
         type(row.get('device')) is int, 'HELD_HELPER_APK_FILE_METADATA')
    return value


def command_success(ci, cr, raw, stderr, mutation, timeout):
    need(type(ci) is dict and type(cr) is dict and type(raw) is bytes and type(stderr) is bytes,
         'COMPLETE_COMMAND_RECORD_REQUIRED')
    need(ci.get('label') == 'Android command' and ci.get('mutation') is mutation and
         ci.get('automatic_retry') is False and ci.get('timeout_seconds') == timeout,
         'EXACT_ORIGINAL_ANDROID_COMMAND_KIND')
    need(cr.get('returncode') == 0 and type(cr.get('returncode')) is int and
         cr.get('spawned') is True and cr.get('owned_command_joined') is True and
         cr.get('timed_out') is False and cr.get('error') is None and cr.get('errors') == [] and
         cr.get('action_attempted') is mutation and cr.get('automatic_retry') is False and
         cr.get('stdout_sha256') == sha(raw) and cr.get('stderr_sha256') == sha(stderr) and stderr == b'',
         'ACTUAL_COMMAND_SUCCESS_JOIN_AND_COMPLETE_RAW_REQUIRED')
    need(type(cr.get('seconds')) in (int, float) and math.isfinite(cr['seconds']) and
         0 <= cr['seconds'] <= timeout + 5, 'BOUNDED_COMMAND_ELAPSED_TIME')
    need(timestamp(ci['started_utc']) <= timestamp(cr['ended_utc']), 'COMMAND_UTC_ORDER')


def command_argv(ci, expected_args, timeout, held_helper_path, classpaths, transport):
    argv, authorities = ci.get('argv'), ci.get('authority_fds_passed')
    need(type(argv) is list and argv == ci.get('execution_argv') and
         all(type(item) is str and item and '\0' not in item for item in argv) and
         type(authorities) is list and len(authorities) == len(set(authorities)) == 7 and
         all(type(fd) is int and fd >= 3 for fd in authorities), 'REAL_HELD_COMMAND_AUTHORITY_SET')
    need(len(argv) >= 12 and argv[0] == held_helper_path and
         re.fullmatch(r'--parent-pid=[1-9][0-9]*', argv[1]), 'HELD_ENTRY_EXACT_HELPER_AND_PARENT')
    expected_prefix = [argv[0], argv[1], '--root-fd=' + str(authorities[0])]
    expected_prefix += ['--' + key + '-fd=' + str(fd) for key, fd in
                       zip(('mnt', 'pid', 'uts', 'ipc', 'net', 'cgroup'), authorities[1:])]
    need(argv[:10] == expected_prefix + ['--'], 'NO_NUMERIC_NAMESPACE_TARGET_OR_OTHER_PREFIX')
    suffix = argv[10:]
    need(suffix[:2] == ['/system/bin/env', '-i'] and suffix.count('/system/xbin/su') == 1,
         'ORIGINAL_CLEAN_ANDROID_ENVIRONMENT')
    boundary = suffix.index('/system/xbin/su')
    environment = {}
    for item in suffix[2:boundary]:
        key, equal, value = item.partition('=')
        need(equal and key not in environment, 'EXACT_ENVIRONMENT_ASSIGNMENT')
        environment[key] = value
    transport.environment_values(environment)
    need(suffix[2:boundary] == [key + '=' + environment[key] for key in sorted(environment)] and
         all(environment.get(key) == value for key, value in classpaths.items()),
         'EXACT_RECORDED_HELD_CLASSPATH_VALUES')
    need(suffix[boundary:] == ['/system/xbin/su', '2000', '/system/bin/timeout', '-k', '2',
                              str(max(1, timeout - 5)), *expected_args],
         'NO_EXTRA_ANDROID_COMMAND_OR_ARGUMENT')
    return {'parent_pid': int(argv[1].split('=', 1)[1]), 'authority_fds': authorities,
            'environment': environment}


def _phase_request(qa, plan, phase, op, scope=None, extra=None):
    value = {'protocol': qa.PROTOCOL, 'nonce': plan['nonces'][phase], 'op': op}
    if scope is not None:
        value['scope'] = scope
    value.update(extra or {})
    qa.validate_request(value)
    return value


def validate_step(files, *, adapter, qa, transport, scope, launch, build, mutation,
                  held_helper_path, expected_binding):
    """Validate a full original qa_adapter step; reject case or legacy UI shapes."""
    fixed_scope(scope); fixed_launch(launch); fixed_build(build)
    need(type(files) is dict and 1 <= len(files) <= MAX_STEP_FILES and
         all(type(k) is str and '/' not in k and '\\' not in k and
             type(v) is bytes and len(v) <= 2 * 1024 * 1024 for k, v in files.items()) and
         sum(map(len, files.values())) <= MAX_STEP_BYTES, 'COMPLETE_BOUNDED_STEP_BUNDLE')
    used = set()
    def raw(key):
        need(key in files, 'MISSING_ORIGINAL_EVIDENCE:' + key)
        used.add(key)
        return files[key]
    def read(key):
        return document(raw(key))
    intent, result = read('intent.json'), read('result.json')
    need(intent.get('operation') == 'owned-qa' and intent.get('mutation') is mutation and
         intent.get('scope') == scope and intent.get('automatic_retry') is False and
         intent.get('unknown_step') is None and intent.get('observation_step') is None and
         intent.get('postcondition') is None, 'ONLY_FROZEN_OWNED_QA_SINGLE_SEQUENCE')
    need(result.get('ok') is True and result.get('error') is None and result.get('secondary_errors') == [] and
         result.get('automatic_retry') is False and result.get('epoch_sha256') == MAIN_EPOCH and
         result.get('action_attempted') is mutation and result.get('outcome_unknown') is mutation and
         result.get('next_business_mutation_requires_explicit_postcondition_reconciliation') is mutation and
         result.get('business_success_verified') is False and result.get('whole_app_production_ready') is False and
         result.get('old_v2_helper_called') is False, 'COMPLETED_SUCCESSFUL_UNKNOWN_ACTION_OR_READONLY_SEQUENCE')
    request = intent.get('request')
    need(type(request) is dict and set(request) == {'plan', 'plan_sha256', 'owned_build'}, 'EXACT_ORIGINAL_PLAN_REQUEST')
    plan = adapter.validate_plan(request['plan'], qa)
    need(plan['operation'] in (('click', 'set_text') if mutation else ('inspect',)), 'NARROW_BEIKE_OPERATION_ONLY')
    need(re.fullmatch('[0-9a-f]{64}', request['plan_sha256']) and
         result.get('plan_sha256') == request['plan_sha256'] and
         request['owned_build'] == result.get('build') == build and
         result.get('source_manifest_sha256') == HELPER_MANIFEST, 'ORIGINAL_PLAN_AND_BUILD_BINDING')
    need(timestamp(intent['started_utc']) <= timestamp(result['ended_utc']), 'STEP_UTC_ORDER')
    binding = read('held-main-binding.json')
    need(binding.get('schema') == 'pocket4-successor-held-binding-r5-v1' and
         binding.get('framework_epoch_sha256') == MAIN_EPOCH and
         binding.get('runtime_epoch_sha256') == RUNTIME_EPOCH and binding.get('app_scope_sha256') == APP_SCOPE and
         binding.get('package') == PACKAGE and binding.get('uid') == UID and
         binding.get('ui_actions_performed_by_binding') is False and binding.get('production_ready') is False and
         binding['target'].get('pidfd_held') is True and binding['target'].get('numeric_target_used_for_entry') is False,
         'EXACT_HELD_R5_RUNTIME_APP_CLASSPATH_BINDING')
    binding_comparison = compare_held_bindings(binding, expected_binding)
    installed = installed_identity(result.get('installed_before'), build)
    need(installed == result.get('installed_after') and result.get('owned_task') == launch and
         result.get('after_state_attempted') is True and result.get('after_state_completed') is True and
         result.get('post_state_matches_before') is True and result.get('restoration_qualified') is True,
         'INSTALLED_TASK_AND_RESTORATION_SEQUENCE_REQUIRED')
    foreground = qa.scope(result.get('foreground_before'))
    qa.scope(result.get('foreground_after'))
    if not mutation:
        need(result['foreground_after'] == foreground, 'READONLY_INSPECT_FOREGROUND_CHANGED')
    requests = {
        'before': _phase_request(qa, plan, 'before', 'state'),
        'inspect': _phase_request(qa, plan, 'inspect', 'inspect', foreground),
        'after': _phase_request(qa, plan, 'after', 'state')}
    assessments = {}
    sequence = []
    def add(args, timeout, mut=False, phase=None, private=False):
        sequence.append({'args': args, 'timeout': timeout, 'mutation': mut,
                         'phase': phase, 'private': private})
    def packages():
        add(['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--user', '0', HELPER], 8)
        add(['/system/bin/cmd', 'package', 'path', '--user', '0', HELPER], 8)
    def task():
        add(['/system/bin/cmd', 'activity', 'stack', 'list'], 20)
    def front():
        add(['/system/bin/dumpsys', 'window', 'displays'], 15, private=True)
    def instrument(phase):
        add(qa.instrumentation_argv(requests[phase]), 20, phase == 'action', phase)
    packages(); task(); instrument('before'); front(); instrument('inspect'); front()
    # The action request is derived only after the recorded pre-action inspect
    # has been parsed from its original raw instrumentation output below.
    if mutation:
        add(None, 20, True, 'action')
    instrument('after'); front(); task(); packages()
    command_index = 0
    parent_authority = None
    previous_command_end = timestamp(intent['started_utc'])
    previous_helper_end = None
    for index, item in enumerate(sequence, 1):
        phase = item['phase']
        if phase == 'action':
            inspection = assessments['inspect']['helper']['inspection']
            selector = qa.select_unique_editable if plan['operation'] == 'set_text' else qa.select_unique_clickable
            node = selector(inspection, plan['selector'])
            extra = {'inspection_nonce': plan['nonces']['inspect'],
                     'inspection_sha256': assessments['inspect']['wire_sha256'], **node}
            if plan['operation'] == 'set_text':
                extra['value'] = plan['value']
            requests['action'] = _phase_request(qa, plan, 'action', plan['operation'], foreground, extra)
            item['args'] = qa.instrumentation_argv(requests['action'])
        stem = 'transport-%03d.' % index
        ti = read(stem + 'intent.json')
        tc = read(stem + 'command-result.json')
        tv = read(stem + 'verified-result.json')
        identity = {'sequence': index, 'epoch_sha256': MAIN_EPOCH, 'package': PACKAGE, 'uid': UID,
                    'command_sha256': sha(json.dumps(item['args'], ensure_ascii=False, separators=(',', ':')).encode()),
                    'timeout_seconds': item['timeout'], 'inner_timeout_seconds': max(1, item['timeout'] - 5),
                    'automatic_retry': False, 'numeric_pid_target_used': False}
        need(ti == identity and tc == tv and all(tc.get(k) == v for k, v in identity.items()) and
             tc.get('returncode') == 0 and type(tc.get('returncode')) is int and
             tc.get('action_attempted') is True and tc.get('outcome_unknown') is False and
             tc.get('stderr_bytes') == 0 and tc.get('stderr_sha256') == EMPTY_SHA and
             type(tc.get('stdout_bytes')) is int and 0 <= tc['stdout_bytes'] <= 4 * 1024 * 1024 and
             re.fullmatch('[0-9a-f]{64}', tc.get('stdout_sha256', '')) and
             set(tc) == set(identity) | {'returncode', 'stdout_bytes', 'stderr_bytes', 'stdout_sha256',
                                      'stderr_sha256', 'action_attempted', 'outcome_unknown'},
             'COMPLETE_SUCCESSFUL_LEASE_EXIT_AND_POST_GUARD_TRANSPORT')
        if item['private']:
            # The frozen foreground helper intentionally discards raw dumpsys.
            # Its synchronous transport result is hash-bound, not invented as
            # a recorder-owned command or persisted private window dump.
            need(tc['stdout_bytes'] > 0, 'PRIVATE_FOREGROUND_OBSERVATION_EMPTY')
            continue
        command_index += 1
        stem = 'command-%03d' % command_index
        ci, cr = read(stem + '.intent.json'), read(stem + '.result.json')
        out, err = raw(stem + '.stdout'), raw(stem + '.stderr')
        command_success(ci, cr, out, err, item['mutation'], item['timeout'])
        authority = command_argv(ci, item['args'], item['timeout'], held_helper_path,
                                 binding['classpath']['values'], transport)
        if parent_authority is None:
            parent_authority = authority
        need(authority == parent_authority, 'SAME_ORIGINAL_HELD_AUTHORITY_FOR_WHOLE_SEQUENCE')
        need(previous_command_end <= timestamp(ci['started_utc']) <= timestamp(cr['ended_utc']) <=
             timestamp(result['ended_utc']), 'ORIGINAL_COMMAND_ORDER_OR_END_CHANGED')
        previous_command_end = timestamp(cr['ended_utc'])
        need(tc['stdout_bytes'] == len(out) and tc['stdout_sha256'] == sha(out),
             'RAW_COMMAND_NOT_SAME_TRANSPORT_OBSERVATION')
        if phase is not None:
            expected_request = requests[phase]
            nonce = expected_request['nonce']
            need(read(nonce + '.request.json') == expected_request, 'ORIGINAL_NONCE_REQUEST_CHANGED')
            assessed = qa.parse_completed(out, err, cr['returncode'], expected_request, HELPER_UID)
            assessed['recorder_command_result_sha256'] = sha(files[stem + '.result.json'])
            assessed['held_transport_returned_after_post_guard'] = True
            need(read(nonce + '.assessment.json') == assessed, 'ASSESSMENT_MUST_RECOMPUTE_FROM_RAW')
            helper = assessed['helper']
            need(previous_helper_end is None or previous_helper_end <= helper['started_elapsed_ms'],
                 'HELPER_ELAPSED_SEQUENCE_ORDER')
            previous_helper_end = helper['finished_elapsed_ms']
            assessments[phase] = assessed
    before, after = assessments['before'], assessments['after']
    inspected = assessments['inspect']
    middle = assessments['action'] if mutation else inspected
    restore = qa.assess_restoration(before, middle, after)
    need(result.get('accessibility_restoration') == restore and
         result.get('inspection_wire_sha256') == inspected['wire_sha256'] and
         result.get('post_termination_state') == {'nonce': plan['nonces']['after'],
             'wire_sha256': after['wire_sha256'], 'state': after['helper']['state'],
             'helper_uid': HELPER_UID, 'ui_automation_connected': False}, 'ACTUAL_INDEPENDENT_STATE_RESTORATION')
    if mutation:
        need(result.get('set_text_acknowledged' if plan['operation'] == 'set_text' else 'click_acknowledged') is True and
             middle['helper']['action_window'] == inspected['helper']['inspection']['window'],
             'ORIGINAL_ACTION_ACK_AND_OBSERVED_WINDOW')
    need(used == set(files), 'UNEXPECTED_OR_UNVALIDATED_STEP_FILE')
    return {'intent': intent, 'result': result, 'plan': plan, 'assessments': assessments,
            'files_sha256': {key: sha(value) for key, value in sorted(files.items())},
            'command_count': command_index, 'transport_count': len(sequence),
            'private_foreground_raw_persisted': False,
            'binding': binding, 'binding_comparison': binding_comparison,
            'installed': installed, 'owned_task': launch}


def validate_pair(action, observed, postcondition, *, qa, now):
    condition(postcondition)
    need(action['intent']['mutation'] is True and observed['intent']['mutation'] is False,
         'ACTION_AND_SEPARATE_READONLY_INSPECTION_REQUIRED')
    times = [timestamp(action['intent']['started_utc']), timestamp(action['result']['ended_utc']),
             timestamp(observed['intent']['started_utc']), timestamp(observed['result']['ended_utc']), now]
    need(now.tzinfo is not None and times == sorted(times), 'STRICT_ACTION_THEN_LATER_READONLY_SEQUENCE')
    need(set(action['plan']['nonces'].values()).isdisjoint(observed['plan']['nonces'].values()),
         'INDEPENDENT_INSPECT_MUST_USE_NEW_NONCES')
    need(action['assessments']['after']['helper']['finished_elapsed_ms'] <=
         observed['assessments']['before']['helper']['started_elapsed_ms'], 'ANDROID_MONOTONIC_OBSERVATION_ORDER')
    need(action['installed'] == observed['installed'] and action['owned_task'] == observed['owned_task'],
         'NO_HELPER_OR_TASK_CHANGE_BETWEEN_STEPS')
    binding_comparison = compare_held_bindings(action['binding'], observed['binding'])
    binding_comparison['raw_held_binding_file_sha256'] = {
        'left': action['files_sha256']['held-main-binding.json'],
        'right': observed['files_sha256']['held-main-binding.json']}
    matched = match_postcondition(qa, observed['assessments']['inspect']['helper']['inspection'], postcondition)
    return {'schema': 'pocket4-beike-owned-qa-postcondition-offline-proof-v1',
            'original_action_outcome': 'unknown_retained', 'original_action_result_rewritten': False,
            'matched': matched, 'postcondition': postcondition,
            'later_inspection_nonce': observed['plan']['nonces']['inspect'],
            'later_inspection_wire_sha256': observed['assessments']['inspect']['wire_sha256'],
            'held_binding_comparison': binding_comparison,
            'raw_protocol_recomputed': True, 'complete_sequences_verified': True,
            'requires_fresh_held_runtime_task_and_helper_check': True,
            'Flow_admission_published': False, 'business_success_verified': False,
            'production_ready': False, 'automatic_retry': False}
