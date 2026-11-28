"""Verify calibration's original PID 1 and public image-parent boundaries."""
import hashlib
import json

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_shared_payload_cgroup_policy import parse_expression, original_xperms
from verify_native_stdio import class_permissions

ROLE = "droidloom_policy_loader"
MANAGER = "init_t"
PERMISSIONS = {
    "dir": {"getattr", "search"},
    "file": {"getattr", "open", "read"},
    "lnk_file": {"read"},
    "process": {"getattr", "sigchld"},
}
STORE = "p4_linux_product_store_t"
STORE_PERMISSIONS = {
    "dir": {"getattr", "search"},
    "file": set(),
    "lnk_file": set(),
}
SOURCE_PINS = {'runtime/droidloom-supervisor/src/production_mac.rs': (85051,
                                                        '581568c242a9cf92e4e6ecf6e3ebbaca67586fb5c731bb664fa0c8aca8726343'),
 'runtime/droidloom-supervisor/src/production_mac_release.rs': (15659,
                                                                '7ce54a89c36ce6cfc96ff0fce4919ff557931b14ec411657eae6ed3a2a5892c0'),
 'runtime/droidloom-supervisor/src/production_mac_policy.rs': (14769,
                                                               'ed82e4403c6c77f4fb2bea0bd06751216ccd6a4f91ce5c1bf939343c13586b2b'),
 'runtime/droidloom-supervisor/src/production_mac_loader.rs': (6683,
                                                               'eaccfa3f5199c4c353a5e7c1bda8bcbf524cbfc78573885ecb2a2306017ab0c3'),
 'runtime/droidloom-supervisor/src/bin/droidloom-host-mac.rs': (1641,
                                                                '431458a7ccc35d9380b9df2819b387db465428053a75d6811753c3553e6f4817'),
 'runtime/droidloom-supervisor/src/droidloom-mac-calibration.service': (1373,
                                                                        'c75560036d34b1538fa01f607242c08701620689c55e2d45fffe159c75e8811b'),
 'runtime/droidloom-supervisor/src/production_selection.rs': (25600,
                                                              '3ca5ebf07f2ec9e03c7cf66d54a20e5bb8c035b51f6bbe8bb5ff2920bfe6ea8f'),
 'runtime/droidloom-supervisor/src/production_early_release.rs': (21920,
                                                                  'e0a322f044d5a439fdb9b687e09a2aae80281f8d2d17d27a697450dce1c5d7f8')}


def source_inputs(here):
    return [here.parents[3] / name for name in SOURCE_PINS]


def verify_sources(here):
    result = {}
    for name, expected in SOURCE_PINS.items():
        body = (here.parents[3] / name).read_bytes()
        actual = (len(body), hashlib.sha256(body).hexdigest())
        if actual != expected:
            raise ValueError("Normal calibration identity consumer differs: " + name)
        result[name] = {"bytes": actual[0], "sha256": actual[1]}
    return result


def verify_store_boundary(policy, text, exported):
    """Read the complete concrete store vector, including attribute grants."""
    lines = text.splitlines()
    members = Membership(text)
    vocabulary = {kind: class_permissions(lines, kind) for kind in STORE_PERMISSIONS}
    raw = {kind: set() for kind in STORE_PERMISSIONS}
    for line in lines:
        if not line.startswith("(allow "):
            continue
        form = parse_expression(line)
        actor, target, (kind, names) = form[1:]
        if (kind in raw and members.member(actor, ROLE) and target != "self"
                and members.member(target, STORE)):
            if not isinstance(names, list) or not set(names).issubset(vocabulary[kind]):
                raise ValueError("Unknown calibration store permission")
            raw[kind].update(names)
    if raw != STORE_PERMISSIONS:
        raise ValueError("Calibration store permission/complement differs")
    masks = original_xperms([exported], [ROLE], STORE,
                            class_names=tuple(STORE_PERMISSIONS))
    if any(masks[kind][ROLE] for kind in masks):
        raise ValueError("Calibration store acquired an ioctl filter")
    checks = []
    for source_level in LEVELS:
        for target_level in LEVELS:
            actor = f"u:r:{ROLE}:{source_level}"
            target = f"u:object_r:{STORE}:{target_level}"
            for kind, allowed in STORE_PERMISSIONS.items():
                _, bits = policy.permissions(kind, vocabulary[kind])
                permitted = sum(bits[name] for name in allowed)
                actual = policy.context_av(actor, target, kind, vocabulary[kind])
                if actual & ~permitted:
                    raise ValueError("Calibration store category pair escaped its complement")
                if source_level == target_level == "s0" and actual != permitted:
                    raise ValueError("Calibration public image parent traversal is denied")
                checks.append([source_level, target_level, kind, actual])
    return {
        "actor": ROLE, "target": STORE,
        "raw_permissions": {kind: sorted(names) for kind, names in raw.items()},
        "directory_enumeration_granted": False, "private_file_access_granted": False,
        "new_te_permission_bits": 2, "effective_vectors": checks,
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
    }


def verify_native_calibration(library, binary, exported, here):
    sources = verify_sources(here)
    policy = ContextPolicy(library, binary)
    text = exported.read_text()
    store = verify_store_boundary(policy, text, exported)
    lines = text.splitlines()
    members = Membership(text)
    vocabulary = {kind: class_permissions(lines, kind) for kind in PERMISSIONS}
    raw = {kind: set() for kind in PERMISSIONS}
    for line in lines:
        if not line.startswith("(allow "):
            continue
        form = parse_expression(line)
        if (len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 2):
            raise ValueError("Unmodeled calibration raw TE rule")
        actor, target, (kind, names) = form[1:]
        if (kind in raw and members.member(actor, ROLE) and target != "self"
                and members.member(target, MANAGER)):
            if not isinstance(names, list) or not set(names).issubset(vocabulary[kind]):
                raise ValueError("Unknown calibration permission")
            raw[kind].update(names)
    if raw != PERMISSIONS:
        raise ValueError("Calibration PID 1 raw permission/complement differs")
    masks = original_xperms([exported], [ROLE], MANAGER,
                            class_names=("dir", "file", "lnk_file"))
    if any(masks[kind][ROLE] for kind in masks):
        raise ValueError("Calibration PID 1 acquired an ioctl filter")
    ioctls = {kind: [] for kind in masks}

    checks = []
    count = 0
    for source_level in LEVELS:
        for target_level in LEVELS:
            actor = f"u:r:{ROLE}:{source_level}"
            target = f"u:system_r:{MANAGER}:{target_level}"
            for kind, allowed in PERMISSIONS.items():
                _, bits = policy.permissions(kind, vocabulary[kind])
                permitted = sum(bits[name] for name in allowed)
                actual = policy.context_av(actor, target, kind, vocabulary[kind])
                # Raw TE is exact above. MLS may remove rights at other category
                # pairs, but can never create a right outside this closed set.
                if actual & ~permitted:
                    raise ValueError("Calibration category pair escaped its complement")
                if source_level == target_level == "s0" and actual != permitted:
                    raise ValueError("Calibration original manager observation is denied")
                checks.append([source_level, target_level, kind, actual])
                count += len(vocabulary[kind])
    return {
        "schema": "droidloom.native-calibration-manager-proof.v1",
        "consumer_sources": sources,
        "actor": ROLE, "target": MANAGER,
        "proc_root": "/proc/1",
        "fixed_files": ["/proc/1/attr/current", "/proc/1/attr/apparmor/current"],
        "fixed_links": ["/proc/1/exe", "/proc/1/ns/user", "/proc/1/ns/pid"],
        "raw_permissions": {kind: sorted(names) for kind, names in raw.items()},
        "original_process_permissions": sorted(PERMISSIONS["process"]),
        "new_te_permission_bits": 6,
        "ptrace_granted": False, "directory_enumeration_granted": False,
        "link_getattr_granted": False, "ioctls": ioctls,
        "category_pairs": len(LEVELS) ** 2,
        "full_class_permission_checks": count,
        "effective_vectors": checks,
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
        "runtime_qualified": False,
        "selected_public_image_parents": store,
    }
