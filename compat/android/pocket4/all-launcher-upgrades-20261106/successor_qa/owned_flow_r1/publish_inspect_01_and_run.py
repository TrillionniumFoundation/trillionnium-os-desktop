#!/usr/bin/env python3
"""Publish one fresh inspection plan and enter the exact existing owned adapter."""
import hashlib,json,os,stat,sys
from pathlib import Path
ROOT=Path("/home/alex/work/pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb")
ADAPTER=Path("/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03/qa_adapter.py")
PLAN=Path("/home/alex/work/pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb/qa-inspect-01.plan.json")
PLAN_RAW="{\"schema\":1,\"operation\":\"inspect\",\"nonces\":{\"before\":\"f600dc0d4194e51e29f27ec93e07d0da\",\"inspect\":\"c7e4eacdf02d95131390e303f023d7f4\",\"after\":\"f2f1d466b82096eab6de831712a6c868\"}}\n".encode("utf-8")
PLAN_SHA="c169844c76247ef56a1048831ba5a593de666fcf95f0b6a4caafa6ff22c1e3dd"
ARGV=["/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03/qa_adapter.py","--execute-once","--interactive-production","--source-manifest-sha256","dfb9b6a483f1069847433152b9b2e8b0f1b2cdd571a1dbde3068fc9393ad62c4","--build-receipt","/home/alex/work/pocket4-successor-qa-build-b34f158f88bbebf112840fd88df25d03/build-result.json","--build-receipt-sha256","c0dd8117cdb7fa8b551e2a59b466c91d48ee2f2d9a98908f69b3d3fb8807bf3d","--apk-sha256","006b3bdd64fcd8a03a4ceac0d036b3b99906140feadee61d198756cb6c55c8d9","--signer-certificate-sha256","d48d103342b42791ae4e927d70258062d0de11f9acb9f32b4426aff583f27d6f","--plan","/home/alex/work/pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb/qa-inspect-01.plan.json","--plan-sha256","c169844c76247ef56a1048831ba5a593de666fcf95f0b6a4caafa6ff22c1e3dd","--step","inspect-01","--recorder-root","/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder","--flow-dir","/home/alex/work/pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb","--helper-uid","10157"]
FIELDS=("st_dev","st_ino","st_mode","st_uid","st_gid","st_nlink","st_size","st_mtime_ns","st_ctime_ns")
def need(ok,code):
    if not ok:raise RuntimeError(code)
def meta(s):return tuple(getattr(s,k) for k in FIELDS)
need(os.getuid()==os.geteuid()==0,"ROOT_EXISTING_FLOW_REQUIRED")
before=len(os.listdir("/proc/self/fd"))
need(ROOT.resolve()==ROOT and PLAN.parent==ROOT and ADAPTER.resolve()==ADAPTER,"EXACT_CANONICAL_PATHS")
info=ROOT.lstat()
need(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700,"EXISTING_PRIVATE_FLOW_REQUIRED")
fd=os.open(ADAPTER,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
try:
    first=os.fstat(fd)
    need(stat.S_ISREG(first.st_mode) and first.st_uid==0 and first.st_nlink==1 and first.st_size==29378,"EXACT_ROOT_ADAPTER_FILE")
    raw=bytearray()
    while len(raw)<=29378:
        part=os.read(fd,29379-len(raw))
        if not part:break
        raw.extend(part)
    need(len(raw)==29378 and hashlib.sha256(raw).hexdigest()=="ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c" and meta(first)==meta(os.fstat(fd))==meta(ADAPTER.lstat()),"PINNED_ADAPTER_CHANGED")
finally:os.close(fd)
need(hashlib.sha256(PLAN_RAW).hexdigest()==PLAN_SHA,"PLAN_PIN")
parsed=json.loads(PLAN_RAW)
need(set(parsed)=={"schema","operation","nonces"} and parsed["schema"]==1 and parsed["operation"]=="inspect","INSPECTION_ONLY_PLAN")
need(set(parsed["nonces"])=={"before","inspect","after"} and len(set(parsed["nonces"].values()))==3,"FRESH_PHASE_NONCES")
os.umask(0o077)
fd=os.open(PLAN,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
try:
    view=memoryview(PLAN_RAW)
    while view:
        count=os.write(fd,view)
        need(count>0,"PLAN_WRITE_PROGRESS")
        view=view[count:]
    os.fsync(fd)
finally:os.close(fd)
fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
try:os.fsync(fd)
finally:os.close(fd)
need(PLAN.read_bytes()==PLAN_RAW and len(os.listdir("/proc/self/fd"))==before,"PLAN_READBACK_AND_DESCRIPTOR_CLOSURE")
print(json.dumps({"schema":"pocket4-owned-inspection-plan-publication-v1","plan":str(PLAN),"bytes":len(PLAN_RAW),"sha256":PLAN_SHA,"new_plan_only":True,"UI_actions_before_adapter":0}),flush=True)
sys.argv=ARGV
exec(compile(bytes(raw),str(ADAPTER),"exec"),{"__name__":"__main__","__file__":str(ADAPTER)})
