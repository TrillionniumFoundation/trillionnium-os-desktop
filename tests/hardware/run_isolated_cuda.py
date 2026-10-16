#!/usr/bin/env python3
"""Bounded subprocess runner for CUDA GEMM on a disposable local GPU lab ONLY.

The launcher validates reported CUDA results and records failure/timeout as
unknown device effects. It cannot attest that the host is Asterinas. It does
not reset devices, touch system drivers, or assert hardware DMA quiescence.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

try:
    from cuda_gemm import BDF_RE, GOLDEN_OUTPUT
except ImportError:  # importlib package use
    from tests.hardware.cuda_gemm import BDF_RE, GOLDEN_OUTPUT


class Blocked(RuntimeError):
    pass


def initial_evidence(bdf, name, timeout_seconds):
    """Common fail-closed schema even when validation prevents device access."""
    return {"schema": "a09.cuda-bounded-run.v1",
           "timestamp_utc": datetime.now(timezone.utc).isoformat(),
           "requested_guest_bdf": bdf, "requested_model": name,
           "requested_timeout_seconds": timeout_seconds,
           "status": "blocked", "child_exit_code": None,
           "child_evidence": None, "error": None,
           "host_asterinas_execution_attested": False,
           "guest_kernel_identity_attested": False,
           "physical_gpu_passthrough_attested": False,
           "DMA_quiescence_attested": False,
           "recovery_verified": False,
           "device_effect_if_failure": "unknown",
           "no_driver_rebind_no_device_reset": True}


def canonical_gpu_model(value):
    """Compare the *full* model, allowing only explicit vendor-name prefixes."""
    if not isinstance(value, str):
        return None
    model = " ".join(value.casefold().split())
    for prefix in ("nvidia geforce ", "nvidia ", "geforce "):
        if model.startswith(prefix):
            model = model[len(prefix):]
            break
    return model or None


def run_lab(bdf, name, isolated_lab, timeout_seconds=30, runner=subprocess.run):
    if not isolated_lab:
        raise Blocked("--isolated-lab is mandatory; NEVER test H3/training/production GPU")
    if not BDF_RE.fullmatch(bdf) or not name.strip():
        raise Blocked("exact isolated guest GPU BDF and nonempty model name required")
    if not 1 <= timeout_seconds <= 120:
        raise Blocked("bounded timeout must be between 1 and 120 seconds")

    script = Path(__file__).with_name("cuda_gemm.py").resolve()
    argv = [sys.executable, str(script), "--isolated-lab", "--require-name", name,
            "--require-bdf", bdf]
    start = time.monotonic()
    result = initial_evidence(bdf, name, timeout_seconds)
    try:
        completed = runner(argv, capture_output=True, text=True, timeout=timeout_seconds,
                           check=False)
    except subprocess.TimeoutExpired:
        result.update(status="timed_out_device_effect_unknown",
                      error="GPU child timeout; process termination is NOT proof of DMA quiescence")
        result["elapsed_seconds"] = round(time.monotonic() - start, 4)
        return 4, result
    except (OSError, ValueError) as exc:
        result.update(status="failed_runner", error=f"failed to start child: {exc}")
        result["elapsed_seconds"] = round(time.monotonic() - start, 4)
        return 1, result

    result["elapsed_seconds"] = round(time.monotonic() - start, 4)
    result["child_exit_code"] = completed.returncode
    try:
        child = json.loads(completed.stdout)
        if not isinstance(child, dict):
            raise ValueError("child JSON was not an object")
    except (ValueError, TypeError) as exc:
        result.update(status="failed_unparseable_child", error=str(exc),
                      child_stderr_tail=(completed.stderr or "")[-1000:])
        return 1, result
    result["child_evidence"] = child
    if completed.returncode == 2:
        result.update(status="blocked", error=child.get("error", "CUDA device unavailable"))
        return 2, result
    if completed.returncode != 0:
        result.update(status="failed_device_effect_unknown",
                      error=child.get("error", f"child returned {completed.returncode}"))
        return 1, result
    expected = {
        "schema": "a09.cuda-gemm.v1",
        "status": "passed_on_reported_cuda_environment",
        "expected_output_sha256": GOLDEN_OUTPUT,
        "actual_output_sha256": GOLDEN_OUTPUT,
        "no_cpu_fallback": True,
        "device_access_attempted": True,
        "device_memory_allocated": True,
        "cuda_kernel_launched": True,
        "synchronization_completed": True,
        "results_copied": True,
        "resources_released": True,
    }
    errors = [k for k, v in expected.items() if child.get(k) != v]
    identity = child.get("device")
    observed_bdf = identity.get("device_bdf") if isinstance(identity, dict) else None
    observed_model = identity.get("device_name") if isinstance(identity, dict) else None
    if (not isinstance(observed_bdf, str)
            or BDF_RE.fullmatch(observed_bdf) is None
            or observed_bdf.casefold() != bdf.casefold()
            or canonical_gpu_model(observed_model) != canonical_gpu_model(name)):
        errors.append("device PCI identity and model")
    if errors:
        result.update(status="failed_false_positive_child", error="invalid: " + ", ".join(errors))
        return 1, result
    result.update(status="guest_cuda_reported_pass_not_asterinas_attestation",
                  device_effect_if_failure="not_applicable_success")
    return 0, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolated-lab", action="store_true")
    parser.add_argument("--require-bdf", default="")
    parser.add_argument("--require-name", default="RTX 4060")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    try:
        code, evidence = run_lab(args.require_bdf, args.require_name,
                                 args.isolated_lab, args.timeout_seconds)
    except Blocked as exc:
        evidence = initial_evidence(args.require_bdf, args.require_name,
                                    args.timeout_seconds)
        evidence.update(error=str(exc), attempted_device_access=False)
        code = 2
    payload = json.dumps(evidence, sort_keys=True, indent=2) + "\n"
    if args.output == "-":
        print(payload, end="")
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
