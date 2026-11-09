.method public final setIntent(Landroid/content/Intent;Landroid/content/pm/ActivityInfo;)V
    .registers 16

    #@0
    .line 1042
    invoke-virtual {p0}, Lcom/android/server/wm/Task;->isLeafTask()Z

    #@3
    move-result v0

    #@4
    if-nez v0, :cond_8

    #@6
    goto/16 :goto_160

    #@8
    .line 1044
    :cond_8
    iget v0, p2, Landroid/content/pm/ActivityInfo;->flags:I

    #@a
    and-int/lit16 v0, v0, 0x1000

    #@c
    const/4 v1, 0x0

    #@d
    const/4 v2, 0x1

    #@e
    if-nez v0, :cond_12

    #@10
    move v0, v2

    #@11
    goto :goto_13

    #@12
    :cond_12
    move v0, v1

    #@13
    :goto_13
    iput-boolean v0, p0, Lcom/android/server/wm/Task;->mNeverRelinquishIdentity:Z

    #@15
    .line 1045
    iget-object v0, p2, Landroid/content/pm/ActivityInfo;->taskAffinity:Ljava/lang/String;

    #@17
    iput-object v0, p0, Lcom/android/server/wm/Task;->affinity:Ljava/lang/String;

    #@19
    .line 1046
    iget-object v3, p0, Lcom/android/server/wm/Task;->intent:Landroid/content/Intent;

    #@1b
    if-nez v3, :cond_23

    #@1d
    .line 1050
    iput-object v0, p0, Lcom/android/server/wm/Task;->rootAffinity:Ljava/lang/String;

    #@1f
    .line 1051
    iget-object v0, p2, Landroid/content/pm/ActivityInfo;->requiredDisplayCategory:Ljava/lang/String;

    #@21
    iput-object v0, p0, Lcom/android/server/wm/Task;->mRequiredDisplayCategory:Ljava/lang/String;

    #@23
    .line 1053
    :cond_23
    invoke-virtual {p2}, Landroid/content/pm/ActivityInfo;->getUid()I

    #@26
    move-result v0

    #@27
    iput v0, p0, Lcom/android/server/wm/Task;->effectiveUid:I

    #@29
    .line 1054
    iget-object v0, p2, Landroid/content/pm/ActivityInfo;->applicationInfo:Landroid/content/pm/ApplicationInfo;

    #@2b
    invoke-virtual {v0}, Landroid/content/pm/ApplicationInfo;->isSystemApp()Z

    #@2e
    move-result v0

    #@2f
    iput-boolean v0, p0, Lcom/android/server/wm/Task;->mIsEffectivelySystemApp:Z

    #@31
    .line 1056
    iget-object v0, p2, Landroid/content/pm/ActivityInfo;->targetActivity:Ljava/lang/String;

    #@33
    const/4 v3, 0x0

    #@34
    if-nez v0, :cond_83

    #@36
    if-eqz p1, :cond_50

    #@38
    .line 1061
    invoke-virtual {p1}, Landroid/content/Intent;->getSelector()Landroid/content/Intent;

    #@3b
    move-result-object v0

    #@3c
    if-nez v0, :cond_44

    #@3e
    invoke-virtual {p1}, Landroid/content/Intent;->getSourceBounds()Landroid/graphics/Rect;

    #@41
    move-result-object v0

    #@42
    if-eqz v0, :cond_50

    #@44
    .line 1062
    :cond_44
    new-instance v0, Landroid/content/Intent;

    #@46
    invoke-direct {v0, p1}, Landroid/content/Intent;-><init>(Landroid/content/Intent;)V

    #@49
    .line 1063
    invoke-virtual {v0, v3}, Landroid/content/Intent;->setSelector(Landroid/content/Intent;)V

    #@4c
    .line 1064
    invoke-virtual {v0, v3}, Landroid/content/Intent;->setSourceBounds(Landroid/graphics/Rect;)V

    #@4f
    move-object p1, v0

    #@50
    .line 1067
    :cond_50
    sget-object v0, Lcom/android/internal/protolog/ProtoLogImpl_1081728087$Cache;->WM_DEBUG_TASKS_enabled:[Z

    #@52
    sget-object v4, Lcom/android/internal/protolog/common/LogLevel;->VERBOSE:Lcom/android/internal/protolog/common/LogLevel;

    #@54
    invoke-virtual {v4}, Lcom/android/internal/protolog/common/LogLevel;->ordinal()I

    #@57
    move-result v4

    #@58
    aget-boolean v0, v0, v4

    #@5a
    if-eqz v0, :cond_74

    #@5c
    invoke-static {p0}, Ljava/lang/String;->valueOf(Ljava/lang/Object;)Ljava/lang/String;

    #@5f
    move-result-object v0

    #@60
    invoke-static {p1}, Ljava/lang/String;->valueOf(Ljava/lang/Object;)Ljava/lang/String;

    #@63
    move-result-object v4

    #@64
    sget-object v5, Lcom/android/internal/protolog/WmProtoLogGroups;->WM_DEBUG_TASKS:Lcom/android/internal/protolog/WmProtoLogGroups;

    #@66
    const-wide/16 v8, 0x0

    #@68
    filled-new-array {v0, v4}, [Ljava/lang/Object;

    #@6b
    move-result-object v10

    #@6c
    const-wide v6, -0x1d0a0df16200cb12L    # -5.176351657627526E168

    #@71
    invoke-static/range {v5 .. v10}, Lcom/android/internal/protolog/ProtoLogImpl_1081728087;->v(Lcom/android/internal/protolog/common/IProtoLogGroup;JJ[Ljava/lang/Object;)V

    #@74
    .line 1068
    :cond_74
    iput-object p1, p0, Lcom/android/server/wm/Task;->intent:Landroid/content/Intent;

    #@76
    if-eqz p1, :cond_7d

    #@78
    .line 1069
    invoke-virtual {p1}, Landroid/content/Intent;->getComponent()Landroid/content/ComponentName;

    #@7b
    move-result-object p1

    #@7c
    goto :goto_7e

    #@7d
    :cond_7d
    move-object p1, v3

    #@7e
    :goto_7e
    iput-object p1, p0, Lcom/android/server/wm/Task;->realActivity:Landroid/content/ComponentName;

    #@80
    .line 1070
    iput-object v3, p0, Lcom/android/server/wm/Task;->origActivity:Landroid/content/ComponentName;

    #@82
    goto :goto_d7

    #@83
    .line 1072
    :cond_83
    new-instance v0, Landroid/content/ComponentName;

    #@85
    iget-object v4, p2, Landroid/content/pm/ActivityInfo;->packageName:Ljava/lang/String;

    #@87
    iget-object v5, p2, Landroid/content/pm/ActivityInfo;->targetActivity:Ljava/lang/String;

    #@89
    invoke-direct {v0, v4, v5}, Landroid/content/ComponentName;-><init>(Ljava/lang/String;Ljava/lang/String;)V

    #@8c
    if-eqz p1, :cond_c8

    #@8e
    .line 1075
    new-instance v4, Landroid/content/Intent;

    #@90
    invoke-direct {v4, p1}, Landroid/content/Intent;-><init>(Landroid/content/Intent;)V

    #@93
    .line 1076
    invoke-virtual {v4, v3}, Landroid/content/Intent;->setSelector(Landroid/content/Intent;)V

    #@96
    .line 1077
    invoke-virtual {v4, v3}, Landroid/content/Intent;->setSourceBounds(Landroid/graphics/Rect;)V

    #@99
    .line 1078
    sget-object v5, Lcom/android/internal/protolog/ProtoLogImpl_1081728087$Cache;->WM_DEBUG_TASKS_enabled:[Z

    #@9b
    sget-object v6, Lcom/android/internal/protolog/common/LogLevel;->VERBOSE:Lcom/android/internal/protolog/common/LogLevel;

    #@9d
    invoke-virtual {v6}, Lcom/android/internal/protolog/common/LogLevel;->ordinal()I

    #@a0
    move-result v6

    #@a1
    aget-boolean v5, v5, v6

    #@a3
    if-eqz v5, :cond_bd

    #@a5
    invoke-static {p0}, Ljava/lang/String;->valueOf(Ljava/lang/Object;)Ljava/lang/String;

    #@a8
    move-result-object v5

    #@a9
    invoke-static {v4}, Ljava/lang/String;->valueOf(Ljava/lang/Object;)Ljava/lang/String;

    #@ac
    move-result-object v6

    #@ad
    sget-object v7, Lcom/android/internal/protolog/WmProtoLogGroups;->WM_DEBUG_TASKS:Lcom/android/internal/protolog/WmProtoLogGroups;

    #@af
    const-wide/16 v10, 0x0

    #@b1
    filled-new-array {v5, v6}, [Ljava/lang/Object;

    #@b4
    move-result-object v12

    #@b5
    const-wide v8, 0x4ab34789b5da3d65L    # 7.21329676740986E51

    #@ba
    invoke-static/range {v7 .. v12}, Lcom/android/internal/protolog/ProtoLogImpl_1081728087;->v(Lcom/android/internal/protolog/common/IProtoLogGroup;JJ[Ljava/lang/Object;)V

    #@bd
    .line 1079
    :cond_bd
    iput-object v4, p0, Lcom/android/server/wm/Task;->intent:Landroid/content/Intent;

    #@bf
    .line 1080
    iput-object v0, p0, Lcom/android/server/wm/Task;->realActivity:Landroid/content/ComponentName;

    #@c1
    .line 1081
    invoke-virtual {p1}, Landroid/content/Intent;->getComponent()Landroid/content/ComponentName;

    #@c4
    move-result-object p1

    #@c5
    iput-object p1, p0, Lcom/android/server/wm/Task;->origActivity:Landroid/content/ComponentName;

    #@c7
    goto :goto_d7

    #@c8
    .line 1083
    :cond_c8
    iput-object v3, p0, Lcom/android/server/wm/Task;->intent:Landroid/content/Intent;

    #@ca
    .line 1084
    iput-object v0, p0, Lcom/android/server/wm/Task;->realActivity:Landroid/content/ComponentName;

    #@cc
    .line 1085
    new-instance p1, Landroid/content/ComponentName;

    #@ce
    iget-object v0, p2, Landroid/content/pm/ActivityInfo;->packageName:Ljava/lang/String;

    #@d0
    iget-object v4, p2, Landroid/content/pm/ActivityInfo;->name:Ljava/lang/String;

    #@d2
    invoke-direct {p1, v0, v4}, Landroid/content/ComponentName;-><init>(Ljava/lang/String;Ljava/lang/String;)V

    #@d5
    iput-object p1, p0, Lcom/android/server/wm/Task;->origActivity:Landroid/content/ComponentName;

    #@d7
    .line 1089
    :goto_d7
    iget-object p1, p2, Landroid/content/pm/ActivityInfo;->windowLayout:Landroid/content/pm/ActivityInfo$WindowLayout;

    #@d9
    if-nez p1, :cond_dd

    #@db
    move-object p1, v3

    #@dc
    goto :goto_df

    #@dd
    :cond_dd
    iget-object p1, p1, Landroid/content/pm/ActivityInfo$WindowLayout;->windowLayoutAffinity:Ljava/lang/String;

    #@df
    :goto_df
    iput-object p1, p0, Lcom/android/server/wm/Task;->mWindowLayoutAffinity:Ljava/lang/String;

    #@e1
    .line 1091
    iget-object p1, p0, Lcom/android/server/wm/Task;->intent:Landroid/content/Intent;

    #@e3
    if-nez p1, :cond_e7

    #@e5
    move p1, v1

    #@e6
    goto :goto_eb

    #@e7
    :cond_e7
    invoke-virtual {p1}, Landroid/content/Intent;->getFlags()I

    #@ea
    move-result p1

    #@eb
    :goto_eb
    const/high16 v0, 0x200000

    #@ed
    and-int/2addr v0, p1

    #@ee
    if-eqz v0, :cond_f2

    #@f0
    .line 1095
    iput-boolean v2, p0, Lcom/android/server/wm/Task;->rootWasReset:Z

    #@f2
    .line 1098
    :cond_f2
    invoke-virtual {p2}, Landroid/content/pm/ActivityInfo;->getUid()I

    #@f5
    move-result v0

    #@f6
    invoke-static {v0}, Landroid/os/UserHandle;->getUserId(I)I

    #@f9
    move-result v0

    #@fa
    iput v0, p0, Lcom/android/server/wm/Task;->mUserId:I

    #@fc
    .line 1110
    iget-object v0, p0, Lcom/android/server/wm/TaskFragment;->mAtmService:Lcom/android/server/wm/ActivityTaskManagerService;

    #@fe
    iget-object v0, v0, Lcom/android/server/wm/ActivityTaskManagerService;->mContext:Landroid/content/Context;

    #@100
    .line 1111
    invoke-virtual {v0}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    #@103
    move-result-object v0

    #@104
    const-string v4, "user_setup_complete"

    #@106
    iget v5, p0, Lcom/android/server/wm/Task;->mUserId:I

    #@108
    .line 1110
    invoke-static {v0, v4, v1, v5}, Landroid/provider/Settings$Secure;->getIntForUser(Landroid/content/ContentResolver;Ljava/lang/String;II)I

    #@10b
    move-result v0

    #@10c
    if-eqz v0, :cond_110

    #@10e
    move v0, v2

    #@10f
    goto :goto_111

    #@110
    :cond_110
    move v0, v1

    #@111
    :goto_111
    iput-boolean v0, p0, Lcom/android/server/wm/Task;->mUserSetupComplete:Z

    #@113
    .line 1112
    iget v0, p2, Landroid/content/pm/ActivityInfo;->flags:I

    #@115
    and-int/lit16 v0, v0, 0x2000

    #@117
    if-eqz v0, :cond_11c

    #@119
    .line 1114
    iput-boolean v2, p0, Lcom/android/server/wm/Task;->autoRemoveRecents:Z

    #@11b
    goto :goto_130

    #@11c
    :cond_11c
    const v0, 0x82000

    #@11f
    and-int/2addr p1, v0

    #@120
    const/high16 v0, 0x80000

    #@122
    if-ne p1, v0, :cond_12e

    #@124
    .line 1120
    iget p1, p2, Landroid/content/pm/ActivityInfo;->documentLaunchMode:I

    #@126
    if-eqz p1, :cond_12b

    #@128
    .line 1121
    iput-boolean v1, p0, Lcom/android/server/wm/Task;->autoRemoveRecents:Z

    #@12a
    goto :goto_130

    #@12b
    .line 1123
    :cond_12b
    iput-boolean v2, p0, Lcom/android/server/wm/Task;->autoRemoveRecents:Z

    #@12d
    goto :goto_130

    #@12e
    .line 1126
    :cond_12e
    iput-boolean v1, p0, Lcom/android/server/wm/Task;->autoRemoveRecents:Z

    #@130
    .line 1129
    :goto_130
    iget p1, p0, Lcom/android/server/wm/Task;->mResizeMode:I

    #@132
    iget v0, p2, Landroid/content/pm/ActivityInfo;->resizeMode:I

    #@134
    if-eq p1, v0, :cond_139

    #@136
    .line 1130
    iput v0, p0, Lcom/android/server/wm/Task;->mResizeMode:I

    #@138
    move v1, v2

    #@139
    .line 1133
    :cond_139
    invoke-virtual {p0, p2}, Lcom/android/server/wm/Task;->setMinDimensions(Landroid/content/pm/ActivityInfo;)Z

    #@13c
    move-result p1

    #@13d
    if-eqz p1, :cond_140

    #@13f
    goto :goto_141

    #@140
    :cond_140
    move v2, v1

    #@141
    :goto_141
    if-eqz v2, :cond_146

    #@143
    .line 1137
    invoke-virtual {p0}, Lcom/android/server/wm/Task;->updateTaskDescription()V

    #@146
    .line 1139
    :cond_146
    invoke-virtual {p2}, Landroid/content/pm/ActivityInfo;->supportsPictureInPicture()Z

    #@149
    move-result p1

    #@14a
    iput-boolean p1, p0, Lcom/android/server/wm/Task;->mSupportsPictureInPicture:Z

    #@14c
    .line 1140
    iput-object v3, p0, Lcom/android/server/wm/Task;->stringName:Ljava/lang/String;

    #@14e
    .line 1143
    iget-boolean p1, p0, Lcom/android/server/wm/Task;->inRecents:Z

    #@150
    if-eqz p1, :cond_160

    #@152
    .line 1144
    iget-object p1, p0, Lcom/android/server/wm/TaskFragment;->mTaskSupervisor:Lcom/android/server/wm/ActivityTaskSupervisor;

    #@154
    iget-object p1, p1, Lcom/android/server/wm/ActivityTaskSupervisor;->mRecentTasks:Lcom/android/server/wm/RecentTasks;

    #@156
    invoke-virtual {p1, p0}, Lcom/android/server/wm/RecentTasks;->remove(Lcom/android/server/wm/Task;)V

    #@159
    .line 1145
    iget-object p1, p0, Lcom/android/server/wm/TaskFragment;->mTaskSupervisor:Lcom/android/server/wm/ActivityTaskSupervisor;

    #@15b
    iget-object p1, p1, Lcom/android/server/wm/ActivityTaskSupervisor;->mRecentTasks:Lcom/android/server/wm/RecentTasks;

    #@15d
    invoke-virtual {p1, p0}, Lcom/android/server/wm/RecentTasks;->add(Lcom/android/server/wm/Task;)V

    #@160
    :cond_160
    :goto_160
    return-void
.end method
