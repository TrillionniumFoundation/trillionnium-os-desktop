"""Adversarial full-projection/path tests for the fixed native APK component."""
from collections import defaultdict
from pathlib import Path
import unittest
import verify_native_apk as v


def fixture(extra=""):
    types = set(v.OWNED) | {"other_t", "outsider_t", "app_data_file", "kernel"}
    classes = defaultdict(set)
    acl = v._forms(v.FIXED_ACL)
    for f in acl:
        for name in f[1:3]:
            if name != "self" and name not in v.GROUPS:
                types.add(name)
        if f[0] == "typetransition":
            types.add(f[-1])
        elif f[0] == "allow":
            classes[f[3][0]].update(f[3][1])
    classes["file"].update(("ioctl", "write", "append", "relabelfrom", "relabelfrom", "execute"))
    classes["dir"].update(("write", "add_name"))
    classes["process"].update(("fork", "dyntransition", "ptrace"))
    rows = ["(type " + n + ")" for n in sorted(types)]
    rows += ["(class " + c + " (" + " ".join(sorted(p)) + "))" for c, p in classes.items()]
    for name in sorted(types):
        rows.append(f"(roletype object_r {name})")
        if name in v.SUBJECTS:
            rows.append(f"(roletype r {name})")
    groups = {**v.GROUPS, "p4_all_board_owned": v.OWNED}
    groups.update({g: () for g in ("domain", "coredomain", "mlstrustedsubject", "mlstrustedobject",
                                   "netdomain", "p4_linux_procs", "p4_linux_data",
                                   "p4_linux_native_processes", "p4_linux_mac_roles")})
    rows += ["(typeattributeset " + n + " (" + " ".join(sorted(m)) + "))" for n, m in groups.items()]
    forms = v._forms("\n".join(rows) + "\n" + extra)
    return v._Index(forms), forms, acl


class NativeApkTests(unittest.TestCase):
    def test_fixed_complete_projection_and_four_birth_transitions(self):
        index, _, acl = fixture()
        v._validate_membership(index)
        expected = v._expectation(index, [])
        v._compare(v._project(acl, index), expected)
        self.assertEqual(len(expected[1]), 4)
        self.assertEqual(expected[2], set())

    def test_every_unrelated_inbound_and_outbound_raw_grant_is_rejected(self):
        index, _, acl = fixture("(typeattributeset outside (other_t outsider_t))")
        expected = v._expectation(index, [])
        for row in (
            f"(allow outside {v.SOURCE} (file (read)))",
            f"(allow {v.READER} other_t (file (read)))",
            f"(allow {v.BROKER} {v.COPY} (file (write)))",
            f"(allow {v.CREATOR} {v.SOURCE} (file (open)))",
            f"(allow {v.READER} app_data_file (file (getattr)))",
            f"(allow {v.READER} self (process (fork)))",
            f"(allow {v.ANCESTOR_PAIR[0]} {v.ANCESTOR_PAIR[1]} (file (read)))",
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                v._compare(v._project(acl + v._forms(row), index), expected)

    def test_attribute_complements_cannot_hide_new_readers(self):
        index, _, acl = fixture("(typeattributeset unknown_readers (not (droidloom_broker)))")
        bad = v._forms(f"(allow unknown_readers {v.COPY} (file (read)))")
        with self.assertRaises(ValueError):
            v._compare(v._project(acl + bad, index), v._expectation(index, []))

    def test_audit_suppression_and_full_ioctl_space_are_closed(self):
        index, _, acl = fixture()
        for kind in ("auditallow", "dontaudit"):
            with self.assertRaises(ValueError):
                v._compare(v._project(acl + v._forms(f"({kind} other_t {v.COPY} (file (read)))"), index), v._expectation(index, []))
        for kind in ("allowx", "auditallowx", "dontauditx"):
            with self.assertRaises(ValueError):
                v._compare(v._project(acl + v._forms(f"({kind} {v.READER} {v.COPY} (ioctl file (range 0x0000 0xffff)))"), index), v._expectation(index, []))

    def test_transitions_contexts_and_nested_authority_cannot_escape(self):
        index, _, acl = fixture()
        for row in (
            f"(typetransition other_t tmpfs file {v.COPY})",
            f"(typetransition {v.READER} tmpfs file \"caller-name\" {v.COPY})",
            f"(genfscon tmpfs /unexpected (u object_r {v.COPY} ((s0) (s0))))",
            f"(typepermissive {v.CREATOR})",
            f"(typebounds other_t {v.READER})",
            f"(optional extra (allow other_t {v.SOURCE} (file (read))))",
            f"(booleanif conditional (true (allow p4_native_apk_children other_t (file (read)))))",
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                v._compare(v._project(acl + v._forms(row), index), v._expectation(index, []))

    def test_old_role_or_broad_attribute_membership_cannot_be_added(self):
        _, forms, _ = fixture()
        for row in (
            f"(roletype system_r {v.READER})",
            f"(roletype r {v.COPY})",
            f"(typeattributeset domain ({v.CREATOR}))",
            f"(typeattributeset p4_linux_data ({v.SOURCE}))",
            f"(typeattributeset p4_native_apk_children (other_t))",
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                v._validate_membership(v._Index(forms + v._forms(row)))

    def test_exact_source_apparmor_rejects_additional_file_wildcard_or_writer(self):
        here = Path(__file__).resolve().parent
        value = v._contract(here)
        for name in ("droidloom-production-broker", "droidloom-working-privateprep", "droidloom-working-application"):
            body = (here / "apparmor" / name).read_text()
            v._helper_apparmor(name, body, value)
            marker = "# END fixed native helper sources"
            for extra in ("/usr/libexec/droidloom/native-application-leaves/** r,\n",
                          "/usr/libexec/droidloom/other.apk r,\n",
                          value["helper_source_files"][0]["path"] + " rw,\n"):
                with self.subTest(name=name, extra=extra), self.assertRaises(ValueError):
                    v._helper_apparmor(name, body.replace(marker, extra + marker), value)


if __name__ == "__main__":
    unittest.main()
