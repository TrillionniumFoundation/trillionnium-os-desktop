"""Pinned existing R2 CLI and successful bounded Git journal qualification.

This is a reusable adaptation of the reviewed existing qualifier and journal gate.
Import performs no filesystem, lock, child, source, or build operation. It does
not launch or authorize a recovery. Callers must separately qualify the actual
Audio316 source/full retirement and current owner before normal Native admission.
The reader passed to qualify_normal_cli must hold, bound, hash, and recheck each
exact file and named inode; preserve all returned identities for its post-check.
"""
from pathlib import Path
import hashlib
import json
P = Path
RETRY_ROOT = Path('/home/alex/work/pocket4-native-source-transport-retry-20261108-r2')
NORMAL_CLI = RETRY_ROOT / "target/release/droidloom-source"
C = Path('/home/alex/work/pocket4-android-final/native/source-evidence/native-known-physical-lock-candidate-20261108-r2')
SOURCE = Path("/home/alex/work/pocket4-android-final/native/work/aosp-source")
NEW_SHA = "2b699174977614e080cf99a991f3e648774b24581c4ecdc29f1bd53b7b01ef23"
NORMAL_CLI_PIN = {'path': '/home/alex/work/pocket4-native-source-transport-retry-20261108-r2/target/release/droidloom-source', 'bytes': 1627024, 'sha256': '0a4a4bc426b1db8ec325d093858e9d9ce3200e8f0be33c93f4ea266566b73bda'}
NORMAL_CLI_QUALIFICATION_PIN = {'path': '/home/alex/work/pocket4-native-source-transport-retry-20261108-r2/audit/qualification.json', 'bytes': 6016, 'sha256': '3b463c4d6ca664efc5848882b5278e59960bbf450290fb667c4e3950ead8a71d'}
NORMAL_CLI_PROCESS_RESULT_PIN = {'path': '/home/alex/work/pocket4-native-source-transport-retry-20261108-r2/audit/process-result.json', 'bytes': 71905, 'sha256': '42ab374771c0f47481f74acf66f6edd5b26f9b80dfbb889c395394779992196a'}
NORMAL_CLI_PHYSICAL_PIN = {'path': '/home/alex/work/pocket4-native-source-transport-retry-20261108-r2/audit/physical-retirement.json', 'bytes': 410, 'sha256': '426638ec211132c0df4f880b0c6dfe866a1742ff27534c1340b5a83690c8eb00'}
R2_CLASSIFIER_SOURCE_PIN = {'path': '/home/alex/work/pocket4-native-source-transport-retry-20261108-r2/source/tools/droidloom-source/src/git_retry.rs', 'bytes': 30876, 'sha256': '956435860d0a7cd14880128b3bb80aa946b7e328da5cf34aa31efbfe37fe619f'}
R2_HARD_DENY = (b'authentication failed', b'authorization failed', b'could not read username', b'could not read password', b'permission denied', b'access denied', b'proxy authentication required', b'http 401', b'http 403', b'http 407', b'returned error: 401', b'returned error: 403', b'returned error: 407', b'repository not found', b'returned error: 404', b"couldn't find remote ref", b'could not find remote ref', b'not our ref', b'unadvertised object', b'reference is not a tree', b'not a valid object', b'invalid object', b'bad object', b'bad tree object', b'corrupt', b'checksum mismatch', b'sha1 mismatch', b'sha-1 mismatch', b'sha256 mismatch', b'sha-256 mismatch', b'inflate: data stream error', b'inflate returned', b'invalid pack', b'did not receive expected object', b'no space left', b'disk quota exceeded', b'read-only file system', b'input/output error', b'too many open files', b'unable to create', b'cannot create', b'index.lock', b'shallow.lock', b'packed-refs.lock', b'another git process', b'dubious ownership', b'certificate', b'ssl peer', b'ssl routines', b'tls handshake')

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def qualify_h_terminal(document, job_id, state, exit_code):
    need(document.get('job_id') == job_id and document.get('state') == state
         and type(document.get('exit_code')) is int and document['exit_code'] == exit_code
         and document.get('timed_out') is False and document.get('cancelled') is False
         and document.get('automatic_retry') is False
         and document.get('output_complete') is True and document.get('output_durable') is True
         and document.get('terminal_publication_confirmed') is True
         and document.get('log_errors') == {'stdout': None, 'stderr': None}
         and document.get('log_truncated') == {'stdout': False, 'stderr': False}
         and document.get('log_synced') == {'stdout': True, 'stderr': True},
         'exact complete durable predecessor H terminal required')

def qualify_normal_cli(reader):
    qualified = json.loads(reader(NORMAL_CLI_QUALIFICATION_PIN,
        RETRY_ROOT / 'audit/qualification.json', 65536))
    need(qualified['schema_version'] == 1 and qualified['qualified'] is True
         and qualified['qualification'] == 'independent_normal_source_cli_with_opt_in_transport_retries'
         and qualified['candidate_root'] == str(RETRY_ROOT)
         and qualified['source_root'] == str(RETRY_ROOT / 'source')
         and qualified['base_root'] == str(C / 'builder-source-r4')
         and qualified['binary'] == NORMAL_CLI_PIN
         and qualified['process_result'] == NORMAL_CLI_PROCESS_RESULT_PIN
         and qualified['physical_retirement'] == NORMAL_CLI_PHYSICAL_PIN
         and qualified['frozen_base_unchanged'] is True
         and qualified['current_source_modified'] is False
         and qualified['full_builder_modified'] is False
         and qualified['network_reconcile_run'] is False and qualified['six_locks_taken'] is False
         and qualified['source_file_count'] == 457
         and qualified['cargo_lock_sha256'] == 'c1dfa6f13f789cf40435d0d72973d029d0e264b27bd833eabb5a727492127f62'
         and qualified['changed_paths'] == ['tools/droidloom-source/src/git_retry.rs',
             'tools/droidloom-source/src/lib.rs', 'tools/droidloom-source/src/main.rs'],
         'exact isolated ordinary-source CLI qualification required')
    expected_interface = {"accepted_attempts": [1, 3], "backoff_ms": [1000, 3000], "commands": ["materialize", "reconcile"], "default_attempts": 1, "journal_create_only": True, "journal_events": ["header", "attempt_start", "attempt_finish", "execution_error"], "journal_mode": "0600", "journal_outside_output_and_staging": True, "journal_parent_private_owned_real": True, "journal_schema_version": 1, "max_attempts_total": 3, "nested_retry": False, "retry_flags": ["--git-transport-attempts", "3", "--git-attempt-journal", "<new-absolute-private-jsonl-file>"], "retry_operations": ["fetch", "checkout"], "signal_or_io_or_journal_failure_retried": False}
    need(qualified['interface'] == expected_interface, 'reviewed bounded transport interface changed')
    reader(NORMAL_CLI_PIN, NORMAL_CLI, 16 * 1024 * 1024)
    evidence = {}
    for name in ('base_source_manifest', 'compiled_source_manifest', 'patch', 'build_test_result',
                 'build_admission', 'build_environment', 'build_resources', 'process_result', 'physical_retirement'):
        pin = qualified[name]
        raw = reader(pin, P(pin['path']), 128 * 1024)
        evidence[name] = json.loads(raw) if name not in ('base_source_manifest', 'compiled_source_manifest', 'patch') else None
    expected_protected = [
        {'path': str(C / 'bin-r4/droidloom-source'), 'bytes': 1501880,
         'sha256': '9fd7276af58c56b2a970c5586aad792dbfca29ced9a1eab4dea19bec135f5a86'},
        {'path': str(C / 'bin-r4/droidloom-update'), 'bytes': 3805784,
         'sha256': '75bf728444a101d39428a8c90a876e53d3325c1e45441c132b2552deb74660f0'}]
    need(qualified['protected_original_binaries'] == expected_protected,
         'historical source CLI and full updater must keep their original identities')
    for pin in expected_protected:
        reader(pin, P(pin['path']), 16 * 1024 * 1024)
    compiled = evidence['build_test_result']
    need(compiled['schema_version'] == 1 and compiled['error'] is None
         and compiled['all_four_focused_tests_passed'] is True
         and compiled['release_succeeded'] is True and compiled['network_isolated'] is True
         and compiled['source_verify_after_build'] is True
         and compiled['binary'] == NORMAL_CLI_PIN
         and compiled['compiled_source_manifest'] == qualified['compiled_source_manifest'],
         'real focused tests and offline release must qualify the exact new executable')
    names = ['git_retry::tests::transport_classifier_parameterized',
        'git_retry::tests::transport_retry_and_journal_parameterized',
        'tests::exact_local_git_fetch_and_manifest_link_are_verified',
        'tests::materialized_verification_rejects_dirty_projects']
    need(qualified['test_names'] == names and len(compiled['steps']) == 5,
         'exact four focused regressions and one release required')
    cargo = '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/cargo'
    for index, step in enumerate(compiled['steps']):
        expected = ([cargo, 'test', '--locked', '--offline', '-j', '1', '-p', 'droidloom-source',
                     '--lib', '--target-dir', str(RETRY_ROOT / 'target'), names[index],
                     '--', '--exact', '--nocapture', '--test-threads=1'] if index < 4 else
                    [cargo, 'build', '--locked', '--offline', '--release', '-j', '1',
                     '-p', 'droidloom-source', '--bin', 'droidloom-source',
                     '--target-dir', str(RETRY_ROOT / 'target')])
        need(step['exit_code'] == 0 and type(step['exit_code']) is int and step['argv'] == expected
             and step['cwd'] == str(RETRY_ROOT / 'source')
             and (index == 4 or step['exactly_one_test_passed'] is True),
             'actual tested command or release differs')
        for stream in ('stdout', 'stderr'):
            reader(step[stream], RETRY_ROOT / 'audit' / (step['name'] + '.' + stream),
                           1048576, allow_empty=True)
    process = evidence['process_result']
    build_job = '1a1bb00c20d-12894-1f01'
    terminal = process['build']['status']
    qualify_h_terminal(terminal, build_job, 'succeeded', 0)
    need(qualified['build_job'] == {'id': build_job, 'state': 'succeeded', 'exit_code': 0,
         'output_complete': True, 'output_durable': True, 'terminal_publication_confirmed': True},
         'qualification summary must bind the exact actual R2 job')
    need(terminal['log_bytes'] == {'stdout': {'seen': 1744, 'stored': 1744},
         'stderr': {'seen': 0, 'stored': 0}}, 'R2 original durable logs must remain complete')
    need(process['build']['job_id'] == build_job
         and process['build']['start']['job']['id'] == build_job
         and terminal['launch_nonce'] == '446259a61d36c5092783c9d4b3a09fa2'
         and terminal['at_unix_ms'] == 1794138810702,
         'same actual successful offline build H generation required')
    resources = evidence['build_resources']
    fields = resources['resource_after']
    events = dict(line.split() for line in fields['memory.events'].splitlines())
    need(resources['exit_code'] == 0 and fields['cpu.max'] == '100000 100000'
         and fields['memory.max'] == '1610612736' and fields['memory.peak'] == '536969216'
         and fields['memory.swap.current'] == fields['memory.swap.max'] == '0'
         and all(events.get(name) == '0' for name in ('max', 'oom', 'oom_kill', 'oom_group_kill')),
         'actual independent CLI build must retain clean bounded resource evidence')
    retired = evidence['physical_retirement']
    need(retired['schema_version'] == 1 and retired['complete'] is True
         and retired['build_job_id'] == build_job and retired['cgroup_exists'] is False
         and retired['cgroup_procs'] == [] and retired['active_build_or_candidate_tool_processes'] == []
         and retired['scan_errors'] == [] and retired['proc_entries_checked'] == 682
         and retired['cgroup_path'] == '/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-' + build_job + '.service'
         and not P(retired['cgroup_path']).exists(), 'actual independent CLI build physical retirement required')
    return {'qualification': NORMAL_CLI_QUALIFICATION_PIN, 'process_result': NORMAL_CLI_PROCESS_RESULT_PIN,
            'physical_retirement': NORMAL_CLI_PHYSICAL_PIN, 'binary': NORMAL_CLI_PIN,
            'build_job_id': build_job, 'build_H_state': 'succeeded',
            'frozen_full_builder_unchanged': True, 'network_reconcile_claimed': False}

def r2_transient_stderr(stderr):
    need(type(stderr) is bytes, 'complete raw Git stderr required')
    lower = stderr.lower()
    if any(pattern in lower for pattern in R2_HARD_DENY):
        return False
    return (b'gnutls recv error (-110): the tls connection was non-properly terminated.' in lower
            or (b'curl 56 ' in lower and
                (b'recv failure: connection timed out' in lower
                 or b'recv failure: connection reset by peer' in lower)))

def validate_transport_journal(raw, step):
    need(isinstance(raw, bytes) and 0 < len(raw) <= 128 * 1024 * 1024 and raw.endswith(b'\n'),
         'complete bounded normal transport journal required')
    lines = raw.splitlines()
    need(1 <= len(lines) <= 1 + 2 * 597 * 2 * 3, 'bounded ordinary project command journal')
    rows = [json.loads(line) for line in lines]
    header = rows[0]
    need(header == {'schema_version': 1, 'event': 'header', 'process_id': step['pid'],
         'at_unix_ms': header.get('at_unix_ms'), 'maximum_attempts': 3,
         'retry_operations': ['fetch', 'checkout'], 'backoff_ms': [1000, 3000],
         'lock_sha256': NEW_SHA, 'destination_hex': str(SOURCE).encode().hex(),
         'output_encoding': 'hex', 'environment_values_logged': False},
         'same frozen597 normal reconciliation and three-attempt policy required')
    beginning, ending = step['started_ns'] // 1000000, step['finished_ns'] // 1000000
    need(type(header['at_unix_ms']) is int and beginning <= header['at_unix_ms'] <= ending,
         'journal header must belong to the actual reconcile interval')
    need((len(rows) - 1) % 2 == 0, 'every successful source attempt must have a complete finish')
    command_id, attempt, previous_finish, context, retried = 0, 0, None, None, 0
    children_seen = []
    for index in range(1, len(rows), 2):
        start_row, end_row = rows[index:index+2]
        need(start_row.get('schema_version') == end_row.get('schema_version') == 1
             and start_row.get('event') == 'attempt_start' and end_row.get('event') == 'attempt_finish'
             and start_row.get('process_id') == end_row.get('process_id') == step['pid'],
             'only actual paired ordinary Git starts and finishes may qualify')
        next_id, next_attempt = start_row['command_id'], start_row['attempt']
        if next_id == command_id:
            need(previous_finish is not None and previous_finish['retry'] is True
                 and next_attempt == attempt + 1 and next_attempt <= 3,
                 'same command retries must be consecutive and bounded')
        else:
            need(next_id == command_id + 1 and next_attempt == 1
                 and (previous_finish is None or previous_finish['exit_code'] == 0),
                 'next ordinary command requires the preceding command to succeed')
            command_id, context = next_id, None
        attempt = next_attempt
        need(type(command_id) is int and type(attempt) is int and 1 <= command_id <= 597 * 2
             and 1 <= attempt <= 3 and end_row['command_id'] == command_id
             and end_row['attempt'] == attempt and end_row['operation'] == start_row['operation']
             and start_row['operation'] in ('fetch', 'checkout'),
             'exact bounded typed fetch or checkout event required')
        argv = [bytes.fromhex(value) for value in start_row['argv_hex']]
        need(start_row['program_hex'] == b'git'.hex() and len(argv) >= 3 and argv[0] == b'-C'
             and argv[2] == start_row['operation'].encode()
             and start_row['cwd_hex'] == str(C / 'builder-source-r4').encode().hex()
             and len(start_row['environment_sha256']) == 64
             and all(ch in '0123456789abcdef' for ch in start_row['environment_sha256']),
             'ordinary Git argv, working directory and captured environment required')
        current_context = {key: start_row[key] for key in
            ('operation', 'program_hex', 'argv_hex', 'cwd_hex', 'environment_sha256')}
        if context is None:
            context = current_context
        else:
            need(current_context == context, 'transport retry changed command context')
        need(type(start_row['at_unix_ms']) is int and type(end_row['at_unix_ms']) is int
             and beginning <= start_row['at_unix_ms'] <= end_row['at_unix_ms'] <= ending
             and end_row['started_at_unix_ms'] == start_row['at_unix_ms']
             and type(end_row['elapsed_ms']) is int and end_row['elapsed_ms'] >= 0
             and type(end_row['child_pid']) is int and end_row['child_pid'] > 1
             and end_row['signal'] is None and type(end_row['exit_code']) is int,
             'complete direct Git child status and timing required')
        stdout, stderr = bytes.fromhex(end_row['stdout_hex']), bytes.fromhex(end_row['stderr_hex'])
        children_seen.append(end_row['child_pid'])
        if end_row['exit_code'] == 0:
            need(end_row['decision'] == 'success' and end_row['retry'] is False
                 and end_row['backoff_ms'] == 0, 'actual successful Git completion required')
        else:
            need(end_row['exit_code'] == 128 and attempt < 3
                 and end_row['decision'] == 'transient_retry' and end_row['retry'] is True
                 and end_row['backoff_ms'] == (1000 if attempt == 1 else 3000)
                 and r2_transient_stderr(stderr),
                 'only fully logged typed transient128 retries may precede success')
            retried += 1
        previous_finish = end_row
    need(previous_finish is None or previous_finish['exit_code'] == 0,
         'successful normal reconciliation cannot end on an uncompleted retry')
    return {'schema_version': 1, 'records': len(rows), 'commands': command_id,
            'completed_attempts': len(children_seen), 'transient_retries': retried,
            'all_commands_final_exit_zero': True, 'all_attempts_closed': True,
            'all_retries_same_context': True, 'direct_child_pids': children_seen}
