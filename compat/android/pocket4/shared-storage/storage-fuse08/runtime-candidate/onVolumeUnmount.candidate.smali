.method public onVolumeUnmount(Lcom/android/server/storage/ImmutableVolumeInfo;)V
    .registers 11
    .param p1, "vol"    # Lcom/android/server/storage/ImmutableVolumeInfo;

    invoke-direct {p0, p1}, Lcom/android/server/storage/StorageSessionController;->shouldHandle(Lcom/android/server/storage/ImmutableVolumeInfo;)Z

    move-result v0

    if-nez v0, :storage_unmount_supported

    return-void

    :storage_unmount_supported

    .line 255
    const-string v0, "StorageSessionController"

    invoke-virtual {p1}, Lcom/android/server/storage/ImmutableVolumeInfo;->getId()Ljava/lang/String;

    move-result-object v1

    .line 256
    .local v1, "sessionId":Ljava/lang/String;
    invoke-static {}, Landroid/os/Binder;->clearCallingIdentity()J

    move-result-wide v2

    .line 258
    .local v2, "token":J
    :try_start_a
    invoke-virtual {p0, p1}, Lcom/android/server/storage/StorageSessionController;->getConnectionUserIdForVolume(Lcom/android/server/storage/ImmutableVolumeInfo;)I

    move-result v7

    iget-object v8, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v8
    :storage_before_lookup_end
    .catch Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException; {:try_start_a .. :storage_before_lookup_end} :catch_2a
    .catchall {:try_start_a .. :storage_before_lookup_end} :catchall_28

    :storage_lookup_start
    iget-object v4, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v4, v7}, Landroid/util/SparseArray;->get(I)Ljava/lang/Object;

    move-result-object v4

    check-cast v4, Lcom/android/server/storage/StorageUserConnection;

    monitor-exit v8
    :storage_lookup_end
    .catchall {:storage_lookup_start .. :storage_lookup_end} :storage_lookup_failed

    :storage_after_lookup

    .line 259
    .local v4, "connection":Lcom/android/server/storage/StorageUserConnection;
    new-instance v5, Ljava/lang/StringBuilder;

    invoke-direct {v5}, Ljava/lang/StringBuilder;-><init>()V

    const-string v6, "On volume unmount "

    invoke-virtual {v5, v6}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v5, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {v5}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v5

    invoke-static {v0, v5}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 260
    if-eqz v4, :cond_2c

    .line 261
    invoke-virtual {v4, v1}, Lcom/android/server/storage/StorageUserConnection;->removeSessionAndWait(Ljava/lang/String;)V
    :try_end_27
    .catch Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException; {:storage_after_lookup .. :try_end_27} :catch_2a
    .catchall {:storage_after_lookup .. :try_end_27} :catchall_28

    goto :goto_2c

    .line 266
    .end local v4    # "connection":Lcom/android/server/storage/StorageUserConnection;
    :catchall_28
    move-exception v0

    goto :goto_49

    .line 263
    :catch_2a
    move-exception v4

    goto :goto_31

    .line 266
    :cond_2c
    :goto_2c
    nop

    :goto_2d
    invoke-static {v2, v3}, Landroid/os/Binder;->restoreCallingIdentity(J)V

    .line 267
    goto :goto_48

    .line 263
    :goto_31
    nop

    .line 264
    .local v4, "e":Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;
    :try_start_32
    new-instance v5, Ljava/lang/StringBuilder;

    invoke-direct {v5}, Ljava/lang/StringBuilder;-><init>()V

    const-string v6, "Failed to end session for vol with id: "

    invoke-virtual {v5, v6}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v5, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v5}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v5

    invoke-static {v0, v5, v4}, Landroid/util/Slog;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I
    :try_end_46
    .catchall {:try_start_32 .. :try_end_46} :catchall_28

    .line 266
    nop

    .end local v4    # "e":Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;
    goto :goto_2d

    .line 268
    :goto_48
    return-void

    .line 266
    :goto_49
    invoke-static {v2, v3}, Landroid/os/Binder;->restoreCallingIdentity(J)V

    .line 267
    throw v0

    :storage_lookup_failed
    move-exception v4

    :storage_unlock_start
    monitor-exit v8

    throw v4
    :storage_unlock_end
    .catch Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException; {:storage_unlock_start .. :storage_unlock_end} :catch_2a
    .catchall {:storage_unlock_start .. :storage_unlock_end} :catchall_28
.end method
