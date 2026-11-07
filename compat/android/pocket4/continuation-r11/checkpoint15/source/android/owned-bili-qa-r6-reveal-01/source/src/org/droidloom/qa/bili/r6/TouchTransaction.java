package org.droidloom.qa.bili.r6;

import java.util.ArrayList;
import java.util.List;

/** One fixed pointer stream; used unchanged by the Android adapter and host controls. */
final class TouchTransaction<E> {
    static final int DOWN = 0, UP = 1, CANCEL = 3;
    static final long MAX_DOWN_TO_UP_ADMISSION_MS = 150;

    interface Backend<E> {
        long now();
        E obtain(int action, long downTime, long eventTime) throws Exception;
        void beforeDown() throws Exception;
        boolean inject(E event) throws Exception;
        void recycle(E event) throws Exception;
    }
    static final class Fault extends Exception {
        Fault(String message) { super(message); }
    }
    static final class Observation {
        boolean downAttempted, downAcknowledged, upAttempted, upAcknowledged;
        boolean cancelCreationAttempted, cancelAttempted, cancelAcknowledged;
        boolean downCreated, upCreated, cancelCreated;
        boolean downRecycled, upRecycled, cancelRecycled;
        long downTime, upAdmissionElapsed = -1, finishedTime;
        Exception primary;
        final List<String> secondary = new ArrayList<String>();
        void remember(String phase, Exception error) {
            if (primary == null) primary = error;
            else secondary.add(phase + ":" + code(error));
        }
        boolean inputTerminated() { return !downAttempted || upAcknowledged || cancelAcknowledged; }
        boolean allCreatedRecycled() {
            return (!downCreated || downRecycled) && (!upCreated || upRecycled)
                && (!cancelCreated || cancelRecycled);
        }
    }
    static String code(Exception error) {
        return error instanceof Fault ? error.getMessage() : "EXCEPTION_" + error.getClass().getSimpleName();
    }
    static void need(boolean value, String message) throws Fault {
        if (!value) throw new Fault(message);
    }

    static <E> Observation run(Backend<E> backend) {
        Observation out = new Observation();
        E down = null, up = null, cancel = null;
        try {
            out.downTime = backend.now();
            down = backend.obtain(DOWN, out.downTime, out.downTime);
            need(down != null, "REVEAL_DOWN_EVENT_REQUIRED"); out.downCreated = true;
            backend.beforeDown();
            long admission = backend.now() - out.downTime;
            need(admission >= 0 && admission <= MAX_DOWN_TO_UP_ADMISSION_MS,
                 "REVEAL_DOWN_ADMISSION_DEADLINE");
            out.downAttempted = true;
            out.downAcknowledged = backend.inject(down);
            need(out.downAcknowledged, "REVEAL_DOWN_NOT_ACKNOWLEDGED");
            long now = backend.now(); out.upAdmissionElapsed = now - out.downTime;
            need(out.upAdmissionElapsed >= 0 && out.upAdmissionElapsed <= MAX_DOWN_TO_UP_ADMISSION_MS,
                 "REVEAL_UP_ADMISSION_DEADLINE");
            up = backend.obtain(UP, out.downTime, now);
            need(up != null, "REVEAL_UP_EVENT_REQUIRED"); out.upCreated = true;
            long ready = backend.now() - out.downTime;
            need(ready >= 0 && ready <= MAX_DOWN_TO_UP_ADMISSION_MS, "REVEAL_UP_CREATION_DEADLINE");
            out.upAttempted = true;
            out.upAcknowledged = backend.inject(up);
            need(out.upAcknowledged, "REVEAL_UP_NOT_ACKNOWLEDGED");
        } catch (Exception error) {
            out.remember("pointer_stream", error);
        } finally {
            // A failed or uncertain DOWN/UP never causes another DOWN/UP. One
            // CANCEL, with a current timestamp, is the only cleanup input.
            if (out.downAttempted && !out.upAcknowledged) {
                try {
                    out.cancelCreationAttempted = true;
                    cancel = backend.obtain(CANCEL, out.downTime, backend.now());
                    need(cancel != null, "REVEAL_CANCEL_EVENT_REQUIRED"); out.cancelCreated = true;
                    out.cancelAttempted = true;
                    out.cancelAcknowledged = backend.inject(cancel);
                    need(out.cancelAcknowledged, "REVEAL_CANCEL_NOT_ACKNOWLEDGED");
                } catch (Exception error) { out.remember("pointer_cancel", error); }
            }
            if (up != null) {
                try { backend.recycle(up); out.upRecycled = true; }
                catch (Exception error) { out.remember("up_recycle", error); }
            }
            if (down != null) {
                try { backend.recycle(down); out.downRecycled = true; }
                catch (Exception error) { out.remember("down_recycle", error); }
            }
            if (cancel != null) {
                try { backend.recycle(cancel); out.cancelRecycled = true; }
                catch (Exception error) { out.remember("cancel_recycle", error); }
            }
            try { out.finishedTime = backend.now(); }
            catch (Exception error) { out.remember("final_clock", error); }
        }
        return out;
    }
}
