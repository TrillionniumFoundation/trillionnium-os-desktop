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


def extract_exact_member(jar_bytes, store, end):
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
                             0o500, dir_fd=store.fd)
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
            os.fchmod(descriptor, 0o500)
            os.fsync(descriptor)
            metadata = os.fstat(descriptor)
            required(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == 0 and metadata.st_nlink == 1 and
                     metadata.st_size == count and stat.S_IMODE(metadata.st_mode) == 0o500,
                     "NEW_ROOT_OWNED_TOOL_METADATA")
        finally:
            os.close(descriptor)
        os.fsync(store.fd)
        return {"path": OUTPUT + "/aapt2", "bytes": count, "sha256": checksum.hexdigest(),
                "source_jar_sha256": JAR["sha256"], "member": "aapt2", "member_crc32": member.CRC,
                "member_crc_checked_by_complete_ZipExtFile_read": True,
                "other_members_extracted": False, "mode": "0500", "execution_performed_by_extraction": False}


def static_graph(bind, candidate, elf, end, rows):
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
    files, store = [], None
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
        store = EvidenceStore(reader)

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
        derived = extract_exact_member(jar.content(16 * 1024 * 1024), store, end)
        result["extraction"] = derived
        candidate = bind(derived["path"], 8 * 1024 * 1024, {key: derived[key] for key in ("path", "bytes", "sha256")})
        required(stat.S_IMODE(candidate.observed["stat"]["st_mode"]) == 0o500, "EXACT_NEW_TOOL_EXECUTABLE_MODE")
        result["candidate"] = candidate.pin()
        result["static_dependency_graph"] = []
        static_graph(bind, candidate, elf, end, result["static_dependency_graph"])
        result["static_dependency_file_count"] = len(result["static_dependency_graph"])
        runner_source = bind(COLLECTOR["path"], 65536, COLLECTOR)
        runner = frozen_module(runner_source.content(65536).decode("utf-8"), COLLECTOR["sha256"], "original_bounded_owned_host_tool_runner")
        result["bounded_runner_source"] = runner_source.pin()
        for item in files:
            required(time.monotonic() < end, "TOTAL_DEADLINE_BEFORE_PRE_EXEC_RECHECK")
            item.recheck()
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
