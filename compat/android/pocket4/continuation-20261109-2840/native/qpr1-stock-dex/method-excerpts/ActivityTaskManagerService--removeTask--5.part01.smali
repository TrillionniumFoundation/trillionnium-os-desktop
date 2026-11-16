.method public removeTask(ILjava/lang/String;)Z
    .registers 5

    #@0
    .line 2317
    iget-object v0, p0, Lcom/android/server/wm/ActivityTaskManagerService;->mRootWindowContainer:Lcom/android/server/wm/RootWindowContainer;

    #@2
    const/4 v1, 0x1

    #@3
    invoke-virtual {v0, p1, v1}, Lcom/android/server/wm/RootWindowContainer;->anyTaskForId(II)Lcom/android/server/wm/Task;

    #@6
    move-result-object v0

    #@7
    if-nez v0, :cond_1e

    #@9
    .line 2320
    new-instance p0, Ljava/lang/StringBuilder;

    #@b
    const-string p2, "removeTask: No task remove with id="

    #@d
    invoke-direct {p0, p2}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@10
    invoke-virtual {p0, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@13
    invoke-virtual {p0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@16
    move-result-object p0

    #@17
    const-string p1, "ActivityTaskManager"

    #@19
    invoke-static {p1, p0}, Landroid/util/Slog;->w(Ljava/lang/String;Ljava/lang/String;)I

    #@1c
    const/4 p0, 0x0

    #@1d
    return p0

    #@1e
    .line 2323
    :cond_1e
    invoke-virtual {p0, v0, p2}, Lcom/android/server/wm/ActivityTaskManagerService;->removeTask(Lcom/android/server/wm/Task;Ljava/lang/String;)V

    #@21
    return v1
.end method
