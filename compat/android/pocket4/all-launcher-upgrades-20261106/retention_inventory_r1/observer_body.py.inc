def safe_error(error):
    result = {"type": type(error).__name__}
    if isinstance(error, OSError):
        result["errno"] = error.errno
    elif isinstance(error, RuntimeError) and re.fullmatch(r"[A-Z0-9_]{1,96}", str(error)):
        result["code"] = str(error)
    else:
        result["code"] = "UNEXPECTED_DETAILS_NOT_EXPORTED"
    return result


def path_parts(path):
    need(type(path) is str and path.startswith("/") and len(path.encode()) <= 4096 and
         "\0" not in path and all(p not in ("", ".", "..") for p in path[1:].split("/")), "CLOSED_CANONICAL_PATH")
    return path[1:].split("/")


def file_metadata(fd):
    value = os.fstat(fd)
    result = {key: getattr(value, key) for key in STAT}
    result["st_blocks"] = value.st_blocks
    result["allocated_bytes"] = value.st_blocks * 512
    return result


def open_relative(pool, root, path, flags=os.O_PATH):
    """No symlink is followed in an ordinary path, including its final entry."""
    parts = path_parts(path)
    parents = []
    try:
        parent = root
        for part in parts[:-1]:
            parent = pool.own(os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent))
            parents.append(parent)
        return pool.own(os.open(parts[-1], flags | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent))
    finally:
        for fd in reversed(parents):
            pool.close(fd)


def bounded_proc_read(pool, proc, name, limit, end):
    need(re.fullmatch(r"(?:mountinfo|maps|fdinfo/[0-9]+)", name) is not None, "CLOSED_PROC_METADATA_NAME")
    fd = pool.own(os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=proc))
    try:
        raw = bytearray()
        while len(raw) <= limit:
            need(time.monotonic() < end, "PROC_METADATA_DEADLINE")
            block = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not block:
                return bytes(raw)
            raw.extend(block)
        raise RuntimeError("PROC_METADATA_SIZE_BOUND")
    finally:
        pool.close(fd)


def mount_id(pool, self_proc, fd, end):
    raw = bounded_proc_read(pool, self_proc, "fdinfo/" + str(fd), 4096, end)
    rows = [line for line in raw.decode("ascii", "strict").splitlines() if line.startswith("mnt_id:")]
    need(len(rows) == 1 and re.fullmatch(r"mnt_id:\s+[0-9]+", rows[0]), "EXACT_FD_MOUNT_ID")
    return int(rows[0].split()[1])


def mount_records(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 2097152, "MOUNTINFO_BOUND")
    rows = []
    for line in raw.decode("utf-8", "strict").splitlines():
        fields = line.split(" ")
        need(fields.count("-") == 1, "MOUNTINFO_SEPARATOR")
        split = fields.index("-")
        need(split >= 6 and len(fields) >= split + 4 and fields[0].isdigit() and fields[1].isdigit() and
             re.fullmatch(r"[0-9]+:[0-9]+", fields[2]), "MOUNTINFO_FIELDS")
        # Preserve the kernel's octal escapes. Never reinterpret a path as a
        # shell argument or automatically open an overlay/loop backing path.
        rows.append({"mount_id": int(fields[0]), "parent_id": int(fields[1]), "major_minor": fields[2],
                     "root_literal": fields[3], "mountpoint_literal": fields[4], "options_literal": fields[5],
                     "optional_fields": fields[6:split], "filesystem": fields[split+1],
                     "source_literal": fields[split+2], "super_options_literal": fields[split+3:]})
    need(len(rows) <= 8192 and len({r["mount_id"] for r in rows}) == len(rows), "MOUNTINFO_COUNT_OR_DUPLICATE")
    return rows


class PrivateOutput:
    """Own new evidence files only. No target or existing artifact is written."""
    def __init__(self, core, pool, root, directory, maximum=33554432):
        self.core, self.pool, self.root, self.directory = core, pool, root, directory
        self.identity = file_metadata(directory)
        self.maximum, self.total = maximum, 0
        self.stream_fd, self.stream_bytes = None, 0
        self.stream_digest = hashlib.sha256()
        self.outputs = []

    def verify(self):
        current = self.core.open_host(self.pool, self.root, os.O_PATH | os.O_DIRECTORY)
        try:
            now = file_metadata(current)
            need(all(now[k] == self.identity[k] for k in ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")), "PRIVATE_OUTPUT_ROOT_REPLACED")
        finally:
            self.pool.close(current)

    def new_fd(self, name):
        need(re.fullmatch(r"[A-Za-z0-9_.-]+", name), "NEW_PRIVATE_OUTPUT_NAME")
        self.verify()
        return self.pool.own(os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                     0o400, dir_fd=self.directory))

    def write_all(self, fd, raw):
        need(type(raw) is bytes and self.total + len(raw) <= self.maximum, "PRIVATE_METADATA_AGGREGATE_BOUND")
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            need(count > 0, "NEW_PRIVATE_WRITE_PROGRESS")
            view = view[count:]
        self.total += len(raw)

    def readback(self, name, size, digest):
        self.verify()
        fd = self.pool.own(os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.directory))
        try:
            before = file_metadata(fd)
            need(stat.S_ISREG(before["st_mode"]) and before["st_uid"] == 0 and before["st_nlink"] == 1 and
                 stat.S_IMODE(before["st_mode"]) == 0o400 and before["st_size"] == size, "NEW_PRIVATE_METADATA_SHAPE")
            got, count = hashlib.sha256(), 0
            while count <= size:
                block = os.read(fd, min(131072, size + 1 - count))
                if not block:
                    break
                got.update(block); count += len(block)
            need(count == size and got.hexdigest() == digest and file_metadata(fd) == before, "NEW_PRIVATE_METADATA_READBACK")
            check = self.pool.own(os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.directory))
            try:
                need(file_metadata(check) == before, "NEW_PRIVATE_METADATA_PATH_REPLACED")
            finally:
                self.pool.close(check)
            pin = {"path": self.root + "/" + name, "bytes": size, "sha256": digest, "file": before}
            self.outputs.append(pin)
            return pin
        finally:
            self.pool.close(fd)

    def write(self, name, raw):
        fd = self.new_fd(name)
        try:
            self.write_all(fd, raw)
            os.fsync(fd)
        finally:
            self.pool.close(fd)
        os.fsync(self.directory)
        return self.readback(name, len(raw), sha(raw))

    def start_entries(self):
        need(self.stream_fd is None, "ENTRY_STREAM_ALREADY_OPEN")
        self.stream_fd = self.new_fd("entries.private.jsonl")

    def entry(self, value):
        need(self.stream_fd is not None, "ENTRY_STREAM_NOT_OPEN")
        raw = canonical(value) + b"\n"
        if value.get("tree_root"):
            # Reserve room for final fixed-reference observations and closure.
            # A partial tree is an explicit gap, not a reason to lose the
            # original whole-process and runtime postconditions.
            need(self.total + len(raw) + 4194304 <= self.maximum, "TREE_ARTIFACT_BUDGET")
        self.write_all(self.stream_fd, raw)
        self.stream_digest.update(raw); self.stream_bytes += len(raw)

    def finish_entries(self):
        if self.stream_fd is None:
            return None
        fd, self.stream_fd = self.stream_fd, None
        try:
            os.fsync(fd)
        finally:
            self.pool.close(fd)
        os.fsync(self.directory)
        return self.readback("entries.private.jsonl", self.stream_bytes, self.stream_digest.hexdigest())


class AllocationIndex:
    def __init__(self):
        self.rows = {}
        self.observations = 0

    def add(self, row):
        info = row["stat"]
        key = (info["st_dev"], info["st_ino"])
        self.observations += 1
        value = self.rows.setdefault(key, {"device": key[0], "inode": key[1], "observed_aliases": set(),
            "allocated_samples": set(), "logical_samples": set(), "nlink_samples": set(), "kinds": set(),
            "known_reference_ids": set(), "mount_ids": set()})
        value["observed_aliases"].add((row["coordinate"], row["path"]))
        value["allocated_samples"].add(info["allocated_bytes"])
        value["logical_samples"].add(info["st_size"])
        value["nlink_samples"].add(info["st_nlink"])
        value["kinds"].add(stat.S_IFMT(info["st_mode"]))
        value["mount_ids"].add(row["mount_id"])
        if row.get("reference_id"):
            value["known_reference_ids"].add(row["reference_id"])

    def summary(self):
        stable = [v for v in self.rows.values() if all(len(v[k]) == 1 for k in ("allocated_samples", "logical_samples", "nlink_samples", "kinds"))]
        return {"metadata_observations": self.observations, "distinct_device_inode_pairs": len(self.rows),
            "stable_metadata_pairs": len(stable), "pairs_with_multiple_observed_aliases": sum(len(v["observed_aliases"]) > 1 for v in self.rows.values()),
            "stable_allocated_bytes_unique_device_inode": sum(next(iter(v["allocated_samples"])) for v in stable),
            "stable_regular_file_logical_bytes_unique_device_inode": sum(next(iter(v["logical_samples"])) for v in stable if next(iter(v["kinds"])) == stat.S_IFREG),
            "same_device_inode_may_be_hardlink_or_bind_alias": True, "external_aliases_proved_absent": False,
            "reflink_compression_snapshot_extent_accounting_proved": False, "reclaimable_bytes": None}

    def public_use_matches(self, device, inode):
        row = self.rows.get((device, inode))
        return sorted(row["known_reference_ids"]) if row is not None else []


def observe_exact(pool, roots, self_proc, reference, end, index, output, phase):
    fd = None
    row = {"reference_id": reference["id"], "coordinate": reference["coordinate"], "path": reference["path"], "phase": phase}
    try:
        fd = open_relative(pool, roots[row["coordinate"]], row["path"])
        info = file_metadata(fd)
        row.update(status="OBSERVED_METADATA", stat=info, mount_id=mount_id(pool, self_proc, fd, end))
        if stat.S_ISLNK(info["st_mode"]):
            row["symlink_not_followed"] = True
        need(file_metadata(fd) == info, "EXACT_METADATA_CHANGED_WHILE_HELD")
        check = open_relative(pool, roots[row["coordinate"]], row["path"])
        try:
            need(file_metadata(check) == info, "EXACT_METADATA_PATH_CHANGED")
        finally:
            pool.close(check)
        index.add(row)
    except OSError as error:
        row.update(status="ABSENT" if error.errno == errno.ENOENT else "UNRESOLVED_METADATA", error=safe_error(error))
    except RuntimeError as error:
        row.update(status="UNSTABLE_METADATA", error=safe_error(error))
    finally:
        if fd is not None:
            pool.close(fd)
    output.entry(row)
    return row


def walk_tree(pool, host_root, self_proc, scope, end, global_budget, index, output):
    """A finite metadata walk, never following a symlink or a child mount."""
    result = {"path": scope["path"], "status": "INCOMPLETE", "entries": 0, "directories_opened": 0,
              "directory_iterators_opened": 0, "directory_iterators_closed": 0, "gaps": [], "reclaimable_bytes": None}
    root_fd = None
    try:
        root_fd = open_relative(pool, host_root, scope["path"], os.O_RDONLY | os.O_DIRECTORY)
        first = file_metadata(root_fd)
        root_mount = mount_id(pool, self_proc, root_fd, end)
        need(first["st_uid"] in (0, 1000), "UNREVIEWED_TREE_OWNER")
        result.update(root_before=first, root_mount_id=root_mount)

        def visit(directory, path, depth):
            need(time.monotonic() < end, "TREE_WALK_TIME_BOUND")
            before = file_metadata(directory)
            result["directories_opened"] += 1
            result["directory_iterators_opened"] += 1
            try:
                with os.scandir(directory) as iterator:
                    for entry in iterator:
                        need(time.monotonic() < end, "TREE_WALK_TIME_BOUND")
                        need(result["entries"] < scope["maximum_entries"] and global_budget[0] < 100000,
                             "TREE_WALK_ENTRY_BOUND")
                        name = entry.name
                        need(name not in ("", ".", "..") and "/" not in name and "\0" not in name and
                             len(name.encode("utf-8", "surrogateescape")) <= 255, "TREE_ENTRY_NAME_BOUND")
                        child = None
                        result["entries"] += 1; global_budget[0] += 1
                        row = {"coordinate": "host", "path": path + "/" + name, "tree_root": scope["path"]}
                        try:
                            child = pool.own(os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory))
                            info = file_metadata(child)
                            child_mount = mount_id(pool, self_proc, child, end)
                            row.update(status="OBSERVED_METADATA", stat=info, mount_id=child_mount)
                            need(file_metadata(child) == info, "TREE_ENTRY_CHANGED_WHILE_HELD")
                            index.add(row)
                            if stat.S_ISLNK(info["st_mode"]):
                                row["symlink_not_followed"] = True
                            output.entry(row)
                            if stat.S_ISDIR(info["st_mode"]):
                                if child_mount != root_mount:
                                    result["gaps"].append({"path_sha256": sha(row["path"].encode("utf-8", "surrogateescape")), "code": "CHILD_MOUNT_NOT_TRAVERSED"})
                                elif depth >= scope["maximum_depth"]:
                                    raise RuntimeError("TREE_WALK_DEPTH_BOUND")
                                else:
                                    read_dir = pool.own(os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory))
                                    try:
                                        need(file_metadata(read_dir) == info and mount_id(pool, self_proc, read_dir, end) == child_mount,
                                             "TREE_DIRECTORY_REPLACED_BEFORE_ENTRY")
                                        visit(read_dir, row["path"], depth + 1)
                                    finally:
                                        pool.close(read_dir)
                        except OSError as error:
                            row.update(status="UNRESOLVED_METADATA", error=safe_error(error))
                            output.entry(row)
                            result["gaps"].append({"path_sha256": sha(row["path"].encode("utf-8", "surrogateescape")), "error": safe_error(error)})
                        finally:
                            if child is not None:
                                pool.close(child)
            finally:
                result["directory_iterators_closed"] += 1
            need(file_metadata(directory) == before, "DIRECTORY_MUTATED_DURING_METADATA_WALK")

        visit(root_fd, scope["path"], 0)
        result["root_after"] = file_metadata(root_fd)
        need(result["root_after"] == first, "TREE_ROOT_CHANGED_DURING_METADATA_WALK")
        check = open_relative(pool, host_root, scope["path"], os.O_PATH | os.O_DIRECTORY)
        try:
            need(file_metadata(check) == first and mount_id(pool, self_proc, check, end) == root_mount,
                 "TREE_ROOT_PATH_CHANGED")
        finally:
            pool.close(check)
        result["status"] = "COMPLETE_METADATA_WALK" if not result["gaps"] else "INCOMPLETE_WITH_EXPLICIT_GAPS"
    except (OSError, RuntimeError) as error:
        result["gaps"].append(safe_error(error))
    finally:
        if root_fd is not None:
            pool.close(root_fd)
    need(result["directory_iterators_opened"] == result["directory_iterators_closed"], "TREE_ITERATOR_NOT_CLOSED")
    return result


def process_fd_metadata(pool, proc, self_proc, role, end, index, output):
    directory = pool.own(os.open("fd", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=proc))
    rows, matches, gaps = [], [], []
    try:
        with os.scandir(directory) as iterator:
            for entry in iterator:
                need(time.monotonic() < end and len(rows) < 4096, "HELD_ROLE_FD_METADATA_BOUND")
                need(entry.name.isdigit(), "HELD_ROLE_FD_NUMBER")
                row = {"fd_number": int(entry.name)}
                target = None
                try:
                    # This is the held role's kernel FD reference, not a path
                    # obtained from a command or from arbitrary file content.
                    # O_PATH observes metadata without reading the target.
                    target = pool.own(os.open(entry.name, os.O_PATH | os.O_CLOEXEC, dir_fd=directory))
                    info = file_metadata(target)
                    row.update(stat=info, mount_id=mount_id(pool, self_proc, target, end), status="HELD_FD_METADATA")
                    need(file_metadata(target) == info, "HELD_FD_TARGET_METADATA_CHANGED")
                    hit = index.public_use_matches(info["st_dev"], info["st_ino"])
                    if hit:
                        matches.append({"role": role, "fd_number": int(entry.name), "reference_ids": hit,
                                        "device": info["st_dev"], "inode": info["st_ino"]})
                except OSError as error:
                    row.update(status="UNRESOLVED_CLOSED_OR_DENIED_FD", error=safe_error(error))
                    gaps.append(safe_error(error))
                finally:
                    if target is not None:
                        pool.close(target)
                rows.append(row)
        pin = output.write("role-" + role + "-fd-metadata.private.json", canonical(rows) + b"\n")
        return {"role": role, "observed_FDs": len(rows), "private_metadata": pin, "known_reference_matches": matches,
                "gaps": gaps, "all_processes_reference_absence_proved": False}
    finally:
        pool.close(directory)


def config_path_literals(value, pointer="", rows=None):
    if rows is None:
        rows = []
    need(len(rows) <= 256, "CONFIG_LITERAL_COUNT_BOUND")
    if type(value) is dict:
        for key, child in value.items():
            config_path_literals(child, pointer + "/" + key.replace("~", "~0").replace("/", "~1"), rows)
    elif type(value) is list:
        for i, child in enumerate(value):
            config_path_literals(child, pointer + "/" + str(i), rows)
    elif type(value) is str and value.startswith("/") and "\0" not in value and len(value.encode()) <= 4096:
        rows.append({"pointer": pointer, "literal": value, "automatically_opened": False, "path_coordinate": "UNRESOLVED_CONFIG_LITERAL"})
    return rows


def run(request):
    need(type(request) is dict and set(request) == {"schema", "guard", "scope", "worker", "output_root"} and
         request["schema"] == "pocket4-bounded-retention-observation-request-v1" and request["guard"] == GUARD and
         request["scope"] == SCOPE_PIN and request["output_root"] == OUTPUT and
         request["worker"]["path"] == STAGE + "/observe_retention.py" and str(Path(__file__).resolve()) == request["worker"]["path"],
         "EXACT_RETENTION_SOURCE_REQUEST")
    read_root_pin(request["worker"])
    need(os.getuid() == os.geteuid() == 0, "EXISTING_HOST_ROOT_REQUIRED")
    scope = parse(read_root_pin(SCOPE_PIN))
    need(type(scope) is dict and set(scope) == {"schema", "references", "trees", "protected_scope_reference",
         "protected_packages", "origin_pins", "additional_reference_evidence", "complete_current_scope_claimed"} and
         scope["schema"] == "pocket4-retention-metadata-scope-v1" and len(scope["references"]) == REFERENCE_COUNT and
         len(scope["trees"]) == 16 and scope["protected_scope_reference"] == PROTECTED_SCOPE and
         scope["protected_packages"] == PROTECTED_PACKAGES and scope["complete_current_scope_claimed"] is False,
         "CLOSED_METADATA_SCOPE_REQUIRED")
    guard = load_source(GUARD, "retention_current_typed_guard")
    core = guard._core()
    pool, leases = core.FDs(), core.FDs()
    held = output = directory = action_lock = None
    result = {"schema": "pocket4-bounded-retention-observation-v1", "ok": False, "errors": [],
              "automatic_retry": False, "production_ready": False, "cleanup_eligible": 0, "reclaimable_bytes": None,
              "deletions": 0, "moves": 0, "existing_permission_changes": 0, "existing_process_signals": 0,
              "UI_actions": 0, "App_launches": 0, "installs": 0, "permission_changes": 0,
              "native_command_count": 0, "Android_namespace_commands": 0, "ADB_commands": 0,
              "business_data_content_reads": 0, "worker_direct_commands": 0,
              "frozen_guard_host_reads": "UNCHANGED_ORIGINAL_IMPLEMENTATION",
              "old_failed_or_unknown_receipts_reclassified": False, "complete_installed_package_set_claimed": False,
              "current_scope_reference": scope["protected_scope_reference"], "output_artifacts_are_private": True,
              "runtime_executable_and_APK_bytes_rehashed_by_this_worker": False,
              "historical_content_hashes_are_reference_only_with_fresh_metadata_binding": True,
              "additional_reference_evidence": scope["additional_reference_evidence"],
              "all_processes_reference_absence_proved": False}
    end = time.monotonic() + 180
    index, entries_closed = AllocationIndex(), False
    try:
        core.create_private_root(OUTPUT)
        directory = core.open_host(pool, OUTPUT, os.O_RDONLY | os.O_DIRECTORY)
        lock_fd = pool.own(os.open("flow.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory))
        try:
            os.fsync(lock_fd)
        finally:
            pool.close(lock_fd)
        os.fsync(directory)
        _, result["flow_lock"] = core.acquire_lock(leases, OUTPUT + "/flow.lock")
        action_lock, result["action_lock"] = core.acquire_lock(leases, core.ACTION_LOCK)
        result["guard_before"] = guard.current_guard()
        need(result["guard_before"].get("runtime_epoch_sha256") == EPOCH, "EXACT_RUNTIME_EPOCH")
        baseline = guard.current_baseline()
        expected = baseline["runtime"]["held"]["process_snapshot"]["binding"]
        held = core.HeldProcesses(pool, {key: row["host_pid"] for key, row in expected["processes"].items()})
        need(held.before["binding"] == expected, "EXACT_EIGHT_ROLES")
        core.verify_runtime(pool, held, baseline["runtime"])
        result["protected_scope_before"] = guard.check_app_scope(scope["protected_scope_reference"], scope["protected_packages"])
        host_root = pool.own(os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC))
        self_proc = pool.own(os.open("/proc/" + str(os.getpid()), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC))
        roots = {"host": host_root, "held_android_init_root": held.roots["android_init"]}
        output = PrivateOutput(core, pool, OUTPUT, directory)
        result["request"] = output.write("request.original.json", canonical(request) + b"\n")
        output.start_entries()
        reference_rows = []
        for reference in scope["references"]:
            need(time.monotonic() + 15 < end, "EXACT_REFERENCE_TOTAL_BUDGET")
            reference_rows.append(observe_exact(pool, roots, self_proc, reference, end, index, output, "before"))
        result["exact_reference_summary"] = {"count": len(reference_rows), "observed": sum(r["status"] == "OBSERVED_METADATA" for r in reference_rows),
            "absent": sum(r["status"] == "ABSENT" for r in reference_rows), "unresolved": sum(r["status"] not in ("ABSENT", "OBSERVED_METADATA") for r in reference_rows)}
        mount_before = {}
        procs = {"host_observer": self_proc, **held.procs}
        result["mount_views"], result["process_views"] = [], []
        for role, proc in procs.items():
            need(time.monotonic() + 15 < end, "MOUNT_CAPTURE_TOTAL_BUDGET")
            raw = bounded_proc_read(pool, proc, "mountinfo", 2097152, end)
            records = mount_records(raw)
            mount_before[role] = sha(raw)
            result["mount_views"].append({"role": role, "mount_count": len(records),
                "raw": output.write("role-" + role + "-mountinfo.private", raw),
                "records": output.write("role-" + role + "-mounts.private.json", canonical(records) + b"\n"),
                "backing_paths_automatically_opened": False})
            if role != "host_observer":
                maps = bounded_proc_read(pool, proc, "maps", 4194304, end)
                need(b"\0" not in maps, "MAPS_NUL_REJECTED")
                row = process_fd_metadata(pool, proc, self_proc, role, end, index, output)
                row["maps"] = output.write("role-" + role + "-maps.private", maps)
                result["process_views"].append(row)
        config = baseline["runtime"]["cell_config"]
        config_raw, _ = core.host_read(config["path"], 65536, config["sha256"], config["bytes"])
        literals = config_path_literals(parse(config_raw))
        result["config_path_observation"] = {"source": {k: config[k] for k in ("path", "bytes", "sha256")},
            "literal_count": len(literals), "private_literals": output.write("cell-config-path-literals.private.json", canonical(literals) + b"\n"),
            "new_backing_paths_traversed": False, "raw_configuration_exported": False}
        tree_end, global_budget = min(time.monotonic() + 90, end - 30), [0]
        result["tree_observations"] = []
        for tree in scope["trees"]:
            if time.monotonic() >= tree_end or global_budget[0] >= 100000 or output.total + 4202496 >= output.maximum:
                result["tree_observations"].append({"path": tree["path"], "status": "NOT_VISITED_REMAINING_GLOBAL_BUDGET_EXHAUSTED", "reclaimable_bytes": None})
            else:
                result["tree_observations"].append(walk_tree(pool, host_root, self_proc, tree, tree_end, global_budget, index, output))
        result["total_tree_entries"] = global_budget[0]
        result["reference_path_changes"] = []
        for reference, before in zip(scope["references"], reference_rows):
            need(time.monotonic() + 5 < end, "REFERENCE_FINAL_CHECK_BUDGET")
            after = observe_exact(pool, roots, self_proc, reference, end, index, output, "after")
            keys = ("status", "stat", "mount_id")
            if any(before.get(k) != after.get(k) for k in keys):
                result["reference_path_changes"].append(reference["id"])
        result["mount_views_changed"] = []
        for role, proc in procs.items():
            raw = bounded_proc_read(pool, proc, "mountinfo", 2097152, end)
            if sha(raw) != mount_before[role]:
                result["mount_views_changed"].append(role)
                output.write("role-" + role + "-mountinfo-after.private", raw)
        result["entries_private"] = output.finish_entries(); entries_closed = True
        result["allocation_summary"] = index.summary()
        known_alias_rows = []
        for row in index.rows.values():
            if row["known_reference_ids"]:
                projected = {k: sorted(v) if isinstance(v, set) else v for k, v in row.items() if k != "observed_aliases"}
                aliases = sorted(row["observed_aliases"])
                projected.update(observed_aliases_prefix=aliases[:32], total_observed_aliases=len(aliases),
                                 aliases_complete_in_this_index=len(aliases) <= 32,
                                 complete_observed_rows_retained_in_entry_stream=True)
                known_alias_rows.append(projected)
        result["private_known_reference_aliases"] = output.write("known-reference-aliases.private.json", canonical(known_alias_rows) + b"\n")
        core.verify_runtime(pool, held, baseline["runtime"])
        result["protected_scope_after"] = guard.check_app_scope(scope["protected_scope_reference"], scope["protected_packages"])
        result["guard_after"] = guard.current_guard()
        need(result["guard_after"] == result["guard_before"] and result["protected_scope_after"] == result["protected_scope_before"],
             "FINAL_RUNTIME_OR_PROTECTED_SCOPE_CHANGED")
        held.verify()
        for pin in (GUARD, SCOPE_PIN, request["worker"]):
            read_root_pin(pin)
        result["scope_references_unchanged"] = True
        result["all_tree_scans_complete"] = all(r["status"] == "COMPLETE_METADATA_WALK" for r in result["tree_observations"])
        result["exact_reference_snapshot_stable"] = not result["reference_path_changes"] and result["exact_reference_summary"]["unresolved"] == 0
        result["all_mount_views_stable"] = not result["mount_views_changed"]
        result["bounded_observation_finished"] = True
        result["inventory_exhaustive_or_cleanup_qualified"] = False
        result["ok"] = True
    except BaseException as error:
        result["errors"].append(safe_error(error))
    finally:
        if output is not None:
            if not entries_closed:
                try:
                    result["partial_entries_private"] = output.finish_entries()
                except BaseException as error:
                    result["errors"].append({"phase": "partial_entry_close", **safe_error(error)})
            result["private_artifacts"] = output.outputs
            result["private_written_bytes"] = output.total
        if action_lock is not None:
            try:
                fcntl.flock(action_lock, fcntl.LOCK_UN)
                result["action_lock_released"] = True
            except BaseException as error:
                result["errors"].append({"phase": "action_unlock", **safe_error(error)})
        for name, owned in (("observation", pool), ("lease", leases)):
            try:
                owned.close_all()
            except BaseException as error:
                result["errors"].append({"phase": name + "_close", **safe_error(error)})
            result[name + "_FDs_final"] = owned.summary()
        result["owned_descriptors_final"] = result["observation_FDs_final"]
        if result["errors"]:
            result["ok"] = False
    result["status"] = "BOUNDED_DEPENDENCY_METADATA_OBSERVED_WITH_EXPLICIT_GAPS" if result["ok"] else "RETENTION_OBSERVATION_INCOMPLETE_NO_RETRY"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    before = len(os.listdir("/proc/self/fd"))
    try:
        size = os.stat(args.request, follow_symlinks=False).st_size
        request = parse(read_root_pin({"path": args.request, "bytes": size, "sha256": args.request_sha256}))
        result = run(request)
    except BaseException as error:
        result = {"schema": "pocket4-retention-entry-rejection-v1", "ok": False, "errors": [safe_error(error)],
                  "automatic_retry": False, "production_ready": False}
    after = len(os.listdir("/proc/self/fd"))
    result.update(process_FDs_before=before, process_FDs_after=after)
    if before != after:
        result["ok"] = False
        result.setdefault("errors", []).append({"code": "ORIGINAL_PROCESS_FD_GATE_FAILED"})
    raw = canonical(result)
    need(len(raw) <= 524288, "BOUNDED_PUBLIC_METADATA_SUMMARY")
    envelope = {"encoding": "zlib-base64", "artifact_bytes": len(raw), "artifact_sha256": sha(raw),
                "data": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}
    stdout = canonical(envelope)
    need(len(stdout) <= 98304, "BOUNDED_PUBLIC_OBSERVER_STDOUT")
    print(stdout.decode("ascii"), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
