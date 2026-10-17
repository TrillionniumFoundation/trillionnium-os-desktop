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
import platform
import re
import struct

N = 16
MAX_CUDA_ENUM_DEVICES = 64
MAX_NVRTC_LOG_BYTES = 64 * 1024
MAX_NVRTC_PTX_BYTES = 8 * 1024 * 1024
BDF_RE = re.compile(r"^[0-9a-fA-F]{4,8}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$")
GOLDEN_INPUT_A = "0d9121c90b659969a44ca689809ebd3a6579f3f18b6aa5b9de5da1b98a9458ae"
GOLDEN_INPUT_B = "37ca62264050ddd6b8674649a77ec6047f3aa1a2d87f97858f7f6be38189df74"
GOLDEN_OUTPUT = "5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847"

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


def checked_nvrtc_size(size, limit, purpose):
    """Reject impossible compiler-reported sizes before allocating Python RAM."""
    if type(size) is not int or size < 1 or size > limit:
        raise GpuError(f"NVRTC {purpose} size outside 1..{limit} bytes: {size}")
    return size


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


def cleanup_device_resources(cuda, ptrs, module, ctx, submission_attempted, synchronized):
    """No explicit CUDA frees on potentially in-flight GPU work.

    Does not prove that process teardown or GPU reset is safe. Such cases need
    the independent host/VMM DMA-quiescence gate and are not a recovery pass.
    """
    if submission_attempted and not synchronized:
        return ["UNKNOWN_DMA_EFFECT: explicit device allocations/module/context release suppressed; host quarantine required"]
    errors = []
    for ptr in reversed(ptrs):
        try:
            cuda.call("cuMemFree_v2", [C.c_uint64], ptr)
        except Exception as exc:
            errors.append(str(exc))
    if module.value:
        try:
            cuda.call("cuModuleUnload", [C.c_void_p], module)
        except Exception as exc:
            errors.append(str(exc))
    if ctx.value:
        try:
            cuda.call("cuCtxDestroy_v2", [C.c_void_p], ctx)
        except Exception as exc:
            errors.append(str(exc))
    return errors


def gpu_gemm(required_name, required_bdf, *, lab_isolated=False):
    if not lab_isolated or not BDF_RE.fullmatch(required_bdf) or not required_name.strip():
        raise Blocked("direct CUDA calls require isolated-lab opt-in, pinned BDF and device name")
    cuda = Api(library(["libcuda.so.1", find_library("cuda")]), "CUDA")
    # Driver API is mandatory; a software rendering backend cannot satisfy these calls.
    cuda.call("cuInit", [C.c_uint], 0)
    count = C.c_int()
    cuda.call("cuDeviceGetCount", [C.POINTER(C.c_int)], C.byref(count))
    if count.value < 1:
        raise Blocked("CUDA driver reports zero usable devices")
    if count.value > MAX_CUDA_ENUM_DEVICES:
        raise Blocked("CUDA driver reports an unreasonable device count; refusing unbounded enumeration")
    selected = None
    seen = []
    for index in range(count.value):
        handle = C.c_int()
        cuda.call("cuDeviceGet", [C.POINTER(C.c_int), C.c_int], C.byref(handle), index)
        name_buf = C.create_string_buffer(256)
        cuda.call("cuDeviceGetName", [C.c_void_p, C.c_int, C.c_int],
                  name_buf, len(name_buf), handle)
        name = name_buf.value.decode("utf-8", "replace")
        pci_buf = C.create_string_buffer(32)
        cuda.call("cuDeviceGetPCIBusId", [C.c_void_p, C.c_int, C.c_int],
                  pci_buf, len(pci_buf), handle)
        bdf = pci_buf.value.decode("ascii", "replace")
        seen.append({"name": name, "bdf": bdf})
        if (required_name.lower() in name.lower() and
                (not required_bdf or required_bdf.lower() == bdf.lower())):
            selected = (handle, name, bdf, index)
            break
    if selected is None:
        raise Blocked(f"no CUDA GPU matches target name={required_name!r} "
                      f"bdf={required_bdf!r}; enumerated={seen}")
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
                "nvrtc_version": f"{nv_major.value}.{nv_minor.value}"}
    program = C.c_void_p()
    ptx = None
    nvrtc.call("nvrtcCreateProgram", [C.POINTER(C.c_void_p), C.c_char_p, C.c_char_p,
                                     C.c_int, C.c_void_p, C.c_void_p],
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
                checked_nvrtc_size(log_len.value, MAX_NVRTC_LOG_BYTES, "diagnostic log")
            )
            nvrtc.call("nvrtcGetProgramLog", [C.c_void_p, C.c_void_p], program, log)
            raise GpuError(f"NVRTC compile {rc}: {log.value.decode(errors='replace')[:2000]}")
        ptx_len = C.c_size_t()
        nvrtc.call("nvrtcGetPTXSize", [C.c_void_p, C.POINTER(C.c_size_t)], program, C.byref(ptx_len))
        ptx = C.create_string_buffer(
            checked_nvrtc_size(ptx_len.value, MAX_NVRTC_PTX_BYTES, "PTX program")
        )
        nvrtc.call("nvrtcGetPTX", [C.c_void_p, C.c_void_p], program, ptx)
    finally:
        nvrtc.call("nvrtcDestroyProgram", [C.POINTER(C.c_void_p)], C.byref(program))
    ctx, module, function = C.c_void_p(), C.c_void_p(), C.c_void_p()
    ptrs = []
    cleanup_errors = []
    failure = None
    output = None
    submission_attempted = False
    synchronized = False
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
        for _ in range(3):
            dev_ptr = C.c_uint64()
            cuda.call("cuMemAlloc_v2", [C.POINTER(C.c_uint64), C.c_size_t],
                      C.byref(dev_ptr), C.sizeof(host_a))
            ptrs.append(dev_ptr)
        for dev_ptr, host in ((ptrs[0], host_a), (ptrs[1], host_b)):
            cuda.call("cuMemcpyHtoD_v2", [C.c_uint64, C.c_void_p, C.c_size_t],
                      dev_ptr, C.cast(host, C.c_void_p), C.sizeof(host))
        kernel_args = (C.c_void_p * 3)(*[C.cast(C.byref(p), C.c_void_p) for p in ptrs])
        # A CUDA launch error may still leave partial hardware side effects.
        # Mark the attempt before entering the driver; only a successful
        # synchronization can authorize explicit device memory reclamation.
        submission_attempted = True
        cuda.call("cuLaunchKernel", [C.c_void_p, C.c_uint, C.c_uint, C.c_uint,
                                     C.c_uint, C.c_uint, C.c_uint, C.c_uint,
                                     C.c_void_p, C.POINTER(C.c_void_p), C.c_void_p],
                  function, N, 1, 1, N, 1, 1, 0, None, kernel_args, None)
        cuda.call("cuCtxSynchronize", [])
        synchronized = True
        cuda.call("cuMemcpyDtoH_v2", [C.c_void_p, C.c_uint64, C.c_size_t],
                  C.cast(host_c, C.c_void_p), ptrs[2], C.sizeof(host_c))
        output = list(host_c)
    except Exception as exc:
        failure = exc
    finally:
        cleanup_errors.extend(cleanup_device_resources(
            cuda, ptrs, module, ctx, submission_attempted, synchronized
        ))
    if failure:
        raise GpuError(str(failure) + (f"; cleanup errors: {cleanup_errors}" if cleanup_errors else ""))
    if cleanup_errors:
        raise GpuError(f"resource cleanup failed: {cleanup_errors}")
    return metadata, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-name", default="RTX 4060")
    parser.add_argument("--require-bdf", default="", help="REQUIRED exact guest PCI BDF from read-only probe")
    parser.add_argument("--isolated-lab", action="store_true",
                        help="explicitly acknowledge that this is an idle disposable GPU lab, not H3/training/prod")
    parser.add_argument("--output", default="-", help="'-' prints JSON")
    args = parser.parse_args()
    a, b = inputs()
    expected = reference(a, b)
    evidence = {
        "schema": "a09.cuda-gemm.v1", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "blocked", "test": "gemm16_f32", "dimension": [N, N, N],
        "input_a_sha256": digest(a), "input_b_sha256": digest(b),
        "expected_output_sha256": digest(expected), "driver_api": "CUDA Driver API",
        "compiler": "NVRTC", "reference": "CPU scalar deterministic integer-valued FP32",
        "reported_execution_kernel": f"{platform.system()} {platform.release()}",
        "asterinas_execution_verified": False,
        "vmm_passthrough_verified": False,
        "physical_device_assignment_verified": False,
        "reset_or_failure_recovery_verified": False,
        "no_cpu_fallback": True, "device": None,
        "device_access_attempted": False, "isolated_lab_user_assertion": args.isolated_lab,
        "host_kernel_attested": False, "guest_kernel_attested": False,
        "actual_gpu_location_attested": False,
    }
    try:
        if not args.isolated_lab:
            raise Blocked("explicit --isolated-lab required before loading CUDA driver; never run on H3/training/prod")
        if not BDF_RE.fullmatch(args.require_bdf):
            raise Blocked("exact --require-bdf domain:bus:device.function required from isolated guest enumeration")
        if not args.require_name.strip():
            raise Blocked("nonempty --require-name required")
        if (evidence["input_a_sha256"], evidence["input_b_sha256"],
                evidence["expected_output_sha256"]) != (
                GOLDEN_INPUT_A, GOLDEN_INPUT_B, GOLDEN_OUTPUT):
            raise GpuError("CPU golden inputs/reference mismatch; refusing GPU launch")
        evidence["device_access_attempted"] = True
        device, output = gpu_gemm(args.require_name, args.require_bdf, lab_isolated=True)
        evidence["device"] = device
        evidence["actual_output_sha256"] = digest(output)
        mismatch = compare(output, expected)
        if mismatch:
            raise GpuError(f"GPU numerical mismatch: {mismatch}")
        evidence.update(status="passed_on_reported_cuda_environment", error=None,
                        device_memory_allocated=True, cuda_kernel_launched=True,
                        synchronization_completed=True, results_copied=True,
                        resources_released=True)
        rc = 0
    except Blocked as exc:
        evidence.update(status="blocked", error=str(exc))
        rc = 2
    except (GpuError, OSError, ValueError) as exc:
        evidence.update(status="failed", error=str(exc))
        rc = 1
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        print(payload, end="")
    else:
        from pathlib import Path
        Path(args.output).write_text(payload, encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
