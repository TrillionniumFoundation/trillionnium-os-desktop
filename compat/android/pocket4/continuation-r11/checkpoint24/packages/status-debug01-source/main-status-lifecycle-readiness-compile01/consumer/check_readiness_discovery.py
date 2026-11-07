"""Targeted current-owner discovery controls using private in-memory I/O seams.

Real production discover_current and the exact legacy discover function run.
No /proc read, Status child, Android command or write occurs in these fixtures.
The caller supplies the already qualified private baseline only in memory.
"""
import ast
import copy
import hashlib
import io
import json
import re
import types

LEGACY_SHA = "eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66"
DISCOVERY_SHA = "dfd1208793980d92664f55aab040042cdc4cdd5e0ec7e66f016e0140d87a58f5"
BASE_COUNT = 15


def need(value, code):
    if not value:
        raise RuntimeError(code)


class Fixture:
    def __init__(self, baseline, discovery_source, legacy_source):
        need(hashlib.sha256(legacy_source).hexdigest() == LEGACY_SHA and
             hashlib.sha256(discovery_source).hexdigest() == DISCOVERY_SHA,
             "EXACT_PRODUCTION_DISCOVERY_CONTROL_SOURCES")
        self.baseline = copy.deepcopy(baseline)
        self.source = discovery_source
        self.main_guards = 0
        self.fail_guard_at = None
        self.status_calls = 0
        self.expected_subcommand = "status"
        self.identity_calls = []
        self.environment_reads = 0
        self.records = []
        self.rows = {
            "daemon":self.baseline["daemon_process"],
            "launcher":self.baseline["launcher_process"],
            "android_init":self.baseline["framework_epoch"]["binding"]["processes"]["init"],
            "owner_intermediary":self.baseline["owner_lineage"]["intermediary_process"]}
        self.live = {row["host_pid"]:copy.deepcopy(row) for row in self.rows.values()}
        self.private_io = {pid:copy.deepcopy(row) for pid,row in self.live.items()}
        self.init = self.rows["android_init"]["host_pid"]
        self.bridge = 2000000000
        need(self.bridge not in self.live, "SYNTHETIC_BRIDGE_PID_COLLISION")
        self.private_io[self.bridge] = {
            "host_pid":self.bridge, "parent_host_pid":self.init, "uids":[0,0,0,0],
            "cmdline":["app_process","/system/bin","com.android.droidloom.input.InputBridge"],
            "executable":"/system/bin/app_process64",
            "namespaces":dict(self.rows["android_init"]["namespaces"])}
        self.status = {"state":"running","message":"Android is ready",
                       "host_pid":self.rows["launcher"]["host_pid"]}
        self.environment = {"PATH":"/system/bin","BOOTCLASSPATH":"/system/framework/control.jar",
            "DEX2OATBOOTCLASSPATH":"/system/framework/control.jar","ANDROID_ROOT":"/system",
            "ANDROID_DATA":"/data","ANDROID_ART_ROOT":"/apex/com.android.art"}
        legacy = types.ModuleType("memory_legacy_discovery")
        legacy.__dict__.update(json=json,re=re,open=self.open,
            os=types.SimpleNamespace(readlink=self.readlink),
            glob=types.SimpleNamespace(glob=self.glob),
            subprocess=types.SimpleNamespace(PIPE=object(),run=self.status_run))
        selected = {"proc_cmd","ppid","require_root_process","cell_ancestors","discover"}
        body = [n for n in ast.parse(legacy_source).body
                if (isinstance(n,ast.FunctionDef) and n.name in selected) or
                   (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and
                       t.id in {"CTL","HOST_ENV","ENV_KEYS"} for t in n.targets))]
        need({n.name for n in body if isinstance(n,ast.FunctionDef)} == selected,
             "EXACT_LEGACY_DISCOVERY_FUNCTION_SET")
        exec(compile(ast.Module(body=body,type_ignores=[]),"<exact-legacy-discovery>","exec"),
             legacy.__dict__)
        self.app = legacy
        self.epoch = types.SimpleNamespace(process_identity=self.process_identity)
        self.current = types.ModuleType("memory_current_discovery")
        self.current.__dict__["open"] = self.open
        exec(compile(discovery_source,"<production-current-discovery>","exec"),self.current.__dict__)

    def process_identity(self, pid):
        self.identity_calls.append(pid)
        return copy.deepcopy(self.live[pid])

    def guard(self):
        self.main_guards += 1
        if self.main_guards == self.fail_guard_at:
            raise RuntimeError("CONTROL_MAIN_GUARD_STOP")

    def glob(self, pattern):
        need(pattern == "/proc/[0-9]*","EXACT_LEGACY_PROC_GLOB")
        return ["/proc/"+str(self.bridge)]

    def status_run(self, argv, **options):
        need(argv == ["/usr/bin/droidloomctl",self.expected_subcommand,"--json"] and
             options == {"stdout":self.app.subprocess.PIPE,"stderr":self.app.subprocess.PIPE,
                "timeout":8,"env":self.app.HOST_ENV,"check":True} and self.status_calls == 0,
             "EXACT_ONCE_LEGACY_STATUS_CALL")
        self.status_calls += 1
        return types.SimpleNamespace(stdout=json.dumps(self.status).encode())

    def readlink(self, path):
        if path == "/proc/self/ns/mnt":
            return "mnt:[1]"
        match = re.fullmatch(r"/proc/([1-9][0-9]*)/(exe|ns/(mnt|pid|uts|ipc))",path)
        need(match is not None,"MEMORY_DISCOVERY_READLINK_ONLY")
        row = self.private_io[int(match.group(1))]
        if match.group(2) == "exe":
            return row["executable"]
        namespace = match.group(3)
        return row["namespaces"].get(namespace,namespace+":[2]")

    def open(self, path, mode="r", **options):
        match = re.fullmatch(r"/proc/([1-9][0-9]*)/(cmdline|status|environ)",str(path))
        need(match is not None,"MEMORY_DISCOVERY_FILES_ONLY")
        pid,kind = int(match.group(1)),match.group(2)
        row = self.private_io[pid]
        if kind == "cmdline":
            need(mode == "rb","MEMORY_CMDLINE_MODE")
            return io.BytesIO(b"\0".join(x.encode() for x in row["cmdline"])+b"\0")
        if kind == "status":
            need(mode == "r" and options == {"encoding":"utf-8","errors":"replace"},
                 "MEMORY_STATUS_MODE")
            return io.StringIO("PPid:\t"+str(row["parent_host_pid"])+"\nUid:\t"+
                               " ".join(str(x) for x in row["uids"])+"\n")
        need(pid == self.bridge and mode == "rb","MEMORY_ENVIRONMENT_MODE")
        self.environment_reads += 1
        return io.BytesIO(b"\0".join((k+"="+v).encode() for k,v in self.environment.items())+b"\0")

    def discover(self):
        self.expected_subcommand = "readiness"
        return self.current.discover_current(self.app,self.baseline,self.epoch,self.guard)


def run_discovery_controls(discovery_source, baseline, legacy_source):
    rows = []
    def fresh():
        return Fixture(baseline,discovery_source,legacy_source)
    def reject(name, fixture, call, code):
        try:
            call()
        except RuntimeError as error:
            need(str(error) == code,"DISCOVERY_CONTROL_WRONG_FIRST_ERROR:"+name)
        else:
            raise RuntimeError("DISCOVERY_NEGATIVE_ACCEPTED:"+name)
        rows.append({"name":name,"passed":True})

    fixture = fresh()
    reject("legacy_production_discover_reproduces_current_owner_rejection",fixture,
        fixture.app.discover,"UNEXPECTED_CELL_OWNER")
    fixture = fresh()
    init,environment,status = fixture.discover()
    need(init == fixture.init and environment == fixture.environment and status == fixture.status and
         fixture.status_calls == 1 and fixture.main_guards == 2 and
         len(fixture.identity_calls) == 8,
         "CURRENT_CHAIN_MUST_REACH_FULL_PRODUCTION_DISCOVERY")
    rows.append({"name":"production_current_discovery_complete_qualified_chain","passed":True})

    fixture = fresh();fixture.baseline["schema"] = "pocket4-main-current-baseline-v1"
    reject("old_baseline_rejected_before_Status",fixture,fixture.discover,
           "EXACT_CURRENT_DISCOVERY_BASELINE_REQUIRED")
    need(fixture.status_calls == 0,"INVALID_BASELINE_SENT_STATUS")
    fixture = fresh()
    fixture.baseline["owner_lineage"]["intermediary_process"]["cmdline"].append("foreign")
    reject("forged_baseline_owner_argv_rejected",fixture,fixture.discover,
           "QUALIFIED_CURRENT_OWNER_IDENTITY_REQUIRED")
    fixture = fresh();fixture.baseline["owner_lineage"]["intermediary_program_authority_assigned"] = True
    reject("intermediary_command_authority_not_adopted",fixture,fixture.discover,
           "EXACT_CURRENT_OWNER_LINEAGE_REQUIRED")
    fixture = fresh();fixture.status["host_pid"] = fixture.rows["owner_intermediary"]["host_pid"]
    reject("Status_must_report_fixed_launcher_not_intermediary",fixture,fixture.discover,
           "STATUS_AND_INIT_MUST_MATCH_CURRENT_BASELINE")

    mutations = [
        ("intermediary_birth_changed","owner_intermediary",lambda r:r.update(start_ticks=r["start_ticks"]+1)),
        ("intermediary_argv_changed","owner_intermediary",lambda r:r["cmdline"].append("foreign")),
        ("intermediary_executable_changed","owner_intermediary",lambda r:r.update(executable="/foreign")),
        ("intermediary_uid_changed","owner_intermediary",lambda r:r.update(uids=[1,1,1,1])),
        ("intermediary_namespace_changed","owner_intermediary",lambda r:r["namespaces"].update(mnt="mnt:[1]")),
        ("launcher_parent_changed","launcher",lambda r:r.update(parent_host_pid=2)),
        ("init_parent_changed","android_init",lambda r:r.update(parent_host_pid=2)),
    ]
    for name,role,change in mutations:
        fixture = fresh();change(fixture.live[fixture.rows[role]["host_pid"]])
        reject(name,fixture,fixture.discover,"CURRENT_DISCOVERY_PROCESS_IDENTITY_CHANGED")
        need(fixture.environment_reads == 0,"BAD_OWNER_READ_ENVIRONMENT")
    fixture = fresh();fixture.fail_guard_at = 1
    reject("first_Main_guard_failure_stops_before_Status",fixture,fixture.discover,"CONTROL_MAIN_GUARD_STOP")
    need(fixture.status_calls == 0,"FAILED_FIRST_GUARD_SENT_STATUS")
    fixture = fresh();fixture.fail_guard_at = 2
    reject("final_Main_guard_failure_cannot_return_discovery",fixture,fixture.discover,"CONTROL_MAIN_GUARD_STOP")
    need(len(rows) == BASE_COUNT and len({r["name"] for r in rows}) == BASE_COUNT,
         "EXACT_CURRENT_OWNER_DISCOVERY_CONTROL_COUNT")
    return rows



def run_readiness_controls(discovery_source, baseline, legacy_source):
    """Run the real new discovery with the original exact owner fixtures."""
    import subprocess
    rows = run_discovery_controls(discovery_source, baseline, legacy_source)

    def fresh():
        return Fixture(baseline, discovery_source, legacy_source)

    def reject_response(name, message, state):
        fixture = fresh()
        fixture.status.update(message=message, state=state)
        try:
            fixture.discover()
        except RuntimeError as error:
            need(str(error) == "DROIDLOOM_NOT_READY", "READINESS_RESPONSE_FIRST_ERROR")
        else:
            raise RuntimeError("READINESS_RESPONSE_ACCEPTED:" + name)
        need(fixture.expected_subcommand == "readiness" and fixture.status_calls == 1 and
             fixture.main_guards == 1 and not fixture.identity_calls and
             fixture.environment_reads == 0, "FAILED_READINESS_MUST_STOP_BEFORE_OWNER_AND_ENV")
        rows.append({"name": name, "passed": True})

    reject_response("lifecycle_running_response_does_not_prove_Android_ready",
        "cell fixture is running; Android readiness has not been checked", "running")
    reject_response("fresh_boot_phase_does_not_prove_Android_ready",
        "cell fixture is running; Android boot phase: waiting for Android to complete boot", "running")
    reject_response("stopped_state_cannot_reuse_a_ready_message",
        "Android is ready", "stopped")

    for name, error in [
        ("eight_second_timeout_is_preserved_without_Status_fallback",
         subprocess.TimeoutExpired(["/usr/bin/droidloomctl", "readiness", "--json"], 8)),
        ("checked_readiness_failure_is_preserved_without_Status_fallback",
         subprocess.CalledProcessError(1, ["/usr/bin/droidloomctl", "readiness", "--json"])),
    ]:
        fixture = fresh()
        def failed_run(argv, **options):
            fixture.status_run(argv, **options)
            raise error
        fixture.app.subprocess.run = failed_run
        try:
            fixture.discover()
        except BaseException as observed:
            need(observed is error, "READINESS_TRANSPORT_FIRST_ERROR_CHANGED")
        else:
            raise RuntimeError("READINESS_TRANSPORT_FAILURE_ACCEPTED")
        need(fixture.expected_subcommand == "readiness" and fixture.status_calls == 1 and
             fixture.main_guards == 1 and not fixture.identity_calls and
             fixture.environment_reads == 0, "READINESS_TRANSPORT_RETRIED_OR_USED_STALE_RESULT")
        rows.append({"name": name, "passed": True})
    need(len(rows) == 20 and len({row["name"] for row in rows}) == 20,
         "EXACT_FIFTEEN_OWNER_AND_FIVE_READINESS_CONTROLS")
    return {"count": 20, "cases": rows, "executed_production": "discover_current",
            "IO": "explicit in-memory fixtures", "Android_actions": 0,
            "real_children": 0, "private_baseline_exported": False}
