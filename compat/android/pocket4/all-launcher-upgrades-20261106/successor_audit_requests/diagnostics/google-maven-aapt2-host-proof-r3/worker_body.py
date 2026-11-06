def require_secure_directory(reader, descriptor, private=False):
    value = reader.metadata(descriptor)
    required(stat.S_ISDIR(value["st_mode"]) and value["st_uid"] == 0 and
             not stat.S_IMODE(value["st_mode"]) & 0o022 and
             (not private or stat.S_IMODE(value["st_mode"]) == 0o700),
             "ROOT_OWNED_NONWRITABLE_ANCESTOR_OR_PRIVATE_DIRECTORY_REQUIRED")
    return value


def observe_missing_sonames(descriptor, names):
    observed = []
    for name in names:
        required(type(name) is str and re.fullmatch(r"[A-Za-z0-9_+.-]{1,160}", name) and
                 name not in (".", ".."), "EXACT_ABSENCE_SONAME_FORM")
        try:
            found = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
        except FileNotFoundError as error:
            required(error.errno == errno.ENOENT, "ONLY_ACTUAL_ENOENT_IS_LIBRARY_ABSENCE")
            observed.append({"soname": name, "outcome": "ENOENT"})
        else:
            os.close(found)
            raise RuntimeError("LIBRARY_CANDIDATE_EXISTS_IN_PRIVATE_RUNPATH")
    return observed


def exact_controlled_search_paths(candidate, data):
    tool_path = OUTPUT + "/toolchain/platform/bin/aapt2"
    required(candidate.declared == candidate.resolved == tool_path and
             all(candidate.observed[key] == EXACT_EXTRACTED_TOOL[key] for key in ("bytes", "sha256")),
             "ONLY_EXACT_OFFICIAL_BINARY_USES_CONTROLLED_LAYOUT")
    required(data.get("rpath") is None and data.get("runpath") == EXACT_TOOL_RUNPATH and
             data.get("needed") == EXACT_TOOL_NEEDED and
             data.get("interpreter") == "/lib64/ld-linux-x86-64.so.2" and
             data.get("additional_loader_directives") == [], "EXACT_OBSERVED_OFFICIAL_LOADER_INPUTS_REQUIRED")
    origin = str(Path(tool_path).parent)
    expanded = [os.path.normpath(part.replace("$ORIGIN", origin)) for part in EXACT_TOOL_RUNPATH.split(":")]
    expected = [OUTPUT + "/" + relative for relative in CONTROLLED_SEARCH_RELATIVE_PATHS]
    required(expanded == expected and len(set(expanded)) == 5 and
             all(path.startswith(OUTPUT + "/") for path in expanded), "EXACT_FIVE_PRIVATE_RUNPATH_DIRECTORIES")
    return expanded


class ControlledRunpathLayout:
    """Hold this job's new directories; do not extend the system resolver."""
    CONTENTS = {
        "toolchain": {"platform", "lib64"},
        "toolchain/platform": {"bin", "lib64"},
        "toolchain/platform/bin": {"aapt2", "lib64"},
        "toolchain/platform/bin/lib64": set(),
        "toolchain/platform/lib64": set(),
        "toolchain/lib64": set(),
        "lib64": set(),
    }

    def __init__(self, reader, record):
        self.reader, self.record = reader, record
        self.store, self.anchor = None, None
        self.directories, self.directory_stats, self.parent_before = {}, {}, []
        self.root_stat = None

    def verify_parent_before_creation(self):
        required(str(Path(OUTPUT).parent) == "/var/lib", "FIXED_ROOT_CONTROLLED_OUTPUT_PARENT")
        parent = self.reader.HeldPath("/var/lib")
        try:
            parent.open()
            required(parent.fd is not None and parent.missing is None, "EXISTING_ROOT_CONTROLLED_OUTPUT_PARENT")
            rows = parent.parents + [{"path": "/var/lib", "fd": parent.fd}]
            required([row["path"] for row in rows] == ["/", "/var", "/var/lib"], "EXACT_OUTPUT_ANCESTORS")
            self.parent_before = [{"path": row["path"], "stat": require_secure_directory(self.reader, row["fd"])} for row in rows]
            parent.verify_parent_paths()
            self.record["ancestors_before_new_output"] = self.parent_before
        finally:
            parent.close()

    def create(self, store, end):
        self.store = store
        self.anchor = self.reader.HeldPath(OUTPUT)
        self.anchor.open()
        required(self.anchor.fd is not None and self.anchor.missing is None and
                 self.reader.metadata(self.anchor.fd) == self.reader.metadata(store.fd), "NEW_OUTPUT_FULL_PATH_BINDING")
        require_secure_directory(self.reader, store.fd, True)
        required([row["path"] for row in self.anchor.parents] == ["/", "/var", "/var/lib"], "EXACT_NEW_OUTPUT_ANCESTORS")
        after_creation = []
        # Creation may change the parent's link count and timestamps. Its
        # dev/inode/owner/mode must be identical; subsequent original reader
        # checks include the now-observed parent link counts as usual.
        for previous, current in zip(self.parent_before, self.anchor.parents):
            value = require_secure_directory(self.reader, current["fd"])
            required(previous["path"] == current["path"] and
                     all(previous["stat"][key] == value[key] for key in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")),
                     "OUTPUT_ANCESTOR_IDENTITY_CHANGED_DURING_CREATION")
            after_creation.append({"path": current["path"], "stat": value})
        self.record["ancestors_after_new_output"] = after_creation
        required(os.listdir(store.fd) == [], "NEW_OUTPUT_MUST_START_EMPTY")
        for relative in self.CONTENTS:
            required(time.monotonic() < end, "CONTROLLED_LAYOUT_CREATION_DEADLINE")
            prefix, unused, leaf = relative.rpartition("/")
            parent = store.fd if not prefix else self.directories[prefix]
            os.mkdir(leaf, 0o700, dir_fd=parent)
            descriptor = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            self.directories[relative] = descriptor
            require_secure_directory(self.reader, descriptor, True)
            os.fsync(parent)
        self.record["created_directories"] = [OUTPUT + "/" + relative for relative in self.directories]

    def freeze_after_extraction(self):
        self.root_stat = require_secure_directory(self.reader, self.store.fd, True)
        self.directory_stats = {relative: require_secure_directory(self.reader, descriptor, True)
                                for relative, descriptor in self.directories.items()}
        self.record["searched_directory_full_stat_frozen_after_extraction"] = True
        self.record["output_root_metadata_policy"] = "dev/inode/owner/mode/link-count fixed; size/timestamps may change only with recorded evidence files"

    def verify(self, stage, end):
        row = {"stage": stage, "complete": False, "directories": []}
        self.record.setdefault("observations", []).append(row)
        required(self.root_stat is not None and time.monotonic() < end, "FROZEN_CONTROLLED_LAYOUT_REQUIRED")
        required(all(self.reader.metadata(self.store.fd)[key] == self.root_stat[key] for key in self.reader.PARENT_ID) and
                 all(self.reader.metadata(self.anchor.fd)[key] == self.root_stat[key] for key in self.reader.PARENT_ID),
                 "HELD_OUTPUT_ROOT_IDENTITY_CHANGED")
        self.anchor.verify_parent_paths()
        for parent in self.anchor.parents:
            require_secure_directory(self.reader, parent["fd"])
        root_again = os.open(Path(OUTPUT).name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=self.anchor.parents[-1]["fd"])
        try:
            required(all(self.reader.metadata(root_again)[key] == self.root_stat[key] for key in self.reader.PARENT_ID),
                     "OUTPUT_ROOT_FULL_PATH_CHANGED")
        finally:
            os.close(root_again)
        allowed_root_entries = {"toolchain", "lib64"} | {Path(pin["path"]).name for pin in self.store.written}
        required(set(os.listdir(self.store.fd)) == allowed_root_entries, "UNRECORDED_ENTRY_IN_CONTROLLED_OUTPUT_ROOT")
        for relative, expected_entries in self.CONTENTS.items():
            required(time.monotonic() < end, "CONTROLLED_LAYOUT_RECHECK_DEADLINE")
            descriptor = self.directories[relative]
            observed = require_secure_directory(self.reader, descriptor, True)
            required(observed == self.directory_stats[relative], "CONTROLLED_DIRECTORY_FULL_STAT_CHANGED")
            prefix, unused, leaf = relative.rpartition("/")
            parent = self.store.fd if not prefix else self.directories[prefix]
            fresh = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            try:
                required(self.reader.metadata(fresh) == observed, "CONTROLLED_DIRECTORY_PATH_REPLACED")
            finally:
                os.close(fresh)
            entries = sorted(os.listdir(descriptor))
            observation = {"path": OUTPUT + "/" + relative, "stat": observed, "entries": entries, "missing_needed": []}
            row["directories"].append(observation)
            required(set(entries) == expected_entries, "UNEXPECTED_PRIVATE_RUNPATH_ENTRY")
            if relative in CONTROLLED_SEARCH_RELATIVE_PATHS:
                observation["missing_needed"] = observe_missing_sonames(descriptor, EXACT_TOOL_NEEDED)
            required(self.reader.metadata(descriptor) == observed, "CONTROLLED_DIRECTORY_CHANGED_DURING_ABSENCE_CHECK")
        row["complete"] = True
        row["all_five_search_directories_and_thirty_candidates_proved"] = True
        return row

    def close(self):
        acquired = len(self.directories) + (len(self.anchor.fds) if self.anchor is not None else 0)
        closed, errors = 0, []
        for relative, descriptor in reversed(list(self.directories.items())):
            try:
                os.close(descriptor)
                closed += 1
            except OSError as error:
                errors.append({"directory": relative, "errno": error.errno})
        self.directories.clear()
        if self.anchor is not None:
            count = len(self.anchor.fds)
            try:
                self.anchor.close()
                closed += count
            except BaseException as error:
                errors.append({"anchor": OUTPUT, "type": type(error).__name__})
            self.anchor = None
        self.record["owned_directory_descriptors"] = {"acquired": acquired, "closed": closed, "errors": errors,
                                                        "evidence_store_descriptor_borrowed_not_closed_here": True}
        required(not errors and closed == acquired, "CONTROLLED_LAYOUT_OWNED_DESCRIPTORS_NOT_CLOSED")


def verify_original_download(raw):
    value = json.loads(raw)
    required(value.get("schema") == "pocket4-official-aapt2-download-v1" and value.get("ok") is True and
             value.get("published_sha256_match") is True and value.get("original_descriptor_identities_restored") is True,
             "ACTUAL_OFFICIAL_DOWNLOAD_NOT_COMPLETE")
    required(all(value.get(key) == JAR[key] for key in ("path", "bytes", "sha256")) and
             value.get("expected_sha256") == JAR["sha256"] and value.get("url") == OFFICIAL_URL,
             "ACTUAL_OFFICIAL_DOWNLOAD_IDENTITY_CHANGED")
    required(value.get("jar_members") == EXPECTED_MEMBERS and value.get("jar_extracted") is False and
             value.get("tool_executed") is False and value.get("legacy_tools_or_APKs_modified") is False,
             "EXACT_ORIGINAL_JAR_OBSERVATION_REQUIRED")
    required(all(type(value.get(key)) is int and value[key] == 0 for key in
                 ("Android_commands", "App_installs", "Main_actions", "permission_changes", "namespace_entries", "subprocesses_started")),
             "ORIGINAL_DOWNLOAD_BOUNDARY_CHANGED")
    http = value.get("http", {})
    required(http.get("status") == 200 and http.get("final_url") == OFFICIAL_URL and
             http.get("redirect_followed") is False and http.get("content_length") == JAR["bytes"] and
             http.get("certificate_verification") == "default required HTTPS", "ORIGINAL_HTTPS_EVIDENCE_DIFFERS")
    terminal_raw = DOWNLOAD_TERMINAL_RAW.encode("utf-8")
    required(len(terminal_raw) == 731 and sha(terminal_raw) ==
             "e7cec94c8f5a2b012e7bfecd40cef5065c7d23516ff1a81400673eadb959c458",
             "ORIGINAL_DOWNLOAD_TERMINAL_PIN")
    terminal = json.loads(terminal_raw)
    required(terminal.get("job_id") == "1a1b220b4d3-fc05-7c7f" and terminal.get("state") == "succeeded" and
             terminal.get("exit_code") == 0, "ORIGINAL_DOWNLOAD_TERMINAL_NOT_SUCCESS")
    required(all(terminal.get(key) is True for key in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
             all(terminal.get(key) is False for key in ("automatic_retry", "timed_out", "cancelled")) and
             terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
             terminal.get("log_errors") == {"stdout": None, "stderr": None} and
             terminal.get("log_synced") == {"stdout": True, "stderr": True},
             "ORIGINAL_DOWNLOAD_AUTHORITATIVE_LOGS_INCOMPLETE")
    return {"job_id": terminal["job_id"], "terminal_sha256": sha(terminal_raw),
            "original_https_download_and_published_checksum_observed": True,
            "new_network_request_performed": False}


def extract_exact_member(jar_bytes, store, end, tool_directory):
    required(len(jar_bytes) == JAR["bytes"] and sha(jar_bytes) == JAR["sha256"], "HELD_OFFICIAL_JAR_BYTES_CHANGED")
    with zipfile.ZipFile(io.BytesIO(jar_bytes), "r") as archive:
        members = archive.infolist()
        observed = [{"name": item.filename, "bytes": item.file_size, "compressed_bytes": item.compress_size} for item in members]
        required(observed == EXPECTED_MEMBERS and len({item.filename for item in members}) == 4,
                 "EXACT_FOUR_OFFICIAL_JAR_MEMBERS_REQUIRED")
        for item in members:
            name = PurePosixPath(item.filename)
            required(not name.is_absolute() and ".." not in name.parts and not item.flag_bits & 1 and
                     stat.S_IFMT(item.external_attr >> 16) != stat.S_IFLNK and
                     item.compress_type == zipfile.ZIP_DEFLATED, "OFFICIAL_JAR_MEMBER_FORM_CHANGED")
        member = next(item for item in members if item.filename == "aapt2")
        required(not member.is_dir() and member.file_size == 6489808 and member.compress_size == 2440131 and
                 time.monotonic() < end, "EXACT_OFFICIAL_AAPT2_MEMBER_REQUIRED")
        descriptor = os.open("aapt2", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o500, dir_fd=tool_directory)
        count, checksum = 0, hashlib.sha256()
        try:
            with archive.open(member, "r") as stream:
                while True:
                    required(time.monotonic() < end, "EXTRACTION_TOTAL_DEADLINE")
                    chunk = stream.read(min(65536, member.file_size + 1 - count))
                    if not chunk:
                        break
                    count += len(chunk)
                    required(count <= member.file_size, "EXTRACTED_TOOL_SIZE_BOUND")
                    checksum.update(chunk)
                    view = memoryview(chunk)
                    while view:
                        written = os.write(descriptor, view)
                        required(written > 0, "EXTRACTED_TOOL_WRITE_PROGRESS")
                        view = view[written:]
            required(count == member.file_size, "EXTRACTED_TOOL_TRUNCATED")
            required(count == EXACT_EXTRACTED_TOOL["bytes"] and checksum.hexdigest() == EXACT_EXTRACTED_TOOL["sha256"],
                     "ORIGINAL_OFFICIAL_BINARY_BYTES_MUST_BE_UNCHANGED")
            os.fchmod(descriptor, 0o500)
            os.fsync(descriptor)
            metadata = os.fstat(descriptor)
            required(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == 0 and metadata.st_nlink == 1 and
                     metadata.st_size == count and stat.S_IMODE(metadata.st_mode) == 0o500,
                     "NEW_ROOT_OWNED_TOOL_METADATA")
        finally:
            os.close(descriptor)
        os.fsync(tool_directory)
        return {"path": OUTPUT + "/toolchain/platform/bin/aapt2", "bytes": count, "sha256": checksum.hexdigest(),
                "source_jar_sha256": JAR["sha256"], "member": "aapt2", "member_crc32": member.CRC,
                "member_crc_checked_by_complete_ZipExtFile_read": True,
                "other_members_extracted": False, "mode": "0500", "execution_performed_by_extraction": False}


def static_graph(bind, candidate, elf, end, rows, layout):
    queue, seen = [candidate], {}
    while queue:
        current = queue.pop(0)
        if current.resolved in seen:
            continue
        required(len(seen) < 48 and time.monotonic() < end, "STATIC_ELF_GRAPH_BOUND")
        data = elf.inspect_elf_fd(current.held.fd, current.observed["bytes"])
        row = {"file": current.pin(), "static_elf": data, "resolved_needed": []}
        rows.append(row)
        required(data["additional_loader_directives"] == [], "ADDITIONAL_LOADER_DIRECTIVES_OUTSIDE_BOUND_SCOPE")
        seen[current.resolved] = data
        if current is candidate:
            row["controlled_private_runpath"] = exact_controlled_search_paths(candidate, data)
            layout.verify("before_system_dependency_resolution", end)
            # All thirty private name candidates were proven absent in this
            # job's root-owned tree. The unchanged system-only resolver still
            # resolves every dependency; no private library is admitted.
            dirs = list(SEARCH_DIRS)
        else:
            origin = str(Path(current.resolved).parent)
            dirs = search_paths(data.get("rpath"), origin) + search_paths(data.get("runpath"), origin) + list(SEARCH_DIRS)
        for name in data["needed"]:
            declared = resolve_dependency(name, dirs)
            resolved = str(Path(declared).resolve(strict=True))
            row["resolved_needed"].append({"soname": name, "declared_path": declared, "resolved_path": resolved})
            if resolved not in seen and not any(item.resolved == resolved for item in queue):
                queue.append(bind(declared, resolve=True))
        interpreter = data.get("interpreter")
        if interpreter is not None:
            required(interpreter.startswith("/"), "ABSOLUTE_ELF_INTERPRETER_REQUIRED")
            resolved = str(Path(interpreter).resolve(strict=True))
            required(in_system_library_root(resolved), "ELF_INTERPRETER_OUTSIDE_SYSTEM_LIBRARY_ROOTS")
            row["resolved_interpreter"] = {"declared_path": interpreter, "resolved_path": resolved}
            if resolved not in seen and not any(item.resolved == resolved for item in queue):
                queue.append(bind(interpreter, resolve=True))
    return rows


def main():
    required(os.getuid() == os.geteuid() == 0, "EXISTING_AUTHORIZED_HOST_ROOT_REQUIRED")
    required(len(sys.argv) == 6 and sys.argv[1] == "--prepare-and-version-once" and sys.argv[2] == "--source-sha256" and
             re.fullmatch(r"[0-9a-f]{64}", sys.argv[3]) and sys.argv[4] == "--source-bytes" and sys.argv[5].isdigit(),
             "EXACT_PINNED_HOST_SOURCE_OPERATION")
    required(str(Path(__file__).resolve()) == SOURCE_ROOT + "/prepare_official_aapt2.py", "EXACT_HOST_SOURCE_PATH")
    self_pin = {"path": SOURCE_ROOT + "/prepare_official_aapt2.py", "bytes": int(sys.argv[5]), "sha256": sys.argv[3]}
    os.umask(0o077)
    before = census()
    end = time.monotonic() + 210
    files, store, layout = [], None, None
    result = {"schema": "pocket4-official-aapt2-extraction-elf-version-v1", "ok": False, "errors": [],
              "source": self_pin, "official_version": "9.5.1-16666295", "official_jar": JAR,
              "new_network_requests": 0, "Main_reads": 0, "Android_commands": 0, "native_commands": 0,
              "namespace_entries": 0, "APK_reads": 0, "APK_tool_inputs": 0, "App_launches": 0,
              "installs": 0, "UI_actions": 0, "permission_changes": 0, "action_lock_acquired": False,
              "existing_files_modified": False, "original_failed_audits_reclassified": False,
              "automatic_retry": False, "production_ready": False, "candidate_executions": 0, "commands": [],
              "process_FDs_before": len(before), "static_graph_is_actual_loader_mapping_proof": False,
              "version_proves_Calendar_resource_compatibility": False}
    try:
        reader = frozen_module(READER_SOURCE, READER_SHA, "original_nofollow_host_reader")
        elf = frozen_module(ELF_SOURCE, ELF_SHA, "original_borrowed_fd_static_elf_parser")
        result["controlled_runpath_layout"] = {"output_root": OUTPUT, "new_private_directories_mode": "0700",
                                               "arbitrary_non_system_search_paths_permitted": False,
                                               "binary_or_loader_environment_modified": False}
        layout = ControlledRunpathLayout(reader, result["controlled_runpath_layout"])
        layout.verify_parent_before_creation()
        store = EvidenceStore(reader)
        layout.create(store, end)

        def bind(path, limit=MAX_FILE, expected=None, resolve=False):
            required(time.monotonic() < end and len(files) < 64, "HOST_PROOF_TIME_OR_FILE_BOUND")
            item = BoundFile(reader, path, limit, expected, resolve)
            files.append(item)
            required(sum(row.observed["bytes"] for row in files) <= MAX_TOTAL, "HOST_PROOF_TOTAL_BYTES_BOUND")
            return item

        source = bind(self_pin["path"], 262144, self_pin)
        receipt = bind(DOWNLOAD["path"], 4096, DOWNLOAD)
        result["original_download"] = verify_original_download(receipt.content(4096))
        jar = bind(JAR["path"], 16 * 1024 * 1024, JAR)
        result["original_download_receipt"] = receipt.pin()
        result["held_original_jar"] = jar.pin()
        derived = extract_exact_member(jar.content(16 * 1024 * 1024), store, end, layout.directories["toolchain/platform/bin"])
        result["extraction"] = derived
        candidate = bind(derived["path"], 8 * 1024 * 1024, {key: derived[key] for key in ("path", "bytes", "sha256")})
        required(stat.S_IMODE(candidate.observed["stat"]["st_mode"]) == 0o500, "EXACT_NEW_TOOL_EXECUTABLE_MODE")
        result["candidate"] = candidate.pin()
        layout.freeze_after_extraction()
        result["static_dependency_graph"] = []
        static_graph(bind, candidate, elf, end, result["static_dependency_graph"], layout)
        result["static_dependency_file_count"] = len(result["static_dependency_graph"])
        runner_source = bind(COLLECTOR["path"], 65536, COLLECTOR)
        runner = frozen_module(runner_source.content(65536).decode("utf-8"), COLLECTOR["sha256"], "original_bounded_owned_host_tool_runner")
        result["bounded_runner_source"] = runner_source.pin()
        for item in files:
            required(time.monotonic() < end, "TOTAL_DEADLINE_BEFORE_PRE_EXEC_RECHECK")
            item.recheck()
        layout.verify("immediately_before_version", end)
        command = {"name": "version", "APK_input": False}
        result["commands"].append(command)
        required(time.monotonic() + 5 < end, "TOTAL_DEADLINE_BEFORE_VERSION_SPAWN")
        outputs = runner.run_tool([candidate.declared, "version"], (candidate.held.fd,), command, end)
        result["candidate_executions"] += int(command.get("spawned") is True)
        for stream, raw in outputs.items():
            command[stream] = store.write("version." + stream, raw)
            if len(raw) <= 32768:
                command[stream + "_original_hex"] = raw.hex()
        required(command.get("joined") is True and command.get("pipes_closed") is True, "OWNED_VERSION_CHILD_NOT_RETIRED")
        required(command.get("returncode") == 0 and command.get("output_capture_complete") is True and
                 command.get("timed_out") is False and not command.get("error") and not command.get("retirement_error"),
                 "OFFICIAL_TOOL_VERSION_COMMAND_FAILED")
        version = outputs["stdout"] + outputs["stderr"]
        required(0 < len(version) <= 4096 and version.decode("utf-8", "strict").strip().startswith("Android Asset Packaging Tool (aapt) "),
                 "UNRECOGNISED_ACTUAL_TOOL_VERSION_OUTPUT")
        result["version_original"] = version.decode("utf-8", "strict")
        for item in files:
            required(time.monotonic() < end, "TOTAL_DEADLINE_BEFORE_FINAL_FILE_RECHECK")
            item.recheck()
        layout.verify("after_version_and_final_file_recheck", end)
        result.update(ok=True, official_jar_and_extracted_tool_unchanged=True, all_bound_host_files_unchanged=True)
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:256]})
    finally:
        result["static_dependency_file_count"] = len(result.get("static_dependency_graph", []))
        for item in reversed(files):
            try:
                item.close()
            except BaseException as error:
                result["errors"].append({"stage": "held_host_file_close", "type": type(error).__name__})
        if layout is not None:
            try:
                layout.close()
            except BaseException as error:
                result["errors"].append({"stage": "controlled_layout_close", "type": type(error).__name__, "reason": str(error)[:160]})
        result["all_owned_tool_children_joined"] = all(command.get("joined") is True and command.get("pipes_closed") is True
                                                       for command in result["commands"])
        if result["errors"]:
            result["ok"] = False
        try:
            if store is not None:
                result["new_evidence_files"] = list(store.written)
                result["success_requires_final_stdout_and_authoritative_terminal"] = True
                raw = canonical(result) + b"\n"
                required(len(raw) <= MAX_RESULT, "RESULT_BOUND")
                result["inner_receipt"] = store.write("result.json", raw)
        except BaseException as error:
            result["errors"].append({"stage": "receipt_write", "type": type(error).__name__, "reason": str(error)[:160]})
            result["ok"] = False
        finally:
            if store is not None:
                try:
                    store.close()
                except BaseException as error:
                    result["errors"].append({"stage": "evidence_directory_close", "type": type(error).__name__})
                    result["ok"] = False
        after = census()
        result["process_FDs_after"] = len(after)
        result["original_descriptor_identities_restored"] = after == before
        if after != before:
            result["errors"].append({"reason": "HOST_PROCESS_DESCRIPTOR_IDENTITY_CHANGED"})
            result["ok"] = False
    result["status"] = "OFFICIAL_HOST_TOOL_EXTRACTED_BOUND_AND_VERSION_OBSERVED" if result["ok"] else "HOST_TOOL_PREPARATION_INCOMPLETE_NO_RETRY"
    raw = canonical(result)
    required(len(raw) <= MAX_RESULT, "STDOUT_ARTIFACT_BOUND")
    print(json.dumps({"encoding": "zlib-base64", "artifact_bytes": len(raw), "artifact_sha256": sha(raw),
                      "data": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}, separators=(",", ":")), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
