#!/usr/bin/python3
"""Combine the admitted native libraries/GDM and systemd normal package cohorts."""
import argparse
import contextlib
import ctypes
import fcntl
import stat
import tarfile
import hashlib
import os
from pathlib import Path
from release import (need,exact,digest,canonical,safe_absolute,safe_relative,read_pin,
                     json_bytes,file_pin,new_file,copy_pin,mkdir_new,integer,held,hash_fd,f9,pin_shape,STORE)
import native_bundle as core
import systemd_bundle as systemd

SCHEMA="droidloom-normal-native-package-release-v2"
COMPONENTS=("native-five","systemd")
CLOSURE_SHA=hashlib.sha256(canonical({"native_five":core.CLOSURE_SHA,
                                    "systemd":systemd.CLOSURE_SHA})).hexdigest()

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

def verify_components(directory,components,root):
    need(set(components)==set(COMPONENTS),"fixed native source components")
    packages={};payloads={};roles=[];index_by_component={}
    for subdir,module in (("native-five",core),("systemd",systemd)):
        c=components[subdir];exact(c,{"directory","release_id"},"normal native component")
        need(c["directory"]==subdir,"fixed component directory")
        index,closure,p,body=module.verify_bundle(directory/subdir,c["release_id"],root)
        need(not(set(packages)&set(p)),"overlapping package role components")
        packages.update(p);payloads.update(body)
        roles.extend(component_roles(subdir,index,body))
        index_by_component[subdir]=index
    need(len(roles)==15 and len({x["name"] for x in roles})==15,"exact native fifteen-package closure")
    return roles,packages,payloads,index_by_component

def verify_bundle(directory,release_id,root=False):
    directory=safe_absolute(str(directory));digest(release_id)
    release=json_bytes(read_pin(file_pin(directory/"NATIVE-RELEASE.json"),1024*1024,root))
    if release.get("schema")==core.SCHEMA:
        index,closure,packages,payloads=core.verify_bundle(directory,release_id,root)
        index={**index,"closure_sha256":core.CLOSURE_SHA}
        return index,closure,packages,payloads
    need(release.get("schema")==SCHEMA and release.get("release_id")==release_id,
         "normal native combined release identity")
    descriptor={k:v for k,v in release.items() if k!="release_id"}
    exact(descriptor,{"schema","components","closure_sha256","package_names","package_roles","files",
                      "normal_archives_verified","whole_payload_verified","package_database_modified",
                      "physical_install","runtime_qualified"},"combined native release")
    need(hashlib.sha256(canonical(descriptor)).hexdigest()==release_id
         and descriptor["closure_sha256"]==CLOSURE_SHA,"same native source release digest")
    need(descriptor["physical_install"] is False and descriptor["runtime_qualified"] is False
         and descriptor["package_database_modified"] is False,"materials are not activation authority")
    need(set(p.name for p in directory.iterdir())==set(COMPONENTS)|{"NATIVE-RELEASE.json"},
         "unexpected combined native release root member")
    roles,packages,payloads,indices=verify_components(directory,descriptor["components"],root)
    need(roles==descriptor["package_roles"] and [x["name"] for x in roles]==descriptor["package_names"],
         "source-owned combined normal package role declarations")
    actual_files=[]
    for subdir in COMPONENTS:
        for p in sorted((directory/subdir).iterdir()):
            fp=file_pin(p)
            actual_files.append({"path":subdir+"/"+p.name,"bytes":fp["bytes"],"sha256":fp["sha256"]})
    expected=sorted(actual_files,key=lambda x:x["path"])
    need(expected==descriptor["files"],"complete combined native file inventory")
    for row in expected:
        read_pin(relative_pin(directory,row["path"],row),64*1024*1024,root)
    return descriptor,{"package_roles":roles,"closure_sha256":CLOSURE_SHA},packages,payloads

def prepare(core_directory,core_id,systemd_directory,systemd_id,output):
    core_directory=safe_absolute(str(core_directory));systemd_directory=safe_absolute(str(systemd_directory))
    output=safe_absolute(str(output))
    core.verify_bundle(core_directory,core_id);systemd.verify_bundle(systemd_directory,systemd_id)
    mkdir_new(output)
    for name,source in (("native-five",core_directory),("systemd",systemd_directory)):
        target=output/name;mkdir_new(target)
        for p in sorted(source.iterdir()):copy_pin(file_pin(p),target/p.name,0o444)
    components={"native-five":{"directory":"native-five","release_id":core_id},
                "systemd":{"directory":"systemd","release_id":systemd_id}}
    roles,_,_,_=verify_components(output,components,False)
    files=[]
    for subdir in COMPONENTS:
        for p in sorted((output/subdir).iterdir()):
            fp=file_pin(p);files.append({"path":subdir+"/"+p.name,"bytes":fp["bytes"],"sha256":fp["sha256"]})
    descriptor={"schema":SCHEMA,"components":components,"closure_sha256":CLOSURE_SHA,
                "package_names":[x["name"] for x in roles],"package_roles":roles,
                "files":sorted(files,key=lambda x:x["path"]),"normal_archives_verified":True,
                "whole_payload_verified":True,"package_database_modified":False,
                "physical_install":False,"runtime_qualified":False}
    release_id=hashlib.sha256(canonical(descriptor)).hexdigest()
    new_file(output/"NATIVE-RELEASE.json",canonical({"release_id":release_id,**descriptor}))
    verify_bundle(output,release_id)
    return {"release_id":release_id,"receipt":file_pin(output/"NATIVE-RELEASE.json"),
            "package_count":15,"rollback_package_count":15,"runtime_qualified":False}

# Transport is deliberately separate from activation: all normal package
# sources, inventories and original rollback packages travel together.
ARCHIVE_SCHEMA="droidloom-normal-native-archive-v1"
ARCHIVE_NAME="native-packages.tar"
ARCHIVE_INDEX="NATIVE-ARCHIVE.json"
MANIFEST_NAME="NATIVE-RELEASE.json"
MAX_ARCHIVE_FILES=128
MAX_ARCHIVE_BYTES=128*1024*1024
MAX_MEMBER_BYTES=64*1024*1024
RELEASE_FIELDS={"schema","components","closure_sha256","package_names","package_roles","files",
                "normal_archives_verified","whole_payload_verified","package_database_modified",
                "physical_install","runtime_qualified"}

def _archive_manifest(raw,release_id):
    release=json_bytes(raw)
    need(isinstance(release,dict) and release.get("release_id")==digest(release_id),
         "same normal native archive release")
    descriptor={k:v for k,v in release.items() if k!="release_id"}
    exact(descriptor,RELEASE_FIELDS,"transported native release")
    need(descriptor["schema"]==SCHEMA and descriptor["closure_sha256"]==CLOSURE_SHA
         and hashlib.sha256(canonical(descriptor)).hexdigest()==release_id,
         "source-bound native archive descriptor")
    need(raw==canonical(release),"canonical native release bytes")
    need(descriptor["normal_archives_verified"] is True and descriptor["whole_payload_verified"] is True
         and all(descriptor[k] is False for k in
                 ("package_database_modified","physical_install","runtime_qualified")),
         "native package materials never assert activation")
    need(set(descriptor["components"])==set(COMPONENTS),"fixed native archive components")
    for subdir,c in descriptor["components"].items():
        exact(c,{"directory","release_id"},"native archive component")
        need(c["directory"]==subdir,"fixed native component path");digest(c["release_id"])
    rows=descriptor["files"]
    need(isinstance(rows,list) and 1<=len(rows)<MAX_ARCHIVE_FILES,"native archive member count")
    seen=set()
    for row in rows:
        exact(row,{"path","bytes","sha256"},"native archive original member")
        relative=safe_relative(row["path"])
        need(len(relative.split("/"))==2 and relative.split("/")[0] in COMPONENTS
             and relative not in seen,"fixed unique native source member")
        seen.add(relative);integer(row["bytes"],1,MAX_MEMBER_BYTES,"native source bytes");digest(row["sha256"])
    need(rows==sorted(rows,key=lambda x:x["path"]),"ordered native archive members")
    need(sum(r["bytes"] for r in rows)+len(raw)<=MAX_ARCHIVE_BYTES,
         "native archive total bytes")
    names=descriptor["package_names"]
    need(isinstance(names,list) and len(names)==15 and len(set(names))==15
         and isinstance(descriptor["package_roles"],list) and len(descriptor["package_roles"])==15,
         "complete native fifteen-package archive")
    members=[{"path":MANIFEST_NAME,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()},*rows]
    return descriptor,members

def _tar_header(name,size=0,*,directory=False):
    # Comparing the exact USTAR header rejects PAX/GNU extensions, aliases,
    # links, devices, alternate modes and a second concatenated archive.
    item=tarfile.TarInfo(name+"/" if directory else name)
    item.type=tarfile.DIRTYPE if directory else tarfile.REGTYPE
    item.mode=0o700 if directory else 0o444
    item.uid=item.gid=item.mtime=0;item.size=size
    item.uname=item.gname=""
    body=item.tobuf(format=tarfile.USTAR_FORMAT,encoding="ascii",errors="strict")
    need(len(body)==512,"one canonical native USTAR header")
    return body

def _archive_bytes(members):
    return (len(COMPONENTS)+len(members)+2)*512+sum((r["bytes"]+511)//512*512 for r in members)

def _read_material(pin,maximum,root):
    pin_shape(pin)
    with held(pin["path"],root=root,modes={0o400,0o444},maximum=maximum) as (fd,st):
        need((st.st_size,hash_fd(fd))==(pin["bytes"],pin["sha256"]),"native material pin")
        raw=os.read(fd,maximum+1);need(len(raw)==st.st_size,"complete native material")
        return raw,list(f9(st))

def _revalidate_material(pin,identity,root):
    with held(pin["path"],root=root,modes={0o400,0o444}) as (fd,st):
        need(list(f9(st))==identity and (st.st_size,hash_fd(fd))==(pin["bytes"],pin["sha256"]),
             "native material source replaced during verification")

def archive_inputs(index_pin,root=False):
    index_path=safe_absolute(pin_shape(index_pin)["path"])
    need(index_path.name==ARCHIVE_INDEX,"fixed normal native archive index")
    raw,index_identity=_read_material(index_pin,2*1024*1024,root);index=json_bytes(raw)
    exact(index,{"schema","native_release_id","closure_sha256","manifest","archive","files",
                 "package_names","normal_archives_verified","whole_payload_verified",
                 "physical_install","runtime_qualified"},"native archive index")
    need(raw==canonical(index) and index["schema"]==ARCHIVE_SCHEMA
         and index["closure_sha256"]==CLOSURE_SHA,"canonical source-bound native archive")
    need(index["normal_archives_verified"] is True and index["whole_payload_verified"] is True
         and index["physical_install"] is False and index["runtime_qualified"] is False,
         "native archive is public material")
    for key,name in (("manifest",MANIFEST_NAME),("archive",ARCHIVE_NAME)):
        row=index[key];exact(row,{"path","bytes","sha256"},"native archive fixed leaf")
        need(row["path"]==name,"native archive path substitution")
        integer(row["bytes"],1,MAX_ARCHIVE_BYTES,"native archive leaf bound");digest(row["sha256"])
    manifest_pin=relative_pin(index_path.parent,MANIFEST_NAME,index["manifest"])
    manifest_raw,manifest_identity=_read_material(manifest_pin,1024*1024,root)
    descriptor,members=_archive_manifest(manifest_raw,index["native_release_id"])
    need(members==index["files"] and index["manifest"]==members[0]
         and index["package_names"]==descriptor["package_names"],"native archive full member binding")
    need(index["archive"]["bytes"]==_archive_bytes(members)<=MAX_ARCHIVE_BYTES,
         "exact canonical native archive length")
    return {"index":index,"descriptor":descriptor,"members":members,
            "index_pin":index_pin,"index_identity":index_identity,
            "manifest_pin":manifest_pin,"manifest_identity":manifest_identity,
            "archive_pin":relative_pin(index_path.parent,ARCHIVE_NAME,index["archive"])}

def _write_all(fd,body):
    view=memoryview(body)
    while view:
        wrote=os.write(fd,view);need(wrote>0,"complete native material write");view=view[wrote:]

def _read_exact(fd,count):
    chunks=[];left=count
    while left:
        b=os.read(fd,min(left,1024*1024));need(b,"truncated native archive")
        chunks.append(b);left-=len(b)
    return b"".join(chunks)

def _consume_archive(inputs,output,root):
    # This is an ordinary create-only materialization, never a package install.
    output=safe_absolute(str(output));mkdir_new(output)
    dirs={}
    try:
        base=os.open(output,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        dirs[""]=base;initial=os.fstat(base)
        need(stat.S_IMODE(initial.st_mode)==0o700,"private native archive output")
        for name in COMPONENTS:
            os.mkdir(name,0o700,dir_fd=base)
            dirs[name]=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=base)
        p=inputs["archive_pin"]
        with held(p["path"],root=root,modes={0o400,0o444},maximum=MAX_ARCHIVE_BYTES) as (fd,st):
            need((st.st_size,hash_fd(fd))==(p["bytes"],p["sha256"]),"complete native archive source")
            for name in COMPONENTS:
                need(_read_exact(fd,512)==_tar_header(name,directory=True),"native archive directory header")
            for row in inputs["members"]:
                need(_read_exact(fd,512)==_tar_header(row["path"],row["bytes"]),
                     "native archive exact regular header")
                parent,_,leaf=row["path"].rpartition("/")
                out=os.open(leaf,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,
                            0o400,dir_fd=dirs[parent])
                try:
                    h=hashlib.sha256();left=row["bytes"]
                    while left:
                        b=_read_exact(fd,min(left,1024*1024));h.update(b);_write_all(out,b);left-=len(b)
                    need(h.hexdigest()==row["sha256"],"native archive member changed")
                    padding=(-row["bytes"])%512
                    need(_read_exact(fd,padding)==b"\0"*padding,"native archive nonzero member padding")
                    os.fchmod(out,0o444);os.fsync(out)
                    current=os.fstat(out);named=os.stat(leaf,dir_fd=dirs[parent],follow_symlinks=False)
                    need(stat.S_ISREG(current.st_mode) and current.st_nlink==1
                         and current.st_size==row["bytes"] and current.st_dev==initial.st_dev
                         and f9(current)==f9(named),"native output inode and length")
                finally:os.close(out)
            need(_read_exact(fd,1024)==b"\0"*1024 and not os.read(fd,1),"native archive exact termination")
        for directory in dirs.values():os.fsync(directory)
        named=os.stat(output,follow_symlinks=False)
        need((named.st_dev,named.st_ino)==(initial.st_dev,initial.st_ino),"native output root replaced")
    finally:
        for fd in dirs.values():os.close(fd)
    _revalidate_material(inputs["index_pin"],inputs["index_identity"],root)
    _revalidate_material(inputs["manifest_pin"],inputs["manifest_identity"],root)
    index,_,packages,_=verify_bundle(output,inputs["index"]["native_release_id"],root)
    need(index["schema"]==SCHEMA and len(packages)==15,"full normal native source/rollback closure")
    return {"native_release_id":inputs["index"]["native_release_id"],
            "native_manifest":file_pin(output/MANIFEST_NAME),"files_verified":len(inputs["members"]),
            "packages_verified":len(packages),"whole_payload_verified":True,
            "physical_install":False,"runtime_qualified":False}

def inspect_archive(index_pin,output,root=False):
    return _consume_archive(archive_inputs(index_pin,root),output,root)

def export_archive(directory,release_id,output):
    directory=safe_absolute(str(directory));output=safe_absolute(str(output));digest(release_id)
    index,_,packages,_=verify_bundle(directory,release_id)
    need(index["schema"]==SCHEMA and len(packages)==15,"transport requires the complete normal native release")
    manifest_pin=file_pin(directory/MANIFEST_NAME);raw,identity=_read_material(manifest_pin,1024*1024,False)
    descriptor,members=_archive_manifest(raw,release_id)
    need(descriptor==index,"same verified native manifest")
    mkdir_new(output);copy_pin(manifest_pin,output/MANIFEST_NAME,0o444)
    fd=os.open(output/ARCHIVE_NAME,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o400)
    try:
        for name in COMPONENTS:_write_all(fd,_tar_header(name,directory=True))
        for row in members:
            _write_all(fd,_tar_header(row["path"],row["bytes"]))
            source=relative_pin(directory,row["path"],row)
            with held(source["path"],modes={0o400,0o444},maximum=MAX_MEMBER_BYTES) as (original,st):
                need((st.st_size,hash_fd(original))==(row["bytes"],row["sha256"]),"native source member before export")
                h=hashlib.sha256();count=0
                while True:
                    b=os.read(original,1024*1024)
                    if not b:break
                    count+=len(b);need(count<=row["bytes"],"native export member grew")
                    h.update(b);_write_all(fd,b)
                need(count==row["bytes"] and h.hexdigest()==row["sha256"],"native source changed during export")
            _write_all(fd,b"\0"*((-row["bytes"])%512))
        _write_all(fd,b"\0"*1024);os.fchmod(fd,0o444);os.fsync(fd)
        need(os.fstat(fd).st_size==_archive_bytes(members),"native normal export length")
    finally:os.close(fd)
    _revalidate_material(manifest_pin,identity,False)
    archive_pin=file_pin(output/ARCHIVE_NAME)
    archive={"schema":ARCHIVE_SCHEMA,"native_release_id":release_id,"closure_sha256":CLOSURE_SHA,
             "manifest":members[0],"archive":{"path":ARCHIVE_NAME,"bytes":archive_pin["bytes"],
                                               "sha256":archive_pin["sha256"]},
             "files":members,"package_names":descriptor["package_names"],
             "normal_archives_verified":True,"whole_payload_verified":True,
             "physical_install":False,"runtime_qualified":False}
    new_file(output/ARCHIVE_INDEX,canonical(archive),0o444)
    check=inspect_archive(file_pin(output/ARCHIVE_INDEX),output/"readback")
    result={"schema":"droidloom-normal-native-archive-result-v1","native_release_id":release_id,
            "source_manifest":manifest_pin,"descriptor":file_pin(output/ARCHIVE_INDEX),
            "archive":archive_pin,"manifest":file_pin(output/MANIFEST_NAME),"readback":check,
            "physical_install":False,"runtime_qualified":False}
    new_file(output/"RESULT.json",canonical(result),0o444)
    return result

@contextlib.contextmanager
def _protected_material_store(state):
    # The CLI supplies only STORE. Tests can exercise this material engine in
    # a separate root-owned qualification directory; no root argument is public.
    state=safe_absolute(str(state));fd=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        for part in state.parts[1:]:
            try:n=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part,0o700,dir_fd=fd)
                n=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                os.fsync(fd)
            s=os.fstat(n)
            need(s.st_uid==s.st_gid==0 and not(s.st_mode&0o022),"protected native store parent")
            os.close(fd);fd=n
        need(stat.S_IMODE(os.fstat(fd).st_mode)==0o700,"private native material store")
        try:os.mkdir("native-releases",0o700,dir_fd=fd);os.fsync(fd)
        except FileExistsError:pass
        releases=os.open("native-releases",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
        try:
            s=os.fstat(releases)
            need(s.st_uid==s.st_gid==0 and s.st_dev==os.fstat(fd).st_dev
                 and stat.S_IMODE(s.st_mode)==0o700,"protected native releases directory")
            lock=os.open("import.lock",os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=releases)
            try:
                ls=os.fstat(lock)
                need(stat.S_ISREG(ls.st_mode) and ls.st_uid==ls.st_gid==0 and ls.st_nlink==1
                     and stat.S_IMODE(ls.st_mode)==0o600,"native import owner lock")
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                yield releases,state/"native-releases"
                need(f9(os.fstat(lock))==f9(os.stat("import.lock",dir_fd=releases,follow_symlinks=False)),
                     "native import owner lock replaced")
            finally:os.close(lock)
        finally:os.close(releases)
    finally:os.close(fd)

def import_archive(index_pin,release_id,state):
    need(os.getuid()==os.geteuid()==0,"protected native material import requires root")
    digest(release_id);inputs=archive_inputs(index_pin,True)
    need(inputs["index"]["native_release_id"]==release_id,"requested native archive identity")
    with _protected_material_store(state) as (parent,base):
        target=base/release_id
        try:s=os.stat(release_id,dir_fd=parent,follow_symlinks=False)
        except FileNotFoundError:s=None
        if s is not None:
            need(stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0 and stat.S_IMODE(s.st_mode)==0o700,
                 "existing native material target")
            _,_,packages,_=verify_bundle(target,release_id,True)
            need(len(packages)==15,"existing normal native closure")
            return {"native_release_id":release_id,"directory":str(target),"reused":True,
                    "physical_install":False,"runtime_qualified":False}
        pending=".import-"+release_id+"-"+os.urandom(8).hex()
        result=_consume_archive(inputs,base/pending,True)
        original=os.stat(pending,dir_fd=parent,follow_symlinks=False)
        libc=ctypes.CDLL(None,use_errno=True)
        rename=libc.renameat2
        rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        rename.restype=ctypes.c_int
        need(rename(parent,pending.encode(),parent,release_id.encode(),1)==0,
             "create-only normal native material publication failed")
        os.fsync(parent)
        published=os.stat(release_id,dir_fd=parent,follow_symlinks=False)
        need((original.st_dev,original.st_ino)==(published.st_dev,published.st_ino),
             "native published directory identity")
        verify_bundle(target,release_id,True)
        result["native_manifest"]=file_pin(target/MANIFEST_NAME)
        return {**result,"directory":str(target),"reused":False}

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest="command",required=True)
    a=s.add_parser("prepare")
    for arg in ("core","systemd","output"):a.add_argument("--"+arg,type=Path,required=True)
    a.add_argument("--core-release-id",required=True);a.add_argument("--systemd-release-id",required=True)
    for name in ("verify","export"):
        a=s.add_parser(name);a.add_argument("--bundle",type=Path,required=True);a.add_argument("--release-id",required=True)
        if name=="export":a.add_argument("--output",type=Path,required=True)
    for name in ("verify-archive","import-archive"):
        a=s.add_parser(name);a.add_argument("--descriptor",type=Path,required=True)
        a.add_argument("--descriptor-sha256",required=True);a.add_argument("--release-id",required=True)
        if name=="verify-archive":a.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.command=="prepare":r=prepare(a.core,a.core_release_id,a.systemd,a.systemd_release_id,a.output)
    elif a.command=="verify":
        verify_bundle(a.bundle,a.release_id);r={"verified":True,"release_id":a.release_id,"runtime_qualified":False}
    elif a.command=="export":r=export_archive(a.bundle,a.release_id,a.output)
    else:
        descriptor=file_pin(a.descriptor)
        need(descriptor["sha256"]==digest(a.descriptor_sha256),"pinned normal native archive index")
        need(archive_inputs(descriptor)["index"]["native_release_id"]==digest(a.release_id),
             "same requested native archive")
        r=(inspect_archive(descriptor,a.output) if a.command=="verify-archive"
           else import_archive(descriptor,a.release_id,STORE))
    print(canonical(r).decode(),end="")
if __name__=="__main__":main()
