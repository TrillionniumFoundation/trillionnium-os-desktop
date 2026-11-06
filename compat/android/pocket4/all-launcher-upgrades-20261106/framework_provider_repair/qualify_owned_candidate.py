import os,sys,json,hashlib,stat,pathlib,subprocess,time,signal,ctypes,resource,datetime
P=pathlib.Path
ROOT=P('/home/alex/work/pocket4-native-typed-ingress-builder469-native-provider-compile-01-20261106')
SOURCE=ROOT/'builder-source'
ATTEMPT=ROOT/'qualify01'
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



Path=P
COPIED=SOURCE
OUT=ATTEMPT
FAKEROOT_TEST='native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata'
def sha(value):return hashlib.sha256(value).hexdigest()
def pinned_json(path,digest,maximum):
 raw,pin=held(path,maximum);require(pin['sha256']==digest,'authority digest changed: '+str(path));return json.loads(raw),pin
def command(argv,cwd,environment,label,records,maximum_seconds=30):
 require(child_ids()==[],'unexpected child before focused command')
 start=time.monotonic();stdout=OUT/(label+'.stdout');stderr=OUT/(label+'.stderr')
 with stdout.open('xb') as out,stderr.open('xb') as err:
  proc=subprocess.Popen(argv,cwd=cwd,env=environment,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
  try:rc=proc.wait(timeout=maximum_seconds)
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
   raise RuntimeError('focused command timed out: '+label)
 raw,out_pin=held(stdout,32*1024*1024);_,err_pin=held(stderr,4*1024*1024)
 row={'label':label,'argv':argv,'cwd':str(cwd),'returncode':rc,'timed_out':False,'seconds':time.monotonic()-start,'stdout':out_pin,'stderr':err_pin}
 records.append(row)
 require(rc==0 and child_ids()==[],'focused command failed or left a child')
 print(json.dumps({'event':'FOCUSED_COMMAND_COMPLETED','label':label,'returncode':rc}),flush=True)
 return raw

require(os.getuid()==1000 and os.geteuid()==1000,'unprivileged operator required')
os.umask(63);resource.setrlimit(resource.RLIMIT_CORE,(0,0));no_alias(ROOT)
require(not ATTEMPT.exists(),'qualification output must be fresh');ATTEMPT.mkdir(mode=448)
result={'schema':1,'state':'FAILED','scope':'builder469 actual compile02 qualification supplement; no Cargo rebuild or Android build',
 'Main_actions':0,'Android_actions':0,'install_actions':0,'Soong_invoked':False,'cargo_commands':0,
 'runtime_authorization_enabled':False,'production_ready':False,'started_utc':utc()}
records=[];failure=None;baseline=None;candidate=None;dependencies=None;test_pin=None;builder_pin=None;tools_before=None;cgroup=None
try:
 compile_result,compile_pin=pinned_json(ROOT/'compile02/result.json','a14dde5d3a2e85fe44d90c651527c8c8402d341403ef84a7bc92b93252de72b9',1048576)
 require(compile_result['state']=='RUST_BUILD_AND_FOCUSED_TESTS_PASS' and compile_result['tests_passed']==16 and compile_result['registered_tests']==206 and compile_result['test_names']==TESTS and len(compile_result['commands'])==20 and all(c['returncode']==0 for c in compile_result['commands']),'actual compile02 result differs')
 require(all(compile_result[k] is True for k in ('candidate_source_unchanged_after','baseline_source_unchanged_after','tool_inputs_unchanged_after')) and compile_result['cleanup']['complete'] is True and compile_result['cleanup']['children']==[] and compile_result['cleanup']['errors']==[] and compile_result['owned_resource_gate']['pass'] is True and compile_result['swap_peak']=='0','actual compile02 final source/resource/child qualification differs')
 require(all(compile_result['owned_resource_gate']['events'][k]==0 for k in ('oom','oom_kill','oom_group_kill')),'actual compile02 OOM event')
 result['actual_compile02']=compile_pin;result['actual_compile02_job_id']='1a1b063d4cc-fc05-702e'
 old_result,old_result_pin=pinned_json(BASE/'attempt01/result.json','871e78f7ad8f3f3a12c165297e4fe566d96cfe3a2ce64a0d0010cffdb647b6b8',1048576)
 require(old_result['state']=='PASS' and old_result['focused_tests_passed']==24 and old_result['source_resume_tests_passed']==9 and old_result['source_actual_registered_test_count']==20 and old_result['source_test_fixtures_network_disabled'] is True,'actual unchanged droidloom-source parent authority differs')
 result['original_compiler03_authority']=old_result_pin
 affinity=sorted(os.sched_getaffinity(0));require(len(affinity)>=3,'at least two logical CPUs must remain free');os.sched_setaffinity(0,affinity[-1:]);result['cpu_affinity']=affinity[-1:]
 member=P('/proc/self/cgroup').read_text().strip();require(member.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'),'own cgroup required')
 cgroup=P('/sys/fs/cgroup')/member[3:].lstrip('/');unit=cgroup.name
 require(unit.endswith('.service') and str(os.getpid()) in (cgroup/'cgroup.procs').read_text().split(),'own unit identity')
 require((cgroup/'memory.max').read_text().strip()==str(MEMORY_MAX) and (cgroup/'cpu.max').read_text().strip()=='100000 100000','owned Rust qualification budget')
 subprocess.run(['/usr/bin/systemctl','--user','set-property','--runtime',unit,'MemorySwapMax=0'],check=True,capture_output=True,timeout=15)
 memory,owned,admission=record_resource_admission(cgroup);result['resource_admission']=admission
 subreaper();require(child_ids()==[],'unexpected owned child')
 candidate,candidate_pin=pinned_json(ROOT/'candidate-source-manifest.json','d9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934',1048576)
 baseline,baseline_pin=pinned_json(BASE/'attempt01/copied-builder-source-manifest.json','e06522400f746b62016f82dfd3ec913b39cd9a8f33f9bca4f61a19a2787684ee',1048576)
 require(len(candidate)==493 and len(baseline)==491 and inventory(SOURCE)==candidate and inventory(BASE/'builder-source')==baseline,'exact copied/baseline source map differs')
 changed=sorted(p for p in baseline if candidate.get(p)!=baseline[p])
 added=sorted(set(candidate)-set(baseline))
 require(changed==['tools/droidloom-update/src/android.rs','tools/droidloom-update/src/native_role_ingress.rs'] and added==['android/manifest/m2-role-ingress-provider2-source-lock.json','android/native-role-ingress/provider-fixtures/neuralnetworks-common.Android.bp'] and set(baseline)<=set(candidate),'exact four-file delta differs')
 result['candidate_manifest']=candidate_pin;result['baseline_manifest']=baseline_pin;result['source_delta']={'unchanged_existing':489,'changed_existing':changed,'added':added,'actual_source_file_count':493}
 candidate_rows={name:hash_held(SOURCE/name) for name in candidate}
 dependency_document,dependency_pin=pinned_json(BASE/'attempt01/dependency-inputs-before.json','34ab55489959d957294dcc25a93083346dffec934c96768c515d584bb91731c7',2*1024*1024)
 dependencies=dependency_document['files'];packages=dependency_document['packages']
 require(0<len(dependencies)<=16384 and len(packages)==49 and sum(p['kind']=='offline-registry' for p in packages)==45,'parent dependency source closure count differs')
 for name,row in dependencies.items():
  path=P(name);require(path.is_absolute() and str(path)==row['path'] and path.is_relative_to(P('/home/alex/.cargo/registry')),'dependency path escaped qualified registry')
  no_alias(path.parent);require(hash_held(path)==row,'registry archive/source bytes or full stat identity changed across compile03 and compile02: '+name)
 remapped=json.loads(json.dumps(packages).replace(str(BASE/'builder-source'),str(SOURCE)))
 require(sum(p['kind']=='pinned-builder-source' for p in remapped)==4,'workspace source package count differs')
 logs={}
 for label in ('build','test-compile'):
  item=next(c for c in compile_result['commands'] if c['label']==label)
  require(P(item['stdout']['path']).parent==ROOT/'compile02' and hash_pin(item['stdout']['path'])==item['stdout'],'actual compile command log identity differs')
  raw,_=held(P(item['stdout']['path']),32*1024*1024)
  logs[label]=qualify_compiler_inputs(raw,remapped,dependencies,candidate_rows)
 expected_packages=sorted(p['id'] for p in remapped)
 require(logs['build']==logs['test-compile']==expected_packages and len(expected_packages)==49,'actual build/test package closure differs')
 result['dependency_continuity']={'authority':dependency_pin,'all_bytes_and_full_stat_identities_equal':True,'recorded_files_and_archives':len(dependencies),'selected_packages':49,'registry_packages':45,'actual_build_packages':logs['build'],'actual_test_compile_packages':logs['test-compile'],'new_dependency_fetches':0,'proof_interval':'actual compiler03 pre-build inventory through current supplement after compile02'}
 configs=set()
 for p in [SOURCE,*SOURCE.parents,P('/home/alex/.cargo')]:
  for name in ('config','config.toml'):configs.add(p/('.cargo/'+name) if p!=P('/home/alex/.cargo') else p/name)
 require(all(not p.exists() and not p.is_symlink() for p in configs),'Cargo configuration appeared after compile02')
 result['cargo_configs_absent_after']=sorted(str(p) for p in configs)
 raw,_=read(ROOT/'compile02/tool-inputs-before.json',1048576);tools_before=json.loads(raw)
 parent_tools,parent_tools_pin=pinned_json(BASE/'attempt01/tool-inputs-before.json','323f770a9c227f4e3804f38c2211e78ce46a8031565242d34b6e42ed7f7b2433',1048576)
 authority={};collect_pins(parent_tools,authority);authority.pop('/home/alex/.cargo/bin/rustup',None)
 require(set(authority)<=set(tools_before),'actual compiler inputs missing parent tool closure')
 for name,row in authority.items():
  require(tools_before[name]['bytes']==row['bytes'] and tools_before[name]['sha256']==row['sha256'] and tools_before[name]['resolved_path']==row['resolved_path'],'compile02 tool differs from parent authority')
 for name,row in tools_before.items():require(hash_pin(name)==row,'actual compile02 tool identity changed')
 result['tool_continuity']={'authority':parent_tools_pin,'actual_compile02_before_pin':hash_held(ROOT/'compile02/tool-inputs-before.json'),'tool_count':len(tools_before),'all_current_equal_compile02_before':True,'rustup_proxy_executed':False}
 builder_pin=compile_result['builder'];test_pin=compile_result['test_executable']
 require(hash_pin(builder_pin['path'])==builder_pin and hash_pin(test_pin['path'])==test_pin and P(builder_pin['path']).is_relative_to(ROOT/'compile02/cargo-target') and P(test_pin['path']).is_relative_to(ROOT/'compile02/cargo-target'),'actual compiler outputs changed or escaped owned directory')
 result['builder']=builder_pin;result['test_executable']=test_pin
 (ATTEMPT/'tmp').mkdir(mode=448)
 ENV=dict(compile_result['build_environment']);ENV['TMPDIR']=str(ATTEMPT/'tmp')
 require('HOME' not in ENV and ENV['CARGO_NET_OFFLINE']=='true' and ENV['RUSTC'].endswith('/1.93.0-x86_64-unknown-linux-gnu/bin/rustc'),'actual compiler environment scope changed')
 listed=command([test_pin['path'],'--list'],COPIED,ENV,'test-list',records,20).decode()
 names=[line[:-6] for line in listed.splitlines() if line.endswith(': test')]
 require(len(names)==206 and len(set(names))==206 and set(TESTS)<=set(names),'actual registered test closure changed')
 gates=[]
 for index,name in enumerate(TESTS):gates.append(focused_test(P(test_pin['path']),name,index,206,ENV,records))
 result['independent_result_gates']=gates;result['tests_passed']=len(gates);result['registered_tests']=206;result['expected_test_names']=TESTS
 result['unchanged_source_resume_controls']={'inherited_authority':old_result_pin,'source_files_unchanged':True,'historically_passed':9,'rerun_in_this_supplement':False,'historical_registered_count':20,'names':old_result['expected_source_resume_test_names'],'scope':'unchanged droidloom-source and source-resume library; new provider-lock controls are current builder469 tests'}
 result['state']='ACTUAL_COMPILE02_INPUT_CONTINUITY_AND_16_INDEPENDENT_TESTS_PASS'
except BaseException as error:
 failure=repr(error);result['state']='FAILED';result['error']=failure
finally:
 try:
  result['cleanup']=cleanup_children();require(result['cleanup']['complete'] is True and result['cleanup']['children']==[] and not result['cleanup']['errors'],'qualification left children')
  if candidate is not None:require(inventory(SOURCE)==candidate,'candidate source changed after supplement');result['candidate_source_unchanged_after']=True
  if baseline is not None:require(inventory(BASE/'builder-source')==baseline,'original builder source changed after supplement');result['original_source_unchanged_after']=True
  if dependencies is not None:
   for name,row in dependencies.items():require(hash_held(P(name))==row,'dependency changed during supplement: '+name)
   result['dependency_changes']=[]
  if tools_before is not None:
   for name,row in tools_before.items():require(hash_pin(name)==row,'compiler tool changed during supplement: '+name)
   result['tool_changes']=[]
  if test_pin is not None:require(hash_pin(test_pin['path'])==test_pin and hash_pin(builder_pin['path'])==builder_pin,'actual compiler ELF changed during supplement')
  if cgroup is not None:
   result['memory_events']=(cgroup/'memory.events').read_text();result['owned_resource_gate']=owned_resource_gate(result['memory_events'])
   require(all(result['owned_resource_gate']['events'][k]==0 for k in ('oom','oom_kill','oom_group_kill')),'owned OOM event')
   result['memory_peak']=(cgroup/'memory.peak').read_text().strip();result['swap_peak']=(cgroup/'memory.swap.peak').read_text().strip()
   require((cgroup/'memory.swap.max').read_text().strip()=='0' and (cgroup/'memory.swap.current').read_text().strip()=='0' and result['swap_peak']=='0','owned zero-swap qualification differs')
 except BaseException as error:
  failure=failure or repr(error);result['state']='FAILED';result['finalization_error']=repr(error)
 result['commands']=records;result['finished_utc']=utc();save(ATTEMPT/'result.json',result)
 print(json.dumps({'state':result['state'],'error':result.get('error'),'finalization_error':result.get('finalization_error'),'tests_passed':result.get('tests_passed',0),'result':hash_pin(ATTEMPT/'result.json')}),flush=True)
if failure:sys.exit(1)

