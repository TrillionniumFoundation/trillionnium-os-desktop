#!/usr/bin/env python3
"""Bind D0A-01 evidence to one immutable desktop Git object.

The permanent Servo compile gate runs for pull requests, exact ``main`` pushes,
and manual dispatches.  GitHub's checkout object alone is not enough to prove
which source was tested, so this helper validates the event topology and exports
the identities consumed by the evidence envelope.  It has no write authority:
the only network operation is a read-only fetch of ``origin/main``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")
ZERO_SHA = "0" * 40
PR_REF_RE = re.compile(r"^refs/pull/([1-9][0-9]*)/merge$")


def validate_event_ref(event_name: str, source_ref: str, source_ref_name: str) -> None:
    """Bind the event class to GitHub's immutable ref topology.

    These values are copied into evidence and later consumed as provenance.
    Checking only the commit parents is insufficient when a caller can supply
    an inconsistent ref tuple (for example, a PR role on a branch ref).
    """

    for value, label in (
        (event_name, "event name"),
        (source_ref, "source ref"),
        (source_ref_name, "source ref name"),
    ):
        if not isinstance(value, str) or not value or any(ord(char) < 0x20 for char in value):
            raise ValueError(f"{label} is malformed")

    if event_name == "pull_request":
        match = PR_REF_RE.fullmatch(source_ref)
        if match is None or source_ref_name != f"{match.group(1)}/merge":
            raise ValueError("pull-request source ref is not an exact synthetic merge ref")
        return

    if event_name == "push":
        if source_ref != "refs/heads/main" or source_ref_name != "main":
            raise ValueError("push source ref is not refs/heads/main")
        return

    if event_name == "workflow_dispatch":
        # Manual runs may target a branch or tag, but never a pull-request
        # merge ref.  GitHub's ref_name is the suffix after refs/{heads,tags}/.
        for prefix in ("refs/heads/", "refs/tags/"):
            if source_ref.startswith(prefix):
                suffix = source_ref[len(prefix) :]
                if suffix and source_ref_name == suffix:
                    return
        raise ValueError("manual source ref must be a branch or tag ref")

    raise ValueError(f"unsupported D0A-01 event: {event_name!r}")


def valid_sha(value: str, label: str) -> str:
    if SHA40.fullmatch(value) is None or value == ZERO_SHA:
        raise ValueError(f"{label} is not a non-zero lowercase 40-hex SHA: {value!r}")
    return value


def derive_identity(
    *,
    event_name: str,
    source_ref: str,
    source_ref_name: str,
    event_sha: str,
    tested_sha: str,
    tested_tree_sha: str,
    parents: Iterable[str],
    current_main_sha: str,
    pr_head_sha: str = "",
    pr_base_sha: str = "",
    dispatch_base_sha: str = "",
) -> dict[str, Any]:
    """Return fail-closed identity fields for one already-observed topology."""

    validate_event_ref(event_name, source_ref, source_ref_name)
    tested_sha = valid_sha(tested_sha, "tested SHA")
    tested_tree_sha = valid_sha(tested_tree_sha, "tested tree SHA")
    event_sha = valid_sha(event_sha, "event SHA")
    current_main_sha = valid_sha(current_main_sha, "current main SHA")
    parent_list = [valid_sha(parent, "parent SHA") for parent in parents]
    if event_sha != tested_sha:
        raise ValueError("checked-out HEAD does not equal the workflow event SHA")

    if event_name == "pull_request":
        if len(parent_list) != 2:
            raise ValueError("pull-request qualification requires an exact two-parent merge")
        pr_head_sha = valid_sha(pr_head_sha, "pull-request head SHA")
        pr_base_sha = valid_sha(pr_base_sha, "pull-request base SHA")
        if parent_list[0] != pr_base_sha:
            raise ValueError("merge first parent does not equal the live pull-request base")
        if parent_list[0] != current_main_sha:
            raise ValueError("merge first parent is not the current origin/main object")
        if parent_list[1] != pr_head_sha:
            raise ValueError("merge second parent does not equal the live pull-request head")
        return {
            "EVENT_NAME": event_name,
            "EVENT_SHA": event_sha,
            "SOURCE_REF": source_ref,
            "SOURCE_REF_NAME": source_ref_name,
            "CURRENT_MAIN_SHA": current_main_sha,
            "TESTED_SHA": tested_sha,
            "TESTED_TREE_SHA": tested_tree_sha,
            "BASE_SHA": parent_list[0],
            "CANDIDATE_HEAD_SHA": parent_list[1],
            "TESTED_MERGE_SHA": tested_sha,
            "INTEGRATED_MAIN_SHA": "",
            "EVIDENCE_ROLE": "pr_synthetic_merge",
            "PROMOTION_AUTHORITATIVE": "false",
        }

    if event_name == "push":
        if source_ref != "refs/heads/main" or source_ref_name != "main":
            raise ValueError("D0A-01 push qualification is authoritative only on refs/heads/main")
        if not parent_list:
            raise ValueError("exact-main qualification requires at least one parent")
        if tested_sha != current_main_sha:
            raise ValueError("tested push object is not the current origin/main object")
        return {
            "EVENT_NAME": event_name,
            "EVENT_SHA": event_sha,
            "SOURCE_REF": source_ref,
            "SOURCE_REF_NAME": source_ref_name,
            "CURRENT_MAIN_SHA": current_main_sha,
            "TESTED_SHA": tested_sha,
            "TESTED_TREE_SHA": tested_tree_sha,
            "BASE_SHA": parent_list[0],
            "CANDIDATE_HEAD_SHA": tested_sha,
            "TESTED_MERGE_SHA": "",
            "INTEGRATED_MAIN_SHA": tested_sha,
            "EVIDENCE_ROLE": "exact_main_push",
            "PROMOTION_AUTHORITATIVE": "true",
        }

    if event_name == "workflow_dispatch":
        if not parent_list:
            raise ValueError("manual qualification requires at least one parent")
        base_sha = valid_sha(dispatch_base_sha, "manual base SHA") if dispatch_base_sha else current_main_sha
        return {
            "EVENT_NAME": event_name,
            "EVENT_SHA": event_sha,
            "SOURCE_REF": source_ref,
            "SOURCE_REF_NAME": source_ref_name,
            "CURRENT_MAIN_SHA": current_main_sha,
            "TESTED_SHA": tested_sha,
            "TESTED_TREE_SHA": tested_tree_sha,
            "BASE_SHA": base_sha,
            "CANDIDATE_HEAD_SHA": tested_sha,
            "TESTED_MERGE_SHA": "",
            "INTEGRATED_MAIN_SHA": "",
            "EVIDENCE_ROLE": "manual_non_authoritative",
            "PROMOTION_AUTHORITATIVE": "false",
        }

    raise ValueError(f"unsupported D0A-01 event: {event_name!r}")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def append_github_env(identity: dict[str, Any]) -> None:
    destination = os.environ.get("GITHUB_ENV")
    if not destination:
        return
    with Path(destination).open("a", encoding="utf-8") as stream:
        for key, value in identity.items():
            rendered = str(value)
            if "\n" in rendered or "\r" in rendered:
                raise ValueError(f"identity value {key} contains a newline")
            stream.write(f"{key}={rendered}\n")


def run() -> int:
    event_name = os.environ.get("EVENT_NAME") or os.environ.get("GITHUB_EVENT_NAME", "")
    event_sha = os.environ.get("EVENT_SHA") or os.environ.get("GITHUB_SHA", "")
    source_ref = os.environ.get("SOURCE_REF") or os.environ.get("GITHUB_REF", "")
    source_ref_name = os.environ.get("SOURCE_REF_NAME") or os.environ.get("GITHUB_REF_NAME", "")
    if not event_name or not event_sha or not source_ref or not source_ref_name:
        raise ValueError("GitHub event/ref identity environment is incomplete")

    tested_sha = git("rev-parse", "HEAD")
    tested_tree_sha = git("rev-parse", "HEAD^{tree}")
    parents = git("show", "-s", "--format=%P", "HEAD").split()
    subprocess.run(["git", "fetch", "--no-tags", "origin", "main"], cwd=ROOT, check=True)
    current_main_sha = git("rev-parse", "origin/main")
    dispatch_base_sha = (
        git("merge-base", tested_sha, current_main_sha) if event_name == "workflow_dispatch" else ""
    )
    identity = derive_identity(
        event_name=event_name,
        source_ref=source_ref,
        source_ref_name=source_ref_name,
        event_sha=event_sha,
        tested_sha=tested_sha,
        tested_tree_sha=tested_tree_sha,
        parents=parents,
        current_main_sha=current_main_sha,
        pr_head_sha=os.environ.get("PR_HEAD_SHA", ""),
        pr_base_sha=os.environ.get("PR_BASE_SHA", ""),
        dispatch_base_sha=dispatch_base_sha,
    )

    event_before = os.environ.get("EVENT_BEFORE", "")
    if event_name == "push" and event_before and event_before != ZERO_SHA and parents:
        subprocess.run(["git", "cat-file", "-e", f"{event_before}^{{commit}}"], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", event_before, parents[0]],
            cwd=ROOT,
            check=True,
        )
    if git("status", "--porcelain=v1"):
        raise ValueError("desktop checkout is not clean before D0A-01 qualification")
    append_github_env(identity)
    print(json.dumps(identity, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    return run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - fail-closed CLI boundary
        print(f"D0A-01 identity validation failed: {error}", file=sys.stderr)
        raise
