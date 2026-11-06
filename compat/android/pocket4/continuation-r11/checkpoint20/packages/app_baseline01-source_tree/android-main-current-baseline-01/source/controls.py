"""Pure boundary controls. No files, processes, Android API or mock epoch adoption."""
import copy
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
    p.need(len(compiled)==7,"EXACT_SEVEN_SOURCE_COMPILATIONS_REQUIRED")
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
    def inspect_edit(edit):
        s,a,r=fixture();edit(s,a,r);s["sha256"]=p.sha(p.canonical(s["binding"]))
        return p.validate_snapshot(s,a,r)
    yes("fixed_7_roles_and_separate_mount_namespaces",lambda:p.validate_snapshot(*fixture()))
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
       lambda:inspect_edit(lambda s,a,r:s["binding"]["processes"]["launcher"].update(cmdline=["/different"])))
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
    yes("three_double_samples_10second_span",lambda:p.validate_samples(*samples()))
    no("short_span","OBSERVATION_SPAN_OUTSIDE_EXPLICIT_10_TO_90_SECONDS",
       lambda:p.validate_samples(*samples(9_999_999_999)))
    no("overlong_span","OBSERVATION_SPAN_OUTSIDE_EXPLICIT_10_TO_90_SECONDS",
       lambda:p.validate_samples(*samples(90_000_000_001)))
    no("only_two_samples","EXACT_THREE_DOUBLE_SAMPLES_REQUIRED",lambda:p.validate_samples(*samples(count=2)))
    no("old_deploy_not_verified","HISTORICAL_DEPLOYMENT_NOT_VERIFIED",
       lambda:p.historical({"main_deployed":False},{"main_deployed":True}))
    no("duplicate_json_field","DUPLICATE_JSON_FIELD",lambda:p.parse(b'{"a":1,"a":2}'))
    no("nonfinite_json","NONFINITE_JSON_NUMBER",lambda:p.parse(b'{"a":NaN}'))
    def current_fixture():
        ss,a,r=samples();last=ss[-1];rows=last["binding"]["processes"]
        out={"schema":p.SCHEMA,"kind":"current-framework-generation","deployment_performed":False,
          "old_epoch_sha256":p.OLD_EPOCH,"framework_epoch":p.android_epoch(last),
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
    yes("new_schema_not_new_deployment",lambda:p.validate_new_baseline(current_fixture()))
    def altered(**fields):
        b=current_fixture();b.update(fields);return p.validate_new_baseline(b)
    no("no_fake_main_deployed","CURRENT_BASELINE_MUST_NOT_IMPERSONATE_DEPLOYMENT",lambda:altered(main_deployed=True))
    no("unresolved_cause_not_upgraded","UNRESOLVED_CAUSE_AND_PRODUCTION_BOUNDARY_REQUIRED",
       lambda:altered(framework_exit_cause_resolved=True))
    no("production_not_upgraded","UNRESOLVED_CAUSE_AND_PRODUCTION_BOUNDARY_REQUIRED",
       lambda:altered(whole_app_production_ready=True))
    no("baseline_never_launches","BASELINE_READONLY_SCOPE_CHANGED",lambda:altered(App_launches=1))
    no("baseline_count_not_boolean","BASELINE_READONLY_SCOPE_CHANGED",lambda:altered(UI_actions=False))
    def bad_artifact():
        b=current_fixture();b["current_process_executables"].pop("launcher")
        return p.validate_new_baseline(b)
    no("missing_current_executable_proof","ALL_SEVEN_CURRENT_EXECUTABLES_REQUIRED",bad_artifact)
    def wrong_pair():
        b=current_fixture();b["classpath"]["files"][0]["zygote_view"]["st_ino"]+=1
        return p.validate_new_baseline(b)
    no("different_classpath_backing","PAIRED_CLASSPATH_BACKING_MISMATCH",wrong_pair)
    p.need(len(names)==32,"EXACT_32_BASELINE_CONTROLS_REQUIRED")
    return {"all_passed":True,"count":len(names),"cases":names,"files_opened":0,
            "processes_spawned":0,"Android_commands":0,"private_deployment_fixture_claimed":False,
            "compiled_sources":sorted(compiled),"guard_template_values_are_syntax_only":True}
