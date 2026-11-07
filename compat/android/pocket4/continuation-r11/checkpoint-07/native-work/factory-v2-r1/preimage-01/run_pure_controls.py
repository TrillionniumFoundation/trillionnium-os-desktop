#!/usr/bin/env python3
"""Compile and exercise pure V2 protocol/parser code only; no service entry."""
from pathlib import Path
import hashlib,json,subprocess,shutil,sys
root=Path(__file__).resolve().parent
out=root/"controls-01"
out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
compiler=Path(shutil.which("g++")).resolve()
source_files=sorted([p for directory in ("include","source","engine-delta","tests") for p in (root/directory).rglob("*") if p.is_file()])
pins={str(p.relative_to(root)):sha(p) for p in source_files}
report={"schema":1,"scope":"actual V2 shared wire/context source, strict host build and pure controls; no service, socket, Android, namespace or mount operation",
        "compiler":{"path":str(compiler),"sha256":sha(compiler)},"sources":pins,"commands":[],
        "production_ready":False,"service_run":False,"Android_run":False}
def run(name,argv,expected=0):
    p=subprocess.run([str(a) for a in argv],capture_output=True,timeout=45,cwd=root)
    (out/(name+".stdout")).write_bytes(p.stdout);(out/(name+".stderr")).write_bytes(p.stderr)
    report["commands"].append({"name":name,"argv":[str(a) for a in argv],"returncode":p.returncode,
       "stdout_sha256":hashlib.sha256(p.stdout).hexdigest(),"stderr_sha256":hashlib.sha256(p.stderr).hexdigest()})
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    if p.returncode!=expected:
        raise RuntimeError(name+": unexpected exit "+str(p.returncode)+": "+p.stderr.decode(errors="replace")[:2000])
    return p
base=[compiler,"-std=c++20","-O2","-Wall","-Wextra","-Werror","-fno-exceptions","-fno-rtti","-I",root/"include","-I",root/"source"]
wire=root/"source/proc_maps_factory_wire.cc"
context=root/"source/factory_context.cc"
test=root/"tests/wire_context_controls.cc"
try:
    run("compile-factory",base+[root/"source/factory_main.cc",context,wire,"-o",out/"factory-v2"])
    p=run("factory-default-plan-only",[out/"factory-v2"])
    plan=json.loads(p.stdout)
    assert plan["service_started"] is False and plan["production_ready"] is False
    for label,extra in (("glibc",[]),("bionic-branch-fixture",["-D__BIONIC__"])):
        run("compile-"+label,base+extra+[test,context,wire,"-o",out/label])
        p=run("run-"+label,[out/label])
        rows=[json.loads(line) for line in p.stdout.splitlines()]
        assert rows[-1]["passed"]==17 and rows[-1]["failed"]==0
        assert rows[-1]["service_run"] is False
    mutations={
      "negative-kernel-loses-ST_VALID":("value.f_flags=w[kFsFlags];","value.f_flags=w[kFsFlags]&~UINT64_C(0x20);","all_120_kernel_statfs_bytes_including_ST_VALID_and_spares"),
      "negative-libc-gets-raw-flags":("KernelStatfsToLibc(value,result);","memcpy(result,&value,sizeof(value));","host_libc_conversion_clears_only_Bionic_ST_VALID")}
    for label,(old,new,case) in mutations.items():
        original=wire.read_text();assert original.count(old)==1
        target=out/(label+".cc");target.write_text(original.replace(old,new))
        run("compile-"+label,base+["-D__BIONIC__"]+[test,context,target,"-o",out/label])
        p=run("run-"+label,[out/label],expected=1)
        rows=[json.loads(line) for line in p.stdout.splitlines()]
        assert any(row.get("case")==case and row["pass"] is False for row in rows)
        assert rows[-1]["failed"]>0 and rows[-1]["service_run"] is False
    assert pins=={str(p.relative_to(root)):sha(p) for p in source_files}
    assert report["compiler"]["sha256"]==sha(compiler)
    report["state"]="PURE_CONTROLS_PASS";report["source_unchanged"]=True
    report["positive_controls_per_build"]=17;report["negative_mutants_detected"]=2
except BaseException as error:
    report["state"]="FAILED";report["error"]=repr(error)
finally:
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({"state":report["state"],"report":str(out/"report.json"),"sha256":sha(out/"report.json"),
                  "production_ready":False,"service_run":False}))
sys.exit(0 if report["state"]=="PURE_CONTROLS_PASS" else 1)
