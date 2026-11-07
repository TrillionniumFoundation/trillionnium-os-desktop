"""Explicit current-cell discovery for the separately pinned owned controller.

The legacy android-app and shared R6 files remain byte exact. This controller
requests one explicit fresh Readiness response with the original eight-second
checked subprocess bound. The ready predicate, unique InputBridge, namespace,
environment and complete owner-chain gates remain unchanged. Lifecycle Status
is never used as a fallback or accepted as Android readiness.

The intermediary identity comes from the qualified current baseline. The
caller's complete Main guard still runs on both sides; no process is adopted
and no legacy globals are overwritten.
"""
import hashlib
import json
import types

BASELINE_SHA = "633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364"
QUALIFICATION_SHA = "ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e"
MAIN_EPOCH = "7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c"
OWNER_IDENTITY_PINS = {
  "daemon": "0c97203b9dcf0334fb796b6d5264dba1df3644f048180f709b687671a37e7aaa",
  "launcher": "b1a6ea5384d7096772650aa7ea3f4db22b70b112d054521e339fea4df3f3c830",
  "android_init": "25b9e20a0d7fe4a67a4ed645223532be0af4df4f0923385c63bf8575d44fdf01",
  "owner_intermediary": "2705458a631597a25618cf841426fd6319ab5c3f7aae051c1f037cf480416a33"
}
IDENTITY_KEYS = {"host_pid","parent_host_pid","start_ticks","namespace_pids",
                 "uids","cmdline","executable","namespaces","cgroup"}


def require(value, code):
    if not value:
        raise RuntimeError(code)


def identity_sha(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(",",":"),allow_nan=False).encode()).hexdigest()


def expected_owner_chain(baseline):
    require(type(baseline) is dict and
            baseline.get("schema") == "pocket4-main-current-baseline-v2" and
            baseline.get("kind") == "current-cell-generation" and
            baseline.get("deployment_performed") is False and "main_deployed" not in baseline and
            baseline.get("framework_exit_cause_resolved") is False and
            baseline.get("whole_app_production_ready") is False and
            baseline["framework_epoch"]["sha256"] == MAIN_EPOCH,
            "EXACT_CURRENT_DISCOVERY_BASELINE_REQUIRED")
    lineage = baseline["owner_lineage"]
    require(lineage.get("schema") == "pocket4-current-cell-owner-lineage-v1" and
            lineage.get("intermediary_program_authority_assigned") is False,
            "EXACT_CURRENT_OWNER_LINEAGE_REQUIRED")
    rows = {"daemon":baseline["daemon_process"],"launcher":baseline["launcher_process"],
            "android_init":baseline["framework_epoch"]["binding"]["processes"]["init"],
            "owner_intermediary":lineage["intermediary_process"]}
    for role,row in rows.items():
        require(type(row) is dict and set(row) == IDENTITY_KEYS and
                identity_sha(row) == OWNER_IDENTITY_PINS[role],
                "QUALIFIED_CURRENT_OWNER_IDENTITY_REQUIRED")
    daemon, launcher, init, intermediary = (rows[name] for name in
        ("daemon","launcher","android_init","owner_intermediary"))
    require(launcher["parent_host_pid"] == daemon["host_pid"] and
            intermediary["parent_host_pid"] == launcher["host_pid"] and
            init["parent_host_pid"] == intermediary["host_pid"] and
            len({row["host_pid"] for row in rows.values()}) == 4 and
            baseline["status"] == {"host_pid":launcher["host_pid"]},
            "QUALIFIED_CURRENT_OWNER_CHAIN_REQUIRED")
    return rows


def verify_current_owner(app, baseline, epoch, status, init):
    rows = expected_owner_chain(baseline)
    require(type(status) is dict and type(status.get("host_pid")) is int and
            status["host_pid"] == rows["launcher"]["host_pid"] and
            type(init) is int and init == rows["android_init"]["host_pid"],
            "STATUS_AND_INIT_MUST_MATCH_CURRENT_BASELINE")
    for role,row in rows.items():
        require(epoch.process_identity(row["host_pid"]) == row,
                "CURRENT_DISCOVERY_PROCESS_IDENTITY_CHANGED")
    require(app.ppid(init) == rows["owner_intermediary"]["host_pid"] and
            app.ppid(rows["owner_intermediary"]["host_pid"]) == rows["launcher"]["host_pid"] and
            app.ppid(rows["launcher"]["host_pid"]) == rows["daemon"]["host_pid"],
            "CURRENT_DISCOVERY_PARENT_CHAIN_CHANGED")
    return rows["owner_intermediary"]


def discovery_view(app, baseline, epoch, guard):
    """An explicit MainBinding parameter; never patch the legacy module."""
    return types.SimpleNamespace(discover=lambda:discover_current(app,baseline,epoch,guard))


def discover_current(app, baseline, epoch, guard):
    require(callable(guard), 'CURRENT_DISCOVERY_GUARD_REQUIRED')
    expected_owner_chain(baseline)
    guard()
    status=json.loads(app.subprocess.run([app.CTL,'readiness','--json'],stdout=app.subprocess.PIPE,stderr=app.subprocess.PIPE,timeout=8,env=app.HOST_ENV,check=True).stdout)
    if status.get('state')!='running' or 'Android is ready' not in status.get('message',''):
        raise RuntimeError('DROIDLOOM_NOT_READY')
    host=status.get('host_pid')
    app.require_root_process(host)
    bridges=[]
    for p in app.glob.glob('/proc/[0-9]*'):
        try:
            pid=int(p.rsplit('/',1)[1])
            if app.proc_cmd(pid)=='app_process /system/bin com.android.droidloom.input.InputBridge':
                ancestors=app.cell_ancestors(pid,host)
                if ancestors is not None: bridges.append((pid,ancestors))
        except (OSError,ValueError):
            pass
    if len(bridges)!=1: raise RuntimeError(f'INPUT_BRIDGE_COUNT:{len(bridges)}')
    bridge,ancestors=bridges[0]; init=None
    for par in ancestors:
        try: cmd=app.proc_cmd(par)
        except OSError: cmd=''
        if cmd=='/init' or cmd.startswith('/init '):
            init=par; break
    if not init: raise RuntimeError('ANDROID_INIT_NOT_FOUND')
    app.require_root_process(bridge,'/system/bin/app_process64')
    app.require_root_process(init,'/system/bin/init')
    owner=app.ppid(init)
    app.require_root_process(owner,'/usr/bin/unshare')
    # This exact observed intermediary is qualified by baseline02; its argv is
    # private identity data, not a new command or executable authority.
    current_owner=verify_current_owner(app,baseline,epoch,status,init)
    expected=' '.join(current_owner['cmdline'])
    if app.proc_cmd(owner)!=expected: raise RuntimeError('UNEXPECTED_CELL_OWNER')
    # The verified Ubuntu compatibility launcher is the daemon's recorded
    # host_pid; its immediate child is the real util-linux unshare process.
    # Also accept a directly recorded real unshare process on an upstream host.
    if owner!=host and app.ppid(owner)!=host: raise RuntimeError('CELL_OWNER_NOT_STATUS_CHILD')
    if owner!=host:
        expected_host='/usr/bin/python3 -I /usr/local/libexec/droidloom-compat/unshare --mount --pid --mount-proc --ipc --uts --fork --kill-child=TERM --forward-signals --propagation=private /usr/bin/droidloom-supervisor development-enter --spec /etc/droidloom/cell.json'
        if app.proc_cmd(host)!=expected_host: raise RuntimeError('UNEXPECTED_CELL_LAUNCHER')
        if not app.re.fullmatch(r'/usr/bin/python3(?:\.\d+)?',app.os.readlink(f'/proc/{host}/exe')):
            raise RuntimeError('UNEXPECTED_CELL_LAUNCHER_EXECUTABLE')
    for ns in ('mnt','pid','uts','ipc'):
        if app.os.readlink(f'/proc/{bridge}/ns/{ns}')!=app.os.readlink(f'/proc/{init}/ns/{ns}'):
            raise RuntimeError('INPUT_BRIDGE_NAMESPACE_MISMATCH')
    if app.os.readlink(f'/proc/{init}/ns/mnt')==app.os.readlink('/proc/self/ns/mnt'):
        raise RuntimeError('ANDROID_CELL_IS_HOST_MOUNT_NAMESPACE')
    raw=open(f'/proc/{bridge}/environ','rb').read().split(b'\0')
    env={}
    for item in raw:
        if b'=' not in item: continue
        k,v=item.split(b'=',1)
        k=k.decode('utf-8','strict')
        if k in app.ENV_KEYS:
            value=v.decode('utf-8','strict')
            if len(value)>65536 or '\x00' in value: raise RuntimeError('INVALID_ANDROID_ENV')
            env[k]=value
    required={'PATH','BOOTCLASSPATH','DEX2OATBOOTCLASSPATH','ANDROID_ROOT','ANDROID_DATA','ANDROID_ART_ROOT'}
    if not required.issubset(env): raise RuntimeError('INCOMPLETE_ANDROID_ENV')
    verify_current_owner(app,baseline,epoch,status,init)
    guard()
    return init,env,status

