#!/usr/bin/env python3
"""Materialize a passing D0A-01 compatibility report into the product tree."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

EXPECTED_COMMIT = "670ae8a70801b162e186f81cbb5bdd2d59c39108"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--servo-root", type=Path, required=True)
    return parser.parse_args()


def normalize(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize(item, replacements)
            for key, item in value.items()
            if key not in {"log", "output"}
        }
    if isinstance(value, list):
        return [normalize(item, replacements) for item in value]
    if isinstance(value, str):
        for source, target in replacements.items():
            value = value.replace(source, target)
        value = re.sub(
            r"/tmp/trillionnium-servo-probe-[^/\s]+",
            "<temporary-probe>",
            value,
        )
        return value
    return value


def append_once(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        path.write_text(text.rstrip() + "\n\n" + block.strip() + "\n", encoding="utf-8")


def add_required_path(validator: Path, required: str) -> None:
    text = validator.read_text(encoding="utf-8")
    if required in text:
        return
    match = re.search(r"(REQUIRED_PATHS\s*=\s*\[)(.*?)(\n\])", text, flags=re.S)
    if match is None:
        raise RuntimeError("REQUIRED_PATHS list not found")
    body = match.group(2) + f'\n    "{required}",'
    validator.write_text(
        text[: match.start(2)] + body + text[match.end(2) :],
        encoding="utf-8",
    )


def main() -> int:
    options = parse_args()
    root = options.repository_root.resolve()
    result_root = options.result_root.resolve()
    servo_root = options.servo_root.resolve()

    report_source = result_root / "servo-embedder-compat.json"
    sentinel_source = result_root / "servo_api_sentinel.rs"
    probe_source = result_root / "probe-result.json"
    for path in (report_source, sentinel_source, probe_source):
        if not path.is_file():
            raise RuntimeError(f"missing D0A-01 result: {path}")

    report = json.loads(report_source.read_text(encoding="utf-8"))
    if report.get("status") != "PASS":
        raise RuntimeError("D0A-01 report is not PASS")
    if report.get("source", {}).get("actual_commit") != EXPECTED_COMMIT:
        raise RuntimeError("D0A-01 report has the wrong Servo commit")
    if report.get("headed_reference", {}).get("passed") is not True:
        raise RuntimeError("D0A-01 headed reference did not pass")
    if report.get("final_public_api_sentinel", {}).get("passed") is not True:
        raise RuntimeError("D0A-01 aggregate API sentinel did not pass")

    experiment = root / "experiments" / "servo-embedder-probe"
    (experiment / "src").mkdir(parents=True, exist_ok=True)
    shutil.copy2(sentinel_source, experiment / "src" / "main.rs")

    replacements = {
        str(servo_root): ".servo-source",
        str(root): ".",
        str(result_root): "target/servo-compatibility",
    }
    normalized_report = normalize(report, replacements)
    normalized_probe = normalize(
        json.loads(probe_source.read_text(encoding="utf-8")),
        replacements,
    )
    manifests = root / "manifests"
    (manifests / "servo-embedder-compat.json").write_text(
        json.dumps(normalized_report, indent=2) + "\n",
        encoding="utf-8",
    )
    (manifests / "servo-probe-result.json").write_text(
        json.dumps(normalized_probe, indent=2) + "\n",
        encoding="utf-8",
    )

    append_once(
        root / "README.md",
        "## D0A-01 pinned Servo compile compatibility",
        """
## D0A-01 pinned Servo compile compatibility

The exact Servo commit now has a machine-reproducible compile gate. The gate
resolves and compiles the required public embedder API, compiles one aggregate
sentinel, and runs `cargo check --locked` for Servo's own headed reference
shell. This is compile evidence only; the product wrapper, first frame and
native input remain later checkpoints.
""",
    )
    append_once(
        root / "docs" / "CURRENT_STATE.md",
        "## 2026-08-28 D0A-01 checkpoint",
        """
## 2026-08-28 D0A-01 checkpoint

The pinned Servo public embedder boundary and upstream headed reference package
pass the D0A-01 compile gate. `manifests/servo-embedder-compat.json` records the
exact public paths, source locations, Cargo.lock digest, selected event-loop
entry and check commands. No Servo runtime, window, frame, input or network was
exercised. D0A-02 now owns the product wrapper and headed lifecycle spike.
""",
    )
    append_once(
        root / "docs" / "DESKTOP_PLAN-2026-08-28-d5.md",
        "### D0A-01 implementation checkpoint",
        """
### D0A-01 implementation checkpoint

The exact Servo source lock now passes an executable compatibility gate: public
`Servo`, `WebView`, builder, rendering-context, waker and delegate boundaries are
compiled from an external sentinel, and Servo's headed reference shell passes
`cargo check --locked`. The local patch ledger is zero-delta. This closes only
compile compatibility. D0A-02 must instantiate the product-owned headed wrapper,
prove lifecycle and produce first-frame evidence without WebDriver.
""",
    )

    checkpoint = {
        "id": "TOS-D0A-01",
        "status": "PASS_COMPILE_ONLY_NO_RUNTIME",
        "servo_commit": EXPECTED_COMMIT,
        "evidence": "docs/evidence/2026-08-28-d0a01-servo-compatibility.md",
        "compatibility_manifest": "manifests/servo-embedder-compat.json",
    }
    for relative in ("manifests/repository-state.json", "docs/MANIFEST.json"):
        path = root / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        checkpoints = data.setdefault("implementation_checkpoints", [])
        existing = next(
            (
                item
                for item in checkpoints
                if isinstance(item, dict) and item.get("id") == checkpoint["id"]
            ),
            None,
        )
        if existing is None:
            checkpoints.append(checkpoint)
        else:
            existing.clear()
            existing.update(checkpoint)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    gitignore = root / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines()
    for item in (
        ".servo-source/",
        "experiments/servo-embedder-probe/Cargo.lock",
        "experiments/servo-embedder-probe/target/",
    ):
        if item not in lines:
            lines.append(item)
    gitignore.write_text("\n".join(lines) + "\n", encoding="utf-8")

    validator = root / "tools" / "validate_repository.py"
    for required in (
        "tools/verify_servo_compatibility.py",
        "manifests/servo-api-requirements.v1.json",
        "manifests/servo-patch-ledger.v1.json",
        "manifests/servo-embedder-compat.json",
        "manifests/servo-probe-result.json",
        "experiments/servo-embedder-probe/Cargo.toml",
        "experiments/servo-embedder-probe/src/main.rs",
        "docs/architecture/SERVO_EMBEDDER_COMPATIBILITY.md",
    ):
        add_required_path(validator, required)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
