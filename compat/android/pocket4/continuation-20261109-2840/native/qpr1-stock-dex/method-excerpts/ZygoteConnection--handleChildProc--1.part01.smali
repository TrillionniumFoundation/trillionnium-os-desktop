.method private blacklist handleChildProc(Lcom/android/internal/os/ZygoteArguments;Ljava/io/FileDescriptor;Z)Ljava/lang/Runnable;
    .registers 11
    .param p1, "parsedArgs"    # Lcom/android/internal/os/ZygoteArguments;
    .param p2, "pipeFd"    # Ljava/io/FileDescriptor;
    .param p3, "isZygote"    # Z

    #@0
    .line 515
    invoke-virtual {p0}, Lcom/android/internal/os/ZygoteConnection;->closeSocket()V

    #@3
    .line 517
    const-string v0, "Zygote"

    #@5
    invoke-static {p1, v0}, Lcom/android/internal/os/Zygote;->setAppProcessName(Lcom/android/internal/os/ZygoteArguments;Ljava/lang/String;)V

    #@8
    .line 520
    const-wide/16 v0, 0x40

    #@a
    invoke-static {v0, v1}, Landroid/os/Trace;->traceEnd(J)V

    #@d
    .line 521
    iget-object v0, p1, Lcom/android/internal/os/ZygoteArguments;->mInvokeWith:Ljava/lang/String;

    #@f
    if-nez v0, :cond_28

    #@11
    .line 530
    if-nez p3, :cond_21

    #@13
    .line 531
    iget v0, p1, Lcom/android/internal/os/ZygoteArguments;->mTargetSdkVersion:I

    #@15
    iget-object v1, p1, Lcom/android/internal/os/ZygoteArguments;->mDisabledCompatChanges:[J

    #@17
    iget-object v2, p1, Lcom/android/internal/os/ZygoteArguments;->mEnabledCompatChanges:[J

    #@19
    iget-object v3, p1, Lcom/android/internal/os/ZygoteArguments;->mRemainingArgs:[Ljava/lang/String;

    #@1b
    const/4 v4, 0x0

    #@1c
    invoke-static {v0, v1, v2, v3, v4}, Lcom/android/internal/os/ZygoteInit;->zygoteInit(I[J[J[Ljava/lang/String;Ljava/lang/ClassLoader;)Ljava/lang/Runnable;

    #@1f
    move-result-object v0

    #@20
    return-object v0

    #@21
    .line 536
    :cond_21
    iget-object v0, p1, Lcom/android/internal/os/ZygoteArguments;->mRemainingArgs:[Ljava/lang/String;

    #@23
    invoke-static {v0}, Lcom/android/internal/os/ZygoteInit;->childZygoteInit([Ljava/lang/String;)Ljava/lang/Runnable;

    #@26
    move-result-object v0

    #@27
    return-object v0

    #@28
    .line 522
    :cond_28
    iget-object v1, p1, Lcom/android/internal/os/ZygoteArguments;->mInvokeWith:Ljava/lang/String;

    #@2a
    iget-object v2, p1, Lcom/android/internal/os/ZygoteArguments;->mNiceName:Ljava/lang/String;

    #@2c
    iget v3, p1, Lcom/android/internal/os/ZygoteArguments;->mTargetSdkVersion:I

    #@2e
    .line 524
    invoke-static {}, Ldalvik/system/VMRuntime;->getCurrentInstructionSet()Ljava/lang/String;

    #@31
    move-result-object v4

    #@32
    iget-object v6, p1, Lcom/android/internal/os/ZygoteArguments;->mRemainingArgs:[Ljava/lang/String;

    #@34
    .line 522
    move-object v5, p2

    #@35
    .end local p2    # "pipeFd":Ljava/io/FileDescriptor;
    .local v5, "pipeFd":Ljava/io/FileDescriptor;
    invoke-static/range {v1 .. v6}, Lcom/android/internal/os/WrapperInit;->execApplication(Ljava/lang/String;Ljava/lang/String;ILjava/lang/String;Ljava/io/FileDescriptor;[Ljava/lang/String;)V

    #@38
    .line 528
    new-instance p2, Ljava/lang/IllegalStateException;

    #@3a
    const-string v0, "WrapperInit.execApplication unexpectedly returned"

    #@3c
    invoke-direct {p2, v0}, Ljava/lang/IllegalStateException;-><init>(Ljava/lang/String;)V

    #@3f
    throw p2
.end method
