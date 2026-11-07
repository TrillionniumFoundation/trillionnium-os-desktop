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
DISCOVERY_SHA = "9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886"
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
        need(argv == ["/usr/bin/droidloomctl","status","--json"] and
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


def run_context_route_controls(context, files, baseline, legacy_source, expected_manifest):
    """Invoke the actual production source loader used by open_context."""
    from pathlib import PurePosixPath
    source = files["current_discovery.py"]
    context_name = context.PACKAGE
    need(context_name == "com.united.mobile.android", "EXACT_INDEPENDENT_TARGET_CONTEXT_REQUIRED")
    context_source = files["united_context.py"]
    tree = ast.parse(context_source)
    opened = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == "open_context"]
    need(len(opened) == 1,"ONE_PRODUCTION_OPEN_CONTEXT_REQUIRED")
    calls = [n for n in ast.walk(opened[0]) if isinstance(n,ast.Call)]
    need(sum(isinstance(n.func,ast.Name) and n.func.id == "current_discovery" for n in calls) == 1 and
         not any(isinstance(n.func,ast.Attribute) and n.func.attr == "discover" for n in calls),
         "PRODUCTION_CONTEXT_MUST_ROUTE_CURRENT_DISCOVERY")
    rows = []
    def case():
        f = Fixture(baseline,source,legacy_source)
        root = PurePosixPath("/pure-owned-source")
        digest = hashlib.sha256(source).hexdigest()
        def verify(expected):
            need(expected == expected_manifest,"ROUTE_SOURCE_MANIFEST_CHANGED")
            return {"files":{"current_discovery.py":{"bytes":len(source),"sha256":digest}}}
        def load(path, expected, name):
            need(path == root/"current_discovery.py" and expected == digest and
                 name == "owned_current_discovery","CURRENT_DISCOVERY_SOURCE_LOAD_PIN")
            return f.current
        util = types.SimpleNamespace(module=load)
        return f,root,verify,util
    f,root,verify,util = case()
    result = context.current_discovery(util,expected_manifest,verify,root,f.app,f.baseline,f.epoch,f.guard)
    need(result == (f.init,f.environment,f.status) and f.status_calls == 1 and f.main_guards == 2,
         "PRODUCTION_CONTEXT_CURRENT_DISCOVERY_NOT_REACHED")
    rows.append({"name":"production_Context_loader_reaches_new_discover_complete","passed":True})
    f,root,verify,util = case()
    def wrong(expected):
        value = verify(expected);value["files"]["current_discovery.py"]["sha256"] = "0"*64
        return value
    try:context.current_discovery(util,expected_manifest,wrong,root,f.app,f.baseline,f.epoch,f.guard)
    except RuntimeError as error:
        need(str(error) == "CURRENT_DISCOVERY_SOURCE_LOAD_PIN","ROUTE_PIN_CONTROL_WRONG_CAUSE")
    else:raise RuntimeError("UNPINNED_CURRENT_DISCOVERY_ACCEPTED")
    need(f.status_calls == 0,"UNPINNED_DISCOVERY_SENT_STATUS")
    rows.append({"name":"production_Context_loader_rejects_changed_discovery_pin","passed":True})
    f,root,verify,util = case();f.current.BASELINE_SHA = "0"*64
    try:context.current_discovery(util,expected_manifest,verify,root,f.app,f.baseline,f.epoch,f.guard)
    except RuntimeError as error:
        need(str(error) == "CURRENT_DISCOVERY_SOURCE_BINDING_REQUIRED","ROUTE_BASELINE_CONTROL_WRONG_CAUSE")
    else:raise RuntimeError("WRONG_BASELINE_DISCOVERY_ACCEPTED")
    need(f.status_calls == 0,"WRONG_BASELINE_SENT_STATUS")
    rows.append({"name":"production_Context_loader_rejects_previous_baseline","passed":True})
    return rows


def run_bili_route_controls(entry, files, baseline, legacy_source, recorder):
    """Execute own production factory and bind; frozen MainBinding I/O is a seam."""
    from pathlib import PurePosixPath
    source = files["current_discovery.py"]
    factory_source = files["current_flow.py"]
    parsed = ast.parse(files["install_state.py"])
    workers = [n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name == "worker"]
    need(len(workers) == 1,"ONE_PRODUCTION_BILI_WORKER_REQUIRED")
    calls = [n for n in ast.walk(workers[0]) if isinstance(n,ast.Call)]
    need(sum(isinstance(n.func,ast.Name) and n.func.id == "current_flow_type" for n in calls) == 1 and
         not any(isinstance(n.func,ast.Attribute) and n.func.attr == "Flow" for n in calls),
         "PRODUCTION_BILI_WORKER_MUST_ROUTE_CURRENT_FLOW")
    rows = []
    def case():
        f = Fixture(baseline,source,legacy_source)
        factory = types.ModuleType("production_owned_flow_factory")
        exec(compile(factory_source,"<production-owned-flow>","exec"),factory.__dict__)
        manifest = {"files":{name:{"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
            for name,raw in (("current_discovery.py",source),("current_flow.py",factory_source))}}
        loads = []
        def load(path, expected, name):
            leaf = path.name
            need(path == entry.HERE/leaf and leaf in manifest["files"] and
                 expected == manifest["files"][leaf]["sha256"] and
                 name == {"current_discovery.py":"owned_current_discovery",
                          "current_flow.py":"owned_current_flow"}[leaf],
                 "CURRENT_FLOW_SOURCE_LOAD_PIN")
            loads.append(leaf)
            return f.current if leaf == "current_discovery.py" else factory
        namespace = dict(entry.current_flow_type.__globals__)
        namespace["module"] = load
        gate = types.FunctionType(entry.current_flow_type.__code__,namespace)
        return f,factory,manifest,loads,gate
    f,factory,manifest,loads,gate = case()
    writes = []
    recorder_view = types.SimpleNamespace(**vars(recorder))
    recorder_view.write_new = lambda path,value:writes.append((path,value))
    current_type = gate(manifest,recorder_view)
    need(issubclass(current_type,recorder.Flow) and current_type.bind is not recorder.Flow.bind and
         all(getattr(current_type,name) is getattr(recorder.Flow,name) for name in
             ("__init__","guard","begin","command","android","close","launch","cleanup")) and
         loads == ["current_discovery.py","current_flow.py"],
         "EXACT_R6_INHERITANCE_AND_CURRENT_BIND_ONLY_REQUIRED")
    holder = {}
    class BindingBoundary:
        def __init__(self, *, contract, source, scope, activation, epoch, app, guard):
            need(app is not f.app and set(vars(app)) == {"discover"},
                 "BIND_MUST_RECEIVE_EXPLICIT_DISCOVERY_FACADE")
            holder["discovery"] = app.discover()
            self.record = {"schema":2,"fixture_not_runtime":True}
        def transport(self, *, record, runner, guard):
            holder["runner"] = runner
            return object()
        def close(self):
            holder["closed"] = True
    def contract_load(name, label):
        need(name == "main_binding.py" and label == "bili_main_binding",
             "ORIGINAL_MAIN_BINDING_LOAD_REQUIRED")
        return types.SimpleNamespace(MainBinding=BindingBoundary)
    flow = current_type.__new__(current_type)
    flow.binding = None;flow.transport = None
    flow.contract = types.SimpleNamespace(load=contract_load)
    flow.source = object();flow.scope = object()
    flow.activation = f.baseline;flow.epoch = f.epoch;flow.app = f.app
    flow.guard = lambda attempted=False:f.guard()
    flow.step = PurePosixPath("/pure-owned-step")
    flow.action_attempted = False;flow._android_mutation = False;flow._private_backend_transport = False
    returned = flow.bind()
    need(returned is flow.binding and holder["discovery"] == (f.init,f.environment,f.status) and
         f.main_guards == 2 and f.status_calls == 1 and
         flow.app is f.app and len(writes) == 1 and
         writes[0][0] == flow.step/"held-main-binding.json",
         "PRODUCTION_CURRENT_BIND_MUST_REACH_NEW_DISCOVERY")
    # Exercise the copied runner's symbol bindings without invoking transport.
    sentinel = object();flow.command = lambda *args,**options:sentinel
    need(holder["runner"](["/pure-owned-command"],timeout=1,close_fds=True,
        stdout=recorder.subprocess.PIPE,stderr=recorder.subprocess.PIPE,pass_fds=(),
        env={}) is sentinel,"COPIED_RUNNER_MUST_DELEGATE_ORIGINAL_COMMAND_BOUNDARY")
    rows.append({"name":"production_Bili_factory_and_bind_reach_current_discovery","passed":True})
    f,factory,manifest,loads,gate = case()
    changed = copy.deepcopy(manifest);changed["files"]["current_discovery.py"]["sha256"] = "0"*64
    try:gate(changed,recorder)
    except RuntimeError as error:
        need(str(error) == "CURRENT_FLOW_SOURCE_LOAD_PIN","FLOW_PIN_CONTROL_WRONG_CAUSE")
    else:raise RuntimeError("UNPINNED_DISCOVERY_FACTORY_ACCEPTED")
    need(f.status_calls == 0,"UNPINNED_FACTORY_SENT_STATUS")
    rows.append({"name":"production_Bili_factory_loader_rejects_changed_source_pin","passed":True})
    f,factory,manifest,loads,gate = case();factory.MAIN_EPOCH = "0"*64
    try:gate(manifest,recorder)
    except RuntimeError as error:
        need(str(error) == "CURRENT_FLOW_FACTORY_SOURCE_BINDING_REQUIRED",
             "FLOW_BASELINE_CONTROL_WRONG_CAUSE")
    else:raise RuntimeError("OLD_FLOW_EPOCH_ACCEPTED")
    need(f.status_calls == 0,"OLD_FLOW_EPOCH_SENT_STATUS")
    rows.append({"name":"production_Bili_factory_loader_rejects_previous_epoch","passed":True})
    return rows
