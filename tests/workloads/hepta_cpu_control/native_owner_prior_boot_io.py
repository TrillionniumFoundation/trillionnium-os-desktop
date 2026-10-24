"""Actual two-boot transport, before the separate original-owner oracle.

One held host inode is used by both QEMU processes. Only the existing runner
formats it, once. Copies made while QEMU is stopped are forensic artifacts;
they are never the next boot's drive. This module produces no passing native
qualification and never interprets an observer error as a durable outcome.
"""
import fcntl
import hashlib
import os
from pathlib import Path
import selectors
import signal
import stat
import struct
import subprocess
import time

import native_owner_evidence as evidence
import native_owner_inputs as inputs
import run_native_owner as original


require = evidence.require


def qemu_argv(binary, output, boot_directory, state):
    """Original machine/profile, opening the exact inherited campaign inode."""
    return original.qemu_argv(binary, output, boot_directory, False) + [
        "-drive", "if=none,format=raw,id=hepta_g2_state,file=" + state.child_path,
        "-device", "virtio-blk-pci,bus=pcie.0,addr=0x8,drive=hepta_g2_state,disable-legacy=on,disable-modern=off"]


class SameStateDisk:
    """Hold and recheck the exact raw image throughout the two actual boots."""

    def __init__(self, path, initial_sha256):
        self.path = Path(path)
        require(self.path.is_absolute() and self.path.resolve(strict=True) == self.path
                and not self.path.is_symlink(), "canonical original physical state image required")
        self.fd = os.open(self.path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            meta = os.fstat(self.fd)
            require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1
                    and meta.st_size == original.STATE_BYTES,
                    "original state image must be a unique unchanged-size regular inode")
            self.identity = (meta.st_dev, meta.st_ino)
            self.uuid = self.superblock_uuid()
            self.initial = self.observe(initial_sha256)
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.fd)
        self.fd = None

    @property
    def child_path(self):
        require(type(self.fd) is int and self.fd >= 3, "held original state descriptor required")
        return "/proc/self/fd/" + str(self.fd)

    def descriptor_binding(self):
        meta = self._same_inode()
        require(fcntl.fcntl(self.fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDWR,
                "actual QEMU must inherit the original read/write state descriptor")
        return {"source_path": str(self.path), "inherited_fd": self.fd, "qemu_path": self.child_path,
                "host_device": meta.st_dev, "host_inode": meta.st_ino, "bytes": meta.st_size,
                "binding": "pass_fds; QEMU opens its inherited /proc/self/fd descriptor"}

    def _same_inode(self):
        held = os.fstat(self.fd)
        named = self.path.lstat()
        require(stat.S_ISREG(named.st_mode) and stat.S_ISREG(held.st_mode)
                and named.st_nlink == held.st_nlink == 1
                and named.st_size == held.st_size == original.STATE_BYTES
                and (held.st_dev, held.st_ino) == (named.st_dev, named.st_ino) == self.identity
                and self.path.resolve(strict=True) == self.path,
                "second boot cannot replace, copy, resize, alias or redirect the original raw inode")
        return held

    def superblock_uuid(self):
        raw = os.pread(self.fd, 1024, 1024)
        require(len(raw) == 1024 and struct.unpack_from("<H", raw, 56)[0] == 0xEF53
                and struct.unpack_from("<I", raw, 24)[0] == 2
                and struct.unpack_from("<H", raw, 88)[0] == 256
                and struct.unpack_from("<I", raw, 92)[0] == 0
                and struct.unpack_from("<I", raw, 96)[0] == 2
                and struct.unpack_from("<I", raw, 100)[0] == 0 and any(raw[104:120]),
                "same original ext2/no-journal physical filesystem required")
        return raw[104:120].hex()

    def digest(self):
        self._same_inode()
        digest = hashlib.sha256()
        offset = 0
        while offset < original.STATE_BYTES:
            part = os.pread(self.fd, min(1024 * 1024, original.STATE_BYTES - offset), offset)
            require(part, "actual retained physical image was truncated during hashing")
            digest.update(part)
            offset += len(part)
        self._same_inode()
        return digest.hexdigest()

    def observe(self, expected_sha256=None):
        meta = self._same_inode()
        require(self.superblock_uuid() == self.uuid, "original physical filesystem UUID changed between boots")
        digest = self.digest()
        if expected_sha256 is not None:
            require(digest == evidence.digest(expected_sha256, "expected stopped disk digest"),
                    "state bytes changed between the actual stopped observation and the next boot")
        return {"path": str(self.path), "host_device": meta.st_dev, "host_inode": meta.st_ino,
                "bytes": meta.st_size, "links": meta.st_nlink, "ext2_uuid": self.uuid, "sha256": digest}

    def retain_stopped_copy(self, destination, expected_sha256):
        destination = Path(destination)
        require(destination.is_absolute() and not destination.exists() and not destination.is_symlink()
                and destination != self.path, "new forensic-only stopped image required")
        before = self.observe(expected_sha256)
        with destination.open("xb") as output:
            offset = 0
            while offset < original.STATE_BYTES:
                part = os.pread(self.fd, min(1024 * 1024, original.STATE_BYTES - offset), offset)
                require(part, "physical image changed while retaining its stopped bytes")
                output.write(part)
                offset += len(part)
            output.flush()
            os.fsync(output.fileno())
        destination.chmod(0o444)
        require(inputs.sha(destination) == before["sha256"] and self.observe() == before,
                "forensic copy differs from the exact stopped original disk")
        return {"path": str(destination), "bytes": original.STATE_BYTES, "sha256": before["sha256"],
                "execution_input": False, "purpose": "read-only evidence of the stopped physical disk"}

    def require_drive(self, argv):
        self._same_inode()
        expected = "if=none,format=raw,id=hepta_g2_state,file=" + self.child_path
        require(argv.count("-drive") == 1 and argv[argv.index("-drive") + 1] == expected
                and not any(option in argv for option in ("-snapshot", "-loadvm", "-incoming", "-blockdev")),
                "both actual QEMU processes must use the same original physical raw drive")


def run_until_actual_cut(argv, directory, timeout, qemu_identity, state, inspect_complete_line):
    """Kill this actual VM immediately after the source-bound Root cut event.

The caller supplies the fixed producer-schema reader, which performs no file
or network I/O. It returns None for non-cut lines or the checked actual cut
DTO. Timing is retained in the host monotonic clock; it is never relabeled as
guest BOOTTIME. The final transcript/disk oracle is still mandatory.
    """
    require(callable(inspect_complete_line), "actual first-boot cut reader required")
    return _run_actual_boot(argv, directory, timeout, qemu_identity, state, inspect_complete_line)


def run_until_actual_poweroff(argv, directory, timeout, qemu_identity, state):
    """Second actual VM consumes the same held inode and must return raw 33."""
    return _run_actual_boot(argv, directory, timeout, qemu_identity, state, None)


def _run_actual_boot(argv, directory, timeout, qemu_identity, state, inspect_complete_line):
    directory = Path(directory)
    is_cut = inspect_complete_line is not None
    require(type(timeout) is int and 1 <= timeout <= 120, "original finite per-boot deadline required")
    state.require_drive(argv)
    require(argv == qemu_argv(argv[0], Path(argv[argv.index("-kernel") + 1]).parent, directory, state),
            "actual boot changed the original QEMU machine, flags or disk topology")
    require(qemu_identity["path"] == argv[0] and inputs.sha(Path(argv[0])) == qemu_identity["sha256"],
            "actual selected QEMU bytes differ before boot")
    record = {"argv": argv, "qemu": qemu_identity, "timeout_seconds": timeout,
              "raw_exit_code": None, "timed_out": False, "serial_excessive": False,
              "host_cut": None, "artifacts": {}, "state_descriptor": state.descriptor_binding(),
              "pass_fds": [state.fd],
              "profile": {"machine": "q35", "accel": "tcg", "cpu": "max", "memory_mib": 512,
                          "vcpus": 1, "network": False},
              "failure_layer": ("actual QEMU VM process killed; no physical host power-loss claim"
                                if is_cut else "original guest poweroff; unresolved old operation retained")}
    for option in ("-kernel", "-initrd", "-bios"):
        path = Path(argv[argv.index(option) + 1])
        record["artifacts"][option] = {"path": str(path), "bytes": path.stat().st_size, "sha256": inputs.sha(path)}
    original.save(directory / "qemu.json", record)
    started = time.monotonic_ns()
    process = subprocess.Popen(argv, env=original.ENV, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
                               pass_fds=(state.fd,))
    selector = selectors.DefaultSelector()
    total, line_offset, pending, eof = 0, 0, bytearray(), False
    post_kill_deadline = None
    processing_error = None
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        with (directory / "serial.log").open("xb") as log:
            while True:
                now = time.monotonic_ns()
                remaining_ns = (started + timeout * 1_000_000_000 - now if post_kill_deadline is None
                                else post_kill_deadline - now)
                if remaining_ns <= 0:
                    record["timed_out"] = True
                    break
                for key, _ in selector.select(min(remaining_ns / 1_000_000_000, 0.05)):
                    content = os.read(key.fd, 65_536)
                    if not content:
                        selector.unregister(key.fd)
                        eof = True
                        continue
                    allowed = min(len(content), evidence.MAX_SERIAL_BYTES - total)
                    log.write(content[:allowed])
                    total += allowed
                    if allowed != len(content):
                        record["serial_excessive"] = True
                        break
                    if not is_cut or record["host_cut"] is not None:
                        # Preserve all bytes already emitted before SIGKILL.
                        # The full source oracle rejects any later owner event.
                        continue
                    pending.extend(content)
                    while b"\n" in pending:
                        raw_line, _, tail = pending.partition(b"\n")
                        line = bytes(raw_line) + b"\n"
                        pending = bytearray(tail)
                        observed_at = time.monotonic_ns()
                        cut = inspect_complete_line(line)
                        if cut is not None:
                            require(process.poll() is None, "actual VM exited before the observed cut could be killed")
                            before_kill = time.monotonic_ns()
                            os.killpg(process.pid, signal.SIGKILL)
                            after_kill = time.monotonic_ns()
                            record["host_cut"] = {"signal": signal.SIGKILL, "process_group": process.pid,
                                "line_offset": line_offset, "line_bytes": len(line),
                                "line_sha256": hashlib.sha256(line).hexdigest(), "original_cut": cut,
                                "clock": "host time.monotonic_ns",
                                "observed_at_ns": observed_at, "kill_call_before_ns": before_kill,
                                "kill_call_after_ns": after_kill, "guest_time_inferred": False}
                            post_kill_deadline = after_kill + 10_000_000_000
                            break
                        line_offset += len(line)
                    require(len(pending) <= evidence.MAX_EVENT_BYTES + len(evidence.PREFIX) + 2,
                            "first-boot serial contains an unbounded incomplete line")
                if record["serial_excessive"] or (eof and process.poll() is not None):
                    break
    except BaseException as error:
        processing_error = error
        record["transport_error"] = f"{type(error).__name__}: {error}"
    finally:
        selector.close()
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=10)
        process.stdout.close()
        raw = (directory / "serial.log").read_bytes()
        record.update(raw_exit_code=process.returncode, elapsed_seconds=(time.monotonic_ns() - started) / 1_000_000_000,
                      serial_sha256=hashlib.sha256(raw).hexdigest(), serial_bytes=len(raw))
        original.save(directory / "qemu.json", record)
    if processing_error is not None:
        raise processing_error
    require(not record["timed_out"] and not record["serial_excessive"] and eof,
            "actual bounded VM serial/exit observation is incomplete")
    if is_cut:
        require(record["host_cut"] is not None and record["raw_exit_code"] == -signal.SIGKILL,
                "first boot did not end in an actual complete source-cut SIGKILL observation")
    else:
        require(record["host_cut"] is None and record["raw_exit_code"] == 33,
                "second boot did not finish through original guest poweroff/raw 33")
    state.require_drive(argv)
    require(inputs.sha(Path(argv[0])) == qemu_identity["sha256"], "actual QEMU changed during boot")
    for artifact in record["artifacts"].values():
        path = Path(artifact["path"])
        require(path.stat().st_size == artifact["bytes"] and inputs.sha(path) == artifact["sha256"],
                "actual boot input changed during VM execution")
    return raw, record
