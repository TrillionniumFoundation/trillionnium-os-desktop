"""Focused declaration-boundary tests for the existing policy library."""
import copy
import unittest

from derive_preserved_alias_policy import _validate_inputs


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
