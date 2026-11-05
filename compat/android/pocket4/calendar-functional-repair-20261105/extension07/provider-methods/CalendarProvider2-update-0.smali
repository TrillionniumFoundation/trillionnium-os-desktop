.method public update(Landroid/net/Uri;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I
    .registers 7

    .line 2331
    sget-object v0, Lcom/android/providers/calendar/CalendarAlarmManager;->SCHEDULE_ALARM_REMOVE_URI:Landroid/net/Uri;

    invoke-virtual {p1, v0}, Landroid/net/Uri;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_11

    .line 2332
    iget-boolean v0, p0, Lcom/android/providers/calendar/CalendarProvider2;->mPostInitializeWorkRunning:Z

    if-eqz v0, :cond_11

    const/4 p1, 0x1

    .line 2333
    iput-boolean p1, p0, Lcom/android/providers/calendar/CalendarProvider2;->mPendingScheduledAlarmsRemoval:Z

    const/4 p0, 0x0

    return p0

    .line 2337
    :cond_11
    invoke-virtual {p0}, Lcom/android/providers/calendar/SQLiteContentProvider;->applyingBatch()Z

    move-result v0

    if-nez v0, :cond_24

    .line 2338
    iget-object v0, p0, Lcom/android/providers/calendar/CalendarProvider2;->mCallingUid:Ljava/lang/ThreadLocal;

    invoke-static {}, Landroid/os/Binder;->getCallingUid()I

    move-result v1

    invoke-static {v1}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v1

    invoke-virtual {v0, v1}, Ljava/lang/ThreadLocal;->set(Ljava/lang/Object;)V

    .line 2341
    :cond_24
    invoke-super {p0, p1, p2, p3, p4}, Lcom/android/providers/calendar/SQLiteContentProvider;->update(Landroid/net/Uri;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I

    move-result p0

    return p0
.end method

