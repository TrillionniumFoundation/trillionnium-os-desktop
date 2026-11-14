.method public removeTask(Lcom/android/server/wm/Task;Ljava/lang/String;)V
    .registers 4

    #@0
    .line 2328
    invoke-virtual {p1}, Lcom/android/server/wm/Task;->isLeafTask()Z

    #@3
    move-result v0

    #@4
    .line 2331
    iget-object p0, p0, Lcom/android/server/wm/ActivityTaskManagerService;->mTaskSupervisor:Lcom/android/server/wm/ActivityTaskSupervisor;

    #@6
    if-eqz v0, :cond_d

    #@8
    const/4 v0, 0x1

    #@9
    .line 2329
    invoke-virtual {p0, p1, v0, v0, p2}, Lcom/android/server/wm/ActivityTaskSupervisor;->removeTask(Lcom/android/server/wm/Task;ZZLjava/lang/String;)V

    #@c
    return-void

    #@d
    .line 2331
    :cond_d
    invoke-virtual {p0, p1}, Lcom/android/server/wm/ActivityTaskSupervisor;->removeRootTask(Lcom/android/server/wm/Task;)V

    #@10
    return-void
.end method
