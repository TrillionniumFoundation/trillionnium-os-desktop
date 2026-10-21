#!/usr/bin/env python3
import datetime, hashlib, json, os, pathlib, subprocess, sys, tarfile, time
REPO=pathlib.Path("/tmp/trillionnium-a01-main40ca002")
OUT=pathlib.Path(__file__).resolve().parent/"main-control-current"
OUT.mkdir(exist_ok=False)
env=os.environ.copy()
env.update(CARGO_HOME="/workspace/scratch/ae1a8cf05419/toolchains/cargo", RUSTUP_HOME="/workspace/scratch/ae1a8cf05419/toolchains/rustup", RUSTUP_TOOLCHAIN="nightly-2026-07-21", CARGO_TARGET_DIR="/tmp/trillionnium-a01-main40ca002-control-target", CARGO_BUILD_JOBS="2", CARGO_INCREMENTAL="0")
env["PATH"]=env["CARGO_HOME"]+"/bin:"+env["PATH"]
def git(*args): return subprocess.check_output(["git",*args],cwd=REPO,text=True).strip()
tracked=git("ls-files","libs/os-control","tests/control").splitlines()
selected=[p for p in tracked if pathlib.Path(p).suffix in (".rs",".toml",".lock",".sh")]
def binding():
 return {p:{"sha256":hashlib.sha256((REPO/p).read_bytes()).hexdigest(),"size":(REPO/p).stat().st_size,"blob":git("rev-parse","HEAD:"+p)} for p in selected}
before=binding()
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
envkeys=("PATH","CARGO_HOME","RUSTUP_HOME","RUSTUP_TOOLCHAIN","CARGO_TARGET_DIR","CARGO_BUILD_JOBS","CARGO_INCREMENTAL","RUSTFLAGS","RUSTDOCFLAGS","CARGO_ENCODED_RUSTFLAGS","RUSTC_WRAPPER","RUSTC_WORKSPACE_WRAPPER","A03_CARGO","LD_LIBRARY_PATH")
cmd=["sh","tests/control/run-validation.sh",str(OUT/"script-logs")]
inv={"started_utc":start,"cwd":str(REPO),"argv":cmd,"environment":{k:env.get(k) for k in envkeys},"git_head":git("rev-parse","HEAD"),"git_tree":git("rev-parse","HEAD^{tree}"),"status_before":git("status","--porcelain"),"sources_before":before,"runner_sha256":hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),"scope":"A03 control host validation only; no VM/kernel/Hepta durable acceptance"}
(OUT/"invocation.json").write_text(json.dumps(inv,indent=2)+"\n")
with tarfile.open(OUT/"sources.tar.gz","w:gz") as tf:
 for p in selected: tf.add(REPO/p,arcname=p,recursive=False)
with (OUT/"console.log").open("wb") as f:
 p=subprocess.run(cmd,cwd=REPO,env=env,stdout=f,stderr=subprocess.STDOUT)
after=binding()
result={"finished_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"exit_code":p.returncode,"sources_stable":before==after,"sources_after":after,"status_after":git("status","--porcelain"),"README_bytes":(REPO/"README.md").stat().st_size}
(OUT/"result.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({"exit_code":p.returncode,"sources_stable":before==after,"output":str(OUT)}))
sys.exit(p.returncode)

