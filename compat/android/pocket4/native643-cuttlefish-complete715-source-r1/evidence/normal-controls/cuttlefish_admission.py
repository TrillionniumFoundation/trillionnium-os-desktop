"""Admit the exact complete original hotplug compiler and unchanged source epoch."""
import fcntl, importlib.util, os, sys
from pathlib import Path
C = Path(__file__).resolve().parent
B, R = C.parent, C.parent / 'recipe'
COMMIT, TREE = '3450f2591faec153dbab06477d0a00e95120321f', 'af2c7788ca297e8cf499a4f18a0aa3d278d3b419'
BOOT = 'b1620269-aaef-43e7-bf47-bc6eb1c1a447'
PREPARATION = {'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/tools-build-cuttlefish643-20261113-takeover-r1/control/code-preparation.json', 'bytes': 911685, 'sha256': 'e94b8f9df29f839b1a03d60563be1abc566f9753b020402d11a6192c8cfab5d1'}
NORMAL974 = {'path': '/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/tools-build-global-compat643-20261113-takeover-r1/qualification/result.json', 'bytes': 189013, 'sha256': '0ef4d7f1f9b6b95909be5d8e382424f7c5f403e06dc60a8cc59509714a7c70d6'}


def module(name):
    spec = importlib.util.spec_from_file_location('cuttlefish_' + name.removesuffix('.py'), C / name)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


legacy = module('legacy_source604_admission.py')
need = legacy.need
source = module('restored9fe_admission.py')
source.configure(legacy.HeldReader, need, legacy.identity, legacy.reference, legacy.joint_original_locks)


def frozen(reader, root, refs, count):
    seen = set()
    need(len(refs) == count, 'complete exact recipe membership')
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(directory) == root and d == '.git')]
        need('.git' not in dirs and all(not (Path(directory) / d).is_symlink() for d in dirs), 'no nested repository or recipe directory alias')
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            need(relative in refs and relative not in seen and refs[relative]['path'] == str(path), 'exact frozen recipe path')
            reader.pinned(refs[relative], 16 * 1024**2)
            seen.add(relative)
    need(seen == set(refs), 'all frozen recipe files present')


def prep():
    reader = legacy.HeldReader(480)
    p = reader.document(PREPARATION)
    need(p['schema'] == 'native643-cuttlefish-hotplug-isolated-code-preparation-v1'
         and p['state'] == 'PREPARED_SOURCE_CODE_NOT_NORMAL_QUALIFIED'
         and p['recipe_path'] == str(R) and p['recipe_commit'] == COMMIT and p['recipe_tree'] == TREE
         and p['shared_source_writes'] == p['normal_builds_started'] == p['full_builds_started'] == 0
         and p['runtime_qualified'] is False, 'exact private hotplug source preparation')
    need(p['original_commit'] == '2f91fe5f81886ca24c4c562ce9491f16e17261d5'
         and p['original_tree'] == 'd30800eda1b2be36ac636913171195551cfefd38'
         and p['source_lock']['bytes'] == 369279 and p['source_lock']['sha256'] == 'e4bc640833bbdee16a1e84bd8314cc81c44351e4b03c03e6439bc31318d0a5bf', 'exact same643 one-cone candidate')
    need(set(p['changed_existing_files']) == {'android/native-generation-pair/source-lock.json', 'tools/droidloom-update/src/native_generation_pair_build.rs', 'tools/droidloom-source/src/lib.rs'}
         and len(p['added_files']) == 68 and all(name.startswith('android/native-generation-pair/cuttlefish-graphics-fixtures/') for name in p['added_files']), 'only three existing files and68 exact provenance fixtures change')
    need(p['existing49_F9_unchanged'] is p['unmaterialized14_still_absent'] is True, 'actual finite existing graphics/provider originals preserved')
    for command in p['commands']:
        life = command['lifecycle']
        need(life['returncode'] == 0 and life['actual_parent_reaped'] and life['pidfd_exit_observed'] and life['retirement_known'] and not life['timed_out'] and not life['forced_termination'] and life['errors'] == [], 'all private preparation commands retired')
        for side in ('stdout', 'stderr'):
            reader.pinned(command[side], 2 * 1024**2)
    return p


def qualify(p, held):
    reader = legacy.HeldReader(480)
    need(p == prep() and len(held) == 3 and Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT, 'same private recipe and original three leases')
    contract = reader.document(p['restored9fe_contract'])
    for fd, row in zip(held, contract['current_locks']):
        need(legacy.identity(os.fstat(fd)) == row['identity'] == legacy.identity(Path(row['path']).lstat()), 'same actual restored9fe source lease epoch')
        reader.pinned(row)
    proof = source.qualify(contract, borrowed_locks={row['path']: fd for row, fd in zip(contract['current_locks'], held)})
    frozen(reader, Path(p['original_recipe_path']), p['original647_files'], 647)
    frozen(legacy.HeldReader(480), R, p['current715_files'], 715)
    need(set(p['current715_files']) == set(p['original647_files']) | set(p['added_files']), 'exact68 new fixture membership')
    for name, old in p['original647_files'].items():
        if name not in p['changed_existing_files']:
            need(all(old[k] == p['current715_files'][name][k] for k in ('bytes', 'sha256')), 'unrelated recipe bytes changed')
    for name, row in {**p['changed_existing_files'], **p['added_files']}.items():
        need(row == p['current715_files'][name], 'exact reviewed candidate differs')
        reader.pinned(row, 16 * 1024**2)
    reader.pinned(p['source_lock']); reader.pinned(p['patch'])
    packet = reader.document(p['original_provider_packet'])
    need(packet['new_files'] == 3 and packet['physical_bytes'] == 6021 and packet['complete_graphics_files'] == 57 and packet['project_commit'] == '283645aacf6cdb56cc31a9362f54d412dbc132a1', 'same exact complete original graphics/hotplug inputs')
    finite = reader.document(p['existing49_originals'])
    need(len(finite) == 49 and len({row['path'] for row in finite}) == 49, 'exact49 independent existing source original set')
    for row in finite:
        reader.pinned(row, 16 * 1024**2)
    for row in finite:
        fd = reader.open_absolute(row['path'])
        try:
            need(legacy.identity(os.fstat(fd)) == row['identity'] == legacy.identity(Path(row['path']).lstat()), 'finite existing graphics/provider F9 changed')
        finally:
            os.close(fd)
    for row in packet['complete_graphics_inventory']:
        if not row['previously_materialized']:
            need(not os.path.lexists(source.SOURCE / row['aosp_path']), 'unselected original graphics must remain absent before source transaction')
    return {'source9fe_H': '1a1d7215e1b-392-9fe', 'source30952_F9_unchanged': proof['source30952_F9_unchanged'], 'source161_current_originals_F9_unchanged': proof['source161_current_originals_F9_unchanged'], 'all643_current_indexes_F9_unchanged': proof['all643_current_indexes_F9_unchanged'], 'source_physical_bytes': 503404771, 'original647_F9_unchanged': True, 'current715_F9_unchanged': True, 'existing49_F9_unchanged': True, 'unmaterialized14_still_absent': True, 'frozen630_unchanged': True, 'frozen624_unchanged': True, 'complete_original_normal974': proof['actual_normal974'], 'same643_project_and_commit_selection': True, 'one_complete_original_hotplug_cone_three_files': True, 'source_writes': 0, 'full_starts': 0, 'runtime_qualified': False, 'recipe_commit': COMMIT, 'recipe_tree': TREE}


def begin():
    p = prep()
    contract = legacy.HeldReader(480).document(p['restored9fe_contract'])
    held = []
    try:
        for row in contract['current_locks']:
            fd = os.open(row['path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            held.append(fd)
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        return p, held, qualify(p, held)
    except BaseException:
        close(held)
        raise


def close(held):
    while held:
        os.close(held.pop())


def original_normal_toolchain():
    return legacy.HeldReader(480).document(NORMAL974)['toolchain']
