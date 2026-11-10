import com.android.calendar.event.EventDraft;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneOffset;

public final class EventDraftTest {
    static int checks;
    static void check(boolean value,String message) {
        checks++; if(!value) throw new AssertionError(message);
    }
    static void fails(Runnable call,String message) {
        boolean failed=false;
        try { call.run(); } catch(IllegalArgumentException e) { failed=true; }
        check(failed,message);
    }
    static EventDraft draft(String begin,String end,String zone,boolean day) {
        EventDraft d=new EventDraft(); d.calendarId=1;
        d.setTimes(Instant.parse(begin).toEpochMilli(),Instant.parse(end).toEpochMilli(),zone,day);
        return d;
    }
    public static void main(String[] args) {
        EventDraft utc=draft("2026-11-13T12:00:00Z","2026-11-13T12:45:00Z","UTC",false);
        utc.validate();
        check(utc.duration().equals("PT2700S"),"45 minute duration");
        check(utc.beginMillis()==Instant.parse("2026-11-13T12:00:00Z").toEpochMilli(),"UTC roundtrip");
        EventDraft day=draft("2026-03-08T00:00:00Z","2026-03-09T00:00:00Z","America/Los_Angeles",true);
        day.validate();
        check(day.startDate.equals(day.endDate),"inclusive UI end for one all-day date");
        check(day.endMillis()-day.beginMillis()==86400000L,"all-day UTC ignores DST");
        check(day.providerTimezone().equals("UTC") && day.duration().equals("P1D"),"all-day storage contract");
        EventDraft spring=draft("2026-03-08T09:30:00Z","2026-03-08T10:30:00Z","America/Los_Angeles",false);
        check(spring.startTime.equals(LocalTime.of(1,30)) && spring.endTime.equals(LocalTime.of(3,30)),"DST wall time");
        check(spring.duration().equals("PT3600S"),"elapsed duration across spring transition");
        spring.startTime=LocalTime.of(2,30);
        fails(spring::beginMillis,"nonexistent local wall time must not be silently shifted");
        EventDraft fall=draft("2026-11-01T09:30:00Z","2026-11-01T10:30:00Z","America/Los_Angeles",false);
        check(fall.preferredStartOffset.equals(ZoneOffset.ofHours(-8)),"second ambiguous occurrence retained");
        check(fall.beginMillis()==Instant.parse("2026-11-01T09:30:00Z").toEpochMilli(),"fall-back occurrence roundtrip");
        utc.endTime=LocalTime.of(11,59); fails(utc::validate,"end before start");
        EventDraft original=draft("2026-11-13T12:00:00Z","2026-11-13T12:45:00Z","UTC",false);
        original.recurrence="FREQ=WEEKLY;BYDAY=MO,WE"; original.reminderMinutes=-1;
        EventDraft editing=original.copy();
        editing.chooseRecurrence("FREQ=DAILY",false,original);
        check(editing.recurrenceChanged && "FREQ=DAILY".equals(editing.recurrence),"custom to daily");
        editing.chooseRecurrence(null,true,original);
        check(!editing.recurrenceChanged && editing.recurrence.equals(original.recurrence),"unchanged restores original custom rule");
        editing.chooseReminder(15,false,original);
        check(editing.remindersChanged && editing.reminderMinutes==15,"multiple original reminders replaced only on selection");
        editing.chooseReminder(-1,true,original);
        check(!editing.remindersChanged && editing.reminderMinutes==original.reminderMinutes,"unchanged restores untouched reminders");
        editing.timingChanged=true; editing.chooseRecurrence(null,true,original);
        check(editing.timingChanged,"restoring recurrence must preserve independent timing edit");
        check(original.startDate.equals(LocalDate.of(2026,11,13)) && !original.recurrenceChanged &&
              !original.remindersChanged,"draft edits do not mutate original snapshot");
        System.out.println("EventDraftTest: "+checks+" checks passed");
    }
}
