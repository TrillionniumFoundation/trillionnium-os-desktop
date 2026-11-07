#!/usr/bin/env python3
"""Single reviewed normal PM coexistence install; no UI action or replay."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

sys.dont_write_bytecode = True
ROOT = '/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1'
FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
PACKAGE = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2'
BASE = {'path': '/home/alex/work/pocket4-beike-owned-cleanup-20261106-r1/cleanup_owned_task_once.py', 'bytes': 22233, 'sha256': '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf'}
INSTALLER = {'path': '/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1/install_search_helper_full_scope.py', 'bytes': 24933, 'sha256': 'a15d1322c1bbf6001d0870307243bf4509e00111484b042038ad583871f101c6'}
ADAPTER = {'path': '/home/alex/work/pocket4-successor-qa-build-source-362bdb6f45eeb344b3584aa998cb03e1/qa_adapter.py', 'bytes': 31253, 'sha256': '15559f9f1cd59bb1e9540251d4270a4f37a9e229bf86d9ec1e2f9b65d625692f'}
HELPER_MANIFEST = {'path': '/home/alex/work/pocket4-successor-qa-build-source-362bdb6f45eeb344b3584aa998cb03e1/SOURCE_PINS.json', 'bytes': 3259, 'sha256': '0bd7c10043f46063fdbf46e19a48e40430c02f3373d697ad7a44af8ad64b8489'}
PARENT_SCOPE = {'path': '/home/alex/work/pocket4-successor-native-install-20261106-zbj-s43-full48-r4-01/app-scope-after.private.json', 'bytes': 59259, 'sha256': '9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a'}
BUILD_JOB = '1a1b339c056-fc05-8136'
BUILD_RESULT = {'path': '/home/alex/work/pocket4-successor-qa-build-362bdb6f45eeb344b3584aa998cb03e1/build-result.json', 'bytes': 39246, 'sha256': '0d6a4e19388358032c9ba4ad4f034e714470d7d194c36599226bd0ba6745330f'}
BUILD_FILE_VERSION = '66306:35127954:39246:1794008288630404826:1794008288630404826'
APK = {'bytes': 41104, 'path': '/home/alex/work/pocket4-successor-qa-build-362bdb6f45eeb344b3584aa998cb03e1/owned-bili-qa.apk', 'sha256': '968c23aac929130a76dfa49d796fbe5264c073f805b7f048b68737e427d96372'}
SIGNER_SHA = 'f5eb5f24311fb19187b37219db272837d2d68632d9e8b855a89b2b6518904143'
BUILD_STDOUT = {'path': '/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1/build.stdout.original.json', 'bytes': 263, 'sha256': '608d7dec90de0bba10dd8e5e7daf3999a22f984dcd289edb18e7547e4babbc57'}
BUILD_TERMINAL = {'path': '/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1/build.terminal.original.json', 'bytes': 729, 'sha256': '121ac5733395c1e66d280ff8cb69df38fe7a163f07ff6c99df18aee73ac4ae7b'}
RECORDER_ROOT = '/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder'
NO_ACTION_CORE = {'path': '/home/alex/work/pocket4-beike-no-action-runtime-20261106-r1/no_action_core.py', 'bytes': 38241, 'sha256': '92cbde977c018203f8206b47a178774bb9c408cfb9c4559be0a574751e01debd'}
STAGE_B_JOB = '1a1b33fbae4-fc05-8172'
STAGE_B_SOURCE = {'bytes': 77716, 'path': '/home/alex/work/pocket4-beike-no-action-commit-20261106-r1/commit_stage_b_once.py', 'sha256': 'f36e146221d43359690b2d73969244dce337a9ac36da038d2bae506a2de981b7'}
STAGE_B_REQUEST = {'bytes': 2531, 'path': '/home/alex/work/pocket4-beike-no-action-commit-20261106-r1/request.json', 'sha256': 'a2e6b26f52fc0874a5dddac3435df326124558765236e7a1d19d85c3584c6449'}
STAGE_B_STDOUT = {'path': '/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1/stage-b.stdout.original.jsonl', 'bytes': 19805, 'sha256': '3a046f40503768c5e0411daee65c5b233e6245b32c0098c8fd4493a8915a9cbf'}
STAGE_B_TERMINAL = {'path': '/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1/stage-b.terminal.original.json', 'bytes': 733, 'sha256': '29f4241e351442586e8080fa0d252c883075df864934add9657216cecde72ece'}
B_ENVELOPE = {'bytes': 29722, 'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/reconciliations/search-click-after-partial-commit-01.json', 'sha256': '306475d1ac5f9d03626c325653e9c158b3c6b06dc99baccabcc45808d53e1da4'}
B_PROOF = {'bytes': 19528, 'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/no-action-commit-01/owned-qa-no-action-proof.json', 'sha256': '120b57ddd5dcf5d5fd83b04452af4d04a05ff8a53a0cad2db297e9bfec8285ea'}
B_STEP_RESULT = {'bytes': 1336, 'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/no-action-commit-01/result.json', 'sha256': '45c454a877af217a6053056acc2b540aa72619ef2b4a7823e0930f788fdd1bed'}
B_JOINT = {'bytes': 18719, 'path': '/home/alex/work/pocket4-beike-no-action-commit-20261106-r1/owned-partial-reconciliation-joint.json', 'sha256': '72097e70113a7b753a212c84bf33152cca319547a90d3eb4cad5b2b24a429ff4'}
ACTUAL_STAGE_B_PUBLICATION = {'Main_commands': 0, 'Main_locks_or_guards': 0, 'files': {'commit_stage_b_once.py': {'bytes': 77716, 'sha256': 'f36e146221d43359690b2d73969244dce337a9ac36da038d2bae506a2de981b7'}, 'request.json': {'bytes': 2531, 'sha256': 'a2e6b26f52fc0874a5dddac3435df326124558765236e7a1d19d85c3584c6449'}, 'stage-a.stdout.original.jsonl': {'bytes': 15528, 'sha256': '099a24caac0527f24a97417419cea432b57663cde227d7c844204b2896b08561'}, 'stage-a.terminal.original.json': {'bytes': 733, 'sha256': '8ca15446afb6c5a4623632071495abafb57c007459257fc463bac3001529abbe'}}, 'mode': 'single-no-action-commit-owner-not-yet-invoked', 'namespace_entries': 0, 'private_bundle_copied': False, 'reconciliation_published': False, 'root': '/home/alex/work/pocket4-beike-no-action-commit-20261106-r1', 'schema': 'pocket4-stage-b-no-action-commit-stage-v1', 'whole_process_fd_identities_unchanged': True}
STAT_FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_rdev', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
FIXED_REQUEST = {'schema': 'pocket4-fixed-normal-search-helper-coexist-install-request-v1', 'flow': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe', 'step': 'install-search-helper-r2-01', 'state_nonce': '6f1b17628528422dad623e5305c1f776', 'package': 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2', 'installer': {'path': '/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1/install_search_helper_full_scope.py', 'bytes': 24933, 'sha256': 'a15d1322c1bbf6001d0870307243bf4509e00111484b042038ad583871f101c6'}, 'helper_source_manifest': {'path': '/home/alex/work/pocket4-successor-qa-build-source-362bdb6f45eeb344b3584aa998cb03e1/SOURCE_PINS.json', 'bytes': 3259, 'sha256': '0bd7c10043f46063fdbf46e19a48e40430c02f3373d697ad7a44af8ad64b8489'}, 'build_result': {'path': '/home/alex/work/pocket4-successor-qa-build-362bdb6f45eeb344b3584aa998cb03e1/build-result.json', 'bytes': 39246, 'sha256': '0d6a4e19388358032c9ba4ad4f034e714470d7d194c36599226bd0ba6745330f'}, 'build_job': '1a1b339c056-fc05-8136', 'build_APK': {'bytes': 41104, 'path': '/home/alex/work/pocket4-successor-qa-build-362bdb6f45eeb344b3584aa998cb03e1/owned-bili-qa.apk', 'sha256': '968c23aac929130a76dfa49d796fbe5264c073f805b7f048b68737e427d96372'}, 'signer_certificate_sha256': 'f5eb5f24311fb19187b37219db272837d2d68632d9e8b855a89b2b6518904143', 'completed_no_action_job': '1a1b33fbae4-fc05-8172', 'completed_no_action_envelope': {'bytes': 29722, 'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/reconciliations/search-click-after-partial-commit-01.json', 'sha256': '306475d1ac5f9d03626c325653e9c158b3c6b06dc99baccabcc45808d53e1da4'}, 'parent_app_scope': {'path': '/home/alex/work/pocket4-successor-native-install-20261106-zbj-s43-full48-r4-01/app-scope-after.private.json', 'bytes': 59259, 'sha256': '9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a'}, 'replacement': False, 'old_helper_retained': True, 'UI_actions': 0, 'permission_grants': 0, 'automatic_retry': False, 'new_UID_must_come_from_actual_PM': True, 'new_49_scope_must_come_from_actual_observer': True, 'production_ready': False}
SELF = REQUEST = None


def need(value, reason):
    if not value:
        raise RuntimeError(reason)



def sha(raw):
    return hashlib.sha256(raw).hexdigest()



def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')



def load_base():
    """Bootstrap only the already deployed exact root-owned utility module."""
    path = Path(BASE['path']); fds = []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); fds.append(parent)
        for name in path.parts[1:-1]:
            parent = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            fds.append(parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent); fds.append(fd)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1 and
             not before.st_mode & 0o022 and before.st_size == BASE['bytes'], 'EXACT_ROOT_UTILITY_FILE')
        raw = bytearray()
        while len(raw) <= before.st_size:
            part = os.read(fd, before.st_size + 1 - len(raw))
            if not part:
                break
            raw.extend(part)
        after, named = os.fstat(fd), os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        need(len(raw) == BASE['bytes'] and sha(raw) == BASE['sha256'] and
             all(getattr(before, key) == getattr(after, key) == getattr(named, key) for key in keys), 'UTILITY_SOURCE_CHANGED')
    finally:
        for fd in reversed(fds):
            os.close(fd)
    module = types.ModuleType('unchanged_cleanup_utilities_only'); module.__file__ = str(path)
    exec(compile(bytes(raw), str(path), 'exec'), module.__dict__)
    return module



def write_once(base, path, raw):
    path = Path(path)
    need(path.parent.as_posix() == ROOT and path.name not in ('', '.', '..'), 'FIXED_OWNED_OUTPUT_DIRECTORY')
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(directory)
        need(before.st_uid == 0 and stat.S_IMODE(before.st_mode) == 0o700 and path.parent.resolve() == path.parent,
             'ROOT_PRIVATE_FIXED_OUTPUT_PARENT')
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=directory)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view); need(count > 0, 'WRITE_PROGRESS'); view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
        named = os.stat(path.parent, follow_symlinks=False)
        need(all(getattr(before, key) == getattr(named, key) for key in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')),
             'OUTPUT_PARENT_REPLACED')
    finally:
        os.close(directory)
    need(base.read(path)[0] == raw, 'EXACT_IMMUTABLE_OUTPUT_READBACK')
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}



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
    value = partial.document(raw)
    need(value.get('schema') == CHILD_SCHEMA and value.get('ok') is True and value.get('errors') == [] and
         value.get('source') == SELF and value.get('request') == REQUEST and value.get('flow') == FLOW and
         value.get('task') == TASK and value.get('step') == STEP and value.get('operation') == OPERATION and
         all(value.get(key) is True for key in ('held_Main_authority_closed',
             'original_foreground_predicate_preserved', 'all_historical_originals_unchanged',
             'requires_parent_normal_pidfd_exit_and_durable_terminal', 'reconciliation_published',
             'compatibility_envelope_written', 'publication_attempted',
             'next_decision_requires_fresh_original_helper_inspection')) and
         value.get('original_case_ok') is False and value.get('original_case_outcome_unknown') is True and
         all(value.get(key) is False for key in ('original_results_rewritten', 'old_action_replayed',
             'Flow_reconcile_called', 'current_action_authority', 'business_success_verified',
             'production_ready', 'automatic_retry', 'manual_library_close', 'private_UI_raw_or_nodes_in_stdout',
             'publication_outcome_unknown', 'frozen_consumer_checks_controller_terminal')) and
         all(type(value.get(key)) is int and value[key] == 0 for key in ('UI_actions',
             'instrumentation_calls', 'installs', 'permission_changes', 'lifecycle_or_activation_actions',
             'unknown_descriptors_closed')), 'COMPLETE_STAGE_B_COMMIT_AND_NORMAL_RETIREMENT_JOINTLY_REQUIRED')
    core = base.load(base.CORE, 'unchanged_scope_and_hash_contract')
    proof_pin = value['typed_proof']; proof_raw = base.pinned(proof_pin); proof = partial.document(proof_raw)
    need(proof_pin['path'] == FLOW + '/steps/' + STEP + '/owned-qa-no-action-proof.json' and
         proof_raw == canonical(proof) + b'\n' and proof.get('schema') == PROOF_SCHEMA and
         proof.get('source') == SELF and proof.get('request') == REQUEST and proof.get('flow') == FLOW and
         proof.get('step') == STEP and proof.get('producer_operation') == OPERATION and
         proof.get('runtime_commands') == value['runtime_commands'] and
         proof.get('completed_stage_A') == value['completed_stage_A'] and
         proof['completed_stage_A']['job_id'] == STAGE_A_JOB and
         proof['completed_stage_A']['runtime_candidate'] == STAGE_A_CANDIDATE and
         proof.get('publication_attempted_at_file_creation') is False and
         proof.get('this_file_does_not_claim_stage_B_process_exit_or_controller_terminal') is True and
         proof.get('original_case_ok') is False and proof.get('original_case_outcome_unknown') is True and
         proof.get('current_action_authority') is False and proof.get('private_UI_raw_or_nodes_included') is False,
         'EXACT_NEW_TYPED_PROOF_AND_ALREADY_COMPLETED_STAGE_A')
    committed = value['committed']
    envelope = committed_envelope(base, partial, core, committed, proof_pin)
    need(value['envelope_evidence_count'] == len(envelope['evidence_sha256']), 'SAME_COMPLETE_FLOW_EVIDENCE_SET')
    old_raw, _ = base.read(Path(FLOW) / 'steps' / CASE_STEP / 'result.json')
    old = partial.document(old_raw)
    need(old.get('ok') is False and old.get('outcome_unknown') is True and
         sha(old_raw) == envelope['evidence_sha256']['steps/' + CASE_STEP + '/result.json'],
         'ORIGINAL_PARTIAL_CASE_STILL_FAILED_UNKNOWN')
    step_result_raw, _ = base.read(Path(FLOW) / 'steps' / STEP / 'result.json')
    step_result = partial.document(step_result_raw)
    need(step_result.get('schema') == 'pocket4-owned-qa-no-action-commit-step-result-v1' and
         step_result.get('ok') is True and step_result.get('errors') == [] and
         step_result.get('action_attempted') is False and step_result.get('outcome_unknown') is False and
         step_result.get('publication_attempted') is True and step_result.get('publication_outcome_unknown') is False and
         step_result.get('compatibility_envelope') == committed and step_result.get('typed_proof') == proof_pin and
         step_result.get('reconciliation_published') is True and step_result.get('current_action_authority') is False and
         step_result.get('original_case_ok') is False and step_result.get('original_case_outcome_unknown') is True,
         'ACTUAL_POSTCOMMIT_STEP_RESULT_REQUIRED')
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
