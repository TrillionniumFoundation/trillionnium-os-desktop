"""Local contracts and real temporary-file custody tests; never Android/SDK."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import firefox_adapter as a
import firefox_custody as c
import firefox_protocol as p


class OfflinePort:
    def __init__(self, mutate=None, fail=None):
        self.calls = []
        self.mutate, self.fail = mutate, fail
        self.binding = {"package": c.PACKAGE, "version_code": c.VERSION_CODE,
            "apk": {"bytes": c.APK_BYTES, "sha256": c.APK_SHA256}, "session": "offline-owned-session",
            "Main": "OFFLINE_FIXTURE_NOT_A_BASELINE", "epoch": "offline-epoch", "uid": 10123, "user": 0}
        self.task = 11
        self.tabs = ["owned-first"]
        self.tab = "owned-first"

    def reply(self, call, name=None, **extra):
        self.calls.append(call)
        if call == self.fail:
            error = RuntimeError("OFFLINE_INJECTED_LOST_ACK")
            error.outcome_unknown = True
            raise error
        value = {"binding": copy.deepcopy(self.binding), "session": self.binding["session"],
            "evidence_complete": True, "outcome_unknown": False, "automatic_retry": False,
            "task": self.task, "tab": self.tab, "owned_tabs": list(self.tabs),
            "user_history_read": False, "user_tab_enumeration": False, **extra}
        if name is not None:
            value.update(p.PAGES[name], heading_visible=True, normal_https_page=True,
                         network_error=False, certificate_warning=False)
        if self.mutate:
            self.mutate(call, value)
        return value

    def admit(self):
        return self.reply("admit", browser_ownership_proved=True, task_ownership_is_browser_ownership=False)

    def navigate(self, tab, name):
        assert tab == self.tab
        return self.reply("navigate-" + name, name)

    def back(self, tab):
        assert tab == self.tab
        return self.reply("back", "manifesto")

    def forward(self, tab):
        assert tab == self.tab
        return self.reply("forward", "history")

    def new_tab(self, name):
        self.tabs.append("owned-second")
        self.tab = "owned-second"
        return self.reply("new-tab", name)

    def close_tab(self, tab):
        assert tab == "owned-second"
        self.tabs = ["owned-first"]
        self.tab = "owned-first"
        return self.reply("close-tab", "history")

    def normal_close(self):
        return self.reply("normal-close", closed_task=self.task, owned_task_absent=True,
            other_tasks_preserved=True, normal_task_close=True, force_stop=False, clear_data=False)

    def reopen(self):
        self.task = 12
        return self.reply("reopen", "history", independent_launch=True)

    def cleanup(self):
        self.tabs = []
        return self.reply("cleanup", closed_task=self.task, owned_task_absent=True,
            other_tasks_preserved=True, force_stop=False, clear_data=False)

    def close_resources(self):
        self.calls.append("release-host-resources")
        return True


class ProtocolControls(unittest.TestCase):
    def rejected(self, phase, key, value):
        def mutate(call, row):
            if call == phase:
                row[key] = value
        port = OfflinePort(mutate)
        result = p.offline_control(port)
        self.assertFalse(result["protocol_control_passed"])
        self.assertFalse(result["finite_public_case_passed"])
        self.assertFalse(result["Android_execution_observed"])
        self.assertEqual(port.calls[-2:], [phase, "release-host-resources"])

    def test_complete_real_sequence_shape_but_offline_credit_only(self):
        port = OfflinePort()
        result = p.offline_control(port)
        self.assertTrue(result["protocol_control_passed"])
        self.assertEqual([r["id"] for r in result["steps"]], list(p.STEPS))
        self.assertEqual(port.calls, ["admit", "navigate-manifesto", "navigate-history", "back", "forward",
            "new-tab", "close-tab", "normal-close", "reopen", "cleanup", "release-host-resources"])
        for name in p.no_release_credit():
            self.assertIs(result[name], False)
        self.assertFalse(result["finite_public_case_passed"])
        self.assertFalse(result["cleanup_completed"])
        self.assertFalse(result["Android_execution_observed"])

    def test_offline_port_cannot_enter_production(self):
        port = OfflinePort()
        with self.assertRaises(c.Refused):
            p.execute(port)
        self.assertEqual(port.calls, [])

    def test_missing_real_browser_owner_refuses_before_main_or_ui(self):
        controller = types.SimpleNamespace(browser_owner=None)
        adapter = a.FirefoxFlowAdapter(controller)
        with patch.object(a.os, "getuid", return_value=0), patch.object(a.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(c.Refused, "BROWSER_SESSION_OWNERSHIP_PROVIDER_UNAVAILABLE"):
                adapter.admit()

    def test_task_claim_is_not_browser_ownership(self):
        self.rejected("admit", "task_ownership_is_browser_ownership", True)

    def test_unproved_browser_owner(self):
        self.rejected("admit", "browser_ownership_proved", False)

    def test_wrong_public_url(self):
        self.rejected("navigate-manifesto", "url", "https://example.invalid/")

    def test_wrong_heading(self):
        self.rejected("navigate-history", "heading", "Sign in")

    def test_insecure_page(self):
        self.rejected("forward", "normal_https_page", False)

    def test_certificate_warning(self):
        self.rejected("back", "certificate_warning", True)

    def test_existing_tab_contamination(self):
        self.rejected("navigate-manifesto", "owned_tabs", ["owned-first", "unrelated-user-tab"])

    def test_duplicate_second_tab(self):
        self.rejected("new-tab", "tab", "owned-first")

    def test_unscoped_history_read(self):
        self.rejected("forward", "user_history_read", True)

    def test_user_tab_enumeration(self):
        self.rejected("new-tab", "user_tab_enumeration", True)

    def test_force_stop_is_not_normal_close(self):
        self.rejected("normal-close", "force_stop", True)

    def test_same_task_is_not_independent_reopen(self):
        self.rejected("reopen", "task", 11)

    def test_reopen_must_restore_owned_page(self):
        self.rejected("reopen", "url", p.PAGES["manifesto"]["url"])

    def test_incomplete_cleanup(self):
        self.rejected("cleanup", "owned_tabs", ["owned-first"])

    def test_main_uid_and_epoch_changes_reject(self):
        for key, value in (("uid", 99999), ("epoch", "different"), ("Main", "replacement")):
            with self.subTest(key=key):
                def mutate(call, row):
                    if call == "back":
                        row["binding"][key] = value
                port = OfflinePort(mutate)
                result = p.offline_control(port)
                self.assertFalse(result["protocol_control_passed"])
                self.assertEqual(port.calls[-2:], ["back", "release-host-resources"])

    def test_lost_mutation_ack_no_retry_or_blind_android_cleanup(self):
        port = OfflinePort(fail="back")
        result = p.offline_control(port)
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertEqual(port.calls[-2:], ["back", "release-host-resources"])
        self.assertNotIn("cleanup", port.calls)
        self.assertFalse(result["automatic_retry"])


class CustodyControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="firefox-custody-control-")
        self.path = Path(self.temp.name) / "public-fixture.bin"
        self.body = (b"bounded public stream fixture\n" * 5000) + b"tail"
        self.path.write_bytes(self.body)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC)
        self.expected = c.identity(self.fd)
        self.sha = hashlib.sha256(self.body).hexdigest()

    def tearDown(self):
        os.close(self.fd)
        self.temp.cleanup()

    def test_actual_file_stream_uses_64k_reads_not_whole_body(self):
        requested = []
        real = os.read
        def read(fd, count):
            requested.append(count)
            return real(fd, count)
        with patch.object(c.os, "read", side_effect=read):
            value = c.stream_exact_fd(self.fd, self.expected, self.sha, time.monotonic() + 5)
        self.assertEqual(value["bytes"], len(self.body))
        self.assertEqual(value["sha256"], self.sha)
        self.assertGreater(len(requested), 2)
        self.assertLessEqual(max(requested), 65536)
        self.assertFalse(value["independent_signature_execution"])

    def test_wrong_hash_rejects_full_stream(self):
        with self.assertRaises(c.Refused):
            c.stream_exact_fd(self.fd, self.expected, "0" * 64, time.monotonic() + 5)

    def test_actual_held_file_change_rejects(self):
        self.path.write_bytes(self.body[:-1] + b"X")
        with self.assertRaises(c.Refused):
            c.stream_exact_fd(self.fd, self.expected, self.sha, time.monotonic() + 5)

    def test_same_content_wrong_inode_rejects(self):
        other = Path(self.temp.name) / "other.bin"
        other.write_bytes(self.body)
        fd = os.open(other, os.O_RDONLY)
        try:
            with self.assertRaises(c.Refused):
                c.stream_exact_fd(fd, self.expected, self.sha, time.monotonic() + 5)
        finally:
            os.close(fd)

    def test_extra_hardlink_rejects(self):
        os.link(self.path, Path(self.temp.name) / "alias.bin")
        with self.assertRaises(c.Refused):
            c.stream_exact_fd(self.fd, c.identity(self.fd), self.sha, time.monotonic() + 5)

    def test_elapsed_deadline_rejects_before_read(self):
        with patch.object(c.os, "read", side_effect=AssertionError("read after expiry")):
            with self.assertRaisesRegex(c.Refused, "DEADLINE"):
                c.stream_exact_fd(self.fd, self.expected, self.sha, time.monotonic() - 1)

    def test_unselected_large_body_refuses_before_target_access(self):
        target = types.SimpleNamespace(verify=lambda: self.fail("should not touch target"))
        for size, sha in ((c.APK_BYTES + 1, c.APK_SHA256), (c.APK_BYTES, "0" * 64)):
            with self.subTest(size=size, sha=sha):
                with self.assertRaisesRegex(c.Refused, "ONLY_CURRENT_QUALIFIED_FIREFOX_BODY"):
                    c.HeldFirefoxAPK(target, {"guest_path": "/data/app/~~test/org.mozilla.firefox-test/base.apk",
                        "bytes": size, "sha256": sha, "stat_file": {}}, deadline=time.monotonic() + 5)

    def test_paths_and_observed_uid_version_not_guessed(self):
        good = "/data/app/~~test/org.mozilla.firefox-test/base.apk"
        self.assertEqual(c.installed_path(("package:" + good + "\n").encode()), good)
        for bad in (good + "/../base.apk", good.replace("org.mozilla.firefox", "other.app"), good.replace("base.apk", "split_x.apk")):
            with self.assertRaises(c.Refused):
                c.canonical_apk_path(bad)
        raw = f"package:org.mozilla.firefox versionCode:{c.VERSION_CODE} uid:10123\n".encode()
        self.assertEqual(c.installed_metadata(raw, 10123, 0)["uid"], 10123)
        with self.assertRaises(c.Refused):
            c.installed_metadata(raw, 10124, 0)


class WireControls(unittest.TestCase):
    def test_exact_find_wire_and_ambiguity(self):
        value = {"ok": True, "accessibility_mode_restoration_verified": True, "count": 1,
            "matches": [{"package": c.PACKAGE, "visible": True, "enabled": True, "password": False,
                         "source": "native_accessibility", "window_id": 4}], "window_context": {}}
        self.assertEqual(a.one_find(value), value["matches"][0])
        for key, changed in (("count", 2), ("matches", []), ("accessibility_mode_restoration_verified", False)):
            altered = copy.deepcopy(value)
            altered[key] = changed
            with self.assertRaises(c.Refused):
                a.one_find(altered)
        altered = copy.deepcopy(value)
        altered["matches"][0]["password"] = True
        with self.assertRaises(c.Refused):
            a.one_find(altered)

    def test_missing_selector_binding_refuses(self):
        with self.assertRaises(c.Refused):
            a.validate_selector_contract({}, {"apk": {"bytes": c.APK_BYTES, "sha256": c.APK_SHA256}})

    def parent_fixture(self, root, change=None):
        step = root / "steps/ui-01-find"
        step.mkdir(parents=True)
        def put(path, value):
            raw = value if isinstance(value, bytes) else json.dumps(value).encode()
            path.write_bytes(raw)
            return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        def read(ref):
            raw = Path(ref["path"]).read_bytes()
            c.need(len(raw) == ref["bytes"] and hashlib.sha256(raw).hexdigest() == ref["sha256"], "FIXTURE_REF_CHANGED")
            return raw
        common = types.SimpleNamespace(parse=json.loads, read_ref=read,
            regular=lambda path: (Path(path).read_bytes(), {}))
        # Source-only import of the exact existing typed entry; no main call.
        source = Path(__file__).parent / "originals/business_ui_entry.py"
        entry = types.ModuleType("offline_original_ui_entry")
        entry.__file__ = str(source)
        exec(compile(source.read_bytes(), str(source), "exec"), entry.__dict__)
        request = {"op": "find", "selector": {"text": p.PAGES["manifesto"]["heading"]}, "accessibility_mode": "none"}
        scope_ref = {"path": str(root / "scope.json"), "bytes": 1, "sha256": "a" * 64}
        argv = entry.logical_argv(request, c.PACKAGE, step)
        logical = {"schema": "pocket4-final-ui-logical-command-v1", "scope_sha256": scope_ref["sha256"],
            "argv": argv, "mutation": False, "label": "Existing android-app CLI", "automatic_retry": False}
        output = {"ok": True, "OFFLINE_CONTROL": True}
        result = {"host_retirement_proved": True, "evidence_complete": True, "returncode": 0,
            "timed_out": False, "errors": [], "first_error": None,
            "argv": entry.entry_argv(scope_ref, "client", step.name, "command-001", argv[1:]),
            "stdout": put(step / "command-001.stdout", output), "stderr": put(step / "command-001.stderr", b"")}
        if change:
            change(result, logical)
        put(step / "command-001.result.json", result)
        put(step / "command-001.logical.json", logical)
        flow = types.SimpleNamespace(c=common, scope={"flow_root": str(root)}, scope_ref=scope_ref,
            modules={"business_ui_entry.py": entry}, guard=lambda: None)
        return flow, step, output, request

    def test_actual_parent_chain_verifier_accepts_only_complete_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.parent_fixture(Path(directory))
            self.assertTrue(a.verify_ui_parent_result(*values)["host_retirement_proved"])

    def test_parent_without_reap_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.parent_fixture(Path(directory), lambda r, _: r.update(host_retirement_proved=False))
            with self.assertRaises(c.Refused):
                a.verify_ui_parent_result(*values)

    def test_wrong_parent_scope_or_argv_rejected(self):
        for change in (lambda r, _: r["argv"].append("--unbound"),
                       lambda _, logical: logical.update(scope_sha256="b" * 64)):
            with tempfile.TemporaryDirectory() as directory:
                values = self.parent_fixture(Path(directory), change)
                with self.assertRaises(c.Refused):
                    a.verify_ui_parent_result(*values)


if __name__ == "__main__":
    unittest.main(verbosity=2)
