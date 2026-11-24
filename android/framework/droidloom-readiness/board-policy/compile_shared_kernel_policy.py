#!/usr/bin/env python3
"""Link the Pocket4 shared-kernel policy using the original Android assertions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from derive_shared_payload_cgroup_policy import derive, verify


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def add_namespace_to_board_guard(source):
    original = "(typeattributeset p4_nonboard_except_kernel_cmdline (and (p4_all_nonboard) (not (proc_cmdline))))"
    registered = "(typeattributeset p4_nonboard_except_kernel_cmdline (and (p4_all_nonboard) (not (or (proc_cmdline) (p4_kernel_ns_handle_t)))))"
    if source.count(original) != 1:
        raise ValueError("Expected the board's single Linux PID 1 command-line guard")
    return source.replace(original, registered).replace(
        "p4_nonboard_except_kernel_cmdline", "p4_nonboard_except_kernel_cmdline_and_pidns_handle"
    )


def compile_policy(compiler, inputs, output, contexts, environment):
    subprocess.run(
        [str(compiler), "-m", "-M", "true", "-G", "-c", "30", "-o", str(output),
         "-f", str(contexts), *(str(path) for path in inputs)],
        env=environment,
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secilc", type=Path, required=True)
    parser.add_argument("--sepol-library", type=Path, required=True)
    parser.add_argument("--android-cil", type=Path, action="append", required=True)
    parser.add_argument("--linux-board-cil", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    release = json.loads((here / "cp3a-kernel-handle-inputs.json").read_text())
    actual = sorted(sha256(path) for path in args.android_cil)
    expected = sorted(item["sha256"] for item in release["android_inputs"])
    if actual != expected:
        raise ValueError("The supplied Android policy inputs do not match the selected CP3A image")
    compiler = args.secilc.resolve(strict=True)
    library = args.sepol_library.resolve(strict=True)
    library_entry = args.sepol_library.absolute().parent / "libsepol.so.2"
    if (sha256(compiler) != release["secilc_sha256"] or
            sha256(library) != release["libsepol_sha256"] or
            library_entry.resolve(strict=True) != library):
        raise ValueError("The selected compiler and libsepol do not match the admitted build tools")
    environment = os.environ.copy()
    for key in ("LD_PRELOAD", "LD_AUDIT"):
        environment.pop(key, None)
    environment.update(LC_ALL="C", LD_LIBRARY_PATH=str(library_entry.parent))
    output = args.output.absolute()
    component_names = (
        "readiness-observer-android.cil", "readiness-host-challenge-interface.cil",
        "kernel-namespace-custody.cil", "cp3a-kernel-handle-access.cil",
        "early-readiness-inode-owner.cil", "linux-host-service-roles.cil",
        "linux-initial-calibration.cil", "protected-device-readiness-target.cil", "orderly-android-shutdown.cil",
        "ubuntu-real-root-interpreter.cil", "ubuntu-mounted-api-metadata.cil",
        "ubuntu-core-cgroup-ownership.cil", "ubuntu-native-services.cil",
        "frontend-android-interface.cil", "linux-frontend-observer.cil", "instance-launcher.cil",
        "linux-query-owner.cil", "linux-fixed-metadata-observer.cil",
        "instance-factory-cgroup.cil", "ubuntu-systemd-unit-status.cil",
        "linux-application-roles.cil", "linux-install-catalog.cil",
        "ubuntu-dbus.cil", "ubuntu-native-selinux-query.cil",
        "ubuntu-native-pam.cil",
    )
    components = [here / name for name in component_names]
    sources = [compiler, library, args.linux_board_cil, *args.android_cil, *components,
               here / "cp3a-kernel-handle-inputs.json", Path(__file__),
               here / "derive_shared_payload_cgroup_policy.py"]
    if any(output.resolve() == path.resolve() for path in sources):
        raise ValueError("The output path is a policy input or build tool")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix="pocket4-sepolicy-") as private:
        work = Path(private)
        original = work / "original.policy"
        contexts = work / "contexts"
        compile_policy(compiler, args.android_cil, original, contexts, environment)
        if sha256(original) != release["original_binary_sha256"]:
            raise ValueError("The linked original Android policy differs from its release digest")
        shared = work / "shared-payload.cil"
        contract = derive(library, original, args.android_cil, shared)
        board = work / "linux-board.cil"
        board.write_text(add_namespace_to_board_guard(args.linux_board_cil.read_text()))
        linked = work / "combined.policy"
        compile_policy(compiler, [*args.android_cil, board, *components, shared], linked, contexts, environment)
        shared_access = verify(library, linked, contract)
        result = {
            "android_original": sha256(original),
            "secilc": sha256(compiler),
            "libsepol": sha256(library),
            "linux_board_source": sha256(args.linux_board_cil),
            "original_input_count": len(actual),
            "components": {part.name: sha256(part) for part in components},
            "output": sha256(linked),
            "shared_payload_android_access": shared_access,
            "shared_payload_deriver": sha256(here / "derive_shared_payload_cgroup_policy.py"),
        }
        os.replace(linked, output)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
