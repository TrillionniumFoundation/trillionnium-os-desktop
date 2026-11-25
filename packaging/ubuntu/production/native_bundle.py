#!/usr/bin/python3
"""Closed normal Debian materials for the five native runtime packages.

This prepares and verifies public build inputs. It performs no installation,
does not manufacture a package database, and grants no runtime qualification.
"""
import argparse
import hashlib
import io
import os
from pathlib import Path
import posixpath
import re
import tarfile
from release import (
    need, exact, digest, canonical, safe_relative, safe_absolute, held, hash_fd,
    read_pin, json_bytes, file_pin, new_file, copy_pin, mkdir_new,
    bounded_process, Rejected,
)

CLOSURE_SHA="6efe392551d6244491ca4cafc3b83c05feca6a4d5d4c82df9b145d5779a248e0"
CLOSURE_BYTES=53678
MATERIALS_SHA="7bf3bfa35edecec628d482c24b086a03ad596efd0aa3b2f211e64332c15251d4"
SCHEMA="droidloom-normal-native-package-release-v1"
ROLES=("libselinux","libapparmor","libgdm","gir","gdm")
NAMES={"libselinux":"libselinux1","libapparmor":"libapparmor1",
       "libgdm":"libgdm1","gir":"gir1.2-gdm-1.0","gdm":"gdm3","apparmor":"apparmor"}
OLD={"libselinux":"3.9-4build1","libapparmor":"5.0.2-0ubuntu1~26.04.1",
     "libgdm":"50.1-0ubuntu0.1","gir":"50.1-0ubuntu0.1","gdm":"50.1-0ubuntu0.1",
     "apparmor":"5.0.2-0ubuntu1~26.04.1"}
NEW={"libselinux":"3.9-4build1+p4lsmexec4",
     "libapparmor":"5.0.2-0ubuntu1~26.04.1+p4peer1",
     "libgdm":"50.1-0ubuntu0.1+p4fsuser3","gir":"50.1-0ubuntu0.1+p4fsuser3",
     "gdm":"50.1-0ubuntu0.1+p4fsuser3","apparmor":"5.0.2-0ubuntu1~26.04.1+p4peer1"}
PROJECTS={"libselinux":"libselinux","libapparmor":"apparmor",
          "libgdm":"gdm3","gir":"gdm3","gdm":"gdm3","apparmor":"apparmor"}
MAX_MEMBER=16*1024*1024
MAX_TAR=32*1024*1024
CONTROL_FIELDS=("Package","Version","Architecture","Source")

def material_pin(directory,name,row):
    need(isinstance(name,str) and Path(name).name==name,"flat public material")
    safe_relative(name)
    return {"path":str(directory/name),"bytes":row["bytes"],"sha256":row["sha256"]}

def deb822(raw):
    need(isinstance(raw,bytes) and len(raw)<=1024*1024,"control size")
    text=raw.decode("utf-8","strict")
    need("\0" not in text and "\r" not in text,"control encoding")
    fields={};last=None
    for line in text.splitlines():
        if not line:
            continue
        if line[:1] in (" ","\t"):
            need(last is not None,"orphan folded control line")
            fields[last]+="\n"+line[1:]
            continue
        need(":" in line and not line.startswith("-----"),"plain normal Debian control")
        key,value=line.split(":",1)
        need(re.fullmatch(r"[A-Za-z0-9-]+",key) and key not in fields,"duplicate control field")
        fields[key]=value.lstrip();last=key
    return fields

def sha_rows(fields):
    need("Checksums-Sha256" in fields,"normal Debian source checksum table")
    result={}
    for line in fields["Checksums-Sha256"].splitlines():
        if not line.strip():continue
        pieces=line.split()
        need(len(pieces)==3,"Debian SHA256 tuple")
        sha,size,name=pieces;digest(sha)
        need(size.isdecimal() and 0<int(size)<128*1024*1024,"Debian source size")
        need(Path(name).name==name and name not in result and "\0" not in name,"Debian source basename")
        result[name]={"bytes":int(size),"sha256":sha}
    need(bool(result),"empty normal source checksums")
    return result

def tar_rows(raw,permitted):
    need(len(raw)<=MAX_TAR,"normal Debian stream bound")
    result={};bodies={};root=False
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:") as tar:
        for member in tar:
            name=member.name
            if name in (".","./"):
                need(not root and member.isdir(),"one archive root directory")
                root=True;continue
            if name.startswith("./"):name=name[2:]
            name=name.rstrip("/") if member.isdir() else name
            need(name in permitted and 0<len(name)<=300 and not name.startswith("/") and
                 all(part not in ("",".","..") for part in name.split("/")) and
                 all(32<=ord(c)<127 for c in name),"exact reviewed native archive pathname")
            need(name not in result and len(result)<2048,"normal Debian member uniqueness/bound")
            need(not member.pax_headers and not member.sparse,"ordinary fixed archive format")
            need(member.uid==member.gid==0,"native package public root owner")
            need(0<=member.size<=MAX_MEMBER,"native package member bound")
            row={"path":name,"type":member.type.decode("ascii"),"mode":member.mode,
                 "uid":member.uid,"gid":member.gid,"bytes":member.size}
            if member.isfile():
                body=tar.extractfile(member).read(MAX_MEMBER+1)
                need(len(body)==member.size,"normal package full body")
                row["sha256"]=hashlib.sha256(body).hexdigest();bodies[name]=body
            elif member.issym():
                target=member.linkname
                need(member.size==0 and 0<len(target)<=4096 and "\0" not in target and
                     all(ord(c)>=32 and ord(c)<127 for c in target),"normal public alias")
                # Package-root semantics, never the build host's Path.resolve.
                virtual=posixpath.normpath(target if target.startswith("/") else "/"+posixpath.join(posixpath.dirname(name),target))
                need(virtual.startswith("/") and not virtual.startswith("//"),"alias inside virtual package root")
                row["target"]=target
            else:
                need(member.isdir() and member.size==0,"no device/hardlink/special native payload")
            result[name]=row
        end=tar.offset
    need(not any(raw[end:]),"nonzero trailing native archive bytes")
    # An earlier symlink cannot be used as an output parent by this payload.
    aliases={p for p,x in result.items() if x["type"]=="2"}
    for name in result:
        parts=name.split("/")
        need(not any("/".join(parts[:n]) in aliases for n in range(1,len(parts))),
             "native package traverses an output alias")
    return result,bodies

def package_contents(pin,inventory,role,kind,root=False):
    # The old five-package materials remain byte-identical. The combined v3
    # publisher separately admits the same normal source's apparmor package.
    need(kind in ("old","new") and role in NAMES,"native package role")
    with held(pin["path"],root=root,maximum=16*1024*1024) as (fd,st):
        need((st.st_size,hash_fd(fd))==(pin["bytes"],pin["sha256"]),"native package bytes changed")
        controls=bounded_process(["/usr/bin/dpkg-deb","--ctrl-tarfile",f"/proc/self/fd/{fd}"],
                                 seconds=60,maximum=MAX_TAR,pass_fds=(fd,))
        need(controls["exit"]==0,"normal dpkg-deb control read failed")
        control_rows,control_body=tar_rows(controls["stdout"],set(inventory["control"]))
        need(control_rows==inventory["control"],"every actual native control member must match")
        os.lseek(fd,0,os.SEEK_SET)
        payload=bounded_process(["/usr/bin/dpkg-deb","--fsys-tarfile",f"/proc/self/fd/{fd}"],
                                seconds=60,maximum=MAX_TAR,pass_fds=(fd,))
        need(payload["exit"]==0,"normal dpkg-deb data read failed")
        rows,_=tar_rows(payload["stdout"],{x["path"] for x in inventory["payload"]})
        expected={x["path"]:x for x in inventory["payload"]}
        need(len(expected)==len(inventory["payload"]) and rows==expected,"whole native payload differs")
        control=deb822(control_body["control"])
        need(control.get("Package")==NAMES[role] and control.get("Version")==(OLD if kind=="old" else NEW)[role]
             and control.get("Architecture")=="amd64","fixed native package identity")
        source=control.get("Source",NAMES[role]).split()[0]
        need(source==PROJECTS[role],"normal source package relation")
        return {"control":control,"payload":rows,"control_bodies":control_body}

def verify_materials(directory,root=False):
    directory=safe_absolute(str(directory))
    index_path=directory/"NATIVE-MATERIALS.json"
    ip=file_pin(index_path)
    need(ip["sha256"]==MATERIALS_SHA,"fixed normal native material index")
    index=json_bytes(read_pin(ip,1024*1024,root))
    need(index.get("schema")=="p4-normal-native-public-materials-v1" and
         index.get("original_account_data_included") is False,"native public source scope")
    need(set(index["roles"])==set(ROLES) and len(index["files"])==50,"fixed five-package closure")
    need(set(p.name for p in directory.iterdir()) in
         (set(index["files"])|{"NATIVE-MATERIALS.json"},
          set(index["files"])|{"NATIVE-MATERIALS.json","NATIVE-RELEASE.json"}),"unexpected native bundle member")
    for name,row in index["files"].items():
        p=material_pin(directory,name,row)
        read_pin(p,16*1024*1024,root)
    closure=json_bytes(read_pin({"path":str(directory/"CLOSURE.json"),
                                "bytes":CLOSURE_BYTES,"sha256":CLOSURE_SHA},1024*1024,root))
    need(closure.get("schema")=="p4-normal-native-five-package-closure-v1" and
         closure.get("runtime_elf_count")==11 and
         closure.get("whole_deb_runtime_qualified") is False and
         closure.get("physical_install") is False,"original native source declaration")
    packages={};payloads={}
    for role in ROLES:
        declaration=closure["package_roles"][role]
        need(declaration["package_name"]==NAMES[role] and
             not declaration["configuration_or_maintainer_script_changes"],"reviewed native role")
        packages[role]={};payloads[role]={}
        for kind in ("old","new"):
            entry=index["roles"][role][kind];row=declaration[kind]
            p=material_pin(directory,entry["package"],index["files"][entry["package"]])
            need((p["bytes"],p["sha256"])==(row["package"]["bytes"],row["package"]["sha256"]),"closure package pin")
            invpin=material_pin(directory,entry["inventory"],index["files"][entry["inventory"]])
            need((invpin["bytes"],invpin["sha256"])==(row["inventory"]["bytes"],row["inventory"]["sha256"]),
                 "closure inventory pin")
            inv=json_bytes(read_pin(invpin,1024*1024,root))
            packages[role][kind]=p
            payloads[role][kind]=package_contents(p,inv,role,kind,root)
    verify_sources(directory,index,closure,root)
    return index,closure,packages,payloads

def verify_sources(directory,index,closure,root):
    for project in ("libselinux","apparmor","gdm3"):
        names=index["source_names"][project]
        def source(name):
            alias=names[name];p=material_pin(directory,alias,index["files"][alias])
            original=closure["source_proofs"][project][name]
            need((p["bytes"],p["sha256"])==(original["bytes"],original["sha256"]),"source proof identity")
            return read_pin(p,16*1024*1024,root)
        dsc_names=[n for n in names if n.endswith(".dsc") and "+p4" in n]
        changes_names=[n for n in names if n.endswith(".changes")]
        info_names=[n for n in names if n.endswith(".buildinfo")]
        need(len(dsc_names)==len(changes_names)==len(info_names)==1,"one normal native source build")
        dsc=deb822(source(dsc_names[0]));changes=deb822(source(changes_names[0]));info=deb822(source(info_names[0]))
        roles=[r for r in ROLES if PROJECTS[r]==project];version=NEW[roles[0]]
        need(all(f.get("Version")==version and f.get("Source","").split()[0]==project
                 for f in (dsc,changes,info)),"same normal source/version across build records")
        ds=sha_rows(dsc);cs=sha_rows(changes);bs=sha_rows(info)
        for name,row in ds.items():
            need(name in names,"source archive omitted from closure")
            alias=names[name];p=index["files"][alias]
            need((row["bytes"],row["sha256"])==(p["bytes"],p["sha256"]),"DSC archive identity")
            source(name)
        for name in (dsc_names[0],info_names[0]):
            need(name in cs,"normal changes lacks source/buildinfo")
            p=index["files"][names[name]]
            need((cs[name]["bytes"],cs[name]["sha256"])==(p["bytes"],p["sha256"]),"normal changes source checksum")
        for role in roles:
            original=closure["package_roles"][role]["new"]["package"]
            name=Path(original["path"]).name
            need(name in cs and name in bs,"normal changes/buildinfo lacks runtime package")
            for table in (cs,bs):
                need((table[name]["bytes"],table[name]["sha256"])==(original["bytes"],original["sha256"]),
                     "normal runtime output checksum")
        receipt=json_bytes(source("build-result.json"))
        if project=="libselinux":
            commands=receipt.get("commands",[])
            need(receipt.get("success") is True and receipt.get("candidate_version")==version
                 and len(commands)>=5 and all(x.get("exit_code")==0 for x in commands)
                 and any(x.get("name")=="build" and "dpkg-buildpackage" in x.get("argv",[]) for x in commands),
                 "completed normal libselinux build")
        elif project=="apparmor":
            need(receipt.get("exit_code")==0 and receipt.get("candidate_version")==version and
                 receipt.get("tests_disabled") is False and "dpkg-buildpackage" in receipt.get("argv",[]),
                 "completed normal libapparmor build")
        else:
            need(receipt.get("exit_code")==0 and receipt.get("source_roundtrip_verified") is True and
                 receipt.get("canonical_source_unchanged") is True and receipt.get("frozen_source_unchanged") is True,
                 "completed normal GDM source build")
            need(receipt.get("source_commit")==closure["gdm_same_normal_build"]["commit"],
                 "GDM normal source commit")
            for role in roles:
                p=closure["package_roles"][role]["new"]["package"]
                need(receipt["outputs"][Path(p["path"]).name]=={"bytes":p["bytes"],"sha256":p["sha256"]},
                     "GDM same build package closure")

def prepare(materials,output):
    index,closure,packages,payloads=verify_materials(materials)
    output=safe_absolute(str(output));mkdir_new(output)
    for name,row in index["files"].items():
        copy_pin(material_pin(materials,name,row),output/name,0o444)
    copy_pin(file_pin(materials/"NATIVE-MATERIALS.json"),output/"NATIVE-MATERIALS.json",0o444)
    descriptor={"schema":SCHEMA,"closure_sha256":CLOSURE_SHA,"material_index_sha256":MATERIALS_SHA,
                "package_names":[NAMES[r] for r in ROLES],"runtime_elf_count":11,
                "files":[{"path":p.name,"bytes":file_pin(p)["bytes"],"sha256":file_pin(p)["sha256"]}
                         for p in sorted(output.iterdir())],"normal_archives_verified":True,
                "whole_payload_verified":True,"package_database_modified":False,
                "physical_install":False,"runtime_qualified":False}
    release_id=hashlib.sha256(canonical(descriptor)).hexdigest()
    new_file(output/"NATIVE-RELEASE.json",canonical({"release_id":release_id,**descriptor}))
    verify_bundle(output,release_id)
    return {"release_id":release_id,"receipt":file_pin(output/"NATIVE-RELEASE.json"),
            "package_count":5,"rollback_package_count":5,"runtime_qualified":False}

def verify_bundle(directory,release_id,root=False):
    digest(release_id)
    path=directory/"NATIVE-RELEASE.json"
    rp=file_pin(path);release=json_bytes(read_pin(rp,1024*1024,root))
    need(release.get("release_id")==release_id and release.get("schema")==SCHEMA,"native release identity")
    descriptor={k:v for k,v in release.items() if k!="release_id"}
    need(hashlib.sha256(canonical(descriptor)).hexdigest()==release_id,"native release digest")
    need(descriptor.get("closure_sha256")==CLOSURE_SHA and descriptor.get("material_index_sha256")==MATERIALS_SHA
         and descriptor.get("runtime_qualified") is False and descriptor.get("physical_install") is False,
         "normal native release remains unqualified")
    for row in descriptor["files"]:
        read_pin(material_pin(directory,row["path"],row),16*1024*1024,root)
    return verify_materials(directory,root)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("prepare");p.add_argument("--materials",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    v=sub.add_parser("verify");v.add_argument("--bundle",type=Path,required=True);v.add_argument("--release-id",required=True)
    args=parser.parse_args()
    if args.command=="prepare":result=prepare(args.materials,args.output)
    else:
        verify_bundle(args.bundle,args.release_id)
        result={"verified":True,"release_id":args.release_id,"runtime_qualified":False}
    print(canonical(result).decode(),end="")
if __name__=="__main__":
    main()
