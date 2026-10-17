#!/usr/bin/env python3
import datetime,difflib,hashlib,json,os,pathlib,stat,subprocess,tarfile
OUT=pathlib.Path(__file__).resolve().parent
SCRATCH=pathlib.Path("/workspace/scratch/ae1a8cf05419/integration-case-target")
REPO=OUT.parents[3]
ready=json.loads((OUT/"source-validation-ready.json").read_text())
for rel,binding in ready["files"].items():
 assert hashlib.sha256((OUT/"sources/fixed"/rel).read_bytes()).hexdigest()==binding["sha256"]
members=[];links=[];excluded=[]
with tarfile.open(OUT/"raw.tar.gz","w:gz",dereference=False) as tf:
 for directory,dirs,files in os.walk(SCRATCH,followlinks=False):
  here=pathlib.Path(directory)
  for name in list(dirs):
   p=here/name
   if p.is_symlink():
    links.append({"path":str(p.relative_to(SCRATCH)),"link":os.readlink(p)})
    dirs.remove(name)
   elif name=="__pycache__":
    excluded.append(str(p.relative_to(SCRATCH)));dirs.remove(name)
  for name in sorted(files):
   p=here/name;relative=p.relative_to(SCRATCH)
   if p.is_symlink():
    links.append({"path":str(relative),"link":os.readlink(p)});continue
   if name.endswith(".pyc"):
    excluded.append(str(relative));continue
   a=p.stat();raw=p.read_bytes();z=p.stat()
   assert stat.S_ISREG(a.st_mode) and (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns),str(p)
   members.append({"path":str(relative),"size":len(raw),"sha256":hashlib.sha256(raw).hexdigest()})
   tf.add(p,arcname=str(relative),recursive=False)
with tarfile.open(OUT/"raw.tar.gz","r:gz") as tf:
 names={m.name:m for m in tf.getmembers()}
 assert len(names)==len(members)
 for row in members:
  raw=tf.extractfile(names[row["path"]]).read()
  assert len(raw)==row["size"] and hashlib.sha256(raw).hexdigest()==row["sha256"]
manifest={"regular_members":members,"symlink_metadata_only_not_followed":links,"excluded_bytecode_paths":excluded}
(OUT/"raw-members.json").write_text(json.dumps(manifest,indent=2)+"\n")
patch=[]
for rel in ready["files"]:
 new=(OUT/"sources/fixed"/rel).read_text()
 if rel.endswith("run.py"):
  old=(OUT/"sources/baseline/run.py").read_text()
 elif rel.endswith("README.md"):
  old=subprocess.check_output(["git","show","7997651e257e32d3161e1bb572d0130772009410:"+rel],cwd=REPO).decode()
 else: old=""
 patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile="baseline/"+rel if old else "/dev/null",tofile="fixed/"+rel))
(OUT/"case-targets.patch").write_text("".join(patch))
report={
 "frozen_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "freezer_sha256":hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
 "source_files":ready["files"],"baseline_run_matches_commit":"7997651e257e32d3161e1bb572d0130772009410",
 "pinned_SDK_base_crate_source_sha256":hashlib.sha256((OUT/"sources/base-crate-d895.rs").read_bytes()).hexdigest(),
 "diagnosis":{"native_failure":"case20 work_in_workspace failed before any guest with OSDK6 and dependency pointing to previous case root/myos instead of root/myworkspace/myos","source_verification":"Pinned SDK compares Cargo.toml/main/linkers; unchanged9338 source-built binary normally regenerates correct changed path in actual small probe. The failure is not attributed to a missing manifest comparison.","writer":"unknown; no attribution","solution":"Exclusive per-case CARGO_TARGET_DIR/private osdk root plus three verified shared Cargo artifact directory symlinks; no generated output cleanup/copy or shared osdk link","before_Cargo_preflight":"Cache root/profile NOFOLLOW+identity checks before prepare_harness and any Cargo action; prior missing/file/symlink roots and foreign profile links rejected","preservation":"Existing target/profile entries fail without replacement; partial owned directories and old shared osdk remain untouched"},
 "validation":{
  "baseline_public_entry_red":{"I":1,"IO":1,"expected_assertion_failures":2,"directory":"raw/red","scope":"Real runner orchestration with subprocess fixture child retaining stale generated manifest; not actual Cargo/OSDK"},
  "intermediate_targeted":{"I":8,"IO":8,"exit_codes":[0,0],"directory":"raw/green-targeted","not_final_source":"before preflight and two additional final tests"},
  "first_full":{"mode":"I","tests":139,"passed":138,"failures":1,"exit":1,"source_stable":True,"directory":"raw/green-full/I","failure":"existing test_runner.TimeoutTests ready file absent at 0.5second timeout; no production change or test relaxation; subsequent isolated and same-source full repeats passed"},
  "same_source_readiness_recheck":{"tests":1,"exit":0,"directory":"raw/readiness-recheck"},
  "intermediate_same_source_full_retry":{"I":139,"IO":139,"exit_codes":[0,0],"directory":"raw/green-full-retry","not_final_source":"before new cache preflight"},
  "final_full":{"I":141,"IO":141,"executions":282,"exit_codes":[0,0],"all_input_source_hashes_stable":True,"directory":"raw/green-full-final","scope":"Host fixtures including native host GDB lease lifecycle;0VM/0kernel/0actual22 matrix replay"},
  "independent_review":{"directory":"independent-review","preflight_same_fixture":"old source122557 reaches prepare+production collaborator; final run6d1ade rejects with calls=[] and foreignkeep intact","focused_tests_at_review":9,"later_10th_test":"prior missing/file root and exclusive newcache; included in final141 suite","reviewer_VM_Cargo_runs":0},
  "actual_source_SDK_probe":{"fixed_binary_sha256":"9338c5166093eb8133a0f6999e82ba70fe31f71ed26d3902b46887d194e122d9","final_directory":"raw/actual-sdk-probe-05-final","valid_outer_calls":5,"normal_regeneration":"two project roots/same crate name correctly regenerate before injection","fault":"restore saved prior manifest only into fixture-owned shared target/osdk/myos-run-base before actual Cargo metadata","red_missing_old_source_metadata_exit":101,"green_private_target_metadata_exit":0,"all_outer_SDK_exit_codes":6,"why_outer_exit6":"Each valid SDK call deliberately encounters fake Cargo build exit42 after real metadata; rustc/kernel build is never executed.","earlier_controls":"raw/actual-sdk-probe-03 and -04-production retained; earlier attempts01/02 configuration/PATH errors preserved"},
  "actual_tiny_host_Cargo":{"final_directory":"raw/tiny-host-cargo-final","build_invocations":2,"build_exit_codes":[0,0],"second_compiler_artifact_fresh":True,"actual_metadata_target_roots_distinct":True,"toolchain":"nightly-2026-07-21","cargo_sha256":"1e8bffe479c27798861dd7f0a3add4adb898879da0be8431fb48ff8c7cc78c03","kernel_builds":0,"VM_runs":0,"earlier_identical_scope":"raw/tiny-host-cargo"},
  "probe_setup_failures":{"attempt01":{"controller_exit":1,"SDK_exit":5,"reason":"fixture OSDK.toml direct is invalid; corrected to vmm-direct in next new directory"},"attempt02":{"controller_exit":1,"SDK_exit":12,"reason":"fixture PATH did not include fixed rustc; added exact toolchain/bin in next new directory"},"all_original_command_stderr_and_controller_versions_preserved":True}
 },
 "limits":["No new actual native22 acceptance; root owns later exact-published-source rerun.","Per-case osdk isolates both base crates and bundles across cases; within-case run/test can reuse/overwrite a same-name bundle. Persistent per-guest artifact snapshots remain a separately owned recorder task.","Shared debug/release/triple compiled artifacts can change as serial cases compile; their existence is never treated as freshness or retained guest acceptance.","No protection against privileged/adversarial path replacement during process execution; no historical writer attribution.","No core/upstream source changes, production service/disk/BIOS change, kernel version/toolchain upgrade, Ollama, commit/push by this agent."],
 "raw":{"member_count":len(members),"uncompressed_regular_bytes":sum(x["size"] for x in members),"sha256":hashlib.sha256((OUT/"raw.tar.gz").read_bytes()).hexdigest(),"size":(OUT/"raw.tar.gz").stat().st_size,"all_members_verified":True,"symlinks_not_dereferenced":len(links)}
}
(OUT/"report.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({"raw_member_count":len(members),"raw_bytes":report["raw"]["size"],"raw_sha256":report["raw"]["sha256"],"source_ready":True}))

