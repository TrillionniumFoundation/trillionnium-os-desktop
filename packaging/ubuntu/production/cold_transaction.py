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
    Rejected, SCHEMA, COMMIT, KERNEL, KERNEL_SHA, STORE, need, exact, digest, canonical,
    f9, safe_relative, safe_absolute, held, hash_fd, pin_shape, read_pin,
    json_bytes, read_json_file, file_pin, new_file, copy_pin, mkdir_new,
    bounded_process, host_manifest,
)
from cold_publish import COHORT, RUNTIME, BOARD, KERNEL_MODULES_SHA, ANDROID_HANDOFF_SHA

ROOT_UUID="01c27223-3933-481e-9836-7bd0ef1be8c9"
ORIGINAL_KERNEL="7.0.14-p4cred1"
ORIGINAL_ENTRY="gnulinux-simple-"+ROOT_UUID
REQUIRED_HOST={
 "usr/lib/droidloom/production/current/droidloom-maintenance":0o755,
 "usr/lib/droidloom/production/current/droidloom-maintenance.py":0o444,
 "usr/share/droidloom/production/droidloom-production.target":0o644,
 "usr/share/droidloom/board/pocket4-board-inputs.lock.json":0o444,
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


COLD_MODULES=("release.py","cold_publish.py","cold_transaction.py","cold_apply.py",
              "native_bundle.py","systemd_bundle.py","native_release.py","cold_native.py")
REQUIRED_HOST.update({"usr/lib/droidloom/production/current/"+name:0o444 for name in COLD_MODULES})

def native_identity(inputs):
    value=inputs["index"];descriptor=inputs["descriptor"]
    return {"release_id":value["native_release_id"],"closure_sha256":value["closure_sha256"],
            "archive_index_sha256":inputs["index_pin"]["sha256"],"archive":value["archive"],
            "manifest":value["manifest"],
            "package_roles":[{k:r[k] for k in ("role","name","source","old_version","new_version")}
                             |{"old_package_sha256":r["old"]["package"]["sha256"],
                               "new_package_sha256":r["new"]["package"]["sha256"]}
                             for r in descriptor["package_roles"]]}

def deployment_identity(source,packages,native=None):
    value={"source":source,"packages":{role:{"bytes":packages[role]["bytes"],
                                            "sha256":packages[role]["sha256"]}
                                      for role in ("host","kernel","android")},"root_uuid":ROOT_UUID}
    if native is not None:
        value["native"]={"release_id":native["release_id"],
                         "archive_index_sha256":native["archive_index_sha256"],
                         "archive_sha256":native["archive"]["sha256"]}
    return hashlib.sha256(canonical(value)).hexdigest()

def bound_native_inputs(bundle,intent=None,*,root=False):
    # This validates material identity only. The caller still needs the actual
    # owned runtime and original-device private-account authority before dpkg.
    import native_release
    bundle=safe_absolute(str(bundle))
    if intent is None:
        intent,_=read_json_file(bundle/"COLD-INTENT.json",2*1024*1024,root,{0o444})
    need(intent.get("schema")=="droidloom-cold-transaction-candidate-v2",
         "cold operation requires a native-bound candidate")
    inputs=native_release.archive_inputs(file_pin(bundle/native_release.ARCHIVE_INDEX),root)
    native=native_identity(inputs)
    need(intent.get("native_material")==native
         and intent.get("native_material_target")==str(STORE/"native-releases"/native["release_id"])
         and intent.get("native_before_public") is True,
         "fixed normal native cold intent")
    need(intent["component_identity"].get("native")==native,"same native component identity")
    manifest,rows=host_manifest(file_pin(bundle/"host-manifest.json"))
    source={"source_commit":manifest["commit"],"source_tree":manifest["tree"],
            "host_file_count":len(rows),
            "missing_required_maintenance":[p for p,mode in REQUIRED_HOST.items()
                                            if p not in rows or rows[p]["mode"]!=mode]}
    need(intent["component_identity"]["host"]==source,"same actual normal host source and cold modules")
    packages={role:file_pin(bundle/(role+".deb")) for role in ("host","kernel","android")}
    need(intent["deployment_id"]==deployment_identity(source,packages,native),
         "public/native packages share the actual cold deployment identity")
    return inputs

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
        inputs["android-inventory.json"]=result["inventory"]
        info={"cohort_sha256":COHORT,"runtime_sha256":RUNTIME,
              "query_labels_require_actual_cold_install_readback":True}
    return inputs,info,control

BOOT_HOST_MEMBERS={
    "DROIDLOOM-PRODUCTION.target":("usr/share/droidloom/production/droidloom-production.target",0o644),
    "BOARD-INPUTS.lock.json":("usr/share/droidloom/board/pocket4-board-inputs.lock.json",0o444),
}

def normal_host_boot_inputs(package,manifest_pin):
    """Use original normal-host bytes for both activation and native-init identity."""
    _,rows=host_manifest(manifest_pin)
    expected={relative:(name,mode) for name,(relative,mode) in BOOT_HOST_MEMBERS.items()}
    for relative,(_,mode) in expected.items():
        row=rows.get(relative)
        need(row is not None and row["mode"]==mode and 0<row["size"]<65536,
             "normal host must publish its original target and board contract")
    with held(package["path"]) as (fd,st):
        need(st.st_size==package["bytes"] and hash_fd(fd)==package["sha256"],"same normal host package")
        r=bounded_process(["/usr/bin/dpkg-deb","--fsys-tarfile",f"/proc/self/fd/{fd}"],
                          seconds=60,maximum=64*1024*1024,pass_fds=(fd,))
        need(r["exit"]==0,"normal host package reader failed")
    found={}
    with tarfile.open(fileobj=io.BytesIO(r["stdout"]),mode="r:") as archive:
        for member in archive:
            name=member.name[2:] if member.name.startswith("./") else member.name
            if name not in expected:continue
            leaf,mode=expected[name];row=rows[name]
            need(leaf not in found and member.isfile() and member.uid==member.gid==0
                 and member.mode==mode and member.size==row["size"],"normal boot member metadata")
            stream=archive.extractfile(member);need(stream is not None,"normal boot member body")
            body=stream.read(65536)
            need(len(body)==row["size"] and hashlib.sha256(body).hexdigest()==row["sha256"],
                 "normal boot member whole bytes")
            found[leaf]=body
    need(set(found)==set(BOOT_HOST_MEMBERS),"exact normal boot member set")
    return found

def native_init_contract(raw,native=None):
    value=json_bytes(raw)
    need(value.get("schema")=="droidloom-pocket4-joint-initramfs-inputs-v1",
         "normal board input contract schema")
    selected=value.get("native_init")
    exact(selected,("path","size","sha256","package_name","package_version",
                    "package_architecture","package_bytes","package_sha256"),"normal native init")
    need(selected["path"]=="/usr/lib/systemd/systemd" and selected["package_name"]=="systemd"
         and selected["package_architecture"]=="amd64"
         and type(selected["size"]) is int and 0<selected["size"]<=16*1024*1024
         and type(selected["package_bytes"]) is int and 0<selected["package_bytes"]<=128*1024*1024
         and isinstance(selected["package_version"],str)
         and re.fullmatch(r"[A-Za-z0-9.+:~_-]{1,128}",selected["package_version"]),
         "fixed normal native-init role")
    digest(selected["sha256"]);digest(selected["package_sha256"])
    if native is not None:
        matches=[r for r in native["descriptor"]["package_roles"] if r["name"]=="systemd"]
        need(len(matches)==1,"one actual normal systemd package")
        role=matches[0];package=role["new"]["package"]
        need(role["new_version"]==selected["package_version"]
             and package["bytes"]==selected["package_bytes"]
             and package["sha256"]==selected["package_sha256"],
             "native closure and board init must use the same normal Debian package")
    return selected

def native_init_at(root,selected):
    """Recheck the installed ELF; no alternate digest or caller-selected path."""
    path=Path(root)/selected["path"].lstrip("/")
    with held(path,root=True,modes={0o755},maximum=16*1024*1024) as (fd,st):
        need(st.st_size==selected["size"] and hash_fd(fd)==selected["sha256"],
             "installed native init differs from the normal board contract")
        return {"path":selected["path"],"identity":list(f9(st)),
                "bytes":st.st_size,"sha256":selected["sha256"]}

def grub_candidate(deployment_id):
    digest(deployment_id)
    entry="droidloom-shared-"+deployment_id
    command=("root=UUID="+ROOT_UUID+" rootfstype=ext4 rw rootwait enforcing=1 "
       "audit_backlog_limit=32768 lsm="+LSMS+" audit=1 "
       "init=/usr/lib/droidloom/production/current/droidloom-board-init "
       "systemd.unit=droidloom-production.target systemd.log_target=journal-or-kmsg systemd.show_status=1")
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
    need(plan["schema"] in ("droidloom-cold-release-preparation-v1","droidloom-cold-release-preparation-v2"),"cold release plan schema")
    native_plan=plan["schema"].endswith("-v2")
    exact(plan["components"],("host","kernel","android","native") if native_plan else
          ("host","kernel","android"),"normal component roles")
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
    native_inputs=None;native=None
    if native_plan:
        import native_release
        native_inputs=native_release.archive_inputs(pin_shape(plan["components"]["native"]))
        native=native_identity(native_inputs);details["native"]=native
        for name,key in ((native_release.ARCHIVE_INDEX,"index_pin"),
                         (native_release.MANIFEST_NAME,"manifest_pin"),(native_release.ARCHIVE_NAME,"archive_pin")):
            all_inputs[name]=native_inputs[key]
    deployment=deployment_identity(source,{r:all_inputs[r+".deb"] for r in ("host","kernel","android")},native)
    grub=grub_candidate(deployment)
    boot_inputs=normal_host_boot_inputs(all_inputs["host.deb"],all_inputs["host-manifest.json"])
    selected_init=native_init_contract(boot_inputs["BOARD-INPUTS.lock.json"],native_inputs)
    blockers=list(CORE_BLOCKERS)
    if source["missing_required_maintenance"]:blockers.insert(0,"normal_host_missing_fixed_maintenance_payload")
    intent={"schema":"droidloom-cold-transaction-candidate-v2" if native_plan else "droidloom-cold-transaction-candidate-v1","deployment_id":deployment,
        "root_uuid":ROOT_UUID,"original_kernel":ORIGINAL_KERNEL,"original_entry":ORIGINAL_ENTRY,
        "new_entry":grub["entry"],"kernel_release":KERNEL,"kernel_sha256":KERNEL_SHA,
        "component_control":controls,"component_identity":details,
        "original_grub":target["public_originals"]["/boot/grub/grub.cfg"],
        "original_grubenv":target["public_originals"]["/boot/grub/grubenv"],
        "public_package_install_order":["kernel.deb","android.deb","host.deb"],
        "candidate_install_targets":{
          "GRUB-CANDIDATE.cfg":"/boot/grub/droidloom/"+deployment+".cfg",
          "GRUB-GENERATOR":"/etc/grub.d/42_droidloom_"+deployment,
          "GRUB-DEFAULTS.cfg":"/etc/default/grub.d/90-droidloom-recovery.cfg",
          "DROIDLOOM-PRODUCTION.target":"/etc/systemd/system/droidloom-production.target"},
        "required_new_initrd":"/boot/droidloom/releases/"+deployment+"/initrd.img",
        "required_final_kernel_command_line":grub["command_line"],
        "native_init":selected_init,
        "activation_blockers":blockers,"activation_supported":False,
        "fresh_fixture_root_is_not_a_deployment_target":True,
        "accounts_passwords_ssh_and_original_android_data_are_not_payloads":True,
        "physical_install":False,"runtime_qualified":False}
    if native is not None:
        intent.update(native_material=native,native_material_target=str(STORE/"native-releases"/native["release_id"]),
                      native_before_public=True)
    output=safe_absolute(str(output));mkdir_new(output)
    native_check=None
    if native_inputs is not None:
        native_check=native_release.inspect_archive(native_inputs["index_pin"],output/"native-readback")
    bundle=output/"release";bundle.mkdir(mode=0o700)
    inventory=[]
    for name,pin in sorted(all_inputs.items()):
        safe_relative(name);need("/" not in name,"flat candidate inventory")
        copy_pin(pin,bundle/name,0o444)
        inventory.append({"path":name,"bytes":pin["bytes"],"sha256":pin["sha256"],"mode":0o444})
    for name,body in (("COLD-INTENT.json",canonical(intent)),("GRUB-CANDIDATE.cfg",grub["config"]),
                      ("GRUB-GENERATOR",grub["generator"]),("GRUB-DEFAULTS.cfg",grub["defaults"]),
                       *boot_inputs.items()):
        new_file(bundle/name,body,0o444)
        inventory.append({"path":name,"bytes":len(body),"sha256":hashlib.sha256(body).hexdigest(),"mode":0o444})
    release={"schema":SCHEMA,"source_commit":source["source_commit"],"source_tree":source["source_tree"],
             "files":sorted(inventory,key=lambda r:r["path"]),"qualified":False}
    raw=canonical(release);release_id=hashlib.sha256(raw).hexdigest()
    new_file(bundle/"RELEASE.json",raw,0o444)
    verification=verify(bundle,release_id)
    result={"schema":"droidloom-cold-release-prepared-v2" if native_plan else "droidloom-cold-release-prepared-v1","plan":planpin,"release":file_pin(bundle/"RELEASE.json"),
            "release_id":release_id,"deployment_id":deployment,"files":len(inventory),
            "verification":verification,"activation_blockers":blockers,
            "activation_supported":False,"system_modified":False,"runtime_qualified":False}
    if native_check is not None:result["native_material_verification"]=native_check
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
    result={"manifest":pin,"files_verified":len(seen),"qualified":False}
    intent,_=read_json_file(bundle/"COLD-INTENT.json",2*1024*1024,modes={0o444})
    if "DROIDLOOM-PRODUCTION.target" in seen:
        grub=grub_candidate(intent["deployment_id"])
        need(intent["required_final_kernel_command_line"]==grub["command_line"]
             and intent["candidate_install_targets"]=={
                 "GRUB-CANDIDATE.cfg":"/boot/grub/droidloom/"+intent["deployment_id"]+".cfg",
                 "GRUB-GENERATOR":"/etc/grub.d/42_droidloom_"+intent["deployment_id"],
                 "GRUB-DEFAULTS.cfg":"/etc/default/grub.d/90-droidloom-recovery.cfg",
                 "DROIDLOOM-PRODUCTION.target":"/etc/systemd/system/droidloom-production.target"},
             "closed production target and boot selection")
        for name,key in (("GRUB-CANDIDATE.cfg","config"),("GRUB-GENERATOR","generator"),
                         ("GRUB-DEFAULTS.cfg","defaults")):
            need(read_pin(file_pin(bundle/name),16384)==grub[key],"source-owned original/candidate GRUB text")
        boot_inputs=normal_host_boot_inputs(file_pin(bundle/"host.deb"),file_pin(bundle/"host-manifest.json"))
        for name,body in boot_inputs.items():
            need(name in seen and read_pin(file_pin(bundle/name),65536)==body,
                 "candidate boot member differs from its normal host package")
        need(intent.get("native_init")==native_init_contract(boot_inputs["BOARD-INPUTS.lock.json"]),
             "same original board native-init contract")
    if intent.get("schema")=="droidloom-cold-transaction-candidate-v2":
        native=bound_native_inputs(bundle,intent)
        if "BOARD-INPUTS.lock.json" in seen:
            native_init_contract(read_pin(file_pin(bundle/"BOARD-INPUTS.lock.json"),65536),native)
        result["native_release_id"]=native["index"]["native_release_id"]
    return result


# Evidence consumers read the original protected producer outputs. No field in
# these observations can grant physical or private-account qualification.
QUALIFICATION_ROOT=Path("/var/lib/droidloom-qualification")
RUNTIME_INPUT_SCHEMA="droidloom-cold-owned-runtime-inputs-v1"
SELECTED_BASE="/var/lib/droidloom-public-apks/u1000"

def proof_path(path):
    path=safe_absolute(str(path))
    need(path.is_relative_to(QUALIFICATION_ROOT) or path.is_relative_to(STORE),
         "runtime evidence must remain in the protected qualification or maintenance tree")
    return path

def evidence_pin(pin,maximum):
    exact(pin,("path","bytes","sha256"),"runtime evidence pin")
    safe_absolute(pin["path"]);digest(pin["sha256"])
    need(type(maximum) is int and 0<maximum<=128*1024**3 and
         type(pin["bytes"]) is int and 0<=pin["bytes"]<=maximum,"bounded runtime evidence file")
    return pin

def evidence_file(pin,maximum,*,contents=False,protected=True):
    pin=evidence_pin(pin,maximum)
    path=proof_path(pin["path"]) if protected else safe_absolute(pin["path"])
    with held(path,root=protected,maximum=maximum) as (fd,before):
        need(before.st_size==pin["bytes"] and not (stat.S_IMODE(before.st_mode)&0o022),
             "runtime evidence metadata")
        checksum=hashlib.sha256();pieces=[];size=0;deadline=time.monotonic()+900
        while size<before.st_size:
            need(time.monotonic()<deadline,"bounded original runtime evidence read")
            part=os.read(fd,min(1024*1024,before.st_size-size))
            need(part,"truncated runtime evidence")
            size+=len(part);checksum.update(part)
            if contents:pieces.append(part)
        need(not os.read(fd,1),"trailing runtime evidence bytes")
        need(checksum.hexdigest()==pin["sha256"],"original runtime evidence bytes")
        body=b"".join(pieces) if contents else None
        need(f9(os.fstat(fd))==f9(before)==f9(os.stat(path,follow_symlinks=False)),
             "runtime evidence changed during read")
        identity={"dev":before.st_dev,"ino":before.st_ino,"mode":before.st_mode,
                  "uid":before.st_uid,"gid":before.st_gid,"nlink":before.st_nlink,"size":before.st_size,
                  "mtime_sec":before.st_mtime_ns//1000000000,"mtime_nsec":before.st_mtime_ns%1000000000,
                  "ctime_sec":before.st_ctime_ns//1000000000,"ctime_nsec":before.st_ctime_ns%1000000000}
    return body,identity

def proof_file(pin,maximum,*,contents=False):
    return evidence_file(pin,maximum,contents=contents,protected=True)

def proof_json(pin,maximum):
    body,identity=proof_file(pin,maximum,contents=True)
    return json_bytes(body),identity

def public_source(pin,role):
    # The original controller pins public source bytes and F9, without requiring
    # the build user's source checkout to be owned by root. Results remain root
    # protected. These sources are read as data; no code here executes them.
    names={"execution":("EXECUTION.json","EXECUTION-CANDIDATE.json"),
           "guest_runner":("guest_runner.py",),"guest_transfer":("guest_transfer.py",)}
    need(role in names,"fixed selected39 source role")
    path=safe_absolute(pin["path"])
    need(path.name in names[role] and any(path.is_relative_to(p) for p in
         (QUALIFICATION_ROOT,STORE,Path("/home/alex/work"),Path("/home/qq/work"))),
         "fixed public selected39 source location")
    expected={"guest_runner":(26373,"6e9bb3a0c5e3e13af8f66a5dda10c29e3666e30fb63c6b59b9012e7a42f110ce"),
              "guest_transfer":(7797,"be652417b6d12755a4459c5de89767d589c2d40b5b1aec564632683e3d32401a")}
    if role in expected:
        need((pin["bytes"],pin["sha256"])==expected[role],"reviewed original selected39 source bytes")
    raw,identity=evidence_file(pin,256*1024,contents=True,protected=False)
    return (json_bytes(raw) if role=="execution" else None),identity

def same_bytes(a,b):
    return isinstance(a,dict) and isinstance(b,dict) and type(a.get("bytes")) is int and type(b.get("bytes")) is int and (
        a.get("bytes"),a.get("sha256"))==(b.get("bytes"),b.get("sha256"))

def recorded_source(value,maximum):
    exact(value,("pin","body"),"recorded complete native source")
    pin=value["pin"];exact(pin,("path","bytes","sha256","device","inode","mode","uid","gid"),"original source evidence pin")
    need(isinstance(value["body"],str),"original recorded source body")
    raw=value["body"].encode("utf-8")
    need(0<len(raw)<=maximum and len(raw)==pin["bytes"] and
         hashlib.sha256(raw).hexdigest()==digest(pin["sha256"]) and
         all(type(pin[k]) is int for k in ("bytes","device","inode","mode","uid","gid")) and
         pin["device"]>0 and pin["inode"]>0 and pin["uid"]==pin["gid"]==0 and pin["mode"]==0o400,
         "complete native source original bytes and protected origin")
    return json_bytes(raw)

def real_epoch(value,boot_id):
    exact(value,("boot_id","cell_host_pid","framework_host_pid","framework_start_ticks"),"actual runtime epoch")
    need(isinstance(boot_id,str) and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",boot_id) is not None
         and value["boot_id"]==boot_id and
         all(type(value[k]) is int and 0<value[k]<=2**31-1 for k in ("cell_host_pid","framework_host_pid")) and
         type(value["framework_start_ticks"]) is int and 0<value["framework_start_ticks"]<2**64,
         "original live runtime epoch")
    return value

def actual_launch(value):
    need(isinstance(value,str) and 0<len(value)<=256,"original Launch text")
    parts=value.split();need(len(parts)==4,"exact Launch fields")
    result={}
    for part in parts:
        need(part.count("=")==1,"Launch field syntax")
        key,number=part.split("=")
        need(key not in result and re.fullmatch(r"[0-9]+",number) is not None,"unique numeric Launch field")
        result[key]=int(number)
    exact(result,("object","composer_display","android_display","task"),"original owned task")
    need(0<result["object"]<2**64 and 0<result["composer_display"]<2**64 and
         result["android_display"]==0 and 0<result["task"]<=2**31-1,"original task/display bounds")
    return result



def owned_runtime_observations(materials,inputs_pin):
    """Bind real owned-run and selected39 outputs without granting acceptance."""
    from cold_apply import selected39_observations
    inputs,_=proof_json(inputs_pin,128*1024)
    exact(inputs,("schema","public_release_id","deployment_id","native_release_id","normal_build",
                  "fixture","ended","collected","backend_config","backend_result"),"owned runtime inputs")
    need(inputs["schema"]==RUNTIME_INPUT_SCHEMA and all(inputs[k]==materials[k]
         for k in ("public_release_id","deployment_id","native_release_id")),
         "owned observations use this actual public/native candidate")
    build,_=proof_json(inputs["normal_build"],4*1024*1024)
    need(build.get("schema") in ("p4-r126-normal-host-source-bound-release-v9",
         "p4-r126-normal-host-source-bound-release-v10",
         "p4-r126-normal-host-source-bound-release-v11") and
         build.get("success") is True and build.get("source_clean") is True and
         build.get("source_clean_after") is True and
         build.get("source_commit")==materials["source_commit"] and
         build.get("source_tree")==materials["source_tree"] and
         build.get("runtime_qualified") is False and build.get("production_activated") is False,
         "same completed normal host and fixture source")
    steps=build["steps"]
    need(len(steps)==3 and {x["name"] for x in steps}=={"bootstrap","host-stage","fixture"} and
         all(type(x["exit_code"]) is int and x["exit_code"]==0 for x in steps),
         "all normal build stages actually completed")
    fixture=build["fixture_binary"]
    need(fixture["foreign_project_paths"]==[] and same_bytes(fixture,inputs["fixture"]),
         "source-bound normal fixture executable")
    proof_file(inputs["fixture"],32*1024*1024)
    release=build["release"]
    need(release["commit"]==materials["source_commit"] and release["tree"]==materials["source_tree"] and
         (release["manifest"]["size"],release["manifest"]["sha256"])==
         (materials["host_manifest"]["bytes"],materials["host_manifest"]["sha256"]),
         "normal source/build manifest is the cold package manifest")
    ended,ended_id=proof_json(inputs["ended"],256*1024)
    collected,collected_id=proof_json(inputs["collected"],16*1024*1024)
    need(ended.get("schema")=="droidloom.full-ubuntu-run-ended.v1" and
         collected.get("schema")=="droidloom.full-ubuntu-boot-collected.v1",
         "actual owned runtime/collection producer schemas")
    run=proof_path(ended["run_directory"])
    need(Path(inputs["ended"]["path"])==run/"RUN-ENDED.json" and
         run.parent.name=="boot" and run.parent.parent.parent==QUALIFICATION_ROOT,
         "original fixed qualification run directory")
    prepared_pin=ended["prepared"]
    need(Path(prepared_pin["path"])==run.parent/"BOOT-PREPARED.json" and
         collected["ended"]==inputs["ended"] and collected["prepared"]==prepared_pin,
         "one prepared/run-ended/collected chain")
    prepared,_=proof_json(prepared_pin,2*1024*1024)
    need(prepared.get("schema")=="droidloom.full-ubuntu-boot-prepared.v1" and
         prepared.get("work_directory")==str(run.parent.parent) and
         prepared.get("boot_directory")==str(run.parent) and
         prepared.get("calibration_requested") is False and
         prepared.get("target_kernel_release")==materials["kernel_release"],
         "full normal boot, not calibration or a different shared kernel")
    for record in (prepared,ended,collected):
        need(record.get("guest_qualified") is False and record.get("production_ready") is False,
             "original observational receipt cannot assert qualification")
    need(type(ended.get("exit_code")) is int and ended["exit_code"]==0 and ended.get("signal") is None and ended.get("forced_stop") is False
         and ended.get("source_image_preserved") is True,
         "original QEMU retired normally without a forced stop")
    need(collected.get("status")=="collected" and collected.get("errors")==[] and
         collected.get("source_image_preserved") is True,"actual complete collection")
    collection=proof_path(collected["collection_directory"])
    need(Path(inputs["collected"]["path"])==collection/"COLLECTED.json" and
         collection.parent==run,"original ended-run collection directory")
    host=prepared["host_release"]
    need(host["source_commit"]==materials["source_commit"] and host["source_tree"]==materials["source_tree"] and
         same_bytes(host["normal_host_manifest"],materials["host_manifest"]) and
         (host["normal_host_archive"]["bytes"],host["normal_host_archive"]["sha256"])==
         (release["archive"]["size"],release["archive"]["sha256"]) and
         host.get("full_file_readback") is True,"normal host package bytes were prepared")
    android=prepared["android_release"]
    need(android["cohort"]["sha256"]==materials["android_cohort"] and
         android["runtime"]["sha256"]==materials["android_runtime"] and
         android["device_manifest"]["sha256"]==materials["board_manifest"] and
         android["selected"]["base_cohort_sha256"]==materials["android_cohort"] and
         android["selected"]["runtime_manifest_sha256"]==materials["android_runtime"] and
         android.get("calibration_requested") is False and android.get("working_data_supplied") is False,
         "same actual normal fresh Android/runtime/board cohort")
    need(prepared.get("native_source_kind")=="complete-installed","complete normally installed native root required")
    native=prepared["complete_native_source"]
    need(native.get("complete_package_database") is True and
         native.get("normal_package_transaction_verified") is True and
         native.get("whole_payload_verified") is True and native.get("single_elf_overlays_applied") is False,
         "complete native preparation, not individual ELF overlays")
    source=recorded_source(native["source"],128*1024)
    need(source.get("schema")=="droidloom.complete-ubuntu-native-source.v1" and
         source.get("stage")=="installed" and source.get("fresh_generated_root") is True and
         source.get("private_accounts_copied") is False and source.get("configured") is True and
         same_bytes(source.get("native_release"),materials["native_manifest"]),
         "same fifteen-package normal installed source")
    native_manifest,_=proof_json(native["fixture_manifest"],64*1024*1024)
    need(native_manifest.get("source")==native["source"],"same actual captured complete native source")
    # Reopen original files, not path strings or caller success booleans.
    need(ended["preserved_source_image"]==prepared["root_image"]==collected["preserved_source_image"] and
         Path(ended["working_disk"]["path"])==run/"working.ext4" and
         Path(ended["serial"]["path"])==run/"serial.log","original disk/serial/source file roles")
    _,source_id=proof_file(prepared["root_image"],128*1024**3)
    _,working_id=proof_file(ended["working_disk"],128*1024**3)
    proof_file(ended["serial"],256*1024*1024)
    need(source_id==ended["source_identity"] and
         (source_id["dev"],source_id["ino"])!=(working_id["dev"],working_id["ino"]) and
         source_id["size"]==working_id["size"],"preserved source and independent actual working clone")
    need(prepared["kernel"]["sha256"]==materials["kernel_sha256"],"same shared kernel executable")
    proof_file(prepared["kernel"],64*1024*1024)
    proof_file(prepared["initrd"],1024*1024*1024)
    running,_=proof_json(file_pin(run/"RUNNING.json"),256*1024)
    admitted,_=proof_json(file_pin(run/"QEMU-ADMITTED.json"),256*1024)
    launch=running["fixed_descriptor_launcher"]
    need(admitted.get("schema")=="droidloom.qemu-paused-launch-admitted.v1" and
         admitted.get("guest_cpus_started") is False and admitted["launcher"]==launch and
         launch.get("schema")=="droidloom.qemu-fixed-descriptor-launch.v1" and
         running["program"]==ended["qemu"]==launch["qemu_source"] and
         running["working_disk"]==str(run/"working.ext4") and running["private_qmp"]==str(run/"qmp.sock") and
         running["preserved_source_image"]==prepared["root_image"] and
         running["source_identity"]==ended["source_identity"],"one original owned QEMU launch")
    need(launch["sandbox"]=="on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny" and
         launch["uid"]==launch["gid"]==65534 and launch["supplementary_groups"]==[] and
         launch["no_new_privileges"] is True and launch["original_prepared_disk_inherited"] is False and
         admitted["qmp"]["return"]["running"] is False and
         admitted["qmp"]["return"]["status"] in ("paused","prelaunch"),"unchanged complete pre-vCPU sandbox")
    need(same_bytes(launch["kernel_readonly"],prepared["kernel"]) and
         same_bytes(launch["initrd_readonly"],prepared["initrd"]),"same actual held boot descriptors")
    for private,original in (("private_qemu","qemu_source"),("private_privilege_tool","privilege_tool")):
        need(same_bytes(launch[private],launch[original]),"original tool bytes in private executable")
        _,identity=proof_file(launch[private],64*1024*1024)
        need(identity["mode"]&0o7777==0o511,"original unreadable execution copy")
        if private=="private_qemu":qemu_id=identity
    need(qemu_id==launch["private_qemu_identity"],"original private QEMU inode unchanged")
    process=admitted["actual_process"];status=process["process_status"]
    need(type(running["pid"]) is int and running["pid"]>1 and status["Pid"]==str(running["pid"]) and
         process["live_executable_device"]==qemu_id["dev"] and process["live_executable_inode"]==qemu_id["ino"] and
         process["proc_status_owner_for_non_dumpable_exec"]==[0,0],"original live QEMU identity and dumpability")
    need(all(status[k].split()==["65534"]*4 for k in ("Uid","Gid")) and status["Groups"]=="" and
         all(int(status[k],16)==0 for k in ("CapEff","CapPrm","CapInh","CapAmb")) and
         status["NoNewPrivs"]=="1" and status["Seccomp"]=="2","actual credentials/capabilities/NNP/seccomp admission")
    detail=collected["details"]
    need(detail.get("journal_integrity_verified") is True and detail.get("ordinary_guest_shutdown") is True and
         detail.get("ended_working_disk_preserved") is True,"actual original journal collection integrity")
    collection_input,_=proof_json(file_pin(collection/"COLLECT-INPUTS.json"),128*1024)
    need(collection_input.get("schema")=="droidloom.full-ubuntu-boot-collect-plan.v1" and
         collection_input.get("ended")==inputs["ended"] and
         collection_input.get("collection_name")==collection.name and
         collection_input.get("journalctl",{}).get("path")=="/usr/bin/journalctl",
         "original fixed collection plan and journal tool")
    journals=detail["journals"];need(isinstance(journals,list) and 1<=len(journals)<=128,"bounded original journal set")
    rows=[];bytes_total=0
    seen_journals=set()
    for index,journal in enumerate(journals):
        need(journal["journal"]["path"] not in seen_journals and
             Path(journal["journal"]["path"]).parent==collection,"original unique journal export")
        seen_journals.add(journal["journal"]["path"])
        proof_file(journal["journal"],256*1024*1024)
        for key,argument in (("integrity","--verify"),("json","--output=json")):
            command=journal[key]
            need(isinstance(command,dict) and command["tool"]==collection_input["journalctl"] and type(command["exit_code"]) is int and command["exit_code"]==0 and command["signal"] is None and
                 command["timed_out"] is False and command["output_limited"] is False and
                 command["child_reaped"] is True and command["tool_identity_preserved"] is True and
                 command["executed_held_descriptor"] is True and
                 argument in command["args"] and
                 "--file="+journal["journal"]["path"] in command["args"],
                 "actual held-descriptor journal tool completion")
            for stream in ("stdout","stderr"):
                need(Path(command[stream]["path"]).parent==collection,"original journal tool streams")
                maximum=64*1024*1024 if key=="json" and stream=="stdout" else 8*1024*1024
                raw,_=proof_file(command[stream],maximum,contents=True)
                bytes_total+=len(raw);need(bytes_total<=512*1024*1024,"aggregate journal evidence bound")
                if key=="json" and stream=="stdout":
                    for line in raw.splitlines():
                        if line:rows.append(json_bytes(line))
                    need(len(rows)<=200000,"original producer journal row bound")
    need(rows and len(rows)==detail["journal_entries"],"actual original journal rows")
    boot_ids=sorted({x["_BOOT_ID"] for x in rows if isinstance(x.get("_BOOT_ID"),str)})
    need(len(boot_ids)==1 and re.fullmatch(r"[0-9a-f]{32}",boot_ids[0]) and boot_ids==detail["boot_ids"],
         "one actual journal boot identity")
    boot_id="-".join((boot_ids[0][:8],boot_ids[0][8:12],boot_ids[0][12:16],boot_ids[0][16:20],boot_ids[0][20:]))
    failures=[x for x in rows if x.get("_PID")=="1" and x.get("JOB_RESULT") in ("failed","dependency","timeout")]
    denials=[x for x in rows if isinstance(x.get("MESSAGE"),str) and
             ("avc:" in x["MESSAGE"] or 'apparmor="DENIED"' in x["MESSAGE"])]
    errors=[x for x in rows if isinstance(x.get("PRIORITY"),str) and
            re.fullmatch(r"\+?[0-9]+",x["PRIORITY"]) is not None and 0<=int(x["PRIORITY"])<=3]
    need(failures==detail["systemd_failed_jobs"] and denials==detail["mac_denials"] and
         errors==detail["priority_error_records"],"full original failed-job/MAC/error accounting")
    backend=selected39_observations(materials,inputs["backend_config"],inputs["backend_result"],boot_id)
    machine_ids={x["_MACHINE_ID"] for x in rows if isinstance(x.get("_MACHINE_ID"),str)}
    need(machine_ids=={backend["machine_id"]},"backend and original journal belong to the same actual guest")
    config,_=proof_json(inputs["backend_config"],256*1024)
    need(config["known_hosts"]==running["known_hosts"] and
         config["ssh_key"]==running["fresh_client_key"] and
         type(config["ssh_port"]) is int and 50000<=config["ssh_port"]<=59999 and
         any(x==f"user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:{config['ssh_port']}-:22"
             for x in running["args"]),
         "same original fresh-SSH guest instance")
    proof_file(config["known_hosts"],64*1024)
    blockers=[]
    if materials["host_missing_required_maintenance"]:blockers.append("normal_host_missing_fixed_maintenance_payload")
    if failures:blockers.append("actual_systemd_failed_jobs")
    if denials:blockers.append("actual_mac_denials")
    if errors:blockers.append("actual_high_priority_journal_errors")
    if backend["command_failures"]:blockers.append("actual_backend_command_failures")
    blockers.extend(("actual_live_enforcing_mac_and_maintenance_return",
                     "actual_frame_and_application_input_acceptance",
                     "actual_business_and_latest_delivery_acceptance",
                     "original_device_private_account_continuity",
                     "original_ubuntu_boot_publication_and_return"))
    return {"schema":"droidloom-cold-owned-runtime-observation-v1",
            **{k:materials[k] for k in ("public_release_id","deployment_id","native_release_id","source_commit","source_tree")},
            "inputs":inputs_pin,"normal_fixture":inputs["fixture"],"prepared":prepared_pin,
            "ended":inputs["ended"],"collected":inputs["collected"],"boot_id":boot_id,
            "original_source_image":prepared["root_image"],"original_working_disk":ended["working_disk"],
            "kernel_sha256":materials["kernel_sha256"],"android_cohort":materials["android_cohort"],
            "android_runtime":materials["android_runtime"],"normal_native_manifest":materials["native_manifest"],
            "journal_rows":len(rows),"failed_jobs":len(failures),"mac_denials":len(denials),
            "priority_errors":len(errors),"selected39":backend,"activation_blockers":blockers,
            "runtime_qualified":False,"private_accounts_qualified":False,"physical_activation":False}


def activate(bundle,release_id):
    verify(bundle,release_id)
    # No invented boolean, caller assertion, or public-fresh-VM result grants
    # physical-data qualification. This remains a closed interface until the
    # actual owned-runtime/private-working-copy verifier is integrated.
    raise Rejected("activation unavailable: no admitted owned-runtime and physical private-working-copy acceptance verifier")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    q=sub.add_parser("preflight");q.add_argument("--output",required=True,type=Path)
    q=sub.add_parser("prepare");q.add_argument("--plan",required=True,type=Path);q.add_argument("--output",required=True,type=Path)
    for name in ("verify","activate"):
        q=sub.add_parser(name);q.add_argument("--bundle",required=True,type=Path);q.add_argument("--release",required=True)
    a=p.parse_args()
    if a.command=="preflight":result=preflight(a.output)
    elif a.command=="prepare":result=prepare(a.plan,a.output)
    elif a.command=="verify":result=verify(a.bundle,a.release)
    else:result=activate(a.bundle,a.release)
    sys.stdout.buffer.write(canonical(result));sys.stdout.buffer.flush()

if __name__=="__main__":
    try:main()
    except (Rejected,OSError,ValueError,KeyError,tarfile.TarError) as e:
        print("droidloom-cold-transaction: "+str(e),file=sys.stderr);sys.exit(1)
