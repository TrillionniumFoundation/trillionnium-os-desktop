"""Static preservation and isolated R21 baseline-rejection controls.

Never imports the operational controller, reads a host source tree, takes a
lock, or dispatches a command. Synthetic bookend rows below grant no source
or runtime credit; complete real inventory replay belongs to ROOT integration.
"""
from pathlib import Path
from types import SimpleNamespace
import ast
import copy
import hashlib
import json

ROOT = Path(__file__).resolve().parent
BEFORE_SHA = '71e439b91b5363ed9f295589ea7b29f6404de1556b9e61af0d85c6640e4768e9'

def need(value, message):
    if not value:
        raise ValueError(message)

def functions(raw):
    return {node.name: node for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef)}

def body(raw, node):
    return b''.join(raw.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])

def budgets(node):
    return [ast.dump(call.args[3], include_attributes=False) for call in ast.walk(node)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and call.func.id == 'run']

def main():
    old = (ROOT / 'source-r21.py').read_bytes()
    new = (ROOT / 'R22-TRANSITION-FUNCTIONS.py').read_bytes()
    assert len(old) == 277931 and hashlib.sha256(old).hexdigest() == BEFORE_SHA
    before, after = functions(old), functions(new)
    expected = {'source_contracts', 'r22_require_R21_bodies', 'r22_compare', 'r22_candidate_rules',
                'normal_reconcile_and_verify', 'r22_verify_reconcile_return',
                'r20_recovery_retirement', 'verify_recovered_source'}
    assert set(after) == expected
    assert all(isinstance(node, ast.FunctionDef) or
               (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and type(node.value.value) is str) for node in ast.parse(new).body)
    compile(new, 'R22-TRANSITION-FUNCTIONS.py', 'exec')
    retirement_before = body(old, before['r20_recovery_retirement'])
    retirement_after = body(new, after['r20_recovery_retirement'])
    old_schema = b'p4-r21-original-build-retirement-before-recovery-v1'
    new_schema = b'p4-r22-original-build-retirement-before-recovery-v1'
    assert retirement_before.count(old_schema) == retirement_after.count(new_schema) == 1
    assert retirement_before.replace(old_schema, new_schema) == retirement_after
    for name in ('normal_reconcile_and_verify', 'verify_recovered_source'):
        assert budgets(before[name]) == budgets(after[name]), name
        count = lambda node: sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                                 and n.func.id == 'original_source_locks' for n in ast.walk(node))
        assert count(before[name]) == count(after[name]) == 1
    assert new.count(b"run('normal-resume-apex-tests652-once'") == 1
    assert b"elif resume is not None:" in new
    assert b"pre-existing resume record requires a separately reviewed successor; no retry" in new
    assert not any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == 'DEADLINE'
                   for n in ast.walk(ast.parse(new)))
    # Only this pure admission predicate is executed. r20_json is represented
    # by an explicit finite in-memory table; its real F9 reader is not tested
    # or replaced in the operational candidate.
    fn = after['r22_require_R21_bodies']
    ns = {'need': need, 'TRANSITION22': SimpleNamespace(TRACKED_MEMBERS=1045300)}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<baseline-predicate>', 'exec'), ns)
    actual_recovery = json.loads((ROOT.parent / 'r21-review/RECOVERY-OBSERVATION-FINAL.json').read_bytes())
    baseline_pin = actual_recovery['final_normal_manifest']['original']
    projects = [dict(project='controlled/project%03d' % i, tree='b' * 40,
                     tracked_entries=1044649 if i == 0 else 1,
                     materialized_entries=500 if i == 0 else 0,
                     materialized_bytes=1000 if i == 0 else 0,
                     sparse_absent_entries=1044149 if i == 0 else 1,
                     body_sha256='d' * 64) for i in range(652)]
    baseline = dict(schema='pocket4-original-materialized-source-content-bookend-v1',
                    all_actual_Git_blob_reads_verified=True, source_mutations=False,
                    project_count=652, projects=projects, content_sha256='c' * 64,
                    materialized_entries=500, materialized_bytes=1000, sparse_absent_entries=1044800)
    contracts = {'old': {'plan': {'projects': [p['project'] for p in projects]}}}
    recovery = copy.deepcopy(actual_recovery)
    recovery['content_bookends']['lint652-content-after-recovery'] = 'controlled-bookend'
    ns['R22'] = {'predecessor': {'recovery': 'controlled-recovery'}, 'baseline': {'manifest': baseline_pin}}
    active = {}
    ns['r20_json'] = lambda ref: copy.deepcopy(active[ref])
    def exercise(change_summary=None, change_recovery=None, expected=True):
        summary, observed = copy.deepcopy(baseline), copy.deepcopy(recovery)
        if change_summary:
            change_summary(summary)
        if change_recovery:
            change_recovery(observed)
        active.clear(); active.update({'controlled-bookend': baseline, 'controlled-recovery': observed})
        try:
            ns['r22_require_R21_bodies'](summary, contracts)
        except (ValueError, KeyError):
            assert not expected
        else:
            assert expected
    exercise()
    negatives = [
        ('source_body_changed', lambda x: x['projects'][10].update(body_sha256='e' * 64), None),
        ('tuple_tree_changed', lambda x: x['projects'][11].update(tree='a' * 40), None),
        ('tracked_scope_changed', lambda x: x['projects'][12].update(tracked_entries=2), None),
        ('project_order_changed', lambda x: x['projects'].reverse(), None),
        ('aggregate_content_changed', lambda x: x.update(content_sha256='f' * 64), None),
        ('aggregate_bytes_changed', lambda x: x.update(materialized_bytes=1001), None),
        ('actual_blob_credit_missing', lambda x: x.update(all_actual_Git_blob_reads_verified=False), None),
        ('source_mutation_claim', lambda x: x.update(source_mutations=True), None),
        ('wrong_project_count', lambda x: x.update(project_count=651), None),
        ('recovery_incomplete', None, lambda x: x.update(source_recovery_complete=False)),
        ('recovery_error_retained', None, lambda x: x.update(errors=['controlled error'])),
        ('native_provenance_not_preserved', None, lambda x: x.update(native_source_926_members_and_git_provenance_unchanged=False)),
        ('manifest_epoch_changed', None, lambda x: x['final_normal_manifest']['original']['identity'].__setitem__(1, 1)),
        ('cmake_member_loss', None, lambda x: x.update(complete_cmake_members_preserved=3914)),
    ]
    for _, mutate_summary, mutate_recovery in negatives:
        exercise(mutate_summary, mutate_recovery, False)
    report = {
        'schema': 'p4-r22-transition-functions-static-review-v1',
        'fragment': {'bytes': len(new), 'sha256': hashlib.sha256(new).hexdigest()},
        'source_r21_unmodified': {'bytes': len(old), 'sha256': hashlib.sha256(old).hexdigest()},
        'retirement_only_schema_literal_changed': True,
        'all_original_run_budget_expressions_preserved': True,
        'original_lock_contexts_preserved': True,
        'single_conditional_resume_and_no_repeat_preserved': True,
        'fragment_never_reassigns_deadline': True,
        'module_has_no_import_time_actions': True,
        'python_compile_passed': True,
        'isolated_baseline_positive_controls': 1,
        'isolated_baseline_negative_controls': [name for name, _, _ in negatives],
        'real_complete_inventory_replay_executed': False,
        'normal_reconcile_executed': False,
        'source_recovery_complete': False,
        'vendor_build_passed': False,
        'runtime_qualified': False,
        'production_ready': False,
        'integration_requires': [
            'ROOT exact R22 globals, current CLI/profile plan evidence and reviewed actual R21 baseline',
            'ROOT R22 write_source_stage/read_source_stage schema and R22 outer retirement writer',
            'unchanged original generic build/recover, runner, three locks, fixed deadlines and 1200-second recovery',
            'actual strict F9 reads of complete R21 lint652 bookend and full1045300-row transition inventory',
            'ROOT full integrated source review before any normal launch'
        ]
    }
    (ROOT / 'R22-TRANSITION-REVIEW.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True, indent=2))

if __name__ == '__main__':
    main()
