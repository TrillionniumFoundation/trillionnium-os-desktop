.method public whitelist test-api toString()Ljava/lang/String;
    .registers 8

    #@0
    .line 585
    new-instance v0, Ljava/lang/StringBuilder;

    #@2
    const/16 v1, 0x100

    #@4
    invoke-direct {v0, v1}, Ljava/lang/StringBuilder;-><init>(I)V

    #@7
    .line 586
    .local v0, "sb":Ljava/lang/StringBuilder;
    const-string v1, "RootTask id="

    #@9
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@c
    iget v1, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->taskId:I

    #@e
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@11
    .line 587
    const-string v1, " bounds="

    #@13
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@16
    iget-object v2, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->bounds:Landroid/graphics/Rect;

    #@18
    invoke-virtual {v2}, Landroid/graphics/Rect;->toShortString()Ljava/lang/String;

    #@1b
    move-result-object v2

    #@1c
    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@1f
    .line 588
    const-string v2, " displayId="

    #@21
    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@24
    iget v2, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->displayId:I

    #@26
    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@29
    .line 589
    const-string v2, " userId="

    #@2b
    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@2e
    iget v3, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->userId:I

    #@30
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@33
    .line 590
    const-string v3, "\n"

    #@35
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@38
    .line 592
    const-string v4, " configuration="

    #@3a
    invoke-virtual {v0, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@3d
    iget-object v4, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->configuration:Landroid/content/res/Configuration;

    #@3f
    invoke-virtual {v0, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@42
    .line 593
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@45
    .line 595
    const/4 v4, 0x0

    #@46
    .local v4, "i":I
    :goto_46
    iget-object v5, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->childTaskIds:[I

    #@48
    array-length v5, v5

    #@49
    if-ge v4, v5, :cond_a0

    #@4b
    .line 596
    const-string v5, "  taskId="

    #@4d
    invoke-virtual {v0, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@50
    iget-object v5, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->childTaskIds:[I

    #@52
    aget v5, v5, v4

    #@54
    invoke-virtual {v0, v5}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@57
    .line 597
    const-string v5, ": "

    #@59
    invoke-virtual {v0, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@5c
    iget-object v5, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->childTaskNames:[Ljava/lang/String;

    #@5e
    aget-object v5, v5, v4

    #@60
    invoke-virtual {v0, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@63
    .line 598
    iget-object v5, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->childTaskBounds:[Landroid/graphics/Rect;

    #@65
    if-eqz v5, :cond_75

    #@67
    .line 599
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@6a
    iget-object v5, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->childTaskBounds:[Landroid/graphics/Rect;

    #@6c
    aget-object v5, v5, v4

    #@6e
    invoke-virtual {v5}, Landroid/graphics/Rect;->toShortString()Ljava/lang/String;

    #@71
    move-result-object v5

    #@72
    invoke-virtual {v0, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@75
    .line 601
    :cond_75
    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@78
    move-result-object v5

    #@79
    iget-object v6, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->childTaskUserIds:[I

    #@7b
    aget v6, v6, v4

    #@7d
    invoke-virtual {v5, v6}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@80
    .line 602
    const-string v5, " visible="

    #@82
    invoke-virtual {v0, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@85
    move-result-object v5

    #@86
    iget-boolean v6, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->visible:Z

    #@88
    invoke-virtual {v5, v6}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@8b
    .line 603
    iget-object v5, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->topActivity:Landroid/content/ComponentName;

    #@8d
    if-eqz v5, :cond_9a

    #@8f
    .line 604
    const-string v5, " topActivity="

    #@91
    invoke-virtual {v0, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@94
    move-result-object v5

    #@95
    iget-object v6, p0, Landroid/app/ActivityTaskManager$RootTaskInfo;->topActivity:Landroid/content/ComponentName;

    #@97
    invoke-virtual {v5, v6}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@9a
    .line 606
    :cond_9a
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@9d
    .line 595
    add-int/lit8 v4, v4, 0x1

    #@9f
    goto :goto_46

    #@a0
    .line 608
    .end local v4    # "i":I
    :cond_a0
    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@a3
    move-result-object v1

    #@a4
    return-object v1
.end method
