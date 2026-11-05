#!/usr/bin/python3 -I
"""Prepared single-generation USB PM contrast; default is an inert plan.

--preflight reads current host/sysfs metadata and performs no configuration write.
--execute is a separate, explicit future operation. It has no device-arrival wait,
no capture or UI operation, and no power-write retry. This prepared file has not
been executed against Pocket4 sysfs.
"""
from contextlib import contextmanager
from pathlib import Path
import argparse
import ctypes
import fcntl
import hashlib
import json
import os
import re
import signal
import stat
import time

HOST = "alex-G1628-04"
KERNEL = "7.0.0-38-generic"
BUS = "/sys/devices/pci0000:00/0000:00:08.3/0000:c7:00.0/usb3"
ALIAS = "/sys/bus/usb/devices/3-4"
CANONICAL = BUS + "/3-4"  # Required future topology, not a claimed present device.
UI_LOCK = "/run/lock/android-digitalis-actions.lock"
SECONDS = 30.0
IDENTITY = {"idVendor": "1e08", "idProduct": "5520", "serial": "JX20250923V2",
            "manufacturer": "SunplusIT Inc", "product": "Integrated Camera",
            "bcdDevice": "0923", "busnum": "3", "devpath": "4"}
POWER_FIELDS = ("runtime_status", "autosuspend_delay_ms", "runtime_active_time",
                "runtime_suspended_time", "runtime_usage", "connected_duration",
                "active_duration", "wakeup", "persist")
READ_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
DIR_FLAGS = READ_FLAGS | os.O_DIRECTORY
LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.write.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
LIBC.write.restype = ctypes.c_ssize_t


class Refused(RuntimeError):
    pass


def require(value, reason):
    if not value:
        raise Refused(reason)


def stamp(fd):
    value = os.fstat(fd)
    return {"dev": value.st_dev, "ino": value.st_ino, "mode": value.st_mode,
            "uid": value.st_uid, "gid": value.st_gid}


def read_fd(fd, maximum=4096):
    # Offset zero rearms a sysfs show callback. Do not reuse a cached old read.
    raw = os.pread(fd, maximum + 1, 0)
    require(len(raw) <= maximum and b"\x00" not in raw, "ATTRIBUTE_NOT_BOUNDED_TEXT")
    return raw.decode("ascii", "strict").rstrip("\n")


def single_store(fd, value):
    require(value in ("on", "auto"), "STORE_VALUE_NOT_ALLOWED")
    payload = (value + "\n").encode("ascii")
    os.lseek(fd, 0, os.SEEK_SET)
    # One libc write invocation, including on EINTR or a short return. Python's
    # os.write may automatically retry EINTR; this wrapper deliberately does not.
    ctypes.set_errno(0)
    written = LIBC.write(fd, ctypes.c_char_p(payload), len(payload))
    if written < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    require(written == len(payload), "SHORT_STORE_OUTCOME_UNKNOWN_NO_RETRY")
    return written


def open_directories(path):
    require(path.startswith("/") and ".." not in Path(path).parts,
            "ABSOLUTE_CANONICAL_PATH_REQUIRED")
    fd = os.open("/", DIR_FLAGS)
    try:
        for part in Path(path).parts[1:]:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def host_identity(expected_boot=None):
    uname = os.uname()
    require(uname.nodename == HOST and uname.release == KERNEL, "HOST_OR_KERNEL_CHANGED")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    require(re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot), "INVALID_BOOT_ID")
    require(expected_boot is None or boot == expected_boot, "BOOT_BINDING_CHANGED")
    require(os.readlink("/proc/self/ns/mnt") == os.readlink("/proc/1/ns/mnt"),
            "HOST_MOUNT_NAMESPACE_REQUIRED")
    require(Path("/proc/1/comm").read_text().strip() == "systemd", "HOST_INIT_REQUIRED")
    return {"hostname": uname.nodename, "kernel_release": uname.release, "boot_id": boot,
            "mount_namespace": os.readlink("/proc/self/ns/mnt")}


def require_sysfs(fd):
    info = Path("/proc/self/fdinfo", str(fd)).read_text()
    ids = re.findall(r"^mnt_id:\s*(\d+)$", info, re.M)
    require(len(ids) == 1, "MOUNT_ID_UNKNOWN")
    rows = [row for row in Path("/proc/self/mountinfo").read_text().splitlines()
            if row.split(" ", 1)[0] == ids[0]]
    require(len(rows) == 1 and " - sysfs " in rows[0], "REAL_SYSFS_REQUIRED")
    require(rows[0].split()[4] == "/sys", "CANONICAL_SYSFS_MOUNT_REQUIRED")


class HeldDevice:
    def __init__(self, writable, expected_boot=None):
        self.fds = []
        try:
            self.host = host_identity(expected_boot)
            require(os.path.realpath(ALIAS) == CANONICAL, "TARGET_ABSENT_OR_TOPOLOGY_CHANGED")
            self.device = self.keep(open_directories(CANONICAL))
            require_sysfs(self.device)
            self.device_stamp = stamp(self.device)
            require(self.device_stamp["uid"] == 0 and not (self.device_stamp["mode"] & 0o022),
                    "DEVICE_DIRECTORY_NOT_ROOT_OWNED")
            self.identity_fds = {name: self.attribute(self.device, name) for name in IDENTITY}
            observed = {name: read_fd(fd) for name, fd in self.identity_fds.items()}
            require(observed == IDENTITY, "EXACT_CAMERA_IDENTITY_REQUIRED")
            self.devnum = self.attribute(self.device, "devnum")
            self.devnum_value = read_fd(self.devnum)
            require(self.devnum_value.isdigit() and 1 <= int(self.devnum_value) <= 127,
                    "DEVICE_ADDRESS_INVALID")
            self.power = self.keep(os.open("power", DIR_FLAGS, dir_fd=self.device))
            self.power_stamp = stamp(self.power)
            flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW if writable else READ_FLAGS
            self.control = self.attribute(self.power, "control", flags)
            self.control_stamp = stamp(self.control)
            self.power_fds = {}
            for name in POWER_FIELDS:
                try:
                    self.power_fds[name] = self.attribute(self.power, name)
                except FileNotFoundError:
                    self.power_fds[name] = None
            require(all(self.power_fds[name] is not None for name in
                        ("runtime_status", "autosuspend_delay_ms", "runtime_suspended_time")),
                    "REQUIRED_DEVICE_PM_EVIDENCE_MISSING")
            self.guard()
        except BaseException:
            self.close()
            raise

    def keep(self, fd):
        self.fds.append(fd)
        return fd

    def attribute(self, directory, name, flags=READ_FLAGS):
        fd = self.keep(os.open(name, flags, dir_fd=directory))
        value = os.fstat(fd)
        require(stat.S_ISREG(value.st_mode) and value.st_uid == 0 and not (value.st_mode & 0o022),
                "UNEXPECTED_SYSFS_ATTRIBUTE_TYPE_OR_OWNER")
        return fd

    def guard(self):
        require(host_identity(self.host["boot_id"]) == self.host, "HOST_CONTEXT_CHANGED")
        require(os.path.realpath(ALIAS) == CANONICAL, "DEVICE_GENERATION_GONE_OR_CHANGED")
        for path, fd, original in ((CANONICAL, self.device, self.device_stamp),
                                   (CANONICAL + "/power", self.power, self.power_stamp),
                                   (CANONICAL + "/power/control", self.control, self.control_stamp)):
            current = os.stat(path, follow_symlinks=False)
            held = os.fstat(fd)
            require(not stat.S_ISLNK(current.st_mode) and held.st_nlink > 0 and
                    current.st_dev == held.st_dev == original["dev"] and
                    current.st_ino == held.st_ino == original["ino"],
                    "DEVICE_OR_CONTROL_GENERATION_CHANGED")
        require({name: read_fd(fd) for name, fd in self.identity_fds.items()} == IDENTITY and
                read_fd(self.devnum) == self.devnum_value, "HELD_DEVICE_IDENTITY_CHANGED")

    def snapshot(self):
        self.guard()
        result = {"control": read_fd(self.control), "power": {
            name: None if fd is None else read_fd(fd) for name, fd in self.power_fds.items()}}
        self.guard()
        return result

    def control_value(self):
        # Cleanup requires identity plus the actual control value, not success
        # of unrelated diagnostic PM counters that might independently fail.
        self.guard()
        value = read_fd(self.control)
        self.guard()
        return value

    def store(self, value):
        self.guard()
        # Never reopen power/control for writing. A replacement at the same
        # pathname cannot receive this write through the retained original FD.
        return single_store(self.control, value)

    def binding(self):
        return {"host": self.host, "alias": ALIAS, "canonical": CANONICAL,
                "expected_identity": IDENTITY, "device_number": self.devnum_value,
                "device_directory": self.device_stamp, "power_directory": self.power_stamp,
                "control_attribute": self.control_stamp}

    def close(self):
        while self.fds:
            os.close(self.fds.pop())


class SignalState:
    def __init__(self):
        self.restoring = False
        self.received = []

    def handler(self, number, frame):
        self.received.append(number)
        if not self.restoring:
            raise InterruptedError("SIGNAL_" + str(number))


def run_trial(device, emit, signals, clock=time.monotonic, sleep=time.sleep,
              bootclock=lambda: time.clock_gettime(time.CLOCK_BOOTTIME), seconds=SECONDS):
    require(seconds >= SECONDS, "OBSERVATION_MUST_EXCEED_HISTORICAL_14_SECOND_WINDOW")
    result = {"state": "NOT_STARTED", "on_write_attempts": 0, "restore_write_attempts": 0,
              "on_write_acknowledged": False, "original_value_verified": False,
              "observation_complete": False, "outcome_unknown": False,
              "causality_established": False, "idle_window_independently_verified": False,
              "camera_function_qualified": False, "production_ready": False,
              "observation_seconds_required": seconds, "samples": []}
    try:
        before = device.snapshot()
        result["before"] = before
        require(before["control"] == "auto", "TARGET_CONTROL_IS_NOT_AUTO_NO_WRITE")
        delay = before["power"]["autosuspend_delay_ms"]
        require(re.fullmatch(r"-?\d+", delay) and int(delay) >= 0,
                "AUTOSUSPEND_ALREADY_DISABLED_OR_DELAY_UNKNOWN_NO_WRITE")
        require(int(delay) < int(seconds * 1000), "NO_WRITE_OUTSIDE_OBSERVATION_WINDOW")
        emit("before", before)
        emit("on-intent", {"value": "on", "automatic_retry": False})
        result["on_write_attempts"] = 1
        result["outcome_unknown"] = True
        device.store("on")
        result["on_write_acknowledged"] = True
        after = device.snapshot()
        require(after["control"] == "on" and after["power"]["runtime_status"] == "active",
                "ON_READBACK_OR_ACTIVE_STATE_NOT_VERIFIED")
        result["after_on"] = after
        result["outcome_unknown"] = False
        emit("on-readback", after)
        start, boot_start = clock(), bootclock()
        suspended = after["power"]["runtime_suspended_time"]
        require(suspended.isdigit(), "SUSPEND_COUNTER_NOT_RECOGNIZED")
        while True:
            sample = device.snapshot()
            elapsed = clock() - start
            require(sample["control"] == "on", "CONTROL_CHANGED_DURING_OBSERVATION")
            require(sample["power"]["runtime_status"] == "active", "DEVICE_NOT_ACTIVE_DURING_OBSERVATION")
            require(sample["power"]["runtime_suspended_time"] == suspended,
                    "SUSPEND_COUNTER_CHANGED_DURING_OBSERVATION")
            require(abs((bootclock() - boot_start) - elapsed) < 1.0,
                    "SYSTEM_SLEEP_OR_CLOCK_DISCONTINUITY_INVALIDATES_CONTRAST")
            entry = {"elapsed_seconds": round(elapsed, 6), **sample}
            result["samples"].append(entry)
            emit("on-sample", entry)
            if elapsed >= seconds:
                result["observed_seconds"] = elapsed
                result["observation_complete"] = True
                break
            sleep(min(1.0, seconds - elapsed))
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        signals.restoring = True
        def cleanup_emit(kind, value):
            # Once a mutation may have happened, a logging failure must never
            # prevent the one same-generation restoration attempt.
            try:
                emit(kind, value)
            except BaseException as exc:
                result.setdefault("cleanup_evidence_errors", []).append(
                    type(exc).__name__ + ": " + str(exc))
        if result["on_write_attempts"]:
            try:
                current = device.control_value()
                require(current in ("on", "auto"), "UNEXPECTED_CONTROL_NO_RESTORE_WRITE")
                if current == "on":
                    cleanup_emit("restore-intent", {"original_value": "auto", "automatic_retry": False})
                    result["restore_write_attempts"] = 1
                    device.store("auto")
                else:
                    result["restoration_note"] = "ORIGINAL_VALUE_ALREADY_PRESENT_NO_WRITE"
                restored = {"control": device.control_value()}
                require(restored["control"] == "auto", "RESTORE_READBACK_NOT_VERIFIED")
                result["original_value_verified"] = True
                result["after_restore"] = restored
                cleanup_emit("restore-readback", restored)
            except BaseException as exc:
                result["restoration_error"] = type(exc).__name__ + ": " + str(exc)
                result["outcome_unknown"] = True
        result["signals_received"] = list(signals.received)
    complete = (result["on_write_acknowledged"] and result["observation_complete"] and
                result["original_value_verified"] and "error" not in result and
                "restoration_error" not in result and "cleanup_evidence_errors" not in result)
    result["state"] = ("ON_WINDOW_OBSERVED_ORIGINAL_VALUE_VERIFIED" if complete else
                       "STOPPED_WITHOUT_POWER_WRITE" if not result["on_write_attempts"] else
                       "CONTRAST_INCOMPLETE_RESTORED" if result["original_value_verified"] else
                       "CONTRAST_INCOMPLETE_RESTORATION_UNVERIFIED")
    return result


@contextmanager
def ui_lock():
    fd = os.open(UI_LOCK, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        value = os.fstat(fd)
        require(stat.S_ISREG(value.st_mode) and value.st_uid == 0 and value.st_nlink == 1,
                "UI_LOCK_IDENTITY_INVALID")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


class Evidence:
    def __init__(self, directory):
        self.root = Path(directory)
        require(self.root.is_absolute(), "ABSOLUTE_NEW_RESULT_DIRECTORY_REQUIRED")
        self.root.mkdir(mode=0o700)  # Create-only: rerunning this trial path fails.
        self.fd = os.open(self.root / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                          os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)

    def emit(self, kind, data):
        payload = (json.dumps({"event": kind, "monotonic_ns": time.monotonic_ns(),
                               "utc_unix_ns": time.time_ns(), "data": data},
                              sort_keys=True) + "\n").encode()
        with os.fdopen(os.dup(self.fd), "ab", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    def finish(self, result):
        self.emit("terminal", result)
        fd = os.open(self.root / "result.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        parent = os.open(self.root, DIR_FLAGS)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)

    def close(self):
        os.close(self.fd)


def plan():
    return {"state": "PLAN_ONLY", "host_reads_performed": False, "sysfs_writes": 0,
            "target": {"alias": ALIAS, "required_canonical": CANONICAL, **IDENTITY},
            "kernel_required": KERNEL, "observation_seconds": SECONDS,
            "execute_preconditions": ["explicit execute mode and fresh expected boot_id",
                "target present now, complete exact identity, same retained sysfs generation",
                "target own power/control=auto and 0<=autosuspend_delay_ms<30000",
                "existing cooperative Android action lock acquired nonblocking",
                "new create-only evidence directory"],
            "maximum_power_writes": {"on": 1, "restore_auto_same_fd": 1},
            "wait_for_future_device": False, "provider_or_ui_actions": 0,
            "causality_or_production_qualification": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-boot-id")
    parser.add_argument("--result-dir")
    args = parser.parse_args()
    if not args.preflight and not args.execute:
        print(json.dumps(plan(), indent=2))
        return 0
    if args.preflight:
        result = {"state": "PREFLIGHT_BLOCKED", "sysfs_writes": 0, "wait_for_future_device": False}
        device = None
        try:
            result["host"] = host_identity(args.expected_boot_id)
            device = HeldDevice(False, args.expected_boot_id)
            result.update(state="PREFLIGHT_READ_ONLY", binding=device.binding(), device=device.snapshot())
        except BaseException as exc:
            result["error"] = type(exc).__name__ + ": " + str(exc)
        finally:
            if device is not None:
                device.close()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["state"] == "PREFLIGHT_READ_ONLY" else 2
    require(os.getuid() == os.geteuid() == 0, "HOST_ROOT_REQUIRED")
    require(args.expected_boot_id is not None and args.result_dir is not None,
            "EXECUTE_REQUIRES_EXPLICIT_FRESH_BOOT_BINDING_AND_NEW_RESULT_DIRECTORY")
    host_identity(args.expected_boot_id)
    signals = SignalState()
    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, signals.handler)
    with ui_lock():
        evidence = Evidence(args.result_dir)
        device = None
        result = {"state": "STOPPED_WITHOUT_POWER_WRITE", "on_write_attempts": 0,
                  "restore_write_attempts": 0, "original_value_verified": False}
        try:
            device = HeldDevice(True, args.expected_boot_id)
            binding = device.binding()
            evidence.emit("binding", binding)
            result = run_trial(device, evidence.emit, signals)
            result["binding"] = binding
        except BaseException as exc:
            result["error"] = type(exc).__name__ + ": " + str(exc)
        finally:
            signals.restoring = True
            if device is not None:
                device.close()
            result.update(schema="pocket4-single-device-pm-contrast-v1",
                          source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          automatic_retry=False, wait_for_future_device=False,
                          device_ui_actions=0, capture_actions=0, provider_changes=0,
                          global_parameter_changes=0, power_reset_actions=0,
                          production_ready=False)
            evidence.finish(result)
            evidence.close()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] == "ON_WINDOW_OBSERVED_ORIGINAL_VALUE_VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
