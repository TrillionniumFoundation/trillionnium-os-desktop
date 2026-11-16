.method public getTasks(IZZI)Ljava/util/List;
    .registers 12

    #@0
    .line 2619
    invoke-static {}, Landroid/os/Binder;->getCallingUid()I

    #@3
    move-result v4

    #@4
    .line 2620
    invoke-static {}, Landroid/os/Binder;->getCallingPid()I

    #@7
    move-result v0

    #@8
    const/4 v1, 0x0

    #@9
    if-eqz p3, :cond_e

    #@b
    const/16 p3, 0x8

    #@d
    goto :goto_f

    #@e
    :cond_e
    move p3, v1

    #@f
    :goto_f
    or-int/2addr p2, p3

    #@10
    .line 2624
    invoke-virtual {p0, v0, v4}, Lcom/android/server/wm/ActivityTaskManagerService;->isCrossUserAllowed(II)Z

    #@13
    move-result p3

    #@14
    if-eqz p3, :cond_18

    #@16
    const/4 p3, 0x4

    #@17
    goto :goto_19

    #@18
    :cond_18
    move p3, v1

    #@19
    :goto_19
    or-int/2addr p2, p3

    #@1a
    .line 2626
    invoke-virtual {p0}, Lcom/android/server/wm/ActivityTaskManagerService;->getUserManager()Lcom/android/server/pm/UserManagerService;

    #@1d
    move-result-object p3

    #@1e
    .line 2627
    invoke-static {v4}, Landroid/os/UserHandle;->getUserId(I)I

    #@21
    move-result v2

    #@22
    const/4 v3, 0x1

    #@23
    .line 2626
    invoke-virtual {p3, v2, v3}, Lcom/android/server/pm/UserManagerService;->getProfileIds(IZ)[I

    #@26
    move-result-object p3

    #@27
    .line 2628
    new-instance v5, Landroid/util/ArraySet;

    #@29
    invoke-direct {v5}, Landroid/util/ArraySet;-><init>()V

    #@2c
    move v2, v1

    #@2d
    .line 2629
    :goto_2d
    array-length v3, p3

    #@2e
    if-ge v2, v3, :cond_3c

    #@30
    .line 2630
    aget v3, p3, v2

    #@32
    invoke-static {v3}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    #@35
    move-result-object v3

    #@36
    invoke-virtual {v5, v3}, Landroid/util/ArraySet;->add(Ljava/lang/Object;)Z

    #@39
    add-int/lit8 v2, v2, 0x1

    #@3b
    goto :goto_2d

    #@3c
    .line 2632
    :cond_3c
    new-instance v2, Ljava/util/ArrayList;

    #@3e
    invoke-direct {v2}, Ljava/util/ArrayList;-><init>()V

    #@41
    .line 2634
    iget-object p3, p0, Lcom/android/server/wm/ActivityTaskManagerService;->mGlobalLock:Lcom/android/server/wm/WindowManagerGlobalLock;

    #@43
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->traceBeforeWmsLock()V

    #@46
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->boostPriorityForLockedSection()V

    #@49
    monitor-enter p3

    #@4a
    :try_start_4a
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->traceAfterWmsLock()V

    #@4d
    .line 2637
    const-string v3, "getTasks"

    #@4f
    invoke-virtual {p0, v3, v0, v4}, Lcom/android/server/wm/ActivityTaskManagerService;->isGetTasksAllowed(Ljava/lang/String;II)Z

    #@52
    move-result v0

    #@53
    if-eqz v0, :cond_56

    #@55
    const/4 v1, 0x2

    #@56
    :cond_56
    or-int v3, p2, v1

    #@58
    .line 2639
    iget-object v0, p0, Lcom/android/server/wm/ActivityTaskManagerService;->mRootWindowContainer:Lcom/android/server/wm/RootWindowContainer;

    #@5a
    move v1, p1

    #@5b
    move v6, p4

    #@5c
    invoke-virtual/range {v0 .. v6}, Lcom/android/server/wm/RootWindowContainer;->getRunningTasks(ILjava/util/List;IILandroid/util/ArraySet;I)V

    #@5f
    .line 2641
    monitor-exit p3
    :try_end_60
    .catchall {:try_start_4a .. :try_end_60} :catchall_67

    #@60
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->resetPriorityAfterLockedSection()V

    #@63
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->traceAfterWmsUnlock()V

    #@66
    return-object v2

    #@67
    :catchall_67
    move-exception v0

    #@68
    move-object p0, v0

    #@69
    :try_start_69
    monitor-exit p3
    :try_end_6a
    .catchall {:try_start_69 .. :try_end_6a} :catchall_67

    #@6a
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->resetPriorityAfterLockedSection()V

    #@6d
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->traceAfterWmsUnlock()V

    #@70
    throw p0
.end method
