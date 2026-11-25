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
ANDROID_HANDOFF_SHA="d882e60b2c5db54960e812ce7a222f502e7a12432bf2281aa6486465d68a69c9"
ANDROID_SOURCE_COMMIT="2d5779f613ac2ef1e88c9272ed35fd884b12d54d"
ANDROID_SOURCE_TREE="d7cc7dd8a3d2d845d8210fb6b0e3a782d5068ca9"
QUERY_REQUIREMENTS_SHA="fac92bbf42f4145f61008e6c5eb9abfff29395919c9ed975a75a244b9e41b9d4"
COHORT="5cffd431a41a450440fe9bac7b5a5f93927471b331acde5662df4e8379b1fa87"
RUNTIME="c5e3167aa80f6a05f4deb5152ec19242b2263785416633494db57e47ab5c8f0b"
BOARD="028e2f9ed3b9fd1faf1bd4f5256e95226172187b7a5723840e4827059a16ffef"
BANK="b5b7ee1522f87c6fafb668d671ff028685db9e8e346564b1edda1f7ef867d5f7"
QUERY={
 "cmd-original":(52160,"237410b6f4bfb9586a9a1135feaa4e75c189288483575890447aa5d492c56984",0o555,"u:object_r:system_file:s0"),
 "toybox-original":(611248,"5c2b46686560564967fb5c1cb4ec633c42f658c347831c1d8c788ecf66e1774b",0o555,"u:object_r:toolbox_exec:s0"),
 "contacts-app-process64-original":(51616,"bcc150b9c7e2abcc9aef312ea04f5bbcba631dbb2e23cb1b240b7219df1229a2",0o555,"u:object_r:zygote_exec:s0"),
 "contacts-content-jar-original":(20158,"c0ee6290243eda4a6dd95292c28274dd199b82b57466e00a83e1bb1a50eae8b3",0o444,"u:object_r:system_file:s0"),
 "diagnostics-logcat-original":(186488,"73a4c21d53b9aac14fa07c7ea0bbf92dc56ac180b964d0d42179e0b093cd3203",0o555,"u:object_r:logcat_exec:s0"),
 "diagnostics-dumpsys-original":(68848,"f2848aeb2dda2bc4fd4fe3d7867d1cdd30b7f36efe8f718f47a48b06dc810a2d",0o555,"u:object_r:system_file:s0"),
}
QUERY_SOURCE={
 "cmd-original":"/system/bin/cmd","toybox-original":"/system/bin/toybox",
 "contacts-app-process64-original":"/system/bin/app_process64","contacts-content-jar-original":"/system/framework/content.jar",
 "diagnostics-logcat-original":"/system/bin/logcat","diagnostics-dumpsys-original":"/system/bin/dumpsys",
}
IMAGES={
 "system":(2294853632,SYSTEM),
 "vendor":(1073741824,"7a0559cfa3d0103e9256332bf0b1dcca009cf4399727685debfa11326767ce81"),
 "system_ext_lib64":(25165824,"5e5112d735d2fdab2fad50f309bc5cebb17a4d7bdc401cc4956a4afbc376be32"),
 "system_ext_readiness":(8388608,"5700f28e2af0c09023170096224281f45a71f17e30cc892c8441691ba479bde6"),
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

def android_inputs(original):
    need(original["bytes"]==19679 and original["sha256"]==ANDROID_HANDOFF_SHA,
         "exact completed normal query6 material handoff")
    h=json_bytes(read_pin(original,1024*1024))
    need(h["schema"]=="droidloom-fixed-query-six-normal-materials-v1" and
         h["source_commit"]==ANDROID_SOURCE_COMMIT and h["source_tree"]==ANDROID_SOURCE_TREE and
         h["query_input_count"]==6 and h["normal_publication_passed"] is True and
         h["independent_full_artifact_readback_passed"] is True and h["all_original_inputs_unchanged"] is True,
         "completed source-bound six-input normal publication")
    need(h["runtime_qualified"] is False and h["application_admission"] is False and
         h["production_ready"] is False and h["actual_installed_labels_observed"] is False,
         "normal public material is not runtime or label qualification")
    build=json_bytes(read_pin(project_pin(h["normal_build"]),1024*1024))
    result=json_bytes(read_pin(project_pin(h["normal_result"]),1024*1024))
    identity={"commit":ANDROID_SOURCE_COMMIT,"tree":ANDROID_SOURCE_TREE,"status":""}
    need(build["source_identity"]==identity and build["passed"] is True and build["runtime_qualified"] is False and
         len(build["commands"])==2 and all(type(x["exit_code"]) is int and x["exit_code"]==0 for x in build["commands"]),
         "normal producer actually built from the frozen source")
    producer=project_pin(h["normal_producer"])
    need(sum((x["bytes"],x["sha256"])==(producer["bytes"],producer["sha256"]) for x in build["artifacts"])==1,
         "normal producer bytes match its build")
    with held(producer["path"],maximum=32*1024*1024) as (fd,st):
        need(st.st_size==producer["bytes"] and hash_fd(fd)==producer["sha256"],"held normal producer unchanged")
    need(result["schema"]=="droidloom-normal-query6-producer-result-v1" and
         result["source_identity"]==identity and type(result["exit_code"]) is int and result["exit_code"]==0 and
         result["passed"] is True and result["inputs_unchanged"] is True and
         result["runtime_qualified"] is False and result["application_admission"] is False,
         "actual completed normal six-input producer")
    before=read_pin(project_pin(h["source_input_bookend_before"]),1024*1024)
    after=read_pin(project_pin(h["source_input_bookend_after"]),1024*1024)
    need(before==after,"normal four-image inputs remained unchanged")
    camera=json_bytes(read_pin(project_pin(h["source_four_image_materials"]),1024*1024))
    vendor_pin=project_pin(camera["normal_result"])
    vendor=json_bytes(read_pin(vendor_pin,2*1024*1024))
    need(camera["schema"]=="p4-normal-camera-android-materials-v1" and
         camera["base_cohort_sha256"]==COHORT and camera["runtime_qualified"] is False and
         camera["production_ready"] is False and
         vendor["schema"]=="droidloom-official-gsi-independent-vendor-normal-result-v1" and
         vendor["normal_user_commands_returned_success"] is True and vendor["source_projection_restored"] is True and
         vendor["official_system_bytes_preserved"] is True and vendor["runtime_qualified"] is False and
         vendor["production_ready"] is False,"same normal camera four-image source")
    publication=result["normal_publication"];package=publication["package"]
    need(publication["normal_vendor_receipt_sha256"]==vendor_pin["sha256"] and
         package["cohort_sha256"]==h["base_cohort_sha256"]==COHORT and
         package["kernel_first"]["runtime_manifest_sha256"]==h["runtime_manifest_sha256"]==RUNTIME,
         "normal publisher binds the final base and runtime")
    argv=result["argv"]
    need(isinstance(argv,list) and len(argv)==16 and argv[0]==producer["path"] and argv[1]=="package-official-base",
         "fixed normal package publisher command")
    flags=dict(zip(argv[2::2],argv[3::2]))
    exact(flags,("--system-image","--vendor-image","--normal-vendor-result","--normal-vendor-result-sha256",
                 "--system-ext-lib64","--system-ext-readiness","--output"),"normal publisher arguments")
    package_root=safe_absolute(flags["--output"])
    need(flags["--normal-vendor-result"]==vendor_pin["path"] and
         flags["--normal-vendor-result-sha256"]==vendor_pin["sha256"] and
         flags["--system-image"]==camera["images"]["system"]["path"] and
         flags["--system-ext-lib64"]==camera["images"]["system_ext_lib64"]["path"] and
         flags["--system-ext-readiness"]==camera["images"]["system_ext_readiness"]["path"],
         "original normal source arguments")
    basepin=project_pin(h["base_manifest"]);runtimepin=project_pin(h["runtime_manifest"]);boardpin=project_pin(h["board_device_manifest"])
    need(basepin["sha256"]==COHORT and runtimepin["sha256"]==RUNTIME and boardpin["sha256"]==BOARD,
         "normal final manifest byte identities")
    base=json_bytes(read_pin(basepin));runtime=json_bytes(read_pin(runtimepin));board=json_bytes(read_pin(boardpin))
    need(package["base"]==base and package["kernel_first"]["runtime"]==runtime and
         package["kernel_first"]["board_device_source"]["source"]==board,"original publisher manifest objects")
    need(base["schema"]==3 and base["scope"]=="android_base_images_v3" and base["layout"]=="gsi_system_as_root","normal v3 base")
    need(runtime["schema"]==2 and runtime["scope"]=="android_kernel_first_stage_v2" and
         runtime["base_cohort_sha256"]==COHORT and runtime["source_system_sha256"]==SYSTEM,"normal v2 runtime")
    need(runtime["argv"]==["/system/bin/init","second_stage"] and runtime["init_path"]=="/system/bin/init" and
         runtime["init_bytes"]==2934488 and runtime["init_sha256"]=="9f69cc83a88db5f8533014cfea5ad9ea8e0454120335329aec27f8d65b2a9537","stock init")
    need(board["schema"]==1 and board["scope"]=="android_private_device_source_v1" and
         board["base_cohort_sha256"]==COHORT and board["runtime_manifest_sha256"]==RUNTIME and
         board["source_system_sha256"]==SYSTEM and board["bytes"]==8388608 and
         board["sha256"]==BANK and board["file"]==BANK+".img","normal final device bank binding")
    need(base["system_ext_readiness"]["frontend"]["camera"]==h["camera_declaration"],"normal camera declaration preserved")
    need(set(h["images"])==set(IMAGES) and set(camera["images"])==set(IMAGES),"closed original image roles")
    for role,(size,sha) in IMAGES.items():
        need((h["images"][role]["bytes"],h["images"][role]["sha256"])==
             (camera["images"][role]["bytes"],camera["images"][role]["sha256"])==(size,sha),
             "all four normal images remain the same cohort")
    q=runtime["query_inputs"]
    exact(q,("scope","source_system_sha256","cmd","toybox","contacts","diagnostics"),"runtime six-input graph")
    exact(q["contacts"],("scope","app_process64","content_jar"),"fixed contacts graph")
    exact(q["diagnostics"],("scope","logcat","dumpsys"),"fixed diagnostics graph")
    need(q["scope"]=="fixed_application_query_v1" and q["source_system_sha256"]==SYSTEM and
         q["contacts"]["scope"]=="fixed_contacts_content_query_v1" and
         q["diagnostics"]["scope"]=="fixed_android_diagnostics_v1","fixed runtime query scopes")
    declarations={"cmd":q["cmd"],"toybox":q["toybox"],
        "contacts_app_process64":q["contacts"]["app_process64"],"contacts_content_jar":q["contacts"]["content_jar"],
        "diagnostics_logcat":q["diagnostics"]["logcat"],"diagnostics_dumpsys":q["diagnostics"]["dumpsys"]}
    need(set(h["query_inputs"])==set(declarations),"closed normal six-query roles")
    originals={}
    for role,declaration in declarations.items():
        row=h["query_inputs"][role]
        need(row["declaration"]==declaration,"original query runtime declaration")
        name=declaration["original"]["file"];need(name in QUERY and name not in originals,"unique fixed query original")
        size,sha,mode,label=QUERY[name]
        need(declaration["original"]=={"file":name,"bytes":size,"sha256":sha} and
             declaration["source_path"]==QUERY_SOURCE[name] and
             declaration["interpreter"]==(None if name=="contacts-content-jar-original" else "/system/bin/linker64"),
             "exact original query source and loader")
        originals[name]=project_pin(row["artifact"])
    need(set(originals)==set(QUERY),"all six originals supplied")
    requirements=project_pin(h["query_install_requirements"])
    need((requirements["bytes"],requirements["sha256"])==(4400,QUERY_REQUIREMENTS_SHA),
         "actual six-input label/lifecycle requirements")
    requirements_value=json_bytes(read_pin(requirements))
    need(requirements_value==h["query_install_requirements_value"] and
         package["kernel_first"]["query_inputs"]["installation_requirements_sha256"]==requirements["sha256"],
         "normal source requirements are unchanged")
    return h,package_root,basepin,runtimepin,boardpin,base,runtime,board,originals,requirements,requirements_value

def pack_android(plan_path,output):
    original,plan=read_plan(plan_path,"droidloom-normal-android-deb-plan-v1","handoff")
    h,package_root,basepin,runtimepin,boardpin,base,runtime,board,originals,requirements,q=android_inputs(original)
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
    need(q["schema"]=="droidloom-fixed-cp3a-query-inputs-v1" and q["input_count"]==6 and q["source_system_sha256"]==SYSTEM,"normal query install contract")
    requirements_by_name={row["file"]:row for row in q["sources"]}
    need(len(q["sources"])==6 and set(requirements_by_name)==set(QUERY),"closed query install labels")
    for name,(size,sha,mode,label) in QUERY.items():
        pin=originals[name];row=requirements_by_name[name]
        need((pin["bytes"],pin["sha256"])==(size,sha),"fixed original query bytes")
        need((row["bytes"],row["sha256"],row["required_installed_uid"],row["required_installed_gid"],row["required_installed_mode"],row["required_original_label"])==(size,sha,0,0,mode,label+"\0"),"fixed original query metadata")
        need(row["required_security_capability_absent"] is True,"original query has no capability")
        source("var/lib/droidloom/runtime-cohorts/"+RUNTIME+"/images/"+name,pin,mode)
    source("var/lib/droidloom/runtime-cohorts/"+RUNTIME+"/QUERY-INSTALL-REQUIREMENTS.json",requirements,0o444)
    result=build_deb(root,inventory,output,"droidloom-android-cohort","0.1+"+COHORT+"."+RUNTIME)
    receipt={"schema":"droidloom-normal-android-deb-result-v1","plan":plan,"handoff":original,
             "normal_source_commit":ANDROID_SOURCE_COMMIT,"normal_source_tree":ANDROID_SOURCE_TREE,
             "query_input_count":6,"normal_query_producer_result":project_pin(h["normal_result"]),
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
