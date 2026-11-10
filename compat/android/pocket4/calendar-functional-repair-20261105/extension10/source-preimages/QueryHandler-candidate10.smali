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

    iget-object v0, p0, Lcom/android/calendar/AllInOneActivity$QueryHandler;->this$0:Lcom/android/calendar/AllInOneActivity;
    invoke-static {v0}, Lcom/android/calendar/repair/CalendarActions;->onNoCalendars(Landroid/app/Activity;)V
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
