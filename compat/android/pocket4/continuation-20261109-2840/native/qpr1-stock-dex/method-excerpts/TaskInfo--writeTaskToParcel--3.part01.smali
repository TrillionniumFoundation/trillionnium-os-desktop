.method public blacklist writeTaskToParcel(Landroid/os/Parcel;I)V
    .registers 5
    .param p1, "dest"    # Landroid/os/Parcel;
    .param p2, "flags"    # I

    #@0
    .line 771
    iget v0, p0, Landroid/app/TaskInfo;->userId:I

    #@2
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@5
    .line 772
    iget v0, p0, Landroid/app/TaskInfo;->taskId:I

    #@7
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@a
    .line 773
    iget v0, p0, Landroid/app/TaskInfo;->effectiveUid:I

    #@c
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@f
    .line 774
    iget v0, p0, Landroid/app/TaskInfo;->seqId:I

    #@11
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@14
    .line 775
    iget v0, p0, Landroid/app/TaskInfo;->displayId:I

    #@16
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@19
    .line 776
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isRunning:Z

    #@1b
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@1e
    .line 777
    iget-object v0, p0, Landroid/app/TaskInfo;->baseIntent:Landroid/content/Intent;

    #@20
    const/4 v1, 0x0

    #@21
    invoke-virtual {p1, v0, v1}, Landroid/os/Parcel;->writeTypedObject(Landroid/os/Parcelable;I)V

    #@24
    .line 779
    iget-object v0, p0, Landroid/app/TaskInfo;->baseActivity:Landroid/content/ComponentName;

    #@26
    invoke-static {v0, p1}, Landroid/content/ComponentName;->writeToParcel(Landroid/content/ComponentName;Landroid/os/Parcel;)V

    #@29
    .line 780
    iget-object v0, p0, Landroid/app/TaskInfo;->topActivity:Landroid/content/ComponentName;

    #@2b
    invoke-static {v0, p1}, Landroid/content/ComponentName;->writeToParcel(Landroid/content/ComponentName;Landroid/os/Parcel;)V

    #@2e
    .line 781
    iget-object v0, p0, Landroid/app/TaskInfo;->origActivity:Landroid/content/ComponentName;

    #@30
    invoke-static {v0, p1}, Landroid/content/ComponentName;->writeToParcel(Landroid/content/ComponentName;Landroid/os/Parcel;)V

    #@33
    .line 782
    iget-object v0, p0, Landroid/app/TaskInfo;->realActivity:Landroid/content/ComponentName;

    #@35
    invoke-static {v0, p1}, Landroid/content/ComponentName;->writeToParcel(Landroid/content/ComponentName;Landroid/os/Parcel;)V

    #@38
    .line 783
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isRealActivityAppLockEnabled:Z

    #@3a
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@3d
    .line 785
    iget v0, p0, Landroid/app/TaskInfo;->numActivities:I

    #@3f
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@42
    .line 786
    iget-wide v0, p0, Landroid/app/TaskInfo;->lastActiveTime:J

    #@44
    invoke-virtual {p1, v0, v1}, Landroid/os/Parcel;->writeLong(J)V

    #@47
    .line 788
    iget-object v0, p0, Landroid/app/TaskInfo;->taskDescription:Landroid/app/ActivityManager$TaskDescription;

    #@49
    invoke-virtual {p1, v0, p2}, Landroid/os/Parcel;->writeTypedObject(Landroid/os/Parcelable;I)V

    #@4c
    .line 789
    iget-boolean v0, p0, Landroid/app/TaskInfo;->supportsMultiWindow:Z

    #@4e
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@51
    .line 790
    iget-boolean v0, p0, Landroid/app/TaskInfo;->supportsMultiWindowWithoutConstraints:Z

    #@53
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@56
    .line 791
    iget v0, p0, Landroid/app/TaskInfo;->resizeMode:I

    #@58
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@5b
    .line 792
    iget-object v0, p0, Landroid/app/TaskInfo;->configuration:Landroid/content/res/Configuration;

    #@5d
    invoke-virtual {v0, p1, p2}, Landroid/content/res/Configuration;->writeToParcel(Landroid/os/Parcel;I)V

    #@60
    .line 793
    iget-object v0, p0, Landroid/app/TaskInfo;->token:Landroid/window/WindowContainerToken;

    #@62
    invoke-virtual {v0, p1, p2}, Landroid/window/WindowContainerToken;->writeToParcel(Landroid/os/Parcel;I)V

    #@65
    .line 794
    iget v0, p0, Landroid/app/TaskInfo;->topActivityType:I

    #@67
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@6a
    .line 795
    iget-object v0, p0, Landroid/app/TaskInfo;->pictureInPictureParams:Landroid/app/PictureInPictureParams;

    #@6c
    invoke-virtual {p1, v0, p2}, Landroid/os/Parcel;->writeTypedObject(Landroid/os/Parcelable;I)V

    #@6f
    .line 796
    iget-boolean v0, p0, Landroid/app/TaskInfo;->shouldDockBigOverlays:Z

    #@71
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@74
    .line 797
    iget v0, p0, Landroid/app/TaskInfo;->launchIntoPipHostTaskId:I

    #@76
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@79
    .line 798
    iget v0, p0, Landroid/app/TaskInfo;->lastParentTaskIdBeforePip:I

    #@7b
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@7e
    .line 799
    iget-object v0, p0, Landroid/app/TaskInfo;->displayCutoutInsets:Landroid/graphics/Rect;

    #@80
    invoke-virtual {p1, v0, p2}, Landroid/os/Parcel;->writeTypedObject(Landroid/os/Parcelable;I)V

    #@83
    .line 800
    iget-object v0, p0, Landroid/app/TaskInfo;->topActivityInfo:Landroid/content/pm/ActivityInfo;

    #@85
    invoke-virtual {p1, v0, p2}, Landroid/os/Parcel;->writeTypedObject(Landroid/os/Parcelable;I)V

    #@88
    .line 801
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isResizeable:Z

    #@8a
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@8d
    .line 802
    iget v0, p0, Landroid/app/TaskInfo;->minWidth:I

    #@8f
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@92
    .line 803
    iget v0, p0, Landroid/app/TaskInfo;->minHeight:I

    #@94
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@97
    .line 804
    iget v0, p0, Landroid/app/TaskInfo;->defaultMinSize:I

    #@99
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@9c
    .line 805
    iget-object v0, p0, Landroid/app/TaskInfo;->launchCookies:Ljava/util/ArrayList;

    #@9e
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBinderList(Ljava/util/List;)V

    #@a1
    .line 806
    iget-object v0, p0, Landroid/app/TaskInfo;->positionInParent:Landroid/graphics/Point;

    #@a3
    invoke-virtual {p1, v0, p2}, Landroid/os/Parcel;->writeTypedObject(Landroid/os/Parcelable;I)V

    #@a6
    .line 807
    iget v0, p0, Landroid/app/TaskInfo;->parentTaskId:I

    #@a8
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@ab
    .line 808
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isFocused:Z

    #@ad
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@b0
    .line 809
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isVisible:Z

    #@b2
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@b5
    .line 810
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isVisibleRequested:Z

    #@b7
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@ba
    .line 811
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isTopActivityNoDisplay:Z

    #@bc
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@bf
    .line 812
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isSleeping:Z

    #@c1
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@c4
    .line 813
    iget-object v0, p0, Landroid/app/TaskInfo;->mTopActivityLocusId:Landroid/content/LocusId;

    #@c6
    invoke-virtual {p1, v0, p2}, Landroid/os/Parcel;->writeTypedObject(Landroid/os/Parcelable;I)V

    #@c9
    .line 814
    iget v0, p0, Landroid/app/TaskInfo;->displayAreaFeatureId:I

    #@cb
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@ce
    .line 815
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isTopActivityTransparent:Z

    #@d0
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@d3
    .line 816
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isActivityStackTransparent:Z

    #@d5
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@d8
    .line 817
    iget-object v0, p0, Landroid/app/TaskInfo;->lastNonFullscreenBounds:Landroid/graphics/Rect;

    #@da
    invoke-virtual {p1, v0, p2}, Landroid/os/Parcel;->writeTypedObject(Landroid/os/Parcelable;I)V

    #@dd
    .line 818
    iget-boolean v0, p0, Landroid/app/TaskInfo;->leafTaskBoundsFromOptions:Z

    #@df
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@e2
    .line 819
    iget-object v0, p0, Landroid/app/TaskInfo;->capturedLink:Landroid/net/Uri;

    #@e4
    invoke-virtual {p1, v0, p2}, Landroid/os/Parcel;->writeTypedObject(Landroid/os/Parcelable;I)V

    #@e7
    .line 820
    iget-wide v0, p0, Landroid/app/TaskInfo;->capturedLinkTimestamp:J

    #@e9
    invoke-virtual {p1, v0, v1}, Landroid/os/Parcel;->writeLong(J)V

    #@ec
    .line 821
    iget v0, p0, Landroid/app/TaskInfo;->requestedVisibleTypes:I

    #@ee
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@f1
    .line 822
    iget-wide v0, p0, Landroid/app/TaskInfo;->topActivityRequestOpenInBrowserEducationTimestamp:J

    #@f3
    invoke-virtual {p1, v0, v1}, Landroid/os/Parcel;->writeLong(J)V

    #@f6
    .line 823
    iget-object v0, p0, Landroid/app/TaskInfo;->appCompatTaskInfo:Landroid/app/AppCompatTaskInfo;

    #@f8
    invoke-virtual {p1, v0, p2}, Landroid/os/Parcel;->writeTypedObject(Landroid/os/Parcelable;I)V

    #@fb
    .line 824
    iget-object v0, p0, Landroid/app/TaskInfo;->topActivityMainWindowFrame:Landroid/graphics/Rect;

    #@fd
    invoke-virtual {p1, v0, p2}, Landroid/os/Parcel;->writeTypedObject(Landroid/os/Parcelable;I)V

    #@100
    .line 825
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isAppBubble:Z

    #@102
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@105
    .line 826
    iget-boolean v0, p0, Landroid/app/TaskInfo;->isInteractive:Z

    #@107
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeBoolean(Z)V

    #@10a
    .line 827
    return-void
.end method
