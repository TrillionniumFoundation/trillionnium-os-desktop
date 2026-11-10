#!/usr/bin/env python3
"""Replay the saved source-method regression on a POSIX host with a C++20 compiler.
This does not build or deploy Android SensorService. See README.md for substitutes.
The output directory must not exist. Original inputs are verified before and after.
"""
import argparse, hashlib, json, os, resource, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def digest(path):
    b=path.read_bytes()
    if len(b)>262144: raise RuntimeError("INPUT_TOO_LARGE")
    return hashlib.sha256(b).hexdigest()
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--compiler",default="g++")
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    compiler=shutil.which(args.compiler)
    if compiler is None: raise RuntimeError("COMPILER_NOT_FOUND")
    compiler=str(Path(compiler).resolve())
    pins=json.loads((ROOT/"TEST_INPUT_PINS.json").read_text())
    for name,pin in pins.items():
        if digest(ROOT/name)!=pin:raise RuntimeError("INPUT_PIN:"+name)
    args.output.mkdir(parents=False,exist_ok=False)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_CPU,(20,20))
    result={"scope":"host regression of exact production method bodies with stated substitutes","runs":[],"deployed":False}
    try:
        for label,flag in (("original",0),("candidate",1)):
            out=args.output/label;out.mkdir()
            exe=out/"regression"
            argv=[compiler,"-std=c++20","-O1","-g0","-Wall","-Wextra","-Werror","-pthread",
                  "-DEXPECT_CANDIDATE="+str(flag),"-I"+str(ROOT/"include"),
                  str(ROOT/(label+"-regression.cpp")),"-o",str(exe)]
            cp=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40)
            (out/"compile.stdout").write_bytes(cp.stdout);(out/"compile.stderr").write_bytes(cp.stderr)
            row={"label":label,"compile_argv":argv,"compile_rc":cp.returncode}
            result["runs"].append(row)
            if cp.returncode:raise RuntimeError("COMPILE_FAILED:"+label)
            rp=subprocess.run([str(exe)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
            (out/"run.stdout").write_bytes(rp.stdout);(out/"run.stderr").write_bytes(rp.stderr)
            row["run_rc"]=rp.returncode
            events=[json.loads(line) for line in rp.stdout.decode().splitlines()]
            row["events"]=events
            summary=events[-1]
            expected="CANDIDATE_CONTRACTS_PASS" if flag else "BASELINE_DEFECT_REPRODUCED"
            if rp.returncode or summary.get("summary")!=expected or summary.get("cases")!=17 or summary.get("unexpected")!=0 or summary.get("baseline_defects_reproduced")!=(0 if flag else 4):
                raise RuntimeError("REGRESSION_CONTRACT_FAILED:"+label)
        for name,pin in pins.items():
            if digest(ROOT/name)!=pin:raise RuntimeError("INPUT_CHANGED:"+name)
        result["state"]="ORIGINAL_DEFECT_REPRODUCED_CANDIDATE_HOST_CONTRACTS_PASS"
    except Exception as exc:
        result["state"]="FAILED";result["error_type"]=type(exc).__name__;result["error"]=str(exc)
    finally:
        (args.output/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"state":result["state"],"output":str(args.output)}))
    return 0 if result["state"]!="FAILED" else 1
if __name__=="__main__":sys.exit(main())
