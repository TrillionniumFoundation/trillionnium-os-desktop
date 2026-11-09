.method blacklist processCommand(Lcom/android/internal/os/ZygoteServer;Z)Ljava/lang/Runnable;
    .registers 33
    .param p1, "zygoteServer"    # Lcom/android/internal/os/ZygoteServer;
    .param p2, "multipleOK"    # Z

    #@0
    .line 123
    move-object/from16 v1, p0

    #@2
    move-object/from16 v2, p1

    #@4
    move/from16 v3, p2

    #@6
    new-instance v0, Lcom/android/internal/os/ZygoteCommandBuffer;

    #@8
    iget-object v4, v1, Lcom/android/internal/os/ZygoteConnection;->mSocket:Landroid/net/LocalSocket;

    #@a
    invoke-direct {v0, v4}, Lcom/android/internal/os/ZygoteCommandBuffer;-><init>(Landroid/net/LocalSocket;)V

    #@d
    move-object v5, v0

    #@e
    .line 126
    .local v5, "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    :goto_e
    :try_start_e
    invoke-static {v5}, Lcom/android/internal/os/ZygoteArguments;->getInstance(Lcom/android/internal/os/ZygoteCommandBuffer;)Lcom/android/internal/os/ZygoteArguments;

    #@11
    move-result-object v0
    :try_end_12
    .catch Ljava/io/IOException; {:try_start_e .. :try_end_12} :catch_28a
    .catchall {:try_start_e .. :try_end_12} :catchall_287

    #@12
    move-object v4, v0

    #@13
    .line 130
    .local v4, "parsedArgs":Lcom/android/internal/os/ZygoteArguments;
    nop

    #@14
    .line 131
    const/4 v0, 0x1

    #@15
    const/4 v6, 0x0

    #@16
    if-nez v4, :cond_1f

    #@18
    .line 132
    :try_start_18
    iput-boolean v0, v1, Lcom/android/internal/os/ZygoteConnection;->isEof:Z
    :try_end_1a
    .catchall {:try_start_18 .. :try_end_1a} :catchall_287

    #@1a
    .line 133
    nop

    #@1b
    .line 302
    invoke-virtual {v5}, Lcom/android/internal/os/ZygoteCommandBuffer;->close()V

    #@1e
    .line 133
    return-object v6

    #@1f
    .line 137
    :cond_1f
    const/4 v7, 0x0

    #@20
    .line 138
    .local v7, "childPipeFd":Ljava/io/FileDescriptor;
    const/4 v8, 0x0

    #@21
    .line 140
    .local v8, "serverPipeFd":Ljava/io/FileDescriptor;
    :try_start_21
    iget-boolean v9, v4, Lcom/android/internal/os/ZygoteArguments;->mBootCompleted:Z

    #@23
    if-eqz v9, :cond_2d

    #@25
    .line 141
    invoke-direct {v1}, Lcom/android/internal/os/ZygoteConnection;->handleBootCompleted()V
    :try_end_28
    .catchall {:try_start_21 .. :try_end_28} :catchall_287

    #@28
    .line 142
    nop

    #@29
    .line 302
    invoke-virtual {v5}, Lcom/android/internal/os/ZygoteCommandBuffer;->close()V

    #@2c
    .line 142
    return-object v6

    #@2d
    .line 145
    :cond_2d
    :try_start_2d
    iget-boolean v9, v4, Lcom/android/internal/os/ZygoteArguments;->mAbiListQuery:Z

    #@2f
    if-eqz v9, :cond_39

    #@31
    .line 146
    invoke-direct {v1}, Lcom/android/internal/os/ZygoteConnection;->handleAbiListQuery()V
    :try_end_34
    .catchall {:try_start_2d .. :try_end_34} :catchall_287

    #@34
    .line 147
    nop

    #@35
    .line 302
    invoke-virtual {v5}, Lcom/android/internal/os/ZygoteCommandBuffer;->close()V

    #@38
    .line 147
    return-object v6

    #@39
    .line 150
    :cond_39
    :try_start_39
    iget-boolean v9, v4, Lcom/android/internal/os/ZygoteArguments;->mPidQuery:Z

    #@3b
    if-eqz v9, :cond_45

    #@3d
    .line 151
    invoke-direct {v1}, Lcom/android/internal/os/ZygoteConnection;->handlePidQuery()V
    :try_end_40
    .catchall {:try_start_39 .. :try_end_40} :catchall_287

    #@40
    .line 152
    nop

    #@41
    .line 302
    invoke-virtual {v5}, Lcom/android/internal/os/ZygoteCommandBuffer;->close()V

    #@44
    .line 152
    return-object v6

    #@45
    .line 155
    :cond_45
    :try_start_45
    iget-boolean v9, v4, Lcom/android/internal/os/ZygoteArguments;->mUsapPoolStatusSpecified:Z

    #@47
    const/4 v10, -0x1

    #@48
    if-nez v9, :cond_254

    #@4a
    iget-object v9, v4, Lcom/android/internal/os/ZygoteArguments;->mApiDenylistExemptions:[Ljava/lang/String;

    #@4c
    if-nez v9, :cond_254

    #@4e
    iget v9, v4, Lcom/android/internal/os/ZygoteArguments;->mHiddenApiAccessLogSampleRate:I

    #@50
    if-ne v9, v10, :cond_254

    #@52
    iget v9, v4, Lcom/android/internal/os/ZygoteArguments;->mHiddenApiAccessStatslogSampleRate:I

    #@54
    if-eq v9, v10, :cond_58

    #@56
    .line 160
    goto/16 :goto_254

    #@58
    .line 163
    :cond_58
    iget-boolean v9, v4, Lcom/android/internal/os/ZygoteArguments;->mPreloadDefault:Z

    #@5a
    if-eqz v9, :cond_64

    #@5c
    .line 164
    invoke-direct {v1}, Lcom/android/internal/os/ZygoteConnection;->handlePreload()V
    :try_end_5f
    .catchall {:try_start_45 .. :try_end_5f} :catchall_287

    #@5f
    .line 165
    nop

    #@60
    .line 302
    invoke-virtual {v5}, Lcom/android/internal/os/ZygoteCommandBuffer;->close()V

    #@63
    .line 165
    return-object v6

    #@64
    .line 168
    :cond_64
    :try_start_64
    invoke-virtual {v1}, Lcom/android/internal/os/ZygoteConnection;->canPreloadApp()Z

    #@67
    move-result v9

    #@68
    const/4 v11, 0x0

    #@69
    if-eqz v9, :cond_a1

    #@6b
    iget-object v9, v4, Lcom/android/internal/os/ZygoteArguments;->mPreloadApp:Ljava/lang/String;

    #@6d
    if-eqz v9, :cond_a1

    #@6f
    .line 169
    invoke-static {}, Ljava/util/Base64;->getDecoder()Ljava/util/Base64$Decoder;

    #@72
    move-result-object v0

    #@73
    iget-object v9, v4, Lcom/android/internal/os/ZygoteArguments;->mPreloadApp:Ljava/lang/String;

    #@75
    invoke-virtual {v0, v9}, Ljava/util/Base64$Decoder;->decode(Ljava/lang/String;)[B

    #@78
    move-result-object v0

    #@79
    .line 170
    .local v0, "rawParcelData":[B
    invoke-static {}, Landroid/os/Parcel;->obtain()Landroid/os/Parcel;

    #@7c
    move-result-object v9

    #@7d
    .line 171
    .local v9, "appInfoParcel":Landroid/os/Parcel;
    array-length v10, v0

    #@7e
    invoke-virtual {v9, v0, v11, v10}, Landroid/os/Parcel;->unmarshall([BII)V

    #@81
    .line 172
    invoke-virtual {v9, v11}, Landroid/os/Parcel;->setDataPosition(I)V

    #@84
    .line 173
    sget-object v10, Landroid/content/pm/ApplicationInfo;->CREATOR:Landroid/os/Parcelable$Creator;

    #@86
    .line 174
    invoke-interface {v10, v9}, Landroid/os/Parcelable$Creator;->createFromParcel(Landroid/os/Parcel;)Ljava/lang/Object;

    #@89
    move-result-object v10

    #@8a
    check-cast v10, Landroid/content/pm/ApplicationInfo;

    #@8c
    .line 175
    .local v10, "appInfo":Landroid/content/pm/ApplicationInfo;
    invoke-virtual {v9}, Landroid/os/Parcel;->recycle()V

    #@8f
    .line 176
    if-eqz v10, :cond_99

    #@91
    .line 177
    invoke-virtual {v1, v10}, Lcom/android/internal/os/ZygoteConnection;->handlePreloadApp(Landroid/content/pm/ApplicationInfo;)V
    :try_end_94
    .catchall {:try_start_64 .. :try_end_94} :catchall_287

    #@94
    .line 181
    nop

    #@95
    .line 302
    invoke-virtual {v5}, Lcom/android/internal/os/ZygoteCommandBuffer;->close()V

    #@98
    .line 181
    return-object v6

    #@99
    .line 179
    :cond_99
    :try_start_99
    new-instance v6, Ljava/lang/IllegalArgumentException;

    #@9b
    const-string v11, "Failed to deserialize --preload-app"

    #@9d
    invoke-direct {v6, v11}, Ljava/lang/IllegalArgumentException;-><init>(Ljava/lang/String;)V

    #@a0
    .end local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    .end local p0    # "this":Lcom/android/internal/os/ZygoteConnection;
    .end local p1    # "zygoteServer":Lcom/android/internal/os/ZygoteServer;
    .end local p2    # "multipleOK":Z
    throw v6

    #@a1
    .line 184
    .end local v0    # "rawParcelData":[B
    .end local v9    # "appInfoParcel":Landroid/os/Parcel;
    .end local v10    # "appInfo":Landroid/content/pm/ApplicationInfo;
    .restart local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    .restart local p0    # "this":Lcom/android/internal/os/ZygoteConnection;
    .restart local p1    # "zygoteServer":Lcom/android/internal/os/ZygoteServer;
    .restart local p2    # "multipleOK":Z
    :cond_a1
    iget-wide v12, v4, Lcom/android/internal/os/ZygoteArguments;->mPermittedCapabilities:J

    #@a3
    const-wide/16 v14, 0x0

    #@a5
    cmp-long v9, v12, v14

    #@a7
    if-nez v9, :cond_225

    #@a9
    iget-wide v12, v4, Lcom/android/internal/os/ZygoteArguments;->mEffectiveCapabilities:J

    #@ab
    cmp-long v9, v12, v14

    #@ad
    if-nez v9, :cond_225

    #@af
    .line 192
    iget-object v9, v1, Lcom/android/internal/os/ZygoteConnection;->peer:Landroid/net/Credentials;

    #@b1
    invoke-static {v4, v9}, Lcom/android/internal/os/Zygote;->applyUidSecurityPolicy(Lcom/android/internal/os/ZygoteArguments;Landroid/net/Credentials;)V

    #@b4
    .line 193
    iget-object v9, v1, Lcom/android/internal/os/ZygoteConnection;->peer:Landroid/net/Credentials;

    #@b6
    invoke-static {v4, v9}, Lcom/android/internal/os/Zygote;->applyInvokeWithSecurityPolicy(Lcom/android/internal/os/ZygoteArguments;Landroid/net/Credentials;)V

    #@b9
    .line 195
    invoke-static {v4}, Lcom/android/internal/os/Zygote;->applyDebuggerSystemProperty(Lcom/android/internal/os/ZygoteArguments;)V

    #@bc
    .line 196
    invoke-static {v4}, Lcom/android/internal/os/Zygote;->applyInvokeWithSystemProperty(Lcom/android/internal/os/ZygoteArguments;)V

    #@bf
    .line 198
    const/4 v9, 0x0

    #@c0
    .line 200
    .local v9, "rlimits":[[I
    iget-object v12, v4, Lcom/android/internal/os/ZygoteArguments;->mRLimits:Ljava/util/ArrayList;

    #@c2
    if-eqz v12, :cond_d0

    #@c4
    .line 201
    iget-object v12, v4, Lcom/android/internal/os/ZygoteArguments;->mRLimits:Ljava/util/ArrayList;

    #@c6
    sget-object v13, Lcom/android/internal/os/Zygote;->INT_ARRAY_2D:[[I

    #@c8
    invoke-virtual {v12, v13}, Ljava/util/ArrayList;->toArray([Ljava/lang/Object;)[Ljava/lang/Object;

    #@cb
    move-result-object v12

    #@cc
    check-cast v12, [[I

    #@ce
    move-object v9, v12

    #@cf
    goto :goto_d1

    #@d0
    .line 200
    :cond_d0
    move-object v12, v9

    #@d1
    .line 204
    .end local v9    # "rlimits":[[I
    .local v12, "rlimits":[[I
    :goto_d1
    const/4 v9, 0x0

    #@d2
    .line 206
    .local v9, "fdsToIgnore":[I
    iget-object v13, v4, Lcom/android/internal/os/ZygoteArguments;->mInvokeWith:Ljava/lang/String;
    :try_end_d4
    .catchall {:try_start_99 .. :try_end_d4} :catchall_287

    #@d4
    if-eqz v13, :cond_102

    #@d6
    .line 208
    :try_start_d6
    sget v13, Landroid/system/OsConstants;->O_CLOEXEC:I

    #@d8
    invoke-static {v13}, Landroid/system/Os;->pipe2(I)[Ljava/io/FileDescriptor;

    #@db
    move-result-object v13

    #@dc
    .line 209
    .local v13, "pipeFds":[Ljava/io/FileDescriptor;
    aget-object v14, v13, v0

    #@de
    move-object v7, v14

    #@df
    .line 210
    aget-object v14, v13, v11

    #@e1
    move-object v8, v14

    #@e2
    .line 211
    sget v14, Landroid/system/OsConstants;->F_SETFD:I

    #@e4
    invoke-static {v7, v14, v11}, Landroid/system/Os;->fcntlInt(Ljava/io/FileDescriptor;II)I

    #@e7
    .line 212
    invoke-virtual {v7}, Ljava/io/FileDescriptor;->getInt$()I

    #@ea
    move-result v14

    #@eb
    invoke-virtual {v8}, Ljava/io/FileDescriptor;->getInt$()I

    #@ee
    move-result v15

    #@ef
    filled-new-array {v14, v15}, [I

    #@f2
    move-result-object v14
    :try_end_f3
    .catch Landroid/system/ErrnoException; {:try_start_d6 .. :try_end_f3} :catch_f9
    .catchall {:try_start_d6 .. :try_end_f3} :catchall_287

    #@f3
    move-object v9, v14

    #@f4
    .line 216
    .end local v13    # "pipeFds":[Ljava/io/FileDescriptor;
    move-object v13, v7

    #@f5
    move-object v14, v8

    #@f6
    move-object/from16 v16, v9

    #@f8
    goto :goto_106

    #@f9
    .line 213
    :catch_f9
    move-exception v0

    #@fa
    .line 214
    .local v0, "errnoEx":Landroid/system/ErrnoException;
    :try_start_fa
    new-instance v6, Ljava/lang/IllegalStateException;

    #@fc
    const-string v10, "Unable to set up pipe for invoke-with"

    #@fe
    invoke-direct {v6, v10, v0}, Ljava/lang/IllegalStateException;-><init>(Ljava/lang/String;Ljava/lang/Throwable;)V

    #@101
    .end local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    .end local p0    # "this":Lcom/android/internal/os/ZygoteConnection;
    .end local p1    # "zygoteServer":Lcom/android/internal/os/ZygoteServer;
    .end local p2    # "multipleOK":Z
    throw v6

    #@102
    .line 206
    .end local v0    # "errnoEx":Landroid/system/ErrnoException;
    .restart local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    .restart local p0    # "this":Lcom/android/internal/os/ZygoteConnection;
    .restart local p1    # "zygoteServer":Lcom/android/internal/os/ZygoteServer;
    .restart local p2    # "multipleOK":Z
    :cond_102
    move-object v13, v7

    #@103
    move-object v14, v8

    #@104
    move-object/from16 v16, v9

    #@106
    .line 231
    .end local v7    # "childPipeFd":Ljava/io/FileDescriptor;
    .end local v8    # "serverPipeFd":Ljava/io/FileDescriptor;
    .end local v9    # "fdsToIgnore":[I
    .local v13, "childPipeFd":Ljava/io/FileDescriptor;
    .local v14, "serverPipeFd":Ljava/io/FileDescriptor;
    .local v16, "fdsToIgnore":[I
    :goto_106
    filled-new-array {v10, v10}, [I

    #@109
    move-result-object v15

    #@10a
    .line 233
    .local v15, "fdsToClose":[I
    iget-object v7, v1, Lcom/android/internal/os/ZygoteConnection;->mSocket:Landroid/net/LocalSocket;

    #@10c
    invoke-virtual {v7}, Landroid/net/LocalSocket;->getFileDescriptor()Ljava/io/FileDescriptor;

    #@10f
    move-result-object v7

    #@110
    move-object/from16 v26, v7

    #@112
    .line 235
    .local v26, "fd":Ljava/io/FileDescriptor;
    if-eqz v26, :cond_11a

    #@114
    .line 236
    invoke-virtual/range {v26 .. v26}, Ljava/io/FileDescriptor;->getInt$()I

    #@117
    move-result v7

    #@118
    aput v7, v15, v11

    #@11a
    .line 239
    :cond_11a
    invoke-virtual {v2}, Lcom/android/internal/os/ZygoteServer;->getZygoteSocketFileDescriptor()Ljava/io/FileDescriptor;

    #@11d
    move-result-object v7

    #@11e
    move-object/from16 v27, v7

    #@120
    .line 241
    .local v27, "zygoteFd":Ljava/io/FileDescriptor;
    if-eqz v27, :cond_128

    #@122
    .line 242
    invoke-virtual/range {v27 .. v27}, Ljava/io/FileDescriptor;->getInt$()I

    #@125
    move-result v7

    #@126
    aput v7, v15, v0

    #@128
    .line 245
    :cond_128
    iget-object v0, v4, Lcom/android/internal/os/ZygoteArguments;->mInvokeWith:Ljava/lang/String;

    #@12a
    if-nez v0, :cond_168

    #@12c
    iget-boolean v0, v4, Lcom/android/internal/os/ZygoteArguments;->mStartChildZygote:Z

    #@12e
    if-nez v0, :cond_168

    #@130
    if-eqz v3, :cond_168

    #@132
    iget-object v0, v1, Lcom/android/internal/os/ZygoteConnection;->peer:Landroid/net/Credentials;

    #@134
    .line 246
    invoke-virtual {v0}, Landroid/net/Credentials;->getUid()I

    #@137
    move-result v0

    #@138
    const/16 v7, 0x3e8

    #@13a
    if-eq v0, v7, :cond_13d

    #@13c
    goto :goto_168

    #@13d
    .line 284
    :cond_13d
    invoke-static {}, Ldalvik/system/ZygoteHooks;->preFork()V

    #@140
    .line 285
    nop

    #@141
    .line 286
    invoke-virtual {v2}, Lcom/android/internal/os/ZygoteServer;->getZygoteSocketFileDescriptor()Ljava/io/FileDescriptor;

    #@144
    move-result-object v6

    #@145
    iget-object v0, v1, Lcom/android/internal/os/ZygoteConnection;->peer:Landroid/net/Credentials;

    #@147
    .line 287
    invoke-virtual {v0}, Landroid/net/Credentials;->getUid()I

    #@14a
    move-result v7

    #@14b
    iget-object v0, v1, Lcom/android/internal/os/ZygoteConnection;->peer:Landroid/net/Credentials;

    #@14d
    invoke-static {v0}, Lcom/android/internal/os/Zygote;->minChildUid(Landroid/net/Credentials;)I

    #@150
    move-result v8

    #@151
    iget-object v9, v4, Lcom/android/internal/os/ZygoteArguments;->mNiceName:Ljava/lang/String;

    #@153
    iget-boolean v10, v4, Lcom/android/internal/os/ZygoteArguments;->mIsTopApp:Z

    #@155
    .line 285
    invoke-static/range {v5 .. v10}, Lcom/android/internal/os/Zygote;->forkSimpleApps(Lcom/android/internal/os/ZygoteCommandBuffer;Ljava/io/FileDescriptor;IILjava/lang/String;Z)Ljava/lang/Runnable;

    #@158
    move-result-object v0

    #@159
    .line 289
    .local v0, "result":Ljava/lang/Runnable;
    if-nez v0, :cond_160

    #@15b
    .line 292
    invoke-static {}, Ldalvik/system/ZygoteHooks;->postForkCommon()V

    #@15e
    .line 294
    goto/16 :goto_e

    #@160
    .line 297
    :cond_160
    invoke-virtual {v2}, Lcom/android/internal/os/ZygoteServer;->setForkChild()V
    :try_end_163
    .catchall {:try_start_fa .. :try_end_163} :catchall_287

    #@163
    .line 298
    nop

    #@164
    .line 302
    invoke-virtual {v5}, Lcom/android/internal/os/ZygoteCommandBuffer;->close()V

    #@167
    .line 298
    return-object v0

    #@168
    .line 247
    .end local v0    # "result":Ljava/lang/Runnable;
    :cond_168
    :goto_168
    :try_start_168
    const-string v0, "Zygote"

    #@16a
    new-instance v7, Ljava/lang/StringBuilder;

    #@16c
    invoke-direct {v7}, Ljava/lang/StringBuilder;-><init>()V

    #@16f
    const-string v8, "Resorting to Java fork code; multipleOK = "

    #@171
    invoke-virtual {v7, v8}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@174
    move-result-object v7

    #@175
    invoke-virtual {v7, v3}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@178
    move-result-object v7

    #@179
    .line 248
    iget-object v8, v4, Lcom/android/internal/os/ZygoteArguments;->mInvokeWith:Ljava/lang/String;

    #@17b
    if-eqz v8, :cond_180

    #@17d
    const-string v8, "; invokeWith used"

    #@17f
    goto :goto_182

    #@180
    :cond_180
    const-string v8, ""

    #@182
    :goto_182
    invoke-virtual {v7, v8}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@185
    move-result-object v7

    #@186
    invoke-virtual {v7}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@189
    move-result-object v7

    #@18a
    .line 247
    invoke-static {v0, v7}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;)I

    #@18d
    .line 250
    iget v7, v4, Lcom/android/internal/os/ZygoteArguments;->mUid:I

    #@18f
    iget v8, v4, Lcom/android/internal/os/ZygoteArguments;->mGid:I

    #@191
    iget-object v9, v4, Lcom/android/internal/os/ZygoteArguments;->mGids:[I

    #@193
    iget v10, v4, Lcom/android/internal/os/ZygoteArguments;->mRuntimeFlags:I

    #@195
    move-object v11, v12

    #@196
    .end local v12    # "rlimits":[[I
    .local v11, "rlimits":[[I
    iget v12, v4, Lcom/android/internal/os/ZygoteArguments;->mMountExternal:I

    #@198
    move-object/from16 v17, v13

    #@19a
    .end local v13    # "childPipeFd":Ljava/io/FileDescriptor;
    .local v17, "childPipeFd":Ljava/io/FileDescriptor;
    iget-object v13, v4, Lcom/android/internal/os/ZygoteArguments;->mSeInfo:Ljava/lang/String;

    #@19c
    move-object/from16 v18, v14

    #@19e
    .end local v14    # "serverPipeFd":Ljava/io/FileDescriptor;
    .local v18, "serverPipeFd":Ljava/io/FileDescriptor;
    iget-object v14, v4, Lcom/android/internal/os/ZygoteArguments;->mNiceName:Ljava/lang/String;

    #@1a0
    iget-boolean v0, v4, Lcom/android/internal/os/ZygoteArguments;->mStartChildZygote:Z

    #@1a2
    move-object/from16 v28, v6

    #@1a4
    iget-object v6, v4, Lcom/android/internal/os/ZygoteArguments;->mInstructionSet:Ljava/lang/String;

    #@1a6
    move/from16 v19, v0

    #@1a8
    iget-object v0, v4, Lcom/android/internal/os/ZygoteArguments;->mAppDataDir:Ljava/lang/String;

    #@1aa
    move-object/from16 v20, v0

    #@1ac
    iget-boolean v0, v4, Lcom/android/internal/os/ZygoteArguments;->mIsTopApp:Z

    #@1ae
    move/from16 v21, v0

    #@1b0
    iget-object v0, v4, Lcom/android/internal/os/ZygoteArguments;->mPkgDataInfoList:[Ljava/lang/String;

    #@1b2
    move-object/from16 v22, v0

    #@1b4
    iget-object v0, v4, Lcom/android/internal/os/ZygoteArguments;->mAllowlistedDataInfoList:[Ljava/lang/String;

    #@1b6
    move-object/from16 v23, v0

    #@1b8
    iget-boolean v0, v4, Lcom/android/internal/os/ZygoteArguments;->mBindMountAppDataDirs:Z

    #@1ba
    move/from16 v24, v0

    #@1bc
    iget-boolean v0, v4, Lcom/android/internal/os/ZygoteArguments;->mBindMountAppStorageDirs:Z

    #@1be
    move/from16 v25, v0

    #@1c0
    iget-boolean v0, v4, Lcom/android/internal/os/ZygoteArguments;->mBindMountSyspropOverrides:Z

    #@1c2
    move-object/from16 v29, v18

    #@1c4
    move-object/from16 v18, v6

    #@1c6
    move-object/from16 v6, v17

    #@1c8
    move/from16 v17, v19

    #@1ca
    move-object/from16 v19, v20

    #@1cc
    move/from16 v20, v21

    #@1ce
    move-object/from16 v21, v22

    #@1d0
    move-object/from16 v22, v23

    #@1d2
    move/from16 v23, v24

    #@1d4
    move/from16 v24, v25

    #@1d6
    move/from16 v25, v0

    #@1d8
    .end local v17    # "childPipeFd":Ljava/io/FileDescriptor;
    .end local v18    # "serverPipeFd":Ljava/io/FileDescriptor;
    .local v6, "childPipeFd":Ljava/io/FileDescriptor;
    .local v29, "serverPipeFd":Ljava/io/FileDescriptor;
    invoke-static/range {v7 .. v25}, Lcom/android/internal/os/Zygote;->forkAndSpecialize(II[II[[IILjava/lang/String;Ljava/lang/String;[I[IZLjava/lang/String;Ljava/lang/String;Z[Ljava/lang/String;[Ljava/lang/String;ZZZ)I

    #@1db
    move-result v0
    :try_end_1dc
    .catchall {:try_start_168 .. :try_end_1dc} :catchall_287

    #@1dc
    move v7, v0

    #@1dd
    .line 261
    .local v7, "pid":I
    if-nez v7, :cond_201

    #@1df
    .line 263
    :try_start_1df
    invoke-virtual {v2}, Lcom/android/internal/os/ZygoteServer;->setForkChild()V

    #@1e2
    .line 265
    invoke-virtual {v2}, Lcom/android/internal/os/ZygoteServer;->closeServerSocket()V

    #@1e5
    .line 266
    invoke-static/range {v29 .. v29}, Llibcore/io/IoUtils;->closeQuietly(Ljava/io/FileDescriptor;)V
    :try_end_1e8
    .catchall {:try_start_1df .. :try_end_1e8} :catchall_1fc

    #@1e8
    .line 267
    const/4 v14, 0x0

    #@1e9
    .line 269
    .end local v29    # "serverPipeFd":Ljava/io/FileDescriptor;
    .restart local v14    # "serverPipeFd":Ljava/io/FileDescriptor;
    :try_start_1e9
    iget-boolean v0, v4, Lcom/android/internal/os/ZygoteArguments;->mStartChildZygote:Z

    #@1eb
    invoke-direct {v1, v4, v6, v0}, Lcom/android/internal/os/ZygoteConnection;->handleChildProc(Lcom/android/internal/os/ZygoteArguments;Ljava/io/FileDescriptor;Z)Ljava/lang/Runnable;

    #@1ee
    move-result-object v0
    :try_end_1ef
    .catchall {:try_start_1e9 .. :try_end_1ef} :catchall_1f9

    #@1ef
    .line 280
    :try_start_1ef
    invoke-static {v6}, Llibcore/io/IoUtils;->closeQuietly(Ljava/io/FileDescriptor;)V

    #@1f2
    .line 281
    invoke-static {v14}, Llibcore/io/IoUtils;->closeQuietly(Ljava/io/FileDescriptor;)V
    :try_end_1f5
    .catchall {:try_start_1ef .. :try_end_1f5} :catchall_287

    #@1f5
    .line 302
    invoke-virtual {v5}, Lcom/android/internal/os/ZygoteCommandBuffer;->close()V

    #@1f8
    .line 269
    return-object v0

    #@1f9
    .line 280
    :catchall_1f9
    move-exception v0

    #@1fa
    move-object v13, v6

    #@1fb
    goto :goto_21d

    #@1fc
    .end local v14    # "serverPipeFd":Ljava/io/FileDescriptor;
    .restart local v29    # "serverPipeFd":Ljava/io/FileDescriptor;
    :catchall_1fc
    move-exception v0

    #@1fd
    move-object v13, v6

    #@1fe
    move-object/from16 v14, v29

    #@200
    goto :goto_21d

    #@201
    .line 274
    :cond_201
    :try_start_201
    invoke-static {v6}, Llibcore/io/IoUtils;->closeQuietly(Ljava/io/FileDescriptor;)V
    :try_end_204
    .catchall {:try_start_201 .. :try_end_204} :catchall_218

    #@204
    .line 275
    const/4 v13, 0x0

    #@205
    .line 276
    .end local v6    # "childPipeFd":Ljava/io/FileDescriptor;
    .restart local v13    # "childPipeFd":Ljava/io/FileDescriptor;
    move-object/from16 v8, v29

    #@207
    .end local v29    # "serverPipeFd":Ljava/io/FileDescriptor;
    .restart local v8    # "serverPipeFd":Ljava/io/FileDescriptor;
    :try_start_207
    invoke-direct {v1, v7, v8}, Lcom/android/internal/os/ZygoteConnection;->handleParentProc(ILjava/io/FileDescriptor;)V
    :try_end_20a
    .catchall {:try_start_207 .. :try_end_20a} :catchall_215

    #@20a
    .line 277
    nop

    #@20b
    .line 280
    :try_start_20b
    invoke-static {v13}, Llibcore/io/IoUtils;->closeQuietly(Ljava/io/FileDescriptor;)V

    #@20e
    .line 281
    invoke-static {v8}, Llibcore/io/IoUtils;->closeQuietly(Ljava/io/FileDescriptor;)V
    :try_end_211
    .catchall {:try_start_20b .. :try_end_211} :catchall_287

    #@211
    .line 302
    invoke-virtual {v5}, Lcom/android/internal/os/ZygoteCommandBuffer;->close()V

    #@214
    .line 277
    return-object v28

    #@215
    .line 280
    :catchall_215
    move-exception v0

    #@216
    move-object v14, v8

    #@217
    goto :goto_21d

    #@218
    .end local v8    # "serverPipeFd":Ljava/io/FileDescriptor;
    .end local v13    # "childPipeFd":Ljava/io/FileDescriptor;
    .restart local v6    # "childPipeFd":Ljava/io/FileDescriptor;
    .restart local v29    # "serverPipeFd":Ljava/io/FileDescriptor;
    :catchall_218
    move-exception v0

    #@219
    move-object/from16 v8, v29

    #@21b
    move-object v13, v6

    #@21c
    move-object v14, v8

    #@21d
    .end local v6    # "childPipeFd":Ljava/io/FileDescriptor;
    .end local v29    # "serverPipeFd":Ljava/io/FileDescriptor;
    .restart local v13    # "childPipeFd":Ljava/io/FileDescriptor;
    .restart local v14    # "serverPipeFd":Ljava/io/FileDescriptor;
    :goto_21d
    :try_start_21d
    invoke-static {v13}, Llibcore/io/IoUtils;->closeQuietly(Ljava/io/FileDescriptor;)V

    #@220
    .line 281
    invoke-static {v14}, Llibcore/io/IoUtils;->closeQuietly(Ljava/io/FileDescriptor;)V

    #@223
    .line 282
    nop

    #@224
    .end local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    .end local p0    # "this":Lcom/android/internal/os/ZygoteConnection;
    .end local p1    # "zygoteServer":Lcom/android/internal/os/ZygoteServer;
    .end local p2    # "multipleOK":Z
    throw v0

    #@225
    .line 186
    .end local v11    # "rlimits":[[I
    .end local v13    # "childPipeFd":Ljava/io/FileDescriptor;
    .end local v14    # "serverPipeFd":Ljava/io/FileDescriptor;
    .end local v15    # "fdsToClose":[I
    .end local v16    # "fdsToIgnore":[I
    .end local v26    # "fd":Ljava/io/FileDescriptor;
    .end local v27    # "zygoteFd":Ljava/io/FileDescriptor;
    .restart local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    .local v7, "childPipeFd":Ljava/io/FileDescriptor;
    .restart local v8    # "serverPipeFd":Ljava/io/FileDescriptor;
    .restart local p0    # "this":Lcom/android/internal/os/ZygoteConnection;
    .restart local p1    # "zygoteServer":Lcom/android/internal/os/ZygoteServer;
    .restart local p2    # "multipleOK":Z
    :cond_225
    new-instance v0, Lcom/android/internal/os/ZygoteSecurityException;

    #@227
    new-instance v6, Ljava/lang/StringBuilder;

    #@229
    invoke-direct {v6}, Ljava/lang/StringBuilder;-><init>()V

    #@22c
    const-string v9, "Client may not specify capabilities: permitted=0x"

    #@22e
    invoke-virtual {v6, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@231
    move-result-object v6

    #@232
    iget-wide v9, v4, Lcom/android/internal/os/ZygoteArguments;->mPermittedCapabilities:J

    #@234
    .line 187
    invoke-static {v9, v10}, Ljava/lang/Long;->toHexString(J)Ljava/lang/String;

    #@237
    move-result-object v9

    #@238
    invoke-virtual {v6, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@23b
    move-result-object v6

    #@23c
    const-string v9, ", effective=0x"

    #@23e
    invoke-virtual {v6, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@241
    move-result-object v6

    #@242
    iget-wide v9, v4, Lcom/android/internal/os/ZygoteArguments;->mEffectiveCapabilities:J

    #@244
    .line 189
    invoke-static {v9, v10}, Ljava/lang/Long;->toHexString(J)Ljava/lang/String;

    #@247
    move-result-object v9

    #@248
    invoke-virtual {v6, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@24b
    move-result-object v6

    #@24c
    invoke-virtual {v6}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@24f
    move-result-object v6

    #@250
    invoke-direct {v0, v6}, Lcom/android/internal/os/ZygoteSecurityException;-><init>(Ljava/lang/String;)V

    #@253
    .end local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    .end local p0    # "this":Lcom/android/internal/os/ZygoteConnection;
    .end local p1    # "zygoteServer":Lcom/android/internal/os/ZygoteServer;
    .end local p2    # "multipleOK":Z
    throw v0
    :try_end_254
    .catchall {:try_start_21d .. :try_end_254} :catchall_287

    #@254
    .line 302
    .end local v7    # "childPipeFd":Ljava/io/FileDescriptor;
    .end local v8    # "serverPipeFd":Ljava/io/FileDescriptor;
    .restart local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    .restart local p0    # "this":Lcom/android/internal/os/ZygoteConnection;
    .restart local p1    # "zygoteServer":Lcom/android/internal/os/ZygoteServer;
    .restart local p2    # "multipleOK":Z
    :cond_254
    :goto_254
    invoke-virtual {v5}, Lcom/android/internal/os/ZygoteCommandBuffer;->close()V

    #@257
    .line 304
    .end local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    iget-boolean v0, v4, Lcom/android/internal/os/ZygoteArguments;->mUsapPoolStatusSpecified:Z

    #@259
    if-eqz v0, :cond_262

    #@25b
    .line 305
    iget-boolean v0, v4, Lcom/android/internal/os/ZygoteArguments;->mUsapPoolEnabled:Z

    #@25d
    invoke-direct {v1, v2, v0}, Lcom/android/internal/os/ZygoteConnection;->handleUsapPoolStatusChange(Lcom/android/internal/os/ZygoteServer;Z)Ljava/lang/Runnable;

    #@260
    move-result-object v0

    #@261
    return-object v0

    #@262
    .line 307
    :cond_262
    iget-object v0, v4, Lcom/android/internal/os/ZygoteArguments;->mApiDenylistExemptions:[Ljava/lang/String;

    #@264
    if-eqz v0, :cond_26d

    #@266
    .line 308
    iget-object v0, v4, Lcom/android/internal/os/ZygoteArguments;->mApiDenylistExemptions:[Ljava/lang/String;

    #@268
    invoke-direct {v1, v2, v0}, Lcom/android/internal/os/ZygoteConnection;->handleApiDenylistExemptions(Lcom/android/internal/os/ZygoteServer;[Ljava/lang/String;)Ljava/lang/Runnable;

    #@26b
    move-result-object v0

    #@26c
    return-object v0

    #@26d
    .line 311
    :cond_26d
    iget v0, v4, Lcom/android/internal/os/ZygoteArguments;->mHiddenApiAccessLogSampleRate:I

    #@26f
    if-ne v0, v10, :cond_27e

    #@271
    iget v0, v4, Lcom/android/internal/os/ZygoteArguments;->mHiddenApiAccessStatslogSampleRate:I

    #@273
    if-eq v0, v10, :cond_276

    #@275
    goto :goto_27e

    #@276
    .line 317
    :cond_276
    new-instance v0, Ljava/lang/AssertionError;

    #@278
    const-string v5, "Shouldn\'t get here"

    #@27a
    invoke-direct {v0, v5}, Ljava/lang/AssertionError;-><init>(Ljava/lang/Object;)V

    #@27d
    throw v0

    #@27e
    .line 313
    :cond_27e
    :goto_27e
    iget v0, v4, Lcom/android/internal/os/ZygoteArguments;->mHiddenApiAccessLogSampleRate:I

    #@280
    iget v5, v4, Lcom/android/internal/os/ZygoteArguments;->mHiddenApiAccessStatslogSampleRate:I

    #@282
    invoke-direct {v1, v2, v0, v5}, Lcom/android/internal/os/ZygoteConnection;->handleHiddenApiAccessLogSampleRate(Lcom/android/internal/os/ZygoteServer;II)Ljava/lang/Runnable;

    #@285
    move-result-object v0

    #@286
    return-object v0

    #@287
    .line 123
    .end local v4    # "parsedArgs":Lcom/android/internal/os/ZygoteArguments;
    .restart local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    :catchall_287
    move-exception v0

    #@288
    move-object v4, v0

    #@289
    goto :goto_293

    #@28a
    .line 128
    :catch_28a
    move-exception v0

    #@28b
    .line 129
    .local v0, "ex":Ljava/io/IOException;
    :try_start_28b
    new-instance v4, Ljava/lang/IllegalStateException;

    #@28d
    const-string v6, "IOException on command socket"

    #@28f
    invoke-direct {v4, v6, v0}, Ljava/lang/IllegalStateException;-><init>(Ljava/lang/String;Ljava/lang/Throwable;)V

    #@292
    .end local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    .end local p0    # "this":Lcom/android/internal/os/ZygoteConnection;
    .end local p1    # "zygoteServer":Lcom/android/internal/os/ZygoteServer;
    .end local p2    # "multipleOK":Z
    throw v4
    :try_end_293
    .catchall {:try_start_28b .. :try_end_293} :catchall_287

    #@293
    .line 123
    .end local v0    # "ex":Ljava/io/IOException;
    .restart local v5    # "argBuffer":Lcom/android/internal/os/ZygoteCommandBuffer;
    .restart local p0    # "this":Lcom/android/internal/os/ZygoteConnection;
    .restart local p1    # "zygoteServer":Lcom/android/internal/os/ZygoteServer;
    .restart local p2    # "multipleOK":Z
    :goto_293
    :try_start_293
    invoke-virtual {v5}, Lcom/android/internal/os/ZygoteCommandBuffer;->close()V
    :try_end_296
    .catchall {:try_start_293 .. :try_end_296} :catchall_297

    #@296
    goto :goto_29b

    #@297
    :catchall_297
    move-exception v0

    #@298
    invoke-virtual {v4, v0}, Ljava/lang/Throwable;->addSuppressed(Ljava/lang/Throwable;)V

    #@29b
    :goto_29b
    throw v4
.end method
