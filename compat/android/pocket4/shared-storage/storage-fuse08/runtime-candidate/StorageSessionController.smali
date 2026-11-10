.class public final Lcom/android/server/storage/StorageSessionController;
.super Ljava/lang/Object;
.source "StorageSessionController.java"


# static fields
.field private static final TAG:Ljava/lang/String; = "StorageSessionController"


# instance fields
.field private final mConnections:Landroid/util/SparseArray;
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "Landroid/util/SparseArray<",
            "Lcom/android/server/storage/StorageUserConnection;",
            ">;"
        }
    .end annotation
.end field

.field private final mContext:Landroid/content/Context;

.field private volatile mExternalStorageServiceAppId:I

.field private volatile mExternalStorageServiceComponent:Landroid/content/ComponentName;

.field private volatile mExternalStorageServicePackageName:Ljava/lang/String;

.field private volatile mIsResetting:Z

.field private final mLock:Ljava/lang/Object;

.field private final mUserManager:Landroid/os/UserManager;


# direct methods
.method public constructor <init>(Landroid/content/Context;)V
    .registers 4
    .param p1, "context"    # Landroid/content/Context;

    .line 70
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    .line 59
    new-instance v0, Ljava/lang/Object;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object v0, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    .line 62
    new-instance v0, Landroid/util/SparseArray;

    invoke-direct {v0}, Landroid/util/SparseArray;-><init>()V

    iput-object v0, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    .line 71
    invoke-static {p1}, Ljava/util/Objects;->requireNonNull(Ljava/lang/Object;)Ljava/lang/Object;

    move-object v0, p1

    check-cast v0, Landroid/content/Context;

    iput-object p1, p0, Lcom/android/server/storage/StorageSessionController;->mContext:Landroid/content/Context;

    .line 72
    iget-object v0, p0, Lcom/android/server/storage/StorageSessionController;->mContext:Landroid/content/Context;

    const-class v1, Landroid/os/UserManager;

    invoke-virtual {v0, v1}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/os/UserManager;

    iput-object v0, p0, Lcom/android/server/storage/StorageSessionController;->mUserManager:Landroid/os/UserManager;

    .line 73
    return-void
.end method

.method private initExternalStorageServiceComponent()V
    .registers 8
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;
        }
    .end annotation

    .line 362
    const-string v0, "StorageSessionController"

    const-string v1, "Initialialising..."

    invoke-static {v0, v1}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 363
    iget-object v0, p0, Lcom/android/server/storage/StorageSessionController;->mContext:Landroid/content/Context;

    invoke-virtual {v0}, Landroid/content/Context;->getPackageManager()Landroid/content/pm/PackageManager;

    move-result-object v0

    const-string/jumbo v1, "media"

    const/high16 v2, 0x1c0000

    invoke-virtual {v0, v1, v2}, Landroid/content/pm/PackageManager;->resolveContentProvider(Ljava/lang/String;I)Landroid/content/pm/ProviderInfo;

    move-result-object v0

    .line 367
    .local v0, "provider":Landroid/content/pm/ProviderInfo;
    if-eqz v0, :cond_6b

    .line 371
    iget-object v1, v0, Landroid/content/pm/ProviderInfo;->applicationInfo:Landroid/content/pm/ApplicationInfo;

    iget-object v1, v1, Landroid/content/pm/ApplicationInfo;->packageName:Ljava/lang/String;

    iput-object v1, p0, Lcom/android/server/storage/StorageSessionController;->mExternalStorageServicePackageName:Ljava/lang/String;

    .line 372
    invoke-virtual {v0}, Landroid/content/pm/ProviderInfo;->getUid()I

    move-result v1

    invoke-static {v1}, Landroid/os/UserHandle;->getAppId(I)I

    move-result v1

    iput v1, p0, Lcom/android/server/storage/StorageSessionController;->mExternalStorageServiceAppId:I

    .line 374
    const/4 v1, 0x0

    invoke-direct {p0, v1}, Lcom/android/server/storage/StorageSessionController;->resolveExternalStorageServiceAsUser(I)Landroid/content/pm/ServiceInfo;

    move-result-object v1

    .line 375
    .local v1, "serviceInfo":Landroid/content/pm/ServiceInfo;
    if-eqz v1, :cond_63

    .line 380
    new-instance v2, Landroid/content/ComponentName;

    iget-object v3, v1, Landroid/content/pm/ServiceInfo;->packageName:Ljava/lang/String;

    iget-object v4, v1, Landroid/content/pm/ServiceInfo;->name:Ljava/lang/String;

    invoke-direct {v2, v3, v4}, Landroid/content/ComponentName;-><init>(Ljava/lang/String;Ljava/lang/String;)V

    .line 381
    .local v2, "name":Landroid/content/ComponentName;
    iget-object v3, v1, Landroid/content/pm/ServiceInfo;->permission:Ljava/lang/String;

    .line 382
    const-string v4, "android.permission.BIND_EXTERNAL_STORAGE_SERVICE"

    invoke-virtual {v4, v3}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-eqz v3, :cond_45

    .line 388
    iput-object v2, p0, Lcom/android/server/storage/StorageSessionController;->mExternalStorageServiceComponent:Landroid/content/ComponentName;

    .line 389
    return-void

    .line 383
    :cond_45
    new-instance v3, Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;

    new-instance v5, Ljava/lang/StringBuilder;

    invoke-direct {v5}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {v2}, Landroid/content/ComponentName;->flattenToShortString()Ljava/lang/String;

    move-result-object v6

    invoke-virtual {v5, v6}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v6, " does not require permission "

    invoke-virtual {v5, v6}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v5, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v5}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v4

    invoke-direct {v3, v4}, Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;-><init>(Ljava/lang/String;)V

    throw v3

    .line 376
    .end local v2    # "name":Landroid/content/ComponentName;
    :cond_63
    new-instance v2, Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;

    const-string v3, "No valid ExternalStorageService component found"

    invoke-direct {v2, v3}, Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;-><init>(Ljava/lang/String;)V

    throw v2

    .line 368
    .end local v1    # "serviceInfo":Landroid/content/pm/ServiceInfo;
    :cond_6b
    new-instance v1, Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;

    const-string v2, "No valid MediaStore provider found"

    invoke-direct {v1, v2}, Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;-><init>(Ljava/lang/String;)V

    throw v1
.end method

.method public static isEmulatedOrPublic(Lcom/android/server/storage/ImmutableVolumeInfo;)Z
    .registers 3
    .param p0, "vol"    # Lcom/android/server/storage/ImmutableVolumeInfo;

    .line 466
    invoke-virtual {p0}, Lcom/android/server/storage/ImmutableVolumeInfo;->getType()I

    move-result v0

    const/4 v1, 0x2

    if-eq v0, v1, :cond_16

    .line 467
    invoke-virtual {p0}, Lcom/android/server/storage/ImmutableVolumeInfo;->getType()I

    move-result v0

    if-nez v0, :cond_14

    invoke-virtual {p0}, Lcom/android/server/storage/ImmutableVolumeInfo;->isVisible()Z

    move-result v0

    if-eqz v0, :cond_14

    goto :goto_16

    :cond_14
    const/4 v0, 0x0

    goto :goto_17

    :cond_16
    :goto_16
    const/4 v0, 0x1

    .line 466
    :goto_17
    return v0
.end method

.method private static isSupportedVolume(Lcom/android/server/storage/ImmutableVolumeInfo;)Z
    .registers 3
    .param p0, "vol"    # Lcom/android/server/storage/ImmutableVolumeInfo;

    .line 486
    invoke-static {p0}, Lcom/android/server/storage/StorageSessionController;->isEmulatedOrPublic(Lcom/android/server/storage/ImmutableVolumeInfo;)Z

    move-result v0

    if-nez v0, :cond_d

    invoke-virtual {p0}, Lcom/android/server/storage/ImmutableVolumeInfo;->getType()I

    move-result v0

    const/4 v1, 0x5

    if-ne v0, v1, :cond_e

    :cond_d
    goto :goto_10

    :cond_e
    const/4 v0, 0x0

    goto :goto_11

    :goto_10
    const/4 v0, 0x1

    :goto_11
    return v0
.end method

.method private killExternalStorageService(I)V
    .registers 9
    .param p1, "userId"    # I

    .line 452
    invoke-static {}, Landroid/app/ActivityManager;->getService()Landroid/app/IActivityManager;

    move-result-object v1

    .line 454
    .local v1, "am":Landroid/app/IActivityManager;
    :try_start_4
    iget-object v2, p0, Lcom/android/server/storage/StorageSessionController;->mExternalStorageServicePackageName:Ljava/lang/String;

    iget v3, p0, Lcom/android/server/storage/StorageSessionController;->mExternalStorageServiceAppId:I

    const-string/jumbo v5, "storage_session_controller reset"
    :try_end_b
    .catch Landroid/os/RemoteException; {:try_start_4 .. :try_end_b} :catch_15

    const/16 v6, 0xd

    move v4, p1

    .end local p1    # "userId":I
    .local v4, "userId":I
    :try_start_e
    invoke-interface/range {v1 .. v6}, Landroid/app/IActivityManager;->killApplication(Ljava/lang/String;IILjava/lang/String;I)V
    :try_end_11
    .catch Landroid/os/RemoteException; {:try_start_e .. :try_end_11} :catch_12

    .line 458
    goto :goto_2e

    .line 456
    :catch_12
    move-exception v0

    move-object p1, v0

    goto :goto_18

    .end local v4    # "userId":I
    .restart local p1    # "userId":I
    :catch_15
    move-exception v0

    move v4, p1

    move-object p1, v0

    .line 457
    .restart local v4    # "userId":I
    .local p1, "e":Landroid/os/RemoteException;
    :goto_18
    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    const-string v2, "Failed to kill the ExtenalStorageService for user "

    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0, v4}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const-string v2, "StorageSessionController"

    invoke-static {v2, v0}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 459
    .end local p1    # "e":Landroid/os/RemoteException;
    :goto_2e
    return-void
.end method

.method private resolveExternalStorageServiceAsUser(I)Landroid/content/pm/ServiceInfo;
    .registers 5
    .param p1, "userId"    # I

    .line 502
    new-instance v0, Landroid/content/Intent;

    const-string v1, "android.service.storage.ExternalStorageService"

    invoke-direct {v0, v1}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    .line 503
    .local v0, "intent":Landroid/content/Intent;
    iget-object v1, p0, Lcom/android/server/storage/StorageSessionController;->mExternalStorageServicePackageName:Ljava/lang/String;

    invoke-virtual {v0, v1}, Landroid/content/Intent;->setPackage(Ljava/lang/String;)Landroid/content/Intent;

    .line 504
    iget-object v1, p0, Lcom/android/server/storage/StorageSessionController;->mContext:Landroid/content/Context;

    invoke-virtual {v1}, Landroid/content/Context;->getPackageManager()Landroid/content/pm/PackageManager;

    move-result-object v1

    const/16 v2, 0x84

    invoke-virtual {v1, v0, v2, p1}, Landroid/content/pm/PackageManager;->resolveServiceAsUser(Landroid/content/Intent;II)Landroid/content/pm/ResolveInfo;

    move-result-object v1

    .line 506
    .local v1, "resolveInfo":Landroid/content/pm/ResolveInfo;
    if-nez v1, :cond_1c

    .line 507
    const/4 v2, 0x0

    return-object v2

    .line 510
    :cond_1c
    iget-object v2, v1, Landroid/content/pm/ResolveInfo;->serviceInfo:Landroid/content/pm/ServiceInfo;

    return-object v2
.end method

.method private shouldHandle(Lcom/android/server/storage/ImmutableVolumeInfo;)Z
    .registers 3
    .param p1, "vol"    # Lcom/android/server/storage/ImmutableVolumeInfo;

    .line 490
    iget-boolean v0, p0, Lcom/android/server/storage/StorageSessionController;->mIsResetting:Z

    if-nez v0, :cond_e

    if-eqz p1, :cond_c

    invoke-static {p1}, Lcom/android/server/storage/StorageSessionController;->isSupportedVolume(Lcom/android/server/storage/ImmutableVolumeInfo;)Z

    move-result v0

    if-eqz v0, :cond_e

    :cond_c
    const/4 v0, 0x1

    goto :goto_f

    :cond_e
    const/4 v0, 0x0

    :goto_f
    return v0
.end method


# virtual methods
.method public freeCache(Ljava/lang/String;J)V
    .registers 9
    .param p1, "volumeUuid"    # Ljava/lang/String;
    .param p2, "bytes"    # J
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;
        }
    .end annotation

    .line 182
    iget-object v0, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v0

    .line 183
    :try_start_3
    iget-object v1, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v1}, Landroid/util/SparseArray;->size()I

    move-result v1

    .line 184
    .local v1, "size":I
    const/4 v2, 0x0

    .local v2, "i":I
    :goto_a
    if-ge v2, v1, :cond_25

    .line 185
    iget-object v3, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v3, v2}, Landroid/util/SparseArray;->keyAt(I)I

    move-result v3

    .line 186
    .local v3, "key":I
    iget-object v4, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v4, v3}, Landroid/util/SparseArray;->get(I)Ljava/lang/Object;

    move-result-object v4

    check-cast v4, Lcom/android/server/storage/StorageUserConnection;

    .line 187
    .local v4, "connection":Lcom/android/server/storage/StorageUserConnection;
    if-eqz v4, :cond_22

    .line 188
    invoke-virtual {v4, p1, p2, p3}, Lcom/android/server/storage/StorageUserConnection;->freeCache(Ljava/lang/String;J)V

    goto :goto_22

    .line 191
    .end local v1    # "size":I
    .end local v2    # "i":I
    .end local v3    # "key":I
    .end local v4    # "connection":Lcom/android/server/storage/StorageUserConnection;
    :catchall_20
    move-exception v1

    goto :goto_28

    .line 184
    .restart local v1    # "size":I
    .restart local v2    # "i":I
    :cond_22
    :goto_22
    add-int/lit8 v2, v2, 0x1

    goto :goto_a

    :cond_25
    nop

    .line 191
    .end local v1    # "size":I
    .end local v2    # "i":I
    monitor-exit v0

    .line 192
    return-void

    .line 191
    :goto_28
    monitor-exit v0
    :try_end_29
    .catchall {:try_start_3 .. :try_end_29} :catchall_20

    throw v1
.end method

.method public getConnectionUserIdForVolume(Lcom/android/server/storage/ImmutableVolumeInfo;)I
    .registers 6
    .param p1, "vol"    # Lcom/android/server/storage/ImmutableVolumeInfo;

    .line 84
    iget-object v0, p0, Lcom/android/server/storage/StorageSessionController;->mContext:Landroid/content/Context;

    .line 85
    invoke-virtual {p1}, Lcom/android/server/storage/ImmutableVolumeInfo;->getMountUserId()I

    move-result v1

    invoke-static {v1}, Landroid/os/UserHandle;->of(I)Landroid/os/UserHandle;

    move-result-object v1

    .line 84
    const/4 v2, 0x0

    invoke-virtual {v0, v1, v2}, Landroid/content/Context;->createContextAsUser(Landroid/os/UserHandle;I)Landroid/content/Context;

    move-result-object v0

    .line 86
    .local v0, "volumeUserContext":Landroid/content/Context;
    const-class v1, Landroid/os/UserManager;

    invoke-virtual {v0, v1}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v1

    check-cast v1, Landroid/os/UserManager;

    .line 87
    invoke-virtual {v1}, Landroid/os/UserManager;->isMediaSharedWithParent()Z

    move-result v1

    .line 89
    .local v1, "isMediaSharedWithParent":Z
    iget-object v2, p0, Lcom/android/server/storage/StorageSessionController;->mUserManager:Landroid/os/UserManager;

    invoke-virtual {p1}, Lcom/android/server/storage/ImmutableVolumeInfo;->getMountUserId()I

    move-result v3

    invoke-virtual {v2, v3}, Landroid/os/UserManager;->getUserInfo(I)Landroid/content/pm/UserInfo;

    move-result-object v2

    .line 90
    .local v2, "userInfo":Landroid/content/pm/UserInfo;
    if-eqz v2, :cond_2c

    if-eqz v1, :cond_2c

    .line 92
    iget v3, v2, Landroid/content/pm/UserInfo;->profileGroupId:I

    return v3

    .line 94
    :cond_2c
    invoke-virtual {p1}, Lcom/android/server/storage/ImmutableVolumeInfo;->getMountUserId()I

    move-result v3

    return v3
.end method

.method public getExternalStorageServiceComponentName()Landroid/content/ComponentName;
    .registers 2

    .line 394
    iget-object v0, p0, Lcom/android/server/storage/StorageSessionController;->mExternalStorageServiceComponent:Landroid/content/ComponentName;

    return-object v0
.end method

.method public isAppIoBlocked(I)Z
    .registers 5
    .param p1, "uid"    # I

    .line 439
    invoke-static {p1}, Landroid/os/UserHandle;->getUserId(I)I

    move-result v0

    .line 441
    .local v0, "userId":I
    iget-object v1, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v1

    .line 442
    :try_start_7
    iget-object v2, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v2, v0}, Landroid/util/SparseArray;->get(I)Ljava/lang/Object;

    move-result-object v2

    check-cast v2, Lcom/android/server/storage/StorageUserConnection;

    .line 443
    .local v2, "connection":Lcom/android/server/storage/StorageUserConnection;
    monitor-exit v1
    :try_end_10
    .catchall {:try_start_7 .. :try_end_10} :catchall_19

    .line 445
    if-eqz v2, :cond_17

    .line 446
    invoke-virtual {v2, p1}, Lcom/android/server/storage/StorageUserConnection;->isAppIoBlocked(I)Z

    move-result v1

    return v1

    .line 448
    :cond_17
    const/4 v1, 0x0

    return v1

    .line 443
    .end local v2    # "connection":Lcom/android/server/storage/StorageUserConnection;
    :catchall_19
    move-exception v2

    :try_start_1a
    monitor-exit v1
    :try_end_1b
    .catchall {:try_start_1a .. :try_end_1b} :catchall_19

    throw v2
.end method

.method public notifyAnrDelayStarted(Ljava/lang/String;III)V
    .registers 8
    .param p1, "packageName"    # Ljava/lang/String;
    .param p2, "uid"    # I
    .param p3, "tid"    # I
    .param p4, "reason"    # I
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;
        }
    .end annotation

    .line 201
    invoke-static {p2}, Landroid/os/UserHandle;->getUserId(I)I

    move-result v0

    .line 203
    .local v0, "userId":I
    iget-object v1, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v1

    .line 204
    :try_start_7
    iget-object v2, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v2, v0}, Landroid/util/SparseArray;->get(I)Ljava/lang/Object;

    move-result-object v2

    check-cast v2, Lcom/android/server/storage/StorageUserConnection;

    .line 205
    .local v2, "connection":Lcom/android/server/storage/StorageUserConnection;
    monitor-exit v1
    :try_end_10
    .catchall {:try_start_7 .. :try_end_10} :catchall_16

    .line 207
    if-eqz v2, :cond_15

    .line 208
    invoke-virtual {v2, p1, p2, p3, p4}, Lcom/android/server/storage/StorageUserConnection;->notifyAnrDelayStarted(Ljava/lang/String;III)V

    .line 210
    :cond_15
    return-void

    .line 205
    .end local v2    # "connection":Lcom/android/server/storage/StorageUserConnection;
    :catchall_16
    move-exception v2

    :try_start_17
    monitor-exit v1
    :try_end_18
    .catchall {:try_start_17 .. :try_end_18} :catchall_16

    throw v2
.end method

.method public notifyAppIoBlocked(Ljava/lang/String;III)V
    .registers 8
    .param p1, "volumeUuid"    # Ljava/lang/String;
    .param p2, "uid"    # I
    .param p3, "tid"    # I
    .param p4, "reason"    # I

    .line 407
    invoke-static {p2}, Landroid/os/UserHandle;->getUserId(I)I

    move-result v0

    .line 409
    .local v0, "userId":I
    iget-object v1, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v1

    .line 410
    :try_start_7
    iget-object v2, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v2, v0}, Landroid/util/SparseArray;->get(I)Ljava/lang/Object;

    move-result-object v2

    check-cast v2, Lcom/android/server/storage/StorageUserConnection;

    .line 411
    .local v2, "connection":Lcom/android/server/storage/StorageUserConnection;
    monitor-exit v1
    :try_end_10
    .catchall {:try_start_7 .. :try_end_10} :catchall_16

    .line 413
    if-eqz v2, :cond_15

    .line 414
    invoke-virtual {v2, p1, p2, p3, p4}, Lcom/android/server/storage/StorageUserConnection;->notifyAppIoBlocked(Ljava/lang/String;III)V

    .line 416
    :cond_15
    return-void

    .line 411
    .end local v2    # "connection":Lcom/android/server/storage/StorageUserConnection;
    :catchall_16
    move-exception v2

    :try_start_17
    monitor-exit v1
    :try_end_18
    .catchall {:try_start_17 .. :try_end_18} :catchall_16

    throw v2
.end method

.method public notifyAppIoResumed(Ljava/lang/String;III)V
    .registers 8
    .param p1, "volumeUuid"    # Ljava/lang/String;
    .param p2, "uid"    # I
    .param p3, "tid"    # I
    .param p4, "reason"    # I

    .line 426
    invoke-static {p2}, Landroid/os/UserHandle;->getUserId(I)I

    move-result v0

    .line 428
    .local v0, "userId":I
    iget-object v1, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v1

    .line 429
    :try_start_7
    iget-object v2, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v2, v0}, Landroid/util/SparseArray;->get(I)Ljava/lang/Object;

    move-result-object v2

    check-cast v2, Lcom/android/server/storage/StorageUserConnection;

    .line 430
    .local v2, "connection":Lcom/android/server/storage/StorageUserConnection;
    monitor-exit v1
    :try_end_10
    .catchall {:try_start_7 .. :try_end_10} :catchall_16

    .line 432
    if-eqz v2, :cond_15

    .line 433
    invoke-virtual {v2, p1, p2, p3, p4}, Lcom/android/server/storage/StorageUserConnection;->notifyAppIoResumed(Ljava/lang/String;III)V

    .line 435
    :cond_15
    return-void

    .line 430
    .end local v2    # "connection":Lcom/android/server/storage/StorageUserConnection;
    :catchall_16
    move-exception v2

    :try_start_17
    monitor-exit v1
    :try_end_18
    .catchall {:try_start_17 .. :try_end_18} :catchall_16

    throw v2
.end method

.method public notifyVolumeStateChanged(Lcom/android/server/storage/ImmutableVolumeInfo;)V
    .registers 8
    .param p1, "vol"    # Lcom/android/server/storage/ImmutableVolumeInfo;
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;
        }
    .end annotation

    .line 150
    invoke-direct {p0, p1}, Lcom/android/server/storage/StorageSessionController;->shouldHandle(Lcom/android/server/storage/ImmutableVolumeInfo;)Z

    move-result v0

    if-nez v0, :cond_7

    .line 151
    return-void

    .line 153
    :cond_7
    invoke-virtual {p1}, Lcom/android/server/storage/ImmutableVolumeInfo;->getId()Ljava/lang/String;

    move-result-object v0

    .line 154
    .local v0, "sessionId":Ljava/lang/String;
    invoke-virtual {p0, p1}, Lcom/android/server/storage/StorageSessionController;->getConnectionUserIdForVolume(Lcom/android/server/storage/ImmutableVolumeInfo;)I

    move-result v1

    .line 156
    .local v1, "connectionUserId":I
    const/4 v2, 0x0

    .line 157
    .local v2, "connection":Lcom/android/server/storage/StorageUserConnection;
    iget-object v3, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v3

    .line 158
    :try_start_13
    iget-object v4, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v4, v1}, Landroid/util/SparseArray;->get(I)Ljava/lang/Object;

    move-result-object v4

    check-cast v4, Lcom/android/server/storage/StorageUserConnection;

    move-object v2, v4

    .line 159
    monitor-exit v3
    :try_end_1d
    .catchall {:try_start_13 .. :try_end_1d} :catchall_5b

    .line 161
    if-eqz v2, :cond_44

    .line 162
    const-string v3, "StorageSessionController"

    new-instance v4, Ljava/lang/StringBuilder;

    invoke-direct {v4}, Ljava/lang/StringBuilder;-><init>()V

    const-string v5, "Notifying volume state changed for session with id: "

    invoke-virtual {v4, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v4, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v4}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v4

    invoke-static {v3, v4}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 163
    iget-object v3, p0, Lcom/android/server/storage/StorageSessionController;->mContext:Landroid/content/Context;

    .line 164
    invoke-virtual {p1}, Lcom/android/server/storage/ImmutableVolumeInfo;->getMountUserId()I

    move-result v4

    const/4 v5, 0x0

    invoke-virtual {p1, v3, v4, v5}, Lcom/android/server/storage/ImmutableVolumeInfo;->buildStorageVolume(Landroid/content/Context;IZ)Landroid/os/storage/StorageVolume;

    move-result-object v3

    .line 163
    invoke-virtual {v2, v0, v3}, Lcom/android/server/storage/StorageUserConnection;->notifyVolumeStateChanged(Ljava/lang/String;Landroid/os/storage/StorageVolume;)V

    goto :goto_5a

    .line 166
    :cond_44
    const-string v3, "StorageSessionController"

    new-instance v4, Ljava/lang/StringBuilder;

    invoke-direct {v4}, Ljava/lang/StringBuilder;-><init>()V

    const-string v5, "No available storage user connection for userId : "

    invoke-virtual {v4, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v4, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    invoke-virtual {v4}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v4

    invoke-static {v3, v4}, Landroid/util/Slog;->w(Ljava/lang/String;Ljava/lang/String;)I

    .line 169
    :goto_5a
    return-void

    .line 159
    :catchall_5b
    move-exception v4

    :try_start_5c
    monitor-exit v3
    :try_end_5d
    .catchall {:try_start_5c .. :try_end_5d} :catchall_5b

    throw v4
.end method

.method public onReset(Landroid/os/IVold;Ljava/lang/Runnable;)V
    .registers 12
    .param p1, "vold"    # Landroid/os/IVold;
    .param p2, "resetHandlerRunnable"    # Ljava/lang/Runnable;

    .line 312
    const/4 v0, 0x0

    invoke-direct {p0, v0}, Lcom/android/server/storage/StorageSessionController;->shouldHandle(Lcom/android/server/storage/ImmutableVolumeInfo;)Z

    move-result v0

    if-nez v0, :cond_8

    .line 313
    return-void

    .line 316
    :cond_8
    new-instance v0, Landroid/util/SparseArray;

    invoke-direct {v0}, Landroid/util/SparseArray;-><init>()V

    .line 317
    .local v0, "connections":Landroid/util/SparseArray;, "Landroid/util/SparseArray<Lcom/android/server/storage/StorageUserConnection;>;"
    iget-object v1, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v1

    .line 318
    const/4 v2, 0x1

    :try_start_11
    iput-boolean v2, p0, Lcom/android/server/storage/StorageSessionController;->mIsResetting:Z

    .line 319
    const-string v2, "StorageSessionController"

    const-string v3, "Started resetting external storage service..."

    invoke-static {v2, v3}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 320
    const/4 v2, 0x0

    .local v2, "i":I
    :goto_1b
    iget-object v3, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v3}, Landroid/util/SparseArray;->size()I

    move-result v3

    if-ge v2, v3, :cond_3a

    .line 321
    iget-object v3, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v3, v2}, Landroid/util/SparseArray;->keyAt(I)I

    move-result v3

    iget-object v4, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v4, v2}, Landroid/util/SparseArray;->valueAt(I)Ljava/lang/Object;

    move-result-object v4

    check-cast v4, Lcom/android/server/storage/StorageUserConnection;

    invoke-virtual {v0, v3, v4}, Landroid/util/SparseArray;->put(ILjava/lang/Object;)V

    .line 320
    add-int/lit8 v2, v2, 0x1

    goto :goto_1b

    .line 323
    .end local v2    # "i":I
    :catchall_37
    move-exception v2

    goto/16 :goto_11d

    .line 320
    .restart local v2    # "i":I
    :cond_3a
    nop

    .line 323
    .end local v2    # "i":I
    monitor-exit v1
    :try_end_3c
    .catchall {:try_start_11 .. :try_end_3c} :catchall_37

    .line 325
    const/4 v1, 0x0

    .local v1, "i":I
    :goto_3d
    invoke-virtual {v0}, Landroid/util/SparseArray;->size()I

    move-result v2

    if-ge v1, v2, :cond_102

    .line 326
    invoke-virtual {v0, v1}, Landroid/util/SparseArray;->valueAt(I)Ljava/lang/Object;

    move-result-object v2

    check-cast v2, Lcom/android/server/storage/StorageUserConnection;

    .line 327
    .local v2, "connection":Lcom/android/server/storage/StorageUserConnection;
    invoke-virtual {v2}, Lcom/android/server/storage/StorageUserConnection;->getAllSessionIds()Ljava/util/Set;

    move-result-object v3

    invoke-interface {v3}, Ljava/util/Set;->iterator()Ljava/util/Iterator;

    move-result-object v3

    :goto_51
    invoke-interface {v3}, Ljava/util/Iterator;->hasNext()Z

    move-result v4

    nop

    if-eqz v4, :cond_fb

    invoke-interface {v3}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v4

    check-cast v4, Ljava/lang/String;

    .line 329
    .local v4, "sessionId":Ljava/lang/String;
    :try_start_5e
    const-string v5, "StorageSessionController"

    new-instance v6, Ljava/lang/StringBuilder;

    invoke-direct {v6}, Ljava/lang/StringBuilder;-><init>()V

    const-string v7, "Unmounting "

    invoke-virtual {v6, v7}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v6, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v6}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v6

    invoke-static {v5, v6}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 330
    invoke-interface {p1, v4}, Landroid/os/IVold;->unmount(Ljava/lang/String;)V

    .line 331
    const-string v5, "StorageSessionController"

    new-instance v6, Ljava/lang/StringBuilder;

    invoke-direct {v6}, Ljava/lang/StringBuilder;-><init>()V

    const-string v7, "Unmounted "

    invoke-virtual {v6, v7}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v6, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v6}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v6

    invoke-static {v5, v6}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_8d
    .catch Landroid/os/ServiceSpecificException; {:try_start_5e .. :try_end_8d} :catch_8e
    .catch Landroid/os/RemoteException; {:try_start_5e .. :try_end_8d} :catch_8e

    .line 335
    goto :goto_a5

    .line 332
    :catch_8e
    move-exception v5

    .line 334
    .local v5, "e":Ljava/lang/Exception;
    const-string v6, "StorageSessionController"

    new-instance v7, Ljava/lang/StringBuilder;

    invoke-direct {v7}, Ljava/lang/StringBuilder;-><init>()V

    const-string v8, "Failed to unmount volume: "

    invoke-virtual {v7, v8}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v7, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v7}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v7

    invoke-static {v6, v7, v5}, Landroid/util/Slog;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I

    .line 338
    .end local v5    # "e":Ljava/lang/Exception;
    :goto_a5
    :try_start_a5
    const-string v5, "StorageSessionController"

    new-instance v6, Ljava/lang/StringBuilder;

    invoke-direct {v6}, Ljava/lang/StringBuilder;-><init>()V

    const-string v7, "Exiting "

    invoke-virtual {v6, v7}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v6, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v6}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v6

    invoke-static {v5, v6}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 339
    invoke-virtual {v2, v4}, Lcom/android/server/storage/StorageUserConnection;->removeSessionAndWait(Ljava/lang/String;)V

    .line 340
    const-string v5, "StorageSessionController"

    new-instance v6, Ljava/lang/StringBuilder;

    invoke-direct {v6}, Ljava/lang/StringBuilder;-><init>()V

    const-string v7, "Exited "

    invoke-virtual {v6, v7}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v6, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v6}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v6

    invoke-static {v5, v6}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I
    :try_end_d4
    .catch Ljava/lang/IllegalStateException; {:try_start_a5 .. :try_end_d4} :catch_d7
    .catch Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException; {:try_start_a5 .. :try_end_d4} :catch_d7

    .line 348
    nop

    .line 349
    .end local v4    # "sessionId":Ljava/lang/String;
    goto/16 :goto_51

    .line 341
    .restart local v4    # "sessionId":Ljava/lang/String;
    :catch_d7
    move-exception v3

    .line 342
    .local v3, "e":Ljava/lang/Exception;
    const-string v5, "StorageSessionController"

    new-instance v6, Ljava/lang/StringBuilder;

    invoke-direct {v6}, Ljava/lang/StringBuilder;-><init>()V

    const-string v7, "Failed to exit session: "

    invoke-virtual {v6, v7}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v6, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v7, ". Killing MediaProvider..."

    invoke-virtual {v6, v7}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v6}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v6

    invoke-static {v5, v6, v3}, Landroid/util/Slog;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I

    .line 346
    invoke-virtual {v0, v1}, Landroid/util/SparseArray;->keyAt(I)I

    move-result v5

    invoke-direct {p0, v5}, Lcom/android/server/storage/StorageSessionController;->killExternalStorageService(I)V

    .line 347
    nop

    .line 350
    .end local v3    # "e":Ljava/lang/Exception;
    .end local v4    # "sessionId":Ljava/lang/String;
    :cond_fb
    invoke-virtual {v2}, Lcom/android/server/storage/StorageUserConnection;->close()V

    .line 325
    .end local v2    # "connection":Lcom/android/server/storage/StorageUserConnection;
    add-int/lit8 v1, v1, 0x1

    goto/16 :goto_3d

    :cond_102
    nop

    .line 353
    .end local v1    # "i":I
    invoke-interface {p2}, Ljava/lang/Runnable;->run()V

    .line 354
    iget-object v2, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v2

    .line 355
    :try_start_109
    iget-object v1, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v1}, Landroid/util/SparseArray;->clear()V

    .line 356
    const/4 v1, 0x0

    iput-boolean v1, p0, Lcom/android/server/storage/StorageSessionController;->mIsResetting:Z

    .line 357
    const-string v1, "StorageSessionController"

    const-string v3, "Finished resetting external storage service"

    invoke-static {v1, v3}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 358
    monitor-exit v2

    .line 359
    return-void

    .line 358
    :catchall_11a
    move-exception v1

    monitor-exit v2
    :try_end_11c
    .catchall {:try_start_109 .. :try_end_11c} :catchall_11a

    throw v1

    .line 323
    :goto_11d
    :try_start_11d
    monitor-exit v1
    :try_end_11e
    .catchall {:try_start_11d .. :try_end_11e} :catchall_37

    throw v2
.end method

.method public onUnlockUser(I)V
    .registers 4
    .param p1, "userId"    # I
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;
        }
    .end annotation

    .line 274
    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    const-string v1, "On user unlock "

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v0, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const-string v1, "StorageSessionController"

    invoke-static {v1, v0}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 275
    if-nez p1, :cond_1b

    .line 276
    invoke-direct {p0}, Lcom/android/server/storage/StorageSessionController;->initExternalStorageServiceComponent()V

    .line 278
    :cond_1b
    return-void
.end method

.method public onUserStopping(I)V
    .registers 6
    .param p1, "userId"    # I

    .line 289
    const/4 v0, 0x0

    invoke-direct {p0, v0}, Lcom/android/server/storage/StorageSessionController;->shouldHandle(Lcom/android/server/storage/ImmutableVolumeInfo;)Z

    move-result v0

    if-nez v0, :cond_8

    .line 290
    return-void

    .line 292
    :cond_8
    const/4 v0, 0x0

    .line 293
    .local v0, "connection":Lcom/android/server/storage/StorageUserConnection;
    iget-object v1, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v1

    .line 294
    :try_start_c
    iget-object v2, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v2, p1}, Landroid/util/SparseArray;->get(I)Ljava/lang/Object;

    move-result-object v2

    check-cast v2, Lcom/android/server/storage/StorageUserConnection;

    move-object v0, v2

    .line 295
    monitor-exit v1
    :try_end_16
    .catchall {:try_start_c .. :try_end_16} :catchall_49

    .line 297
    if-eqz v0, :cond_32

    .line 298
    const-string v1, "StorageSessionController"

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const-string v3, "Removing all sessions for user: "

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-static {v1, v2}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 299
    invoke-virtual {v0}, Lcom/android/server/storage/StorageUserConnection;->removeAllSessions()V

    goto :goto_48

    .line 301
    :cond_32
    const-string v1, "StorageSessionController"

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const-string v3, "No connection found for user: "

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-static {v1, v2}, Landroid/util/Slog;->w(Ljava/lang/String;Ljava/lang/String;)I

    .line 303
    :goto_48
    return-void

    .line 295
    :catchall_49
    move-exception v2

    :try_start_4a
    monitor-exit v1
    :try_end_4b
    .catchall {:try_start_4a .. :try_end_4b} :catchall_49

    throw v2
.end method

.method public onVolumeMount(Landroid/os/ParcelFileDescriptor;Lcom/android/server/storage/ImmutableVolumeInfo;)V
    .registers 10
    .param p1, "deviceFd"    # Landroid/os/ParcelFileDescriptor;
    .param p2, "vol"    # Lcom/android/server/storage/ImmutableVolumeInfo;
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Lcom/android/server/storage/StorageSessionController$ExternalStorageServiceException;
        }
    .end annotation

    .line 114
    invoke-direct {p0, p2}, Lcom/android/server/storage/StorageSessionController;->shouldHandle(Lcom/android/server/storage/ImmutableVolumeInfo;)Z

    move-result v0

    if-nez v0, :cond_7

    .line 115
    return-void

    .line 118
    :cond_7
    const-string v0, "StorageSessionController"

    new-instance v1, Ljava/lang/StringBuilder;

    invoke-direct {v1}, Ljava/lang/StringBuilder;-><init>()V

    const-string v2, "On volume mount "

    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v1, p2}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    invoke-static {v0, v1}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 120
    invoke-virtual {p2}, Lcom/android/server/storage/ImmutableVolumeInfo;->getId()Ljava/lang/String;

    move-result-object v0

    .line 121
    .local v0, "sessionId":Ljava/lang/String;
    invoke-virtual {p0, p2}, Lcom/android/server/storage/StorageSessionController;->getConnectionUserIdForVolume(Lcom/android/server/storage/ImmutableVolumeInfo;)I

    move-result v1

    .line 123
    .local v1, "userId":I
    const/4 v2, 0x0

    .line 124
    .local v2, "connection":Lcom/android/server/storage/StorageUserConnection;
    iget-object v3, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v3

    .line 125
    :try_start_29
    iget-object v4, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v4, v1}, Landroid/util/SparseArray;->get(I)Ljava/lang/Object;

    move-result-object v4

    check-cast v4, Lcom/android/server/storage/StorageUserConnection;

    move-object v2, v4

    .line 126
    if-nez v2, :cond_5a

    .line 127
    const-string v4, "StorageSessionController"

    new-instance v5, Ljava/lang/StringBuilder;

    invoke-direct {v5}, Ljava/lang/StringBuilder;-><init>()V

    const-string v6, "Creating connection for user: "

    invoke-virtual {v5, v6}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v5, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    invoke-virtual {v5}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v5

    invoke-static {v4, v5}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 128
    new-instance v4, Lcom/android/server/storage/StorageUserConnection;

    iget-object v5, p0, Lcom/android/server/storage/StorageSessionController;->mContext:Landroid/content/Context;

    invoke-direct {v4, v5, v1, p0}, Lcom/android/server/storage/StorageUserConnection;-><init>(Landroid/content/Context;ILcom/android/server/storage/StorageSessionController;)V

    move-object v2, v4

    .line 129
    iget-object v4, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v4, v1, v2}, Landroid/util/SparseArray;->put(ILjava/lang/Object;)V

    goto :goto_5a

    .line 131
    :catchall_58
    move-exception v4

    goto :goto_85

    :cond_5a
    :goto_5a
    monitor-exit v3
    :try_end_5b
    .catchall {:try_start_29 .. :try_end_5b} :catchall_58

    .line 132
    const-string v3, "StorageSessionController"

    new-instance v4, Ljava/lang/StringBuilder;

    invoke-direct {v4}, Ljava/lang/StringBuilder;-><init>()V

    const-string v5, "Creating and starting session with id: "

    invoke-virtual {v4, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v4, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v4}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v4

    invoke-static {v3, v4}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 133
    invoke-virtual {p2}, Lcom/android/server/storage/ImmutableVolumeInfo;->getPath()Ljava/io/File;

    move-result-object v3

    invoke-virtual {v3}, Ljava/io/File;->getPath()Ljava/lang/String;

    move-result-object v3

    .line 134
    invoke-virtual {p2}, Lcom/android/server/storage/ImmutableVolumeInfo;->getInternalPath()Ljava/io/File;

    move-result-object v4

    invoke-virtual {v4}, Ljava/io/File;->getPath()Ljava/lang/String;

    move-result-object v4

    .line 133
    invoke-virtual {v2, v0, p1, v3, v4}, Lcom/android/server/storage/StorageUserConnection;->startSession(Ljava/lang/String;Landroid/os/ParcelFileDescriptor;Ljava/lang/String;Ljava/lang/String;)V

    .line 135
    return-void

    .line 131
    :goto_85
    :try_start_85
    monitor-exit v3
    :try_end_86
    .catchall {:try_start_85 .. :try_end_86} :catchall_58

    throw v4
.end method

.method public onVolumeRemove(Lcom/android/server/storage/ImmutableVolumeInfo;)Lcom/android/server/storage/StorageUserConnection;
    .registers 9
    .param p1, "vol"    # Lcom/android/server/storage/ImmutableVolumeInfo;

    .line 221
    invoke-direct {p0, p1}, Lcom/android/server/storage/StorageSessionController;->shouldHandle(Lcom/android/server/storage/ImmutableVolumeInfo;)Z

    move-result v0

    const/4 v1, 0x0

    if-nez v0, :cond_8

    .line 222
    return-object v1

    .line 225
    :cond_8
    const-string v0, "StorageSessionController"

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const-string v3, "On volume remove "

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-static {v0, v2}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 226
    invoke-virtual {p1}, Lcom/android/server/storage/ImmutableVolumeInfo;->getId()Ljava/lang/String;

    move-result-object v0

    .line 227
    .local v0, "sessionId":Ljava/lang/String;
    invoke-virtual {p0, p1}, Lcom/android/server/storage/StorageSessionController;->getConnectionUserIdForVolume(Lcom/android/server/storage/ImmutableVolumeInfo;)I

    move-result v2

    .line 229
    .local v2, "userId":I
    const/4 v3, 0x0

    .line 230
    .local v3, "connection":Lcom/android/server/storage/StorageUserConnection;
    iget-object v4, p0, Lcom/android/server/storage/StorageSessionController;->mLock:Ljava/lang/Object;

    monitor-enter v4

    .line 231
    :try_start_2a
    iget-object v5, p0, Lcom/android/server/storage/StorageSessionController;->mConnections:Landroid/util/SparseArray;

    invoke-virtual {v5, v2}, Landroid/util/SparseArray;->get(I)Ljava/lang/Object;

    move-result-object v5

    check-cast v5, Lcom/android/server/storage/StorageUserConnection;

    move-object v3, v5

    .line 232
    monitor-exit v4
    :try_end_34
    .catchall {:try_start_2a .. :try_end_34} :catchall_67

    .line 234
    if-eqz v3, :cond_50

    .line 235
    const-string v1, "StorageSessionController"

    new-instance v4, Ljava/lang/StringBuilder;

    invoke-direct {v4}, Ljava/lang/StringBuilder;-><init>()V

    const-string v5, "Removed session for vol with id: "

    invoke-virtual {v4, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v4, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v4}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v4

    invoke-static {v1, v4}, Landroid/util/Slog;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 236
    invoke-virtual {v3, v0}, Lcom/android/server/storage/StorageUserConnection;->removeSession(Ljava/lang/String;)Lcom/android/server/storage/StorageUserConnection$Session;

    .line 237
    return-object v3

    .line 239
    :cond_50
    const-string v4, "StorageSessionController"

    new-instance v5, Ljava/lang/StringBuilder;

    invoke-direct {v5}, Ljava/lang/StringBuilder;-><init>()V

    const-string v6, "Session already removed for vol with id: "

    invoke-virtual {v5, v6}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v5, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v5}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v5

    invoke-static {v4, v5}, Landroid/util/Slog;->w(Ljava/lang/String;Ljava/lang/String;)I

    .line 240
    return-object v1

    .line 232
    :catchall_67
    move-exception v1

    :try_start_68
    monitor-exit v4
    :try_end_69
    .catchall {:try_start_68 .. :try_end_69} :catchall_67

    throw v1
.end method

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

.method public supportsExternalStorage(I)Z
    .registers 3
    .param p1, "userId"    # I

    .line 498
    invoke-direct {p0, p1}, Lcom/android/server/storage/StorageSessionController;->resolveExternalStorageServiceAsUser(I)Landroid/content/pm/ServiceInfo;

    move-result-object v0

    if-eqz v0, :cond_8

    const/4 v0, 0x1

    goto :goto_9

    :cond_8
    const/4 v0, 0x0

    :goto_9
    return v0
.end method
