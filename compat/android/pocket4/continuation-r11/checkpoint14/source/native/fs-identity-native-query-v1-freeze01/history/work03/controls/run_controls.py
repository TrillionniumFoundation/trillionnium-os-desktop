#!/usr/bin/env python3
"""Local, bounded controls; neither an AOSP build nor an Android qualification."""
import argparse
import datetime
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
ALLOW = 0x7fff0000
TRAP = 0x00030000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": sha(data)}


def source_pins():
    result = {}
    for prefix in ("preimage", "candidate", "fixtures", "controls"):
        for path in sorted((HERE / prefix).rglob("*")):
            if path.is_symlink():
                raise RuntimeError("source symlink rejected: " + str(path))
            if path.is_file():
                result[str(path.relative_to(HERE))] = pin(path)
    return result


def evaluate(program, arch, nr, arg):
    # Independent, small classic-BPF interpreter for the actual captured bytecode.
    # Any unknown instruction, invalid offset, loop or missing RET rejects.
    nr = nr if nr < 0x80000000 else nr - 0x100000000
    data = struct.pack("<iI7Q", nr, arch, 0, arg, 0, 0, 0, 0, 0)
    index = accumulator = 0
    for _ in range(len(program) + 1):
        if index >= len(program):
            raise RuntimeError("BPF fell off end")
        code, yes, no, value = program[index]
        if code == 0x20:  # BPF_LD | BPF_W | BPF_ABS
            if value % 4 or value > len(data) - 4:
                raise RuntimeError("invalid BPF data load")
            accumulator = struct.unpack_from("<I", data, value)[0]
            index += 1
        elif code == 0x15:  # BPF_JMP | BPF_JEQ | BPF_K
            index += 1 + (yes if accumulator == value else no)
        elif code == 0x35:  # BPF_JMP | BPF_JGE | BPF_K
            index += 1 + (yes if accumulator >= value else no)
        elif code == 0x06:  # BPF_RET | BPF_K
            return value
        else:
            raise RuntimeError("unsupported instruction " + str(code))
    raise RuntimeError("BPF did not terminate")


def program_bytes(program):
    return struct.pack("<I", len(program)) + b"".join(struct.pack("<HBBI", *row) for row in program)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-once", action="store_true")
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()
    if not args.execute_once:
        print(json.dumps({"state": "PLAN", "scope": "local explicit-policy-fixture controls",
                          "source_changes": False, "Android": False, "Hepta": False,
                          "installed_filter_changes_in_parent": False}))
        return 0
    if args.out is None:
        raise RuntimeError("fresh output required")
    out = args.out.resolve()
    if out.parent != HERE or out.exists():
        raise RuntimeError("output must be a fresh direct child of this source root")
    compiler = pathlib.Path(shutil.which("g++") or "").resolve(strict=True)
    before = source_pins()
    compiler_before = pin(compiler)
    out.mkdir(mode=0o700)
    report = {"schema": "fs-identity-query-local-controls-v1", "pass": False,
              "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "scope": "complete current-source TU with explicit generated-table/header/logging and Clang-offset compatibility fixtures",
              "local_constructor_optimization": "O0; local GCC is not the AOSP Clang toolchain",
              "AOSP_generated_policy_qualified": False, "Android_qualified": False,
              "all_architectures_compiled": False, "role_or_factory_qualified": False,
              "process_actions": "only dedicated local test executables and ten exact owned children",
              "commands": [], "sources_before": before,
              "compiler": {"path": str(compiler), **compiler_before}, "error": None}

    def run(name, argv, timeout=30):
        result = subprocess.run(argv, cwd=HERE, capture_output=True, timeout=timeout, check=False)
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        report["commands"].append({"name": name, "argv": argv, "returncode": result.returncode,
                                   "timeout": False,
                                   "stdout": {"path": name + ".stdout", **pin(out / (name + ".stdout"))},
                                   "stderr": {"path": name + ".stderr", **pin(out / (name + ".stderr"))}})
        if result.returncode != 0:
            raise RuntimeError(name + " failed: " + str(result.returncode))
        return result.stdout

    try:
        run("compiler-version", [str(compiler), "--version"])
        shared = [str(compiler), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O0"]
        constructor = HERE / "controls/constructor.cc"
        programs = {}
        for name, candidate in (("preimage", 0), ("candidate", 1)):
            source = HERE / name / "bionic/libc/seccomp/seccomp_policy.cpp"
            executable = out / (name + "-constructor")
            run(name + "-compile", shared + ["-I" + str(HERE / "fixtures"),
                "-DSOURCE_FILE=" + json.dumps(str(source)), "-DCANDIDATE=" + str(candidate),
                str(constructor), "-o", str(executable)])
            programs[name] = json.loads(run(name + "-construct", [str(executable)]))
        original, candidate = programs["preimage"], programs["candidate"]
        existing = ("app", "app_zygote", "system")
        if set(original) != set(existing) or set(candidate) != set(existing) | {"app_zygote_fs_queries_v1"}:
            raise RuntimeError("unexpected constructor set")
        equality = {name: original[name] == candidate[name] for name in existing}
        if not all(equality.values()):
            raise RuntimeError("an existing stock entry point changed bytecode")
        old = original["app_zygote"]
        new = candidate["app_zygote_fs_queries_v1"]
        args = [0, 1, 1000, 61171, 0xffff, 0x7fffffff, 0xfffffffe, 0xffffffff,
                0xffffffffffffffff, 0x1ffffffff, 0x80000000ffffffff,
                0xffffffff00000000, 0x100000000]
        numbers = list(range(-2, 4097)) + [0x40000000 | value for value in (117, 119, 122, 123, 215, 216)] + [0x7fffffff]
        architectures = [(0xc000003e, (122, 123)), (0x40000003, (215, 216)),
                         (0xc00000b7, ()), (0, ())]
        comparisons = changed = 0
        for arch, setters in architectures:
            for number in numbers:
                for argument in args:
                    baseline = evaluate(old, arch, number, argument)
                    actual = evaluate(new, arch, number, argument)
                    query = number in setters and argument & 0xffffffff == 0xffffffff
                    expected = ALLOW if query else baseline
                    if actual != expected or (not setters and actual != TRAP):
                        raise RuntimeError("unexpected policy decision: " + repr((arch, number, argument, baseline, actual)))
                    if number in setters and not query and actual != TRAP:
                        raise RuntimeError("mutation was admitted")
                    comparisons += 1
                    changed += actual != baseline
        (out / "preimage-app-zygote.bpf").write_bytes(program_bytes(old))
        (out / "candidate-app-zygote.bpf").write_bytes(program_bytes(new))
        report["constructed_programs"] = programs
        report["interpreter"] = {"pass": True, "existing_entrypoints_byte_identical": equality,
                                 "comparisons": comparisons, "changed_query_decisions": changed,
                                 "x86_64_and_i386": True, "unknown_architectures_rejected": True,
                                 "x32_number_decisions_preserved": True,
                                 "upper_register_bits_covered": True,
                                 "generated_table_fixture": True}
        executable = out / "kernel-control"
        run("kernel-control-compile", shared + [str(HERE / "controls/kernel_control.cc"), "-o", str(executable)])
        kernel = json.loads(run("kernel-control", [str(executable), str(out / "preimage-app-zygote.bpf"),
                               str(out / "candidate-app-zygote.bpf")], timeout=40))
        if kernel.get("pass") is not True or len(kernel.get("cases", [])) != 10:
            raise RuntimeError("kernel controls incomplete")
        report["kernel"] = kernel
        report["pass"] = True
    except Exception as error:
        report["error"] = repr(error)
    finally:
        report["sources_after"] = source_pins()
        report["source_changes"] = [key for key in sorted(set(before) | set(report["sources_after"]))
                                    if before.get(key) != report["sources_after"].get(key)]
        report["compiler_after"] = pin(compiler)
        if report["source_changes"] or compiler_before != report["compiler_after"]:
            report["pass"] = False
            report["error"] = report["error"] or "source/compiler changed"
        report["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
        (out / "result.json").write_bytes(raw)
        print(json.dumps({"pass": report["pass"], "result": str(out / "result.json"),
                          "bytes": len(raw), "sha256": sha(raw), "error": report["error"]}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
