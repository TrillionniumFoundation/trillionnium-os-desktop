.method private static blacklist preserveCapabilities()V
    .registers 16

    #@0
    .line 190
    const-string v1, "AndroidRuntime"

    #@2
    new-instance v0, Landroid/system/StructCapUserHeader;

    #@4
    sget v2, Landroid/system/OsConstants;->_LINUX_CAPABILITY_VERSION_3:I

    #@6
    const/4 v3, 0x0

    #@7
    invoke-direct {v0, v2, v3}, Landroid/system/StructCapUserHeader;-><init>(II)V

    #@a
    move-object v2, v0

    #@b
    .line 194
    .local v2, "header":Landroid/system/StructCapUserHeader;
    :try_start_b
    invoke-static {v2}, Landroid/system/Os;->capget(Landroid/system/StructCapUserHeader;)[Landroid/system/StructCapUserData;

    #@e
    move-result-object v0
    :try_end_f
    .catch Landroid/system/ErrnoException; {:try_start_b .. :try_end_f} :catch_95

    #@f
    move-object v4, v0

    #@10
    .line 198
    .local v4, "data":[Landroid/system/StructCapUserData;
    nop

    #@11
    .line 200
    aget-object v0, v4, v3

    #@13
    iget v0, v0, Landroid/system/StructCapUserData;->permitted:I

    #@15
    aget-object v5, v4, v3

    #@17
    iget v5, v5, Landroid/system/StructCapUserData;->inheritable:I

    #@19
    const/4 v6, 0x1

    #@1a
    if-ne v0, v5, :cond_26

    #@1c
    aget-object v0, v4, v6

    #@1e
    iget v0, v0, Landroid/system/StructCapUserData;->permitted:I

    #@20
    aget-object v5, v4, v6

    #@22
    iget v5, v5, Landroid/system/StructCapUserData;->inheritable:I

    #@24
    if-eq v0, v5, :cond_50

    #@26
    .line 202
    :cond_26
    new-instance v0, Landroid/system/StructCapUserData;

    #@28
    aget-object v5, v4, v3

    #@2a
    iget v5, v5, Landroid/system/StructCapUserData;->effective:I

    #@2c
    aget-object v7, v4, v3

    #@2e
    iget v7, v7, Landroid/system/StructCapUserData;->permitted:I

    #@30
    aget-object v8, v4, v3

    #@32
    iget v8, v8, Landroid/system/StructCapUserData;->permitted:I

    #@34
    invoke-direct {v0, v5, v7, v8}, Landroid/system/StructCapUserData;-><init>(III)V

    #@37
    aput-object v0, v4, v3

    #@39
    .line 204
    new-instance v0, Landroid/system/StructCapUserData;

    #@3b
    aget-object v3, v4, v6

    #@3d
    iget v3, v3, Landroid/system/StructCapUserData;->effective:I

    #@3f
    aget-object v5, v4, v6

    #@41
    iget v5, v5, Landroid/system/StructCapUserData;->permitted:I

    #@43
    aget-object v7, v4, v6

    #@45
    iget v7, v7, Landroid/system/StructCapUserData;->permitted:I

    #@47
    invoke-direct {v0, v3, v5, v7}, Landroid/system/StructCapUserData;-><init>(III)V

    #@4a
    aput-object v0, v4, v6

    #@4c
    .line 207
    :try_start_4c
    invoke-static {v2, v4}, Landroid/system/Os;->capset(Landroid/system/StructCapUserHeader;[Landroid/system/StructCapUserData;)V
    :try_end_4f
    .catch Landroid/system/ErrnoException; {:try_start_4c .. :try_end_4f} :catch_8e

    #@4f
    .line 211
    nop

    #@50
    .line 214
    :cond_50
    const/4 v0, 0x0

    #@51
    move v3, v0

    #@52
    .local v3, "i":I
    :goto_52
    const/16 v0, 0x40

    #@54
    if-ge v3, v0, :cond_8d

    #@56
    .line 215
    invoke-static {v3}, Landroid/system/OsConstants;->CAP_TO_INDEX(I)I

    #@59
    move-result v5

    #@5a
    .line 216
    .local v5, "dataIndex":I
    invoke-static {v3}, Landroid/system/OsConstants;->CAP_TO_MASK(I)I

    #@5d
    move-result v6

    #@5e
    .line 217
    .local v6, "capMask":I
    aget-object v0, v4, v5

    #@60
    iget v0, v0, Landroid/system/StructCapUserData;->inheritable:I

    #@62
    and-int/2addr v0, v6

    #@63
    if-eqz v0, :cond_8a

    #@65
    .line 219
    :try_start_65
    sget v7, Landroid/system/OsConstants;->PR_CAP_AMBIENT:I

    #@67
    sget v0, Landroid/system/OsConstants;->PR_CAP_AMBIENT_RAISE:I

    #@69
    int-to-long v8, v0

    #@6a
    int-to-long v10, v3

    #@6b
    const-wide/16 v12, 0x0

    #@6d
    const-wide/16 v14, 0x0

    #@6f
    invoke-static/range {v7 .. v15}, Landroid/system/Os;->prctl(IJJJJ)I
    :try_end_72
    .catch Landroid/system/ErrnoException; {:try_start_65 .. :try_end_72} :catch_73

    #@72
    .line 226
    goto :goto_8a

    #@73
    .line 221
    :catch_73
    move-exception v0

    #@74
    .line 224
    .local v0, "ex":Landroid/system/ErrnoException;
    new-instance v7, Ljava/lang/StringBuilder;

    #@76
    invoke-direct {v7}, Ljava/lang/StringBuilder;-><init>()V

    #@79
    const-string v8, "RuntimeInit: Failed to raise ambient capability "

    #@7b
    invoke-virtual {v7, v8}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@7e
    move-result-object v7

    #@7f
    invoke-virtual {v7, v3}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@82
    move-result-object v7

    #@83
    invoke-virtual {v7}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@86
    move-result-object v7

    #@87
    invoke-static {v1, v7, v0}, Landroid/util/Slog;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I

    #@8a
    .line 214
    .end local v0    # "ex":Landroid/system/ErrnoException;
    .end local v5    # "dataIndex":I
    .end local v6    # "capMask":I
    :cond_8a
    :goto_8a
    add-int/lit8 v3, v3, 0x1

    #@8c
    goto :goto_52

    #@8d
    .line 229
    .end local v3    # "i":I
    :cond_8d
    return-void

    #@8e
    .line 208
    :catch_8e
    move-exception v0

    #@8f
    .line 209
    .local v0, "e":Landroid/system/ErrnoException;
    const-string v3, "RuntimeInit: Failed capset"

    #@91
    invoke-static {v1, v3, v0}, Landroid/util/Slog;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I

    #@94
    .line 210
    return-void

    #@95
    .line 195
    .end local v0    # "e":Landroid/system/ErrnoException;
    .end local v4    # "data":[Landroid/system/StructCapUserData;
    :catch_95
    move-exception v0

    #@96
    .line 196
    .restart local v0    # "e":Landroid/system/ErrnoException;
    const-string v3, "RuntimeInit: Failed capget"

    #@98
    invoke-static {v1, v3, v0}, Landroid/util/Slog;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I

    #@9b
    .line 197
    return-void
.end method
