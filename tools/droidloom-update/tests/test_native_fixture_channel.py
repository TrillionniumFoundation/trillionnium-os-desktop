"""Pure protocol rejection tests; these fixtures confer no runtime credit."""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "resources/native-leaves/cp3a-20261126-apps-r2/native_leaf_channel.py"
SPEC = importlib.util.spec_from_file_location("fixture_channel_under_test", SOURCE)
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


def encoded(value):
    body = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
    return b"Result: Bundle[{reply=" + base64.b64encode(body) + b"}]\n"


def observed(kind="saf", terminal=True):
    spec = C.FIXTURE_PINS[kind]
    uid = 10345
    context = "u:r:untrusted_app_32:s0:c89,c257,c512,c768"
    raw = context.encode() + (b"\0" if terminal else b"")
    ce = [5, 71, stat.S_IFDIR | 0o700, uid, uid]
    de = [5, 72, stat.S_IFDIR | 0o700, uid, uid]
    value = {
        "schema": "droidloom.owned-fixture-state.v1", "package": spec["package"],
        "run": spec["run_id"], "uid": uid, "pid": 2345, "caller_uid": 2000,
        "ce": ce, "de": de, "prefs": None,
        "process_selinux": {"value": context, "bytes": len(raw),
                            "sha256": hashlib.sha256(raw).hexdigest(), "terminal_nul": terminal},
        "started_elapsed_ns": 100, "finished_elapsed_ns": 200,
        "state_mutated": False, "activity_started": False,
    }
    data = {"directories": [{}, {}, *[
        dict(zip(("device", "inode", "mode", "host_uid", "host_gid"), row))
        for row in (ce, de)]]}
    return value, spec, {"uid": uid}, data


class FixedFixtureProtocolTests(unittest.TestCase):
    def test_actual_self_context_digest_and_optional_kernel_terminator(self):
        for kind in C.FIXTURE_PINS:
            for terminal in (False, True):
                value, spec, app, data = observed(kind, terminal)
                actual, body = C.validate_fixture_state(encoded(value), spec, app, data)
                self.assertEqual(actual, value)
                self.assertIsNone(body)

    def test_provider_reply_cannot_choose_another_uid_inode_package_or_capability(self):
        original, spec, app, data = observed()
        mutations = [
            lambda v: v.update(package="other.package"),
            lambda v: v.update(uid=app["uid"] + 1),
            lambda v: v.update(caller_uid=0),
            lambda v: v.update(activity_started=True),
            lambda v: v.update(state_mutated=True),
            lambda v: v.update(extra="unreviewed"),
            lambda v: v["ce"].__setitem__(1, 999),
            lambda v: v["de"].__setitem__(4, 0),
            lambda v: v.update(finished_elapsed_ns=16_000_000_101),
        ]
        for mutate in mutations:
            value = copy.deepcopy(original)
            mutate(value)
            with self.assertRaises(RuntimeError):
                C.validate_fixture_state(encoded(value), spec, app, data)

    def test_label_text_without_matching_actual_bytes_or_selected_domain_is_rejected(self):
        original, spec, app, data = observed()
        for context in (
            "u:r:untrusted_app:s0:c1,c2,c513,c769",
            "u:r:untrusted_app_32:s0:c1,c1,c513,c769",
            "u:r:untrusted_app_32:s0:c2,c1,c513,c769",
            "u:r:untrusted_app_32:s0:c01,c2,c513,c769",
            "u:r:untrusted_app_32:s0:c1,c2,c513,c1024",
            "u:r:untrusted_app_32:s0:c1,c2,c513,c769\0",
            "u:r:untrusted_app_32:s0:c90,c257,c512,c768",
        ):
            value = copy.deepcopy(original)
            raw = context.encode() + b"\0"
            value["process_selinux"].update(value=context, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            with self.assertRaises(RuntimeError):
                C.validate_fixture_state(encoded(value), spec, app, data)
        for key, substitute in (("bytes", 1), ("sha256", "0" * 64), ("terminal_nul", False)):
            value = copy.deepcopy(original)
            value["process_selinux"][key] = substitute
            with self.assertRaises(RuntimeError):
                C.validate_fixture_state(encoded(value), spec, app, data)

    def test_preference_is_one_complete_fixed_file_owned_by_actual_app(self):
        value, spec, app, data = observed()
        body = ("<map><string name=\"run\">" + spec["run_id"] + "</string></map>").encode()
        prefs = {"name": spec["preference"], "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                 "base64": base64.b64encode(body).decode(),
                 "metadata": [5, 81, stat.S_IFREG | 0o600, app["uid"], app["uid"], 1, len(body), 1, 0, 1, 0]}
        value["prefs"] = prefs
        self.assertEqual(C.validate_fixture_state(encoded(value), spec, app, data)[1], body)
        for key, substitute in (("name", "other.xml"), ("bytes", len(body) - 1), ("sha256", "0" * 64)):
            changed = copy.deepcopy(value)
            changed["prefs"][key] = substitute
            with self.assertRaises(RuntimeError):
                C.validate_fixture_state(encoded(changed), spec, app, data)
        for index, substitute in ((0, 6), (3, 0), (5, 2), (6, len(body) + 1)):
            changed = copy.deepcopy(value)
            changed["prefs"]["metadata"][index] = substitute
            with self.assertRaises(RuntimeError):
                C.validate_fixture_state(encoded(changed), spec, app, data)

    def test_stock_bundle_envelope_has_no_second_result_or_trailing_bytes(self):
        value, spec, app, data = observed()
        raw = encoded(value)
        for wrong in (raw + b"\n", raw + raw, raw[:-1], raw.replace(b"reply=", b"other="), b" "+raw):
            with self.assertRaises((RuntimeError, ValueError)):
                C.validate_fixture_state(wrong, spec, app, data)

    def test_only_two_fixed_existing_phase_pairs_receive_install_retire_reserve(self):
        self.assertEqual(C.fixture_phase_budget(600, 120), (1741, 686))
        self.assertEqual(C.fixture_phase_budget(750, 150), (1891, 716))
        for pair in ((750, 120), (600, 150), (601, 120), (1, 1), (999999, 999999)):
            with self.assertRaises(RuntimeError):
                C.fixture_phase_budget(*pair)


if __name__ == "__main__":
    unittest.main()
