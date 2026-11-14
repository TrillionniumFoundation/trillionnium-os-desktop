.method blacklist readTaskFromParcel(Landroid/os/Parcel;)V
    .registers 4
    .param p1, "source"    # Landroid/os/Parcel;

    #@0
    .line 711
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@3
    move-result v0

    #@4
    iput v0, p0, Landroid/app/TaskInfo;->userId:I

    #@6
    .line 712
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@9
    move-result v0

    #@a
    iput v0, p0, Landroid/app/TaskInfo;->taskId:I

    #@c
    .line 713
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@f
    move-result v0

    #@10
    iput v0, p0, Landroid/app/TaskInfo;->effectiveUid:I

    #@12
    .line 714
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@15
    move-result v0

    #@16
    iput v0, p0, Landroid/app/TaskInfo;->seqId:I

    #@18
    .line 715
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@1b
    move-result v0

    #@1c
    iput v0, p0, Landroid/app/TaskInfo;->displayId:I

    #@1e
    .line 716
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@21
    move-result v0

    #@22
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isRunning:Z

    #@24
    .line 717
    sget-object v0, Landroid/content/Intent;->CREATOR:Landroid/os/Parcelable$Creator;

    #@26
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readTypedObject(Landroid/os/Parcelable$Creator;)Ljava/lang/Object;

    #@29
    move-result-object v0

    #@2a
    check-cast v0, Landroid/content/Intent;

    #@2c
    iput-object v0, p0, Landroid/app/TaskInfo;->baseIntent:Landroid/content/Intent;

    #@2e
    .line 718
    invoke-static {p1}, Landroid/content/ComponentName;->readFromParcel(Landroid/os/Parcel;)Landroid/content/ComponentName;

    #@31
    move-result-object v0

    #@32
    iput-object v0, p0, Landroid/app/TaskInfo;->baseActivity:Landroid/content/ComponentName;

    #@34
    .line 719
    invoke-static {p1}, Landroid/content/ComponentName;->readFromParcel(Landroid/os/Parcel;)Landroid/content/ComponentName;

    #@37
    move-result-object v0

    #@38
    iput-object v0, p0, Landroid/app/TaskInfo;->topActivity:Landroid/content/ComponentName;

    #@3a
    .line 720
    invoke-static {p1}, Landroid/content/ComponentName;->readFromParcel(Landroid/os/Parcel;)Landroid/content/ComponentName;

    #@3d
    move-result-object v0

    #@3e
    iput-object v0, p0, Landroid/app/TaskInfo;->origActivity:Landroid/content/ComponentName;

    #@40
    .line 721
    invoke-static {p1}, Landroid/content/ComponentName;->readFromParcel(Landroid/os/Parcel;)Landroid/content/ComponentName;

    #@43
    move-result-object v0

    #@44
    iput-object v0, p0, Landroid/app/TaskInfo;->realActivity:Landroid/content/ComponentName;

    #@46
    .line 722
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@49
    move-result v0

    #@4a
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isRealActivityAppLockEnabled:Z

    #@4c
    .line 723
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@4f
    move-result v0

    #@50
    iput v0, p0, Landroid/app/TaskInfo;->numActivities:I

    #@52
    .line 724
    invoke-virtual {p1}, Landroid/os/Parcel;->readLong()J

    #@55
    move-result-wide v0

    #@56
    iput-wide v0, p0, Landroid/app/TaskInfo;->lastActiveTime:J

    #@58
    .line 725
    sget-object v0, Landroid/app/ActivityManager$TaskDescription;->CREATOR:Landroid/os/Parcelable$Creator;

    #@5a
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readTypedObject(Landroid/os/Parcelable$Creator;)Ljava/lang/Object;

    #@5d
    move-result-object v0

    #@5e
    check-cast v0, Landroid/app/ActivityManager$TaskDescription;

    #@60
    iput-object v0, p0, Landroid/app/TaskInfo;->taskDescription:Landroid/app/ActivityManager$TaskDescription;

    #@62
    .line 726
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@65
    move-result v0

    #@66
    iput-boolean v0, p0, Landroid/app/TaskInfo;->supportsMultiWindow:Z

    #@68
    .line 727
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@6b
    move-result v0

    #@6c
    iput-boolean v0, p0, Landroid/app/TaskInfo;->supportsMultiWindowWithoutConstraints:Z

    #@6e
    .line 728
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@71
    move-result v0

    #@72
    iput v0, p0, Landroid/app/TaskInfo;->resizeMode:I

    #@74
    .line 729
    iget-object v0, p0, Landroid/app/TaskInfo;->configuration:Landroid/content/res/Configuration;

    #@76
    invoke-virtual {v0, p1}, Landroid/content/res/Configuration;->readFromParcel(Landroid/os/Parcel;)V

    #@79
    .line 730
    sget-object v0, Landroid/window/WindowContainerToken;->CREATOR:Landroid/os/Parcelable$Creator;

    #@7b
    invoke-interface {v0, p1}, Landroid/os/Parcelable$Creator;->createFromParcel(Landroid/os/Parcel;)Ljava/lang/Object;

    #@7e
    move-result-object v0

    #@7f
    check-cast v0, Landroid/window/WindowContainerToken;

    #@81
    iput-object v0, p0, Landroid/app/TaskInfo;->token:Landroid/window/WindowContainerToken;

    #@83
    .line 731
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@86
    move-result v0

    #@87
    iput v0, p0, Landroid/app/TaskInfo;->topActivityType:I

    #@89
    .line 732
    sget-object v0, Landroid/app/PictureInPictureParams;->CREATOR:Landroid/os/Parcelable$Creator;

    #@8b
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readTypedObject(Landroid/os/Parcelable$Creator;)Ljava/lang/Object;

    #@8e
    move-result-object v0

    #@8f
    check-cast v0, Landroid/app/PictureInPictureParams;

    #@91
    iput-object v0, p0, Landroid/app/TaskInfo;->pictureInPictureParams:Landroid/app/PictureInPictureParams;

    #@93
    .line 733
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@96
    move-result v0

    #@97
    iput-boolean v0, p0, Landroid/app/TaskInfo;->shouldDockBigOverlays:Z

    #@99
    .line 734
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@9c
    move-result v0

    #@9d
    iput v0, p0, Landroid/app/TaskInfo;->launchIntoPipHostTaskId:I

    #@9f
    .line 735
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@a2
    move-result v0

    #@a3
    iput v0, p0, Landroid/app/TaskInfo;->lastParentTaskIdBeforePip:I

    #@a5
    .line 736
    sget-object v0, Landroid/graphics/Rect;->CREATOR:Landroid/os/Parcelable$Creator;

    #@a7
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readTypedObject(Landroid/os/Parcelable$Creator;)Ljava/lang/Object;

    #@aa
    move-result-object v0

    #@ab
    check-cast v0, Landroid/graphics/Rect;

    #@ad
    iput-object v0, p0, Landroid/app/TaskInfo;->displayCutoutInsets:Landroid/graphics/Rect;

    #@af
    .line 737
    sget-object v0, Landroid/content/pm/ActivityInfo;->CREATOR:Landroid/os/Parcelable$Creator;

    #@b1
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readTypedObject(Landroid/os/Parcelable$Creator;)Ljava/lang/Object;

    #@b4
    move-result-object v0

    #@b5
    check-cast v0, Landroid/content/pm/ActivityInfo;

    #@b7
    iput-object v0, p0, Landroid/app/TaskInfo;->topActivityInfo:Landroid/content/pm/ActivityInfo;

    #@b9
    .line 738
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@bc
    move-result v0

    #@bd
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isResizeable:Z

    #@bf
    .line 739
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@c2
    move-result v0

    #@c3
    iput v0, p0, Landroid/app/TaskInfo;->minWidth:I

    #@c5
    .line 740
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@c8
    move-result v0

    #@c9
    iput v0, p0, Landroid/app/TaskInfo;->minHeight:I

    #@cb
    .line 741
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@ce
    move-result v0

    #@cf
    iput v0, p0, Landroid/app/TaskInfo;->defaultMinSize:I

    #@d1
    .line 742
    iget-object v0, p0, Landroid/app/TaskInfo;->launchCookies:Ljava/util/ArrayList;

    #@d3
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readBinderList(Ljava/util/List;)V

    #@d6
    .line 743
    sget-object v0, Landroid/graphics/Point;->CREATOR:Landroid/os/Parcelable$Creator;

    #@d8
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readTypedObject(Landroid/os/Parcelable$Creator;)Ljava/lang/Object;

    #@db
    move-result-object v0

    #@dc
    check-cast v0, Landroid/graphics/Point;

    #@de
    iput-object v0, p0, Landroid/app/TaskInfo;->positionInParent:Landroid/graphics/Point;

    #@e0
    .line 744
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@e3
    move-result v0

    #@e4
    iput v0, p0, Landroid/app/TaskInfo;->parentTaskId:I

    #@e6
    .line 745
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@e9
    move-result v0

    #@ea
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isFocused:Z

    #@ec
    .line 746
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@ef
    move-result v0

    #@f0
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isVisible:Z

    #@f2
    .line 747
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@f5
    move-result v0

    #@f6
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isVisibleRequested:Z

    #@f8
    .line 748
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@fb
    move-result v0

    #@fc
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isTopActivityNoDisplay:Z

    #@fe
    .line 749
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@101
    move-result v0

    #@102
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isSleeping:Z

    #@104
    .line 750
    sget-object v0, Landroid/content/LocusId;->CREATOR:Landroid/os/Parcelable$Creator;

    #@106
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readTypedObject(Landroid/os/Parcelable$Creator;)Ljava/lang/Object;

    #@109
    move-result-object v0

    #@10a
    check-cast v0, Landroid/content/LocusId;

    #@10c
    iput-object v0, p0, Landroid/app/TaskInfo;->mTopActivityLocusId:Landroid/content/LocusId;

    #@10e
    .line 751
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@111
    move-result v0

    #@112
    iput v0, p0, Landroid/app/TaskInfo;->displayAreaFeatureId:I

    #@114
    .line 752
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@117
    move-result v0

    #@118
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isTopActivityTransparent:Z

    #@11a
    .line 753
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@11d
    move-result v0

    #@11e
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isActivityStackTransparent:Z

    #@120
    .line 754
    sget-object v0, Landroid/graphics/Rect;->CREATOR:Landroid/os/Parcelable$Creator;

    #@122
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readTypedObject(Landroid/os/Parcelable$Creator;)Ljava/lang/Object;

    #@125
    move-result-object v0

    #@126
    check-cast v0, Landroid/graphics/Rect;

    #@128
    iput-object v0, p0, Landroid/app/TaskInfo;->lastNonFullscreenBounds:Landroid/graphics/Rect;

    #@12a
    .line 755
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@12d
    move-result v0

    #@12e
    iput-boolean v0, p0, Landroid/app/TaskInfo;->leafTaskBoundsFromOptions:Z

    #@130
    .line 756
    sget-object v0, Landroid/net/Uri;->CREATOR:Landroid/os/Parcelable$Creator;

    #@132
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readTypedObject(Landroid/os/Parcelable$Creator;)Ljava/lang/Object;

    #@135
    move-result-object v0

    #@136
    check-cast v0, Landroid/net/Uri;

    #@138
    iput-object v0, p0, Landroid/app/TaskInfo;->capturedLink:Landroid/net/Uri;

    #@13a
    .line 757
    invoke-virtual {p1}, Landroid/os/Parcel;->readLong()J

    #@13d
    move-result-wide v0

    #@13e
    iput-wide v0, p0, Landroid/app/TaskInfo;->capturedLinkTimestamp:J

    #@140
    .line 758
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@143
    move-result v0

    #@144
    iput v0, p0, Landroid/app/TaskInfo;->requestedVisibleTypes:I

    #@146
    .line 759
    invoke-virtual {p1}, Landroid/os/Parcel;->readLong()J

    #@149
    move-result-wide v0

    #@14a
    iput-wide v0, p0, Landroid/app/TaskInfo;->topActivityRequestOpenInBrowserEducationTimestamp:J

    #@14c
    .line 760
    sget-object v0, Landroid/app/AppCompatTaskInfo;->CREATOR:Landroid/os/Parcelable$Creator;

    #@14e
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readTypedObject(Landroid/os/Parcelable$Creator;)Ljava/lang/Object;

    #@151
    move-result-object v0

    #@152
    check-cast v0, Landroid/app/AppCompatTaskInfo;

    #@154
    iput-object v0, p0, Landroid/app/TaskInfo;->appCompatTaskInfo:Landroid/app/AppCompatTaskInfo;

    #@156
    .line 761
    sget-object v0, Landroid/graphics/Rect;->CREATOR:Landroid/os/Parcelable$Creator;

    #@158
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->readTypedObject(Landroid/os/Parcelable$Creator;)Ljava/lang/Object;

    #@15b
    move-result-object v0

    #@15c
    check-cast v0, Landroid/graphics/Rect;

    #@15e
    iput-object v0, p0, Landroid/app/TaskInfo;->topActivityMainWindowFrame:Landroid/graphics/Rect;

    #@160
    .line 762
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@163
    move-result v0

    #@164
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isAppBubble:Z

    #@166
    .line 763
    invoke-virtual {p1}, Landroid/os/Parcel;->readBoolean()Z

    #@169
    move-result v0

    #@16a
    iput-boolean v0, p0, Landroid/app/TaskInfo;->isInteractive:Z

    #@16c
    .line 764
    return-void
.end method
