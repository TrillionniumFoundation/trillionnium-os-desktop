#!/usr/bin/env python3
"""One fresh ai395 normal strict complete Native engine and ART APEX pair build and source recovery."""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time
import traceback

CONTROL = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ai395_build_support', CONTROL / 'ai395_build_support.py')
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
ROOT = Path('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1')
WORK = ROOT / 'work'
SOURCE = WORK / 'aosp-source'
RECIPE = ROOT / 'recipe-provider-r1'
TOOLS = ROOT / 'tools-provider-r1'
OUTPUT_ROOT = Path('/home/qq/work/pocket4-native-build597-ai395-20261108-8b88-r1')
OUT = OUTPUT_ROOT / 'out-r4'
TEMPORARY = WORK / 'native-build-tmp-r4'
RESULT = ROOT / 'qualification/full-ai395-r4'
UNIT = 'p4-native-source600-full-ai395-20261109-8b88-r4.service'
MANIFEST_SHA = '31266faa7a39385eb0dd429d16617196e51397e638384d10eb22541068687d11'
MANIFEST_BYTES = 392937
LOCK_SHA = '600dc00660af69b4b8eeb497fac8f2a83f0d8b24ad3d02c2774a4df96f5ec8cf'
pair = s.load_module(CONTROL / 'native_pair_control.py')
command_witness = s.load_module(CONTROL / 'process_command_witness.py')
RELATIVE = tuple(dict.fromkeys(pair.ART_PATHS + tuple(pair.REQUIRED_COMPILE_SOURCES)))
RECOVERY_SHA = 'c4b3487bdf6ce27705881071d8466add5a4d28a82eccab846c655b0751d35932'
NATIVE_PREBUILT_BP = 'prebuilts/misc/common/robolectric-native-prebuilt/Android.bp'
NATIVE_PREBUILT_BP_SHA = 'd1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a'


def environment():
    return {
        'HOME': '/home/qq', 'PATH': str(TOOLS) + ':/usr/bin:/bin:/usr/sbin:/sbin',
        'LANG': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
        'GIT_OPTIONAL_LOCKS': '0', 'GIT_CONFIG_COUNT': '2', 'GIT_CONFIG_KEY_0': 'maintenance.auto',
        'GIT_CONFIG_VALUE_0': 'false', 'GIT_CONFIG_KEY_1': 'gc.auto', 'GIT_CONFIG_VALUE_1': '0',
        'DROIDLOOM_NATIVE_BRIDGE_SOURCE': str(ROOT / 'inputs/engine-working'),
        'DROIDLOOM_COMPILER_CPUS_RESERVED': '1', 'GOMAXPROCS': '2', 'GOMEMLIMIT': '5GiB',
        'GOGC': '50', 'GODEBUG': 'gctrace=1', 'NINJA_ARGS': '-d keeprsp -d keepdepfile',
        'PYTHONDONTWRITEBYTECODE': '1',
        'TMPDIR': str(TEMPORARY), 'GOTMPDIR': str(TEMPORARY),
        'ALLOW_MISSING_DEPENDENCIES': 'false',
    }


def small_stdout(record):
    return s.pinned(record['stdout'], 4 * 1024**2, contents=True)[1]


def source_qualification(commands, name, config, *, recovery=False):
    env = environment()
    lock = RECIPE / 'android/native-generation-pair/source-lock.json'
    for ref in config['normal_tools'] + config['fixed_assets'] + config['recipe_control_sources']:
        s.pinned(ref)
    helper = s.pinned(config['recovery_only_tool'])
    s.need(helper['bytes'] == 32204872 and helper['sha256'] == RECOVERY_SHA,
           'separate reviewed normal recovery-only tool differs')
    commands.run('normal-lock-' + name, [str(TOOLS / 'droidloom-source'), 'verify-lock', '--lock', str(lock)],
                 120, cwd=RECIPE, env=env, recovery=recovery)
    commands.run('normal-materialized-' + name, [str(TOOLS / 'droidloom-source'), 'verify-materialized',
                 '--lock', str(lock), '--output', str(SOURCE)], 1200, cwd=RECIPE, env=env, recovery=recovery)
    manifest = s.file_ref(SOURCE / '.droidloom-source-manifest.json', 1024**2)
    s.need(manifest['bytes'] == MANIFEST_BYTES and manifest['sha256'] == MANIFEST_SHA,
           'fresh normal materialized Source600 epoch changed')
    s.need(s.file_ref(lock)['sha256'] == LOCK_SHA, 'exact Native source lock changed')
    for key, expression, expected in (('head', 'HEAD', config['recipe_commit']),
                                      ('tree', 'HEAD^{tree}', config['recipe_tree'])):
        row = commands.run('recipe-' + key + '-' + name, ['/usr/bin/git', 'rev-parse', expression],
                           30, cwd=RECIPE, env=env, recovery=recovery)
        s.need(small_stdout(row).decode().strip() == expected, 'actual recipe revision differs')
    # The tested producer preserves the 458-file recipe, adding only the reviewed
    # original provider inputs in its lock and normal validators. Check this generation;
    # the historical 515-file packet remains provenance, not current authority.
    exact_tree(RECIPE, config['recipe_source_files'], 458, ignore_git=True)
    s.need(not (RECIPE / '.git/objects/info/alternates').exists()
           and not (RECIPE / '.git/objects/info/http-alternates').exists(),
           'new-host recipe must remain independent of old absolute object stores')
    commands.run('recipe-self-contained-' + name, ['/usr/bin/git', 'fsck', '--full', '--strict', '--no-dangling'],
                 180, cwd=RECIPE, env=env, recovery=recovery)
    engine = ROOT / 'inputs/engine-working'
    exact_tree(engine, config['engine_working_files'], 926, ignore_git=True)
    for relative, inventory in config['companion_files'].items():
        s.need(relative in ('mesa-source', 'python'), 'only the two actual companion sources are admitted')
        exact_tree(WORK / relative, inventory, len(inventory), ignore_git=False)
    row = s.file_ref(SOURCE / NATIVE_PREBUILT_BP, 65536)
    s.need(row['bytes'] == 1017 and row['sha256'] == NATIVE_PREBUILT_BP_SHA,
           'frozen native prebuilt provider differs')
    return manifest


def exact_tree(root, expected, count, *, ignore_git):
    s.need(type(expected) is dict and len(expected) == count and count > 0,
           'complete frozen source map required')
    seen = set()
    for directory, directories, files in os.walk(root, followlinks=False):
        if ignore_git and Path(directory) == root:
            directories[:] = [name for name in directories if name != '.git']
        for name in list(directories):
            path = Path(directory) / name
            if path.is_symlink():
                files.append(name); directories.remove(name)
        for name in files:
            path = Path(directory) / name; relative = path.relative_to(root).as_posix()
            s.need(relative in expected, 'unapproved additional source file: ' + relative)
            row = expected[relative]; info = path.lstat()
            s.need(stat.S_IMODE(info.st_mode) == row['mode'], 'source permission changed: ' + relative)
            if row['kind'] == 'file':
                actual = s.file_ref(path)
                s.need(actual['bytes'] == row['bytes'] and actual['sha256'] == row['sha256'],
                       'complete source bytes changed: ' + relative)
            else:
                s.need(row['kind'] == 'symlink' and stat.S_ISLNK(info.st_mode)
                       and os.readlink(path) == row['target'], 'complete source link changed: ' + relative)
            seen.add(relative)
    s.need(seen == set(expected), 'complete source map has missing files')


def source_extension_qualification(config):
    """Bind the actual normal extension; old transfer records stay provenance."""
    reference, raw = s.pinned(config['normal_source_extension'], contents=True)
    extension = json.loads(raw)
    s.need(extension['schema'] == 'native600-original-provider-normal-source-extension-v1'
           and extension['state'] == 'NATIVE600_ORIGINAL_PROVIDER_INPUTS_NORMAL_RECONCILED'
           and extension['build_host'] == 'ai395' and extension['host_generation_inherited'] is False
           and type(extension['source_project_count']) is int and extension['source_project_count'] == 600
           and type(extension['full_builds_started']) is int and extension['full_builds_started'] == 0
           and extension['runtime_qualified'] is False and extension['artifact_qualified'] is False
           and extension['normal_source_extension_verified'] is True
           and extension['source_delta_only_authenticated_original_inputs'] is True
           and extension['all_native_owner_locks_released'] is True
           and extension['all_command_children_retired'] is True and extension['errors'] == [],
           'new normal source extension is incomplete')
    s.need(extension['manifest_before']['bytes'] == 386435
           and extension['manifest_before']['sha256'] == '924637edc039b0f23013a7ca921b4c6c05a0800574599742cddcc75eeed160e2'
           and extension['original_source_lock']['sha256'] == 'b1fb40b9de4e2ab35407022862706b9d0a7e580a59e607b27bc9d99ec0a67fbb'
           and extension['source_lock']['path'] == str(RECIPE / 'android/native-generation-pair/source-lock.json')
           and extension['source_lock']['sha256'] == LOCK_SHA
           and extension['manifest_after']['path'] == str(SOURCE / '.droidloom-source-manifest.json')
           and extension['manifest_after']['bytes'] == MANIFEST_BYTES
           and extension['manifest_after']['sha256'] == MANIFEST_SHA,
           'normal source extension is not the approved original provider delta')
    for key in ('path', 'bytes', 'sha256'):
        s.need(extension['recipe_import'][key] == config['new_recipe_tool_import'][key]
               and extension['previous_failed_full']['inner'][key] == config['previous_failed_full']['inner'][key]
               and extension['previous_failed_full']['outer'][key] == config['previous_failed_full']['outer'][key],
               'source continuation belongs to a different recipe or failed full')
    guards = s.load_module(CONTROL / 'audio_continuation_control.py')
    actual = {name: json.loads(s.pinned(ref, contents=True)[1])
              for name, ref in config['normal_source_extension_H'].items()}
    terminal = config['normal_source_extension_terminal']
    guards.validate_raw_exit(actual['exit'], actual['request'], actual['started'],
        expected_exit_code=0, expected_at_unix_ms=terminal['at_unix_ms'],
        expected_stream_bytes=terminal['stream_bytes'])
    s.need(actual['exit']['job_id'] == '1a1be661aec-5e21-96', 'normal source extension H generation differs')
    plan_ref, plan_raw = s.pinned(extension['reviewed_source_plan'], contents=True)
    delta_ref = s.pinned(extension['normal_recipe_delta'])
    s.need(plan_ref['bytes'] == 320654 and plan_ref['sha256'] ==
           '1c0b36787b8b3802e5aafe3ab3eb04918e89cd23eebdc976027046ea556c1eab'
           and delta_ref['bytes'] == 2293 and delta_ref['sha256'] ==
           'd401a7e2f8d7fe8214254a4820e173626f6f5d78e3b8302f20c8a60a0a6e6e59',
           'complete reviewed source delta bytes differ')
    plan = json.loads(plan_raw)
    expected = {str(SOURCE / row['path']): row['sha256'] for row in plan['added_blueprint_files']}
    files = extension['normal_materialized_provider_files']
    s.need(len(files) == len(expected) == 297 and {row['path'] for row in files} == set(expected)
           and all(row['sha256'] == expected[row['path']] for row in files),
           'all normal materialized original provider inputs are required')
    for ref in files:
        s.pinned(ref)
    s.pinned(extension['source_lock']); s.pinned(extension['manifest_after'])
    return reference


def art_preimages():
    result = {}
    for relative in pair.ART_PATHS:
        path = SOURCE / relative
        try:
            info = path.lstat()
        except FileNotFoundError:
            result[relative] = {'absent': True}
        else:
            ref = s.file_ref(path, 2 * 1024**2)
            result[relative] = {'bytes': ref['bytes'], 'sha256': ref['sha256'],
                                'mode': stat.S_IMODE(info.st_mode)}
    return result


def snapshot_effective(row, processes, work_locks, outer_ref, expected_argv, executable_ref):
    s.need(row['lifecycle']['pidfd_closed'] is False, 'owned child PIDFD must remain held')
    with command_witness.PinnedExecutable(executable_ref) as executable:
        before = s.process_identity(row['driver']['pid'])
        generation = command_witness.validate_executed_command(
            row['driver'], before, expected_argv, executable_ref['path'])
        executable.verify_running(before['pid'])
        environment_before = command_witness.validate_temporary_environment(
            (Path('/proc') / str(before['pid']) / 'environ').read_bytes(), str(TEMPORARY))
        s.need(before['exe'] == str(TOOLS / 'droidloom-update') and before['cgroup'] == '0::/system.slice/' + UNIT + '\n',
               'actual normal driver is outside the fresh owned build cgroup')
        path = RESULT / 'effective-inputs'; path.mkdir(mode=0o700)
        begun_ns = time.time_ns()
        lock_rows = []
        kernel = Path('/proc/locks').read_text(); s.need(len(kernel) <= 1024**2, 'bounded kernel lock table required')
        for old in work_locks:
            ref, raw = s.file_ref(old['path'], 4096, contents=True)
            s.need(ref['identity'][:2] == old['identity'][:2] and raw == (str(before['pid']) + '\n').encode(),
                   'fresh normal lock owner or inode differs')
            dev, inode = ref['identity'][:2]
            key = '%02x:%02x:%s' % (os.major(dev), os.minor(dev), inode)
            found = [line for line in kernel.splitlines() if len(line.split()) >= 8
                     and line.split()[1] == 'FLOCK' and line.split()[4] == str(before['pid']) and line.split()[5] == key]
            s.need(len(found) == 1, 'fresh normal driver does not hold its work lock')
            lock_rows.append({'reference': ref, 'kernel_flock': found[0]})
        journal = s.file_ref(WORK / 'source-projection.json', 128 * 1024**2,
                             copy_to=path / 'source-projection.original.json')
        normal_inputs, normal_ref = s.read_json(OUT / 'droidloom-native-generation-build-inputs.json')
        s.need(normal_inputs['required_actual_compile_sources'] == pair.REQUIRED_COMPILE_SOURCES
               and normal_inputs['targets'] == pair.TARGETS and normal_inputs['dependency_mode'] == 'Strict',
               'actual normal pair compile-source declaration differs')
        s.file_ref(normal_ref['path'], 8 * 1024**2, copy_to=path / 'normal-build-inputs.json')
        files = []
        for index, relative in enumerate(RELATIVE):
            copy = path / ('%02d-' % index + Path(relative).name)
            ref = s.file_ref(SOURCE / relative, 2 * 1024**2, copy_to=copy)
            expected = normal_inputs['effective_source_projection']['files'].get(relative)
            if relative.startswith('frameworks/libs/binary_translation/'):
                expected = normal_inputs['effective_engine_files'][relative[len('frameworks/libs/binary_translation/'):]]
            s.need(type(expected) is str and ref['sha256'] == expected,
                   'actual effective source differs from the normal pair projection')
            files.append({'relative': relative, 'actual': ref, 'snapshot': s.file_ref(copy)})
        s.need(s.file_ref(WORK / 'source-projection.json', 128 * 1024**2) == journal, 'projection changed during observation')
        for file in files:
            s.need(s.file_ref(file['actual']['path'], 2 * 1024**2) == file['actual'], 'effective source changed during observation')
        after = s.process_identity(before['pid'])
        s.need(command_witness.validate_executed_command(row['driver'], after, expected_argv,
               executable_ref['path']) == generation, 'driver generation changed during input observation')
        executable.verify_running(before['pid'])
        environment_after = command_witness.validate_temporary_environment(
            (Path('/proc') / str(after['pid']) / 'environ').read_bytes(), str(TEMPORARY))
        s.need(environment_before == environment_after, 'actual driver temporary environment changed')
        s.need(row['lifecycle']['pidfd_closed'] is False, 'owned child PIDFD must remain held')
        s.need(s.file_ref(normal_ref['path'], 8 * 1024**2) == normal_ref,
               'normal pair input record changed during source observation')
        result = {'schema': 'pocket4-native600-effective-pair-input-observation-v1',
                  'state': 'OBSERVED_NOT_COMPILED_QUALIFIED', 'build_host': 'ai395',
                  'host_generation_inherited': False, 'begun_ns': begun_ns, 'finished_ns': time.time_ns(),
                  'driver': before, 'driver_initial_observation': row['driver'],
                  'driver_final_observation': after, 'stable_driver_generation': generation,
                  'driver_temporary_environment_before': environment_before,
                  'driver_temporary_environment_after': environment_after,
                  'actual_command_argv': expected_argv, 'pinned_executable': executable.record(),
                  'outer_admission': outer_ref, 'actual_build_processes': processes,
                  'resource_profile': s.PROFILE, 'source_manifest': s.file_ref(SOURCE / '.droidloom-source-manifest.json'),
                  'source_projection': journal, 'source_projection_copy': s.file_ref(path / 'source-projection.original.json'),
                  'normal_pair_inputs': normal_ref, 'required_compile_sources': pair.REQUIRED_COMPILE_SOURCES,
                  'source_files': files, 'observed_work_locks': lock_rows, 'work_locks_acquired': 0,
                  'source_mutations': 0, 'complete_translation_unit_qualification': False, 'artifact_qualified': False,
                  'runtime_qualified': False}
        return s.create(path / 'result.json', result)

def completion_gate():
    records = {}; documents = []
    for name in ('attempt', 'inputs', 'command'):
        document, ref = s.read_json(OUT / ('droidloom-native-generation-build-' + name + '.json'))
        records[name] = ref; documents.append(document)
    contract = pair.validate_records(*documents)
    s.need(not (WORK / 'source-projection.json').exists()
           and not (WORK / 'source-projection.json').is_symlink(), 'normal pair source journal remains')
    product = OUT / 'target/product/droidloom_x86_64'
    actual, pair_ref = s.read_json(product / 'droidloom-native-generation-pair.json', 65536)
    s.need(actual == contract, 'actual product pair contract differs')
    engine, raw = s.file_ref(product / 'system/lib64/libberberis_arm64.so', 64 * 1024**2, contents=True)
    apex = s.file_ref(product / 'system/apex/com.android.art.apex', 512 * 1024**2)
    s.need(engine['sha256'] == contract['engine_sha256'] and apex['sha256'] == contract['art_apex_sha256'],
           'actual complete engine or whole ART APEX differs')
    marker_offsets = pair.pair_engine_marker(raw)
    return {'state': 'ORDINARY_PAIR_COMMAND_COMPLETED_ARTIFACT_QUALIFICATION_PENDING',
            'normal_records': records, 'pair': contract, 'actual_product_pair': pair_ref,
            'engine': engine, 'whole_ART_APEX': apex, 'engine_marker_offsets': marker_offsets,
            'published_projects': 600, 'published_root_links': 8,
            'targets': pair.TARGETS, 'dependency_mode': 'Strict', 'source_projection_restored': True,
            'full_translation_unit_qualification_verified': False,
            'signature_and_payload_verification_complete': False,
            'private_AppZygote_role_authorized': False, 'installation_performed': False,
            'runtime_authorization_enabled': False, 'latest_QPR1_cohort_qualified': False}


def run_build(config):
    result = {'schema': 'pocket4-native600-ai395-normal-full-build-v1', 'state': 'STARTED',
              'build_host': 'ai395', 'host_generation_inherited': False, 'source_origin_host': 'pocket4',
              'source_project_count': 600, 'resource_profile': s.PROFILE, 'started_ns': time.time_ns(),
              'build_success': False, 'complete_engine_ART_pair_qualified': False, 'runtime_qualified': False,
              'source_projection_restored': False, 'input_after_qualified': False,
              'owned_retirement_complete': False, 'errors': [], 'commands': []}
    RESULT.mkdir(mode=0o700)
    s.create(RESULT / 'STARTED.json', result)
    serial = None; commands = None; cgroup = None; heavy_started = False; locks = None
    try:
        s.need(os.getuid() == os.geteuid() == 1000, 'normal source build must run as the ai395 owner')
        s.validate_profile(config['resource_profile'])
        cgroup = s.self_cgroup(); s.need(cgroup == Path('/sys/fs/cgroup/system.slice') / UNIT, 'fresh fixed inner cgroup differs')
        result['budget_before'] = s.budget_snapshot(cgroup, inner=True)
        events_before = s.event_counts(result['budget_before']['memory.events'])
        s.need(all(events_before.get(key) == 0 for key in ('oom', 'oom_kill', 'oom_group_kill')), 'fresh build cgroup already has OOM events')
        serial, result['shared_serial_lock'] = s.serial_lock()
        result['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        outer, outer_ref = s.read_json(CONTROL / 'outer-execution.json')
        result['outer_admission'] = outer_ref; result['outer_job_id'] = outer['outer_job_id']
        s.need(outer['resource_profile'] == s.PROFILE and outer['full_unit'] == UNIT
               and outer['controller_source']['sha256'] == s.file_ref(__file__)['sha256'], 'actual new outer/controller binding differs')
        result['configuration'] = s.file_ref(CONTROL / 'build-inputs.json')
        s.need(result['configuration']['sha256'] == outer['configuration']['sha256'], 'actual launch configuration changed')
        transfer = json.loads(s.pinned(config['source_transfer_result'], contents=True)[1])
        s.need(transfer['schema'] == 'pocket4-native597-ai395-source-transfer-v1'
               and transfer['build_host'] == 'ai395' and transfer['source_host'] == 'desktop'
               and transfer['state'] == 'SOURCE_TRANSFERRED_AND_NORMAL_VERIFIED_ON_NEW_HOST'
               and transfer['source_materialization_verified_on_new_host'] is True
               and transfer['host_generation_inherited'] is False and transfer['errors'] == []
               and transfer['all_command_children_retired'] is True and transfer['builds_started'] == 0,
               'fresh ai395 source qualification is not complete')
        result['source_transfer'] = config['source_transfer_result']
        recipe_import = json.loads(s.pinned(config['new_recipe_tool_import'], contents=True)[1])
        s.need(recipe_import['schema'] == 'native600-ai395-normal-recipe-and-tools-import-v1'
               and recipe_import['state'] == 'NEW_NORMAL_NATIVE_RECIPE_AND_TOOLS_VERIFIED_ON_AI395'
               and recipe_import['build_host'] == 'ai395' and recipe_import['origin_host'] == 'pocket4'
               and recipe_import['host_generation_inherited'] is False
               and recipe_import['AOSP_full_builds_started'] == 0 and recipe_import['new_loader_verified'] is True
               and recipe_import['all_command_children_retired'] is True and recipe_import['errors'] == []
               and recipe_import['recipe_commit'] == config['recipe_commit']
               and recipe_import['recipe_tree'] == config['recipe_tree'], 'new real-host tested recipe import differs')
        result['new_recipe_tool_import'] = config['new_recipe_tool_import']
        source_H = {name: json.loads(s.pinned(ref, contents=True)[1])
                    for name, ref in config['source_transfer_H'].items()}
        guards = s.load_module(CONTROL / 'audio_continuation_control.py')
        expected_terminal = config['source_transfer_terminal']
        guards.validate_raw_exit(source_H['exit'], source_H['request'], source_H['started'],
            expected_exit_code=0, expected_at_unix_ms=expected_terminal['at_unix_ms'],
            expected_stream_bytes=expected_terminal['stream_bytes'])
        import_H = {name: json.loads(s.pinned(ref, contents=True)[1])
                    for name, ref in config['new_recipe_tool_import_H'].items()}
        import_terminal = config['new_recipe_tool_import_terminal']
        guards.validate_raw_exit(import_H['exit'], import_H['request'], import_H['started'],
            expected_exit_code=0, expected_at_unix_ms=import_terminal['at_unix_ms'],
            expected_stream_bytes=import_terminal['stream_bytes'])
        s.need(import_H['exit']['job_id'] == '1a1be5f73cd-5e21-7f',
               'new recipe and tools belong to another actual import generation')
        result['normal_source_extension'] = source_extension_qualification(config)
        s.need(not OUT.exists() and not (WORK / 'source-projection.json').exists(), 'new generation requires a fresh OUT and restored source')
        locks = s.work_lock_probe(WORK, config['work_locks']); result['work_locks_before'] = locks
        s.need(WORK.is_dir() and not WORK.is_symlink() and WORK.stat().st_uid == 1000,
               'temporary compiler files require the owned work directory')
        TEMPORARY.mkdir(mode=0o700)
        temporary_stat = TEMPORARY.lstat()
        s.need(stat.S_ISDIR(temporary_stat.st_mode) and temporary_stat.st_uid == 1000
               and stat.S_IMODE(temporary_stat.st_mode) == 0o700
               and temporary_stat.st_dev == WORK.stat().st_dev,
               'temporary compiler files must stay on the owned AI395 work volume')
        result['temporary_directory'] = {'path': str(TEMPORARY),
            'device': temporary_stat.st_dev, 'inode': temporary_stat.st_ino,
            'included_in_owned_96_GiB_work_budget': True}
        commands = s.OwnedCommands(RESULT / 'commands', CONTROL)
        result['commands'] = commands.records
        result['materialized_manifest_before'] = source_qualification(commands, 'before', config)
        result['ART_source_preimages'] = art_preimages()
        s.pinned(config['go_probe'])
        probe = commands.run('actual-eight-cpu-go-probe', [config['go_probe']['path']], 30, env=environment())
        facts = json.loads(small_stdout(probe)); result['go_probe'] = facts
        for name, value in (('NumCPU', 8), ('GOMAXPROCS', 2), ('GOMEMLIMIT', 5 * s.GIB), ('GOGC', 50)):
            s.need(type(facts[name]) is int and facts[name] == value, 'actual Go visibility differs: ' + name)
        s.need(facts['GODEBUG'] == 'gctrace=1' and 'Cpus_allowed_list:\t8-15\n' in facts['proc_status'], 'actual Go affinity/diagnostic differs')
        s.need(facts['GoVersion'] == config['go_runtime_version'], 'probe uses another source-bound Go runtime')
        s.need(facts['TMPDIR'] == facts['GOTMPDIR'] == facts['TempDir'] == str(TEMPORARY),
               'actual Go temporary files escape the owned work volume')
        s.need(b'gc 1 @' in s.pinned(probe['stderr'], 1024**2, contents=True)[1], 'fresh Go GC diagnostic missing')
        s.need(s.file_ref(config['go_probe']['path'])['sha256'] == config['go_probe']['sha256'], 'fresh probe binary changed')
        result['work_locks_prelaunch'] = s.work_lock_probe(WORK, locks)
        allocation = commands.run('owned-work-allocation-before', ['/usr/bin/du', '-sx', '--block-size=1', str(ROOT), str(OUTPUT_ROOT)],
                                  60, env=environment())
        result['owned_allocation_before_bytes'] = sum(int(line.split()[0]) for line in small_stdout(allocation).splitlines())
        result['admission'] = s.admission(ROOT)
        result['argv'] = [str(TOOLS / 'droidloom-update'), '--source', str(RECIPE), '--jobs', '6', 'native-generation-build', '--work', str(WORK), '--out', str(OUT)]
        normal_executables = [ref for ref in config['normal_tools']
                              if ref['path'] == str(TOOLS / 'droidloom-update')]
        s.need(len(normal_executables) == 1, 'one exact normal executable pin required')
        normal_executable_ref = normal_executables[0]
        result['normal_targets'] = pair.TARGETS
        result['strict_allow_missing_dependencies'] = False
        result['state'] = 'RUNNING'; s.create(RESULT / 'admission.json', result)
        observed = {'next_sample': 0, 'next_space_check': 0, 'next_usage_check': 0,
                    'source_input_observation': None, 'samples': [], 'seen': set(), 'work_growth_peak_bytes': 0, 'soong_generations': {}}

        def monitor(row):
            now = time.monotonic()
            if now >= observed['next_space_check']:
                observed['next_space_check'] = now + 5
                s.need(s.disk_free(ROOT) >= s.PROFILE['shared_disk_reserve_bytes'], 'shared disk reserve reached; retiring only this build')
                s.need(s.memavailable() >= s.PROFILE['host_reserve_bytes'], 'shared host memory reserve reached; retiring only this build')
            if now < observed['next_sample']:
                return
            observed['next_sample'] = now + 2
            if 'driver' not in result:
                result['driver'] = row['driver']; s.create(RESULT / 'running.json', result)
            processes = []
            pids = (cgroup / 'cgroup.procs').read_text().split()
            s.need(len(pids) <= 512, 'bounded actual build cgroup process count exceeded')
            for token in pids:
                try:
                    proc = s.process_identity(int(token)); name = Path(proc['exe']).name
                    if name not in ('soong_ui', 'soong_build', 'ninja'):
                        continue
                    env = dict(x.split(b'=', 1) for x in (Path('/proc') / token / 'environ').read_bytes().split(b'\0') if b'=' in x)
                    proc['affinity'] = sorted(os.sched_getaffinity(int(token)))
                    proc['environment'] = {key: env.get(key.encode(), b'').decode() for key in
                                           ('ALLOW_MISSING_DEPENDENCIES', 'GOMEMLIMIT', 'GOMAXPROCS', 'GOGC', 'GODEBUG', 'NINJA_ARGS', 'TMPDIR', 'GOTMPDIR')}
                    s.need(proc['affinity'] == s.PROFILE['cpu_affinity'], 'actual build process affinity differs')
                    if name in ('soong_ui', 'soong_build'):
                        s.need(all(proc['environment'][key] == value for key, value in
                                   (('GOMEMLIMIT', '5GiB'), ('GOMAXPROCS', '2'), ('GOGC', '50'), ('GODEBUG', 'gctrace=1'))),
                               'actual Soong internal resource projection differs')
                        s.need(proc['environment']['ALLOW_MISSING_DEPENDENCIES'] in ('false', ''), 'relaxed missing dependencies are forbidden')
                    if name == 'soong_build':
                        observed['soong_generations'][(proc['pid'], proc['start_ticks'])] = proc
                    observed['seen'].add(name); processes.append(proc)
                except (FileNotFoundError, ProcessLookupError):
                    continue
            if processes and observed['source_input_observation'] is None and (WORK / 'source-projection.json').exists():
                observed['source_input_observation'] = snapshot_effective(row, processes, locks, outer_ref,
                    result['argv'], normal_executable_ref)
                print(json.dumps({'state': 'EFFECTIVE_NATIVE_PAIR_INPUTS_OBSERVED', 'result': observed['source_input_observation']}), flush=True)
            if processes and (not observed['samples'] or now >= observed.get('next_record', 0)):
                observed['next_record'] = now + 30
                sample = {'observed_ns': time.time_ns(), 'processes': processes,
                          'resources': {key: (cgroup / key).read_text().strip() for key in
                                        ('memory.max', 'memory.high', 'memory.current', 'memory.peak',
                                         'memory.events', 'memory.stat', 'memory.swap.current')},
                          'disk_free_bytes': s.disk_free(ROOT)}
                observed['samples'].append(s.create(RESULT / ('resource-%04d.json' % len(observed['samples'])), sample))
            if now >= observed['next_usage_check'] and OUT.exists():
                observed['next_usage_check'] = now + 60
                run = subprocess.run(['/usr/bin/du', '-sx', '--block-size=1', str(ROOT), str(OUTPUT_ROOT)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                s.need(run.returncode == 0, 'owned output allocation observation failed')
                allocated = sum(int(line.split()[0]) for line in run.stdout.splitlines()) - result['owned_allocation_before_bytes']
                observed['work_growth_peak_bytes'] = max(observed['work_growth_peak_bytes'], allocated)
                s.need(allocated < s.PROFILE['initial_build_work_budget_bytes'], 'owned 96 GiB incremental work/output budget reached')

        heavy_started = True
        try:
            result['normal_build'] = commands.run('normal-full-native-engine-ART-pair', result['argv'], 21600,
                                                  cwd=RECIPE, env=environment(), monitor=monitor)
        finally:
            result['effective_source_input_observation'] = observed['source_input_observation']
            result['resource_observations'] = observed['samples']
            result['actual_build_processes_seen'] = sorted(observed['seen'])
            result['observed_work_growth_peak_bytes'] = observed['work_growth_peak_bytes']
        s.need(result['effective_source_input_observation'] is not None and 'ninja' in observed['seen'],
               'successful full build lacks its actual source/compile window')
        metrics = s.load_module(CONTROL / 'go_runtime_budget.py')
        refs = [(name, result['normal_build'][name]) for name in ('stdout', 'stderr')]
        with contextlib.ExitStack() as logs:
            streams = []
            for name, reference in refs:
                s.pinned(reference, 256 * 1024**2)
                fd = os.open(reference['path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                stream = logs.enter_context(os.fdopen(fd, 'rb'))
                s.need(s.identity(os.fstat(stream.fileno())) == reference['identity'], 'normal log identity changed')
                streams.append((name, stream))
            actual = metrics.qualify_runtime_budget(streams,
                {row['pid'] for row in observed['soong_generations'].values()})
            for _, reference in refs:
                s.pinned(reference, 256 * 1024**2)
        actual['normal_build_logs'] = dict(refs)
        actual['actual_soong_process_generations'] = list(observed['soong_generations'].values())
        actual['runtime_observer_source'] = s.file_ref(CONTROL / 'go_runtime_budget.py')
        actual['source_patch'] = s.file_ref(RECIPE / 'android/apex-compat/0011-blueprint-ordinary-pair-go-budget.patch')
        result['actual_go_runtime_budget'] = s.create(RESULT / 'actual-go-runtime-budget.json', actual)

    except BaseException as error:
        result['errors'].append({'stage': 'execution', 'type': type(error).__name__, 'message': str(error)})
        result['traceback'] = traceback.format_exc()
    finally:
        retired = bool(commands is not None and all(row['owned_retirement_complete'] for row in commands.records))
        result['owned_retirement_complete'] = retired or not heavy_started
        if commands is not None and retired and serial is not None:
            try:
                if (WORK / 'source-projection.json').exists():
                    result['interrupted_projection'] = s.file_ref(WORK / 'source-projection.json', 128 * 1024**2)
                    commands.run('normal-source-recovery', [config['recovery_only_tool']['path'], 'recover-source', '--work', str(WORK)], 300, cwd=RECIPE, env=environment(), recovery=True)
                s.need(not (WORK / 'source-projection.json').exists(), 'source projection remains after owned retirement')
                result['source_projection_restored'] = True
                result['materialized_manifest_after'] = source_qualification(commands, 'after', config, recovery=True)
                if 'ART_source_preimages' in result:
                    s.need(art_preimages() == result['ART_source_preimages'], 'all ten original ART source states must be restored')
                result['work_locks_after'] = s.work_lock_probe(WORK, locks)
                result['input_after_qualified'] = True
            except BaseException as error:
                result['errors'].append({'stage': 'normal_restore_or_verify', 'type': type(error).__name__, 'message': str(error)})
        if commands is not None and result.get('owned_allocation_before_bytes') is not None:
            try:
                allocation = commands.run('owned-work-allocation-after',
                    ['/usr/bin/du', '-sx', '--block-size=1', str(ROOT), str(OUTPUT_ROOT)],
                    60, env=environment(), recovery=True)
                allocated = sum(int(line.split()[0]) for line in small_stdout(allocation).splitlines())
                growth = allocated - result['owned_allocation_before_bytes']
                result['owned_allocation_after_bytes'] = allocated
                result['owned_work_growth_after_bytes'] = growth
                result['disk_free_after_bytes'] = s.disk_free(ROOT)
                s.need(growth < s.PROFILE['initial_build_work_budget_bytes'],
                       'final owned work/output exceeds the actual new budget')
                s.need(result['disk_free_after_bytes'] >= s.PROFILE['shared_disk_reserve_bytes'],
                       'final common disk reserve was crossed')
                result['owned_allocation_after_verified'] = True
            except BaseException as error:
                result['errors'].append({'stage': 'final_owned_allocation',
                                         'type': type(error).__name__, 'message': str(error)})
        if cgroup is not None:
            try:
                result['budget_after'] = s.budget_snapshot(cgroup, inner=True)
                resources = s.validate_inner_resource_retirement(result['budget_before'], result['budget_after'])
                result['resource_events_delta'] = resources['events_delta']
                result['resource_memory_stat'] = {key: resources[key] for key in
                    ('memory_stat_before', 'memory_stat_after', 'reclaim_counters_delta', 'peak_tolerance_bytes')}
                result['resource_gate_passed'] = True
            except BaseException as error:
                result['resource_gate_passed'] = False
                result['errors'].append({'stage': 'resources', 'type': type(error).__name__, 'message': str(error)})
        if result.get('normal_build') and result['input_after_qualified']:
            try:
                result['normal_pair_completion'] = completion_gate()
            except BaseException as error:
                result['errors'].append({'stage': 'pair_completion', 'type': type(error).__name__, 'message': str(error)})
        result['signals'] = list(s.CANCELLED)
        if commands is not None:
            result['owned_retirement_complete'] = all(row['owned_retirement_complete'] for row in commands.records)
        result['build_success'] = bool(heavy_started and result.get('normal_build') and result.get('normal_pair_completion')
            and result['owned_retirement_complete'] and result['input_after_qualified']
            and result.get('resource_gate_passed') and result.get('effective_source_input_observation')
            and result.get('actual_go_runtime_budget') and result.get('owned_allocation_after_verified')
            and not result['errors'] and not s.CANCELLED)
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        pending = signal.sigpending() & {signal.SIGTERM, signal.SIGINT}
        if pending:
            result['pending_signals_at_commit'] = sorted(pending); result['build_success'] = False
        result['state'] = 'ORDINARY_PAIR_COMMAND_COMPLETED_ARTIFACT_QUALIFICATION_PENDING' if result['build_success'] else 'FAILED'
        result['finished_ns'] = time.time_ns(); result['shared_lock_held_through_restore'] = serial is not None
        reference = s.create(RESULT / 'terminal.json', result)
        if serial is not None:
            os.close(serial)
        print(json.dumps({'state': result['state'], 'terminal': reference, 'build_success': result['build_success'],
                          'owned_retirement_complete': result['owned_retirement_complete'],
                          'input_after_qualified': result['input_after_qualified'], 'errors': result['errors']}), flush=True)
    return 0 if result['build_success'] else 1


if __name__ == '__main__':
    s.install_signals()
    config, _ = s.read_json(CONTROL / 'build-inputs.json')
    progress = os.open(CONTROL / 'inner-progress.jsonl',
                       os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(progress, 'w', buffering=1) as stream:
        with contextlib.redirect_stdout(stream):
            status = run_build(config)
        stream.flush()
        os.fsync(stream.fileno())
    raise SystemExit(status)
