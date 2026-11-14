.method private constructor greylist-max-o <init>(Landroid/content/Intent;I)V
    .registers 5
    .param p1, "o"    # Landroid/content/Intent;
    .param p2, "copyMode"    # I

    #@0
    .line 8062
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    #@3
    .line 8029
    const/4 v0, -0x2

    #@4
    iput v0, p0, Landroid/content/Intent;->mContentUserHint:I

    #@6
    .line 8063
    iget-object v0, p1, Landroid/content/Intent;->mAction:Ljava/lang/String;

    #@8
    iput-object v0, p0, Landroid/content/Intent;->mAction:Ljava/lang/String;

    #@a
    .line 8064
    iget-object v0, p1, Landroid/content/Intent;->mData:Landroid/net/Uri;

    #@c
    iput-object v0, p0, Landroid/content/Intent;->mData:Landroid/net/Uri;

    #@e
    .line 8065
    iget-object v0, p1, Landroid/content/Intent;->mType:Ljava/lang/String;

    #@10
    iput-object v0, p0, Landroid/content/Intent;->mType:Ljava/lang/String;

    #@12
    .line 8066
    iget-object v0, p1, Landroid/content/Intent;->mIdentifier:Ljava/lang/String;

    #@14
    iput-object v0, p0, Landroid/content/Intent;->mIdentifier:Ljava/lang/String;

    #@16
    .line 8067
    iget-object v0, p1, Landroid/content/Intent;->mPackage:Ljava/lang/String;

    #@18
    iput-object v0, p0, Landroid/content/Intent;->mPackage:Ljava/lang/String;

    #@1a
    .line 8068
    iget-object v0, p1, Landroid/content/Intent;->mComponent:Landroid/content/ComponentName;

    #@1c
    iput-object v0, p0, Landroid/content/Intent;->mComponent:Landroid/content/ComponentName;

    #@1e
    .line 8069
    iget-object v0, p1, Landroid/content/Intent;->mOriginalIntent:Landroid/content/Intent;

    #@20
    iput-object v0, p0, Landroid/content/Intent;->mOriginalIntent:Landroid/content/Intent;

    #@22
    .line 8070
    iget-object v0, p1, Landroid/content/Intent;->mCreatorTokenInfo:Landroid/content/Intent$CreatorTokenInfo;

    #@24
    iput-object v0, p0, Landroid/content/Intent;->mCreatorTokenInfo:Landroid/content/Intent$CreatorTokenInfo;

    #@26
    .line 8072
    iget-object v0, p1, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@28
    if-eqz v0, :cond_33

    #@2a
    .line 8073
    new-instance v0, Landroid/util/ArraySet;

    #@2c
    iget-object v1, p1, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@2e
    invoke-direct {v0, v1}, Landroid/util/ArraySet;-><init>(Landroid/util/ArraySet;)V

    #@31
    iput-object v0, p0, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@33
    .line 8078
    :cond_33
    iget v0, p1, Landroid/content/Intent;->mLocalFlags:I

    #@35
    iput v0, p0, Landroid/content/Intent;->mLocalFlags:I

    #@37
    .line 8079
    iget v0, p0, Landroid/content/Intent;->mLocalFlags:I

    #@39
    const/4 v1, 0x1

    #@3a
    or-int/2addr v0, v1

    #@3b
    iput v0, p0, Landroid/content/Intent;->mLocalFlags:I

    #@3d
    .line 8081
    if-eq p2, v1, :cond_97

    #@3f
    .line 8082
    iget v0, p1, Landroid/content/Intent;->mFlags:I

    #@41
    iput v0, p0, Landroid/content/Intent;->mFlags:I

    #@43
    .line 8083
    iget v0, p1, Landroid/content/Intent;->mExtendedFlags:I

    #@45
    iput v0, p0, Landroid/content/Intent;->mExtendedFlags:I

    #@47
    .line 8084
    iget v0, p1, Landroid/content/Intent;->mContentUserHint:I

    #@49
    iput v0, p0, Landroid/content/Intent;->mContentUserHint:I

    #@4b
    .line 8085
    iget-object v0, p1, Landroid/content/Intent;->mLaunchToken:Ljava/lang/String;

    #@4d
    iput-object v0, p0, Landroid/content/Intent;->mLaunchToken:Ljava/lang/String;

    #@4f
    .line 8086
    iget-object v0, p1, Landroid/content/Intent;->mSourceBounds:Landroid/graphics/Rect;

    #@51
    if-eqz v0, :cond_5c

    #@53
    .line 8087
    new-instance v0, Landroid/graphics/Rect;

    #@55
    iget-object v1, p1, Landroid/content/Intent;->mSourceBounds:Landroid/graphics/Rect;

    #@57
    invoke-direct {v0, v1}, Landroid/graphics/Rect;-><init>(Landroid/graphics/Rect;)V

    #@5a
    iput-object v0, p0, Landroid/content/Intent;->mSourceBounds:Landroid/graphics/Rect;

    #@5c
    .line 8089
    :cond_5c
    iget-object v0, p1, Landroid/content/Intent;->mSelector:Landroid/content/Intent;

    #@5e
    if-eqz v0, :cond_69

    #@60
    .line 8090
    new-instance v0, Landroid/content/Intent;

    #@62
    iget-object v1, p1, Landroid/content/Intent;->mSelector:Landroid/content/Intent;

    #@64
    invoke-direct {v0, v1}, Landroid/content/Intent;-><init>(Landroid/content/Intent;)V

    #@67
    iput-object v0, p0, Landroid/content/Intent;->mSelector:Landroid/content/Intent;

    #@69
    .line 8093
    :cond_69
    const/4 v0, 0x2

    #@6a
    if-eq p2, v0, :cond_87

    #@6c
    .line 8094
    iget-object v0, p1, Landroid/content/Intent;->mExtras:Landroid/os/Bundle;

    #@6e
    if-eqz v0, :cond_79

    #@70
    .line 8095
    new-instance v0, Landroid/os/Bundle;

    #@72
    iget-object v1, p1, Landroid/content/Intent;->mExtras:Landroid/os/Bundle;

    #@74
    invoke-direct {v0, v1}, Landroid/os/Bundle;-><init>(Landroid/os/Bundle;)V

    #@77
    iput-object v0, p0, Landroid/content/Intent;->mExtras:Landroid/os/Bundle;

    #@79
    .line 8097
    :cond_79
    iget-object v0, p1, Landroid/content/Intent;->mClipData:Landroid/content/ClipData;

    #@7b
    if-eqz v0, :cond_97

    #@7d
    .line 8098
    new-instance v0, Landroid/content/ClipData;

    #@7f
    iget-object v1, p1, Landroid/content/Intent;->mClipData:Landroid/content/ClipData;

    #@81
    invoke-direct {v0, v1}, Landroid/content/ClipData;-><init>(Landroid/content/ClipData;)V

    #@84
    iput-object v0, p0, Landroid/content/Intent;->mClipData:Landroid/content/ClipData;

    #@86
    goto :goto_97

    #@87
    .line 8101
    :cond_87
    iget-object v0, p1, Landroid/content/Intent;->mExtras:Landroid/os/Bundle;

    #@89
    if-eqz v0, :cond_97

    #@8b
    iget-object v0, p1, Landroid/content/Intent;->mExtras:Landroid/os/Bundle;

    #@8d
    invoke-virtual {v0}, Landroid/os/Bundle;->isDefinitelyEmpty()Z

    #@90
    move-result v0

    #@91
    if-nez v0, :cond_97

    #@93
    .line 8102
    sget-object v0, Landroid/os/Bundle;->STRIPPED:Landroid/os/Bundle;

    #@95
    iput-object v0, p0, Landroid/content/Intent;->mExtras:Landroid/os/Bundle;

    #@97
    .line 8109
    :cond_97
    :goto_97
    return-void
.end method
