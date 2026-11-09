.method public final startActivityAndWait(Landroid/app/IApplicationThread;Ljava/lang/String;Ljava/lang/String;Landroid/content/Intent;Ljava/lang/String;Landroid/os/IBinder;Ljava/lang/String;IILandroid/app/ProfilerInfo;Landroid/os/Bundle;I)Landroid/app/WaitResult;
    .registers 18

    #@0
    .line 1711
    invoke-virtual {p0, p2}, Lcom/android/server/wm/ActivityTaskManagerService;->assertPackageMatchesCallingUid(Ljava/lang/String;)V

    #@3
    .line 1712
    new-instance v0, Landroid/app/WaitResult;

    #@5
    invoke-direct {v0}, Landroid/app/WaitResult;-><init>()V

    #@8
    .line 1713
    const-string v1, "startActivityAndWait"

    #@a
    invoke-static {v1}, Lcom/android/server/wm/ActivityTaskManagerService;->enforceNotIsolatedCaller(Ljava/lang/String;)V

    #@d
    .line 1714
    invoke-static {}, Landroid/os/Binder;->getCallingPid()I

    #@10
    move-result v2

    #@11
    .line 1715
    invoke-static {}, Landroid/os/Binder;->getCallingUid()I

    #@14
    move-result v3

    #@15
    move/from16 v4, p12

    #@17
    .line 1716
    invoke-virtual {p0, v2, v3, v4, v1}, Lcom/android/server/wm/ActivityTaskManagerService;->handleIncomingUser(IIILjava/lang/String;)I

    #@1a
    move-result v4

    #@1b
    .line 1718
    invoke-virtual {p0}, Lcom/android/server/wm/ActivityTaskManagerService;->getActivityStartController()Lcom/android/server/wm/ActivityStartController;

    #@1e
    move-result-object p0

    #@1f
    invoke-virtual {p0, p4, v1}, Lcom/android/server/wm/ActivityStartController;->obtainStarter(Landroid/content/Intent;Ljava/lang/String;)Lcom/android/server/wm/ActivityStarter;

    #@22
    move-result-object p0

    #@23
    .line 1719
    invoke-virtual {p0, p1}, Lcom/android/server/wm/ActivityStarter;->setCaller(Landroid/app/IApplicationThread;)Lcom/android/server/wm/ActivityStarter;

    #@26
    move-result-object p0

    #@27
    .line 1720
    invoke-virtual {p0, p2}, Lcom/android/server/wm/ActivityStarter;->setCallingPackage(Ljava/lang/String;)Lcom/android/server/wm/ActivityStarter;

    #@2a
    move-result-object p0

    #@2b
    .line 1721
    invoke-virtual {p0, p3}, Lcom/android/server/wm/ActivityStarter;->setCallingFeatureId(Ljava/lang/String;)Lcom/android/server/wm/ActivityStarter;

    #@2e
    move-result-object p0

    #@2f
    .line 1722
    invoke-virtual {p0, p5}, Lcom/android/server/wm/ActivityStarter;->setResolvedType(Ljava/lang/String;)Lcom/android/server/wm/ActivityStarter;

    #@32
    move-result-object p0

    #@33
    .line 1723
    invoke-virtual {p0, p6}, Lcom/android/server/wm/ActivityStarter;->setResultTo(Landroid/os/IBinder;)Lcom/android/server/wm/ActivityStarter;

    #@36
    move-result-object p0

    #@37
    .line 1724
    invoke-virtual {p0, p7}, Lcom/android/server/wm/ActivityStarter;->setResultWho(Ljava/lang/String;)Lcom/android/server/wm/ActivityStarter;

    #@3a
    move-result-object p0

    #@3b
    .line 1725
    invoke-virtual {p0, p8}, Lcom/android/server/wm/ActivityStarter;->setRequestCode(I)Lcom/android/server/wm/ActivityStarter;

    #@3e
    move-result-object p0

    #@3f
    .line 1726
    invoke-virtual {p0, p9}, Lcom/android/server/wm/ActivityStarter;->setStartFlags(I)Lcom/android/server/wm/ActivityStarter;

    #@42
    move-result-object p0

    #@43
    move-object/from16 p1, p11

    #@45
    .line 1727
    invoke-virtual {p0, p1, v2, v3}, Lcom/android/server/wm/ActivityStarter;->setActivityOptions(Landroid/os/Bundle;II)Lcom/android/server/wm/ActivityStarter;

    #@48
    move-result-object p0

    #@49
    .line 1728
    invoke-virtual {p0, v4}, Lcom/android/server/wm/ActivityStarter;->setUserId(I)Lcom/android/server/wm/ActivityStarter;

    #@4c
    move-result-object p0

    #@4d
    .line 1729
    invoke-virtual {p0, p10}, Lcom/android/server/wm/ActivityStarter;->setProfilerInfo(Landroid/app/ProfilerInfo;)Lcom/android/server/wm/ActivityStarter;

    #@50
    move-result-object p0

    #@51
    .line 1730
    invoke-virtual {p0, v0}, Lcom/android/server/wm/ActivityStarter;->setWaitResult(Landroid/app/WaitResult;)Lcom/android/server/wm/ActivityStarter;

    #@54
    move-result-object p0

    #@55
    .line 1731
    invoke-virtual {p0}, Lcom/android/server/wm/ActivityStarter;->execute()I

    #@58
    return-object v0
.end method
