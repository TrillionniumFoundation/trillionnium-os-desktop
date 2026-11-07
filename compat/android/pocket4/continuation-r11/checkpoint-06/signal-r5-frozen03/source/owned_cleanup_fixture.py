#!/usr/bin/env python3
"""Fixed, once-only R5 owned systemd fixture. Default mode only prints its plan."""
import argparse
import ast
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode=True
HERE=Path(__file__).parent
WORK=Path("/home/alex/work/pocket4-signal-runtime-r5-work-01")
EVIDENCE=WORK/"owned-unit-control-02"
CLAIM=WORK/"owned-unit-control-02.claim.json"
NAME="p4-signal-r5-unit-control-20261104-02"
NONCE="5c53c248004139cd14513e8d88023c18"
UNIT=NAME+"-bus.service"
DESCRIPTION=NAME+" "+NONCE+" bus"
GROUP="/system.slice/"+UNIT
ACTIVATION=Path("/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json")
ACTIVATION_SHA="7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615"
GUARD=Path("/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py")
GUARD_SHA="f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288"
EPOCH_SHA="48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f"
ENV={"PATH":"/usr/bin:/bin","LANG":"C","LC_ALL":"C","PYTHONDONTWRITEBYTECODE":"1"}
PLAN={"schema":1,"name":NAME,"nonce":NONCE,"unit":UNIT,"group":GROUP,
    "properties":{"Type":"oneshot","RemainAfterExit":"yes","KillMode":"control-group","Restart":"no",
        "CPUQuota":"5%","MemoryMax":"64M","MemorySwapMax":"0","TasksMax":"16",
        "TimeoutStartSec":"15","TimeoutStopSec":"5","OOMPolicy":"stop","UMask":"0077",
        "NoNewPrivileges":"yes","Nice":"10"},
    "worker":str(HERE/"owned_cleanup_fixture_child.py"),"worker_children":1,
    "child_only_moves_itself":"owned-sleeper","child_lifetime_max_seconds":45,
    "once_claim":str(CLAIM),"evidence":str(EVIDENCE),
    "readiness_required":["Main epoch 48cb unchanged","MainPID=0","ActiveState=active",
        "root cgroup.procs empty","cgroup.events populated=1","pids.current=1","exact child pidfd alive"],
    "faults":["first post-start generation observation deliberately withheld",
        "one ENOSPC exception at resources-before-cleanup save"],
    "required_effect":["actual R5 cleanup reconciles exact unit","exact systemctl stop once",
        "hierarchical cgroup empty/deactivated","original child pidfd signals exit","original child reaped"],
    "forbidden":["Android entry","UI","pressure","Main unit stop","controller/limit changes",
        "engine deployment","unknown-outcome replay"],
    "scope_limit":"Only this exact unit subtree and its one known child; no escaped-descendant claim",
    "default_mode":"PLAN_ONLY_NO_ACTIONS","production_ready":False}
def need(value,message):
    if not value:raise RuntimeError(message)
def pin(path):
    path=Path(path)
    with path.open("rb") as stream: digest=hashlib.file_digest(stream,"sha256").hexdigest()
    return {"bytes":path.stat().st_size,"sha256":digest}
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value);return value
def write_new(path,value):
    raw=value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True,indent=2)+"\n").encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
    with os.fdopen(fd,"wb") as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
def validate_plan():
    """Pure preflight through the actual production guard; creates nothing."""
    cleanup_source=HERE/"cleanup_owned.py"
    need(pin(cleanup_source)=={"bytes":23861,
        "sha256":"45661ea4b0c3d9de0708571cdab3521d6827bed1f2108abf6814493d812fdbd3"},
        "unreviewed production cleanup source")
    module=load("actual_r5_fixture_preflight",cleanup_source)
    row={"role":"bus","unit":UNIT,"description":DESCRIPTION}
    actual=module.OwnedCleanup({"NAME":NAME,"NONCE":NONCE}).planned(row)
    need(actual==GROUP,"actual planned control group differs")
    need(PLAN["name"]==NAME and PLAN["nonce"]==NONCE and PLAN["unit"]==UNIT
         and PLAN["group"]==GROUP and PLAN["once_claim"]==str(CLAIM)
         and PLAN["evidence"]==str(EVIDENCE),"fixed plan fields differ")
    # Parse constants without importing the worker's deliberately effectful entry.
    tree=ast.parse((HERE/"owned_cleanup_fixture_child.py").read_bytes())
    values={}
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            key=node.targets[0].id
            if key in ("NAME","NONCE"):
                need(key not in values and isinstance(node.value,ast.Constant)
                     and type(node.value.value) is str,"ambiguous worker identity constant")
                values[key]=node.value.value
    need(values=={"NAME":NAME,"NONCE":NONCE},"worker identity differs from preflighted plan")
    return {"state":"ACTUAL_PRODUCTION_PLANNED_PREFLIGHT_PASS",
            "nonce_hex_length":len(NONCE),"unit":UNIT,"group":actual,
            "cleanup_source":pin(cleanup_source),"worker_identity_constants_match":True,
            "claim_created":False,"services_started":0,"Android_operations":0}

def source_contract(expected):
    need(pin(HERE/"source-manifest.json")["sha256"]==expected,"fixture manifest pin differs")
    manifest=json.loads((HERE/"source-manifest.json").read_text())
    need(manifest["artifact"]=="isolated-signal-canary-runtime-r5","wrong fixture source")
    for name,row in manifest["files"].items():
        path=HERE/name;value=path.lstat()
        need(stat.S_ISREG(value.st_mode) and value.st_nlink==1 and pin(path)==row,"source changed: "+name)
    need(pin(ACTIVATION)["sha256"]==ACTIVATION_SHA and pin(GUARD)["sha256"]==GUARD_SHA,
         "Main fence source or activation changed")
    config=json.loads((HERE/"references/android-input-a03.json").read_text())
    launch=json.loads((HERE/"host-launch-inputs.json").read_text())
    known={**config["tools"],**launch["tools"]}
    required=("/usr/bin/python3","/usr/bin/systemd-run","/usr/bin/systemctl","/usr/bin/journalctl")
    for path in required:
        need(path in known and pin(path)["sha256"]==known[path],"host fixture tool pin differs: "+path)
    return {"manifest_sha256":expected,"activation_sha256":ACTIVATION_SHA,"guard_sha256":GUARD_SHA,
            "host_tools":{path:known[path] for path in required}}
def raw(command,timeout=20):
    return subprocess.run(list(map(str,command)),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,timeout=timeout,env=ENV,check=False)
def properties(unit):
    need(unit in (UNIT,"droidloomd.service"),"unlisted system unit observation")
    result=raw(["/usr/bin/systemctl","show",unit,"-p","LoadState","-p","ActiveState","-p","SubState",
        "-p","MainPID","-p","InvocationID","-p","ControlGroup","-p","Description","-p","ExecStart",
        "-p","CPUQuotaPerSecUSec","-p","MemoryMax","-p","MemorySwapMax","-p","TasksMax",
        "-p","KillMode","-p","Type","-p","RemainAfterExit"])
    value=dict(line.split("=",1) for line in result.stdout.decode().splitlines() if "=" in line)
    need(result.returncode==0 or value.get("LoadState")=="not-found","unit property observation failed")
    return value
def child_identity(pid):
    path=Path("/proc")/str(pid)
    before=(path/"stat").read_text().rsplit(")",1)[1].split()
    status=dict(line.split(":",1) for line in (path/"status").read_text().splitlines() if ":" in line)
    result={"pid":pid,"start_ticks":int(before[19]),"uids":[int(x) for x in status["Uid"].split()],
            "cgroup":(path/"cgroup").read_text().strip(),"state":before[0]}
    after=(path/"stat").read_text().rsplit(")",1)[1].split()
    need(before[19]==after[19] and after[0] not in ("X","Z"),"child identity not live/stable")
    return result

def execute(expected):
    plan_preflight=validate_plan()
    need(os.geteuid()==0 and sys.flags.optimize==0,"root/nonoptimized host fixture required")
    contract=source_contract(expected)
    activation=json.loads(ACTIVATION.read_text())
    guard=load("owned_unit_main_fence",GUARD)
    epoch=activation["framework_epoch"];need(epoch["sha256"]==EPOCH_SHA,"wrong Main generation")
    def main_snapshot():
        guard.require_unchanged(epoch)
        current=properties("droidloomd.service")
        baseline=activation["daemon_unit"]
        for key in ("ActiveState","MainPID","InvocationID","ControlGroup"):
            need(current[key]==baseline[key],"Main daemon generation changed")
        return {"framework_sha256":epoch["sha256"],"daemon":{k:current[k] for k in
                ("ActiveState","MainPID","InvocationID","ControlGroup")}}
    def main_resources():
        root=Path("/sys/fs/cgroup/system.slice/droidloomd.service")
        return {name:(root/name).read_text().strip() for name in
                ("memory.high","memory.max","memory.swap.max","cpu.max","pids.max")}
    main_before=main_snapshot();resources_before=main_resources()
    need(properties(UNIT).get("LoadState")=="not-found","fixed owned unit already exists")
    need(not Path("/sys/fs/cgroup"+GROUP).exists(),"fixed owned cgroup already exists")
    # The same fixed operation cannot be restarted with a new transport key.
    write_new(CLAIM,{"schema":1,"source":contract,"plan":PLAN,"started_unix":time.time()})
    EVIDENCE.mkdir(mode=0o700,exist_ok=False)
    module=load("actual_r5_owned_cleanup_fixture",HERE/"cleanup_owned.py")
    result={"schema":1,"state":"OWNED_FIXTURE_STARTED","plan":PLAN,"source":contract,
        "Android_operations":0,"Main_actions":0,"pressure_generated":False,
        "source_contract_before":contract,"main_resources_before":resources_before,"plan_preflight":plan_preflight,
        "production_ready":False}
    row={"role":"bus","unit":UNIT,"description":DESCRIPTION}
    transports=[];injected=False;stop_attempts=0;pidfd=-1;held=None;child=None;scope=None;cleanup=None
    def save(name,value):
        nonlocal injected
        if name=="resources-before-cleanup.json" and not injected:
            injected=True
            raise OSError(errno.ENOSPC,"owned fixture injected resource receipt write failure")
        write_new(EVIDENCE/name,value)
    def call(command,timeout=20,check=True):
        nonlocal stop_attempts
        command=list(map(str,command))
        is_stop=command==["/usr/bin/systemctl","stop",UNIT]
        allowed=(command[:3]==["/usr/bin/systemctl","show",UNIT] or is_stop or
                 (command[:3]==["/usr/bin/journalctl","-u",UNIT] and
                  "_SYSTEMD_INVOCATION_ID="+row.get("invocation","") in command))
        need(allowed,"fixture refuses an unlisted command")
        if is_stop:
            need(stop_attempts==0,"fixture does not retry stop")
            stop_attempts+=1
        response=raw(command,timeout)
        transports.append({"argv":command,"returncode":response.returncode,
            "stdout":response.stdout.decode("utf8","replace"),"stderr":response.stderr.decode("utf8","replace")})
        if check:need(response.returncode==0,"fixture transport failed")
        return response
    def release(errors):
        result["release_phase_reached"]=True
    scope={"NAME":NAME,"NONCE":NONCE,"ROWS":[row],"INIT":None,"RESULT":result,
        "P":{"main_before":main_before},"SOCK":EVIDENCE/"no-Android-daemon.sock",
        "props":properties,"call":call,"save":save,"release_held_binding":release,
        "main_snapshot":main_snapshot,"main_resources":main_resources,
        "source_contract":lambda:source_contract(expected)}
    cleanup=module.OwnedCleanup(scope)
    try:
        command=["/usr/bin/systemd-run","--unit="+UNIT,"--property=Description="+DESCRIPTION]
        command+=["--property="+key+"="+value for key,value in PLAN["properties"].items()]
        command+=["--","/usr/bin/python3","-I",str(HERE/"owned_cleanup_fixture_child.py")]
        started=raw(command,25)
        result["start_ack"]={"argv":command,"returncode":started.returncode,
            "stdout":started.stdout.decode("utf8","replace"),"stderr":started.stderr.decode("utf8","replace")}
        need(started.returncode==0,"owned unit start did not acknowledge success")
        # This deliberately withheld observation models the earlier launch
        # response read failure. cleanup.reconcile() must establish the actual
        # manager generation, not take an injected InvocationID from the test.
        result["launch_observation_fault"]="post-start props result deliberately withheld; row remains unbound"
        deadline=time.monotonic()+10
        while True:
            current=properties(UNIT)
            if current.get("MainPID")=="0" and current.get("ActiveState")=="active":break
            need(time.monotonic()<deadline,"oneshot parent did not exit into active/exited state")
            time.sleep(.05)
        need(current["Description"]==DESCRIPTION and current["ControlGroup"]==GROUP,
             "fixture unit scope differs")
        need(current.get("Type")=="oneshot" and current.get("RemainAfterExit")=="yes" and
             current.get("KillMode")=="control-group" and current.get("TasksMax")=="16" and
             current.get("MemoryMax")=="67108864" and current.get("MemorySwapMax")=="0" and
             current.get("CPUQuotaPerSecUSec")=="50ms","fixture fixed resource protocol differs")
        result["unit_before"]=current
        actual=json.loads((EVIDENCE/"child-identity.json").read_text())
        need(actual["nonce"]==NONCE and actual["unit"]==UNIT and actual["sleep_seconds_max"]==45,
             "child identity receipt differs")
        child=actual["pid"];pidfd=os.pidfd_open(child,0)
        observed=child_identity(child)
        need(observed["start_ticks"]==actual["start_ticks"] and observed["uids"]==[0]*4 and
             observed["cgroup"]=="0::"+GROUP+"/owned-sleeper","actual owned child differs")
        poll=select.poll();poll.register(pidfd,select.POLLIN|select.POLLHUP|select.POLLERR)
        need(not poll.poll(0),"child already exited before control")
        held=module.CgroupProof(Path("/sys/fs/cgroup"),GROUP)
        before=held.sample();result["cgroup_before"]=before
        need(before["root_processes"]==[] and before["events"]["populated"]==1 and
             before["pids_current"]==1,"fixture does not have the required empty root/live subtree")
        errors=cleanup.run()
        need(injected and len(errors)==1 and errors[0].startswith("cleanup-evidence-write:resources-before-cleanup.json"),
             "unexpected cleanup outcome or missing injected failure")
        need(stop_attempts==1 and row.get("reconciled_after_launch_error") and result.get("release_phase_reached"),
             "actual cleanup did not reconcile/release/stop once")
        need(all(item["retired"] for item in result["cleanup"]["retirements"]),
             "actual cleanup did not retire the unit")
        deadline=time.monotonic()+5
        while True:
            after=held.sample()
            if after["absent"]:break
            need(module.CgroupProof.empty(after),"post-stop subtree repopulated")
            need(time.monotonic()<deadline,"empty owned cgroup was not removed")
            time.sleep(.05)
        result["held_cgroup_after"]=after
        need(poll.poll(5000),"original child pidfd did not report exit")
        result["original_child_pidfd_exited"]=True
        deadline=time.monotonic()+5
        while True:
            try:remaining=Path("/proc")/str(child)/"stat";raw_stat=remaining.read_text()
            except (FileNotFoundError,ProcessLookupError):break
            start=int(raw_stat.rsplit(")",1)[1].split()[19])
            if start!=actual["start_ticks"]:break
            need(time.monotonic()<deadline,"original owned child has not been reaped")
            time.sleep(.05)
        result["original_child_reaped"]=True
        result["main_after"]=main_snapshot()
        need(result["main_after"]==main_before and main_resources()==resources_before,"Main fence changed")
        result["would_qualify_full_canary"]=not bool(errors)
        need(result["would_qualify_full_canary"] is False,"injected cleanup failure must keep canary failed")
        result["state"]="OWNED_SYSTEMD_RETIREMENT_FIXTURE_PASS"
    except BaseException as error:
        result.update(state="OWNED_SYSTEMD_RETIREMENT_FIXTURE_FAILED_NO_RETRY",
                      error=repr(error),traceback=traceback.format_exc())
    finally:
        # Cleanup runs once even if an earlier fixture precondition fails.
        # Any unknown manager generation stays failed; there is no blind kill.
        if cleanup is not None and not result.get("cleanup_started"):
            try:cleanup.run()
            except BaseException as error:result.setdefault("fixture_cleanup_errors",[]).append(repr(error))
        if held is not None:
            try:held.close()
            except BaseException as error:result.setdefault("fixture_cleanup_errors",[]).append(repr(error))
        if pidfd>=0:os.close(pidfd)
        result["stop_attempts"]=stop_attempts
        result["transports"]=transports
        try:
            result["unit_final"]=properties(UNIT)
            result["cgroup_path_absent"]=not Path("/sys/fs/cgroup"+GROUP).exists()
            result["main_after_finally"]=main_snapshot()
            need(result["main_after_finally"]==main_before,"Main changed at final fixture readback")
        except BaseException as error:
            result.setdefault("fixture_cleanup_errors",[]).append(repr(error))
        if result.get("fixture_cleanup_errors"):
            result["state"]="OWNED_SYSTEMD_RETIREMENT_FIXTURE_FAILED_NO_RETRY"
        result["finished_unix"]=time.time()
        try:write_new(EVIDENCE/"result.json",result)
        except BaseException as error:
            result["state"]="OWNED_SYSTEMD_RETIREMENT_FIXTURE_FAILED_NO_RETRY"
            result["result_write_error"]=repr(error)
        for path in EVIDENCE.iterdir():
            if path.is_file():path.chmod(0o444)
        EVIDENCE.chmod(0o555)
    print(json.dumps({key:result.get(key) for key in ("state","error","stop_attempts","cgroup_path_absent",
        "original_child_pidfd_exited","original_child_reaped","would_qualify_full_canary","fixture_cleanup_errors")},sort_keys=True))
    return 0 if result["state"]=="OWNED_SYSTEMD_RETIREMENT_FIXTURE_PASS" else 1

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-once",action="store_true")
    parser.add_argument("--source-manifest-sha256")
    options=parser.parse_args(argv)
    if not options.execute_once:
        validation=validate_plan()
        print(json.dumps({**PLAN,"preflight":validation},sort_keys=True,indent=2))
        return 0
    need(re.fullmatch(r"[0-9a-f]{64}",options.source_manifest_sha256 or ""),
         "explicit frozen source manifest pin required")
    return execute(options.source_manifest_sha256)

if __name__=="__main__":
    raise SystemExit(main())
