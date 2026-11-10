.class public abstract Lcom/android/gallery3d/util/IntentHelper;
.super Ljava/lang/Object;
.source "IntentHelper.java"


# direct methods
.method public static getCameraIntent(Landroid/content/Context;)Landroid/content/Intent;
    .registers 3

    .line 24
    new-instance p0, Landroid/content/Intent;

    const-string v0, "android.intent.action.MAIN"

    invoke-direct {p0, v0}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    const-string v0, "com.android.camera2"

    const-string v1, "com.android.camera.CameraLauncher"

    .line 25
    invoke-virtual {p0, v0, v1}, Landroid/content/Intent;->setClassName(Ljava/lang/String;Ljava/lang/String;)Landroid/content/Intent;

    move-result-object p0

    return-object p0
.end method

.method public static getGalleryIntent(Landroid/content/Context;)Landroid/content/Intent;
    .registers 3

    .line 29
    new-instance p0, Landroid/content/Intent;

    const-string v0, "android.intent.action.MAIN"

    invoke-direct {p0, v0}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    const-string v0, "com.android.gallery3d"

    const-string v1, "com.android.gallery3d.app.GalleryActivity"

    .line 30
    invoke-virtual {p0, v0, v1}, Landroid/content/Intent;->setClassName(Ljava/lang/String;Ljava/lang/String;)Landroid/content/Intent;

    move-result-object p0

    return-object p0
.end method
