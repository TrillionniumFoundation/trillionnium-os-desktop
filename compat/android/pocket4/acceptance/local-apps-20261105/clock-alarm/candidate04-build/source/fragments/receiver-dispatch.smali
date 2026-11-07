.method public static $r8$lambda$_knPXn4cJMDcun_XoalMIdqZCj0(Landroid/content/Context;Landroid/content/Intent;Landroid/content/BroadcastReceiver$PendingResult;Landroid/os/PowerManager$WakeLock;)Lkotlin/Unit;
    .locals 2
    :try_start
    const-string v0, "com.android.deskclock.extra.SCHEDULED_ALARM_VERSION"
    invoke-virtual {p1, v0}, Landroid/content/Intent;->hasExtra(Ljava/lang/String;)Z
    move-result v0
    if-eqz v0, :handle
    const-string v0, "intent.extra.alarm.state"
    const/4 v1, -0x1
    invoke-virtual {p1, v0, v1}, Landroid/content/Intent;->getIntExtra(Ljava/lang/String;I)I
    move-result v0
    const/4 v1, 0x5
    # New scheduled FIRED events belong to the foreground-service PI only.
    if-eq v0, v1, :complete
    :handle
    sget-object v0, Lcom/android/deskclock/alarms/AlarmStateManager;->Companion:Lcom/android/deskclock/alarms/AlarmStateManager$Companion;
    invoke-virtual {v0, p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->handleIntent(Landroid/content/Context;Landroid/content/Intent;)V
    :try_end
    :complete
    invoke-static {p2, p3}, Lcom/android/deskclock/alarms/AlarmStateManager;->finishScheduledBroadcast(Landroid/content/BroadcastReceiver$PendingResult;Landroid/os/PowerManager$WakeLock;)V
    sget-object v0, Lkotlin/Unit;->INSTANCE:Lkotlin/Unit;
    return-object v0
    :failed
    move-exception v0
    invoke-static {p2, p3}, Lcom/android/deskclock/alarms/AlarmStateManager;->finishScheduledBroadcast(Landroid/content/BroadcastReceiver$PendingResult;Landroid/os/PowerManager$WakeLock;)V
    throw v0
    .catchall {:try_start .. :try_end} :failed
.end method

.method private static finishScheduledBroadcast(Landroid/content/BroadcastReceiver$PendingResult;Landroid/os/PowerManager$WakeLock;)V
    .locals 1
    :try_start
    invoke-virtual {p0}, Landroid/content/BroadcastReceiver$PendingResult;->finish()V
    :try_end
    invoke-virtual {p1}, Landroid/os/PowerManager$WakeLock;->release()V
    return-void
    :failed
    move-exception v0
    invoke-virtual {p1}, Landroid/os/PowerManager$WakeLock;->release()V
    throw v0
    .catchall {:try_start .. :try_end} :failed
.end method
