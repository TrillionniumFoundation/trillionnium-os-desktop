import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

WORK = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02')
EVIDENCE = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence')
BASE = WORK/'paired-builder451-work01'
OLD_REQUEST = WORK/'builder-streaming-compile-03/final-request-01'
DEST = WORK/'paired-builder451-compile01'
REMOTE = '/home/alex/work/pocket4-native-generation-builder451-compile-01-20261105'

def pin(data):
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def write(name,data):
    path=DEST/name
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(data)

template=(BASE/'compile_builder.template.py').read_bytes()
assert pin(template)['sha256']=='a68f23024f20b165d54da31dfa4071ab77daac25937b6cc6ea7028c73f831c29'
helper=(WORK/'paired451-image-tools-bound01.py').read_text()
source=template.decode()
source=source.replace('import signal\n','import signal\nimport shutil\n',1)
source=source.replace('Compile only an isolated normal builder with a frozen 1-change/1-addition source delta.',
                      'Compile a fresh paired-generation builder451 and run 22 exact source tests; no platform execution.')
start=source.index('IMAGE_TOOL_OBSERVATION = ')
end=source.index('\ndef execute():',start)
source=source[:start]+helper+'\n'+source[end:]
old="    require(code == 0 and not timeout, 'command failed: '+label)\n    require(not children(), 'command left owned children: '+label)"
new="""    require(code == 0 and not timeout, 'command failed: '+label)
    if label == 'projection-test-20':
        require(argv[1:] == ['--exact',FAKEROOT_TEST,'--test-threads=1','--nocapture'],
                'normal daemon retirement is restricted to the exact fakeroot metadata test')
        row['normal_fakeroot_daemon_retirement'] = {}
        reap_normal_fakeroot_daemon(row['normal_fakeroot_daemon_retirement'])
    require(not children(), 'command left owned children: '+label)"""
assert source.count(old)==1;source=source.replace(old,new)
old="""        test_env['PATH']='/usr/bin:/bin'
        require('FAKEROOTKEY' not in test_env and 'LD_PRELOAD' not in test_env,"""
new="""        test_env['PATH']=IMAGE_TEST_PATH
        require(all(name not in test_env for name in ('FAKEROOTKEY','LD_PRELOAD','LD_LIBRARY_PATH')),"""
assert source.count(old)==1;source=source.replace(old,new)
ast.parse(source)

data={
    'compile_builder.py':source.encode(),
    'compiled-parent450-manifest.json':(BASE/'compiled-parent450-manifest.json').read_bytes(),
    'expected-builder451-manifest.json':(BASE/'expected-builder451-manifest.json').read_bytes(),
    'compiled-parent450-result.json':(EVIDENCE/'builder450-compile03/result.json').read_bytes(),
    'image-tools-result.json':(EVIDENCE/'native-generation-image-tools-read02/result.json').read_bytes(),
}
assert pin(data['compiled-parent450-result.json'])['sha256']=='a1d8fe1e891c876baeff555b18fce9bafe6a895d379d9e55261c6df1981785de'
assert pin(data['image-tools-result.json'])['sha256']=='b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292'
for name in ['go-control-result.json','rust193-tools-read02-result.json','selection-result.json','selected-build.stdout','registry-result.json']:
    data[name]=(OLD_REQUEST/name).read_bytes()
for path in (BASE/'delta').rglob('*.rs'):
    data[str(path.relative_to(BASE))]=path.read_bytes()
assert len(data)==14
oldmap=json.loads(data['compiled-parent450-manifest.json'])
newmap=json.loads(data['expected-builder451-manifest.json'])
delta=[p for p in newmap if newmap[p]!=oldmap.get(p)]
assert len(oldmap)==450 and len(newmap)==451 and len(delta)==4
assert {p for p in oldmap if p not in newmap}==set()
for p in delta:assert pin(data['delta/'+p])=={k:newmap[p][k] for k in ['bytes','sha256']}
expected={name:pin(raw) for name,raw in data.items()}
stage="""import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path(REMOTE_ROOT)
EXPECTED=EXPECTED_FILES
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('staged source member set differs')
    for name,text in packet.items():
        path=PurePosixPath(name)
        if not name or path.is_absolute() or '..' in path.parts or str(path)!=name:raise RuntimeError('noncanonical staged source path')
        raw=text.encode('utf-8')
        if len(raw)!=EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('staged source pin mismatch: '+name)
    for parent in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('owned root parent aliases non-directory')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    source=ROOT/'control-source';source.mkdir(mode=0o700)
    for name,text in packet.items():
        path=source/name
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        for parent in [path.parent,*path.parent.parents]:
            if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('staged parent is not a real directory')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as stream:
            stream.write(text.encode('utf-8'));stream.flush();os.fsync(stream.fileno())
    raw=(json.dumps({'schema':1,'files':EXPECTED,'Main_actions':0,'only_owned_root_written':True},indent=2)+'\\n').encode()
    fd=os.open(ROOT/'stage-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'compile_builder.py'),'--execute-once'],{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
""".replace('REMOTE_ROOT',repr(REMOTE)).replace('EXPECTED_FILES',repr(expected))
packet=json.dumps({name:raw.decode('utf-8') for name,raw in data.items()},ensure_ascii=True,sort_keys=True)
stdin=stage+'\nPACKET=json.loads('+repr(packet)+')\nmain(PACKET)\n'
request={'host':'pocket4','executable':'/usr/bin/python3','args':['-I','-B','-'],'stdin':stdin,'cwd':'/',
         'cpu_quota_percent':100,'memory_max_bytes':1073741824,'nice':15,'timeout_seconds':600,
         'idempotency_key':'pocket4-native-generation-builder451-matching-compile-01-20261105'}
ast.parse(stdin)
defs=lambda text:{n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
olddefs=defs(template);newdefs=defs(source)
same=sorted(name for name in olddefs if name in newdefs and olddefs[name]==newdefs[name])
changed=sorted(name for name in olddefs if name in newdefs and olddefs[name]!=newdefs[name])
assert changed==['command','execute','image_toolchain']
assert len(same)==28
assert set(newdefs)-set(olddefs)=={'image_pin','reap_normal_fakeroot_daemon'}
DEST.mkdir()
for name,raw in data.items():write(name,raw)
write('stage.py',stage.encode())
write('verified-source-packet.json',(packet+'\n').encode())
write('exact-request.json',(json.dumps(request,ensure_ascii=False,indent=2)+'\n').encode())
write('template-to-actual-bound.patch',''.join(difflib.unified_diff(template.decode().splitlines(True),source.splitlines(True),fromfile='template/compile_builder.py',tofile='actual-bound/compile_builder.py')).encode())
write('references/compile_builder.template.py',template)
write('image_tools_bound.py',helper.encode())
write('make_request.py',Path(__file__).read_bytes())
plan=subprocess.run([sys.executable,'-I','-B',str(DEST/'compile_builder.py')],capture_output=True,check=True)
planvalue=json.loads(plan.stdout)
assert planvalue['mode']=='PLAN' and planvalue['source_files']==451 and len(planvalue['focused_existing_tests'])==22
assert planvalue['focused_existing_tests'][20]=='native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata'
assert not plan.stderr
write('PLAN.json',plan.stdout)
validation={'schema':1,'scope':'source/packet derivation, AST comparison and default PLAN only','actual_remote_execution':False,
            'unchanged_template_functions':same,'changed_template_functions':changed,
            'added_functions':sorted(set(newdefs)-set(olddefs)),
            'source_parent_count':450,'source_candidate_count':451,'source_changed_existing':3,'source_added':1,'source_unchanged_existing':447,
            'frozen_451_production_sources_changed_from_next01':False,
            'packet_files':expected,'actual_Rust_compile':False,'actual_image_tests':False,
            'fixed_auxiliaries_first_observed_at_execution_not_reader02':['/usr/bin/sed','/usr/bin/cut','/usr/bin/cat'],
            'normal_daemon_retirement_scope':'only exact projection-test-20; waitpid WNOHANG <=2s; <=1 own daemon; exit0 or wrapper SIGTERM; no signals; any remaining live child fails',
            'outer_budget':{k:request[k] for k in ('cpu_quota_percent','memory_max_bytes','timeout_seconds','nice')},
            'request_sha256':pin((DEST/'exact-request.json').read_bytes())['sha256']}
write('LOCAL_VALIDATION.json',(json.dumps(validation,indent=2)+'\n').encode())
write('README.txt',b'Actual-bound paired builder451 source and 22-test compile-only request. No Main, Android, ART or full-engine action.\nThe 3-edit/1-addition Rust source delta is unchanged from frozen next01. Existing 7 projection tests and 15 paired-record/image tests remain required. The 5 image tests use real ext4/erofs/zip/fakeroot tools on disposable ordinary test bytes; no platform APEX signature or enabled lifecycle is claimed.\nReader02 binds nine actual tools and four selected fakeroot backend/interpreter inputs. Fixed sed/cut/cat are new held root-owned observations before execution and are recorded honestly as such. Controlled test PATH includes actual /usr/sbin; no inherited loader/fakeroot state. Actual dynamic closure and uutils chown behavior must pass.\nOnly the exact fakeroot metadata test may waitpid its one adopted daemon for up to 2 seconds, without signals. An alive daemon, unexpected status or extra child remains a failure; final forced cleanup never produces PASS.\nRoot alone schedules the exact request after review; no remote action was performed while generating this freeze.\n')
pins={str(p.relative_to(DEST)):pin(p.read_bytes()) for p in sorted(DEST.rglob('*')) if p.is_file()}
write('SOURCE_PINS.json',(json.dumps({'schema':1,'files':pins,'remote_execution':False},indent=2)+'\n').encode())
print(json.dumps({'root':str(DEST),'controller':pin(data['compile_builder.py']),'request':pin((DEST/'exact-request.json').read_bytes()),
                  'source_pins':pin((DEST/'SOURCE_PINS.json').read_bytes()),'files':len(pins)+1,'bytes':sum(r['bytes'] for r in pins.values())},indent=2))
