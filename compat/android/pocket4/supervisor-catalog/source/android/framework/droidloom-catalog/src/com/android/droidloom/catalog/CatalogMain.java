/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

/** Fixed entry for the independent, init-owned read-only catalog service. */
public final class CatalogMain {
    private CatalogMain() {}

    /**
     * Terminate only this independent process. The number is a closed reason,
     * not a promised exit status; a successful call ends in SIGKILL.
     */
    static void terminate(int closedReason) {
        final int self = android.os.Process.myPid();
        if (self <= 1) throw new IllegalStateException("CATALOG_SELF_PID_REQUIRED");
        try {
            android.system.Os.kill(self, android.system.OsConstants.SIGKILL);
        } catch (android.system.ErrnoException unavailable) {
            // No native Runtime exit hook or logging is attempted. A failed
            // self-signal is not accepted as completed process retirement.
            throw new IllegalStateException("CATALOG_SELF_SIGKILL_UNAVAILABLE_" + closedReason);
        }
        throw new IllegalStateException("CATALOG_SELF_SIGKILL_RETURNED_" + closedReason);
    }

    public static void main(String[] arguments) {
        if (arguments.length != 0 || android.os.Process.myUid() != 0) {
            terminate(64);
        }
        try {
            CatalogResidentServer.run();
        } catch (Throwable unavailable) {
            // A closed reason is sufficient for init supervision. Never emit
            // package-manager exceptions or catalog data to service logs.
        }
        // A listener failure cannot leave a Binder/Looper worker alive without
        // an endpoint. Only this independent process is terminated; init owns
        // its later restart and socket recreation.
        terminate(70);
    }
}
