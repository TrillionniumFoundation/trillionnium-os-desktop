"""Negative controls for the independent fixed state authority model."""
from pathlib import Path
import unittest
from derive_native_uevent_policy import Membership
import verify_fixture_state as v


class FixedStateBoundaryTests(unittest.TestCase):
    def membership(self, extra="", *, missing=()):
        groups = ("domain", "coredomain", "appdomain", "netdomain", "mlstrustedsubject",
                  "mlstrustedobject", "file_type")
        original = "\n".join(["(type rootfs)", "(type tmpfs)",
                              *("(typeattribute " + x + ")" for x in groups)])
        final = original + "\n" + "\n".join([
            *("(type " + x + ")" for x in v.NEW),
            "(typeattribute p4_all_board_owned)",
            "(typeattributeset p4_all_board_owned (" + " ".join(v.NEW) + "))",
            *("(typeattributeset " + x + " (" + v.QUERY + "))"
              for x in ("domain", "coredomain") if x not in missing),
            "(typeattributeset file_type (" + v.TEMP + "))", extra,
        ])
        return original, Membership(final)

    def raw(self, rule):
        types = v.NEW | {"kernel", "tmpfs", "untrusted_app_32", "untrusted_app",
                         "outsider", "app_data_file", "appdomain_tmpfs", "system_server"}
        text = "\n".join([*("(type " + x + ")" for x in types), rule])
        classes = {"file": ["getattr", "open", "read", "write", "map", "execute", "ioctl"],
                   "binder": ["call", "transfer", "impersonate", "set_context_mgr"],
                   "fd": ["use"], "process": ["transition", "dyntransition"]}
        return v._raw(text, Membership(text), classes)

    def test_original_domain_and_core_membership_is_required_without_trust(self):
        old, actual = self.membership()
        v._expected_membership(old, actual)
        for name in ("domain", "coredomain"):
            old, actual = self.membership(missing=(name,))
            with self.assertRaises(ValueError):
                v._expected_membership(old, actual)
        for name in ("appdomain", "netdomain", "mlstrustedsubject", "mlstrustedobject"):
            for subject in v.NEW:
                old, actual = self.membership("(typeattributeset " + name + " (" + subject + "))")
                with self.assertRaises(ValueError):
                    v._expected_membership(old, actual)

    def test_tmpfs_cannot_become_an_android_process(self):
        for name in ("domain", "coredomain"):
            old, actual = self.membership("(typeattributeset " + name + " (" + v.TEMP + "))")
            with self.assertRaises(ValueError):
                v._expected_membership(old, actual)

    def test_unrelated_board_actor_membership_is_rejected(self):
        for name in ("p4_linux_procs", "p4_handle_owner", "p4_working_actors",
                     "p4_closed_runtime_queries", "p4_native_ui_queries", "p4_fixed_metadata_tasks"):
            old, actual = self.membership("(typeattribute " + name + ")\n"
                "(typeattributeset " + name + " (" + v.QUERY + "))")
            with self.assertRaises(ValueError):
                v._expected_membership(old, actual)

    def test_other_provider_domain_is_not_learned_from_candidate(self):
        expected = self.raw(f"(allow {v.QUERY} untrusted_app_32 (binder (call transfer)))")
        wrong = self.raw(f"(allow {v.QUERY} untrusted_app (binder (call transfer)))")
        with self.assertRaises(ValueError):
            v._compare(wrong, expected, "fixed peer")

    def test_descriptor_and_cursorwindow_authority_is_rejected(self):
        for rule in (f"(allow {v.QUERY} untrusted_app_32 (fd (use)))",
                     f"(allow {v.QUERY} appdomain_tmpfs (file (getattr read map)))",
                     f"(allow {v.QUERY} app_data_file (file (getattr open read)))"):
            with self.assertRaises(ValueError):
                v._compare(self.raw(rule), {}, "provider body")

    def test_incoming_grants_cannot_hide_behind_outgoing_closure(self):
        incoming = self.raw(f"(allow outsider {v.QUERY} (fd (use)))")
        outgoing = self.raw(f"(allow {v.QUERY} outsider (fd (use)))")
        self.assertNotEqual(incoming, outgoing)
        for table in (incoming, outgoing):
            with self.assertRaises(ValueError):
                v._compare(table, {}, "complete direction")

    def test_audit_and_extended_rules_are_measured(self):
        for tag in ("auditallow", "dontaudit"):
            with self.assertRaises(ValueError):
                v._compare(self.raw(f"({tag} {v.QUERY} app_data_file (file (read)))"), {}, "audit")
        base = self.raw(f"(allowx {v.QUERY} tmpfs (ioctl file (0x1234)))")
        extra = self.raw(f"(allowx {v.QUERY} tmpfs (ioctl file ((range 0x1234 0x1235))))")
        with self.assertRaises(ValueError):
            v._compare(extra, base, "extended")

    def test_only_owned_anonymous_transition_outputs_are_expected(self):
        text = "\n".join([*("(type " + x + ")" for x in v.NEW | {"kernel", "tmpfs"}),
            f"(typetransition kernel tmpfs process {v.QUERY})"])
        rows = v._transition_rows(text, Membership(text))
        expected = {("typetransition", v.QUERY, "tmpfs", v.canonical([kind, v.TEMP]))
                    for kind in ("file", "memfd_file")}
        self.assertTrue(rows - expected)

    def test_literal_board_table_and_source_agree_before_android_inheritance(self):
        expected = v._explicit_board()
        types = v.NEW | {x for key in expected for x in key[1:3]}
        groups = "(typeattribute p4_query_original_dirs)\n(typeattributeset p4_query_original_dirs (" + " ".join(v.ORIGINAL_DIRS) + "))"
        text = "\n".join([*("(type " + x + ")" for x in types), groups,
                          (Path(__file__).parent / "linux-fixture-state.cil").read_text()])
        classes = {}
        for (_, _, _, cls, _), rights in expected.items():
            classes.setdefault(cls, set()).update(rights)
        actual = v._raw(text, Membership(text), classes)
        v._compare(actual, expected, "independent board table")
        wrong = {k: set(rights) for k, rights in actual.items()}
        wrong[("allow", v.QUERY, "untrusted_app_32", "fd", "")] = {"use"}
        with self.assertRaises(ValueError):
            v._compare(wrong, expected, "forbidden descriptor")

    def test_existing_metadata_and_stdio_roles_remain_distinct(self):
        table = v._explicit_board()
        self.assertEqual(table[("allow", v.QUERY, "droidloom_query_io", "fifo_file", "")], {"getattr", "write"})
        self.assertNotIn(("allow", v.QUERY, "kernel", "fifo_file", ""), table)
        self.assertNotIn(("allow", "droidloom_broker", v.QUERY, "process", ""), table)
        self.assertEqual(table[("allow", "droidloom_metadata_observer", v.QUERY, "process", "")], {"getattr"})


if __name__ == "__main__":
    unittest.main()
