/*
 * Copyright 2026 The Droidloom Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package com.android.calendar.repair;

import android.app.Activity;
import android.Manifest;
import android.content.pm.PackageManager;
import android.content.ContentUris;
import android.content.Context;
import android.content.Intent;
import android.provider.CalendarContract;
import android.provider.CalendarContract.Events;
import android.view.Menu;
import android.view.MenuItem;
import android.widget.Toast;

import com.android.calendar.alerts.RestoredAlerts;

/** Small ABI boundary called only by the selected original Calendar methods. */
public final class CalendarActions {
    private static final int NEW_EVENT=0x0d010101;
    private static final String PACKAGE="com.android.calendar";
    private static final String EDITOR="com.android.calendar.event.EditEventActivity";
    private static final String DETAILS="com.android.calendar.EventInfoActivity";
    private CalendarActions() {}

    public static void onCalendarStarted(Activity activity) {
        if(activity.checkSelfPermission(Manifest.permission.READ_CALENDAR)==PackageManager.PERMISSION_GRANTED &&
           activity.checkSelfPermission(Manifest.permission.WRITE_CALENDAR)==PackageManager.PERMISSION_GRANTED)
            RestoredAlerts.refresh(activity);
    }

    public static void addNewEvent(Menu menu) {
        if(menu.findItem(NEW_EVENT)==null) {
            menu.add(Menu.NONE,NEW_EVENT,0,"New event")
                .setIcon(android.R.drawable.ic_menu_add)
                .setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM);
        }
    }

    public static boolean onMenu(Activity activity,MenuItem item,Long selectedMillis) {
        if(item==null || item.getItemId()!=NEW_EVENT) return false;
        Intent intent=new Intent(Intent.ACTION_INSERT,Events.CONTENT_URI);
        intent.setClassName(PACKAGE,EDITOR);
        if(selectedMillis!=null) {
            intent.putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME,selectedMillis.longValue());
            intent.putExtra(CalendarContract.EXTRA_EVENT_END_TIME,selectedMillis.longValue()+3_600_000L);
        }
        open(activity,intent);
        return true;
    }

    public static boolean onEvent(Context context,long eventType,long eventId) {
        // These are exact constants from the captured CalendarController.EventType ABI.
        if(context==null || eventId<0 || (eventType!=2L && eventType!=4L && eventType!=8L)) return false;
        Intent intent=new Intent(eventType==8L?Intent.ACTION_EDIT:Intent.ACTION_VIEW,
            ContentUris.withAppendedId(Events.CONTENT_URI,eventId));
        intent.setClassName(PACKAGE,eventType==8L?EDITOR:DETAILS);
        if(!(context instanceof Activity)) intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        open(context,intent);
        return true;
    }

    private static void open(Context context,Intent intent) {
        try { context.startActivity(intent); }
        catch(RuntimeException failure) {
            Toast.makeText(context,"Calendar could not open this event. Please try again.",Toast.LENGTH_LONG).show();
        }
    }
}
