"""Check readonly binder prerequisites without generating a plan or calling main."""
from pathlib import Path
import ast
import copy
import hashlib
import json

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(__file__).resolve().parent
OUT = ROOT / 'owner14-normal-generator-freeze-01'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    assert not OUT.exists()
    path = WORK / 'freeze_normal14.py'
    source = path.read_text()
    tree = ast.parse(source)
    ns = {'__name__': 'source_only_verification', '__file__': str(path)}
    exec(compile(tree, str(path), 'exec'), ns)
    ns['old_plan'] = json.loads((ROOT / 'owner11-normal01-freeze-01/plan.json').read_bytes())
    ns['plan'] = copy.deepcopy(ns['old_plan'])
    ns['host_manifest'] = (ns['HOST_PAIR'] / 'manifest.json').read_bytes()
    assert sha(ns['host_manifest']) == 'fab7226afa93d372a7ba7d025cd704ae4aba878f9fa5336490af72eca98e6593'
    actual_main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    blocks = [
        ('fixture_lineage', '    fixture_manifest =', '    expected = dict(cfg'),
        ('actual_Owner11_failure_and_cause', '    predecessor_path =', '    assert plan["broker_bootstrap_source_manifest_sha256"]'),
        ('diagnostics_and_original_terminal_contract', '    assert plan["broker_bootstrap_source_manifest_sha256"]', '    prior_ordinary_raw ='),
        ('actual_producer13_failure_preservation', '    prior_ordinary_raw =', '    plan["broker_bootstrap_source_contract"]'),
        ('source_profile_and_retained_observation', '    source_freeze =', '    payload = {};'),
    ]
    checked = []
    for label, start, end in blocks:
        first = source.index(start)
        last = source.index(end, first)
        first_line = source.count('\n', 0, first) + 1
        last_line = source.count('\n', 0, last) + 1
        nodes = [n for n in actual_main.body if n.lineno >= first_line and n.end_lineno < last_line]
        assert nodes, label
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), label, 'exec'), ns)
        checked.append({'block': label, 'actual_local_statements_checked': len(nodes)})
    old = (ROOT / 'owner13-normal-generator-freeze-01/freeze_normal13.py').read_text()
    first = '    predecessor_path ='
    last = '    assert plan["broker_bootstrap_source_manifest_sha256"]'
    assert old[old.index(first):old.index(last)] == source[source.index(first):source.index(last)]
    old_functions = {n.name: ast.dump(n) for n in ast.parse(old).body if isinstance(n, ast.FunctionDef)}
    new_functions = {n.name: ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert set(old_functions) == set(new_functions)
    assert all(old_functions[n] == new_functions[n] for n in old_functions if n != 'main')
    evidence = ROOT.parent / 'root-recovery-20261104-02/evidence'
    compile13 = json.loads((evidence / 'owner13-compile01/compile-result.json').read_bytes())
    ordinary13 = json.loads((evidence / 'owner13-ordinary01/run-result.json').read_bytes())
    rejected = []
    for role, value in [('rb', compile13), ('rr', ordinary13)]:
        expressions = [n for n in actual_main.body if isinstance(n, ast.Assert) and
            f'{role}["revision"]' in (ast.get_source_segment(source, n) or '')]
        assert len(expressions) == 1
        observed = eval(compile(ast.Expression(expressions[0].test), 'actual_revision_admission', 'eval'), {role: value})
        assert observed is False
        rejected.append({'actual_input': role, 'previous13_rejected_by_actual14_predicate': True})
    assert not (ROOT / 'owner13-normal01-freeze-01').exists()
    assert not (ROOT / 'owner14-normal01-freeze-01').exists()
    review = {
        'schema': 1, 'scope': 'Binder source-only local readonly prerequisite verification',
        'binder_bytes': len(source.encode()), 'binder_sha256': sha(source.encode()),
        'read_only_actual_blocks_checked': checked,
        'old_compile_and_failed_ordinary_rejected': rejected,
        'Owner11_predecessor_block_exactly_unchanged_from13': True,
        'helpers_except_main_AST_unchanged': sorted(n for n in old_functions if n != 'main'),
        'actual14_compile_or_ordinary_receipts_used': False,
        'actual14_hashes_assumed': False,
        'plan_nonce_request_or_runtime_created': False,
        'remote_called': False,
        'normal13_never_prepared_or_executed': True,
        'first_local_check_setup_error': 'An earlier ad-hoc readonly check omitted host_manifest from its local namespace and raised NameError before writing any freeze. This checker loads and verifies that already-frozen manifest explicitly.',
        'scope_limits': [
            'Eight new profile predicates were checked; old init observation controls were retained through exact function AST and qualifier bytes, not rerun.',
            'All Producer13 and Owner11 failures remain failed; ordinary success does not qualify actual Owner.',
            'Planned fresh UID61286/range20900000+100000 still require device live absence gates.',
        ],
    }
    files = {name: (WORK / name).read_bytes() for name in
        ['freeze_normal14.py', 'freeze_normal13-to14.diff', 'derive_freezer14.py', 'check_binder14.py']}
    files['predecessor-binding-check.json'] = (json.dumps(review, indent=2, sort_keys=True) + '\n').encode()
    files['README.md'] = b'''# Owner14 actual-receipt binder source snapshot

This snapshot contains only the future binder. It requires four externally pinned
actual receipts, including successful Producer14 compile and ordinary results;
unknown hashes are not filled. No plan, random nonce, prepare or runtime request
has been created. The actual Producer13 ordinary failure is rejected as an
eligible ordinary result and remains immutable evidence.

The binder preserves the last actual Owner11 failed runtime and its original
retirement failure, with later outer cleanup recorded separately. Producer14 only
changes two test fixtures; the production13 diagnostics and terminal-drain
contract keep their original manifest identities. New fixture lineage is an
additional distinct field. The original ABI3 Android DSO and LMKD are unchanged.

Local verification evaluated only readonly source/evidence prerequisites and
actual admission predicates. It did not execute Rust, Android, namespaces or any
remote tool. Matching actual results and Root review remain necessary.
'''
    OUT.mkdir()
    rows = []
    for name, data in sorted(files.items()):
        data.decode('utf-8')
        with (OUT / name).open('xb') as stream:
            stream.write(data)
        rows.append({'path': name, 'bytes': len(data), 'sha256': sha(data)})
    manifest = (json.dumps({'schema': 1, 'kind': 'owner14_normal_binder_source_snapshot', 'files': rows}, sort_keys=True, indent=2) + '\n').encode()
    with (OUT / 'manifest.json').open('xb') as stream:
        stream.write(manifest)
    print(json.dumps({'root': str(OUT), 'files': len(files) + 1, 'manifest_sha256': sha(manifest),
        'review_sha256': sha(files['predecessor-binding-check.json']),
        'actual_readonly_statements_checked': sum(x['actual_local_statements_checked'] for x in checked)}))


if __name__ == '__main__':
    main()
