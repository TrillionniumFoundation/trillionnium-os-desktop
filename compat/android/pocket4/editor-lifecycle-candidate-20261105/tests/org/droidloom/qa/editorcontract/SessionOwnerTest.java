package org.droidloom.qa.editorcontract;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

/** Tests the production ownership class, not a second implementation. */
public final class SessionOwnerTest {
    private static int checks;

    private static void check(boolean value, String name) {
        if (!value) throw new AssertionError(name);
        checks++;
    }

    private static void rejects(Runnable work, String name) {
        try { work.run(); } catch (IllegalStateException expected) { checks++; return; }
        throw new AssertionError(name);
    }

    private static final class Snapshot {
        final String text = "中文 café 😀";
        final int selectionStart = 3;
        final int selectionEnd = 8;
        final int editorActions = 4;
        final int connections = 2;
        final long createdElapsed = 123456789L;
        final Object originalJournal = new Object();
        final Object originalEvents = new Object();
    }

    private static void normalTransferAndLateOldCallbacks() {
        Object oldOwner = new Object();
        Object nextOwner = new Object();
        SessionOwner<Snapshot> session = new SessionOwner<Snapshot>("owned_run", oldOwner);
        Snapshot snapshot = new Snapshot();
        check(session.owns(oldOwner), "fresh owner");
        SessionOwner.Ticket<Snapshot> ticket = session.detach(oldOwner, snapshot);
        check(!session.owns(oldOwner), "old writer disabled before transfer escapes");
        session.closeIfOwner(oldOwner);
        Snapshot restored = session.attach("owned_run", nextOwner, ticket);
        check(restored == snapshot, "same state object, no reset or reconstruction of journal");
        check(restored.text.equals("中文 café 😀") && restored.selectionStart == 3
                && restored.selectionEnd == 8, "edit state preserved");
        check(restored.editorActions == 4 && restored.connections == 2
                && restored.createdElapsed == 123456789L, "callback count and origin preserved");
        check(restored.originalJournal == snapshot.originalJournal
                && restored.originalEvents == snapshot.originalEvents, "same journal and events");
        session.closeIfOwner(oldOwner);
        check(session.owns(nextOwner) && !session.owns(oldOwner), "late old destroy cannot close successor");
        rejects(() -> session.attach("owned_run", new Object(), ticket), "ticket reuse");
        rejects(() -> session.detach(oldOwner, snapshot), "late old callback cannot transfer");
        session.closeIfOwner(nextOwner);
        check(!session.owns(nextOwner), "normal destroy closes active owner");
        rejects(() -> session.attach("owned_run", new Object(), ticket), "closed session cannot revive");
    }

    private static void missingMismatchedAndForeignAuthority() {
        Object old = new Object();
        SessionOwner<Snapshot> session = new SessionOwner<Snapshot>("run_one", old);
        rejects(() -> session.attach("run_one", new Object(), null), "same-nonce new intent is not a transfer");
        check(session.owns(old), "rejection leaves active owner unchanged");
        Snapshot snapshot = new Snapshot();
        SessionOwner.Ticket<Snapshot> ticket = session.detach(old, snapshot);
        rejects(() -> session.attach("run_other", new Object(), ticket), "nonce mismatch");
        rejects(() -> session.attach("run_one", null, ticket), "null owner");
        SessionOwner<Snapshot> afterProcessDeath = new SessionOwner<Snapshot>("run_one", new Object());
        rejects(() -> afterProcessDeath.attach("run_one", new Object(), ticket), "ticket from a different process/session");
        Object next = new Object();
        check(session.attach("run_one", next, ticket) == snapshot, "failed attempts do not consume real transfer");
        check(session.owns(next), "only proper successor acquires");
    }

    private static void exactlyOneConcurrentSuccessor() throws Exception {
        Object old = new Object();
        SessionOwner<Snapshot> session = new SessionOwner<Snapshot>("concurrent_run", old);
        Snapshot snapshot = new Snapshot();
        SessionOwner.Ticket<Snapshot> ticket = session.detach(old, snapshot);
        AtomicInteger winners = new AtomicInteger();
        AtomicInteger rejected = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);
        Thread[] threads = new Thread[2];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(() -> {
                try {
                    start.await();
                    if (session.attach("concurrent_run", new Object(), ticket) != snapshot)
                        throw new AssertionError("different state");
                    winners.incrementAndGet();
                } catch (IllegalStateException expected) { rejected.incrementAndGet(); }
                catch (InterruptedException error) { throw new AssertionError(error); }
            });
            threads[i].start();
        }
        start.countDown();
        for (Thread thread : threads) thread.join(1000);
        check(!threads[0].isAlive() && !threads[1].isAlive(), "both contenders joined");
        check(winners.get() == 1 && rejected.get() == 1, "exactly one writer wins");
    }

    private static void transferCannotCrossAnInFlightWrite() throws Exception {
        Object old = new Object();
        SessionOwner<Snapshot> session = new SessionOwner<Snapshot>("write_run", old);
        CountDownLatch writing = new CountDownLatch(1);
        CountDownLatch finish = new CountDownLatch(1);
        AtomicInteger state = new AtomicInteger();
        Thread writer = new Thread(() -> {
            synchronized (session) {
                if (!session.owns(old)) throw new AssertionError("writer disappeared");
                writing.countDown();
                try { finish.await(); } catch (InterruptedException e) { throw new AssertionError(e); }
                state.set(1);
            }
        });
        writer.start();
        writing.await();
        Thread transfer = new Thread(() -> {
            synchronized (session) {
                if (state.get() != 1) throw new AssertionError("transfer crossed journal write");
                session.detach(old, new Snapshot());
                state.set(2);
            }
        });
        transfer.start();
        check(state.get() == 0, "uncommitted write not bypassed");
        finish.countDown();
        writer.join(1000);
        transfer.join(1000);
        check(!writer.isAlive() && !transfer.isAlive() && state.get() == 2,
                "write then detach, joined, no concurrent journal writer");
    }

    public static void main(String[] args) throws Exception {
        normalTransferAndLateOldCallbacks();
        missingMismatchedAndForeignAuthority();
        exactlyOneConcurrentSuccessor();
        transferCannotCrossAnInFlightWrite();
        System.out.println("SessionOwner production checks=" + checks + " PASS; Android lifecycle unrun");
    }
}
