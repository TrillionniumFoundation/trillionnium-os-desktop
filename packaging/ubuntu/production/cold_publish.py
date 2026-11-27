#!/usr/bin/python3
"""Normal public Debian components; never a fresh-root or runtime qualification."""
import argparse
import base64
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
RUNTIME="ca2ebe17cd18df298b57f621892b186f183d915790d3ad44d8f9b6d78d965556"
BOARD="cd0ca973b22ce2a05a55dd43ac9c42ecbe86eb2fadb1e855bc89b912dcd478c1"
BANK="b5b7ee1522f87c6fafb668d671ff028685db9e8e346564b1edda1f7ef867d5f7"
# Actual new normal publication; historical camera source records above remain unchanged.
QUERY_SOURCE="21ff8712523b944a360f814eb5f86bd1aadc70cc"
QUERY_TREE="bed5b422add907aba7e0f518b8fecb1fe18efcd2"
QUERY_MATERIALS_BYTES=14840
QUERY_MATERIALS_SHA="a40ba48c6479c51870e5cf002433821ed71b738ad3ddb70f798bcc7be8e412b9"
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

def query_evidence_member(name):
    """A portable byte copy never replaces the original producer's source facts."""
    suffix={"normal_producer":".elf","normal_producer_depfile":".d",
            "device_bank":".img"}.get(name,".bin" if name in QUERY else ".json")
    need(name in set(QUERY)|{"materials","normal_producer","normal_producer_record",
         "normal_producer_depfile","normal_build","independent_image_copy","execution",
         "publication","stderr","base_manifest","runtime_manifest","board_device_manifest",
         "device_bank","query_install_requirements","archive_readback","retained_normal_result",
         "retained_inventory","archive_execution","archive_stdout","archive_stderr"},
         "closed portable five-query evidence role")
    return "android-query-"+name+suffix

def admit_query_materials(original,portable=None,*,whole_images=False):
    """Verify new normal publication separately from the historical image build.

    Original JSON is retained verbatim. A portable map only moves byte-identical
    evidence; it cannot change the original source, command, image or query facts.
    Full images are re-opened by the normal Debian builder. Public preparation
    verifies the resulting complete archive and these original producer records;
    the physical importer separately hashes every actual Debian payload member.
    """
    original=project_pin(original)
    need((original["bytes"],original["sha256"])==(QUERY_MATERIALS_BYTES,QUERY_MATERIALS_SHA),
         "exact actual five-query material publication")
    evidence={}
    def selected(name,reference):
        reference=project_pin(reference)
        local=reference if portable is None else project_pin(portable[name])
        need((local["bytes"],local["sha256"])==(reference["bytes"],reference["sha256"]),
             "portable query evidence changed original bytes")
        need(name not in evidence or evidence[name]==local,"duplicate query evidence binding")
        evidence[name]=local
        return local
    def body(name,reference,maximum=2*1024*1024):
        return read_pin(selected(name,reference),maximum)
    def value(name,reference,maximum=2*1024*1024):
        return json_bytes(body(name,reference,maximum))
    def log(name,reference):
        # Existing payload FilePin deliberately excludes empty files. Preserve
        # actual command logs, including zero bytes, in a positive-size envelope
        # without changing that global contract or replacing the original log.
        need(name in {"stderr","archive_stdout","archive_stderr"},"fixed command log role")
        reference={k:reference[k] for k in ("path","bytes","sha256")}
        safe_absolute(reference["path"]);integer(reference["bytes"],0,8*1024*1024,"actual command log bytes")
        digest(reference["sha256"])
        if portable is None:
            with held(reference["path"],maximum=8*1024*1024) as (fd,st):
                need(st.st_size==reference["bytes"] and hash_fd(fd)==reference["sha256"],"actual original command log differs")
                data=os.read(fd,8*1024*1024+1)
                need(len(data)==st.st_size,"short original command log")
            envelope={"schema":"droidloom-original-query-command-log-v1","original":reference,
                      "body_base64":base64.b64encode(data).decode("ascii")}
            evidence[name]={"log_envelope":canonical(envelope)}
        else:
            local=project_pin(portable[name]);envelope=json_bytes(read_pin(local,12*1024*1024))
            exact(envelope,("schema","original","body_base64"),"original query command log envelope")
            need(envelope["schema"]=="droidloom-original-query-command-log-v1" and
                 envelope["original"]==reference,"original command log provenance changed")
            data=base64.b64decode(envelope["body_base64"],validate=True)
            need(len(data)==reference["bytes"] and hashlib.sha256(data).hexdigest()==reference["sha256"],
                 "portable command log did not preserve every original byte")
            evidence[name]=local
    q=value("materials",original)
    need(q["schema"]=="p4-normal-five-query-materials-v1" and
         (q["source_commit"],q["source_tree"])==(QUERY_SOURCE,QUERY_TREE) and
         q["base_cohort_sha256"]==COHORT and q["query_input_count"]==len(QUERY),
         "normal five-query producer source and selected base")
    need(q["historical_images_preserved"] is True and q["original_inputs_modified"] is False and
         q["runtime_qualified"] is q["production_ready"] is False,
         "input publication cannot assert execution, activation or altered images")
    need((q["historical_camera_materials"]["bytes"],q["historical_camera_materials"]["sha256"])==
         (12961,ANDROID_MATERIALS_SHA),"new query publication must retain actual camera history")
    package_root=safe_absolute(q["package_root"])
    producer=body("normal_producer",q["normal_producer"],32*1024*1024)
    need(len(producer)==18264184 and hashlib.sha256(producer).hexdigest()==
         "03d273cd8484023a1b46ebdd5073ff822137c2066035f1b4106b137e3e3c2818" and
         producer[:7]==b"\x7fELF\x02\x01\x01" and producer[18:20]==b"\x3e\0",
         "actual normally built x86_64 kernel-first publisher")
    built=value("normal_producer_record",q["normal_producer_record"])
    need(built["source_commit"]==QUERY_SOURCE and
         project_pin(built["producer"])==project_pin(q["normal_producer"]),
         "normal producer ELF/source record binding")
    dependency=body("normal_producer_depfile",q["normal_producer_depfile"])
    need(project_pin(built["producer"]["dependency_file"])==project_pin(q["normal_producer_depfile"]),
         "actual normal producer dependency file")
    required={"tools/droidloom-update/src/coherent_kernel_first.rs",
              "tools/droidloom-update/src/coherent_kernel_query.rs",
              "tools/droidloom-update/src/query_input_metadata.rs",
              "runtime/droidloom-supervisor/src/production_query_input_profile.rs"}
    dependencies=built["producer"]["project_dependencies"]
    need(len({r["path"] for r in dependencies})==len(dependencies) and
         required<={r["path"] for r in dependencies} and
         all(path.encode() in dependency for path in required),"complete actual kernel-first implementation")
    normal=value("normal_build",q["normal_build"])
    need((q["normal_build"]["bytes"],q["normal_build"]["sha256"])==
         (4603,"a2e82620526195a4980a0e2856ca17ced905b3f599e16f6454dc56da2e46b956") and
         normal["exit_code"]==0 and normal["error"] is None and normal["retirement"]["verified"] is True and
         normal["retirement"]["actual"]["ActiveState"]=="inactive" and
         normal["retirement"]["actual"]["MainPID"]=="0","actual R6 normal build terminal")
    execution=value("execution",q["execution"])
    need(execution["schema"]=="p4.normal-five-query-actual-command.v1" and
         execution["exit_code"]==0 and execution["error"] is None and
         (execution["source_commit"],execution["source_tree"])==(QUERY_SOURCE,QUERY_TREE) and
         project_pin(execution["normal_producer"])==project_pin(q["normal_producer"]) and
         project_pin(execution["normal_build"])==project_pin(q["normal_build"]),
         "actual normal five-query command must have succeeded")
    argv=execution["argv"]
    need(len(argv)==10 and argv[0]==q["normal_producer"]["path"] and
         argv[1:2]==["--source"] and argv[3:6]==["--jobs","2","bind-kernel-first-runtime"] and
         argv[6:]==["--package",str(package_root),"--base-sha256",COHORT],
         "exact ordinary kernel-first publication command")
    safe_absolute(argv[2])
    need(project_pin(execution["stdout"])==project_pin(q["publication"]),"actual publication stdout binding")
    publication=value("publication",q["publication"])
    log("stderr",execution["stderr"])
    recovered=value("archive_readback",q["retained_normal_archive_readback"])
    need(recovered["schema"]=="p4-retained-normal-android-archive-readback-v1" and
         recovered["all_member_bytes_verified"] is True and
         recovered["historical_inputs_modified"] is recovered["historical_normal_build_repeated"] is
         recovered["runtime_qualified"] is recovered["production_ready"] is False,
         "actual retained archive readback must preserve all historical facts")
    need(project_pin(recovered["historical_camera_materials"])==project_pin(q["historical_camera_materials"]) and
         (recovered["archive"]["bytes"],recovered["archive"]["sha256"])==
             (1252956170,"7b785edba710a74272605c68340bfbcd463e2f3e2f9a3d85032825a149d62baa"),
         "exact retained original normal Android archive")
    previous=value("retained_normal_result",recovered["historical_normal_result"])
    need((recovered["historical_normal_result"]["bytes"],recovered["historical_normal_result"]["sha256"])
         ==(1973,"19d9111e5837aa852a7e569474acf6b13046cfe9a03bb231e8b11043e8c64847") and
         previous["schema"]=="droidloom-normal-android-deb-result-v1" and previous["normal_build_exit_code"]==0 and
         (previous["android_source_commit"],previous["android_source_tree"])==(ANDROID_SOURCE,ANDROID_TREE),
         "retained original camera package normal producer")
    inventory=value("retained_inventory",recovered["inventory"])
    need((recovered["inventory"]["bytes"],recovered["inventory"]["sha256"])
         ==(3034,"fca630cea75316667b77a1f80bf23031735e8c423e0f72ef9c361f93f7359fbd") and
         project_pin(previous["package"])==project_pin(recovered["archive"]) and
         project_pin(previous["inventory"])==project_pin(recovered["inventory"]),"complete retained archive inventory")
    need(len(inventory)==13 and len(recovered["verified_members"])==13 and
         {r["path"] for r in inventory}==set(recovered["verified_members"]),"complete actual retained payload set")
    for row in inventory:
        restored=recovered["verified_members"][row["path"]]
        need((row["bytes"],row["sha256"],row["mode"])==
             (restored["bytes"],restored["sha256"],stat.S_IMODE(restored["f9"][2])),
             "all actual restored archive bytes and modes")
    extraction=value("archive_execution",recovered["execution"])
    need(extraction["schema"]=="p4.retained-android-archive-extract-execution.v1" and
         extraction["exit_code"]==0 and extraction["error"] is None and
         extraction["argv"]==["/usr/bin/dpkg-deb","--extract",recovered["archive"]["path"],recovered["destination"]],
         "actual normal archive extraction terminal")
    log("archive_stdout",extraction["stdout"]);log("archive_stderr",extraction["stderr"])
    copied=value("independent_image_copy",q["independent_image_copy"])
    need(project_pin(copied["base_manifest"])==project_pin(q["base_manifest"]) and
         set(copied["images"])==set(q["images"])==set(IMAGES),"independent whole-image publication inputs")
    basepin=project_pin(q["base_manifest"])
    base=value("base_manifest",basepin)
    need(basepin["path"]==str(package_root/"etc/droidloom/cohorts"/(COHORT+".json")) and
         basepin["sha256"]==COHORT and base["schema"]==3 and
         base["scope"]=="android_base_images_v3" and base["layout"]=="gsi_system_as_root",
         "actual selected four-image base")
    for role,(size,sha) in IMAGES.items():
        pin=project_pin(q["images"][role]);entry=base[role]
        need(project_pin(copied["images"][role])==pin and
             (recovered["images"][role]["bytes"],recovered["images"][role]["sha256"])==(size,sha) and
             (pin["bytes"],pin["sha256"])==(size,sha) and
             (entry["bytes"],entry["sha256"],entry["file"])==(size,sha,role+".img") and
             pin["path"]==str(package_root/"var/lib/droidloom/cohorts"/COHORT/"images"/(role+".img")),
             "byte-identical normal image restoration and source namespace")
        if whole_images:
            with held(pin["path"]) as (fd,st):
                need(st.st_size==size and hash_fd(fd)==sha,"complete actual source image differs")
    runtimepin=project_pin(q["runtime_manifest"]);runtime=value("runtime_manifest",runtimepin)
    need(runtimepin["sha256"]==RUNTIME and
         runtimepin["path"]==str(package_root/"etc/droidloom/runtime-cohorts"/(RUNTIME+".json")) and
         publication["runtime_manifest_sha256"]==RUNTIME and publication["runtime"]==runtime and
         publication["manifest"]=="etc/droidloom/runtime-cohorts/"+RUNTIME+".json",
         "actual kernel-first runtime bytes and original stdout")
    exact(runtime,("schema","scope","base_cohort_sha256","source_system_sha256","init_path",
          "init_bytes","init_sha256","argv","query_inputs"),"five-query runtime")
    need(runtime["schema"]==2 and runtime["scope"]=="android_kernel_first_stage_v2" and
         runtime["base_cohort_sha256"]==COHORT and runtime["source_system_sha256"]==SYSTEM and
         runtime["init_path"]=="/system/bin/init" and runtime["init_bytes"]==2934488 and
         runtime["init_sha256"]=="9f69cc83a88db5f8533014cfea5ad9ea8e0454120335329aec27f8d65b2a9537" and
         runtime["argv"]==["/system/bin/init","second_stage"],"unchanged complete original init declaration")
    declaration=runtime["query_inputs"]
    exact(declaration,("scope","source_system_sha256","cmd","toybox","toolbox","contacts"),"five-query declaration")
    exact(declaration["contacts"],("scope","app_process64","content_jar"),"original contacts query declaration")
    need(declaration["scope"]=="fixed_application_query_v2" and declaration["source_system_sha256"]==SYSTEM and
         declaration["contacts"]["scope"]=="fixed_contacts_content_query_v1","actual fixed query scope")
    selected_roles={"cmd-original":(declaration["cmd"],"/system/bin/cmd"),
       "toybox-original":(declaration["toybox"],"/system/bin/toybox"),
       "contacts-app-process64-original":(declaration["contacts"]["app_process64"],"/system/bin/app_process64"),
       "contacts-content-jar-original":(declaration["contacts"]["content_jar"],"/system/framework/content.jar"),
       "toolbox-original":(declaration["toolbox"],"/system/bin/toolbox")}
    requirementspin=project_pin(q["query_install_requirements"])
    requirements=value("query_install_requirements",requirementspin)
    relative="var/lib/droidloom/runtime-cohorts/"+RUNTIME
    need(requirementspin["path"]==str(package_root/relative/"QUERY-INSTALL-REQUIREMENTS.json") and
         requirements["schema"]=="droidloom-fixed-cp3a-query-inputs-v2" and
         requirements["input_scope"]=="cp3a_fixed_application_query_inputs_v2" and
         requirements["source_system_sha256"]==SYSTEM and requirements["source_system_bytes"]==IMAGES["system"][0] and
         requirements["input_count"]==len(QUERY),"complete original query installation contract")
    query_publication=publication["query_inputs"]
    need(query_publication=={"images_directory":relative,
         "installation_requirements":relative+"/QUERY-INSTALL-REQUIREMENTS.json",
         "installation_requirements_sha256":requirementspin["sha256"],"input_count":len(QUERY),
         "installed_original_labels_observed":False,"application_admission":False},
         "actual five-query publication cannot assert installed-label or application acceptance")
    need(requirements["private_query_projection_observed"] is requirements["application_admission"] is
         requirements["runtime_qualified"] is False and requirements["original_query_executions"]==0,
         "source extraction is not query execution")
    originals={r["file"]:r for r in requirements["sources"]}
    query={r["name"]:r for r in q["query_inputs"]}
    need(len(originals)==len(requirements["sources"])==len(query)==len(q["query_inputs"])==len(QUERY) and
         set(originals)==set(query)==set(QUERY),"exact five actual original query roles")
    for name,(size,sha,mode,label) in QUERY.items():
        source,path=selected_roles[name];observed=originals[name];pin=project_pin(query[name])
        interpreter=None if name=="contacts-content-jar-original" else "/system/bin/linker64"
        exact(source,("original","source_path","interpreter"),"original query member declaration")
        need(source=={"original":{"file":name,"bytes":size,"sha256":sha},"source_path":path,
              "interpreter":interpreter},"exact original query path, interpreter and whole body")
        need((pin["bytes"],pin["sha256"])==(size,sha) and
             pin["path"]==str(package_root/relative/"images"/name) and
             query[name]["original_observation"]==observed,"new publication source/observed role binding")
        need((observed["source_path"],observed["source_mode"],observed["source_uid"],observed["source_gid"])
             ==(path,0o100644 if interpreter is None else 0o100755,0,0 if interpreter is None else 2000) and
             type(observed["source_inode"]) is int and observed["source_inode"]>0,
             "original image inode, full mode and root:shell identity")
        need((observed["bytes"],observed["sha256"],observed["required_installed_mode"],
              observed["required_installed_uid"],observed["required_installed_gid"],observed["required_original_label"])
             ==(size,sha,mode,0,0,label+"\0") and
             observed["required_original_label_preserved"] is observed["required_security_capability_absent"] is True and
             observed["installed_label_observed"] is False,"exact original label and privilege-free sealed role")
        data=body(name,pin)
        need((data[:7]==b"\x7fELF\x02\x01\x01" and data[18:20]==b"\x3e\0") if interpreter is not None
             else data[:4]==b"PK\x03\x04","original query ELF/JAR format")
        if whole_images:
            with held(pin["path"],modes={mode}) as (fd,st):
                need(st.st_size==size and hash_fd(fd)==sha,"actual sealed normal query source")
    boardpin=project_pin(q["board_device_manifest"]);board=value("board_device_manifest",boardpin)
    need(boardpin["sha256"]==BOARD and
         boardpin["path"]==str(package_root/"etc/droidloom/board-devices"/(BOARD+".json")) and
         publication["board_device_source"]=={"manifest":"etc/droidloom/board-devices/"+BOARD+".json",
             "sha256":BOARD,"source":board},"actual five-query board publication")
    need(board["schema"]==1 and board["scope"]=="android_private_device_source_v1" and
         board["base_cohort_sha256"]==COHORT and board["runtime_manifest_sha256"]==RUNTIME and
         board["source_system_sha256"]==SYSTEM and (board["bytes"],board["sha256"],board["file"])
             ==(8388608,BANK,BANK+".img"),"unchanged actual device bank, new runtime binding")
    bankpin=project_pin(q["device_bank"])
    need(bankpin["path"]==str(package_root/"var/lib/droidloom/cohorts"/COHORT/"board"/(BANK+".img")) and
         (bankpin["bytes"],bankpin["sha256"])==(8388608,BANK),"actual device bank original bytes")
    body("device_bank",bankpin,16*1024*1024)
    if portable is not None:need(set(portable)==set(evidence),"portable five-query evidence has missing or extra members")
    return q,evidence

def pack_android(plan_path,output):
    plan_value,plan=read_json_file(plan_path,1024*1024)
    exact(plan_value,("schema","materials","query_materials"),"normal five-query Android plan")
    need(plan_value["schema"]=="droidloom-normal-android-deb-plan-v3","normal five-query Android plan schema")
    original=pin_shape(plan_value["materials"])
    historical,readback,normal,evidence=admit_camera_materials(original)
    current,query_evidence=admit_query_materials(pin_shape(plan_value["query_materials"]),whole_images=True)
    package_root=safe_absolute(current["package_root"])
    need((current["base_manifest"]["bytes"],current["base_manifest"]["sha256"])==
         (historical["base_manifest"]["bytes"],historical["base_manifest"]["sha256"]),
         "new query publication retains the actual historical camera base")
    for role in IMAGES:
        need((current["images"][role]["bytes"],current["images"][role]["sha256"])==
             (historical["images"][role]["bytes"],historical["images"][role]["sha256"]),
             "new normal query package cannot alter an original camera image")
    basepin=project_pin(current["base_manifest"])
    runtimepin=project_pin(current["runtime_manifest"])
    boardpin=project_pin(current["board_device_manifest"])
    output,root=new_stage(output);inventory={}
    def source(relative,pin,mode):
        pin=project_pin(pin)
        need(pin["path"]==str(package_root/relative),"actual five-query normal input namespace")
        put(root,inventory,relative,pin,mode)
    source("etc/droidloom/cohorts/"+COHORT+".json",basepin,0o444)
    source("etc/droidloom/runtime-cohorts/"+RUNTIME+".json",runtimepin,0o444)
    source("etc/droidloom/board-devices/"+BOARD+".json",boardpin,0o444)
    for role in IMAGES:
        source("var/lib/droidloom/cohorts/"+COHORT+"/images/"+role+".img",current["images"][role],0o444)
    source("var/lib/droidloom/cohorts/"+COHORT+"/board/"+BANK+".img",current["device_bank"],0o444)
    query={r["name"]:project_pin(r) for r in current["query_inputs"]}
    for name,(_,_,mode,_) in QUERY.items():
        source("var/lib/droidloom/runtime-cohorts/"+RUNTIME+"/images/"+name,query[name],mode)
    source("var/lib/droidloom/runtime-cohorts/"+RUNTIME+"/QUERY-INSTALL-REQUIREMENTS.json",
           current["query_install_requirements"],0o444)
    result=build_deb(root,inventory,output,"droidloom-android-cohort","0.1+"+COHORT+".query."+RUNTIME)
    for role,pin in evidence.items():copy_pin(pin,output/("source-"+role+".json"),0o444)
    evidence={role:file_pin(output/("source-"+role+".json")) for role in evidence}
    for name,pin in query_evidence.items():
        if "log_envelope" in pin:
            need(name in {"stderr","archive_stdout","archive_stderr"},"only actual command logs use envelopes")
            new_file(output/query_evidence_member(name),pin["log_envelope"],0o444)
        else:copy_pin(pin,output/query_evidence_member(name),0o444)
    query_evidence={name:file_pin(output/query_evidence_member(name)) for name in query_evidence}
    # Verify the transported copies through the same admission used by public prepare.
    admitted,_=admit_query_materials(query_evidence["materials"],query_evidence)
    need(admitted==current,"copied actual query publication changed")
    receipt={"schema":"droidloom-normal-android-deb-result-v2","plan":plan,**evidence,
             "android_source_commit":ANDROID_SOURCE,"android_source_tree":ANDROID_TREE,
             "query_source_commit":QUERY_SOURCE,"query_source_tree":QUERY_TREE,
             "query_materials":query_evidence["materials"],"query_evidence":query_evidence,
             "query_input_count":len(QUERY),"cohort_sha256":COHORT,"runtime_sha256":RUNTIME,
             "board_device_manifest_sha256":BOARD,"package":result,"inventory":file_pin(output/"INVENTORY.json"),
             "normal_build_exit_code":0,"original_userdata_accessed":False,
             "query_original_labels_required_at_cold_install":True,"query_installed_labels_observed":False,
             "historical_camera_build_reexecuted":False,"actual_new_query_publication_verified":True,
             "physical_install":False,"runtime_qualified":False}
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
