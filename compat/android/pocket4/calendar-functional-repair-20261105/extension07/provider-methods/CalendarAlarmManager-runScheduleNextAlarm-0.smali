.method runScheduleNextAlarm(ZLcom/android/providers/calendar/CalendarProvider2;)V
    .registers 6

    .line 207
    invoke-virtual {p2}, Lcom/android/providers/calendar/SQLiteContentProvider;->getWritableDatabase()Landroid/database/sqlite/SQLiteDatabase;

    move-result-object v0

    if-nez v0, :cond_e

    .line 209
    const-string p0, "CalendarProvider2"

    const-string p1, "Unable to get the database."

    invoke-static {p0, p1}, Landroid/util/Log;->wtf(Ljava/lang/String;Ljava/lang/String;)I

    return-void

    .line 214
    :cond_e
    iget-object v1, p0, Lcom/android/providers/calendar/CalendarAlarmManager;->mNextAlarmCheckScheduled:Ljava/util/concurrent/atomic/AtomicBoolean;

    const/4 v2, 0x0

    invoke-virtual {v1, v2}, Ljava/util/concurrent/atomic/AtomicBoolean;->set(Z)V

    .line 215
    invoke-virtual {v0}, Landroid/database/sqlite/SQLiteDatabase;->beginTransaction()V

    if-eqz p1, :cond_1f

    .line 218
    :try_start_19
    invoke-static {v0}, Lcom/android/providers/calendar/CalendarAlarmManager;->removeScheduledAlarmsLocked(Landroid/database/sqlite/SQLiteDatabase;)V

    goto :goto_1f

    :catchall_1d
    move-exception p0

    goto :goto_29

    .line 220
    :cond_1f
    :goto_1f
    invoke-direct {p0, v0, p2}, Lcom/android/providers/calendar/CalendarAlarmManager;->scheduleNextAlarmLocked(Landroid/database/sqlite/SQLiteDatabase;Lcom/android/providers/calendar/CalendarProvider2;)V

    .line 221
    invoke-virtual {v0}, Landroid/database/sqlite/SQLiteDatabase;->setTransactionSuccessful()V
    :try_end_25
    .catchall {:try_start_19 .. :try_end_25} :catchall_1d

    .line 223
    invoke-virtual {v0}, Landroid/database/sqlite/SQLiteDatabase;->endTransaction()V

    return-void

    :goto_29
    invoke-virtual {v0}, Landroid/database/sqlite/SQLiteDatabase;->endTransaction()V

    .line 224
    throw p0
.end method

