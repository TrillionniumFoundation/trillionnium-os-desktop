"""Exact owned-unit retirement that survives independent evidence failures.

The only mutable targets are the four nonce-bound private units in ROWS.
Unknown or changed identity never licenses a stop. Cgroup events and pids.current
are hierarchical counters; an empty root cgroup.procs is not a retirement proof.
"""
import ctypes
import errno
import os
from pathlib import Path
import re
import stat
import time

ROLES = ("bus", "sway", "presenter", "daemon")

class CleanupError(RuntimeError):
    pass

def require(value, message):
    if not value:
        raise CleanupError(message)

def read_at(directory, name, limit=65536):
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory)
    try:
        result = bytearray()
        while True:
            part = os.read(fd, min(4096, limit + 1 - len(result)))
            if not part:
                return bytes(result).decode("ascii", "strict")
            result.extend(part)
            require(len(result) <= limit, "cgroup counter exceeds read bound")
    finally:
        os.close(fd)

def parse_events(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        require(len(fields) == 2 and fields[0] not in result and fields[1].isdigit(),
                "malformed cgroup events")
        result[fields[0]] = int(fields[1])
    require(result.get("populated") in (0, 1), "hierarchical populated counter absent")
    return result

CGROUP2_SUPER_MAGIC = 0x63677270

def filesystem_type(fd):
    require(os.uname().machine == "x86_64", "qualified host cgroup proof is x86_64 only")
    # The host's x86_64 statfs structure fits in 256 bytes; f_type is its first
    # native long. No target Android ABI structure is passed through here.
    libc = ctypes.CDLL(None, use_errno=True)
    buffer = ctypes.create_string_buffer(256)
    method = libc.fstatfs
    method.argtypes = (ctypes.c_int, ctypes.c_void_p)
    method.restype = ctypes.c_int
    if method(fd, ctypes.byref(buffer)) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return ctypes.c_long.from_buffer(buffer).value

class CgroupProof:
    """Hold a particular cgroup directory across the one permitted stop."""
    def __init__(self, root, group, *, allow_regular_counter_fixture=False):
        self.root = Path(root)
        self.group = group
        require(group.startswith("/") and "//" not in group and
                all(part not in ("", ".", "..") for part in group[1:].split("/")),
                "invalid control group path")
        self.path = self.root / group[1:]
        self.fd = -1
        self.identity = None
        self.fs_type = None
        self.allow_regular_counter_fixture = allow_regular_counter_fixture
        try:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY |
                              os.O_CLOEXEC | os.O_NOFOLLOW)
        except FileNotFoundError:
            return
        try:
            value = os.fstat(self.fd)
            require(stat.S_ISDIR(value.st_mode), "control group is not a directory")
            self.identity = {"device": value.st_dev, "inode": value.st_ino}
            self.fs_type = filesystem_type(self.fd)
            require(self.fs_type == CGROUP2_SUPER_MAGIC or allow_regular_counter_fixture,
                    "held directory is not cgroup v2")
        except BaseException:
            self.close()
            raise

    def sample(self):
        try:
            current = self.path.stat(follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if self.fd < 0:
            require(current is None, "control group appeared after absence")
            return {"path": self.group, "absent": True, "held_identity": None,
                    "hierarchical_population_checked": True,
                    "proof": "path absent at both observations; no cgroup FD was ever acquired"}
        before = os.fstat(self.fd)
        require((before.st_dev, before.st_ino) ==
                (self.identity["device"], self.identity["inode"]),
                "held original cgroup identity changed")
        if current is not None:
            require(self.identity == {"device": current.st_dev, "inode": current.st_ino},
                    "control group directory was replaced")
        try:
            events_text = read_at(self.fd, "cgroup.events", 4096)
        except OSError as error:
            # On this actual cgroupfs, rmdir leaves held-directory nlink=2.
            # The always-present cgroup.events and cgroup.procs disappear on
            # deactivation; a mere rename keeps both accessible through fd.
            require(error.errno == errno.ENOENT and current is None and
                    self.fs_type == CGROUP2_SUPER_MAGIC,
                    "cgroup event observation failed without a deletion proof")
            try:
                read_at(self.fd, "cgroup.procs")
            except OSError as second:
                require(second.errno == errno.ENOENT,
                        "original cgroup process-file disappearance is unproved")
            else:
                raise CleanupError("original cgroup still exposes its process file")
            require(not self.path.exists(), "replacement cgroup appeared during deletion proof")
            after = os.fstat(self.fd)
            require((after.st_dev, after.st_ino) == (before.st_dev, before.st_ino),
                    "held cgroup descriptor changed during deletion proof")
            return {"path": self.group, "absent": True, "held_identity": self.identity,
                    "filesystem_type": self.fs_type, "held_nlink": after.st_nlink,
                    "hierarchical_population_checked": True,
                    "proof": "original cgroup2 directory held; path absent; both mandatory controls removed"}
        events = parse_events(events_text)
        pids = read_at(self.fd, "pids.current", 128).strip()
        require(pids.isdigit(), "hierarchical pids.current absent or invalid")
        root_procs = read_at(self.fd, "cgroup.procs").split()
        require(all(value.isdigit() for value in root_procs), "cgroup.procs is invalid")
        after = os.fstat(self.fd)
        require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino) ==
                (self.identity["device"], self.identity["inode"]),
                "held control group identity changed")
        return {"path": self.group, "absent": False, "held_identity": self.identity,
                "filesystem_type": self.fs_type, "path_present": current is not None,
                "events": events, "pids_current": int(pids),
                "root_processes": [int(value) for value in root_procs],
                "hierarchical_population_checked": True}

    @staticmethod
    def empty(sample):
        return sample["absent"] or (sample["events"]["populated"] == 0 and
                                   sample["pids_current"] == 0 and
                                   not sample["root_processes"])

    def close(self):
        if self.fd >= 0:
            fd, self.fd = self.fd, -1
            os.close(fd)

class OwnedCleanup:
    def __init__(self, scope, *, cgroup_root=Path("/sys/fs/cgroup"), allow_regular_counter_fixture=False):
        self.s = scope
        # Test-only dependency injection supplies a declared regular-file
        # counter fixture. Production install() exposes no root override.
        self.cgroup_root = Path(cgroup_root)
        self.allow_regular_counter_fixture = allow_regular_counter_fixture
        self.errors = []
        self.retirements = []
        self.reconciliations = []

    def error(self, phase, error):
        message = phase + ": " + repr(error)
        self.errors.append(message)
        self.s["RESULT"].setdefault("first_cleanup_error", message)
        return message

    def save(self, name, value):
        try:
            self.s["save"](name, value)
            return True
        except BaseException as error:
            self.error("cleanup-evidence-write:" + name, error)
            return False

    def planned(self, row):
        role = row.get("role")
        require(role in ROLES and row.get("unit") == self.s["NAME"] + "-" + role + ".service"
                and row.get("description") == self.s["NAME"] + " " + self.s["NONCE"] + " " + role,
                "row is not one of this exact nonce's private units")
        require(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,200}", self.s["NAME"]) and
                re.fullmatch(r"[0-9a-f]{32}", self.s["NONCE"]),
                "private unit name or nonce is invalid")
        return "/system.slice/" + row["unit"]

    def exact(self, row, observed):
        expected_group = self.planned(row)
        require(re.fullmatch(r"[0-9a-f]{32}", row.get("invocation", "")) is not None,
                "unit invocation was never established")
        require(row.get("group") == expected_group and
                observed.get("InvocationID") == row["invocation"] and
                observed.get("Description") == row["description"] and
                observed.get("ControlGroup") == expected_group,
                "unit InvocationID/Description/ControlGroup differs")
        return observed

    def reconcile(self):
        for row in self.s["ROWS"]:
            try:
                expected_group = self.planned(row)
                if row.get("invocation"):
                    require(row.get("group") == expected_group,
                            "established control group differs from the private unit")
                    continue
                current = self.s["props"](row["unit"])
                report = {"unit": row["unit"], "observed": current, "action_taken": False}
                self.reconciliations.append(report)
                if current.get("LoadState") == "not-found":
                    # No generation was established. Absence is recorded, not
                    # upgraded to permission to act on a guessed generation.
                    row["absent_at_reconciliation"] = True
                    require(not (self.cgroup_root / expected_group[1:]).exists(),
                            "unbound unit has a surviving control group")
                    raise CleanupError("launch generation was never observed; absence is not a retirement proof")
                require(current.get("Description") == row["description"] and
                        re.fullmatch(r"[0-9a-f]{32}", current.get("InvocationID", "")) and
                        current.get("ControlGroup") == expected_group,
                        "ambiguous unit generation; no stop authorized")
                row.update(invocation=current["InvocationID"], group=expected_group,
                           reconciled_after_launch_error=True)
                report["exact_generation_established"] = True
            except BaseException as error:
                self.error("unit-reconciliation:" + str(row.get("unit")), error)

    def collect_resources(self):
        resources = []
        for row in self.s["ROWS"]:
            if not row.get("invocation"):
                continue
            try:
                self.exact(row, self.s["props"](row["unit"]))
                value = self.s["call"](["/usr/bin/systemctl", "show", row["unit"],
                    "-p", "CPUUsageNSec", "-p", "MemoryPeak", "-p", "MemoryCurrent",
                    "-p", "MemoryMax", "-p", "MemorySwapMax", "-p", "CPUQuotaPerSecUSec"], check=False)
                require(value.returncode == 0, "owned resource property query failed")
                item = {"unit": row["unit"], "properties": value.stdout.decode()}
                group = self.cgroup_root / row["group"][1:]
                for name in ("memory.events", "memory.pressure", "cpu.pressure"):
                    item[name] = (group / name).read_text()
                resources.append(item)
            except BaseException as error:
                resources.append({"unit": row["unit"], "error": repr(error)})
        try:
            group = Path("/proc/self/cgroup").read_text().strip().split("0::", 1)[1]
            actor = self.cgroup_root / group[1:]
            item = {"unit": "current-owned-controller-actor", "cgroup": str(actor)}
            for name in ("memory.events", "memory.pressure", "cpu.pressure",
                         "memory.peak", "memory.max", "memory.swap.max", "cpu.max"):
                item[name] = (actor / name).read_text().strip()
            resources.append(item)
        except BaseException as error:
            resources.append({"unit": "current-owned-controller-actor", "error": repr(error)})
        for item in resources:
            try:
                require("error" not in item, "owned resource observation failed")
                events = dict((key, int(value)) for key, value in
                              (line.split() for line in item["memory.events"].splitlines()))
                require(all(events.get(key) == 0 for key in ("oom", "oom_kill", "oom_group_kill")),
                        "owned memory OOM counters nonzero or missing")
            except BaseException as error:
                self.error("owned-memory-events:" + str(item.get("unit")), error)
        self.s["RESULT"]["owned_memory_events_zero"] = not any(
            value.startswith("owned-memory-events:") for value in self.errors)
        self.s["RESULT"]["cleanup_resource_observations"] = resources
        self.save("resources-before-cleanup.json", resources)

    def cell_stop(self):
        daemon = next((row for row in self.s["ROWS"]
                       if row["role"] == "daemon" and row.get("invocation")), None)
        if daemon is None:
            return
        try:
            current = self.exact(daemon, self.s["props"](daemon["unit"]))
            if int(current.get("MainPID", "0")) > 0 and self.s["SOCK"].exists():
                result = self.s["ctl"]("stop")
                self.save("stop-cell.json", result)
                require(result.get("ok") and result.get("state") == "stopped",
                        "private cell stop was not acknowledged")
        except BaseException as error:
            self.error("cell-stop", error)

    def retire(self, row):
        report = {"unit": row.get("unit"), "role": row.get("role"),
                  "stop_attempted": False, "retired": False, "automatic_retry": False}
        self.retirements.append(report)
        proof = None
        try:
            expected_group = self.planned(row)
            if not row.get("invocation"):
                current = self.s["props"](row["unit"])
                require(row.get("absent_at_reconciliation") is True and
                        current.get("LoadState") == "not-found" and
                        not (self.cgroup_root / expected_group[1:]).exists(),
                        "unbound unit cannot be retired")
                report["never_bound_unit_remains_absent"] = True
                raise CleanupError("unknown launch generation; no stop or completed-retirement claim")
            require(row.get("group") == expected_group and
                    re.fullmatch(r"[0-9a-f]{32}", row.get("invocation", "")) is not None,
                    "established unit binding is incomplete or wrong")
            current = self.s["props"](row["unit"])
            exact = (current.get("InvocationID") == row["invocation"] and
                     current.get("Description") == row["description"] and
                     current.get("ControlGroup") == expected_group)
            gone = current.get("LoadState") == "not-found"
            inactive_same = (current.get("InvocationID") == row["invocation"] and
                             current.get("Description") == row["description"] and
                             current.get("ControlGroup") in ("", expected_group) and
                             current.get("ActiveState") in ("inactive", "failed"))
            # Never touch an unknown/changed manager generation.
            require(exact or gone or inactive_same,
                    "unit InvocationID/Description/ControlGroup differs")
            try:
                proof = CgroupProof(self.cgroup_root, row["group"],
                    allow_regular_counter_fixture=self.allow_regular_counter_fixture)
                report["before"] = proof.sample()
            except BaseException as error:
                report["before_error"] = self.error("unit-cgroup-before:" + row["unit"], error)
            if not exact:
                # No stop is authorized after the manager forgot the group.
                # A passive, complete old-group proof is still required.
                require(current.get("MainPID", "0") == "0" and
                        "before" in report and CgroupProof.empty(report["before"]),
                        "unbound manager state does not prove old owned subtree empty")
                report.update(retired=True, already_inactive=True, final=current, after=report["before"])
                return
            # Re-read the exact manager identity immediately before the one
            # stop. Earlier diagnostic I/O failure does not block retirement.
            self.exact(row, self.s["props"](row["unit"]))
            report["stop_attempted"] = True
            try:
                response = self.s["call"](["/usr/bin/systemctl", "stop", row["unit"]], 45, check=False)
                report["stop_returncode"] = response.returncode
                require(response.returncode == 0, "exact unit stop command failed")
            except BaseException as error:
                self.error("unit-stop:" + row["unit"], error)
            final_ok = after_ok = False
            try:
                final = self.s["props"](row["unit"])
                report["final"] = final
                require(final.get("MainPID", "0") == "0" and
                        final.get("ActiveState", "inactive") in ("inactive", "failed"),
                        "unit still has a main process or active state")
                require(final.get("LoadState") == "not-found" or
                        (final.get("InvocationID") == row["invocation"] and
                         final.get("Description") == row["description"] and
                         final.get("ControlGroup") in ("", expected_group)),
                        "unit generation changed during retirement")
                final_ok = True
            except BaseException as error:
                self.error("unit-final-manager:" + row["unit"], error)
            try:
                if proof is None:
                    proof = CgroupProof(self.cgroup_root, row["group"],
                        allow_regular_counter_fixture=self.allow_regular_counter_fixture)
                after = proof.sample()
                report["after"] = after
                require(CgroupProof.empty(after), "owned hierarchical cgroup remains populated")
                after_ok = True
            except BaseException as error:
                self.error("unit-final-cgroup:" + row["unit"], error)
            report["retired"] = final_ok and after_ok
        except BaseException as error:
            report["error"] = self.error("unit-retirement:" + str(row.get("unit")), error)
        finally:
            if proof is not None:
                try:
                    proof.close()
                except BaseException as error:
                    self.error("cgroup-proof-release:" + str(row.get("unit")), error)
            if row.get("invocation"):
                try:
                    journal = self.s["call"](["/usr/bin/journalctl", "-u", row["unit"],
                        "_SYSTEMD_INVOCATION_ID=" + row["invocation"],
                        "-b", "--no-pager", "-n", "160"], check=False)
                    require(journal.returncode == 0, "owned unit journal query failed")
                    self.save("journal-" + row["role"] + ".txt", journal.stdout)
                except BaseException as error:
                    self.error("unit-journal:" + str(row.get("unit")), error)

    def final_readbacks(self):
        init = self.s["INIT"]
        if init:
            try:
                require(not Path("/proc/" + str(init["pid"])).exists() or
                        self.s["proc"](init["pid"]) != init,
                        "original private init remains alive")
            except BaseException as error:
                self.error("init-liveness", error)
        for name, operation in (
            ("Main-preservation", self.main_after),
            ("Main-resources", self.main_resources_after),
            ("source-contract", self.source_after),
        ):
            try:
                operation()
            except BaseException as error:
                self.error(name, error)

    def main_after(self):
        result = self.s["RESULT"]
        after = self.s["main_snapshot"]()
        result["main_after"] = after
        result["main_preserved"] = after == self.s["P"]["main_before"]
        require(result["main_preserved"], "Main generation changed")

    def main_resources_after(self):
        result = self.s["RESULT"]
        after = self.s["main_resources"]()
        result["main_resources_after"] = after
        require(after == result["main_resources_before"], "Main resource contract changed")

    def source_after(self):
        result = self.s["RESULT"]
        after = self.s["source_contract"]()
        result["source_contract_after"] = after
        result["source_contract_preserved"] = after == result["source_contract_before"]
        require(result["source_contract_preserved"], "source contract changed")

    def run(self):
        # Install the result early, so even an unexpected recording error has
        # an in-memory terminal record. One cleanup invocation is permitted.
        require(not self.s["RESULT"].get("cleanup_started"), "cleanup is not replayable")
        self.s["RESULT"]["cleanup_started"] = True
        self.s["RESULT"]["cleanup"] = {
            "errors": self.errors, "units": self.s["ROWS"],
            "reconciliations": self.reconciliations, "retirements": self.retirements,
            "runtime_directories_retained_for_inspection": True}
        try:
            self.reconcile()
        except BaseException as error:
            self.error("cleanup-reconciliation", error)
        try:
            self.collect_resources()
        except BaseException as error:
            self.error("cleanup-resources", error)
        if self.s["INIT"]:
            try:
                value = self.s["atext"](["/system/bin/getprop", "init.svc.adbd"], 0)
                self.s["RESULT"]["adbd_before_cleanup"] = value
                require(value == "stopped", "adbd disabled contract differs")
            except BaseException as error:
                self.error("adbd-disabled-contract", error)
        try:
            self.s["release_held_binding"](self.errors)
        except BaseException as error:
            self.error("held-entry-release", error)
        try:
            self.cell_stop()
        except BaseException as error:
            self.error("private-cell-stop", error)
        for row in reversed(self.s["ROWS"]):
            try:
                self.retire(row)
            except BaseException as error:
                self.error("unexpected-unit-retirement:" + str(row.get("unit")), error)
        try:
            self.final_readbacks()
        except BaseException as error:
            self.error("cleanup-final-readbacks", error)
        self.save("owned-retirement.json", self.s["RESULT"]["cleanup"])
        return self.errors

def install(scope):
    original = scope["cleanup"]
    cleanup = OwnedCleanup(scope)
    scope["cleanup_v5_reference"] = original
    scope["cleanup"] = cleanup.run
    scope["owned_cleanup"] = cleanup
