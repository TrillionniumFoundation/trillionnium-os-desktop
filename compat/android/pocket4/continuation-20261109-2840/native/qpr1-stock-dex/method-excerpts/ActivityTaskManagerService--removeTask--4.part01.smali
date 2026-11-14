.method public removeTask(I)Z
    .registers 8

    #@0
    .line 2304
    const-string v0, "remove-by-pid#"

    #@2
    iget-object v1, p0, Lcom/android/server/wm/ActivityTaskManagerService;->mAmInternal:Landroid/app/ActivityManagerInternal;

    #@4
    const-string v2, "android.permission.REMOVE_TASKS"

    #@6
    const-string v3, "removeTask()"

    #@8
    invoke-virtual {v1, v2, v3}, Landroid/app/ActivityManagerInternal;->enforceCallingPermission(Ljava/lang/String;Ljava/lang/String;)V

    #@b
    .line 2305
    iget-object v1, p0, Lcom/android/server/wm/ActivityTaskManagerService;->mGlobalLock:Lcom/android/server/wm/WindowManagerGlobalLock;

    #@d
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->traceBeforeWmsLock()V

    #@10
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->boostPriorityForLockedSection()V

    #@13
    monitor-enter v1

    #@14
    :try_start_14
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->traceAfterWmsLock()V

    #@17
    .line 2306
    invoke-static {}, Landroid/os/Binder;->getCallingPid()I

    #@1a
    move-result v2

    #@1b
    .line 2307
    invoke-static {}, Landroid/os/Binder;->clearCallingIdentity()J

    #@1e
    move-result-wide v3
    :try_end_1f
    .catchall {:try_start_14 .. :try_end_1f} :catchall_3a

    #@1f
    .line 2309
    :try_start_1f
    new-instance v5, Ljava/lang/StringBuilder;

    #@21
    invoke-direct {v5, v0}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@24
    invoke-virtual {v5, v2}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@27
    invoke-virtual {v5}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@2a
    move-result-object v0

    #@2b
    invoke-virtual {p0, p1, v0}, Lcom/android/server/wm/ActivityTaskManagerService;->removeTask(ILjava/lang/String;)Z

    #@2e
    move-result p0
    :try_end_2f
    .catchall {:try_start_1f .. :try_end_2f} :catchall_3c

    #@2f
    .line 2311
    :try_start_2f
    invoke-static {v3, v4}, Landroid/os/Binder;->restoreCallingIdentity(J)V

    #@32
    monitor-exit v1
    :try_end_33
    .catchall {:try_start_2f .. :try_end_33} :catchall_3a

    #@33
    .line 2309
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->resetPriorityAfterLockedSection()V

    #@36
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->traceAfterWmsUnlock()V

    #@39
    return p0

    #@3a
    :catchall_3a
    move-exception p0

    #@3b
    goto :goto_41

    #@3c
    :catchall_3c
    move-exception p0

    #@3d
    .line 2311
    :try_start_3d
    invoke-static {v3, v4}, Landroid/os/Binder;->restoreCallingIdentity(J)V

    #@40
    .line 2312
    throw p0

    #@41
    .line 2313
    :goto_41
    monitor-exit v1
    :try_end_42
    .catchall {:try_start_3d .. :try_end_42} :catchall_3a

    #@42
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->resetPriorityAfterLockedSection()V

    #@45
    invoke-static {}, Lcom/android/server/wm/WindowManagerService;->traceAfterWmsUnlock()V

    #@48
    throw p0
.end method
