l v0    # "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@694
    move-result-object v8

    #@695
    .line 8822
    .restart local v8    # "value":Ljava/lang/String;
    invoke-static {v8}, Landroid/content/Intent;->decodeInteger(Ljava/lang/String;)Ljava/lang/Integer;

    #@698
    move-result-object v9

    #@699
    invoke-virtual {v3, v0, v9}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/io/Serializable;)Landroid/content/Intent;

    #@69c
    .line 8824
    .end local v0    # "key":Ljava/lang/String;
    .end local v8    # "value":Ljava/lang/String;
    move-object/from16 v10, p0

    #@69e
    goto/16 :goto_714

    #@6a0
    .line 8815
    :pswitch_6a0
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@6a3
    move-result-object v0

    #@6a4
    .line 8816
    .restart local v0    # "key":Ljava/lang/String;
    move-object/from16 v10, v16

    #@6a6
    check-cast v10, Ljava/lang/String;

    #@6a8
    move-object/from16 v8, v16

    #@6aa
    invoke-virtual {v3, v0, v8}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/lang/String;)Landroid/content/Intent;

    #@6ad
    .line 8818
    .end local v0    # "key":Ljava/lang/String;
    move-object/from16 v10, p0

    #@6af
    goto/16 :goto_714

    #@6b1
    .line 8809
    :pswitch_6b1
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@6b4
    move-result-object v0

    #@6b5
    .line 8810
    .restart local v0    # "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@6b8
    move-result-object v8

    #@6b9
    .line 8811
    .restart local v8    # "value":Ljava/lang/String;
    invoke-virtual {v3, v0, v8}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/lang/String;)Landroid/content/Intent;

    #@6bc
    .line 8813
    .end local v0    # "key":Ljava/lang/String;
    .end local v8    # "value":Ljava/lang/String;
    move-object/from16 v10, p0

    #@6be
    goto/16 :goto_714

    #@6c0
    .line 8802
    :pswitch_6c0
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@6c3
    move-result-object v0

    #@6c4
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addCategory(Ljava/lang/String;)Landroid/content/Intent;

    #@6c7
    .line 8803
    if-ne v3, v2, :cond_6ce

    #@6c9
    .line 8804
    const/4 v0, 0x1

    #@6ca
    move-object/from16 v10, p0

    #@6cc
    move v4, v0

    #@6cd
    .end local v4    # "hasIntentInfo":Z
    .local v0, "hasIntentInfo":Z
    goto :goto_714

    #@6ce
    .line 8803
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :cond_6ce
    move-object/from16 v10, p0

    #@6d0
    goto :goto_714

    #@6d1
    .line 8796
    :pswitch_6d1
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@6d4
    move-result-object v0

    #@6d5
    invoke-virtual {v3, v0}, Landroid/content/Intent;->setIdentifier(Ljava/lang/String;)Landroid/content/Intent;

    #@6d8
    .line 8797
    if-ne v3, v2, :cond_6df

    #@6da
    .line 8798
    const/4 v0, 0x1

    #@6db
    move-object/from16 v10, p0

    #@6dd
    move v4, v0

    #@6de
    .end local v4    # "hasIntentInfo":Z
    .restart local v0    # "hasIntentInfo":Z
    goto :goto_714

    #@6df
    .line 8797
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :cond_6df
    move-object/from16 v10, p0

    #@6e1
    goto :goto_714

    #@6e2
    .line 8790
    :pswitch_6e2
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@6e5
    move-result-object v0

    #@6e6
    .line 8791
    .end local v6    # "type":Ljava/lang/String;
    .local v0, "type":Ljava/lang/String;
    if-ne v3, v2, :cond_6ed

    #@6e8
    .line 8792
    const/4 v4, 0x1

    #@6e9
    move-object/from16 v10, p0

    #@6eb
    move-object v6, v0

    #@6ec
    goto :goto_714

    #@6ed
    .line 8791
    :cond_6ed
    move-object/from16 v10, p0

    #@6ef
    move-object v6, v0

    #@6f0
    goto :goto_714

    #@6f1
    .line 8784
    .end local v0    # "type":Ljava/lang/String;
    .restart local v6    # "type":Ljava/lang/String;
    :pswitch_6f1
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@6f4
    move-result-object v0

    #@6f5
    invoke-static {v0}, Landroid/net/Uri;->parse(Ljava/lang/String;)Landroid/net/Uri;

    #@6f8
    move-result-object v0

    #@6f9
    .line 8785
    .end local v5    # "data":Landroid/net/Uri;
    .local v0, "data":Landroid/net/Uri;
    if-ne v3, v2, :cond_700

    #@6fb
    .line 8786
    const/4 v4, 0x1

    #@6fc
    move-object/from16 v10, p0

    #@6fe
    move-object v5, v0

    #@6ff
    goto :goto_714

    #@700
    .line 8785
    :cond_700
    move-object/from16 v10, p0

    #@702
    move-object v5, v0

    #@703
    goto :goto_714

    #@704
    .line 8778
    .end local v0    # "data":Landroid/net/Uri;
    .restart local v5    # "data":Landroid/net/Uri;
    :pswitch_704
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@707
    move-result-object v0

    #@708
    invoke-virtual {v3, v0}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    #@70b
    .line 8779
    if-ne v3, v2, :cond_712

    #@70d
    .line 8780
    const/4 v0, 0x1

    #@70e
    move-object/from16 v10, p0

    #@710
    move v4, v0

    #@711
    .end local v4    # "hasIntentInfo":Z
    .local v0, "hasIntentInfo":Z
    goto :goto_714

    #@712
    .line 8779
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :cond_712
    move-object/from16 v10, p0

    #@714
    .line 9119
    :goto_714
    goto/16 :goto_f

    #@716
    .line 9113
    :cond_716
    move-object/from16 v10, p0

    #@718
    .line 9116
    :cond_718
    new-instance v0, Ljava/lang/IllegalArgumentException;

    #@71a
    new-instance v8, Ljava/lang/StringBuilder;

    #@71c
    invoke-direct {v8}, Ljava/lang/StringBuilder;-><init>()V

    #@71f
    const-string v9, "Unknown option: "

    #@721
    invoke-virtual {v8, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@724
    move-result-object v8

    #@725
    invoke-virtual {v8, v7}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@728
    move-result-object v8

    #@729
    invoke-virtual {v8}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@72c
    move-result-object v8

    #@72d
    invoke-direct {v0, v8}, Ljava/lang/IllegalArgumentException;-><init>(Ljava/lang/String;)V

    #@730
    throw v0

    #@731
    .line 9121
    :cond_731
    const/4 v0, 0x1

    #@732
    move-object/from16 v10, p0

    #@734
    invoke-virtual {v3, v5, v6}, Landroid/content/Intent;->setDataAndType(Landroid/net/Uri;Ljava/lang/String;)Landroid/content/Intent;

    #@737
    .line 9123
    if-eq v3, v2, :cond_73b

    #@739
    move v11, v0

    #@73a
    goto :goto_73c

    #@73b
    :cond_73b
    const/4 v11, 0x0

    #@73c
    .line 9124
    .local v11, "hasSelector":Z
    :goto_73c
    if-eqz v11, :cond_742

    #@73e
    .line 9126
    invoke-virtual {v2, v3}, Landroid/content/Intent;->setSelector(Landroid/content/Intent;)V

    #@741
    .line 9127
    move-object v3, v2

    #@742
    .line 9130
    :cond_742
    invoke-virtual {v10}, Landroid/os/ShellCommand;->getNextArg()Ljava/lang/String;

    #@745
    move-result-object v0

    #@746
    .line 9131
    .local v0, "arg":Ljava/lang/String;
    const/4 v2, 0x0

    #@747
    .line 9132
    const-string v12, "android.intent.category.LAUNCHER"

    #@749
    const-string v13, "android.intent.action.MAIN"

    #@74b
    if-nez v0, :cond_759

    #@74d
    .line 9133
    if-eqz v11, :cond_789

    #@74f
    .line 9139
    new-instance v8, Landroid/content/Intent;

    #@751
    invoke-direct {v8, v13}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    #@754
    move-object v2, v8

    #@755
    .line 9140
    invoke-virtual {v2, v12}, Landroid/content/Intent;->addCategory(Ljava/lang/String;)Landroid/content/Intent;

    #@758
    goto :goto_789

    #@759
    .line 9142
    :cond_759
    const/16 v14, 0x3a

    #@75b
    invoke-virtual {v0, v14}, Ljava/lang/String;->indexOf(I)I

    #@75e
    move-result v14

    #@75f
    if-ltz v14, :cond_766

    #@761
    .line 9145
    invoke-static {v0, v9}, Landroid/content/Intent;->parseUri(Ljava/lang/String;I)Landroid/content/Intent;

    #@764
    move-result-object v2

    #@765
    goto :goto_789

    #@766
    .line 9147
    :cond_766
    invoke-virtual {v0, v8}, Ljava/lang/String;->indexOf(I)I

    #@769
    move-result v8

    #@76a
    if-ltz v8, :cond_77d

    #@76c
    .line 9150
    new-instance v8, Landroid/content/Intent;

    #@76e
    invoke-direct {v8, v13}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    #@771
    move-object v2, v8

    #@772
    .line 9151
    invoke-virtual {v2, v12}, Landroid/content/Intent;->addCategory(Ljava/lang/String;)Landroid/content/Intent;

    #@775
    .line 9152
    invoke-static {v0}, Landroid/content/ComponentName;->unflattenFromString(Ljava/lang/String;)Landroid/content/ComponentName;

    #@778
    move-result-object v8

    #@779
    invoke-virtual {v2, v8}, Landroid/content/Intent;->setComponent(Landroid/content/ComponentName;)Landroid/content/Intent;

    #@77c
    goto :goto_789

    #@77d
    .line 9155
    :cond_77d
    new-instance v8, Landroid/content/Intent;

    #@77f
    invoke-direct {v8, v13}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    #@782
    move-object v2, v8

    #@783
    .line 9156
    invoke-virtual {v2, v12}, Landroid/content/Intent;->addCategory(Ljava/lang/String;)Landroid/content/Intent;

    #@786
    .line 9157
    invoke-virtual {v2, v0}, Landroid/content/Intent;->setPackage(Ljava/lang/String;)Landroid/content/Intent;

    #@789
    .line 9159
    :cond_789
    :goto_789
    if-eqz v2, :cond_7d9

    #@78b
    .line 9160
    invoke-virtual {v3}, Landroid/content/Intent;->getExtras()Landroid/os/Bundle;

    #@78e
    move-result-object v8

    #@78f
    .line 9161
    .local v8, "extras":Landroid/os/Bundle;
    const/4 v9, 0x0

    #@790
    move-object v12, v9

    #@791
    check-cast v12, Landroid/os/Bundle;

    #@793
    invoke-virtual {v3, v9}, Landroid/content/Intent;->replaceExtras(Landroid/os/Bundle;)Landroid/content/Intent;

    #@796
    .line 9162
    invoke-virtual {v2}, Landroid/content/Intent;->getExtras()Landroid/os/Bundle;

    #@799
    move-result-object v12

    #@79a
    .line 9163
    .local v12, "uriExtras":Landroid/os/Bundle;
    invoke-virtual {v2, v9}, Landroid/content/Intent;->replaceExtras(Landroid/os/Bundle;)Landroid/content/Intent;

    #@79d
    .line 9164
    invoke-virtual {v3}, Landroid/content/Intent;->getAction()Ljava/lang/String;

    #@7a0
    move-result-object v9

    #@7a1
    if-eqz v9, :cond_7c6

    #@7a3
    invoke-virtual {v2}, Landroid/content/Intent;->getCategories()Ljava/util/Set;

    #@7a6
    move-result-object v9

    #@7a7
    if-eqz v9, :cond_7c6

    #@7a9
    .line 9165
    new-instance v9, Ljava/util/HashSet;

    #@7ab
    invoke-virtual {v2}, Landroid/content/Intent;->getCategories()Ljava/util/Set;

    #@7ae
    move-result-object v13

    #@7af
    invoke-direct {v9, v13}, Ljava/util/HashSet;-><init>(Ljava/util/Collection;)V

    #@7b2
    .line 9166
    .local v9, "cats":Ljava/util/HashSet;, "Ljava/util/HashSet<Ljava/lang/String;>;"
    invoke-virtual {v9}, Ljava/util/HashSet;->iterator()Ljava/util/Iterator;

    #@7b5
    move-result-object v13

    #@7b6
    :goto_7b6
    invoke-interface {v13}, Ljava/util/Iterator;->hasNext()Z

    #@7b9
    move-result v14

    #@7ba
    if-eqz v14, :cond_7c6

    #@7bc
    invoke-interface {v13}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    #@7bf
    move-result-object v14

    #@7c0
    check-cast v14, Ljava/lang/String;

    #@7c2
    .line 9167
    .local v14, "c":Ljava/lang/String;
    invoke-virtual {v2, v14}, Landroid/content/Intent;->removeCategory(Ljava/lang/String;)V

    #@7c5
    .line 9168
    .end local v14    # "c":Ljava/lang/String;
    goto :goto_7b6

    #@7c6
    .line 9170
    .end local v9    # "cats":Ljava/util/HashSet;, "Ljava/util/HashSet<Ljava/lang/String;>;"
    :cond_7c6
    const/16 v9, 0x48

    #@7c8
    invoke-virtual {v3, v2, v9}, Landroid/content/Intent;->fillIn(Landroid/content/Intent;I)I

    #@7cb
    .line 9171
    if-nez v8, :cond_7cf

    #@7cd
    .line 9172
    move-object v8, v12

    #@7ce
    goto :goto_7d5

    #@7cf
    .line 9173
    :cond_7cf
    if-eqz v12, :cond_7d5

    #@7d1
    .line 9174
    invoke-virtual {v12, v8}, Landroid/os/Bundle;->putAll(Landroid/os/Bundle;)V

    #@7d4
    .line 9175
    move-object v8, v12

    #@7d5
    .line 9177
    :cond_7d5
    :goto_7d5
    invoke-virtual {v3, v8}, Landroid/content/Intent;->replaceExtras(Landroid/os/Bundle;)Landroid/content/Intent;

    #@7d8
    .line 9178
    const/4 v4, 0x1

    #@7d9
    .line 9181
    .end local v8    # "extras":Landroid/os/Bundle;
    .end local v12    # "uriExtras":Landroid/os/Bundle;
    :cond_7d9
    if-eqz v4, :cond_7dc

    #@7db
    .line 9182
    return-object v3

    #@7dc
    .line 9181
    :cond_7dc
    new-instance v8, Ljava/lang/IllegalArgumentException;

    #@7de
    const-string v9, "No intent supplied"

    #@7e0
    invoke-direct {v8, v9}, Ljava/lang/IllegalArgumentException;-><init>(Ljava/lang/String;)V

    #@7e3
    throw v8

    #@7e4
    :sswitch_data_7e4
    .sparse-switch
        -0x7ffea226 -> :sswitch_2b1
        -0x7e40bfdd -> :sswitch_2a6
        -0x61305b9a -> :sswitch_29b
        -0x4aae571d -> :sswitch_290
        -0x3fbe74d1 -> :sswitch_285
        -0x328eb9b9 -> :sswitch_27a
        -0x31a9343b -> :sswitch_26f
        -0x2f378b56 -> :sswitch_264
        -0x2e804d8f -> :sswitch_259
        0x5d4 -> :sswitch_24e
        0x5d6 -> :sswitch_243
        0x5d7 -> :sswitch_238
        0x5d8 -> :sswitch_22d
        0x5d9 -> :sswitch_221
        0x5dc -> :sswitch_216
        0x5e1 -> :sswitch_20a
        0x5e3 -> :sswitch_1fe
        0x5e7 -> :sswitch_1f3
        0x152a3f -> :sswitch_1e7
        0x152a41 -> :sswitch_1db
        0x152a44 -> :sswitch_1d0
        0x152a47 -> :sswitch_1c4
        0x152a4e -> :sswitch_1b9
        0x152a50 -> :sswitch_1ad
        0x152a55 -> :sswitch_1a1
        0x2901df0 -> :sswitch_195
        0x2901e02 -> :sswitch_189
        0x2901e40 -> :sswitch_17d
        0x2901e9d -> :sswitch_171
        0x2901efa -> :sswitch_165
        0x2901fd3 -> :sswitch_159
        0x2901fe0 -> :sswitch_14e
        0x41eb1c6 -> :sswitch_142
        0x54a2ed6 -> :sswitch_136
        0xb611ab9 -> :sswitch_12a
        0xe1b6a37 -> :sswitch_11e
        0x1998b94a -> :sswitch_112
        0x1a0135d9 -> :sswitch_106
        0x1a23762e -> :sswitch_fc
        0x1f699c40 -> :sswitch_f0
        0x22987a20 -> :sswitch_e4
        0x2caeb912 -> :sswitch_d8
        0x2e337d40 -> :sswitch_cc
        0x422c3bb1 -> :sswitch_c0
        0x47f6597f -> :sswitch_b4
        0x4f73a2aa -> :sswitch_a8
        0x4f73aa2c -> :sswitch_9c
        0x4f73b56f -> :sswitch_90
        0x4f73c0b2 -> :sswitch_84
        0x4f73daf9 -> :sswitch_78
        0x50b32d5c -> :sswitch_6c
        0x5359f12e -> :sswitch_60
        0x569e74a2 -> :sswitch_54
        0x62838641 -> :sswitch_48
        0x67da9e16 -> :sswitch_3c
        0x69396684 -> :sswitch_30
        0x6c467a2f -> :sswitch_24
    .end sparse-switch

    #@8ca
    :pswitch_data_8ca
    .packed-switch 0x0
        :pswitch_704
        :pswitch_6f1
        :pswitch_6e2
        :pswitch_6d1
        :pswitch_6c0
        :pswitch_6b1
        :pswitch_6b1
        :pswitch_6a0
        :pswitch_68d
        :pswitch_67a
        :pswitch_64e
        :pswitch_625
        :pswitch_5fc
        :pswitch_5e9
        :pswitch_5be
        :pswitch_593
        :pswitch_57e
        :pswitch_553
        :pswitch_528
        :pswitch_513
        :pswitch_4e8
        :pswitch_4bd
        :pswitch_4a8
        :pswitch_481
        :pswitch_41e
        :pswitch_3f3
        :pswitch_3e5
        :pswitch_3d2
        :pswitch_3ca
        :pswitch_3c2
        :pswitch_3b9
        :pswitch_3b0
        :pswitch_3a7
        :pswitch_39e
        :pswitch_397
        :pswitch_38e
        :pswitch_385
        :pswitch_37c
        :pswitch_373
        :pswitch_36a
        :pswitch_363
        :pswitch_35a
        :pswitch_353
        :pswitch_34a
        :pswitch_343
        :pswitch_33a
        :pswitch_331
        :pswitch_32a
        :pswitch_320
        :pswitch_317
        :pswitch_30e
        :pswitch_307
        :pswitch_300
        :pswitch_2f7
        :pswitch_2f0
        :pswitch_2e9
        :pswitch_2dc
    .end packed-switch
.end method
