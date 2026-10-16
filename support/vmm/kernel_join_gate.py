#!/usr/bin/env python3
"""Read-only, fail-closed A09/A01 kernel GPU passthrough source gate.

This program only inspects bounded source files from the checked-out
Asterinas tree.  It never opens a device, writes sysfs, changes a driver, or
assigns a PCI function.  Source evidence is useful for finding the next kernel
owner and for detecting a known unsafe global IOMMU mapping, but it is not a
hardware or compiler attestation.  The command therefore always returns the
blocked status (exit code 2), including when all source checks are satisfied.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat


KERNEL_PIN = "c4b7ed575b7b32773475b194d2ad41fb6d03765b"
MAX_SOURCE_BYTES = 512 * 1024

# Keep this list tied to the pinned source layout.  The architecture-specific
# VM files are optional because their absence is itself useful evidence: the
# current pinned tree contains Intel VMX but no AMD SVM or ARM EL2 backend.
SOURCE_PATHS = {
    "iommu_dma": "kernel/asterinas/ostd/src/arch/x86/iommu/dma_remapping/mod.rs",
    "iommu_irq": "kernel/asterinas/ostd/src/arch/x86/iommu/interrupt_remapping/mod.rs",
    "guest_mode": "kernel/asterinas/ostd/src/vm/guest_mode.rs",
    "dma_stream": "kernel/asterinas/ostd/src/mm/dma/dma_stream.rs",
    "resource_domain": "libs/os-control/src/lib.rs",
    "x86_vm": "kernel/asterinas/ostd/src/arch/x86/vm/mod.rs",
    "x86_vmx": "kernel/asterinas/ostd/src/arch/x86/vm/vmx/mod.rs",
    "amd_svm": "kernel/asterinas/ostd/src/arch/x86/vm/svm/mod.rs",
    "arm_el2": "kernel/asterinas/ostd/src/arch/arm/vm/mod.rs",
}

REQUIRED_SOURCES = (
    "iommu_dma",
    "iommu_irq",
    "guest_mode",
    "dma_stream",
    "resource_domain",
)

SCOPE_WORD = re.compile(
    r"\b(?:device|dev|group|iommu|pci|bdf|requester|rid|domain|location)\w*\b",
    re.IGNORECASE,
)


def _bounded_read(path: Path) -> bytes:
    """Read one regular source file without following the final symlink.

    Opening first and then fstat'ing the descriptor avoids the usual
    stat/open race.  O_NONBLOCK makes a FIFO safe to inspect: it is rejected
    after fstat instead of waiting for a writer.  The second size check catches
    a file that grows between stat and read.
    """

    fd = os.open(
        path,
        os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_BYTES:
            raise ValueError("source is not a bounded regular file")
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("source changed or grew beyond bounded read")
    return raw


def _read_sources_from(root: Path, paths: dict[str, str]):
    files = {}
    text = {}
    hashes = {}
    for name, relative in paths.items():
        path = root / relative
        try:
            raw = _bounded_read(path)
            decoded = raw.decode("utf-8")
            files[name] = {
                "path": relative,
                "present": True,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "error": None,
            }
            text[name] = decoded
            hashes[name] = files[name]["sha256"]
        except (OSError, UnicodeError, ValueError) as exc:
            files[name] = {
                "path": relative,
                "present": False,
                "bytes": None,
                "sha256": None,
                "error": str(exc),
            }
            text[name] = ""
            hashes[name] = None
    return files, text, hashes


def _read_sources(root: Path):
    return _read_sources_from(root, SOURCE_PATHS)


def _blank_non_code(source: str) -> str:
    """Mask comments and string/character literals while preserving newlines.

    Lexical evidence must not be forged by a comment or a string containing a
    fake function declaration or backend marker.  This is deliberately a
    small scanner rather than a Rust parser; the result is only a conservative
    source gate and never a semantic proof.
    """

    out = list(source)
    length = len(source)

    def blank(start: int, end: int) -> None:
        for index in range(start, min(end, length)):
            if source[index] != "\n":
                out[index] = " "

    index = 0
    while index < length:
        # Line comments.
        if source.startswith("//", index):
            end = source.find("\n", index + 2)
            blank(index, length if end < 0 else end)
            index = length if end < 0 else end
            continue

        # Nested block comments are legal in Rust.
        if source.startswith("/*", index):
            start = index
            index += 2
            depth = 1
            while index < length and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            blank(start, index)
            continue

        # Raw strings, including r###"..."###.  Rust permits an arbitrary
        # number of hashes; mask the complete literal before looking for code.
        if source[index] == "r":
            raw_match = re.match(r"r(#+)?\"", source[index:])
            if raw_match:
                hashes_in_delimiter = raw_match.group(1) or ""
                close = "\"" + hashes_in_delimiter
                end = source.find(close, index + len(raw_match.group(0)))
                end = length if end < 0 else end + len(close)
                blank(index, end)
                index = end
                continue

        # Ordinary strings.  Newlines are preserved even for malformed input.
        if source[index] == '"':
            start = index
            index += 1
            escaped = False
            while index < length:
                char = source[index]
                index += 1
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    break
            blank(start, index)
            continue

        # Mask a character literal when it has a nearby closing quote.  A Rust
        # lifetime such as `'a` is left untouched and cannot contain a fake
        # function declaration.
        if source[index] == "'" and index + 2 < length:
            if source[index + 1] == "\\":
                end = index + 4 if index + 3 < length and source[index + 3] == "'" else index
            else:
                end = index + 3 if source[index + 2] == "'" else index
            if end > index:
                blank(index, end)
                index = end
                continue

        index += 1
    return "".join(out)


def _matching_close(text: str, opening: int) -> int | None:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _function_arguments(source: str, name: str):
    """Return `(signature, args)` for every visible `fn name(...)`."""

    pattern = re.compile(r"\bfn\s+" + re.escape(name) + r"\b\s*(?:<[^>{}]*>\s*)?\(")
    found = []
    for match in pattern.finditer(source):
        opening = match.end() - 1
        closing = _matching_close(source, opening)
        if closing is None:
            found.append((source[match.start():], ""))
        else:
            found.append((source[match.start():closing + 1], source[opening + 1:closing]))
    return found


def _split_arguments(arguments: str):
    parts = []
    start = 0
    angle = paren = bracket = brace = 0
    for index, char in enumerate(arguments):
        if char == "<":
            angle += 1
        elif char == ">" and angle:
            angle -= 1
        elif char == "(":
            paren += 1
        elif char == ")" and paren:
            paren -= 1
        elif char == "[":
            bracket += 1
        elif char == "]" and bracket:
            bracket -= 1
        elif char == "{":
            brace += 1
        elif char == "}" and brace:
            brace -= 1
        elif char == "," and not (angle or paren or bracket or brace):
            parts.append(arguments[start:index])
            start = index + 1
    parts.append(arguments[start:])
    return [part.strip() for part in parts if part.strip()]


def _has_device_scope(arguments: str) -> bool:
    for argument in _split_arguments(arguments):
        if argument in ("self", "&self", "&mut self"):
            continue
        if ":" not in argument:
            continue
        name, type_name = argument.split(":", 1)
        if SCOPE_WORD.search(name + " " + type_name):
            return True
    return False


def _signature_report(source: str, name: str):
    definitions = _function_arguments(source, name)
    return {
        "definitions_found": len(definitions),
        "signatures": [signature.strip() for signature, _ in definitions],
        "all_definitions_device_scoped": bool(definitions)
        and all(_has_device_scope(arguments) for _, arguments in definitions),
    }


def _contains(source: str, *patterns: str) -> bool:
    return any(re.search(pattern, source, re.IGNORECASE) for pattern in patterns)


def audit(root: Path | str):
    """Inspect a checkout and return a JSON-serializable blocked report."""

    root = Path(root)
    files, raw_text, hashes = _read_sources(root)
    source = {name: _blank_non_code(value) for name, value in raw_text.items()}
    blockers = []

    for name in REQUIRED_SOURCES:
        if not files[name]["present"]:
            blockers.append("required_source_missing_or_unreadable:" + name)

    iommu = source["iommu_dma"]
    map_report = _signature_report(iommu, "map")
    unmap_report = _signature_report(iommu, "unmap")
    scoped_map = map_report["all_definitions_device_scoped"]
    scoped_unmap = unmap_report["all_definitions_device_scoped"]
    shared_iommu = bool(
        re.search(r"\bPciDeviceLocation\s*::\s*zero\s*\(", iommu)
        or re.search(r"\bPciDeviceLocation\s*::\s*all\s*\(", iommu)
        and re.search(r"specify_device_page_table", iommu, re.DOTALL)
    )
    if shared_iommu:
        blockers.append("iommu_shared_device_page_table_detected")
    if not (scoped_map and scoped_unmap):
        blockers.append("iommu_device_scoped_map_unmap_not_found")

    vm_text = "\n".join(source[name] for name in ("guest_mode", "x86_vm", "x86_vmx"))
    svm_text = "\n".join(source[name] for name in ("x86_vm", "x86_vmx", "amd_svm"))
    arm_text = source["arm_el2"]
    vmx_visible = _contains(
        vm_text,
        r"\bVmxGuard\b",
        r"\bVmcs\b",
        r"\bVMCS\b",
        r"\bvmxon\b",
    )
    svm_visible = _contains(
        svm_text,
        r"\bSvm\b",
        r"\bsvm\b",
        r"\bVmcb\b",
        r"\bVMCB\b",
        r"\bVMRUN\b",
        r"\bvmrun\b",
        r"\bNPT\b",
        r"\bnested_page\b",
    )
    el2_visible = _contains(
        arm_text,
        r"\bEL2\b",
        r"\bel2\b",
        r"\bhcr_el2\b",
        r"\bvttbr_el2\b",
        r"\bstage[_ -]?2\b",
        r"\bSMMU\b",
        r"\bVGIC\b",
        r"\bvgic\b",
    )
    if not vmx_visible:
        blockers.append("intel_vmx_source_evidence_missing")
    if not svm_visible:
        blockers.append("amd_svm_source_evidence_missing")
    if not el2_visible:
        blockers.append("arm_el2_source_evidence_missing")

    guest_visible = _contains(source["guest_mode"], r"\b(?:struct|enum)\s+GuestMode\b")
    dma_visible = _contains(source["dma_stream"], r"\b(?:struct|trait)\s+DmaStream\b")
    resource_visible = _contains(
        source["resource_domain"], r"\b(?:struct|enum|trait)\s+ResourceDomain\b"
    )
    irq_visible = _contains(
        source["iommu_irq"], r"\balloc_irt_entry\b", r"interrupt[_ ]?remap"
    )
    if not guest_visible:
        blockers.append("ostd_guest_mode_primitive_missing")
    if not dma_visible:
        blockers.append("ostd_dma_stream_primitive_missing")
    if not resource_visible:
        blockers.append("canonical_resource_domain_source_missing")
    if not irq_visible:
        blockers.append("ostd_interrupt_remapping_primitive_missing")

    # No source scan can prove these gates.  Keeping them unconditionally in
    # the report makes accidental conversion to an approval tool impossible.
    blockers.extend(
        (
            "per_iommu_group_dma_irq_isolation_not_hardware_verified",
            "linux_guest_gpu_passthrough_not_hardware_verified",
            "quiescence_and_dma_pin_accounting_not_hardware_verified",
            "hardware_virtualization_execution_not_verified",
            "gpu_reset_recovery_not_hardware_verified",
        )
    )

    observations = {
        "shared_iommu_page_table_source_pattern": shared_iommu,
        "device_scoped_map_signature_visible": scoped_map,
        "device_scoped_unmap_signature_visible": scoped_unmap,
        "map_signature": map_report,
        "unmap_signature": unmap_report,
        "ostd_guest_mode_primitive_visible": guest_visible,
        "ostd_dma_stream_primitive_visible": dma_visible,
        "host_resource_domain_type_visible": resource_visible,
        "ostd_interrupt_remapping_primitive_visible": irq_visible,
        "intel_vmx_source_visible": vmx_visible,
        "amd_svm_source_visible": svm_visible,
        "arm_el2_source_visible": el2_visible,
    }
    return {
        "schema": "a09.asterinas-gpu-kernel-join-source-gate.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "blocked",
        "passthrough_approved": False,
        "asterinas_gpu_verified": False,
        "scope": "bounded_static_source_inspection_only",
        "kernel_pin": KERNEL_PIN,
        "required_paths": SOURCE_PATHS,
        "source_sha256": hashes,
        "source_files": files,
        "observations": observations,
        "hard_blockers": sorted(set(blockers)),
        "next_owner_actions": {
            "A01": "Add device/group-scoped IOMMU domains, IRQ remapping, DMA quiescence and a real VM backend/lifecycle.",
            "A05": "Bind one physical group and queue incarnation to the canonical CapSpace/grant owner and revoke future admission.",
            "A06": "Charge pinned DMA pages, VM RAM and queue work in the existing ResourceDomain hierarchy without refund before quiescence.",
            "A00": "Review source pin, compiler evidence and independent isolated hardware logs; source scanning cannot approve passthrough.",
        },
    }


def inspect_source(kernel_root: Path | str, target_arch: str = "x86_64"):
    """Compatibility view for the earlier kernel-root source gate.

    ``audit`` is the repository-root API used by the current command.  Older
    callers pass the imported ``kernel/asterinas`` directory and expect a
    compact report.  This adapter performs the same bounded reads and lexical
    checks without treating a source-complete fixture as hardware evidence.
    A coherent fixture is labelled ``manual_review_required``; it is never a
    pass and still reports both hardware flags as false.
    """

    root = Path(kernel_root)
    legacy_paths = {
        "iommu_dma": "ostd/src/arch/x86/iommu/dma_remapping/mod.rs",
        "x86_vm": "ostd/src/arch/x86/vm/mod.rs",
        "x86_context": "ostd/src/arch/x86/vm/context.rs",
        "x86_ept": "ostd/src/arch/x86/vm/ept.rs",
        "x86_guest_mode": "ostd/src/arch/x86/vm/guest_mode.rs",
        "x86_vmx": "ostd/src/arch/x86/vm/vmx/mod.rs",
    }
    files, raw_text, hashes = _read_sources_from(root, legacy_paths)
    source = {name: _blank_non_code(value) for name, value in raw_text.items()}
    iommu = source["iommu_dma"]
    map_report = _signature_report(iommu, "map")
    unmap_report = _signature_report(iommu, "unmap")
    iommu_scoped = (
        map_report["all_definitions_device_scoped"]
        and unmap_report["all_definitions_device_scoped"]
    )
    uses_zero_device = bool(
        re.search(r"\bPciDeviceLocation\s*::\s*zero\s*\(", iommu)
    )
    vmx_files = ("x86_vm", "x86_context", "x86_ept", "x86_guest_mode", "x86_vmx")
    vmx_source = all(files[name]["present"] for name in vmx_files)
    blockers = []
    if target_arch != "x86_64":
        blockers.append("unsupported target architecture: " + str(target_arch))
    if not iommu_scoped:
        blockers.append("IOMMU map/unmap is not proven device/group scoped")
    if uses_zero_device:
        blockers.append("IOMMU source uses a zero/shared device identity")
    if not vmx_source:
        blockers.append("VMX source evidence is incomplete")
    if not files["iommu_dma"]["present"]:
        blockers.append("required IOMMU source is missing or unreadable")
    status = "manual_review_required" if not blockers else "blocked"
    return {
        "schema": "a09.asterinas-kernel-source-gate.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "target_arch": target_arch,
        "source": {
            "kernel_pin": KERNEL_PIN,
            "iommu_device_scoped": iommu_scoped,
            "iommu_uses_zero_device": uses_zero_device,
            "vmx_source": vmx_source,
            "map_signature": map_report,
            "unmap_signature": unmap_report,
            "source_sha256": hashes,
            "files": files,
        },
        "blockers": sorted(set(blockers)),
        "hardware_execution_verified": False,
        "device_assignment_verified": False,
        "passthrough_approved": False,
        "notes": "Static source evidence only; manual review is not hardware or GPU-compute proof.",
    }


def _write_json(path: Path, payload: str) -> None:
    """Write only to a regular, non-symlink output path."""

    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="checked-out repository root",
    )
    parser.add_argument(
        "--kernel-root",
        type=Path,
        default=None,
        help="compatibility form: imported kernel/asterinas directory",
    )
    parser.add_argument(
        "--target-arch",
        default="x86_64",
        help="compatibility gate architecture (default: x86_64)",
    )
    parser.add_argument("--output", default="-", help="'-' prints JSON")
    args = parser.parse_args()
    result = (
        inspect_source(args.kernel_root, args.target_arch)
        if args.kernel_root is not None
        else audit(args.repo_root)
    )
    payload = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output == "-":
        print(payload, end="")
    else:
        _write_json(Path(args.output), payload)
    return 3 if result["status"] == "manual_review_required" else 2


if __name__ == "__main__":
    raise SystemExit(main())
