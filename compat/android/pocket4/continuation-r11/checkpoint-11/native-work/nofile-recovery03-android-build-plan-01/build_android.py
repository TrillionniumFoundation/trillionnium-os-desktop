#!/usr/bin/env python3
import ctypes,datetime,hashlib,json,os,re,signal,stat,subprocess,sys,time,shlex
from pathlib import Path

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def identity(st):
    return [st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns]

def held(path, maximum=4*1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'unexpected file type/size: '+str(path))
        parts = []
        total = 0
        while total <= maximum:
            chunk = os.read(fd, min(65536, maximum+1-total))
            if not chunk:
                break
            parts.append(chunk)
            total += len(chunk)
        data = b''.join(parts)
        require(total == before.st_size and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()), 'source changed during read: '+str(path))
        return data, {'path': str(path), 'bytes': total, 'sha256': sha(data), 'identity': identity(before)}
    finally:
        os.close(fd)

def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(data, bytes):
        data = (json.dumps(data, indent=2, sort_keys=True)+'\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}

def real_directory(path):
    for item in (path, *path.parents):
        require(stat.S_ISDIR(item.lstat().st_mode), 'directory alias rejected: '+str(item))

def children():
    return [int(x) for x in Path('/proc/self/task/%d/children' % os.getpid()).read_text().split()]

def cleanup_children():
    initial = children()
    errors = []
    reaped = []
    deadline = time.monotonic()+8
    while children() and time.monotonic() < deadline:
        for pid in children():
            try:
                got, status = os.waitpid(pid, os.WNOHANG)
                if got:
                    reaped.append({'pid': got, 'status': status})
                    continue
                fd = os.pidfd_open(pid, 0)
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                finally:
                    os.close(fd)
            except ChildProcessError:
                continue
            except ProcessLookupError:
                continue
            except Exception as error:
                errors.append(repr(error))
        time.sleep(0.02)
    remaining = children()
    return {'initial_owned_children': initial, 'forced_cleanup': bool(initial), 'reaped': reaped, 'remaining': remaining, 'errors': errors}

def command(argv, cwd, env, label, records, maximum_seconds=180):
    require(not children(), 'unreaped child before command')
    maximum_seconds = min(maximum_seconds, DEADLINE-time.monotonic())
    require(maximum_seconds > 0, 'owned overall deadline exhausted')
    stdout = OUT/(label+'.stdout')
    stderr = OUT/(label+'.stderr')
    started = utc()
    with stdout.open('xb') as out, stderr.open('xb') as err:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=err, start_new_session=True)
        timeout = False
        try:
            code = proc.wait(timeout=maximum_seconds)
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                code = proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                code = proc.wait(timeout=3)
    output, outrow = held(stdout, 32*1024*1024)
    _, errrow = held(stderr, 4*1024*1024)
    row = {'argv': [str(x) for x in argv], 'cwd': str(cwd), 'label': label,
           'started_utc': started, 'finished_utc': utc(), 'returncode': code,
           'timed_out': timeout, 'stdout': outrow, 'stderr': errrow}
    records.append(row)
    require(code == 0 and not timeout, 'command failed: '+label)
    require(not children(), 'command left owned children: '+label)
    return output

def resource_text(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        raw = os.read(fd, 32769)
        require(len(raw) <= 32768, 'owned resource observation exceeds bound')
        return raw.decode('ascii').strip()
    finally:
        os.close(fd)

def resource_events(text):
    rows = [line.split() for line in text.splitlines()]
    require(rows and all(len(row) == 2 and row[1].isdigit() for row in rows), 'malformed owned memory.events')
    events = {row[0]:int(row[1]) for row in rows}
    require(len(events) == len(rows) and all(k in events for k in ['oom','oom_kill','oom_group_kill']), 'incomplete or duplicate owned memory.events')
    return events

def resource_snapshot(directory_fd, membership):
    observed = Path('/proc/self/cgroup').read_text().strip()
    require(observed == membership, 'controller cgroup membership changed')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    held_st = os.fstat(directory_fd)
    named_st = path.lstat()
    require(stat.S_ISDIR(held_st.st_mode) and stat.S_ISDIR(named_st.st_mode) and
            (held_st.st_dev,held_st.st_ino) == (named_st.st_dev,named_st.st_ino), 'owned invocation cgroup identity changed')
    fields = {name:resource_text(directory_fd,name) for name in [
        'cgroup.procs','memory.events','memory.current','memory.peak','memory.high','memory.max',
        'memory.swap.current','memory.swap.peak','memory.swap.max','cpu.max']}
    require(str(os.getpid()) in fields['cgroup.procs'].split(), 'controller is not in the held invocation')
    require(fields['memory.max'] == '1073741824' and fields['cpu.max'] == '100000 100000', 'owned resource limits do not match the request')
    for key in ['memory.current','memory.peak','memory.swap.current','memory.swap.peak']:
        require(fields[key].isdigit(), 'invalid owned resource counter: '+key)
    return {'observed_utc':utc(), 'membership':membership, 'path':str(path),
            'directory_identity':[held_st.st_dev,held_st.st_ino],
            'controller_pid':os.getpid(), 'fields':fields, 'events':resource_events(fields['memory.events'])}

def begin_resources():
    membership = Path('/proc/self/cgroup').read_text().strip()
    require('\n' not in membership and membership.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'), 'not the exact owned user invocation')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    require(path.name.startswith('hepta-runtime-job-') and path.name.endswith('.service') and '..' not in path.parts, 'unexpected owned unit path')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = resource_snapshot(fd,membership)
        require(all(before['events'][k] == 0 for k in ['oom','oom_kill','oom_group_kill']), 'owned invocation already recorded OOM before the control')
        return fd,before
    except BaseException:
        os.close(fd)
        raise

def finish_resources(directory_fd, before, report):
    after = resource_snapshot(directory_fd,before['membership'])
    report['owned_resources_after'] = after
    report['owned_memory_peak'] = int(after['fields']['memory.peak'])
    report['owned_memory_swap_peak'] = int(after['fields']['memory.swap.peak'])
    require(after['directory_identity'] == before['directory_identity'], 'owned cgroup object replaced')
    require(set(before['events']) == set(after['events']), 'owned memory event fields changed')
    delta = {key:after['events'][key]-value for key,value in before['events'].items()}
    report['owned_memory_events_delta'] = delta
    require(all(value >= 0 for value in delta.values()), 'owned memory event counters went backwards')
    require(all(delta[key] == 0 for key in ['oom','oom_kill','oom_group_kill']), 'owned OOM event occurred; control is not qualified')
    require(all(before['fields'][key] == after['fields'][key] for key in ['memory.max','memory.high','memory.swap.max','cpu.max']), 'owned cgroup limits changed during control')
    return {'pass':True, 'before':before, 'after':after, 'memory_events_delta':delta,
            'memory_peak':int(after['fields']['memory.peak']), 'memory_swap_peak':int(after['fields']['memory.swap.peak']),
            'resource_settings_changed':False, 'swap_max_observed_only':after['fields']['memory.swap.max']}

def hash_held(path, maximum=512*1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'unexpected held file type/size: '+str(path))
        digest = hashlib.sha256()
        total = 0
        while True:
            raw = os.read(fd,65536)
            if not raw:
                break
            total += len(raw)
            require(total <= maximum, 'held file grew beyond bound: '+str(path))
            digest.update(raw)
        require(total == before.st_size and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
                'held file changed: '+str(path))
        return {'path':str(path),'bytes':total,'sha256':digest.hexdigest(),'identity':identity(before)}
    finally:
        os.close(fd)

def regular_tree(root, file_bound=2048, byte_bound=32*1024*1024):
    real_directory(root)
    rows = {}
    total = 0
    def walk_error(error):
        raise error
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=walk_error):
        dirs.sort()
        for name in dirs:
            path=Path(directory)/name
            require(stat.S_ISDIR(path.lstat().st_mode),'source directory alias rejected: '+str(path))
        for name in sorted(files):
            path=Path(directory)/name
            relative=str(path.relative_to(root))
            require(relative not in rows and len(rows)<file_bound,'source inventory bound or duplicate')
            row=hash_held(path)
            total+=row['bytes']
            require(total<=byte_bound,'source inventory byte bound exceeded')
            rows[relative]=row
    require(rows,'empty source inventory: '+str(root))
    return rows

def verify_resolved(rows):
    changes=[]
    for row in rows:
        try:
            path=Path(row['requested_path'])
            resolved=path.resolve(strict=True)
            after=hash_held(resolved)
            if str(resolved)!=row['resolved_path'] or after!={k:row[k] for k in ['path','bytes','sha256','identity']}:
                changes.append(str(path))
        except Exception as error:
            changes.append({'path':row['requested_path'],'error':repr(error)})
    return changes

import zipfile

ROOT = Path("/home/alex/work/pocket4-nofile-owner-recovery03-android-build-01-20261105")
HERE = ROOT / "control-source"
OUT = ROOT / "coordinator01"
R3_SHA = "6f07583856f660eba100589f43114ff6b423659256363a9cf3883a334d6b4c81"
HOST_RESULT = Path("/home/alex/work/pocket4-nofile-owner-recovery03-host-run-01-20261105/run01/result.json")
HOST_RESULT_SHA = "b0a03b1b95e3292131105dcb22fd59f4a767e63017197e29f4482036976a4ac2"
SOURCE_PINS_SHA = "21a644c1fd29fcaa0ff4368a4c39926168db8adff5880290f86af9fe18baf98b"

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
