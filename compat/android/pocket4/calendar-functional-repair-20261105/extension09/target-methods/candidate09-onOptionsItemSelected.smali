.method public onOptionsItemSelected(Landroid/view/MenuItem;)Z
    .registers 17

    move-object/from16 v2, p0
    move-object/from16 v3, p1
    const/4 v4, 0x0
    iget-object v0, v2, Lcom/android/calendar/AllInOneActivity;->mController:Lcom/android/calendar/CalendarController;
    if-eqz v0, :restored_menu_time_ready
    invoke-virtual {v0}, Lcom/android/calendar/CalendarController;->getTime()Ljava/lang/Long;
    move-result-object v4
    :restored_menu_time_ready
    invoke-static {v2, v3, v4}, Lcom/android/calendar/repair/CalendarActions;->onMenu(Landroid/app/Activity;Landroid/view/MenuItem;Ljava/lang/Long;)Z
    move-result v0
    if-eqz v0, :restored_menu_original
    return v0
    :restored_menu_original

    invoke-virtual/range {p1 .. p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 628
    invoke-interface/range {p1 .. p1}, Landroid/view/MenuItem;->getItemId()I

    move-result v0

    const v2, 0x7f09002b

    const/4 v14, 0x1

    if-eq v0, v2, :cond_44

    const v2, 0x7f090030

    if-eq v0, v2, :cond_26

    .line 652
    new-instance v1, Ljava/lang/StringBuilder;

    const-string v2, "Unsupported itemId: "

    invoke-direct {v1, v2}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v1, v0}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const-string v1, "AllInOneActivity"

    invoke-static {v1, v0}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    return v14

    .line 631
    :cond_26
    new-instance v4, Landroid/text/format/Time;

    iget-object v0, p0, Lcom/android/calendar/AllInOneActivity;->mTimeZone:Ljava/lang/String;

    invoke-direct {v4, v0}, Landroid/text/format/Time;-><init>(Ljava/lang/String;)V

    .line 632
    invoke-virtual {v4}, Landroid/text/format/Time;->setToNow()V

    .line 655
    iget-object v0, p0, Lcom/android/calendar/AllInOneActivity;->mController:Lcom/android/calendar/CalendarController;

    if-eqz v0, :cond_43

    const/4 v12, 0x0

    const/4 v13, 0x0

    const-wide/16 v2, 0x20

    const/4 v5, 0x0

    const-wide/16 v7, -0x1

    const/4 v9, 0x0

    const-wide/16 v10, 0xa

    move-object v6, v4

    move-object v1, p0

    invoke-virtual/range {v0 .. v13}, Lcom/android/calendar/CalendarController;->sendEvent(Ljava/lang/Object;JLandroid/text/format/Time;Landroid/text/format/Time;Landroid/text/format/Time;JIJLjava/lang/String;Landroid/content/ComponentName;)V

    :cond_43
    return v14

    .line 635
    :cond_44
    iget-boolean v0, p0, Lcom/android/calendar/AllInOneActivity;->mHideControls:Z

    xor-int/lit8 v2, v0, 0x1

    iput-boolean v2, p0, Lcom/android/calendar/AllInOneActivity;->mHideControls:Z

    if-nez v0, :cond_51

    .line 636
    iget-object v0, p0, Lcom/android/calendar/AllInOneActivity;->mShowString:Ljava/lang/String;

    :goto_4e
    move-object/from16 v2, p1

    goto :goto_54

    :cond_51
    iget-object v0, p0, Lcom/android/calendar/AllInOneActivity;->mHideString:Ljava/lang/String;

    goto :goto_4e

    :goto_54
    invoke-interface {v2, v0}, Landroid/view/MenuItem;->setTitle(Ljava/lang/CharSequence;)Landroid/view/MenuItem;

    .line 637
    iget-boolean v0, p0, Lcom/android/calendar/AllInOneActivity;->mHideControls:Z

    const/4 v2, 0x0

    if-nez v0, :cond_71

    .line 638
    iget-object v0, p0, Lcom/android/calendar/AllInOneActivity;->mMiniMonth:Landroid/view/View;

    if-eqz v0, :cond_63

    invoke-virtual {v0, v2}, Landroid/view/View;->setVisibility(I)V

    .line 639
    :cond_63
    iget-object v0, p0, Lcom/android/calendar/AllInOneActivity;->mCalendarsList:Landroid/view/View;

    if-eqz v0, :cond_6a

    invoke-virtual {v0, v2}, Landroid/view/View;->setVisibility(I)V

    .line 640
    :cond_6a
    iget-object v0, p0, Lcom/android/calendar/AllInOneActivity;->mMiniMonthContainer:Landroid/view/View;

    if-eqz v0, :cond_71

    invoke-virtual {v0, v2}, Landroid/view/View;->setVisibility(I)V

    .line 644
    :cond_71
    iget-boolean v0, p0, Lcom/android/calendar/AllInOneActivity;->mHideControls:Z

    if-eqz v0, :cond_77

    move v3, v2

    goto :goto_79

    :cond_77
    iget v3, p0, Lcom/android/calendar/AllInOneActivity;->mControlsAnimateWidth:I

    :goto_79
    if-eqz v0, :cond_7d

    .line 645
    iget v2, p0, Lcom/android/calendar/AllInOneActivity;->mControlsAnimateWidth:I

    :cond_7d
    filled-new-array {v3, v2}, [I

    move-result-object v0

    .line 642
    const-string v2, "controlsOffset"

    invoke-static {p0, v2, v0}, Landroid/animation/ObjectAnimator;->ofInt(Ljava/lang/Object;Ljava/lang/String;[I)Landroid/animation/ObjectAnimator;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 647
    iget v1, p0, Lcom/android/calendar/AllInOneActivity;->mCalendarControlsAnimationTime:I

    int-to-long v1, v1

    invoke-virtual {v0, v1, v2}, Landroid/animation/ObjectAnimator;->setDuration(J)Landroid/animation/ObjectAnimator;

    const-wide/16 v1, 0x0

    .line 648
    invoke-static {v1, v2}, Landroid/animation/ObjectAnimator;->setFrameDelay(J)V

    .line 649
    invoke-virtual {v0}, Landroid/animation/ObjectAnimator;->start()V

    return v14
.end method