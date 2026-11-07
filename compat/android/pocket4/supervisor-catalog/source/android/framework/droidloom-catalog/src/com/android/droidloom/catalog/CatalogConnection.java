/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicReference;

/** One socket owner. A failed or in-progress close never becomes a reusable request slot. */
final class CatalogConnection {
    enum State { OPEN, CLOSING, CLOSED, FAILED }
    interface Operations {
        void shutdownInput() throws IOException;
        void shutdownOutput() throws IOException;
        void close() throws IOException;
    }

    private final Operations operations;
    private final AtomicReference<State> state = new AtomicReference<>(State.OPEN);

    CatalogConnection(Operations operations) { this.operations = operations; }

    void shutdown() {
        if (state.get() != State.OPEN) return;
        // These are auxiliary wakeups, not a claim that the FD was closed.
        try { operations.shutdownInput(); } catch (IOException | RuntimeException ignored) { }
        try { operations.shutdownOutput(); } catch (IOException | RuntimeException ignored) { }
    }

    State closeOnce() {
        if (!state.compareAndSet(State.OPEN, State.CLOSING)) return state.get();
        try {
            operations.close();
            state.set(State.CLOSED);
        } catch (IOException | RuntimeException failure) {
            // Never retry a close whose effect on the descriptor is uncertain.
            state.set(State.FAILED);
        }
        return state.get();
    }

    State state() { return state.get(); }
}
