#!/usr/bin/env python3
"""New post-maintenance Git review. Never recreates old JSON or runs a product."""
import ast
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import urllib.parse

ROOT = Path('/workspace/scratch/499c7902de8e')
REPO = ROOT / 'r11-g1b-usage'
OUT = ROOT / 'r11-evidence/g1b-review'
HEAD = 'f9669912e2886190429187e14753d62b2060bd5f'
BASE = '00e2652c62ce6e34337d8f5bc3f3366b089c3d9c'
TREE = '659736e494be76de1d29e2e80972b126071e5cfe'
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
START = datetime.datetime.now(datetime.timezone.utc).isoformat()
CPU = 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu'
SCHED = 'kernel/asterinas/kernel/core/src/sched/sched_class'
TIME = 'kernel/asterinas/kernel/core/comps/time/src'
TEST = 'tests/organ_backend'

# Expected byte identities below survive in the original tool outputs and final
# review message. They are not reconstructed original JSON receipts.
EXPECTED = {
    CPU + '.rs': 'b78cf58b0dabd34b3055748d4fc8a7e59ce37d90d092b32b72e06fee8814c4d0',
    CPU + '/native.rs': '1f7fb0e3e3129cc29b62d6ac0858d9e74716575e435d635c353f45b99cca6c2c',
    CPU + '/native/usage_tests.rs': '9199dee49d804bb3b217a417362ed78043bcb6ae7a23f3bb29191d8f7c304dcb',
    SCHED + '/mod.rs': '6b0cc85db8c868d9342ce4179f94fa1825420f30d6e8e7e2117495912e64e667',
    SCHED + '/clock.rs': '3fb6e0f2489d6b46af702626e68a9734a0ecb334211425b0511790822362988f',
    TIME + '/clocksource.rs': 'e780c0fcf590796482a3610bcf2f0a82ac220ea8770b7cc6dd89da0e056665cb',
    TIME + '/lib.rs': '637eb2ef32c33cf387cb583fd79a319f6fe89c68682652d2b7fb1bca3175d1e1',
    'kernel/asterinas/kernel/core/src/vdso.rs': '344c56cfcaf752ef68f1325f4f12ab9332189937d7873d3d30c2c8a75e043ac4',
    TEST + '/cpu_owner_current_slot_negative.patch': '04b19a7a89b8f8591d9a18766390167201e999a9617febcd9d0c70902005f1bd',
    TEST + '/clocksource_drop_fraction_negative.patch': '6aeb53178b4facbe105c7fd4ff3e8086d5a9b57f2715f80781efc2764338a442',
    TEST + '/vdso_drop_fraction_negative.patch': 'a1e116c7af6a57add22693b4fa985b8bb45809df3ad6765b52ea8efa979975c9',
    TEST + '/vdso_skip_fault_mode_negative.patch': 'da1f7c360136bfe330cba58acef4cf894d423043e1b3b9790958b923d4fcd452',
    TEST + '/cpu_handoff_drop_tail_negative.patch': '2e9a87cdf9044f29dbcb8c932e72079eaf3fc9ecde791c9627b45b9b06257ffc',
    TEST + '/cpu_handoff_eligibility_first_negative.patch': '8a90266278c3610c337e9ce780130e3a179ccce6942bbd4db05c53cfd805546c',
    TEST + '/cpu_dequeue_drop_owner_negative.patch': 'b6fc10180e9fe292249409c758151763401dddb39bb4b2851bf53f71b3c959dd',
    TEST + '/run_cpu_owner_negative.py': '2433f1b130997fbbb6b5e0dd4af67e994babae97aac334df33abf0e369c3fbc4',
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, env=ENV)


def get(path, ref=HEAD):
    return git('show', ref + ':' + path)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(ref):
    entries = {}
    for item in git('ls-tree', '-rz', ref).split(b'\0'):
        if item:
            metadata, path = item.split(b'\t', 1)
            mode, kind, obj = metadata.decode().split()
            entries[path.decode()] = dict(mode=mode, kind=kind, blob=obj)
    return entries


before, after = inventory(BASE), inventory(HEAD)
changed = [p for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)]
docs = [p for p in changed if p.endswith('.md')]
bindings = []
for path, expected in EXPECTED.items():
    data = get(path)
    bindings.append(dict(path=path, bytes=len(data), sha256=digest(data), historical_expected_sha256=expected, matches=digest(data) == expected))
changes = []
for path in changed:
    data = get(path)
    changes.append(dict(path=path, **after[path], bytes=len(data), sha256=digest(data), base_entry=before.get(path)))
lock_paths = [p for p in sorted(after) if not p.startswith('results/') and (p.endswith('.lock') or PurePosixPath(p).name in ('Cargo.toml', 'rust-toolchain.toml', 'rust-toolchain'))]
locks = [dict(path=p, **after[p], unchanged=before.get(p) == after[p]) for p in lock_paths]
subtrees = []
for p in ['support/build', '.github/workflows', 'kernel/asterinas/ostd', 'kernel/asterinas/osdk', 'libs/os-control', 'libs/os-abi']:
    old, new = [git('rev-parse', f'{r}:{p}').decode().strip() for r in [BASE, HEAD]]
    subtrees.append(dict(path=p, base_tree=old, candidate_tree=new, unchanged=old == new))
guard_paths = ['kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs', 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs', CPU + '/max_config.rs', 'kernel/asterinas/ostd/src/sync/rcu/mod.rs']
guards = [dict(path=p, **after[p], unchanged=before[p] == after[p]) for p in guard_paths]
legacy = []
names = lambda data: re.findall(r'#\[ktest(?:\([^]]*\))?\]\s*fn\s+(\w+)\(', data.decode())
for p in changed:
    if p.endswith('_regressions.rs') or p.endswith('/native/tests.rs'):
        old, new = get(p, BASE), get(p)
        legacy.append(dict(path=p, before_names=names(old), after_names=names(new), names_equal=names(old) == names(new), before_asserts=len(re.findall(rb'\bassert(?:_eq|_ne)?!', old)), after_asserts=len(re.findall(rb'\bassert(?:_eq|_ne)?!', new))))
usage_names = names(get(CPU + '/native/usage_tests.rs'))
function_asts = lambda data: {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(data.decode()).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
runner_equal = function_asts(get(TEST + '/run_cpu_owner_negative.py', BASE)) == function_asts(get(TEST + '/run_cpu_owner_negative.py'))
links = []
for p in docs:
    text = get(p).decode()
    for m in re.finditer(r'\]\(([^)\s]+)(?:\s+"[^"]*")?\)', text):
        url = m.group(1)
        if urllib.parse.urlsplit(url).scheme or url.startswith('#'):
            continue
        path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
        target = posixpath.normpath(posixpath.join(posixpath.dirname(p), path))
        links.append(dict(source=p, line=text[:m.start()].count('\n') + 1, target=target, exists=target in after or any(x.startswith(target + '/') for x in after)))
historical = []
for p in ['docs/ASTERINAS_CPU_OWNER_G1A.md', TEST + '/CPU_BOOTTIME_CLOCK.md', TEST + '/CPU_CLOCK_HANDOFF_CI.md']:
    old, new = get(p, BASE).splitlines(keepends=True), get(p).splitlines(keepends=True)
    historical.append(dict(path=p, original_body_retained=old == new[:2] + new[4:]))
technical = get('docs/ASTERINAS_CPU_USAGE_G1B.md').decode()
checks = dict(
    exact_remote_tree=git('rev-parse', HEAD + '^{tree}').decode().strip() == TREE,
    exact_parent=git('rev-parse', HEAD + '^').decode().strip() == BASE,
    exact_24_paths_and_7_docs=len(changed) == 24 and len(docs) == 7,
    all_16_retained_historical_source_hashes_match=all(x['matches'] for x in bindings),
    fixed_usage_file_35603_bytes=len(get(CPU + '/native/usage_tests.rs')) == 35603,
    nineteen_distinct_usage_test_names=len(usage_names) == len(set(usage_names)) == 19,
    thirty_two_legacy_names_preserved=sum(len(x['after_names']) for x in legacy) == 32 and all(x['names_equal'] for x in legacy),
    legacy_assert_counts_preserved=all(x['before_asserts'] == x['after_asserts'] for x in legacy),
    all_runner_functions_match_parent=runner_equal,
    all_168_lock_manifest_toolchain_inputs_unchanged=len(locks) == 168 and all(x['unchanged'] for x in locks),
    build_workflow_ostd_osdk_control_abi_subtrees_unchanged=all(x['unchanged'] for x in subtrees),
    lifecycle_hos2_and_parser_unchanged=all(x['unchanged'] for x in guards),
    all_301_links_resolve=len(links) == 301 and all(x['exists'] for x in links),
    three_original_historical_bodies_retained=all(x['original_body_retained'] for x in historical),
    four_disabled_operations_correct='| ReadUsage、InstallBudget、QueryDelivery、RetireThrough 四项用户态操作 | 本切片未开放 |' in technical,
    max_recovery_scope_correct='发生 `accounting_fault` 时有限 quota 拒绝' in technical and 'Closed、metadata Indeterminate 和 revision Overflow 仍由原写入 gate 拒绝' in technical,
    root_readme_zero_bytes=len(get('README.md')) == 0,
)
report = dict(
    schema_version=1, kind='new_post_maintenance_fixed_git_review', reviewer='/root/r9_g1_contract',
    started_at_utc=START, completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    source=dict(repo=str(REPO), commit=HEAD, tree=TREE, parent=BASE, git_only=True),
    recovery_scope='This is a newly generated review. Old JSON bytes are missing. Source hashes below were retained in original conversation tool outputs and compared to newly read fixed Git bytes. The original 20246-byte script alone was exactly recovered; it was not executed.',
    checks=checks, blocking=[k for k, v in checks.items() if not v],
    changed_files=changes, retained_historical_bindings=bindings, usage_test_names=usage_names, legacy_test_names=legacy,
    protected_files=guards, unchanged_subtrees=subtrees,
    lock_inventory=dict(selection='Non-results paths ending .lock or named Cargo.toml/rust-toolchain.toml/rust-toolchain, including historical inputs outside results.', count=len(locks), entries=locks),
    local_links=dict(method='Inline Markdown local target path existence in fixed Git tree; remote URLs and fragment anchors are not checked.', occurrences=len(links), unique_targets=len({x['target'] for x in links}), entries=links),
    historical_document_checks=historical,
    historical_conclusions=dict(original_local_source='83e122d40e5427f84efebb4b7a224f7131580e63', original_reported_tree=TREE, original_reported_blocking=[], original_report_bytes_available=False, bounded_source_conclusion='The reread immutable tree and 16 retained byte identities preserve the reviewed ns/cycles split, same-owner snapshot and fixture correction. This review confirms source identity and static contracts, not a newly run kernel.', wip_runtime='Prior messages reported core03 220/220, raw QEMU33, serial SHA ab7ae20b3dafef9250d74e829fed703698f673061d47950eaa8e96fb12ef705e on dirty WIP. Those original local runtime bytes were not recovered and are not revalidated here.'),
    qualification_limits=['The exact PR205 head needs its own real A06 artifact; none is declared passed by this source review.', 'A descendant host-fixture fix needs its own commit and CI identity even if production bytes remain unchanged.', 'No trusted-init/Process authority or four HOS2 resource operations are opened. Same-CPU private observation does not prove full SMP, physical switch atomicity, Hepta K-to-D delivery or device support.'],
    activities=dict(cargo_rust_qemu_invocations=0, product_source_edits=0, remote_writes=0, old_script_execution=0),
)
path = OUT / 'recovered-f966-source-review.json'
data = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
with path.open('xb') as handle:
    handle.write(data)
print(json.dumps(dict(path=str(path), bytes=len(data), sha256=digest(data), checks_passed=sum(checks.values()), checks_total=len(checks), blocking=report['blocking'])))
raise SystemExit(1 if report['blocking'] else 0)
