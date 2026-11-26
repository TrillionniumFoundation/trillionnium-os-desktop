#!/usr/bin/python3
"""Pinned normal systemd packages and their original rollback archives."""
import argparse
import hashlib
import os
from pathlib import Path
from release import (need,exact,digest,canonical,safe_absolute,held,hash_fd,read_pin,
                     json_bytes,file_pin,new_file,copy_pin,mkdir_new,bounded_process)
from native_bundle import material_pin,deb822,sha_rows,tar_rows

NAMES=("systemd","systemd-sysv","systemd-timesyncd","libpam-systemd",
       "libnss-systemd","libsystemd0","libsystemd-shared","udev","libudev1",
       "systemd-resolved")
OLD="259.9-0ubuntu0.1"
NEW=OLD+"+p4gentmp2"
CLOSURE_SHA="d2d5721e51a7f5f277efff8a2203c03da5edf4e6055522f4374e99111c798755"
CLOSURE_BYTES=182043
BUILD_SHA="bcc3464689e33ab645a8372aec6cd0ce38e0e7f21dae22a8ef9a0be5b3e3c88c"
BUILD_BYTES=115885
SCHEMA="droidloom-systemd-native-package-release-v1"
INDEX_SCHEMA="droidloom-systemd-native-materials-v1"
PROOF_NAMES=("build-result.json","build-command.json","build.stdout","build.stderr",
             "source-lock.json","source-delta.json","normal.changes","normal.buildinfo",
             "systemd-new.dsc","systemd.orig.tar.gz","systemd-new.debian.tar.xz",
             "systemd-old.dsc","systemd-old.debian.tar.xz")
ORIGINAL_SOURCE={
 "systemd-old.dsc":(8779,"17ad848e882b6b91ac0d31300181bb4ec6b221077329b0c5296c9765cce769b5"),
 "systemd.orig.tar.gz":(17618264,"6ac77a1baf0539b835193eec46cdb1c73abb42d7f87aa977009150e9d8375757"),
 "systemd-old.debian.tar.xz":(254204,"c58ab8296f580f8760afc945261917fa23dfb62df8a78121a5967c5b237a24cc"),
}

CONFIGURED_DIRECTORY_RULES=("etc/credstore","etc/credstore.encrypted")
CREDSTORE_RULE_FILE="usr/lib/tmpfiles.d/credstore.conf"
CREDSTORE_RULE_BYTES=474
CREDSTORE_RULE_SHA="2bafed09323dcb75c9c59ffd863510c2d05b6939fbcda267a82198875d1b4ddb"

def configured_row(role,kind,path,row,payloads):
    # The unchanged stock postinst runs the unchanged credstore tmpfiles rule.
    # Both installed versions therefore require 0700, rather than the 0755
    # archive placeholder. No other configured metadata is exempted.
    if role!="systemd" or path not in CONFIGURED_DIRECTORY_RULES:
        return row
    need(row["type"]=="5" and row["mode"]==0o755 and row["uid"]==row["gid"]==0,
         "original credstore archive directory")
    source=payloads["systemd"][kind]["payload"][CREDSTORE_RULE_FILE]
    need(source["type"]=="0" and (source["bytes"],source["sha256"])==
         (CREDSTORE_RULE_BYTES,CREDSTORE_RULE_SHA),"exact stock credstore rule source")
    postinst=payloads["systemd"][kind]["control_bodies"]["postinst"]
    need(b"systemd-tmpfiles" in postinst and b"credstore.conf" in postinst,
         "stock systemd configure invokes the credstore rule")
    return {**row,"mode":0o700}

def package_contents(pin,inventory,name,kind,root):
    with held(pin["path"],root=root,maximum=16*1024*1024) as (fd,st):
        need((st.st_size,hash_fd(fd))==(pin["bytes"],pin["sha256"]),
             "held normal systemd archive changed")
        controls=bounded_process(["/usr/bin/dpkg-deb","--ctrl-tarfile",f"/proc/self/fd/{fd}"],
                                 seconds=60,maximum=32*1024*1024,pass_fds=(fd,))
        need(controls["exit"]==0,"normal systemd control archive read")
        cr,cb=tar_rows(controls["stdout"],set(inventory["control"]))
        need(cr==inventory["control"],"systemd control member identity")
        os.lseek(fd,0,os.SEEK_SET)
        payload=bounded_process(["/usr/bin/dpkg-deb","--fsys-tarfile",f"/proc/self/fd/{fd}"],
                                seconds=60,maximum=32*1024*1024,pass_fds=(fd,))
        need(payload["exit"]==0,"normal systemd payload archive read")
        rows,_=tar_rows(payload["stdout"],{x["path"] for x in inventory["payload"]})
        expected={x["path"]:x for x in inventory["payload"]}
        need(len(expected)==len(inventory["payload"]) and rows==expected,
             "complete systemd payload identity")
        control=deb822(cb["control"])
        need(control.get("Package")==name and control.get("Version")==(OLD if kind=="old" else NEW)
             and control.get("Architecture")=="amd64","fixed systemd binary package")
        need(control.get("Source",name).split()[0]=="systemd","same normal systemd source package")
        return {"control":control,"payload":rows,"control_bodies":cb}

def source_fields(raw):
    # Preserve and pin the original signed DSC bytes; only decode its cleartext
    # for the source archive checksum relationship already authenticated by APT.
    if raw.startswith(b"-----BEGIN PGP SIGNED MESSAGE-----\n"):
        head,sep,tail=raw.partition(b"\n\n")
        need(sep and head==b"-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512",
             "fixed original DSC clear-sign envelope")
        body,sep,signature=tail.partition(b"-----BEGIN PGP SIGNATURE-----\n")
        need(sep and signature.rstrip().endswith(b"-----END PGP SIGNATURE-----"),
             "complete original DSC signature envelope")
        raw=b"\n".join(line[2:] if line.startswith(b"- ") else line for line in body.split(b"\n"))
    return deb822(raw)

def verify_sources(directory,index,build,root):
    def proof(name):
        return read_pin(material_pin(directory,name,index["files"][name]),64*1024*1024,root)
    for name,wanted in ORIGINAL_SOURCE.items():
        p=index["files"][name]
        need((p["bytes"],p["sha256"])==wanted,"original Ubuntu systemd source pin")
        proof(name)
    mapped={
        "build-command.json":build["normal_build_receipt"],
        "build.stdout":build["normal_build"]["stdout"],
        "build.stderr":build["normal_build"]["stderr"],
        "source-lock.json":build["source_lock"],"source-delta.json":build["source_delta"],
        "normal.changes":build["changes"],"normal.buildinfo":build["buildinfo"],
        "systemd-new.dsc":build["source_dsc"],
    }
    source_rows={Path(x["path"]).name:x for x in build["source_checksum_table"]}
    mapped["systemd.orig.tar.gz"]=source_rows["systemd_259.9.orig.tar.gz"]
    mapped["systemd-new.debian.tar.xz"]=source_rows["systemd_"+NEW+".debian.tar.xz"]
    for name,wanted in mapped.items():
        p=index["files"][name]
        need((p["bytes"],p["sha256"])==(wanted["bytes"],wanted["sha256"]),
             "normal systemd build source/proof changed")
        proof(name)
    command=json_bytes(proof("build-command.json"))
    need(command.get("exit_code")==0 and build["normal_build_exit_code"]==0,
         "normal systemd build was not successful")
    need(build["normal_tests"]=={"failed":0,"passed":1415,"stock_skipped":39,"tests_disabled":False},
         "original normal systemd test evidence")
    need(build["parent_git_commit"]=="2601488570f379847a9b6785de76d451dcb5b789"
         and build["source_version"]==NEW and build["original_source_version"]==OLD,
         "reviewed systemd patch/version source")
    for kind,version,alias in (("old",OLD,"systemd-old.dsc"),("new",NEW,"systemd-new.dsc")):
        fields=source_fields(proof(alias))
        need(fields.get("Source")=="systemd" and fields.get("Version")==version,
             "normal systemd DSC identity")
        table=sha_rows(fields)
        expected={"systemd_259.9.orig.tar.gz":"systemd.orig.tar.gz",
                  "systemd_"+version+".debian.tar.xz":"systemd-"+kind+".debian.tar.xz"}
        need(set(table)==set(expected),"complete ordinary systemd DSC sources")
        for name,dest in expected.items():
            p=index["files"][dest]
            need(table[name]=={"bytes":p["bytes"],"sha256":p["sha256"]},"DSC archive full identity")
    changes=deb822(proof("normal.changes"));info=deb822(proof("normal.buildinfo"))
    need(all(x.get("Source","").split()[0]=="systemd" and x.get("Version")==NEW
             for x in (changes,info)),"normal systemd changes/buildinfo identity")
    ct=sha_rows(changes);bt=sha_rows(info)
    for name in NAMES:
        pin=index["files"][name+"-new.deb"]
        real=name+"_"+NEW+"_amd64.deb"
        need(all(t.get(real)=={"bytes":pin["bytes"],"sha256":pin["sha256"]} for t in (ct,bt)),
             "runtime archive not from the normal source build")
    for real,alias in (("systemd_"+NEW+".dsc","systemd-new.dsc"),
                       ("systemd_"+NEW+"_amd64.buildinfo","normal.buildinfo")):
        p=index["files"][alias]
        need(ct.get(real)=={"bytes":p["bytes"],"sha256":p["sha256"]},
             "normal changes source record binding")

def verify_materials(directory,root=False):
    directory=safe_absolute(str(directory))
    index=json_bytes(read_pin(file_pin(directory/"SYSTEMD-MATERIALS.json"),1024*1024,root))
    exact(index,{"schema","files"},"systemd material index")
    need(index["schema"]==INDEX_SCHEMA,"systemd material schema")
    expected={"CLOSURE.json",*PROOF_NAMES}
    for name in NAMES:
        for kind in ("old","new"):
            expected|={name+"-"+kind+".deb",name+"-"+kind+"-inventory.json"}
    need(set(index["files"])==expected,"exact normal systemd material closure")
    need(set(p.name for p in directory.iterdir()) in
         (expected|{"SYSTEMD-MATERIALS.json"},expected|{"SYSTEMD-MATERIALS.json","NATIVE-RELEASE.json"}),
         "unexpected systemd material file")
    for name,row in index["files"].items():
        exact(row,{"bytes","sha256"},"systemd material pin")
        read_pin(material_pin(directory,name,row),64*1024*1024,root)
    cp=index["files"]["CLOSURE.json"]
    need((cp["bytes"],cp["sha256"])==(CLOSURE_BYTES,CLOSURE_SHA),"reviewed systemd package closure")
    closure=json_bytes(read_pin(material_pin(directory,"CLOSURE.json",cp),1024*1024,root))
    need(closure["schema"]=="p4-normal-systemd-native-package-closure-v1"
         and set(closure["package_roles"])==set(NAMES) and closure["package_names"]==list(NAMES)
         and closure["new_version"]==NEW and closure["original_version"]==OLD,
         "fixed normal systemd binary package set")
    bp=index["files"]["build-result.json"]
    need((bp["bytes"],bp["sha256"])==(BUILD_BYTES,BUILD_SHA),"normal systemd build receipt pin")
    build=json_bytes(read_pin(material_pin(directory,"build-result.json",bp),1024*1024,root))
    verify_sources(directory,index,build,root)
    packages={};payloads={}
    for name in NAMES:
        need(not closure["package_roles"][name]["configuration_delta"],
             "systemd native configuration change requires separate review")
        packages[name]={};payloads[name]={}
        for kind in ("old","new"):
            pp=name+"-"+kind+".deb";ip=name+"-"+kind+"-inventory.json"
            reference=closure["package_roles"][name][kind]
            for alias,original in ((pp,reference["package"]),(ip,reference["inventory"])):
                p=index["files"][alias]
                need((p["bytes"],p["sha256"])==(original["bytes"],original["sha256"]),
                     "source-bound systemd archive/inventory")
            p=material_pin(directory,pp,index["files"][pp])
            inv=json_bytes(read_pin(material_pin(directory,ip,index["files"][ip]),4*1024*1024,root))
            packages[name][kind]=p
            payloads[name][kind]=package_contents(p,inv,name,kind,root)
        old=payloads[name]["old"]["control_bodies"];new=payloads[name]["new"]["control_bodies"]
        for member in ("preinst","postinst","prerm","postrm","config","triggers","conffiles"):
            need(old.get(member)==new.get(member),"systemd maintainer script/config semantics changed")
    return index,closure,packages,payloads

def prepare(materials,output):
    materials=safe_absolute(str(materials));output=safe_absolute(str(output))
    index,_,_,_=verify_materials(materials)
    mkdir_new(output)
    for name,row in index["files"].items():
        copy_pin(material_pin(materials,name,row),output/name,0o444)
    copy_pin(file_pin(materials/"SYSTEMD-MATERIALS.json"),output/"SYSTEMD-MATERIALS.json",0o444)
    descriptor={"schema":SCHEMA,"closure_sha256":CLOSURE_SHA,"build_sha256":BUILD_SHA,
                "package_names":list(NAMES),"files":[{"path":p.name,"bytes":file_pin(p)["bytes"],
                "sha256":file_pin(p)["sha256"]} for p in sorted(output.iterdir())],
                "normal_archives_verified":True,"whole_payload_verified":True,
                "package_database_modified":False,"physical_install":False,"runtime_qualified":False}
    release_id=hashlib.sha256(canonical(descriptor)).hexdigest()
    new_file(output/"NATIVE-RELEASE.json",canonical({"release_id":release_id,**descriptor}))
    verify_bundle(output,release_id)
    return {"release_id":release_id,"receipt":file_pin(output/"NATIVE-RELEASE.json"),
            "package_count":len(NAMES),"runtime_qualified":False}

def verify_bundle(directory,release_id,root=False):
    digest(release_id);directory=safe_absolute(str(directory))
    release=json_bytes(read_pin(file_pin(directory/"NATIVE-RELEASE.json"),1024*1024,root))
    need(release.get("schema")==SCHEMA and release.get("release_id")==release_id,"systemd release identity")
    descriptor={k:v for k,v in release.items() if k!="release_id"}
    need(hashlib.sha256(canonical(descriptor)).hexdigest()==release_id,"systemd release digest")
    need(descriptor["closure_sha256"]==CLOSURE_SHA and descriptor["build_sha256"]==BUILD_SHA
         and descriptor["package_names"]==list(NAMES) and descriptor["runtime_qualified"] is False
         and descriptor["physical_install"] is False,"fixed normal systemd release")
    need(len(descriptor["files"])==len(set(x["path"] for x in descriptor["files"])),
         "duplicate systemd release files")
    for row in descriptor["files"]:
        read_pin(material_pin(directory,row["path"],row),64*1024*1024,root)
    return verify_materials(directory,root)

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest="command",required=True)
    a=s.add_parser("prepare");a.add_argument("--materials",type=Path,required=True);a.add_argument("--output",type=Path,required=True)
    a=s.add_parser("verify");a.add_argument("--bundle",type=Path,required=True);a.add_argument("--release-id",required=True)
    a=p.parse_args()
    if a.command=="prepare":r=prepare(a.materials,a.output)
    else:verify_bundle(a.bundle,a.release_id);r={"verified":True,"release_id":a.release_id,"runtime_qualified":False}
    print(canonical(r).decode(),end="")
if __name__=="__main__":main()
