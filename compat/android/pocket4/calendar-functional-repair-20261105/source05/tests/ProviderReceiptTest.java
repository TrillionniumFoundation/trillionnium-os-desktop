import com.android.calendar.event.ProviderReceipt;

public final class ProviderReceiptTest {
    private static int checks;
    private static void check(boolean condition) {
        checks++; if(!condition) throw new AssertionError("receipt classification");
    }
    private static void committedButInvalid(String uri) {
        // The production validator runs after applyBatch returned. Its exception must
        // never enter the editor's IllegalArgumentException (invalid input) branch.
        try { ProviderReceipt.id(uri,"events"); throw new AssertionError("invalid receipt accepted"); }
        catch(IllegalStateException outcomeUnknown) { checks++; }
    }
    public static void main(String[] args) {
        check(ProviderReceipt.id("content://com.android.calendar/events/9","events")==9);
        check(ProviderReceipt.id("content://com.android.calendar/calendars/1","calendars")==1);
        for(String value:new String[]{null,"", "content://com.android.calendar/events/not-a-number",
            "content://other/events/9","content://com.android.calendar/calendars/9",
            "content://com.android.calendar/events/-1","content://com.android.calendar/events/9?x=y",
            "content://com.android.calendar/events/9#fragment","content://com.android.calendar/events/9/10",
            "content://com.android.calendar/events/9223372036854775808"}) committedButInvalid(value);
        System.out.println("ProviderReceiptTest: "+checks+" checks passed");
    }
}
