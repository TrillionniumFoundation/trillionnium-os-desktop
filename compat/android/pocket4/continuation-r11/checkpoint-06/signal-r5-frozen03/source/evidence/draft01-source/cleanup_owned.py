"""Exact owned-unit retirement that survives independent evidence failures.

The only mutable targets are the four nonce-bound private units in ROWS.
Unknown or changed identity never licenses a stop. Cgroup events and pids.current
are hierarchical counters; an empty root cgroup.procs is not a retirement proof.
"""
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

class CgroupProof:
    """Hold a particular cgroup directory across the one permitted stop."""
    def __init__(self, root, group):
        self.root = Path(root)
        self.group = group
        require(group.startswith("/") and "//" not in group and
                all(part not in ("", ".", "..") for part in group[1:].split("/")),
                "invalid control group path")
        self.path = self.root / group[1:]
        self.fd = -1
        self.identity = None
        try:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY |
                              os.O_CLOEXEC | os.O_NOFOLLOW)
        except FileNotFoundError:
            return
        value = os.fstat(self.fd)
        require(stat.S_ISDIR(value.st_mode), "control group is not a directory")
        self.identity = {"device": value.st_dev, "inode": value.st_ino}

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
        if current is not None:
            require(self.identity == {"device": current.st_dev, "inode": current.st_ino},
                    "control group directory was replaced")
        else:
            # A rename is not deletion: keep reading the held original
            # directory unless its link count proves it was unlinked.
            if before.st_nlink == 0:
                return {"path": self.group, "absent": True,
                        "held_identity": self.identity, "held_nlink": 0,
                        "hierarchical_population_checked": True,
                        "proof": "held original cgroup directory unlinked; populated cgroups cannot be removed"}
        events = parse_events(read_at(self.fd, "cgroup.events", 4096))
        pids = read_at(self.fd, "pids.current", 128).strip()
        require(pids.isdigit(), "hierarchical pids.current absent or invalid")
        root_procs = read_at(self.fd, "cgroup.procs").split()
        require(all(value.isdigit() for value in root_procs), "cgroup.procs is invalid")
        after = os.fstat(self.fd)
        require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino) ==
                (self.identity["device"], self.identity["inode"]),
                "held control group identity changed")
        return {"path": self.group, "absent": False, "held_identity": self.identity,
                "path_present": current is not None,
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
    def __init__(self, scope, *, cgroup_root=Path("/sys/fs/cgroup")):
        self.s = scope
        # Test-only dependency injection supplies a declared regular-file
        # counter fixture. Production install() exposes no root override.
        self.cgroup_root = Path(cgroup_root)
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
            proof = CgroupProof(self.cgroup_root, row["group"])
            before = proof.sample()
            report["before"] = before
            # A unit may already have exited and been collected. This branch
            # never sends a stop and still requires the original cgroup empty.
            gone = current.get("LoadState") == "not-found"
            inactive_same = (current.get("InvocationID") == row["invocation"] and
                             current.get("Description") == row["description"] and
                             current.get("ControlGroup") in ("", row["group"]) and
                             current.get("ActiveState") in ("inactive", "failed"))
            if (gone or inactive_same) and current.get("MainPID", "0") == "0" and CgroupProof.empty(before):
                report.update(retired=True, already_inactive=True, final=current, after=before)
                return
            self.exact(row, current)
            # Do not use MainPID as a process-tree liveness test. The unit may
            # own nested child cgroups even when its main process is absent.
            report["stop_attempted"] = True
            try:
                response = self.s["call"](["/usr/bin/systemctl", "stop", row["unit"]], 45, check=False)
                report["stop_returncode"] = response.returncode
                require(response.returncode == 0, "exact unit stop command failed")
            except BaseException as error:
                self.error("unit-stop:" + row["unit"], error)
            # A command error does not suppress the independent final read.
            final = self.s["props"](row["unit"])
            report["final"] = final
            require(final.get("MainPID", "0") == "0" and
                    final.get("ActiveState", "inactive") in ("inactive", "failed"),
                    "unit still has a main process or active state")
            require(final.get("LoadState") == "not-found" or
                    (final.get("InvocationID") == row["invocation"] and
                     final.get("Description") == row["description"] and
                     final.get("ControlGroup") in ("", row["group"])),
                    "unit generation changed during retirement")
            after = proof.sample()
            report["after"] = after
            require(CgroupProof.empty(after), "owned hierarchical cgroup remains populated")
            report["retired"] = True
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
