"""Read actual ELF64 DT_NEEDED transitively; never execute ldd or an output ELF.

This preserves a complete static file closure. External libraries/interpreter
require explicit exact file pins supplied by a later reviewed host binding.
This module does not invent loader-cache resolution or qualify tool execution.
"""
import importlib.util
import os
from pathlib import Path
import re
import struct

_descriptor = importlib.util.spec_from_file_location('p4_elf_checks', Path(__file__).with_name('carrier_checks.py'))
c = importlib.util.module_from_spec(_descriptor); _descriptor.loader.exec_module(c)
need = c.need

# These tags cause the loader to select objects outside DT_NEEDED. Until their
# ordering and lookup rules have a reviewed resolver, a NEEDED-only traversal
# must reject them rather than report a complete preserved dependency closure.
# Numeric values are the ELF ABI constants, also exposed by <elf.h>.
UNSUPPORTED_LOAD_TAGS = {
    0x6ffffefb: 'DT_DEPAUDIT',
    0x6ffffefc: 'DT_AUDIT',
    0x7ffffffd: 'DT_AUXILIARY',
    0x7fffffff: 'DT_FILTER',
}


def parse_elf(raw):
    need(len(raw) >= 64 and raw[:7] == b'\x7fELF\x02\x01\x01', 'ELF64 little-endian version 1 required')
    header = struct.unpack_from('<HHIQQQIHHHHHH', raw, 16)
    kind, machine, version, _, phoff, _, _, ehsize, phentsize, phnum, _, _, _ = header
    need(kind in (2, 3) and machine == 62 and version == 1 and ehsize == 64 and phentsize == 56 and 0 < phnum <= 256, 'normal x86_64 ELF program headers required')
    need(phoff >= 64 and phoff + phnum * phentsize <= len(raw), 'ELF program headers outside file')
    loads = []; dynamic = None; interpreter = None
    for i in range(phnum):
        tag, _, offset, address, _, size, memsize, _ = struct.unpack_from('<IIQQQQQQ', raw, phoff + i * phentsize)
        need(offset <= len(raw) and size <= len(raw) - offset and size <= memsize, 'ELF segment outside file')
        need(address <= 2**64 - memsize, 'ELF virtual segment range overflows its address space')
        if tag == 1:
            loads.append((address, size, offset, memsize))
        elif tag == 2:
            need(dynamic is None and size % 16 == 0 and 0 < size <= 1024 * 1024, 'ambiguous or invalid dynamic segment')
            dynamic = (offset, size, address)
        elif tag == 3:
            need(interpreter is None and 1 < size <= 4096, 'ambiguous or invalid ELF interpreter')
            text = raw[offset:offset + size]
            need(text.endswith(b'\0') and b'\0' not in text[:-1], 'invalid ELF interpreter string')
            interpreter = text[:-1].decode('utf-8', 'strict')
            need(interpreter.startswith('/') and '..' not in Path(interpreter).parts, 'nonabsolute ELF interpreter')
    need(dynamic is not None, 'actual dynamically linked ELF required')
    def mapped_offset(address, size, label):
        need(0 < size <= 2**64 - address, label + ' virtual range overflows its address space')
        # Include partially overlapping and zero-fill LOAD memory, not just a
        # LOAD that happens to contain the start or the whole file-backed range.
        overlaps = [row for row in loads if row[3] and address < row[0] + row[3] and row[0] < address + size]
        need(len(overlaps) == 1, label + ' has ambiguous or absent PT_LOAD mapping')
        base, file_size, offset, _ = overlaps[0]
        need(base <= address and address - base <= file_size and size <= file_size - (address - base),
             label + ' is not completely file-backed by its PT_LOAD')
        return offset + address - base
    need(mapped_offset(dynamic[2], dynamic[1], 'ELF dynamic segment') == dynamic[0],
         'ELF dynamic segment file offset differs from PT_LOAD mapping')
    tags = {}; needed = []; ended = False
    for at in range(dynamic[0], dynamic[0] + dynamic[1], 16):
        tag, value = struct.unpack_from('<qQ', raw, at)
        if tag == 0:
            ended = True; break
        need(tag not in UNSUPPORTED_LOAD_TAGS,
             'unsupported ELF load directive ' + UNSUPPORTED_LOAD_TAGS.get(tag, '') +
             ' requires a separately reviewed dependency resolver')
        if tag == 1:
            needed.append(value)
        elif tag in (5, 10, 14, 15, 29):
            need(tag not in tags, 'duplicate ELF singleton dynamic tag')
            tags[tag] = value
    need(ended and 5 in tags and 10 in tags and 0 < tags[10] <= 32 * 1024**2, 'complete ELF dynamic string table required')
    string_offset = mapped_offset(tags[5], tags[10], 'ELF string table')
    strings = raw[string_offset:string_offset + tags[10]]
    def string(offset):
        need(offset < len(strings), 'ELF string index outside table')
        end = strings.find(b'\0', offset)
        need(end >= offset, 'unterminated ELF dynamic string')
        return strings[offset:end].decode('utf-8', 'strict')
    names = [string(value) for value in needed]
    need(len(set(names)) == len(names) and all(name and '/' not in name and '\x00' not in name for name in names), 'duplicate or path-bearing DT_NEEDED')
    soname = string(tags[14]) if 14 in tags else None
    if soname is not None:
        need(soname and '/' not in soname, 'invalid ELF SONAME')
    runpath = string(tags[29]) if 29 in tags else None
    rpath = string(tags[15]) if 15 in tags else None
    need(rpath is None or runpath is not None, 'legacy inherited DT_RPATH requires a separately reviewed loader resolver')
    return {'needed': names, 'soname': soname, 'runpath': runpath, 'rpath_ignored_by_runpath': rpath,
            'interpreter': interpreter, 'machine': machine, 'elf_type': kind}


def _read(path):
    reference, raw = c.read_file(path, 256 * 1024**2, True)
    return reference, parse_elf(raw)


def _runpath_paths(value, origin, output_root):
    if value is None:
        return []
    paths = []
    for part in value.split(':'):
        need(part, 'empty RUNPATH would search the working directory')
        part = re.sub(r'(?:\$\{ORIGIN\}|\$ORIGIN)(?=/|$)', lambda _: str(origin), part)
        need('$' not in part and Path(part).is_absolute(), 'unresolved or relative dynamic loader search directory')
        path = Path(os.path.normpath(part))
        need(path == output_root or path.is_relative_to(output_root), 'output RUNPATH escaped the preserved output root')
        if path.exists():
            c.parents(path / 'placeholder')
        paths.append(path)
    return paths


def _owned_alias(path, root, links):
    for _ in range(16):
        c.parents(path)
        before = path.lstat()
        if not path.is_symlink():
            return path
        target = os.readlink(path)
        row = {'path': str(path), 'identity': c.f9(before), 'target': target}
        need(str(path) not in links or links[str(path)] == row, 'library alias differs from its first dependency snapshot')
        links[str(path)] = row
        need(c.f9(path.lstat()) == c.f9(before), 'library alias changed during read')
        resolved = Path(target) if Path(target).is_absolute() else path.parent / target
        path = Path(os.path.normpath(resolved))
        need(path.is_relative_to(root), 'library alias escaped owned output')
    raise RuntimeError('cyclic or excessive library alias chain')


def capture(root_reference, output_root, external_inputs=(), interpreter_reference=None):
    """Capture static dependencies, retaining explicit unresolved-host boundaries.

    external_inputs is a finite, reviewed list of full F9/SHA references whose
    SONAMEs are unique. It is not a search path, an allowlist to skip a missing
    dependency, or a statement of what the dynamic loader actually selected.
    """
    output_root = Path(output_root)
    root = Path(root_reference['path'])
    need(root == output_root / 'host/linux-x86/bin/secilc', 'exact normal Soong secilc output required')
    root_pin = c.exact_file(root_reference, root)
    snapshots = {}
    def snapshot(path, expected=None):
        key = str(path)
        if key not in snapshots:
            need(len(snapshots) < 128, 'finite dependency graph bound exceeded')
            snapshots[key] = _read(path)
        ref, meta = snapshots[key]
        need(expected is None or ref == expected, 'ELF file differs from its pinned dependency snapshot: ' + key)
        return ref, meta
    snapshot(root, root_pin)
    external = {}
    for row in external_inputs:
        ref = c.exact_file(row, row['path'], identity=True)
        _, meta = snapshot(Path(ref['path']), ref)
        name = meta['soname']
        need(name and name not in external, 'explicit external library SONAME missing or ambiguous')
        external[name] = ref
    pending = [root]; files = {}; metadata = {}; edges = []; links = {}; interpreted = None
    while pending:
        path = pending.pop()
        if str(path) in files:
            continue
        need(len(files) < 128, 'finite dependency graph bound exceeded')
        # Every edge and queue visit consumes the exact first-read bytes and
        # metadata. A later inode cannot replace a previously checked SONAME.
        ref, meta = snapshot(path); files[str(path)] = ref; metadata[str(path)] = meta
        if path == root and meta['interpreter'] is not None:
            need(interpreter_reference is not None and interpreter_reference.get('loader_path') == meta['interpreter'], 'actual ELF interpreter lacks an explicit current host binding')
            bound = interpreter_reference['reference']
            interpreted = c.exact_file(bound, bound['path'], identity=True)
            snapshot(Path(bound['path']), interpreted)
            # The loader's actual file is preserved. A loader_path alias remains
            # an explicit external host binding, not a silently followed path.
            pending.append(Path(bound['path']))
        dirs = _runpath_paths(meta['runpath'], path.parent, output_root) if path.is_relative_to(output_root) else []
        if not path.is_relative_to(output_root):
            need(meta['runpath'] is None and meta['rpath_ignored_by_runpath'] is None, 'external loader search semantics require separate review')
        for name in meta['needed']:
            selected = None; search = []
            for directory in dirs:
                candidate = directory / name
                search.append(str(candidate))
                if os.path.lexists(candidate):
                    selected = _owned_alias(candidate, output_root, links)
                    break
            origin = 'actual_output_RUNPATH'
            if selected is None:
                need(name in external, 'unresolved actual DT_NEEDED (explicit host binding required): ' + name)
                selected = Path(external[name]['path']); origin = 'explicit_external_static_binding'
            _, selected_meta = snapshot(selected)
            need(selected_meta['soname'] in (None, name), 'selected library SONAME differs from DT_NEEDED')
            edges.append({'from': str(path), 'DT_NEEDED': name, 'to': str(selected), 'resolution': origin, 'searched_output_paths': search})
            if str(selected) not in files:
                pending.append(selected)
    for row, _ in snapshots.values():
        c.exact_file(row, row['path'], identity=True)
    for row in links.values():
        path = Path(row['path'])
        need(c.f9(path.lstat()) == row['identity'] and os.readlink(path) == row['target'], 'preserved library alias changed')
    c.exact_file(root_pin, root, identity=True)
    return {'schema': 'p4-normal-secilc-static-elf-closure-v1', 'root': files[str(root)],
            'files': files, 'dynamic_metadata': metadata, 'dependencies': edges, 'aliases': links,
            'interpreter': interpreted, 'static_dependency_closure_complete': True,
            'loader_resolution_qualified': False, 'tool_execution_qualified': False,
            'selected_CP3A_policy_qualified': False, 'runtime_qualified': False, 'production_ready': False}
