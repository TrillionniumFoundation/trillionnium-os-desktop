.method public onReceive(Landroid/content/Context;Landroid/content/Intent;)V
    .registers 6

    .line 49
    invoke-virtual {p2}, Landroid/content/Intent;->getAction()Ljava/lang/String;

    move-result-object p2

    .line 51
    const-string v0, "android.intent.action.BOOT_COMPLETED"

    invoke-virtual {v0, p2}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v0

    const-string v1, "CalendarProvider2"

    if-nez v0, :cond_20

    .line 52
    new-instance p0, Ljava/lang/StringBuilder;

    const-string p1, "Unexpected broadcast: "

    invoke-direct {p0, p1}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {p0, p2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {p0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p0

    invoke-static {v1, p0}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;)I

    return-void

    :cond_20
    const/4 p2, 0x3

    .line 55
    invoke-static {v1, p2}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result p2

    if-eqz p2, :cond_2c

    .line 56
    const-string p2, "BOOT_COMPLETED"

    invoke-static {v1, p2}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    .line 59
    :cond_2c
    iget-object p2, p0, Lcom/android/providers/calendar/CalendarReceiver;->mWakeLock:Landroid/os/PowerManager$WakeLock;

    if-nez p2, :cond_44

    .line 60
    const-string p2, "power"

    invoke-virtual {p1, p2}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object p2

    check-cast p2, Landroid/os/PowerManager;

    .line 61
    const-string v0, "CalendarReceiver_Provider"

    const/4 v1, 0x1

    invoke-virtual {p2, v1, v0}, Landroid/os/PowerManager;->newWakeLock(ILjava/lang/String;)Landroid/os/PowerManager$WakeLock;

    move-result-object p2

    iput-object p2, p0, Lcom/android/providers/calendar/CalendarReceiver;->mWakeLock:Landroid/os/PowerManager$WakeLock;

    .line 62
    invoke-virtual {p2, v1}, Landroid/os/PowerManager$WakeLock;->setReferenceCounted(Z)V

    .line 64
    :cond_44
    iget-object p2, p0, Lcom/android/providers/calendar/CalendarReceiver;->mWakeLock:Landroid/os/PowerManager$WakeLock;

    invoke-virtual {p2}, Landroid/os/PowerManager$WakeLock;->acquire()V

    .line 66
    invoke-virtual {p1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object p2

    .line 67
    invoke-virtual {p0}, Landroid/content/BroadcastReceiver;->goAsync()Landroid/content/BroadcastReceiver$PendingResult;

    move-result-object v0

    .line 69
    new-instance v1, Ljava/lang/Thread;

    new-instance v2, Lcom/android/providers/calendar/CalendarReceiver$$ExternalSyntheticLambda0;

    invoke-direct {v2, p0, p1, p2, v0}, Lcom/android/providers/calendar/CalendarReceiver$$ExternalSyntheticLambda0;-><init>(Lcom/android/providers/calendar/CalendarReceiver;Landroid/content/Context;Landroid/content/ContentResolver;Landroid/content/BroadcastReceiver$PendingResult;)V

    invoke-direct {v1, v2}, Ljava/lang/Thread;-><init>(Ljava/lang/Runnable;)V

    .line 74
    invoke-virtual {v1}, Ljava/lang/Thread;->start()V

    return-void
.end method

