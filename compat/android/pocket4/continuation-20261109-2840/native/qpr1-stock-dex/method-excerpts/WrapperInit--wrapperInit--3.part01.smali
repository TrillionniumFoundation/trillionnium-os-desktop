.method private static blacklist wrapperInit(I[Ljava/lang/String;)Ljava/lang/Runnable;
    .registers 7
    .param p0, "targetSdkVersion"    # I
    .param p1, "argv"    # [Ljava/lang/String;

    #@0
    .line 160
    const/4 v0, 0x0

    #@1
    .line 161
    .local v0, "classLoader":Ljava/lang/ClassLoader;
    if-eqz p1, :cond_2a

    #@3
    array-length v1, p1

    #@4
    const/4 v2, 0x2

    #@5
    if-le v1, v2, :cond_2a

    #@7
    const/4 v1, 0x0

    #@8
    aget-object v3, p1, v1

    #@a
    const-string v4, "-cp"

    #@c
    invoke-virtual {v3, v4}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@f
    move-result v3

    #@10
    if-eqz v3, :cond_2a

    #@12
    .line 162
    const/4 v3, 0x1

    #@13
    aget-object v3, p1, v3

    #@15
    invoke-static {v3, p0}, Lcom/android/internal/os/ZygoteInit;->createPathClassLoader(Ljava/lang/String;I)Ljava/lang/ClassLoader;

    #@18
    move-result-object v0

    #@19
    .line 165
    invoke-static {}, Ljava/lang/Thread;->currentThread()Ljava/lang/Thread;

    #@1c
    move-result-object v3

    #@1d
    invoke-virtual {v3, v0}, Ljava/lang/Thread;->setContextClassLoader(Ljava/lang/ClassLoader;)V

    #@20
    .line 168
    array-length v3, p1

    #@21
    sub-int/2addr v3, v2

    #@22
    new-array v3, v3, [Ljava/lang/String;

    #@24
    .line 169
    .local v3, "removedArgs":[Ljava/lang/String;
    array-length v4, p1

    #@25
    sub-int/2addr v4, v2

    #@26
    invoke-static {p1, v2, v3, v1, v4}, Ljava/lang/System;->arraycopy(Ljava/lang/Object;ILjava/lang/Object;II)V

    #@29
    .line 170
    move-object p1, v3

    #@2a
    .line 173
    .end local v3    # "removedArgs":[Ljava/lang/String;
    :cond_2a
    invoke-static {}, Lcom/android/internal/os/Zygote;->nativePreApplicationInit()V

    #@2d
    .line 174
    const/4 v1, 0x0

    #@2e
    invoke-static {p0, v1, v1, p1, v0}, Lcom/android/internal/os/RuntimeInit;->applicationInit(I[J[J[Ljava/lang/String;Ljava/lang/ClassLoader;)Ljava/lang/Runnable;

    #@31
    move-result-object v1

    #@32
    return-object v1
.end method
