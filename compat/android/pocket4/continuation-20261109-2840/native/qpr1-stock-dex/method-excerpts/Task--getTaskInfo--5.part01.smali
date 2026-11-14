.method public getTaskInfo()Landroid/app/ActivityManager$RunningTaskInfo;
    .registers 2

    #@0
    .line 3699
    new-instance v0, Landroid/app/ActivityManager$RunningTaskInfo;

    #@2
    invoke-direct {v0}, Landroid/app/ActivityManager$RunningTaskInfo;-><init>()V

    #@5
    .line 3700
    invoke-virtual {p0, v0}, Lcom/android/server/wm/Task;->fillTaskInfo(Landroid/app/TaskInfo;)V

    #@8
    return-object v0
.end method
