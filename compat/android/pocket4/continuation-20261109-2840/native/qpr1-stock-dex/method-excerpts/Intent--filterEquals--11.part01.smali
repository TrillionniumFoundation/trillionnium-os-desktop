.method public whitelist filterEquals(Landroid/content/Intent;)Z
    .registers 5
    .param p1, "other"    # Landroid/content/Intent;

    #@0
    .line 11969
    const/4 v0, 0x0

    #@1
    if-nez p1, :cond_4

    #@3
    .line 11970
    return v0

    #@4
    .line 11972
    :cond_4
    iget-object v1, p0, Landroid/content/Intent;->mAction:Ljava/lang/String;

    #@6
    iget-object v2, p1, Landroid/content/Intent;->mAction:Ljava/lang/String;

    #@8
    invoke-static {v1, v2}, Ljava/util/Objects;->equals(Ljava/lang/Object;Ljava/lang/Object;)Z

    #@b
    move-result v1

    #@c
    if-nez v1, :cond_f

    #@e
    return v0

    #@f
    .line 11973
    :cond_f
    iget-object v1, p0, Landroid/content/Intent;->mData:Landroid/net/Uri;

    #@11
    iget-object v2, p1, Landroid/content/Intent;->mData:Landroid/net/Uri;

    #@13
    invoke-static {v1, v2}, Ljava/util/Objects;->equals(Ljava/lang/Object;Ljava/lang/Object;)Z

    #@16
    move-result v1

    #@17
    if-nez v1, :cond_1a

    #@19
    return v0

    #@1a
    .line 11974
    :cond_1a
    iget-object v1, p0, Landroid/content/Intent;->mType:Ljava/lang/String;

    #@1c
    iget-object v2, p1, Landroid/content/Intent;->mType:Ljava/lang/String;

    #@1e
    invoke-static {v1, v2}, Ljava/util/Objects;->equals(Ljava/lang/Object;Ljava/lang/Object;)Z

    #@21
    move-result v1

    #@22
    if-nez v1, :cond_25

    #@24
    return v0

    #@25
    .line 11975
    :cond_25
    iget-object v1, p0, Landroid/content/Intent;->mIdentifier:Ljava/lang/String;

    #@27
    iget-object v2, p1, Landroid/content/Intent;->mIdentifier:Ljava/lang/String;

    #@29
    invoke-static {v1, v2}, Ljava/util/Objects;->equals(Ljava/lang/Object;Ljava/lang/Object;)Z

    #@2c
    move-result v1

    #@2d
    if-nez v1, :cond_30

    #@2f
    return v0

    #@30
    .line 11976
    :cond_30
    iget-object v1, p0, Landroid/content/Intent;->mPackage:Ljava/lang/String;

    #@32
    iget-object v2, p1, Landroid/content/Intent;->mPackage:Ljava/lang/String;

    #@34
    invoke-static {v1, v2}, Ljava/util/Objects;->equals(Ljava/lang/Object;Ljava/lang/Object;)Z

    #@37
    move-result v1

    #@38
    if-nez v1, :cond_3b

    #@3a
    return v0

    #@3b
    .line 11977
    :cond_3b
    iget-object v1, p0, Landroid/content/Intent;->mComponent:Landroid/content/ComponentName;

    #@3d
    iget-object v2, p1, Landroid/content/Intent;->mComponent:Landroid/content/ComponentName;

    #@3f
    invoke-static {v1, v2}, Ljava/util/Objects;->equals(Ljava/lang/Object;Ljava/lang/Object;)Z

    #@42
    move-result v1

    #@43
    if-nez v1, :cond_46

    #@45
    return v0

    #@46
    .line 11978
    :cond_46
    iget-object v1, p0, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@48
    iget-object v2, p1, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@4a
    invoke-static {v1, v2}, Ljava/util/Objects;->equals(Ljava/lang/Object;Ljava/lang/Object;)Z

    #@4d
    move-result v1

    #@4e
    if-nez v1, :cond_51

    #@50
    return v0

    #@51
    .line 11980
    :cond_51
    const/4 v0, 0x1

    #@52
    return v0
.end method
