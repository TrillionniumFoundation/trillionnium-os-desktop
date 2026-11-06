import os,sys,json,hashlib,stat,pathlib,subprocess,time,signal,ctypes,resource,datetime
P=pathlib.Path
ROOT=P('/home/alex/work/pocket4-native-typed-ingress-builder469-native-provider-compile-01-20261106')
SOURCE=ROOT/'builder-source'
ATTEMPT=ROOT/'compile02'
BASE=P('/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106')
MEMORY_MAX=1024**3
SWAP_MAX=0
# Compiler03 used 1 GiB / one CPU. The new 3 GiB fresh-read floor adds
# 2 GiB headroom for this Rust-only attempt; Soong retains its 15 GiB floor.
MIN_AVAILABLE=3*1024**3
TESTS=["android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes","android::tests::restoration_preserves_original_and_removes_created_file","android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch","android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout","android::patch_tests::interrupted_projection_recovers_before_next_build","tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets","tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory","native_role_ingress::tests::observed_lock_passes_normal_schema_and_exact_extension_gate","native_role_ingress::tests::structurally_valid_unobserved_root_is_rejected_before_source_actions","android::tests::typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata","android::tests::typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas","android::tests::typed_shared_provider_projection_keeps_other_root_projection_unchanged","native_role_ingress::tests::provider_extension_rejects_unlisted_path_commit_metadata_or_project_change","native_role_ingress::tests::published_workspace_selects_only_exact_current_or_previous_typed_lock","native_role_ingress::tests::previous_typed_manifest_does_not_bypass_fresh_project_verification","native_role_ingress::tests::native_provider_extension_rejects_missing_or_unpinned_providers"]
def require(c,m):
 if not c:raise RuntimeError(m)
def no_alias(p):
 for x in [p,*p.parents]:
  if x.exists() or x.is_symlink():require(stat.S_ISDIR(x.lstat().st_mode),'non-directory parent: '+str(x))
def read(p,bound):
 no_alias(p.parent);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  a=os.fstat(fd);require(stat.S_ISREG(a.st_mode) and a.st_size<=bound,'file bound: '+str(p))
  with os.fdopen(fd,'rb',closefd=False) as f:b=f.read(bound+1)
  z=os.fstat(fd);n=p.lstat();ident=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  require(len(b)==a.st_size and ident(a)==ident(z)==ident(n),'file changed: '+str(p));return b,stat.S_IMODE(a.st_mode)
 finally:os.close(fd)
def inventory(root):
 out={}
 for here,ds,fs in os.walk(root,followlinks=False):
  for d in ds:require(stat.S_ISDIR((P(here)/d).lstat().st_mode),'directory alias')
  for f in fs:
   p=P(here)/f;b,mode=read(p,2097152);out[str(p.relative_to(root))]={'kind':'file','bytes':len(b),'mode':mode,'sha256':hashlib.sha256(b).hexdigest()}
 return out
def save(p,b,mode=384):
 no_alias(p.parent);fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(),mode)

def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(p,data):
 raw=(json.dumps(data,indent=2)+'\n').encode();no_alias(p.parent);fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,384)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def held_file(p,bound,keep=False):
 b,mode=read(p,bound);s=p.lstat();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'identity':[s.st_dev,s.st_ino,s.st_mode,str(s.st_mtime_ns),str(s.st_ctime_ns)]},b if keep else None
def parse_admission_meminfo(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) <= 16384,
            "fixed meminfo byte bound differs")
    names = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree", "SwapCached"}
    memory = {}
    for line in raw.decode("ascii", "strict").splitlines():
        name, separator, value = line.partition(":")
        if name not in names:
            continue
        require(name not in memory, "duplicate required meminfo field")
        words = value.split()
        require(separator == ":" and len(words) == 2 and words[0].isdigit() and words[1] == "kB",
                "required meminfo field units differ")
        memory[name] = int(words[0]) * 1024
    require(set(memory) == names, "required meminfo fields incomplete")
    require(0 < memory["MemTotal"] and 0 <= memory["MemAvailable"] <= memory["MemTotal"] and
            0 <= memory["SwapFree"] <= memory["SwapTotal"] and memory["SwapCached"] >= 0,
            "required meminfo values inconsistent")
    return memory


def memory_admission(memory, owned):
    require(MEMORY_MAX == 1024**3 and SWAP_MAX == 0 and
            MIN_AVAILABLE - MEMORY_MAX == 2 * 1024**3,
            "one-GiB Rust profile or new two-GiB fresh-admission headroom changed")
    require(owned["memory.max"] == str(MEMORY_MAX) and owned["cpu.max"] == "100000 100000",
            "owned RAM or CPU limit differs before admission")
    require(owned["memory.swap.max"] == "0", "owned swap limit is not zero")
    require(owned["memory.swap.current"] == "0", "existing owned swap is not zero")
    require(memory["MemAvailable"] >= MIN_AVAILABLE,
            "less than 3 GiB MemAvailable for one-GiB zero-swap Rust profile; no automatic retry")
    # Global swap is recorded, never counted as this build's available budget.


def record_resource_admission(cgroup):
    owned = {}
    for name in ("memory.max", "cpu.max", "memory.swap.max", "memory.swap.current"):
        with (cgroup / name).open("r", encoding="ascii") as stream:
            value = stream.read(65)
        require(0 < len(value) <= 64, "owned resource scalar bound differs")
        owned[name] = value.strip()
    with P("/proc/meminfo").open("rb") as stream:
        raw = stream.read(16385)
    require(0 < len(raw) <= 16384, "fixed meminfo byte bound differs")
    receipt = {
        "schema": 1, "state": "OBSERVED_BEFORE_RESOURCE_ADMISSION",
        "observed_utc": utc(), "observed_unix_ns_decimal": str(time.time_ns()),
        "profile": {"memory_max_bytes": MEMORY_MAX, "memory_swap_max_bytes": SWAP_MAX,
                    "minimum_fresh_MemAvailable_bytes": MIN_AVAILABLE,
                    "admission_difference_bytes": MIN_AVAILABLE - MEMORY_MAX,
                    "global_swap_is_owned_budget": False},
        "meminfo": {"path": "/proc/meminfo", "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(), "raw_ascii": raw.decode("ascii", "strict")},
        "owned_cgroup": str(cgroup), "owned_observed": owned,
        "decision_performed": False, "historical_sample_used_for_admission": False,
        "Main_actions": 0, "Android_actions": 0, "production_ready": False}
    path = ATTEMPT / "resource-admission.json"
    save(path, receipt)
    pin, _ = held_file(path, 65536)
    print(json.dumps({"state": "FRESH_RESOURCE_ADMISSION_OBSERVED", "receipt": pin}), flush=True)
    # Persist the exact bounded read before parsing or comparing any resource threshold.
    memory = parse_admission_meminfo(raw)
    memory_admission(memory, owned)
    return memory, owned, pin

def owned_resource_gate(text):
    require(isinstance(text, str), "owned memory.events was not observed")
    rows = [line.split() for line in text.splitlines()]
    require(rows and all(len(row) == 2 and row[1].isdigit() for row in rows),
            "malformed owned memory.events")
    events = {row[0]: int(row[1]) for row in rows}
    require(len(events) == len(rows) and all(name in events for name in ("oom", "oom_kill", "oom_group_kill")),
            "incomplete or duplicate owned memory.events")
    require(events["oom_kill"] == 0 and events["oom_group_kill"] == 0,
            "owned OOM kill observed; build is not qualified")
    return {"pass": True, "events": events, "owned_oom_kills_zero": True}

def subreaper():
    # Only this newly owned controller process is changed.
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    require(libc.prctl(36, 1, 0, 0, 0) == 0, "cannot establish owned-child subreaper")

def child_ids():
    # The controller is single threaded and owns all of its subprocesses.
    require(os.readlink("/proc/self") == str(os.getpid()),
            "controller proc view does not match its PID namespace")
    text = P("/proc/thread-self/children").read_text()
    values = [int(x) for x in text.split()]
    require(len(values) <= 4096 and all(x > 1 for x in values), "unexpected owned child set")
    return values

def cleanup_children():
    records = []
    errors = []
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            children = child_ids()
        except Exception as error:
            return {"complete": False, "children": records,
                    "errors": errors + [{"operation": "enumerate", "error": repr(error)}]}
        if not children:
            return {"complete": not errors, "children": records, "errors": errors}
        for pid in children:
            if time.monotonic() >= deadline:
                break
            fd = -1
            try:
                fd = os.pidfd_open(pid, 0)
                # No other thread/handler reaps a child. A zombie still holds its
                # PID until this exact waitpid; pidfd binds the kernel object.
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL, None, 0)
                except ProcessLookupError:
                    pass
                stop = min(deadline, time.monotonic() + 1)
                status = None
                while time.monotonic() < stop:
                    got, value = os.waitpid(pid, os.WNOHANG)
                    if got == pid:
                        status = value
                        break
                    time.sleep(0.01)
                records.append({"pid": pid, "wait_status": status, "reaped": status is not None})
            except Exception as error:
                errors.append({"pid": pid, "operation": "pidfd_stop_or_wait", "error": repr(error)})
            finally:
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError as error:
                        errors.append({"pid": pid, "operation": "close_pidfd", "error": repr(error)})
        time.sleep(0.01)
    try:
        remaining = child_ids()
    except Exception as error:
        remaining = None
        errors.append({"operation": "final_enumerate", "error": repr(error)})
    return {"complete": remaining == [] and not errors, "children": records,
            "errors": errors, "remaining": remaining}


def hash_pin(p):
 requested=P(p);resolved=requested.resolve(strict=True);no_alias(resolved.parent)
 fd=os.open(resolved,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  a=os.fstat(fd);require(stat.S_ISREG(a.st_mode) and a.st_size<1024**3,'tool file bound')
  h=hashlib.sha256()
  with os.fdopen(fd,'rb',closefd=False) as f:
   while True:
    b=f.read(1024*1024)
    if not b:break
    h.update(b)
  z=os.fstat(fd);ident=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  require(ident(a)==ident(z)==ident(resolved.lstat()) and requested.resolve(strict=True)==resolved,'tool changed')
  return {'path':str(requested),'resolved_path':str(resolved),'bytes':a.st_size,'sha256':h.hexdigest(),'identity':[a.st_dev,a.st_ino,a.st_mode,str(a.st_mtime_ns),str(a.st_ctime_ns)]}
 finally:os.close(fd)
def collect_pins(value,out):
 if isinstance(value,dict):
  path=value.get('requested_path') or value.get('path') or value.get('resolved_path')
  if isinstance(path,str) and path.startswith('/') and isinstance(value.get('bytes'),int) and isinstance(value.get('sha256'),str) and len(value['sha256'])==64:
   row={'bytes':value['bytes'],'sha256':value['sha256'],'resolved_path':value.get('resolved_path') or path}
   require(path not in out or out[path]==row,'inconsistent tool authority');out[path]=row
  for x in value.values():collect_pins(x,out)
 elif isinstance(value,list):
  for x in value:collect_pins(x,out)
def checked_tools(pins):
 observed={}
 for path,row in pins.items():
  require('/.cargo/bin/rustup' not in path,'proxy is not an approved compiler input')
  pin=hash_pin(path);require(pin['bytes']==row['bytes'] and pin['sha256']==row['sha256'] and pin['resolved_path']==row['resolved_path'],'tool differs '+path);observed[path]=pin
 return observed
def command(label,argv,timeout=300):
 stdout=ATTEMPT/(label+'.stdout');stderr=ATTEMPT/(label+'.stderr');start=time.monotonic()
 with stdout.open('xb') as out,stderr.open('xb') as err:
  proc=subprocess.Popen(argv,cwd=SOURCE,env=ENV,stdout=out,stderr=err,start_new_session=True)
  try:rc=proc.wait(timeout=timeout)
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10);raise RuntimeError('command timeout '+label)
 row={'label':label,'argv':argv,'returncode':rc,'seconds':time.monotonic()-start,'stdout':hash_pin(stdout),'stderr':hash_pin(stderr)}
 commands.append(row);print(json.dumps({'event':'COMMAND_COMPLETED','label':label,'returncode':rc}),flush=True)
 require(rc==0,'command failed '+label)
 return stdout.read_text()
require(os.getuid()==1000 and os.geteuid()==1000,'operator uid required');os.umask(63);resource.setrlimit(resource.RLIMIT_CORE,(0,0));no_alias(ROOT)
require(not ATTEMPT.exists(),'fresh compile output required');ATTEMPT.mkdir(mode=448)
commands=[];result={'schema':1,'state':'FAILED_BEFORE_BUILD','Main_actions':0,'Android_actions':0,'Soong_invoked':False,'runtime_authorization_enabled':False,'install_actions':0,'started_utc':utc()}
failure=None;tools_before=None;expected=None;old_expected=None;cgroup=None
try:
 prior_raw,_=read(ROOT/'compile01/result.json',4096);require(hashlib.sha256(prior_raw).hexdigest()=='25db6e954c8f4e15cadcb7122f024349a3d97e10be121646ff051ce9cbef99b4','prior failed result changed')
 prior=json.loads(prior_raw);require(prior['state']=='FAILED' and prior['commands']==[],'prior failure must be settled before cargo')
 result['prior_failed_attempt']={'job_id':'1a1b0607f86-fc05-700f','sha256':'25db6e954c8f4e15cadcb7122f024349a3d97e10be121646ff051ce9cbef99b4','cargo_commands':0,'tests_run':0}
 old_raw,_=read(BASE/'attempt01/result.json',1048576);require(hashlib.sha256(old_raw).hexdigest()=='871e78f7ad8f3f3a12c165297e4fe566d96cfe3a2ce64a0d0010cffdb647b6b8','original Rust profile receipt changed')
 old_profile=json.loads(old_raw)['owned_resource_gate'];require(old_profile['pass'] is True and old_profile['before']['fields']['memory.max']=='1073741824' and old_profile['before']['fields']['cpu.max']=='100000 100000','original Rust profile differs')
 result['profile_authority']={'source':str(BASE/'attempt01/result.json'),'sha256':'871e78f7ad8f3f3a12c165297e4fe566d96cfe3a2ce64a0d0010cffdb647b6b8','memory_max_bytes':1073741824,'cpu_quota_percent':100,'jobs':1,'zero_swap_newly_enforced':True,'fresh_MemAvailable_3GiB_new_for_this_Rust_attempt':True,'full_Soong_profile_changed':False}
 affinity=sorted(os.sched_getaffinity(0));require(len(affinity)>=3,'at least two CPUs must remain free');selected=affinity[-1:];os.sched_setaffinity(0,selected)
 member=P('/proc/self/cgroup').read_text().strip();require(member.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'),'own cgroup required')
 cgroup=P('/sys/fs/cgroup')/member[3:].lstrip('/');unit=cgroup.name
 require(unit.endswith('.service') and str(os.getpid()) in (cgroup/'cgroup.procs').read_text().split(),'own unit identity')
 require((cgroup/'memory.max').read_text().strip()==str(MEMORY_MAX) and (cgroup/'cpu.max').read_text().strip()=='100000 100000','owned budget')
 subprocess.run(['/usr/bin/systemctl','--user','set-property','--runtime',unit,'MemorySwapMax=0'],check=True,capture_output=True,timeout=15)
 memory,owned,admission=record_resource_admission(cgroup);result['resource_admission']=admission;result['cpu_affinity']=selected
 subreaper();require(child_ids()==[],'unexpected owned children')
 raw,_=read(ROOT/'candidate-source-manifest.json',1048576);require(hashlib.sha256(raw).hexdigest()=='d9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934','candidate manifest changed');expected=json.loads(raw)
 require(len(expected)==493 and inventory(SOURCE)==expected,'candidate source changed')
 raw,_=read(BASE/'attempt01/copied-builder-source-manifest.json',1048576);require(hashlib.sha256(raw).hexdigest()=='e06522400f746b62016f82dfd3ec913b39cd9a8f33f9bca4f61a19a2787684ee','baseline authority changed');old_expected=json.loads(raw)
 require(inventory(BASE/'builder-source')==old_expected,'baseline source changed')
 configs=set()
 for p in [SOURCE,*SOURCE.parents,P('/home/alex/.cargo')]:
  for name in ('config','config.toml'):configs.add(p/('.cargo/'+name) if p!=P('/home/alex/.cargo') else p/name)
 require(all(not p.exists() and not p.is_symlink() for p in configs),'new Cargo configuration input')
 raw,_=read(BASE/'attempt01/tool-inputs-before.json',1048576);require(hashlib.sha256(raw).hexdigest()=='323f770a9c227f4e3804f38c2211e78ce46a8031565242d34b6e42ed7f7b2433','tool authority changed')
 pins={};collect_pins(json.loads(raw),pins)
 pins.pop('/home/alex/.cargo/bin/rustup',None)
 rustroot='/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu'
 explicit={'/bin/cargo':(40753664,'9548937d530bf439ff1ba47a3b2bd26eeb9c3aff1961c20c01798613de922578'),'/bin/rustc':(656704,'d32249a7c3bfcfc67b471460386e46323accae7125e344567a12d5664d99bb57'),'/bin/rustdoc':(13173040,'ece7829b8e7448a9d59c88080e2b16253b885c560f792002837901c7f24b7695')}
 for suffix,(count,sha) in explicit.items():
  path=rustroot+suffix;row={'bytes':count,'sha256':sha,'resolved_path':path};require(path not in pins or pins[path]==row,'compiler pin mismatch');pins[path]=row
 require(len(pins)>=10,'compiler/library authority incomplete');tools_before=checked_tools(pins);save(ATTEMPT/'tool-inputs-before.json',tools_before)
 (ATTEMPT/'tmp').mkdir(mode=448);(ATTEMPT/'cargo-target').mkdir(mode=448)
 ENV={'PATH':rustroot+'/bin:/usr/bin:/bin','LANG':'C','LC_ALL':'C','CARGO_HOME':'/home/alex/.cargo','CARGO_TARGET_DIR':str(ATTEMPT/'cargo-target'),'CARGO_NET_OFFLINE':'true','CARGO_BUILD_JOBS':'1','RUSTC':rustroot+'/bin/rustc','RUSTDOC':rustroot+'/bin/rustdoc','CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER':'/usr/bin/cc','RUSTC_WRAPPER':'','RUSTC_WORKSPACE_WRAPPER':'','RUSTFLAGS':'','RUSTDOCFLAGS':'','CARGO_ENCODED_RUSTFLAGS':'','CARGO_ENCODED_RUSTDOCFLAGS':'','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1','GIT_OPTIONAL_LOCKS':'0','TMPDIR':str(ATTEMPT/'tmp')}
 version=command('rust-version',[rustroot+'/bin/rustc','-Vv'],20);require('release: 1.93.0\n' in version,'Rust version differs')
 cargo=rustroot+'/bin/cargo';command('build',[cargo,'build','--offline','--locked','-j','1','-p','droidloom-update','--bin','droidloom-update','--message-format=json-render-diagnostics'],450)
 output=command('test-compile',[cargo,'test','--offline','--locked','-j','1','-p','droidloom-update','--bin','droidloom-update','--no-run','--message-format=json-render-diagnostics'],300)
 artifacts=[json.loads(line) for line in output.splitlines() if line.startswith('{')]
 executables=[x['executable'] for x in artifacts if x.get('reason')=='compiler-artifact' and x.get('target',{}).get('name')=='droidloom-update' and x.get('profile',{}).get('test') and x.get('executable')]
 require(len(executables)==1,'one actual test executable required');test=P(executables[0]);require(test.is_relative_to(ATTEMPT/'cargo-target'),'test executable escaped owned target')
 listed=command('test-list',[str(test),'--list'],20);names=[line[:-6] for line in listed.splitlines() if line.endswith(': test')]
 require(len(names)==206 and set(TESTS)<=set(names),'actual registered test scope differs')
 for index,name in enumerate(TESTS):
  output=command('focused-%02d'%index,[str(test),'--exact',name,'--nocapture'],30)
  require('test result: ok. 1 passed;' in output,'exact test did not run once')
 result.update({'state':'RUST_BUILD_AND_FOCUSED_TESTS_PASS','tests_passed':len(TESTS),'test_names':TESTS,'registered_tests':len(names),'builder':hash_pin(ATTEMPT/'cargo-target/debug/droidloom-update'),'test_executable':hash_pin(test),'build_environment':ENV,'source_manifest_sha256':'d9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934','source_files':493,'new_project_count':225,'full_Android_Java_JNI_compiled':False})
except BaseException as error:
 failure=repr(error);result['state']='FAILED';result['error']=failure
finally:
 try:
  cleanup=cleanup_children();result['cleanup']=cleanup
  require(cleanup.get('complete') is True,'owned child cleanup incomplete')
  if expected is not None:require(inventory(SOURCE)==expected,'candidate source changed after build');result['candidate_source_unchanged_after']=True
  if old_expected is not None:require(inventory(BASE/'builder-source')==old_expected,'baseline source changed after build');result['baseline_source_unchanged_after']=True
  if tools_before is not None:require(checked_tools(pins)==tools_before,'compiler input identity changed');result['tool_inputs_unchanged_after']=True
  if cgroup is not None:
   result['memory_events']=(cgroup/'memory.events').read_text();result['owned_resource_gate']=owned_resource_gate(result['memory_events'])
   result['memory_peak']=(cgroup/'memory.peak').read_text().strip();result['swap_peak']=(cgroup/'memory.swap.peak').read_text().strip()
   require((cgroup/'memory.swap.max').read_text().strip()=='0' and (cgroup/'memory.swap.current').read_text().strip()=='0','zero swap after')
 except BaseException as error:
  result['state']='FAILED';result['finalization_error']=repr(error);failure=failure or repr(error)
 result['commands']=commands;result['finished_utc']=utc();save(ATTEMPT/'result.json',result)
 print(json.dumps({'state':result['state'],'error':result.get('error'),'finalization_error':result.get('finalization_error'),'tests_passed':result.get('tests_passed',0),'result':hash_pin(ATTEMPT/'result.json')}),flush=True)
if failure:sys.exit(1)
