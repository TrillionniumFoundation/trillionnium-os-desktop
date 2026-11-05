.method private scheduleNextAlarmLocked(Landroid/database/sqlite/SQLiteDatabase;Lcom/android/providers/calendar/CalendarProvider2;)V
    .registers 36

    move-object/from16 v0, p0

    move-object/from16 v1, p1

    move-object/from16 v2, p2

    .line 252
    const-string v11, "cursor results: "

    iget-object v3, v2, Lcom/android/providers/calendar/CalendarProvider2;->mConfidenceChecker:Lcom/android/providers/calendar/CalendarConfidenceChecker;

    invoke-virtual {v3}, Lcom/android/providers/calendar/CalendarConfidenceChecker;->updateLastCheckTime()V

    .line 254
    new-instance v12, Lcom/android/calendarcommon2/Time;

    invoke-direct {v12}, Lcom/android/calendarcommon2/Time;-><init>()V

    .line 256
    invoke-static {}, Ljava/lang/System;->currentTimeMillis()J

    move-result-wide v13

    const-wide/32 v3, 0x6ddd00

    sub-long v3, v13, v3

    const-wide/32 v5, 0x5265c00

    add-long/2addr v5, v13

    .line 262
    const-string v15, "CalendarProvider2"

    const/4 v7, 0x3

    invoke-static {v15, v7}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result v8

    if-eqz v8, :cond_40

    .line 263
    invoke-virtual {v12, v3, v4}, Lcom/android/calendarcommon2/Time;->set(J)V

    .line 264
    invoke-virtual {v12}, Lcom/android/calendarcommon2/Time;->format()Ljava/lang/String;

    move-result-object v8

    .line 265
    new-instance v9, Ljava/lang/StringBuilder;

    const-string v10, "runScheduleNextAlarm() start search: "

    invoke-direct {v9, v10}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v9, v8}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v9}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v8

    invoke-static {v15, v8}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    :cond_40
    const-wide/32 v8, 0x247a6100

    sub-long v8, v13, v8

    .line 274
    invoke-static {v8, v9}, Ljava/lang/Long;->toString(J)Ljava/lang/String;

    move-result-object v8

    filled-new-array {v8}, [Ljava/lang/String;

    move-result-object v8

    .line 277
    const-string v9, "CalendarAlerts"

    const-string v10, "_id IN (SELECT ca._id FROM CalendarAlerts AS ca LEFT OUTER JOIN Instances USING (event_id,begin,end) LEFT OUTER JOIN Reminders AS r ON (ca.event_id=r.event_id AND ca.minutes=r.minutes) LEFT OUTER JOIN view_events AS e ON (ca.event_id=e._id) WHERE Instances.begin ISNULL   OR ca.alarmTime<?   OR (r.minutes ISNULL       AND ca.minutes<>0)   OR e.visible=0)"

    invoke-virtual {v1, v9, v10, v8}, Landroid/database/sqlite/SQLiteDatabase;->delete(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;)I

    move-result v16

    .line 281
    iget-object v8, v0, Lcom/android/providers/calendar/CalendarAlarmManager;->mContext:Landroid/content/Context;

    invoke-virtual {v8}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v8

    .line 282
    invoke-static {v8, v13, v14}, Landroid/provider/CalendarContract$CalendarAlerts;->findNextAlarmTime(Landroid/content/ContentResolver;J)J

    move-result-wide v9

    const-wide/16 v17, -0x1

    cmp-long v17, v9, v17

    if-eqz v17, :cond_6a

    cmp-long v17, v9, v5

    if-gez v17, :cond_6a

    move-wide v5, v9

    .line 309
    :cond_6a
    invoke-static {}, Ljava/lang/System;->currentTimeMillis()J

    move-result-wide v9

    invoke-virtual {v12, v9, v10}, Lcom/android/calendarcommon2/Time;->set(J)V

    .line 310
    invoke-virtual {v12}, Lcom/android/calendarcommon2/Time;->normalize()J

    .line 311
    invoke-virtual {v12}, Lcom/android/calendarcommon2/Time;->getGmtOffset()J

    move-result-wide v9

    const-wide/16 v17, 0x3e8

    mul-long v9, v9, v17

    .line 313
    new-instance v7, Ljava/lang/StringBuilder;

    move-wide/from16 v18, v3

    const-string v3, " -("

    invoke-direct {v7, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v7, v9, v10}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    const-string v3, ") "

    invoke-virtual {v7, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v7}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v3

    .line 331
    new-instance v4, Ljava/lang/StringBuilder;

    const-string v7, "SELECT begin"

    invoke-direct {v4, v7}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v4, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v3, " -(minutes*60000) AS myAlarmTime,Instances.event_id AS eventId,begin,end,title,allDay,method,minutes FROM Instances INNER JOIN view_events ON (view_events._id=Instances.event_id) INNER JOIN Reminders ON (Instances.event_id=Reminders.event_id) WHERE visible=1 AND myAlarmTime>=CAST(? AS INT) AND myAlarmTime<=CAST(? AS INT) AND end>=? AND method=1 AND allDay=1"

    invoke-virtual {v4, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v4}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v3

    .line 338
    new-instance v4, Ljava/lang/StringBuilder;

    const-string v7, "SELECT * FROM ("

    invoke-direct {v4, v7}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v4, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v3, " UNION ALL SELECT begin -(minutes*60000) AS myAlarmTime,Instances.event_id AS eventId,begin,end,title,allDay,method,minutes FROM Instances INNER JOIN view_events ON (view_events._id=Instances.event_id) INNER JOIN Reminders ON (Instances.event_id=Reminders.event_id) WHERE visible=1 AND myAlarmTime>=CAST(? AS INT) AND myAlarmTime<=CAST(? AS INT) AND end>=? AND method=1 AND allDay=0) WHERE 0=(SELECT count(*) FROM CalendarAlerts CA WHERE CA.event_id=eventId AND CA.begin=begin AND CA.alarmTime=myAlarmTime) ORDER BY myAlarmTime,begin,title"

    invoke-virtual {v4, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v4}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v3

    .line 345
    invoke-static/range {v18 .. v19}, Ljava/lang/String;->valueOf(J)Ljava/lang/String;

    move-result-object v20

    invoke-static {v5, v6}, Ljava/lang/String;->valueOf(J)Ljava/lang/String;

    move-result-object v21

    .line 346
    invoke-static {v13, v14}, Ljava/lang/String;->valueOf(J)Ljava/lang/String;

    move-result-object v22

    invoke-static/range {v18 .. v19}, Ljava/lang/String;->valueOf(J)Ljava/lang/String;

    move-result-object v23

    invoke-static {v5, v6}, Ljava/lang/String;->valueOf(J)Ljava/lang/String;

    move-result-object v24

    .line 347
    invoke-static {v13, v14}, Ljava/lang/String;->valueOf(J)Ljava/lang/String;

    move-result-object v25

    filled-new-array/range {v20 .. v25}, [Ljava/lang/String;

    move-result-object v4

    .line 349
    iget-object v7, v2, Lcom/android/providers/calendar/CalendarProvider2;->mCalendarCache:Lcom/android/providers/calendar/CalendarCache;

    invoke-virtual {v7}, Lcom/android/providers/calendar/CalendarCache;->readTimezoneInstances()Ljava/lang/String;

    move-result-object v9

    .line 350
    iget-object v7, v2, Lcom/android/providers/calendar/CalendarProvider2;->mCalendarCache:Lcom/android/providers/calendar/CalendarCache;

    invoke-virtual {v7}, Lcom/android/providers/calendar/CalendarCache;->readTimezoneType()Ljava/lang/String;

    move-result-object v7

    .line 351
    const-string v10, "home"

    invoke-virtual {v10, v7}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v10

    const-wide/32 v18, 0x5943900

    sub-long v18, v13, v18

    const-wide/32 v20, 0xa4cb800

    add-long v20, v13, v20

    const/4 v7, 0x0

    move-object/from16 v22, v8

    const/4 v8, 0x0

    move-object v0, v3

    move-object/from16 v29, v12

    move-wide/from16 v27, v13

    move-object/from16 v17, v22

    const/4 v12, 0x3

    move-wide v13, v5

    move-wide/from16 v5, v20

    move-object/from16 v32, v11

    move-object v11, v4

    move-wide/from16 v3, v18

    move-object/from16 v18, v32

    .line 354
    invoke-virtual/range {v2 .. v10}, Lcom/android/providers/calendar/CalendarProvider2;->acquireInstanceRangeLocked(JJZZLjava/lang/String;Z)V

    .line 366
    :try_start_108
    invoke-virtual {v1, v0, v11}, Landroid/database/sqlite/SQLiteDatabase;->rawQuery(Ljava/lang/String;[Ljava/lang/String;)Landroid/database/Cursor;

    move-result-object v1
    :try_end_10c
    .catchall {:try_start_108 .. :try_end_10c} :catchall_25e

    .line 368
    :try_start_10c
    const-string v0, "begin"

    invoke-interface {v1, v0}, Landroid/database/Cursor;->getColumnIndex(Ljava/lang/String;)I

    move-result v0

    .line 369
    const-string v2, "end"

    invoke-interface {v1, v2}, Landroid/database/Cursor;->getColumnIndex(Ljava/lang/String;)I

    move-result v2

    .line 370
    const-string v3, "eventId"

    invoke-interface {v1, v3}, Landroid/database/Cursor;->getColumnIndex(Ljava/lang/String;)I

    move-result v3

    .line 371
    const-string v4, "myAlarmTime"

    invoke-interface {v1, v4}, Landroid/database/Cursor;->getColumnIndex(Ljava/lang/String;)I

    move-result v4

    .line 372
    const-string v5, "minutes"

    invoke-interface {v1, v5}, Landroid/database/Cursor;->getColumnIndex(Ljava/lang/String;)I

    move-result v5

    .line 374
    invoke-static {v15, v12}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result v6

    if-eqz v6, :cond_15a

    move-object/from16 v6, v29

    .line 375
    invoke-virtual {v6, v13, v14}, Lcom/android/calendarcommon2/Time;->set(J)V

    .line 376
    invoke-virtual {v6}, Lcom/android/calendarcommon2/Time;->format()Ljava/lang/String;

    move-result-object v7

    .line 377
    new-instance v8, Ljava/lang/StringBuilder;

    move-object/from16 v9, v18

    invoke-direct {v8, v9}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    .line 378
    invoke-interface {v1}, Landroid/database/Cursor;->getCount()I

    move-result v9

    invoke-virtual {v8, v9}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    const-string v9, " nextAlarmTime: "

    invoke-virtual {v8, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v8, v7}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v8}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v7

    .line 377
    invoke-static {v15, v7}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    goto :goto_15c

    :catchall_157
    move-exception v0

    goto/16 :goto_260

    :cond_15a
    move-object/from16 v6, v29

    .line 381
    :goto_15c
    invoke-interface {v1}, Landroid/database/Cursor;->moveToNext()Z

    move-result v7

    if-eqz v7, :cond_1e6

    .line 389
    invoke-interface {v1, v4}, Landroid/database/Cursor;->getLong(I)J

    move-result-wide v7

    .line 390
    invoke-interface {v1, v3}, Landroid/database/Cursor;->getLong(I)J

    move-result-wide v9

    .line 391
    invoke-interface {v1, v5}, Landroid/database/Cursor;->getInt(I)I

    move-result v26

    move-wide/from16 p1, v13

    .line 392
    invoke-interface {v1, v0}, Landroid/database/Cursor;->getLong(I)J

    move-result-wide v12

    .line 393
    invoke-interface {v1, v2}, Landroid/database/Cursor;->getLong(I)J

    move-result-wide v24

    const/4 v11, 0x3

    .line 395
    invoke-static {v15, v11}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result v14
    :try_end_17d
    .catchall {:try_start_10c .. :try_end_17d} :catchall_157

    const-string v11, " "

    if-eqz v14, :cond_1be

    .line 396
    :try_start_181
    invoke-virtual {v6, v7, v8}, Lcom/android/calendarcommon2/Time;->set(J)V

    .line 397
    invoke-virtual {v6}, Lcom/android/calendarcommon2/Time;->format()Ljava/lang/String;

    move-result-object v14

    .line 398
    invoke-virtual {v6, v12, v13}, Lcom/android/calendarcommon2/Time;->set(J)V

    move/from16 v29, v0

    .line 399
    invoke-virtual {v6}, Lcom/android/calendarcommon2/Time;->format()Ljava/lang/String;

    move-result-object v0

    move/from16 v30, v2

    .line 401
    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    move/from16 v31, v3

    const-string v3, "  looking at id: "

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v9, v10}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v11}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v12, v13}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v0, " alarm: "

    invoke-virtual {v2, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v7, v8}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v2, v14}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    invoke-static {v15, v0}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    goto :goto_1c4

    :cond_1be
    move/from16 v29, v0

    move/from16 v30, v2

    move/from16 v31, v3

    :goto_1c4
    cmp-long v0, v7, p1

    if-gez v0, :cond_1d1

    move-wide/from16 v22, v7

    move-wide/from16 v20, v12

    move-wide/from16 v13, v22

    :goto_1ce
    move-wide/from16 v18, v9

    goto :goto_1f1

    :cond_1d1
    const-wide/32 v2, 0xea60

    add-long v2, p1, v2

    cmp-long v0, v7, v2

    if-lez v0, :cond_1ea

    const/4 v0, 0x3

    .line 411
    invoke-static {v15, v0}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result v0

    if-eqz v0, :cond_1e6

    .line 412
    const-string v0, "This event alarm (and all later ones) will be scheduled later"

    invoke-static {v15, v0}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    :cond_1e6
    move-object/from16 v2, p0

    goto/16 :goto_253

    :cond_1ea
    move-wide/from16 v22, v7

    move-wide/from16 v20, v12

    move-wide/from16 v13, p1

    goto :goto_1ce

    .line 420
    :goto_1f1
    invoke-static/range {v17 .. v23}, Landroid/provider/CalendarContract$CalendarAlerts;->alarmExists(Landroid/content/ContentResolver;JJJ)Z

    move-result v2

    move-wide/from16 v7, v18

    if-eqz v2, :cond_227

    const/4 v0, 0x3

    .line 421
    invoke-static {v15, v0}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result v2

    if-eqz v2, :cond_224

    .line 422
    const-string v2, "title"

    invoke-interface {v1, v2}, Landroid/database/Cursor;->getColumnIndex(Ljava/lang/String;)I

    move-result v2

    .line 423
    invoke-interface {v1, v2}, Landroid/database/Cursor;->getString(I)Ljava/lang/String;

    move-result-object v2

    .line 424
    new-instance v3, Ljava/lang/StringBuilder;

    invoke-direct {v3}, Ljava/lang/StringBuilder;-><init>()V

    const-string v9, "  alarm exists for id: "

    invoke-virtual {v3, v9}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3, v7, v8}, Ljava/lang/StringBuilder;->append(J)Ljava/lang/StringBuilder;

    invoke-virtual {v3, v11}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-static {v15, v2}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    :cond_224
    :goto_224
    move-object/from16 v2, p0

    goto :goto_24a

    :cond_227
    move-wide/from16 v18, v24

    move-wide/from16 v24, v22

    move-wide/from16 v22, v18

    move-wide/from16 v18, v7

    const/4 v0, 0x3

    .line 431
    invoke-static/range {v17 .. v26}, Landroid/provider/CalendarContract$CalendarAlerts;->insert(Landroid/content/ContentResolver;JJJJI)Landroid/net/Uri;

    move-result-object v2

    move-wide/from16 v7, v24

    if-nez v2, :cond_245

    const/4 v2, 0x6

    .line 434
    invoke-static {v15, v2}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result v2

    if-eqz v2, :cond_224

    .line 435
    const-string v2, "runScheduleNextAlarm() insert into CalendarAlerts table failed"

    invoke-static {v15, v2}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I

    goto :goto_224

    :cond_245
    move-object/from16 v2, p0

    .line 441
    invoke-virtual {v2, v7, v8}, Lcom/android/providers/calendar/CalendarAlarmManager;->scheduleAlarm(J)V
    :try_end_24a
    .catchall {:try_start_181 .. :try_end_24a} :catchall_157

    :goto_24a
    move v12, v0

    move/from16 v0, v29

    move/from16 v2, v30

    move/from16 v3, v31

    goto/16 :goto_15c

    .line 446
    :goto_253
    invoke-interface {v1}, Landroid/database/Cursor;->close()V

    if-lez v16, :cond_25d

    move-wide/from16 v0, v27

    .line 452
    invoke-virtual {v2, v0, v1}, Lcom/android/providers/calendar/CalendarAlarmManager;->scheduleAlarm(J)V

    :cond_25d
    return-void

    :catchall_25e
    move-exception v0

    const/4 v1, 0x0

    :goto_260
    if-eqz v1, :cond_265

    .line 446
    invoke-interface {v1}, Landroid/database/Cursor;->close()V

    .line 448
    :cond_265
    throw v0
.end method


