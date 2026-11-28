"""Negative controls for the independent Calendar authority model."""
import unittest
import verify_native_calendar_counts as v
from derive_native_uevent_policy import Membership

class CalendarBoundaryTests(unittest.TestCase):
    def membership_fixture(self, extra=""):
        original = "\n".join([
            "(type rootfs)", "(type tmpfs)",
            *(f"(typeattribute {a})" for a in ("domain","coredomain","appdomain",
                "mlstrustedsubject","mlstrustedobject","file_type")),
        ])
        final = original + "\n" + "\n".join([
            *(f"(type {t})" for t in sorted(v.NEW)),
            "(type droidloom_metadata_observer)", "(type droidloom_contacts_tmpfs)",
            "(typeattribute p4_all_board_owned)",
            "(typeattributeset p4_all_board_owned (droidloom_metadata_observer droidloom_contacts_tmpfs " +
                " ".join(sorted(v.NEW)) + "))",
            "(typeattributeset file_type (droidloom_contacts_tmpfs " + v.TEMP + "))",
            extra,
        ])
        return original, Membership(final)

    def raw(self, rule):
        text = "\n".join([*(f"(type {t})" for t in sorted(v.NEW | {"kernel","privapp_data_file","tmpfs","outsider"})), rule])
        classes = {"file":["getattr","read","open","write","ioctl"],"fd":["use"]}
        return v._raw(text, Membership(text), classes)

    def test_calendar_never_inherits_android_domain_or_mls_trust(self):
        old, final = self.membership_fixture()
        v._expected_membership(old, final)
        for name in ("domain","coredomain","appdomain","mlstrustedsubject","mlstrustedobject"):
            old, bad = self.membership_fixture(f"(typeattributeset {name} ({v.QUERY}))")
            with self.assertRaises(ValueError):
                v._expected_membership(old, bad)

    def test_calendar_inbound_and_outbound_authority_are_both_measured(self):
        a = self.raw(f"(allow outsider {v.QUERY} (fd (use)))")
        b = self.raw(f"(allow {v.QUERY} outsider (fd (use)))")
        self.assertNotEqual(a,b)
        for value in (a,b):
            with self.assertRaises(ValueError):
                v._compare(value, {}, "test boundary")

    def test_calendar_private_write_is_not_learned_from_a_candidate(self):
        expected = self.raw(f"(allow {v.QUERY} privapp_data_file (file (getattr read open)))")
        widened = self.raw(f"(allow {v.QUERY} privapp_data_file (file (getattr read open write)))")
        with self.assertRaises(ValueError):
            v._compare(widened, expected, "database authority")

    def test_calendar_audit_rules_cannot_hide_extra_authority(self):
        for tag in ("auditallow","dontaudit"):
            candidate = self.raw(f"({tag} {v.QUERY} privapp_data_file (file (read)))")
            with self.assertRaises(ValueError):
                v._compare(candidate, {}, "audit authority")

    def test_calendar_ioctl_extra_bit_is_rejected(self):
        base = self.raw(f"(allowx {v.META} rootfs (ioctl file (0xb703)))".replace("rootfs","tmpfs"))
        extra = self.raw(f"(allowx {v.META} tmpfs (ioctl file ((range 0xb703 0xb704))))")
        with self.assertRaises(ValueError):
            v._compare(extra, base, "namespace ioctl")
        self.assertEqual(v._commands("0xb703"), 1 << 0xb703)
        with self.assertRaises(ValueError):
            v._commands("0x10000")

    def test_calendar_unreviewed_transition_destination_is_detected(self):
        text = "\n".join([*(f"(type {t})" for t in sorted(v.NEW | {"kernel","tmpfs"})),
            f"(typetransition kernel tmpfs process {v.META})"])
        rows = v._transition_rows(text, Membership(text))
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows, {("typetransition",v.QUERY,"tmpfs",v.canonical(["file",v.TEMP]))})


    def test_working_context_projection_accepts_only_the_complete_six_literals(self):
        import copy
        import verify_native_original_projection as p
        declarations=[["type",t]for t in sorted(p.WORKING_CONTEXT_TYPES)]
        ordinary=["genfscon","cgroup2",'"/ordinary"',["u","object_r","old_type",[["s0"],["s0"]]]]
        fixed=copy.deepcopy(list(p.WORKING_GENFS))
        accepted=p.reviewed_working_contexts(declarations+fixed+[ordinary])
        self.assertEqual(accepted,frozenset(p.canonical(f)for f in fixed))
        self.assertNotIn(p.canonical(ordinary),accepted)
        for bad in (fixed[:-1],fixed+[fixed[0]],[]):
            with self.assertRaises(ValueError):
                p.reviewed_working_contexts(declarations+bad)

    def test_working_context_projection_rejects_changed_path_type_user_or_level(self):
        import copy
        import verify_native_original_projection as p
        declarations=[["type",t]for t in sorted(p.WORKING_CONTEXT_TYPES)]
        for mutation in range(5):
            bad=copy.deepcopy(list(p.WORKING_GENFS))
            if mutation==0:bad[0][2]='"/system.slice/other.service"'
            elif mutation==1:bad[0][3][2]="p4_linux_working_limits_t"
            elif mutation==2:bad[0][3][0]="other_u"
            elif mutation==3:bad[0][3][3]=[["s0","c512"],["s0","c512"]]
            else:bad[0][1]="proc"
            with self.assertRaises(ValueError):
                p.reviewed_working_contexts(declarations+bad)


    def test_calendar_dbus_membership_keeps_the_four_source_named_legacy_helpers(self):
        additions = "\n".join([
            "(type droidloom_query_io)", "(type droidloom_instance_launcher)",
            "(type droidloom_policy_loader)",
            "(typeattribute " + v.DBUS_HELPER_ATTRIBUTE + ")",
        ])
        definition = "(typeattributeset " + v.DBUS_HELPER_ATTRIBUTE + " ({members}))"
        old, good = self.membership_fixture(additions + "\n" +
            definition.format(members=" ".join(sorted(v.DBUS_CLOSED_HELPERS))))
        v._expected_membership(old, good)
        for members in (v.DBUS_CLOSED_HELPERS | {v.QUERY},
                        v.DBUS_CLOSED_HELPERS - {"droidloom_query_io"}):
            old, bad = self.membership_fixture(additions + "\n" +
                definition.format(members=" ".join(sorted(members))))
            with self.assertRaises(ValueError):
                v._expected_membership(old, bad)


    def test_calendar_class_vocabulary_extends_original_only_by_fixed_native_classes(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        original = "(class file (getattr read write))"
        service = "(class service (start stop status reload kill load enable disable))"
        dbus = "(class dbus (acquire_svc send_msg))"
        final = "\n".join((original, service, dbus))
        self.assertEqual(v._classes_after_normal_inputs(original, final), {
            "file": ["getattr", "read", "write"],
            "service": ["start", "stop", "status", "reload", "kill", "load", "enable", "disable"],
            "dbus": ["acquire_svc", "send_msg"],
        })
        for bad in (original + "\n" + service,
                    final.replace("acquire_svc send_msg", "acquire_svc send_msg unknown"),
                    final.replace("getattr read write", "getattr read write execute"),
                    final + "\n(class unreviewed (extra))"):
            with self.assertRaises(ValueError):
                v._classes_after_normal_inputs(original, bad)
        with self.assertRaises(ValueError):
            v._classes_after_normal_inputs(original + "\n" + dbus, final)
        with TemporaryDirectory() as directory:
            here = Path(directory)
            service_path = here / "ubuntu-systemd-unit-status.cil"
            dbus_path = here / "ubuntu-dbus.cil"
            service_path.write_text(service)
            dbus_path.write_text(dbus)
            v._require_fixed_native_classes(here)
            for bad in (dbus + "\n" + dbus,
                        dbus.replace("send_msg", "send_msg unknown"),
                        dbus + "\n(classcommon dbus unreviewed)"):
                dbus_path.write_text(bad)
                with self.assertRaises(ValueError):
                    v._require_fixed_native_classes(here)


if __name__ == "__main__":
    unittest.main()
