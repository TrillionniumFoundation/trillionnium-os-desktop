#!/usr/bin/env python3
"""Run the pinned C ELF cases on host Linux with captured loader/libs.

NO chroot, guest, QEMU or storage isolation is claimed. All filesystem writes
stay in a throwaway scratch; system glibc loader may still resolve implicit host
services, NSS and TLS. Hepta requires its own real trace.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import tempfile
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

runner=load("a04_run",HERE/"run.py")
guest=load("a04_guest",HERE/"guest.py")
capture=load("a04_capture",ROOT/"support/rootfs/capture.py")


def run(root,manifest_path,reference):
    root=root.resolve()
    manifest_path=manifest_path.resolve()
    capture.verify(root,manifest_path)
    manifest=json.loads(manifest_path.read_text())
    binaries={x["name"]:x for x in manifest["elf"]}
    lib_path=str(root/"lib/x86_64-linux-gnu")
    env=os.environ.copy()
    for name in ("LD_PRELOAD", "LD_AUDIT", "LD_DEBUG", "LD_ORIGIN_PATH"):
        env.pop(name,None)
    env.update({"LC_ALL":"C","TZ":"UTC","LD_LIBRARY_PATH":lib_path})
    cases={}
    with tempfile.TemporaryDirectory(prefix="a04-staged-rootfs-") as td:
        scratch=Path(td)
        for name,stem,case in guest.reference_elf_cases(reference):
            elf=binaries[guest.BINARY_FOR[stem]]
            stage=root/elf["path"].lstrip("/")
            actual_sha=runner.digest(stage)
            if actual_sha!=reference["binaries"][stem]["sha256"] or actual_sha!=elf["sha256"]:
                raise ValueError("rootfs ELF SHA mismatch: "+name)
            interpreter=reference["binaries"][stem]["interpreter"]
            if interpreter:
                loader=root/interpreter.lstrip("/")
                if not loader.is_file():
                    raise FileNotFoundError("missing staged loader: "+interpreter)
                command=[loader,"--library-path",lib_path,stage]
            else:
                command=[stage]
            case_dir=scratch/name
            case_dir.mkdir(parents=True)
            command.extend([case_dir] if stem.startswith("sqlite_") else [case,case_dir])
            cases[name]=runner.run_case(name,command,case_dir,env=env)
    counts={state:sum(x["status"]==state for x in cases.values())
            for state in ("pass","fail","not_run")}
    return {"schema":1,"suite":"a04-host-staged-loader-elf-only",
            "platform":{"system":platform.system(),"machine":platform.machine(),
                        "release":platform.release(),"execution":"host_linux_no_chroot"},
            "binaries":reference["binaries"],"cases":dict(sorted(cases.items())),
            "counts":counts,"rootfs_manifest_sha256":runner.digest(manifest_path),
            "staged_glibc_lib_path":"/lib/x86_64-linux-gnu",
            "guest_execution_verified":False,
            "all_staged_elf_passed":counts["pass"]==len(cases) and counts["fail"]==0}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rootfs",type=Path,required=True)
    ap.add_argument("--manifest",type=Path,required=True)
    ap.add_argument("--reference",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    try:
        result=run(args.rootfs,args.manifest,json.loads(args.reference.read_text()))
    except (OSError,ValueError,RuntimeError,KeyError) as e:
        ap.exit(2,"invalid staged rootfs/input: "+str(e)+"\n")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"counts":result["counts"],
                      "all_staged_elf_passed":result["all_staged_elf_passed"],
                      "guest_execution_verified":False}))
    return 0 if result["all_staged_elf_passed"] else 1


if __name__=="__main__":
    sys.exit(main())
