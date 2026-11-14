.method public setIntent(Lcom/android/server/wm/ActivityRecord;)V
    .registers 3

    #@0
    const/4 v0, 0x0

    #@1
    .line 1006
    invoke-virtual {p0, p1, v0, v0}, Lcom/android/server/wm/Task;->setIntent(Lcom/android/server/wm/ActivityRecord;Landroid/content/Intent;Landroid/content/pm/ActivityInfo;)V

    #@4
    return-void
.end method
