"""Offline boundary tests. All device/cell/UI functions are synthetic doubles.

The generated helper is assembled in memory from the pinned original helper
and the candidate extension. No privileged helper, APK or device is invoked.
ORGAN_TEST_SUBJECT selects the unchanged extension for an offline red run.
It is test harness configuration, not a product qualification switch.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import types
import unittest

from support.android.receiver import build_receiver


RECEIVER = build_receiver.ROOT
GENERATION = {"boot_id": "synthetic-boot", "init_start_ticks": "123",
              "mount_namespace": "mnt:[1]", "pid_namespace": "pid:[2]",
              "time_namespace": "time:[3]"}


def encoded_request(op="organ-set-text", observation_extra=None):
    observation = {
        "generation": GENERATION,
        "window": {"package": "com.example.settings"},
        "target": {"resource_id": "com.example.settings:id/search"},
    }
    observation.update(observation_extra or {})
    payload = {"schema_version": 1, "action": "set_text",
               "operation_id": "offline.boundary.test",
               "destination_id": "pocket4.android:" + "0" * 64,
               "observation": observation, "value": "离线测试😀",
               "expires_elapsed_ms": 125000}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode()
    return {"op": op, "payload_base64": base64.b64encode(raw).decode(),
            "payload_sha256": hashlib.sha256(raw).hexdigest()}


class HelperHarness:
    def __init__(self, receiver="legacy", injected_globals=None):
        original = (RECEIVER / "upstream/android_app.py").read_bytes()
        if hashlib.sha256(original).hexdigest() != build_receiver.PREIMAGES["android_app.py"]:
            raise RuntimeError("original helper source pin mismatch")
        subject = Path(os.environ.get("ORGAN_TEST_SUBJECT", RECEIVER / "organ_extension.py"))
        extension = subject.read_text()
        marker = "def dispatch(r):\n"
        source = original.decode()
        if source.count(marker) != 1:
            raise RuntimeError("original dispatch marker changed")
        source = source.replace(marker, extension + "\n\n" + marker
                                + "    if r.get('op') in ('organ-observe','organ-set-text','organ-readback'):return _organ_dispatch(r)\n", 1)
        self.ns = {"__name__": "offline_helper_subject"}
        exec(compile(source, str(subject), "exec"), self.ns)
        self.calls = []
        self.ui_requests = []
        self.effects = []
        harness = self

        class Cell:
            def __init__(self):
                harness.calls.append("cell")
                self.generation = GENERATION
                self.deadline = 155.0

            def run(self, *args, **kwargs):
                raise AssertionError("No Android transport may run in an offline test")

            def close(self):
                harness.calls.append("close")

        def ui(request):
            harness.calls.append("ui")
            harness.ui_requests.append(copy.deepcopy(request))
            if request["op"] != "find":
                harness.effects.append(request["op"])
            if receiver == "unknown":
                raise RuntimeError("synthetic unknown receiver")
            if receiver == "legacy":
                # An old APK ignores top-level organ, acts on legacy op/value,
                # and returns no strict protocol. This double exposes late checks.
                return {"ok": True, "performed": request["op"],
                        "readback_verified": request["op"] == "set-text"}
            reply = {"ok": True, "organ_protocol": "pocket4-bound-text-v1",
                     "receiver_generation": GENERATION}
            if request["organ"]["mode"] != "observe":
                payload = json.loads(base64.b64decode(request["organ"]["payload_base64"]))
                reply.update(operation_id=payload["operation_id"],
                             payload_sha256=request["organ"]["payload_sha256"])
            return reply

        self.ns.update(_OrganCell=Cell, ui=ui,
                       time=types.SimpleNamespace(CLOCK_BOOTTIME=1,
                                                  clock_gettime=lambda _: 100.0))
        self.ns.update(injected_globals or {})

    def dispatch(self, request):
        return self.ns["dispatch"](request)


class EffectBoundaryTests(unittest.TestCase):
    def assert_no_effect_path(self, harness):
        self.assertEqual(harness.calls, [], "must reject before cell discovery or UI")
        self.assertEqual(harness.ui_requests, [])
        self.assertEqual(harness.effects, [])

    def assert_denied(self, harness, request):
        with self.assertRaises(harness.ns["ControlError"]) as raised:
            harness.dispatch(request)
        self.assertEqual(str(raised.exception), "ORGAN_EFFECT_RECEIVER_NOT_QUALIFIED")
        self.assertEqual(raised.exception.details, {
            "action_taken": False, "action_submitted": False,
            "outcome_unknown": False, "automatic_retry": False})
        self.assert_no_effect_path(harness)

    def test_legacy_apk_cannot_receive_effect_probe(self):
        self.assert_denied(HelperHarness("legacy"), encoded_request())

    def test_unknown_receiver_cannot_receive_effect_probe(self):
        self.assert_denied(HelperHarness("unknown"), encoded_request())

    def test_strict_looking_reply_cannot_qualify_before_submission(self):
        self.assert_denied(HelperHarness("strict"), encoded_request())

    def test_nested_forged_qualification_does_not_enable_effect(self):
        request = encoded_request(observation_extra={
            "receiver_qualified": True, "same_signer": True,
            "organ": {"qualified": True, "organ_protocol": "pocket4-bound-text-v1"}})
        self.assert_denied(HelperHarness("strict"), request)

    def test_forged_top_level_organ_fields_fail_without_ui(self):
        for key, value in [("organ", {"qualified": True}),
                           ("receiver_qualified", True),
                           ("installed_receiver_sha256", "f" * 64),
                           ("same_signer", True)]:
            with self.subTest(field=key):
                harness = HelperHarness("strict")
                request = encoded_request()
                request[key] = value
                with self.assertRaises(harness.ns["ControlError"]) as raised:
                    harness.dispatch(request)
                self.assertEqual(str(raised.exception), "UNKNOWN_ORGAN_ARGUMENT")
                self.assert_no_effect_path(harness)

    def test_unreviewed_globals_cannot_enable_effect(self):
        self.assert_denied(HelperHarness("strict", {
            "ORGAN_EFFECT_RECEIVER_QUALIFIED": True,
            "_organ_receiver_qualified": lambda *_: True}), encoded_request())

    def test_old_apk_observation_rejects_protocol_without_mutation(self):
        harness = HelperHarness("legacy")
        with self.assertRaises(harness.ns["ControlError"]) as raised:
            harness.dispatch({"op": "organ-observe", "package": "com.example.settings",
                              "resource_id": "com.example.settings:id/search"})
        self.assertEqual(str(raised.exception), "ORGAN_RECEIVER_UNQUALIFIED")
        self.assertEqual(harness.effects, [])
        self.assertEqual([r["op"] for r in harness.ui_requests], ["find"])

    def test_observe_remains_find_only(self):
        harness = HelperHarness("strict")
        reply = harness.dispatch({"op": "organ-observe", "package": "com.example.settings",
                                  "resource_id": "com.example.settings:id/search"})
        self.assertTrue(reply["ok"])
        self.assertEqual(harness.effects, [])
        self.assertEqual([r["op"] for r in harness.ui_requests], ["find"])
        self.assertNotIn("value", harness.ui_requests[0])

    def test_readback_remains_find_only_without_mutation_value(self):
        harness = HelperHarness("strict")
        reply = harness.dispatch(encoded_request("organ-readback"))
        self.assertEqual(reply["operation_id"], "offline.boundary.test")
        self.assertEqual(harness.effects, [])
        self.assertEqual([r["op"] for r in harness.ui_requests], ["find"])
        self.assertNotIn("value", harness.ui_requests[0])

    def test_readonly_cleanup_restores_original_transport(self):
        harness = HelperHarness("strict")
        original_arun = harness.ns["arun"]
        harness.dispatch(encoded_request("organ-readback"))
        self.assertIs(harness.ns["arun"], original_arun)
        self.assertEqual(harness.calls, ["cell", "ui", "close"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
