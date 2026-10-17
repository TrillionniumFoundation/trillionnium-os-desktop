#!/usr/bin/env python3
"""Opt-in, pinned-consumer path projection. This is not a security boundary."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = "a01-component-path-projection/3"
FILES = ("profile.py", "run.py", "rustc-wrapper.py", "cargo-metadata-wrapper.py")
HELPERS = ("profile.py", "rustc-wrapper.py", "cargo-metadata-wrapper.py")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f"not a private regular file: {path}")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read()
        after = os.fstat(fd)
        if identity(before) != identity(after):
            raise ValueError(f"input changed while reading: {path}")
        if identity(after) != identity(os.stat(path, follow_symlinks=False)):
            raise ValueError(f"input pathname changed while reading: {path}")
        return data, identity(after)
    finally:
        os.close(fd)


def identity(info):
    return {name: getattr(info, name) for name in
            ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode", "st_nlink")}


def exclusive(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def code_hashes(directory):
    return {name: digest(regular(directory / name)[0]) for name in FILES}


def compiler_argv(incoming, policy):
    """Keep all OSDK/Cargo arguments; enforce the same map used by metadata.

    OSDK's global RUSTFLAGS append does not reach its already-built run/test
    action configs. The compiler wrapper is the final reliable insertion point.
    """
    if not incoming:
        raise ValueError("missing compiler executable")
    flag = f"--remap-path-prefix={policy['real_root']}={policy['virtual_root']}"
    result = list(incoming)
    delimiter = result.index("--") if "--" in result else len(result)
    options = result[:delimiter]
    for index, argument in enumerate(options):
        value = None
        if argument.startswith("--remap-path-prefix="):
            value = argument.split("=", 1)[1]
        elif argument == "--remap-path-prefix" and index + 1 < len(options):
            value = options[index + 1]
        if value is None:
            continue
        before, separator, after = value.partition("=")
        real = policy["real_root"]
        overlaps = before == real or before.startswith(real + "/") or real.startswith(before.rstrip("/") + "/")
        if separator and overlaps and (before, after) != (real, policy["virtual_root"]):
            raise ValueError("conflicting compiler path map overlaps this profile's source root")
    if flag not in options:
        # Preserve even an explicit end-of-options delimiter and source filename.
        index = result.index("--") if "--" in result else len(result)
        result.insert(index, flag)
    return result


def compiler_unit(arguments, environment):
    """Describe a Cargo rustc unit without guessing artifact filename hashes."""
    options = arguments[1:arguments.index("--")] if "--" in arguments else arguments[1:]
    codegen = []
    values = {}
    ambiguous = False
    index = 0
    while index < len(options):
        argument = options[index]
        if (argument == "--codegen" and index + 1 < len(options)
                and options[index + 1].startswith("metadata=")) or argument.startswith("--codegen=metadata="):
            raise ValueError("unsupported Cargo metadata option spelling")
        if argument == "-C":
            if index + 1 == len(options):
                raise ValueError("incomplete codegen argument")
            codegen.append((index + 2, options[index + 1], False))
            index += 2
            continue
        if argument.startswith("-C") and len(argument) > 2:
            codegen.append((index + 1, argument[2:], True))
        if argument in ("--crate-name", "--crate-type", "--target", "--out-dir"):
            if index + 1 == len(options) or argument in values:
                ambiguous = True
            else:
                values[argument] = options[index + 1]
        index += 1
    salts = [entry for entry in codegen if entry[1].startswith("metadata=")]
    if not salts:
        return None
    if ambiguous or len(salts) != 1 or "--crate-name" not in values or "--out-dir" not in values:
        raise ValueError("ambiguous Cargo compiler unit identity")
    extras = [entry[1].split("=", 1)[1] for entry in codegen if entry[1].startswith("extra-filename=")]
    if len(extras) != 1:
        raise ValueError("Cargo compiler unit must have one artifact suffix")
    manifest = environment.get("CARGO_MANIFEST_DIR")
    name = environment.get("CARGO_PKG_NAME")
    version = environment.get("CARGO_PKG_VERSION")
    if not manifest or not os.path.isabs(manifest) or not name or not version:
        raise ValueError("Cargo compiler unit lacks package provenance")
    return {"manifest": manifest, "package": name, "version": version,
            "crate": values["--crate-name"], "crate_type": values.get("--crate-type"),
            "target": values.get("--target", "host"), "out_dir": values["--out-dir"],
            "extra_filename": extras[0], "incoming_metadata": salts[0][1].split("=", 1)[1],
            "salt_argument": salts[0][0], "salt_combined": salts[0][2]}


def artifact_identity(path):
    info = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("compiler artifact is not a regular file")
    # Cargo may create another hard link after rustc returns. That changes ctime
    # and nlink without changing the completed producer's bytes or inode.
    return {key: getattr(info, key) for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns")}


def completed_artifacts(unit):
    if unit is None:
        return {}
    basename = unit["crate"] + unit["extra_filename"]
    names = ["lib" + basename + suffix for suffix in (".rlib", ".rmeta", ".so", ".a")]
    names.append(basename)
    result = {}
    for name in names:
        path = os.path.abspath(os.path.join(unit["out_dir"], name))
        try:
            result[path] = artifact_identity(path)
        except FileNotFoundError:
            pass
    return result


def canonical_compiler_metadata(arguments, environment, cwd, policy, history):
    """Project local Cargo crate disambiguators; retain real artifact filenames.

    The descriptor includes every compiler argument except the original salt,
    output naming/location and incremental cache location. Externs bind to
    successful producers, rather than stripping filename hashes heuristically.
    """
    result = list(arguments)
    unit = compiler_unit(arguments, environment)
    if unit is None:
        return result, None
    real, virtual = policy["real_root"], policy["virtual_root"]
    local = unit["manifest"] == real or unit["manifest"].startswith(real + "/")
    if not local:
        identity = {key: unit[key] for key in
                    ("manifest", "package", "version", "crate", "crate_type", "target", "incoming_metadata")}
        unit.update(scope="cargo-original", canonical_id=digest(json.dumps(identity, sort_keys=True).encode()),
                    effective_metadata=unit["incoming_metadata"])
        return result, unit

    def normalize(value):
        # Only absolute path prefixes and path-valued '=' arguments. Do not
        # rewrite a neighboring directory or arbitrary quoted cfg string.
        return re.sub(r"(^|=)" + re.escape(real) + r"(?=$|[/=])",
                      lambda match: match.group(1) + virtual, value)

    if environment.get("OUT_DIR"):
        raise ValueError("local build-script OUT_DIR inputs are outside this pinned profile")
    if any(re.search(r"/target/(?:[^/]+/)*build/[^/]+-[0-9a-f]{8,}/out(?:/|$)", argument)
           for argument in result):
        raise ValueError("local build-script artifact paths are outside this pinned profile")

    def dependency(value):
        alias, separator, filename = value.partition("=")
        if not separator:
            if alias == "proc_macro" and policy.get("rustc_identity"):
                return alias + "=<fixed-sysroot:" + policy["rustc_identity"] + ">"
            raise ValueError("local compiler unit has an implicit extern without producer provenance")
        filename = os.path.abspath(filename)
        matches = {entry["unit"]["canonical_id"] for entry in history
                   if entry.get("state") == "completed" and entry.get("returncode") == 0
                   and filename in entry.get("artifacts", {})
                   and entry["artifacts"][filename] == artifact_identity(filename)}
        if len(matches) != 1:
            raise ValueError(f"extern lacks one unchanged successful producer: {alias}")
        return alias + "=<producer:" + matches.pop() + ">"

    descriptor_args = []
    options_end = result.index("--") if "--" in result else len(result)
    index = 1
    while index < len(result):
        argument = result[index]
        if index < options_end and argument in ("-C", "--codegen"):
            if index + 1 >= options_end:
                raise ValueError("incomplete codegen option")
            value = result[index + 1]
            if value.startswith(("metadata=", "extra-filename=")):
                index += 2
                continue
            descriptor_args.append("-C" + ("incremental=<enabled>" if value.startswith("incremental=") else normalize(value)))
            index += 2
            continue
        if index < options_end and argument.startswith("-C") and len(argument) > 2:
            value = argument[2:]
            if value.startswith(("metadata=", "extra-filename=")):
                index += 1
                continue
            descriptor_args.append("-C" + ("incremental=<enabled>" if value.startswith("incremental=") else normalize(value)))
            index += 1
            continue
        if index < options_end and argument == "--out-dir":
            descriptor_args.extend((argument, "<cargo-output-directory>"))
            index += 2
            continue
        if index < options_end and argument == "--extern":
            descriptor_args.extend((argument, dependency(result[index + 1])))
            index += 2
            continue
        if index < options_end and argument.startswith("--extern="):
            descriptor_args.append("--extern=" + dependency(argument.split("=", 1)[1]))
            index += 1
            continue
        descriptor_args.append(normalize(argument))
        index += 1
    import tomllib
    manifest = tomllib.loads(regular(Path(unit["manifest"]) / "Cargo.toml")[0].decode())

    def manifest_paths(value):
        if isinstance(value, dict):
            return {key: normalize(entry) if key in ("path", "workspace") and isinstance(entry, str)
                    else manifest_paths(entry) for key, entry in value.items()}
        if isinstance(value, list):
            return [manifest_paths(entry) for entry in value]
        return value

    descriptor = {"schema": "a01-local-cargo-unit/1", "manifest": normalize(unit["manifest"]),
                  "manifest_sha256": digest(json.dumps(manifest_paths(manifest), sort_keys=True).encode()),
                  "package": unit["package"], "version": unit["version"], "crate": unit["crate"],
                  "crate_type": unit["crate_type"], "target": unit["target"],
                  "compiler": policy.get("rustc_identity"), "cwd": normalize(cwd), "arguments": descriptor_args}
    canonical = digest(json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode())
    for entry in history:
        other = entry.get("unit")
        if (other and other.get("scope") == "canonical-local" and other["canonical_id"] == canonical
                and other["incoming_metadata"] != unit["incoming_metadata"]):
            raise ValueError("distinct Cargo units collide in the canonical local descriptor")
    argument = "metadata=" + canonical
    result[unit["salt_argument"]] = "-C" + argument if unit["salt_combined"] else argument
    unit.update(scope="canonical-local", canonical_id=canonical,
                effective_metadata=canonical, descriptor=descriptor)
    return result, unit


def materialize_helpers(destination, source):
    destination.mkdir(mode=0o700)
    for name in HELPERS:
        raw = regular(source / name)[0]
        exclusive(destination / name, raw, 0o500 if "wrapper" in name else 0o400)


def helper_hashes(root):
    helpers = root / "helpers"
    values = {}
    for name in HELPERS:
        raw, observed = regular(helpers / name)
        if "wrapper" in name and not observed["st_mode"] & stat.S_IXUSR:
            raise ValueError("profile helper is not executable")
        values[name] = digest(raw)
    return values


def safe_root(path):
    path = Path(os.path.abspath(path))
    if path.resolve() != path:
        raise ValueError("profile/source roots must be real paths, without symlink aliases")
    if any(char.isspace() or char in "=#@%" for char in str(path)):
        raise ValueError("this pinned profile requires simple absolute paths")
    return path


def snapshot(profile_root):
    if profile_root.is_symlink() or not profile_root.is_dir():
        raise ValueError("profile directory is not a real directory")
    if set(os.listdir(profile_root)) != {"owner.json", "lock", "virtual-asterinas", "helpers"}:
        raise ValueError("foreign or incomplete profile directory")
    virtual = profile_root / "virtual-asterinas"
    if virtual.is_symlink() or not virtual.is_dir() or set(os.listdir(virtual)) != {"Components.toml"}:
        raise ValueError("foreign virtual input directory")
    helpers = profile_root / "helpers"
    if helpers.is_symlink() or not helpers.is_dir() or set(os.listdir(helpers)) != set(HELPERS):
        raise ValueError("foreign helper closure")
    values = {".": identity(profile_root.stat()), "virtual-asterinas": identity(virtual.stat()),
              "helpers": identity(helpers.stat())}
    for name in ("owner.json", "lock", "virtual-asterinas/Components.toml", *("helpers/" + name for name in HELPERS)):
        raw, observed = regular(profile_root / name)
        values[name] = {"identity": observed, "sha256": digest(raw)}
    return values


def graph_ids(data):
    ids = [package["id"] for package in data["packages"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate package IDs")
    known = set(ids)
    refs = list(data["workspace_members"]) + list(data.get("workspace_default_members", []))
    resolve = data.get("resolve")
    if resolve is not None:
        if resolve.get("root") is not None:
            refs.append(resolve["root"])
        nodes = resolve["nodes"]
        node_ids = [node["id"] for node in nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("duplicate resolve nodes")
        for node in nodes:
            refs.append(node["id"])
            refs.extend(node["dependencies"])
            refs.extend(dep["pkg"] for dep in node["deps"])
    if not set(refs) <= known:
        raise ValueError("metadata graph contains dangling package IDs")
    return ids


def project_metadata(data, real, virtual, component_bytes):
    import tomllib
    real, virtual = str(real), str(virtual)
    if data["workspace_root"] != real or data.get("version") != 1:
        raise ValueError("unexpected metadata workspace or format")
    graph_ids(data)

    def remap(value):
        if value == real or value.startswith(real + "/"):
            return virtual + value[len(real):]
        prefix = "path+file://" + real
        if value == prefix or any(value.startswith(prefix + boundary) for boundary in ("/", "#", "@")):
            return "path+file://" + virtual + value[len(prefix):]
        return value

    def walk(value):
        if isinstance(value, str):
            return remap(value)
        if isinstance(value, list):
            return [walk(entry) for entry in value]
        if isinstance(value, dict):
            return {key: walk(entry) for key, entry in value.items()}
        return value

    mapped = walk(data)
    original_ids, mapped_ids = graph_ids(data), graph_ids(mapped)
    if any(value.startswith("path+file://" + real + boundary) for value in mapped_ids for boundary in ("/", "#", "@")):
        raise ValueError("unmapped package ID under the real source root")
    if mapped_ids != [remap(value) for value in original_ids]:
        raise ValueError("metadata ID projection is not coherent")
    configured = tomllib.loads(component_bytes.decode())["components"]
    if not isinstance(configured, dict) or any(
            not isinstance(value, dict) or set(value) != {"name"} or not isinstance(value["name"], str)
            for value in configured.values()):
        raise ValueError("unexpected pinned Components.toml structure")
    names = {value["name"] for value in configured.values()}
    checks = []
    component_names = set()
    for original, projected in zip(data["packages"], mapped["packages"]):
        if not any(dep["name"] == "component" for dep in original["dependencies"]):
            continue
        name = original["name"]
        if name in component_names or not original["id"].startswith("path+file://"):
            raise ValueError("ambiguous or non-path component identity")
        component_names.add(name)
        # This is the pinned macro's exact membership predicate. Preserve it
        # rather than bypassing its missing-component check through ID-only edits.
        before, after = real in original["id"], virtual in projected["id"]
        if before != after:
            raise ValueError("component workspace membership changed")
        if before and name not in names:
            raise ValueError(f"component missing from Components.toml: {name}")
        checks.append({"name": name, "in_workspace_before": before,
                       "in_workspace_after": after, "listed": name in names})
    return mapped, checks
