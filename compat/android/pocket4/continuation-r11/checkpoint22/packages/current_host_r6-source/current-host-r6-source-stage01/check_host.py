"""Pure current-host source controls. No process, filesystem, namespace or Android actions."""
import ast,copy,hashlib,json,types
def require(value,code):
    if not value:raise RuntimeError(code)
def functions(raw,classname=None):
    tree=ast.parse(raw)
    if classname is None:body=tree.body
    else:
        rows=[x for x in tree.body if isinstance(x,ast.ClassDef) and x.name==classname]
        require(len(rows)==1,"EXACT_CLASS_REQUIRED")
        body=rows[0].body
    return {x.name:ast.dump(x,include_attributes=False) for x in body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
def run_controls(files,parents,manifest_raw):
    require(type(files) is dict and type(parents) is dict,"CONTROL_SOURCE_MAPS_REQUIRED")
    m=json.loads(manifest_raw)
    require(m["schema"]==2 and m["artifact"]=="pocket4-bilibili-current-recorder-held-r6" and
            set(m["files"])==set(files),"EXACT_NEW_HOST_SOURCE_CLOSURE_REQUIRED")
    compiled=[]
    for name,raw in sorted(files.items()):
        require(len(raw.encode())==m["files"][name]["bytes"] and
                hashlib.sha256(raw.encode()).hexdigest()==m["files"][name]["sha256"],"CONTROL_SOURCE_PIN_CHANGED")
        if name.endswith(".py"):
            compile(raw,name,"exec");compiled.append(name)
    rows=[]
    def passed(name):rows.append({"name":name,"passed":True})
    passed("complete_new_source_closure_compiles")
    source=types.ModuleType("controlled_current_source_contract");source.__file__="/current-source/source_contract.py"
    parsed=ast.parse(files["source_contract.py"])
    constants={"PACKAGE","COMPONENT","UID","BASELINE_SCHEMA","MAIN_EPOCH","BASELINE_SHA",
               "BASELINE_QUALIFICATION_SHA","HISTORICAL_ACTIVATION_SHA","HISTORICAL_VERIFIED_SHA"}
    selected=[x for x in parsed.body if
              (isinstance(x,ast.FunctionDef) and x.name in {"require","verify_scope"}) or
              (isinstance(x,ast.Assign) and len(x.targets)==1 and isinstance(x.targets[0],ast.Name) and
               x.targets[0].id in constants)]
    require(len(selected)==len(constants)+2,"EXACT_PRODUCTION_PURE_SCOPE_SELECTION_REQUIRED")
    exec(compile(ast.Module(body=selected,type_ignores=[]),source.__file__,"exec"),source.__dict__)
    contract=types.SimpleNamespace(sha256=hashlib.sha256(manifest_raw.encode()).hexdigest(),files=m["files"])
    scope={"schema":"pocket4-current-recorder-scope-v2","current_baseline_schema":source.BASELINE_SCHEMA,
           "package":source.PACKAGE,"component":source.COMPONENT,"uid":source.UID,"user":0,
           "automatic_retry":False,"epoch_sha256":source.MAIN_EPOCH,
           "current_baseline_sha256":source.BASELINE_SHA,
           "current_baseline_qualification_sha256":source.BASELINE_QUALIFICATION_SHA,
           "historical_activation_sha256":source.HISTORICAL_ACTIVATION_SHA,
           "historical_verified_sha256":source.HISTORICAL_VERIFIED_SHA,
           "adapter_manifest_sha256":contract.sha256,"recorder_sha256":m["files"]["recorder.py"]["sha256"]}
    baseline={"schema":source.BASELINE_SCHEMA,"kind":"current-cell-generation","deployment_performed":False,
              "framework_epoch":{"sha256":source.MAIN_EPOCH},
              "historical_deployment":{"activation_sha256":source.HISTORICAL_ACTIVATION_SHA,
                  "verification_sha256":source.HISTORICAL_VERIFIED_SHA},
              "framework_exit_cause_resolved":False,"whole_app_production_ready":False}
    source.verify_scope(copy.deepcopy(scope),copy.deepcopy(baseline),contract)
    passed("typed_current_scope_positive")
    def negative(name,change):
        s=copy.deepcopy(scope);b=copy.deepcopy(baseline);change(s,b)
        try:source.verify_scope(s,b,contract)
        except RuntimeError:pass
        else:raise RuntimeError("CURRENT_SCOPE_NEGATIVE_ACCEPTED:"+name)
        passed(name)
    negative("old_epoch",lambda s,b:s.update(epoch_sha256="48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f"))
    negative("missing_baseline",lambda s,b:s.pop("current_baseline_sha256"))
    negative("wrong_qualification",lambda s,b:s.update(current_baseline_qualification_sha256="0"*64))
    negative("old_scope_schema",lambda s,b:s.pop("schema"))
    negative("historical_as_current",lambda s,b:s.update(activation_sha256=source.HISTORICAL_ACTIVATION_SHA))
    negative("forged_deployment_flag",lambda s,b:b.update(main_deployed=True))
    negative("new_deployment_claim",lambda s,b:b.update(deployment_performed=True))
    negative("foreign_target",lambda s,b:s.update(package="example.unrelated"))
    negative("wrong_uid",lambda s,b:s.update(uid=source.UID+1))
    negative("bool_uid",lambda s,b:s.update(uid=True))
    negative("bool_user",lambda s,b:s.update(user=False))
    negative("wrong_component",lambda s,b:s.update(component=source.PACKAGE+"/Other"))
    negative("source_pin_changed",lambda s,b:s.update(adapter_manifest_sha256="0"*64))
    negative("history_pin_changed",lambda s,b:b["historical_deployment"].update(activation_sha256="0"*64))
    negative("production_claim",lambda s,b:b.update(whole_app_production_ready=True))
    negative("cause_resolved_claim",lambda s,b:b.update(framework_exit_cause_resolved=True))
    negative("automatic_retry",lambda s,b:s.update(automatic_retry=True))
    old=functions(parents["recorder.py"],"Flow");new=functions(files["recorder.py"],"Flow")
    keep=set(old)-{"__init__","guard"}
    require(set(old)==set(new) and all(old[x]==new[x] for x in keep),"FROZEN_FLOW_ACTION_OR_CLEANUP_BODY_CHANGED")
    passed("all_flow_action_command_lock_cleanup_bodies_unchanged")
    def body(raw,classname,name):
        t=ast.parse(raw);c=next(x for x in t.body if isinstance(x,ast.ClassDef) and x.name==classname)
        return next(x for x in c.body if isinstance(x,ast.FunctionDef) and x.name==name)
    og=body(parents["recorder.py"],"Flow","guard");ng=body(files["recorder.py"],"Flow","guard")
    extra=[x for x in ng.body if isinstance(x,ast.Expr) and isinstance(x.value,ast.Call) and
           isinstance(x.value.func,ast.Attribute) and x.value.func.attr=="current_guard"]
    require(len(extra)==1 and ast.unparse(extra[0].value)=="self.current_guard.current_guard(self.activation, action_attempted=attempted)",
            "EXACT_ADDITIONAL_CURRENT_MAIN_GUARD_REQUIRED")
    ng.body=[x for x in ng.body if x not in extra]
    require(ast.dump(og,include_attributes=False)==ast.dump(ng,include_attributes=False),"ORIGINAL_FLOW_GUARD_WEAKENED")
    passed("original_flow_guard_all_checks_retained_plus_current_guard")
    current_init=body(files["recorder.py"],"Flow","__init__")
    calls=[ast.unparse(x) for x in ast.walk(current_init) if isinstance(x,ast.Call)]
    require("self.current_guard.current_guard()" in calls and not any("activation_after" in x for x in calls),
            "CURRENT_INIT_OR_OLD_DEPLOYMENT_REJECTION_MISSING")
    passed("current_init_prewrite_guard_and_no_old_activation_argument")
    old_entry=functions(parents["existing_ui_entry.py"]);new_entry=functions(files["existing_ui_entry.py"])
    require(set(old_entry)==set(new_entry) and all(old_entry[k]==new_entry[k] for k in old_entry if k!="load_context"),
            "EXISTING_UI_CHILD_DISPATCH_CHANGED")
    passed("existing_ui_dispatch_bodies_unchanged")
    context=ast.unparse(ast.parse(files["existing_ui_entry.py"]))
    require("view.current_guard = current_guard" in context and "baseline-qualification.json" in context and
            "activation-verified.json" not in context,"CHILD_CURRENT_BASELINE_BINDING_MISSING")
    passed("child_guard_instance_and_new_saved_inputs_bound")
    old_source=functions(parents["source_contract.py"]);new_source=functions(files["source_contract.py"])
    require(all(old_source[k]==new_source[k] for k in old_source if k!="verify_scope"),
            "ORIGINAL_SHARED_HELPER_OR_BOUNDED_READ_CHANGED")
    passed("shared_native_helper_and_bounded_source_reads_unchanged")
    for name in ("references/original_recorder.py","references/android_app.py","references/android_backend.py",
                 "references/framework_epoch.py","references/task_scope_baseline.py","references/held_runtime_r5.py",
                 "references/bound_android_transport_r3.py"):
        require(files[name]==parents[name],"FROZEN_REFERENCE_CHANGED")
    passed("all_seven_original_references_byte_exact")
    negative("previous_current_epoch_rejected",lambda s,b:s.update(epoch_sha256="734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2"))
    negative("previous_current_baseline_schema_rejected",lambda s,b:b.update(schema="pocket4-main-current-baseline-v1"))
    negative("previous_current_baseline_kind_rejected",lambda s,b:b.update(kind="current-framework-generation"))
    negative("previous_typed_scope_schema_rejected",lambda s,b:s.update(schema="pocket4-current-recorder-scope-v1"))
    negative("previous_baseline_digest_rejected",lambda s,b:s.update(current_baseline_sha256="163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266"))
    negative("previous_qualification_digest_rejected",lambda s,b:s.update(current_baseline_qualification_sha256="f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6"))
    # Only the filesystem boundary is a memory fixture. Execute the actual
    # SourceContract constructor, verify, path/manifest/source pin predicates.
    from pathlib import PurePosixPath
    import re
    class MemoryPath(PurePosixPath):
        def resolve(self):return self
    namespace={"__file__":"/current-source/source_contract.py","Path":MemoryPath,
               "PurePosixPath":PurePosixPath,"hashlib":hashlib,"json":json,"re":re,"types":types}
    selected=[x for x in ast.parse(files["source_contract.py"]).body
        if isinstance(x,(ast.Assign,ast.AnnAssign)) or
           (isinstance(x,ast.FunctionDef) and x.name in {"require","sha"}) or
           (isinstance(x,ast.ClassDef) and x.name=="SourceContract")]
    exec(compile(ast.Module(body=selected,type_ignores=[]),namespace["__file__"],"exec"),namespace)
    def constructor(manifest,override=None):
        text=json.dumps(manifest,sort_keys=True,separators=(",",":"))+"\n"
        contents={"/current-source/source-manifest.json":text.encode(),
                  **{"/current-source/"+n:v.encode() for n,v in files.items()}}
        if override:contents.update(override)
        reads=[]
        def memory_read(path,limit=131072):
            key=str(path);require(key in contents,"FIXTURE_UNEXPECTED_SOURCE_READ")
            raw=contents[key];require(len(raw)<=limit,"FIXTURE_INPUT_BOUND");reads.append(key);return raw
        namespace["bounded_file"]=memory_read
        value=namespace["SourceContract"](MemoryPath("/current-source/source-manifest.json"),
                                         hashlib.sha256(text.encode()).hexdigest())
        require(set(reads)==set(contents),"ACTUAL_CONSTRUCTOR_DID_NOT_VERIFY_ALL_INPUTS")
        return value
    constructor(copy.deepcopy(m));passed("actual_source_constructor_all_fourteen_leaves")
    def constructor_no(name,change,code,override=None):
        manifest=copy.deepcopy(m);change(manifest)
        try:constructor(manifest,override)
        except RuntimeError as error:
            require(str(error)==code,"SOURCE_CONSTRUCTOR_WRONG_FIRST_ERROR")
        else:raise RuntimeError("SOURCE_CONSTRUCTOR_NEGATIVE_ACCEPTED")
        passed(name)
    constructor_no("old_host_artifact_rejected",lambda v:v.update(artifact="pocket4-bilibili-current-recorder-held-r5"),
                   "ADAPTER_MANIFEST_SCHEMA_CHANGED")
    constructor_no("missing_current_coordinator_rejected",lambda v:v["files"].pop("current_coordinator.py"),
                   "ADAPTER_SOURCE_CLOSURE_INCOMPLETE")
    constructor_no("old_manifest_baseline_schema_rejected",lambda v:v["current_baseline"].update(schema="pocket4-main-current-baseline-v1"),
                   "ACTUAL_CURRENT_HOST_MANIFEST_BINDING_REQUIRED")
    constructor_no("different_generated_guard_pin_rejected",lambda v:v["files"]["current_baseline_guard.py"].update(sha256="0"*64),
                   "CURRENT_GUARD_SOURCE_PIN_CHANGED")
    constructor_no("actual_constructor_runtime_source_drift_rejected",lambda v:None,
                   "ADAPTER_SOURCE_CHANGED:recorder.py", {"/current-source/recorder.py":b"changed\n"})
    require(len(rows)==38 and len({r["name"] for r in rows})==38,"EXACT_CURRENT_HOST_CONTROL_COUNT")
    return {"schema":"pocket4-current-host-source-controls-v2","all_passed":True,"count":len(rows),"cases":rows,
            "compiled_sources":compiled,"fixture_is_not_baseline_observation":True,
            "Android_commands":0,"UI_actions":0,"children":0,"filesystem_operations":0}
