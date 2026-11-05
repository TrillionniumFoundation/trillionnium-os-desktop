#define OWNED_USE_PREIMAGE 1
// SPDX-License-Identifier: Apache-2.0
// Transport-only JNI wrapper around the unchanged recovery03 owned controls.
#include <jni.h>
#include <atomic>
#include <cstdarg>
#include <cstdio>
#include <sys/syscall.h>
#include <unistd.h>

static char probe_result[131072];
static size_t result_used;
static bool result_overflow;
static std::atomic_flag entered = ATOMIC_FLAG_INIT;

static int CapturePrintf(const char* format, ...) __attribute__((format(printf, 1, 2)));
static int CapturePrintf(const char* format, ...) {
  if (result_overflow) return -1;
  va_list arguments;
  va_start(arguments, format);
  const int count = vsnprintf(probe_result + result_used,
                             sizeof(probe_result) - result_used, format, arguments);
  va_end(arguments);
  if (count < 0 || static_cast<size_t>(count) >= sizeof(probe_result) - result_used) {
    result_overflow = true;
    return -1;
  }
  result_used += static_cast<size_t>(count);
  return count;
}
static int CapturePutchar(int value) {
  if (result_overflow || result_used + 1 >= sizeof(probe_result)) {
    result_overflow = true;
    return EOF;
  }
  probe_result[result_used++] = static_cast<char>(value);
  probe_result[result_used] = 0;
  return static_cast<unsigned char>(value);
}
static int CaptureFlush(FILE*) { return result_overflow ? EOF : 0; }

// The original builder intentionally compiles one translation unit. Include
// the unchanged wire definitions here; no source or syscall seam is injected.
#include "actual/proc_maps_factory_wire.cc"
#define printf CapturePrintf
#define putchar CapturePutchar
#define fflush CaptureFlush
#define main RunOwnedNofileCases
#include "owned_nofile_controls.cc"
#undef main
#undef fflush
#undef putchar
#undef printf

extern "C" JNIEXPORT jstring JNICALL
Java_local_pocket4_fdownerprobe_ProbeInstrumentation_runProbe(JNIEnv* env, jclass) {
  if (entered.test_and_set(std::memory_order_acq_rel))
    return env->NewStringUTF("{\"pass\":false,\"wrapper_error\":\"same-process replay refused\"}");
  // The original harness enumerates its own leader's children. The existing
  // Instrumentation.onCreate entry must run on that thread, or refuse before
  // any control, subreaper change, fork, or resource-limit change.
  if (static_cast<pid_t>(syscall(SYS_gettid)) != getpid())
    return env->NewStringUTF("{\"pass\":false,\"wrapper_error\":\"leader thread required\"}");
  result_used = 0;
  result_overflow = false;
  probe_result[0] = 0;
  char name[] = "owned-nofile-recovery03-android";
  char execute[] = "--execute-once";
  char* argv[] = {name, execute, nullptr};
  const int result = RunOwnedNofileCases(2, argv);
  if (result_overflow || result_used == 0) {
    snprintf(probe_result, sizeof(probe_result),
             "{\"pass\":false,\"wrapper_error\":\"capture incomplete\",\"early_rc\":%d,\"overflow\":%s}",
             result, result_overflow ? "true" : "false");
  }
  // Keep the original complete per-case JSON and known-red assertions. The
  // harness's qualification flags stay false; actual platform qualification
  // belongs to the receipt-bound external verifier, never a source constant.
  return env->NewStringUTF(probe_result);
}
