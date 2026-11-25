#!/usr/bin/python3
"""Create immutable cold-deployment candidates; never installs or activates one.

The original Ubuntu filesystem is a target, not a fresh qualification root.
No command in this component invokes dpkg install, changes GRUB, labels the
physical filesystem, accesses original Android data, or enables a service.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
import time
from release import (
    Rejected, SCHEMA, COMMIT, KERNEL, KERNEL_SHA, need, exact, digest, canonical,
    f9, safe_relative, safe_absolute, held, hash_fd, pin_shape, read_pin,
    json_bytes, read_json_file, file_pin, new_file, copy_pin, mkdir_new,
    bounded_process, host_manifest,
)
from cold_publish import (
    COHORT, RUNTIME, BOARD, KERNEL_MODULES_SHA, ANDROID_HANDOFF_SHA,
    ANDROID_MATERIALS_SHA, ANDROID_NORMAL_SHA, ANDROID_TERMINAL_SHA,
    ANDROID_SOURCE, ANDROID_TREE,
)

ROOT_UUID="01c27223-3933-481e-9836-7bd0ef1be8c9"
ORIGINAL_KERNEL="7.0.14-p4cred1"
ORIGINAL_ENTRY="gnulinux-simple-"+ROOT_UUID
REQUIRED_HOST={
 "usr/lib/droidloom/production/current/droidloom-maintenance":0o755,
 "usr/lib/droidloom/production/current/droidloom-maintenance.py":0o444,
}
NAMES={"host":"droidloom-shared-host","kernel":"droidloom-shared-kernel",
       "android":"droidloom-android-cohort"}
SOURCE_PATHS=(
 "/boot/grub/grub.cfg","/boot/grub/grubenv",
 "/boot/vmlinuz-"+ORIGINAL_KERNEL,"/boot/initrd.img-"+ORIGINAL_KERNEL,
 "/usr/bin/grub-script-check","/usr/bin/grub-editenv","/usr/sbin/update-grub",
 "/usr/sbin/grub-mkconfig","/usr/sbin/mkinitramfs","/usr/bin/dpkg","/usr/bin/dpkg-deb",
)
# These are metadata-only preservation guards, not copied account/secret inputs.
PRESERVE_METADATA=(
 "/etc/passwd","/etc/group","/etc/shadow","/etc/gshadow",
 "/etc/ssh","/etc/ssh/sshd_config","/home/alex",
)
LSMS="lockdown,capability,landlock,yama,selinux,apparmor,bpf,ima,evm"
CORE_BLOCKERS=(
 "normal_owned_full_guest_acceptance",
 "physical_independent_private_working_copy_acceptance",
 "normal_native_libselinux_apparmor_gdm_candidate_admission",
 "same_candidate_original_host_initramfs_and_readback",
 "same_candidate_original_host_file_contexts_and_readback",
 "normal_selected_original_data_and_five_file_mac_publication",
 "actual_production_maintenance_and_original_ubuntu_return",
)

def original_public(path):
    with held(path,root=True,maximum=512*1024*1024) as (fd,st):
        need(not (stat.S_IMODE(st.st_mode)&0o022),"public original is writable by other users")
        return {"pin":{"path":str(path),"bytes":st.st_size,"sha256":hash_fd(fd)},
                "identity":list(f9(st))}

def mount_identity(path):
    r=bounded_process(["/usr/bin/findmnt","-J","-o","UUID,FSTYPE,SOURCE,TARGET",
                       "--target",path],seconds=5,maximum=65536)
    need(r["exit"]==0,"stock findmnt failed")
    v=json_bytes(r["stdout"]);rows=v.get("filesystems")
    need(isinstance(rows,list) and len(rows)==1,"one actual native mount")
    row=rows[0]
    need(row.get("uuid")==ROOT_UUID and row.get("fstype")=="ext4","original root filesystem differs")
    need(isinstance(row.get("source"),str) and row["source"].startswith("/dev/"),"actual block-backed root")
    return row

def preflight(output):
    output=safe_absolute(str(output))
    need(output.parent==Path("/home/alex/work/p4-native-maintenance-cutover-516eec-r1")
         and re.fullmatch(r"COLD-PREFLIGHT-[a-z0-9-]+\.json",output.name),
         "preflight output is confined to the fixed public evidence directory")
    need(os.geteuid()==0 and os.getuid()==0,"public cold preflight requires original root")
    need(os.uname().release==ORIGINAL_KERNEL,"cold preflight must run on original Ubuntu kernel")
    need(Path("/proc/self/uid_map").read_text().split()==["0","0","4294967295"],"initial user namespace")
    own=os.stat("/");pid1=os.stat("/proc/1/root")
    need((own.st_dev,own.st_ino)==(pid1.st_dev,pid1.st_ino),"original PID1 root must be this filesystem")
    root=mount_identity("/");boot=mount_identity("/boot")
    need(root["source"]==boot["source"],"reviewed /boot and root must share the original filesystem")
    originals={p:original_public(p) for p in SOURCE_PATHS}
    grub=read_pin(originals["/boot/grub/grub.cfg"]["pin"],16*1024*1024,True)
    entry_lines=[line for line in grub.decode("utf-8","strict").splitlines()
                 if line.startswith("menuentry ") and ("'"+ORIGINAL_ENTRY+"'") in line]
    need(len(entry_lines)==1,"exact original stock Ubuntu entry missing or duplicated")
    env=read_pin(originals["/boot/grub/grubenv"]["pin"],4096,True)
    need(len(env)==1024 and env.startswith(b"# GRUB Environment Block"),"original GRUB environment")
    preserved={}
    for path in PRESERVE_METADATA:
        st=os.lstat(path)
        need(st.st_uid==0 or path=="/home/alex","unexpected preserved path owner")
        need(not stat.S_ISLNK(st.st_mode),"preserved path must not be a symlink")
        preserved[path]=list(f9(st))
    result={"schema":"droidloom-original-ubuntu-cold-preflight-v1",
            "kernel":ORIGINAL_KERNEL,"root_uuid":ROOT_UUID,"original_entry":ORIGINAL_ENTRY,
            "root_mount":root,"boot_mount":boot,"root_identity":[own.st_dev,own.st_ino],
            "boot_id":Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "observed_monotonic_ns":time.monotonic_ns(),"public_originals":originals,
            "preserved_metadata_only":preserved,"account_or_secret_bytes_read":False,
            "original_android_data_accessed":False,"system_modified":False,
            "runtime_qualified":False}
    new_file(safe_absolute(str(output)),canonical(result),0o444)
    return {"preflight":file_pin(output),"system_modified":False}

def admit_target(pin):
    target=json_bytes(read_pin(pin,1024*1024))
    exact(target,("schema","kernel","root_uuid","original_entry","root_mount","boot_mount",
                 "root_identity","boot_id","observed_monotonic_ns","public_originals",
                 "preserved_metadata_only","account_or_secret_bytes_read",
                 "original_android_data_accessed","system_modified","runtime_qualified"),"cold target")
    need(target["schema"]=="droidloom-original-ubuntu-cold-preflight-v1" and
         target["kernel"]==ORIGINAL_KERNEL and target["root_uuid"]==ROOT_UUID and
         target["original_entry"]==ORIGINAL_ENTRY,"fixed original Ubuntu target")
    need(all(target[x] is False for x in ("account_or_secret_bytes_read",
         "original_android_data_accessed","system_modified","runtime_qualified")),"readonly original target evidence")
    need(set(target["public_originals"])==set(SOURCE_PATHS),"complete original public file inventory")
    for path,row in target["public_originals"].items():
        exact(row,("pin","identity"),"original file row")
        pin_shape(row["pin"]);need(row["pin"]["path"]==path,"original public path substitution")
        need(isinstance(row["identity"],list) and len(row["identity"])==9,"original F9 identity")
        need(row["identity"][3:6]==[0,0,1] and row["identity"][6]==row["pin"]["bytes"],
             "original public root ownership/links/length")
    for key in ("root_mount","boot_mount"):
        need(target[key].get("uuid")==ROOT_UUID and target[key].get("fstype")=="ext4","original fixed ext4 target")
    need(target["root_mount"]["source"]==target["boot_mount"]["source"],"separate unreviewed boot filesystem")
    return target

def package_control(pin,expected_name):
    pin_shape(pin)
    with held(pin["path"]) as (fd,st):
        need(st.st_size==pin["bytes"] and hash_fd(fd)==pin["sha256"],"normal package original bytes")
        r=bounded_process(["/usr/bin/dpkg-deb","--ctrl-tarfile",f"/proc/self/fd/{fd}"],
                          seconds=30,maximum=4*1024*1024,pass_fds=(fd,))
        need(r["exit"]==0,"stock normal Debian control reader failed")
        found={}
        with tarfile.open(fileobj=io.BytesIO(r["stdout"]),mode="r:") as archive:
            for entry in archive:
                rel=entry.name[2:] if entry.name.startswith("./") else entry.name
                if rel in ("","."):
                    need(entry.isdir() and entry.uid==entry.gid==0,"normal control directory");continue
                need(rel in ("control","md5sums") and rel not in found and entry.isfile()
                     and entry.uid==entry.gid==0 and entry.mode==0o644,"only fixed normal control files")
                need(0<entry.size<=3*1024*1024,"bounded normal package control")
                f=archive.extractfile(entry);need(f is not None,"normal control leaf")
                found[rel]=f.read()
        need(set(found)=={"control","md5sums"},"normal package control set")
        fields={}
        for line in found["control"].decode("utf-8","strict").splitlines():
            if line.startswith(" "):continue
            need(": " in line,"normal control field")
            k,v=line.split(": ",1);need(k not in fields,"duplicate normal control field");fields[k]=v
        need(fields.get("Package")==expected_name and fields.get("Architecture")=="amd64",
             "normal package name/architecture")
        return {"package":fields["Package"],"version":fields["Version"],"architecture":"amd64",
                "control_sha256":hashlib.sha256(found["control"]).hexdigest(),
                "md5sums_sha256":hashlib.sha256(found["md5sums"]).hexdigest(),
                "maintainer_scripts":False}

def component(role,pin):
    result=json_bytes(read_pin(pin,2*1024*1024))
    need(result.get("schema")=="droidloom-normal-"+role+"-deb-result-v1" and
         result.get("normal_build_exit_code")==0 and result.get("physical_install") is False and
         result.get("runtime_qualified") is False,"completed ordinary Debian component required")
    package=pin_shape(result["package"])
    control=package_control(package,NAMES[role])
    inputs={role+"-result.json":pin,role+".deb":package}
    if role=="host":
        m,rows=host_manifest(result["host_manifest"])
        need(m["commit"]==result["source_commit"] and m["tree"]==result["source_tree"],
             "normal host source binding")
        need(len(m["files"])==result["file_count"],"normal host inventory count")
        inputs["host-manifest.json"]=result["host_manifest"]
        missing=[p for p,mode in REQUIRED_HOST.items() if p not in rows or rows[p]["mode"]!=mode]
        info={"source_commit":m["commit"],"source_tree":m["tree"],
              "host_file_count":len(rows),"missing_required_maintenance":missing}
    elif role=="kernel":
        need(result.get("kernel_release")==KERNEL and result.get("kernel_sha256")==KERNEL_SHA and
             result.get("module_count")==6797 and result.get("index_count")==15 and
             result.get("all_module_original_bytes_verified") is True and
             result["modules_manifest"]["sha256"]==KERNEL_MODULES_SHA,"current shared kernel/module cohort")
        inputs["kernel-inventory.json"]=result["inventory"]
        info={"kernel_release":KERNEL,"kernel_sha256":KERNEL_SHA,"modules":6797}
    else:
        need(result.get("cohort_sha256")==COHORT and result.get("runtime_sha256")==RUNTIME and
             result.get("board_device_manifest_sha256")==BOARD and
             result.get("original_userdata_accessed") is False and
             result["handoff"]["sha256"]==ANDROID_HANDOFF_SHA and
             result.get("query_original_labels_required_at_cold_install") is True and
             result.get("query_installed_labels_observed") is False,"current normal Android cohort")
        need((result.get("android_source_commit"),result.get("android_source_tree"))==
             (ANDROID_SOURCE,ANDROID_TREE),"completed camera normal source")
        for name,size,sha in (("materials",12961,ANDROID_MATERIALS_SHA),
               ("handoff",135437,ANDROID_HANDOFF_SHA),("normal_result",120640,ANDROID_NORMAL_SHA),
               ("normal_terminal",782,ANDROID_TERMINAL_SHA)):
            source=pin_shape(result[name])
            need((source["bytes"],source["sha256"])==(size,sha),"fixed actual Android source evidence")
            read_pin(source,1024*1024)
            inputs["android-source-"+name+".json"]=source
        inputs["android-inventory.json"]=result["inventory"]
        info={"cohort_sha256":COHORT,"runtime_sha256":RUNTIME,
              "android_source_commit":ANDROID_SOURCE,"android_source_tree":ANDROID_TREE,
              "query_labels_require_actual_cold_install_readback":True}
    return inputs,info,control

def grub_candidate(deployment_id):
    digest(deployment_id)
    entry="droidloom-shared-"+deployment_id
    command=("root=UUID="+ROOT_UUID+" rootfstype=ext4 rw rootwait enforcing=1 "
       "audit_backlog_limit=32768 lsm="+LSMS+" audit=1 "
       "init=/usr/lib/droidloom/production/current/droidloom-board-init "
       "systemd.unit=graphical.target systemd.log_target=journal-or-kmsg systemd.show_status=1")
    text=("menuentry 'Droidloom shared kernel "+deployment_id[:12]+"' --id '"+entry+"' {\n"
       "    insmod part_gpt\n    insmod ext2\n"
       "    search --no-floppy --fs-uuid --set=root "+ROOT_UUID+"\n"
       "    linux /boot/droidloom/kernels/"+KERNEL_SHA+"/vmlinuz "+command+"\n"
       "    initrd /boot/droidloom/releases/"+deployment_id+"/initrd.img\n}\n")
    generator="#!/bin/sh\nset -eu\nexec cat /boot/grub/droidloom/"+deployment_id+".cfg\n"
    defaults=("GRUB_DEFAULT='"+ORIGINAL_ENTRY+"'\nGRUB_TIMEOUT_STYLE=menu\nGRUB_TIMEOUT=10\n")
    return {"entry":entry,"command_line":command,"config":text.encode(),
            "generator":generator.encode(),"defaults":defaults.encode()}

def prepare(plan_path,output):
    need(os.geteuid()!=0,"release preparation runs as an ordinary build user")
    plan,planpin=read_json_file(plan_path,1024*1024)
    exact(plan,("schema","components","target_preflight"),"cold release plan")
    need(plan["schema"]=="droidloom-cold-release-preparation-v1","cold release plan schema")
    exact(plan["components"],("host","kernel","android"),"normal component roles")
    target=admit_target(pin_shape(plan["target_preflight"]))
    all_inputs={"target-preflight.json":plan["target_preflight"]}
    details={};controls={}
    for role in ("host","kernel","android"):
        files,info,control=component(role,pin_shape(plan["components"][role]))
        need(not (set(files)&set(all_inputs)),"duplicate source role")
        all_inputs.update(files);details[role]=info;controls[role]=control
    source=details["host"]
    need(COMMIT.fullmatch(source["source_commit"]) and COMMIT.fullmatch(source["source_tree"]),
         "normal host source objects")
    deployment=hashlib.sha256(canonical({"source":source,"packages":{
        k:{"bytes":all_inputs[k+".deb"]["bytes"],"sha256":all_inputs[k+".deb"]["sha256"]}
        for k in ("host","kernel","android")},"root_uuid":ROOT_UUID})).hexdigest()
    grub=grub_candidate(deployment)
    blockers=list(CORE_BLOCKERS)
    if source["missing_required_maintenance"]:blockers.insert(0,"normal_host_missing_fixed_maintenance_payload")
    intent={"schema":"droidloom-cold-transaction-candidate-v1","deployment_id":deployment,
        "root_uuid":ROOT_UUID,"original_kernel":ORIGINAL_KERNEL,"original_entry":ORIGINAL_ENTRY,
        "new_entry":grub["entry"],"kernel_release":KERNEL,"kernel_sha256":KERNEL_SHA,
        "component_control":controls,"component_identity":details,
        "original_grub":target["public_originals"]["/boot/grub/grub.cfg"],
        "original_grubenv":target["public_originals"]["/boot/grub/grubenv"],
        "public_package_install_order":["kernel.deb","android.deb","host.deb"],
        "candidate_install_targets":{
          "GRUB-CANDIDATE.cfg":"/boot/grub/droidloom/"+deployment+".cfg",
          "GRUB-GENERATOR":"/etc/grub.d/42_droidloom_"+deployment,
          "GRUB-DEFAULTS.cfg":"/etc/default/grub.d/90-droidloom-recovery.cfg"},
        "required_new_initrd":"/boot/droidloom/releases/"+deployment+"/initrd.img",
        "required_final_kernel_command_line":grub["command_line"],
        "activation_blockers":blockers,"activation_supported":False,
        "fresh_fixture_root_is_not_a_deployment_target":True,
        "accounts_passwords_ssh_and_original_android_data_are_not_payloads":True,
        "physical_install":False,"runtime_qualified":False}
    output=safe_absolute(str(output));mkdir_new(output)
    bundle=output/"release";bundle.mkdir(mode=0o700)
    inventory=[]
    for name,pin in sorted(all_inputs.items()):
        safe_relative(name);need("/" not in name,"flat candidate inventory")
        copy_pin(pin,bundle/name,0o444)
        inventory.append({"path":name,"bytes":pin["bytes"],"sha256":pin["sha256"],"mode":0o444})
    for name,body in (("COLD-INTENT.json",canonical(intent)),("GRUB-CANDIDATE.cfg",grub["config"]),
                      ("GRUB-GENERATOR",grub["generator"]),("GRUB-DEFAULTS.cfg",grub["defaults"])):
        new_file(bundle/name,body,0o444)
        inventory.append({"path":name,"bytes":len(body),"sha256":hashlib.sha256(body).hexdigest(),"mode":0o444})
    release={"schema":SCHEMA,"source_commit":source["source_commit"],"source_tree":source["source_tree"],
             "files":sorted(inventory,key=lambda r:r["path"]),"qualified":False}
    raw=canonical(release);release_id=hashlib.sha256(raw).hexdigest()
    new_file(bundle/"RELEASE.json",raw,0o444)
    verification=verify(bundle,release_id)
    result={"schema":"droidloom-cold-release-prepared-v1","plan":planpin,"release":file_pin(bundle/"RELEASE.json"),
            "release_id":release_id,"deployment_id":deployment,"files":len(inventory),
            "verification":verification,"activation_blockers":blockers,
            "activation_supported":False,"system_modified":False,"runtime_qualified":False}
    new_file(output/"RESULT.json",canonical(result));return result

def verify(bundle,release_id):
    bundle=safe_absolute(str(bundle));digest(release_id)
    value,pin=read_json_file(bundle/"RELEASE.json",8*1024*1024,modes={0o444})
    need(pin["sha256"]==release_id,"release manifest identity")
    exact(value,("schema","source_commit","source_tree","files","qualified"),"normal release")
    need(value["schema"]==SCHEMA and value["qualified"] is False,"candidate is not qualification")
    need(COMMIT.fullmatch(value["source_commit"]) and COMMIT.fullmatch(value["source_tree"]),"normal source objects")
    rows=value["files"];need(isinstance(rows,list) and 1<=len(rows)<=128,"bounded release inventory")
    seen=set()
    for row in rows:
        exact(row,("path","bytes","sha256","mode"),"release row")
        name=safe_relative(row["path"]);need("/" not in name and name not in seen and row["mode"]==0o444,
                                             "flat immutable unique candidate leaf")
        seen.add(name)
        with held(bundle/name,modes={0o444}) as (fd,st):
            need(st.st_size==row["bytes"] and hash_fd(fd)==digest(row["sha256"]),"candidate payload changed")
    need({p.name for p in bundle.iterdir()}==seen|{"RELEASE.json"},"unlisted release member")
    return {"manifest":pin,"files_verified":len(seen),"qualified":False}

def activate(bundle,release_id):
    verify(bundle,release_id)
    # No invented boolean, caller assertion, or public-fresh-VM result grants
    # physical-data qualification. This remains a closed interface until the
    # actual owned-runtime/private-working-copy verifier is integrated.
    raise Rejected("activation unavailable: no admitted owned-runtime and physical private-working-copy acceptance verifier")

def initramfs_materials(bundle,release_id,native_bundle,native_id,output):
    """Read actual normal public and sixteen-native archives for private staging.

    The Rust original-host producer calls this readonly existing admission
    code before an isolated normal package installation. This grants neither
    physical dpkg authority nor a boot/service action.
    """
    from cold_apply import load_inputs,package_payload
    import native_release
    need(os.getuid()==os.geteuid()==0,"protected original-host staging inputs require root")
    bundle=safe_absolute(str(bundle));native_bundle=safe_absolute(str(native_bundle))
    output=safe_absolute(str(output))
    need(output.parent.parent==Path("/var/lib/droidloom-qualification") and
         output.parent.name.startswith("original-initramfs-") and output.name=="MATERIALS.json",
         "fixed create-only original-host material output")
    intent,entries,_,packages,controls,scopes=load_inputs(bundle,release_id)
    descriptor,closure,natives,payloads=native_release.verify_bundle(native_bundle,native_id,True)
    need(descriptor["schema"]==native_release.FULL_SCHEMA and len(natives)==16,
         "original-host initramfs requires all sixteen normal native packages")
    rows=[]
    for role in sorted(natives):
        control=payloads[role]["new"]["control"]
        rows.append({"role":role,"package":natives[role]["new"],
                     "name":control["Package"],"version":control["Version"],
                     "architecture":control["Architecture"]})
    for role in ("kernel","host"):
        package_payload(packages[role],scopes[role],output.parent)
        rows.append({"role":role,"package":packages[role],"name":controls[role]["package"],
                     "version":controls[role]["version"],"architecture":controls[role]["architecture"]})
    required=[]
    for relative,target in (
       ("usr/lib/droidloom/production/current/droidloomd","/usr/lib/droidloom/production/current/droidloomd"),
       ("usr/lib/droidloom/production/current/droidloom-early-firststage","/usr/lib/droidloom/production/current/droidloom-early-firststage"),
       ("usr/share/initramfs-tools/scripts/init-bottom/droidloom-early-custody","/scripts/init-bottom/droidloom-early-custody")):
        row=entries[relative];need(row["role"]=="host","normal host owns required initramfs member")
        required.append({"source_path":"/"+relative,"initrd_path":target,
                         "bytes":row["bytes"],"sha256":row["sha256"],"mode":row["mode"]})
    for role,prefix in (("selinux","usr/lib/x86_64-linux-gnu/libselinux.so."),
                        ("apparmor","usr/lib/x86_64-linux-gnu/libapparmor.so.")):
        # The package role names differ from the Debian package names. Select
        # by its already source-verified control, not by a caller pathname.
        name="libselinux1" if role=="selinux" else "libapparmor1"
        matches=[v["new"] for v in payloads.values() if v["new"]["control"]["Package"]==name]
        need(len(matches)==1,"one actual normal native initramfs library")
        library=[(p,v) for p,v in matches[0]["payload"].items() if p.startswith(prefix) and v["type"]=="0"]
        need(len(library)==1,"one complete regular native library payload")
        p,row=library[0];need(row["uid"]==row["gid"]==0,"normal native library owner")
        required.append({"source_path":"/"+p,"initrd_path":"/"+p,
                         "bytes":row["bytes"],"sha256":row["sha256"],"mode":row["mode"]})
    module_path="usr/lib/droidloom/kernels/"+KERNEL+"/MODULES.json"
    module=entries[module_path]
    need(module["sha256"]==KERNEL_MODULES_SHA,"same complete shared-kernel modules")
    result={"schema":"droidloom.original-host-initramfs-materials.v1",
       "public_release":file_pin(bundle/"RELEASE.json"),"public_release_id":release_id,
       "deployment_id":intent["deployment_id"],"native_release":file_pin(native_bundle/"NATIVE-RELEASE.json"),
       "native_release_id":native_id,"native_closure":closure["closure_sha256"],
       "kernel_release":KERNEL,"kernel_sha256":KERNEL_SHA,"root_uuid":ROOT_UUID,
       "original_kernel":ORIGINAL_KERNEL,"cohort_sha256":COHORT,"runtime_sha256":RUNTIME,
       "packages":rows,"required_initrd_members":required,
       "module_manifest":{"path":"/"+module_path,"bytes":module["bytes"],"sha256":module["sha256"]},
       "physical_install":False,"qualification_boot_authorized":False,"production_ready":False}
    new_file(output,canonical(result),0o444)
    return {"materials":file_pin(output),"physical_install":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    q=sub.add_parser("preflight");q.add_argument("--output",required=True,type=Path)
    q=sub.add_parser("prepare");q.add_argument("--plan",required=True,type=Path);q.add_argument("--output",required=True,type=Path)
    q=sub.add_parser("initramfs-materials")
    q.add_argument("--bundle",required=True,type=Path);q.add_argument("--release",required=True)
    q.add_argument("--native-bundle",required=True,type=Path);q.add_argument("--native-release",required=True)
    q.add_argument("--output",required=True,type=Path)
    for name in ("verify","activate"):
        q=sub.add_parser(name);q.add_argument("--bundle",required=True,type=Path);q.add_argument("--release",required=True)
    a=p.parse_args()
    if a.command=="preflight":result=preflight(a.output)
    elif a.command=="prepare":result=prepare(a.plan,a.output)
    elif a.command=="verify":result=verify(a.bundle,a.release)
    elif a.command=="initramfs-materials":result=initramfs_materials(a.bundle,a.release,a.native_bundle,a.native_release,a.output)
    else:result=activate(a.bundle,a.release)
    sys.stdout.buffer.write(canonical(result));sys.stdout.buffer.flush()

if __name__=="__main__":
    try:main()
    except (Rejected,OSError,ValueError,KeyError,tarfile.TarError) as e:
        print("droidloom-cold-transaction: "+str(e),file=sys.stderr);sys.exit(1)
