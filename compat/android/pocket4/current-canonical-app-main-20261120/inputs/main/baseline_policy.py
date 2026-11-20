"""Fixed new cell identity policy. Pure validation; no deployment or action authority."""
import hashlib,json,re,stat
SCHEMA="pocket4-main-current-baseline-v2"
QUAL_SCHEMA="pocket4-main-current-baseline-qualification-v2"
OLD_EPOCH="48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f"
BOOT_ID="981ff371-cd72-4f81-9be3-a862111afdb1"
INVOCATION="67cdc2375f394012ad9d7f39b0d77426"
ACTIVATION_PATH="/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json"
ACTIVATION_SHA="7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615"
ACTIVATION_BYTES=63675
VERIFIED_PATH="/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-verified-01.json"
VERIFIED_SHA="2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387"
CELL_PATH="/etc/droidloom/cell.json"
CELL_SHA="f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc"
ENGINE_SHA="c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d"
PRESENTER_SHA="47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24"
LIMITS={"cpu.max":"200000 100000","memory.high":"5368709120","memory.max":"6442450944","memory.swap.max":"max","pids.max":"12288"}
TARGET_UIDS={"tv.danmaku.bili":10117,"com.ihg.apps.android":10137,"com.amazon.mShop.android.shopping":10129,"com.bestbuy.android":10130,"local.pocket4.actions.v2":10125}
TARGETS=tuple(x for x in TARGET_UIDS if x!="local.pocket4.actions.v2")
EXPECTED=json.loads("{\"android_init\":{\"pid\":3268779,\"start_ticks\":99615082,\"ppid\":3268775,\"uids\":[0,0,0,0],\"namespace_pids\":[3268779,1],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533280]\",\"pid\":\"pid:[4026533285]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"daemon\":{\"pid\":3588022,\"start_ticks\":80796995,\"ppid\":1,\"uids\":[0,0,0,0],\"namespace_pids\":[3588022],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026531832]\",\"pid\":\"pid:[4026531836]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"launcher\":{\"pid\":3268774,\"start_ticks\":99615080,\"ppid\":3588022,\"uids\":[0,0,0,0],\"namespace_pids\":[3268774],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533279]\",\"pid\":\"pid:[4026531836]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"presenter\":{\"pid\":3588024,\"start_ticks\":80796995,\"ppid\":2472,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[3588024],\"cgroup\":\"0::/user.slice/user-1000.slice/user@1000.service/app.slice/droidloom.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026531832]\",\"pid\":\"pid:[4026531836]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"surfaceflinger\":{\"pid\":3270350,\"start_ticks\":99615245,\"ppid\":3268779,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[3270350,661],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_1000/pid_661\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533280]\",\"pid\":\"pid:[4026533285]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"zygote64\":{\"pid\":3270325,\"start_ticks\":99615242,\"ppid\":3268779,\"uids\":[0,0,0,0],\"namespace_pids\":[3270325,638],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_0/pid_638\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533718]\",\"pid\":\"pid:[4026533285]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"system_server\":{\"pid\":3270611,\"start_ticks\":99615342,\"ppid\":3270325,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[3270611,808],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_1000/pid_808\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533719]\",\"pid\":\"pid:[4026533285]\"},\"root_identity\":{\"device\":106,\"inode\":1}}}")
EXPECTED_INTERMEDIARY=json.loads("{\"pid\":3268775,\"start_ticks\":99615082,\"ppid\":3268774,\"uids\":[0,0,0,0],\"namespace_pids\":[3268775],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533280]\",\"pid\":\"pid:[4026531836]\"}}")
CURRENT_BINDING=json.loads("{\"role_identity_sha256\":{\"daemon\":\"0c97203b9dcf0334fb796b6d5264dba1df3644f048180f709b687671a37e7aaa\",\"launcher\":\"b1a6ea5384d7096772650aa7ea3f4db22b70b112d054521e339fea4df3f3c830\",\"presenter\":\"346c6eef8623ebdd359432bf8609b143590db470d4e0b5778e17fc312888326c\",\"android_init\":\"25b9e20a0d7fe4a67a4ed645223532be0af4df4f0923385c63bf8575d44fdf01\",\"zygote64\":\"2ea56f66613caa7850652ef19476df4356ad808bae94e9e9cedba476f71a06f4\",\"system_server\":\"58cd65beff51ea53cd38c3cf021d89fd2a19527759efb5c5756c06cb9ab6c2b9\",\"surfaceflinger\":\"8e1106acb9eb02b802e85b331b492593092e66c9570c052ed94b92fd99f89c76\"},\"intermediary_identity_sha256\":\"2705458a631597a25618cf841426fd6319ab5c3f7aae051c1f037cf480416a33\",\"framework_epoch_sha256\":\"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\",\"child_table_sha256\":{\"daemon\":\"15eebd4b58f9779cfd805e3fb0468877b9111a02b3e7883ac70a36087716f2a8\",\"launcher\":\"e433d7ebbbd21219f1c07c1efc44ed2db14b5b12ddc276715aebb38b3bf5a9bb\",\"intermediary\":\"01bc1128edf84a16ed5d46d117083fbf91fbd482082364a787f5cd9c08e0de82\"}}")
DISCOVERY=json.loads("{\"job_id\":\"1a1b11bc7e8-fc05-75d8\",\"git_tree\":\"644a1a101ddde89b189159f8d5681373190eed92\",\"git_blob_sha\":\"0d43d38e27252d1ee4a4c42015b216c52ba7d255\",\"stdout\":{\"bytes\":17817,\"sha256\":\"5f029ed98fa932f060a3617764b29485f09a4b09e1052c280ffd925235f488ae\"},\"source\":{\"bytes\":48747,\"sha256\":\"2d4808c6ae499443302dc4ecc195116a4e4a4ccb2a52d589ca995cda42173f3b\"},\"framework_epoch_sha256\":\"7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c\",\"authenticated_daemon_status_supplied_owner\":true,\"complete_unique_kernel_chain\":true,\"old_helpers_or_tasks_reauthorized\":false,\"installed_Main_source_version_verified\":false}")
PREVIOUS_BASELINE=json.loads("{\"path\":\"/home/alex/work/pocket4-main-current-baseline-01/baseline.private.json\",\"bytes\":41844,\"sha256\":\"163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266\",\"epoch_sha256\":\"734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2\"}")
CHAIN_PARENTS=json.loads("[{\"role\":\"daemon\",\"pid\":3588022,\"child\":3268774},{\"role\":\"launcher\",\"pid\":3268774,\"child\":3268775},{\"role\":\"intermediary\",\"pid\":3268775,\"child\":3268779}]")
ROLES=tuple(EXPECTED)
ANDROID_ROLES=("init","zygote64","system_server","surfaceflinger")
OLD_ROLES={"zygote64":(3588887,80797153),"system_server":(3589120,80797249)}
IDENTITY_KEYS={"host_pid","parent_host_pid","start_ticks","namespace_pids","uids","cmdline","executable","namespaces","cgroup"}
def need(value,code):
    if not value:raise RuntimeError(code)
def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def no_duplicates(pairs):
    out={}
    for key,value in pairs:
        need(key not in out,"DUPLICATE_JSON_FIELD")
        out[key]=value
    return out
def reject_number(_):raise RuntimeError("NONFINITE_JSON_NUMBER")
def parse(raw):
    return json.loads(raw,object_pairs_hook=no_duplicates,parse_constant=reject_number)
def historical(activation,verified):
    need(activation.get("main_deployed") is True and verified.get("main_deployed") is True,
         "HISTORICAL_DEPLOYMENT_NOT_VERIFIED")
    old=activation["framework_epoch"]
    need(old.get("schema")=="pocket4-framework-epoch-v1" and
         old.get("sha256")==OLD_EPOCH==sha(canonical(old["binding"])) and
         old["binding"].get("boot_id")==BOOT_ID and
         verified.get("framework_epoch_sha256")==OLD_EPOCH,"HISTORICAL_EPOCH_PIN_DIFFERS")
    need(activation.get("engine_sha256")==ENGINE_SHA and
         activation.get("presenter_sha256")==PRESENTER_SHA and
         activation.get("limits")==LIMITS,"HISTORICAL_DEPLOYED_ARTIFACT_OR_LIMIT_DIFFERS")
    for role,(pid,birth) in OLD_ROLES.items():
        row=old["binding"]["processes"][role]
        need(row["host_pid"]==pid and row["start_ticks"]==birth,"HISTORICAL_OLD_ROLE_DIFFERS")
    need(all(activation["packages"].get(k)==v for k,v in TARGET_UIDS.items()),
         "HISTORICAL_FIXED_PACKAGE_UID_DIFFERS")
    need(type(activation["status"].get("host_pid")) is int and
         activation["status"]["host_pid"]==3588089,"HISTORICAL_CELL_OWNER_DIFFERS")
    return True
def old_survivors(activation):
    p=activation["framework_epoch"]["binding"]["processes"]
    return {"daemon":activation["daemon_process"],"presenter":activation["presenter_process"]}
def validate_identity(role,row,expected,old=None):
    need(type(row) is dict and set(row)==IDENTITY_KEYS,"FULL_PROCESS_IDENTITY_SCHEMA")
    need(type(row["host_pid"]) is int and type(row["start_ticks"]) is int and
         type(row["parent_host_pid"]) is int and row["host_pid"]==expected["pid"] and
         row["start_ticks"]==expected["start_ticks"] and row["parent_host_pid"]==expected["ppid"],
         "FIXED_HOST_PID_BIRTH_PARENT_DIFFERS")
    need(row["uids"]==expected["uids"] and all(type(n) is int for n in row["uids"]) and
         row["namespace_pids"]==expected["namespace_pids"] and
         all(type(n) is int for n in row["namespace_pids"]),"FIXED_UID_OR_NAMESPACE_PID_DIFFERS")
    need(row["namespaces"]=={k:expected["namespaces"][k] for k in ("pid","mnt")} and
         row["cgroup"]==expected["cgroup"].splitlines(),"FIXED_NAMESPACE_OR_CGROUP_DIFFERS")
    need(type(row["cmdline"]) is list and 0<len(row["cmdline"])<=64 and
         all(type(x) is str and 0<len(x.encode())<=65536 and "\0" not in x for x in row["cmdline"]) and
         type(row["executable"]) is str and row["executable"].startswith("/") and
         "\0" not in row["executable"],"PROCESS_EXECUTABLE_OR_ARGV_SCHEMA")
    if old is not None:need(row==old,"SURVIVING_FULL_HISTORICAL_IDENTITY_DIFFERS")
    if role in ("zygote64","system_server"):
        need(row["cmdline"]==[role] and row["executable"]=="/system/bin/app_process64",
             "NEW_ROLE_EXECUTABLE_OR_ARGV_DIFFERS")
    if role=="android_init":
        need(row["executable"]=="/system/bin/init" and row["cmdline"][0]=="/init",
             "INIT_ROLE_EXECUTABLE_DIFFERS")
    if role=="surfaceflinger":
        need(row["executable"]=="/system/bin/surfaceflinger" and
             row["cmdline"]==["/system/bin/surfaceflinger"],"SURFACEFLINGER_ROLE_DIFFERS")
    return True
def validate_snapshot(snapshot,activation,roots,*,binding_authority=None):
    need(snapshot.get("schema")=="pocket4-framework-epoch-v1" and
         snapshot.get("sha256")==sha(canonical(snapshot["binding"])) and
         snapshot["binding"].get("boot_id")==BOOT_ID,"CURRENT_SEVEN_ROLE_SNAPSHOT_INVALID")
    rows=snapshot["binding"]["processes"]
    need(set(rows)==set(ROLES) and set(roots)==set(ROLES),"EXACT_SEVEN_FIXED_ROLES_REQUIRED")
    originals=old_survivors(activation)
    for role,expected in EXPECTED.items():
        validate_identity(role,rows[role],expected,originals.get(role))
        need(roots[role]==expected["root_identity"],"FIXED_PROCESS_ROOT_DIFFERS")
    need(rows["system_server"]["parent_host_pid"]==rows["zygote64"]["host_pid"] and
         rows["zygote64"]["parent_host_pid"]==rows["android_init"]["host_pid"] and
         rows["surfaceflinger"]["parent_host_pid"]==rows["android_init"]["host_pid"] and
         rows["launcher"]["parent_host_pid"]==rows["daemon"]["host_pid"] and
         rows["android_init"]["parent_host_pid"]==EXPECTED_INTERMEDIARY["pid"],
         "NEW_FRAMEWORK_ANCESTRY_DIFFERS")
    need(rows["launcher"]["cmdline"]==activation["launcher_process"]["cmdline"] and
         rows["launcher"]["executable"]==activation["launcher_process"]["executable"],
         "CURRENT_OWNER_HISTORICAL_PROGRAM_DIFFERS")
    match_discovery_identities(rows,binding_authority)
    return True
def android_epoch(snapshot,*,binding_authority=None):
    rows=snapshot["binding"]["processes"]
    selected={"init":rows["android_init"],**{k:rows[k] for k in ANDROID_ROLES if k!="init"}}
    body={"boot_id":BOOT_ID,"processes":selected}
    digest=sha(canonical(body))
    need(digest not in (OLD_EPOCH,PREVIOUS_BASELINE["epoch_sha256"]),"OLD_EPOCH_MUST_NOT_BE_REAUTHORIZED")
    need(digest==authority(binding_authority)["framework_epoch_sha256"],"ACTUAL_DISCOVERED_EPOCH_DIFFERS")
    return {"schema":"pocket4-framework-epoch-v1","binding":body,"sha256":digest,
            "collected_monotonic_ns":snapshot["collected_monotonic_ns"]}
def validate_samples(samples,activation,roots,*,binding_authority=None):
    need(type(samples) is list and len(samples)==3,"EXACT_THREE_DOUBLE_SAMPLES_REQUIRED")
    for value in samples:validate_snapshot(value,activation,roots,binding_authority=binding_authority)
    need(all(x["binding"]==samples[0]["binding"] for x in samples),"SAMPLED_IDENTITY_CHANGED")
    times=[x["collected_monotonic_ns"] for x in samples]
    need(all(type(x) is int and x>0 for x in times) and times==sorted(set(times)) and
         10_000_000_000<=times[-1]-times[0]<=90_000_000_000,
         "OBSERVATION_SPAN_OUTSIDE_EXPLICIT_10_TO_90_SECONDS")
    return True
def valid_sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}",value) is not None
def validate_artifact(row,expected=None):
    need(type(row) is dict and set(row)=={"bytes","sha256","file"} and
         type(row["bytes"]) is int and 0<row["bytes"]<=268435456 and valid_sha(row["sha256"]) and
         (expected is None or row["sha256"]==expected),"CURRENT_ARTIFACT_PROOF_REQUIRED")
    f=row["file"]
    keys={"st_dev","st_ino","st_mode","st_uid","st_gid","st_nlink","st_size","st_mtime_ns","st_ctime_ns"}
    need(type(f) is dict and set(f)==keys and all(type(v) is int and v>=0 for v in f.values()) and
         f["st_ino"]>0 and f["st_nlink"]==1 and f["st_size"]==row["bytes"] and
         stat.S_ISREG(f["st_mode"]),"CURRENT_ARTIFACT_FILE_IDENTITY_REQUIRED")
    return True
def validate_artifact_closure(value):
    validate_artifact(value["engine_artifact"],ENGINE_SHA)
    exes=value["current_process_executables"]
    need(type(exes) is dict and set(exes)==set(ROLES),"ALL_SEVEN_CURRENT_EXECUTABLES_REQUIRED")
    for role,row in exes.items():validate_artifact(row,PRESENTER_SHA if role=="presenter" else None)
    cell=value["cell_config"]
    need(set(cell)=={"path","sha256","bytes","file"} and cell["path"]==CELL_PATH and cell["sha256"]==CELL_SHA,
         "CURRENT_CONFIG_PROOF_REQUIRED")
    validate_artifact({k:cell[k] for k in ("sha256","bytes","file")},CELL_SHA)
    pkg=value["current_package_source"]
    need(set(pkg)=={"source_sha256","source_bytes","source_metadata","selected"} and
         valid_sha(pkg["source_sha256"]) and type(pkg["source_bytes"]) is int and 0<pkg["source_bytes"]<=1048576 and
         pkg["selected"]==TARGET_UIDS,"CURRENT_FIXED_UID_SOURCE_PROOF_REQUIRED")
    validate_artifact({"sha256":pkg["source_sha256"],"bytes":pkg["source_bytes"],"file":pkg["source_metadata"]})
    dirs=value["app_directories"];wanted={kind+"/0/"+package for kind in ("user","user_de") for package in TARGETS}
    need(type(dirs) is dict and set(dirs)==wanted,"EIGHT_EXACT_TARGET_DATA_DIRECTORIES_REQUIRED")
    for path,row in dirs.items():
        need(set(row)=={"device","inode","uid","gid"} and all(type(v) is int and v>=0 for v in row.values()) and
             row["inode"]>0 and row["uid"]==TARGET_UIDS[path.split("/")[-1]],"CURRENT_TARGET_DATA_IDENTITY_REQUIRED")
    cp=value["classpath"]
    need(type(cp) is dict and set(cp)=={"values","files","total_bytes","paired_complete","limits",
        "different_mount_namespaces_permitted","different_backing_files_permitted"} and
        cp["paired_complete"] is True and cp["different_mount_namespaces_permitted"] is True and
        cp["different_backing_files_permitted"] is False and
        cp["limits"]=={"deadline_seconds":45,"path_count":256,"per_file_bytes":134217728,"total_bytes":805306368} and
        set(cp["values"])=={"BOOTCLASSPATH","DEX2OATBOOTCLASSPATH"} and type(cp["files"]) is list and
        0<len(cp["files"])<=256,"CURRENT_COMPLETE_PAIRED_CLASSPATH_REQUIRED")
    paths=[]
    for key in ("BOOTCLASSPATH","DEX2OATBOOTCLASSPATH"):
        need(type(cp["values"][key]) is str and 0<len(cp["values"][key].encode())<=32768,
             "CURRENT_SELECTED_CLASSPATH_VALUE_REQUIRED")
        per=cp["values"][key].split(":")
        need(len(per)==len(set(per)) and all(x.startswith("/") and x.endswith(".jar") and
             all(c not in ("",".","..") for c in x[1:].split("/")) for x in per),
             "CURRENT_CLASSPATH_PATH_INVALID")
        paths.extend(per)
    paths=list(dict.fromkeys(paths));need(paths==[x.get("path") for x in cp["files"]],"CLASSPATH_FILES_DO_NOT_MATCH_VALUES")
    total=0
    for row in cp["files"]:
        need(set(row)=={"path","sha256","bytes","init_view","zygote_view","same_backing_verified"} and
             row["same_backing_verified"] is True and type(row["bytes"]) is int and 0<row["bytes"]<=134217728,
             "PAIRED_CLASSPATH_RECORD_REQUIRED")
        for view in ("init_view","zygote_view"):
            validate_artifact({"bytes":row["bytes"],"sha256":row["sha256"],"file":row[view]})
        need(tuple(row["init_view"][k] for k in ("st_dev","st_ino","st_size"))==
             tuple(row["zygote_view"][k] for k in ("st_dev","st_ino","st_size")),"PAIRED_CLASSPATH_BACKING_MISMATCH")
        total+=row["bytes"]
    need(type(cp["total_bytes"]) is int and cp["total_bytes"]==total<=805306368,"CLASSPATH_TOTAL_PROOF_REQUIRED")
    need(value["held_helper_static_qualification"]=={
         "source_sha256":"adf5b08f7854bec061ab8d2a208f3414339701c816218881e6550afde2e6c31c",
         "binary_sha256":"21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689",
         "qualification_sha256":"3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3",
         "whole_process_tree_cleanup_qualified":False},"HISTORICAL_SHARED_HELPER_SCOPE_CHANGED")
    service=value["current_service"]
    need(set(service)=={"MainPID","ControlGroup","InvocationID","ActiveState","SubState","NRestarts","ExecMainStartTimestampMonotonic"} and
         service["MainPID"]=="3588022" and service["ControlGroup"]=="/system.slice/droidloomd.service" and
         service["InvocationID"]==INVOCATION and service["ActiveState"]=="active" and service["SubState"]=="running" and
         service["NRestarts"]=="0" and service["ExecMainStartTimestampMonotonic"]=="807969950841",
         "CURRENT_MAIN_SERVICE_LINEAGE_REQUIRED")
    return True
def validate_new_baseline(value,*,binding_authority=None):
    need(value.get("schema")==SCHEMA and value.get("kind")=="current-cell-generation" and
         "main_deployed" not in value and value.get("deployment_performed") is False,
         "CURRENT_BASELINE_MUST_NOT_IMPERSONATE_DEPLOYMENT")
    required={"schema","kind","deployment_performed","old_epoch_sha256","framework_epoch","historical_deployment",
        "daemon_process","launcher_process","presenter_process","status","all_seven_processes","process_roots",
        "sample_monotonic_ns","sample_span_ns","three_double_samples_equal","bounded_observation_is_not_future_stability_proof",
        "limits","cell_config","engine_sha256","presenter_sha256","engine_artifact","current_process_executables",
        "current_package_source","packages","app_directories","classpath","held_helper_static_qualification","current_service",
        "namespace_entry","Android_commands","UI_actions","App_launches","helper_installs","framework_exit_cause_resolved",
        "whole_app_production_ready","production_gate","previous_current_baseline","discovery_observation",
        "owner_lineage","previous_executable_content","surviving_host_executable_backing_equal",
        "previous_cell_runtime_authority_transferred"}
    need(set(value)==required,"EXACT_CURRENT_BASELINE_FIELDS_REQUIRED")
    all7=value["all_seven_processes"]
    need(all7.get("schema")=="pocket4-framework-epoch-v1" and all7.get("sha256")==sha(canonical(all7["binding"])) and
         all7["binding"].get("boot_id")==BOOT_ID and set(all7["binding"]["processes"])==set(ROLES) and
         value["process_roots"]=={k:v["root_identity"] for k,v in EXPECTED.items()},"CURRENT_SEVEN_ROLE_DOCUMENT_REQUIRED")
    for role,row in all7["binding"]["processes"].items():validate_identity(role,row,EXPECTED[role])
    match_discovery_identities(all7["binding"]["processes"],binding_authority)
    validate_cell_lineage(value["owner_lineage"],binding_authority=binding_authority)
    need(value["previous_current_baseline"]==PREVIOUS_BASELINE and
         value["discovery_observation"]==DISCOVERY and
         value["previous_cell_runtime_authority_transferred"] is False,
         "PREVIOUS_CELL_LINEAGE_IS_NOT_RUNTIME_AUTHORITY")
    need(value["framework_epoch"]==android_epoch(all7,binding_authority=binding_authority),"ANDROID_SUBSET_MUST_BE_FROM_THE_SAME_SEVEN_ROLE_OBSERVATION")
    need(all(value[field]==all7["binding"]["processes"][role] for field,role in
         (("daemon_process","daemon"),("launcher_process","launcher"),("presenter_process","presenter"))) and
         value["status"]=={"host_pid":EXPECTED["launcher"]["pid"]},"HOST_IDENTITY_MUST_BIND_THE_SAME_CAPTURE")
    times=value["sample_monotonic_ns"]
    need(type(times) is list and len(times)==3 and all(type(x) is int and x>0 for x in times) and
         times==sorted(set(times)) and 10_000_000_000<=times[-1]-times[0]<=90_000_000_000 and
         type(value["sample_span_ns"]) is int and value["sample_span_ns"]==times[-1]-times[0] and
         value["three_double_samples_equal"] is True and value["bounded_observation_is_not_future_stability_proof"] is True,
         "EXACT_BOUNDED_OBSERVATION_CLAIM_REQUIRED")
    need(value.get("old_epoch_sha256")==OLD_EPOCH and value["framework_epoch"]["sha256"]!=OLD_EPOCH and
         value["framework_epoch"].get("schema")=="pocket4-framework-epoch-v1" and
         value["framework_epoch"]["sha256"]==sha(canonical(value["framework_epoch"]["binding"])),
         "NEW_FRAMEWORK_EPOCH_DOCUMENT_REQUIRED")
    need(value.get("historical_deployment")=={"activation_path":ACTIVATION_PATH,
         "activation_bytes":ACTIVATION_BYTES,"activation_sha256":ACTIVATION_SHA,
         "verification_path":VERIFIED_PATH,"verification_sha256":VERIFIED_SHA},
         "EXACT_HISTORICAL_DEPLOYMENT_LINEAGE_REQUIRED")
    need(value.get("framework_exit_cause_resolved") is False and
         value.get("whole_app_production_ready") is False and
         value.get("production_gate")=={"unresolved_framework_exit_cause":True,
             "repeated_crash_freedom_proved":False,"business_acceptance_proved":False},
         "UNRESOLVED_CAUSE_AND_PRODUCTION_BOUNDARY_REQUIRED")
    need(value.get("limits")==LIMITS and value.get("packages")==TARGET_UIDS and
         value.get("engine_sha256")==ENGINE_SHA and value.get("presenter_sha256")==PRESENTER_SHA,
         "CURRENT_BOUND_ARTIFACT_OR_UID_OR_LIMIT_DIFFERS")
    need(value.get("namespace_entry") is False and all(type(value.get(k)) is int and value[k]==0 for k in
         ("Android_commands","UI_actions","App_launches","helper_installs")),"BASELINE_READONLY_SCOPE_CHANGED")
    validate_artifact_closure(value)
    validate_executable_content(value["current_process_executables"],value["previous_executable_content"])
    need(value["surviving_host_executable_backing_equal"] is True,"SURVIVING_HOST_EXECUTABLE_LINEAGE_REQUIRED")
    return True

def identity_sha(value):
    return sha(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode())

def authority(supplied=None):
    # Explicit pure-data argument supports synthetic boundary controls. Every
    # runtime caller omits it and is fixed to this source's actual discovery.
    value=CURRENT_BINDING if supplied is None else supplied
    need(type(value) is dict and set(value)=={"role_identity_sha256","intermediary_identity_sha256",
        "framework_epoch_sha256","child_table_sha256"} and
        set(value["role_identity_sha256"])==set(ROLES) and
        set(value["child_table_sha256"])=={"daemon","launcher","intermediary"} and
        all(valid_sha(x) for x in list(value["role_identity_sha256"].values())+
            list(value["child_table_sha256"].values())+
            [value["intermediary_identity_sha256"],value["framework_epoch_sha256"]]),
        "EXACT_DISCOVERY_AUTHORITY_SCHEMA")
    return value

def match_discovery_identities(rows,binding_authority=None):
    bound=authority(binding_authority)
    need(type(rows) is dict and set(rows)==set(ROLES),"EXACT_SEVEN_FIXED_ROLES_REQUIRED")
    need({k:identity_sha(v) for k,v in rows.items()}==bound["role_identity_sha256"],
         "CURRENT_FULL_IDENTITIES_DIFFER_FROM_ACTUAL_DISCOVERY")
    return True

def validate_child_table(table,parent,child):
    need(type(table) is dict and set(table)=={"thread_ids","per_thread","child_host_pids"},
         "COMPLETE_OWNER_CHILD_TABLE_SCHEMA")
    tids=table["thread_ids"];per=table["per_thread"];children=table["child_host_pids"]
    need(type(tids) is list and 0<len(tids)<=64 and
         all(type(x) is int and 0<x<=2147483647 for x in tids) and
         tids==sorted(set(tids)) and parent in tids and type(per) is dict and
         set(per)=={str(x) for x in tids},"COMPLETE_OWNER_THREAD_SET_REQUIRED")
    flat=[]
    for tid in tids:
        row=per[str(tid)]
        need(type(row) is list and len(row)<=32 and all(type(x) is int and 0<x<=2147483647 for x in row) and
             row==sorted(set(row)),"COMPLETE_OWNER_PER_THREAD_CHILDREN_REQUIRED")
        flat.extend(row)
    need(len(flat)<=32 and len(flat)==len(set(flat)) and
         type(children) is list and all(type(x) is int for x in children) and
         children==sorted(flat),"COMPLETE_OWNER_CHILD_UNION_REQUIRED")
    need(children==[child] and parent!=child,"OWNER_SINGLE_DIRECT_CHILD_REQUIRED")
    return True

def validate_cell_lineage(value,*,binding_authority=None):
    bound=authority(binding_authority)
    need(type(value) is dict and set(value)=={"schema","intermediary_process","child_tables",
         "host_user_namespace","role_user_namespaces","intermediary_user_namespace","intermediary_root",
         "intermediary_program_authority_assigned"} and
         value["schema"]=="pocket4-current-cell-owner-lineage-v1" and
         value["intermediary_program_authority_assigned"] is False,"CURRENT_OWNER_LINEAGE_SCHEMA")
    mid=value["intermediary_process"]
    validate_identity("owner_intermediary",mid,EXPECTED_INTERMEDIARY)
    need(identity_sha(mid)==bound["intermediary_identity_sha256"],"CURRENT_INTERMEDIARY_IDENTITY_DIFFERS")
    tables=value["child_tables"]
    need(type(tables) is dict and set(tables)=={"daemon","launcher","intermediary"},
         "THREE_COMPLETE_PARENT_TABLES_REQUIRED")
    for row in CHAIN_PARENTS:
        table=tables[row["role"]]
        validate_child_table(table,row["pid"],row["child"])
        need(identity_sha(table)==bound["child_table_sha256"][row["role"]],
             "OWNER_KERNEL_TABLE_DIFFERS_FROM_DISCOVERY")
    root=value["intermediary_root"]
    need(type(root) is dict and set(root)=={"device","inode"} and
         type(root["device"]) is int and root["device"]>=0 and
         type(root["inode"]) is int and root["inode"]>0,"CURRENT_INTERMEDIARY_ROOT_PROOF_REQUIRED")
    host=value["host_user_namespace"];roles=value["role_user_namespaces"]
    need(type(host) is str and re.fullmatch(r"user:\[[1-9][0-9]{0,19}\]",host) is not None and
         type(roles) is dict and set(roles)==set(ROLES) and
         all(type(v) is str and v==host for v in roles.values()) and
         value["intermediary_user_namespace"]==host,
         "FRESH_HOST_AND_ROLE_USER_NAMESPACES_REQUIRED")
    return True

def executable_content(artifacts):
    need(type(artifacts) is dict and set(artifacts)==set(ROLES),"ALL_SEVEN_CURRENT_EXECUTABLES_REQUIRED")
    out={}
    for role,row in artifacts.items():
        validate_artifact(row,PRESENTER_SHA if role=="presenter" else None)
        out[role]={"bytes":row["bytes"],"sha256":row["sha256"]}
    return out

def validate_executable_content(artifacts,previous):
    actual=executable_content(artifacts)
    need(type(previous) is dict and set(previous)==set(ROLES) and all(
        type(row) is dict and set(row)=={"bytes","sha256"} and type(row["bytes"]) is int and
        0<row["bytes"]<=268435456 and valid_sha(row["sha256"]) for row in previous.values()),
        "PREVIOUS_SEVEN_EXECUTABLE_CONTENT_PINS_REQUIRED")
    need(actual==previous,"CURRENT_EXECUTABLE_CONTENT_LINEAGE_CHANGED")
    return True

def validate_previous_baseline(value,activation):
    need(type(value) is dict and value.get("schema")=="pocket4-main-current-baseline-v1" and
         value.get("kind")=="current-framework-generation" and
         value.get("deployment_performed") is False and "main_deployed" not in value,
         "EXACT_PREVIOUS_BASELINE_DOCUMENT_REQUIRED")
    old=value["framework_epoch"]
    need(old.get("schema")=="pocket4-framework-epoch-v1" and
         old.get("sha256")==PREVIOUS_BASELINE["epoch_sha256"]==sha(canonical(old["binding"])) and
         old["binding"]["boot_id"]==BOOT_ID and
         old["sha256"] not in (OLD_EPOCH,CURRENT_BINDING["framework_epoch_sha256"]),
         "PREVIOUS_EPOCH_IS_HISTORICAL_ONLY")
    need(value.get("historical_deployment")=={"activation_path":ACTIVATION_PATH,
         "activation_bytes":ACTIVATION_BYTES,"activation_sha256":ACTIVATION_SHA,
         "verification_path":VERIFIED_PATH,"verification_sha256":VERIFIED_SHA} and
         value.get("old_epoch_sha256")==OLD_EPOCH and value.get("status")=={"host_pid":3588089} and
         value.get("packages")==TARGET_UIDS and value.get("limits")==LIMITS,
         "PREVIOUS_BASELINE_DEPLOYMENT_LINEAGE_DIFFERS")
    need(value.get("daemon_process")==activation["daemon_process"] and
         value.get("presenter_process")==activation["presenter_process"] and
         value.get("launcher_process")==activation["launcher_process"],
         "PREVIOUS_BASELINE_HOST_HISTORY_DIFFERS")
    validate_artifact_closure(value)
    need(value.get("whole_app_production_ready") is False and value.get("framework_exit_cause_resolved") is False,
         "PREVIOUS_PRODUCTION_BOUNDARY_CHANGED")
    return True

def validate_lineage_samples(values,*,binding_authority=None):
    need(type(values) is list and len(values)==3,"THREE_COMPLETE_OWNER_LINEAGE_SAMPLES_REQUIRED")
    for value in values:validate_cell_lineage(value,binding_authority=binding_authority)
    need(all(value==values[0] for value in values),"OWNER_LINEAGE_OR_USER_NAMESPACE_SAMPLES_CHANGED")
    return True

def protected_process_projection(snapshot,roots,lineage,*,binding_authority=None):
    # All text emitted here is constrained to the fixed role/cgroup/namespace
    # schema. Full executable strings and argv remain private.
    match_discovery_identities(snapshot["binding"]["processes"],binding_authority)
    validate_cell_lineage(lineage,binding_authority=binding_authority)
    need(type(roots) is dict and roots=={k:v["root_identity"] for k,v in EXPECTED.items()},
         "MEASURED_SEVEN_ROLE_ROOT_PROJECTION_REQUIRED")
    rows=snapshot["binding"]["processes"];out={}
    for role in ROLES+("owner_intermediary",):
        row=lineage["intermediary_process"] if role=="owner_intermediary" else rows[role]
        expected=EXPECTED_INTERMEDIARY if role=="owner_intermediary" else EXPECTED[role]
        validate_identity(role,row,expected)
        user=lineage["intermediary_user_namespace"] if role=="owner_intermediary" else lineage["role_user_namespaces"][role]
        root=lineage["intermediary_root"] if role=="owner_intermediary" else roots[role]
        out[role]={"host_pid":row["host_pid"],"parent_host_pid":row["parent_host_pid"],
            "start_ticks":row["start_ticks"],"uids":list(row["uids"]),"namespace_pids":list(row["namespace_pids"]),
            "cgroup":list(row["cgroup"]),"namespaces":{**row["namespaces"],"user":user},"root_identity":dict(root)}
    return out
