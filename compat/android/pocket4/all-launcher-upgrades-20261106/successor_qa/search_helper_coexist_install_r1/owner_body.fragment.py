def entry(mode):
    global SELF, REQUEST
    need(os.getuid() == os.geteuid() == 0 and len(sys.argv) == 10 and sys.argv[1] == mode and
         sys.argv[2] == '--source-sha256' and re.fullmatch('[0-9a-f]{64}', sys.argv[3]) and
         sys.argv[4] == '--source-bytes' and sys.argv[5].isdigit() and 0 < int(sys.argv[5]) <= 131072 and
         sys.argv[6] == '--request-sha256' and re.fullmatch('[0-9a-f]{64}', sys.argv[7]) and
         sys.argv[8] == '--request-bytes' and sys.argv[9].isdigit() and 0 < int(sys.argv[9]) <= 16384,
         'EXACT_ROOT_FIXED_COEXISTENCE_INSTALL_ENTRY')
    need(str(Path(__file__).resolve()) == ROOT + '/owned_install_once.py', 'REAL_NEW_FIXED_OWNER_LOCATION')
    SELF = {'path': str(Path(__file__).resolve()), 'bytes': int(sys.argv[5]), 'sha256': sys.argv[3]}
    REQUEST = {'path': ROOT + '/request.json', 'bytes': int(sys.argv[9]), 'sha256': sys.argv[7]}
    os.umask(0o077)
    base = load_base(); base.pinned(SELF)
    return base


def request_value(raw, core):
    value = core.document(raw)
    need(value == FIXED_REQUEST and raw == canonical(value) + b'\n',
         'EXACT_SINGLE_NORMAL_INSTALL_REQUEST_NO_UID_OR_COMMAND_OVERRIDE')
    return value


def completed_b_header(base, partial, stdout, terminal):
    partial.original_terminal(terminal, STAGE_B_JOB, len(stdout))
    lines = stdout.splitlines()
    need(len(lines) == 2 and partial.document(lines[0]) == ACTUAL_STAGE_B_PUBLICATION,
         'ACTUAL_B_SOURCE_STAGE_AND_SINGLE_PARENT_RECORD')
    outer = partial.document(lines[1])
    need(outer.get('schema') == 'pocket4-owned-qa-no-action-commit-owned-result-v1' and
         outer.get('ok') is True and outer.get('errors') == [] and
         outer.get('source') == STAGE_B_SOURCE and outer.get('request') == STAGE_B_REQUEST and
         outer.get('flow') == FLOW and outer.get('task') == 878 and outer.get('step') == 'no-action-commit-01' and
         outer.get('operation') == 'owned-qa-no-action-commit' and
         outer.get('committed') == B_ENVELOPE and outer.get('typed_proof') == B_PROOF and
         outer.get('step_result') == B_STEP_RESULT and outer.get('joint_artifact') == B_JOINT and
         outer.get('envelope_evidence_count') == 211 and outer.get('original_case_ok') is False and
         outer.get('original_case_outcome_unknown') is True and outer.get('original_action_outcome') == 'unknown_retained' and
         all(outer.get(key) is True for key in ('reconciliation_published', 'compatibility_envelope_written',
             'all_owned_child_resources_retired_by_normal_pidfd_exit', 'parent_whole_process_FD_identity_restored',
             'acceptance_requires_original_stdout_and_authoritative_durable_terminal',
             'next_decision_requires_fresh_original_helper_inspection')) and
         all(outer.get(key) is False for key in ('publication_outcome_unknown', 'original_results_rewritten',
             'old_action_replayed', 'current_action_authority', 'production_ready', 'automatic_retry',
             'frozen_consumer_checks_controller_terminal')) and
         all(type(outer.get(key)) is int and outer[key] == 0 for key in ('UI_actions', 'installs',
             'instrumentation_calls', 'permission_changes', 'lifecycle_or_activation_actions')),
         'ACTUAL_COMPLETED_B_OUTER_JOINT_NOT_ONLY_COMPATIBILITY_RECORD')
    need(type(outer.get('child_stdout_original')) is str and type(outer.get('child_stderr_original')) is str,
         'EXACT_ORIGINAL_B_CHILD_STREAMS_REQUIRED')
    raw = outer['child_stdout_original'].encode('utf-8')
    stderr = outer['child_stderr_original'].encode('utf-8')
    need(outer.get('child_stdout_bytes') == len(raw) and outer.get('child_stdout_sha256') == sha(raw) and
         outer.get('child_stderr_bytes') == len(stderr) == 0 and outer.get('child_stderr_sha256') == sha(stderr),
         'B_CHILD_ORIGINAL_STREAM_BYTES_AND_HASH')
    base.require_owned_exit(outer['child_lifecycle'], stderr)
    return outer, raw


def completed_b_gate(base):
    """Read only completed B evidence; never call any of its execution entries."""
    b = base.load(STAGE_B_SOURCE, 'completed_no_action_B_definitions_only')
    # These two exact externally bound identities configure read-only definitions.
    # They are not inferred from the stdout and do not authorize publication.
    b.SELF, b.REQUEST = dict(STAGE_B_SOURCE), dict(STAGE_B_REQUEST)
    partial = base.load(b.PARTIAL_SOURCE, 'completed_no_action_document_parser_only')
    b.request_value(base.pinned(STAGE_B_REQUEST), partial)
    stdout = base.pinned(STAGE_B_STDOUT)
    terminal = partial.document(base.pinned(STAGE_B_TERMINAL))
    outer, raw = completed_b_header(base, partial, stdout, terminal)
    original_joint = dict(outer); original_joint.pop('joint_artifact')
    need(base.pinned(B_JOINT) == canonical(original_joint) + b'\n', 'EXACT_COMPLETED_B_DURABLE_JOINT_BYTES')
    SELF, REQUEST = STAGE_B_SOURCE, STAGE_B_REQUEST
    CHILD_SCHEMA, PROOF_SCHEMA, OPERATION = b.CHILD_SCHEMA, b.PROOF_SCHEMA, b.OPERATION
    STEP, CASE_STEP, TASK = b.STEP, b.CASE_STEP, b.TASK
    STAGE_A_JOB, STAGE_A_CANDIDATE = b.STAGE_A_JOB, b.STAGE_A_CANDIDATE
    committed_envelope = b.committed_envelope
    # BEGIN unchanged completed-child / typed-proof / envelope predicates.
__ORIGINAL_COMPLETED_B_PREDICATES__
    # END unchanged completed B predicates. No old producer function is invoked.
    need(outer['committed'] == value['committed'] == B_ENVELOPE and
         outer['typed_proof'] == value['typed_proof'] == B_PROOF and
         outer['completed_stage_A'] == value['completed_stage_A'] and
         outer['envelope_evidence_count'] == value['envelope_evidence_count'] == 211 and
         base.pinned(B_STEP_RESULT) == step_result_raw, 'SAME_B_PARENT_CHILD_PROOF_AND_POSTCOMMIT_RESULT')
    # Preserve all inputs actually bound by the B parent. Their private bodies
    # are only hashed in this process and are never returned or copied to stage.
    for pin in (STAGE_B_SOURCE, STAGE_B_REQUEST, b.BASE, b.UI_SOURCE, b.HOST_SOURCE, b.PARTIAL_SOURCE,
                b.HOST_STDOUT, b.HOST_TERMINAL, b.HISTORY_BUNDLE, b.STAGE_A_SOURCE, b.STAGE_A_REQUEST,
                b.STAGE_A_STDOUT, b.STAGE_A_TERMINAL, b.STAGE_A_CANDIDATE, b.STAGE_A_RESULT, b.STAGE_A_JOINT,
                STAGE_B_STDOUT, STAGE_B_TERMINAL):
        base.pinned(pin)
    return {'job_id': STAGE_B_JOB, 'stdout': STAGE_B_STDOUT, 'terminal': STAGE_B_TERMINAL,
            'source': STAGE_B_SOURCE, 'request': STAGE_B_REQUEST, 'joint': B_JOINT,
            'envelope': B_ENVELOPE, 'typed_proof': B_PROOF, 'step_result': B_STEP_RESULT,
            'complete_original_evidence_members': 211, 'original_FAILED_UNKNOWN_retained': True,
            'new_UI_authority': False, 'B_execution_entries_called': False}


def build_identity(metadata):
    need(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and metadata.st_uid == metadata.st_gid == 1000 and
         stat.S_IMODE(metadata.st_mode) == 0o600 and
         f'{metadata.st_dev}:{metadata.st_ino}:{metadata.st_size}:{metadata.st_mtime_ns}:{metadata.st_ctime_ns}' == BUILD_FILE_VERSION,
         'ACTUAL_UID1000_BUILD_RECEIPT_FULL_IDENTITY')
    return {key: getattr(metadata, key) for key in STAT_FIELDS}


def completed_build_gate(base):
    partial = base.load(NO_ACTION_CORE, 'unchanged_authoritative_terminal_predicate')
    raw = base.pinned(BUILD_STDOUT); terminal = partial.document(base.pinned(BUILD_TERMINAL))
    partial.original_terminal(terminal, BUILD_JOB, len(raw))
    value = partial.document(raw)
    need(value == {'state': 'BUILT_STATIC_VERIFIED_ANDROID_UNRUN', 'result': BUILD_RESULT['path'],
                   'result_sha256': BUILD_RESULT['sha256'], 'Android_actions': 0},
         'ACTUAL_NEW_BUILD_COMPLETED_OUTPUT')
    adapter = base.load(ADAPTER, 'unchanged_r2_owned_adapter')
    manifest = adapter.own_source(HELPER_MANIFEST['sha256'])
    builder = adapter.load(Path(ADAPTER['path']).with_name('build_candidate.py'),
                           manifest['files']['build_candidate.py']['sha256'], 'unchanged_r2_build_qualification')
    before = build_identity(os.stat(BUILD_RESULT['path'], follow_symlinks=False))
    need(str(Path(BUILD_RESULT['path']).resolve()) == BUILD_RESULT['path'], 'CANONICAL_ACTUAL_BUILD_RECEIPT')
    args = types.SimpleNamespace(build_receipt=Path(BUILD_RESULT['path']), build_receipt_sha256=BUILD_RESULT['sha256'],
        source_manifest_sha256=HELPER_MANIFEST['sha256'], apk_sha256=APK['sha256'], signer_certificate_sha256=SIGNER_SHA)
    proof = adapter.qualified_build(args, manifest, builder)
    after = build_identity(os.stat(BUILD_RESULT['path'], follow_symlinks=False))
    need(before == after and proof['APK'] == APK and proof['build_receipt_sha256'] == BUILD_RESULT['sha256'] and
         proof['signer_certificate_sha256'] == SIGNER_SHA and proof['source_manifest_sha256'] == HELPER_MANIFEST['sha256'] and
         proof['self_instrumentation'] is True and proof['old_v2_provenance_inherited'] is False,
         'SAME_FULL_ACTUAL_BUILD_AND_NEW_SIGNED_APK')
    return {'job_id': BUILD_JOB, 'stdout': BUILD_STDOUT, 'terminal': BUILD_TERMINAL,
            'result': BUILD_RESULT, 'result_file_version': BUILD_FILE_VERSION,
            'actual_UID1000_file_identity': before, 'qualified_build': proof}


def original_argv(request):
    return [INSTALLER['path'], '--install-once', '--coexistence-source-sha256', INSTALLER['sha256'],
            '--source-manifest-sha256', HELPER_MANIFEST['sha256'], '--build-receipt', BUILD_RESULT['path'],
            '--build-receipt-sha256', BUILD_RESULT['sha256'], '--apk-sha256', APK['sha256'],
            '--signer-certificate-sha256', SIGNER_SHA, '--recorder-root', RECORDER_ROOT,
            '--flow-dir', FLOW, '--step', request['step'], '--state-nonce', request['state_nonce']]


def verify_install(base, core, request, proof, raw):
    original = core.document(raw)
    need(original.get('schema') == 'pocket4-successor-owned-helper-coexist-install-v1' and
         original.get('ok') is True and original.get('errors') == [] and original.get('package') == PACKAGE and
         original.get('build') == proof and original.get('action_attempted') is True and
         original.get('outcome_unknown') is False and original.get('install_attempted') is True and
         original.get('install_success_observed') is True and original.get('state_attempted') is True and
         original.get('helper_retained') is True and original.get('action_lock_held_through_durable_result') is True and
         original.get('scope_requires_outer_owned_child_and_durable_terminal') is True and
         all(original.get(key) is False for key in ('old_v2_helper_called', 'automatic_retry', 'production_ready')) and
         all(type(original.get(key)) is int and original[key] == 0 for key in ('UI_actions', 'permission_grants', 'App_launches')),
         'COMPLETE_NORMAL_INSTALL_STATE_AND_SCOPE_RESULT')
    result_path = FLOW + '/steps/' + request['step'] + '/result.json'
    result_raw, _ = base.read(result_path)
    need(core.document(result_raw) == original, 'SAME_ORIGINAL_DURABLE_INSTALL_RESULT_AND_STDOUT')
    installer = base.load(INSTALLER, 'reviewed_coexistence_pure_scope_validator_only')
    parent = core.document(base.pinned(PARENT_SCOPE))
    transition = original['whole_scope_after']
    next_pin = transition['next_app_scope']
    need(next_pin == original['next_app_scope'] and
         next_pin['path'] == FLOW + '/steps/' + request['step'] + '/app-scope-after.private.json',
         'EXACT_NEW_STEP_SCOPE_OUTPUT_ONLY')
    scope = core.document(base.pinned(next_pin))
    actual = installer.validate_scope_transition(parent, scope, proof, original['helper_uid'], original['installed_after_state'])
    need(transition['transition'] == actual and transition['parent_app_scope'] == PARENT_SCOPE and
         transition['observation']['ok'] is True and
         transition['observation']['app_scope'] == next_pin and
         transition['observation']['observation_fds']['acquired'] == transition['observation']['observation_fds']['closed'] and
         transition['observation']['observation_fds']['remaining'] == 0 and
         transition['observation']['observation_fds']['errors'] == [] and
         original['whole_scope_before'] == transition['original_48_guard_before'] ==
         transition['original_48_guard_after'] == original['whole_scope_final_guard'] and
         original['installed_before_state'] == original['installed_after_state'] and
         original['state']['helper']['ui_automation_connected'] is False and
         original['state']['helper']['action_attempted'] is False and original['state']['helper']['outcome_unknown'] is False,
         'UNCHANGED48_OBSERVED49_AND_NO_UI_AUTOMATION')
    binding = transition['observation']['qa_build_input']
    need(binding['path'] == FLOW + '/steps/' + request['step'] + '/observation-binding.private.json',
         'FIXED_ACTUAL_BINDING_OUTPUT')
    base.pinned(binding)
    return original, {'path': result_path, 'bytes': len(result_raw), 'sha256': sha(result_raw)}


def child():
    base = entry('--child')
    need(sys.stdin.buffer.read(1) == b'R', 'PARENT_HELD_PIDFD_RELEASE_REQUIRED')
    result = {'schema': 'pocket4-owned-search-helper-coexist-child-v1', 'ok': False, 'errors': [],
        'source': SELF, 'request': REQUEST, 'flow': FLOW, 'original_entry_invoked': False,
        'original_sources_modified': False, 'original_FAILED_UNKNOWN_rewritten': False,
        'reconciliation_published': False, 'UI_actions': 0, 'permission_grants': 0,
        'target_App_launches': 0, 'replacement': False, 'old_helper_uninstalled': False,
        'production_ready': False, 'automatic_retry': False}
    try:
        support = base.load(base.SUPPORT, 'unchanged_library_bootstrap')
        probe = support.load_module(support.PROBE_SOURCE, 'unchanged_owned_child_probe')
        observed = support.probe_proof(); _, frozen, library_fd, library = support.initialize_library(probe, observed)
        core = base.load(base.CORE, 'unchanged_pure_document_parser')
        request = request_value(base.pinned(REQUEST), core)
        result['step'] = request['step']
        result['completed_no_action_B'] = completed_b_gate(base)
        qualified = completed_build_gate(base); result['completed_build'] = qualified
        need(not os.path.lexists(Path(FLOW) / 'steps' / request['step']), 'NEW_INSTALL_STEP_NO_REPLAY')
        installer = base.load(INSTALLER, 'reviewed_full48_normal_coexist_installer')
        _, lock_metadata = base.read(Path(FLOW) / 'flow.lock', 65536)
        need(stat.S_IMODE(lock_metadata['st_mode']) == 0o600, 'EXACT_EXISTING_FLOW_LOCK')
        need(probe.same_descriptors(frozen, probe.census()), 'NO_PRE_INSTALL_UNKNOWN_DESCRIPTOR')
        argv = original_argv(request)
        saved, output, returned = sys.argv, io.StringIO(), None
        result['original_entry_invoked'] = True
        try:
            sys.argv = argv
            with contextlib.redirect_stdout(output):
                try:
                    returned = installer.main()
                except SystemExit as error:
                    returned = error.code
        finally:
            sys.argv = saved
            raw = output.getvalue().encode('utf-8')
            result.update(original_returncode=returned, original_stdout=raw.decode('utf-8'), original_stdout_bytes=len(raw),
                          original_stdout_sha256=sha(raw), original_argv=argv)
        need(type(returned) is int and returned == 0, 'ORIGINAL_INSTALL_FAILED_NO_RETRY_OR_AUTOMATIC_RECONCILIATION')
        original, result_pin = verify_install(base, core, request, qualified['qualified_build'], raw)
        need(completed_b_gate(base) == result['completed_no_action_B'], 'COMPLETED_B_AND_OLD_FAILURE_EVIDENCE_UNCHANGED')
        need(completed_build_gate(base) == qualified, 'ACTUAL_BUILD_AND_SOURCE_AFTER_INSTALL_UNCHANGED')
        for pin in (SELF, REQUEST, BASE, INSTALLER, ADAPTER, HELPER_MANIFEST, PARENT_SCOPE,
                    BUILD_STDOUT, BUILD_TERMINAL, base.RECORDER, base.CORE, base.SUPPORT, support.PROBE_SOURCE):
            base.pinned(pin)
        support.pin_runtime_files(probe, observed)
        final = probe.census(); extra = set(final) - set(frozen)
        need(len(extra) == 1 and probe.same_descriptors(frozen, {k: v for k, v in final.items() if k in frozen}),
             'ONLY_DECLARED_ORIGINAL_FLOW_LOCK_MAY_REMAIN')
        held = final[next(iter(extra))]
        need(held['link'] == FLOW + '/flow.lock' and held['fstat'] == lock_metadata and held['descriptor_flags'] == 1 and
             held['status_flags'] & os.O_ACCMODE == os.O_RDWR and
             support.stable_library(probe.library_binding(library_fd, final[str(library_fd)])) == support.stable_library(library),
             'ORIGINAL_FLOW_LOCK_AND_EXPLICIT_LIBRARY_UNCHANGED')
        result.update(ok=True, original_result=result_pin, original_action_attempted=original['action_attempted'],
            original_action_outcome_unknown=original['outcome_unknown'], helper_uid=original['helper_uid'],
            next_app_scope=original['next_app_scope'], whole_scope_transition=original['whole_scope_after']['transition'],
            original_namespace_authority_released=True, normal_process_exit_required_for_lock_and_library=True,
            final_descriptors=final, unknown_descriptors_closed=0, manual_library_close=False,
            original_private_UI_nodes_exported=False)
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    result['outcome_unknown'] = bool(result.get('original_action_outcome_unknown', result['original_entry_invoked'] and not result['ok']))
    raw = canonical(result); need(len(raw) <= 131072, 'CHILD_OUTPUT_BOUND')
    print(raw.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1


def parent():
    base = entry('--install-once')
    result = {'schema': 'pocket4-owned-search-helper-coexist-result-v1', 'ok': False, 'errors': [],
        'source': SELF, 'request': REQUEST, 'flow': FLOW, 'package': PACKAGE,
        'original_FAILED_UNKNOWN_rewritten': False, 'reconciliation_published': False,
        'production_ready': False, 'automatic_retry': False, 'UI_actions': 0, 'permission_grants': 0,
        'target_App_launches': 0, 'old_helper_uninstalled': False, 'old_products_deleted': False,
        'full_PM_or_launcher_inventory_claimed': False,
        'acceptance_requires_original_stdout_and_authoritative_durable_terminal': True}
    invoked = False
    try:
        support = base.load(base.SUPPORT, 'unchanged_owned_library_functions')
        probe = support.load_module(support.PROBE_SOURCE, 'unchanged_pidfd_lifetime_functions')
        observed = support.probe_proof(); support.pin_runtime_files(probe, observed)
        before = probe.census(); need(set(before) == {'0', '1', '2'}, 'PARENT_INITIAL_STDIO_ONLY')
        core = base.load(base.CORE, 'unchanged_request_document_parser')
        request = request_value(base.pinned(REQUEST), core)
        for pin in (INSTALLER, ADAPTER, HELPER_MANIFEST, PARENT_SCOPE, STAGE_B_SOURCE, STAGE_B_REQUEST,
                    STAGE_B_STDOUT, STAGE_B_TERMINAL, BUILD_STDOUT, BUILD_TERMINAL):
            base.pinned(pin)
        marker = Path(ROOT) / 'attempt.json'
        write_once(base, marker, canonical({'source': SELF, 'request': REQUEST, 'step': request['step'],
                   'automatic_retry': False, 'child_not_yet_started': True}) + b'\n')
        need(probe.same_descriptors(before, probe.census()), 'PARENT_DESCRIPTORS_BEFORE_CHILD')
        argv = [sys.executable, '-I', '-B', SELF['path'], '--child', '--source-sha256', SELF['sha256'],
                '--source-bytes', str(SELF['bytes']), '--request-sha256', REQUEST['sha256'], '--request-bytes', str(REQUEST['bytes'])]
        invoked = True
        life, raw, stderr = probe.run_owned_child(argv, seconds=600)
        result.update(child_lifecycle=life, child_stdout_original=raw.decode('utf-8', 'strict'), child_stdout_bytes=len(raw),
            child_stdout_sha256=sha(raw), child_stderr_original=stderr.decode('utf-8', 'replace'),
            child_stderr_bytes=len(stderr), child_stderr_sha256=sha(stderr))
        base.require_owned_exit(life, stderr)
        value = core.document(raw)
        need(value.get('schema') == 'pocket4-owned-search-helper-coexist-child-v1' and value.get('ok') is True and
             value.get('errors') == [] and value.get('source') == SELF and value.get('request') == REQUEST and
             value.get('flow') == FLOW and value.get('step') == request['step'] and
             value.get('original_entry_invoked') is True and value.get('original_returncode') == 0 and
             value.get('original_action_attempted') is True and value.get('original_action_outcome_unknown') is False and
             value.get('outcome_unknown') is False and value.get('original_namespace_authority_released') is True and
             value.get('normal_process_exit_required_for_lock_and_library') is True and
             value.get('unknown_descriptors_closed') == 0 and value.get('manual_library_close') is False and
             value.get('original_private_UI_nodes_exported') is False,
             'NORMAL_INSTALL_AND_OWNED_CHILD_EXIT_JOINTLY_REQUIRED')
        original_raw = value['original_stdout'].encode('utf-8')
        need(len(original_raw) == value['original_stdout_bytes'] and sha(original_raw) == value['original_stdout_sha256'],
             'EXACT_ORIGINAL_INSTALL_STREAM')
        original, result_pin = verify_install(base, core, request, value['completed_build']['qualified_build'], original_raw)
        need(result_pin == value['original_result'] and original['next_app_scope'] == value['next_app_scope'] and
             original['helper_uid'] == value['helper_uid'], 'SAME_ACTUAL_NEW_UID_AND_49_SCOPE')
        for pin in (SELF, REQUEST, BASE, INSTALLER, ADAPTER, HELPER_MANIFEST, PARENT_SCOPE,
                    BUILD_STDOUT, BUILD_TERMINAL, STAGE_B_SOURCE, STAGE_B_REQUEST, STAGE_B_STDOUT, STAGE_B_TERMINAL,
                    base.SUPPORT, support.PROBE_SOURCE):
            base.pinned(pin)
        support.pin_runtime_files(probe, observed)
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_RESTORED')
        result.update(ok=True, step=request['step'], original_result=result_pin,
            completed_build=value['completed_build'], completed_no_action_B=value['completed_no_action_B'],
            helper_uid=original['helper_uid'], next_app_scope=original['next_app_scope'],
            observed_explicit_packages=49, observed_APKs=89, all_original48_unchanged=True,
            normal_PM_install_success_observed=True, state_without_UiAutomation_verified=True,
            original_action_attempted=True, original_action_outcome_unknown=False, outcome_unknown=False,
            all_owned_child_resources_retired_by_normal_pidfd_exit=True, parent_whole_process_FD_identity_restored=True,
            current_scope_adoption_requires_this_actual_durable_terminal=True,
            later_QA_permissions_and_framework_must_rebind_actual_new_scope=True)
        artifact = write_once(base, Path(ROOT) / 'owned-install-joint.json', canonical(result) + b'\n')
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_AFTER_ARTIFACT')
        result['joint_artifact'] = artifact
    except BaseException as error:
        result['ok'] = False
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    if not result['ok']:
        result['outcome_unknown'] = invoked
        result['current_scope_must_not_advance_from_partial_outputs'] = True
    raw = canonical(result); need(len(raw) <= 262144, 'PARENT_OUTPUT_BOUND')
    print(raw.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    mode = sys.argv[1:2]
    if mode == ['--child']:
        raise SystemExit(child())
    need(mode == ['--install-once'], 'CLOSED_SINGLE_NORMAL_INSTALL_OWNER')
    raise SystemExit(parent())
