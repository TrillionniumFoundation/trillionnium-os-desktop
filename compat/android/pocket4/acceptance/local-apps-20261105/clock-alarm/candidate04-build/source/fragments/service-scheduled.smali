.method private final stopScheduledStartIfIdle(I)V
    .locals 1
    iget-object v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;
    if-nez v0, :done
    invoke-virtual {p0, p1}, Landroid/app/Service;->stopSelf(I)V
    :done
    return-void
.end method

.method private final onScheduledStart(Landroid/content/Intent;I)Z
    .locals 10
    if-eqz p1, :legacy
    const-string v1, "com.android.deskclock.extra.SCHEDULED_ALARM_VERSION"
    invoke-virtual {p1, v1}, Landroid/content/Intent;->hasExtra(Ljava/lang/String;)Z
    move-result v1
    if-eqz v1, :legacy

    :try_start
    const-string v1, "intent.extra.alarm.state"
    const/4 v5, -0x1
    invoke-virtual {p1, v1, v5}, Landroid/content/Intent;->getIntExtra(Ljava/lang/String;I)I
    move-result v1
    const/4 v5, 0x5
    if-ne v1, v5, :idle
    invoke-virtual {p1}, Landroid/content/Intent;->getData()Landroid/net/Uri;
    move-result-object v2
    if-eqz v2, :idle
    sget-object v4, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;
    :uri_start
    invoke-virtual {v4, v2}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getId(Landroid/net/Uri;)J
    move-result-wide v2
    :uri_end
    invoke-virtual {p0}, Landroid/app/Service;->getContentResolver()Landroid/content/ContentResolver;
    move-result-object v1
    invoke-virtual {v4, v1, v2, v3}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getInstance(Landroid/content/ContentResolver;J)Lcom/android/deskclock/provider/AlarmInstance;
    move-result-object v0
    if-eqz v0, :idle
    sget-object v4, Lcom/android/deskclock/alarms/AlarmStateManager;->Companion:Lcom/android/deskclock/alarms/AlarmStateManager$Companion;
    invoke-virtual {v4, p0, p1, v0}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->isScheduledIntentCurrent(Landroid/content/Context;Landroid/content/Intent;Lcom/android/deskclock/provider/AlarmInstance;)Z
    move-result v1
    if-eqz v1, :idle
    invoke-static {}, Ljava/util/Calendar;->getInstance()Ljava/util/Calendar;
    move-result-object v7
    invoke-virtual {v0}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;
    move-result-object v8
    invoke-virtual {v7, v8}, Ljava/util/Calendar;->before(Ljava/lang/Object;)Z
    move-result v1
    if-nez v1, :idle
    invoke-virtual {v0}, Lcom/android/deskclock/provider/AlarmInstance;->getTimeout()Ljava/util/Calendar;
    move-result-object v8
    if-eqz v8, :not_expired
    invoke-virtual {v7, v8}, Ljava/util/Calendar;->after(Ljava/lang/Object;)Z
    move-result v1
    if-eqz v1, :not_expired
    # Use the installed recovery transition (MISSED/deletion as appropriate),
    # rather than starting an already expired alarm or inventing a new state rule.
    const/4 v1, 0x1
    invoke-virtual {v4, p0, v0, v1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->registerInstance(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;Z)V
    goto :idle

    :not_expired
    iget v1, v0, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I
    if-ne v1, v5, :handle
    iget-object v7, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;
    invoke-virtual {v4, v0, v7}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->sameScheduledOccurrence(Lcom/android/deskclock/provider/AlarmInstance;Lcom/android/deskclock/provider/AlarmInstance;)Z
    move-result v1
    if-nez v1, :handled

    :handle
    invoke-virtual {v4, p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->handleIntent(Landroid/content/Context;Landroid/content/Intent;)V
    # A void handler return does not prove that the requested state was accepted.
    # Read the same occurrence again; only a current FIRED row may start sound/FGS.
    sget-object v6, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;
    invoke-virtual {p0}, Landroid/app/Service;->getContentResolver()Landroid/content/ContentResolver;
    move-result-object v1
    invoke-virtual {v6, v1, v2, v3}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getInstance(Landroid/content/ContentResolver;J)Lcom/android/deskclock/provider/AlarmInstance;
    move-result-object v6
    invoke-virtual {v4, v0, v6}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->sameScheduledOccurrence(Lcom/android/deskclock/provider/AlarmInstance;Lcom/android/deskclock/provider/AlarmInstance;)Z
    move-result v1
    if-eqz v1, :idle
    iget v1, v6, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I
    if-ne v1, v5, :idle
    invoke-virtual {v4, p0, p1, v6}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->isScheduledIntentCurrent(Landroid/content/Context;Landroid/content/Intent;Lcom/android/deskclock/provider/AlarmInstance;)Z
    move-result v1
    if-eqz v1, :idle
    iget-object v7, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;
    invoke-virtual {v4, v6, v7}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->sameScheduledOccurrence(Lcom/android/deskclock/provider/AlarmInstance;Lcom/android/deskclock/provider/AlarmInstance;)Z
    move-result v1
    if-nez v1, :handled
    invoke-direct {p0, v6}, Lcom/android/deskclock/alarms/AlarmService;->startAlarm(Lcom/android/deskclock/provider/AlarmInstance;)V
    :try_end
    goto :handled

    :malformed_uri
    move-exception v0
    :idle
    invoke-direct {p0, p2}, Lcom/android/deskclock/alarms/AlarmService;->stopScheduledStartIfIdle(I)V
    :handled
    const/4 v0, 0x1
    return v0
    :failed
    move-exception v0
    invoke-direct {p0, p2}, Lcom/android/deskclock/alarms/AlarmService;->stopScheduledStartIfIdle(I)V
    throw v0
    :legacy
    const/4 v0, 0x0
    return v0

    .catch Ljava/lang/IllegalArgumentException; {:uri_start .. :uri_end} :malformed_uri
    .catchall {:try_start .. :try_end} :failed
.end method
