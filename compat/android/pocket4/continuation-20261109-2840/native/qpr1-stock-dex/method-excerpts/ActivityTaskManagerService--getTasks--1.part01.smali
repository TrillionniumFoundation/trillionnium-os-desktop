.method public getTasks(I)Ljava/util/List;
    .registers 4

    #@0
    const/4 v0, 0x0

    #@1
    const/4 v1, -0x1

    #@2
    .line 2600
    invoke-virtual {p0, p1, v0, v0, v1}, Lcom/android/server/wm/ActivityTaskManagerService;->getTasks(IZZI)Ljava/util/List;

    #@5
    move-result-object p0

    #@6
    return-object p0
.end method
