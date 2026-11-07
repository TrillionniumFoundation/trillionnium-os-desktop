.method static getCheckNextAlarmIntent(Landroid/content/Context;Z)Landroid/content/Intent;
    .registers 4

    .line 141
    new-instance v0, Landroid/content/Intent;

    const-string v1, "com.android.providers.calendar.intent.CalendarProvider2"

    invoke-direct {v0, v1}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    .line 142
    const-class v1, Lcom/android/providers/calendar/CalendarProviderBroadcastReceiver;

    invoke-virtual {v0, p0, v1}, Landroid/content/Intent;->setClass(Landroid/content/Context;Ljava/lang/Class;)Landroid/content/Intent;

    if-eqz p1, :cond_14

    .line 144
    const-string p0, "removeAlarms"

    const/4 p1, 0x1

    invoke-virtual {v0, p0, p1}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Z)Landroid/content/Intent;

    :cond_14
    return-object v0
.end method

