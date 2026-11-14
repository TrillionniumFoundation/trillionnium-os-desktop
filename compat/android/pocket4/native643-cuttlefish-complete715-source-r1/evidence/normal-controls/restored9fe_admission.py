"""Admit the independently retired, restored9fe source without granting build credit."""
import os
from pathlib import Path

N = Path('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1')
SOURCE = N / 'work/aosp-source'
H = '1a1d7215e1b-392-9fe'
BOOT = 'b1620269-aaef-43e7-bf47-bc6eb1c1a447'
RETIREMENT = {'path': str(N / 'control/full9fe-retirement-20261113-takeover-r2/FULL9FE-RETIREMENT.json'), 'bytes': 105650, 'sha256': '3154130bec8697a4f4e31c633933ca8fed1226d9e3252ac04a8197070f19f97d'}


def configure(reader, require, identity, reference, joint):
    global Reader, need, F9, pick, joint_locks
    Reader, need, F9, pick, joint_locks = reader, require, identity, reference, joint


def load():
    reader = Reader(480)
    contract = reader.document(RETIREMENT)
    need(contract['schema'] == 'native643-full9fe-independent-physical-retirement-v1'
         and contract['state'] == 'FULL9FE_ACTUAL_RESULT_PRESERVED_SOURCE_AND_ALL_OWNED_ACTORS_RETIRED'
         and contract['original_full_H'] == H and contract['actual_commands'] == 32
         and contract['all_three_original_EX_leases_released'] is contract['original_result_preserved'] is True
         and contract['current_source_files'] == 30952 and contract['complete_indexes'] == 643
         and contract['projection_originals'] == 161 and contract['source_writes'] == contract['source_writers_started'] == contract['full_builds_started'] == 0
         and contract['runtime_qualified'] is contract['production_ready'] is contract['full_build_qualified'] is False,
         'actual independent a09 full9fe retirement must remain exact')
    manifest = reader.document(contract['original_control_manifest'])
    need(len(manifest['files']) == 49, 'all original49 full9fe controls remain fixed')
    for row in manifest['files'].values():
        reader.pinned(row, 8 * 1024**2)
    return contract, manifest, reader.document(contract['previous_full_contract'])


def history(contract, manifest, prior):
    reader = Reader(480)
    guards = reader.module(manifest['files']['audio_continuation_control.py'])
    docs = {name: reader.document(row) for name, row in contract['original_documents'].items()}
    request, started, exited, inner, outer, fallback = [docs[name] for name in ('request', 'started', 'exit', 'inner', 'outer', 'fallback')]
    need(request['job_id'] == started['job_id'] == exited['job_id'] == H
         and request['request_digest'] == 'c442a52c3ff7208ebe98ea58245928038591dea656f2d6909c0f4bd77cdc7348'
         and request['launch_nonce'] == started['launch_nonce'] == exited['launch_nonce'] == '7885a53c46662729d6fce82d18a699ed',
         'the unique failed9fe identity must remain fixed')
    guards.validate_raw_exit(exited, request, started, expected_exit_code=1, expected_at_unix_ms=1794610860700, expected_stream_bytes={'stdout': 2014, 'stderr': 385})
    need(inner['state'] == 'FAILED' and inner['build_success'] is inner['runtime_qualified'] is inner['complete_engine_ART_pair_qualified'] is False
         and inner['input_after_qualified'] is inner['source_projection_restored'] is inner['owned_retirement_complete'] is inner['resource_gate_passed'] is True
         and outer['owned_unit_retired'] is outer['launcher_child_reaped'] is outer['source_projection_absent_after'] is fallback['source_projection_restored'] is fallback['does_not_upgrade_failed_build'] is True
         and outer['build_success'] is False and outer['errors'] == [], 'failed9fe source recovery is not full success')
    need(pick(outer['inner_terminal']) == pick(contract['original_documents']['inner'])
         and pick(outer['fallback_recovery']) == pick(contract['original_documents']['fallback'])
         and inner['outer_job_id'] == outer['outer_job_id'] == fallback['outer_job_id'] == H, 'actual full9fe receipt chain')
    commands = inner['commands'] + fallback['commands']
    need(len(inner['commands']) == 27 and len(fallback['commands']) == 5 and len(commands) == 32, 'all32 original full9fe commands')
    normal = []
    for row in commands:
        life = row['lifecycle']
        need(row['owned_retirement_complete'] is life['child_reaped'] is life['pidfd_closed'] is life['owned_tree_cleanup_complete'] is True
             and life['remaining_owned_children'] == [], 'every original full9fe command tree retired')
        if row['name'] == 'normal-full-native-engine-ART-pair':
            normal.append(row)
            need(life['returncode'] == 1 and row['argv'] == prior['full_context']['normal_argv'], 'actual normal9fe pair failure preserved')
        else:
            need(life['returncode'] == 0, 'actual non-build full9fe command failure')
        for side in ('stdout', 'stderr'):
            reader.pinned(row[side], 16 * 1024**2)
    need(len(normal) == 1, 'one original failed normal pair')
    actual = [line for line in reader.pinned(normal[0]['stdout'], 16 * 1024**2, contents=True)[1].decode().splitlines() if line.startswith('error:')]
    need(actual == contract['business_first_errors'] == ['error: device/google/cuttlefish/tests/graphics/Android.bp:19:1: "CuttlefishDisplayHotplugTest" depends on undefined module "CuttlefishDisplayHotplugHelperApp".'], 'exact unresolved original provider error preserved')
    for name in ('before_boundary', 'after_boundary', 'fallback_boundary'):
        row = docs[name]
        need(row['source_originals'] == 30952 and row['actual_roles'] == 161
             and row['whole_original_bytes_mode_nsmtime_absence_verified'] is row['unchanged_F9_required_outside_actual_projection'] is row['all_source_original_nsmtime_verified'] is True,
             'all original30952 and independent161 full9fe restoration bookends')
    need(docs['after_boundary'] == docs['fallback_boundary'], 'full9fe recovery and fallback agree')
    for name in ('index_modes_after', 'index_modes_fallback'):
        row = docs[name]
        need(row['index_count'] == 643 and row['changed_count'] == 0
             and row['all_original_mode_owner_link_preserved'] is row['only_exact_original_mode_restored'] is True, 'original643 cache metadata unchanged')
    need(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT
         and len(contract['fresh_original_PIDFD_ESRCH']) == 45
         and not any(os.path.lexists(path) for path in contract['actual_original_cgroups_absent']), 'original failed9fe boot/cgroups')
    for pid in contract['fresh_original_PIDFD_ESRCH']:
        try:
            fd = os.pidfd_open(pid, 0)
        except ProcessLookupError:
            continue
        os.close(fd)
        raise RuntimeError('original full9fe PID allocated; reconcile exact generation')
    job = Path('/home/qq/.local/state/hepta-runtime-mac-worker/jobs/1a1d728ffe2-392-a09')
    owner = {name: reader.document(reader.file_ref(job / (name + '.json'))) for name in ('request', 'started', 'exit')}
    rq, st, ex = [owner[name] for name in ('request', 'started', 'exit')]
    need(rq['job_id'] == st['job_id'] == ex['job_id'] == '1a1d728ffe2-392-a09'
         and rq['request_digest'] == 'ce5bc083d89148f3bb14185305b0278c3107ab45014f73927ec966bb4b896b70'
         and rq['launch_nonce'] == st['launch_nonce'] == ex['launch_nonce'] == 'a2b53fcbae2f61ce2b9e8c889303ae48', 'actual independent a09 owner')
    guards.validate_raw_exit(ex, rq, st, expected_exit_code=0, expected_at_unix_ms=1794611156249, expected_stream_bytes={'stdout': 2823, 'stderr': 0})
    # Successful independent retirement's own original actors must also be gone.
    groups = ['/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-1a1d728ffe2-392-a09.service',
              '/sys/fs/cgroup/system.slice/hepta-runtime-job-1a1d728ffe2-392-a09.service']
    need(not any(os.path.lexists(path) for path in groups), 'independent a09 metadata cgroup remains')
    for pid in (st['supervisor_pid'], contract['budget_before']['own_cap_control']['pid']):
        try:
            fd = os.pidfd_open(pid, 0)
        except ProcessLookupError:
            continue
        os.close(fd)
        raise RuntimeError('independent a09 PID allocated; reconcile exact generation')
    source = reader.module(manifest['files']['qualified_global_source_admission.py'])
    source.configure(Reader, need, F9, pick, joint_locks)
    _, source_docs, _, source_proof = source.load(prior['global_source'])
    source.fresh_retirement(source_docs)
    normal_proof = source.normal_admission(prior['global_source'])
    return {'actual_source_H': '1a1d6e282f9-392-9bd', 'actual_source_writer_H': '1a1d6d7911d-392-9aa', 'source9aa_failure_and9bd_completion_preserved': source_proof['source_admission_fields_verified'], 'actual_normal974': normal_proof, 'failed_full_H': H, 'independent_retirement_H': '1a1d728ffe2-392-a09', 'original_failure_preserved': True, 'all32_original_commands_retired': True, 'fresh_original_PIDFD_ESRCH': contract['fresh_original_PIDFD_ESRCH'], 'fresh_original_cgroups_absent': contract['actual_original_cgroups_absent'], 'runtime_qualified': False, 'full_ready': False}


def current(contract, manifest, prior):
    reader = Reader(480)
    index = reader.document(contract['current_physical_index'])
    need(index['schema'] == 'native643-restored-after-full9fe-physical-index-v1' and index['restoring_full_H'] == H
         and index['file_count'] == len(index['files']) == 30952 and index['physical_bytes'] == 503404771, 'complete actual restored9fe physical epoch')
    physical = reader.module(prior['global_source']['physical_helper'])
    physical.configure(None, need, F9, None, None)
    observed = [(row, physical.physical(reader, row, require_original_f9=True)) for row in index['files']]
    for row, identity in observed:
        fd = reader.open_absolute(Path(row['path']).parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            need(F9(os.stat(Path(row['path']).name, dir_fd=fd, follow_symlinks=False)) == identity, 'complete source F9 changed across restored9fe audit')
        finally:
            os.close(fd)
    for row in index['auxiliary_refs']:
        reader.pinned(row)
    projection = reader.module(manifest['files']['projection_baseline_admission.py'])
    projection.verify_restored(reader.document(contract['current_projection_baseline']), {})
    materialized = reader.document(contract['source_manifest'])
    need(materialized['source_lock_sha256'] == 'e8b359276e49d6f520344284cbf2876f403d03150018d286ab8b0df362817e71'
         and len(materialized['plan']['projects']) == 643, 'same actual post-full9fe manifest and locked source')
    cache = reader.document(contract['current_index_cache'])
    need(cache['schema'] == 'native643-full9fe-current-index-cache-v1' and cache['index_count'] == 643
         and len(cache['indexes']) == 643, 'all643 actual post-full9fe SHA cache epochs')
    rows = cache['indexes']
    for row in rows:
        reader.pinned(row, 128 * 1024**2)
    for row in rows:
        path = Path(row['path']); fd = reader.open_absolute(path)
        try:
            need(F9(os.fstat(fd)) == row['identity'] == F9(path.lstat()), 'current SHA-bound cache F9 changed')
        finally:
            os.close(fd)
    need(not os.path.lexists(N / 'work/source-projection.json') and not list((N / 'work').glob('.droidloom-project-*')), 'no source projection or staging')
    return {'source30952_F9_unchanged': True, 'source161_current_originals_F9_unchanged': True, 'all643_current_indexes_F9_unchanged': True, 'source_physical_bytes': 503404771, 'source_writes': 0}


def qualify(contract, borrowed_locks=None):
    actual, manifest, prior = load()
    need(actual == contract, 'same pinned restored9fe epoch')
    proof = history(contract, manifest, prior)
    reader = Reader(480)
    with joint_locks(reader, contract['current_locks'], borrowed_locks) as (held, observed):
        proof.update(current(contract, manifest, prior))
        for fd, row in zip(held, observed):
            need(F9(os.fstat(fd)) == row['identity'], 'same actual restored9fe source lease')
            reader.pinned(row)
        reader.pinned(contract['source_manifest'])
        proof.update(current_locks=observed, current_source_manifest=contract['source_manifest'], production_variant='user', release_source_label='cp2a', CP3A_source_equivalence_qualified=False, source_writes=0, full_builds_started=0)
    return proof
