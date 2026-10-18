#!/usr/bin/env python3
"""Break at the complete Asterinas Rust entry, detach, then verify its boot."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import select
import shlex
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import time


ENTRY = "__ostd_main"
HIT = re.compile(r"^A01_GDB_RUST_ENTRY_HIT pc=0x([0-9a-fA-F]+) entry=0x([0-9a-fA-F]+)$",
                 re.MULTILINE)
ENTRY_BYTES = 32
BYTE_HIT = re.compile(r"^A01_GDB_RUST_ENTRY_BYTES pc=0x([0-9a-fA-F]+) size=32 bytes=([0-9a-fA-F]{64})$",
                      re.MULTILINE)


class ShutdownRequested(Exception):
    def __init__(self, signum):
        self.signum = signum
        super().__init__(signal.Signals(signum).name)


class Shutdown:
    """Defer asynchronous shutdown until an owned child has been published."""

    def __init__(self):
        self.signum = None
        self.received = []

    def remember(self, signum, _frame):
        if self.signum is None:
            self.signum = signum
        self.received.append(signal.Signals(signum).name)

    def check(self):
        if self.signum is not None:
            raise ShutdownRequested(self.signum)


@contextmanager
def interruption_handlers():
    shutdown = Shutdown()
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        for number in previous:
            signal.signal(number, shutdown.remember)
        yield shutdown
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def private_osdk_evidence(boot, project):
    """Observe this invocation's private SDK and its install receipt."""
    prefix = Path(boot).resolve() / "osdk"
    binary = prefix / "bin/cargo-osdk"
    keys = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
    identity = lambda value: {key: getattr(value, key) for key in keys}
    descriptor = os.open(binary, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_mode & 0o111,
                "private OSDK is not a regular executable")
        require(identity(binary.lstat()) == identity(before), "private OSDK changed before observation")
        digest = hashlib.sha256()
        for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
            digest.update(chunk)
        require(identity(os.fstat(descriptor)) == identity(before)
                and identity(binary.lstat()) == identity(before), "private OSDK changed during observation")
    finally:
        os.close(descriptor)
    receipt = prefix / "cargo-osdk.sha256"
    require(not receipt.is_symlink(), "private OSDK installation receipt is a symlink")
    raw_receipt = receipt.read_bytes()
    filename = str(binary)
    escaped = filename.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
    line = ("\\" if escaped != filename else "") + digest.hexdigest() + "  " + escaped + "\n"
    require(raw_receipt == line.encode(), "private OSDK differs from this build's installation receipt")
    source = Path(project).resolve() / "kernel/asterinas/osdk"
    return {"path": str(binary), "size": before.st_size, "sha256": digest.hexdigest(),
            "stat": identity(before), "installation_root": str(prefix),
            "source_directory": str(source),
            "source_inputs": {name: {"path": str(source / name), "sha256": sha256(source / name)}
                              for name in ("Cargo.toml", "Cargo.lock")},
            "installation_receipt": {"path": str(receipt), "sha256": hashlib.sha256(raw_receipt).hexdigest()},
            "matches_installation_receipt": True,
            "observation": "private SDK after this debug build reached live QEMU; source inputs are also recorded in environment.json",
            "scope": "post-build path and byte observation; not immutable custody of executed SDK bytes"}


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def own_listener():
    """Keep the actual loopback listener reserved across Bash/make/OSDK execs."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as original:
        original.bind(("127.0.0.1", 0))
        original.listen(1)
        descriptor = fcntl.fcntl(original.fileno(), fcntl.F_DUPFD, 64)
    listener = socket.socket(fileno=descriptor)
    os.set_inheritable(descriptor, False)  # pass_fds grants inheritance to our child.
    return listener


class OwnedSession:
    """Keep our direct child's PID/group anchored until group cleanup precedes reap."""

    def __init__(self, command, *, cwd, env, output, pass_fds=()):
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                                        stderr=subprocess.STDOUT, start_new_session=True,
                                        pass_fds=pass_fds)
        self.reaped = False
        self.external_reap = False
        self.status = None

    def exited(self):
        if self.reaped:
            return True
        try:
            return os.waitid(os.P_PID, self.process.pid,
                             os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
        except ChildProcessError as error:
            self.external_reap = True
            raise RuntimeError("owned session was externally reaped; group signals disarmed") from error

    def stop(self, grace=0.25):
        if self.reaped or self.external_reap:
            return self.status
        # WNOWAIT also detects an external reaper before any numeric group signal.
        self.exited()
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            time.sleep(min(0.025, max(0, deadline - time.monotonic())))
        # Even an exited leader remains our unreaped child here. Its group number
        # cannot be recycled; TERM-ignoring descendants must not outlive cleanup.
        self.exited()
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.status = self.process.wait()
        self.reaped = True
        return self.status

    def wait(self, timeout, shutdown=None):
        deadline = time.monotonic() + timeout
        while True:
            if shutdown is not None:
                shutdown.check()
            if self.exited():
                return self.stop()
            if time.monotonic() >= deadline:
                raise TimeoutError("owned session completion deadline expired")
            time.sleep(0.05)


def wait_for_qemu(path, session, listener, timeout, shutdown=None):
    deadline = time.monotonic() + timeout
    expected_address = list(listener.getsockname())
    while time.monotonic() < deadline:
        if shutdown is not None:
            shutdown.check()
        require(not session.exited(), "kernel driver exited before GDB readiness")
        try:
            record = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.05)
            continue
        require(record.get("raw_exit_code") is None and record.get("timed_out") is False,
                "QEMU exited before the Rust breakpoint could be installed")
        server = record.get("gdb_listener", {})
        pid = record.get("qemu_pid")
        if (server.get("address") != expected_address or
                server.get("fd") != listener.fileno() or type(pid) is not int or pid <= 0):
            time.sleep(0.05)
            continue
        try:
            descriptor = os.pidfd_open(pid)
        except ProcessLookupError as error:
            raise ValueError("recorded QEMU exited before GDB readiness") from error
        try:
            poller = select.poll()
            poller.register(descriptor, select.POLLIN)
            require(not poller.poll(0), "recorded QEMU is no longer alive")
        finally:
            os.close(descriptor)
        # Do not connect a throwaway TCP probe: it could consume the GDB client.
        # A live recorded QEMU owns our inherited listening socket. GDB's bounded
        # real protocol handshake below establishes that its stub is servicing it.
        return record
    raise TimeoutError("QEMU/GDB readiness deadline expired")


def entry_address(symbol_log):
    addresses = []
    with symbol_log.open() as source:
        for line in source:
            fields = line.split()
            if len(fields) >= 3 and fields[0] == ENTRY and fields[1] == "T":
                addresses.append(int(fields[2], 16))
    require(len(addresses) == 1 and addresses[0] != 0,
            "unstripped symbol ELF must define exactly one T __ostd_main")
    return addresses[0]


def elf_entry_bytes(path, address, machine):
    """Read the Rust entry from one executable ELF64 PT_LOAD file range."""
    path = Path(path)
    size = path.stat().st_size
    with path.open("rb") as source:
        header = source.read(64)
        require(len(header) == 64 and header[:7] == b"\x7fELF\x02\x01\x01",
                "entry artifact must be a complete little-endian ELF64 header")
        fields = struct.unpack("<16sHHIQQQIHHHHHH", header)
        require(fields[1] == 2 and fields[2] == machine and fields[3] == 1,
                "entry artifact must have the expected executable type and machine")
        offset, stride, count = fields[5], fields[9], fields[10]
        require(fields[8] == 64 and stride == 56 and count > 0
                and offset >= 64 and offset + count * stride <= size,
                "entry artifact has an invalid or truncated program-header table")
        require(type(address) is int and 0 < address <= (1 << 64) - ENTRY_BYTES,
                "Rust entry address is outside the ELF64 address range")
        locations = []
        for index in range(count):
            source.seek(offset + index * stride)
            program_header = source.read(56)
            require(len(program_header) == 56, "entry artifact program header is truncated")
            kind, flags, file_offset, virtual, _, file_size, memory_size, _ = struct.unpack(
                "<IIQQQQQQ", program_header)
            if kind != 1:
                continue
            require(file_size <= memory_size and file_offset + file_size <= size,
                    "entry artifact has a truncated PT_LOAD file range")
            if flags & 1 and virtual <= address and address + ENTRY_BYTES <= virtual + file_size:
                locations.append(file_offset + address - virtual)
        require(len(locations) == 1, "Rust entry must map to exactly one executable PT_LOAD range")
        source.seek(locations[0])
        entry = source.read(ENTRY_BYTES)
        require(len(entry) == ENTRY_BYTES, "Rust entry instruction bytes are truncated")
    return {"path": str(path), "size": size, "sha256": sha256(path),
            "elf_class": "ELF64", "elf_type": 2, "elf_machine": machine,
            "symbol": ENTRY, "address": hex(address),
            "entry_file_offset": locations[0], "entry_bytes": entry.hex()}


def bind_entry_artifacts(symbols, ready, address):
    original = elf_entry_bytes(symbols, address, 62)
    recorded = ready.get("artifacts", {}).get("-kernel", {})
    require(isinstance(recorded.get("path"), str), "QEMU record has no executed boot ELF path")
    boot_path = Path(recorded["path"])
    if not boot_path.is_absolute():
        boot_path = Path(ready["cwd"]) / boot_path
    boot = elf_entry_bytes(boot_path, address, 3)
    require(boot["sha256"] == recorded.get("sha256") and boot["size"] == recorded.get("size"),
            "executed boot ELF changed after QEMU recorded it")
    require(original["entry_bytes"] == boot["entry_bytes"],
            "original symbol ELF and executed boot ELF have different Rust entry bytes")
    return {"entry_address": hex(address), "entry_size": ENTRY_BYTES,
            "expected_bytes": original["entry_bytes"], "symbol_artifact": original,
            "boot_artifact": boot}


def gdb_script(port, address, expected_bytes):
    return f"""set pagination off
set confirm off
set language c
set breakpoint pending off
set remotetimeout 10
set tcp auto-retry on
set tcp connect-timeout 20
target remote 127.0.0.1:{port}
hbreak *{ENTRY}
continue
if (unsigned long)$pc != (unsigned long)&{ENTRY}
  echo A01_GDB_WRONG_PC\\n
  quit 1
end
printf "A01_GDB_RUST_ENTRY_HIT pc=0x%lx entry=0x%lx\\n", (unsigned long)$pc, (unsigned long)&{ENTRY}
python
import gdb
pc = int(gdb.parse_and_eval("$pc"))
observed = bytes(gdb.selected_inferior().read_memory(pc, {ENTRY_BYTES}))
if pc != {address} or observed != bytes.fromhex("{expected_bytes.hex()}"):
    raise gdb.GdbError("A01_GDB_ENTRY_BYTES_MISMATCH")
gdb.write("A01_GDB_RUST_ENTRY_BYTES pc=0x%x size={ENTRY_BYTES} bytes=%s\\n" % (pc, observed.hex()))
end
bt
info source
info line *{ENTRY}
info registers rip
disable breakpoints
detach
echo A01_GDB_DETACHED\\n
quit 0
"""


def accept_gdb(status, log, expected_address, expected_bytes):
    require(status == 0, "GDB did not exit successfully")
    text = log.read_text(errors="replace")
    hits = HIT.findall(text)
    require(len(hits) == 1, "GDB log lacks one verified Rust-entry hit")
    pc, address = (int(value, 16) for value in hits[0])
    require(pc == address == expected_address, "GDB PC does not match the Rust-entry symbol")
    byte_hits = BYTE_HIT.findall(text)
    require(len(byte_hits) == 1, "GDB log lacks one verified runtime Rust-entry byte read")
    byte_pc, runtime = byte_hits[0]
    require(int(byte_pc, 16) == expected_address and bytes.fromhex(runtime) == expected_bytes,
            "runtime Rust-entry bytes do not match the original symbol and boot ELFs")
    require(text.count("A01_GDB_DETACHED") == 1, "GDB did not complete detach")
    require("A01_GDB_WRONG_PC" not in text, "GDB stopped at the wrong PC")
    return {"symbol": ENTRY, "pc": hex(pc), "entry_address": hex(address),
            "gdb_status": status, "detached": True,
            "runtime_entry_bytes": runtime.lower(), "entry_size": ENTRY_BYTES}


def accept_boot(status, directory):
    require(status == 0, "kernel driver or its live boot checker failed")
    require((directory / "run-exit-code.txt").read_text().strip() == "0",
            "kernel driver did not record successful live boot validation")
    record = json.loads((directory / "qemu.json").read_text())
    require(record.get("raw_exit_code") == 33 and record.get("timed_out") is False,
            "detached kernel did not complete with raw QEMU status 33")
    require(sha256(directory / "serial.log") == record.get("serial_sha256"),
            "final raw serial SHA does not match QEMU evidence")
    return {"driver_status": status, "raw_qemu_exit": 33, "timed_out": False,
            "serial_sha256": record["serial_sha256"]}


def main():
    with interruption_handlers() as shutdown:
        return debug_main(shutdown)


def debug_main(shutdown):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new evidence directory")
    parser.add_argument("--gdb", default="gdb", help="GDB executable or PATH name")
    parser.add_argument("--nm", default="nm", help="native nm executable or PATH name")
    parser.add_argument("--ready-timeout", type=float, default=900,
                        help="seconds for source build and live QEMU record")
    parser.add_argument("--gdb-timeout", type=float, default=90)
    parser.add_argument("--boot-timeout", type=float, default=120,
                        help="seconds for complete boot after GDB detach")
    args = parser.parse_args()
    if "CARGO_ENCODED_RUSTFLAGS" in os.environ:
        print("CARGO_ENCODED_RUSTFLAGS overrides mandatory OSDK kernel flags; "
              "unset CARGO_ENCODED_RUSTFLAGS and retry", file=sys.stderr)
        raise SystemExit(2)
    for timeout in (args.ready_timeout, args.gdb_timeout, args.boot_timeout):
        if not 0 < timeout < float("inf"):
            parser.error("timeouts must be positive finite seconds")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = Path(__file__).resolve().parents[3]
    symbols = project / "kernel/asterinas/target/x86_64-unknown-none/release/asterinas-osdk-bin"
    result = {"passed": False, "stage": "prepare", "boot_directory": str(output / "boot")}
    commands = []
    sessions = []
    listener = None
    handles = []
    env = os.environ.copy()
    exit_code = 1

    def invoke(command, log_name, timeout=None, pass_fds=()):
        shutdown.check()
        commands.append({"argv": command, "shell_command": shlex.join(command),
                         "cwd": str(project), "stdout_stderr": log_name,
                         "pass_fds": list(pass_fds), "timeout_seconds": timeout})
        write_json(output / "commands.json", commands)
        handle = (output / log_name).open("w")
        handles.append(handle)
        owned = OwnedSession(command, cwd=project, env=env, output=handle, pass_fds=pass_fds)
        # Signal handlers only record requests, so Popen -> owner publication
        # cannot be interrupted. Check only after cleanup can find this child.
        sessions.append(owned)
        shutdown.check()
        if timeout is None:
            return owned
        status = owned.wait(timeout, shutdown)
        shutdown.check()
        return status

    try:
        gdb, nm = shutil.which(args.gdb), shutil.which(args.nm)
        require(gdb is not None and nm is not None, "GDB and nm must be available")
        gdb, nm = str(Path(gdb).resolve()), str(Path(nm).resolve())
        for tool, label in ((gdb, "gdb"), (nm, "nm")):
            require(invoke([tool, "--version"], label + "-version.log", 30) == 0,
                    label + " --version failed")
        listener = own_listener()
        address = list(listener.getsockname())
        descriptor = listener.fileno()
        updates = {"A01_GDB_FD": str(descriptor), "A01_GDB_PORT": str(address[1]),
                   "A01_RUN_DIR": str(output / "boot"),
                   "A01_KERNEL_WORKER": "1",
                   "CARGO_TARGET_DIR": str(project / "kernel/asterinas/target")}
        env.update(updates)
        sources = ["support/build/kernel.sh", "support/build/minimal.mk",
                   "support/build/record-qemu.py", "support/build/check-boot.py",
                   "support/build/minimal/OSDK.toml", "support/build/minimal/Cargo.lock",
                   "support/upstream-lock.json", "kernel/asterinas/rust-toolchain.toml",
                   "kernel/asterinas/Cargo.lock", "kernel/asterinas/osdk/Cargo.toml",
                   "kernel/asterinas/osdk/Cargo.lock",
                   "kernel/asterinas/ostd/src/boot/mod.rs"]
        sources += [str(path.relative_to(project)) for path in
                    sorted((project / "kernel/asterinas/osdk/src").rglob("*")) if path.is_file()]
        sources += [str(path.relative_to(project)) for path in sorted(Path(__file__).resolve().parent.glob("*"))
                    if path.is_file()]
        git = lambda *argv: subprocess.check_output(["git", "-C", str(project), *argv], text=True).strip()
        write_json(output / "environment.json", {
            "python": sys.version, "python_executable": sys.executable,
            "platform": platform.platform(), "git_head": git("rev-parse", "HEAD"),
            "git_tree": git("rev-parse", "HEAD^{tree}"), "git_status": git("status", "--short"),
            "explicit_environment_updates": updates,
            "selected_inherited_environment": {key: os.environ.get(key) for key in
                ("CARGO_HOME", "RUSTUP_HOME", "RUSTUP_TOOLCHAIN", "CARGO_BUILD_JOBS",
                 "VDSO_LIBRARY_DIR", "PATH", "LD_LIBRARY_PATH")},
            "complete_inherited_environment_saved": False,
            "gdb_executable": {"path": gdb, "sha256": sha256(gdb)},
            "nm_executable": {"path": nm, "sha256": sha256(nm)},
            "source_sha256": {relative: sha256(project / relative) for relative in sources},
            "listener": {"fd": descriptor, "address": address, "prebound": True},
            "toolchain": "nightly-2026-07-21"})
        result["stage"] = "build_and_qemu_ready"
        driver = invoke(["bash", str(project / "support/build/kernel.sh"), "gdb_server"],
                        "kernel-driver.log", pass_fds=(descriptor,))
        ready = wait_for_qemu(output / "boot/qemu.json", driver, listener, args.ready_timeout, shutdown)
        write_json(output / "qemu-ready.json", ready)
        write_json(output / "installed-osdk.json", private_osdk_evidence(output / "boot", project))
        listener.close()
        listener = None
        result["stage"] = "symbol_lookup"
        require(symbols.is_file(), "original Rust symbol ELF is missing")
        require(invoke([nm, "--defined-only", "--format=posix", str(symbols)],
                       "symbols.log", 30) == 0, "nm failed for the original Rust ELF")
        address = entry_address(output / "symbols.log")
        binding = bind_entry_artifacts(symbols, ready, address)
        write_json(output / "symbol-artifact.json", binding["symbol_artifact"])
        write_json(output / "entry-artifact-binding.json", binding)
        result["entry_artifact_binding"] = binding
        expected_bytes = bytes.fromhex(binding["expected_bytes"])
        script = output / "rust-entry.gdb"
        script.write_text(gdb_script(int(updates["A01_GDB_PORT"]), address, expected_bytes))
        result["stage"] = "gdb_rust_entry"
        gdb_status = invoke([gdb, "--nx", "--batch", "--se=" + str(symbols), "-x", str(script)],
                            "gdb.log", args.gdb_timeout)
        (output / "gdb-exit-code.txt").write_text(str(gdb_status) + "\n")
        result["gdb"] = accept_gdb(gdb_status, output / "gdb.log", address, expected_bytes)
        result["stage"] = "boot_after_detach"
        driver_status = driver.wait(args.boot_timeout, shutdown)
        shutdown.check()
        (output / "driver-exit-code.txt").write_text(str(driver_status) + "\n")
        result["boot"] = accept_boot(driver_status, output / "boot")
        result.update(passed=True, stage="complete")
        exit_code = 0
    except ShutdownRequested as error:
        result["error"] = "interrupted by " + signal.Signals(error.signum).name
        exit_code = 128 + error.signum
    except KeyboardInterrupt:
        result["error"] = "interrupted"
        exit_code = 130
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
        result["error"] = str(error)
    finally:
        if listener is not None:
            listener.close()
        cleanup = []
        for owned in reversed(sessions):
            try:
                cleanup.append({"leader_pid": owned.process.pid, "status": owned.stop(),
                                "reaped": owned.reaped, "external_reap": owned.external_reap})
            except (OSError, RuntimeError) as error:
                cleanup.append({"leader_pid": owned.process.pid, "error": str(error)})
                result.update(passed=False, cleanup_error=str(error))
                exit_code = 1
        for handle in handles:
            handle.close()
        result["owned_session_cleanup"] = cleanup
        if shutdown.signum is not None:
            result.update(passed=False, interrupted_by=signal.Signals(shutdown.signum).name,
                          received_signals=shutdown.received)
            result["error"] = "interrupted by " + result["interrupted_by"]
            exit_code = 128 + shutdown.signum
        write_json(output / "result.json", result)
        (output / "exit-code.txt").write_text(str(exit_code) + "\n")
    print(("PASS" if result["passed"] else "FAIL") + ": Rust-entry debug evidence: " + str(output))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
