#!/usr/bin/env python3
"""Record genuine OSDK integration guests while fixing only host VM resources."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import re
import socket
import subprocess
import sys
import threading
import time


FIRMWARE = Path("/usr/share/seabios/bios-256k.bin")
PROFILE = {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max",
           "vcpus": 1, "memory_mib": 512, "network": False, "data_disks": False,
           "firmware": str(FIRMWARE)}
LOCAL_TCP_PROFILE = "osdk-native-local-tcp-v1"
CAPTURE_PROFILE = "osdk-native-local-tcp-gdb-capture-v2"
# The default producer name remains a compatibility fixture constant. The
# inherited handoff is selected by its unique chardev id/reference pair.
MONITOR_CHARDEV_ID = "osdk-managed-monitor"


def select_private_inputs(arguments, record):
    """Apply the normal recorder's opt-in selectors after the fixed profile."""
    source = Path(__file__).resolve().parent.parent / "record-qemu.py"
    raw = source.read_bytes()
    spec = importlib.util.spec_from_file_location("a01_shared_qemu_selectors", source)
    selectors = importlib.util.module_from_spec(spec)
    # Bind the recorded hash to the exact source bytes being loaded rather than
    # a possibly stale Python bytecode cache or a second pathname read.
    exec(compile(raw, str(source), "exec"), selectors.__dict__)
    record["shared_selector_source"] = {"path": str(source), "size": len(raw),
                                         "sha256": hashlib.sha256(raw).hexdigest()}
    positions = [index for index, value in enumerate(arguments) if value == "-bios"]
    if len(positions) != 1 or positions[0] + 1 == len(arguments):
        raise ValueError("fixed integration profile must supply exactly one BIOS path")
    try:
        actual = selectors.select_bios(arguments, {"-bios": positions[0] + 1}, record)
    except (OSError, ValueError) as error:
        raise ValueError(f"A01_QEMU_BIOS selection rejected: {error}") from error
    try:
        actual = selectors.select_data_directory(actual, record)
    except (OSError, ValueError) as error:
        raise ValueError(f"A01_QEMU_DATA_DIR selection rejected: {error}") from error
    return actual


def snapshot_helpers(record):
    """Load the exact ordinary recorder already used for private selection."""
    source = Path(__file__).resolve().parent.parent / "record-qemu.py"
    raw = source.read_bytes()
    expected = {"path": str(source), "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest()}
    if record["shared_selector_source"] != expected:
        raise ValueError("shared recorder source changed after input selection")
    spec = importlib.util.spec_from_file_location("a01_shared_snapshot_helpers", source)
    helpers = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(source), "exec"), helpers.__dict__)
    return helpers


def snapshot_input(source, target, helpers):
    """Keep source provenance separate from the private copy's exact stat."""
    original = Path(source).absolute()
    captured = helpers.capture_artifact(original, target)
    target.chmod(0o400)
    copied = helpers.capture_artifact(target)
    if any(copied[key] != captured[key] for key in ("size", "sha256")):
        raise ValueError("private input differs from its captured source")
    artifact = {"path": str(target), **{key: copied[key] for key in ("size", "sha256")}}
    provenance = {"requested_path": str(source), "path": str(original), **captured}
    snapshot = {**artifact, "stat": copied["stat"],
                "creation": "exclusive xb; read-only private copy; no source-path fallback"}
    return artifact, provenance, snapshot


def snapshot_arguments(arguments, guest, record, helpers):
    """Snapshot mandatory kernel/BIOS and optional initrd before any QEMU probe."""
    actual = list(arguments)
    positions = {}
    names = {"-kernel": "kernel.elf", "-initrd": "initramfs.cpio.gz", "-bios": "bios.bin"}
    # Use the existing transform's accepted option spellings and value
    # boundaries. In particular, -append's literal value is not another option.
    value_options = {"-machine", "-M", "-accel", "-cpu", "-m", "-smp", "-bios",
                     "-display", "-vga", "-kernel", "-initrd", "-append", "-drive",
                     "-device", "-chardev", "-serial", "-monitor", "-gdb", "-qmp", "-L"}
    found = {option: [] for option in names}
    index = 0
    while index < len(arguments):
        token = arguments[index]
        key = "-" + token.lstrip("-") if token.startswith("-") else token
        if key in value_options:
            if index + 1 == len(arguments):
                raise ValueError(f"QEMU option {token} has no value")
            if key in names:
                found[key].append(index + 1)
            index += 2
        else:
            index += 1
    for option in names:
        matches = found[option]
        if len(matches) > 1 or option != "-initrd" and len(matches) != 1:
            raise ValueError(f"{option} must occur {'at most' if option == '-initrd' else 'exactly'} once")
        if not matches:
            continue
        index = matches[0]
        if index == len(arguments) or not arguments[index] or arguments[index].startswith("-"):
            raise ValueError(f"{option} requires one explicit artifact path")
        positions[option] = index
    directory = guest / "artifacts"
    directory.mkdir(mode=0o700)
    record["snapshot_directory"] = {"path": str(directory),
        "stat": helpers.file_state(directory.stat()),
        "ownership": "new exclusive private directory retained as guest evidence"}
    record["artifacts"], record["artifact_sources"], record["artifact_snapshots"] = {}, {}, {}
    for option, index in positions.items():
        artifact, provenance, snapshot = snapshot_input(arguments[index], directory / names[option], helpers)
        record["artifacts"][option] = artifact
        record["artifact_sources"][option] = provenance
        record["artifact_snapshots"][option] = snapshot
        actual[index] = artifact["path"]
    return actual


def snapshot_coverage_symbol(symbol, record, helpers):
    target = Path(record["snapshot_directory"]["path"]) / "coverage-symbol.elf"
    artifact, provenance, snapshot = snapshot_input(symbol["path"], target, helpers)
    if any(artifact[key] != symbol[key] for key in ("size", "sha256")):
        raise ValueError("coverage symbols changed before the private capture")
    with target.open("rb") as stream:
        header = stream.read(20)
    if len(header) != 20 or header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\x3e\x00":
        raise ValueError("private coverage symbols must remain ELF64 little-endian EM62")
    record["coverage_symbol_source"] = provenance
    record["artifact_snapshots"]["coverage-symbol"] = snapshot
    return artifact


def verify_input_snapshots(record, helpers):
    """Verify private bytes and identity; original build outputs may change later."""
    for option, expected in record["artifact_snapshots"].items():
        actual = helpers.capture_artifact(Path(expected["path"]))
        if any(actual[key] != expected[key] for key in ("size", "sha256", "stat")):
            raise ValueError(f"private input snapshot changed: {option}")


def file_record(path):
    path = Path(path).resolve()
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"path": str(path), "size": path.stat().st_size, "sha256": digest}


def qemu_options(value):
    """Split QEMU comma options, preserving its doubled-comma escape."""
    fields, current, index = [], [], 0
    while index < len(value):
        if value[index:index + 2] == ",,":
            current.append(",")
            index += 2
        elif value[index] == ",":
            fields.append("".join(current))
            current = []
            index += 1
        else:
            current.append(value[index])
            index += 1
    fields.append("".join(current))
    return fields


def transform_args(requested, guest, cwd):
    """Keep workload/debug/coverage semantics; replace resources and pflash."""
    fixed_values = {"-machine", "-M", "-accel", "-cpu", "-m", "-smp", "-bios",
                    "-display", "-vga"}
    fixed_flags = {"-enable-kvm", "-nographic", "-nodefaults", "-no-user-config"}
    forbidden_values = {"-net", "-netdev", "-nic", "-hda", "-hdb", "-hdc", "-hdd",
                        "-cdrom", "-fda", "-fdb", "-blockdev", "-pflash"}
    values = fixed_values | forbidden_values | {
        "-kernel", "-initrd", "-append", "-drive", "-device", "-chardev", "-serial",
        "-monitor", "-gdb", "-qmp", "-readconfig"}
    result, removed, logs, kernels = [], [], [], 0
    debug_exit, serial_present, stdio_present = False, False, False
    index = 0
    while index < len(requested):
        argument = requested[index]
        key = "-" + argument.lstrip("-") if argument.startswith("-") else argument
        if key in fixed_flags:
            removed.append([argument])
            index += 1
            continue
        if key not in values:
            result.append(argument)
            index += 1
            continue
        if index + 1 == len(requested):
            raise ValueError(f"QEMU option {argument} has no value")
        value = requested[index + 1]
        index += 2
        if key in fixed_values:
            removed.append([argument, value])
            continue
        if key in forbidden_values or key == "-readconfig":
            raise ValueError(f"QEMU profile forbids {argument}: {value}")
        fields = qemu_options(value)
        if key == "-drive":
            if "if=pflash" not in fields:
                raise ValueError(f"QEMU profile forbids a data/boot drive: {value}")
            removed.append([argument, value])
            continue
        if key == "-device":
            if fields[0].startswith(("virtio-net", "e1000", "rtl8139", "ne2k", "vmxnet",
                                     "virtio-blk", "virtio-scsi", "scsi-", "ide-", "nvme")):
                raise ValueError(f"QEMU profile forbids network/disk device: {value}")
            debug_exit |= fields[0] == "isa-debug-exit"
        if key == "-kernel":
            kernels += 1
        if key == "-serial":
            serial_present = True
        if key == "-chardev" and fields[0] == "stdio":
            if stdio_present:
                raise ValueError("multiple stdio chardevs are unsupported")
            stdio_present = True
            logfiles = [field.split("=", 1)[1] for field in fields if field.startswith("logfile=")]
            if len(logfiles) > 1:
                raise ValueError("stdio chardev has multiple logfiles")
            if logfiles:
                log = Path(logfiles[0])
                logs.append(log if log.is_absolute() else cwd / log)
            else:
                log = guest / "serial.log"
                value += ",logfile=" + str(log).replace(",", ",,")
                logs.append(log)
        result.extend((argument, value))
    if kernels != 1:
        raise ValueError("direct integration guest requires exactly one -kernel")
    if not stdio_present:
        # OSDK's templates normally provide their own mux; this is the plain
        # direct-boot fallback, with a distinct id so other chardevs survive.
        identifier = "a01-record-serial"
        if any(identifier in item for item in result):
            raise ValueError("reserved fallback serial chardev id is already used")
        log = guest / "serial.log"
        result.extend(("-chardev", "stdio,id=" + identifier + ",signal=off,logfile="
                       + str(log).replace(",", ",,")))
        logs.append(log)
        if serial_present:
            serial_positions = [i for i, item in enumerate(result) if item in ("-serial", "--serial")]
            if len(serial_positions) != 1 or result[serial_positions[0] + 1] not in ("stdio", "none"):
                raise ValueError("non-stdio serial backend cannot be replaced without changing semantics")
            result[serial_positions[0] + 1] = "chardev:" + identifier
        else:
            result.extend(("-serial", "chardev:" + identifier))
    if not debug_exit:
        result.extend(("-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"))
    result.extend(("-machine", "q35", "-accel", "tcg", "-cpu", "max", "-m", "512M",
                   "-smp", "1", "-bios", str(FIRMWARE), "-nodefaults", "-no-user-config",
                   "-display", "none"))
    return result, logs, removed


def reserve_guest(directory):
    directory.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        guest = directory / f"guest-{index:03d}"
        try:
            guest.mkdir()
            return guest
        except FileExistsError:
            index += 1


def local_tcp_controls(arguments, allow_gdb_zero=False):
    """Validate explicit local TCP controls without rewriting their arguments."""
    controls = []
    for index, argument in enumerate(arguments):
        key = "-" + argument.lstrip("-") if argument.startswith("-") else argument
        if key not in ("-gdb", "-monitor", "-chardev"):
            continue
        if index + 1 == len(arguments):
            raise ValueError(f"QEMU option {argument} has no value")
        value = arguments[index + 1]
        fields = qemu_options(value)
        if key == "-chardev":
            if fields[0] != "socket":
                continue
            entries = [field.partition("=") for field in fields[1:]]
            if any(name == "fd" for name, _, _ in entries):
                # QEMU consumes every field. Do not let dict construction hide
                # duplicate keys or bare tokens and record a different meaning.
                if len(fields) != 4 or any(not separator for _, separator, _ in entries) \
                        or len({name for name, _, _ in entries}) != 3:
                    raise ValueError("private monitor requires exactly socket,id,fd,server without duplicate or bare fields")
                options = {name: entry for name, _, entry in entries}
                if set(options) != {"id", "fd", "server"} \
                        or not re.fullmatch(r"[A-Za-z0-9._-]+", options["id"]) \
                        or options["server"] != "off" or not re.fullmatch(r"[0-9]+", options["fd"]) \
                        or not 64 <= int(options["fd"]) <= 2**31 - 1:
                    raise ValueError("local TCP profile requires a named preconnected monitor descriptor fd >= 64")
                controls.append({"kind": "monitor", "handoff": "private-connected-inherited-fd",
                                 "fd": int(options["fd"]), "chardev_id": options["id"],
                                 "requested_value": value})
                continue
            options = dict(field.split("=", 1) for field in fields[1:] if "=" in field)
            if options.get("host") != "127.0.0.1" or not options.get("port", "").isdigit():
                raise ValueError("local TCP profile forbids non-loopback socket chardev")
            port = int(options["port"])
            if not 0 < port <= 65535:
                raise ValueError("local TCP control port must be between 1 and 65535")
            # GDB in this profile uses the direct -gdb tcp: endpoint below;
            # other socket chardevs are recorded but never silently rewritten.
            controls.append({"kind": "chardev", "host": "127.0.0.1", "port": port,
                             "requested_value": value})
            continue
        if key == "-monitor" and (fields[0] in ("none", "stdio") or fields[0].startswith("chardev:")):
            continue  # Preserve the normal stdio mux monitor alongside TCP.
        matched = re.fullmatch(r"tcp:127\.0\.0\.1:([0-9]{1,5})", fields[0])
        if not matched or not (0 < int(matched[1]) <= 65535
                               or key == "-gdb" and allow_gdb_zero and int(matched[1]) == 0):
            raise ValueError(f"local TCP profile requires explicit 127.0.0.1 endpoint: {value}")
        if key == "-monitor" and any(field == "server" or field.startswith("server=")
                                     and field != "server=off" for field in fields[1:]):
            raise ValueError("local TCP monitor must connect to the OSDK-owned listener")
        controls.append({"kind": key[1:], "role": "server" if key == "-gdb" else "client",
                         "host": "127.0.0.1", "port": int(matched[1]), "requested_value": value})
    if sum(item["kind"] == "monitor" for item in controls) > 1:
        raise ValueError("local TCP profile requires a unique managed monitor")
    if sum(item["kind"] == "gdb" for item in controls) > 1:
        raise ValueError("local TCP profile requires a unique GDB endpoint")
    return controls


def inherit_monitor_socket(arguments, controls):
    """Validate and own only OSDK's already connected private monitor FD."""
    endpoint = next((item for item in controls
                     if item.get("handoff") == "private-connected-inherited-fd"), None)
    if endpoint is None:
        return None, None
    # Take ownership of this inherited descriptor. Any validation or spawn
    # failure closes it; on success the wrapper closes its copy after Popen.
    try:
        stream = socket.socket(fileno=endpoint["fd"])
    except BaseException:
        try:
            os.close(endpoint["fd"])
        except OSError:
            pass
        raise
    try:
        references = [arguments[index + 1] for index, value in enumerate(arguments[:-1])
                      if value in ("-monitor", "--monitor")]
        identifier = endpoint.get("chardev_id")
        definitions = [qemu_options(arguments[index + 1]) for index, value in enumerate(arguments[:-1])
                       if value in ("-chardev", "--chardev")]
        if not identifier or references.count("chardev:" + identifier) != 1 \
                or sum("id=" + identifier in fields for fields in definitions) != 1:
            raise ValueError("private monitor descriptor requires its unique managed monitor reference and chardev definition")
        if stream.family != socket.AF_INET or stream.type != socket.SOCK_STREAM \
                or stream.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN):
            raise ValueError("private monitor descriptor must be a connected IPv4 stream, not a listener")
        local, peer = stream.getsockname(), stream.getpeername()
        if any(address[0] != "127.0.0.1" or not 0 < address[1] <= 65535 for address in (local, peer)):
            raise ValueError("private monitor endpoints must both be 127.0.0.1 with assigned ports")
        metadata = {"fd": stream.fileno(), "chardev_id": identifier,
                    "local": list(local), "peer": list(peer),
                    "connected": True, "listening": False,
                    "handoff": "private-connected-inherited-fd",
                    "parent_copy_closed_after_spawn": False}
        return stream, metadata
    except BaseException:
        stream.close()
        raise


def reserve_gdb_listener(arguments, endpoint):
    """Keep the loopback listener owned until QEMU inherits its descriptor."""
    identifier = "a01-gdb0"
    if any(identifier in item for item in arguments):
        raise ValueError("reserved GDB chardev id is already used")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((endpoint["host"], endpoint["port"]))
        listener.listen(1)
        index = next(i for i, item in enumerate(arguments) if item in ("-gdb", "--gdb"))
        adapted = [*arguments[:index], "-chardev",
                   f"socket,id={identifier},fd={listener.fileno()},server=on,wait=off",
                   "-gdb", "chardev:" + identifier, *arguments[index + 2:]]
        return adapted, listener
    except BaseException:
        listener.close()
        raise


def coverage_symbol(cwd):
    configured = os.environ.get("A01_OSDK_COVERAGE_SYMBOL_ELF")
    if configured:
        symbol = Path(configured)
        if not symbol.is_absolute():
            raise ValueError("coverage symbol ELF must have an absolute path")
    else:
        target = Path(os.environ.get("CARGO_TARGET_DIR", "target"))
        symbol = target / "x86_64-unknown-none/debug/basic_coverage-osdk-bin"
        if not symbol.is_absolute():
            symbol = cwd / symbol
    symbol = symbol.resolve()
    with symbol.open("rb") as source:
        header = source.read(20)
    if len(header) != 20 or header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\x3e\x00":
        raise ValueError("coverage symbols must be the original ELF64 little-endian EM62 binary")
    return file_record(symbol)


def stop_capture_child(process):
    """Stop and reap this direct child; the outer runner owns group cleanup."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    else:
        process.wait()


def supervise_capture(qemu, capture, guest_timeout, capture_timeout=180):
    """Observe both children; never synthesize a successful QEMU exit."""
    deadline = time.monotonic() + guest_timeout
    capture_deadline = time.monotonic() + min(guest_timeout, capture_timeout)
    while True:
        qemu_status, capture_status = qemu.poll(), capture.poll()
        if qemu_status is not None and qemu_status != 33:
            if capture_status is None:
                stop_capture_child(capture)
            return qemu_status, False
        if capture_status is not None and capture_status != 0:
            stop_capture_child(capture)
            if qemu_status is None:
                qemu.kill()
                qemu.wait()
            return 125, False
        if qemu_status is not None and capture_status is not None:
            return qemu_status, False
        now = time.monotonic()
        if now >= deadline or capture_status is None and now >= capture_deadline:
            stop_capture_child(capture)
            if qemu_status is None:
                qemu.kill()
                qemu.wait()
            return 124, True
        time.sleep(0.05)


def run_capture(qemu, arguments, guest, metadata, timeout):
    stream_paths = {"stdout": guest / "coverage-capture-stdout.log",
                    "stderr": guest / "coverage-capture-stderr.log"}
    started, child = time.monotonic(), None
    try:
        with stream_paths["stdout"].open("wb") as stdout, stream_paths["stderr"].open("wb") as stderr:
            child = subprocess.Popen(arguments, stdout=stdout, stderr=stderr)
            metadata["pid"] = child.pid
            metadata["process_group"] = os.getpgrp()
            metadata["group_policy"] = "inherit recorder group; no capture session or group created"
            try:
                status, timed_out = supervise_capture(qemu, child, timeout)
                metadata["timed_out"] = timed_out
                return status, timed_out
            except BaseException:
                stop_capture_child(child)
                raise
            finally:
                metadata["raw_exit_code"] = child.returncode
    finally:
        metadata["duration_seconds"] = round(time.monotonic() - started, 3)
        metadata["logs"] = {name: file_record(path) for name, path in stream_paths.items() if path.is_file()}


def finalize_capture(metadata, record, sidecar, serial, raw_path, symbol, guest_record):
    """Bind the paused dump to this guest, original symbols and final serial."""
    captured = json.loads(sidecar.read_text())
    if not isinstance(captured, dict):
        raise ValueError("coverage sidecar must be an object")
    if record["raw_exit_code"] != 33 or metadata.get("raw_exit_code") != 0 or metadata.get("timed_out"):
        raise ValueError("coverage requires real QEMU exit 33 and capture exit 0")
    if captured.get("passed") is not True or captured.get("profile_id") != CAPTURE_PROFILE \
            or captured.get("gdb_exit_code") != 0:
        raise ValueError("coverage capture sidecar did not report a valid GDB capture")
    if captured.get("guest_record") != guest_record \
            or captured.get("kernel_sha256") != record["artifacts"]["-kernel"]["sha256"]:
        raise ValueError("coverage capture does not bind this QEMU guest and kernel")
    if captured.get("symbol_elf") != symbol:
        raise ValueError("coverage capture symbol ELF differs from the original EM62 input")
    breakpoint = captured.get("breakpoint", {})
    if not isinstance(breakpoint, dict):
        raise ValueError("coverage breakpoint observation must be an object")
    if breakpoint.get("symbol") != "ostd::arch::power::try_poweroff" \
            or int(breakpoint.get("resolved_address", "0"), 16) <= 0 \
            or int(breakpoint.get("actual_pc", "0"), 16) != int(breakpoint.get("resolved_address", "0"), 16):
        raise ValueError("coverage capture did not stop at the expected poweroff breakpoint")
    raw = file_record(raw_path)
    announcement = captured.get("announcement", {})
    if not isinstance(announcement, dict):
        raise ValueError("coverage announcement must be an object")
    if raw != captured.get("raw") or raw["size"] <= 0 or raw["size"] != announcement.get("size"):
        raise ValueError("coverage raw bytes differ from the dump and announcement")
    serial_bytes = serial.read_bytes()
    prefix = captured.get("serial_prefix", {})
    if not isinstance(prefix, dict):
        raise ValueError("coverage serial prefix must be an object")
    prefix_size = prefix.get("size")
    if not isinstance(prefix_size, int) or not 0 < prefix_size <= len(serial_bytes) \
            or hashlib.sha256(serial_bytes[:prefix_size]).hexdigest() != prefix.get("sha256"):
        raise ValueError("coverage serial prefix differs from this final guest log")
    announcements = re.findall(rb"#### Coverage: (0x[0-9a-fA-F]+) ([0-9]+)", serial_bytes[:prefix_size])
    if len(announcements) != 1 or int(announcements[0][0], 16) != int(announcement.get("address", "0"), 16) \
            or int(announcements[0][1]) != announcement.get("size"):
        raise ValueError("coverage announcement differs from this paused guest log")
    captured.update({"serial_sha256": hashlib.sha256(serial_bytes).hexdigest(), "finalized": True})
    sidecar.write_text(json.dumps(captured, indent=2) + "\n")
    metadata.update({"sidecar": file_record(sidecar), "raw": raw, "finalized": True,
                     "serial_sha256": captured["serial_sha256"]})


def tee_stream(source, destination, sink, errors):
    """Drain one pipe in bounded chunks, retaining bytes if forwarding fails."""
    recording, forwarding = True, True
    try:
        while chunk := source.read1(65536):
            if recording:
                try:
                    destination.write(chunk)
                    destination.flush()
                except (OSError, ValueError) as error:
                    errors.append(f"recording {destination.name}: {error}")
                    recording = False
            if forwarding:
                try:
                    sink.write(chunk)
                    sink.flush()
                except (OSError, ValueError) as error:
                    errors.append(f"forwarding QEMU output: {error}")
                    forwarding = False
    except (OSError, ValueError) as error:
        errors.append(f"reading QEMU output: {error}")
    finally:
        source.close()


def main():
    requested, cwd = sys.argv[1:], Path.cwd()
    case = Path(os.environ["A01_OSDK_CASE_OUTPUT"]).resolve()
    guest = reserve_guest(case / "guests")
    destination = guest / "qemu.json"
    record = {"schema": 1, "cwd": str(cwd), "requested_osdk_args": requested,
              "profile": PROFILE, "raw_exit_code": None, "timed_out": False}
    started = time.monotonic()
    status = 125
    gdb_listener = None
    monitor_socket = None
    try:
        arguments, logs, removed = transform_args(requested, guest, cwd)
        record["fixed_profile_args"] = list(arguments)
        arguments = select_private_inputs(arguments, record)
        record["selected_profile_args"] = list(arguments)
        record["profile"] = dict(PROFILE, firmware=arguments[arguments.index("-bios") + 1])
        local_tcp = os.environ.get("A01_OSDK_LOCAL_TCP") == "1"
        profile_id = os.environ.get("A01_OSDK_PROFILE", "osdk-native-unix-v1")
        capture_enabled = os.environ.get("A01_OSDK_COVERAGE_GDB") == "1"
        if local_tcp != (profile_id in (LOCAL_TCP_PROFILE, CAPTURE_PROFILE)):
            raise ValueError("local TCP flag and profile id disagree")
        if capture_enabled and (not local_tcp or profile_id != CAPTURE_PROFILE):
            raise ValueError("GDB coverage capture requires the explicit v2 local TCP profile")
        record.update({"profile_id": profile_id,
                       "control_transport": "loopback-tcp" if local_tcp else "upstream-original"})
        controls = local_tcp_controls(arguments, allow_gdb_zero=capture_enabled) if local_tcp else []
        record["control_endpoints"] = controls
        monitor_socket, monitor_metadata = inherit_monitor_socket(arguments, controls)
        if monitor_metadata is not None:
            record["monitor_socket"] = monitor_metadata
        gdb_endpoint = next((item for item in controls if item["kind"] == "gdb"), None)
        if capture_enabled and (gdb_endpoint is None or gdb_endpoint["port"] != 0 or "-S" not in arguments):
            raise ValueError("coverage capture requires its own paused GDB listener requested on port 0")
        ready_path = None
        if gdb_endpoint:
            if os.environ.get("A01_OSDK_GDB_READY"):
                ready_path = Path(os.environ["A01_OSDK_GDB_READY"]).resolve()
                if not ready_path.is_relative_to(case) or ready_path.exists():
                    raise ValueError("GDB readiness marker must be a new path inside this case output")
            record["gdb_readiness"] = {"ready": False, "marker_requested": ready_path is not None,
                                       "startup_survival_seconds": 0.05}
            arguments, gdb_listener = reserve_gdb_listener(arguments, gdb_endpoint)
            actual_endpoint = dict(gdb_endpoint)
            if gdb_endpoint["port"] == 0:
                actual_endpoint["port"] = gdb_listener.getsockname()[1]
                if not isinstance(actual_endpoint["port"], int) or not 0 < actual_endpoint["port"] <= 65535:
                    raise ValueError("prebound GDB listener did not resolve a valid ephemeral port")
            record["gdb_listener"] = {"host": gdb_endpoint["host"], "port": actual_endpoint["port"],
                                       "requested_port": gdb_endpoint["port"],
                                       "fd": gdb_listener.fileno(), "bind_succeeded": True,
                                       "held_until_qemu_spawn": True, "bind_close_rebind_gap": False,
                                       "handoff": "prebound-listener-inherited-fd",
                                       "parent_copy_closed_after_spawn": False}
        binary = shutil.which("qemu-system-x86_64")
        if not binary:
            raise FileNotFoundError("qemu-system-x86_64 is not installed")
        helpers = snapshot_helpers(record)
        arguments = snapshot_arguments(arguments, guest, record, helpers)
        record["profile"]["firmware"] = record["artifacts"]["-bios"]["path"]
        command = [binary, *arguments]
        artifacts = record["artifacts"]
        timeout = int(os.environ.get("A01_OSDK_GUEST_TIMEOUT", "300"))
        if timeout <= 0:
            raise ValueError("A01_OSDK_GUEST_TIMEOUT must be positive")
        record.update({"argv": command, "shell_command": shlex.join(command),
                       "removed_profile_args": removed, "artifacts": artifacts,
                       "qemu": file_record(binary), "serial_sources": list(map(str, logs)),
                       "timeout_seconds": timeout})
        if capture_enabled:
            if len(logs) != 1:
                raise ValueError("coverage capture requires exactly one serial logfile")
            raw_path = cwd / "coverage.profraw"
            if os.path.lexists(raw_path):
                raise ValueError("coverage capture refuses a preexisting coverage.profraw")
            symbol = snapshot_coverage_symbol(coverage_symbol(cwd), record, helpers)
            sidecar = guest / "coverage-capture.json"
            guest_record = str(destination.relative_to(case))
            capture_command = [sys.executable, "-I", str(Path(__file__).with_name("capture.py")),
                               "--endpoint", f"127.0.0.1:{actual_endpoint['port']}",
                               "--symbol-elf", symbol["path"], "--serial-log", str(logs[0]),
                               "--raw-output", str(raw_path), "--sidecar", str(sidecar),
                               "--kernel-sha256", artifacts["-kernel"]["sha256"],
                               "--guest-record", guest_record, "--timeout", "180"]
            record["capture"] = {"mode": "gdb-before-poweroff", "argv": capture_command,
                                 "symbol_elf": symbol, "serial_source": str(logs[0]),
                                 "raw_output": str(raw_path), "sidecar_path": str(sidecar),
                                 "raw_exit_code": None, "timed_out": False, "finalized": False}
        record["qemu_version"] = subprocess.check_output([binary, "--version"], text=True,
                                                        timeout=10).strip()
        verify_input_snapshots(record, helpers)
        record["snapshot_verification"] = {"before_qemu": True, "after_qemu": False}
        destination.write_text(json.dumps(record, indent=2) + "\n")
        stream_paths = {"stdout": guest / "qemu-stdout.log", "stderr": guest / "qemu-stderr.log"}
        stream_errors = []
        with stream_paths["stdout"].open("wb") as stdout_log, \
                stream_paths["stderr"].open("wb") as stderr_log, \
                subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 pass_fds=tuple(stream.fileno() for stream in (gdb_listener, monitor_socket)
                                                if stream is not None)) as process:
            record["qemu_pid"] = process.pid
            if monitor_socket is not None:
                monitor_socket.close()
                monitor_socket = None
                record["monitor_socket"]["parent_copy_closed_after_spawn"] = True
                record["monitor_socket"]["qemu_pid"] = process.pid
            if gdb_listener is not None:
                gdb_listener.close()
                gdb_listener = None
                record["gdb_listener"]["parent_copy_closed_after_spawn"] = True
            readers = [threading.Thread(target=tee_stream, args=(source, destination, sink, stream_errors))
                       for source, destination, sink in (
                           (process.stdout, stdout_log, sys.stdout.buffer),
                           (process.stderr, stderr_log, sys.stderr.buffer))]
            for reader in readers:
                reader.start()
            try:
                if gdb_endpoint:
                    try:
                        early_status = process.wait(timeout=0.05)
                    except subprocess.TimeoutExpired:
                        if ready_path is not None:
                            marker = {"schema": 1, "qemu_pid": process.pid,
                                      "endpoint": actual_endpoint, "profile_id": profile_id,
                                      "startup_survival_seconds": 0.05,
                                      "listener_handoff": "prebound-listener-inherited-fd",
                                      "bind_close_rebind_gap": False}
                            with ready_path.open("x") as output:
                                output.write(json.dumps(marker, indent=2) + "\n")
                            record["gdb_readiness"].update({"ready": True, "marker": file_record(ready_path)})
                    else:
                        record["gdb_readiness"]["early_exit_code"] = early_status
                if capture_enabled:
                    if "early_exit_code" in record["gdb_readiness"]:
                        status = record["gdb_readiness"]["early_exit_code"]
                        record["capture"]["error"] = "QEMU exited before capture could attach"
                    else:
                        status, record["timed_out"] = run_capture(process, capture_command, guest,
                                                                  record["capture"], timeout)
                else:
                    status = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                status = 124
                record["timed_out"] = True
            except BaseException:
                process.kill()
                process.wait()
                raise
            finally:
                # Both pipes are drained concurrently while QEMU runs. Joining
                # only after wait/kill avoids either full pipe blocking QEMU.
                for reader in readers:
                    reader.join()
                record["raw_exit_code"] = process.returncode
        record["stream_logs"] = {name: file_record(path) for name, path in stream_paths.items()}
        if stream_errors:
            record["stream_errors"] = stream_errors
            status = 125
        snapshots = []
        for index, source in enumerate(logs):
            if source.exists():
                target = guest / ("serial.log" if index == 0 else f"serial-{index + 1}.log")
                if source.resolve() != target.resolve():
                    shutil.copyfile(source, target)
                snapshots.append(file_record(target))
        record["serial_logs"] = snapshots
        if capture_enabled:
            try:
                finalize_capture(record["capture"], record, sidecar, guest / "serial.log", raw_path,
                                 symbol, guest_record)
            except (OSError, ValueError, KeyError, TypeError) as error:
                record["capture"]["finalization_error"] = str(error)
                if sidecar.is_file():
                    record["capture"]["sidecar"] = file_record(sidecar)
                raise
        verify_input_snapshots(record, helpers)
        record["snapshot_verification"]["after_qemu"] = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        status = 124 if record["timed_out"] else 125
        record["error"] = f"{type(error).__name__}: {error}"
        print(record["error"], file=sys.stderr)
    finally:
        if gdb_listener is not None:
            gdb_listener.close()
        if monitor_socket is not None:
            monitor_socket.close()
    record["wrapper_exit_code"] = status if status >= 0 else 128 - status
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    destination.write_text(json.dumps(record, indent=2) + "\n")
    return record["wrapper_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
