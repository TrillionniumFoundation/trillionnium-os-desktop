"""Focused checks for the fixed normal Netplan selection and path labels."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import derive_native_netplan_policy as netplan

HERE = Path(__file__).parent


class NetplanSelectionTests(unittest.TestCase):
    def changed(self, mutate):
        source = json.loads((HERE / "native-netplan-source.json").read_text())
        mutate(source)
        original = Path.read_text
        def read(path, *args, **kwargs):
            if path.name == "native-netplan-source.json":
                return json.dumps(source)
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", read):
            with self.assertRaises(ValueError):
                netplan.contract(HERE)

    def test_current_exact_public_selection_is_admitted_without_runtime_claim(self):
        value = netplan.contract(HERE)
        self.assertEqual(len(value["elf_paths"]), 18)
        self.assertEqual(len(value["files"]), 26)
        self.assertFalse(value["runtime_qualified"])
        self.assertFalse(value["other_yaml_profiles_qualified"])

    def test_unselected_dependency_or_missing_shared_group_member_is_rejected(self):
        self.changed(lambda v: v["elf_paths"].__setitem__(0, "/usr/bin/other"))
        self.changed(lambda v: v["shared_library_paths"].pop())
        self.changed(lambda v: v["files"].pop())

    def test_another_yaml_profile_and_changed_normal_unit_are_rejected(self):
        self.changed(lambda v: v["directories"][1]["names"].append("private.yaml"))
        self.changed(lambda v: v["unit_argv"].append("--root-dir=/other"))
        self.changed(lambda v: next(r for r in v["files"] if r["path"] == netplan.YAML_PATH)
                     .update(sha256="0" * 64))

    def test_source_alias_or_normal_metadata_cannot_change(self):
        self.changed(lambda v: v["aliases"][1].update(source="device"))
        self.changed(lambda v: v["files"][0].update(nlink=2))
        self.changed(lambda v: v["files"][0].update(uid=1000))

    def test_real_file_context_matcher_has_fixed_entry_and_negative_paths(self):
        with tempfile.TemporaryDirectory() as work:
            proof = netplan.verify_file_contexts(HERE, Path(work))
        self.assertGreaterEqual(proof["selected_and_negative_cases"], 90)

    def test_fixed_transition_roster_has_no_child_process_or_arbitrary_parent(self):
        transitions = netplan.fixed_transitions()
        self.assertEqual(len(transitions), 14)
        self.assertEqual(sum(" process " in row for row in transitions), 1)
        self.assertIn('(typetransition p4_linux_netplan_t p4_linux_network_manager_run_t dir '
                      'p4_linux_netplan_unselected_dir_t)', transitions)


class PrivateNetplanSelectionTests(unittest.TestCase):
    def test_private_selection_keeps_seven_hashes_without_runtime_claim(self):
        value = netplan.private_contract(HERE)
        self.assertEqual(len(value["profiles"]), 7)
        self.assertTrue(all(row["mode"] == 0o600 for row in value["profiles"]))
        self.assertFalse(value["runtime_qualified"])
        self.assertFalse(value["policy_enforcement_qualified"])

    def test_private_scope_rejects_missing_extra_unprotected_or_qualified_inputs(self):
        for mutate in (
                lambda v: v["profiles"].pop(),
                lambda v: v["profiles"].append(dict(v["profiles"][0])),
                lambda v: v["profiles"][0].update(mode=0o644),
                lambda v: v.update(runtime_qualified=True),
                lambda v: v.update(policy_enforcement_qualified=True)):
            value = json.loads((HERE / "native-netplan-private-source.json").read_text())
            mutate(value)
            original = Path.read_text
            def read(path, *args, **kwargs):
                if path.name == "native-netplan-private-source.json":
                    return json.dumps(value)
                return original(path, *args, **kwargs)
            with patch.object(Path, "read_text", read), self.assertRaises(ValueError):
                netplan.private_contract(HERE)


class NetplanRelabelProofTests(unittest.TestCase):
    @staticmethod
    def constraints():
        return [
            "(type sysfs)",
            "(type p4_linux_netplan_output_t)",
            "(validatetrans dir (or (neq t3 p4_linux_hardware_label_t) "
            "(or (eq t1 device) (eq t1 t2))))",
            "(validatetrans file (or (neq t3 p4_linux_uevent_label_t) (eq t2 sysfs)))",
        ]

    def test_relabel_predicate_identity_or_unmodeled_actor_is_rejected(self):
        class NoRelabel:
            def context_av(self, *args):
                return 0
        lines = self.constraints()
        self.assertEqual(len(netplan._relabel_constraints(NoRelabel(), lines)), len(netplan.ALIASES))
        for altered in (
                lines[-1].replace("(eq t2 sysfs)", "(eq t2 p4_linux_netplan_output_t)"),
                lines[-1].replace("(eq t2 sysfs)", "(eq t2 t1)"),
                lines[-1].replace("p4_linux_uevent_label_t", "unmodeled_actor")):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                netplan._relabel_constraints(NoRelabel(), lines[:-1] + [altered])
        with self.assertRaises(ValueError):
            netplan._relabel_constraints(NoRelabel(), lines[:-1])

    def test_relabel_reachability_in_another_category_is_rejected(self):
        class LastCategoryRelabel:
            def context_av(self, source, target, cls, names):
                return int(cls == "file" and
                           source.endswith(":" + netplan.LEVELS[-1]) and
                           target.endswith(":" + netplan.LEVELS[-1]))
        with self.assertRaises(ValueError):
            netplan._relabel_constraints(LastCategoryRelabel(), self.constraints())


class NetplanFixedActorProofTests(unittest.TestCase):
    def test_category_pairs_are_not_replaced_by_raw_or_union_permissions(self):
        class CategoryPolicy:
            def context_av(self, source, target, cls, names):
                self_source = source.split(":", 3)[3]
                object_type = target.split(":")[2]
                target_level = target.split(":", 3)[3]
                if object_type == netplan.PROFILE_DIR:
                    return 0
                return 7 if self_source == target_level else 1
        policy = CategoryPolicy()
        for actor in netplan.FIXED_OLD_ACTORS:
            for source in netplan.LEVELS:
                for target in netplan.LEVELS:
                    before, alias = netplan._actor_effective(policy, actor,
                        netplan.NM_RUN, netplan.PROFILE_DIR, "dir", source, target,
                        ["getattr", "create", "setattr"])
                    wanted = 7 if source == target else 1
                    self.assertEqual((before, alias), (wanted, wanted))

    def test_fixed_entry_preimage_is_required_without_other_extras(self):
        entry = {"getattr", "open", "read", "execute", "map"}
        for actor in ("init_t", netplan.EXECUTOR):
            self.assertEqual(netplan._actor_allowed_raw(
                actor, netplan.ENTRY, "file", {"getattr"}, entry), entry)
            for preimage in (entry - {"map"}, entry | {"write"}):
                with self.assertRaises(ValueError):
                    netplan._actor_allowed_raw(actor, netplan.ENTRY, "file", set(), preimage)
            with self.assertRaises(ValueError):
                netplan._actor_allowed_raw(actor, netplan.PROFILE_DIR, "dir",
                                          {"getattr"}, {"getattr", "create"})
        self.assertEqual(netplan._actor_extra(netplan.NM_ROLE, netplan.ENTRY, "file"), set())
        with self.assertRaises(ValueError):
            netplan._actor_extra("unselected_actor", netplan.ENTRY, "file")

    def test_raw_reader_preserves_attribute_and_self_rules_and_rejects_bounds(self):
        actor = "init_t"
        lines = [
            "(type " + actor + ")", "(type target)", "(type other)",
            "(typeattribute selected)", "(typeattributeset selected (" + actor + "))",
            "(roletype object_r " + actor + ")", "(roletype object_r target)",
            "(roletype object_r other)",
            "(allow selected target (dir (getattr create write)))",
            "(allow " + actor + " self (file (read)))",
        ]
        classes = {"dir": ["getattr", "create", "write"], "file": ["read", "write"]}
        raw = netplan._actor_raw(None, lines, classes, actor)
        actual = {(target, cls): names for target, cls, names in raw}
        self.assertEqual(actual[("target", "dir")], ["create", "getattr", "write"])
        self.assertEqual(actual[(actor, "file")], ["read"])
        self.assertEqual(actual[("other", "file")], [])
        with self.assertRaises(ValueError):
            netplan._actor_raw(None, lines + ["(typebounds init_t other)"], classes, actor)
        with self.assertRaises(ValueError):
            netplan._actor_raw(None, lines, classes, "unselected_actor")


if __name__ == "__main__":
    unittest.main()
