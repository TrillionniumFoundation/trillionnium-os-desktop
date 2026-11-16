.method public final makeIntent(I)Landroid/content/Intent;
    .registers 6

    #@0
    const/4 v0, 0x0

    #@1
    .line 623
    iput v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mStartFlags:I

    #@3
    .line 624
    iput-boolean v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mWaitOption:Z

    #@5
    .line 625
    iput-boolean v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mStopOption:Z

    #@7
    .line 626
    iput v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mRepeat:I

    #@9
    const/4 v1, 0x0

    #@a
    .line 627
    iput-object v1, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mProfileFile:Ljava/lang/String;

    #@c
    .line 628
    iput v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mSamplingInterval:I

    #@e
    .line 629
    iput-boolean v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mAutoStop:Z

    #@10
    .line 630
    iput-boolean v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mStreaming:Z

    #@12
    .line 631
    iput-boolean v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mLongRunningMethods:Z

    #@14
    const-wide/16 v2, 0x0

    #@16
    .line 632
    iput-wide v2, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mDurationMicros:J

    #@18
    .line 633
    iput p1, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mUserId:I

    #@1a
    const/4 p1, -0x1

    #@1b
    .line 634
    iput p1, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mDisplayId:I

    #@1d
    .line 635
    iput p1, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mTaskDisplayAreaFeatureId:I

    #@1f
    .line 636
    iput v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mWindowingMode:I

    #@21
    .line 637
    iput v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mActivityType:I

    #@23
    .line 638
    iput p1, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mTaskId:I

    #@25
    .line 639
    iput-boolean v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mIsTaskOverlay:Z

    #@27
    .line 640
    iput-boolean v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mIsLockTask:Z

    #@29
    .line 641
    iput-boolean v0, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mAsync:Z

    #@2b
    .line 642
    iput-object v1, p0, Lcom/android/server/am/ActivityManagerShellCommand;->mBroadcastOptions:Landroid/app/BroadcastOptions;

    #@2d
    .line 644
    new-instance p1, Lcom/android/server/am/ActivityManagerShellCommand$1;

    #@2f
    invoke-direct {p1, p0}, Lcom/android/server/am/ActivityManagerShellCommand$1;-><init>(Lcom/android/server/am/ActivityManagerShellCommand;)V

    #@32
    invoke-static {p0, p1}, Landroid/content/Intent;->parseCommandArgs(Landroid/os/ShellCommand;Landroid/content/Intent$CommandOptionHandler;)Landroid/content/Intent;

    #@35
    move-result-object p0

    #@36
    return-object p0
.end method
