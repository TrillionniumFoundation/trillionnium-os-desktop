#!/usr/bin/python3
"""Combine the admitted native libraries/GDM and systemd normal package cohorts."""
import argparse
import hashlib
import io
import os
from pathlib import Path
import tarfile
from release import (need,exact,digest,canonical,safe_absolute,safe_relative,read_pin,
                     json_bytes,file_pin,new_file,copy_pin,mkdir_new,held,hash_fd,bounded_process)
import native_bundle as core
import systemd_bundle as systemd

SCHEMA="droidloom-normal-native-package-release-v2"
FULL_SCHEMA="droidloom-normal-native-package-release-v3"
COMPONENTS=("native-five","systemd")
CLOSURE_SHA=hashlib.sha256(canonical({"native_five":core.CLOSURE_SHA,
                                    "systemd":systemd.CLOSURE_SHA})).hexdigest()
APPARMOR_PACKAGES={
 "old":{"bytes":379516,"sha256":"8621170a44534ef32ab4f7e26a5cacabb2077a5a95bcb5236c0652f118032820"},
 "new":{"bytes":502050,"sha256":"a586b91b09dfafc0ac0ea1c3511acb147f986bc332865c99eb0e3ba4cd97c31b"},
}
FULL_COMPONENTS=(*COMPONENTS,"apparmor")
FULL_CLOSURE_SHA=hashlib.sha256(canonical({"native_five":core.CLOSURE_SHA,
    "systemd":systemd.CLOSURE_SHA,"apparmor":APPARMOR_PACKAGES})).hexdigest()

def apparmor_scripts(old,new):
    """Only exact normal dh_apparmor version comments differ; no shell changes."""
    for name in ("config","triggers","conffiles","templates","preinst","postinst","prerm","postrm"):
        a=old.get(name);b=new.get(name)
        if name in ("postinst","postrm"):
            before=("# Automatically added by dh_apparmor/"+core.OLD["apparmor"]).encode()
            after=("# Automatically added by dh_apparmor/"+core.NEW["apparmor"]).encode()
            need(isinstance(a,bytes) and isinstance(b,bytes),"normal apparmor maintainer script missing")
            al=a.splitlines(keepends=True);bl=b.splitlines(keepends=True)
            need(al.count(before+b"\n")==bl.count(after+b"\n")==2,
                 "exact normal dh_apparmor comment count")
            b=b"".join(before+b"\n" if line==after+b"\n" else line for line in bl)
        need(a==b,"apparmor configuration or executable maintainer script changed")

def apparmor_source(directory,index,root):
    names=index["source_names"]["apparmor"]
    real="apparmor_"+core.NEW["apparmor"]+"_amd64.deb"
    for extension in (".changes",".buildinfo"):
        matching=[name for name in names if name.endswith(extension)]
        need(len(matching)==1,"one actual normal AppArmor build record")
        alias=names[matching[0]]
        raw=read_pin(core.material_pin(directory,alias,index["files"][alias]),16*1024*1024,root)
        fields=core.deb822(raw)
        need(fields.get("Source")=="apparmor" and fields.get("Version")==core.NEW["apparmor"]
             and core.sha_rows(fields).get(real)==APPARMOR_PACKAGES["new"],
             "apparmor package is not the same normal libapparmor source build")

def archive_inventory(pin):
    """Read the complete fixed normal archive; never extract or run its scripts."""
    result={}
    with held(pin["path"],maximum=16*1024*1024) as (fd,st):
        need((st.st_size,hash_fd(fd))==(pin["bytes"],pin["sha256"]),"fixed apparmor archive changed")
        for key,option in (("control","--ctrl-tarfile"),("payload","--fsys-tarfile")):
            os.lseek(fd,0,os.SEEK_SET)
            actual=bounded_process(["/usr/bin/dpkg-deb",option,f"/proc/self/fd/{fd}"],
                seconds=60,maximum=core.MAX_TAR,pass_fds=(fd,))
            need(actual["exit"]==0,"normal AppArmor archive read failed")
            with tarfile.open(fileobj=io.BytesIO(actual["stdout"]),mode="r:") as archive:
                names=set()
                for member in archive:
                    name=member.name.removeprefix("./")
                    if member.isdir():name=name.rstrip("/")
                    if name not in ("", "."):names.add(name)
                    need(len(names)<=2048,"normal AppArmor archive member bound")
            rows,_=core.tar_rows(actual["stdout"],names)
            result[key]=rows if key=="control" else [rows[name] for name in sorted(rows)]
    return result

def verify_apparmor(directory,native_index,root):
    apparmor_source(directory/"native-five",native_index,root)
    area=directory/"apparmor"
    expected={"apparmor-"+kind+suffix for kind in ("old","new")
              for suffix in (".deb","-inventory.json")}
    need(set(p.name for p in area.iterdir())==expected,"exact complete AppArmor component")
    packages={};payloads={};record={"role":"apparmor","name":"apparmor","source":"apparmor",
        "old_version":core.OLD["apparmor"],"new_version":core.NEW["apparmor"]}
    for kind in ("old","new"):
        package=file_pin(area/("apparmor-"+kind+".deb"))
        need({k:package[k] for k in ("bytes","sha256")}==APPARMOR_PACKAGES[kind],
             "fixed original/candidate AppArmor package")
        ip=file_pin(area/("apparmor-"+kind+"-inventory.json"))
        inventory=json_bytes(read_pin(ip,4*1024*1024,root))
        packages[kind]=package
        payloads[kind]=core.package_contents(package,inventory,"apparmor",kind,root)
        record[kind]={key:{"path":"apparmor/"+Path(pin["path"]).name,
                     "bytes":pin["bytes"],"sha256":pin["sha256"]}
                     for key,pin in (("package",package),("inventory",ip))}
    apparmor_scripts(payloads["old"]["control_bodies"],payloads["new"]["control_bodies"])
    return record,packages,payloads

def relative_pin(directory,relative,row):
    safe_relative(relative)
    return {"path":str(directory/relative),"bytes":row["bytes"],"sha256":row["sha256"]}

def component_roles(subdir,index,payloads):
    records=[]
    roles=core.ROLES if subdir=="native-five" else systemd.NAMES
    for role in roles:
        old=payloads[role]["old"]["control"];new=payloads[role]["new"]["control"]
        record={"role":role,"name":new["Package"],"source":new.get("Source",new["Package"]).split()[0],
                "old_version":old["Version"],"new_version":new["Version"]}
        for kind in ("old","new"):
            if subdir=="native-five":
                package=index["roles"][role][kind]["package"]
                inventory=index["roles"][role][kind]["inventory"]
            else:
                package=role+"-"+kind+".deb";inventory=role+"-"+kind+"-inventory.json"
            record[kind]={}
            for key,name in (("package",package),("inventory",inventory)):
                p=index["files"][name]
                record[kind][key]={"path":subdir+"/"+name,"bytes":p["bytes"],"sha256":p["sha256"]}
        records.append(record)
    return records

def verify_components(directory,components,root,full=False):
    need(set(components)==set(FULL_COMPONENTS if full else COMPONENTS),"fixed native source components")
    packages={};payloads={};roles=[];index_by_component={}
    for subdir,module in (("native-five",core),("systemd",systemd)):
        c=components[subdir];exact(c,{"directory","release_id"},"normal native component")
        need(c["directory"]==subdir,"fixed component directory")
        index,closure,p,body=module.verify_bundle(directory/subdir,c["release_id"],root)
        need(not(set(packages)&set(p)),"overlapping package role components")
        packages.update(p);payloads.update(body)
        roles.extend(component_roles(subdir,index,body))
        index_by_component[subdir]=index
    if full:
        need(components["apparmor"]=={"directory":"apparmor"},"fixed AppArmor component directory")
        row,p,body=verify_apparmor(directory,index_by_component["native-five"],root)
        roles.append(row);packages["apparmor"]=p;payloads["apparmor"]=body
    count=16 if full else 15
    need(len(roles)==count and len({x["name"] for x in roles})==count,"exact normal native package closure")
    return roles,packages,payloads,index_by_component

def verify_bundle(directory,release_id,root=False):
    directory=safe_absolute(str(directory));digest(release_id)
    release=json_bytes(read_pin(file_pin(directory/"NATIVE-RELEASE.json"),1024*1024,root))
    if release.get("schema")==core.SCHEMA:
        index,closure,packages,payloads=core.verify_bundle(directory,release_id,root)
        index={**index,"closure_sha256":core.CLOSURE_SHA}
        return index,closure,packages,payloads
    full=release.get("schema")==FULL_SCHEMA
    need(release.get("schema") in (SCHEMA,FULL_SCHEMA) and release.get("release_id")==release_id,
         "normal native combined release identity")
    descriptor={k:v for k,v in release.items() if k!="release_id"}
    exact(descriptor,{"schema","components","closure_sha256","package_names","package_roles","files",
                      "normal_archives_verified","whole_payload_verified","package_database_modified",
                      "physical_install","runtime_qualified"},"combined native release")
    need(hashlib.sha256(canonical(descriptor)).hexdigest()==release_id
         and descriptor["closure_sha256"]==(FULL_CLOSURE_SHA if full else CLOSURE_SHA),"same native source release digest")
    need(descriptor["physical_install"] is False and descriptor["runtime_qualified"] is False
         and descriptor["package_database_modified"] is False,"materials are not activation authority")
    components=FULL_COMPONENTS if full else COMPONENTS
    need(set(p.name for p in directory.iterdir())==set(components)|{"NATIVE-RELEASE.json"},
         "unexpected combined native release root member")
    roles,packages,payloads,indices=verify_components(directory,descriptor["components"],root,full)
    need(roles==descriptor["package_roles"] and [x["name"] for x in roles]==descriptor["package_names"],
         "source-owned combined normal package role declarations")
    actual_files=[]
    for subdir in components:
        for p in sorted((directory/subdir).iterdir()):
            fp=file_pin(p)
            actual_files.append({"path":subdir+"/"+p.name,"bytes":fp["bytes"],"sha256":fp["sha256"]})
    expected=sorted(actual_files,key=lambda x:x["path"])
    need(expected==descriptor["files"],"complete combined native file inventory")
    for row in expected:
        read_pin(relative_pin(directory,row["path"],row),64*1024*1024,root)
    return descriptor,{"package_roles":roles,"closure_sha256":descriptor["closure_sha256"]},packages,payloads

def prepare(core_directory,core_id,systemd_directory,systemd_id,output,apparmor_old,apparmor_new):
    core_directory=safe_absolute(str(core_directory));systemd_directory=safe_absolute(str(systemd_directory))
    output=safe_absolute(str(output))
    core.verify_bundle(core_directory,core_id);systemd.verify_bundle(systemd_directory,systemd_id)
    mkdir_new(output)
    for name,source in (("native-five",core_directory),("systemd",systemd_directory)):
        target=output/name;mkdir_new(target)
        for p in sorted(source.iterdir()):copy_pin(file_pin(p),target/p.name,0o444)
    components={"native-five":{"directory":"native-five","release_id":core_id},
                "systemd":{"directory":"systemd","release_id":systemd_id}}
    area=output/"apparmor";mkdir_new(area)
    for kind,path in (("old",apparmor_old),("new",apparmor_new)):
        pin=file_pin(safe_absolute(str(path)))
        need({k:pin[k] for k in ("bytes","sha256")}==APPARMOR_PACKAGES[kind],"fixed normal AppArmor input")
        target=area/("apparmor-"+kind+".deb")
        copy_pin(pin,target,0o444)
        inventory=archive_inventory(file_pin(target))
        core.package_contents(file_pin(target),inventory,"apparmor",kind)
        new_file(area/("apparmor-"+kind+"-inventory.json"),canonical(inventory))
    components["apparmor"]={"directory":"apparmor"}
    roles,_,_,_=verify_components(output,components,False,True)
    files=[]
    for subdir in FULL_COMPONENTS:
        for p in sorted((output/subdir).iterdir()):
            fp=file_pin(p);files.append({"path":subdir+"/"+p.name,"bytes":fp["bytes"],"sha256":fp["sha256"]})
    descriptor={"schema":FULL_SCHEMA,"components":components,"closure_sha256":FULL_CLOSURE_SHA,
                "package_names":[x["name"] for x in roles],"package_roles":roles,
                "files":sorted(files,key=lambda x:x["path"]),"normal_archives_verified":True,
                "whole_payload_verified":True,"package_database_modified":False,
                "physical_install":False,"runtime_qualified":False}
    release_id=hashlib.sha256(canonical(descriptor)).hexdigest()
    new_file(output/"NATIVE-RELEASE.json",canonical({"release_id":release_id,**descriptor}))
    verify_bundle(output,release_id)
    return {"release_id":release_id,"receipt":file_pin(output/"NATIVE-RELEASE.json"),
            "package_count":16,"rollback_package_count":16,"runtime_qualified":False}

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest="command",required=True)
    a=s.add_parser("prepare")
    for arg in ("core","systemd","output","apparmor-old","apparmor-new"):
        a.add_argument("--"+arg,type=Path,required=True)
    a.add_argument("--core-release-id",required=True);a.add_argument("--systemd-release-id",required=True)
    a=s.add_parser("verify");a.add_argument("--bundle",type=Path,required=True);a.add_argument("--release-id",required=True)
    a=p.parse_args()
    if a.command=="prepare":r=prepare(a.core,a.core_release_id,a.systemd,a.systemd_release_id,
                                    a.output,a.apparmor_old,a.apparmor_new)
    else:verify_bundle(a.bundle,a.release_id);r={"verified":True,"release_id":a.release_id,"runtime_qualified":False}
    print(canonical(r).decode(),end="")
if __name__=="__main__":main()
