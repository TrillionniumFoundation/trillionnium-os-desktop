#!/usr/bin/env python3
"""Bind a CI source checkout to canonical live Git refs; no promotion authority."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time

OFFICIAL_REPOSITORY = "TrillionniumFoundation/trillionnium-os-desktop"
OFFICIAL_REMOTE = "https://github.com/TrillionniumFoundation/trillionnium-os-desktop.git"
TOTAL_SECONDS = 20
COMMAND_SECONDS = 5
OUTPUT_BYTES = 262144
REF_BYTES = 1024
TRACKED_FILES = 4096
TRACKED_FILE_BYTES = 16777216
TRACKED_TOTAL_BYTES = 67108864
TRACKED_CHUNK_BYTES = 65536
FIELDS = (
    "CI_SOURCE_ROLE", "CI_SOURCE_EVENT", "CI_SOURCE_REPOSITORY", "CI_SOURCE_REF",
    "CI_SOURCE_REF_NAME", "CI_SOURCE_SHA", "CI_SOURCE_PR_NUMBER",
    "CI_SOURCE_PR_HEAD", "CI_SOURCE_PR_BASE", "CI_SOURCE_BASE_REF",
)
SHA = re.compile(r"[0-9a-f]{40}\Z")
NUMBER = re.compile(r"[1-9][0-9]{0,9}\Z")


class SourceIdentityError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _ref_name(value: object) -> str:
    if (type(value) is not str or not value or value.startswith(("refs/", "-"))
            or len(value.encode("utf-8")) > REF_BYTES or value != value.strip()
            or any(ord(char) < 33 or ord(char) == 127 for char in value)
            or "@{" in value or "\\" in value):
        raise SourceIdentityError("INVALID_INPUT")
    return value


def _sha(value: object) -> str:
    if type(value) is not str or SHA.fullmatch(value) is None:
        raise SourceIdentityError("INVALID_INPUT")
    return value


def _inputs(value: object) -> dict[str, str]:
    if type(value) is not dict or set(value) != set(FIELDS) or any(type(item) is not str for item in value.values()):
        raise SourceIdentityError("INVALID_INPUT")
    try:
        if any(len(item.encode("utf-8")) > REF_BYTES for item in value.values()):
            raise SourceIdentityError("INVALID_INPUT")
    except UnicodeError as error:
        raise SourceIdentityError("INVALID_INPUT") from error
    result = dict(value)
    if result["CI_SOURCE_ROLE"] not in {"head", "prospective-merge", "event-source"}:
        raise SourceIdentityError("INVALID_INPUT")
    event = result["CI_SOURCE_EVENT"]
    if event not in {"pull_request", "push", "workflow_dispatch"} or result["CI_SOURCE_REPOSITORY"].lower() != OFFICIAL_REPOSITORY.lower():
        raise SourceIdentityError("INVALID_INPUT")
    _sha(result["CI_SOURCE_SHA"])
    if event == "pull_request":
        number = result["CI_SOURCE_PR_NUMBER"]
        if NUMBER.fullmatch(number) is None:
            raise SourceIdentityError("INVALID_INPUT")
        if result["CI_SOURCE_REF"] != f"refs/pull/{number}/merge" or result["CI_SOURCE_REF_NAME"] != f"{number}/merge":
            raise SourceIdentityError("INVALID_INPUT")
        _sha(result["CI_SOURCE_PR_HEAD"]); _sha(result["CI_SOURCE_PR_BASE"])
        _ref_name(result["CI_SOURCE_BASE_REF"])
    else:
        if result["CI_SOURCE_ROLE"] == "prospective-merge" or any(result[key] for key in FIELDS[-4:]):
            raise SourceIdentityError("INVALID_INPUT")
        branch = _ref_name(result["CI_SOURCE_REF_NAME"])
        if result["CI_SOURCE_REF"] != "refs/heads/" + branch:
            # Manual diagnostics retain branch semantics and gain no tag or
            # promotion fallback. Availability jobs do not invoke this guard.
            raise SourceIdentityError("INVALID_INPUT")
    return result


def _run(command: list[str], *, cwd: Path, deadline: float) -> bytes:
    """Bound native output/time and retire this retained, unreaped process group."""
    end = min(deadline, time.monotonic() + COMMAND_SECONDS)
    if end <= time.monotonic():
        raise SourceIdentityError("COMMAND_TIMEOUT")
    environment = {
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/false",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    process = subprocess.Popen(command, cwd=cwd, env=environment,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    output = bytearray(); total = 0
    try:
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map():
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise SourceIdentityError("COMMAND_TIMEOUT")
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fileobj.fileno(), 4096)
                    total += len(chunk)
                    if total > OUTPUT_BYTES:
                        raise SourceIdentityError("OUTPUT_LIMIT")
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif key.fileobj is process.stdout:
                        output.extend(chunk)
            # Inspect exit without reaping: the original leader anchors group
            # identity until all group signals are finished in the finally.
            while True:
                if time.monotonic() >= end:
                    raise SourceIdentityError("COMMAND_TIMEOUT")
                status = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if status is not None:
                    if status.si_code != os.CLD_EXITED or status.si_status != 0:
                        raise SourceIdentityError("COMMAND_FAILED")
                    return bytes(output)
                time.sleep(min(0.005, max(0, end - time.monotonic())))
    finally:
        # No Popen poll/wait has reaped the leader. Never signal after wait.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        finally:
            try:
                process.wait(timeout=COMMAND_SECONDS)
            finally:
                process.stdout.close(); process.stderr.close()


class _Git:
    def __init__(self, root: Path, remote: str, budget: float):
        self.root = root
        self.remote = remote
        self.deadline = time.monotonic() + budget

    def local(self, *arguments: str) -> bytes:
        return _run(["/usr/bin/git", "--no-replace-objects", *arguments], cwd=self.root, deadline=self.deadline)

    def branch(self, name: str) -> str:
        name = _ref_name(name)
        if self.local("check-ref-format", "--branch", name).strip() != name.encode("utf-8"):
            raise SourceIdentityError("INVALID_INPUT")
        query = "refs/heads/" + name
        self.local("check-ref-format", query)
        return query

    def resolve(self, query: str) -> str:
        # Outside the checkout, with global/system Git config disabled: a
        # checkout-local URL/credential rewrite cannot replace the fixed URL.
        raw = _run(["/usr/bin/git", "ls-remote", "--exit-code", "--refs", self.remote, query],
                   cwd=Path("/"), deadline=self.deadline)
        try:
            rows = raw.decode("utf-8", "strict").splitlines()
        except UnicodeError as error:
            raise SourceIdentityError("MALFORMED_GIT_OUTPUT") from error
        if len(rows) != 1:
            raise SourceIdentityError("MALFORMED_GIT_OUTPUT")
        fields = rows[0].split("\t")
        if len(fields) != 2 or fields[1] != query or SHA.fullmatch(fields[0]) is None:
            raise SourceIdentityError("MALFORMED_GIT_OUTPUT")
        return fields[0]

    def snapshot(self) -> tuple[str, str, list[str]]:
        head = _sha(self.local("rev-parse", "HEAD").decode("ascii", "strict").strip())
        raw = self.local("cat-file", "commit", head)
        if hashlib.sha1(b"commit " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest() != head:
            raise SourceIdentityError("MALFORMED_GIT_OUTPUT")
        header = raw.split(b"\n\n", 1)[0].splitlines()
        trees = [row[5:].decode("ascii", "strict") for row in header if row.startswith(b"tree ")]
        parents = [row[7:].decode("ascii", "strict") for row in header if row.startswith(b"parent ")]
        if len(trees) != 1:
            raise SourceIdentityError("MALFORMED_GIT_OUTPUT")
        return head, _sha(trees[0]), [_sha(parent) for parent in parents]


def _tracked_bytes(git: _Git, tree: str) -> None:
    """Compare bounded current source bytes/modes with the immutable Git tree."""
    rows = git.local("ls-tree", "-r", "-z", tree).split(b"\0")
    if len(rows) - 1 > TRACKED_FILES:
        raise SourceIdentityError("SOURCE_LIMIT")
    root = os.open(git.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    total = 0

    def current() -> None:
        if time.monotonic() >= git.deadline:
            raise SourceIdentityError("COMMAND_TIMEOUT")

    def identity(metadata):
        return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_size,
                metadata.st_mtime_ns, metadata.st_ctime_ns)

    try:
        for row in rows:
            if not row:
                continue
            current()
            try:
                header, name = row.split(b"\t", 1)
                mode, kind, expected = header.split(b" ")
                parts = name.split(b"/")
                if (mode not in {b"100644", b"100755", b"120000"} or kind != b"blob"
                        or SHA.fullmatch(expected.decode("ascii")) is None
                        or len(name) > 4096 or any(part in {b"", b".", b".."} for part in parts)):
                    raise ValueError("tree record")
            except (ValueError, UnicodeError) as error:
                raise SourceIdentityError("MALFORMED_GIT_OUTPUT") from error
            parent = root
            directories = []
            source = None
            try:
                for part in parts[:-1]:
                    current()
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                    directories.append((parent, part, child))
                    parent = child
                before = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                if (before.st_size > TRACKED_FILE_BYTES
                        or total + before.st_size > TRACKED_TOTAL_BYTES):
                    raise SourceIdentityError("SOURCE_LIMIT")
                total += before.st_size
                digest = hashlib.sha1(b"blob " + str(before.st_size).encode("ascii") + b"\0")
                if mode == b"120000":
                    if not stat.S_ISLNK(before.st_mode):
                        raise SourceIdentityError("SOURCE_DRIFT")
                    content = os.readlink(parts[-1], dir_fd=parent)
                    if len(content) != before.st_size:
                        raise SourceIdentityError("SOURCE_DRIFT")
                    digest.update(content)
                else:
                    if (not stat.S_ISREG(before.st_mode)
                            or bool(before.st_mode & 0o111) != (mode == b"100755")):
                        raise SourceIdentityError("SOURCE_DRIFT")
                    source = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                    if identity(os.fstat(source)) != identity(before):
                        raise SourceIdentityError("SOURCE_DRIFT")
                    size = 0
                    while True:
                        current()
                        chunk = os.read(source, TRACKED_CHUNK_BYTES)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > before.st_size:
                            raise SourceIdentityError("SOURCE_DRIFT")
                        digest.update(chunk)
                    if size != before.st_size or identity(os.fstat(source)) != identity(before):
                        raise SourceIdentityError("SOURCE_DRIFT")
                if (digest.hexdigest().encode("ascii") != expected
                        or identity(os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)) != identity(before)):
                    raise SourceIdentityError("SOURCE_DRIFT")
                for ancestor, part, descriptor in directories:
                    named = os.stat(part, dir_fd=ancestor, follow_symlinks=False)
                    held = os.fstat(descriptor)
                    if not stat.S_ISDIR(named.st_mode) or (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino):
                        raise SourceIdentityError("SOURCE_DRIFT")
                named_root = os.stat(git.root, follow_symlinks=False)
                held_root = os.fstat(root)
                if not stat.S_ISDIR(named_root.st_mode) or (named_root.st_dev, named_root.st_ino) != (held_root.st_dev, held_root.st_ino):
                    raise SourceIdentityError("SOURCE_DRIFT")
            finally:
                if source is not None:
                    os.close(source)
                for _, _, descriptor in reversed(directories):
                    os.close(descriptor)
        current()
    finally:
        os.close(root)


def _verify(root: Path, fields: object, *, _remote: str = OFFICIAL_REMOTE,
            _budget: float = TOTAL_SECONDS) -> dict:
    value = _inputs(fields)
    git = _Git(root, _remote, _budget)
    before = git.snapshot(); head, tree, parents = before
    live = {}
    event, role = value["CI_SOURCE_EVENT"], value["CI_SOURCE_ROLE"]
    if event == "pull_request":
        number = value["CI_SOURCE_PR_NUMBER"]
        head_query = f"refs/pull/{number}/head"
        live[head_query] = git.resolve(head_query)
        if live[head_query] != value["CI_SOURCE_PR_HEAD"]:
            raise SourceIdentityError("LIVE_REF_MISMATCH")
        if role == "head":
            if head != live[head_query]:
                raise SourceIdentityError("SOURCE_MISMATCH")
            binding = "candidate_head"
        else:
            base_query = git.branch(value["CI_SOURCE_BASE_REF"])
            merge_query = f"refs/pull/{number}/merge"
            live[base_query] = git.resolve(base_query)
            live[merge_query] = git.resolve(merge_query)
            if (live[base_query] != value["CI_SOURCE_PR_BASE"]
                    or live[merge_query] != value["CI_SOURCE_SHA"]
                    or head != value["CI_SOURCE_SHA"]
                    or parents != [live[base_query], live[head_query]]):
                raise SourceIdentityError("LIVE_REF_MISMATCH")
            binding = "prospective_merge"
    else:
        query = git.branch(value["CI_SOURCE_REF_NAME"])
        live[query] = git.resolve(query)
        if head != value["CI_SOURCE_SHA"] or live[query] != head:
            raise SourceIdentityError("LIVE_REF_MISMATCH")
        binding = "manual_source" if event == "workflow_dispatch" else "push_head"
    # status alone trusts assume-unchanged and skip-worktree flags. Reject
    # those flags so a modified tracked source cannot hide behind the index.
    indexed = git.local("ls-files", "-v", "-z")
    if any(not entry.startswith(b"H ") for entry in indexed.split(b"\0") if entry):
        raise SourceIdentityError("SOURCE_DRIFT")
    try:
        _tracked_bytes(git, tree)
    except OSError as error:
        raise SourceIdentityError("SOURCE_DRIFT") from error
    if git.snapshot() != before or git.local("status", "--porcelain=v1", "-z"):
        raise SourceIdentityError("SOURCE_DRIFT")
    if time.monotonic() >= git.deadline:
        raise SourceIdentityError("COMMAND_TIMEOUT")
    return {
        "schema": "trillionnium.ci-source-identity-result.v1", "status": "PASS_CI_SOURCE_IDENTITY",
        "binding": binding, "tested_sha": head, "tested_tree": tree,
        "parents": parents, "live_refs": live, "promotion_authority": False,
        "production_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        if {name for name in os.environ if name.startswith("CI_SOURCE_")} != set(FIELDS):
            raise SourceIdentityError("INVALID_INPUT")
        result = _verify(args.repository, {name: os.environ[name] for name in FIELDS})
    except (SourceIdentityError, OSError, UnicodeError, subprocess.SubprocessError) as error:
        code = error.code if isinstance(error, SourceIdentityError) else "COMMAND_FAILED"
        print("CI_SOURCE_IDENTITY_REFUSED:" + code, file=os.sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
