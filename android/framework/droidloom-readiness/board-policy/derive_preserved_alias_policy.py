"""Pure preservation of concrete access to fixed narrower object aliases.

This library grants nothing to isolated new roles. Each consumer retains its
own source contract, entry transitions and complete binary role verifier.
"""
import hashlib
import re
from collections import defaultdict

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_shared_payload_cgroup_policy import parse_expression, original_xperms

def _classes(text):
    common = dict((n, body.split()) for n, body in
                  re.findall(r"\(common (\w+) \(([^()]*)\)\)", text))
    result = dict((n, body.split()) for n, body in
                  re.findall(r"\(class (\w+) \(([^()]*)\)\)", text))
    for name, parent in re.findall(r"\(classcommon (\w+) (\w+)\)", text):
        result[name] = common[parent] + result[name]
    return result

def _roles(lines):
    return sorted({(role, line[len("(roletype " + role + " "):-1])
                   for role in ("r", "system_r") for line in lines
                   if line.startswith("(roletype " + role + " ")})

def _context(role, actor, level="s0"):
    return "u:" + role + ":" + actor + ":" + level

def _validate_inputs(lines, classes, aliases, prefix, isolated_roles, extra_permissions, preamble):
    """Reject ignored declarations before reading or emitting any access vectors."""
    identifier = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    if not isinstance(prefix, str) or not identifier.fullmatch(prefix):
        raise ValueError("A fixed CIL attribute prefix is required")
    if any(line.startswith("(typeattribute " + prefix + "_") for line in lines):
        raise ValueError("Alias attribute prefix already exists in the baseline")
    all_actors = _roles(lines)
    actor_names = {actor for _, actor in all_actors}
    isolated = set(isolated_roles)
    if not isolated.issubset(actor_names) or isolated == actor_names:
        raise ValueError("Isolated roles must be explicit defined concrete actors")
    objects = {line[len("(roletype object_r "):-1] for line in lines
               if line.startswith("(roletype object_r ")}
    if not isinstance(aliases, list) or not 1 <= len(aliases) <= 64:
        raise ValueError("A bounded explicit alias list is required")
    selected = set()
    for row in aliases:
        if not isinstance(row, dict) or set(row) != {"source", "target", "class"}:
            raise ValueError("Alias declarations require source, target and class only")
        old, new, cls = row["source"], row["target"], row["class"]
        if (not all(isinstance(value, str) and identifier.fullmatch(value)
                    for value in (old, new, cls)) or old == new or
                old not in objects or new not in objects or cls not in classes or
                (new, cls) in selected):
            raise ValueError("Repeated, unknown or self-referencing object alias")
        selected.add((new, cls))
    if {row["source"] for row in aliases} & {row["target"] for row in aliases}:
        raise ValueError("Aliases must derive directly from original object types")
    extras = {}
    if not isinstance(extra_permissions, dict):
        raise ValueError("Extra access must be keyed by actor, target and class")
    for key, names in extra_permissions.items():
        if not isinstance(key, tuple) or len(key) != 3:
            raise ValueError("Extra access requires an exact actor, target and class")
        actor, target, cls = key
        if (actor not in actor_names or actor in isolated or
                (target, cls) not in selected or isinstance(names, str)):
            raise ValueError("Extra access references an absent or isolated actor/object")
        names = set(names)
        if not names or not names.issubset(classes[cls]):
            raise ValueError("Extra access has empty or unknown class permissions")
        extras[key] = names
    if any(not isinstance(line, str) or not line.startswith(";") or
           "\n" in line or "\r" in line for line in preamble):
        raise ValueError("Alias preamble may contain comment lines only")
    return [(role, actor) for role, actor in all_actors if actor not in isolated], extras


def derive_preserved_aliases(library, baseline, exported, aliases, output, export, *,
                             prefix, isolated_roles, extra_permissions, preamble=()):
    """Preserve old actors exactly; isolated roles receive no permissions here.

    Callers separately prove each selected inode, the complete role boundary,
    and their exact new entry transitions. Extra access is finite and specific
    to one concrete actor, object alias and class.
    """
    policy = ContextPolicy(library, baseline)
    lines = export(policy, baseline, exported)
    text = exported.read_text()
    members = Membership(text)
    classes = _classes(text)
    actors, extras = _validate_inputs(lines, classes, aliases, prefix,
        isolated_roles, extra_permissions, preamble)
    generated = list(preamble)
    samples, transitions = [], set()
    for index, row in enumerate(aliases):
        old, new, cls = row["source"], row["target"], row["class"]
        names = classes[cls]
        _, bits = policy.permissions(cls, names)
        groups = defaultdict(list)
        for role, actor in actors:
            vals = [policy.context_av(_context(role, actor, level),
                                      "u:object_r:" + old + ":s0", cls, names)
                    for level in LEVELS]
            # Native private types are not category-dependent Android storage.
            # Reject a new object family needing a stronger derivation.
            if len(set(vals)) != 1:
                raise ValueError("Alias source access depends on MCS: " + old)
            extra = extras.get((actor, new, cls), set())
            allowed = vals[0] | sum(bits[n] for n in extra)
            groups[allowed].append(actor)
            samples.append([role, actor, old, new, cls, vals, allowed])
        for group, (allowed, selected) in enumerate(sorted(groups.items())):
            attr = prefix + "_" + str(index) + "_" + str(group)
            generated += ["(typeattribute " + attr + ")",
                          "(typeattributeset " + attr + " (" + " ".join(sorted(set(selected))) + "))"]
            for op, choose in (("allow", True), ("neverallow", False)):
                chosen = [name for name in names if bool(allowed & bits[name]) == choose]
                if chosen:
                    generated.append("(" + op + " " + attr + " " + new +
                                     " (" + cls + " (" + " ".join(chosen) + ")))")
        # Match the original exported transition, including named transitions.
        # The source policy's macros have already expanded to concrete types.
        for line in lines:
            if line.startswith(("(typetransition ", "(typechange ", "(typemember ",
                                "(roletransition ", "(allowx ")):
                form = parse_expression(line)
                if len(form) >= 4 and form[2] == old:
                    copied = line.replace(" " + old + " ", " " + new + " ", 1)
                    generated.append(copied)
                    transitions.add(copied)
        # Preserve constraint target atoms for every possible MLS range.
        for line in lines:
            if not line.startswith(("(constrain ", "(mlsconstrain ")):
                continue
            form = parse_expression(line)
            if form[1][0] != cls:
                continue
            def visit(expr):
                if not isinstance(expr, list):
                    return
                if len(expr) == 3 and expr[0] in ("eq", "neq") and "t2" in expr[1:]:
                    other = expr[2] if expr[1] == "t2" else expr[1]
                    if other in ("t1", "t2", "t3"):
                        raise ValueError("Alias needs a direct type-identity constraint proof")
                    if members.member(other, old) != members.member(other, new):
                        raise ValueError("Alias changed constraint membership: " + new + " " + other)
                for sub in expr[1:]:
                    visit(sub)
            visit(form[2])
    output.write_text("\n".join(sorted(set(generated))) + "\n")
    return {"samples": samples, "classes": classes, "actors": actors,
            "transitions": sorted(transitions),
            "source_xperms": {row["source"]: original_xperms([exported],
                sorted({a for _, a in actors}), row["source"])
                for row in {r["source"]:r for r in aliases}.values()},
            "aliases": [dict(row) for row in aliases],
            "isolated_roles": sorted(set(isolated_roles)),
            "extra_permissions": [[*key, sorted(names)] for key, names in sorted(extras.items())],
            "source_transition_forms": sorted(line for line in lines
                if line.startswith(("(typetransition ", "(typechange ", "(typemember ",
                                    "(roletransition ", "(allowx "))
                and parse_expression(line)[2] in {row["source"] for row in aliases}),
            "derived_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def verify_preserved_aliases(policy, exported, aliases, expected):
    """Read all original and aliased vectors from the same linked binary.

    The supplied ContextPolicy must refer to the binary exported by the caller
    into exported. This checks preservation, not the caller's new role contract.
    """
    if aliases != expected["aliases"]:
        raise ValueError("Alias input list differs from the actual derivation")
    lines = set(exported.read_text().splitlines())
    source_types = {row["source"] for row in aliases}
    source_forms = sorted(line for line in lines
        if line.startswith(("(typetransition ", "(typechange ", "(typemember ",
                            "(roletransition ", "(allowx "))
        and parse_expression(line)[2] in source_types)
    if source_forms != expected["source_transition_forms"]:
        raise ValueError("Original transition or extended-permission forms changed")
    if not set(expected["transitions"]).issubset(lines):
        raise ValueError("An original alias transition or ioctl filter disappeared")
    checks = []
    for role, actor, old, new, cls, vals, wanted in expected["samples"]:
        names = expected["classes"][cls]
        for i, level in enumerate(LEVELS):
            before = policy.context_av(_context(role, actor, level),
                                       _context("object_r", old), cls, names)
            after = policy.context_av(_context(role, actor, level),
                                      _context("object_r", new), cls, names)
            if before != vals[i] or after != wanted:
                raise ValueError("Alias changed existing access: " + actor + " " + new)
        checks.append([role, actor, new, cls, wanted])
    actor_names = sorted({actor for _, actor in expected["actors"]})
    for row in aliases:
        wanted = expected["source_xperms"][row["source"]][row["class"]]
        for target in (row["source"], row["target"]):
            actual = original_xperms([exported], actor_names, target)[row["class"]]
            if actual != wanted:
                raise ValueError("Alias changed original ioctl filters: " + target)
    return checks
