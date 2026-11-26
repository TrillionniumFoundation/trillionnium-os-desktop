"""Focused declaration-boundary tests for the existing policy library."""
import copy
import unittest
import tempfile
from pathlib import Path

from derive_preserved_alias_policy import (
    _validate_inputs, _mcs_transform_guards, _preserved_xperm_rules)
from derive_shared_payload_cgroup_policy import original_xperms


class PreservedAliasInputs(unittest.TestCase):
    def setUp(self):
        self.lines = {
            "(roletype system_r old_a)", "(roletype r old_b)",
            "(roletype system_r new_role)",
            "(roletype object_r original)", "(roletype object_r selected)",
            "(roletype object_r next_selected)",
        }
        self.classes = {"file": ["getattr", "open", "read", "execute", "map"]}
        self.aliases = [{"source": "original", "target": "selected", "class": "file"}]

    def check(self, *, aliases=None, isolated=None, extras=None, lines=None, preamble=()):
        return _validate_inputs(
            self.lines if lines is None else lines, self.classes,
            self.aliases if aliases is None else aliases, "test_preserved",
            {"new_role"} if isolated is None else isolated,
            {} if extras is None else extras, preamble)

    def test_extra_permissions_stay_on_one_concrete_actor(self):
        requested = {("old_a", "selected", "file"): {"read", "map"}}
        before = copy.deepcopy(requested)
        actors, extras = self.check(extras=requested)
        self.assertEqual(actors, [("r", "old_b"), ("system_r", "old_a")])
        self.assertEqual(extras, requested)
        self.assertNotIn(("old_b", "selected", "file"), extras)
        self.assertNotIn(("new_role", "selected", "file"), extras)
        self.assertEqual(requested, before)

    def test_isolated_role_cannot_receive_extra_permissions(self):
        with self.assertRaisesRegex(ValueError, "isolated"):
            self.check(extras={("new_role", "selected", "file"): {"read"}})

    def test_unmatched_extra_scope_or_permission_is_rejected(self):
        cases = [
            {("missing", "selected", "file"): {"read"}},
            {("old_a", "missing", "file"): {"read"}},
            {("old_a", "selected", "dir"): {"read"}},
            {("old_a", "selected", "file"): {"invented"}},
            {("old_a", "selected", "file"): set()},
            {("old_a", "selected", "file"): "read"},
        ]
        for extras in cases:
            with self.subTest(extras=extras), self.assertRaises(ValueError):
                self.check(extras=extras)

    def test_duplicate_alias_cannot_silently_change_the_source(self):
        with self.assertRaisesRegex(ValueError, "Repeated"):
            self.check(aliases=self.aliases * 2)

    def test_chained_alias_is_not_an_original_source(self):
        rows = self.aliases + [
            {"source": "selected", "target": "next_selected", "class": "file"}]
        with self.assertRaisesRegex(ValueError, "original"):
            self.check(aliases=rows)

    def test_absent_or_every_actor_isolation_is_rejected(self):
        for isolated in ({"absent"}, {"old_a", "old_b", "new_role"}):
            with self.subTest(isolated=isolated), self.assertRaises(ValueError):
                self.check(isolated=isolated)

    def test_existing_attribute_prefix_cannot_be_reused(self):
        with self.assertRaisesRegex(ValueError, "prefix already"):
            self.check(lines=self.lines | {"(typeattribute test_preserved_0_0)"})

    def test_preamble_cannot_inject_a_policy_form(self):
        for preamble in (("(allow old_a selected (file (execute)))",),
                         ("; comment\n(allow old_a selected (file (execute)))",)):
            with self.subTest(preamble=preamble), self.assertRaises(ValueError):
                self.check(preamble=preamble)


class McsTransformGuards(unittest.TestCase):
    def setUp(self):
        self.classes = {name: [] for name in ("file", "dir", "chr_file", "lnk_file", "blk_file")}
        self.selected = {"lnk_file", "blk_file"}

    def check(self, lines):
        return _mcs_transform_guards(lines, self.classes, self.selected)

    def test_typebounds_rejected_even_when_not_named_in_alias(self):
        with self.assertRaisesRegex(ValueError, "typebounds"):
            self.check(["(typebounds parent_actor unrelated_actor)"])

    def test_selected_relabel_constraints_rejected(self):
        for op in ("validatetrans", "mlsvalidatetrans"):
            for cls in self.selected:
                with self.subTest(op=op, cls=cls), self.assertRaisesRegex(
                        ValueError, "selected relabel constraints"):
                    self.check(["(" + op + " " + cls + " (eq t1 t2))"])

    def test_other_inode_classes_keep_existing_constraints(self):
        self.check([
            "(validatetrans chr_file (eq t1 t2))",
            "(mlsvalidatetrans chr_file (eq l1 l2))",
            "(validatetrans dir (eq t1 t2))",
            "(validatetrans file (neq t3 writer))",
        ])

    def test_noncanonical_or_unknown_constraints_are_rejected(self):
        for lines in (["(validatetrans", " lnk_file (eq t1 t2))"],
                      ["(validatetrans unknown_class (eq t1 t2))"]):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                self.check(lines)


class PreservedIoctlFilters(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.source = Path(self.work.name) / "source.cil"
        self.linked = Path(self.work.name) / "alias.cil"
        self.base = "\n".join([
            "(type actor_a)", "(type actor_b)", "(type isolated)",
            "(type original)", "(type selected)", "(type self_alias)",
            "(typeattribute actors)", "(typeattributeset actors (actor_a actor_b isolated))",
            "(typeattribute devices)", "(typeattributeset devices (original))",
            "(allowx actors devices (ioctl blk_file ((range 0x5450 0x5451))))",
            "(allowx actor_a original (ioctl blk_file (0x1268)))",
            "(allowx actor_b devices (ioctl blk_file ((not (0x0 (range 0x100 0xfffe))))))",
            "(allowx actors self (ioctl lnk_file (0x77)))",
        ]) + "\n"
        self.source.write_text(self.base)
        self.aliases = [
            {"source": "original", "target": "selected", "class": "blk_file"},
            {"source": "actor_a", "target": "self_alias", "class": "lnk_file"},
        ]
        self.actors = [("r", "actor_a"), ("r", "actor_b")]
        self.expected, self.rules = _preserved_xperm_rules(
            self.source, self.aliases, self.actors)
        self.linked.write_text(self.base + "\n".join(self.rules) + "\n")

    def test_attribute_and_direct_filters_preserve_all_65536_bits(self):
        actual = original_xperms([self.linked], ["actor_a", "actor_b"], "selected",
                                 class_names=("blk_file",))["blk_file"]
        wanted_a = (1 << 0x1268) | (1 << 0x5450) | (1 << 0x5451)
        wanted_b = ((1 << 0x100) - 2) | (1 << 0xffff) | (1 << 0x5450) | (1 << 0x5451)
        self.assertEqual(actual, {"actor_a": wanted_a, "actor_b": wanted_b})
        self.assertEqual(actual, self.expected["original"]["blk_file"])
        self.assertTrue(all(" actors " not in line and " devices " not in line
                            for line in self.rules))

    def test_excluded_actor_receives_no_alias_filter(self):
        actual = original_xperms([self.linked], ["isolated"], "selected",
                                 class_names=("blk_file",))
        self.assertEqual(actual["blk_file"]["isolated"], 0)
        self.assertTrue(all(" isolated " not in line for line in self.rules))

    def test_self_filter_matches_both_source_actor_and_original_target(self):
        actual = original_xperms([self.linked], ["actor_a", "actor_b"], "self_alias",
                                 class_names=("lnk_file",))["lnk_file"]
        self.assertEqual(actual, {"actor_a": 1 << 0x77, "actor_b": 0})
        self.assertEqual(actual, self.expected["actor_a"]["lnk_file"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
