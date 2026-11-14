.method public whitelist test-api toString()Ljava/lang/String;
    .registers 4

    #@0
    .line 831
    new-instance v0, Ljava/lang/StringBuilder;

    #@2
    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    #@5
    const-string v1, "TaskInfo{userId="

    #@7
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@a
    move-result-object v0

    #@b
    iget v1, p0, Landroid/app/TaskInfo;->userId:I

    #@d
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@10
    move-result-object v0

    #@11
    const-string v1, " taskId="

    #@13
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@16
    move-result-object v0

    #@17
    iget v1, p0, Landroid/app/TaskInfo;->taskId:I

    #@19
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@1c
    move-result-object v0

    #@1d
    const-string v1, " effectiveUid="

    #@1f
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@22
    move-result-object v0

    #@23
    iget v1, p0, Landroid/app/TaskInfo;->effectiveUid:I

    #@25
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@28
    move-result-object v0

    #@29
    const-string v1, " seqId="

    #@2b
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@2e
    move-result-object v0

    #@2f
    iget v1, p0, Landroid/app/TaskInfo;->seqId:I

    #@31
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@34
    move-result-object v0

    #@35
    const-string v1, " displayId="

    #@37
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@3a
    move-result-object v0

    #@3b
    iget v1, p0, Landroid/app/TaskInfo;->displayId:I

    #@3d
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@40
    move-result-object v0

    #@41
    const-string v1, " isRunning="

    #@43
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@46
    move-result-object v0

    #@47
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isRunning:Z

    #@49
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@4c
    move-result-object v0

    #@4d
    const-string v1, " baseIntent="

    #@4f
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@52
    move-result-object v0

    #@53
    iget-object v1, p0, Landroid/app/TaskInfo;->baseIntent:Landroid/content/Intent;

    #@55
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@58
    move-result-object v0

    #@59
    const-string v1, " baseActivity="

    #@5b
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@5e
    move-result-object v0

    #@5f
    iget-object v1, p0, Landroid/app/TaskInfo;->baseActivity:Landroid/content/ComponentName;

    #@61
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@64
    move-result-object v0

    #@65
    const-string v1, " topActivity="

    #@67
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@6a
    move-result-object v0

    #@6b
    iget-object v1, p0, Landroid/app/TaskInfo;->topActivity:Landroid/content/ComponentName;

    #@6d
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@70
    move-result-object v0

    #@71
    const-string v1, " origActivity="

    #@73
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@76
    move-result-object v0

    #@77
    iget-object v1, p0, Landroid/app/TaskInfo;->origActivity:Landroid/content/ComponentName;

    #@79
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@7c
    move-result-object v0

    #@7d
    const-string v1, " realActivity="

    #@7f
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@82
    move-result-object v0

    #@83
    iget-object v1, p0, Landroid/app/TaskInfo;->realActivity:Landroid/content/ComponentName;

    #@85
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@88
    move-result-object v0

    #@89
    const-string v1, " realActivityIsAppLockEnabled="

    #@8b
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@8e
    move-result-object v0

    #@8f
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isRealActivityAppLockEnabled:Z

    #@91
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@94
    move-result-object v0

    #@95
    const-string v1, " numActivities="

    #@97
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@9a
    move-result-object v0

    #@9b
    iget v1, p0, Landroid/app/TaskInfo;->numActivities:I

    #@9d
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@a0
    move-result-object v0

    #@a1
    const-string v1, " lastActiveTime="

    #@a3
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@a6
    move-result-object v0

    #@a7
    iget-wide v1, p0, Landroid/app/TaskInfo;->lastActiveTime:J

    #@a9
    invoke-virtual {v0, v1, v2}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    #@ac
    move-result-object v0

    #@ad
    const-string v1, " supportsMultiWindow="

    #@af
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@b2
    move-result-object v0

    #@b3
    iget-boolean v1, p0, Landroid/app/TaskInfo;->supportsMultiWindow:Z

    #@b5
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@b8
    move-result-object v0

    #@b9
    const-string v1, " supportsMultiWindowWithoutConstraints="

    #@bb
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@be
    move-result-object v0

    #@bf
    iget-boolean v1, p0, Landroid/app/TaskInfo;->supportsMultiWindowWithoutConstraints:Z

    #@c1
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@c4
    move-result-object v0

    #@c5
    const-string v1, " resizeMode="

    #@c7
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@ca
    move-result-object v0

    #@cb
    iget v1, p0, Landroid/app/TaskInfo;->resizeMode:I

    #@cd
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@d0
    move-result-object v0

    #@d1
    const-string v1, " isResizeable="

    #@d3
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@d6
    move-result-object v0

    #@d7
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isResizeable:Z

    #@d9
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@dc
    move-result-object v0

    #@dd
    const-string v1, " minWidth="

    #@df
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@e2
    move-result-object v0

    #@e3
    iget v1, p0, Landroid/app/TaskInfo;->minWidth:I

    #@e5
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@e8
    move-result-object v0

    #@e9
    const-string v1, " minHeight="

    #@eb
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@ee
    move-result-object v0

    #@ef
    iget v1, p0, Landroid/app/TaskInfo;->minHeight:I

    #@f1
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@f4
    move-result-object v0

    #@f5
    const-string v1, " defaultMinSize="

    #@f7
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@fa
    move-result-object v0

    #@fb
    iget v1, p0, Landroid/app/TaskInfo;->defaultMinSize:I

    #@fd
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@100
    move-result-object v0

    #@101
    const-string v1, " token="

    #@103
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@106
    move-result-object v0

    #@107
    iget-object v1, p0, Landroid/app/TaskInfo;->token:Landroid/window/WindowContainerToken;

    #@109
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@10c
    move-result-object v0

    #@10d
    const-string v1, " topActivityType="

    #@10f
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@112
    move-result-object v0

    #@113
    iget v1, p0, Landroid/app/TaskInfo;->topActivityType:I

    #@115
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@118
    move-result-object v0

    #@119
    const-string v1, " pictureInPictureParams="

    #@11b
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@11e
    move-result-object v0

    #@11f
    iget-object v1, p0, Landroid/app/TaskInfo;->pictureInPictureParams:Landroid/app/PictureInPictureParams;

    #@121
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@124
    move-result-object v0

    #@125
    const-string v1, " shouldDockBigOverlays="

    #@127
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@12a
    move-result-object v0

    #@12b
    iget-boolean v1, p0, Landroid/app/TaskInfo;->shouldDockBigOverlays:Z

    #@12d
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@130
    move-result-object v0

    #@131
    const-string v1, " launchIntoPipHostTaskId="

    #@133
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@136
    move-result-object v0

    #@137
    iget v1, p0, Landroid/app/TaskInfo;->launchIntoPipHostTaskId:I

    #@139
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@13c
    move-result-object v0

    #@13d
    const-string v1, " lastParentTaskIdBeforePip="

    #@13f
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@142
    move-result-object v0

    #@143
    iget v1, p0, Landroid/app/TaskInfo;->lastParentTaskIdBeforePip:I

    #@145
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@148
    move-result-object v0

    #@149
    const-string v1, " displayCutoutSafeInsets="

    #@14b
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@14e
    move-result-object v0

    #@14f
    iget-object v1, p0, Landroid/app/TaskInfo;->displayCutoutInsets:Landroid/graphics/Rect;

    #@151
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@154
    move-result-object v0

    #@155
    const-string v1, " topActivityInfo="

    #@157
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@15a
    move-result-object v0

    #@15b
    iget-object v1, p0, Landroid/app/TaskInfo;->topActivityInfo:Landroid/content/pm/ActivityInfo;

    #@15d
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@160
    move-result-object v0

    #@161
    const-string v1, " launchCookies="

    #@163
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@166
    move-result-object v0

    #@167
    iget-object v1, p0, Landroid/app/TaskInfo;->launchCookies:Ljava/util/ArrayList;

    #@169
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@16c
    move-result-object v0

    #@16d
    const-string v1, " positionInParent="

    #@16f
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@172
    move-result-object v0

    #@173
    iget-object v1, p0, Landroid/app/TaskInfo;->positionInParent:Landroid/graphics/Point;

    #@175
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@178
    move-result-object v0

    #@179
    const-string v1, " parentTaskId="

    #@17b
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@17e
    move-result-object v0

    #@17f
    iget v1, p0, Landroid/app/TaskInfo;->parentTaskId:I

    #@181
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@184
    move-result-object v0

    #@185
    const-string v1, " isFocused="

    #@187
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@18a
    move-result-object v0

    #@18b
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isFocused:Z

    #@18d
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@190
    move-result-object v0

    #@191
    const-string v1, " isInteractive="

    #@193
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@196
    move-result-object v0

    #@197
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isInteractive:Z

    #@199
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@19c
    move-result-object v0

    #@19d
    const-string v1, " isVisible="

    #@19f
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@1a2
    move-result-object v0

    #@1a3
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isVisible:Z

    #@1a5
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@1a8
    move-result-object v0

    #@1a9
    const-string v1, " isVisibleRequested="

    #@1ab
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@1ae
    move-result-object v0

    #@1af
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isVisibleRequested:Z

    #@1b1
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@1b4
    move-result-object v0

    #@1b5
    const-string v1, " isTopActivityNoDisplay="

    #@1b7
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@1ba
    move-result-object v0

    #@1bb
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isTopActivityNoDisplay:Z

    #@1bd
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@1c0
    move-result-object v0

    #@1c1
    const-string v1, " isSleeping="

    #@1c3
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@1c6
    move-result-object v0

    #@1c7
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isSleeping:Z

    #@1c9
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@1cc
    move-result-object v0

    #@1cd
    const-string v1, " locusId="

    #@1cf
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@1d2
    move-result-object v0

    #@1d3
    iget-object v1, p0, Landroid/app/TaskInfo;->mTopActivityLocusId:Landroid/content/LocusId;

    #@1d5
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@1d8
    move-result-object v0

    #@1d9
    const-string v1, " displayAreaFeatureId="

    #@1db
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@1de
    move-result-object v0

    #@1df
    iget v1, p0, Landroid/app/TaskInfo;->displayAreaFeatureId:I

    #@1e1
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@1e4
    move-result-object v0

    #@1e5
    const-string v1, " isTopActivityTransparent="

    #@1e7
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@1ea
    move-result-object v0

    #@1eb
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isTopActivityTransparent:Z

    #@1ed
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@1f0
    move-result-object v0

    #@1f1
    const-string v1, " isActivityStackTransparent="

    #@1f3
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@1f6
    move-result-object v0

    #@1f7
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isActivityStackTransparent:Z

    #@1f9
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@1fc
    move-result-object v0

    #@1fd
    const-string v1, " lastNonFullscreenBounds="

    #@1ff
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@202
    move-result-object v0

    #@203
    iget-object v1, p0, Landroid/app/TaskInfo;->lastNonFullscreenBounds:Landroid/graphics/Rect;

    #@205
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@208
    move-result-object v0

    #@209
    const-string v1, " leafTaskBoundsFromOptions= "

    #@20b
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@20e
    move-result-object v0

    #@20f
    iget-boolean v1, p0, Landroid/app/TaskInfo;->leafTaskBoundsFromOptions:Z

    #@211
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@214
    move-result-object v0

    #@215
    const-string v1, " capturedLink="

    #@217
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@21a
    move-result-object v0

    #@21b
    iget-object v1, p0, Landroid/app/TaskInfo;->capturedLink:Landroid/net/Uri;

    #@21d
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@220
    move-result-object v0

    #@221
    const-string v1, " capturedLinkTimestamp="

    #@223
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@226
    move-result-object v0

    #@227
    iget-wide v1, p0, Landroid/app/TaskInfo;->capturedLinkTimestamp:J

    #@229
    invoke-virtual {v0, v1, v2}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    #@22c
    move-result-object v0

    #@22d
    const-string v1, " requestedVisibleTypes="

    #@22f
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@232
    move-result-object v0

    #@233
    iget v1, p0, Landroid/app/TaskInfo;->requestedVisibleTypes:I

    #@235
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    #@238
    move-result-object v0

    #@239
    const-string v1, " topActivityRequestOpenInBrowserEducationTimestamp="

    #@23b
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@23e
    move-result-object v0

    #@23f
    iget-wide v1, p0, Landroid/app/TaskInfo;->topActivityRequestOpenInBrowserEducationTimestamp:J

    #@241
    invoke-virtual {v0, v1, v2}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    #@244
    move-result-object v0

    #@245
    const-string v1, " appCompatTaskInfo="

    #@247
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@24a
    move-result-object v0

    #@24b
    iget-object v1, p0, Landroid/app/TaskInfo;->appCompatTaskInfo:Landroid/app/AppCompatTaskInfo;

    #@24d
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@250
    move-result-object v0

    #@251
    const-string v1, " topActivityMainWindowFrame="

    #@253
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@256
    move-result-object v0

    #@257
    iget-object v1, p0, Landroid/app/TaskInfo;->topActivityMainWindowFrame:Landroid/graphics/Rect;

    #@259
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    #@25c
    move-result-object v0

    #@25d
    const-string v1, " isAppBubble="

    #@25f
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@262
    move-result-object v0

    #@263
    iget-boolean v1, p0, Landroid/app/TaskInfo;->isAppBubble:Z

    #@265
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;

    #@268
    move-result-object v0

    #@269
    const-string/jumbo v1, "}"

    #@26c
    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    #@26f
    move-result-object v0

    #@270
    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@273
    move-result-object v0

    #@274
    return-object v0
.end method
