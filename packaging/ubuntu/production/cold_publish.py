#!/usr/bin/python3
"""Normal public Debian components; never a fresh-root or runtime qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
from release import (
    Rejected, need, exact, integer, digest, canonical, f9, safe_relative, safe_absolute,
    held, hash_fd, pin_shape, read_pin, json_bytes, read_json_file, file_pin,
    new_file, copy_pin, mkdir_new, bounded_process, KERNEL, KERNEL_SHA, SYSTEM,
)

KERNEL_MODULES_SHA="5399a707d1aa2b8511a936dbc1b056891613f6043b8eafe0a1c0ad5c45eb7fa8"
KERNEL_CERT_SHA="c8085a1357354a180e49eae55a5f4a3d202b0f6aef1cd748cb31db5d8e5fefdf"
KERNEL_ARCHIVE_SHA="e5a305dfecff9dde1c7fc7a5980f606a67802963c31b363b412768c4e55949fc"
ANDROID_MATERIALS_SHA="84916101e6c7908114e4053bf6fbdfefc2480b902153923152cad64e62c54547"
ANDROID_HANDOFF_SHA="e476ae7039e9ee35aca15b49baa38930bdcdf28e2b393807d794a6fdb7664513"
ANDROID_NORMAL_SHA="ccd0bf1294652ad907a254250711250515244b963a72ceb8271a75014b1d9714"
ANDROID_TERMINAL_SHA="716b3b9a148f2cb304dcd02a39300163a2021702439b866e73c7ccc47ab1343a"
ANDROID_SOURCE="11bf0fa339d9c52fbf1093d95e1218f1ada40574"
ANDROID_TREE="266e49032d5a68e843dabb49db33595e652e5466"
COHORT="5cffd431a41a450440fe9bac7b5a5f93927471b331acde5662df4e8379b1fa87"
RUNTIME="ed9781109ae5bd0124b12badac21127636a742d0dbc406b3cee0f3900d257db8"
BOARD="0c839371072c7c8bc2513909c92b7623853e3c1a6538f92e1d60248cb0739520"
BANK="b5b7ee1522f87c6fafb668d671ff028685db9e8e346564b1edda1f7ef867d5f7"
QUERY={
 "cmd-original":(52160,"237410b6f4bfb9586a9a1135feaa4e75c189288483575890447aa5d492c56984",0o555,"u:object_r:system_file:s0"),
 "toybox-original":(611248,"5c2b46686560564967fb5c1cb4ec633c42f658c347831c1d8c788ecf66e1774b",0o555,"u:object_r:toolbox_exec:s0"),
 "contacts-app-process64-original":(51616,"bcc150b9c7e2abcc9aef312ea04f5bbcba631dbb2e23cb1b240b7219df1229a2",0o555,"u:object_r:zygote_exec:s0"),
 "contacts-content-jar-original":(20158,"c0ee6290243eda4a6dd95292c28274dd199b82b57466e00a83e1bb1a50eae8b3",0o444,"u:object_r:system_file:s0"),
 "toolbox-original":(169856,"a1d2b30312db7b099cfc4f25b712420b46574affa0d73709add5bc7630d55ae8",0o555,"u:object_r:toolbox_exec:s0"),
}
IMAGES={
 "system":(2294853632,SYSTEM),
 "vendor":(1073741824,"7a0559cfa3d0103e9256332bf0b1dcca009cf4399727685debfa11326767ce81"),
 "system_ext_lib64":(25165824,"5e5112d735d2fdab2fad50f309bc5cebb17a4d7bdc401cc4956a4afbc376be32"),
 "system_ext_readiness":(8388608,"5700f28e2af0c09023170096224281f45a71f17e30cc892c8441691ba479bde6"),
}
CAMERA={
 "jar":("/framework/droidloom-camera-producer.jar",17833,"708752a90d2993392a175c3ae0916e7f05f1097aad9030676a9746c1a04b9ef1",0o644,"u:object_r:droidloom_camera_producer_jar:s0"),
 "init_rc":("/etc/init/droidloom-camera-producer.rc",547,"7aa2fa285276242f72cd31683bf1c71854114280c2e8c78271d3843ff9e1fed0",0o644,"u:object_r:system_file:s0"),
 "provider":("/bin/droidloom-virtual-camera",495424,"7e8d7bf4eacaa1d2f6a1f14fb0991bb29249346a1b40b4018ba4768d8f2ea6d9",0o755,"u:object_r:virtual_camera_exec:s0"),
 "provider_init_rc":("/etc/init/droidloom-virtual-camera.rc",500,"f4624d70d2ce8214ce9a83a0ac80ea36f72426219b472907ff59b2b8f6e46886",0o644,"u:object_r:system_file:s0"),
}
def project_pin(value):
    need(isinstance(value,dict) and {"path","bytes","sha256"}<=set(value),"normal original file pin")
    return pin_shape({k:value[k] for k in ("path","bytes","sha256")})

def new_stage(output):
    need(os.geteuid()!=0,"normal component packaging must run as an ordinary build user")
    output=safe_absolute(str(output));mkdir_new(output)
    root=output/"root";root.mkdir(mode=0o700)
    return output,root

def put(root,inventory,relative,pin,mode,*,empty_index=False):
    safe_relative(relative)
    if empty_index:
        exact(pin,("path","bytes","sha256"),"normal empty module index")
        safe_absolute(pin["path"])
        need(pin["bytes"]==0 and pin["sha256"]==hashlib.sha256(b"").hexdigest(),"normal zero-length index")
    else:
        pin_shape(pin)
    need(relative not in inventory,"duplicate normal component payload")
    need(mode in (0o444,0o555,0o644,0o755),"normal immutable payload mode")
    path=root/relative;path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    if empty_index:
        with held(pin["path"]) as (fd,st):
            need(st.st_size==0 and hash_fd(fd)==pin["sha256"],"normal empty original index changed")
            new_file(path,b"",mode)
    else:
        copy_pin(pin,path,mode)
    inventory[relative]={"path":relative,"bytes":pin["bytes"],"sha256":pin["sha256"],"mode":mode}

def hash_md5(path):
    with held(path) as (fd,_):
        value=hashlib.md5(usedforsecurity=False)
        while True:
            b=os.read(fd,1024*1024)
            if not b:break
            value.update(b)
        return value.hexdigest()

def build_deb(root,inventory,output,name,version):
    need(name in ("droidloom-shared-kernel","droidloom-android-cohort"),"fixed normal component package")
    need(version and all(c in "abcdefghijklmnopqrstuvwxyz0123456789.+~-" for c in version),"fixed version characters")
    need(1<=len(inventory)<=7000,"normal component inventory count")
    need(sum(x["bytes"] for x in inventory.values())<=6*1024**3,"normal component byte budget")
    root.chmod(0o755)
    for p in root.rglob("*"):
        need(not p.is_symlink(),"normal component must not contain links")
        if p.is_dir():p.chmod(0o755)
    controls=root/"DEBIAN";controls.mkdir(mode=0o755);controls.chmod(0o755)
    control=(f"Package: {name}\nVersion: {version}\nArchitecture: amd64\n"
             "Maintainer: Droidloom maintainers\nSection: admin\nPriority: optional\n"
             "Description: Pinned public shared-kernel release component\n"
             " Normal source-bound bytes only; no activation or userdata.\n").encode()
    md5=("\n".join(hash_md5(root/x)+"  "+x for x in sorted(inventory))+"\n").encode()
    new_file(controls/"control",control,0o644);new_file(controls/"md5sums",md5,0o644)
    deb=output/(name+".deb")
    # The multi-GiB Android raw-image cohort uses normal Debian zstd so the
    # bounded one-CPU publisher does not spend its entire deadline in xz.
    # Module packages retain the already validated xz stream.
    compression = "zstd" if name == "droidloom-android-cohort" else "xz"
    result=bounded_process(["/usr/bin/dpkg-deb","--root-owner-group","--uniform-compression",
                            "--threads-max=1","-Z"+compression,"-z3","--build",str(root),str(deb)],
                           env={"PATH":"/usr/bin:/bin","LC_ALL":"C","SOURCE_DATE_EPOCH":"0","XZ_DEFAULTS":"-T1"},
                           seconds=300,maximum=1024*1024)
    new_file(output/"dpkg-deb.stdout",result["stdout"]);new_file(output/"dpkg-deb.stderr",result["stderr"])
    need(result["exit"]==0,"normal Debian component build failed")
    built=file_pin(deb)
    listing=bounded_process(["/usr/bin/dpkg-deb","--contents",str(deb)],seconds=300,maximum=4*1024*1024)
    need(listing["exit"]==0,"normal Debian metadata listing failed")
    lines=listing["stdout"].decode("utf-8","strict").splitlines()
    need(1<=len(lines)<=2*len(inventory)+64,"normal Debian metadata count")
    for line in lines:
        fields=line.split(None,5)
        need(len(fields)==6 and fields[1]=="root/root","normal Debian archive owner differs")
    new_file(output/"dpkg-deb.contents",listing["stdout"])
    readback=output/"readback";readback.mkdir(mode=0o700)
    result=bounded_process(["/usr/bin/dpkg-deb","--extract",str(deb),str(readback)],seconds=300,maximum=1024*1024)
    need(result["exit"]==0,"normal Debian component extraction failed")
    found=set()
    for p in readback.rglob("*"):
        need(not p.is_symlink(),"Debian component introduced a link")
        if p.is_dir():
            need(stat.S_IMODE(p.stat().st_mode)==0o755,"Debian component directory mode")
            continue
        rel=p.relative_to(readback).as_posix();need(rel in inventory,"unexpected Debian component leaf")
        row=inventory[rel];found.add(rel)
        with held(p,modes={row["mode"]}) as (fd,st):
            need(st.st_size==row["bytes"] and hash_fd(fd)==row["sha256"],"normal Debian payload changed")
    need(found==set(inventory),"normal Debian component inventory missing")
    controlback=output/"control-readback";controlback.mkdir(mode=0o700)
    result=bounded_process(["/usr/bin/dpkg-deb","--control",str(deb),str(controlback)],seconds=30,maximum=1024*1024)
    need(result["exit"]==0,"normal control extraction failed")
    need({x.name for x in controlback.iterdir()}=={"control","md5sums"},"unexpected package maintainer script")
    need((controlback/"control").read_bytes()==control and (controlback/"md5sums").read_bytes()==md5,"normal control bytes changed")
    need(file_pin(deb)==built,"normal Debian original package changed")
    new_file(output/"INVENTORY.json",canonical([inventory[k] for k in sorted(inventory)]))
    return built

def read_plan(path,schema,key):
    value,pin=read_json_file(path,1024*1024)
    exact(value,("schema",key),"normal component plan")
    need(value["schema"]==schema,"normal component plan schema")
    pin_shape(value[key])
    return value[key],pin

def pack_kernel(plan_path,output):
    publication,plan=read_plan(plan_path,"droidloom-normal-kernel-deb-plan-v1","publication")
    raw=read_pin(publication,1024*1024);p=json_bytes(raw)
    need(p["schema"]=="p4-readonly-peer-lsm-kernel-publication-v1" and p["release"]==KERNEL,"normal kernel publication")
    need(p["public_only"] is True and p["private_key_exported"] is False,"only public kernel inputs")
    need(p["physical_install"] is False and p["production_qualified"] is False,"normal kernel is not runtime qualification")
    need(p["module_count"]==p["signature_checks"]==6797 and p["index_count"]==15,"normal complete module cohort")
    image=project_pin(p["image"]);manifest=project_pin(p["modules"]);certificate=project_pin(p["signature_public_certificate"])
    need((image["bytes"],image["sha256"])==(16855552,KERNEL_SHA),"fixed current kernel bytes")
    need((manifest["bytes"],manifest["sha256"])==(2144597,KERNEL_MODULES_SHA),"fixed signed module manifest")
    need((certificate["bytes"],certificate["sha256"])==(1324,KERNEL_CERT_SHA),"normal module public certificate")
    need(p["archive"]["sha256"]==KERNEL_ARCHIVE_SHA,"normal kernel archive origin")
    m=json_bytes(read_pin(manifest,4*1024*1024))
    need(m["schema"]=="p4-normal-kernel-installed-module-manifest-v1" and m["release"]==KERNEL,"normal module manifest schema")
    need(m["count"]==6797 and len(m["rows"])==6797 and len(m["indexes"])==15,"complete module inventory")
    need(m["all_pkcs7_signatures_verified"] is True and m["all_vermagic_exact"] is True,"normal signature/vermagic proof")
    need(project_pin(m["module_signing_public_der"])["sha256"]==KERNEL_CERT_SHA,"manifest certificate binding")
    original=safe_absolute(image["path"])
    need(original.name=="vmlinuz-"+KERNEL and original.parent.name=="boot","normal kernel input layout")
    package_root=original.parent.parent
    module_root=package_root/"usr/lib/modules"/KERNEL
    output,root=new_stage(output);inventory={}
    put(root,inventory,"boot/droidloom/kernels/"+KERNEL_SHA+"/vmlinuz",image,0o444)
    put(root,inventory,"usr/lib/droidloom/kernels/"+KERNEL+"/module-signing-public.der",certificate,0o444)
    put(root,inventory,"usr/lib/droidloom/kernels/"+KERNEL+"/MODULES.json",manifest,0o444)
    config=project_pin(p["config"])
    need(config["path"]==str(module_root/("config-"+KERNEL)),"normal config source path")
    put(root,inventory,"usr/lib/modules/"+KERNEL+"/config-"+KERNEL,config,0o444)
    for row in m["rows"]:
        exact(row,("relative","sha256","bytes","vermagic","pkcs7_signature_verified"),"normal signed module")
        rel=safe_relative(row["relative"])
        need(rel.startswith("kernel/") and rel.endswith(".ko"),"only current kernel module leaves")
        need(row["vermagic"]==KERNEL+" SMP preempt mod_unload modversions" and row["pkcs7_signature_verified"] is True,
             "normal per-module signed vermagic")
        pin={"path":str(module_root/rel),"bytes":row["bytes"],"sha256":row["sha256"]}
        put(root,inventory,"usr/lib/modules/"+KERNEL+"/"+rel,pin,0o644)
    expected_indexes={"modules.alias","modules.alias.bin","modules.builtin","modules.builtin.alias.bin",
       "modules.builtin.bin","modules.builtin.modinfo","modules.builtin.ranges","modules.dep","modules.dep.bin",
       "modules.devname","modules.order","modules.softdep","modules.symbols","modules.symbols.bin","modules.weakdep"}
    need({r["relative"] for r in m["indexes"]}==expected_indexes,"normal module index set")
    for row in m["indexes"]:
        exact(row,("relative","sha256","bytes"),"normal module index")
        pin={"path":str(module_root/row["relative"]),"bytes":row["bytes"],"sha256":row["sha256"]}
        put(root,inventory,"usr/lib/modules/"+KERNEL+"/"+row["relative"],pin,0o644,empty_index=row["bytes"]==0)
    result=build_deb(root,inventory,output,"droidloom-shared-kernel","0.1+"+KERNEL)
    receipt={"schema":"droidloom-normal-kernel-deb-result-v1","plan":plan,"publication":publication,
             "kernel_release":KERNEL,"kernel_sha256":KERNEL_SHA,"modules_manifest":manifest,
             "module_count":6797,"index_count":15,"module_signatures_previously_verified_by_normal_publisher":6797,
             "all_module_original_bytes_verified":True,"package":result,"inventory":file_pin(output/"INVENTORY.json"),
             "normal_build_exit_code":0,"physical_install":False,"runtime_qualified":False}
    new_file(output/"RESULT.json",canonical(receipt));return receipt

def camera_readback(materials,handoff,normal):
    """Bind exact normal producer output to its independently extracted members.

    The fixed parent receipts are hashed by admit_camera_materials. These are
    image/packaging facts, not a claim that physical camera capture has passed.
    """
    rows=materials["camera"];other=handoff["camera"]
    need(isinstance(rows,list) and len(rows)==4 and {r["role"] for r in rows}==set(CAMERA),
         "complete fixed camera source roles")
    need(isinstance(other,list) and len(other)==4 and {r["role"] for r in other}==set(CAMERA),
         "complete independently extracted camera roles")
    actual={r["role"]:r for r in other}
    built=normal["early_boot_readiness"]["installed_frontend"]["camera"]
    members=normal["early_boot_readiness"]["readback"]["members"]
    need(set(built)==set(CAMERA),"normal camera build closure")
    for row in rows:
        role=row["role"];path,size,sha,mode,label=CAMERA[role];observed=actual[role]
        need((row["image_path"],row["bytes"],row["sha256"],row["mode"],row["uid"],row["gid"],row["selinux"])==
             (path,size,sha,mode,0,0,label),"exact normal camera source and label")
        need(project_pin(observed)==project_pin(row) and
             all(observed[k]==row[k] for k in ("image_path","mode","uid","gid","selinux")),
             "independent camera extraction differs")
        need((built[role]["bytes"],built[role]["sha256"])==(size,sha),"camera differs from normal build")
        member=members[path[1:]]
        need((member["sha256"],member["uid"],member["gid"],member["mode"])==
             (sha,0,0,oct(stat.S_IFREG|mode)) and
             member["xattrs_hex"]=={"security.selinux":(label+"\0").encode().hex()},
             "camera image bytes/metadata/label readback differs")

def admit_camera_materials(original):
    need((original["bytes"],original["sha256"])==(12961,ANDROID_MATERIALS_SHA),
         "exact completed camera material source")
    m=json_bytes(read_pin(original,1024*1024))
    need(m["schema"]=="p4-normal-camera-android-materials-v1" and
         (m["source_head"],m["source_tree"])==(ANDROID_SOURCE,ANDROID_TREE),"normal camera source objects")
    hp=project_pin(m["full_readback"]);np=project_pin(m["normal_result"])
    need((hp["bytes"],hp["sha256"])==(135437,ANDROID_HANDOFF_SHA) and
         (np["bytes"],np["sha256"])==(120640,ANDROID_NORMAL_SHA),"normal camera original receipts")
    h=json_bytes(read_pin(hp,1024*1024));n=json_bytes(read_pin(np,1024*1024))
    need(h["schema"]=="p4-camera-normal-four-image-public-handoff-v1" and
         (h["source_head"],h["source_tree"])==(ANDROID_SOURCE,ANDROID_TREE),"independent normal camera source")
    need(project_pin(h["normal_result"])==np and h["base_cohort_sha256"]==m["base_cohort_sha256"]==COHORT,
         "camera producer/readback cohort binding")
    tp=project_pin(h["normal_terminal"])
    need((tp["bytes"],tp["sha256"])==(782,ANDROID_TERMINAL_SHA),"actual normal producer terminal")
    t=json_bytes(read_pin(tp,1024*1024))
    need(t["schema"]=="p4-camera-normal-vendor-terminal-v1" and t["exit_code"]==0 and
         (t["source_head"],t["source_tree"])==(ANDROID_SOURCE,ANDROID_TREE) and t["source_unchanged"] is True,
         "completed normal producer and unchanged source")
    for key in ("stdout","stderr"):read_pin(project_pin(t[key]),8*1024*1024)
    need(n["schema"]=="droidloom-official-gsi-independent-vendor-normal-result-v1" and
         n["normal_user_commands_returned_success"] is True and n["source_projection_restored"] is True,
         "normal vendor build completion")
    need(m["runtime_qualified"] is m["production_ready"] is False and
         h["runtime_qualified"] is h["production_ready"] is h["original_userdata_accessed"] is False and
         n["runtime_qualified"] is n["production_ready"] is False and
         t["runtime_qualified"] is t["production_selection_changed"] is False,
         "normal public source cannot claim runtime or activation")
    need(h["camera_physical_capture_verified"] is False and h["android_tests_executed"] is False,
         "packaging cannot manufacture application or physical camera acceptance")
    for key in ("base_manifest","runtime_manifest","board_device_manifest"):
        need(project_pin(m[key])==project_pin(h[key]),"camera manifest source/readback differs")
    need(set(m["images"])==set(h["images"])==set(IMAGES),"complete four-image camera cohort")
    for role in IMAGES:
        need(project_pin(m["images"][role])==project_pin(h["images"][role]),"camera whole-image readback binding")
    camera_readback(m,h,n)
    for row in m["camera"]:read_pin(project_pin(row),1024*1024)
    policies=m["android_policy_inputs"]
    other={r["partition_path"]:r for r in h["android_policy_inputs"]}
    need(len(policies)==len(other)==len(h["android_policy_inputs"])==9 and
         {r["partition_path"] for r in policies}==set(other),"nine actual Android policy inputs")
    for row in policies:
        observed=other[row["partition_path"]]
        need(project_pin(row)==project_pin(observed) and
             all(row[k]==observed[k] for k in ("image_role","image_path","image_sha256")) and
             row["image_sha256"]==IMAGES[row["image_role"]][1],"policy source/actual image binding")
        read_pin(project_pin(row),4*1024*1024)
    need(len(h["commands"])==70 and all(r["exit_code"]==0 for r in h["commands"]),
         "completed independent normal image extraction")
    # Freeze the actual original records too; a transport summary alone cannot
    # replace either the normal build or its complete independent readback.
    return m,h,n,{"materials":original,"handoff":hp,"normal_result":np,"normal_terminal":tp}

def pack_android(plan_path,output):
    original,plan=read_plan(plan_path,"droidloom-normal-android-deb-plan-v2","materials")
    h,readback,normal,evidence=admit_camera_materials(original)
    package_root=safe_absolute(readback["package_root"])
    basepin=project_pin(h["base_manifest"]);runtimepin=project_pin(h["runtime_manifest"]);boardpin=project_pin(h["board_device_manifest"])
    need(basepin["sha256"]==COHORT and runtimepin["sha256"]==RUNTIME and boardpin["sha256"]==BOARD,"normal manifest byte identities")
    base=json_bytes(read_pin(basepin));runtime=json_bytes(read_pin(runtimepin));board=json_bytes(read_pin(boardpin))
    need(base["schema"]==3 and base["scope"]=="android_base_images_v3" and base["layout"]=="gsi_system_as_root","normal v3 base")
    need(runtime["schema"]==2 and runtime["scope"]=="android_kernel_first_stage_v2" and runtime["base_cohort_sha256"]==COHORT and runtime["source_system_sha256"]==SYSTEM,"normal v2 runtime")
    need(runtime["argv"]==["/system/bin/init","second_stage"] and runtime["init_path"]=="/system/bin/init" and runtime["init_bytes"]==2934488 and runtime["init_sha256"]=="9f69cc83a88db5f8533014cfea5ad9ea8e0454120335329aec27f8d65b2a9537","stock init")
    need(board["schema"]==1 and board["scope"]=="android_private_device_source_v1" and board["base_cohort_sha256"]==COHORT and board["runtime_manifest_sha256"]==RUNTIME and board["source_system_sha256"]==SYSTEM,"normal board device binding")
    need(board["bytes"]==8388608 and board["sha256"]==BANK and board["file"]==BANK+".img","normal device bank")
    query=h["query_inputs"]
    need(h["query_input_count"]==readback["query_input_count"]==len(query)==len(QUERY),
         "five actual original query inputs")
    query={Path(r["path"]).name:project_pin(r) for r in query}
    need(set(h["images"])==set(IMAGES) and set(query)==set(QUERY),"closed normal image/query roles")
    need(runtime==readback["runtime"] and board==readback["board_device_source"],
         "normal runtime and device bank independent readback")
    output,root=new_stage(output);inventory={}
    def source(relative,pin,mode):
        need(pin["path"]==str(package_root/relative),"normal publisher relative input changed")
        put(root,inventory,relative,pin,mode)
    source("etc/droidloom/cohorts/"+COHORT+".json",basepin,0o444)
    source("etc/droidloom/runtime-cohorts/"+RUNTIME+".json",runtimepin,0o444)
    source("etc/droidloom/board-devices/"+BOARD+".json",boardpin,0o444)
    for role,(size,sha) in IMAGES.items():
        pin=project_pin(h["images"][role]);entry=base[role]
        need((pin["bytes"],pin["sha256"])==(size,sha) and (entry["bytes"],entry["sha256"],entry["file"])==(size,sha,role+".img"),"normal four-image pin")
        source("var/lib/droidloom/cohorts/"+COHORT+"/images/"+role+".img",pin,0o444)
    bank=project_pin(h["device_bank"]);need((bank["bytes"],bank["sha256"])==(8388608,BANK),"normal device bank bytes")
    source("var/lib/droidloom/cohorts/"+COHORT+"/board/"+BANK+".img",bank,0o444)
    requirements=project_pin(h["query_install_requirements"]);q=json_bytes(read_pin(requirements))
    need(q["schema"]=="droidloom-fixed-cp3a-query-inputs-v2" and q["input_count"]==len(QUERY) and q["source_system_sha256"]==SYSTEM,"normal query install contract")
    requirements_by_name={row["file"]:row for row in q["sources"]}
    need(len(q["sources"])==len(QUERY) and set(requirements_by_name)==set(QUERY),"closed query install labels")
    for name,(size,sha,mode,label) in QUERY.items():
        pin=query[name];row=requirements_by_name[name]
        need((pin["bytes"],pin["sha256"])==(size,sha),"fixed original query bytes")
        need((row["bytes"],row["sha256"],row["required_installed_uid"],row["required_installed_gid"],row["required_installed_mode"],row["required_original_label"])==(size,sha,0,0,mode,label+"\0"),"fixed original query metadata")
        need(row["required_security_capability_absent"] is True,"original query has no capability")
        source("var/lib/droidloom/runtime-cohorts/"+RUNTIME+"/images/"+name,pin,mode)
    source("var/lib/droidloom/runtime-cohorts/"+RUNTIME+"/QUERY-INSTALL-REQUIREMENTS.json",requirements,0o444)
    result=build_deb(root,inventory,output,"droidloom-android-cohort","0.1+"+COHORT)
    for role,pin in evidence.items():copy_pin(pin,output/("source-"+role+".json"),0o444)
    evidence={role:file_pin(output/("source-"+role+".json")) for role in evidence}
    receipt={"schema":"droidloom-normal-android-deb-result-v1","plan":plan,**evidence,
             "android_source_commit":ANDROID_SOURCE,"android_source_tree":ANDROID_TREE,
             "cohort_sha256":COHORT,"runtime_sha256":RUNTIME,"board_device_manifest_sha256":BOARD,
             "package":result,"inventory":file_pin(output/"INVENTORY.json"),"normal_build_exit_code":0,
             "original_userdata_accessed":False,"query_original_labels_required_at_cold_install":True,
             "query_installed_labels_observed":False,"physical_install":False,"runtime_qualified":False}
    new_file(output/"RESULT.json",canonical(receipt));return receipt

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("pack-kernel","pack-android"):
        p=sub.add_parser(name);p.add_argument("--plan",required=True,type=Path);p.add_argument("--output",required=True,type=Path)
    a=parser.parse_args()
    result={"pack-kernel":pack_kernel,"pack-android":pack_android}[a.command](a.plan,a.output)
    sys.stdout.buffer.write(canonical(result));sys.stdout.buffer.flush()
if __name__=="__main__":
    try:main()
    except (Rejected,OSError,ValueError,KeyError,tarfile.TarError) as error:
        print("droidloom-cold-publish: "+str(error),file=sys.stderr);sys.exit(1)
