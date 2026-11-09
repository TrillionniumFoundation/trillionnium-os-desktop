.method public runStack(Ljava/io/PrintWriter;)I
    .registers 5

    #@0
    .line 3915
    invoke-virtual {p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@3
    move-result-object v0

    #@4
    .line 3916
    invoke-virtual {v0}, Ljava/lang/Object;->hashCode()I

    #@7
    invoke-virtual {v0}, Ljava/lang/String;->hashCode()I

    #@a
    move-result v1

    #@b
    const/4 v2, -0x1

    #@c
    sparse-switch v1, :sswitch_data_70

    #@f
    :goto_f
    move v1, v2

    #@10
    goto :goto_3e

    #@11
    :sswitch_11
    const-string/jumbo v1, "move-task"

    #@14
    invoke-virtual {v0, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    #@17
    move-result v1

    #@18
    if-nez v1, :cond_1b

    #@1a
    goto :goto_f

    #@1b
    :cond_1b
    const/4 v1, 0x3

    #@1c
    goto :goto_3e

    #@1d
    :sswitch_1d
    const-string v1, "list"

    #@1f
    invoke-virtual {v0, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    #@22
    move-result v1

    #@23
    if-nez v1, :cond_26

    #@25
    goto :goto_f

    #@26
    :cond_26
    const/4 v1, 0x2

    #@27
    goto :goto_3e

    #@28
    :sswitch_28
    const-string v1, "info"

    #@2a
    invoke-virtual {v0, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    #@2d
    move-result v1

    #@2e
    if-nez v1, :cond_31

    #@30
    goto :goto_f

    #@31
    :cond_31
    const/4 v1, 0x1

    #@32
    goto :goto_3e

    #@33
    :sswitch_33
    const-string/jumbo v1, "remove"

    #@36
    invoke-virtual {v0, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    #@39
    move-result v1

    #@3a
    if-nez v1, :cond_3d

    #@3c
    goto :goto_f

    #@3d
    :cond_3d
    const/4 v1, 0x0

    #@3e
    :goto_3e
    packed-switch v1, :pswitch_data_82

    #@41
    .line 3926
    invoke-virtual {p0}, Landroid/os/ShellCommand;->getErrPrintWriter()Ljava/io/PrintWriter;

    #@44
    move-result-object p0

    #@45
    new-instance p1, Ljava/lang/StringBuilder;

    #@47
    const-string v1, "Error: unknown command \'"

    #@49
    invoke-direct {p1, v1}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@4c
    invoke-virtual {p1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@4f
    const-string v0, "\'"

    #@51
    invoke-virtual {p1, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@54
    invoke-virtual {p1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@57
    move-result-object p1

    #@58
    invoke-virtual {p0, p1}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@5b
    return v2

    #@5c
    .line 3918
    :pswitch_5c
    invoke-virtual {p0, p1}, Lcom/android/server/am/ActivityManagerShellCommand;->runStackMoveTask(Ljava/io/PrintWriter;)I

    #@5f
    move-result p0

    #@60
    return p0

    #@61
    .line 3920
    :pswitch_61
    invoke-virtual {p0, p1}, Lcom/android/server/am/ActivityManagerShellCommand;->runStackList(Ljava/io/PrintWriter;)I

    #@64
    move-result p0

    #@65
    return p0

    #@66
    .line 3922
    :pswitch_66
    invoke-virtual {p0, p1}, Lcom/android/server/am/ActivityManagerShellCommand;->runRootTaskInfo(Ljava/io/PrintWriter;)I

    #@69
    move-result p0

    #@6a
    return p0

    #@6b
    .line 3924
    :pswitch_6b
    invoke-virtual {p0, p1}, Lcom/android/server/am/ActivityManagerShellCommand;->runRootTaskRemove(Ljava/io/PrintWriter;)I

    #@6e
    move-result p0

    #@6f
    return p0

    #@70
    :sswitch_data_70
    .sparse-switch
        -0x37b5077c -> :sswitch_33
        0x3164ae -> :sswitch_28
        0x32b09e -> :sswitch_1d
        0x3ceed601 -> :sswitch_11
    .end sparse-switch

    #@82
    :pswitch_data_82
    .packed-switch 0x0
        :pswitch_6b
        :pswitch_66
        :pswitch_61
        :pswitch_5c
    .end packed-switch
.end method
