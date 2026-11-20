#!/usr/bin/env python3
"""Exercise actual QSB phase methods and the unchanged exclusive journal writer.

This is a local phase regression only. It never constructs a live Session,
obtains a Main/release/resource authority, or calls a host/Android transport.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types


HERE = Path(__file__).resolve().parent
BEFORE_SHA = '5da8c14db7e6b3489b7729bf960b543658edf4f705553daeccaf287b094348fe'
COMMON_SHA = '682e0805008846437882162bf4b21fdd4982937c1003a5804f64d7aa4d2e2211'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_runtime(path, raw):
    module = types.ModuleType('qsb_phase_regression_' + digest(raw)[:12])
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    clock = types.SimpleNamespace(now=1000.0)
    module.time = types.SimpleNamespace(monotonic=lambda: clock.now)
    # The real constructor and transport base are intentionally unavailable.
    session_type = module.make_session_class(
        types.SimpleNamespace(ClockTransportBase=object))
    return session_type, clock


def common_writer(raw):
    source = ast.parse(raw)
    functions = [node for node in source.body
                 if isinstance(node, ast.FunctionDef)
                 and node.name in {'need', 'canonical', 'sha', 'write_new'}]
    assert {node.name for node in functions} == {'need', 'canonical', 'sha', 'write_new'}
    module = ast.Module(body=functions, type_ignores=[])
    namespace = {'Path': Path, 'os': os, 'hashlib': hashlib, 'json': json}
    exec(compile(module, str(HERE.parent / 'current-canonical-app-main-20261120/bundle/source/shared/app_common.py'), 'exec'), namespace)
    return types.SimpleNamespace(**namespace)


def phase_fixture(session_type, common, root):
    session = object.__new__(session_type)
    session.c = common
    session.root = root
    session.pending = session.active_api = None
    session.host_retirement_unknown = False
    session.phase = 'business'
    session.started = 1000.0
    session.deadline = 1600.0
    session.cleanup_deadline = 1720.0
    session.native_launches = 1
    session.base_ref = {'model': 'phase-only-no-runtime-authority'}
    return session


def expect_failure(kind, action):
    try:
        action()
    except kind as error:
        return error
    raise AssertionError('expected ' + kind.__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    work = args.work.absolute() if args.work else None
    if work is not None:
        assert work.resolve() == work and work.is_dir() and not work.is_relative_to(HERE)
    report = args.report.absolute() if args.report else None
    if report is not None:
        assert report.parent.resolve() == report.parent and not report.is_relative_to(HERE)
        assert not report.exists()
    before_path = HERE / 'preimage/qsb_runtime.py'
    after_path = HERE / 'source/qsb_runtime.py'
    common_path = HERE.parent / 'current-canonical-app-main-20261120/bundle/source/shared/app_common.py' 
    before, after, common_raw = [path.read_bytes()
                                 for path in (before_path, after_path, common_path)]
    assert digest(before) == BEFORE_SHA and digest(common_raw) == COMMON_SHA
    old = b"self.record('phase-cleanup',{'phase':'cleanup','base_plan':self.base_ref,"
    new = b"self.record('phase-cleanup-%d'%self.native_launches,{'phase':'cleanup','base_plan':self.base_ref,"
    assert before.count(old) == 1 and after == before.replace(old, new, 1)
    common = common_writer(common_raw)
    original_type, original_clock = load_runtime(before_path, before)
    fixed_type, fixed_clock = load_runtime(after_path, after)
    passed = []

    with tempfile.TemporaryDirectory(prefix='phase-regression-', dir=work) as tmp:
        root = Path(tmp)

        original = root / 'original'
        original.mkdir()
        session = phase_fixture(original_type, common, original)
        session.begin_cleanup()
        first = (original / 'phase-cleanup.json').read_bytes()
        session.reopen_business()
        session.native_launches = 2  # Model only the already bounded second launch count.
        error = expect_failure(FileExistsError, session.begin_cleanup)
        assert Path(error.filename).name == 'phase-cleanup.json'
        assert (original / 'phase-cleanup.json').read_bytes() == first
        passed.append('exact_preimage_reproduces_second_cleanup_collision')

        cycles = root / 'two-cycles'
        cycles.mkdir()
        session = phase_fixture(fixed_type, common, cycles)
        session.begin_cleanup()
        first_ref = dict(session.phase_ref)
        first = (cycles / 'phase-cleanup-1.json').read_bytes()
        assert session.deadline == session.cleanup_deadline == 1720.0
        session.reopen_business()
        assert session.deadline == session.started + 600 == 1600.0
        assert session.cleanup_deadline == 1720.0
        session.native_launches = 2
        session.begin_cleanup()
        assert session.phase_ref['path'] != first_ref['path']
        assert (cycles / 'phase-cleanup-1.json').read_bytes() == first
        assert sorted(path.name for path in cycles.iterdir()) == [
            'phase-cleanup-1.json', 'phase-cleanup-2.json', 'phase-reopen.json']
        for reference in (first_ref, session.phase_ref):
            raw = Path(reference['path']).read_bytes()
            assert reference['bytes'] == len(raw) and reference['sha256'] == digest(raw)
            body = json.loads(raw)
            assert body == {'phase': 'cleanup', 'base_plan': session.base_ref,
                            'deadline_monotonic': 1720.0, 'automatic_retry': False}
        assert session.deadline == session.cleanup_deadline == 1720.0
        passed.append('two_cleanup_cycles_keep_distinct_exclusive_receipts_and_original_deadlines')

        replay = root / 'same-cycle-replay'
        replay.mkdir()
        session = phase_fixture(fixed_type, common, replay)
        session.begin_cleanup()
        first = (replay / 'phase-cleanup-1.json').read_bytes()
        session.reopen_business()
        # No second launch occurred: the existing cycle's journal must not be replaced.
        error = expect_failure(FileExistsError, session.begin_cleanup)
        assert Path(error.filename).name == 'phase-cleanup-1.json'
        assert (replay / 'phase-cleanup-1.json').read_bytes() == first
        assert not (replay / 'phase-cleanup-2.json').exists()
        passed.append('same_cycle_replay_still_fails_exclusive_create_without_overwrite')

        expired = root / 'expired-cleanup'
        expired.mkdir()
        session = phase_fixture(fixed_type, common, expired)
        fixed_clock.now = 1720.0
        error = expect_failure(RuntimeError, session.begin_cleanup)
        assert str(error) == 'QSB_CLEANUP_REQUIRES_KNOWN_EFFECTS_AND_ORIGINAL_RESERVE'
        assert session.phase == 'business' and not list(expired.iterdir())
        passed.append('original_720_second_cleanup_cutoff_rejects_before_journal_creation')

        expired_reopen = root / 'expired-reopen'
        expired_reopen.mkdir()
        fixed_clock.now = 1000.0
        session = phase_fixture(fixed_type, common, expired_reopen)
        session.begin_cleanup()
        fixed_clock.now = 1600.0
        error = expect_failure(RuntimeError, session.reopen_business)
        assert str(error) == 'QSB_REOPEN_INSIDE_ORIGINAL_BUSINESS_BUDGET'
        assert session.cleanup_deadline == session.deadline == 1720.0
        assert not (expired_reopen / 'phase-reopen.json').exists()
        passed.append('original_600_second_reopen_cutoff_remains_enforced')

    assert before_path.read_bytes() == before
    assert after_path.read_bytes() == after
    assert common_path.read_bytes() == common_raw
    result = {
        'schema': 'p4-qsb-two-cleanup-phase-regression-v1',
        'state': 'EXACT_ORIGINAL_FAILURE_REPRODUCED_AND_FIVE_PHASE_CONTROLS_PASSED',
        'before_sha256': digest(before), 'after_sha256': digest(after),
        'unchanged_common_sha256': digest(common_raw),
        'passed_controls': passed, 'count': len(passed),
        'actual_exclusive_file_writer_used': True,
        'local_test_inputs_bookends_equal': True,
        'live_session_constructor_called': False,
        'clock_and_launch_count_are_explicit_phase_models': True,
        'host_commands': 0, 'Android_commands': 0, 'Main_entries': 0,
        'runtime_qualified': False, 'production_ready': False,
    }
    if report is not None:
        with report.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
