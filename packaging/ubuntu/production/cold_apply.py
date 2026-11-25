#!/usr/bin/python3
"""Original-Ubuntu public package transaction and conservative rollback.

No production service, private image, account, SSH file, or boot selection is a
payload. The public apply dispatcher remains behind the real qualification
binding; no boolean or receipt schema is accepted as a substitute.
"""
import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import stat
import subprocess
import signal
import sys
import tarfile
import tempfile
import time
from release import (
    Rejected, STORE, HOST_ACL_MEMBER, need, exact, digest, canonical, f9,
    safe_relative, safe_host_relative, safe_absolute, held, hash_fd, read_pin,
    json_bytes, read_json_file, file_pin, new_file, copy_pin, bounded_process,
    host_manifest, TOOLS,
)
from cold_transaction import (
    ROOT_UUID, ORIGINAL_KERNEL, SOURCE_PATHS, PRESERVE_METADATA, NAMES,
    mount_identity, package_control, verify,
)
from cold_publish import KERNEL, KERNEL_SHA, COHORT, RUNTIME, BOARD, BANK

MAX_FILES=7200
MAX_BYTES=6*1024**3
SYSTEM_DPKG="/usr/bin/dpkg"
PUBLIC_ORDER=("kernel","android","host")

def public_relative(relative):
    # Only the already-reviewed @ template and its own fixed ancestors.
    allowed={HOST_ACL_MEMBER}
    pieces=HOST_ACL_MEMBER.split("/")
    allowed.update("/".join(pieces[:n]) for n in range(1,len(pieces)))
    if relative in allowed:return relative
    return safe_relative(relative)

def absolute_under(root,relative):
    public_relative(relative)
    return root/relative

def ensure_private_state(root):
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        device=os.fstat(fd).st_dev
        for part in ("var","lib","droidloom-maintenance","transactions"):
            try:os.mkdir(part,0o700,dir_fd=fd)
            except FileExistsError:pass
            n=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=n;s=os.fstat(fd)
            need(s.st_uid==s.st_gid==0 and s.st_dev==device and not(s.st_mode&0o022),"private state parent identity")
        return root/"var/lib/droidloom-maintenance/transactions"
    finally:os.close(fd)

def bounded_xattrs(fd):
    names=os.listxattr(fd);need(len(names)<=64,"original public xattr count")
    result={};total=0
    for name in names:
        need(isinstance(name,str) and 0<len(name)<=255 and "\0" not in name,"xattr name")
        raw=os.getxattr(fd,name);total+=len(raw)
        need(len(raw)<=65536 and total<=1024*1024,"original public xattr bound")
        result[name]=base64.b64encode(raw).decode("ascii")
    return result

def restore_xattrs(fd,values):
    need(isinstance(values,dict) and len(values)<=64,"saved public xattr count")
    decoded={};total=0
    for name,value in values.items():
        need(isinstance(name,str) and 0<len(name)<=255 and "\0" not in name,"saved xattr name")
        raw=base64.b64decode(value,validate=True);total+=len(raw)
        need(len(raw)<=65536 and total<=1024*1024,"saved xattr bytes")
        decoded[name]=raw
    for name in os.listxattr(fd):
        if name not in decoded:os.removexattr(fd,name)
    for name,raw in decoded.items():os.setxattr(fd,name,raw)

NATIVE_RELEASE_ID="27aa919057651931545bbf16edca2375decb23f3c5ee7c6e8b6c9ac95db55d51"

def cold_systemctl_pins(payloads):
    # The caller supplies only the output of the complete native release
    # verifier, which checks both original archives and all normal source proof.
    package=payloads["systemd"]
    allowed=set()
    for kind in ("old","new"):
        row=package[kind]["payload"]["usr/bin/systemctl"]
        need(row["path"]=="usr/bin/systemctl" and row["type"]=="0" and
             row["uid"]==row["gid"]==0 and row["mode"]==0o755,"normal systemctl inode metadata")
        allowed.add((row["bytes"],row["sha256"]))
    new=package["new"]["payload"]
    for name in ("systemctl","journalctl"):
        row=new["usr/bin/"+name]
        need((TOOLS[name][0],TOOLS[name][1],TOOLS[name][2])==
             ("/"+row["path"],row["bytes"],row["sha256"]),"production tools match the complete normal native source")
    need(len(allowed)==2,"exact original/new cold systemctl set")
    return allowed

@contextlib.contextmanager
def held_cold_systemctl():
    from native_release import verify_bundle
    bundle=STORE/"native-releases"/NATIVE_RELEASE_ID
    index,_,packages,payloads=verify_bundle(bundle,NATIVE_RELEASE_ID,True)
    need(index["schema"]=="droidloom-normal-native-package-release-v2" and len(packages)==15,
         "cold tools require the full normal native15 source closure")
    allowed=cold_systemctl_pins(payloads)
    with held("/usr/bin/systemctl",root=True,modes={0o755},maximum=16*1024*1024) as (fd,st):
        need((st.st_size,hash_fd(fd)) in allowed,"unreviewed original/new cold systemctl")
        yield fd

def original_cold_authority():
    need(os.getuid()==os.geteuid()==0,"cold public transaction requires original root")
    need(os.uname().release==ORIGINAL_KERNEL,"only original Ubuntu maintenance kernel")
    need(Path("/proc/self/uid_map").read_text().split()==["0","0","4294967295"],"initial user namespace")
    root=os.stat("/");pid1=os.stat("/proc/1/root")
    need((root.st_dev,root.st_ino)==(pid1.st_dev,pid1.st_ino),"original PID1 filesystem")
    a=mount_identity("/");b=mount_identity("/boot")
    need(a["source"]==b["source"] and a["uuid"]==ROOT_UUID,"fixed original root and boot")
    # The public transaction is cold. It does not stop a session to obtain
    # permission; the operator must first reach the admitted maintenance boot.
    with held_cold_systemctl() as command:
        for unit in ("graphical.target","gdm.service","droidloom-production.service",
                     "droidloom-instance-launcher.service","droidloom-instance-factory.service"):
            r=bounded_process([f"/proc/self/fd/{command}","show","--value","--property=ActiveState",unit],
                              seconds=5,maximum=65536,pass_fds=(command,))
            need(r["exit"]==0 and r["stdout"].strip() in (b"inactive",b"failed"),
                 "live graphical/Android owner blocks cold transaction")
    return {"boot_id":Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "root_identity":[root.st_dev,root.st_ino],"kernel":ORIGINAL_KERNEL}

def actual_acceptance_binding(release_id):
    digest(release_id)
    from cold_transaction import owned_runtime_observations
    materials=candidate_material_binding(release_id)
    path=STORE/"observations"/materials["deployment_id"]/"RUNTIME-INPUTS.json"
    try:pin=file_pin(path)
    except FileNotFoundError:
        raise Rejected("missing protected original owned-runtime inputs for this deployment") from None
    observed=owned_runtime_observations(materials,pin)
    # The existing producers deliberately do not assert business, application
    # input, latest delivery or original-account continuity. Their false fields
    # are never converted into permission to install or activate a release.
    need(not observed["activation_blockers"],"unclosed actual acceptance: "+
         ", ".join(observed["activation_blockers"]))
    raise Rejected("no source-owned original-device account/boot-return validator has admitted this deployment")

def load_inputs(bundle,release_id):
    verify(bundle,release_id)
    release,_=read_json_file(bundle/"RELEASE.json",8*1024*1024,True,{0o444})
    for row in release["files"]:
        with held(bundle/row["path"],root=True,modes={0o444}) as (fd,st):
            need(st.st_size==row["bytes"] and hash_fd(fd)==row["sha256"],"protected release member changed")
    intent,_=read_json_file(bundle/"COLD-INTENT.json",2*1024*1024,True,{0o444})
    need(intent["root_uuid"]==ROOT_UUID and intent["original_kernel"]==ORIGINAL_KERNEL,
         "cold target identity")
    entries={};packages={};controls={};directories={};audit_scopes={}
    for role in PUBLIC_ORDER:
        role_files={};role_directories={}
        result,_=read_json_file(bundle/(role+"-result.json"),2*1024*1024,True,{0o444})
        need(result["normal_build_exit_code"]==0 and result["physical_install"] is False and
             result["runtime_qualified"] is False,"completed normal candidate component")
        package=file_pin(bundle/(role+".deb"))
        need((package["bytes"],package["sha256"])==(result["package"]["bytes"],result["package"]["sha256"]),
             "normal package result binding")
        controls[role]=package_control(package,NAMES[role]);packages[role]=package
        if role=="host":
            mpin=file_pin(bundle/"host-manifest.json")
            need((mpin["bytes"],mpin["sha256"])==(result["host_manifest"]["bytes"],result["host_manifest"]["sha256"]),
                 "host inventory binding")
            manifest,_=host_manifest(mpin)
            need(manifest["commit"]==release["source_commit"] and manifest["tree"]==release["source_tree"],
                 "normal host source")
            rows=[{"path":r["path"],"bytes":r["size"],"sha256":r["sha256"],"mode":r["mode"]}
                  for r in manifest["files"]]
            for row in manifest["directories"]:
                directories[row["path"]]=row["mode"];role_directories[row["path"]]=row["mode"]
        else:
            ip=file_pin(bundle/(role+"-inventory.json"))
            need((ip["bytes"],ip["sha256"])==(result["inventory"]["bytes"],result["inventory"]["sha256"]),
                 "normal public inventory binding")
            rows=json_bytes(read_pin(ip,4*1024*1024,True))
        need(isinstance(rows,list) and 0<len(rows)<=7000,"component inventory bound")
        for row in rows:
            exact(row,("path","bytes","sha256","mode"),"normal public leaf")
            rel=safe_host_relative(row["path"])
            need(rel not in entries and type(row["bytes"]) is int and 0<=row["bytes"]<=3*1024**3,
                 "normal public leaf identity/size")
            digest(row["sha256"]);need(row["mode"] in (0o444,0o555,0o644,0o755),"normal public leaf mode")
            if role=="host":
                need(rel.startswith(("usr/","etc/selinux/")) or rel==HOST_ACL_MEMBER,"host public scope")
            elif role=="kernel":
                need(rel=="boot/droidloom/kernels/"+KERNEL_SHA+"/vmlinuz" or
                     rel.startswith("usr/lib/modules/"+KERNEL+"/") or
                     rel.startswith("usr/lib/droidloom/kernels/"+KERNEL+"/"),"exact shared kernel cohort")
            else:
                need(rel in ("etc/droidloom/cohorts/"+COHORT+".json",
                     "etc/droidloom/runtime-cohorts/"+RUNTIME+".json",
                     "etc/droidloom/board-devices/"+BOARD+".json") or
                     rel.startswith("var/lib/droidloom/cohorts/"+COHORT+"/") or
                     rel.startswith("var/lib/droidloom/runtime-cohorts/"+RUNTIME+"/"),
                     "exact public Android cohort; no userdata")
            entries[rel]=dict(row,role=role);role_files[rel]=dict(row)
            parts=rel.split("/")
            for count in range(1,len(parts)):
                parent="/".join(parts[:count])
                directories.setdefault(parent,0o755);role_directories.setdefault(parent,0o755)
        for rel in list(role_directories):
            parts=rel.split("/")
            for count in range(1,len(parts)):
                parent="/".join(parts[:count])
                directories.setdefault(parent,0o755);role_directories.setdefault(parent,0o755)
        audit_scopes[role]={"files":role_files,"directories":role_directories}
    need(0<len(entries)<=MAX_FILES and sum(r["bytes"] for r in entries.values())<=MAX_BYTES,
         "whole normal public transaction bound")
    return intent,entries,directories,packages,controls,audit_scopes


def package_payload(pin,scope,workdir):
    """Read the real Debian data stream before dpkg may mutate the root.

    The uncompressed tar is an anonymous, mode-0600 temporary file under the
    protected transaction. Its byte/deadline bounds are independent of the
    caller result JSON. No archive member is extracted or executed here.
    """
    expected=scope["files"];directories=scope["directories"]
    limit=MAX_BYTES+MAX_FILES*4096+4*1024*1024
    started=time.monotonic()
    with held(pin["path"],root=True,modes={0o444}) as (source,original), \
         tempfile.TemporaryFile(dir=workdir) as data, \
         tempfile.TemporaryFile(dir=workdir) as errors:
        need(original.st_size==pin["bytes"] and hash_fd(source)==pin["sha256"],
             "original public Debian bytes before payload audit")
        os.lseek(source,0,os.SEEK_SET)
        child=subprocess.Popen(["/usr/bin/dpkg-deb","--fsys-tarfile",f"/proc/self/fd/{source}"],
              stdin=subprocess.DEVNULL,stdout=data,stderr=errors,close_fds=True,
              pass_fds=(source,),start_new_session=True,
              env={"PATH":"/usr/bin:/bin","LC_ALL":"C"})
        deadline=time.monotonic()+300
        try:
            while child.poll() is None:
                need(time.monotonic()<deadline,"normal Debian payload reader deadline")
                need(os.fstat(data.fileno()).st_size<=limit and
                     os.fstat(errors.fileno()).st_size<=1024*1024,
                     "normal Debian payload reader output bound")
                time.sleep(0.05)
            need(child.wait()==0,"normal Debian data reader failed")
        finally:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
        length=os.fstat(data.fileno()).st_size
        need(1024<=length<=limit and os.fstat(errors.fileno()).st_size<=1024*1024,
             "complete bounded Debian data stream")
        data.seek(0);seen=set();seen_dirs=set();total=0;count=0
        with tarfile.open(fileobj=data,mode="r:") as archive:
            for entry in archive:
                count+=1;need(count<=2*MAX_FILES+64,"normal Debian member count")
                rel=entry.name[2:] if entry.name.startswith("./") else entry.name
                if entry.isdir():rel=rel.rstrip("/")
                if rel==".":rel=""
                need(entry.uid==entry.gid==0 and not entry.pax_headers and
                     not entry.issparse() and not entry.linkname,
                     "Debian payload has unexpected ownership or extension")
                if entry.isdir():
                    need(rel not in seen_dirs and entry.size==0 and
                         ((rel=="" and entry.mode==0o755) or
                          (rel in directories and entry.mode==directories[rel])),
                         "Debian directory differs from the normal inventory")
                    seen_dirs.add(rel);continue
                public_relative(rel)
                need(entry.isfile() and rel in expected and rel not in seen,
                     "unlisted, duplicate or nonregular Debian payload")
                row=expected[rel]
                need(entry.size==row["bytes"] and entry.mode==row["mode"],
                     "Debian public payload metadata differs")
                total+=entry.size;need(total<=MAX_BYTES,"Debian public payload bytes")
                body=archive.extractfile(entry);need(body is not None,"Debian body unavailable")
                checksum=hashlib.sha256();read=0
                while True:
                    block=body.read(1024*1024)
                    if not block:break
                    read+=len(block);need(read<=entry.size,"Debian body grew")
                    checksum.update(block)
                need(read==entry.size and checksum.hexdigest()==row["sha256"],
                     "Debian body differs from the original normal inventory")
                seen.add(rel)
            end=archive.offset
        need(seen==set(expected) and seen_dirs==set(directories)|{""},
             "Debian payload omitted normal files or directories")
        data.seek(end)
        while True:
            tail=data.read(1024*1024)
            if not tail:break
            need(not any(tail),"nonzero data after normal Debian archive terminator")
        need(f9(os.fstat(source))==f9(original),"Debian package changed during payload audit")
        return {"package_sha256":pin["sha256"],"files":len(seen),
                "directories":len(seen_dirs)-1,"body_bytes":total,
                "data_stream_bytes":length,"elapsed_seconds":time.monotonic()-started}


def candidate_material_binding(release_id,*,state=STORE):
    """Read actual public/native candidates from one protected material store.

    The optional state path is for isolated engine verification; no command-line
    option can change the production store. This returns material identity only,
    never runtime, private-account, or installation authority.
    """
    from native_release import verify_bundle,MANIFEST_NAME
    from cold_transaction import bound_native_inputs
    digest(release_id);state=safe_absolute(str(state))
    need(os.getuid()==os.geteuid()==0,"protected cold material inspection requires root")
    s=state.lstat()
    need(stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0 and
         stat.S_IMODE(s.st_mode)==0o700,"protected cold material store")
    bundle=state/"releases"/release_id
    intent,entries,directories,packages,controls,scopes=load_inputs(bundle,release_id)
    need(intent.get("component_control")==controls,"actual normal public package controls")
    archive=bound_native_inputs(bundle,intent,root=True)
    native_id=archive["index"]["native_release_id"]
    need(native_id==NATIVE_RELEASE_ID,"reviewed complete normal native source cohort")
    native_bundle=state/"native-releases"/native_id
    index,_,native_packages,payloads=verify_bundle(native_bundle,native_id,True)
    manifest=file_pin(native_bundle/MANIFEST_NAME)
    declared=archive["index"]["manifest"]
    need((manifest["bytes"],manifest["sha256"])==(declared["bytes"],declared["sha256"])
         and index==archive["descriptor"],"imported native packages differ from the cold archive")
    need(len(native_packages)==15,"complete normal native fifteen-package closure")
    cold_systemctl_pins(payloads)
    # Results and inventories alone cannot assert Debian content. Reuse the
    # bounded normal data reader before linking any acceptance to these bytes.
    with tempfile.TemporaryDirectory(prefix=".material-read-",dir=state) as scratch:
        audited={role:package_payload(packages[role],scopes[role],scratch) for role in PUBLIC_ORDER}
    source=intent["component_identity"]["host"]
    return {"schema":"droidloom-cold-material-binding-v1","public_release_id":release_id,
            "deployment_id":intent["deployment_id"],"native_release_id":native_id,
            "native_manifest":manifest,"native_package_roles":index["package_roles"],
            "native_directory":str(native_bundle),"state_directory":str(state),
            "public_manifest":file_pin(bundle/"RELEASE.json"),
            "source_commit":source["source_commit"],"source_tree":source["source_tree"],
            "host_manifest":file_pin(bundle/"host-manifest.json"),
            "host_missing_required_maintenance":source["missing_required_maintenance"],
            "public_packages":packages,"public_controls":controls,"public_payloads":audited,
            "kernel_release":KERNEL,"kernel_sha256":KERNEL_SHA,
            "android_cohort":COHORT,"android_runtime":RUNTIME,"board_manifest":BOARD,
            "root_uuid":ROOT_UUID,"native_before_public":True,
            "runtime_qualified":False,"private_accounts_qualified":False,"physical_activation":False}


SELECTED_PACKAGE_NAMES=('com.Hyatt.hyt', 'com.MobileTicket', 'com.amazon.mShop.android.shopping', 'com.android.calendar', 'com.android.camera2', 'com.android.contacts', 'com.android.deskclock', 'com.android.dialer', 'com.android.documentsui', 'com.android.gallery3d', 'com.android.messaging', 'com.android.quicksearchbox', 'com.android.settings', 'com.bestbuy.android', 'com.ehi.national.mobile', 'com.google.android.gms', 'com.hertz.android.digital', 'com.hilton.android.hhonors', 'com.ihg.apps.android', 'com.jingdong.app.mall', 'com.lianjia.beike', 'com.marriott.mrt', 'com.rytong.airchina', 'com.rytong.ceair', 'com.sankuai.meituan.takeoutnew', 'com.sdu.didi.psnger', 'com.ss.android.ugc.aweme', 'com.szzc', 'com.taobao.taobao', 'com.tencent.mm', 'com.united.mobile.android', 'com.xunmeng.pinduoduo', 'com.zhubajie.client', 'com.zillow.android.streeteasy', 'ctrip.android.view', 'jp.co.ana.android.tabidachi', 'org.fcitx.fcitx5.android', 'org.mozilla.firefox', 'tv.danmaku.bili')

def selected39_observations(materials,config_pin,result_pin,boot_id):
    """Recheck the original controller exports; Launch is not a frame or account."""
    from collections import Counter
    from cold_transaction import (proof_json,proof_file,proof_path,same_bytes,real_epoch,
                                  actual_launch,public_source,SELECTED_BASE)
    config,_=proof_json(config_pin,256*1024)
    result,_=proof_json(result_pin,4*1024*1024)
    out=proof_path(result_pin["path"]).parent
    need(Path(config_pin["path"])==out/"CONFIG.json" and Path(result_pin["path"]).name=="RESULT.json",
         "original selected39 controller directory")
    need(config.get("schema")=="p4-selected39-controller-config-v1" and
         result.get("schema")=="p4-selected39-controller-result-v1" and
         config.get("source_commit")==result.get("source_commit")==materials["source_commit"] and
         same_bytes(config.get("normal_host_manifest"),materials["host_manifest"]),
         "selected39 and normal host use one source and manifest")
    need(type(config.get("budget_seconds")) is int and 0<config["budget_seconds"]<=2700 and
         isinstance(config.get("machine_id"),str) and re.fullmatch(r"[0-9a-f]{32}",config["machine_id"]) is not None and config["machine_id"]!="0"*32,
         "bounded original backend and actual guest machine identity")
    need(result.get("stage_complete") is True and result.get("applications_executed") is True and
         type(result.get("guest_exit")) is int and result["guest_exit"]==0 and result.get("guest_boot_id")==boot_id and
         result.get("original_userdata_transferred") is False and
         result.get("automatic_install_retry") is False and result.get("production_ready") is False,
         "real completed bounded selected39 attempt")
    plan,_=public_source(config["execution_plan"],"execution")
    public_source(config["guest_runner"],"guest_runner")
    public_source(config["guest_transfer"],"guest_transfer")
    need(plan.get("schema")=="p4-selected39-execution-v3" and
         plan.get("scope")=="fresh_isolated_vm_only" and plan.get("guest_stage")==SELECTED_BASE and
         plan.get("file_count")==65 and len(plan.get("rows",[]))==39,"original selected39 plan")
    rows={}
    for row in plan["rows"]:
        package=row["package"]
        need(isinstance(package,str) and re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+",package)
             and package not in rows and row["role"] in ("system","third_party") and
             type(row["version_code"]) is int and row["version_code"]>=0,"unique planned package/version")
        need(isinstance(row["files"],list) and 0<len(row["files"])<=32 and
             row["signers_sha256"] and len(set(row["signers_sha256"]))==len(row["signers_sha256"]),
             "planned APK and signing identity")
        for sha in row["signers_sha256"]:digest(sha)
        for item in row["files"]:
            need(type(item["bytes"]) is int and 4<=item["bytes"]<=2**31 and
                 item["name"]==digest(item["sha256"])+".apk","canonical original APK material")
        need(isinstance(row["components"],list) and row["components"] and
             all(isinstance(x,str) and x.startswith(package+"/") for x in row["components"]),
             "source-declared launch components")
        rows[package]=row
    need(tuple(sorted(rows))==SELECTED_PACKAGE_NAMES and
         Counter(row["role"] for row in rows.values())=={"system":10,"third_party":29} and
         sum(len(row["files"]) for row in rows.values())==65,"exact selected39 role/APK closure")
    imported,_=proof_json(config["import_receipt"],2*1024*1024)
    imported_rows={row["package"]:row for row in imported["packages"]}
    need(imported.get("schema")=="p4-selected39-public-apk-import-v1" and
         imported.get("file_count")==65 and imported.get("package_count")==39 and
         len(imported["packages"])==39 and set(imported_rows)==set(rows),"same protected public import")
    planned=[(x["bytes"],x["sha256"]) for r in rows.values() for x in r["files"]]
    need(Counter(planned)==Counter((x["bytes"],x["sha256"]) for x in imported["files"]),
         "selected39 plan matches all actual imported APK bytes")
    for package,row in rows.items():
        original=imported_rows[package]
        need(row["version_code"]==original["version_code"] and row["version_name"]==original["version_name"]
             and row["signers_sha256"]==original["signer_certificates_sha256"],
             "normal import's original package/version/signer identity")
    exports=result.get("exports");need(isinstance(exports,list) and 1<=len(exports)<=1000,"bounded actual guest export")
    blobs={};total=0
    for pin in exports:
        path=proof_path(pin["path"]);name=path.name
        need(path.parent==out/"guest-evidence" and name not in blobs and
             re.fullmatch(r"selected39-r3-[A-Za-z0-9_.-]+",name),"flat unique original evidence export")
        total+=pin["bytes"];need(total<=256*1024*1024,"total actual guest export bound")
        raw,_=proof_file(pin,8*1024*1024,contents=True);blobs[name]=(pin,raw)
    def guest_pin(pin,json_value=True):
        exact(pin,("path","bytes","sha256"),"original guest evidence pin")
        path=Path(pin["path"]);need(str(path.parent)==SELECTED_BASE and path.name in blobs,
                                  "fixed original guest evidence path")
        local,raw=blobs[path.name];need(same_bytes(pin,local),"same exported original guest bytes")
        return json_bytes(raw) if json_value else raw
    summary_name="selected39-r3-RESULT.json"
    need(summary_name in blobs,"actual guest result export")
    summary=json_bytes(blobs[summary_name][1])
    need(summary.get("schema")=="p4-selected39-backend-result-v3" and
         summary.get("guest_boot_id")==boot_id and summary.get("guest_clock")=="CLOCK_MONOTONIC" and
         summary.get("aborted") is None and summary.get("original_userdata_transferred") is False and
         summary.get("automatic_install_retry") is False,"same completed guest backend")
    # These are explicit limitations of this producer, not flags to promote.
    need(summary.get("all_business_qualified") is False and
         summary.get("all_latest_device_delivery_qualified") is False and
         summary.get("production_ready") is False,"backend result cannot assert business/latest qualification")
    epoch=real_epoch(summary["original_epoch"],boot_id)
    start=json_bytes(blobs["selected39-r3-run-start.json"][1])
    need(start.get("schema")=="p4-selected39-run-start-v1" and
         start.get("guest_boot_id")==boot_id and start.get("machine_id")==config["machine_id"] and
         start.get("plan_sha256")==config["execution_plan"]["sha256"] and
         start.get("automatic_retry") is False and start.get("original_userdata") is False,
         "guest backend original start and exact plan")
    commands=summary["commands"];need(isinstance(commands,list) and 1<=len(commands)<=512,"bounded original command list")
    records={};last_ns=0;failed=[]
    for number,command in enumerate(commands,1):
        exact(command,("argv","returncode","guest_clock","guest_monotonic_ns_start",
              "guest_monotonic_ns_end","stdout","stderr","problem"),"actual normal CLI command")
        prefix="selected39-r3-%04d"%number
        need(json_bytes(blobs[prefix+"-command.json"][1])==command,"original command record bytes")
        a,b=command["guest_monotonic_ns_start"],command["guest_monotonic_ns_end"]
        need(type(a) is type(b) is int and 0<a<=b and a>=last_ns and
             command["guest_clock"]=="CLOCK_MONOTONIC","ordered actual guest command clock")
        last_ns=b
        need(command["stdout"]["path"]==SELECTED_BASE+"/"+prefix+"-stdout.json" and
             command["stderr"]["path"]==SELECTED_BASE+"/"+prefix+"-stderr.txt","original sequence stream names")
        guest_pin(command["stdout"],False);guest_pin(command["stderr"],False)
        argv=command["argv"]
        need(isinstance(argv,list) and 1<=len(argv)<=40 and
             all(isinstance(x,str) and 0<len(x)<=4096 for x in argv) and
             argv[0] in ("/usr/bin/droidloomctl","/usr/bin/droidloom-applications"),
             "only original normal application CLI commands")
        need(type(command["returncode"]) is int and command["problem"] is None,
             "no abandoned or unretired normal CLI operation")
        if command["returncode"]!=0:failed.append(number)
        key=command["stdout"]["sha256"];records.setdefault(key,[]).append(command)
    def response(pin,argv):
        matches=[c for c in records.get(pin["sha256"],[]) if c["argv"]==argv and c["stdout"]==pin]
        need(len(matches)==1 and matches[0]["returncode"]==0,"one actual successful normal CLI response")
        value=guest_pin(pin)
        need(isinstance(value,dict) and value.get("ok") is True and value.get("state")=="running",
             "actual Running response, not command acknowledgement")
        return value,matches[0]
    def inspect(value,row):
        item=value.get("inspection")
        need(isinstance(item,dict) and item.get("package")==row["package"] and type(item.get("user")) is int and item["user"]==0 and
             type(item.get("uid")) is int and item["uid"]>=0 and
             type(item.get("version_code")) is int and item["version_code"]==row["version_code"],"actual installed package/user/version")
        need(real_epoch(item["epoch"],boot_id)==epoch and value.get("host_pid")==epoch["cell_host_pid"],
             "unchanged original framework/cell epoch")
        apks=item.get("apks");need(isinstance(apks,list) and len(apks)==len(row["files"]),"complete installed original APK set")
        need(Counter((x["bytes"],x["sha256"]) for x in apks)==
             Counter((x["bytes"],x["sha256"]) for x in row["files"]),"actual installed APK bytes")
        return item
    catalog,_=response(summary["catalog_response"],["/usr/bin/droidloomctl","--json","applications","--user","0"])
    applications=catalog.get("applications");need(isinstance(applications,list) and len(applications)<=10000,"bounded actual catalog")
    available={(x["package"],x["component"]) for x in applications}
    need(len(available)==len(applications),"unique catalog entries")
    results=summary["packages"];need(isinstance(results,dict) and set(results)==set(rows),"all actual selected package records")
    events=result["launch_events"];need(isinstance(events,list) and len(events)==39,"all original launch observations")
    event_rows={}
    for event_number,item in enumerate(events,1):
        exact(item,("event","response","package","binding","epoch"),"root preserved launch event")
        need(Path(item["event"]["path"])==out/("launch-%03d-event.json"%event_number) and
             Path(item["response"]["path"])==out/("launch-%03d-response.json"%event_number),
             "original controller launch sequence files")
        # Controller preserves the original event and response as separate pins.
        event_pin=item["event"];raw,_=proof_file(event_pin,128*1024,contents=True)
        event=json_bytes(raw);package=event["package"]
        need(package in rows and package not in event_rows and item["package"]==package and
             item["binding"]==event["binding"] and item["epoch"]==event["epoch"],"unique observed launch event")
        event_rows[package]=(event,item)
    bound={}
    for package,row in rows.items():
        record=results[package]
        need(record["errors"]==[] and record["installed_bytes_and_metadata_verified"] is True and
             record["catalog_enabled"] is True and record["launch_binding_verified"] is True and
             record["business_accepted"] is False and record["latest_device_delivery_verified"] is False,
             "complete backend evidence with explicit business/latest limitations")
        value,_=response(record["inspection"],["/usr/bin/droidloomctl","--json","inspect",package,"--user","0"])
        installed=inspect(value,row)
        need(type(record["observed_uid"]) is int and record["observed_uid"]==installed["uid"] and
             real_epoch(record["epoch"],boot_id)==epoch,"original package owner/epoch")
        component=record["component"]
        need(component in row["components"] and (package,component) in available,"source-declared enabled component")
        value,command=response(record["launch_response"],["/usr/bin/droidloomctl","--json","launch",
                                package,"--component",component,"--user","0"])
        launch_inspection=inspect(value,row)
        need(launch_inspection["uid"]==installed["uid"],"original app UID across Launch")
        binding=actual_launch(value.get("launch"));need(binding==record["binding"],"actual owned task binding")
        event,entry=event_rows[package]
        need(event.get("schema")=="p4-selected39-launch-event-v1" and event.get("guest_boot_id")==boot_id and
             event.get("guest_clock")=="CLOCK_MONOTONIC" and event.get("epoch")==epoch and
             event.get("component")==component and event.get("binding")==binding and
             event.get("guest_monotonic_ns_start")==command["guest_monotonic_ns_start"] and
             event.get("guest_monotonic_ns_end")==command["guest_monotonic_ns_end"] and
             event.get("response")==record["launch_response"],"original event/response/clock/epoch binding")
        raw,_=proof_file(entry["response"],8*1024*1024,contents=True)
        need(raw==guest_pin(record["launch_response"],False),"controller preserved original Launch stdout")
        bound[package]={"version_code":row["version_code"],"uid":installed["uid"],"component":component,
                        "binding":binding,"inspection":record["inspection"],"launch_response":record["launch_response"]}
    need(summary["all_installed_bytes_and_metadata_verified"] is True and
         summary["all_catalog_launch_bindings_verified"] is True,"derived complete backend result")
    return {"controller_result":result_pin,"controller_config":config_pin,
            "execution_plan":config["execution_plan"],"guest_result":blobs[summary_name][0],
            "guest_boot_id":boot_id,"machine_id":config["machine_id"],"epoch":epoch,
            "packages":bound,"package_count":39,"apk_count":65,"commands":len(commands),
            "command_failures":failed,"original_backend_bound":True,
            "business_qualified":False,"latest_delivery_qualified":False,"private_accounts_qualified":False}


def require_same_candidate(materials,authority):
    need(isinstance(authority,dict) and all(authority.get(key)==materials[key]
         for key in ("public_release_id","deployment_id","native_release_id")),
         "same actual public/native deployment acceptance")


class PublicTransaction:
    """Actual dpkg public phase; CLI owns the cold/qualification authority gate.

    Tests may exercise this engine in an explicitly isolated root with real
    ordinary Debian packages. Such tests do not call the admission dispatcher
    and do not claim the production target or private data was qualified.
    """
    def __init__(self,root,bundle,release_id,*,existing=False):
        need(os.geteuid()==0,"public transaction engine requires root")
        self._owned=contextlib.ExitStack()
        try:
            self.root=Path(root);self.bundle=Path(bundle);self.release_id=digest(release_id)
            s=self.root.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0,"root directory ownership")
            self.root_device=s.st_dev
            self.intent,self.files,self.directories,self.packages,self.controls,self.audit_scopes=load_inputs(self.bundle,release_id)
            state=ensure_private_state(self.root)
            # One original cold transaction, across every release; also honor
            # the standard frontend lock while the actual dpkg child operates.
            for path,frontend in ((state/"owner.lock",False),
                                  (self.root/"var/lib/dpkg/lock-frontend",True)):
                fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
                self._owned.callback(os.close,fd)
                s=os.fstat(fd)
                need(stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and s.st_nlink==1 and not(s.st_mode&0o022),
                     "original cold/database lock")
                if frontend:fcntl.lockf(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                else:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.pointer=state/("latest-"+release_id+".json")
            self.expected_snapshot=None
            if existing:
                v,_=read_json_file(self.pointer,65536,True,{0o600})
                exact(v,("schema","release_id","transaction","snapshot"),"transaction pointer")
                need(v["schema"]=="droidloom-cold-public-latest-v1" and v["release_id"]==release_id
                     and re.fullmatch(re.escape(release_id)+r"-[0-9a-f]{16}",v["transaction"]),
                     "fixed latest transaction identity")
                self.path=state/v["transaction"];self.expected_snapshot=v["snapshot"]
                need(self.expected_snapshot["path"]==str(self.path/"SNAPSHOT.json"),"original snapshot pointer")
                s=self.path.lstat()
                need(stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0 and stat.S_IMODE(s.st_mode)==0o700,
                     "existing protected transaction")
                self.snapshot=json_bytes(read_pin(self.expected_snapshot,32*1024*1024,True))
                self.validate_snapshot()
            else:
                self.path=state/(release_id+"-"+os.urandom(8).hex())
                self.path.mkdir(mode=0o700);os.chmod(self.path,0o700)
                (self.path/"backups").mkdir(mode=0o700)
                self.snapshot=None
            self.journal=self.path/"journal.jsonl"
            self._payload_audited=False
        except BaseException:
            self._owned.close();raise

    def close(self):
        self._owned.close()

    def publish_snapshot_pointer(self):
        self.expected_snapshot=file_pin(self.path/"SNAPSHOT.json")
        value={"schema":"droidloom-cold-public-latest-v1","release_id":self.release_id,
               "transaction":self.path.name,"snapshot":self.expected_snapshot}
        temporary=self.path.parent/("next-"+self.path.name+".json")
        new_file(temporary,canonical(value),0o600)
        if self.pointer.exists():
            with held(self.pointer,root=True,modes={0o600}) as (fd,st):
                need(st.st_size<=65536,"bounded prior transaction pointer")
        os.replace(temporary,self.pointer)
        fd=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)

    def event(self,phase,**fields):
        row={"phase":phase,"release_id":self.release_id,"monotonic_ns":time.monotonic_ns(),**fields}
        b=canonical(row);need(len(b)<=65536,"bounded transaction event")
        fd=os.open(self.journal,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
        try:
            st=os.fstat(fd);need(st.st_uid==st.st_gid==0 and st.st_nlink==1 and st.st_size<=16*1024*1024,"journal custody")
            need(os.write(fd,b)==len(b),"complete transaction event");os.fsync(fd)
        finally:os.close(fd)

    @contextlib.contextmanager
    def directory(self,relative,*,missing=False):
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:
            if relative:
                public_relative(relative)
                for part in relative.split("/"):
                    try:n=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=fd)
                    except FileNotFoundError:
                        if missing:
                            yield None;return
                        raise
                    os.close(fd);fd=n
                    s=os.fstat(fd)
                    need(s.st_dev==self.root_device and s.st_uid==0 and not(s.st_mode&0o022),
                         "original public parent directory boundary")
            yield fd
        finally:os.close(fd)

    def package_absent(self,name):
        status=self.root/"var/lib/dpkg/status"
        with held(status,root=True,maximum=32*1024*1024) as (fd,st):
            b=os.read(fd,st.st_size+1);need(len(b)==st.st_size,"complete dpkg status")
        for paragraph in b.decode("utf-8","strict").split("\n\n"):
            lines=dict(line.split(": ",1) for line in paragraph.splitlines() if ": " in line and not line[0].isspace())
            if lines.get("Package")==name:
                need(lines.get("Status","").split()[-1:]==["not-installed"],"existing package version requires a separate admitted upgrade transaction")

    def audit_payloads(self):
        if self._payload_audited:return
        for role in PUBLIC_ORDER:
            result=package_payload(self.packages[role],self.audit_scopes[role],self.path)
            self.event("public-package-payload-verified",role=role,**result)
        self._payload_audited=True

    def capture(self):
        need(self.snapshot is None,"transaction already snapshotted")
        self.audit_payloads()
        for name in NAMES.values():self.package_absent(name)
        dirs={};leaves={};budget=0
        for rel in sorted(self.directories,key=lambda x:(x.count("/"),x)):
            with self.directory(rel,missing=True) as fd:
                if fd is None:dirs[rel]={"existed":False};continue
                s=os.fstat(fd);dirs[rel]={"existed":True,"identity":list(f9(s)),"xattrs":bounded_xattrs(fd)}
        for index,(rel,row) in enumerate(sorted(self.files.items())):
            parent,_,leaf=rel.rpartition("/")
            with self.directory(parent,missing=True) as d:
                if d is None:leaves[rel]={"existed":False};continue
                try:fd=os.open(leaf,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d)
                except FileNotFoundError:
                    leaves[rel]={"existed":False};continue
                try:
                    s=os.fstat(fd)
                    need(stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and s.st_nlink==1 and s.st_dev==self.root_device,
                         "only original root-owned public regular files may be replaced")
                    budget+=s.st_size;need(budget<=MAX_BYTES,"public backup byte budget")
                    sha=hash_fd(fd);attrs=bounded_xattrs(fd)
                    pin={"path":str(absolute_under(self.root,rel)),"bytes":s.st_size,"sha256":sha}
                    backup=self.path/"backups"/f"{index:05d}"
                    out=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
                    try:
                        os.fchmod(out,0o600);os.lseek(fd,0,os.SEEK_SET);copied=0
                        while True:
                            block=os.read(fd,1024*1024)
                            if not block:break
                            copied+=len(block);need(copied<=s.st_size,"original public backup grew")
                            view=memoryview(block)
                            while view:
                                n=os.write(out,view);need(n>0,"public backup write");view=view[n:]
                        need(copied==s.st_size,"public backup truncated");os.fsync(out)
                    finally:os.close(out)
                    need(file_pin(backup)["sha256"]==sha,"original backup digest")
                    need(f9(os.fstat(fd))==f9(s) and f9(os.stat(leaf,dir_fd=d,follow_symlinks=False))==f9(s),
                         "original public file changed during backup")
                    leaves[rel]={"existed":True,"identity":list(f9(s)),"sha256":sha,
                                 "backup":file_pin(backup),"xattrs":attrs}
                finally:os.close(fd)
        preserved={}
        for path in PRESERVE_METADATA:
            p=self.root/path.lstrip("/")
            preserved[path]=list(f9(p.lstat()))
        self.snapshot={"schema":"droidloom-cold-public-snapshot-v1","release_id":self.release_id,
             "root_identity":[self.root_device,self.root.stat().st_ino],"files":leaves,"directories":dirs,
             "preserved_metadata_only":preserved,"backup_bytes":budget}
        new_file(self.path/"SNAPSHOT.json",canonical(self.snapshot),0o600)
        self.validate_snapshot()
        self.publish_snapshot_pointer()
        self.event("snapshot",snapshot=self.expected_snapshot,files=len(leaves),backup_bytes=budget)

    def validate_snapshot(self):
        v=self.snapshot
        exact(v,("schema","release_id","root_identity","files","directories","preserved_metadata_only","backup_bytes"),"snapshot")
        need(v["schema"]=="droidloom-cold-public-snapshot-v1" and v["release_id"]==self.release_id and
             v["root_identity"]==[self.root_device,self.root.stat().st_ino],"original transaction root")
        need(set(v["files"])==set(self.files) and set(v["directories"])==set(self.directories),"snapshot scope")
        need(set(v["preserved_metadata_only"])==set(PRESERVE_METADATA),"original account/SSH metadata guards")
        for index,(rel,row) in enumerate(sorted(v["files"].items())):
            if row["existed"]:
                exact(row,("existed","identity","sha256","backup","xattrs"),"saved public file")
                need(row["backup"]["path"]==str(self.path/"backups"/f"{index:05d}") and
                     row["backup"]["sha256"]==row["sha256"] and row["backup"]["bytes"]==row["identity"][6],
                     "fixed backup identity")
                with held(row["backup"]["path"],root=True,modes={0o600}) as (fd,st):
                    need(st.st_size==row["backup"]["bytes"] and hash_fd(fd)==row["sha256"],"saved original bytes changed")
            else:exact(row,("existed",),"absent original public file")

    def preserved(self):
        for path,original in self.snapshot["preserved_metadata_only"].items():
            need(list(f9((self.root/path.lstrip("/")).lstat()))==original,
                 "account/SSH/home metadata changed during public transaction")

    def recreated_directories(self):
        result={}
        if not self.journal.exists():return result
        with held(self.journal,root=True,modes={0o600},maximum=16*1024*1024) as (fd,st):
            raw=os.read(fd,st.st_size+1);need(len(raw)==st.st_size,"complete owned transaction journal")
        for line in raw.splitlines():
            value=json_bytes(line)
            need(value.get("release_id")==self.release_id,"journal release identity")
            if value.get("phase")!="rollback-directory-created":continue
            exact(value,("phase","release_id","monotonic_ns","path","original_identity","identity"),
                  "owned recreated directory event")
            rel=public_relative(value["path"]);row=self.snapshot["directories"].get(rel)
            identity=value["identity"]
            need(row is not None and row["existed"] and rel not in result and
                 value["original_identity"]==row["identity"][:2] and
                 isinstance(identity,list) and len(identity)==9 and
                 identity[0]==self.root_device and identity[1]>0 and
                 stat.S_ISDIR(identity[2]) and identity[3:5]==[0,0] and
                 type(value["monotonic_ns"]) is int and value["monotonic_ns"]>0,
                 "recreated directory must belong to this original snapshot")
            result[rel]=identity[:2]
        return result

    def recreate_original_directories(self):
        owned=self.recreated_directories()
        for rel,row in sorted(self.snapshot["directories"].items(),
                              key=lambda x:(x[0].count("/"),x[0])):
            if not row["existed"]:continue
            parent,_,leaf=rel.rpartition("/")
            with self.directory(parent) as parent_fd:
                try:fd=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent_fd)
                except FileNotFoundError:
                    need(rel not in owned,"previously recreated directory disappeared")
                    os.mkdir(leaf,0o700,dir_fd=parent_fd)
                    fd=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent_fd)
                    try:
                        st=os.fstat(fd)
                        need(st.st_dev==self.root_device and st.st_uid==st.st_gid==0 and
                             stat.S_IMODE(st.st_mode)==0o700,"new rollback directory identity")
                        os.fsync(fd);os.fsync(parent_fd)
                        self.event("rollback-directory-created",path=rel,
                                   original_identity=row["identity"][:2],identity=list(f9(st)))
                        owned[rel]=[st.st_dev,st.st_ino]
                    except BaseException:
                        os.close(fd);raise
                try:
                    st=os.fstat(fd)
                    need([st.st_dev,st.st_ino]==owned.get(rel,row["identity"][:2]),
                         "unknown directory replacement blocks public rollback")
                finally:os.close(fd)
        return owned

    def restore_directory_metadata(self,*,owned=None):
        owned={} if owned is None else owned
        for rel,row in sorted(self.snapshot["directories"].items(),key=lambda x:x[0].count("/")):
            if not row["existed"]:continue
            with self.directory(rel) as fd:
                s=os.fstat(fd);before=row["identity"]
                need([s.st_dev,s.st_ino]==owned.get(rel,before[:2]),
                     "original public parent directory replaced")
                os.fchown(fd,before[3],before[4]);os.fchmod(fd,stat.S_IMODE(before[2]))
                restore_xattrs(fd,row["xattrs"]);os.fsync(fd)

    def dpkg(self,operation):
        need(operation in ("unpack","configure","remove"),"closed dpkg operation")
        need(self.snapshot is not None,"original snapshot required")
        self.event("dpkg-"+operation+"-begin")
        argv=[SYSTEM_DPKG,"--root="+str(self.root),"--no-triggers","--"+operation]
        held_fds=[]
        try:
            if operation=="unpack":
                for role in PUBLIC_ORDER:
                    pin=self.packages[role]
                    fd=os.open(pin["path"],os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
                    st=os.fstat(fd);need(st.st_uid==st.st_gid==0 and st.st_nlink==1 and stat.S_ISREG(st.st_mode)
                        and st.st_size==pin["bytes"] and hash_fd(fd)==pin["sha256"],"original protected package FD")
                    os.lseek(fd,0,os.SEEK_SET);held_fds.append(fd);argv.append(f"/proc/self/fd/{fd}")
            else:argv.extend(NAMES[r] for r in PUBLIC_ORDER)
            r=bounded_process(argv,env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","LC_ALL":"C",
                    "DEBIAN_FRONTEND":"noninteractive","DPKG_FRONTEND_LOCKED":"1"},seconds=300,maximum=8*1024*1024,pass_fds=tuple(held_fds))
            suffix=str(time.monotonic_ns())
            new_file(self.path/(operation+"-"+suffix+".stdout"),r["stdout"],0o600)
            new_file(self.path/(operation+"-"+suffix+".stderr"),r["stderr"],0o600)
            self.event("dpkg-"+operation+"-end",exit_code=r["exit"])
            need(r["exit"]==0,"normal dpkg public "+operation+" failed; protected snapshot retained")
        finally:
            for fd in held_fds:os.close(fd)

    def verify_installed(self):
        for rel,row in self.files.items():
            with held(absolute_under(self.root,rel),root=True,modes={row["mode"]},
                      host_acl=rel==HOST_ACL_MEMBER) as (fd,st):
                need(st.st_size==row["bytes"] and hash_fd(fd)==row["sha256"],"installed normal public bytes differ")
                try:os.getxattr(fd,"security.capability")
                except OSError as e:
                    need(e.errno in (61,95),"installed file capability query failed")
                else:raise Rejected("normal public package unexpectedly installed file capabilities")
        self.preserved()
        self.event("public-installed-readback",files=len(self.files),runtime_qualified=False)

    def install(self):
        self.capture()
        self.dpkg("unpack")
        self.dpkg("configure")
        # Package structural directories may not widen an existing private
        # parent. Preserve its original owner/mode/ACL, including 0700 roots.
        self.restore_directory_metadata()
        self.verify_installed()
        self.event("public-phase-completed",activated=False)

    def restore_files(self):
        self.validate_snapshot()
        owned=self.recreate_original_directories()
        for index,(rel,row) in enumerate(sorted(self.snapshot["files"].items())):
            parent,_,leaf=rel.rpartition("/")
            if not row["existed"]:
                with self.directory(parent,missing=True) as d:
                    if d is None:continue
                    try:fd=os.open(leaf,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d)
                    except FileNotFoundError:continue
                    try:
                        s=os.fstat(fd);expected=self.files[rel]
                        need(s.st_uid==s.st_gid==0 and s.st_nlink==1 and stat.S_ISREG(s.st_mode)
                             and s.st_size==expected["bytes"] and hash_fd(fd)==expected["sha256"],
                             "refuse to delete a changed post-install public file")
                        need((os.stat(leaf,dir_fd=d,follow_symlinks=False).st_dev,
                              os.stat(leaf,dir_fd=d,follow_symlinks=False).st_ino)==(s.st_dev,s.st_ino),
                             "public leaf replacement during rollback")
                        os.unlink(leaf,dir_fd=d);os.fsync(d)
                    finally:os.close(fd)
                continue
            with self.directory(parent) as d:
                try:current=os.open(leaf,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d)
                except FileNotFoundError:current=None
                if current is not None:
                    try:
                        st=os.fstat(current);need(st.st_uid==st.st_gid==0 and st.st_nlink==1,"rollback leaf owner")
                        sha=hash_fd(current)
                        need(sha in (row["sha256"],self.files[rel]["sha256"]),"refuse to overwrite a changed public file")
                    finally:os.close(current)
                temporary=".droidloom-restore-"+self.release_id[:16]+"-"+f"{index:05d}"
                fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600,dir_fd=d)
                try:
                    with held(row["backup"]["path"],root=True,modes={0o600}) as (source,st):
                        need(st.st_size==row["backup"]["bytes"] and hash_fd(source)==row["sha256"],"original backup bytes")
                        os.lseek(source,0,os.SEEK_SET)
                        while True:
                            block=os.read(source,1024*1024)
                            if not block:break
                            view=memoryview(block)
                            while view:
                                n=os.write(fd,view);need(n>0,"rollback write");view=view[n:]
                    original=row["identity"]
                    os.fchown(fd,original[3],original[4]);os.fchmod(fd,stat.S_IMODE(original[2]))
                    restore_xattrs(fd,row["xattrs"]);os.fsync(fd)
                finally:os.close(fd)
                os.rename(temporary,leaf,src_dir_fd=d,dst_dir_fd=d);os.fsync(d)
        self.restore_directory_metadata(owned=owned)
        for rel,row in sorted(self.snapshot["directories"].items(),key=lambda x:-x[0].count("/")):
            if row["existed"]:continue
            try:absolute_under(self.root,rel).rmdir()
            except FileNotFoundError:pass
            except OSError as e:
                need(e.errno in (39,17),"unexpected new-directory rollback error")
                self.event("new-directory-not-empty-preserved",path=rel)
        self.preserved()
        self.event("original-public-files-restored",files=len(self.files),original_data_accessed=False)

    def rollback(self):
        need(self.snapshot is not None,"rollback needs the original durable snapshot")
        self.audit_payloads()
        self.preserved()
        # Check before dpkg is allowed to unlink a leaf. A different public
        # update or a changed file is preserved and requires reconciliation.
        for rel,row in self.files.items():
            path=absolute_under(self.root,rel)
            try:
                with held(path,root=True,host_acl=rel==HOST_ACL_MEMBER) as (fd,st):
                    old=self.snapshot["files"][rel]
                    allowed={row["sha256"]}
                    if old["existed"]:allowed.add(old["sha256"])
                    need(hash_fd(fd) in allowed,"changed public file blocks package removal")
            except FileNotFoundError:pass
        status_path=self.root/"var/lib/dpkg/status"
        with held(status_path,root=True,maximum=32*1024*1024) as (fd,st):
            status=os.read(fd,st.st_size+1).decode("utf-8","strict")
        expected={NAMES[k]:self.controls[k]["version"] for k in PUBLIC_ORDER}
        for paragraph in status.split("\n\n"):
            fields=dict(line.split(": ",1) for line in paragraph.splitlines()
                        if ": " in line and not line[0].isspace())
            if fields.get("Package") in expected and fields.get("Status","").split()[-1:]!=["not-installed"]:
                need(fields.get("Version")==expected[fields["Package"]],"different package version blocks rollback")
        self.dpkg("remove")
        self.restore_files()
        self.event("public-rollback-completed",rebooted=False)

# The boot phase is separate from package installation and never starts a unit
# or changes the next boot. Only arm_once(), after admission, may set next_entry.
BOOT_TARGET="etc/systemd/system/droidloom-production.target"
BOOT_FILE_BUDGET=1024**3
BOOT_EVENT_SCHEMA="droidloom-cold-boot-event-v2"
BOOT_ID=re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

def boot_clock():
    """Observe this boot; a monotonic value is meaningful only within it."""
    fd=os.open("/proc/sys/kernel/random/boot_id",os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        raw=os.read(fd,64)
        need(not os.read(fd,1),"bounded kernel boot identity")
    finally:os.close(fd)
    value=raw.decode("ascii","strict").strip()
    need(BOOT_ID.fullmatch(value) is not None,"actual kernel boot identity")
    return value,time.monotonic_ns()

def boot_file_scope(deployment_id):
    deployment_id=digest(deployment_id)
    return {
        "boot/grub/grub.cfg":0o444,
        "boot/grub/grubenv":0o600,
        "boot/grub/droidloom/"+deployment_id+".cfg":0o400,
        "etc/grub.d/42_droidloom_"+deployment_id:0o755,
        "etc/default/grub.d/90-droidloom-recovery.cfg":0o644,
        "boot/droidloom/releases/"+deployment_id+"/initrd.img":0o400,
        BOOT_TARGET:0o644,
        "etc/droidloom-maintenance/installation.json":0o400,
    }

def stock_grub_entries(raw):
    """Preserve complete entries from stock grub-mkconfig's checked syntax.

    Callers must first run the admitted grub-script-check. This deliberately
    rejects an unreviewed custom layout instead of attempting to reinterpret it.
    """
    need(isinstance(raw,bytes) and 0<len(raw)<=16*1024*1024 and b"\0" not in raw,
         "bounded ordinary GRUB configuration")
    lines=raw.decode("utf-8","strict").splitlines(keepends=True)
    entries=[];begin=None
    for index,line in enumerate(lines):
        if begin is None:
            if line.startswith(("menuentry ","submenu ")):
                need(line.rstrip().endswith("{"),"ordinary GRUB entry opening")
                begin=index
        elif line.rstrip()=="}":
            body="".join(lines[begin:index+1]).encode()
            need(body not in entries,"duplicate original GRUB entry")
            entries.append(body);begin=None
    need(begin is None and entries,"complete stock GRUB menu entries")
    return entries


class BootFileTransaction:
    """Closed, durable boot-file publication on one admitted native filesystem.

    The production dispatcher supplies cold authority and actual qualification.
    This engine can also be tested in an independent public root; it never
    infers physical authority from such a successful mechanism test.
    """
    def __init__(self,root,release_id,deployment_id,*,existing=None):
        need(os.getuid()==os.geteuid()==0,"boot publication requires root")
        self.root=Path("/") if str(root)=="/" else safe_absolute(str(root))
        self.release_id=digest(release_id)
        self.deployment_id=digest(deployment_id);self.files=boot_file_scope(deployment_id)
        self._owned=contextlib.ExitStack();self.snapshot=None
        try:
            self.root_fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            self._owned.callback(os.close,self.root_fd)
            st=os.fstat(self.root_fd)
            need(st.st_uid==st.st_gid==0 and not(st.st_mode&0o022),"protected native root")
            self.root_identity=[st.st_dev,st.st_ino];self.root_device=st.st_dev
            parent=ensure_private_state(self.root)
            lock=os.open(parent/"owner.lock",os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
            self._owned.callback(os.close,lock);st=os.fstat(lock)
            need(stat.S_ISREG(st.st_mode) and st.st_uid==st.st_gid==0 and st.st_nlink==1
                 and not(st.st_mode&0o022),"original cold owner lock")
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if existing is None:
                self.path=parent/(self.deployment_id+"-boot-"+os.urandom(8).hex())
                self.path.mkdir(mode=0o700)
                for name in ("backups","staged"):(self.path/name).mkdir(mode=0o700)
            else:
                self.path=safe_absolute(str(existing))
                need(self.path.parent==parent and re.fullmatch(
                    re.escape(self.deployment_id)+r"-boot-[0-9a-f]{16}",self.path.name),
                    "same fixed boot transaction")
                for p in (self.path,self.path/"backups",self.path/"staged"):
                    s=p.lstat()
                    need(stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0
                         and s.st_dev==self.root_device and stat.S_IMODE(s.st_mode)==0o700,
                         "original protected boot state")
                self.snapshot,_=read_json_file(self.path/"SNAPSHOT.json",8*1024*1024,True,{0o400})
            self.journal=self.path/"events.jsonl"
            if self.snapshot is not None:self.validate_snapshot()
        except BaseException:
            self._owned.close();raise

    def close(self):self._owned.close()

    def event(self,phase,**values):
        previous=self.events();boot,now=boot_clock()
        if previous:
            if previous[-1]["boot_id"]==boot:
                need(now>previous[-1]["monotonic_ns"],"same-boot event clock decreased")
            else:
                need(all(row["boot_id"]!=boot for row in previous),"closed boot segment reappeared")
        need(not(set(values)&{"schema","sequence","boot_id","monotonic_ns","phase",
                              "release_id","deployment_id"}),"fixed boot event envelope")
        body=canonical({"schema":BOOT_EVENT_SCHEMA,"sequence":len(previous)+1,
            "phase":phase,"release_id":self.release_id,"deployment_id":self.deployment_id,
            "boot_id":boot,"monotonic_ns":now,**values})
        need(len(body)<=1024*1024,"bounded boot event")
        fd=os.open(self.journal,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            st=os.fstat(fd)
            need(stat.S_ISREG(st.st_mode) and st.st_uid==st.st_gid==0 and st.st_nlink==1
                 and stat.S_IMODE(st.st_mode)==0o600 and st.st_size<=32*1024*1024,
                 "protected boot event journal")
            view=memoryview(body)
            while view:
                n=os.write(fd,view);need(n>0,"boot event write");view=view[n:]
            os.fsync(fd)
        finally:os.close(fd)
        d=os.open(self.path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:os.fsync(d)
        finally:os.close(d)

    def events(self):
        try:
            with held(self.journal,root=True,modes={0o600},maximum=32*1024*1024) as (fd,st):
                raw=os.read(fd,st.st_size+1);need(len(raw)==st.st_size,"complete boot journal")
        except FileNotFoundError:return []
        rows=[];last=0;boot=None;seen_boots=set()
        for line in raw.splitlines():
            row=json_bytes(line)
            current=row.get("boot_id")
            need(row.get("schema")==BOOT_EVENT_SCHEMA
                 and type(row.get("sequence")) is int and row["sequence"]==len(rows)+1
                 and row.get("release_id")==self.release_id and row.get("deployment_id")==self.deployment_id
                 and isinstance(current,str) and BOOT_ID.fullmatch(current) is not None
                 and type(row.get("monotonic_ns")) is int and row["monotonic_ns"]>0,
                 "boot journal identity, sequence and clock segment")
            if current!=boot:
                need(current not in seen_boots,"closed boot journal segment reappeared")
                seen_boots.add(current);boot=current;last=0
            need(row["monotonic_ns"]>last,"same-boot journal clock decreased")
            last=row["monotonic_ns"];rows.append(row)
        return rows

    def parents(self):
        result=set()
        for rel in self.files:
            parts=rel.split("/")
            result.update("/".join(parts[:n]) for n in range(1,len(parts)))
        return result

    def created_directories(self):
        out={}
        for row in self.events():
            if row["phase"]!="boot-directory-created":continue
            rel=row["path"]
            need(rel in self.parents() and rel not in out,"unique owned boot directory")
            identity=row["identity"]
            need(isinstance(identity,list) and len(identity)==9 and identity[0]==self.root_device
                 and stat.S_ISDIR(identity[2]) and identity[3:5]==[0,0],"created directory identity")
            out[rel]=identity
        return out

    @contextlib.contextmanager
    def directory(self,relative,*,missing=False,create=False):
        need(not relative or relative in self.parents(),"closed boot parent")
        fd=os.dup(self.root_fd);walk=[]
        try:
            for part in relative.split("/") if relative else ():
                walk.append(part);current="/".join(walk)
                try:n=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        if missing:yield None;return
                        raise
                    need(self.snapshot is not None and not self.snapshot["directories"][current]["existed"],
                         "only snapshotted absent parents may be created")
                    need(current not in self.created_directories(),"owned boot directory disappeared")
                    self.event("boot-directory-create-started",path=current)
                    mode=0o700 if current.startswith(("boot/droidloom","boot/grub/droidloom",
                                                      "etc/droidloom-maintenance")) else 0o755
                    os.mkdir(part,mode,dir_fd=fd)
                    n=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                    os.fchmod(n,mode);os.fsync(n);os.fsync(fd)
                    self.event("boot-directory-created",path=current,identity=list(f9(os.fstat(n))))
                os.close(fd);fd=n;s=os.fstat(fd)
                need(s.st_uid==s.st_gid==0 and s.st_dev==self.root_device and not(s.st_mode&0o022),
                     "native boot parent boundary")
                if self.snapshot is not None:
                    old=self.snapshot["directories"][current]
                    expected=old["identity"] if old["existed"] else self.created_directories().get(current)
                    need(expected is not None and [s.st_dev,s.st_ino]==expected[:2],
                         "original or owned boot parent replaced")
            yield fd
        finally:os.close(fd)

    def leaf(self,relative):
        need(relative in self.files,"closed boot file")
        parent,_,name=relative.rpartition("/")
        with self.directory(parent,missing=True) as d:
            if d is None:return None
            try:fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=d)
            except FileNotFoundError:return None
            try:
                st=os.fstat(fd)
                need(stat.S_ISREG(st.st_mode) and st.st_dev==self.root_device and st.st_uid==st.st_gid==0
                     and st.st_nlink==1 and not(st.st_mode&0o7022) and st.st_size<=BOOT_FILE_BUDGET,
                     "single original native boot file")
                sha=hash_fd(fd);attrs=bounded_xattrs(fd)
                need("security.capability" not in attrs,"boot files must not carry file capabilities")
                need(f9(st)==f9(os.fstat(fd))==f9(os.stat(name,dir_fd=d,follow_symlinks=False)),
                     "boot file changed while held")
                return {"identity":list(f9(st)),"atime_ns":st.st_atime_ns,"sha256":sha,"xattrs":attrs}
            finally:os.close(fd)

    def capture(self):
        need(self.snapshot is None,"boot snapshot already exists")
        directories={};files={};budget=0
        for rel in sorted(self.parents(),key=lambda x:(x.count("/"),x)):
            with self.directory(rel,missing=True) as fd:
                if fd is None:directories[rel]={"existed":False};continue
                st=os.fstat(fd);directories[rel]={"existed":True,"identity":list(f9(st)),
                                                "xattrs":bounded_xattrs(fd)}
        for index,rel in enumerate(sorted(self.files)):
            row=self.leaf(rel)
            if row is None:files[rel]={"existed":False};continue
            budget+=row["identity"][6];need(budget<=BOOT_FILE_BUDGET,"bounded original boot backup")
            pin={"path":str(self.root/rel),"bytes":row["identity"][6],"sha256":row["sha256"]}
            backup=self.path/"backups"/f"{index:03d}"
            copy_pin(pin,backup,0o400)
            again=self.leaf(rel);need(again is not None and again["identity"]==row["identity"]
                                     and again["xattrs"]==row["xattrs"],"original boot changed during backup")
            files[rel]={"existed":True,**row,"backup":file_pin(backup)}
        self.snapshot={"schema":"droidloom-cold-boot-files-snapshot-v2","release_id":self.release_id,
            "deployment_id":self.deployment_id,"root_identity":self.root_identity,
            "files":files,"directories":directories,"backup_bytes":budget}
        new_file(self.path/"SNAPSHOT.json",canonical(self.snapshot),0o400)
        self.validate_snapshot()
        self.event("boot-files-snapshot",snapshot=file_pin(self.path/"SNAPSHOT.json"))

    def validate_snapshot(self):
        v=self.snapshot
        exact(v,("schema","release_id","deployment_id","root_identity","files","directories","backup_bytes"),
              "boot snapshot")
        need(v["schema"]=="droidloom-cold-boot-files-snapshot-v2" and v["release_id"]==self.release_id
             and v["deployment_id"]==self.deployment_id and v["root_identity"]==self.root_identity
             and set(v["files"])==set(self.files) and set(v["directories"])==self.parents(),
             "complete fixed boot snapshot")
        total=0
        for index,(rel,row) in enumerate(sorted(v["files"].items())):
            if not row["existed"]:exact(row,("existed",),"absent original boot file");continue
            exact(row,("existed","identity","atime_ns","sha256","xattrs","backup"),"original boot file")
            identity=row["identity"]
            need(isinstance(identity,list) and len(identity)==9 and identity[0]==self.root_device
                 and stat.S_ISREG(identity[2]) and identity[3:6]==[0,0,1],"original boot inode")
            pin=row["backup"];need(pin["path"]==str(self.path/"backups"/f"{index:03d}")
                 and pin["bytes"]==identity[6] and pin["sha256"]==row["sha256"],"fixed boot backup")
            with held(pin["path"],root=True,modes={0o400},maximum=BOOT_FILE_BUDGET) as (fd,st):
                need(st.st_size==pin["bytes"] and hash_fd(fd)==pin["sha256"],"original boot backup changed")
            total+=pin["bytes"]
        need(total==v["backup_bytes"] and total<=BOOT_FILE_BUDGET,"boot snapshot bytes")

    def staged(self):
        rows={}
        for row in self.events():
            if row["phase"]!="boot-file-staged":continue
            rel=row["path"];need(rel in self.files,"fixed staged boot target")
            pin=row["source"]
            need(pin["path"]==str(self.path/"staged"/hashlib.sha256(rel.encode()).hexdigest()),
                 "fixed staged source")
            need(rel not in rows or rows[rel]==pin,"conflicting staged boot file")
            rows[rel]=pin
        return rows

    def stage(self,relative,pin):
        need(self.snapshot is not None and relative in self.files,"snapshot and closed boot target required")
        target=self.path/"staged"/hashlib.sha256(relative.encode()).hexdigest()
        need(relative not in self.staged(),"boot target already staged")
        need(0<pin["bytes"]<=BOOT_FILE_BUDGET,"bounded staged boot file")
        copy_pin(pin,target,0o400)
        actual=file_pin(target);self.event("boot-file-staged",path=relative,source=actual)
        return actual

    def stage_bytes(self,relative,body):
        need(isinstance(body,bytes) and 0<len(body)<=16*1024*1024,"bounded source-owned boot text")
        source=self.path/("source-"+hashlib.sha256(relative.encode()+body).hexdigest())
        new_file(source,body,0o400)
        return self.stage(relative,file_pin(source))

    def unchanged_or_owned(self,relative,current):
        old=self.snapshot["files"][relative];staged=self.staged().get(relative)
        if current is None:
            need(not old["existed"],"original boot file disappeared");return
        own_nodes={tuple(row["identity"][:2]) for row in self.events()
                   if row["phase"]=="boot-file-rename-ready" and row["path"]==relative
                   and row["sha256"]==current["sha256"]}
        known_node=tuple(current["identity"][:2]) in own_nodes
        original=(old["existed"] and (known_node or current["identity"][:2]==old["identity"][:2]) and
            current["sha256"]==old["sha256"] and
            current["identity"][2:7]==old["identity"][2:7] and current["xattrs"]==old["xattrs"])
        expected_attrs=old["xattrs"] if old["existed"] else {}
        owned=(known_node and staged is not None and current["sha256"]==staged["sha256"] and
            current["identity"][6]==staged["bytes"] and
            stat.S_IMODE(current["identity"][2])==self.files[relative] and current["xattrs"]==expected_attrs)
        need(original or owned,"unknown boot-file update blocks publication and rollback")

    def cleanup_temporaries(self):
        """Retire only named original inodes recorded by this transaction."""
        created={};started=set()
        for row in self.events():
            if row["phase"] not in ("boot-file-temporary-create-started","boot-file-temporary-created",
                                    "boot-file-rename-ready"):continue
            rel=row.get("path");name=row.get("temporary")
            need(rel in self.files and isinstance(name,str)
                 and re.fullmatch(r"\.droidloom-boot-[0-9a-f]{24}",name),"fixed recorded boot temporary")
            key=(rel,name)
            if row["phase"]=="boot-file-temporary-create-started":
                need(key not in started,"duplicate boot temporary creation")
                started.add(key);continue
            identity=row.get("identity")
            need(key in started and isinstance(identity,list) and len(identity)==9
                 and identity[0]==self.root_device and stat.S_ISREG(identity[2])
                 and identity[3:6]==[0,0,1],"recorded boot temporary inode")
            if row["phase"]=="boot-file-temporary-created":
                need(key not in created,"duplicate boot temporary inode")
                created[key]=identity
            else:
                need(key in created and identity[:2]==created[key][:2],"rename names the original temporary inode")
                digest(row["sha256"])
        for relative,name in sorted(started):
            parent,_,_=relative.rpartition("/")
            with self.directory(parent,missing=True) as directory:
                if directory is None:continue
                try:fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory)
                except FileNotFoundError:continue
                try:
                    current=os.fstat(fd);identity=created.get((relative,name))
                    need(identity is not None and [current.st_dev,current.st_ino]==identity[:2]
                         and stat.S_ISREG(current.st_mode) and current.st_uid==current.st_gid==0
                         and current.st_nlink==1 and not(current.st_mode&0o7022)
                         and current.st_size<=BOOT_FILE_BUDGET,"unknown boot temporary must be preserved")
                    need("security.capability" not in bounded_xattrs(fd),"boot temporary gained file capabilities")
                    self.event("boot-file-temporary-remove-started",path=relative,temporary=name,
                               identity=list(f9(current)))
                    need(f9(os.stat(name,dir_fd=directory,follow_symlinks=False))==f9(current),
                         "recorded boot temporary changed before retirement")
                    os.unlink(name,dir_fd=directory);os.fsync(directory)
                    self.event("boot-file-temporary-removed",path=relative,temporary=name,
                               identity=list(f9(current)))
                finally:os.close(fd)

    def write_leaf(self,relative,pin,mode,attrs,*,times=None):
        parent,_,leaf=relative.rpartition("/")
        with self.directory(parent,create=True) as d:
            before=self.leaf(relative);self.unchanged_or_owned(relative,before)
            temporary=".droidloom-boot-"+os.urandom(12).hex()
            self.event("boot-file-temporary-create-started",path=relative,temporary=temporary)
            out=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=d)
            published=False
            try:
                os.fsync(out);os.fsync(d)
                self.event("boot-file-temporary-created",path=relative,temporary=temporary,
                           identity=list(f9(os.fstat(out))))
                with held(pin["path"],root=True,modes={0o400},maximum=BOOT_FILE_BUDGET) as (source,st):
                    need(st.st_size==pin["bytes"] and hash_fd(source)==pin["sha256"],"held boot source")
                    copied=0;h=hashlib.sha256()
                    while True:
                        block=os.read(source,1024*1024)
                        if not block:break
                        copied+=len(block);h.update(block);view=memoryview(block)
                        while view:
                            n=os.write(out,view);need(n>0,"boot leaf write");view=view[n:]
                    need(copied==pin["bytes"] and h.hexdigest()==pin["sha256"],"complete boot source")
                os.fchown(out,0,0);os.fchmod(out,mode);restore_xattrs(out,attrs)
                if times is not None:os.utime(out,ns=times)
                os.fsync(out)
                now=self.leaf(relative)
                need((now is None and before is None) or
                     (now is not None and before is not None and now["identity"]==before["identity"]
                      and now["xattrs"]==before["xattrs"]),"boot target changed before atomic publication")
                self.event("boot-file-rename-ready",path=relative,temporary=temporary,identity=list(f9(os.fstat(out))),
                           sha256=pin["sha256"])
                os.rename(temporary,leaf,src_dir_fd=d,dst_dir_fd=d);published=True;os.fsync(d)
            finally:
                try:
                    if not published:
                        try:named=os.stat(temporary,dir_fd=d,follow_symlinks=False)
                        except FileNotFoundError:pass
                        else:
                            current=os.fstat(out)
                            need(f9(named)==f9(current),"unknown temporary replacement must be preserved")
                            os.unlink(temporary,dir_fd=d);os.fsync(d)
                finally:os.close(out)
            row=self.leaf(relative)
            need(row is not None and row["sha256"]==pin["sha256"] and row["identity"][6]==pin["bytes"]
                 and stat.S_IMODE(row["identity"][2])==mode and row["xattrs"]==attrs,
                 "boot leaf whole readback")
            return row

    def publish(self,relative):
        need(self.snapshot is not None,"original boot snapshot required")
        pin=self.staged().get(relative);need(pin is not None,"actual staged boot file required")
        self.unchanged_or_owned(relative,self.leaf(relative))
        old=self.snapshot["files"][relative]
        attrs=old["xattrs"] if old["existed"] else {}
        # Existing ACL/capability metadata is preserved; SELinux publication is
        # an explicit, separately journaled metadata phase, never guessed here.
        self.event("boot-file-publish-started",path=relative,source=pin)
        result=self.write_leaf(relative,pin,self.files[relative],attrs)
        self.event("boot-file-published",path=relative,identity=result["identity"],sha256=result["sha256"])
        return result

    def rollback(self):
        need(self.snapshot is not None,"original boot snapshot required")
        self.validate_snapshot();self.cleanup_temporaries();staged=self.staged()
        for rel in staged:self.unchanged_or_owned(rel,self.leaf(rel))
        for rel in reversed(tuple(staged)):
            old=self.snapshot["files"][rel];now=self.leaf(rel)
            self.unchanged_or_owned(rel,now)
            self.event("boot-file-restore-started",path=rel)
            if old["existed"]:
                self.write_leaf(rel,old["backup"],stat.S_IMODE(old["identity"][2]),old["xattrs"],
                                times=(old["atime_ns"],old["identity"][7]))
            elif now is not None:
                parent,_,name=rel.rpartition("/")
                with self.directory(parent) as d:
                    st=os.stat(name,dir_fd=d,follow_symlinks=False)
                    need(list(f9(st))==now["identity"],"owned boot file replaced before removal")
                    os.unlink(name,dir_fd=d);os.fsync(d)
            self.event("boot-file-restored",path=rel,existed=old["existed"])
        created=self.created_directories()
        for rel,identity in sorted(created.items(),key=lambda x:-x[0].count("/")):
            with self.directory(rel,missing=True) as fd:
                if fd is None:continue
                need([os.fstat(fd).st_dev,os.fstat(fd).st_ino]==identity[:2],"owned boot directory replaced")
            parent,_,name=rel.rpartition("/")
            with self.directory(parent) as fd:
                try:os.rmdir(name,dir_fd=fd);os.fsync(fd)
                except OSError as e:
                    need(e.errno in (39,17),"boot directory retirement failed")
                    self.event("boot-directory-nonempty-preserved",path=rel)
        for rel,row in self.snapshot["directories"].items():
            if not row["existed"]:continue
            with self.directory(rel) as fd:
                st=os.fstat(fd);need([st.st_dev,st.st_ino]==row["identity"][:2],"original boot directory replaced")
                need(stat.S_IMODE(st.st_mode)==stat.S_IMODE(row["identity"][2]) and
                     bounded_xattrs(fd)==row["xattrs"],"original boot directory metadata changed")
        self.event("boot-files-rollback-completed",rebooted=False)



def protected_bundle(release_id):
    return STORE/"releases"/digest(release_id)

def apply(release_id):
    original_cold_authority()
    materials=candidate_material_binding(release_id)
    binding=actual_acceptance_binding(release_id)
    require_same_candidate(materials,binding)
    tx=PublicTransaction(Path("/"),protected_bundle(release_id),release_id)
    try:
        tx.install()
        return {"schema":"droidloom-cold-public-phase-v1","release_id":release_id,
                "public_files_verified":len(tx.files),"activated":False}
    finally:tx.close()

def rollback(release_id):
    original_cold_authority()
    tx=PublicTransaction(Path("/"),protected_bundle(release_id),release_id,existing=True)
    try:
        tx.rollback()
        return {"schema":"droidloom-cold-public-rollback-v1","release_id":release_id,
                "restored":True,"rebooted":False}
    finally:tx.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
    for name in ("inspect-materials","inspect-runtime","apply-public","rollback-public"):
        q=sub.add_parser(name);q.add_argument("--release",required=True)
        if name=="inspect-runtime":
            q.add_argument("--inputs",type=Path,required=True)
            q.add_argument("--inputs-sha256",required=True)
    a=p.parse_args()
    if a.command=="inspect-runtime":
        from cold_transaction import owned_runtime_observations
        pin=file_pin(a.inputs);need(pin["sha256"]==digest(a.inputs_sha256),"fixed runtime inputs digest")
        result=owned_runtime_observations(candidate_material_binding(a.release),pin)
    else:
        result=(candidate_material_binding(a.release) if a.command=="inspect-materials" else
                apply(a.release) if a.command=="apply-public" else rollback(a.release))
    sys.stdout.buffer.write(canonical(result));sys.stdout.buffer.flush()

if __name__=="__main__":
    try:main()
    except (Rejected,OSError,ValueError,KeyError) as e:
        print("droidloom-cold-apply: "+str(e),file=sys.stderr);sys.exit(1)
