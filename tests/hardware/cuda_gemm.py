#!/usr/bin/env python3
"""CUDA Driver API + NVRTC FP32 GEMM: no CPU fallback and no destructive reset.

Exit 0: real CUDA device result + release verified; 2: environment blocked; 1: failed.
A Linux host pass is explicitly NOT an Asterinas GPU/VM pass.
"""
import argparse
import ctypes as C
from ctypes.util import find_library
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import platform
import signal
import struct
import sys
import threading
import time

N = 16
CUDA_SOURCE = r'''
extern "C" __global__ void gemm16(const float *a, const float *b, float *c) {
    int r = blockIdx.x;
    int col = threadIdx.x;
    if (r >= 16 || col >= 16) return;
    float acc = 0.0f;
    for (int k = 0; k < 16; ++k) acc += a[r * 16 + k] * b[k * 16 + col];
    c[r * 16 + col] = acc;
}
'''


class Blocked(RuntimeError):
    pass


class GpuError(RuntimeError):
    pass


class TimeoutExpired(GpuError):
    """The bounded test window expired before the device operation finished."""


STAGES = (
    "enumerate_device",
    "compile_kernel",
    "allocate_device_memory",
    "copy_inputs",
    "submit_command",
    "synchronize",
    "copy_result",
    "compare_reference",
    "release_resources",
    "failure_recovery",
)


def new_stage_status():
    """Return a machine-readable scorecard for the seven proof obligations."""
    return {name: "not_run" for name in STAGES}


def _mark_in_progress_stages_failed(stages):
    for name, status in stages.items():
        if status == "in_progress":
            stages[name] = "failed"


def timeout_available():
    """Only the independent Linux subprocess supervisor is an enforced deadline."""
    from cuda_process_supervisor import available
    return available()


def run_bounded(fn, timeout_seconds):
    """Legacy in-process native timeout is forbidden: Python SIGALRM is unsafe."""
    raise Blocked("in-process SIGALRM cannot bound a native CUDA call; use supervised main")


def inputs():
    a = [float((r * 3 + k * 5) % 7 - 3) for r in range(N) for k in range(N)]
    b = [float((k * 2 + col * 3) % 5 - 2) for k in range(N) for col in range(N)]
    return a, b


def reference(a, b):
    return [sum(a[r * N + k] * b[k * N + col] for k in range(N))
            for r in range(N) for col in range(N)]


def digest(values):
    return hashlib.sha256(struct.pack("<" + "f" * len(values), *values)).hexdigest()


def compare(actual, expected):
    if len(actual) != len(expected):
        return {"length_expected": len(expected), "length_actual": len(actual)}
    for i, (x, y) in enumerate(zip(actual, expected)):
        if not math.isfinite(x) or x != y:
            return {"index": i, "actual": x if math.isfinite(x) else str(x), "expected": y}
    return None


def library(candidates):
    errors = []
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return C.CDLL(candidate)
        except OSError as exc:
            errors.append(str(exc))
    raise Blocked("required CUDA library unavailable: " + ", ".join(str(x) for x in candidates))


class Api:
    def __init__(self, lib, prefix):
        self.lib, self.prefix = lib, prefix

    def bind(self, symbol, argtypes):
        try:
            fn = getattr(self.lib, symbol)
        except AttributeError as exc:
            raise Blocked(f"{self.prefix} missing symbol {symbol}") from exc
        fn.argtypes = argtypes
        fn.restype = C.c_int
        return fn

    def call(self, symbol, argtypes, *args):
        rc = self.bind(symbol, argtypes)(*args)
        if rc != 0:
            raise GpuError(f"{self.prefix}.{symbol} returned {rc}")


def gpu_gemm(required_name, required_bdf, stages=None):
    stages = new_stage_status() if stages is None else stages
    cuda = Api(library(["libcuda.so.1", find_library("cuda")]), "CUDA")
    # Driver API is mandatory; a software rendering backend cannot satisfy these calls.
    stages["enumerate_device"] = "in_progress"
    cuda.call("cuInit", [C.c_uint], 0)
    count = C.c_int()
    cuda.call("cuDeviceGetCount", [C.POINTER(C.c_int)], C.byref(count))
    if count.value < 1:
        stages["enumerate_device"] = "blocked"
        raise Blocked("CUDA driver reports zero usable devices")
    selected = None
    seen = []
    for index in range(count.value):
        handle = C.c_int()
        cuda.call("cuDeviceGet", [C.POINTER(C.c_int), C.c_int], C.byref(handle), index)
        name_buf = C.create_string_buffer(256)
        cuda.call("cuDeviceGetName", [C.POINTER(C.c_char), C.c_int, C.c_int],
                  name_buf, len(name_buf), handle)
        name = name_buf.value.decode("utf-8", "replace")
        pci_buf = C.create_string_buffer(32)
        cuda.call("cuDeviceGetPCIBusId", [C.POINTER(C.c_char), C.c_int, C.c_int],
                  pci_buf, len(pci_buf), handle)
        bdf = pci_buf.value.decode("ascii", "replace")
        seen.append({"name": name, "bdf": bdf})
        if (required_name.lower() in name.lower() and
                (not required_bdf or required_bdf.lower() == bdf.lower())):
            selected = (handle, name, bdf, index)
            break
    if selected is None:
        stages["enumerate_device"] = "blocked"
        raise Blocked(f"no CUDA GPU matches target name={required_name!r} "
                      f"bdf={required_bdf!r}; enumerated={seen}")
    stages["enumerate_device"] = "passed"
    device, name, bdf, index = selected
    cc_major, cc_minor, version = C.c_int(), C.c_int(), C.c_int()
    for attribute, destination in ((75, cc_major), (76, cc_minor)):
        cuda.call("cuDeviceGetAttribute", [C.POINTER(C.c_int), C.c_int, C.c_int],
                  C.byref(destination), attribute, device)
    cuda.call("cuDriverGetVersion", [C.POINTER(C.c_int)], C.byref(version))
    nvrtc = Api(library(["libnvrtc.so", find_library("nvrtc")]), "NVRTC")
    nv_major, nv_minor = C.c_int(), C.c_int()
    nvrtc.call("nvrtcVersion", [C.POINTER(C.c_int), C.POINTER(C.c_int)],
               C.byref(nv_major), C.byref(nv_minor))
    metadata = {"device_name": name, "device_bdf": bdf, "device_index": index,
                "compute_capability": f"{cc_major.value}.{cc_minor.value}",
                "cuda_driver_api_version": version.value,
                "nvrtc_version": f"{nv_major.value}.{nv_minor.value}",
                "driver_api": "CUDA Driver API", "compiler": "NVRTC"}
    program = C.c_void_p()
    ptx = None
    stages["compile_kernel"] = "in_progress"
    nvrtc.call("nvrtcCreateProgram", [C.POINTER(C.c_void_p), C.c_char_p, C.c_char_p,
                                       C.c_int, C.POINTER(C.c_char_p), C.POINTER(C.c_char_p)],
               C.byref(program), CUDA_SOURCE.encode(), b"gemm16.cu", 0, None, None)
    try:
        arch = f"--gpu-architecture=compute_{cc_major.value}{cc_minor.value}".encode()
        options = (C.c_char_p * 1)(arch)
        rc = nvrtc.bind("nvrtcCompileProgram", [C.c_void_p, C.c_int,
                                                  C.POINTER(C.c_char_p)])(program, 1, options)
        if rc:
            log_len = C.c_size_t()
            nvrtc.call("nvrtcGetProgramLogSize", [C.c_void_p, C.POINTER(C.c_size_t)],
                       program, C.byref(log_len))
            log = C.create_string_buffer(max(1, log_len.value))
            nvrtc.call("nvrtcGetProgramLog", [C.c_void_p, C.c_void_p], program, log)
            raise GpuError(f"NVRTC compile {rc}: {log.value.decode(errors='replace')[:2000]}")
        ptx_len = C.c_size_t()
        nvrtc.call("nvrtcGetPTXSize", [C.c_void_p, C.POINTER(C.c_size_t)], program, C.byref(ptx_len))
        ptx = C.create_string_buffer(ptx_len.value)
        nvrtc.call("nvrtcGetPTX", [C.c_void_p, C.c_void_p], program, ptx)
        stages["compile_kernel"] = "passed"
    finally:
        try:
            nvrtc.call("nvrtcDestroyProgram", [C.POINTER(C.c_void_p)], C.byref(program))
        except GpuError:
            if stages["compile_kernel"] == "passed":
                stages["compile_kernel"] = "failed"
            raise
    ctx, module, function = C.c_void_p(), C.c_void_p(), C.c_void_p()
    ptrs = []
    cleanup_errors = []
    failure = None
    output = None
    timed_out = False
    try:
        cuda.call("cuCtxCreate_v2", [C.POINTER(C.c_void_p), C.c_uint, C.c_int],
                  C.byref(ctx), 0, device)
        cuda.call("cuModuleLoadData", [C.POINTER(C.c_void_p), C.c_void_p],
                  C.byref(module), C.cast(ptx, C.c_void_p))
        cuda.call("cuModuleGetFunction", [C.POINTER(C.c_void_p), C.c_void_p, C.c_char_p],
                  C.byref(function), module, b"gemm16")
        a, b = inputs()
        host_a = (C.c_float * (N * N))(*a)
        host_b = (C.c_float * (N * N))(*b)
        host_c = (C.c_float * (N * N))()
        stages["allocate_device_memory"] = "in_progress"
        for _ in range(3):
            dev_ptr = C.c_uint64()
            cuda.call("cuMemAlloc_v2", [C.POINTER(C.c_uint64), C.c_size_t],
                      C.byref(dev_ptr), C.sizeof(host_a))
            ptrs.append(dev_ptr)
        stages["allocate_device_memory"] = "passed"
        stages["copy_inputs"] = "in_progress"
        for dev_ptr, host in ((ptrs[0], host_a), (ptrs[1], host_b)):
            cuda.call("cuMemcpyHtoD_v2", [C.c_uint64, C.c_void_p, C.c_size_t],
                      dev_ptr, C.cast(host, C.c_void_p), C.sizeof(host))
        stages["copy_inputs"] = "passed"
        # Kernel parameters are pointers to the three CUdeviceptr values, as required
        # by cuLaunchKernel's void **kernelParams ABI (not the device addresses alone).
        kernel_args = (C.c_void_p * 3)()
        for position, ptr in enumerate(ptrs):
            kernel_args[position] = C.cast(C.byref(ptr), C.c_void_p)
        stages["submit_command"] = "in_progress"
        cuda.call("cuLaunchKernel", [C.c_void_p, C.c_uint, C.c_uint, C.c_uint,
                                       C.c_uint, C.c_uint, C.c_uint, C.c_uint,
                                       C.c_void_p, C.POINTER(C.c_void_p), C.c_void_p],
                  function, N, 1, 1, N, 1, 1, 0, None, kernel_args, None)
        stages["submit_command"] = "passed"
        stages["synchronize"] = "in_progress"
        cuda.call("cuCtxSynchronize", [])
        stages["synchronize"] = "passed"
        stages["copy_result"] = "in_progress"
        cuda.call("cuMemcpyDtoH_v2", [C.c_void_p, C.c_uint64, C.c_size_t],
                  C.cast(host_c, C.c_void_p), ptrs[2], C.sizeof(host_c))
        output = list(host_c)
        stages["copy_result"] = "passed"
    except TimeoutExpired as exc:
        timed_out = True
        failure = exc
    except Exception as exc:
        failure = exc
    finally:
        # A timed-out device call may still be executing asynchronously. Do not issue
        # more CUDA calls in that process; the supervisor's process exit is the safe
        # containment boundary and no reset is attempted.
        if timed_out:
            _mark_in_progress_stages_failed(stages)
        else:
            has_resources = bool(ptrs) or bool(module.value) or bool(ctx.value)
            if has_resources:
                stages["release_resources"] = "in_progress"
            for ptr in reversed(ptrs):
                if not ptr.value:
                    continue
                try:
                    cuda.call("cuMemFree_v2", [C.c_uint64], ptr)
                except Exception as exc:
                    cleanup_errors.append(str(exc))
            if module.value:
                try:
                    cuda.call("cuModuleUnload", [C.c_void_p], module)
                except Exception as exc:
                    cleanup_errors.append(str(exc))
            if ctx.value:
                try:
                    cuda.call("cuCtxDestroy_v2", [C.c_void_p], ctx)
                except Exception as exc:
                    cleanup_errors.append(str(exc))
            if has_resources:
                stages["release_resources"] = "failed" if cleanup_errors else "passed"
    if failure:
        if cleanup_errors:
            raise type(failure)(str(failure) + f"; cleanup errors: {cleanup_errors}") from failure
        raise failure
    if cleanup_errors:
        raise GpuError(f"resource cleanup failed: {cleanup_errors}")
    return metadata, output


def _base_evidence(expected, a, b, timeout_seconds):
    return {
        "schema": "a09.cuda-gemm.v2",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "blocked",
        "test": "gemm16_f32",
        "dimension": [N, N, N],
        "input_a_sha256": digest(a),
        "input_b_sha256": digest(b),
        "expected_output_sha256": digest(expected),
        "driver_api": "CUDA Driver API",
        "compiler": "NVRTC",
        "reference": "CPU scalar deterministic integer-valued FP32",
        "reported_execution_kernel": f"{platform.system()} {platform.release()}",
        "asterinas_execution_verified": False,
        "vmm_passthrough_verified": False,
        "physical_device_assignment_verified": False,
        "reset_or_failure_recovery_verified": False,
        "execution_provenance": {
            "process_id": os.getpid(),
            "process_executable": os.path.realpath(sys.executable),
            "process_started_utc": datetime.now(timezone.utc).isoformat(),
            "kernel_name": platform.system(),
            "kernel_release": platform.release(),
            "machine": platform.machine(),
            "execution_layer": "linux_process_cuda_driver_api",
            "asterinas_execution_verified": False,
            "vmm_passthrough_verified": False,
            "physical_device_assignment_verified": False,
        },
        "timeout_seconds": timeout_seconds,
        "no_cpu_fallback": True,
        "device": None,
        "stages": new_stage_status(),
        # This test never resets or fault-injects a device. A separate isolated
        # recovery experiment must provide evidence for this obligation.
        "failure_recovery_verified": False,
    }


def _worker_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-name", default="RTX 4060")
    parser.add_argument("--require-bdf", default="", help="optional exact PCI BDF from read-only probe")
    parser.add_argument("--timeout-seconds", type=float, default=30.0,
                        help="bounded wall-clock window for CUDA calls (default: 30)")
    parser.add_argument("--output", default="-", help="'-' prints JSON")
    args = parser.parse_args()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be a finite positive number")
    a, b = inputs()
    expected = reference(a, b)
    evidence = _base_evidence(expected, a, b, args.timeout_seconds)
    evidence["timeout_enforced"] = False
    started = time.monotonic()
    try:
        # This path executes ONLY in a separately supervised child process.
        # A native CUDA call can block forever; the parent performs kill/reap.
        device, output = gpu_gemm(args.require_name, args.require_bdf, evidence["stages"])
        evidence["device"] = device
        evidence["actual_output_sha256"] = digest(output)
        evidence["stages"]["compare_reference"] = "in_progress"
        mismatch = compare(output, expected)
        if mismatch:
            evidence["stages"]["compare_reference"] = "failed"
            raise GpuError(f"GPU numerical mismatch: {mismatch}")
        evidence["stages"]["compare_reference"] = "passed"
        evidence.update(status="passed_on_reported_cuda_environment", error=None,
                        device_memory_allocated=(
                            evidence["stages"]["allocate_device_memory"] == "passed"),
                        cuda_kernel_launched=(evidence["stages"]["submit_command"] == "passed"),
                        synchronization_completed=(evidence["stages"]["synchronize"] == "passed"),
                        results_copied=(evidence["stages"]["copy_result"] == "passed"),
                        resources_released=(evidence["stages"]["release_resources"] == "passed"))
        rc = 0
    except Blocked as exc:
        _mark_in_progress_stages_failed(evidence["stages"])
        evidence.update(status="blocked", error=str(exc))
        rc = 2
    except TimeoutExpired as exc:
        _mark_in_progress_stages_failed(evidence["stages"])
        evidence.update(status="timeout", error=str(exc),
                        reset_or_failure_recovery_verified=False)
        rc = 1
    except (GpuError, OSError, ValueError) as exc:
        _mark_in_progress_stages_failed(evidence["stages"])
        evidence.update(status="failed", error=str(exc))
        rc = 1
    evidence["elapsed_seconds"] = round(time.monotonic() - started, 6)
    evidence["stages"]["failure_recovery"] = "not_run"
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        print(payload, end="")
    else:
        from pathlib import Path
        Path(args.output).write_text(payload, encoding="utf-8")
    return rc


def _strict_worker_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate worker evidence key")
        out[key] = value
    return out


def _supervised_main():
    """Never enter CUDA/FFI in the command's parent process."""
    from pathlib import Path
    from tempfile import TemporaryDirectory
    # The fixed sibling helper is trusted code from this checked-out tree.
    # Python -I omits the script directory from import lookup by default.
    host_dir = str(Path(__file__).resolve().parent)
    if host_dir not in sys.path:
        sys.path.insert(0, host_dir)
    from cuda_process_supervisor import available, run_worker

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-name", default="RTX 4060")
    parser.add_argument("--require-bdf", default="")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be a finite positive number")

    a, b = inputs()
    result = _base_evidence(reference(a, b), a, b, args.timeout_seconds)
    result["timeout_enforced"] = False
    result["error"] = None
    exit_code = 2
    if not available():
        result.update(status="blocked", error="independent Linux worker supervisor unavailable")
    else:
        with TemporaryDirectory(prefix="a09-cuda-supervised-") as private:
            worker_report = Path(private) / "worker.json"
            command = [sys.executable, "-I", os.path.realpath(__file__),
                       "--_a09_worker", "--require-name", args.require_name,
                       "--require-bdf", args.require_bdf,
                       "--timeout-seconds", str(args.timeout_seconds),
                       "--output", str(worker_report)]
            try:
                status, supervisor = run_worker(command, args.timeout_seconds)
                result["worker_supervision"] = supervisor
                result["timeout_enforced"] = bool(
                    supervisor.get("worker_reaped")
                    and not supervisor.get("worker_group_incomplete")
                )
                if supervisor["timed_out"]:
                    result.update(status="timeout",
                                  error="native worker exceeded wall-clock deadline; effect unknown",
                                  reset_or_failure_recovery_verified=False)
                    exit_code = 1
                elif supervisor.get("worker_group_incomplete"):
                    # A reaped *leader* does not prove its worker session is
                    # drained. Do not read a forged success report or claim
                    # bounded CUDA effects with surviving group members.
                    result.update(
                        status="failed",
                        error="worker exited but process group remains; effect unknown",
                        reset_or_failure_recovery_verified=False,
                    )
                    exit_code = 1
                elif not supervisor["worker_reaped"]:
                    result.update(status="failed", error="worker not reaped; effect unknown")
                    exit_code = 1
                else:
                    # Parse only the bounded report written inside the private
                    # host-owned directory. Never parse unbounded worker logs.
                    size = worker_report.stat().st_size
                    if not 0 < size <= 65536:
                        raise ValueError("worker report size invalid")
                    report = json.loads(
                        worker_report.read_text(encoding="utf-8"),
                        object_pairs_hook=_strict_worker_pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite worker value")),
                    )
                    if (not isinstance(report, dict)
                        or report.get("schema") != "a09.cuda-gemm.v2"
                        or report.get("status") not in (
                            "blocked", "failed", "timeout", "passed_on_reported_cuda_environment"
                        ) or not isinstance(report.get("stages"), dict)
                        or set(report["stages"]) != set(STAGES)):
                        raise ValueError("malformed worker evidence")
                    mapped = {"blocked": 2, "failed": 1, "timeout": 1,
                              "passed_on_reported_cuda_environment": 0}
                    if status != mapped[report["status"]]:
                        raise ValueError("worker exit disagrees with evidence")
                    supervisor["effect_result_known"] = True
                    report["worker_supervision"] = supervisor
                    report["timeout_enforced"] = True
                    result = report
                    exit_code = status
            except (OSError, ValueError, GpuError) as exc:
                result.update(status="failed", error="untrusted or absent worker report: " + str(exc),
                              reset_or_failure_recovery_verified=False)
                exit_code = 1
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        print(payload, end="")
    else:
        from pathlib import Path
        Path(args.output).write_text(payload, encoding="utf-8")
    return exit_code


def main():
    # Internal worker mode is not an independent hardware authorization API.
    if "--_a09_worker" in sys.argv[1:]:
        sys.argv.remove("--_a09_worker")
        return _worker_main()
    return _supervised_main()


if __name__ == "__main__":
    raise SystemExit(main())
