"""Reject widened input, service entry and audit authority for EMPTY diagnostics."""
from pathlib import Path
import json
import tempfile
import unittest

import verify_empty_meituan as e
import verify_working_qualification as w
from test_working_qualification import index


class EmptyMeituanTests(unittest.TestCase):
    def test_omitting_capture_or_budget_source_cannot_redefine_the_reviewed_roster(self):
        here = Path(__file__).resolve().parent
        value = e.verify_sources(here)
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "android/framework/droidloom-readiness/board-policy"
            copy.mkdir(parents=True)
            for name in (
                    e.FIXTURE + "boot_empty_meituan_capture.rs",
                    e.FIXTURE + "boot_owned_evidence.rs",
                    e.RUNTIME + "production_persistent_data_backings.rs",
                    e.RUNTIME + "droidloom-early-observer.service"):
                changed = dict(value)
                changed["files"] = {key: pin for key, pin in value["files"].items() if key != name}
                (copy / "empty-meituan-source.json").write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, "causal source closure differs"):
                    e.verify_sources(copy)

    def test_changed_admission_capture_and_budget_bytes_invalidate_the_source_commitment(self):
        here = Path(__file__).resolve().parent
        value = e.verify_sources(here)
        original = here.parents[3]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy = root / "android/framework/droidloom-readiness/board-policy"
            copy.mkdir(parents=True)
            (copy / "empty-meituan-source.json").write_text(json.dumps(value))
            for name in e.FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((original / name).read_bytes())
            for name in (
                    e.FIXTURE + "boot_empty_meituan_capture.rs",
                    e.FIXTURE + "boot_vm.rs",
                    e.RUNTIME + "production_persistent_data_backings.rs",
                    e.RUNTIME + "droidloom-production.service"):
                target = root / name
                body = target.read_bytes()
                target.write_bytes(body + b"\nchanged source\n")
                with self.assertRaisesRegex(ValueError, "Changed EMPTY runtime source"):
                    e.verify_sources(copy)
                target.write_bytes(body)

    def test_input_objects_are_not_generic_linux_data_or_processes(self):
        idx, forms = index()
        w._validate_membership(idx)
        for group in ("p4_linux_data", "p4_linux_procs", "domain", "mlstrustedobject"):
            for obj in w.EMPTY_DATA:
                with self.assertRaises(ValueError):
                    w._validate_membership(w._Index(forms + w._forms(
                        "(typeattributeset " + group + " (" + obj + "))")))

    def test_only_preparation_reads_body_and_no_actor_mutates_or_executes(self):
        idx, _ = index()
        expected = w._project(w._forms(w.EMPTY_ACL), idx)
        for actor in (w.PARENT, w.PHYSICAL, w.RETURN, w.BIRTH, "droidloom_broker", "old_reader_t"):
            for tag in ("allow", "auditallow", "dontaudit"):
                bad = w._forms(w.EMPTY_ACL + "\n(" + tag + " " + actor + " " + w.EMPTY_APK + " (file (read)))")
                with self.assertRaises(ValueError):
                    w._compare(w._project(bad, idx), expected)
        for permission in ("write", "append", "create", "setattr", "map", "execute"):
            bad = w._forms(w.EMPTY_ACL + "\n(allow " + w.PREP + " " + w.EMPTY_APK + " (file (" + permission + ")))")
            with self.assertRaises(ValueError):
                w._compare(w._project(bad, idx), expected)

    def test_unit_entry_does_not_grant_dynamic_or_other_child_transition(self):
        idx, _ = index()
        expected = w._project(w._forms(w.EMPTY_ACL), idx)
        for actor, permission in ((w.PREP, "dyntransition"), (w.PHYSICAL, "transition")):
            bad = w._forms(w.EMPTY_ACL + "\n(allow p4_linux_service_executor_t " + actor + " (process (" + permission + ")))")
            with self.assertRaises(ValueError):
                w._compare(w._project(bad, idx), expected)
        for permission in ("ptrace", "sigkill"):
            bad = w._forms(w.EMPTY_ACL + "\n(allow droidloom_broker " + w.PREP + " (process (" + permission + ")))")
            with self.assertRaises(ValueError):
                w._compare(w._project(bad, idx), expected)

    def test_fixed_unit_values_are_complete_and_duplicate_authority_is_rejected(self):
        good = "[Unit]\nConditionPathExists=" + e.APK + "\n[Service]\n" + "\n".join(
            key + "=" + value for key, value in e.UNIT_VALUES.items() if key != "ConditionPathExists")
        e.verify_unit(good)
        for bad in (good + "\nExecStart=/bin/sh", good + "\n[Install]\nWantedBy=graphical.target",
                    good.replace("RuntimeMaxSec=780s", "RuntimeMaxSec=infinity"),
                    good.replace("CAP_SYS_PTRACE", "CAP_SYS_ADMIN"),
                    good.replace("empty-meituan-diagnostic\n", "empty-meituan-diagnostic --package arbitrary\n")):
            with self.assertRaises(ValueError):
                e.verify_unit(bad)

    def test_exact_apparmor_pair_rejects_wildcard_and_other_readers(self):
        here = Path(__file__).resolve().parent
        profiles = {name: (here / "apparmor" / name).read_text() for name in (
            "droidloom-working-qualification", "droidloom-working-privateprep",
            "droidloom-working-application", "droidloom-working-qualification-return",
            "droidloom-production-broker")}
        e.verify_apparmor(profiles)
        for name in ("droidloom-working-application", "droidloom-working-qualification-return"):
            bad = dict(profiles)
            bad[name] += "\n" + e.APK + " r,\n"
            with self.assertRaises(ValueError):
                e.verify_apparmor(bad)
        bad = dict(profiles)
        bad["droidloom-working-privateprep"] = bad["droidloom-working-privateprep"].replace(e.APK + " r,", e.DIRECTORY + "/** rw,")
        with self.assertRaises(ValueError):
            e.verify_apparmor(bad)


if __name__ == "__main__":
    unittest.main()
