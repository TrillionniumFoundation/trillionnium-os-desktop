.method public whitelist writeToParcel(Landroid/os/Parcel;I)V
    .registers 8
    .param p1, "out"    # Landroid/os/Parcel;
    .param p2, "flags"    # I

    #@0
    .line 12785
    iget-object v0, p0, Landroid/content/Intent;->mAction:Ljava/lang/String;

    #@2
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeString8(Ljava/lang/String;)V

    #@5
    .line 12786
    iget-object v0, p0, Landroid/content/Intent;->mData:Landroid/net/Uri;

    #@7
    invoke-static {p1, v0}, Landroid/net/Uri;->writeToParcel(Landroid/os/Parcel;Landroid/net/Uri;)V

    #@a
    .line 12787
    iget-object v0, p0, Landroid/content/Intent;->mType:Ljava/lang/String;

    #@c
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeString8(Ljava/lang/String;)V

    #@f
    .line 12788
    iget-object v0, p0, Landroid/content/Intent;->mIdentifier:Ljava/lang/String;

    #@11
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeString8(Ljava/lang/String;)V

    #@14
    .line 12789
    iget v0, p0, Landroid/content/Intent;->mFlags:I

    #@16
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@19
    .line 12790
    iget v0, p0, Landroid/content/Intent;->mExtendedFlags:I

    #@1b
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@1e
    .line 12791
    iget-object v0, p0, Landroid/content/Intent;->mPackage:Ljava/lang/String;

    #@20
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeString8(Ljava/lang/String;)V

    #@23
    .line 12792
    iget-object v0, p0, Landroid/content/Intent;->mComponent:Landroid/content/ComponentName;

    #@25
    invoke-static {v0, p1}, Landroid/content/ComponentName;->writeToParcel(Landroid/content/ComponentName;Landroid/os/Parcel;)V

    #@28
    .line 12794
    iget-object v0, p0, Landroid/content/Intent;->mSourceBounds:Landroid/graphics/Rect;

    #@2a
    const/4 v1, 0x1

    #@2b
    const/4 v2, 0x0

    #@2c
    if-eqz v0, :cond_37

    #@2e
    .line 12795
    invoke-virtual {p1, v1}, Landroid/os/Parcel;->writeInt(I)V

    #@31
    .line 12796
    iget-object v0, p0, Landroid/content/Intent;->mSourceBounds:Landroid/graphics/Rect;

    #@33
    invoke-virtual {v0, p1, p2}, Landroid/graphics/Rect;->writeToParcel(Landroid/os/Parcel;I)V

    #@36
    goto :goto_3a

    #@37
    .line 12798
    :cond_37
    invoke-virtual {p1, v2}, Landroid/os/Parcel;->writeInt(I)V

    #@3a
    .line 12801
    :goto_3a
    iget-object v0, p0, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@3c
    if-eqz v0, :cond_59

    #@3e
    .line 12802
    iget-object v0, p0, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@40
    invoke-virtual {v0}, Landroid/util/ArraySet;->size()I

    #@43
    move-result v0

    #@44
    .line 12803
    .local v0, "N":I
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@47
    .line 12804
    const/4 v3, 0x0

    #@48
    .local v3, "i":I
    :goto_48
    if-ge v3, v0, :cond_58

    #@4a
    .line 12805
    iget-object v4, p0, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@4c
    invoke-virtual {v4, v3}, Landroid/util/ArraySet;->valueAt(I)Ljava/lang/Object;

    #@4f
    move-result-object v4

    #@50
    check-cast v4, Ljava/lang/String;

    #@52
    invoke-virtual {p1, v4}, Landroid/os/Parcel;->writeString8(Ljava/lang/String;)V

    #@55
    .line 12804
    add-int/lit8 v3, v3, 0x1

    #@57
    goto :goto_48

    #@58
    .line 12807
    .end local v0    # "N":I
    .end local v3    # "i":I
    :cond_58
    goto :goto_5c

    #@59
    .line 12808
    :cond_59
    invoke-virtual {p1, v2}, Landroid/os/Parcel;->writeInt(I)V

    #@5c
    .line 12811
    :goto_5c
    iget-object v0, p0, Landroid/content/Intent;->mSelector:Landroid/content/Intent;

    #@5e
    if-eqz v0, :cond_69

    #@60
    .line 12812
    invoke-virtual {p1, v1}, Landroid/os/Parcel;->writeInt(I)V

    #@63
    .line 12813
    iget-object v0, p0, Landroid/content/Intent;->mSelector:Landroid/content/Intent;

    #@65
    invoke-virtual {v0, p1, p2}, Landroid/content/Intent;->writeToParcel(Landroid/os/Parcel;I)V

    #@68
    goto :goto_6c

    #@69
    .line 12815
    :cond_69
    invoke-virtual {p1, v2}, Landroid/os/Parcel;->writeInt(I)V

    #@6c
    .line 12818
    :goto_6c
    iget-object v0, p0, Landroid/content/Intent;->mClipData:Landroid/content/ClipData;

    #@6e
    if-eqz v0, :cond_79

    #@70
    .line 12819
    invoke-virtual {p1, v1}, Landroid/os/Parcel;->writeInt(I)V

    #@73
    .line 12820
    iget-object v0, p0, Landroid/content/Intent;->mClipData:Landroid/content/ClipData;

    #@75
    invoke-virtual {v0, p1, p2}, Landroid/content/ClipData;->writeToParcel(Landroid/os/Parcel;I)V

    #@78
    goto :goto_7c

    #@79
    .line 12822
    :cond_79
    invoke-virtual {p1, v2}, Landroid/os/Parcel;->writeInt(I)V

    #@7c
    .line 12824
    :goto_7c
    iget v0, p0, Landroid/content/Intent;->mContentUserHint:I

    #@7e
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@81
    .line 12825
    iget-object v0, p0, Landroid/content/Intent;->mExtras:Landroid/os/Bundle;

    #@83
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBundle(Landroid/os/Bundle;)V

    #@86
    .line 12827
    iget-object v0, p0, Landroid/content/Intent;->mOriginalIntent:Landroid/content/Intent;

    #@88
    if-eqz v0, :cond_93

    #@8a
    .line 12828
    invoke-virtual {p1, v1}, Landroid/os/Parcel;->writeInt(I)V

    #@8d
    .line 12829
    iget-object v0, p0, Landroid/content/Intent;->mOriginalIntent:Landroid/content/Intent;

    #@8f
    invoke-virtual {v0, p1, p2}, Landroid/content/Intent;->writeToParcel(Landroid/os/Parcel;I)V

    #@92
    goto :goto_96

    #@93
    .line 12831
    :cond_93
    invoke-virtual {p1, v2}, Landroid/os/Parcel;->writeInt(I)V

    #@96
    .line 12834
    :goto_96
    invoke-static {}, Lcom/android/internal/hidden_from_bootclasspath/android/security/Flags;->preventIntentRedirect()Z

    #@99
    move-result v0

    #@9a
    if-eqz v0, :cond_f0

    #@9c
    .line 12835
    iget-object v0, p0, Landroid/content/Intent;->mCreatorTokenInfo:Landroid/content/Intent$CreatorTokenInfo;

    #@9e
    if-nez v0, :cond_a4

    #@a0
    .line 12836
    invoke-virtual {p1, v2}, Landroid/os/Parcel;->writeInt(I)V

    #@a3
    goto :goto_f0

    #@a4
    .line 12838
    :cond_a4
    invoke-virtual {p1, v1}, Landroid/os/Parcel;->writeInt(I)V

    #@a7
    .line 12839
    iget-object v0, p0, Landroid/content/Intent;->mCreatorTokenInfo:Landroid/content/Intent$CreatorTokenInfo;

    #@a9
    invoke-static {v0}, Landroid/content/Intent$CreatorTokenInfo;->-$$Nest$fgetmCreatorToken(Landroid/content/Intent$CreatorTokenInfo;)Landroid/os/IBinder;

    #@ac
    move-result-object v0

    #@ad
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeStrongBinder(Landroid/os/IBinder;)V

    #@b0
    .line 12841
    iget-object v0, p0, Landroid/content/Intent;->mCreatorTokenInfo:Landroid/content/Intent$CreatorTokenInfo;

    #@b2
    invoke-static {v0}, Landroid/content/Intent$CreatorTokenInfo;->-$$Nest$fgetmNestedIntentKeys(Landroid/content/Intent$CreatorTokenInfo;)Landroid/util/ArraySet;

    #@b5
    move-result-object v0

    #@b6
    if-eqz v0, :cond_ed

    #@b8
    .line 12842
    iget-object v0, p0, Landroid/content/Intent;->mCreatorTokenInfo:Landroid/content/Intent$CreatorTokenInfo;

    #@ba
    invoke-static {v0}, Landroid/content/Intent$CreatorTokenInfo;->-$$Nest$fgetmNestedIntentKeys(Landroid/content/Intent$CreatorTokenInfo;)Landroid/util/ArraySet;

    #@bd
    move-result-object v0

    #@be
    invoke-virtual {v0}, Landroid/util/ArraySet;->size()I

    #@c1
    move-result v0

    #@c2
    .line 12843
    .restart local v0    # "N":I
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@c5
    .line 12844
    const/4 v1, 0x0

    #@c6
    .local v1, "i":I
    :goto_c6
    if-ge v1, v0, :cond_ec

    #@c8
    .line 12845
    iget-object v2, p0, Landroid/content/Intent;->mCreatorTokenInfo:Landroid/content/Intent$CreatorTokenInfo;

    #@ca
    invoke-static {v2}, Landroid/content/Intent$CreatorTokenInfo;->-$$Nest$fgetmNestedIntentKeys(Landroid/content/Intent$CreatorTokenInfo;)Landroid/util/ArraySet;

    #@cd
    move-result-object v2

    #@ce
    invoke-virtual {v2, v1}, Landroid/util/ArraySet;->valueAt(I)Ljava/lang/Object;

    #@d1
    move-result-object v2

    #@d2
    check-cast v2, Landroid/content/Intent$NestedIntentKey;

    #@d4
    .line 12846
    .local v2, "key":Landroid/content/Intent$NestedIntentKey;
    invoke-static {v2}, Landroid/content/Intent$NestedIntentKey;->-$$Nest$fgetmType(Landroid/content/Intent$NestedIntentKey;)I

    #@d7
    move-result v3

    #@d8
    invoke-virtual {p1, v3}, Landroid/os/Parcel;->writeInt(I)V

    #@db
    .line 12847
    invoke-static {v2}, Landroid/content/Intent$NestedIntentKey;->-$$Nest$fgetmKey(Landroid/content/Intent$NestedIntentKey;)Ljava/lang/String;

    #@de
    move-result-object v3

    #@df
    invoke-virtual {p1, v3}, Landroid/os/Parcel;->writeString8(Ljava/lang/String;)V

    #@e2
    .line 12848
    invoke-static {v2}, Landroid/content/Intent$NestedIntentKey;->-$$Nest$fgetmIndex(Landroid/content/Intent$NestedIntentKey;)I

    #@e5
    move-result v3

    #@e6
    invoke-virtual {p1, v3}, Landroid/os/Parcel;->writeInt(I)V

    #@e9
    .line 12844
    .end local v2    # "key":Landroid/content/Intent$NestedIntentKey;
    add-int/lit8 v1, v1, 0x1

    #@eb
    goto :goto_c6

    #@ec
    .line 12850
    .end local v0    # "N":I
    .end local v1    # "i":I
    :cond_ec
    goto :goto_f0

    #@ed
    .line 12851
    :cond_ed
    invoke-virtual {p1, v2}, Landroid/os/Parcel;->writeInt(I)V

    #@f0
    .line 12855
    :cond_f0
    :goto_f0
    return-void
.end method
