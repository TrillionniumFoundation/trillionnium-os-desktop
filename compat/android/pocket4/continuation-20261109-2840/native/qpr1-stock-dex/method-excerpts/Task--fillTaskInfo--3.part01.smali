.method public fillTaskInfo(Landroid/app/TaskInfo;ZLcom/android/server/wm/TaskDisplayArea;)V
    .registers 14

    #@0
    .line 3495
    iget-object v0, p1, Landroid/app/TaskInfo;->launchCookies:Ljava/util/ArrayList;

    #@2
    invoke-virtual {v0}, Ljava/util/ArrayList;->clear()V

    #@5
    .line 3496
    iget-object v0, p0, Lcom/android/server/wm/Task;->mLaunchCookie:Landroid/os/IBinder;

    #@7
    invoke-virtual {p1, v0}, Landroid/app/TaskInfo;->addLaunchCookie(Landroid/os/IBinder;)V

    #@a
    .line 3497
    iget-object v0, p0, Lcom/android/server/wm/TaskFragment;->mTaskSupervisor:Lcom/android/server/wm/ActivityTaskSupervisor;

    #@c
    iget-object v0, v0, Lcom/android/server/wm/ActivityTaskSupervisor;->mTaskInfoHelper:Lcom/android/server/wm/ActivityTaskSupervisor$TaskInfoHelper;

    #@e
    invoke-virtual {v0, p0, p1}, Lcom/android/server/wm/ActivityTaskSupervisor$TaskInfoHelper;->fillAndReturnTop(Lcom/android/server/wm/Task;Landroid/app/TaskInfo;)Lcom/android/server/wm/ActivityRecord;

    #@11
    move-result-object v0

    #@12
    .line 3499
    invoke-virtual {p0}, Lcom/android/server/wm/Task;->getUserId()I

    #@15
    move-result v1

    #@16
    iput v1, p1, Landroid/app/TaskInfo;->userId:I

    #@18
    .line 3500
    iget v1, p0, Lcom/android/server/wm/Task;->mTaskId:I

    #@1a
    iput v1, p1, Landroid/app/TaskInfo;->taskId:I

    #@1c
    .line 3501
    iget v1, p0, Lcom/android/server/wm/Task;->effectiveUid:I

    #@1e
    iput v1, p1, Landroid/app/TaskInfo;->effectiveUid:I

    #@20
    const/4 v1, 0x0

    #@21
    .line 3502
    iput v1, p1, Landroid/app/TaskInfo;->seqId:I

    #@23
    .line 3503
    invoke-virtual {p0}, Lcom/android/server/wm/TaskFragment;->getDisplayId()I

    #@26
    move-result v2

    #@27
    iput v2, p1, Landroid/app/TaskInfo;->displayId:I

    #@29
    const/4 v2, -0x1

    #@2a
    if-eqz p3, :cond_2f

    #@2c
    .line 3504
    iget v3, p3, Lcom/android/server/wm/DisplayArea;->mFeatureId:I

    #@2e
    goto :goto_30

    #@2f
    :cond_2f
    move v3, v2

    #@30
    :goto_30
    iput v3, p1, Landroid/app/TaskInfo;->displayAreaFeatureId:I

    #@32
    .line 3505
    invoke-virtual {p0}, Lcom/android/server/wm/Task;->getBaseIntent()Landroid/content/Intent;

    #@35
    move-result-object v3

    #@36
    if-nez v3, :cond_3a

    #@38
    move v4, v1

    #@39
    goto :goto_3e

    #@3a
    .line 3508
    :cond_3a
    invoke-virtual {v3}, Landroid/content/Intent;->getFlags()I

    #@3d
    move-result v4

    #@3e
    :goto_3e
    if-nez v3, :cond_46

    #@40
    .line 3510
    new-instance p2, Landroid/content/Intent;

    #@42
    invoke-direct {p2}, Landroid/content/Intent;-><init>()V

    #@45
    goto :goto_52

    #@46
    :cond_46
    if-eqz p2, :cond_4d

    #@48
    .line 3511
    invoke-virtual {v3}, Landroid/content/Intent;->cloneFilter()Landroid/content/Intent;

    #@4b
    move-result-object p2

    #@4c
    goto :goto_52

    #@4d
    :cond_4d
    new-instance p2, Landroid/content/Intent;

    #@4f
    invoke-direct {p2, v3}, Landroid/content/Intent;-><init>(Landroid/content/Intent;)V

    #@52
    :goto_52
    iput-object p2, p1, Landroid/app/TaskInfo;->baseIntent:Landroid/content/Intent;

    #@54
    .line 3512
    invoke-virtual {p2, v4}, Landroid/content/Intent;->setFlags(I)Landroid/content/Intent;

    #@57
    const/4 p2, 0x1

    #@58
    if-eqz v0, :cond_5c

    #@5a
    move v3, p2

    #@5b
    goto :goto_5d

    #@5c
    :cond_5c
    move v3, v1

    #@5d
    .line 3514
    :goto_5d
    iput-boolean v3, p1, Landroid/app/TaskInfo;->isRunning:Z

    #@5f
    const/4 v3, 0x0

    #@60
    if-eqz v0, :cond_65

    #@62
    .line 3515
    iget-object v4, v0, Lcom/android/server/wm/ActivityRecord;->mActivityComponent:Landroid/content/ComponentName;

    #@64
    goto :goto_66

    #@65
    :cond_65
    move-object v4, v3

    #@66
    :goto_66
    iput-object v4, p1, Landroid/app/TaskInfo;->topActivity:Landroid/content/ComponentName;

    #@68
    .line 3516
    iget-object v4, p0, Lcom/android/server/wm/Task;->origActivity:Landroid/content/ComponentName;

    #@6a
    iput-object v4, p1, Landroid/app/TaskInfo;->origActivity:Landroid/content/ComponentName;

    #@6c
    .line 3517
    iget-object v4, p0, Lcom/android/server/wm/Task;->realActivity:Landroid/content/ComponentName;

    #@6e
    iput-object v4, p1, Landroid/app/TaskInfo;->realActivity:Landroid/content/ComponentName;

    #@70
    .line 3518
    iget-boolean v4, p0, Lcom/android/server/wm/Task;->mRealActivityAppLockEnabled:Z

    #@72
    iput-boolean v4, p1, Landroid/app/TaskInfo;->isRealActivityAppLockEnabled:Z

    #@74
    .line 3519
    iget-wide v4, p0, Lcom/android/server/wm/Task;->lastActiveTime:J

    #@76
    iput-wide v4, p1, Landroid/app/TaskInfo;->lastActiveTime:J

    #@78
    .line 3520
    new-instance v4, Landroid/app/ActivityManager$TaskDescription;

    #@7a
    invoke-virtual {p0}, Lcom/android/server/wm/Task;->getTaskDescription()Landroid/app/ActivityManager$TaskDescription;

    #@7d
    move-result-object v5

    #@7e
    invoke-direct {v4, v5}, Landroid/app/ActivityManager$TaskDescription;-><init>(Landroid/app/ActivityManager$TaskDescription;)V

    #@81
    iput-object v4, p1, Landroid/app/TaskInfo;->taskDescription:Landroid/app/ActivityManager$TaskDescription;

    #@83
    .line 3521
    invoke-virtual {p0, p3}, Lcom/android/server/wm/TaskFragment;->supportsMultiWindowInDisplayArea(Lcom/android/server/wm/TaskDisplayArea;)Z

    #@86
    move-result v4

    #@87
    iput-boolean v4, p1, Landroid/app/TaskInfo;->supportsMultiWindow:Z

    #@89
    .line 3523
    invoke-virtual {p0, p3}, Lcom/android/server/wm/TaskFragment;->supportsMultiWindowWithoutConstraintsInDisplayArea(Lcom/android/server/wm/TaskDisplayArea;)Z

    #@8c
    move-result p3

    #@8d
    iput-boolean p3, p1, Landroid/app/TaskInfo;->supportsMultiWindowWithoutConstraints:Z

    #@8f
    .line 3524
    iget-object p3, p1, Landroid/app/TaskInfo;->configuration:Landroid/content/res/Configuration;

    #@91
    invoke-virtual {p0}, Lcom/android/server/wm/ConfigurationContainer;->getConfiguration()Landroid/content/res/Configuration;

    #@94
    move-result-object v4

    #@95
    invoke-virtual {p3, v4}, Landroid/content/res/Configuration;->setTo(Landroid/content/res/Configuration;)V

    #@98
    .line 3527
    iget-object p3, p1, Landroid/app/TaskInfo;->configuration:Landroid/content/res/Configuration;

    #@9a
    iget-object p3, p3, Landroid/content/res/Configuration;->windowConfiguration:Landroid/app/WindowConfiguration;

    #@9c
    invoke-virtual {p0}, Lcom/android/server/wm/TaskFragment;->getActivityType()I

    #@9f
    move-result v4

    #@a0
    invoke-virtual {p3, v4}, Landroid/app/WindowConfiguration;->setActivityType(I)V

    #@a3
    .line 3528
    iget-object p3, p1, Landroid/app/TaskInfo;->configuration:Landroid/content/res/Configuration;

    #@a5
    iget-object p3, p3, Landroid/content/res/Configuration;->windowConfiguration:Landroid/app/WindowConfiguration;

    #@a7
    invoke-virtual {p0}, Lcom/android/server/wm/ConfigurationContainer;->getWindowingMode()I

    #@aa
    move-result v4

    #@ab
    invoke-virtual {p3, v4}, Landroid/app/WindowConfiguration;->setWindowingMode(I)V

    #@ae
    .line 3529
    iget-object p3, p0, Lcom/android/server/wm/WindowContainer;->mRemoteToken:Lcom/android/server/wm/WindowContainer$RemoteToken;

    #@b0
    invoke-virtual {p3}, Lcom/android/server/wm/WindowContainer$RemoteToken;->toWindowContainerToken()Landroid/window/WindowContainerToken;

    #@b3
    move-result-object p3

    #@b4
    iput-object p3, p1, Landroid/app/TaskInfo;->token:Landroid/window/WindowContainerToken;

    #@b6
    if-eqz v0, :cond_c4

    #@b8
    .line 3533
    invoke-virtual {v0}, Lcom/android/server/wm/ActivityRecord;->getTask()Lcom/android/server/wm/Task;

    #@bb
    move-result-object p3

    #@bc
    if-eqz p3, :cond_c4

    #@be
    invoke-virtual {v0}, Lcom/android/server/wm/ActivityRecord;->getTask()Lcom/android/server/wm/Task;

    #@c1
    move-result-object p3

    #@c2
    move-object v5, p3

    #@c3
    goto :goto_c5

    #@c4
    :cond_c4
    move-object v5, p0

    #@c5
    .line 3534
    :goto_c5
    iget p3, v5, Lcom/android/server/wm/Task;->mResizeMode:I

    #@c7
    iput p3, p1, Landroid/app/TaskInfo;->resizeMode:I

    #@c9
    .line 3535
    invoke-virtual {v5}, Lcom/android/server/wm/TaskFragment;->getActivityType()I

    #@cc
    move-result p3

    #@cd
    iput p3, p1, Landroid/app/TaskInfo;->topActivityType:I

    #@cf
    .line 3536
    invoke-virtual {v5}, Lcom/android/server/wm/Task;->getDisplayCutoutInsets()Landroid/graphics/Rect;

    #@d2
    move-result-object p3

    #@d3
    iput-object p3, p1, Landroid/app/TaskInfo;->displayCutoutInsets:Landroid/graphics/Rect;

    #@d5
    .line 3537
    invoke-virtual {p0}, Lcom/android/server/wm/Task;->isResizeable()Z

    #@d8
    move-result p3

    #@d9
    iput-boolean p3, p1, Landroid/app/TaskInfo;->isResizeable:Z

    #@db
    .line 3540
    invoke-virtual {p0}, Lcom/android/server/wm/TaskFragment;->getMinWidth()I

    #@de
    move-result p3

    #@df
    iput p3, p1, Landroid/app/TaskInfo;->minWidth:I

    #@e1
    .line 3541
    invoke-virtual {p0}, Lcom/android/server/wm/TaskFragment;->getMinHeight()I

    #@e4
    move-result p3

    #@e5
    iput p3, p1, Landroid/app/TaskInfo;->minHeight:I

    #@e7
    .line 3542
    iget-object p3, p0, Lcom/android/server/wm/WindowContainer;->mDisplayContent:Lcom/android/server/wm/DisplayContent;

    #@e9
    if-nez p3, :cond_ee

    #@eb
    const/16 p3, 0xdc

    #@ed
    goto :goto_f0

    #@ee
    .line 3543
    :cond_ee
    iget p3, p3, Lcom/android/server/wm/DisplayContent;->mMinSizeOfResizeableTaskDp:I

    #@f0
    :goto_f0
    iput p3, p1, Landroid/app/TaskInfo;->defaultMinSize:I

    #@f2
    .line 3544
    invoke-virtual {p0}, Lcom/android/server/wm/Task;->getRelativePosition()Landroid/graphics/Point;

    #@f5
    move-result-object p3

    #@f6
    iput-object p3, p1, Landroid/app/TaskInfo;->positionInParent:Landroid/graphics/Point;

    #@f8
    if-eqz v0, :cond_fd

    #@fa
    .line 3546
    iget-object p3, v0, Lcom/android/server/wm/ActivityRecord;->info:Landroid/content/pm/ActivityInfo;

    #@fc
    goto :goto_fe

    #@fd
    :cond_fd
    move-object p3, v3

    #@fe
    :goto_fe
    iput-object p3, p1, Landroid/app/TaskInfo;->topActivityInfo:Landroid/content/pm/ActivityInfo;

    #@100
    .line 3547
    invoke-static {v0}, Lcom/android/server/wm/Task;->getPictureInPictureParams(Lcom/android/server/wm/ActivityRecord;)Landroid/app/PictureInPictureParams;

    #@103
    move-result-object p3

    #@104
    iput-object p3, p1, Landroid/app/TaskInfo;->pictureInPictureParams:Landroid/app/PictureInPictureParams;

    #@106
    if-eqz p3, :cond_11b

    #@108
    .line 3549
    invoke-virtual {p3}, Landroid/app/PictureInPictureParams;->isLaunchIntoPip()Z

    #@10b
    move-result p3

    #@10c
    if-eqz p3, :cond_11b

    #@10e
    .line 3550
    invoke-virtual {v0}, Lcom/android/server/wm/ActivityRecord;->getLastParentBeforePip()Lcom/android/server/wm/Task;

    #@111
    move-result-object p3

    #@112
    if-eqz p3, :cond_11b

    #@114
    .line 3551
    invoke-virtual {v0}, Lcom/android/server/wm/ActivityRecord;->getLastParentBeforePip()Lcom/android/server/wm/Task;

    #@117
    move-result-object p3

    #@118
    iget p3, p3, Lcom/android/server/wm/Task;->mTaskId:I

    #@11a
    goto :goto_11c

    #@11b
    :cond_11b
    move p3, v2

    #@11c
    :goto_11c
    iput p3, p1, Landroid/app/TaskInfo;->launchIntoPipHostTaskId:I

    #@11e
    if-eqz v0, :cond_12d

    #@120
    .line 3552
    invoke-virtual {v0}, Lcom/android/server/wm/ActivityRecord;->getLastParentBeforePip()Lcom/android/server/wm/Task;

    #@123
    move-result-object p3

    #@124
    if-eqz p3, :cond_12d

    #@126
    .line 3553
    invoke-virtual {v0}, Lcom/android/server/wm/ActivityRecord;->getLastParentBeforePip()Lcom/android/server/wm/Task;

    #@129
    move-result-object p3

    #@12a
    iget p3, p3, Lcom/android/server/wm/Task;->mTaskId:I

    #@12c
    goto :goto_12e

    #@12d
    :cond_12d
    move p3, v2

    #@12e
    :goto_12e
    iput p3, p1, Landroid/app/TaskInfo;->lastParentTaskIdBeforePip:I

    #@130
    if-eqz v0, :cond_138

    #@132
    .line 3554
    iget-boolean p3, v0, Lcom/android/server/wm/ActivityRecord;->shouldDockBigOverlays:Z

    #@134
    if-eqz p3, :cond_138

    #@136
    move p3, p2

    #@137
    goto :goto_139

    #@138
    :cond_138
    move p3, v1

    #@139
    :goto_139
    iput-boolean p3, p1, Landroid/app/TaskInfo;->shouldDockBigOverlays:Z

    #@13b
    if-eqz v0, :cond_142

    #@13d
    .line 3555
    invoke-virtual {v0}, Lcom/android/server/wm/ActivityRecord;->getLocusId()Landroid/content/LocusId;

    #@140
    move-result-object p3

    #@141
    goto :goto_143

    #@142
    :cond_142
    move-object p3, v3

    #@143
    :goto_143
    iput-object p3, p1, Landroid/app/TaskInfo;->mTopActivityLocusId:Landroid/content/LocusId;

    #@145
    if-eqz v0, :cond_14a

    #@147
    .line 3557
    iget-wide v6, v0, Lcom/android/server/wm/ActivityRecord;->mRequestOpenInBrowserEducationTimestamp:J

    #@149
    goto :goto_14c

    #@14a
    :cond_14a
    const-wide/16 v6, 0x0

    #@14c
    :goto_14c
    iput-wide v6, p1, Landroid/app/TaskInfo;->topActivityRequestOpenInBrowserEducationTimestamp:J

    #@14e
    .line 3558
    invoke-virtual {p0}, Lcom/android/server/wm/WindowContainer;->getParent()Lcom/android/server/wm/WindowContainer;

    #@151
    move-result-object p3

    #@152
    if-eqz p3, :cond_15d

    #@154
    invoke-virtual {p0}, Lcom/android/server/wm/WindowContainer;->getParent()Lcom/android/server/wm/WindowContainer;

    #@157
    move-result-object p3

    #@158
    invoke-virtual {p3}, Lcom/android/server/wm/WindowContainer;->asTask()Lcom/android/server/wm/Task;

    #@15b
    move-result-object p3

    #@15c
    goto :goto_15e

    #@15d
    :cond_15d
    move-object p3, v3

    #@15e
    :goto_15e
    if-eqz p3, :cond_166

    #@160
    .line 3559
    iget-boolean v4, p3, Lcom/android/server/wm/TaskFragment;->mCreatedByOrganizer:Z

    #@162
    if-eqz v4, :cond_166

    #@164
    .line 3560
    iget v2, p3, Lcom/android/server/wm/Task;->mTaskId:I

    #@166
    .line 3561
    :cond_166
    iput v2, p1, Landroid/app/TaskInfo;->parentTaskId:I

    #@168
    .line 3562
    invoke-virtual {p0}, Lcom/android/server/wm/Task;->isFocused()Z

    #@16b
    move-result p3

    #@16c
    iput-boolean p3, p1, Landroid/app/TaskInfo;->isFocused:Z

    #@16e
    .line 3563
    invoke-virtual {p0}, Lcom/android/server/wm/Task;->isInteractive()Z

    #@171
    move-result p3

    #@172
    iput-boolean p3, p1, Landroid/app/TaskInfo;->isInteractive:Z

    #@174
    .line 3564
    invoke-virtual {p0}, Lcom/android/server/wm/Task;->hasVisibleChildren()Z

    #@177
    move-result p3

    #@178
    iput-boolean p3, p1, Landroid/app/TaskInfo;->isVisible:Z

    #@17a
    .line 3565
    invoke-virtual {p0}, Lcom/android/server/wm/WindowContainer;->isVisibleRequested()Z

    #@17d
    move-result p3

    #@17e
    iput-boolean p3, p1, Landroid/app/TaskInfo;->isVisibleRequested:Z

    #@180
    if-eqz v0, :cond_18a

    #@182
    .line 3566
    invoke-virtual {v0}, Lcom/android/server/wm/ActivityRecord;->isNoDisplay()Z

    #@185
    move-result p3

    #@186
    if-eqz p3, :cond_18a

    #@188
    move p3, p2

    #@189
    goto :goto_18b

    #@18a
    :cond_18a
    move p3, v1

    #@18b
    :goto_18b
    iput-boolean p3, p1, Landroid/app/TaskInfo;->isTopActivityNoDisplay:Z

    #@18d
    .line 3567
    invoke-virtual {p0}, Lcom/android/server/wm/TaskFragment;->shouldSleepActivities()Z

    #@190
    move-result p3

    #@191
    iput-boolean p3, p1, Landroid/app/TaskInfo;->isSleeping:Z

    #@193
    if-eqz v0, :cond_19d

    #@195
    .line 3568
    invoke-virtual {v0}, Lcom/android/server/wm/ActivityRecord;->fillsParent()Z

    #@198
    move-result p3

    #@199
    if-nez p3, :cond_19d

    #@19b
    move p3, p2

    #@19c
    goto :goto_19e

    #@19d
    :cond_19d
    move p3, v1

    #@19e
    :goto_19e
    iput-boolean p3, p1, Landroid/app/TaskInfo;->isTopActivityTransparent:Z

    #@1a0
    .line 3569
    iget-object p3, p0, Lcom/android/server/wm/TaskFragment;->mAtmService:Lcom/android/server/wm/ActivityTaskManagerService;

    #@1a2
    iget-object v4, p3, Lcom/android/server/wm/ActivityTaskManagerService;->mVisibilityHelper:Lcom/android/server/wm/WindowContainerVisibilityHelper;

    #@1a4
    const/4 v8, 0x0

    #@1a5
    const/4 v9, 0x1

    #@1a6
    const/4 v6, 0x0

    #@1a7
    const/4 v7, 0x1

    #@1a8
    invoke-interface/range {v4 .. v9}, Lcom/android/server/wm/WindowContainerVisibilityHelper;->isOpaque(Lcom/android/server/wm/WindowContainer;Lcom/android/server/wm/ActivityRecord;ZZZ)Z

    #@1ab
    move-result p3

    #@1ac
    xor-int/2addr p2, p3

    #@1ad
    iput-boolean p2, p1, Landroid/app/TaskInfo;->isActivityStackTransparent:Z

    #@1af
    .line 3572
    iget-object p2, v5, Lcom/android/server/wm/Task;->mLastNonFullscreenBounds:Landroid/graphics/Rect;

    #@1b1
    iput-object p2, p1, Landroid/app/TaskInfo;->lastNonFullscreenBounds:Landroid/graphics/Rect;

    #@1b3
    .line 3573
    iget-boolean p2, p0, Lcom/android/server/wm/Task;->mLeafTaskBoundsFromOptions:Z

    #@1b5
    iput-boolean p2, p1, Landroid/app/TaskInfo;->leafTaskBoundsFromOptions:Z

    #@1b7
    if-eqz v0, :cond_1bd

    #@1b9
    .line 3575
    invoke-virtual {v0, v1}, Lcom/android/server/wm/ActivityRecord;->findMainWindow(Z)Lcom/android/server/wm/WindowState;

    #@1bc
    move-result-object v3

    #@1bd
    :cond_1bd
    if-eqz v3, :cond_1c4

    #@1bf
    .line 3578
    invoke-virtual {v3}, Lcom/android/server/wm/WindowState;->getRequestedVisibleTypes()I

    #@1c2
    move-result p2

    #@1c3
    goto :goto_1c8

    #@1c4
    .line 3579
    :cond_1c4
    invoke-static {}, Landroid/view/WindowInsets$Type;->defaultVisible()I

    #@1c7
    move-result p2

    #@1c8
    :goto_1c8
    iput p2, p1, Landroid/app/TaskInfo;->requestedVisibleTypes:I

    #@1ca
    .line 3580
    invoke-static {p0, p1, v0}, Lcom/android/server/wm/AppCompatUtils;->fillAppCompatTaskInfo(Lcom/android/server/wm/Task;Landroid/app/TaskInfo;Lcom/android/server/wm/ActivityRecord;)V

    #@1cd
    .line 3581
    invoke-static {v0}, Lcom/android/server/wm/Task;->calculateTopActivityMainWindowFrameForTaskInfo(Lcom/android/server/wm/ActivityRecord;)Landroid/graphics/Rect;

    #@1d0
    move-result-object p2

    #@1d1
    iput-object p2, p1, Landroid/app/TaskInfo;->topActivityMainWindowFrame:Landroid/graphics/Rect;

    #@1d3
    .line 3583
    iget-boolean p0, p0, Lcom/android/server/wm/Task;->mLaunchNextToBubble:Z

    #@1d5
    iput-boolean p0, p1, Landroid/app/TaskInfo;->isAppBubble:Z

    #@1d7
    return-void
.end method
