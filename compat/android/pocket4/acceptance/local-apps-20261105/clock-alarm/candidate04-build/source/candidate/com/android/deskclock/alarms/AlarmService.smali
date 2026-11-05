.class public final Lcom/android/deskclock/alarms/AlarmService;
.super Landroid/app/Service;
.source "AlarmService.kt"


# static fields
.field public static final Companion:Lcom/android/deskclock/alarms/AlarmService$Companion;


# instance fields
.field private final mActionsReceiver:Landroid/content/BroadcastReceiver;

.field private final mBinder:Landroid/os/IBinder;

.field private mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

.field private mIsBound:Z

.field private mIsRegistered:Z

.field private final mPhoneStateListener:Lcom/android/deskclock/alarms/AlarmService$PhoneStateChangeListener;

.field private mTelephonyManager:Landroid/telephony/TelephonyManager;


# direct methods
.method static constructor <clinit>()V
    .registers 2

    new-instance v0, Lcom/android/deskclock/alarms/AlarmService$Companion;

    const/4 v1, 0x0

    invoke-direct {v0, v1}, Lcom/android/deskclock/alarms/AlarmService$Companion;-><init>(Lkotlin/jvm/internal/DefaultConstructorMarker;)V

    sput-object v0, Lcom/android/deskclock/alarms/AlarmService;->Companion:Lcom/android/deskclock/alarms/AlarmService$Companion;

    return-void
.end method

.method public constructor <init>()V
    .registers 2

    .line 44
    invoke-direct {p0}, Landroid/app/Service;-><init>()V

    .line 46
    new-instance v0, Landroid/os/Binder;

    invoke-direct {v0}, Landroid/os/Binder;-><init>()V

    iput-object v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mBinder:Landroid/os/IBinder;

    .line 52
    new-instance v0, Lcom/android/deskclock/alarms/AlarmService$PhoneStateChangeListener;

    invoke-direct {v0, p0}, Lcom/android/deskclock/alarms/AlarmService$PhoneStateChangeListener;-><init>(Lcom/android/deskclock/alarms/AlarmService;)V

    iput-object v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mPhoneStateListener:Lcom/android/deskclock/alarms/AlarmService$PhoneStateChangeListener;

    .line 105
    new-instance v0, Lcom/android/deskclock/alarms/AlarmService$mActionsReceiver$1;

    invoke-direct {v0, p0}, Lcom/android/deskclock/alarms/AlarmService$mActionsReceiver$1;-><init>(Lcom/android/deskclock/alarms/AlarmService;)V

    iput-object v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mActionsReceiver:Landroid/content/BroadcastReceiver;

    return-void
.end method

.method public static final synthetic access$getMCurrentAlarm$p(Lcom/android/deskclock/alarms/AlarmService;)Lcom/android/deskclock/provider/AlarmInstance;
    .registers 1

    .line 44
    iget-object p0, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

    return-object p0
.end method

.method public static final synthetic access$getMIsBound$p(Lcom/android/deskclock/alarms/AlarmService;)Z
    .registers 1

    .line 44
    iget-boolean p0, p0, Lcom/android/deskclock/alarms/AlarmService;->mIsBound:Z

    return p0
.end method

.method private final startAlarm(Lcom/android/deskclock/provider/AlarmInstance;)V
    .registers 6

    .line 71
    iget-wide v0, p1, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "AlarmService.start with instance: "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0, v1}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v0, v1}, Lcom/android/deskclock/LogUtils;->v(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 72
    iget-object v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

    if-eqz v0, :cond_25

    .line 73
    sget-object v1, Lcom/android/deskclock/alarms/AlarmStateManager;->Companion:Lcom/android/deskclock/alarms/AlarmStateManager$Companion;

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {v1, p0, v0}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->setMissedState(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 74
    invoke-direct {p0}, Lcom/android/deskclock/alarms/AlarmService;->stopCurrentAlarm()V

    .line 77
    :cond_25
    invoke-static {p0}, Lcom/android/deskclock/AlarmAlertWakeLock;->acquireCpuWakeLock(Landroid/content/Context;)V

    .line 79
    iput-object p1, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

    .line 80
    sget-object v0, Lcom/android/deskclock/alarms/AlarmNotifications;->INSTANCE:Lcom/android/deskclock/alarms/AlarmNotifications;

    invoke-virtual {v0, p0, p1}, Lcom/android/deskclock/alarms/AlarmNotifications;->showAlarmNotification(Landroid/app/Service;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 81
    iget-object p1, p0, Lcom/android/deskclock/alarms/AlarmService;->mTelephonyManager:Landroid/telephony/TelephonyManager;

    if-nez p1, :cond_39

    const-string p1, "mTelephonyManager"

    invoke-static {p1}, Lkotlin/jvm/internal/Intrinsics;->throwUninitializedPropertyAccessException(Ljava/lang/String;)V

    const/4 p1, 0x0

    :cond_39
    iget-object v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mPhoneStateListener:Lcom/android/deskclock/alarms/AlarmService$PhoneStateChangeListener;

    invoke-virtual {v0}, Lcom/android/deskclock/alarms/AlarmService$PhoneStateChangeListener;->init()Lcom/android/deskclock/alarms/AlarmService$PhoneStateChangeListener;

    move-result-object v0

    const/16 v1, 0x20

    invoke-virtual {p1, v0, v1}, Landroid/telephony/TelephonyManager;->listen(Landroid/telephony/PhoneStateListener;I)V

    .line 82
    iget-object p1, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-static {p0, p1}, Lcom/android/deskclock/alarms/AlarmKlaxon;->start(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V

    .line 83
    new-instance p1, Landroid/content/Intent;

    const-string v0, "com.android.deskclock.ALARM_ALERT"

    invoke-direct {p1, v0}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    invoke-virtual {p0, p1}, Landroid/app/Service;->sendBroadcast(Landroid/content/Intent;)V

    return-void
.end method

.method private final stopCurrentAlarm()V
    .registers 5

    .line 87
    iget-object v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

    const/4 v1, 0x0

    if-nez v0, :cond_d

    .line 88
    const-string p0, "There is no current alarm to stop"

    new-array v0, v1, [Ljava/lang/Object;

    invoke-static {p0, v0}, Lcom/android/deskclock/LogUtils;->v(Ljava/lang/String;[Ljava/lang/Object;)V

    return-void

    .line 92
    :cond_d
    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    iget-wide v2, v0, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    .line 93
    invoke-static {v2, v3}, Ljava/lang/Long;->valueOf(J)Ljava/lang/Long;

    move-result-object v0

    filled-new-array {v0}, [Ljava/lang/Object;

    move-result-object v0

    const-string v2, "AlarmService.stop with instance: %s"

    invoke-static {v2, v0}, Lcom/android/deskclock/LogUtils;->v(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 95
    invoke-static {p0}, Lcom/android/deskclock/alarms/AlarmKlaxon;->stop(Landroid/content/Context;)V

    .line 96
    iget-object v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mTelephonyManager:Landroid/telephony/TelephonyManager;

    const/4 v2, 0x0

    if-nez v0, :cond_2d

    const-string v0, "mTelephonyManager"

    invoke-static {v0}, Lkotlin/jvm/internal/Intrinsics;->throwUninitializedPropertyAccessException(Ljava/lang/String;)V

    move-object v0, v2

    :cond_2d
    iget-object v3, p0, Lcom/android/deskclock/alarms/AlarmService;->mPhoneStateListener:Lcom/android/deskclock/alarms/AlarmService$PhoneStateChangeListener;

    invoke-virtual {v0, v3, v1}, Landroid/telephony/TelephonyManager;->listen(Landroid/telephony/PhoneStateListener;I)V

    .line 97
    new-instance v0, Landroid/content/Intent;

    const-string v1, "com.android.deskclock.ALARM_DONE"

    invoke-direct {v0, v1}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    invoke-virtual {p0, v0}, Landroid/app/Service;->sendBroadcast(Landroid/content/Intent;)V

    const/4 v0, 0x1

    .line 99
    invoke-virtual {p0, v0}, Landroid/app/Service;->stopForeground(Z)V

    .line 101
    iput-object v2, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

    .line 102
    invoke-static {}, Lcom/android/deskclock/AlarmAlertWakeLock;->releaseCpuLock()V

    return-void
.end method


# virtual methods
.method public onBind(Landroid/content/Intent;)Landroid/os/IBinder;
    .registers 2

    const/4 p1, 0x1

    .line 58
    iput-boolean p1, p0, Lcom/android/deskclock/alarms/AlarmService;->mIsBound:Z

    .line 59
    iget-object p0, p0, Lcom/android/deskclock/alarms/AlarmService;->mBinder:Landroid/os/IBinder;

    return-object p0
.end method

.method public onCreate()V
    .registers 4

    .line 138
    invoke-super {p0}, Landroid/app/Service;->onCreate()V

    .line 139
    const-string v0, "phone"

    invoke-virtual {p0, v0}, Landroid/app/Service;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    check-cast v0, Landroid/telephony/TelephonyManager;

    iput-object v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mTelephonyManager:Landroid/telephony/TelephonyManager;

    .line 142
    new-instance v0, Landroid/content/IntentFilter;

    const-string v1, "com.android.deskclock.ALARM_SNOOZE"

    invoke-direct {v0, v1}, Landroid/content/IntentFilter;-><init>(Ljava/lang/String;)V

    .line 143
    const-string v1, "com.android.deskclock.ALARM_DISMISS"

    invoke-virtual {v0, v1}, Landroid/content/IntentFilter;->addAction(Ljava/lang/String;)V

    .line 144
    iget-object v1, p0, Lcom/android/deskclock/alarms/AlarmService;->mActionsReceiver:Landroid/content/BroadcastReceiver;

    const/4 v2, 0x2

    invoke-virtual {p0, v1, v0, v2}, Landroid/app/Service;->registerReceiver(Landroid/content/BroadcastReceiver;Landroid/content/IntentFilter;I)Landroid/content/Intent;

    const/4 v0, 0x1

    .line 145
    iput-boolean v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mIsRegistered:Z

    return-void
.end method

.method public onDestroy()V
    .registers 4

    const/4 v0, 0x0

    .line 192
    new-array v1, v0, [Ljava/lang/Object;

    const-string v2, "AlarmService.onDestroy() called"

    invoke-static {v2, v1}, Lcom/android/deskclock/LogUtils;->v(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 193
    invoke-super {p0}, Landroid/app/Service;->onDestroy()V

    .line 194
    iget-object v1, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

    if-eqz v1, :cond_12

    .line 195
    invoke-direct {p0}, Lcom/android/deskclock/alarms/AlarmService;->stopCurrentAlarm()V

    .line 198
    :cond_12
    iget-boolean v1, p0, Lcom/android/deskclock/alarms/AlarmService;->mIsRegistered:Z

    if-eqz v1, :cond_1d

    .line 199
    iget-object v1, p0, Lcom/android/deskclock/alarms/AlarmService;->mActionsReceiver:Landroid/content/BroadcastReceiver;

    invoke-virtual {p0, v1}, Landroid/app/Service;->unregisterReceiver(Landroid/content/BroadcastReceiver;)V

    .line 200
    iput-boolean v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mIsRegistered:Z

    :cond_1d
    return-void
.end method

.method public onStartCommand(Landroid/content/Intent;II)I
    .registers 9
    invoke-direct {p0, p1, p3}, Lcom/android/deskclock/alarms/AlarmService;->onScheduledStart(Landroid/content/Intent;I)Z
    move-result v0
    if-eqz v0, :scheduled_legacy
    const/4 v0, 0x2
    return v0
    :scheduled_legacy

    .line 149
    const-string p2, "AlarmService.onStartCommand() with %s"

    filled-new-array {p1}, [Ljava/lang/Object;

    move-result-object p3

    invoke-static {p2, p3}, Lcom/android/deskclock/LogUtils;->v(Ljava/lang/String;[Ljava/lang/Object;)V

    const/4 p2, 0x2

    if-nez p1, :cond_d

    return p2

    .line 154
    :cond_d
    sget-object p3, Lcom/android/deskclock/provider/AlarmInstance;->Companion:Lcom/android/deskclock/provider/AlarmInstance$Companion;

    invoke-virtual {p1}, Landroid/content/Intent;->getData()Landroid/net/Uri;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p3, v0}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getId(Landroid/net/Uri;)J

    move-result-wide v0

    .line 155
    invoke-virtual {p1}, Landroid/content/Intent;->getAction()Ljava/lang/String;

    move-result-object v2

    if-eqz v2, :cond_c4

    invoke-virtual {v2}, Ljava/lang/String;->hashCode()I

    move-result v3

    const v4, 0xeecb742

    if-eq v3, v4, :cond_69

    const p1, 0x16875bb4

    if-eq v3, p1, :cond_30

    goto/16 :goto_c4

    :cond_30
    const-string p1, "STOP_ALARM"

    invoke-virtual {v2, p1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result p1

    if-nez p1, :cond_3a

    goto/16 :goto_c4

    .line 178
    :cond_3a
    iget-object p1, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

    if-eqz p1, :cond_62

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    iget-wide v2, p1, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    cmp-long p1, v2, v0

    if-eqz p1, :cond_62

    .line 179
    sget-object p1, Lcom/android/deskclock/LogUtils;->INSTANCE:Lcom/android/deskclock/LogUtils;

    .line 180
    invoke-static {v0, v1}, Ljava/lang/Long;->valueOf(J)Ljava/lang/Long;

    move-result-object p3

    iget-object p0, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

    invoke-virtual {p0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    iget-wide v0, p0, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    invoke-static {v0, v1}, Ljava/lang/Long;->valueOf(J)Ljava/lang/Long;

    move-result-object p0

    filled-new-array {p3, p0}, [Ljava/lang/Object;

    move-result-object p0

    .line 179
    const-string p3, "Can\'t stop alarm for instance: %d because current alarm is: %d"

    invoke-virtual {p1, p3, p0}, Lcom/android/deskclock/LogUtils;->e(Ljava/lang/String;[Ljava/lang/Object;)V

    goto :goto_c4

    .line 182
    :cond_62
    invoke-direct {p0}, Lcom/android/deskclock/alarms/AlarmService;->stopCurrentAlarm()V

    .line 183
    invoke-virtual {p0}, Landroid/app/Service;->stopSelf()V

    goto :goto_c4

    .line 155
    :cond_69
    const-string v3, "change_state"

    invoke-virtual {v2, v3}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v2

    if-eqz v2, :cond_c4

    .line 157
    sget-object v2, Lcom/android/deskclock/alarms/AlarmStateManager;->Companion:Lcom/android/deskclock/alarms/AlarmStateManager$Companion;

    invoke-virtual {v2, p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->handleIntent(Landroid/content/Context;Landroid/content/Intent;)V

    .line 160
    const-string v2, "intent.extra.alarm.state"

    const/4 v3, -0x1

    invoke-virtual {p1, v2, v3}, Landroid/content/Intent;->getIntExtra(Ljava/lang/String;I)I

    move-result p1

    const/4 v2, 0x5

    if-ne p1, v2, :cond_c4

    .line 162
    invoke-virtual {p0}, Landroid/app/Service;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object p1

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 163
    invoke-virtual {p3, p1, v0, v1}, Lcom/android/deskclock/provider/AlarmInstance$Companion;->getInstance(Landroid/content/ContentResolver;J)Lcom/android/deskclock/provider/AlarmInstance;

    move-result-object p1

    if-nez p1, :cond_a4

    .line 165
    sget-object p1, Lcom/android/deskclock/LogUtils;->INSTANCE:Lcom/android/deskclock/LogUtils;

    invoke-static {v0, v1}, Ljava/lang/Long;->valueOf(J)Ljava/lang/Long;

    move-result-object p3

    filled-new-array {p3}, [Ljava/lang/Object;

    move-result-object p3

    const-string v0, "No instance found to start alarm: %d"

    invoke-virtual {p1, v0, p3}, Lcom/android/deskclock/LogUtils;->e(Ljava/lang/String;[Ljava/lang/Object;)V

    .line 166
    iget-object p0, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

    if-eqz p0, :cond_c4

    .line 168
    invoke-static {}, Lcom/android/deskclock/AlarmAlertWakeLock;->releaseCpuLock()V

    goto :goto_c4

    .line 170
    :cond_a4
    iget-object p3, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;

    if-eqz p3, :cond_c1

    invoke-virtual {p3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    iget-wide v2, p3, Lcom/android/deskclock/provider/AlarmInstance;->mId:J

    cmp-long p3, v2, v0

    if-nez p3, :cond_c1

    .line 171
    sget-object p0, Lcom/android/deskclock/LogUtils;->INSTANCE:Lcom/android/deskclock/LogUtils;

    invoke-static {v0, v1}, Ljava/lang/Long;->valueOf(J)Ljava/lang/Long;

    move-result-object p1

    filled-new-array {p1}, [Ljava/lang/Object;

    move-result-object p1

    const-string p3, "Alarm already started for instance: %d"

    invoke-virtual {p0, p3, p1}, Lcom/android/deskclock/LogUtils;->e(Ljava/lang/String;[Ljava/lang/Object;)V

    goto :goto_c4

    .line 173
    :cond_c1
    invoke-direct {p0, p1}, Lcom/android/deskclock/alarms/AlarmService;->startAlarm(Lcom/android/deskclock/provider/AlarmInstance;)V

    :cond_c4
    :goto_c4
    return p2
.end method

.method public onUnbind(Landroid/content/Intent;)Z
    .registers 3

    const/4 v0, 0x0

    .line 63
    iput-boolean v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mIsBound:Z

    .line 64
    invoke-super {p0, p1}, Landroid/app/Service;->onUnbind(Landroid/content/Intent;)Z

    move-result p0

    return p0
.end method

.method private final stopScheduledStartIfIdle(I)V
    .registers 3
    iget-object v0, p0, Lcom/android/deskclock/alarms/AlarmService;->mCurrentAlarm:Lcom/android/deskclock/provider/AlarmInstance;
    if-nez v0, :done
    invoke-virtual {p0, p1}, Landroid/app/Service;->stopSelf(I)V
    :done
    return-void
.end method

.method private final onScheduledStart(Landroid/content/Intent;I)Z
    .registers 13
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
    goto/16 :idle

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
    goto/16 :handled

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
