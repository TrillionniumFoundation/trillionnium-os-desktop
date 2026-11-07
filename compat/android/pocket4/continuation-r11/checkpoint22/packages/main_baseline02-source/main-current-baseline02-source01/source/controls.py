"""Pure boundary controls. No files, processes, Android API or mock epoch adoption."""
import ast,copy
def run(p,encoded):
    compiled=[]
    for name,raw in encoded.items():
        if not name.endswith(".py"):continue
        if name=="current_baseline_guard.template.py":
            text=raw.decode()
            for marker in ("@@BASELINE_SHA@@","@@QUALIFICATION_SHA@@","@@CURRENT_EPOCH@@","@@MANIFEST_SHA@@"):
                p.need(marker in text,"TEMPLATE_SYNTAX_MARKER_REQUIRED");text=text.replace(marker,"f"*64)
            for marker in ("@@BASELINE_BYTES@@","@@QUALIFICATION_BYTES@@"):
                p.need(marker in text,"TEMPLATE_SIZE_MARKER_REQUIRED");text=text.replace(marker,"1")
            p.need("@@" not in text,"UNBOUND_TEMPLATE_SYNTAX_MARKER")
            compile(text,"<current_guard_syntax_fixture>","exec")
        else:compile(raw,"<"+name+">","exec")
        compiled.append(name)
    p.need(len(compiled)==8,"EXACT_EIGHT_SOURCE_COMPILATIONS_REQUIRED")
    names=[]
    def yes(name,fn):
        value=fn()
        p.need(value is True,"POSITIVE_CONTROL_DID_NOT_RETURN_TRUE")
        names.append({"name":name,"passed":True})
    def no(name,code,fn):
        try:fn()
        except RuntimeError as e:
            p.need(str(e)==code,"NEGATIVE_CONTROL_WRONG_FIRST_CAUSE")
        else:raise RuntimeError("NEGATIVE_CONTROL_ACCEPTED")
        names.append({"name":name,"passed":True})
    def fixture():
        rows={}
        for role,x in p.EXPECTED.items():
            argv=[role] if role in ("zygote64","system_server") else ["/system/bin/surfaceflinger"] if role=="surfaceflinger" else ["/init"] if role=="android_init" else ["/fixed-"+role]
            exe="/system/bin/app_process64" if role in ("zygote64","system_server") else "/system/bin/surfaceflinger" if role=="surfaceflinger" else "/system/bin/init" if role=="android_init" else "/fixed-"+role
            rows[role]={"host_pid":x["pid"],"parent_host_pid":x["ppid"],"start_ticks":x["start_ticks"],
                "uids":copy.deepcopy(x["uids"]),"namespace_pids":copy.deepcopy(x["namespace_pids"]),
                "cgroup":x["cgroup"].splitlines(),"namespaces":{k:x["namespaces"][k] for k in ("pid","mnt")},
                "cmdline":argv,"executable":exe}
        body={"boot_id":p.BOOT_ID,"processes":rows}
        snap={"schema":"pocket4-framework-epoch-v1","binding":body,"sha256":p.sha(p.canonical(body)),
              "collected_monotonic_ns":1_000_000_000}
        a={"framework_epoch":{"binding":{"processes":{"init":copy.deepcopy(rows["android_init"]),
                "surfaceflinger":copy.deepcopy(rows["surfaceflinger"])}}},
           "daemon_process":copy.deepcopy(rows["daemon"]),"launcher_process":copy.deepcopy(rows["launcher"]),
           "presenter_process":copy.deepcopy(rows["presenter"])}
        roots={k:copy.deepcopy(v["root_identity"]) for k,v in p.EXPECTED.items()}
        return snap,a,roots
    def lineage_fixture():
        x=p.EXPECTED_INTERMEDIARY
        mid={"host_pid":x["pid"],"parent_host_pid":x["ppid"],"start_ticks":x["start_ticks"],
             "uids":copy.deepcopy(x["uids"]),"namespace_pids":copy.deepcopy(x["namespace_pids"]),
             "cgroup":x["cgroup"].splitlines(),"namespaces":copy.deepcopy(x["namespaces"]),
             "cmdline":["/synthetic-intermediary"],"executable":"/synthetic-intermediary"}
        tables={row["role"]:{"thread_ids":[row["pid"]],"per_thread":{str(row["pid"]):[row["child"]]},
                            "child_host_pids":[row["child"]]} for row in p.CHAIN_PARENTS}
        return {"schema":"pocket4-current-cell-owner-lineage-v1","intermediary_process":mid,
                "child_tables":tables,"host_user_namespace":"user:[42]",
                "role_user_namespaces":{role:"user:[42]" for role in p.ROLES},
                "intermediary_user_namespace":"user:[42]","intermediary_root":{"device":106,"inode":1},
                "intermediary_program_authority_assigned":False}
    def synthetic_authority():
        s,_,_=fixture();rows=s["binding"]["processes"];lineage=lineage_fixture()
        body={"boot_id":p.BOOT_ID,"processes":{"init":rows["android_init"],
              **{k:rows[k] for k in p.ANDROID_ROLES if k!="init"}}}
        return {"role_identity_sha256":{k:p.identity_sha(v) for k,v in rows.items()},
                "intermediary_identity_sha256":p.identity_sha(lineage["intermediary_process"]),
                "framework_epoch_sha256":p.sha(p.canonical(body)),
                "child_table_sha256":{k:p.identity_sha(v) for k,v in lineage["child_tables"].items()}}
    def inspect_edit(edit):
        s,a,r=fixture();bound=synthetic_authority()
        edit(s,a,r);s["sha256"]=p.sha(p.canonical(s["binding"]))
        return p.validate_snapshot(s,a,r,binding_authority=bound)
    yes("fixed_7_roles_and_separate_mount_namespaces",
        lambda:p.validate_snapshot(*fixture(),binding_authority=synthetic_authority()))
    no("host_pid_not_namespace_pid","FIXED_HOST_PID_BIRTH_PARENT_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["system_server"].update(host_pid=1160408)))
    no("old_system_server_not_adopted","FIXED_HOST_PID_BIRTH_PARENT_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["system_server"].update(host_pid=3589120,start_ticks=80797249)))
    no("new_birth_change","FIXED_HOST_PID_BIRTH_PARENT_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["zygote64"].update(start_ticks=96586438)))
    no("wrong_parent","FIXED_HOST_PID_BIRTH_PARENT_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["system_server"].update(parent_host_pid=3588093)))
    no("boolean_pid","FIXED_HOST_PID_BIRTH_PARENT_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["daemon"].update(host_pid=True)))
    no("wrong_uid","FIXED_UID_OR_NAMESPACE_PID_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["system_server"].update(uids=[0]*4)))
    no("namespace_pid_swap","FIXED_UID_OR_NAMESPACE_PID_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["system_server"].update(namespace_pids=[90516,830])))
    no("wrong_mnt_ns","FIXED_NAMESPACE_OR_CGROUP_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["zygote64"]["namespaces"].update(mnt="mnt:[4026533284]")))
    no("foreign_cgroup","FIXED_NAMESPACE_OR_CGROUP_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["system_server"].update(cgroup=["0::/unrelated"])))
    no("wrong_new_executable","NEW_ROLE_EXECUTABLE_OR_ARGV_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["zygote64"].update(executable="/unrelated")))
    no("argv_append","NEW_ROLE_EXECUTABLE_OR_ARGV_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["system_server"].update(cmdline=["system_server","extra"])))
    no("surviving_full_argv_changed","SURVIVING_FULL_HISTORICAL_IDENTITY_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["daemon"].update(cmdline=["/different"])))
    no("wrong_root","FIXED_PROCESS_ROOT_DIFFERS",
       lambda:inspect_edit(lambda s,a,r:r["android_init"].update(inode=2)))
    no("missing_role","EXACT_SEVEN_FIXED_ROLES_REQUIRED",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"].pop("surfaceflinger")))
    no("extra_role","EXACT_SEVEN_FIXED_ROLES_REQUIRED",
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"].update(extra=copy.deepcopy(s["binding"]["processes"]["daemon"]))))
    no("foreign_boot","CURRENT_SEVEN_ROLE_SNAPSHOT_INVALID",
       lambda:inspect_edit(lambda s,a,r:s["binding"].update(boot_id="00000000-0000-0000-0000-000000000000")))
    def samples(delta=10_000_000_000,count=3):
        s,a,r=fixture();v=[copy.deepcopy(s) for _ in range(count)]
        if count>=2:v[1]["collected_monotonic_ns"]+=5_000_000_000
        if count>=3:v[2]["collected_monotonic_ns"]+=delta
        return v,a,r
    yes("three_double_samples_10second_span",lambda:p.validate_samples(*samples(),binding_authority=synthetic_authority()))
    no("short_span","OBSERVATION_SPAN_OUTSIDE_EXPLICIT_10_TO_90_SECONDS",
       lambda:p.validate_samples(*samples(9_999_999_999),binding_authority=synthetic_authority()))
    no("overlong_span","OBSERVATION_SPAN_OUTSIDE_EXPLICIT_10_TO_90_SECONDS",
       lambda:p.validate_samples(*samples(90_000_000_001),binding_authority=synthetic_authority()))
    no("only_two_samples","EXACT_THREE_DOUBLE_SAMPLES_REQUIRED",lambda:p.validate_samples(*samples(count=2),binding_authority=synthetic_authority()))
    no("old_deploy_not_verified","HISTORICAL_DEPLOYMENT_NOT_VERIFIED",
       lambda:p.historical({"main_deployed":False},{"main_deployed":True}))
    no("duplicate_json_field","DUPLICATE_JSON_FIELD",lambda:p.parse(b'{"a":1,"a":2}'))
    no("nonfinite_json","NONFINITE_JSON_NUMBER",lambda:p.parse(b'{"a":NaN}'))
    def current_fixture():
        ss,a,r=samples();last=ss[-1];rows=last["binding"]["processes"]
        out={"schema":p.SCHEMA,"kind":"current-cell-generation","deployment_performed":False,
          "old_epoch_sha256":p.OLD_EPOCH,"framework_epoch":p.android_epoch(last,binding_authority=synthetic_authority()),
          "previous_current_baseline":copy.deepcopy(p.PREVIOUS_BASELINE),
          "discovery_observation":copy.deepcopy(p.DISCOVERY),"owner_lineage":lineage_fixture(),
          "previous_executable_content":{},"surviving_host_executable_backing_equal":True,
          "previous_cell_runtime_authority_transferred":False,
          "historical_deployment":{"activation_path":p.ACTIVATION_PATH,"activation_bytes":p.ACTIVATION_BYTES,
              "activation_sha256":p.ACTIVATION_SHA,"verification_path":p.VERIFIED_PATH,"verification_sha256":p.VERIFIED_SHA},
          "daemon_process":rows["daemon"],"launcher_process":rows["launcher"],"presenter_process":rows["presenter"],
          "status":{"host_pid":p.EXPECTED["launcher"]["pid"]},"all_seven_processes":last,"process_roots":r,
          "sample_monotonic_ns":[x["collected_monotonic_ns"] for x in ss],"sample_span_ns":10_000_000_000,
          "three_double_samples_equal":True,"bounded_observation_is_not_future_stability_proof":True,
          "limits":dict(p.LIMITS),"cell_config":{},"engine_sha256":p.ENGINE_SHA,"presenter_sha256":p.PRESENTER_SHA,
          "engine_artifact":{},"current_process_executables":{},"current_package_source":{},
          "packages":dict(p.TARGET_UIDS),"app_directories":{},"classpath":{},"held_helper_static_qualification":{},
          "current_service":{},"namespace_entry":False,"Android_commands":0,"UI_actions":0,"App_launches":0,
          "helper_installs":0,"framework_exit_cause_resolved":False,"whole_app_production_ready":False,
          "production_gate":{"unresolved_framework_exit_cause":True,"repeated_crash_freedom_proved":False,
                             "business_acceptance_proved":False}}
        def file(n=4):
            return {"st_dev":106,"st_ino":17,"st_mode":33188,"st_uid":0,"st_gid":0,"st_nlink":1,
                    "st_size":n,"st_mtime_ns":1,"st_ctime_ns":1}
        def art(digest="a"*64):
            return {"bytes":4,"sha256":digest,"file":file()}
        out["engine_artifact"]=art(p.ENGINE_SHA)
        out["current_process_executables"]={role:art(p.PRESENTER_SHA if role=="presenter" else "b"*64) for role in p.ROLES}
        out["previous_executable_content"]=p.executable_content(out["current_process_executables"])
        out["cell_config"]={"path":p.CELL_PATH,**art(p.CELL_SHA)}
        out["current_package_source"]={"source_sha256":"c"*64,"source_bytes":4,"source_metadata":file(),"selected":dict(p.TARGET_UIDS)}
        out["app_directories"]={kind+"/0/"+package:{"device":106,"inode":18,"uid":p.TARGET_UIDS[package],"gid":p.TARGET_UIDS[package]}
                               for kind in ("user","user_de") for package in p.TARGETS}
        out["classpath"]={"values":{"BOOTCLASSPATH":"/system/framework/fixed.jar","DEX2OATBOOTCLASSPATH":"/system/framework/fixed.jar"},
            "files":[{"path":"/system/framework/fixed.jar","sha256":"d"*64,"bytes":4,
                      "init_view":file(),"zygote_view":file(),"same_backing_verified":True}],
            "total_bytes":4,"paired_complete":True,
            "limits":{"deadline_seconds":45,"path_count":256,"per_file_bytes":134217728,"total_bytes":805306368},
            "different_mount_namespaces_permitted":True,"different_backing_files_permitted":False}
        out["held_helper_static_qualification"]={
            "source_sha256":"adf5b08f7854bec061ab8d2a208f3414339701c816218881e6550afde2e6c31c",
            "binary_sha256":"21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689",
            "qualification_sha256":"3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3",
            "whole_process_tree_cleanup_qualified":False}
        out["current_service"]={"MainPID":"3588022","ControlGroup":"/system.slice/droidloomd.service",
            "InvocationID":p.INVOCATION,"ActiveState":"active","SubState":"running","NRestarts":"0",
            "ExecMainStartTimestampMonotonic":"807969950841"}
        return out
    # Synthetic complete data exercises the actual pure validators; it is never
    # represented as a private historical deployment or current device sample.
    def check_baseline(value):
        return p.validate_new_baseline(value,binding_authority=synthetic_authority())
    yes("new_schema_not_new_deployment",lambda:check_baseline(current_fixture()))
    def altered(**fields):
        b=current_fixture();b.update(fields);return check_baseline(b)
    no("no_fake_main_deployed","CURRENT_BASELINE_MUST_NOT_IMPERSONATE_DEPLOYMENT",lambda:altered(main_deployed=True))
    no("unresolved_cause_not_upgraded","UNRESOLVED_CAUSE_AND_PRODUCTION_BOUNDARY_REQUIRED",
       lambda:altered(framework_exit_cause_resolved=True))
    no("production_not_upgraded","UNRESOLVED_CAUSE_AND_PRODUCTION_BOUNDARY_REQUIRED",
       lambda:altered(whole_app_production_ready=True))
    no("baseline_never_launches","BASELINE_READONLY_SCOPE_CHANGED",lambda:altered(App_launches=1))
    no("baseline_count_not_boolean","BASELINE_READONLY_SCOPE_CHANGED",lambda:altered(UI_actions=False))
    def bad_artifact():
        b=current_fixture();b["current_process_executables"].pop("launcher")
        return check_baseline(b)
    no("missing_current_executable_proof","ALL_SEVEN_CURRENT_EXECUTABLES_REQUIRED",bad_artifact)
    def wrong_pair():
        b=current_fixture();b["classpath"]["files"][0]["zygote_view"]["st_ino"]+=1
        return check_baseline(b)
    no("different_classpath_backing","PAIRED_CLASSPATH_BACKING_MISMATCH",wrong_pair)
    # New cell-specific constraints use the unchanged production functions with
    # an explicit synthetic authority argument; production omits that argument.
    yes("actual_authority_schema_from_fixed_discovery",lambda:p.authority()==p.CURRENT_BINDING)
    yes("complete_discovery_identity_hash_map",
        lambda:p.match_discovery_identities(fixture()[0]["binding"]["processes"],synthetic_authority()))
    def hash_changed():
        rows=fixture()[0]["binding"]["processes"];rows["daemon"]["cmdline"].append("different")
        return p.match_discovery_identities(rows,synthetic_authority())
    no("complete_identity_hash_change_rejected","CURRENT_FULL_IDENTITIES_DIFFER_FROM_ACTUAL_DISCOVERY",hash_changed)
    def missing_authority_role():
        value=synthetic_authority();value["role_identity_sha256"].pop("daemon");return p.authority(value)
    no("missing_authority_role","EXACT_DISCOVERY_AUTHORITY_SCHEMA",missing_authority_role)
    no("owner_program_not_inherited_by_pid","CURRENT_OWNER_HISTORICAL_PROGRAM_DIFFERS",
        lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["launcher"].update(executable="/other-owner")))
    def wrong_epoch():
        bound=synthetic_authority();bound["framework_epoch_sha256"]=p.PREVIOUS_BASELINE["epoch_sha256"]
        return bool(p.android_epoch(fixture()[0],binding_authority=bound))
    no("previous_epoch_not_substituted_for_current","ACTUAL_DISCOVERED_EPOCH_DIFFERS",wrong_epoch)
    def lineage_edit(edit):
        value=lineage_fixture();bound=synthetic_authority();edit(value)
        return p.validate_cell_lineage(value,binding_authority=bound)
    yes("complete_three_link_owner_lineage",lambda:p.validate_cell_lineage(lineage_fixture(),binding_authority=synthetic_authority()))
    def replace_daemon_children(value,children):
        table=value["child_tables"]["daemon"];table["per_thread"][str(p.EXPECTED["daemon"]["pid"])]=children
        table["child_host_pids"]=children
    no("owner_missing_from_complete_table","OWNER_SINGLE_DIRECT_CHILD_REQUIRED",
        lambda:lineage_edit(lambda x:replace_daemon_children(x,[])))
    no("foreign_second_daemon_child","OWNER_SINGLE_DIRECT_CHILD_REQUIRED",
        lambda:lineage_edit(lambda x:replace_daemon_children(x,[p.EXPECTED["launcher"]["pid"],2147483647])))
    no("omitted_thread_in_complete_table","COMPLETE_OWNER_THREAD_SET_REQUIRED",
        lambda:lineage_edit(lambda x:x["child_tables"]["daemon"]["per_thread"].clear()))
    no("duplicate_per_thread_child","COMPLETE_OWNER_PER_THREAD_CHILDREN_REQUIRED",
        lambda:lineage_edit(lambda x:replace_daemon_children(x,[p.EXPECTED["launcher"]["pid"]]*2)))
    no("child_union_incomplete","COMPLETE_OWNER_CHILD_UNION_REQUIRED",
        lambda:lineage_edit(lambda x:x["child_tables"]["daemon"].update(child_host_pids=[])))
    def extra_empty_thread(value):
        table=value["child_tables"]["daemon"];tid=p.EXPECTED["daemon"]["pid"]+1
        table["thread_ids"].append(tid);table["per_thread"][str(tid)]=[]
    no("changed_complete_table_digest","OWNER_KERNEL_TABLE_DIFFERS_FROM_DISCOVERY",
        lambda:lineage_edit(extra_empty_thread))
    no("intermediary_foreign_parent","FIXED_HOST_PID_BIRTH_PARENT_DIFFERS",
        lambda:lineage_edit(lambda x:x["intermediary_process"].update(parent_host_pid=1)))
    no("intermediary_argv_changed","CURRENT_INTERMEDIARY_IDENTITY_DIFFERS",
        lambda:lineage_edit(lambda x:x["intermediary_process"].update(cmdline=["/other"])))
    no("intermediary_not_promoted_to_program_authority","CURRENT_OWNER_LINEAGE_SCHEMA",
        lambda:lineage_edit(lambda x:x.update(intermediary_program_authority_assigned=True)))
    no("user_namespace_wrong_syntax","FRESH_HOST_AND_ROLE_USER_NAMESPACES_REQUIRED",
        lambda:lineage_edit(lambda x:x.update(host_user_namespace="pid:[42]")))
    no("foreign_role_user_namespace","FRESH_HOST_AND_ROLE_USER_NAMESPACES_REQUIRED",
        lambda:lineage_edit(lambda x:x["role_user_namespaces"].update(zygote64="user:[43]")))
    no("missing_role_user_namespace","FRESH_HOST_AND_ROLE_USER_NAMESPACES_REQUIRED",
        lambda:lineage_edit(lambda x:x["role_user_namespaces"].pop("system_server")))
    no("boolean_user_namespace","FRESH_HOST_AND_ROLE_USER_NAMESPACES_REQUIRED",
        lambda:lineage_edit(lambda x:x.update(intermediary_user_namespace=True)))
    yes("three_equal_owner_lineage_samples",
        lambda:p.validate_lineage_samples([lineage_fixture() for _ in range(3)],binding_authority=synthetic_authority()))
    no("two_owner_lineage_samples_rejected","THREE_COMPLETE_OWNER_LINEAGE_SAMPLES_REQUIRED",
        lambda:p.validate_lineage_samples([lineage_fixture() for _ in range(2)],binding_authority=synthetic_authority()))
    def changed_user_namespace_sample():
        values=[lineage_fixture() for _ in range(3)]
        values[2].update(host_user_namespace="user:[43]",intermediary_user_namespace="user:[43]",
                         role_user_namespaces={k:"user:[43]" for k in p.ROLES})
        return p.validate_lineage_samples(values,binding_authority=synthetic_authority())
    no("individually_valid_user_namespace_changed","OWNER_LINEAGE_OR_USER_NAMESPACE_SAMPLES_CHANGED",changed_user_namespace_sample)
    no("v1_baseline_not_v2_authority","CURRENT_BASELINE_MUST_NOT_IMPERSONATE_DEPLOYMENT",
        lambda:altered(schema="pocket4-main-current-baseline-v1"))
    def previous_pin_changed():
        value=current_fixture();value["previous_current_baseline"]["sha256"]="a"*64
        return check_baseline(value)
    no("previous_baseline_pin_cannot_change","PREVIOUS_CELL_LINEAGE_IS_NOT_RUNTIME_AUTHORITY",previous_pin_changed)
    no("old_cell_task_authority_never_transferred","PREVIOUS_CELL_LINEAGE_IS_NOT_RUNTIME_AUTHORITY",
        lambda:altered(previous_cell_runtime_authority_transferred=True))
    def executable_changed():
        value=current_fixture();value["current_process_executables"]["zygote64"]["sha256"]="e"*64
        return check_baseline(value)
    no("changed_executable_content_lineage","CURRENT_EXECUTABLE_CONTENT_LINEAGE_CHANGED",executable_changed)
    def previous_executable_missing():
        value=current_fixture();value["previous_executable_content"].pop("launcher");return check_baseline(value)
    no("missing_previous_executable_pin","PREVIOUS_SEVEN_EXECUTABLE_CONTENT_PINS_REQUIRED",previous_executable_missing)
    no("host_backing_lineage_not_claimed","SURVIVING_HOST_EXECUTABLE_LINEAGE_REQUIRED",
        lambda:altered(surviving_host_executable_backing_equal=False))
    def discovery_changed():
        value=current_fixture();value["discovery_observation"]["job_id"]="different"
        return check_baseline(value)
    no("discovery_job_binding_changed","PREVIOUS_CELL_LINEAGE_IS_NOT_RUNTIME_AUTHORITY",discovery_changed)
    def production_omits_synthetic_authority():
        checks={"validate_snapshot","validate_samples","android_epoch","validate_new_baseline",
                "validate_cell_lineage","validate_lineage_samples","match_discovery_identities"}
        count=0
        for name in ("qualify_baseline.py","cell_ancestry.py","current_baseline_guard.template.py"):
            text=encoded[name].decode()
            if name.endswith(".template.py"):
                for marker in ("@@BASELINE_SHA@@","@@QUALIFICATION_SHA@@","@@CURRENT_EPOCH@@","@@MANIFEST_SHA@@"):
                    text=text.replace(marker,"f"*64)
                for marker in ("@@BASELINE_BYTES@@","@@QUALIFICATION_BYTES@@"):text=text.replace(marker,"1")
            tree=ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in checks:
                    p.need(not any(x.arg=="binding_authority" for x in node.keywords),
                           "PRODUCTION_MUST_USE_FIXED_ACTUAL_AUTHORITY")
                    count+=1
        p.need(count>=8,"PRODUCTION_DISCOVERY_GUARD_CALLS_MISSING")
        return True
    yes("production_calls_fixed_actual_authority",production_omits_synthetic_authority)
    no("boolean_intermediary_root_not_measurement","CURRENT_INTERMEDIARY_ROOT_PROOF_REQUIRED",
        lambda:lineage_edit(lambda x:x["intermediary_root"].update(inode=True)))
    def changed_intermediary_root_sample():
        values=[lineage_fixture() for _ in range(3)];values[2]["intermediary_root"]["inode"]+=1
        return p.validate_lineage_samples(values,binding_authority=synthetic_authority())
    no("intermediary_root_changed_between_samples","OWNER_LINEAGE_OR_USER_NAMESPACE_SAMPLES_CHANGED",changed_intermediary_root_sample)
    def projection_is_closed_and_measured():
        s,_,r=fixture();lineage=lineage_fixture()
        out=p.protected_process_projection(s,r,lineage,binding_authority=synthetic_authority())
        fields={"host_pid","parent_host_pid","start_ticks","uids","namespace_pids","cgroup","namespaces","root_identity"}
        p.need(set(out)==set(p.ROLES)|{"owner_intermediary"} and all(set(v)==fields for v in out.values()),
               "PROTECTED_PROJECTION_CLOSED_FIELDS")
        p.need(all(v["namespaces"]["user"]=="user:[42]" for v in out.values()) and
               out["owner_intermediary"]["root_identity"]==lineage["intermediary_root"] and
               all(out[k]["root_identity"]==r[k] for k in p.ROLES),"PROTECTED_PROJECTION_MUST_USE_ACTUAL_INPUTS")
        return True
    yes("eight_role_projection_closed_and_measured",projection_is_closed_and_measured)
    p.need(len(names)==66,"EXACT_66_BASELINE_CONTROLS_REQUIRED")
    return {"all_passed":True,"count":len(names),"cases":names,"files_opened":0,
            "processes_spawned":0,"Android_commands":0,"private_deployment_fixture_claimed":False,
            "compiled_sources":sorted(compiled),"guard_template_values_are_syntax_only":True}
