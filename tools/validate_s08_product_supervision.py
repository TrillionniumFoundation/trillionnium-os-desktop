#!/usr/bin/env python3
"""Validate the S08 hepta-browserd product Servo supervision boundary."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REQUIRED_PATHS = (
    "apps/hepta-browserd/Cargo.toml",
    "apps/hepta-browserd/src/lib.rs",
    "apps/hepta-browserd/src/servo_product_runtime.rs",
    "docs/architecture/S08_PRODUCT_SERVO_SUPERVISION.md",
    ".github/workflows/s08-product-servo-runtime.yml",
)

REQUIRED_DOC_HEADINGS = (
    "Scope",
    "Trust and authority boundary",
    "Runtime generations and stale references",
    "Crash and reconstruction protocol",
    "No automatic replay",
    "Durable receipt continuity",
    "Failure and logging policy",
    "Qualification",
    "Claim ceiling",
)

REQUIRED_SOURCE_TOKENS = (
    "pub struct RuntimeGeneration",
    "checked_add(1)",
    "pub struct SemanticReference",
    "pub struct BrowserdRuntimeSupervisor",
    "pub type ProductServoRuntime",
    "ServoBrowserActor",
    "pub fn validate_reference",
    "ProductRuntimeError::StaleGeneration",
    "pub fn content_process_crashed",
    "self.actor = None;",
    "pub fn reconstruct",
    "DispatchCompletion::IndeterminateAfterDispatch",
    "RuntimeState::ReplayReconciliationRequired",
    "RuntimeState::CrashLoopOpen",
    "pub fn reconcile_indeterminate",
)


def regular_file(root: Path, relative: str, errors: list[str]) -> Path:
    path = root / relative
    if path.is_symlink():
        errors.append(f"symlinked normative path: {relative}")
    if not path.is_file():
        errors.append(f"missing normative file: {relative}")
    return path


def strip_rust_comments(text: str) -> str:
    """Remove Rust comments while preserving string and character literals."""
    out: list[str] = []
    i = 0
    block_depth = 0
    state = "code"
    while i < len(text):
        pair = text[i : i + 2]
        char = text[i]
        if state == "line":
            if char == "\n":
                out.append(char)
                state = "code"
            else:
                out.append(" ")
            i += 1
            continue
        if state == "block":
            if pair == "/*":
                block_depth += 1
                out.extend("  ")
                i += 2
            elif pair == "*/":
                block_depth -= 1
                out.extend("  ")
                i += 2
                if block_depth == 0:
                    state = "code"
            else:
                out.append("\n" if char == "\n" else " ")
                i += 1
            continue
        if state in {"string", "char"}:
            out.append(char)
            if char == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if (state == "string" and char == '"') or (state == "char" and char == "'"):
                state = "code"
            i += 1
            continue
        if pair == "//":
            out.extend("  ")
            state = "line"
            i += 2
        elif pair == "/*":
            out.extend("  ")
            state = "block"
            block_depth = 1
            i += 2
        elif char == '"':
            out.append(char)
            state = "string"
            i += 1
        elif char == "'":
            out.append(char)
            state = "char"
            i += 1
        else:
            out.append(char)
            i += 1
    if block_depth:
        raise ValueError("unterminated Rust block comment")
    return "".join(out)


def visible_markdown(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    lines: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        match = re.match(r"(`{3,}|~{3,})", stripped)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker[0]
            elif marker[0] == fence:
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return "\n".join(lines)


def function_body(code: str, name: str) -> str | None:
    match = re.search(rf"\bfn\s+{re.escape(name)}\b[^{{]*{{", code)
    if match is None:
        return None
    start = match.end() - 1
    depth = 0
    for index in range(start, len(code)):
        if code[index] == "{":
            depth += 1
        elif code[index] == "}":
            depth -= 1
            if depth == 0:
                return code[start + 1 : index]
    return None


def validate(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    paths = {relative: regular_file(root, relative, errors) for relative in REQUIRED_PATHS}
    if errors:
        return errors

    temporary = sorted(
        path.relative_to(root).as_posix()
        for pattern in ("temporary-s08-*.yml", "temporary-s08-*.yaml")
        for path in (root / ".github/workflows").glob(pattern)
    )
    if temporary:
        errors.append("temporary S08 workflows remain: " + ", ".join(temporary))

    try:
        manifest = tomllib.loads(paths["apps/hepta-browserd/Cargo.toml"].read_text("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"invalid hepta-browserd manifest: {exc}")
        return errors
    dependency = manifest.get("dependencies", {}).get("hepta-browser-actor")
    if not isinstance(dependency, dict):
        errors.append("hepta-browserd must declare hepta-browser-actor as a path dependency")
    else:
        if dependency.get("path") != "../../crates/hepta-browser-actor":
            errors.append("hepta-browser-actor dependency must use the exact workspace path")
        if dependency.get("optional") is True:
            errors.append("product Servo binding must not be optional")

    lib_text = paths["apps/hepta-browserd/src/lib.rs"].read_text("utf-8")
    try:
        lib_code = strip_rust_comments(lib_text)
    except ValueError as exc:
        errors.append(str(exc))
        lib_code = ""
    if len(re.findall(r"\bmod\s+servo_product_runtime\s*;", lib_code)) != 1:
        errors.append("lib.rs must contain exactly one executable servo_product_runtime module declaration")
    for symbol in (
        "BrowserdRuntimeSupervisor",
        "ProductServoRuntime",
        "RuntimeGeneration",
        "SemanticReference",
    ):
        if not re.search(rf"\b{symbol}\b", lib_code):
            errors.append(f"lib.rs does not expose {symbol}")

    source_text = paths["apps/hepta-browserd/src/servo_product_runtime.rs"].read_text("utf-8")
    try:
        source = strip_rust_comments(source_text)
    except ValueError as exc:
        errors.append(str(exc))
        source = ""
    if re.search(r"\bunsafe\b", source):
        errors.append("product supervisor must not use unsafe")
    for token in REQUIRED_SOURCE_TOKENS:
        if token not in source:
            errors.append(f"missing product-supervision source token: {token}")
    if "wrapping_add" in source or "saturating_add" in source:
        errors.append("runtime generations and crash counters must use checked arithmetic")
    if source.count("operation(actor)") != 1:
        errors.append("dispatch must invoke the operation closure exactly once")
    crash_body = function_body(source, "content_process_crashed")
    if crash_body is None:
        errors.append("cannot parse content_process_crashed")
    elif "factory" in crash_body or "reconstruct(" in crash_body:
        errors.append("crash transition must not reconstruct or invoke the actor factory")
    reconcile_body = function_body(source, "reconcile_indeterminate")
    if reconcile_body is None:
        errors.append("cannot parse reconcile_indeterminate")
    elif "operation(" in reconcile_body or "dispatch(" in reconcile_body or "factory" in reconcile_body:
        errors.append("reconciliation must not dispatch, replay or reconstruct")

    doc = visible_markdown(
        paths["docs/architecture/S08_PRODUCT_SERVO_SUPERVISION.md"].read_text("utf-8")
    )
    headings = re.findall(r"^##\s+(.+?)\s*$", doc, flags=re.MULTILINE)
    if tuple(headings) != REQUIRED_DOC_HEADINGS:
        errors.append("S08 supervision document must contain the exact ordered normative headings")
    for phrase in (
        "attested AgentPort",
        "exact-pin Servo",
        "durable terminal or indeterminate receipt",
        "no automatic replay",
        "stale references",
        "CrashLoopOpen",
        "trusted chrome",
        "Claim ceiling",
    ):
        if phrase not in doc:
            errors.append(f"S08 supervision document omits required phrase: {phrase}")

    workflow = paths[".github/workflows/s08-product-servo-runtime.yml"].read_text("utf-8")
    if "contents: write" in workflow or "pull-requests: write" in workflow:
        errors.append("permanent S08 qualification workflow must remain read-only")
    if "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" not in workflow:
        errors.append("permanent S08 workflow must use the exact checkout pin")
    for token in (
        "exact-head:",
        "prospective-merge:",
        "cargo fmt --all --check",
        "cargo check --locked -p hepta-browserd --all-targets",
        "cargo clippy --locked -p hepta-browserd --all-targets -- -D warnings",
        "cargo test --locked -p hepta-browserd --all-targets",
        "python3 tools/validate_s08_product_supervision.py",
    ):
        if token not in workflow:
            errors.append(f"permanent S08 workflow omits executable gate token: {token}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = validate(args.root)
    if errors:
        for error in errors:
            print(f"S08-PRODUCT-SUPERVISION: {error}", file=sys.stderr)
        return 1
    print("S08-PRODUCT-SUPERVISION: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
