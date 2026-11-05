.method static removeScheduledAlarms(Landroid/content/ContentResolver;)V
    .registers 3

    .line 89
    sget-object v0, Lcom/android/providers/calendar/CalendarAlarmManager;->SCHEDULE_ALARM_REMOVE_URI:Landroid/net/Uri;

    const/4 v1, 0x0

    invoke-virtual {p0, v0, v1, v1, v1}, Landroid/content/ContentResolver;->update(Landroid/net/Uri;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I

    return-void
.end method

