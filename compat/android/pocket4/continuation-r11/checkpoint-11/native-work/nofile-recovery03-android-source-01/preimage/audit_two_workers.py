#!/usr/bin/env python3
"""Audit the fixed raw worker's final ELF call closure; never execute the ELF."""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("elf")
    parser.add_argument("--objdump", default="objdump")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    elf = pathlib.Path(args.elf)
    output = pathlib.Path(args.output)
    text = subprocess.check_output(
        [args.objdump, "-d", "--demangle", "--no-show-raw-insn", str(elf)], text=True
    )
    functions = {}
    current = None
    for line in text.splitlines():
        match = re.match(r"^\s*([0-9a-f]+) <(.+)>:$", line)
        if match:
            current = int(match[1], 16)
            functions[current] = {"name": match[2], "lines": []}
        elif current is not None:
            functions[current]["lines"].append(line)
    workers = [address for address, body in functions.items()
               if body["name"].endswith(("::Worker(void*)", "::InheritedWorker(void*)")) and
               "berberis::proc_maps_provenance::raw_metadata_owner::" in body["name"]]
    trampolines = [address for address, body in functions.items()
                   if body["name"] == "berberis_proc_metadata_raw_clone_x86_64"]
    errors = []
    suffixes = ("::Worker(void*)", "::InheritedWorker(void*)")
    if len(workers) != 2 or any(sum(functions[x]["name"].endswith(suffix) for x in workers) != 1 for suffix in suffixes):
        errors.append("Exactly one persistent Worker and one InheritedWorker are required; missing symbols fail.")
    if len(trampolines) != 1:
        errors.append("Exactly one own clone trampoline is required.")
    addresses = sorted(functions)
    bounds = {address: addresses[i + 1] if i + 1 < len(addresses) else 2**64
              for i, address in enumerate(addresses)}
    visited = set()
    pending = list(workers)
    calls = []
    forbidden_tokens = ("%fs:", "%gs:", "fs:[", "gs:[", "@plt", "__tls_get_addr",
                        "__stack_chk", "__atomic_", "__cxa_", "__asan_", "__tsan_", "__ubsan_")
    while pending:
        address = pending.pop()
        if address in visited:
            continue
        visited.add(address)
        body = functions[address]
        if not body["name"].startswith("berberis::proc_maps_provenance::raw_metadata_owner::"):
            errors.append("Worker reaches a non-owner function: " + body["name"])
        for line in body["lines"]:
            lower = line.lower()
            if any(token in lower for token in forbidden_tokens):
                errors.append("Forbidden TLS/runtime edge: " + line.strip())
            instruction = re.match(r"\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)", line)
            if not instruction:
                continue
            operation, operand = instruction[2], instruction[3]
            if not (operation.startswith("call") or operation.startswith("j")):
                continue
            target = re.match(r"(?:0x)?([0-9a-f]+)\s+<", operand)
            if not target:
                errors.append("Unresolved/indirect worker control transfer: " + line.strip())
                continue
            destination = int(target[1], 16)
            if address <= destination < bounds[address]:
                continue
            if destination not in functions:
                errors.append("Unresolved direct worker target: " + line.strip())
                continue
            calls.append({"from": body["name"], "to": functions[destination]["name"]})
            pending.append(destination)
    trampoline_info = None
    if len(trampolines) == 1:
        body = functions[trampolines[0]]
        instructions = []
        for line in body["lines"]:
            match = re.match(r"\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)", line)
            if match:
                instructions.append((match[2], match[3]))
            if any(token in line.lower() for token in forbidden_tokens):
                errors.append("Forbidden trampoline TLS/runtime edge: " + line.strip())
        indirect = [operand for operation, operand in instructions if operation.startswith("call")]
        if len(indirect) != 1 or not re.fullmatch(r"\*(?:0x0)?\(%rsp\)", indirect[0].strip()):
            errors.append("Trampoline must call exactly the stack-stored fixed entry once.")
        syscall_count = sum(operation == "syscall" for operation, _ in instructions)
        if syscall_count != 2:
            errors.append("Trampoline must contain only the clone and fallback exit syscall sites.")
        trampoline_info = {"name": body["name"], "syscall_sites": syscall_count,
                           "indirect_fixed_entry_calls": indirect,
                           "source_binding_required": "Start passes Worker/null; ReadInheritedAfterAllocationFailure passes only InheritedWorker/its retained Request. Review both actual clone call sites."}
    report = {
        "schema": 1,
        "elf": str(elf),
        "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
        "objdump": args.objdump,
        "qualified_worker_closure": not errors,
        "worker_symbols": [functions[x]["name"] for x in workers],
        "reachable_functions": [functions[x]["name"] for x in sorted(visited)],
        "edges": calls,
        "clone_trampoline": trampoline_info,
        "errors": errors,
        "limits": [
            "This verifies the named final binary closure, not runtime credential or signal policy.",
            "The inherited TLS pointer exists but the audited child closure must not dereference it.",
            "No Bionic pthread registration is created. Credential transitions and host cancellation remain unqualified.",
            "A host ELF result cannot substitute for auditing the actual Android ELF."
        ],
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    output.with_suffix(".disassembly.txt").write_text(text)
    print(json.dumps(report))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
