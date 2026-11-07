import com.android.calendar.alerts.SnoozeState;
import static com.android.calendar.alerts.SnoozeState.*;

public final class SnoozeStateTest {
    static int checks;
    static void check(boolean value,String label) { checks++;if(!value)throw new AssertionError(label); }
    static void expect(Decision wanted,int phase,boolean valid,boolean source,int sourceState,int count,int target,boolean fresh,String label) {
        check(SnoozeState.decide(phase,valid,source,sourceState,count,target,fresh)==wanted,label);
    }
    public static void main(String[] args) {
        expect(Decision.INITIAL_WRITE,REQUESTED,true,true,FIRED,0,ABSENT,true,"one authentic fresh snooze can write");
        expect(Decision.NO_EFFECT,REQUESTED,true,true,FIRED,0,ABSENT,false,"interrupted before atomic batch is not silently replayed");
        expect(Decision.ADOPT,REQUESTED,true,true,DISMISSED,1,SCHEDULED,false,"committed batch with unknown URI is reconciled by exact row");
        expect(Decision.UNKNOWN,REQUESTED,true,true,DISMISSED,0,ABSENT,false,"compound commit/reset ambiguity never fabricates confirmation");
        expect(Decision.RESTORE,CONFIRMED,true,true,DISMISSED,0,ABSENT,false,"confirmed user snooze survives scheduled-row reset");
        expect(Decision.ADOPT,CONFIRMED,true,true,DISMISSED,1,SCHEDULED,false,"restart after restoration adopts row without inserting again");
        expect(Decision.PUBLISH,CONFIRMED,true,true,DISMISSED,1,FIRED,false,"already fired target still requires publication");
        expect(Decision.FORGET,CONFIRMED,true,true,DISMISSED,1,DISMISSED,false,"dismissed target is never resurrected");
        expect(Decision.CANCEL_TARGET,CONFIRMED,false,true,DISMISSED,1,SCHEDULED,false,"event edit cancels exact pending snooze");
        expect(Decision.CANCEL_TARGET,CONFIRMED,false,true,DISMISSED,1,FIRED,false,"event edit cancels stale fired snooze");
        expect(Decision.FORGET,CONFIRMED,false,false,ABSENT,0,ABSENT,false,"deleted event or source does not create anything");
        expect(Decision.FORGET,CONFIRMED,true,false,DISMISSED,1,SCHEDULED,false,"changed source identity cannot authorize provider writes");
        expect(Decision.CANCEL_TARGET,CANCELLED,true,true,DISMISSED,1,SCHEDULED,false,"cancel record wins over a delayed recovery delivery");
        expect(Decision.CANCEL_TARGET,CANCELLED,true,true,DISMISSED,0,ABSENT,false,"missing cancelled target requires no insert");
        expect(Decision.UNKNOWN,CONFIRMED,true,true,DISMISSED,2,SCHEDULED,false,"conflicting duplicate provider rows block mutation");
        expect(Decision.UNKNOWN,CONFIRMED,true,true,FIRED,0,ABSENT,false,"confirmed source unexpectedly reverted blocks recovery");
        expect(Decision.UNKNOWN,REQUESTED,true,true,FIRED,1,SCHEDULED,true,"preexisting target cannot silently consume original fired alert");
        expect(Decision.PUBLISH,REQUESTED,true,true,DISMISSED,1,FIRED,false,"committed then fired before acknowledgement is read back");
        expect(Decision.UNKNOWN,CONFIRMED,true,true,SCHEDULED,1,SCHEDULED,false,"reverted source does not silently discard recovery state");
        boolean invalid=false;try{SnoozeState.decide(CONFIRMED,true,true,DISMISSED,0,FIRED,false);}catch(IllegalArgumentException e){invalid=true;}
        check(invalid,"inconsistent read model rejected");
        // A reset/rebuild/interruption sequence uses actual decisions, not a second initial snooze.
        int phase=CONFIRMED;
        check(SnoozeState.decide(phase,true,true,DISMISSED,0,ABSENT,false)==Decision.RESTORE,"reset requires an exact restore");
        check(SnoozeState.decide(phase,true,true,DISMISSED,1,SCHEDULED,false)==Decision.ADOPT,"unknown restore effect adopted once");
        check(SnoozeState.decide(phase,true,true,DISMISSED,1,FIRED,false)==Decision.PUBLISH,"one later firing still needs publication");
        check(SnoozeState.canForgetPublished(CONFIRMED,true,DISMISSED,true,FIRED,true,true),"one active exact notification settles the journal");
        check(!SnoozeState.canForgetPublished(CONFIRMED,true,DISMISSED,true,FIRED,true,false),"crash after FIRED before notify retains recovery");
        check(!SnoozeState.canForgetPublished(REQUESTED,true,DISMISSED,true,FIRED,true,true),"unknown initial write must first be reconciled");
        check(!SnoozeState.canForgetPublished(CONFIRMED,false,DISMISSED,true,FIRED,true,true),"changed source cannot settle publication");
        check(!SnoozeState.canForgetPublished(CONFIRMED,true,FIRED,true,FIRED,true,true),"source dismissal must still hold");
        check(!SnoozeState.canForgetPublished(CONFIRMED,true,DISMISSED,false,FIRED,true,true),"edited event needs cancellation even after notify");
        check(!SnoozeState.canForgetPublished(CONFIRMED,true,DISMISSED,true,SCHEDULED,true,true),"old active notification cannot stand for a new pending row");
        check(!SnoozeState.canForgetPublished(CONFIRMED,true,DISMISSED,true,FIRED,false,true),"different target ID cannot settle the recorded target");
        System.out.println("SnoozeStateTest: "+checks+" checks passed");
    }
}
