/*
 * Copyright 2026 The Droidloom Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package com.android.calendar.event;

import android.content.ContentProviderOperation;
import android.content.ContentProviderResult;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;
import android.provider.CalendarContract;
import android.provider.CalendarContract.Calendars;
import android.provider.CalendarContract.Events;
import android.provider.CalendarContract.Reminders;

import java.time.Duration;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

/** Public-provider persistence. No AccountManager account, sync request or raw DB write. */
public final class EventEditorStore {
    public static final String LOCAL_ACCOUNT="Droidloom local calendars";
    public static final String LOCAL_NAME_PREFIX="droidloom-local-";
    private static final String[] EVENT_COLUMNS = {
        Events._ID, Events.CALENDAR_ID, Events.TITLE, Events.EVENT_LOCATION, Events.DESCRIPTION,
        Events.DTSTART, Events.DTEND, Events.EVENT_TIMEZONE, Events.ALL_DAY, Events.RRULE,
        Events.RDATE, Events.EXRULE, Events.EXDATE, Events.DURATION, Events.ORIGINAL_ID
    };
    private static final String[] CALENDAR_COLUMNS = {
        Calendars._ID, Calendars.CALENDAR_DISPLAY_NAME, Calendars.ACCOUNT_NAME,
        Calendars.ACCOUNT_TYPE, Calendars.OWNER_ACCOUNT, Calendars.CALENDAR_ACCESS_LEVEL,
        Calendars.MAX_REMINDERS, Calendars.ALLOWED_REMINDERS
    };

    public static final class CalendarChoice {
        public final long id;
        public final String label;
        public final ContentValues identity;
        public final boolean alertReminderAllowed;
        public final boolean writable;
        CalendarChoice(Cursor c) {
            id=c.getLong(0); label=nonnull(c.getString(1));
            identity=new ContentValues();
            for (int i=0; i<CALENDAR_COLUMNS.length; i++) putColumn(identity,c,i,CALENDAR_COLUMNS[i]);
            int max=c.isNull(6) ? 0 : c.getInt(6);
            String methods=c.getString(7);
            boolean alert=false;
            if (methods!=null) for (String value:methods.split(","))
                if (value.trim().equals(Integer.toString(Reminders.METHOD_ALERT))) alert=true;
            alertReminderAllowed=max>0 && alert;
            writable=c.getInt(5)>=Calendars.CAL_ACCESS_CONTRIBUTOR;
        }
        @Override public String toString() {
            String account=identity.getAsString(Calendars.ACCOUNT_NAME);
            return label + (account==null || account.equals(label) ? "" : " ("+account+")");
        }
    }

    public static final class Loaded {
        public EventDraft draft;
        public ContentValues original;
        public List<CalendarChoice> calendars;
        public int originalReminderCount;
        public boolean customReminders;
        public final List<ContentValues> originalReminders = new ArrayList<>();
        public boolean recurring;
        public boolean exception;
        public boolean canWrite;
    }

    private final ContentResolver resolver;
    public EventEditorStore(ContentResolver resolver) { this.resolver=resolver; }
    private static String nonnull(String value) { return value==null ? "" : value; }
    private static void require(boolean value, String message) {
        if (!value) throw new IllegalStateException(message);
    }
    private static void putColumn(ContentValues values,Cursor c,int column,String name) {
        if (c.isNull(column)) values.putNull(name);
        else if (c.getType(column)==Cursor.FIELD_TYPE_INTEGER) values.put(name,c.getLong(column));
        else values.put(name,c.getString(column));
    }

    public static long eventId(Uri uri) {
        if (uri==null || !"content".equals(uri.getScheme()) ||
            !CalendarContract.AUTHORITY.equals(uri.getAuthority()) || uri.getQuery()!=null ||
            uri.getFragment()!=null || uri.getPathSegments().size()!=2 ||
            !"events".equals(uri.getPathSegments().get(0)))
            throw new IllegalArgumentException("This is not a Calendar event.");
        long id=ContentUris.parseId(uri);
        if (id<0) throw new IllegalArgumentException("The event ID is invalid.");
        return id;
    }

    private List<CalendarChoice> writableCalendars(long existingCalendar) {
        ArrayList<CalendarChoice> values=new ArrayList<>();
        String where=Calendars.CALENDAR_ACCESS_LEVEL+">=?";
        String[] args={Integer.toString(Calendars.CAL_ACCESS_CONTRIBUTOR)};
        // Include a hidden but writable calendar for an existing event.
        if (existingCalendar>=0) {
            where=Calendars._ID+"=?";
            args=new String[]{Long.toString(existingCalendar)};
        } else where+=" AND "+Calendars.VISIBLE+"=1";
        try (Cursor c=resolver.query(Calendars.CONTENT_URI,CALENDAR_COLUMNS,where,args,
                                    Calendars.CALENDAR_DISPLAY_NAME+" COLLATE NOCASE,"+Calendars._ID)) {
            require(c!=null,"Calendar information is temporarily unavailable.");
            while (c.moveToNext()) values.add(new CalendarChoice(c));
        }
        return Collections.unmodifiableList(values);
    }

    public Loaded load(long eventId,long requestedCalendar,long begin,long end,boolean allDay,
                       String title,String location,String description) {
        Loaded loaded=new Loaded(); EventDraft d=new EventDraft(); d.id=eventId;
        if (eventId>=0) {
            try (Cursor c=resolver.query(Events.CONTENT_URI,EVENT_COLUMNS,Events._ID+"=?",
                                        new String[]{Long.toString(eventId)},null)) {
                require(c!=null && c.moveToFirst() && c.getCount()==1,"This event is no longer available.");
                loaded.original=new ContentValues();
                for(int i=0;i<EVENT_COLUMNS.length;i++) putColumn(loaded.original,c,i,EVENT_COLUMNS[i]);
                d.calendarId=c.getLong(1); d.title=nonnull(c.getString(2));
                d.location=nonnull(c.getString(3)); d.description=nonnull(c.getString(4));
                long start=c.getLong(5); String duration=c.getString(13);
                long finish;
                if (!c.isNull(6)) finish=c.getLong(6);
                else {
                    require(duration!=null,"The event has no valid end time.");
                    // CalendarContract uses RFC 2445 day or time durations, not months.
                    String normalized=duration.startsWith("P") && duration.endsWith("W")
                        ? "P"+Math.multiplyExact(Long.parseLong(duration.substring(1,duration.length()-1)),7)+"D"
                        : duration;
                    finish=Math.addExact(start,Duration.parse(normalized).toMillis());
                }
                String timezone=c.getString(7);
                if (timezone==null || timezone.isEmpty()) timezone=ZoneId.systemDefault().getId();
                d.setTimes(start,finish,timezone,c.getInt(8)!=0);
                d.recurrence=c.getString(9);
                loaded.recurring=(d.recurrence!=null && !d.recurrence.isEmpty()) ||
                    (c.getString(10)!=null && !c.getString(10).isEmpty());
                loaded.exception=!c.isNull(14);
            }
            String[] reminderColumns={Reminders._ID,Reminders.EVENT_ID,Reminders.MINUTES,Reminders.METHOD};
            try (Cursor c=resolver.query(Reminders.CONTENT_URI,
                    reminderColumns,Reminders.EVENT_ID+"=?",
                    new String[]{Long.toString(eventId)},Reminders._ID)) {
                require(c!=null,"Reminder information is temporarily unavailable.");
                loaded.originalReminderCount=c.getCount();
                loaded.customReminders=c.getCount()>1;
                while(c.moveToNext()) {
                    ContentValues row=new ContentValues();
                    for(int i=0;i<reminderColumns.length;i++) putColumn(row,c,i,reminderColumns[i]);
                    loaded.originalReminders.add(row);
                    if(c.getInt(3)!=Reminders.METHOD_ALERT) loaded.customReminders=true;
                    if(c.getCount()==1 && c.getInt(3)==Reminders.METHOD_ALERT)
                        d.reminderMinutes=c.getInt(2);
                }
            }
        } else {
            d.title=nonnull(title); d.location=nonnull(location); d.description=nonnull(description);
            d.setTimes(begin,end,ZoneId.systemDefault().getId(),allDay);
        }
        loaded.calendars=writableCalendars(d.calendarId);
        require(eventId<0 || !loaded.calendars.isEmpty(),"This event's calendar is no longer available.");
        if (eventId<0 && !loaded.calendars.isEmpty()) {
            d.calendarId=loaded.calendars.get(0).id;
            for (CalendarChoice value:loaded.calendars)
                if (value.id==requestedCalendar) d.calendarId=value.id;
        }
        loaded.draft=d;
        for(CalendarChoice choice:loaded.calendars)
            if(choice.id==d.calendarId) loaded.canWrite=choice.writable;
        return loaded;
    }

    /** Called only after the user confirms creation in the empty-calendar screen. */
    public long createLocalCalendar(String displayName) throws Exception {
        String label=displayName==null?"":displayName.trim();
        if(label.isEmpty() || label.length()>255)
            throw new IllegalArgumentException("Enter a calendar name of 1 to 255 characters.");
        String name=LOCAL_NAME_PREFIX+UUID.randomUUID().toString();
        Uri local=Calendars.CONTENT_URI.buildUpon()
            .appendQueryParameter(CalendarContract.CALLER_IS_SYNCADAPTER,"true")
            .appendQueryParameter(Calendars.ACCOUNT_NAME,LOCAL_ACCOUNT)
            .appendQueryParameter(Calendars.ACCOUNT_TYPE,CalendarContract.ACCOUNT_TYPE_LOCAL).build();
        ContentValues values=new ContentValues();
        values.put(Calendars.ACCOUNT_NAME,LOCAL_ACCOUNT);
        values.put(Calendars.ACCOUNT_TYPE,CalendarContract.ACCOUNT_TYPE_LOCAL);
        values.put(Calendars.NAME,name); values.put(Calendars.CALENDAR_DISPLAY_NAME,label);
        values.put(Calendars.OWNER_ACCOUNT,LOCAL_ACCOUNT);
        values.put(Calendars.CALENDAR_ACCESS_LEVEL,Calendars.CAL_ACCESS_OWNER);
        values.put(Calendars.CALENDAR_COLOR,0xff1976d2);
        values.put(Calendars.CALENDAR_TIME_ZONE,ZoneId.systemDefault().getId());
        values.put(Calendars.VISIBLE,1); values.put(Calendars.SYNC_EVENTS,1);
        values.put(Calendars.MAX_REMINDERS,5); values.put(Calendars.ALLOWED_REMINDERS,"1");
        values.put(Calendars.ALLOWED_AVAILABILITY,"0,1,2");
        values.put(Calendars.ALLOWED_ATTENDEE_TYPES,"0,1,2");
        String scope=Calendars.ACCOUNT_NAME+"=? AND "+Calendars.ACCOUNT_TYPE+"=? AND "+Calendars.NAME+"=?";
        String[] args={LOCAL_ACCOUNT,CalendarContract.ACCOUNT_TYPE_LOCAL,name};
        ArrayList<ContentProviderOperation> ops=new ArrayList<>();
        ops.add(ContentProviderOperation.newAssertQuery(local).withSelection(scope,args)
            .withExpectedCount(0).build());
        ops.add(ContentProviderOperation.newInsert(local).withValues(values).build());
        ContentProviderResult[] results=resolver.applyBatch(CalendarContract.AUTHORITY,ops);
        require(results.length==2 && results[1].uri!=null,"The new calendar could not be confirmed.");
        long id=ProviderReceipt.id(results[1].uri.toString(),"calendars");
        require(id>=0,"The provider returned an invalid calendar ID.");
        try(Cursor c=resolver.query(Calendars.CONTENT_URI,
                new String[]{Calendars._ID,Calendars.CALENDAR_DISPLAY_NAME,Calendars.OWNER_ACCOUNT},
                Calendars._ID+"=? AND "+scope,
                new String[]{Long.toString(id),args[0],args[1],args[2]},null)) {
            require(c!=null && c.moveToFirst() && c.getCount()==1 &&
                label.equals(c.getString(1)) && LOCAL_ACCOUNT.equals(c.getString(2)),
                "The new calendar could not be confirmed. Check the calendar list before trying again.");
        } catch(RuntimeException failure) {
            throw new IllegalStateException("Calendar creation may have completed. Check the calendar list before trying again.",failure);
        }
        return id;
    }

    private CalendarChoice calendar(Loaded loaded,EventDraft d) {
        for(CalendarChoice c:loaded.calendars) if(c.id==d.calendarId) return c;
        throw new IllegalArgumentException("Choose a writable calendar.");
    }

    private ArrayList<ContentProviderOperation> guards(Loaded loaded,EventDraft d) {
        CalendarChoice choice=calendar(loaded,d);
        require(choice.writable,"This calendar is read-only.");
        ArrayList<ContentProviderOperation> ops=new ArrayList<>();
        ops.add(ContentProviderOperation.newAssertQuery(Calendars.CONTENT_URI)
            .withSelection(Calendars._ID+"=?",new String[]{Long.toString(choice.id)})
            .withValues(new ContentValues(choice.identity)).withExpectedCount(1).build());
        if(d.id>=0) {
            require(loaded.original!=null && loaded.original.getAsLong(Events._ID)==d.id,
                    "Reload this event before editing it.");
            ops.add(ContentProviderOperation.newAssertQuery(Events.CONTENT_URI)
                .withSelection(Events._ID+"=?",new String[]{Long.toString(d.id)})
                .withValues(new ContentValues(loaded.original)).withExpectedCount(1).build());
        }
        return ops;
    }

    public Uri save(Loaded loaded,EventDraft d) throws Exception {
        d.validate(); CalendarChoice choice=calendar(loaded,d);
        require(!d.remindersChanged || d.reminderMinutes<0 || choice.alertReminderAllowed,
                "This calendar does not allow an alert reminder.");
        require(!(loaded.exception && d.recurrenceChanged),
                "Change the repeating series from its original event.");
        ArrayList<ContentProviderOperation> ops=guards(loaded,d);
        if(d.id>=0 && d.remindersChanged) {
            ops.add(ContentProviderOperation.newAssertQuery(Reminders.CONTENT_URI)
                .withSelection(Reminders.EVENT_ID+"=?",new String[]{Long.toString(d.id)})
                .withExpectedCount(loaded.originalReminderCount).build());
            for(ContentValues row:loaded.originalReminders) {
                ops.add(ContentProviderOperation.newAssertQuery(Reminders.CONTENT_URI)
                    .withSelection(Reminders._ID+"=?",new String[]{row.getAsString(Reminders._ID)})
                    .withValues(new ContentValues(row)).withExpectedCount(1).build());
            }
        }
        ContentValues values=new ContentValues();
        values.put(Events.TITLE,d.title); values.put(Events.EVENT_LOCATION,d.location);
        values.put(Events.DESCRIPTION,d.description);
        if(d.id<0) {
            values.put(Events.CALENDAR_ID,d.calendarId); values.put(Events.STATUS,Events.STATUS_CONFIRMED);
            values.put(Events.AVAILABILITY,Events.AVAILABILITY_BUSY);
        }
        if(d.id<0 || d.timingChanged || d.recurrenceChanged) {
            values.put(Events.DTSTART,d.beginMillis()); values.put(Events.ALL_DAY,d.allDay?1:0);
            values.put(Events.EVENT_TIMEZONE,d.providerTimezone());
            boolean repeats=(d.recurrence!=null && !d.recurrence.isEmpty()) ||
                (!d.recurrenceChanged && loaded.original!=null &&
                 loaded.original.getAsString(Events.RDATE)!=null &&
                 !loaded.original.getAsString(Events.RDATE).isEmpty());
            if(repeats) { values.putNull(Events.DTEND); values.put(Events.DURATION,d.duration()); }
            else { values.put(Events.DTEND,d.endMillis()); values.putNull(Events.DURATION); }
        }
        if(d.id<0 || d.recurrenceChanged) {
            values.put(Events.RRULE,d.recurrence);
            if(d.recurrenceChanged) {
                values.putNull(Events.RDATE); values.putNull(Events.EXRULE); values.putNull(Events.EXDATE);
            }
        }
        if(d.id<0 || d.remindersChanged) values.put(Events.HAS_ALARM,d.reminderMinutes>=0?1:0);
        int writeIndex=ops.size();
        if(d.id<0) ops.add(ContentProviderOperation.newInsert(Events.CONTENT_URI).withValues(values).build());
        else ops.add(ContentProviderOperation.newUpdate(Events.CONTENT_URI)
            .withSelection(Events._ID+"=?",new String[]{Long.toString(d.id)})
            .withValues(values).withExpectedCount(1).build());
        if(d.id>=0 && d.remindersChanged) ops.add(ContentProviderOperation.newDelete(Reminders.CONTENT_URI)
            .withSelection(Reminders.EVENT_ID+"=?",new String[]{Long.toString(d.id)}).build());
        if((d.id<0 || d.remindersChanged) && d.reminderMinutes>=0) {
            ContentProviderOperation.Builder reminder=ContentProviderOperation.newInsert(Reminders.CONTENT_URI)
                .withValue(Reminders.MINUTES,d.reminderMinutes).withValue(Reminders.METHOD,Reminders.METHOD_ALERT);
            if(d.id<0) reminder.withValueBackReference(Reminders.EVENT_ID,writeIndex);
            else reminder.withValue(Reminders.EVENT_ID,d.id);
            ops.add(reminder.build());
        }
        ContentProviderResult[] result=resolver.applyBatch(CalendarContract.AUTHORITY,ops);
        require(result.length==ops.size(),"The provider returned an incomplete save result.");
        Uri uri=d.id<0 ? result[writeIndex].uri : ContentUris.withAppendedId(Events.CONTENT_URI,d.id);
        require(uri!=null,"The provider did not return the saved event.");
        ProviderReceipt.id(uri.toString(),"events"); return uri;
    }

    public void delete(Loaded loaded) throws Exception {
        EventDraft d=loaded.draft;
        require(d.id>=0,"There is no saved event to delete.");
        ArrayList<ContentProviderOperation> ops=guards(loaded,d);
        ops.add(ContentProviderOperation.newDelete(Events.CONTENT_URI)
            .withSelection(Events._ID+"=?",new String[]{Long.toString(d.id)})
            .withExpectedCount(1).build());
        ContentProviderResult[] result=resolver.applyBatch(CalendarContract.AUTHORITY,ops);
        require(result.length==ops.size() && Integer.valueOf(1).equals(result[result.length-1].count),
                "The provider did not confirm the event deletion.");
    }
}
