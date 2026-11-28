"""Regressions for the watchdog birth role's non-inherited device boundary.

These are parser/vector fixtures, not a claim of linked-kernel qualification.
The normal strict producer additionally compiles every neverallow and checks
the complete actual binary, including the unchanged original device vectors.
"""
import copy
import tempfile
import unittest
from pathlib import Path

import derive_native_tmpfiles_policy as tmp
from derive_native_random_seed_policy import RawPolicy

HERE = Path(__file__).resolve().parent
ACTORS = [("r", tmp.BIRTH_LABEL)] + [("system_r", name) for name in (
    "p4_linux_early_t", "p4_linux_hardware_label_t",
    "droidloom_metadata_observer", "droidloom_query_io")]
PERMISSIONS = ["getattr", "search", "open", "read", "write", "create",
               "setattr", "relabelfrom", "relabelto", "ioctl", "associate", "add_name"]


def fixture(extra=()):
    names = {"device", tmp.BIRTH_DEVICE, *tmp.FRESH_OBJECTS.values(),
             tmp.FRESH_METADATA_REFERENCE, tmp.ROLE, *(name for _, name in ACTORS)}
    lines = [f"(type {name})" for name in sorted(names)]
    lines += [f"(class {kind} ({' '.join(PERMISSIONS)}))"
              for kind in ("chr_file", "dir", "filesystem", "lnk_file", "blk_file", "file")]
    lines += [f"(allow {tmp.BIRTH_LABEL} device (chr_file (getattr relabelfrom)))",
              f"(allow {tmp.BIRTH_LABEL} device (filesystem (getattr)))",
              f"(allow {tmp.BIRTH_LABEL} {tmp.BIRTH_DEVICE} (chr_file (getattr relabelto)))"]
    lines += [f"(allow {name} device (chr_file (getattr relabelfrom)))"
              for name in ("p4_linux_early_t", "p4_linux_hardware_label_t")]
    lines += ["(allow droidloom_query_io device (dir (getattr search)))"]
    lines += [f"(allow {tmp.ROLE} {tmp.FRESH_OBJECTS['chr_file']} (chr_file (create getattr relabelto setattr)))",
              f"(allow {tmp.ROLE} {tmp.FRESH_OBJECTS['dir']} (dir (add_name create getattr open read relabelto search setattr write)))"]
    for name in ("droidloom_metadata_observer", "droidloom_query_io"):
        for target in (tmp.FRESH_METADATA_REFERENCE, *tmp.FRESH_OBJECTS.values()):
            lines.append(f"(allow {name} {target} (dir (getattr search)))")
    return lines + list(extra)


class ObservedPolicy:
    def __init__(self, raw, nonzero=None):
        self.raw, self.nonzero = raw, nonzero

    def permissions(self, kind, names):
        return 1, {name: 1 << PERMISSIONS.index(name) for name in names}

    def context_av(self, actor, target, kind, names):
        if actor.split(":")[2] == tmp.BIRTH_LABEL and actor.split(":")[1] != "r":
            raise AssertionError("The real birth actor is bound to r, not system_r")
        key = (actor, target, kind)
        if key == self.nonzero:
            return 1
        allowed = self.raw.actor(actor.split(":")[2]).get((target.split(":")[2], kind), set())
        return sum(bit for name, bit in self.permissions(kind, names)[1].items() if name in allowed)


def derived():
    lines = fixture()
    raw = RawPolicy(lines)
    proof, generated = tmp._derive_devices(ObservedPolicy(raw), raw, lines, None, ACTORS)
    linked = RawPolicy(lines + generated)
    return proof, generated, linked


class FixedBirthDeviceBoundary(unittest.TestCase):
    def test_actual_source_contract_keeps_neverallow_and_explicit_confinement(self):
        value = tmp.contract(HERE)
        self.assertEqual(value["device_view_preservation"]["fixed_board_birth_confinement"],
                         tmp.BIRTH_DEVICE_CONFINEMENT)
        self.assertFalse(value["normal_implementation_changed"])
        self.assertFalse(value["production_qualified"])

    def test_only_the_birth_child_is_omitted_from_the_derived_static_node_group(self):
        proof, generated, linked = derived()
        self.assertNotIn(tmp.BIRTH_LABEL, "\n".join(generated))
        before = RawPolicy(fixture())
        self.assertEqual(before.incoming("device"), linked.incoming("device"))
        for role in ("p4_linux_early_t", "p4_linux_hardware_label_t"):
            self.assertEqual(linked.incoming(tmp.FRESH_OBJECTS["chr_file"])[role, "chr_file"],
                             {"getattr", "relabelfrom"})
        checks = tmp._verify_devices(ObservedPolicy(linked), linked, [], None, proof)
        self.assertTrue(checks)

    def test_json_roundtripped_actor_rows_keep_the_same_closed_role(self):
        raw = RawPolicy(fixture())
        self.assertTrue(tmp._birth_device_boundary(ObservedPolicy(raw), raw,
                                                  [list(row) for row in ACTORS]))

    def test_hidden_attribute_grant_to_the_static_node_is_rejected(self):
        lines = fixture([
            "(typeattribute hidden)",
            f"(typeattributeset hidden ({tmp.BIRTH_LABEL} p4_linux_early_t))",
            f"(allow hidden {tmp.FRESH_OBJECTS['chr_file']} (chr_file (getattr)))",
        ])
        raw = RawPolicy(lines)
        with self.assertRaisesRegex(ValueError, "static-device raw"):
            tmp._birth_device_boundary(ObservedPolicy(raw), raw, ACTORS)

    def test_every_class_on_both_new_objects_remains_zero(self):
        for target in tmp.FRESH_OBJECTS.values():
            for kind in ("dir", "file", "lnk_file", "blk_file", "filesystem", "chr_file"):
                raw = RawPolicy(fixture([f"(allow {tmp.BIRTH_LABEL} {target} ({kind} (getattr)))"]))
                with self.subTest(target=target, kind=kind), self.assertRaises(ValueError):
                    tmp._birth_device_boundary(ObservedPolicy(raw), raw, ACTORS)

    def test_source_changes_cannot_enable_later_device_alias_inheritance(self):
        for kind, permission in (("chr_file", "read"), ("lnk_file", "read"),
                                 ("blk_file", "getattr"), ("dir", "search"),
                                 ("filesystem", "associate")):
            raw = RawPolicy(fixture([f"(allow {tmp.BIRTH_LABEL} device ({kind} ({permission})))"]))
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "preimage"):
                tmp._birth_device_boundary(ObservedPolicy(raw), raw, ACTORS)

    def test_missing_original_metadata_and_changed_selected_device_vector_fail(self):
        lines = fixture()
        for old, new in (("(getattr relabelfrom)", "(getattr)"),
                         ("(getattr relabelto)", "(getattr read relabelto)")):
            raw = RawPolicy([line.replace(old, new) if tmp.BIRTH_LABEL in line else line for line in lines])
            with self.assertRaisesRegex(ValueError, "preimage"):
                tmp._birth_device_boundary(ObservedPolicy(raw), raw, ACTORS)

    def test_even_an_ineffective_ioctl_filter_is_not_copied_to_new_devices(self):
        for target in ("device", tmp.BIRTH_DEVICE, *tmp.FRESH_OBJECTS.values()):
            raw = RawPolicy(fixture([f"(allowx {tmp.BIRTH_LABEL} {target} (ioctl chr_file (0x542a)))"]))
            with self.subTest(target=target), self.assertRaises(ValueError):
                tmp._birth_device_boundary(ObservedPolicy(raw), raw, ACTORS)

    def test_binary_decision_at_a_nondefault_category_cannot_escape_zero(self):
        raw = RawPolicy(fixture())
        target = tmp.FRESH_OBJECTS["chr_file"]
        key = (tmp._context("r", tmp.BIRTH_LABEL, tmp.LEVELS[-1]),
               tmp._context("object_r", target, tmp.LEVELS[0]), "chr_file")
        with self.assertRaisesRegex(ValueError, "category decision"):
            tmp._birth_device_boundary(ObservedPolicy(raw, key), raw, ACTORS)

    def test_missing_duplicated_or_retyped_birth_actor_is_rejected(self):
        raw = RawPolicy(fixture())
        for actors in (ACTORS[1:], ACTORS + ACTORS[:1],
                       [("object_r", tmp.BIRTH_LABEL)] + ACTORS[1:],
                       [("system_r", tmp.BIRTH_LABEL)] + ACTORS[1:],
                       ACTORS + [("system_r", tmp.BIRTH_LABEL)]):
            with self.assertRaisesRegex(ValueError, "preimage"):
                tmp._birth_device_boundary(ObservedPolicy(raw), raw, actors)

    def test_expected_proof_cannot_override_the_fixed_zero_boundary(self):
        proof, _, raw = derived()
        bad = copy.deepcopy(proof)
        bad["fixed_board_birth_confinement"] = {}
        with self.assertRaisesRegex(ValueError, "contract"):
            tmp._verify_devices(ObservedPolicy(raw), raw, [], None, bad)
        bad = copy.deepcopy(proof)
        bad["birth_zero_vectors"] = []
        with self.assertRaisesRegex(ValueError, "zero vector"):
            tmp._verify_devices(ObservedPolicy(raw), raw, [], None, bad)

    def test_source_boundary_cannot_drop_or_widen_the_existing_neverallow(self):
        body = (HERE / "ubuntu-working-qualification.cil").read_text()
        for changed in (body.replace(f"(roletype r {tmp.BIRTH_LABEL})",
                                    f"(roletype system_r {tmp.BIRTH_LABEL})"),
                        body.replace(f"(neverallow {tmp.BIRTH_LABEL} p4_working_birth_other_devices", "; removed"),
                        body.replace(f"(not (device {tmp.BIRTH_DEVICE}))",
                                     f"(not (device {tmp.BIRTH_DEVICE} p4_linux_tmpfiles_static_node_t))")):
            with tempfile.TemporaryDirectory() as directory:
                here = Path(directory)
                (here / "ubuntu-working-qualification.cil").write_text(changed)
                with self.assertRaisesRegex(ValueError, "source boundary"):
                    tmp._birth_source_boundary(here)


if __name__ == "__main__":
    unittest.main()
