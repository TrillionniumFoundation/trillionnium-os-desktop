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
    host_manifest, fixed_command,
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
    for unit in ("graphical.target","gdm.service","droidloom-production.service",
                 "droidloom-instance-launcher.service","droidloom-instance-factory.service"):
        r=fixed_command("systemctl",["show","--value","--property=ActiveState",unit],maximum=65536)
        need(r["exit"]==0 and r["stdout"].strip() in (b"inactive",b"failed"),"live graphical/Android owner blocks cold transaction")
    return {"boot_id":Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "root_identity":[root.st_dev,root.st_ino],"kernel":ORIGINAL_KERNEL}

def actual_acceptance_binding(release_id):
    digest(release_id)
    # Parent integration must call the actual owned VM and original-device
    # private-working-copy validators and bind their original file/process
    # identities to this release. Public fresh-data or caller pass flags never
    # establish this authority. There is deliberately no accepted placeholder.
    raise Rejected("physical apply requires the not-yet-integrated actual owned-runtime/private-working-copy verifier")

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

def protected_bundle(release_id):
    return STORE/"releases"/digest(release_id)

def apply(release_id):
    original_cold_authority()
    binding=actual_acceptance_binding(release_id)
    need(binding is not None,"actual acceptance did not return owned authority")
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
    for name in ("apply-public","rollback-public"):
        q=sub.add_parser(name);q.add_argument("--release",required=True)
    a=p.parse_args()
    result=apply(a.release) if a.command=="apply-public" else rollback(a.release)
    sys.stdout.buffer.write(canonical(result));sys.stdout.buffer.flush()

if __name__=="__main__":
    try:main()
    except (Rejected,OSError,ValueError,KeyError) as e:
        print("droidloom-cold-apply: "+str(e),file=sys.stderr);sys.exit(1)
