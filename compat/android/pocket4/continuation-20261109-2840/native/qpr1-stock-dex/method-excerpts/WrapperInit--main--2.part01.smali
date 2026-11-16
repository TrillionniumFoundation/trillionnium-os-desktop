.method public static blacklist main([Ljava/lang/String;)V
    .registers 8
    .param p0, "args"    # [Ljava/lang/String;

    #@0
    .line 66
    const/4 v0, 0x0

    #@1
    aget-object v1, p0, v0

    #@3
    const/16 v2, 0xa

    #@5
    invoke-static {v1, v2}, Ljava/lang/Integer;->parseInt(Ljava/lang/String;I)I

    #@8
    move-result v1

    #@9
    .line 67
    .local v1, "fdNum":I
    const/4 v3, 0x1

    #@a
    aget-object v3, p0, v3

    #@c
    invoke-static {v3, v2}, Ljava/lang/Integer;->parseInt(Ljava/lang/String;I)I

    #@f
    move-result v2

    #@10
    .line 71
    .local v2, "targetSdkVersion":I
    if-eqz v1, :cond_42

    #@12
    .line 72
    new-instance v3, Ljava/io/FileDescriptor;

    #@14
    invoke-direct {v3}, Ljava/io/FileDescriptor;-><init>()V

    #@17
    .line 74
    .local v3, "fd":Ljava/io/FileDescriptor;
    :try_start_17
    invoke-virtual {v3, v1}, Ljava/io/FileDescriptor;->setInt$(I)V

    #@1a
    .line 75
    new-instance v4, Ljava/io/DataOutputStream;

    #@1c
    new-instance v5, Ljava/io/FileOutputStream;

    #@1e
    invoke-direct {v5, v3}, Ljava/io/FileOutputStream;-><init>(Ljava/io/FileDescriptor;)V

    #@21
    invoke-direct {v4, v5}, Ljava/io/DataOutputStream;-><init>(Ljava/io/OutputStream;)V

    #@24
    .line 76
    .local v4, "os":Ljava/io/DataOutputStream;
    invoke-static {}, Landroid/os/Process;->myPid()I

    #@27
    move-result v5

    #@28
    invoke-virtual {v4, v5}, Ljava/io/DataOutputStream;->writeInt(I)V

    #@2b
    .line 77
    invoke-virtual {v4}, Ljava/io/DataOutputStream;->close()V
    :try_end_2e
    .catch Ljava/io/IOException; {:try_start_17 .. :try_end_2e} :catch_31
    .catchall {:try_start_17 .. :try_end_2e} :catchall_2f

    #@2e
    .line 81
    .end local v4    # "os":Ljava/io/DataOutputStream;
    goto :goto_3a

    #@2f
    :catchall_2f
    move-exception v0

    #@30
    goto :goto_3e

    #@31
    .line 78
    :catch_31
    move-exception v4

    #@32
    .line 79
    .local v4, "ex":Ljava/io/IOException;
    :try_start_32
    const-string v5, "AndroidRuntime"

    #@34
    const-string v6, "Could not write pid of wrapped process to Zygote pipe."

    #@36
    invoke-static {v5, v6, v4}, Landroid/util/Slog;->d(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I
    :try_end_39
    .catchall {:try_start_32 .. :try_end_39} :catchall_2f

    #@39
    .line 81
    nop

    #@3a
    .end local v4    # "ex":Ljava/io/IOException;
    :goto_3a
    invoke-static {v3}, Llibcore/io/IoUtils;->closeQuietly(Ljava/io/FileDescriptor;)V

    #@3d
    .line 82
    goto :goto_42

    #@3e
    .line 81
    :goto_3e
    invoke-static {v3}, Llibcore/io/IoUtils;->closeQuietly(Ljava/io/FileDescriptor;)V

    #@41
    .line 82
    throw v0

    #@42
    .line 86
    .end local v3    # "fd":Ljava/io/FileDescriptor;
    :cond_42
    :goto_42
    new-instance v3, Landroid/util/TimingsTraceLog;

    #@44
    const-string v4, "WrapperInitTiming"

    #@46
    const-wide/16 v5, 0x4000

    #@48
    invoke-direct {v3, v4, v5, v6}, Landroid/util/TimingsTraceLog;-><init>(Ljava/lang/String;J)V

    #@4b
    invoke-static {v3}, Lcom/android/internal/os/ZygoteInit;->preload(Landroid/util/TimingsTraceLog;)V

    #@4e
    .line 90
    array-length v3, p0

    #@4f
    const/4 v4, 0x2

    #@50
    sub-int/2addr v3, v4

    #@51
    new-array v3, v3, [Ljava/lang/String;

    #@53
    .line 91
    .local v3, "runtimeArgs":[Ljava/lang/String;
    array-length v5, v3

    #@54
    invoke-static {p0, v4, v3, v0, v5}, Ljava/lang/System;->arraycopy(Ljava/lang/Object;ILjava/lang/Object;II)V

    #@57
    .line 92
    invoke-static {v2, v3}, Lcom/android/internal/os/WrapperInit;->wrapperInit(I[Ljava/lang/String;)Ljava/lang/Runnable;

    #@5a
    move-result-object v0

    #@5b
    .line 94
    .local v0, "r":Ljava/lang/Runnable;
    invoke-interface {v0}, Ljava/lang/Runnable;->run()V

    #@5e
    .line 95
    return-void
.end method
