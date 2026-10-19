#!/usr/bin/env python3
"""Freeze a read-only documentation/source identity review of published G1-c."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/workspace/scratch/499c7902de8e/r12-g1c')
EVIDENCE = ROOT.parent / 'r12-evidence'
OUT = EVIDENCE / 'g1c-review' / 'docs-review-72c8dff3.json'
HEAD = '72c8dff3f0145a7e16b7095d48a3e7faaf192685'
TREE = 'e2089e2350772a6cb965b3131820abea499f767d'
BASE = '7c675e1d3efe46587edeebe14bd90ac1a842ffbf'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


assert git('rev-parse', 'HEAD').decode().strip() == HEAD
assert git('rev-parse', 'HEAD^{tree}').decode().strip() == TREE
assert git('status', '--porcelain=v1') == b''
entries = {}
for raw in git('ls-tree', '-r', '-z', HEAD).split(b'\0'):
    if not raw:
        continue
    metadata, path = raw.split(b'\t', 1)
    mode, kind, oid = metadata.decode().split()
    entries[path.decode()] = {'mode': mode, 'kind': kind, 'git_blob': oid}


def file_identity(relative):
    p = ROOT / relative
    data = p.read_bytes()
    item = {'path': relative, 'bytes': len(data), 'sha256': sha(data), **entries[relative]}
    assert blob(data) == item['git_blob'], relative
    observed_mode = '100755' if p.stat().st_mode & 0o111 else '100644'
    assert observed_mode == item['mode'], relative
    return item


prior_path = EVIDENCE / 'g1c-review' / 'implementation-review-v1.json'
prior_bytes = prior_path.read_bytes()
assert sha(prior_bytes) == 'd44abb50df776517e7a05dbffb6da30b03974e355c2b6586950ff40615cbd3b6'
prior = json.loads(prior_bytes)
source_groups = {}
for group in ('source_files', 'additional_reviewed_files', 'preserved_call_path_inputs'):
    source_groups[group] = []
    for old in prior[group]:
        current = file_identity(old['path'])
        assert all(current[key] == old[key] for key in ('bytes', 'sha256', 'git_blob')), old['path']
        source_groups[group].append({**current, 'matches_prior_review': True})

docs = ['docs/ASTERINAS_PROCESS_IMAGE_G1C.md',
        'tests/kernel/control/PROCESS_IMAGE_G1C.md',
        'docs/INDEX.md', 'docs/STATUS.md']
doc_inputs = []
local_links = []
for relative in docs:
    item = file_identity(relative)
    text = (ROOT / relative).read_text()
    item['line_count'] = len(text.splitlines())
    if relative in docs[:2]:
        reviewed = text
        item['content_review_scope'] = 'full document'
    else:
        diff = git('diff', '--unified=0', BASE, HEAD, '--', relative).decode()
        reviewed = '\n'.join(line[1:] for line in diff.splitlines()
                             if line.startswith('+') and not line.startswith('+++'))
        item['content_review_scope'] = 'all added lines against base; historical prose retained without new qualification'
    item['reviewed_text_sha256'] = sha(reviewed.encode())
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', reviewed):
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('#'):
            continue
        clean_target = target.split('#', 1)[0]
        resolved = (ROOT / relative).parent.joinpath(clean_target).resolve()
        resolved_relative = str(resolved.relative_to(ROOT))
        assert resolved.is_file(), (relative, target)
        assert resolved_relative in entries, (relative, target)
        local_links.append({'from': relative, 'target': target,
                            'resolved_path': resolved_relative,
                            'exists_at_reviewed_commit': True})
    doc_inputs.append(item)

manual = (ROOT / docs[1]).read_text()
test_names = []
for relative in ['kernel/asterinas/kernel/core/src/process/process/image.rs',
                 'kernel/asterinas/kernel/core/src/process/process/init_proc.rs']:
    names = re.findall(r'#\[ktest\]\s*fn\s+(\w+)\s*\(', (ROOT / relative).read_text())
    assert len(names) == 9
    for name in names:
        assert manual.count('`' + name + '`') == 1, name
        test_names.append({'path': relative, 'name': name})
assert test_names == prior['kernel_test_source_inventory']

host_results = []
host_summary_path = EVIDENCE / 'local-host' / 'summary.json'
host_summary = json.loads(host_summary_path.read_bytes())
for name in ('spec.log', 'control.log', 'control-optimized.log'):
    data = (host_summary_path.parent / name).read_bytes()
    expected = host_summary[name]
    assert sha(data) == expected['sha256']
    count = re.search(rb'^Ran (\d+) tests in ([0-9.]+)s$', data, re.M)
    assert count and int(count.group(1)) == expected['tests']
    assert re.search(rb'^OK$', data, re.M)
    candidate_names = re.findall(rb'^test_.*\(test_queryabi_candidate_runner\.[^)]+\) \.\.\. ok$', data, re.M)
    if name != 'spec.log':
        assert len(candidate_names) == 8
    host_results.append({'path': 'local-host/' + name, 'bytes': len(data),
                         'sha256': sha(data), 'reported_tests': int(count.group(1)),
                         'candidate_source_and_parser_tests': len(candidate_names),
                         'recorded_result': 'OK',
                         'review_activity': 'existing raw host log inspected; not rerun'})

probe_dir = EVIDENCE / 'probe-preflight-old-4d3011cf'
probe_bytes = (probe_dir / 'result.json').read_bytes()
probe = json.loads(probe_bytes)
serial = (probe_dir / 'serial.log').read_bytes()
acceptance = probe['acceptance']
assert len(serial) == acceptance['raw_serial_size']
assert sha(serial) == acceptance['raw_serial_sha256']
assert type(probe['raw_exit_code']) is int and probe['raw_exit_code'] == 33
assert probe['timed_out'] is False
lines = serial.decode(errors='strict').replace('\r\n', '\n').splitlines()
markers = acceptance['marker_counts']
assert len(markers) == 18
counts = {marker: lines.count(marker) for marker in markers}
assert set(counts.values()) == {1}
assert counts == markers
for relative, expected_sha in probe['source_inputs'].items():
    assert sha((ROOT / relative).read_bytes()) == expected_sha
probe_inputs = []
for name, expected in probe['inputs'].items():
    data = (probe_dir / name).read_bytes()
    assert len(data) == expected['size'] and sha(data) == expected['sha256']
    probe_inputs.append({'path': 'probe-preflight-old-4d3011cf/' + name,
                         'bytes': len(data), 'sha256': sha(data)})

out = {
    'schema_version': 1,
    'kind': 'independent_g1c_published_documentation_review',
    'reviewer': '/root/g1c_review',
    'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'source_head': HEAD, 'source_tree': TREE, 'base_head': BASE,
    'working_tree_clean': True,
    'decision': 'No blocking factual, local-link or qualification-scope defect found in the four reviewed documentation additions. This review does not establish any new kernel build or runtime qualification.',
    'blocking_findings': [],
    'documentation_inputs': doc_inputs,
    'local_links': local_links,
    'local_link_count': len(local_links),
    'unique_local_target_count': len({link['resolved_path'] for link in local_links}),
    'prior_source_review': {'path': 'g1c-review/implementation-review-v1.json',
                            'bytes': len(prior_bytes), 'sha256': sha(prior_bytes)},
    'reviewed_source_identity_continuity': source_groups,
    'verified_test_inventory': test_names,
    'qualification_scope_checks': [
        'The 18 new ktests are described as actual unstarted Process/VMAR/Task object cases; no exec/exit syscall fixture or loaded fixture execution is claimed.',
        '220 plus 18 gives expected 238 core cases; the new product actual denominator, complete results and filters must still be checked in its raw serial.',
        'Historical OSTD 221 reported includes three VMX soft skips; all 221 are not relabeled as executed.',
        'Task VMAR provenance is attributed to the same private factory chain, not to an inaccessible unstarted Task ThreadLocal inspection.',
        'Initial locking is VMAR -> TaskSet -> image; no new reverse TaskSet -> VMAR order is asserted.',
        'EFAULT/ENOENT guest cases are pre-boundary failures; non-last-thread survival is distinguished from final Process exit and fatal post-boundary exec.',
        'Prepared resume claims before PID/session publication and scheduling; Process first-run state is not reset by exec.',
        'The four resource operations remain EOPNOTSUPP and QueryAbi remains the sole advertised operation.',
        'Current image admission before user copy is not claimed to provide future canonical grant revoke/effect linearization.',
        'Next static ELF trust requires actual immutable mapping bytes, proc-mem retained handles, ptrace writes, forced alien fault/COW and cross-Process CLONE_VM policy before native grant admission.',
        'CPU owner retention and final debit are preserved; the same original owner synchronization is still required for future resource operations.',
        'INDEX retains the R11 62-entry count as historical; neither the new manuals nor INDEX/STATUS grant SMP, Android, physical-device or complete Hepta authority qualification.',
    ],
    'existing_host_log_support': host_results,
    'existing_old_product_probe_support': {
        'record_path': 'probe-preflight-old-4d3011cf/result.json',
        'record_bytes': len(probe_bytes), 'record_sha256': sha(probe_bytes),
        'kernel_source_head': probe['old_kernel_source_head'],
        'scope': probe['scope'],
        'recorded_raw_exit_code': probe['raw_exit_code'],
        'recorded_timed_out': probe['timed_out'],
        'recorded_elapsed_seconds': probe['elapsed_seconds'],
        'serial_bytes': len(serial), 'serial_sha256': sha(serial),
        'independently_counted_exact_line_markers': counts,
        'input_files_verified': probe_inputs,
        'review_activity': 'existing receipt, serial and file bytes inspected; QEMU not rerun',
    },
    'activities': {
        'product_source_modified': False, 'kernel_builds': 0,
        'product_test_runs': 0, 'host_test_reruns': 0,
        'remote_reads': 0, 'remote_writes': 0, 'ci_polling': 0,
        'toolchain_installations': 0,
    },
    'pending_separate_review': 'Original A06 artifact/source/core/OSTD acceptance for the fixed 72c8 product; no current run status asserted here.',
}
assert git('status', '--porcelain=v1') == b''
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
saved = OUT.read_bytes()
print(json.dumps({'path': str(OUT), 'bytes': len(saved), 'sha256': sha(saved),
                  'links': len(local_links), 'source_inputs_unchanged': sum(map(len, source_groups.values())),
                  'new_ktest_names': len(test_names), 'blocking_findings': 0}, ensure_ascii=False))
