#!/usr/bin/env python3
"""Package A04 *identical* ELF bytes into A01's pinned initramfs; parse raw serial.

This script does not launch QEMU, assert new-kernel compatibility, or modify
A01-owned build code. The original A01 init's boot checks remain in place.
Guest inputs MUST be kernel+initramfs obtained from A01's actual verified build.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys

A01_IMAGE_SHA = "86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3"
A01_KERNEL_SHA = "e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63"
CASE_BEGIN = re.compile(r"^A04_CASE_BEGIN=([a-z_]+\.[a-z_]+)$")
CASE_END = re.compile(r"^A04_CASE_END=([a-z_]+\.[a-z_]+):(\d+)$")
EXPECTED_MARKERS = ("TRILLIONNIUM_A01_INIT_BEGIN", "TRILLIONNIUM_A01_BOOT_OK",
                    "TRILLIONNIUM_A04_WORKLOAD_BEGIN", "TRILLIONNIUM_A04_WORKLOAD_END")
INIT_ANCHOR = "exec /bin/busybox poweroff -f\n"
BINARY_FOR = {"dynamic": "probe_dynamic", "static": "probe_static",
              "sqlite_dynamic": "sqlite_dynamic", "sqlite_static": "sqlite_static"}
# Names become shell arguments and serial markers. Only literal probe tokens
# may cross into generated /init or the guest-run.sh command interpreter.
SAFE_CASE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_binary_identity(rootfs_dir, root_manifest, reference, *, required_stems=None):
    """Bind ELF metadata to the exact bytes at the guest execution path.

    A self-consistent files[] hash alone is not an identical-ELF claim: elf[]
    could retain the ORIGINAL digest while files[] describes a replacement
    binary with identical JSON behavior. Every runner must reject that drift.
    """
    records = root_manifest["elf"]
    binary_manifest = {x["name"]: x for x in records}
    if len(binary_manifest) != len(records):
        raise ValueError("duplicate ELF identity in rootfs manifest")
    stems = (BINARY_FOR if required_stems is None else required_stems)
    for stem in stems:
        filename = BINARY_FOR[stem]
        reference_elf = reference["binaries"][stem]
        pinned = binary_manifest.get(filename)
        path = "/usr/local/bin/a04/" + filename
        actual = rootfs_dir / path.lstrip("/")
        if (not pinned or pinned.get("path") != path or
                pinned.get("sha256") != reference_elf["sha256"] or
                pinned.get("interpreter") != reference_elf["interpreter"] or
                pinned.get("needed") != reference_elf["needed"] or
                actual.is_symlink() or not actual.is_file() or
                sha_file(actual) != reference_elf["sha256"] or
                (reference_elf.get("size") is not None and
                 actual.stat().st_size != reference_elf["size"]) or
                not actual.stat().st_mode & 0o111):
            raise ValueError("ELF bytes not identical to pinned Linux reference: " + stem)
    return binary_manifest


def valid_path(name):
    p = PurePosixPath(name)
    if not name or name.startswith("/") or "\\" in name or "\x00" in name or name == "TRAILER!!!":
        return False
    return all(part not in ("", ".", "..") for part in name.split("/")) and not name.endswith("/")


def align4(offset):
    return (offset + 3) & ~3


def parse_newc(archive):
    entries, offset, trailer = {}, 0, False
    while offset + 110 <= len(archive):
        start = offset
        magic = archive[offset:offset + 6]
        if magic != b"070701":
            raise ValueError(f"unsupported/invalid newc magic at {offset}")
        fields = []
        for i in range(13):
            part = archive[offset+6+i*8:offset+14+i*8]
            try:
                fields.append(int(part, 16))
            except ValueError as exc:
                raise ValueError(f"invalid newc field at {offset}") from exc
        mode, size, namesize = fields[1], fields[6], fields[11]
        if not 1 <= namesize <= 4096:
            raise ValueError("invalid newc pathname length")
        endname = offset + 110 + namesize
        if endname > len(archive) or archive[endname-1] != 0:
            raise ValueError("truncated or unterminated pathname")
        name = archive[offset+110:endname-1].decode("utf-8", "strict")
        begin = align4(endname)
        end = begin + size
        if end > len(archive):
            raise ValueError("truncated newc file data")
        data = archive[begin:end]
        offset = align4(end)
        if name == "TRAILER!!!":
            if size != 0:
                raise ValueError("invalid trailer")
            trailer = True
            break
        if not valid_path(name) or name in entries:
            raise ValueError(f"duplicate/unsafe initramfs entry: {name!r}")
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
            raise ValueError(f"unsupported initramfs entry mode: {name}")
        entries[name] = (mode, data)
        if offset <= start:
            raise ValueError("newc parser made no progress")
    if not trailer or any(b != 0 for b in archive[offset:]):
        raise ValueError("missing newc trailer or unexpected trailing data")
    return entries


def cpio_entry(name, mode, data, inode):
    namebuf = name.encode() + b"\x00"
    fields = (inode, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1,
              0, len(data), 0, 0, 0, 0, len(namebuf), 0)
    if any(x < 0 or x > 0xffffffff for x in fields):
        raise ValueError("newc size overflow")
    record = b"070701" + b"".join(f"{x:08x}".encode() for x in fields) + namebuf
    record += b"\x00" * (-len(record) % 4)
    record += data
    return record + b"\x00" * (-len(data) % 4)


def make_newc(entries):
    archive = bytearray()
    for inode, (name, (mode, data)) in enumerate(sorted(entries.items()), 1):
        archive.extend(cpio_entry(name, mode, data, inode))
    archive.extend(cpio_entry("TRAILER!!!", 0, b"", len(entries)+1))
    archive.extend(b"\x00" * (-len(archive) % 512))
    return bytes(archive)


def read_a01(path, expected_sha=A01_IMAGE_SHA):
    if sha_file(path) != expected_sha:
        raise ValueError("A01 initramfs SHA-256 differs from the fixed accepted boot artifact")
    with gzip.open(path, "rb") as reader:
        data = reader.read()
    return parse_newc(data)


def reference_elf_cases(reference):
    items = []
    for name, result in sorted(reference["cases"].items()):
        stem, dot, case = name.partition(".")
        if stem in BINARY_FOR:
            if not dot or SAFE_CASE.fullmatch(case) is None:
                raise ValueError("unsafe guest ELF case name: " + repr(name))
            if result.get("status") == "pass":
                items.append((name, stem, case))
    return items


def add_directory(entries, name):
    if name in entries:
        if not stat.S_ISDIR(entries[name][0]):
            raise ValueError(f"file conflicts with directory: {name}")
        return
    entries[name] = (stat.S_IFDIR | 0o755, b"")


def add_file(entries, name, data, mode=0o555):
    if not valid_path(name) or name in entries:
        raise ValueError(f"unsafe or duplicate path: {name}")
    for ancestor in reversed(PurePosixPath(name).parents):
        if str(ancestor) != ".":
            add_directory(entries, str(ancestor))
    entries[name] = (stat.S_IFREG | mode, data)


def make_guest_script(cases):
    lines = ["#!/bin/sh", "set -u", "umask 077", "fail=0",
             "/bin/busybox mkdir -p /tmp/a04"]
    for name, stem, case in cases:
        if (stem not in BINARY_FOR or SAFE_CASE.fullmatch(case) is None or
                name != stem + "." + case):
            raise ValueError("unsafe guest ELF command token")
        binary = "/usr/local/bin/a04/" + BINARY_FOR[stem]
        scratch = "/tmp/a04/" + name
        lines.extend([
            f"/bin/busybox mkdir -p '{scratch}'",
            f"echo 'A04_CASE_BEGIN={name}'",
            f"if '{binary}' " + (f"'{scratch}'" if stem.startswith("sqlite_") else f"'{case}' '{scratch}'") + "; then rc=0; else rc=$?; fail=1; fi",
            f"echo \"A04_CASE_END={name}:$rc\"",
        ])
    lines.extend(["exit \"$fail\"", ""])
    return "\n".join(lines).encode()


def inject_a01_init(original):
    decoded = original.decode("utf-8", "strict")
    if decoded.count(INIT_ANCHOR) != 1 or "TRILLIONNIUM_A01_BOOT_OK" not in decoded:
        raise ValueError("unrecognized A01 init; cannot safely inject workload without changing smoke")
    injection = ("echo TRILLIONNIUM_A04_WORKLOAD_BEGIN\n"
                 "if /bin/busybox sh /test/a04/guest-run.sh; then\n"
                 "    echo TRILLIONNIUM_A04_RUNNER_STATUS=0\n"
                 "else\n"
                 "    echo TRILLIONNIUM_A04_RUNNER_STATUS=1\n"
                 "fi\n"
                 "echo TRILLIONNIUM_A04_WORKLOAD_END\n")
    return decoded.replace(INIT_ANCHOR, injection + INIT_ANCHOR).encode()


def pack(a01_path, rootfs_dir, rootfs_manifest_path, reference, output, manifest_path, *, expected_a01_sha=A01_IMAGE_SHA):
    if output.exists() or manifest_path.exists():
        raise ValueError("output already exists; refusing to overwrite prior evidence")
    entries = read_a01(a01_path, expected_a01_sha)
    if "init" not in entries or "bin/busybox" not in entries:
        raise ValueError("A01 initramfs missing required init or BusyBox")
    root_manifest = json.loads(rootfs_manifest_path.read_text())
    captured = root_manifest["files"]
    if rootfs_dir.is_symlink() or not rootfs_dir.is_dir():
        raise ValueError("rootfs must be a real directory, not a symlink")
    members = list(rootfs_dir.rglob("*"))
    if any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in members):
        raise ValueError("rootfs contains symlink or special file")
    actual = {"/" + p.relative_to(rootfs_dir).as_posix(): p for p in members if p.is_file()}
    expected = {f["path"] for f in captured}
    if len(expected) != len(captured) or not all(isinstance(path, str) and
       path.startswith("/") and ".." not in path.split("/") for path in expected):
        raise ValueError("rootfs manifest has duplicate or invalid paths")
    if set(actual) != expected:
        raise ValueError("rootfs file list differs from pinned manifest")
    for f in captured:
        src=actual[f["path"]]
        if sha_file(src) != f["sha256"] or f"{src.stat().st_mode&0o777:04o}" != f["mode"]:
            raise ValueError("rootfs content or file permissions do not match manifest")
    verify_binary_identity(rootfs_dir, root_manifest, reference,
                           required_stems=BINARY_FOR)
    original_mode, original_init = entries["init"]
    if not stat.S_ISREG(original_mode):
        raise ValueError("A01 init is not regular file")
    entries["init"] = (original_mode, inject_a01_init(original_init))
    for dest, src in sorted(actual.items()):
        add_file(entries, dest.lstrip("/"), src.read_bytes(), mode=src.stat().st_mode & 0o777)
    cases = reference_elf_cases(reference)
    add_file(entries, "test/a04/guest-run.sh", make_guest_script(cases), mode=0o555)
    add_file(entries, "test/a04/a01-init-original.sh", original_init, mode=0o444)
    archive = make_newc(entries)
    # Independent round-trip of all payloads, symlinks, directories and modes.
    if parse_newc(archive) != entries:
        raise RuntimeError("newc roundtrip verification failed")
    container = io.BytesIO()
    with gzip.GzipFile(fileobj=container, mode="wb", filename="", mtime=0) as gz:
        gz.write(archive)
    data = container.getvalue()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    report = {"schema": 1, "kind": "a04_a01_guest_image_candidate", "qualified_guest": False,
              "a01_initramfs_sha256": sha_file(a01_path),
              "a01_original_init_sha256": sha_bytes(original_init),
              "a04_initramfs_sha256": sha_bytes(data),
              "a04_initramfs_bytes": len(data),
              "rootfs_manifest_sha256": sha_file(rootfs_manifest_path),
              "linux_reference_sha256": sha_bytes(json.dumps(reference, sort_keys=True).encode()),
              "elf": {stem: {"sha256": reference["binaries"][stem]["sha256"],
                                "interpreter": reference["binaries"][stem]["interpreter"]}
                      for stem in BINARY_FOR},
              "cases": [name for name, _, _ in cases], "case_count": len(cases),
              "included_a01_boot_checks": True, "writable_area": "initramfs /tmp (volatile)",
              "storage_durability_verified": False, "guest_execution_verified": False}
    manifest_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _json_unique_guest_object(serial_line):
    """Refuse ambiguous duplicate keys or nonstandard NaN/Infinity values."""
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate guest JSON key")
            result[key] = value
        return result

    def reject_constant(token):
        raise ValueError("invalid guest JSON constant: " + token)

    return json.loads(serial_line, object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)


def parse_serial(serial_text, reference, manifest, *, qemu_exit, kernel_sha=None, image_sha=None):
    expected_cases = set(manifest["cases"])
    results = {}
    active, payload, anomalies = None, [], []
    marker_positions = {}
    status_positions = []
    for line_no, original_line in enumerate(serial_text.splitlines()):
        line = original_line.strip()
        if "Uncaught panic:" in line or "Kernel panic - not syncing" in line:
            anomalies.append("kernel panic in serial output")
        if line in EXPECTED_MARKERS:
            if line in marker_positions:
                anomalies.append("duplicate boot/workload marker")
            else:
                marker_positions[line] = line_no
            if line == "TRILLIONNIUM_A04_WORKLOAD_END" and active is not None:
                anomalies.append("workload ended with unfinished case")
            continue
        if line.startswith("TRILLIONNIUM_A04_RUNNER_STATUS="):
            if line not in ("TRILLIONNIUM_A04_RUNNER_STATUS=0",
                            "TRILLIONNIUM_A04_RUNNER_STATUS=1"):
                anomalies.append("malformed runner status")
            status_positions.append((line_no, line.rsplit("=", 1)[-1]))
            if (active is not None or
                "TRILLIONNIUM_A04_WORKLOAD_BEGIN" not in marker_positions or
                "TRILLIONNIUM_A04_WORKLOAD_END" in marker_positions):
                anomalies.append("runner status outside workload completion")
            continue
        begin = CASE_BEGIN.match(line)
        finish = CASE_END.match(line)
        if begin or finish or line.startswith(("A04_CASE_BEGIN=", "A04_CASE_END=")):
            if ("TRILLIONNIUM_A01_BOOT_OK" not in marker_positions or
                "TRILLIONNIUM_A04_WORKLOAD_BEGIN" not in marker_positions or
                "TRILLIONNIUM_A04_WORKLOAD_END" in marker_positions or
                status_positions):
                anomalies.append("case outside workload phase")
            if not (begin or finish):
                anomalies.append("malformed case marker")
                continue
        if begin:
            name = begin.group(1)
            if active is not None or name not in expected_cases or name in results:
                anomalies.append("unexpected/duplicate case start")
                continue
            active, payload = name, []
        elif finish:
            name, status = finish.group(1), int(finish.group(2))
            if name != active:
                anomalies.append("case exit without matching start")
                continue
            parsed = None
            for candidate in payload:
                if candidate.startswith("{") and candidate.endswith("}"):
                    try:
                        obj = _json_unique_guest_object(candidate)
                    except (ValueError, json.JSONDecodeError):
                        anomalies.append("invalid or ambiguous guest JSON")
                        continue
                    if isinstance(obj, dict) and parsed is None:
                        parsed = obj
                    else:
                        anomalies.append("multiple JSON payloads")
            # A successful exit and {"ok":true} only establish that a guest
            # program *claims* success. An errno/IPC/SQLite fact can diverge
            # while it still returns zero. Qualification needs identical
            # reference observations, not a self-reported success bit.
            expected = reference["cases"][name]
            if len(payload) != 1:
                anomalies.append("unexpected or ambiguous guest case output")
            well_formed = (status == 0 and len(payload) == 1 and
                           isinstance(parsed, dict) and parsed.get("ok") is True)
            same_facts = well_formed and expected.get("status") == "pass" and parsed == expected.get("facts")
            results[name] = {"status": "pass" if same_facts else "fail", "exit_code": status,
                             "facts": parsed,
                             "error": None if same_facts else (
                                 "guest facts differ from reference" if well_formed else
                                 "guest exit failed or JSON output absent/invalid")}
            active, payload = None, []
        elif active:
            payload.append(line)
    if active is not None:
        anomalies.append("unfinished guest case")
    markers = {name: name in marker_positions for name in EXPECTED_MARKERS}
    runner_status = [value for _, value in status_positions]
    if all(markers.values()):
        ordering = [marker_positions[name] for name in EXPECTED_MARKERS]
        if ordering != sorted(ordering) or len(set(ordering)) != len(ordering):
            anomalies.append("out-of-order boot/workload markers")
        if len(status_positions) != 1 or not (
            marker_positions["TRILLIONNIUM_A04_WORKLOAD_BEGIN"] <
            status_positions[0][0] <
            marker_positions["TRILLIONNIUM_A04_WORKLOAD_END"]
        ):
            anomalies.append("missing/duplicated/out-of-phase runner status")
    trusted_input = bool(kernel_sha == A01_KERNEL_SHA and image_sha == manifest["a04_initramfs_sha256"])
    observed_all = (trusted_input and qemu_exit == 33 and all(markers.values())
                    and len(runner_status) == 1 and not anomalies and len(results)==len(expected_cases))
    qualified = observed_all and runner_status == ["0"] and all(
        x["status"] == "pass" for x in results.values())
    for name in expected_cases - results.keys():
        results[name] = {"status": "not_run", "reason": "guest did not produce this case marker"}
    for name in reference["cases"]:
        if name not in results:
            results[name] = {"status": "not_run", "reason": "not packaged into BusyBox ELF-only guest"}
    report = {"schema": 1, "suite": "a04-linux-guest-differential",
              "platform": {"system": "Asterinas candidate guest (unattested)",
                           "kernel_sha256": kernel_sha},
              "binaries": reference["binaries"], "cases": dict(sorted(results.items())),
              "boot_evidence": {"a01_kernel_elf_sha256_matches": kernel_sha == A01_KERNEL_SHA,
                                "a04_initramfs_sha256_matches": image_sha == manifest["a04_initramfs_sha256"],
                                "qemu_exit_code": qemu_exit, "markers": markers,
                                "runner_status": runner_status,
                                "anomalies": anomalies, "guest_execution_verified": observed_all,
                                "serial_sha256": sha_bytes(serial_text.encode())},
              "counts": {status: sum(x["status"] == status for x in results.values())
                         for status in ("pass", "fail", "not_run")},
              "guest_execution_verified": observed_all,
              "guest_compatibility_passed": qualified}
    return report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest="command",required=True)
    pp=sub.add_parser("pack",help="generate derived image using exact A01 accepted initramfs")
    pp.add_argument("--a01-initramfs",type=Path,required=True)
    pp.add_argument("--rootfs",type=Path,required=True)
    pp.add_argument("--rootfs-manifest",type=Path,required=True)
    pp.add_argument("--reference",type=Path,required=True)
    pp.add_argument("--output",type=Path,required=True)
    pp.add_argument("--manifest",type=Path,required=True)
    sp=sub.add_parser("parse",help="convert an ACTUAL QEMU serial log into a differential report")
    sp.add_argument("--serial",type=Path,required=True)
    sp.add_argument("--qemu-exit",type=int,required=True)
    sp.add_argument("--kernel-elf",type=Path,required=True)
    sp.add_argument("--guest-initramfs",type=Path,required=True)
    sp.add_argument("--reference",type=Path,required=True)
    sp.add_argument("--manifest",type=Path,required=True)
    sp.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    try:
        reference=json.loads(args.reference.read_text())
        if args.command=="pack":
            summary=pack(args.a01_initramfs,args.rootfs,args.rootfs_manifest,
                         reference,args.output,args.manifest)
            print(json.dumps({k:summary[k] for k in ("case_count","a04_initramfs_sha256","guest_execution_verified")}))
        else:
            manifest=json.loads(args.manifest.read_text())
            if sha_file(args.guest_initramfs)!=manifest["a04_initramfs_sha256"]:
                raise ValueError("guest-initramfs differs from pack manifest")
            report=parse_serial(args.serial.read_text(errors="replace"),reference,manifest,
                                qemu_exit=args.qemu_exit,kernel_sha=sha_file(args.kernel_elf),
                                image_sha=sha_file(args.guest_initramfs))
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
            # Emit only fixed-shape status scalars.  Do not echo guest facts,
            # paths or serial content to stdout where a caller could treat it
            # as an untrusted log channel.
            print(json.dumps({"case_count": len(report["cases"]),
                              "guest_execution_verified": bool(report["guest_execution_verified"]),
                              "guest_compatibility_passed": bool(report["guest_compatibility_passed"])}))
            return 0 if report["guest_compatibility_passed"] else 2
    except (OSError, ValueError, KeyError, EOFError, gzip.BadGzipFile) as exc:
        # Keep paths, serial text and other input-derived details out of the
        # process log; the machine-readable output already records the status.
        ap.exit(2,"A04 guest input rejected: " + type(exc).__name__ + "\n")
    return 0


if __name__=="__main__":
    sys.exit(main())
