/*
 * Copyright 2026 Droidloom
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
package com.android.droidloom.catalog;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.FileDescriptor;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InterruptedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Host regressions for the production protocol/session/FD-drain/budget methods.
 * Android PM and SCM_RIGHTS delivery are explicit adapters, not claimed here.
 */
public final class CatalogProtocolTest {
    private static int passed;
    private interface Check { void run() throws Exception; }

    private static void check(boolean condition) {
        if (!condition) throw new AssertionError("catalog regression failed");
    }

    private static void run(String name, Check action) throws Exception {
        action.run();
        passed++;
        System.out.println("PASS " + name);
    }

    private static byte[] frame(int operation, int user, int size, String component)
            throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(result);
        byte[] value = component.getBytes(StandardCharsets.UTF_8);
        out.write(CatalogProtocol.MAGIC);
        out.writeByte(operation);
        out.writeInt(user);
        out.writeInt(size);
        out.writeShort(value.length);
        out.write(value);
        return result.toByteArray();
    }

    private static byte[] list() throws IOException { return frame(1, 0, 0, ""); }

    private static String reply(byte[] bytes, int expectedStatus) throws IOException {
        DataInputStream input = new DataInputStream(new ByteArrayInputStream(bytes));
        byte[] magic = new byte[8];
        input.readFully(magic);
        check(Arrays.equals(magic, CatalogProtocol.MAGIC));
        check(input.readUnsignedByte() == expectedStatus);
        int count = input.readInt();
        check(count > 0 && count <= CatalogProtocol.MAX_RESPONSE_BYTES);
        byte[] payload = new byte[count];
        input.readFully(payload);
        check(input.read() == -1);
        return new String(payload, StandardCharsets.UTF_8);
    }

    private static byte[] serve(byte[] request, CatalogSession.Query backend) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        CatalogSession.serve(new ByteArrayInputStream(request), output, backend, () -> 0L, 0L);
        return output.toByteArray();
    }

    private static void invalid(byte[] request) throws IOException {
        AtomicInteger calls = new AtomicInteger();
        String result = reply(serve(request, ignored -> {
            calls.incrementAndGet();
            return "SHOULD_NOT_RUN";
        }), CatalogProtocol.INVALID);
        check(result.equals("INVALID_REQUEST") && calls.get() == 0);
    }

    private static void expectLimit(Check action) throws Exception {
        try {
            action.run();
            throw new AssertionError("output bound was not enforced");
        } catch (CatalogBudget.OutputLimit expected) {
            check(expected.getMessage().equals("CATALOG_OUTPUT_LIMIT"));
        }
    }

    private static void closeDescriptor(FileDescriptor descriptor) throws IOException {
        // These are test-owned descriptors. FileDescriptor.closeAll invalidates
        // every Java stream sharing the descriptor; final owner.close is safe.
        new FileInputStream(descriptor).close();
    }

    public static void main(String[] arguments) throws Exception {
        check(arguments.length == 0);
        run("fresh_backend_per_request_and_icon_arguments", () -> {
            AtomicInteger calls = new AtomicInteger();
            CatalogSession.Query backend = request -> {
                int call = calls.incrementAndGet();
                if (call <= 2) {
                    check(request.operation == 1 && request.user == 0
                            && request.size == 0 && request.component.isEmpty());
                    return call == 1 ? "FIRST_FRESH_LIST" : "SECOND_CHANGED_LIST";
                }
                check(request.operation == 2 && request.user == 10 && request.size == 128
                        && request.component.equals("org.example.catalog/.Main"));
                return "FRESH_ICON";
            };
            check(reply(serve(list(), backend), 0).equals("FIRST_FRESH_LIST"));
            check(reply(serve(list(), backend), 0).equals("SECOND_CHANGED_LIST"));
            check(reply(serve(frame(2, 10, 128, "org.example.catalog/.Main"), backend), 0)
                    .equals("FRESH_ICON"));
            check(calls.get() == 3);
        });
        run("strict_header_version_and_truncation", () -> {
            byte[] bad = list();
            bad[0] ^= 1;
            invalid(bad);
            for (int count : new int[] {0, 1, 7, 8, 9, 12, 16, 18}) {
                invalid(Arrays.copyOf(list(), count));
            }
        });
        run("closed_operations_users_and_icon_bounds", () -> {
            invalid(frame(0, 0, 0, ""));
            invalid(frame(3, 0, 0, ""));
            invalid(frame(1, -1, 0, ""));
            invalid(frame(1, CatalogProtocol.MAX_USER + 1, 0, ""));
            invalid(frame(1, 0, 1, ""));
            invalid(frame(1, 0, 0, "org.example/.Main"));
            invalid(frame(2, 0, 15, "org.example/.Main"));
            invalid(frame(2, 0, 513, "org.example/.Main"));
        });
        run("strict_component_utf8_and_single_request_eof", () -> {
            invalid(frame(2, 0, 128, "no_package/Main"));
            invalid(frame(2, 0, 128, "org.example/"));
            invalid(frame(2, 0, 128, "org.example/.Main/extra"));
            invalid(frame(2, 0, 128, "org.example/Bad-Name"));
            invalid(frame(2, 0, 128, "org.example/" + "A".repeat(512)));
            byte[] utf8 = frame(2, 0, 128, "org.example/A");
            utf8[utf8.length - 1] = (byte) 0xff;
            invalid(utf8);
            byte[] twice = new byte[list().length * 2];
            System.arraycopy(list(), 0, twice, 0, list().length);
            System.arraycopy(list(), 0, twice, list().length, list().length);
            invalid(twice);
        });
        run("fragmented_reads_preserve_one_complete_request", () -> {
            InputStream fragmented = new ByteArrayInputStream(list()) {
                @Override
                public synchronized int read(byte[] bytes, int offset, int length) {
                    return super.read(bytes, offset, Math.min(length, 1));
                }
            };
            AtomicInteger drains = new AtomicInteger();
            CatalogGuardedInput input = new CatalogGuardedInput(fragmented, () -> {
                drains.incrementAndGet();
                return false;
            });
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            CatalogSession.serve(input, output, ignored -> "[]", () -> 0L, 0L);
            input.drainPending();
            check(reply(output.toByteArray(), 0).equals("[]"));
            check(drains.get() >= list().length + 2);
        });
        run("backend_errors_are_closed_and_private_text_never_escapes", () -> {
            byte[] result = serve(list(), ignored -> {
                throw new IOException("PRIVATE_PACKAGE_PATH_AND_ACCOUNT_DATA");
            });
            check(reply(result, 2).equals("CATALOG_UNAVAILABLE"));
            check(!new String(result, StandardCharsets.UTF_8).contains("PRIVATE"));
        });
        run("expired_request_never_calls_backend_or_emits_success", () -> {
            AtomicInteger calls = new AtomicInteger();
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            try {
                CatalogSession.serve(new ByteArrayInputStream(list()), output, ignored -> {
                    calls.incrementAndGet();
                    return "LATE";
                }, () -> 5_000_000_000L, 0L);
                throw new AssertionError("expired request accepted");
            } catch (InterruptedIOException expected) {
                check(output.size() == 0 && calls.get() == 0);
            }
        });
        run("backend_finishing_after_deadline_cannot_return_a_stale_success", () -> {
            AtomicLong time = new AtomicLong();
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            try {
                CatalogSession.serve(new ByteArrayInputStream(list()), output, ignored -> {
                    time.set(5_000_000_000L);
                    return "LATE_PRIVATE_RESULT";
                }, time::get, 0L);
                throw new AssertionError("late backend accepted");
            } catch (InterruptedIOException expected) {
                check(output.size() == 0);
            }
        });
        run("oversized_backend_and_constructor_limit_have_closed_errors", () -> {
            check(reply(serve(list(), ignored ->
                    "x".repeat(CatalogProtocol.MAX_RESPONSE_BYTES + 1)), 4)
                    .equals("CATALOG_OUTPUT_LIMIT"));
            check(reply(serve(list(), ignored -> {
                throw new CatalogBudget.OutputLimit();
            }), 4).equals("CATALOG_OUTPUT_LIMIT"));
        });
        run("received_fd_batch_is_closed_before_any_following_read", () -> {
            Path path = Files.createTempFile("catalog-fd-", ".owned");
            try (FileInputStream first = new FileInputStream(path.toFile());
                    FileInputStream second = new FileInputStream(path.toFile())) {
                FileDescriptor a = first.getFD(), b = second.getFD();
                AtomicReference<FileDescriptor[]> pending = new AtomicReference<>();
                AtomicBoolean healthy = new AtomicBoolean(true);
                AtomicInteger reads = new AtomicInteger(), calls = new AtomicInteger();
                InputStream delivered = new ByteArrayInputStream(list()) {
                    @Override
                    public synchronized int read(byte[] bytes, int offset, int length) {
                        check(pending.get() == null);
                        if (reads.incrementAndGet() == 3) pending.set(new FileDescriptor[] {a, b});
                        return super.read(bytes, offset, Math.min(length, 1));
                    }
                };
                CatalogGuardedInput input = new CatalogGuardedInput(delivered, () ->
                        CatalogAncillary.drain(() -> pending.getAndSet(null),
                                CatalogProtocolTest::closeDescriptor, healthy));
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                CatalogSession.serve(input, output, ignored -> {
                    calls.incrementAndGet();
                    return "FORBIDDEN";
                }, () -> 0L, 0L);
                input.drainPending();
                check(reply(output.toByteArray(), 1).equals("INVALID_REQUEST"));
                check(reads.get() == 3 && calls.get() == 0 && healthy.get()
                        && !a.valid() && !b.valid() && pending.get() == null);
            } finally {
                Files.delete(path);
            }
        });
        run("read_failure_still_drains_fds_and_preserves_original_io", () -> {
            Path path = Files.createTempFile("catalog-fd-", ".owned");
            try (FileInputStream owned = new FileInputStream(path.toFile())) {
                FileDescriptor descriptor = owned.getFD();
                IOException original = new IOException("ORIGINAL_READ_FAILURE");
                AtomicReference<FileDescriptor[]> pending =
                        new AtomicReference<>(new FileDescriptor[] {descriptor});
                AtomicBoolean healthy = new AtomicBoolean(true);
                CatalogGuardedInput input = new CatalogGuardedInput(new InputStream() {
                    @Override public int read() throws IOException { throw original; }
                }, () -> CatalogAncillary.drain(() -> pending.getAndSet(null),
                        CatalogProtocolTest::closeDescriptor, healthy));
                try {
                    input.read();
                    throw new AssertionError("read failure lost");
                } catch (IOException actual) {
                    check(actual == original && actual.getSuppressed().length == 1);
                    check(!descriptor.valid() && healthy.get() && pending.get() == null);
                }
            } finally {
                Files.delete(path);
            }
        });
        run("one_fd_close_failure_does_not_skip_remaining_fds_or_stay_healthy", () -> {
            Path path = Files.createTempFile("catalog-fd-", ".owned");
            try (FileInputStream first = new FileInputStream(path.toFile());
                    FileInputStream second = new FileInputStream(path.toFile())) {
                FileDescriptor a = first.getFD(), b = second.getFD();
                AtomicBoolean healthy = new AtomicBoolean(true);
                AtomicInteger attempted = new AtomicInteger();
                try {
                    CatalogAncillary.drain(() -> new FileDescriptor[] {a, b}, descriptor -> {
                        attempted.incrementAndGet();
                        if (descriptor == a) throw new IOException("INJECTED_FIRST_CLOSE_FAILURE");
                        closeDescriptor(descriptor);
                    }, healthy);
                    throw new AssertionError("failed cleanup accepted");
                } catch (IOException expected) {
                    check(!healthy.get() && attempted.get() == 2 && a.valid() && !b.valid());
                }
            } finally {
                Files.delete(path);
            }
        });
        run("ancillary_source_failure_poison_and_final_drain", () -> {
            AtomicBoolean healthy = new AtomicBoolean(true);
            try {
                CatalogAncillary.drain(() -> { throw new IOException("SOURCE_FAILURE"); },
                        ignored -> { throw new AssertionError(); }, healthy);
                throw new AssertionError("ancillary source accepted");
            } catch (IOException expected) { check(!healthy.get()); }
            AtomicInteger drains = new AtomicInteger();
            CatalogGuardedInput input = new CatalogGuardedInput(
                    new ByteArrayInputStream(new byte[0]), () -> {
                        drains.incrementAndGet();
                        return false;
                    });
            input.drainPending();
            check(drains.get() == 1);
        });
        run("label_bound_precedes_to_string_and_counts_utf8", () -> {
            expectLimit(() -> CatalogBudget.label(new CharSequence() {
                @Override public int length() { return 1025; }
                @Override public char charAt(int index) { throw new AssertionError(); }
                @Override public CharSequence subSequence(int start, int end) {
                    throw new AssertionError();
                }
                @Override public String toString() { throw new AssertionError("copied huge label"); }
            }, "org.example"));
            check(CatalogBudget.utf8Size("é".repeat(512), 1024) == 1024);
            expectLimit(() -> CatalogBudget.utf8Size("é".repeat(513), 1024));
            expectLimit(() -> CatalogBudget.utf8Size("\ud800", 1024));
            check(CatalogBudget.utf8Size("\ud83d\ude00", 1024) == 4);
        });
        run("bounded_json_escapes_and_configuration_keys_remain_fresh", () -> {
            CatalogBudget first = new CatalogBudget();
            first.add("A\"\\\n", "org.example", "org.example/.Main", "1:2:3:" + "a".repeat(64));
            String a = first.finish();
            check(a.equals("[{\"name\":\"A\\\"\\\\\\u000a\",\"package\":\"org.example\","
                    + "\"component\":\"org.example/.Main\",\"icon_key\":\"1:2:3:"
                    + "a".repeat(64) + "\"}]"));
            CatalogBudget second = new CatalogBudget();
            second.add("A\"\\\n", "org.example", "org.example/.Main", "1:2:3:" + "b".repeat(64));
            check(!a.equals(second.finish()));
            expectLimit(() -> new CatalogBudget().add(
                    "bad\0label", "org.example", "org.example/.Main", "1"));
        });
        run("aggregate_encoded_budget_rejects_before_partial_append", () -> {
            CatalogBudget result = new CatalogBudget();
            int accepted = 0;
            for (;;) {
                try {
                    result.add("\u0001".repeat(1024), "org.example",
                            "org.example/.Main" + accepted, "1:2:3");
                    accepted++;
                } catch (CatalogBudget.OutputLimit limit) { break; }
            }
            String encoded = result.finish();
            check(accepted > 1 && accepted < 1024
                    && encoded.getBytes(StandardCharsets.UTF_8).length
                    <= CatalogProtocol.MAX_RESPONSE_BYTES);
            check(encoded.endsWith("\"icon_key\":\"1:2:3\"}]"));
            expectLimit(() -> result.add("x", "org.example", "org.example/.Main", "1"));
        });
        run("png_intermediate_cannot_exceed_base64_response_budget", () -> {
            CatalogBudget.PngBytes bytes = new CatalogBudget.PngBytes();
            bytes.write(new byte[CatalogBudget.MAX_PNG_BYTES], 0, CatalogBudget.MAX_PNG_BYTES);
            expectLimit(() -> bytes.write(0));
            check(bytes.size() == CatalogBudget.MAX_PNG_BYTES);
            check(4L * ((bytes.size() + 2L) / 3L) <= CatalogProtocol.MAX_RESPONSE_BYTES);
        });
        run("error_response_payload_cannot_be_arbitrary", () -> {
            try {
                CatalogProtocol.writeResponse(new ByteArrayOutputStream(), 2, "PRIVATE_EXCEPTION");
                throw new AssertionError("open error vocabulary accepted");
            } catch (IOException expected) { check(true); }
        });
        check(passed == 18);
        System.out.println("PASS CATALOG_PROTOCOL_SESSION_ANCILLARY_BUDGET " + passed);
    }
}
