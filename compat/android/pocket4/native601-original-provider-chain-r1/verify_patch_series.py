#!/usr/bin/env python3
"""Replay the four ordinary patches against exact public preimages, without building."""
import hashlib,json,os,shutil,stat,subprocess,tempfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent

def relative(name):
 p=PurePosixPath(name)
 if not name or p.is_absolute() or ".." in p.parts or p.as_posix()!=name:raise ValueError("unsafe capsule member")
 return p

def read(path):
 with path.open("rb") as f:
  before=os.fstat(f.fileno())
  if not stat.S_ISREG(before.st_mode) or before.st_size>2*1024*1024:raise ValueError("regular bounded source required")
  raw=f.read(2*1024*1024+1);after=os.fstat(f.fileno())
 if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError("source changed")
 return raw

def matches(raw,row):
 return type(row["bytes"]) is int and len(raw)==row["bytes"] and hashlib.sha256(raw).hexdigest()==row["sha256"]

def main():
 manifest=json.loads(read(ROOT/"FILES.json"));pins=json.loads(read(ROOT/"SOURCE-PINS.json"))
 if manifest["schema"]!=1:raise ValueError("manifest schema")
 for name,row in manifest["files"].items():
  relative(name)
  if not matches(read(ROOT/name),row):raise ValueError("capsule digest: "+name)
 git=shutil.which("git")
 if git is None:raise RuntimeError("normal git is required for patch replay")
 env=dict(os.environ,GIT_CONFIG_NOSYSTEM="1",GIT_CONFIG_GLOBAL=os.devnull,GIT_OPTIONAL_LOCKS="0",GIT_TERMINAL_PROMPT="0")
 with tempfile.TemporaryDirectory(prefix="native601-public-source-replay-") as directory:
  work=Path(directory)
  for name,row in pins["stages"][0]["files"].items():
   relative(name);raw=read(ROOT/"preimages"/name)
   if not matches(raw,row):raise ValueError("baseline preimage: "+name)
   p=work/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  for entry in pins["patches"]:
   relative(entry["path"]);patch=ROOT/entry["path"]
   if not matches(read(patch),entry):raise ValueError("patch digest")
   argv=[git,"-c","core.hooksPath="+os.devnull,"apply","--whitespace=nowarn"]
   for extra in (["--check"],[]):subprocess.run(argv+extra+[str(patch)],cwd=work,env=env,check=True,timeout=20)
   target=pins["stages"][entry["after_stage"]]["files"]
   present={p.relative_to(work).as_posix() for p in work.rglob("*") if p.is_file()}
   if present!=set(target):raise ValueError("replayed source member set")
   for name,row in target.items():
    if not matches(read(work/name),row):raise ValueError("replayed exact source: "+name)
  if read(work/"android/native-generation-pair/source-lock.json")!=read(ROOT/"source-lock.json"):raise ValueError("final lock")
 print(json.dumps({"capsule":"native601-original-provider-chain-r1","normal_git_patch_replay":True,"patches":len(pins["patches"]),"normal_build_rerun":False,"runtime_qualified":False},sort_keys=True))

if __name__=="__main__":main()
