.class public final Lcom/android/deskclock/alarms/AlarmStateManager;
.super Landroid/content/BroadcastReceiver;
.source "AlarmStateManager.kt"


# static fields
.field public static final Companion:Lcom/android/deskclock/alarms/AlarmStateManager$Companion;

.field private static sStateChangeScheduler:Lcom/android/deskclock/alarms/AlarmStateManager$StateChangeScheduler;


# direct methods
.method public static $r8$lambda$_knPXn4cJMDcun_XoalMIdqZCj0(Landroid/content/Context;Landroid/content/Intent;Landroid/content/BroadcastReceiver$PendingResult;Landroid/os/PowerManager$WakeLock;)Lkotlin/Unit;
    .registers 5

    .line 73
    sget-object v0, Lcom/android/deskclock/alarms/AlarmStateManager;->Companion:Lcom/android/deskclock/alarms/AlarmStateManager$Companion;

    invoke-virtual {v0, p0, p1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->handleIntent(Landroid/content/Context;Landroid/content/Intent;)V

    .line 74
    invoke-virtual {p2}, Landroid/content/BroadcastReceiver$PendingResult;->finish()V

    .line 75
    invoke-virtual {p3}, Landroid/os/PowerManager$WakeLock;->release()V

    .line 76
    sget-object p0, Lkotlin/Unit;->INSTANCE:Lkotlin/Unit;

    return-object p0
.end method

.method static constructor <clinit>()V
    .registers 2

    new-instance v0, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;

    const/4 v1, 0x0

    invoke-direct {v0, v1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;-><init>(Lkotlin/jvm/internal/DefaultConstructorMarker;)V

    sput-object v0, Lcom/android/deskclock/alarms/AlarmStateManager;->Companion:Lcom/android/deskclock/alarms/AlarmStateManager$Companion;

    .line 188
    new-instance v0, Lcom/android/deskclock/alarms/AlarmStateManager$AlarmManagerStateChangeScheduler;

    invoke-direct {v0}, Lcom/android/deskclock/alarms/AlarmStateManager$AlarmManagerStateChangeScheduler;-><init>()V

    sput-object v0, Lcom/android/deskclock/alarms/AlarmStateManager;->sStateChangeScheduler:Lcom/android/deskclock/alarms/AlarmStateManager$StateChangeScheduler;

    return-void
.end method

.method public constructor <init>()V
    .registers 1

    .line 62
    invoke-direct {p0}, Landroid/content/BroadcastReceiver;-><init>()V

    return-void
.end method

.method public static final synthetic access$getSCurrentTimeFactory$cp()Lcom/android/deskclock/alarms/AlarmStateManager$CurrentTimeFactory;
    .registers 1

    const/4 v0, 0x0

    return-object v0
.end method

.method public static final synthetic access$getSStateChangeScheduler$cp()Lcom/android/deskclock/alarms/AlarmStateManager$StateChangeScheduler;
    .registers 1

    .line 62
    sget-object v0, Lcom/android/deskclock/alarms/AlarmStateManager;->sStateChangeScheduler:Lcom/android/deskclock/alarms/AlarmStateManager$StateChangeScheduler;

    return-object v0
.end method


# virtual methods
.method public onReceive(Landroid/content/Context;Landroid/content/Intent;)V
    .registers 6

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 65
    const-string v0, "indicator"

    invoke-virtual {p2}, Landroid/content/Intent;->getAction()Ljava/lang/String;

    move-result-object v1

    invoke-static {v0, v1}, Lkotlin/jvm/internal/Intrinsics;->areEqual(Ljava/lang/Object;Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_13

    return-void

    .line 69
    :cond_13
    invoke-virtual {p0}, Landroid/content/BroadcastReceiver;->goAsync()Landroid/content/BroadcastReceiver$PendingResult;

    move-result-object p0

    invoke-virtual {p0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 70
    invoke-static {p1}, Lcom/android/deskclock/AlarmAlertWakeLock;->createPartialWakeLock(Landroid/content/Context;)Landroid/os/PowerManager$WakeLock;

    move-result-object v0

    .line 71
    invoke-virtual {v0}, Landroid/os/PowerManager$WakeLock;->acquire()V

    .line 72
    sget-object v1, Lcom/android/deskclock/AsyncHandler;->INSTANCE:Lcom/android/deskclock/AsyncHandler;

    new-instance v2, Lcom/android/deskclock/alarms/AlarmStateManager$$ExternalSyntheticLambda0;

    invoke-direct {v2, p1, p2, p0, v0}, Lcom/android/deskclock/alarms/AlarmStateManager$$ExternalSyntheticLambda0;-><init>(Landroid/content/Context;Landroid/content/Intent;Landroid/content/BroadcastReceiver$PendingResult;Landroid/os/PowerManager$WakeLock;)V

    invoke-virtual {v1, v2}, Lcom/android/deskclock/AsyncHandler;->post(Lkotlin/jvm/functions/Function0;)V

    return-void
.end method
