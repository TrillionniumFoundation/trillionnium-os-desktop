from pathlib import Path
import ast, hashlib, json

root = Path(__file__).resolve().parent
prior = (root/'base-support/lint_transition.py').read_text()
assert hashlib.sha256(prior.encode()).hexdigest() == '5efb6374609c59dfacff7d0c2bce4d940ea216c84cfb4222ac29c4d4856e237e'
tree = ast.parse(prior)
node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'VerifiedInventory')
inventory = ast.get_source_segment(prior, node)
provider_evidence = json.loads((root.parent/'p4_vendor_apex_source_fix/evidence/GIT-COMPLETE-PROVIDERS.json').read_text())
assert provider_evidence['status']['exit_code'] == 0 and provider_evidence['output_complete'] is True
observed = json.loads(provider_evidence['text'])
old_raw = (root.parent/'p4_vendor_apex_source_fix/base/android/manifest/production-full-lint-source-lock.json').read_bytes()
assert hashlib.sha256(old_raw).hexdigest() == 'aa14d968c14c2febcfacbb90e82598e2ba8e57f4bbb2cfc8f1f2a741555153ca'
old_lock = json.loads(old_raw)
providers, candidates = {}, {}
for item in observed:
    row = next(p for p in old_lock['projects'] if p['path'] == item['project'])
    assert item['commit'] == row['commit'] and item['cone'] not in row['sparse_paths']
    providers[item['project']] = {
        'commit': item['commit'], 'url': 'https://android.googlesource.com/' + row['name'],
        'cone': item['cone'], 'original_cones': len(row['sparse_paths']),
    }
    for file in item['files']:
        b = file['text'].encode()
        assert len(b) == file['bytes'] and hashlib.sha256(b).hexdigest() == file['sha256']
        assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest() == file['git_blob']
        assert file['mode'] == '100644'
        candidates[(item['project'], file['path'])] = (file['git_blob'], file['bytes'], file['sha256'])
assert len(providers) == 2 and len(candidates) == 4
assert sum(v[1] for v in candidates.values()) == 2186
header = '''#!/usr/bin/python3
"""Exact complete/partial source predicates for four original APEX providers.

No writer, launcher, retry or runtime authority is exposed. The controller must
hold the original serial lock and budgets, bind both real normal CLI plans, and
validate the immutable R21 final recovery before using these predicates.
"""
from itertools import zip_longest
from pathlib import Path
import hashlib
import os
import stat
import time

OLD_LOCK_SHA = 'aa14d968c14c2febcfacbb90e82598e2ba8e57f4bbb2cfc8f1f2a741555153ca'
NEW_LOCK_SHA = '14fd227541b01876c7e34d7e6a1ffcb2a202d97d94c6a8f6e14be369e4b79505'
OLD_MANIFEST_SHA = 'cb140d8937176a4e20fb5059830d3774f930aafb45c3cc7f88423b7b2d16d152'
TRACKED_MEMBERS = 1045300
'''
body = '''

def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def validate_profiles(bookends, old, new):
    old, new = bookends.normalized_manifest(old), bookends.normalized_manifest(new)
    need(old['source_lock_sha256'] == OLD_LOCK_SHA
         and new['source_lock_sha256'] == NEW_LOCK_SHA, 'exact old lint and new APEX provider locks')
    before, after = old['plan'], new['plan']
    need(len(before['projects']) == len(after['projects']) == 652
         and len(before['links']) == 8, 'same full 652 project scope and eight root links')
    need({k: v for k, v in before.items() if k != 'projects'}
         == {k: v for k, v in after.items() if k != 'projects'}, 'root links or superproject changed')
    found = set()
    for a, b in zip(before['projects'], after['projects']):
        provider = PROVIDERS.get(a['path'])
        if provider is None:
            need(a == b, 'unrelated original project or order changed')
            continue
        need(a['path'] not in found, 'duplicate original APEX provider')
        found.add(a['path'])
        need(a['commit'] == provider['commit'] and a['url'] == provider['url']
             and len(a['sparse_paths']) == provider['original_cones']
             and provider['cone'] not in a['sparse_paths'], 'exact original APEX provider and cones')
        need(b == {**a, 'sparse_paths': a['sparse_paths'] + [provider['cone']]},
             'only append each complete original APEX provider directory')
    need(found == set(PROVIDERS), 'both original APEX provider projects required')
    return old, new


def recovery_branch(bookends, actual, old, new, reconcile_intent, vendor_intent, resume_intent):
    old, new = validate_profiles(bookends, old, new)
    actual = bookends.normalized_manifest(actual)
    need(all(type(v) is bool for v in (reconcile_intent, vendor_intent, resume_intent)),
         'actual source-stage presence booleans required')
    need(not vendor_intent or reconcile_intent, 'Vendor cannot precede original source intent')
    need(not resume_intent or reconcile_intent, 'resume cannot precede original source intent')
    if actual == old:
        need(not vendor_intent, 'Vendor intent contradicts the old lint manifest')
        if not reconcile_intent:
            return 'old652-before-reconcile-dispatch'
        need(not resume_intent, 'old manifest after this recovery resume is unresolved; no retry')
        return 'old652-dispatched-requires-partial-bookend-before-one-normal-resume'
    if actual == new:
        need(reconcile_intent, 'new APEX provider manifest lacks this owner original intent')
        return 'new652-apex-tests-atomic-manifest-published'
    raise RuntimeError('manifest matches neither complete fixed normal profile')


def _candidate(row, key, missing_allowed):
    need(type(key) is tuple and key in CANDIDATES and type(missing_allowed) is bool,
         'exact fixed candidate and presence mode')
    oid, size, sha = CANDIDATES[key]
    base = {'project': key[0], 'path': key[1], 'git_mode': '100644', 'git_blob': oid}
    if row.get('present') is False:
        need(missing_allowed and row == {**base, 'present': False, 'sparse_skip': True, 'f9': None},
             'only a complete original S-absent APEX provider tuple is allowed')
        return False
    need(set(row) == set(base) | {'present', 'bytes', 'sha256', 'mode', 'f9'}
         and all(row[k] == v for k, v in base.items())
         and row['present'] is True and type(row['bytes']) is int and row['bytes'] == size
         and row['sha256'] == sha, 'APEX provider must be its exact original raw Git blob')
    identity = row['f9']
    need(type(identity) is list and len(identity) == 9
         and all(type(v) is int for v in identity)
         and identity[0] > 0 and identity[1] > 0
         and stat.S_ISREG(identity[2]) and identity[2] & 0o111 == 0
         and identity[3:6] == [1000, 1000, 1] and identity[6] == size
         and type(row['mode']) is int and row['mode'] == stat.S_IMODE(identity[2]),
         'new provider must be an ordinary same-account non-executable original inode')
    return True


def compare_rows(before_rows, after_rows, *, allow_partial, expected_count):
    need(type(allow_partial) is bool and type(expected_count) is int and expected_count >= 4,
         'explicit complete or partial comparison scope')
    before_iter, after_iter = iter(before_rows), iter(after_rows)
    try:
        return _compare_rows(before_iter, after_iter, allow_partial, expected_count)
    finally:
        for stream in (before_iter, after_iter):
            close = getattr(stream, 'close', None)
            if close is not None:
                close()


def _compare_rows(before_rows, after_rows, allow_partial, expected_count):
    missing = object()
    seen = set()
    count = added = added_bytes = identity_changes = 0
    for a, b in zip_longest(before_rows, after_rows, fillvalue=missing):
        need(a is not missing and b is not missing, 'complete source inventory membership differs')
        need(type(a) is dict and type(b) is dict, 'full source row objects')
        key = (a.get('project'), a.get('path'))
        need(key == (b.get('project'), b.get('path')), 'original source row order or identity differs')
        count += 1
        need(count <= expected_count, 'source inventory exceeds fixed full roster')
        if key in CANDIDATES:
            need(key not in seen, 'duplicate original APEX provider member')
            seen.add(key)
            need(_candidate(a, key, True) is False,
                 'this transition requires the actual four original absent provider members')
            present = _candidate(b, key, allow_partial)
            if present:
                added += 1
                added_bytes += b['bytes']
        else:
            need({k: v for k, v in a.items() if k != 'f9'}
                 == {k: v for k, v in b.items() if k != 'f9'},
                 'original unrelated source tuple, mode, content or representation changed')
            identity_changes += a.get('f9') != b.get('f9')
    need(count == expected_count and seen == set(CANDIDATES), 'incomplete exact source/provider roster')
    need(allow_partial or (added == 4 and added_bytes == 2186), 'all four original provider bodies required')
    return {'schema': 'p4-r22-four-original-apex-provider-content-comparison-v1',
            'tracked_members_compared': count, 'original_provider_members': 4,
            'provider_materialized': added, 'provider_remaining_absent': 4 - added,
            'provider_raw_bytes_materialized': added_bytes,
            'all_other_original_tuples_identical': True,
            'non_provider_identity_changes': identity_changes,
            'partial_recovery_admission_only': allow_partial,
            'source_recovery_complete': False, 'Vendor_build_credit': False}
'''
tail = '''


class VerifiedPartialInventory(VerifiedInventory):
    """Independent old/new cone state for both original provider projects."""
    def __init__(self, bookends, summary, old, new, deadline, guard):
        self.old, self.new = validate_profiles(bookends, old, new)
        states = summary['actual_provider_cone_profiles']
        need(type(states) is dict and set(states) == set(PROVIDERS)
             and all(state in ('old', 'new') for state in states.values()),
             'both actual fixed provider cone observations')
        replacement = {p['path']: p for p in self.new['plan']['projects']}
        projects = [replacement[p['path']] if states.get(p['path']) == 'new' else p
                    for p in self.old['plan']['projects']]
        super().__init__(bookends, summary, projects, deadline, guard)

    def _validate_summary(self):
        b, s = self.bookends, self.summary
        need(s['schema'] == 'p4-r22-incomplete-apex-provider-recovery-diagnostic-v1'
             and s['strict_complete_source_verified'] is False
             and s['recovery_admission_only'] is True
             and s['source_recovery_complete'] is False
             and s['profile_contract_validated'] is True
             and s['all_actual_Git_blob_reads_verified'] is True
             and s['all_tracked_filter_queries_complete'] is True
             and s['custom_filters_executed'] is False and s['source_mutations'] is False
             and s['production_ready'] is False and s['runtime_qualified'] is False
             and s['project_count'] == len(self.projects) == 652
             and [v['project'] for v in s['projects']] == self.projects,
             'explicit complete diagnostic roster without strict-complete source credit')
        need(s['original_manifest']['sha256'] == OLD_MANIFEST_SHA
             and s['old_manifest_semantic_sha256'] == hashlib.sha256(b.encoded(self.old)).hexdigest()
             and s['new_manifest_semantic_sha256'] == hashlib.sha256(b.encoded(self.new)).hexdigest(),
             'exact original old manifest and both distinct plans')
        all_attrs = s['provider_checkout_attributes']
        need(type(all_attrs) is dict and set(all_attrs) == set(PROVIDERS),
             'both original provider attribute observations')
        for project, attrs in all_attrs.items():
            expected = {path: {k: 'unspecified' for k in ('text', 'eol', 'filter', 'ident', 'working-tree-encoding')}
                        for provider, path in sorted(CANDIDATES) if provider == project}
            need(len(attrs) == 2 and [x['committed'] for x in attrs] == [True, False]
                 and all(x['values'] == expected for x in attrs),
                 'exact committed/effective raw-only provider checkout rules')
        for project in s['projects']:
            observed = project['all_tracked_filter_observation']
            need(observed['tracked_paths'] == project['tracked_entries']
                 and observed['all_tracked_filters_unspecified_or_unset'] is True
                 and observed['configuration_changed'] is False and observed['custom_filters_executed'] is False
                 and set(observed['attributes']) == {'unset', 'unspecified'}
                 and sum(observed['attributes'].values()) == project['tracked_entries'],
                 'every tracked member has a completed non-executable filter observation')
            expected_cones = b.canonical_sparse_cones(project['project']['sparse_paths'])
            need(len(project['actual_sparse_cones']) == len(set(project['actual_sparse_cones']))
                 and set(project['actual_sparse_cones']) == set(expected_cones),
                 'actual exact old or new canonical cones')


def compare_complete(bookends, old, new, before, after, deadline, guard):
    old, new = validate_profiles(bookends, old, new)
    a = VerifiedInventory(bookends, before, old['plan']['projects'], deadline, guard)
    z = VerifiedInventory(bookends, after, new['plan']['projects'], deadline, guard)
    result = compare_rows(a, z, allow_partial=False, expected_count=TRACKED_MEMBERS)
    need(a.completed and z.completed, 'both complete actual strict inventories consumed')
    return result
'''
s = header + '\nPROVIDERS = ' + repr(providers) + '\nCANDIDATES = ' + repr(candidates) + '\n' + body + '\n\n' + inventory + tail
ast.parse(s)
new_tree = ast.parse(s)
new_node = next(n for n in new_tree.body if isinstance(n, ast.ClassDef) and n.name == 'VerifiedInventory')
assert ast.get_source_segment(s, new_node) == inventory
out = root/'apex_test_transition.py'
with out.open('x') as f:
    f.write(s)
print(json.dumps({'bytes':len(s.encode()), 'sha256':hashlib.sha256(s.encode()).hexdigest(),
                  'unchanged_VerifiedInventory_bytes':len(inventory.encode()),
                  'provider_count':len(providers),'candidate_count':len(candidates),
                  'source_mutations':False,'runtime_qualified':False}))
