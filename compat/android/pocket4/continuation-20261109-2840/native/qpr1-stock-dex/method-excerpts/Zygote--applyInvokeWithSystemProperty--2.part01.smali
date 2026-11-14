.method static blacklist applyInvokeWithSystemProperty(Lcom/android/internal/os/ZygoteArguments;)V
    .registers 2
    .param p0, "args"    # Lcom/android/internal/os/ZygoteArguments;

    #@0
    .line 1138
    iget-object v0, p0, Lcom/android/internal/os/ZygoteArguments;->mInvokeWith:Ljava/lang/String;

    #@2
    if-nez v0, :cond_c

    #@4
    .line 1139
    iget-object v0, p0, Lcom/android/internal/os/ZygoteArguments;->mNiceName:Ljava/lang/String;

    #@6
    invoke-static {v0}, Lcom/android/internal/os/Zygote;->getWrapProperty(Ljava/lang/String;)Ljava/lang/String;

    #@9
    move-result-object v0

    #@a
    iput-object v0, p0, Lcom/android/internal/os/ZygoteArguments;->mInvokeWith:Ljava/lang/String;

    #@c
    .line 1141
    :cond_c
    return-void
.end method
