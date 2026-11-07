"""Pure seams for the new typed MainFence bridge; no Main, fd or process access."""
import ast, copy, json, types

def run(candidate_source, baseline_source, historical_main):
    checks = []
    def need(value, message):
        if not value: raise AssertionError(message)
    def loaded():
        module = types.ModuleType("tested_owner20_support")
        exec(compile(candidate_source, "<Owner20 support under pure controls>", "exec"), module.__dict__)
        return module
    def case(name, body):
        body()
        checks.append({"name": name, "passed": True})
    def denied(call, text):
        try: call()
        except RuntimeError as error:
            need(text in str(error), "wrong failure: " + str(error))
            return error
        raise AssertionError("negative control accepted")
    def setup():
        mod = loaded()
        state = {"reads": 0, "opens": [], "pidfds": [], "closes": [], "proof_calls": [],
                 "captures": 0, "resource_reads": [], "artifact_checks": [], "close_failure": None,
                 "pidfd_failure_at": None, "capture_failure_at": None, "proof_failure": None,
                 "resource_failure": None}
        authority = copy.deepcopy(mod.CURRENT_MAIN_AUTHORITY)
        role_pids = {"android_init":3588093, "daemon":3588022, "launcher":3588089,
                     "presenter":3588024, "surfaceflinger":3588912,
                     "system_server":90516, "zygote64":90360}
        # Synthetic minimal rows exercise wiring only; this is not a private
        # baseline fixture or a substitute for its separately pinned policy.
        rows = {role:{"host_pid":pid, "start_ticks":100 + i}
                for i,(role,pid) in enumerate(role_pids.items())}
        b = {"schema":"pocket4-main-current-baseline-v1", "kind":"current-framework-generation",
             "deployment_performed":False, "old_epoch_sha256":historical_main["framework_sha256"],
             "framework_epoch":{"sha256":authority["current_epoch_sha256"]},
             "limits":copy.deepcopy(historical_main["resources"]),
             "all_seven_processes":{"binding":{"boot_id":historical_main["framework_binding"]["boot_id"],
                                                "processes":rows}}}
        proof = {"schema":"pocket4-current-main-guard-v1",
                 "Main_epoch_sha256":authority["current_epoch_sha256"],
                 "current_baseline_sha256":authority["baseline"]["sha256"],
                 "current_baseline_qualification_sha256":authority["qualification"]["sha256"],
                 "seven_processes_match":True, "three_host_processes_match":True,
                 "resource_limits_match":True, "current_executable_and_root_backing_match":True,
                 "framework_exit_cause_resolved":False, "production_ready":False}
        guard_body = (
            "MAIN_EPOCH = " + repr(authority["current_epoch_sha256"]) + "\n" +
            "BASELINE_SHA = " + repr(authority["baseline"]["sha256"]) + "\n" +
            "QUALIFICATION_SHA = " + repr(authority["qualification"]["sha256"]) + "\n" +
            "SOURCE_MANIFEST_SHA = " + repr(authority["source_manifest_sha256"]) + "\n" +
            "def current_baseline(): return _baseline\n" +
            "def current_guard(candidate, *, action_attempted=False):\n" +
            "    return _proof(candidate, action_attempted)\n").encode()
        def full_guard(candidate, attempted):
            need(candidate is b and attempted is False, "current cached baseline not passed unchanged")
            state["proof_calls"].append("fresh")
            if state["proof_failure"]: raise RuntimeError(state["proof_failure"])
            return copy.deepcopy(proof)
        def module_factory(name):
            m = types.ModuleType(name)
            m._baseline = b; m._proof = full_guard
            return m
        def read_guard():
            state["reads"] += 1
            if state.get("changed_published_guard") and state["reads"] > 1:
                return guard_body + b"# changed\n"
            return guard_body
        mod.types = types.SimpleNamespace(ModuleType=module_factory)
        mod.MainFence.read_guard = staticmethod(read_guard)
        real_os = mod.os
        def pidfd_open(pid):
            state["pidfds"].append(pid)
            if state["pidfd_failure_at"] == len(state["pidfds"]):
                raise RuntimeError("injected pidfd allocation failure")
            return 1000 + pid
        def close(fd):
            state["closes"].append(fd)
            if fd == state["close_failure"]: raise OSError("injected close ambiguity")
        def opened(path, flags):
            need(path == "/sys/fs/cgroup/system.slice/droidloomd.service", "unexpected path")
            state["opens"].append(path); return 31
        info = types.SimpleNamespace(st_dev=30, st_ino=26651611)
        mod.os = types.SimpleNamespace(pidfd_open=pidfd_open, open=opened, close=close,
            fstat=lambda fd:info, stat=lambda path,follow_symlinks:info,
            O_RDONLY=real_os.O_RDONLY, O_DIRECTORY=real_os.O_DIRECTORY,
            O_CLOEXEC=real_os.O_CLOEXEC, O_NOFOLLOW=real_os.O_NOFOLLOW)
        class Boot:
            def __init__(self, path):
                need(path == "/proc/sys/kernel/random/boot_id", "unexpected boot path")
            def read_text(self):return historical_main["framework_binding"]["boot_id"] + "\n"
        mod.Path = Boot
        mod.props = lambda unit:{"ActiveState":"active", **historical_main["daemon"]}
        fd_rows = {1000+row["host_pid"]:row for row in rows.values()}
        def capture(fence, fd):
            state["captures"] += 1
            if state["capture_failure_at"] == state["captures"]:
                return {"host_pid":1,"start_ticks":1}
            return copy.deepcopy(fd_rows[fd])
        mod.MainFence.capture = capture
        def bounded(fd,key,limit):
            need(fd == 31 and limit == 128, "resource read authority")
            state["resource_reads"].append(key)
            return ("6144" if key == state["resource_failure"] else historical_main["resources"][key]).encode()
        def pinned(path, digest, executable):
            need(historical_main["artifacts"].get(path) == digest, "historical artifact changed")
            state["artifact_checks"].append(path); return 41 + len(state["artifact_checks"])
        actor = {"require_cgroup2":lambda fd:need(fd==31,"wrong group"),
                 "bounded":bounded,"pinned":pinned}
        plan = {"main":copy.deepcopy(historical_main),"current_main":authority}
        return mod,state,plan,actor,b,proof

    def accepted():
        m,s,p,a,b,proof=setup()
        fence=m.MainFence(p,a)
        need(set(s["pidfds"]) == {3588093,3588022,3588089,3588024,3588912,90516,90360},
             "historical zygote/server incorrectly adopted")
        need(3588887 not in s["pidfds"] and 3589120 not in s["pidfds"],"old epoch revived")
        value=fence.check()
        need(value["framework_sha256"] != value["historical_framework_sha256"] and
             value["old_epoch_reauthorized"] is False and value["private_baseline_body_exported"] is False and
             "current" not in value and "all_seven_processes" not in value,
             "typed/current/private scope confused")
        need(s["proof_calls"] == ["fresh"] * 4 and s["captures"] == 28 and
             len(s["resource_reads"]) == 10 and len(s["artifact_checks"]) == 6,
             "full and held guards not repeated")
        fence.close()
        need(len(set(s["closes"])) == len(s["closes"]) and not fence.processes and fence.group is None,
             "descriptor close repeated")
    case("current_seven_pidfds_and_typed_safe_receipt",accepted)

    def reject_before_io(change,text):
        m,s,p,a,*_=setup();change(p)
        denied(lambda:m.MainFence(p,a),text)
        need(s["reads"] == 0 and not s["pidfds"] and not s["opens"],"gate did I/O before rejection")
    case("missing_current_authority_zero_io",lambda:reject_before_io(
        lambda p:p.pop("current_main"),"exact current Main authority"))
    case("historical_epoch_cannot_be_current",lambda:reject_before_io(
        lambda p:p["current_main"].update(current_epoch_sha256=p["main"]["framework_sha256"]),
        "exact current Main authority"))
    case("historical_deployment_bytes_preserved",lambda:reject_before_io(
        lambda p:p["main"]["resources"].update({"pids.max":"6144"}),"historical Main deployment lineage"))

    def pidfd_failure():
        m,s,p,a,*_=setup();s["pidfd_failure_at"]=4
        denied(lambda:m.MainFence(p,a),"injected pidfd allocation failure")
        need(len(s["closes"]) == 3 and not s["opens"],"partial pidfds not all closed")
    case("partial_current_pidfd_acquisition_closes_all",pidfd_failure)

    def close_failure():
        m,s,p,a,*_=setup();f=m.MainFence(p,a);s["closes"].clear()
        s["close_failure"]=next(iter(f.processes.values()))
        denied(f.close,"descriptor close failed")
        need(len(s["closes"]) == 8 and len(set(s["closes"])) == 8,"close failure skipped another fd")
        denied(f.close,"descriptor close failed")
        need(len(s["closes"]) == 8,"ambiguous close retried")
    case("close_failure_is_sticky_without_retry_and_closes_remaining",close_failure)

    def guard_failure():
        m,s,p,a,*_=setup();s["proof_failure"]="injected exact guard failure"
        denied(lambda:m.MainFence(p,a),"injected exact guard failure")
        need(s["captures"] == 0 and len(s["closes"]) == 8,"guard failure qualified or leaked")
    case("full_current_guard_failure_prevents_held_acceptance",guard_failure)

    def capture_failure(n):
        m,s,p,a,*_=setup();s["capture_failure_at"]=n
        denied(lambda:m.MainFence(p,a),"current Main")
        need(len(s["closes"]) == 8 + len(s["artifact_checks"]),"changed held process leaked descriptors")
    case("current_pidfd_identity_swap_rejected",lambda:capture_failure(1))
    case("process_change_after_artifact_checks_rejected",lambda:capture_failure(8))

    def resource_failure():
        m,s,p,a,*_=setup();s["resource_failure"]="pids.max"
        denied(lambda:m.MainFence(p,a),"Main resource changed")
        need(not s["artifact_checks"] and len(s["closes"]) == 8,"resource mismatch continued")
    case("pids12288_remains_exact",resource_failure)

    def guard_source_failure():
        m,s,p,a,*_=setup();s["changed_published_guard"]=True
        denied(lambda:m.MainFence(p,a),"published current guard changed")
        need(not s["proof_calls"] and len(s["closes"]) == 8,"changed published code used")
    case("published_guard_replacement_rejected",guard_source_failure)

    def source_scope():
        old=ast.parse(baseline_source);new=ast.parse(candidate_source)
        olddefs={n.name:ast.dump(n,include_attributes=False) for n in old.body
                 if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
        newdefs={n.name:ast.dump(n,include_attributes=False) for n in new.body
                 if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
        need(set(olddefs)==set(newdefs),"unexpected new runtime function")
        need(all(newdefs[k]==v for k,v in olddefs.items() if k!="MainFence"),"unrelated original helper changed")
        need("current_main" not in baseline_source and "CURRENT_MAIN_AUTHORITY" in candidate_source,
             "historical source relabelled")
    case("only_MainFence_runtime_definition_changes",source_scope)
    need(len(checks)==12,"control count")
    return {"schema":"owner20-current-main-bridge-pure-controls-v1","passed":True,"count":len(checks),
            "controls":checks,"all_process_and_guard_IO_are_explicit_seams":True,
            "private_baseline_body_used":False,"current_Main_runtime_qualified":False,
            "process_children":0,"pidfds_opened":0,"Main_accessed":False,"Android_commands":0}
