.method public onReceive(Landroid/content/Context;Landroid/content/Intent;)V
    .registers 9

    .line 36
    invoke-virtual {p2}, Landroid/content/Intent;->getAction()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    .line 37
    const-string v2, "CalendarProvider2"

    if-eqz v0, :cond_7d

    const-string v3, "com.android.providers.calendar.intent.CalendarProvider2"

    .line 38
    invoke-virtual {v3, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-nez v3, :cond_1a

    const-string v3, "android.intent.action.EVENT_REMINDER"

    .line 39
    invoke-virtual {v3, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-nez v0, :cond_1a

    goto :goto_7d

    :cond_1a
    const/4 v0, 0x3

    .line 44
    invoke-static {v2, v0}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result v0

    if-eqz v0, :cond_32

    .line 45
    new-instance v0, Ljava/lang/StringBuilder;

    const-string v3, "Received intent: "

    invoke-direct {v0, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v0, p2}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    invoke-static {v2, v0}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    .line 48
    :cond_32
    new-instance v0, Landroid/app/job/JobWorkItem;

    invoke-direct {v0, p2}, Landroid/app/job/JobWorkItem;-><init>(Landroid/content/Intent;)V

    .line 49
    new-instance p2, Landroid/app/job/JobInfo$Builder;

    sget v3, Lcom/android/providers/calendar/CalendarProviderJobService;->JOB_ID:I

    new-instance v4, Landroid/content/ComponentName;

    const-class v5, Lcom/android/providers/calendar/CalendarProviderJobService;

    invoke-direct {v4, p1, v5}, Landroid/content/ComponentName;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    invoke-direct {p2, v3, v4}, Landroid/app/job/JobInfo$Builder;-><init>(ILandroid/content/ComponentName;)V

    const/4 v3, 0x1

    .line 51
    invoke-virtual {p2, v3}, Landroid/app/job/JobInfo$Builder;->setExpedited(Z)Landroid/app/job/JobInfo$Builder;

    move-result-object p2

    .line 52
    const-class v4, Landroid/app/job/JobScheduler;

    invoke-virtual {p1, v4}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object p1

    check-cast p1, Landroid/app/job/JobScheduler;

    .line 53
    invoke-virtual {p2}, Landroid/app/job/JobInfo$Builder;->build()Landroid/app/job/JobInfo;

    move-result-object v4

    invoke-virtual {p1, v4, v0}, Landroid/app/job/JobScheduler;->enqueue(Landroid/app/job/JobInfo;Landroid/app/job/JobWorkItem;)I

    move-result v4

    const/4 v5, -0x1

    if-ne v4, v3, :cond_61

    .line 54
    invoke-virtual {p0, v5}, Landroid/content/BroadcastReceiver;->setResultCode(I)V

    return-void

    .line 56
    :cond_61
    const-string v4, "Failed to schedule expedited job"

    invoke-static {v2, v4}, Landroid/util/Slog;->wtf(Ljava/lang/String;Ljava/lang/String;)I

    .line 58
    invoke-virtual {p2, v1}, Landroid/app/job/JobInfo$Builder;->setExpedited(Z)Landroid/app/job/JobInfo$Builder;

    .line 59
    invoke-virtual {p2}, Landroid/app/job/JobInfo$Builder;->build()Landroid/app/job/JobInfo;

    move-result-object p2

    invoke-virtual {p1, p2, v0}, Landroid/app/job/JobScheduler;->enqueue(Landroid/app/job/JobInfo;Landroid/app/job/JobWorkItem;)I

    move-result p1

    if-ne p1, v3, :cond_77

    .line 60
    invoke-virtual {p0, v5}, Landroid/content/BroadcastReceiver;->setResultCode(I)V

    return-void

    .line 62
    :cond_77
    const-string p0, "Failed to schedule regular job"

    invoke-static {v2, p0}, Landroid/util/Slog;->wtf(Ljava/lang/String;Ljava/lang/String;)I

    return-void

    .line 40
    :cond_7d
    :goto_7d
    new-instance p1, Ljava/lang/StringBuilder;

    const-string v0, "Received invalid intent: "

    invoke-direct {p1, v0}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {p1, p2}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {p1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p1

    invoke-static {v2, p1}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I

    .line 41
    invoke-virtual {p0, v1}, Landroid/content/BroadcastReceiver;->setResultCode(I)V

    return-void
.end method

