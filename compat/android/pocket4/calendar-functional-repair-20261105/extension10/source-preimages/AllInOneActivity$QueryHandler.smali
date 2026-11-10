.class final Lcom/android/calendar/AllInOneActivity$QueryHandler;
.super Landroid/content/AsyncQueryHandler;
.source "AllInOneActivity.kt"


# instance fields
.field final synthetic this$0:Lcom/android/calendar/AllInOneActivity;


# direct methods
.method public constructor <init>(Lcom/android/calendar/AllInOneActivity;Landroid/content/ContentResolver;)V
    .registers 3

    .line 145
    iput-object p1, p0, Lcom/android/calendar/AllInOneActivity$QueryHandler;->this$0:Lcom/android/calendar/AllInOneActivity;

    invoke-direct {p0, p2}, Landroid/content/AsyncQueryHandler;-><init>(Landroid/content/ContentResolver;)V

    return-void
.end method


# virtual methods
.method protected onQueryComplete(ILjava/lang/Object;Landroid/database/Cursor;)V
    .registers 12

    .line 148
    iget-object p1, p0, Lcom/android/calendar/AllInOneActivity$QueryHandler;->this$0:Lcom/android/calendar/AllInOneActivity;

    const/4 p2, 0x0

    invoke-static {p1, p2}, Lcom/android/calendar/AllInOneActivity;->access$setMCheckForAccounts$p(Lcom/android/calendar/AllInOneActivity;Z)V

    if-eqz p3, :cond_57

    .line 151
    :try_start_8
    invoke-interface {p3}, Landroid/database/Cursor;->getCount()I

    move-result p1

    if-gtz p1, :cond_57

    iget-object p1, p0, Lcom/android/calendar/AllInOneActivity$QueryHandler;->this$0:Lcom/android/calendar/AllInOneActivity;

    invoke-virtual {p1}, Landroid/app/Activity;->isFinishing()Z

    move-result p1
    :try_end_14
    .catchall {:try_start_8 .. :try_end_14} :catchall_51

    if-eqz p1, :cond_17

    goto :goto_57

    .line 156
    :cond_17
    invoke-interface {p3}, Landroid/database/Cursor;->close()V

    .line 159
    new-instance v4, Landroid/os/Bundle;

    invoke-direct {v4}, Landroid/os/Bundle;-><init>()V

    .line 162
    iget-object p1, p0, Lcom/android/calendar/AllInOneActivity$QueryHandler;->this$0:Lcom/android/calendar/AllInOneActivity;

    invoke-virtual {p1}, Landroid/app/Activity;->getResources()Landroid/content/res/Resources;

    move-result-object p1

    const p2, 0x7f0f003a

    invoke-virtual {p1, p2}, Landroid/content/res/Resources;->getString(I)Ljava/lang/String;

    move-result-object p1

    .line 160
    const-string p2, "introMessage"

    invoke-virtual {v4, p2, p1}, Landroid/os/Bundle;->putCharSequence(Ljava/lang/String;Ljava/lang/CharSequence;)V

    .line 164
    const-string p1, "allowSkip"

    const/4 p2, 0x1

    invoke-virtual {v4, p1, p2}, Landroid/os/Bundle;->putBoolean(Ljava/lang/String;Z)V

    .line 165
    iget-object p1, p0, Lcom/android/calendar/AllInOneActivity$QueryHandler;->this$0:Lcom/android/calendar/AllInOneActivity;

    invoke-static {p1}, Landroid/accounts/AccountManager;->get(Landroid/content/Context;)Landroid/accounts/AccountManager;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    .line 167
    iget-object v5, p0, Lcom/android/calendar/AllInOneActivity$QueryHandler;->this$0:Lcom/android/calendar/AllInOneActivity;

    .line 168
    new-instance v6, Lcom/android/calendar/AllInOneActivity$QueryHandler$onQueryComplete$1;

    invoke-direct {v6}, Lcom/android/calendar/AllInOneActivity$QueryHandler$onQueryComplete$1;-><init>()V

    const/4 v7, 0x0

    .line 166
    const-string v1, "com.google"

    const-string v2, "com.android.calendar"

    const/4 v3, 0x0

    invoke-virtual/range {v0 .. v7}, Landroid/accounts/AccountManager;->addAccount(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;Landroid/os/Bundle;Landroid/app/Activity;Landroid/accounts/AccountManagerCallback;Landroid/os/Handler;)Landroid/accounts/AccountManagerFuture;

    return-void

    :catchall_51
    move-exception v0

    move-object p0, v0

    .line 156
    invoke-interface {p3}, Landroid/database/Cursor;->close()V

    throw p0

    :cond_57
    :goto_57
    if-eqz p3, :cond_5c

    invoke-interface {p3}, Landroid/database/Cursor;->close()V

    :cond_5c
    return-void
.end method
