"""Strict, bounded evidence for the five-class view-only Probe fixture.

This module never sends UI input, removes a task, changes a permission, or
qualifies an engine automatically. All returned counts describe actual reads.
"""
import copy
import hashlib
import os
import re
import stat
import time
from datetime import datetime

PACKAGE = 'local.pocket4.fixture'
UID = 10115
PREINPUT_ERRORS = frozenset(('AMBIGUOUS_MATCH', 'INCOMPLETE_TREE_NO_ACTION_TAKEN',
    'WINDOW_CHANGED_NO_ACTION_TAKEN', 'WINDOW_BOUNDS_CHANGED_NO_ACTION_TAKEN',
    'TARGET_CHANGED_NO_ACTION_TAKEN', 'AMBIGUOUS_MATCH_NO_ACTION_TAKEN',
    'MATCH_SET_CHANGED_NO_ACTION_TAKEN', 'ACCESSIBILITY_TREE_NOT_READY_NO_ACTION_TAKEN'))
RESOURCE_BUDGET = {'minimum_samples_each_round': 20, 'minimum_sample_span_seconds': 25,
    'maximum_rss_kib': 524288, 'maximum_fds': 512, 'maximum_threads': 128,
    'maximum_late_rss_growth_kib': 32768, 'maximum_late_fd_growth': 16,
    'maximum_late_thread_growth': 8, 'maximum_adjacent_sample_gap_seconds': 12}


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def no_input_error(exc, helper):
    details = getattr(exc, 'details', {})
    return (isinstance(exc, helper.ControlError) and str(exc) in PREINPUT_ERRORS
        and details.get('outcome_unknown') is False and details.get('automatic_retry') is False
        and details.get('accessibility_mode_restoration_verified') is True)


def actual_target_matches(target, selector):
    mapping = {'id': 'resource-id', 'text': 'text', 'desc': 'content-desc',
        'class': 'class', 'package': 'package', 'enabled': 'enabled', 'clickable': 'clickable'}
    return (isinstance(target, dict) and set(selector) <= set(mapping)
        and all(target.get(mapping[k]) == v for k, v in selector.items()))


def complete_observation(value, focus):
    native = value.get('native', value)
    context = native.get('window_context', {})
    selected, root = context.get('selected_window', {}), context.get('root', {})
    shot = value.get('screenshot', {})
    scope = shot.get('scope', {})
    nodes = native.get('nodes')
    need(value.get('ok') is True and value.get('outcome_unknown') is not True
        and native.get('ok') is True and native.get('outcome_unknown') is not True
        and native.get('accessibility_mode_restoration_verified') is True
        and context.get('snapshot_complete') is True and context.get('tree_status') == 'available'
        and context.get('semantic_controls_available') is True
        and context.get('null_child_count') == 0 and context.get('truncated') is False
        and isinstance(nodes, list) and 1 <= len(nodes) <= 128,
        'COMPLETE_BOUNDED_PROBE_NODES_REQUIRED')
    window = selected.get('window_id')
    need(type(window) is int and window >= 0 and selected.get('active') is True
        and selected.get('focused') is True and selected.get('display_id') == 0
        and root.get('window_id') == window and root.get('package') == PACKAGE
        and root.get('visible') is True and root.get('present') is True
        and all(type(n.get('window_id')) is int and n['window_id'] == window for n in nodes)
        and selected.get('bounds') == root.get('bounds') == shot.get('scope_bounds')
        and scope.get('package') == focus.get('package') == PACKAGE
        and scope.get('window_token') == focus.get('window_token'),
        'PROBE_NATIVE_WINDOW_OR_GEOMETRY_CHANGED')
    return nodes


def exit_details(text, package, uid):
    """Parse actual Android exit tuple fields; callers retain the complete dump."""
    rows = {}
    for block in re.split(r'(?=^\s*ApplicationExitInfo #\d+:)', text, flags=re.M)[1:]:
        def one(pattern):
            found = re.findall(pattern, block)
            need(len(found) == 1, 'EXIT_DETAIL_FIELD_UNKNOWN')
            return found[0].strip()
        key = (one(r'\btimestamp=([^\n]+)'), one(r'\bpid=(\d+)'),
               one(r'\brealUid=(\d+)'), one(r'\breason=(\d+)\s*\('),
               one(r'\bprocess=([^\s]+)'))
        need(int(key[2]) == uid and key[4] == package and key not in rows,
             'EXIT_DETAIL_IDENTITY_OR_DUPLICATE')
        rows[key] = {'subreason': int(one(r'\bsubreason=(\d+)\s*\(')),
            'status': int(one(r'\bstatus=(-?\d+)')),
            'description': one(r'\bdescription=([^\n]+)')}
    return rows


class Diagnostics:
    """Contiguous retained-buffer checks, with exact normal-close exit ownership."""
    def __init__(self, session, module, record):
        self.s, self.d, self.record = session, module, record
        self.first = self.previous = None
        self.last_sample = None
        self.proofs = []
        self.failed = False
        self.maximum_segments = 72

    def start(self):
        need(self.first is None, 'ONE_DIAGNOSTIC_BASELINE_REQUIRED')
        self.first = self.previous = self.d.capture(self.s, self.record, 'probe-diagnostic-baseline')
        self.last_sample = time.monotonic()

    def accept(self, after, label, expected_close=None):
        need(self.previous is not None and not self.failed and len(self.proofs) < self.maximum_segments,
             'PROBE_DIAGNOSTIC_CHAIN_UNAVAILABLE')
        try:
            proof = self.d.compare(self.previous, after)
            item = proof['packages'][PACKAGE]
            need(item['bounded_log_window_retained'] and item['old_exit_records_retained']
                and item['raw_log_unknown_line_count'] == 0,
                'PROBE_DIAGNOSTIC_INTERVAL_NOT_RETAINED')
            need(item['no_new_crash_or_anr_observed'], 'NEW_PROBE_CRASH_OR_ANR')
            old = self.d.exits(self.previous['packages'][PACKAGE]['exits'], PACKAGE, UID)
            new = self.d.exits(after['packages'][PACKAGE]['exits'], PACKAGE, UID)
            added = new - old
            details = exit_details(after['packages'][PACKAGE]['exits'], PACKAGE, UID)
            if added:
                need(expected_close is not None and len(added) == 1, 'UNEXPLAINED_PROBE_SELF_EXIT')
                row = next(iter(added))
                need(int(row[1]) == expected_close['guest_pid'] and int(row[3]) == 10
                    and details[row] == {'subreason': 22, 'status': 0, 'description': 'remove task'},
                    'PROBE_EXIT_NOT_EXACT_OWNED_NORMAL_REMOVE')
            record = {'label': label, 'from_guest_seconds': self.previous['guest_seconds'],
                'to_guest_seconds': after['guest_seconds'], 'proof': item,
                'expected_normal_close': copy.deepcopy(expected_close),
                'actual_normal_close_exits': len(added),
                'new_exit_tuples': [list(row) for row in sorted(added)]}
            self.record('probe-diagnostic-segment-%d' % (len(self.proofs) + 1), record)
            self.proofs.append(record)
            self.previous, self.last_sample = after, time.monotonic()
            return bool(added)
        except BaseException:
            self.failed = True
            raise

    def checkpoint(self, label, force=False):
        need(self.first is not None and not self.failed, 'PROBE_DIAGNOSTICS_NOT_ACTIVE')
        if force or time.monotonic() - self.last_sample >= 8:
            after = self.d.capture(self.s, self.record, 'probe-diagnostic-%d' % (len(self.proofs) + 1))
            return self.accept(after, label)
        return False

    def after_close(self, task, guest_pid):
        expected = {'task': task, 'guest_pid': guest_pid, 'normal_remove_completed': True}
        deadline = time.monotonic() + 8
        for index in range(5):
            need(time.monotonic() < deadline, 'NORMAL_CLOSE_EXIT_READBACK_DEADLINE')
            after = self.d.capture(self.s, self.record, 'probe-close-exit-%d-%d' % (task, index))
            if self.accept(after, 'normal-close-%d' % task, expected):
                return
            time.sleep(.25)
        raise RuntimeError('EXPECTED_NORMAL_CLOSE_EXIT_NOT_OBSERVED')

    def finish(self):
        self.checkpoint('final', force=True)
        need(sum(p['actual_normal_close_exits'] for p in self.proofs) == 3,
             'THREE_EXACT_NORMAL_CLOSE_EXITS_REQUIRED')
        return {'clear': True, 'coverage': 'all_contiguous_intervals_retained',
            'from_guest_seconds': self.first['guest_seconds'],
            'to_guest_seconds': self.previous['guest_seconds'],
            'segments': self.proofs, 'new_crash_or_anr_events': 0,
            'actual_normal_close_exits': 3, 'unexplained_self_exits': 0,
            'maximum_segments': self.maximum_segments, 'background_workers': 0,
            'external_log_reset_exclusion': False}


def protected_data(session):
    """Hash only the exact fixture's bounded model directories; never write data."""
    session.guard()
    dump = session.android(['/system/bin/dumpsys', 'package', PACKAGE], 15).decode()
    blocks = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', dump, re.M | re.S)
    need(len(blocks) == 1, 'PROBE_ACTIVE_PACKAGE_SECTION_REQUIRED')
    users = re.findall(r'^    User 0: (.*?)(?=^    User \d+:|\Z)', blocks[0], re.M | re.S)
    need(len(users) == 1, 'PROBE_USER_ZERO_SECTION_REQUIRED')
    inodes = {}
    for key in ('ce', 'de'):
        values = re.findall(r'\b' + key + r'DataInode=(\d+)', users[0])
        need(len(values) == 1, 'PROBE_DATA_INODE_UNAVAILABLE')
        inodes[key] = int(values[0])
    out, files, total = {}, 0, 0
    deadline = time.monotonic() + 8

    def tree(fd, depth):
        nonlocal files, total
        need(depth <= 5 and time.monotonic() < deadline, 'PROBE_MODEL_TREE_BOUND')
        names = sorted(os.listdir(fd)); need(len(names) <= 128, 'PROBE_MODEL_DIRECTORY_BOUND')
        result = {}
        for name in names:
            files += 1
            need(files <= 256 and '/' not in name and name not in ('.', '..'), 'PROBE_MODEL_ENTRY_BOUND')
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            need(st.st_uid == UID and not stat.S_ISLNK(st.st_mode), 'PROBE_MODEL_ENTRY_OWNER_OR_LINK')
            if stat.S_ISDIR(st.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME, dir_fd=fd)
                try:
                    result[name] = {'kind': 'directory', 'mode': stat.S_IMODE(st.st_mode), 'children': tree(child, depth + 1)}
                finally:
                    os.close(child)
            else:
                need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_size <= 2 * 1024 * 1024,
                     'PROBE_MODEL_FILE_TYPE_OR_BOUND')
                total += st.st_size; need(total <= 8 * 1024 * 1024, 'PROBE_MODEL_TOTAL_BYTE_BOUND')
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME, dir_fd=fd)
                try:
                    before = os.fstat(child)
                    need((before.st_dev, before.st_ino, before.st_size) == (st.st_dev, st.st_ino, st.st_size),
                         'PROBE_MODEL_FILE_CHANGED_BEFORE_READ')
                    h, offset = hashlib.sha256(), 0
                    while offset < before.st_size:
                        need(time.monotonic() < deadline, 'PROBE_MODEL_HASH_DEADLINE')
                        raw = os.pread(child, min(65536, before.st_size - offset), offset)
                        need(raw, 'PROBE_MODEL_FILE_TRUNCATED'); h.update(raw); offset += len(raw)
                    after = os.fstat(child)
                    keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
                    need(all(getattr(before, k) == getattr(after, k) for k in keys), 'PROBE_MODEL_FILE_CHANGED_DURING_READ')
                    result[name] = {'kind': 'file', 'bytes': before.st_size,
                        'mode': stat.S_IMODE(before.st_mode), 'sha256': h.hexdigest()}
                finally:
                    os.close(child)
        need(names == sorted(os.listdir(fd)), 'PROBE_MODEL_DIRECTORY_CHANGED_DURING_READ')
        return result

    for key, prefix in (('ce', '/data/user/0/'), ('de', '/data/user_de/0/')):
        fd = session.target.open_root(prefix + PACKAGE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME)
        try:
            st = os.fstat(fd)
            need(st.st_uid == st.st_gid == UID and st.st_ino == inodes[key], 'PROBE_DATA_DIRECTORY_IDENTITY_CHANGED')
            entry = {'device': st.st_dev, 'inode': st.st_ino, 'uid': st.st_uid,
                'gid': st.st_gid, 'mode': stat.S_IMODE(st.st_mode), 'model_directories': {}}
            for name in ('files', 'shared_prefs', 'databases', 'no_backup'):
                try:
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME, dir_fd=fd)
                except FileNotFoundError:
                    entry['model_directories'][name] = None
                else:
                    try:
                        entry['model_directories'][name] = tree(child, 0)
                    finally:
                        os.close(child)
            out[key] = entry
        finally:
            os.close(fd)
    session.guard()
    return {'directories': out, 'model_entries': files, 'model_file_bytes': total,
        'model_file_contents_returned': False, 'data_writes': 0,
        'framework_cache_or_code_cache_contents_read': False}


def runtime_budget(runtime):
    """Review bounded live stability separately from later full engine mapping review."""
    rounds = []
    for index in (1, 2, 3):
        phase = 'probe-round-%d' % index
        rows = [r for s in runtime.samples if s['phase'] == phase for r in s['rows']]
        need(len(rows) >= RESOURCE_BUDGET['minimum_samples_each_round']
            and all(r['process_name'] == PACKAGE and r['stable_process_identity'] for r in rows),
            'PROBE_ROUND_RUNTIME_SAMPLE_COVERAGE')
        generations = {(r['host_pid'], r['start_ticks']) for r in rows}
        need(len(generations) == 1, 'UNEXPLAINED_PROCESS_REPLACEMENT_WITHIN_OWNED_ROUND')
        times = [datetime.fromisoformat(r['utc']).timestamp() for r in rows]
        span = times[-1] - times[0]
        gaps = [b - a for a, b in zip(times, times[1:])]
        need(span >= RESOURCE_BUDGET['minimum_sample_span_seconds']
            and all(0 <= gap <= RESOURCE_BUDGET['maximum_adjacent_sample_gap_seconds'] for gap in gaps),
            'PROBE_ROUND_RUNTIME_TIME_COVERAGE')
        rss, fds, threads = [], [], []
        for row in rows:
            status = row['status']
            need(re.fullmatch(r'\d+ kB', status.get('VmRSS', '')) and re.fullmatch(r'\d+', status.get('Threads', '')),
                 'PROBE_RESOURCE_FORMAT_UNKNOWN')
            rss.append(int(status['VmRSS'].split()[0])); fds.append(row['fd_count']); threads.append(int(status['Threads']))
        need(max(rss) <= RESOURCE_BUDGET['maximum_rss_kib'] and max(fds) <= RESOURCE_BUDGET['maximum_fds']
            and max(threads) <= RESOURCE_BUDGET['maximum_threads'], 'PROBE_ABSOLUTE_RESOURCE_BUDGET_EXCEEDED')
        late = [i for i, stamp in enumerate(times) if stamp - times[0] >= 10]
        need(len(late) >= 5, 'PROBE_LATE_RESOURCE_SAMPLES_MISSING')
        growth = {'rss_kib': rss[-1] - rss[late[0]], 'fds': fds[-1] - fds[late[0]],
            'threads': threads[-1] - threads[late[0]]}
        need(growth['rss_kib'] <= RESOURCE_BUDGET['maximum_late_rss_growth_kib']
            and growth['fds'] <= RESOURCE_BUDGET['maximum_late_fd_growth']
            and growth['threads'] <= RESOURCE_BUDGET['maximum_late_thread_growth'],
            'PROBE_BOUNDED_LATE_RESOURCE_GROWTH_EXCEEDED')
        stable = sum(r.get('full_mapping_snapshot') and r.get('maps_before_after_equal') for r in rows)
        need(stable >= 1, 'PROBE_ROUND_STABLE_FULL_MAPPING_NOT_CAPTURED')
        rounds.append({'round': index, 'samples': len(rows), 'span_seconds': span,
            'maximum_sample_gap_seconds': max(gaps), 'process_generation_count': len(generations),
            'maximum_rss_kib': max(rss), 'maximum_fds': max(fds), 'maximum_threads': max(threads),
            'late_growth': growth, 'stable_full_mapping_samples': stable})
    return {'reviewed_budget': RESOURCE_BUDGET, 'rounds': rounds,
        'bounded_live_resource_budget_verified': True, 'unmeasured_long_duration_claim': False,
        'engine_identity_automatically_passed': False}
