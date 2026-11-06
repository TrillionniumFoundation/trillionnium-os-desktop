#!/usr/bin/env python3
"""Derive reviewable host-only requests; do not submit or execute either one."""
from pathlib import Path
import ast
import copy
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "builder470-hostprep-r1"
CANDIDATE = ROOT / "candidate-r3"
HOST_ROOT = "/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-01-20261106"
BASELINE = "/home/alex/work/pocket4-native-typed-ingress-builder469-native-provider-compile-01-20261106"
PROFILE = "/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106"
digest = lambda data: hashlib.sha256(data).hexdigest()

baseline_bytes = (ROOT / "reference/builder469-harness/expected-builder469-manifest.json").read_bytes()
assert len(baseline_bytes) == 97964
assert digest(baseline_bytes) == "d9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934"
baseline = json.loads(baseline_bytes)
assert len(baseline) == 493
candidate_manifest = json.loads((CANDIDATE / "SOURCE_CANDIDATE.json").read_bytes())
expected = copy.deepcopy(baseline)
overlays = {}
for entry in candidate_manifest["files"]:
    data = (CANDIDATE / entry["path"]).read_bytes()
    assert len(data) == entry["bytes"] and digest(data) == entry["sha256"]
    overlays[entry["path"]] = data.decode("utf-8")
    expected[entry["path"]] = {"kind": "file", "bytes": len(data), "mode": baseline.get(entry["path"], {}).get("mode", 0o600), "sha256": digest(data)}
assert len(expected) == 498
changed = sorted(name for name in baseline if expected[name] != baseline[name])
added = sorted(set(expected) - set(baseline))
assert changed == ["tools/droidloom-update/src/android.rs", "tools/droidloom-update/src/native_role_ingress.rs"]
assert len(added) == 5
expected_bytes = (json.dumps(expected, sort_keys=True, indent=2) + "\n").encode()

prior_compile = (ROOT / "reference/builder469-harness/compile_owned_candidate_02.py").read_text()
prior_qualify = (ROOT / "reference/builder469-harness/qualify_owned_candidate_02.py").read_text()
assert digest(prior_compile.encode()) == "b78a80fab53847b0f88f6b3369b44858ed12df2d58feb76fb9a0811c2304927a"
assert digest(prior_qualify.encode()) == "69691a58fe19ffd0de7a6544647b8290923ab4e58aad43cba734250f05753486"
tree = ast.parse(prior_qualify)
functions = {node.name: ast.get_source_segment(prior_qualify, node) for node in tree.body if isinstance(node, ast.FunctionDef)}
required = ["require", "no_alias", "read", "inventory", "utc", "save", "held_file", "parse_admission_meminfo", "memory_admission", "record_resource_admission", "owned_resource_gate", "subreaper", "child_ids", "cleanup_children", "hash_pin", "collect_pins", "checked_tools", "identity", "held", "hash_held", "qualify_compiler_inputs", "validate_focused_result", "focused_test", "sha", "pinned_json", "command"]
tests = next(ast.literal_eval(node.value) for node in ast.parse(prior_compile).body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TESTS" for t in node.targets))
assert len(tests) == 16
tests += ["android::tests::typed_systemui_defaults_preserve_real_consumers_and_dependency_edges", "android::tests::typed_systemui_projection_preserves_loaded_ordinary_dependencies", "native_role_ingress::tests::systemui_extension_rejects_missing_provider_wrong_revision_or_scope"]
assert len(set(tests)) == 19

header = "import os,sys,json,hashlib,stat,pathlib,subprocess,time,signal,ctypes,resource,datetime,re\nP=Path=pathlib.Path\n"
header += f"ROOT=P({HOST_ROOT!r})\nSOURCE=COPIED=ROOT/'builder-source'\nATTEMPT=OUT=ROOT/'compile01'\nBASE=P({BASELINE!r})\nPROFILE_BASE=P({PROFILE!r})\n"
header += "MEMORY_MAX=1024**3\nSWAP_MAX=0\nMIN_AVAILABLE=3*1024**3\n"
header += "TESTS=" + repr(tests) + "\nEXPECTED_REGISTERED_TESTS=209\n"
header += "EXPECTED_MANIFEST_SHA=" + repr(digest(expected_bytes)) + "\n"
header += "FAKEROOT_TEST='native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata'\n"
helper_text = "\n\n".join(functions[name] for name in required) + "\n\n"
main = r'''
if sys.argv[1:] != ['--execute-once']:
 print(json.dumps({'state':'PLAN_ONLY','Main_actions':0,'Android_actions':0,'Soong_invoked':False,'compiler_invoked':False,'production_ready':False}));sys.exit(0)
require(os.getuid()==1000 and os.geteuid()==1000,'unprivileged operator required')
os.umask(63);resource.setrlimit(resource.RLIMIT_CORE,(0,0));no_alias(ROOT)
require(not ATTEMPT.exists(),'fresh compile output required; no automatic retry');ATTEMPT.mkdir(mode=448)
records=[];failure=None;candidate=None;baseline=None;dependencies=None;tools_before=None;cgroup=None
result={'schema':1,'state':'FAILED_BEFORE_BUILD','scope':'builder470 Rust-only exact source successor qualification',
 'Main_actions':0,'Android_actions':0,'install_actions':0,'Soong_invoked':False,
 'runtime_authorization_enabled':False,'production_ready':False,'started_utc':utc()}
try:
 parent_compile,parent_compile_pin=pinned_json(BASE/'compile02/result.json','a14dde5d3a2e85fe44d90c651527c8c8402d341403ef84a7bc92b93252de72b9',1048576)
 parent_qualification,parent_qualification_pin=pinned_json(BASE/'qualify02/result.json','f31bb31d29967bacdb0842eea99dae65f8b67425f26f10063c3d84099367fd64',1048576)
 require(parent_compile['state']=='RUST_BUILD_AND_FOCUSED_TESTS_PASS' and parent_compile['tests_passed']==16 and parent_compile['registered_tests']==206,'actual builder469 baseline differs')
 require(parent_qualification['state']=='ACTUAL_COMPILE02_INPUT_CONTINUITY_AND_16_INDEPENDENT_TESTS_PASS' and parent_qualification['production_ready'] is False,'builder469 independent qualification differs')
 result['baseline_compile']=parent_compile_pin;result['baseline_independent_qualification']=parent_qualification_pin
 profile,profile_pin=pinned_json(PROFILE_BASE/'attempt01/result.json','871e78f7ad8f3f3a12c165297e4fe566d96cfe3a2ce64a0d0010cffdb647b6b8',1048576)
 require(profile['state']=='PASS' and profile['owned_resource_gate']['pass'] is True and profile['owned_resource_gate']['before']['fields']['memory.max']=='1073741824' and profile['owned_resource_gate']['before']['fields']['cpu.max']=='100000 100000','original one-GiB Rust authority differs')
 result['profile_authority']=profile_pin
 affinity=sorted(os.sched_getaffinity(0));require(len(affinity)>=3,'at least two logical CPUs must remain free');os.sched_setaffinity(0,affinity[-1:]);result['cpu_affinity']=affinity[-1:]
 member=P('/proc/self/cgroup').read_text().strip();require(member.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'),'own cgroup required')
 cgroup=P('/sys/fs/cgroup')/member[3:].lstrip('/');unit=cgroup.name
 require(unit.endswith('.service') and str(os.getpid()) in (cgroup/'cgroup.procs').read_text().split(),'own unit identity')
 require((cgroup/'memory.max').read_text().strip()==str(MEMORY_MAX) and (cgroup/'cpu.max').read_text().strip()=='100000 100000','owned Rust budget')
 subprocess.run(['/usr/bin/systemctl','--user','set-property','--runtime',unit,'MemorySwapMax=0'],check=True,capture_output=True,timeout=15)
 memory,owned,admission=record_resource_admission(cgroup);result['resource_admission']=admission
 subreaper();require(child_ids()==[],'unexpected owned child')
 candidate,candidate_pin=pinned_json(ROOT/'candidate-source-manifest.json',EXPECTED_MANIFEST_SHA,1048576)
 baseline,baseline_pin=pinned_json(BASE/'candidate-source-manifest.json','d9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934',1048576)
 require(len(candidate)==498 and len(baseline)==493 and inventory(SOURCE)==candidate and inventory(BASE/'builder-source')==baseline,'exact copied/baseline source map differs')
 changed=sorted(p for p in baseline if candidate.get(p)!=baseline[p]);added=sorted(set(candidate)-set(baseline))
 require(changed==CHANGED_FILES and added==ADDED_FILES and set(baseline)<=set(candidate),'exact seven-file source delta differs')
 result['candidate_manifest']=candidate_pin;result['baseline_manifest']=baseline_pin;result['source_delta']={'unchanged_existing':491,'changed_existing':changed,'added':added,'actual_source_file_count':498}
 candidate_rows={name:hash_held(SOURCE/name) for name in candidate}
 dependency_document,dependency_pin=pinned_json(PROFILE_BASE/'attempt01/dependency-inputs-before.json','34ab55489959d957294dcc25a93083346dffec934c96768c515d584bb91731c7',2*1024*1024)
 dependencies=dependency_document['files'];packages=dependency_document['packages']
 require(0<len(dependencies)<=16384 and len(packages)==49 and sum(p['kind']=='offline-registry' for p in packages)==45,'parent dependency source closure count differs')
 for name,row in dependencies.items():
  path=P(name);require(path.is_absolute() and str(path)==row['path'] and path.is_relative_to(P('/home/alex/.cargo/registry')),'dependency path escaped qualified registry')
  no_alias(path.parent);require(hash_held(path)==row,'registry source/archive identity changed: '+name)
 remapped=json.loads(json.dumps(packages).replace(str(PROFILE_BASE/'builder-source'),str(SOURCE)))
 require(sum(p['kind']=='pinned-builder-source' for p in remapped)==4,'workspace source package count differs')
 configs=set()
 for p in [SOURCE,*SOURCE.parents,P('/home/alex/.cargo')]:
  for name in ('config','config.toml'):configs.add(p/('.cargo/'+name) if p!=P('/home/alex/.cargo') else p/name)
 require(all(not p.exists() and not p.is_symlink() for p in configs),'new Cargo configuration input')
 parent_tools,parent_tools_pin=pinned_json(PROFILE_BASE/'attempt01/tool-inputs-before.json','323f770a9c227f4e3804f38c2211e78ce46a8031565242d34b6e42ed7f7b2433',1048576)
 pins={};collect_pins(parent_tools,pins);pins.pop('/home/alex/.cargo/bin/rustup',None)
 rustroot='/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu'
 explicit={'/bin/cargo':(40753664,'9548937d530bf439ff1ba47a3b2bd26eeb9c3aff1961c20c01798613de922578'),'/bin/rustc':(656704,'d32249a7c3bfcfc67b471460386e46323accae7125e344567a12d5664d99bb57'),'/bin/rustdoc':(13173040,'ece7829b8e7448a9d59c88080e2b16253b885c560f792002837901c7f24b7695')}
 for suffix,(count,checksum) in explicit.items():
  path=rustroot+suffix;row={'bytes':count,'sha256':checksum,'resolved_path':path};require(path not in pins or pins[path]==row,'compiler pin mismatch');pins[path]=row
 require(len(pins)>=10,'compiler/library authority incomplete');tools_before=checked_tools(pins);save(ATTEMPT/'tool-inputs-before.json',tools_before)
 (ATTEMPT/'tmp').mkdir(mode=448);(ATTEMPT/'cargo-target').mkdir(mode=448)
 environment={'PATH':rustroot+'/bin:/usr/bin:/bin','LANG':'C','LC_ALL':'C','CARGO_HOME':'/home/alex/.cargo','CARGO_TARGET_DIR':str(ATTEMPT/'cargo-target'),'CARGO_NET_OFFLINE':'true','CARGO_BUILD_JOBS':'1','RUSTC':rustroot+'/bin/rustc','RUSTDOC':rustroot+'/bin/rustdoc','CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER':'/usr/bin/cc','RUSTC_WRAPPER':'','RUSTC_WORKSPACE_WRAPPER':'','RUSTFLAGS':'','RUSTDOCFLAGS':'','CARGO_ENCODED_RUSTFLAGS':'','CARGO_ENCODED_RUSTDOCFLAGS':'','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1','GIT_OPTIONAL_LOCKS':'0','TMPDIR':str(ATTEMPT/'tmp')}
 version=command([rustroot+'/bin/rustc','-Vv'],SOURCE,environment,'rust-version',records,20).decode();require('release: 1.93.0\n' in version,'Rust version differs')
 cargo=rustroot+'/bin/cargo'
 build_log=command([cargo,'build','--offline','--locked','-j','1','-p','droidloom-update','--bin','droidloom-update','--message-format=json-render-diagnostics'],SOURCE,environment,'build',records,450)
 test_log=command([cargo,'test','--offline','--locked','-j','1','-p','droidloom-update','--bin','droidloom-update','--no-run','--message-format=json-render-diagnostics'],SOURCE,environment,'test-compile',records,300)
 build_packages=qualify_compiler_inputs(build_log,remapped,dependencies,candidate_rows)
 test_packages=qualify_compiler_inputs(test_log,remapped,dependencies,candidate_rows)
 expected_packages=sorted(p['id'] for p in remapped)
 require(build_packages==test_packages==expected_packages and len(expected_packages)==49,'actual Cargo package closure differs')
 result['dependency_continuity']={'authority':dependency_pin,'all_source_bytes_and_full_identities_equal_before':True,'recorded_files_and_archives':len(dependencies),'selected_packages':49,'registry_packages':45,'actual_build_packages':build_packages,'actual_test_compile_packages':test_packages,'new_dependency_fetches':0}
 artifacts=[json.loads(line) for line in test_log.decode().splitlines() if line.startswith('{')]
 executables=[x['executable'] for x in artifacts if x.get('reason')=='compiler-artifact' and x.get('target',{}).get('name')=='droidloom-update' and x.get('profile',{}).get('test') and x.get('executable')]
 require(len(executables)==1,'one actual test executable required');test=P(executables[0]);require(test.is_relative_to(ATTEMPT/'cargo-target'),'test executable escaped owned target')
 listed=command([str(test),'--list'],SOURCE,environment,'test-list',records,20).decode();names=[line[:-6] for line in listed.splitlines() if line.endswith(': test')]
 require(len(names)==EXPECTED_REGISTERED_TESTS and len(set(names))==EXPECTED_REGISTERED_TESTS and set(TESTS)<=set(names),'actual registered test scope differs')
 focused=[]
 for index,name in enumerate(TESTS):focused.append(focused_test(test,name,index,len(names),environment,records))
 result.update({'state':'RUST_BUILD_AND_19_INDEPENDENT_FOCUSED_TESTS_PASS','tests_passed':len(focused),'test_names':TESTS,'registered_tests':len(names),'builder':hash_pin(ATTEMPT/'cargo-target/debug/droidloom-update'),'test_executable':hash_pin(test),'build_environment':environment,'source_manifest_sha256':EXPECTED_MANIFEST_SHA,'source_files':498,'new_project_count':242,'full_Android_Java_JNI_compiled':False})
except BaseException as error:
 failure=repr(error);result['state']='FAILED';result['error']=failure
finally:
 try:
  cleanup=cleanup_children();result['cleanup']=cleanup;require(cleanup.get('complete') is True,'owned child cleanup incomplete')
  if candidate is not None:require(inventory(SOURCE)==candidate,'candidate source changed after build');result['candidate_source_unchanged_after']=True
  if baseline is not None:require(inventory(BASE/'builder-source')==baseline,'baseline source changed after build');result['baseline_source_unchanged_after']=True
  if dependencies is not None:
   for name,row in dependencies.items():require(hash_held(P(name))==row,'registry input changed after build: '+name)
   result['registry_input_bytes_and_full_identities_unchanged_after']=True
  if tools_before is not None:require(checked_tools(pins)==tools_before,'compiler input identity changed');result['tool_inputs_unchanged_after']=True
  if cgroup is not None:
   result['memory_events']=(cgroup/'memory.events').read_text();result['owned_resource_gate']=owned_resource_gate(result['memory_events'])
   require(all(result['owned_resource_gate']['events'][k]==0 for k in ('oom','oom_kill','oom_group_kill')),'owned OOM event')
   result['memory_peak']=(cgroup/'memory.peak').read_text().strip();result['swap_peak']=(cgroup/'memory.swap.peak').read_text().strip()
   require((cgroup/'memory.swap.max').read_text().strip()=='0' and (cgroup/'memory.swap.current').read_text().strip()=='0' and result['swap_peak']=='0','zero swap after')
 except BaseException as error:
  result['state']='FAILED';result['finalization_error']=repr(error);failure=failure or repr(error)
 result['commands']=records;result['finished_utc']=utc();save(ATTEMPT/'result.json',result)
 print(json.dumps({'state':result['state'],'error':result.get('error'),'finalization_error':result.get('finalization_error'),'tests_passed':result.get('tests_passed',0),'result':hash_pin(ATTEMPT/'result.json')}),flush=True)
if failure:sys.exit(1)
'''
main = main.replace("CHANGED_FILES", repr(changed)).replace("ADDED_FILES", repr(added))
compiler = header + helper_text + main
ast.parse(compiler)

stage = r'''
import os,sys,json,hashlib,stat,pathlib,datetime
P=pathlib.Path
ROOT=P(HOST_ROOT_LITERAL)
BASE=P(BASELINE_LITERAL)
EXPECTED_BASELINE_SHA='d9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934'
EXPECTED_CANDIDATE_SHA=EXPECTED_CANDIDATE_LITERAL
FILE_PINS=FILE_PINS_LITERAL
OVERLAY_NAMES=OVERLAY_NAMES_LITERAL
def require(c,m):
 if not c:raise RuntimeError(m)
def no_alias(p):
 for q in [p,*p.parents]:
  if q.exists() or q.is_symlink():require(stat.S_ISDIR(q.lstat().st_mode),'non-directory or aliased parent: '+str(q))
def read(p,bound=2*1024*1024):
 no_alias(p.parent);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  a=os.fstat(fd);require(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_size<=bound,'source file type/link/bound: '+str(p))
  parts=[];total=0
  while total<=bound:
   b=os.read(fd,min(65536,bound+1-total))
   if not b:break
   parts.append(b);total+=len(b)
  data=b''.join(parts);z=os.fstat(fd);n=p.lstat();ident=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  require(total==a.st_size and ident(a)==ident(z)==ident(n),'source changed during read: '+str(p))
  return data,stat.S_IMODE(a.st_mode)
 finally:os.close(fd)
def inventory(root):
 result={}
 for here,ds,fs in os.walk(root,followlinks=False):
  for d in ds:require(stat.S_ISDIR((P(here)/d).lstat().st_mode),'directory alias')
  for f in fs:
   p=P(here)/f;b,mode=read(p);result[str(p.relative_to(root))]={'kind':'file','bytes':len(b),'mode':mode,'sha256':hashlib.sha256(b).hexdigest()}
 return result
def save(p,b,mode=384):
 no_alias(p.parent);fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(),mode)
def main(files):
 require(os.getuid()==os.geteuid()==1000,'unprivileged operator required');os.umask(63)
 require(set(files)==set(FILE_PINS),'exact staged file names differ')
 for name,contents in files.items():
  require(isinstance(contents,str),'UTF-8 file required');data=contents.encode();pin=FILE_PINS[name]
  require(len(data)==pin['bytes'] and hashlib.sha256(data).hexdigest()==pin['sha256'],'staged file differs: '+name)
 baseline_raw,unused=read(BASE/'candidate-source-manifest.json',1048576)
 require(hashlib.sha256(baseline_raw).hexdigest()==EXPECTED_BASELINE_SHA,'builder469 manifest differs')
 baseline=json.loads(baseline_raw);require(len(baseline)==493 and inventory(BASE/'builder-source')==baseline,'builder469 source baseline differs')
 expected_raw=files['candidate-source-manifest.json'].encode();require(hashlib.sha256(expected_raw).hexdigest()==EXPECTED_CANDIDATE_SHA,'candidate map differs')
 expected=json.loads(expected_raw);require(len(expected)==498 and set(baseline)<=set(expected),'candidate source count/ancestry differs')
 no_alias(ROOT.parent);require(not ROOT.exists() and not ROOT.is_symlink(),'fresh owned builder470 root required');ROOT.mkdir(mode=448)
 result={'schema':1,'state':'FAILED','Main_actions':0,'Android_actions':0,'commands_started':0,'compiler_invoked':False,'Soong_invoked':False,'bytes_copied':0,'files_copied':0,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 failure=None
 try:
  source=ROOT/'builder-source';source.mkdir(mode=448)
  for name,row in sorted(expected.items()):
   relative=P(name);require(not relative.is_absolute() and all(p not in ('','..','.') for p in relative.parts),'unsafe source relative path')
   if name in OVERLAY_NAMES:data=files['overlay/'+name].encode();mode=row['mode']
   else:
    data,mode=read(BASE/'builder-source'/name)
    require(name in baseline,'non-overlay source lacks baseline')
   require(mode==row['mode'] and len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'source copy differs: '+name)
   target=source/relative;target.parent.mkdir(parents=True,exist_ok=True,mode=448);save(target,data,mode);result['bytes_copied']+=len(data);result['files_copied']+=1
  require(inventory(source)==expected,'candidate source readback differs')
  require(inventory(BASE/'builder-source')==baseline,'builder469 source changed during stage')
  for name in ['candidate-source-manifest.json','compile_builder470.py','source-candidate.json','source-controls.json']:
   save(ROOT/name,files[name].encode())
  result.update(state='EXACT_BUILDER470_SOURCE_STAGED_NO_COMPILER_RUN',baseline_source_unchanged_after=True,candidate_source_exact=True,candidate_source_manifest_sha256=EXPECTED_CANDIDATE_SHA,source_files=498,added_files=5,changed_files=2)
 except BaseException as error:failure=repr(error);result['error']=failure
 finally:
  result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save(ROOT/'stage-result.json',(json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result),flush=True)
 if failure:raise RuntimeError(failure)
'''
files = {
    "candidate-source-manifest.json": expected_bytes.decode(),
    "compile_builder470.py": compiler,
    "source-candidate.json": (CANDIDATE / "SOURCE_CANDIDATE.json").read_text(),
    "source-controls.json": (ROOT / "candidate-r3-offline-controls.json").read_text(),
}
files.update({"overlay/" + name: text for name, text in overlays.items()})
pins = {name: {"bytes": len(text.encode()), "sha256": digest(text.encode())} for name, text in files.items()}
stage = stage.replace("HOST_ROOT_LITERAL", repr(HOST_ROOT)).replace("BASELINE_LITERAL", repr(BASELINE)).replace("EXPECTED_CANDIDATE_LITERAL", repr(digest(expected_bytes))).replace("FILE_PINS_LITERAL", repr(pins)).replace("OVERLAY_NAMES_LITERAL", repr(sorted(overlays)))
ast.parse(stage)
wire = json.dumps({"schema": 1, "stage": stage, "files": files}, ensure_ascii=False, separators=(",", ":"))
transport = f'''import hashlib,json,sys
if sys.argv[1:] != ['--stage-only-once']:
 print(json.dumps({{'state':'PLAN_ONLY','Main_actions':0,'Android_actions':0,'compiler_invoked':False,'submitted':False}}));raise SystemExit(0)
raw=sys.stdin.buffer.read({len(wire.encode())+1})
if len(raw)!={len(wire.encode())} or hashlib.sha256(raw).hexdigest()!={digest(wire.encode())!r}:raise RuntimeError('exact builder470 source request differs')
packet=json.loads(raw.decode('utf-8','strict'))
if set(packet)!={{'schema','stage','files'}} or type(packet['schema']) is not int or packet['schema']!=1:raise RuntimeError('builder470 source packet shape differs')
stage=packet['stage'].encode()
if len(stage)!={len(stage.encode())} or hashlib.sha256(stage).hexdigest()!={digest(stage.encode())!r}:raise RuntimeError('builder470 stage differs')
scope={{'__name__':'frozen_builder470_stage','__file__':'<frozen-builder470-stage>'}}
exec(compile(stage,'stage_builder470.py','exec'),scope,scope);scope['main'](packet['files'])
'''
stage_request = {"host": "pocket4", "executable": "/usr/bin/python3", "args": ["-B", "-I", "-c", transport, "--stage-only-once"], "stdin": wire, "idempotency_key": "pocket4-builder470-systemui-provider-source-stage-01-20261106", "timeout_seconds": 180, "cpu_quota_percent": 100, "memory_max_bytes": 1024**3, "nice": 10}
compile_transport = f'''import hashlib,os,stat,sys
from pathlib import Path
if sys.argv[1:] != ['--execute-once']:raise SystemExit('PLAN_ONLY: compiler not invoked')
p=Path({(HOST_ROOT+'/compile_builder470.py')!r})
for q in [p.parent,*p.parent.parents]:
 if not stat.S_ISDIR(q.lstat().st_mode):raise RuntimeError('compile source parent differs')
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 before=os.fstat(fd)
 if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size!={len(compiler.encode())}:raise RuntimeError('compile source type/bound differs')
 with os.fdopen(fd,'rb',closefd=False) as f:raw=f.read({len(compiler.encode())+1})
 identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 if identity(before)!=identity(os.fstat(fd)) or identity(before)!=identity(p.lstat()) or len(raw)!={len(compiler.encode())} or hashlib.sha256(raw).hexdigest()!={digest(compiler.encode())!r}:raise RuntimeError('compile source changed')
finally:os.close(fd)
scope={{'__name__':'__main__','__file__':str(p)}};exec(compile(raw,str(p),'exec'),scope,scope)
'''
compile_request = {"host": "pocket4", "executable": "/usr/bin/python3", "args": ["-B", "-I", "-c", compile_transport, "--execute-once"], "idempotency_key": "pocket4-builder470-systemui-provider-rust-compile-01-20261106", "timeout_seconds": 1500, "cpu_quota_percent": 100, "memory_max_bytes": 1024**3, "nice": 10}
assert not DEST.exists(), "immutable packet directory already exists"
DEST.mkdir()
outputs = {
    "candidate-source-manifest.json": expected_bytes,
    "compile_builder470.py": compiler.encode(),
    "stage_builder470.py": stage.encode(),
    "stage_transport.py": transport.encode(),
    "compile_transport.py": compile_transport.encode(),
    "stage-stdin.json": wire.encode(),
    "exact-stage-request.json": (json.dumps(stage_request, indent=2) + "\n").encode(),
    "exact-compile-request.json": (json.dumps(compile_request, indent=2) + "\n").encode(),
}
for name, data in outputs.items():
    (DEST / name).write_bytes(data)
helper_pins = [{"name": name, "source": "reference/builder469-harness/qualify_owned_candidate_02.py", "bytes": len(functions[name].encode()), "sha256": digest(functions[name].encode()), "copied_unchanged": True} for name in required]
plan = {
    "schema": "pocket4-builder470-host-only-preparation-v1",
    "state": "SEALED_FOR_ROOT_REVIEW_NOT_SUBMITTED",
    "host_root": HOST_ROOT,
    "baseline_root": BASELINE,
    "baseline_files": 493,
    "candidate_files": 498,
    "changed_existing": changed,
    "added": added,
    "source_bytes_to_copy": sum(row["bytes"] for row in expected.values()),
    "helper_provenance": helper_pins,
    "compiler_changes": "Retain old qualified resource/child/libtest helpers verbatim; bind a new complete source inventory, 19 selected tests and 209 registrations; validate all 49 compiler package inputs before/after.",
    "rust_profile": {"memory_max_bytes": 1024**3, "swap_max_bytes": 0, "cpu_quota_percent": 100, "jobs": 1, "fresh_MemAvailable_minimum_bytes": 3*1024**3, "logical_CPUs_left": 2, "rust_version": "1.93.0", "offline_locked": True},
    "full_framework_profile_unchanged": {"memory_max_bytes": 10*1024**3, "swap_max_bytes": 0, "fresh_MemAvailable_minimum_bytes": 15*1024**3, "cpu_quota_percent": 200, "jobs": 1, "dependency_mode": "Strict", "allow_missing_dependencies": False},
    "source_stage_only_request": "exact-stage-request.json",
    "subsequent_rust_only_request": "exact-compile-request.json",
    "normal06_framework_request": "Not sealed: requires actual newly qualified builder470 output and root's current exact full scope, including the new QA helper. Old 46-scope is not complete for this purpose.",
    "Main_or_Android_reads_or_writes": 0,
    "whole_AOSP_source_copy": False,
    "full_framework_build_submitted": False,
    "production_ready": False,
    "cleanup_eligible": False,
    "files": [{"path": name, "bytes": len(data), "sha256": digest(data)} for name, data in outputs.items()],
}
plan_bytes = (json.dumps(plan, indent=2) + "\n").encode()
(DEST / "execution-plan.json").write_bytes(plan_bytes)
print(json.dumps({"output": str(DEST), "candidate_manifest_bytes": len(expected_bytes), "candidate_manifest_sha256": digest(expected_bytes), "files": plan["files"], "execution_plan_bytes": len(plan_bytes), "execution_plan_sha256": digest(plan_bytes)}))
