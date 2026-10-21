#!/usr/bin/env python3
"""Read only saved GET responses and source snapshots; no remote mutation."""
import datetime,hashlib,json,pathlib,re,subprocess
ROOT=pathlib.Path(__file__).resolve().parent
def j(name): return json.loads((ROOT/"api"/(name+".json")).read_text())
def src(name): return (ROOT/"blobs"/(name+".source")).read_text()
def lines(name,needle,radius=0):
 xs=src(name).splitlines();found=[]
 for i,x in enumerate(xs):
  if needle in x:
   found.append({"line":i+1,"text":"\n".join(xs[max(0,i-radius):i+radius+1])})
 return found
blobs=json.loads((ROOT/"blob-verification.json").read_text())["blobs"]
assert len(blobs)==18 and all(x["blob_matches"] for x in blobs)
validate=ROOT/"main-control-current"
inv=json.loads((validate/"invocation.json").read_text())
result=json.loads((validate/"result.json").read_text())
assert result["exit_code"]==0 and result["sources_stable"] and result["status_after"]=="" and result["README_bytes"]==0
test_counts={}
for mode in ("std","spin"):
 text=(validate/"script-logs"/(mode+"-tests.log")).read_text()
 rows=[list(map(int,m)) for m in re.findall(r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out",text)]
 assert rows and sum(x[0] for x in rows)==129 and all(not any(x[1:]) for x in rows)
 test_counts[mode]={"groups":rows,"passed":129,"failed":0,"ignored":0,"filtered":0,"doctests":0}
capture=json.loads((ROOT/"api"/"a01-lastgreen-joblogs.capture.json").read_text())
logs=capture["result"]["structuredContent"]["content"]
(ROOT/"a01-lastgreen-job.log").write_bytes(logs.encode("utf-8"))
counts=[int(x) for x in re.findall(r"Ran (\d+) tests in",logs)]
assert counts==[27,27,30,30,28,28]
assert "HEAD is now at 154d4a6 Merge 1e81ef45250dc16e903b05d0386e4f95f332aee9 into 82ef86a9d48851c17de2df0699b16f032be7dd3e" in logs
assert "154d4a62b18e3126a9dacd9e62df94f8e0536045" in logs
green_merge=j("a01-lastgreen-merge-commit")
assert [x["sha"] for x in green_merge["parents"]]==["82ef86a9d48851c17de2df0699b16f032be7dd3e","1e81ef45250dc16e903b05d0386e4f95f332aee9"]
latest_pr=j("final-pr-22");latest_run=j("final-a01-latest-run")
assert latest_pr["head"]["sha"]==latest_run["head_sha"]=="84f49159b066faa87a135c0662f9eba5be971e10"
current_merge=j("final-pr22-merge-commit")
assert [x["sha"] for x in current_merge["parents"]]==["40ca002fac0726b366726d3353916637b29adeae","84f49159b066faa87a135c0662f9eba5be971e10"]
assert j("issue-63")["state"]=="open"
assert j("issue-63-comments")==[]
assert "let Some(process) = thread.weak_process().upgrade() else {" in src("a06-cpu")
assert "pub(crate) fn charge_task_cpu" in src("a06-cpu")
assert j("search-a07-title")["total_count"]==0
assert j("a07-head-search")["total_count"]==0
assert not any(x["name"].startswith("agents/A07") for x in j("branches"))
assert "services" not in [x["path"] for x in j("main-root-tree")["tree"]]
assert "integration" not in [x["path"] for x in j("main-tests-tree")["tree"]]
compare=j("main-8f3bb49-to-40ca002")
assert not any(x["filename"].startswith(("kernel/","support/build/","libs/os-abi/","tests/abi/")) for x in compare["files"])
receipts=[]
for p in sorted((ROOT/"api").glob("*.receipt.json")):
 r=json.loads(p.read_text());r["receipt"]=str(p.relative_to(ROOT));receipts.append(r)
advice={
 "scope":"Read-only remote owner/CI refresh plus explicitly authorized exact-main host control validation; no kernel source edits, VM, effect authority, PR/issue/comment mutation.",
 "frozen_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "script_sha256":hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
 "capture_window":{"started":min(x["started"] for x in receipts),"ended":max(x["ended"] for x in receipts)},
 "observed_remote":{"main":j("final-main-branch")["commit"]["sha"],"a01":latest_pr["head"]["sha"],"pr22_merge":current_merge["sha"],"pr22_merge_parents":[x["sha"] for x in current_merge["parents"]]},
 "main_8f3_to_40ca":{"ahead_commits":compare["ahead_by"],"changed_paths":len(compare["files"]),"paths":[x["filename"] for x in compare["files"]],"kernel_build_abi_paths_changed":False,"control_source_changed":True},
 "owners":{
  "A05":{"pr":87,"head":j("pr-87")["head"]["sha"],"draft":j("pr-87")["draft"],"state":j("pr-87")["state"],"handler_blob":next(x["actual_git_blob"] for x in blobs if x["id"]=="a05-handler"),"verified_static":"Only QueryAbi is advertised; no effect operation or trusted CapSpace; decoder errors map to EINVAL and disabled operations ENOTTY in current owner handler. A00 #88 is separate pending correction.","owner_reported_guest":"Historical actual guest report is tied to earlier kernel/source 5fc3887dfc5833b61d11280eb1421bb7fd78648f and its earlier guest; this refresh did not rebuild/rerun or transfer that result to newer sources."},
  "A06":{"pr":18,"head":j("pr-18")["head"]["sha"],"draft":j("pr-18")["draft"],"cpu_blob":next(x["actual_git_blob"] for x in blobs if x["id"]=="a06-cpu"),"issue63_state":j("issue-63")["state"],"issue63_comments":0,"verified_static":"Issue63 cited cpu.rs blob is unchanged: charge_task_cpu returns after failed Weak<Process> upgrade; final runtime accounting concern remains. No new QEMU exploit proof or universal scheduler correctness inference."},
  "A04":{"pr":8,"head":j("pr-8")["head"]["sha"],"draft":j("pr-8")["draft"],"owner_reported_guest":{"cases":13,"pass":11,"remaining":["MSG_CMSG_CLOEXEC received descriptor FD_CLOEXEC clear","RLIMIT_NOFILE soft=32 accepts 256 opens"],"reexecuted_by_A01_this_refresh":False},"verified_main_static":"main ctrl_msg writes received files with FdFlags::empty and retains CLOEXEC TODO; open->FileTable::insert has no RLIMIT_NOFILE check. These snapshots support unresolved source gaps but are not a new runtime run.","exact_inputs":"Owner reports all four rebuilt ELF hashes differ from fixed rootfs manifest. Original exact bytes remain required; no substitution accepted."},
  "A07":{"named_branch_found":False,"named_pr_title_hits":0,"named_head_query_hits":0,"main_services_tree_present":False,"main_tests_integration_tree_present":False,"related_pr11":{"head":j("pr-11")["head"]["sha"],"merged":j("pr-11")["merged"],"scope":"organ-backend diagnostic/docs; no A07 native durable owner implementation"},"owner_reported":"A04 provider audit reports 0 concrete implementations / 0 composition attachments and no terminal receipt for fixed Hepta. This refresh did not independently execute Hepta or verify its external authenticated owner.","verified_limit":"No G2 closure evidence in fetched desktop branch/PR/root-tree scope. Does not prove absence in other repositories or inaccessible external systems."}
 },
 "ci":{
  "latest_observed":{"run":latest_run["id"],"head":latest_run["head_sha"],"status":latest_run["status"],"conclusion":latest_run["conclusion"],"job":j("final-a01-latest-jobs")["jobs"][0]["id"]},
  "earlier_green":{"run":38987804080,"head":"1e81ef45250dc16e903b05d0386e4f95f332aee9","checkout_merge":green_merge["sha"],"merge_parents":[x["sha"] for x in green_merge["parents"]],"job":117263227470,"status":"completed","conclusion":"success","host_fixture_groups":counts,"host_fixture_executions":sum(counts)},
  "limits":"Earlier170 host CI executions do not qualify current queued head, default AF_UNIX, KVM, VMX, kernel, G1 or G2. GitHub run.pull_requests[].head can reflect newer PR state; checkout log+actual git merge parents establish historical tree."
 },
 "main_control_current":{"head":inv["git_head"],"tree":inv["git_tree"],"command":inv["argv"],"exit":result["exit_code"],"tests":test_counts,"total_test_executions":258,"fmt":"pass","std_clippy_strict":"pass","spin_clippy_strict":"pass","no_std_x86_64_unknown_none":"pass","source_bytes_stable":True,"worktree_clean":True,"scope":"Host Rust model only;0 kernel builds,0VM,0Hepta effects"},
 "host_entry_review":{"directory":"host-entry-review","submanifest_sha256":"466ad0d9ddbdfaa2b1944651ade395fb8e8ca08b02fd49d86adacc16044cb1f6","conclusion":"No authorized available KVM/second dedicated host endpoint was found in reviewed repo docs/config. No credential search, no repeated capability probes. Does not prove external resources do not exist."},
 "verified_blob_count":18,
 "source_excerpts":{"a05_only_query":lines("a05-handler","supported_ops"),"a05_errors":lines("a05-handler","invalid HOS2 request"),"a06_final_charge":lines("a06-cpu","pub(crate) fn charge_task_cpu",10),"main_scm_cloexec":lines("main-unix-ctrl-msg","TODO: Deal with the"),"main_open_insert":lines("main-open","file_table_locked.insert"),"main_file_insert":lines("main-file-table","pub(crate) fn insert",4)},
 "claim_boundaries":["Owner-reported historical guest receipts retained and source-bound; this refresh does not reexecute owner guest workloads.","Source Git object identity and JSON facts verified by A01; dynamic behavior claims remain with original reports.","No other owner/core source changed; no issue/comment/PR mutation; no second host authorization inferred."],
 "capture_receipts":receipts
}
(ROOT/"report.json").write_text(json.dumps(advice,indent=2)+"\n")
print(json.dumps({"api_receipts":len(receipts),"verified_blobs":18,"main_control_executions":258,"earlier_CI_executions":170,"latest_CI":"queued","report":str(ROOT/"report.json")}))

