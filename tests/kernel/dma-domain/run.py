#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Build an OSTD hardware test and prove two-device DMA isolation in QEMU."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import shutil
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "safety"))
from run import snapshot, save, require, digest
sys.path.insert(0, str(HERE))
from record import run_guest, command

TEST = "dma_domains_two_edu_devices_reject_cross_access_and_revoked_iova"
APPEND = "loglevel=error earlycon console=ttyS0 --"


def verdict(directory, iommu, smp, snoop=True):
    receipt_bytes = (directory / "qemu.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    raw = (directory / "serial.log").read_bytes()
    text = re.sub(r"\x1b\[[0-9;]*m", "", raw.decode(errors="replace"))
    if not iommu:
        marker = "HEPTA_DMA_DOMAINS_NO_IOMMU_REJECTED"
    elif not snoop:
        marker = "HEPTA_DMA_DOMAINS_UNSUPPORTED_REJECTED"
    else:
        marker = "HEPTA_DMA_DOMAINS_EDU_PASS cross-read cross-write revoke rebind queue-wrap"
    argv = receipt["argv"]
    expected = command(argv[0], directory, APPEND, smp, iommu, snoop)
    checks = {
        "schema": receipt["schema"] == "hepta.dma-domain-guest.v1",
        "profile": receipt["iommu"] is iommu and receipt["snoop_control"] is snoop
                   and receipt["smp"] == smp and argv == expected,
        "exit": receipt["exit"] == 33 and not receipt["timed_out"],
        "qemu": digest(Path(argv[0]).read_bytes()) == receipt["qemu_sha256"],
        "artifacts": receipt["artifacts_unchanged"] and all(
            receipt[key] == digest((directory / name).read_bytes())
            for name, key in [("kernel.elf", "kernel_sha256"), ("bios.bin", "bios_sha256"),
                              ("serial.log", "serial_sha256")]),
        "marker": text.count("HEPTA_DMA_DOMAINS_") == 1 and text.count(marker) == 1,
        "test": f"::{TEST} ..." in text and "1 passed; 0 failed;" in text
                and "[skipped:" not in text and "panic" not in text.lower()
                and "FAILED" not in text,
    }
    return {"passed": all(checks.values()), "checks": checks,
            "receipt_sha256": digest(receipt_bytes)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--smp", type=int, choices=(2,4), default=2)
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True,exist_ok=False)
    before = snapshot(); save(output / "source-before.json",before)
    result = {"schema":"hepta.dma-domain-stage.v1","passed":False,"production_qualified":False,"source_head":before["head"],"smp":args.smp}
    save(output / "result.json",result)
    lock = (ROOT / "support/build/out-kernel.lock").open("a")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with (output / "source-inputs.json").open("wb") as source_log:
        checked = subprocess.run([sys.executable, "-I", str(ROOT / "support/build/verify-source.py")],
                                 cwd=ROOT, stdout=source_log, stderr=subprocess.STDOUT)
    require(checked.returncode == 0, "pinned source inputs rejected; inspect source-inputs.json")
    env = dict(os.environ)
    home = Path(env.get("CARGO_HOME",str(Path.home()/".cargo")))
    require((home/"bin/cargo-osdk").is_file(),"worktree-specific OSDK required")
    env.update(PATH=str(home/"bin")+os.pathsep+env.get("PATH",""), OSDK_LOCAL_DEV="1", CARGO_BUILD_JOBS="2",
               OSDK_CARGO_LOCK=str(ROOT/"support/build/ktest/locks/ostd.Cargo.lock"),
               CARGO_TARGET_DIR=str(ROOT/"kernel/asterinas/target"), HEPTA_DMA_GUEST_DIR=str(output/"iommu"),
               HEPTA_DMA_SMP=str(args.smp), NETDEV="none",ENABLE_KVM="0",OVMF="off",SMP=str(args.smp),MEM="512M",
               BOOT_METHOD="vmm-direct",BOOT_PROTOCOL="multiboot",QEMU_DISPLAY="none")
    for key in ("RUSTFLAGS","CARGO_ENCODED_RUSTFLAGS"):
        env.pop(key,None)
    argv = ["cargo","+nightly-2026-07-21","osdk","test","--release",TEST,"--features=dma-domain-ktest",
            "--boot-method=vmm-direct","--grub-boot-protocol=multiboot",f"--qemu-exe={HERE/'record.py'}",
            "--kcmd-args=loglevel=error","--kcmd-args=earlycon","--kcmd-args=console=ttyS0"]
    save(output/"command.json", {"argv":argv,"cwd":str(ROOT/"kernel/asterinas/ostd"),
                                 "osdk_sha256":digest((home/"bin/cargo-osdk").read_bytes()),
                                 "rustc":subprocess.check_output(["rustc", "+nightly-2026-07-21", "-Vv"], text=True),
                                 "vdso_sha256":digest((Path(env["VDSO_LIBRARY_DIR"])/"vdso_x86_64.so").read_bytes()),
                                 "fixed_lock_sha256":digest(Path(env["OSDK_CARGO_LOCK"]).read_bytes())})
    with (output/"build.log").open("wb") as log:
        code = subprocess.run(argv,cwd=ROOT/"kernel/asterinas/ostd",env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    result["build_exit"] = code
    save(output/"result.json",result)
    generated = ROOT / "kernel/asterinas/target/osdk/ostd-test-base/Cargo.lock"
    if generated.is_file():
        shutil.copyfile(generated, output/"generated.Cargo.lock")
    require(generated.is_file() and generated.read_bytes() == Path(env["OSDK_CARGO_LOCK"]).read_bytes(),
            "generated test lock differs from pinned inputs")
    require(code == 0,"OSDK hardware test failed; inspect retained build and guest logs")
    result["iommu"] = verdict(output/"iommu",True,args.smp)
    save(output/"result.json",result)
    require(result["iommu"]["passed"],"actual two-EDU test did not pass")
    qemu = json.loads((output/"iommu/qemu.json").read_text())
    append = qemu["argv"][qemu["argv"].index("-append")+1]
    run_guest(output/"iommu/kernel.elf",append,output/"no-iommu",args.smp,False)
    result["no_iommu"] = verdict(output/"no-iommu",False,args.smp)
    run_guest(output/"iommu/kernel.elf",append,output/"no-snoop",args.smp,True,False)
    result["no_snoop"] = verdict(output/"no-snoop",True,args.smp,False)
    after = snapshot();save(output/"source-after.json",after)
    result.update(source_unchanged=before==after,passed=before==after and result["iommu"]["passed"] and result["no_iommu"]["passed"] and result["no_snoop"]["passed"])
    save(output/"result.json",result)
    print(json.dumps(result,indent=2));return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
