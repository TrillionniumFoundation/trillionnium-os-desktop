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


def _raw_vectors(lines, classes, aliases, actors, policy):
    """Read unconditional TE rules, before any MLS constraint is evaluated."""
    text = "\n".join(lines)
    if re.search(r"\((?:booleanif|tunableif)\b", text):
        raise ValueError("MCS alias preservation requires unconditional TE rules")
    members = Membership(text)
    wanted = {(row[side], row["class"]) for row in aliases for side in ("source", "target")}
    bits = {cls: policy.permissions(cls, classes[cls])[1] for _, cls in wanted}
    rules = []
    for line in lines:
        line = line.strip()
        if not line.startswith("(allow "):
            continue
        form = parse_expression(line)
        if (len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 2
                or not isinstance(form[3][1], list)):
            raise ValueError("Unsupported raw TE allow form")
        source, target, (cls, names) = form[1:]
        if cls not in classes or any(not isinstance(name, str) or
                name not in classes[cls] for name in names):
            raise ValueError("Unknown raw TE class or permission")
        rules.append((source, target, cls, names))
    if len(rules) != text.count("(allow "):
        raise ValueError("Raw TE rules are not complete unconditional statements")
    result = {}
    for target, cls in sorted(wanted):
        selected = [(source, object_type, sum(bits[cls][name] for name in set(names)))
                    for source, object_type, rule_class, names in rules
                    if rule_class == cls and
                    (object_type == "self" or members.member(object_type, target))]
        for _, actor in actors:
            value = 0
            for source, object_type, mask in selected:
                if ((object_type != "self" or actor == target) and
                        members.member(source, actor)):
                    value |= mask
            result[(actor, target, cls)] = value
    return result


def _constraint_targets(lines, aliases):
    """Prove identical target-type predicates for every possible MLS range."""
    members = Membership("\n".join(lines))
    forms = []
    checked = 0
    for line in lines:
        if not line.startswith(("(constrain ", "(mlsconstrain ")):
            continue
        form = parse_expression(line)
        selected = [row for row in aliases if row["class"] == form[1][0]]
        if not selected:
            continue
        forms.append(line)
        def target_atoms(expr, target):
            if not isinstance(expr, list):
                return expr
            if len(expr) == 3 and expr[0] in ("eq", "neq") and "t2" in expr[1:]:
                other = expr[2] if expr[1] == "t2" else expr[1]
                if isinstance(other, str) and other in ("t1", "t2", "t3"):
                    raise ValueError("Alias needs a direct type-identity constraint proof")
                value = members.member(other, target)
                return value if expr[0] == "eq" else not value
            return [target_atoms(child, target) for child in expr]
        for row in selected:
            if target_atoms(form[2], row["source"]) != target_atoms(form[2], row["target"]):
                raise ValueError("Alias changed a complete constraint target expression: " + row["target"])
            checked += 1
    return sorted(forms), checked


def derive_preserved_aliases(library, baseline, exported, aliases, output, export, *,
                             prefix, isolated_roles, extra_permissions, preamble=(),
                             mcs_aliases=()):
    """Preserve old actors exactly; isolated roles receive no permissions here.

    Callers separately prove each selected inode, the complete role boundary,
    and their exact new entry transitions. Extra access is finite and specific
    to one concrete actor, object alias and class.
    """
    policy = ContextPolicy(library, baseline)
    lines = export(policy, baseline, exported)
    text = exported.read_text()
    classes = _classes(text)
    actors, extras = _validate_inputs(lines, classes, aliases, prefix,
        isolated_roles, extra_permissions, preamble)
    mcs_selected = set(mcs_aliases)
    selected_pairs = {(row["target"], row["class"]) for row in aliases}
    if not mcs_selected.issubset(selected_pairs):
        raise ValueError("MCS preservation references an unselected object alias")
    mcs_rows = [row for row in aliases if (row["target"], row["class"]) in mcs_selected]
    constraints, constraint_checks = _constraint_targets(lines, aliases)
    raw = _raw_vectors(lines, classes, mcs_rows, actors, policy) if mcs_rows else {}
    raw_samples, mcs_samples = [], []
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
            extra = extras.get((actor, new, cls), set())
            extra_mask = sum(bits[n] for n in extra)
            if (new, cls) in mcs_selected:
                # Derive from raw TE, never a union of category-dependent AVs.
                original_raw = raw[(actor, old, cls)]
                target_raw = raw[(actor, new, cls)]
                allowed = original_raw | extra_mask
                if target_raw & ~allowed or extra_mask & ~target_raw:
                    raise ValueError("MCS alias lacks its exact explicit extra-permission preimage")
                raw_samples.append([role, actor, old, new, cls, original_raw, allowed])
                for source_level in LEVELS:
                    for target_level in LEVELS:
                        source_context = _context(role, actor, source_level)
                        before = policy.context_av(source_context,
                            _context("object_r", old, target_level), cls, names)
                        preimage = policy.context_av(source_context,
                            _context("object_r", new, target_level), cls, names)
                        mcs_samples.append([role, actor, old, new, cls,
                            source_level, target_level, before, before | preimage])
            else:
                # Existing consumers retain the original category-independent gate.
                if len(set(vals)) != 1:
                    raise ValueError("Alias source access depends on MCS: " + old)
                allowed = vals[0] | extra_mask
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
    output.write_text("\n".join(sorted(set(generated))) + "\n")
    return {"samples": samples, "classes": classes, "actors": actors,
            "mcs_aliases": [dict(row) for row in mcs_rows],
            "raw_te_samples": raw_samples, "mcs_effective_samples": mcs_samples,
            "constraint_forms": constraints, "constraint_target_checks": constraint_checks,
            "transitions": sorted(transitions),
            "source_xperms": {row["source"]: original_xperms([exported],
                sorted({a for _, a in actors}), row["source"],
                class_names=tuple(sorted({r["class"] for r in aliases if r["source"] == row["source"]})))
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
    constraints, _ = _constraint_targets(sorted(lines), aliases)
    if constraints != expected["constraint_forms"]:
        raise ValueError("Alias changed original constraint expressions")
    mcs_rows = expected["mcs_aliases"]
    mcs_selected = {(row["target"], row["class"]) for row in mcs_rows}
    raw = _raw_vectors(sorted(lines), expected["classes"], mcs_rows,
                       expected["actors"], policy) if mcs_rows else {}
    checks = []
    for role, actor, old, new, cls, before, after in expected["raw_te_samples"]:
        if raw[(actor, old, cls)] != before or raw[(actor, new, cls)] != after:
            raise ValueError("MCS alias changed a complete raw TE vector: " + actor + " " + new)
        checks.append([role, actor, new, cls, "raw-te", before, after])
    for role, actor, old, new, cls, source_level, target_level, before, after in expected["mcs_effective_samples"]:
        for target, wanted in ((old, before), (new, after)):
            actual = policy.context_av(_context(role, actor, source_level),
                _context("object_r", target, target_level), cls, expected["classes"][cls])
            if actual != wanted:
                raise ValueError("MCS alias changed constrained access: " + actor + " " + target)
        checks.append([role, actor, new, cls, source_level, target_level, before, after])
    for role, actor, old, new, cls, vals, wanted in expected["samples"]:
        if (new, cls) in mcs_selected:
            continue
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
            actual = original_xperms([exported], actor_names, target,
                class_names=(row["class"],))[row["class"]]
            if actual != wanted:
                raise ValueError("Alias changed original ioctl filters: " + target)
    return checks
