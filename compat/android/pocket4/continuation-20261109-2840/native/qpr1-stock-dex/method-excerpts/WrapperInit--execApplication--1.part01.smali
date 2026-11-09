.method public static blacklist execApplication(Ljava/lang/String;Ljava/lang/String;ILjava/lang/String;Ljava/io/FileDescriptor;[Ljava/lang/String;)V
    .registers 11
    .param p0, "invokeWith"    # Ljava/lang/String;
    .param p1, "niceName"    # Ljava/lang/String;
    .param p2, "targetSdkVersion"    # I
    .param p3, "instructionSet"    # Ljava/lang/String;
    .param p4, "pipeFd"    # Ljava/io/FileDescriptor;
    .param p5, "args"    # [Ljava/lang/String;

    #@0
    .line 110
    new-instance v0, Ljava/lang/StringBuilder;

    #@2
    invoke-direct {v0, p0}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    #@5
    .line 113
    .local v0, "command":Ljava/lang/StringBuilder;
    invoke-static {p3}, Ldalvik/system/VMRuntime;->is64BitInstructionSet(Ljava/lang/String;)Z

    #@8
    move-result v1

    #@9
    if-eqz v1, :cond_e

    #@b
    .line 114
    const-string v1, "/system/bin/app_process64"

    #@d
    .local v1, "appProcess":Ljava/lang/String;
    goto :goto_10

    #@e
    .line 116
    .end local v1    # "appProcess":Ljava/lang/String;
    :cond_e
    const-string v1, "/system/bin/app_process32"

    #@10
    .line 118
    .restart local v1    # "appProcess":Ljava/lang/String;
    :goto_10
    const/16 v2, 0x20

    #@12
    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@15
    .line 119
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@18
    .line 127
    const-string v3, " -Xcompiler-option --generate-mini-debug-info"

    #@1a
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@1d
    .line 129
    const-string v3, " /system/bin --application"

    #@1f
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@22
    .line 130
    if-eqz p1, :cond_33

    #@24
    .line 131
    const-string v3, " \'--nice-name="

    #@26
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@29
    move-result-object v3

    #@2a
    invoke-virtual {v3, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@2d
    move-result-object v3

    #@2e
    const-string v4, "\'"

    #@30
    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@33
    .line 133
    :cond_33
    const-string v3, " com.android.internal.os.WrapperInit "

    #@35
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@38
    .line 134
    if-eqz p4, :cond_3f

    #@3a
    invoke-virtual {p4}, Ljava/io/FileDescriptor;->getInt$()I

    #@3d
    move-result v3

    #@3e
    goto :goto_40

    #@3f
    :cond_3f
    const/4 v3, 0x0

    #@40
    :goto_40
    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@43
    .line 135
    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@46
    .line 136
    invoke-virtual {v0, p2}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@49
    .line 137
    invoke-static {v0, p5}, Lcom/android/internal/os/Zygote;->appendQuotedShellArgs(Ljava/lang/StringBuilder;[Ljava/lang/String;)V

    #@4c
    .line 138
    invoke-static {}, Lcom/android/internal/os/WrapperInit;->preserveCapabilities()V

    #@4f
    .line 139
    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@52
    move-result-object v2

    #@53
    invoke-static {v2}, Lcom/android/internal/os/Zygote;->execShell(Ljava/lang/String;)V

    #@56
    .line 140
    return-void
.end method
