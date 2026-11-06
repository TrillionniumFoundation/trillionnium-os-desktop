# Explicit reviewed reader and static-ELF modules; their main() entries are never called.
READER_SOURCE = '#!/usr/bin/env python3\n"""Read two proposed host aapt2 paths and the already pinned aapt closure.\n\nNever execute a candidate, invoke Android, take an action lock, or read an\nexisting Main process. Existence and ELF headers do not establish provenance,\ncompatibility, or permission to run a candidate.\n"""\nimport hashlib\nimport json\nimport os\nimport stat\nimport struct\nimport sys\nimport time\n\nsys.dont_write_bytecode = True\nSTAT = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",\n        "st_size", "st_mtime_ns", "st_ctime_ns")\nPARENT_ID = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink")\nMAX_CANDIDATE = 64 * 1024 * 1024\nDEPS = {\n    "path": "/home/alex/work/pocket4-app-identities-20261105-r12-01/dependencies.json",\n    "sha256": "dfe1182d8e0da4d3d6e842736378539df33e03a87cf0ed9ab4bbe9ae1f26c041",\n}\nAAPT = {\n    "path": "/usr/lib/android-sdk/build-tools/debian/aapt",\n    "bytes": 30680,\n    "sha256": "d9c0d90fc4bcf03d57cbf4fe19ca66c80280ac760c53245c8678b9837844b972",\n}\nCANDIDATES = (\n    "/usr/lib/android-sdk/build-tools/debian/aapt2",\n    "/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/sdk/tools/linux/bin/aapt2",\n)\n\n\ndef need(value, reason):\n    if not value:\n        raise RuntimeError(reason)\n\n\ndef canonical(value):\n    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")\n\n\ndef metadata(fd):\n    value = os.fstat(fd)\n    return {key: getattr(value, key) for key in STAT}\n\n\ndef path_parts(path):\n    need(type(path) is str and path.startswith("/"), "ABSOLUTE_PATH_REQUIRED")\n    parts = path[1:].split("/")\n    need(all(part not in ("", ".", "..") for part in parts), "CANONICAL_PATH_REQUIRED")\n    return parts\n\n\nclass HeldPath:\n    """Own only descriptors opened by this reader; never close by scanning."""\n    def __init__(self, path):\n        self.path, self.parts = path, path_parts(path)\n        self.fds, self.parents, self.fd, self.missing = [], [], None, None\n\n    def open(self):\n        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)\n        self.fds.append(parent)\n        self.parents.append({"path": "/", "fd": parent, "stat": metadata(parent)})\n        for index, name in enumerate(self.parts[:-1]):\n            try:\n                parent = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)\n            except FileNotFoundError:\n                self.missing = {"parent_fd": self.parents[-1]["fd"], "name": name,\n                                "component": "/" + "/".join(self.parts[:index + 1])}\n                return self\n            self.fds.append(parent)\n            self.parents.append({"path": "/" + "/".join(self.parts[:index + 1]), "fd": parent, "stat": metadata(parent)})\n        try:\n            self.fd = os.open(self.parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)\n        except FileNotFoundError:\n            self.missing = {"parent_fd": parent, "name": self.parts[-1], "component": self.path}\n            return self\n        self.fds.append(self.fd)\n        return self\n\n    def verify_parent_paths(self):\n        new = []\n        try:\n            parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)\n            new.append(parent)\n            for index, row in enumerate(self.parents):\n                if index:\n                    parent = os.open(self.parts[index - 1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)\n                    new.append(parent)\n                current, held = metadata(parent), metadata(row["fd"])\n                need(all(current[key] == held[key] == row["stat"][key] for key in PARENT_ID), "PARENT_IDENTITY_CHANGED")\n        finally:\n            errors = []\n            for fd in reversed(new):\n                try:\n                    os.close(fd)\n                except OSError:\n                    errors.append(fd)\n            need(not errors, "PARENT_RECHECK_FD_CLOSE_FAILED")\n\n    def close(self):\n        errors = []\n        for fd in reversed(self.fds):\n            try:\n                os.close(fd)\n            except OSError:\n                errors.append(fd)\n        self.fds.clear()\n        need(not errors, "OWNED_FD_CLOSE_FAILED")\n\n\ndef read_regular(path, limit, require_root=False, expected=None):\n    held = HeldPath(path)\n    try:\n        held.open()\n        parents = [{"path": row["path"], "stat": row["stat"]} for row in held.parents]\n        if held.missing is not None:\n            try:\n                os.stat(held.missing["name"], dir_fd=held.missing["parent_fd"], follow_symlinks=False)\n            except FileNotFoundError:\n                pass\n            else:\n                raise RuntimeError("MISSING_COMPONENT_CHANGED_DURING_OBSERVATION")\n            held.verify_parent_paths()\n            return {"path": path, "status": "ABSENT_AT_OBSERVATION", "missing_component": held.missing["component"],\n                    "parents": parents, "parent_identity_rechecked": True}, None\n        before = metadata(held.fd)\n        need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"] == 1, "REGULAR_SINGLE_LINK_FILE_REQUIRED")\n        need(not require_root or before["st_uid"] == 0, "PINNED_DEPENDENCY_ROOT_OWNER_REQUIRED")\n        need(0 < before["st_size"] <= limit, "FILE_SIZE_BOUND")\n        digest, head, body, count = hashlib.sha256(), bytearray(), bytearray(), 0\n        end = time.monotonic() + 20\n        while count <= limit:\n            need(time.monotonic() < end, "BOUNDED_READ_DEADLINE")\n            part = os.read(held.fd, min(65536, limit + 1 - count))\n            if not part:\n                break\n            count += len(part)\n            digest.update(part)\n            head.extend(part[:max(0, 64 - len(head))])\n            if limit <= 262144:\n                body.extend(part)\n        need(count == before["st_size"] and metadata(held.fd) == before, "HELD_FILE_CHANGED")\n        again = os.open(held.parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=held.parents[-1]["fd"])\n        try:\n            need(metadata(again) == before, "FILE_PATH_CHANGED")\n        finally:\n            os.close(again)\n        held.verify_parent_paths()\n        row = {"path": path, "status": "OBSERVED_REGULAR_FILE", "bytes": count, "sha256": digest.hexdigest(),\n               "stat": before, "parents": parents, "held_file_and_path_full_stat_rechecked": True,\n               "parent_identity_rechecked": True, "header_64_hex": bytes(head).hex()}\n        if expected is not None:\n            need(row["sha256"] == expected["sha256"] and ("bytes" not in expected or row["bytes"] == expected["bytes"]), "EXISTING_PIN_CHANGED")\n        return row, bytes(body) if limit <= 262144 else None\n    finally:\n        held.close()\n\n\ndef elf_header(row):\n    raw = bytes.fromhex(row["header_64_hex"])\n    value = {"elf": raw[:4] == b"\\x7fELF", "host_x86_64_header": False, "execution_performed": False}\n    if len(raw) >= 64 and value["elf"]:\n        value.update(elf_class=raw[4], data_encoding=raw[5], identification_version=raw[6])\n        if raw[4:7] == b"\\x02\\x01\\x01":\n            kind, machine, version = struct.unpack_from("<HHI", raw, 16)\n            value.update(elf_type=kind, machine=machine, header_version=version,\n                         host_x86_64_header=kind in (2, 3) and machine == 62 and version == 1)\n    return value\n\n\ndef main():\n    need(os.getuid() == os.geteuid() == 0, "EXISTING_AUTHORIZED_ROOT_READER_REQUIRED")\n    before = len(os.listdir("/proc/self/fd"))\n    result = {"schema": "pocket4-two-proposed-aapt2-host-candidates-v1", "ok": False, "candidates": [], "errors": [],\n              "tool_execution_authorized_by_this_result": False, "candidate_provenance_verified": False,\n              "candidate_compatibility_verified": False, "candidate_executions": 0,\n              "Main_reads": 0, "Android_commands": 0, "native_commands": 0, "namespace_entries": 0,\n              "action_lock_acquired": False, "installs": 0, "UI_actions": 0, "permission_changes": 0,\n              "existing_files_modified": False, "automatic_retry": False,\n              "original_failed_audit_reclassified": False, "process_FDs_before": before}\n    try:\n        dependencies, raw = read_regular(DEPS["path"], 262144, True, DEPS)\n        need(raw is not None, "EXISTING_DEPENDENCIES_ABSENT")\n        deps = json.loads(raw)\n        expected_aapt = {"declared_path": AAPT["path"], "resolved_path": AAPT["path"],\n                         "bytes": AAPT["bytes"], "sha256": AAPT["sha256"]}\n        need(deps["files"]["aapt"] == expected_aapt, "EXISTING_AAPT_DEPENDENCY_DIFFERS")\n        result["fixed_dependencies"] = dependencies\n        result["aapt2_already_declared_in_fixed_dependencies"] = any("aapt2" in key.lower() for key in deps["files"])\n        original, unused = read_regular(AAPT["path"], 262144, True, AAPT)\n        need(original["status"] == "OBSERVED_REGULAR_FILE", "EXISTING_AAPT_ABSENT")\n        result["original_aapt"] = original\n        for path in CANDIDATES:\n            try:\n                row, unused = read_regular(path, MAX_CANDIDATE)\n                row["path_basis"] = "explicit_proposed_candidate_not_previously_observed"\n                if row["status"] == "OBSERVED_REGULAR_FILE":\n                    row["elf_header"] = elf_header(row)\n                    row["provenance"] = "UNKNOWN_NOT_ESTABLISHED_BY_PATH_OR_HEADER"\n                result["candidates"].append(row)\n            except (OSError, RuntimeError) as error:\n                result["candidates"].append({"path": path, "status": "NOT_INSPECTED_SAFELY", "type": type(error).__name__,\n                                             "reason": str(error)[:200], "errno": getattr(error, "errno", None)})\n                result["errors"].append({"path": path, "type": type(error).__name__})\n        result["ok"] = len(result["candidates"]) == len(CANDIDATES) and not result["errors"]\n    except BaseException as error:\n        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:200]})\n    result["process_FDs_after"] = len(os.listdir("/proc/self/fd"))\n    if result["process_FDs_after"] != before:\n        result["errors"].append({"reason": "HOST_READER_DESCRIPTOR_DIFFERENCE"})\n        result["ok"] = False\n    raw = canonical(result)\n    need(len(raw) <= 65536, "RESULT_BYTE_BOUND")\n    print(raw.decode("ascii"), flush=True)\n    return 0 if result["ok"] else 1\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
READER_SHA = '5b56807f415bdce9be10f90952adfee063cc9f26bcd4deb91d8897bdd9b672f3'
ELF_SOURCE = '"""Bounded ELF64LE/x86_64 static metadata from a caller-owned, already pinned FD.\n\nThe only FD operation here is os.pread. This module never opens, closes, seeks,\nmaps or executes a file and never searches a library path. The caller owns all\nidentity/hash/stat checks and retains/then closes its FD. Results describe file\nmetadata, not an actual loader resolution, ABI compatibility or execution proof.\n\nELF layouts/constants follow Elf64_Ehdr/Phdr/Dyn in the system <elf.h>;\nunknown dynamic tags remain outside this narrow interpretation.\n"""\nimport os\nimport struct\n\n__all__ = ["ELFError", "inspect_elf_fd"]\n\nMAX_FILE_BYTES = 512 * 1024 * 1024\nMAX_PHNUM = 1024\nMAX_DYNAMIC_BYTES = 64 * 1024\nMAX_STRTAB_BYTES = 4 * 1024 * 1024\nMAX_READ_BYTES = 5 * 1024 * 1024\nMAX_STRING_BYTES = 4096\nMAX_NEEDED = 128\nU64_END = 1 << 64\nPT_LOAD, PT_DYNAMIC, PT_INTERP = 1, 2, 3\nDT_NULL, DT_NEEDED, DT_STRTAB, DT_STRSZ, DT_RPATH, DT_RUNPATH = 0, 1, 5, 10, 15, 29\nEXTRA_LOAD_STRINGS = {0x6ffffefa: "DT_CONFIG", 0x6ffffefb: "DT_DEPAUDIT",\n                      0x6ffffefc: "DT_AUDIT", 0x7ffffffd: "DT_AUXILIARY",\n                      0x7fffffff: "DT_FILTER"}\n\nclass ELFError(ValueError):\n    """Unsupported shape, ambiguous mapping, malformed data or exceeded bound."""\n\ndef _need(value, reason):\n    if not value:\n        raise ELFError(reason)\n\ndef inspect_elf_fd(fd, size):\n    """Return static metadata; preserve the borrowed FD and its current offset.\n\n    Supports ET_EXEC/ET_DYN, normal (non-extended) program-header counts and\n    bounded, unique file-backed string-table mapping. Rejects unsupported or\n    malformed forms instead of inferring dependencies. Dynamic loader audit,\n    filter and configuration strings are reported separately so callers can\n    explicitly reject them. RPATH/RUNPATH are raw strings, including empty\n    strings; they are never expanded or normalized here.\n    """\n    _need(type(fd) is int and fd >= 0, "BORROWED_FD_REQUIRED")\n    _need(type(size) is int and 64 <= size <= MAX_FILE_BYTES, "ELF_FILE_SIZE_BOUND")\n    read_total = 0\n\n    def span(offset, count):\n        _need(type(offset) is int and type(count) is int and 0 <= offset <= size\n              and 0 <= count <= size - offset, "FILE_SPAN_OUT_OF_BOUNDS")\n\n    def read_at(offset, count):\n        nonlocal read_total\n        span(offset, count)\n        _need(count <= MAX_READ_BYTES - read_total, "PREAD_TOTAL_BOUND")\n        read_total += count\n        chunks = []\n        got = 0\n        while got < count:\n            block = os.pread(fd, count - got, offset + got)\n            _need(block, "SHORT_PREAD")\n            chunks.append(block)\n            got += len(block)\n        return b"".join(chunks)\n\n    head = read_at(0, 64)\n    fields = struct.unpack("<16sHHIQQQIHHHHHH", head)\n    ident, kind, machine, version, entry, phoff, shoff, flags, ehsize, phentsize, phnum, shentsize, shnum, shstrndx = fields\n    _need(ident[:4] == b"\\x7fELF" and ident[4] == 2 and ident[5] == 1 and ident[6] == 1,\n          "ELF64_LITTLE_ENDIAN_VERSION1_REQUIRED")\n    _need(machine == 62 and version == 1 and kind in (2, 3), "X86_64_EXEC_OR_DYN_REQUIRED")\n    _need(ehsize == 64 and phentsize == 56, "EXACT_ELF64_HEADER_LAYOUT_REQUIRED")\n    _need(0 < phnum <= MAX_PHNUM and phnum != 0xffff, "NORMAL_BOUNDED_PHNUM_REQUIRED")\n    _need(phoff >= 64, "PROGRAM_HEADERS_OVERLAP_ELF_HEADER")\n    table = read_at(phoff, phnum * 56)\n    loads, dynamics, interps = [], [], []\n    for index in range(phnum):\n        values = struct.unpack_from("<IIQQQQQQ", table, index * 56)\n        ptype, pflags, offset, address, physical, file_bytes, memory_bytes, alignment = values\n        span(offset, file_bytes)\n        _need(address + memory_bytes <= U64_END, "VIRTUAL_SPAN_OVERFLOW")\n        _need(alignment in (0, 1) or alignment & (alignment - 1) == 0, "SEGMENT_ALIGNMENT_NOT_POWER_OF_TWO")\n        segment = {"index": index, "offset": offset, "vaddr": address,\n                   "file_bytes": file_bytes, "memory_bytes": memory_bytes,\n                   "flags": pflags, "alignment": alignment}\n        if ptype == PT_LOAD:\n            _need(file_bytes <= memory_bytes, "LOAD_FILE_EXCEEDS_MEMORY")\n            _need(alignment in (0, 1) or (address - offset) % alignment == 0, "LOAD_ALIGNMENT_CONGRUENCE")\n            loads.append(segment)\n        elif ptype == PT_DYNAMIC:\n            dynamics.append(segment)\n        elif ptype == PT_INTERP:\n            interps.append(segment)\n    _need(0 < len(loads) <= 128, "BOUNDED_LOAD_SEGMENTS_REQUIRED")\n    _need(len(dynamics) <= 1 and len(interps) <= 1, "DUPLICATE_DYNAMIC_OR_INTERPRETER")\n\n    def map_unique(address, count):\n        _need(type(address) is int and 0 <= address < U64_END and 0 < count <= U64_END - address,\n              "DYNAMIC_VIRTUAL_SPAN_OUT_OF_BOUNDS")\n        end = address + count\n        cuts = {address, end}\n        for segment in loads:\n            for boundary in (segment["vaddr"], segment["vaddr"] + segment["memory_bytes"]):\n                if address < boundary < end:\n                    cuts.add(boundary)\n        ordered = sorted(cuts)\n        pieces = []\n        for start, stop in zip(ordered, ordered[1:]):\n            matches = [p for p in loads if p["vaddr"] <= start\n                       and stop <= p["vaddr"] + p["memory_bytes"]]\n            _need(len(matches) == 1, "VIRTUAL_MAPPING_NOT_UNIQUE")\n            chosen = matches[0]\n            _need(stop <= chosen["vaddr"] + chosen["file_bytes"], "VIRTUAL_SPAN_NOT_FILE_BACKED")\n            offset = chosen["offset"] + start - chosen["vaddr"]\n            span(offset, stop - start)\n            pieces.append({"vaddr": start, "offset": offset, "bytes": stop - start,\n                           "load_segment_index": chosen["index"]})\n        _need(sum(p["bytes"] for p in pieces) == count, "MAPPED_SPAN_NOT_COMPLETE")\n        return pieces\n\n    def text(raw, label):\n        _need(raw and len(raw) <= MAX_STRING_BYTES and b"\\0" not in raw\n              and all(v >= 32 and v != 127 for v in raw), label + "_INVALID_STRING")\n        try:\n            return raw.decode("utf-8", "strict")\n        except UnicodeDecodeError as error:\n            raise ELFError(label + "_NOT_UTF8") from error\n\n    interpreter = None\n    if interps:\n        p = interps[0]\n        _need(1 < p["file_bytes"] <= MAX_STRING_BYTES, "INTERPRETER_LENGTH_BOUND")\n        raw = read_at(p["offset"], p["file_bytes"])\n        _need(raw.endswith(b"\\0") and raw.count(b"\\0") == 1, "INTERPRETER_TERMINATION")\n        interpreter = text(raw[:-1], "INTERPRETER")\n        _need(interpreter.startswith("/"), "ABSOLUTE_INTERPRETER_REQUIRED")\n\n    result = {"format": "ELF64LE", "type": "ET_EXEC" if kind == 2 else "ET_DYN",\n              "machine": "EM_X86_64", "machine_id": machine, "osabi": ident[7],\n              "abi_version": ident[8], "interpreter": interpreter,\n              "needed": [], "rpath": None, "runpath": None,\n              "additional_loader_directives": [], "load_segments": loads,\n              "program_header_count": phnum, "dynamic": None, "string_table": None,\n              "is_loader_resolution_proof": False,\n              "unknown_dynamic_tags_interpreted": False,\n              "fd_ownership": "borrowed_pread_only_caller_retains",\n              "read_bytes": None}\n    if not dynamics:\n        _need(interpreter is None, "INTERPRETER_WITHOUT_DYNAMIC_UNSUPPORTED")\n        result["read_bytes"] = read_total\n        return result\n    p = dynamics[0]\n    _need(16 <= p["file_bytes"] <= MAX_DYNAMIC_BYTES and p["file_bytes"] % 16 == 0\n          and p["file_bytes"] <= p["memory_bytes"], "DYNAMIC_TABLE_SIZE_BOUND")\n    dynamic_map = map_unique(p["vaddr"], p["file_bytes"])\n    _need(all(piece["offset"] == p["offset"] + piece["vaddr"] - p["vaddr"]\n              for piece in dynamic_map), "DYNAMIC_FILE_AND_VIRTUAL_MAPPING_DIFFER")\n    raw = read_at(p["offset"], p["file_bytes"])\n    singleton, needed_offsets, extra_offsets, other_tags = {}, [], [], set()\n    terminated = False\n    used_entries = 0\n    for at in range(0, len(raw), 16):\n        tag, value = struct.unpack_from("<qQ", raw, at)\n        used_entries += 1\n        if tag == DT_NULL:\n            terminated = True\n            break\n        if tag in (DT_STRTAB, DT_STRSZ, DT_RPATH, DT_RUNPATH):\n            _need(tag not in singleton, "DUPLICATE_DYNAMIC_SINGLETON")\n            singleton[tag] = value\n        elif tag == DT_NEEDED:\n            needed_offsets.append(value)\n            _need(len(needed_offsets) <= MAX_NEEDED, "NEEDED_COUNT_BOUND")\n        elif tag in EXTRA_LOAD_STRINGS:\n            extra_offsets.append((tag, value))\n            _need(len(extra_offsets) <= 32, "EXTRA_LOADER_DIRECTIVE_BOUND")\n        else:\n            other_tags.add(tag)\n    _need(terminated, "DYNAMIC_TABLE_UNTERMINATED")\n    _need(DT_STRTAB in singleton and DT_STRSZ in singleton, "DYNAMIC_STRING_TABLE_REQUIRED")\n    string_bytes = singleton[DT_STRSZ]\n    _need(0 < string_bytes <= MAX_STRTAB_BYTES, "STRING_TABLE_SIZE_BOUND")\n    string_map = map_unique(singleton[DT_STRTAB], string_bytes)\n    strings = b"".join(read_at(piece["offset"], piece["bytes"]) for piece in string_map)\n    _need(strings[0] == 0 and strings[-1] == 0, "STRING_TABLE_EDGE_TERMINATORS_REQUIRED")\n\n    def string_at(offset, label, allow_empty=False):\n        _need(type(offset) is int and 0 <= offset < string_bytes, label + "_OFFSET_OUT_OF_BOUNDS")\n        end = strings.find(b"\\0", offset, min(offset + MAX_STRING_BYTES, string_bytes))\n        _need(end >= offset, label + "_UNTERMINATED_OR_TOO_LONG")\n        if end == offset and allow_empty:\n            return ""\n        return text(strings[offset:end], label)\n\n    result["needed"] = [string_at(o, "NEEDED") for o in needed_offsets]\n    result["rpath"] = string_at(singleton[DT_RPATH], "RPATH", True) if DT_RPATH in singleton else None\n    result["runpath"] = string_at(singleton[DT_RUNPATH], "RUNPATH", True) if DT_RUNPATH in singleton else None\n    result["additional_loader_directives"] = [\n        {"tag": tag, "name": EXTRA_LOAD_STRINGS[tag], "value": string_at(o, EXTRA_LOAD_STRINGS[tag])}\n        for tag, o in extra_offsets]\n    dynamic_indexes = list(dict.fromkeys(piece["load_segment_index"] for piece in dynamic_map))\n    string_indexes = list(dict.fromkeys(piece["load_segment_index"] for piece in string_map))\n    string_contiguous = all(piece["offset"] == string_map[0]["offset"]\n                            + piece["vaddr"] - singleton[DT_STRTAB] for piece in string_map)\n    result["dynamic"] = {"offset": p["offset"], "vaddr": p["vaddr"],\n                         "bytes": p["file_bytes"],\n                         "load_segment_index": dynamic_indexes[0] if len(dynamic_indexes) == 1 else None,\n                         "mappings": dynamic_map,\n                         "entries_through_null": used_entries,\n                         "other_tags_not_interpreted": sorted(other_tags)}\n    result["string_table"] = {"offset": string_map[0]["offset"] if string_contiguous else None,\n                              "vaddr": singleton[DT_STRTAB], "bytes": string_bytes,\n                              "load_segment_index": string_indexes[0] if len(string_indexes) == 1 else None,\n                              "mappings": string_map}\n    result["read_bytes"] = read_total\n    return result\n\n'
ELF_SHA = 'f829cd8664dc5f7172274b4917f70c60114c3bfb43694422c1a5412718b432dd'
CANDIDATE = {'bytes': 54512, 'file': {'st_ctime_ns': 1791415705179294996, 'st_dev': 66306, 'st_gid': 0, 'st_ino': 108138273, 'st_mode': 33261, 'st_mtime_ns': 1757926427000000000, 'st_nlink': 1, 'st_size': 54512, 'st_uid': 0}, 'path': '/usr/lib/android-sdk/build-tools/debian/aapt2', 'sha256': '0e9ff92342040acdfd03e8708512f4e02353e3ca0a2b85ea2950da659110b009'}

#!/usr/bin/env python3
"""Host-only installed AAPT2 provenance, static dependencies, and help/version.

Final source embeds the already reviewed nofollow reader and a separately
reviewed static ELF parser. No APK is opened or passed to a tool. The local
dpkg records are provenance evidence, not a new distribution signature proof.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types
import zlib

sys.dont_write_bytecode = True

# The source assembler supplies READER_SOURCE / READER_SHA and ELF_SOURCE /
# ELF_SHA from exact reviewed files, plus CANDIDATE from actual inventory JSON.
COLLECTOR = {
    "path": "/home/alex/work/pocket4-successor-install-audit-source-20261106-r1/audit_successor_apks.py",
    "bytes": 29242, "sha256": "faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a",
}
INVENTORY_REFERENCE = {
    "job_id": "1a1b194cd9b-fc05-79b1", "stdout_bytes": 9876,
    "stdout_sha256": "60ee9c47cb1719343a1667d306e26086d66f2376d62b8c5251f4e64446887341",
}
OUTPUT = "/home/alex/work/pocket4-aapt2-provenance-interface-20261106-r2"
SYSTEM_LIBRARY_ROOTS = ("/usr/lib", "/lib", "/lib64")
SEARCH_DIRS = ("/usr/lib/x86_64-linux-gnu/android", "/usr/lib/x86_64-linux-gnu", "/lib/x86_64-linux-gnu", "/usr/lib64", "/lib64")
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_RESULT = 262144


def required(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def frozen_module(source, digest, name):
    raw = source.encode("utf-8")
    required(sha(raw) == digest, "EMBEDDED_REVIEWED_SOURCE_CHANGED")
    module = types.ModuleType(name)
    module.__file__ = "<" + name + ">"
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    return module


class BoundFile:
    """Hold one root-owned host file and retain the original reader's guards."""
    def __init__(self, reader, path, limit, expected=None, resolve=False):
        self.reader, self.declared, self.limit = reader, path, limit
        self.resolved = str(Path(path).resolve(strict=True)) if resolve else path
        self.held = None
        observed, unused = reader.read_regular(self.resolved, limit, True, expected)
        required(observed["status"] == "OBSERVED_REGULAR_FILE", "REQUIRED_HOST_FILE_ABSENT")
        self.observed = observed
        try:
            self.held = reader.HeldPath(self.resolved)
            self.held.open()
            required(self.held.fd is not None and reader.metadata(self.held.fd) == observed["stat"], "HOST_FILE_CHANGED_BETWEEN_BINDINGS")
            if expected is not None and "file" in expected:
                required(observed["stat"] == expected["file"], "ACTUAL_INVENTORY_FILE_STAT_CHANGED")
            required(str(Path(self.declared).resolve(strict=True)) == self.resolved, "HOST_PATH_RESOLUTION_CHANGED")
        except BaseException:
            self.close()
            raise

    def content(self, limit):
        required(self.observed["bytes"] <= limit, "CONTENT_SIZE_BOUND")
        raw = bytearray()
        while len(raw) < self.observed["bytes"]:
            part = os.pread(self.held.fd, min(65536, self.observed["bytes"] - len(raw)), len(raw))
            required(bool(part), "HOST_PREAD_PROGRESS")
            raw.extend(part)
        required(sha(raw) == self.observed["sha256"] and self.reader.metadata(self.held.fd) == self.observed["stat"], "HOST_CONTENT_CHANGED")
        return bytes(raw)

    def recheck(self):
        required(self.reader.metadata(self.held.fd) == self.observed["stat"], "HELD_HOST_FILE_CHANGED")
        required(str(Path(self.declared).resolve(strict=True)) == self.resolved, "HOST_PATH_RESOLUTION_CHANGED")
        fresh, unused = self.reader.read_regular(self.resolved, self.limit, True)
        required(all(fresh[key] == self.observed[key] for key in ("bytes", "sha256", "stat")), "HOST_BYTES_OR_PATH_CHANGED")
        self.held.verify_parent_paths()

    def pin(self):
        return {"declared_path": self.declared, "resolved_path": self.resolved,
                "bytes": self.observed["bytes"], "sha256": self.observed["sha256"], "file": self.observed["stat"]}

    def close(self):
        if self.held is not None:
            self.held.close()
            self.held = None


class EvidenceStore:
    def __init__(self, reader):
        self.reader, self.fd, self.written = reader, None, []
        parent = reader.HeldPath(str(Path(OUTPUT).parent))
        try:
            parent.open()
            required(parent.fd is not None and stat.S_ISDIR(os.fstat(parent.fd).st_mode), "FIXED_OUTPUT_PARENT_REQUIRED")
            os.mkdir(Path(OUTPUT).name, 0o700, dir_fd=parent.fd)
            self.fd = os.open(Path(OUTPUT).name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent.fd)
            value = os.fstat(self.fd)
            required(value.st_uid == 0 and stat.S_IMODE(value.st_mode) == 0o700, "ROOT_PRIVATE_NEW_OUTPUT_REQUIRED")
            os.fsync(parent.fd)
        except BaseException:
            self.close()
            raise
        finally:
            parent.close()

    def write(self, name, raw):
        required(re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", name) and name not in (".", ".."), "SAFE_OUTPUT_NAME")
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                required(count > 0, "OUTPUT_WRITE_PROGRESS")
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        pin = {"path": OUTPUT + "/" + name, "bytes": len(raw), "sha256": sha(raw)}
        # read_regular intentionally rejects zero-sized candidate files. Empty
        # logs are read with a held direct fd instead of weakening that reader.
        check = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.fd)
        try:
            value = self.reader.metadata(check)
            required(stat.S_ISREG(value["st_mode"]) and value["st_uid"] == 0 and value["st_nlink"] == 1 and value["st_size"] == len(raw), "OUTPUT_READBACK_IDENTITY")
            body = bytearray()
            while len(body) < len(raw):
                part = os.read(check, min(65536, len(raw) - len(body)))
                required(bool(part), "OUTPUT_READBACK_PROGRESS")
                body.extend(part)
            required(bytes(body) == raw and self.reader.metadata(check) == value, "OUTPUT_READBACK_CHANGED")
        finally:
            os.close(check)
        self.written.append(pin)
        return pin

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def package_fields(raw):
    fields, key = {}, None
    for line in raw.decode("utf-8", "strict").splitlines():
        if line.startswith((" ", "\t")):
            required(key is not None, "DPKG_CONTINUATION_WITHOUT_FIELD")
            fields[key] += "\n" + line
        else:
            required(":" in line, "DPKG_FIELD_SYNTAX")
            key, value = line.split(":", 1)
            required(re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", key) and key not in fields, "DPKG_DUPLICATE_OR_INVALID_FIELD")
            fields[key] = value.lstrip(" ")
    return fields


def in_system_library_root(path):
    return any(path == root or path.startswith(root + "/") for root in SYSTEM_LIBRARY_ROOTS)


def search_paths(value, origin):
    if value is None:
        return []
    required(type(value) is str and len(value) <= 4096, "STATIC_SEARCH_PATH_BOUND")
    paths = []
    for entry in value.split(":"):
        required(bool(entry), "NO_CWD_LOADER_SEARCH_PATH")
        entry = entry.replace("${ORIGIN}", origin).replace("$ORIGIN", origin)
        required("$" not in entry and entry.startswith("/"), "UNSUPPORTED_LOADER_EXPANSION")
        resolved = str(Path(entry).resolve(strict=False))
        required(in_system_library_root(resolved), "SEARCH_PATH_OUTSIDE_REVIEWED_SYSTEM_LIBRARY_ROOTS")
        if resolved not in paths:
            paths.append(resolved)
    return paths


def resolve_dependency(name, dirs):
    required(type(name) is str and re.fullmatch(r"[A-Za-z0-9_+.-]{1,160}", name) and name not in (".", ".."), "BOUNDED_SONAME_REQUIRED")
    matches = {}
    for folder in dirs:
        path = Path(folder) / name
        try:
            resolved = str(path.resolve(strict=True))
        except FileNotFoundError:
            continue
        required(in_system_library_root(resolved), "DEPENDENCY_RESOLVED_OUTSIDE_SYSTEM_LIBRARY_ROOTS")
        matches.setdefault(resolved, str(path))
    required(len(matches) == 1, "STATIC_DEPENDENCY_ABSENT_OR_AMBIGUOUS")
    return next(iter(matches.values()))


def main():
    required(os.getuid() == os.geteuid() == 0, "EXISTING_AUTHORIZED_ROOT_HOST_READER_REQUIRED")
    os.umask(0o077)
    start_fds = len(os.listdir("/proc/self/fd"))
    end = time.monotonic() + 210
    files, store = [], None
    result = {"schema": "pocket4-existing-dpkg-aapt2-host-proof-and-interface-v1", "ok": False,
              "inventory_reference": INVENTORY_REFERENCE, "candidate": CANDIDATE,
              "Main_reads": 0, "Android_commands": 0, "native_commands": 0, "namespace_entries": 0,
              "action_lock_acquired": False, "APK_reads": 0, "APK_tool_inputs": 0,
              "App_launches": 0, "installs": 0, "UI_actions": 0, "permission_changes": 0,
              "existing_files_modified": False, "automatic_retry": False,
              "original_failed_audit_reclassified": False, "candidate_executions": 0,
              "process_FDs_before": start_fds, "commands": [], "errors": [],
              "official_distribution_signature_reverified": False,
              "static_dependency_observation_is_runtime_loader_proof": False}
    try:
        reader = frozen_module(READER_SOURCE, READER_SHA, "pinned_aapt2_host_reader")
        elf = frozen_module(ELF_SOURCE, ELF_SHA, "pinned_static_elf_reader")
        store = EvidenceStore(reader)
        def bind(path, limit=MAX_FILE, expected=None, resolve=False):
            required(time.monotonic() < end and len(files) < 64, "HOST_PROOF_TIME_OR_FILE_BOUND")
            item = BoundFile(reader, path, limit, expected, resolve)
            files.append(item)
            required(sum(row.observed["bytes"] for row in files) <= MAX_TOTAL, "HOST_PROOF_TOTAL_BYTES_BOUND")
            return item
        candidate = bind(CANDIDATE["path"], 262144, CANDIDATE)
        candidate_bytes = candidate.content(262144)
        candidate_md5 = hashlib.md5(candidate_bytes, usedforsecurity=False).hexdigest()
        status_file = bind("/var/lib/dpkg/status", 32 * 1024 * 1024)
        status = status_file.content(32 * 1024 * 1024)
        packages = []
        for block in status.split(b"\n\n"):
            if re.search(br"(?:^|\n)Package: aapt(?:\n|$)", block):
                fields = package_fields(block)
                if fields.get("Architecture") == "amd64" and fields.get("Status") == "install ok installed":
                    packages.append((fields, block))
        required(len(packages) == 1, "EXACT_INSTALLED_AMD64_AAPT_DPKG_RECORD_REQUIRED")
        fields, block = packages[0]
        result["installed_package"] = {key: fields[key] for key in ("Package", "Status", "Version", "Architecture", "Source", "Depends") if key in fields}
        result["installed_package"]["original_status_paragraph"] = store.write("aapt-installed-status.original.txt", block + b"\n")
        pairs = []
        for prefix in ("/var/lib/dpkg/info/aapt", "/var/lib/dpkg/info/aapt:amd64"):
            a, b = Path(prefix + ".list"), Path(prefix + ".md5sums")
            if a.exists() and b.exists():
                pairs.append((str(a), str(b)))
        required(len(pairs) == 1, "UNIQUE_INSTALLED_AAPT_DPKG_FILE_METADATA_REQUIRED")
        list_file, md5_file = (bind(path, 4 * 1024 * 1024) for path in pairs[0])
        listed = list_file.content(4 * 1024 * 1024).decode("utf-8", "strict").splitlines()
        required(listed.count(CANDIDATE["path"]) == 1, "AAPT2_NOT_EXACT_MEMBER_OF_INSTALLED_PACKAGE")
        matches = []
        for line in md5_file.content(4 * 1024 * 1024).decode("ascii", "strict").splitlines():
            match = re.fullmatch(r"([0-9a-f]{32}) [ *](.+)", line)
            required(match is not None, "DPKG_MD5_LINE_SYNTAX")
            if match[2] == CANDIDATE["path"].lstrip("/"):
                matches.append(match[1])
        required(matches == [candidate_md5], "INSTALLED_PACKAGE_AAPT2_MD5_MISMATCH")
        result["installed_dpkg_candidate_membership_and_checksum_match"] = True
        result["candidate_md5_from_actual_bytes"] = candidate_md5
        result["dpkg_metadata"] = [row.pin() for row in (status_file, list_file, md5_file)]
        static_rows, queue, seen, total = [], [candidate], {}, 0
        while queue:
            current = queue.pop(0)
            if current.resolved in seen:
                continue
            required(len(seen) < 48 and time.monotonic() < end, "STATIC_ELF_GRAPH_BOUND")
            data = elf.inspect_elf_fd(current.held.fd, current.observed["bytes"])
            required(data["additional_loader_directives"] == [], "ADDITIONAL_LOADER_DIRECTIVES_OUTSIDE_BOUND_SCOPE")
            seen[current.resolved] = data
            row = {"file": current.pin(), "static_elf": data, "resolved_needed": []}
            static_rows.append(row)
            origin = str(Path(current.resolved).parent)
            dirs = search_paths(data.get("rpath"), origin) + search_paths(data.get("runpath"), origin) + list(SEARCH_DIRS)
            for name in data["needed"]:
                declared = resolve_dependency(name, dirs)
                resolved = str(Path(declared).resolve(strict=True))
                row["resolved_needed"].append({"soname": name, "declared_path": declared, "resolved_path": resolved})
                if resolved not in seen and not any(x.resolved == resolved for x in queue):
                    queue.append(bind(declared, resolve=True))
            interpreter = data.get("interpreter")
            if interpreter is not None:
                required(interpreter.startswith("/"), "ABSOLUTE_ELF_INTERPRETER_REQUIRED")
                resolved = str(Path(interpreter).resolve(strict=True))
                required(in_system_library_root(resolved), "ELF_INTERPRETER_OUTSIDE_SYSTEM_LIBRARY_ROOTS")
                row["resolved_interpreter"] = {"declared_path": interpreter, "resolved_path": resolved}
                if resolved not in seen and not any(x.resolved == resolved for x in queue):
                    queue.append(bind(interpreter, resolve=True))
        result["static_dependency_graph"] = static_rows
        result["static_dependency_file_count"] = len(static_rows)
        result["static_graph_limitations"] = "Closed-system-path static dependency observations, not proof of the dynamic loader's selected mappings or official release provenance."
        collector_file = bind(COLLECTOR["path"], 65536, COLLECTOR)
        tool_source = collector_file.content(65536)
        runner = frozen_module(tool_source.decode("utf-8"), COLLECTOR["sha256"], "pinned_original_bounded_host_runner")
        result["bounded_runner_source"] = collector_file.pin()
        for name, tail in (("version", ["version"]), ("dump-badging-help", ["dump", "badging", "--help"])):
            for item in files:
                required(time.monotonic() < end, "HOST_TOTAL_DEADLINE_BEFORE_FILE_RECHECK")
                item.recheck()
            command = {"name": name, "APK_input": False}
            result["commands"].append(command)
            required(time.monotonic() + 5 < end, "HOST_TOTAL_DEADLINE_BEFORE_CANDIDATE_SPAWN")
            outputs = runner.run_tool([CANDIDATE["path"], *tail], (candidate.held.fd,), command, end)
            result["candidate_executions"] += int(command.get("spawned") is True)
            for stream, raw in outputs.items():
                command[stream] = store.write(name + "." + stream, raw)
                if len(raw) <= 32768:
                    command[stream + "_original_hex"] = raw.hex()
            required(command.get("joined") is True and command.get("pipes_closed") is True, "OWNED_TOOL_CHILD_RETIREMENT_NOT_PROVED")
            for item in files:
                required(time.monotonic() < end, "HOST_TOTAL_DEADLINE_BEFORE_FILE_RECHECK")
                item.recheck()
        result["all_bound_host_files_unchanged"] = True
        result["all_interface_commands_succeeded"] = len(result["commands"]) == 2 and all(
            command.get("returncode") == 0 and command.get("output_capture_complete") is True and not command.get("timed_out") and not command.get("error")
            for command in result["commands"])
        result["ok"] = result["all_interface_commands_succeeded"]
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:240]})
    finally:
        for item in reversed(files):
            try:
                item.close()
            except BaseException as error:
                result["errors"].append({"stage": "host_file_close", "type": type(error).__name__})
        if result["errors"]:
            result["ok"] = False
        result["all_owned_tool_children_joined"] = all(row.get("joined") is True and row.get("pipes_closed") is True for row in result["commands"])
        result["status"] = ("EXISTING_DPKG_TOOL_AND_INTERFACE_OBSERVED" if result["ok"] else
                            "HOST_PROOF_OR_INTERFACE_INCOMPLETE_NO_RETRY")
        try:
            if store is not None:
                result["new_evidence_files"] = list(store.written)
                raw = canonical(result) + b"\n"
                required(len(raw) <= MAX_RESULT, "RESULT_BOUND")
                result["final_receipt"] = store.write("result.json", raw)
        except BaseException as error:
            result["errors"].append({"stage": "final_receipt", "type": type(error).__name__, "reason": str(error)[:160]})
            result["ok"] = False
        finally:
            if store is not None:
                try:
                    store.close()
                except BaseException as error:
                    result["errors"].append({"stage": "evidence_directory_close", "type": type(error).__name__})
                    result["ok"] = False
        result["process_FDs_after"] = len(os.listdir("/proc/self/fd"))
        if result["process_FDs_after"] != start_fds:
            result["errors"].append({"reason": "HOST_PROCESS_DESCRIPTOR_DIFFERENCE"})
            result["ok"] = False
        if not result["ok"]:
            result["status"] = "HOST_PROOF_OR_INTERFACE_INCOMPLETE_NO_RETRY"
    raw = canonical(result)
    required(len(raw) <= MAX_RESULT, "STDOUT_ARTIFACT_BOUND")
    print(json.dumps({"encoding": "zlib-base64", "artifact_bytes": len(raw), "artifact_sha256": sha(raw),
                      "data": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}, separators=(",", ":")), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
