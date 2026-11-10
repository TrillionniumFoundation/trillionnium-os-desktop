import com.android.calendar.event.EventReference;

public final class EventReferenceTest {
    static int checks;
    static void check(boolean value,String why) {
        checks++; if(!value) throw new AssertionError(why);
    }
    static void rejects(String value) {
        boolean rejected=false;
        try { EventReference.parse(value); }
        catch(IllegalArgumentException expected) { rejected=true; }
        check(rejected,"invalid reference accepted: "+value);
    }
    public static void main(String[] args) {
        EventReference plain=EventReference.parse("content://com.android.calendar/events/7");
        check(plain.id==7 && !plain.hasOccurrence && plain.begin==-1 && plain.end==-1,"plain event has no invented occurrence");
        EventReference legacy=EventReference.parse("content://com.android.calendar/events/7/EventTime/1795176000000/1795178700000");
        check(legacy.id==7 && legacy.hasOccurrence && legacy.begin==1795176000000L &&
              legacy.end==1795178700000L,"existing EventTime route retains both timestamps");
        check(EventReference.parse("content://com.android.calendar/events/0").id==0,"numeric zero follows provider URI grammar");
        for(String input:new String[]{null,"", "https://com.android.calendar/events/7",
            "content://other/events/7","content://com.android.calendar/events/7?x=1",
            "content://com.android.calendar/events/7#x","content://com.android.calendar/events/-1",
            "content://com.android.calendar/events/7/","content://com.android.calendar/events/%37",
            "content://com.android.calendar/events/7/EventTime/9/9",
            "content://com.android.calendar/events/7/EventTime/10/9",
            "content://com.android.calendar/events/7/EventTime/9/10/11",
            "content://com.android.calendar/events/7/Other/9/10",
            "content://com.android.calendar/events/9223372036854775808"}) rejects(input);
        System.out.println("EventReferenceTest: "+checks+" checks passed");
    }
}
