#!/usr/bin/env python3
"""Read fixed Git objects and freeze the bounded G1-b source review; no product runs."""
import ast
import datetime
import hashlib
import json
import os
import pathlib
import posixpath
import re
import subprocess
import urllib.parse

ROOT = pathlib.Path('/workspace/scratch/499c7902de8e')
REPO = ROOT / 'r11-g1b-usage'
OUT = ROOT / 'r11-evidence/g1b-review'
HEAD = '83e122d40e5427f84efebb4b7a224f7131580e63'
TREE = '659736e494be76de1d29e2e80972b126071e5cfe'
BASE = '00e2652c62ce6e34337d8f5bc3f3366b089c3d9c'
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
START = datetime.datetime.now(datetime.timezone.utc).isoformat()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, env=ENV)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob(path, ref=HEAD):
    return git('show', f'{ref}:{path}')


def inventory(ref):
    out = {}
    for row in git('ls-tree', '-r', '-z', ref).split(b'\0'):
        if not row:
            continue
        metadata, path = row.split(b'\t', 1)
        mode, kind, object_id = metadata.decode().split()
        out[path.decode()] = {'mode': mode, 'kind': kind, 'blob': object_id}
    return out


def file_record(path, inv):
    data = blob(path)
    return {'path': path, **inv[path], 'bytes': len(data), 'sha256': sha(data)}


def load_prior(name):
    data = (OUT / name).read_bytes()
    return json.loads(data), {'path': str(OUT / name), 'bytes': len(data), 'sha256': sha(data)}


def match_records(rows):
    out = []
    for row in rows:
        data = blob(row['path'])
        out.append({
            'path': row['path'], 'reviewed_bytes': row['bytes'],
            'reviewed_sha256': row['sha256'], 'final_bytes': len(data),
            'final_sha256': sha(data),
            'matches': len(data) == row['bytes'] and sha(data) == row['sha256'],
        })
    return out


def exclusive_json(path, obj):
    data = (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode()
    with path.open('xb') as handle:
        handle.write(data)
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}


status_before = git('status', '--porcelain=v1').decode()
actual_head = git('rev-parse', 'HEAD').decode().strip()
actual_tree = git('rev-parse', f'{HEAD}^{{tree}}').decode().strip()
actual_parent = git('rev-parse', f'{HEAD}^').decode().strip()
before, after = inventory(BASE), inventory(HEAD)
changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
docs = [p for p in changed if p.endswith('.md')]
source_runner = [p for p in changed if p not in docs]
changed_records = []
for p in changed:
    changed_records.append({
        **file_record(p, after),
        'change': 'modified' if p in before else 'added',
        'base_entry': before.get(p),
    })

production, production_receipt = load_prior('wip-production-review-01.json')
negative, negative_receipt = load_prior('wip-final-negative-source-check.json')
fixture, fixture_receipt = load_prior('fixture-fix-6004306-review.json')
wip, wip_receipt = load_prior('wip-core-03-independent-review.json')
diagnostic, diagnostic_receipt = load_prior('wip-fixture-diagnostic-01.json')
usage_path = fixture['source']['file']['path']
production_matches = match_records([r for r in production['source']['files'] if r['path'] != usage_path])
negative_matches = match_records(negative['source_files'] + negative['patch_checks'] + [negative['runner']])
fixture_match = match_records([fixture['source']['file']])[0]

guard_paths = [
    'kernel/asterinas/Cargo.lock',
    'kernel/asterinas/osdk/Cargo.lock',
    'kernel/asterinas/rust-toolchain.toml',
    'support/build/minimal/Cargo.lock',
    'kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs',
    'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs',
    'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/max_config.rs',
    'kernel/asterinas/ostd/src/sync/rcu/mod.rs',
    'libs/os-control/src/lib.rs',
    'libs/os-control/src/resource_state.rs',
    'libs/os-control/src/native.rs',
    'libs/os-abi/src/lib.rs',
]
guards = [{**file_record(p, after), 'unchanged_from_base': before[p] == after[p]} for p in guard_paths]
lock_paths = sorted(p for p in after if not p.startswith('results/') and (
    p.endswith('.lock') or pathlib.PurePosixPath(p).name in ('Cargo.toml', 'rust-toolchain.toml', 'rust-toolchain')))
locks = [{'path': p, **after[p], 'unchanged_from_base': before.get(p) == after[p]} for p in lock_paths]
subtrees = []
for p in ['support/build', '.github/workflows', 'kernel/asterinas/ostd', 'kernel/asterinas/osdk', 'libs/os-control', 'libs/os-abi']:
    base_tree = git('rev-parse', f'{BASE}:{p}').decode().strip()
    final_tree = git('rev-parse', f'{HEAD}:{p}').decode().strip()
    subtrees.append({'path': p, 'base_tree': base_tree, 'final_tree': final_tree, 'unchanged': base_tree == final_tree})

legacy = []
for p in source_runner:
    if not (p.endswith('_regressions.rs') or p.endswith('/native/tests.rs')):
        continue
    old, new = blob(p, BASE).decode(), blob(p).decode()
    names = lambda s: re.findall(r'#\[ktest(?:\([^]]*\))?\]\s*fn\s+(\w+)\(', s)
    legacy.append({
        'path': p, 'before_names': names(old), 'after_names': names(new),
        'names_equal': names(old) == names(new),
        'assert_calls_before': len(re.findall(r'\bassert(?:_eq|_ne)?!', old)),
        'assert_calls_after': len(re.findall(r'\bassert(?:_eq|_ne)?!', new)),
        'manual_diff_scope': 'Existing ns unit/field adaptations, original-clock test initialization, explicit initialization of new fields and formatting; existing assertion intent retained.',
    })
usage = blob(usage_path).decode()
usage_names = re.findall(r'#\[ktest\]\s*fn\s+(\w+)\(', usage)
runner_path = negative['runner']['path']
functions = lambda s: {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(s).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
runner_functions_equal = functions(blob(runner_path).decode()) == functions(blob(runner_path, '775061af51e6ee91fce290d5855e24a276292e14').decode())

links = []
for p in docs:
    text = blob(p).decode()
    for match in re.finditer(r'\]\(([^)\s]+)(?:\s+"[^"]*")?\)', text):
        url = match.group(1)
        if urllib.parse.urlsplit(url).scheme or url.startswith('#'):
            continue
        path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
        target = posixpath.normpath(posixpath.join(posixpath.dirname(p), path))
        links.append({'source': p, 'line': text[:match.start()].count('\n') + 1, 'url': url, 'target': target,
                      'exists': target in after or any(x.startswith(target + '/') for x in after)})
historical = []
for p in ['docs/ASTERINAS_CPU_OWNER_G1A.md', 'tests/organ_backend/CPU_BOOTTIME_CLOCK.md', 'tests/organ_backend/CPU_CLOCK_HANDOFF_CI.md']:
    old, new = blob(p, BASE).splitlines(keepends=True), blob(p).splitlines(keepends=True)
    historical.append({'path': p, 'only_two_line_scope_pointer_inserted_after_title': old == new[:2] + new[4:]})
technical = blob('docs/ASTERINAS_CPU_USAGE_G1B.md').decode()
four_ops_fixed = '| ReadUsage、InstallBudget、QueryDelivery、RetireThrough 四项用户态操作 | 本切片未开放 |' in technical
max_scope_fixed = '发生 `accounting_fault` 时有限 quota 拒绝' in technical and 'Closed、metadata Indeterminate 和 revision Overflow 仍由原写入 gate 拒绝' in technical
status_after = git('status', '--porcelain=v1').decode()

checks = {
    'head_exact': actual_head == HEAD,
    'tree_exact': actual_tree == TREE,
    'parent_exact': actual_parent == BASE,
    'worktree_clean_before_and_after': status_before == status_after == '',
    'exact_24_changed_paths_17_source_runner_7_docs': (len(changed), len(source_runner), len(docs)) == (24, 17, 7),
    'all_previously_reviewed_production_and_support_bytes_match': all(x['matches'] for x in production_matches),
    'all_four_negative_source_seven_patches_and_runner_match': all(x['matches'] for x in negative_matches),
    'usage_tests_exact_fixed_6004306_bytes': fixture_match['matches'],
    'usage_tests_exact_same_19_names': len(usage_names) == 19 and usage_names == fixture['test_names'],
    'all_legacy_test_names_retained': len(legacy) == 6 and all(x['names_equal'] for x in legacy),
    'all_legacy_assert_call_counts_retained': all(x['assert_calls_before'] == x['assert_calls_after'] for x in legacy),
    'negative_runner_all_functions_ast_unchanged': runner_functions_equal,
    'protected_authority_lifecycle_abi_and_lock_files_unchanged': all(x['unchanged_from_base'] for x in guards),
    'all_cargo_toolchain_lock_inventory_entries_unchanged': all(x['unchanged_from_base'] for x in locks),
    'build_workflow_ostd_osdk_control_abi_subtrees_unchanged': all(x['unchanged'] for x in subtrees),
    'all_301_local_link_occurrences_resolve_in_fixed_tree': len(links) == 301 and all(x['exists'] for x in links),
    'three_historical_documents_retain_original_body': all(x['only_two_line_scope_pointer_inserted_after_title'] for x in historical),
    'four_disabled_operations_documented_accurately': four_ops_fixed,
    'max_recovery_limited_to_accounting_fault_and_existing_metadata_gate': max_scope_fixed,
    'root_readme_zero_bytes': len(blob('README.md')) == 0,
}
blocking = [key for key, passed in checks.items() if not passed]
inputs = {
    'schema_version': 1, 'reviewer': '/root/r9_g1_contract', 'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source': {'repo': str(REPO), 'head': HEAD, 'tree': TREE, 'parent': BASE},
    'binding_method': 'git ls-tree -r -z plus raw git show bytes; mode/blob comparisons and SHA-256 over original Git file bytes. No target or downloaded executable read.',
    'changed_paths': changed_records, 'prior_production_matches': production_matches,
    'prior_negative_input_matches': negative_matches, 'fixed_fixture_match': fixture_match,
    'protected_files': guards, 'unchanged_subtrees': subtrees,
    'cargo_toolchain_lock_inventory': {'selection': 'Non-results Git paths ending .lock, or named Cargo.toml, rust-toolchain.toml, rust-toolchain; includes any historical inputs in other directories, not only active manifests.', 'count': len(locks), 'entries': locks},
    'legacy_test_identity': legacy, 'new_19_test_names': usage_names,
    'documentation_links': {'method': 'Markdown inline local target paths resolved against fixed Git tree; path existence, not anchors or remote URL status.', 'occurrences': len(links), 'unique_targets': len({x['target'] for x in links}), 'entries': links},
    'historical_body_checks': historical,
    'prior_receipts': [production_receipt, negative_receipt, fixture_receipt, wip_receipt, diagnostic_receipt],
}
inputs_id = exclusive_json(OUT / 'fixed-83e122d-inputs.json', inputs)
cpu = 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs'
native = 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native.rs'
sched = 'kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs'
clock = 'kernel/asterinas/kernel/core/comps/time/src/clocksource.rs'
source_conclusions = [
    {'topic': 'One original owner and units', 'locations': [f'{cpu}:67', f'{cpu}:198', f'{sched}:172'], 'conclusion': 'Original CpuMax budget/window/debt/cumulative values use calibrated absolute BOOTTIME ns; CurrentRuntime CFS/RT start/delta/period_delta remain cycles. The separate Option ns cursor only partitions already-owned execution. No second ResourceDomain or cumulative ledger.'},
    {'topic': 'No accounting refill or endpoint rewind', 'locations': [f'{cpu}:235', f'{cpu}:261', f'{native}:68', f'{sched}:189'], 'conclusion': 'Configuration and eligibility clamp to the owner high-water time before window mutation. N0 stale configuration/read and missing intervals fence; valid SMP late/overlapping positive charge is not rejected solely against a shared high-water endpoint. CFS cycle cursor separately keeps its maximum and counts only later suffixes.'},
    {'topic': 'Fault and Linux max recovery', 'locations': [f'{cpu}:198', f'{native}:68', f'{native}:97'], 'conclusion': 'Missing/reversed runtime intervals and cumulative overflow permanently retain accounting_fault. Finite quota and native samples remain refused. A max configuration can recover unlimited Linux scheduling only after existing metadata checks; detached, indeterminate metadata and revision overflow still reject. No production reset clears this history.'},
    {'topic': 'Complete fixed native window', 'locations': [f'{cpu}:261', f'{native}:97'], 'conclusion': 'Every real period change taints native observation until the next fixed 100 ms boundary; same-period writes do not clear the taint. Checked arithmetic failing to represent that boundary leaves None. Exact 100 ms finite cap <= period is required; Linux legal larger quota retains its existing saturating representation without gaining N0 qualification.'},
    {'topic': 'Coherent bounded observation', 'locations': [f'{native}:97', f'{native}:173'], 'conclusion': 'Private wrapper first requires exactly one CPU, settles at the original paired cut, verifies current RCU Arc identity under local IRQ exclusion, then copies identity/revision/cap/usage under original bandwidth lock. Invariants compare window use, cumulative use and elapsed absolute time. Events are explicitly 0/0 and user_paused false because producers are absent, not reliable event delivery.'},
    {'topic': 'Clock and locks', 'locations': [f'{clock}:183', f'{clock}:187', f'{sched}:81', f'{cpu}:351'], 'conclusion': 'Quiet accounting reads share original calibrated ClockSource/fault state without logging under runqueue. The new observation/configuration path adds no portable mutex, blocking, user-copy or heap allocation under runqueue/bandwidth locks. cpu.stat collects and releases its bandwidth guard before the first VmPrinter write. Existing owner/ancestor Arc retention and RCU publication ordering remain in force.'},
    {'topic': 'Initialization and authority', 'locations': [f'{cpu}:419', 'kernel/asterinas/kernel/core/comps/time/src/lib.rs:96', f'{native}:173', f'{native}:204'], 'conclusion': 'The sole production CpuControl constructor initializes all new fields; test reset helpers remain cfg(ktest). Once-only test initialization calls the original time_init only when original CLOCK is absent and does not reset a present source. HOS2 and os-control/ABI subtrees are byte-identical to base: trusted bootstrap and four resource operations remain unopened.'},
    {'topic': 'Actual retained lifecycle in fixtures', 'locations': [usage_path, 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs', 'kernel/asterinas/ostd/src/sync/rcu/mod.rs'], 'conclusion': 'Fixed 6004306 test bytes release runtime first, mark actual Process zombie, move to root retaining current lease, drop Process/TaskSet then final Task, and only then invoke unchanged mark_as_dead. No manual grace, EBUSY suppression, authority hook or production reset was introduced.'},
]
review = {
    'schema_version': 1, 'kind': 'fixed_git_g1b_source_and_documentation_review', 'reviewer': '/root/r9_g1_contract',
    'started_at_utc': START, 'completed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source': {'repo': str(REPO), 'head': HEAD, 'tree': TREE, 'parent': BASE, 'observed_worktree_status_before': status_before, 'observed_worktree_status_after': status_after, 'changed_paths': len(changed), 'source_runner_paths': len(source_runner), 'documentation_paths': len(docs)},
    'inputs_receipt': inputs_id, 'checks': checks, 'blocking': blocking,
    'identity_summary': {'prior_production_and_support_paths_identical': len(production_matches), 'negative_input_paths_identical': len(negative_matches), 'usage_test_sha256': fixture_match['final_sha256'], 'usage_tests': len(usage_names), 'legacy_test_names_preserved': sum(len(x['after_names']) for x in legacy), 'cargo_toolchain_lock_inventory_count': len(locks), 'local_link_occurrences': len(links), 'unique_local_targets': len({x['target'] for x in links})},
    'source_conclusions': source_conclusions,
    'resolved_findings': [
        {'id': 'G1B-WIP-R1', 'status': 'Corrected in reviewed fixed bytes', 'prior_receipt': production_receipt, 'issue': 'Stale reconfiguration could reopen an earlier bandwidth window and refill quota.', 'resolution': 'Effective monotonic configuration/eligibility cuts, N0-only stale-observation fencing, and per-runtime rather than globally shared interval ordering.'},
        {'id': 'G1B-FIXTURE-EBUSY', 'status': 'Original failure preserved; final test bytes equal reviewed real-lifecycle correction', 'prior_diagnostic': diagnostic_receipt, 'fixed_fixture_review': fixture_receipt, 'resolution': 'Correct object destruction order releases still-current original CPU lease before the unchanged deletion gate; no fabricated grace period.'},
        {'id': 'G1B-DOC-BOUNDARY', 'status': 'Both corrections present', 'resolution': 'Technical manual lists four disabled operations and confines max recovery to accounting_fault under existing metadata gate.'},
    ],
    'negative_control_scope': {'count': 7, 'expected_failure_counts': [3, 4, 3, 1, 4, 1, 2], 'prior_apply_check': negative_receipt, 'prior_applicability_remains_bound_by_exact_bytes': True, 'all_runner_function_asts_unchanged': runner_functions_equal, 'actual_negative_guest_qualification_at_this_review': 'Not supplied or asserted; seven complete failures and restored candidate still need their own receipts.'},
    'runtime_evidence_boundary': {'independent_wip_core_review': wip_receipt, 'actual_observation': 'Dirty WIP core03: 220 declared/unique/passed, 0 failed/filtered/core soft skips, exact 19 usage names, raw QEMU 33, no timeout, serial 27372 B SHA ab7ae20b3dafef9250d74e829fed703698f673061d47950eaa8e96fb12ef705e.', 'scope': 'This successful development run belongs to base 00e2652c with 17 dirty/untracked paths, not this final clean commit. Its 118-file upstream input check is not a complete atomic dirty-source snapshot. Raw OSDK exit 0 and result passed were retained; the enclosing host-process 0 was parent-reported, not separately re-observed by this reviewer.', 'final_commit_runtime_claim': False},
    'remaining_boundaries': [
        'Final same-candidate complete core/OSTD, seven full production controls, ordinary product/Linux workloads, CPU quota/configuration and exact remote CI still require distinct actual execution receipts.',
        'The kernel regressions use actual unstarted Process/Task/controller objects and controlled clock endpoints; they do not by themselves qualify ordinary live workload observation, physical context-switch atomicity, remote CPU rendezvous or full SMP.',
        'Late intervals from an already-ended shared window, migration/IRQ/IPI/hotplug, suspend/resume and strict scheduling error bounds remain outside this slice.',
        'No trusted Process/exec authority, public ReadUsage grant, InstallBudget, QueryDelivery or RetireThrough effect is opened; no native event stream, Hepta K-to-D delivery or device/mobile qualification is claimed.',
        'config_regressions retains its existing assertion field subset; source ordering still parses invalid input before mutation. This review does not describe that legacy test alone as exhaustive coverage of every new field.',
    ],
    'activities': {'cargo_or_rust_invocations': 0, 'qemu_or_guest_invocations': 0, 'fixture_executions_in_this_final_review': 0, 'product_source_edits': 0, 'active_target_reads': 0, 'git_mutations': 0, 'remote_writes': 0},
    'prior_evidence_policy': 'Original WIP source review, initial failed run/diagnostic, corrected fixture review and WIP successful serial review are retained byte-for-byte. This receipt binds final source; it does not rewrite historical identities or promote WIP runs.',
}
review_id = exclusive_json(OUT / 'fixed-83e122d-source-review.json', review)
print(json.dumps({'review': review_id, 'inputs': inputs_id, 'blocking': blocking, 'checks_passed': sum(checks.values()), 'checks_total': len(checks)}, ensure_ascii=False, indent=2))
raise SystemExit(1 if blocking else 0)
