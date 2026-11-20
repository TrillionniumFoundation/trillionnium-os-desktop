#!/usr/bin/python3
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

PROVIDERS = {'packages/modules/IPsec': {'commit': '5c58f82cc230a9a4e22c80d6eaec62dffaec4444', 'url': 'https://android.googlesource.com/platform/packages/modules/IPsec', 'cone': 'apex/testing', 'original_cones': 10}, 'packages/modules/Permission': {'commit': '1093eca7407576c72e51b1a88550ee0667a6e5dc', 'url': 'https://android.googlesource.com/platform/packages/modules/Permission', 'cone': 'testing', 'original_cones': 112}}
CANDIDATES = {('packages/modules/IPsec', 'apex/testing/Android.bp'): ('57b6f53d7b3148d3c025b5f21ac2b4a4cfb210f1', 997, '2a6958f9eb0cba0135989f870ab575b64e1b973a1c2bf3ce0d21396b9671d4e0'), ('packages/modules/IPsec', 'apex/testing/test_apex_manifest.json'): ('38a8de615750557fe1761672796a3ff810d5bb79', 63, '8f4afd2171f18ca587e81ab72ea47092fd25632c7b4f7f58ca12b6038d115a9e'), ('packages/modules/Permission', 'testing/Android.bp'): ('d74510754d656c37bd8da78ffb1e5f9d5880394b', 1062, '27d6a932f683d3225ba732d63d53ce5a5377cd9fa0eb238ba658efc1db2973f4'), ('packages/modules/Permission', 'testing/test_manifest.json'): ('bc19a9ea0172ac5c6ae094a59668ea02cf6df030', 64, 'd4d84d1594071b8518623af1942f5d5943791aa8db8eca75ae32527abd511028')}


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


class VerifiedInventory:
    """One bounded-memory pass verifies every row and the entire bookend digest."""
    def __init__(self, bookends, summary, projects, deadline, guard):
        self.bookends, self.summary = bookends, summary
        self.projects = bookends.normalized_projects(projects)
        self.deadline, self.guard = deadline, guard
        self.completed = False
        self.started = False

    def __iter__(self):
        b, s = self.bookends, self.summary
        need(not self.started, 'inventory is single pass')
        self.started = True
        self._validate_summary()
        return self._rows()

    def _validate_summary(self):
        s = self.summary
        need(s['schema'] == 'pocket4-original-materialized-source-content-bookend-v1'
             and s['all_actual_Git_blob_reads_verified'] is True and s['source_mutations'] is False
             and s['project_count'] == len(self.projects)
             and [v['project'] for v in s['projects']] == self.projects,
             'complete fixed strict-helper project summaries')

    def _rows(self):
        b, s = self.bookends, self.summary
        ref = s['inventory']; path = Path(ref['path'])
        need(path.is_absolute() and path.parent.resolve() == path.parent,
             'canonical original inventory path')
        first = f9(path.lstat())
        need(first == ref['identity'] and stat.S_ISREG(first[2]) and first[5] == 1
             and first[6] == ref['bytes'], 'original inventory F9 and bytes')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        stream = os.fdopen(fd, 'rb')
        whole = hashlib.sha256(); content = hashlib.sha256(); byte_count = 0
        total_files = total_bytes = total_absent = total_rows = 0
        try:
            need(f9(os.fstat(fd)) == first, 'inventory inode replaced before stream')
            pending = None
            for project, expected in zip(self.projects, s['projects']):
                body = hashlib.sha256(); files = size = absent = rows = 0; previous = None
                while True:
                    need(time.monotonic() < self.deadline, 'original source comparison deadline')
                    if pending is None:
                        line = stream.readline(1024 * 1024 + 1)
                        if not line:
                            break
                        need(len(line) <= 1024 * 1024 and line.endswith(b'\n'), 'bounded whole source row')
                        whole.update(line); byte_count += len(line)
                        item = b.strict_json(line)
                    else:
                        item = pending; pending = None
                    need(type(item) is dict and 'f9' in item and 'project' in item, 'observed complete row')
                    if item['project'] != project['path']:
                        pending = item; break
                    relative = item.get('path'); b.safe_relative(relative)
                    need(previous is None or relative > previous, 'unique lexicographic project roster')
                    previous = relative
                    need(item.get('present') is True or item.get('present') is False, 'actual presence boolean')
                    raw = {k: v for k, v in item.items() if k not in ('project', 'f9')}
                    body.update(b.encoded(raw)); rows += 1; total_rows += 1
                    if item['present']:
                        files += 1; size += item.get('bytes', 0)
                        need(type(item['f9']) is list and len(item['f9']) == 9
                             and all(type(v) is int for v in item['f9']), 'complete actual present F9')
                    else:
                        absent += 1
                        need(item['f9'] is None and item.get('sparse_skip') is True, 'actual original sparse absence')
                    if total_rows % 8192 == 0:
                        self.guard()
                    yield item
                stable = {'project': project, 'tree': expected['tree'], 'tracked_entries': rows,
                          'materialized_entries': files, 'materialized_bytes': size,
                          'sparse_absent_entries': absent, 'body_sha256': body.hexdigest()}
                need({k: expected[k] for k in stable} == stable, 'complete raw project body summary differs')
                content.update(b.encoded(stable)); total_files += files; total_bytes += size; total_absent += absent
            need(pending is None and stream.read(1) == b'', 'extra project or trailing inventory data')
            need(byte_count == ref['bytes'] and whole.hexdigest() == ref['sha256']
                 and f9(os.fstat(fd)) == first == f9(path.lstat()), 'whole original inventory hash/F9 bookends')
            need(content.hexdigest() == s['content_sha256']
                 and total_files == s['materialized_entries']
                 and total_bytes == s['materialized_bytes']
                 and total_absent == s['sparse_absent_entries'], 'complete inventory aggregate differs')
            self.completed = True
        finally:
            stream.close()


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
