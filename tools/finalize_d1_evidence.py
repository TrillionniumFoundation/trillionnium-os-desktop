#!/usr/bin/env python3
"""Validate D1 results and stage one strict, portable evidence artifact."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from gate_evidence_envelope import build_envelope, load_json_strict, write_envelope

CHUNK_BYTES = 1024 * 1024
MAX_RAW_EVIDENCE_BYTES = 4 * 1024 * 1024
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _has_symlink_component(path: Path) -> bool:
    """Check a raw CLI path before ``resolve`` can erase a symlink."""

    lexical = path if path.is_absolute() else Path.cwd() / path
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component in {lexical.anchor, "", "."}:
            continue
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ValueError(f"cannot inspect path component: {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _reject_symlink_path(path: Path, label: str) -> None:
    if _has_symlink_component(path):
        raise ValueError(f"{label} path contains a symlink: {path}")


def _open_regular(path: Path, label: str) -> int:
    """Open a regular input without following a late symlink replacement."""

    _reject_symlink_path(path, label)
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | _O_CLOEXEC | _O_NONBLOCK | _O_NOFOLLOW,
        )
    except OSError as error:
        if error.errno == errno.ENOENT:
            raise FileNotFoundError(f"{label} is absent: {path}") from error
        raise ValueError(f"{label} is absent or unreadable: {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"{label} is not a regular file: {path}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_text(path: Path, label: str) -> str:
    descriptor = _open_regular(path, label)
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _copy_stream_atomic(source: int, destination: Path, label: str) -> None:
    """Copy an already-open source to a regular destination atomically."""

    temporary_descriptor = -1
    temporary: Path | None = None
    try:
        _reject_symlink_path(destination, label)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if _has_symlink_component(destination.parent) or destination.is_symlink():
            raise ValueError(f"{label} path contains a symlink: {destination}")
        temporary_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(source, "rb", closefd=True) as source_stream:
            source = -1
            with os.fdopen(
                temporary_descriptor, "wb", closefd=True
            ) as destination_stream:
                temporary_descriptor = -1
                shutil.copyfileobj(source_stream, destination_stream, CHUNK_BYTES)
                destination_stream.flush()
                try:
                    os.fsync(destination_stream.fileno())
                except OSError:
                    pass
        if _has_symlink_component(destination) or destination.is_symlink():
            raise ValueError(f"{label} path became a symlink: {destination}")
        os.replace(temporary, destination)
        temporary = None
    finally:
        if source >= 0:
            os.close(source)
        if temporary_descriptor >= 0:
            os.close(temporary_descriptor)
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _write_bytes_atomic(destination: Path, data: bytes, label: str) -> None:
    """Write bounded evidence bytes without following a destination link."""

    temporary_descriptor = -1
    temporary: Path | None = None
    try:
        _reject_symlink_path(destination, label)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if _has_symlink_component(destination.parent) or destination.is_symlink():
            raise ValueError(f"{label} path contains a symlink: {destination}")
        temporary_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(temporary_descriptor, "wb", closefd=True) as stream:
            temporary_descriptor = -1
            stream.write(data)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                pass
        if _has_symlink_component(destination) or destination.is_symlink():
            raise ValueError(f"{label} path became a symlink: {destination}")
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary_descriptor >= 0:
            os.close(temporary_descriptor)
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = _open_regular(path, "hashed file")
    try:
        stream = os.fdopen(descriptor, "rb", closefd=True)
        descriptor = -1
    except BaseException:
        os.close(descriptor)
        raise
    try:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    finally:
        stream.close()
    return digest.hexdigest()


def require_git_sha(value: str | None, label: str) -> str:
    if value is None or GIT_SHA_RE.fullmatch(value) is None or set(value) == {"0"}:
        raise ValueError(f"{label} is not a non-null lowercase Git object id")
    return value


def git_output(repository: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments],
        cwd=repository,
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def load_json(path: Path) -> dict[str, Any]:
    descriptor = _open_regular(path, "JSON input")
    try:
        stream = os.fdopen(descriptor, "r", encoding="utf-8", closefd=True)
        descriptor = -1
    except BaseException:
        os.close(descriptor)
        raise
    try:
        value = load_json_strict(stream)
    finally:
        stream.close()
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def require_true(mapping: dict[str, Any], key: str) -> None:
    if mapping.get(key) is not True:
        raise ValueError(f"required true field {key!r} is absent: {mapping}")


def require_false(mapping: dict[str, Any], key: str) -> None:
    if mapping.get(key) is not False:
        raise ValueError(f"required false field {key!r} is absent: {mapping}")


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(f"required evidence file is absent or unsafe: {source}")
    descriptor = _open_regular(source, "evidence source")
    source_descriptor = descriptor
    descriptor = -1
    _copy_stream_atomic(source_descriptor, destination, "evidence destination")


def copy_optional_bounded(source: Path, destination: Path) -> None:
    _reject_symlink_path(source, "optional evidence source")
    _reject_symlink_path(destination, "optional evidence destination")
    if not source.is_file() or source.is_symlink():
        return
    descriptor = _open_regular(source, "optional evidence source")
    try:
        source_size = os.fstat(descriptor).st_size
        if source_size <= MAX_RAW_EVIDENCE_BYTES:
            source_descriptor = descriptor
            descriptor = -1
            _copy_stream_atomic(
                source_descriptor, destination, "optional evidence destination"
            )
            return
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            stream.seek(-MAX_RAW_EVIDENCE_BYTES, os.SEEK_END)
            data = stream.read()
        _write_bytes_atomic(
            destination.with_suffix(destination.suffix + ".tail"),
            data,
            "optional evidence tail destination",
        )
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def tracked_source_manifest(
    repository: Path,
    *,
    tested_sha: str | None = None,
    tested_tree_sha: str | None = None,
) -> dict[str, Any]:
    """Hash exactly the clean tree object that the gate said it tested.

    The qualification builds create ignored outputs, so a status check alone
    is not enough: a tracked source file could be edited after identities were
    captured while retaining the same ``HEAD``.  Enumerating the tested tree
    and comparing each worktree blob closes that time-of-check gap.
    """

    tested_sha = require_git_sha(
        tested_sha or os.environ.get("TESTED_SHA"), "TESTED_SHA"
    )
    tested_tree_sha = require_git_sha(
        tested_tree_sha or os.environ.get("TESTED_TREE_SHA"), "TESTED_TREE_SHA"
    )
    current_head = git_output(repository, "rev-parse", "HEAD")
    current_tree = git_output(repository, "rev-parse", "HEAD^{tree}")
    if current_head != tested_sha or current_tree != tested_tree_sha:
        raise ValueError(
            "repository HEAD/tree drifted after qualification identities were captured"
        )
    status = git_output(
        repository, "status", "--porcelain=v1", "--untracked-files=all"
    )
    if status:
        raise ValueError(f"repository worktree is dirty after qualification: {status}")
    staged = git_output(
        repository, "diff", "--cached", "--name-status", "--no-renames"
    )
    if staged:
        raise ValueError(f"repository index is dirty after qualification: {staged}")

    encoded = subprocess.check_output(
        ["git", "ls-tree", "-r", "-z", "--full-tree", tested_sha],
        cwd=repository,
    )
    entries: list[tuple[str, str]] = []
    for item in encoded.split(b"\0"):
        if not item:
            continue
        try:
            header, raw_name = item.split(b"\t", 1)
            _mode, object_type, blob = header.decode("ascii").split(" ", 2)
            name = raw_name.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("tested Git tree contains an invalid source entry") from error
        if object_type != "blob" or not name or name.startswith("/") or ".." in name.split("/"):
            raise ValueError(f"tested Git tree contains an unsafe non-file path: {name!r}")
        entries.append((name, blob))
    names = sorted((name for name, _blob in entries), key=os.fsencode)
    if len(names) != len(set(names)):
        raise ValueError("tested Git tree contains duplicate source paths")
    files: dict[str, str] = {}
    expected_blobs = dict(entries)
    for name in names:
        path = repository / name
        _reject_symlink_path(path, "tracked source input")
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"tracked source input is absent or unsafe: {name}")
        actual_blob = git_output(repository, "hash-object", "--no-filters", "--", name)
        if actual_blob != expected_blobs[name]:
            raise ValueError(
                f"tracked source input drifted from tested tree: {name}"
            )
        files[name] = sha256(path)
    canonical = json.dumps(files, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return {
        "schema": "trillionnium.desktop.source-input-digests.v1",
        "tested_sha": tested_sha,
        "tree_sha": tested_tree_sha,
        "file_count": len(files),
        "files_sha256": hashlib.sha256(canonical).hexdigest(),
        "files": files,
    }


def rootfs_entries(path: Path) -> dict[str, dict[str, Any]]:
    document = load_json(path)
    if document.get("schema") != "trillionnium.desktop.d1-rootfs-manifest.v1":
        raise ValueError(f"unexpected rootfs manifest schema: {path}")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"rootfs manifest entries are not a list: {path}")
    output: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError(f"invalid rootfs manifest entry: {path}")
        name = entry["path"]
        if name in output:
            raise ValueError(f"duplicate rootfs path {name!r}: {path}")
        output[name] = entry
    if document.get("entry_count") != len(output):
        raise ValueError(f"rootfs manifest entry count is inconsistent: {path}")
    return output


def validate_results(root: Path) -> dict[str, Any]:
    evidence = root / "evidence"
    pipeline = load_json(root / "pipeline-result.json")
    reproducibility = load_json(root / "reproducibility-result.json")
    boot = load_json(root / "qemu/boot-result.json")
    acceptance = load_json(root / "qemu/acceptance.json")
    host_tool = load_json(evidence / "e2fsprogs-host-tool-result.json")
    product_check = load_json(evidence / "product-daemon-self-check-host.json")
    qualification_check = load_json(
        evidence / "d1-qualification-self-check-host.json"
    )
    host_environment = load_json(evidence / "host-toolchain.json")

    if pipeline.get("status") != "PASS":
        raise ValueError("D1 pipeline is not a pass")
    if reproducibility.get("status") != "PASS_TWO_INDEPENDENT_BUILDS":
        raise ValueError("D1 same-run reproducibility result is not a pass")
    require_true(reproducibility, "reproducible")
    if boot.get("status") != "PASS_QEMU_PID1_WAYLAND_AND_AGENT_PORT":
        raise ValueError("D1 QEMU boot result is not a pass")
    if acceptance.get("schema") != "trillionnium.desktop.d1-acceptance.v2":
        raise ValueError("D1 acceptance result has the wrong schema")
    if acceptance.get("status") != "PASS":
        raise ValueError("D1 acceptance result is not a pass")
    if host_tool.get("status") != "PASS_PINNED_ISOLATED_HOST_TOOL":
        raise ValueError("pinned e2fsprogs result is not a pass")
    require_true(product_check, "ok")
    require_false(product_check, "product_handler_connected")
    require_false(product_check, "fixture_handler_linked")
    if qualification_check.get("status") != "PASS":
        raise ValueError("D1 qualification fixture self-check is not a pass")
    require_true(qualification_check, "qualification_only")
    require_false(qualification_check, "product_handler_connected")
    if host_environment.get("schema") != "trillionnium.desktop.d1-host-toolchain.v1":
        raise ValueError("D1 host toolchain evidence has the wrong schema")

    claims = boot.get("claims")
    if not isinstance(claims, dict):
        raise ValueError("D1 boot claims are absent")
    for key in (
        "systemd_booted",
        "udev_active",
        "dbus_active",
        "logind_active",
        "headless_wayland_active",
        "agent_port_default_disabled",
        "agent_port_pid1_activation_validated",
        "unauthorized_peer_denied",
        "authorized_fixture_request",
        "per_connection_teardown",
        "connection_kill_recovered",
    ):
        require_true(claims, key)
    for key in (
        "network_enabled",
        "servo_started",
        "visible_window_created",
        "secure_boot_qualified",
    ):
        require_false(claims, key)
    require_true(boot, "release_marker_absent")
    require_true(boot, "clean_poweroff")

    agent = acceptance.get("agent_port")
    if not isinstance(agent, dict):
        raise ValueError("D1 acceptance AgentPort evidence is absent")
    for key in (
        "qualification_only_server",
        "product_daemon_fixture_free",
        "marker_removed_before_poweroff",
        "socket_removed_before_poweroff",
    ):
        require_true(agent, key)
    require_false(agent, "product_handler_connected")
    require_false(agent, "product_daemon_exercised_for_requests")
    if agent.get("qualification_server_exec") != (
        "/usr/libexec/hepta-agent-d1-fixture --mode server"
    ):
        raise ValueError("D1 qualification server command is not exact")

    return {
        "pipeline": pipeline,
        "reproducibility": reproducibility,
        "boot": boot,
        "acceptance": acceptance,
        "host_tool": host_tool,
        "host_environment": host_environment,
        "product_check": product_check,
        "qualification_check": qualification_check,
    }


_GIT_MUTATING_SUBCOMMANDS = frozenset({"push", "update-ref", "receive-pack"})
_GIT_MUTATING_EXECUTABLES = frozenset(
    {"git-push", "git-update-ref", "git-receive-pack"}
)
_GIT_GLOBAL_OPTIONS_WITH_ARGS = frozenset(
    {
        "-C",
        "-c",
        "--config-env",
        "--exec-path",
        "--git-dir",
        "--namespace",
        "--super-prefix",
        "--work-tree",
    }
)


def _shell_command_words(text: str) -> list[list[str]]:
    """Tokenize shell-ish workflow lines while retaining command boundaries.

    This is deliberately a small scanner rather than a shell evaluator.  It
    understands quoted paths and backslash-newline continuations, which are
    the forms that let ``git -C <path> push`` evade a plain substring check.
    Malformed/unbalanced shell text falls back to conservative whitespace
    tokenization so the mutation guard still fails closed.
    """

    continued = re.sub(r"\\\r?\n", " ", text)
    commands: list[list[str]] = []
    current: list[str] = []
    try:
        lexer = shlex.shlex(
            continued,
            posix=True,
            punctuation_chars=";&|()\n",
        )
        lexer.whitespace_split = True
        lexer.commenters = ""
        separators = {";", "&&", "||", "|", "(", ")", "\n"}
        for word in lexer:
            if word in separators:
                if current:
                    commands.append(current)
                    current = []
            else:
                current.append(word)
    except ValueError:
        # Unbalanced quoting in a workflow is invalid YAML/shell anyway.  Use
        # conservative whitespace chunks so a mutation cannot hide behind it.
        for segment in re.split(r"(?:\r?\n|&&|\|\||[;|])", continued):
            words = re.findall(r"[^\s]+", segment)
            if words:
                commands.append(words)
        return commands
    if current:
        commands.append(current)
    return commands


def workflow_contains_git_mutation(text: str, *, _depth: int = 0) -> bool:
    """Return whether workflow text contains a Git ref/transport mutation.

    The check covers Git global options (including ``-C``/``--git-dir``),
    line continuations, receive helper executables, and bounded nested shell
    fragments.  Malformed shell text is handled conservatively by the
    tokenizer fallback above.
    """

    for words in _shell_command_words(text):
        for index, word in enumerate(words):
            executable = word.rsplit("/", 1)[-1]
            if executable in _GIT_MUTATING_EXECUTABLES:
                return True
            if executable not in {"git", "git.exe"}:
                continue
            cursor = index + 1
            while cursor < len(words):
                argument = words[cursor]
                option = argument.split("=", 1)[0]
                if argument == "--":
                    cursor += 1
                    continue
                if argument in _GIT_MUTATING_SUBCOMMANDS:
                    return True
                if not argument.startswith("-"):
                    break
                if "=" not in argument and option in _GIT_GLOBAL_OPTIONS_WITH_ARGS:
                    cursor += 2
                else:
                    cursor += 1
        # A workflow can pass a shell fragment through ``bash -c``/``sh -c``.
        # ``shlex`` returns that fragment as one quoted token, so inspect a
        # bounded number of nested fragments instead of relying on a literal
        # ``git push`` substring in the outer command.
        if _depth < 2:
            for word in words:
                if (
                    any(character.isspace() for character in word)
                    and "git" in word
                    and workflow_contains_git_mutation(word, _depth=_depth + 1)
                ):
                    return True
    return False


def validate_workflow(repository: Path) -> dict[str, str]:
    workflow = repository / ".github/workflows/d1-final-qualification.yml"
    text = _read_text(workflow, "qualification workflow")
    trigger = text.split("\npermissions:\n", 1)[0]
    if "paths:" in trigger or "paths-ignore:" in trigger:
        raise ValueError("permanent D1 promotion workflow must not use path filters")
    for marker in ("pull_request:", "push:", "branches: [main]"):
        if marker not in trigger:
            raise ValueError(f"permanent D1 workflow lacks trigger marker {marker!r}")
    if "permissions:\n  contents: read" not in text:
        raise ValueError("permanent D1 workflow is not read-only")
    if workflow_contains_git_mutation(text) or "gh workflow run" in text:
        raise ValueError("permanent D1 workflow contains branch mutation")
    return {
        "path": str(workflow.relative_to(repository)),
        "sha256": sha256(workflow),
    }


def stage_artifact(
    repository: Path,
    root: Path,
    artifact: Path,
    results: dict[str, Any],
) -> None:
    # Keep this guard here as well as in ``main``: callers and tests may use
    # ``stage_artifact`` directly, and resolving a symlinked destination would
    # otherwise redirect the destructive cleanup or subsequent evidence writes.
    for path, label in (
        (repository, "repository"),
        (root, "D1 output root"),
        (artifact, "artifact root"),
    ):
        if _has_symlink_component(path):
            raise ValueError(f"{label} path contains a symlink: {path}")
    if artifact.exists():
        if not artifact.is_dir():
            raise ValueError(f"artifact root is not a directory: {artifact}")
        shutil.rmtree(artifact)
    artifact.mkdir(parents=True)

    tested_sha = require_git_sha(
        os.environ.get("TESTED_SHA"), "TESTED_SHA"
    )
    tested_tree_sha = require_git_sha(
        os.environ.get("TESTED_TREE_SHA"), "TESTED_TREE_SHA"
    )
    source_manifest = tracked_source_manifest(
        repository,
        tested_sha=tested_sha,
        tested_tree_sha=tested_tree_sha,
    )
    source_manifest_path = artifact / "evidence/source-input-digests.json"
    _write_bytes_atomic(
        source_manifest_path,
        (json.dumps(source_manifest, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
        "source manifest destination",
    )

    canonical_files = {
        root / "pipeline-result.json": artifact / "pipeline/pipeline-result.json",
        root / "reproducibility-result.json": artifact
        / "reproducibility/reproducibility-result.json",
        root / "qemu/boot-result.json": artifact / "qemu/boot-result.json",
        root / "qemu/acceptance.json": artifact / "qemu/acceptance.json",
        root / "prepared/prepared-inputs.json": artifact
        / "inputs/prepared-inputs.json",
        root / "prepared/expected-package-lock.tsv": artifact
        / "inputs/expected-package-lock.tsv",
        root / "build-a/candidate/artifacts/build-result.json": artifact
        / "builds/build-a/build-result.json",
        root / "build-a/candidate/artifacts/package-lock.tsv": artifact
        / "builds/build-a/package-lock.tsv",
        root / "build-a/candidate/artifacts/rootfs-content-manifest.json": artifact
        / "builds/build-a/rootfs-content-manifest.json",
        root / "build-b/candidate/artifacts/build-result.json": artifact
        / "builds/build-b/build-result.json",
        root / "build-b/candidate/artifacts/package-lock.tsv": artifact
        / "builds/build-b/package-lock.tsv",
        root / "build-b/candidate/artifacts/rootfs-content-manifest.json": artifact
        / "builds/build-b/rootfs-content-manifest.json",
        root / "evidence/e2fsprogs-host-tool-result.json": artifact
        / "evidence/e2fsprogs-host-tool-result.json",
        root / "evidence/host-toolchain.json": artifact
        / "evidence/host-toolchain.json",
        root / "evidence/product-cargo-tree.txt": artifact
        / "evidence/product-cargo-tree.txt",
        root / "evidence/qualification-cargo-tree.txt": artifact
        / "evidence/qualification-cargo-tree.txt",
        root / "evidence/product-daemon-self-check-host.json": artifact
        / "evidence/product-daemon-self-check-host.json",
        root / "evidence/d1-qualification-self-check-host.json": artifact
        / "evidence/d1-qualification-self-check-host.json",
    }
    for source, destination in canonical_files.items():
        copy_file(source, destination)

    raw_root = root / "evidence"
    _reject_symlink_path(raw_root, "raw evidence root")
    if raw_root.is_dir():
        for source in sorted(raw_root.rglob("*")):
            if not source.is_file() or source.is_symlink():
                continue
            if source.name in {
                "d1-final-qualification.json",
                "gate-evidence-envelope.json",
            }:
                continue
            copy_optional_bounded(
                source,
                artifact / "raw-evidence" / source.relative_to(raw_root),
            )

    product_binary = repository / "target/release/hepta-agent-portd"
    qualification_binary = repository / "target/release/hepta-agent-d1-fixture"
    binary_digests = {
        "schema": "trillionnium.desktop.d1-binary-digests.v1",
        "product": {
            "path": "target/release/hepta-agent-portd",
            "sha256": sha256(product_binary),
            "bytes": product_binary.stat().st_size,
        },
        "qualification": {
            "path": "target/release/hepta-agent-d1-fixture",
            "sha256": sha256(qualification_binary),
            "bytes": qualification_binary.stat().st_size,
        },
    }
    for build in ("build-a", "build-b"):
        manifest_path = (
            root
            / build
            / "candidate/artifacts/rootfs-content-manifest.json"
        )
        entries = rootfs_entries(manifest_path)
        product_entry = entries.get("./usr/libexec/hepta-agent-portd")
        qualification_entry = entries.get("./usr/libexec/hepta-agent-d1-fixture")
        if product_entry is None or product_entry.get("sha256") != binary_digests[
            "product"
        ]["sha256"]:
            raise ValueError(f"{build} product binary digest is not bound to rootfs")
        if qualification_entry is None or qualification_entry.get(
            "sha256"
        ) != binary_digests["qualification"]["sha256"]:
            raise ValueError(
                f"{build} qualification binary digest is not bound to rootfs"
            )
    binary_path = artifact / "evidence/binary-digests.json"
    _write_bytes_atomic(
        binary_path,
        (json.dumps(binary_digests, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
        "binary digest destination",
    )

    workflow = validate_workflow(repository)
    role = os.environ.get("EVIDENCE_ROLE")
    ref = os.environ.get("SOURCE_REF")
    authoritative_text = os.environ.get("PROMOTION_AUTHORITATIVE")
    if role not in {"pr_synthetic_merge", "exact_main_push", "manual_non_authoritative"}:
        raise ValueError(f"invalid D1 evidence role: {role!r}")
    if authoritative_text not in {"true", "false"}:
        raise ValueError("PROMOTION_AUTHORITATIVE is not canonical boolean text")
    authoritative = authoritative_text == "true"
    if role == "exact_main_push":
        if ref != "refs/heads/main" or not authoritative:
            raise ValueError("exact-main role is not bound to authoritative main")
    elif authoritative:
        raise ValueError("non-main D1 evidence is marked authoritative")

    # Emit the common envelope alongside the gate-specific receipt.  The
    # envelope deliberately excludes both receipts from its artifact list to
    # avoid a self-referential digest cycle; the specialized receipt below
    # still binds every staged file (including this envelope) via
    # ``output_digests``.
    envelope_relative = Path("evidence/gate-evidence-envelope.json")
    envelope_artifacts: list[dict[str, Any]] = []
    for path in sorted(artifact.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(artifact)
        if relative in {
            Path("evidence/d1-final-qualification.json"),
            envelope_relative,
        }:
            continue
        envelope_artifacts.append(
            {
                "path": relative.as_posix(),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    event_name = os.environ["GITHUB_EVENT_NAME"]
    if event_name == "pull_request":
        tested_merge_sha: str | None = tested_sha
        integrated_main_sha: str | None = None
    elif event_name == "push":
        tested_merge_sha = None
        integrated_main_sha = tested_sha
    elif event_name == "workflow_dispatch":
        tested_merge_sha = None
        integrated_main_sha = None
    else:
        raise ValueError(f"unsupported D1 event for evidence envelope: {event_name!r}")
    claim_ceiling = {
        "servo_started": False,
        "visible_window_created": False,
        "network_enabled_during_acceptance": False,
        "secure_boot_qualified": False,
        "product_agent_port_enabled": False,
        "product_release_authorized": False,
    }
    envelope = build_envelope(
        gate_id="D1-01",
        package_id="d1-debian-qemu-substrate",
        status="PASS",
        evidence_tier="qemu_image",
        base_sha=os.environ.get("BASE_SHA"),
        candidate_head_sha=os.environ.get("CANDIDATE_HEAD_SHA"),
        tested_merge_sha=tested_merge_sha,
        integrated_main_sha=integrated_main_sha,
        tree_sha=tested_tree_sha,
        workflow_path=workflow["path"],
        workflow_sha256=workflow["sha256"],
        input_digests=source_manifest["files"],
        runner=results["host_environment"],
        commands=[
            {
                "name": name,
                "status": stage.get("status"),
                "exit_code": stage.get("exit_code"),
            }
            for name, stage in sorted(results["pipeline"].get("stages", {}).items())
            if isinstance(stage, dict)
        ],
        artifacts=envelope_artifacts,
        claim_ceiling=claim_ceiling,
        event_name=event_name,
        ref=ref,
        ref_name=os.environ.get("SOURCE_REF_NAME"),
        evidence_role=role,
        promotion_authoritative=authoritative,
        tested_sha=tested_sha,
        workflow_run_id=os.environ.get("GITHUB_RUN_ID"),
        workflow_run_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
    )
    write_envelope(artifact / envelope_relative, envelope)

    output_digests: dict[str, str] = {}
    receipt_relative = Path("evidence/d1-final-qualification.json")
    for path in sorted(artifact.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(artifact)
        if relative == receipt_relative:
            continue
        output_digests[relative.as_posix()] = sha256(path)

    receipt = {
        "schema": "trillionnium.desktop.d1-final-qualification.v3",
        "status": "PASS",
        "repository": os.environ["GITHUB_REPOSITORY"],
        "event_name": os.environ["GITHUB_EVENT_NAME"],
        "ref": ref,
        "ref_name": os.environ.get("SOURCE_REF_NAME"),
        "evidence_role": role,
        "promotion_authoritative": authoritative,
        "tested_topology": os.environ["TESTED_TOPOLOGY"],
        "base_sha": os.environ["BASE_SHA"],
        "candidate_head_sha": os.environ["CANDIDATE_HEAD_SHA"],
        "tested_sha": tested_sha,
        "tree_sha": tested_tree_sha,
        "workflow": workflow,
        "runner_sha256": sha256(
            repository / "tools/run_d1_final_qualification.sh"
        ),
        "workflow_run_id": os.environ["GITHUB_RUN_ID"],
        "workflow_run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "source_input_manifest_sha256": sha256(source_manifest_path),
        "source_input_files_sha256": source_manifest["files_sha256"],
        "source_input_count": source_manifest["file_count"],
        "output_digests": output_digests,
        "product_fixture_separation": {
            "product_default_graph_fixture_free": True,
            "qualification_feature": "d1-qualification",
            "qualification_binary": "hepta-agent-d1-fixture",
            "qualification_server_exec": results["acceptance"]["agent_port"][
                "qualification_server_exec"
            ],
            "product_handler_connected": False,
            "production_install_map_contains_qualification_binary": False,
        },
        "host_tool": results["host_tool"],
        "host_environment": results["host_environment"],
        "pipeline": results["pipeline"],
        "reproducibility": results["reproducibility"],
        "reproducibility_scope": {
            "same_run_two_build_byte_identity": True,
            "cross_run_identity_claimed": False,
            "hermetic_host_environment_claimed": False,
        },
        "boot": results["boot"],
        "acceptance": results["acceptance"],
        "claim_ceiling": claim_ceiling,
    }
    receipt_path = artifact / receipt_relative
    _write_bytes_atomic(
        receipt_path,
        (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        "D1 receipt destination",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()

    for path, label in (
        (args.repository, "repository"),
        (args.root, "D1 output root"),
        (args.artifact_root, "artifact root"),
    ):
        if _has_symlink_component(path):
            raise SystemExit(f"{label} path contains a symlink: {path}")

    repository = args.repository.absolute()
    root = args.root.absolute()
    artifact = args.artifact_root.absolute()
    if not repository.is_dir() or not (repository / ".git").exists():
        raise SystemExit("repository path is not a Git worktree")
    if _has_symlink_component(repository / ".git"):
        raise SystemExit("repository .git path is a symlink")
    if not root.is_dir() or root.is_symlink():
        raise SystemExit("D1 output root is missing or unsafe")
    results = validate_results(root)
    stage_artifact(repository, root, artifact, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
