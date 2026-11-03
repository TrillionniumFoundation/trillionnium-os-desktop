"""Inert evidence-parser records only; no kernel or resource-pressure execution."""

import copy
import unittest

import native_owner_memory as memory


class Lifecycle:
    def __init__(self):
        self.lines, self.images = [], []
        self.sequence, self.minimum = 0, 512 * 1024**2
        self.roles = {"root": 1, "manager": 2, "workload": 3, "recovery": 4}
        self.sample("before_snapshot", "none", 0, 400_000_000)
        self.sample("snapshot_retained", "none", 0, 370_000_000)
        for role in self.roles:
            self.images.append(len(self.lines))
            self.lines.append("inert image position")
            self.sample("initial_image_prepared", role, 0, 370_000_000 - 25_000_000 * self.roles[role])
        self.activation = len(self.lines)
        self.lines.append("inert activation position")
        self.sample("initial_roles_ready", "none", 0, 272_000_000)
        self.event = len(self.lines)
        self.lines.append("inert owner event position")

    def sample(self, stage, role, generation, free):
        self.sequence += 1
        self.minimum = min(self.minimum, free)
        workload = role == "workload"
        pid = 0 if role == "none" else self.roles.get(role, 9) + generation * 10
        self.lines.append(
            f"{memory.PREFIX} schema=1 sample={self.sequence} stage={stage} generation={generation} "
            f"role={role} pid={pid} ordinary_free_bytes={free} sampled_min_free_bytes={self.minimum} "
            f"slab_backing_bytes=8192000 account_present={'true' if workload else 'false'} "
            f"selected_user_pages={5100 if workload else 0} selected_user_limit_pages={16384 if workload else 0} "
            "complete_peak=false global_memory_reserve=false")

    def result(self):
        return memory.evaluate(self.lines, self.roles, self.images, self.activation, self.event)


class LifecycleMemoryTests(unittest.TestCase):
    def test_initial_and_successor_samples_retain_finite_scope(self):
        fixture = Lifecycle()
        for stage, role in (("successor_before_images", "none"), ("successor_image_prepared", "manager"),
                            ("successor_image_prepared", "recovery"), ("successor_roles_ready", "none")):
            fixture.sample(stage, role, 1, 240_000_000)
        for stage, role in (("history_before_image", "none"), ("history_image_prepared", "history"),
                            ("history_role_ready", "none")):
            fixture.sample(stage, role, 2, 260_000_000)
        result = fixture.result()
        self.assertEqual(len(result["samples"]), 14)
        self.assertEqual(result["sampled_min_ordinary_free_bytes"], 240_000_000)
        self.assertFalse(result["continuous_peak_verified"])
        self.assertFalse(result["global_memory_reserve"])
        self.assertFalse(result["whole_process_tree_memory_verified"])
        self.assertEqual([entry["role"] for entry in result["samples"] if entry["account_present"]], ["workload"])

    def test_incomplete_initial_or_successor_evidence_is_not_accepted(self):
        missing = Lifecycle()
        missing.lines = missing.lines[:missing.activation]
        with self.assertRaisesRegex(ValueError, "incomplete"):
            missing.result()
        partial = Lifecycle()
        partial.sample("successor_before_images", "none", 1, 250_000_000)
        with self.assertRaisesRegex(ValueError, "incomplete successor"):
            partial.result()

    def test_actual_image_order_and_role_identity_are_required(self):
        fixture = Lifecycle()
        changed = copy.deepcopy(fixture)
        changed.images[0] = changed.images[1]
        with self.assertRaisesRegex(ValueError, "bracket"):
            changed.result()
        changed = copy.deepcopy(fixture)
        changed.roles["workload"] = 99
        with self.assertRaisesRegex(ValueError, "actual initial Process"):
            changed.result()

    def test_sample_minimum_and_unaccounted_roles_cannot_be_relabelled(self):
        original = Lifecycle()
        for before, after in (("sampled_min_free_bytes=400000000", "sampled_min_free_bytes=399999999"),
                              ("complete_peak=false", "complete_peak=true"),
                              ("account_present=false", "account_present=true"),
                              ("ordinary_free_bytes=400000000", "ordinary_free_bytes=600000000")):
            fixture = copy.deepcopy(original)
            fixture.lines[0] = fixture.lines[0].replace(before, after)
            with self.subTest(change=after), self.assertRaises(ValueError):
                fixture.result()

    def test_legacy_owner_evidence_does_not_accept_new_memory_records(self):
        import native_owner_evidence as oracle
        from test_native_owner_evidence import ELF, NONCE, InertRecords

        records = InertRecords(oracle.SCENARIOS[0])
        raw = records.raw() + Lifecycle().lines[0].encode() + b"\n"
        with self.assertRaisesRegex(ValueError, "legacy owner profile"):
            oracle.evaluate(raw, 33, False, False, records.scenario, NONCE, ELF)


if __name__ == "__main__":
    unittest.main()
