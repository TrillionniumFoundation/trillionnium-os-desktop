.method static blacklist execShell(Ljava/lang/String;)V
    .registers 4
    .param p0, "command"    # Ljava/lang/String;

    #@0
    .line 1194
    const-string v0, "/system/bin/sh"

    #@2
    const-string v1, "-c"

    #@4
    filled-new-array {v0, v1, p0}, [Ljava/lang/String;

    #@7
    move-result-object v0

    #@8
    .line 1196
    .local v0, "args":[Ljava/lang/String;
    const/4 v1, 0x0

    #@9
    :try_start_9
    aget-object v1, v0, v1

    #@b
    invoke-static {v1, v0}, Landroid/system/Os;->execv(Ljava/lang/String;[Ljava/lang/String;)V
    :try_end_e
    .catch Landroid/system/ErrnoException; {:try_start_9 .. :try_end_e} :catch_10

    #@e
    .line 1199
    nop

    #@f
    .line 1200
    return-void

    #@10
    .line 1197
    :catch_10
    move-exception v1

    #@11
    .line 1198
    .local v1, "e":Landroid/system/ErrnoException;
    new-instance v2, Ljava/lang/RuntimeException;

    #@13
    invoke-direct {v2, v1}, Ljava/lang/RuntimeException;-><init>(Ljava/lang/Throwable;)V

    #@16
    throw v2
.end method
