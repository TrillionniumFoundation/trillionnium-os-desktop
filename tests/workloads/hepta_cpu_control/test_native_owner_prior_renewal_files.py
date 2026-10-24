"""Actual private ext2 reads of inert records, never a native owner receipt."""
import copy
import struct
import unittest

import native_owner_evidence as e
import native_owner_prior_boot_authority as authority
import native_owner_prior_boot_disk as physical
import native_owner_prior_boot_types as fixed
import native_owner_prior_renewal_files as observed
import native_owner_root_observation as launch
import test_native_owner_prior_boot_disk as support
from native_owner_prior_renewal_test_records import pair


class PriorRenewalPhysicalFileTests(unittest.TestCase):
    setUp = support.ActualPriorBootDiskTests.setUp
    mutate = support.ActualPriorBootDiskTests.mutate
    directory = support.ActualPriorBootDiskTests.directory
    install = support.ActualPriorBootDiskTests.install
    disk = support.ActualPriorBootDiskTests.disk

    def source(self, name, raw):
        path = self.root / name
        path.write_bytes(raw)
        return path

    def observation_fixture(self):
        _, records = pair()
        transcript = records.evaluate()
        values = [transcript["adoption_event"], *transcript["root_launch_observations_expected"]]
        self.directory(fixed.OBSERVATIONS)
        empty = self.source("empty-inert-lock", b"")
        for index, value in enumerate(values):
            name = launch.launch_observation_filename(value["observation_id"])
            raw = e.canonical({"schema_version": 1, "observation_id": value["observation_id"],
                               "payload": list(value["durable_payload_json"].encode())}).encode()
            self.install(self.source(f"inert-observation-{index}", raw), fixed.OBSERVATIONS + "/" + name)
            self.install(empty, fixed.OBSERVATIONS + "/" + name + ".lock")
        return transcript

    def test_actual_cut_and_two_launches_have_one_closed_inventory_and_retained_bytes(self):
        transcript = self.observation_fixture()
        with self.disk("combined-readonly") as disk:
            result = observed.saved_observations(disk, transcript)
            self.assertTrue(result["exact_inventory_verified"])
            self.assertFalse(result["native_execution_verified"])
            self.assertEqual(len(result["launch_files"]), 2)
            inodes = [result[key]["inode"]["inode"] for key in ("record", "lock")]
            inodes += [value[key]["inode"]["inode"] for value in result["launch_files"] for key in ("record", "lock")]
            self.assertEqual(len(inodes), len(set(inodes)))
            for command in disk.commands:
                self.assertNotIn("-w", command["argv"])
                self.assertEqual(command["pass_fds"], [disk.fd])

    def test_extra_staged_root_record_or_changed_cut_is_not_hidden_by_valid_launches(self):
        transcript = self.observation_fixture()
        changed = copy.deepcopy(transcript)
        changed["adoption_event"]["durable_payload_json"] += " "
        with self.disk("changed-cut") as disk, self.assertRaisesRegex(ValueError, "physical cut"):
            observed.saved_observations(disk, changed)
        path = fixed.OBSERVATIONS + "/unexpected.next"
        self.install(self.source("inert-unexpected", b"unexpected staged record"), path)
        with self.disk("unexpected-record") as disk, self.assertRaisesRegex(ValueError, "missing, extra or unfinished"):
            observed.saved_observations(disk, transcript)

    def consumer_fixture(self):
        head = {"authority_epoch": 7, "revision": 1, "revoked_grant_ids": []}
        pin = {"expected_verifying_key": [9] * 32}
        state = e.canonical({"schema": 3, "signer_id": fixed.SIGNER,
                            "trust": {"IssuerKeyRing": authority.keyring_digest(pin["expected_verifying_key"], 7)},
                            "head": head}).encode()
        self.directory(fixed.BASE + "/consumer-local", 60001)
        empty = self.source("inert-empty", b"")
        nonces = [bytes([index]) * 32 for index in range(1, 5)]
        expected = []
        for lane in ("device", "notes"):
            directory = fixed.BASE + "/consumer-local/" + lane
            self.directory(directory, 60001)
            self.install(self.source("inert-state-" + lane, state), directory + "/authority.json", 60001)
            self.install(empty, directory + "/authority.lock", 60001)
            claims = b"" if lane == "notes" else b"".join(struct.pack(">Q", 7) + nonce for nonce in nonces)
            self.install(self.source("inert-claims-" + lane, claims), directory + "/authority.claims", 60001)
            if lane == "device":
                # Explicit inert file-size fixture: all bytes are test data.
                # The first actual read exposes only the old 40-byte prefix;
                # a later size change exercises same-inode prefix checking.
                self.mutate("set_inode_field " + physical.Disk.physical(directory + "/authority.claims") + " size 40")
            frontier = authority.final_use_frontier(head, nonces[:1] if lane == "device" else [])
            expected.append(frontier)
            self.protected_frontier(lane, frontier)
        return pin, head, nonces, expected

    def protected_frontier(self, lane, value, replace=False):
        directory = fixed.AUTHORITY + "/" + lane + "-consumer"
        self.directory(directory)
        path = directory + "/" + authority.frontier_name(fixed.SIGNER)
        if replace:
            self.mutate("rm " + physical.Disk.physical(path))
        raw = e.canonical({"schema": 1, "owner_id": fixed.SIGNER, "frontier": value}).encode()
        self.install(self.source("inert-frontier-" + lane, raw), path)

    def test_original_claim_prefix_and_inodes_survive_three_new_effect_observations(self):
        pin, head, nonces, expected = self.consumer_fixture()
        with self.disk("first-consumers") as disk:
            first = observed.consumers(disk, expected, pin, 0)
        path = fixed.BASE + "/consumer-local/device/authority.claims"
        self.mutate("set_inode_field " + physical.Disk.physical(path) + " size 160")
        expected[0] = authority.final_use_frontier(head, nonces)
        self.protected_frontier("device", expected[0], replace=True)
        with self.disk("continued-consumers") as disk:
            final = observed.consumers(disk, expected, pin, 3, first)
            self.assertEqual(final["device"]["claim_count"], 4)
            self.assertEqual(final["notes"]["claim_count"], 0)
            self.assertEqual(final["device"]["claims_file"]["inode"]["inode"], first["device"]["claims_file"]["inode"]["inode"])
        with self.disk("unaccounted-effect") as disk, self.assertRaisesRegex(ValueError, "redispatched"):
            observed.consumers(disk, expected, pin, 4, first)


if __name__ == "__main__":
    unittest.main()
