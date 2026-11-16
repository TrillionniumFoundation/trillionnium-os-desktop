.method static blacklist forkAndSpecialize(II[II[[IILjava/lang/String;Ljava/lang/String;[I[IZLjava/lang/String;Ljava/lang/String;Z[Ljava/lang/String;[Ljava/lang/String;ZZZ)I
    .registers 40
    .param p0, "uid"    # I
    .param p1, "gid"    # I
    .param p2, "gids"    # [I
    .param p3, "runtimeFlags"    # I
    .param p4, "rlimits"    # [[I
    .param p5, "mountExternal"    # I
    .param p6, "seInfo"    # Ljava/lang/String;
    .param p7, "niceName"    # Ljava/lang/String;
    .param p8, "fdsToClose"    # [I
    .param p9, "fdsToIgnore"    # [I
    .param p10, "startChildZygote"    # Z
    .param p11, "instructionSet"    # Ljava/lang/String;
    .param p12, "appDataDir"    # Ljava/lang/String;
    .param p13, "isTopApp"    # Z
    .param p14, "pkgDataInfoList"    # [Ljava/lang/String;
    .param p15, "allowlistedDataInfoList"    # [Ljava/lang/String;
    .param p16, "bindMountAppDataDirs"    # Z
    .param p17, "bindMountAppStorageDirs"    # Z
    .param p18, "bindMountSyspropOverrides"    # Z

    #@0
    .line 382
    invoke-static {}, Ldalvik/system/ZygoteHooks;->preFork()V

    #@3
    .line 384
    const-string/jumbo v0, "sys.use_fifo_ui"

    #@6
    const/4 v1, 0x0

    #@7
    invoke-static {v0, v1}, Landroid/os/SystemProperties;->getInt(Ljava/lang/String;I)I

    #@a
    move-result v0

    #@b
    const/4 v2, 0x1

    #@c
    if-ne v0, v2, :cond_10

    #@e
    move v15, v2

    #@f
    goto :goto_11

    #@10
    :cond_10
    move v15, v1

    #@11
    .line 385
    .local v15, "useFifoUi":Z
    :goto_11
    move/from16 v1, p0

    #@13
    move/from16 v2, p1

    #@15
    move-object/from16 v3, p2

    #@17
    move/from16 v4, p3

    #@19
    move-object/from16 v5, p4

    #@1b
    move/from16 v6, p5

    #@1d
    move-object/from16 v7, p6

    #@1f
    move-object/from16 v8, p7

    #@21
    move-object/from16 v9, p8

    #@23
    move-object/from16 v10, p9

    #@25
    move/from16 v11, p10

    #@27
    move-object/from16 v12, p11

    #@29
    move-object/from16 v13, p12

    #@2b
    move/from16 v14, p13

    #@2d
    move-object/from16 v16, p14

    #@2f
    move-object/from16 v17, p15

    #@31
    move/from16 v18, p16

    #@33
    move/from16 v19, p17

    #@35
    move/from16 v20, p18

    #@37
    invoke-static/range {v1 .. v20}, Lcom/android/internal/os/Zygote;->nativeForkAndSpecialize(II[II[[IILjava/lang/String;Ljava/lang/String;[I[IZLjava/lang/String;Ljava/lang/String;ZZ[Ljava/lang/String;[Ljava/lang/String;ZZZ)I

    #@3a
    move-result v0

    #@3b
    .line 390
    .local v0, "pid":I
    if-nez v0, :cond_50

    #@3d
    .line 392
    const-wide/16 v1, 0x40

    #@3f
    const-string v4, "PostFork"

    #@41
    invoke-static {v1, v2, v4}, Landroid/os/Trace;->traceBegin(JLjava/lang/String;)V

    #@44
    .line 395
    if-eqz v3, :cond_50

    #@46
    array-length v1, v3

    #@47
    if-lez v1, :cond_50

    #@49
    .line 396
    invoke-static {v3}, Lcom/android/internal/os/Zygote;->containsInetGid([I)Z

    #@4c
    move-result v1

    #@4d
    invoke-static {v1}, Lcom/android/internal/net/NetworkUtilsInternal;->setAllowNetworkingForProcess(Z)V

    #@50
    .line 401
    :cond_50
    invoke-static {}, Ljava/lang/Thread;->currentThread()Ljava/lang/Thread;

    #@53
    move-result-object v1

    #@54
    const/4 v2, 0x5

    #@55
    invoke-virtual {v1, v2}, Ljava/lang/Thread;->setPriority(I)V

    #@58
    .line 403
    invoke-static {}, Ldalvik/system/ZygoteHooks;->postForkCommon()V

    #@5b
    .line 404
    return v0
.end method
