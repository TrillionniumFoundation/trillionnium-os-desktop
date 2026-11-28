"""Admit the fixed normal kmod static-node configuration lifecycle.

Early PID 1 prepares one fixed directory; the normal executor validates it. The unchanged
kmod command writes one named regular file. The unchanged normal tmpfiles ELF
uses its dedicated consumer; the original setup actor retains its full source
view, independently of the dedicated consumer's complete permission proof.
"""
import ctypes
import hashlib
import json
import re
import stat
from collections import defaultdict

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_preserved_alias_policy import (
    _context, _classes, _roles, _validate_inputs, _constraint_targets, _preserved_xperm_rules,
    original_xperms)
from derive_shared_payload_cgroup_policy import parse_expression

PRODUCER = "p4_linux_module_loader_t"
EXECUTOR = "p4_linux_service_executor_t"
TMPFILES = "p4_linux_tmpfiles_t"
ISOLATED_ROLES = {TMPFILES}
DIRECTORY = "p4_linux_kmod_tmpfiles_dir_t"
CONFIG = "p4_linux_kmod_static_nodes_t"
ALIASES = [
    {"source": "p4_linux_rootdir_t", "target": DIRECTORY, "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": CONFIG, "class": "file"},
]
EXTRA = {
    (EXECUTOR, DIRECTORY, "dir"): {"open", "read", "setattr"},
    ("kernel", DIRECTORY, "dir"): {"relabelto"},
    (PRODUCER, DIRECTORY, "dir"): {"write", "add_name"},
    (PRODUCER, CONFIG, "file"): {"create", "write", "setattr"},
}
TRANSITIONS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")
CONSTRAINTS = ("(constrain ", "(mlsconstrain ", "(validatetrans ", "(mlsvalidatetrans ")
FIXED_TRANSITIONS = {
    '(typetransition ' + PRODUCER + ' ' + DIRECTORY + ' file "static-nodes.conf" ' + CONFIG + ')',
}
DROPIN = "ubuntu-kmod-static-nodes-runtime.conf"
DROPIN_PATH = "usr/lib/systemd/system/kmod-static-nodes.service.d/50-droidloom-runtime-directory.conf"
PACKAGERS = (
    "tools/droidloom-update/src/early_boot_package.rs",
    "tools/droidloom-update/src/host_archive.rs",
    "tools/droidloom-update/src/package.rs",
)
SOURCE_FILES = {('kernel', 'fs/namei.c'): (153602, 'd8fe89b24c757861906d4b7fbcbe04b3d66736f8df813a21544d0f8f5f93dc63'),
 ('kernel', 'security/selinux/ss/services.c'): (96491, 'a3dc132fceec9f42a8d1728cef1b45685d5d2e0f3b5dcb812bec4049c5c19f67'),
 ('glibc', 'libio/fileops.c'): (43969, '8c14eb902c1030b898a198b720bb6a9ba4925e05e85cbef71b9f571834a9d735'),
 ('kernel', 'security/selinux/hooks.c'): (212133,
                                          '4fa2a20bff2788fffc1f6bc95d49af3e1145e6a679f69ff5aa2d5a1bd85272a0'),
 ('kmod', 'shared/util.c'): (10505, '4a79e8ff9b9acd8250909d230604515a9bface3bd04e50e994bdae6267ad374b'),
 ('kmod', 'tools/static-nodes.c'): (6719, 'd53f1fd27317ddd94a8d2ec28ece809223502b1454502953147446e8aa8e8feb'),
 ('source', 'src/basic/conf-files.c'): (34859,
                                        'ee1d150afbc9ab9ec3714c67bf49a15ec452ff01368a4d61b2e9f84a969c1619'),
 ('source', 'src/basic/constants.h'): (3287,
                                       '8beabd68da7b1398a6239c04c8d510e0f93fb7809e09ba846204cfbd50820102'),
 ('source', 'src/basic/fs-util.c'): (52249, 'de38f495f3be7fc9e80051487bac1242c71f2f38cffa4fba2d8f11380d3794d4'),
 ('source', 'src/basic/mkdir.c'): (9880, '88a9ce00bc2c05c0c5d329653c29846622356efcbc207639a5877b323d102756'),
 ('source', 'src/core/exec-invoke.c'): (276788,
                                        '24eda88ee0914d0c43d30ebfb13f0f3aadd00391b5820fb6d6509278f0925dfe'),
 ('source', 'src/core/execute.c'): (111938, '3fdc25491919ccbe96812a8d56d20e34bbf367a29555b304b5fa0b06838c8a26'),
 ('source', 'src/core/execute.h'): (25855, 'ed2f451076685ec0ce043cb619a985bcd9c066436d583887b9de3e6a494c04cc'),
 ('source', 'src/core/load-fragment-gperf.gperf.in'): (94199,
                                                       '5f3f314afa01340a071722f1656f5c40c0c4ffcf3bd82b14ce0471548c2556fa'),
 ('source', 'src/core/load-fragment.c'): (235363,
                                          '9985bb9569789696c80e0132ddd5abfdde2deef6f8be0dd2baddde67b5bf27b5'),
 ('source', 'src/core/unit.c'): (250300, '2c6ca36da9fc5324a1d168e161e63d4972f000a2921f00b6489597453dd393b6'),
 ('source', 'src/shared/chown-recursive.c'): (5635,
                                              'ce5d1a8d79b32011c479fdb78bd75faabdf3107bdffcd6bc5b1793967edf189f'),
 ('source', 'src/shared/mkdir-label.c'): (1389,
                                          'cb5470df867959d3668f22c41ef2d6a514e996f6c2348b8eee3f1c07800d6e5a'),
 ('source', 'src/shared/selinux-util.c'): (25770,
                                           '241a1cdb353d954a1a771e4b33709860a2df729bb7512130b5fb985fe1105df7'),
 ('source', 'src/tmpfiles/tmpfiles.c'): (180129,
                                         'f3aa633ad113f8ef4e98a3401a8b3403cb1af253ffb6cbcfc748ace70b9619e9')}
NORMAL_FILES = {'/usr/bin/kmod': (174472, '6edf62330978627d75d8de7e903f243b6ba765f8b54baa914ec83e21cd85bdc7', 493),
 '/usr/bin/systemd-tmpfiles': (121544, 'a647746774851ef136cea5ea1862c77e2b0ff0bd962629ce07da029ff5bd8cc8', 493),
 '/usr/lib/systemd/system/kmod-static-nodes.service': (771,
                                                       'aec86f5b56a23faf7e748914ec8362b2a8651f2aa114881184b7af5fb883687d',
                                                       420),
 '/usr/lib/systemd/system/systemd-tmpfiles-setup-dev-early.service': (852,
                                                                      '6c9429db294f317608868337ca1befd1fc961886e0d4accf8997dfd33e1a61de',
                                                                      420),
 '/usr/lib/systemd/system/systemd-tmpfiles-setup-dev.service': (877,
                                                                '9f0a6b2414d3b398357b7508f6a841acae0d8f0ff079e096c0bed78f0572122e',
                                                                420),
 '/usr/lib/systemd/system/systemd-tmpfiles-setup.service': (1023,
                                                            'f22a7dc686fc61d586bc8e44f46e76eb6d926c7919249b10848830eb4bf90c28',
                                                            420),
 '/usr/lib/systemd/systemd-executor': (154176,
                                       'afdc9afa0073871b5b303c7eae2857da727abec5d9cfa5bcb63df96ac53da12f',
                                       493)}
SOURCE_VERSIONS = {
    "source": ("systemd", "259.9-0ubuntu0.1+p4gentmp2", "normal-dsc-roundtrip"),
    "kmod": ("kmod", "34.2-2ubuntu2", "normal-signed-apt-quilt-source"),
    "glibc": ("glibc", "2.43-2ubuntu2.7", "normal-signed-apt-quilt-source"),
    "kernel": ("linux", "6.18.64-p4ctx6181-fusectl-aafs-peer-r1", "selected-kernel-source"),
}
DROPIN_SHA256 = '6a8391acd73957bfc0a81aa8b2353e702c120342aeee2d1b2b4f05244f895a7d'
DROPIN_BYTES = 240
EARLY_FILES = {'runtime/droidloom-early-boot/board_policy.c': (58619,
                                                 'feb5ad943565e5ee8f716c8c86ee3d9bd874d433959636c271100faf207daa43'),
 'runtime/droidloom-early-boot/linux_run_label.c': (88695,
                                                    '2b077a453505bd7d9912a105993effe16c4278bc9cd247c300b3af0a66716d60'),
 'runtime/droidloom-early-boot/linux_run_label.h': (4939,
                                                    'cf67eb6b96cf8bf09e0b70c763b3407c10fd4ee5580ade5761579f368eadaf94')}


def source_inputs(here):
    return [here / "native-kmod-static-source.json", here / DROPIN,
            *(here.parents[3] / name for name in (*PACKAGERS, *EARLY_FILES)),
            here.parents[3] / "runtime/droidloom-early-boot/tests/tmpfiles_directory_test.c"]


def contract(here):
    value = json.loads((here / "native-kmod-static-source.json").read_text())
    expected_keys = {"schema", "actor", "executor", "aliases", "source_documents",
                     "normal_files", "source_admissions", "unit", "dropin",
                     "runtime_directory", "output", "original_policy_sha256",
                     "unit_changed", "runtime_qualified", "early_directory"}
    if (set(value) != expected_keys or
            value["schema"] != "droidloom.native-kmod-static-source.v1" or
            value["actor"] != PRODUCER or value["executor"] != EXECUTOR or
            value["aliases"] != ALIASES or value["unit_changed"] is not False or
            value["runtime_qualified"] is not False or
            value["original_policy_sha256"] != "334f85991aa8b821efbd8ee793083d0031ff1ffbb9bddac7e928c5fa2092d42c"):
        raise ValueError("Unexpected normal kmod static-node contract")
    sources = value["source_documents"]
    if (len(sources) != len(SOURCE_FILES) or
            {(r.get("kind"), r.get("path")) for r in sources} != set(SOURCE_FILES)):
        raise ValueError("Incomplete fixed kmod/source/kernel closure")
    for row in sources:
        if (set(row) != {"kind", "path", "bytes", "sha256", "package", "version", "admission"} or
                (row["bytes"], row["sha256"]) != SOURCE_FILES[(row["kind"], row["path"])] or
                (row["package"], row["version"], row["admission"]) != SOURCE_VERSIONS[row["kind"]]):
            raise ValueError("Kmod source is not the admitted normal input")
    files = value["normal_files"]
    if len(files) != len(NORMAL_FILES) or {r.get("path") for r in files} != set(NORMAL_FILES):
        raise ValueError("Incomplete unchanged normal kmod/tmpfiles files")
    for row in files:
        if (set(row) != {"path", "bytes", "sha256", "uid", "gid", "mode", "nlink"} or
                (row["bytes"], row["sha256"], row["mode"]) != NORMAL_FILES[row["path"]] or
                (row["uid"], row["gid"], row["nlink"]) != (0, 0, 1)):
            raise ValueError("Unexpected normal kmod/tmpfiles input metadata")
    if value["source_admissions"] != {
            "kmod": {"bytes": 14259, "sha256": "b618c83a5999ab078c66bf6bf7d920bbc36273085259136c8e87008ee96dd012"},
            "glibc": {"bytes": 19073, "sha256": "8b1d42efa9e602dbf104c7ca3b255c1e846f85f3e77e0eac10166095cad10081"}}:
        raise ValueError("Normal kmod/glibc source admission changed")
    if value["unit"] != {
            "path": "/usr/lib/systemd/system/kmod-static-nodes.service",
            "argv": ["/usr/bin/kmod", "static-nodes", "--format=tmpfiles",
                     "--output=/run/tmpfiles.d/static-nodes.conf"],
            "before": "systemd-tmpfiles-setup-dev-early.service"}:
        raise ValueError("The unchanged normal kmod command differs")
    if value["dropin"] != {"source": DROPIN, "path": "/" + DROPIN_PATH, "bytes": DROPIN_BYTES,
                           "sha256": DROPIN_SHA256, "mode": 0o444}:
        raise ValueError("The normal kmod RuntimeDirectory drop-in differs")
    body = (here / DROPIN).read_bytes()
    if len(body) != DROPIN_BYTES or hashlib.sha256(body).hexdigest() != DROPIN_SHA256:
        raise ValueError("Kmod drop-in source bytes changed")
    if value["runtime_directory"] != {
            "path": "/run/tmpfiles.d", "name": "tmpfiles.d", "uid": 0, "gid": 0,
            "mode": 0o755, "preserve": "yes", "type": DIRECTORY,
            "quota_query": False, "recursive_chown_if_owner_differs_only": True,
            "prepared_before_policy": True}:
        raise ValueError("Shared generated tmpfiles directory lifecycle changed")
    if value["output"] != {
            "path": "/run/tmpfiles.d/static-nodes.conf", "name": "static-nodes.conf",
            "type": CONFIG, "open_mode": "we", "rename": False, "unlink": False,
            "device_nodes_created_by_kmod": False,
            "reader": TMPFILES, "preserved_original_reader": "p4_linux_setup_t"}:
        raise ValueError("Kmod output escaped its fixed text-file lifecycle")
    early = value["early_directory"]
    wanted_early = {
        "source_files": [{"path": name, "bytes": size, "sha256": digest}
                         for name, (size, digest) in EARLY_FILES.items()],
        "producer": "droidloom_board_activate_policy",
        "prepare": "droidloom_hold_linux_tmpfiles", "label": "droidloom_label_linux_tmpfiles",
        "before_first_policy_load": True, "same_held_inode_after_load": True,
        "create_only": True, "original_label": "u:object_r:tmpfs:s0",
        "selected_label": "u:object_r:" + DIRECTORY + ":s0",
        "generic_run_write_added": False}
    if early != wanted_early:
        raise ValueError("The fixed early directory handoff differs")
    for name, (size, digest) in EARLY_FILES.items():
        data = (here.parents[3] / name).read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("The compiled early tmpfiles producer changed")
    for name in PACKAGERS:
        text = (here.parents[3] / name).read_text()
        if text.count('"' + DROPIN_PATH + '"') != 1 or DROPIN not in text:
            raise ValueError("A normal packager omits or duplicates the kmod drop-in")
    return value


def _raw_new_targets(policy, lines, classes, actors, *, targets=(DIRECTORY, CONFIG)):
    """Complete raw permissions, including implicit zero vectors in every class."""
    members = Membership("\n".join(lines))
    wanted_targets = tuple(targets)
    result = {}
    bits = {cls: policy.permissions(cls, names)[1] for cls, names in classes.items()}
    for line in lines:
        if not line.startswith("(allow "):
            continue
        form = parse_expression(line)
        cls, names = form[3]
        if cls not in classes:
            raise ValueError("Unknown class in normal binary export")
        selected = [name for name in wanted_targets if form[2] == "self" or members.member(form[2], name)]
        if not selected:
            continue
        mask = sum(bits[cls][name] for name in names)
        for role, actor in actors:
            if members.member(form[1], actor):
                for target in selected:
                    if form[2] == "self" and actor != target:
                        continue
                    key = (role, actor, target, cls)
                    result[key] = result.get(key, 0) | mask
    return [list(key) + [mask] for key, mask in sorted(result.items()) if mask]


def _selected_transitions(lines):
    return sorted(line for line in lines if line.startswith(TRANSITIONS) and
                  ({DIRECTORY, CONFIG} & set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", line))))


def _guard_vectors(policy, classes):
    """Keep the old producer authority and executor's generic parent unchanged."""
    selected = [
        (PRODUCER, PRODUCER, "capability"), (PRODUCER, PRODUCER, "capability2"),
        (PRODUCER, "p4_linux_run_t", "dir"),
        (PRODUCER, "p4_linux_rootdir_t", "dir"),
        (PRODUCER, "p4_linux_native_data_t", "file"),
        (PRODUCER, "p4_linux_native_config_t", "file"),
        (PRODUCER, "p4_linux_auth_data_t", "file"),
        (PRODUCER, "p4_linux_kernel_modules_t", "file"),
        (PRODUCER, "p4_linux_kernel_modules_t", "system"),
        (PRODUCER, "sysfs", "file"),
        (EXECUTOR, "p4_linux_run_t", "dir"),
    ]
    rows = []
    for actor, target, cls in selected:
        role = "system_r" if actor == target else "object_r"
        for level in LEVELS:
            rows.append([actor, target, cls, level,
                         policy.context_av(_context("system_r", actor, level),
                                           _context(role, target), cls, classes[cls])])
    return rows


def _fixed_relabel_guards(policy, lines, classes, actors, raw):
    """Model the two actual relabel guards without changing their expressions.

    The guarded hardware/uevent subjects have no label authority on either the
    source or its fixed alias. Every other subject satisfies the first disjunct.
    Thus alias access preservation does not create a newly permitted relabel.
    """
    text = "\n".join(lines)
    if re.search(r"\((?:typebounds|booleanif|tunableif)\b", text):
        raise ValueError("Kmod raw aliases require the fixed unconditional policy")
    fixed = {
        "dir": ("p4_linux_hardware_label_t",
                "13e95abc68e40d41bd459bcaa270c23b3ce47db852053bc0413ca4038ea506b8"),
        "file": ("p4_linux_uevent_label_t",
                 "e328092894bfada71771f047d512b0811ecd3ee902334b34015fe0153876beb7"),
    }
    found = {}
    for line in lines:
        if not line.startswith(("(validatetrans ", "(mlsvalidatetrans ")):
            continue
        form = parse_expression(line)
        if len(form) != 3 or not isinstance(form[1], str) or form[1] not in classes:
            raise ValueError("Unmodelled normal relabel constraint")
        cls = form[1]
        if cls not in fixed:
            continue
        actor, digest = fixed[cls]
        if (cls in found or form[0] != "validatetrans" or
                hashlib.sha256(line.encode()).hexdigest() != digest or
                form[2][:2] != ["or", ["neq", "t3", actor]]):
            raise ValueError("The selected fixed relabel guard changed")
        found[cls] = line
    if set(found) != set(fixed):
        raise ValueError("A fixed relabel guard is missing")
    checks = []
    for row in ALIASES:
        cls = row["class"]
        actor = fixed[cls][0]
        roles = [role for role, name in actors if name == actor]
        if roles != ["system_r"]:
            raise ValueError("Relabel guard subject role changed")
        _, bits = policy.permissions(cls, classes[cls])
        mask = bits["relabelfrom"] | bits["relabelto"]
        for target in (row["source"], row["target"]):
            if raw.get(("system_r", actor, target, cls), 0) & mask:
                raise ValueError("Guarded label subject gained authority on the fixed alias")
            checks.append([actor, target, cls, 0])
    return {"forms": [found[name] for name in sorted(found)],
            "guarded_label_vectors": checks, "other_subject_first_disjunct": True}


def _derive_aliases(library, baseline, exported, output, export):
    policy = ContextPolicy(library, baseline)
    lines = export(policy, baseline, exported)
    classes = _classes("\n".join(lines))
    actors, extras = _validate_inputs(
        lines, classes, ALIASES, "p4_kmod_static_preserved", ISOLATED_ROLES, EXTRA, ())
    if not ISOLATED_ROLES <= {a for _, a in _roles(lines)}:
        raise ValueError("The separately verified tmpfiles consumer is missing")
    raw_rows = _raw_new_targets(
        policy, lines, classes, actors,
        targets=tuple(sorted({r[k] for r in ALIASES for k in ("source", "target")})))
    raw = {tuple(row[:-1]): row[-1] for row in raw_rows}
    relabel = _fixed_relabel_guards(policy, lines, classes, actors, raw)
    constraints, constraint_checks = _constraint_targets(lines, ALIASES)
    xperms, xperm_rules = _preserved_xperm_rules(exported, ALIASES, actors)
    generated = ["; Fixed kmod raw TE aliases; original relabel guards retained."] + xperm_rules
    samples, raw_samples, mcs_samples, transitions = [], [], [], set()
    for index, row in enumerate(ALIASES):
        old, new, cls = row["source"], row["target"], row["class"]
        _, bits = policy.permissions(cls, classes[cls])
        groups = defaultdict(list)
        for role, actor in actors:
            original = raw.get((role, actor, old, cls), 0)
            preimage = raw.get((role, actor, new, cls), 0)
            extra = sum(bits[n] for n in extras.get((actor, new, cls), set()))
            wanted = original | extra
            if preimage & ~wanted or extra & ~preimage:
                raise ValueError("Kmod alias lacks its exact explicit raw preimage")
            raw_samples.append([role, actor, old, new, cls, original, wanted])
            values = []
            for source_level in LEVELS:
                for target_level in LEVELS:
                    source_context = _context(role, actor, source_level)
                    before = policy.context_av(source_context, _context("object_r", old, target_level),
                                               cls, classes[cls])
                    target = policy.context_av(source_context, _context("object_r", new, target_level),
                                               cls, classes[cls])
                    mcs_samples.append([role, actor, old, new, cls, source_level, target_level,
                                        before, before | target])
                    if target_level == "s0":
                        values.append(before)
            samples.append([role, actor, old, new, cls, values, wanted])
            groups[wanted].append(actor)
        for group, (mask, names) in enumerate(sorted(groups.items())):
            attr = "p4_kmod_static_preserved_" + str(index) + "_" + str(group)
            generated += ["(typeattribute " + attr + ")",
                          "(typeattributeset " + attr + " (" + " ".join(sorted(set(names))) + "))"]
            for op, choose in (("allow", True), ("neverallow", False)):
                selected = [name for name in classes[cls] if bool(mask & bits[name]) == choose]
                if selected:
                    generated.append("(" + op + " " + attr + " " + new +
                                     " (" + cls + " (" + " ".join(selected) + ")))")
        for line in lines:
            if line.startswith(TRANSITIONS) and parse_expression(line)[2] == old:
                copied = line.replace(" " + old + " ", " " + new + " ", 1)
                generated.append(copied)
                transitions.add(copied)
    output.write_text("\n".join(sorted(set(generated))) + "\n")
    return {"samples": samples, "classes": classes, "actors": actors,
            "isolated_roles": sorted(ISOLATED_ROLES),
            "raw_te_samples": raw_samples, "mcs_effective_samples": mcs_samples,
            "constraint_forms": constraints, "constraint_target_checks": constraint_checks,
            "relabel_guard_proof": relabel, "transitions": sorted(transitions),
            "source_xperms": xperms, "aliases": ALIASES,
            "source_transition_forms": sorted(line for line in lines
                if line.startswith(TRANSITIONS + ("(allowx ",)) and
                parse_expression(line)[2] in {row["source"] for row in ALIASES}),
            "derived_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def _verify_aliases(policy, exported, expected):
    lines = exported.read_text().splitlines()
    if (expected["isolated_roles"] != sorted(ISOLATED_ROLES) or
            not ISOLATED_ROLES <= {a for _, a in _roles(lines)} or
            [(r, a) for r, a in _roles(lines) if a not in ISOLATED_ROLES] !=
            [tuple(x) for x in expected["actors"]]):
        raise ValueError("Kmod separately verified consumer/actor roster changed")
    if expected["aliases"] != ALIASES:
        raise ValueError("The actual kmod derivation selected different aliases")
    source_forms = sorted(line for line in lines
        if line.startswith(TRANSITIONS + ("(allowx ",)) and
        parse_expression(line)[2] in {row["source"] for row in ALIASES})
    if source_forms != expected["source_transition_forms"] or not set(expected["transitions"]) <= set(lines):
        raise ValueError("Kmod alias changed an original transition or ioctl form")
    constraints, count = _constraint_targets(lines, ALIASES)
    if constraints != expected["constraint_forms"] or count != expected["constraint_target_checks"]:
        raise ValueError("Kmod alias changed an original constraint target predicate")
    raw_rows = _raw_new_targets(policy, lines, expected["classes"], expected["actors"],
        targets=tuple(sorted({r[k] for r in ALIASES for k in ("source", "target")})))
    raw = {tuple(row[:-1]): row[-1] for row in raw_rows}
    if _fixed_relabel_guards(policy, lines, expected["classes"], expected["actors"], raw) != expected["relabel_guard_proof"]:
        raise ValueError("Kmod alias changed the complete relabel guard proof")
    checks = []
    for role, actor, old, new, cls, before, after in expected["raw_te_samples"]:
        if (raw.get((role, actor, old, cls), 0) != before or
                raw.get((role, actor, new, cls), 0) != after):
            raise ValueError("Kmod alias changed a complete raw TE vector")
        checks.append([role, actor, new, cls, "raw-te", before, after])
    for role, actor, old, new, cls, source_level, target_level, before, after in expected["mcs_effective_samples"]:
        for target, wanted in ((old, before), (new, after)):
            actual = policy.context_av(_context(role, actor, source_level),
                _context("object_r", target, target_level), cls, expected["classes"][cls])
            if actual != wanted:
                raise ValueError("Kmod alias changed constrained access: " + actor + " " + target)
        checks.append([role, actor, new, cls, source_level, target_level, before, after])
    actor_names = sorted({actor for _, actor in expected["actors"]})
    for row in ALIASES:
        wanted = expected["source_xperms"][row["source"]][row["class"]]
        for target in (row["source"], row["target"]):
            actual = original_xperms([exported], actor_names, target,
                                     class_names=(row["class"],))[row["class"]]
            if actual != wanted:
                raise ValueError("Kmod alias changed a complete original ioctl filter")
    return checks



# These are the only existing metadata traversers whose generic data view
# also applies when this regular-file type is queried as a directory.
OTHER_CLASS_PREIMAGE = {
    ("r", "droidloom_metadata_observer", CONFIG, "dir"): {"getattr", "search"},
    ("r", "droidloom_query_io", CONFIG, "dir"): {"getattr", "search"},
}


def _other_class_preimage(policy, lines, classes, actors):
    """Admit a fixed cross-class preimage, with its actual old-source view."""
    selected = {row["target"]: row for row in ALIASES}
    raw = {tuple(row[:-1]): row[-1] for row in _raw_new_targets(
        policy, lines, classes, actors,
        targets=tuple(sorted({row[k] for row in ALIASES for k in ("source", "target")})))}
    actual = {key: mask for key, mask in raw.items()
              if key[2] in selected and key[3] != selected[key[2]]["class"]}
    fixed = {}
    for key, names in OTHER_CLASS_PREIMAGE.items():
        if (key[0], key[1]) not in set(map(tuple, actors)):
            raise ValueError("A fixed kmod metadata observer is absent")
        _, bits = policy.permissions(key[3], classes[key[3]])
        fixed[key] = sum(bits[name] for name in names)
    if actual != fixed:
        raise ValueError("Kmod preimage has an unapproved other-class permission")
    raw_rows, effective_rows = [], []
    for key, mask in sorted(fixed.items()):
        role, actor, target, cls = key
        source = selected[target]["source"]
        if raw.get((role, actor, source, cls), 0) != mask:
            raise ValueError("Kmod metadata preimage differs from the fixed old source")
        raw_rows.append([role, actor, source, target, cls, mask])
        for source_level in LEVELS:
            for target_level in LEVELS:
                before = policy.context_av(_context(role, actor, source_level),
                    _context("object_r", source, target_level), cls, classes[cls])
                after = policy.context_av(_context(role, actor, source_level),
                    _context("object_r", target, target_level), cls, classes[cls])
                if before != after:
                    raise ValueError("Kmod metadata preimage changed a category pair")
                effective_rows.append([role, actor, source, target, cls,
                                       source_level, target_level, before, after])
    return {"fixed_raw_rows": raw_rows, "effective_rows": effective_rows}

def derive(library, baseline, exported, here, output, export):
    contract(here)
    expected = _derive_aliases(library, baseline, exported, output, export)
    policy = ContextPolicy(library, baseline)
    lines = exported.read_text().splitlines()
    if _selected_transitions(lines) != sorted(FIXED_TRANSITIONS):
        raise ValueError("Kmod prelink contains an unapproved birth transition")
    expected["other_class_preimage"] = _other_class_preimage(
        policy, lines, expected["classes"], expected["actors"])
    raw = {tuple(row[:-1]): row[-1]
           for row in _raw_new_targets(policy, lines, expected["classes"], expected["actors"])}
    for role, actor, old, new, cls, before, after in expected["raw_te_samples"]:
        key = (role, actor, new, cls)
        if after:
            raw[key] = after
        else:
            raw.pop(key, None)
    expected["all_new_target_raw"] = [list(key) + [mask] for key, mask in sorted(raw.items())]
    expected["all_constraint_forms"] = sorted(line for line in lines if line.startswith(CONSTRAINTS))
    expected["selected_transitions"] = sorted(FIXED_TRANSITIONS | set(expected["transitions"]))
    expected["guard_vectors"] = _guard_vectors(policy, expected["classes"])
    expected["contract_sha256"] = hashlib.sha256((here / "native-kmod-static-source.json").read_bytes()).hexdigest()
    return expected


def verify(library, binary, exported, here, expected, export):
    value = contract(here)
    if hashlib.sha256((here / "native-kmod-static-source.json").read_bytes()).hexdigest() != expected["contract_sha256"]:
        raise ValueError("Kmod source changed after its actual derivation")
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    checks = _verify_aliases(policy, exported, expected)
    if _other_class_preimage(policy, lines, expected["classes"], expected["actors"]) != expected["other_class_preimage"]:
        raise ValueError("Kmod fixed metadata preimage changed after derivation")
    if sorted(line for line in lines if line.startswith(CONSTRAINTS)) != expected["all_constraint_forms"]:
        raise ValueError("Kmod aliases changed complete existing constraints")
    if _selected_transitions(lines) != expected["selected_transitions"]:
        raise ValueError("Kmod fixed birth acquired a missing or additional transition")
    if _raw_new_targets(policy, lines, expected["classes"], expected["actors"]) != expected["all_new_target_raw"]:
        raise ValueError("Kmod new target acquired an unmodelled raw permission or class")
    if _guard_vectors(policy, expected["classes"]) != expected["guard_vectors"]:
        raise ValueError("Kmod changed existing module, hardware, capability or generic-parent authority")

    complete = {
        (EXECUTOR, DIRECTORY, "dir"): {"getattr", "search", "open", "read", "setattr", "mounton"},
        ("kernel", DIRECTORY, "dir"): {"getattr", "search", "open", "read", "relabelto"},
        (PRODUCER, DIRECTORY, "dir"): {"getattr", "search", "open", "read", "write", "add_name"},
        (PRODUCER, CONFIG, "file"): {"getattr", "open", "read", "map", "create", "write", "setattr"},
        (EXECUTOR, CONFIG, "file"): {"getattr", "open", "read"},
        (EXECUTOR, DIRECTORY, "file"): set(),
        (PRODUCER, DIRECTORY, "file"): set(),
        (PRODUCER, CONFIG, "dir"): set(),
    }
    for (actor, target, cls), names in complete.items():
        _, bits = policy.permissions(cls, expected["classes"][cls])
        actual = policy.context_av(_context("r" if actor == "kernel" else "system_r", actor), _context("object_r", target),
                                   cls, expected["classes"][cls])
        if actual != sum(bits[name] for name in names):
            raise ValueError("Kmod normal operation/complement differs: " + actor + " " + target + " " + cls)
        checks.append([actor, target, cls, sorted(names), actual])
    objects = sorted(set(re.findall(r"\(roletype object_r (\w+)\)", "\n".join(lines))))
    _, fs_bits = policy.permissions("filesystem", expected["classes"]["filesystem"])
    for source in (DIRECTORY, CONFIG):
        for target in objects:
            actual = policy.context_av(_context("object_r", source), _context("object_r", target),
                                       "filesystem", expected["classes"]["filesystem"])
            wanted = fs_bits["associate"] if target == "tmpfs" else 0
            if actual != wanted:
                raise ValueError("Kmod inode escaped its exact tmpfs association")
            checks.append([source, target, "filesystem", actual])
    for target, cls, names in (
        (DIRECTORY, "dir", ["create", "remove_name", "rmdir", "rename", "setattr", "ioctl"]),
        (CONFIG, "file", ["append", "unlink", "link", "rename", "execute", "entrypoint", "ioctl"]),
        ("p4_linux_run_t", "dir", ["write", "add_name", "remove_name", "create"]),
        ("p4_linux_native_data_t", "file", ["write", "append", "create", "setattr"]),
    ):
        for level in LEVELS:
            if policy.context_av(_context("system_r", PRODUCER, level),
                                 _context("object_r", target), cls, names):
                raise ValueError("Kmod gained another output/lifecycle operation")
            checks.append([PRODUCER, target, cls, level, names, 0])
    # Both old readers and the new writer still meet the same MLS predicates.
    # All sixteen source/target combinations were measured above, never ORed
    # across category pairs. A mismatched writer category must remain denied.
    writes = []
    for actor, target, cls, names in (
        (EXECUTOR, DIRECTORY, "dir", ["setattr"]),
        (PRODUCER, DIRECTORY, "dir", ["write", "add_name"]),
        (PRODUCER, CONFIG, "file", ["write", "create", "setattr"]),
    ):
        _, bits = policy.permissions(cls, names)
        for level in LEVELS:
            actual = policy.context_av(_context("system_r", actor, level),
                                       _context("object_r", target), cls, names)
            wanted = sum(bits[name] for name in names) if level == "s0" else 0
            if actual != wanted:
                raise ValueError("Kmod normal writes escaped the admitted s0 category")
            writes.append([actor, target, cls, level, actual])
    return {
        "schema": "droidloom.native-kmod-static-policy-proof.v1",
        "source_contract_sha256": expected["contract_sha256"],
        "derived_alias_policy_sha256": expected["derived_sha256"],
        "alias_preserver_sha256": hashlib.sha256((here / "derive_preserved_alias_policy.py").read_bytes()).hexdigest(),
        "verifier_sha256": hashlib.sha256((here / "derive_native_kmod_static_policy.py").read_bytes()).hexdigest(),
        "aliases": ALIASES,
        "separately_verified_consumers": [TMPFILES],
        "new_types": [DIRECTORY, CONFIG],
        "new_roles": [],
        "alias_model": "raw-te-with-fixed-inert-relabel-guards",
        "relabel_guard_proof": expected["relabel_guard_proof"],
        "other_class_preimage": expected["other_class_preimage"],
        "preserved_actor_object_vectors": len(expected["samples"]),
        "preserved_raw_te_vectors": len(expected["raw_te_samples"]),
        "preserved_mcs_source_target_vectors": len(expected["mcs_effective_samples"]),
        "preserved_transitions": len(expected["transitions"]),
        "all_ranges_constraint_target_checks": expected["constraint_target_checks"],
        "complete_new_target_raw_vectors": len(expected["actors"]) * 2 * len(expected["classes"]),
        "unchanged_authority_vectors": len(expected["guard_vectors"]),
        "fixed_named_transitions": sorted(FIXED_TRANSITIONS),
        "extra_permissions": [[*key, sorted(names)] for key, names in sorted(EXTRA.items())],
        "normal_dropin": value["dropin"],
        "early_directory": value["early_directory"],
        "normal_unit_and_elf_unchanged": True,
        "runtime_directory_preserved": True,
        "generic_run_write_added": False,
        "device_creation_added": False,
        "startup_write_vectors": writes,
        "file_contexts": verify_file_contexts(here, exported.parent),
        "permission_checks": len(checks),
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
        "runtime_qualified": False,
    }


def verify_file_contexts(here, work):
    contract(here)
    path = work / "kmod-static-file-contexts"
    names = ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
             "linux-service-file_contexts", "linux-initial-calibration-file_contexts")
    path.write_bytes(b"".join((here / name).read_bytes() for name in names))
    class Option(ctypes.Structure):
        _fields_ = [("type", ctypes.c_int), ("value", ctypes.c_char_p)]
    lib = ctypes.CDLL("libselinux.so.1", use_errno=True)
    lib.selabel_open.argtypes = [ctypes.c_uint, ctypes.POINTER(Option), ctypes.c_uint]
    lib.selabel_open.restype = ctypes.c_void_p
    lib.selabel_lookup_raw.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p), ctypes.c_char_p, ctypes.c_int]
    lib.selabel_lookup_raw.restype = ctypes.c_int
    lib.selabel_close.argtypes = [ctypes.c_void_p]
    lib.freecon.argtypes = [ctypes.c_void_p]
    handle = lib.selabel_open(0, ctypes.byref(Option(3, str(path).encode())), 1)
    if not handle:
        raise OSError(ctypes.get_errno(), "Cannot open normal kmod context matcher")
    def lookup(filename, mode, allow_unmatched=False):
        result = ctypes.c_char_p()
        if lib.selabel_lookup_raw(handle, ctypes.byref(result), filename.encode(), mode):
            error = ctypes.get_errno()
            if allow_unmatched and error == 2:
                return None
            raise OSError(error, "Kmod context lookup failed: " + filename)
        try:
            return result.value.decode().split(":")[2]
        finally:
            lib.freecon(result)
    checks = []
    try:
        for filename, kind, wanted in (
            ("/run/tmpfiles.d", stat.S_IFDIR, DIRECTORY),
            ("/run/tmpfiles.d/static-nodes.conf", stat.S_IFREG, CONFIG),
        ):
            for mode in (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK):
                actual = lookup(filename, mode, allow_unmatched=(mode != kind))
                if ((mode == kind and actual != wanted) or
                        (mode != kind and actual in (DIRECTORY, CONFIG))):
                    raise ValueError("Kmod context escaped the exact inode kind")
                checks.append([filename, mode, actual])
        for filename, mode, wanted in (
            ("/run/tmpfilesX.d", stat.S_IFDIR, "p4_linux_rootdir_t"),
            ("/run/tmpfiles.d-extra", stat.S_IFDIR, "p4_linux_rootdir_t"),
            ("/run/tmpfiles.d/sub", stat.S_IFDIR, "p4_linux_rootdir_t"),
            ("/run/tmpfiles.d/static-nodesXconf", stat.S_IFREG, "p4_linux_native_data_t"),
            ("/run/tmpfiles.d/static-nodes.conf.extra", stat.S_IFREG, "p4_linux_native_data_t"),
            ("/run/tmpfiles.d/other.conf", stat.S_IFREG, "p4_linux_native_data_t"),
            ("/run/tmpfiles.d/sub/static-nodes.conf", stat.S_IFREG, "p4_linux_native_data_t"),
            ("/usr/lib/systemd/system/kmod-static-nodes.service.d", stat.S_IFDIR, "p4_linux_unit_directory_t"),
            ("/" + DROPIN_PATH, stat.S_IFREG, "p4_linux_unit_file_t"),
        ):
            actual = lookup(filename, mode)
            if actual != wanted:
                raise ValueError("Kmod context changed an adjacent normal object: " + filename)
            checks.append([filename, mode, actual])
    finally:
        lib.selabel_close(handle)
    return {"checks": len(checks),
            "lookup_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
            "composed_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
