/*
 * Copyright 2026 The Droidloom Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package com.android.calendar.alerts;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.ContentProviderOperation;
import android.content.ContentProviderResult;
import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.net.Uri;
import android.provider.CalendarContract;
import android.provider.CalendarContract.CalendarAlerts;
import android.provider.CalendarContract.Events;
import android.service.notification.StatusBarNotification;
import android.util.Base64;
import android.util.Log;

import com.android.calendar.event.ProviderReceipt;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.text.DateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Standard notification extras and real immutable actions for the installed host bridge. */
public final class RestoredAlerts {
    private static final String PACKAGE="com.android.calendar";
    private static final String RECEIVER=PACKAGE+".alerts.AlertReceiver";
    private static final String CHANNEL="calendar-events-restored-v1";
    private static final String SNOOZE=PACKAGE+".restored.SNOOZE";
    private static final String DISMISS=PACKAGE+".restored.DISMISS";
    private static final String TOKEN="calendar_action_token";
    private static final String ROW_ID="calendar_alert_id";
    private static final String PREFS="calendar_restored_alert_actions";
    private static final String TAG="CalendarAlerts";
    private static final int MAX_VISIBLE=20;
    private static final long SNOOZE_MILLIS=10*60_000L;
    private static final ExecutorService WORK=Executors.newSingleThreadExecutor();
    private static final String[] PROJECTION={
        CalendarAlerts._ID,CalendarAlerts.EVENT_ID,CalendarAlerts.STATE,CalendarAlerts.BEGIN,
        CalendarAlerts.END,CalendarAlerts.ALARM_TIME,CalendarAlerts.MINUTES,
        CalendarAlerts.TITLE,CalendarAlerts.EVENT_LOCATION,CalendarAlerts.ALL_DAY
    };
    private RestoredAlerts() {}

    private static final class Alert {
        final long id,event,begin,end,alarm;
        final int state,minutes;
        final String title,location;
        final boolean allDay;
        Alert(Cursor c) {
            id=c.getLong(0); event=c.getLong(1); state=c.getInt(2); begin=c.getLong(3);
            end=c.getLong(4); alarm=c.getLong(5); minutes=c.getInt(6);
            title=c.isNull(7)?"":c.getString(7); location=c.isNull(8)?"":c.getString(8);
            allDay=c.getInt(9)!=0;
        }
        String tag() { return "calendar-alert-"+id; }
        ContentValues identity() {
            ContentValues v=new ContentValues();
            v.put(CalendarAlerts._ID,id); v.put(CalendarAlerts.EVENT_ID,event);
            v.put(CalendarAlerts.BEGIN,begin); v.put(CalendarAlerts.END,end);
            v.put(CalendarAlerts.ALARM_TIME,alarm); v.put(CalendarAlerts.STATE,state);
            return v;
        }
    }

    private static String token(Context context) {
        synchronized(RestoredAlerts.class) {
            SharedPreferences preferences=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE);
            String value=preferences.getString(TOKEN,null);
            if(value==null) {
                byte[] bytes=new byte[32]; new SecureRandom().nextBytes(bytes);
                value=Base64.encodeToString(bytes,Base64.NO_WRAP);
                if(!preferences.edit().putString(TOKEN,value).commit())
                    throw new IllegalStateException("Notification action identity could not be saved.");
            }
            return value;
        }
    }
    private static boolean authenticated(Context context,Intent intent) {
        String supplied=intent.getStringExtra(TOKEN);
        String expected=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString(TOKEN,null);
        return supplied!=null && expected!=null && MessageDigest.isEqual(
            supplied.getBytes(StandardCharsets.UTF_8),expected.getBytes(StandardCharsets.UTF_8));
    }
    private static boolean systemReminder(String action) {
        return CalendarContract.ACTION_EVENT_REMINDER.equals(action) ||
            Intent.ACTION_BOOT_COMPLETED.equals(action) || Intent.ACTION_TIME_CHANGED.equals(action) ||
            Intent.ACTION_TIMEZONE_CHANGED.equals(action) || Intent.ACTION_LOCALE_CHANGED.equals(action) ||
            Intent.ACTION_PROVIDER_CHANGED.equals(action);
    }

    /** Runs from the existing exported receiver; private actions require an unguessable app token. */
    public static void onReceive(BroadcastReceiver receiver,Context context,Intent incoming) {
        if(incoming==null) return;
        final Intent intent=new Intent(incoming); String action=intent.getAction();
        if(!(systemReminder(action) ||
             ((SNOOZE.equals(action)||DISMISS.equals(action))&&authenticated(context,intent))))
            return;
        final Context app=context.getApplicationContext();
        final BroadcastReceiver.PendingResult pending=receiver.goAsync();
        WORK.execute(() -> {
            try { handle(app,intent); }
            catch(Exception failure) { reportFailure(app,failure); }
            finally { pending.finish(); }
        });
    }

    /** Compatibility with the existing non-exported AlertService. No sticky redelivery loop. */
    public static int onServiceStart(Service service,Intent incoming,int startId) {
        final Intent intent=incoming==null?null:new Intent(incoming);
        final Context app=service.getApplicationContext();
        WORK.execute(() -> {
            try {
                if(intent!=null && systemReminder(intent.getAction())) handle(app,intent);
                else publishDue(app);
            } catch(Exception failure) { reportFailure(app,failure); }
            finally { service.stopSelfResult(startId); }
        });
        return Service.START_NOT_STICKY;
    }

    /** Reconcile already-due rows on startup/save. Provider owns ordinary reminder scheduling. */
    public static void refresh(Context context) {
        final Context app=context.getApplicationContext();
        WORK.execute(() -> {
            try { publishDue(app); }
            catch(Exception failure) { reportFailure(app,failure); }
        });
    }

    /** The event's immutable notification PI carries the private token; arbitrary VIEW intents do not. */
    public static void acknowledgeOpen(Context context,Intent incoming) {
        if(incoming==null || !authenticated(context,incoming)) return;
        final Intent intent=new Intent(incoming);
        final Context app=context.getApplicationContext();
        WORK.execute(() -> {
            try {
                Alert row=one(app,intent.getLongExtra(ROW_ID,-1));
                if(row!=null && row.state==CalendarAlerts.STATE_FIRED && intent.getData()!=null &&
                   ContentUris.withAppendedId(Events.CONTENT_URI,row.event).equals(intent.getData()) &&
                   intent.getLongExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME,-1)==row.begin &&
                   intent.getLongExtra(CalendarContract.EXTRA_EVENT_END_TIME,-1)==row.end) dismiss(app,row);
                publishDue(app);
            } catch(Exception failure) { reportFailure(app,failure); }
        });
    }

    private static void handle(Context context,Intent intent) throws Exception {
        String action=intent.getAction();
        if(SNOOZE.equals(action) || DISMISS.equals(action)) {
            long id=intent.getLongExtra(ROW_ID,-1);
            Alert alert=one(context,id);
            if(alert!=null && alert.state==CalendarAlerts.STATE_FIRED) {
                if(SNOOZE.equals(action)) snooze(context,alert); else dismiss(context,alert);
            } else if(id>=0) manager(context).cancel("calendar-alert-"+id,0);
        }
        publishDue(context);
    }

    private static NotificationManager manager(Context context) {
        NotificationManager manager=context.getSystemService(NotificationManager.class);
        if(manager==null) throw new IllegalStateException("Notification service unavailable.");
        return manager;
    }
    private static void channel(Context context) {
        NotificationChannel channel=new NotificationChannel(CHANNEL,"Calendar reminders",NotificationManager.IMPORTANCE_HIGH);
        channel.setDescription("Reminders for Calendar events");
        channel.enableVibration(true);
        channel.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),
            new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION_EVENT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build());
        manager(context).createNotificationChannel(channel);
    }
    private static Alert one(Context context,long id) {
        if(id<0) return null;
        try(Cursor c=context.getContentResolver().query(CalendarAlerts.CONTENT_URI,PROJECTION,
                CalendarAlerts._ID+"=?",new String[]{Long.toString(id)},null)) {
            if(c==null) throw new IllegalStateException("Calendar alerts unavailable.");
            return c.moveToFirst()?new Alert(c):null;
        }
    }
    private static final class DueBatch {
        final List<Alert> alerts=new ArrayList<>();
        int count;
    }
    private static DueBatch due(Context context) {
        DueBatch batch=new DueBatch();
        String selection=CalendarAlerts.STATE+"=? AND "+CalendarAlerts.ALARM_TIME+"<=?";
        try(Cursor c=context.getContentResolver().query(CalendarAlerts.CONTENT_URI,PROJECTION,selection,
                new String[]{Integer.toString(CalendarAlerts.STATE_FIRED),Long.toString(System.currentTimeMillis())},
                CalendarAlerts.ALARM_TIME+" DESC,"+CalendarAlerts._ID+" DESC")) {
            if(c==null) throw new IllegalStateException("Calendar alerts unavailable.");
            batch.count=c.getCount();
            while(c.moveToNext() && batch.alerts.size()<MAX_VISIBLE) batch.alerts.add(new Alert(c));
        }
        return batch;
    }

    private static void publishDue(Context context) throws Exception {
        channel(context);
        ContentValues fired=new ContentValues();
        fired.put(CalendarAlerts.STATE,CalendarAlerts.STATE_FIRED);
        fired.put(CalendarAlerts.RECEIVED_TIME,System.currentTimeMillis());
        // Claim every due scheduled row in one SQL update. Older reminders remain
        // FIRED in the provider and are promoted as visible reminders are dismissed;
        // a notification cap must never leave overdue scheduled rows in a wakeup loop.
        context.getContentResolver().update(CalendarAlerts.CONTENT_URI,fired,
            CalendarAlerts.STATE+"=? AND "+CalendarAlerts.ALARM_TIME+"<=?",
            new String[]{Integer.toString(CalendarAlerts.STATE_SCHEDULED),Long.toString(System.currentTimeMillis())});
        DueBatch batch=due(context);
        Set<String> visible=new HashSet<>();
        for(Alert alert:batch.alerts) {
            visible.add(alert.tag());
            Notification notification=notification(context,alert);
            manager(context).notify(alert.tag(),0,notification);
            // A concurrent dismiss must not leave a stale notification visible.
            Alert after=one(context,alert.id);
            if(after==null || after.state!=CalendarAlerts.STATE_FIRED) manager(context).cancel(alert.tag(),0);
        }
        for(StatusBarNotification active:manager(context).getActiveNotifications()) {
            String tag=active.getTag();
            if(tag!=null && tag.startsWith("calendar-alert-") && !visible.contains(tag))
                manager(context).cancel(tag,active.getId());
        }
        if(batch.count>MAX_VISIBLE) {
            Intent open=new Intent(Intent.ACTION_MAIN).setClassName(PACKAGE,PACKAGE+".AllInOneActivity")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            PendingIntent content=PendingIntent.getActivity(context,2,open,
                PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
            manager(context).notify("calendar-reminder-overflow",0,new Notification.Builder(context,CHANNEL)
                .setSmallIcon(android.R.drawable.ic_menu_my_calendar)
                .setContentTitle(batch.count+" Calendar reminders")
                .setContentText("More reminders will appear as you open or dismiss the current reminders.")
                .setContentIntent(content).setOnlyAlertOnce(true).setAutoCancel(true).build());
        } else manager(context).cancel("calendar-reminder-overflow",0);
    }

    private static PendingIntent action(Context context,String action,long id) {
        Intent intent=new Intent(action).setClassName(PACKAGE,RECEIVER);
        intent.setData(CalendarAlerts.CONTENT_URI.buildUpon().appendPath(Long.toString(id)).appendPath(action).build());
        intent.putExtra(ROW_ID,id); intent.putExtra(TOKEN,token(context));
        intent.addFlags(Intent.FLAG_RECEIVER_FOREGROUND);
        return PendingIntent.getBroadcast(context,0,intent,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
    }
    private static Notification notification(Context context,Alert alert) {
        String title=alert.title.isEmpty()?"(No title)":alert.title;
        DateFormat format=alert.allDay?DateFormat.getDateInstance(DateFormat.MEDIUM):
            DateFormat.getDateTimeInstance(DateFormat.MEDIUM,DateFormat.SHORT);
        if(alert.allDay) format.setTimeZone(TimeZone.getTimeZone("UTC"));
        String body=format.format(new Date(alert.begin));
        if(!alert.location.isEmpty()) body+=" · "+alert.location;
        Intent open=new Intent(Intent.ACTION_VIEW,ContentUris.withAppendedId(Events.CONTENT_URI,alert.event));
        open.setClassName(PACKAGE,PACKAGE+".EventInfoActivity");
        open.putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME,alert.begin);
        open.putExtra(CalendarContract.EXTRA_EVENT_END_TIME,alert.end);
        open.putExtra(ROW_ID,alert.id); open.putExtra(TOKEN,token(context));
        open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent content=PendingIntent.getActivity(context,(int)(alert.id^(alert.id>>>32)),open,
            PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(context,CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_my_calendar)
            .setContentTitle(title).setContentText(body)
            .setStyle(new Notification.BigTextStyle().bigText(body))
            .setCategory(Notification.CATEGORY_EVENT).setVisibility(Notification.VISIBILITY_PRIVATE)
            .setWhen(alert.begin).setShowWhen(true).setOnlyAlertOnce(true).setAutoCancel(true)
            .setContentIntent(content).setDeleteIntent(action(context,DISMISS,alert.id))
            .addAction(new Notification.Action.Builder(
                android.R.drawable.ic_lock_idle_alarm,"Snooze 10 min",action(context,SNOOZE,alert.id)).build())
            .addAction(new Notification.Action.Builder(
                android.R.drawable.ic_menu_close_clear_cancel,"Dismiss",action(context,DISMISS,alert.id)).build())
            .build();
    }

    private static ArrayList<ContentProviderOperation> assertion(Alert alert) {
        ArrayList<ContentProviderOperation> ops=new ArrayList<>();
        ops.add(ContentProviderOperation.newAssertQuery(CalendarAlerts.CONTENT_URI)
            .withSelection(CalendarAlerts._ID+"=?",new String[]{Long.toString(alert.id)})
            .withValues(alert.identity()).withExpectedCount(1).build());
        return ops;
    }
    private static void dismiss(Context context,Alert alert) throws Exception {
        ArrayList<ContentProviderOperation> ops=assertion(alert);
        ops.add(ContentProviderOperation.newUpdate(CalendarAlerts.CONTENT_URI)
            .withSelection(CalendarAlerts._ID+"=?",new String[]{Long.toString(alert.id)})
            .withValue(CalendarAlerts.STATE,CalendarAlerts.STATE_DISMISSED).withExpectedCount(1).build());
        context.getContentResolver().applyBatch(CalendarContract.AUTHORITY,ops);
        manager(context).cancel(alert.tag(),0);
    }
    private static void snooze(Context context,Alert alert) throws Exception {
        if(alert.state!=CalendarAlerts.STATE_FIRED) return;
        long now=System.currentTimeMillis(),when=Math.addExact(now,SNOOZE_MILLIS);
        ContentValues next=new ContentValues();
        next.put(CalendarAlerts.EVENT_ID,alert.event); next.put(CalendarAlerts.BEGIN,alert.begin);
        next.put(CalendarAlerts.END,alert.end); next.put(CalendarAlerts.ALARM_TIME,when);
        next.put(CalendarAlerts.CREATION_TIME,now); next.put(CalendarAlerts.RECEIVED_TIME,0L);
        next.put(CalendarAlerts.NOTIFY_TIME,0L); next.put(CalendarAlerts.MINUTES,0);
        next.put(CalendarAlerts.STATE,CalendarAlerts.STATE_SCHEDULED);
        ArrayList<ContentProviderOperation> ops=assertion(alert);
        ops.add(ContentProviderOperation.newInsert(CalendarAlerts.CONTENT_URI).withValues(next).build());
        ops.add(ContentProviderOperation.newUpdate(CalendarAlerts.CONTENT_URI)
            .withSelection(CalendarAlerts._ID+"=?",new String[]{Long.toString(alert.id)})
            .withValue(CalendarAlerts.STATE,CalendarAlerts.STATE_DISMISSED).withExpectedCount(1).build());
        // Arm the exact one-shot PI before the atomic row change. If this
        // process exits after the batch commits, AlarmManager already owns the
        // wakeup. If the batch fails, the one-shot wakeup finds no snoozed row;
        // the original fired reminder remains intact and visible.
        scheduleSnooze(context,when);
        ContentProviderResult[] result=context.getContentResolver().applyBatch(CalendarContract.AUTHORITY,ops);
        if(result==null || result.length!=3 || result[1]==null || result[1].uri==null)
            throw new IllegalStateException("Snooze could not be confirmed.");
        ProviderReceipt.id(result[1].uri.toString(),"calendar_alerts");
        manager(context).cancel(alert.tag(),0);
    }

    private static void scheduleSnooze(Context context,long when) {
        // This is the existing Calendar app snooze protocol: a durable alerts row
        // plus a one-shot EVENT_REMINDER. Ordinary Reminders are scheduled only
        // by CalendarProvider; this code does not mirror its future alarms.
        Intent broadcast=new Intent(CalendarContract.ACTION_EVENT_REMINDER).setClassName(PACKAGE,RECEIVER);
        broadcast.setData(ContentUris.withAppendedId(CalendarAlerts.CONTENT_URI,when));
        broadcast.putExtra(CalendarAlerts.ALARM_TIME,when);
        broadcast.addFlags(Intent.FLAG_RECEIVER_FOREGROUND);
        PendingIntent intent=PendingIntent.getBroadcast(context,0,broadcast,
            PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        AlarmManager manager=context.getSystemService(AlarmManager.class);
        if(manager==null) throw new IllegalStateException("Alarm service unavailable.");
        if(manager.canScheduleExactAlarms()) manager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,when,intent);
        else manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,when,intent);
    }

    /** Legacy private-component contract: only exact fired occurrences may be snoozed. */
    public static void snoozeLegacy(Context context,Intent intent) throws Exception {
        if(intent==null) return;
        long id=intent.getLongExtra("eventid",-1);
        long begin=intent.getLongExtra("eventstart",-1),end=intent.getLongExtra("eventend",-1);
        if(id<0 || begin<0 || end<begin) return;
        List<Alert> rows=new ArrayList<>();
        try(Cursor c=context.getContentResolver().query(CalendarAlerts.CONTENT_URI,PROJECTION,
                CalendarAlerts.EVENT_ID+"=? AND "+CalendarAlerts.BEGIN+"=? AND "+CalendarAlerts.END+"=? AND "+
                CalendarAlerts.STATE+"=?",new String[]{Long.toString(id),Long.toString(begin),Long.toString(end),
                Integer.toString(CalendarAlerts.STATE_FIRED)},CalendarAlerts._ID)) {
            if(c==null) throw new IllegalStateException("Calendar alerts unavailable.");
            while(c.moveToNext()) rows.add(new Alert(c));
        }
        for(Alert alert:rows) snooze(context,alert);
    }
    static void reportFailure(Context context,Exception failure) {
        // No event content, account names, intent extras or action tokens are logged.
        Log.w(TAG,"Reminder operation failed: "+failure.getClass().getSimpleName());
        try {
            channel(context);
            Intent open=new Intent(Intent.ACTION_MAIN).setClassName(PACKAGE,PACKAGE+".AllInOneActivity")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            PendingIntent content=PendingIntent.getActivity(context,1,open,
                PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
            manager(context).notify("calendar-reminder-status",0,new Notification.Builder(context,CHANNEL)
                .setSmallIcon(android.R.drawable.ic_menu_my_calendar)
                .setContentTitle("Calendar reminder needs attention")
                .setContentText("A reminder change could not be confirmed. Open Calendar to check the event.")
                .setContentIntent(content).setOnlyAlertOnce(true).setAutoCancel(true).build());
        } catch(RuntimeException ignored) { /* The original provider failure remains unmodified. */ }
    }
}
