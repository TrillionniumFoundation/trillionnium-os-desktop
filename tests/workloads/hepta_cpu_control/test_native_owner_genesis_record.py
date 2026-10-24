"""Inert schema records only; no original Root or native effect runs here."""
import copy
import hashlib
import struct
import unittest

import native_owner_evidence as e
import native_owner_genesis_record as genesis
import native_owner_prior_boot_types as fixed


BOOT = list(range(1, 17))
SPACES = {"manager": [17] * 16, "recovery": [18] * 16}
ROOT = {"uid": 0, "pid": 1, "boot_id": fixed.uuid(BOOT), "process_start_ticks": 27}
CUT = {"profile": "hepta:cognitive:exact-current-cut:v1", "owner_agent_id": fixed.AGENT,
       "schema_digest": "a1" * 32, "state_digest": "b2" * 32}
KEY = [19] * 32


def record():
    policies = [{"subject_id": fixed.AGENT, "destination_id": "hos2.cpu-budget.v1",
                 "scope_sha256": list(hashlib.sha256(b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(BOOT)
                     + bytes(SPACES[name]) + struct.pack("<QQ", 2, 1)).digest()), "lifetime_ms": 5000}
                for name in ("manager", "recovery")]
    return {"schema_version": 1, "initial_root": copy.deepcopy(ROOT), "initial_cut": copy.deepcopy(CUT),
            "issuer_id": fixed.SIGNER, "verifying_key": list(KEY), "policies": policies}


def encode(value):
    return e.canonical({"schema_version": 1, "observation_id": genesis.identity(),
                        "payload": list(e.canonical(value).encode())}).encode()


def inspect(raw):
    return genesis.inspect(raw, expected_root=ROOT, expected_anchor=CUT, expected_key=KEY, boot=BOOT, spaces=SPACES)


class OriginalGenesisRecordTests(unittest.TestCase):
    def test_exact_original_record_never_produces_a_current_or_native_qualification(self):
        raw = encode(record())
        checked = inspect(raw)
        self.assertEqual(checked["record_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(checked["payload"]["initial_cut"], CUT)
        self.assertFalse(checked["checkpoint_or_current_created"])
        self.assertFalse(checked["native_execution_verified"])
        self.assertNotIn("passed", checked)
        self.assertNotIn("head", checked["payload"])

    def test_fake_head_zero_unknown_fields_and_wrapper_reencoding_are_rejected(self):
        for name, value in (("head", {"counter": 0}), ("current", None), ("writer_reservation", None)):
            with self.subTest(name=name), self.assertRaises(ValueError):
                inspect(encode({**record(), name: value}))
        with self.assertRaises(ValueError):
            inspect(encode(record()) + b"\n")
        changed = record()
        changed["schema_version"] = True
        with self.assertRaises(ValueError):
            inspect(encode(changed))

    def test_replaced_root_key_material_or_initial_namespace_is_rejected(self):
        mutations = [("root", lambda v: v["initial_root"].update(process_start_ticks=28)),
                     ("key", lambda v: v["verifying_key"].__setitem__(0, 20)),
                     ("material", lambda v: v["initial_cut"].update(state_digest="a0" * 32)),
                     ("namespace", lambda v: v["policies"][0].update(scope_sha256=[21] * 32)),
                     ("lifetime", lambda v: v["policies"][0].update(lifetime_ms=6000))]
        for name, mutate in mutations:
            changed = record()
            mutate(changed)
            with self.subTest(name=name), self.assertRaises(ValueError):
                inspect(encode(changed))


if __name__ == "__main__":
    unittest.main()
