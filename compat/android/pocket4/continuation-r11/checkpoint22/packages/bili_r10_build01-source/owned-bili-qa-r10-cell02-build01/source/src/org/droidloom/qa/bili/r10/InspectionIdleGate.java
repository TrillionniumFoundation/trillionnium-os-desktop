package org.droidloom.qa.bili.r10;

import java.util.concurrent.TimeoutException;

/** One event-stream quiet observation. It does not capture a tree or prove content readiness. */
public final class InspectionIdleGate {
    public static final long QUIET_MS = 500;
    public static final long GLOBAL_CAP_MS = 2000;
    public static final long OPERATION_DEADLINE_MS = 8000;

    public interface Clock { long now(); }
    public interface Waiter { void waitForIdle(long quietMillis, long globalMillis) throws Exception; }

    public static final class Fault extends Exception {
        Fault(String code, Exception cause) { super(code, cause); }
    }

    public static final class Observation {
        public final long operationStarted;
        public boolean invoked, apiReturned, qualified;
        public int callCount;
        public long began, last, waited, globalMillis;
        public String exceptionClass = "", secondaryClockExceptionClass = "", error = "";
        public Observation(long operationStarted) { this.operationStarted = operationStarted; }
    }

    private static void reject(Observation observation, String code, Exception cause) throws Fault {
        observation.error = code;
        throw new Fault(code, cause);
    }

    public static void once(Observation observation, Clock clock, Waiter waiter) throws Fault {
        if (observation.invoked) throw new Fault("INSPECTION_IDLE_ALREADY_INVOKED", null);
        observation.invoked = true;
        try {
            observation.began = clock.now();
            observation.last = observation.began;
        } catch (RuntimeException error) {
            observation.exceptionClass = error.getClass().getName();
            reject(observation, "INSPECTION_IDLE_CLOCK_FAILED", error);
        }
        if (observation.operationStarted < 0 || observation.operationStarted > Long.MAX_VALUE - OPERATION_DEADLINE_MS
                || observation.began < observation.operationStarted) {
            reject(observation, "INSPECTION_IDLE_CLOCK_INVALID", null);
        }
        long deadline = observation.operationStarted + OPERATION_DEADLINE_MS;
        observation.globalMillis = Math.min(GLOBAL_CAP_MS, Math.max(0, deadline - observation.began));
        if (observation.globalMillis < QUIET_MS) {
            reject(observation, "INSPECTION_IDLE_BUDGET_EXHAUSTED", null);
        }

        Exception primary = null;
        observation.callCount = 1;
        try {
            waiter.waitForIdle(QUIET_MS, observation.globalMillis);
            observation.apiReturned = true;
        } catch (Exception error) {
            primary = error;
            observation.exceptionClass = error.getClass().getName();
        } finally {
            try {
                observation.last = clock.now();
                observation.waited = observation.last - observation.began;
            } catch (RuntimeException error) {
                if (primary == null) {
                    primary = error;
                    observation.exceptionClass = error.getClass().getName();
                } else {
                    observation.secondaryClockExceptionClass = error.getClass().getName();
                }
            }
        }
        // Keep the API's first failure even if the final clock read also failed.
        if (primary != null) {
            reject(observation, primary instanceof TimeoutException ? "INSPECTION_IDLE_TIMEOUT"
                    : "INSPECTION_IDLE_WAIT_FAILED", primary);
        }
        if (observation.last < observation.began || observation.waited < 0) {
            reject(observation, "INSPECTION_IDLE_CLOCK_INVALID", null);
        }
        if (observation.waited > observation.globalMillis || observation.last > deadline) {
            reject(observation, "INSPECTION_IDLE_BUDGET_EXCEEDED", null);
        }
        observation.qualified = true;
    }

    private InspectionIdleGate() {}
}
