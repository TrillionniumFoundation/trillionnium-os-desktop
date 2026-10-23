"""Host regressions only: no phone, helper, UI, issuer or production writer."""

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from support.android import device_organ as adapter
from support.android import device_organ_transport as transport


def process_reply(value, returncode=0, stderr=b""):
    return transport.ProcessReply(returncode, transport.canonical_bytes(value), stderr)


def cell_status():
    return {
        "ok": True, "backend": "droidloom-teto-digitalis-derived", "running": True,
        "host_pid": 101, "android_init_host_pid": 202, "boot_completed": "1",
        "android": "17", "sdk": "37", "native_bridge": "fixture_bridge.so",
        "berberis_flags": "fixture", "adbd": "stopped", "adb_tcp_port": "-1",
        "persist_adb_tcp_port": "-1", "usb_config": "none", "persist_usb_config": "none",
    }


def qualification():
    return {"qualified": True, "identity": {"android_init_host_pid": 202},
            "identity_sha256": "a" * 64}


def observed_result():
    window = {"package": "org.example.notes", "activity": "org.example.notes.Main",
              "window_token": "abc123", "display_id": 0,
              "window_bounds": [0, 0, 100, 200], "android_init_host_pid": 202}
    screenshot = {
        "source": "android_screencap", "width": 100, "height": 200,
        "scope_bounds": [0, 0, 100, 200],
        "scope": {**window, "accessibility_mode": "none"},
        "context_token": adapter.window_context(window, [0, 0, 100, 200], [100, 200]),
        "frame_sha256": "b" * 64, "scope_sha256": "c" * 64,
        "captured_unix_ms": 1_700_000_000_000, "atomic_snapshot": False,
    }
    return {"ok": True, "screenshot": screenshot,
            "native": {"nodes": [{"text": "private fixture text", "id": "org.example.notes:id/editor"}]}}


def observation():
    result = observed_result()
    return adapter.project_observation(result, "d" * 64, qualification(), "org.example.notes")


class DeviceOrganTests(unittest.TestCase):
    def make_adapter(self):
        return adapter.AndroidDeviceAdapter("e" * 64, timeout_seconds=2)

    def test_identity_probe_executes_only_two_fixed_read_commands(self):
        calls = []
        replies = [process_reply({"state": "running", "message": "Android is ready", "host_pid": 101}),
                   process_reply(cell_status())]
        def run(argv, stdin, timeout):
            calls.append((argv, stdin, timeout))
            return replies.pop(0)
        with patch.object(transport.PinnedTool, "measure", return_value={"source": "fixture"}), \
                patch.object(adapter, "run_bounded", side_effect=run):
            report = self.make_adapter().qualify()
        self.assertTrue(report["qualified"])
        self.assertEqual(calls, [
            ([adapter.CTL_PATH, "status", "--json"], b"", 2),
            (["/usr/bin/sudo", "-n", adapter.HELPER_PATH], b'{"op":"status"}\n', 2),
        ])
        self.assertFalse(report["ui_observation_executed"])
        self.assertFalse(report["production_authority"])
        self.assertFalse(report["physical_handset_verified"])
        self.assertEqual(report["device_mutation_attempts"], 0)

    def test_identity_mismatch_and_adb_reenable_never_qualify(self):
        for key, changed in [("host_pid", 303), ("sdk", "36"), ("adbd", "running"),
                             ("usb_config", "mtp,adb"), ("adb_tcp_port", "5555")]:
            status = cell_status()
            status[key] = changed
            with self.subTest(key=key), \
                    patch.object(transport.PinnedTool, "measure", return_value={}), \
                    patch.object(adapter, "run_bounded", side_effect=[
                        process_reply({"state": "running", "message": "Android is ready", "host_pid": 101}),
                        process_reply(status),
                    ]) as run:
                report = self.make_adapter().qualify()
                self.assertFalse(report["qualified"])
                self.assertEqual(run.call_count, 2)

    def test_effects_and_unknown_arguments_are_rejected_before_privileged_call(self):
        requests = [
            ({"op": "click", "selector": {"text": "Confirm"}}, "EFFECT_OWNER_NOT_CONFIGURED"),
            ({"op": "set-text", "value": "中文"}, "EFFECT_OWNER_NOT_CONFIGURED"),
            ({"op": "commit-text", "value": "中文"}, "COMMIT_TEXT_NOT_CONFIGURED"),
            ({"op": "launch", "package": "org.example.notes"}, "EFFECT_OWNER_NOT_CONFIGURED"),
            ({"op": "status", "shell": "anything"}, "UNKNOWN_ARGUMENT"),
            ({"op": "observe", "package": "org.example.notes", "display": 0,
              "with_png": False, "accessibility_mode": "touch-exploration"}, "READ_ONLY_PROFILE_REQUIRED"),
        ]
        for request, code in requests:
            with self.subTest(request=request), patch.object(adapter, "run_bounded") as run:
                with self.assertRaises(transport.AdapterError) as failed:
                    self.make_adapter().read_helper(request)
                self.assertEqual(failed.exception.code, code)
                self.assertFalse(failed.exception.attempted)
                run.assert_not_called()

    def test_helper_timeout_error_is_unknown_without_retry_or_private_log(self):
        reply = transport.ProcessReply(2, b"", b'{"ok":false,"error":"TIMEOUT","outcome_unknown":true,"automatic_retry":false}')
        with patch.object(transport.PinnedTool, "measure", return_value={}), \
                patch.object(adapter, "run_bounded", return_value=reply) as run:
            with self.assertRaises(transport.AdapterError) as failed:
                self.make_adapter().read_helper({"op": "status"})
        self.assertEqual(run.call_count, 1)
        self.assertTrue(failed.exception.receipt()["outcome_unknown"])
        self.assertFalse(failed.exception.receipt()["automatic_retry"])
        self.assertNotIn("stderr", failed.exception.receipt())

    def test_ok_with_unknown_or_malformed_json_never_becomes_completed(self):
        replies = [process_reply({"ok": True, "outcome_unknown": True}),
                   transport.ProcessReply(0, b'{"ok":true,"ok":false}', b""),
                   transport.ProcessReply(0, b'{"ok":true,"v":NaN}', b""),
                   transport.ProcessReply(0, b'\xff', b"")]
        for reply in replies:
            with self.subTest(reply=reply), self.assertRaises(transport.AdapterError) as failed:
                adapter.helper_reply(reply)
            self.assertTrue(failed.exception.outcome_unknown)
            self.assertTrue(failed.exception.attempted)

    def test_invalid_status_after_submission_preserves_unknown_attempt(self):
        status = cell_status()
        status["sdk"] = 37
        with patch.object(transport.PinnedTool, "measure", return_value={}), \
                patch.object(adapter, "run_bounded", side_effect=[
                    process_reply({"state": "running", "message": "Android is ready", "host_pid": 101}),
                    process_reply(status),
                ]) as run:
            with self.assertRaises(transport.AdapterError) as failed:
                self.make_adapter().qualify()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(failed.exception.code, "INVALID_DEVICE_STATUS")
        self.assertTrue(failed.exception.attempted)
        self.assertTrue(failed.exception.outcome_unknown)

    def test_invalid_observation_after_submission_preserves_unknown_attempt(self):
        result = observed_result()
        result["screenshot"]["scope"]["window_token"] = "abc124"
        client = self.make_adapter()
        with patch.object(client, "qualify", return_value=qualification()), \
                patch.object(transport.PinnedTool, "measure", return_value={}), \
                patch.object(adapter, "run_bounded", return_value=process_reply(result)) as run:
            with self.assertRaises(transport.AdapterError) as failed:
                client.observe("org.example.notes")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(failed.exception.code, "WINDOW_CONTEXT_HASH_MISMATCH")
        self.assertTrue(failed.exception.attempted)
        self.assertTrue(failed.exception.outcome_unknown)

    def test_observation_keeps_bound_hashes_without_private_tree(self):
        result = observation()
        self.assertNotIn("private fixture text", json.dumps(result))
        self.assertEqual(result["native_snapshot_sha256"], adapter.hash_json(observed_result()["native"]))
        self.assertEqual(result["window"]["window_token"], "abc123")
        self.assertFalse(result["atomic_snapshot"])
        self.assertEqual(result["authority"], "none")

    def test_window_drift_and_changed_cell_reject_projection(self):
        cases = [("window_token", "abc124"), ("android_init_host_pid", 203),
                 ("package", "org.other.notes"), ("display_id", 1)]
        for field, value in cases:
            result = observed_result()
            result["screenshot"]["scope"][field] = value
            with self.subTest(field=field), self.assertRaises(transport.AdapterError):
                adapter.project_observation(result, "d" * 64, qualification(), "org.example.notes")

    def test_chinese_intent_retains_exact_utf8_bytes_and_complete_binding(self):
        value = "中文输入😀\n第二行"
        with patch.object(adapter, "run_bounded") as run:
            intent = adapter.prepare_semantic_intent(
                observation(), "operation/one", "set-text",
                {"id": "org.example.notes:id/editor", "editable": True}, value)
        raw = transport.canonical_bytes(intent["payload"])
        self.assertIn(value.split("\n")[0].encode("utf-8"), raw)
        self.assertEqual(json.loads(raw)["value"], value)
        self.assertEqual(intent["payload_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(intent["payload"]["window"], observation()["window"])
        self.assertEqual(intent["payload"]["raw_observation_sha256"], "d" * 64)
        self.assertEqual(intent["dispatch_status"], "NOT_CONFIGURED")
        run.assert_not_called()

    def test_changed_token_cannot_reuse_an_old_window_context(self):
        stale = observation()
        stale["window"]["window_token"] = "abc124"
        with self.assertRaises(transport.AdapterError) as failed:
            adapter.prepare_semantic_intent(stale, "operation/one", "click", {"text": "Confirm"})
        self.assertEqual(failed.exception.code, "WINDOW_CONTEXT_HASH_MISMATCH")

    def test_frame_or_selector_change_alters_exact_intent_digest(self):
        original = observation()
        first = adapter.prepare_semantic_intent(original, "operation/one", "click", {"text": "Confirm"})
        changed = copy.deepcopy(original)
        changed["frame_sha256"] = "f" * 64
        second = adapter.prepare_semantic_intent(changed, "operation/one", "click", {"text": "Confirm"})
        third = adapter.prepare_semantic_intent(original, "operation/one", "click", {"text": "Cancel"})
        self.assertEqual(len({first["payload_sha256"], second["payload_sha256"], third["payload_sha256"]}), 3)

    def test_intent_rejects_malformed_geometry_even_with_recomputed_context(self):
        original = observation()
        for field, value in [("display_id", True), ("android_init_host_pid", 0),
                             ("window_bounds", [0, 0, 101, 200]), ("activity", "")]:
            changed = copy.deepcopy(original)
            changed["window"][field] = value
            changed["context_token"] = adapter.window_context(
                changed["window"], changed["scope_bounds"], changed["screen_size"])
            with self.subTest(field=field), self.assertRaises(transport.AdapterError):
                adapter.prepare_semantic_intent(changed, "operation/one", "click", {"text": "Confirm"})
        intent = adapter.prepare_semantic_intent(original, "operation/one", "click", {"text": "Confirm"})
        original["window"]["window_bounds"][0] = 1
        original["scope_bounds"][0] = 1
        self.assertEqual(intent["payload"]["window"]["window_bounds"][0], 0)
        self.assertEqual(intent["payload"]["scope_bounds"][0], 0)
        self.assertEqual(intent["selector_resolution"], "NOT_EXECUTED")

    def test_ambiguous_unscoped_and_unsupported_intents_fail_before_transport(self):
        selectors = [{"editable": True}, {"contains": "Confirm"}, {"text": ""},
                     {"text": "Confirm", "package": "org.other.notes"}, {"text": "Confirm", "index": 0}]
        with patch.object(adapter, "run_bounded") as run:
            for selector in selectors:
                with self.subTest(selector=selector), self.assertRaises(transport.AdapterError):
                    adapter.prepare_semantic_intent(observation(), "operation/one", "click", selector)
            with self.assertRaises(transport.AdapterError):
                adapter.prepare_semantic_intent(observation(), "operation/one", "set-text", {"id": "editor"}, "中" * 1366)
            with self.assertRaises(transport.AdapterError) as failed:
                adapter.prepare_semantic_intent(observation(), "operation/one", "commit-text", {"id": "editor"}, "中文")
            self.assertEqual(failed.exception.code, "COMMIT_TEXT_NOT_CONFIGURED")
            run.assert_not_called()


class DeviceProcessTests(unittest.TestCase):
    def test_actual_child_preserves_one_complete_json_reply(self):
        reply = transport.run_bounded(
            [sys.executable, "-c", "import sys; raw=sys.stdin.buffer.read(); sys.stdout.buffer.write(raw)"],
            '{"value":"中文😀"}\n'.encode(), 2)
        self.assertEqual(reply.returncode, 0)
        self.assertEqual(transport.parse_object(reply.stdout), {"value": "中文😀"})

    def test_actual_child_timeout_has_one_attempt_and_no_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "attempts"
            program = "import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); p.write_text('one'); time.sleep(30)"
            with self.assertRaises(transport.AdapterError) as failed:
                transport.run_bounded([sys.executable, "-c", program, str(marker)], b"", 1)
            self.assertEqual(marker.read_text(), "one")
            self.assertEqual(failed.exception.code, "TIMEOUT")
            self.assertTrue(failed.exception.outcome_unknown)
            self.assertFalse(failed.exception.receipt()["automatic_retry"])

    def test_actual_child_output_is_bounded(self):
        with self.assertRaises(transport.AdapterError) as failed:
            transport.run_bounded([sys.executable, "-c", "import sys; sys.stdout.write('x' * 2000000)"], b"", 2)
        self.assertEqual(failed.exception.code, "REPLY_TOO_LARGE")
        self.assertTrue(failed.exception.outcome_unknown)

    def test_timeout_cleans_pipe_holder_after_group_leader_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "descendant"
            program = """import os,pathlib,sys,time
if os.fork() == 0:
    pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))
    time.sleep(30)
else:
    os._exit(0)
"""
            with self.assertRaises(transport.AdapterError) as failed:
                transport.run_bounded([sys.executable, "-c", program, str(marker)], b"", 1)
            self.assertEqual(failed.exception.code, "TIMEOUT")
            pid = int(marker.read_text())
            state_path = Path(f"/proc/{pid}/stat")
            deadline = time.monotonic() + 1
            while state_path.exists():
                try:
                    state = state_path.read_text().split(") ", 1)[1].split()[0]
                except FileNotFoundError:
                    break
                if state in ("Z", "X"):
                    break
                if time.monotonic() >= deadline:
                    os.kill(pid, 9)
                    self.fail("transport descendant remained runnable after timeout")
                time.sleep(0.01)

    def test_pinned_file_rejects_replacement_symlink_and_writable_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "tool"
            source.write_bytes(b"#!/usr/bin/python3\npass\n")
            source.chmod(0o755)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            pin = transport.PinnedTool(str(source), digest, owner_uid=os.getuid())
            self.assertEqual(pin.measure()["sha256"], digest)
            source.write_bytes(b"#!/usr/bin/python3\nprint('changed')\n")
            with self.assertRaises(transport.AdapterError) as failed:
                pin.measure()
            self.assertEqual(failed.exception.code, "TOOL_PIN_MISMATCH")
            source.chmod(0o777)
            with self.assertRaises(transport.AdapterError) as failed:
                pin.measure()
            self.assertEqual(failed.exception.code, "UNTRUSTED_TOOL_FILE")
            link = Path(directory) / "symlink"
            link.symlink_to(source)
            with self.assertRaises(transport.AdapterError):
                transport.PinnedTool(str(link), digest, owner_uid=os.getuid()).measure()
            fifo = Path(directory) / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(transport.AdapterError) as failed:
                transport.PinnedTool(str(fifo), digest, owner_uid=os.getuid()).measure()
            self.assertEqual(failed.exception.code, "UNTRUSTED_TOOL_FILE")


if __name__ == "__main__":
    unittest.main()
