.class public Lcom/android/camera/CameraActivity;
.super Landroid/app/Activity;
.source "CameraActivity.java"


# direct methods
.method public constructor <init>()V
    .registers 1

    .line 25
    invoke-direct {p0}, Landroid/app/Activity;-><init>()V

    return-void
.end method


# virtual methods
.method public onCreate(Landroid/os/Bundle;)V
    .registers 3

    .line 28
    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V

    .line 29
    invoke-static {p0}, Lcom/android/gallery3d/util/IntentHelper;->getCameraIntent(Landroid/content/Context;)Landroid/content/Intent;

    move-result-object p1

    const/high16 v0, 0x200000

    .line 33
    invoke-virtual {p1, v0}, Landroid/content/Intent;->setFlags(I)Landroid/content/Intent;

    const/high16 v0, 0x10000000

    .line 34
    invoke-virtual {p1, v0}, Landroid/content/Intent;->setFlags(I)Landroid/content/Intent;

    .line 35
    invoke-virtual {p0, p1}, Landroid/app/Activity;->startActivity(Landroid/content/Intent;)V

    .line 36
    invoke-virtual {p0}, Landroid/app/Activity;->finish()V

    return-void
.end method
