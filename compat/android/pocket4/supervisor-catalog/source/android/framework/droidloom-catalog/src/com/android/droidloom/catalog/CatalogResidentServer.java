/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import android.net.LocalServerSocket;
import android.net.LocalSocket;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.system.ErrnoException;
import android.system.Os;
import android.util.Log;

import java.io.IOException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/** Independent init child: main accept thread, one query Looper and one deadline thread. */
final class CatalogResidentServer {
    private static final String TAG = "DroidloomCatalog";
    private static final String SOCKET_ENV = "ANDROID_SOCKET_droidloom_catalog";
    private static final int RECOVERY_GRACE_MILLIS = 2000;

    private CatalogResidentServer() {}

    private static void terminate(CatalogLifetime lifetime, CatalogLifetime.Failure reason) {
        if (lifetime.fail(reason)) {
            CatalogMain.terminate(reason.reasonCode);
        }
    }

    static void run() throws IOException {
        final int rawDescriptor;
        try {
            rawDescriptor = Integer.parseInt(System.getenv(SOCKET_ENV));
            if (rawDescriptor < 3) throw new NumberFormatException();
        } catch (RuntimeException invalid) {
            throw new IOException("CATALOG_INIT_SOCKET_REQUIRED");
        }
        ParcelFileDescriptor owner = ParcelFileDescriptor.adoptFd(rawDescriptor);
        LocalServerSocket listener;
        try {
            // The borrowed inherited descriptor is listened again by this
            // process. Host SO_PEERCRED validation binds this service, not init.
            listener = new LocalServerSocket(owner.getFileDescriptor());
        } catch (IOException failure) {
            owner.close();
            throw failure;
        }

        CatalogLifetime lifetime = new CatalogLifetime();
        AtomicReference<CatalogConnection> activeClient = new AtomicReference<>();
        AtomicReference<Handler> handler = new AtomicReference<>();
        AtomicReference<Throwable> startup = new AtomicReference<>();
        AtomicBoolean descriptorCleanupHealthy = new AtomicBoolean(true);
        AtomicBoolean deadlineThreadCreated = new AtomicBoolean(false);
        CountDownLatch initialized = new CountDownLatch(1);
        ScheduledThreadPoolExecutor deadlines = new ScheduledThreadPoolExecutor(1,
                new java.util.concurrent.ThreadFactory() {
                    @Override public Thread newThread(Runnable task) {
                        if (!deadlineThreadCreated.compareAndSet(false, true)) {
                            terminate(lifetime, CatalogLifetime.Failure.DEADLINE_WORKER);
                            throw new IllegalStateException("CATALOG_DEADLINE_WORKER_REPLACEMENT");
                        }
                        Thread thread = new Thread(task, "droidloom-catalog-deadline");
                        thread.setDaemon(true);
                        return thread;
                    }
                });
        deadlines.setMaximumPoolSize(1);
        deadlines.setRemoveOnCancelPolicy(true);
        deadlines.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
        deadlines.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);

        Thread worker = new Thread(new Runnable() {
            @Override public void run() {
                try {
                    android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_BACKGROUND);
                    Looper.prepareMainLooper();
                    handler.set(new Handler(Looper.myLooper()));
                } catch (Throwable failure) {
                    startup.set(failure);
                } finally {
                    initialized.countDown();
                }
                if (startup.get() == null) {
                    try {
                        Looper.loop();
                    } finally {
                        terminate(lifetime, CatalogLifetime.Failure.QUERY_WORKER);
                    }
                }
            }
        }, "droidloom-catalog-query");
        worker.setDaemon(true);

        try (ParcelFileDescriptor owned = owner; LocalServerSocket server = listener) {
            worker.start();
            try {
                if (!initialized.await(CatalogProtocol.REQUEST_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)
                        || startup.get() != null || handler.get() == null) {
                    throw new IOException("CATALOG_WORKER_UNAVAILABLE");
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IOException("CATALOG_START_INTERRUPTED", interrupted);
            }
            CatalogFrameworkQuery query = new CatalogFrameworkQuery();
            // This is the process main thread. It remains here for the service
            // lifetime rather than returning while only daemon workers exist.
            for (;;) {
                lifetime.requireServing();
                LocalSocket client = server.accept();
                CatalogConnection connection = connection(client);
                long started = System.nanoTime();
                ScheduledFuture<?> deadline = null;
                CatalogLifetime.Token token = null;
                ScheduledFuture<?> recovery = null;
                boolean transferred = false;
                try {
                    // A failed asynchronous self-signal cannot leave this
                    // listener serving BUSY replies or scheduling new work.
                    lifetime.requireServing();
                    deadline = deadlines.schedule(new Runnable() {
                        @Override public void run() { connection.shutdown(); }
                    }, CatalogProtocol.REQUEST_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS);
                    final ScheduledFuture<?> deadlineTimer = deadline;
                    // A host PID may be invisible in the guest PID namespace.
                    // Authorization uses only the established root UID boundary.
                    if (client.getPeerCredentials().getUid() != 0) continue;
                    client.setSoTimeout(CatalogProtocol.REQUEST_TIMEOUT_MILLIS);
                    token = lifetime.begin();
                    if (token == null) {
                        lifetime.requireServing();
                        CatalogProtocol.writeError(client.getOutputStream(), CatalogProtocol.BUSY);
                        continue;
                    }
                    final CatalogLifetime.Token request = token;
                    activeClient.set(connection);
                    recovery = deadlines.schedule(new Runnable() {
                        @Override public void run() {
                            // Completion and expiry compete for exactly this token.
                            // An old timer can never terminate a newer request.
                            if (lifetime.expire(request)) {
                                // Do not perform logging or socket I/O before the
                                // terminal action. Kernel teardown closes this
                                // independent process's descriptors.
                                CatalogMain.terminate(CatalogLifetime.Failure.BACKEND_DEADLINE.reasonCode);
                            }
                        }
                    }, CatalogProtocol.REQUEST_TIMEOUT_MILLIS + RECOVERY_GRACE_MILLIS,
                            TimeUnit.MILLISECONDS);
                    final ScheduledFuture<?> recoveryTimer = recovery;
                    boolean posted = handler.get().post(new Runnable() {
                        @Override public void run() {
                        try {
                            lifetime.requireServing();
                            CatalogGuardedInput input = new CatalogGuardedInput(
                                    client.getInputStream(),
                                    new CatalogGuardedInput.Ancillary() {
                                        @Override public boolean closeReceived() throws IOException {
                                            return CatalogResidentServer.closeReceived(
                                                    client, descriptorCleanupHealthy);
                                        }
                                    });
                            CatalogSession.serve(input, client.getOutputStream(),
                                    query, new java.util.function.LongSupplier() {
                                        @Override public long getAsLong() { return System.nanoTime(); }
                                    }, started);
                        } catch (Exception unavailable) {
                            Log.w(TAG, "Catalog query unavailable");
                        } finally {
                            try {
                                closeReceived(client, descriptorCleanupHealthy);
                            } catch (IOException unresolved) {
                                Log.e(TAG, "Catalog descriptor cleanup unavailable");
                            }
                            deadlineTimer.cancel(false);
                            CatalogConnection.State closed = close(connection, lifetime);
                            if (closed == CatalogConnection.State.CLOSED) {
                                activeClient.compareAndSet(connection, null);
                            }
                            if (!descriptorCleanupHealthy.get()) {
                                terminate(lifetime, CatalogLifetime.Failure.DESCRIPTOR_CLEANUP);
                            }
                            // Never cancel the overrun timer or release the
                            // request slot until its worker really returns.
                            if (lifetime.complete(request, closed)) recoveryTimer.cancel(false);
                        }
                        }
                    });
                    if (!posted) {
                        terminate(lifetime, CatalogLifetime.Failure.QUERY_WORKER);
                        throw new IOException("CATALOG_QUERY_WORKER_UNAVAILABLE");
                    }
                    transferred = true;
                } finally {
                    if (!transferred) {
                        if (deadline != null) deadline.cancel(false);
                        if (recovery != null) recovery.cancel(false);
                        CatalogConnection.State closed = close(connection, lifetime);
                        if (closed == CatalogConnection.State.CLOSED) {
                            activeClient.compareAndSet(connection, null);
                            if (token != null) lifetime.complete(token, closed);
                        }
                    }
                }
            }
        } finally {
            lifetime.fail(CatalogLifetime.Failure.LISTENER);
            CatalogConnection active = activeClient.getAndSet(null);
            if (active != null) close(active, lifetime);
            deadlines.shutdownNow();
            // A Binder call cannot be cancelled safely by creating a replacement
            // worker. CatalogMain terminates this process after the scope exits.
        }
    }

    private static boolean closeReceived(LocalSocket socket, AtomicBoolean healthy)
            throws IOException {
        return CatalogAncillary.drain(new CatalogAncillary.Source() {
            @Override public java.io.FileDescriptor[] take() throws IOException {
                return socket.getAncillaryFileDescriptors();
            }
        }, new CatalogAncillary.Closer() {
            @Override public void close(java.io.FileDescriptor descriptor) throws IOException {
                try {
                    Os.close(descriptor);
                } catch (ErrnoException error) {
                    throw error.rethrowAsIOException();
                }
            }
        }, healthy);
    }

    private static CatalogConnection connection(LocalSocket socket) {
        return new CatalogConnection(new CatalogConnection.Operations() {
            @Override public void shutdownInput() throws IOException { socket.shutdownInput(); }
            @Override public void shutdownOutput() throws IOException { socket.shutdownOutput(); }
            @Override public void close() throws IOException { socket.close(); }
        });
    }

    private static CatalogConnection.State close(CatalogConnection connection, CatalogLifetime lifetime) {
        connection.shutdown();
        CatalogConnection.State result = connection.closeOnce();
        if (result == CatalogConnection.State.FAILED) {
            // No query can follow an uncertain close. The independent process
            // exits; descriptor reuse is never guessed or retried.
            terminate(lifetime, CatalogLifetime.Failure.SOCKET_CLOSE);
        }
        return result;
    }
}
