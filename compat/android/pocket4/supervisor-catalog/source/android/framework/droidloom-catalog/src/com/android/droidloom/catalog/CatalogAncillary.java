/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import java.io.FileDescriptor;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;

/** Close the complete received batch even if an earlier descriptor fails. */
final class CatalogAncillary {
    interface Source {
        FileDescriptor[] take() throws IOException;
    }

    interface Closer {
        void close(FileDescriptor descriptor) throws IOException;
    }

    private CatalogAncillary() {}

    static boolean drain(Source source, Closer closer, AtomicBoolean healthy) throws IOException {
        final FileDescriptor[] received;
        try {
            received = source.take();
        } catch (IOException failure) {
            healthy.set(false);
            throw failure;
        }
        if (received == null) return false;
        IOException failure = null;
        for (FileDescriptor descriptor : received) {
            try {
                if (descriptor == null) throw new IOException("INVALID_RECEIVED_DESCRIPTOR");
                closer.close(descriptor);
            } catch (IOException error) {
                if (failure == null) failure = new IOException("DESCRIPTOR_CLOSE_UNAVAILABLE");
                failure.addSuppressed(error);
            }
        }
        if (failure != null) {
            healthy.set(false);
            throw failure;
        }
        return received.length != 0;
    }
}
