.class public final Lcom/android/deskclock/alarms/AlarmStateManager$Companion;
.super Ljava/lang/Object;
.source "AlarmStateManager.kt"


# direct methods
.method private constructor <init>()V
    .registers 1

    .line 151
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method public synthetic constructor <init>(Lkotlin/jvm/internal/DefaultConstructorMarker;)V
    .registers 2

    .line 0
    invoke-direct {p0}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;-><init>()V

    return-void
.end method

.method private final cancelScheduledInstanceStateChange(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 3

    .line 396
    # getter for: Lcom/android/deskclock/alarms/AlarmStateManager;->sStateChangeScheduler:Lcom/android/deskclock/alarms/AlarmStateManager$StateChangeScheduler;
    invoke-static {}, Lcom/android/deskclock/alarms/AlarmStateManager;->access$getSStateChangeScheduler$cp()Lcom/android/deskclock/alarms/AlarmStateManager$StateChangeScheduler;

    move-result-object p0

    invoke-interface {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$StateChangeScheduler;->cancelScheduledInstanceStateChange(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void
.end method

.method private final createIndicatorIntent(Landroid/content/Context;)Landroid/content/Intent;
    .registers 3

    .line 1008
    new-instance p0, Landroid/content/Intent;

    const-class v0, Lcom/android/deskclock/alarms/AlarmStateManager;

    invoke-direct {p0, p1, v0}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    const-string p1, "indicator"

    invoke-virtual {p0, p1}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    move-result-object p0

    invoke-virtual {p0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    return-object p0
.end method

.method private final getCurrentTime()Ljava/util/Calendar;
    .registers 1

    .line 191
    invoke-static {}, Lcom/android/deskclock/alarms/AlarmStateManager;->access$getSCurrentTimeFactory$cp()Lcom/android/deskclock/alarms/AlarmStateManager$CurrentTimeFactory;

    .line 192
    sget-object p0, Lcom/android/deskclock/data/DataModel;->Companion:Lcom/android/deskclock/data/DataModel$Companion;

    invoke-virtual {p0}, Lcom/android/deskclock/data/DataModel$Companion;->getDataModel()Lcom/android/deskclock/data/DataModel;

    move-result-object p0

    invoke-virtual {p0}, Lcom/android/deskclock/data/DataModel;->getCalendar()Ljava/util/Calendar;

    move-result-object p0

    return-object p0
.end method

.method private final scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V
    .registers 5

    .line 386
    # getter for: Lcom/android/deskclock/alarms/AlarmStateManager;->sStateChangeScheduler:Lcom/android/deskclock/alarms/AlarmStateManager$StateChangeScheduler;
    invoke-static {}, Lcom/android/deskclock/alarms/AlarmStateManager;->access$getSStateChangeScheduler$cp()Lcom/android/deskclock/alarms/AlarmStateManager$StateChangeScheduler;

    move-result-object p0

    invoke-interface {p0, p1, p2, p3, p4}, Lcom/android/deskclock/alarms/AlarmStateManager$StateChangeScheduler;->scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V

    return-void
.end method

.method private final setAlarmState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;I)V
    .registers 4

    if-nez p2, :cond_12

    .line 909
    sget-object p0, Lcom/android/deskclock/LogUtils;->INSTANCE:Lcom/android/deskclock/LogUtils;

    invoke-static {p3}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object p1

    filled-new-array {p1}, [Ljava/lang/Object;

    move-result-object p1

    const-string p2, "Null alarm instance while setting state to %d"

    invoke-virtual {p0, p2, p1}, Lcom/android/deskclock/LogUtils;->e(Ljava/lang/String;[Ljava/lang/Object;)V

    return-void

    :cond_12
    packed-switch p3, :pswitch_data_52

    .line 930
    sget-object p0, Lcom/android/deskclock/LogUtils;->INSTANCE:Lcom/android/deskclock/LogUtils;

    new-instance p1, Ljava/lang/StringBuilder;

    const-string p2, "Trying to change to unknown alarm state: "

    invoke-direct {p1, p2}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {p1, p3}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    invoke-virtual {p1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p1

    const/4 p2, 0x0

    new-array p2, p2, [Ljava/lang/Object;

    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/LogUtils;->e(Ljava/lang/String;[Ljava/lang/Object;)V

    return-void

    .line 928
    :pswitch_2c
    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setPreDismissState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    .line 929
    :pswitch_30
    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->deleteInstanceAndUpdateParent(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    .line 927
    :pswitch_34
    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setMissedState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    .line 923
    :pswitch_38
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setFiredState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    :pswitch_3c
    const/4 p3, 0x1

    .line 925
    invoke-virtual {p0, p1, p2, p3}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setSnoozeState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;Z)V

    return-void

    .line 921
    :pswitch_41
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setHighNotificationState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    .line 918
    :pswitch_45
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setHideNotificationState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    .line 915
    :pswitch_49
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setLowNotificationState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    .line 913
    :pswitch_4d
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setSilentState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    nop

    :pswitch_data_52
    .packed-switch 0x0
        :pswitch_4d
        :pswitch_49
        :pswitch_45
        :pswitch_41
        :pswitch_3c
        :pswitch_38
        :pswitch_34
        :pswitch_30
        :pswitch_2c
    .end packed-switch
.end method

.method private final setDismissState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 6

    .line 640
    iget-wide v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance p0, Ljava/lang/StringBuilder;

    const-string v2, "Setting dismissed state to instance "

    invoke-direct {p0, v2}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {p0, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {p0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p0

    const/4 v0, 0x0

    new-array v0, v0, [Ljava/lang/Object;

    invoke-static {p0, v0}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    const/4 p0, 0x7

    .line 641
    iput p0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    .line 642
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object p0

    invoke-virtual {p0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 643
    sget-object p1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {p1, p0, p2}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->updateInstance(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/AlarmInstance;)Z

    return-void
.end method

.method private final setFiredState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 13

    .line 496
    iget-wide v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "Setting fire state to instance "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v2, v1, [Ljava/lang/Object;

    invoke-static {v0, v2}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 499
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v5

    invoke-virtual {v5}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/4 v0, 0x5

    .line 500
    iput v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    .line 501
    sget-object v3, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {v3, v5, p2}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->updateInstance(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/AlarmInstance;)Z

    .line 503
    iget-object v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;

    if-eqz v0, :cond_34

    invoke-virtual {v0}, Ljava/lang/Number;->longValue()J

    move-result-wide v6

    .line 506
    iget-wide v8, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    move-object v4, p1

    invoke-virtual/range {v3 .. v9}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->deleteOtherInstances(Landroid/content/Context;Landroid/content/ContentResolver;JJ)V

    goto :goto_35

    :cond_34
    move-object v4, p1

    :goto_35
    const p1, 0x7f12017b

    .line 509
    invoke-static {p1, v1}, Lcom/android/deskclock/events/Events;->sendAlarmEvent(II)V

    .line 511
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getTimeout()Ljava/util/Calendar;

    move-result-object p1

    if-eqz p1, :cond_47

    .line 513
    sget-object v0, Lcom/android/deskclock/alarms/AlarmStateManager;->Companion:Lcom/android/deskclock/alarms/AlarmStateManager$Companion;

    const/4 v1, 0x6

    invoke-direct {v0, v4, p1, p2, v1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V

    .line 517
    :cond_47
    invoke-direct {p0, v4}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateNextAlarm(Landroid/content/Context;)V

    return-void
.end method

.method private final setHideNotificationState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 7

    .line 452
    iget-wide v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "Setting hide notification state to instance "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v0, v1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 455
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/4 v1, 0x2

    .line 456
    iput v1, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    .line 457
    sget-object v1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {v1, v0, p2}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->updateInstance(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/AlarmInstance;)Z

    .line 460
    invoke-static {p1, p2}, Lcom/android/deskclock/alarms/AlarmNotifications;->clearNotification(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 461
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getHighNotificationTime()Ljava/util/Calendar;

    move-result-object v0

    const/4 v1, 0x3

    invoke-direct {p0, p1, v0, p2, v1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V

    return-void
.end method

.method private final setHighNotificationState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 7

    .line 474
    iget-wide v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "Setting high notification state to instance "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v0, v1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 477
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/4 v1, 0x3

    .line 478
    iput v1, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    .line 479
    sget-object v1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {v1, v0, p2}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->updateInstance(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/AlarmInstance;)Z

    .line 482
    invoke-static {p1, p2}, Lcom/android/deskclock/alarms/AlarmNotifications;->showHighPriorityNotification(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 483
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v0

    const/4 v1, 0x5

    invoke-direct {p0, p1, v0, p2, v1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V

    return-void
.end method

.method private final setLowNotificationState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 7

    .line 430
    iget-wide v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "Setting low notification state to instance "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v0, v1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 433
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/4 v1, 0x1

    .line 434
    iput v1, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    .line 435
    sget-object v1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {v1, v0, p2}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->updateInstance(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/AlarmInstance;)Z

    .line 438
    invoke-static {p1, p2}, Lcom/android/deskclock/alarms/AlarmNotifications;->showLowPriorityNotification(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 439
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getHighNotificationTime()Ljava/util/Calendar;

    move-result-object v0

    const/4 v1, 0x3

    invoke-direct {p0, p1, v0, p2, v1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V

    return-void
.end method

.method private final setSilentState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 7

    .line 408
    iget-wide v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "Setting silent state to instance "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v2, v1, [Ljava/lang/Object;

    invoke-static {v0, v2}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 411
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 412
    iput v1, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    .line 413
    sget-object v1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {v1, v0, p2}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->updateInstance(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/AlarmInstance;)Z

    .line 416
    invoke-static {p1, p2}, Lcom/android/deskclock/alarms/AlarmNotifications;->clearNotification(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 417
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getLowNotificationTime()Ljava/util/Calendar;

    move-result-object v0

    const/4 v1, 0x1

    invoke-direct {p0, p1, v0, p2, v1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V

    return-void
.end method

.method private final updateNextAlarm(Landroid/content/Context;)V
    .registers 4

    .line 210
    invoke-virtual {p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->getNextFiringAlarm(Landroid/content/Context;)Lcom/android/deskclock/provider/AlarmInstance;

    move-result-object v0

    .line 212
    sget-object v1, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;

    invoke-virtual {v1}, Lcom/android/deskclock/Utils;->isPreL()Z

    move-result v1

    if-eqz v1, :cond_10

    .line 213
    invoke-direct {p0, p1, v0}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateNextAlarmInSystemSettings(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    .line 215
    :cond_10
    invoke-direct {p0, p1, v0}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateNextAlarmInAlarmManager(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void
.end method

.method private final updateNextAlarmInAlarmManager(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 9

    .line 274
    const-string v0, "alarm"

    invoke-virtual {p1, v0}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    check-cast v0, Landroid/app/AlarmManager;

    const/4 v1, 0x0

    if-nez p2, :cond_11

    const/high16 v2, 0x20000000

    goto :goto_12

    :cond_11
    move v2, v1

    .line 278
    :goto_12
    invoke-direct {p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->createIndicatorIntent(Landroid/content/Context;)Landroid/content/Intent;

    move-result-object p0

    .line 277
    invoke-static {p1, v1, p0, v2}, Landroid/app/PendingIntent;->getBroadcast(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;

    move-result-object p0

    if-eqz p2, :cond_58

    .line 281
    iget-wide v2, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v4, Ljava/lang/StringBuilder;

    const-string v5, "Setting upcoming AlarmClockInfo for alarm: "

    invoke-direct {v4, v5}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v4, v2, v3}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v4}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v2, v1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 282
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v1

    invoke-virtual {v1}, Ljava/util/Calendar;->getTimeInMillis()J

    move-result-wide v1

    .line 286
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->hashCode()I

    move-result v3

    .line 287
    invoke-static {p1, p2}, Lcom/android/deskclock/alarms/AlarmNotifications;->createViewAlarmIntent(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)Landroid/content/Intent;

    move-result-object p2

    const/high16 v4, 0x8000000

    .line 286
    invoke-static {p1, v3, p2, v4}, Landroid/app/PendingIntent;->getActivity(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 290
    new-instance p2, Landroid/app/AlarmManager$AlarmClockInfo;

    invoke-direct {p2, v1, v2, p1}, Landroid/app/AlarmManager$AlarmClockInfo;-><init>(JLandroid/app/PendingIntent;)V

    .line 291
    sget-object p1, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;

    invoke-virtual {p0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p1, v0, p2, p0}, Lcom/android/deskclock/Utils;->updateNextAlarm(Landroid/app/AlarmManager;Landroid/app/AlarmManager$AlarmClockInfo;Landroid/app/PendingIntent;)V

    return-void

    :cond_58
    if-eqz p0, :cond_64

    .line 293
    const-string p1, "Canceling upcoming AlarmClockInfo"

    new-array p2, v1, [Ljava/lang/Object;

    invoke-static {p1, p2}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 294
    invoke-virtual {v0, p0}, Landroid/app/AlarmManager;->cancel(Landroid/app/PendingIntent;)V

    :cond_64
    return-void
.end method

.method private final updateNextAlarmInSystemSettings(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 6

    .line 247
    const-string p0, "\'"

    const-string v0, "Updated next alarm time to: \'"

    if-eqz p2, :cond_f

    .line 249
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object p2

    invoke-static {p1, p2}, Lcom/android/deskclock/AlarmUtils;->getFormattedTime(Landroid/content/Context;Ljava/util/Calendar;)Ljava/lang/String;

    move-result-object p2

    goto :goto_11

    .line 248
    :cond_f
    const-string p2, ""

    .line 254
    :goto_11
    :try_start_11
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v1

    const-string v2, "next_alarm_formatted"

    invoke-static {v1, v2, p2}, Landroid/provider/Settings$System;->putString(Landroid/content/ContentResolver;Ljava/lang/String;Ljava/lang/String;)Z

    .line 255
    new-instance v1, Ljava/lang/StringBuilder;

    invoke-direct {v1, v0}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v1, p2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v0, v1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 258
    new-instance v0, Landroid/content/Intent;

    const-string v1, "com.android.deskclock.ALARM_CHANGED"

    invoke-direct {v0, v1}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    invoke-virtual {p1, v0}, Landroid/content/Context;->sendBroadcast(Landroid/content/Intent;)V
    :try_end_39
    .catch Ljava/lang/SecurityException; {:try_start_11 .. :try_end_39} :catch_3a

    return-void

    :catch_3a
    move-exception p1

    .line 261
    new-instance v0, Ljava/lang/StringBuilder;

    const-string v1, "Unable to update next alarm to: \'"

    invoke-direct {v0, v1}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v0, p2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p0

    invoke-static {p0, p1}, Lcom/android/deskclock/LogUtils;->e(Ljava/lang/String;Ljava/lang/Throwable;)V

    return-void
.end method

.method private final updateParentAlarm(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 10

    .line 306
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 307
    sget-object v1, Lcom/android/deskclock/provider/Alarm;->Companion:Lcom/android/deskclock/provider/Alarm$Companion;

    iget-object v2, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;

    invoke-virtual {v2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {v2}, Ljava/lang/Long;->longValue()J

    move-result-wide v2

    invoke-virtual {v1, v0, v2, v3}, Lcom/android/deskclock/provider/Alarm$Companion;->getAlarm(Landroid/content/ContentResolver;J)Lcom/android/deskclock/provider/Alarm;

    move-result-object v2

    const/4 v3, 0x0

    if-nez v2, :cond_2f

    .line 309
    sget-object p0, Lcom/android/deskclock/LogUtils;->INSTANCE:Lcom/android/deskclock/LogUtils;

    new-instance p1, Ljava/lang/StringBuilder;

    const-string v0, "Parent has been deleted with instance: "

    invoke-direct {p1, v0}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {p1, p2}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {p1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p1

    new-array p2, v3, [Ljava/lang/Object;

    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/LogUtils;->e(Ljava/lang/String;[Ljava/lang/Object;)V

    return-void

    .line 313
    :cond_2f
    iget-object v4, v2, Lcom/android/deskclock/provider/Alarm;->daysOfWeek:Lcom/android/deskclock/data/Weekdays;

    invoke-virtual {v4}, Lcom/android/deskclock/data/Weekdays;->isRepeating()Z

    move-result v4

    if-nez v4, :cond_6f

    .line 314
    iget-boolean p0, v2, Lcom/android/deskclock/provider/Alarm;->deleteAfterUse:Z

    .line 318
    iget-wide p1, v2, Lcom/android/deskclock/provider/Alarm;->id:J

    if-eqz p0, :cond_56

    .line 315
    new-instance p0, Ljava/lang/StringBuilder;

    const-string v4, "Deleting parent alarm: "

    invoke-direct {p0, v4}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {p0, p1, p2}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {p0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p0

    new-array p1, v3, [Ljava/lang/Object;

    invoke-static {p0, p1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 316
    iget-wide p0, v2, Lcom/android/deskclock/provider/Alarm;->id:J

    invoke-virtual {v1, v0, p0, p1}, Lcom/android/deskclock/provider/Alarm$Companion;->deleteAlarm(Landroid/content/ContentResolver;J)Z

    return-void

    .line 318
    :cond_56
    new-instance p0, Ljava/lang/StringBuilder;

    const-string v4, "Disabling parent alarm: "

    invoke-direct {p0, v4}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {p0, p1, p2}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {p0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p0

    new-array p1, v3, [Ljava/lang/Object;

    invoke-static {p0, p1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 319
    iput-boolean v3, v2, Lcom/android/deskclock/provider/Alarm;->enabled:Z

    .line 320
    invoke-virtual {v1, v0, v2}, Lcom/android/deskclock/provider/Alarm$Companion;->updateAlarm(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/Alarm;)Z

    return-void

    .line 326
    :cond_6f
    invoke-direct {p0}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->getCurrentTime()Ljava/util/Calendar;

    move-result-object v1

    invoke-virtual {v2, v1}, Lcom/android/deskclock/provider/Alarm;->createInstanceAfter(Ljava/util/Calendar;)Lcom/android/deskclock/provider/AlarmInstance;

    move-result-object v1

    .line 327
    iget v4, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    const/4 v5, 0x5

    if-le v4, v5, :cond_92

    .line 328
    invoke-virtual {v1}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v4

    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v5

    invoke-static {v4, v5}, Lkotlin/jvm/internal/Intrinsics;->areEqual(Ljava/lang/Object;Ljava/lang/Object;)Z

    move-result v4

    if-eqz v4, :cond_92

    .line 329
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object p2

    invoke-virtual {v2, p2}, Lcom/android/deskclock/provider/Alarm;->createInstanceAfter(Ljava/util/Calendar;)Lcom/android/deskclock/provider/AlarmInstance;

    move-result-object v1

    .line 332
    :cond_92
    iget-wide v4, v2, Lcom/android/deskclock/provider/Alarm;->id:J

    .line 334
    invoke-virtual {v1}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object p2

    invoke-static {p1, p2}, Lcom/android/deskclock/AlarmUtils;->getFormattedTime(Landroid/content/Context;Ljava/util/Calendar;)Ljava/lang/String;

    move-result-object p2

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v6, "Creating new instance for repeating alarm "

    invoke-direct {v2, v6}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v4, v5}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    const-string v4, " at "

    invoke-virtual {v2, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, p2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p2

    new-array v2, v3, [Ljava/lang/Object;

    .line 332
    invoke-static {p2, v2}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 335
    sget-object p2, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {p2, v0, v1}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->addInstance(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/AlarmInstance;)Lcom/android/deskclock/provider/AlarmInstance;

    const/4 p2, 0x1

    .line 336
    invoke-virtual {p0, p1, v1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->registerInstance(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;Z)V

    return-void
.end method


# virtual methods
.method public final createStateChangeIntent(Landroid/content/Context;Ljava/lang/String;Lcom/android/deskclock/provider/AlarmInstance;Ljava/lang/Integer;)Landroid/content/Intent;
    .registers 8

    invoke-virtual {p3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 362
    sget-object p0, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    const-class v0, Lcom/android/deskclock/alarms/AlarmService;

    iget-wide v1, p3, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    invoke-virtual {p0, p1, v0, v1, v2}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->createIntent(Landroid/content/Context;Ljava/lang/Class;J)Landroid/content/Intent;

    move-result-object p0

    .line 363
    const-string p1, "change_state"

    invoke-virtual {p0, p1}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    .line 364
    invoke-virtual {p0, p2}, Landroid/content/Intent;->addCategory(Ljava/lang/String;)Landroid/content/Intent;

    .line 365
    sget-object p1, Lcom/android/deskclock/data/DataModel;->Companion:Lcom/android/deskclock/data/DataModel$Companion;

    invoke-virtual {p1}, Lcom/android/deskclock/data/DataModel$Companion;->getDataModel()Lcom/android/deskclock/data/DataModel;

    move-result-object p1

    invoke-virtual {p1}, Lcom/android/deskclock/data/DataModel;->getGlobalIntentId()I

    move-result p1

    const-string p2, "intent.extra.alarm.global.id"

    invoke-virtual {p0, p2, p1}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    if-eqz p4, :cond_2f

    .line 367
    const-string p1, "intent.extra.alarm.state"

    invoke-virtual {p4}, Ljava/lang/Integer;->intValue()I

    move-result p2

    invoke-virtual {p0, p1, p2}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    :cond_2f
    return-object p0
.end method

.method public final deleteAllInstances(Landroid/content/Context;J)V
    .registers 8

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 820
    new-instance v0, Ljava/lang/StringBuilder;

    const-string v1, "Deleting all instances of alarm: "

    invoke-direct {v0, v1}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v0, p2, p3}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v0, v1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 821
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 822
    sget-object v1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {v1, v0, p2, p3}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getInstancesByAlarmId(Landroid/content/ContentResolver;J)Ljava/util/List;

    move-result-object p2

    .line 823
    invoke-interface {p2}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object p2

    :goto_28
    invoke-interface {p2}, Ljava/util/Iterator;->hasNext()Z

    move-result p3

    if-eqz p3, :cond_46

    invoke-interface {p2}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object p3

    check-cast p3, Lcom/android/deskclock/provider/AlarmInstance;

    .line 824
    invoke-virtual {p0, p1, p3}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->unregisterInstance(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 825
    sget-object v0, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    iget-wide v2, p3, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    invoke-virtual {v0, v1, v2, v3}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->deleteInstance(Landroid/content/ContentResolver;J)Z

    goto :goto_28

    .line 827
    :cond_46
    invoke-direct {p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateNextAlarm(Landroid/content/Context;)V

    return-void
.end method

.method public final deleteInstanceAndUpdateParent(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 7

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 655
    iget-wide v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "Deleting instance "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    const-string v0, " and updating parent alarm."

    invoke-virtual {v2, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v0, v1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 658
    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->unregisterInstance(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 661
    iget-object v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;

    if-eqz v0, :cond_2b

    .line 662
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateParentAlarm(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 666
    :cond_2b
    sget-object v0, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    iget-wide v2, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    invoke-virtual {v0, v1, v2, v3}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->deleteInstance(Landroid/content/ContentResolver;J)Z

    .line 669
    invoke-direct {p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateNextAlarm(Landroid/content/Context;)V

    return-void
.end method

.method public final fixAlarmInstances(Landroid/content/Context;)V
    .registers 10

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/4 v0, 0x0

    .line 855
    new-array v1, v0, [Ljava/lang/Object;

    const-string v2, "Fixing alarm instances"

    invoke-static {v2, v1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 857
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 858
    invoke-direct {p0}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->getCurrentTime()Ljava/util/Calendar;

    move-result-object v2

    .line 863
    sget-object v3, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    const/4 v4, 0x0

    .line 864
    new-array v5, v0, [Ljava/lang/String;

    .line 863
    invoke-virtual {v3, v1, v4, v5}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getInstances(Landroid/content/ContentResolver;Ljava/lang/String;[Ljava/lang/String;)Ljava/util/List;

    move-result-object v3

    .line 865
    sget-object v4, Lcom/android/deskclock/alarms/AlarmStateManager$Companion$fixAlarmInstances$1;->INSTANCE:Lcom/android/deskclock/alarms/AlarmStateManager$Companion$fixAlarmInstances$1;

    invoke-static {v3, v4}, Lkotlin/collections/CollectionsKt;->sortWith(Ljava/util/List;Ljava/util/Comparator;)V

    .line 867
    invoke-interface {v3}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v3

    :goto_28
    invoke-interface {v3}, Ljava/util/Iterator;->hasNext()Z

    move-result v4

    if-eqz v4, :cond_9d

    invoke-interface {v3}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v4

    check-cast v4, Lcom/android/deskclock/provider/AlarmInstance;

    .line 868
    sget-object v5, Lcom/android/deskclock/provider/Alarm;->Companion:Lcom/android/deskclock/provider/Alarm$Companion;

    iget-object v6, v4, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;

    invoke-virtual {v6}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {v6}, Ljava/lang/Long;->longValue()J

    move-result-wide v6

    invoke-virtual {v5, v1, v6, v7}, Lcom/android/deskclock/provider/Alarm$Companion;->getAlarm(Landroid/content/ContentResolver;J)Lcom/android/deskclock/provider/Alarm;

    move-result-object v5

    if-nez v5, :cond_5b

    .line 870
    invoke-virtual {p0, p1, v4}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->unregisterInstance(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 871
    sget-object v5, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    iget-wide v6, v4, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    invoke-virtual {v5, v1, v6, v7}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->deleteInstance(Landroid/content/ContentResolver;J)Z

    .line 872
    sget-object v5, Lcom/android/deskclock/LogUtils;->INSTANCE:Lcom/android/deskclock/LogUtils;

    const-string v6, "Found instance without matching alarm; deleting instance %s"

    .line 873
    filled-new-array {v4}, [Ljava/lang/Object;

    move-result-object v4

    .line 872
    invoke-virtual {v5, v6, v4}, Lcom/android/deskclock/LogUtils;->e(Ljava/lang/String;[Ljava/lang/Object;)V

    goto :goto_28

    .line 876
    :cond_5b
    invoke-virtual {v4}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v6

    invoke-virtual {v5, v6}, Lcom/android/deskclock/provider/Alarm;->getPreviousAlarmTime(Ljava/util/Calendar;)Ljava/util/Calendar;

    move-result-object v6

    .line 877
    invoke-virtual {v4}, Lcom/android/deskclock/provider/AlarmInstance;->getMissedTimeToLive()Ljava/util/Calendar;

    move-result-object v7

    .line 878
    invoke-virtual {v2, v6}, Ljava/util/Calendar;->before(Ljava/lang/Object;)Z

    move-result v6

    if-nez v6, :cond_78

    invoke-virtual {v2, v7}, Ljava/util/Calendar;->after(Ljava/lang/Object;)Z

    move-result v6

    if-eqz v6, :cond_74

    goto :goto_78

    .line 893
    :cond_74
    invoke-virtual {p0, p1, v4, v0}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->registerInstance(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;Z)V

    goto :goto_28

    .line 879
    :cond_78
    :goto_78
    invoke-virtual {v4}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v6

    .line 880
    invoke-virtual {v5, v2}, Lcom/android/deskclock/provider/Alarm;->getNextAlarmTime(Ljava/util/Calendar;)Ljava/util/Calendar;

    move-result-object v5

    .line 882
    const-string v7, "MM/dd/yyyy hh:mm a"

    invoke-static {v7, v6}, Landroid/text/format/DateFormat;->format(Ljava/lang/CharSequence;Ljava/util/Calendar;)Ljava/lang/CharSequence;

    move-result-object v6

    invoke-virtual {v6}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 884
    invoke-static {v7, v5}, Landroid/text/format/DateFormat;->format(Ljava/lang/CharSequence;Ljava/util/Calendar;)Ljava/lang/CharSequence;

    move-result-object v5

    invoke-virtual {v5}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 885
    const-string v7, "A time change has caused an existing alarm scheduled to fire at %s to be replaced by a new alarm scheduled to fire at %s"

    .line 887
    filled-new-array {v6, v5}, [Ljava/lang/Object;

    move-result-object v5

    .line 885
    invoke-static {v7, v5}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 891
    invoke-virtual {p0, p1, v4}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->deleteInstanceAndUpdateParent(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    goto :goto_28

    .line 897
    :cond_9d
    invoke-direct {p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateNextAlarm(Landroid/content/Context;)V

    return-void
.end method

.method public final getNextFiringAlarm(Landroid/content/Context;)Lcom/android/deskclock/provider/AlarmInstance;
    .registers 5

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 227
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object p0

    invoke-virtual {p0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 230
    sget-object p1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    const/4 v0, 0x0

    new-array v0, v0, [Ljava/lang/String;

    const-string v1, "alarm_state<5"

    invoke-virtual {p1, p0, v1, v0}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getInstances(Landroid/content/ContentResolver;Ljava/lang/String;[Ljava/lang/String;)Ljava/util/List;

    move-result-object p0

    .line 233
    invoke-interface {p0}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object p0

    const/4 p1, 0x0

    :cond_1a
    :goto_1a
    invoke-interface {p0}, Ljava/util/Iterator;->hasNext()Z

    move-result v0

    if-eqz v0, :cond_38

    invoke-interface {p0}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Lcom/android/deskclock/provider/AlarmInstance;

    if-eqz p1, :cond_36

    .line 234
    invoke-virtual {v0}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v1

    invoke-virtual {p1}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v2

    invoke-virtual {v1, v2}, Ljava/util/Calendar;->before(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_1a

    :cond_36
    move-object p1, v0

    goto :goto_1a

    :cond_38
    return-object p1
.end method

.method public final handleIntent(Landroid/content/Context;Landroid/content/Intent;)V
    .registers 12

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 935
    invoke-virtual {p2}, Landroid/content/Intent;->getAction()Ljava/lang/String;

    move-result-object v0

    .line 936
    new-instance v1, Ljava/lang/StringBuilder;

    const-string v2, "AlarmStateManager received intent "

    invoke-direct {v1, v2}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v1, p2}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    const/4 v2, 0x0

    new-array v3, v2, [Ljava/lang/Object;

    invoke-static {v1, v3}, Lcom/android/deskclock/LogUtils;->v(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 937
    const-string v1, "change_state"

    invoke-static {v1, v0}, Lkotlin/jvm/internal/Intrinsics;->areEqual(Ljava/lang/Object;Ljava/lang/Object;)Z

    move-result v1

    const/4 v3, -0x1

    if-eqz v1, :cond_d9

    .line 938
    invoke-virtual {p2}, Landroid/content/Intent;->getData()Landroid/net/Uri;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 940
    sget-object v1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 941
    invoke-virtual {v1, v0}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getId(Landroid/net/Uri;)J

    move-result-wide v5

    .line 940
    invoke-virtual {v1, v4, v5, v6}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getInstance(Landroid/content/ContentResolver;J)Lcom/android/deskclock/provider/AlarmInstance;

    move-result-object v1

    if-nez v1, :cond_57

    .line 943
    sget-object p0, Lcom/android/deskclock/LogUtils;->INSTANCE:Lcom/android/deskclock/LogUtils;

    new-instance p1, Ljava/lang/StringBuilder;

    const-string p2, "Can not change state for unknown instance: "

    invoke-direct {p1, p2}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {p1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {p1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p1

    new-array p2, v2, [Ljava/lang/Object;

    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/LogUtils;->e(Ljava/lang/String;[Ljava/lang/Object;)V

    return-void

    .line 947
    :cond_57
    sget-object v0, Lcom/android/deskclock/data/DataModel;->Companion:Lcom/android/deskclock/data/DataModel$Companion;

    invoke-virtual {v0}, Lcom/android/deskclock/data/DataModel$Companion;->getDataModel()Lcom/android/deskclock/data/DataModel;

    move-result-object v0

    invoke-virtual {v0}, Lcom/android/deskclock/data/DataModel;->getGlobalIntentId()I

    move-result v0

    .line 948
    const-string v4, "intent.extra.alarm.global.id"

    invoke-virtual {p2, v4, v3}, Landroid/content/Intent;->getIntExtra(Ljava/lang/String;I)I

    move-result v4

    .line 949
    const-string v5, "intent.extra.alarm.state"

    invoke-virtual {p2, v5, v3}, Landroid/content/Intent;->getIntExtra(Ljava/lang/String;I)I

    move-result v3

    .line 950
    const-string v5, "SNOOZE_TAG"

    const-string v6, "DISMISS_TAG"

    if-eq v4, v0, :cond_aa

    .line 952
    new-instance v7, Ljava/lang/StringBuilder;

    const-string v8, "IntentId: "

    invoke-direct {v7, v8}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v7, v4}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    const-string v4, " GlobalId: "

    invoke-virtual {v7, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v7, v0}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    const-string v0, " AlarmState: "

    invoke-virtual {v7, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v7, v3}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    invoke-virtual {v7}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    new-array v4, v2, [Ljava/lang/Object;

    .line 951
    invoke-static {v0, v4}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 954
    invoke-virtual {p2, v6}, Landroid/content/Intent;->hasCategory(Ljava/lang/String;)Z

    move-result v0

    if-nez v0, :cond_aa

    .line 955
    invoke-virtual {p2, v5}, Landroid/content/Intent;->hasCategory(Ljava/lang/String;)Z

    move-result v0

    if-nez v0, :cond_aa

    .line 956
    const-string p0, "Ignoring old Intent"

    new-array p1, v2, [Ljava/lang/Object;

    invoke-static {p0, p1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    return-void

    .line 961
    :cond_aa
    const-string v0, "intent.extra.from.notification"

    invoke-virtual {p2, v0, v2}, Landroid/content/Intent;->getBooleanExtra(Ljava/lang/String;Z)Z

    move-result v0

    if-eqz v0, :cond_ce

    .line 962
    invoke-virtual {p2, v6}, Landroid/content/Intent;->hasCategory(Ljava/lang/String;)Z

    move-result v0

    const v2, 0x7f120201

    if-eqz v0, :cond_c2

    const p2, 0x7f120177

    .line 963
    invoke-static {p2, v2}, Lcom/android/deskclock/events/Events;->sendAlarmEvent(II)V

    goto :goto_ce

    .line 964
    :cond_c2
    invoke-virtual {p2, v5}, Landroid/content/Intent;->hasCategory(Ljava/lang/String;)Z

    move-result p2

    if-eqz p2, :cond_ce

    const p2, 0x7f120184

    .line 965
    invoke-static {p2, v2}, Lcom/android/deskclock/events/Events;->sendAlarmEvent(II)V

    :cond_ce
    :goto_ce
    if-ltz v3, :cond_d4

    .line 970
    invoke-direct {p0, p1, v1, v3}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setAlarmState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;I)V

    return-void

    :cond_d4
    const/4 p2, 0x1

    .line 972
    invoke-virtual {p0, p1, v1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->registerInstance(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;Z)V

    return-void

    .line 974
    :cond_d9
    const-string v1, "show_and_dismiss_alarm"

    invoke-static {v1, v0}, Lkotlin/jvm/internal/Intrinsics;->areEqual(Ljava/lang/Object;Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_13c

    .line 975
    invoke-virtual {p2}, Landroid/content/Intent;->getData()Landroid/net/Uri;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 977
    sget-object v1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 978
    invoke-virtual {v1, v0}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getId(Landroid/net/Uri;)J

    move-result-wide v5

    .line 977
    invoke-virtual {v1, v4, v5, v6}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getInstance(Landroid/content/ContentResolver;J)Lcom/android/deskclock/provider/AlarmInstance;

    move-result-object v0

    if-nez v0, :cond_114

    .line 981
    sget-object p0, Lcom/android/deskclock/LogUtils;->INSTANCE:Lcom/android/deskclock/LogUtils;

    const-string v0, "Null alarminstance for SHOW_AND_DISMISS"

    new-array v1, v2, [Ljava/lang/Object;

    invoke-virtual {p0, v0, v1}, Lcom/android/deskclock/LogUtils;->e(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 983
    const-string p0, "extra_notification_id"

    invoke-virtual {p2, p0, v3}, Landroid/content/Intent;->getIntExtra(Ljava/lang/String;I)I

    move-result p0

    if-eq p0, v3, :cond_13c

    .line 985
    invoke-static {p1}, Landroidx/core/app/NotificationManagerCompat;->from(Landroid/content/Context;)Landroidx/core/app/NotificationManagerCompat;

    move-result-object p1

    invoke-virtual {p1, p0}, Landroidx/core/app/NotificationManagerCompat;->cancel(I)V

    return-void

    .line 990
    :cond_114
    iget-object p2, v0, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;

    if-eqz p2, :cond_11d

    invoke-virtual {p2}, Ljava/lang/Long;->longValue()J

    move-result-wide v1

    goto :goto_11f

    :cond_11d
    const-wide/16 v1, -0x1

    .line 992
    :goto_11f
    sget-object p2, Lcom/android/deskclock/provider/Alarm;->Companion:Lcom/android/deskclock/provider/Alarm$Companion;

    const-class v3, Lcom/android/deskclock/DeskClock;

    invoke-virtual {p2, p1, v3, v1, v2}, Lcom/android/deskclock/provider/Alarm$Companion;->createIntent(Landroid/content/Context;Ljava/lang/Class;J)Landroid/content/Intent;

    move-result-object p2

    .line 993
    const-string v3, "deskclock.scroll.to.alarm"

    invoke-virtual {p2, v3, v1, v2}, Landroid/content/Intent;->putExtra(Ljava/lang/String;J)Landroid/content/Intent;

    move-result-object p2

    const/high16 v1, 0x10000000

    .line 994
    invoke-virtual {p2, v1}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    move-result-object p2

    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 997
    invoke-virtual {p1, p2}, Landroid/content/Context;->startActivity(Landroid/content/Intent;)V

    .line 999
    invoke-virtual {p0, p1, v0}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->deleteInstanceAndUpdateParent(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    :cond_13c
    return-void
.end method

.method public final registerInstance(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;Z)V
    .registers 16

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 718
    iget-wide v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "Registering instance: "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v2, v1, [Ljava/lang/Object;

    invoke-static {v0, v2}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 719
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 720
    sget-object v2, Lcom/android/deskclock/provider/Alarm;->Companion:Lcom/android/deskclock/provider/Alarm$Companion;

    iget-object v3, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;

    invoke-virtual {v3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {v3}, Ljava/lang/Long;->longValue()J

    move-result-wide v3

    invoke-virtual {v2, v0, v3, v4}, Lcom/android/deskclock/provider/Alarm$Companion;->getAlarm(Landroid/content/ContentResolver;J)Lcom/android/deskclock/provider/Alarm;

    move-result-object v3

    .line 721
    invoke-direct {p0}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->getCurrentTime()Ljava/util/Calendar;

    move-result-object v4

    .line 722
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v5

    .line 723
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getTimeout()Ljava/util/Calendar;

    move-result-object v6

    .line 724
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getLowNotificationTime()Ljava/util/Calendar;

    move-result-object v7

    .line 725
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getHighNotificationTime()Ljava/util/Calendar;

    move-result-object v8

    .line 726
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getMissedTimeToLive()Ljava/util/Calendar;

    move-result-object v9

    .line 729
    iget v10, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    const/4 v11, 0x7

    if-ne v10, v11, :cond_5c

    .line 731
    sget-object p3, Lcom/android/deskclock/LogUtils;->INSTANCE:Lcom/android/deskclock/LogUtils;

    const-string v0, "Alarm Instance is dismissed, but never deleted"

    new-array v1, v1, [Ljava/lang/Object;

    invoke-virtual {p3, v0, v1}, Lcom/android/deskclock/LogUtils;->e(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 732
    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->deleteInstanceAndUpdateParent(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    :cond_5c
    const/4 v11, 0x5

    if-ne v10, v11, :cond_6c

    if-eqz v6, :cond_68

    .line 736
    invoke-virtual {v4, v6}, Ljava/util/Calendar;->after(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_68

    goto :goto_a0

    .line 738
    :cond_68
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setFiredState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    :cond_6c
    const/4 v6, 0x6

    if-ne v10, v6, :cond_8e

    .line 742
    invoke-virtual {v4, v5}, Ljava/util/Calendar;->before(Ljava/lang/Object;)Z

    move-result v6

    if-eqz v6, :cond_a0

    .line 743
    iget-object v6, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;

    if-nez v6, :cond_84

    .line 744
    const-string p3, "Cannot restore missed instance for one-time alarm"

    new-array v0, v1, [Ljava/lang/Object;

    invoke-static {p3, v0}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 747
    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->deleteInstanceAndUpdateParent(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    .line 757
    :cond_84
    invoke-virtual {v3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/4 v1, 0x1

    iput-boolean v1, v3, Lcom/android/deskclock/provider/Alarm;->enabled:Z

    .line 758
    invoke-virtual {v2, v0, v3}, Lcom/android/deskclock/provider/Alarm$Companion;->updateAlarm(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/Alarm;)Z

    goto :goto_a0

    :cond_8e
    const/16 v0, 0x8

    if-ne v10, v0, :cond_a0

    .line 761
    invoke-virtual {v4, v5}, Ljava/util/Calendar;->before(Ljava/lang/Object;)Z

    move-result p3

    if-eqz p3, :cond_9c

    .line 762
    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setPreDismissState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    .line 764
    :cond_9c
    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->deleteInstanceAndUpdateParent(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void

    .line 770
    :cond_a0
    :goto_a0
    invoke-virtual {v4, v9}, Ljava/util/Calendar;->after(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_aa

    .line 772
    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->deleteInstanceAndUpdateParent(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    goto :goto_100

    .line 773
    :cond_aa
    invoke-virtual {v4, v5}, Ljava/util/Calendar;->after(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_d0

    .line 777
    invoke-static {}, Ljava/util/Calendar;->getInstance()Ljava/util/Calendar;

    move-result-object v0

    .line 778
    invoke-virtual {v5}, Ljava/util/Calendar;->getTime()Ljava/util/Date;

    move-result-object v1

    invoke-virtual {v0, v1}, Ljava/util/Calendar;->setTime(Ljava/util/Date;)V

    const/16 v1, 0xd

    const/16 v2, 0xf

    .line 779
    invoke-virtual {v0, v1, v2}, Ljava/util/Calendar;->add(II)V

    .line 780
    invoke-virtual {v4, v0}, Ljava/util/Calendar;->before(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_cc

    .line 781
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setFiredState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    goto :goto_100

    .line 783
    :cond_cc
    invoke-virtual {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setMissedState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    goto :goto_100

    .line 785
    :cond_d0
    iget v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    const/4 v1, 0x4

    if-ne v0, v1, :cond_e0

    .line 788
    invoke-static {p1, p2}, Lcom/android/deskclock/alarms/AlarmNotifications;->showSnoozeNotification(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 789
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v0

    invoke-direct {p0, p1, v0, p2, v11}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V

    goto :goto_100

    .line 791
    :cond_e0
    invoke-virtual {v4, v8}, Ljava/util/Calendar;->after(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_ea

    .line 792
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setHighNotificationState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    goto :goto_100

    .line 793
    :cond_ea
    invoke-virtual {v4, v7}, Ljava/util/Calendar;->after(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_fd

    .line 795
    iget v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    const/4 v1, 0x2

    if-ne v0, v1, :cond_f9

    .line 796
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setHideNotificationState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    goto :goto_100

    .line 798
    :cond_f9
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setLowNotificationState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    goto :goto_100

    .line 802
    :cond_fd
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setSilentState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    :goto_100
    if-eqz p3, :cond_105

    .line 807
    invoke-direct {p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateNextAlarm(Landroid/content/Context;)V

    :cond_105
    return-void
.end method

.method public final setMissedState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 7

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 584
    iget-wide v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "Setting missed state to instance "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v0, v1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 586
    sget-object v0, Lcom/android/deskclock/alarms/AlarmService;->Companion:Lcom/android/deskclock/alarms/AlarmService$Companion;

    invoke-virtual {v0, p1, p2}, Lcom/android/deskclock/alarms/AlarmService$Companion;->stopAlarm(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 589
    iget-object v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;

    if-eqz v0, :cond_28

    .line 590
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateParentAlarm(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 594
    :cond_28
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/4 v1, 0x6

    .line 595
    iput v1, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    .line 596
    sget-object v1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {v1, v0, p2}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->updateInstance(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/AlarmInstance;)Z

    .line 599
    invoke-static {p1, p2}, Lcom/android/deskclock/alarms/AlarmNotifications;->showMissedNotification(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 600
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getMissedTimeToLive()Ljava/util/Calendar;

    move-result-object v0

    const/4 v1, 0x7

    invoke-direct {p0, p1, v0, p2, v1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V

    .line 604
    invoke-direct {p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateNextAlarm(Landroid/content/Context;)V

    return-void
.end method

.method public final setPreDismissState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 7

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 616
    iget-wide v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "Setting predismissed state to instance "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v0, v1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 619
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/16 v1, 0x8

    .line 620
    iput v1, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    .line 621
    sget-object v1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {v1, v0, p2}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->updateInstance(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/AlarmInstance;)Z

    .line 624
    invoke-static {p1, p2}, Lcom/android/deskclock/alarms/AlarmNotifications;->clearNotification(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 625
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v0

    const/4 v1, 0x7

    invoke-direct {p0, p1, v0, p2, v1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V

    .line 629
    iget-object v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmId:Ljava/lang/Long;

    if-eqz v0, :cond_3e

    .line 630
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateParentAlarm(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 633
    :cond_3e
    invoke-direct {p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateNextAlarm(Landroid/content/Context;)V

    return-void
.end method

.method public final setSnoozeState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;Z)V
    .registers 11

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 535
    sget-object v0, Lcom/android/deskclock/alarms/AlarmService;->Companion:Lcom/android/deskclock/alarms/AlarmService$Companion;

    invoke-virtual {v0, p1, p2}, Lcom/android/deskclock/alarms/AlarmService$Companion;->stopAlarm(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 538
    sget-object v0, Lcom/android/deskclock/data/DataModel;->Companion:Lcom/android/deskclock/data/DataModel$Companion;

    invoke-virtual {v0}, Lcom/android/deskclock/data/DataModel$Companion;->getDataModel()Lcom/android/deskclock/data/DataModel;

    move-result-object v0

    invoke-virtual {v0}, Lcom/android/deskclock/data/DataModel;->getSnoozeLength()I

    move-result v0

    .line 539
    invoke-static {}, Ljava/util/Calendar;->getInstance()Ljava/util/Calendar;

    move-result-object v1

    const/16 v2, 0xc

    .line 540
    invoke-virtual {v1, v2, v0}, Ljava/util/Calendar;->add(II)V

    .line 543
    iget-wide v2, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    .line 544
    invoke-static {p1, v1}, Lcom/android/deskclock/AlarmUtils;->getFormattedTime(Landroid/content/Context;Ljava/util/Calendar;)Ljava/lang/String;

    move-result-object v4

    new-instance v5, Ljava/lang/StringBuilder;

    const-string v6, "Setting snoozed state to instance "

    invoke-direct {v5, v6}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v5, v2, v3}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    const-string v2, " for "

    invoke-virtual {v5, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v5, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v5}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    const/4 v3, 0x0

    new-array v3, v3, [Ljava/lang/Object;

    .line 543
    invoke-static {v2, v3}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 545
    invoke-virtual {p2, v1}, Lcom/android/deskclock/provider/AlarmInstance;->setAlarmTime(Ljava/util/Calendar;)V

    const/4 v1, 0x4

    .line 546
    iput v1, p2, Lcom/android/deskclock/provider/AlarmInstance;->mAlarmState:I

    .line 547
    sget-object v1, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {v1, v2, p2}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->updateInstance(Landroid/content/ContentResolver;Lcom/android/deskclock/provider/AlarmInstance;)Z

    .line 550
    invoke-static {p1, p2}, Lcom/android/deskclock/alarms/AlarmNotifications;->showSnoozeNotification(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 551
    invoke-virtual {p2}, Lcom/android/deskclock/provider/AlarmInstance;->getAlarmTime()Ljava/util/Calendar;

    move-result-object v1

    const/4 v2, 0x5

    invoke-direct {p0, p1, v1, p2, v2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V

    if-eqz p3, :cond_70

    .line 556
    new-instance p2, Landroid/os/Handler;

    invoke-virtual {p1}, Landroid/content/Context;->getMainLooper()Landroid/os/Looper;

    move-result-object p3

    invoke-direct {p2, p3}, Landroid/os/Handler;-><init>(Landroid/os/Looper;)V

    .line 557
    new-instance p3, Lcom/android/deskclock/alarms/AlarmStateManager$Companion$setSnoozeState$myRunnable$1;

    invoke-direct {p3, p1, v0}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion$setSnoozeState$myRunnable$1;-><init>(Landroid/content/Context;I)V

    .line 568
    invoke-virtual {p2, p3}, Landroid/os/Handler;->post(Ljava/lang/Runnable;)Z

    .line 572
    :cond_70
    invoke-direct {p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->updateNextAlarm(Landroid/content/Context;)V

    return-void
.end method

.method public final unregisterInstance(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 7

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 680
    iget-wide v0, p2, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "Unregistering instance "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v0, v1}, Lcom/android/deskclock/LogUtils;->i(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 682
    sget-object v0, Lcom/android/deskclock/alarms/AlarmService;->Companion:Lcom/android/deskclock/alarms/AlarmService$Companion;

    invoke-virtual {v0, p1, p2}, Lcom/android/deskclock/alarms/AlarmService$Companion;->stopAlarm(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 683
    invoke-static {p1, p2}, Lcom/android/deskclock/alarms/AlarmNotifications;->clearNotification(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 684
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->cancelScheduledInstanceStateChange(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 685
    invoke-direct {p0, p1, p2}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setDismissState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    return-void
.end method
