"""New APK objects must not change or conceal the original policy boundary."""
import unittest

from derive_native_uevent_policy import Membership
import verify_native_original_projection as original


def cil(value):
    return value if isinstance(value, str) else "(" + " ".join(map(cil, value)) + ")"


def fixture(extra=()):
    rows = [["type", name] for name in ("original_reader_t", "original_file_t")]
    for name in sorted(original.ORIGINAL_ATTRIBUTES):
        rows.extend([["typeattribute", name], ["typeattributeset", name, []]])
    rows.append(["allow", "original_reader_t", "original_file_t", ["file", ["read"]]])
    rows.extend(extra)
    return rows, Membership("\n".join(map(cil, rows)))


class OriginalWorkingApkProjectionTests(unittest.TestCase):
    def test_fixed_apk_objects_preserve_every_original_form(self):
        base, base_membership = fixture()
        expected, baseline = original.project(base, base_membership)
        additions = []
        for name, kind, perms in (
            ("p4_linux_working_apk_dir_t", "dir", ["getattr", "search", "open", "read"]),
            ("p4_linux_working_apk_input_t", "file", ["getattr", "open", "read"]),
        ):
            additions.extend([
                ["type", name], ["roletype", "object_r", name],
                ["allow", "original_reader_t", name, [kind, perms]],
                ["typeattributeset", "p4_all_board_owned", [name]],
            ])
        current, membership = fixture(additions)
        observed, proof = original.project(current, membership)
        self.assertEqual(observed, expected)
        self.assertEqual(proof["original_concrete_types"], baseline["original_concrete_types"])
        self.assertEqual(set(proof["new_types"]), {
            "p4_linux_working_apk_dir_t", "p4_linux_working_apk_input_t"})
        current.append(["allow", "original_reader_t", "original_file_t", ["file", ["write"]]])
        changed, _ = original.project(current, membership)
        self.assertNotEqual(original.summaries(changed), original.summaries(expected))

    def test_unreviewed_type_and_unmodeled_constraint_remain_rejected(self):
        base, membership = fixture()
        _, baseline = original.project(base, membership)
        extra, membership = fixture([["type", "unreviewed_apk_object_t"]])
        _, proof = original.project(extra, membership)
        self.assertNotEqual(proof["original_concrete_types"], baseline["original_concrete_types"])
        constrained, membership = fixture([
            ["type", "p4_linux_working_apk_input_t"],
            ["constrain", ["file", ["read"]], ["eq", "t1", "p4_linux_working_apk_input_t"]],
        ])
        with self.assertRaisesRegex(ValueError, "Unmodeled new-type authority"):
            original.project(constrained, membership)


if __name__ == "__main__":
    unittest.main()
