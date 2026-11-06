package org.droidloom.qa.bili.r7;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Executes the production transaction with explicit capture/guard/action seams. */
public final class PlayerButtonTransactionControl {
    static final class Capture { final int id;Capture(int value){id=value;} }
    static final class Backend implements PlayerButtonTransaction.Backend<Capture,String> {
        final List<String> calls=new ArrayList<String>();final List<Integer> closed=new ArrayList<Integer>();
        final Exception primary=new Exception("EXPECTED_PRIMARY"),secondary=new Exception("EXPECTED_CLOSE_SECONDARY");
        String fail;int clicks;int closeFailure=-1;long clock=1300;boolean acknowledged=true;
        void call(String name) throws Exception {calls.add(name);if(name.equals(fail))throw primary;}
        public Capture inspectSelection() throws Exception {call("selection");return new Capture(1);}
        public String selectCurrent(Capture value) throws Exception {call("role");return "fresh-role";}
        public Capture inspectTarget(String value) throws Exception {call("target");return new Capture(2);}
        public void requireSameWholeTreeAndWindow(Capture first,Capture target) throws Exception {call("full-tree");}
        public void requireRefreshedTarget(Capture current,String selected) throws Exception {call("refresh-node-eligible");}
        public Capture inspectFinal() throws Exception {call("final");return new Capture(3);}
        public void requireFinalWholeTreeAndWindow(Capture target,Capture last) throws Exception {call("final-full-tree");}
        public void bindEvidence(Capture a,Capture b,Capture c,String selected) throws Exception {call("evidence");}
        public long selectedAt(Capture value) throws Exception {call("selected-time");return 1000;}
        public long now(){return clock;}
        public void beforeAction(long now,long age) throws Exception {call("admit");}
        public boolean clickOnce(Capture target) throws Exception {clicks++;call("click");return acknowledged;}
        public void close(Capture value) throws Exception {
            closed.add(value.id);calls.add("close-"+value.id);if(value.id==closeFailure)throw secondary;
        }
    }
    static int count;
    static void need(boolean yes,String message){if(!yes)throw new AssertionError(message);}
    static Exception run(Backend backend) {
        try {PlayerButtonTransaction.run(backend);return null;}
        catch(Exception error){return error;}
    }
    static void report(String name,Backend backend,Exception error,int clicks,Integer... closed) {
        need(backend.clicks==clicks,name+":click count");
        need(backend.closed.equals(Arrays.asList(closed)),name+":cleanup "+backend.closed);
        need(backend.clicks<=1,name+":automatic replay");count++;
        System.out.println("{\"case\":\""+name+"\",\"passed\":true,\"click_calls\":"+backend.clicks+
            ",\"capture_close_order\":"+backend.closed+",\"failed\":"+(error!=null)+"}");
    }
    public static void main(String[] args) {
        Backend b=new Backend();Exception error=run(b);need(error==null,"success failed");
        need(b.calls.equals(Arrays.asList("selection","role","target","full-tree","refresh-node-eligible","final",
            "final-full-tree","evidence","close-3","selected-time","admit","click","close-2","close-1")),"guard order changed");
        report("single_click_only_after_all_complete_guards",b,error,1,3,2,1);
        String[] failures={"selection","role","target","full-tree","refresh-node-eligible","final","final-full-tree","evidence","selected-time","admit"};
        for(String failure:failures) {
            b=new Backend();b.fail=failure;error=run(b);need(error==b.primary,"original failure replaced: "+failure);
            Integer[] closed;
            if(failure.equals("selection"))closed=new Integer[]{};
            else if(failure.equals("role")||failure.equals("target"))closed=new Integer[]{1};
            else if(failure.equals("full-tree")||failure.equals("refresh-node-eligible")||failure.equals("final"))closed=new Integer[]{2,1};
            else closed=new Integer[]{3,2,1};
            report("reject_"+failure,b,error,0,closed);
        }
        b=new Backend();b.clock=2001;error=run(b);
        need("CURRENT_PLAYER_SELECTION_TOO_OLD".equals(error.getMessage()),"stale capture accepted");
        report("reject_stale_selection",b,error,0,3,2,1);
        b=new Backend();b.clock=999;error=run(b);
        need("CURRENT_PLAYER_SELECTION_TOO_OLD".equals(error.getMessage()),"negative age accepted");
        report("reject_negative_selection_age",b,error,0,3,2,1);
        b=new Backend();b.acknowledged=false;error=run(b);
        need("PLAYER_BUTTON_NOT_ACKNOWLEDGED_OUTCOME_UNKNOWN".equals(error.getMessage()),"false ACK accepted");
        report("false_ACK_unknown_no_retry",b,error,1,3,2,1);
        b=new Backend();b.fail="click";error=run(b);need(error==b.primary,"click error replaced");
        report("throwing_click_unknown_no_retry",b,error,1,3,2,1);
        b=new Backend();b.closeFailure=3;error=run(b);need(error==b.secondary,"final close error hidden");
        report("failed_final_close_prevents_input",b,error,0,3,2,1);
        b=new Backend();b.closeFailure=2;error=run(b);need(error==b.secondary,"post-input close error hidden");
        report("post_input_close_failure_retained",b,error,1,3,2,1);
        b=new Backend();b.fail="full-tree";b.closeFailure=2;error=run(b);
        need(error==b.primary&&error.getSuppressed().length==1&&error.getSuppressed()[0]==b.secondary,"primary/secondary ordering");
        report("first_guard_failure_and_cleanup_secondary_preserved",b,error,0,2,1);
        need(count==18,"case count");
        System.out.println("{\"passed\":18,\"production_transaction_compiled_and_executed\":true,\"Android_calls\":0}");
    }
}
