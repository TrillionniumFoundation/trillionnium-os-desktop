package org.droidloom.qa.successor.p8f89f253350ba2fa.r2;

/** Synthetic controls of the exact inherited transaction; no Android imports or input. */
public final class SearchTransactionChecks {
    static final String[] NAMES = {
        "three_equal_captures_one_click_all_closed", "target_tree_change_no_click", "target_window_change_no_click",
        "target_connection_change_no_click", "refresh_change_no_click", "final_tree_change_no_click",
        "final_window_change_no_click", "final_connection_change_no_click", "age_1001_no_click",
        "final_close_failure_no_click", "ack_false_single_attempt_no_retry", "selection_failure_no_click"
    };
    static final class Capture { final int id; boolean closed; Capture(int value) { id=value; } }
    static final class Backend implements PlayerButtonTransaction.Backend<Capture,Integer> {
        final String fault; final Capture[] captures=new Capture[3]; int clicks,checks;
        Backend(String value) { fault=value; }
        void fail(String phase) throws Exception { if (fault.equals(phase)) throw new Exception(phase); }
        public Capture inspectSelection() { return captures[0]=new Capture(0); }
        public Integer selectCurrent(Capture first) throws Exception { fail("selection"); return 0; }
        public Capture inspectTarget(Integer selected) { return captures[1]=new Capture(1); }
        public void requireSameWholeTreeAndWindow(Capture first,Capture target) throws Exception {
            checks++;fail("target_tree");fail("target_window");fail("target_connection");
        }
        public void requireRefreshedTarget(Capture target,Integer selected) throws Exception { fail("refresh"); }
        public Capture inspectFinal() { return captures[2]=new Capture(2); }
        public void requireFinalWholeTreeAndWindow(Capture target,Capture last) throws Exception {
            checks++;fail("final_tree");fail("final_window");fail("final_connection");
        }
        public void bindEvidence(Capture first,Capture target,Capture last,Integer selected) {
            if (checks!=2) throw new AssertionError("all comparisons before evidence");
        }
        public long selectedAt(Capture first) { return 1000; }
        public long now() { return fault.equals("age") ? 2001 : 1500; }
        public void beforeAction(long admitted,long age) {
            if (checks!=2 || !captures[2].closed) throw new AssertionError("all checks and final close before click");
        }
        public boolean clickOnce(Capture target) { clicks++;return !fault.equals("ack"); }
        public void close(Capture capture) throws Exception {
            if (capture.closed) throw new AssertionError("double close");capture.closed=true;
            if (capture.id==2) fail("final_close");
        }
    }
    public static void main(String[] args) throws Exception {
        if(args.length!=0)throw new AssertionError("no runtime arguments");
        String[] faults={"", "target_tree", "target_window", "target_connection", "refresh", "final_tree",
                         "final_window", "final_connection", "age", "final_close", "ack", "selection"};
        StringBuilder out=new StringBuilder("{\"schema\":1,\"all_passed\":true,\"count\":12,\"cases\":[");
        for(int i=0;i<faults.length;i++) {
            Backend backend=new Backend(faults[i]);Exception error=null;
            try { PlayerButtonTransaction.run(backend); } catch(Exception observed) { error=observed; }
            if ((i==0)!=(error==null))throw new AssertionError("success/failure "+NAMES[i]);
            int expectedClicks=(i==0 || faults[i].equals("ack"))?1:0;
            if(backend.clicks!=expectedClicks)throw new AssertionError("exact click count "+NAMES[i]);
            for(Capture capture:backend.captures)if(capture!=null && !capture.closed)throw new AssertionError("unclosed capture");
            if(i>0)out.append(',');out.append("{\"name\":\"").append(NAMES[i]).append("\",\"passed\":true}");
        }
        out.append("],\"android_calls\":0,\"tree_captures\":0,\"input_actions\":0}");
        System.out.println(out.toString());
    }
}
