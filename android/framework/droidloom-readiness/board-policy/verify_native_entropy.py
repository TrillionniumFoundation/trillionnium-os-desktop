"""Verify the fixed early entropy-label transaction, without device-body access."""
import hashlib
import json
import re

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_shared_payload_cgroup_policy import parse_expression, original_xperms
from verify_native_stdio import class_permissions

EARLY = "p4_linux_early_t"
EXPECTED = {
    (EARLY, "device", "chr_file"): {"getattr", "relabelfrom"},
    (EARLY, "random_device", "chr_file"): {"getattr", "relabelto"},
    ("random_device", "device", "filesystem"): {"associate"},
}
SOURCE_PINS = {
    "runtime/droidloom-early-boot/linux_run_label.c":
        (81473, "06067bea8bae2b52116339330bcb29bdb7de3c65eee722a6f834bf4cc75ca755"),
    "runtime/droidloom-early-boot/linux_run_label.h":
        (4896, "0906e6cb194798595dfbb0461f518514865efe4b89484c0159d72b709a746e91"),
    "runtime/droidloom-early-boot/board_init.c":
        (28851, "b695288f215158e5dd83292f156898103e82d01fdf6a6d855d7f03d778711b1b"),
    "runtime/droidloom-early-boot/tests/standard_devices_test.c":
        (17094, "f64e112e1cf1bab909089f2085f0ca06863ee26482613c14b5cddde64eacfeb3"),
}
RELABEL_GUARDS = {
    "(mlsvalidatetrans chr_file (or (not (eq t3 p4_native_pam_roles)) (and (eq l1 l2) (eq h1 h2))))",
    "(validatetrans chr_file (or (neq t3 p4_linux_hardware_label_t) (or (eq t1 device) (eq t1 t2))))",
    "(validatetrans chr_file (or (not (eq t3 p4_native_pam_roles)) (and (eq t1 t2) (and (eq u1 u2) (eq r1 r2)))))",
}
FS_USE = "(fsuse trans devtmpfs (u object_r device ((s0) (s0))))"


def source_inputs(here):
    return [here.parents[3] / path for path in SOURCE_PINS]


def verify_sources(here):
    sources = {}
    for name, wanted in SOURCE_PINS.items():
        body = (here.parents[3] / name).read_bytes()
        actual = (len(body), hashlib.sha256(body).hexdigest())
        if actual != wanted:
            raise ValueError("Early entropy source identity differs: " + name)
        sources[name] = {"bytes": actual[0], "sha256": actual[1]}
    fixed = [line.strip() for line in (here / "ubuntu-native-file_contexts").read_text().splitlines()
             if line.startswith(("/dev/random ", "/dev/urandom "))]
    if sorted(fixed) != [
        "/dev/random -c u:object_r:random_device:s0",
        "/dev/urandom -c u:object_r:random_device:s0",
    ]:
        raise ValueError("Fixed normal entropy file-context entries differ")
    return {"consumer_sources": sources, "fixed_file_contexts": fixed}


def verify_native_entropy(library, binary, exported, here):
    source = verify_sources(here)
    text = exported.read_text()
    lines = text.splitlines()
    members = Membership(text)
    policy = ContextPolicy(library, binary)
    vocabulary = {kind: class_permissions(lines, kind) for _, _, kind in EXPECTED}
    raw = {key: set() for key in EXPECTED}
    allow_count = 0
    for line in lines:
        if not line.startswith("(allow "):
            continue
        allow_count += 1
        form = parse_expression(line)
        if len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 2:
            raise ValueError("Unmodeled early entropy raw rule")
        actor, target, (kind, names) = form[1:]
        for (role, obj, cls), permissions in raw.items():
            if (kind == cls and members.member(actor, role)
                    and (role == obj if target == "self" else members.member(target, obj))):
                if not isinstance(names, list) or not set(names).issubset(vocabulary[cls]):
                    raise ValueError("Unknown early entropy raw permission")
                permissions.update(names)
    if allow_count != len(re.findall(r"\(allow\s", text)):
        raise ValueError("Early entropy raw rules are not complete statements")
    if raw != EXPECTED:
        raise ValueError("Early entropy permission or complete complement differs")
    for obj in ("device", "random_device"):
        masks = original_xperms([exported], [EARLY], obj, class_names=("chr_file",))
        if masks["chr_file"][EARLY]:
            raise ValueError("Early entropy transaction acquired a device ioctl filter")
    # The existing three complete relabel constraints have explicit actor
    # guards. The fixed early role is outside both guarded actor sets, so
    # all three evaluate true without changing any constraint or category.
    guards = [line for line in lines if line.startswith(
        ("(validatetrans chr_file ", "(mlsvalidatetrans chr_file "))]
    if (len(guards) != len(RELABEL_GUARDS) or set(guards) != RELABEL_GUARDS
            or len(guards) != len(re.findall(
                r"\((?:validatetrans|mlsvalidatetrans)\s+chr_file\s", text))):
        raise ValueError("Early entropy complete relabel constraints differ")
    if (members.member("p4_native_pam_roles", EARLY)
            or members.member("p4_linux_hardware_label_t", EARLY)):
        raise ValueError("Early role entered a guarded relabel actor set")
    if [line for line in lines if line.startswith("(fsuse ") and
            parse_expression(line)[2] == "devtmpfs"] != [FS_USE]:
        raise ValueError("Original devtmpfs initial labeling differs")
    rows = []
    checks = 0
    for source_level in LEVELS:
        for target_level in LEVELS:
            for (actor, obj, cls), names in EXPECTED.items():
                source_role = "system_r" if actor == EARLY else "object_r"
                _, bits = policy.permissions(cls, vocabulary[cls])
                wanted = sum(bits[name] for name in names)
                actual = policy.context_av(
                    f"u:{source_role}:{actor}:{source_level}",
                    f"u:object_r:{obj}:{target_level}", cls, vocabulary[cls])
                if actual & ~wanted:
                    raise ValueError("Early entropy category pair escaped its complement")
                if source_level == target_level == "s0" and actual != wanted:
                    raise ValueError("Fixed early entropy labeling is denied")
                rows.append([actor, obj, cls, source_level, target_level, actual])
                checks += len(vocabulary[cls])
    return {
        "schema": "droidloom.native-early-entropy-proof.v1",
        **source,
        "fixed_nodes": [
            {"path": "/dev/random", "major": 1, "minor": 8, "mode": 438, "uid": 0, "gid": 0},
            {"path": "/dev/urandom", "major": 1, "minor": 9, "mode": 438, "uid": 0, "gid": 0},
        ],
        "raw_vectors": [[*key, sorted(value)] for key, value in sorted(raw.items())],
        "new_te_permission_bits": 3,
        "original_device_relabelfrom_preserved": True,
        "device_body_access": False,
        "device_ioctl_filters": [],
        "relabel_guards": sorted(guards),
        "fixed_actor_outside_relabel_guards": True,
        "devtmpfs_fs_use": FS_USE,
        "all_other_xattrs_verified": True,
        "category_pairs": len(LEVELS) ** 2,
        "full_class_permission_checks": checks,
        "effective_vectors": rows,
        "matrix_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
        "runtime_qualified": False,
    }
