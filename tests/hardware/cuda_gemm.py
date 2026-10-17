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
import stat
from pathlib import Path
import struct
import sys
import tempfile
import time

import cuda_process_supervisor as process_supervisor

# Reuse one exact PCI/model identity representation in both the CUDA client
# and the Asterinas/Linux cross-kernel acceptance checker.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "support/hardware"))
from pci_identity import canonical_bdf, matches_target_model
from evidence_output import write_evidence_output
from cuda_worker_identity import validate_supervised_cuda_success

N = 16
MAX_CUDA_ENUM_DEVICES = 64
MAX_NVRTC_LOG_BYTES = 64 * 1024
MAX_NVRTC_PTX_BYTES = 8 * 1024 * 1024
MAX_WORKER_REPORT_BYTES = 64 * 1024
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
    """A worker-local test hook; production deadlines are OS-supervised."""


def checked_nvrtc_size(size, limit, purpose):
    """Reject compiler-reported sizes before allocating Python memory."""
    if type(size) is not int or size < 1 or size > limit:
        raise GpuError(f"NVRTC {purpose} size outside 1..{limit} bytes: {size}")
    return size


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
    """Whether a separate Linux worker can be killed and reaped safely."""
    return process_supervisor.available()


def run_bounded(fn, timeout_seconds):
    """Reject the retired in-process deadline path.

    A Python signal cannot safely bound a foreign CUDA/NVRTC call: the handler
    may run only after the C call returns while the device effect continues.
    The command-line path below always uses ``cuda_process_supervisor``.
    """
    del fn, timeout_seconds
    raise Blocked("in-process CUDA deadline disabled; use the OS worker supervisor")


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
    target_bdf = canonical_bdf(required_bdf)
    if target_bdf is None:
        stages["enumerate_device"] = "blocked"
        raise Blocked("explicit valid physical/guest PCI BDF required before CUDA device access")
    # A09 Route C is deliberately pinned to the discrete RTX 4060; do not
    # silently turn RTX 4060 Ti or an unrelated RTX GPU into the lab target.
    if not matches_target_model(required_name, "RTX 4060"):
        stages["enumerate_device"] = "blocked"
        raise Blocked("A09 lab compute target must be the exact RTX 4060 model")
    cuda = Api(library(["libcuda.so.1", find_library("cuda")]), "CUDA")
    # Driver API is mandatory; a software rendering backend cannot satisfy these calls.
    stages["enumerate_device"] = "in_progress"
    cuda.call("cuInit", [C.c_uint], 0)
    count = C.c_int()
    cuda.call("cuDeviceGetCount", [C.POINTER(C.c_int)], C.byref(count))
    if count.value < 1:
        stages["enumerate_device"] = "blocked"
        raise Blocked("CUDA driver reports zero usable devices")
    if count.value > MAX_CUDA_ENUM_DEVICES:
        stages["enumerate_device"] = "blocked"
        raise Blocked("CUDA driver reports an unreasonable device count; refusing unbounded enumeration")
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
        if matches_target_model(name, required_name) and canonical_bdf(bdf) == target_bdf:
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
    if (cc_major.value, cc_minor.value) != (8, 9):
        stages["enumerate_device"] = "blocked"
        raise Blocked("selected GPU is not RTX 4060 CUDA compute capability 8.9")
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
            log = C.create_string_buffer(
                checked_nvrtc_size(log_len.value, MAX_NVRTC_LOG_BYTES, "diagnostic log"))
            nvrtc.call("nvrtcGetProgramLog", [C.c_void_p, C.c_void_p], program, log)
            raise GpuError(f"NVRTC compile {rc}: {log.value.decode(errors='replace')[:2000]}")
        ptx_len = C.c_size_t()
        nvrtc.call("nvrtcGetPTXSize", [C.c_void_p, C.POINTER(C.c_size_t)], program, C.byref(ptx_len))
        ptx = C.create_string_buffer(
            checked_nvrtc_size(ptx_len.value, MAX_NVRTC_PTX_BYTES, "PTX program"))
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
        "device_access_attempted": False,
        "device": None,
        "stages": new_stage_status(),
        # This test never resets or fault-injects a device. A separate isolated
        # recovery experiment must provide evidence for this obligation.
        "failure_recovery_verified": False,
    }


def _write_evidence(evidence, output):
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    write_evidence_output(output, payload)


def read_supervised_worker_report(path):
    """Bounded, single-fd Linux receipt read; no symlinks, FIFO or duplicates.

    This is an OS worker receipt, not a cryptographic attestation of GPU/DMA.
    """
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or not 0 < before.st_size <= MAX_WORKER_REPORT_BYTES):
            raise ValueError("worker report must be bounded regular file")
        raw = os.read(fd, MAX_WORKER_REPORT_BYTES + 1)
        after = os.fstat(fd)
        identity_before = (before.st_dev, before.st_ino, before.st_size,
                           before.st_mtime_ns, before.st_ctime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size,
                          after.st_mtime_ns, after.st_ctime_ns)
        if (len(raw) != before.st_size or len(raw) > MAX_WORKER_REPORT_BYTES
                or identity_before != identity_after):
            raise ValueError("worker report changed or exceeded byte limit")
    finally:
        os.close(fd)

    def unique_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate worker JSON key: " + key)
            obj[key] = value
        return obj

    def reject_nonfinite(value):
        raise ValueError("nonfinite worker JSON value: " + value)

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                      parse_constant=reject_nonfinite)


def _run_local(args):
    """Run inside an already-supervised worker or a unit-test-only seam."""
    a, b = inputs()
    expected = reference(a, b)
    evidence = _base_evidence(expected, a, b, args.timeout_seconds)
    # This path has no deadline guarantee. The production parent overwrites
    # this field only after the OS worker has been reaped or a timeout recorded.
    evidence["timeout_enforced"] = False
    evidence["execution_provenance"]["execution_layer"] = (
        "linux_worker_cuda_driver_api")
    started = time.monotonic()
    try:
        # No signal/alarm is allowed around foreign CUDA/NVRTC calls. The
        # parent process supervisor owns the deadline and kill/reap boundary.
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
                        device_access_attempted=True,
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
    _write_evidence(evidence, args.output)
    return rc


def _unknown_effect_evidence(args, record, error, status="timeout", timeout_enforced=False):
    a, b = inputs()
    evidence = _base_evidence(reference(a, b), a, b, args.timeout_seconds)
    evidence.update(status=status, error=error, timeout_enforced=timeout_enforced,
                    supervisor=record, failure_recovery_verified=False)
    evidence["execution_provenance"]["execution_layer"] = (
        "linux_supervised_worker_cuda_driver_api")
    evidence["execution_provenance"]["supervisor"] = record
    # The parent cannot know which native CUDA call was active when SIGKILL
    # arrived. Every obligation remains unknown-effect until an external
    # device-quiescence/reset procedure proves otherwise.
    for name in evidence["stages"]:
        evidence["stages"][name] = "unknown_effect"
    return evidence


def _run_supervised(args):
    """Launch CUDA in an isolated process session with a kill/reap deadline."""
    started = time.monotonic()
    if not timeout_available():
        a, b = inputs()
        evidence = _base_evidence(reference(a, b), a, b, args.timeout_seconds)
        evidence.update(status="blocked",
                        error="OS process supervisor unavailable",
                        timeout_enforced=False)
        _write_evidence(evidence, args.output)
        return 2

    with tempfile.TemporaryDirectory(prefix="a09-cuda-worker-") as directory:
        worker_output = os.path.join(directory, "worker-evidence.json")
        worker_args = [
            sys.executable, os.path.realpath(__file__), "--worker",
            "--require-name", args.require_name,
            "--timeout-seconds", str(args.timeout_seconds),
            "--output", worker_output,
        ]
        if args.require_bdf:
            worker_args.extend(("--require-bdf", args.require_bdf))
        try:
            code, record = process_supervisor.run_worker(
                worker_args, args.timeout_seconds)
        except (OSError, ValueError) as exc:
            a, b = inputs()
            evidence = _base_evidence(reference(a, b), a, b, args.timeout_seconds)
            evidence.update(status="blocked", error=f"worker supervisor: {exc}",
                            timeout_enforced=False)
            _write_evidence(evidence, args.output)
            return 2

        supervision_complete = bool(
            record.get("worker_reaped")
            and not record.get("worker_group_incomplete")
            and not record.get("worker_group_inspection_failed")
            and not record.get("worker_group_kill_error")
            and not record.get("worker_identity_lost")
            and not record.get("unreaped_worker_may_remain")
            and code != 125
        )
        if code == 124 or not supervision_complete or code == 125:
            # A worker leader can exit while CUDA-using descendants stay
            # alive. Never parse its forged "success" report if group/PGID
            # lifetime or cleanup is not verified. Reset is always unknown.
            failure = code == 125 or not supervision_complete
            evidence = _unknown_effect_evidence(
                args, record,
                ("worker group/identity cleanup unverified; device effect unknown"
                 if failure else "CUDA worker deadline expired; device effect unknown"),
                status="failed" if failure else "timeout",
                timeout_enforced=(code == 124 and supervision_complete),
            )
            evidence["elapsed_seconds"] = round(time.monotonic() - started, 6)
            _write_evidence(evidence, args.output)
            return 1

        try:
            evidence = read_supervised_worker_report(worker_output)
            if (not isinstance(evidence, dict)
                    or evidence.get("schema") != "a09.cuda-gemm.v2"
                    or evidence.get("status") not in (
                        "blocked", "failed", "timeout",
                        "passed_on_reported_cuda_environment")
                    or not isinstance(evidence.get("stages"), dict)
                    or set(evidence["stages"]) != set(STAGES)
                    or not isinstance(evidence.get("execution_provenance"), dict)):
                raise ValueError("unrecognized or incomplete CUDA worker evidence")
            expected_code = {"blocked": 2, "failed": 1, "timeout": 1,
                             "passed_on_reported_cuda_environment": 0}
            if expected_code[evidence["status"]] != code:
                raise ValueError("worker return code and evidence disagree")
            if evidence["status"] == "passed_on_reported_cuda_environment":
                a, b = inputs()
                expected = digest(reference(a, b))
                must_be_true = (
                    "device_access_attempted", "device_memory_allocated",
                    "cuda_kernel_launched", "synchronization_completed",
                    "results_copied", "resources_released", "no_cpu_fallback",
                )
                required_stages = tuple(name for name in STAGES if name != "failure_recovery")
                if (any(evidence.get(field) is not True for field in must_be_true)
                        or any(evidence["stages"].get(stage) != "passed"
                               for stage in required_stages)
                        or evidence.get("input_a_sha256") != digest(a)
                        or evidence.get("input_b_sha256") != digest(b)
                        or evidence.get("expected_output_sha256") != expected
                        or evidence.get("actual_output_sha256") != expected
                        or evidence.get("test") != "gemm16_f32"
                        or evidence.get("dimension") != [N, N, N]
                        or evidence.get("driver_api") != "CUDA Driver API"
                        or evidence.get("compiler") != "NVRTC"
                        or not isinstance(evidence.get("device"), dict)):
                    raise ValueError("CUDA success receipt failed fixed GEMM proof obligations")
                # Validate the *original request* and the parent's OS-owned
                # worker identity before reporting any Linux CUDA success.
                validate_supervised_cuda_success(
                    evidence, record, args.require_name, args.require_bdf
                )
            # Linux worker output is NEVER authoritative about which host
            # kernel owns the physical PCI function or whether DMA is safe.
            for key in ("asterinas_execution_verified", "vmm_passthrough_verified",
                        "physical_device_assignment_verified",
                        "reset_or_failure_recovery_verified",
                        "failure_recovery_verified"):
                evidence[key] = False
            for key in ("asterinas_execution_verified", "vmm_passthrough_verified",
                        "physical_device_assignment_verified"):
                evidence["execution_provenance"][key] = False
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            a, b = inputs()
            evidence = _base_evidence(reference(a, b), a, b, args.timeout_seconds)
            evidence.update(status="failed",
                            error=f"worker evidence invalid: {exc}")
            code = 1
        evidence["timeout_enforced"] = bool(supervision_complete)
        evidence["supervisor"] = record
        evidence["execution_provenance"]["execution_layer"] = (
            "linux_supervised_worker_cuda_driver_api")
        evidence["execution_provenance"]["supervisor"] = record
        evidence["elapsed_seconds"] = round(time.monotonic() - started, 6)
        _write_evidence(evidence, args.output)
        return code if code in (0, 1, 2) else 1


def main(supervise=True):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-name", default="RTX 4060")
    parser.add_argument("--require-bdf", default="", help="optional exact PCI BDF from read-only probe")
    parser.add_argument("--timeout-seconds", type=float, default=30.0,
                        help="bounded wall-clock window for CUDA worker (default: 30)")
    parser.add_argument("--output", default="-", help="'-' prints JSON")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be a finite positive number")
    if args.worker or not supervise:
        return _run_local(args)
    return _run_supervised(args)


if __name__ == "__main__":
    raise SystemExit(main())
