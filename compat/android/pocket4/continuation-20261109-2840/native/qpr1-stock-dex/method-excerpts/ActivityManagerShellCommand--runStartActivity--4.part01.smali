.method public runStartActivity(Ljava/io/PrintWriter;)I
    .registers 33

    #@0
    move-object/from16 v0, p0

    #@2
    move-object/from16 v1, p1

    #@4
    const/4 v2, -0x2

    #@5
    const/4 v3, 0x0

    #@6
    .line 782
    :try_start_6
    invoke-virtual {v0, v2}, Lcom/android/server/am/ActivityManagerShellCommand;->makeIntent(I)Landroid/content/Intent;

    #@9
    move-result-object v8
    :try_end_a
    .catch Ljava/net/URISyntaxException; {:try_start_6 .. :try_end_a} :catch_381

    #@a
    .line 787
    iget v2, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mUserId:I

    #@c
    const/4 v10, -0x1

    #@d
    const/4 v11, 0x1

    #@e
    if-ne v2, v10, :cond_1a

    #@10
    .line 788
    invoke-virtual {v0}, Landroid/os/ShellCommand;->getErrPrintWriter()Ljava/io/PrintWriter;

    #@13
    move-result-object v0

    #@14
    const-string v1, "Error: Can\'t start service with user \'all\'"

    #@16
    invoke-virtual {v0, v1}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@19
    return v11

    #@1a
    .line 792
    :cond_1a
    iget-object v2, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mInternal:Lcom/android/server/am/ActivityManagerService;

    #@1c
    iget-object v2, v2, Lcom/android/server/am/ActivityManagerService;->mContext:Landroid/content/Context;

    #@1e
    invoke-virtual {v8, v2}, Landroid/content/Intent;->resolveType(Landroid/content/Context;)Ljava/lang/String;

    #@21
    move-result-object v9

    #@22
    .line 794
    iget-boolean v2, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mDebugLink:Z

    #@24
    if-eqz v2, :cond_39

    #@26
    invoke-virtual {v0, v8}, Lcom/android/server/am/ActivityManagerShellCommand;->isWebUri(Landroid/content/Intent;)Z

    #@29
    move-result v2

    #@2a
    if-eqz v2, :cond_39

    #@2c
    .line 795
    const-string v2, "--- App Link Resolution Debug ---\n"

    #@2e
    invoke-virtual {v1, v2}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@31
    .line 796
    invoke-virtual {v0, v1, v8, v9}, Lcom/android/server/am/ActivityManagerShellCommand;->printAppLinkDebugInfo(Ljava/io/PrintWriter;Landroid/content/Intent;Ljava/lang/String;)V

    #@34
    .line 797
    const-string v2, "---------------------------------\n"

    #@36
    invoke-virtual {v1, v2}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@39
    .line 801
    :cond_39
    :goto_39
    iget-boolean v2, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mStopOption:Z

    #@3b
    if-eqz v2, :cond_dd

    #@3d
    .line 803
    invoke-virtual {v8}, Landroid/content/Intent;->getComponent()Landroid/content/ComponentName;

    #@40
    move-result-object v2

    #@41
    if-eqz v2, :cond_4d

    #@43
    .line 804
    invoke-virtual {v8}, Landroid/content/Intent;->getComponent()Landroid/content/ComponentName;

    #@46
    move-result-object v2

    #@47
    invoke-virtual {v2}, Landroid/content/ComponentName;->getPackageName()Ljava/lang/String;

    #@4a
    move-result-object v2

    #@4b
    move-object v5, v8

    #@4c
    goto :goto_a6

    #@4d
    .line 807
    :cond_4d
    iget-object v2, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mInternal:Lcom/android/server/am/ActivityManagerService;

    #@4f
    iget-object v12, v2, Lcom/android/server/am/ActivityManagerService;->mUserController:Lcom/android/server/am/UserController;

    #@51
    .line 808
    invoke-static {}, Landroid/os/Binder;->getCallingPid()I

    #@54
    move-result v13

    #@55
    invoke-static {}, Landroid/os/Binder;->getCallingUid()I

    #@58
    move-result v14

    #@59
    iget v15, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mUserId:I

    #@5b
    const-string v18, "ActivityManagerShellCommand"

    #@5d
    const/16 v19, 0x0

    #@5f
    const/16 v16, 0x0

    #@61
    const/16 v17, 0x0

    #@63
    .line 807
    invoke-virtual/range {v12 .. v19}, Lcom/android/server/am/UserController;->handleIncomingUser(IIIZILjava/lang/String;Ljava/lang/String;)I

    #@66
    move-result v2

    #@67
    .line 810
    iget-object v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mPm:Landroid/content/pm/IPackageManager;

    #@69
    move-object v5, v8

    #@6a
    const-wide/16 v7, 0x0

    #@6c
    move-object v6, v9

    #@6d
    move v9, v2

    #@6e
    invoke-interface/range {v4 .. v9}, Landroid/content/pm/IPackageManager;->queryIntentActivities(Landroid/content/Intent;Ljava/lang/String;JI)Landroid/content/pm/ParceledListSlice;

    #@71
    move-result-object v2

    #@72
    move-object v9, v6

    #@73
    .line 811
    invoke-virtual {v2}, Landroid/content/pm/ParceledListSlice;->getList()Ljava/util/List;

    #@76
    move-result-object v2

    #@77
    if-eqz v2, :cond_c7

    #@79
    .line 812
    invoke-interface {v2}, Ljava/util/List;->size()I

    #@7c
    move-result v4

    #@7d
    if-gtz v4, :cond_80

    #@7f
    goto :goto_c7

    #@80
    .line 816
    :cond_80
    invoke-interface {v2}, Ljava/util/List;->size()I

    #@83
    move-result v4

    #@84
    if-le v4, v11, :cond_9c

    #@86
    .line 817
    invoke-virtual {v0}, Landroid/os/ShellCommand;->getErrPrintWriter()Ljava/io/PrintWriter;

    #@89
    move-result-object v0

    #@8a
    new-instance v1, Ljava/lang/StringBuilder;

    #@8c
    const-string v2, "Error: Intent matches multiple activities; can\'t stop: "

    #@8e
    invoke-direct {v1, v2}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@91
    invoke-virtual {v1, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@94
    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@97
    move-result-object v1

    #@98
    invoke-virtual {v0, v1}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@9b
    return v11

    #@9c
    .line 822
    :cond_9c
    invoke-interface {v2, v3}, Ljava/util/List;->get(I)Ljava/lang/Object;

    #@9f
    move-result-object v2

    #@a0
    check-cast v2, Landroid/content/pm/ResolveInfo;

    #@a2
    iget-object v2, v2, Landroid/content/pm/ResolveInfo;->activityInfo:Landroid/content/pm/ActivityInfo;

    #@a4
    iget-object v2, v2, Landroid/content/pm/ActivityInfo;->packageName:Ljava/lang/String;

    #@a6
    .line 824
    :goto_a6
    new-instance v4, Ljava/lang/StringBuilder;

    #@a8
    const-string v6, "Stopping: "

    #@aa
    invoke-direct {v4, v6}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@ad
    invoke-virtual {v4, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@b0
    invoke-virtual {v4}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@b3
    move-result-object v4

    #@b4
    invoke-virtual {v1, v4}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@b7
    .line 825
    invoke-virtual {v1}, Ljava/io/PrintWriter;->flush()V

    #@ba
    .line 826
    iget-object v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mInterface:Landroid/app/IActivityManager;

    #@bc
    iget v6, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mUserId:I

    #@be
    invoke-interface {v4, v2, v6}, Landroid/app/IActivityManager;->forceStopPackage(Ljava/lang/String;I)V

    #@c1
    const-wide/16 v6, 0xfa

    #@c3
    .line 828
    :try_start_c3
    invoke-static {v6, v7}, Ljava/lang/Thread;->sleep(J)V
    :try_end_c6
    .catch Ljava/lang/InterruptedException; {:try_start_c3 .. :try_end_c6} :catch_de

    #@c6
    goto :goto_de

    #@c7
    .line 813
    :cond_c7
    :goto_c7
    invoke-virtual {v0}, Landroid/os/ShellCommand;->getErrPrintWriter()Ljava/io/PrintWriter;

    #@ca
    move-result-object v0

    #@cb
    new-instance v1, Ljava/lang/StringBuilder;

    #@cd
    const-string v2, "Error: Intent does not match any activities: "

    #@cf
    invoke-direct {v1, v2}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@d2
    invoke-virtual {v1, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@d5
    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@d8
    move-result-object v1

    #@d9
    invoke-virtual {v0, v1}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@dc
    return v11

    #@dd
    :cond_dd
    move-object v5, v8

    #@de
    .line 835
    :catch_de
    :goto_de
    iget-object v2, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mProfileFile:Ljava/lang/String;

    #@e0
    const/16 v17, 0x0

    #@e2
    if-nez v2, :cond_ec

    #@e4
    iget-object v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mAgent:Ljava/lang/String;

    #@e6
    if-eqz v4, :cond_e9

    #@e8
    goto :goto_ec

    #@e9
    :cond_e9
    move-object/from16 v14, v17

    #@eb
    goto :goto_12e

    #@ec
    :cond_ec
    :goto_ec
    if-eqz v2, :cond_fb

    #@ee
    .line 838
    const-string/jumbo v4, "w"

    #@f1
    invoke-virtual {v0, v2, v4}, Landroid/os/ShellCommand;->openFileForSystem(Ljava/lang/String;Ljava/lang/String;)Landroid/os/ParcelFileDescriptor;

    #@f4
    move-result-object v2

    #@f5
    if-nez v2, :cond_f8

    #@f7
    return v11

    #@f8
    :cond_f8
    move-object/from16 v20, v2

    #@fa
    goto :goto_fd

    #@fb
    :cond_fb
    move-object/from16 v20, v17

    #@fd
    .line 843
    :goto_fd
    iget v2, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mClockType:I

    #@ff
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mProfilerOutputVersion:I

    #@101
    iget v6, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mProfilerFlags:I

    #@103
    invoke-static {v2, v4, v6}, Landroid/app/ProfilerInfo;->updateFlags(III)I

    #@106
    move-result v26

    #@107
    .line 845
    new-instance v18, Landroid/app/ProfilerInfo;

    #@109
    iget-object v2, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mProfileFile:Ljava/lang/String;

    #@10b
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mSamplingInterval:I

    #@10d
    iget-boolean v6, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mAutoStop:Z

    #@10f
    iget-boolean v7, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mStreaming:Z

    #@111
    iget-object v8, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mAgent:Ljava/lang/String;

    #@113
    iget-boolean v12, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mAttachAgentDuringBind:Z

    #@115
    iget-boolean v13, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mLongRunningMethods:Z

    #@117
    iget-wide v14, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mDurationMicros:J

    #@119
    move-object/from16 v19, v2

    #@11b
    move/from16 v21, v4

    #@11d
    move/from16 v22, v6

    #@11f
    move/from16 v23, v7

    #@121
    move-object/from16 v24, v8

    #@123
    move/from16 v25, v12

    #@125
    move/from16 v27, v13

    #@127
    move-wide/from16 v28, v14

    #@129
    invoke-direct/range {v18 .. v29}, Landroid/app/ProfilerInfo;-><init>(Ljava/lang/String;Landroid/os/ParcelFileDescriptor;IZZLjava/lang/String;ZIZJ)V

    #@12c
    move-object/from16 v14, v18

    #@12e
    .line 850
    :goto_12e
    new-instance v2, Ljava/lang/StringBuilder;

    #@130
    const-string v4, "Starting: "

    #@132
    invoke-direct {v2, v4}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@135
    invoke-virtual {v2, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@138
    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@13b
    move-result-object v2

    #@13c
    invoke-virtual {v1, v2}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@13f
    .line 851
    invoke-virtual {v1}, Ljava/io/PrintWriter;->flush()V

    #@142
    const/high16 v2, 0x10000000

    #@144
    .line 852
    invoke-virtual {v5, v2}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@147
    .line 856
    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    #@14a
    move-result-wide v18

    #@14b
    .line 858
    iget v2, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mDisplayId:I

    #@14d
    if-eq v2, v10, :cond_159

    #@14f
    .line 859
    invoke-static {}, Landroid/app/ActivityOptions;->makeBasic()Landroid/app/ActivityOptions;

    #@152
    move-result-object v2

    #@153
    .line 860
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mDisplayId:I

    #@155
    invoke-virtual {v2, v4}, Landroid/app/ActivityOptions;->setLaunchDisplayId(I)Landroid/app/ActivityOptions;

    #@158
    goto :goto_15b

    #@159
    :cond_159
    move-object/from16 v2, v17

    #@15b
    .line 862
    :goto_15b
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mTaskDisplayAreaFeatureId:I

    #@15d
    if-eq v4, v10, :cond_16a

    #@15f
    if-nez v2, :cond_165

    #@161
    .line 864
    invoke-static {}, Landroid/app/ActivityOptions;->makeBasic()Landroid/app/ActivityOptions;

    #@164
    move-result-object v2

    #@165
    .line 866
    :cond_165
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mTaskDisplayAreaFeatureId:I

    #@167
    invoke-virtual {v2, v4}, Landroid/app/ActivityOptions;->setLaunchTaskDisplayAreaFeatureId(I)V

    #@16a
    .line 868
    :cond_16a
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mWindowingMode:I

    #@16c
    if-eqz v4, :cond_179

    #@16e
    if-nez v2, :cond_174

    #@170
    .line 870
    invoke-static {}, Landroid/app/ActivityOptions;->makeBasic()Landroid/app/ActivityOptions;

    #@173
    move-result-object v2

    #@174
    .line 872
    :cond_174
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mWindowingMode:I

    #@176
    invoke-virtual {v2, v4}, Landroid/app/ActivityOptions;->setLaunchWindowingMode(I)V

    #@179
    .line 874
    :cond_179
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mActivityType:I

    #@17b
    if-eqz v4, :cond_188

    #@17d
    if-nez v2, :cond_183

    #@17f
    .line 876
    invoke-static {}, Landroid/app/ActivityOptions;->makeBasic()Landroid/app/ActivityOptions;

    #@182
    move-result-object v2

    #@183
    .line 878
    :cond_183
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mActivityType:I

    #@185
    invoke-virtual {v2, v4}, Landroid/app/ActivityOptions;->setLaunchActivityType(I)V

    #@188
    .line 880
    :cond_188
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mTaskId:I

    #@18a
    if-eq v4, v10, :cond_19e

    #@18c
    if-nez v2, :cond_192

    #@18e
    .line 882
    invoke-static {}, Landroid/app/ActivityOptions;->makeBasic()Landroid/app/ActivityOptions;

    #@191
    move-result-object v2

    #@192
    .line 884
    :cond_192
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mTaskId:I

    #@194
    invoke-virtual {v2, v4}, Landroid/app/ActivityOptions;->setLaunchTaskId(I)V

    #@197
    .line 886
    iget-boolean v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mIsTaskOverlay:Z

    #@199
    if-eqz v4, :cond_19e

    #@19b
    .line 887
    invoke-virtual {v2, v11, v11}, Landroid/app/ActivityOptions;->setTaskOverlay(ZZ)V

    #@19e
    .line 890
    :cond_19e
    iget-boolean v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mIsLockTask:Z

    #@1a0
    if-eqz v4, :cond_1ab

    #@1a2
    if-nez v2, :cond_1a8

    #@1a4
    .line 892
    invoke-static {}, Landroid/app/ActivityOptions;->makeBasic()Landroid/app/ActivityOptions;

    #@1a7
    move-result-object v2

    #@1a8
    .line 894
    :cond_1a8
    invoke-virtual {v2, v11}, Landroid/app/ActivityOptions;->setLockTaskEnabled(Z)Landroid/app/ActivityOptions;

    #@1ab
    .line 896
    :cond_1ab
    iget-boolean v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mShowSplashScreen:Z

    #@1ad
    if-eqz v4, :cond_1b8

    #@1af
    if-nez v2, :cond_1b5

    #@1b1
    .line 898
    invoke-static {}, Landroid/app/ActivityOptions;->makeBasic()Landroid/app/ActivityOptions;

    #@1b4
    move-result-object v2

    #@1b5
    .line 900
    :cond_1b5
    invoke-virtual {v2, v11}, Landroid/app/ActivityOptions;->setSplashScreenStyle(I)Landroid/app/ActivityOptions;

    #@1b8
    .line 902
    :cond_1b8
    iget-boolean v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mDismissKeyguardIfInsecure:Z

    #@1ba
    if-eqz v4, :cond_1c5

    #@1bc
    if-nez v2, :cond_1c2

    #@1be
    .line 904
    invoke-static {}, Landroid/app/ActivityOptions;->makeBasic()Landroid/app/ActivityOptions;

    #@1c1
    move-result-object v2

    #@1c2
    .line 906
    :cond_1c2
    invoke-virtual {v2}, Landroid/app/ActivityOptions;->setDismissKeyguardIfInsecure()V

    #@1c5
    .line 908
    :cond_1c5
    invoke-virtual {v5}, Landroid/content/Intent;->collectExtraIntentKeys()V

    #@1c8
    .line 909
    iget-boolean v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mWaitOption:Z

    #@1ca
    move v6, v4

    #@1cb
    .line 915
    iget-object v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mInternal:Lcom/android/server/am/ActivityManagerService;

    #@1cd
    if-eqz v6, :cond_1fa

    #@1cf
    .line 910
    iget v13, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mStartFlags:I

    #@1d1
    if-eqz v2, :cond_1d7

    #@1d3
    .line 912
    invoke-virtual {v2}, Landroid/app/ActivityOptions;->toBundle()Landroid/os/Bundle;

    #@1d6
    move-result-object v17

    #@1d7
    :cond_1d7
    move-object/from16 v15, v17

    #@1d9
    iget v2, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mUserId:I

    #@1db
    move-object v8, v5

    #@1dc
    const/4 v5, 0x0

    #@1dd
    .line 910
    const-string v6, "com.android.shell"

    #@1df
    const/4 v7, 0x0

    #@1e0
    move v12, v10

    #@1e1
    const/4 v10, 0x0

    #@1e2
    move/from16 v16, v11

    #@1e4
    const/4 v11, 0x0

    #@1e5
    move/from16 v17, v12

    #@1e7
    const/4 v12, 0x0

    #@1e8
    move/from16 v20, v16

    #@1ea
    move/from16 v16, v2

    #@1ec
    move/from16 v2, v20

    #@1ee
    move/from16 v20, v17

    #@1f0
    invoke-virtual/range {v4 .. v16}, Lcom/android/server/am/ActivityManagerService;->startActivityAndWait(Landroid/app/IApplicationThread;Ljava/lang/String;Ljava/lang/String;Landroid/content/Intent;Ljava/lang/String;Landroid/os/IBinder;Ljava/lang/String;IILandroid/app/ProfilerInfo;Landroid/os/Bundle;I)Landroid/app/WaitResult;

    #@1f3
    move-result-object v4

    #@1f4
    move-object v5, v8

    #@1f5
    .line 913
    iget v6, v4, Landroid/app/WaitResult;->result:I

    #@1f7
    move-object/from16 v17, v4

    #@1f9
    goto :goto_21f

    #@1fa
    :cond_1fa
    move/from16 v20, v10

    #@1fc
    move/from16 v16, v11

    #@1fe
    .line 915
    iget v13, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mStartFlags:I

    #@200
    if-eqz v2, :cond_208

    #@202
    .line 917
    invoke-virtual {v2}, Landroid/app/ActivityOptions;->toBundle()Landroid/os/Bundle;

    #@205
    move-result-object v2

    #@206
    move-object v15, v2

    #@207
    goto :goto_20a

    #@208
    :cond_208
    move-object/from16 v15, v17

    #@20a
    :goto_20a
    iget v2, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mUserId:I

    #@20c
    move-object v8, v5

    #@20d
    const/4 v5, 0x0

    #@20e
    .line 915
    const-string v6, "com.android.shell"

    #@210
    const/4 v7, 0x0

    #@211
    const/4 v10, 0x0

    #@212
    const/4 v11, 0x0

    #@213
    const/4 v12, 0x0

    #@214
    move/from16 v30, v16

    #@216
    move/from16 v16, v2

    #@218
    move/from16 v2, v30

    #@21a
    invoke-virtual/range {v4 .. v16}, Lcom/android/server/am/ActivityManagerService;->startActivityAsUserWithFeature(Landroid/app/IApplicationThread;Ljava/lang/String;Ljava/lang/String;Landroid/content/Intent;Ljava/lang/String;Landroid/os/IBinder;Ljava/lang/String;IILandroid/app/ProfilerInfo;Landroid/os/Bundle;I)I

    #@21d
    move-result v6

    #@21e
    move-object v5, v8

    #@21f
    .line 919
    :goto_21f
    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    #@222
    move-result-wide v7

    #@223
    .line 920
    iget-boolean v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mWaitOption:Z

    #@225
    if-eqz v4, :cond_229

    #@227
    move-object v4, v1

    #@228
    goto :goto_22d

    #@229
    :cond_229
    invoke-virtual {v0}, Landroid/os/ShellCommand;->getErrPrintWriter()Ljava/io/PrintWriter;

    #@22c
    move-result-object v4

    #@22d
    :goto_22d
    const/16 v10, -0x62

    #@22f
    if-eq v6, v10, :cond_37b

    #@231
    const/16 v10, -0x61

    #@233
    if-eq v6, v10, :cond_369

    #@235
    const/16 v10, -0x58

    #@237
    if-eq v6, v10, :cond_363

    #@239
    const/16 v10, 0x64

    #@23b
    if-eq v6, v10, :cond_2b4

    #@23d
    if-eqz v6, :cond_2b9

    #@23f
    if-eq v6, v2, :cond_2ae

    #@241
    const/4 v10, 0x2

    #@242
    if-eq v6, v10, :cond_2a8

    #@244
    const/4 v10, 0x3

    #@245
    if-eq v6, v10, :cond_2a2

    #@247
    packed-switch v6, :pswitch_data_38a

    #@24a
    .line 987
    new-instance v0, Ljava/lang/StringBuilder;

    #@24c
    const-string v1, "Error: Activity not started, unknown error code "

    #@24e
    invoke-direct {v0, v1}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@251
    invoke-virtual {v0, v6}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@254
    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@257
    move-result-object v0

    #@258
    invoke-virtual {v4, v0}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@25b
    return v2

    #@25c
    .line 952
    :pswitch_25c
    new-instance v0, Ljava/lang/StringBuilder;

    #@25e
    const-string v1, "Error: Activity not started, unable to resolve "

    #@260
    invoke-direct {v0, v1}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@263
    .line 954
    invoke-virtual {v5}, Landroid/content/Intent;->toString()Ljava/lang/String;

    #@266
    move-result-object v1

    #@267
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@26a
    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@26d
    move-result-object v0

    #@26e
    .line 952
    invoke-virtual {v4, v0}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@271
    return v2

    #@272
    .line 957
    :pswitch_272
    const-string v0, "Error type 3"

    #@274
    invoke-virtual {v4, v0}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@277
    .line 958
    new-instance v0, Ljava/lang/StringBuilder;

    #@279
    const-string v1, "Error: Activity class "

    #@27b
    invoke-direct {v0, v1}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@27e
    .line 959
    invoke-virtual {v5}, Landroid/content/Intent;->getComponent()Landroid/content/ComponentName;

    #@281
    move-result-object v1

    #@282
    invoke-virtual {v1}, Landroid/content/ComponentName;->toShortString()Ljava/lang/String;

    #@285
    move-result-object v1

    #@286
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@289
    const-string v1, " does not exist."

    #@28b
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@28e
    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@291
    move-result-object v0

    #@292
    .line 958
    invoke-virtual {v4, v0}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@295
    return v2

    #@296
    .line 963
    :pswitch_296
    const-string v0, "Error: Activity not started, you requested to both forward and receive its result"

    #@298
    invoke-virtual {v4, v0}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@29b
    return v2

    #@29c
    .line 968
    :pswitch_29c
    const-string v0, "Error: Activity not started, you do not have permission to access it."

    #@29e
    invoke-virtual {v4, v0}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@2a1
    return v2

    #@2a2
    .line 934
    :cond_2a2
    const-string v6, "Warning: Activity not started, intent has been delivered to currently running top-most instance."

    #@2a4
    invoke-virtual {v4, v6}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@2a7
    goto :goto_2b9

    #@2a8
    .line 947
    :cond_2a8
    const-string v6, "Warning: Activity not started, its current task has been brought to the front"

    #@2aa
    invoke-virtual {v4, v6}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@2ad
    goto :goto_2b9

    #@2ae
    .line 941
    :cond_2ae
    const-string v6, "Warning: Activity not started because intent should be handled by the caller"

    #@2b0
    invoke-virtual {v4, v6}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@2b3
    goto :goto_2b9

    #@2b4
    .line 928
    :cond_2b4
    const-string v6, "Warning: Activity not started because the  current activity is being kept for the user."

    #@2b6
    invoke-virtual {v4, v6}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@2b9
    .line 991
    :cond_2b9
    :goto_2b9
    invoke-virtual {v4}, Ljava/io/PrintWriter;->flush()V

    #@2bc
    .line 992
    iget-boolean v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mWaitOption:Z

    #@2be
    if-eqz v4, :cond_34c

    #@2c0
    if-nez v17, :cond_2ce

    #@2c2
    .line 994
    new-instance v4, Landroid/app/WaitResult;

    #@2c4
    invoke-direct {v4}, Landroid/app/WaitResult;-><init>()V

    #@2c7
    .line 995
    invoke-virtual {v5}, Landroid/content/Intent;->getComponent()Landroid/content/ComponentName;

    #@2ca
    move-result-object v6

    #@2cb
    iput-object v6, v4, Landroid/app/WaitResult;->who:Landroid/content/ComponentName;

    #@2cd
    goto :goto_2d0

    #@2ce
    :cond_2ce
    move-object/from16 v4, v17

    #@2d0
    .line 997
    :goto_2d0
    iget-boolean v6, v4, Landroid/app/WaitResult;->timeout:Z

    #@2d2
    if-eqz v6, :cond_2d8

    #@2d4
    const-string/jumbo v6, "timeout"

    #@2d7
    goto :goto_2db

    #@2d8
    :cond_2d8
    const-string/jumbo v6, "ok"

    #@2db
    :goto_2db
    const-string v10, "Status: "

    #@2dd
    invoke-virtual {v10, v6}, Ljava/lang/String;->concat(Ljava/lang/String;)Ljava/lang/String;

    #@2e0
    move-result-object v6

    #@2e1
    invoke-virtual {v1, v6}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@2e4
    .line 998
    new-instance v6, Ljava/lang/StringBuilder;

    #@2e6
    const-string v10, "LaunchState: "

    #@2e8
    invoke-direct {v6, v10}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@2eb
    iget v10, v4, Landroid/app/WaitResult;->launchState:I

    #@2ed
    invoke-static {v10}, Landroid/app/WaitResult;->launchStateToString(I)Ljava/lang/String;

    #@2f0
    move-result-object v10

    #@2f1
    invoke-virtual {v6, v10}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@2f4
    invoke-virtual {v6}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@2f7
    move-result-object v6

    #@2f8
    invoke-virtual {v1, v6}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@2fb
    .line 999
    iget-object v6, v4, Landroid/app/WaitResult;->who:Landroid/content/ComponentName;

    #@2fd
    if-eqz v6, :cond_316

    #@2ff
    .line 1000
    new-instance v6, Ljava/lang/StringBuilder;

    #@301
    const-string v10, "Activity: "

    #@303
    invoke-direct {v6, v10}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@306
    iget-object v10, v4, Landroid/app/WaitResult;->who:Landroid/content/ComponentName;

    #@308
    invoke-virtual {v10}, Landroid/content/ComponentName;->flattenToShortString()Ljava/lang/String;

    #@30b
    move-result-object v10

    #@30c
    invoke-virtual {v6, v10}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@30f
    invoke-virtual {v6}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@312
    move-result-object v6

    #@313
    invoke-virtual {v1, v6}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@316
    .line 1002
    :cond_316
    iget-wide v10, v4, Landroid/app/WaitResult;->totalTime:J

    #@318
    const-wide/16 v12, 0x0

    #@31a
    cmp-long v6, v10, v12

    #@31c
    if-ltz v6, :cond_331

    #@31e
    .line 1003
    new-instance v6, Ljava/lang/StringBuilder;

    #@320
    const-string v10, "TotalTime: "

    #@322
    invoke-direct {v6, v10}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@325
    iget-wide v10, v4, Landroid/app/WaitResult;->totalTime:J

    #@327
    invoke-virtual {v6, v10, v11}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    #@32a
    invoke-virtual {v6}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@32d
    move-result-object v4

    #@32e
    invoke-virtual {v1, v4}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@331
    .line 1005
    :cond_331
    new-instance v4, Ljava/lang/StringBuilder;

    #@333
    const-string v6, "WaitTime: "

    #@335
    invoke-direct {v4, v6}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@338
    sub-long v7, v7, v18

    #@33a
    invoke-virtual {v4, v7, v8}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    #@33d
    invoke-virtual {v4}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@340
    move-result-object v4

    #@341
    invoke-virtual {v1, v4}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@344
    .line 1006
    const-string v4, "Complete"

    #@346
    invoke-virtual {v1, v4}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@349
    .line 1007
    invoke-virtual {v1}, Ljava/io/PrintWriter;->flush()V

    #@34c
    .line 1009
    :cond_34c
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mRepeat:I

    #@34e
    sub-int/2addr v4, v2

    #@34f
    iput v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mRepeat:I

    #@351
    if-lez v4, :cond_358

    #@353
    .line 1011
    iget-object v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mTaskInterface:Landroid/app/IActivityTaskManager;

    #@355
    invoke-interface {v4}, Landroid/app/IActivityTaskManager;->unhandledBack()V

    #@358
    .line 1013
    :cond_358
    iget v4, v0, Lcom/android/server/am/ActivityManagerShellCommand;->mRepeat:I

    #@35a
    if-gtz v4, :cond_35d

    #@35c
    return v3

    #@35d
    :cond_35d
    move v11, v2

    #@35e
    move-object v8, v5

    #@35f
    move/from16 v10, v20

    #@361
    goto/16 :goto_39

    #@363
    .line 983
    :cond_363
    const-string v0, "Error: Activity not started, not allowed for the given user."

    #@365
    invoke-virtual {v4, v0}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@368
    return v2

    #@369
    .line 973
    :cond_369
    new-instance v0, Ljava/lang/StringBuilder;

    #@36b
    const-string v1, "Error: Activity not started, voice control not allowed for: "

    #@36d
    invoke-direct {v0, v1}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@370
    invoke-virtual {v0, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@373
    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@376
    move-result-object v0

    #@377
    invoke-virtual {v4, v0}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@37a
    return v2

    #@37b
    .line 978
    :cond_37b
    const-string v0, "Error: Not allowed to start background user activity that shouldn\'t be displayed for all users."

    #@37d
    invoke-virtual {v4, v0}, Ljava/io/PrintWriter;->println(Ljava/lang/String;)V

    #@380
    return v2

    #@381
    :catch_381
    move-exception v0

    #@382
    .line 784
    invoke-virtual {v0}, Ljava/net/URISyntaxException;->getMessage()Ljava/lang/String;

    #@385
    move-result-object v1

    #@386
    invoke-static {v1, v0}, Lcom/android/server/pm/UserDataPreparer$$ExternalSyntheticBUOutline0;->m(Ljava/lang/String;Ljava/lang/Throwable;)V

    #@389
    return v3

    #@38a
    :pswitch_data_38a
    .packed-switch -0x5e
        :pswitch_29c
        :pswitch_296
        :pswitch_272
        :pswitch_25c
    .end packed-switch
.end method
