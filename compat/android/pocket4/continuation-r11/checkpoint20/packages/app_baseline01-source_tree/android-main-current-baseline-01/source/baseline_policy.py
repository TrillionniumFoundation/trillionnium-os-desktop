"""Fixed new framework identity policy. Pure data validation; no runtime authority."""
import hashlib,json,re,stat
SCHEMA="pocket4-main-current-baseline-v1"
QUAL_SCHEMA="pocket4-main-current-baseline-qualification-v1"
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
EXPECTED=json.loads("{\"android_init\":{\"pid\":3588093,\"start_ticks\":80797014,\"ppid\":3588092,\"uids\":[0,0,0,0],\"namespace_pids\":[3588093,1],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533284]\",\"pid\":\"pid:[4026533288]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"daemon\":{\"pid\":3588022,\"start_ticks\":80796995,\"ppid\":1,\"uids\":[0,0,0,0],\"namespace_pids\":[3588022],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026531832]\",\"pid\":\"pid:[4026531836]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"launcher\":{\"pid\":3588089,\"start_ticks\":80797013,\"ppid\":3588022,\"uids\":[0,0,0,0],\"namespace_pids\":[3588089],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533281]\",\"pid\":\"pid:[4026531836]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"presenter\":{\"pid\":3588024,\"start_ticks\":80796995,\"ppid\":2472,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[3588024],\"cgroup\":\"0::/user.slice/user-1000.slice/user@1000.service/app.slice/droidloom.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026531832]\",\"pid\":\"pid:[4026531836]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"surfaceflinger\":{\"pid\":3588912,\"start_ticks\":80797155,\"ppid\":3588093,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[3588912,672],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_1000/pid_672\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533284]\",\"pid\":\"pid:[4026533288]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"zygote64\":{\"pid\":90360,\"start_ticks\":96586437,\"ppid\":3588093,\"uids\":[0,0,0,0],\"namespace_pids\":[90360,1160345],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_0/pid_1160345\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533070]\",\"pid\":\"pid:[4026533288]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"system_server\":{\"pid\":90516,\"start_ticks\":96586493,\"ppid\":90360,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[90516,1160408],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_1000/pid_1160408\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533239]\",\"pid\":\"pid:[4026533288]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}}}")
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
         activation["status"]["host_pid"]==EXPECTED["launcher"]["pid"],"HISTORICAL_CELL_OWNER_DIFFERS")
    return True
def old_survivors(activation):
    p=activation["framework_epoch"]["binding"]["processes"]
    return {"android_init":p["init"],"surfaceflinger":p["surfaceflinger"],
            "daemon":activation["daemon_process"],"launcher":activation["launcher_process"],
            "presenter":activation["presenter_process"]}
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
def validate_snapshot(snapshot,activation,roots):
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
         rows["zygote64"]["parent_host_pid"]==rows["android_init"]["host_pid"],
         "NEW_FRAMEWORK_ANCESTRY_DIFFERS")
    return True
def android_epoch(snapshot):
    rows=snapshot["binding"]["processes"]
    selected={"init":rows["android_init"],**{k:rows[k] for k in ANDROID_ROLES if k!="init"}}
    body={"boot_id":BOOT_ID,"processes":selected}
    digest=sha(canonical(body))
    need(digest!=OLD_EPOCH,"OLD_EPOCH_MUST_NOT_BE_REAUTHORIZED")
    return {"schema":"pocket4-framework-epoch-v1","binding":body,"sha256":digest,
            "collected_monotonic_ns":snapshot["collected_monotonic_ns"]}
def validate_samples(samples,activation,roots):
    need(type(samples) is list and len(samples)==3,"EXACT_THREE_DOUBLE_SAMPLES_REQUIRED")
    for value in samples:validate_snapshot(value,activation,roots)
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
def validate_new_baseline(value):
    need(value.get("schema")==SCHEMA and value.get("kind")=="current-framework-generation" and
         "main_deployed" not in value and value.get("deployment_performed") is False,
         "CURRENT_BASELINE_MUST_NOT_IMPERSONATE_DEPLOYMENT")
    required={"schema","kind","deployment_performed","old_epoch_sha256","framework_epoch","historical_deployment",
        "daemon_process","launcher_process","presenter_process","status","all_seven_processes","process_roots",
        "sample_monotonic_ns","sample_span_ns","three_double_samples_equal","bounded_observation_is_not_future_stability_proof",
        "limits","cell_config","engine_sha256","presenter_sha256","engine_artifact","current_process_executables",
        "current_package_source","packages","app_directories","classpath","held_helper_static_qualification","current_service",
        "namespace_entry","Android_commands","UI_actions","App_launches","helper_installs","framework_exit_cause_resolved",
        "whole_app_production_ready","production_gate"}
    need(set(value)==required,"EXACT_CURRENT_BASELINE_FIELDS_REQUIRED")
    all7=value["all_seven_processes"]
    need(all7.get("schema")=="pocket4-framework-epoch-v1" and all7.get("sha256")==sha(canonical(all7["binding"])) and
         all7["binding"].get("boot_id")==BOOT_ID and set(all7["binding"]["processes"])==set(ROLES) and
         value["process_roots"]=={k:v["root_identity"] for k,v in EXPECTED.items()},"CURRENT_SEVEN_ROLE_DOCUMENT_REQUIRED")
    for role,row in all7["binding"]["processes"].items():validate_identity(role,row,EXPECTED[role])
    need(value["framework_epoch"]==android_epoch(all7),"ANDROID_SUBSET_MUST_BE_FROM_THE_SAME_SEVEN_ROLE_OBSERVATION")
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
    return True
