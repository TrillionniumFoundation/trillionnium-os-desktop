#!/usr/bin/env python3
"""Authenticate both full original roots and replay the exact unified1595 D7 producer."""
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
AUDIO_COMMIT = 'fbb235628023f5fb5d9e47064a6d2884d23534bc'
AUDIO_TREE = '23c1a126efd8975156d219af22a2d858a4dd3b2b'
RUNTIME_COMMIT = '7d86a66b8d95477781519cec99e53fd0e76b6f36'
RUNTIME_TREE = '224fdc48b1083044cdce30a09ee4ec995a48c12d'
HEAD_COMMIT = '273d1a2b554923b7b53e645560ddbe5999cbde9b'
HEAD_TREE = 'cde7467f68d2de89f688431cafd494fed147e247'


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


def successful_cargo_stream(raw):
    rows=[decode(line) for line in raw.decode().splitlines() if line]
    terminals=[row for row in rows if row.get('reason')=='build-finished']
    need(rows and terminals==[{'reason':'build-finished','success':True}] and rows[-1]==terminals[0],
         'one complete successful Cargo terminal required')
    need(not any(row.get('reason')=='compiler-message' and row.get('message',{}).get('level')=='error' for row in rows),
         'successful Cargo stream contains an error')
    return rows


def test_terminal(text, passed, ignored=(), filtered=None):
    passed,ignored=set(passed),set(ignored)
    need(not passed.intersection(ignored),'passed and ignored identities must be distinct')
    records=[];running=[];summaries=[]
    for line in text.splitlines():
        if line.startswith('test result:'):
            summaries.append(line)
        elif line.startswith('test '):
            match=re.fullmatch(r'test (\S+) \.\.\. (ok|FAILED|ignored)(?:, (.+))?',line)
            need(match is not None,'malformed Rust test record')
            name,status,reason=match.groups()
            need(reason is None or status=='ignored','unexpected test reason')
            records.append((name,status))
        elif line.startswith('running '):
            need(re.fullmatch(r'running \d+ tests?',line),'malformed Rust running count')
            running.append(line)
    total=len(passed)+len(ignored)
    need(len(records)==total and len({name for name,status in records})==total and
         {name for name,status in records if status=='ok'}==passed and
         {name for name,status in records if status=='ignored'}==ignored and
         all(status in ('ok','ignored') for name,status in records),'complete exact Rust identities/statuses required')
    need(running==[f'running {total} '+('test' if total==1 else 'tests')] and len(summaries)==1,
         'exactly one complete Rust harness required')
    match=re.fullmatch(r'test result: ok\. (\d+) passed; 0 failed; (\d+) ignored; 0 measured; (\d+) filtered out; finished in [0-9]+(?:\.[0-9]+)?s',summaries[0])
    need(match is not None and int(match[1])==len(passed) and int(match[2])==len(ignored),
         'successful Rust summary must equal every actual record')
    need(filtered is None or int(match[3])==filtered,'unexpected Rust filter count')
    return {'passed':sorted(passed),'ignored':sorted(ignored),'filtered':int(match[3])}


def catalog(manifest,label):
    item=manifest[label]['inventory']
    return decode(check(HERE/safe(item['path']),item))


def test_catalog(manifest):
    item=manifest['test_catalog'];return decode(check(HERE/safe(item['path']),item))


def verify_history(manifest):
    evidence=manifest['evidence']
    need(len(evidence)==167,'all167 original runtime and tool qualification records required')
    raw={name:check(HERE/safe(row['path']),row) for name,row in evidence.items()}
    need(all(row['path']=='evidence/'+name for name,row in evidence.items()),'exact independent evidence namespace required')
    bindings={
        'runtime/normal/RESULT.json':(97958,'b7a18e0f8b37d855f95885ee53cf78b0a8c02446cb2713187e459dfd2a1318c3'),
        'runtime/independent/RESULT.json':(7360,'f64c29579d3c4b60a52201a8c8b6e9768119ce29f08e4b16cbdf9df24991ecdd'),
        'tools/normal/RESULT.json':(75557,'9b0c06c141bfbf4cee4ec765e6a3f437a2bfa7396c6b0276b90b8be4888bd0db'),
        'tools/dma/RESULT.json':(122995,'cb7147de2ad8a376f2136f241a63bd68af25bc51c56cac806eacdfa43553bac8'),
        'tools/independent/RESULT.json':(13227,'1a9c2d37e9d609ca5e6ced833ad96ce2f81917c074247075db6621fd085b50bc'),
        'tools/history/independent-r1-FAILED.json':(1579,'75d36de126429ce19adbab77ae97b09b50d52b88b7692c1577403d71592d7e64')}
    for name,(size,sha) in bindings.items():need(digest(raw[name])=={'bytes':size,'sha256':sha},'immutable original qualification differs: '+name)
    runtime=decode(raw['runtime/normal/RESULT.json']);rret=decode(raw['runtime/independent/RESULT.json'])
    tools=decode(raw['tools/normal/RESULT.json']);dma=decode(raw['tools/dma/RESULT.json']);tret=decode(raw['tools/independent/RESULT.json'])
    tc=test_catalog(manifest)
    need(runtime['head']==rret['head']==tools['recipe_commit']==tret['head']==HEAD_COMMIT and
         runtime['tree']==rret['tree']==tools['recipe_tree']==tret['tree']==HEAD_TREE,'all actual tests must use this exact unified producer')
    need(runtime['state']=='ALL_ORDINARY_RUNTIME_TESTS_AND_FOUR_FRESH_UNIFIED_RELEASE_BINARIES_PASSED' and not runtime['errors'] and
         rret['state']=='ALL289_ACTUAL_ORDINARY_TESTS_FOUR_FRESH_RELEASES_AND_ALL3152_SOURCE_FILES_INDEPENDENTLY_RETIRED' and not rret['errors'],
         'actual runtime qualification and complete independent retirement required')
    need(tools['state']=='D7_333_ACTUAL_TOOL_TESTS_AND_EXISTING_FOUR_RELEASES_PRESERVED_DMA_PENDING' and not tools['errors'] and
         dma['state']=='ALL334_REGISTERED_SOURCE_UPDATER_AND_INTEGRATION_TESTS_ACTUALLY_PASSED' and not dma['errors'] and
         tret['state']=='ALL334_D7_TOOL_TESTS_AND_1595_SOURCE_FOUR_RELEASES_INDEPENDENTLY_VERIFIED_AND_RETIRED' and not tret['errors'],
         '333 and actual DMA1 plus independent tool retirement required')
    need(runtime['actual_ordinary_tests_passed']==rret['actual_ordinary_tests_passed']==289 and
         tools['actual_distinct_tests_passed']==333 and dma['actual_distinct_tests_passed']==tret['actual_distinct_tool_tests_passed']==334,
         'actual host test totals differ')
    need(set(runtime['all_registered_supervisor_tests'])==set(tc['runtime_registered']) and
         set(runtime['actual_tests_passed'])==set(tc['runtime_ordinary']) and
         set(runtime['privileged_ignored_tests_not_qualified'])==set(tc['runtime_privileged_ignored']) and
         len(tc['runtime_registered'])==310 and len(tc['runtime_ordinary'])==289 and len(tc['runtime_privileged_ignored'])==21,
         'all ordinary and explicitly unqualified privileged identities required')
    commands={}
    for label,obj in [('runtime/normal',runtime),('tools/normal',tools),('tools/dma',dma)]:
        commands[label]={}
        for row in obj['commands']:
            need(row['name'] not in commands[label] and row['exit_code']==0 and row['timed_out'] is False and row['original_pidfd_retired'] is True,
                 'each actual original command must succeed and retire')
            commands[label][row['name']]=row
            for side in ('stdout','stderr'):
                need(digest(raw[label+'/'+row['name']+'.'+side])=={k:row[side][k] for k in ('bytes','sha256')},'whole actual command output differs')
    test_terminal(raw['runtime/normal/all-ordinary-supervisor-tests.stdout'].decode(),tc['runtime_ordinary'],tc['runtime_privileged_ignored'],0)
    tools_catalog=tc['tools334']
    for name,expected,filtered in [
        ('updater-main-287-including-network',set(tools_catalog['updater'])-{'image_policy::tests::repack_preserves_android_metadata_and_adbd'},1),
        ('original-erofs-metadata-repack',{'image_policy::tests::repack_preserves_android_metadata_and_adbd'},287),
        ('source-library-43',tools_catalog['source'],0),('source-bin-no-tests',[],0),
        ('release-queue-original-cpp-2',tools_catalog['release_queue'],0),('source-doc-tests',[],0)]:
        test_terminal(raw['tools/normal/'+name+'.stdout'].decode(),expected,filtered=filtered)
    test_terminal(raw['tools/dma/actual-original-dma-layout.stdout'].decode(),tools_catalog['dma_heap_layout'],filtered=0)
    need('native_bridge::tests::published_source_pin_fetches_and_verifies' in tools_catalog['updater'],'actual network test cannot be omitted')
    release=successful_cargo_stream(raw['runtime/normal/four-fresh-release-binaries.stdout'])
    names={'droidloom-source','droidloom-update','droidloomd','droidloom-supervisor'}
    artifacts=[x for x in release if x.get('reason')=='compiler-artifact' and x.get('executable') and x['target']['name'] in names]
    need(len(artifacts)==4 and {x['target']['name'] for x in artifacts}==names and all(x['fresh'] is False and x['profile']['test'] is False for x in artifacts),
         'four actual fresh unified release products required')
    compiled=successful_cargo_stream(raw['tools/normal/compile-all-harnesses.stdout'])
    actual=[x for x in compiled if x.get('reason')=='compiler-artifact' and x.get('executable') and x.get('profile',{}).get('test')]
    need(len(actual)==5 and all(x['fresh'] is False for x in actual),'five actual fresh tool harnesses required')
    bins=runtime['release_binaries']
    need(set(bins)==names and bins==rret['independent_single_link_0555_release_binaries']==tools['release_binaries_before']==dma['all_four_existing_release_binaries']==tret['four_original_0555_release_binaries'],
         'every later tool test must preserve the exact original four released binaries')
    for name,ref in bins.items():
        need(ref['identity'][5]==1 and stat.S_IMODE(ref['identity'][2])==0o555 and ref['bytes']>0 and re.fullmatch('[0-9a-f]{64}',ref['sha256']),
             'independent original0555 binary required')
        need(commands['runtime/normal']['normal-help-'+name]['argv']==[ref['path'],'--help'],'original four release CLI entries required')
    need(tools['release_binaries_rebuilt']==tools['runtime_tests_repeated']==dma['release_binaries_rebuilt']==dma['runtime_tests_repeated']==0,
         'later tool qualification must not invent a second runtime/release generation')
    need(tret['all1595_source_Git_blobs_modes_and_F9_preserved'] and tret['all_four_release_F9_preserved'] and
         tret['original103_fixture_Git_blobs_modes_and_F9_preserved'] and tret['producer_membership_only1595_plus_exact103_fixture'] and
         tret['complete_original_fixture_files']==103 and len(tret['fresh_original_PIDFD_ESRCH'])==43 and len(tret['original_cgroups_absent'])==6 and
         tret['all_original_OOM_events_zero'],'whole actual334 source/binary/fixture/retirement boundary required')
    need(dma['source_commit']==tret['fixture_commit']=='ce79bbee67b3e2ea7abb110e1415e9ceceaa6471' and
         dma['source_tree']==tret['fixture_tree']=='95c2eb6837a39a6ef62ae454c5d9767cf2066c53' and
         dma['private_original_file_count']==103 and dma['fixture_published_with_producer'] is False,
         'actual DMA requires exactly its isolated original source fixture')
    before_runtime=decode(raw['runtime/normal/SOURCE-BEFORE.json']);before_tools=decode(raw['tools/source/SOURCE-BEFORE.json'])
    wanted=validate_rows(catalog(manifest,'head'),1595)
    need(set(before_runtime)==set(wanted) and len(before_tools)==1595,'complete actual producer evidence required')
    for row in before_tools:
        name=row['relative'];original=before_runtime[name]
        need({k:row[k] for k in ('path','bytes','sha256','identity')}==original and
             all(row[k]==wanted[name][k] for k in ('bytes','sha256','git_blob')) and row['git_mode']==wanted[name]['mode'],
             'all1595 source identities must join both actual qualification epochs')
    for obj in (runtime,rret,tools,dma,tret):
        need(obj['runtime_qualified'] is obj['production_ready'] is False,'host ordinary tests cannot qualify actual Android/runtime')
        events=dict((k,int(v)) for k,v in map(str.split,obj['memory_events'].splitlines()))
        need(all(events.get(k)==0 for k in ('oom','oom_kill','oom_group_kill')),'original qualification encountered OOM')
    def h(prefix,jobid,nonce,digest_value,finished,counts):
        docs={name:decode(raw[prefix+'-'+name+'.json']) for name in ('request','started','exit')}
        need(all(x['job_id']==jobid and x['launch_nonce']==nonce for x in docs.values()) and docs['request']['request_digest']==digest_value,
             'original durable request identity differs')
        end=docs['exit'];need(end['exit_code']==0 and end['at_unix_ms']==finished and end['output_complete'] is end['output_durable'] is True and
             end['timed_out'] is end['cancelled'] is False,'complete original durable success required')
        for side,size in counts.items():need(end['log_bytes'][side]=={'seen':size,'stored':size} and end['log_errors'][side] is None and
             end['log_synced'][side] is True and end['log_truncated'][side] is False,'original durable stream is incomplete')
    h('runtime/durable/normal','1a1d74074e7-392-a34','150356723c7c3a41313cd4c440b13b1e','e76baf64d95593b5d255d1f1a414ec46ef8b702fc2dfe7dc8e7bc44c8456d2fe',1794612833463,{'stdout':2484,'stderr':299})
    h('tools/durable/normal','1a1d751a90e-392-a4e','668fe30dfe5a4c175ca0a29aed20d8fc','ba20755aecbfc7e85b7cef2503432db9b26867a39ab05ad0e80b9325841c1edc',1794613883510,{'stdout':3729,'stderr':297})
    h('tools/durable/dma','1a1d75411a8-392-a50','0bda6933aa8d5fae3bc36353e930b3ea','c1119cca3abb581bdd64b039e57fd33553e8a8bc7b17877c7516ab7f69718011',1794613978051,{'stdout':1568,'stderr':290})
    h('tools/durable/independent','1a1d75840a3-392-a55','296594c71f4fd098f041d94d57af5333','4951b9b71a4c7772b517a248540fe07b72f06a7d831b05671da14c63da8c962e',1794614254929,{'stdout':791,'stderr':0})
    failed=decode(raw['tools/history/independent-r1-FAILED.json'])
    need(failed['state']=='FAILED' and failed['errors'] and tret['prior_read_size_failure_preserved']['sha256']==bindings['tools/history/independent-r1-FAILED.json'][1],
         'the original bounded-reader failure must remain failed')


def verify_capsule(expected_inventory):
    index=regular(HERE/'FILES.sha256')
    need(re.fullmatch('[0-9a-f]{64}',expected_inventory) and hashlib.sha256(index).hexdigest()==expected_inventory,
         'externally pinned complete capsule inventory differs')
    expected={}
    for line in index.decode().splitlines():
        sha,name=line.split('  ',1);safe(name)
        need(re.fullmatch('[0-9a-f]{64}',sha) and name not in expected and name!='FILES.sha256','unique exact inventory required')
        expected[name]=sha
    actual,dirs=member_names(HERE);all_names=set(expected)|{'FILES.sha256'}
    expected_dirs={'.'}|{str(p) for name in all_names for p in Path(name).parents if str(p)!='.'}
    need(actual==all_names and set(dirs)==expected_dirs,'missing/extra capsule files or directories')
    for name,sha in expected.items():need(hashlib.sha256(regular(HERE/name)).hexdigest()==sha,'capsule member differs: '+name)
    manifest=decode(regular(HERE/'manifest.json'))
    need(manifest['schema']=='pocket4-runtime-d7-complete-unified1595-source-v1','complete D7 unified source capsule required')
    inventories={}
    for label,commit,tree,count in [('audio',AUDIO_COMMIT,AUDIO_TREE,1557),('runtime',RUNTIME_COMMIT,RUNTIME_TREE,430),('head',HEAD_COMMIT,HEAD_TREE,1595)]:
        item=manifest[label]
        need((item['commit'],item['tree'],item['files'])==(commit,tree,count),'fixed complete original source root required')
        raw=check(HERE/safe(item['raw_commit']['path']),item['raw_commit']);headers=raw.split(b'\n\n',1)[0].splitlines()
        need(object_id('commit',raw)==commit and headers[0]==('tree '+tree).encode() and sum(x.startswith(b'tree ') for x in headers)==1,
             'actual complete commit/tree authentication failed')
        if label=='head':need([x for x in headers if x.startswith(b'parent ')]==[('parent '+AUDIO_COMMIT).encode()],'D7 must retain the actual Audio538 Git parent')
        rows=catalog(manifest,label);inventories[label]=validate_rows(rows,count)
        need(tree_id(rows)==tree,'complete original root membership differs')
    a,d,n=[inventories[x] for x in ('audio','runtime','head')]
    selected=manifest['selected_runtime_paths']
    need(len(selected)==len(set(selected))==66 and set(selected)<=set(d),'exact66 runtime source selections required')
    expected_head=dict(a)
    for name in selected:expected_head[name]=d[name]
    need(expected_head==n,'current1595 must be the exact original two-root composition')
    changed={name for name in a if a[name]!=n[name]};added=set(n)-set(a)
    need(len(changed)==13 and len(added)==38 and len(set(a)-set(n))==0 and manifest['unchanged_audio_files']==1544 and
         set(manifest['changed_paths'])==changed and set(manifest['new_paths'])==added and
         len(manifest['files'])==51 and {row['path'] for row in manifest['files']}==changed|added,'exact13 modified/38 new/1544 retained boundary required')
    for row in manifest['files']:
        name=row['path'];need(row['mode']==n[name]['mode']=='100644','delta cannot invent an executable mode')
        need(row['post']=={k:n[name][k] for k in ('bytes','sha256')},'postimage contradicts complete root')
        check(HERE/'postimages'/safe(name),n[name])
        if name in changed:
            need(row['pre']=={k:a[name][k] for k in ('bytes','sha256')},'preimage contradicts complete root');check(HERE/'preimages'/safe(name),a[name])
        else:need(row['pre'] is None and not (HERE/'preimages'/name).exists(),'new source cannot have a fabricated preimage')
    need(all(n[name]==row for name,row in a.items() if name.startswith(('tools/droidloom-source/','tools/droidloom-update/','android/security/'))),
         'current538 tool source and both official security repairs must be retained')
    need(not any(name.startswith('.work/') for name in n),'private DMA fixture cannot enter the producer')
    check(HERE/safe(manifest['patch']['path']),manifest['patch'])
    original=decode(check(HERE/safe(manifest['original_candidate']['path']),manifest['original_candidate']))
    need(original['head']==HEAD_COMMIT and original['tree']==HEAD_TREE and original['parent']==AUDIO_COMMIT and
         original['selected_D6_paths']==selected,'original composition record must remain exact')
    for key in ('fresh_CI_tests_prequalified','runtime_qualified','production_ready','ExecutionAdmission_constructible','actual_SELinux_transition_qualified','private_minigbm_fixture_in_producer'):
        need(manifest[key] is False,'ordinary source evidence cannot grant execution or fresh CI credit')
    need(manifest['Android_builds']==manifest['Android_starts']==manifest['host_policy_writes']==0,'source publication cannot start Android')
    verify_history(manifest)
    return manifest


def replay(manifest,audio_source,runtime_source,output):
    audio_source,runtime_source=Path(audio_source).absolute(),Path(runtime_source).absolute()
    need(audio_source!=runtime_source and not audio_source.is_relative_to(runtime_source) and not runtime_source.is_relative_to(audio_source),
         'independent complete source roots required')
    output=fresh_destination(output,[HERE,audio_source,runtime_source])
    a,d,n=[catalog(manifest,label) for label in ('audio','runtime','head')]
    before_a=source_snapshot(audio_source,a,AUDIO_TREE);before_d=source_snapshot(runtime_source,d,RUNTIME_TREE)
    shutil.copytree(audio_source,output,ignore=lambda directory,names:['.git'] if Path(directory)==audio_source else [])
    copied=source_snapshot(output,a,AUDIO_TREE)
    need(all(copied['files'][name][:2]!=before_a['files'][name][:2] for name in before_a['files']),'independent copied source inodes required')
    env={key:value for key,value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_SYSTEM='/dev/null',GIT_OPTIONAL_LOCKS='0')
    commands=[]
    def git(args):
        argv=['git','-c','core.hooksPath=/dev/null','-c','core.filemode=true','-c','core.autocrlf=false',*args]
        run=subprocess.run(argv,cwd=output,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,umask=0o022)
        commands.append({'argv':argv,'exit_code':run.returncode,'stdout':digest(run.stdout),'stderr':digest(run.stderr)})
        need(run.returncode==0,'actual Git replay failed: '+run.stderr.decode(errors='replace'));return run.stdout
    def prove(rows,tree):
        source_snapshot(output,rows,tree);git(['add','--force','--all'])
        need(git(['write-tree']).decode().strip()==tree,'actual whole source Git root differs');return tree
    git(['init','--quiet','--template=']);trees=[prove(a,AUDIO_TREE)]
    raw=HERE/safe(manifest['audio']['raw_commit']['path'])
    need(git(['hash-object','-w','-t','commit',str(raw)]).decode().strip()==AUDIO_COMMIT,'original Audio commit object differs')
    patch=str(HERE/safe(manifest['patch']['path']))
    for args,rows,tree in [(['--check'],None,None),([],n,HEAD_TREE),(['--reverse','--check'],None,None),(['--reverse'],a,AUDIO_TREE),(['--check'],None,None),([],n,HEAD_TREE)]:
        git(['apply',*args,patch])
        if rows is not None:trees.append(prove(rows,tree))
    raw=HERE/safe(manifest['head']['raw_commit']['path'])
    need(git(['hash-object','-w','-t','commit',str(raw)]).decode().strip()==HEAD_COMMIT,'original D7 commit object differs')
    git(['update-ref','refs/heads/replay-d7-unified538',HEAD_COMMIT]);git(['symbolic-ref','HEAD','refs/heads/replay-d7-unified538'])
    need(not git(['status','--porcelain']),'complete current replay must be clean')
    need(source_snapshot(audio_source,a,AUDIO_TREE)==before_a and source_snapshot(runtime_source,d,RUNTIME_TREE)==before_d,
         'both complete original source roots must retain every byte/mode/F9')
    final=source_snapshot(output,n,HEAD_TREE)
    return {'output':str(output),'audio_input':str(audio_source),'runtime_input':str(runtime_source),
        'complete_root_file_counts':[1557,430,1595],'actual_Git_root_trees':trees,'git_commands':commands,
        'full_forward_reverse_forward_replay':True,'both_complete_input_F9_preserved':True,
        'all1595_output_bytes_Git_blobs_modes_members_verified':len(final['files'])==1595,
        'skipped_only_root_git':True,'private_Git_reconstructed':True,'Rust_tests_run':False}


def write_report(path,value,protected):
    path=fresh_destination(path,protected);path.parent.mkdir(parents=True,exist_ok=True)
    need(path.parent.resolve()==path.parent,'report parent became aliased')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--inventory-sha256',required=True)
    parser.add_argument('--audio-source',type=Path);parser.add_argument('--runtime-source',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--producer',type=Path);parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    need(args.producer is None or args.output is None,'fresh replay and producer check are separate operations')
    need(args.output is None or (args.audio_source is not None and args.runtime_source is not None),'both complete source inputs required for replay')
    protected=[HERE]+[path.absolute() for path in (args.audio_source,args.runtime_source,args.output,args.producer) if path is not None]
    if args.report is not None:fresh_destination(args.report,protected)
    manifest=verify_capsule(args.inventory_sha256)
    result={'state':'EXACT_D7_COMPLETE_TWO_ROOT_UNIFIED1595_SOURCE_CAPSULE_VERIFIED','head':HEAD_COMMIT,'tree':HEAD_TREE,
        'historical_runtime_tests':289,'historical_tools_tests':334,'historical_fresh_release_binaries':4,
        'fresh_CI_tests':0,'runtime_qualified':False,'production_ready':False,'ExecutionAdmission_constructible':False,
        'actual_SELinux_transition_qualified':False,'Android_builds':0,'Android_starts':0}
    if args.output is not None:result['replay']=replay(manifest,args.audio_source,args.runtime_source,args.output)
    if args.producer is not None:
        current=source_snapshot(args.producer,catalog(manifest,'head'),HEAD_TREE)
        result['producer']={'path':str(args.producer.absolute()),'files':len(current['files']),'tree':current['tree'],'whole_source_verified':True}
    if args.report is not None:write_report(args.report,result,protected)
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':
    main()
