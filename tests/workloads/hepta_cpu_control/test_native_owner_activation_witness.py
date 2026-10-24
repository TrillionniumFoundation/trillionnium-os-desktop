"""Inert commitments and real private ext2 I/O; never native receipts."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

import native_owner_activation_witness as witness
import native_owner_activation_witness_disk as physical
import native_owner_continuity_types as types
import native_owner_evidence as e
import native_owner_inputs as inputs
import native_owner_prior_boot_authority as authority
import native_owner_prior_boot_types as fixed
from native_owner_activation_test_records import ActivationRecords
import test_native_owner_prior_boot_disk as disk_fixture


class OriginalActivationCommitmentTests(unittest.TestCase):
    def inputs(self):
        records = ActivationRecords("activation-after-material-v1")
        failure = records.event("activation_recovery_prepared")["reconciliation"]
        previous = records.event("owner_released")["current"]
        root = {"uid": 0, "pid": 1, "boot_id": records.linux_boot, "process_start_ticks": 21}
        return failure["canonical_writer"], previous, root, failure["failed_peer"], records.event("owner_released")["material_sha256"]

    def test_complete_original_candidate_token_material_root_and_peer_are_bound(self):
        expected = witness.expectation(*self.inputs())
        for case in ("token", "cut", "root-start", "peer-start", "spawn", "scope", "lease-duration", "legacy"):
            candidate, previous, root, peer, material = copy.deepcopy(self.inputs())
            if case == "token": previous["token"]["head_sha256"] = "cd" * 32
            elif case == "cut": previous["head"]["last_current"]["state_digest"] = "ab" * 32
            elif case == "root-start": root["process_start_ticks"] += 1
            elif case == "peer-start": peer["process_start_ticks"] += 1
            elif case == "spawn": candidate["spawn_generation"] += 1
            elif case == "scope": candidate["authority_lease"]["binding"]["scope_sha256"][0] ^= 1
            elif case == "lease-duration": candidate["authority_lease"]["expires_at_unix_ms"] += 1
            else:
                candidate["authority_lease"]["binding"]["payload_sha256"] = list(bytes.fromhex(types.sha([
                    previous["head"]["last_current"], candidate["spawn_generation"], candidate["local_lease_generation"]])))
            with self.subTest(case=case), self.assertRaises(ValueError):
                witness.expectation(candidate, previous, root, peer, material)
        candidate, previous, root, peer, material = self.inputs()
        reordered = dict(reversed(list(candidate.items())))
        self.assertEqual(witness.expectation(reordered, previous, root, peer, material), expected)

    def test_original_bounded_saved_wrapper_and_complete_payload_are_exact(self):
        expected = witness.expectation(*self.inputs())
        wrapper = {"schema_version": 1, "observation_id": expected["observation_id"],
                   "payload": list(expected["durable_payload_json"].encode())}
        checked = witness.inspect(e.canonical(wrapper).encode(), expected)
        self.assertEqual(checked["payload_sha256"], expected["payload_sha256"])
        for case in ("version", "id", "payload", "extra", "oversize"):
            changed = copy.deepcopy(wrapper)
            if case == "version": changed["schema_version"] = True
            elif case == "id": changed["observation_id"] += "0"
            elif case == "payload": changed["payload"][0] ^= 1
            elif case == "extra": changed["unreviewed"] = True
            else: changed["payload"] = [123] * 16384
            with self.subTest(case=case), self.assertRaises(ValueError):
                witness.inspect(e.canonical(changed).encode(), expected)


class ActualActivationWitnessDiskTests(unittest.TestCase):
    # Reuse only the private ext2 fixture setup helpers, not its test methods.
    mutate = disk_fixture.ActualPriorBootDiskTests.mutate
    directory = disk_fixture.ActualPriorBootDiskTests.directory
    install = disk_fixture.ActualPriorBootDiskTests.install

    def setUp(self):
        disk_fixture.ActualPriorBootDiskTests.setUp(self)
        self.records = ActivationRecords("activation-after-material-v1", agent=fixed.AGENT)
        self.expected = self.records.evaluate()["activation_witnesses_expected"]
        self.directory(witness.DIRECTORY)
        empty = self.root / "inert-lock"
        empty.write_bytes(b"")
        frontier = self.root / "inert-frontier"
        frontier.write_bytes(b'{"inert_file_metadata_test_only":true}')
        frontier_name = authority.frontier_name("root-cognitive-checkpoint-v1")
        self.install(frontier, witness.DIRECTORY + "/" + frontier_name)
        self.install(empty, witness.DIRECTORY + "/" + frontier_name + ".lock")
        material = self.root / "inert-physical-material"
        material.write_bytes(b"INERT HOST FILE: no original writer or SQLite qualification\n")
        installed = set()
        for value in self.expected:
            value["material_sha256"] = inputs.sha(material)
            if value["material_path"] not in installed:
                self.directory(str(Path(value["material_path"]).parent))
                self.install(material, value["material_path"])
                installed.add(value["material_path"])
            wrapper = {"schema_version": 1, "observation_id": value["observation_id"],
                       "payload": list(value["durable_payload_json"].encode())}
            source = self.root / value["filename"]
            source.write_bytes(e.canonical(wrapper).encode())
            self.install(source, witness.DIRECTORY + "/" + value["filename"])
            self.install(empty, witness.DIRECTORY + "/" + value["filename"] + ".lock")

    def verify(self, label):
        return physical.verify(self.image, self.tool, self.tool_identity, inputs.sha(self.image),
                               self.expected, self.root / label)

    def test_actual_same_inode_readonly_record_lock_material_and_raw_outputs(self):
        before = inputs.sha(self.image)
        result = self.verify("actual-read")
        self.assertEqual(inputs.sha(self.image), before)
        self.assertEqual(len(result["actual_files"]), 2)
        self.assertTrue(result["readonly_extraction"])
        for key in ("native_execution_verified", "g2_complete", "production_ready"):
            self.assertFalse(result[key], key)
        for path in (self.root / "actual-read").glob("[0-9][0-9][0-9].json"):
            record = json.loads(path.read_bytes())
            self.assertNotIn("-w", record["argv"])
            self.assertEqual(record["argv"][-1], "/proc/self/fd/" + str(record["pass_fds"][0]))
            for stream in ("stdout", "stderr"):
                self.assertEqual(inputs.sha(Path(record[stream]["path"])), record[stream]["sha256"])

    def test_actual_root_witness_file_cannot_be_writable_by_the_host_owner(self):
        name = self.expected[0]["filename"]
        path = disk_fixture.physical.Disk.physical(witness.DIRECTORY + "/" + name)
        self.mutate("set_inode_field " + path + " uid 60001")
        before = inputs.sha(self.image)
        with self.assertRaises(ValueError):
            self.verify("actual-owner-refusal")
        self.assertEqual(inputs.sha(self.image), before)

    def test_actual_material_and_missing_witness_are_not_replaced_by_transcript_values(self):
        changed = copy.deepcopy(self.expected)
        self.expected[0]["material_sha256"] = hashlib.sha256(b"different inert bytes").hexdigest()
        with self.assertRaisesRegex(ValueError, "physical bytes"):
            self.verify("actual-material-refusal")
        self.expected = changed
        path = disk_fixture.physical.Disk.physical(witness.DIRECTORY + "/" + changed[0]["filename"])
        self.mutate("rm " + path)
        with self.assertRaisesRegex(ValueError, "missing, unexpected"):
            self.verify("actual-absence-refusal")

    def test_old_crash_candidate_is_selected_only_by_exact_physical_canonical_proof(self):
        candidate = self.records.authorities["recovery"]["writer"]
        proof = copy.deepcopy(self.records.authorities["recovery"]["proof"])
        proof["claims"]["issuer_id"] = fixed.SIGNER
        proof_hash = types.sha(proof)
        current = copy.deepcopy(self.records.event("activation_recovery_prepared")["reconciliation"]["previous"])
        current["head"]["writer_binding"].update(authority_grant_digest=proof_hash,
            fencing_token_digest=hashlib.sha256(hashlib.sha256(b"hepta:production-authority-token-grant:v2\0"
                + proof_hash.encode() + proof["signature_hex"].encode()).digest()).hexdigest())
        owner = {"role": "recovery", "pid": 4, "agent_id": fixed.AGENT, "spawn_generation": candidate["spawn_generation"],
                 "writer_proof_sha256": proof_hash, "current": current}
        payload = json.loads(self.expected[0]["durable_payload_json"])
        pending = witness.pending_final_canonical(self.records.event("owner_released")["current"],
            payload["root"], payload["peer"], self.expected[0]["material_sha256"], owner)
        root_lease = self.records.authorities["recovery"]["root"]
        registry = {"authority_epoch": 7, "store_revision": 3,
                    "leases": {lease["lease_id"]: lease for lease in (root_lease, candidate["authority_lease"])},
                    "revocations": {}, "retired_revisions": {}}
        issuer = {"signer_id": fixed.SIGNER, "policies": [],
                  "head": {"authority_epoch": 7, "revision": 1, "revoked_grant_ids": []},
                  "sequence": proof["claims"]["sequence"], "writer_authorization": proof}
        def install_json(path, value, label):
            self.directory(str(Path(path).parent))
            source = self.root / label
            source.write_bytes(e.canonical(value).encode())
            self.install(source, path)
        registry_path = fixed.AUTHORITY + "/leases/authority-leases.json"
        install_json(registry_path, {"schema_version": 2, "owner_id": "root-authority-leases-v1", "state": registry}, "inert-registry")
        install_json(fixed.AUTHORITY + "/" + authority.frontier_name("root-authority-leases-v1"),
                     {"schema": 1, "owner_id": "root-authority-leases-v1", "frontier": authority.lease_frontier(registry)}, "inert-registry-frontier")
        issuer_path = fixed.AUTHORITY + "/issuer/" + authority.frontier_name("local-final-use-issuer")
        wrapper = {"schema": 1, "owner_id": "local-final-use-issuer", "frontier": issuer}
        install_json(issuer_path, wrapper, "inert-canonical")
        with physical.physical.Disk(self.image, inputs.sha(self.image), self.tool, self.tool_identity,
                                    self.root / "actual-canonical-selection") as disk:
            selected, receipt = physical.resolve_final_canonical(disk, pending)
        self.assertEqual(selected["observation_id"], self.expected[0]["observation_id"])
        self.assertEqual(receipt["writer_proof_sha256"], proof_hash)
        self.assertFalse(receipt["private_key_bytes_read_or_exported"])
        issuer["writer_authorization"]["claims"]["issuer_id"] = "different-inert-issuer"
        self.mutate("rm " + disk_fixture.physical.Disk.physical(issuer_path))
        install_json(issuer_path, wrapper, "inert-canonical-changed")
        with physical.physical.Disk(self.image, inputs.sha(self.image), self.tool, self.tool_identity,
                                    self.root / "actual-canonical-refusal") as disk, self.assertRaisesRegex(ValueError, "another original issuer"):
            physical.resolve_final_canonical(disk, pending)


if __name__ == "__main__":
    unittest.main()
