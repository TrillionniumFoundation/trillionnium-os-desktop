.method private synthetic lambda$onReceive$0(Landroid/content/Context;Landroid/content/ContentResolver;Landroid/content/BroadcastReceiver$PendingResult;)V
    .registers 4

    .line 70
    invoke-static {p1}, Lcom/android/providers/calendar/CalendarReceiver;->setCalendarCheckAlarm(Landroid/content/Context;)V

    .line 71
    invoke-static {p2}, Lcom/android/providers/calendar/CalendarReceiver;->removeScheduledAlarms(Landroid/content/ContentResolver;)V

    .line 72
    invoke-virtual {p3}, Landroid/content/BroadcastReceiver$PendingResult;->finish()V

    .line 73
    iget-object p0, p0, Lcom/android/providers/calendar/CalendarReceiver;->mWakeLock:Landroid/os/PowerManager$WakeLock;

    invoke-virtual {p0}, Landroid/os/PowerManager$WakeLock;->release()V

    return-void
.end method

