package org.droidloom.qa.editorcontract;

/**
 * A single in-process writer, with a one-use framework-retained handoff.
 *
 * This class cannot reopen a durable claim. Its ticket is deliberately neither
 * Parcelable nor Serializable. A matching run id or a Bundle is not a ticket.
 * Callers hold this monitor while touching session counters or the AtomicFile,
 * so transfer and a complete journal write cannot overlap.
 */
final class SessionOwner<S> {
    private final String runId;
    private Object owner;
    private Ticket<S> pending;
    private boolean closed;

    static final class Ticket<S> {
        private final SessionOwner<S> issuer;
        private S state;

        private Ticket(SessionOwner<S> issuer, S state) {
            this.issuer = issuer;
            this.state = state;
        }
    }

    SessionOwner(String runId, Object owner) {
        if (runId == null || !runId.matches("[A-Za-z0-9_]{1,64}") || owner == null) {
            throw new IllegalArgumentException("valid_run_and_owner_required");
        }
        this.runId = runId;
        this.owner = owner;
    }

    synchronized boolean owns(Object candidate) {
        return !closed && candidate != null && owner == candidate;
    }

    synchronized Ticket<S> detach(Object candidate, S state) {
        if (!owns(candidate) || pending != null || state == null) {
            throw new IllegalStateException("current_owner_required_for_transfer");
        }
        Ticket<S> next = new Ticket<S>(this, state);
        owner = null;
        pending = next;
        return next;
    }

    synchronized S attach(String expectedRunId, Object nextOwner, Ticket<S> ticket) {
        if (closed || owner != null || nextOwner == null || !runId.equals(expectedRunId)
                || ticket == null || ticket.issuer != this || pending != ticket || ticket.state == null) {
            throw new IllegalStateException("one_use_same_session_transfer_required");
        }
        S state = ticket.state;
        ticket.state = null;
        pending = null;
        owner = nextOwner;
        return state;
    }

    /** The old Activity's later onDestroy must not revoke its successor. */
    synchronized void closeIfOwner(Object candidate) {
        if (owns(candidate)) {
            owner = null;
            closed = true;
        }
    }
}
