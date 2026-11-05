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
    private static void invalidCalendar(String receipt,String submitted) {
        try { ProviderReceipt.calendarId(receipt,submitted); throw new AssertionError("invalid calendar receipt accepted"); }
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
        String query="caller_is_syncadapter=true&account_name=Droidloom%20local%20calendars&account_type=LOCAL";
        String submitted="content://com.android.calendar/calendars?"+query;
        String receipt="content://com.android.calendar/calendars/1?"+query;
        // The actual provider returns its incoming collection URI with the ID appended,
        // retaining the query. The old generic validator must remain strict.
        try { ProviderReceipt.id(receipt,"calendars"); throw new AssertionError("generic query rule changed"); }
        catch(IllegalStateException stillStrict) { checks++; }
        check(ProviderReceipt.calendarId(receipt,submitted)==1);
        check(ProviderReceipt.calendarId("content://com.android.calendar/calendars/17?"+query,submitted)==17);
        for(String bad:new String[]{null,"",receipt+"#fragment",receipt+"&x=y",
            receipt+"&account_name=extra",receipt.replace("%20","+"),
            receipt.replace("account_type=LOCAL","account_type=other"),
            receipt.replace("calendars/1?","events/1?"),receipt.replace("com.android.calendar/","other/"),
            receipt.replace("calendars/1?","calendars/%31?"),receipt.replace("calendars/1?","calendars/-1?"),
            receipt.replace("calendars/1?","calendars/9223372036854775808?"),
            "content://com.android.calendar/calendars/1"}) invalidCalendar(bad,submitted);
        for(String bad:new String[]{null,"",submitted+"#fragment",submitted+"&x=y",
            submitted.replace("caller_is_syncadapter=true","caller_is_syncadapter=false"),
            submitted.replace("account_name=Droidloom%20local%20calendars","account_name="),
            submitted.replace("account_type=LOCAL","account_type=other"),
            submitted.replace("/calendars?","/events?"),submitted.replace("com.android.calendar/","other/")})
            invalidCalendar(receipt,bad);
        System.out.println("ProviderReceiptTest: "+checks+" checks passed");
    }
}
