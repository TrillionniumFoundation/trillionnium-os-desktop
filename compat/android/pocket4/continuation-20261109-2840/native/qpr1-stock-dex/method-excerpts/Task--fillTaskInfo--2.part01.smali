.method public fillTaskInfo(Landroid/app/TaskInfo;Z)V
    .registers 4

    #@0
    .line 3485
    invoke-virtual {p0}, Lcom/android/server/wm/TaskFragment;->getDisplayArea()Lcom/android/server/wm/TaskDisplayArea;

    #@3
    move-result-object v0

    #@4
    invoke-virtual {p0, p1, p2, v0}, Lcom/android/server/wm/Task;->fillTaskInfo(Landroid/app/TaskInfo;ZLcom/android/server/wm/TaskDisplayArea;)V

    #@7
    return-void
.end method
