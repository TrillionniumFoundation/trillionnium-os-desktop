.class public Lcom/android/gallery3d/app/GalleryAppImpl;
.super Landroid/app/Application;
.source "GalleryAppImpl.java"

# interfaces
.implements Lcom/android/gallery3d/app/GalleryApp;


# instance fields
.field private mDataManager:Lcom/android/gallery3d/data/DataManager;

.field private mDownloadCache:Lcom/android/gallery3d/data/DownloadCache;

.field private mImageCacheService:Lcom/android/gallery3d/data/ImageCacheService;

.field private mLock:Ljava/lang/Object;

.field private mThreadPool:Lcom/android/gallery3d/util/ThreadPool;


# direct methods
.method public constructor <init>()V
    .registers 2

    .line 35
    invoke-direct {p0}, Landroid/app/Application;-><init>()V

    .line 41
    new-instance v0, Ljava/lang/Object;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object v0, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mLock:Ljava/lang/Object;

    return-void
.end method

.method private initializeAsyncTask()V
    .registers 1

    .line 110
    :try_start_0
    const-class p0, Landroid/os/AsyncTask;

    invoke-virtual {p0}, Ljava/lang/Class;->getName()Ljava/lang/String;

    move-result-object p0

    invoke-static {p0}, Ljava/lang/Class;->forName(Ljava/lang/String;)Ljava/lang/Class;
    :try_end_9
    .catch Ljava/lang/ClassNotFoundException; {:try_start_0 .. :try_end_9} :catch_9

    :catch_9
    return-void
.end method


# virtual methods
.method public getAndroidContext()Landroid/content/Context;
    .registers 1

    return-object p0
.end method

.method public declared-synchronized getDataManager()Lcom/android/gallery3d/data/DataManager;
    .registers 2

    monitor-enter p0

    .line 63
    :try_start_1
    iget-object v0, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mDataManager:Lcom/android/gallery3d/data/DataManager;

    if-nez v0, :cond_12

    .line 64
    new-instance v0, Lcom/android/gallery3d/data/DataManager;

    invoke-direct {v0, p0}, Lcom/android/gallery3d/data/DataManager;-><init>(Lcom/android/gallery3d/app/GalleryApp;)V

    iput-object v0, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mDataManager:Lcom/android/gallery3d/data/DataManager;

    .line 65
    invoke-virtual {v0}, Lcom/android/gallery3d/data/DataManager;->initializeSourceMap()V

    goto :goto_12

    :catchall_10
    move-exception v0

    goto :goto_16

    .line 67
    :cond_12
    :goto_12
    iget-object v0, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mDataManager:Lcom/android/gallery3d/data/DataManager;
    :try_end_14
    .catchall {:try_start_1 .. :try_end_14} :catchall_10

    monitor-exit p0

    return-object v0

    :goto_16
    :try_start_16
    monitor-exit p0
    :try_end_17
    .catchall {:try_start_16 .. :try_end_17} :catchall_10

    throw v0
.end method

.method public declared-synchronized getDownloadCache()Lcom/android/gallery3d/data/DownloadCache;
    .registers 5

    const-string v0, "fail to create: "

    monitor-enter p0

    .line 92
    :try_start_3
    iget-object v1, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mDownloadCache:Lcom/android/gallery3d/data/DownloadCache;

    if-nez v1, :cond_45

    .line 93
    new-instance v1, Ljava/io/File;

    invoke-virtual {p0}, Landroid/app/Application;->getExternalCacheDir()Ljava/io/File;

    move-result-object v2

    const-string v3, "download"

    invoke-direct {v1, v2, v3}, Ljava/io/File;-><init>(Ljava/io/File;Ljava/lang/String;)V

    .line 95
    invoke-virtual {v1}, Ljava/io/File;->isDirectory()Z

    move-result v2

    if-nez v2, :cond_1e

    invoke-virtual {v1}, Ljava/io/File;->mkdirs()Z

    goto :goto_1e

    :catchall_1c
    move-exception v0

    goto :goto_49

    .line 97
    :cond_1e
    :goto_1e
    invoke-virtual {v1}, Ljava/io/File;->isDirectory()Z

    move-result v2

    if-eqz v2, :cond_2f

    .line 101
    new-instance v0, Lcom/android/gallery3d/data/DownloadCache;

    const-wide/32 v2, 0x4000000

    invoke-direct {v0, p0, v1, v2, v3}, Lcom/android/gallery3d/data/DownloadCache;-><init>(Lcom/android/gallery3d/app/GalleryApp;Ljava/io/File;J)V

    iput-object v0, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mDownloadCache:Lcom/android/gallery3d/data/DownloadCache;

    goto :goto_45

    .line 98
    :cond_2f
    new-instance v2, Ljava/lang/RuntimeException;

    new-instance v3, Ljava/lang/StringBuilder;

    invoke-direct {v3, v0}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    .line 99
    invoke-virtual {v1}, Ljava/io/File;->getAbsolutePath()Ljava/lang/String;

    move-result-object v0

    invoke-virtual {v3, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    invoke-direct {v2, v0}, Ljava/lang/RuntimeException;-><init>(Ljava/lang/String;)V

    throw v2

    .line 103
    :cond_45
    :goto_45
    iget-object v0, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mDownloadCache:Lcom/android/gallery3d/data/DownloadCache;
    :try_end_47
    .catchall {:try_start_3 .. :try_end_47} :catchall_1c

    monitor-exit p0

    return-object v0

    :goto_49
    :try_start_49
    monitor-exit p0
    :try_end_4a
    .catchall {:try_start_49 .. :try_end_4a} :catchall_1c

    throw v0
.end method

.method public getImageCacheService()Lcom/android/gallery3d/data/ImageCacheService;
    .registers 4

    .line 74
    iget-object v0, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mLock:Ljava/lang/Object;

    monitor-enter v0

    .line 75
    :try_start_3
    iget-object v1, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mImageCacheService:Lcom/android/gallery3d/data/ImageCacheService;

    if-nez v1, :cond_15

    .line 76
    new-instance v1, Lcom/android/gallery3d/data/ImageCacheService;

    invoke-virtual {p0}, Lcom/android/gallery3d/app/GalleryAppImpl;->getAndroidContext()Landroid/content/Context;

    move-result-object v2

    invoke-direct {v1, v2}, Lcom/android/gallery3d/data/ImageCacheService;-><init>(Landroid/content/Context;)V

    iput-object v1, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mImageCacheService:Lcom/android/gallery3d/data/ImageCacheService;

    goto :goto_15

    :catchall_13
    move-exception p0

    goto :goto_19

    .line 78
    :cond_15
    :goto_15
    iget-object p0, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mImageCacheService:Lcom/android/gallery3d/data/ImageCacheService;

    monitor-exit v0

    return-object p0

    .line 79
    :goto_19
    monitor-exit v0
    :try_end_1a
    .catchall {:try_start_3 .. :try_end_1a} :catchall_13

    throw p0
.end method

.method public declared-synchronized getThreadPool()Lcom/android/gallery3d/util/ThreadPool;
    .registers 2

    monitor-enter p0

    .line 84
    :try_start_1
    iget-object v0, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mThreadPool:Lcom/android/gallery3d/util/ThreadPool;

    if-nez v0, :cond_f

    .line 85
    new-instance v0, Lcom/android/gallery3d/util/ThreadPool;

    invoke-direct {v0}, Lcom/android/gallery3d/util/ThreadPool;-><init>()V

    iput-object v0, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mThreadPool:Lcom/android/gallery3d/util/ThreadPool;

    goto :goto_f

    :catchall_d
    move-exception v0

    goto :goto_13

    .line 87
    :cond_f
    :goto_f
    iget-object v0, p0, Lcom/android/gallery3d/app/GalleryAppImpl;->mThreadPool:Lcom/android/gallery3d/util/ThreadPool;
    :try_end_11
    .catchall {:try_start_1 .. :try_end_11} :catchall_d

    monitor-exit p0

    return-object v0

    :goto_13
    :try_start_13
    monitor-exit p0
    :try_end_14
    .catchall {:try_start_13 .. :try_end_14} :catchall_d

    throw v0
.end method

.method public onCreate()V
    .registers 1

    .line 48
    invoke-super {p0}, Landroid/app/Application;->onCreate()V

    .line 49
    invoke-direct {p0}, Lcom/android/gallery3d/app/GalleryAppImpl;->initializeAsyncTask()V

    .line 50
    invoke-static {p0}, Lcom/android/gallery3d/util/GalleryUtils;->initialize(Landroid/content/Context;)V

    .line 51
    invoke-static {p0}, Lcom/android/gallery3d/gadget/WidgetUtils;->initialize(Landroid/content/Context;)V

    .line 52
    invoke-static {p0}, Lcom/android/gallery3d/picasasource/PicasaSource;->initialize(Landroid/content/Context;)V

    .line 53
    invoke-static {p0}, Lcom/android/gallery3d/util/UsageStatistics;->initialize(Landroid/content/Context;)V

    return-void
.end method
