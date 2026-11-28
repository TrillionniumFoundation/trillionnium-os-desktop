"""Adversarial checks for the two fixed production actors and their history."""
from collections import defaultdict
from pathlib import Path
import unittest
import verify_production_commit as v


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
        elif f[0] in ("allow", "auditallow", "dontaudit"):
            classes[f[3][0]].update(f[3][1])
    classes["file"].update(("ioctl", "write", "append", "setattr", "relabelto", "execute", "create"))
    classes["dir"].update(("create", "write", "add_name"))
    classes["process"].update(("fork", "dyntransition", "ptrace", "setexec"))
    classes["capability"].update(("sys_admin", "sys_boot", "dac_override"))
    rows = ["(type " + n + ")" for n in sorted(types)]
    rows += ["(class " + c + " (" + " ".join(sorted(p)) + "))" for c, p in classes.items()]
    for name in sorted(types):
        rows.append(f"(roletype object_r {name})")
        if name in v.SUBJECTS:
            rows.append(f"(roletype system_r {name})")
    groups = {**v.GROUPS, "p4_all_board_owned": v.OWNED,
              "droidloom_public_control_peers": (v.VERIFY,)}
    groups.update({g: () for g in ("domain", "coredomain", "mlstrustedsubject",
        "mlstrustedobject", "netdomain", "p4_linux_procs", "p4_linux_data",
        "p4_linux_native_processes", "p4_linux_mac_roles", "p4_working_actors",
        "p4_working_children", "p4_handle_owner")})
    rows += ["(typeattributeset " + n + " (" + " ".join(sorted(m)) + "))"
             for n, m in groups.items()]
    forms = v._forms("\n".join(rows) + "\n" + extra)
    return v._Index(forms), forms, acl


class ProductionCommitTests(unittest.TestCase):
    def test_exact_roles_and_eight_named_outputs(self):
        index, _, acl = fixture()
        v._validate_membership(index)
        expected = v._expectation(index, [])
        v._compare(v._project(acl, index), expected)
        self.assertEqual(len(expected[1]), 8)
        self.assertEqual(expected[2], set())
        self.assertEqual({r[4] for r in expected[1]},
            {'"PLAN.json"', '"SUMMARY.json"', '"MAIN.json"', '"STDERR.log"',
             '"COMMIT.json"', '"TRIAL.json"', '"REQUEST.json"', '"ACTIVE.json"'})

    def test_unrelated_inbound_and_outbound_authority_is_rejected(self):
        index, _, acl = fixture("(typeattributeset outside (other_t outsider_t))")
        for row in (
            f"(allow outside {v.COMMIT} (process (transition)))",
            f"(allow {v.COMMIT} other_t (file (read)))",
            f"(allow {v.VERIFY} p4_linux_production_record_t (file (write)))",
            f"(allow {v.COMMIT} p4_linux_production_activation_t (file (read)))",
            f"(allow {v.COMMIT} droidloom_public_control_socket (sock_file (write)))",
            f"(allow {v.VERIFY} app_data_file (file (getattr)))",
            f"(allow {v.PARENT} p4_linux_maintenance_grubenv_t (file (write)))",
        ):
            # The last tuple contains no new endpoint. It belongs to the
            # independent working/original projection, not this new component.
            if "maintenance_grubenv" in row:
                self.assertEqual(v._project(v._forms(row), index)[0], {})
                continue
            with self.subTest(row=row), self.assertRaises(ValueError):
                v._compare(v._project(acl + v._forms(row), index), v._expectation(index, []))

    def test_same_role_capability_and_grub_write_do_not_authorize_setattr(self):
        index, _, acl = fixture()
        for row in (
            f"(allow {v.COMMIT} self (capability (sys_admin)))",
            f"(allow {v.VERIFY} self (capability (sys_boot)))",
            f"(allow {v.COMMIT} p4_linux_maintenance_grubenv_t (file (setattr)))",
            f"(allow {v.VERIFY} p4_linux_production_record_dir_t (dir (create)))",
            f"(allow {v.COMMIT} p4_linux_working_plan_t (file (open)))",
            f"(allow {v.COMMIT} p4_linux_working_plan_t (file (write)))",
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                v._compare(v._project(acl + v._forms(row), index), v._expectation(index, []))

    def test_attribute_complements_cannot_hide_history_writers(self):
        index, _, acl = fixture("(typeattributeset hidden (not (p4_linux_production_commit_t)))")
        bad = v._forms("(allow hidden p4_linux_production_record_t (file (write)))")
        with self.assertRaises(ValueError):
            v._compare(v._project(acl + bad, index), v._expectation(index, []))

    def test_audits_and_unreviewed_ioctl_commands_are_closed(self):
        index, _, acl = fixture()
        for tag in ("auditallow", "dontaudit"):
            row = f"({tag} other_t p4_linux_production_record_t (file (read)))"
            with self.subTest(row=row), self.assertRaises(ValueError):
                v._compare(v._project(acl + v._forms(row), index), v._expectation(index, []))
        for tag in ("allowx", "auditallowx", "dontauditx"):
            for value in ("0x7602", "range 0x0000 0xffff"):
                row = f"({tag} {v.COMMIT} p4_linux_maintenance_grubenv_t (ioctl file ({value})))"
                with self.subTest(row=row), self.assertRaises(ValueError):
                    v._compare(v._project(acl + v._forms(row), index), v._expectation(index, []))

    def test_named_outputs_do_not_admit_generic_or_other_name_transitions(self):
        index, _, acl = fixture()
        for row in (
            f"(typetransition {v.COMMIT} p4_linux_production_record_dir_t file p4_linux_production_record_t)",
            f'(typetransition {v.COMMIT} p4_linux_production_record_dir_t file "EXTRA.json" p4_linux_production_record_t)',
            f'(typetransition {v.COMMIT} p4_linux_production_record_dir_t file "ACTIVE.json" p4_linux_production_activation_t)',
            f"(genfscon tmpfs /extra (u object_r p4_linux_production_record_t ((s0) (s0))))",
            f"(typepermissive {v.COMMIT})",
            f"(typebounds other_t {v.VERIFY})",
            f"(optional extra (allow other_t {v.VERIFY} (file (read))))",
            f"(booleanif b (true (allow p4_production_commit_actors other_t (file (read)))))",
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                v._compare(v._project(acl + v._forms(row), index), v._expectation(index, []))

    def test_roles_and_broad_inheritance_stay_outside_existing_domains(self):
        _, forms, _ = fixture()
        for row in (
            f"(roletype r {v.COMMIT})",
            "(roletype system_r p4_linux_production_record_t)",
            f"(typeattributeset domain ({v.COMMIT}))",
            "(typeattributeset p4_linux_data (p4_linux_production_record_t))",
            f"(typeattributeset p4_working_children ({v.COMMIT}))",
            f"(typeattributeset p4_handle_owner ({v.VERIFY}))",
            f"(typeattributeset droidloom_public_control_peers ({v.COMMIT}))",
            "(typeattributeset p4_production_commit_actors (other_t))",
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                v._validate_membership(v._Index(forms + v._forms(row)))

    def test_fixed_alias_is_mechanical_and_does_not_authorize_another_permission(self):
        index, _, acl = fixture()
        aliases = [{"source": "p4_linux_native_bin_t", "target": "other_t", "class": "file"}]
        copied = v._forms(f"(allow {v.COMMIT} other_t (file (getattr open read execute execute_no_trans map)))"
                         + chr(10) + f"(allow {v.VERIFY} other_t (file (getattr open read execute execute_no_trans map)))")
        expected = v._expectation(index, aliases)
        v._compare(v._project(acl + copied, index), expected)
        with self.assertRaises(ValueError):
            v._compare(v._project(acl + copied + v._forms(f"(allow {v.COMMIT} other_t (file (write)))"), index), expected)

    def test_reciprocal_apparmor_blocks_reject_wildcards_wrong_peer_and_write(self):
        here = Path(__file__).resolve().parent
        for name, expected in v.RECIPROCAL_BLOCKS.items():
            body = (here / "apparmor" / name).read_text()
            v._reciprocal(name, body)
            end = expected.splitlines()[-1].strip()
            for extra in ("/** rw,\n", "unix (send, receive),\n", "/proc/[0-9]*/mem r,\n"):
                with self.subTest(name=name, extra=extra), self.assertRaises(ValueError):
                    v._reciprocal(name, body.replace(end, extra + end))

    def test_actual_source_and_exact_context_contract(self):
        here = Path(__file__).resolve().parent
        actual = v.verify_sources(here)
        self.assertEqual(set(actual), set(v.FILES))
        self.assertEqual(len(actual), 36)
        self.assertEqual(set(v.PROFILES), {"droidloom-production-commit", "droidloom-production-verify"})
        self.assertEqual(len(v.FILE_CONTEXTS), 10)


if __name__ == "__main__":
    unittest.main()
