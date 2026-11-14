.method public setIntent(Lcom/android/server/wm/ActivityRecord;Landroid/content/Intent;Landroid/content/pm/ActivityInfo;)V
    .registers 9

    #@0
    .line 1018
    iget-object v0, p0, Lcom/android/server/wm/Task;->intent:Landroid/content/Intent;

    #@2
    const/4 v1, 0x1

    #@3
    if-nez v0, :cond_6

    #@5
    goto :goto_23

    #@6
    .line 1020
    :cond_6
    iget-boolean v0, p0, Lcom/android/server/wm/Task;->mNeverRelinquishIdentity:Z

    #@8
    const/4 v2, 0x0

    #@9
    if-nez v0, :cond_22

    #@b
    if-eqz p3, :cond_f

    #@d
    move-object v0, p3

    #@e
    goto :goto_11

    #@f
    .line 1021
    :cond_f
    iget-object v0, p1, Lcom/android/server/wm/ActivityRecord;->info:Landroid/content/pm/ActivityInfo;

    #@11
    .line 1022
    :goto_11
    iget v3, p0, Lcom/android/server/wm/Task;->effectiveUid:I

    #@13
    const/16 v4, 0x3e8

    #@15
    if-eq v3, v4, :cond_23

    #@17
    iget-boolean v4, p0, Lcom/android/server/wm/Task;->mIsEffectivelySystemApp:Z

    #@19
    if-nez v4, :cond_23

    #@1b
    .line 1023
    invoke-virtual {v0}, Landroid/content/pm/ActivityInfo;->getUid()I

    #@1e
    move-result v0

    #@1f
    if-ne v3, v0, :cond_22

    #@21
    goto :goto_23

    #@22
    :cond_22
    move v1, v2

    #@23
    :cond_23
    :goto_23
    if-eqz v1, :cond_3e

    #@25
    .line 1026
    iget v0, p1, Lcom/android/server/wm/ActivityRecord;->launchedFromUid:I

    #@27
    iput v0, p0, Lcom/android/server/wm/Task;->mCallingUid:I

    #@29
    .line 1027
    iget-object v0, p1, Lcom/android/server/wm/ActivityRecord;->launchedFromPackage:Ljava/lang/String;

    #@2b
    iput-object v0, p0, Lcom/android/server/wm/Task;->mCallingPackage:Ljava/lang/String;

    #@2d
    .line 1028
    iget-object v0, p1, Lcom/android/server/wm/ActivityRecord;->launchedFromFeatureId:Ljava/lang/String;

    #@2f
    iput-object v0, p0, Lcom/android/server/wm/Task;->mCallingFeatureId:Ljava/lang/String;

    #@31
    if-eqz p2, :cond_34

    #@33
    goto :goto_36

    #@34
    .line 1029
    :cond_34
    iget-object p2, p1, Lcom/android/server/wm/ActivityRecord;->intent:Landroid/content/Intent;

    #@36
    :goto_36
    if-eqz p3, :cond_39

    #@38
    goto :goto_3b

    #@39
    :cond_39
    iget-object p3, p1, Lcom/android/server/wm/ActivityRecord;->info:Landroid/content/pm/ActivityInfo;

    #@3b
    :goto_3b
    invoke-virtual {p0, p2, p3}, Lcom/android/server/wm/Task;->setIntent(Landroid/content/Intent;Landroid/content/pm/ActivityInfo;)V

    #@3e
    :cond_3e
    if-eqz p1, :cond_43

    #@40
    .line 1035
    invoke-virtual {p0, p1, v1}, Lcom/android/server/wm/Task;->updateAppCompatProperties(Lcom/android/server/wm/ActivityRecord;Z)V

    #@43
    .line 1037
    :cond_43
    invoke-virtual {p0, p1}, Lcom/android/server/wm/Task;->setLockTaskAuth(Lcom/android/server/wm/ActivityRecord;)V

    #@46
    return-void
.end method
