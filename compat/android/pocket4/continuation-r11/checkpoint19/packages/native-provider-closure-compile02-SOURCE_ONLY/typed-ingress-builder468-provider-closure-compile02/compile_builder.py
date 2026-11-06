#!/usr/bin/env python3
"""Compile builder468 real-provider closure with 15 updater and 9 source controls; no platform execution."""
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import stat
import subprocess
import sys
import time
import tomllib
import tarfile
from pathlib import PurePosixPath

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

def children():
    return [int(x) for x in Path('/proc/self/task/%d/children' % os.getpid()).read_text().split()]

def cleanup_children():
    initial = children()
    errors = []
    reaped = []
    deadline = time.monotonic()+8
    while children() and time.monotonic() < deadline:
        for pid in children():
            try:
                got, status = os.waitpid(pid, os.WNOHANG)
                if got:
                    reaped.append({'pid': got, 'status': status})
                    continue
                fd = os.pidfd_open(pid, 0)
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                finally:
                    os.close(fd)
            except ChildProcessError:
                continue
            except ProcessLookupError:
                continue
            except Exception as error:
                errors.append(repr(error))
        time.sleep(0.02)
    remaining = children()
    return {'initial_owned_children': initial, 'forced_cleanup': bool(initial), 'reaped': reaped, 'remaining': remaining, 'errors': errors}

def command(argv, cwd, env, label, records, maximum_seconds=180):
    require(not children(), 'unreaped child before command')
    maximum_seconds = min(maximum_seconds, DEADLINE-time.monotonic())
    require(maximum_seconds > 0, 'owned overall deadline exhausted')
    stdout = OUT/(label+'.stdout')
    stderr = OUT/(label+'.stderr')
    started = utc()
    with stdout.open('xb') as out, stderr.open('xb') as err:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=err, start_new_session=True)
        timeout = False
        try:
            code = proc.wait(timeout=maximum_seconds)
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                code = proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                code = proc.wait(timeout=3)
    output, outrow = held(stdout, 32*1024*1024)
    _, errrow = held(stderr, 4*1024*1024)
    row = {'argv': [str(x) for x in argv], 'cwd': str(cwd), 'label': label,
           'started_utc': started, 'finished_utc': utc(), 'returncode': code,
           'timed_out': timeout, 'stdout': outrow, 'stderr': errrow}
    records.append(row)
    require(code == 0 and not timeout, 'command failed: '+label)
    if label == 'projection-test-20':
        require(argv[1:] == ['--exact',FAKEROOT_TEST,'--test-threads=1','--nocapture',
                            '--logfile',str(OUT/'projection-test-20.libtest')],
                'normal daemon retirement is restricted to the exact fakeroot metadata test')
        row['normal_fakeroot_daemon_retirement'] = {}
        reap_normal_fakeroot_daemon(row['normal_fakeroot_daemon_retirement'])
    require(not children(), 'command left owned children: '+label)
    return output

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

BASE_SOURCE = Path('/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-03-20261106/builder-source')
ROOT = Path('/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-02-20261106')
HERE = ROOT/'control-source'
OUT = ROOT/'attempt01'
COPIED = ROOT/'builder-source'
RUST_SYSROOT = Path('/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu')
CARGO_HOME = Path('/home/alex/.cargo')
TOOLCHAIN = '1.93.0'
MANIFEST_PARENT = '71768da388021a870ef5f5516cc3efbfd956288a8fa74cb9b176b312f68d7605'
MANIFEST_468 = 'e06522400f746b62016f82dfd3ec913b39cd9a8f33f9bca4f61a19a2787684ee'
GO_PATCH = '9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307'
OBSERVATION = '60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb'
GO_CONTROL = '391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674'
TESTS = [
    'android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes',
    'android::tests::restoration_preserves_original_and_removes_created_file',
    'android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch',
    'android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout',
    'android::patch_tests::interrupted_projection_recovers_before_next_build',
    'tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets',
    'tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory',
]
ORIGINAL_TESTS = list(TESTS)
PAIR_TESTS = ['native_generation::tests::legacy_and_disabled_preserve_the_disabled_mode', 'native_generation::tests::rejects_every_mixed_old_new_combination', 'native_generation::tests::enabled_triplet_requires_exact_contract', 'native_generation::tests::rejects_malformed_foreign_or_ambiguous_marker', 'native_generation::tests::rejects_foreign_elf_and_unrecognized_contract', 'native_generation::tests::rejects_symlinked_components', 'native_generation::tests::rejects_previous_protocol_for_each_role_and_mode', 'native_generation::tests::rejects_previous_protocol_inside_self_consistent_enabled_contract', 'native_generation::tests::rejects_previous_protocol_contract', 'native_generation::tests::real_ext4_apex_extraction_rejects_changed_nested_component', 'native_generation::tests::product_contract_generation_requires_enabled_triplet', 'native_generation::tests::product_contract_generation_is_create_only_and_binds_components', 'native_generation::tests::real_erofs_bundle_verifies_its_embedded_pair', 'native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata', 'tests::native_generation_pair_cli_requires_one_explicit_product']
ART_PROJECTION_TESTS = ['native_generation_art::tests::output_rejects_source_overlap_alias_and_reuse', 'native_generation_art::tests::records_are_create_only_and_never_grant_runtime_readiness']
TYPED_INGRESS_TESTS = ['native_role_ingress::tests::observed_lock_passes_normal_schema_and_exact_extension_gate', 'native_role_ingress::tests::structurally_valid_unobserved_root_is_rejected_before_source_actions']
PARENT_TESTS = ORIGINAL_TESTS + PAIR_TESTS + ART_PROJECTION_TESTS + TYPED_INGRESS_TESTS
PROVIDER_CLOSURE_TESTS = ["android::tests::typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata","android::tests::typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas","android::tests::typed_shared_provider_projection_keeps_other_root_projection_unchanged","native_role_ingress::tests::provider_extension_rejects_unlisted_path_commit_metadata_or_project_change","native_role_ingress::tests::published_workspace_selects_only_exact_current_or_previous_typed_lock","native_role_ingress::tests::previous_typed_manifest_does_not_bypass_fresh_project_verification"]
TESTS = ORIGINAL_TESTS + TYPED_INGRESS_TESTS + PROVIDER_CLOSURE_TESTS
FIXED_PROVIDER_DELTA = ["android/manifest/m2-role-ingress-provider-source-lock.json","android/native-role-ingress/provider-fixtures/SystemUI.Android.bp","android/native-role-ingress/provider-fixtures/asuite-atest-metadata.Android.bp","android/native-role-ingress/provider-fixtures/asuite-proto.Android.bp","android/native-role-ingress/provider-fixtures/car-builtin.Android.bp","android/native-role-ingress/provider-fixtures/car-jni.Android.bp","android/native-role-ingress/provider-fixtures/car-lib.Android.bp","android/native-role-ingress/provider-fixtures/clearcut-junit-listener.Android.bp","android/native-role-ingress/provider-fixtures/icu4j.Android.bp","android/native-role-ingress/provider-fixtures/motion.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-aosp-plugins.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-pluginapi.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-processor.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-resources.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-robolectric.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-root.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-sandbox.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-shadowapi.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-shadows-httpclient.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-shadows-versioning.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-utils-reflector.Android.bp","android/native-role-ingress/provider-fixtures/robolectric-utils.Android.bp","android/native-role-ingress/provider-fixtures/runner.Android.bp","android/native-role-ingress/provider-fixtures/screenshot.Android.bp","android/native-role-ingress/provider-fixtures/test-parameter.Android.bp","tools/droidloom-update/src/android.rs","tools/droidloom-update/src/native_role_ingress.rs"]
CLOSURE_PROOF_SHA = '841de1878aecbf5235d4c8068b4ac5bbf7351131c17245c725782e4d66f01384'
SOURCE_RESUME_TESTS = ['resume::tests::completed_project_reuse_has_no_fetch_or_checkout_and_publishes_only_after_verify', 'resume::tests::initial_checkout_reuses_cached_commit_and_preserves_interrupted_index_lock', 'resume::tests::nonempty_interrupted_index_lock_is_preserved_in_place_and_rejected', 'resume::tests::dirty_completed_project_keeps_original_bytes_and_never_gets_manifest', 'resume::tests::conflicting_untracked_partial_file_is_not_forced_or_removed', 'resume::tests::wrong_origin_is_rejected_before_any_fetch_or_checkout', 'resume::tests::recovered_parent_symlink_cannot_create_a_project_outside_staging', 'resume::tests::mismatched_staging_manifest_is_preserved_and_not_published', 'resume::tests::sparse_parent_normalization_keeps_exact_locked_selection']
SOURCE_REGISTERED_TESTS = ['tests::project_bound_admits_superproject_gitlink_extensions_but_not_unbounded_sync', 'tests::source_lock_accepts_bounded_133_sparse_paths_but_rejects_257', 'tests::plan_uses_only_exact_official_projects', 'tests::platform_compat_uses_its_official_tools_namespace', 'tests::traversal_and_full_sync_policy_are_rejected_together', 'tests::duplicate_projects_and_moving_refs_are_rejected', 'tests::root_links_are_relative_to_their_parent', 'tests::exact_local_git_fetch_and_manifest_link_are_verified', 'tests::reconciliation_accepts_only_monotonic_plan_expansion', 'tests::reconciliation_accepts_bounded_sparse_path_expansion', 'tests::materialized_verification_rejects_dirty_projects', 'resume::tests::completed_project_reuse_has_no_fetch_or_checkout_and_publishes_only_after_verify', 'resume::tests::initial_checkout_reuses_cached_commit_and_preserves_interrupted_index_lock', 'resume::tests::nonempty_interrupted_index_lock_is_preserved_in_place_and_rejected', 'resume::tests::dirty_completed_project_keeps_original_bytes_and_never_gets_manifest', 'resume::tests::conflicting_untracked_partial_file_is_not_forced_or_removed', 'resume::tests::wrong_origin_is_rejected_before_any_fetch_or_checkout', 'resume::tests::recovered_parent_symlink_cannot_create_a_project_outside_staging', 'resume::tests::mismatched_staging_manifest_is_preserved_and_not_published', 'resume::tests::sparse_parent_normalization_keeps_exact_locked_selection']
DEADLINE = None
OBSERVED_SIGNALS = []

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

def parse_selected_tree(raw, copied):
    require(0 < len(raw) <= 131072, 'selected tree output outside bound')
    selected={}
    for line in raw.decode('utf-8').splitlines():
        match=re.fullmatch(r'([A-Za-z0-9_-]+) v([0-9][A-Za-z0-9.+-]*)(?: \(proc-macro\))?(?: \((/[^()\n]+)\))?(?: \(\*\))?',line)
        require(match is not None, 'unrecognized pinned Cargo tree line: '+line)
        name,version,directory=match.groups()
        if directory is not None:
            path=Path(directory)
            require(path.is_relative_to(copied) and '..' not in path.parts and str(path)==directory,
                    'selected path package escaped the exact copied source')
        key=(name,version)
        require(key not in selected or selected[key]==directory, 'ambiguous selected package source')
        selected[key]=directory
        require(len(selected)<=128, 'selected package bound exceeded')
    require(selected, 'empty selected dependency tree')
    return selected

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

def dependency_sources(metadata, build_tree, test_tree, observed_tree, registry_authority):
    require(metadata['resolve'] is None and metadata['workspace_root']==str(COPIED),
            'no-deps metadata must describe only the exact copied workspace')
    packages={p['id']:p for p in metadata['packages']}
    roots=[p['id'] for p in packages.values() if p['name']=='droidloom-update' and Path(p['manifest_path'])==COPIED/'tools/droidloom-update/Cargo.toml']
    require(len(roots)==1, 'selected package not the exact copied builder')
    previous=Path('/home/alex/work/pocket4-blueprint-streaming-builder-450-compile-01-20261105/builder-source')
    expected=observed_tree.decode().replace(str(previous),'<BUILDER_SOURCE>')
    for raw in [build_tree,test_tree]:
        require(raw.decode().replace(str(COPIED),'<BUILDER_SOURCE>')==expected,
                'selected tree differs from the actual offline package-selection authority')
    selected=parse_selected_tree(build_tree,COPIED)
    require(selected==parse_selected_tree(test_tree,COPIED) and len(selected)==49,
            'actual selected build/test package sets changed')
    lock=tomllib.loads((COPIED/'Cargo.lock').read_text())
    lock_by_key={}
    for package in lock['package']:
        lock_by_key.setdefault((package['name'],package['version']),[]).append(package)
    registry=CARGO_HOME/'registry/src';real_directory(registry)
    sources=sorted(registry.iterdir())
    require(0 < len(sources) <= 16 and all(stat.S_ISDIR(p.lstat().st_mode) for p in sources),
            'registry source roots are ambiguous aliases or exceed the bound')
    collected={};descriptions=[]
    for (name,version),selected_directory in sorted(selected.items()):
        locked=lock_by_key.get((name,version),[])
        require(len(locked)==1, 'selected package is ambiguous or absent in unchanged Cargo.lock')
        package=locked[0]
        if selected_directory is not None:
            matches=[p for p in packages.values() if p['name']==name and p['version']==version and
                     p['source'] is None and p['manifest_path']==str(Path(selected_directory)/'Cargo.toml')]
            require(package.get('source') is None and len(matches)==1,
                    'selected path package is not the exact no-deps workspace member')
            descriptions.append({'id':matches[0]['id'],'kind':'pinned-builder-source','manifest':matches[0]['manifest_path']})
            continue
        require(package.get('source')=='registry+https://github.com/rust-lang/crates.io-index' and
                re.fullmatch(r'[0-9a-f]{64}',package.get('checksum','')) is not None,
                'selected package is not the original locked crates.io source')
        candidates=[]
        for root in sources:
            candidate=root/(name+'-'+version)
            try:
                st=candidate.lstat()
            except FileNotFoundError:
                continue
            require(stat.S_ISDIR(st.st_mode), 'selected registry package is a directory alias')
            candidates.append(candidate)
        require(len(candidates)==1, 'selected package must have one existing local registry source: '+name+'@'+version)
        directory=candidates[0]
        observed=registry_authority.get((name,version))
        require(observed is not None and observed['source_directory']==str(directory) and
                observed['expected_lock_checksum']==package['checksum'] and
                observed['comparison']['archive_matches_lock'] is True and
                observed['comparison']['every_archive_file_matches_held_extracted_source'] is True,
                'selected source differs from actual locked-archive authority')
        archive=CARGO_HOME/'registry/cache'/directory.parent.name/(name+'-'+version+'.crate')
        require(str(archive)==observed['expected_archive_path'],'actual archive source location changed')
        real_directory(archive.parent)
        comparison,rows,archive_pin=qualify_cached_archive(archive,directory,name,version,package['checksum'])
        require(archive_pin['sha256']==observed['comparison']['archive']['sha256'],'actual archive digest changed')
        collected[str(archive)]=archive_pin
        manifest_raw,manifest_pin=held(directory/'Cargo.toml',1024*1024)
        manifest=tomllib.loads(manifest_raw.decode())
        require(manifest['package']['name']==name and manifest['package']['version']==version and
                rows['Cargo.toml']==manifest_pin,
                'cached package manifest/checksum changed or names a different package')
        for row in rows.values():
            require(len(collected)<16384, 'complete dependency inventory too large')
            collected[row['path']]=row
        package_id=package['source']+'#'+name+'@'+version
        descriptions.append({'id':package_id,'kind':'offline-registry','manifest':str(directory/'Cargo.toml'),
                             'recorded_files':len(rows),'package_checksum':package['checksum'],
                             'archive':archive_pin,'archive_to_source':comparison['source_inventory']})
    require(sum(p['kind']=='offline-registry' for p in descriptions)==45 and len(descriptions)==49,
            'selected existing dependency closure count changed')
    return roots[0],descriptions,collected

def qualify_compiler_inputs(raw,packages,dependency_rows,candidate_rows):
    qualified={p['manifest']:p for p in packages}
    qualified_ids={p['id'] for p in packages}
    observed=set()
    for line in raw.decode().splitlines():
        if not line.strip():continue
        item=json.loads(line)
        if item.get('reason')=='compiler-artifact':
            manifest=item.get('manifest_path')
            require(manifest in qualified and item['package_id']==qualified[manifest]['id'],
                    'Cargo compiled a package outside the pre-qualified source closure')
            path=Path(item['target']['src_path'])
            row=dependency_rows.get(str(path))
            if row is None and path.is_relative_to(COPIED):row=candidate_rows.get(str(path.relative_to(COPIED)))
            require(row is not None and hash_held(path)==row, 'actual compiled target source was not qualified or changed')
            observed.add(item['package_id'])
        elif item.get('reason')=='build-script-executed':
            require(item['package_id'] in qualified_ids, 'Cargo executed an unqualified build script')
    require(observed, 'no actual compiler-artifact inputs observed')
    return sorted(observed)

def build_artifact(raw, package_id, test):
    artifacts=[]
    for line in raw.decode().splitlines():
        if not line.strip():
            continue
        item=json.loads(line)
        if item.get('reason')=='compiler-artifact' and item.get('package_id')==package_id and item['target']['name']=='droidloom-update' and item.get('executable') and bool(item['profile']['test'])==test:
            artifacts.append(Path(item['executable']))
    require(len(artifacts)==1,'actual Cargo artifact set is not the one selected builder')
    artifact=artifacts[0]
    require(artifact.is_relative_to(OUT/'cargo-target'),'artifact escaped fresh owned target')
    return artifact

IMAGE_TOOL_OBSERVATION = 'b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292'
IMAGE_TEST_PATH = '/usr/bin:/usr/sbin:/bin:/sbin'
FAKEROOT_DAEMON = '/usr/bin/faked-sysv'
FAKEROOT_PRELOAD = '/usr/lib/x86_64-linux-gnu/libfakeroot/libfakeroot-sysv.so'
FAKEROOT_TEST = 'native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata'
IMAGE_TOOL_PATHS = {
    'zip':'/usr/bin/zip', 'unzip':'/usr/bin/unzip', 'debugfs':'/usr/sbin/debugfs',
    'mke2fs':'/usr/sbin/mke2fs', 'fsck.erofs':'/usr/bin/fsck.erofs',
    'mkfs.erofs':'/usr/bin/mkfs.erofs', 'fakeroot':'/usr/bin/fakeroot',
    'chown':'/usr/bin/chown', 'setfattr':'/usr/bin/setfattr',
}
IMAGE_TOOL_NAMES = tuple(IMAGE_TOOL_PATHS)
FAKEROOT_AUXILIARIES = ('/usr/bin/sed', '/usr/bin/cut', '/usr/bin/cat')


def image_pin(path, allowed, native_elf):
    row = pin_resolved(path, allowed)
    resolved = Path(row['resolved_path'])
    for parent in resolved.parents:
        value = parent.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and not value.st_mode & 0o022,
                'image tool ancestor is not immutable to this operator: '+str(parent))
    fd = os.open(resolved, os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(identity(before) == row['identity'] and before.st_uid == 0 and
                not before.st_mode & 0o022, 'image input owner/mode changed or is not root-owned')
        is_elf = os.read(fd,4) == b'\x7fELF'
        require(is_elf is native_elf, 'image input ELF/script kind differs')
        require(identity(before) == identity(os.fstat(fd)) == identity(resolved.lstat()),
                'image input changed during owner/type verification')
        require(path.resolve(strict=True) == resolved, 'image input resolution changed')
    finally:
        os.close(fd)
    row['root_owner_and_nonwritable_parents_verified'] = True
    row['is_ELF'] = is_elf
    return row


def image_toolchain(report, environment):
    raw, authority_pin = pinned_packet('image-tools-result.json', IMAGE_TOOL_OBSERVATION)
    authority = json.loads(raw)
    require(authority['state'] == 'PASS_FIXED_READ_ONLY_OBSERVATIONS' and
            authority['commands_executed'] == 0 and authority['image_or_mount_actions'] == 0 and
            authority['install_update_actions'] == 0 and authority['observations_unchanged_after'] is True and
            authority['owned_resource_gate']['pass'] is True and set(authority['tools']) == set(IMAGE_TOOL_NAMES) and
            authority['controlled_selection_PATH'] == IMAGE_TEST_PATH and not authority['missing_required_tools'] and
            sum(len(rows) for rows in authority['tool_candidate_observations'].values()) == 13 and
            len(authority['backend_observations']) == 10,
            'fixed image tool observation is not complete')
    require(all(name not in environment for name in ('FAKEROOTKEY','LD_PRELOAD','LD_LIBRARY_PATH')),
            'image tool environment contains inherited fakeroot or loader state')
    wrapper = authority['tools']['fakeroot']['complete_script_source']
    require(sha(wrapper.encode()) == authority['tools']['fakeroot']['sha256'] and
            wrapper.startswith('#!/bin/sh\n') and
            'FAKEROOT_PREFIX=/usr\nFAKEROOT_BINDIR=/usr/bin\n' in wrapper and
            'USEABSLIBPATH=0\nFAKEROOT_LIB=libfakeroot-sysv.so\n' in wrapper and
            'PATHS=/usr/lib/x86_64-linux-gnu/libfakeroot:${FAKEROOT_PREFIX}/lib64/libfakeroot:${FAKEROOT_PREFIX}/lib32/libfakeroot\n' in wrapper and
            'FAKED=${FAKEROOT_BINDIR}/faked-sysv\n' in wrapper,
            'complete observed fakeroot wrapper does not select the fixed sysv backend')
    allowed = [Path('/usr/bin'), Path('/usr/sbin'), Path('/usr/lib')]
    rows = []
    executables = []
    for name in IMAGE_TOOL_NAMES:
        before = authority['tools'][name]
        requested = IMAGE_TOOL_PATHS[name]
        require(before['requested_path'] == requested and before['uid'] == 0 and
                shutil.which(name,path=IMAGE_TEST_PATH) == requested,
                'image tool does not match the explicit controlled PATH selection')
        row = image_pin(Path(requested), allowed, before['is_ELF'])
        require(row['sha256'] == before['sha256'] and row['bytes'] == before['bytes'] and
                row['resolved_path'] == before['resolved_path'], 'observed image tool changed: '+name)
        rows.append(row)
        if before['is_ELF']:
            executables.append(Path(requested))
        else:
            require(name == 'fakeroot', 'only the independently read fakeroot script may be a wrapper')
    backends = {row['requested_path']:row for row in authority['backend_observations']}
    for name in (FAKEROOT_DAEMON, FAKEROOT_PRELOAD, '/bin/sh', '/usr/bin/getopt'):
        require(name in backends and backends[name].get('absent') is not True,
                'exact fakeroot backend/interpreter is absent from the fixed read authority')
        before = backends[name]
        row = image_pin(Path(name), allowed, True)
        require(before['is_ELF'] is True and row['sha256'] == before['sha256'] and
                row['bytes'] == before['bytes'] and row['resolved_path'] == before['resolved_path'],
                'fakeroot backend/interpreter changed')
        rows.append(row)
        executables.append(Path(name))
    # These three fixed auxiliary paths were identified in the complete wrapper.
    # They are first observed here before execution, not claimed as reader02 pins.
    auxiliaries = []
    for name in FAKEROOT_AUXILIARIES:
        require(shutil.which(Path(name).name,path=IMAGE_TEST_PATH) == name,
                'fixed fakeroot auxiliary is shadowed in the controlled PATH')
        row = image_pin(Path(name), allowed, True)
        rows.append(row)
        auxiliaries.append(row)
        executables.append(Path(name))
    require(shutil.which('getopt',path=IMAGE_TEST_PATH) == '/usr/bin/getopt',
            'observed getopt is shadowed in the controlled PATH')
    # Fixed root-owned native ELF inputs only; no fixture/candidate program is
    # passed to ldd. Runtime dependencies are held/hash-pinned and rechecked.
    linked = set()
    for index,path in enumerate(executables):
        raw = command(['/usr/bin/ldd',str(path)],COPIED,environment,
                      'image-linked-libraries-'+str(index),report['commands'],10).decode()
        require('not found' not in raw, 'image tool runtime library is missing')
        for line in raw.splitlines():
            match = re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
            if match:
                linked.add(match.group(1))
    for name in sorted(linked):
        rows.append(image_pin(Path(name), allowed+[Path('/lib')], True))
    report['actual_image_tools_authority'] = authority_pin
    report['image_tools_scope'] = {
        'tool_names':list(IMAGE_TOOL_NAMES), 'controlled_test_PATH':IMAGE_TEST_PATH,
        'fixed_fakeroot_daemon':FAKEROOT_DAEMON, 'fixed_fakeroot_preload':FAKEROOT_PRELOAD,
        'auxiliaries_first_observed_before_execution':auxiliaries,
        'fakeroot_args':'-- <actual held test executable> --exact <fixed metadata test> --nocapture',
        'fakeroot_save_or_load_flags_permitted':False,
        'real_ext4_erofs_zip_fakeroot_tests_required':5,
        'mount_or_install_commands_permitted':False,
        'fixtures_are_test_marked_bytes_not_platform_signed_APEX':True,
        'uutils_chown_compatibility_not_assumed':True}
    return list({row['requested_path']:row for row in rows}.values())


def reap_normal_fakeroot_daemon(record):
    # The exact test wrapper owns one daemon and requests its normal TERM on
    # exit. The controller is a subreaper: an exited adopted daemon still needs
    # waitpid. This function never signals a child or treats a live one as done.
    record.update({'maximum_seconds':2,'signal_actions':0,'reaped':[],'remaining':[]})
    deadline = min(time.monotonic()+2, DEADLINE)
    while True:
        current = children()
        record['remaining'] = current
        require(len(current)+len(record['reaped']) <= 1,
                'exact fakeroot test left more than its one owned daemon')
        if not current:
            return
        for pid in current:
            got,status = os.waitpid(pid,os.WNOHANG)
            if got:
                record['reaped'].append({'pid':got,'status':status})
                require((os.WIFEXITED(status) and os.WEXITSTATUS(status)==0) or
                        (os.WIFSIGNALED(status) and os.WTERMSIG(status)==signal.SIGTERM),
                        'owned fakeroot daemon did not exit normally or by wrapper TERM')
        if not children():
            record['remaining'] = []
            return
        require(time.monotonic()<deadline,'owned fakeroot daemon remained live after bounded normal retirement')
        time.sleep(0.01)



def validate_focused_result(name, index, output, log, registered_count):
    # Rust 1.93 libtest writes this one result directly to its own File, so
    # inherited stdout from mkfs.erofs or a nested fakeroot test cannot splice it.
    require(log == ('ok '+name+'\n').encode(),
            'independent libtest result is not exactly one success for the selected test')
    expected_runs = 2 if index == 20 else 1
    require((index == 20) == (name == FAKEROOT_TEST), 'nested fakeroot test index differs')
    summaries = [line for line in output.splitlines() if line.startswith('test result:')]
    pattern = r'test result: ok\. 1 passed; 0 failed; 0 ignored; 0 measured; (\d+) filtered out; finished in \d+(?:\.\d+)?s'
    parsed = [re.fullmatch(pattern, line) for line in summaries]
    require(len(parsed) == expected_runs and all(parsed) and
            all(int(match.group(1)) == registered_count-1 for match in parsed),
            'complete libtest summary/count/filter contract differs')
    require(output.splitlines().count('running 1 test') == expected_runs and
            output.count('test '+name+' ... ') == expected_runs,
            'selected test start/count differs from the exact registration')
    return {'outer_results': 1, 'expected_stdout_runs': expected_runs,
            'registered_tests': registered_count, 'filtered_out_per_run': registered_count-1,
            'exact_name': name, 'summary_and_independent_result_agree': True}


def focused_test(test_binary, name, index, registered_count, environment, records):
    label = 'projection-test-'+str(index)
    path = OUT/(label+'.libtest')
    # Claim a new regular file and retain the descriptor while libtest opens
    # that exact private path. Replacement, aliases and extra records fail.
    fd = os.open(path, os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC, 0o600)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                before.st_uid == os.geteuid() and stat.S_IMODE(before.st_mode) == 0o600 and
                before.st_size == 0, 'fresh libtest result claim differs')
        output = command([str(test_binary),'--exact',name,'--test-threads=1','--nocapture',
                          '--logfile',str(path)],COPIED,environment,label,records,30).decode()
        after = os.fstat(fd)
        require((after.st_dev,after.st_ino,after.st_mode,after.st_uid,after.st_gid,after.st_nlink) ==
                (before.st_dev,before.st_ino,before.st_mode,before.st_uid,before.st_gid,before.st_nlink) and
                after.st_size <= 4096, 'held libtest result object or bound differs')
        log = os.pread(fd,4097,0)
        final = os.fstat(fd)
        require(len(log) == after.st_size and identity(after) == identity(final) == identity(path.lstat()),
                'libtest result changed while read or named path was replaced')
        records[-1]['independent_libtest_result'] = {
            'path': str(path), 'bytes': len(log), 'sha256': sha(log), 'identity': identity(final)}
        result = validate_focused_result(name,index,output,log,registered_count)
        records[-1]['focused_result_gate'] = result
        return result
    finally:
        os.close(fd)


def execute():
    global DEADLINE
    require(os.getuid()==1000 and os.geteuid()==1000,'ordinary operator UID1000 required')
    require(Path(__file__).absolute()==HERE/'compile_builder.py','exact staged controller required')
    real_directory(HERE)
    require(not OUT.exists() and not OUT.is_symlink(),'create-only attempt already exists')
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    (OUT/'tmp').mkdir(mode=0o700)
    DEADLINE=time.monotonic()+550
    libc=ctypes.CDLL(None,use_errno=True)
    require(libc.prctl(36,1,0,0,0)==0,'cannot establish owned subreaper')
    require(not children(),'unexpected initial child')
    allowed=sorted(os.sched_getaffinity(0))
    require(len(allowed)>=3,'cannot leave two logical CPUs free')
    os.sched_setaffinity(0,[allowed[-1]])
    report={'schema':1,'state':'RUNNING','started_utc':utc(),'scope':'fresh builder468 provider closure compile02, 491 source files, 15 exact updater and 9 unchanged source-resume controls; no real published source/staging/Soong/Java/Android/service execution',
            'Main_actions':0,'Main_identity_observed':False,'install_actions':0,'network_downloads_permitted':False,
            'commands':[],'allowed_cpus_before':allowed,'selected_cpus':[allowed[-1]],'expected_test_names':TESTS,'expected_source_resume_test_names':SOURCE_RESUME_TESTS}
    def interrupted(number,frame):
        OBSERVED_SIGNALS.append(number)
        raise RuntimeError('owned controller interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    resource_fd=-1;resource_before=None
    original_rows={};candidate_rows={};dependency_rows={};tool_rows=[];config_rows=[]
    copied_expected=None;config_paths=[];builder=None;builder_pin=None;test_binary=None;test_pin=None
    try:
        resource_fd,resource_before=begin_resources()
        report['owned_resources_before']=resource_before
        go_control_raw,go_control_pin=pinned_packet('go-control-result.json',GO_CONTROL)
        go_control=json.loads(go_control_raw)
        require(go_control['state']=='PASS' and go_control['patch']['sha256']==GO_PATCH and
                go_control['fixture']['sha256']=='5a928d10fbaabab5a1198c9c4a5abe9281da091abdde923a2e0a500071e8fbc5' and
                go_control['whole_output_files_equal']>0 and go_control['owned_resource_gate']['pass'] is True,
                'actual complete-package comparison gate is not qualified')
        report['actual_Go_comparison_gate']=go_control_pin
        report['upstream_vet_pass_claimed']=False
        old_bytes,_=pinned_packet('compiled-parent467-manifest.json',MANIFEST_PARENT)
        new_bytes,_=pinned_packet('expected-builder468-manifest.json',MANIFEST_468)
        expected=json.loads(old_bytes);copied_expected=json.loads(new_bytes)
        require(len(expected)==466 and len(copied_expected)==491,'source manifest count changed')
        original_rows,copied_before=exact_source_copy(expected)
        original_manifest=portable(original_rows,expected)
        report['original_manifest']=write_new(OUT/'original-builder-source-manifest.json',(json.dumps(original_manifest,indent=2)+'\n').encode())
        env={'PATH':'/usr/bin:/bin','HOME':'/home/alex','CARGO_HOME':str(CARGO_HOME),
             'RUSTC':str(RUST_SYSROOT/'bin/rustc'),'RUSTDOC':str(RUST_SYSROOT/'bin/rustdoc'),
             'CARGO_NET_OFFLINE':'true','LC_ALL':'C','LANG':'C',
             'TMPDIR':str(OUT/'tmp'),'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
        tools,tool_rows=toolchain(report,env)
        report['tool_inputs']=write_new(OUT/'tool-inputs-before.json',tool_rows)
        parent_raw,parent_pin=pinned_packet('compiled-parent467-result.json',
            'cd9f61ca21dd83210299f24dd50b68f5aa7aeba7eab94ac9cada71271d660e28')
        parent=json.loads(parent_raw)
        require(parent_pin['bytes']==140163 and parent['state']=='PASS' and
                parent['focused_tests_passed']==18 and parent['updater_focused_tests_passed']==9 and
                parent['source_resume_tests_passed']==9 and parent['actual_registered_test_count']==199 and
                parent['source_actual_registered_test_count']==20 and
                len(parent['commands'])==56 and all(row['returncode']==0 and not row['timed_out'] for row in parent['commands']) and
                parent['copied_manifest']['bytes']==91945 and parent['copied_manifest']['sha256']==MANIFEST_PARENT and
                parent['builder_elf']['bytes']==34579760 and
                parent['builder_elf']['sha256']=='fd4ef1903fa506512f2605fa03b39b5af0712680ff26dfbebfb4683c1b9ec288' and
                parent['owned_resource_gate']['pass'] is True and not parent['dependency_changes'] and
                not parent['tool_changes'] and not parent['cleanup']['errors'] and not parent['cleanup']['remaining'] and
                not parent['cleanup']['forced_cleanup'] and parent['copied_source_unchanged_after'] is True and
                parent['original_source_unchanged_after'] is True and parent['cargo_configs_unchanged_after'] is True,
                'actual compiled parent467 qualification differs')
        report['actual_parent467_compile_authority']=parent_pin
        roots_raw,roots_pin=pinned_packet('typed-root-trees-result.json',
            '0088aaea045f1c0e048db1a65184e536495f3d0d8a9721cd668bdfa0016b43e8')
        roots=json.loads(roots_raw)
        require(roots['state']=='PASS_THREE_FIXED_COMMIT_ROOT_TREES' and
                roots['all_started_children_joined'] is True and roots['first_error'] is None and
                not roots['secondary_errors'] and roots['owned_resource_gate']['pass'] is True and
                roots['source_lock_reference_sha256']==expected['android/manifest/m2-sparse-source-lock.json']['sha256'],
                'actual fixed root-tree input authority differs')
        derivation_raw,derivation_pin=pinned_packet('typed-lock-derivation.json',
            'c5cd3f0efd5519b8e724a42b7fc27850e20dc5a5ea55fff868366e902b56c3e0')
        derivation=json.loads(derivation_raw)
        require(derivation['state']=='DERIVED_THREE_PROJECT_SOURCE_EXTENSION_NOT_COMPILED' and
                derivation['actual_report_sha256']==roots_pin['sha256'] and
                derivation['base_lock_sha256']==roots['source_lock_reference_sha256'] and
                derivation['derived_lock_sha256']==copied_expected['android/manifest/m2-role-ingress-source-lock.json']['sha256'] and
                derivation['derived_lock_bytes']==copied_expected['android/manifest/m2-role-ingress-source-lock.json']['bytes'] and
                derivation['other_lock_fields_unchanged'] is True and derivation['original_lock_modified'] is False,
                'derived lock authority does not bind the exact source delta')
        report['actual_typed_root_tree_authority']=roots_pin
        report['typed_lock_derivation_authority']=derivation_pin
        closure_raw,closure_pin=pinned_packet('provider-closure-proof.json',CLOSURE_PROOF_SHA)
        closure=json.loads(closure_raw)
        require(closure['state']=='SOURCE_CANDIDATE_NOT_COMPILED_OR_SOONG_QUALIFIED' and
                closure['baseline']['manifest']['sha256']==MANIFEST_PARENT and
                closure['baseline']['compile_result']['sha256']==parent_pin['sha256'] and
                closure['source_delta']['expected_manifest']['sha256']==MANIFEST_468 and
                closure['source_locks']['previous_typed_unchanged']==expected['android/manifest/m2-role-ingress-source-lock.json']['sha256'] and
                closure['source_locks']['candidate']['sha256']==copied_expected['android/manifest/m2-role-ingress-provider-source-lock.json']['sha256'] and
                closure['source_locks']['candidate']['bytes']==copied_expected['android/manifest/m2-role-ingress-provider-source-lock.json']['bytes'] and
                closure['validation']['remote_compile_pending'] is True and
                closure['strictness']['ALLOW_MISSING_DEPENDENCIES']=='false' and
                closure['strictness']['targets']==['framework-minus-apex','libandroid_runtime'],
                'provider closure proof does not bind the exact candidate')
        report['provider_closure_derivation_authority']=closure_pin
        changes=[name for name in copied_expected if copied_expected[name]!=expected.get(name)]
        wanted=FIXED_PROVIDER_DELTA
        require(sorted(changes)==wanted and set(expected).issubset(copied_expected) and
                sum(name not in expected for name in changes)==25 and
                sum(name in expected for name in changes)==2 and
                set(copied_expected)-set(expected)==set(closure['source_delta']['added']) and
                all(copied_expected[name]==expected[name] for name in expected if name not in wanted),
                'provider delta is not exactly two replacements and twenty-five additions')
        for name in changes:
            wanted_row=copied_expected[name]
            data,pin=pinned_packet('delta/'+name,wanted_row['sha256'])
            require(pin['bytes']==wanted_row['bytes'] and wanted_row['kind']=='file','provider source delta differs')
            target=COPIED/name
            if name in expected:
                require(hash_held(target)==copied_before[name],
                        'copied parent source differs before provider delta')
                fd=os.open(target,os.O_WRONLY|os.O_TRUNC|os.O_CLOEXEC|os.O_NOFOLLOW)
                with os.fdopen(fd,'wb') as stream:
                    require(stream.write(data)==len(data),'short provider delta write')
                    stream.flush();os.fsync(stream.fileno())
            else:
                write_new(target,data)
            os.chmod(target,wanted_row['mode'],follow_symlinks=False)
        candidate_rows=regular_tree(COPIED)
        actual_map=portable(candidate_rows,copied_expected)
        require(json.loads(new_bytes)==actual_map and sha(new_bytes)==MANIFEST_468,
                'actual copied 491-file builder468 manifest differs')
        report['copied_manifest']=write_new(OUT/'copied-builder-source-manifest.json',new_bytes)
        report['source_delta']={'changed_existing':[name for name in wanted if name in expected],
                                'added':[name for name in wanted if name not in expected],
                                'unchanged_existing':464,'actual_source_file_count':491,
                                'builder_revision_name':'468-provider-closure','Rust_source_files_changed':2,
                                'Cargo_lock_or_dependency_manifest_changed':False,
                                'Go5_or_Blueprint_patch_changed':False,'engine_source_files_changed':0,
                                'typed_ingress_framework_patch_changed':False,'previous_source_locks_changed':False,
                                'new_exact_provider_source_lock_added':True,
                                'source_resume_library_changed':False,'real_published_source_accessed':False,
                                'real_source_staging_accessed':False,'framework_sources_executed_or_built':False,
                                'runtime_authorization_enabled':False}
        env.update({'PATH':str(tools['cargo'].parent)+':/usr/bin:/bin','RUSTC':str(tools['rustc']),
                    'RUSTDOC':str(tools['rustdoc']),'RUSTDOCFLAGS':'','CARGO_ENCODED_RUSTDOCFLAGS':'',
                    'RUSTC_WRAPPER':'','RUSTC_WORKSPACE_WRAPPER':'','RUSTFLAGS':'','CARGO_ENCODED_RUSTFLAGS':'',
                    'CARGO_TARGET_DIR':str(OUT/'cargo-target'),'CARGO_BUILD_JOBS':'1',
                    'CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER':'/usr/bin/cc'})
        require('/home/alex/.cargo/bin' not in env['PATH'].split(':') and
                all(shutil.which(name,path=env['PATH'])==str(tools[name]) for name in ['cargo','rustc','rustdoc']) and
                not any(name.startswith('RUSTUP') for name in env) and
                all(name not in env for name in ('LD_PRELOAD','LD_LIBRARY_PATH','RUSTC_BOOTSTRAP')),
                'fixed direct compiler tools are shadowed or proxy environment was reintroduced')
        config_paths=[CARGO_HOME/'config',CARGO_HOME/'config.toml']
        for parent in [COPIED,*COPIED.parents]:
            config_paths += [parent/'.cargo/config',parent/'.cargo/config.toml']
        config_rows=read_existing_config(config_paths)
        report['cargo_config_inputs_before']=config_rows
        report['build_environment']=env
        tool_rows += image_toolchain(report,env)
        report['image_and_compiler_tool_inputs']=write_new(OUT/'all-tool-inputs-before-tests.json',tool_rows)
        require(all(row.get('absent') is True for row in config_rows),
                'selected cache qualification requires the actually observed absent Cargo configuration inputs')
        selection_raw,selection_pin=pinned_packet('selection-result.json','185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf')
        selection=json.loads(selection_raw)
        require(selection['state']=='PASS' and selection['owned_resource_gate']['pass'] is True and
                all(selection[k] is True for k in ['source_unchanged_after','tools_unchanged_after','configs_unchanged_after','authority_unchanged_after']) and
                len(selection['commands'])==3 and all(c['returncode']==0 for c in selection['commands']),
                'actual offline selection observation is not qualified')
        observed_tree,tree_pin=pinned_packet('selected-build.stdout','82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d')
        require(selection['commands'][1]['stdout']['sha256']==tree_pin['sha256'] and selection['commands'][2]['stdout']['sha256']==tree_pin['sha256'],
                'actual selected tree does not bind both build and test dependency queries')
        report['actual_selected_dependency_authority']=selection_pin
        metadata_raw=command([str(tools['cargo']),'metadata','--offline','--locked','--no-deps','--format-version','1'],COPIED,env,'workspace-no-deps',report['commands'],30)
        metadata=json.loads(metadata_raw)
        trees=[]
        for label,edges in [('selected-build','normal,build'),('selected-test','normal,build,dev')]:
            trees.append(command([str(tools['cargo']),'tree','--offline','--locked','-p','droidloom-update','--target','x86_64-unknown-linux-gnu',
                                  '--edges',edges,'--prefix','none','--format','{p}','--color','never'],COPIED,env,label,report['commands'],30))
        registry_raw,registry_pin=pinned_packet('registry-result.json','b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993')
        registry=json.loads(registry_raw)
        require(registry['state']=='PASS' and registry['collection_complete'] is True and
                registry['all_45_archive_and_source_matches'] is True and registry['authorities_unchanged_after'] is True and
                registry['owned_resource_gate']['pass'] is True and len(registry['packages'])==45,
                'actual existing archive/source qualification is incomplete')
        registry_authority={(r['name'],r['version']):r for r in registry['packages']}
        require(len(registry_authority)==45,'duplicate registry authority package')
        report['actual_registry_archive_authority']=registry_pin
        package_id,packages,dependency_rows=dependency_sources(metadata,trees[0],trees[1],observed_tree,registry_authority)
        report['dependency_inputs']=write_new(OUT/'dependency-inputs-before.json',{'packages':packages,'files':dependency_rows})
        common=[str(tools['cargo']),'--offline','--locked','-j','1','-p','droidloom-update','--bin','droidloom-update']
        build=command([common[0],'build',*common[1:],'--message-format=json-render-diagnostics'],COPIED,env,'builder-compile',report['commands'],240)
        report['actual_build_packages']=qualify_compiler_inputs(build,packages,dependency_rows,candidate_rows)
        builder=build_artifact(build,package_id,False)
        builder_pin=hash_held(builder)
        require((builder.lstat().st_mode&0o111)!=0,'builder artifact is not executable')
        with builder.open('rb') as stream:
            require(stream.read(4)==b'\x7fELF','builder artifact is not ELF')
        help_output=command([str(builder),'--help'],COPIED,env,'builder-help',report['commands'],10)
        require(b'Usage:' in help_output and b'native-engine-build' in help_output and
                b'native-generation-pair' in help_output and b'native-generation-art-build' in help_output and
                b'native-role-ingress-build' in help_output,
                'normal builder or explicit paired-record/ART/typed-ingress build-only CLI missing')
        resume_help=command([str(builder),'native-role-ingress-build','--help'],COPIED,env,'source-resume-cli-help',report['commands'],10)
        require(all(option in resume_help for option in [b'--work',b'--out',b'--resume-source-staging']),
                'typed source-resume CLI does not expose the explicit fixed route arguments')
        test_build=command([common[0],'test',*common[1:],'--no-run','--message-format=json-render-diagnostics'],COPIED,env,'builder-test-compile',report['commands'],180)
        report['actual_test_compile_packages']=qualify_compiler_inputs(test_build,packages,dependency_rows,candidate_rows)
        test_binary=build_artifact(test_build,package_id,True)
        test_pin=hash_held(test_binary)
        test_list=command([str(test_binary),'--list'],COPIED,env,'builder-test-list',report['commands'],10).decode()
        require(len(ORIGINAL_TESTS)==7 and len(PAIR_TESTS)==15 and len(ART_PROJECTION_TESTS)==2 and len(TYPED_INGRESS_TESTS)==2 and len(PARENT_TESTS)==len(set(PARENT_TESTS))==26 and
                len(PROVIDER_CLOSURE_TESTS)==6 and len(TESTS)==len(set(TESTS))==15 and
                all(test_list.splitlines().count(name+': test')==1 for name in PARENT_TESTS+PROVIDER_CLOSURE_TESTS),
                'original 26 registrations or six provider controls absent/duplicated in actual test executable')
        listed_names=[line[:-6] for line in test_list.splitlines() if line.endswith(': test')]
        require(len(listed_names)==205 and len(listed_names)==len(set(listed_names)) and
                not any(line.endswith(': benchmark') for line in test_list.splitlines()),
                'actual registration list is duplicate/empty or contains unqualified benchmarks')
        libtest_help=command([str(test_binary),'--help'],COPIED,env,'builder-test-help',report['commands'],10).decode()
        require(re.search(r'^\s*--logfile\s',libtest_help,re.MULTILINE) is not None and
                'Write logs to the specified file' in libtest_help,
                'actual pinned libtest does not advertise the independently reviewed logfile option')
        report['actual_libtest_logfile_support']=True
        report['actual_registered_test_count']=len(listed_names)
        test_env=dict(env)
        test_env['PATH']=IMAGE_TEST_PATH
        require(all(name not in test_env for name in ('FAKEROOTKEY','LD_PRELOAD','LD_LIBRARY_PATH')),
                'test environment already contains fakeroot state')
        report['test_environment']=test_env
        report['focused_result_gates']=[]
        for index,name in enumerate(TESTS):
            report['focused_result_gates'].append(focused_test(
                test_binary,name,index,len(listed_names),test_env,report['commands']))
        source_packages=[p for p in metadata['packages'] if p['name']=='droidloom-source' and
                         p['manifest_path']==str(COPIED/'tools/droidloom-source/Cargo.toml') and p['source'] is None]
        require(len(source_packages)==1,'source controls do not identify the exact copied library package')
        source_package=source_packages[0]
        source_tree=command([str(tools['cargo']),'tree','--offline','--locked','-p','droidloom-source',
                             '--target','x86_64-unknown-linux-gnu','--edges','normal,build,dev',
                             '--prefix','none','--format','{p}','--color','never'],
                            COPIED,env,'source-resume-selected-test',report['commands'],30)
        selected_source=parse_selected_tree(source_tree,COPIED)
        selected_builder=parse_selected_tree(trees[1],COPIED)
        require(selected_source and all(key in selected_builder and selected_builder[key]==directory
                for key,directory in selected_source.items()),
                'source test dependency closure adds a package outside the already qualified complete builder closure')
        source_build=command([str(tools['cargo']),'test','--offline','--locked','-j','1','-p',
                              'droidloom-source','--lib','--no-run','--message-format=json-render-diagnostics'],
                             COPIED,env,'source-resume-test-compile',report['commands'],90)
        report['actual_source_test_compile_packages']=qualify_compiler_inputs(
            source_build,packages,dependency_rows,candidate_rows)
        source_artifacts=[]
        for line in source_build.decode().splitlines():
            if not line.strip():continue
            item=json.loads(line)
            if item.get('reason')=='compiler-artifact' and item.get('package_id')==source_package['id'] and item.get('executable'):
                require(item['profile']['test'] is True and item['target']['kind']==['lib'] and
                        item['target']['src_path']==str(COPIED/'tools/droidloom-source/src/lib.rs'),
                        'source control artifact is not the exact copied library test target')
                source_artifacts.append(Path(item['executable']))
        require(len(source_artifacts)==1 and source_artifacts[0].is_relative_to(OUT/'cargo-target'),
                'source test executable is ambiguous or escaped the new target')
        source_test_binary=source_artifacts[0]
        source_test_pin=hash_held(source_test_binary)
        require(source_test_binary.lstat().st_mode&0o111,'source test artifact is not executable')
        with source_test_binary.open('rb') as stream:
            require(stream.read(4)==b'\x7fELF','source test artifact is not ELF')
        source_list=command([str(source_test_binary),'--list'],COPIED,env,'source-resume-test-list',report['commands'],10).decode()
        source_names=[line[:-6] for line in source_list.splitlines() if line.endswith(': test')]
        require(len(source_names)==len(set(source_names))==20 and set(source_names)==set(SOURCE_REGISTERED_TESTS) and
                not any(line.endswith(': benchmark') for line in source_list.splitlines()),
                'source test registrations differ from the eleven baseline and nine new controls')
        source_help=command([str(source_test_binary),'--help'],COPIED,env,'source-resume-test-help',report['commands'],10).decode()
        require(re.search(r'^\s*--logfile\s',source_help,re.MULTILINE) is not None and
                'Write logs to the specified file' in source_help,
                'source test executable lacks independent libtest result support')
        report['source_resume_result_gates']=[]
        # Keep source labels disjoint from the historical exact fakeroot label 20.
        for index,name in enumerate(SOURCE_RESUME_TESTS,start=100):
            report['source_resume_result_gates'].append(focused_test(
                source_test_binary,name,index,len(source_names),test_env,report['commands']))
        require(hash_held(source_test_binary)==source_test_pin,'source test ELF changed while tested')
        report['source_test_elf']=source_test_pin
        report['source_actual_registered_test_count']=len(source_names)
        report['source_resume_tests_passed']=len(SOURCE_RESUME_TESTS)
        report['source_original_tests_listed_not_rerun']=len(SOURCE_REGISTERED_TESTS)-len(SOURCE_RESUME_TESTS)
        report['source_test_fixtures_network_disabled']=True
        report['actual_device_staging_reuse_qualified']=False
        require(hash_held(builder)==builder_pin and hash_held(test_binary)==test_pin,'actual ELF changed while tested')
        report['builder_elf']=builder_pin
        report['test_elf']=test_pin
        report['updater_focused_tests_passed']=len(TESTS)
        report['focused_tests_passed']=len(TESTS)+len(SOURCE_RESUME_TESTS)
        report['original_projection_tests_passed']=len(ORIGINAL_TESTS)
        report['pairing_tests_passed']=0
        report['ART_projection_tests_passed']=0
        report['typed_ingress_lock_tests_passed']=len(TYPED_INGRESS_TESTS)
        report['provider_closure_tests_passed']=len(PROVIDER_CLOSURE_TESTS)
        report['framework_Java_and_Android_JNI_compiled']=False
        report['transitive_framework_closure_qualified']=False
        report['runtime_authorization_enabled']=False
        report['real_image_test_count']=0
        report['parent_targeted_tests_passed_historically']=18
        report['parent_only_test_names_not_rerun']=PAIR_TESTS+ART_PROJECTION_TESTS
        report['platform_APEX_signature_validated']=False
        report['actual_enabled_ART_lifecycle_validated']=False
        require(len(report['commands'])==62 and all(row['returncode']==0 and not row['timed_out'] for row in report['commands']),
                'fixed provider compiler command sequence differs')
        report['state']='PASS'
    except Exception as error:
        report['state']='FAIL'
        report['error']=repr(error)
        report['error_detail']={'type':type(error).__name__,'message':str(error),'errno':getattr(error,'errno',None),'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['observed_signals']=OBSERVED_SIGNALS
        report['cleanup']=cleanup_children()
        for label,source,rows in [('original_source',BASE_SOURCE,original_rows),('copied_source',COPIED,candidate_rows)]:
            try:
                unchanged=bool(rows) and regular_tree(source)==rows
                report[label+'_unchanged_after']=unchanged
                if not unchanged:
                    report['state']='FAIL'
            except Exception as error:
                report[label+'_after_error']=repr(error);report['state']='FAIL'
        changes=[]
        for path,row in dependency_rows.items():
            try:
                if hash_held(Path(path))!=row:
                    changes.append(path)
            except Exception as error:
                changes.append({'path':path,'error':repr(error)})
        report['dependency_changes']=changes
        report['tool_changes']=verify_resolved(tool_rows)
        try:
            report['cargo_configs_unchanged_after']=bool(config_rows) and read_existing_config(config_paths)==config_rows
        except Exception as error:
            report['cargo_configs_unchanged_after']=False;report['cargo_config_after_error']=repr(error)
        if changes or report['tool_changes'] or not report['cargo_configs_unchanged_after']:
            report['state']='FAIL'
        cleanup=report['cleanup']
        if cleanup['forced_cleanup'] or cleanup['remaining'] or cleanup['errors']:
            report['state']='FAIL'
        try:
            require(resource_fd>=0 and resource_before is not None,'owned resource admission not observed')
            report['owned_resource_gate']=finish_resources(resource_fd,resource_before,report)
        except Exception as error:
            report['owned_resource_gate']={'pass':False,'error':repr(error)};report['state']='FAIL'
        finally:
            if resource_fd>=0:
                os.close(resource_fd)
        report['finished_utc']=utc()
        result=write_new(OUT/'result.json',report)
        print(json.dumps({'state':report['state'],'result':result,'builder_elf':report.get('builder_elf'),
                          'Main_actions':0,'full_engine_build':False}),flush=True)
    return 0 if report['state']=='PASS' else 1

if __name__=='__main__':
    if sys.argv[1:]==[]:
        print(json.dumps({'mode':'PLAN','root':str(ROOT),'base_source':str(BASE_SOURCE),'source_files':491,
                          'requires_explicit_execute_once':True,'Rust_toolchain':TOOLCHAIN,'Main_actions':0,
                          'Android_and_full_engine_execution':False,'focused_existing_tests':TESTS,'source_resume_tests':SOURCE_RESUME_TESTS}))
    elif sys.argv[1:]==['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: compile_builder.py [--execute-once]')
