"""Admit the observed H329 formal-source epoch; never launch a build or write a source.

This is a metadata adapter, not a replacement for the normal full-build gates.
The prior normal-producer admission implementation is loaded from exact held
bytes and reused without changing its 26-command/86-stream/actor checks.
"""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import types

FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
          'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(value, message):
    if not value:
        raise RuntimeError(message)


def identity(info):
    return [getattr(info, name) for name in FIELDS]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def same(actual, expected, message):
    need(canonical(actual) == canonical(expected), message)


def integer(value, expected, message):
    need(type(value) is int and value == expected, message)


def reference(row):
    return {name: row[name] for name in ('path', 'bytes', 'sha256')}


def validate_core(entry, inner, outer, inputs, normal, materialized, lock):
    need(entry['schema'] == 'native604-ndk-parent-retaining-source-entry-r1'
         and outer['schema'] == 'native604-ndk-parent-retaining-source-outer-r1'
         and inner['state'] == 'NATIVE604_NDK_PARENT_RETAINING_SOURCE_NORMAL_RECONCILED',
         'the actual formal-source generation is required')
    need(entry['passed'] is True and outer['passed'] is True and outer['inner_passed'] is True
         and entry['errors'] == inner['errors'] == outer['errors'] == [], 'source owner failed')
    integer(entry['ordinary_launch_attempts'], 1, 'one original source dispatch required')
    integer(entry['actual_normal_commands'], 40, 'actual source command count differs')
    integer(inner['expected_normal_commands'], 40, 'source command contract differs')
    integer(inner['source_project_count'], 604, 'source count differs')
    need([row['name'] for row in inner['commands']] == inputs['expected_command_names']
         and len(inner['commands']) == 40, 'exact original source command sequence differs')
    need(inner['normal_source_extension_verified'] is True
         and inner['all_command_children_retired'] is True
         and inner['all_native_owner_locks_released'] is True
         and inner['materialized_original_file_set_unchanged'] is True
         and inner['materialized_original_file_set_changed'] is False,
         'formal source verification or retirement incomplete')
    need(entry['direct_child_state'] == 'REAPED'
         and outer['owned_unit_retired'] is True and outer['systemd_launcher_pidfd_exit_observed'] is True
         and outer['timed_out'] is False and outer['privileged'] is False,
         'both original source owner layers must have retired')
    same(entry['inputs_before'], entry['inputs_after'], 'source entry inputs changed')
    same(reference(entry['inner']), reference(outer['inner']), 'inner ownership binding differs')
    same(inner['source_lock'], normal['source_lock'], 'source and normal tool lock differ')
    same(inner['manifest_after'], outer['source_postcondition']['manifest'], 'source postcondition differs')
    same(inner['original_locks_after'], outer['source_postcondition']['jointly_held_original_locks'],
         'post-retirement lock observations differ')
    need(outer['source_postcondition']['observed_after_unit_retirement'] is True
         and outer['source_postcondition']['source_projection_absent'] is True, 'post-retirement source unknown')
    need(normal['recipe_commit'] == inputs['recipe_commit'] == '0b5d6d48302b7a1570d3440391608f015936e0ef'
         and normal['recipe_tree'] == inputs['recipe_tree'] == '59c8e0007a69d9f6218065c8b30a24ef11371814'
         and normal['production_variant'] == inner['production_variant'] == 'user'
         and normal['release_source_label'] == inner['release_source_label'] == 'cp2a',
         'only the qualified user/cp2a producer can be selected')
    need(materialized['source_lock_sha256'] == inner['source_lock']['sha256']
         == 'd88549bc89076017baffcc28e39695431993cc12516238278e015f23325d9596'
         and len(materialized['plan']['projects']) == len(lock['projects']) == 604,
         'current materialized selection/lock differs')
    # These remain negative even after successful metadata admission.
    for doc, counters in ((entry, ('AOSP_full_builds_started', 'VM_runs')),
                          (inner, ('full_builds_started',)),
                          (outer, ('Android_starts', 'VM_runs', 'host_policy_loads')),
                          (normal, ('AOSP_full_builds_started',))):
        for name in counters:
            integer(doc[name], 0, 'source proof must not acquire build/runtime credit: ' + name)
    need(inner['CP3A_source_equivalence_qualified'] is False
         and normal['CP3A_source_equivalence_qualified'] is False
         and inner['Soong_build_qualification'] is False
         and inner['runtime_qualified'] is normal['runtime_qualified'] is entry['runtime_qualified'] is False,
         'source metadata cannot grant QPR1/full/runtime qualification')
    for row in inner['commands']:
        life = row['lifecycle']
        integer(life['returncode'], 0, 'source command failed')
        need(row['owned_retirement_complete'] is True and row['errors'] == []
             and life['child_reaped'] is True and life['pidfd_closed'] is True
             and life['owned_tree_cleanup_complete'] is True and life['remaining_owned_children'] == []
             and row['reaper']['final_children_empty'] is True and row['reaper']['restored'] is True
             and row['adopted_normal_exit']['complete'] is True, 'source command custody incomplete')
    for snapshot in (inner['resources_before'], inner['resources_after']):
        need(snapshot['affinity'] == [8, 9] and snapshot['memory.max'] == '4294967296'
             and snapshot['cpu.max'] == '200000 100000'
             and snapshot['memory.swap.max'] == snapshot['memory.swap.current'] == '0',
             'actual source resource contract changed')
        events = dict(line.split() for line in snapshot['memory.events'].splitlines())
        need(all(events.get(key) == '0' for key in ('oom', 'oom_kill', 'oom_group_kill')),
             'actual source had an OOM event')
    return {'source_admission_fields_verified': True, 'source_projects': 604,
            'production_variant': 'user', 'release_source_label': 'cp2a',
            'full_ready': False, 'runtime_qualified': False, 'CP3A_source_equivalence_qualified': False}


class HeldReader:
    """Complete streamed reads, no symlink components, F9/name/FD bookends."""
    need = staticmethod(need)

    def __init__(self, deadline_seconds=100):
        self.deadline = time.monotonic() + deadline_seconds
        self.total = 0
        self.references = []

    def tick(self):
        need(time.monotonic() < self.deadline, 'metadata read deadline exceeded')

    def open_absolute(self, path, flags=os.O_RDONLY):
        path = Path(path)
        need(path.is_absolute() and '..' not in path.parts, 'absolute canonical evidence path required')
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            for part in path.parts[1:-1]:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                os.close(fd); fd = nxt
            return os.open(path.name, flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd)
        finally:
            os.close(fd)

    def file_ref(self, path, maximum=128 * 1024**2, *, contents=False):
        self.tick(); fd = self.open_absolute(path)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == before.st_gid == 1000
                 and 0 <= before.st_size <= maximum, 'bounded ordinary evidence required')
            h = hashlib.sha256(); parts = []; count = 0
            while True:
                self.tick(); part = os.read(fd, 1024**2)
                if not part: break
                count += len(part); self.total += len(part)
                need(count <= before.st_size and self.total <= 256 * 1024**2, 'metadata read budget exceeded')
                h.update(part)
                if contents: parts.append(part)
            named = self.open_absolute(path)
            try: need(identity(before) == identity(os.fstat(fd)) == identity(os.fstat(named)), 'held/name evidence changed')
            finally: os.close(named)
            need(count == before.st_size, 'complete evidence required')
            row = {'path': str(path), 'bytes': count, 'sha256': h.hexdigest(), 'identity': identity(before)}
            self.references.append(row)
            return (row, b''.join(parts)) if contents else row
        finally:
            os.close(fd)

    def pinned(self, expected, maximum=128 * 1024**2, *, contents=False):
        actual, raw = self.file_ref(expected['path'], maximum, contents=True) if contents else (self.file_ref(expected['path'], maximum), None)
        same(reference(actual), reference(expected), 'exact evidence bytes changed')
        if 'identity' in expected: same(actual['identity'], expected['identity'], 'evidence F9 changed')
        return (actual, raw) if contents else actual

    def document(self, expected):
        _, raw = self.pinned(expected, contents=True)
        return json.loads(raw)

    def module(self, expected):
        _, raw = self.pinned(expected, 1024**2, contents=True)
        module = types.ModuleType('held_' + expected['sha256']); module.__file__ = expected['path']
        exec(compile(raw, expected['path'], 'exec'), module.__dict__)
        return module


def normal_admission(contract, build=None, config=None):
    """Actual producer/actor qualification, preserving the original Normal checks."""
    reader = HeldReader(); entry = reader.document(contract['entry']); inner = reader.document(contract['inner'])
    inputs = reader.document(inner['input_record']); normal = reader.document(inner['recipe_tool_build'])
    if build is not None: same(build, normal, 'selected normal producer changed')
    if config is not None:
        same(config['recipe_commit'], inputs['recipe_commit'], 'selected recipe commit changed')
        same(config['recipe_tree'], inputs['recipe_tree'], 'selected recipe tree changed')
        same(reference(config['normal_tool_build']), reference(inner['recipe_tool_build']), 'normal producer reference changed')
    helper = reader.module(entry['inputs_before']['source_epoch_admission.py'])
    guards = reader.module(entry['inputs_before']['audio_continuation_control.py'])
    helper.configure(reader, guards, Path(contract['root']))
    helper.validate_normal_tools(normal, inputs)
    records = {name: reader.document(ref) for name, ref in inputs['normal_tool_raw_H'].items()}
    return helper.validate_normal_owner(records, reader.document(inputs['normal_tool_outer']), normal,
                                        inner['recipe_tool_build'], inputs)


def qualify(contract, borrowed_locks=None):
    reader = HeldReader(); entry = reader.document(contract['entry']); inner = reader.document(contract['inner'])
    outer = reader.document(contract['outer']); inputs = reader.document(inner['input_record'])
    normal = reader.document(inner['recipe_tool_build']); normal_outer = reader.document(inputs['normal_tool_outer'])
    need(reference(inputs['normal_tool_build']) == reference(inner['recipe_tool_build']), 'normal producer reference changed')
    helper = reader.module(entry['inputs_before']['source_epoch_admission.py'])
    guards = reader.module(entry['inputs_before']['audio_continuation_control.py'])
    helper.configure(reader, guards, Path(contract['root']))
    helper.validate_normal_tools(normal, inputs)
    normal_records = {name: reader.document(ref) for name, ref in inputs['normal_tool_raw_H'].items()}
    normal_owner = helper.validate_normal_owner(normal_records, normal_outer, normal, inner['recipe_tool_build'], inputs)
    for ref in normal['normal_tools']:
        reader.pinned(ref)
    recipe = Path(inner['source_lock']['path']).parents[2]
    need(str(recipe) == contract['recipe'], 'normal recipe path changed')
    seen = set()
    for directory, dirs, files in os.walk(recipe, followlinks=False):
        reader.tick(); dirs[:] = [name for name in dirs if name != '.git']
        need(all(not (Path(directory) / name).is_symlink() for name in dirs), 'recipe directory alias')
        for name in files:
            path = Path(directory) / name; relative = path.relative_to(recipe).as_posix()
            need(relative in normal['recipe_files'] and relative not in seen, 'extra recipe member')
            expected = normal['recipe_files'][relative]
            need(expected['kind'] == 'file', 'this metadata adapter requires ordinary recipe members')
            actual = reader.pinned({'path':str(path), 'bytes':expected['bytes'], 'sha256':expected['sha256']})
            need(stat.S_IMODE(actual['identity'][2]) == expected['mode'], 'recipe mode changed')
            seen.add(relative)
    same(sorted(seen), sorted(normal['recipe_files']), 'recipe membership changed')
    jobs = Path('/home/qq/.local/state/hepta-runtime-mac-worker/jobs') / contract['source_H']['job_id']
    source_records = {}
    for name in ('request', 'started', 'exit'):
        actual, raw = reader.file_ref(jobs / (name + '.json'), 1024**2, contents=True)
        source_records[name] = json.loads(raw)
    h = contract['source_H']; request = source_records['request']; started = source_records['started']; terminal = source_records['exit']
    guards.validate_raw_exit(terminal, request, started, expected_exit_code=0,
        expected_at_unix_ms=h['at_unix_ms'], expected_stream_bytes={'stdout':374, 'stderr':0})
    need(request['job_id'] == started['job_id'] == terminal['job_id'] == h['job_id']
         and request['launch_nonce'] == started['launch_nonce'] == terminal['launch_nonce'] == h['launch_nonce'],
         'actual formal-source H generation differs')
    approved = contract['source_approved_request']
    for name in ('executable', 'args', 'cwd', 'env', 'timeout_seconds', 'memory_max_bytes', 'cpu_quota_percent', 'nice'):
        same(request[name], approved[name], 'actual source request differs: ' + name)
    integer(started['supervisor_uid'], 1000, 'ordinary source supervisor required')
    _, actual_entry = reader.pinned(entry['actual_entry'], contents=True)
    same(request['args'], ['-I','-B','-c',actual_entry.decode()], 'actual source H did not execute the retained entry')
    same(reference(entry['inner']), reference(contract['inner']), 'entry/inner reference differs')
    same(reference(entry['outer']), reference(contract['outer']), 'entry/outer reference differs')
    helper.process_retired(entry['launcher_child']); helper.process_retired(outer['systemd_launcher'])
    for proof in (entry['independent_unit_reconciliation'], outer['unit_reconciliation']):
        need(proof['state'] == 'MATCHED_INVOCATION_RETIRED' and proof['retired'] is True
             and proof['identity_conflict'] is False and proof['errors'] == [] and proof['stop_requests'] == []
             and proof['actual_started_value'] == inner['owned_unit_started']
             and proof['actual_invocation_id'] == '8b69f08e4d7f4dd18752b62029311aab'
             and proof['cgroup_absent'] is True and proof['original_controller_generation_absent'] is True,
             'formal source exact-unit retirement incomplete')
    # Every original source command stream is consumed from its pinned held read.
    for row in inner['commands']:
        for name in ('stdout', 'stderr'): reader.pinned(row[name], 16*1024**2)
        path = Path(row['stdout']['path']).with_suffix('.json')
        _, raw = reader.file_ref(path, 1024**2, contents=True)
        same(json.loads(raw), row, 'source command record differs from retained inner')
    with joint_original_locks(reader, inner['held_original_locks'], borrowed_locks) as (held, lock_rows):
        materialized = reader.document(inner['manifest_after']); lock = reader.document(inner['source_lock'])
        result = validate_core(entry, inner, outer, inputs, normal, materialized, lock)
        need(not os.path.lexists(Path(contract['root']) / 'work/source-projection.json'), 'source projection still active')
        owner = inner['source_owner']
        need(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == owner['boot_id'], 'source host boot changed')
        need(not os.path.lexists(outer['observed_owned_cgroup']), 'source cgroup still present')
        try: fd = os.pidfd_open(owner['pid'], 0)
        except ProcessLookupError: pass
        else:
            os.close(fd); raise RuntimeError('source PID allocated: generation-specific reconciliation required')
        for fd, ref in zip(held, lock_rows):
            same(identity(os.fstat(fd)), ref['identity'], 'held original lock changed')
            reader.pinned(ref)
        reader.pinned(inner['manifest_after'])
        result.update(normal_owner=normal_owner, source_H=h, original_locks_jointly_observed=lock_rows,
                      current_source_manifest=inner['manifest_after'], normal_tools=normal['normal_tools'],
                      read_bytes=reader.total, source_writes=0, full_builds_started=0,
                      metadata_admitted=True, original_locks_released_on_return=not bool(borrowed_locks),
                      borrowed_lock_paths=sorted(borrowed_locks or {}),
                      borrowed_descriptors_preserved=True)
        return result



@contextlib.contextmanager
def joint_original_locks(reader, references, borrowed_locks=None):
    borrowed_locks = {} if borrowed_locks is None else borrowed_locks
    need(type(borrowed_locks) is dict and set(borrowed_locks) <= {r['path'] for r in references},
         'foreign borrowed lock')
    held = []; owned = []; lock_rows = []
    try:
        for ref in references:
            reader.pinned(ref)
            if ref['path'] in borrowed_locks:
                fd = borrowed_locks[ref['path']]
                need(type(fd) is int and fd >= 0, 'borrowed lock descriptor required')
            else:
                fd = reader.open_absolute(ref['path'], os.O_RDWR); owned.append(fd)
            held.append(fd)
            same(identity(os.fstat(fd)), ref['identity'], 'original lock inode/owner changed')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raw = os.pread(fd, ref['bytes'] + 1, 0)
            need(len(raw) == ref['bytes'] and hashlib.sha256(raw).hexdigest() == ref['sha256'],
                 'original lock content changed')
            lock_rows.append(ref)
        need(len(held) == 3, 'three joint original locks required')
        yield held, lock_rows
    finally:
        for fd in reversed(owned): os.close(fd)
