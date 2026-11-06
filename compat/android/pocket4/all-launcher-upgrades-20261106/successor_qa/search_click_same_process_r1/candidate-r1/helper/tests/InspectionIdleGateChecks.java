package org.droidloom.qa.successor.p8f89f253350ba2fa.r2;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeoutException;

/** Executes the exact production gate with bounded clocks/waiters; no Android classes. */
public final class InspectionIdleGateChecks {
    interface Check { void run() throws Exception; }
    static final List<String> passed = new ArrayList<String>();

    static void need(boolean value, String name) {
        if (!value) throw new AssertionError(name);
    }
    static void check(String name, Check body) throws Exception {
        body.run();
        passed.add(name);
    }
    static final class Fixture implements InspectionIdleGate.Clock, InspectionIdleGate.Waiter {
        final InspectionIdleGate.Observation observation;
        final long began, last;
        int clockReads, calls, clockFailureAt;
        long quietArgument = -1, globalArgument = -1;
        Exception apiFailure;
        final IllegalStateException clockFailure = new IllegalStateException("fixed-clock-failure");

        Fixture(long start, long began, long last) {
            this.observation = new InspectionIdleGate.Observation(start);
            this.began = began; this.last = last;
        }
        public long now() {
            clockReads++;
            if (clockReads == clockFailureAt) throw clockFailure;
            if (clockReads > 2) throw new AssertionError("clock read retried");
            return clockReads == 1 ? began : last;
        }
        public void waitForIdle(long quiet, long global) throws Exception {
            calls++; quietArgument = quiet; globalArgument = global;
            if (calls != 1) throw new AssertionError("API retried");
            if (apiFailure != null) throw apiFailure;
        }
        void run() throws InspectionIdleGate.Fault {
            InspectionIdleGate.once(observation, this, this);
        }
        void fault(String code, Exception cause) throws Exception {
            try { run(); throw new AssertionError("expected rejection " + code); }
            catch (InspectionIdleGate.Fault failure) {
                need(code.equals(failure.getMessage()), "wrong rejection " + failure.getMessage());
                need(failure.getCause() == cause, "original cause not retained");
                need(!observation.qualified, "failed observation qualified");
            }
        }
        void good(long expectedGlobal, long expectedWaited) throws Exception {
            run();
            need(observation.invoked && observation.qualified && observation.apiReturned, "success flags");
            need(calls == 1 && observation.callCount == 1 && clockReads == 2, "exact call/read counts");
            need(quietArgument == 500 && globalArgument == expectedGlobal
                    && observation.globalMillis == expectedGlobal, "budget arguments");
            need(observation.waited == expectedWaited && observation.began == began
                    && observation.last == last, "actual time record");
            need(observation.error.isEmpty() && observation.exceptionClass.isEmpty()
                    && observation.secondaryClockExceptionClass.isEmpty(), "success errors");
        }
    }

    public static void main(String[] args) throws Exception {
        need(args.length == 0, "no arbitrary arguments");
        check("fixed_original_budgets", new Check() { public void run() {
            need(InspectionIdleGate.QUIET_MS == 500 && InspectionIdleGate.GLOBAL_CAP_MS == 2000
                    && InspectionIdleGate.OPERATION_DEADLINE_MS == 8000, "fixed budgets");
        }});
        check("one_successful_event_quiet_call", new Check() { public void run() throws Exception {
            new Fixture(1000, 1100, 1600).good(2000, 500);
        }});
        check("already_quiet_immediate_return_allowed", new Check() { public void run() throws Exception {
            new Fixture(1000, 1100, 1100).good(2000, 0);
        }});
        check("global_cap_exact_edge_allowed", new Check() { public void run() throws Exception {
            new Fixture(1000, 1100, 3100).good(2000, 2000);
        }});
        check("remaining_original_budget_clamps_global", new Check() { public void run() throws Exception {
            new Fixture(1000, 8000, 8500).good(1000, 500);
        }});
        check("exact_quiet_budget_one_call", new Check() { public void run() throws Exception {
            new Fixture(1000, 8500, 9000).good(500, 500);
        }});
        check("insufficient_quiet_budget_no_call", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 8501, 8501);
            f.fault("INSPECTION_IDLE_BUDGET_EXHAUSTED", null);
            need(f.calls == 0 && f.clockReads == 1 && f.observation.globalMillis == 499, "no insufficient call");
        }});
        check("expired_original_deadline_no_call", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 9001, 9001);
            f.fault("INSPECTION_IDLE_BUDGET_EXHAUSTED", null);
            need(f.calls == 0 && f.observation.globalMillis == 0, "expired no call");
        }});
        check("clock_before_operation_start_no_call", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 999, 999);
            f.fault("INSPECTION_IDLE_CLOCK_INVALID", null);
            need(f.calls == 0, "invalid clock no call");
        }});
        check("negative_operation_start_no_call", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(-1, 0, 0);
            f.fault("INSPECTION_IDLE_CLOCK_INVALID", null);
            need(f.calls == 0, "negative start no call");
        }});
        check("operation_deadline_overflow_no_call", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(Long.MAX_VALUE - 7999, Long.MAX_VALUE - 7999, Long.MAX_VALUE - 7999);
            f.fault("INSPECTION_IDLE_CLOCK_INVALID", null);
            need(f.calls == 0, "overflow no call");
        }});
        check("first_clock_failure_no_call", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 1100, 1600); f.clockFailureAt = 1;
            f.fault("INSPECTION_IDLE_CLOCK_FAILED", f.clockFailure);
            need(f.calls == 0 && f.clockReads == 1
                    && f.observation.exceptionClass.equals("java.lang.IllegalStateException"), "first clock evidence");
        }});
        check("timeout_preserves_original_cause_no_retry", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 1100, 3101);
            f.apiFailure = new TimeoutException("fixed-timeout");
            f.fault("INSPECTION_IDLE_TIMEOUT", f.apiFailure);
            need(f.calls == 1 && f.clockReads == 2 && !f.observation.apiReturned
                    && f.observation.waited == 2001
                    && f.observation.exceptionClass.equals("java.util.concurrent.TimeoutException"), "timeout evidence");
        }});
        check("disconnected_api_preserves_original_cause", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 1100, 1101);
            f.apiFailure = new IllegalStateException("fixed-disconnected");
            f.fault("INSPECTION_IDLE_WAIT_FAILED", f.apiFailure);
            need(f.calls == 1 && !f.observation.apiReturned, "disconnected no retry");
        }});
        check("timeout_and_clock_failure_keep_first_error", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 1100, 3100);
            f.apiFailure = new TimeoutException("first-timeout"); f.clockFailureAt = 2;
            f.fault("INSPECTION_IDLE_TIMEOUT", f.apiFailure);
            need(f.calls == 1 && f.observation.secondaryClockExceptionClass.equals("java.lang.IllegalStateException"),
                    "secondary clock error retained");
        }});
        check("successful_api_then_clock_failure_unqualified", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 1100, 1600); f.clockFailureAt = 2;
            f.fault("INSPECTION_IDLE_WAIT_FAILED", f.clockFailure);
            need(f.calls == 1 && f.observation.apiReturned, "returned API is not qualification");
        }});
        check("final_clock_regression_unqualified", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 1100, 1099);
            f.fault("INSPECTION_IDLE_CLOCK_INVALID", null);
            need(f.calls == 1 && f.observation.waited == -1, "regression evidence");
        }});
        check("global_cap_overrun_unqualified", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 1100, 3101);
            f.fault("INSPECTION_IDLE_BUDGET_EXCEEDED", null);
            need(f.calls == 1 && f.observation.apiReturned, "late returned API must fail");
        }});
        check("owner_deadline_overrun_unqualified", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 8500, 9001);
            f.fault("INSPECTION_IDLE_BUDGET_EXCEEDED", null);
            need(f.globalArgument == 500 && f.calls == 1, "original deadline not extended");
        }});
        check("duplicate_after_success_cannot_call_again", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 1100, 1600); f.good(2000, 500);
            try { f.run(); throw new AssertionError("second invocation accepted"); }
            catch (InspectionIdleGate.Fault failure) {
                need(failure.getMessage().equals("INSPECTION_IDLE_ALREADY_INVOKED")
                        && f.calls == 1 && f.clockReads == 2 && f.observation.qualified
                        && f.observation.error.isEmpty(), "original success record preserved");
            }
        }});
        check("duplicate_after_timeout_cannot_call_again", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 1100, 3100); f.apiFailure = new TimeoutException("first");
            f.fault("INSPECTION_IDLE_TIMEOUT", f.apiFailure);
            f.fault("INSPECTION_IDLE_ALREADY_INVOKED", null);
            need(f.calls == 1 && f.clockReads == 2 && f.observation.error.equals("INSPECTION_IDLE_TIMEOUT"),
                    "original timeout record preserved");
        }});
        check("duplicate_after_budget_failure_cannot_call", new Check() { public void run() throws Exception {
            Fixture f = new Fixture(1000, 8501, 8501);
            f.fault("INSPECTION_IDLE_BUDGET_EXHAUSTED", null);
            f.fault("INSPECTION_IDLE_ALREADY_INVOKED", null);
            need(f.calls == 0 && f.clockReads == 1 && f.observation.error.equals("INSPECTION_IDLE_BUDGET_EXHAUSTED"),
                    "original pre-call failure preserved");
        }});
        need(passed.size() == 22, "exact case count");
        StringBuilder out = new StringBuilder("{\"schema\":1,\"all_passed\":true,\"count\":22,\"cases\":[");
        for (int index = 0; index < passed.size(); index++) {
            if (index > 0) out.append(',');
            out.append("{\"name\":\"").append(passed.get(index)).append("\",\"passed\":true}");
        }
        out.append("],\"android_calls\":0,\"tree_captures\":0,\"input_actions\":0}");
        System.out.println(out.toString());
    }

    private InspectionIdleGateChecks() {}
}
