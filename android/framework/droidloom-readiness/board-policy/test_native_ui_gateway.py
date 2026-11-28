"""Adversarial parsing checks for the complete native UI policy boundary."""
import unittest
from unittest.mock import patch

import verify_native_ui_gateway as v
from derive_native_uevent_policy import Membership

BASE = "\n".join("(type " + t + ")" for t in
                 sorted(v.NEW | {"peer", "ordinary", "alias", "tmpfs"}))
CLASSES = {"file": ["read", "write", "map", "getattr"],
           "process": ["fork", "transition", "dyntransition", "ptrace"],
           "chr_file": ["read", "write", "ioctl"],
           "capability": ["sys_admin"]}


def raw(rules, declarations=""):
    text = BASE + "\n" + declarations + "\n" + rules + "\n"
    return v._raw(text, Membership(text), CLASSES)


class CompleteUiBoundaryTests(unittest.TestCase):
    def test_inbound_outbound_and_self_cover_each_new_type(self):
        for selected in v.NEW:
            with self.subTest(selected=selected):
                rows = raw(
                    f"(allow {selected} ordinary (file (read)))\n"
                    f"(allow peer {selected} (file (write)))\n"
                    f"(allow {selected} self (file (getattr)))")
                self.assertEqual(rows, {
                    ("allow", selected, "ordinary", "file", ""): {"read"},
                    ("allow", "peer", selected, "file", ""): {"write"},
                    ("allow", selected, selected, "file", ""): {"getattr"},
                })

    def test_every_audit_and_extended_family_is_compared(self):
        for operation in sorted(v.AV):
            with self.subTest(operation=operation):
                value = ("(ioctl chr_file (0x0 0xffff))" if operation in v.EXTENDED
                         else "(file (write))")
                rows = raw(f"({operation} peer {v.TEMP[v.READ]} {value})")
                self.assertEqual(len(rows), 1)
                expected = (1 | (1 << 65535) if operation in v.EXTENDED else {"write"})
                self.assertEqual(next(iter(rows.values())), expected)
                with self.assertRaisesRegex(ValueError, "complete"):
                    v._compare(rows, {}, "negative-control")

    def test_boolean_attributes_cannot_hide_an_inbound_grant(self):
        declarations = (
            "(typeattribute selected)\n"
            f"(typeattributeset selected (and (all) (not (ordinary peer alias tmpfs {v.UI} {v.READ} {v.TEMP[v.UI]}))))")
        rows = raw("(allow peer selected (file (write)))", declarations)
        self.assertEqual(rows, {
            ("allow", "peer", v.TEMP[v.READ], "file", ""): {"write"}})
        with self.assertRaises(ValueError):
            v._compare(rows, {}, "hidden-inbound")

    def test_permission_complements_preserve_unexpected_rights(self):
        rows = raw(f"(allow {v.UI} ordinary (file (not (read))))")
        expected = {("allow", v.UI, "ordinary", "file", ""): {"getattr", "map"}}
        self.assertEqual(rows[("allow", v.UI, "ordinary", "file", "")],
                         {"write", "map", "getattr"})
        with self.assertRaises(ValueError):
            v._compare(rows, expected, "hidden-write")

    def test_last_extended_bit_is_not_truncated(self):
        wanted = raw(f"(allowx {v.READ} ordinary (ioctl chr_file (range 0x1 0xfffe)))")
        actual = raw(f"(allowx {v.READ} ordinary (ioctl chr_file (not (0x0))))")
        self.assertEqual(next(iter(actual.values())) ^ next(iter(wanted.values())),
                         1 << 65535)
        with self.assertRaises(ValueError):
            v._compare(actual, wanted, "last-ioctl-bit")

    def test_unknown_permissions_classes_and_nested_rules_fail_closed(self):
        rules = [
            f"(allow {v.UI} ordinary (file (invented)))",
            f"(allow {v.UI} ordinary (invented (read)))",
            f"(allowx {v.UI} ordinary (ioctl chr_file (0x10000)))",
            f"(allowx {v.UI} ordinary (invented chr_file (0x1)))",
            f"(booleanif flag (true (allow {v.UI} ordinary (file (write)))))",
        ]
        for rule in rules:
            with self.subTest(rule=rule), self.assertRaises((ValueError, OverflowError)):
                raw(rule)

    def test_transition_output_is_checked_even_when_both_inputs_are_old(self):
        rule = f"(typetransition peer tmpfs file {v.TEMP[v.UI]})"
        text = BASE + "\n" + rule
        rows = v._transition_rows(text, Membership(text))
        self.assertEqual(rows, {
            ("typetransition", "peer", "tmpfs",
             v.canonical(["file", v.TEMP[v.UI]]))})

    def test_role_and_range_transitions_through_attributes_fail_closed(self):
        declarations = "\n(typeattribute concealed)\n(typeattributeset concealed (" + v.UI + "))\n"
        for rule in ("(roletransition r concealed process system_r)",
                     "(rangetransition peer concealed process ((s0) (s0)))"):
            text = BASE + declarations + rule
            with self.subTest(rule=rule), self.assertRaisesRegex(ValueError, "role/range"):
                v._transition_rows(text, Membership(text))

    def test_original_membership_is_not_learned_from_final_ui_rows(self):
        original = "\n".join([
            "(type original)", "(type old_file)",
            "(typeattribute domain)", "(typeattribute coredomain)",
            "(typeattribute mlstrustedsubject)", "(typeattribute file_type)",
            "(typeattribute untrusted_domain)",
            "(typeattributeset domain (original))",
            "(typeattributeset coredomain (original))",
            "(typeattributeset file_type (old_file))",
            "(typeattributeset untrusted_domain (and (domain) (not (mlstrustedsubject))))",
        ])
        final = original + "\n" + "\n".join(
            ["(type " + t + ")" for t in sorted(v.NEW |
             {"droidloom_contacts_read", "droidloom_contacts_tmpfs"})] + [
            "(typeattributeset domain (droidloom_contacts_read " + v.UI + " " + v.READ + "))",
            "(typeattributeset coredomain (droidloom_contacts_read " + v.UI + " " + v.READ + "))",
            "(typeattributeset mlstrustedsubject (droidloom_contacts_read " + v.READ + "))",
            "(typeattributeset file_type (droidloom_contacts_tmpfs " +
                " ".join(v.TEMP.values()) + "))",
            "(typeattribute p4_native_ui_queries)",
            "(typeattributeset p4_native_ui_queries (" + v.UI + " " + v.READ + "))",
            "(typeattribute p4_closed_cmd_queries)",
            "(typeattributeset p4_closed_cmd_queries (" + v.UI + " " + v.READ + "))",
            ])
        expected, _ = v._expected_membership(original, Membership(final))
        self.assertTrue(expected.member("untrusted_domain", v.UI))
        self.assertFalse(expected.member("untrusted_domain", v.READ))
        corrupted = final + "\n(typeattributeset mlstrustedsubject (" + v.UI + "))"
        with self.assertRaisesRegex(ValueError, "original-attribute"):
            v._expected_membership(original, Membership(corrupted))
        extra = final + "\n(typeattribute unreviewed)\n(typeattributeset unreviewed (" + v.READ + "))"
        with self.assertRaisesRegex(ValueError, "board membership"):
            v._expected_membership(original, Membership(extra))

    def test_normal_alias_does_not_invent_audit_suppression(self):
        table = raw(
            f"(allow {v.UI} ordinary (file (read)))\n"
            f"(dontaudit {v.UI} ordinary (file (write)))")
        aliases = [{"source": "ordinary", "target": "alias", "class": "file"}]
        with patch.object(v, "fixed_normal_aliases", return_value=aliases):
            v._add_aliases(table, None)
        self.assertEqual(table[("allow", v.UI, "alias", "file", "")], {"read"})
        self.assertNotIn(("dontaudit", v.UI, "alias", "file", ""), table)


if __name__ == "__main__":
    unittest.main()
