import zipfile

ROOT = Path("/home/alex/work/pocket4-nofile-owner-recovery03-android-build-01-20261105")
HERE = ROOT / "control-source"
OUT = ROOT / "coordinator01"
R3_SHA = "6f07583856f660eba100589f43114ff6b423659256363a9cf3883a334d6b4c81"
HOST_RESULT = Path("/home/alex/work/pocket4-nofile-owner-recovery03-host-run-01-20261105/run01/result.json")
HOST_RESULT_SHA = "b0a03b1b95e3292131105dcb22fd59f4a767e63017197e29f4482036976a4ac2"
SOURCE_PINS_SHA = "PENDING_FIXED_ARM_PINS_SHA"

def input_rows(source, expected):
    real_directory(source)
    actual = set()
    for directory, dirs, files in os.walk(source, followlinks=False):
        dirs.sort()
        for name in list(dirs):
            child = Path(directory) / name
            require(stat.S_ISDIR(child.lstat().st_mode), "source directory alias: " + str(child))
            if child == source / "build-attempt-1":
                dirs.remove(name)
        for name in files:
            actual.add(str((Path(directory) / name).relative_to(source)))
    require(actual == set(expected), "source member set changed: " + str(source))
    rows = {}
    for name, wanted in expected.items():
        row = hash_held(source / name)
        require({key: row[key] for key in ("bytes", "sha256")} == wanted,
                "source bytes changed: " + name)
        rows[name] = row
    return rows

def package_binding(source, report):
    require(report["state"] == "BUILT_STATIC_VERIFIED_ANDROID_UNRUN" and
            report["kind"] == "owner" and report["actual_android_executed"] is False and
            report["package"] == "local.pocket4.fdownerprobe.r11" and report["ABI"] == "x86_64" and
            report["builder_sha256"] == R3_SHA and report["no_permissions"] is True and
            report["no_activity"] is True and all(row["returncode"] == 0 for row in report["commands"]),
            "actual APK build/static gate is incomplete")
    build = source / "build-attempt-1"
    elf = build / "lib/x86_64/libfdownerprobe.so"
    apk = build / "fdownerprobe.apk"
    elf_pin = hash_held(elf, 32 * 1024 * 1024)
    apk_pin = hash_held(apk, 32 * 1024 * 1024)
    require(report["APK"]["path"] == str(apk) and report["APK"]["sha256"] == apk_pin["sha256"] and
            report["APK"]["bytes"] == apk_pin["bytes"] and
            report["ELF"]["sha256"] == elf_pin["sha256"] and report["ELF"]["needed"] == ["libc.so"] and
            report["ELF"]["NX_RELRO_NOW_no_WX"] is True, "actual package/ELF identity differs")
    fd = os.open(apk, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        require(identity(os.fstat(fd)) == apk_pin["identity"], "APK changed before held archive read")
        with os.fdopen(os.dup(fd), "rb") as stream, zipfile.ZipFile(stream) as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)) and
                    [name for name in names if name.startswith("lib/")] ==
                    ["lib/x86_64/libfdownerprobe.so"], "unexpected embedded native member set")
            info = archive.getinfo("lib/x86_64/libfdownerprobe.so")
            require(info.file_size == elf_pin["bytes"] and info.file_size <= 32 * 1024 * 1024,
                    "embedded ELF size differs")
            require(sha(archive.read(info)) == elf_pin["sha256"], "embedded ELF differs from audited file")
        require(identity(os.fstat(fd)) == apk_pin["identity"] == identity(apk.lstat()),
                "APK changed during held archive read")
    finally:
        os.close(fd)
    return {"APK": apk_pin, "ELF": elf_pin, "APK_embedded_ELF_exact": True}

def entry_excerpt(path):
    text = path.read_text()
    wanted = ("::Start()", "::ReadInheritedAfterAllocationFailure(",
              "::Read(int,", "berberis_proc_metadata_raw_clone_x86_64>")
    lines = []
    take = False
    count = 0
    for line in text.splitlines(True):
        if re.match(r"^\s*[0-9a-f]+ <.+>:\s*$", line):
            take = any(name in line for name in wanted)
            count += int(take)
        if take:
            lines.append(line)
    raw = "".join(lines).encode()
    require(count >= 3 and 0 < len(raw) <= 131072, "actual entry excerpt is incomplete or exceeds bound")
    return raw

def execute():
    global DEADLINE
    require(os.getuid() == 1000 and os.geteuid() == 1000, "ordinary operator UID1000 required")
    require(Path(__file__).absolute() == HERE / "build_android.py", "fixed staged controller required")
    real_directory(HERE)
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    DEADLINE = time.monotonic() + 550
    allowed = sorted(os.sched_getaffinity(0))
    require(len(allowed) >= 3, "cannot leave two logical CPUs free")
    os.sched_setaffinity(0, [allowed[-1]])
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(36, 1, 0, 0, 0) == 0 and not children(), "owned subreaper admission failed")
    report = {"schema": 1, "state": "RUNNING", "started_utc": utc(), "commands": [], "arms": {},
              "scope": "two fixed owned Android APK builds and actual final ELF audits only",
              "Main_actions": 0, "Main_identity_observed": False, "Android_install_or_execution": False,
              "factory_service_started": False, "production_ready": False,
              "owned_host_control_sha256": HOST_RESULT_SHA, "original_26_case_assertions_unchanged": True}
    def interrupted(number, frame):
        raise RuntimeError("owned Android build interrupted by signal " + str(number))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    resource_fd = -1
    before = None
    authorities = {}
    sources = {}
    tools = {}
    packages = {}
    expected = {}
    try:
        resource_fd, before = begin_resources()
        report["owned_resources_before"] = before
        raw, pin = held(HERE / "arm-source-pins.json", 65536)
        require(sha(raw) == SOURCE_PINS_SHA, "fixed arm source inventory changed")
        expected = json.loads(raw)
        require(set(expected) == {"preimage", "candidate"} and all(len(v) == 22 for v in expected.values()),
                "fixed two-arm source member count differs")
        authorities[str(HERE / "arm-source-pins.json")] = pin
        raw, pin = held(HOST_RESULT, 65536)
        require(sha(raw) == HOST_RESULT_SHA, "actual host control receipt changed")
        host = json.loads(raw)
        require(host["state"] == "PASS" and len(host["arms"]) == 2 and
                all(row["matched_expected"] is True and row["case_count"] == 26 for row in host["arms"]) and
                host["source_unchanged_after"] is True and host["held_ELF_unchanged_after"] is True and
                host["owned_resource_gate"]["pass"] is True and not host["cleanup"]["forced_cleanup"] and
                not host["cleanup"]["remaining"] and not host["cleanup"]["errors"],
                "actual host 26-case prerequisite is incomplete")
        authorities[str(HOST_RESULT)] = pin
        builder = HERE / "build-r3.py"
        raw, pin = held(builder, 32768)
        require(sha(raw) == R3_SHA, "pinned existing Android builder changed")
        authorities[str(builder)] = pin
        env = {"PATH": "/usr/bin:/bin", "HOME": "/home/alex", "LANG": "C", "LC_ALL": "C"}
        for arm in ("preimage", "candidate"):
            source = ROOT / arm
            require(not (source / "build-attempt-1").exists(), "fresh build attempt required")
            sources[arm] = input_rows(source, expected[arm])
            command(["/usr/bin/python3", "-I", "-B", str(builder), str(source), "owner", "1"],
                    source, env, arm + "-APK-build", report["commands"], 220)
            raw, build_pin = held(source / "build-attempt-1/build-result.json", 131072)
            built = json.loads(raw)
            binding = package_binding(source, built)
            require(built["source_sha256"] == {name: row["sha256"] for name, row in sources[arm].items()},
                    "actual compiler source set differs from frozen input")
            native = next(row for row in built["commands"] if row["name"] == "compile-native")
            disassembly = next(row for row in built["commands"] if row["name"] == "disassembly")
            objdump = Path(disassembly["argv"][0])
            require(objdump.is_absolute() and objdump.name == "llvm-objdump" and
                    objdump.parent == Path(native["argv"][0]).parent, "unexpected actual disassembly tool")
            resolved = objdump.resolve(strict=True)
            tool = hash_held(resolved)
            if str(objdump) in built["tools_sha256"]:
                require(tool["sha256"] == built["tools_sha256"][str(objdump)],
                        "actual audited objdump differs from pinned builder tools")
                tool["binding"] = "existing builder tool pin"
            else:
                tool["binding"] = "actual compiler sibling observed independently before/after audit"
            tool.update(requested_path=str(objdump), resolved_path=str(resolved))
            tools[arm] = tool
            audit_script = source / ("audit_two_workers.py" if arm == "candidate" else "audit_worker_binary.py")
            audit_path = OUT / (arm + "-worker-audit.json")
            command(["/usr/bin/python3", "-I", "-B", str(audit_script), binding["ELF"]["path"],
                     "--objdump", str(objdump), "--output", str(audit_path)],
                    source, env, arm + "-worker-audit", report["commands"], 20)
            raw, audit_pin = held(audit_path, 32768)
            audit = json.loads(raw)
            require(audit["qualified_worker_closure"] is True and not audit["errors"] and
                    audit["elf_sha256"] == binding["ELF"]["sha256"], "actual Android worker closure failed")
            disassembly_path = audit_path.with_suffix(".disassembly.txt")
            full_pin = hash_held(disassembly_path, 8 * 1024 * 1024)
            excerpt_pin = write_new(OUT / (arm + "-entry-disassembly.txt"), entry_excerpt(disassembly_path))
            binding.update(build_receipt=build_pin, worker_audit=audit_pin,
                           disassembly=full_pin, entry_disassembly=excerpt_pin)
            report["arms"][arm] = binding
            packages[arm] = binding
            require(input_rows(source, expected[arm]) == sources[arm], "source changed during Android build")
        report["state"] = "PASS"
    except Exception as error:
        report["state"] = "FAIL"
        report["error"] = {"type": type(error).__name__, "message": str(error),
                           "errno": getattr(error, "errno", None), "filename": getattr(error, "filename", None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        report["cleanup"] = cleanup_children()
        try:
            report["source_unchanged_after"] = len(sources) == 2 and all(
                input_rows(ROOT / arm, expected[arm]) == rows for arm, rows in sources.items())
            report["authority_unchanged_after"] = bool(authorities) and all(
                hash_held(Path(path)) == row for path, row in authorities.items())
            report["tool_changes"] = []
            for arm, row in tools.items():
                path = Path(row["requested_path"])
                require(str(path.resolve(strict=True)) == row["resolved_path"], "actual objdump target changed")
                after = hash_held(Path(row["resolved_path"]))
                if after != {key: row[key] for key in ("path", "bytes", "sha256", "identity")}:
                    report["tool_changes"].append(arm)
            report["APK_ELF_unchanged_after"] = len(packages) == 2 and all(
                hash_held(Path(binding[key]["path"]), 32 * 1024 * 1024) == binding[key]
                for binding in packages.values() for key in ("APK", "ELF"))
            require(report["source_unchanged_after"] and report["authority_unchanged_after"] and
                    not report["tool_changes"] and report["APK_ELF_unchanged_after"],
                    "actual Android source/tool/package closure changed or incomplete")
        except Exception as error:
            report["after_error"] = str(error)
            report["state"] = "FAIL"
        try:
            require(resource_fd >= 0 and before is not None, "missing owned resource admission")
            report["owned_resource_gate"] = finish_resources(resource_fd, before, report)
        except Exception as error:
            report["resource_error"] = str(error)
            report["state"] = "FAIL"
        finally:
            if resource_fd >= 0:
                os.close(resource_fd)
        if report["cleanup"]["forced_cleanup"] or report["cleanup"]["remaining"] or report["cleanup"]["errors"]:
            report["state"] = "FAIL"
    report["finished_utc"] = utc()
    report["source_inputs"] = sources
    report["actual_audit_tools"] = tools
    result = write_new(OUT / "result.json", report)
    print(json.dumps({"state": report["state"], "result": result,
                      "Android_install_or_execution": False}), flush=True)
    return 0 if report["state"] == "PASS" else 1

if __name__ == "__main__":
    if sys.argv[1:] != ["--execute-once"]:
        print(json.dumps({"mode": "PLAN", "root": str(ROOT), "arms": ["preimage", "candidate"],
                          "NDK_builder_sha256": R3_SHA, "Android_install_or_execution": False,
                          "requires_actual_final_ELF_audits": True, "Main_actions": 0}))
    else:
        raise SystemExit(execute())
