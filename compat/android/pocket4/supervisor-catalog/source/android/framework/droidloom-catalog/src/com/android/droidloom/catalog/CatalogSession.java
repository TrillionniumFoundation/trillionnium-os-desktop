/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import java.io.IOException;
import java.io.InputStream;
import java.io.InterruptedIOException;
import java.io.OutputStream;
import java.util.function.LongSupplier;

/** One fresh read-only backend invocation per complete bounded request. */
final class CatalogSession {
    interface Query {
        String execute(CatalogProtocol.Request request) throws Exception;
    }

    private CatalogSession() {}

    static void serve(InputStream input, OutputStream output, Query query,
            LongSupplier monotonic, long started) throws IOException {
        CatalogProtocol.Request request;
        try {
            request = CatalogProtocol.readRequest(input);
        } catch (IOException error) {
            requireTime(monotonic, started);
            CatalogProtocol.writeError(output, CatalogProtocol.INVALID);
            return;
        }
        requireTime(monotonic, started);
        final String result;
        try {
            result = query.execute(request);
        } catch (CatalogBudget.OutputLimit limit) {
            requireTime(monotonic, started);
            CatalogProtocol.writeError(output, CatalogProtocol.OUTPUT_LIMIT);
            return;
        } catch (Exception unavailable) {
            requireTime(monotonic, started);
            // Framework exceptions can contain paths or internal metadata.
            // The public error vocabulary never forwards their text.
            CatalogProtocol.writeError(output, CatalogProtocol.UNAVAILABLE);
            return;
        }
        requireTime(monotonic, started);
        if (result == null || result.isEmpty()) {
            CatalogProtocol.writeError(output, CatalogProtocol.UNAVAILABLE);
        } else {
            try {
                CatalogBudget.utf8Size(result, CatalogProtocol.MAX_RESPONSE_BYTES);
            } catch (CatalogBudget.OutputLimit limit) {
                CatalogProtocol.writeError(output, CatalogProtocol.OUTPUT_LIMIT);
                return;
            }
            requireTime(monotonic, started);
            CatalogProtocol.writeResponse(output, CatalogProtocol.OK, result);
        }
    }

    private static void requireTime(LongSupplier monotonic, long started) throws IOException {
        long elapsed = monotonic.getAsLong() - started;
        if (elapsed < 0 || elapsed >= CatalogProtocol.REQUEST_TIMEOUT_MILLIS * 1000000L) {
            throw new InterruptedIOException("CATALOG_DEADLINE");
        }
    }
}
