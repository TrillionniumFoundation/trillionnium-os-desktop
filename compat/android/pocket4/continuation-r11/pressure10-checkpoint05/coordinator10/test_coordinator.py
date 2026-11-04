"""Ordinary pure/owned-file coordinator controls; no unit or pressure action."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

def load(name):
    spec = importlib.util.spec_from_file_location("coordinator_"+name, Path(__file__).with_name(name+".py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
prepare, once = load("prepare"), load("once")

def relief_qualified():
    return {"qualification_status":"pass","stale_actual_queue_zero_kill_verified":True,
            "stale_actual_critical_queue_zero_kill_verified":True,
            "stale_after_allocator_relief_zero_kill_verified":True,
            "critical_event_observed_in_phase":True,
            "stale_test_scope":"relieved-domain-aged-critical-queue",
            "native_stale_drop_observed":False,"above_high_stale_zero_kill_verified":False}

class CoordinatorControls(unittest.TestCase):
    def test_actual_scope_contract_accepts_only_relief_claim(self):
        once.require_phase_qualification("stale",0,relief_qualified())
        flags=once.phase_result_flags("stale",True,0)
        self.assertTrue(flags["stale_relief_critical_qualified"])
        for name in ("stale_qualified","stale_critical_qualified","native_stale_drop_observed",
                     "above_high_stale_zero_kill_verified","pressure_qualified","partial_medium_only"):
            self.assertIs(flags[name],False,name)

    def test_legacy_stale_booleans_cannot_authorize_new_scope(self):
        old=relief_qualified()
        for name in ("stale_after_allocator_relief_zero_kill_verified","stale_test_scope",
                     "native_stale_drop_observed","above_high_stale_zero_kill_verified"):
            old.pop(name)
        with self.assertRaises(RuntimeError):
            once.require_phase_qualification("stale",0,old)

    def test_inflated_or_missing_claims_fail_closed(self):
        for key,value in (("stale_after_allocator_relief_zero_kill_verified",False),
                          ("critical_event_observed_in_phase",1),
                          ("stale_actual_critical_queue_zero_kill_verified",False),
                          ("stale_test_scope","above-high-independent-native-expiry"),
                          ("native_stale_drop_observed",True),
                          ("above_high_stale_zero_kill_verified",True)):
            with self.subTest(key=key):
                q=relief_qualified();q[key]=value
                with self.assertRaises(RuntimeError):once.require_phase_qualification("stale",0,q)
        with self.assertRaises(RuntimeError):once.require_phase_qualification("stale",2,relief_qualified())

    def test_failed_or_unknown_phase_never_acquires_any_qualification(self):
        for phase in ("pressure","stale",None,"invalid"):
            f=once.phase_result_flags(phase,False,None)
            for key,value in f.items():
                if key.endswith("_qualified") or key.endswith("_verified") or key=="native_stale_drop_observed":
                    self.assertIs(value,False,key)
        with self.assertRaises(RuntimeError):once.phase_result_flags(None,True,0)
        with self.assertRaises(RuntimeError):once.phase_result_flags("stale",True,2)
        with self.assertRaises(RuntimeError):once.phase_result_flags("stale",True,False)

    def test_positive_critical_and_medium_only_remain_distinct(self):
        once.require_phase_qualification("pressure",0,{"qualification_status":"pass"})
        once.require_phase_qualification("pressure",2,{"qualification_status":"partial_medium_only"})
        full=once.phase_result_flags("pressure",True,0);partial=once.phase_result_flags("pressure",True,2)
        self.assertTrue(full["pressure_qualified"]);self.assertFalse(full["partial_medium_only"])
        self.assertFalse(partial["pressure_qualified"]);self.assertTrue(partial["partial_medium_only"])
        self.assertFalse(full["stale_relief_critical_qualified"])
        self.assertFalse(partial["stale_relief_critical_qualified"])

    def test_predecessor_requires_external_pin_exact_revision_and_critical(self):
        for module in (prepare,once):
            original={"phase":"pressure","unit":module.PROFILES["pressure"][0]+".service",
                      "source_manifest_sha256":module.SOURCE,"matching_build_receipt_sha256":module.BUILD,
                      "ok":True,"external_unit_binding_verified":True,"exact_owned_cleanup_verified":True,
                      "main_epoch_unchanged_after_cleanup":True,"outcome_unknown":False,"forced_teardown":False,
                      "pressure_qualified":True,"partial_medium_only":False,
                      "qualification":{"critical_event_observed_in_phase":True,"fresh_critical_event_correlated_with_cached_exit":True}}
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/"owned-result.json"
                def check(value,accept):
                    raw=(json.dumps(value)+"\n").encode();path.write_bytes(raw)
                    pin=hashlib.sha256(raw).hexdigest()
                    with mock.patch.object(module,"P",lambda unused:path):
                        if accept:self.assertFalse(module.predecessor(pin)["partial_medium_only"])
                        else:
                            with self.assertRaises(RuntimeError):module.predecessor(pin)
                check(original,True)
                for key,value in (("pressure_qualified",False),("partial_medium_only",True),
                                  ("source_manifest_sha256","0"*64),("unit","another-owned.service"),
                                  ("exact_owned_cleanup_verified",False),("outcome_unknown",True)):
                    bad=copy.deepcopy(original);bad[key]=value;check(bad,False)
                bad=copy.deepcopy(original);bad["qualification"]["critical_event_observed_in_phase"]=False;check(bad,False)
                path.write_text("{}\n")
                with mock.patch.object(module,"P",lambda unused:path),self.assertRaises(RuntimeError):
                    module.predecessor("f"*64)

    def binding(self):
        unit="p4-lmkd-relay-pressure-r11-04.service";invocation="a"*32
        identity={"unit":unit,"driver_pid":42,"cgroup_device":30,"cgroup_inode":77}
        status={"ExecMainPID":"42","InvocationID":invocation,"ExecMainStartTimestampMonotonic":"1000",
                "ExecMainExitTimestampMonotonic":"5000","MemoryPeak":"10000000","MemorySwapPeak":"0"}
        first={"cgroup_device":30,"cgroup_inode":77,"invocation_id":invocation,"observed_monotonic_ns":2000000}
        outer={"observed_monotonic_ns":4000000,"memory_peak":9000000}
        q={"outer_identity_for_external_unit_binding":identity}
        return status,first,outer,q,unit,invocation

    def test_retained_outer_identity_cannot_bind_another_driver_or_invocation(self):
        args=self.binding();self.assertEqual(once.bind_terminal(*args),args[3]["outer_identity_for_external_unit_binding"])
        for index,key,value in ((0,"ExecMainPID","43"),(0,"InvocationID","b"*32),
                                (1,"cgroup_inode",78),(1,"cgroup_device",31),
                                (1,"invocation_id","b"*32)):
            changed=copy.deepcopy(args);changed[index][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):once.bind_terminal(*changed)

    def test_retained_outer_times_peaks_and_swap_remain_bounded(self):
        for index,key,value in ((0,"ExecMainStartTimestampMonotonic","3000"),
                                (0,"ExecMainExitTimestampMonotonic","3000"),
                                (0,"MemoryPeak",str(once.HARD)),(0,"MemoryPeak","8999999"),
                                (0,"MemorySwapPeak","1"),(2,"observed_monotonic_ns",999999)):
            changed=copy.deepcopy(self.binding());changed[index][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):once.bind_terminal(*changed)

if __name__=="__main__":unittest.main(verbosity=2)
