#!/usr/bin/env python3
"""Create a fresh runner revision using libtest's independent result file."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

WORK = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02')
OLD = WORK/'paired-builder451-compile01'
DEST = WORK/'paired-builder451-compile02'
REMOTE = '/home/alex/work/pocket4-native-generation-builder451-compile-02-20261105'
EVIDENCE = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/paired-builder451-compile01')


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write(name, data):
    path = DEST/name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


old = (OLD/'compile_builder.py').read_text()
assert pin(old.encode())['sha256'] == 'e626724aa36d49412aaacd6249687044501438c05492f2176c59ad9c3aadcd5a'
source = old.replace('/home/alex/work/pocket4-native-generation-builder451-compile-01-20261105', REMOTE)
before = "require(argv[1:] == ['--exact',FAKEROOT_TEST,'--test-threads=1','--nocapture'],"
after = "require(argv[1:] == ['--exact',FAKEROOT_TEST,'--test-threads=1','--nocapture',\n                            '--logfile',str(OUT/'projection-test-20.libtest')],"
assert source.count(before) == 1
source = source.replace(before, after)

helper = r'''
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

'''
assert source.count('\ndef execute():') == 1
source = source.replace('\ndef execute():', '\n'+helper+'\ndef execute():')

before = """        test_env=dict(env)
        test_env['PATH']=IMAGE_TEST_PATH"""
after = """        listed_names=[line[:-6] for line in test_list.splitlines() if line.endswith(': test')]
        require(listed_names and len(listed_names)==len(set(listed_names)) and
                not any(line.endswith(': benchmark') for line in test_list.splitlines()),
                'actual registration list is duplicate/empty or contains unqualified benchmarks')
        libtest_help=command([str(test_binary),'--help'],COPIED,env,'builder-test-help',report['commands'],10).decode()
        require(re.search(r'^\\s*--logfile\\s',libtest_help,re.MULTILINE) is not None and
                'Write logs to the specified file' in libtest_help,
                'actual pinned libtest does not advertise the independently reviewed logfile option')
        report['actual_libtest_logfile_support']=True
        report['actual_registered_test_count']=len(listed_names)
        test_env=dict(env)
        test_env['PATH']=IMAGE_TEST_PATH"""
assert source.count(before) == 1
source = source.replace(before, after)
before = """        for index,name in enumerate(TESTS):
            output=command([str(test_binary),'--exact',name,'--test-threads=1','--nocapture'],COPIED,test_env,'projection-test-'+str(index),report['commands'],30).decode()
            require('test result: ok. 1 passed; 0 failed;' in output and 'test '+name+' ... ok' in output,
                    'focused test did not actually execute exactly once: '+name)
"""
after = """        report['focused_result_gates']=[]
        for index,name in enumerate(TESTS):
            report['focused_result_gates'].append(focused_test(
                test_binary,name,index,len(listed_names),test_env,report['commands']))
"""
assert source.count(before) == 1
source = source.replace(before, after)
ast.parse(source)

old_packet = json.loads((OLD/'verified-source-packet.json').read_bytes())
assert len(old_packet) == 14
data = {name: value.encode() for name, value in old_packet.items()}
data['compile_builder.py'] = source.encode()
for name, raw in data.items():
    if name != 'compile_builder.py':
        assert raw == (OLD/name).read_bytes()
old_stage = (OLD/'stage.py').read_text()
stage_ast = ast.parse(old_stage)
expected_assignment = next(n for n in stage_ast.body if isinstance(n, ast.Assign) and n.targets[0].id == 'EXPECTED')
old_expected = ast.get_source_segment(old_stage, expected_assignment)
expected = {name: pin(raw) for name, raw in data.items()}
stage = old_stage.replace('/home/alex/work/pocket4-native-generation-builder451-compile-01-20261105', REMOTE)
stage = stage.replace(old_expected, 'EXPECTED='+repr(expected))
packet = json.dumps({name: raw.decode() for name, raw in data.items()}, ensure_ascii=True, sort_keys=True)
request = json.loads((OLD/'exact-request.json').read_bytes())
request['stdin'] = stage+'\nPACKET=json.loads('+repr(packet)+')\nmain(PACKET)\n'
request['idempotency_key'] = 'pocket4-native-generation-builder451-matching-compile-02-20261105'
ast.parse(request['stdin'])
defs = lambda text: {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
olddefs, newdefs = defs(old), defs(source)
changed = sorted(n for n in olddefs if olddefs[n] != newdefs[n])
added = sorted(set(newdefs)-set(olddefs))
assert changed == ['command', 'execute']
assert added == ['focused_test', 'validate_focused_result']
assert defs(old_stage)['main'] == defs(stage)['main']
for name in ['TESTS','ORIGINAL_TESTS','PAIR_TESTS','MANIFEST_PARENT','MANIFEST_451']:
    a = next(n for n in ast.parse(old).body if isinstance(n,ast.Assign) and n.targets[0].id == name)
    b = next(n for n in ast.parse(source).body if isinstance(n,ast.Assign) and n.targets[0].id == name)
    assert ast.dump(a,include_attributes=False) == ast.dump(b,include_attributes=False)

DEST.mkdir()
for name, raw in data.items():
    write(name, raw)
write('stage.py', stage.encode())
write('verified-source-packet.json', (packet+'\n').encode())
write('exact-request.json', (json.dumps(request, ensure_ascii=False, indent=2)+'\n').encode())
write('runner01-to02.patch', ''.join(difflib.unified_diff(old.splitlines(True), source.splitlines(True), fromfile='compile01/compile_builder.py', tofile='compile02/compile_builder.py')).encode())
write('stage01-to02.patch', ''.join(difflib.unified_diff(old_stage.splitlines(True), stage.splitlines(True), fromfile='compile01/stage.py', tofile='compile02/stage.py')).encode())
for name, digest in [('result.json','a6e91dc00c6b97b91be2168d86c3c8b00b1f2efc1c8abb3e6a6a471f68c0af8a'),
                     ('projection-test-19.stdout','4fdf8201f38fdf183be29d63b7a9f7641b82c1bc14f78b1097892a6d530d3512'),
                     ('projection-test-19.stderr','e09f2e63bf27b7d28ec359671bdf3ab4ba50d041dcf5203dcafb7085fa9be630')]:
    raw=(EVIDENCE/name).read_bytes(); assert pin(raw)['sha256'] == digest
    write('references/actual-compile01/'+name, raw)
for f in sorted((WORK/'paired451-libtest-references01').iterdir()):
    write('references/rust-1.93.0/'+f.name, f.read_bytes())
write('make_request.py', Path(__file__).read_bytes())
plan = subprocess.run([sys.executable,'-I','-B',str(DEST/'compile_builder.py')], capture_output=True, check=True)
assert not plan.stderr
write('PLAN.json', plan.stdout)

# This is a local parser control using the actual noisy stdout plus an explicitly
# synthetic independent result. It is not a libtest execution or device pass.
namespace = {'re': __import__('re')}
code = ast.parse(source)
subset = ast.Module(body=[n for n in code.body if isinstance(n,ast.FunctionDef) and n.name in ('require','validate_focused_result')],type_ignores=[])
exec(compile(subset,'<reviewed-focused-parser>','exec'), namespace)
namespace['FAKEROOT_TEST'] = 'native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata'
name = 'native_generation::tests::real_erofs_bundle_verifies_its_embedded_pair'
actual_output = (EVIDENCE/'projection-test-19.stdout').read_text()
ok = ('ok '+name+'\n').encode()
cases = [
    ('actual_noisy_stdout_and_synthetic_exact_result',actual_output,ok,195,True),
    ('wrong_name',actual_output,b'ok foreign\n',195,False),
    ('duplicate_result',actual_output,ok+ok,195,False),
    ('missing_result',actual_output,b'',195,False),
    ('ignored_result',actual_output,('ignored '+name+'\n').encode(),195,False),
    ('zero_executed_summary',actual_output.replace('1 passed; 0 failed;','0 passed; 0 failed;'),ok,195,False),
    ('duplicate_summary',actual_output+actual_output,ok,195,False),
    ('wrong_registration_count',actual_output,ok,196,False),
]
observed=[]
for label,output,log,count,wanted in cases:
    try:
        namespace['validate_focused_result'](name,19,output,log,count)
        accepted=True
    except RuntimeError:
        accepted=False
    assert accepted is wanted, label
    observed.append({'name':label,'accepted':accepted,'expected':wanted})
validation = {'schema':1,'scope':'source/packet/AST/default PLAN and eight local parser controls only',
              'changed_existing_functions':changed,'added_functions':added,
              'unchanged_functions':sorted(n for n in olddefs if n not in changed),
              'stage_main_AST_unchanged':True,'unchanged_packet_files':13,
              'production451_manifest_unchanged':True,'original22_tests_unchanged':True,
              'old_actual_compile01_failure_retained':True,'parser_controls':observed,
              'independent_log_values_in_local_controls_are_synthetic':True,
              'actual_libtest_execution':False,'actual_compile02_execution':False,
              'request_sha256':pin((DEST/'exact-request.json').read_bytes())['sha256']}
write('LOCAL_VALIDATION.json',(json.dumps(validation,sort_keys=True,indent=2)+'\n').encode())
write('README.md',b'''# Paired builder451 runner revision 02

The Rust451 source manifest, four source payloads, original seven projection tests and fifteen pairing tests are unchanged. Compile01's actual FAIL is preserved. Its test19 child returned zero but mkfs.erofs inserted output between libtest's test-name prefix and its final ok, so the old contiguous-name gate rejected it.

This fresh runner uses Rust1.93's supported, deprecated --logfile option. Official tag sources are retained as references; they are not a claim that source bytes are tied to the installed toolchain. The actual held test ELF must advertise --logfile in --help before any focused test executes. Each test gets a create-only 0600 file, held across execution, and exactly `ok <full exact test name>\n` is required from that same inode. Ordinary stdout/stderr remain complete. Exact registration, --exact selection, running count, zero ignored/measured/failed, filtered count and successful summary still agree. Only the original nested fakeroot case permits its two stdout summaries; its outer independent result is exactly one record. Original timeout, process-exit and child-retirement gates remain unchanged.

Default PLAN and eight local parser controls ran; the positive parser fixture combines actual noisy stdout with a clearly synthetic logfile line. No Rust compile, installed libtest or image test was executed locally. Root alone dispatches the frozen fresh request. This does not qualify ART/APEX signatures, enabled metadata lifecycle or all apps.
''')
pins={str(f.relative_to(DEST)):pin(f.read_bytes()) for f in sorted(DEST.rglob('*')) if f.is_file()}
write('SOURCE_PINS.json',(json.dumps({'schema':1,'files':pins,'remote_execution':False},indent=2)+'\n').encode())
print(json.dumps({'directory':str(DEST),'controller':pin(data['compile_builder.py']),
                  'request':pin((DEST/'exact-request.json').read_bytes()),
                  'source_pins':pin((DEST/'SOURCE_PINS.json').read_bytes()),
                  'files':len(pins)+1,'request_packet_files':len(data)},sort_keys=True,indent=2))
