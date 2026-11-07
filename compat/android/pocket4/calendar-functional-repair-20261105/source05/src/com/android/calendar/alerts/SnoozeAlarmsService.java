/*
 * Copyright 2026 The Droidloom Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package com.android.calendar.alerts;

import android.app.IntentService;
import android.content.Intent;

/** Restores the non-exported service already declared by the installed manifest. */
public final class SnoozeAlarmsService extends IntentService {
    public SnoozeAlarmsService() { super("CalendarSnooze"); }
    @Override protected void onHandleIntent(Intent intent) {
        try { RestoredAlerts.snoozeLegacy(this,intent); }
        catch(Exception failure) { RestoredAlerts.reportFailure(this,failure); }
    }
}
