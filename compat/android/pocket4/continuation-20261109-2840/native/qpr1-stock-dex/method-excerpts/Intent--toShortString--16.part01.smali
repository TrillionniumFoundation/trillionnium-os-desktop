.method public greylist-max-o toShortString(Ljava/lang/StringBuilder;ZZZZ)V
    .registers 16
    .param p1, "b"    # Ljava/lang/StringBuilder;
    .param p2, "secure"    # Z
    .param p3, "comp"    # Z
    .param p4, "extras"    # Z
    .param p5, "clip"    # Z

    #@0
    .line 12053
    const/4 v0, 0x1

    #@1
    .line 12054
    .local v0, "first":Z
    iget-object v1, p0, Landroid/content/Intent;->mAction:Ljava/lang/String;

    #@3
    if-eqz v1, :cond_11

    #@5
    .line 12055
    const-string v1, "act="

    #@7
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@a
    move-result-object v1

    #@b
    iget-object v2, p0, Landroid/content/Intent;->mAction:Ljava/lang/String;

    #@d
    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@10
    .line 12056
    const/4 v0, 0x0

    #@11
    .line 12058
    :cond_11
    iget-object v1, p0, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@13
    const/16 v2, 0x20

    #@15
    if-eqz v1, :cond_45

    #@17
    .line 12059
    if-nez v0, :cond_1c

    #@19
    .line 12060
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@1c
    .line 12062
    :cond_1c
    const/4 v0, 0x0

    #@1d
    .line 12063
    const-string v1, "cat=["

    #@1f
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@22
    .line 12064
    const/4 v1, 0x0

    #@23
    .local v1, "i":I
    :goto_23
    iget-object v3, p0, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@25
    invoke-virtual {v3}, Landroid/util/ArraySet;->size()I

    #@28
    move-result v3

    #@29
    if-ge v1, v3, :cond_40

    #@2b
    .line 12065
    if-lez v1, :cond_32

    #@2d
    const/16 v3, 0x2c

    #@2f
    invoke-virtual {p1, v3}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@32
    .line 12066
    :cond_32
    iget-object v3, p0, Landroid/content/Intent;->mCategories:Landroid/util/ArraySet;

    #@34
    invoke-virtual {v3, v1}, Landroid/util/ArraySet;->valueAt(I)Ljava/lang/Object;

    #@37
    move-result-object v3

    #@38
    check-cast v3, Ljava/lang/String;

    #@3a
    invoke-virtual {p1, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@3d
    .line 12064
    add-int/lit8 v1, v1, 0x1

    #@3f
    goto :goto_23

    #@40
    .line 12068
    .end local v1    # "i":I
    :cond_40
    const-string v1, "]"

    #@42
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@45
    .line 12070
    :cond_45
    iget-object v1, p0, Landroid/content/Intent;->mData:Landroid/net/Uri;

    #@47
    if-eqz v1, :cond_64

    #@49
    .line 12071
    if-nez v0, :cond_4e

    #@4b
    .line 12072
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@4e
    .line 12074
    :cond_4e
    const/4 v0, 0x0

    #@4f
    .line 12075
    const-string v1, "dat="

    #@51
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@54
    .line 12076
    nop

    #@55
    .line 12079
    iget-object v1, p0, Landroid/content/Intent;->mData:Landroid/net/Uri;

    #@57
    .line 12076
    if-eqz p2, :cond_61

    #@59
    .line 12077
    invoke-virtual {v1}, Landroid/net/Uri;->toSafeString()Ljava/lang/String;

    #@5c
    move-result-object v1

    #@5d
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@60
    goto :goto_64

    #@61
    .line 12079
    :cond_61
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@64
    .line 12082
    :cond_64
    :goto_64
    iget-object v1, p0, Landroid/content/Intent;->mType:Ljava/lang/String;

    #@66
    if-eqz v1, :cond_7a

    #@68
    .line 12083
    if-nez v0, :cond_6d

    #@6a
    .line 12084
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@6d
    .line 12086
    :cond_6d
    const/4 v0, 0x0

    #@6e
    .line 12087
    const-string/jumbo v1, "typ="

    #@71
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@74
    move-result-object v1

    #@75
    iget-object v3, p0, Landroid/content/Intent;->mType:Ljava/lang/String;

    #@77
    invoke-virtual {v1, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@7a
    .line 12089
    :cond_7a
    iget-object v1, p0, Landroid/content/Intent;->mIdentifier:Ljava/lang/String;

    #@7c
    if-eqz v1, :cond_90

    #@7e
    .line 12090
    if-nez v0, :cond_83

    #@80
    .line 12091
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@83
    .line 12093
    :cond_83
    const/4 v0, 0x0

    #@84
    .line 12094
    const-string/jumbo v1, "id="

    #@87
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@8a
    move-result-object v1

    #@8b
    iget-object v3, p0, Landroid/content/Intent;->mIdentifier:Ljava/lang/String;

    #@8d
    invoke-virtual {v1, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@90
    .line 12096
    :cond_90
    iget v1, p0, Landroid/content/Intent;->mFlags:I

    #@92
    if-eqz v1, :cond_a9

    #@94
    .line 12097
    if-nez v0, :cond_99

    #@96
    .line 12098
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@99
    .line 12100
    :cond_99
    const/4 v0, 0x0

    #@9a
    .line 12101
    const-string v1, "flg=0x"

    #@9c
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@9f
    move-result-object v1

    #@a0
    iget v3, p0, Landroid/content/Intent;->mFlags:I

    #@a2
    invoke-static {v3}, Ljava/lang/Integer;->toHexString(I)Ljava/lang/String;

    #@a5
    move-result-object v3

    #@a6
    invoke-virtual {v1, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@a9
    .line 12103
    :cond_a9
    iget v1, p0, Landroid/content/Intent;->mExtendedFlags:I

    #@ab
    if-eqz v1, :cond_c3

    #@ad
    .line 12104
    if-nez v0, :cond_b2

    #@af
    .line 12105
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@b2
    .line 12107
    :cond_b2
    const/4 v0, 0x0

    #@b3
    .line 12108
    const-string/jumbo v1, "xflg=0x"

    #@b6
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@b9
    move-result-object v1

    #@ba
    iget v3, p0, Landroid/content/Intent;->mExtendedFlags:I

    #@bc
    invoke-static {v3}, Ljava/lang/Integer;->toHexString(I)Ljava/lang/String;

    #@bf
    move-result-object v3

    #@c0
    invoke-virtual {v1, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@c3
    .line 12110
    :cond_c3
    iget-object v1, p0, Landroid/content/Intent;->mPackage:Ljava/lang/String;

    #@c5
    if-eqz v1, :cond_d9

    #@c7
    .line 12111
    if-nez v0, :cond_cc

    #@c9
    .line 12112
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@cc
    .line 12114
    :cond_cc
    const/4 v0, 0x0

    #@cd
    .line 12115
    const-string/jumbo v1, "pkg="

    #@d0
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@d3
    move-result-object v1

    #@d4
    iget-object v3, p0, Landroid/content/Intent;->mPackage:Ljava/lang/String;

    #@d6
    invoke-virtual {v1, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@d9
    .line 12117
    :cond_d9
    if-eqz p3, :cond_f4

    #@db
    iget-object v1, p0, Landroid/content/Intent;->mComponent:Landroid/content/ComponentName;

    #@dd
    if-eqz v1, :cond_f4

    #@df
    .line 12118
    if-nez v0, :cond_e4

    #@e1
    .line 12119
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@e4
    .line 12121
    :cond_e4
    const/4 v0, 0x0

    #@e5
    .line 12122
    const-string v1, "cmp="

    #@e7
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@ea
    move-result-object v1

    #@eb
    iget-object v3, p0, Landroid/content/Intent;->mComponent:Landroid/content/ComponentName;

    #@ed
    invoke-virtual {v3}, Landroid/content/ComponentName;->flattenToShortString()Ljava/lang/String;

    #@f0
    move-result-object v3

    #@f1
    invoke-virtual {v1, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@f4
    .line 12124
    :cond_f4
    iget-object v1, p0, Landroid/content/Intent;->mSourceBounds:Landroid/graphics/Rect;

    #@f6
    if-eqz v1, :cond_10d

    #@f8
    .line 12125
    if-nez v0, :cond_fd

    #@fa
    .line 12126
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@fd
    .line 12128
    :cond_fd
    const/4 v0, 0x0

    #@fe
    .line 12129
    const-string v1, "bnds="

    #@100
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@103
    move-result-object v1

    #@104
    iget-object v3, p0, Landroid/content/Intent;->mSourceBounds:Landroid/graphics/Rect;

    #@106
    invoke-virtual {v3}, Landroid/graphics/Rect;->toShortString()Ljava/lang/String;

    #@109
    move-result-object v3

    #@10a
    invoke-virtual {v1, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@10d
    .line 12131
    :cond_10d
    iget-object v1, p0, Landroid/content/Intent;->mClipData:Landroid/content/ClipData;

    #@10f
    if-eqz v1, :cond_12e

    #@111
    .line 12132
    if-nez v0, :cond_116

    #@113
    .line 12133
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@116
    .line 12135
    :cond_116
    const-string v1, "clip={"

    #@118
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@11b
    .line 12136
    iget-object v1, p0, Landroid/content/Intent;->mClipData:Landroid/content/ClipData;

    #@11d
    if-eqz p5, :cond_124

    #@11f
    if-eqz p2, :cond_122

    #@121
    goto :goto_124

    #@122
    :cond_122
    const/4 v3, 0x0

    #@123
    goto :goto_125

    #@124
    :cond_124
    :goto_124
    const/4 v3, 0x1

    #@125
    :goto_125
    invoke-virtual {v1, p1, v3}, Landroid/content/ClipData;->toShortString(Ljava/lang/StringBuilder;Z)V

    #@128
    .line 12137
    const/4 v0, 0x0

    #@129
    .line 12138
    const/16 v1, 0x7d

    #@12b
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@12e
    .line 12140
    :cond_12e
    if-eqz p4, :cond_13f

    #@130
    iget-object v1, p0, Landroid/content/Intent;->mExtras:Landroid/os/Bundle;

    #@132
    if-eqz v1, :cond_13f

    #@134
    .line 12141
    if-nez v0, :cond_139

    #@136
    .line 12142
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@139
    .line 12144
    :cond_139
    const/4 v0, 0x0

    #@13a
    .line 12145
    const-string v1, "(has extras)"

    #@13c
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@13f
    .line 12147
    :cond_13f
    iget v1, p0, Landroid/content/Intent;->mContentUserHint:I

    #@141
    const/4 v3, -0x2

    #@142
    if-eq v1, v3, :cond_156

    #@144
    .line 12148
    if-nez v0, :cond_149

    #@146
    .line 12149
    invoke-virtual {p1, v2}, Ljava/lang/StringBuilder;->append(C)Ljava/lang/StringBuilder;

    #@149
    .line 12151
    :cond_149
    const/4 v0, 0x0

    #@14a
    .line 12152
    const-string/jumbo v1, "u="

    #@14d
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@150
    move-result-object v1

    #@151
    iget v2, p0, Landroid/content/Intent;->mContentUserHint:I

    #@153
    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@156
    .line 12154
    :cond_156
    iget-object v1, p0, Landroid/content/Intent;->mSelector:Landroid/content/Intent;

    #@158
    const-string/jumbo v2, "}"

    #@15b
    if-eqz v1, :cond_170

    #@15d
    .line 12155
    const-string v1, " sel="

    #@15f
    invoke-virtual {p1, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@162
    .line 12156
    iget-object v3, p0, Landroid/content/Intent;->mSelector:Landroid/content/Intent;

    #@164
    move-object v4, p1

    #@165
    move v5, p2

    #@166
    move v6, p3

    #@167
    move v7, p4

    #@168
    move v8, p5

    #@169
    .end local p1    # "b":Ljava/lang/StringBuilder;
    .end local p2    # "secure":Z
    .end local p3    # "comp":Z
    .end local p4    # "extras":Z
    .end local p5    # "clip":Z
    .local v4, "b":Ljava/lang/StringBuilder;
    .local v5, "secure":Z
    .local v6, "comp":Z
    .local v7, "extras":Z
    .local v8, "clip":Z
    invoke-virtual/range {v3 .. v8}, Landroid/content/Intent;->toShortString(Ljava/lang/StringBuilder;ZZZZ)V

    #@16c
    .line 12157
    invoke-virtual {v4, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@16f
    goto :goto_175

    #@170
    .line 12154
    .end local v4    # "b":Ljava/lang/StringBuilder;
    .end local v5    # "secure":Z
    .end local v6    # "comp":Z
    .end local v7    # "extras":Z
    .end local v8    # "clip":Z
    .restart local p1    # "b":Ljava/lang/StringBuilder;
    .restart local p2    # "secure":Z
    .restart local p3    # "comp":Z
    .restart local p4    # "extras":Z
    .restart local p5    # "clip":Z
    :cond_170
    move-object v4, p1

    #@171
    move v5, p2

    #@172
    move v6, p3

    #@173
    move v7, p4

    #@174
    move v8, p5

    #@175
    .line 12159
    .end local p1    # "b":Ljava/lang/StringBuilder;
    .end local p2    # "secure":Z
    .end local p3    # "comp":Z
    .end local p4    # "extras":Z
    .end local p5    # "clip":Z
    .restart local v4    # "b":Ljava/lang/StringBuilder;
    .restart local v5    # "secure":Z
    .restart local v6    # "comp":Z
    .restart local v7    # "extras":Z
    .restart local v8    # "clip":Z
    :goto_175
    iget-object p1, p0, Landroid/content/Intent;->mOriginalIntent:Landroid/content/Intent;

    #@177
    if-eqz p1, :cond_190

    #@179
    .line 12160
    const-string p1, " org={"

    #@17b
    invoke-virtual {v4, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@17e
    .line 12161
    move v9, v8

    #@17f
    move v8, v7

    #@180
    move v7, v6

    #@181
    move v6, v5

    #@182
    move-object v5, v4

    #@183
    .end local v4    # "b":Ljava/lang/StringBuilder;
    .local v5, "b":Ljava/lang/StringBuilder;
    .local v6, "secure":Z
    .local v7, "comp":Z
    .local v8, "extras":Z
    .local v9, "clip":Z
    iget-object v4, p0, Landroid/content/Intent;->mOriginalIntent:Landroid/content/Intent;

    #@185
    invoke-virtual/range {v4 .. v9}, Landroid/content/Intent;->toShortString(Ljava/lang/StringBuilder;ZZZZ)V

    #@188
    .line 12162
    move-object v4, v5

    #@189
    move v5, v6

    #@18a
    move v6, v7

    #@18b
    move v7, v8

    #@18c
    move v8, v9

    #@18d
    .end local v9    # "clip":Z
    .restart local v4    # "b":Ljava/lang/StringBuilder;
    .local v5, "secure":Z
    .local v6, "comp":Z
    .local v7, "extras":Z
    .local v8, "clip":Z
    invoke-virtual {v4, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@190
    .line 12164
    :cond_190
    return-void
.end method
