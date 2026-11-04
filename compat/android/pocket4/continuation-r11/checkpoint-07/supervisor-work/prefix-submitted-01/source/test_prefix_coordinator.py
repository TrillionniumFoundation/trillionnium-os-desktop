"""Pure qualification and owned-tempdir controls; no systemd/netns action."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("prefix_coordinator", Path(__file__).with_name("prefix_coordinator.py"))
target = importlib.util.module_from_spec(spec); spec.loader.exec_module(target)
spec = importlib.util.spec_from_file_location("prefix_actor", Path(__file__).with_name("full_prefix_control.py"))
actor = importlib.util.module_from_spec(spec); spec.loader.exec_module(actor)

def fixture(mode="normal"):
    plan = {"nonce": "abcd" * 16, "mode": mode, "sources": {"actor": {"path": "/owned/actor.py", "sha256": "a"*64},
            "probe": {"path": "/owned/probe", "sha256": "b"*64}}, "tools": {p: "c"*64 for p in
            ("/usr/bin/ip", "/usr/bin/unshare", "/usr/bin/python3")}}
    value = target.actor_input(plan, "d"*32, [11, 22], [33, 44])
    n = target.names(plan)
    terminal = {"LoadState": "loaded", "Transient": "yes", "Description": n["description"], "ControlGroup": n["group"],
                "InvocationID": "d"*32, "ExecMainPID": "100", "MainPID": "0", "Result": "success", "ExecMainCode": "1",
                "ExecMainStatus": "0", "ExecMainStartTimestampMonotonic": "1000000", "ExecMainExitTimestampMonotonic": "4000000",
                "MemoryPeak": "30000000", "MemorySwapPeak": "0"}
    argv = ["/usr/bin/ip", "netns", "exec", n["namespace"], "/usr/bin/unshare", "--mount", "--pid", "--mount-proc",
            "--ipc", "--uts", "--fork", "--kill-child=TERM", "--propagation=private", "/proc/self/fd/201",
            "development-enter", "--spec", n["evidence"] + "/actor-input.json"]
    proof = {"normal_exit": True, "next_exec_no_fixed_FDs": True} if mode == "normal" else {
        "probe_control_held_open": True, "native_deadline_not_used": True, "elapsed_from_probe_start_ms": 400,
        "exact_owner_killed": True, "private_pid1_dead": True, "exact_controller_killed": True,
        "exact_owner_dead": True, "exact_private_pid1_dead": True}
    result = {"success": True, "scope": target.SCOPE, "mode": mode, "nonce": plan["nonce"], "Android_operations": 0,
        "actual_Rust_Owner_executed": False, "declared_prefix_standin": True,
        "outer_final": {"nonce": plan["nonce"], "actor_pid": 100, "unit": value["unit"],
            "sole_remaining_actor": True, "sampled_before_unit_exit": True,
            "counters": dict(target.LIMITS, **{"pids.current": "1", "cgroup.procs": "100", "memory.events": "max 0\noom 0\noom_kill 0",
                                            "memory.swap.current": "0", "memory.peak": "20000000"})},
        "actual_prefix": {"nonce": plan["nonce"], "scope": target.SCOPE,
            "inherited_owner_pidfd_matches_exact_child": True, "private_pid1": {"parent": 102, "nspid": [103, 1]},
            "owner": {"pid": 102, "parent": 101}, "controller_pid": 101,
            "namespace_identity": {"net": [33, 44]}, "prefix": argv, "probe_lifetime_ms": 15000}, "terminal": proof}
    return plan, value, terminal, result

class QualificationControls(unittest.TestCase):
    def test_three_correct_logical_records(self):
        for mode in ("normal", "owner-kill", "controller-loss"):
            with self.subTest(mode=mode):
                _, value, terminal, result = fixture(mode)
                self.assertTrue(target.qualify(result, value, terminal, 100)["full_prefix_contract_observed"])

    def rejected(self, change, mode="normal"):
        plan, value, terminal, result = fixture(mode)
        change(plan, value, terminal, result)
        with self.assertRaises((RuntimeError, KeyError, ValueError, TypeError)):
            target.qualify(result, value, terminal, 100)

    def test_wrong_invocation_rejected(self):
        self.rejected(lambda p,v,t,r: t.update(InvocationID="e"*32))

    def test_wrong_exec_main_pid_rejected(self):
        self.rejected(lambda p,v,t,r: t.update(ExecMainPID="101"))

    def test_claimed_success_with_nonzero_actual_exit_rejected(self):
        self.rejected(lambda p,v,t,r: t.update(ExecMainStatus="97"))

    def test_replaced_first_cgroup_identity_rejected(self):
        self.rejected(lambda p,v,t,r: r["outer_final"].update(unit=dict(v["unit"], cgroup_identity=[11,23])))

    def test_empty_root_with_unknown_descendant_rejected(self):
        self.rejected(lambda p,v,t,r: r["outer_final"]["counters"].update({"pids.current":"2"}))

    def test_wrong_root_process_rejected(self):
        self.rejected(lambda p,v,t,r: r["outer_final"]["counters"].update({"cgroup.procs":"101"}))

    def test_outer_oom_or_swap_rejected(self):
        for mutation in ({"memory.events":"max 1\noom 0\noom_kill 0"}, {"memory.swap.current":"1"}):
            with self.subTest(mutation=mutation):
                self.rejected(lambda p,v,t,r: r["outer_final"]["counters"].update(mutation))

    def test_terminal_memory_peak_boundary_rejected(self):
        self.rejected(lambda p,v,t,r: t.update(MemoryPeak=target.LIMITS["memory.max"]))

    def test_duplicate_counter_cannot_hide_an_oom(self):
        self.rejected(lambda p,v,t,r: r["outer_final"]["counters"].update({"memory.events":"max 1\nmax 0\noom 0\noom_kill 0"}))

    def test_exact_unit_lifetime_boundary_rejected(self):
        self.rejected(lambda p,v,t,r: t.update(ExecMainExitTimestampMonotonic="61000000"))

    def test_original_legacy_wrapper_argv_rejected(self):
        self.rejected(lambda p,v,t,r: r["actual_prefix"]["prefix"].__setitem__(4, "unshare"))

    def test_arbitrary_outside_owner_pidfd_is_not_sufficient(self):
        self.rejected(lambda p,v,t,r: r["actual_prefix"].update(inherited_owner_pidfd_matches_exact_child=False))

    def test_lost_control_endpoint_cannot_prove_parent_death(self):
        self.rejected(lambda p,v,t,r: r["terminal"].update(probe_control_held_open=False), "controller-loss")

    def test_exact_native_death_observation_boundary_rejected(self):
        self.rejected(lambda p,v,t,r: r["terminal"].update(elapsed_from_probe_start_ms=10000), "owner-kill")

    def test_actor_cleanup_error_cannot_be_overridden_by_success(self):
        self.rejected(lambda p,v,t,r: r.update(cleanup_error="original child not retired"))

    def test_compiled_owner_or_android_claim_is_rejected_for_standin(self):
        self.rejected(lambda p,v,t,r: r.update(actual_Rust_Owner_executed=True))
        self.rejected(lambda p,v,t,r: r.update(Android_operations=1))

    def test_changed_unit_never_licenses_a_stop(self):
        plan, _, current, _ = fixture()
        plan.update(sources={},tools={})
        value = target.Attempt(argparse.Namespace(plan_sha256="f"*64),plan,actor.__dict__)
        value.unit_attempted=True;value.invocation="d"*32
        current["Description"]="unrelated unit"
        with mock.patch.object(target,"props",return_value=current), mock.patch.object(target,"call") as call:
            self.assertFalse(value.cleanup()); self.assertEqual(call.call_count,0)
        self.assertFalse(value.result["exact_cleanup_complete"])

    def test_missing_group_name_requires_independent_retirement_proof(self):
        plan, _, current, _ = fixture()
        current["ControlGroup"]=""
        with self.assertRaises(RuntimeError):target.bind_unit(current,plan,"d"*32)
        target.bind_unit(current,plan,"d"*32,retired_group_proven=True)

class OwnedRecordControls(unittest.TestCase):
    def test_create_only_atomic_publish_preserves_first_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
            try:
                digest=target.atomic_json(fd,"receipt.json",{"nonce":"original"})
                old=(Path(root)/"receipt.json").read_bytes()
                self.assertEqual(digest,hashlib.sha256(old).hexdigest())
                with self.assertRaises(OSError):target.atomic_json(fd,"receipt.json",{"nonce":"replacement"})
                self.assertEqual((Path(root)/"receipt.json").read_bytes(),old)
                self.assertEqual(target.read_json_at(fd,"receipt.json")[0],{"nonce":"original"})
            finally:os.close(fd)

    def test_record_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
            try:
                target.atomic_json(fd,"receipt.json",{"owned":True})
                (Path(root)/"alias.json").symlink_to("receipt.json")
                with self.assertRaises(OSError):target.read_json_at(fd,"alias.json")
            finally:os.close(fd)

    def test_hierarchical_counter_prevents_empty_root_false_retirement(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"group";p.mkdir()
            (p/"cgroup.events").write_text("populated 1\nfrozen 0\n")
            (p/"pids.current").write_text("1\n");(p/"cgroup.procs").write_text("")
            fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);s=os.fstat(fd)
            try:
                with self.assertRaises(RuntimeError):target.empty_original_group(actor.__dict__,fd,p,[s.st_dev,s.st_ino])
            finally:os.close(fd)

    def test_renamed_regular_fixture_is_not_removed_cgroup_proof(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"group";p.mkdir()
            (p/"cgroup.events").write_text("populated 0\nfrozen 0\n")
            (p/"pids.current").write_text("0\n");(p/"cgroup.procs").write_text("")
            fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);s=os.fstat(fd)
            try:
                p.rename(Path(root)/"renamed")
                proof=target.empty_original_group(actor.__dict__,fd,p,[s.st_dev,s.st_ino])
                self.assertTrue(proof["empty"]);self.assertFalse(proof["removed"])
            finally:os.close(fd)

    def test_replaced_group_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"group";p.mkdir()
            fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);s=os.fstat(fd)
            try:
                p.rename(Path(root)/"original");p.mkdir()
                with self.assertRaises(RuntimeError):target.empty_original_group(actor.__dict__,fd,p,[s.st_dev,s.st_ino])
            finally:os.close(fd)

if __name__=="__main__":unittest.main(verbosity=2)
