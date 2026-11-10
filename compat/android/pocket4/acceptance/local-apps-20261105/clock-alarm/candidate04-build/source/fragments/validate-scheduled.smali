.method public final isScheduledIntentCurrent(Landroid/content/Context;Landroid/content/Intent;Lcom/android/deskclock/provider/AlarmInstance;)Z
    .locals 8

    # Only the new scheduler envelope adds these checks. Existing unmarked
    # restoration, SNOOZE_TAG, DISMISS_TAG, and negative-state registration keep
    # the installed handler's semantics and global-generation exceptions.
    const-string v0, "com.android.deskclock.extra.SCHEDULED_ALARM_VERSION"
    invoke-virtual {p2, v0}, Landroid/content/Intent;->hasExtra(Ljava/lang/String;)Z
    move-result v1
    if-eqz v1, :accept
    const/4 v1, -0x1
    invoke-virtual {p2, v0, v1}, Landroid/content/Intent;->getIntExtra(Ljava/lang/String;I)I
    move-result v0
    const/4 v1, 0x1
    if-ne v0, v1, :reject
    if-eqz p3, :reject
    const-string v0, "change_state"
    invoke-virtual {p2}, Landroid/content/Intent;->getAction()Ljava/lang/String;
    move-result-object v1
    invoke-virtual {v0, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-eqz v0, :reject
    const-string v0, "ALARM_MANAGER"
    invoke-virtual {p2, v0}, Landroid/content/Intent;->hasCategory(Ljava/lang/String;)Z
    move-result v0
    if-eqz v0, :reject
    sget-object v0, Lcom/android/deskclock/data/DataModel;->Companion:Lcom/android/deskclock/data/DataModel$Companion;
    invoke-virtual {v0}, Lcom/android/deskclock/data/DataModel$Companion;->getDataModel()Lcom/android/deskclock/data/DataModel;
    move-result-object v0
    invoke-virtual {v0}, Lcom/android/deskclock/data/DataModel;->getGlobalIntentId()I
    move-result v0
    const-string v1, "intent.extra.alarm.global.id"
    const/4 v6, -0x1
    invoke-virtual {p2, v1, v6}, Landroid/content/Intent;->getIntExtra(Ljava/lang/String;I)I
    move-result v1
    if-ne v0, v1, :reject
    const-string v0, "intent.extra.alarm.state"
    invoke-virtual {p2, v0, v6}, Landroid/content/Intent;->getIntExtra(Ljava/lang/String;I)I
    move-result v7
    if-ltz v7, :reject
    const/16 v0, 0x8
    if-gt v7, v0, :reject
    const-string v1, "com.android.deskclock.extra.SCHEDULED_ALARM_FROM_STATE"
    invoke-virtual {p2, v1, v6}, Landroid/content/Intent;->getIntExtra(Ljava/lang/String;I)I
    move-result v6
    if-ltz v6, :reject
    if-gt v6, v0, :reject
    iget v1, p3, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I
    const/4 v0, 0x5
    if-ne v7, v0, :source_match
    if-gt v1, v0, :reject
    if-ltz v1, :reject
    # A valid FIRED instance may legitimately restart after process death.
    if-ne v1, v0, :source_match
    if-le v6, v0, :state_ready
    :source_match
    if-ne v1, v6, :reject
    :state_ready
    const-string v0, "com.android.deskclock.extra.SCHEDULED_ALARM_TIME"
    const-wide/high16 v2, -0x8000000000000000L
    invoke-virtual {p2, v0, v2, v3}, Landroid/content/Intent;->getLongExtra(Ljava/lang/String;J)J
    move-result-wide v2
    invoke-virtual {p3}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;
    move-result-object v0
    invoke-virtual {v0}, Ljava/util/Calendar;->getTimeInMillis()J
    move-result-wide v4
    cmp-long v0, v2, v4
    if-nez v0, :reject
    const-string v0, "com.android.deskclock.extra.SCHEDULED_ALARM_PARENT"
    const-wide/high16 v2, -0x8000000000000000L
    invoke-virtual {p2, v0, v2, v3}, Landroid/content/Intent;->getLongExtra(Ljava/lang/String;J)J
    move-result-wide v2
    iget-object v0, p3, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;
    const-wide/16 v4, -0x1
    if-eqz v0, :parent_ready
    invoke-virtual {v0}, Ljava/lang/Long;->longValue()J
    move-result-wide v4
    :parent_ready
    cmp-long v0, v2, v4
    if-nez v0, :reject
    :accept
    const/4 v0, 0x1
    return v0
    :reject
    const/4 v0, 0x0
    return v0
.end method

.method public final sameScheduledOccurrence(Lcom/android/deskclock/provider/AlarmInstance;Lcom/android/deskclock/provider/AlarmInstance;)Z
    .locals 5
    if-eqz p1, :different
    if-eqz p2, :different
    iget-wide v0, p1, Lcom/android/deskclock/provider/AlarmInstance;->mId:J
    iget-wide v2, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J
    cmp-long v4, v0, v2
    if-nez v4, :different
    iget-object v0, p1, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;
    iget-object v1, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;
    invoke-static {v0, v1}, Ljava/util/Objects;->equals(Ljava/lang/Object;Ljava/lang/Object;)Z
    move-result v4
    if-eqz v4, :different
    invoke-virtual {p1}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;
    move-result-object v0
    invoke-virtual {v0}, Ljava/util/Calendar;->getTimeInMillis()J
    move-result-wide v0
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;
    move-result-object v2
    invoke-virtual {v2}, Ljava/util/Calendar;->getTimeInMillis()J
    move-result-wide v2
    cmp-long v4, v0, v2
    if-nez v4, :different
    const/4 v0, 0x1
    return v0
    :different
    const/4 v0, 0x0
    return v0
.end method
