#!/usr/bin/env python3
"""Host-only reader of two exact existing Beike evidence steps. No Main API.

Full original bytes go only into a new root-private bundle. Neither that bundle
nor stdout's visible-node summary is approved for Git. No command is executed,
no guard is loaded, and no original flow, plan or evidence file is modified.
"""
import argparse
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

FLOW = Path('/home/alex/work/pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb')
OUTPUT = Path('/home/alex/work/pocket4-beike-postcondition-evidence-20261106-r1')
QA = Path('/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03/qa_contract.py')
QA_BYTES = 52359
QA_SHA = 'bfe1e781e254033ab5c5b7616a928d309998bde4cbc243bd542c3eb4805eda6e'
STEPS = {
    'close-entry-popup-01': ('525d5f2be2309ec8716b39404a0eb12c', '8330558e0ce5e24f859d3ea445c0f5d2',
                             'dac3bddf3bdeb3f41093e67fa436fb9d', '7fe44de4e94b12758d9f104a45320038'),
    'inspect-after-close-02': ('24de842af6c4f70ea621ced38836aa82', '636d352c1a3bd92424c394daf0799107',
                             '35380b5c9d2a02ca0bce1d3f67b1ff60')}
ROOT_FILES = ('scope.json', 'launch-scope.json', 'baseline.json', 'baseline-qualification.json',
              'qa-close-entry-popup-01.plan.json', 'qa-inspect-after-close-02.plan.json')
INSPECT_NONCE = '636d352c1a3bd92424c394daf0799107'
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
PER_FILE = 2 * 1024 * 1024
TOTAL = 32 * 1024 * 1024


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def meta(row):
    return tuple(getattr(row, key) for key in FIELDS)


def census():
    result = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd = int(name); row = os.fstat(fd)
            result[name] = {'link': os.readlink('/proc/self/fd/' + name), 'device': row.st_dev,
                            'inode': row.st_ino, 'mode': row.st_mode, 'uid': row.st_uid, 'gid': row.st_gid}
        except OSError as failure:
            if failure.errno not in (errno.EBADF, errno.ENOENT):
                raise
    return result


def private_dir(path, *, parent=None):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        row = os.fstat(fd)
        need(stat.S_ISDIR(row.st_mode) and row.st_uid == 0 and not row.st_mode & 0o077,
             'EXACT_ROOT_PRIVATE_DIRECTORY')
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_at(parent, name, deadline, maximum=PER_FILE):
    need('/' not in name and name not in ('', '.', '..') and '\0' not in name, 'FIXED_FILE_BASENAME')
    need(time.monotonic() < deadline, 'TOTAL_HOST_READ_DEADLINE')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_uid == 0 and first.st_nlink == 1 and
             not first.st_mode & 0o022 and 0 <= first.st_size <= maximum, 'ROOT_BOUNDED_SINGLE_REGULAR_FILE')
        body = bytearray()
        while len(body) <= first.st_size:
            need(time.monotonic() < deadline, 'TOTAL_HOST_READ_DEADLINE')
            part = os.read(fd, min(65536, first.st_size + 1 - len(body)))
            if not part:
                break
            body.extend(part)
        need(len(body) == first.st_size and meta(first) == meta(os.fstat(fd)) ==
             meta(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'FILE_CHANGED_DURING_READ')
        return bytes(body), meta(first)
    finally:
        os.close(fd)


def valid_names(selected, names):
    need(3 <= len(names) <= 128 and {'intent.json', 'result.json', 'held-main-binding.json'} <= set(names),
         'COMPLETE_BOUNDED_ORIGINAL_STEP')
    phase_names = {nonce + suffix for nonce in STEPS[selected] for suffix in ('.request.json', '.assessment.json')}
    need(phase_names <= set(names), 'ALL_ORIGINAL_NONCE_REQUESTS_AND_ASSESSMENTS')
    fixed = {'intent.json', 'result.json', 'held-main-binding.json'} | phase_names
    commands = {}; transports = {}
    for name in names:
        if name in fixed:
            continue
        match = re.fullmatch(r'command-([0-9]{3})\.(intent\.json|result\.json|stdout|stderr)', name)
        if match:
            commands.setdefault(int(match[1]), set()).add(match[2]); continue
        match = re.fullmatch(r'transport-([0-9]{3})\.(intent|command-result|verified-result)\.json', name)
        need(match is not None, 'UNEXPECTED_STEP_FILE_NOT_READ')
        transports.setdefault(int(match[1]), set()).add(match[2])
    need(commands and sorted(commands) == list(range(1, len(commands) + 1)) and
         all(v == {'intent.json', 'result.json', 'stdout', 'stderr'} for v in commands.values()),
         'COMPLETE_SEQUENTIAL_RAW_COMMAND_FILES')
    need(transports and sorted(transports) == list(range(1, len(transports) + 1)) and
         all(v == {'intent', 'command-result', 'verified-result'} for v in transports.values()),
         'COMPLETE_SEQUENTIAL_TRANSPORT_FILES')


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:]); need(count > 0, 'OWNED_WRITE_PROGRESS'); offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
        actual, _ = read_at(parent, path.name, time.monotonic() + 20, len(raw))
        need(actual == raw, 'OWNED_OUTPUT_READBACK')
    finally:
        os.close(parent)
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def collect(source_sha):
    need(os.getuid() == os.geteuid() == 0, 'ACTUAL_ROOT_REQUIRED')
    need(FLOW.resolve() == FLOW and QA.resolve() == QA and OUTPUT.parent.resolve() == OUTPUT.parent,
         'EXACT_CANONICAL_EXISTING_PATHS')
    os.umask(0o077)
    before = census(); deadline = time.monotonic() + 90
    files = {}; identities = {}; file_sets = {}; total = 0
    root = private_dir(FLOW)
    original_root = os.fstat(root)
    try:
        def retain(relative, parent, leaf):
            nonlocal total
            body, identity = read_at(parent, leaf, deadline)
            total += len(body); need(total <= TOTAL, 'TOTAL_ORIGINAL_EVIDENCE_BYTE_BOUND')
            files[relative] = body; identities[relative] = identity
        for name in ROOT_FILES:
            retain(name, root, name)
        steps = private_dir('steps', parent=root)
        try:
            for selected in STEPS:
                fd = private_dir(selected, parent=steps)
                try:
                    names = sorted(os.listdir(fd)); valid_names(selected, names); file_sets[selected] = names
                    for name in names:
                        retain('steps/' + selected + '/' + name, fd, name)
                    need(sorted(os.listdir(fd)) == names, 'STEP_FILE_SET_CHANGED')
                    for name in names:
                        body, identity = read_at(fd, name, deadline)
                        key = 'steps/' + selected + '/' + name
                        need(body == files[key] and identity == identities[key], 'STEP_CHANGED_AFTER_COLLECTION')
                finally:
                    os.close(fd)
        finally:
            os.close(steps)
        for name in ROOT_FILES:
            body, identity = read_at(root, name, deadline)
            need(body == files[name] and identity == identities[name], 'FLOW_METADATA_OR_PLAN_CHANGED')
        current = FLOW.lstat()
        need((current.st_dev, current.st_ino, current.st_uid, current.st_mode) ==
             (original_root.st_dev, original_root.st_ino, original_root.st_uid, original_root.st_mode), 'FLOW_ROOT_REPLACED')
    finally:
        os.close(root)
    qa_parent = os.open(QA.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        source, _ = read_at(qa_parent, QA.name, deadline, QA_BYTES)
    finally:
        os.close(qa_parent)
    need(len(source) == QA_BYTES and sha(source) == QA_SHA, 'EXACT_OFFLINE_QA_PARSER_SOURCE')
    qa = types.ModuleType('actual_frozen_offline_qa_parser'); qa.__file__ = str(QA)
    exec(compile(source, str(QA), 'exec'), qa.__dict__)
    prefix = 'steps/inspect-after-close-02/'
    request = json.loads(files[prefix + INSPECT_NONCE + '.request.json'])
    assessment = json.loads(files[prefix + INSPECT_NONCE + '.assessment.json'])
    need(request.get('nonce') == INSPECT_NONCE and request.get('op') == 'inspect', 'FIXED_POST_INSPECTION_NONCE')
    candidates = [key for key, body in files.items() if key.startswith(prefix + 'command-') and
                  key.endswith('.result.json') and sha(body) == assessment.get('recorder_command_result_sha256')]
    need(len(candidates) == 1, 'ONE_ACTUAL_POST_INSPECT_COMMAND_RESULT')
    selected = candidates[0]; stem = selected[:-len('.result.json')]
    command = json.loads(files[selected]); stdout = files[stem + '.stdout']; stderr = files[stem + '.stderr']
    need(command.get('returncode') == 0 and command.get('owned_command_joined') is True and
         command.get('spawned') is True and command.get('timed_out') is False and command.get('errors') == [] and
         command.get('error') is None and command.get('action_attempted') is False and
         command.get('stdout_sha256') == sha(stdout) and command.get('stderr_sha256') == sha(stderr),
         'ACTUAL_JOINED_POST_INSPECT_RAW_COMMAND')
    recomputed = qa.parse_completed(stdout, stderr, command['returncode'], request, 10157)
    recomputed['recorder_command_result_sha256'] = sha(files[selected])
    recomputed['held_transport_returned_after_post_guard'] = True
    need(recomputed == assessment, 'POST_INSPECT_ASSESSMENT_MUST_MATCH_RAW')
    tree = qa.inspect_record(assessment['helper']['inspection'])
    summary = []
    for node in tree['nodes']:
        if (node.get('package') != 'com.lianjia.beike' or node.get('visible') is not True or
                node.get('password') is not False or node.get('content_redacted') is True):
            continue
        row = {key: node[key] for key in ('path', 'node_sha256', 'enabled', 'clickable', 'editable', 'supports_set_text') if key in node}
        row['omitted_truncated_fields'] = []
        for key in ('resource_id', 'class', 'text', 'content_desc'):
            if node.get(key + '_truncated') is True:
                row['omitted_truncated_fields'].append(key)
            elif node.get(key + '_truncated') is False and type(node.get(key)) is str:
                row[key] = node[key]
        summary.append(row)
    bundle = {'schema': 'pocket4-beike-two-step-private-original-byte-bundle-v1', 'flow': str(FLOW),
              'step_file_sets': file_sets, 'files': {key: {'bytes': len(body), 'sha256': sha(body),
                  'base64': base64.b64encode(body).decode('ascii')} for key, body in sorted(files.items())},
              'full_original_bytes': True, 'contains_private_UI_evidence': True, 'approved_for_Git': False}
    OUTPUT.mkdir(mode=0o700)
    raw = (json.dumps(bundle, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode()
    bundle_pin = write_new(OUTPUT / 'bundle.private.json', raw)
    need(census() == before, 'WHOLE_PROCESS_FD_IDENTITIES_CHANGED')
    result = {'schema': 'pocket4-beike-two-step-host-reader-v1', 'ok': True, 'source_sha256': source_sha,
              'source_qa_sha256': QA_SHA, 'private_bundle': bundle_pin, 'files': len(files), 'total_original_bytes': total,
              'step_file_sets': file_sets, 'flow_metadata_and_plan_files': list(ROOT_FILES),
              'originals_unchanged': True, 'whole_process_fd_identities_unchanged': True,
              'namespace_entries': 0, 'Main_commands': 0, 'UI_actions': 0, 'guards_or_Main_locks_acquired': 0,
              'original_flow_writes': 0, 'reconciliation_written': False,
              'inspection_nonce': INSPECT_NONCE, 'inspection_wire_sha256': assessment['wire_sha256'],
              'tree_sha256': tree['tree_sha256'], 'window_sha256': tree['window_sha256'],
              'visible_nonpassword_node_summary': summary, 'summary_is_postcondition_proof': False,
              'stdout_contains_private_UI_evidence': True, 'stdout_approved_for_Git': False}
    write_new(OUTPUT / 'result.private.json', (json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode())
    need(census() == before, 'FINAL_FD_IDENTITY_CHECK')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-once', action='store_true')
    parser.add_argument('--source-sha256')
    args = parser.parse_args()
    if not args.collect_once:
        print(json.dumps({'state': 'PLAN_ONLY', 'Main_commands': 0, 'collection_started': False}))
        return 0
    need(type(args.source_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.source_sha256), 'EXTERNAL_SOURCE_PIN')
    result = collect(args.source_sha256)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
