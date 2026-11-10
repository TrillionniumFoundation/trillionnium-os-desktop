package org.droidloom.qa.editorcontract;

import android.util.AtomicFile;
import java.io.File;
import org.json.JSONArray;

/** Calls the actual production snapshot/take methods, not a second state machine. */
public final class RetainedEditorStateTest {
    private static int checks;
    private static final String RUN = "host_recreate_01";
    private static final String TEXT = "中文 A🙂B";
    private static void check(boolean ok) {
        if (!ok) throw new AssertionError("check " + (checks + 1));
        checks++;
    }
    private static void rejected(Runnable operation) {
        try { operation.run(); }
        catch (IllegalStateException expected) { checks++; return; }
        throw new AssertionError("rejection required " + (checks + 1));
    }
    public static void main(String[] args) {
        Object old = new Object(), replacement = new Object(), third = new Object();
        SessionOwner<RetainedEditorState> lease = new SessionOwner<RetainedEditorState>(RUN, old);
        AtomicFile journal = new AtomicFile(new File("unused-no-IO"));
        JSONArray events = new JSONArray();
        rejected(() -> new RetainedEditorState(lease, old, RUN, journal, events,
                1234L, 4, 2, 7, TEXT, -1, 0));
        check(lease.owns(old));
        rejected(() -> new RetainedEditorState(lease, old, RUN, journal, events,
                1234L, 4, 2, 7, TEXT, 0, TEXT.length() + 1));
        check(lease.owns(old));
        rejected(() -> new RetainedEditorState(lease, old, RUN, journal, events,
                1234L, -1, 2, 7, TEXT, 0, 0));
        check(lease.owns(old));
        rejected(() -> new RetainedEditorState(lease, old, RUN, null, events,
                1234L, 4, 2, 7, TEXT, 0, 0));
        check(lease.owns(old));
        RetainedEditorState state = new RetainedEditorState(lease, old, RUN, journal,
                events, 1234L, 4, 2, 7, TEXT, TEXT.length(), 2);
        check(!lease.owns(old));
        rejected(() -> state.take("different_new_intent", replacement));
        check(!lease.owns(replacement));
        RetainedEditorState received = state.take(RUN, replacement);
        check(received == state && lease.owns(replacement));
        check(received.evidence == journal && received.events == events);
        check(received.createdElapsed == 1234L && received.editorActions == 4
                && received.connections == 2 && received.droppedEvents == 7);
        check(TEXT.equals(received.text) && received.selectionStart == TEXT.length()
                && received.selectionEnd == 2);
        rejected(() -> state.take(RUN, third));
        lease.closeIfOwner(old);
        check(lease.owns(replacement));
        RetainedEditorState again = new RetainedEditorState(lease, replacement, RUN,
                received.evidence, received.events, received.createdElapsed,
                received.editorActions, received.connections, received.droppedEvents,
                received.text, -1, -1);
        check(again.take(RUN, third) == again && lease.owns(third));
        check(again.evidence == journal && again.events == events
                && again.editorActions == 4 && again.connections == 2
                && again.selectionStart == -1 && again.selectionEnd == -1);
        // A process restart has no framework-retained in-memory ticket.
        // Matching nonce alone cannot transfer the old lease or journal.
        rejected(() -> lease.attach(RUN, new Object(), null));
        check(lease.owns(third));
        System.out.println("PASS RetainedEditorStateTest checks=" + checks
                + " Android_lifecycle_executed=false file_IO_simulated=false");
    }
}
