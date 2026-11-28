"""Adversarial tests for complete original-client alias preservation."""
import tempfile
import unittest
from pathlib import Path

import derive_observed_client_policy as v
from verify_working_qualification import _Index, _forms


def fixture(extra=""):
    names = (v.SOURCE, v.TARGET, v.BROKER, "reader", "other", "labeledfs",
             "p4_linux_user_session_t", "p4_linux_user_executor_t", "droidloom_public_control_client")
    rows = ["(type " + name + ")" for name in names]
    rows += ["(class file (getattr open read execute map write ioctl))",
             "(class dir (getattr search))", "(class filesystem (associate))",
             "(typeattribute clients)", "(typeattributeset clients (reader other))",
             "(typeattribute files)", "(typeattributeset files (" + v.SOURCE + " " + v.TARGET + "))"]
    forms = _forms("\n".join(rows) + "\n" + extra)
    return forms, _Index(forms)


class ObservedClientTests(unittest.TestCase):
    def test_only_new_broker_read_delta_and_old_roles_preserved(self):
        forms, index = fixture("(allow clients " + v.SOURCE + " (file (getattr open read execute map)))")
        before = v._matrix(forms, index, v.SOURCE)
        expected = v._expected(before)
        self.assertEqual(expected[("allow", v.BROKER, v.TARGET, "file")], v.READ)
        self.assertEqual(expected[("allow", "reader", v.TARGET, "file")],
                         frozenset(("getattr", "open", "read", "execute", "map")))
        self.assertNotIn(("allow", v.BROKER, v.SOURCE, "file"), before)
        for forbidden in ("execute", "map", "write", "ioctl"):
            bad = dict(expected)
            bad[("allow", v.BROKER, v.TARGET, "file")] = v.READ | {forbidden}
            with self.assertRaises(ValueError):
                v._require_subset(bad, expected)

    def test_old_broker_read_cannot_be_hidden_by_new_alias(self):
        forms, index = fixture("(allow " + v.BROKER + " " + v.SOURCE + " (file (read)))")
        with self.assertRaises(ValueError):
            v._expected(v._matrix(forms, index, v.SOURCE))

    def test_all_raw_audit_operations_and_full_ioctl_space_are_preserved(self):
        for tag in v.FLOW:
            permission = "(ioctl file ((range 0x0000 0xffff)))" if tag.endswith("x") else "(file (read ioctl))"
            forms, index = fixture("(" + tag + " clients " + v.SOURCE + " " + permission + ")")
            old = v._matrix(forms, index, v.SOURCE)
            expected = v._expected(old)
            text = "\n".join(v._emit(expected))
            linked, new_index = fixture(text)
            self.assertEqual(v._matrix(linked, new_index, v.TARGET), expected)
            self.assertEqual(len(expected[(tag, "reader", v.TARGET, "file")]),
                             65536 if tag.endswith("x") else 2)
            changed = dict(expected)
            changed[(tag, "other", v.TARGET, "dir")] = frozenset(("search",))
            with self.assertRaises(ValueError):
                v._require_subset(changed, expected)

    def test_object_outgoing_and_non_file_incoming_are_not_omitted(self):
        forms, index = fixture(
            "(allow " + v.SOURCE + " labeledfs (filesystem (associate)))\n"
            "(allow reader files (dir (getattr search)))")
        expected = v._expected(v._matrix(forms, index, v.SOURCE))
        self.assertEqual(expected[("allow", v.TARGET, "labeledfs", "filesystem")], {"associate"})
        self.assertEqual(expected[("allow", "reader", v.TARGET, "dir")], {"getattr", "search"})

    def test_conditionals_permissive_and_bounds_fail_closed(self):
        for extra in ("(booleanif option (true (allow reader " + v.SOURCE + " (file (read)))))",
                      "(tunableif option (true (allow reader " + v.SOURCE + " (file (read)))))",
                      "(optional extra_authority (allow reader " + v.SOURCE + " (file (read))))",
                      "(typepermissive " + v.TARGET + ")", "(typebounds other " + v.TARGET + ")"):
            forms, index = fixture(extra)
            with self.assertRaises(ValueError):
                v._matrix(forms, index, v.SOURCE)

    def test_an_extra_process_role_or_genfs_label_cannot_escape_fixed_paths(self):
        roles = "\n(roletype object_r " + v.SOURCE + ")\n(roletype object_r " + v.TARGET + ")"
        forms, index = fixture(roles)
        v._object_only(forms, index)
        for extra in ("(roletype system_r " + v.TARGET + ")",
                      "(genfscon proc /anything (u object_r " + v.TARGET + " ((s0) (s0))))"):
            forms, index = fixture(roles + "\n" + extra)
            with self.assertRaises(ValueError):
                v._object_only(forms, index)

    def test_constraints_require_both_source_and_target_predicates_equal(self):
        good = "(mlsconstrain (file (read)) (or (eq t2 files) (dom l1 l2)))"
        forms, index = fixture(good)
        self.assertEqual(len(v._constraints(forms, index)), 1)
        for variable in ("t1", "t2", "t3"):
            forms, index = fixture("(constrain (file (read)) (eq " + variable + " " + v.SOURCE + "))")
            with self.assertRaises(ValueError):
                v._constraints(forms, index)
        forms, index = fixture("(constrain (file (read)) (eq t1 t2))")
        with self.assertRaises(ValueError):
            v._constraints(forms, index)
        for tag in ("validatetrans", "mlsvalidatetrans"):
            forms, index = fixture("(" + tag + " file (or (eq t3 files) (eq l1 l2)))")
            self.assertEqual(len(v._constraints(forms, index)), 1)
            forms, index = fixture("(" + tag + " file (eq t2 " + v.SOURCE + "))")
            with self.assertRaises(ValueError):
                v._constraints(forms, index)
        forms, index = fixture("(validatetrans dir (eq t1 t2))")
        self.assertEqual(v._constraints(forms, index), ["(validatetrans dir (eq t1 t2))"])

    def test_automatic_entry_roster_and_unexpected_role_transition_are_visible(self):
        forms, index = fixture("\n".join(v.SOURCE_ENTRIES))
        self.assertEqual(v._entries(forms, index, v.SOURCE), v.SOURCE_ENTRIES)
        forms, index = fixture("\n".join(v.SOURCE_ENTRIES) + "\n(roletransition system_r " + v.SOURCE + " process r)")
        self.assertNotEqual(v._entries(forms, index, v.SOURCE), v.SOURCE_ENTRIES)

    def test_only_two_exact_regular_file_contexts_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            here = Path(tmp)
            for name in ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
                         "linux-initial-calibration-file_contexts", "linux-public-control.cil",
                         "linux-observed-client.cil", "derive_observed_client_policy.py"):
                (here / name).write_text("")
            path = here / "linux-service-file_contexts"
            path.write_text("\n".join(v.CONTEXTS) + "\n")
            v.contract(here)
            for bad in ("/usr/bin/.* -- u:object_r:" + v.TARGET + ":s0",
                        v.CONTEXTS[0] + "\n/usr/bin/third -- u:object_r:" + v.TARGET + ":s0",
                        "\n".join(v.CONTEXTS) + "\n/usr/bin/old -- u:object_r:" + v.SOURCE + ":s0"):
                path.write_text(bad + "\n")
                with self.assertRaises(ValueError):
                    v.contract(here)


if __name__ == "__main__":
    unittest.main()
