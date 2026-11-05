.method public cancelScheduledInstanceStateChange(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .locals 7

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;
    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->hashCode()I
    move-result v0
    sget-object v4, Lcom/android/deskclock/alarms/AlarmStateManager;->Companion:Lcom/android/deskclock/alarms/AlarmStateManager$Companion;
    const-string v5, "ALARM_MANAGER"
    const/4 v6, 0x0
    invoke-virtual {v4, p1, v5, p2, v6}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->createStateChangeIntent(Landroid/content/Context;Ljava/lang/String;Lcom/android/deskclock/provider/AlarmInstance;Ljava/lang/Integer;)Landroid/content/Intent;
    move-result-object v1
    const/high16 v2, 0x20000000

    # The installed preimage used a service PI for every state. Cancel that
    # exact legacy identity as well as both new identities; extras are not PI identity.
    invoke-static {p1, v0, v1, v2}, Landroid/app/PendingIntent;->getService(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;
    move-result-object v3
    invoke-direct {p0, p1, v3}, Lcom/android/deskclock/alarms/AlarmStateManager$AlarmManagerStateChangeScheduler;->cancelIfPresent(Landroid/content/Context;Landroid/app/PendingIntent;)V
    invoke-static {p1, v0, v1, v2}, Landroid/app/PendingIntent;->getForegroundService(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;
    move-result-object v3
    invoke-direct {p0, p1, v3}, Lcom/android/deskclock/alarms/AlarmStateManager$AlarmManagerStateChangeScheduler;->cancelIfPresent(Landroid/content/Context;Landroid/app/PendingIntent;)V
    const-class v3, Lcom/android/deskclock/alarms/AlarmStateManager;
    invoke-virtual {v1, p1, v3}, Landroid/content/Intent;->setClass(Landroid/content/Context;Ljava/lang/Class;)Landroid/content/Intent;
    invoke-static {p1, v0, v1, v2}, Landroid/app/PendingIntent;->getBroadcast(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;
    move-result-object v3
    invoke-direct {p0, p1, v3}, Lcom/android/deskclock/alarms/AlarmStateManager$AlarmManagerStateChangeScheduler;->cancelIfPresent(Landroid/content/Context;Landroid/app/PendingIntent;)V
    return-void
.end method

.method private final cancelIfPresent(Landroid/content/Context;Landroid/app/PendingIntent;)V
    .locals 1
    if-eqz p2, :done
    const-string v0, "alarm"
    invoke-virtual {p1, v0}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;
    move-result-object v0
    check-cast v0, Landroid/app/AlarmManager;
    invoke-virtual {v0, p2}, Landroid/app/AlarmManager;->cancel(Landroid/app/PendingIntent;)V
    invoke-virtual {p2}, Landroid/app/PendingIntent;->cancel()V
    :done
    return-void
.end method
