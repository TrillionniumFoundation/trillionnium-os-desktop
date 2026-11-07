/* Copyright 2026 Droidloom contributors. SPDX-License-Identifier: Apache-2.0 */
package org.droidloom.signalprobe.r3;

import android.app.Instrumentation;
import android.content.Context;
import android.os.Build;
import android.os.Bundle;
import android.os.Process;
import android.os.SystemClock;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;

/** Headless, one case per invocation. No Activity, service, receiver or network. */
public final class SignalProbeInstrumentation extends Instrumentation {
    private static final long WATCHDOG_MS = 10000;
    private final AtomicBoolean finished = new AtomicBoolean(false);
    private Bundle arguments;
    private File output;
    private String nonce;
    private String caseName;
    private long startedElapsedMs;

    private static native String nativeRun(int caseId);

    @Override public void onCreate(Bundle args) {
        super.onCreate(args);
        arguments = args == null ? new Bundle() : new Bundle(args);
        start();
    }

    @Override public void onStart() {
        nonce = arguments.getString("nonce", "");
        caseName = arguments.getString("case", "");
        final int caseId;
        if ("svc".equals(caseName)) caseId = 1;
        else if ("smc-handler".equals(caseName)) caseId = 2;
        else if ("smc-default".equals(caseName)) caseId = 3;
        else if ("smc-mask-edit".equals(caseName)) caseId = 4;
        else { finishWithoutClaim("ARGUMENT_ERROR", "case must be svc, smc-handler, smc-default or smc-mask-edit"); return; }
        if (!nonce.matches("[A-Za-z0-9][A-Za-z0-9_-]{7,95}")) {
            finishWithoutClaim("ARGUMENT_ERROR", "nonce must be 8..96 ASCII letters/digits/underscore/hyphen"); return;
        }
        Context context = getTargetContext();
        try {
            File directory = new File(context.getFilesDir(), "signal-probe");
            if (!directory.isDirectory() && !directory.mkdirs()) throw new IllegalStateException("cannot create private evidence directory");
            File claim = new File(directory, nonce + ".claim");
            /* Atomic O_EXCL-style claim. Do this before loading any native code.
             * A duplicate invocation never overwrites the first run's evidence.
             */
            if (!claim.createNewFile()) {
                finishWithoutClaim("DUPLICATE_NONCE", "nonce already claimed; native code was not loaded or called"); return;
            }
            try (FileOutputStream claimBytes = new FileOutputStream(claim, true)) {
                claimBytes.write(("case=" + caseName + "\nnonce=" + nonce + "\npid=" + Process.myPid() + "\n")
                        .getBytes(StandardCharsets.UTF_8));
                claimBytes.getFD().sync();
            }
            output = new File(directory, nonce + ".json");
            startedElapsedMs = SystemClock.elapsedRealtime();
            persist(envelope("STARTED"));
            Bundle started = new Bundle();
            started.putString("phase", "STARTED"); started.putString("nonce", nonce);
            started.putString("case", caseName); started.putString("result_path", output.getAbsolutePath());
            sendStatus(1, started);
        } catch (Throwable failure) {
            finishWithoutClaim("SETUP_ERROR", describe(failure)); return;
        }

        Thread watchdog = new Thread(new Runnable() {
          @Override public void run() {
            for (;;) {
                long remaining = WATCHDOG_MS - (SystemClock.elapsedRealtime() - startedElapsedMs);
                if (remaining <= 0) break;
                SystemClock.sleep(remaining);
            }
            if (!finished.compareAndSet(false, true)) return;
            JSONObject evidence;
            try {
                evidence = envelope("JAVA_WATCHDOG_TIMEOUT");
                evidence.put("error", "native case did not complete within 10000 ms");
                persist(evidence);
            } catch (Throwable failure) {
                evidence = minimal("JAVA_WATCHDOG_TIMEOUT", describe(failure));
            }
            publish(false, evidence);
            /* Only our own instrumentation process. The default-case child
             * installs PR_SET_PDEATHSIG before executing its faulting word.
             */
            Process.killProcess(Process.myPid());
          }
        }, "owned-signal-probe-watchdog");
        watchdog.setDaemon(true);

        try {
            watchdog.start();
            System.loadLibrary("owned_signal_probe");
            String wire = nativeRun(caseId);
            if (wire == null) throw new IllegalStateException("native returned null");
            JSONObject nativeEvidence = new JSONObject(wire);
            boolean pass = nativeEvidence.optInt("schema", -1) == 1 &&
                    caseName.equals(nativeEvidence.optString("case")) &&
                    "PASS".equals(nativeEvidence.optString("status"));
            complete(pass, nativeEvidence, null);
        } catch (Throwable failure) {
            complete(false, null, describe(failure));
        }
    }

    private JSONObject envelope(String phase) throws Exception {
        JSONObject result = new JSONObject();
        result.put("schema", 1); result.put("phase", phase);
        result.put("case", caseName); result.put("nonce", nonce);
        result.put("java_pid", Process.myPid());
        result.put("elapsed_ms", startedElapsedMs == 0 ? 0 : SystemClock.elapsedRealtime() - startedElapsedMs);
        result.put("target_sdk", getTargetContext().getApplicationInfo().targetSdkVersion);
        result.put("package", getTargetContext().getPackageName());
        result.put("fingerprint", Build.FINGERPRINT);
        result.put("java_os_arch", System.getProperty("os.arch", "unknown"));
        result.put("java_process_is_64_bit", Process.is64Bit());
        result.put("watchdog_ms", WATCHDOG_MS);
        result.put("self_security", readSelfSecurity());
        return result;
    }

    /** Diagnostic-only reads of this process. Failure never vetoes a case. */
    private JSONObject readSelfSecurity() {
        JSONObject security = new JSONObject();
        try {
            try {
                String status = readBounded("/proc/self/status", 32768);
                String seccomp = null;
                String noNewPrivs = null;
                for (String line : status.split("\n")) {
                    if (line.startsWith("Seccomp:")) seccomp = line.substring(8).trim();
                    if (line.startsWith("NoNewPrivs:")) noNewPrivs = line.substring(11).trim();
                }
                security.put("seccomp", seccomp == null ? JSONObject.NULL : seccomp);
                security.put("no_new_privs", noNewPrivs == null ? JSONObject.NULL : noNewPrivs);
                security.put("status_read_error", JSONObject.NULL);
                if (seccomp == null || noNewPrivs == null)
                    security.put("status_missing_field", true);
            } catch (Throwable failure) {
                security.put("seccomp", JSONObject.NULL);
                security.put("no_new_privs", JSONObject.NULL);
                security.put("status_read_error", describe(failure));
            }
            try {
                security.put("attr_current", readBounded("/proc/self/attr/current", 4096).trim());
                security.put("attr_read_error", JSONObject.NULL);
            } catch (Throwable failure) {
                security.put("attr_current", JSONObject.NULL);
                security.put("attr_read_error", describe(failure));
            }
        } catch (Throwable ignored) {
            /* Even a diagnostic serialization failure cannot veto the case. */
        }
        return security;
    }

    private static String readBounded(String path, int maximumChars) throws Exception {
        StringBuilder text = new StringBuilder();
        char[] buffer = new char[1024];
        try (InputStreamReader reader = new InputStreamReader(
                new FileInputStream(path), StandardCharsets.US_ASCII)) {
            for (;;) {
                int count = reader.read(buffer);
                if (count < 0) break;
                if (count == 0) continue;
                if (text.length() > maximumChars - count)
                    throw new IllegalStateException("diagnostic proc read exceeds bound");
                text.append(buffer, 0, count);
            }
        }
        return text.toString();
    }

    private void complete(boolean pass, JSONObject nativeEvidence, String error) {
        if (!finished.compareAndSet(false, true)) return;
        JSONObject result;
        try {
            result = envelope(pass ? "PASS" : "FAIL");
            if (nativeEvidence != null) result.put("native", nativeEvidence);
            if (error != null) result.put("error", error);
            persist(result);
        } catch (Throwable failure) {
            pass = false;
            result = minimal("EVIDENCE_WRITE_ERROR", describe(failure));
        }
        publish(pass, result);
    }

    private synchronized void persist(JSONObject evidence) throws Exception {
        File temporary = new File(output.getParentFile(), output.getName() + ".tmp");
        try (FileOutputStream stream = new FileOutputStream(temporary, false)) {
            stream.write((evidence.toString() + "\n").getBytes(StandardCharsets.UTF_8));
            stream.getFD().sync();
        }
        if (!temporary.renameTo(output)) throw new IllegalStateException("cannot atomically publish evidence");
    }

    private void finishWithoutClaim(String phase, String error) {
        if (!finished.compareAndSet(false, true)) return;
        publish(false, minimal(phase, error));
    }

    private JSONObject minimal(String phase, String error) {
        JSONObject value = new JSONObject();
        try {
            value.put("schema", 1); value.put("phase", phase);
            value.put("nonce", nonce); value.put("case", caseName);
            value.put("java_pid", Process.myPid()); value.put("error", error);
        } catch (Exception impossible) { /* Only primitive/string values. */ }
        return value;
    }

    private void publish(boolean pass, JSONObject evidence) {
        Bundle result = new Bundle();
        result.putString("phase", evidence.optString("phase", "FAIL"));
        result.putString("case", caseName); result.putString("nonce", nonce);
        result.putString("evidence_json", evidence.toString());
        if (output != null) result.putString("result_path", output.getAbsolutePath());
        finish(pass ? -1 : 0, result);
    }

    private static String describe(Throwable failure) {
        return failure.getClass().getName() + ": " + String.valueOf(failure.getMessage());
    }
}
