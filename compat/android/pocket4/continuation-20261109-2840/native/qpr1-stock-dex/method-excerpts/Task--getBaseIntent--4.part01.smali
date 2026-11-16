.method public getBaseIntent()Landroid/content/Intent;
    .registers 2

    #@0
    .line 1530
    iget-object v0, p0, Lcom/android/server/wm/Task;->intent:Landroid/content/Intent;

    #@2
    if-eqz v0, :cond_5

    #@4
    return-object v0

    #@5
    .line 1531
    :cond_5
    iget-object v0, p0, Lcom/android/server/wm/Task;->affinityIntent:Landroid/content/Intent;

    #@7
    if-eqz v0, :cond_a

    #@9
    return-object v0

    #@a
    .line 1533
    :cond_a
    invoke-virtual {p0}, Lcom/android/server/wm/WindowContainer;->getTopMostTask()Lcom/android/server/wm/Task;

    #@d
    move-result-object v0

    #@e
    if-eq v0, p0, :cond_17

    #@10
    if-eqz v0, :cond_17

    #@12
    .line 1534
    invoke-virtual {v0}, Lcom/android/server/wm/Task;->getBaseIntent()Landroid/content/Intent;

    #@15
    move-result-object p0

    #@16
    return-object p0

    #@17
    :cond_17
    const/4 p0, 0x0

    #@18
    return-object p0
.end method
