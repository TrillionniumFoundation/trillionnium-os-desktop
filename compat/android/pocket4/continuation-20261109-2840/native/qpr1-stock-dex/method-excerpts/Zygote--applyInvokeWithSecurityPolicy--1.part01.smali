.method static blacklist applyInvokeWithSecurityPolicy(Lcom/android/internal/os/ZygoteArguments;Landroid/net/Credentials;)V
    .registers 5
    .param p0, "args"    # Lcom/android/internal/os/ZygoteArguments;
    .param p1, "peer"    # Landroid/net/Credentials;
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Lcom/android/internal/os/ZygoteSecurityException;
        }
    .end annotation

    #@0
    .line 1102
    invoke-virtual {p1}, Landroid/net/Credentials;->getUid()I

    #@3
    move-result v0

    #@4
    .line 1104
    .local v0, "peerUid":I
    iget-object v1, p0, Lcom/android/internal/os/ZygoteArguments;->mInvokeWith:Ljava/lang/String;

    #@6
    if-eqz v1, :cond_1b

    #@8
    if-eqz v0, :cond_1b

    #@a
    iget v1, p0, Lcom/android/internal/os/ZygoteArguments;->mRuntimeFlags:I

    #@c
    const v2, 0x2000001

    #@f
    and-int/2addr v1, v2

    #@10
    if-eqz v1, :cond_13

    #@12
    goto :goto_1b

    #@13
    .line 1107
    :cond_13
    new-instance v1, Lcom/android/internal/os/ZygoteSecurityException;

    #@15
    const-string v2, "Peer is permitted to specify an explicit invoke-with wrapper command only for debuggable applications."

    #@17
    invoke-direct {v1, v2}, Lcom/android/internal/os/ZygoteSecurityException;-><init>(Ljava/lang/String;)V

    #@1a
    throw v1

    #@1b
    .line 1111
    :cond_1b
    :goto_1b
    return-void
.end method
