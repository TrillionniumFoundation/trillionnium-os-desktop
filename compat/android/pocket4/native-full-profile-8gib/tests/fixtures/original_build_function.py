def build(expected_sha):
    require(os.getuid() == 1000 and os.geteuid() == 1000, "build requires original operator uid")
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    context = verify_prepared(expected_sha)
    no_alias(ATTEMPT)
    no_alias(OUT)
    require(not ATTEMPT.exists() and not OUT.exists(), "attempt and output must both be fresh")
    affinity = sorted(os.sched_getaffinity(0))
    require(len(affinity) >= 4, "original two-core placement requires at least four allowed CPUs")
    selected = affinity[-2:]
    os.sched_setaffinity(0, selected)
    text = P("/proc/self/cgroup").read_text().strip()
    require(text.startswith("0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-"),
            "not the exact owned user build unit")
    cgroup = P("/sys/fs/cgroup") / text[3:].lstrip("/")
    unit = cgroup.name
    require(unit.startswith("hepta-runtime-job-") and unit.endswith(".service"), "unexpected unit")
    require(str(os.getpid()) in (cgroup / "cgroup.procs").read_text().split(), "controller not in its claimed unit")
    require((cgroup / "memory.max").read_text().strip() == str(MEMORY_MAX), "wrong MemoryMax")
    require((cgroup / "cpu.max").read_text().strip() == "200000 100000", "wrong CPUQuota")
    subprocess.run(["/usr/bin/systemctl", "--user", "set-property", "--runtime", unit,
                    "MemorySwapMax=0"], check=True, capture_output=True, timeout=15)
    # Only this exact owned job is changed. Its observed zero swap limit/current
    # and a fresh kernel RAM sample are saved before admission can pass or fail.
    memory, owned_budget_before, resource_admission_pin = record_resource_admission(cgroup)
    subreaper()
    require(child_ids() == [], "controller has preexisting children or cannot enumerate its own children")
    ATTEMPT.mkdir(mode=0o700)
    claim = {"schema": 1, "state": "STARTING_ORDINARY_ENGINE_AND_WHOLE_ART_PAIR_NORMAL_STRICT_BUILD",
             "started_utc": utc(), "preparation_sha256": expected_sha, "plan": plan(),
             "mem_available_before": memory["MemAvailable"], "swap_free_before": memory["SwapFree"],
             "resource_admission_receipt": resource_admission_pin,
             "resource_admission_qualified": True, "owned_budget_before_builder": owned_budget_before,
             "global_swap_is_owned_budget": False,
             "cpu_affinity_before": affinity,
             "cpu_affinity": selected, "unit": unit, "normal_builder_lock_and_recovery": True,
             "automatic_retry": False, "Main_resource_changes": False}
    claim["filesystem_available_before"] = os.statvfs(ACTIVE_WORK).f_bavail * os.statvfs(ACTIVE_WORK).f_frsize
    save(ATTEMPT / "claim.json", claim)
    save(ATTEMPT / "input-bindings-before.json", {
        "work_preparation": context["prepared_pin"], "actual_builder_compile": context["compiled_pin"],
        "actual_builder_manifest": context["builder_map_pin"], "actual_content_manifests": context["manifest_pins"],
        "reused_inventory_source": context["inventory_pin"], "observations": context["initial_observations"],
        "prior_failure_authorities": context["prior_failure_authority_pins"]})
    print(json.dumps(claim), flush=True)
    env = os.environ.copy()
    env["DROIDLOOM_NATIVE_BRIDGE_SOURCE"] = str(ENGINE_SOURCE)
    # The actual outer affinity selected exactly two CPUs above; do not reserve again.
    env["DROIDLOOM_COMPILER_CPUS_RESERVED"] = "1"
    env["PATH"] = "/usr/bin:/usr/sbin:/bin:/sbin"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    argv = plan()["argv"]
    start = time.monotonic()
    child = None
    code = None
    failure = None
    artifact = None
    cleanup = {"complete": False, "children": []}
    def interrupted(signum, frame):
        raise InterruptedError("owned build controller received signal " + str(signum))
    old_term = signal.signal(signal.SIGTERM, interrupted)
    try:
        with (ATTEMPT / "build.stdout").open("xb") as stdout, (ATTEMPT / "build.stderr").open("xb") as stderr:
            child = subprocess.Popen(argv, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                code = child.wait(timeout=6100)
            except BaseException:
                # No other thread/handler reaps this direct child. On a timed
                # out/interrupted wait its PID is retained until our exact wait;
                # this session/PGID was created solely for this owned builder.
                if child.returncode is None:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    code = child.wait(timeout=8)
                raise
        cleanup = cleanup_children()
        require(cleanup["complete"], "owned build descendants remain")
        require(code == 0, "normal builder returned " + str(code))
        artifact = completion_gate(context)
    except BaseException as error:
        failure = repr(error)
    finally:
        # A second interrupt must not abort bounded retirement after the first
        # one was recorded. Only this owned controller changes these handlers.
        old_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if not cleanup["complete"]:
            try:
                cleanup = cleanup_children()
            except Exception as error:
                cleanup = {"complete": False, "error": repr(error), "children": []}
        if not cleanup["complete"] and failure is None:
            failure = "owned descendants were not proven retired"
        input_after = None
        input_after_error = None
        try:
            input_after = verify_inputs_after(context)
            save(ATTEMPT / "input-bindings-after.json", input_after)
        except BaseException as error:
            input_after_error = repr(error)
            if failure is None:
                failure = "post-build input qualification failed: " + repr(error)
        observation_errors = []
        def observe(label, operation):
            try:
                return operation()
            except Exception as error:
                observation_errors.append({"observation": label, "error": repr(error)})
                return None
        terminal = {"schema": 1, "state": "ORDINARY_PAIR_COMMAND_COMPLETED_QUALIFICATION_PENDING" if failure is None else "FAILED",
                    "builder_returncode": code, "error": failure, "seconds": time.monotonic() - start,
                    "finished_utc": utc(), "cleanup": cleanup,
                    "stdout_sha256": observe("stdout", lambda: digest(ATTEMPT / "build.stdout")),
                    "stderr_sha256": observe("stderr", lambda: digest(ATTEMPT / "build.stderr")),
                    "memory_events": observe("memory_events", lambda: (cgroup / "memory.events").read_text()),
                    "memory_peak": observe("memory_peak", lambda: (cgroup / "memory.peak").read_text().strip()),
                    "memory_swap_peak": observe("memory_swap_peak", lambda: (cgroup / "memory.swap.peak").read_text().strip()),
                    "memory_swap_current": observe("memory_swap_current", lambda: (cgroup / "memory.swap.current").read_text().strip()),
                    "memory_swap_max": observe("memory_swap_max", lambda: (cgroup / "memory.swap.max").read_text().strip()),
                    "resource_admission_receipt": resource_admission_pin,
                    "owned_budget_before_builder": owned_budget_before,
                    "global_swap_is_owned_budget": False,
                    "source_projection_journal_present": (ACTIVE_WORK / "source-projection.json").exists(),
                    "normal_command_completion_gate": artifact,
                    "input_after_qualified": input_after is not None and input_after_error is None,
                    "input_after_error": input_after_error,
                    "work_preparation_sha256": PREPARATION_SHA, "builder_compile_sha256": FINAL_BUILDER_RECOVERY_SHA,
                    "historical_pair_validation_sha256": BUILD_RESULT_SHA,
                    "builder_sha256": BUILDER_SHA, "strict_targets": TARGETS,
                    "prior_failed_inner_sha256": PRIOR_INNER_SHA, "prior_failed_outer_sha256": PRIOR_OUTER_SHA,
                    "published_source_path": str(ACTIVE_SOURCE),
                    "source_reconciliation_uses_normal_builder": True,
                    "old_QA_epoch_invalid": True, "new_QA_epoch_qualified": False,
                    "complete_native_engine_and_ART_TU_qualified": False,
                    "runtime_authorization_enabled": False, "Main_actions": 0, "Android_actions": 0,
                    "service_started": False, "all_apps_ready": False}
        try:
            terminal["owned_resource_gate"] = owned_resource_gate(terminal["memory_events"])
            require(terminal["memory_swap_max"] == "0" and terminal["memory_swap_current"] == "0",
                    "owned zero-swap budget changed after build")
            terminal["owned_resource_gate"]["zero_swap_limit_and_current_observed_after"] = True
        except Exception as error:
            terminal["owned_resource_gate"] = {"pass": False, "error": repr(error)}
            if failure is None:
                failure = "owned resource qualification failed: " + repr(error)
                terminal["state"] = "FAILED"
                terminal["error"] = failure
        if observation_errors:
            terminal["observation_errors"] = observation_errors
            if failure is None:
                failure = "terminal resource/artifact observations incomplete"
                terminal["state"] = "FAILED"
                terminal["error"] = failure
        try:
            save(ATTEMPT / "terminal.json", terminal)
            print(json.dumps({"state": terminal["state"], "builder_returncode": code,
                              "terminal_sha256": digest(ATTEMPT / "terminal.json"),
                              "cleanup_complete": cleanup["complete"], "error": failure}), flush=True)
        finally:
            signal.signal(signal.SIGINT, old_int)
            signal.signal(signal.SIGTERM, old_term)
    return 0 if failure is None and cleanup["complete"] else 1
