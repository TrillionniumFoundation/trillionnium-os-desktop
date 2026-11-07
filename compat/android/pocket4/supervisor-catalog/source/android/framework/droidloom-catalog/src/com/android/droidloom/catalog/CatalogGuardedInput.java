/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import java.io.IOException;
import java.io.InputStream;

/** Drain descriptor messages after each read, before another read can replace them. */
final class CatalogGuardedInput extends InputStream {
    interface Ancillary {
        /** Close every received descriptor. Return true if any were present. */
        boolean closeReceived() throws IOException;
    }

    private final InputStream input;
    private final Ancillary ancillary;

    CatalogGuardedInput(InputStream input, Ancillary ancillary) {
        this.input = input;
        this.ancillary = ancillary;
    }

    @Override
    public int read() throws IOException {
        IOException failure = null;
        try {
            return input.read();
        } catch (IOException error) {
            failure = error;
            throw error;
        } finally {
            afterRead(failure);
        }
    }

    @Override
    public int read(byte[] bytes, int offset, int length) throws IOException {
        IOException failure = null;
        try {
            return input.read(bytes, offset, length);
        } catch (IOException error) {
            failure = error;
            throw error;
        } finally {
            afterRead(failure);
        }
    }

    private void afterRead(IOException primary) throws IOException {
        try {
            if (ancillary.closeReceived()) {
                throw new IOException("ANCILLARY_DESCRIPTORS_NOT_ALLOWED");
            }
        } catch (IOException cleanup) {
            if (primary == null) throw cleanup;
            primary.addSuppressed(cleanup);
        }
    }

    /** The socket owner also calls this when a request exits or is interrupted. */
    void drainPending() throws IOException {
        ancillary.closeReceived();
    }
}
