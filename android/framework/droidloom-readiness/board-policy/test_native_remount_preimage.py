"""Exercise the normal raw-TE preimage guard for working root metadata."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import derive_native_remount_policy as remount
import derive_preserved_alias_policy as preserved
from derive_native_uevent_policy import LEVELS

HERE = Path(__file__).resolve().parent
WORKING = (
    "p4_linux_working_qualification_t", "p4_linux_working_privateprep_t",
    "p4_linux_working_application_t", "p4_linux_working_return_t",
)
OUTSIDERS = (
    "unrelated_actor", "p4_linux_working_watchdog_label_t",
    "p4_linux_working_payload_birth_t",
)
CLASSES = {
    "file": ["getattr", "open", "read", "execute", "map"],
    "lnk_file": ["getattr", "read", "write", "relabelto"],
    "blk_file": ["getattr", "open", "read", "write", "ioctl", "relabelto"],
}


class WorkingRootPreimage(unittest.TestCase):
    def baseline(self):
        rules = {}
        for actor in WORKING + (remount.RETURN,):
            rules[(actor, remount.ROOT_LINK, "lnk_file")] = {"getattr", "read"}
            rules[(actor, remount.ROOT_BLOCK, "blk_file")] = {"getattr"}
        rules[(remount.EARLY, "device", "lnk_file")] = {"getattr", "read"}
        rules[(remount.EARLY, "device", "blk_file")] = {"getattr"}
        rules[(remount.EARLY, remount.ROOT_LINK, "lnk_file")] = {
            "getattr", "read", "relabelto"}
        rules[(remount.EARLY, remount.ROOT_BLOCK, "blk_file")] = {
            "getattr", "relabelto"}
        return rules

    def derive(self, rules):
        """Use the real declaration/raw-vector/alias code with an AV fixture.

        The observed AV deliberately hides body/mutation bits for the selected
        root objects. The raw exported rules must still reject those bits.
        """
        actors = set(WORKING + OUTSIDERS) | {
            "init_t", remount.EXECUTOR, remount.EARLY, remount.RETURN,
            remount.ROLE, remount.TMP_ROLE,
        }
        objects = {row[key] for row in remount.ALIASES for key in ("source", "target")}
        lines = [f"(type {name})" for name in sorted(actors | objects)]
        lines += [f"(roletype system_r {name})" for name in sorted(actors)]
        lines += [f"(roletype object_r {name})" for name in sorted(objects)]
        lines += [f"(class {name} ({' '.join(names)}))" for name, names in CLASSES.items()]
        lines += [f"(allow {a} {t} ({c} ({' '.join(sorted(names))})))"
                  for (a, t, c), names in sorted(rules.items()) if names]
        body = "\n".join(lines) + "\n"

        class ObservedPolicy:
            def __init__(self, *_):
                pass

            def permissions(self, kind, names):
                return 1, {name: 1 << CLASSES[kind].index(name) for name in names}

            def context_av(self, source, target, kind, names):
                actor, obj = source.split(":")[2], target.split(":")[2]
                actual = set(rules.get((actor, obj, kind), ()))
                if obj == remount.ROOT_LINK:
                    actual &= {"getattr", "read", "relabelto"}
                elif obj == remount.ROOT_BLOCK:
                    actual &= {"getattr", "relabelto"}
                return sum(bit for name, bit in self.permissions(kind, names)[1].items()
                           if name in actual)

        def export(_policy, _binary, path):
            path.write_text(body)
            return set(lines)

        with tempfile.TemporaryDirectory() as tmp, patch.object(
                preserved, "ContextPolicy", ObservedPolicy):
            work = Path(tmp)
            return remount.derive(None, work / "fixture.policy", work / "before.cil",
                                  HERE, work / "derived.cil", export)

    def test_normal_deriver_preserves_all_fixed_working_metadata_vectors(self):
        proof = self.derive(self.baseline())
        rows = [row for row in proof["raw_te_samples"] if row[1] in WORKING]
        self.assertEqual(len(rows), 8)
        for _, _, old, target, kind, original, allowed in rows:
            self.assertEqual((old, original), ("device", 0))
            wanted = {"getattr", "read"} if target == remount.ROOT_LINK else {"getattr"}
            self.assertEqual(allowed, sum(1 << CLASSES[kind].index(name) for name in wanted))
        samples = [row for row in proof["mcs_effective_samples"] if row[1] in WORKING]
        self.assertEqual(len(samples), 8 * len(LEVELS) ** 2)
        for row in samples:
            self.assertEqual(row[-2], 0)
        self.assertEqual(proof["isolated_roles"], sorted((remount.ROLE, remount.TMP_ROLE)))

    def test_declared_extra_cannot_create_an_absent_source_preimage(self):
        for actor in WORKING:
            for target, kind, missing in (
                    (remount.ROOT_LINK, "lnk_file", "read"),
                    (remount.ROOT_BLOCK, "blk_file", "getattr")):
                rules = self.baseline()
                rules[(actor, target, kind)].remove(missing)
                with self.subTest(actor=actor, target=target), self.assertRaisesRegex(
                        ValueError, "exact explicit extra-permission preimage"):
                    self.derive(rules)

    def test_effective_av_cannot_hide_extra_device_body_or_mutation_bits(self):
        for actor in WORKING:
            for target, kind, forbidden in (
                    (remount.ROOT_LINK, "lnk_file", "write"),
                    (remount.ROOT_LINK, "lnk_file", "relabelto"),
                    *((remount.ROOT_BLOCK, "blk_file", permission)
                      for permission in ("open", "read", "write", "ioctl", "relabelto"))):
                rules = self.baseline()
                rules[(actor, target, kind)].add(forbidden)
                with self.subTest(actor=actor, target=target, forbidden=forbidden), \
                        self.assertRaisesRegex(ValueError, "exact explicit extra-permission preimage"):
                    self.derive(rules)

    def test_other_roles_cannot_inherit_the_working_metadata_declaration(self):
        for actor in OUTSIDERS:
            for target, kind in ((remount.ROOT_LINK, "lnk_file"),
                                 (remount.ROOT_BLOCK, "blk_file")):
                rules = copy.deepcopy(self.baseline())
                rules[(actor, target, kind)] = {"getattr"}
                with self.subTest(actor=actor, target=target), self.assertRaisesRegex(
                        ValueError, "exact explicit extra-permission preimage"):
                    self.derive(rules)


if __name__ == "__main__":
    unittest.main()
