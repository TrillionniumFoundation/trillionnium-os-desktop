package org.droidloom.qa.editorcontract;

import android.util.AtomicFile;
import org.json.JSONArray;

/**
 * In-memory state handed through Activity's nonconfiguration-instance channel.
 * No file is read, deleted, created, or written here. In particular this object
 * cannot be reconstructed from an Intent, Bundle, journal length or nonce.
 */
final class RetainedEditorState {
    final SessionOwner<RetainedEditorState> lease;
    final SessionOwner.Ticket<RetainedEditorState> ticket;
    final String runId;
    final AtomicFile evidence;
    final JSONArray events;
    final long createdElapsed;
    final int editorActions;
    final int connections;
    final int droppedEvents;
    final String text;
    final int selectionStart;
    final int selectionEnd;

    RetainedEditorState(SessionOwner<RetainedEditorState> lease, Object owner,
            String runId, AtomicFile evidence, JSONArray events, long createdElapsed,
            int editorActions, int connections, int droppedEvents,
            String text, int selectionStart, int selectionEnd) {
        if (lease == null || runId == null || evidence == null || events == null
                || text == null || createdElapsed < 0 || editorActions < 0
                || connections < 0 || droppedEvents < 0 || droppedEvents > 1000000) {
            throw new IllegalStateException("complete_retained_editor_state_required");
        }
        boolean noSelection = selectionStart == -1 && selectionEnd == -1;
        if (!noSelection && (selectionStart < 0 || selectionEnd < 0
                || selectionStart > text.length() || selectionEnd > text.length())) {
            throw new IllegalStateException("retained_selection_out_of_bounds");
        }
        this.lease = lease;
        this.runId = runId;
        this.evidence = evidence;
        this.events = events;
        this.createdElapsed = createdElapsed;
        this.editorActions = editorActions;
        this.connections = connections;
        this.droppedEvents = droppedEvents;
        this.text = text;
        this.selectionStart = selectionStart;
        this.selectionEnd = selectionEnd;
        // Validation precedes detachment; a rejected snapshot leaves its writer.
        this.ticket = lease.detach(owner, this);
    }

    RetainedEditorState take(String expectedRunId, Object nextOwner) {
        if (!runId.equals(expectedRunId)) {
            throw new IllegalStateException("retained_run_id_mismatch");
        }
        return lease.attach(expectedRunId, nextOwner, ticket);
    }
}
