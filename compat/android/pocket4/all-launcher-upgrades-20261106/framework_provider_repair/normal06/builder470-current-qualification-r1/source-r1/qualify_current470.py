import os,sys,json,hashlib,stat,pathlib,subprocess,time,signal,resource,datetime,re,errno,fcntl
P = Path = pathlib.Path
ROOT = P('/home/alex/work/pocket4-builder470-explicit-current-qualification-01-20261106')
ACTIVE = P('/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106')
SOURCE = COPIED = ACTIVE / "builder-source"
ATTEMPT = OUT = ROOT / "qualify01"
PROFILE_BASE = P('/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106')
BUILD_RESULT = ACTIVE / "compile01/result.json"
MEMORY_MAX = 1073741824
SWAP_MAX = 0
MIN_AVAILABLE = 3221225472
TESTS = ['android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes',
 'android::tests::restoration_preserves_original_and_removes_created_file',
 'android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch',
 'android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout',
 'android::patch_tests::interrupted_projection_recovers_before_next_build',
 'tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets',
 'tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory',
 'native_role_ingress::tests::observed_lock_passes_normal_schema_and_exact_extension_gate',
 'native_role_ingress::tests::structurally_valid_unobserved_root_is_rejected_before_source_actions',
 'android::tests::typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata',
 'android::tests::typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas',
 'android::tests::typed_shared_provider_projection_keeps_other_root_projection_unchanged',
 'native_role_ingress::tests::provider_extension_rejects_unlisted_path_commit_metadata_or_project_change',
 'native_role_ingress::tests::published_workspace_selects_only_exact_current_or_previous_typed_lock',
 'native_role_ingress::tests::previous_typed_manifest_does_not_bypass_fresh_project_verification',
 'native_role_ingress::tests::native_provider_extension_rejects_missing_or_unpinned_providers',
 'android::tests::typed_systemui_defaults_preserve_real_consumers_and_dependency_edges',
 'android::tests::typed_systemui_projection_preserves_loaded_ordinary_dependencies',
 'native_role_ingress::tests::systemui_extension_rejects_missing_provider_wrong_revision_or_scope']
EXPECTED_TESTS = ['android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes',
 'android::tests::restoration_preserves_original_and_removes_created_file',
 'android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch',
 'android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout',
 'android::patch_tests::interrupted_projection_recovers_before_next_build',
 'tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets',
 'tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory',
 'native_role_ingress::tests::observed_lock_passes_normal_schema_and_exact_extension_gate',
 'native_role_ingress::tests::structurally_valid_unobserved_root_is_rejected_before_source_actions',
 'android::tests::typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata',
 'android::tests::typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas',
 'android::tests::typed_shared_provider_projection_keeps_other_root_projection_unchanged',
 'native_role_ingress::tests::provider_extension_rejects_unlisted_path_commit_metadata_or_project_change',
 'native_role_ingress::tests::published_workspace_selects_only_exact_current_or_previous_typed_lock',
 'native_role_ingress::tests::previous_typed_manifest_does_not_bypass_fresh_project_verification',
 'native_role_ingress::tests::native_provider_extension_rejects_missing_or_unpinned_providers',
 'android::tests::typed_systemui_defaults_preserve_real_consumers_and_dependency_edges',
 'android::tests::typed_systemui_projection_preserves_loaded_ordinary_dependencies',
 'native_role_ingress::tests::systemui_extension_rejects_missing_provider_wrong_revision_or_scope']
SOURCE_TESTS = ['resume::tests::completed_project_reuse_has_no_fetch_or_checkout_and_publishes_only_after_verify',
 'resume::tests::initial_checkout_reuses_cached_commit_and_preserves_interrupted_index_lock',
 'resume::tests::nonempty_interrupted_index_lock_is_preserved_in_place_and_rejected',
 'resume::tests::dirty_completed_project_keeps_original_bytes_and_never_gets_manifest',
 'resume::tests::conflicting_untracked_partial_file_is_not_forced_or_removed',
 'resume::tests::wrong_origin_is_rejected_before_any_fetch_or_checkout',
 'resume::tests::recovered_parent_symlink_cannot_create_a_project_outside_staging',
 'resume::tests::mismatched_staging_manifest_is_preserved_and_not_published',
 'resume::tests::sparse_parent_normalization_keeps_exact_locked_selection']
EXPECTED_REGISTERED_TESTS = 209
EXPECTED_FRESH_LABELS = ['rust-version',
 'current-builder-help',
 'current-typed-ingress-help',
 'updater-test-list',
 'projection-test-0',
 'projection-test-1',
 'projection-test-2',
 'projection-test-3',
 'projection-test-4',
 'projection-test-5',
 'projection-test-6',
 'projection-test-7',
 'projection-test-8',
 'projection-test-9',
 'projection-test-10',
 'projection-test-11',
 'projection-test-12',
 'projection-test-13',
 'projection-test-14',
 'projection-test-15',
 'projection-test-16',
 'projection-test-17',
 'projection-test-18',
 'source-resume-test-compile',
 'source-resume-test-list',
 'projection-test-100',
 'projection-test-101',
 'projection-test-102',
 'projection-test-103',
 'projection-test-104',
 'projection-test-105',
 'projection-test-106',
 'projection-test-107',
 'projection-test-108']
EXPECTED_COMPILE_LABELS = ['rust-version',
 'build',
 'test-compile',
 'test-list',
 'projection-test-0',
 'projection-test-1',
 'projection-test-2',
 'projection-test-3',
 'projection-test-4',
 'projection-test-5',
 'projection-test-6',
 'projection-test-7',
 'projection-test-8',
 'projection-test-9',
 'projection-test-10',
 'projection-test-11',
 'projection-test-12',
 'projection-test-13',
 'projection-test-14',
 'projection-test-15',
 'projection-test-16',
 'projection-test-17',
 'projection-test-18']
EXPECTED_SOURCE_DELTA = {'actual_source_file_count': 498,
 'added': ['android/manifest/m2-role-ingress-provider3-source-lock.json',
           'android/native-role-ingress/provider-fixtures/SystemUI-pods-build.Android.bp',
           'android/native-role-ingress/provider-fixtures/SystemUI-pods-policy.Android.bp',
           'android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp',
           'android/native-role-ingress/provider-fixtures/WindowManager-Shell.Android.bp'],
 'changed_existing': ['tools/droidloom-update/src/android.rs',
                      'tools/droidloom-update/src/native_role_ingress.rs'],
 'unchanged_existing': 491}
SOURCE_MANIFEST_SHA = 'f4a0e6ff82f1ecf9bd786872d99cc0b1608e1d94d0adc37761e87aed449c81bd'
EXPECTED_MANIFEST_SHA = 'f4a0e6ff82f1ecf9bd786872d99cc0b1608e1d94d0adc37761e87aed449c81bd'
FAKEROOT_TEST = 'native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata'
EXPLICIT_RUST_TOOLS = [('/bin/cargo', 40753664, '9548937d530bf439ff1ba47a3b2bd26eeb9c3aff1961c20c01798613de922578'),
 ('/bin/rustc', 656704, 'd32249a7c3bfcfc67b471460386e46323accae7125e344567a12d5664d99bb57'),
 ('/bin/rustdoc', 13173040, 'ece7829b8e7448a9d59c88080e2b16253b885c560f792002837901c7f24b7695')]
LIBFFI = {'bytes': 64184,
 'identity': [66306, 108020388, 33188, 64184, 1774599998000000000, 1791083436303902806],
 'path': '/usr/lib/x86_64-linux-gnu/libffi.so.8.2.0',
 'sha256': '1a0dc86f787f73e025a6e521056360afcbe70f2a82cd808132fefc2b4ee95daa'}
AUTHORITIES = {'current470-resource-admission': {'bytes': 2746,
                                   'path': '/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106/compile01/resource-admission.json',
                                   'sha256': '5b4b728f90ee088141d2cd9aaa7e242ef33e58b355c790422ed858930c926031'},
 'current470-result': {'bytes': 76136,
                       'path': '/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106/compile01/result.json',
                       'sha256': '6599026ebe5071ecdd5f0e2d962eb96cc791041be0dee9fd59a402735a6387d8'},
 'current470-tool-inputs': {'bytes': 38712,
                            'identity': [66306,
                                         38436520,
                                         33152,
                                         38712,
                                         1793985117029124108,
                                         1793985117029124108],
                            'path': '/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106/compile01/tool-inputs-before.json',
                            'sha256': '9c0a2fef8ef04bb26ba65c01354d612d47e16e6e4361e423c007640acef62383'},
 'current498-manifest': {'bytes': 99075,
                         'path': '/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106/candidate-source-manifest.json',
                         'sha256': 'f4a0e6ff82f1ecf9bd786872d99cc0b1608e1d94d0adc37761e87aed449c81bd'},
 'dependency-inputs': {'bytes': 1376033,
                       'path': '/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106/attempt01/dependency-inputs-before.json',
                       'sha256': '34ab55489959d957294dcc25a93083346dffec934c96768c515d584bb91731c7'},
 'legacy468-result': {'bytes': 161423,
                      'path': '/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106/attempt01/result.json',
                      'sha256': '871e78f7ad8f3f3a12c165297e4fe566d96cfe3a2ce64a0d0010cffdb647b6b8'},
 'legacy469-qualification': {'bytes': 65386,
                             'path': '/home/alex/work/pocket4-native-typed-ingress-builder469-native-provider-compile-01-20261106/qualify02/result.json',
                             'sha256': 'f31bb31d29967bacdb0842eea99dae65f8b67425f26f10063c3d84099367fd64'},
 'legacy469-result': {'bytes': 37384,
                      'path': '/home/alex/work/pocket4-native-typed-ingress-builder469-native-provider-compile-01-20261106/compile02/result.json',
                      'sha256': 'a14dde5d3a2e85fe44d90c651527c8c8402d341403ef84a7bc92b93252de72b9'},
 'legacy491-manifest': {'bytes': 97525,
                        'path': '/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106/attempt01/copied-builder-source-manifest.json',
                        'sha256': 'e06522400f746b62016f82dfd3ec913b39cd9a8f33f9bca4f61a19a2787684ee'},
 'legacy493-manifest': {'bytes': 97964,
                        'path': '/home/alex/work/pocket4-native-typed-ingress-builder469-native-provider-compile-01-20261106/candidate-source-manifest.json',
                        'sha256': 'd9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934'},
 'tool-inputs': {'bytes': 41106,
                 'identity': [66306, 35833111, 33152, 41106, 1793944381937098438, 1793944381937098438],
                 'path': '/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106/attempt01/tool-inputs-before.json',
                 'sha256': '323f770a9c227f4e3804f38c2211e78ce46a8031565242d34b6e42ed7f7b2433'}}
EXPECTED_GATES = ['actual_current_470_compile_receipt_and_19_original_gates',
 'all2706_registry_files_and49_package_inputs_qualified',
 'all70_tools_and_explicit_Rust1_93_and_no_Cargo_config',
 'all_bound_inputs_and_owners_unchanged_after',
 'complete498_source_and_exact491_493_498_ancestry',
 'current_CLI_help_and19_updater_independent_tests',
 'exact242_project_lock_and_private_offline_resume_fixture_source',
 'exact34_fresh_commands_and28_independent_tests',
 'exact_stdio_and_prequalified_library_FD_set',
 'existing470_ELF_and_test_exact_original_identity_owner_and_SHA',
 'fresh_3GiB_and_owned_1GiB_1CPU_zero_swap',
 'fresh_current_source_resume_compile_and9_independent_tests',
 'original23_command_outputs_and19_independent_logs_revalidated',
 'owned_no_OOM_and_zero_swap',
 'strict_no_residual_owned_children']

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

def qualify_builder470_receipt(result):
    # This checks the pinned actual receipt. It does not compile or run tests.
    require(result['state'] == 'RUST_BUILD_AND_19_INDEPENDENT_FOCUSED_TESTS_PASS' and
            result['test_names'] == EXPECTED_TESTS and result['tests_passed'] == 19 and
            result['registered_tests'] == 209 and result['source_files'] == 498 and
            result['new_project_count'] == 242 and
            result['source_manifest_sha256'] == SOURCE_MANIFEST_SHA,
            'actual builder470 result/source/test closure differs')
    require([row['label'] for row in result['commands']] == EXPECTED_COMPILE_LABELS and
            all(row['returncode'] == 0 and row['timed_out'] is False for row in result['commands']) and
            len(result['independent_result_gates']) == 19,
            'actual builder470 command or independent gate closure differs')
    require(all(result[key] is True for key in ['candidate_source_unchanged_after',
                'baseline_source_unchanged_after', 'registry_input_bytes_and_full_identities_unchanged_after',
                'tool_inputs_unchanged_after']) and
            result['cleanup'] == {'complete': True, 'children': [], 'errors': []} and
            result['owned_resource_gate']['pass'] is True and
            all(result['owned_resource_gate']['events'][key] == 0 for key in ['oom', 'oom_kill', 'oom_group_kill']) and
            result['memory_peak'] == '1073741824' and result['owned_resource_gate']['events']['max'] == 657 and
            result['swap_peak'] == '0' and result['Soong_invoked'] is False and
            result['full_Android_Java_JNI_compiled'] is False and
            result['runtime_authorization_enabled'] is False and result['production_ready'] is False and
            result['Main_actions'] == result['Android_actions'] == result['install_actions'] == 0 and
            'HOME' not in result['build_environment'] and
            result['build_environment']['CARGO_NET_OFFLINE'] == 'true' and
            result['build_environment']['CARGO_BUILD_JOBS'] == '1',
            'actual builder470 source/resource/child/scope qualification differs')
    for index, name in enumerate(EXPECTED_TESTS):
        row = result['commands'][index + 4]
        log_path = BUILD_RESULT.parent / ('projection-test-' + str(index) + '.libtest')
        expected_log = ('ok ' + name + '\n').encode()
        gate = {'exact_name': name, 'expected_stdout_runs': 1, 'filtered_out_per_run': 208,
                'outer_results': 1, 'registered_tests': 209, 'summary_and_independent_result_agree': True}
        require(row['argv'] == [result['test_executable']['path'], '--exact', name,
                '--test-threads=1', '--nocapture', '--logfile', str(log_path)] and
                row['focused_result_gate'] == result['independent_result_gates'][index] == gate and
                row['independent_libtest_result']['path'] == str(log_path) and
                row['independent_libtest_result']['bytes'] == len(expected_log) and
                row['independent_libtest_result']['sha256'] == hashlib.sha256(expected_log).hexdigest(),
                'actual builder470 independent exact test differs: ' + name)
    continuity = result['dependency_continuity']
    require(continuity['all_source_bytes_and_full_identities_equal_before'] is True and
            continuity['recorded_files_and_archives'] == 2706 and continuity['selected_packages'] == 49 and
            continuity['registry_packages'] == 45 and continuity['new_dependency_fetches'] == 0 and
            len(continuity['actual_build_packages']) == len(set(continuity['actual_build_packages'])) == 49 and
            continuity['actual_build_packages'] == continuity['actual_test_compile_packages'] and
            result['source_delta'] == EXPECTED_SOURCE_DELTA,
            'actual builder470 dependency or seven-file successor differs')

def failure_detail(error, phase):
    frames = []
    trace = error.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        frames.append({'file': code.co_filename, 'function': code.co_name, 'line': trace.tb_lineno})
        trace = trace.tb_next
    return {'phase': phase, 'type': type(error).__name__, 'repr': repr(error),
        'errno': getattr(error, 'errno', None),
        'filename': str(error.filename) if getattr(error, 'filename', None) is not None else None,
        'frames': frames[:64]}


def owner_identity(path, owner=1000):
    path = P(path)
    no_alias(path.parent)
    value = path.lstat()
    require(stat.S_ISREG(value.st_mode) and value.st_uid == owner and value.st_gid == owner and
            not value.st_mode & 0o6002, 'owned regular input required: ' + str(path))
    return {'path': str(path), 'uid': value.st_uid, 'gid': value.st_gid,
        'nlink': value.st_nlink, 'identity': identity(value)}


def authority(name, observations):
    expected = AUTHORITIES[name]
    path = P(expected['path'])
    document, observed = pinned_json(path, expected['sha256'], expected['bytes'])
    require(observed['bytes'] == expected['bytes'] and
            ('identity' not in expected or observed['identity'] == expected['identity']),
            'authority byte count or exact original identity differs: ' + name)
    observations[name] = {'pin': observed, 'owner': owner_identity(path)}
    return document


def source_observation(manifest):
    no_alias(SOURCE)
    root = SOURCE.lstat()
    require(stat.S_ISDIR(root.st_mode) and root.st_uid == root.st_gid == 1000 and
            not root.st_mode & 0o002, 'current source directory owner differs')
    require(inventory(SOURCE) == manifest, 'complete current 498-file map differs')
    files = {}
    for name in sorted(manifest):
        path = SOURCE / name
        files[name] = {'pin': hash_held(path), 'owner': owner_identity(path)}
    directories = {}
    for here, names, unused in os.walk(SOURCE, followlinks=False):
        for path in [P(here), *(P(here) / name for name in names)]:
            info = path.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 1000 and
                    not info.st_mode & 0o002, 'current source directory identity differs')
            directories[str(path.relative_to(SOURCE))] = {
                'identity': identity(info), 'uid': info.st_uid, 'gid': info.st_gid, 'nlink': info.st_nlink}
    return {'files': files, 'directories': directories}


def current_artifact(row, path):
    require(row['path'] == row['resolved_path'] == str(path), 'exact current artifact path required')
    observed = hash_pin(path)
    require(observed == row and observed['identity'][2] & 0o111,
            'existing qualified builder470 artifact identity or bytes changed')
    return {'pin': observed, 'owner': owner_identity(path)}


def verify_source_ancestry(old491, old493, current):
    require(len(old491) == 491 and len(old493) == 493 and len(current) == 498,
            'closed source ancestry counts differ')
    expected_changed = ['tools/droidloom-update/src/android.rs', 'tools/droidloom-update/src/native_role_ingress.rs']
    changes = []
    for label, earlier, later, added in [
        ('491-to-493', old491, old493, [
            'android/manifest/m2-role-ingress-provider2-source-lock.json',
            'android/native-role-ingress/provider-fixtures/neuralnetworks-common.Android.bp']),
        ('493-to-498', old493, current, EXPECTED_SOURCE_DELTA['added']),
    ]:
        changed = sorted(name for name in earlier if later.get(name) != earlier[name])
        observed_added = sorted(set(later) - set(earlier))
        require(set(earlier) <= set(later) and changed == expected_changed and observed_added == added,
                'exact retained source ancestry differs: ' + label)
        changes.append({'stage': label, 'changed': changed, 'added': observed_added,
                        'removed': [], 'unchanged_count': len(earlier) - len(changed)})
    unchanged = [name for name in current if name.startswith('tools/droidloom-source/')]
    unchanged += ['Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml']
    require(len(set(unchanged)) == 7 and
            all(old491[name] == old493[name] == current[name] for name in unchanged),
            'source-resume library, dependency declarations or pinned toolchain changed')
    require(current['android/manifest/m2-role-ingress-provider3-source-lock.json']['sha256'] ==
            'f5717d49fe0d4656b952bd397beab5d2fa70aa0992dd936ac31f81246c9e4772',
            'current exact provider3 lock changed')
    return {'transitions': changes, 'unchanged_resume_and_cargo_inputs': sorted(unchanged),
            'legacy_source_directories_claimed_current': False}


def cargo_config_paths():
    paths = set()
    for parent in [SOURCE, *SOURCE.parents, P('/home/alex/.cargo')]:
        for name in ('config', 'config.toml'):
            paths.add(parent / ('.cargo/' + name) if parent != P('/home/alex/.cargo') else parent / name)
    return sorted(paths)


def no_cargo_config(paths):
    require(all(not path.exists() and not path.is_symlink() for path in paths),
            'unexpected Cargo configuration input')


def fd_census():
    require(len(os.listdir('/proc/self/task')) == 1, 'single owned controller thread required')
    observed = {}
    for value in os.listdir('/proc/self/fd'):
        try:
            fd = int(value)
            info = os.fstat(fd)
            observed[value] = {'target': os.readlink('/proc/self/fd/' + value),
                'identity': [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_nlink],
                'fd_flags': fcntl.fcntl(fd, fcntl.F_GETFD), 'file_flags': fcntl.fcntl(fd, fcntl.F_GETFL)}
        except OSError as error:
            if error.errno not in (errno.EBADF, errno.ENOENT):
                raise
    return observed


def explicit_library_baseline():
    # The existing owned-bootstrap probe established that importing _ctypes
    # opens this process-lifetime library FD. Bind it at an explicit early phase;
    # never adopt an unknown descriptor found after work has started.
    global ctypes
    require('ctypes' not in sys.modules and '_ctypes' not in sys.modules,
            'fresh explicit ctypes import required')
    inherited = fd_census()
    require(set(inherited) == {'0', '1', '2'}, 'only stdio may be inherited')
    import ctypes
    descriptors = fd_census()
    require(all(descriptors.get(name) == row for name, row in inherited.items()),
            'stdio changed during explicit ctypes import')
    require(set(descriptors) == {'0', '1', '2', '3'}, 'only stdio and explicit ctypes library are allowed')
    library = descriptors['3']
    require(library['target'] == LIBFFI['path'] and library['identity'] ==
            [66306, 108020388, 33188, 0, 0, 1] and library['fd_flags'] == fcntl.FD_CLOEXEC and
            library['file_flags'] == 32768,
            'explicit ctypes library descriptor differs')
    first = os.fstat(3)
    content = os.pread(3, LIBFFI['bytes'] + 1, 0)
    final = os.fstat(3)
    named = P(LIBFFI['path']).lstat()
    require(len(content) == LIBFFI['bytes'] == first.st_size and sha(content) == LIBFFI['sha256'] and
            identity(first) == identity(final) == identity(named) == LIBFFI['identity'],
            'explicit library pin changed')
    return descriptors, {'path': LIBFFI['path'], 'bytes': len(content), 'sha256': sha(content),
                         'inherited_stdio': inherited, 'explicit_import_added_FDs': ['3'],
                         'identity': identity(first), 'manual_close': False,
                         'retirement': 'authoritative durable normal process exit'}


def final_descriptor_gate(before, library):
    require(fd_census() == before, 'owned descriptor identities differ after qualification')
    require(identity(os.fstat(3)) == library['identity'] == identity(P(LIBFFI['path']).lstat()),
            'explicit process-lifetime library changed')


def current_receipt_outputs(receipt):
    checked = []
    for row in receipt['commands']:
        for stream in ('stdout', 'stderr'):
            path = P(row[stream]['path'])
            require(path.parent == ACTIVE / 'compile01' and hash_held(path, 32 * 1024 * 1024) == row[stream],
                    'actual current compile output identity changed')
            checked.append({'pin': row[stream], 'owner': owner_identity(path)})
    for index, name in enumerate(TESTS):
        expected = receipt['commands'][index + 4]['independent_libtest_result']
        path = ACTIVE / 'compile01' / ('projection-test-' + str(index) + '.libtest')
        raw, observed = held(path, 4096)
        require(observed == expected and raw == ('ok ' + name + '\n').encode(),
                'original current independent result changed')
        checked.append({'pin': observed, 'owner': owner_identity(path)})
    return checked


def registered_tests(executable, name, expected, required, environment, records):
    output = command([str(executable), '--list'], SOURCE, environment, name, records, 20).decode()
    observed = [line[:-6] for line in output.splitlines() if line.endswith(': test')]
    require(len(observed) == len(set(observed)) == expected and set(required) <= set(observed),
            'exact current test registration differs')
    return observed


def qualification_complete(result):
    return (result.get('errors') == [] and
            result.get('cleanup') == {'complete': True, 'children': [], 'errors': []} and
            set(result.get('gates', {})) == set(EXPECTED_GATES) and
            all(value is True for value in result['gates'].values()) and
            [row.get('label') for row in result.get('commands', [])] == EXPECTED_FRESH_LABELS and
            all(row.get('returncode') == 0 and row.get('timed_out') is False for row in result['commands']) and
            result.get('command_count') == 34 and result.get('tests_passed') == 28 and
            [row.get('exact_name') for row in result.get('fresh_updater_independent_result_gates', [])] == TESTS and
            [row.get('exact_name') for row in result.get('fresh_source_resume_independent_result_gates', [])] == SOURCE_TESTS)


def run_current_qualification(expected_source_sha):
    require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000,
            'unprivileged original operator required')
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    no_alias(ROOT)
    root_info = ROOT.lstat()
    require(stat.S_ISDIR(root_info.st_mode) and root_info.st_uid == root_info.st_gid == 1000 and
            stat.S_IMODE(root_info.st_mode) == 0o700 and
            set(os.listdir(ROOT)) == {'qualify_current470.py', 'stage-receipt.json'},
            'fresh closed current-qualification stage required')
    own_raw, own_pin = held(P(__file__), 131072)
    require(own_pin['sha256'] == expected_source_sha and P(__file__) == ROOT / 'qualify_current470.py',
            'fixed qualifier source differs')
    own_info = P(__file__).lstat()
    require(own_info.st_uid == own_info.st_gid == 1000 and own_info.st_nlink == 1 and
            stat.S_IMODE(own_info.st_mode) == 0o400, 'fixed qualifier source owner/mode differs')
    stage_raw, stage_pin = held(ROOT / 'stage-receipt.json', 65536)
    stage_receipt = json.loads(stage_raw)
    stage_owner = owner_identity(ROOT / 'stage-receipt.json')
    require(stage_receipt['schema'] == 'pocket4-current470-qualification-stage-v1' and
            stage_receipt['state'] == 'SOURCE_STAGED_ONLY' and
            stage_receipt['qualifier_source'] == own_pin and
            stage_receipt['compiler_invoked'] is False and stage_receipt['Main_actions'] == 0,
            'closed new stage receipt does not bind this qualifier source')
    require(not OUT.exists(), 'qualification output already exists; reconcile original job')
    OUT.mkdir(mode=0o700)
    before, library = explicit_library_baseline()
    records = []
    errors = []
    observations = {}
    current = old491 = old493 = source_before = None
    dependencies = dependency_owners = tools_before = tool_owners = None
    configs = None
    current_artifacts = None
    current_output_pins = None
    cgroup = None
    result = {'schema': 'pocket4-builder470-explicit-current-qualification-v1',
        'state': 'FAILED_BEFORE_QUALIFICATION', 'started_utc': utc(),
        'qualifier_source': own_pin, 'stage_receipt': stage_pin, 'explicit_library_resource': library,
        'Main_actions': 0, 'Android_actions': 0, 'install_actions': 0,
        'Soong_invoked': False, 'runtime_authorization_enabled': False,
        'full_Android_Java_JNI_compiled': False, 'production_ready': False, 'cleanup_eligible': False,
        'new_authorization_contract_connected': False, 'historical_originals_rewritten': False,
        'legacy_binary_paths_written': False, 'legacy_binary_identities_claimed_current': False,
        'updater_rebuilt': False, 'automatic_retry': False,
        'acceptance_requires_final_stdout_and_authoritative_durable_terminal': True,
        'gates': {}, 'errors': errors}
    phase = 'current_and_historical_authorities'
    try:
        compile470 = authority('current470-result', observations)
        qualify_builder470_receipt(compile470)
        prior_admission = authority('current470-resource-admission', observations)
        recorded = compile470['resource_admission']
        expected_recorded = dict(recorded)
        expected_recorded['identity'] = recorded['identity'][:3] + [recorded['bytes']] + [int(x) for x in recorded['identity'][3:]]
        require(observations['current470-resource-admission']['pin'] == expected_recorded and
                prior_admission['profile'] == {'memory_max_bytes': 1073741824, 'memory_swap_max_bytes': 0,
                    'minimum_fresh_MemAvailable_bytes': 3221225472, 'admission_difference_bytes': 2147483648,
                    'global_swap_is_owned_budget': False} and
                prior_admission['owned_observed'] == {'memory.max': '1073741824', 'cpu.max': '100000 100000',
                    'memory.swap.max': '0', 'memory.swap.current': '0'} and
                parse_admission_meminfo(prior_admission['meminfo']['raw_ascii'].encode('ascii'))['MemAvailable'] >= 3*1024**3 and
                len(compile470['cpu_affinity']) == 1, 'actual original current Rust resource authority differs')
        legacy468 = authority('legacy468-result', observations)
        legacy469 = authority('legacy469-result', observations)
        legacy469_qualification = authority('legacy469-qualification', observations)
        require(legacy468['state'] == 'PASS' and legacy468['focused_tests_passed'] == 24 and
                legacy468['expected_source_resume_test_names'] == SOURCE_TESTS and
                legacy468['source_actual_registered_test_count'] == 20 and
                legacy469['state'] == 'RUST_BUILD_AND_FOCUSED_TESTS_PASS' and
                legacy469_qualification['state'] == 'ACTUAL_COMPILE02_INPUT_CONTINUITY_AND_16_INDEPENDENT_TESTS_PASS',
                'immutable historical capability provenance differs')
        result['historical_provenance'] = {'468': observations['legacy468-result'],
            '469_compile': observations['legacy469-result'], '469_qualification': observations['legacy469-qualification'],
            'classification': 'historical evidence only; no live legacy ELF identity assertion',
            'missing468_diagnostic_job': '1a1b2240691-fc05-7c96',
            'missing468_diagnostic_stdout_sha256': '2a8c2c6c141a76bbc604c039d4dfcc22ab2daac80b6d51286b06718f19e6207b',
            'missing468_diagnostic_state': 'DIAGNOSIS_FAILED',
            'missing468_diagnostic_secondary_FD_failure_preserved': True}
        result['current_compile_authority'] = observations['current470-result']
        require(compile470['baseline_compile'] == observations['legacy469-result']['pin'] ==
                    legacy469_qualification['actual_compile02'] and
                compile470['baseline_independent_qualification'] == observations['legacy469-qualification']['pin'] and
                compile470['profile_authority'] == observations['legacy468-result']['pin'] ==
                    legacy469_qualification['original_compiler03_authority'] and
                legacy468['expected_test_names'] == TESTS[:15] and
                legacy469['test_names'] == legacy469_qualification['expected_test_names'] == TESTS[:16] and
                legacy469_qualification['unchanged_source_resume_controls']['names'] == SOURCE_TESTS,
                'exact current and historical capability bindings differ')
        result['gates']['actual_current_470_compile_receipt_and_19_original_gates'] = True

        phase = 'fresh_owned_Rust_resource_admission'
        affinity = sorted(os.sched_getaffinity(0))
        require(len(affinity) >= 3, 'at least two logical CPUs must remain free')
        os.sched_setaffinity(0, affinity[-1:])
        result['cpu_affinity_before'] = affinity
        result['cpu_affinity'] = affinity[-1:]
        member = P('/proc/self/cgroup').read_text().strip()
        require(member.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'),
                'exact newly owned user cgroup required')
        cgroup = P('/sys/fs/cgroup') / member[3:].lstrip('/')
        unit = cgroup.name
        require(unit.endswith('.service') and str(os.getpid()) in (cgroup / 'cgroup.procs').read_text().split(),
                'owned cgroup process identity differs')
        require((cgroup / 'memory.max').read_text().strip() == str(MEMORY_MAX) and
                (cgroup / 'cpu.max').read_text().strip() == '100000 100000', 'owned Rust limits differ')
        subprocess.run(['/usr/bin/systemctl', '--user', 'set-property', '--runtime', unit, 'MemorySwapMax=0'],
                       check=True, capture_output=True, timeout=15)
        memory, owned, admission = record_resource_admission(cgroup)
        result['resource_admission'] = admission
        result['owned_unit'] = unit
        subreaper()
        require(child_ids() == [], 'preexisting owned children')
        result['gates']['fresh_3GiB_and_owned_1GiB_1CPU_zero_swap'] = True

        phase = 'complete_current_source_and_ancestry'
        current = authority('current498-manifest', observations)
        old493 = authority('legacy493-manifest', observations)
        old491 = authority('legacy491-manifest', observations)
        result['source_ancestry'] = verify_source_ancestry(old491, old493, current)
        require(compile470['candidate_manifest'] == observations['current498-manifest']['pin'] and
                compile470['baseline_manifest'] == legacy469_qualification['candidate_manifest'] ==
                    observations['legacy493-manifest']['pin'] and
                legacy469_qualification['baseline_manifest'] == observations['legacy491-manifest']['pin'],
                'exact current manifest ancestry identities differ')
        source_before = source_observation(current)
        candidate_rows = {name: row['pin'] for name, row in source_before['files'].items()}
        current_lock, unused = held(SOURCE / 'android/manifest/m2-role-ingress-provider3-source-lock.json', 1048576)
        lock = json.loads(current_lock)
        require(len(lock['projects']) == 242 and len(lock['links']) == 8 and
                lock['remote_base'] == 'https://android.googlesource.com/' and
                lock['superproject']['commit'] == '28f0bbddc24d56c8ec5a8df5342ac7a292184039' and
                lock['policy']['allow_unrestricted_repo_sync'] is False and
                lock['policy']['require_exact_commits'] is True and
                lock['policy']['add_dependencies_only_from_superproject'] is True,
                'current locked provider source policy differs')
        resume, unused = held(SOURCE / 'tools/droidloom-source/src/resume.rs', 65536)
        require(sha(resume) == '2026055997ba7d8392bada503d0e1c229cad13bba931f13b410457ac86daafe6' and
                b'#[cfg(test)]\n    command.args(["-c", "protocol.https.allow=never"]);' in resume and
                b'let temporary = tempfile::tempdir().unwrap();' in resume,
                'current source-resume test network and private-fixture boundary changed')
        result['gates']['complete498_source_and_exact491_493_498_ancestry'] = True
        result['gates']['exact242_project_lock_and_private_offline_resume_fixture_source'] = True

        phase = 'current_artifacts_and_original_compile_outputs'
        current_artifacts = {
            'builder': current_artifact(compile470['builder'], ACTIVE / 'compile01/cargo-target/debug/droidloom-update'),
            'test': current_artifact(compile470['test_executable'],
                ACTIVE / 'compile01/cargo-target/debug/deps/droidloom_update-77fdace49114cd0d')}
        current_output_pins = current_receipt_outputs(compile470)
        result['current_artifacts'] = current_artifacts
        result['gates']['existing470_ELF_and_test_exact_original_identity_owner_and_SHA'] = True
        result['gates']['original23_command_outputs_and19_independent_logs_revalidated'] = True

        phase = 'closed_registry_toolchain_and_configuration_inputs'
        dependency_document = authority('dependency-inputs', observations)
        require(observations['dependency-inputs']['pin'] == compile470['dependency_continuity']['authority'] ==
                    legacy469_qualification['dependency_continuity']['authority'],
                'original dependency authority full identity differs')
        dependencies = dependency_document['files']
        packages = dependency_document['packages']
        require(len(dependencies) == 2706 and len(packages) == 49 and
                sum(p['kind'] == 'offline-registry' for p in packages) == 45,
                'complete registry closure differs')
        dependency_owners = {}
        for name, row in dependencies.items():
            path = P(name)
            require(path.is_absolute() and str(path) == row['path'] and
                    path.is_relative_to(P('/home/alex/.cargo/registry')), 'registry path escaped its bound root')
            no_alias(path.parent)
            require(hash_held(path) == row, 'qualified registry bytes or full identity changed: ' + name)
            dependency_owners[name] = owner_identity(path)
        remapped = json.loads(json.dumps(packages).replace(str(PROFILE_BASE / 'builder-source'), str(SOURCE)))
        require(sum(p['kind'] == 'pinned-builder-source' for p in remapped) == 4 and
                sorted(p['id'] for p in remapped) == compile470['dependency_continuity']['actual_build_packages'],
                'exact current 49-package ancestry differs')
        expected_source_packages = sorted(value.replace(str(PROFILE_BASE / 'builder-source'), str(SOURCE))
                                         for value in legacy468['actual_source_test_compile_packages'])
        require(len(expected_source_packages) == 46 and set(expected_source_packages) <= {p['id'] for p in remapped},
                'exact current source-resume library subset differs')
        configs = cargo_config_paths()
        no_cargo_config(configs)
        original_tools = authority('tool-inputs', observations)
        pins = {}
        collect_pins(original_tools, pins)
        pins.pop('/home/alex/.cargo/bin/rustup', None)
        rustroot = '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu'
        for suffix, count, checksum in EXPLICIT_RUST_TOOLS:
            path = rustroot + suffix
            row = {'bytes': count, 'sha256': checksum, 'resolved_path': path}
            require(path not in pins or pins[path] == row, 'explicit pinned toolchain differs')
            pins[path] = row
        require(len(pins) == 70, 'exact full compiler/runtime tool closure differs')
        tools_before = checked_tools(pins)
        original_current_tools = authority('current470-tool-inputs', observations)
        require(len(original_current_tools) == 70 and tools_before == original_current_tools,
                'full current tool identities differ from actual470 pre-compile inputs')
        original_modes = {}
        for row in original_tools:
            path = row.get('requested_path') or row['path']
            require(path not in original_modes or original_modes[path] == row['identity'][2],
                    'inconsistent original tool mode')
            original_modes[path] = row['identity'][2]
        require(set(original_modes) == set(pins), 'original tool mode closure differs')
        tool_owners = {}
        for path, row in tools_before.items():
            info = P(row['resolved_path']).lstat()
            expected_owner = 1000 if row['resolved_path'].startswith('/home/alex/.rustup/') else 0
            require(row['resolved_path'].startswith(('/home/alex/.rustup/', '/usr/')) and
                    info.st_uid == info.st_gid == expected_owner and
                    info.st_mode == original_modes[path] and not info.st_mode & 0o6002,
                    'tool differs from original mode or explicit current owner policy')
            tool_owners[path] = {'uid': info.st_uid, 'gid': info.st_gid, 'nlink': info.st_nlink,
                                 'identity': identity(info)}
        save(OUT / 'source-inputs-before.json', source_before)
        save(OUT / 'tool-inputs-before.json', {'pins': tools_before, 'owners': tool_owners})
        result['dependency_continuity'] = {'authority': observations['dependency-inputs'],
            'selected_packages': 49, 'registry_packages': 45, 'recorded_files_and_archives': 2706,
            'current_updater_packages': sorted(p['id'] for p in remapped),
            'expected_source_resume_packages': expected_source_packages, 'new_dependency_fetches': 0}
        result['gates']['all2706_registry_files_and49_package_inputs_qualified'] = True
        result['gates']['all70_tools_and_explicit_Rust1_93_and_no_Cargo_config'] = True

        phase = 'explicit_current_commands'
        (OUT / 'tmp').mkdir(mode=0o700)
        (OUT / 'cargo-target').mkdir(mode=0o700)
        environment = {'PATH': rustroot + '/bin:/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
            'CARGO_HOME': '/home/alex/.cargo', 'CARGO_TARGET_DIR': str(OUT / 'cargo-target'),
            'CARGO_NET_OFFLINE': 'true', 'CARGO_BUILD_JOBS': '1', 'RUSTC': rustroot + '/bin/rustc',
            'RUSTDOC': rustroot + '/bin/rustdoc', 'CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER': '/usr/bin/cc',
            'RUSTC_WRAPPER': '', 'RUSTC_WORKSPACE_WRAPPER': '', 'RUSTFLAGS': '', 'RUSTDOCFLAGS': '',
            'CARGO_ENCODED_RUSTFLAGS': '', 'CARGO_ENCODED_RUSTDOCFLAGS': '',
            'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_OPTIONAL_LOCKS': '0',
            'TMPDIR': str(OUT / 'tmp')}
        result['command_environment'] = environment
        version = command([rustroot + '/bin/rustc', '-Vv'], SOURCE, environment, 'rust-version', records, 20)
        require('release: 1.93.0\n' in version.decode(), 'actual current Rust version differs')
        builder = P(compile470['builder']['path'])
        test = P(compile470['test_executable']['path'])
        general_help = command([str(builder), '--help'], SOURCE, environment, 'current-builder-help', records, 20)
        typed_help = command([str(builder), 'native-role-ingress-build', '--help'], SOURCE, environment,
                             'current-typed-ingress-help', records, 20)
        require(b'native-role-ingress-build' in general_help and b'--work' in typed_help and
                b'--resume-source-staging' in typed_help, 'actual current fixed typed-ingress CLI surface differs')
        names = registered_tests(test, 'updater-test-list', 209, TESTS, environment, records)
        updater_gates = [focused_test(test, name, index, len(names), environment, records)
                         for index, name in enumerate(TESTS)]
        result['fresh_updater_independent_result_gates'] = updater_gates
        result['gates']['current_CLI_help_and19_updater_independent_tests'] = len(updater_gates) == 19

        phase = 'current_source_resume_test_compilation_and_execution'
        source_log = command([rustroot + '/bin/cargo', 'test', '--offline', '--locked', '-j', '1',
            '-p', 'droidloom-source', '--lib', '--no-run', '--message-format=json-render-diagnostics'],
            SOURCE, environment, 'source-resume-test-compile', records, 300)
        actual_packages = qualify_compiler_inputs(source_log, remapped, dependencies, candidate_rows)
        require(actual_packages == expected_source_packages, 'actual source-resume compilation closure differs')
        artifacts = [json.loads(line) for line in source_log.decode().splitlines() if line.startswith('{')]
        executables = [item['executable'] for item in artifacts if item.get('reason') == 'compiler-artifact' and
            item.get('target', {}).get('name') == 'droidloom_source' and
            item.get('target', {}).get('kind') == ['lib'] and
            item.get('manifest_path') == str(SOURCE / 'tools/droidloom-source/Cargo.toml') and
            item.get('profile', {}).get('test') is True and item.get('executable')]
        require(len(executables) == 1, 'exactly one actual current source-resume test executable is required')
        source_test = P(executables[0])
        require(source_test.is_relative_to(OUT / 'cargo-target') and not source_test.is_symlink(),
                'new source-resume test executable escaped its owned target')
        source_test_pin = hash_pin(source_test)
        source_test_owner = owner_identity(source_test)
        source_names = registered_tests(source_test, 'source-resume-test-list', 20, SOURCE_TESTS, environment, records)
        source_gates = [focused_test(source_test, name, 100 + index, len(source_names), environment, records)
                        for index, name in enumerate(SOURCE_TESTS)]
        require(hash_pin(source_test) == source_test_pin and owner_identity(source_test) == source_test_owner,
                'new source-resume executable changed during its tests')
        result['fresh_source_resume_independent_result_gates'] = source_gates
        result['source_resume_test_executable'] = {'pin': source_test_pin, 'owner': source_test_owner}
        result['actual_source_resume_compile_packages'] = actual_packages
        result['source_resume_test_compiled_from_current498_source'] = True
        result['source_resume_test_fixtures_network_disabled_by_exact_cfg_test_source'] = True
        result['gates']['fresh_current_source_resume_compile_and9_independent_tests'] = len(source_gates) == 9
        require([row['label'] for row in records] == EXPECTED_FRESH_LABELS and
                all(row['returncode'] == 0 and row['timed_out'] is False for row in records),
                'exact fresh 34-command closure differs')
        result['gates']['exact34_fresh_commands_and28_independent_tests'] = True
    except BaseException as error:
        errors.append(failure_detail(error, phase))
    finally:
        try:
            cleanup = cleanup_children()
            result['cleanup'] = cleanup
            require(cleanup.get('complete') is True and cleanup.get('children') == [] and cleanup.get('errors') == [],
                    'owned child cleanup incomplete or residual child retirement occurred')
            result['gates']['strict_no_residual_owned_children'] = True
        except BaseException as error:
            errors.append(failure_detail(error, 'owned_children_final'))
        try:
            for name, row in observations.items():
                require(hash_held(P(row['pin']['path']), AUTHORITIES[name]['bytes']) == row['pin'] and
                        owner_identity(P(row['pin']['path'])) == row['owner'], 'authority changed during qualification')
            if source_before is not None:
                require(source_observation(current) == source_before, 'complete current source identity changed')
            if current_artifacts is not None:
                require(current_artifact(compile470['builder'], P(compile470['builder']['path'])) == current_artifacts['builder'] and
                        current_artifact(compile470['test_executable'], P(compile470['test_executable']['path'])) == current_artifacts['test'],
                        'current builder or test artifact changed after qualification')
            if current_output_pins is not None:
                require(current_receipt_outputs(compile470) == current_output_pins, 'current original result evidence changed')
            if dependencies is not None:
                for path, row in dependencies.items():
                    require(hash_held(P(path)) == row and owner_identity(P(path)) == dependency_owners[path],
                            'registry bytes, owner or identity changed after qualification')
            if tools_before is not None:
                require(checked_tools(pins) == tools_before, 'tool bytes or full identity changed after qualification')
                for path, row in tools_before.items():
                    info = P(row['resolved_path']).lstat()
                    require(tool_owners[path] == {'uid': info.st_uid, 'gid': info.st_gid, 'nlink': info.st_nlink,
                            'identity': identity(info)}, 'tool owner changed after qualification')
            if configs is not None:
                no_cargo_config(configs)
            require(held(P(__file__), 131072)[1] == own_pin and
                    held(ROOT / 'stage-receipt.json', 65536)[1] == stage_pin and
                    owner_identity(ROOT / 'stage-receipt.json') == stage_owner,
                    'qualifier source or closed-stage receipt changed')
            require(set(observations) == set(AUTHORITIES) and source_before is not None and
                    current_artifacts is not None and current_output_pins is not None and
                    dependencies is not None and tools_before is not None and configs is not None,
                    'full mandatory continuity observation was not reached')
            result['gates']['all_bound_inputs_and_owners_unchanged_after'] = True
        except BaseException as error:
            errors.append(failure_detail(error, 'input_continuity_final'))
        try:
            if cgroup is not None:
                result['memory_events'] = (cgroup / 'memory.events').read_text()
                result['owned_resource_gate'] = owned_resource_gate(result['memory_events'])
                require(result['owned_resource_gate']['pass'] is True and
                        all(result['owned_resource_gate']['events'][name] == 0
                            for name in ('oom', 'oom_kill', 'oom_group_kill')), 'owned OOM gate failed')
                result['memory_peak'] = (cgroup / 'memory.peak').read_text().strip()
                result['swap_peak'] = (cgroup / 'memory.swap.peak').read_text().strip()
                require(result['swap_peak'] == '0' and (cgroup / 'memory.swap.max').read_text().strip() == '0' and
                        (cgroup / 'memory.swap.current').read_text().strip() == '0', 'owned zero-swap gate failed')
                result['gates']['owned_no_OOM_and_zero_swap'] = True
            final_descriptor_gate(before, library)
            result['gates']['exact_stdio_and_prequalified_library_FD_set'] = True
        except BaseException as error:
            errors.append(failure_detail(error, 'resource_and_descriptor_final'))
    result['authority_observations'] = observations
    result['commands'] = records
    result['command_count'] = len(records)
    result['tests_passed'] = len(result.get('fresh_updater_independent_result_gates', [])) + len(result.get('fresh_source_resume_independent_result_gates', []))
    result['expected_gates'] = EXPECTED_GATES
    qualified = qualification_complete(result)
    result['current_builder_qualification_complete'] = qualified
    result['state'] = 'CURRENT470_EXPLICIT_28_TEST_QUALIFICATION_PASS' if qualified else 'FAILED'
    result['finished_utc'] = utc()
    save(OUT / 'result.json', result)
    result_raw, result_pin = held(OUT / 'result.json', 1048576)
    late_error = None
    try:
        final_descriptor_gate(before, library)
        require(child_ids() == [], 'owned child appeared after result publication')
    except BaseException as error:
        late_error = failure_detail(error, 'after_result_publication')
    final_ok = qualified and late_error is None
    print(json.dumps({'schema': 'pocket4-current470-qualification-final-summary-v1',
        'state': 'PASS' if final_ok else 'FAILED', 'current_builder_qualification_complete': final_ok,
        'result': result_pin, 'commands': len(records), 'tests_passed': result['tests_passed'],
        'late_error': late_error, 'Main_actions': 0, 'Soong_invoked': False,
        'new_authorization_contract_connected': False, 'production_ready': False,
        'cleanup_eligible': False, 'authoritative_durable_exit_zero_still_required': True}), flush=True)
    return 0 if final_ok else 1


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print(json.dumps({'state': 'PLAN_ONLY', 'Main_actions': 0, 'compiler_invoked': False}))
    else:
        require(len(sys.argv) == 4 and sys.argv[1:3] == ['--qualify-once', '--source-sha256'] and
                re.fullmatch('[0-9a-f]{64}', sys.argv[3]), 'exact once-only qualification arguments required')
        raise SystemExit(run_current_qualification(sys.argv[3]))
