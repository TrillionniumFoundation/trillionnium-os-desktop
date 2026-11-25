#!/usr/bin/python3
"""Normal five-package native upgrade and rollback on an admitted cold root.

The engine runs the unchanged Debian maintainer scripts. A temporary, exact
policy-rc.d denies service actions; no package state is forged and no dependency
or conffile force flag is used. Production entry points require the actual
owned-runtime/private-working-copy authority supplied by cold_apply.
"""
import argparse
import base64
import contextlib
import ctypes
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import time
from release import (need,exact,digest,canonical,f9,safe_absolute,held,hash_fd,
                     new_file,read_json_file,bounded_process,Rejected)
from native_bundle import (ROLES,NAMES,OLD,NEW,CLOSURE_SHA,verify_bundle)
from cold_apply import original_cold_authority,actual_acceptance_binding

POLICY=b"#!/bin/sh\nexit 101\n"
STATE_REL="var/lib/droidloom-maintenance/native-transactions"
PRIVATE_METADATA=("etc/passwd","etc/group","etc/shadow","etc/gshadow",
                  "etc/ssh/sshd_config","etc/ssh/ssh_host_ed25519_key",
                  "etc/ssh/ssh_host_rsa_key","home","home/alex")
DISPLAY_CONFIG=("etc/gdm3/greeter.dconf-defaults","etc/X11/default-display-manager",
                "etc/systemd/system/display-manager.service")
ENV={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","LC_ALL":"C","LANG":"C",
     "DEBIAN_FRONTEND":"noninteractive","DPKG_FRONTEND_LOCKED":"1",
     "SYSTEMD_OFFLINE":"1","SYSTEMD_COLORS":"0"}
MAX_CONFIG=2*1024*1024

def node(st):
    return {"device":st.st_dev,"inode":st.st_ino,"mode":stat.S_IMODE(st.st_mode),
            "uid":st.st_uid,"gid":st.st_gid,"nlink":st.st_nlink}

def fixed_tool(name,args,seconds=300,pass_fds=()):
    need(name in ("dpkg","dpkg-query"),"fixed native package command")
    path="/usr/bin/"+name
    with held(path,root=True,modes={0o755},maximum=16*1024*1024) as (fd,st):
        result=bounded_process([f"/proc/self/fd/{fd}",*args],env=ENV,seconds=seconds,
                               maximum=8*1024*1024,pass_fds=(fd,*pass_fds))
        result["tool"]={"path":path,"bytes":st.st_size,"sha256":hash_fd(fd)}
        return result

class NativeTransaction:
    def __init__(self,root,bundle,release_id,*,existing=None):
        self.rootfd=self.lockfd=self.frontfd=None
        self.history=[]
        try:self._initialize(root,bundle,release_id,existing=existing)
        except BaseException:
            self.close();raise

    def _initialize(self,root,bundle,release_id,*,existing=None):
        need(os.getuid()==os.geteuid()==0,"normal native transaction requires root")
        self.root=safe_absolute(str(root));self.bundle=safe_absolute(str(bundle))
        self.release_id=digest(release_id)
        self.rootfd=os.open(self.root,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        s=os.fstat(self.rootfd)
        need(s.st_uid==s.st_gid==0 and not(s.st_mode&0o022),"root directory owner/mode")
        self.root_identity=[s.st_dev,s.st_ino]
        self.index,self.closure,self.packages,self.payloads=verify_bundle(self.bundle,release_id,True)
        self.state=self.ensure_state()
        self.lockfd=os.open(self.state/"transaction.lock",os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        ls=os.fstat(self.lockfd)
        need(stat.S_ISREG(ls.st_mode) and ls.st_uid==ls.st_gid==0 and ls.st_nlink==1 and
             stat.S_IMODE(ls.st_mode)==0o600,"native transaction lock")
        fcntl.flock(self.lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.frontfd=self.open_regular("var/lib/dpkg/lock-frontend",os.O_RDWR)
        fcntl.lockf(self.frontfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.attempt=None;self.snapshot=None;self.sequence=0
        if existing is not None:
            need(isinstance(existing,str) and re.fullmatch(r"[0-9a-f]{64}-[0-9a-f]{16}",existing),"saved native attempt")
            self.attempt=self.state/existing
            ss=self.attempt.lstat()
            need(stat.S_ISDIR(ss.st_mode) and ss.st_uid==ss.st_gid==0 and stat.S_IMODE(ss.st_mode)==0o700,
                 "saved native transaction owner")
            self.snapshot,_=read_json_file(self.attempt/"SNAPSHOT.json",8*1024*1024,True,{0o400})
            need(self.snapshot["release_id"]==release_id and self.snapshot["root_identity"]==self.root_identity
                 and self.snapshot["closure_sha256"]==CLOSURE_SHA,"saved native target/source binding")
            events=sorted(self.attempt.glob("EVENT-*.json"))
            need(len(events)<=64,"native journal event bound")
            for n,p in enumerate(events,1):
                value,_=read_json_file(p,1024*1024,True,{0o400})
                need(p.name==f"EVENT-{n:04d}.json" and value["sequence"]==n
                     and value["attempt"]==self.attempt.name,"native journal sequence")
                self.history.append(value)
            self.sequence=len(events)

    def close(self):
        for name in ("frontfd","lockfd","rootfd"):
            fd=getattr(self,name,None)
            if fd is not None:
                os.close(fd);setattr(self,name,None)

    def __enter__(self):return self
    def __exit__(self,*args):self.close()

    @contextlib.contextmanager
    def parent(self,relative,*,create=False):
        need(isinstance(relative,str) and 0<len(relative)<=300 and not relative.startswith("/")
             and all(x not in ("",".","..") for x in relative.split("/")),"native relative target")
        fd=os.dup(self.rootfd)
        try:
            for part in relative.split("/")[:-1]:
                if create:
                    try:os.mkdir(part,0o700,dir_fd=fd)
                    except FileExistsError:pass
                child=os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                m=os.fstat(child)
                need(m.st_dev==self.root_identity[0] and m.st_uid==m.st_gid==0 and not(m.st_mode&0o022),
                     "native target traverses foreign filesystem/parent")
                os.close(fd);fd=child
            yield fd,relative.rsplit("/",1)[-1]
        finally:os.close(fd)

    def ensure_state(self):
        with self.parent(STATE_REL+"/placeholder",create=True) as (fd,_):
            s=os.fstat(fd)
            need(stat.S_IMODE(s.st_mode)==0o700,"private native state mode")
        return self.root/STATE_REL

    def open_regular(self,relative,flags=os.O_RDONLY,maximum=16*1024*1024):
        with self.parent(relative) as (parent,name):
            fd=os.open(name,flags|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
        m=os.fstat(fd)
        if not(stat.S_ISREG(m.st_mode) and m.st_uid==m.st_gid==0 and m.st_nlink==1 and
               not(m.st_mode&0o6022) and m.st_size<=maximum):
            os.close(fd);raise Rejected("native fixed regular file identity")
        return fd

    def observe(self,relative,*,body=True,maximum=64*1024*1024):
        with self.parent(relative) as (parent,name):
            try:s=os.stat(name,dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError:return {"absent":True}
            out={"node":node(s),"f9":list(f9(s))}
            if stat.S_ISREG(s.st_mode):
                out["type"]="0"
                if body:
                    need(s.st_size<=maximum,"native regular body exceeds fixed bound")
                    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
                    try:
                        before=os.fstat(fd);need(f9(before)==f9(s) and s.st_nlink==1,"native original regular identity")
                        out.update(bytes=s.st_size,sha256=hash_fd(fd))
                        need(f9(os.fstat(fd))==f9(s),"native original body changed")
                    finally:os.close(fd)
            elif stat.S_ISLNK(s.st_mode):
                out.update(type="2",target=os.readlink(name,dir_fd=parent))
            elif stat.S_ISDIR(s.st_mode):out["type"]="5"
            else:raise Rejected("special file in native package/config scope")
            need(f9(os.stat(name,dir_fd=parent,follow_symlinks=False))==f9(s),"native named identity changed")
            return out

    def check_root(self):
        s=self.root.lstat()
        need([s.st_dev,s.st_ino]==self.root_identity and
             stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0 and not(s.st_mode&0o022),
             "original native root replaced")

    def query_all(self):
        args=["--admindir="+str(self.root/"var/lib/dpkg"),"-W",
              "-f="+chr(36)+"{binary:Package}\t"+chr(36)+"{Version}\t"+chr(36)+"{db:Status-Abbrev}\n"]
        r=fixed_tool("dpkg-query",args,seconds=60)
        need(r["exit"]==0,"actual package database query failed")
        result={}
        for line in r["stdout"].decode("utf-8","strict").splitlines():
            p=line.split("\t");need(len(p)==3 and p[0] not in result,"actual package database row")
            result[p[0]]={"version":p[1],"status":p[2]}
        need(50<=len(result)<=6000,"complete native package database required")
        return result

    def five_rows(self,all_rows):
        out={}
        for role in ROLES:
            candidates=[k for k in (NAMES[role]+":amd64",NAMES[role]) if k in all_rows]
            need(len(candidates)==1,"one actual native amd64 package row")
            out[role]=(candidates[0],all_rows[candidates[0]])
        return out

    def audit(self):
        result=fixed_tool("dpkg",["--root="+str(self.root),"--audit"],seconds=60)
        need(result["exit"]==0 and not result["stdout"].strip() and not result["stderr"].strip(),
             "normal package database is not completely configured")

    def private_metadata(self):
        result={}
        for path in PRIVATE_METADATA:
            try:result[path]=self.observe(path,body=False)
            except FileNotFoundError:result[path]={"absent":True}
        return result

    def public_configs(self):
        paths=set(DISPLAY_CONFIG)
        for role in ROLES:
            raw=self.payloads[role]["old"]["control_bodies"].get("conffiles",b"")
            need(raw==self.payloads[role]["new"]["control_bodies"].get("conffiles",b""),"unchanged conffile declaration")
            for line in raw.decode().splitlines():
                path=line.split()[0]
                need(path.startswith("/etc/") and not line.endswith("remove-on-upgrade"),"fixed native conffile scope")
                paths.add(path[1:])
        result={}
        for path in sorted(paths):
            try:result[path]=self.observe(path,maximum=MAX_CONFIG)
            except FileNotFoundError:result[path]={"absent":True}
        return result

    def backup_public_configs(self,configs):
        # These are only the original declared public conffiles and fixed
        # display-manager selection, never account, SSH key or user data.
        # Keep a recoverable original even if a normal maintainer script fails.
        # A changed live conffile still fails closed; rollback never overwrites
        # a later administrator edit merely because a backup exists.
        result={};total=0
        for number,(path,observed) in enumerate(sorted(configs.items())):
            if observed.get("absent") or observed["type"]!="0":continue
            need(observed["bytes"]<=MAX_CONFIG,"native public configuration bound")
            total+=observed["bytes"];need(total<=8*MAX_CONFIG,"native configuration total bound")
            with self.parent(path) as (parent,name):
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
                try:
                    before=os.fstat(fd)
                    need(list(f9(before))==observed["f9"] and before.st_nlink==1,
                         "original public configuration changed before backup")
                    data=bytearray()
                    while chunk:=os.read(fd,65536):
                        data.extend(chunk);need(len(data)<=MAX_CONFIG,"native configuration grew")
                    need((len(data),hashlib.sha256(data).hexdigest())==
                         (observed["bytes"],observed["sha256"]),"original configuration body changed")
                    xattrs={}
                    for key in sorted(os.listxattr(fd)):
                        need(len(xattrs)<32 and len(key)<=255,"native configuration xattr bound")
                        value=os.getxattr(fd,key)
                        need(len(value)<=65536,"native configuration xattr size")
                        xattrs[key]=base64.b64encode(value).decode("ascii")
                    need(f9(os.fstat(fd))==f9(before) and
                         f9(os.stat(name,dir_fd=parent,follow_symlinks=False))==f9(before),
                         "original public configuration replaced during backup")
                finally:os.close(fd)
            filename=f"public-config-{number:03d}.original"
            new_file(self.attempt/filename,bytes(data),0o400)
            result[path]={"file":filename,"bytes":len(data),"sha256":observed["sha256"],
                          "original_node":observed["node"],"original_xattrs":xattrs}
        return result

    def compare_configs(self):
        actual=self.public_configs()
        need(set(actual)==set(self.snapshot["public_configs"]),"native config scope")
        for path,old in self.snapshot["public_configs"].items():
            new=actual[path]
            if old.get("absent"):
                need(new.get("absent"),"unexpected new native conffile")
                continue
            need(not new.get("absent") and old["type"]==new["type"],"native conffile type changed")
            need(all(old["node"][k]==new["node"][k] for k in ("mode","uid","gid")),"native conffile owner/mode changed")
            if old["type"]=="0":
                need((old["bytes"],old["sha256"])==(new["bytes"],new["sha256"]),"original native conffile changed")
            elif old["type"]=="2":need(old["target"]==new["target"],"original display-manager selection changed")
        need(self.private_metadata()==self.snapshot["private_metadata"],"original account/SSH/home metadata changed")
        return actual

    def check_payload(self,kind,*,conffiles=True):
        exempt=set(self.public_configs()) if conffiles else set()
        checked=0
        for role in ROLES:
            for relative,row in self.payloads[role][kind]["payload"].items():
                if relative in exempt:continue
                actual=self.observe(relative)
                need(not actual.get("absent") and actual["type"]==row["type"],"native payload type/missing: "+relative)
                need(all(actual["node"][k]==row[k] for k in ("mode","uid","gid")),"native payload owner/mode: "+relative)
                if row["type"]=="0":
                    need((actual["bytes"],actual["sha256"])==(row["bytes"],row["sha256"]),"native payload bytes: "+relative)
                elif row["type"]=="2":need(actual["target"]==row["target"],"native payload alias: "+relative)
                checked+=1
        return checked

    def event(self,stage,**fields):
        need(self.attempt is not None and self.sequence<64,"native transaction journal bound")
        self.sequence+=1
        value={"schema":"droidloom-normal-native-event-v1","attempt":self.attempt.name,
               "sequence":self.sequence,"stage":stage,"monotonic_ns":time.monotonic_ns(),**fields}
        new_file(self.attempt/f"EVENT-{self.sequence:04d}.json",canonical(value),0o400)
        fd=os.open(self.attempt,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
        self.history.append(value)

    def begin(self):
        self.check_root();self.audit()
        baseline=self.query_all();five=self.five_rows(baseline)
        need(all(row["version"]==OLD[role] and row["status"]=="ii " for role,(_,row) in five.items()),
             "actual original five normal packages required")
        self.check_payload("old")
        # New files may only occupy previously absent leaves, never another
        # package's existing bytes. Shared directories remain normal dpkg.
        for role in ROLES:
            old=self.payloads[role]["old"]["payload"]
            for path,row in self.payloads[role]["new"]["payload"].items():
                if path not in old and row["type"]!="5":
                    try:a=self.observe(path)
                    except FileNotFoundError:a={"absent":True}
                    need(a.get("absent"),"new native leaf already exists: "+path)
        self.attempt=self.state/(self.release_id+"-"+os.urandom(8).hex())
        os.mkdir(self.attempt,0o700)
        self.snapshot={"schema":"droidloom-normal-native-snapshot-v1","release_id":self.release_id,
                       "closure_sha256":CLOSURE_SHA,"root_identity":self.root_identity,
                       "all_packages":baseline,"public_configs":self.public_configs(),
                       "service_policy":self.observe("usr/sbin/policy-rc.d"),
                       "private_metadata":self.private_metadata(),
                       "boot_id":Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
        self.snapshot["public_config_backups"]=self.backup_public_configs(self.snapshot["public_configs"])
        new_file(self.attempt/"SNAPSHOT.json",canonical(self.snapshot),0o400)
        self.event("snapshot-complete")
        return self.attempt.name

    @contextlib.contextmanager
    def service_guard(self):
        relative="usr/sbin/policy-rc.d"
        fd=None;owned=False
        with self.parent(relative) as (parent,name):
            try:
                try:fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
                except FileNotFoundError:
                    # Persist the actual inode before create-only publication.
                    # Recovery never guesses ownership from matching bytes.
                    pending=self.attempt/("service-policy-"+str(self.sequence+1)+".pending")
                    new_file(pending,POLICY,0o755)
                    ps=pending.lstat()
                    self.event("service-policy-prepared",guard={"owned":True,"node":node(ps),
                               "sha256":hashlib.sha256(POLICY).hexdigest()},pending=pending.name)
                    libc=ctypes.CDLL(None,use_errno=True)
                    rename=libc.renameat2
                    rename.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)
                    rename.restype=ctypes.c_int
                    rc=rename(-100,os.fsencode(pending),parent,os.fsencode(name),1)
                    if rc:raise OSError(ctypes.get_errno(),"create-only service policy publication")
                    pd=os.open(".",os.O_RDONLY|os.O_DIRECTORY,dir_fd=parent);os.fsync(pd);os.close(pd)
                    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);owned=True
                before=os.fstat(fd)
                need(stat.S_ISREG(before.st_mode) and before.st_uid==before.st_gid==0 and
                     before.st_nlink==1 and stat.S_IMODE(before.st_mode)==0o755 and
                     os.read(fd,len(POLICY)+1)==POLICY,"unknown service policy blocks cold native transaction")
                if not owned and self.snapshot["service_policy"].get("absent"):
                    owned=any(e.get("stage")=="service-policy-prepared" and
                              e.get("guard",{}).get("owned") is True and
                              e["guard"]["node"]==node(before) and
                              e["guard"]["sha256"]==hashlib.sha256(POLICY).hexdigest()
                              for e in self.history)
                    need(owned,"unrecorded service policy inode blocks recovery")
                elif not owned:
                    old=self.snapshot["service_policy"]
                    need(not old.get("absent") and old["node"]==node(before) and
                         old.get("sha256")==hashlib.sha256(POLICY).hexdigest(),
                         "original service policy replaced")
                self.event("service-policy-held",guard={"owned":owned,"node":node(before),
                           "sha256":hashlib.sha256(POLICY).hexdigest()})
                try:yield
                finally:
                    after=os.fstat(fd);named=os.stat(name,dir_fd=parent,follow_symlinks=False)
                    need(f9(before)==f9(after)==f9(named),"service policy replaced during normal dpkg")
                    if owned:
                        os.unlink(name,dir_fd=parent)
                        pd=os.open(".",os.O_RDONLY|os.O_DIRECTORY,dir_fd=parent);os.fsync(pd);os.close(pd)
                    self.event("service-policy-restored",owned_guard_removed=owned)
            finally:
                if fd is not None:os.close(fd)

    def run_dpkg(self,stage,args,borrowed=()):
        self.check_root();self.event(stage+"-started",arguments=args)
        result=fixed_tool("dpkg",["--root="+str(self.root),*args],pass_fds=borrowed)
        out=stage+f"-{self.sequence:04d}.stdout";err=stage+f"-{self.sequence:04d}.stderr"
        new_file(self.attempt/out,result["stdout"],0o400);new_file(self.attempt/err,result["stderr"],0o400)
        self.event(stage+"-ended",exit_code=result["exit"],tool=result["tool"],
                   stdout={"file":out,"bytes":len(result["stdout"]),"sha256":hashlib.sha256(result["stdout"]).hexdigest()},
                   stderr={"file":err,"bytes":len(result["stderr"]),"sha256":hashlib.sha256(result["stderr"]).hexdigest()})
        need(result["exit"]==0,"normal native dpkg "+stage+" failed")
        return result

    @contextlib.contextmanager
    def package_fds(self,kind):
        with contextlib.ExitStack() as stack:
            fds=[]
            for role in ROLES:
                p=self.packages[role][kind]
                fd,st=stack.enter_context(held(p["path"],root=True,modes={0o400,0o444},maximum=16*1024*1024))
                need((st.st_size,hash_fd(fd))==(p["bytes"],p["sha256"]),"held normal native archive")
                fds.append(fd)
            yield fds

    def unpack(self,kind):
        with self.package_fds(kind) as fds:
            return self.run_dpkg("unpack-"+kind,["--no-triggers","--unpack",*[f"/proc/self/fd/{fd}" for fd in fds]],fds)

    def configure(self,kind):
        return self.run_dpkg("configure-"+kind,["--configure",*[NAMES[r]+":amd64" for r in ROLES]])

    def verify_installed(self,kind):
        self.check_root();self.audit()
        current=self.query_all();five=self.five_rows(current)
        wanted=NEW if kind=="new" else OLD
        need(all(row["version"]==wanted[role] and row["status"]=="ii " for role,(_,row) in five.items()),
             "actual configured five-package version closure")
        keys={key for key,_ in five.values()}
        need({k:v for k,v in current.items() if k not in keys}==
             {k:v for k,v in self.snapshot["all_packages"].items() if k not in keys},
             "native transaction changed another package state")
        n=self.check_payload(kind);configs=self.compare_configs()
        if kind=="old":
            for role in ROLES:
                old=self.payloads[role]["old"]["payload"]
                for path,row in self.payloads[role]["new"]["payload"].items():
                    if path not in old and row["type"]!="5":
                        try:a=self.observe(path)
                        except FileNotFoundError:a={"absent":True}
                        need(a.get("absent"),"new native leaf remains after normal downgrade")
        self.event("verified-"+kind,actual_package_rows={r:row for r,(_,row) in five.items()},
                   whole_payload_members=n,configuration_semantics_preserved=True,
                   private_metadata_unchanged=True,package_state_sha256=hashlib.sha256(canonical(current)).hexdigest())
        return n

    def apply(self):
        need(self.snapshot is not None,"native snapshot required")
        with self.service_guard():
            self.unpack("new");self.configure("new");n=self.verify_installed("new")
        self.event("normal-native-installed",members=n,runtime_qualified=False,physical_activation=False)

    def rollback(self):
        need(self.snapshot is not None,"original native snapshot required")
        current=self.query_all();five=self.five_rows(current)
        need(all(row["version"] in (OLD[role],NEW[role]) for role,(_,row) in five.items()),
             "foreign native package version blocks rollback")
        # The five original, normal archives are always reinstalled, including
        # a half-installed package after a genuine interrupted/failed unpack.
        with self.service_guard():
            self.unpack("old");self.configure("old");n=self.verify_installed("old")
        self.event("normal-native-rolled-back",members=n,runtime_qualified=False)

def physical_inputs(deployment_id,native_id):
    digest(deployment_id);digest(native_id)
    original_cold_authority()
    authority=actual_acceptance_binding(deployment_id)
    need(isinstance(authority,dict) and authority.get("native_release_id")==native_id
         and authority.get("deployment_id")==deployment_id,"same owned runtime/private/native release authority")
    bundle=Path("/var/lib/droidloom-maintenance/releases")/deployment_id/"native"
    verify_bundle(bundle,native_id,True)
    return bundle

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation",choices=("apply","rollback"))
    p.add_argument("deployment_id");p.add_argument("native_release_id")
    p.add_argument("--attempt")
    args=p.parse_args()
    bundle=physical_inputs(args.deployment_id,args.native_release_id)
    need((args.operation=="rollback")==bool(args.attempt),"rollback needs original durable attempt")
    with NativeTransaction(Path("/"),bundle,args.native_release_id,existing=args.attempt) as tx:
        if args.operation=="apply":tx.begin();tx.apply()
        else:tx.rollback()
        print(canonical({"attempt":tx.attempt.name,"normal_operation":args.operation,
                         "runtime_qualified":False,"physical_activation":False}).decode(),end="")
if __name__=="__main__":main()
