#!/usr/bin/env python3
"""Extract permanent D0A-02 run blocks into a reviewable shell runner."""

from __future__ import annotations

import textwrap
from pathlib import Path

WORKFLOW = Path(".github/workflows/servo-headed-runtime.yml")
OUTPUT = Path("tools/run_servo_headed_runtime_gate.sh")

STEPS = [
    ("Derive and validate exact Git identities", "identities"),
    ("Verify exact clean zero-patch Servo input", "verify-servo"),
    ("Install headed runtime dependencies", "install-deps"),
    ("Install Servo-declared Rust channel", "install-rust"),
    ("Install deterministic formatted product overlay", "install-overlay"),
    ("Compile exact-pin headed runtime", "compile"),
    ("Run causal one-window crash-and-recovery corpus", "run-runtime"),
    ("Enforce causal evidence and claim ceiling", "enforce-evidence"),
    ("Restore clean exact Servo checkout", "restore-servo"),
    ("Validate tracked desktop repository", "validate-repository"),
]


def extract_run_block(lines: list[str], step_name: str) -> str:
    marker = f"      - name: {step_name}"
    try:
        start = lines.index(marker)
    except ValueError as error:
        raise SystemExit(f"missing workflow step: {step_name}") from error

    run_line = None
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("      - name:"):
            break
        if lines[index] == "        run: |":
            run_line = index
            break
    if run_line is None:
        raise SystemExit(f"step has no literal run block: {step_name}")

    end = len(lines)
    for index in range(run_line + 1, len(lines)):
        if lines[index].startswith("      - name:"):
            end = index
            break
    raw = "\n".join(lines[run_line + 1 : end]).rstrip() + "\n"
    block = textwrap.dedent(raw)
    if not block.strip() or "set -euo pipefail" not in block:
        raise SystemExit(f"invalid run block for: {step_name}")
    return block


def function_name(command: str) -> str:
    return "step_" + command.replace("-", "_")


def main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks = [(command, extract_run_block(lines, name)) for name, command in STEPS]

    output = [
        "#!/usr/bin/env bash",
        "# Generated once from the reviewed permanent gate; do not self-modify.",
        "set -euo pipefail",
        "",
    ]
    for command, block in blocks:
        output.extend([f"{function_name(command)}() {{", block.rstrip(), "}", ""])

    output.extend([
        'case "${1:-}" in',
    ])
    for command, _ in blocks:
        output.extend([
            f"  {command})",
            f"    {function_name(command)}",
            "    ;;",
        ])
    output.extend([
        "  *)",
        '    printf \'unknown Servo headed gate command: %s\\n\' "${1:-}" >&2',
        "    exit 64",
        "    ;;",
        "esac",
        "",
    ])
    OUTPUT.write_text("\n".join(output), encoding="utf-8")
    OUTPUT.chmod(0o755)


if __name__ == "__main__":
    main()
