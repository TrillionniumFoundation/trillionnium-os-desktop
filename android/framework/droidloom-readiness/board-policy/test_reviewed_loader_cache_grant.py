"""Bounded source-set rewrites must preserve every other permission."""
import copy
import unittest
from unittest.mock import patch
import verify_native_tcgets2_audit as audit

SOURCE = "droidloom_policy_loader"
TARGET = "p4_linux_console_ld_cache_native_config_t"
ATTRIBUTE = "p4_console_preserved_12_2"
ZERO_ATTRIBUTE = "p4_console_preserved_12_0"
PERMISSIONS = ["getattr", "map", "open", "read"]

def cil(value):
    return value if isinstance(value, str) else "(" + " ".join(cil(v) for v in value) + ")"

def fixture(extra=()):
    types = [SOURCE, TARGET, "init_t", "other_file", "zero_member"]
    forms = [["type", name] for name in types]
    forms += [["typeattribute", ATTRIBUTE],
              ["typeattributeset", ATTRIBUTE, [SOURCE, "init_t"]],
              ["typeattribute", ZERO_ATTRIBUTE],
              ["typeattributeset", ZERO_ATTRIBUTE, ["zero_member"]],
              ["allow", ATTRIBUTE, TARGET, ["file", list(PERMISSIONS)]],
              ["allow", "init_t", "other_file", ["file", ["write"]]]]
    forms += list(extra)
    return forms, audit.Membership("\n".join(cil(f) for f in forms))

class LoaderCacheDerivedGrantTests(unittest.TestCase):
    def test_split_preserves_all_effective_vectors_and_actual_membership(self):
        forms, membership = fixture()
        original = copy.deepcopy(forms)
        virtual, resolver, proof = audit._split_reviewed_loader_cache_grant(forms, membership)
        self.assertEqual(forms, original)
        self.assertTrue(membership.member(ATTRIBUTE, SOURCE))
        self.assertFalse(resolver.member(ATTRIBUTE, SOURCE))
        self.assertFalse(membership.member(ZERO_ATTRIBUTE, SOURCE))
        self.assertTrue(resolver.member(ZERO_ATTRIBUTE, SOURCE))
        self.assertTrue(resolver.member(ZERO_ATTRIBUTE, "zero_member"))
        self.assertTrue(proof["present"])
        for source in membership.types:
            for target in membership.types:
                self.assertEqual(
                    audit._base_permissions(forms, membership, source, target, "file"),
                    audit._base_permissions(virtual, resolver, source, target, "file"))
        literal = ["allow", SOURCE, TARGET, ["file", PERMISSIONS]]
        restored = [f for f in virtual if f != literal]
        self.assertEqual(audit._base_permissions(restored, resolver, SOURCE, TARGET, "file"), set())
        self.assertEqual(audit._base_permissions(restored, resolver, "init_t", TARGET, "file"),
                         set(PERMISSIONS))
        self.assertEqual(audit._base_permissions(restored, resolver, "init_t", "other_file", "file"),
                         {"write"})

    def test_shared_attribute_used_by_another_target_is_rejected(self):
        forms, membership = fixture([["allow", ATTRIBUTE, "other_file", ["file", ["read"]]]])
        with self.assertRaises(ValueError):
            audit._split_reviewed_loader_cache_grant(forms, membership)

    def test_nested_attribute_reference_is_rejected(self):
        forms, membership = fixture([["typeattribute", "nested_clients"],
                                    ["typeattributeset", "nested_clients", [ATTRIBUTE]]])
        with self.assertRaises(ValueError):
            audit._split_reviewed_loader_cache_grant(forms, membership)

    def test_attribute_used_by_a_constraint_is_rejected(self):
        forms, membership = fixture([["constrain", ["file", ["read"]],
                                     ["eq", "t1", ATTRIBUTE]]])
        with self.assertRaises(ValueError):
            audit._split_reviewed_loader_cache_grant(forms, membership)

    def test_extra_permission_is_not_silently_subtracted(self):
        forms, membership = fixture()
        for form in forms:
            if form[0] == "allow" and form[1] == ATTRIBUTE:
                form[3][1].append("write")
        with self.assertRaises(ValueError):
            audit._split_reviewed_loader_cache_grant(forms, membership)

    def test_repeated_member_is_rejected(self):
        forms, membership = fixture()
        next(f for f in forms if f[0] == "typeattributeset")[2].append(SOURCE)
        with self.assertRaises(ValueError):
            audit._split_reviewed_loader_cache_grant(forms, membership)

    def test_member_bound_is_enforced(self):
        forms, _ = fixture()
        extra = ["member_" + str(i) for i in range(127)]
        forms += [["type", name] for name in extra]
        next(f for f in forms if f[0] == "typeattributeset")[2].extend(extra)
        membership = audit.Membership("\n".join(cil(f) for f in forms))
        with self.assertRaises(ValueError):
            audit._split_reviewed_loader_cache_grant(forms, membership)

    def test_unknown_or_boolean_members_are_rejected(self):
        for member in ("missing_type", ["not", SOURCE]):
            forms, membership = fixture()
            next(f for f in forms if f[0] == "typeattributeset")[2].append(member)
            with self.assertRaises(ValueError):
                audit._split_reviewed_loader_cache_grant(forms, membership)

    def test_existing_concrete_grant_does_not_hide_overlapping_group_authority(self):
        forms, membership = fixture([["allow", SOURCE, TARGET, ["file", list(PERMISSIONS)]]])
        virtual, resolver, proof = audit._split_reviewed_loader_cache_grant(forms, membership)
        self.assertFalse(proof["present"])
        self.assertIs(resolver, membership)
        with patch.object(audit, "REVIEWED_NATIVE_GRANTS",
                          ((SOURCE, TARGET, "file", tuple(PERMISSIONS)),)):
            with self.assertRaisesRegex(ValueError, "already granted"):
                audit._subtract_native_grants(virtual, resolver)


    def test_zero_group_with_any_authority_or_nested_reference_is_rejected(self):
        additions = (
            [["allow", ZERO_ATTRIBUTE, "other_file", ["file", ["read"]]]],
            [["constrain", ["file", ["read"]], ["eq", "t1", ZERO_ATTRIBUTE]]],
            [["typeattribute", "nested_zero"],
             ["typeattributeset", "nested_zero", [ZERO_ATTRIBUTE]]],
        )
        for extra in additions:
            with self.subTest(extra=extra):
                forms, membership = fixture(extra)
                with self.assertRaises(ValueError):
                    audit._split_reviewed_loader_cache_grant(forms, membership)

    def test_zero_group_missing_or_repeated_definition_is_rejected(self):
        for action in ("missing", "repeated"):
            forms, membership = fixture()
            definition = next(f for f in forms
                              if f[0] == "typeattributeset" and f[1] == ZERO_ATTRIBUTE)
            if action == "missing":
                forms.remove(definition)
            else:
                forms.append(copy.deepcopy(definition))
            with self.subTest(action=action), self.assertRaises(ValueError):
                audit._split_reviewed_loader_cache_grant(forms, membership)

    def test_zero_group_requires_unique_concrete_members_without_actor(self):
        for members in ([], ["zero_member", "zero_member"], ["missing_type"],
                        [["not", SOURCE]], ["zero_member", SOURCE]):
            forms, membership = fixture()
            definition = next(f for f in forms
                              if f[0] == "typeattributeset" and f[1] == ZERO_ATTRIBUTE)
            definition[2] = members
            with self.subTest(members=members), self.assertRaises(ValueError):
                audit._split_reviewed_loader_cache_grant(forms, membership)

    def test_zero_group_member_bound_is_enforced(self):
        forms, _ = fixture()
        extra = ["zero_" + str(i) for i in range(4096)]
        forms += [["type", name] for name in extra]
        definition = next(f for f in forms
                          if f[0] == "typeattributeset" and f[1] == ZERO_ATTRIBUTE)
        definition[2].extend(extra)
        membership = audit.Membership("\n".join(cil(f) for f in forms))
        with self.assertRaises(ValueError):
            audit._split_reviewed_loader_cache_grant(forms, membership)

class ExecutorMountDerivedGrantTests(unittest.TestCase):
    def remount(self):
        forms, _ = fixture()
        names = {SOURCE: "p4_linux_service_executor_t",
                 TARGET: "p4_linux_remount_mount_exec_t",
                 ATTRIBUTE: "p4_remount_preserved_1_2",
                 ZERO_ATTRIBUTE: "p4_remount_preserved_1_0"}
        def rename(value):
            if isinstance(value, str):
                return names.get(value, value)
            return [rename(part) for part in value]
        forms = [rename(form) for form in forms]
        permissions = ["execute", *PERMISSIONS]
        next(f for f in forms if f[0] == "allow" and f[1] == names[ATTRIBUTE])[3][1] = permissions
        literal = ["allow", names[SOURCE], names[TARGET], ["file", list(permissions)]]
        forms.append(literal)
        membership = audit.Membership("\n".join(cil(f) for f in forms))
        return forms, membership, literal

    def test_explicit_and_derived_rows_preserve_all_effective_vectors(self):
        forms, membership, literal = self.remount()
        original = copy.deepcopy(forms)
        virtual, resolver, proof = audit._split_reviewed_executor_mount_grant(forms, membership)
        self.assertEqual(forms, original)
        self.assertTrue(proof["existing_concrete_row_retained"])
        self.assertFalse(membership.member("p4_remount_preserved_1_0", literal[1]))
        self.assertTrue(resolver.member("p4_remount_preserved_1_0", literal[1]))
        self.assertEqual(sum(f == literal for f in virtual), 1)
        for source in membership.types:
            for target in membership.types:
                self.assertEqual(
                    audit._base_permissions(forms, membership, source, target, "file"),
                    audit._base_permissions(virtual, resolver, source, target, "file"))
        restored = [f for f in virtual if f != literal]
        self.assertEqual(audit._base_permissions(
            restored, resolver, literal[1], literal[2], "file"), set())
        self.assertEqual(audit._base_permissions(
            restored, resolver, "init_t", literal[2], "file"), set(literal[3][1]))

    def test_missing_explicit_remount_row_is_rejected(self):
        forms, membership, literal = self.remount()
        forms.remove(literal)
        with self.assertRaises(ValueError):
            audit._split_reviewed_executor_mount_grant(forms, membership)

    def test_wider_explicit_remount_row_is_rejected(self):
        forms, membership, literal = self.remount()
        literal[3][1].append("execute_no_trans")
        with self.assertRaises(ValueError):
            audit._split_reviewed_executor_mount_grant(forms, membership)

    def test_remount_attribute_cannot_be_reused(self):
        forms, membership, literal = self.remount()
        forms.append(["allow", "p4_remount_preserved_1_2", "other_file", ["file", ["read"]]])
        with self.assertRaises(ValueError):
            audit._split_reviewed_executor_mount_grant(forms, membership)


if __name__ == "__main__":
    unittest.main()
