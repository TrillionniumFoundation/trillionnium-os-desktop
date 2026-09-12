#!/usr/bin/env python3
"""Bind image qualification to the live event object; never authorize promotion."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

REPOSITORY = "TrillionniumFoundation/trillionnium-os-desktop"
WORKFLOW = ".github/workflows/s10-production-debian-qemu.yml"
SHA = re.compile(r"[0-9a-f]{40}\Z")


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=root, capture_output=True,
                            text=True, timeout=30, check=True)
    if len(result.stdout) > 65536:
        raise ValueError("unbounded Git identity response")
    return result.stdout.strip()


def require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError(f"{label} is not an exact commit identity")
    return value


def live_ref(root: Path, reference: str) -> str:
    if not isinstance(reference, str) or not reference.startswith("refs/") or len(reference) > 1024:
        raise ValueError("invalid reference")
    git(root, "check-ref-format", reference)
    rows = git(root, "ls-remote", "--exit-code", "origin", reference).splitlines()
    if len(rows) != 1:
        raise ValueError("live reference is absent or ambiguous")
    parts = rows[0].split("\t")
    if len(parts) != 2 or parts[1] != reference:
        raise ValueError("live reference identity mismatch")
    return require_sha(parts[0], "live ref")


def validate_context(context: dict[str, Any]) -> None:
    expected_fields = {"repository", "event", "object", "subject", "tree", "parents",
                       "event_head", "event_base", "event_merge", "live_head", "live_base",
                       "live_merge", "source_ref"}
    if set(context) != expected_fields or context["repository"] != REPOSITORY:
        raise ValueError("closed source identity or repository mismatch")
    for field in ("subject", "tree", "event_head", "live_head"):
        require_sha(context[field], field)
    parents = context["parents"]
    if not isinstance(parents, list) or not 1 <= len(parents) <= 2:
        raise ValueError("unsupported source parent topology")
    for value in parents:
        require_sha(value, "parent")
    event, mode = context["event"], context["object"]
    if mode not in {"exact-head", "prospective-merge"}:
        raise ValueError("unknown source qualification object")
    if context["live_head"] != context["event_head"]:
        raise ValueError("candidate head moved; evidence is stale")
    if event == "pull_request":
        for field in ("event_base", "live_base", "event_merge", "live_merge"):
            require_sha(context[field], field)
        if context["event_base"] != context["live_base"]:
            raise ValueError("candidate base moved; evidence is stale")
        if context["event_merge"] != context["live_merge"]:
            raise ValueError("prospective merge moved; evidence is stale")
        if not isinstance(context["source_ref"], str) or not re.fullmatch(r"refs/pull/[1-9][0-9]{0,9}/head", context["source_ref"]):
            raise ValueError("PR head is not bound to its canonical pull ref")
        if mode == "prospective-merge":
            if context["subject"] != context["event_merge"] or parents != [context["event_base"], context["event_head"]]:
                raise ValueError("prospective merge subject or ordered parents differ")
        elif context["subject"] != context["event_head"]:
            raise ValueError("checkout is not the exact candidate head")
    elif event in {"push", "workflow_dispatch"}:
        if mode != "exact-head" or context["subject"] != context["event_head"]:
            raise ValueError("non-PR event cannot qualify a prospective merge")
        if any(context[field] is not None for field in ("event_base", "live_base", "event_merge", "live_merge")):
            raise ValueError("non-PR identity contains invented merge fields")
        reference = context["source_ref"]
        if not isinstance(reference, str) or not reference.startswith("refs/heads/"):
            raise ValueError("non-PR source must be an explicit branch")
        if event == "push" and reference != "refs/heads/main":
            raise ValueError("automatic image pushes qualify main only")
    else:
        raise ValueError("unsupported qualification event")


def inspect(root: Path, environment: dict[str, str]) -> dict[str, Any]:
    if environment.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise ValueError("repository environment mismatch")
    event = environment.get("GITHUB_EVENT_NAME")
    mode = environment.get("IMAGE_OBJECT", "exact-head")
    head = require_sha(environment.get("EXPECTED_HEAD"), "expected head")
    context: dict[str, Any] = {
        "repository": REPOSITORY, "event": event, "object": mode,
        "subject": git(root, "rev-parse", "HEAD"), "tree": git(root, "rev-parse", "HEAD^{tree}"),
        "parents": git(root, "show", "-s", "--format=%P", "HEAD").split(),
        "event_head": head, "event_base": None, "event_merge": None,
        "live_head": None, "live_base": None, "live_merge": None, "source_ref": None,
    }
    if event == "pull_request":
        number = environment.get("PR_NUMBER", "")
        if not re.fullmatch(r"[1-9][0-9]{0,9}", number):
            raise ValueError("invalid pull-request number")
        base_ref = environment.get("EXPECTED_BASE_REF", "")
        if not base_ref or len(base_ref) > 1000:
            raise ValueError("missing or unbounded base ref")
        context.update(
            event_base=require_sha(environment.get("EXPECTED_BASE"), "event base"),
            event_merge=require_sha(environment.get("EXPECTED_MERGE"), "event merge"),
            live_base=live_ref(root, f"refs/heads/{base_ref}"),
            live_head=live_ref(root, f"refs/pull/{number}/head"),
            live_merge=live_ref(root, f"refs/pull/{number}/merge"),
            source_ref=f"refs/pull/{number}/head",
        )
    else:
        reference = environment.get("GITHUB_REF", "")
        context.update(source_ref=reference, live_head=live_ref(root, reference))
    validate_context(context)
    if git(root, "status", "--porcelain=v1"):
        raise ValueError("qualification checkout is not clean")
    return context


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        context = inspect(args.repository, dict(os.environ))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f"image source identity refused: {type(error).__name__}: {error}") from error
    print(json.dumps({"schema": "trillionnium.image-source-context.v1", "context": context,
                      "source_identity_verified": True, "installed_image_proven": False,
                      "promotion_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
