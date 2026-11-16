#!/usr/bin/env python3
"""Validate original Ninja dependency edges and exact Audio compile arguments.

These functions qualify evidence from a successful build. They do not execute
commands or infer that a declared Ninja command actually ran. The caller must
also bind every non-phony edge to the actual successful Ninja log and artifacts.
"""
import os
from pathlib import Path
import re
import shlex
import struct


def need(value, message):
    if not value:
        raise RuntimeError(message)


def query_record(target, output):
    need(type(output) is str and output.endswith("\n"), "complete Ninja query required")
    lines = output.splitlines()
    need(lines and lines[0] == target + ":", "Ninja query target mismatch")
    need(len(lines) >= 3 and lines[1].startswith("  input: "), "produced Ninja target required")
    rule = lines[1][len("  input: "):]
    need(rule and not any(x.isspace() for x in rule), "unambiguous Ninja rule required")
    dependencies = []
    in_outputs = False
    for line in lines[2:]:
        if line == "  outputs:":
            need(not in_outputs, "duplicate Ninja outputs section")
            in_outputs = True
            continue
        need(line.startswith("    "), "unexpected Ninja query line")
        if in_outputs:
            continue
        value = line[4:]
        kind = "explicit"
        if value.startswith("|| "):
            kind, value = "order_only", value[3:]
        elif value.startswith("| "):
            kind, value = "implicit", value[2:]
        need(value and "\0" not in value, "empty Ninja dependency")
        dependencies.append({"path": value, "kind": kind})
    need(in_outputs, "Ninja query missing outputs section")
    need(len({x["path"] for x in dependencies}) == len(dependencies),
         "duplicate dependency is ambiguous")
    return {"target": target, "rule": rule, "dependencies": dependencies}


def dependency_edge(record, child):
    found = [x for x in record["dependencies"] if x["path"] == child]
    need(len(found) == 1, "selected dependency edge absent or ambiguous")
    need(found[0]["kind"] != "order_only", "order-only edges do not prove object linkage")
    return {"parent": record["target"], "child": child, "kind": found[0]["kind"],
            "rule": record["rule"]}


def dependency_path(target, source, output):
    need(type(output) is str and output.endswith("\n"), "complete Ninja path required")
    path = output.splitlines()
    need(3 <= len(path) <= 128 and path[0] == target and path[-1] == source,
         "Ninja path must connect the exact ELF target and source")
    need(all(path) and len(set(path)) == len(path), "empty or cyclic Ninja dependency path")
    need(path[-2].endswith(".o"), "source must have an immediate compiled object parent")
    return path


def words(command):
    need(type(command) is str and command and "\0" not in command, "exact nonempty command required")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def response_paths(command):
    paths = [x[1:] for x in words(command) if x.startswith("@")]
    need(all(paths) and len(paths) <= 1, "at most one unambiguous Ninja response file is supported")
    return paths


def canonical(path, cwd):
    p = Path(path)
    need("\0" not in str(p), "invalid path")
    return os.path.normpath(str(p if p.is_absolute() else Path(cwd) / p))


def option_values(argv, option, joined=False):
    result = []
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == option:
            need(index + 1 < len(argv), "option lacks its value: " + option)
            result.append(argv[index + 1])
            index += 2
            continue
        if joined and value.startswith(option) and len(value) > len(option):
            result.append(value[len(option):])
        index += 1
    return result


def compile_input(argv):
    """Parse the positional TU, treating -c as a mode switch, as Clang does.

    Split-value options are the normal Clang/Soong forms. Unknown options with
    an additional positional value fail closed instead of silently consuming a
    possible second translation unit. Joined flags remain single arguments.
    """
    valued = {"-o", "-target", "--target", "-x", "-I", "-F", "-D", "-U", "-B",
              "-isystem", "-iquote", "-idirafter", "-iframework", "-isysroot", "--sysroot",
              "-include", "-imacros", "-include-pch", "-iprefix", "-iwithprefix",
              "-iwithprefixbefore", "-MF", "-MT", "-MQ", "-MJ", "-Xclang", "-Xassembler",
              "-Xpreprocessor", "-Xlinker", "-mllvm", "-resource-dir", "-gcc-toolchain",
              "--gcc-toolchain", "-ivfsoverlay", "-fmodule-map-file", "-fmodule-file",
              "-fmodules-cache-path", "-fprofile-use", "-fprofile-sample-use"}
    positional, mode_count = [], 0
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            positional.extend(argv[index + 1:])
            break
        if token in valued:
            need(index + 1 < len(argv), "Clang option lacks its value: " + token)
            index += 2
            continue
        if token == "-c":
            mode_count += 1
        elif token.startswith("-"):
            pass
        else:
            positional.append(token)
        index += 1
    need(mode_count == 1 and len(positional) == 1, "one compile mode and one positional translation unit required")
    return positional[0]


def compile_command(command, response_content, source, output, required_macro, cwd):
    """Return the exact matching Clang invocation; reject wrong/masked flags."""
    need(not any(x in command for x in ("\n", "\r", "`", "$(")),
         "multiline or command-substitution shell grammar is not qualified")
    tokens = words(command)
    paths = response_paths(command)
    need(type(response_content) is bytes, "response content must be exact bytes")
    need(bool(paths) or not response_content, "response bytes without a response-file invocation")
    if paths:
        expansion = shlex.split(response_content.decode("utf-8", "strict"), comments=False, posix=True)
        need(not any(x.startswith("@") for x in expansion), "nested response files require separate evidence")
        expanded = []
        for token in tokens:
            expanded.extend(expansion if token == "@" + paths[0] else [token])
        tokens = expanded
    segments = [[]]
    for token in tokens:
        if token and all(x in ";&|()" for x in token):
            need(token == "&&" and segments[-1],
                 "only an unconditional successful && command chain is qualified")
            segments.append([])
        else:
            segments[-1].append(token)
    need(segments[-1], "incomplete successful command chain")
    invocations = []
    for segment_index, segment in enumerate(segments):
        for index, token in enumerate(segment):
            if re.fullmatch(r"clang(?:\+\+)?(?:-[0-9.]+)?", Path(token).name) is None:
                continue
            need(segment_index == 0, "the original Soong Clang must be the first command in its success chain")
            prefix = segment[:index]
            if prefix and prefix[0] in ("env", "/usr/bin/env"):
                prefix = prefix[1:]
            need(not prefix or len(prefix) == 1 and prefix[0].startswith("PWD="),
                 "only the original Soong PWD assignment may precede Clang")
            argv = segment[index + 1:]
            input_path = compile_input(argv)
            outputs = option_values(argv, "-o")
            if len(outputs) != 1:
                continue
            if canonical(input_path, cwd) != canonical(source, cwd) or canonical(outputs[0], cwd) != canonical(output, cwd):
                continue
            triples = option_values(argv, "-target") + option_values(argv, "--target")
            triples += [x.split("=", 1)[1] for x in argv if x.startswith("--target=")]
            need(len(triples) == 1 and re.fullmatch(r"x86_64(?:-none)?-linux-android[0-9]*", triples[0]),
                 "exact x86_64 Android compile target required")
            definitions = option_values(argv, "-D", joined=True)
            undefinitions = option_values(argv, "-U", joined=True)
            selected = [x.partition("=")[2] if "=" in x else "1" for x in definitions
                        if x.partition("=")[0] == required_macro]
            if required_macro is not None:
                need(type(required_macro) is str and required_macro, "explicit feature macro name required")
                need(selected and all(x == "1" for x in selected), "required feature macro must be explicitly enabled")
                need(required_macro not in undefinitions, "required feature macro was undefined")
            need(not any(x in ("-E", "-S", "-fsyntax-only") for x in argv), "actual object compilation required")
            for after in segments[1:]:
                need(len(after) == 2 and after[0] in ("touch", "/usr/bin/touch")
                     and canonical(after[1], cwd) == canonical(output, cwd),
                     "unverified post-command can replace or mask the compiled object")
            invocations.append({"compiler": canonical(token, cwd), "source": canonical(source, cwd),
                                "output": canonical(output, cwd), "target_triple": triples[0],
                                "macro": required_macro, "macro_value": 1 if required_macro is not None else None,
                                "response_file": paths[0] if paths else None,
                                "argument_count": len(argv)})
    need(len(invocations) == 1, "exactly one matching actual Clang compilation is required")
    return invocations[0]


def elf_header(raw, kind):
    need(type(raw) is bytes and len(raw) >= 64, "complete ELF64 header required")
    need(raw[:7] == b"\x7fELF\x02\x01\x01", "ELF64 little-endian executable format required")
    e_type, machine, version = struct.unpack_from("<HHI", raw, 16)
    expected = {"object": 1, "shared": 3}[kind]
    need(e_type == expected and machine == 62 and version == 1,
         "wrong ELF type or non-x86_64 artifact")
    return {"class": "ELF64", "endianness": "little", "machine": "x86_64", "type": kind}


def compiled_object_header(raw):
    if raw.startswith(b"\x7fELF"):
        return elf_header(raw, "object")
    need(len(raw) >= 16 and raw[:4] in (b"BC\xc0\xde", b"\xde\xc0\x17\x0b"),
         "compiled object is neither x86_64 ELF nor LLVM bitcode")
    return {"type": "LLVM_bitcode", "architecture_evidence": "actual_Clang_target_and_final_ELF"}


def header_dependencies(target, raw, object_mtime_ns):
    """Read the actual valid Ninja deps entry, including its object generation."""
    need(type(raw) is str and raw.endswith("\n"), "complete Ninja dependency output required")
    lines = raw.splitlines()
    need(lines, "missing actual Ninja header dependencies")
    pattern = re.escape(target) + r": #deps ([0-9]+), deps mtime ([0-9]+) \(VALID\)"
    match = re.fullmatch(pattern, lines[0])
    need(match is not None, "actual Ninja deps are stale or belong to another object")
    need(type(object_mtime_ns) is int and int(match[2]) == object_mtime_ns,
         "header dependencies belong to another object generation")
    names = []
    for line in lines[1:]:
        if not line:
            continue
        need(line.startswith("    ") and line[4:] and "\0" not in line,
             "unexpected Ninja dependency line")
        names.append(line[4:])
    need(len(names) == int(match[1]) and len(set(names)) == len(names),
         "incomplete or ambiguous actual header dependency set")
    return names
