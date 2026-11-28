#!/usr/bin/python3
"""Combine the admitted native libraries/GDM and systemd normal package cohorts."""
import argparse
import contextlib
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

# This is a separate physical-host profile. The complete fixture's sixteen
# package contract above is unchanged. The original host has six additional
# installed binaries from the same normal sources, including systemd-dev:all.
ORIGINAL_SCHEMA="droidloom-original-host-native-package-release-v1"
ORIGINAL_PROFILE="pocket4-original-installed-native-22-v1"
ORIGINAL_SIGNER="F6ECB3762474EDA9D21B7022871920D1991BC93C"
ORIGINAL_EXTRAS={
 "libselinux-dev":{"old":(175796,"300abd658047ee4aeeef8e120c1950d1c253c0a4c27acf9999e232393a4fb385"),
                    "new":(179840,"e887a10b0701d86ed66a7b5ccbffae3073f781ed6c2bdfb16cb0d2aa847886d7")},
 "libsystemd-dev":{"old":(1366204,"f074150505b62b572d3ff2c621be1b0a55bb860c7a497fde6563baf5d2371ab7"),
                    "new":(1409396,"615f6eb8f93aa55f61b2fd0d2e3c227e4babd7a0f634ab321d836e22310c60f7")},
 "libudev-dev":{"old":(22014,"e9e142b9b0f287a58dc0cef550bc8200cddad495fdf9ba6245c76be615d24048"),
                 "new":(65626,"3c7b4db0eb8593ebf4f6d2949ead7531ade0452a83ea965b540f6a5a603c9d99")},
 "systemd-cryptsetup":{"old":(124792,"8fb5cdacd68b3f6ab91ae621f953c859868c641d9aa07c6910da1a489393b2bf"),
                       "new":(167950,"64bf295a554825639733237f7d090860c38bb463b104948f4a429a863d4ff5b8")},
 "systemd-dev":{"old":(64626,"c90b3b9ba3ca609ed4516303dbb13d7a9b7c7339b4e570786453e5e1f2ca9ac2"),
                "new":(64848,"be2507f7ee1730151395734ba729c247b41a13bae79673aa2d6ea8f9d21837aa")},
 "systemd-oomd":{"old":(40542,"c2c7b4e3e51384ee2de3870c44212233e34876764a495775f1db493ec6e6dde8"),
                 "new":(83712,"bb371bcb193ff6a441022668096adebb814fb1eb412be8116c0dcd103bf40b57")},
}
ORIGINAL_METADATA={
 "original-dpkg-status":(2442903,"138ba337672dfb6761a62eda7f2f4c50112c97d0c8d627c31174f6634151574a"),
 "ubuntu-archive-keyring.gpg":(3607,"80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31"),
 "main.InRelease":(135549,"45f95ce276cdba3e41870516a130e03c58b8b7a79e9546b0efe9e526d255740c"),
 "main.Packages":(7581722,"92eb335c0ed27983d41a5a0efdf0edce3e67bfa34e8e987af9df260ca72d9bf9"),
 "updates.InRelease":(137401,"f0118485ce454ac2233d0611c33d567a8dcc973cfa142171bacee4296c8ac4d7"),
 "updates.Packages":(4874561,"5f1b12c2cf2aff59a26fc4bce4b22704f4d2894509f2640dfb053e4c67052493"),
}
ORIGINAL_COMPONENTS=(*FULL_COMPONENTS,"original-extras")
ORIGINAL_CLOSURE_SHA=hashlib.sha256(canonical({"native_sixteen":FULL_CLOSURE_SHA,
    "profile":ORIGINAL_PROFILE,"extra_packages":ORIGINAL_EXTRAS,
    "original_sources":ORIGINAL_METADATA,"signer":ORIGINAL_SIGNER})).hexdigest()

def original_extra_identity(name,kind):
    need(name in ORIGINAL_EXTRAS and kind in ("old","new"),"fixed original extra package")
    if name=="libselinux-dev":
        return "libselinux",(core.OLD if kind=="old" else core.NEW)["libselinux"],"amd64"
    return "systemd",systemd.OLD if kind=="old" else systemd.NEW,"all" if name=="systemd-dev" else "amd64"

def original_profile_status(raw,roles):
    """Require the complete, actually observed original source family."""
    records={}
    for stanza in raw.split(b"\n\n"):
        if not stanza.strip():continue
        row=core.deb822(stanza);name=row.get("Package")
        need(isinstance(name,str) and name not in records,"unique original package database record")
        records[name]=row
    need(len(records)==2391,"complete original package database record count")
    selected={name:row for name,row in records.items()
              if row.get("Source",name).split()[0] in ("systemd","libselinux","apparmor","gdm3")
              and row.get("Status") in ("install ok installed","hold ok installed")}
    need(len(roles)==22 and set(selected)=={r["name"] for r in roles},"exact original installed native family")
    for role in roles:
        row=selected[role["name"]]
        architecture="all" if role["name"]=="systemd-dev" else "amd64"
        need(row.get("Version")==role["old_version"] and row.get("Architecture")==architecture
             and row.get("Source",role["name"]).split()[0]==role["source"],
             "original installed package version/architecture/source differs")

def original_signed_archives(area,root):
    bodies={}
    for name,wanted in ORIGINAL_METADATA.items():
        pin=file_pin(area/name)
        need((pin["bytes"],pin["sha256"])==wanted,"fixed original signed metadata changed")
        bodies[name]=read_pin(pin,16*1024*1024,root)
    declarations={}
    for pocket in ("main","updates"):
        with contextlib.ExitStack() as stack:
            key,ks=stack.enter_context(held(area/"ubuntu-archive-keyring.gpg",root=root,maximum=65536))
            signed,ss=stack.enter_context(held(area/(pocket+".InRelease"),root=root,maximum=1024*1024))
            need((ks.st_size,hash_fd(key))==ORIGINAL_METADATA["ubuntu-archive-keyring.gpg"]
                 and (ss.st_size,hash_fd(signed))==ORIGINAL_METADATA[pocket+".InRelease"],
                 "held signature inputs changed after source readback")
            os.lseek(key,0,os.SEEK_SET);os.lseek(signed,0,os.SEEK_SET)
            signature=bounded_process(["/usr/bin/gpgv","--status-fd=1","--keyring",f"/proc/self/fd/{key}",
                f"/proc/self/fd/{signed}"],seconds=30,maximum=65536,pass_fds=(key,signed))
            need(signature["exit"]==0 and
                 ("[GNUPG:] VALIDSIG "+ORIGINAL_SIGNER+" ").encode() in signature["stdout"],
                 "original archive index lacks the actual Ubuntu archive signature")
        fields=systemd.source_fields(bodies[pocket+".InRelease"])
        need(fields.get("Origin")=="Ubuntu" and fields.get("Codename")=="resolute",
             "original Ubuntu archive identity")
        rows=[line.split() for line in fields.get("SHA256","").splitlines() if line.strip()]
        wanted=ORIGINAL_METADATA[pocket+".Packages"]
        matches=[r for r in rows if len(r)==3 and r[2]=="main/binary-amd64/Packages"]
        need(matches==[[wanted[1],str(wanted[0]),"main/binary-amd64/Packages"]],
             "complete package index is not bound by the signed InRelease")
        for stanza in bodies[pocket+".Packages"].split(b"\n\n"):
            if not stanza.strip():continue
            row=core.deb822(stanza);name=row.get("Package")
            if name not in ORIGINAL_EXTRAS:continue
            source,version,arch=original_extra_identity(name,"old")
            if row.get("Version")!=version:continue
            need(name not in declarations and row.get("Architecture")==arch
                 and row.get("Source",name).split()[0]==source,"original signed binary identity")
            expected=ORIGINAL_EXTRAS[name]["old"]
            need((row.get("Size"),row.get("SHA256"))==(str(expected[0]),expected[1]),
                 "rollback archive differs from the signed Ubuntu package index")
            directory="libs/libselinux" if source=="libselinux" else "s/systemd"
            need(row.get("Filename")=="pool/main/"+directory+"/"+name+"_"+version+"_"+arch+".deb",
                 "fixed original archive repository path")
            declarations[name]=row
    need(set(declarations)==set(ORIGINAL_EXTRAS),"complete original rollback package signed provenance")
    return bodies["original-dpkg-status"]

def original_extra_build(directory,indices,name,pin,root):
    source,version,arch=original_extra_identity(name,"new")
    real=name+"_"+version+"_"+arch+".deb"
    for extension in ("changes","buildinfo"):
        if source=="systemd":
            area=directory/"systemd";index=indices["systemd"];alias="normal."+extension
        else:
            area=directory/"native-five";index=indices["native-five"]
            names=index["source_names"][source]
            matching=[n for n in names if n.endswith("."+extension)]
            need(len(matching)==1,"one normal native source build record")
            alias=names[matching[0]]
        body=read_pin(core.material_pin(area,alias,index["files"][alias]),1024*1024,root)
        fields=core.deb822(body)
        need(fields.get("Source","").split()[0]==source and fields.get("Version")==version
             and core.sha_rows(fields).get(real)=={k:pin[k] for k in ("bytes","sha256")},
             "extra original-host package is not from the admitted normal source build")

def original_extra_contents(pin,inventory,name,kind,root):
    source,version,arch=original_extra_identity(name,kind)
    with held(pin["path"],root=root,maximum=16*1024*1024) as (fd,st):
        need((st.st_size,hash_fd(fd))==ORIGINAL_EXTRAS[name][kind],"fixed original extra archive")
        result={}
        for key,option in (("control","--ctrl-tarfile"),("payload","--fsys-tarfile")):
            os.lseek(fd,0,os.SEEK_SET)
            command=bounded_process(["/usr/bin/dpkg-deb",option,f"/proc/self/fd/{fd}"],
                seconds=60,maximum=core.MAX_TAR,pass_fds=(fd,))
            need(command["exit"]==0,"normal original extra package stream read")
            expected=inventory[key] if key=="control" else {r["path"]:r for r in inventory[key]}
            need(len(expected)==len(inventory[key]),"unique complete original extra inventory")
            rows,bodies=core.tar_rows(command["stdout"],set(expected))
            need(rows==expected,"every original extra package member must match")
            result[key]=rows
            if key=="control":result["control_bodies"]=bodies
        fields=core.deb822(result["control_bodies"]["control"])
        need((fields.get("Package"),fields.get("Version"),fields.get("Architecture"))==(name,version,arch)
             and fields.get("Source",name).split()[0]==source,"original extra binary/source identity")
        result["control"]=fields
        return result

def verify_original_extras(directory,indices,root):
    area=directory/"original-extras"
    expected=set(ORIGINAL_METADATA)|{name+"-"+kind+suffix for name in ORIGINAL_EXTRAS
        for kind in ("old","new") for suffix in (".deb","-inventory.json")}
    need(set(p.name for p in area.iterdir())==expected,"exact original-host extra component inventory")
    status=original_signed_archives(area,root)
    roles=[];packages={};payloads={}
    for name in sorted(ORIGINAL_EXTRAS):
        packages[name]={};payloads[name]={}
        source,old_version,_=original_extra_identity(name,"old")
        row={"role":name,"name":name,"source":source,"old_version":old_version,
             "new_version":original_extra_identity(name,"new")[1]}
        for kind in ("old","new"):
            pin=file_pin(area/(name+"-"+kind+".deb"));ip=file_pin(area/(name+"-"+kind+"-inventory.json"))
            need((pin["bytes"],pin["sha256"])==ORIGINAL_EXTRAS[name][kind],"normal extra archive fixed identity")
            if kind=="new":original_extra_build(directory,indices,name,pin,root)
            inventory=json_bytes(read_pin(ip,4*1024*1024,root))
            payloads[name][kind]=original_extra_contents(pin,inventory,name,kind,root)
            packages[name][kind]=pin
            row[kind]={key:{"path":"original-extras/"+Path(p["path"]).name,
                       "bytes":p["bytes"],"sha256":p["sha256"]} for key,p in (("package",pin),("inventory",ip))}
        for part in ("config","triggers","conffiles","templates","preinst","postinst","prerm","postrm"):
            need(payloads[name]["old"]["control_bodies"].get(part)==payloads[name]["new"]["control_bodies"].get(part),
                 "normal extra package executable/configuration script changed")
        roles.append(row)
    return roles,packages,payloads,status

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

def verify_components(directory,components,root,full=False,original=False):
    need(not original or full,"original profile includes the complete native sixteen")
    expected=ORIGINAL_COMPONENTS if original else FULL_COMPONENTS if full else COMPONENTS
    need(set(components)==set(expected),"fixed native source components")
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
    if original:
        need(components["original-extras"]=={"directory":"original-extras","profile":ORIGINAL_PROFILE},
             "fixed original installed native profile")
        extra,p,body,status=verify_original_extras(directory,index_by_component,root)
        need(not(set(packages)&set(p)),"unique original package roles")
        roles.extend(extra);packages.update(p);payloads.update(body)
        original_profile_status(status,roles)
    count=22 if original else 16 if full else 15
    need(len(roles)==count and len({x["name"] for x in roles})==count,"exact normal native package closure")
    return roles,packages,payloads,index_by_component

def verify_bundle(directory,release_id,root=False):
    directory=safe_absolute(str(directory));digest(release_id)
    release=json_bytes(read_pin(file_pin(directory/"NATIVE-RELEASE.json"),1024*1024,root))
    if release.get("schema")==core.SCHEMA:
        index,closure,packages,payloads=core.verify_bundle(directory,release_id,root)
        index={**index,"closure_sha256":core.CLOSURE_SHA}
        return index,closure,packages,payloads
    original=release.get("schema")==ORIGINAL_SCHEMA
    full=original or release.get("schema")==FULL_SCHEMA
    need(release.get("schema") in (SCHEMA,FULL_SCHEMA,ORIGINAL_SCHEMA) and release.get("release_id")==release_id,
         "normal native combined release identity")
    descriptor={k:v for k,v in release.items() if k!="release_id"}
    exact(descriptor,{"schema","components","closure_sha256","package_names","package_roles","files",
                      "normal_archives_verified","whole_payload_verified","package_database_modified",
                      "physical_install","runtime_qualified"},"combined native release")
    expected_closure=ORIGINAL_CLOSURE_SHA if original else FULL_CLOSURE_SHA if full else CLOSURE_SHA
    need(hashlib.sha256(canonical(descriptor)).hexdigest()==release_id
         and descriptor["closure_sha256"]==expected_closure,"same native source release digest")
    need(descriptor["physical_install"] is False and descriptor["runtime_qualified"] is False
         and descriptor["package_database_modified"] is False,"materials are not activation authority")
    components=ORIGINAL_COMPONENTS if original else FULL_COMPONENTS if full else COMPONENTS
    need(set(p.name for p in directory.iterdir())==set(components)|{"NATIVE-RELEASE.json"},
         "unexpected combined native release root member")
    roles,packages,payloads,indices=verify_components(directory,descriptor["components"],root,full,original)
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

def prepare_original(native_full,native_id,extras,output):
    native_full=safe_absolute(str(native_full));extras=safe_absolute(str(extras));output=safe_absolute(str(output))
    admitted,_,packages,_=verify_bundle(native_full,native_id)
    need(admitted["schema"]==FULL_SCHEMA and len(packages)==16,"unchanged complete sixteen-package source required")
    sources=set(ORIGINAL_METADATA)|{name+"-"+kind+".deb" for name in ORIGINAL_EXTRAS for kind in ("old","new")}
    need(set(p.name for p in extras.iterdir())==sources,"exact normal original extra input files")
    for name,wanted in ORIGINAL_METADATA.items():
        pin=file_pin(extras/name);need((pin["bytes"],pin["sha256"])==wanted,"fixed original source metadata input")
    for name,versions in ORIGINAL_EXTRAS.items():
        for kind,wanted in versions.items():
            pin=file_pin(extras/(name+"-"+kind+".deb"))
            need((pin["bytes"],pin["sha256"])==wanted,"fixed original normal extra archive input")
    mkdir_new(output)
    for name in FULL_COMPONENTS:
        mkdir_new(output/name)
        for p in sorted((native_full/name).iterdir()):copy_pin(file_pin(p),output/name/p.name,0o444)
    area=output/"original-extras";mkdir_new(area)
    for p in sorted(extras.iterdir()):copy_pin(file_pin(p),area/p.name,0o444)
    for name in ORIGINAL_EXTRAS:
        for kind in ("old","new"):
            pin=file_pin(area/(name+"-"+kind+".deb"));inventory=archive_inventory(pin)
            original_extra_contents(pin,inventory,name,kind,False)
            new_file(area/(name+"-"+kind+"-inventory.json"),canonical(inventory))
    components={**admitted["components"],"original-extras":{"directory":"original-extras","profile":ORIGINAL_PROFILE}}
    roles,_,_,_=verify_components(output,components,False,True,True)
    files=[]
    for subdir in ORIGINAL_COMPONENTS:
        for p in sorted((output/subdir).iterdir()):
            fp=file_pin(p);files.append({"path":subdir+"/"+p.name,"bytes":fp["bytes"],"sha256":fp["sha256"]})
    descriptor={"schema":ORIGINAL_SCHEMA,"components":components,"closure_sha256":ORIGINAL_CLOSURE_SHA,
                "package_names":[x["name"] for x in roles],"package_roles":roles,"files":sorted(files,key=lambda x:x["path"]),
                "normal_archives_verified":True,"whole_payload_verified":True,"package_database_modified":False,
                "physical_install":False,"runtime_qualified":False}
    release_id=hashlib.sha256(canonical(descriptor)).hexdigest()
    new_file(output/"NATIVE-RELEASE.json",canonical({"release_id":release_id,**descriptor}))
    verify_bundle(output,release_id)
    return {"release_id":release_id,"receipt":file_pin(output/"NATIVE-RELEASE.json"),
            "profile":ORIGINAL_PROFILE,"package_count":22,"rollback_package_count":22,"runtime_qualified":False}

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest="command",required=True)
    a=s.add_parser("prepare")
    for arg in ("core","systemd","output","apparmor-old","apparmor-new"):
        a.add_argument("--"+arg,type=Path,required=True)
    a.add_argument("--core-release-id",required=True);a.add_argument("--systemd-release-id",required=True)
    a=s.add_parser("prepare-original")
    for arg in ("native-full","extras","output"):a.add_argument("--"+arg,type=Path,required=True)
    a.add_argument("--native-release-id",required=True)
    a=s.add_parser("verify");a.add_argument("--bundle",type=Path,required=True);a.add_argument("--release-id",required=True)
    a=p.parse_args()
    if a.command=="prepare":r=prepare(a.core,a.core_release_id,a.systemd,a.systemd_release_id,
                                    a.output,a.apparmor_old,a.apparmor_new)
    elif a.command=="prepare-original":r=prepare_original(a.native_full,a.native_release_id,a.extras,a.output)
    else:verify_bundle(a.bundle,a.release_id);r={"verified":True,"release_id":a.release_id,"runtime_qualified":False}
    print(canonical(r).decode(),end="")
if __name__=="__main__":main()
