.class final Lcom/android/deskclock/alarms/AlarmStateManager$AlarmManagerStateChangeScheduler;
.super Ljava/lang/Object;
.source "AlarmStateManager.kt"

# interfaces
.implements Lcom/android/deskclock/alarms/AlarmStateManager$StateChangeScheduler;


# direct methods
.method public constructor <init>()V
    .registers 1

    .line 107
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method


# virtual methods
.method public cancelScheduledInstanceStateChange(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 10

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
    .registers 4
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

.method public scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V
    .registers 12

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;
    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;
    invoke-virtual {p3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;
    invoke-virtual {p2}, Ljava/util/Calendar;->getTimeInMillis()J
    move-result-wide v0
    if-ltz p4, :invalid_state
    const/16 v2, 0x8
    if-gt p4, v2, :invalid_state

    # Switching a timer between receiver and FGS types must not leave the old
    # type scheduled. Request code, URI, action, and ALARM_MANAGER category stay identical.
    invoke-virtual {p0, p1, p3}, Lcom/android/deskclock/alarms/AlarmStateManager$AlarmManagerStateChangeScheduler;->cancelScheduledInstanceStateChange(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    sget-object v2, Lcom/android/deskclock/alarms/AlarmStateManager;->Companion:Lcom/android/deskclock/alarms/AlarmStateManager$Companion;
    const-string v3, "ALARM_MANAGER"
    invoke-static {p4}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;
    move-result-object v6
    invoke-virtual {v2, p1, v3, p3, v6}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->createStateChangeIntent(Landroid/content/Context;Ljava/lang/String;Lcom/android/deskclock/provider/AlarmInstance;Ljava/lang/Integer;)Landroid/content/Intent;
    move-result-object v2
    const-string v3, "com.android.deskclock.extra.SCHEDULED_ALARM_VERSION"
    const/4 v6, 0x1
    invoke-virtual {v2, v3, v6}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;
    invoke-virtual {p3}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;
    move-result-object v3
    invoke-virtual {v3}, Ljava/util/Calendar;->getTimeInMillis()J
    move-result-wide v4
    const-string v3, "com.android.deskclock.extra.SCHEDULED_ALARM_TIME"
    invoke-virtual {v2, v3, v4, v5}, Landroid/content/Intent;->putExtra(Ljava/lang/String;J)Landroid/content/Intent;
    iget-object v3, p3, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;
    const-wide/16 v4, -0x1
    if-eqz v3, :parent_ready
    invoke-virtual {v3}, Ljava/lang/Long;->longValue()J
    move-result-wide v4
    :parent_ready
    const-string v3, "com.android.deskclock.extra.SCHEDULED_ALARM_PARENT"
    invoke-virtual {v2, v3, v4, v5}, Landroid/content/Intent;->putExtra(Ljava/lang/String;J)Landroid/content/Intent;
    iget v4, p3, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I
    const-string v3, "com.android.deskclock.extra.SCHEDULED_ALARM_FROM_STATE"
    invoke-virtual {v2, v3, v4}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;
    const/high16 v3, 0x10000000
    invoke-virtual {v2, v3}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;
    invoke-virtual {p3}, Lcom/android/deskclock/provider/AlarmInstance;->hashCode()I
    move-result v3
    const/high16 v4, 0x8000000
    const/4 v5, 0x5
    if-ne p4, v5, :receiver
    invoke-static {p1, v3, v2, v4}, Landroid/app/PendingIntent;->getForegroundService(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;
    move-result-object v2
    goto/16 :pending_ready
    :receiver
    const-class v5, Lcom/android/deskclock/alarms/AlarmStateManager;
    invoke-virtual {v2, p1, v5}, Landroid/content/Intent;->setClass(Landroid/content/Context;Ljava/lang/Class;)Landroid/content/Intent;
    invoke-static {p1, v3, v2, v4}, Landroid/app/PendingIntent;->getBroadcast(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;
    move-result-object v2
    :pending_ready
    invoke-virtual {v2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;
    const-string v3, "alarm"
    invoke-virtual {p1, v3}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;
    move-result-object v3
    check-cast v3, Landroid/app/AlarmManager;
    sget-object v4, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;
    invoke-virtual {v4}, Lcom/android/deskclock/Utils;->isMOrLater()Z
    move-result v4
    const/4 v5, 0x0
    if-eqz v4, :before_m
    invoke-virtual {v3, v5, v0, v1, v2}, Landroid/app/AlarmManager;->setExactAndAllowWhileIdle(IJLandroid/app/PendingIntent;)V
    return-void
    :before_m
    invoke-virtual {v3, v5, v0, v1, v2}, Landroid/app/AlarmManager;->setExact(IJLandroid/app/PendingIntent;)V
    return-void
    :invalid_state
    new-instance v2, Ljava/lang/IllegalArgumentException;
    const-string v3, "Invalid scheduled alarm state"
    invoke-direct {v2, v3}, Ljava/lang/IllegalArgumentException;-><init>(Ljava/lang/String;)V
    throw v2
.end method
