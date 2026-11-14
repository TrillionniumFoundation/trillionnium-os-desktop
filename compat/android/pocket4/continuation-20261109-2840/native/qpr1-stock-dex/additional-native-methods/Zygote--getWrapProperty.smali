.method public static blacklist getWrapProperty(Ljava/lang/String;)Ljava/lang/String;
    .registers 4
    .param p0, "appName"    # Ljava/lang/String;

    #@0
    .line 1121
    const/4 v0, 0x0

    #@1
    if-eqz p0, :cond_2c

    #@3
    invoke-virtual {p0}, Ljava/lang/String;->isEmpty()Z

    #@6
    move-result v1

    #@7
    if-eqz v1, :cond_a

    #@9
    goto :goto_2c

    #@a
    .line 1125
    :cond_a
    new-instance v1, Ljava/lang/StringBuilder;

    #@c
    invoke-direct {v1}, Ljava/lang/StringBuilder;-><init>()V

    #@f
    const-string/jumbo v2, "wrap."

    #@12
    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@15
    move-result-object v1

    #@16
    invoke-virtual {v1, p0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@19
    move-result-object v1

    #@1a
    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@1d
    move-result-object v1

    #@1e
    invoke-static {v1}, Landroid/os/SystemProperties;->get(Ljava/lang/String;)Ljava/lang/String;

    #@21
    move-result-object v1

    #@22
    .line 1126
    .local v1, "propertyValue":Ljava/lang/String;
    if-eqz v1, :cond_2b

    #@24
    invoke-virtual {v1}, Ljava/lang/String;->isEmpty()Z

    #@27
    move-result v2

    #@28
    if-nez v2, :cond_2b

    #@2a
    .line 1127
    return-object v1

    #@2b
    .line 1129
    :cond_2b
    return-object v0

    #@2c
    .line 1122
    .end local v1    # "propertyValue":Ljava/lang/String;
    :cond_2c
    :goto_2c
    return-object v0
.end method
