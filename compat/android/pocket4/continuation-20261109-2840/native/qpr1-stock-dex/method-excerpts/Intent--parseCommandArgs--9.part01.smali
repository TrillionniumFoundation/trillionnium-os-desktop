.method public static greylist-max-r parseCommandArgs(Landroid/os/ShellCommand;Landroid/content/Intent$CommandOptionHandler;)Landroid/content/Intent;
    .registers 19
    .param p0, "cmd"    # Landroid/os/ShellCommand;
    .param p1, "optionHandler"    # Landroid/content/Intent$CommandOptionHandler;
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Ljava/net/URISyntaxException;
        }
    .end annotation

    #@0
    .line 8767
    move-object/from16 v1, p1

    #@2
    new-instance v0, Landroid/content/Intent;

    #@4
    invoke-direct {v0}, Landroid/content/Intent;-><init>()V

    #@7
    .line 8768
    .local v0, "intent":Landroid/content/Intent;
    move-object v2, v0

    #@8
    .line 8769
    .local v2, "baseIntent":Landroid/content/Intent;
    const/4 v3, 0x0

    #@9
    .line 8771
    .local v3, "hasIntentInfo":Z
    const/4 v4, 0x0

    #@a
    .line 8772
    .local v4, "data":Landroid/net/Uri;
    const/4 v5, 0x0

    #@b
    move-object v6, v5

    #@c
    move-object v5, v4

    #@d
    move v4, v3

    #@e
    move-object v3, v0

    #@f
    .line 8775
    .end local v0    # "intent":Landroid/content/Intent;
    .local v3, "intent":Landroid/content/Intent;
    .local v4, "hasIntentInfo":Z
    .local v5, "data":Landroid/net/Uri;
    .local v6, "type":Ljava/lang/String;
    :goto_f
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextOption()Ljava/lang/String;

    #@12
    move-result-object v0

    #@13
    move-object v7, v0

    #@14
    .local v7, "opt":Ljava/lang/String;
    const/16 v8, 0x2f

    #@16
    const/4 v9, 0x7

    #@17
    if-eqz v0, :cond_731

    #@19
    .line 8776
    invoke-virtual {v7}, Ljava/lang/Object;->hashCode()I

    #@1c
    move-result v0

    #@1d
    const/16 v13, 0x8

    #@1f
    sparse-switch v0, :sswitch_data_7e4

    #@22
    :cond_22
    goto/16 :goto_2bc

    #@24
    :sswitch_24
    const-string v0, "--grant-write-uri-permission"

    #@26
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@29
    move-result v0

    #@2a
    if-eqz v0, :cond_22

    #@2c
    const/16 v8, 0x1d

    #@2e
    goto/16 :goto_2bd

    #@30
    :sswitch_30
    const-string v0, "--activity-multiple-task"

    #@32
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@35
    move-result v0

    #@36
    if-eqz v0, :cond_22

    #@38
    const/16 v8, 0x28

    #@3a
    goto/16 :goto_2bd

    #@3c
    :sswitch_3c
    const-string v0, "--grant-read-uri-permission"

    #@3e
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@41
    move-result v0

    #@42
    if-eqz v0, :cond_22

    #@44
    const/16 v8, 0x1c

    #@46
    goto/16 :goto_2bd

    #@48
    :sswitch_48
    const-string v0, "--receiver-foreground"

    #@4a
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@4d
    move-result v0

    #@4e
    if-eqz v0, :cond_22

    #@50
    const/16 v8, 0x35

    #@52
    goto/16 :goto_2bd

    #@54
    :sswitch_54
    const-string v0, "--receiver-no-abort"

    #@56
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@59
    move-result v0

    #@5a
    if-eqz v0, :cond_22

    #@5c
    const/16 v8, 0x36

    #@5e
    goto/16 :goto_2bd

    #@60
    :sswitch_60
    const-string v0, "--activity-launched-from-history"

    #@62
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@65
    move-result v0

    #@66
    if-eqz v0, :cond_22

    #@68
    const/16 v8, 0x27

    #@6a
    goto/16 :goto_2bd

    #@6c
    :sswitch_6c
    const-string v0, "--activity-clear-when-task-reset"

    #@6e
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@71
    move-result v0

    #@72
    if-eqz v0, :cond_22

    #@74
    const/16 v8, 0x25

    #@76
    goto/16 :goto_2bd

    #@78
    :sswitch_78
    const-string v0, "--esal"

    #@7a
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@7d
    move-result v0

    #@7e
    if-eqz v0, :cond_22

    #@80
    const/16 v8, 0x17

    #@82
    goto/16 :goto_2bd

    #@84
    :sswitch_84
    const-string v0, "--elal"

    #@86
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@89
    move-result v0

    #@8a
    if-eqz v0, :cond_22

    #@8c
    const/16 v8, 0xf

    #@8e
    goto/16 :goto_2bd

    #@90
    :sswitch_90
    const-string v0, "--eial"

    #@92
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@95
    move-result v0

    #@96
    if-eqz v0, :cond_22

    #@98
    const/16 v8, 0xc

    #@9a
    goto/16 :goto_2bd

    #@9c
    :sswitch_9c
    const-string v0, "--efal"

    #@9e
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@a1
    move-result v0

    #@a2
    if-eqz v0, :cond_22

    #@a4
    const/16 v8, 0x12

    #@a6
    goto/16 :goto_2bd

    #@a8
    :sswitch_a8
    const-string v0, "--edal"

    #@aa
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@ad
    move-result v0

    #@ae
    if-eqz v0, :cond_22

    #@b0
    const/16 v8, 0x15

    #@b2
    goto/16 :goto_2bd

    #@b4
    :sswitch_b4
    const-string v0, "--selector"

    #@b6
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@b9
    move-result v0

    #@ba
    if-eqz v0, :cond_22

    #@bc
    const/16 v8, 0x38

    #@be
    goto/16 :goto_2bd

    #@c0
    :sswitch_c0
    const-string v0, "--activity-match-external"

    #@c2
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@c5
    move-result v0

    #@c6
    if-eqz v0, :cond_22

    #@c8
    const/16 v8, 0x32

    #@ca
    goto/16 :goto_2bd

    #@cc
    :sswitch_cc
    const-string v0, "--receiver-replace-pending"

    #@ce
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@d1
    move-result v0

    #@d2
    if-eqz v0, :cond_22

    #@d4
    const/16 v8, 0x34

    #@d6
    goto/16 :goto_2bd

    #@d8
    :sswitch_d8
    const-string v0, "--include-stopped-packages"

    #@da
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@dd
    move-result v0

    #@de
    if-eqz v0, :cond_22

    #@e0
    const/16 v8, 0x21

    #@e2
    goto/16 :goto_2bd

    #@e4
    :sswitch_e4
    const-string v0, "--exclude-stopped-packages"

    #@e6
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@e9
    move-result v0

    #@ea
    if-eqz v0, :cond_22

    #@ec
    const/16 v8, 0x20

    #@ee
    goto/16 :goto_2bd

    #@f0
    :sswitch_f0
    const-string v0, "--grant-persistable-uri-permission"

    #@f2
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@f5
    move-result v0

    #@f6
    if-eqz v0, :cond_22

    #@f8
    const/16 v8, 0x1e

    #@fa
    goto/16 :goto_2bd

    #@fc
    :sswitch_fc
    const-string v0, "--activity-single-top"

    #@fe
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@101
    move-result v0

    #@102
    if-eqz v0, :cond_22

    #@104
    goto/16 :goto_2bd

    #@106
    :sswitch_106
    const-string v0, "--receiver-registered-only"

    #@108
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@10b
    move-result v0

    #@10c
    if-eqz v0, :cond_22

    #@10e
    const/16 v8, 0x33

    #@110
    goto/16 :goto_2bd

    #@112
    :sswitch_112
    const-string v0, "--activity-no-user-action"

    #@114
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@117
    move-result v0

    #@118
    if-eqz v0, :cond_22

    #@11a
    const/16 v8, 0x2b

    #@11c
    goto/16 :goto_2bd

    #@11e
    :sswitch_11e
    const-string v0, "--activity-clear-top"

    #@120
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@123
    move-result v0

    #@124
    if-eqz v0, :cond_22

    #@126
    const/16 v8, 0x24

    #@128
    goto/16 :goto_2bd

    #@12a
    :sswitch_12a
    const-string v0, "--activity-reset-task-if-needed"

    #@12c
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@12f
    move-result v0

    #@130
    if-eqz v0, :cond_22

    #@132
    const/16 v8, 0x2e

    #@134
    goto/16 :goto_2bd

    #@136
    :sswitch_136
    const-string v0, "--activity-no-animation"

    #@138
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@13b
    move-result v0

    #@13c
    if-eqz v0, :cond_22

    #@13e
    const/16 v8, 0x29

    #@140
    goto/16 :goto_2bd

    #@142
    :sswitch_142
    const-string v0, "--activity-exclude-from-recents"

    #@144
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@147
    move-result v0

    #@148
    if-eqz v0, :cond_22

    #@14a
    const/16 v8, 0x26

    #@14c
    goto/16 :goto_2bd

    #@14e
    :sswitch_14e
    const-string v0, "--esn"

    #@150
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@153
    move-result v0

    #@154
    if-eqz v0, :cond_22

    #@156
    move v8, v9

    #@157
    goto/16 :goto_2bd

    #@159
    :sswitch_159
    const-string v0, "--esa"

    #@15b
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@15e
    move-result v0

    #@15f
    if-eqz v0, :cond_22

    #@161
    const/16 v8, 0x16

    #@163
    goto/16 :goto_2bd

    #@165
    :sswitch_165
    const-string v0, "--ela"

    #@167
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@16a
    move-result v0

    #@16b
    if-eqz v0, :cond_22

    #@16d
    const/16 v8, 0xe

    #@16f
    goto/16 :goto_2bd

    #@171
    :sswitch_171
    const-string v0, "--eia"

    #@173
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@176
    move-result v0

    #@177
    if-eqz v0, :cond_22

    #@179
    const/16 v8, 0xb

    #@17b
    goto/16 :goto_2bd

    #@17d
    :sswitch_17d
    const-string v0, "--efa"

    #@17f
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@182
    move-result v0

    #@183
    if-eqz v0, :cond_22

    #@185
    const/16 v8, 0x11

    #@187
    goto/16 :goto_2bd

    #@189
    :sswitch_189
    const-string v0, "--eda"

    #@18b
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@18e
    move-result v0

    #@18f
    if-eqz v0, :cond_22

    #@191
    const/16 v8, 0x14

    #@193
    goto/16 :goto_2bd

    #@195
    :sswitch_195
    const-string v0, "--ecn"

    #@197
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@19a
    move-result v0

    #@19b
    if-eqz v0, :cond_22

    #@19d
    const/16 v8, 0xa

    #@19f
    goto/16 :goto_2bd

    #@1a1
    :sswitch_1a1
    const-string v0, "--ez"

    #@1a3
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@1a6
    move-result v0

    #@1a7
    if-eqz v0, :cond_22

    #@1a9
    const/16 v8, 0x18

    #@1ab
    goto/16 :goto_2bd

    #@1ad
    :sswitch_1ad
    const-string v0, "--eu"

    #@1af
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@1b2
    move-result v0

    #@1b3
    if-eqz v0, :cond_22

    #@1b5
    const/16 v8, 0x9

    #@1b7
    goto/16 :goto_2bd

    #@1b9
    :sswitch_1b9
    const-string v0, "--es"

    #@1bb
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@1be
    move-result v0

    #@1bf
    if-eqz v0, :cond_22

    #@1c1
    const/4 v8, 0x6

    #@1c2
    goto/16 :goto_2bd

    #@1c4
    :sswitch_1c4
    const-string v0, "--el"

    #@1c6
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@1c9
    move-result v0

    #@1ca
    if-eqz v0, :cond_22

    #@1cc
    const/16 v8, 0xd

    #@1ce
    goto/16 :goto_2bd

    #@1d0
    :sswitch_1d0
    const-string v0, "--ei"

    #@1d2
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@1d5
    move-result v0

    #@1d6
    if-eqz v0, :cond_22

    #@1d8
    move v8, v13

    #@1d9
    goto/16 :goto_2bd

    #@1db
    :sswitch_1db
    const-string v0, "--ef"

    #@1dd
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@1e0
    move-result v0

    #@1e1
    if-eqz v0, :cond_22

    #@1e3
    const/16 v8, 0x10

    #@1e5
    goto/16 :goto_2bd

    #@1e7
    :sswitch_1e7
    const-string v0, "--ed"

    #@1e9
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@1ec
    move-result v0

    #@1ed
    if-eqz v0, :cond_22

    #@1ef
    const/16 v8, 0x13

    #@1f1
    goto/16 :goto_2bd

    #@1f3
    :sswitch_1f3
    const-string v0, "-t"

    #@1f5
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@1f8
    move-result v0

    #@1f9
    if-eqz v0, :cond_22

    #@1fb
    const/4 v8, 0x2

    #@1fc
    goto/16 :goto_2bd

    #@1fe
    :sswitch_1fe
    const-string v0, "-p"

    #@200
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@203
    move-result v0

    #@204
    if-eqz v0, :cond_22

    #@206
    const/16 v8, 0x1a

    #@208
    goto/16 :goto_2bd

    #@20a
    :sswitch_20a
    const-string v0, "-n"

    #@20c
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@20f
    move-result v0

    #@210
    if-eqz v0, :cond_22

    #@212
    const/16 v8, 0x19

    #@214
    goto/16 :goto_2bd

    #@216
    :sswitch_216
    const-string v0, "-i"

    #@218
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@21b
    move-result v0

    #@21c
    if-eqz v0, :cond_22

    #@21e
    const/4 v8, 0x3

    #@21f
    goto/16 :goto_2bd

    #@221
    :sswitch_221
    const-string v0, "-f"

    #@223
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@226
    move-result v0

    #@227
    if-eqz v0, :cond_22

    #@229
    const/16 v8, 0x1b

    #@22b
    goto/16 :goto_2bd

    #@22d
    :sswitch_22d
    const-string v0, "-e"

    #@22f
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@232
    move-result v0

    #@233
    if-eqz v0, :cond_22

    #@235
    const/4 v8, 0x5

    #@236
    goto/16 :goto_2bd

    #@238
    :sswitch_238
    const-string v0, "-d"

    #@23a
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@23d
    move-result v0

    #@23e
    if-eqz v0, :cond_22

    #@240
    const/4 v8, 0x1

    #@241
    goto/16 :goto_2bd

    #@243
    :sswitch_243
    const-string v0, "-c"

    #@245
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@248
    move-result v0

    #@249
    if-eqz v0, :cond_22

    #@24b
    const/4 v8, 0x4

    #@24c
    goto/16 :goto_2bd

    #@24e
    :sswitch_24e
    const-string v0, "-a"

    #@250
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@253
    move-result v0

    #@254
    if-eqz v0, :cond_22

    #@256
    const/4 v8, 0x0

    #@257
    goto/16 :goto_2bd

    #@259
    :sswitch_259
    const-string v0, "--receiver-include-background"

    #@25b
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@25e
    move-result v0

    #@25f
    if-eqz v0, :cond_22

    #@261
    const/16 v8, 0x37

    #@263
    goto :goto_2bd

    #@264
    :sswitch_264
    const-string v0, "--activity-previous-is-top"

    #@266
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@269
    move-result v0

    #@26a
    if-eqz v0, :cond_22

    #@26c
    const/16 v8, 0x2c

    #@26e
    goto :goto_2bd

    #@26f
    :sswitch_26f
    const-string v0, "--activity-brought-to-front"

    #@271
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@274
    move-result v0

    #@275
    if-eqz v0, :cond_22

    #@277
    const/16 v8, 0x23

    #@279
    goto :goto_2bd

    #@27a
    :sswitch_27a
    const-string v0, "--activity-reorder-to-front"

    #@27c
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@27f
    move-result v0

    #@280
    if-eqz v0, :cond_22

    #@282
    const/16 v8, 0x2d

    #@284
    goto :goto_2bd

    #@285
    :sswitch_285
    const-string v0, "--debug-log-resolution"

    #@287
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@28a
    move-result v0

    #@28b
    if-eqz v0, :cond_22

    #@28d
    const/16 v8, 0x22

    #@28f
    goto :goto_2bd

    #@290
    :sswitch_290
    const-string v0, "--activity-clear-task"

    #@292
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@295
    move-result v0

    #@296
    if-eqz v0, :cond_22

    #@298
    const/16 v8, 0x30

    #@29a
    goto :goto_2bd

    #@29b
    :sswitch_29b
    const-string v0, "--activity-no-history"

    #@29d
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@2a0
    move-result v0

    #@2a1
    if-eqz v0, :cond_22

    #@2a3
    const/16 v8, 0x2a

    #@2a5
    goto :goto_2bd

    #@2a6
    :sswitch_2a6
    const-string v0, "--activity-task-on-home"

    #@2a8
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@2ab
    move-result v0

    #@2ac
    if-eqz v0, :cond_22

    #@2ae
    const/16 v8, 0x31

    #@2b0
    goto :goto_2bd

    #@2b1
    :sswitch_2b1
    const-string v0, "--grant-prefix-uri-permission"

    #@2b3
    invoke-virtual {v7, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@2b6
    move-result v0

    #@2b7
    if-eqz v0, :cond_22

    #@2b9
    const/16 v8, 0x1f

    #@2bb
    goto :goto_2bd

    #@2bc
    :goto_2bc
    const/4 v8, -0x1

    #@2bd
    :goto_2bd
    const-string v0, "Bad component name: "

    #@2bf
    const/high16 v9, 0x20000000

    #@2c1
    const/16 v16, 0x0

    #@2c3
    const/high16 v10, 0x1000000

    #@2c5
    const/high16 v12, 0x40000000    # 2.0f

    #@2c7
    const/high16 v11, 0x8000000

    #@2c9
    const-string v15, "(?<!\\\\),"

    #@2cb
    const-string v14, ","

    #@2cd
    packed-switch v8, :pswitch_data_8ca

    #@2d0
    .line 9113
    if-eqz v1, :cond_716

    #@2d2
    move-object/from16 v10, p0

    #@2d4
    invoke-interface {v1, v7, v10}, Landroid/content/Intent$CommandOptionHandler;->handleOption(Ljava/lang/String;Landroid/os/ShellCommand;)Z

    #@2d7
    move-result v0

    #@2d8
    if-eqz v0, :cond_718

    #@2da
    goto/16 :goto_714

    #@2dc
    .line 9109
    :pswitch_2dc
    invoke-virtual {v3, v5, v6}, Landroid/content/Intent;->setDataAndType(Landroid/net/Uri;Ljava/lang/String;)Landroid/content/Intent;

    #@2df
    .line 9110
    new-instance v0, Landroid/content/Intent;

    #@2e1
    invoke-direct {v0}, Landroid/content/Intent;-><init>()V

    #@2e4
    .line 9111
    .end local v3    # "intent":Landroid/content/Intent;
    .restart local v0    # "intent":Landroid/content/Intent;
    move-object/from16 v10, p0

    #@2e6
    move-object v3, v0

    #@2e7
    goto/16 :goto_714

    #@2e9
    .line 9106
    .end local v0    # "intent":Landroid/content/Intent;
    .restart local v3    # "intent":Landroid/content/Intent;
    :pswitch_2e9
    invoke-virtual {v3, v10}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@2ec
    .line 9107
    move-object/from16 v10, p0

    #@2ee
    goto/16 :goto_714

    #@2f0
    .line 9103
    :pswitch_2f0
    invoke-virtual {v3, v11}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@2f3
    .line 9104
    move-object/from16 v10, p0

    #@2f5
    goto/16 :goto_714

    #@2f7
    .line 9100
    :pswitch_2f7
    const/high16 v0, 0x10000000

    #@2f9
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@2fc
    .line 9101
    move-object/from16 v10, p0

    #@2fe
    goto/16 :goto_714

    #@300
    .line 9097
    :pswitch_300
    invoke-virtual {v3, v9}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@303
    .line 9098
    move-object/from16 v10, p0

    #@305
    goto/16 :goto_714

    #@307
    .line 9094
    :pswitch_307
    invoke-virtual {v3, v12}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@30a
    .line 9095
    move-object/from16 v10, p0

    #@30c
    goto/16 :goto_714

    #@30e
    .line 9091
    :pswitch_30e
    const/16 v0, 0x800

    #@310
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@313
    .line 9092
    move-object/from16 v10, p0

    #@315
    goto/16 :goto_714

    #@317
    .line 9088
    :pswitch_317
    const/16 v0, 0x4000

    #@319
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@31c
    .line 9089
    move-object/from16 v10, p0

    #@31e
    goto/16 :goto_714

    #@320
    .line 9085
    :pswitch_320
    const v0, 0x8000

    #@323
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@326
    .line 9086
    move-object/from16 v10, p0

    #@328
    goto/16 :goto_714

    #@32a
    .line 9082
    :pswitch_32a
    invoke-virtual {v3, v9}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@32d
    .line 9083
    move-object/from16 v10, p0

    #@32f
    goto/16 :goto_714

    #@331
    .line 9079
    :pswitch_331
    const/high16 v0, 0x200000

    #@333
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@336
    .line 9080
    move-object/from16 v10, p0

    #@338
    goto/16 :goto_714

    #@33a
    .line 9076
    :pswitch_33a
    const/high16 v0, 0x20000

    #@33c
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@33f
    .line 9077
    move-object/from16 v10, p0

    #@341
    goto/16 :goto_714

    #@343
    .line 9073
    :pswitch_343
    invoke-virtual {v3, v10}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@346
    .line 9074
    move-object/from16 v10, p0

    #@348
    goto/16 :goto_714

    #@34a
    .line 9070
    :pswitch_34a
    const/high16 v0, 0x40000

    #@34c
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@34f
    .line 9071
    move-object/from16 v10, p0

    #@351
    goto/16 :goto_714

    #@353
    .line 9067
    :pswitch_353
    invoke-virtual {v3, v12}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@356
    .line 9068
    move-object/from16 v10, p0

    #@358
    goto/16 :goto_714

    #@35a
    .line 9064
    :pswitch_35a
    const/high16 v0, 0x10000

    #@35c
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@35f
    .line 9065
    move-object/from16 v10, p0

    #@361
    goto/16 :goto_714

    #@363
    .line 9061
    :pswitch_363
    invoke-virtual {v3, v11}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@366
    .line 9062
    move-object/from16 v10, p0

    #@368
    goto/16 :goto_714

    #@36a
    .line 9058
    :pswitch_36a
    const/high16 v0, 0x100000

    #@36c
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@36f
    .line 9059
    move-object/from16 v10, p0

    #@371
    goto/16 :goto_714

    #@373
    .line 9055
    :pswitch_373
    const/high16 v0, 0x800000

    #@375
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@378
    .line 9056
    move-object/from16 v10, p0

    #@37a
    goto/16 :goto_714

    #@37c
    .line 9052
    :pswitch_37c
    const/high16 v0, 0x80000

    #@37e
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@381
    .line 9053
    move-object/from16 v10, p0

    #@383
    goto/16 :goto_714

    #@385
    .line 9049
    :pswitch_385
    const/high16 v0, 0x4000000

    #@387
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@38a
    .line 9050
    move-object/from16 v10, p0

    #@38c
    goto/16 :goto_714

    #@38e
    .line 9046
    :pswitch_38e
    const/high16 v0, 0x400000

    #@390
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@393
    .line 9047
    move-object/from16 v10, p0

    #@395
    goto/16 :goto_714

    #@397
    .line 9043
    :pswitch_397
    invoke-virtual {v3, v13}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@39a
    .line 9044
    move-object/from16 v10, p0

    #@39c
    goto/16 :goto_714

    #@39e
    .line 9040
    :pswitch_39e
    const/16 v0, 0x20

    #@3a0
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@3a3
    .line 9041
    move-object/from16 v10, p0

    #@3a5
    goto/16 :goto_714

    #@3a7
    .line 9037
    :pswitch_3a7
    const/16 v0, 0x10

    #@3a9
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@3ac
    .line 9038
    move-object/from16 v10, p0

    #@3ae
    goto/16 :goto_714

    #@3b0
    .line 9034
    :pswitch_3b0
    const/16 v0, 0x80

    #@3b2
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@3b5
    .line 9035
    move-object/from16 v10, p0

    #@3b7
    goto/16 :goto_714

    #@3b9
    .line 9031
    :pswitch_3b9
    const/16 v0, 0x40

    #@3bb
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@3be
    .line 9032
    move-object/from16 v10, p0

    #@3c0
    goto/16 :goto_714

    #@3c2
    .line 9028
    :pswitch_3c2
    const/4 v0, 0x2

    #@3c3
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@3c6
    .line 9029
    move-object/from16 v10, p0

    #@3c8
    goto/16 :goto_714

    #@3ca
    .line 9025
    :pswitch_3ca
    const/4 v0, 0x1

    #@3cb
    invoke-virtual {v3, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;

    #@3ce
    .line 9026
    move-object/from16 v10, p0

    #@3d0
    goto/16 :goto_714

    #@3d2
    .line 9021
    :pswitch_3d2
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@3d5
    move-result-object v0

    #@3d6
    .line 9022
    .local v0, "str":Ljava/lang/String;
    invoke-static {v0}, Landroid/content/Intent;->decodeInteger(Ljava/lang/String;)Ljava/lang/Integer;

    #@3d9
    move-result-object v8

    #@3da
    invoke-virtual {v8}, Ljava/lang/Integer;->intValue()I

    #@3dd
    move-result v8

    #@3de
    invoke-virtual {v3, v8}, Landroid/content/Intent;->setFlags(I)Landroid/content/Intent;

    #@3e1
    .line 9023
    move-object/from16 v10, p0

    #@3e3
    goto/16 :goto_714

    #@3e5
    .line 9013
    .end local v0    # "str":Ljava/lang/String;
    :pswitch_3e5
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@3e8
    move-result-object v0

    #@3e9
    .line 9014
    .restart local v0    # "str":Ljava/lang/String;
    invoke-virtual {v3, v0}, Landroid/content/Intent;->setPackage(Ljava/lang/String;)Landroid/content/Intent;

    #@3ec
    .line 9015
    if-ne v3, v2, :cond_3ef

    #@3ee
    .line 9016
    const/4 v4, 0x1

    #@3ef
    .line 9019
    .end local v0    # "str":Ljava/lang/String;
    :cond_3ef
    move-object/from16 v10, p0

    #@3f1
    goto/16 :goto_714

    #@3f3
    .line 9002
    :pswitch_3f3
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@3f6
    move-result-object v8

    #@3f7
    .line 9003
    .local v8, "str":Ljava/lang/String;
    invoke-static {v8}, Landroid/content/ComponentName;->unflattenFromString(Ljava/lang/String;)Landroid/content/ComponentName;

    #@3fa
    move-result-object v9

    #@3fb
    .line 9004
    .local v9, "cn":Landroid/content/ComponentName;
    if-eqz v9, :cond_407

    #@3fd
    .line 9006
    invoke-virtual {v3, v9}, Landroid/content/Intent;->setComponent(Landroid/content/ComponentName;)Landroid/content/Intent;

    #@400
    .line 9007
    if-ne v3, v2, :cond_403

    #@402
    .line 9008
    const/4 v4, 0x1

    #@403
    .line 9011
    .end local v8    # "str":Ljava/lang/String;
    .end local v9    # "cn":Landroid/content/ComponentName;
    :cond_403
    move-object/from16 v10, p0

    #@405
    goto/16 :goto_714

    #@407
    .line 9005
    .restart local v8    # "str":Ljava/lang/String;
    .restart local v9    # "cn":Landroid/content/ComponentName;
    :cond_407
    new-instance v10, Ljava/lang/IllegalArgumentException;

    #@409
    new-instance v11, Ljava/lang/StringBuilder;

    #@40b
    invoke-direct {v11}, Ljava/lang/StringBuilder;-><init>()V

    #@40e
    invoke-virtual {v11, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@411
    move-result-object v0

    #@412
    invoke-virtual {v0, v8}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@415
    move-result-object v0

    #@416
    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@419
    move-result-object v0

    #@41a
    invoke-direct {v10, v0}, Ljava/lang/IllegalArgumentException;-><init>(Ljava/lang/String;)V

    #@41d
    throw v10

    #@41e
    .line 8981
    .end local v8    # "str":Ljava/lang/String;
    .end local v9    # "cn":Landroid/content/ComponentName;
    :pswitch_41e
    const/4 v0, 0x1

    #@41f
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@422
    move-result-object v8

    #@423
    .line 8982
    .local v8, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@426
    move-result-object v9

    #@427
    invoke-virtual {v9}, Ljava/lang/String;->toLowerCase()Ljava/lang/String;

    #@42a
    move-result-object v9

    #@42b
    .line 8986
    .local v9, "value":Ljava/lang/String;
    const-string/jumbo v10, "true"

    #@42e
    invoke-virtual {v10, v9}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@431
    move-result v10

    #@432
    if-nez v10, :cond_479

    #@434
    const-string/jumbo v10, "t"

    #@437
    invoke-virtual {v10, v9}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@43a
    move-result v10

    #@43b
    if-eqz v10, :cond_43e

    #@43d
    goto :goto_479

    #@43e
    .line 8988
    :cond_43e
    const-string v10, "false"

    #@440
    invoke-virtual {v10, v9}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@443
    move-result v10

    #@444
    if-nez v10, :cond_477

    #@446
    const-string v10, "f"

    #@448
    invoke-virtual {v10, v9}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    #@44b
    move-result v10

    #@44c
    if-eqz v10, :cond_44f

    #@44e
    goto :goto_477

    #@44f
    .line 8992
    :cond_44f
    :try_start_44f
    invoke-static {v9}, Landroid/content/Intent;->decodeInteger(Ljava/lang/String;)Ljava/lang/Integer;

    #@452
    move-result-object v10

    #@453
    invoke-virtual {v10}, Ljava/lang/Integer;->intValue()I

    #@456
    move-result v10
    :try_end_457
    .catch Ljava/lang/NumberFormatException; {:try_start_44f .. :try_end_457} :catch_45d

    #@457
    if-eqz v10, :cond_45b

    #@459
    move v11, v0

    #@45a
    goto :goto_45c

    #@45b
    :cond_45b
    const/4 v11, 0x0

    #@45c
    .line 8995
    .local v11, "arg":Z
    :goto_45c
    goto :goto_47a

    #@45d
    .line 8993
    .end local v11    # "arg":Z
    :catch_45d
    move-exception v0

    #@45e
    .line 8994
    .local v0, "ex":Ljava/lang/NumberFormatException;
    new-instance v10, Ljava/lang/IllegalArgumentException;

    #@460
    new-instance v11, Ljava/lang/StringBuilder;

    #@462
    invoke-direct {v11}, Ljava/lang/StringBuilder;-><init>()V

    #@465
    const-string v12, "Invalid boolean value: "

    #@467
    invoke-virtual {v11, v12}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@46a
    move-result-object v11

    #@46b
    invoke-virtual {v11, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@46e
    move-result-object v11

    #@46f
    invoke-virtual {v11}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@472
    move-result-object v11

    #@473
    invoke-direct {v10, v11}, Ljava/lang/IllegalArgumentException;-><init>(Ljava/lang/String;)V

    #@476
    throw v10

    #@477
    .line 8989
    .end local v0    # "ex":Ljava/lang/NumberFormatException;
    :cond_477
    :goto_477
    const/4 v11, 0x0

    #@478
    .restart local v11    # "arg":Z
    goto :goto_47a

    #@479
    .line 8987
    .end local v11    # "arg":Z
    :cond_479
    :goto_479
    const/4 v11, 0x1

    #@47a
    .line 8998
    .restart local v11    # "arg":Z
    :goto_47a
    invoke-virtual {v3, v8, v11}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Z)Landroid/content/Intent;

    #@47d
    .line 9000
    .end local v8    # "key":Ljava/lang/String;
    .end local v9    # "value":Ljava/lang/String;
    .end local v11    # "arg":Z
    move-object/from16 v10, p0

    #@47f
    goto/16 :goto_714

    #@481
    .line 8966
    :pswitch_481
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@484
    move-result-object v0

    #@485
    .line 8967
    .local v0, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@488
    move-result-object v8

    #@489
    .line 8971
    .local v8, "value":Ljava/lang/String;
    invoke-virtual {v8, v15}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    #@48c
    move-result-object v9

    #@48d
    .line 8972
    .local v9, "strings":[Ljava/lang/String;
    new-instance v10, Ljava/util/ArrayList;

    #@48f
    array-length v11, v9

    #@490
    invoke-direct {v10, v11}, Ljava/util/ArrayList;-><init>(I)V

    #@493
    .line 8973
    .local v10, "list":Ljava/util/ArrayList;, "Ljava/util/ArrayList<Ljava/lang/String;>;"
    const/4 v11, 0x0

    #@494
    .local v11, "i":I
    :goto_494
    array-length v12, v9

    #@495
    if-ge v11, v12, :cond_49f

    #@497
    .line 8974
    aget-object v12, v9, v11

    #@499
    invoke-virtual {v10, v12}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z

    #@49c
    .line 8973
    add-int/lit8 v11, v11, 0x1

    #@49e
    goto :goto_494

    #@49f
    .line 8976
    .end local v11    # "i":I
    :cond_49f
    invoke-virtual {v3, v0, v10}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/io/Serializable;)Landroid/content/Intent;

    #@4a2
    .line 8977
    const/4 v0, 0x1

    #@4a3
    .line 8979
    .end local v4    # "hasIntentInfo":Z
    .end local v8    # "value":Ljava/lang/String;
    .end local v9    # "strings":[Ljava/lang/String;
    .end local v10    # "list":Ljava/util/ArrayList;, "Ljava/util/ArrayList<Ljava/lang/String;>;"
    .local v0, "hasIntentInfo":Z
    move-object/from16 v10, p0

    #@4a5
    move v4, v0

    #@4a6
    goto/16 :goto_714

    #@4a8
    .line 8955
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :pswitch_4a8
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@4ab
    move-result-object v0

    #@4ac
    .line 8956
    .local v0, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@4af
    move-result-object v8

    #@4b0
    .line 8960
    .restart local v8    # "value":Ljava/lang/String;
    invoke-virtual {v8, v15}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    #@4b3
    move-result-object v9

    #@4b4
    .line 8961
    .restart local v9    # "strings":[Ljava/lang/String;
    invoke-virtual {v3, v0, v9}, Landroid/content/Intent;->putExtra(Ljava/lang/String;[Ljava/lang/String;)Landroid/content/Intent;

    #@4b7
    .line 8962
    const/4 v0, 0x1

    #@4b8
    .line 8964
    .end local v4    # "hasIntentInfo":Z
    .end local v8    # "value":Ljava/lang/String;
    .end local v9    # "strings":[Ljava/lang/String;
    .local v0, "hasIntentInfo":Z
    move-object/from16 v10, p0

    #@4ba
    move v4, v0

    #@4bb
    goto/16 :goto_714

    #@4bd
    .line 8943
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :pswitch_4bd
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@4c0
    move-result-object v0

    #@4c1
    .line 8944
    .local v0, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@4c4
    move-result-object v8

    #@4c5
    .line 8945
    .restart local v8    # "value":Ljava/lang/String;
    invoke-virtual {v8, v14}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    #@4c8
    move-result-object v9

    #@4c9
    .line 8946
    .restart local v9    # "strings":[Ljava/lang/String;
    new-instance v10, Ljava/util/ArrayList;

    #@4cb
    array-length v11, v9

    #@4cc
    invoke-direct {v10, v11}, Ljava/util/ArrayList;-><init>(I)V

    #@4cf
    .line 8947
    .local v10, "list":Ljava/util/ArrayList;, "Ljava/util/ArrayList<Ljava/lang/Double;>;"
    const/4 v11, 0x0

    #@4d0
    .restart local v11    # "i":I
    :goto_4d0
    array-length v12, v9

    #@4d1
    if-ge v11, v12, :cond_4df

    #@4d3
    .line 8948
    aget-object v12, v9, v11

    #@4d5
    invoke-static {v12}, Ljava/lang/Double;->valueOf(Ljava/lang/String;)Ljava/lang/Double;

    #@4d8
    move-result-object v12

    #@4d9
    invoke-virtual {v10, v12}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z

    #@4dc
    .line 8947
    add-int/lit8 v11, v11, 0x1

    #@4de
    goto :goto_4d0

    #@4df
    .line 8950
    .end local v11    # "i":I
    :cond_4df
    invoke-virtual {v3, v0, v10}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/io/Serializable;)Landroid/content/Intent;

    #@4e2
    .line 8951
    const/4 v0, 0x1

    #@4e3
    .line 8953
    .end local v4    # "hasIntentInfo":Z
    .end local v8    # "value":Ljava/lang/String;
    .end local v9    # "strings":[Ljava/lang/String;
    .end local v10    # "list":Ljava/util/ArrayList;, "Ljava/util/ArrayList<Ljava/lang/Double;>;"
    .local v0, "hasIntentInfo":Z
    move-object/from16 v10, p0

    #@4e5
    move v4, v0

    #@4e6
    goto/16 :goto_714

    #@4e8
    .line 8931
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :pswitch_4e8
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@4eb
    move-result-object v0

    #@4ec
    .line 8932
    .local v0, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@4ef
    move-result-object v8

    #@4f0
    .line 8933
    .restart local v8    # "value":Ljava/lang/String;
    invoke-virtual {v8, v14}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    #@4f3
    move-result-object v9

    #@4f4
    .line 8934
    .restart local v9    # "strings":[Ljava/lang/String;
    array-length v10, v9

    #@4f5
    new-array v10, v10, [D

    #@4f7
    .line 8935
    .local v10, "list":[D
    const/4 v11, 0x0

    #@4f8
    .restart local v11    # "i":I
    :goto_4f8
    array-length v12, v9

    #@4f9
    if-ge v11, v12, :cond_50a

    #@4fb
    .line 8936
    aget-object v12, v9, v11

    #@4fd
    invoke-static {v12}, Ljava/lang/Double;->valueOf(Ljava/lang/String;)Ljava/lang/Double;

    #@500
    move-result-object v12

    #@501
    invoke-virtual {v12}, Ljava/lang/Double;->doubleValue()D

    #@504
    move-result-wide v12

    #@505
    aput-wide v12, v10, v11

    #@507
    .line 8935
    add-int/lit8 v11, v11, 0x1

    #@509
    goto :goto_4f8

    #@50a
    .line 8938
    .end local v11    # "i":I
    :cond_50a
    invoke-virtual {v3, v0, v10}, Landroid/content/Intent;->putExtra(Ljava/lang/String;[D)Landroid/content/Intent;

    #@50d
    .line 8939
    const/4 v0, 0x1

    #@50e
    .line 8941
    .end local v4    # "hasIntentInfo":Z
    .end local v8    # "value":Ljava/lang/String;
    .end local v9    # "strings":[Ljava/lang/String;
    .end local v10    # "list":[D
    .local v0, "hasIntentInfo":Z
    move-object/from16 v10, p0

    #@510
    move v4, v0

    #@511
    goto/16 :goto_714

    #@513
    .line 8924
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :pswitch_513
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@516
    move-result-object v0

    #@517
    .line 8925
    .local v0, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@51a
    move-result-object v8

    #@51b
    .line 8926
    .restart local v8    # "value":Ljava/lang/String;
    invoke-static {v8}, Ljava/lang/Double;->valueOf(Ljava/lang/String;)Ljava/lang/Double;

    #@51e
    move-result-object v9

    #@51f
    invoke-virtual {v3, v0, v9}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/io/Serializable;)Landroid/content/Intent;

    #@522
    .line 8927
    const/4 v0, 0x1

    #@523
    .line 8929
    .end local v4    # "hasIntentInfo":Z
    .end local v8    # "value":Ljava/lang/String;
    .local v0, "hasIntentInfo":Z
    move-object/from16 v10, p0

    #@525
    move v4, v0

    #@526
    goto/16 :goto_714

    #@528
    .line 8912
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :pswitch_528
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@52b
    move-result-object v0

    #@52c
    .line 8913
    .local v0, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@52f
    move-result-object v8

    #@530
    .line 8914
    .restart local v8    # "value":Ljava/lang/String;
    invoke-virtual {v8, v14}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    #@533
    move-result-object v9

    #@534
    .line 8915
    .restart local v9    # "strings":[Ljava/lang/String;
    new-instance v10, Ljava/util/ArrayList;

    #@536
    array-length v11, v9

    #@537
    invoke-direct {v10, v11}, Ljava/util/ArrayList;-><init>(I)V

    #@53a
    .line 8916
    .local v10, "list":Ljava/util/ArrayList;, "Ljava/util/ArrayList<Ljava/lang/Float;>;"
    const/4 v11, 0x0

    #@53b
    .restart local v11    # "i":I
    :goto_53b
    array-length v12, v9

    #@53c
    if-ge v11, v12, :cond_54a

    #@53e
    .line 8917
    aget-object v12, v9, v11

    #@540
    invoke-static {v12}, Ljava/lang/Float;->valueOf(Ljava/lang/String;)Ljava/lang/Float;

    #@543
    move-result-object v12

    #@544
    invoke-virtual {v10, v12}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z

    #@547
    .line 8916
    add-int/lit8 v11, v11, 0x1

    #@549
    goto :goto_53b

    #@54a
    .line 8919
    .end local v11    # "i":I
    :cond_54a
    invoke-virtual {v3, v0, v10}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/io/Serializable;)Landroid/content/Intent;

    #@54d
    .line 8920
    const/4 v0, 0x1

    #@54e
    .line 8922
    .end local v4    # "hasIntentInfo":Z
    .end local v8    # "value":Ljava/lang/String;
    .end local v9    # "strings":[Ljava/lang/String;
    .end local v10    # "list":Ljava/util/ArrayList;, "Ljava/util/ArrayList<Ljava/lang/Float;>;"
    .local v0, "hasIntentInfo":Z
    move-object/from16 v10, p0

    #@550
    move v4, v0

    #@551
    goto/16 :goto_714

    #@553
    .line 8900
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :pswitch_553
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@556
    move-result-object v0

    #@557
    .line 8901
    .local v0, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@55a
    move-result-object v8

    #@55b
    .line 8902
    .restart local v8    # "value":Ljava/lang/String;
    invoke-virtual {v8, v14}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    #@55e
    move-result-object v9

    #@55f
    .line 8903
    .restart local v9    # "strings":[Ljava/lang/String;
    array-length v10, v9

    #@560
    new-array v10, v10, [F

    #@562
    .line 8904
    .local v10, "list":[F
    const/4 v11, 0x0

    #@563
    .restart local v11    # "i":I
    :goto_563
    array-length v12, v9

    #@564
    if-ge v11, v12, :cond_575

    #@566
    .line 8905
    aget-object v12, v9, v11

    #@568
    invoke-static {v12}, Ljava/lang/Float;->valueOf(Ljava/lang/String;)Ljava/lang/Float;

    #@56b
    move-result-object v12

    #@56c
    invoke-virtual {v12}, Ljava/lang/Float;->floatValue()F

    #@56f
    move-result v12

    #@570
    aput v12, v10, v11

    #@572
    .line 8904
    add-int/lit8 v11, v11, 0x1

    #@574
    goto :goto_563

    #@575
    .line 8907
    .end local v11    # "i":I
    :cond_575
    invoke-virtual {v3, v0, v10}, Landroid/content/Intent;->putExtra(Ljava/lang/String;[F)Landroid/content/Intent;

    #@578
    .line 8908
    const/4 v0, 0x1

    #@579
    .line 8910
    .end local v4    # "hasIntentInfo":Z
    .end local v8    # "value":Ljava/lang/String;
    .end local v9    # "strings":[Ljava/lang/String;
    .end local v10    # "list":[F
    .local v0, "hasIntentInfo":Z
    move-object/from16 v10, p0

    #@57b
    move v4, v0

    #@57c
    goto/16 :goto_714

    #@57e
    .line 8893
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :pswitch_57e
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@581
    move-result-object v0

    #@582
    .line 8894
    .local v0, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@585
    move-result-object v8

    #@586
    .line 8895
    .restart local v8    # "value":Ljava/lang/String;
    invoke-static {v8}, Ljava/lang/Float;->valueOf(Ljava/lang/String;)Ljava/lang/Float;

    #@589
    move-result-object v9

    #@58a
    invoke-virtual {v3, v0, v9}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/io/Serializable;)Landroid/content/Intent;

    #@58d
    .line 8896
    const/4 v0, 0x1

    #@58e
    .line 8898
    .end local v4    # "hasIntentInfo":Z
    .end local v8    # "value":Ljava/lang/String;
    .local v0, "hasIntentInfo":Z
    move-object/from16 v10, p0

    #@590
    move v4, v0

    #@591
    goto/16 :goto_714

    #@593
    .line 8881
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :pswitch_593
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@596
    move-result-object v0

    #@597
    .line 8882
    .local v0, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@59a
    move-result-object v8

    #@59b
    .line 8883
    .restart local v8    # "value":Ljava/lang/String;
    invoke-virtual {v8, v14}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    #@59e
    move-result-object v9

    #@59f
    .line 8884
    .restart local v9    # "strings":[Ljava/lang/String;
    new-instance v10, Ljava/util/ArrayList;

    #@5a1
    array-length v11, v9

    #@5a2
    invoke-direct {v10, v11}, Ljava/util/ArrayList;-><init>(I)V

    #@5a5
    .line 8885
    .local v10, "list":Ljava/util/ArrayList;, "Ljava/util/ArrayList<Ljava/lang/Long;>;"
    const/4 v11, 0x0

    #@5a6
    .restart local v11    # "i":I
    :goto_5a6
    array-length v12, v9

    #@5a7
    if-ge v11, v12, :cond_5b5

    #@5a9
    .line 8886
    aget-object v12, v9, v11

    #@5ab
    invoke-static {v12}, Ljava/lang/Long;->valueOf(Ljava/lang/String;)Ljava/lang/Long;

    #@5ae
    move-result-object v12

    #@5af
    invoke-virtual {v10, v12}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z

    #@5b2
    .line 8885
    add-int/lit8 v11, v11, 0x1

    #@5b4
    goto :goto_5a6

    #@5b5
    .line 8888
    .end local v11    # "i":I
    :cond_5b5
    invoke-virtual {v3, v0, v10}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/io/Serializable;)Landroid/content/Intent;

    #@5b8
    .line 8889
    const/4 v0, 0x1

    #@5b9
    .line 8891
    .end local v4    # "hasIntentInfo":Z
    .end local v8    # "value":Ljava/lang/String;
    .end local v9    # "strings":[Ljava/lang/String;
    .end local v10    # "list":Ljava/util/ArrayList;, "Ljava/util/ArrayList<Ljava/lang/Long;>;"
    .local v0, "hasIntentInfo":Z
    move-object/from16 v10, p0

    #@5bb
    move v4, v0

    #@5bc
    goto/16 :goto_714

    #@5be
    .line 8869
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :pswitch_5be
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@5c1
    move-result-object v0

    #@5c2
    .line 8870
    .local v0, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@5c5
    move-result-object v8

    #@5c6
    .line 8871
    .restart local v8    # "value":Ljava/lang/String;
    invoke-virtual {v8, v14}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    #@5c9
    move-result-object v9

    #@5ca
    .line 8872
    .restart local v9    # "strings":[Ljava/lang/String;
    array-length v10, v9

    #@5cb
    new-array v10, v10, [J

    #@5cd
    .line 8873
    .local v10, "list":[J
    const/4 v11, 0x0

    #@5ce
    .restart local v11    # "i":I
    :goto_5ce
    array-length v12, v9

    #@5cf
    if-ge v11, v12, :cond_5e0

    #@5d1
    .line 8874
    aget-object v12, v9, v11

    #@5d3
    invoke-static {v12}, Ljava/lang/Long;->valueOf(Ljava/lang/String;)Ljava/lang/Long;

    #@5d6
    move-result-object v12

    #@5d7
    invoke-virtual {v12}, Ljava/lang/Long;->longValue()J

    #@5da
    move-result-wide v12

    #@5db
    aput-wide v12, v10, v11

    #@5dd
    .line 8873
    add-int/lit8 v11, v11, 0x1

    #@5df
    goto :goto_5ce

    #@5e0
    .line 8876
    .end local v11    # "i":I
    :cond_5e0
    invoke-virtual {v3, v0, v10}, Landroid/content/Intent;->putExtra(Ljava/lang/String;[J)Landroid/content/Intent;

    #@5e3
    .line 8877
    const/4 v0, 0x1

    #@5e4
    .line 8879
    .end local v4    # "hasIntentInfo":Z
    .end local v8    # "value":Ljava/lang/String;
    .end local v9    # "strings":[Ljava/lang/String;
    .end local v10    # "list":[J
    .local v0, "hasIntentInfo":Z
    move-object/from16 v10, p0

    #@5e6
    move v4, v0

    #@5e7
    goto/16 :goto_714

    #@5e9
    .line 8863
    .end local v0    # "hasIntentInfo":Z
    .restart local v4    # "hasIntentInfo":Z
    :pswitch_5e9
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@5ec
    move-result-object v0

    #@5ed
    .line 8864
    .local v0, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@5f0
    move-result-object v8

    #@5f1
    .line 8865
    .restart local v8    # "value":Ljava/lang/String;
    invoke-static {v8}, Ljava/lang/Long;->valueOf(Ljava/lang/String;)Ljava/lang/Long;

    #@5f4
    move-result-object v9

    #@5f5
    invoke-virtual {v3, v0, v9}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/io/Serializable;)Landroid/content/Intent;

    #@5f8
    .line 8867
    .end local v0    # "key":Ljava/lang/String;
    .end local v8    # "value":Ljava/lang/String;
    move-object/from16 v10, p0

    #@5fa
    goto/16 :goto_714

    #@5fc
    .line 8852
    :pswitch_5fc
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@5ff
    move-result-object v0

    #@600
    .line 8853
    .restart local v0    # "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@603
    move-result-object v8

    #@604
    .line 8854
    .restart local v8    # "value":Ljava/lang/String;
    invoke-virtual {v8, v14}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    #@607
    move-result-object v9

    #@608
    .line 8855
    .restart local v9    # "strings":[Ljava/lang/String;
    new-instance v10, Ljava/util/ArrayList;

    #@60a
    array-length v11, v9

    #@60b
    invoke-direct {v10, v11}, Ljava/util/ArrayList;-><init>(I)V

    #@60e
    .line 8856
    .local v10, "list":Ljava/util/ArrayList;, "Ljava/util/ArrayList<Ljava/lang/Integer;>;"
    const/4 v11, 0x0

    #@60f
    .restart local v11    # "i":I
    :goto_60f
    array-length v12, v9

    #@610
    if-ge v11, v12, :cond_61e

    #@612
    .line 8857
    aget-object v12, v9, v11

    #@614
    invoke-static {v12}, Landroid/content/Intent;->decodeInteger(Ljava/lang/String;)Ljava/lang/Integer;

    #@617
    move-result-object v12

    #@618
    invoke-virtual {v10, v12}, Ljava/util/ArrayList;->add(Ljava/lang/Object;)Z

    #@61b
    .line 8856
    add-int/lit8 v11, v11, 0x1

    #@61d
    goto :goto_60f

    #@61e
    .line 8859
    .end local v11    # "i":I
    :cond_61e
    invoke-virtual {v3, v0, v10}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/io/Serializable;)Landroid/content/Intent;

    #@621
    .line 8861
    .end local v0    # "key":Ljava/lang/String;
    .end local v8    # "value":Ljava/lang/String;
    .end local v9    # "strings":[Ljava/lang/String;
    .end local v10    # "list":Ljava/util/ArrayList;, "Ljava/util/ArrayList<Ljava/lang/Integer;>;"
    move-object/from16 v10, p0

    #@623
    goto/16 :goto_714

    #@625
    .line 8841
    :pswitch_625
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@628
    move-result-object v0

    #@629
    .line 8842
    .restart local v0    # "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@62c
    move-result-object v8

    #@62d
    .line 8843
    .restart local v8    # "value":Ljava/lang/String;
    invoke-virtual {v8, v14}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    #@630
    move-result-object v9

    #@631
    .line 8844
    .restart local v9    # "strings":[Ljava/lang/String;
    array-length v10, v9

    #@632
    new-array v10, v10, [I

    #@634
    .line 8845
    .local v10, "list":[I
    const/4 v11, 0x0

    #@635
    .restart local v11    # "i":I
    :goto_635
    array-length v12, v9

    #@636
    if-ge v11, v12, :cond_647

    #@638
    .line 8846
    aget-object v12, v9, v11

    #@63a
    invoke-static {v12}, Landroid/content/Intent;->decodeInteger(Ljava/lang/String;)Ljava/lang/Integer;

    #@63d
    move-result-object v12

    #@63e
    invoke-virtual {v12}, Ljava/lang/Integer;->intValue()I

    #@641
    move-result v12

    #@642
    aput v12, v10, v11

    #@644
    .line 8845
    add-int/lit8 v11, v11, 0x1

    #@646
    goto :goto_635

    #@647
    .line 8848
    .end local v11    # "i":I
    :cond_647
    invoke-virtual {v3, v0, v10}, Landroid/content/Intent;->putExtra(Ljava/lang/String;[I)Landroid/content/Intent;

    #@64a
    .line 8850
    .end local v0    # "key":Ljava/lang/String;
    .end local v8    # "value":Ljava/lang/String;
    .end local v9    # "strings":[Ljava/lang/String;
    .end local v10    # "list":[I
    move-object/from16 v10, p0

    #@64c
    goto/16 :goto_714

    #@64e
    .line 8832
    :pswitch_64e
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@651
    move-result-object v8

    #@652
    .line 8833
    .local v8, "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@655
    move-result-object v9

    #@656
    .line 8834
    .local v9, "value":Ljava/lang/String;
    invoke-static {v9}, Landroid/content/ComponentName;->unflattenFromString(Ljava/lang/String;)Landroid/content/ComponentName;

    #@659
    move-result-object v10

    #@65a
    .line 8835
    .local v10, "cn":Landroid/content/ComponentName;
    if-eqz v10, :cond_663

    #@65c
    .line 8837
    invoke-virtual {v3, v8, v10}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Landroid/os/Parcelable;)Landroid/content/Intent;

    #@65f
    .line 8839
    .end local v8    # "key":Ljava/lang/String;
    .end local v9    # "value":Ljava/lang/String;
    .end local v10    # "cn":Landroid/content/ComponentName;
    move-object/from16 v10, p0

    #@661
    goto/16 :goto_714

    #@663
    .line 8836
    .restart local v8    # "key":Ljava/lang/String;
    .restart local v9    # "value":Ljava/lang/String;
    .restart local v10    # "cn":Landroid/content/ComponentName;
    :cond_663
    new-instance v11, Ljava/lang/IllegalArgumentException;

    #@665
    new-instance v12, Ljava/lang/StringBuilder;

    #@667
    invoke-direct {v12}, Ljava/lang/StringBuilder;-><init>()V

    #@66a
    invoke-virtual {v12, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@66d
    move-result-object v0

    #@66e
    invoke-virtual {v0, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@671
    move-result-object v0

    #@672
    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@675
    move-result-object v0

    #@676
    invoke-direct {v11, v0}, Ljava/lang/IllegalArgumentException;-><init>(Ljava/lang/String;)V

    #@679
    throw v11

    #@67a
    .line 8826
    .end local v8    # "key":Ljava/lang/String;
    .end local v9    # "value":Ljava/lang/String;
    .end local v10    # "cn":Landroid/content/ComponentName;
    :pswitch_67a
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@67d
    move-result-object v0

    #@67e
    .line 8827
    .restart local v0    # "key":Ljava/lang/String;
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@681
    move-result-object v8

    #@682
    .line 8828
    .local v8, "value":Ljava/lang/String;
    invoke-static {v8}, Landroid/net/Uri;->parse(Ljava/lang/String;)Landroid/net/Uri;

    #@685
    move-result-object v9

    #@686
    invoke-virtual {v3, v0, v9}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Landroid/os/Parcelable;)Landroid/content/Intent;

    #@689
    .line 8830
    .end local v0    # "key":Ljava/lang/String;
    .end local v8    # "value":Ljava/lang/String;
    move-object/from16 v10, p0

    #@68b
    goto/16 :goto_714

    #@68d
    .line 8820
    :pswitch_68d
    invoke-virtual/range {p0 .. p0}, Landroid/os/ShellCommand;->getNextArgRequired()Ljava/lang/String;

    #@690
    move-result-object v0

    #@691
    .line 8821
    .restart loca