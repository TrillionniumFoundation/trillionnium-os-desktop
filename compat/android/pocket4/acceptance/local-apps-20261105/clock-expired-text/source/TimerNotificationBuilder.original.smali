.class public final Lcom/android/deskclock/data/TimerNotificationBuilder;
.super Ljava/lang/Object;
.source "TimerNotificationBuilder.kt"


# static fields
.field public static final Companion:Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;


# direct methods
.method static constructor <clinit>()V
    .registers 2

    new-instance v0, Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;

    const/4 v1, 0x0

    invoke-direct {v0, v1}, Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;-><init>(Lkotlin/jvm/internal/DefaultConstructorMarker;)V

    sput-object v0, Lcom/android/deskclock/data/TimerNotificationBuilder;->Companion:Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;

    return-void
.end method

.method public constructor <init>()V
    .registers 1

    .line 51
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method private final buildChronometer(Ljava/lang/String;JZLjava/lang/CharSequence;)Landroid/widget/RemoteViews;
    .registers 12

    .line 403
    new-instance v0, Landroid/widget/RemoteViews;

    const p0, 0x7f0d0024

    invoke-direct {v0, p1, p0}, Landroid/widget/RemoteViews;-><init>(Ljava/lang/String;I)V

    const p0, 0x7f0a008d

    const/4 p1, 0x1

    .line 404
    invoke-virtual {v0, p0, p1}, Landroid/widget/RemoteViews;->setChronometerCountDown(IZ)V

    const v1, 0x7f0a008d

    const/4 v4, 0x0

    move-wide v2, p2

    move v5, p4

    .line 405
    invoke-virtual/range {v0 .. v5}, Landroid/widget/RemoteViews;->setChronometer(IJLjava/lang/String;Z)V

    const p0, 0x7f0a0228

    .line 406
    invoke-virtual {v0, p0, p5}, Landroid/widget/RemoteViews;->setTextViewText(ILjava/lang/CharSequence;)V

    return-object v0
.end method


# virtual methods
.method public final build(Landroid/content/Context;Lcom/android/deskclock/data/NotificationModel;Ljava/util/List;)Landroid/app/Notification;
    .registers 20

    move-object/from16 v0, p1

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual/range {p2 .. p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual/range {p3 .. p3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/4 v1, 0x0

    move-object/from16 v2, p3

    .line 75
    invoke-interface {v2, v1}, Ljava/util/List;->get(I)Ljava/lang/Object;

    move-result-object v3

    check-cast v3, Lcom/android/deskclock/data/Timer;

    .line 76
    invoke-interface {v2}, Ljava/util/List;->size()I

    move-result v2

    .line 79
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->isRunning()Z

    move-result v8

    .line 80
    invoke-virtual {v0}, Landroid/content/Context;->getResources()Landroid/content/res/Resources;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 82
    sget-object v5, Lcom/android/deskclock/data/TimerNotificationBuilder;->Companion:Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;

    # invokes: Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;->getChronometerBase(Lcom/android/deskclock/data/Timer;)J
    invoke-static {v5, v3}, Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;->access$getChronometerBase(Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;Lcom/android/deskclock/data/Timer;)J

    move-result-wide v6

    .line 83
    invoke-virtual {v0}, Landroid/content/Context;->getPackageName()Ljava/lang/String;

    move-result-object v5

    invoke-virtual {v5}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 85
    new-instance v9, Ljava/util/ArrayList;

    const/4 v10, 0x2

    invoke-direct {v9, v10}, Ljava/util/ArrayList;-><init>(I)V

    .line 88
    const-string v11, "com.android.deskclock.extra.TIMER_ID"

    const/4 v12, 0x1

    if-ne v2, v12, :cond_14b

    if-eqz v8, :cond_cd

    .line 91
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getLabel()Ljava/lang/String;

    move-result-object v10

    if-eqz v10, :cond_4f

    invoke-interface {v10}, Ljava/lang/CharSequence;->length()I

    move-result v10

    if-nez v10, :cond_4a

    goto :goto_4f

    .line 94
    :cond_4a
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getLabel()Ljava/lang/String;

    move-result-object v10

    goto :goto_56

    :cond_4f
    :goto_4f
    const v10, 0x7f1202ce

    .line 92
    invoke-virtual {v4, v10}, Landroid/content/res/Resources;->getString(I)Ljava/lang/String;

    move-result-object v10

    .line 91
    :goto_56
    invoke-virtual {v10}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 98
    new-instance v13, Landroid/content/Intent;

    const-class v14, Lcom/android/deskclock/timer/TimerService;

    invoke-direct {v13, v0, v14}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    .line 99
    const-string v14, "com.android.deskclock.action.PAUSE_TIMER"

    invoke-virtual {v13, v14}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v13

    .line 100
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getId()I

    move-result v14

    invoke-virtual {v13, v11, v14}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    move-result-object v13

    invoke-virtual {v13}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const v14, 0x7f1202d7

    .line 103
    invoke-virtual {v4, v14}, Landroid/content/res/Resources;->getText(I)Ljava/lang/CharSequence;

    move-result-object v14

    invoke-virtual {v14}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 104
    sget-object v15, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;

    invoke-virtual {v15, v0, v13}, Lcom/android/deskclock/Utils;->pendingServiceIntent(Landroid/content/Context;Landroid/content/Intent;)Landroid/app/PendingIntent;

    move-result-object v13

    .line 105
    new-instance v12, Landroidx/core/app/NotificationCompat$Action$Builder;

    const v1, 0x7f0800c1

    invoke-direct {v12, v1, v14, v13}, Landroidx/core/app/NotificationCompat$Action$Builder;-><init>(ILjava/lang/CharSequence;Landroid/app/PendingIntent;)V

    invoke-virtual {v12}, Landroidx/core/app/NotificationCompat$Action$Builder;->build()Landroidx/core/app/NotificationCompat$Action;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-interface {v9, v1}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    .line 108
    new-instance v1, Landroid/content/Intent;

    const-class v12, Lcom/android/deskclock/timer/TimerService;

    invoke-direct {v1, v0, v12}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    .line 109
    const-string v12, "com.android.deskclock.action.ADD_MINUTE_TIMER"

    invoke-virtual {v1, v12}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v1

    .line 110
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getId()I

    move-result v12

    invoke-virtual {v1, v11, v12}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const v12, 0x7f1202d9

    .line 113
    invoke-virtual {v4, v12}, Landroid/content/res/Resources;->getText(I)Ljava/lang/CharSequence;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 114
    invoke-virtual {v15, v0, v1}, Lcom/android/deskclock/Utils;->pendingServiceIntent(Landroid/content/Context;Landroid/content/Intent;)Landroid/app/PendingIntent;

    move-result-object v1

    .line 115
    new-instance v12, Landroidx/core/app/NotificationCompat$Action$Builder;

    const v13, 0x7f080098

    invoke-direct {v12, v13, v4, v1}, Landroidx/core/app/NotificationCompat$Action$Builder;-><init>(ILjava/lang/CharSequence;Landroid/app/PendingIntent;)V

    invoke-virtual {v12}, Landroidx/core/app/NotificationCompat$Action$Builder;->build()Landroidx/core/app/NotificationCompat$Action;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-interface {v9, v1}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    goto/16 :goto_199

    :cond_cd
    const v1, 0x7f1202d8

    .line 118
    invoke-virtual {v4, v1}, Landroid/content/res/Resources;->getString(I)Ljava/lang/String;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 121
    new-instance v12, Landroid/content/Intent;

    const-class v13, Lcom/android/deskclock/timer/TimerService;

    invoke-direct {v12, v0, v13}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    .line 122
    const-string v13, "com.android.deskclock.action.START_TIMER"

    invoke-virtual {v12, v13}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v12

    .line 123
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getId()I

    move-result v13

    invoke-virtual {v12, v11, v13}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    move-result-object v12

    invoke-virtual {v12}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const v13, 0x7f1202ba

    .line 126
    invoke-virtual {v4, v13}, Landroid/content/res/Resources;->getText(I)Ljava/lang/CharSequence;

    move-result-object v13

    invoke-virtual {v13}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 127
    sget-object v14, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;

    invoke-virtual {v14, v0, v12}, Lcom/android/deskclock/Utils;->pendingServiceIntent(Landroid/content/Context;Landroid/content/Intent;)Landroid/app/PendingIntent;

    move-result-object v12

    .line 128
    new-instance v15, Landroidx/core/app/NotificationCompat$Action$Builder;

    const v10, 0x7f0800d4

    invoke-direct {v15, v10, v13, v12}, Landroidx/core/app/NotificationCompat$Action$Builder;-><init>(ILjava/lang/CharSequence;Landroid/app/PendingIntent;)V

    invoke-virtual {v15}, Landroidx/core/app/NotificationCompat$Action$Builder;->build()Landroidx/core/app/NotificationCompat$Action;

    move-result-object v10

    invoke-virtual {v10}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-interface {v9, v10}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    .line 131
    new-instance v10, Landroid/content/Intent;

    const-class v12, Lcom/android/deskclock/timer/TimerService;

    invoke-direct {v10, v0, v12}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    .line 132
    const-string v12, "com.android.deskclock.action.RESET_TIMER"

    invoke-virtual {v10, v12}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v10

    .line 133
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getId()I

    move-result v12

    invoke-virtual {v10, v11, v12}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    move-result-object v10

    invoke-virtual {v10}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const v12, 0x7f1202b9

    .line 136
    invoke-virtual {v4, v12}, Landroid/content/res/Resources;->getText(I)Ljava/lang/CharSequence;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 137
    invoke-virtual {v14, v0, v10}, Lcom/android/deskclock/Utils;->pendingServiceIntent(Landroid/content/Context;Landroid/content/Intent;)Landroid/app/PendingIntent;

    move-result-object v10

    .line 138
    new-instance v12, Landroidx/core/app/NotificationCompat$Action$Builder;

    const v13, 0x7f0800c8

    invoke-direct {v12, v13, v4, v10}, Landroidx/core/app/NotificationCompat$Action$Builder;-><init>(ILjava/lang/CharSequence;Landroid/app/PendingIntent;)V

    invoke-virtual {v12}, Landroidx/core/app/NotificationCompat$Action$Builder;->build()Landroidx/core/app/NotificationCompat$Action;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-interface {v9, v4}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    move-object v10, v1

    goto :goto_199

    :cond_14b
    if-eqz v8, :cond_15e

    .line 143
    invoke-static {v2}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v1

    filled-new-array {v1}, [Ljava/lang/Object;

    move-result-object v1

    const v10, 0x7f1202e8

    invoke-virtual {v4, v10, v1}, Landroid/content/res/Resources;->getString(I[Ljava/lang/Object;)Ljava/lang/String;

    move-result-object v1

    :goto_15c
    move-object v10, v1

    goto :goto_16e

    .line 146
    :cond_15e
    invoke-static {v2}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v1

    filled-new-array {v1}, [Ljava/lang/Object;

    move-result-object v1

    const v10, 0x7f1202e9

    invoke-virtual {v4, v10, v1}, Landroid/content/res/Resources;->getString(I[Ljava/lang/Object;)Ljava/lang/String;

    move-result-object v1

    goto :goto_15c

    .line 141
    :goto_16e
    invoke-virtual {v10}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 149
    sget-object v1, Lcom/android/deskclock/timer/TimerService;->Companion:Lcom/android/deskclock/timer/TimerService$Companion;

    invoke-virtual {v1, v0}, Lcom/android/deskclock/timer/TimerService$Companion;->createResetUnexpiredTimersIntent(Landroid/content/Context;)Landroid/content/Intent;

    move-result-object v1

    const v12, 0x7f1202de

    .line 152
    invoke-virtual {v4, v12}, Landroid/content/res/Resources;->getText(I)Ljava/lang/CharSequence;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 153
    sget-object v12, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;

    invoke-virtual {v12, v0, v1}, Lcom/android/deskclock/Utils;->pendingServiceIntent(Landroid/content/Context;Landroid/content/Intent;)Landroid/app/PendingIntent;

    move-result-object v1

    .line 154
    new-instance v12, Landroidx/core/app/NotificationCompat$Action$Builder;

    const v13, 0x7f0800c8

    invoke-direct {v12, v13, v4, v1}, Landroidx/core/app/NotificationCompat$Action$Builder;-><init>(ILjava/lang/CharSequence;Landroid/app/PendingIntent;)V

    invoke-virtual {v12}, Landroidx/core/app/NotificationCompat$Action$Builder;->build()Landroidx/core/app/NotificationCompat$Action;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-interface {v9, v1}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    .line 158
    :goto_199
    new-instance v1, Landroid/content/Intent;

    const-class v4, Lcom/android/deskclock/timer/TimerService;

    invoke-direct {v1, v0, v4}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    .line 159
    const-string v4, "com.android.deskclock.action.SHOW_TIMER"

    invoke-virtual {v1, v4}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v1

    .line 160
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getId()I

    move-result v4

    invoke-virtual {v1, v11, v4}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    move-result-object v1

    .line 161
    const-string v4, "com.android.deskclock.extra.EVENT_LABEL"

    const v11, 0x7f120201

    invoke-virtual {v1, v4, v11}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/high16 v11, 0x48000000    # 131072.0f

    const/4 v4, 0x0

    .line 164
    invoke-static {v0, v4, v1, v11}, Landroid/app/PendingIntent;->getService(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 167
    new-instance v12, Landroidx/core/app/NotificationCompat$Builder;

    .line 168
    const-string v13, "TimerModelNotification"

    .line 167
    invoke-direct {v12, v0, v13}, Landroidx/core/app/NotificationCompat$Builder;-><init>(Landroid/content/Context;Ljava/lang/String;)V

    const/4 v13, 0x1

    .line 169
    invoke-virtual {v12, v13}, Landroidx/core/app/NotificationCompat$Builder;->setOngoing(Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v12

    .line 170
    invoke-virtual {v12, v13}, Landroidx/core/app/NotificationCompat$Builder;->setLocalOnly(Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v12

    .line 171
    invoke-virtual {v12, v4}, Landroidx/core/app/NotificationCompat$Builder;->setShowWhen(Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v12

    .line 172
    invoke-virtual {v12, v4}, Landroidx/core/app/NotificationCompat$Builder;->setAutoCancel(Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v12

    .line 173
    invoke-virtual {v12, v1}, Landroidx/core/app/NotificationCompat$Builder;->setContentIntent(Landroid/app/PendingIntent;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v1

    const/4 v4, 0x4

    .line 174
    invoke-virtual {v1, v4}, Landroidx/core/app/NotificationCompat$Builder;->setPriority(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v1

    .line 175
    const-string v12, "alarm"

    invoke-virtual {v1, v12}, Landroidx/core/app/NotificationCompat$Builder;->setCategory(Ljava/lang/String;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v1

    const v4, 0x7f080142

    .line 176
    invoke-virtual {v1, v4}, Landroidx/core/app/NotificationCompat$Builder;->setSmallIcon(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v1

    .line 177
    invoke-virtual/range {p2 .. p2}, Lcom/android/deskclock/data/NotificationModel;->getTimerNotificationSortKey()Ljava/lang/String;

    move-result-object v4

    invoke-virtual {v1, v4}, Landroidx/core/app/NotificationCompat$Builder;->setSortKey(Ljava/lang/String;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v1

    const/4 v13, 0x1

    .line 178
    invoke-virtual {v1, v13}, Landroidx/core/app/NotificationCompat$Builder;->setVisibility(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v1

    .line 179
    new-instance v4, Landroidx/core/app/NotificationCompat$DecoratedCustomViewStyle;

    invoke-direct {v4}, Landroidx/core/app/NotificationCompat$DecoratedCustomViewStyle;-><init>()V

    invoke-virtual {v1, v4}, Landroidx/core/app/NotificationCompat$Builder;->setStyle(Landroidx/core/app/NotificationCompat$Style;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v1

    const v4, 0x7f060034

    .line 180
    invoke-static {v0, v4}, Landroidx/core/content/ContextCompat;->getColor(Landroid/content/Context;I)I

    move-result v4

    invoke-virtual {v1, v4}, Landroidx/core/app/NotificationCompat$Builder;->setColor(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 182
    invoke-virtual {v9}, Ljava/util/ArrayList;->size()I

    move-result v4

    const/4 v13, 0x0

    :goto_21b
    if-ge v13, v4, :cond_229

    invoke-virtual {v9, v13}, Ljava/util/ArrayList;->get(I)Ljava/lang/Object;

    move-result-object v14

    add-int/lit8 v13, v13, 0x1

    check-cast v14, Landroidx/core/app/NotificationCompat$Action;

    .line 183
    invoke-virtual {v1, v14}, Landroidx/core/app/NotificationCompat$Builder;->addAction(Landroidx/core/app/NotificationCompat$Action;)Landroidx/core/app/NotificationCompat$Builder;

    goto :goto_21b

    .line 186
    :cond_229
    sget-object v4, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;

    invoke-virtual {v4}, Lcom/android/deskclock/Utils;->isNOrLater()Z

    move-result v4

    if-eqz v4, :cond_249

    move-object/from16 v4, p0

    move-object v9, v10

    .line 187
    invoke-direct/range {v4 .. v9}, Lcom/android/deskclock/data/TimerNotificationBuilder;->buildChronometer(Ljava/lang/String;JZLjava/lang/CharSequence;)Landroid/widget/RemoteViews;

    move-result-object v0

    invoke-virtual {v1, v0}, Landroidx/core/app/NotificationCompat$Builder;->setCustomContentView(Landroid/widget/RemoteViews;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    .line 188
    invoke-virtual/range {p2 .. p2}, Lcom/android/deskclock/data/NotificationModel;->getTimerNotificationGroupKey()Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v0, v2}, Landroidx/core/app/NotificationCompat$Builder;->setGroup(Ljava/lang/String;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    .line 187
    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    goto/16 :goto_2bf

    :cond_249
    move-object v9, v10

    const/4 v13, 0x1

    if-ne v2, v13, :cond_257

    .line 193
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getRemainingTime()J

    move-result-wide v4

    const/4 v2, 0x0

    invoke-static {v0, v4, v5, v2}, Lcom/android/deskclock/data/TimerStringFormatter;->formatTimeRemaining(Landroid/content/Context;JZ)Ljava/lang/String;

    move-result-object v4

    goto :goto_275

    :cond_257
    const/4 v2, 0x0

    if-eqz v8, :cond_26e

    .line 197
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getRemainingTime()J

    move-result-wide v4

    .line 196
    invoke-static {v0, v4, v5, v2}, Lcom/android/deskclock/data/TimerStringFormatter;->formatTimeRemaining(Landroid/content/Context;JZ)Ljava/lang/String;

    move-result-object v4

    const v2, 0x7f120284

    .line 198
    filled-new-array {v4}, [Ljava/lang/Object;

    move-result-object v4

    invoke-virtual {v0, v2, v4}, Landroid/content/Context;->getString(I[Ljava/lang/Object;)Ljava/lang/String;

    move-result-object v4

    goto :goto_275

    :cond_26e
    const v2, 0x7f1201a5

    .line 200
    invoke-virtual {v0, v2}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v4

    .line 203
    :goto_275
    invoke-virtual {v1, v9}, Landroidx/core/app/NotificationCompat$Builder;->setContentTitle(Ljava/lang/CharSequence;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v2

    invoke-virtual {v2, v4}, Landroidx/core/app/NotificationCompat$Builder;->setContentText(Ljava/lang/CharSequence;)Landroidx/core/app/NotificationCompat$Builder;

    .line 205
    invoke-virtual {v0, v12}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    check-cast v2, Landroid/app/AlarmManager;

    .line 206
    sget-object v4, Lcom/android/deskclock/timer/TimerService;->Companion:Lcom/android/deskclock/timer/TimerService$Companion;

    invoke-virtual {v4, v0}, Lcom/android/deskclock/timer/TimerService$Companion;->createUpdateNotificationIntent(Landroid/content/Context;)Landroid/content/Intent;

    move-result-object v4

    .line 207
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getRemainingTime()J

    move-result-wide v5

    .line 208
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->isRunning()Z

    move-result v3

    if-eqz v3, :cond_2b0

    const-wide/32 v7, 0xea60

    cmp-long v3, v5, v7

    if-lez v3, :cond_2b0

    const/4 v3, 0x0

    .line 211
    invoke-static {v0, v3, v4, v11}, Landroid/app/PendingIntent;->getService(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 214
    rem-long/2addr v5, v7

    .line 215
    invoke-static {}, Landroid/os/SystemClock;->elapsedRealtime()J

    move-result-wide v3

    add-long/2addr v3, v5

    .line 216
    sget-object v5, Lcom/android/deskclock/data/TimerModel;->Companion:Lcom/android/deskclock/data/TimerModel$Companion;

    invoke-virtual {v5, v2, v3, v4, v0}, Lcom/android/deskclock/data/TimerModel$Companion;->schedulePendingIntent(Landroid/app/AlarmManager;JLandroid/app/PendingIntent;)V

    goto :goto_2bf

    :cond_2b0
    const/4 v3, 0x0

    const/high16 v5, 0x60000000

    .line 219
    invoke-static {v0, v3, v4, v5}, Landroid/app/PendingIntent;->getService(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;

    move-result-object v0

    if-eqz v0, :cond_2bf

    .line 222
    invoke-virtual {v2, v0}, Landroid/app/AlarmManager;->cancel(Landroid/app/PendingIntent;)V

    .line 223
    invoke-virtual {v0}, Landroid/app/PendingIntent;->cancel()V

    .line 227
    :cond_2bf
    :goto_2bf
    invoke-virtual {v1}, Landroidx/core/app/NotificationCompat$Builder;->build()Landroid/app/Notification;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    return-object v0
.end method

.method public final buildChannel(Landroid/content/Context;Landroidx/core/app/NotificationManagerCompat;)V
    .registers 5

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 66
    new-instance p0, Landroid/app/NotificationChannel;

    const v0, 0x7f1201dd

    .line 68
    invoke-virtual {p1, v0}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object p1

    const/4 v0, 0x3

    .line 66
    const-string v1, "TimerModelNotification"

    invoke-direct {p0, v1, p1, v0}, Landroid/app/NotificationChannel;-><init>(Ljava/lang/String;Ljava/lang/CharSequence;I)V

    .line 70
    invoke-virtual {p2, p0}, Landroidx/core/app/NotificationManagerCompat;->createNotificationChannel(Landroid/app/NotificationChannel;)V

    return-void
.end method

.method public final buildHeadsUp(Landroid/content/Context;Ljava/util/List;)Landroid/app/Notification;
    .registers 22

    move-object/from16 v0, p1

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual/range {p2 .. p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/4 v1, 0x0

    move-object/from16 v2, p2

    .line 231
    invoke-interface {v2, v1}, Ljava/util/List;->get(I)Ljava/lang/Object;

    move-result-object v3

    check-cast v3, Lcom/android/deskclock/data/Timer;

    .line 235
    sget-object v4, Lcom/android/deskclock/timer/TimerService;->Companion:Lcom/android/deskclock/timer/TimerService$Companion;

    invoke-virtual {v4, v0}, Lcom/android/deskclock/timer/TimerService$Companion;->createResetExpiredTimersIntent(Landroid/content/Context;)Landroid/content/Intent;

    move-result-object v5

    .line 236
    sget-object v6, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;

    invoke-virtual {v6, v0, v5}, Lcom/android/deskclock/Utils;->pendingServiceIntent(Landroid/content/Context;Landroid/content/Intent;)Landroid/app/PendingIntent;

    move-result-object v5

    .line 240
    invoke-interface {v2}, Ljava/util/List;->size()I

    move-result v2

    .line 241
    new-instance v7, Ljava/util/ArrayList;

    const/4 v8, 0x2

    invoke-direct {v7, v8}, Ljava/util/ArrayList;-><init>(I)V

    const v8, 0x7f1202cd

    const v9, 0x7f1202e6

    const v10, 0x7f0800d6

    const/4 v11, 0x1

    if-ne v2, v11, :cond_8a

    .line 243
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getLabel()Ljava/lang/String;

    move-result-object v12

    if-eqz v12, :cond_3f

    .line 244
    invoke-interface {v12}, Ljava/lang/CharSequence;->length()I

    move-result v13

    if-nez v13, :cond_43

    .line 245
    :cond_3f
    invoke-virtual {v0, v9}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v12

    .line 244
    :cond_43
    invoke-virtual {v12}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const v13, 0x7f1202e4

    .line 251
    invoke-virtual {v0, v13}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v13

    invoke-virtual {v13}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 252
    new-instance v14, Landroidx/core/app/NotificationCompat$Action$Builder;

    invoke-direct {v14, v10, v13, v5}, Landroidx/core/app/NotificationCompat$Action$Builder;-><init>(ILjava/lang/CharSequence;Landroid/app/PendingIntent;)V

    invoke-virtual {v14}, Landroidx/core/app/NotificationCompat$Action$Builder;->build()Landroidx/core/app/NotificationCompat$Action;

    move-result-object v5

    invoke-virtual {v5}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-interface {v7, v5}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    .line 255
    invoke-virtual {v3}, Lcom/android/deskclock/data/Timer;->getId()I

    move-result v5

    invoke-virtual {v4, v0, v5}, Lcom/android/deskclock/timer/TimerService$Companion;->createAddMinuteTimerIntent(Landroid/content/Context;I)Landroid/content/Intent;

    move-result-object v4

    .line 256
    invoke-virtual {v6, v0, v4}, Lcom/android/deskclock/Utils;->pendingServiceIntent(Landroid/content/Context;Landroid/content/Intent;)Landroid/app/PendingIntent;

    move-result-object v4

    const v5, 0x7f1202d9

    .line 258
    invoke-virtual {v0, v5}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v5

    invoke-virtual {v5}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 259
    new-instance v10, Landroidx/core/app/NotificationCompat$Action$Builder;

    const v13, 0x7f080098

    invoke-direct {v10, v13, v5, v4}, Landroidx/core/app/NotificationCompat$Action$Builder;-><init>(ILjava/lang/CharSequence;Landroid/app/PendingIntent;)V

    invoke-virtual {v10}, Landroidx/core/app/NotificationCompat$Action$Builder;->build()Landroidx/core/app/NotificationCompat$Action;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-interface {v7, v4}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    :goto_87
    move-object/from16 v18, v12

    goto :goto_b3

    .line 261
    :cond_8a
    invoke-static {v2}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v4

    filled-new-array {v4}, [Ljava/lang/Object;

    move-result-object v4

    invoke-virtual {v0, v8, v4}, Landroid/content/Context;->getString(I[Ljava/lang/Object;)Ljava/lang/String;

    move-result-object v12

    invoke-virtual {v12}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const v4, 0x7f1202e5

    .line 264
    invoke-virtual {v0, v4}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 265
    new-instance v13, Landroidx/core/app/NotificationCompat$Action$Builder;

    invoke-direct {v13, v10, v4, v5}, Landroidx/core/app/NotificationCompat$Action$Builder;-><init>(ILjava/lang/CharSequence;Landroid/app/PendingIntent;)V

    invoke-virtual {v13}, Landroidx/core/app/NotificationCompat$Action$Builder;->build()Landroidx/core/app/NotificationCompat$Action;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-interface {v7, v4}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    goto :goto_87

    .line 268
    :goto_b3
    sget-object v4, Lcom/android/deskclock/data/TimerNotificationBuilder;->Companion:Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;

    # invokes: Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;->getChronometerBase(Lcom/android/deskclock/data/Timer;)J
    invoke-static {v4, v3}, Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;->access$getChronometerBase(Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;Lcom/android/deskclock/data/Timer;)J

    move-result-wide v15

    .line 270
    invoke-virtual {v0}, Landroid/content/Context;->getPackageName()Ljava/lang/String;

    move-result-object v14

    invoke-virtual {v14}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 273
    new-instance v3, Landroid/content/Intent;

    const-class v4, Lcom/android/deskclock/timer/ExpiredTimersActivity;

    invoke-direct {v3, v0, v4}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    .line 274
    invoke-virtual {v6, v0, v3}, Lcom/android/deskclock/Utils;->pendingActivityIntent(Landroid/content/Context;Landroid/content/Intent;)Landroid/app/PendingIntent;

    move-result-object v3

    .line 277
    new-instance v5, Landroid/content/Intent;

    invoke-direct {v5, v0, v4}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    const/high16 v4, 0x10040000

    .line 278
    invoke-virtual {v5, v4}, Landroid/content/Intent;->setFlags(I)Landroid/content/Intent;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 279
    invoke-virtual {v6, v0, v4}, Lcom/android/deskclock/Utils;->pendingActivityIntent(Landroid/content/Context;Landroid/content/Intent;)Landroid/app/PendingIntent;

    move-result-object v4

    .line 281
    new-instance v5, Landroidx/core/app/NotificationCompat$Builder;

    .line 282
    const-string v6, "TimerModelNotification"

    .line 281
    invoke-direct {v5, v0, v6}, Landroidx/core/app/NotificationCompat$Builder;-><init>(Landroid/content/Context;Ljava/lang/String;)V

    .line 283
    invoke-virtual {v5, v11}, Landroidx/core/app/NotificationCompat$Builder;->setOngoing(Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v5

    .line 284
    invoke-virtual {v5, v11}, Landroidx/core/app/NotificationCompat$Builder;->setLocalOnly(Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v5

    .line 285
    invoke-virtual {v5, v1}, Landroidx/core/app/NotificationCompat$Builder;->setShowWhen(Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v5

    .line 286
    invoke-virtual {v5, v1}, Landroidx/core/app/NotificationCompat$Builder;->setAutoCancel(Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v5

    .line 287
    invoke-virtual {v5, v3}, Landroidx/core/app/NotificationCompat$Builder;->setContentIntent(Landroid/app/PendingIntent;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v3

    const/4 v5, 0x4

    .line 288
    invoke-virtual {v3, v5}, Landroidx/core/app/NotificationCompat$Builder;->setPriority(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v3

    .line 289
    invoke-virtual {v3, v5}, Landroidx/core/app/NotificationCompat$Builder;->setDefaults(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v3

    const v5, 0x7f080142

    .line 290
    invoke-virtual {v3, v5}, Landroidx/core/app/NotificationCompat$Builder;->setSmallIcon(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v3

    .line 291
    invoke-virtual {v3, v4, v11}, Landroidx/core/app/NotificationCompat$Builder;->setFullScreenIntent(Landroid/app/PendingIntent;Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v3

    .line 292
    new-instance v4, Landroidx/core/app/NotificationCompat$DecoratedCustomViewStyle;

    invoke-direct {v4}, Landroidx/core/app/NotificationCompat$DecoratedCustomViewStyle;-><init>()V

    invoke-virtual {v3, v4}, Landroidx/core/app/NotificationCompat$Builder;->setStyle(Landroidx/core/app/NotificationCompat$Style;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v3

    const v4, 0x7f060034

    .line 293
    invoke-static {v0, v4}, Landroidx/core/content/ContextCompat;->getColor(Landroid/content/Context;I)I

    move-result v4

    invoke-virtual {v3, v4}, Landroidx/core/app/NotificationCompat$Builder;->setColor(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v3

    invoke-virtual {v3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 295
    invoke-virtual {v7}, Ljava/util/ArrayList;->size()I

    move-result v4

    :goto_127
    if-ge v1, v4, :cond_135

    invoke-virtual {v7, v1}, Ljava/util/ArrayList;->get(I)Ljava/lang/Object;

    move-result-object v5

    add-int/lit8 v1, v1, 0x1

    check-cast v5, Landroidx/core/app/NotificationCompat$Action;

    .line 296
    invoke-virtual {v3, v5}, Landroidx/core/app/NotificationCompat$Builder;->addAction(Landroidx/core/app/NotificationCompat$Action;)Landroidx/core/app/NotificationCompat$Builder;

    goto :goto_127

    .line 299
    :cond_135
    sget-object v1, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;

    invoke-virtual {v1}, Lcom/android/deskclock/Utils;->isNOrLater()Z

    move-result v1

    if-eqz v1, :cond_149

    const/16 v17, 0x1

    move-object/from16 v13, p0

    .line 300
    invoke-direct/range {v13 .. v18}, Lcom/android/deskclock/data/TimerNotificationBuilder;->buildChronometer(Ljava/lang/String;JZLjava/lang/CharSequence;)Landroid/widget/RemoteViews;

    move-result-object v0

    invoke-virtual {v3, v0}, Landroidx/core/app/NotificationCompat$Builder;->setCustomContentView(Landroid/widget/RemoteViews;)Landroidx/core/app/NotificationCompat$Builder;

    goto :goto_16b

    :cond_149
    move-object/from16 v12, v18

    if-ne v2, v11, :cond_155

    .line 303
    invoke-virtual {v0, v9}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v0

    .line 302
    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    goto :goto_164

    .line 305
    :cond_155
    invoke-static {v2}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v1

    filled-new-array {v1}, [Ljava/lang/Object;

    move-result-object v1

    invoke-virtual {v0, v8, v1}, Landroid/content/Context;->getString(I[Ljava/lang/Object;)Ljava/lang/String;

    move-result-object v0

    .line 304
    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 307
    :goto_164
    invoke-virtual {v3, v12}, Landroidx/core/app/NotificationCompat$Builder;->setContentTitle(Ljava/lang/CharSequence;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v1

    invoke-virtual {v1, v0}, Landroidx/core/app/NotificationCompat$Builder;->setContentText(Ljava/lang/CharSequence;)Landroidx/core/app/NotificationCompat$Builder;

    .line 310
    :goto_16b
    invoke-virtual {v3}, Landroidx/core/app/NotificationCompat$Builder;->build()Landroid/app/Notification;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    return-object v0
.end method

.method public final buildMissed(Landroid/content/Context;Lcom/android/deskclock/data/NotificationModel;Ljava/util/List;)Landroid/app/Notification;
    .registers 15

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-virtual {p3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/4 v0, 0x0

    .line 318
    invoke-interface {p3, v0}, Ljava/util/List;->get(I)Ljava/lang/Object;

    move-result-object v1

    check-cast v1, Lcom/android/deskclock/data/Timer;

    .line 319
    invoke-interface {p3}, Ljava/util/List;->size()I

    move-result p3

    .line 322
    sget-object v2, Lcom/android/deskclock/data/TimerNotificationBuilder;->Companion:Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;

    # invokes: Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;->getChronometerBase(Lcom/android/deskclock/data/Timer;)J
    invoke-static {v2, v1}, Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;->access$getChronometerBase(Lcom/android/deskclock/data/TimerNotificationBuilder$Companion;Lcom/android/deskclock/data/Timer;)J

    move-result-wide v5

    .line 323
    invoke-virtual {p1}, Landroid/content/Context;->getPackageName()Ljava/lang/String;

    move-result-object v4

    invoke-virtual {v4}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 324
    invoke-virtual {p1}, Landroid/content/Context;->getResources()Landroid/content/res/Resources;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const v3, 0x7f0800c8

    .line 329
    const-string v7, "com.android.deskclock.extra.TIMER_ID"

    const/4 v8, 0x1

    if-ne p3, v8, :cond_89

    .line 331
    invoke-virtual {v1}, Lcom/android/deskclock/data/Timer;->getLabel()Ljava/lang/String;

    move-result-object p3

    invoke-static {p3}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z

    move-result p3

    if-eqz p3, :cond_42

    const p3, 0x7f12023d

    .line 332
    invoke-virtual {v2, p3}, Landroid/content/res/Resources;->getString(I)Ljava/lang/String;

    move-result-object p3

    goto :goto_51

    .line 335
    :cond_42
    invoke-virtual {v1}, Lcom/android/deskclock/data/Timer;->getLabel()Ljava/lang/String;

    move-result-object p3

    filled-new-array {p3}, [Ljava/lang/Object;

    move-result-object p3

    const v9, 0x7f12023c

    .line 334
    invoke-virtual {v2, v9, p3}, Landroid/content/res/Resources;->getString(I[Ljava/lang/Object;)Ljava/lang/String;

    move-result-object p3

    .line 331
    :goto_51
    invoke-virtual {p3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 339
    new-instance v9, Landroid/content/Intent;

    const-class v10, Lcom/android/deskclock/timer/TimerService;

    invoke-direct {v9, p1, v10}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    .line 340
    const-string v10, "com.android.deskclock.action.RESET_TIMER"

    invoke-virtual {v9, v10}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v9

    .line 341
    invoke-virtual {v1}, Lcom/android/deskclock/data/Timer;->getId()I

    move-result v10

    invoke-virtual {v9, v7, v10}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    move-result-object v9

    invoke-virtual {v9}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const v10, 0x7f1202dd

    .line 344
    invoke-virtual {v2, v10}, Landroid/content/res/Resources;->getText(I)Ljava/lang/CharSequence;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 345
    sget-object v10, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;

    invoke-virtual {v10, p1, v9}, Lcom/android/deskclock/Utils;->pendingServiceIntent(Landroid/content/Context;Landroid/content/Intent;)Landroid/app/PendingIntent;

    move-result-object v9

    .line 346
    new-instance v10, Landroidx/core/app/NotificationCompat$Action$Builder;

    invoke-direct {v10, v3, v2, v9}, Landroidx/core/app/NotificationCompat$Action$Builder;-><init>(ILjava/lang/CharSequence;Landroid/app/PendingIntent;)V

    invoke-virtual {v10}, Landroidx/core/app/NotificationCompat$Action$Builder;->build()Landroidx/core/app/NotificationCompat$Action;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    goto :goto_bd

    .line 349
    :cond_89
    invoke-static {p3}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object p3

    filled-new-array {p3}, [Ljava/lang/Object;

    move-result-object p3

    const v9, 0x7f1202cc

    invoke-virtual {v2, v9, p3}, Landroid/content/res/Resources;->getString(I[Ljava/lang/Object;)Ljava/lang/String;

    move-result-object p3

    invoke-virtual {p3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 351
    sget-object v9, Lcom/android/deskclock/timer/TimerService;->Companion:Lcom/android/deskclock/timer/TimerService$Companion;

    invoke-virtual {v9, p1}, Lcom/android/deskclock/timer/TimerService$Companion;->createResetMissedTimersIntent(Landroid/content/Context;)Landroid/content/Intent;

    move-result-object v9

    const v10, 0x7f1202de

    .line 354
    invoke-virtual {v2, v10}, Landroid/content/res/Resources;->getText(I)Ljava/lang/CharSequence;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 355
    sget-object v10, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;

    invoke-virtual {v10, p1, v9}, Lcom/android/deskclock/Utils;->pendingServiceIntent(Landroid/content/Context;Landroid/content/Intent;)Landroid/app/PendingIntent;

    move-result-object v9

    .line 356
    new-instance v10, Landroidx/core/app/NotificationCompat$Action$Builder;

    invoke-direct {v10, v3, v2, v9}, Landroidx/core/app/NotificationCompat$Action$Builder;-><init>(ILjava/lang/CharSequence;Landroid/app/PendingIntent;)V

    invoke-virtual {v10}, Landroidx/core/app/NotificationCompat$Action$Builder;->build()Landroidx/core/app/NotificationCompat$Action;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 360
    :goto_bd
    new-instance v3, Landroid/content/Intent;

    const-class v9, Lcom/android/deskclock/timer/TimerService;

    invoke-direct {v3, p1, v9}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    .line 361
    const-string v9, "com.android.deskclock.action.SHOW_TIMER"

    invoke-virtual {v3, v9}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v3

    .line 362
    invoke-virtual {v1}, Lcom/android/deskclock/data/Timer;->getId()I

    move-result v9

    invoke-virtual {v3, v7, v9}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    move-result-object v3

    .line 363
    const-string v7, "com.android.deskclock.extra.EVENT_LABEL"

    const v9, 0x7f120201

    invoke-virtual {v3, v7, v9}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    move-result-object v3

    invoke-virtual {v3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const/high16 v7, 0x48000000    # 131072.0f

    .line 366
    invoke-static {p1, v8, v3, v7}, Landroid/app/PendingIntent;->getService(Landroid/content/Context;ILandroid/content/Intent;I)Landroid/app/PendingIntent;

    move-result-object v3

    invoke-virtual {v3}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 369
    new-instance v7, Landroidx/core/app/NotificationCompat$Builder;

    .line 370
    const-string v9, "TimerModelNotification"

    .line 369
    invoke-direct {v7, p1, v9}, Landroidx/core/app/NotificationCompat$Builder;-><init>(Landroid/content/Context;Ljava/lang/String;)V

    .line 371
    invoke-virtual {v7, v8}, Landroidx/core/app/NotificationCompat$Builder;->setLocalOnly(Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v7

    .line 372
    invoke-virtual {v7, v0}, Landroidx/core/app/NotificationCompat$Builder;->setShowWhen(Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v7

    .line 373
    invoke-virtual {v7, v0}, Landroidx/core/app/NotificationCompat$Builder;->setAutoCancel(Z)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    .line 374
    invoke-virtual {v0, v3}, Landroidx/core/app/NotificationCompat$Builder;->setContentIntent(Landroid/app/PendingIntent;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    const/4 v3, 0x4

    .line 375
    invoke-virtual {v0, v3}, Landroidx/core/app/NotificationCompat$Builder;->setPriority(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    .line 376
    const-string v3, "alarm"

    invoke-virtual {v0, v3}, Landroidx/core/app/NotificationCompat$Builder;->setCategory(Ljava/lang/String;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    const v3, 0x7f080142

    .line 377
    invoke-virtual {v0, v3}, Landroidx/core/app/NotificationCompat$Builder;->setSmallIcon(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    .line 378
    invoke-virtual {v0, v8}, Landroidx/core/app/NotificationCompat$Builder;->setVisibility(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    .line 379
    invoke-virtual {p2}, Lcom/android/deskclock/data/NotificationModel;->getTimerNotificationMissedSortKey()Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v0, v3}, Landroidx/core/app/NotificationCompat$Builder;->setSortKey(Ljava/lang/String;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    .line 380
    new-instance v3, Landroidx/core/app/NotificationCompat$DecoratedCustomViewStyle;

    invoke-direct {v3}, Landroidx/core/app/NotificationCompat$DecoratedCustomViewStyle;-><init>()V

    invoke-virtual {v0, v3}, Landroidx/core/app/NotificationCompat$Builder;->setStyle(Landroidx/core/app/NotificationCompat$Style;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    .line 381
    invoke-virtual {v0, v2}, Landroidx/core/app/NotificationCompat$Builder;->addAction(Landroidx/core/app/NotificationCompat$Action;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    const v2, 0x7f060034

    .line 382
    invoke-static {p1, v2}, Landroidx/core/content/ContextCompat;->getColor(Landroid/content/Context;I)I

    move-result v2

    invoke-virtual {v0, v2}, Landroidx/core/app/NotificationCompat$Builder;->setColor(I)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 384
    sget-object v2, Lcom/android/deskclock/Utils;->INSTANCE:Lcom/android/deskclock/Utils;

    invoke-virtual {v2}, Lcom/android/deskclock/Utils;->isNOrLater()Z

    move-result v2

    if-eqz v2, :cond_152

    const/4 v7, 0x1

    move-object v3, p0

    move-object v8, p3

    .line 385
    invoke-direct/range {v3 .. v8}, Lcom/android/deskclock/data/TimerNotificationBuilder;->buildChronometer(Ljava/lang/String;JZLjava/lang/CharSequence;)Landroid/widget/RemoteViews;

    move-result-object p0

    invoke-virtual {v0, p0}, Landroidx/core/app/NotificationCompat$Builder;->setCustomContentView(Landroid/widget/RemoteViews;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object p0

    .line 386
    invoke-virtual {p2}, Lcom/android/deskclock/data/NotificationModel;->getTimerNotificationGroupKey()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {p0, p1}, Landroidx/core/app/NotificationCompat$Builder;->setGroup(Ljava/lang/String;)Landroidx/core/app/NotificationCompat$Builder;

    goto :goto_162

    :cond_152
    move-object v8, p3

    .line 389
    invoke-virtual {v1}, Lcom/android/deskclock/data/Timer;->getWallClockExpirationTime()J

    move-result-wide p2

    .line 388
    invoke-static {p1, p2, p3}, Lcom/android/deskclock/AlarmUtils;->getFormattedTime(Landroid/content/Context;J)Ljava/lang/String;

    move-result-object p0

    .line 390
    invoke-virtual {v0, p0}, Landroidx/core/app/NotificationCompat$Builder;->setContentText(Ljava/lang/CharSequence;)Landroidx/core/app/NotificationCompat$Builder;

    move-result-object p0

    invoke-virtual {p0, v8}, Landroidx/core/app/NotificationCompat$Builder;->setContentTitle(Ljava/lang/CharSequence;)Landroidx/core/app/NotificationCompat$Builder;

    .line 393
    :goto_162
    invoke-virtual {v0}, Landroidx/core/app/NotificationCompat$Builder;->build()Landroid/app/Notification;

    move-result-object p0

    invoke-virtual {p0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    return-object p0
.end method

.method public final isChannelCreated(Landroidx/core/app/NotificationManagerCompat;)Z
    .registers 2

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 55
    const-string p0, "TimerModelNotification"

    invoke-virtual {p1, p0}, Landroidx/core/app/NotificationManagerCompat;->getNotificationChannelCompat(Ljava/lang/String;)Landroidx/core/app/NotificationChannelCompat;

    move-result-object p0

    if-eqz p0, :cond_d

    const/4 p0, 0x1

    return p0

    :cond_d
    const/4 p0, 0x0

    return p0
.end method
