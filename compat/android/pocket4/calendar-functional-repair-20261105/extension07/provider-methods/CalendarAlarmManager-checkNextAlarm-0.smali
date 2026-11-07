.method checkNextAlarm(Z)V
    .registers 6

    .line 167
    iget-object v0, p0, Lcom/android/providers/calendar/CalendarAlarmManager;->mNextAlarmCheckScheduled:Ljava/util/concurrent/atomic/AtomicBoolean;

    const/4 v1, 0x1

    invoke-virtual {v0, v1}, Ljava/util/concurrent/atomic/AtomicBoolean;->getAndSet(Z)Z

    move-result v0

    if-eqz v0, :cond_d

    if-eqz p1, :cond_c

    goto :goto_d

    :cond_c
    return-void

    :cond_d
    :goto_d
    const/4 v0, 0x3

    .line 168
    const-string v1, "CalendarProvider2"

    invoke-static {v1, v0}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result v0

    if-eqz v0, :cond_1b

    .line 169
    const-string v0, "Scheduling check of next Alarm"

    invoke-static {v1, v0}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    .line 171
    :cond_1b
    iget-object v0, p0, Lcom/android/providers/calendar/CalendarAlarmManager;->mContext:Landroid/content/Context;

    invoke-static {v0, p1}, Lcom/android/providers/calendar/CalendarAlarmManager;->getCheckNextAlarmIntent(Landroid/content/Context;Z)Landroid/content/Intent;

    move-result-object p1

    .line 172
    iget-object v0, p0, Lcom/android/providers/calendar/CalendarAlarmManager;->mContext:Landroid/content/Context;

    const/high16 v1, 0x24000000

    const/4 v2, 0x0

    invoke-static {v0, v2, p1, v1}, Landroid/app/PendingIntent;->getBroadcast(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;

    move-result-object v0

    if-eqz v0, :cond_2f

    .line 176
    invoke-virtual {p0, v0}, Lcom/android/providers/calendar/CalendarAlarmManager;->cancel(Landroid/app/PendingIntent;)V

    .line 178
    :cond_2f
    iget-object v0, p0, Lcom/android/providers/calendar/CalendarAlarmManager;->mContext:Landroid/content/Context;

    const/high16 v1, 0x14000000

    invoke-static {v0, v2, p1, v1}, Landroid/app/PendingIntent;->getBroadcast(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;

    move-result-object p1

    .line 182
    invoke-static {}, Landroid/os/SystemClock;->elapsedRealtime()J

    move-result-wide v0

    const-wide/16 v2, 0x1388

    add-long/2addr v0, v2

    const/4 v2, 0x2

    .line 184
    invoke-virtual {p0, v2, v0, v1, p1}, Lcom/android/providers/calendar/CalendarAlarmManager;->setExactAndAllowWhileIdle(IJLandroid/app/PendingIntent;)V

    return-void
.end method

