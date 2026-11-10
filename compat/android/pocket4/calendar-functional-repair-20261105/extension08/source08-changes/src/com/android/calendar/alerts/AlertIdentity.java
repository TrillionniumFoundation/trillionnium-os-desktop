/* Copyright 2026 The Droidloom Authors
 * SPDX-License-Identifier: Apache-2.0
 */
package com.android.calendar.alerts;

/** PendingIntent identity must survive reuse of a CalendarAlerts SQLite row ID. */
public final class AlertIdentity {
    private AlertIdentity() {}
    public static String key(long id,long event,long begin,long end,long alarm,long created,int minutes) {
        return id+":"+event+":"+begin+":"+end+":"+alarm+":"+created+":"+minutes;
    }
}
