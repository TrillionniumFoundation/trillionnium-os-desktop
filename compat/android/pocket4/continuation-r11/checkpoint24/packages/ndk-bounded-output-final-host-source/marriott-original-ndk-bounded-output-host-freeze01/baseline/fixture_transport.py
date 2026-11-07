"""NDK-only transport fork from actual IHG02 BoundArun.
The held entry, seven authority FDs, first-error, observation-before-release,
poisoning and direct-child evidence protocol are retained. Package, unallocated
install UID / actual installed UID and phase are bound to the independent fixed
fixture scope. No CLI, no module-global rebinding, no legacy helper patching.
This source does not supply admission or an installed fixture.
"""
import hashlib
import json
import math
import os
import stat
import subprocess
import threading


ANDROID_APP_SHA256 = "eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66"
FRAMEWORK_EPOCH_SHA256 = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
HELD_HELPER_SHA256 = "21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689"
EXPECTED_PACKAGE = "com.example.ndk_tests"
HOST_FIXED_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"}
REQUIRED_ENV = {"PATH", "BOOTCLASSPATH", "DEX2OATBOOTCLASSPATH",
                "ANDROID_ROOT", "ANDROID_DATA", "ANDROID_ART_ROOT"}
ALLOWED_ENV = REQUIRED_ENV | {"ANDROID_ASSETS", "ANDROID_BOOTLOGO", "ANDROID_I18N_ROOT",
    "ANDROID_STORAGE", "ANDROID_TZDATA_ROOT", "ASEC_MOUNTPOINT", "DOWNLOAD_CACHE",
    "EXTERNAL_STORAGE", "LOOP_MOUNTPOINT", "STANDALONE_SYSTEMSERVER_JARS",
    "SYSTEMSERVERCLASSPATH", "LANG"}


class TransportError(RuntimeError):
    """Code and metadata deliberately omit command text and private output."""
    def __init__(self, code, *, attempted=False, unknown=False, **metadata):
        super().__init__(code)
        self.details = {"action_attempted": attempted, "outcome_unknown": unknown,
                        "automatic_retry": False, **metadata}


class TransportTimeout(subprocess.TimeoutExpired):
    """Preserve the existing helper's explicit TimeoutExpired handling."""
    def __init__(self, code, timeout, **metadata):
        super().__init__("<owned Android command>", timeout)
        self.code = code
        self.details = {"action_attempted": True, "outcome_unknown": True,
                        "automatic_retry": False, **metadata}

    def __str__(self):
        return self.code


def require(condition, code):
    if not condition:
        raise TransportError(code)


def environment_values(values):
    require(isinstance(values, dict) and REQUIRED_ENV <= set(values) <= ALLOWED_ENV,
            "ANDROID_ENVIRONMENT_KEYS_DIFFER")
    result = {}
    for key, value in values.items():
        require(isinstance(value, str) and (key not in REQUIRED_ENV or value) and "\0" not in value
                and len(value.encode("utf-8")) <= 65536,
                "ANDROID_ENVIRONMENT_VALUE_INVALID")
        result[key] = value
    return result


def host_environment():
    values = dict(HOST_FIXED_ENV)
    if "HOME" in os.environ:
        value = os.environ["HOME"]
        require(type(value) is str and "\0" not in value and
                len(value.encode("utf-8")) <= 65536, "INHERITED_HOME_BOUND")
        values["HOME"] = value
    return values


class BoundArun:
    """The existing helper's arun signature, with an immutable held target.

    `guard` rechecks the fixed Main epoch; it must never recapture/adopt a new
    epoch. `record` must durably record each transport intent/result inside the
    already claimed recorder step. Its failure stops this adapter permanently.
    The qualified helper only owns its direct entry child. Android's existing
    inner timeout and a separately qualified fixture retirement remain necessary.
    """
    def __init__(self, *, target, environment, guard, record, epoch_sha256,
                 init_pid, package, uid, interactive_production,
                 fixture_scope, fixture_contract, runner=subprocess.run):
        fixture_contract.validate_scope(fixture_scope)
        require(epoch_sha256 == FRAMEWORK_EPOCH_SHA256 and package == EXPECTED_PACKAGE and
                package == fixture_scope["package"] and uid == fixture_scope["uid"],
                "EXACT_INDEPENDENT_NDK_FIXTURE_SCOPE_REQUIRED")
        self.fixture_contract = fixture_contract
        self.fixture_scope = json.loads(json.dumps(fixture_scope, sort_keys=True))
        self.fixture_scope_text = json.dumps(self.fixture_scope, sort_keys=True, separators=(",", ":"))
        require(interactive_production is True, "SEPARATELY_REVIEWED_FIXTURE_ADMISSION_REQUIRED")
        require(type(init_pid) is int and init_pid > 1 and target.expected["pid"] == init_pid,
                "HELD_TARGET_INIT_DIFFERS")
        require(target.helper_sha256 == HELD_HELPER_SHA256,
                "HELD_ENTRY_HELPER_PIN_DIFFERS")
        require(callable(guard) and callable(record) and callable(runner),
                "TRANSPORT_CALLBACK_MISSING")
        self.target = target
        self.environment = environment_values(environment)
        self.guard = guard
        self.record = record
        self.runner = runner
        self._lock = threading.Lock()
        self._poisoned = False
        self._sequence = 0

    def _check(self, attempted):
        self.fixture_contract.validate_scope(self.fixture_scope)
        require(json.dumps(self.fixture_scope,sort_keys=True,separators=(",", ":")) ==
                self.fixture_scope_text, "FIXTURE_SCOPE_MUTATED")
        self.guard(action_attempted=attempted)
        self.target.verify()

    def __call__(self, args, timeout=30):
        require(self._lock.acquire(blocking=False), "TRANSPORT_ALREADY_ACTIVE")
        try:
            require(not self._poisoned, "TRANSPORT_CLOSED_AFTER_FAILURE")
            require(isinstance(args, (list, tuple)) and args and
                    all(isinstance(x, str) and x and "\0" not in x for x in args)
                    and args[0].startswith("/"), "ANDROID_COMMAND_INVALID")
            require(type(timeout) in (int, float) and math.isfinite(timeout)
                    and 0 < timeout <= 70, "ANDROID_COMMAND_TIMEOUT_INVALID")
            self._check(False)
            inner = max(1, timeout - 5)
            command = ["/system/bin/env", "-i"]
            command += [key + "=" + self.environment[key] for key in sorted(self.environment)]
            command += ["/system/xbin/su", "2000", "/system/bin/timeout", "-k", "2",
                        str(inner), *args]
            self._sequence += 1
            identity = {"sequence": self._sequence, "epoch_sha256": FRAMEWORK_EPOCH_SHA256,
                        "package": EXPECTED_PACKAGE, "uid": self.fixture_scope["uid"],
                        "fixture_phase": self.fixture_scope["phase"],
                        "fixture_scope_sha256": hashlib.sha256(self.fixture_scope_text.encode()).hexdigest(),
                        "command_sha256": hashlib.sha256(json.dumps(args, ensure_ascii=False,
                            separators=(",", ":")).encode()).hexdigest(),
                        "timeout_seconds": timeout, "inner_timeout_seconds": inner,
                        "automatic_retry": False, "numeric_pid_target_used": False}
            self.record("intent", identity)
            primary = None
            completed = None
            attempted = False
            entered = False
            manager = None
            status = {**identity, "action_attempted": False, "outcome_unknown": False}

            def remember(failure, code, phase, **metadata):
                nonlocal primary
                if primary is None:
                    if isinstance(failure, (TransportError, TransportTimeout)):
                        primary = failure
                    else:
                        primary = TransportError(code, attempted=attempted, unknown=attempted)
                        primary.__cause__ = failure
                primary.details.update(metadata)
                primary.details.setdefault("observed_errors", []).append({
                    "phase": phase, "exception_type": type(failure).__name__,
                    "errno": getattr(failure, "errno", None)})

            try:
                manager = self.target.entry(command)
                entry_value = manager.__enter__()
                entered = True
                argv, descriptors = entry_value
                require(len(descriptors) == 7 and len(set(descriptors)) == 7
                        and all(type(fd) is int and fd >= 3 for fd in descriptors),
                        "HELD_AUTHORITY_SET_DIFFERS")
                require(isinstance(argv, (list, tuple)) and
                        all(isinstance(part, str) and part and "\0" not in part for part in argv),
                        "HELD_ENTRY_ARGV_INVALID")
                try:
                    boundary = argv.index("--")
                except ValueError:
                    raise TransportError("HELD_ENTRY_SEPARATOR_MISSING")
                prefix = list(argv[:boundary])
                require("--target" not in prefix and "-t" not in prefix and
                        all(not part.startswith("--target=") for part in prefix),
                        "NUMERIC_PID_ENTRY_FORBIDDEN")
                require(list(argv[boundary + 1:]) == command,
                        "HELD_ENTRY_COMMAND_SUFFIX_DIFFERS")
                # Match the qualified R5 helper protocol and the exact passed
                # authority FDs. Only the helper prefix is a namespace entry;
                # Android command options such as pm install -t follow "--".
                expected_prefix = [str(self.target.helper_path),
                    "--parent-pid=" + str(os.getpid()),
                    "--root-fd=" + str(descriptors[0])]
                expected_prefix += ["--" + name + "-fd=" + str(fd) for name, fd in
                    zip(("mnt", "pid", "uts", "ipc", "net", "cgroup"), descriptors[1:])]
                require(prefix == expected_prefix, "HELD_ENTRY_PREFIX_DIFFERS")
                attempted = True
                try:
                    completed = self.runner(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=timeout, env=host_environment(), pass_fds=tuple(descriptors), close_fds=True)
                except subprocess.TimeoutExpired as failure:
                    primary = TransportTimeout("HOST_COMMAND_TIMEOUT", timeout)
                    primary.__cause__ = failure
                except BaseException as failure:
                    primary = TransportError("HOST_COMMAND_INTERRUPTED", attempted=True, unknown=True,
                                             exception_type=type(failure).__name__)
                    primary.__cause__ = failure
                if completed is None:
                    status = {**identity, "first_cause": str(primary),
                        "action_attempted": True, "outcome_unknown": True}
                else:
                    status = {**identity, "returncode": completed.returncode,
                        "stdout_bytes": len(completed.stdout), "stderr_bytes": len(completed.stderr),
                        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
                        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
                        "action_attempted": True, "outcome_unknown": completed.returncode != 0}
                    if getattr(completed, "host_timed_out", False):
                        primary = TransportTimeout("HOST_COMMAND_TIMEOUT", timeout,
                                                   returncode=completed.returncode)
                    elif completed.returncode in (124, 137):
                        primary = TransportTimeout("ANDROID_COMMAND_TIMEOUT", inner,
                                                   returncode=completed.returncode)
                    elif completed.returncode != 0:
                        primary = TransportError("ANDROID_COMMAND_FAILED", attempted=True, unknown=True,
                                                 returncode=completed.returncode)
                    recorder_errors = getattr(completed, "recorder_errors", [])
                    if recorder_errors:
                        remember(TransportError("RECORDER_COMMAND_EVIDENCE_FAILED", attempted=True,
                            unknown=True), "RECORDER_COMMAND_EVIDENCE_FAILED", "recorder_command_evidence",
                            recorder_errors=recorder_errors)
                # This observation precedes lease exit: a release exception must
                # not erase a command that was already sent or replace its cause.
                try:
                    self.record("command-result", status)
                except BaseException as failure:
                    remember(failure, "COMMAND_RESULT_RECORD_FAILED", "command_result_record",
                             command_result_record_failed=True)
            except BaseException as failure:
                phase = "entry_acquire" if not entered else "command_observation"
                code = "HELD_ENTRY_ACQUIRE_FAILED" if not entered else "COMMAND_OBSERVATION_FAILED"
                remember(failure, code, phase)
            finally:
                if entered:
                    try:
                        # Even if a context manager reports suppression, an
                        # already observed command failure stays authoritative.
                        manager.__exit__(type(primary) if primary else None, primary,
                                         primary.__traceback__ if primary else None)
                    except BaseException as failure:
                        remember(failure, "HELD_ENTRY_RELEASE_FAILED", "entry_release",
                                 entry_release_failed=True)
                if attempted:
                    try:
                        self._check(True)
                    except BaseException as failure:
                        remember(failure, "POST_COMMAND_EPOCH_OR_TARGET_CHANGED", "post_command_guard",
                                 post_command_guard_failed=True)
            if primary is not None:
                try:
                    self.record("failure", {**status, "first_cause": str(primary), **primary.details})
                except BaseException:
                    primary.details["failure_record_failed"] = True
                raise primary
            self.record("verified-result", {**status, "outcome_unknown": False})
            return completed.stdout
        except BaseException:
            # Evidence failure or even a pre-entry guard failure cannot invite
            # another command in the same admitted recorder step.
            self._poisoned = True
            raise
        finally:
            self._lock.release()

