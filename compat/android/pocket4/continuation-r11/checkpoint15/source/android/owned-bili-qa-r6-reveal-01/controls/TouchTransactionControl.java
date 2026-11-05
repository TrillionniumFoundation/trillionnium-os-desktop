package org.droidloom.qa.bili.r6;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Executes the unchanged production transaction with explicit input/clock seams. */
public final class TouchTransactionControl {
    static final class Event {
        final int action; final long downTime, eventTime;
        Event(int a,long d,long e) { action=a;downTime=d;eventTime=e; }
    }
    static final class Backend implements TouchTransaction.Backend<Event> {
        long clock=1000;
        int before, cancelObtain, downObtain, upObtain;
        int throwObtain=-1, nullObtain=-1, throwInject=-1, falseInject=-1, throwRecycle=-1;
        long downAdvance, upCreateAdvance, beforeAdvance;
        boolean beforeFails;
        final Exception primary=new Exception("OWNED_PRIMARY");
        final Exception secondary=new Exception("OWNED_SECONDARY");
        final List<Integer> injected=new ArrayList<Integer>(), recycled=new ArrayList<Integer>();
        final List<Event> allocated=new ArrayList<Event>();
        public long now() { return clock; }
        public Event obtain(int a,long d,long e) throws Exception {
            if(a==0)downObtain++;if(a==1)upObtain++;if(a==3)cancelObtain++;
            if(a==throwObtain)throw primary;
            if(a==nullObtain)return null;
            if(a==1)clock+=upCreateAdvance;
            Event result=new Event(a,d,e);allocated.add(result);return result;
        }
        public void beforeDown() throws Exception {
            before++;clock+=beforeAdvance;if(beforeFails)throw primary;
        }
        public boolean inject(Event e) throws Exception {
            injected.add(e.action);
            if(e.action==0)clock+=downAdvance;
            if(e.action==throwInject)throw primary;
            return e.action!=falseInject;
        }
        public void recycle(Event e) throws Exception {
            recycled.add(e.action);if(e.action==throwRecycle)throw secondary;
        }
    }
    static int count;
    static void need(boolean value,String why) { if(!value)throw new AssertionError(why); }
    static void row(String name,Backend b,TouchTransaction.Observation r,int... events) {
        List<Integer> expected=new ArrayList<Integer>();for(int v:events)expected.add(v);
        need(b.injected.equals(expected),name+":unexpected input/retry "+b.injected);
        need(b.downObtain<=1&&b.upObtain<=1&&b.cancelObtain<=1,name+":allocation replay");
        for(Event e:b.allocated)need(b.recycled.contains(e.action),name+":created event cleanup skipped");
        for(Event e:b.allocated) {
            need(e.downTime==1000&&e.eventTime>=e.downTime,name+":timestamp binding");
            if(e.action==3)need(e.eventTime==b.clock,name+":cancel timestamp not current");
        }
        count++;
        System.out.println("{\"case\":\""+name+"\",\"passed\":true,\"attempted_events\":"+b.injected+
          ",\"recycle_attempts\":"+b.recycled+",\"input_terminated\":"+r.inputTerminated()+
          ",\"primary_preserved\":"+(r.primary!=null)+",\"secondary_count\":"+r.secondary.size()+"}");
    }
    public static void main(String[] args) {
        Backend b=new Backend();TouchTransaction.Observation r=TouchTransaction.run(b);
        need(r.primary==null&&r.downAcknowledged&&r.upAcknowledged&&r.allCreatedRecycled(),"normal completion");
        row("single_down_up_no_cancel",b,r,0,1);
        b=new Backend();b.beforeFails=true;r=TouchTransaction.run(b);
        need(r.primary==b.primary&&!r.downAttempted,"preflight error replaced");
        row("before_down_error_no_input",b,r);
        b=new Backend();b.beforeAdvance=151;r=TouchTransaction.run(b);
        need(!r.downAttempted&&"REVEAL_DOWN_ADMISSION_DEADLINE".equals(r.primary.getMessage()),"late down admitted");
        row("late_down_no_input",b,r);
        b=new Backend();b.falseInject=0;r=TouchTransaction.run(b);
        need(!r.downAcknowledged&&r.cancelAcknowledged&&"REVEAL_DOWN_NOT_ACKNOWLEDGED".equals(r.primary.getMessage()),"false down qualified");
        row("uncertain_down_cancel_only",b,r,0,3);
        b=new Backend();b.throwInject=0;r=TouchTransaction.run(b);
        need(r.primary==b.primary&&r.cancelAcknowledged,"throw down first error");
        row("throwing_down_cancel_only",b,r,0,3);
        b=new Backend();b.falseInject=1;r=TouchTransaction.run(b);
        need(!r.upAcknowledged&&r.cancelAcknowledged,"false up qualified");
        row("uncertain_up_cancel_no_replay",b,r,0,1,3);
        b=new Backend();b.throwInject=1;r=TouchTransaction.run(b);
        need(r.primary==b.primary&&r.cancelAcknowledged,"throw up first error");
        row("throwing_up_cancel_no_replay",b,r,0,1,3);
        b=new Backend();b.downAdvance=151;r=TouchTransaction.run(b);
        need(!r.upAttempted&&b.upObtain==0&&"REVEAL_UP_ADMISSION_DEADLINE".equals(r.primary.getMessage()),"late up admitted");
        row("down_returns_late_cancel_without_up",b,r,0,3);
        b=new Backend();b.upCreateAdvance=151;r=TouchTransaction.run(b);
        need(r.upCreated&&!r.upAttempted&&"REVEAL_UP_CREATION_DEADLINE".equals(r.primary.getMessage()),"creation delay ignored");
        row("up_creation_late_cancel_and_recycle",b,r,0,3);
        b=new Backend();b.throwObtain=1;r=TouchTransaction.run(b);
        need(r.primary==b.primary&&!r.upAttempted&&r.cancelAcknowledged,"obtain first error");
        row("up_allocation_error_cancel",b,r,0,3);
        b=new Backend();b.nullObtain=1;r=TouchTransaction.run(b);
        need(!r.upCreated&&!r.upAttempted&&r.cancelAcknowledged,"null up admitted");
        row("up_allocation_null_cancel",b,r,0,3);
        b=new Backend();b.falseInject=0;b.throwObtain=3;r=TouchTransaction.run(b);
        need("REVEAL_DOWN_NOT_ACKNOWLEDGED".equals(r.primary.getMessage())&&r.secondary.size()==1&&!r.inputTerminated(),"cancel allocation masked cause");
        row("cancel_allocation_error_remains_unknown",b,r,0);
        b=new Backend();b.falseInject=0;b.throwInject=3;r=TouchTransaction.run(b);
        need("REVEAL_DOWN_NOT_ACKNOWLEDGED".equals(r.primary.getMessage())&&r.secondary.size()==1&&!r.inputTerminated(),"cancel exception masked cause");
        row("cancel_exception_remains_unknown",b,r,0,3);
        b=new Backend();b.falseInject=1;b.throwRecycle=1;r=TouchTransaction.run(b);
        need("REVEAL_UP_NOT_ACKNOWLEDGED".equals(r.primary.getMessage())&&r.secondary.size()==1&&!r.allCreatedRecycled()&&r.downRecycled&&r.cancelRecycled,"recycle prevented remaining cleanup");
        row("primary_then_recycle_error_other_events_closed",b,r,0,1,3);
        b=new Backend();b.throwRecycle=1;r=TouchTransaction.run(b);
        need(r.primary==b.secondary&&!r.allCreatedRecycled()&&r.downRecycled&&b.cancelObtain==0,"success recycle error hidden");
        row("successful_input_recycle_error_is_failure",b,r,0,1);
        b=new Backend();b.nullObtain=0;r=TouchTransaction.run(b);
        need(!r.downAttempted&&b.before==0,"null down became attempted");
        row("no_down_event_no_input",b,r);
        need(count==16,"control count");
        System.out.println("{\"passed\":16,\"actual_production_transaction\":true,\"input_clock_allocation_seams\":true,\"Android_UI_actions\":0}");
    }
}
