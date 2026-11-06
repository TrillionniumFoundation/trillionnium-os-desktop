#!/usr/bin/env python3
"""Compile exact retirement sources and host controls, leave the full Wayland check to its separate gate; never run Android."""
import ctypes
import datetime
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import select
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
import tomllib

ROOT = Path("/home/alex/work/p4-retirement-ack-host01-20261106")
HERE = ROOT/'control-source'
OUT = ROOT/'attempt01'
COPIED = ROOT/'builder-source'
FIXTURE = ROOT/'host-fixture'
BASE_SOURCE = Path('/home/alex/work/pocket4-native-typed-ingress-builder469-hal-provider-closure-compile-01-20261106/builder-source')
RUST_SYSROOT = Path('/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu')
CARGO_HOME = Path('/home/alex/.cargo')
TOOLCHAIN = '1.93.0'
OBSERVATION = '60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb'
PARENT_MANIFEST_SHA = '88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701'
CANDIDATE_MANIFEST_SHA = "3f2320687f074d48b19bc5284e6ba665a6cfaeb7adab9d59f519de5f3c96d2f4"
CONTROL_PATH = 'graphics/droidloom-composer-service/src/control.rs'
PROVIDER_PATH = 'graphics/droidloom-composer-aidl/src/denial.rs'
ENGINE_PATH = 'graphics/droidloom-wayland/src/retirement.rs'
SOURCE_PINS = {"candidate-protocol.rs":{"path":"graphics/droidloom-denial-protocol/src/lib.rs","bytes":105464,"sha256":"6c7f8df133f2a9e55bd375da4b39dcba5b00d0c4c3ba6531a6b8be329ebce41c"},"candidate-endpoint.rs":{"path":"graphics/droidloom-denial-endpoint/src/lib.rs","bytes":63752,"sha256":"062b65857160eb6e3aeba2a78c4ce3d8503c02572f24353f8c944d950e52308c"},"candidate-engine-retirement.rs":{"path":"graphics/droidloom-wayland/src/retirement.rs","bytes":11118,"sha256":"383f4c6f7490c8568f1853af6e9449fdb35bdb088348de4a9856d75f97306873"},"candidate-wayland-main.rs":{"path":"graphics/droidloom-wayland/src/main.rs","bytes":110131,"sha256":"0f56264e971db9f246d8db34d7fd5de157fd389a97bfb34492a6f53376d27459"},"candidate-wayland-layers.rs":{"path":"graphics/droidloom-wayland/src/layers.rs","bytes":35990,"sha256":"d0a81ce5339c5020496e9b73e007d52ee206449827269b272e4ef6ef43df5ecc"},"candidate-provider.rs":{"path":"graphics/droidloom-composer-aidl/src/denial.rs","bytes":50513,"sha256":"d6f13720da4267ff46f369617faecbb8c6446eca2c624e381c1ff51ddaebbf09"},"candidate-core-denial.rs":{"path":"graphics/droidloom-composer/src/denial.rs","bytes":25541,"sha256":"ed0080cd33a3a4fa67b3a0c2e95bc274ab38e992ec073ab01d87b910bf2db3c8"},"candidate-composer-main.rs":{"path":"graphics/droidloom-composer-service/src/main.rs","bytes":19202,"sha256":"567c60fd293f35e2e0957db6f38bc967cc0c3fa90354b98491d461a7decdb4ce"},"candidate-control.rs":{"path":"graphics/droidloom-composer-service/src/control.rs","bytes":42491,"sha256":"d3d9f4b763a6e80b6549119e42b4d6c3c6ab7368359f3cc71d2e090f05a881ca"}}
FIXTURE_PINS = {"fixture-lib.rs":{"bytes":15599,"sha256":"1eaa3f082edf591062286e2c4ca65968cf5a9c5d107c8452187e21fcf97b1b23"},"fixture-Cargo.toml":{"bytes":937,"sha256":"f7bff80d8487493dfb69eab33998eb0dad0159d88ec49eac68676bc0c891e26b"},"transaction_tests.rs":{"bytes":23472,"sha256":"c87d314841ac50f00943ae9181505755e8f262f538144e6979a9b63e15ecf298"},"provider_tests.rs":{"bytes":22982,"sha256":"fc6b354d704683c0547a4465efbfc8a8b977a311b73e764efd80d086438d9502"},"handshake_under_test.rs":{"bytes":2764,"sha256":"6d338b84adc14ea8cef16f3d5d4ae3b776b10510fe2a57d0b4036481fbc96201"}}
FIXTURE_STATIC_PATHS = {'Cargo.toml','src/lib.rs','src/control_under_test.rs','src/provider_under_test.rs','src/engine_retirement.rs','src/handshake_under_test.rs','src/denial_protocol_contract.rs','src/denial_endpoint_contract.rs'}
TARGET_TESTS = {"pocket4_denial_retirement_ack_controls":["control::transaction_regressions::complete_direct_bind_commits_exact_registry_and_endpoints","control::transaction_regressions::complete_bound_reuse_performs_no_new_backend_calls","control::transaction_regressions::bound_reuse_rejects_different_package_or_android_display","control::transaction_regressions::pending_direct_marker_is_visible_before_denial_register","control::transaction_regressions::sink_bind_after_effect_error_rolls_back_exact_owned_object","control::transaction_regressions::composer_bind_after_effect_error_rolls_back_both_endpoints","control::transaction_regressions::real_registry_duplicate_failure_preserves_foreign_registration","control::transaction_regressions::denial_cleanup_error_preserves_primary_and_pending_progress","control::transaction_regressions::composer_cleanup_retry_skips_already_destroyed_denial_channel","control::transaction_regressions::repeated_composer_cleanup_error_keeps_success_checkpoint","control::transaction_regressions::activation_error_keeps_complete_bound_and_allows_reuse","control::transaction_regressions::reserved_without_endpoint_calls_cancels_without_backend_cleanup","control::transaction_regressions::composer_stage_after_effect_error_cleans_only_invoked_endpoint","control::transaction_regressions::composer_stage_error_without_effect_does_not_infer_absence_from_error","control::transaction_regressions::denial_register_after_effect_error_cleans_both_owned_endpoints","control::transaction_regressions::denial_register_error_missing_local_channel_stays_unresolved","control::transaction_regressions::configure_timeout_preserves_cleanup_error_and_explicit_retirement","control::transaction_regressions::rollback_refuses_complete_bound_registration","control::transaction_regressions::rollback_refuses_changed_reservation_identity_before_backend_calls","control::transaction_regressions::retirement_rejects_progress_for_another_display","control::transaction_regressions::retired_object_with_residual_mapping_is_not_accepted_as_clean","control::transaction_regressions::backend_calls_hold_operation_gate_but_never_state_mutex","control::transaction_regressions::invalid_task_identity_does_not_allocate_or_call_backends","control::transaction_regressions::completed_retirement_is_idempotent_without_repeating_backend_calls","control::transaction_regressions::after_destroy_error_is_not_promoted_to_a_success_checkpoint","control::transaction_regressions::endpoint_call_record_is_required_for_bound_reuse","control::transaction_regressions::removal_checkpoint_cannot_be_reversed","real_provider::tests::android_display_extent_remains_the_hotplug_size","real_provider::tests::android_display_extent_rejects_empty_configures","real_provider::retirement_provider_tests::duplicate_display_cannot_destroy_another_real_provider_owner","real_provider::retirement_provider_tests::duplicate_object_on_another_display_has_no_claim_or_remote_effect","real_provider::retirement_provider_tests::local_timeline_creation_failure_has_exact_no_send_cleanup_proof","real_provider::retirement_provider_tests::local_descriptor_export_failure_retains_primary_until_exact_cleanup","real_provider::retirement_provider_tests::create_send_failure_does_not_erase_the_potential_remote_owner","real_provider::retirement_provider_tests::bind_timelines_send_failure_retains_partial_state_without_legacy_destroy","real_provider::retirement_provider_tests::retirement_waits_for_the_same_socket_object_and_nonce_receipt","real_provider::retirement_provider_tests::old_peer_cannot_enter_registration_or_gain_a_legacy_destroy_fallback","real_provider::retirement_provider_tests::wrong_receipt_object_or_nonce_cannot_complete_the_pending_owner","real_provider::retirement_provider_tests::foreign_socket_instance_is_rejected_before_pending_state_changes","real_provider::retirement_provider_tests::unrequested_receipt_cannot_retire_a_live_channel","real_provider::retirement_provider_tests::nonce_exhaustion_does_not_wrap_or_send_a_replayed_request","real_provider::retirement_provider_tests::timeout_retains_resources_and_late_ack_finishes_without_resending","real_provider::retirement_provider_tests::disconnect_wakes_waiter_without_turning_eof_into_a_receipt","real_provider::retirement_provider_tests::failed_retire_send_preserves_attempt_and_primary_without_resending","real_provider::retirement_provider_tests::receipt_with_accepted_frames_outstanding_is_rejected_without_erasure","real_provider::retirement_provider_tests::local_reservation_survives_receipt_until_real_cancel_path_wakes_waiter","real_provider::retirement_provider_tests::duplicate_receipt_does_not_upgrade_or_erase_reserved_local_resources","real_provider::retirement_provider_tests::retirement_rejects_new_binding_activation_target_and_layer_work","real_provider::retirement_provider_tests::partial_registration_rejects_live_work_until_explicit_retirement","real_provider::retirement_provider_tests::late_target_metadata_does_not_replace_retirement_resource_accounting","real_provider::retirement_provider_tests::late_configure_cannot_send_after_retire_or_publish_new_session_state","real_provider::retirement_provider_tests::same_object_later_registration_rejects_previous_retirement_receipt","real_provider::retirement_provider_tests::real_core_release_path_drains_a_retiring_accepted_frame_before_receipt","engine_retirement::tests::engine_drain_and_exact_callback_both_precede_completion","engine_retirement::tests::engine_live_object_blocks_callback_without_consuming_it","engine_retirement::tests::engine_wrong_object_or_nonce_cannot_complete_owned_request","engine_retirement::tests::engine_wrong_callback_preserves_original_barrier","engine_retirement::tests::engine_disconnected_callback_produces_no_completion","engine_retirement::tests::engine_old_peer_callback_cannot_complete_identical_new_tuple","engine_retirement::tests::engine_duplicate_callback_cannot_retry_failed_ack_attempt","engine_retirement::tests::engine_finish_without_callback_is_rejected","engine_retirement::tests::engine_duplicate_object_cannot_replace_original_nonce","engine_retirement::tests::engine_replayed_callback_after_finish_has_no_owner","engine_retirement::tests::engine_bound_limits_reject_capacity_and_generation_wrap","engine_retirement::tests::engine_invalid_identity_and_disconnected_requests_do_not_allocate","handshake_under_test::tests::current_minor_and_capability_are_both_required","handshake_under_test::tests::activation_is_independent_and_does_not_replace_retirement","handshake_under_test::tests::incomplete_base_capabilities_are_rejected","handshake_under_test::tests::wrong_major_or_unexpected_message_cannot_enable_retirement"],"denial_protocol_contract":["tests::retirement_records_round_trip_exact_object_nonce_and_minor","tests::retirement_rejects_zero_object_and_zero_nonce_in_both_directions","tests::retirement_rejects_legacy_header_version_even_with_known_new_opcode","tests::retirement_rejects_descriptors_direction_and_payload_extensions","tests::retirement_capability_requires_selected_minor_five","tests::retirement_advertisement_keeps_legacy_hello_and_destroy_headers","tests::activation_does_not_raise_the_wire_version_of_legacy_handshakes","tests::android_control_messages_round_trip","tests::buffer_registration_names_exact_plane_descriptor_roles","tests::host_render_target_registration_names_exact_plane_descriptor_roles","tests::timeline_descriptors_are_shared_once_in_fixed_order","tests::steady_state_present_is_descriptor_free","tests::denial_task_state_round_trips","tests::format_feedback_and_all_input_variants_round_trip","tests::error_message_may_be_connection_or_task_scoped","tests::framing_rejects_mutation_and_direction_confusion","tests::malformed_identity_and_unbounded_damage_fail_closed","tests::trailing_payload_and_unknown_header_bits_are_fatal","tests::task_receiver_caches_import_and_releases_only_after_signal","tests::task_receiver_rejects_unbound_and_stale_configure_presents","tests::superseded_configure_ack_is_coalesced_without_acknowledging_latest","tests::superseded_present_is_released_without_reviving_a_retired_buffer","tests::task_receiver_rejects_point_regression_and_release_mismatch"],"denial_endpoint_contract":["tests::listener_authenticates_exact_kernel_peer_before_protocol","tests::exact_peer_policy_rejects_every_identity_mismatch","tests::development_pid_wildcard_keeps_uid_and_gid_exact","tests::hello_selects_required_v1_capabilities","tests::activation_requires_mutual_support_and_a_bound_live_task","tests::every_android_task_becomes_an_independent_native_action","tests::task_messages_before_hello_fail_closed","retirement_tests::retirement_requires_mutual_capability_before_request","retirement_tests::retirement_receipt_requires_the_real_engine_completion_call","retirement_tests::retirement_frame_release_alone_does_not_confirm_engine_removal","retirement_tests::retirement_engine_callback_with_inflight_frame_is_rejected","retirement_tests::retirement_foreign_object_and_nonce_preserve_pending_owner","retirement_tests::retirement_duplicate_and_old_nonce_requests_cannot_reopen_a_completed_retirement","retirement_tests::retirement_absent_partial_create_still_requires_engine_absence_confirmation","retirement_tests::retirement_blocks_new_work_without_consuming_its_pending_tuple","retirement_tests::retirement_disconnect_during_receipt_keeps_failed_attempt_and_prevents_resend","retirement_tests::retirement_duplicate_completion_never_acknowledges_a_later_object","retirement_tests::retirement_nonce_exhaustion_never_wraps_to_a_replayed_request","retirement_tests::retirement_capability_cannot_downgrade_to_legacy_destroy","retirement_tests::retirement_pending_absence_and_live_creation_share_one_capacity_bound"]}
TESTS = [target+'::'+name for target,names in TARGET_TESTS.items() for name in names]
PATH_PACKAGES = {"droidloom-composer":"graphics/droidloom-composer","droidloom-task-control":"graphics/droidloom-task-control","droidloom-denial-protocol":"graphics/droidloom-denial-protocol","droidloom-denial-ipc":"graphics/droidloom-denial-ipc","droidloom-transport":"graphics/droidloom-transport","droidloom-syncobj":"graphics/droidloom-syncobj","droidloom-cpu-placement":"runtime/droidloom-cpu-placement"}
FIXTURE_NAME = 'pocket4-denial-retirement-ack-controls'
SOURCE_MAP = {}
DEADLINE = None
CHILD_REAPER = None
OBSERVED_SIGNALS = []

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def identity(st):
    return [st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns]

def held(path, maximum=4*1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'unexpected file type/size: '+str(path))
        parts = []
        total = 0
        while total <= maximum:
            chunk = os.read(fd, min(65536, maximum+1-total))
            if not chunk:
                break
            parts.append(chunk)
            total += len(chunk)
        data = b''.join(parts)
        require(total == before.st_size and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()), 'source changed during read: '+str(path))
        return data, {'path': str(path), 'bytes': total, 'sha256': sha(data), 'identity': identity(before)}
    finally:
        os.close(fd)

def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(data, bytes):
        data = (json.dumps(data, indent=2, sort_keys=True)+'\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}

def real_directory(path):
    for item in (path, *path.parents):
        require(stat.S_ISDIR(item.lstat().st_mode), 'directory alias rejected: '+str(item))


def resource_text(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        raw = os.read(fd, 32769)
        require(len(raw) <= 32768, 'owned resource observation exceeds bound')
        return raw.decode('ascii').strip()
    finally:
        os.close(fd)

def resource_events(text):
    rows = [line.split() for line in text.splitlines()]
    require(rows and all(len(row) == 2 and row[1].isdigit() for row in rows), 'malformed owned memory.events')
    events = {row[0]:int(row[1]) for row in rows}
    require(len(events) == len(rows) and all(k in events for k in ['oom','oom_kill','oom_group_kill']), 'incomplete or duplicate owned memory.events')
    return events

def resource_snapshot(directory_fd, membership):
    observed = Path('/proc/self/cgroup').read_text().strip()
    require(observed == membership, 'controller cgroup membership changed')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    held_st = os.fstat(directory_fd)
    named_st = path.lstat()
    require(stat.S_ISDIR(held_st.st_mode) and stat.S_ISDIR(named_st.st_mode) and
            (held_st.st_dev,held_st.st_ino) == (named_st.st_dev,named_st.st_ino), 'owned invocation cgroup identity changed')
    fields = {name:resource_text(directory_fd,name) for name in [
        'cgroup.procs','memory.events','memory.current','memory.peak','memory.high','memory.max',
        'memory.swap.current','memory.swap.peak','memory.swap.max','cpu.max']}
    require(str(os.getpid()) in fields['cgroup.procs'].split(), 'controller is not in the held invocation')
    require(fields['memory.max'] == '1073741824' and fields['cpu.max'] == '100000 100000', 'owned resource limits do not match the request')
    for key in ['memory.current','memory.peak','memory.swap.current','memory.swap.peak']:
        require(fields[key].isdigit(), 'invalid owned resource counter: '+key)
    return {'observed_utc':utc(), 'membership':membership, 'path':str(path),
            'directory_identity':[held_st.st_dev,held_st.st_ino],
            'controller_pid':os.getpid(), 'fields':fields, 'events':resource_events(fields['memory.events'])}

def begin_resources():
    membership = Path('/proc/self/cgroup').read_text().strip()
    require('\n' not in membership and membership.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'), 'not the exact owned user invocation')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    require(path.name.startswith('hepta-runtime-job-') and path.name.endswith('.service') and '..' not in path.parts, 'unexpected owned unit path')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = resource_snapshot(fd,membership)
        require(all(before['events'][k] == 0 for k in ['oom','oom_kill','oom_group_kill']), 'owned invocation already recorded OOM before the control')
        return fd,before
    except BaseException:
        os.close(fd)
        raise

def finish_resources(directory_fd, before, report):
    after = resource_snapshot(directory_fd,before['membership'])
    report['owned_resources_after'] = after
    report['owned_memory_peak'] = int(after['fields']['memory.peak'])
    report['owned_memory_swap_peak'] = int(after['fields']['memory.swap.peak'])
    require(after['directory_identity'] == before['directory_identity'], 'owned cgroup object replaced')
    require(set(before['events']) == set(after['events']), 'owned memory event fields changed')
    delta = {key:after['events'][key]-value for key,value in before['events'].items()}
    report['owned_memory_events_delta'] = delta
    require(all(value >= 0 for value in delta.values()), 'owned memory event counters went backwards')
    require(all(delta[key] == 0 for key in ['oom','oom_kill','oom_group_kill']), 'owned OOM event occurred; control is not qualified')
    require(all(before['fields'][key] == after['fields'][key] for key in ['memory.max','memory.high','memory.swap.max','cpu.max']), 'owned cgroup limits changed during control')
    return {'pass':True, 'before':before, 'after':after, 'memory_events_delta':delta,
            'memory_peak':int(after['fields']['memory.peak']), 'memory_swap_peak':int(after['fields']['memory.swap.peak']),
            'resource_settings_changed':False, 'swap_max_observed_only':after['fields']['memory.swap.max']}


def hash_held(path, maximum=512*1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'unexpected held file type/size: '+str(path))
        digest = hashlib.sha256()
        total = 0
        while True:
            raw = os.read(fd,65536)
            if not raw:
                break
            total += len(raw)
            require(total <= maximum, 'held file grew beyond bound: '+str(path))
            digest.update(raw)
        require(total == before.st_size and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
                'held file changed: '+str(path))
        return {'path':str(path),'bytes':total,'sha256':digest.hexdigest(),'identity':identity(before)}
    finally:
        os.close(fd)

def regular_tree(root, file_bound=2048, byte_bound=32*1024*1024):
    real_directory(root)
    rows = {}
    total = 0
    def walk_error(error):
        raise error
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=walk_error):
        dirs.sort()
        for name in dirs:
            path=Path(directory)/name
            require(stat.S_ISDIR(path.lstat().st_mode),'source directory alias rejected: '+str(path))
        for name in sorted(files):
            path=Path(directory)/name
            relative=str(path.relative_to(root))
            require(relative not in rows and len(rows)<file_bound,'source inventory bound or duplicate')
            row=hash_held(path)
            total+=row['bytes']
            require(total<=byte_bound,'source inventory byte bound exceeded')
            rows[relative]=row
    require(rows,'empty source inventory: '+str(root))
    return rows

def portable(rows, expected):
    require(set(rows)==set(expected),'complete source path set changed')
    result={}
    for name in expected:
        row=rows[name]
        result[name]={'kind':'file','sha256':row['sha256'],'bytes':row['bytes'],
                      'mode':stat.S_IMODE(row['identity'][2])}
    require(result==expected,'complete source manifest differs')
    return result

def pinned_packet(name, digest):
    raw,row=held(HERE/name,1024*1024)
    require(row['sha256']==digest,'staged input changed: '+name)
    return raw,row

def exact_source_copy(expected):
    before=regular_tree(BASE_SOURCE)
    portable(before,expected)
    require(not COPIED.exists() and not COPIED.is_symlink(),'create-only builder copy already exists')
    COPIED.mkdir(mode=0o700)
    for name,row in before.items():
        data,pin=held(BASE_SOURCE/name,4*1024*1024)
        require(pin==row,'original source changed while copying: '+name)
        destination=COPIED/name
        write_new(destination,data)
        os.chmod(destination,stat.S_IMODE(row['identity'][2]),follow_symlinks=False)
    copied=regular_tree(COPIED)
    portable(copied,expected)
    require(regular_tree(BASE_SOURCE)==before,'original source changed during copy')
    return before,copied

def read_existing_config(paths):
    rows=[]
    for path in paths:
        try:
            path.lstat()
        except FileNotFoundError:
            rows.append({'path':str(path),'absent':True})
            continue
        rows.append(hash_held(path,1024*1024))
    return rows

def pin_resolved(path, allowed):
    resolved=path.resolve(strict=True)
    require(any(resolved.is_relative_to(root) for root in allowed) or resolved==Path('/usr/libexec/gcc/x86_64-linux-gnu/15/collect2'),
            'resolved tool/library outside allowed roots/exact observed collect2: '+str(path))
    row=hash_held(resolved)
    row['requested_path']=str(path)
    row['resolved_path']=str(resolved)
    require(path.resolve(strict=True)==resolved,'tool resolution changed during observation')
    return row

def verify_resolved(rows):
    changes=[]
    for row in rows:
        try:
            path=Path(row['requested_path'])
            resolved=path.resolve(strict=True)
            after=hash_held(resolved)
            if str(resolved)!=row['resolved_path'] or after!={k:row[k] for k in ['path','bytes','sha256','identity']}:
                changes.append(str(path))
        except Exception as error:
            changes.append({'path':row['requested_path'],'error':repr(error)})
    return changes

def toolchain(report, base_env):
    observation,observation_pin=pinned_packet('rust193-tools-recheck-read03-result.json',OBSERVATION)
    actual=json.loads(observation)
    require(actual['state']=='PASS_FIXED_TOOL_OBSERVATION_NOT_EXECUTION_APPROVAL' and
            actual['complete'] is True and actual['repository_channel']==TOOLCHAIN and
            actual['repository_toolchain']['sha256']=='8bc51ecab82415fddd8489604f2424e137d71856e7f65cbdcfaa48850d794b46' and
            actual['all_observed_tool_contents_and_aliases_unchanged_after'] is True and
            actual['owned_resource_gate']['pass'] is True and actual['first_error'] is None and
            not actual['secondary_errors'] and actual['commands_executed']==0 and actual['tool_execution'] is False,
            'fixed installed toolchain reobservation is not complete')
    previous,previous_pin=pinned_packet('prior-compile01-failure.json',
            '44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3')
    failed=json.loads(previous)
    require(previous_pin['bytes']==7681 and actual['actual_build_failure']==
                {'bytes':previous_pin['bytes'],'sha256':previous_pin['sha256']} and
            failed['state']=='FAIL' and failed['commands']==[] and
            failed['error']=="RuntimeError('observed tool changed before compilation: /home/alex/.cargo/bin/rustup')" and
            not failed['cleanup']['errors'] and not failed['cleanup']['remaining'] and
            not failed['cleanup']['forced_cleanup'],
            'prior compile01 failure authority differs')
    observed={r['requested_path']:r for r in actual['tools']}
    proxy='/home/alex/.cargo/bin/rustup'
    require(len(observed)==len(actual['tools'])==12 and proxy in observed and
            actual['changed_tools']==[{'changed_admission_fields':['sha256','bytes'],
                'original_object_metadata_equal':False,'path':proxy}],
            'reobservation is not the exact single proxy-content change')
    require(all(row['error'] is None and row['content_read'] is True and
                row['resolution_changed'] is False and
                row['held_before']==row['held_after']==row['resolved_named_after'] and
                row['requested_named_before']==row['requested_named_after'] and
                row['requested_link_text_before']==row['requested_link_text_after']
                for row in actual['tools']),
            'fixed observed tool closure changed during reobservation')
    expected={path:row for path,row in observed.items() if path!=proxy}
    require(len(expected)==11 and all(row['compilation_admission_fields_equal'] is True and
                row['changed_compilation_admission_fields']==[] and
                row['original_object_metadata_equal'] is True for row in expected.values()),
            'a directly used tool differs from the original installed authority')
    require(not any(name.startswith('RUSTUP') for name in base_env) and
            all(name not in base_env for name in ('LD_PRELOAD','LD_LIBRARY_PATH','RUSTC_BOOTSTRAP')) and
            base_env['PATH']=='/usr/bin:/bin' and
            base_env['RUSTC']==str(RUST_SYSROOT/'bin/rustc') and
            base_env['RUSTDOC']==str(RUST_SYSROOT/'bin/rustdoc'),
            'direct toolchain environment contains a proxy selection or inherited override')
    real_directory(RUST_SYSROOT)
    allowed=[Path('/usr/bin'),Path('/usr/lib'),RUST_SYSROOT]
    rows=[]
    for path,wanted in expected.items():
        row=pin_resolved(Path(path),allowed)
        require(row['sha256']==wanted['sha256'] and row['bytes']==wanted['bytes'] and
                row['resolved_path']==wanted['resolved_path'],
                'observed direct tool changed before compilation: '+path)
        rows.append(row)
    selected={name:RUST_SYSROOT/'bin'/name for name in ['cargo','rustc','rustdoc']}
    for name in ['cargo','rustc']:
        path=selected[name]
        require(str(path) in expected and path.resolve(strict=True)==path and
                expected[str(path)]['resolved_path']==str(path),
                'direct compiler path differs from the fixed Rust 1.93 authority: '+name)
    # No doctest is requested. Bind the absolute RUSTDOC path to the same
    # installed sysroot closure now and recheck it with all other tool inputs.
    # Its bytes were not included in the old read02/read03 observation.
    rustdoc=pin_resolved(selected['rustdoc'],allowed)
    require(rustdoc['resolved_path']==str(selected['rustdoc']) and
            stat.S_ISREG(rustdoc['identity'][2]) and rustdoc['identity'][2]&0o111,
            'fixed sysroot rustdoc is aliased or not an executable regular file')
    rows.append(rustdoc)
    sysroot=RUST_SYSROOT
    require(selected['cargo'].parent.parent==selected['rustc'].parent.parent==sysroot,
            'cargo/rustc toolchain mismatch')
    cargo_version=command([str(selected['cargo']),'--version'],COPIED,base_env,'cargo-version',report['commands'],10).decode()
    rustc_version=command([str(selected['rustc']),'-vV'],COPIED,base_env,'rustc-version',report['commands'],10).decode()
    require(cargo_version.startswith('cargo '+TOOLCHAIN+' ') and '\nrelease: '+TOOLCHAIN+'\n' in rustc_version,
            'actual toolchain version differs from repository pin')
    for path in [Path('/usr/bin/git'),Path('/usr/bin/timeout'),Path('/usr/bin/ninja'),Path('/usr/bin/cp'),Path('/usr/bin/ldd')]:
        rows.append(pin_resolved(path,allowed))
    library_rows=regular_tree(sysroot/'lib/rustlib/x86_64-unknown-linux-gnu/lib',512,1536*1024*1024)
    for row in library_rows.values():
        row.update({'requested_path':row['path'],'resolved_path':row['path']})
        rows.append(row)
    for path in sorted((sysroot/'lib').glob('*.so*')):
        rows.append(pin_resolved(path,allowed))
    linked=set()
    for index,path in enumerate([selected['cargo'],selected['rustc'],Path('/usr/bin/cc'),Path('/usr/bin/ld'),
                                Path('/usr/bin/git'),Path('/usr/bin/timeout'),Path('/usr/bin/ninja'),selected['rustdoc']]):
        raw=command(['/usr/bin/ldd',str(path)],COPIED,base_env,'linked-libraries-'+str(index),report['commands'],10).decode()
        require('not found' not in raw,'tool runtime library missing')
        for line in raw.splitlines():
            match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
            if match:
                linked.add(match.group(1))
    for name in sorted(linked):
        rows.append(pin_resolved(Path(name),allowed+[Path('/usr/lib'),Path('/lib')]))
    unique={row['requested_path']:row for row in rows}
    require(proxy not in unique,'unused rustup proxy was retained as a compilation input')
    report['actual_tool_reobservation']=observation_pin
    report['prior_compile01_failure_authority']=previous_pin
    report['unused_proxy_observation']={key:observed[proxy][key] for key in
            ['requested_path','resolved_path','bytes','sha256','changed_compilation_admission_fields']}
    report['actual_toolchain']={'repository_version':TOOLCHAIN,'cargo':str(selected['cargo']),
            'rustc':str(selected['rustc']),'rustdoc':str(selected['rustdoc']),
            'cargo_version':cargo_version,'rustc_verbose_version':rustc_version,
            'selection':'explicit observed installed 1.93 cargo/rustc paths; no rustup command',
            'selection_installs_or_updates':False,'global_stable_1_95_not_used':True,
            'rustup_proxy_executed':False,'rustup_proxy_is_compilation_input':False,
            'rustup_proxy_changed_bytes_approved_for_execution':False,
            'rustdoc_observed_with_sysroot_closure_this_attempt':rustdoc,
            'rustdoc_old_hash_prequalified':False,'doctests_requested':False}
    return selected,list(unique.values())


def qualify_cached_archive(archive,directory,name,version,expected):
    fd=os.open(archive,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0<before.st_size<=32*1024*1024,'archive type/size outside bound')
        digest=hashlib.sha256();size=0
        while True:
            chunk=os.read(fd,65536)
            if not chunk:break
            size+=len(chunk);require(size<=32*1024*1024,'archive grew beyond bound');digest.update(chunk)
        archive_pin={'path':str(archive),'bytes':size,'sha256':digest.hexdigest(),'identity':identity(before)}
        require(size==before.st_size and digest.hexdigest()==expected,'existing archive checksum differs from original Cargo.lock')
        source_before=regular_tree(directory,4096,64*1024*1024)
        os.lseek(fd,0,os.SEEK_SET)
        files={};directories=set();total=0;prefix=name+'-'+version+'/'
        with os.fdopen(os.dup(fd),'rb') as stream,tarfile.open(fileobj=stream,mode='r:gz') as packed:
            for member in packed:
                require(time.monotonic()<DEADLINE,'bounded registry observation deadline exhausted')
                if member.isdir() and member.name.rstrip('/')==name+'-'+version:
                    require('' not in directories,'duplicate archive root directory')
                    directories.add('');continue
                require(member.name.startswith(prefix) and not member.name.startswith('/'),'unexpected archive root')
                relative=member.name[len(prefix):]
                path=PurePosixPath(relative)
                require(relative and '..' not in path.parts and str(path)==relative.rstrip('/'),'noncanonical archive member')
                require(len(files)+len(directories)<4096,'archive member count exceeds bound')
                if member.isdir():
                    require(relative not in directories,'duplicate archive directory')
                    directories.add(relative);continue
                require(member.isfile() and relative not in files,'archive alias, special file or duplicate rejected')
                require(0<=member.size<=16*1024*1024 and total+member.size<=64*1024*1024,'archive expansion exceeds bound')
                reader=packed.extractfile(member);require(reader is not None,'archive regular member unreadable')
                member_hash=hashlib.sha256();member_size=0
                while True:
                    chunk=reader.read(65536)
                    if not chunk:break
                    member_size+=len(chunk);require(member_size<=member.size,'archive member exceeded declared size');member_hash.update(chunk)
                require(member_size==member.size,'archive member truncated')
                total+=member_size
                require(relative in source_before and source_before[relative]['bytes']==member_size and
                        source_before[relative]['sha256']==member_hash.hexdigest(),'extracted source differs from locked archive: '+str(directory/relative))
                files[relative]={'bytes':member_size,'sha256':member_hash.hexdigest(),'extracted':source_before[relative]}
        require(files,'empty source archive')
        extra={name:row for name,row in source_before.items() if name not in files}
        require(regular_tree(directory,4096,64*1024*1024)==source_before,'extracted source changed during archive comparison')
        require(identity(before)==identity(os.fstat(fd))==identity(archive.lstat()),'archive changed during comparison')
        comparison={'archive':archive_pin,'archive_matches_lock':True,'archive_files':len(files),'archive_bytes':total,
                'every_archive_file_matches_held_extracted_source':True,'extra_extracted_files':extra,
                'extra_files_are_only_cargo_marker':set(extra)<=set(['.cargo-ok']),
                'source_inventory':write_new(OUT/(name+'-'+version+'-source.json'),{'archive_files':files,'extras':extra}),
                'source_unchanged_after':True}
        require(set(extra)=={'.cargo-ok'} and extra['.cargo-ok']['bytes']==7 and
                extra['.cargo-ok']['sha256']=='afbf9d0f3560b0fd7795e81c42a0a79ee6b6fc67e064f77826aee642cad28d91',
                'extracted package has unqualified extra files or an altered Cargo marker')
        return comparison,source_before,archive_pin
    finally:os.close(fd)


def limit_child_outputs():
    # Cargo artifacts need more than the C-only fixture's 256 KiB file ceiling.
    # Stdout/stderr still have independent complete-capture bounds below.
    resource.setrlimit(resource.RLIMIT_FSIZE, (128*1024*1024, 128*1024*1024))


class OwnChildReaper:
    """Retire only children of this single-threaded isolated controller."""
    def __init__(self):
        self.pid = os.getpid()
        self.original = None
        self.changed = False
        self.active = False
        self.record = {'pid': self.pid, 'begin_passed': False, 'restored': False,
                       'final_children_empty': False, 'max_adopted_per_command': 128,
                       'cleanup_seconds_per_command': 5}
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.prctl = self.libc.prctl
        self.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                              ctypes.c_ulong, ctypes.c_ulong]
        self.prctl.restype = ctypes.c_int

    def flag(self):
        value = ctypes.c_int(-1)
        if self.prctl(37, ctypes.addressof(value), 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'PR_GET_CHILD_SUBREAPER')
        require(value.value in (0, 1), 'invalid own subreaper flag')
        return value.value

    def set_flag(self, value):
        if self.prctl(36, value, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER')

    def single_thread(self):
        require(os.getpid() == self.pid and signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,
                'controller PID/SIGCHLD ownership changed')
        names = []
        with os.scandir('/proc/%d/task' % self.pid) as rows:
            for row in rows:
                names.append(row.name)
                require(len(names) <= 1, 'controller is no longer single-threaded')
        require(names == [str(self.pid)], 'controller thread identity changed')

    def children(self):
        # Fixed self task only, never an all-/proc or other-actor enumeration.
        fd = os.open('/proc/%d/task/%d/children' % (self.pid, self.pid),
                     os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            data = os.read(fd, 8193)
            require(len(data) <= 8192 and os.read(fd, 1) == b'', 'own children list exceeds bound')
        finally:
            os.close(fd)
        fields = data.split()
        require(len(fields) <= 128 and len(fields) == len(set(fields)), 'own child count differs')
        require(all(x.isdigit() and x == str(int(x)).encode() and 0 < int(x) < 2**31
                    for x in fields), 'malformed own children list')
        return [int(x) for x in fields]

    def empty(self):
        self.single_thread()
        require(self.children() == [], 'controller retains child processes')
        try:
            os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            return True
        raise RuntimeError('kernel wait authority did not confirm ECHILD')

    def begin(self):
        require(hasattr(os, 'P_PIDFD') and hasattr(os, 'WNOWAIT'), 'held nonreaping wait unavailable')
        self.empty()
        self.original = self.flag()
        self.record['original_subreaper_flag'] = self.original
        if self.original == 0:
            self.set_flag(1)
            self.changed = True
        require(self.flag() == 1, 'own subreaper did not become active')
        self.active = True
        self.record['begin_passed'] = True

    def before_command(self):
        require(self.active and self.flag() == 1, 'own subreaper not active')
        self.empty()

    def finish(self):
        self.empty()
        self.record['final_children_empty'] = True
        if self.original is not None:
            require(self.flag() == 1, 'own subreaper flag changed during commands')
            if self.changed:
                self.set_flag(self.original)
                self.changed = False
            require(self.flag() == self.original, 'own subreaper flag not restored')
        self.active = False
        self.record['restored'] = True

    @staticmethod
    def peek(pid, pidfd):
        info = os.waitid(os.P_PIDFD if pidfd is not None else os.P_PID,
                         pidfd if pidfd is not None else pid,
                         os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if info is not None:
            require(info.si_pid == pid and info.si_code in
                    (os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED),
                    'owned child wait status differs')
        return info

    @staticmethod
    def observed(info):
        return {'pid': info.si_pid, 'code': info.si_code, 'status': info.si_status}

    def await_exit(self, pid, pidfd, deadline):
        poller = select.poll()
        poller.register(pidfd, select.POLLIN)
        while True:
            info = self.peek(pid, pidfd)
            if info is not None:
                return info
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('owned child exit deadline')
            poller.poll(max(1, min(100, int(remaining * 1000))))

    def retire(self, process, pidfd, record, remember, deadline):
        record['descendants'] = []
        record['owned_tree_cleanup_complete'] = False
        try:
            # WNOWAIT / direct-child relationship reserves the leader PID until
            # after group signalling. No killpg occurs after leader reaping.
            info = self.peek(process.pid, pidfd)
            record['leader_unreaped_before_group_cleanup'] = True
            record['leader_alive_before_group_cleanup'] = info is None
            if info is not None:
                record['leader_observed_before_reap'] = self.observed(info)
            require(os.getpgid(process.pid) == process.pid and
                    os.getsid(process.pid) == process.pid, 'owned session/group identity changed')
            record['owned_group_kill_attempted'] = True
            record['kill_attempted'] = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
                record['owned_group_kill_completed'] = True
            except ProcessLookupError:
                require(info is not None, 'live original group disappeared')
                record['owned_group_already_absent'] = True
        except Exception as error:
            remember(error, 'owned_group_cleanup')
            # If group qualification failed, kill only the known direct child.
            try:
                if self.peek(process.pid, pidfd) is None:
                    if pidfd is not None:
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    else:
                        # The successful P_PID wait above proves this is still
                        # this controller's unreaped child, so its PID cannot be reused.
                        process.kill()
                    record['direct_child_fallback_kill_attempted'] = True
            except Exception as error:
                remember(error, 'direct_child_fallback_cleanup')
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
            record['returncode'] = process.returncode
            record['child_reaped'] = True
        except Exception as error:
            remember(error, 'reap_direct_child')
        if not record['child_reaped']:
            return
        seen = set()
        while True:
            try:
                children = self.children()
                if not children:
                    self.empty()
                    record['owned_tree_cleanup_complete'] = True
                    break
                require(time.monotonic() < deadline, 'adopted child cleanup deadline')
                require(not (set(children) & seen), 'an earlier adopted child was not reaped')
                require(len(seen) + len(children) <= 128, 'adopted child total bound exceeded')
            except Exception as error:
                remember(error, 'adopted_child_list_or_gate')
                break
            complete = True
            for child in children:
                if time.monotonic() >= deadline:
                    remember(TimeoutError('adopted child cleanup deadline'), 'adopted_child_deadline')
                    complete = False
                    break
                seen.add(child)
                item = {'pid': child, 'kill_attempted': False, 'reaped': False, 'pidfd_closed': True}
                record['descendants'].append(item)
                held = None
                try:
                    # The kernel-listed unreaped direct/adopted child cannot be
                    # reaped by another waiter: this controller is single-threaded.
                    try:
                        held = os.pidfd_open(child, 0)
                        item['pidfd_closed'] = False
                    except Exception as error:
                        # Keep this failure, but still retire the kernel-proven
                        # unreaped child if descriptor allocation itself failed.
                        item['pidfd_open_error'] = repr(error)
                        remember(error, 'adopted_pidfd_open')
                    info = self.peek(child, held)
                    if info is None:
                        item['kill_attempted'] = True
                        if held is not None:
                            signal.pidfd_send_signal(held, signal.SIGKILL)
                            info = self.await_exit(child, held, deadline)
                        else:
                            os.kill(child, signal.SIGKILL)
                            while info is None and time.monotonic() < deadline:
                                time.sleep(0.005)
                                info = self.peek(child, None)
                            require(info is not None, 'owned child fallback wait deadline')
                    item['observed_before_reap'] = self.observed(info)
                    waited, status = os.waitpid(child, os.WNOHANG)
                    require(waited == child, 'observed terminal adopted child was not reaped')
                    item['wait_status'] = status
                    item['reaped'] = True
                except Exception as error:
                    complete = False
                    item['error'] = repr(error)
                    remember(error, 'adopted_child_cleanup')
                finally:
                    if held is not None:
                        value, held = held, None
                        try:
                            os.close(value)
                            item['pidfd_closed'] = True
                        except Exception as error:
                            complete = False
                            remember(error, 'adopted_pidfd_close')
            if not complete:
                break
        record['cleanup_elapsed_seconds'] = time.monotonic() - (deadline - 5)
        if record['descendants']:
            # Successful drivers must normally reap their own helpers. Cleanup
            # success is not permission to count orphaned/forced helpers as a
            # successful compilation.
            remember(RuntimeError('driver left descendant processes after its exit'),
                     'driver_left_descendants')



def owned_command(report, root, argv, timeout=25, pidfd_factory=None, environment=None, cwd=None, label=None):
    index = len(report['commands'])
    output = root / ('command%02d.stdout' % index)
    error_path = root / ('command%02d.stderr' % index)
    record = {'argv': argv, 'cwd': str(cwd or root), 'label': label, 'timeout_seconds': timeout,
              'timed_out': False, 'child_started': False, 'child_reaped': False,
              'kill_attempted': False, 'pidfd_closed': True, 'output_fds_closed': False,
              'first_error': None, 'secondary_errors': [],
              'owned_tree_cleanup_complete': False}
    report['commands'].append(record)
    process = None
    pidfd = None
    streams = []
    first = None

    def remember(error, stage):
        nonlocal first
        item = {'stage': stage, 'error': repr(error)}
        if first is None:
            first = error
            record['first_error'] = item
        else:
            record['secondary_errors'].append(item)

    try:
        CHILD_REAPER.before_command()
        remaining = DEADLINE - time.monotonic()
        require(remaining > 0, 'controller work deadline expired before child admission')
        for path in (output, error_path):
            streams.append(path.open('xb'))
        require(type(environment) is dict and environment.get('CARGO_NET_OFFLINE') == 'true',
                'fixed offline child environment missing')
        process = subprocess.Popen(argv, cwd=cwd or root, stdin=subprocess.DEVNULL,
            stdout=streams[0], stderr=streams[1], close_fds=True, start_new_session=True,
            preexec_fn=limit_child_outputs, env=environment)
        record['pid'] = process.pid
        record['child_started'] = True
        pidfd = (pidfd_factory or os.pidfd_open)(process.pid, 0)
        record['pidfd_closed'] = False
        try:
            info = CHILD_REAPER.await_exit(process.pid, pidfd,
                time.monotonic() + min(timeout, remaining))
            record['leader_observed_without_reap'] = CHILD_REAPER.observed(info)
            if info.si_code != os.CLD_EXITED or info.si_status != 0:
                remember(RuntimeError('original command exited unsuccessfully before cleanup'),
                         'leader_exit_status')
        except TimeoutError:
            record['timed_out'] = True
            raise subprocess.TimeoutExpired(argv, timeout)
    except Exception as error:
        remember(error, 'start_or_wait')
    finally:
        if process is not None:
            cleanup_deadline = time.monotonic() + 5
            try:
                CHILD_REAPER.retire(process, pidfd, record, remember, cleanup_deadline)
            except Exception as error:
                remember(error, 'unexpected_owned_tree_cleanup_error')
                # Do not let an unexpected diagnostic error skip the direct
                # child's final wait. Group/adoption qualification stays false.
                try:
                    if process.returncode is None and CHILD_REAPER.peek(process.pid, pidfd) is None:
                        if pidfd is not None:
                            signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                        else:
                            process.kill()
                except Exception as error:
                    remember(error, 'final_direct_kill')
                try:
                    process.wait(timeout=max(0, cleanup_deadline - time.monotonic()))
                    record['returncode'] = process.returncode
                    record['child_reaped'] = True
                except Exception as error:
                    remember(error, 'final_direct_wait')
        if pidfd is not None:
            value, pidfd = pidfd, None
            try:
                os.close(value)
                record['pidfd_closed'] = True
            except Exception as error:
                remember(error, 'close_pidfd')
        closed = True
        for stream in reversed(streams):
            try:
                stream.close()
            except Exception as error:
                closed = False
                remember(error, 'close_output_file')
        record['output_fds_closed'] = closed
    # Each output is retained independently; a capture error cannot hide the
    # earlier child failure or prevent the other stream from being checked.
    for key, path in [('stdout', output), ('stderr', error_path)]:
        try:
            data, pin = held(path, 32*1024*1024 if key == 'stdout' else 4*1024*1024)
            record[key + '_bytes'] = len(data)
            record[key + '_sha256'] = pin['sha256']
            record[key + '_pin'] = pin
            record[key] = data.decode('utf-8')
            record[key + '_complete'] = True
        except Exception as error:
            record[key + '_complete'] = False
            remember(error, 'capture_' + key)
    if first is not None:
        raise first
    require(record.get('returncode') == 0 and record['child_reaped'] and
            record['pidfd_closed'] and record['output_fds_closed'] and
            record['owned_tree_cleanup_complete'] and not record['timed_out'],
            'matching build/control command failed: ' + str(index))
    return record



def command(argv, cwd, env, label, records, maximum_seconds=180):
    row = owned_command({'commands': records}, OUT, [str(x) for x in argv],
                        timeout=maximum_seconds, environment=env, cwd=cwd, label=label)
    raw = row.pop('stdout').encode('utf-8')
    row.pop('stderr')
    row['stdout'] = row.pop('stdout_pin')
    row['stderr'] = row.pop('stderr_pin')
    return raw


HOST_LIFECYCLE_FIXTURE = r"""import os
import sys
import time

mode = sys.argv[1]
if mode == 'pidfd-failure':
    time.sleep(30)
    raise SystemExit(0)
if mode not in ('timeout-descendant', 'escaped-descendant'):
    raise SystemExit(2)
read_end, write_end = os.pipe()
child = os.fork()
if child == 0:
    os.close(read_end)
    if mode == 'escaped-descendant':
        os.setsid()
    os.write(write_end, b'R')
    os.close(write_end)
    time.sleep(30)
    os._exit(0)
os.close(write_end)
if os.read(read_end, 1) != b'R':
    os._exit(3)
os.close(read_end)
print('READY %d %d' % (os.getpid(), child), flush=True)
if mode == 'escaped-descendant':
    os._exit(0)
time.sleep(30)
"""


def run_child_lifecycle_controls(report, root, environment):
    control_root = root / 'host-child-lifecycle-controls'
    control_root.mkdir(mode=0o700)
    report['host_child_lifecycle_controls'] = []
    modes = ('timeout-descendant', 'escaped-descendant', 'pidfd-failure')
    for index, mode in enumerate(modes):
        case_root = control_root / ('case%02d' % index)
        case_root.mkdir(mode=0o700)
        case = {'name': mode, 'passed': False, 'commands': [],
                'Android_executed': False, 'namespace_or_UID_changes': False,
                'pidfd_failure_seam': mode == 'pidfd-failure'}
        report['host_child_lifecycle_controls'].append(case)
        first = None

        def denied_pidfd(pid, flags):
            raise OSError(errno.EMFILE, 'explicit owned-child pidfd-open control seam')

        try:
            owned_command(case, case_root,
                    [sys.executable, '-I', '-B', '-c', HOST_LIFECYCLE_FIXTURE, mode],
                    timeout=1 if mode == 'timeout-descendant' else 5,
                    pidfd_factory=denied_pidfd if mode == 'pidfd-failure' else None, environment=environment)
        except Exception as error:
            first = error
        require(first is not None and len(case['commands']) == 1,
                'lifecycle negative control unexpectedly succeeded')
        row = case['commands'][0]
        require(row['child_started'] and row['child_reaped'] and
                row['owned_tree_cleanup_complete'] and row['pidfd_closed'] and
                row['output_fds_closed'] and row.get('stdout_complete') and row.get('stderr_complete'),
                'lifecycle negative control did not completely retire its owned tree')
        require(row['stderr'] == '' and row['first_error'] is not None,
                'lifecycle negative control lost its first error or had unexpected stderr')
        if mode == 'pidfd-failure':
            require(isinstance(first, OSError) and first.errno == errno.EMFILE and
                    row['first_error']['stage'] == 'start_or_wait' and
                    row['returncode'] == -signal.SIGKILL and not row['descendants'],
                    'post-Popen pidfd failure did not preserve errno and reap the child')
        else:
            fields = row['stdout'].strip().split()
            require(len(fields) == 3 and fields[0] == 'READY' and
                    int(fields[1]) == row['pid'] and len(row['descendants']) == 1 and
                    row['descendants'][0]['pid'] == int(fields[2]) and
                    row['descendants'][0]['reaped'] and row['descendants'][0]['pidfd_closed'] and
                    os.WIFSIGNALED(row['descendants'][0]['wait_status']) and
                    os.WTERMSIG(row['descendants'][0]['wait_status']) == signal.SIGKILL,
                    'real descendant readiness/reaping proof differs')
            if mode == 'timeout-descendant':
                require(isinstance(first, subprocess.TimeoutExpired) and row['timed_out'] and
                        row['returncode'] == -signal.SIGKILL and
                        row['first_error']['stage'] == 'start_or_wait',
                        'timeout control did not retain the original failure')
            else:
                require(row['returncode'] == 0 and not row['timed_out'] and
                        row['descendants'][0]['kill_attempted'] and
                        row['first_error']['stage'] == 'driver_left_descendants',
                        'escaped descendant was not rejected and independently retired')
        CHILD_REAPER.empty()
        case['expected_failure'] = repr(first)
        case['passed'] = True
    require(len(report['host_child_lifecycle_controls']) == 3 and
            all(item['passed'] for item in report['host_child_lifecycle_controls']),
            'owned tree cleanup controls incomplete')





def apply_candidate_sources(expected, candidate_expected, copied_before):
    require(len(expected) == 499 and len(candidate_expected) == 500,
            'original/candidate file counts differ')
    additions = set(candidate_expected)-set(expected)
    differences = {path for path in expected if expected[path] != candidate_expected.get(path)}
    require(additions == {ENGINE_PATH} and len(differences) == 8 and
            differences | additions == {row['path'] for row in SOURCE_PINS.values()} and
            set(expected) <= set(candidate_expected),
            'candidate differs outside eight replacements and one engine ledger')
    for name, wanted in SOURCE_PINS.items():
        path = wanted['path']
        row = candidate_expected[path]
        require(row['kind'] == 'file' and row['mode'] == 0o664 and
                row['bytes'] == wanted['bytes'] and row['sha256'] == wanted['sha256'],
                'candidate map pin differs: '+path)
        data, actual = held(HERE/name, 131072)
        require(actual['bytes'] == wanted['bytes'] and actual['sha256'] == wanted['sha256'],
                'candidate payload changed: '+name)
        target = COPIED/path
        real_directory(target.parent)
        if path in expected:
            require(hash_held(target) == copied_before[path], 'copied baseline changed: '+path)
            flags = os.O_WRONLY|os.O_TRUNC|os.O_CLOEXEC|os.O_NOFOLLOW
        else:
            flags = os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW
        fd = os.open(target,flags,0o600)
        with os.fdopen(fd,'wb') as stream:
            require(stream.write(data) == len(data), 'short owned source write')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(target,0o664,follow_symlinks=False)
    observed = regular_tree(COPIED)
    portable(observed,candidate_expected)
    return observed

def fixture_inputs():
    inputs = {}
    for name, expected in FIXTURE_PINS.items():
        raw, row = held(HERE/name,131072)
        require(row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256'],
                'fixed fixture source changed: '+name)
        inputs[name] = raw
    require(not FIXTURE.exists() and not FIXTURE.is_symlink(), 'fixture root already exists')
    FIXTURE.mkdir(mode=0o700)
    (FIXTURE/'src').mkdir(mode=0o700)
    write_new(FIXTURE/'Cargo.toml',inputs['fixture-Cargo.toml'])
    write_new(FIXTURE/'src/lib.rs',inputs['fixture-lib.rs'])
    compositions = []
    for name, source, tests, target in [
        ('coordinator',CONTROL_PATH,'transaction_tests.rs','src/control_under_test.rs'),
        ('provider',PROVIDER_PATH,'provider_tests.rs','src/provider_under_test.rs'),
    ]:
        wanted = next(row for row in SOURCE_PINS.values() if row['path'] == source)
        production, actual = held(COPIED/source,131072)
        require(actual['bytes'] == wanted['bytes'] and actual['sha256'] == wanted['sha256'],
                'full production fixture prefix changed')
        combined = production+inputs[tests]
        write_new(FIXTURE/target,combined)
        require(combined[:len(production)] == production and combined[len(production):] == inputs[tests],
                'full production source prefix was substituted')
        compositions.append({'name':name,'source':source,'production_bytes':len(production),
            'production_sha256':sha(production),'tests_bytes':len(inputs[tests]),
            'tests_sha256':sha(inputs[tests]),'combined_bytes':len(combined),
            'combined_sha256':sha(combined),'method_body_substitution':False})
    ledger, _ = held(COPIED/ENGINE_PATH,131072)
    require(sha(ledger) == SOURCE_PINS['candidate-engine-retirement.rs']['sha256'],
            'production engine ledger changed')
    write_new(FIXTURE/'src/engine_retirement.rs',ledger)
    main, _ = held(COPIED/'graphics/droidloom-composer-service/src/main.rs',131072)
    begin = b'fn qualified_capabilities('
    end = b'\nfn event_loop('
    require(main.count(begin) == main.count(end) == 1, 'handshake predicate boundaries changed')
    predicate = main.split(begin,1)[1].split(end,1)[0]
    predicate = begin+predicate.rstrip()+b'\n'
    require(inputs['handshake_under_test.rs'].count(predicate) == 1,
            'handshake fixture is not exact production predicate bytes')
    write_new(FIXTURE/'src/handshake_under_test.rs',inputs['handshake_under_test.rs'])
    protocol_copies = []
    for source,target in [
        ('graphics/droidloom-denial-protocol/src/lib.rs','src/denial_protocol_contract.rs'),
        ('graphics/droidloom-denial-endpoint/src/lib.rs','src/denial_endpoint_contract.rs'),
    ]:
        raw, actual = held(COPIED/source,131072)
        wanted = next(row for row in SOURCE_PINS.values() if row['path'] == source)
        require(actual['bytes'] == wanted['bytes'] and actual['sha256'] == wanted['sha256'],
                'complete protocol/endpoint source changed before test composition')
        write_new(FIXTURE/target,raw)
        protocol_copies.append({'source':source,'test_source':target,'bytes':len(raw),'sha256':sha(raw),
                                'body_substitution':False})
    return {'full_production_compositions':compositions,'complete_protocol_endpoint_copies':protocol_copies,
            'engine_ledger':{'bytes':len(ledger),'sha256':sha(ledger)},
            'handshake_predicate':{'bytes':len(predicate),'sha256':sha(predicate)},
            'coordinator_I_O_seams':['DenialPresentationSink','ComposerLifecycle'],
            'provider_host_seams':['Binder descriptor wrapper','DRM timeline/descriptor API','GLES rejects','frame tracing disabled'],
            'real_provider_methods':True,'real_Core_binding':True,'real_ProtocolSocket_socketpair':True,
            'DRM_GPU_Binder_ABI_qualified':False}

def selected_dependencies(metadata, registry, original_lock, selected_lock, phase, cache):
    require(phase == 'fixture' and
            metadata.get('target_directory') == str(OUT/'cargo-target') and
            type(metadata.get('packages')) is list and 0 < len(metadata['packages']) <= 64,
            'metadata target/package bound differs')
    entries = metadata['packages']
    by_id = {p['id']:p for p in entries}
    require(len(by_id) == len(entries), 'duplicate metadata package identity')
    nodes = {node['id']:node for node in metadata.get('resolve',{}).get('nodes',[])}
    require(len(nodes) == len(metadata.get('resolve',{}).get('nodes',[])) and set(nodes) == set(by_id),
            'resolver package membership differs')
    require(metadata.get('workspace_root') == str(FIXTURE), 'fixture workspace root differs')
    expected_paths = {name:str(COPIED/relative/'Cargo.toml') for name,relative in PATH_PACKAGES.items()}
    expected_paths[FIXTURE_NAME] = str(FIXTURE/'Cargo.toml')
    paths = [p for p in entries if p['source'] is None]
    require(len(paths) == len(expected_paths) and
            {p['name']:p['manifest_path'] for p in paths} == expected_paths,
            'fixture path package closure differs')
    roots = [p for p in paths if p['name'] == FIXTURE_NAME and p['version'] == '0.0.0']
    require(len(roots) == 1 and metadata.get('workspace_members') == [roots[0]['id']] and
            metadata['resolve'].get('root') == roots[0]['id'], 'fixture resolver root differs')
    selected_ids = set(by_id)
    def lock_rows(value):
        result = {}
        for row in value['package']:
            key = (row['name'],row['version'])
            require(key not in result, 'ambiguous package version in immutable lock')
            result[key] = row
        return result
    old, new = lock_rows(original_lock), lock_rows(selected_lock)
    require(set(new) == {(p['name'],p['version']) for p in entries},
            'fixture lock and full metadata packages differ')
    authority = {(r['name'],r['version']):r for r in registry['packages']}
    require(len(authority) == len(registry['packages']) == 45,
            'original actual registry authority is incomplete')
    source_roots = {str(Path(r['source_directory']).parent) for r in registry['packages']}
    archive_roots = {str(Path(r['expected_archive_path']).parent) for r in registry['packages']}
    require(len(source_roots) == len(archive_roots) == 1, 'multiple registry namespaces rejected')
    source_root, archive_root = Path(next(iter(source_roots))), Path(next(iter(archive_roots)))
    require(source_root.parent == CARGO_HOME/'registry/src' and
            archive_root.parent == CARGO_HOME/'registry/cache' and
            source_root.name == archive_root.name and '..' not in source_root.parts,
            'actual registry roots are not paired fixed Cargo cache namespaces')
    descriptions, collected = [], {}
    for package_id in sorted(selected_ids):
        p = by_id[package_id]
        key = (p['name'],p['version'])
        require(re.fullmatch(r'[A-Za-z0-9_-]+',key[0]) is not None and
                re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9_.+-]+)?',key[1]) is not None,
                'noncanonical locked package component')
        require(key in new, 'selected package missing from held lock')
        locked = new[key]
        if p['source'] is None:
            require(locked.get('source') is None, 'path package acquired a registry source')
            if p['name'] == FIXTURE_NAME:
                require(phase == 'fixture' and p['manifest_path'] == str(FIXTURE/'Cargo.toml'),
                        'fixture identity escaped its package')
                kind = 'pinned-fixture'
            else:
                require(key in old and old[key].get('source') is None, 'path package is not in original lock')
                manifest = Path(p['manifest_path'])
                require(manifest.is_relative_to(COPIED) and '..' not in manifest.parts and
                        str(manifest.relative_to(COPIED)) in SOURCE_MAP and
                        SOURCE_MAP[str(manifest.relative_to(COPIED))]['kind'] == 'file',
                        'path package manifest escaped exact copied source')
                require(hash_held(manifest)['sha256'] == SOURCE_MAP[str(manifest.relative_to(COPIED))]['sha256'],
                        'path package manifest changed before compilation')
                kind = 'pinned-source'
            descriptions.append({'id':p['id'],'name':p['name'],'version':p['version'],
                                 'kind':kind,'manifest':p['manifest_path']})
            continue
        require(key in old and p['source'] == locked.get('source') ==
                old[key].get('source') == 'registry+https://github.com/rust-lang/crates.io-index' and
                locked.get('checksum') == old[key].get('checksum') and
                re.fullmatch(r'[0-9a-f]{64}',locked.get('checksum','')) is not None,
                'resolver selected a registry package outside immutable original lock')
        observed = authority.get(key)
        directory = source_root/(key[0]+'-'+key[1])
        archive = archive_root/(key[0]+'-'+key[1]+'.crate')
        require(p['manifest_path'] == str(directory/'Cargo.toml'), 'registry manifest escaped exact locked path')
        if observed is not None:
            require(observed['source_directory'] == str(directory) and
                    observed['expected_archive_path'] == str(archive) and
                    observed['expected_lock_checksum'] == locked['checksum'] and
                    observed['comparison']['archive_matches_lock'] is True and
                    observed['comparison']['every_archive_file_matches_held_extracted_source'] is True,
                    'selected original-45 package lost its prior actual archive/source authority')
        real_directory(directory)
        real_directory(archive.parent)
        if key in cache:
            saved = cache[key]
            require(saved['checksum'] == locked['checksum'] and hash_held(archive) == saved['archive'],
                    'shared dependency archive changed between phases')
            require(all(hash_held(Path(path)) == row for path,row in saved['files'].items()),
                    'shared dependency sources changed between phases')
            comparison, rows, archive_pin = saved['comparison'], saved['rows'], saved['archive']
        else:
            comparison, rows, archive_pin = qualify_cached_archive(
                archive,directory,key[0],key[1],locked['checksum'])
            files = {str(archive):archive_pin,**{row['path']:row for row in rows.values()}}
            cache[key] = {'checksum':locked['checksum'],'comparison':comparison,'rows':rows,
                          'archive':archive_pin,'files':files}
        if observed is not None:
            require(archive_pin['sha256'] == observed['comparison']['archive']['sha256'],
                    'existing actual archive bytes changed')
        collected[str(archive)] = archive_pin
        for row in rows.values():
            require(len(collected) < 16384, 'selected source closure exceeds explicit file bound')
            collected[row['path']] = row
        manifest_raw, manifest_pin = held(directory/'Cargo.toml',1024*1024)
        package = tomllib.loads(manifest_raw.decode())['package']
        require(package['name'] == key[0] and package['version'] == key[1] and
                manifest_pin == rows['Cargo.toml'], 'cached package manifest differs')
        descriptions.append({'id':p['id'],'name':p['name'],'version':p['version'],
            'kind':'offline-registry','manifest':p['manifest_path'],'archive':archive_pin,
            'package_checksum':locked['checksum'],'archive_to_source':comparison['source_inventory'],
            'authority_kind':'prior-45-actual-rechecked' if observed is not None else 'additional-original-lock-archive-first-observed',
            'prior_actual_archive_authority_present':observed is not None})
    return roots[0]['id'],descriptions,collected

def qualify_compile_records(raw, packages, dependency_rows, source_rows, fixture_rows, phase, root_id):
    qualified = {p['manifest']:p for p in packages}
    ids = {p['id'] for p in packages}
    observed, executables, completions = set(), {}, []
    require(phase == 'fixture', 'only the explicit host fixture may be compiled by this request')
    expected_tests = {
        FIXTURE_NAME.replace('-','_'):('lib',FIXTURE/'src/lib.rs'),
        'denial_protocol_contract':('test',FIXTURE/'src/denial_protocol_contract.rs'),
        'denial_endpoint_contract':('test',FIXTURE/'src/denial_endpoint_contract.rs'),
    }
    for line in raw.decode().splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        reason = item.get('reason')
        if reason == 'compiler-artifact':
            manifest = item.get('manifest_path')
            require(manifest in qualified and item['package_id'] == qualified[manifest]['id'],
                    'Cargo compiled an unqualified package')
            source = Path(item['target']['src_path'])
            row = dependency_rows.get(str(source))
            if row is None and source.is_relative_to(COPIED):
                row = source_rows.get(str(source.relative_to(COPIED)))
            if row is None and source.is_relative_to(FIXTURE):
                row = fixture_rows.get(str(source.relative_to(FIXTURE)))
            require(row is not None and hash_held(source) == row, 'compiled target source was not prequalified')
            require(all(Path(name).is_relative_to(OUT/'cargo-target') and '..' not in Path(name).parts
                        for name in item['filenames']), 'compiled output escaped owned target')
            observed.add(item['package_id'])
            if item['package_id'] == root_id and item.get('executable'):
                name = item['target']['name']
                require(name in expected_tests and name not in executables, 'extra/duplicate fixture test executable')
                kind, path = expected_tests[name]
                require(item['profile']['test'] is True and item['target']['kind'] == [kind] and
                        item['target']['src_path'] == str(path) and
                        Path(item['executable']).is_relative_to(OUT/'cargo-target'),
                        'test executable target does not match its exact production/source composition')
                executables[name] = Path(item['executable'])
        elif reason == 'build-script-executed':
            require(item['package_id'] in ids and Path(item['out_dir']).is_relative_to(OUT/'cargo-target'),
                    'unqualified build script or output directory')
        elif reason == 'build-finished':
            completions.append(item.get('success'))
        elif reason != 'compiler-message':
            raise RuntimeError('unexpected Cargo JSON record: '+str(reason))
    require(completions == [True] and observed, 'Cargo compilation did not finish successfully')
    require(set(executables) == set(expected_tests), 'three exact real-source test executables were not produced')
    return executables,sorted(observed)

def retirement_focused_test(binary, target, name, index, registered, environment, records):
    tag = target+'-%03d' % index
    path = OUT/(tag+'.libtest')
    fd = os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                before.st_uid == os.geteuid() and stat.S_IMODE(before.st_mode) == 0o600 and before.st_size == 0,
                'fresh held libtest receipt claim differs')
        output = command([str(binary),'--exact',name,'--test-threads=1','--nocapture','--logfile',str(path)],
                         FIXTURE,environment,tag,records,30).decode()
        after = os.fstat(fd)
        require((before.st_dev,before.st_ino,before.st_mode,before.st_uid,before.st_gid,before.st_nlink) ==
                (after.st_dev,after.st_ino,after.st_mode,after.st_uid,after.st_gid,after.st_nlink) and
                after.st_size <= 4096, 'independent libtest receipt identity differs')
        raw = os.pread(fd,4097,0)
        require(len(raw) == after.st_size and identity(after) == identity(os.fstat(fd)) == identity(path.lstat()),
                'held libtest receipt changed during complete read')
        require(raw == ('ok '+name+'\n').encode(), 'independent libtest receipt is not one exact success')
        summaries = [line for line in output.splitlines() if line.startswith('test result:')]
        pattern = r'test result: ok\. 1 passed; 0 failed; 0 ignored; 0 measured; '+str(registered-1)+r' filtered out; finished in \d+(?:\.\d+)?s'
        require(len(summaries) == 1 and re.fullmatch(pattern,summaries[0]) is not None and
                output.splitlines().count('running 1 test') == 1 and output.count('test '+name+' ... ') == 1,
                'stdout and independent libtest success disagree')
        gate = {'target':target,'exact_name':name,'registered_tests':registered,'filtered_out':registered-1,
                'one_passed':True,'independent_logfile':{'path':str(path),'bytes':len(raw),
                    'sha256':sha(raw),'identity':identity(after)}}
        records[-1]['focused_result_gate'] = gate
        return gate
    finally:
        os.close(fd)

def execute():
    global DEADLINE, CHILD_REAPER, SOURCE_MAP
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'ordinary operator UID1000 required')
    require(Path(__file__).absolute() == HERE/'compile_fixture.py', 'exact staged controller required')
    real_directory(HERE)
    require(not OUT.exists() and not OUT.is_symlink(), 'create-only attempt already exists')
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    (OUT/'tmp').mkdir(mode=0o700)
    DEADLINE = time.monotonic()+450
    report = {'schema':1,'state':'RUNNING','started_utc':utc(),
              'scope':'nine exact retirement source changes; complete provider methods with explicit host API seams; real protocol/endpoint tests; Wayland full crate gate remains separate and unrun',
              'Main_actions':0,'Main_identity_observed':False,'install_actions':0,
              'Android_Binder_provider_compile':False,'Android_or_Soong_executed':False,
              'installed_Main_source_provenance_qualified':False,'actual_Bili_failure_cause_proven':False,
              'production_ready':False,'commands':[],'expected_test_names':TESTS,
              'real_provider_methods_host_qualified':False,'fixture_phase_complete':False,
              'Wayland_complete_crate_typecheck_qualified':False,'Wayland_runtime_GPU_qualified':False,
              'network_downloads_permitted':False,'secondary_errors':[]}
    def interrupted(number, frame):
        OBSERVED_SIGNALS.append(number)
        raise RuntimeError('owned controller interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    resource_fd = -1
    resource_before = None
    original_rows = {}
    candidate_rows = {}
    fixture_rows = {}
    fixture_static_rows = {}
    dependency_rows = {}
    dependency_cache = {}
    test_pins = {}
    tool_rows = []
    config_rows = []
    config_paths = []
    test_pin = None
    test_binary = None
    def secondary(stage, error):
        report['state'] = 'FAIL'
        report['secondary_errors'].append({'stage':stage,'error':repr(error)})
    try:
        resource_fd, resource_before = begin_resources()
        report['owned_resources_before'] = resource_before
        allowed = sorted(os.sched_getaffinity(0))
        require(len(allowed) >= 3, 'cannot leave two logical CPUs free')
        os.sched_setaffinity(0, [allowed[-1]])
        report['allowed_cpus_before'] = allowed
        report['selected_cpus'] = [allowed[-1]]
        CHILD_REAPER = OwnChildReaper()
        CHILD_REAPER.begin()
        env = {'PATH':'/usr/bin:/bin','CARGO_HOME':str(CARGO_HOME),
               'RUSTC':str(RUST_SYSROOT/'bin/rustc'),'RUSTDOC':str(RUST_SYSROOT/'bin/rustdoc'),
               'CARGO_NET_OFFLINE':'true','LC_ALL':'C','LANG':'C',
               'TMPDIR':str(OUT/'tmp'),'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null',
               'PYTHONDONTWRITEBYTECODE':'1'}
        python = pin_resolved(Path(sys.executable),[Path('/usr/bin')])
        require(Path(sys.executable) == Path('/usr/bin/python3'), 'admitted Python interpreter path differs')
        tool_rows.append(python)
        report['admitted_python_runtime_observation'] = python
        run_child_lifecycle_controls(report, OUT, env)
        parent_raw, parent_pin = pinned_packet('parent469-result.json',
            '3636057b9a20fc895657064da3fb66d8ded7e69ebfa5a5b92072a51b33f29fd5')
        parent = json.loads(parent_raw)
        require(parent_pin['bytes'] == 170316 and parent['state'] == 'PASS' and
                len(parent['commands']) == 65 and
                all(row['returncode'] == 0 and not row['timed_out'] for row in parent['commands']) and
                parent['focused_tests_passed'] == 27 and parent['updater_focused_tests_passed'] == 18 and
                parent['source_resume_tests_passed'] == 9 and
                parent['source_delta']['actual_source_file_count'] == 499 and
                parent['copied_manifest']['bytes'] == 99327 and
                parent['copied_manifest']['sha256'] == PARENT_MANIFEST_SHA and
                parent['builder_elf']['bytes'] == 34767856 and
                parent['builder_elf']['sha256'] == 'c758a1e12bbc1925cc36f8cde3b369ab8449ad1cf460a9854b42d627575627d8' and
                parent['owned_resource_gate']['pass'] is True and
                parent['copied_source_unchanged_after'] is True and
                parent['original_source_unchanged_after'] is True and
                parent['cargo_configs_unchanged_after'] is True and
                not parent['tool_changes'] and not parent['dependency_changes'] and
                not parent['cleanup']['errors'] and not parent['cleanup']['remaining'] and
                parent['cleanup']['forced_cleanup'] is False and
                parent['runtime_authorization_enabled'] is False,
                'actual builder469 source/tool qualification differs')
        report['actual_parent469_source_authority'] = parent_pin
        old_raw, _ = pinned_packet('parent469-manifest.json', PARENT_MANIFEST_SHA)
        candidate_raw, _ = pinned_packet('candidate-source-manifest.json', CANDIDATE_MANIFEST_SHA)
        expected = json.loads(old_raw)
        candidate_expected = json.loads(candidate_raw)
        SOURCE_MAP = candidate_expected
        original_rows, copied_before = exact_source_copy(expected)
        report['original_manifest'] = write_new(OUT/'original-source-manifest.json',old_raw)
        candidate_rows = apply_candidate_sources(expected,candidate_expected,copied_before)
        report['copied_manifest'] = write_new(OUT/'copied-source-manifest.json',candidate_raw)
        report['source_delta'] = {'changed_files':8,'new_files':1,'unchanged_files':491,
                                  'source_files':500,'Android_AIDL_adapter_source_changed':True,
                                  'Android_AIDL_adapter_engineering_ABI_compiled':False,
                                  'candidate_files':SOURCE_PINS}
        report['fixture_composition'] = fixture_inputs()
        fixture_observed = regular_tree(FIXTURE,16,1024*1024)
        require(set(fixture_observed) == FIXTURE_STATIC_PATHS,
                'fresh eight-leaf fixture source inventory differs')
        fixture_static_rows = fixture_observed
        report['fixture_static_inputs'] = write_new(OUT/'fixture-static-inputs-before.json',fixture_static_rows)
        selected_tools, compiler_rows = toolchain(report, env)
        tool_rows.extend(compiler_rows)
        report['tool_inputs'] = write_new(OUT/'tool-inputs-before.json', tool_rows)
        env.update({'PATH':str(selected_tools['cargo'].parent)+':/usr/bin:/bin',
                    'RUSTC':str(selected_tools['rustc']),'RUSTDOC':str(selected_tools['rustdoc']),
                    'RUSTDOCFLAGS':'','CARGO_ENCODED_RUSTDOCFLAGS':'',
                    'RUSTC_WRAPPER':'','RUSTC_WORKSPACE_WRAPPER':'','RUSTFLAGS':'','CARGO_ENCODED_RUSTFLAGS':'',
                    'CARGO_TARGET_DIR':str(OUT/'cargo-target'),'CARGO_BUILD_JOBS':'1',
                    'CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER':'/usr/bin/cc'})
        require('/home/alex/.cargo/bin' not in env['PATH'].split(':') and
                all(shutil.which(name,path=env['PATH']) == str(selected_tools[name])
                    for name in ['cargo','rustc','rustdoc']) and
                not any(name.startswith('RUSTUP') for name in env) and
                all(name not in env for name in ('LD_PRELOAD','LD_LIBRARY_PATH','RUSTC_BOOTSTRAP')),
                'fixed direct compiler tools were shadowed')
        config_paths = [CARGO_HOME/'config',CARGO_HOME/'config.toml']
        for directory in [COPIED,FIXTURE]:
            for parent_directory in [directory,*directory.parents]:
                config_paths += [parent_directory/'.cargo/config',parent_directory/'.cargo/config.toml']
        config_rows = read_existing_config(config_paths)
        require(config_rows and all(row.get('absent') is True for row in config_rows),
                'unqualified Cargo configuration is present')
        report['cargo_config_inputs_before'] = config_rows
        report['build_environment'] = env
        original_lock_raw, original_lock_pin = held(COPIED/'Cargo.lock',1024*1024)
        require(original_lock_pin == candidate_rows['Cargo.lock'], 'immutable original Cargo.lock changed')
        report['original_lock'] = original_lock_pin
        # Seed only the new owned fixture. generate-lockfile would discard
        # existing choices and select newer cached versions, as host01 did.
        report['fixture_lock_seed'] = write_new(FIXTURE/'Cargo.lock',original_lock_raw)
        seed_raw, seed_pin = held(FIXTURE/'Cargo.lock',1024*1024)
        require(seed_raw == original_lock_raw and
                seed_pin['bytes'] == original_lock_pin['bytes'] and
                seed_pin['sha256'] == original_lock_pin['sha256'],
                'new fixture lock seed is not the exact immutable original')
        report['fixture_lock_seed_held'] = seed_pin
        # Metadata may reconcile this new fixture's package graph once.
        # No Rust is compiled here. Every selected old-45 package retains its
        # prior actual gate; additional packages require exact original-lock
        # archive/source qualification before this host compilation.
        command([str(selected_tools['cargo']),'metadata','--offline','--format-version','1'],
                FIXTURE,env,'fixture-lock-reconciliation',report['commands'],60)
        generated_lock_raw, generated_lock_pin = held(FIXTURE/'Cargo.lock',1024*1024)
        report['generated_fixture_lock'] = generated_lock_pin
        fixture_observed = regular_tree(FIXTURE,16,1024*1024)
        require(set(fixture_observed) == FIXTURE_STATIC_PATHS | {'Cargo.lock'} and
                fixture_observed['Cargo.lock'] == generated_lock_pin and
                {path:row for path,row in fixture_observed.items() if path != 'Cargo.lock'} == fixture_static_rows,
                'fixture resolver changed static source or its held lock inventory')
        fixture_rows = fixture_observed
        report['fixture_inputs'] = write_new(OUT/'fixture-inputs-before.json',fixture_rows)
        metadata_raw = command([str(selected_tools['cargo']),'metadata','--offline','--locked',
                                '--format-version','1'],FIXTURE,env,'fixture-metadata',report['commands'],60)
        registry_raw, registry_pin = pinned_packet('registry-result.json',
            'b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993')
        registry = json.loads(registry_raw)
        require(registry['state'] == 'PASS' and registry['collection_complete'] is True and
                registry['all_45_archive_and_source_matches'] is True and
                registry['authorities_unchanged_after'] is True and registry['owned_resource_gate']['pass'] is True,
                'actual existing registry qualification is incomplete')
        report['actual_registry_archive_authority'] = registry_pin
        fixture_id, packages, current_dependencies = selected_dependencies(
            json.loads(metadata_raw),registry,tomllib.loads(original_lock_raw.decode()),
            tomllib.loads(generated_lock_raw.decode()),'fixture',dependency_cache)
        dependency_rows.update(current_dependencies)
        report['dependency_inputs'] = write_new(OUT/'fixture-dependency-inputs-before.json',
                                                {'packages':packages,'files':dependency_rows})
        built = command([str(selected_tools['cargo']),'test','--offline','--locked','-j','1',
                         '--no-run','--message-format=json-render-diagnostics'],
                         FIXTURE,env,'retirement-fixture-compile',report['commands'],240)
        binaries, compiled_ids = qualify_compile_records(
            built,packages,dependency_rows,candidate_rows,fixture_rows,'fixture',fixture_id)
        report['actual_compiled_fixture_package_ids'] = compiled_ids
        report['focused_result_gates'] = []
        report['actual_registered_test_counts'] = {}
        report['focused_tests_passed'] = 0
        for target,names in TARGET_TESTS.items():
            binary = binaries[target]
            test_pin = hash_held(binary)
            require(stat.S_IMODE(test_pin['identity'][2]) & 0o111,
                    'actual test artifact is not executable')
            fd = os.open(binary,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
            try:
                require(os.read(fd,4) == b'\x7fELF','actual test artifact is not a host ELF')
            finally:
                os.close(fd)
            listing = command([str(binary),'--list'],FIXTURE,env,target+'-list',report['commands'],10).decode()
            listed = [line[:-6] for line in listing.splitlines() if line.endswith(': test')]
            require(len(listed) == len(set(listed)) == len(names) and set(listed) == set(names) and
                    not any(line.endswith(': benchmark') for line in listing.splitlines()),
                    'actual libtest registrations differ for '+target)
            help_text = command([str(binary),'--help'],FIXTURE,env,target+'-help',report['commands'],10).decode()
            require(re.search(r'^\s*--logfile\s',help_text,re.MULTILINE) is not None and
                    'Write logs to the specified file' in help_text,
                    'independent libtest record option missing')
            report['actual_registered_test_counts'][target] = len(listed)
            for index,name in enumerate(names):
                report['focused_result_gates'].append(retirement_focused_test(
                    binary,target,name,index,len(names),env,report['commands']))
                report['focused_tests_passed'] = len(report['focused_result_gates'])
            require(hash_held(binary) == test_pin,'test ELF changed during execution')
            test_pins[target] = test_pin
        report['test_elfs'] = test_pins
        require(len(report['focused_result_gates']) == 112 and len(test_pins) == 3,
                'complete fixed real-source test set did not pass')
        report['fixture_phase_complete'] = True
        report['provider_controls_observed_success_before_final_rechecks'] = True
        report['real_provider_scope'] = {
            'whole_production_denial_rs_compiled':True,
            'production_register_unregister_receipt_methods_executed':True,
            'new_real_provider_controls':24,'original_provider_unit_controls':2,
            'original_coordinator_controls':27,'engine_ledger_controls':12,'handshake_controls':4,
            'protocol_controls':23,'endpoint_controls':20,
            'Binder_DRM_GLES_are_explicit_host_seams':True,'GPU_or_Android_ABI_qualified':False,
            'legacy_endpoint_listener_test_can_skip_permission_denied':True}
        report['Wayland_full_crate_gate'] = 'NOT_RUN_IN_THIS_REQUEST_ROOT_OWNS_SEPARATE_CONTROLLER'
        require(len(report['commands']) == 131 and
                all(row.get('returncode') == 0 and row['child_reaped'] and
                    row['owned_tree_cleanup_complete'] and row['pidfd_closed'] and row['output_fds_closed'] and
                    not row['timed_out'] and not row['descendants'] and
                    row.get('leader_alive_before_group_cleanup') is False and
                    row['first_error'] is None and not row['secondary_errors'] for row in report['commands']),
                'fixed 131-command sequence or strict driver cleanup differs')
        require(time.monotonic() < DEADLINE, 'host fixture work qualification deadline exhausted')
        report['state'] = 'PASS'
    except Exception as error:
        report['state'] = 'FAIL'
        report['error'] = repr(error)
        report['error_detail'] = {'type':type(error).__name__,'message':str(error),
                                  'errno':getattr(error,'errno',None),'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['observed_signals'] = OBSERVED_SIGNALS
        try:
            require(CHILD_REAPER is not None and CHILD_REAPER.active, 'owned subreaper was not established')
            CHILD_REAPER.finish()
        except Exception as error:
            secondary('owned_reaper_final',error)
        report['owned_child_reaper'] = None if CHILD_REAPER is None else CHILD_REAPER.record
        for label, root, before in [
            ('original_source',BASE_SOURCE,original_rows),
            ('copied_source',COPIED,candidate_rows),
        ]:
            try:
                unchanged = bool(before) and regular_tree(root) == before
                report[label+'_unchanged_after'] = unchanged
                require(unchanged, label+' full source identity/content changed or never qualified')
            except Exception as error:
                secondary(label+'_after',error)
        # A missing full baseline is not evidence of a source mutation.
        # Still protect the eight immutable source leaves if they were created.
        report['fixture_source_unchanged_after'] = None
        report['fixture_static_source_unchanged_after'] = None
        report['fixture_baseline_state'] = 'NOT_ESTABLISHED'
        try:
            if fixture_rows:
                current = regular_tree(FIXTURE,16,1024*1024)
                unchanged = current == fixture_rows
                report['fixture_source_unchanged_after'] = unchanged
                report['fixture_static_source_unchanged_after'] = (
                    {path:row for path,row in current.items() if path != 'Cargo.lock'} == fixture_static_rows)
                report['fixture_baseline_state'] = 'FULL_NINE_LEAF_BASELINE'
                require(unchanged, 'qualified fixture source identity/content changed')
            elif fixture_static_rows:
                current = regular_tree(FIXTURE,16,1024*1024)
                unchanged = ({path:row for path,row in current.items() if path != 'Cargo.lock'} ==
                             fixture_static_rows and
                             set(current) <= set(fixture_static_rows) | {'Cargo.lock'})
                report['fixture_static_source_unchanged_after'] = unchanged
                report['fixture_baseline_state'] = 'STATIC_SOURCE_ONLY_LOCK_NOT_QUALIFIED'
                require(unchanged, 'qualified fixture static source identity/content changed')
            if report['state'] == 'PASS':
                require(report['fixture_source_unchanged_after'] is True,
                        'successful fixture run lacks its full immutable baseline')
        except Exception as error:
            secondary('fixture_source_after',error)
        changes = []
        for path,row in dependency_rows.items():
            try:
                if hash_held(Path(path)) != row:
                    changes.append(path)
            except Exception as error:
                changes.append({'path':path,'error':repr(error)})
        report['dependency_changes'] = changes
        if changes:
            secondary('dependency_after', RuntimeError('qualified dependency changed'))
        report['tool_changes'] = verify_resolved(tool_rows)
        if not tool_rows or report['tool_changes']:
            secondary('tool_after', RuntimeError('used tool closure missing or changed'))
        try:
            report['cargo_configs_unchanged_after'] = bool(config_rows) and read_existing_config(config_paths) == config_rows
            require(report['cargo_configs_unchanged_after'], 'Cargo config set changed or was never qualified')
        except Exception as error:
            secondary('cargo_configs_after',error)
        try:
            require(resource_fd >= 0 and resource_before is not None, 'owned resource admission not observed')
            report['owned_resource_gate'] = finish_resources(resource_fd,resource_before,report)
        except Exception as error:
            report['owned_resource_gate'] = {'pass':False,'error':repr(error)}
            secondary('owned_resources_after',error)
        finally:
            if resource_fd >= 0:
                value, resource_fd = resource_fd, -1
                try:
                    os.close(value)
                    report['owned_resource_fd_closed'] = True
                except Exception as error:
                    report['owned_resource_fd_closed'] = False
                    secondary('owned_resource_fd_close',error)
        report['real_provider_methods_host_qualified'] = (
            report['state'] == 'PASS' and report.get('fixture_phase_complete') is True)
        report['Wayland_complete_crate_typecheck_qualified'] = (
            report['state'] == 'PASS' and report.get('Wayland_complete_crate_typecheck_observed_success') is True)
        report['finished_utc'] = utc()
        result = write_new(OUT/'result.json',report)
        resource_gate = report.get('owned_resource_gate',{})
        print(json.dumps({'state':report['state'],'result':result,'test_elfs':report.get('test_elfs'),
                          'Main_actions':0,'Android_Binder_provider_compile':False,
                          'ordinary_commands':len(report['commands']),
                          'focused_tests_passed':report.get('focused_tests_passed',0),
                          'registered_test_counts':report.get('actual_registered_test_counts',{}),
                          'fixture_phase_complete':report.get('fixture_phase_complete',False),
                          'real_provider_methods_host_qualified':report.get('real_provider_methods_host_qualified',False),
                          'Wayland_complete_crate_typecheck_qualified':report.get('Wayland_complete_crate_typecheck_qualified',False),
                          'owned_child_reaper':report.get('owned_child_reaper'),
                          'owned_resource_fd_closed':report.get('owned_resource_fd_closed',False),
                          'owned_resources':{name:resource_gate.get(name) for name in
                              ['pass','memory_peak','memory_swap_peak','memory_events_delta','swap_max_observed_only']},
                          'source_unchanged':{name:report.get(name) for name in
                              ['original_source_unchanged_after','copied_source_unchanged_after',
                               'fixture_source_unchanged_after','cargo_configs_unchanged_after']},
                          'error':report.get('error'),'secondary_errors':report['secondary_errors']}),flush=True)
    return 0 if report['state'] == 'PASS' else 1


if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps({'mode':'PLAN','root':str(ROOT),'base_source':str(BASE_SOURCE),
            'requires_explicit_execute_once':True,'production_files_changed':8,'production_files_added':1,
            'source_files':500,'focused_test_names':TARGET_TESTS,'Main_actions':0,
            'Android_execution':False,'expected_focused_tests':112,'expected_ordinary_commands':131,
            'Wayland_full_binary_target_typecheck_required':True,'Wayland_check_in_this_request':False,
            'GPU_runtime_or_Android_Binder_ABI_qualification':False}))
    elif sys.argv[1:] == ['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: compile_fixture.py [--execute-once]')
