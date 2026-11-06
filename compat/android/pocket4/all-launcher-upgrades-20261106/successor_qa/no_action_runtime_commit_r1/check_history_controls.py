#!/usr/bin/env python3
"""Local-only checks against actual private bytes; never prints their UI content."""
import ast
import base64
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import symtable
import sys
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
CANDIDATE = HERE / 'stage-a-candidate-r1'
PRIVATE = PROJECT.parent / 'p4_private_ui/beike-search-click-failure-bundle-r1/bundle.private.original.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def census():
    result = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd = int(name); row = os.fstat(fd)
            result[name] = [os.readlink('/proc/self/fd/' + name), row.st_dev, row.st_ino,
                            row.st_mode, row.st_uid, row.st_gid]
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno != 9:
                raise
    return result


def module(raw, name):
    value = types.ModuleType(name); value.__file__ = name
    exec(compile(raw, name, 'exec'), value.__dict__)
    return value


def static_globals(raw):
    symbols = symtable.symtable(raw.decode(), 'candidate.py', 'exec')
    allowed = set(symbols.get_identifiers()) | set(vars(builtins)) | {'__file__', '__name__'}
    unknown = set()
    def walk(table):
        for symbol in table.get_symbols():
            if symbol.is_global() and symbol.is_referenced() and symbol.get_name() not in allowed:
                unknown.add(symbol.get_name())
        for child in table.get_children():
            walk(child)
    walk(symbols)
    assert not unknown, sorted(unknown)


def main():
    before = census(); cases = []
    worker_raw = (CANDIDATE / 'runtime_stage_a_once.py').read_bytes()
    partial_raw = (CANDIDATE / 'no_action_core.py').read_bytes()
    static_globals(worker_raw); static_globals(partial_raw)
    worker = module(worker_raw, 'local_only_runtime_definitions')
    partial = module(partial_raw, 'local_only_no_action_reparser')
    reader = module((CANDIDATE / 'read_failed_search_click.frozen.py').read_bytes(), 'local_only_frozen_reader')
    raw = PRIVATE.read_bytes(); archive = json.loads(raw)
    sources = {}
    for label in ('core', 'qa', 'adapter', 'transport', 'run_case', 'base'):
        row = archive['files']['source/' + label]
        body = base64.b64decode(row['base64'], validate=True)
        assert len(body) == row['bytes'] and sha(body) == row['sha256']
        sources[label] = module(body, 'local_only_frozen_' + label)
    task_pin = worker.TASK_SOURCE
    task_raw = (PROJECT / 'successor_qa/reconstructed/source-generation-r2/recorder/references/task_scope_baseline.py').read_bytes()
    assert len(task_raw) == task_pin['bytes'] and sha(task_raw) == task_pin['sha256']
    tasks = module(task_raw, 'local_only_frozen_task_parser')
    bundle, originals, files, result, lifetime = partial.bundle_originals(raw, reader, sources['core'])
    installed, prior_ended, prior = partial.prior_installed_identity(
        (CANDIDATE / 'prior-inspect.stdout.original.jsonl').read_bytes(),
        (CANDIDATE / 'prior-inspect.terminal.original.json').read_bytes(), sources['base'], sources['core'])
    def original(label):
        return partial.document(originals[bundle['files']['input/' + label]['path']][0])
    scope, launch, case = (original(x) for x in ('scope', 'launch', 'case'))
    def verify(selected):
        return partial.verify_failed_single_case(selected, scope, launch, case, result, installed, prior_ended,
            core=sources['core'], qa=sources['qa'], adapter=sources['adapter'],
            transport=sources['transport'], tasks=tasks, runner=sources['run_case'])
    failed = verify(files)
    proof = partial.no_action_public_proof(failed, prior, reader=reader,
        source_pin=worker.PARTIAL_SOURCE, core=sources['core'])
    assert proof['original_case_ok'] is False and proof['original_case_outcome_unknown'] is True
    assert proof['helper_requested_click_dispatch_attempted'] is False
    assert proof['business_postcondition_observed'] is False and proof['independent_later_observer_available'] is False
    assert len(failed['command_proofs']) == 10 and len(failed['phase_proofs']) == 4
    cases.append({'name': 'actual_101_originals_and_single_failed_sequence', 'passed': True,
        'files': 101, 'step_files': 90, 'commands': 10, 'transports': 13,
        'original_FAILED_UNKNOWN_retained': True})

    def rejected(name, changed):
        try:
            verify(changed)
        except (RuntimeError, KeyError, ValueError) as error:
            cases.append({'name': name, 'passed': True, 'rejection_type': type(error).__name__,
                          'rejection_code': str(error) if str(error).replace('_', '').isalnum() else 'STRICT_REJECTION'})
        else:
            raise AssertionError(name + '_NOT_REJECTED')
    absent = dict(files)
    del absent['10b83f1cbaf0af3e9fb1641ba95aacb1.assessment.json']
    rejected('missing_independent_after_state_refused', absent)
    unjoined = dict(files)
    record = partial.document(unjoined['command-006.result.json']); record['owned_command_joined'] = False
    unjoined['command-006.result.json'] = partial.canonical(record) + b'\n'
    rejected('unjoined_action_command_refused', unjoined)
    extra = dict(files); extra['case-00-postcondition.json'] = b'{"invented":true}\n'
    rejected('manufactured_postcondition_refused', extra)
    diagnostic = partial.document(files['15dfd62fe344b6e95aed66cef092b3cb.failed-assessment.json'])
    diagnostic['helper_rejection']['action_attempted'] = True
    ambiguous = dict(files)
    ambiguous['15dfd62fe344b6e95aed66cef092b3cb.failed-assessment.json'] = partial.canonical(diagnostic) + b'\n'
    rejected('helper_attempted_or_ambiguous_record_refused', ambiguous)

    class PinnedPublicOnly:
        def pinned(self, item):
            allowed = {worker.HOST_STDOUT['path']: 'reader.stdout.original.json',
                       worker.HOST_TERMINAL['path']: 'reader.terminal.original.json'}
            body = (CANDIDATE / allowed[item['path']]).read_bytes()
            assert len(body) == item['bytes'] and sha(body) == item['sha256']
            return body
    gate = worker.actual_host_gate(PinnedPublicOnly(), reader, partial)
    assert gate['original_failed_job'] == partial.FAILED_JOB
    cases.append({'name': 'actual_complete_reader_terminal_and_no_action_metadata', 'passed': True})
    after = census(); assert before == after
    assert PRIVATE.read_bytes() == raw
    output = {'schema': 'pocket4-no-action-history-local-controls-v1', 'ok': True,
        'uid': os.getuid(), 'euid': os.geteuid(), 'case_count': len(cases), 'cases': cases,
        'source_sha256': sha(worker_raw), 'core_sha256': sha(partial_raw),
        'actual_bundle_bytes': len(raw), 'actual_bundle_sha256': sha(raw),
        'private_UI_in_output': False, 'private_originals_modified': False,
        'Main_commands': 0, 'Main_locks': 0, 'namespace_entries': 0, 'UI_actions': 0,
        'compatibility_publications': 0, 'current_Main_or_helper_qualification_claimed': False,
        'process_fds_before': before, 'process_fds_after': after,
        'whole_process_fd_identities_unchanged': True}
    print(json.dumps(output, sort_keys=True, separators=(',', ':'), ensure_ascii=True))


if __name__ == '__main__':
    main()
