#!/usr/bin/python3
"""Normal Ubuntu release packaging and fixed production maintenance.

No build/pack command grants runtime qualification. Production maintenance
never invokes dpkg, a shell, a caller executable, or a caller-selected path.
Cold installation is a separate original-Ubuntu/offline transaction.
"""
import argparse
import contextlib
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

SCHEMA = "droidloom-ubuntu-release-v1"
STORE = Path("/var/lib/droidloom-maintenance")
CONFIG = Path("/etc/droidloom-maintenance/installation.json")
CONTEXT = b"u:system_r:p4_linux_maintenance_t:s0"
RELEASE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
SAFE = re.compile(r"[A-Za-z0-9_./+-]+\Z")
KERNEL = "6.18.64-p4ctx6181-fusectl-aafs-peer-r1"
KERNEL_SHA = "19052ac77e40a86147f6bc186739763628916033f7c36f3448b4a872914090df"
SYSTEM = "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4"
TOOLS = {
 "systemctl": ("/usr/bin/systemctl",302112,"639bce3ce5c06b605079ea56f74e3f08216ddffcfa76e11f62073aa775180082"),
 "journalctl": ("/usr/bin/journalctl",97472,"d91b5f8629d41d7503fa00d8f4d58b6d0b72b5f0ca7b46667c8b5b1c59d460a2"),
 "grub-editenv": ("/usr/bin/grub-editenv",1368360,"2e4f8b60ba8712989f87d927d731a368af8620da1227a3090455ea7897ce1338"),
}
SYSTEM_UNITS = (
 "droidloom-instance-factory.service","droidloom-instance-launcher.service",
 "droidloom-manager-label.service","droidloom-production.service",
 "droidloom-early-observer.service","systemd-journald.service",
 "systemd-udevd.service","dbus.service","ssh.service","gdm.service",
 "systemd-logind.service","NetworkManager.service","systemd-resolved.service",
 "pocket4-live-camera.service",
)
USER_UNITS = ("droidloom-production-desktop.service","dbus.service","pipewire.service","wireplumber.service")
PROPERTIES = ("Id","LoadState","ActiveState","SubState","MainPID","InvocationID","ExecMainCode","ExecMainStatus","Result","ControlGroup")
JOURNAL_FIELDS = ("__CURSOR","_BOOT_ID","_PID","_UID","_EXE","_SYSTEMD_UNIT","_SYSTEMD_USER_UNIT",
                  "_SYSTEMD_INVOCATION_ID","__MONOTONIC_TIMESTAMP","PRIORITY","MESSAGE")

class Rejected(RuntimeError):
    pass

def need(value, why):
    if not value:
        raise Rejected(why)

def exact(value, keys, what):
    need(isinstance(value,dict) and set(value)==set(keys),what+" field set")
    return value

def integer(value, lo, hi, what):
    need(type(value) is int and lo<=value<=hi,what+" integer bound")
    return value

def digest(value):
    need(isinstance(value,str) and RELEASE.fullmatch(value),"lowercase SHA256 required")
    return value

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()+b"\n"

def f9(st):
    return (st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink,
            st.st_size,st.st_mtime_ns,st.st_ctime_ns)

def safe_relative(value):
    need(isinstance(value,str) and 0<len(value)<=300 and SAFE.fullmatch(value),"unsafe relative member")
    need(not value.startswith("/") and all(x not in ("",".","..") for x in value.split("/")),"unsafe member component")
    return value

def safe_absolute(value):
    need(isinstance(value,str) and value.startswith("/") and not value.startswith("//"),"absolute path required")
    safe_relative(value[1:])
    return Path(value)

@contextlib.contextmanager
def held(path, *, root=False, modes=None, maximum=16*1024**3, mutable_grub=False):
    """Pin every real component; the final original fd remains held."""
    path=safe_absolute(str(path))
    need(not mutable_grub or (root and str(path)=="/boot/grub/grubenv"),"only the fixed stock environment is mutable")
    fd=os.open("/",os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            child=os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            s=os.fstat(child)
            if root:
                need(s.st_uid==s.st_gid==0 and not(s.st_mode&0o022),"unprotected parent")
            os.close(fd);fd=child
        filefd=os.open(path.name,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
        try:
            before=os.fstat(filefd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,"single regular source required")
            need(0<=before.st_size<=maximum and not(before.st_mode&0o7022),"source size/mode")
            if root:
                need(before.st_uid==before.st_gid==0,"root-owned source required")
            if modes is not None:
                need(stat.S_IMODE(before.st_mode) in modes,"unexpected source mode")
            yield filefd,before
            after=os.fstat(filefd)
            named=os.stat(path.name,dir_fd=fd,follow_symlinks=False)
            if mutable_grub:
                need(f9(before)[:7]==f9(after)[:7]==f9(named)[:7],"original GRUB inode replaced")
            else:
                need(f9(before)==f9(after)==f9(named),"original source replaced or changed")
        finally:
            os.close(filefd)
    finally:
        os.close(fd)

def hash_fd(fd):
    os.lseek(fd,0,os.SEEK_SET)
    h=hashlib.sha256()
    while True:
        b=os.read(fd,1024*1024)
        if not b:
            break
        h.update(b)
    os.lseek(fd,0,os.SEEK_SET)
    return h.hexdigest()

def pin_shape(pin):
    exact(pin,("path","bytes","sha256"),"file pin")
    safe_absolute(pin["path"])
    integer(pin["bytes"],1,16*1024**3,"file bytes")
    digest(pin["sha256"])
    return pin

def read_pin(pin,maximum=8*1024*1024,root=False):
    pin_shape(pin)
    with held(pin["path"],root=root,maximum=maximum) as (fd,st):
        need(st.st_size==pin["bytes"] and hash_fd(fd)==pin["sha256"],"input pin mismatch")
        b=os.read(fd,maximum+1)
        need(len(b)==st.st_size,"short original input")
        return b

def json_bytes(b):
    def pairs(items):
        out={}
        for k,v in items:
            need(k not in out,"duplicate JSON field")
            out[k]=v
        return out
    return json.loads(b,object_pairs_hook=pairs)

def read_json_file(path,maximum=8*1024*1024,root=False,modes=None):
    with held(path,root=root,modes=modes,maximum=maximum) as (fd,st):
        b=os.read(fd,maximum+1)
        need(len(b)==st.st_size,"short JSON")
        return json_bytes(b),{"path":str(path),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}

def file_pin(path):
    with held(path) as (fd,st):
        return {"path":str(path),"bytes":st.st_size,"sha256":hash_fd(fd)}

def new_file(path,body,mode=0o444):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode)
    try:
        view=memoryview(body)
        while view:
            n=os.write(fd,view)
            need(n>0,"short write")
            view=view[n:]
        os.fchmod(fd,mode)
        os.fsync(fd)
    finally:
        os.close(fd)

def copy_pin(pin,target,mode):
    pin_shape(pin)
    with held(pin["path"]) as (fd,before):
        need(before.st_size==pin["bytes"] and hash_fd(fd)==pin["sha256"],"copy input mismatch")
        out=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode)
        h=hashlib.sha256();n=0
        try:
            while True:
                block=os.read(fd,1024*1024)
                if not block:break
                h.update(block);n+=len(block)
                view=memoryview(block)
                while view:
                    wrote=os.write(out,view)
                    need(wrote>0,"short copy")
                    view=view[wrote:]
            need(n==pin["bytes"] and h.hexdigest()==pin["sha256"],"source changed during copy")
            os.fchmod(out,mode);os.fsync(out)
        finally:
            os.close(out)
    need(file_pin(target)["sha256"]==pin["sha256"],"copy readback mismatch")

def mkdir_new(path,mode=0o700):
    need(path.is_absolute(),"fresh output must be absolute")
    # No mkdir(parents=True) through an unreviewed link.
    with_parent=path.parent
    fd=os.open("/",os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        for part in with_parent.parts[1:]:
            child=os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            os.close(fd);fd=child
        os.mkdir(path.name,mode,dir_fd=fd)
    finally:os.close(fd)

def bounded_process(argv, *, env=None, uid=None, seconds=30, maximum=8*1024*1024, pass_fds=()):
    """Bound output and lifetime, and always retire the original subprocess."""
    need(1<=seconds<=300 and 1024<=maximum<=64*1024*1024,"subprocess bounds")
    kw={"user":uid,"group":uid,"extra_groups":[]} if uid is not None else {}
    p=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       env=env or {"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","LC_ALL":"C","LANG":"C"},
                       close_fds=True,pass_fds=pass_fds,start_new_session=True,**kw)
    selector=selectors.DefaultSelector();out=bytearray();err=bytearray()
    for f,dest in ((p.stdout,out),(p.stderr,err)):
        os.set_blocking(f.fileno(),False);selector.register(f,selectors.EVENT_READ,dest)
    deadline=time.monotonic()+seconds
    try:
        while selector.get_map():
            left=deadline-time.monotonic()
            need(left>0,"fixed command deadline exceeded")
            for key,_ in selector.select(min(left,0.25)):
                b=os.read(key.fileobj.fileno(),65536)
                if b:
                    key.data.extend(b)
                    need(len(out)+len(err)<=maximum,"fixed command output bound exceeded")
                else:
                    selector.unregister(key.fileobj);key.fileobj.close()
        rc=p.wait(timeout=max(0.01,deadline-time.monotonic()))
        return {"exit":rc,"stdout":bytes(out),"stderr":bytes(err)}
    finally:
        selector.close()
        if p.returncode is None:
            # The original leader has not been reaped, so its private process
            # group cannot have been recycled. Retire build grandchildren too.
            try:os.killpg(p.pid,9)
            except ProcessLookupError:pass
            p.wait(timeout=5)
        for f in (p.stdout,p.stderr):
            if not f.closed:f.close()

def fixed_command(name,argv,*,uid=None,seconds=30,maximum=8*1024*1024,borrowed=()):
    path,size,sha=TOOLS[name]
    with held(path,root=True,modes={0o755},maximum=16*1024*1024) as (fd,st):
        need(st.st_size==size and hash_fd(fd)==sha,"stock command pin changed")
        env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","LC_ALL":"C","LANG":"C","SYSTEMD_COLORS":"0"}
        if uid is not None:
            need(uid==1000,"fixed native user")
            env.update(XDG_RUNTIME_DIR="/run/user/1000",DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus")
        # Executing the held original fd prevents a pathname replacement after
        # hashing. /proc/self/fd is private to this fixed child, not caller data.
        return bounded_process([f"/proc/self/fd/{fd}",*argv],env=env,uid=uid,
                               seconds=seconds,maximum=maximum,pass_fds=(fd,*borrowed))

def maintenance_context():
    need(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0,"root maintenance required")
    need(Path("/proc/self/attr/current").read_bytes().rstrip(b"\0\n")==CONTEXT,"fixed SELinux maintenance role")
    need(Path("/sys/fs/selinux/enforce").read_bytes().strip()==b"1","SELinux enforcing required")
    need(Path("/proc/self/uid_map").read_text().split()==["0","0","4294967295"],"initial user namespace required")
    need(os.readlink("/proc/self/fd/4")=="/usr/lib/droidloom/production/current/droidloom-maintenance.py",
         "normal C source handoff required")

def text_metadata(path,limit=4096):
    with open(path,"rb",buffering=0) as f:
        b=f.read(limit+1)
    need(len(b)<=limit,"public metadata bound")
    return b.decode("utf-8","strict").rstrip("\0\n")

def unit_state(names,user=False):
    try:
        r=fixed_command("systemctl",(["--user"] if user else [])+["--no-pager","show",*names,
                        "--property="+",".join(PROPERTIES)],uid=1000 if user else None,
                        seconds=10,maximum=128*1024)
    except (Rejected,OSError) as error:
        return {"exit":None,"units":[],"observation_failed":True,"error":str(error)[:512]}
    rows=[];row={}
    for line in r["stdout"].decode("utf-8","strict").splitlines()+[""]:
        if not line:
            if row:
                need(row.get("Id") in names,"unexpected systemd unit response")
                rows.append(row);row={}
            continue
        k,sep,v=line.partition("=")
        need(sep and k in PROPERTIES and k not in row,"unexpected systemd property")
        row[k]=v
    return {"exit":r["exit"],"units":rows,"stderr":r["stderr"].decode("utf-8","replace")[:4096]}

def status():
    boot=text_metadata("/proc/sys/kernel/random/boot_id",64)
    need(UUID.fullmatch(boot),"real boot identity")
    return {"schema":"droidloom-maintenance-status-v1","boot_id":boot,
            "observed_monotonic_ns":time.monotonic_ns(),"kernel":os.uname().release,
            "selinux_context":text_metadata("/proc/self/attr/current",256),
            "selinux_enforcing":text_metadata("/sys/fs/selinux/enforce",8)=="1",
            "apparmor_enabled":text_metadata("/sys/module/apparmor/parameters/enabled",8),
            "self_apparmor":text_metadata("/proc/self/attr/apparmor/current",512),
            "system_units":unit_state(SYSTEM_UNITS),"user_units":unit_state(USER_UNITS,True),
            "production_ready_claimed":False}

def installation():
    v,p=read_json_file(CONFIG,64*1024,True,{0o400,0o444})
    exact(v,("schema","release_id","root_uuid","original_entry","original_kernel",
             "grub_cfg","grubenv","installed_monotonic_ns"),"installation")
    need(v["schema"]=="droidloom-maintenance-installation-v1","installation schema")
    digest(v["release_id"]);need(UUID.fullmatch(v["root_uuid"]),"root UUID")
    need(v["original_entry"]=="gnulinux-simple-"+v["root_uuid"],"fixed original Ubuntu entry")
    need(v["original_kernel"]=="7.0.14-p4cred1","admitted original maintenance kernel")
    for k in ("grub_cfg","grubenv"):
        pin_shape(v[k])
    need(v["grub_cfg"]["path"]=="/boot/grub/grub.cfg" and v["grubenv"]["path"]=="/boot/grub/grubenv","fixed stock GRUB files")
    return v,p

def verify_release(release_id):
    digest(release_id)
    base=STORE/"releases"/release_id
    value,pin=read_json_file(base/"RELEASE.json",8*1024*1024,True,{0o444})
    need(pin["sha256"]==release_id,"release id is not its exact manifest bytes")
    exact(value,("schema","source_commit","source_tree","files","qualified"),"release")
    need(value["schema"]==SCHEMA and value["qualified"] is False,"normal candidate release contract")
    need(COMMIT.fullmatch(value["source_commit"]) and COMMIT.fullmatch(value["source_tree"]),"source identity")
    files=value["files"];need(isinstance(files,list) and 1<=len(files)<=128,"release inventory bound")
    seen=set()
    for item in files:
        exact(item,("path","bytes","sha256","mode"),"release member")
        rel=safe_relative(item["path"]);need("/" not in rel and rel not in seen,"flat unique release inventory")
        seen.add(rel);integer(item["mode"],0o400,0o755,"release mode")
        with held(base/rel,root=True,modes={item["mode"]}) as (fd,st):
            need(st.st_size==item["bytes"] and hash_fd(fd)==digest(item["sha256"]),"release member changed")
    return {"schema":"droidloom-maintenance-release-verification-v1","release_id":release_id,
            "release":pin,"files_verified":len(seen),"source_commit":value["source_commit"],
            "source_tree":value["source_tree"],"runtime_qualified":False}

def collect():
    result=status()
    matches=[]
    for n in SYSTEM_UNITS:
        if matches:matches.append("+")
        matches.append("_SYSTEMD_UNIT="+n)
    matches.extend(["+","_SYSTEMD_USER_UNIT=droidloom-production-desktop.service","_UID=1000"])
    r=fixed_command("journalctl",["--boot","--no-pager","--output=json",
         "--output-fields="+",".join(JOURNAL_FIELDS),"--lines=2000",*matches],
         seconds=30,maximum=8*1024*1024)
    rows=[]
    for line in r["stdout"].splitlines():
        value=json_bytes(line);need(isinstance(value,dict),"journal record")
        need(set(value)<=set(JOURNAL_FIELDS),"unexpected journal field")
        # Sender fields are copied from the actual root-readable journal.
        # A message's own text cannot replace trusted unit/PID/Invocation data.
        rows.append(value)
    result.update(schema="droidloom-maintenance-evidence-v1",journal_exit=r["exit"],
                  journal_stderr=r["stderr"].decode("utf-8","replace")[:4096],journal=rows,
                  journal_truncated_by_fixed_line_limit=len(rows)==2000)
    result["status_after"]=status()
    result["same_boot"]=result["boot_id"]==result["status_after"]["boot_id"]
    return result

def rollback():
    conf,pin=installation()
    grub=read_pin(conf["grub_cfg"],16*1024*1024,True)
    need(("'"+conf["original_entry"]+"'").encode() in grub,"original stock Ubuntu entry missing")
    # GRUB env is mutable by stock grub-reboot/grub-editenv. Bind its original
    # inode and root ownership, then read back the exact one-shot selection.
    with held("/boot/grub/grubenv",root=True,maximum=4096,mutable_grub=True) as (fd,st):
        need(st.st_size==1024 and os.pread(fd,24,0).startswith(b"# GRUB Environment Block"),"stock GRUB environment format")
        r=fixed_command("grub-editenv",[f"/proc/self/fd/{fd}","set","next_entry="+conf["original_entry"]],maximum=65536,borrowed=(fd,))
        need(r["exit"]==0,"stock grub-editenv failed")
        now=os.fstat(fd)
        need(now.st_dev==st.st_dev and now.st_ino==st.st_ino and now.st_size==1024,"GRUB environment inode replaced")
        body=os.pread(fd,1024,0)
        need(body.splitlines().count(("next_entry="+conf["original_entry"]).encode())==1,"one-shot Ubuntu entry readback")
        # This sole mutable-source scope permits only timestamp changes;
        # the original inode, ownership, mode, size and named identity remain.
    return {"schema":"droidloom-maintenance-rollback-v1","installation":pin,
            "original_entry":conf["original_entry"],"reboot_requested":False}

def reboot():
    conf,_=installation()
    grub=read_pin(conf["grub_cfg"],16*1024*1024,True)
    need(("'"+conf["original_entry"]+"'").encode() in grub,"original Ubuntu entry changed")
    with held("/boot/grub/grubenv",root=True,maximum=4096) as (fd,st):
        body=os.pread(fd,4096,0)
        need(body.splitlines().count(("next_entry="+conf["original_entry"]).encode())==1,
             "select the original Ubuntu entry before reboot")
    r=fixed_command("systemctl",["--no-block","--job-mode=replace-irreversibly","start","reboot.target"],maximum=65536)
    need(r["exit"]==0,"systemd did not accept the fixed reboot request")
    return {"schema":"droidloom-maintenance-reboot-v1","requested":True,
            "target":conf["original_entry"],"completed":False}

def host_manifest(pin):
    raw=read_pin(pin)
    value=json_bytes(raw)
    exact(value,("commit","tree","stage","files","directories"),"normal host manifest")
    need(COMMIT.fullmatch(value["commit"]) and COMMIT.fullmatch(value["tree"]),"normal host source")
    need(isinstance(value["files"],list) and 1<=len(value["files"])<=128,"normal host file count")
    expected={}
    for row in value["files"]:
        exact(row,("path","size","sha256","mode"),"normal host member")
        rel=safe_relative(row["path"]);need(rel.startswith(("usr/","etc/selinux/","etc/systemd/")),"host namespace")
        need(rel not in expected,"duplicate host file")
        integer(row["size"],0,32*1024*1024,"host file bytes");digest(row["sha256"])
        integer(row["mode"],0,0o7777,"host mode");need(not(row["mode"]&0o7022),"unsafe host mode")
        expected[rel]=row
    dirs=value["directories"]
    need(isinstance(dirs,list) and 1<=len(dirs)<=2,"normal host empty directories")
    allowed={"var/lib/droidloom-mac-calibration":0o700,"var/lib/droidloom-public-apks":0o755}
    for row in dirs:
        exact(row,("path","mode","uid","gid","empty"),"host directory")
        need(row["uid"]==row["gid"]==0 and row["empty"] is True,"normal empty directory ownership")
        need(row["path"] in allowed and row["mode"]==allowed[row["path"]],"unexpected host directory")
    return value,expected

def unpack_host(archive,manifest,out):
    value,expected=host_manifest(manifest)
    wantdirs={r["path"]:r["mode"] for r in value["directories"]};seen=set()
    with held(archive["path"]) as (fd,st):
        need(st.st_size==archive["bytes"] and hash_fd(fd)==digest(archive["sha256"]),"normal host archive pin")
        with os.fdopen(os.dup(fd),"rb") as stream,tarfile.open(fileobj=stream,mode="r:xz") as tar:
            for item in tar:
                rel=item.name.rstrip("/")
                safe_relative(rel)
                need(rel not in seen and item.uid==item.gid==0,"duplicate/non-root archive member")
                seen.add(rel);target=out/rel
                if item.isdir():
                    need(rel in wantdirs and item.mode==wantdirs[rel] and item.size==0,"unexpected archive directory")
                    target.mkdir(parents=True,exist_ok=True);target.chmod(item.mode)
                    continue
                need(item.isreg() and rel in expected,"archive is not the normal file inventory")
                row=expected[rel];need(item.size==row["size"] and item.mode==row["mode"],"normal member metadata")
                target.parent.mkdir(parents=True,exist_ok=True)
                f=tar.extractfile(item);need(f is not None,"missing member body")
                body=f.read(32*1024*1024+1)
                need(len(body)==row["size"] and hashlib.sha256(body).hexdigest()==row["sha256"],"normal member bytes")
                new_file(target,body,row["mode"])
    need(seen==set(expected)|set(wantdirs),"normal archive inventory incomplete")
    return value,expected

def pack_host(plan_path,output):
    need(os.geteuid()!=0,"normal packaging must run as an ordinary user")
    plan,_=read_json_file(plan_path,1024*1024)
    exact(plan,("schema","host_manifest","host_archive"),"host package plan")
    need(plan["schema"]=="droidloom-normal-host-deb-plan-v1","normal host plan")
    pin_shape(plan["host_manifest"]);pin_shape(plan["host_archive"])
    output=safe_absolute(str(output));mkdir_new(output)
    stage=output/"root";stage.mkdir(mode=0o700)
    manifest,expected=unpack_host(plan["host_archive"],plan["host_manifest"],stage)
    control=stage/"DEBIAN";control.mkdir(mode=0o755)
    desired={r["path"]:r["mode"] for r in manifest["directories"]}
    stage.chmod(0o755)
    for directory in stage.rglob("*"):
        if directory.is_dir():
            directory.chmod(desired.get(directory.relative_to(stage).as_posix(),0o755))
    version="0.1+git."+manifest["commit"]
    body=("Package: droidloom-shared-host\nVersion: "+version+
          "\nArchitecture: amd64\nMaintainer: Droidloom maintainers\n"
          "Section: admin\nPriority: optional\n"
          "Depends: python3.14-minimal, systemd, grub2-common, initramfs-tools, libselinux1, libapparmor1\n"
          "Description: Source-bound shared-kernel host and fixed maintenance entry\n"
          " Normal payload only. Activation is a separate reviewed cold transaction.\n").encode()
    new_file(control/"control",body,0o644)
    md5=[]
    for rel in sorted(expected):
        md5.append(hashlib.md5((stage/rel).read_bytes(),usedforsecurity=False).hexdigest()+"  "+rel)
    new_file(control/"md5sums",("\n".join(md5)+"\n").encode(),0o644)
    deb=output/"droidloom-shared-host.deb"
    r=bounded_process(["/usr/bin/dpkg-deb","--root-owner-group","--uniform-compression","-Zxz","-z3","--build",str(stage),str(deb)],
                       env={"PATH":"/usr/bin:/bin","LC_ALL":"C","SOURCE_DATE_EPOCH":"0","XZ_DEFAULTS":"-T1"},
                       seconds=300,maximum=1024*1024)
    new_file(output/"dpkg-deb.stdout",r["stdout"],0o444);new_file(output/"dpkg-deb.stderr",r["stderr"],0o444)
    need(r["exit"]==0,"normal Debian package build failed")
    built_pin=file_pin(deb)
    # Actual dpkg-deb extraction proves that no control script or unexpected
    # payload entered the package. The public candidate is never installed here.
    readback=output/"readback";readback.mkdir(mode=0o700)
    check=bounded_process(["/usr/bin/dpkg-deb","--extract",str(deb),str(readback)],seconds=300,maximum=1024*1024)
    need(check["exit"]==0,"normal Debian readback failed")
    got=set()
    for p in readback.rglob("*"):
        need(not p.is_symlink(),"Debian introduced a symlink")
        if p.is_file():
            rel=p.relative_to(readback).as_posix();got.add(rel)
            need(rel in expected,"unexpected Debian payload")
            row=expected[rel]
            with held(p,modes={row["mode"]}) as (fd,st):
                need(st.st_size==row["size"] and hash_fd(fd)==row["sha256"],"Debian payload readback mismatch")
    need(got==set(expected),"Debian payload incomplete")
    control_readback=output/"control-readback";control_readback.mkdir(mode=0o700)
    check=bounded_process(["/usr/bin/dpkg-deb","--control",str(deb),str(control_readback)],seconds=30,maximum=1024*1024)
    need(check["exit"]==0,"normal Debian control readback failed")
    need({p.name for p in control_readback.iterdir()}=={"control","md5sums"},"unexpected Debian maintainer script")
    for name in ("control","md5sums"):
        need((control_readback/name).read_bytes()==(control/name).read_bytes(),"Debian control bytes changed")
    need(file_pin(deb)==built_pin,"Debian archive changed during normal readback")

    for directory in readback.rglob("*"):
        if directory.is_dir():
            rel=directory.relative_to(readback).as_posix()
            need(stat.S_IMODE(directory.stat().st_mode)==desired.get(rel,0o755),"Debian directory mode changed")
    receipt={"schema":"droidloom-normal-host-deb-result-v1","source_commit":manifest["commit"],
             "source_tree":manifest["tree"],"plan":file_pin(plan_path),"host_manifest":plan["host_manifest"],
             "host_archive":plan["host_archive"],"package":file_pin(deb),
             "file_count":len(expected),"empty_directories":manifest["directories"],
             "normal_build_exit_code":0,"physical_install":False,"runtime_qualified":False}
    new_file(output/"RESULT.json",canonical(receipt),0o444)
    return receipt

def main():
    if len(sys.argv)>1 and sys.argv[1]=="--maintenance":
        maintenance_context()
        args=sys.argv[2:]
        need(args and args[0] in ("status","collect","verify","rollback","reboot"),"fixed maintenance action")
        action=args[0]
        need(len(args)==(2 if action=="verify" else 1),"fixed maintenance argument count")
        if action=="verify":result=verify_release(args[1])
        else:result={"status":status,"collect":collect,"rollback":rollback,"reboot":reboot}[action]()
    else:
        parser=argparse.ArgumentParser(description=__doc__)
        sub=parser.add_subparsers(dest="command",required=True)
        host=sub.add_parser("pack-host")
        host.add_argument("--plan",required=True,type=Path)
        host.add_argument("--output",required=True,type=Path)
        a=parser.parse_args()
        result=pack_host(a.plan,a.output)
    sys.stdout.buffer.write(canonical(result));sys.stdout.buffer.flush()

if __name__=="__main__":
    try:main()
    except (Rejected,OSError,ValueError,KeyError,tarfile.TarError) as e:
        print("droidloom-maintenance: "+str(e),file=sys.stderr)
        sys.exit(1)
