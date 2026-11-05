.class public Lcom/android/dialer/binary/aosp/AospDialerApplication;
.super Landroid/app/Application;
.source "go/retraceme 9af01222c9f0ce13808ff8a71a2aad063a10a8b4d085240df3537e8ca2c7d173"


# instance fields
.field public volatile rootComponent:Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;


# direct methods
.method public constructor <init>()V
    .registers 1

    invoke-direct {p0}, Landroid/app/Application;-><init>()V

    return-void
.end method


# virtual methods
.method public final buildRootComponent()Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;
    .registers 11

    new-instance v0, Lcom/android/dialer/inject/ContextModule;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object p0, v0, Lcom/android/dialer/inject/ContextModule;->context:Lcom/android/dialer/binary/aosp/AospDialerApplication;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    new-instance p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    sget-object v1, Lcom/android/dialer/activecalls/impl/ActiveCallsImpl_Factory;->INSTANCE:Lcom/android/dialer/activecalls/impl/ActiveCallsImpl_Factory;

    invoke-static {v1}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v1

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->toProvider:Ldagger/internal/DoubleCheck;

    sget-object v1, Lcom/android/bubble/stub/BubbleStub_Factory;->INSTANCE:Lcom/android/bubble/stub/BubbleStub_Factory;

    invoke-static {v1}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v1

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindsBubbleProvider:Ldagger/internal/DoubleCheck;

    new-instance v1, Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v0, v1, Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;->module:Lcom/android/dialer/inject/ContextModule;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    sget-object v0, Lcom/android/dialer/common/concurrent/DialerExecutorModule_ProvideNonUiThreadPoolFactory;->INSTANCE:Lcom/android/dialer/common/concurrent/DialerExecutorModule_ProvideNonUiThreadPoolFactory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideNonUiThreadPoolProvider:Ldagger/internal/DoubleCheck;

    new-instance v1, Lcom/android/dialer/common/concurrent/DialerExecutorModule_ProvideBackgroundExecutorFactory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v0, v1, Lcom/android/dialer/common/concurrent/DialerExecutorModule_ProvideBackgroundExecutorFactory;->delegateProvider:Ldagger/internal/DoubleCheck;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v1}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    iget-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    new-instance v1, Lcom/android/dialer/storage/StorageModule_ProvideUnencryptedSharedPrefsFactory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v0, v1, Lcom/android/dialer/storage/StorageModule_ProvideUnencryptedSharedPrefsFactory;->appContextProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v1}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUnencryptedSharedPrefsProvider:Ldagger/internal/DoubleCheck;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    new-instance v2, Lcom/android/dialer/calllog/notifier/RefreshAnnotatedCallLogNotifier_Factory;

    invoke-direct {v2}, Ljava/lang/Object;-><init>()V

    iput-object v1, v2, Lcom/android/dialer/calllog/notifier/RefreshAnnotatedCallLogNotifier_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v0, v2, Lcom/android/dialer/calllog/notifier/RefreshAnnotatedCallLogNotifier_Factory;->sharedPreferencesProvider:Ldagger/internal/DoubleCheck;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v2}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->refreshAnnotatedCallLogNotifierProvider:Ldagger/internal/DoubleCheck;

    invoke-static {}, Ldagger/internal/MembersInjectors;->noOp()Ldagger/MembersInjector;

    move-result-object v0

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->refreshAnnotatedCallLogNotifierProvider:Ldagger/internal/DoubleCheck;

    new-instance v2, Lcom/android/dialer/calllog/observer/MarkDirtyObserver_Factory;

    invoke-direct {v2}, Ljava/lang/Object;-><init>()V

    iput-object v0, v2, Lcom/android/dialer/calllog/observer/MarkDirtyObserver_Factory;->markDirtyObserverMembersInjector:Ldagger/MembersInjector;

    iput-object v1, v2, Lcom/android/dialer/calllog/observer/MarkDirtyObserver_Factory;->refreshAnnotatedCallLogNotifierProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->markDirtyObserverProvider:Lcom/android/dialer/calllog/observer/MarkDirtyObserver_Factory;

    invoke-static {}, Ldagger/internal/MembersInjectors;->noOp()Ldagger/MembersInjector;

    move-result-object v0

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    new-instance v3, Lcom/android/dialer/calllog/database/AnnotatedCallLogDatabaseHelper_Factory;

    invoke-direct {v3}, Ljava/lang/Object;-><init>()V

    iput-object v0, v3, Lcom/android/dialer/calllog/database/AnnotatedCallLogDatabaseHelper_Factory;->annotatedCallLogDatabaseHelperMembersInjector:Ldagger/MembersInjector;

    iput-object v1, v3, Lcom/android/dialer/calllog/database/AnnotatedCallLogDatabaseHelper_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v3, Lcom/android/dialer/calllog/database/AnnotatedCallLogDatabaseHelper_Factory;->backgroundExecutorProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v3}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->annotatedCallLogDatabaseHelperProvider:Ldagger/internal/DoubleCheck;

    sget-object v0, Lcom/android/dialer/duo/stub/DuoStub_Factory;->INSTANCE:Lcom/android/dialer/duo/stub/DuoStub_Factory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindsDuoProvider:Ldagger/internal/DoubleCheck;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    iget-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->markDirtyObserverProvider:Lcom/android/dialer/calllog/observer/MarkDirtyObserver_Factory;

    iget-object v4, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUnencryptedSharedPrefsProvider:Ldagger/internal/DoubleCheck;

    iget-object v5, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->annotatedCallLogDatabaseHelperProvider:Ldagger/internal/DoubleCheck;

    new-instance v6, Lcom/android/dialer/calllog/datasources/systemcalllog/SystemCallLogDataSource_Factory;

    invoke-direct {v6}, Ljava/lang/Object;-><init>()V

    iput-object v1, v6, Lcom/android/dialer/calllog/datasources/systemcalllog/SystemCallLogDataSource_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v6, Lcom/android/dialer/calllog/datasources/systemcalllog/SystemCallLogDataSource_Factory;->backgroundExecutorServiceProvider:Ljavax/inject/Provider;

    iput-object v3, v6, Lcom/android/dialer/calllog/datasources/systemcalllog/SystemCallLogDataSource_Factory;->markDirtyObserverProvider:Ljavax/inject/Provider;

    iput-object v4, v6, Lcom/android/dialer/calllog/datasources/systemcalllog/SystemCallLogDataSource_Factory;->sharedPreferencesProvider:Ljavax/inject/Provider;

    iput-object v5, v6, Lcom/android/dialer/calllog/datasources/systemcalllog/SystemCallLogDataSource_Factory;->annotatedCallLogDatabaseHelperProvider:Ljavax/inject/Provider;

    iput-object v0, v6, Lcom/android/dialer/calllog/datasources/systemcalllog/SystemCallLogDataSource_Factory;->duoProvider:Ldagger/internal/DoubleCheck;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v6}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->systemCallLogDataSourceProvider:Ldagger/internal/DoubleCheck;

    new-instance v0, Lcom/android/dialer/common/concurrent/DialerExecutorModule_ProvideLightweightExecutorFactory;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideLightweightExecutorProvider:Ldagger/internal/DoubleCheck;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    new-instance v3, Lcom/android/dialer/phonelookup/cequint/CequintPhoneLookup_Factory;

    invoke-direct {v3}, Ljava/lang/Object;-><init>()V

    iput-object v1, v3, Lcom/android/dialer/phonelookup/cequint/CequintPhoneLookup_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v3, Lcom/android/dialer/phonelookup/cequint/CequintPhoneLookup_Factory;->backgroundExecutorServiceProvider:Ljavax/inject/Provider;

    iput-object v0, v3, Lcom/android/dialer/phonelookup/cequint/CequintPhoneLookup_Factory;->lightweightExecutorServiceProvider:Ldagger/internal/DoubleCheck;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->cequintPhoneLookupProvider:Lcom/android/dialer/phonelookup/cequint/CequintPhoneLookup_Factory;

    new-instance v0, Lcom/android/dialer/phonelookup/cnap/CnapPhoneLookup_Factory;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object v1, v0, Lcom/android/dialer/phonelookup/cnap/CnapPhoneLookup_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v0, Lcom/android/dialer/phonelookup/cnap/CnapPhoneLookup_Factory;->backgroundExecutorServiceProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->cnapPhoneLookupProvider:Lcom/android/dialer/phonelookup/cnap/CnapPhoneLookup_Factory;

    iget-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUnencryptedSharedPrefsProvider:Ldagger/internal/DoubleCheck;

    new-instance v1, Lcom/android/dialer/configprovider/SharedPrefConfigProvider_Factory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v0, v1, Lcom/android/dialer/configprovider/SharedPrefConfigProvider_Factory;->sharedPreferencesProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->sharedPrefConfigProvider:Lcom/android/dialer/configprovider/SharedPrefConfigProvider_Factory;

    invoke-static {v1}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->toProvider2:Ldagger/internal/DoubleCheck;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    iget-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideLightweightExecutorProvider:Ldagger/internal/DoubleCheck;

    new-instance v4, Lcom/android/dialer/phonelookup/cp2/MissingPermissionsOperations_Factory;

    invoke-direct {v4}, Ljava/lang/Object;-><init>()V

    iput-object v1, v4, Lcom/android/dialer/phonelookup/cp2/MissingPermissionsOperations_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v4, Lcom/android/dialer/phonelookup/cp2/MissingPermissionsOperations_Factory;->backgroundExecutorProvider:Ljavax/inject/Provider;

    iput-object v3, v4, Lcom/android/dialer/phonelookup/cp2/MissingPermissionsOperations_Factory;->lightweightExecutorProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v4, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->missingPermissionsOperationsProvider:Lcom/android/dialer/phonelookup/cp2/MissingPermissionsOperations_Factory;

    iget-object v5, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUnencryptedSharedPrefsProvider:Ldagger/internal/DoubleCheck;

    new-instance v6, Lcom/android/dialer/phonelookup/cp2/Cp2DefaultDirectoryPhoneLookup_Factory;

    invoke-direct {v6}, Ljava/lang/Object;-><init>()V

    iput-object v1, v6, Lcom/android/dialer/phonelookup/cp2/Cp2DefaultDirectoryPhoneLookup_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v5, v6, Lcom/android/dialer/phonelookup/cp2/Cp2DefaultDirectoryPhoneLookup_Factory;->sharedPreferencesProvider:Ljavax/inject/Provider;

    iput-object v2, v6, Lcom/android/dialer/phonelookup/cp2/Cp2DefaultDirectoryPhoneLookup_Factory;->backgroundExecutorServiceProvider:Ljavax/inject/Provider;

    iput-object v3, v6, Lcom/android/dialer/phonelookup/cp2/Cp2DefaultDirectoryPhoneLookup_Factory;->lightweightExecutorServiceProvider:Ljavax/inject/Provider;

    iput-object v0, v6, Lcom/android/dialer/phonelookup/cp2/Cp2DefaultDirectoryPhoneLookup_Factory;->configProvider:Ldagger/internal/DoubleCheck;

    iput-object v4, v6, Lcom/android/dialer/phonelookup/cp2/Cp2DefaultDirectoryPhoneLookup_Factory;->missingPermissionsOperationsProvider:Lcom/android/dialer/phonelookup/cp2/MissingPermissionsOperations_Factory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v6, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->cp2DefaultDirectoryPhoneLookupProvider:Lcom/android/dialer/phonelookup/cp2/Cp2DefaultDirectoryPhoneLookup_Factory;

    sget-object v0, Lcom/android/dialer/common/concurrent/DialerExecutorModule_ProvideNonUiSerialExecutorServiceFactory;->INSTANCE:Lcom/android/dialer/common/concurrent/DialerExecutorModule_ProvideNonUiSerialExecutorServiceFactory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideNonUiSerialExecutorServiceProvider:Ldagger/internal/DoubleCheck;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    iget-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideLightweightExecutorProvider:Ldagger/internal/DoubleCheck;

    iget-object v4, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->toProvider2:Ldagger/internal/DoubleCheck;

    iget-object v5, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->missingPermissionsOperationsProvider:Lcom/android/dialer/phonelookup/cp2/MissingPermissionsOperations_Factory;

    new-instance v6, Lcom/android/dialer/phonelookup/cp2/Cp2ExtendedDirectoryPhoneLookup_Factory;

    invoke-direct {v6}, Ljava/lang/Object;-><init>()V

    iput-object v1, v6, Lcom/android/dialer/phonelookup/cp2/Cp2ExtendedDirectoryPhoneLookup_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v6, Lcom/android/dialer/phonelookup/cp2/Cp2ExtendedDirectoryPhoneLookup_Factory;->backgroundExecutorServiceProvider:Ljavax/inject/Provider;

    iput-object v3, v6, Lcom/android/dialer/phonelookup/cp2/Cp2ExtendedDirectoryPhoneLookup_Factory;->lightweightExecutorServiceProvider:Ljavax/inject/Provider;

    iput-object v0, v6, Lcom/android/dialer/phonelookup/cp2/Cp2ExtendedDirectoryPhoneLookup_Factory;->scheduledExecutorServiceProvider:Ldagger/internal/DoubleCheck;

    iput-object v4, v6, Lcom/android/dialer/phonelookup/cp2/Cp2ExtendedDirectoryPhoneLookup_Factory;->configProvider:Ljavax/inject/Provider;

    iput-object v5, v6, Lcom/android/dialer/phonelookup/cp2/Cp2ExtendedDirectoryPhoneLookup_Factory;->missingPermissionsOperationsProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v6, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->cp2ExtendedDirectoryPhoneLookupProvider:Lcom/android/dialer/phonelookup/cp2/Cp2ExtendedDirectoryPhoneLookup_Factory;

    new-instance v0, Lcom/android/dialer/phonelookup/emergency/EmergencyPhoneLookup_Factory;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object v1, v0, Lcom/android/dialer/phonelookup/emergency/EmergencyPhoneLookup_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v0, Lcom/android/dialer/phonelookup/emergency/EmergencyPhoneLookup_Factory;->backgroundExecutorServiceProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->emergencyPhoneLookupProvider:Lcom/android/dialer/phonelookup/emergency/EmergencyPhoneLookup_Factory;

    iget-object v4, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->markDirtyObserverProvider:Lcom/android/dialer/calllog/observer/MarkDirtyObserver_Factory;

    new-instance v5, Lcom/android/dialer/phonelookup/blockednumber/SystemBlockedNumberPhoneLookup_Factory;

    invoke-direct {v5}, Ljava/lang/Object;-><init>()V

    iput-object v1, v5, Lcom/android/dialer/phonelookup/blockednumber/SystemBlockedNumberPhoneLookup_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v5, Lcom/android/dialer/phonelookup/blockednumber/SystemBlockedNumberPhoneLookup_Factory;->executorServiceProvider:Ljavax/inject/Provider;

    iput-object v4, v5, Lcom/android/dialer/phonelookup/blockednumber/SystemBlockedNumberPhoneLookup_Factory;->markDirtyObserverProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v5, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->systemBlockedNumberPhoneLookupProvider:Lcom/android/dialer/phonelookup/blockednumber/SystemBlockedNumberPhoneLookup_Factory;

    new-instance v1, Lcom/android/dialer/spam/stub/SpamStub_Factory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v2, v1, Lcom/android/dialer/spam/stub/SpamStub_Factory;->backgroundExecutorServiceProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->spamStubProvider:Lcom/android/dialer/spam/stub/SpamStub_Factory;

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindSpamProvider:Lcom/android/dialer/spam/stub/SpamStub_Factory;

    iget-object v4, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUnencryptedSharedPrefsProvider:Ldagger/internal/DoubleCheck;

    new-instance v7, Lcom/android/dialer/phonelookup/spam/SpamPhoneLookup_Factory;

    invoke-direct {v7}, Ljava/lang/Object;-><init>()V

    iput-object v2, v7, Lcom/android/dialer/phonelookup/spam/SpamPhoneLookup_Factory;->backgroundExecutorServiceProvider:Ljavax/inject/Provider;

    iput-object v3, v7, Lcom/android/dialer/phonelookup/spam/SpamPhoneLookup_Factory;->lightweightExecutorServiceProvider:Ljavax/inject/Provider;

    iput-object v4, v7, Lcom/android/dialer/phonelookup/spam/SpamPhoneLookup_Factory;->sharedPreferencesProvider:Ljavax/inject/Provider;

    iput-object v1, v7, Lcom/android/dialer/phonelookup/spam/SpamPhoneLookup_Factory;->spamProvider:Lcom/android/dialer/spam/stub/SpamStub_Factory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v7, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->spamPhoneLookupProvider:Lcom/android/dialer/phonelookup/spam/SpamPhoneLookup_Factory;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->cequintPhoneLookupProvider:Lcom/android/dialer/phonelookup/cequint/CequintPhoneLookup_Factory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->cnapPhoneLookupProvider:Lcom/android/dialer/phonelookup/cnap/CnapPhoneLookup_Factory;

    iget-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->cp2DefaultDirectoryPhoneLookupProvider:Lcom/android/dialer/phonelookup/cp2/Cp2DefaultDirectoryPhoneLookup_Factory;

    new-instance v4, Lcom/android/dialer/phonelookup/PhoneLookupModule_ProvidePhoneLookupListFactory;

    invoke-direct {v4}, Ljava/lang/Object;-><init>()V

    iput-object v1, v4, Lcom/android/dialer/phonelookup/PhoneLookupModule_ProvidePhoneLookupListFactory;->cequintPhoneLookupProvider:Ljavax/inject/Provider;

    iput-object v2, v4, Lcom/android/dialer/phonelookup/PhoneLookupModule_ProvidePhoneLookupListFactory;->cnapPhoneLookupProvider:Ljavax/inject/Provider;

    iput-object v3, v4, Lcom/android/dialer/phonelookup/PhoneLookupModule_ProvidePhoneLookupListFactory;->cp2DefaultDirectoryPhoneLookupProvider:Ljavax/inject/Provider;

    iput-object v6, v4, Lcom/android/dialer/phonelookup/PhoneLookupModule_ProvidePhoneLookupListFactory;->cp2ExtendedDirectoryPhoneLookupProvider:Lcom/android/dialer/phonelookup/cp2/Cp2ExtendedDirectoryPhoneLookup_Factory;

    iput-object v0, v4, Lcom/android/dialer/phonelookup/PhoneLookupModule_ProvidePhoneLookupListFactory;->emergencyPhoneLookupProvider:Lcom/android/dialer/phonelookup/emergency/EmergencyPhoneLookup_Factory;

    iput-object v5, v4, Lcom/android/dialer/phonelookup/PhoneLookupModule_ProvidePhoneLookupListFactory;->systemBlockedNumberPhoneLookupProvider:Lcom/android/dialer/phonelookup/blockednumber/SystemBlockedNumberPhoneLookup_Factory;

    iput-object v7, v4, Lcom/android/dialer/phonelookup/PhoneLookupModule_ProvidePhoneLookupListFactory;->spamPhoneLookupProvider:Lcom/android/dialer/phonelookup/spam/SpamPhoneLookup_Factory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v4, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->providePhoneLookupListProvider:Lcom/android/dialer/phonelookup/PhoneLookupModule_ProvidePhoneLookupListFactory;

    sget-object v0, Lcom/android/dialer/metrics/StubMetrics_Factory;->INSTANCE:Lcom/android/dialer/metrics/StubMetrics_Factory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->stubMetricsProvider:Ldagger/internal/DoubleCheck;

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindMetricsProvider:Ldagger/internal/DoubleCheck;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideLightweightExecutorProvider:Ldagger/internal/DoubleCheck;

    new-instance v2, Lcom/android/dialer/metrics/FutureTimer_Factory;

    invoke-direct {v2}, Ljava/lang/Object;-><init>()V

    iput-object v0, v2, Lcom/android/dialer/metrics/FutureTimer_Factory;->metricsProvider:Ldagger/internal/DoubleCheck;

    iput-object v1, v2, Lcom/android/dialer/metrics/FutureTimer_Factory;->lightweightExecutorServiceProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->futureTimerProvider:Lcom/android/dialer/metrics/FutureTimer_Factory;

    iget-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUnencryptedSharedPrefsProvider:Ldagger/internal/DoubleCheck;

    iget-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    new-instance v4, Lcom/android/dialer/calllog/CallLogState_Factory;

    invoke-direct {v4}, Ljava/lang/Object;-><init>()V

    iput-object v0, v4, Lcom/android/dialer/calllog/CallLogState_Factory;->sharedPreferencesProvider:Ljavax/inject/Provider;

    iput-object v3, v4, Lcom/android/dialer/calllog/CallLogState_Factory;->backgroundExecutorProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v4, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->callLogStateProvider:Lcom/android/dialer/calllog/CallLogState_Factory;

    iget-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    iget-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->providePhoneLookupListProvider:Lcom/android/dialer/phonelookup/PhoneLookupModule_ProvidePhoneLookupListFactory;

    new-instance v5, Lcom/android/dialer/phonelookup/composite/CompositePhoneLookup_Factory;

    invoke-direct {v5}, Ljava/lang/Object;-><init>()V

    iput-object v0, v5, Lcom/android/dialer/phonelookup/composite/CompositePhoneLookup_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v3, v5, Lcom/android/dialer/phonelookup/composite/CompositePhoneLookup_Factory;->phoneLookupsProvider:Ljavax/inject/Provider;

    iput-object v2, v5, Lcom/android/dialer/phonelookup/composite/CompositePhoneLookup_Factory;->futureTimerProvider:Lcom/android/dialer/metrics/FutureTimer_Factory;

    iput-object v4, v5, Lcom/android/dialer/phonelookup/composite/CompositePhoneLookup_Factory;->callLogStateProvider:Lcom/android/dialer/calllog/CallLogState_Factory;

    iput-object v1, v5, Lcom/android/dialer/phonelookup/composite/CompositePhoneLookup_Factory;->lightweightExecutorServiceProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v5, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->compositePhoneLookupProvider:Lcom/android/dialer/phonelookup/composite/CompositePhoneLookup_Factory;

    invoke-static {}, Ldagger/internal/MembersInjectors;->noOp()Ldagger/MembersInjector;

    move-result-object v0

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    new-instance v3, Lcom/android/dialer/phonelookup/database/PhoneLookupHistoryDatabaseHelper_Factory;

    invoke-direct {v3}, Ljava/lang/Object;-><init>()V

    iput-object v0, v3, Lcom/android/dialer/phonelookup/database/PhoneLookupHistoryDatabaseHelper_Factory;->phoneLookupHistoryDatabaseHelperMembersInjector:Ldagger/MembersInjector;

    iput-object v1, v3, Lcom/android/dialer/phonelookup/database/PhoneLookupHistoryDatabaseHelper_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v3, Lcom/android/dialer/phonelookup/database/PhoneLookupHistoryDatabaseHelper_Factory;->backgroundExecutorProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v3}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->phoneLookupHistoryDatabaseHelperProvider:Ldagger/internal/DoubleCheck;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->compositePhoneLookupProvider:Lcom/android/dialer/phonelookup/composite/CompositePhoneLookup_Factory;

    iget-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    iget-object v4, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideLightweightExecutorProvider:Ldagger/internal/DoubleCheck;

    new-instance v5, Lcom/android/dialer/calllog/datasources/phonelookup/PhoneLookupDataSource_Factory;

    invoke-direct {v5}, Ljava/lang/Object;-><init>()V

    iput-object v1, v5, Lcom/android/dialer/calllog/datasources/phonelookup/PhoneLookupDataSource_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v5, Lcom/android/dialer/calllog/datasources/phonelookup/PhoneLookupDataSource_Factory;->compositePhoneLookupProvider:Ljavax/inject/Provider;

    iput-object v3, v5, Lcom/android/dialer/calllog/datasources/phonelookup/PhoneLookupDataSource_Factory;->backgroundExecutorServiceProvider:Ljavax/inject/Provider;

    iput-object v4, v5, Lcom/android/dialer/calllog/datasources/phonelookup/PhoneLookupDataSource_Factory;->lightweightExecutorServiceProvider:Ljavax/inject/Provider;

    iput-object v0, v5, Lcom/android/dialer/calllog/datasources/phonelookup/PhoneLookupDataSource_Factory;->phoneLookupHistoryDatabaseHelperProvider:Ldagger/internal/DoubleCheck;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v5, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->phoneLookupDataSourceProvider:Lcom/android/dialer/calllog/datasources/phonelookup/PhoneLookupDataSource_Factory;

    new-instance v0, Lcom/android/dialer/calllog/datasources/voicemail/VoicemailDataSource_Factory;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object v1, v0, Lcom/android/dialer/calllog/datasources/voicemail/VoicemailDataSource_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v3, v0, Lcom/android/dialer/calllog/datasources/voicemail/VoicemailDataSource_Factory;->backgroundExecutorProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->voicemailDataSourceProvider:Lcom/android/dialer/calllog/datasources/voicemail/VoicemailDataSource_Factory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->systemCallLogDataSourceProvider:Ldagger/internal/DoubleCheck;

    new-instance v6, Lcom/android/dialer/calllog/CallLogModule_ProvideCallLogDataSourcesFactory;

    invoke-direct {v6}, Ljava/lang/Object;-><init>()V

    iput-object v2, v6, Lcom/android/dialer/calllog/CallLogModule_ProvideCallLogDataSourcesFactory;->systemCallLogDataSourceProvider:Ljavax/inject/Provider;

    iput-object v5, v6, Lcom/android/dialer/calllog/CallLogModule_ProvideCallLogDataSourcesFactory;->phoneLookupDataSourceProvider:Lcom/android/dialer/calllog/datasources/phonelookup/PhoneLookupDataSource_Factory;

    iput-object v0, v6, Lcom/android/dialer/calllog/CallLogModule_ProvideCallLogDataSourcesFactory;->voicemailDataSourceProvider:Lcom/android/dialer/calllog/datasources/voicemail/VoicemailDataSource_Factory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v6, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideCallLogDataSourcesProvider:Lcom/android/dialer/calllog/CallLogModule_ProvideCallLogDataSourcesFactory;

    new-instance v0, Lcom/android/dialer/calllog/database/MutationApplier_Factory;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object v3, v0, Lcom/android/dialer/calllog/database/MutationApplier_Factory;->backgroundExecutorServiceProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->mutationApplierProvider:Lcom/android/dialer/calllog/database/MutationApplier_Factory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->callLogStateProvider:Lcom/android/dialer/calllog/CallLogState_Factory;

    new-instance v5, Lcom/android/dialer/calllog/CallLogCacheUpdater_Factory;

    invoke-direct {v5}, Ljava/lang/Object;-><init>()V

    iput-object v1, v5, Lcom/android/dialer/calllog/CallLogCacheUpdater_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v3, v5, Lcom/android/dialer/calllog/CallLogCacheUpdater_Factory;->backgroundExecutorProvider:Ljavax/inject/Provider;

    iput-object v2, v5, Lcom/android/dialer/calllog/CallLogCacheUpdater_Factory;->callLogStateProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v5, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->callLogCacheUpdaterProvider:Lcom/android/dialer/calllog/CallLogCacheUpdater_Factory;

    iget-object v7, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUnencryptedSharedPrefsProvider:Ldagger/internal/DoubleCheck;

    iget-object v8, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->futureTimerProvider:Lcom/android/dialer/metrics/FutureTimer_Factory;

    new-instance v9, Lcom/android/dialer/calllog/RefreshAnnotatedCallLogWorker_Factory;

    invoke-direct {v9}, Ljava/lang/Object;-><init>()V

    iput-object v1, v9, Lcom/android/dialer/calllog/RefreshAnnotatedCallLogWorker_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v6, v9, Lcom/android/dialer/calllog/RefreshAnnotatedCallLogWorker_Factory;->dataSourcesProvider:Lcom/android/dialer/calllog/CallLogModule_ProvideCallLogDataSourcesFactory;

    iput-object v7, v9, Lcom/android/dialer/calllog/RefreshAnnotatedCallLogWorker_Factory;->sharedPreferencesProvider:Ljavax/inject/Provider;

    iput-object v0, v9, Lcom/android/dialer/calllog/RefreshAnnotatedCallLogWorker_Factory;->mutationApplierProvider:Lcom/android/dialer/calllog/database/MutationApplier_Factory;

    iput-object v8, v9, Lcom/android/dialer/calllog/RefreshAnnotatedCallLogWorker_Factory;->futureTimerProvider:Ljavax/inject/Provider;

    iput-object v2, v9, Lcom/android/dialer/calllog/RefreshAnnotatedCallLogWorker_Factory;->callLogStateProvider:Ljavax/inject/Provider;

    iput-object v5, v9, Lcom/android/dialer/calllog/RefreshAnnotatedCallLogWorker_Factory;->callLogCacheUpdaterProvider:Lcom/android/dialer/calllog/CallLogCacheUpdater_Factory;

    iput-object v3, v9, Lcom/android/dialer/calllog/RefreshAnnotatedCallLogWorker_Factory;->backgroundExecutorServiceProvider:Ljavax/inject/Provider;

    iput-object v4, v9, Lcom/android/dialer/calllog/RefreshAnnotatedCallLogWorker_Factory;->lightweightExecutorServiceProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v9}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->refreshAnnotatedCallLogWorkerProvider:Ldagger/internal/DoubleCheck;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUnencryptedSharedPrefsProvider:Ldagger/internal/DoubleCheck;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    new-instance v3, Lcom/android/dialer/calllog/AnnotatedCallLogMigrator_Factory;

    invoke-direct {v3}, Ljava/lang/Object;-><init>()V

    iput-object v1, v3, Lcom/android/dialer/calllog/AnnotatedCallLogMigrator_Factory;->sharedPreferencesProvider:Ljavax/inject/Provider;

    iput-object v2, v3, Lcom/android/dialer/calllog/AnnotatedCallLogMigrator_Factory;->backgroundExecutorProvider:Ljavax/inject/Provider;

    iput-object v0, v3, Lcom/android/dialer/calllog/AnnotatedCallLogMigrator_Factory;->refreshAnnotatedCallLogWorkerProvider:Ldagger/internal/DoubleCheck;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->annotatedCallLogMigratorProvider:Lcom/android/dialer/calllog/AnnotatedCallLogMigrator_Factory;

    sget-object v0, Lcom/android/dialer/common/concurrent/DialerExecutorModule_ProvideUiThreadExecutorServiceFactory;->INSTANCE:Lcom/android/dialer/common/concurrent/DialerExecutorModule_ProvideUiThreadExecutorServiceFactory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUiThreadExecutorServiceProvider:Ldagger/internal/DoubleCheck;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideCallLogDataSourcesProvider:Lcom/android/dialer/calllog/CallLogModule_ProvideCallLogDataSourcesFactory;

    iget-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->annotatedCallLogMigratorProvider:Lcom/android/dialer/calllog/AnnotatedCallLogMigrator_Factory;

    iget-object v4, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->callLogStateProvider:Lcom/android/dialer/calllog/CallLogState_Factory;

    new-instance v5, Lcom/android/dialer/calllog/CallLogFramework_Factory;

    invoke-direct {v5}, Ljava/lang/Object;-><init>()V

    iput-object v1, v5, Lcom/android/dialer/calllog/CallLogFramework_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v5, Lcom/android/dialer/calllog/CallLogFramework_Factory;->dataSourcesProvider:Ljavax/inject/Provider;

    iput-object v3, v5, Lcom/android/dialer/calllog/CallLogFramework_Factory;->annotatedCallLogMigratorProvider:Ljavax/inject/Provider;

    iput-object v0, v5, Lcom/android/dialer/calllog/CallLogFramework_Factory;->uiExecutorProvider:Ldagger/internal/DoubleCheck;

    iput-object v4, v5, Lcom/android/dialer/calllog/CallLogFramework_Factory;->callLogStateProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v5}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->callLogFrameworkProvider:Ldagger/internal/DoubleCheck;

    iget-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    new-instance v1, Lcom/android/dialer/commandline/impl/Help_Factory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v0, v1, Lcom/android/dialer/commandline/impl/Help_Factory;->contextProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->helpProvider:Lcom/android/dialer/commandline/impl/Help_Factory;

    new-instance v2, Lcom/android/dialer/commandline/impl/Version_Factory;

    invoke-direct {v2}, Ljava/lang/Object;-><init>()V

    iput-object v0, v2, Lcom/android/dialer/commandline/impl/Version_Factory;->contextProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->versionProvider:Lcom/android/dialer/commandline/impl/Version_Factory;

    iget-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    new-instance v4, Lcom/android/dialer/commandline/impl/BlockingCommand_Factory;

    invoke-direct {v4}, Ljava/lang/Object;-><init>()V

    iput-object v0, v4, Lcom/android/dialer/commandline/impl/BlockingCommand_Factory;->contextProvider:Ljavax/inject/Provider;

    iput-object v3, v4, Lcom/android/dialer/commandline/impl/BlockingCommand_Factory;->executorServiceProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v4, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->blockingCommandProvider:Lcom/android/dialer/commandline/impl/BlockingCommand_Factory;

    new-instance v3, Lcom/android/dialer/commandline/impl/CallCommand_Factory;

    invoke-direct {v3}, Ljava/lang/Object;-><init>()V

    iput-object v0, v3, Lcom/android/dialer/commandline/impl/CallCommand_Factory;->appContextProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->callCommandProvider:Lcom/android/dialer/commandline/impl/CallCommand_Factory;

    new-instance v5, Lcom/android/dialer/commandline/impl/ActiveCallsCommand_Factory;

    invoke-direct {v5}, Ljava/lang/Object;-><init>()V

    iput-object v0, v5, Lcom/android/dialer/commandline/impl/ActiveCallsCommand_Factory;->appContextProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v5, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->activeCallsCommandProvider:Lcom/android/dialer/commandline/impl/ActiveCallsCommand_Factory;

    new-instance v6, Lcom/android/dialer/commandline/CommandLineModule_AospCommandInjector_Factory;

    invoke-direct {v6}, Ljava/lang/Object;-><init>()V

    iput-object v1, v6, Lcom/android/dialer/commandline/CommandLineModule_AospCommandInjector_Factory;->helpProvider:Lcom/android/dialer/commandline/impl/Help_Factory;

    iput-object v2, v6, Lcom/android/dialer/commandline/CommandLineModule_AospCommandInjector_Factory;->versionProvider:Lcom/android/dialer/commandline/impl/Version_Factory;

    iput-object v4, v6, Lcom/android/dialer/commandline/CommandLineModule_AospCommandInjector_Factory;->blockingCommandProvider:Lcom/android/dialer/commandline/impl/BlockingCommand_Factory;

    iput-object v3, v6, Lcom/android/dialer/commandline/CommandLineModule_AospCommandInjector_Factory;->callCommandProvider:Lcom/android/dialer/commandline/impl/CallCommand_Factory;

    iput-object v5, v6, Lcom/android/dialer/commandline/CommandLineModule_AospCommandInjector_Factory;->activeCallsCommandProvider:Lcom/android/dialer/commandline/impl/ActiveCallsCommand_Factory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v6, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->aospCommandInjectorProvider:Lcom/android/dialer/commandline/CommandLineModule_AospCommandInjector_Factory;

    new-instance v1, Lcom/android/dialer/commandline/CommandLineModule_ProvideCommandSupplierFactory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v6, v1, Lcom/android/dialer/commandline/CommandLineModule_ProvideCommandSupplierFactory;->aospCommandInjectorProvider:Lcom/android/dialer/commandline/CommandLineModule_AospCommandInjector_Factory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideCommandSupplierProvider:Lcom/android/dialer/commandline/CommandLineModule_ProvideCommandSupplierFactory;

    new-instance v1, Lcom/android/dialer/contacts/displaypreference/ContactDisplayPreferencesImpl_Factory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v0, v1, Lcom/android/dialer/contacts/displaypreference/ContactDisplayPreferencesImpl_Factory;->appContextProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->contactDisplayPreferencesImplProvider:Lcom/android/dialer/contacts/displaypreference/ContactDisplayPreferencesImpl_Factory;

    new-instance v2, Lcom/android/dialer/contacts/ContactsModule_ProvideContactDisplayPreferencesFactory;

    invoke-direct {v2}, Ljava/lang/Object;-><init>()V

    iput-object v0, v2, Lcom/android/dialer/contacts/ContactsModule_ProvideContactDisplayPreferencesFactory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v1, v2, Lcom/android/dialer/contacts/ContactsModule_ProvideContactDisplayPreferencesFactory;->implProvider:Lcom/android/dialer/contacts/displaypreference/ContactDisplayPreferencesImpl_Factory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContactDisplayPreferencesProvider:Lcom/android/dialer/contacts/ContactsModule_ProvideContactDisplayPreferencesFactory;

    sget-object v0, Lcom/android/dialer/common/concurrent/DialerExecutorModule_ProvideUiSerialExecutorServiceFactory;->INSTANCE:Lcom/android/dialer/common/concurrent/DialerExecutorModule_ProvideUiSerialExecutorServiceFactory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUiSerialExecutorServiceProvider:Ldagger/internal/DoubleCheck;

    sget-object v0, Lcom/android/dialer/enrichedcall/stub/StubEnrichedCallModule_ProvideEnrichedCallManagerFactory;->INSTANCE:Lcom/android/dialer/enrichedcall/stub/StubEnrichedCallModule_ProvideEnrichedCallManagerFactory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideEnrichedCallManagerProvider:Ldagger/internal/DoubleCheck;

    sget-object v0, Lcom/android/dialer/enrichedcall/stub/StubEnrichedCallModule_ProvidesRcsVideoShareFactoryFactory;->INSTANCE:Lcom/android/dialer/enrichedcall/stub/StubEnrichedCallModule_ProvidesRcsVideoShareFactoryFactory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->providesRcsVideoShareFactoryProvider:Ldagger/internal/DoubleCheck;

    iget-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    new-instance v1, Lcom/android/dialer/feedback/stub/StubFeedbackModule_ProvideCallFeedbackListenerFactory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v0, v1, Lcom/android/dialer/feedback/stub/StubFeedbackModule_ProvideCallFeedbackListenerFactory;->contextProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideCallFeedbackListenerProvider:Lcom/android/dialer/feedback/stub/StubFeedbackModule_ProvideCallFeedbackListenerFactory;

    new-instance v1, Lcom/android/dialer/glidephotomanager/impl/GlidePhotoManagerImpl_Factory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v0, v1, Lcom/android/dialer/glidephotomanager/impl/GlidePhotoManagerImpl_Factory;->appContextProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->glidePhotoManagerImplProvider:Lcom/android/dialer/glidephotomanager/impl/GlidePhotoManagerImpl_Factory;

    invoke-static {v1}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindGlidePhotoManagerProvider:Ldagger/internal/DoubleCheck;

    sget-object v0, Lcom/android/incallui/maps/stub/StubMapsModule_StubMaps_Factory;->INSTANCE:Lcom/android/incallui/maps/stub/StubMapsModule_StubMaps_Factory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindMapsProvider:Ldagger/internal/DoubleCheck;

    sget-object v0, Lcom/android/dialer/phonenumbergeoutil/impl/PhoneNumberGeoUtilImpl_Factory;->INSTANCE:Lcom/android/dialer/phonenumbergeoutil/impl/PhoneNumberGeoUtilImpl_Factory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindPhoneNumberGeoUtilProvider:Ldagger/internal/DoubleCheck;

    iget-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUiThreadExecutorServiceProvider:Ldagger/internal/DoubleCheck;

    new-instance v1, Lcom/android/dialer/precall/impl/DuoAction_Factory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v0, v1, Lcom/android/dialer/precall/impl/DuoAction_Factory;->uiExecutorProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->duoActionProvider:Lcom/android/dialer/precall/impl/DuoAction_Factory;

    iget-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    new-instance v3, Lcom/android/dialer/preferredsim/impl/PreferredAccountWorkerImpl_Factory;

    invoke-direct {v3}, Ljava/lang/Object;-><init>()V

    iput-object v0, v3, Lcom/android/dialer/preferredsim/impl/PreferredAccountWorkerImpl_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v2, v3, Lcom/android/dialer/preferredsim/impl/PreferredAccountWorkerImpl_Factory;->backgroundExecutorProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->preferredAccountWorkerImplProvider:Lcom/android/dialer/preferredsim/impl/PreferredAccountWorkerImpl_Factory;

    iput-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->toProvider3:Lcom/android/dialer/preferredsim/impl/PreferredAccountWorkerImpl_Factory;

    new-instance v0, Lcom/android/dialer/precall/impl/CallingAccountSelector_Factory;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object v3, v0, Lcom/android/dialer/precall/impl/CallingAccountSelector_Factory;->preferredAccountWorkerProvider:Lcom/android/dialer/preferredsim/impl/PreferredAccountWorkerImpl_Factory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->callingAccountSelectorProvider:Lcom/android/dialer/precall/impl/CallingAccountSelector_Factory;

    new-instance v2, Lcom/android/dialer/precall/impl/PreCallModule_ProvideActionsFactory;

    invoke-direct {v2}, Ljava/lang/Object;-><init>()V

    iput-object v1, v2, Lcom/android/dialer/precall/impl/PreCallModule_ProvideActionsFactory;->duoActionProvider:Lcom/android/dialer/precall/impl/DuoAction_Factory;

    iput-object v0, v2, Lcom/android/dialer/precall/impl/PreCallModule_ProvideActionsFactory;->callingAccountSelectorProvider:Lcom/android/dialer/precall/impl/CallingAccountSelector_Factory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideActionsProvider:Lcom/android/dialer/precall/impl/PreCallModule_ProvideActionsFactory;

    new-instance v0, Lcom/android/dialer/precall/impl/PreCallImpl_Factory;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object v2, v0, Lcom/android/dialer/precall/impl/PreCallImpl_Factory;->actionsProvider:Lcom/android/dialer/precall/impl/PreCallModule_ProvideActionsFactory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->preCallImplProvider:Lcom/android/dialer/precall/impl/PreCallImpl_Factory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->toProvider4:Ldagger/internal/DoubleCheck;

    iget-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideUnencryptedSharedPrefsProvider:Ldagger/internal/DoubleCheck;

    iget-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->toProvider2:Ldagger/internal/DoubleCheck;

    new-instance v3, Lcom/android/dialer/promotion/impl/RttPromotion_Factory;

    invoke-direct {v3}, Ljava/lang/Object;-><init>()V

    iput-object v0, v3, Lcom/android/dialer/promotion/impl/RttPromotion_Factory;->contextProvider:Ljavax/inject/Provider;

    iput-object v1, v3, Lcom/android/dialer/promotion/impl/RttPromotion_Factory;->sharedPreferencesProvider:Ljavax/inject/Provider;

    iput-object v2, v3, Lcom/android/dialer/promotion/impl/RttPromotion_Factory;->configProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->rttPromotionProvider:Lcom/android/dialer/promotion/impl/RttPromotion_Factory;

    iget-object v4, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindsDuoProvider:Ldagger/internal/DoubleCheck;

    new-instance v5, Lcom/android/dialer/promotion/impl/DuoPromotion_Factory;

    invoke-direct {v5}, Ljava/lang/Object;-><init>()V

    iput-object v0, v5, Lcom/android/dialer/promotion/impl/DuoPromotion_Factory;->contextProvider:Ljavax/inject/Provider;

    iput-object v2, v5, Lcom/android/dialer/promotion/impl/DuoPromotion_Factory;->configProvider:Ljavax/inject/Provider;

    iput-object v4, v5, Lcom/android/dialer/promotion/impl/DuoPromotion_Factory;->duoProvider:Ljavax/inject/Provider;

    iput-object v1, v5, Lcom/android/dialer/promotion/impl/DuoPromotion_Factory;->sharedPreferencesProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v5, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->duoPromotionProvider:Lcom/android/dialer/promotion/impl/DuoPromotion_Factory;

    new-instance v1, Lcom/android/dialer/promotion/impl/PromotionModule_ProvidePriorityPromotionListFactory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v3, v1, Lcom/android/dialer/promotion/impl/PromotionModule_ProvidePriorityPromotionListFactory;->rttPromotionProvider:Lcom/android/dialer/promotion/impl/RttPromotion_Factory;

    iput-object v5, v1, Lcom/android/dialer/promotion/impl/PromotionModule_ProvidePriorityPromotionListFactory;->duoPromotionProvider:Lcom/android/dialer/promotion/impl/DuoPromotion_Factory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->providePriorityPromotionListProvider:Lcom/android/dialer/promotion/impl/PromotionModule_ProvidePriorityPromotionListFactory;

    iget-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideBackgroundExecutorProvider:Ldagger/internal/DoubleCheck;

    new-instance v2, Lcom/android/dialer/contacts/hiresphoto/HighResolutionPhotoRequesterImpl_Factory;

    invoke-direct {v2}, Ljava/lang/Object;-><init>()V

    iput-object v0, v2, Lcom/android/dialer/contacts/hiresphoto/HighResolutionPhotoRequesterImpl_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v1, v2, Lcom/android/dialer/contacts/hiresphoto/HighResolutionPhotoRequesterImpl_Factory;->backgroundExecutorProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->highResolutionPhotoRequesterImplProvider:Lcom/android/dialer/contacts/hiresphoto/HighResolutionPhotoRequesterImpl_Factory;

    iput-object v2, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->toHighResolutionPhotoRequesterImplProvider:Lcom/android/dialer/contacts/hiresphoto/HighResolutionPhotoRequesterImpl_Factory;

    iget-object v3, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContactDisplayPreferencesProvider:Lcom/android/dialer/contacts/ContactsModule_ProvideContactDisplayPreferencesFactory;

    new-instance v4, Lcom/android/dialer/speeddial/loader/SpeedDialUiItemMutator_Factory;

    invoke-direct {v4}, Ljava/lang/Object;-><init>()V

    iput-object v0, v4, Lcom/android/dialer/speeddial/loader/SpeedDialUiItemMutator_Factory;->appContextProvider:Ljavax/inject/Provider;

    iput-object v1, v4, Lcom/android/dialer/speeddial/loader/SpeedDialUiItemMutator_Factory;->backgroundExecutorProvider:Ljavax/inject/Provider;

    iput-object v3, v4, Lcom/android/dialer/speeddial/loader/SpeedDialUiItemMutator_Factory;->contactDisplayPreferencesProvider:Ljavax/inject/Provider;

    iput-object v2, v4, Lcom/android/dialer/speeddial/loader/SpeedDialUiItemMutator_Factory;->highResolutionPhotoRequesterProvider:Lcom/android/dialer/contacts/hiresphoto/HighResolutionPhotoRequesterImpl_Factory;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v4}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->speedDialUiItemMutatorProvider:Ldagger/internal/DoubleCheck;

    sget-object v0, Lcom/android/dialer/preferredsim/suggestion/stub/StubSuggestionProvider_Factory;->INSTANCE:Lcom/android/dialer/preferredsim/suggestion/stub/StubSuggestionProvider_Factory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindSuggestionProvider:Ldagger/internal/DoubleCheck;

    sget-object v0, Lcom/android/dialer/simulator/impl/SimulatorImpl_Factory;->INSTANCE:Lcom/android/dialer/simulator/impl/SimulatorImpl_Factory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindsSimulatorProvider:Ldagger/internal/DoubleCheck;

    sget-object v0, Lcom/android/dialer/simulator/stub/SimulatorEnrichedCallStub_Factory;->INSTANCE:Lcom/android/dialer/simulator/stub/SimulatorEnrichedCallStub_Factory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindsSimulatorEnrichedCallProvider:Ldagger/internal/DoubleCheck;

    sget-object v0, Lcom/android/dialer/simulator/impl/SimulatorConnectionsBankImpl_Factory;->INSTANCE:Lcom/android/dialer/simulator/impl/SimulatorConnectionsBankImpl_Factory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindsSimulatorConnectionsBankProvider:Ldagger/internal/DoubleCheck;

    sget-object v0, Lcom/android/dialer/strictmode/impl/SystemDialerStrictMode_Factory;->INSTANCE:Lcom/android/dialer/strictmode/impl/SystemDialerStrictMode_Factory;

    invoke-static {v0}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindDialerStrictModeProvider:Ldagger/internal/DoubleCheck;

    iget-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideContextProvider:Lcom/android/dialer/inject/ContextModule_ProvideContextFactory;

    new-instance v1, Lcom/android/dialer/theme/base/impl/AospThemeModule_ProvideThemeModuleFactory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v0, v1, Lcom/android/dialer/theme/base/impl/AospThemeModule_ProvideThemeModuleFactory;->contextProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v1, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideThemeModuleProvider:Lcom/android/dialer/theme/base/impl/AospThemeModule_ProvideThemeModuleFactory;

    new-instance v1, Lcom/android/voicemail/impl/VoicemailModule_ProvideVoicemailClientFactory;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    iput-object v0, v1, Lcom/android/voicemail/impl/VoicemailModule_ProvideVoicemailClientFactory;->contextProvider:Ljavax/inject/Provider;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v1}, Ldagger/internal/DoubleCheck;->provider(Ljavax/inject/Provider;)Ldagger/internal/DoubleCheck;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->provideVoicemailClientProvider:Ldagger/internal/DoubleCheck;

    return-object p0
.end method

.method public final component()Ljava/lang/Object;
    .registers 2

    iget-object v0, p0, Lcom/android/dialer/binary/aosp/AospDialerApplication;->rootComponent:Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;

    if-nez v0, :cond_16

    monitor-enter p0

    :try_start_5
    iget-object v0, p0, Lcom/android/dialer/binary/aosp/AospDialerApplication;->rootComponent:Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;

    if-nez v0, :cond_12

    invoke-virtual {p0}, Lcom/android/dialer/binary/aosp/AospDialerApplication;->buildRootComponent()Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/binary/aosp/AospDialerApplication;->rootComponent:Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;

    goto :goto_12

    :catchall_10
    move-exception v0

    goto :goto_14

    :cond_12
    :goto_12
    monitor-exit p0

    return-object v0

    :goto_14
    monitor-exit p0
    :try_end_15
    .catchall {:try_start_5 .. :try_end_15} :catchall_10

    throw v0

    :cond_16
    return-object v0
.end method

.method public final onCreate()V
    .registers 16

    const-string v0, "DialerApplication.onCreate"

    invoke-static {v0}, Landroid/os/Trace;->beginSection(Ljava/lang/String;)V

    invoke-virtual {p0}, Landroid/content/Context;->getApplicationContext()Landroid/content/Context;

    move-result-object v0

    check-cast v0, Lcom/android/dialer/binary/aosp/AospDialerApplication;

    invoke-virtual {v0}, Lcom/android/dialer/binary/aosp/AospDialerApplication;->component()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;

    iget-object v0, v0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->bindDialerStrictModeProvider:Ldagger/internal/DoubleCheck;

    invoke-virtual {v0}, Ldagger/internal/DoubleCheck;->get()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Lcom/android/dialer/strictmode/impl/SystemDialerStrictMode;

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    invoke-static {}, Lcom/android/dialer/strictmode/StrictModeUtils;->isStrictModeAllowed()Z

    move-result v0

    const/4 v1, 0x0

    if-eqz v0, :cond_81

    invoke-static {p0}, Landroid/support/v4/os/UserManagerCompat;->isUserUnlocked(Landroid/content/Context;)Z

    move-result v0

    if-eqz v0, :cond_33

    invoke-static {p0}, Landroid/preference/PreferenceManager;->getDefaultSharedPreferences(Landroid/content/Context;)Landroid/content/SharedPreferences;

    invoke-virtual {p0}, Landroid/app/Application;->getPackageName()Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p0, v0, v1}, Landroid/app/Application;->getSharedPreferences(Ljava/lang/String;I)Landroid/content/SharedPreferences;

    :cond_33
    invoke-static {p0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->get$9(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;

    move-result-object v0

    invoke-virtual {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->unencryptedSharedPrefs()Landroid/content/SharedPreferences;

    sget-object v0, Lcom/android/dialer/strictmode/impl/SystemDialerStrictMode;->THREAD_DEATH_PENALTY:Landroid/os/StrictMode$ThreadPolicy;

    new-instance v2, Landroid/os/StrictMode$ThreadPolicy$Builder;

    invoke-direct {v2, v0}, Landroid/os/StrictMode$ThreadPolicy$Builder;-><init>(Landroid/os/StrictMode$ThreadPolicy;)V

    invoke-virtual {v2}, Landroid/os/StrictMode$ThreadPolicy$Builder;->detectAll()Landroid/os/StrictMode$ThreadPolicy$Builder;

    move-result-object v0

    invoke-virtual {v0}, Landroid/os/StrictMode$ThreadPolicy$Builder;->build()Landroid/os/StrictMode$ThreadPolicy;

    move-result-object v0

    invoke-static {v0}, Landroid/os/StrictMode;->setThreadPolicy(Landroid/os/StrictMode$ThreadPolicy;)V

    sget-object v0, Lcom/android/dialer/strictmode/impl/SystemDialerStrictMode;->VM_DEATH_PENALTY:Landroid/os/StrictMode$VmPolicy;

    new-instance v2, Lcom/android/dialer/strictmode/impl/AutoValue_SystemDialerStrictMode_StrictModeVmConfig;

    invoke-direct {v2}, Ljava/lang/Object;-><init>()V

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-static {v2}, Lcom/android/dialer/common/Assert;->isNotNull(Ljava/lang/Object;)V

    new-instance v2, Landroid/os/StrictMode$VmPolicy$Builder;

    invoke-direct {v2, v0}, Landroid/os/StrictMode$VmPolicy$Builder;-><init>(Landroid/os/StrictMode$VmPolicy;)V

    invoke-virtual {v2}, Landroid/os/StrictMode$VmPolicy$Builder;->detectLeakedClosableObjects()Landroid/os/StrictMode$VmPolicy$Builder;

    move-result-object v0

    invoke-virtual {v0}, Landroid/os/StrictMode$VmPolicy$Builder;->detectLeakedSqlLiteObjects()Landroid/os/StrictMode$VmPolicy$Builder;

    move-result-object v0

    invoke-virtual {v0}, Landroid/os/StrictMode$VmPolicy$Builder;->detectContentUriWithoutPermission()Landroid/os/StrictMode$VmPolicy$Builder;

    invoke-virtual {v0}, Landroid/os/StrictMode$VmPolicy$Builder;->build()Landroid/os/StrictMode$VmPolicy;

    move-result-object v0

    invoke-static {v0}, Landroid/os/StrictMode;->setVmPolicy(Landroid/os/StrictMode$VmPolicy;)V

    new-instance v0, Landroid/os/Handler;

    invoke-static {}, Landroid/os/Looper;->myLooper()Landroid/os/Looper;

    move-result-object v2

    invoke-direct {v0, v2}, Landroid/os/Handler;-><init>(Landroid/os/Looper;)V

    new-instance v2, Lcom/android/dialer/strictmode/impl/SystemDialerStrictMode$$ExternalSyntheticLambda0;

    invoke-direct {v2}, Ljava/lang/Object;-><init>()V

    invoke-virtual {v0, v2}, Landroid/os/Handler;->postAtFrontOfQueue(Ljava/lang/Runnable;)Z

    :cond_81
    invoke-super {p0}, Landroid/app/Application;->onCreate()V

    new-instance v0, Lcom/android/dialer/blocking/BlockedNumbersAutoMigrator;

    invoke-virtual {p0}, Landroid/app/Application;->getApplicationContext()Landroid/content/Context;

    move-result-object v2

    new-instance v3, Lcom/android/dialer/blocking/FilteredNumberAsyncQueryHandler;

    invoke-virtual {p0}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v4

    invoke-direct {v3, v4}, Landroid/content/AsyncQueryHandler;-><init>(Landroid/content/ContentResolver;)V

    iput-object p0, v3, Lcom/android/dialer/blocking/FilteredNumberAsyncQueryHandler;->context:Landroid/content/Context;

    invoke-static {p0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$ContactsComponentImpl;->get$1(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$ContactsComponentImpl;

    move-result-object v4

    invoke-virtual {v4}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$ContactsComponentImpl;->dialerExecutorFactory()Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory;

    move-result-object v4

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    invoke-static {v2}, Lcom/android/dialer/common/Assert;->isNotNull(Ljava/lang/Object;)V

    iput-object v2, v0, Lcom/android/dialer/blocking/BlockedNumbersAutoMigrator;->appContext:Landroid/content/Context;

    invoke-static {v3}, Lcom/android/dialer/common/Assert;->isNotNull(Ljava/lang/Object;)V

    iput-object v3, v0, Lcom/android/dialer/blocking/BlockedNumbersAutoMigrator;->queryHandler:Lcom/android/dialer/blocking/FilteredNumberAsyncQueryHandler;

    invoke-static {v4}, Lcom/android/dialer/common/Assert;->isNotNull(Ljava/lang/Object;)V

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    new-instance v3, Lcom/android/dialer/blocking/BlockedNumbersAutoMigrator$1;

    invoke-direct {v3}, Ljava/lang/Object;-><init>()V

    iput-object v2, v3, Lcom/android/dialer/blocking/BlockedNumbersAutoMigrator$1;->this$0:Ljava/lang/Object;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-virtual {v4, v3}, Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory;->createNonUiTaskBuilder(Lcom/android/dialer/common/concurrent/DialerExecutor$Worker;)Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory$NonUiTaskBuilder;

    move-result-object v2

    new-instance v3, Lcom/android/dialer/blocking/BlockedNumbersAutoMigrator$$ExternalSyntheticLambda0;

    invoke-direct {v3}, Ljava/lang/Object;-><init>()V

    iput-object v0, v3, Lcom/android/dialer/blocking/BlockedNumbersAutoMigrator$$ExternalSyntheticLambda0;->f$0:Lcom/android/dialer/blocking/BlockedNumbersAutoMigrator;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-virtual {v2, v3}, Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory$BaseTaskBuilder;->onSuccess(Lcom/android/dialer/common/concurrent/DialerExecutor$SuccessListener;)V

    invoke-virtual {v2}, Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory$NonUiTaskBuilder;->build()Lcom/android/dialer/common/concurrent/DialerExecutor;

    move-result-object v0

    check-cast v0, Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory$NonUiDialerExecutor;

    const/4 v2, 0x0

    invoke-virtual {v0, v2}, Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory$NonUiDialerExecutor;->executeParallel(Ljava/lang/Object;)V

    invoke-static {p0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$SpamComponentImpl;->get$2(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$SpamComponentImpl;

    move-result-object v0

    invoke-virtual {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$SpamComponentImpl;->callLogConfig()Lcom/android/dialer/calllog/config/CallLogConfigImpl;

    move-result-object v0

    iget-object v3, v0, Lcom/android/dialer/calllog/config/CallLogConfigImpl;->appContext:Landroid/content/Context;

    invoke-static {v3}, Landroid/support/v4/os/UserManagerCompat;->isUserUnlocked(Landroid/content/Context;)Z

    move-result v3

    const/4 v4, 0x4

    const/4 v5, 0x1

    if-eqz v3, :cond_127

    iget-object v3, v0, Lcom/android/dialer/calllog/config/CallLogConfigImpl;->appContext:Landroid/content/Context;

    const-class v6, Landroid/app/job/JobScheduler;

    invoke-virtual {v3, v6}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v3

    check-cast v3, Landroid/app/job/JobScheduler;

    invoke-static {v3}, Lcom/android/dialer/common/Assert;->isNotNull(Ljava/lang/Object;)V

    new-instance v6, Landroid/app/job/JobInfo$Builder;

    new-instance v7, Landroid/content/ComponentName;

    iget-object v8, v0, Lcom/android/dialer/calllog/config/CallLogConfigImpl;->appContext:Landroid/content/Context;

    const-class v9, Lcom/android/dialer/calllog/config/CallLogConfigImpl$PollingJob;

    invoke-direct {v7, v8, v9}, Landroid/content/ComponentName;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    const/16 v8, 0x190

    invoke-direct {v6, v8, v7}, Landroid/app/job/JobInfo$Builder;-><init>(ILandroid/content/ComponentName;)V

    const-wide/32 v7, 0x5265c00

    invoke-virtual {v6, v7, v8}, Landroid/app/job/JobInfo$Builder;->setPeriodic(J)Landroid/app/job/JobInfo$Builder;

    move-result-object v6

    invoke-virtual {v6, v5}, Landroid/app/job/JobInfo$Builder;->setPersisted(Z)Landroid/app/job/JobInfo$Builder;

    move-result-object v6

    invoke-virtual {v6, v5}, Landroid/app/job/JobInfo$Builder;->setRequiresCharging(Z)Landroid/app/job/JobInfo$Builder;

    move-result-object v6

    invoke-virtual {v6, v5}, Landroid/app/job/JobInfo$Builder;->setRequiresDeviceIdle(Z)Landroid/app/job/JobInfo$Builder;

    move-result-object v6

    invoke-virtual {v6}, Landroid/app/job/JobInfo$Builder;->build()Landroid/app/job/JobInfo;

    move-result-object v6

    const-string v7, "scheduling"

    new-array v8, v1, [Ljava/lang/Object;

    const-string v9, "CallLogConfigImpl.schedulePollingJob"

    invoke-static {v4, v9, v7, v8}, Lcom/android/dialer/common/LogUtil;->println(ILjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    invoke-virtual {v3, v6}, Landroid/app/job/JobScheduler;->schedule(Landroid/app/job/JobInfo;)I

    :cond_127
    iget-object v0, v0, Lcom/android/dialer/calllog/config/CallLogConfigImpl;->sharedPreferences:Landroid/content/SharedPreferences;

    const-string v3, "newCallLogFrameworkEnabled"

    invoke-interface {v0, v3, v1}, Landroid/content/SharedPreferences;->getBoolean(Ljava/lang/String;Z)Z

    move-result v0

    if-eqz v0, :cond_161

    invoke-static {p0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$SpamComponentImpl;->get$1(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$SpamComponentImpl;

    move-result-object v0

    iget-object v0, v0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$SpamComponentImpl;->this$0:Ljava/lang/Object;

    check-cast v0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;

    iget-object v0, v0, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent;->callLogFrameworkProvider:Ldagger/internal/DoubleCheck;

    invoke-virtual {v0}, Ldagger/internal/DoubleCheck;->get()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Lcom/android/dialer/calllog/CallLogFramework;

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    const-string v3, "CallLogFramework.registerContentObservers"

    invoke-static {v3}, Lcom/android/dialer/common/LogUtil;->enterBlock(Ljava/lang/String;)V

    iget-object v0, v0, Lcom/android/dialer/calllog/CallLogFramework;->dataSources:Lcom/android/dialer/calllog/CallLogModule$1;

    iget-object v0, v0, Lcom/android/dialer/calllog/CallLogModule$1;->val$allDataSources:Lcom/google/common/collect/ImmutableList;

    invoke-virtual {v0}, Lcom/google/common/collect/ImmutableList;->iterator()Lcom/google/common/collect/UnmodifiableIterator;

    move-result-object v0

    :goto_151
    invoke-interface {v0}, Ljava/util/Iterator;->hasNext()Z

    move-result v3

    if-eqz v3, :cond_16a

    invoke-interface {v0}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v3

    check-cast v3, Lcom/android/dialer/calllog/datasources/CallLogDataSource;

    invoke-interface {v3}, Lcom/android/dialer/calllog/datasources/CallLogDataSource;->registerContentObservers()V

    goto :goto_151

    :cond_161
    const-string v0, "framework not enabled"

    new-array v3, v1, [Ljava/lang/Object;

    const-string v6, "DialerApplication.initializeAnnotatedCallLog"

    invoke-static {v4, v6, v0, v3}, Lcom/android/dialer/common/LogUtil;->println(ILjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    :cond_16a
    new-instance v0, Lcom/android/dialer/persistentlog/PersistentLogFileHandler;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    sput-object v0, Lcom/android/dialer/persistentlog/PersistentLogger;->fileHandler:Lcom/android/dialer/persistentlog/PersistentLogFileHandler;

    new-instance v0, Landroid/os/HandlerThread;

    const-string v3, "PersistentLogger"

    invoke-direct {v0, v3}, Landroid/os/HandlerThread;-><init>(Ljava/lang/String;)V

    sput-object v0, Lcom/android/dialer/persistentlog/PersistentLogger;->loggerThread:Landroid/os/HandlerThread;

    invoke-virtual {v0}, Landroid/os/HandlerThread;->start()V

    new-instance v0, Landroid/os/Handler;

    sget-object v3, Lcom/android/dialer/persistentlog/PersistentLogger;->loggerThread:Landroid/os/HandlerThread;

    invoke-virtual {v3}, Landroid/os/HandlerThread;->getLooper()Landroid/os/Looper;

    move-result-object v3

    new-instance v6, Lcom/android/dialer/persistentlog/PersistentLogger$$ExternalSyntheticLambda0;

    invoke-direct {v6}, Ljava/lang/Object;-><init>()V

    iput-object p0, v6, Lcom/android/dialer/persistentlog/PersistentLogger$$ExternalSyntheticLambda0;->f$0:Lcom/android/dialer/binary/aosp/AospDialerApplication;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-direct {v0, v3, v6}, Landroid/os/Handler;-><init>(Landroid/os/Looper;Landroid/os/Handler$Callback;)V

    sput-object v0, Lcom/android/dialer/persistentlog/PersistentLogger;->loggerThreadHandler:Landroid/os/Handler;

    new-instance v3, Lcom/android/dialer/persistentlog/PersistentLogger$$ExternalSyntheticLambda1;

    invoke-direct {v3}, Ljava/lang/Object;-><init>()V

    iput-object p0, v3, Lcom/android/dialer/persistentlog/PersistentLogger$$ExternalSyntheticLambda1;->f$0:Lcom/android/dialer/binary/aosp/AospDialerApplication;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-virtual {v0, v3}, Landroid/os/Handler;->post(Ljava/lang/Runnable;)Z

    invoke-static {v5}, Lcom/android/dialer/common/Assert;->checkArgument(Z)V

    invoke-static {p0}, Lcom/android/dialer/common/Assert;->isNotNull(Ljava/lang/Object;)V

    const-class v0, Landroid/app/NotificationManager;

    invoke-virtual {p0, v0}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/app/NotificationManager;

    new-instance v3, Landroid/util/ArraySet;

    invoke-direct {v3}, Landroid/util/ArraySet;-><init>()V

    const-string v6, "phone_incoming_call"

    invoke-virtual {v3, v6}, Landroid/util/ArraySet;->add(Ljava/lang/Object;)Z

    const-string v7, "phone_ongoing_call"

    invoke-virtual {v3, v7}, Landroid/util/ArraySet;->add(Ljava/lang/Object;)Z

    const-string v8, "phone_missed_call"

    invoke-virtual {v3, v8}, Landroid/util/ArraySet;->add(Ljava/lang/Object;)Z

    const-string v9, "phone_default"

    invoke-virtual {v3, v9}, Landroid/util/ArraySet;->add(Ljava/lang/Object;)Z

    invoke-static {v5}, Lcom/android/dialer/common/Assert;->checkArgument(Z)V

    invoke-static {p0}, Lcom/android/dialer/common/Assert;->isNotNull(Ljava/lang/Object;)V

    new-instance v10, Landroid/util/ArraySet;

    invoke-direct {v10}, Landroid/util/ArraySet;-><init>()V

    invoke-static {p0}, Lcom/android/dialer/notification/VoicemailChannelUtils;->isSingleSimDevice(Landroid/content/Context;)Z

    move-result v11

    const-string v12, "phone_voicemail"

    if-eqz v11, :cond_1e2

    invoke-virtual {v10, v12}, Landroid/util/ArraySet;->add(Ljava/lang/Object;)Z

    goto :goto_1fe

    :cond_1e2
    invoke-static {p0}, Lcom/android/dialer/notification/VoicemailChannelUtils;->getAllEligableAccounts(Lcom/android/dialer/binary/aosp/AospDialerApplication;)Ljava/util/List;

    move-result-object v11

    invoke-interface {v11}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v11

    :goto_1ea
    invoke-interface {v11}, Ljava/util/Iterator;->hasNext()Z

    move-result v13

    if-eqz v13, :cond_1fe

    invoke-interface {v11}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v13

    check-cast v13, Landroid/telecom/PhoneAccountHandle;

    invoke-static {v13}, Lcom/android/dialer/notification/VoicemailChannelUtils;->getChannelIdForAccount(Landroid/telecom/PhoneAccountHandle;)Ljava/lang/String;

    move-result-object v13

    invoke-virtual {v10, v13}, Landroid/util/ArraySet;->add(Ljava/lang/Object;)Z

    goto :goto_1ea

    :cond_1fe
    :goto_1fe
    invoke-virtual {v3, v10}, Landroid/util/ArraySet;->addAll(Ljava/util/Collection;)Z

    new-instance v10, Landroid/util/ArraySet;

    invoke-direct {v10}, Landroid/util/ArraySet;-><init>()V

    const-class v11, Landroid/app/NotificationManager;

    invoke-virtual {p0, v11}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v11

    check-cast v11, Landroid/app/NotificationManager;

    invoke-virtual {v11}, Landroid/app/NotificationManager;->getNotificationChannels()Ljava/util/List;

    move-result-object v11

    invoke-interface {v11}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v11

    :goto_216
    invoke-interface {v11}, Ljava/util/Iterator;->hasNext()Z

    move-result v13

    if-eqz v13, :cond_22a

    invoke-interface {v11}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v13

    check-cast v13, Landroid/app/NotificationChannel;

    invoke-virtual {v13}, Landroid/app/NotificationChannel;->getId()Ljava/lang/String;

    move-result-object v13

    invoke-virtual {v10, v13}, Landroid/util/ArraySet;->add(Ljava/lang/Object;)Z

    goto :goto_216

    :cond_22a
    invoke-virtual {v3, v10}, Landroid/util/ArraySet;->equals(Ljava/lang/Object;)Z

    move-result v11

    if-eqz v11, :cond_232

    goto/16 :goto_39c

    :cond_232
    const-string v11, "doing an expensive initialization of all notification channels"

    new-array v13, v1, [Ljava/lang/Object;

    const-string v14, "NotificationChannelManager.initChannels"

    invoke-static {v4, v14, v11, v13}, Lcom/android/dialer/common/LogUtil;->println(ILjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    new-instance v11, Ljava/lang/StringBuilder;

    const-string v13, "desired channel IDs: "

    invoke-direct {v11, v13}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v11, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {v11}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v11

    new-array v13, v1, [Ljava/lang/Object;

    invoke-static {v4, v14, v11, v13}, Lcom/android/dialer/common/LogUtil;->println(ILjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    new-instance v11, Ljava/lang/StringBuilder;

    const-string v13, "existing channel IDs: "

    invoke-direct {v11, v13}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {v11, v10}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    invoke-virtual {v11}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v11

    new-array v13, v1, [Ljava/lang/Object;

    invoke-static {v4, v14, v11, v13}, Lcom/android/dialer/common/LogUtil;->println(ILjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    invoke-virtual {v10}, Landroid/util/ArraySet;->iterator()Ljava/util/Iterator;

    move-result-object v10

    :cond_265
    :goto_265
    invoke-interface {v10}, Ljava/util/Iterator;->hasNext()Z

    move-result v11

    if-eqz v11, :cond_27b

    invoke-interface {v10}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v11

    check-cast v11, Ljava/lang/String;

    invoke-virtual {v3, v11}, Landroid/util/ArraySet;->contains(Ljava/lang/Object;)Z

    move-result v13

    if-nez v13, :cond_265

    invoke-virtual {v0, v11}, Landroid/app/NotificationManager;->deleteNotificationChannel(Ljava/lang/String;)V

    goto :goto_265

    :cond_27b
    new-instance v0, Landroid/app/NotificationChannel;

    const v3, 0x7f110243

    invoke-virtual {p0, v3}, Landroid/content/Context;->getText(I)Ljava/lang/CharSequence;

    move-result-object v3

    const/4 v10, 0x5

    invoke-direct {v0, v6, v3, v10}, Landroid/app/NotificationChannel;-><init>(Ljava/lang/String;Ljava/lang/CharSequence;I)V

    invoke-virtual {v0, v1}, Landroid/app/NotificationChannel;->setShowBadge(Z)V

    invoke-virtual {v0, v5}, Landroid/app/NotificationChannel;->enableLights(Z)V

    invoke-virtual {v0, v1}, Landroid/app/NotificationChannel;->enableVibration(Z)V

    new-instance v3, Landroid/media/AudioAttributes$Builder;

    invoke-direct {v3}, Landroid/media/AudioAttributes$Builder;-><init>()V

    invoke-virtual {v3, v10}, Landroid/media/AudioAttributes$Builder;->setUsage(I)Landroid/media/AudioAttributes$Builder;

    move-result-object v3

    invoke-virtual {v3}, Landroid/media/AudioAttributes$Builder;->build()Landroid/media/AudioAttributes;

    move-result-object v3

    invoke-virtual {v0, v2, v3}, Landroid/app/NotificationChannel;->setSound(Landroid/net/Uri;Landroid/media/AudioAttributes;)V

    const-class v3, Landroid/app/NotificationManager;

    invoke-virtual {p0, v3}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v3

    check-cast v3, Landroid/app/NotificationManager;

    invoke-virtual {v3, v0}, Landroid/app/NotificationManager;->createNotificationChannel(Landroid/app/NotificationChannel;)V

    new-instance v0, Landroid/app/NotificationChannel;

    const v3, 0x7f110246

    invoke-virtual {p0, v3}, Landroid/content/Context;->getText(I)Ljava/lang/CharSequence;

    move-result-object v3

    const/4 v6, 0x3

    invoke-direct {v0, v7, v3, v6}, Landroid/app/NotificationChannel;-><init>(Ljava/lang/String;Ljava/lang/CharSequence;I)V

    invoke-virtual {v0, v1}, Landroid/app/NotificationChannel;->setShowBadge(Z)V

    invoke-virtual {v0, v1}, Landroid/app/NotificationChannel;->enableLights(Z)V

    invoke-virtual {v0, v1}, Landroid/app/NotificationChannel;->enableVibration(Z)V

    new-instance v3, Landroid/media/AudioAttributes$Builder;

    invoke-direct {v3}, Landroid/media/AudioAttributes$Builder;-><init>()V

    invoke-virtual {v3, v10}, Landroid/media/AudioAttributes$Builder;->setUsage(I)Landroid/media/AudioAttributes$Builder;

    move-result-object v3

    invoke-virtual {v3}, Landroid/media/AudioAttributes$Builder;->build()Landroid/media/AudioAttributes;

    move-result-object v3

    invoke-virtual {v0, v2, v3}, Landroid/app/NotificationChannel;->setSound(Landroid/net/Uri;Landroid/media/AudioAttributes;)V

    const-class v3, Landroid/app/NotificationManager;

    invoke-virtual {p0, v3}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v3

    check-cast v3, Landroid/app/NotificationManager;

    invoke-virtual {v3, v0}, Landroid/app/NotificationManager;->createNotificationChannel(Landroid/app/NotificationChannel;)V

    new-instance v0, Landroid/app/NotificationChannel;

    const v3, 0x7f110245

    invoke-virtual {p0, v3}, Landroid/content/Context;->getText(I)Ljava/lang/CharSequence;

    move-result-object v3

    invoke-direct {v0, v8, v3, v6}, Landroid/app/NotificationChannel;-><init>(Ljava/lang/String;Ljava/lang/CharSequence;I)V

    invoke-virtual {v0, v5}, Landroid/app/NotificationChannel;->setShowBadge(Z)V

    invoke-virtual {v0, v5}, Landroid/app/NotificationChannel;->enableLights(Z)V

    invoke-virtual {v0, v5}, Landroid/app/NotificationChannel;->enableVibration(Z)V

    new-instance v3, Landroid/media/AudioAttributes$Builder;

    invoke-direct {v3}, Landroid/media/AudioAttributes$Builder;-><init>()V

    invoke-virtual {v3, v10}, Landroid/media/AudioAttributes$Builder;->setUsage(I)Landroid/media/AudioAttributes$Builder;

    move-result-object v3

    invoke-virtual {v3}, Landroid/media/AudioAttributes$Builder;->build()Landroid/media/AudioAttributes;

    move-result-object v3

    invoke-virtual {v0, v2, v3}, Landroid/app/NotificationChannel;->setSound(Landroid/net/Uri;Landroid/media/AudioAttributes;)V

    const-class v3, Landroid/app/NotificationManager;

    invoke-virtual {p0, v3}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v3

    check-cast v3, Landroid/app/NotificationManager;

    invoke-virtual {v3, v0}, Landroid/app/NotificationManager;->createNotificationChannel(Landroid/app/NotificationChannel;)V

    new-instance v0, Landroid/app/NotificationChannel;

    const v3, 0x7f110244

    invoke-virtual {p0, v3}, Landroid/content/Context;->getText(I)Ljava/lang/CharSequence;

    move-result-object v3

    invoke-direct {v0, v9, v3, v6}, Landroid/app/NotificationChannel;-><init>(Ljava/lang/String;Ljava/lang/CharSequence;I)V

    invoke-virtual {v0, v1}, Landroid/app/NotificationChannel;->setShowBadge(Z)V

    invoke-virtual {v0, v5}, Landroid/app/NotificationChannel;->enableLights(Z)V

    invoke-virtual {v0, v5}, Landroid/app/NotificationChannel;->enableVibration(Z)V

    const-class v3, Landroid/app/NotificationManager;

    invoke-virtual {p0, v3}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v3

    check-cast v3, Landroid/app/NotificationManager;

    invoke-virtual {v3, v0}, Landroid/app/NotificationManager;->createNotificationChannel(Landroid/app/NotificationChannel;)V

    invoke-static {v5}, Lcom/android/dialer/common/Assert;->checkArgument(Z)V

    invoke-static {p0}, Lcom/android/dialer/common/Assert;->isNotNull(Ljava/lang/Object;)V

    invoke-static {p0}, Lcom/android/dialer/notification/VoicemailChannelUtils;->isSingleSimDevice(Landroid/content/Context;)Z

    move-result v0

    if-eqz v0, :cond_384

    invoke-static {p0, v12, v2}, Lcom/android/dialer/notification/VoicemailChannelUtils;->newChannel(Landroid/content/Context;Ljava/lang/String;Ljava/lang/CharSequence;)Landroid/app/NotificationChannel;

    move-result-object v0

    const-string v2, "android.permission.READ_PHONE_STATE"

    invoke-static {p0, v2}, Lcom/android/dialer/util/PermissionsUtil;->hasPermission(Landroid/content/Context;Ljava/lang/String;)Z

    move-result v2

    const-string v3, "VoicemailChannelUtils.migrateGlobalVoicemailSoundSettings"

    if-nez v2, :cond_34f

    const-string v2, "missing phone permission, not migrating sound settings"

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v4, v3, v2, v1}, Lcom/android/dialer/common/LogUtil;->println(ILjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    goto :goto_378

    :cond_34f
    const-class v2, Landroid/telecom/TelecomManager;

    invoke-virtual {p0, v2}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v2

    check-cast v2, Landroid/telecom/TelecomManager;

    const-string v5, "tel"

    invoke-virtual {v2, v5}, Landroid/telecom/TelecomManager;->getDefaultOutgoingPhoneAccount(Ljava/lang/String;)Landroid/telecom/PhoneAccountHandle;

    move-result-object v2

    if-nez v2, :cond_367

    const-string v2, "phone account is null, not migrating sound settings"

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v4, v3, v2, v1}, Lcom/android/dialer/common/LogUtil;->println(ILjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    goto :goto_378

    :cond_367
    invoke-static {p0, v2}, Lcom/android/dialer/notification/VoicemailChannelUtils;->isChannelAllowedForAccount(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v5

    if-nez v5, :cond_375

    const-string v2, "phone account is not eligable, not migrating sound settings"

    new-array v1, v1, [Ljava/lang/Object;

    invoke-static {v4, v3, v2, v1}, Lcom/android/dialer/common/LogUtil;->println(ILjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    goto :goto_378

    :cond_375
    invoke-static {p0, v0, v2}, Lcom/android/dialer/notification/VoicemailChannelUtils;->migrateVoicemailSoundSettings(Landroid/content/Context;Landroid/app/NotificationChannel;Landroid/telecom/PhoneAccountHandle;)V

    :goto_378
    const-class v1, Landroid/app/NotificationManager;

    invoke-virtual {p0, v1}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object p0

    check-cast p0, Landroid/app/NotificationManager;

    invoke-virtual {p0, v0}, Landroid/app/NotificationManager;->createNotificationChannel(Landroid/app/NotificationChannel;)V

    goto :goto_39c

    :cond_384
    invoke-static {p0}, Lcom/android/dialer/notification/VoicemailChannelUtils;->getAllEligableAccounts(Lcom/android/dialer/binary/aosp/AospDialerApplication;)Ljava/util/List;

    move-result-object v0

    invoke-interface {v0}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v0

    :goto_38c
    invoke-interface {v0}, Ljava/util/Iterator;->hasNext()Z

    move-result v1

    if-eqz v1, :cond_39c

    invoke-interface {v0}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v1

    check-cast v1, Landroid/telecom/PhoneAccountHandle;

    invoke-static {p0, v1}, Lcom/android/dialer/notification/VoicemailChannelUtils;->createVoicemailChannelForAccount(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)V

    goto :goto_38c

    :cond_39c
    :goto_39c
    invoke-static {}, Landroid/os/Trace;->endSection()V

    return-void
.end method
