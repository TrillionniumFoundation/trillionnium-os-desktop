.method public runStackList(Ljava/io/PrintWriter;)I
    .registers 3

    #@0
    .line 3990
    iget-object p0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mTaskInterface:Landroid/app/IActivityTaskManager;

    #@2
    invoke-interface {p0}, Landroid/app/IActivityTaskManager;->getAllRootTaskInfos()Ljava/util/List;

    #@5
    move-result-object p0

    #@6
    .line 3991
    invoke-interface {p0}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    #@9
    move-result-object p0

    #@a
    :goto_a
    invoke-interface {p0}, Ljava/util/Iterator;->hasNext()Z

    #@d
    move-result v0

    #@e
    if-eqz v0, :cond_1a

    #@10
    invoke-interface {p0}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    #@13
    move-result-object v0

    #@14
    check-cast v0, Landroid/app/ActivityTaskManager$RootTaskInfo;

    #@16
    .line 3992
    invoke-virtual {p1, v0}, Ljava/io/PrintWriter;->println(Ljava/lang/Object;)V

    #@19
    goto :goto_a

    #@1a
    :cond_1a
    const/4 p0, 0x0

    #@1b
    return p0
.end method
