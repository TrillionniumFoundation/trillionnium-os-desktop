#!/usr/bin/env python3
"""Review candidate: explicit new owned-qa proof producer for one existing flow.

Default is PLAN_ONLY. Publication requires a new externally pinned request with
actual completed action/observation records. This never calls Flow.reconcile,
does not modify the frozen recorder/helper, and never rewrites the old UNKNOWN.
Runtime commands are the existing held R5 read-only identity/task/foreground
checks. There is no instrumentation, click, input, launch, install, grant or ADB.
"""
import argparse
import ast
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

CORE_BYTES = 28714
CORE_SHA = '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41'
SOURCE_ROOT = Path('/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03')
HELPER_ROOT = Path('/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03')
RECORDER_ROOT = SOURCE_ROOT / 'recorder'
BUILD_PATH = Path('/home/alex/work/pocket4-successor-qa-build-b34f158f88bbebf112840fd88df25d03/build-result.json')
FFI_BOOTSTRAP = {
    'path': '/home/alex/work/pocket4-beike-owned-generation-20261106-b34f158f88bbebf112840fd88df25d03/prepare_beike_owned_lifetime.py',
    'bytes': 20132, 'sha256': '76b858b83c7304287fedb13f80c889e3fa7a8d6d32d4183409a5ad6fce269baf'}
STAT_KEYS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
             'st_size', 'st_mtime_ns', 'st_ctime_ns')
MAX_TOTAL_INPUT = 40 * 1024 * 1024
MAX_FILES = 320
DEADLINE_SECONDS = 240
REQUEST_SCHEMA = 'pocket4-beike-owned-postcondition-request-v1'
PROOF_SCHEMA = 'pocket4-beike-owned-qa-postcondition-proof-v1'
ORIGINAL_ENTRIES = {
    'action': {'bytes': 4496, 'sha256': 'c062807e2bbab080d496f75db0fd1b90b703daa353b1010757bd6896dff2bec4',
               'publication_schema': 'pocket4-owned-close-popup-plan-publication-v1'},
    'observation': {'bytes': 4205, 'sha256': 'd9ce84cfbf8f9f310f1e283f49af84a7f4dd49e678fd94612bc5af42aa47322c',
                    'publication_schema': 'pocket4-owned-inspection-plan-publication-v1'}}
ROOT_PLAN_FILES = ('qa-close-entry-popup-01.plan.json', 'qa-inspect-after-close-02.plan.json')
PRIVATE_BUNDLE = {'path': '/home/alex/work/pocket4-beike-postcondition-evidence-20261106-r1/bundle.private.json',
                  'bytes': 1218042, 'sha256': '3c72bc43b2a32950a576405049b12cf6984ef790978638122ef2a7d4602941c8'}
HOME_POSTCONDITION = {'resource_id': 'com.lianjia.beike:id/tv_home_tab_selected', 'text': '\u9996\u9875',
                      'class': 'android.widget.TextView', 'enabled': True, 'clickable': False}


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def safe_relative(value):
    need(type(value) is str and 0 < len(value) <= 1024 and '\\' not in value and '\0' not in value and
         not value.startswith('/') and all(x not in ('', '.', '..') for x in value.split('/')),
         'EXACT_SAFE_RELATIVE_PATH')
    return value


def pin_shape(row, maximum=2 * 1024 * 1024):
    need(type(row) is dict and set(row) == {'bytes', 'sha256'} and
         type(row['bytes']) is int and 0 <= row['bytes'] <= maximum and
         type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'CLOSED_BYTE_PIN')
    return row


def host_pinned(path, digest, maximum=1048576, exact_bytes=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_uid == 0 and
             not first.st_mode & 0o022 and 0 <= first.st_size <= maximum,
             'ROOT_OWNED_BOUNDED_SINGLE_FILE')
        chunks = []; count = 0
        while count <= first.st_size:
            part = os.read(fd, min(65536, first.st_size + 1 - count))
            if not part:
                break
            chunks.append(part); count += len(part)
        raw = b''.join(chunks)
        last, current = os.fstat(fd), os.stat(path, follow_symlinks=False)
        need(count == first.st_size and (exact_bytes is None or count == exact_bytes) and
             sha(raw) == digest and all(getattr(first, k) == getattr(last, k) == getattr(current, k)
                                       for k in STAT_KEYS), 'EXACT_PIN_AND_UNCHANGED_FILE_REQUIRED')
        return raw
    finally:
        os.close(fd)


def load(path, digest, module_name, maximum=1048576, exact_bytes=None):
    raw = host_pinned(path, digest, maximum, exact_bytes)
    value = types.ModuleType(module_name); value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


class PinnedRoot:
    """One private root FD, no-follow component traversal and before/after checks."""
    def __init__(self, path, pins, deadline):
        self.path = Path(path); self.pins = pins; self.deadline = deadline
        self.fd = None; self.total = 0; self.observed = {}
        need(self.path.is_absolute() and self.path.resolve() == self.path and
             type(pins) is dict and len(pins) <= MAX_FILES, 'BOUNDED_CANONICAL_PRIVATE_INPUT_ROOT')
        for rel, row in pins.items():
            safe_relative(rel); pin_shape(row)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            self.identity = os.fstat(self.fd)
            need(stat.S_ISDIR(self.identity.st_mode) and self.identity.st_uid == 0 and
                 not self.identity.st_mode & 0o077, 'ROOT_PRIVATE_DIRECTORY')
        except BaseException:
            fd, self.fd = self.fd, None
            os.close(fd)
            raise

    def check(self):
        need(time.monotonic() < self.deadline, 'TOTAL_RECONCILIATION_DEADLINE')
        live = os.stat(self.path, follow_symlinks=False)
        held = os.fstat(self.fd)
        need((live.st_dev, live.st_ino, live.st_mode, live.st_uid, live.st_gid) ==
             (held.st_dev, held.st_ino, held.st_mode, held.st_uid, held.st_gid) ==
             (self.identity.st_dev, self.identity.st_ino, self.identity.st_mode,
              self.identity.st_uid, self.identity.st_gid), 'PRIVATE_ROOT_REPLACED')

    def parent(self, relative):
        self.check(); parts = safe_relative(relative).split('/')
        owned = []
        current = self.fd
        try:
            for part in parts[:-1]:
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
                owned.append(fd); row = os.fstat(fd)
                need(row.st_uid == 0 and not row.st_mode & 0o077, 'PRIVATE_INPUT_PARENT_CHANGED')
                current = fd
            return current, parts[-1], owned
        except BaseException:
            for fd in reversed(owned):
                os.close(fd)
            raise

    def read(self, relative):
        need(relative in self.pins, 'UNPINNED_EVIDENCE_FILE')
        row = self.pins[relative]; parent, leaf, owned = self.parent(relative)
        fd = None
        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
            first = os.fstat(fd)
            need(stat.S_ISREG(first.st_mode) and first.st_uid == 0 and first.st_nlink == 1 and
                 not first.st_mode & 0o077 and first.st_size == row['bytes'], 'PRIVATE_PINNED_EVIDENCE_FILE')
            chunks = []; count = 0
            while count <= first.st_size:
                self.check()
                part = os.read(fd, min(65536, first.st_size + 1 - count))
                if not part:
                    break
                chunks.append(part); count += len(part)
            raw = b''.join(chunks)
            last, current = os.fstat(fd), os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            need(count == row['bytes'] and sha(raw) == row['sha256'] and
                 all(getattr(first, k) == getattr(last, k) == getattr(current, k) for k in STAT_KEYS),
                 'EVIDENCE_BYTES_OR_INODE_CHANGED')
            self.total += count
            need(self.total <= 4 * MAX_TOTAL_INPUT, 'TOTAL_EVIDENCE_READ_BOUND')
            previous = self.observed.setdefault(relative, tuple(getattr(first, k) for k in STAT_KEYS))
            need(previous == tuple(getattr(first, k) for k in STAT_KEYS), 'EVIDENCE_REPLACED_BETWEEN_READS')
            return raw
        finally:
            if fd is not None:
                os.close(fd)
            for item in reversed(owned):
                os.close(item)

    def step(self, selected):
        prefix = 'steps/' + selected + '/'
        pins = {key[len(prefix):]: row for key, row in self.pins.items() if key.startswith(prefix)}
        need(pins and all('/' not in key for key in pins), 'SINGLE_FLAT_STEP_INPUT_CLOSURE')
        parent, leaf, owned = self.parent('steps/' + selected)
        fd = None
        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            need(set(os.listdir(fd)) == set(pins), 'ACTUAL_STEP_FILE_SET_DIFFERS')
        finally:
            if fd is not None:
                os.close(fd)
            for item in reversed(owned):
                os.close(item)
        return {key: self.read(prefix + key) for key in sorted(pins)}

    def recheck(self):
        self.check()
        for name in sorted(self.observed):
            self.read(name)
        self.check()

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)


def original_adapter_arguments(requested, role):
    need(role in ORIGINAL_ENTRIES, 'EXACT_ACTION_OR_OBSERVATION_ROLE')
    outer_argv = requested['args']
    entry = ORIGINAL_ENTRIES[role]
    need(type(outer_argv) is list and len(outer_argv) == 6 and
         outer_argv[:5] == ['-n', '/usr/bin/python3', '-I', '-B', '-c'] and
         type(outer_argv[5]) is str and len(outer_argv[5].encode('utf-8')) == entry['bytes'] and
         sha(outer_argv[5].encode('utf-8')) == entry['sha256'], 'EXACT_REVIEWED_ORIGINAL_PLAN_PUBLICATION_ENTRY')
    # The entire entry has an independently reviewed exact byte pin. AST is
    # used only to recover its already fixed literal ARGV; it is never executed.
    candidates = [node.value for node in ast.parse(outer_argv[5]).body if isinstance(node, ast.Assign) and
                  any(isinstance(target, ast.Name) and target.id == 'ARGV' for target in node.targets)]
    need(len(candidates) == 1, 'ONE_LITERAL_ORIGINAL_ADAPTER_ARGV')
    inner_argv = ast.literal_eval(candidates[0])
    need(type(inner_argv) is list and len(inner_argv) == 25 and
         inner_argv[0] == str(HELPER_ROOT / 'qa_adapter.py') and
         all(type(item) is str for item in inner_argv), 'ONLY_ORIGINAL_FROZEN_ADAPTER_ENTRY')
    return ['-n', '/usr/bin/python3', '-I', '-B', *inner_argv]


def execution_proof(core, inputs, role, checked, selected):
    def read(suffix):
        return inputs.read(role + '.' + suffix)
    requested = core.document(read('process-request.json'))
    started = core.document(read('process-start.json'))
    terminal = core.document(read('terminal.json'))
    stdout, stderr, plan_raw = read('stdout.jsonl'), read('stderr.bin'), read('plan.json')
    job = started.get('job', {})
    need(requested.get('host') == 'pocket4' and requested.get('executable') == '/usr/bin/sudo' and
         requested.get('cwd') == '/home/alex/work' and 'env' not in requested and 'stdin' not in requested and
         type(requested.get('timeout_seconds')) is int and 0 < requested['timeout_seconds'] <= 1800 and
         started.get('audit_recorded') is True and started.get('local_record_pending') is False and
         started.get('reused') is False and started.get('launch', {}).get('ok') is True and
         job.get('launch_state') == 'launched' and job.get('launch_error') is None and
         job.get('host') == 'pocket4' and job.get('executable') == requested['executable'] and
         job.get('args') == requested.get('args') and job.get('cwd') == requested['cwd'] and
         job.get('idempotency_key') == requested.get('idempotency_key') and job.get('env_keys') == [],
         'ACTUAL_EXACT_PROCESS_START_REQUIRED')
    argv = original_adapter_arguments(requested, role)
    entry = ORIGINAL_ENTRIES[role]
    flags = {}; index = 5
    while index < len(argv):
        flag = argv[index]
        need(type(flag) is str and flag not in flags and flag.startswith('--'), 'EXACT_UNIQUE_CLI_FLAG')
        if flag in ('--execute-once', '--interactive-production'):
            flags[flag] = True; index += 1
        else:
            need(index + 1 < len(argv) and type(argv[index + 1]) is str, 'CLI_VALUE_REQUIRED')
            flags[flag] = argv[index + 1]; index += 2
    expected = {'--execute-once': True, '--interactive-production': True,
                '--source-manifest-sha256': core.HELPER_MANIFEST,
                '--build-receipt': str(BUILD_PATH), '--build-receipt-sha256': core.BUILD_RECEIPT,
                '--apk-sha256': core.APK_SHA, '--signer-certificate-sha256': core.SIGNER_SHA,
                '--recorder-root': str(RECORDER_ROOT), '--flow-dir': core.FLOW,
                '--helper-uid': str(core.HELPER_UID), '--step': selected,
                '--plan-sha256': checked['intent']['request']['plan_sha256']}
    need(set(flags) == set(expected) | {'--plan'} and all(flags[k] == v for k, v in expected.items()) and
         flags['--plan'] == core.FLOW + '/' + ROOT_PLAN_FILES[0 if role == 'action' else 1] and
         sha(plan_raw) == flags['--plan-sha256'] and
         core.document(plan_raw) == checked['plan'], 'ORIGINAL_FIXED_PLAN_SOURCE_AND_ARGUMENTS')
    need(terminal.get('job_id') == job.get('id') and terminal.get('state') == 'succeeded' and
         type(terminal.get('exit_code')) is int and terminal['exit_code'] == 0 and
         terminal.get('automatic_retry') is False and terminal.get('cancelled') is False and
         terminal.get('timed_out') is False and terminal.get('output_complete') is True and
         terminal.get('output_durable') is True and terminal.get('terminal_publication_confirmed') is True and
         terminal.get('audit_recorded') is True, 'ACTUAL_DURABLE_SUCCESSFUL_WORKER_REQUIRED')
    for stream, raw in (('stdout', stdout), ('stderr', stderr)):
        need(terminal.get('log_bytes', {}).get(stream) == {'seen': len(raw), 'stored': len(raw)} and
             terminal.get('log_errors', {}).get(stream) is None and
             terminal.get('log_synced', {}).get(stream) is True and
             terminal.get('log_truncated', {}).get(stream) is False, 'COMPLETE_DURABLE_ORIGINAL_STREAM')
    lines = stdout.splitlines()
    need(stderr == b'' and len(lines) == 2 and core.document(lines[1]) == checked['result'] and
         core.document(lines[0]) == {'schema': entry['publication_schema'], 'plan': flags['--plan'],
             'bytes': len(plan_raw), 'sha256': sha(plan_raw), 'new_plan_only': True, 'UI_actions_before_adapter': 0},
         'TERMINAL_STDOUT_NOT_EXACT_PLAN_PUBLICATION_AND_ORIGINAL_FLOW_RESULT')
    need(type(job.get('created_unix_ms')) is int and type(terminal.get('at_unix_ms')) is int and
         job['created_unix_ms'] <= core.timestamp(checked['intent']['started_utc']).timestamp() * 1000 and
         core.timestamp(checked['result']['ended_utc']).timestamp() * 1000 <= terminal['at_unix_ms'] + 1,
         'ACTUAL_WORKER_AND_FLOW_TIME_ORDER')
    return {'job_id': job['id'], 'idempotency_key': job['idempotency_key'],
            'terminal_sha256': sha(read('terminal.json')), 'stdout_sha256': sha(stdout),
            'process_request_sha256': sha(read('process-request.json')),
            'process_start_sha256': sha(read('process-start.json')), 'plan_sha256': sha(plan_raw)}


def validate_request(core, value, stage):
    need(type(value) is dict and set(value) == {'schema', 'stage_nonce', 'flow_dir', 'unknown_step',
         'observation_step', 'proof_step', 'postcondition', 'private_bundle', 'execution_pins',
         'publish_new_owned_qa_producer'} and value['schema'] == REQUEST_SCHEMA and
         value['publish_new_owned_qa_producer'] is True and value['flow_dir'] == core.FLOW and
         re.fullmatch('[0-9a-f]{32}', value['stage_nonce']) and
         str(stage) == '/home/alex/work/pocket4-beike-owned-postcondition-20261106-' + value['stage_nonce'],
         'EXPLICIT_NEW_REQUEST_AND_PRODUCER_REQUIRED')
    for field in ('unknown_step', 'observation_step', 'proof_step'):
        core.name(value[field])
    need(len({value[k] for k in ('unknown_step', 'observation_step', 'proof_step')}) == 3,
         'DISTINCT_ACTION_OBSERVATION_PROOF_STEPS')
    need(value['unknown_step'] == 'close-entry-popup-01' and value['observation_step'] == 'inspect-after-close-02',
         'ONLY_THIS_ACTUAL_ACTION_AND_INDEPENDENT_OBSERVER')
    core.condition(value['postcondition'])
    need(value['postcondition'] == HOME_POSTCONDITION and value['private_bundle'] == PRIVATE_BUNDLE,
         'EXACT_ROOT_REVIEWED_HOME_NODE_AND_ACTUAL_PRIVATE_BUNDLE')
    ep = value['execution_pins']
    expected = {role + '.' + suffix for role in ('action', 'observation') for suffix in
                ('process-request.json', 'process-start.json', 'terminal.json', 'stdout.jsonl', 'stderr.bin', 'plan.json')}
    need(type(ep) is dict and set(ep) == expected, 'TWELVE_EXACT_ORIGINAL_EXECUTION_FILES')
    for v in ep.values():
        pin_shape(v)
    return value


def frozen_context(core):
    """Host source/build evidence only. This does not construct a Flow/binding."""
    own = load(HELPER_ROOT / 'qa_adapter.py',
               'ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c', 'new_producer_frozen_adapter')
    manifest = own.own_source(core.HELPER_MANIFEST)
    qa = own.load(HELPER_ROOT / 'qa_contract.py', manifest['files']['qa_contract.py']['sha256'], 'new_producer_qa')
    builder = own.load(HELPER_ROOT / 'build_candidate.py', manifest['files']['build_candidate.py']['sha256'], 'new_producer_builder_gate')
    proof_args = types.SimpleNamespace(build_receipt=BUILD_PATH, build_receipt_sha256=core.BUILD_RECEIPT,
        source_manifest_sha256=core.HELPER_MANIFEST, apk_sha256=core.APK_SHA, signer_certificate_sha256=core.SIGNER_SHA)
    build = own.qualified_build(proof_args, manifest, builder)
    core.fixed_build(build)
    rec_manifest = core.document(host_pinned(RECORDER_ROOT / 'source-manifest.json', core.RECORDER_MANIFEST, 131072))
    transport = own.load(RECORDER_ROOT / 'bound_android_transport.py',
                         rec_manifest['files']['bound_android_transport.py']['sha256'], 'new_producer_frozen_transport')
    return own, qa, build, rec_manifest, transport


def verify_private_bundle(core, here, request, context, deadline):
    raw = host_pinned(PRIVATE_BUNDLE['path'], PRIVATE_BUNDLE['sha256'], 2 * 1024 * 1024, PRIVATE_BUNDLE['bytes'])
    bundle = core.document(raw)
    need(set(bundle) == {'schema', 'flow', 'step_file_sets', 'files', 'full_original_bytes',
         'contains_private_UI_evidence', 'approved_for_Git'} and
         bundle['schema'] == 'pocket4-beike-two-step-private-original-byte-bundle-v1' and bundle['flow'] == core.FLOW and
         bundle['full_original_bytes'] is True and bundle['contains_private_UI_evidence'] is True and
         bundle['approved_for_Git'] is False, 'EXACT_ACTUAL_PRIVATE_BUNDLE_SCHEMA')
    rows = bundle['files']
    need(type(rows) is dict and len(rows) == 177, 'ACTUAL_177_FILE_BUNDLE_REQUIRED')
    allowed = {'scope.json', 'launch-scope.json', 'baseline.json', 'baseline-qualification.json', *ROOT_PLAN_FILES}
    prefixes = tuple('steps/' + request[key] + '/' for key in ('unknown_step', 'observation_step'))
    need(allowed <= set(rows) and all(k in allowed or k.startswith(prefixes) for k in rows), 'ONLY_TWO_STEPS_AND_FIXED_METADATA')
    files = {}; pins = {}
    for path, row in rows.items():
        need(time.monotonic() < deadline, 'OFFLINE_BUNDLE_DEADLINE')
        safe_relative(path)
        need(type(row) is dict and set(row) == {'bytes', 'sha256', 'base64'} and type(row['base64']) is str,
             'EXACT_ORIGINAL_BYTE_ROW')
        pin = pin_shape({key: row[key] for key in ('bytes', 'sha256')})
        body = base64.b64decode(row['base64'], validate=True)
        need(len(body) == row['bytes'] and sha(body) == row['sha256'], 'ALL_ORIGINAL_BUNDLE_BYTES_HASHED')
        files[path] = body; pins[path] = pin
    need(sum(map(len, files.values())) == 888207, 'ACTUAL_ORIGINAL_BYTE_TOTAL')
    scope = core.document(files['scope.json']); launch = core.document(files['launch-scope.json'])
    own, qa, build, rec_manifest, transport = context
    phase_files = {}
    for key in ('unknown_step', 'observation_step'):
        selected = request[key]; prefix = 'steps/' + selected + '/'
        phase_files[key] = {path[len(prefix):]: body for path, body in files.items() if path.startswith(prefix)}
        need(bundle['step_file_sets'].get(selected) == sorted(phase_files[key]), 'ORIGINAL_STEP_FILE_SET_PIN')
    need(set(bundle['step_file_sets']) == {request['unknown_step'], request['observation_step']}, 'TWO_EXACT_BUNDLE_STEP_SETS')
    expected_binding = core.document(phase_files['unknown_step']['held-main-binding.json'])
    common = dict(adapter=own, qa=qa, transport=transport, scope=scope, launch=launch, build=build,
                  held_helper_path='/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry',
                  expected_binding=expected_binding)
    action = core.validate_step(phase_files['unknown_step'], mutation=True, **common)
    observed = core.validate_step(phase_files['observation_step'], mutation=False, **common)
    need(observed['assessments']['inspect']['wire_sha256'] ==
         '2123fbdb9b21d88885cb2c443c1bc541458f802d587235f91c667de74d519609', 'ACTUAL_LATER_INSPECTION_WIRE')
    offline = core.validate_pair(action, observed, request['postcondition'], qa=qa,
                                 now=datetime.datetime.now(datetime.timezone.utc))
    need(offline['matched']['node_path'] == '0/0/0/0/0/0/0/1/0/0/1/0/0/1/0/0/0/3/1/0',
         'EXACT_ROOT_REVIEWED_UNIQUE_VISIBLE_HOME_NODE')
    inputs = PinnedRoot(here, request['execution_pins'], deadline)
    try:
        for role, filename in zip(('action', 'observation'), ROOT_PLAN_FILES):
            need(files[filename] == inputs.read(role + '.plan.json'), 'ORIGINAL_PLAN_MATCHES_EXECUTION_SOURCE')
        execution = {'action': execution_proof(core, inputs, 'action', action, request['unknown_step']),
                     'observation': execution_proof(core, inputs, 'observation', observed, request['observation_step'])}
        need(execution['action']['job_id'] == '1a1b1bceb2f-fc05-7a8f' and
             execution['observation']['job_id'] == '1a1b1caee35-fc05-7ad5', 'EXACT_TWO_ACTUAL_SUCCESSFUL_JOBS')
        inputs.recheck()
    finally:
        inputs.close()
    host_pinned(PRIVATE_BUNDLE['path'], PRIVATE_BUNDLE['sha256'], 2 * 1024 * 1024, PRIVATE_BUNDLE['bytes'])
    return {'pins': pins, 'scope': scope, 'launch': launch, 'action': action, 'observed': observed,
            'offline': offline, 'execution': execution}


def _fd_subset(probe, actual, expected):
    need(set(actual) == set(expected) and all(probe.fd_identity(actual[k]) == probe.fd_identity(expected[k])
                                            for k in actual), 'NO_UNKNOWN_OR_REPLACED_PROCESS_DESCRIPTOR')


def commit_envelope(path, raw, nonce):
    """No-replace publication; temporary is exclusively owned by this call."""
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    temporary = '.' + path.name + '.' + nonce + '.pending'
    fd = None; attempted = False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent)
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:]); need(count > 0, 'ENVELOPE_WRITE_STALLED'); offset += count
        os.fsync(fd); os.close(fd); fd = None
        attempted = True
        os.link(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        # Until this unlink the destination has nlink=2 and the frozen consumer
        # rejects it. The flow lock stays held; no existing path is overwritten.
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)
        return {'sha256': sha(raw), 'bytes': len(raw), 'path': str(path)}
    except BaseException as failure:
        failure.publication_attempted = attempted
        raise
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def run(args):
    need(os.getuid() == os.geteuid() == 0, 'ACTUAL_ROOT_REQUIRED')
    os.umask(0o077)
    here = Path(__file__).resolve().parent
    self_raw = host_pinned(Path(__file__).resolve(), args.source_sha256, 131072)
    core_raw = host_pinned(here / 'owned_postcondition_core.py', CORE_SHA, 131072, CORE_BYTES)
    core = load(here / 'owned_postcondition_core.py', CORE_SHA, 'beike_owned_postcondition_core', 131072, CORE_BYTES)
    request_raw = host_pinned(here / 'request.json', args.request_sha256, 131072)
    request = validate_request(core, core.document(request_raw), here)
    # Reuse only the proven explicit library bootstrap functions. This loads no
    # old worker/guard and never adopts an unknown extra FD into a late baseline.
    boot = load(FFI_BOOTSTRAP['path'], FFI_BOOTSTRAP['sha256'], 'frozen_actual_ffi_bootstrap',
                131072, FFI_BOOTSTRAP['bytes'])
    probe = boot.load_module(boot.PROBE_SOURCE, 'frozen_actual_ffi_probe_functions')
    deadline = time.monotonic() + DEADLINE_SECONDS
    host_before = probe.census()
    need(set(host_before) == {'0', '1', '2'}, 'HOST_ONLY_INITIAL_STDIO_DESCRIPTORS')
    context = frozen_context(core)
    archive = verify_private_bundle(core, here, request, context, deadline)
    _fd_subset(probe, probe.census(), host_before)
    if args.verify_host_only:
        print(json.dumps({'schema': 'pocket4-beike-owned-postcondition-host-verification-v1', 'ok': True,
            'private_bundle': PRIVATE_BUNDLE, 'files_verified': len(archive['pins']),
            'original_bytes_verified': 888207, 'original_action_outcome': 'unknown_retained',
            'actual_execution_evidence': archive['execution'], 'matched': archive['offline']['matched'],
            'held_binding_comparison': archive['offline']['held_binding_comparison'],
            'action_commands_verified': archive['action']['command_count'],
            'observation_commands_verified': archive['observed']['command_count'],
            'whole_process_fd_identities_unchanged': True, 'Main_commands': 0,
            'namespace_entries': 0, 'Main_locks_or_guards': 0, 'reconciliation_published': False,
            'live_runtime_or_task_qualification': False, 'production_ready': False,
            'automatic_retry': False}, ensure_ascii=True, sort_keys=True), flush=True)
        return 0
    observed_runtime = boot.probe_proof()
    initial, frozen, library_fd, library = boot.initialize_library(probe, observed_runtime)
    flow = action_lock = inputs = evidence = None
    publication_attempted = False
    result = {'schema': 'pocket4-beike-owned-postcondition-publication-v1', 'ok': False,
              'errors': [], 'original_action_outcome': 'unknown_retained',
              'original_action_result_rewritten': False, 'old_action_replayed': False,
              'Android_UI_actions': 0, 'instrumentation_calls': 0, 'App_installs': 0,
              'permission_grants': 0, 'Bili_actions': 0, 'automatic_retry': False,
              'business_success_verified': False, 'production_ready': False,
              'frozen_recorder_or_helper_modified': False}
    try:
        inputs = PinnedRoot(here, request['execution_pins'], deadline)
        evidence = PinnedRoot(core.FLOW, archive['pins'], deadline)
        own, qa, build, rec_manifest, _ = context
        recorder = own.load(RECORDER_ROOT / 'recorder.py', rec_manifest['files']['recorder.py']['sha256'], 'new_producer_frozen_recorder')
        fargs = types.SimpleNamespace(operation='owned-qa-postcondition-proof', adapter_manifest_sha256=core.RECORDER_MANIFEST,
            flow_dir=Path(core.FLOW), epoch_module=RECORDER_ROOT / 'references/framework_epoch.py',
            task_source=RECORDER_ROOT / 'references/task_scope_baseline.py', step=request['proof_step'],
            request={'new_producer_schema': PROOF_SCHEMA, 'request_sha256': sha(request_raw),
                     'producer_sha256': sha(self_raw), 'verifier_sha256': CORE_SHA},
            unknown_step=request['unknown_step'], observation_step=request['observation_step'],
            postcondition=request['postcondition'])
        flow = recorder.Flow(fargs)
        flow.begin(fargs, mutation=False)
        action_lock = recorder.lock_file(recorder.ACTION_LOCK)
        need(not (Path(core.FLOW) / 'reconciliations' / (request['unknown_step'] + '.json')).exists(),
             'NO_EXISTING_RECONCILIATION_MAY_BE_REPLACED')
        scope = core.document(evidence.read('scope.json'))
        launch = core.document(evidence.read('launch-scope.json'))
        need(scope == flow.scope, 'PINNED_SCOPE_DIFFERS_FROM_CURRENT_FLOW')
        core.fixed_scope(scope); core.fixed_launch(launch)
        need(evidence.read('baseline.json') == flow.source.actual_documents()[0] and
             evidence.read('baseline-qualification.json') == flow.source.actual_documents()[1],
             'ORIGINAL_FLOW_BASELINE_CHANGED')
        for role, filename in zip(('action', 'observation'), ROOT_PLAN_FILES):
            need(evidence.read(filename) == inputs.read(role + '.plan.json'), 'ACTUAL_ORIGINAL_PLAN_FILE_CHANGED')
        binding = flow.bind()
        session = own.Session(flow, recorder, qa, build, core.HELPER_UID)
        live_installed = session.installed()
        need(session.task() == launch, 'FRESH_EXACT_NATIVE_TASK_REQUIRED')
        live_foreground = session.foreground()
        action_files = evidence.step(request['unknown_step'])
        observation_files = evidence.step(request['observation_step'])
        shared = dict(adapter=own, qa=qa, transport=binding.transport_module, scope=scope, launch=launch,
                      build=build, held_helper_path=str(flow.source.HELPER_PATH), expected_binding=binding.record)
        action = core.validate_step(action_files, mutation=True, **shared)
        observed = core.validate_step(observation_files, mutation=False, **shared)
        offline = core.validate_pair(action, observed, request['postcondition'], qa=qa,
                                     now=datetime.datetime.now(datetime.timezone.utc))
        execution = {
            'action': execution_proof(core, inputs, 'action', action, request['unknown_step']),
            'observation': execution_proof(core, inputs, 'observation', observed, request['observation_step'])}
        need(execution['action']['job_id'] != execution['observation']['job_id'] and
             execution['action']['idempotency_key'] != execution['observation']['idempotency_key'],
             'INDEPENDENT_DURABLE_OBSERVATION_PROCESS_REQUIRED')
        need(live_installed == action['installed'] == observed['installed'] and
             live_foreground == observed['result']['foreground_before'] == observed['result']['foreground_after'],
             'CURRENT_INSTALLED_HELPER_AND_OBSERVED_FOREGROUND_CONTEXT')
        need(session.foreground() == live_foreground and session.task() == launch and
             session.installed() == live_installed, 'SECOND_FRESH_READONLY_IDENTITY_CHECK')
        need(flow.command_index == 6 and flow.action_attempted is False,
             'EXACT_SIX_RECORDED_READONLY_IDENTITY_COMMANDS')
        flow.guard(attempted=False)
        evidence.recheck(); inputs.recheck()
        need(host_pinned(here / 'request.json', args.request_sha256, 131072) == request_raw and
             host_pinned(Path(__file__).resolve(), args.source_sha256, 131072) == self_raw and
             host_pinned(here / 'owned_postcondition_core.py', CORE_SHA, 131072, CORE_BYTES) == core_raw,
             'PRODUCER_REQUEST_OR_SOURCE_CHANGED')
        own.own_source(core.HELPER_MANIFEST)
        flow.contract.verify(); flow.guard(attempted=False)
        flow.close()
        # No Main commands run after authority release. This is the same exact
        # typed guard; it does not recapture/adopt an epoch or reopen the binding.
        flow.source.runtime_and_app_guard(flow.current_guard)
        flow.epoch.require_unchanged(flow.activation['framework_epoch'], action_attempted=False)
        evidence.check(); inputs.check()
        held_baseline = probe.census()
        known_fds = (inputs.fd, evidence.fd, flow.lock, action_lock)
        need(len(set(known_fds)) == 4 and all(str(fd) not in frozen for fd in known_fds), 'FOUR_OWNED_FINAL_DESCRIPTORS')
        _fd_subset(probe, {k: v for k, v in held_baseline.items() if k not in {str(fd) for fd in known_fds}}, frozen)
        need(set(held_baseline) == set(frozen) | {str(fd) for fd in known_fds}, 'NO_UNACCOUNTED_DESCRIPTOR_AFTER_BINDING_CLOSE')
        need(boot.stable_library(probe.library_binding(library_fd, held_baseline[str(library_fd)])) ==
             boot.stable_library(library), 'EXACT_LIBRARY_RESOURCE_STILL_UNCHANGED')
        relative_step = 'steps/' + request['proof_step'] + '/'
        for filename, body in (('producer-source.py', self_raw), ('verifier-source.py', core_raw),
                               ('producer-request.json', request_raw)):
            recorder.write_new(flow.step / filename, body)
        for filename in sorted(request['execution_pins']):
            recorder.write_new(flow.step / ('external-' + filename), inputs.read(filename))
        fresh = {'schema': PROOF_SCHEMA, 'created_utc': recorder.now(), 'offline_proof': offline,
                 'producer_source_sha256': sha(self_raw), 'verifier_source_sha256': CORE_SHA,
                 'producer_is_original_Flow_reconcile': False, 'execution_evidence': execution,
                 'scope_sha256': sha(evidence.read('scope.json')), 'epoch_sha256': core.MAIN_EPOCH,
                 'runtime_epoch_sha256': core.RUNTIME_EPOCH, 'app_scope_sha256': core.APP_SCOPE,
                 'flow_dir': core.FLOW, 'unknown_step': request['unknown_step'],
                 'observation_step': request['observation_step'], 'current_native_task': launch,
                 'current_installed_helper': live_installed, 'current_foreground': live_foreground,
                 'current_held_R5_runtime_app_task_helper_rechecked': True,
                 'original_to_current_binding_comparisons': {
                     'action': action['binding_comparison'], 'observation': observed['binding_comparison']},
                 'held_binding_released': True, 'new_instrumentation_or_UI_actions': 0,
                 'library_resource': {'path': library['path'], 'bytes': library['bytes'], 'sha256': library['sha256'],
                                      'manual_close': False, 'retirement': 'producer process exit'},
                 'unknown_descriptors': [], 'flow_and_action_locks_held_until_process_exit': True,
                 'original_action_outcome': 'unknown_retained', 'old_action_replayed': False,
                 'business_success_verified': False, 'production_ready': False, 'automatic_retry': False,
                 'compatibility_envelope_is_only_new_decision_authority': True}
        recorder.write_new(flow.step / 'owned-qa-proof.json', fresh)
        recorder.write_new(flow.step / 'result.json', {'ok': True, 'action_attempted': False, 'outcome_unknown': False,
            'epoch_sha256': core.MAIN_EPOCH, 'ended_utc': recorder.now(), 'automatic_retry': False,
            'typed_postcondition_evidence_complete': True, 'business_success_verified': False,
            'production_ready': False, 'acceptance_requires_separate_compatibility_envelope': True})
        hashes = {rel: row['sha256'] for rel, row in archive['pins'].items()}
        # Only this new producer step is added; nothing in an old action or
        # observation is overwritten. Re-read all original pinned evidence last.
        for path in sorted(flow.step.iterdir()):
            need(path.is_file() and not path.is_symlink(), 'NEW_PROOF_FILE_SHAPE')
            raw = recorder.read_regular(path)
            need(len(raw) <= 2 * 1024 * 1024, 'NEW_PROOF_FILE_BOUND')
            hashes[relative_step + path.name] = sha(raw)
        evidence.recheck(); inputs.recheck()
        flow.source.runtime_and_app_guard(flow.current_guard)
        flow.epoch.require_unchanged(flow.activation['framework_epoch'], action_attempted=False)
        _fd_subset(probe, probe.census(), held_baseline)
        envelope = {'schema': 'pocket4-flow-explicit-reconciliation-v1', 'created_utc': recorder.now(),
                    'unknown_step': request['unknown_step'], 'observation_step': request['observation_step'],
                    'epoch_sha256': core.MAIN_EPOCH, 'scope_sha256': fresh['scope_sha256'],
                    'evidence_sha256': hashes, 'postcondition': request['postcondition'],
                    'new_owned_qa_producer': {'schema': PROOF_SCHEMA, 'proof_relative_path': relative_step + 'owned-qa-proof.json',
                        'source_sha256': sha(self_raw), 'verifier_sha256': CORE_SHA,
                        'original_Flow_reconcile_called': False},
                    'matched_owned_helper_node': offline['matched'],
                    'original_action_outcome': 'unknown_retained', 'allows_new_decisions_only': True,
                    'original_action_result_rewritten': False, 'old_action_replayed': False,
                    'business_success_verified': False, 'production_ready': False, 'automatic_retry': False}
        # Close only the two explicitly owned private directory FDs. Original
        # flow/global locks remain held until this process exits; no cleanup of
        # any unknown FD or the proven libffi-owned backing FD is attempted.
        inputs.close(); evidence.close()
        end = probe.census()
        final_expected = {**frozen, str(flow.lock): held_baseline[str(flow.lock)], str(action_lock): held_baseline[str(action_lock)]}
        _fd_subset(probe, end, final_expected)
        # Commit comes after all authority/directory release and the final FD
        # census. An I/O interruption at this final transaction is UNKNOWN and
        # must be reconciled from original durable evidence, never retried.
        publication_attempted = True
        envelope_raw = encoded(envelope)
        committed = commit_envelope(Path(core.FLOW) / 'reconciliations' / (request['unknown_step'] + '.json'),
                                    envelope_raw, request['stage_nonce'])
        need(host_pinned(committed['path'], committed['sha256'], 262144, committed['bytes']) == envelope_raw,
             'PUBLISHED_ENVELOPE_READBACK_CHANGED')
        result.update(ok=True, committed=committed, typed_proof_sha256=hashes[relative_step + 'owned-qa-proof.json'],
            action_step=request['unknown_step'], observation_step=request['observation_step'],
            readonly_commands=flow.command_index, flow_and_action_locks_held_until_process_exit=True,
            outcome_unknown=False, postcondition_verified_at_observation=True, next_decision_requires_fresh_original_helper_inspection=True)
    except BaseException as failure:
        publication_attempted |= bool(getattr(failure, 'publication_attempted', False))
        result['errors'].append({'type': type(failure).__name__, 'code': str(failure)[:512]})
        result['outcome_unknown'] = publication_attempted
        result['publication_attempted'] = publication_attempted
        if flow is not None:
            try:
                flow.close()
            except BaseException as secondary:
                result['errors'].append({'phase': 'held_binding_release', 'type': type(secondary).__name__})
        for owned in (inputs, evidence):
            if owned is not None:
                try:
                    owned.close()
                except BaseException as secondary:
                    result['errors'].append({'phase': 'owned_directory_release', 'type': type(secondary).__name__})
    # A caller must require this original stdout AND durable successful process
    # termination. No new Android decision may be inferred from a partial file.
    print(json.dumps(result, ensure_ascii=True, sort_keys=True), flush=True)
    return 0 if result['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--publish-once', action='store_true')
    mode.add_argument('--verify-host-only', action='store_true')
    parser.add_argument('--source-sha256')
    parser.add_argument('--request-sha256')
    args = parser.parse_args()
    if not args.publish_once and not args.verify_host_only:
        print(json.dumps({'state': 'PLAN_ONLY', 'new_producer_schema': PROOF_SCHEMA,
            'actual_action_and_later_inspect_required': True, 'supports_owned_qa_case': False,
            'Main_commands_executed': 0, 'reconciliation_published': False}))
        return 0
    need(all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value)
             for value in (args.source_sha256, args.request_sha256)), 'EXTERNAL_SOURCE_AND_REQUEST_PINS_REQUIRED')
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
