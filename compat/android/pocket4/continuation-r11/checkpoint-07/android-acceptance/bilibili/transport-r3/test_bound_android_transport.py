"""Offline arun boundary controls; no Android or namespace entry is executed."""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("owned_bound_transport", HERE / "bound_android_transport.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
ENV = {"PATH": "/system/bin:/system/xbin", "BOOTCLASSPATH": "/apex/owned/a.jar",
       "DEX2OATBOOTCLASSPATH": "/apex/owned/a.jar", "ANDROID_ROOT": "/system",
       "ANDROID_DATA": "/data", "ANDROID_ART_ROOT": "/apex/com.android.art"}


class Target:
    def __init__(self):
        self.expected = {"pid": 41001}
        self.helper_sha256 = M.HELD_HELPER_SHA256
        self.fds = [os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC) for _ in range(7)]
        self.verified = 0
        self.alias = False
        self.numeric = False
        self.active = 0
        self.enter_failure = False
        self.exit_failure = False
        self.bad_entry_shape = False

    def verify(self):
        self.verified += 1

    @contextmanager
    def entry(self, command):
        if self.enter_failure:
            raise OSError(9, "injected lease acquire error")
        self.active += 1
        argv = ["/qualified/held-namespace-entry", "--parent-pid=" + str(os.getpid())]
        argv += ["--" + name + "-fd=" + str(fd) for name, fd in
                 zip(("root", "mnt", "pid", "uts", "ipc", "net", "cgroup"), self.fds)]
        argv += ["--", *command]
        if self.numeric:
            argv[1:1] = ["--target=41001"]
        try:
            value = (argv, self.fds if not self.alias else [self.fds[0]] * 7)
            yield (*value, "unexpected") if self.bad_entry_shape else value
        finally:
            self.active -= 1
            if self.exit_failure:
                raise OSError(9, "injected lease release error")

    def close(self):
        for fd in self.fds:
            os.close(fd)


class BoundaryControls(unittest.TestCase):
    def setUp(self):
        self.target = Target()
        self.calls = []
        self.guards = []
        self.records = []
        self.returncode = 0
        self.throw = None
        self.post_guard_fail = False
        self.record_fail = None

    def tearDown(self):
        self.assertEqual(self.target.active, 0)
        self.target.close()

    def runner(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.throw:
            raise self.throw
        return subprocess.CompletedProcess(argv, self.returncode, b"\0exact\xff", b"error-private")

    def guard(self, *, action_attempted):
        self.guards.append(action_attempted)
        if action_attempted and self.post_guard_fail:
            raise RuntimeError("epoch differs")

    def record(self, kind, value):
        self.records.append((kind, value))
        if kind == self.record_fail:
            raise OSError(28, "injected ENOSPC")

    def transport(self, **override):
        args = {"target": self.target, "environment": ENV, "guard": self.guard,
                "record": self.record, "epoch_sha256": M.FRAMEWORK_EPOCH_SHA256,
                "init_pid": 41001, "package": "tv.danmaku.bili", "uid": 10117,
                "interactive_production": True, "runner": self.runner}
        args.update(override)
        return M.BoundArun(**args)

    def invoke(self, transport):
        return transport(["/system/bin/dumpsys", "audio"], timeout=15)

    def test_01_actual_old_arun_has_numeric_target(self):
        base = M.load_existing_helper(HERE / "reference/android-app")
        base.discover = lambda: (41001, ENV, {})
        old = base.subprocess
        base.subprocess = types.SimpleNamespace(run=self.runner, PIPE=subprocess.PIPE,
                                                TimeoutExpired=subprocess.TimeoutExpired)
        try:
            self.assertEqual(self.invoke(base.arun), b"\0exact\xff")
        finally:
            base.subprocess = old
        argv, kwargs = self.calls[0]
        self.assertIn("-t", argv)
        self.assertEqual(argv[argv.index("-t") + 1], "41001")
        self.assertNotIn("pass_fds", kwargs)
        self.assertNotIn("-i", argv[argv.index("/system/bin/env") + 1:])

    def test_02_candidate_passes_only_seven_real_authority_fds(self):
        self.assertEqual(self.invoke(self.transport()), b"\0exact\xff")
        argv, kwargs = self.calls[0]
        self.assertNotIn("-t", argv)
        self.assertNotIn("--target", argv)
        self.assertEqual(kwargs["pass_fds"], tuple(self.target.fds))
        self.assertTrue(kwargs["close_fds"])
        self.assertEqual(kwargs["env"], M.HOST_ENV)
        tail = argv[argv.index("--") + 1:]
        self.assertEqual(tail[:2], ["/system/bin/env", "-i"])
        self.assertEqual(tail[-8:], ["/system/xbin/su", "2000", "/system/bin/timeout", "-k", "2", "10",
                                   "/system/bin/dumpsys", "audio"])
        self.assertEqual(self.guards, [False, True])
        self.assertEqual(self.target.verified, 2)

    def test_03_empty_classpath_is_rejected_before_command(self):
        with self.assertRaisesRegex(M.TransportError, "VALUE_INVALID"):
            self.transport(environment={**ENV, "BOOTCLASSPATH": ""})
        self.assertFalse(self.calls or self.records)

    def test_04_missing_classpath_is_rejected_before_command(self):
        env = dict(ENV)
        del env["DEX2OATBOOTCLASSPATH"]
        with self.assertRaisesRegex(M.TransportError, "KEYS_DIFFER"):
            self.transport(environment=env)
        self.assertFalse(self.calls or self.records)

    def test_05_loader_environment_injection_rejected(self):
        with self.assertRaisesRegex(M.TransportError, "KEYS_DIFFER"):
            self.transport(environment={**ENV, "LD_PRELOAD": "/bad.so"})
        self.assertFalse(self.calls)

    def test_06_wrong_scope_uid_or_missing_authorization_rejected(self):
        for args in ({"uid": 10118}, {"epoch_sha256": "0" * 64},
                     {"package": "another.app"}, {"interactive_production": False}):
            with self.subTest(args=args), self.assertRaises(M.TransportError):
                self.transport(**args)
        self.assertFalse(self.calls)

    def test_07_wrong_init_or_helper_rejected(self):
        with self.assertRaisesRegex(M.TransportError, "INIT_DIFFERS"):
            self.transport(init_pid=41002)
        self.target.helper_sha256 = "0" * 64
        with self.assertRaisesRegex(M.TransportError, "HELPER_PIN_DIFFERS"):
            self.transport()
        self.assertFalse(self.calls)

    def test_08_intent_save_failure_prevents_entry(self):
        self.record_fail = "intent"
        transport = self.transport()
        with self.assertRaises(OSError):
            self.invoke(transport)
        with self.assertRaisesRegex(M.TransportError, "CLOSED_AFTER_FAILURE"):
            self.invoke(transport)
        self.assertFalse(self.calls)
        self.assertEqual(self.guards, [False])

    def test_09_nonzero_first_cause_survives_post_guard_failure(self):
        self.returncode = 134
        self.post_guard_fail = True
        with self.assertRaisesRegex(M.TransportError, "ANDROID_COMMAND_FAILED") as error:
            self.invoke(self.transport())
        self.assertEqual(error.exception.details["returncode"], 134)
        self.assertTrue(error.exception.details["post_command_guard_failed"])
        self.assertEqual(self.guards, [False, True])
        self.assertEqual(self.records[1][0], "command-result")

    def test_10_nonzero_first_cause_survives_evidence_failure(self):
        self.returncode = 134
        self.record_fail = "command-result"
        with self.assertRaisesRegex(M.TransportError, "ANDROID_COMMAND_FAILED") as error:
            self.invoke(self.transport())
        self.assertEqual(error.exception.details["returncode"], 134)
        self.assertTrue(error.exception.details["command_result_record_failed"])
        self.assertEqual(self.guards, [False, True])

    def test_11_timeout_closes_transport_without_replay(self):
        self.throw = subprocess.TimeoutExpired(["owned"], 15)
        transport = self.transport()
        with self.assertRaisesRegex(M.TransportTimeout, "HOST_COMMAND_TIMEOUT") as error:
            self.invoke(transport)
        self.assertTrue(error.exception.details["outcome_unknown"])
        with self.assertRaisesRegex(M.TransportError, "CLOSED_AFTER_FAILURE"):
            self.invoke(transport)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.guards, [False, True])

    def test_12_android_timeout_rcs_remain_unknown(self):
        for rc in (124, 137):
            self.returncode = rc
            transport = self.transport()
            with self.subTest(rc=rc), self.assertRaises(M.TransportTimeout) as error:
                self.invoke(transport)
            self.assertEqual(error.exception.details["returncode"], rc)
            self.assertTrue(error.exception.details["outcome_unknown"])
            with self.assertRaisesRegex(M.TransportError, "CLOSED_AFTER_FAILURE"):
                self.invoke(transport)
        self.assertEqual(len(self.calls), 2)

    def test_13_rc_zero_with_changed_epoch_cannot_return_success(self):
        self.post_guard_fail = True
        with self.assertRaisesRegex(M.TransportError, "POST_COMMAND_EPOCH"):
            self.invoke(self.transport())
        self.assertNotIn("verified-result", [row[0] for row in self.records])

    def test_14_alias_authority_rejected_before_runner(self):
        self.target.alias = True
        with self.assertRaisesRegex(M.TransportError, "AUTHORITY_SET_DIFFERS"):
            self.invoke(self.transport())
        self.assertFalse(self.calls)

    def test_15_numeric_target_reintroduction_rejected_before_runner(self):
        self.target.numeric = True
        with self.assertRaisesRegex(M.TransportError, "NUMERIC_PID_ENTRY_FORBIDDEN"):
            self.invoke(self.transport())
        self.assertFalse(self.calls)

    def test_16_original_definitions_and_action_lock_preserved(self):
        base = M.load_existing_helper(HERE / "reference/android-app")
        definitions = {name: value for name, value in vars(base).items()
                       if isinstance(value, types.FunctionType)}
        transport = self.transport()
        with M.patched_transport(base, transport):
            self.assertIs(base.arun, transport)
            for name, value in definitions.items():
                if name != "arun":
                    self.assertIs(vars(base)[name], value)
        for name, value in definitions.items():
            self.assertIs(vars(base)[name], value)
        self.assertIn("/run/lock/android-digitalis-actions.lock", base.helper.__code__.co_consts)
        self.assertFalse(self.calls)

    def test_17_wrong_source_is_not_imported(self):
        source = (HERE / "reference/android-app").read_bytes()
        with tempfile.TemporaryDirectory(prefix="owned-arun-source-") as directory:
            path = Path(directory) / "different-helper"
            path.write_bytes(source.replace(b"No ADB", b"NO ADB", 1))
            with self.assertRaisesRegex(M.TransportError, "SOURCE_PIN_DIFFERS"):
                M.load_existing_helper(path)
        self.assertFalse(self.calls)

    def test_18_success_record_failure_is_not_success(self):
        self.record_fail = "verified-result"
        transport = self.transport()
        with self.assertRaises(OSError):
            self.invoke(transport)
        with self.assertRaisesRegex(M.TransportError, "CLOSED_AFTER_FAILURE"):
            self.invoke(transport)
        self.assertEqual(len(self.calls), 1)

    def test_19_actual_existing_ui_preserves_timeout_protocol(self):
        base = M.load_existing_helper(HERE / "reference/android-app")
        request = {"op": "click", "selector": {"text": "owned local control"}}
        def old_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired("owned", 70)
        base.arun = old_timeout
        with self.assertRaises(subprocess.TimeoutExpired):
            base.ui(request)
        self.returncode = 124
        with M.patched_transport(base, self.transport()):
            with self.assertRaises(M.TransportTimeout) as error:
                base.ui(request)
        self.assertIsInstance(error.exception, subprocess.TimeoutExpired)
        self.assertTrue(error.exception.details["outcome_unknown"])
        self.assertEqual(error.exception.details["returncode"], 124)
        self.assertEqual(len(self.calls), 1)

    def test_20_retained_r2_loses_timeout_on_lease_exit(self):
        path = HERE / "negative-control/bound_android_transport_r2.py"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "d380a388c1cc4391a3dd572dc12a293cfc1015f02627a5187136cf786ea3e018")
        spec = importlib.util.spec_from_file_location("owned_transport_r2_negative", path)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        self.throw = subprocess.TimeoutExpired("owned", 15)
        self.target.exit_failure = True
        transport = old.BoundArun(target=self.target, environment=ENV, guard=self.guard,
            record=self.record, epoch_sha256=M.FRAMEWORK_EPOCH_SHA256,
            init_pid=41001, package="tv.danmaku.bili", uid=10117,
            interactive_production=True, runner=self.runner)
        with self.assertRaisesRegex(OSError, "lease release"):
            self.invoke(transport)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual([kind for kind, _ in self.records], ["intent"])
        self.assertEqual(self.guards, [False])

    def test_21_timeout_primary_preserved_when_lease_exit_fails(self):
        self.throw = subprocess.TimeoutExpired("owned", 15)
        self.target.exit_failure = True
        transport = self.transport()
        with self.assertRaisesRegex(M.TransportTimeout, "HOST_COMMAND_TIMEOUT") as error:
            self.invoke(transport)
        self.assertTrue(error.exception.details["entry_release_failed"])
        self.assertEqual(self.guards, [False, True])
        self.assertEqual([kind for kind, _ in self.records],
                         ["intent", "command-result", "failure"])
        self.assertEqual(self.records[1][1]["first_cause"], "HOST_COMMAND_TIMEOUT")
        with self.assertRaisesRegex(M.TransportError, "CLOSED_AFTER_FAILURE"):
            self.invoke(transport)
        self.assertEqual(len(self.calls), 1)

    def test_22_command_success_retained_when_lease_exit_fails(self):
        self.target.exit_failure = True
        with self.assertRaisesRegex(M.TransportError, "HELD_ENTRY_RELEASE_FAILED") as error:
            self.invoke(self.transport())
        self.assertTrue(error.exception.details["entry_release_failed"])
        self.assertEqual(self.guards, [False, True])
        self.assertEqual(self.records[1][0], "command-result")
        self.assertEqual(self.records[1][1]["returncode"], 0)
        self.assertNotIn("verified-result", [row[0] for row in self.records])

    def test_23_entry_acquire_failure_sends_no_command(self):
        self.target.enter_failure = True
        with self.assertRaisesRegex(M.TransportError, "HELD_ENTRY_ACQUIRE_FAILED") as error:
            self.invoke(self.transport())
        self.assertFalse(error.exception.details["action_attempted"])
        self.assertFalse(self.calls)
        self.assertEqual(self.guards, [False])
        self.assertEqual([kind for kind, _ in self.records], ["intent", "failure"])

    def test_24_timeout_keeps_all_three_secondary_failures(self):
        self.throw = subprocess.TimeoutExpired("owned", 15)
        self.target.exit_failure = True
        self.record_fail = "command-result"
        self.post_guard_fail = True
        with self.assertRaisesRegex(M.TransportTimeout, "HOST_COMMAND_TIMEOUT") as error:
            self.invoke(self.transport())
        details = error.exception.details
        self.assertTrue(details["entry_release_failed"])
        self.assertTrue(details["command_result_record_failed"])
        self.assertTrue(details["post_command_guard_failed"])
        self.assertEqual([row["phase"] for row in details["observed_errors"]],
                         ["command_result_record", "entry_release", "post_command_guard"])
        self.assertEqual(self.guards, [False, True])
        self.assertEqual(len(self.calls), 1)

    def test_25_bad_entry_shape_is_still_released_before_failure(self):
        self.target.bad_entry_shape = True
        with self.assertRaisesRegex(M.TransportError, "COMMAND_OBSERVATION_FAILED") as error:
            self.invoke(self.transport())
        self.assertFalse(error.exception.details["action_attempted"])
        self.assertEqual(self.target.active, 0)
        self.assertFalse(self.calls)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryControls)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"schema": 1, "controls": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "passed": result.wasSuccessful(), "Android_operations": 0, "Main_actions": 0,
        "test_boundary": "actual frozen old arun and candidate code; explicit fake command runner and namespace-target seam",
        "qualifies_real_namespace_entry": False, "qualifies_recorder_integration": False,
        "qualifies_Bilibili_reopen_or_audio": False,
        "source_sha256": hashlib.sha256((HERE / "bound_android_transport.py").read_bytes()).hexdigest()}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
