def verify_official_host_proof(raw_stdout, terminal_raw):
    """Require final original stdout and its actual durable successful job."""
    terminal = json.loads(terminal_raw)
    need(terminal.get("job_id") == OFFICIAL_HOST_JOB and terminal.get("state") == "succeeded" and
         terminal.get("exit_code") == 0 and
         all(terminal.get(key) is True for key in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(key) is False for key in ("automatic_retry", "timed_out", "cancelled")) and
         terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_synced") == {"stdout": True, "stderr": True}, "ACTUAL_OFFICIAL_HOST_DURABLE_SUCCESS_REQUIRED")
    lines = raw_stdout.splitlines()
    need(len(lines) == 2, "EXACT_ORIGINAL_OFFICIAL_HOST_STDOUT")
    stage, envelope = (json.loads(line) for line in lines)
    need(stage.get("schema") == "pocket4-official-aapt2-host-source-stage-result-v1" and
         stage.get("source_stage_ok") is True and stage.get("worker_about_to_exec_once") is True and
         stage.get("source_root") == str(Path(OFFICIAL_HOST_SOURCE["path"]).parent) and
         stage.get("files") == [{"name": "prepare_official_aapt2.py", "bytes": OFFICIAL_HOST_SOURCE["bytes"],
                                 "sha256": OFFICIAL_HOST_SOURCE["sha256"]}], "ACTUAL_OFFICIAL_SOURCE_STAGE_CHANGED")
    need(set(envelope) == {"encoding", "artifact_bytes", "artifact_sha256", "data"} and
         envelope["encoding"] == "zlib-base64" and envelope["artifact_bytes"] == 34091 and
         envelope["artifact_sha256"] == "b827c080d7af767cab60fbd9a682eafd8dfe06d6f4375b23f62988212a4b908e",
         "EXACT_OFFICIAL_FINAL_WORKER_ENVELOPE_REQUIRED")
    compressed = base64.b64decode(envelope["data"], validate=True)
    need(len(compressed) <= 131072, "OFFICIAL_HOST_COMPRESSED_BOUND")
    inflater = zlib.decompressobj()
    raw = inflater.decompress(compressed, 131073)
    need(inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail and
         len(raw) == envelope["artifact_bytes"] and sha(raw) == envelope["artifact_sha256"],
         "OFFICIAL_FINAL_WORKER_BYTES_CHANGED")
    proof = json.loads(raw)
    need(proof.get("schema") == "pocket4-official-aapt2-extraction-elf-version-v1" and proof.get("ok") is True and
         proof.get("errors") == [] and proof.get("status") == "OFFICIAL_HOST_TOOL_EXTRACTED_BOUND_AND_VERSION_OBSERVED" and
         proof.get("source") == OFFICIAL_HOST_SOURCE and proof.get("official_version") == "9.5.1-16666295" and
         all(proof.get(key) is True for key in ("official_jar_and_extracted_tool_unchanged", "all_bound_host_files_unchanged",
             "all_owned_tool_children_joined", "original_descriptor_identities_restored")) and
         proof.get("process_FDs_before") == proof.get("process_FDs_after") == 3, "OFFICIAL_HOST_FINAL_RETIREMENT_OR_IDENTITY_REQUIRED")
    candidate = proof.get("candidate", {})
    need(candidate.get("declared_path") == candidate.get("resolved_path") == OFFICIAL_CANDIDATE["path"] and
         all(candidate.get(key) == OFFICIAL_CANDIDATE[key] for key in ("bytes", "sha256", "file")),
         "EXACT_OFFICIAL_CANDIDATE_FILE_AND_STAT_REQUIRED")
    need(all(type(proof.get(key)) is int and proof[key] == 0 for key in
         ("APK_reads", "APK_tool_inputs", "Android_commands", "App_launches", "Main_reads", "UI_actions", "installs",
          "namespace_entries", "native_commands", "permission_changes", "new_network_requests")) and
         proof.get("action_lock_acquired") is False and proof.get("existing_files_modified") is False and
         proof.get("original_failed_audits_reclassified") is False, "OFFICIAL_HOST_ACTION_BOUNDARY_CHANGED")
    need(proof["extraction"]["source_jar_sha256"] == "fa1014cb1431622d292ef55ba870e75882ea19987bec541698b912f446a2d08f" and
         proof["extraction"]["member_crc_checked_by_complete_ZipExtFile_read"] is True and
         proof["extraction"]["other_members_extracted"] is False, "OFFICIAL_JAR_EXTRACTION_EVIDENCE_REQUIRED")
    commands = proof.get("commands")
    need(type(commands) is list and len(commands) == proof.get("candidate_executions") == 1, "EXACT_ORIGINAL_VERSION_ONCE")
    command = commands[0]
    need(command.get("argv") == [OFFICIAL_CANDIDATE["path"], "version"] and command.get("returncode") == 0 and
         all(command.get(key) is True for key in ("joined", "pipes_closed", "output_capture_complete")) and
         all(command.get(key) is False for key in ("timed_out", "own_group_kill_requested")) and
         not command.get("error") and not command.get("retirement_error"), "OFFICIAL_VERSION_CHILD_DID_NOT_SETTLE_NORMALLY")
    for stream in ("stdout", "stderr"):
        original = bytes.fromhex(command[stream + "_original_hex"])
        need(len(original) == command[stream]["bytes"] and sha(original) == command[stream]["sha256"], "OFFICIAL_VERSION_RAW_STREAM_PIN")
    need(proof.get("version_original") == "Android Asset Packaging Tool (aapt) 2.20-16666295\n", "ACTUAL_OFFICIAL_VERSION_OUTPUT")
    graph = proof.get("static_dependency_graph")
    need(type(graph) is list and len(graph) == proof.get("static_dependency_file_count") == 7 and
         len({row["file"]["resolved_path"] for row in graph}) == 7 and
         all(row["static_elf"]["additional_loader_directives"] == [] for row in graph), "EXACT_OFFICIAL_SEVEN_FILE_STATIC_GRAPH")
    layout = proof["controlled_runpath_layout"]
    need(layout["output_root"] == OFFICIAL_TOOL_ROOT and
         layout["owned_directory_descriptors"] == {"acquired": 11, "closed": 11, "errors": [],
             "evidence_store_descriptor_borrowed_not_closed_here": True} and
         [row["stage"] for row in layout["observations"]] == ["before_system_dependency_resolution", "immediately_before_version",
             "after_version_and_final_file_recheck"] and
         all(row["complete"] is True and row["all_five_search_directories_and_thirty_candidates_proved"] is True
             for row in layout["observations"]), "OFFICIAL_CONTROLLED_LAYOUT_PROOF_INCOMPLETE")
    need(all(row["directories"] == layout["observations"][0]["directories"] for row in layout["observations"]),
         "OFFICIAL_PRIVATE_DIRECTORY_PROOF_CHANGED")
    return proof


def bind_existing_official_layout(core, pool, end, result, proof):
    """Read-only adapter for the already proved exact host layout verifier."""
    raw = core.pinned_record(OFFICIAL_HOST_SOURCE, 131072)
    host = types.ModuleType("pinned_official_aapt2_host_layout_definitions")
    host.__file__ = OFFICIAL_HOST_SOURCE["path"]
    exec(compile(raw, host.__file__, "exec"), host.__dict__)
    reader = host.frozen_module(host.READER_SOURCE, host.READER_SHA, "original_readonly_layout_reader")
    record = {"host_source": OFFICIAL_HOST_SOURCE, "prior_host_job": OFFICIAL_HOST_JOB,
              "existing_directories_only": True, "new_directories_created": False,
              "root_identity_source": "fresh read-only binding; seven child directory full stats equal prior actual host proof"}
    result["official_private_layout"] = record
    layout = host.ControlledRunpathLayout(reader, record)
    try:
        need(host.OUTPUT == OFFICIAL_TOOL_ROOT, "EXACT_OFFICIAL_LAYOUT_SOURCE_ROOT")
        # The original class borrows this descriptor. Its own anchor/children
        # close through the original class; this one closes through core.pool.
        root_fd = core.open_host(pool, OFFICIAL_TOOL_ROOT, os.O_RDONLY | os.O_DIRECTORY)
        layout.store = types.SimpleNamespace(fd=root_fd, written=proof["new_evidence_files"] + [proof["inner_receipt"]])
        layout.anchor = reader.HeldPath(OFFICIAL_TOOL_ROOT)
        layout.anchor.open()
        need(layout.anchor.fd is not None and reader.metadata(layout.anchor.fd) == reader.metadata(root_fd),
             "EXISTING_OFFICIAL_ROOT_FULL_PATH_REQUIRED")
        previous_parents = proof["controlled_runpath_layout"]["ancestors_after_new_output"]
        need([row["path"] for row in layout.anchor.parents] == [row["path"] for row in previous_parents], "OFFICIAL_ANCESTOR_PATHS_CHANGED")
        for current, previous in zip(layout.anchor.parents, previous_parents):
            value = host.require_secure_directory(reader, current["fd"])
            need(all(value[key] == previous["stat"][key] for key in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")),
                 "OFFICIAL_ANCESTOR_IDENTITY_OR_OWNER_CHANGED")
        layout.root_stat = host.require_secure_directory(reader, root_fd, True)
        record["fresh_held_root_stat"] = layout.root_stat
        previous = proof["controlled_runpath_layout"]["observations"][-1]["directories"]
        need([row["path"] for row in previous] == [OFFICIAL_TOOL_ROOT + "/" + name for name in host.ControlledRunpathLayout.CONTENTS],
             "EXACT_SEVEN_PREVIOUS_DIRECTORY_PATHS")
        for row in previous:
            need(time.monotonic() < end, "OFFICIAL_DIRECTORY_REBIND_DEADLINE")
            relative = row["path"][len(OFFICIAL_TOOL_ROOT) + 1:]
            prefix, unused, leaf = relative.rpartition("/")
            parent = root_fd if not prefix else layout.directories[prefix]
            descriptor = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            layout.directories[relative] = descriptor
            need(host.require_secure_directory(reader, descriptor, True) == row["stat"], "OFFICIAL_PRIVATE_DIRECTORY_FULL_STAT_CHANGED")
            layout.directory_stats[relative] = row["stat"]
        layout.verify("fresh_readonly_rebind_before_APK_tools", end)
        return layout
    except BaseException:
        layout.close()
        raise


def add_official_tool_binding(core, pool, tools, end, proof):
    need("aapt2" in tools and "legacy-aapt2" not in tools, "LEGACY_BINDING_MUST_REMAIN")
    tools["legacy-aapt2"] = tools.pop("aapt2")
    candidate = OFFICIAL_CANDIDATE
    fd = core.open_host(pool, candidate["path"])
    value = core.hash_fd(fd, 64 * 1024 * 1024, min(end, time.monotonic() + 45))
    need(value == {key: candidate[key] for key in ("bytes", "sha256", "file")}, "OFFICIAL_TOOL_FULL_BYTES_OR_IDENTITY_CHANGED")
    tools["aapt2"] = {"pin": {"declared_path": candidate["path"], "resolved_path": candidate["path"],
                               "bytes": candidate["bytes"], "sha256": candidate["sha256"]}, "fd": fd, "observed": value}
    additional = {}
    aliases = bind_static_dependencies(core, pool, additional, end, proof)
    for name, row in additional.items():
        key = "official-" + name
        need(key not in tools, "OFFICIAL_STATIC_BINDINGS_MUST_NOT_REPLACE_LEGACY")
        tools[key] = row
    return aliases


def clean_official_badging_observations(commands):
    badging = [row for row in commands if row.get("name") == "badging"]
    return bool([row.get("package") for row in badging] == DIAGNOSTIC_PACKAGES and
                all(row.get("returncode") == 0 and row.get("output_capture_complete") is True and
                    row.get("stderr", {}).get("bytes") == 0 and row.get("stderr", {}).get("sha256") ==
                    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" for row in badging))
