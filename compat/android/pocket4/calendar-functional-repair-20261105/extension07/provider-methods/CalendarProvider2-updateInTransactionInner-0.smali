.method private updateInTransactionInner(Landroid/net/Uri;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;Z)I
    .registers 30

    move-object/from16 v0, p0

    move-object/from16 v1, p1

    .line 4235
    const-string v8, "CalendarProvider2"

    const/4 v9, 0x2

    invoke-static {v8, v9}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result v2

    if-eqz v2, :cond_1e

    .line 4236
    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, "updateInTransaction: "

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-static {v8, v2}, Landroid/util/Log;->v(Ljava/lang/String;Ljava/lang/String;)I

    .line 4238
    :cond_1e
    iget-object v2, v0, Lcom/android/providers/calendar/CalendarProvider2;->mConfidenceChecker:Lcom/android/providers/calendar/CalendarConfidenceChecker;

    invoke-virtual {v2}, Lcom/android/providers/calendar/CalendarConfidenceChecker;->checkLastCheckTime()Z

    .line 4240
    invoke-virtual {v1}, Landroid/net/Uri;->getQueryParameterNames()Ljava/util/Set;

    move-result-object v2

    invoke-direct {v0, v2}, Lcom/android/providers/calendar/CalendarProvider2;->validateUriParameters(Ljava/util/Set;)V

    .line 4241
    sget-object v2, Lcom/android/providers/calendar/CalendarProvider2;->sUriMatcher:Landroid/content/UriMatcher;

    invoke-virtual {v2, v1}, Landroid/content/UriMatcher;->match(Landroid/net/Uri;)I

    move-result v5

    const/4 v1, 0x2

    move-object/from16 v2, p1

    move-object/from16 v3, p2

    move-object/from16 v6, p3

    move-object/from16 v7, p4

    move/from16 v4, p5

    .line 4242
    invoke-direct/range {v0 .. v7}, Lcom/android/providers/calendar/CalendarProvider2;->verifyTransactionAllowed(ILandroid/net/Uri;Landroid/content/ContentValues;ZILjava/lang/String;[Ljava/lang/String;)V

    move-object v1, v2

    move-object v4, v3

    move v2, v5

    move-object v5, v6

    move-object v6, v7

    .line 4244
    iget-object v3, v0, Lcom/android/providers/calendar/CalendarProvider2;->mDbHelper:Lcom/android/providers/calendar/CalendarDatabaseHelper;

    invoke-virtual {v3}, Lcom/android/providers/calendar/CalendarDatabaseHelper;->getWritableDatabase()Landroid/database/sqlite/SQLiteDatabase;

    move-result-object v3

    iput-object v3, v0, Lcom/android/providers/calendar/SQLiteContentProvider;->mDb:Landroid/database/sqlite/SQLiteDatabase;

    const/4 v10, 0x0

    const/4 v7, 0x1

    const/4 v11, 0x0

    if-eq v2, v7, :cond_2e3

    if-eq v2, v9, :cond_2e3

    const/16 v9, 0x10

    .line 4246
    const-string v12, "account_type"

    const-string v13, "account_name"

    if-eq v2, v9, :cond_2d0

    const/16 v9, 0x11

    const-string v14, "_id=?"

    if-eq v2, v9, :cond_295

    const/16 v9, 0x16

    if-eq v2, v9, :cond_28e

    const/16 v9, 0x1c

    if-eq v2, v9, :cond_1de

    const/16 v9, 0x20

    if-eq v2, v9, :cond_1b1

    packed-switch v2, :pswitch_data_338

    const-string v7, "CalendarAlerts"

    packed-switch v2, :pswitch_data_348

    .line 4504
    const-string v0, "Unknown URL "

    invoke-static {v0, v1}, Lcom/android/providers/calendar/CalendarProvider2$$ExternalSyntheticBUOutline1;->m(Ljava/lang/String;Ljava/lang/Object;)V

    return v11

    .line 4391
    :pswitch_7a
    invoke-static {v1}, Landroid/content/ContentUris;->parseId(Landroid/net/Uri;)J

    move-result-wide v1

    .line 4392
    iget-object v0, v0, Lcom/android/providers/calendar/SQLiteContentProvider;->mDb:Landroid/database/sqlite/SQLiteDatabase;

    .line 4393
    invoke-static {v1, v2}, Ljava/lang/String;->valueOf(J)Ljava/lang/String;

    move-result-object v1

    filled-new-array {v1}, [Ljava/lang/String;

    move-result-object v1

    .line 4392
    invoke-virtual {v0, v7, v4, v14, v1}, Landroid/database/sqlite/SQLiteDatabase;->update(Ljava/lang/String;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I

    move-result v0

    return v0

    .line 4398
    :pswitch_8d
    invoke-virtual {v3, v7, v4, v5, v6}, Landroid/database/sqlite/SQLiteDatabase;->update(Ljava/lang/String;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I

    move-result v0

    return v0

    :pswitch_92
    const/4 v5, 0x0

    const/4 v6, 0x0

    .line 4418
    const-string v2, "ExtendedProperties"

    const/4 v3, 0x1

    move/from16 v7, p5

    invoke-direct/range {v0 .. v7}, Lcom/android/providers/calendar/CalendarProvider2;->updateEventRelatedTable(Landroid/net/Uri;Ljava/lang/String;ZLandroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;Z)I

    move-result v0

    return v0

    :pswitch_9e
    const/4 v5, 0x0

    const/4 v6, 0x0

    .line 4405
    const-string v2, "Reminders"

    const/4 v3, 0x1

    move-object/from16 v0, p0

    move-object/from16 v1, p1

    move-object/from16 v4, p2

    move/from16 v7, p5

    invoke-direct/range {v0 .. v7}, Lcom/android/providers/calendar/CalendarProvider2;->updateEventRelatedTable(Landroid/net/Uri;Ljava/lang/String;ZLandroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;Z)I

    move-result v1

    const/4 v2, 0x3

    .line 4410
    invoke-static {v8, v2}, Landroid/util/Log;->isLoggable(Ljava/lang/String;I)Z

    move-result v2

    if-eqz v2, :cond_bb

    .line 4411
    const-string v2, "updateInternal() changing reminder"

    invoke-static {v8, v2}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I

    .line 4413
    :cond_bb
    iget-object v0, v0, Lcom/android/providers/calendar/CalendarProvider2;->mCalendarAlarm:Lcom/android/providers/calendar/CalendarAlarmManager;

    invoke-virtual {v0, v11}, Lcom/android/providers/calendar/CalendarAlarmManager;->checkNextAlarm(Z)V

    return v1

    .line 4402
    :pswitch_c1
    const-string v2, "Reminders"

    const/4 v3, 0x0

    move-object/from16 v1, p1

    move-object/from16 v4, p2

    move/from16 v7, p5

    invoke-direct/range {v0 .. v7}, Lcom/android/providers/calendar/CalendarProvider2;->updateEventRelatedTable(Landroid/net/Uri;Ljava/lang/String;ZLandroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;Z)I

    move-result v0

    return v0

    :pswitch_cf
    const/4 v5, 0x0

    const/4 v6, 0x0

    .line 4385
    const-string v2, "Attendees"

    const/4 v3, 0x1

    move-object/from16 v0, p0

    move-object/from16 v1, p1

    move-object/from16 v4, p2

    move/from16 v7, p5

    invoke-direct/range {v0 .. v7}, Lcom/android/providers/calendar/CalendarProvider2;->updateEventRelatedTable(Landroid/net/Uri;Ljava/lang/String;ZLandroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;Z)I

    move-result v0

    return v0

    .line 4382
    :pswitch_e1
    const-string v2, "Attendees"

    const/4 v3, 0x0

    move-object/from16 v0, p0

    move-object/from16 v1, p1

    move-object/from16 v4, p2

    move-object/from16 v5, p3

    move-object/from16 v6, p4

    move/from16 v7, p5

    invoke-direct/range {v0 .. v7}, Lcom/android/providers/calendar/CalendarProvider2;->updateEventRelatedTable(Landroid/net/Uri;Ljava/lang/String;ZLandroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;Z)I

    move-result v0

    return v0

    :pswitch_f5
    move-object v8, v0

    move-object v15, v4

    move/from16 v0, p5

    const/4 v3, 0x5

    .line 4284
    const-string v4, "Calendars"

    if-ne v2, v3, :cond_103

    .line 4285
    invoke-static {v1}, Landroid/content/ContentUris;->parseId(Landroid/net/Uri;)J

    move-result-wide v1

    goto :goto_125

    :cond_103
    if-eqz v5, :cond_112

    .line 4292
    invoke-static {v5, v14}, Landroid/text/TextUtils;->equals(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Z

    move-result v1

    if-eqz v1, :cond_112

    .line 4293
    aget-object v1, v6, v11

    invoke-static {v1}, Ljava/lang/Long;->parseLong(Ljava/lang/String;)J

    move-result-wide v1

    goto :goto_125

    :cond_112
    if-eqz v5, :cond_1aa

    .line 4294
    const-string v1, "_id="

    invoke-virtual {v5, v1}, Ljava/lang/String;->startsWith(Ljava/lang/String;)Z

    move-result v1

    if-eqz v1, :cond_1aa

    const/4 v1, 0x4

    .line 4297
    invoke-virtual {v5, v1}, Ljava/lang/String;->substring(I)Ljava/lang/String;

    move-result-object v1

    invoke-static {v1}, Ljava/lang/Long;->parseLong(Ljava/lang/String;)J

    move-result-wide v1

    .line 4302
    :goto_125
    const-string v3, "mutators"

    const-string v5, "dirty"

    if-nez v0, :cond_136

    .line 4303
    invoke-static {v7}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v6

    invoke-virtual {v15, v5, v6}, Landroid/content/ContentValues;->put(Ljava/lang/String;Ljava/lang/Integer;)V

    .line 4304
    invoke-direct {v8, v15, v3}, Lcom/android/providers/calendar/CalendarProvider2;->addMutator(Landroid/content/ContentValues;Ljava/lang/String;)V

    goto :goto_149

    .line 4306
    :cond_136
    invoke-virtual {v15, v5}, Landroid/content/ContentValues;->containsKey(Ljava/lang/String;)Z

    move-result v6

    if-eqz v6, :cond_149

    .line 4307
    invoke-virtual {v15, v5}, Landroid/content/ContentValues;->getAsInteger(Ljava/lang/String;)Ljava/lang/Integer;

    move-result-object v5

    invoke-virtual {v5}, Ljava/lang/Integer;->intValue()I

    move-result v5

    if-nez v5, :cond_149

    .line 4308
    invoke-virtual {v15, v3, v10}, Landroid/content/ContentValues;->put(Ljava/lang/String;Ljava/lang/String;)V

    .line 4311
    :cond_149
    :goto_149
    const-string v3, "sync_events"

    invoke-virtual {v15, v3}, Landroid/content/ContentValues;->getAsInteger(Ljava/lang/String;)Ljava/lang/Integer;

    move-result-object v3

    if-eqz v3, :cond_15c

    .line 4313
    invoke-virtual {v3}, Ljava/lang/Integer;->intValue()I

    move-result v3

    if-ne v3, v7, :cond_158

    goto :goto_159

    :cond_158
    move v7, v11

    :goto_159
    invoke-direct {v8, v1, v2, v7}, Lcom/android/providers/calendar/CalendarProvider2;->modifyCalendarSubscription(JZ)V

    .line 4315
    :cond_15c
    const-string v3, "calendar_color_index"

    invoke-virtual {v15, v3}, Landroid/content/ContentValues;->getAsString(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v3

    .line 4316
    invoke-static {v3}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z

    move-result v5

    if-nez v5, :cond_189

    .line 4317
    invoke-virtual {v15, v13}, Landroid/content/ContentValues;->getAsString(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v5

    .line 4318
    invoke-virtual {v15, v12}, Landroid/content/ContentValues;->getAsString(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v6

    .line 4319
    invoke-static {v5}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z

    move-result v7

    if-nez v7, :cond_17c

    invoke-static {v6}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z

    move-result v7

    if-eqz v7, :cond_186

    .line 4320
    :cond_17c
    invoke-direct {v8, v1, v2}, Lcom/android/providers/calendar/CalendarProvider2;->getAccount(J)Landroid/accounts/Account;

    move-result-object v7

    if-eqz v7, :cond_186

    .line 4322
    iget-object v5, v7, Landroid/accounts/Account;->name:Ljava/lang/String;

    .line 4323
    iget-object v6, v7, Landroid/accounts/Account;->type:Ljava/lang/String;

    .line 4326
    :cond_186
    invoke-direct {v8, v5, v6, v3, v11}, Lcom/android/providers/calendar/CalendarProvider2;->verifyColorExists(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;I)I

    .line 4329
    :cond_189
    iget-object v3, v8, Lcom/android/providers/calendar/SQLiteContentProvider;->mDb:Landroid/database/sqlite/SQLiteDatabase;

    .line 4330
    invoke-static {v1, v2}, Ljava/lang/String;->valueOf(J)Ljava/lang/String;

    move-result-object v1

    filled-new-array {v1}, [Ljava/lang/String;

    move-result-object v1

    .line 4329
    invoke-virtual {v3, v4, v15, v14, v1}, Landroid/database/sqlite/SQLiteDatabase;->update(Ljava/lang/String;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I

    move-result v1

    if-lez v1, :cond_1a9

    .line 4334
    const-string v2, "visible"

    invoke-virtual {v15, v2}, Landroid/content/ContentValues;->containsKey(Ljava/lang/String;)Z

    move-result v2

    if-eqz v2, :cond_1a6

    .line 4339
    iget-object v2, v8, Lcom/android/providers/calendar/CalendarProvider2;->mCalendarAlarm:Lcom/android/providers/calendar/CalendarAlarmManager;

    invoke-virtual {v2, v11}, Lcom/android/providers/calendar/CalendarAlarmManager;->checkNextAlarm(Z)V

    .line 4342
    :cond_1a6
    invoke-direct {v8, v0}, Lcom/android/providers/calendar/CalendarProvider2;->sendUpdateNotification(Z)V

    :cond_1a9
    return v1

    .line 4299
    :cond_1aa
    iget-object v0, v8, Lcom/android/providers/calendar/SQLiteContentProvider;->mDb:Landroid/database/sqlite/SQLiteDatabase;

    invoke-virtual {v0, v4, v15, v5, v6}, Landroid/database/sqlite/SQLiteDatabase;->update(Ljava/lang/String;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I

    move-result v0

    return v0

    :cond_1b1
    move-object v8, v0

    move-object v15, v4

    .line 4265
    const-string v0, "color"

    invoke-virtual {v15, v0}, Landroid/content/ContentValues;->getAsInteger(Ljava/lang/String;)Ljava/lang/Integer;

    move-result-object v0

    if-eqz v0, :cond_1bc

    goto :goto_1bd

    :cond_1bc
    move v7, v11

    .line 4268
    :goto_1bd
    const-string v0, "data"

    invoke-virtual {v15, v0}, Landroid/content/ContentValues;->getAsString(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    if-eqz v0, :cond_1c7

    add-int/lit8 v7, v7, 0x1

    .line 4272
    :cond_1c7
    invoke-virtual {v15}, Landroid/content/ContentValues;->size()I

    move-result v0

    if-ne v0, v7, :cond_1d6

    .line 4276
    invoke-direct {v8, v1, v5, v13, v12}, Lcom/android/providers/calendar/CalendarProvider2;->appendAccountToSelection(Landroid/net/Uri;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    invoke-direct {v8, v15, v0, v6}, Lcom/android/providers/calendar/CalendarProvider2;->handleUpdateColors(Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I

    move-result v0

    return v0

    .line 4273
    :cond_1d6
    new-instance v0, Ljava/lang/UnsupportedOperationException;

    const-string v1, "You may only change the COLOR and DATA columns for an existing Colors entry."

    invoke-direct {v0, v1}, Ljava/lang/UnsupportedOperationException;-><init>(Ljava/lang/String;)V

    throw v0

    :cond_1de
    move-object v8, v0

    move-object v15, v4

    move/from16 v0, p5

    .line 4426
    const-string v2, "key=?"

    invoke-virtual {v5, v2}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v2

    if-eqz v2, :cond_288

    .line 4430
    invoke-static {v6}, Ljava/util/Arrays;->asList([Ljava/lang/Object;)Ljava/util/List;

    move-result-object v2

    .line 4432
    const-string v3, "timezoneInstancesPrevious"

    invoke-interface {v2, v3}, Ljava/util/List;->contains(Ljava/lang/Object;)Z

    move-result v3

    if-nez v3, :cond_282

    .line 4438
    iget-object v1, v8, Lcom/android/providers/calendar/CalendarProvider2;->mCalendarCache:Lcom/android/providers/calendar/CalendarCache;

    invoke-virtual {v1}, Lcom/android/providers/calendar/CalendarCache;->readTimezoneInstances()Ljava/lang/String;

    move-result-object v1

    .line 4442
    iget-object v3, v8, Lcom/android/providers/calendar/SQLiteContentProvider;->mDb:Landroid/database/sqlite/SQLiteDatabase;

    const-string v4, "CalendarCache"

    invoke-virtual {v3, v4, v15, v5, v6}, Landroid/database/sqlite/SQLiteDatabase;->update(Ljava/lang/String;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I

    move-result v3

    if-lez v3, :cond_281

    .line 4455
    const-string v4, "timezoneType"

    invoke-interface {v2, v4}, Ljava/util/List;->contains(Ljava/lang/Object;)Z

    move-result v4

    if-eqz v4, :cond_25a

    .line 4456
    const-string v2, "value"

    invoke-virtual {v15, v2}, Landroid/content/ContentValues;->getAsString(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2

    if-eqz v2, :cond_281

    .line 4459
    const-string v4, "home"

    invoke-virtual {v2, v4}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v4

    if-eqz v4, :cond_238

    .line 4460
    iget-object v2, v8, Lcom/android/providers/calendar/CalendarProvider2;->mCalendarCache:Lcom/android/providers/calendar/CalendarCache;

    .line 4461
    invoke-virtual {v2}, Lcom/android/providers/calendar/CalendarCache;->readTimezoneInstancesPrevious()Ljava/lang/String;

    move-result-object v2

    if-eqz v2, :cond_22b

    .line 4463
    iget-object v4, v8, Lcom/android/providers/calendar/CalendarProvider2;->mCalendarCache:Lcom/android/providers/calendar/CalendarCache;

    invoke-virtual {v4, v2}, Lcom/android/providers/calendar/CalendarCache;->writeTimezoneInstances(Ljava/lang/String;)V

    .line 4467
    :cond_22b
    invoke-virtual {v1, v2}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-nez v1, :cond_281

    .line 4468
    invoke-direct {v8}, Lcom/android/providers/calendar/CalendarProvider2;->regenerateInstancesTable()V

    .line 4469
    invoke-direct {v8, v0}, Lcom/android/providers/calendar/CalendarProvider2;->sendUpdateNotification(Z)V

    return v3

    .line 4473
    :cond_238
    const-string v4, "auto"

    invoke-virtual {v2, v4}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v2

    if-eqz v2, :cond_281

    .line 4474
    invoke-static {}, Ljava/util/TimeZone;->getDefault()Ljava/util/TimeZone;

    move-result-object v2

    invoke-virtual {v2}, Ljava/util/TimeZone;->getID()Ljava/lang/String;

    move-result-object v2

    .line 4475
    iget-object v4, v8, Lcom/android/providers/calendar/CalendarProvider2;->mCalendarCache:Lcom/android/providers/calendar/CalendarCache;

    invoke-virtual {v4, v2}, Lcom/android/providers/calendar/CalendarCache;->writeTimezoneInstances(Ljava/lang/String;)V

    .line 4476
    invoke-virtual {v1, v2}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-nez v1, :cond_281

    .line 4477
    invoke-direct {v8}, Lcom/android/providers/calendar/CalendarProvider2;->regenerateInstancesTable()V

    .line 4478
    invoke-direct {v8, v0}, Lcom/android/providers/calendar/CalendarProvider2;->sendUpdateNotification(Z)V

    return v3

    .line 4484
    :cond_25a
    const-string v4, "timezoneInstances"

    invoke-interface {v2, v4}, Ljava/util/List;->contains(Ljava/lang/Object;)Z

    move-result v2

    if-eqz v2, :cond_281

    .line 4486
    invoke-direct {v8}, Lcom/android/providers/calendar/CalendarProvider2;->isHomeTimezone()Z

    move-result v2

    if-eqz v2, :cond_281

    .line 4487
    iget-object v2, v8, Lcom/android/providers/calendar/CalendarProvider2;->mCalendarCache:Lcom/android/providers/calendar/CalendarCache;

    invoke-virtual {v2}, Lcom/android/providers/calendar/CalendarCache;->readTimezoneInstances()Ljava/lang/String;

    move-result-object v2

    .line 4489
    iget-object v4, v8, Lcom/android/providers/calendar/CalendarProvider2;->mCalendarCache:Lcom/android/providers/calendar/CalendarCache;

    invoke-virtual {v4, v2}, Lcom/android/providers/calendar/CalendarCache;->writeTimezoneInstancesPrevious(Ljava/lang/String;)V

    if-eqz v1, :cond_281

    .line 4493
    invoke-virtual {v1, v2}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-nez v1, :cond_281

    .line 4494
    invoke-direct {v8}, Lcom/android/providers/calendar/CalendarProvider2;->regenerateInstancesTable()V

    .line 4495
    invoke-direct {v8, v0}, Lcom/android/providers/calendar/CalendarProvider2;->sendUpdateNotification(Z)V

    :cond_281
    return v3

    .line 4433
    :cond_282
    const-string v0, "Invalid selection key: timezoneInstancesPrevious for "

    invoke-static {v0, v1}, Lcom/android/providers/calendar/CalendarProvider2$$ExternalSyntheticBUOutline0;->m(Ljava/lang/String;Ljava/lang/Object;)V

    return v11

    .line 4427
    :cond_288
    const-string v0, "Selection should be key=? for "

    invoke-static {v0, v1}, Lcom/android/providers/calendar/CalendarProvider2$$ExternalSyntheticBUOutline0;->m(Ljava/lang/String;Ljava/lang/Object;)V

    return v11

    :cond_28e
    move-object v8, v0

    .line 4421
    iget-object v0, v8, Lcom/android/providers/calendar/CalendarProvider2;->mCalendarAlarm:Lcom/android/providers/calendar/CalendarAlarmManager;

    invoke-virtual {v0, v7}, Lcom/android/providers/calendar/CalendarAlarmManager;->checkNextAlarm(Z)V

    return v11

    :cond_295
    move-object v8, v0

    move-object v15, v4

    .line 4253
    invoke-direct {v8, v1, v5, v13, v12}, Lcom/android/providers/calendar/CalendarProvider2;->appendAccountToSelection(Landroid/net/Uri;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    if-nez v0, :cond_2a0

    .line 4256
    const-string v0, ""

    goto :goto_2b3

    :cond_2a0
    new-instance v2, Ljava/lang/StringBuilder;

    const-string v3, " AND ("

    invoke-direct {v2, v3}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v0, ")"

    invoke-virtual {v2, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    :goto_2b3
    invoke-virtual {v14, v0}, Ljava/lang/String;->concat(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    .line 4259
    invoke-static {v1}, Landroid/content/ContentUris;->parseId(Landroid/net/Uri;)J

    move-result-wide v1

    invoke-static {v1, v2}, Ljava/lang/String;->valueOf(J)Ljava/lang/String;

    move-result-object v1

    .line 4258
    invoke-direct {v8, v6, v1}, Lcom/android/providers/calendar/CalendarProvider2;->insertSelectionArg([Ljava/lang/String;Ljava/lang/String;)[Ljava/lang/String;

    move-result-object v1

    .line 4260
    iget-object v2, v8, Lcom/android/providers/calendar/CalendarProvider2;->mDbHelper:Lcom/android/providers/calendar/CalendarDatabaseHelper;

    invoke-virtual {v2}, Lcom/android/providers/calendar/CalendarDatabaseHelper;->getSyncState()Lcom/android/common/content/SyncStateContentProviderHelper;

    move-result-object v2

    iget-object v3, v8, Lcom/android/providers/calendar/SQLiteContentProvider;->mDb:Landroid/database/sqlite/SQLiteDatabase;

    invoke-virtual {v2, v3, v15, v0, v1}, Lcom/android/common/content/SyncStateContentProviderHelper;->update(Landroid/database/sqlite/SQLiteDatabase;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I

    move-result v0

    return v0

    :cond_2d0
    move-object v8, v0

    move-object v15, v4

    .line 4248
    iget-object v0, v8, Lcom/android/providers/calendar/CalendarProvider2;->mDbHelper:Lcom/android/providers/calendar/CalendarDatabaseHelper;

    invoke-virtual {v0}, Lcom/android/providers/calendar/CalendarDatabaseHelper;->getSyncState()Lcom/android/common/content/SyncStateContentProviderHelper;

    move-result-object v0

    iget-object v2, v8, Lcom/android/providers/calendar/SQLiteContentProvider;->mDb:Landroid/database/sqlite/SQLiteDatabase;

    .line 4249
    invoke-direct {v8, v1, v5, v13, v12}, Lcom/android/providers/calendar/CalendarProvider2;->appendAccountToSelection(Landroid/net/Uri;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v1

    .line 4248
    invoke-virtual {v0, v2, v15, v1, v6}, Lcom/android/common/content/SyncStateContentProviderHelper;->update(Landroid/database/sqlite/SQLiteDatabase;Landroid/content/ContentValues;Ljava/lang/String;[Ljava/lang/String;)I

    move-result v0

    return v0

    :cond_2e3
    move-object v8, v0

    move-object v15, v4

    move/from16 v0, p5

    if-ne v2, v9, :cond_30e

    .line 4359
    :try_start_2e9
    invoke-static {v1}, Landroid/content/ContentUris;->parseId(Landroid/net/Uri;)J

    move-result-wide v1

    .line 4360
    iget-object v3, v8, Lcom/android/providers/calendar/SQLiteContentProvider;->mDb:Landroid/database/sqlite/SQLiteDatabase;

    const-string v17, "Events"

    const-string v19, "_id=?"

    .line 4361
    invoke-static {v1, v2}, Ljava/lang/String;->valueOf(J)Ljava/lang/String;

    move-result-object v1

    filled-new-array {v1}, [Ljava/lang/String;

    move-result-object v20

    const/16 v22, 0x0

    const/16 v23, 0x0

    const/16 v18, 0x0

    const/16 v21, 0x0

    move-object/from16 v16, v3

    .line 4360
    invoke-virtual/range {v16 .. v23}, Landroid/database/sqlite/SQLiteDatabase;->query(Ljava/lang/String;[Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Landroid/database/Cursor;

    move-result-object v1

    move v9, v0

    move-object v10, v1

    goto :goto_31f

    :catchall_30c
    move-exception v0

    goto :goto_331

    .line 4365
    :cond_30e
    const-string v1, "Events"

    const/4 v6, 0x0

    const/4 v7, 0x0

    const/4 v2, 0x0

    const/4 v5, 0x0

    move-object/from16 v4, p4

    move v9, v0

    move-object v0, v3

    move-object/from16 v3, p3

    invoke-virtual/range {v0 .. v7}, Landroid/database/sqlite/SQLiteDatabase;->query(Ljava/lang/String;[Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Landroid/database/Cursor;

    move-result-object v0

    move-object v10, v0

    .line 4370
    :goto_31f
    invoke-interface {v10}, Landroid/database/Cursor;->getCount()I

    move-result v0
    :try_end_323
    .catchall {:try_start_2e9 .. :try_end_323} :catchall_30c

    if-nez v0, :cond_329

    .line 4377
    invoke-interface {v10}, Landroid/database/Cursor;->close()V

    return v11

    .line 4374
    :cond_329
    :try_start_329
    invoke-direct {v8, v10, v15, v9}, Lcom/android/providers/calendar/CalendarProvider2;->handleUpdateEvents(Landroid/database/Cursor;Landroid/content/ContentValues;Z)I

    move-result v0
    :try_end_32d
    .catchall {:try_start_329 .. :try_end_32d} :catchall_30c

    .line 4377
    invoke-interface {v10}, Landroid/database/Cursor;->close()V

    return v0

    :goto_331
    if-eqz v10, :cond_336

    invoke-interface {v10}, Landroid/database/Cursor;->close()V

    .line 4379
    :cond_336
    throw v0

    nop

    :pswitch_data_338
    .packed-switch 0x4
        :pswitch_f5
        :pswitch_f5
        :pswitch_e1
        :pswitch_cf
        :pswitch_c1
        :pswitch_9e
    .end packed-switch

    :pswitch_data_348
    .packed-switch 0xb
        :pswitch_92
        :pswitch_8d
        :pswitch_7a
    .end packed-switch
.end method

