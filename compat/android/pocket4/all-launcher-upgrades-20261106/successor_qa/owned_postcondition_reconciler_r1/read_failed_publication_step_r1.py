#!/usr/bin/env python3
"""Read one settled failed proof step. No Main imports, commands, or locks."""
import ast
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
STEP = FLOW / 'steps/owned-postcondition-close-01'
OUTPUT = Path('/home/alex/work/pocket4-beike-publication-foreground-evidence-20261106-r1')
STAGED = Path('/home/alex/work/pocket4-beike-owned-postcondition-20261106-baaf68ac0d617dbe3894f714b18f099b')
RECORDER = Path('/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder')
CORE_PIN = (STAGED / 'owned_postcondition_core.py', 28714, '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41')
TRANSPORT_PIN = (RECORDER / 'bound_android_transport.py', 15603, '069d003809d95b33e0d727fdec3ca6e8488e214180449cacbad07e66a302652f')
TASK_PIN = (RECORDER / 'references/task_scope_baseline.py', 17281, 'a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528')
PUBLISHER_SHA = '1c20f6ffb7c8fc260e161a1ac5a95df0852d0daa23bc833c71533ef6964b55a2'
REQUEST_SHA = '56148436bf7a0f50f456ce4858bf6f0988e4bfc4156f6cd4d5246e5cf0c041ed'
FAILURE_REFERENCE = {'job_id': '1a1b1f2e015-fc05-7ba9', 'stdout_bytes': 582,
    'stdout_sha256': '6018ef68e5fc95822137d56b2bfe9f8ec7cfe805988e9a4df434f2903cade3ab',
    'terminal_bytes': 726, 'terminal_sha256': 'b1211031571b1aab3d0d65a8afe9fb0ebf059cd41769f8d25856556454ce660f',
    'state': 'failed', 'exit_code': 1, 'publication_attempted': False,
    'original_reference_supplied_by_coordinator': True}
STAT = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
DIRECTORY_IDENTITY = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')
EXPECTED = {'intent.json', 'held-main-binding.json'}
EXPECTED |= {f'command-{n:03d}.{suffix}' for n in range(1, 4) for suffix in ('intent.json', 'result.json', 'stdout', 'stderr')}
EXPECTED |= {f'transport-{n:03d}.{suffix}.json' for n in range(1, 5) for suffix in ('intent', 'command-result', 'verified-result')}
HELPER = '/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry'


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def metadata(value):
    return tuple(getattr(value, key) for key in STAT)


def census():
    rows = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            row = os.fstat(int(name))
            rows[name] = (os.readlink('/proc/self/fd/' + name), row.st_dev, row.st_ino,
                          row.st_mode, row.st_uid, row.st_gid)
        except OSError as error:
            if error.errno not in (errno.ENOENT, errno.EBADF):
                raise
    return rows


class Directory:
    def __init__(self, path, private=True):
        self.path = Path(path); self.owned = []; self.parents = []
        try:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            self.owned.append(fd)
            for part in self.path.parts[1:]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
                self.owned.append(child)
                self.parents.append((fd, part, child, tuple(getattr(os.fstat(child), key) for key in DIRECTORY_IDENTITY)))
                fd = child
            self.fd = fd
            row = os.fstat(fd)
            need(row.st_uid == 0 and (not private or stat.S_IMODE(row.st_mode) == 0o700), 'FIXED_ROOT_DIRECTORY')
        except BaseException:
            self.close(); raise

    def check(self):
        for parent, name, fd, original in self.parents:
            held, current = os.fstat(fd), os.stat(name, dir_fd=parent, follow_symlinks=False)
            need(tuple(getattr(held, key) for key in DIRECTORY_IDENTITY) ==
                 tuple(getattr(current, key) for key in DIRECTORY_IDENTITY) == original,
                 'FIXED_INPUT_DIRECTORY_CHANGED')

    def read(self, name, limit, deadline):
        need('/' not in name and name not in ('', '.', '..'), 'FLAT_FIXED_FILE_ONLY')
        fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            first = os.fstat(fd)
            need(stat.S_ISREG(first.st_mode) and first.st_uid == 0 and first.st_nlink == 1 and
                 not first.st_mode & 0o077 and 0 <= first.st_size <= limit, 'ROOT_PRIVATE_BOUNDED_FILE')
            raw = bytearray()
            while len(raw) <= first.st_size:
                need(time.monotonic() < deadline, 'HOST_READER_DEADLINE')
                part = os.read(fd, min(65536, first.st_size + 1 - len(raw)))
                if not part:
                    break
                raw.extend(part)
            need(len(raw) == first.st_size and metadata(first) == metadata(os.fstat(fd)) ==
                 metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False)), 'ORIGINAL_FILE_CHANGED_DURING_READ')
            return bytes(raw), metadata(first)
        finally:
            os.close(fd)

    def absent(self, name):
        try:
            os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            return True
        return False

    def close(self):
        errors = []
        while self.owned:
            fd = self.owned.pop()
            try:
                os.close(fd)
            except OSError as error:
                errors.append(error.errno)
        need(not errors, 'OWNED_DIRECTORY_RELEASE_FAILED')


def source_bytes(pin, deadline):
    path, size, digest = pin
    directory = Directory(path.parent)
    try:
        raw, unused = directory.read(path.name, size, deadline)
        need(len(raw) == size and sha(raw) == digest, 'FROZEN_PURE_SOURCE_PIN')
        directory.check()
        return raw
    finally:
        directory.close()


def pure_module(pin, deadline, name):
    raw = source_bytes(pin, deadline)
    module = types.ModuleType(name); module.__file__ = str(pin[0])
    exec(compile(raw, str(pin[0]), 'exec'), module.__dict__)
    return module


def save_once(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:]); need(count > 0, 'OWNED_WRITE_PROGRESS'); offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        data = bytearray()
        while len(data) <= len(raw):
            part = os.read(fd, min(65536, len(raw) + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        need(bytes(data) == raw, 'OWNED_WRITE_READBACK')
    finally:
        os.close(fd)
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def main():
    need(os.getuid() == os.geteuid() == 0, 'ACTUAL_ROOT_HOST_READER')
    os.umask(0o077); before = census(); deadline = time.monotonic() + 60
    core = pure_module(CORE_PIN, deadline, 'fixed_offline_postcondition_core')
    transport = pure_module(TRANSPORT_PIN, deadline, 'fixed_transport_pure_definitions')
    task_raw = source_bytes(TASK_PIN, deadline)
    task_ast = ast.parse(task_raw)
    functions = [node for node in task_ast.body if isinstance(node, ast.FunctionDef) and node.name in ('require', 'parse_stacks', 'exact_leaf')]
    need({node.name for node in functions} == {'require', 'parse_stacks', 'exact_leaf'}, 'THREE_FROZEN_PURE_TASK_FUNCTIONS')
    task = {'re': re}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(TASK_PIN[0]), 'exec'), task)
    step = reconciliations = None
    try:
        step = Directory(STEP); reconciliations = Directory(FLOW / 'reconciliations')
        need(set(os.listdir(step.fd)) == EXPECTED and len(EXPECTED) == 26, 'EXACT_FAILED_STEP_26_FILES')
        need(reconciliations.absent('close-entry-popup-01.json'), 'RECONCILIATION_MUST_REMAIN_ABSENT')
        originals = {}; stats = {}
        for name in sorted(EXPECTED):
            originals[name], stats[name] = step.read(name, 1048576, deadline)
        need(sum(map(len, originals.values())) <= 2097152, 'BOUNDED_26_FILE_TOTAL')
        read = lambda name: core.document(originals[name])
        intent = read('intent.json'); binding = read('held-main-binding.json')
        core.fixed_scope(intent['scope'])
        need(intent['operation'] == 'owned-qa-postcondition-proof' and intent['mutation'] is False and
             intent['automatic_retry'] is False and intent['unknown_step'] == 'close-entry-popup-01' and
             intent['observation_step'] == 'inspect-after-close-02' and
             intent['request'] == {'new_producer_schema': 'pocket4-beike-owned-qa-postcondition-proof-v1',
                'request_sha256': REQUEST_SHA, 'producer_sha256': PUBLISHER_SHA, 'verifier_sha256': CORE_PIN[2]},
             'EXACT_FAILED_PUBLISHER_INTENT')
        core.held_binding_identity(binding)
        need(binding['framework_epoch_sha256'] == core.MAIN_EPOCH and binding['runtime_epoch_sha256'] == core.RUNTIME_EPOCH and
             binding['app_scope_sha256'] == core.APP_SCOPE and binding['package'] == core.PACKAGE and binding['uid'] == core.UID,
             'FIXED_FAILED_BINDING_SCOPE')
        definitions = [(['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--user', '0', core.HELPER], 8),
            (['/system/bin/cmd', 'package', 'path', '--user', '0', core.HELPER], 8),
            (['/system/bin/cmd', 'activity', 'stack', 'list'], 20),
            (['/system/bin/dumpsys', 'window', 'displays'], 15)]
        authority = None; commands = []; private_foreground = None
        for index, (argv, timeout) in enumerate(definitions, 1):
            stem = f'transport-{index:03d}.'
            ti, tr, verified = (read(stem + name + '.json') for name in ('intent', 'command-result', 'verified-result'))
            expected = {'sequence': index, 'epoch_sha256': core.MAIN_EPOCH, 'package': core.PACKAGE, 'uid': core.UID,
                'command_sha256': sha(json.dumps(argv, ensure_ascii=False, separators=(',', ':')).encode()),
                'timeout_seconds': timeout, 'inner_timeout_seconds': max(1, timeout - 5),
                'automatic_retry': False, 'numeric_pid_target_used': False}
            need(ti == expected and tr == verified and all(tr.get(k) == v for k, v in expected.items()) and
                 set(tr) == set(expected) | {'returncode', 'stdout_bytes', 'stderr_bytes', 'stdout_sha256', 'stderr_sha256', 'action_attempted', 'outcome_unknown'} and
                 type(tr['returncode']) is int and tr['returncode'] == 0 and tr['action_attempted'] is True and
                 tr['outcome_unknown'] is False and tr['stderr_bytes'] == 0 and tr['stderr_sha256'] == core.EMPTY_SHA and
                 type(tr['stdout_bytes']) is int and 0 < tr['stdout_bytes'] <= 4 * 1024 * 1024 and
                 re.fullmatch('[0-9a-f]{64}', tr['stdout_sha256']), 'COMPLETE_FOUR_READONLY_TRANSPORTS')
            if index == 4:
                private_foreground = {key: tr[key] for key in ('returncode', 'stdout_bytes', 'stdout_sha256', 'stderr_bytes', 'stderr_sha256', 'outcome_unknown')}
                continue
            stem = f'command-{index:03d}'
            ci, cr = read(stem + '.intent.json'), read(stem + '.result.json')
            raw, error = originals[stem + '.stdout'], originals[stem + '.stderr']
            core.command_success(ci, cr, raw, error, False, timeout)
            actual_authority = core.command_argv(ci, argv, timeout, HELPER, binding['classpath']['values'], transport)
            authority = actual_authority if authority is None else authority
            need(authority == actual_authority and sha(raw) == tr['stdout_sha256'] and len(raw) == tr['stdout_bytes'],
                 'SAME_AUTHORITY_AND_EXACT_TRANSPORT_RAW')
            commands.append({'index': index, 'command': argv, 'returncode': cr['returncode'], 'joined': cr['owned_command_joined'],
                'timed_out': cr['timed_out'], 'stdout_bytes': len(raw), 'stdout_sha256': sha(raw), 'stderr_bytes': len(error)})
        need(originals['command-001.stdout'].decode('utf-8', 'strict').splitlines() ==
             ['package:' + core.HELPER + ' uid:' + str(core.HELPER_UID)], 'EXACT_HISTORICAL_HELPER_UID')
        paths = originals['command-002.stdout'].decode('utf-8', 'strict').splitlines()
        need(len(paths) == 1 and re.fullmatch(r'package:/data/app/[^/\x00]+/[^/\x00]+/base\.apk', paths[0]), 'ONE_HISTORICAL_HELPER_BASE_APK')
        roots, tasks = task['parse_stacks'](originals['command-003.stdout'].decode('utf-8', 'strict'))
        need(task['exact_leaf'](roots, core.TASK, core.PACKAGE), 'HISTORICAL_TASK_876_EXACT_LEAF')
        for name in sorted(EXPECTED):
            raw, info = step.read(name, 1048576, deadline)
            need(raw == originals[name] and info == stats[name], 'ALL_26_ORIGINALS_UNCHANGED')
        need(set(os.listdir(step.fd)) == EXPECTED and reconciliations.absent('close-entry-popup-01.json'), 'NO_LATE_PROOF_OR_ENVELOPE')
        step.check(); reconciliations.check()
        OUTPUT.mkdir(mode=0o700)
        bundle = {'schema': 'pocket4-failed-publication-step-original-byte-bundle-v1', 'flow': str(FLOW), 'step': str(STEP),
            'files': {name: {'bytes': len(raw), 'sha256': sha(raw), 'base64': base64.b64encode(raw).decode('ascii')}
                      for name, raw in sorted(originals.items())}, 'full_original_bytes': True,
            'contains_private_process_and_task_metadata': True, 'approved_for_Git': False}
        saved = save_once(OUTPUT / 'failed-step.private.json', (json.dumps(bundle, sort_keys=True, separators=(',', ':')) + '\n').encode())
        result = {'schema': 'pocket4-failed-publication-host-evidence-v1', 'ok': True, 'failure_reference': FAILURE_REFERENCE,
            'step': str(STEP), 'file_count': 26, 'total_original_bytes': sum(map(len, originals.values())), 'private_bundle': saved,
            'files': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(originals.items())},
            'three_recorded_commands': commands, 'fourth_private_foreground_transport': private_foreground,
            'historical_helper': {'package': core.HELPER, 'uid': core.HELPER_UID, 'base_apk': paths[0][8:],
                'this_reader_rehashed_installed_APK': False},
            'historical_target_task': {'id': core.TASK, 'root': roots[core.TASK], 'exact_leaf': True},
            'foreground_package_at_failure': 'UNKNOWN_RAW_DISCARDED_BY_FROZEN_PRIVACY_CONTRACT',
            'foreground_predicate_source': 'qa_adapter.Session.foreground compares parsed package to com.lianjia.beike; legacy BILI label unchanged',
            'new_proof_and_result_files_absent': True, 'reconciliation_envelope_absent': True,
            'current_live_state_queried': False, 'Main_reads': 0, 'Main_commands': 0, 'Main_locks_or_guards': 0,
            'namespace_entries': 0, 'UI_actions': 0, 'original_unknown_changed': False,
            'publication_retried': False, 'automatic_retry': False, 'production_ready': False}
    finally:
        if reconciliations is not None:
            reconciliations.close()
        if step is not None:
            step.close()
    need(census() == before, 'WHOLE_PROCESS_FD_IDENTITIES_CHANGED')
    result['whole_process_fd_identities_unchanged'] = True
    raw = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    need(len(raw) <= 65536, 'SAFE_SUMMARY_BOUND')
    save_once(OUTPUT / 'result.json', raw)
    fd = os.open(OUTPUT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    need(census() == before, 'FINAL_PROCESS_FD_IDENTITIES_CHANGED')
    sys.stdout.buffer.write(raw); sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
