/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import java.io.IOException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Real lifetime/close-owner regressions. Only socket Operations are an explicit
 * I/O substitute; no Android FD, Binder timeout, init restart or self-signal is
 * claimed by these host tests. Concurrent tests use actual joined Java threads.
 */
public final class CatalogLifetimeTest {
    interface Checked { void run() throws Exception; }
    private static int passed;

    private static void check(boolean value) {
        if (!value) throw new AssertionError("CATALOG_LIFETIME_CONTROL");
    }

    private static void run(String name, Checked body) throws Exception {
        body.run();
        passed++;
        System.out.println("PASS " + name);
    }

    private static void await(CountDownLatch latch) throws Exception {
        check(latch.await(2, TimeUnit.SECONDS));
    }

    private static Thread start(String name, AtomicReference<Throwable> failure, Checked body) {
        Thread thread = new Thread(() -> {
            try { body.run(); }
            catch (Throwable error) { failure.compareAndSet(null, error); }
        }, name);
        thread.setDaemon(true);
        thread.start();
        return thread;
    }

    private static void joined(Thread thread, AtomicReference<Throwable> failure) throws Exception {
        thread.join(2000);
        check(!thread.isAlive());
        if (failure.get() != null) throw new AssertionError("CONTROL_THREAD_FAILED", failure.get());
    }

    private static class Operations implements CatalogConnection.Operations {
        final AtomicInteger input = new AtomicInteger();
        final AtomicInteger output = new AtomicInteger();
        final AtomicInteger close = new AtomicInteger();
        @Override public void shutdownInput() throws IOException { input.incrementAndGet(); }
        @Override public void shutdownOutput() throws IOException { output.incrementAndGet(); }
        @Override public void close() throws IOException { close.incrementAndGet(); }
    }

    public static void main(String[] arguments) throws Exception {
        check(arguments.length == 0);
        run("request_slot_requires_confirmed_close", () -> {
            CatalogLifetime lifetime = new CatalogLifetime();
            CatalogLifetime.Token token = lifetime.begin();
            check(token != null && lifetime.begin() == null);
            for (CatalogConnection.State state : new CatalogConnection.State[] {
                    CatalogConnection.State.OPEN, CatalogConnection.State.CLOSING,
                    CatalogConnection.State.FAILED, null }) {
                check(!lifetime.complete(token, state));
                check(lifetime.begin() == null);
            }
            check(lifetime.complete(token, CatalogConnection.State.CLOSED));
            check(lifetime.begin() != null && lifetime.failure() == null);
        });
        run("completed_request_cannot_expire_new_generation", () -> {
            CatalogLifetime lifetime = new CatalogLifetime();
            CatalogLifetime.Token old = lifetime.begin();
            check(lifetime.complete(old, CatalogConnection.State.CLOSED));
            CatalogLifetime.Token current = lifetime.begin();
            check(current != null && current != old);
            check(!lifetime.expire(old));
            check(!lifetime.complete(old, CatalogConnection.State.CLOSED));
            CatalogLifetime foreign = new CatalogLifetime();
            check(!lifetime.complete(foreign.begin(), CatalogConnection.State.CLOSED));
            check(lifetime.begin() == null && lifetime.failure() == null);
            check(lifetime.complete(current, CatalogConnection.State.CLOSED));
        });
        run("active_deadline_is_terminal_and_cannot_be_completed", () -> {
            CatalogLifetime lifetime = new CatalogLifetime();
            CatalogLifetime.Token token = lifetime.begin();
            check(lifetime.expire(token));
            check(lifetime.failure() == CatalogLifetime.Failure.BACKEND_DEADLINE);
            check(!lifetime.complete(token, CatalogConnection.State.CLOSED));
            check(!lifetime.expire(token) && lifetime.begin() == null);
        });
        run("null_tokens_do_not_claim_or_release_slot", () -> {
            CatalogLifetime lifetime = new CatalogLifetime();
            check(!lifetime.complete(null, CatalogConnection.State.CLOSED));
            check(!lifetime.expire(null) && lifetime.failure() == null);
            CatalogLifetime.Token token = lifetime.begin();
            check(token != null && !lifetime.expire(null));
            check(!lifetime.complete(null, CatalogConnection.State.CLOSED));
            check(lifetime.begin() == null);
            check(lifetime.complete(token, CatalogConnection.State.CLOSED));
        });
        run("first_service_failure_is_preserved", () -> {
            CatalogLifetime lifetime = new CatalogLifetime();
            lifetime.requireServing();
            CatalogLifetime.Token token = lifetime.begin();
            check(lifetime.fail(CatalogLifetime.Failure.DESCRIPTOR_CLEANUP));
            check(!lifetime.fail(CatalogLifetime.Failure.SOCKET_CLOSE));
            check(!lifetime.expire(token));
            check(!lifetime.complete(token, CatalogConnection.State.CLOSED));
            check(lifetime.failure() == CatalogLifetime.Failure.DESCRIPTOR_CLEANUP);
            check(lifetime.begin() == null);
            boolean rejected = false;
            try {
                lifetime.requireServing();
            } catch (IllegalStateException terminal) {
                rejected = "CATALOG_SERVICE_TERMINAL".equals(terminal.getMessage());
            }
            check(rejected);
        });
        run("completion_and_expiry_have_one_atomic_winner", () -> {
            for (int attempt = 0; attempt < 64; attempt++) {
                CatalogLifetime lifetime = new CatalogLifetime();
                CatalogLifetime.Token token = lifetime.begin();
                CountDownLatch gate = new CountDownLatch(1);
                AtomicBoolean completed = new AtomicBoolean();
                AtomicBoolean expired = new AtomicBoolean();
                AtomicReference<Throwable> failure = new AtomicReference<>();
                Thread complete = start("catalog-complete", failure, () -> {
                    await(gate);
                    completed.set(lifetime.complete(token, CatalogConnection.State.CLOSED));
                });
                Thread expire = start("catalog-expire", failure, () -> {
                    await(gate);
                    expired.set(lifetime.expire(token));
                });
                gate.countDown();
                joined(complete, failure);
                joined(expire, failure);
                check(completed.get() != expired.get());
                if (completed.get()) {
                    check(lifetime.failure() == null);
                    CatalogLifetime.Token next = lifetime.begin();
                    check(next != null && !lifetime.expire(token));
                    check(lifetime.complete(next, CatalogConnection.State.CLOSED));
                } else {
                    check(lifetime.failure() == CatalogLifetime.Failure.BACKEND_DEADLINE);
                    check(lifetime.begin() == null);
                }
            }
        });
        run("socket_close_is_invoked_once", () -> {
            Operations operations = new Operations();
            CatalogConnection connection = new CatalogConnection(operations);
            check(connection.closeOnce() == CatalogConnection.State.CLOSED);
            check(connection.closeOnce() == CatalogConnection.State.CLOSED);
            connection.shutdown();
            check(operations.close.get() == 1);
            check(operations.input.get() == 0 && operations.output.get() == 0);
        });
        run("checked_close_failure_never_retries_or_releases_slot", () -> {
            Operations operations = new Operations() {
                @Override public void close() throws IOException {
                    close.incrementAndGet();
                    throw new IOException("synthetic close failure");
                }
            };
            CatalogConnection connection = new CatalogConnection(operations);
            CatalogLifetime lifetime = new CatalogLifetime();
            CatalogLifetime.Token token = lifetime.begin();
            check(connection.closeOnce() == CatalogConnection.State.FAILED);
            check(connection.closeOnce() == CatalogConnection.State.FAILED);
            connection.shutdown();
            check(operations.close.get() == 1 && operations.input.get() == 0);
            check(!lifetime.complete(token, connection.state()));
            check(lifetime.begin() == null);
            check(lifetime.fail(CatalogLifetime.Failure.SOCKET_CLOSE));
            check(lifetime.begin() == null);
        });
        run("unchecked_close_failure_is_also_terminal", () -> {
            Operations operations = new Operations() {
                @Override public void close() {
                    close.incrementAndGet();
                    throw new IllegalStateException("synthetic close failure");
                }
            };
            CatalogConnection connection = new CatalogConnection(operations);
            check(connection.closeOnce() == CatalogConnection.State.FAILED);
            check(connection.closeOnce() == CatalogConnection.State.FAILED);
            check(operations.close.get() == 1);
        });
        run("concurrent_close_retains_slot_until_original_owner_finishes", () -> {
            CountDownLatch entered = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            Operations operations = new Operations() {
                @Override public void close() throws IOException {
                    close.incrementAndGet();
                    entered.countDown();
                    try {
                        if (!release.await(2, TimeUnit.SECONDS)) throw new IOException("control timeout");
                    } catch (InterruptedException error) {
                        Thread.currentThread().interrupt();
                        throw new IOException(error);
                    }
                }
            };
            CatalogLifetime lifetime = new CatalogLifetime();
            CatalogLifetime.Token token = lifetime.begin();
            CatalogConnection connection = new CatalogConnection(operations);
            AtomicReference<Throwable> failure = new AtomicReference<>();
            Thread owner = start("catalog-close", failure, () -> {
                check(connection.closeOnce() == CatalogConnection.State.CLOSED);
            });
            try {
                await(entered);
                check(connection.closeOnce() == CatalogConnection.State.CLOSING);
                check(operations.close.get() == 1);
                check(!lifetime.complete(token, connection.state()));
                check(lifetime.begin() == null);
            } finally {
                release.countDown();
                joined(owner, failure);
            }
            check(connection.state() == CatalogConnection.State.CLOSED);
            check(lifetime.complete(token, connection.state()));
            check(lifetime.begin() != null && operations.close.get() == 1);
        });
        run("shutdown_failure_is_auxiliary_and_does_not_skip_close", () -> {
            Operations operations = new Operations() {
                @Override public void shutdownInput() throws IOException {
                    input.incrementAndGet();
                    throw new IOException("synthetic shutdown failure");
                }
                @Override public void shutdownOutput() {
                    output.incrementAndGet();
                    throw new IllegalStateException("synthetic shutdown failure");
                }
            };
            CatalogConnection connection = new CatalogConnection(operations);
            connection.shutdown();
            check(connection.state() == CatalogConnection.State.OPEN);
            check(operations.input.get() == 1 && operations.output.get() == 1);
            check(operations.close.get() == 0);
            check(connection.closeOnce() == CatalogConnection.State.CLOSED);
            check(operations.close.get() == 1);
        });
        run("deadline_during_pending_close_remains_terminal_after_close", () -> {
            CountDownLatch entered = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            Operations operations = new Operations() {
                @Override public void close() throws IOException {
                    close.incrementAndGet();
                    entered.countDown();
                    try {
                        if (!release.await(2, TimeUnit.SECONDS)) throw new IOException("control timeout");
                    } catch (InterruptedException error) {
                        Thread.currentThread().interrupt();
                        throw new IOException(error);
                    }
                }
            };
            CatalogConnection connection = new CatalogConnection(operations);
            CatalogLifetime lifetime = new CatalogLifetime();
            CatalogLifetime.Token token = lifetime.begin();
            AtomicReference<Throwable> failure = new AtomicReference<>();
            Thread owner = start("catalog-overrun-close", failure, () -> connection.closeOnce());
            try {
                await(entered);
                check(lifetime.expire(token));
                check(!lifetime.complete(token, connection.state()));
            } finally {
                release.countDown();
                joined(owner, failure);
            }
            check(connection.state() == CatalogConnection.State.CLOSED);
            check(!lifetime.complete(token, connection.state()));
            check(lifetime.failure() == CatalogLifetime.Failure.BACKEND_DEADLINE);
            check(lifetime.begin() == null && operations.close.get() == 1);
        });
        check(passed == 12);
        System.out.println("PASS CATALOG_LIFETIME_CONNECTION " + passed);
    }
}
