#!/usr/bin/env python3
"""Bind Ninja v5 log rows to evaluated commands from the actual pinned binary.

The hash implementation follows upstream Ninja v1.9.0 build_log.cc
SHA256 389bd82e8634be3d01e44b7292f97850e4cca47f2425f4292b9c2ce7a734fefd.
Its applicability to Pocket4's Android Ninja fork must additionally be proven
by the actual binary controls. It is not a claim that upstream source is the
unavailable exact prebuilt source revision.
"""
import re

MASK64 = (1 << 64) - 1
MURMUR_MULTIPLIER = 0xC6A4A7935BD1E995
MURMUR_SEED = 0xDECAFBADDECAFBAD


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def command_hash(command, rspfile_content=b""):
    require(type(command) is bytes and type(rspfile_content) is bytes,
            "exact command and response-file bytes required")
    require(b"\0" not in command and b"\0" not in rspfile_content,
            "NUL is not a command byte")
    data = command
    if rspfile_content:
        data += b";rspfile=" + rspfile_content
    h = MURMUR_SEED ^ ((len(data) * MURMUR_MULTIPLIER) & MASK64)
    end = len(data) - len(data) % 8
    for offset in range(0, end, 8):
        value = int.from_bytes(data[offset:offset + 8], "little")
        value = (value * MURMUR_MULTIPLIER) & MASK64
        value ^= value >> 47
        value = (value * MURMUR_MULTIPLIER) & MASK64
        h ^= value
        h = (h * MURMUR_MULTIPLIER) & MASK64
    tail = data[end:]
    if tail:
        h ^= int.from_bytes(tail, "little")
        h = (h * MURMUR_MULTIPLIER) & MASK64
    h ^= h >> 47
    h = (h * MURMUR_MULTIPLIER) & MASK64
    h ^= h >> 47
    return h


def parse_log(raw):
    require(type(raw) is bytes and len(raw) <= 256 * 1024 * 1024,
            "bounded exact Ninja log bytes required")
    require(raw.endswith(b"\n"), "incomplete Ninja log tail")
    lines = raw.splitlines()
    require(lines and lines[0] == b"# ninja log v5",
            "only the observed Ninja v5 log format is supported")
    entries = {}
    for index, line in enumerate(lines[1:], 2):
        fields = line.split(b"\t")
        require(len(fields) == 5, "invalid Ninja log columns at " + str(index))
        require(all(re.fullmatch(rb"[0-9]+", x) for x in fields[:3]),
                "invalid Ninja log time at " + str(index))
        start_ms, end_ms, mtime = map(int, fields[:3])
        require(end_ms >= start_ms, "reversed Ninja command time")
        require(fields[3] and b"\0" not in fields[3],
                "invalid Ninja output path")
        require(re.fullmatch(rb"[0-9a-fA-F]{1,16}", fields[4]),
                "invalid Ninja command hash")
        output = fields[3].decode("utf-8", "strict")
        row = {"line": index, "output": output, "start_ms": start_ms,
               "end_ms": end_ms, "mtime": mtime,
               "command_hash": int(fields[4], 16),
               "command_hash_hex": fields[4].decode().lower()}
        entries[output] = row
    return entries


def bind_log_entry(raw, output, evaluated_command, rspfile_content=b""):
    entries = parse_log(raw)
    require(output in entries, "output lacks a successful Ninja log row")
    row = entries[output]
    observed = command_hash(evaluated_command, rspfile_content)
    require(observed == row["command_hash"],
            "Ninja log command hash does not match the evaluated command")
    return {**row, "evaluated_command_hash_hex": format(observed, "x"),
            "response_file_content_included": bool(rspfile_content),
            "command_bytes": len(evaluated_command),
            "response_file_bytes": len(rspfile_content)}


