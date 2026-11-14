.method public whitelist readFromParcel(Landroid/os/Parcel;)V
    .registers 10
    .param p1, "in"    # Landroid/os/Parcel;

    #@0
    .line 12876
    invoke-virtual {p1}, Landroid/os/Parcel;->readString8()Ljava/lang/String;

    #@3
    move-result-object v0

    #@4
    invoke-virtual {p0, v0}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    #@7
    .line 12877
    sget-object v0, Landroid/net/Uri;->CREATOR:Landroid/os/Parcelable$Creator;

    #@9
    invoke-interface {v0, p1}, Landroid/os/Parcelable$Creator;->createFromParcel(Landroid/os/Parcel;)Ljava/lang/Object;

    #@c
    move-result-object v0

    #@d
    check-cast v0, Landroid/net/Uri;

    #@f
    iput-object v0, p0, Landroid/content/Intent;->mData:Landroid/net/Uri;

    #@11
    .line 12878
    invoke-virtual {p1}, Landroid/os/Parcel;->readString8()Ljava/lang/String;

    #@14
    move-result-object v0

    #@15
    iput-object v0, p0, Landroid/content/Intent;->mType:Ljava/lang/String;

    #@17
    .line 12879
    invoke-virtual {p1}, Landroid/os/Parcel;->readString8()Ljava/lang/String;

    #@1a
    move-result-object v0

    #@1b
    iput-object v0, p0, Landroid/content/Intent;->mIdentifier:Ljava/lang/String;

    #@1d
    .line 12880
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@20
    move-result v0

    #@21
    iput v0, p0, Landroid/content/Intent;->mFlags:I

    #@23
    .line 12881
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@26
    move-result v0

    #@27
    iput v0, p0, Landroid/content/Intent;->mExtendedFlags:I

    #@29
    .line 12882
    invoke-virtual {p1}, Landroid/os/Parcel;->readString8()Ljava/lang/String;

    #@2c
    move-result-object v0

    #@2d
    iput-object v0, p0, Landroid/content/Intent;->mPackage:Ljava/lang/String;

    #@2f
    .line 12883
    invoke-static {p1}, Landroid/content/ComponentName;->readFromParcel(Landroid/os/Parcel;)Landroid/content/ComponentName;

    #@32
    move-result-object v0

    #@33
    iput-object v0, p0, Landroid/content/Intent;->mComponent:Landroid/content/ComponentName;

    #@35
    .line 12885
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@38
    move-result v0

    #@39
    if-eqz v0, :cond_45

    #@3b
    .line 12886
    sget-object v0, Landroid/graphics/Rect;->CREATOR:Landroid/os/Parcelable$Creator;

    #@3d
    invoke-interface {v0, p1}, Landroid/os/Parcelable$Creator;->createFromParcel(Landroid/os/Parcel;)Ljava/lang/Object;

    #@40
    move-result-object v0

    #@41
    check-cast v0, Landroid/graphics/Rect;

    #@43
    iput-object v0, p0, Landroid/content/Intent;->mSourceBounds:Landroid/graphics/Rect;

    #@45
    .line 12889
    :cond_45
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@48
    move-result v0

    #@49
    .line 12890
    .local v0, "N":I
    const/4 v1, 0x0

    #@4a
    if-lez v0, :cond_67

    #@4c
    .line 12891
    new-instance v2, Landroid/util/ArraySet;

    #@4e
    invoke-direct {v2}, Landroid/util/ArraySet;-><init>()V

    #@51
    iput-object v2, p0, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@53
    .line 12893
    const/4 v2, 0x0

    #@54
    .local v2, "i":I
    :goto_54
    if-ge v2, v0, :cond_66

    #@56
    .line 12894
    iget-object v3, p0, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@58
    invoke-virtual {p1}, Landroid/os/Parcel;->readString8()Ljava/lang/String;

    #@5b
    move-result-object v4

    #@5c
    invoke-virtual {v4}, Ljava/lang/String;->intern()Ljava/lang/String;

    #@5f
    move-result-object v4

    #@60
    invoke-virtual {v3, v4}, Landroid/util/ArraySet;->add(Ljava/lang/Object;)Z

    #@63
    .line 12893
    add-int/lit8 v2, v2, 0x1

    #@65
    goto :goto_54

    #@66
    .line 12896
    .end local v2    # "i":I
    :cond_66
    goto :goto_69

    #@67
    .line 12897
    :cond_67
    iput-object v1, p0, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@69
    .line 12900
    :goto_69
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@6c
    move-result v2

    #@6d
    if-eqz v2, :cond_76

    #@6f
    .line 12901
    new-instance v2, Landroid/content/Intent;

    #@71
    invoke-direct {v2, p1}, Landroid/content/Intent;-><init>(Landroid/os/Parcel;)V

    #@74
    iput-object v2, p0, Landroid/content/Intent;->mSelector:Landroid/content/Intent;

    #@76
    .line 12904
    :cond_76
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@79
    move-result v2

    #@7a
    if-eqz v2, :cond_83

    #@7c
    .line 12905
    new-instance v2, Landroid/content/ClipData;

    #@7e
    invoke-direct {v2, p1}, Landroid/content/ClipData;-><init>(Landroid/os/Parcel;)V

    #@81
    iput-object v2, p0, Landroid/content/Intent;->mClipData:Landroid/content/ClipData;

    #@83
    .line 12907
    :cond_83
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@86
    move-result v2

    #@87
    iput v2, p0, Landroid/content/Intent;->mContentUserHint:I

    #@89
    .line 12908
    invoke-virtual {p1}, Landroid/os/Parcel;->readBundle()Landroid/os/Bundle;

    #@8c
    move-result-object v2

    #@8d
    iput-object v2, p0, Landroid/content/Intent;->mExtras:Landroid/os/Bundle;

    #@8f
    .line 12909
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@92
    move-result v2

    #@93
    if-eqz v2, :cond_9c

    #@95
    .line 12910
    new-instance v2, Landroid/content/Intent;

    #@97
    invoke-direct {v2, p1}, Landroid/content/Intent;-><init>(Landroid/os/Parcel;)V

    #@9a
    iput-object v2, p0, Landroid/content/Intent;->mOriginalIntent:Landroid/content/Intent;

    #@9c
    .line 12913
    :cond_9c
    invoke-static {}, Lcom/android/internal/hidden_from_bootclasspath/android/security/Flags;->preventIntentRedirect()Z

    #@9f
    move-result v2

    #@a0
    if-eqz v2, :cond_e8

    #@a2
    .line 12914
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@a5
    move-result v2

    #@a6
    if-eqz v2, :cond_e8

    #@a8
    .line 12915
    new-instance v2, Landroid/content/Intent$CreatorTokenInfo;

    #@aa
    invoke-direct {v2, v1}, Landroid/content/Intent$CreatorTokenInfo;-><init>(Landroid/content/Intent-IA;)V

    #@ad
    iput-object v2, p0, Landroid/content/Intent;->mCreatorTokenInfo:Landroid/content/Intent$CreatorTokenInfo;

    #@af
    .line 12916
    iget-object v2, p0, Landroid/content/Intent;->mCreatorTokenInfo:Landroid/content/Intent$CreatorTokenInfo;

    #@b1
    invoke-virtual {p1}, Landroid/os/Parcel;->readStrongBinder()Landroid/os/IBinder;

    #@b4
    move-result-object v3

    #@b5
    invoke-static {v2, v3}, Landroid/content/Intent$CreatorTokenInfo;->-$$Nest$fputmCreatorToken(Landroid/content/Intent$CreatorTokenInfo;Landroid/os/IBinder;)V

    #@b8
    .line 12918
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@bb
    move-result v0

    #@bc
    .line 12919
    if-lez v0, :cond_e8

    #@be
    .line 12920
    iget-object v2, p0, Landroid/content/Intent;->mCreatorTokenInfo:Landroid/content/Intent$CreatorTokenInfo;

    #@c0
    new-instance v3, Landroid/util/ArraySet;

    #@c2
    invoke-direct {v3, v0}, Landroid/util/ArraySet;-><init>(I)V

    #@c5
    invoke-static {v2, v3}, Landroid/content/Intent$CreatorTokenInfo;->-$$Nest$fputmNestedIntentKeys(Landroid/content/Intent$CreatorTokenInfo;Landroid/util/ArraySet;)V

    #@c8
    .line 12921
    const/4 v2, 0x0

    #@c9
    .restart local v2    # "i":I
    :goto_c9
    if-ge v2, v0, :cond_e8

    #@cb
    .line 12922
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@ce
    move-result v3

    #@cf
    .line 12923
    .local v3, "type":I
    invoke-virtual {p1}, Landroid/os/Parcel;->readString8()Ljava/lang/String;

    #@d2
    move-result-object v4

    #@d3
    .line 12924
    .local v4, "key":Ljava/lang/String;
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@d6
    move-result v5

    #@d7
    .line 12925
    .local v5, "index":I
    iget-object v6, p0, Landroid/content/Intent;->mCreatorTokenInfo:Landroid/content/Intent$CreatorTokenInfo;

    #@d9
    invoke-static {v6}, Landroid/content/Intent$CreatorTokenInfo;->-$$Nest$fgetmNestedIntentKeys(Landroid/content/Intent$CreatorTokenInfo;)Landroid/util/ArraySet;

    #@dc
    move-result-object v6

    #@dd
    new-instance v7, Landroid/content/Intent$NestedIntentKey;

    #@df
    invoke-direct {v7, v3, v4, v5, v1}, Landroid/content/Intent$NestedIntentKey;-><init>(ILjava/lang/String;ILandroid/content/Intent-IA;)V

    #@e2
    invoke-virtual {v6, v7}, Landroid/util/ArraySet;->append(Ljava/lang/Object;)V

    #@e5
    .line 12921
    .end local v3    # "type":I
    .end local v4    # "key":Ljava/lang/String;
    .end local v5    # "index":I
    add-int/lit8 v2, v2, 0x1

    #@e7
    goto :goto_c9

    #@e8
    .line 12931
    .end local v2    # "i":I
    :cond_e8
    return-void
.end method
