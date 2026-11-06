package org.droidloom.qa.successor.p8f89f253350ba2fa.r2;

/** Exactly one current-selection transaction; no retry and no Android atomicity claim. */
public final class PlayerButtonTransaction {
    public static final long MAX_SELECTION_AGE_MS = 1000;
    public static final class Fault extends Exception {
        Fault(String code) { super(code); }
    }
    public interface Backend<C,S> {
        C inspectSelection() throws Exception;
        S selectCurrent(C selection) throws Exception;
        C inspectTarget(S selection) throws Exception;
        void requireSameWholeTreeAndWindow(C selection,C target) throws Exception;
        void requireRefreshedTarget(C target,S selection) throws Exception;
        C inspectFinal() throws Exception;
        void requireFinalWholeTreeAndWindow(C target,C last) throws Exception;
        void bindEvidence(C selection,C target,C last,S selected) throws Exception;
        long selectedAt(C selection) throws Exception;
        long now();
        void beforeAction(long admitted,long age) throws Exception;
        boolean clickOnce(C target) throws Exception;
        void close(C capture) throws Exception;
    }
    private static <C,S> Exception close(Backend<C,S> backend,C capture,Exception primary) {
        if (capture == null) return primary;
        try { backend.close(capture); }
        catch (Exception error) {
            if (primary == null) primary=error;
            else primary.addSuppressed(error);
        }
        return primary;
    }
    public static <C,S> void run(Backend<C,S> backend) throws Exception {
        C first=null,target=null,last=null;Exception primary=null;
        try {
            first=backend.inspectSelection();
            S selected=backend.selectCurrent(first);
            target=backend.inspectTarget(selected);
            backend.requireSameWholeTreeAndWindow(first,target);
            backend.requireRefreshedTarget(target,selected);
            last=backend.inspectFinal();
            backend.requireFinalWholeTreeAndWindow(target,last);
            backend.bindEvidence(first,target,last,selected);
            // Match the original action: close the final read before dispatch.
            C closing=last;last=null;backend.close(closing);
            long admitted=backend.now(),age=admitted-backend.selectedAt(first);
            if (age<0 || age>MAX_SELECTION_AGE_MS) throw new Fault("CURRENT_PLAYER_SELECTION_TOO_OLD");
            backend.beforeAction(admitted,age);
            if (!backend.clickOnce(target)) throw new Fault("PLAYER_BUTTON_NOT_ACKNOWLEDGED_OUTCOME_UNKNOWN");
        } catch (Exception error) { primary=error; }
        finally {
            primary=close(backend,last,primary);
            primary=close(backend,target,primary);
            primary=close(backend,first,primary);
        }
        if (primary!=null) throw primary;
    }
    private PlayerButtonTransaction() {}
}
