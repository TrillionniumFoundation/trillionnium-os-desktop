#!/usr/bin/env python3
"""Local, one-time sealing only. Does not call a target, Git or any executor."""
import ast
import base64
import difflib
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
DEST = HERE / 'candidate-r1'
ROOT = '/home/alex/work/pocket4-beike-partial-case-proof-20261106-r1'
REMOTE_HELPER = '/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03'
REMOTE_RECORDER = '/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder'


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def exact(relative, length, digest):
    raw = (PROJECT / relative).read_bytes()
    need(len(raw) == length and sha(raw) == digest, 'ACTUAL_LOCAL_ORIGINAL_PIN:' + relative)
    return raw


def pin(path, raw):
    return {'path': path, 'bytes': len(raw), 'sha256': sha(raw)}


def write_once(name, raw):
    path = DEST / name
    need('/' not in name and path.parent == DEST, 'FLAT_NEW_CANDIDATE_PATH')
    if path.exists():
        need(path.read_bytes() == raw, 'EXISTING_CANDIDATE_BYTES_DIFFER_NO_OVERWRITE:' + name)
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:]); need(count > 0, 'LOCAL_WRITE_PROGRESS'); offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    need(path.read_bytes() == raw, 'LOCAL_EXACT_READBACK')


def replace_assignment(source, key, value):
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, ast.Assign) and
             any(isinstance(target, ast.Name) and target.id == key for target in node.targets)]
    need(len(nodes) == 1, 'ONE_SOURCE_ASSIGNMENT:' + key)
    node = nodes[0]; lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [key + ' = ' + value + '\n']
    return ''.join(lines)


def main():
    DEST.mkdir(mode=0o700, exist_ok=True)
    old_reader = exact('successor_qa/case_failure_reader_r1/read_failed_case.py', 44768,
                      '0e0716b7237199f2fe377ba9f067c2d0327d54a8efb5f40813b1f3e5ebc0021d')
    core = (HERE / 'partial_case_core.py').read_bytes(); compile(core, 'partial_case_core.py', 'exec')
    stdout = exact('successor_qa/inspect_after_search_rejection_r1/actual/stdout.original.json', 13961,
                   '50890b7a1c8a591f493a1af26606da2279f5b3c0cc1e7a893b19b77d200c0401')
    terminal = exact('successor_qa/inspect_after_search_rejection_r1/actual/status-01.original.txt', 733,
                     'b314bd6a3cc8304d5d00038ece8f811e88bacadf0df09798c87cb42e613a5ede')
    actual = json.loads(stdout); child = json.loads(actual['child_stdout_original'])
    archived_build = base64.b64decode(json.loads((PROJECT /
        'successor_qa/actual/helper-build-r1/result.binary-read.raw.json').read_bytes())['data_base64'], validate=True)
    need(len(archived_build) == 33691 and sha(archived_build) ==
         'c0dd8117cdb7fa8b551e2a59b466c91d48ee2f2d9a98908f69b3d3fb8807bf3d', 'ACTUAL_BUILD_RECEIPT_BYTES')
    build_info = json.loads((PROJECT / 'successor_qa/actual/helper-build-r1/result.file-info.raw.json').read_bytes())
    need(build_info['metadata']['uid'] == 1000 and build_info['metadata']['gid'] == 1000 and
         build_info['mode'] == 0o600 and build_info['size'] == 33691 and
         build_info['sha256'] == sha(archived_build), 'REAL_UID1000_BUILD_ORIGIN_NOT_RELABELED_ROOT')
    helper_manifest = exact('successor_qa/reconstructed/source-generation-r2/helper/SOURCE_PINS.json', 2431,
        'dfb9b6a483f1069847433152b9b2e8b0f1b2cdd571a1dbde3068fc9393ad62c4')
    recorder_manifest = exact('successor_qa/reconstructed/source-generation-r2/recorder/source-manifest.json', 1759,
        '646f6e4c7d931bf005ada01a84202a891c95e99e93bbde7a561f3307527008a4')
    task = exact('successor_qa/reconstructed/source-generation-r2/recorder/references/task_scope_baseline.py', 17281,
        'a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528')
    inputs = {'schema': 'pocket4-task878-partial-case-fixed-host-inputs-v1', 'root': ROOT,
        'new_core': pin(ROOT + '/partial_case_core.py', core),
        'frozen_failed_reader': pin(ROOT + '/read_failed_case.frozen.py', old_reader),
        'task_source': pin(REMOTE_RECORDER + '/references/task_scope_baseline.py', task),
        'source_manifests': {'helper': pin(REMOTE_HELPER + '/SOURCE_PINS.json', helper_manifest),
                             'recorder': pin(REMOTE_RECORDER + '/source-manifest.json', recorder_manifest)},
        'archived_build_receipt': pin(ROOT + '/actual-build-result.original.json', archived_build),
        'historical_build_receipt': pin(build_info['path'], archived_build),
        'historical_build_receipt_owner_observed': {'uid': 1000, 'gid': 1000, 'mode': 0o600,
             'file_version': build_info['version'], 'not_current_host_revalidation': True},
        'failed_private_bundle': {'path': '/home/alex/work/pocket4-beike-case-failure-evidence-20261106-r1/bundle.private.json',
            'bytes': 2155722, 'sha256': '6e5288e45697a130fa404e7038905521c2f5f912ad24fd3bdff361153d3a7d90'},
        'observation': {'stdout': pin(ROOT + '/observation.stdout.original.json', stdout),
            'terminal': pin(ROOT + '/observation.terminal.original.json', terminal),
            'joint': actual['joint_artifact'], 'request': actual['request'],
            'result': actual['original_result'], 'plan': child['input_artifact'],
            'child_stdout_sha256': actual['child_stdout_sha256'],
            'adapter_stdout_sha256': child['original_stdout_sha256']}}
    input_raw = canonical(inputs) + b'\n'
    template = (HERE / 'verify_partial_case_host.py.in').read_text()
    need(template.count('__INPUTS_PIN__') == 1, 'ONE_FIXED_HOST_INPUT_PIN_SLOT')
    worker = template.replace('__INPUTS_PIN__', repr(pin(ROOT + '/inputs.json', input_raw))).encode()
    compile(worker, ROOT + '/verify_partial_case_host.py', 'exec')
    bodies = {'partial_case_core.py': core, 'read_failed_case.frozen.py': old_reader,
              'actual-build-result.original.json': archived_build,
              'observation.stdout.original.json': stdout, 'observation.terminal.original.json': terminal,
              'inputs.json': input_raw, 'verify_partial_case_host.py': worker}
    members = {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in bodies.items()}
    stage_schema = 'pocket4-fixed-partial-case-host-stage-payload-v1'
    payload = canonical({'schema': stage_schema, 'root': ROOT, 'files': {
        name: {**members[name], 'base64': base64.b64encode(raw).decode('ascii')}
        for name, raw in bodies.items()}}) + b'\n'
    need(len(payload) <= 524288, 'EXISTING_PROVEN_STAGE_INPUT_BOUND')
    original_stage = (PROJECT / 'successor_qa/reusable_owned_ui_r1/stage_first_inspect_once.py').read_text()
    stage = original_stage
    stage = replace_assignment(stage, 'ROOT', 'Path(' + repr(ROOT) + ')')
    stage = replace_assignment(stage, 'PINS', repr(members))
    stage = replace_assignment(stage, 'ENTRY_SHA', repr(sha(worker)))
    stage = replace_assignment(stage, 'PAYLOAD_SHA', repr(sha(payload)))
    replacements = {
      'Stage fixed reusable owned QA source and one readonly inspection request.':
          'Stage one fixed host-only partial-case verifier and exact historical inputs.',
      'pocket4-fixed-owned-ui-stage-payload-v1': stage_schema,
      "ROOT.name == 'pocket4-beike-owned-ui-reusable-20261106-r1'":
          "ROOT.name == 'pocket4-beike-partial-case-proof-20261106-r1'",
      'pocket4-fixed-owned-ui-stage-v1': 'pocket4-partial-case-historical-host-stage-v1',
      'readonly-inspect-not-yet-invoked': 'host-only-verification-not-yet-invoked',
      "entry = ROOT / 'owned_ui_request_once.py'": "entry = ROOT / 'verify_partial_case_host.py'",
      "sys.argv = [str(entry), '--execute-request', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['owned_ui_request_once.py']['bytes']), '--request-sha256', '92bd97c8f6b868168fc98520b4e4908103843bfdb689e7f80c06f51002abab73', '--request-bytes', '400']":
          "sys.argv = [str(entry), '--verify-host-once', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['verify_partial_case_host.py']['bytes'])]",
      "exec(compile(bodies['owned_ui_request_once.py'], str(entry), 'exec'),":
          "exec(compile(bodies['verify_partial_case_host.py'], str(entry), 'exec'),"}
    for old, new in replacements.items():
        need(stage.count(old) == 1, 'ONE_REVIEWABLE_STAGE_REPLACEMENT:' + old[:50])
        stage = stage.replace(old, new)
    compile(stage, 'stage_verify_host_once.py', 'exec')
    stage_raw = stage.encode()
    request = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', stage,
                 '--payload-sha256', sha(payload)], 'stdin': payload.decode('ascii'),
        'cwd': '/home/alex/work', 'timeout_seconds': 300, 'cpu_quota_percent': 100,
        'memory_max_bytes': 536870912, 'nice': 10,
        'idempotency_key': 'pocket4-beike-task878-partial-case-host-verifier-r1-20261106'}
    request_raw = canonical(request) + b'\n'
    for name, raw in bodies.items():
        write_once(name, raw)
    write_once('stage_verify_host_once.py', stage_raw)
    write_once('stage-input.json', payload)
    write_once('process-request.review-only.json', request_raw)
    diff = ''.join(difflib.unified_diff(original_stage.splitlines(keepends=True), stage.splitlines(keepends=True),
        fromfile='actual-reusable-inspect-stage', tofile='new-host-only-stage')).encode()
    write_once('stage-against-actual-inspect.diff', diff)
    metadata = {'schema': 'pocket4-task878-partial-case-host-source-pins-v1', 'target_root': ROOT,
        'staged_files': members, 'stager': {'bytes': len(stage_raw), 'sha256': sha(stage_raw)},
        'stage_input': {'bytes': len(payload), 'sha256': sha(payload)},
        'exact_process_request': {'bytes': len(request_raw), 'sha256': sha(request_raw)},
        'source_stage_difference': {'bytes': len(diff), 'sha256': sha(diff)},
        'actual_old_stager': {'path': 'successor_qa/reusable_owned_ui_r1/stage_first_inspect_once.py',
                              'bytes': len(original_stage.encode()), 'sha256': sha(original_stage.encode())},
        'all_original_source_and_UI_protocol_files_modified': False,
        'private_UI_content_in_source_packet': False, 'device_submitted_by_preparer': False,
        'host_full_actual_bundle_verification': 'NOT_RUN', 'runtime_candidate': 'NOT_RUN',
        'compatibility_publication': 'NOT_IMPLEMENTED_BY_THIS_HOST_PACKET',
        'production_ready': False}
    write_once('SOURCE_PINS.json', canonical(metadata) + b'\n')
    print(json.dumps(metadata, sort_keys=True, ensure_ascii=True))


if __name__ == '__main__':
    main()
