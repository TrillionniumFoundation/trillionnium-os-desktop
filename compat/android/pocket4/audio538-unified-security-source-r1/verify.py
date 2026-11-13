#!/usr/bin/env python3
"""Authenticate and replay the complete Audio538 unified Android-tool producer without Android."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

HERE = Path(__file__).resolve().parent
BASE_COMMIT = '9785ba83d9d37509e02462a0aa7c84d1c991006c'
BASE_TREE = 'c9e0b5771b9e2a169ca4236c5c379446e9592760'
HEAD_COMMIT = 'fbb235628023f5fb5d9e47064a6d2884d23534bc'
HEAD_TREE = '23c1a126efd8975156d219af22a2d858a4dd3b2b'
SOURCE_TESTS = {'exact_audio_libueventd538_source::audio_libueventd538_extends_actual537_only_with_one_same_sp_original_project'}
UPDATE_TESTS = {'android::tests::audio_libueventd538_whole_originals_reject_changed_missing_alias_link_or_exec_mode', 'android::tests::audio_libueventd538_keeps_real_rust_provider_test_examples_and_all_direct_dependencies', 'android::tests::audio_libueventd538_exact_original_project_and_cones_reject_pin_or_scope_drift'}
TESTS = SOURCE_TESTS | UPDATE_TESTS


def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def digest(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def object_id(kind, raw):
    return hashlib.sha1(kind.encode() + b' ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def safe(name):
    need(isinstance(name, str) and name and not name.startswith('/') and '\\' not in name
         and all(part not in ('', '.', '..', '.git') for part in name.split('/'))
         and all(ord(char) >= 32 and ord(char) != 127 for char in name), 'invalid exact relative path')
    return Path(name)


def regular(path, cap=64 * 1024 * 1024):
    path = Path(path).absolute()
    need(path.resolve() == path, 'input path contains an alias: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= cap,
             'bounded independent regular input required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(cap + 1)
        need(len(raw) == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()),
             'input changed during complete held read')
        return raw
    finally:
        os.close(fd)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique_pairs)


def check(path, expected):
    raw = regular(path)
    need(digest(raw) == {key: expected[key] for key in ('bytes', 'sha256')}, 'exact input differs: ' + str(path))
    if 'git_blob' in expected:
        need(object_id('blob', raw) == expected['git_blob'], 'Git blob identity differs: ' + str(path))
    return raw


def member_names(root, skip_root_git=False):
    root = Path(root).absolute()
    need(root.resolve() == root and stat.S_ISDIR(root.lstat().st_mode), 'canonical existing directory required')
    names, directories = set(), {'.': f9(root.lstat())}
    for directory, children, files in os.walk(root, followlinks=False):
        current = Path(directory)
        if current == root and skip_root_git and '.git' in children:
            git = current / '.git'
            need(stat.S_ISDIR(git.lstat().st_mode) and not git.is_symlink(), 'root Git metadata must be a directory')
            children.remove('.git')
        for name in children:
            path = current / name
            relative = path.relative_to(root).as_posix()
            safe(relative)
            need(stat.S_ISDIR(path.lstat().st_mode) and not path.is_symlink(), 'directory alias or special entry rejected')
            directories[relative] = f9(path.lstat())
        for name in files:
            relative = (current / name).relative_to(root).as_posix()
            safe(relative)
            need(relative not in names, 'duplicate physical member')
            names.add(relative)
    return names, directories


def validate_rows(rows, count):
    need(isinstance(rows, list) and len(rows) == count, 'complete source inventory required')
    result = {}
    for row in rows:
        need(set(row) == {'path', 'bytes', 'sha256', 'git_blob', 'mode'}, 'complete exact source row required')
        safe(row['path'])
        need(row['path'] not in result and row['mode'] in ('100644', '100755')
             and type(row['bytes']) is int and 0 <= row['bytes'] <= 64 * 1024 * 1024
             and re.fullmatch('[0-9a-f]{64}', row['sha256'])
             and re.fullmatch('[0-9a-f]{40}', row['git_blob']), 'unique bounded original file required')
        result[row['path']] = row
    return result


def tree_id(rows):
    root = {}
    for row in rows:
        parts = safe(row['path']).parts
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            need(isinstance(node, dict), 'source file/directory collision')
        need(parts[-1] not in node, 'duplicate source tree member')
        node[parts[-1]] = (row['mode'], row['git_blob'])

    def encode(node):
        entries = []
        for name, value in node.items():
            if isinstance(value, dict):
                mode, oid, sortname = '40000', encode(value), name.encode() + b'/'
            else:
                mode, oid = value
                sortname = name.encode()
            entries.append((sortname, mode.encode() + b' ' + name.encode() + b'\0' + bytes.fromhex(oid)))
        return object_id('tree', b''.join(body for _, body in sorted(entries)))
    return encode(root)


def source_snapshot(root, rows, expected_tree):
    root = Path(root).absolute()
    wanted = validate_rows(rows, len(rows))
    need(tree_id(rows) == expected_tree, 'complete declared root tree differs')
    names, directories = member_names(root, skip_root_git=True)
    expected_dirs = {'.'} | {str(parent) for name in wanted for parent in Path(name).parents if str(parent) != '.'}
    need(names == set(wanted) and set(directories) == expected_dirs, 'complete producer file or directory membership changed')
    files = {}
    for name, row in sorted(wanted.items()):
        path = root / name
        before = f9(path.lstat())
        need(stat.S_ISREG(before[2]) and stat.S_IMODE(before[2]) == (int(row['mode'], 8) & 0o777),
             'producer original regular mode differs: ' + name)
        check(path, row)
        need(f9(path.lstat()) == before, 'producer identity changed during verification')
        files[name] = before
    after_names, after_dirs = member_names(root, skip_root_git=True)
    need(names == after_names and directories == after_dirs, 'producer membership changed during full audit')
    need(all(f9((root / name).lstat()) == identity for name, identity in files.items()), 'producer F9 changed during full audit')
    return {'files': files, 'directories': directories, 'tree': expected_tree}


def fresh_destination(path, protected):
    path = Path(path).absolute()
    need(path.resolve() == path and not os.path.lexists(path), 'fresh destination without any parent alias required')
    for root in protected:
        root = Path(root).absolute()
        need(root.resolve() == root and not path.is_relative_to(root), 'destination must be outside every input and producer')
    return path


def verify_history(manifest):
    docs = {name: decode(check(HERE / safe(row['path']), row)) for name, row in manifest['evidence'].items()}
    ordinary, dma, retired = [docs[n] for n in ('ordinary-333.json', 'ordinary-334.json', 'independent-retirement.json')]
    need(ordinary['base_commit'] == BASE_COMMIT and ordinary['recipe_commit'] == HEAD_COMMIT
         and ordinary['recipe_tree'] == HEAD_TREE and ordinary['actual_distinct_tests_passed'] == 333
         and ordinary['all_1557_producer_files_preserved'] is True and ordinary['errors'] == [],
         'actual333 producer evidence differs')
    groups = ordinary['test_runs']
    wanted = {'original_erofs_repack': 1, 'release_queue_2': 2, 'source_43': 43,
              'source_bin_zero': 0, 'source_doc_zero': 0, 'updater_main_287': 287}
    need(set(groups) == set(wanted), 'all actual333 registered harness groups required')
    for name, count in wanted.items():
        row = groups[name]
        need(row['passed'] == len(row['names']) == len(set(row['names'])) == count
             and all(row[k] == 0 for k in ('failed', 'ignored', 'measured')),
             'actual333 complete successful harness required')
    need(UPDATE_TESTS <= set(groups['updater_main_287']['names']) and SOURCE_TESTS <= set(groups['source_43']['names']), 'four exact current source/update Rust tests required in actual host proof')
    need(dma['state'] == 'ALL334_REGISTERED_SOURCE_UPDATER_AND_INTEGRATION_TESTS_ACTUALLY_PASSED'
         and dma['actual_distinct_tests_passed'] == 334 and dma['all_registered_ignored_cases_actually_executed'] is True
         and dma['private_original_file_count'] == 103 and dma['private_original_files_unchanged'] is True
         and dma['source_commit'] == 'ce79bbee67b3e2ea7abb110e1415e9ceceaa6471'
         and dma['source_tree'] == '95c2eb6837a39a6ef62ae454c5d9767cf2066c53'
         and dma['errors'] == [], 'one additional original DMA harness required')
    actual = dma['actual_dma_layout']
    need(actual['names'] == ['dma_heap_video_planes_satisfy_gpu_and_android_layouts']
         and actual['passed'] == 1 and all(actual[k] == 0 for k in ('failed','ignored','measured','filtered')),
         'one actually executed DMA layout test required')
    for claim, name in ((dma['prior333_actual_proof'], 'ordinary-333.json'),
                        (retired['normal333'], 'ordinary-333.json'), (retired['dma334'], 'ordinary-334.json')):
        need(all(claim[k] == manifest['evidence'][name][k] for k in ('bytes','sha256')),
             'same original333/334 evidence chain required')
    need(retired['state'] == 'ACTUAL334_ALL_HARNESSES_RETIRED_AND_ALL1557_SOURCE_FILES_PRESERVED'
         and retired['actual_distinct_tests_passed'] == 334 and retired['all1557_original_recipe_files_unchanged'] is True
         and retired['errors'] == [] and len(retired['original_cgroups_absent']) == len(set(retired['original_cgroups_absent'])) == 3
         and len(retired['original_pids_fresh_ESRCH']) == len(set(retired['original_pids_fresh_ESRCH'])) == 58,
         'independent original56PID/three-cgroup retirement required')
    prior_pids = {command['pid'] for proof in (ordinary,dma) for command in proof['commands']}
    need(prior_pids <= set(retired['original_pids_fresh_ESRCH']), 'all original normal commands must be retired')
    for proof in (ordinary,dma,retired):
        need(proof['Android_builds'] == 0 and proof['runtime_qualified'] is False and proof['production_ready'] is False,
             'ordinary host evidence cannot grant Android/APEX/runtime credit')
        need(all(c['exit_code'] == 0 and c['original_pidfd_retired'] is True and not c.get('timed_out',False)
                 for c in proof['commands']), 'all original normal commands must succeed and retire')
    staged = docs['staging.json']
    need(staged['state'] == 'AUDIO538_UNIFIED_SECURITY_PRODUCER_STAGED_ORIGINAL1517_PRESERVED'
         and staged['base_commit'] == BASE_COMMIT and staged['base_tree'] == BASE_TREE
         and staged['recipe_commit'] == HEAD_COMMIT and staged['recipe_tree'] == HEAD_TREE
         and staged['all_1517_original_parent_source_files_preserved'] is True
         and staged['unchanged_parent_files'] == 1514 and staged['new_files'] == 40
         and staged['new_producer_files'] == 1557 and staged['all_commands_retired'] is True
         and staged['shared_AOSP_writes'] == staged['Android_builds'] == staged['APK_installs'] == 0
         and staged['errors'] == [], 'same exact two-changed/six-added private staging required')
    for name in ('staging-retirement.json','normal-retirement.json','dma-retirement.json'):
        proof = docs[name]
        need(proof['exit_code'] == 0 and proof['original_pidfd_retired'] is True and proof['cgroup_absent'] is True,
             'original staging/normal/DMA unit retirement required')
    tools = retired['independent_release_tools']
    expected = {'droidloom-update': (3382920,'e7c3a147964c7ea3a524b86a2823cbf18c9c841ce68b28cad4d6d84cbdfe8306'),
                'droidloom-source': (1489480,'188d92ec18f7121d97da363581a2a827676d8a0d9723eb526fde040650a8960b')}
    need(len(tools) == 2 and {Path(row['path']).name for row in tools} == set(expected), 'both actual independent release tools required')
    for row in tools:
        need((row['bytes'],row['sha256']) == expected[Path(row['path']).name]
             and stat.S_ISREG(row['identity'][2]) and stat.S_IMODE(row['identity'][2]) == 0o555
             and row['identity'][5] == 1, 'original single-link0555 actual release identity differs')
    return {'actual_host_tests':334,'original_PIDs_retired':58,'fresh_CI_tests':0,
            'official_Cpp_regression_executed':False,'APEX_built':False}


def verify_official_inputs(manifest):
    origin=manifest['official_origin']
    packet=decode(check(HERE/safe(origin['packet']['path']),origin['packet']))
    need(origin['packet']['bytes']==26753 and origin['packet']['sha256']=='1d5fb61f09ab69d12afe8916b27d77f5b69edd5422d78d36314b66b30c70f865',
         'complete actual captured upstream packet required')
    pin='43f41cd5506656e937d332d60cd725764dfca716'
    sp='28f0bbddc24d56c8ec5a8df5342ac7a292184039'
    project={'name':'platform/system/libueventd-rs','path':'system/libueventd-rs','commit':pin,'sparse_paths':['examples','src']}
    need(packet['schema']=='audio538-original-libueventd-complete-same-SP-provider-v1'and packet['project']==project
         and packet['superproject']==sp and packet['original_gitlink']=={'mode':'160000','name':'libueventd-rs','oid':pin}
         and packet['file_count']==21 and packet['selected_original_bytes']==84991,'one exact same-SP original project required')
    objects={}
    for name,row in packet['objects'].items():
        raw=check(HERE/'official/objects'/safe(name),row)
        need(object_id(row['type'],raw)==name==row['oid']and row['type']in('commit','tree','blob'),'complete raw Git object authentication failed')
        objects[name]=(row['type'],raw)
    def tree(name):
        kind,raw=objects[name];need(kind=='tree','actual raw Git tree required');out={};offset=0
        while offset<len(raw):
            end=raw.index(b'\0',offset);mode,leaf=raw[offset:end].decode().split(' ',1)
            need(leaf not in out and '/'not in leaf and leaf not in('.','..')and end+21<=len(raw),'canonical complete raw Git tree entry required')
            out[leaf]=(mode,raw[end+1:end+21].hex());offset=end+21
        need(offset==len(raw),'complete raw tree framing required');return out
    def commit_tree(name):
        kind,raw=objects[name];need(kind=='commit','raw original commit required')
        roots=[x[5:].decode()for x in raw.split(b'\n\n',1)[0].splitlines()if x.startswith(b'tree ')]
        need(len(roots)==1,'exact commit root required');return roots[0]
    need(commit_tree(sp)==packet['superproject_root_tree']and tree(packet['superproject_root_tree'])['system']==('40000',packet['superproject_system_tree'])
         and tree(packet['superproject_system_tree'])['libueventd-rs']==('160000',pin)
         and commit_tree(pin)==packet['project_root_tree']=='b0f3707ae77686bb7d363320fabe0175a4f13599',
         'original superproject root→system→gitlink→project commit linkage required')
    rows=[]
    def walk(name,prefix=''):
        for leaf,(mode,oid)in tree(name).items():
            relative=prefix+leaf
            if mode=='40000':walk(oid,relative+'/')
            else:
                need(mode=='100644'and objects[oid][0]=='blob','only exact original regular non-executable file required')
                rows.append({'relative':relative,'mode':mode,'git_blob':oid,**digest(objects[oid][1]),'source_path':'system/libueventd-rs/'+relative})
    walk(packet['project_root_tree'])
    need(sorted(rows,key=lambda r:r['relative'])==sorted(packet['files'],key=lambda r:r['relative'])
         and len(rows)==21 and sum(r['bytes']for r in rows)==84991,'entire declared original21 tree differs')
    for row in rows:
        raw=check(HERE/'source/tools/droidloom-update/tests/fixtures/audio-libueventd538-original'/safe(row['source_path']),row)
        need(raw==objects[row['git_blob']][1],'actual fixture must equal original upstream Git blob')
    old=decode(regular(HERE/'preimages/android/manifest/audio-bridge-source-lock.json'))
    new=decode(regular(HERE/'source/android/manifest/audio-bridge-source-lock.json'))
    need(len(old['projects'])==537 and len(new['projects'])==538 and old['projects']==new['projects'][:-1]
         and {k:new['projects'][-1][k]for k in project}==project and set(new['projects'][-1])==set(project)|{'purpose'}
         and new['projects'][-1]['purpose']=='Pinned same-superproject original Rust device-event provider and complete source/examples required by actual strict USB authorization service dependencies'
         and {k:v for k,v in old.items()if k!='projects'}=={k:v for k,v in new.items()if k!='projects'},
         'source538 may append only this original project without repinning any537 parent')
    need(regular(HERE/'source/tools/droidloom-source/tests/fixtures/audio-source537-before-libueventd.json')==regular(HERE/'preimages/android/manifest/audio-bridge-source-lock.json'),
         'historical537 fixture must be the entire exact prior lock')
    contract=decode(regular(HERE/'source/android/audio-bridge/libueventd538-originals.json'))
    need(contract['source_files']==packet['files']and len(contract['existing_provider_originals'])==16
         and contract['IntentResolver_and_AAC_security_fixes_retained'] is True,'all21 provider, consumer and16 original direct Rust provider fixtures required')
    prefix='/data/pocket4-audio-source316-offload-20261108-8b88-r1/work/aosp-source/'
    for row in contract['existing_provider_originals']:
        need(row['path'].startswith(prefix)and row['project']=='external/rust/android-crates-io'
             and row['commit']=='1f5e95cd6e996995023c9c0f7df0f15a8a43269e','same original Rust provider project required')
        path=row['path'][len(prefix):];raw=check(HERE/'source/tools/droidloom-update/tests/fixtures/audio-libueventd538-original'/safe(path),row)
        need(object_id('blob',raw)==row['git_blob'],'every fixed original direct Rust provider fixture Git identity required')
    need(contract['original_consumer']=='frameworks/native/services/usbauthservice/Android.bp','exact original USB consumer required')
    check(HERE/'source/tools/droidloom-update/tests/fixtures/audio-libueventd538-original'/safe(contract['original_consumer']),packet['original_consumer'])
    previous=decode(check(HERE/safe(manifest['previous_failed_full']['retirement']['path']),manifest['previous_failed_full']['retirement']))
    need(previous['state']=='ACTUAL_FULL9DB_RESTORED_ALL_OWNED_PROCESSES_AND_THREE_LEASES_RETIRED'
         and previous['actual_failure_preserved']and previous['all_three_original_EX_leases_released']
         and previous['all_actual_original_bytes_modes_nsmtime_and_absence_restored']and previous['original_build_success']is False,
         'actual failed9db must remain failed with genuine independent restoration')
    normal=decode(check(HERE/safe(manifest['previous_failed_full']['normal']['path']),manifest['previous_failed_full']['normal']))
    stdout=check(HERE/safe(manifest['previous_failed_full']['stdout']['path']),manifest['previous_failed_full']['stdout'])
    need(normal['lifecycle']['returncode']==1 and normal['owned_retirement_complete']and b'depends on undefined module "libueventd"'in stdout,
         'original libueventd business failure must remain raw evidence')
    need(all(normal['stdout'][k]==packet['original_business_error_stdout'][k]==manifest['previous_failed_full']['stdout'][k]for k in('bytes','sha256')),
         'actual failed normal stdout identity must match original capture')
    return {'original_superproject':sp,'original_project_commit':pin,'original_provider_files':21,'direct_Rust_provider_fixtures':16,
            'previous_full9db_failed':True,'new_Android_build_qualified':False,'runtime_qualified':False}


def verify_capsule(expected_inventory):
    index = regular(HERE / 'FILES.sha256')
    need(re.fullmatch('[0-9a-f]{64}', expected_inventory)
         and hashlib.sha256(index).hexdigest() == expected_inventory, 'externally pinned capsule inventory differs')
    expected = {}
    for line in index.decode().splitlines():
        sha, name = line.split('  ', 1)
        safe(name)
        need(re.fullmatch('[0-9a-f]{64}', sha) and name not in expected and name != 'FILES.sha256', 'unique inventory entry required')
        expected[name] = sha
    actual, _ = member_names(HERE)
    need(actual == set(expected) | {'FILES.sha256'}, 'capsule has missing or extra inputs')
    for name, sha in expected.items():
        need(hashlib.sha256(regular(HERE / name)).hexdigest() == sha, 'capsule member changed: ' + name)
    manifest = decode(regular(HERE / 'manifest.json'))
    need(manifest['schema'] == 'pocket4-audio538-unified-security-source-v1', 'complete current capsule schema required')
    catalogs = {}
    for label, commit, tree, count in (('base', BASE_COMMIT, BASE_TREE, 1517), ('head', HEAD_COMMIT, HEAD_TREE, 1557)):
        item = manifest[label]
        need((item['commit'], item['tree'], item['files']) == (commit, tree, count), 'fixed source generation required')
        raw = check(HERE / safe(item['raw_commit']['path']), item['raw_commit'])
        need(object_id('commit', raw) == commit and raw.splitlines()[0] == ('tree ' + tree).encode()
             and sum(line.startswith(b'tree ') for line in raw.split(b'\n\n', 1)[0].splitlines()) == 1,
             'original raw commit and root identity differ')
        if label == 'head':
            need(('parent ' + BASE_COMMIT).encode() in raw.split(b'\n\n', 1)[0].splitlines(), 'security head must retain exact AAC330 parent')
        rows = decode(check(HERE / safe(item['inventory']['path']), item['inventory']))
        catalogs[label] = validate_rows(rows, count)
        need(tree_id(rows) == tree, 'entire source membership does not authenticate to original root tree')
    changed = {name for name in set(catalogs['base']) | set(catalogs['head'])
               if catalogs['base'].get(name) != catalogs['head'].get(name)}
    rows = manifest['files']
    need(len(rows) == len({row['path'] for row in rows}) == len(changed) == 43
         and {row['path'] for row in rows} == changed and sum(row['pre'] is not None for row in rows) == 3,
         'exact three changed and40 added files required')
    for row in rows:
        need(row['mode'] == '100644', 'security delta cannot change executable modes')
        for label, side, directory in (('base', 'pre', 'preimages'), ('head', 'post', 'source')):
            original = catalogs[label].get(row['path'])
            if original is None:
                need(row[side] is None, 'new security source must have no preimage')
            else:
                need(row[side] == {key: original[key] for key in ('bytes', 'sha256', 'git_blob')}, 'delta contradicts whole-source inventory')
                check(HERE / directory / safe(row['path']), row[side])
    for name, row in manifest['unchanged_inputs'].items():
        need(catalogs['base'][name] == catalogs['head'][name] == row, 'Audio537 source boundary or Cargo lock changed')
    need(all(manifest[k] is False for k in ('APEX_built', 'APEX_installed', 'official_regression_executed', 'binary_semantic_fix_qualified', 'production_signing_qualified', 'production_ready', 'runtime_qualified')),
         'source capsule cannot grant Android or runtime credit')
    check(HERE / safe(manifest['patch']['path']), manifest['patch'])
    verify_history(manifest)
    verify_official_inputs(manifest)
    return manifest


def focused_test_log(text,expected=None):
    expected=TESTS if expected is None else expected
    need(type(expected)is set and expected and expected<=TESTS,'fixed nonempty exact current test set required')
    records,running,summaries=[],[],[]
    for line in text.splitlines():
        if line.startswith('test result:'):summaries.append(line)
        elif line.startswith('test '):
            match=re.fullmatch(r'test (\S+) \.\.\. (ok|FAILED|ignored)',line);need(match is not None,'malformed Rust test record');records.append(match.groups())
        elif line.startswith('running '):
            need(re.fullmatch(r'running \d+ tests?',line),'malformed Rust test count');running.append(line)
    count=len(expected)
    need(len(records)==count and {n for n,_ in records}==expected and all(v=='ok'for _,v in records),'every exact test must pass once with no extra record')
    need(len(running)==1 and re.fullmatch('running '+str(count)+' tests?',running[0])and len(summaries)==1 and re.fullmatch(
        r'test result: ok\. '+str(count)+r' passed; 0 failed; 0 ignored; 0 measured; \d+ filtered out; finished in [0-9]+(?:\.[0-9]+)?s',summaries[0]),
        'one complete successful Rust terminal without contradictory result required')
    return sorted(n for n,_ in records)


def catalog(manifest, label):
    item = manifest[label]['inventory']
    return decode(check(HERE / safe(item['path']), item))


def replay(manifest, output, parent_source):
    parent_source = Path(parent_source).absolute()
    output = fresh_destination(output, [HERE, parent_source])
    base, head = catalog(manifest, 'base'), catalog(manifest, 'head')
    before = source_snapshot(parent_source, base, BASE_TREE)
    shutil.copytree(parent_source, output,
                    ignore=lambda directory, names: ['.git'] if Path(directory) == parent_source else [])
    need(source_snapshot(parent_source, base, BASE_TREE) == before, 'AAC330 input F9 changed during complete copy')
    copied = source_snapshot(output, base, BASE_TREE)
    need(all(copied['files'][name][:2] != before['files'][name][:2] for name in before['files']), 'copied producer must have independent inodes')
    need(not os.path.lexists(output / '.git'), 'AAC330 root Git metadata must not be copied')
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null', GIT_OPTIONAL_LOCKS='0')
    commands = []

    def git(args):
        argv = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.filemode=true', '-c', 'core.autocrlf=false', *args]
        run = subprocess.run(argv, cwd=output, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=120, umask=0o022)
        commands.append({'argv': argv, 'exit_code': run.returncode, 'stdout': digest(run.stdout), 'stderr': digest(run.stderr)})
        need(run.returncode == 0, 'normal Git replay failed: ' + run.stderr.decode(errors='replace'))
        return run.stdout

    def prove(rows, expected_tree):
        source_snapshot(output, rows, expected_tree)
        git(['add', '--force', '--all'])
        observed = git(['write-tree']).decode().strip()
        need(observed == expected_tree, 'actual complete Git root tree differs')
        return observed

    git(['init', '--quiet', '--template='])
    trees = [prove(base, BASE_TREE)]
    patch = str(HERE / safe(manifest['patch']['path']))
    for args, rows, expected_tree in ((['--check'], None, None), ([], head, HEAD_TREE),
                                     (['--reverse', '--check'], None, None), (['--reverse'], base, BASE_TREE),
                                     (['--check'], None, None), ([], head, HEAD_TREE)):
        git(['apply', *args, patch])
        if rows is not None:
            trees.append(prove(rows, expected_tree))
    need(source_snapshot(parent_source, base, BASE_TREE) == before, 'all original AAC330 input F9 must remain unchanged after round trip')
    return {'output': str(output), 'base_files': 1517, 'head_files': 1557,
            'actual_Git_root_trees': trees, 'git_commands': commands, 'input_F9_preserved': True,
            'skipped_only_root_git': True, 'private_Git_reconstructed': True, 'Git_child_umask': '0022',
            'full_forward_reverse_forward_replay': True, 'Rust_tests_run': False}


def write_report(path, value, protected):
    path = fresh_destination(path, protected)
    path.parent.mkdir(parents=True, exist_ok=True)
    need(path.parent.resolve() == path.parent, 'report parent became aliased')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--parent-source', type=Path)
    parser.add_argument('--producer', type=Path)
    parser.add_argument('--tests-log', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    need((args.output is None) == (args.parent_source is None), 'full AAC330 input and fresh replay output must be supplied together')
    need(args.producer is None or args.output is None, 'producer post-check and fresh replay are separate operations')
    protected = [HERE] + [path.absolute() for path in (args.parent_source, args.output, args.producer, args.tests_log) if path is not None]
    if args.report is not None:
        fresh_destination(args.report, protected)
    manifest = verify_capsule(args.inventory_sha256)
    result = {'state': 'EXACT_AUDIO538_UNIFIED334_COMPLETE_SOURCE_CAPSULE_VERIFIED', 'changed_source_files': 43,
              'historical_actual_host_tests': 334, 'fresh_CI_tests': 0,
              'production_ready': False, 'runtime_qualified': False, 'Android_builds_started': 0}
    if args.output is not None:
        result['replay'] = replay(manifest, args.output, args.parent_source)
    if args.producer is not None:
        snapshot = source_snapshot(args.producer, catalog(manifest, 'head'), HEAD_TREE)
        result['producer'] = {'path': str(args.producer.absolute()), 'file_count': len(snapshot['files']),
                              'root_tree': snapshot['tree'], 'all_bytes_Git_blobs_modes_members_verified': True}
    if args.tests_log is not None:
        raw = regular(args.tests_log)
        result['actual_focused_tests_passed'] = focused_test_log(raw.decode())
        result['observed_focused_test_records'] = 4
        result['test_log'] = digest(raw)
    if args.report is not None:
        write_report(args.report, result, protected)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
