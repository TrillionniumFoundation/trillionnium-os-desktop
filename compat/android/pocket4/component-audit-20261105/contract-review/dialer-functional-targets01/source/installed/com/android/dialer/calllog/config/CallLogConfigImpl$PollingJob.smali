.class public final Lcom/android/dialer/calllog/config/CallLogConfigImpl$PollingJob;
.super Landroid/app/job/JobService;
.source "go/retraceme 9af01222c9f0ce13808ff8a71a2aad063a10a8b4d085240df3537e8ca2c7d173"


# direct methods
.method public constructor <init>()V
    .registers 1

    invoke-direct {p0}, Landroid/app/job/JobService;-><init>()V

    return-void
.end method


# virtual methods
.method public final onStartJob(Landroid/app/job/JobParameters;)Z
    .registers 12

    const-string v0, "PollingJob.onStartJob"

    invoke-static {v0}, Lcom/android/dialer/common/LogUtil;->enterBlock(Ljava/lang/String;)V

    invoke-virtual {p0}, Landroid/app/job/JobService;->getApplicationContext()Landroid/content/Context;

    move-result-object v0

    invoke-static {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$SpamComponentImpl;->get$2(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$SpamComponentImpl;

    move-result-object v0

    invoke-virtual {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$SpamComponentImpl;->callLogConfig()Lcom/android/dialer/calllog/config/CallLogConfigImpl;

    move-result-object v0

    iget-object v1, v0, Lcom/android/dialer/calllog/config/CallLogConfigImpl;->backgroundExecutor:Lcom/google/common/util/concurrent/ListeningExecutorService;

    iget-object v2, v0, Lcom/android/dialer/calllog/config/CallLogConfigImpl;->configProvider:Lcom/android/dialer/configprovider/SharedPrefConfigProvider;

    const-string v3, "new_call_log_fragment_enabled"

    const/4 v4, 0x0

    invoke-virtual {v2, v3, v4}, Lcom/android/dialer/configprovider/SharedPrefConfigProvider;->getBoolean(Ljava/lang/String;Z)Z

    move-result v3

    const-string v5, "new_voicemail_fragment_enabled"

    invoke-virtual {v2, v5, v4}, Lcom/android/dialer/configprovider/SharedPrefConfigProvider;->getBoolean(Ljava/lang/String;Z)Z

    move-result v5

    const-string v6, "nui_peer_enabled"

    invoke-virtual {v2, v6, v4}, Lcom/android/dialer/configprovider/SharedPrefConfigProvider;->getBoolean(Ljava/lang/String;Z)Z

    move-result v2

    iget-object v6, v0, Lcom/android/dialer/calllog/config/CallLogConfigImpl;->sharedPreferences:Landroid/content/SharedPreferences;

    const-string v7, "newCallLogFrameworkEnabled"

    invoke-interface {v6, v7, v4}, Landroid/content/SharedPreferences;->getBoolean(Ljava/lang/String;Z)Z

    move-result v6

    const/4 v7, 0x1

    if-nez v3, :cond_3a

    if-nez v5, :cond_3a

    if-eqz v2, :cond_38

    goto :goto_3a

    :cond_38
    move v8, v4

    goto :goto_3b

    :cond_3a
    :goto_3a
    move v8, v7

    :goto_3b
    if-eqz v8, :cond_9a

    if-nez v6, :cond_9a

    iget-object v6, v0, Lcom/android/dialer/calllog/config/CallLogConfigImpl;->callLogFramework:Lcom/android/dialer/calllog/CallLogFramework;

    invoke-virtual {v6}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const-string v8, "CallLogFramework.registerContentObservers"

    invoke-static {v8}, Lcom/android/dialer/common/LogUtil;->enterBlock(Ljava/lang/String;)V

    iget-object v8, v6, Lcom/android/dialer/calllog/CallLogFramework;->dataSources:Lcom/android/dialer/calllog/CallLogModule$1;

    iget-object v8, v8, Lcom/android/dialer/calllog/CallLogModule$1;->val$allDataSources:Lcom/google/common/collect/ImmutableList;

    invoke-virtual {v8}, Lcom/google/common/collect/ImmutableList;->iterator()Lcom/google/common/collect/UnmodifiableIterator;

    move-result-object v8

    :goto_51
    invoke-interface {v8}, Ljava/util/Iterator;->hasNext()Z

    move-result v9

    if-eqz v9, :cond_61

    invoke-interface {v8}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v9

    check-cast v9, Lcom/android/dialer/calllog/datasources/CallLogDataSource;

    invoke-interface {v9}, Lcom/android/dialer/calllog/datasources/CallLogDataSource;->registerContentObservers()V

    goto :goto_51

    :cond_61
    iget-object v6, v6, Lcom/android/dialer/calllog/CallLogFramework;->annotatedCallLogMigrator:Lcom/android/dialer/calllog/AnnotatedCallLogMigrator;

    iget-object v8, v6, Lcom/android/dialer/calllog/AnnotatedCallLogMigrator;->backgroundExecutor:Lcom/google/common/util/concurrent/ListeningExecutorService;

    new-instance v9, Lcom/android/dialer/calllog/AnnotatedCallLogMigrator$$ExternalSyntheticLambda2;

    invoke-direct {v9, v4}, Lcom/android/dialer/calllog/AnnotatedCallLogMigrator$$ExternalSyntheticLambda2;-><init>(I)V

    iput-object v6, v9, Lcom/android/dialer/calllog/AnnotatedCallLogMigrator$$ExternalSyntheticLambda2;->f$0:Lcom/android/dialer/calllog/AnnotatedCallLogMigrator;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-interface {v8, v9}, Lcom/google/common/util/concurrent/ListeningExecutorService;->submit(Ljava/util/concurrent/Callable;)Lcom/google/common/util/concurrent/ListenableFuture;

    move-result-object v4

    new-instance v8, Lcom/android/dialer/calllog/AnnotatedCallLogMigrator$$ExternalSyntheticLambda0;

    invoke-direct {v8}, Ljava/lang/Object;-><init>()V

    iput-object v6, v8, Lcom/android/dialer/calllog/AnnotatedCallLogMigrator$$ExternalSyntheticLambda0;->f$0:Lcom/android/dialer/calllog/AnnotatedCallLogMigrator;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {}, Lcom/google/common/util/concurrent/MoreExecutors;->directExecutor()Ljava/util/concurrent/Executor;

    move-result-object v6

    invoke-static {v4, v8, v6}, Lcom/google/common/util/concurrent/Futures;->transformAsync(Lcom/google/common/util/concurrent/ListenableFuture;Lcom/google/common/util/concurrent/AsyncFunction;Ljava/util/concurrent/Executor;)Lcom/google/common/util/concurrent/AbstractTransformFuture$AsyncTransformFuture;

    move-result-object v4

    new-instance v6, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda0;

    invoke-direct {v6}, Ljava/lang/Object;-><init>()V

    iput-object v0, v6, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda0;->f$0:Lcom/android/dialer/calllog/config/CallLogConfigImpl;

    iput-boolean v3, v6, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda0;->f$1:Z

    iput-boolean v5, v6, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda0;->f$2:Z

    iput-boolean v2, v6, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda0;->f$3:Z

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v4, v6, v1}, Lcom/google/common/util/concurrent/Futures;->transform(Lcom/google/common/util/concurrent/ListenableFuture;Lcom/google/common/base/Function;Ljava/util/concurrent/Executor;)Lcom/google/common/util/concurrent/AbstractTransformFuture$TransformFuture;

    move-result-object v0

    goto :goto_d3

    :cond_9a
    if-nez v8, :cond_bf

    if-eqz v6, :cond_bf

    new-instance v2, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda1;

    invoke-direct {v2}, Ljava/lang/Object;-><init>()V

    iput-object v0, v2, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda1;->f$0:Lcom/android/dialer/calllog/config/CallLogConfigImpl;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-interface {v1, v2}, Lcom/google/common/util/concurrent/ListeningExecutorService;->submit(Ljava/util/concurrent/Callable;)Lcom/google/common/util/concurrent/ListenableFuture;

    move-result-object v1

    new-instance v2, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda2;

    invoke-direct {v2}, Ljava/lang/Object;-><init>()V

    iput-object v0, v2, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda2;->f$0:Lcom/android/dialer/calllog/config/CallLogConfigImpl;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {}, Lcom/google/common/util/concurrent/MoreExecutors;->directExecutor()Ljava/util/concurrent/Executor;

    move-result-object v0

    invoke-static {v1, v2, v0}, Lcom/google/common/util/concurrent/Futures;->transformAsync(Lcom/google/common/util/concurrent/ListenableFuture;Lcom/google/common/util/concurrent/AsyncFunction;Ljava/util/concurrent/Executor;)Lcom/google/common/util/concurrent/AbstractTransformFuture$AsyncTransformFuture;

    move-result-object v0

    goto :goto_d3

    :cond_bf
    new-instance v4, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda3;

    invoke-direct {v4}, Ljava/lang/Object;-><init>()V

    iput-object v0, v4, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda3;->f$0:Lcom/android/dialer/calllog/config/CallLogConfigImpl;

    iput-boolean v3, v4, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda3;->f$1:Z

    iput-boolean v5, v4, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda3;->f$2:Z

    iput-boolean v2, v4, Lcom/android/dialer/calllog/config/CallLogConfigImpl$$ExternalSyntheticLambda3;->f$3:Z

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-interface {v1, v4}, Lcom/google/common/util/concurrent/ListeningExecutorService;->submit(Ljava/util/concurrent/Callable;)Lcom/google/common/util/concurrent/ListenableFuture;

    move-result-object v0

    :goto_d3
    new-instance v1, Lcom/android/dialer/calllog/config/CallLogConfigImpl$PollingJob$1;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object p0, v1, Lcom/android/dialer/calllog/config/CallLogConfigImpl$PollingJob$1;->this$0:Lcom/android/dialer/calllog/config/CallLogConfigImpl$PollingJob;

    iput-object p1, v1, Lcom/android/dialer/calllog/config/CallLogConfigImpl$PollingJob$1;->val$params:Landroid/app/job/JobParameters;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {}, Lcom/google/common/util/concurrent/MoreExecutors;->directExecutor()Ljava/util/concurrent/Executor;

    move-result-object p0

    invoke-static {v0, v1, p0}, Lcom/google/common/util/concurrent/Futures;->addCallback(Lcom/google/common/util/concurrent/ListenableFuture;Lcom/google/common/util/concurrent/FutureCallback;Ljava/util/concurrent/Executor;)V

    return v7
.end method

.method public final onStopJob(Landroid/app/job/JobParameters;)Z
    .registers 2

    const/4 p0, 0x0

    return p0
.end method
