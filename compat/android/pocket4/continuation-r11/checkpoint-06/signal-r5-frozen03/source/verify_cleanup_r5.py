#!/usr/bin/env python3
"""Run actual R4/R5 cleanup functions on bounded, declared syscall seams."""
import argparse
import ast
from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).parent
parser = argparse.ArgumentParser()
parser.add_argument("--r4-source", required=True)
args = parser.parse_args()
R4 = Path(args.r4_source)
assert hashlib.sha256((R4/"source-manifest.json").read_bytes()).hexdigest() == \
    "b51efedefd1c458fae0cdf0fe1b353cf9c69db3429fa3c07bdc549d10dec0ed4"
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
C = module("owned_cleanup_r5_control", HERE/"cleanup_owned.py")
OLD = module("frozen_r4_cleanup_control", R4/"run.py")
ROWS = []
def record(name, detail):
    ROWS.append({"name":name,"passed":True,"detail":detail})
def must_fail(call):
    try: call()
    except Exception as error: return repr(error)
    raise AssertionError("expected rejection")

class Fixture:
    def __init__(self, root, roles=("bus","sway","presenter","daemon"), *, main_pid=21,
                 nested=False, leave_populated=False, save_failure=False, stop_failure=None):
        self.root=Path(root)
        self.cg=self.root/"cgroup";self.cg.mkdir()
        self.evidence=self.root/"evidence";self.evidence.mkdir()
        self.name="p4-signal-r5-fixture"
        self.nonce="e"*32
        self.rows=[]
        self.states={}
        self.calls=[]
        self.order=[]
        self.save_failure=save_failure
        self.leave_populated=leave_populated
        self.stop_failure=stop_failure
        for index,role in enumerate(roles):
            unit=self.name+"-"+role+".service"
            row={"role":role,"unit":unit,"description":self.name+" "+self.nonce+" "+role,
                 "invocation":format(index+1,"032x"),"group":"/system.slice/"+unit}
            self.rows.append(row)
            self.states[unit]={"LoadState":"loaded","ActiveState":"active","MainPID":str(main_pid),
                "InvocationID":row["invocation"],"Description":row["description"],"ControlGroup":row["group"]}
            self.make_group(self.cg/row["group"][1:],populated=1 if nested else 0,pids=1 if nested else 0)
            if nested:
                self.make_group(self.cg/row["group"][1:]/"child",populated=1,pids=1,procs="41\n")
        actor=Path("/proc/self/cgroup").read_text().strip().split("0::",1)[1]
        self.make_group(self.cg/actor[1:])
        before={"fixed":"declared-owned-control"}
        self.s={"NAME":self.name,"NONCE":self.nonce,"ROWS":self.rows,"INIT":None,
            "RESULT":{"main_resources_before":{"fixed":"resources"},"source_contract_before":{"fixed":"source"}},
            "P":{"main_before":before},"SOCK":self.root/"absent-control.sock",
            "props":self.props,"call":self.call,"save":self.save,
            "release_held_binding":self.release,"ctl":self.ctl,
            "main_snapshot":lambda:before,"main_resources":lambda:{"fixed":"resources"},
            "source_contract":lambda:{"fixed":"source"},"proc":self.forbidden,"atext":self.forbidden,
            "owned":self.owned,"Path":self.path}
    def forbidden(self,*a,**k):
        raise AssertionError("unexpected Android/process operation")
    def make_group(self,path,populated=0,pids=0,procs=""):
        path.mkdir(parents=True,exist_ok=True)
        files={"cgroup.events":"populated %d\nfrozen 0\n"%populated,"pids.current":str(pids)+"\n",
            "cgroup.procs":procs,"memory.events":"low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0\n",
            "memory.pressure":"some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n",
            "cpu.pressure":"some avg10=0.00 avg60=0.00 avg300=0.00 total=0\n",
            "memory.peak":"0\n","memory.max":"268435456\n","memory.swap.max":"0\n","cpu.max":"10000 100000\n"}
        for name,value in files.items():(path/name).write_text(value)
    def path(self,value):
        text=str(value)
        if text=="/sys/fs/cgroup" or text.startswith("/sys/fs/cgroup/"):
            return self.cg/text.removeprefix("/sys/fs/cgroup").lstrip("/")
        return Path(value)
    def props(self,unit):
        return dict(self.states.get(unit,{"LoadState":"not-found","MainPID":"0","ActiveState":"inactive"}))
    def owned(self,row):
        value=self.props(row["unit"])
        assert value.get("InvocationID")==row["invocation"] and value.get("Description")==row["description"]
        return value
    def call(self,argv,*a,**k):
        argv=list(map(str,argv));self.calls.append(argv)
        if argv[:2]==["/usr/bin/systemctl","show"]:
            return subprocess.CompletedProcess(argv,0,b"CPUUsageNSec=0\nMemoryPeak=0\n",b"")
        if argv[:2]==["/usr/bin/journalctl","-u"]:
            return subprocess.CompletedProcess(argv,0,b"declared owned journal\n",b"")
        if argv[:2]==["/usr/bin/systemctl","stop"]:
            unit=argv[2];self.order.append("stop:"+unit)
            if unit==self.stop_failure:raise subprocess.TimeoutExpired(argv,45)
            self.states[unit].update(MainPID="0",ActiveState="inactive")
            if not self.leave_populated:
                root=self.cg/self.states[unit]["ControlGroup"][1:]
                for directory in [root,*[p for p in root.rglob("*") if p.is_dir()]]:
                    (directory/"cgroup.events").write_text("populated 0\nfrozen 0\n")
                    (directory/"pids.current").write_text("0\n")
                    (directory/"cgroup.procs").write_text("")
            return subprocess.CompletedProcess(argv,0,b"",b"")
        raise AssertionError("unlisted transport call: "+repr(argv))
    def save(self,name,value):
        self.order.append("save:"+name)
        if self.save_failure and name=="resources-before-cleanup.json":
            raise OSError(28,"declared evidence ENOSPC")
        raw=value if isinstance(value,bytes) else json.dumps(value,sort_keys=True).encode()
        (self.evidence/name).write_bytes(raw)
    def release(self,failures):
        self.order.append("release")
    def ctl(self,*a):
        raise AssertionError("no private daemon exists in this host control")
    def run_r5(self):
        return C.OwnedCleanup(self.s,cgroup_root=self.cg,allow_regular_counter_fixture=True).run()
    def run_r4(self):
        prep=types.SimpleNamespace(read_json=lambda *a:{"fixture":True},CPU_INVENTORY_SHA="fixture",
            load_guard=lambda *a:{},main_snapshot=lambda *a:{"resources":{"fixed":"resources"}})
        config={"cpu_inventory":{"path":"/declared-not-read"}}
        prepared={key:str(self.root/key) for key in ("stage","runtime","user_runtime","evidence")}
        prepared.update(name=self.name,nonce=self.nonce,arm="declared-host-control")
        scope=OLD.original_runtime(prep,config,prepared,R4/"references/preparation-r1")
        scope.update(self.s)
        return scope["cleanup"]()
    def stops(self):
        return [argv[2] for argv in self.calls if argv[:2]==["/usr/bin/systemctl","stop"]]

with tempfile.TemporaryDirectory(prefix="r5-cleanup-controls-",dir=HERE.parent) as temporary:
    root=Path(temporary)
    def new(label,**kwargs):
        path=root/label;path.mkdir();return Fixture(path,**kwargs)
    old=new("r4-save-error",save_failure=True)
    error=must_fail(old.run_r4)
    assert "ENOSPC" in error and old.stops()==[] and all(v["ActiveState"]=="active" for v in old.states.values())
    record("r4-actual-cleanup-evidence-failure-skips-all-owned-stops",
           {"expected_negative":True,"error":error,"stops":[]})
    fixed=new("r5-save-error",save_failure=True)
    errors=fixed.run_r5()
    assert len(errors)==1 and "cleanup-evidence-write:resources-before-cleanup.json" in errors[0]
    assert fixed.stops()==[r["unit"] for r in reversed(fixed.rows)]
    assert fixed.order.index("release")<fixed.order.index("stop:"+fixed.rows[-1]["unit"])
    assert all(r["retired"] for r in fixed.s["RESULT"]["cleanup"]["retirements"])
    assert fixed.s["RESULT"]["first_cleanup_error"]==errors[0]
    record("r5-actual-cleanup-retirements-continue-after-resource-save-error",
           {"errors":errors,"all_four_retired":True,"release_before_stop":True,"whole_run_must_fail":True})

    old=new("r4-nested",main_pid=0,nested=True)
    errors=old.run_r4()
    assert errors==[] and old.stops()==[]
    assert all((old.cg/r["group"][1:]/"pids.current").read_text().strip()=="1" for r in old.rows)
    record("r4-actual-cleanup-mainpid-zero-root-empty-misses-populated-child",
           {"expected_negative":True,"reported_cleanup_errors":[],"owned_subtrees_still_populated":4})
    fixed=new("r5-nested",main_pid=0,nested=True)
    assert fixed.run_r5()==[]
    assert len(fixed.stops())==4
    reports=fixed.s["RESULT"]["cleanup"]["retirements"]
    assert all(r["before"]["events"]["populated"]==1 and r["before"]["pids_current"]==1
               and r["before"]["root_processes"]==[] and r["after"]["pids_current"]==0 and r["retired"] for r in reports)
    record("r5-actual-cleanup-stops-mainpid-zero-and-proves-hierarchical-empty",
           {"exact_stops":4,"root_empty_before":True,"descendant_populated_before":True,"hierarchical_zero_after":True})

    bad=new("post-stop-subtree-still-live",main_pid=0,nested=True,leave_populated=True)
    errors=bad.run_r5()
    assert len(bad.stops())==4 and len([e for e in errors if "remains populated" in e])==4
    assert all(not r["retired"] for r in bad.s["RESULT"]["cleanup"]["retirements"])
    record("successful-stop-ack-and-empty-root-do-not-hide-live-subtree",
           {"rejected_populated_subtrees":4,"errors":errors})

    # Reconcile the actual immutable unit_launch function after a declared
    # response-read failure. The systemd-run transport is an explicit seam.
    launched=new("launch-finally-props-failure",roles=())
    actual_props=launched.props
    phase={"created":False,"failed":False}
    def props_once(unit):
        if not phase["created"]:return {"LoadState":"not-found"}
        if not phase["failed"]:
            phase["failed"]=True
            raise OSError("declared first post-launch props read failure")
        return actual_props(unit)
    normal_call=launched.call
    def launch_call(argv,*a,**kw):
        if str(argv[0])=="/usr/bin/systemd-run":
            unit=launched.name+"-bus.service"
            description=launched.name+" "+launched.nonce+" bus"
            group="/system.slice/"+unit
            launched.states[unit]={"LoadState":"loaded","ActiveState":"active","MainPID":"0",
                "InvocationID":"a"*32,"Description":description,"ControlGroup":group}
            launched.make_group(launched.cg/group[1:],populated=1,pids=1)
            phase["created"]=True
            return subprocess.CompletedProcess(argv,0,b"",b"")
        return normal_call(argv,*a,**kw)
    launch_scope={"NAME":launched.name,"NONCE":launched.nonce,"ROWS":launched.rows,"ENV":{},"R":root,
        "props":props_once,"call":launch_call,"event":lambda *a,**k:None}
    v5=(R4/"references/preparation-r1/v5_original.py").read_text()
    node=next(n for n in ast.parse(v5).body if isinstance(n,ast.FunctionDef) and n.name=="unit_launch")
    exec(compile(ast.Module(body=[node],type_ignores=[]),"<exact-v5-unit-launch>","exec"),launch_scope)
    error=must_fail(lambda:launch_scope["unit_launch"]("bus",["/declared-not-executed"],2,"32M"))
    assert phase["failed"] and "invocation" not in launched.rows[0]
    launched.s["props"]=props_once
    assert launched.run_r5()==[]
    assert launched.rows[0]["reconciled_after_launch_error"] and len(launched.stops())==1
    record("actual-unit-launch-props-failure-reconciles-one-exact-generation",
           {"initial_error":error,"exact_stops":1,"old_r4_outer_reconciler_existed":True})

    for field,bad_value in (("InvocationID","f"*32),("Description","other-owner"),
                            ("ControlGroup","/system.slice/droidloomd.service")):
        fixture=new("mismatch-"+field)
        protected=fixture.rows[-1]
        fixture.states[protected["unit"]][field]=bad_value
        errors=fixture.run_r5()
        assert errors and protected["unit"] not in fixture.stops() and len(fixture.stops())==3
        record("mismatched-"+field+"-never-stopped-other-owned-units-continue",
               {"protected_unit_not_stopped":True,"other_units_stopped":3})
    fixture=new("one-stop-timeout")
    fixture.stop_failure=fixture.rows[-1]["unit"]
    errors=fixture.run_r5()
    assert errors and len(fixture.stops())==4
    assert all(v["ActiveState"]=="inactive" for k,v in fixture.states.items() if k!=fixture.stop_failure)
    record("one-unit-stop-timeout-does-not-prevent-other-retirements",
           {"stop_attempts":4,"automatic_retry":False,"errors":errors})

    # Real descriptor/path substitution tests use only regular-file counter fixtures.
    fixture=new("held-path-rename",roles=("bus",),nested=True)
    group=fixture.rows[0]["group"]
    proof=C.CgroupProof(fixture.cg,group,allow_regular_counter_fixture=True)
    path=fixture.cg/group[1:]
    renamed=path.with_name(path.name+"-renamed")
    path.rename(renamed)
    sample=proof.sample()
    assert sample["path_present"] is False and not sample["absent"] and not C.CgroupProof.empty(sample)
    record("held-original-populated-directory-is-not-lost-after-path-rename",
           {"held_identity":sample["held_identity"],"populated":sample["events"]["populated"]})
    fixture.make_group(path)
    error=must_fail(proof.sample)
    assert "replaced" in error
    proof.close()
    record("replacement-empty-directory-cannot-prove-old-populated-domain-empty",{"error":error})

    fixture=new("unbound-unknown",roles=("bus",))
    fixture.rows[0].pop("invocation")
    fixture.rows[0].pop("group")
    fixture.states.clear()
    # Simulate no observed group without claiming an unknown launch completed.
    group=fixture.cg/("system.slice/"+fixture.rows[0]["unit"])
    for child in group.iterdir():child.unlink()
    group.rmdir()
    errors=fixture.run_r5()
    assert errors and fixture.stops()==[] and not fixture.s["RESULT"]["cleanup"]["retirements"][0]["retired"]
    record("never-observed-launch-generation-remains-failed-even-if-currently-absent",
           {"stops":0,"retirement_claim":False,"errors":errors})


    fixture=new("counter-read-failure-still-retires",roles=("bus",),nested=True)
    (fixture.cg/fixture.rows[0]["group"][1:]/"pids.current").unlink()
    errors=fixture.run_r5()
    assert errors and len(fixture.stops())==1 and fixture.s["RESULT"]["cleanup"]["retirements"][0]["retired"]
    record("counter-observation-error-does-not-block-exact-manager-retirement",
           {"exact_stops":1,"original_observation_error_preserved":True,"whole_run_must_fail":True})

    fixture=new("ordinary-fs-not-a-cgroup-proof",roles=("bus",))
    before_fds=set(os.listdir("/proc/self/fd"))
    error=must_fail(lambda:C.CgroupProof(fixture.cg,fixture.rows[0]["group"]))
    assert "not cgroup v2" in error and set(os.listdir("/proc/self/fd"))==before_fds
    record("production-proof-rejects-ordinary-filesystem-and-closes-constructor-fds",
           {"error":error,"fd_table_unchanged":True})

report={"schema":1,"state":"ACTUAL_CLEANUP_FUNCTION_CONTROLS_PASS","passed":len(ROWS),"controls":ROWS,
    "actual_cleanup_implementations_executed":["frozen R4 loader cleanup","R5 OwnedCleanup.run"],
    "declared_seams":["systemctl/props/journal transport","regular-file cgroup counter fixtures","fixed Main/source contract values","release callback"],
    "real_mechanisms":["filesystem descriptors","path rename/replacement","exact original v5 unit_launch function"],
    "real_systemd_units_started":0,"Android_operations":0,"Main_actions":0,
    "private_canary_run":"NOT_RUN","production_ready":False,
    "source_pins":{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                   for name in ("cleanup_owned.py","run.py","verify_cleanup_r5.py")}}
print(json.dumps(report,sort_keys=True,indent=2))
