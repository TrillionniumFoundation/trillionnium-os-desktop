#!/usr/bin/python3
"""Pure/profile and streaming evidence checks for R20's six original lint files.

This module has no writer, launcher or self-authorizing main. The controller
must pin this module, the unchanged strict bookend helper, both normal plans,
the original R19 state and the actual newly qualified release before use.
"""
from itertools import zip_longest
from pathlib import Path
import hashlib
import os
import stat
import time

HEALTH = 'packages/modules/HealthFitness'
COMMIT = 'a292a16a8ac82667b65d763c00fa935cc44e9925'
ORIGIN = 'https://android.googlesource.com/platform/packages/modules/HealthFitness'
OLD_LOCK_SHA = '2e9877a58ebbc3625c7411d3573951afa409d9b13692468b825b4c25961ffffb'
NEW_LOCK_SHA = 'aa14d968c14c2febcfacbb90e82598e2ba8e57f4bbb2cfc8f1f2a741555153ca'
OLD_MANIFEST_SHA = 'e05ea8ffb8b6f1b140027cf2842adbf18d5623a0cf6edb3edf5cfd0565c3e487'
TRACKED_MEMBERS = 1045300
LINT = {
    'lint/Android.bp': ('9bb62a2bd8df6f99c6ccee5aa9f5b862d71ee1f2', 1301, 'f740623733b5f4e0e3e8b9ce0e9fa041f8fa87dccabcd47ecdd2568ad022822e'),
    'lint/OWNERS': ('e6a4d39c88cbc2fbf8d294c798a3ebf4e2d2c4e2', 81, 'd6d083143f0855e9c95a8d9766fab03544c80af8e98b8390946832471c13b1ab'),
    'lint/README.md': ('8cbc030138752beeac61da5e8139bd4d9241fda6', 2590, '177906d96f9640773c81ac09657d1f417da229500249700d80d2b381069ff1f3'),
    'lint/src/com/android/health/connect/lint/CheckFlagsRuleDetector.kt': ('a19c17d747b23b1f9bfad8f3de4fd8aae21ab8c8', 3555, '78bc37735efc6f27b3c55b38070fc6e9b1e310a2de6337f6efd7689c9c510945'),
    'lint/src/com/android/health/connect/lint/HealthConnectIssueRegistry.kt': ('7c8dad2e03770b0b839fc81c81145010933e6400', 1434, '62b826fe4296bc218b29ce11ae6cfc2fb3dbbbfab21c8b2c70ca0caf20497c68'),
    'lint/tests/com/android/health/connect/lint/CheckFlagsRuleDetectorTest.kt': ('b6fa8245aa31875f51c037266f8ee5053f94803f', 10415, '7665b17f07fad08cb3ab659082d6849469e5629b2b274e1ed3ddbd17bab0f170'),
}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def validate_profiles(bookends, old, new):
    """The old plan must itself be bound to the actual R19 652 input outside."""
    old, new = bookends.normalized_manifest(old), bookends.normalized_manifest(new)
    need(old['source_lock_sha256'] == OLD_LOCK_SHA
         and new['source_lock_sha256'] == NEW_LOCK_SHA, 'exact old CMake and new lint locks')
    before, after = old['plan'], new['plan']
    need(len(before['projects']) == len(after['projects']) == 652
         and len(before['links']) == 8, 'same full 652 project scope and eight root links')
    need({k: v for k, v in before.items() if k != 'projects'}
         == {k: v for k, v in after.items() if k != 'projects'}, 'root links or superproject changed')
    found = 0
    for a, b in zip(before['projects'], after['projects']):
        if a['path'] != HEALTH:
            need(a == b, 'unrelated original project or order changed')
            continue
        found += 1
        need(a['commit'] == COMMIT and a['url'] == ORIGIN
             and len(a['sparse_paths']) == 61 and 'lint' not in a['sparse_paths'],
             'exact original HealthFitness project and 61 cones')
        need(b == {**a, 'sparse_paths': a['sparse_paths'] + ['lint']},
             'only append the complete original lint directory')
    need(found == 1, 'single original HealthFitness project')
    return old, new


def recovery_branch(bookends, actual, old, new, reconcile_intent, vendor_intent, resume_intent):
    old, new = validate_profiles(bookends, old, new)
    actual = bookends.normalized_manifest(actual)
    need(all(type(v) is bool for v in (reconcile_intent, vendor_intent, resume_intent)),
         'actual source-stage presence booleans required')
    need(not vendor_intent or reconcile_intent, 'Vendor cannot precede original source intent')
    need(not resume_intent or reconcile_intent, 'resume cannot precede original source intent')
    if actual == old:
        need(not vendor_intent, 'Vendor intent contradicts the old CMake manifest')
        if not reconcile_intent:
            return 'old652-before-reconcile-dispatch'
        need(not resume_intent, 'old manifest after this recovery resume is unresolved; no retry')
        # This is a candidate branch, not permission or a recovery success.
        # Controller must prove exact partial bodies, retired children, held
        # serial and the remaining original deadline before a single resume.
        return 'old652-dispatched-requires-partial-bookend-before-one-normal-resume'
    if actual == new:
        need(reconcile_intent, 'new lint manifest lacks this owner original intent')
        return 'new652-lint-atomic-manifest-published'
    raise RuntimeError('manifest matches neither complete fixed normal profile')


def _candidate(row, expected, missing_allowed):
    oid, size, sha = expected
    base = {'project': HEALTH, 'path': row.get('path'), 'git_mode': '100644', 'git_blob': oid}
    if row.get('present') is False:
        need(missing_allowed and row == {**base, 'present': False, 'sparse_skip': True, 'f9': None},
             'only a complete original S-absent lint tuple is allowed')
        return False
    need(set(row) == set(base) | {'present', 'bytes', 'sha256', 'mode', 'f9'}
         and all(row[k] == v for k, v in base.items())
         and row['present'] is True and type(row['bytes']) is int and row['bytes'] == size
         and row['sha256'] == sha, 'lint must be the exact original raw Git blob, not another transform')
    identity = row['f9']
    need(type(identity) is list and len(identity) == 9
         and all(type(v) is int for v in identity)
         and identity[0] > 0 and identity[1] > 0
         and stat.S_ISREG(identity[2]) and identity[2] & 0o111 == 0
         and identity[3:6] == [1000, 1000, 1] and identity[6] == size
         and type(row['mode']) is int and row['mode'] == stat.S_IMODE(identity[2]),
         'new lint body must be an ordinary same-account non-executable original inode')
    return True


def compare_rows(before_rows, after_rows, *, allow_partial, expected_count):
    """Only six fixed S-absent rows may materialize, with exact original bytes.

    Inputs are fully validated pinned bookend streams below, not arbitrary
    JSON claims. F9 changes are counted separately; they never replace byte,
    mode, Git tuple, symlink, gitlink or checkout-conversion comparisons.
    """
    need(type(allow_partial) is bool and type(expected_count) is int and expected_count >= 6,
         'explicit complete or partial comparison scope')
    # The controller passes full generators. Close both even on a rejection;
    # retaining an exception traceback must not retain open inventory FDs.
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
        if key[0] == HEALTH and key[1] in LINT:
            need(key[1] not in seen, 'duplicate lint source member')
            seen.add(key[1])
            need(_candidate(a, LINT[key[1]], True) is False,
                 'this transition requires the actual six original absent lint members')
            present = _candidate(b, LINT[key[1]], allow_partial)
            if present:
                added += 1; added_bytes += b['bytes']
        else:
            need({k: v for k, v in a.items() if k != 'f9'}
                 == {k: v for k, v in b.items() if k != 'f9'},
                 'original non-lint source tuple, mode, content or representation changed')
            identity_changes += a.get('f9') != b.get('f9')
    need(count == expected_count and seen == set(LINT), 'incomplete exact source/lint roster')
    need(allow_partial or (added == 6 and added_bytes == 19376), 'all six original lint bodies required')
    return {'schema': 'p4-r20-six-original-lint-content-comparison-v1',
            'tracked_members_compared': count, 'original_lint_members': 6,
            'lint_materialized': added, 'lint_remaining_absent': 6 - added,
            'lint_raw_bytes_materialized': added_bytes,
            'all_other_original_tuples_identical': True,
            'non_lint_identity_changes': identity_changes,
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
    """Explicit partial schema; never accepted by compare_complete/strict reader."""
    def __init__(self, bookends, summary, old, new, deadline, guard):
        self.old, self.new = validate_profiles(bookends, old, new)
        need(summary['actual_health_cone_profile'] in ('old', 'new'), 'actual fixed Health cone observation')
        projects = list(self.old['plan']['projects'])
        if summary['actual_health_cone_profile'] == 'new':
            replacement = next(p for p in self.new['plan']['projects'] if p['path'] == HEALTH)
            projects = [replacement if p['path'] == HEALTH else p for p in projects]
        super().__init__(bookends, summary, projects, deadline, guard)

    def _validate_summary(self):
        b, s = self.bookends, self.summary
        need(s['schema'] == 'p4-r20-incomplete-lint-recovery-diagnostic-v1'
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
             'partial diagnostic retains the exact original old manifest and both distinct plans')
        attrs = s['lint_checkout_attributes']
        expected = {p: {k: 'unspecified' for k in ('text', 'eol', 'filter', 'ident', 'working-tree-encoding')}
                    for p in sorted(LINT)}
        need(len(attrs) == 2 and [x['committed'] for x in attrs] == [True, False]
             and all(x['values'] == expected for x in attrs), 'six exact committed/effective raw-only checkout rules')
        for project in s['projects']:
            observed = project['all_tracked_filter_observation']
            need(observed['tracked_paths'] == project['tracked_entries']
                 and observed['all_tracked_filters_unspecified_or_unset'] is True
                 and observed['configuration_changed'] is False and observed['custom_filters_executed'] is False
                 and set(observed['attributes']) == {'unset', 'unspecified'}
                 and sum(observed['attributes'].values()) == project['tracked_entries'],
                 'every actual tracked member has a completed non-executable filter observation')
            expected_cones = b.canonical_sparse_cones(project['project']['sparse_paths'])
            need(len(project['actual_sparse_cones']) == len(set(project['actual_sparse_cones']))
                 and set(project['actual_sparse_cones']) == set(expected_cones),
                 'partial summary reflects the actual exact old or new canonical cones')


def compare_complete(bookends, old, new, before, after, deadline, guard):
    old, new = validate_profiles(bookends, old, new)
    a = VerifiedInventory(bookends, before, old['plan']['projects'], deadline, guard)
    z = VerifiedInventory(bookends, after, new['plan']['projects'], deadline, guard)
    result = compare_rows(a, z, allow_partial=False, expected_count=TRACKED_MEMBERS)
    need(a.completed and z.completed, 'both complete actual strict inventories consumed')
    return result
