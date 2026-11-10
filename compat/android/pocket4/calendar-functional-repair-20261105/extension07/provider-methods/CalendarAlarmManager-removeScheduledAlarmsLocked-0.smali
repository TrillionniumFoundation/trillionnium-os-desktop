.method private static removeScheduledAlarmsLocked(Landroid/database/sqlite/SQLiteDatabase;)V
    .registers 4

    const/4 v0, 0x3

    .line 474
    const-string v1, "CalendarProvider2"

    invoke-static {v1, v0}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result v0

    if-eqz v0, :cond_e

    .line 475
    const-string v0, "removing scheduled alarms"

    invoke-static {v1, v0}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    .line 477
    :cond_e
    const-string v0, "state=0"

    const/4 v1, 0x0

    const-string v2, "CalendarAlerts"

    invoke-virtual {p0, v2, v0, v1}, Landroid/database/sqlite/SQLiteDatabase;->delete(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;)I

    return-void
.end method

