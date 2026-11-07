/*
 * Copyright 2026 The Droidloom Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package com.android.calendar.alerts;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.ContentProviderOperation;
import android.content.ContentProviderResult;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.provider.CalendarContract;
import android.provider.CalendarContract.CalendarAlerts;
import android.provider.CalendarContract.Calendars;
import android.provider.CalendarContract.Events;
import android.provider.CalendarContract.Instances;

import com.android.calendar.event.ProviderReceipt;

import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/** Private authorization journal for user snoozes; never schedules ordinary Reminders. */
final class SnoozeJournal {
    private static final Object LOCK=new Object();
    private static final String PREFS="calendar_user_snoozes_v1";
    private static final String PREFIX="request.";
    private static final int MAX_RECORDS=20, MAX_DUE_WAKEUPS=8;
    private static final long SNOOZE_MILLIS=600_000L;
    private static final String[] EVENT_COLUMNS={Events._ID,Events.CALENDAR_ID,Events.TITLE,
        Events.EVENT_LOCATION,Events.DESCRIPTION,Events.DTSTART,Events.DTEND,Events.DURATION,
        Events.EVENT_TIMEZONE,Events.ALL_DAY,Events.RRULE,Events.RDATE,Events.EXRULE,Events.EXDATE,
        Events.ORIGINAL_ID,Events.STATUS,Events.DELETED,Events.HAS_ALARM};
    private static final String[] CALENDAR_COLUMNS={Calendars._ID,Calendars.ACCOUNT_NAME,
        Calendars.ACCOUNT_TYPE,Calendars.NAME,Calendars.OWNER_ACCOUNT,Calendars.VISIBLE};
    private SnoozeJournal() {}

    static final class Record {
        String nonce, fingerprint;
        long sourceId,event,begin,end,sourceAlarm,sourceCreated,created,until,targetId=-1;
        int sourceMinutes,phase=SnoozeState.REQUESTED,dueWakeups;
        JSONObject json() throws Exception {
            JSONObject j=new JSONObject();j.put("version",1);j.put("nonce",nonce);j.put("fingerprint",fingerprint);
            j.put("source",sourceId);j.put("event",event);j.put("begin",begin);j.put("end",end);
            j.put("sourceAlarm",sourceAlarm);j.put("sourceMinutes",sourceMinutes);j.put("sourceCreated",sourceCreated);
            j.put("created",created);j.put("until",until);j.put("phase",phase);j.put("target",targetId);
            j.put("dueWakeups",dueWakeups);return j;
        }
        static Record parse(String key,String value) throws Exception {
            if(value==null || value.length()>4096) throw new IllegalStateException("Invalid snooze journal.");
            JSONObject j=new JSONObject(value);Record r=new Record();
            require(j.getInt("version")==1,"Unknown snooze journal version.");
            r.nonce=j.getString("nonce");r.fingerprint=j.getString("fingerprint");
            r.sourceId=j.getLong("source");r.event=j.getLong("event");r.begin=j.getLong("begin");r.end=j.getLong("end");
            r.sourceAlarm=j.getLong("sourceAlarm");r.sourceMinutes=j.getInt("sourceMinutes");r.sourceCreated=j.getLong("sourceCreated");
            r.created=j.getLong("created");r.until=j.getLong("until");r.phase=j.getInt("phase");
            r.targetId=j.getLong("target");r.dueWakeups=j.getInt("dueWakeups");
            require(r.nonce.matches("[0-9a-f]{32}") && key.equals(PREFIX+r.nonce) &&
                r.fingerprint.matches("[0-9a-f]{64}") && r.sourceId>=0 && r.event>=0 &&
                r.begin>=0 && r.end>r.begin && r.sourceAlarm>=0 && r.sourceMinutes>=0 && r.sourceCreated>=0 &&
                r.created>0 && r.until>r.created && r.until-r.created==SNOOZE_MILLIS &&
                r.phase>=SnoozeState.REQUESTED && r.phase<=SnoozeState.CANCELLED &&
                r.targetId>=-1 && r.dueWakeups>=0 && r.dueWakeups<=MAX_DUE_WAKEUPS,
                "Invalid snooze journal identity.");
            require(r.phase!=SnoozeState.CONFIRMED || r.targetId>=0,"Missing confirmed snooze target.");
            return r;
        }
        boolean sourceMatches(RestoredAlerts.Alert a) {
            return a!=null && a.id==sourceId && a.event==event && a.begin==begin && a.end==end &&
                a.alarm==sourceAlarm && a.minutes==sourceMinutes && a.created==sourceCreated;
        }
        boolean targetMatches(RestoredAlerts.Alert a) {
            return a!=null && a.event==event && a.begin==begin && a.end==end &&
                a.alarm==until && a.minutes==0 && a.created==created;
        }
    }
    private static final class EventSnapshot {
        ContentValues event,calendar;String fingerprint;boolean valid;
    }
    private static final class Target {
        int count;RestoredAlerts.Alert row;
        int state() {return row==null?SnoozeState.ABSENT:row.state;}
    }
    private static void require(boolean value,String message) {
        if(!value)throw new IllegalStateException(message);
    }
    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences(PREFS,Context.MODE_PRIVATE);
    }
    private static Record read(Context context,String nonce) throws Exception {
        if(nonce==null || !nonce.matches("[0-9a-f]{32}"))return null;
        String value=preferences(context).getString(PREFIX+nonce,null);
        return value==null?null:Record.parse(PREFIX+nonce,value);
    }
    private static List<Record> records(Context context) throws Exception {
        ArrayList<Record> result=new ArrayList<>();
        for(Map.Entry<String,?> item:preferences(context).getAll().entrySet()) {
            require(item.getKey().startsWith(PREFIX) && item.getValue() instanceof String,"Unknown snooze journal entry.");
            result.add(Record.parse(item.getKey(),(String)item.getValue()));
            require(result.size()<=MAX_RECORDS,"Too many pending snoozes.");
        }
        return result;
    }
    private static void save(Context context,Record record) throws Exception {
        String value=record.json().toString();Record.parse(PREFIX+record.nonce,value);
        require(preferences(context).edit().putString(PREFIX+record.nonce,value).commit(),
            "Snooze state could not be saved.");
    }
    private static void forget(Context context,Record record) {
        // Removing the capability first makes a late/unknown AlarmManager cancel
        // harmless: its nonce can no longer authorize a provider operation.
        require(preferences(context).edit().remove(PREFIX+record.nonce).commit(),
            "Snooze cancellation could not be saved.");
        cancelWake(context,record);
    }
    static boolean contains(Context context,String nonce) {
        synchronized(LOCK) {
            try{return read(context,nonce)!=null;}
            catch(Exception invalid){return false;}
        }
    }
    private static String hex(byte[] bytes) {
        StringBuilder out=new StringBuilder(bytes.length*2);
        for(byte b:bytes)out.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
        return out.toString();
    }
    private static ContentValues row(Cursor c,String[] columns) {
        ContentValues v=new ContentValues();
        for(int i=0;i<columns.length;i++) {
            if(c.isNull(i))v.putNull(columns[i]);
            else if(c.getType(i)==Cursor.FIELD_TYPE_INTEGER)v.put(columns[i],c.getLong(i));
            else if(c.getType(i)==Cursor.FIELD_TYPE_STRING)v.put(columns[i],c.getString(i));
            else throw new IllegalStateException("Unsupported calendar value.");
        }
        return v;
    }
    private static void hashValues(DataOutputStream out,ContentValues values) throws Exception {
        for(String key:new TreeSet<>(values.keySet())) {
            out.writeUTF(key);Object value=values.get(key);
            if(value==null)out.writeByte(0);
            else if(value instanceof Number){out.writeByte(1);out.writeLong(((Number)value).longValue());}
            else {
                out.writeByte(2);byte[] b=value.toString().getBytes(StandardCharsets.UTF_8);
                require(b.length<=1_048_576,"Calendar value is too large.");out.writeInt(b.length);out.write(b);
            }
        }
    }
    private static EventSnapshot event(Context context,Record record) throws Exception {
        EventSnapshot result=new EventSnapshot();ContentResolver resolver=context.getContentResolver();
        try(Cursor c=resolver.query(Events.CONTENT_URI,EVENT_COLUMNS,Events._ID+"=?",
                new String[]{Long.toString(record.event)},null)) {
            require(c!=null,"Event information unavailable.");
            if(!c.moveToFirst())return result;
            require(c.getCount()==1,"Event identity is not unique.");result.event=row(c,EVENT_COLUMNS);
        }
        if(result.event.getAsInteger(Events.DELETED)!=0)return result;
        long calendar=result.event.getAsLong(Events.CALENDAR_ID);
        try(Cursor c=resolver.query(Calendars.CONTENT_URI,CALENDAR_COLUMNS,Calendars._ID+"=?",
                new String[]{Long.toString(calendar)},null)) {
            require(c!=null,"Calendar information unavailable.");
            if(!c.moveToFirst())return result;
            require(c.getCount()==1,"Calendar identity is not unique.");result.calendar=row(c,CALENDAR_COLUMNS);
        }
        if(result.calendar.getAsInteger(Calendars.VISIBLE)!=1)return result;
        Uri.Builder interval=Instances.CONTENT_URI.buildUpon();
        ContentUris.appendId(interval,record.begin);ContentUris.appendId(interval,Math.addExact(record.begin,1));
        try(Cursor c=resolver.query(interval.build(),new String[]{Instances.EVENT_ID,Instances.BEGIN,Instances.END},
                Instances.EVENT_ID+"=? AND "+Instances.BEGIN+"=? AND "+Instances.END+"=?",
                new String[]{Long.toString(record.event),Long.toString(record.begin),Long.toString(record.end)},null)) {
            require(c!=null,"Event occurrence unavailable.");if(!c.moveToFirst())return result;
            require(c.getCount()==1 && c.getLong(0)==record.event && c.getLong(1)==record.begin && c.getLong(2)==record.end,
                "Event occurrence is not unique.");
        }
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();DataOutputStream data=new DataOutputStream(bytes);
        hashValues(data,result.event);data.writeByte(127);hashValues(data,result.calendar);data.flush();
        result.fingerprint=hex(MessageDigest.getInstance("SHA-256").digest(bytes.toByteArray()));
        result.valid=true;return result;
    }
    private static String selection() {
        // This is the actual provider UNIQUE(alarmTime, begin, event_id) key.
        // A collision with other end/minutes/creation values is not our row.
        return CalendarAlerts.EVENT_ID+"=? AND "+CalendarAlerts.BEGIN+"=? AND "+CalendarAlerts.ALARM_TIME+"=?";
    }
    private static String[] arguments(Record r) {
        return new String[]{Long.toString(r.event),Long.toString(r.begin),Long.toString(r.until)};
    }
    private static Target target(Context context,Record record) {
        Target result=new Target();
        try(Cursor c=context.getContentResolver().query(CalendarAlerts.CONTENT_URI,RestoredAlerts.PROJECTION,
                selection(),arguments(record),CalendarAlerts._ID)) {
            require(c!=null,"Snooze state unavailable.");result.count=c.getCount();
            if(c.moveToFirst())result.row=new RestoredAlerts.Alert(c);
        }
        require(result.count<=1,"Conflicting snooze records.");
        require(result.count==0 || record.targetMatches(result.row),"Snooze target identity changed.");return result;
    }
    private static PendingIntent pending(Context context,Record record,int flags) {
        return PendingIntent.getBroadcast(context,0,RestoredAlerts.recoveryIntent(context,record.nonce),
            flags|PendingIntent.FLAG_IMMUTABLE);
    }
    private static void cancelWake(Context context,Record record) {
        PendingIntent intent=pending(context,record,PendingIntent.FLAG_NO_CREATE);
        if(intent!=null) {
            AlarmManager manager=context.getSystemService(AlarmManager.class);
            require(manager!=null,"Alarm service unavailable.");manager.cancel(intent);intent.cancel();
        }
    }
    private static void arm(Context context,Record record) throws Exception {
        long now=System.currentTimeMillis(),when=record.until;
        if(when<=now) {
            require(record.dueWakeups<MAX_DUE_WAKEUPS,"Snooze recovery needs attention.");
            record.dueWakeups++;save(context,record);when=Math.addExact(now,30_000L);
        }
        AlarmManager manager=context.getSystemService(AlarmManager.class);
        require(manager!=null,"Alarm service unavailable.");
        PendingIntent intent=pending(context,record,PendingIntent.FLAG_UPDATE_CURRENT);
        if(manager.canScheduleExactAlarms())manager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,when,intent);
        else manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,when,intent);
    }
    private static void insert(Context context,Record record,EventSnapshot event,
                               RestoredAlerts.Alert source,boolean first) throws Exception {
        ArrayList<ContentProviderOperation> ops=new ArrayList<>();
        ops.add(ContentProviderOperation.newAssertQuery(Events.CONTENT_URI)
            .withSelection(Events._ID+"=?",new String[]{Long.toString(record.event)})
            .withValues(event.event).withExpectedCount(1).build());
        ops.add(ContentProviderOperation.newAssertQuery(Calendars.CONTENT_URI)
            .withSelection(Calendars._ID+"=?",new String[]{event.calendar.getAsString(Calendars._ID)})
            .withValues(event.calendar).withExpectedCount(1).build());
        ops.add(ContentProviderOperation.newAssertQuery(CalendarAlerts.CONTENT_URI)
            .withSelection(CalendarAlerts._ID+"=?",new String[]{Long.toString(record.sourceId)})
            .withValues(source.identity()).withExpectedCount(1).build());
        ops.add(ContentProviderOperation.newAssertQuery(CalendarAlerts.CONTENT_URI)
            .withSelection(selection(),arguments(record)).withExpectedCount(0).build());
        ContentValues values=new ContentValues();values.put(CalendarAlerts.EVENT_ID,record.event);
        values.put(CalendarAlerts.BEGIN,record.begin);values.put(CalendarAlerts.END,record.end);
        values.put(CalendarAlerts.ALARM_TIME,record.until);values.put(CalendarAlerts.CREATION_TIME,record.created);
        values.put(CalendarAlerts.RECEIVED_TIME,0L);values.put(CalendarAlerts.NOTIFY_TIME,0L);
        values.put(CalendarAlerts.MINUTES,0);values.put(CalendarAlerts.STATE,CalendarAlerts.STATE_SCHEDULED);
        ops.add(ContentProviderOperation.newInsert(CalendarAlerts.CONTENT_URI).withValues(values).build());
        if(first)ops.add(ContentProviderOperation.newUpdate(CalendarAlerts.CONTENT_URI)
            .withSelection(CalendarAlerts._ID+"=?",new String[]{Long.toString(record.sourceId)})
            .withValue(CalendarAlerts.STATE,CalendarAlerts.STATE_DISMISSED).withExpectedCount(1).build());
        // Arm the nonce-bound wakeup before the batch. If the process ends during
        // reconstruction, the next delivery inspects the exact tuple before any
        // insert. The absent-row assertion and source/event CAS stay in one batch.
        arm(context,record);
        Exception reported=null;
        try {
            ContentProviderResult[] reply=context.getContentResolver().applyBatch(CalendarContract.AUTHORITY,ops);
            require(reply!=null && reply.length==ops.size() && reply[4]!=null && reply[4].uri!=null,
                "Snooze provider receipt is unknown.");
            ProviderReceipt.id(reply[4].uri.toString(),"calendar_alerts");
        } catch(Exception failure) {reported=failure;}
        RestoredAlerts.Alert after=RestoredAlerts.one(context,record.sourceId);Target desired=target(context,record);
        EventSnapshot current=event(context,record);
        if(record.sourceMatches(after) && after.state==CalendarAlerts.STATE_DISMISSED &&
           desired.count==1 && (desired.row.state==CalendarAlerts.STATE_SCHEDULED ||
           desired.row.state==CalendarAlerts.STATE_FIRED) && current.valid &&
           record.fingerprint.equals(current.fingerprint)) {
            record.phase=SnoozeState.CONFIRMED;record.targetId=desired.row.id;save(context,record);return;
        }
        // No automatic retry of this write. A later authenticated wakeup can
        // only adopt an exact row or rebuild an already CONFIRMED request.
        if(reported!=null)throw new IllegalStateException("Snooze change could not be confirmed.",reported);
        throw new IllegalStateException("Snooze state changed before confirmation.");
    }
    private static void cancelTarget(Context context,Record record,Target target) throws Exception {
        record.phase=SnoozeState.CANCELLED;
        if(target.count==1)record.targetId=target.row.id;
        save(context,record);
        if(target.count==1 && target.row.state!=CalendarAlerts.STATE_DISMISSED) {
            ArrayList<ContentProviderOperation> ops=new ArrayList<>();
            ops.add(ContentProviderOperation.newAssertQuery(CalendarAlerts.CONTENT_URI)
                .withSelection(CalendarAlerts._ID+"=?",new String[]{Long.toString(target.row.id)})
                .withValues(target.row.identity()).withExpectedCount(1).build());
            ops.add(ContentProviderOperation.newUpdate(CalendarAlerts.CONTENT_URI)
                .withSelection(CalendarAlerts._ID+"=?",new String[]{Long.toString(target.row.id)})
                .withValue(CalendarAlerts.STATE,CalendarAlerts.STATE_DISMISSED).withExpectedCount(1).build());
            Exception reported=null;
            try{context.getContentResolver().applyBatch(CalendarContract.AUTHORITY,ops);}
            catch(Exception failure){reported=failure;}
            Target after=target(context,record);
            if(after.count!=0 && after.row.state!=CalendarAlerts.STATE_DISMISSED)
                throw new IllegalStateException("Snooze cancellation is not confirmed.",reported);
            RestoredAlerts.manager(context).cancel(target.row.tag(),0);
        }
        forget(context,record);
    }
    private static void reconcile(Context context,Record record,boolean fresh) throws Exception {
        RestoredAlerts.Alert source=RestoredAlerts.one(context,record.sourceId);
        // A missing source cannot authorize reconstruction. We may cancel only
        // a previously confirmed target ID with its complete recorded identity.
        if(!record.sourceMatches(source)) {
            Target known=target(context,record);
            if(known.count==0) {forget(context,record);return;}
            if(record.targetId>=0 && known.row.id==record.targetId) {cancelTarget(context,record,known);return;}
            cancelWake(context,record);
            throw new IllegalStateException("Snooze source changed; the remaining target is not confirmed.");
        }
        EventSnapshot snapshot=event(context,record);Target desired=target(context,record);
        SnoozeState.Decision action=SnoozeState.decide(record.phase,snapshot.valid &&
            record.fingerprint.equals(snapshot.fingerprint),true,source.state,desired.count,desired.state(),fresh);
        switch(action) {
            case INITIAL_WRITE:insert(context,record,snapshot,source,true);break;
            case RESTORE:insert(context,record,snapshot,source,false);break;
            case ADOPT:
            case PUBLISH:
                record.phase=SnoozeState.CONFIRMED;record.targetId=desired.row.id;save(context,record);arm(context,record);break;
            case CANCEL_TARGET:cancelTarget(context,record,desired);break;
            case FORGET:forget(context,record);break;
            case NO_EFFECT:
                forget(context,record);throw new IllegalStateException("The original snooze did not complete; the original reminder remains.");
            case UNKNOWN:throw new IllegalStateException("Snooze outcome is unknown. No reminder was recreated.");
        }
    }
    static void request(Context context,RestoredAlerts.Alert source) throws Exception {
        synchronized(LOCK) {
            List<Record> existing=records(context);
            for(Record old:existing)if(old.sourceId==source.id) {reconcile(context,old,false);return;}
            require(source.state==CalendarAlerts.STATE_FIRED,"Only a fired reminder can be snoozed.");
            require(existing.size()<MAX_RECORDS,"Dismiss an existing snooze before adding another.");
            Record r=new Record();byte[] bytes=new byte[16];new SecureRandom().nextBytes(bytes);r.nonce=hex(bytes);
            r.sourceId=source.id;r.event=source.event;r.begin=source.begin;r.end=source.end;
            r.sourceAlarm=source.alarm;r.sourceMinutes=source.minutes;r.sourceCreated=source.created;r.created=System.currentTimeMillis();
            r.until=Math.addExact(r.created,SNOOZE_MILLIS);
            EventSnapshot e=event(context,r);require(e.valid,"This event occurrence is no longer available.");
            r.fingerprint=e.fingerprint;save(context,r);reconcile(context,r,true);
        }
    }
    static void recoverOne(Context context,String nonce) throws Exception {
        synchronized(LOCK) {Record r=read(context,nonce);if(r!=null)reconcile(context,r,false);}
    }
    static void recoverAll(Context context,boolean explicitAppRefresh) {
        synchronized(LOCK) {
            final List<Record> all;
            try{all=records(context);}catch(Exception failure){RestoredAlerts.reportFailure(context,failure);return;}
            for(Record r:all)try {
                if(explicitAppRefresh && r.dueWakeups>0){r.dueWakeups=0;save(context,r);}
                reconcile(context,r,false);
            } catch(Exception failure){RestoredAlerts.reportFailure(context,failure);}
        }
    }
    /** The journal survives FIRED until this exact row has an active notification. */
    static void settlePublished(Context context,Set<Long> published) {
        synchronized(LOCK) {
            try {
                for(Record r:records(context)) {
                    Target t=target(context,r);
                    if(t.count==1 && published.contains(t.row.id) && t.row.state==CalendarAlerts.STATE_FIRED &&
                       r.phase==SnoozeState.CONFIRMED && t.row.id==r.targetId) {
                        RestoredAlerts.Alert source=RestoredAlerts.one(context,r.sourceId);
                        EventSnapshot snapshot=event(context,r);
                        if(SnoozeState.canForgetPublished(r.phase,r.sourceMatches(source),
                           source==null?SnoozeState.ABSENT:source.state,snapshot.valid && r.fingerprint.equals(snapshot.fingerprint),
                           t.row.state,t.row.id==r.targetId,published.contains(t.row.id)))forget(context,r);
                        else reconcile(context,r,false);
                    }
                }
            } catch(Exception failure){RestoredAlerts.reportFailure(context,failure);}
        }
    }
    static boolean cancelled(Context context,RestoredAlerts.Alert alert) {
        synchronized(LOCK) {
            try {
                for(Record r:records(context))if(r.phase==SnoozeState.CANCELLED && r.targetId==alert.id &&
                    r.targetMatches(alert))return true;
            } catch(Exception failure){RestoredAlerts.reportFailure(context,failure);}
            return false;
        }
    }
}
