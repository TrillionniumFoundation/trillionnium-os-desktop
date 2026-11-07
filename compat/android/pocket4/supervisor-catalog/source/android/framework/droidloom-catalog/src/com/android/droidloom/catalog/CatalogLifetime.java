/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

/** One request generation and one terminal service failure; no replacement worker. */
final class CatalogLifetime {
    enum Failure {
        BACKEND_DEADLINE(72), DESCRIPTOR_CLEANUP(73), LISTENER(74),
        QUERY_WORKER(75), DEADLINE_WORKER(76), SOCKET_CLOSE(77);
        final int reasonCode;
        Failure(int reasonCode) { this.reasonCode = reasonCode; }
    }
    static final class Token { private Token() {} }

    private Token active;
    private Failure failure;

    synchronized void requireServing() {
        if (failure != null) throw new IllegalStateException("CATALOG_SERVICE_TERMINAL");
    }

    synchronized Token begin() {
        if (failure != null || active != null) return null;
        active = new Token();
        return active;
    }

    synchronized boolean complete(Token token, CatalogConnection.State closed) {
        if (closed != CatalogConnection.State.CLOSED || token == null
                || failure != null || active != token) return false;
        active = null;
        return true;
    }

    synchronized boolean expire(Token token) {
        if (token == null || failure != null || active != token) return false;
        failure = Failure.BACKEND_DEADLINE;
        active = null;
        return true;
    }

    synchronized boolean fail(Failure reason) {
        if (reason == null) throw new NullPointerException("failure");
        if (failure != null) return false;
        failure = reason;
        active = null;
        return true;
    }

    synchronized Failure failure() { return failure; }
}
