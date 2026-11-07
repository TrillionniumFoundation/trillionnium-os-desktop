.class public Lcom/android/camera/DisableCameraReceiver;
.super Landroid/content/BroadcastReceiver;
.source "DisableCameraReceiver.java"


# static fields
.field private static final ACTIVITIES:[Ljava/lang/String;


# direct methods
.method static constructor <clinit>()V
    .registers 1

    .line 33
    const-string v0, "com.android.camera.CameraLauncher"

    filled-new-array {v0}, [Ljava/lang/String;

    move-result-object v0

    sput-object v0, Lcom/android/camera/DisableCameraReceiver;->ACTIVITIES:[Ljava/lang/String;

    return-void
.end method

.method public constructor <init>()V
    .registers 1

    .line 30
    invoke-direct {p0}, Landroid/content/BroadcastReceiver;-><init>()V

    return-void
.end method

.method private disableComponent(Landroid/content/Context;Ljava/lang/String;)V
    .registers 4

    .line 76
    new-instance p0, Landroid/content/ComponentName;

    invoke-direct {p0, p1, p2}, Landroid/content/ComponentName;-><init>(Landroid/content/Context;Ljava/lang/String;)V

    .line 77
    invoke-virtual {p1}, Landroid/content/Context;->getPackageManager()Landroid/content/pm/PackageManager;

    move-result-object p1

    const/4 p2, 0x2

    const/4 v0, 0x1

    .line 81
    invoke-virtual {p1, p0, p2, v0}, Landroid/content/pm/PackageManager;->setComponentEnabledSetting(Landroid/content/ComponentName;II)V

    return-void
.end method

.method private hasBackCamera()Z
    .registers 6

    .line 62
    invoke-static {}, Landroid/hardware/Camera;->getNumberOfCameras()I

    move-result p0

    .line 63
    new-instance v0, Landroid/hardware/Camera$CameraInfo;

    invoke-direct {v0}, Landroid/hardware/Camera$CameraInfo;-><init>()V

    const/4 v1, 0x0

    move v2, v1

    .line 64
    :goto_b
    const-string v3, "G:DisableCameraReceiver"

    if-ge v2, p0, :cond_2c

    .line 65
    invoke-static {v2, v0}, Landroid/hardware/Camera;->getCameraInfo(ILandroid/hardware/Camera$CameraInfo;)V

    .line 66
    iget v4, v0, Landroid/hardware/Camera$CameraInfo;->facing:I

    if-nez v4, :cond_29

    .line 67
    new-instance p0, Ljava/lang/StringBuilder;

    const-string v0, "back camera found: "

    invoke-direct {p0, v0}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V

    invoke-virtual {p0, v2}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    invoke-virtual {p0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p0

    invoke-static {v3, p0}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    const/4 p0, 0x1

    return p0

    :cond_29
    add-int/lit8 v2, v2, 0x1

    goto :goto_b

    .line 71
    :cond_2c
    const-string p0, "no back camera"

    invoke-static {v3, p0}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    return v1
.end method


# virtual methods
.method public onReceive(Landroid/content/Context;Landroid/content/Intent;)V
    .registers 5

    .line 41
    invoke-direct {p0}, Lcom/android/camera/DisableCameraReceiver;->hasBackCamera()Z

    move-result p2

    if-nez p2, :cond_1b

    .line 45
    const-string p2, "G:DisableCameraReceiver"

    const-string v0, "disable all camera activities"

    invoke-static {p2, v0}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    const/4 p2, 0x0

    .line 46
    :goto_e
    sget-object v0, Lcom/android/camera/DisableCameraReceiver;->ACTIVITIES:[Ljava/lang/String;

    array-length v1, v0

    if-ge p2, v1, :cond_1b

    .line 47
    aget-object v0, v0, p2

    invoke-direct {p0, p1, v0}, Lcom/android/camera/DisableCameraReceiver;->disableComponent(Landroid/content/Context;Ljava/lang/String;)V

    add-int/lit8 p2, p2, 0x1

    goto :goto_e

    .line 52
    :cond_1b
    const-string p2, "com.android.camera.DisableCameraReceiver"

    invoke-direct {p0, p1, p2}, Lcom/android/camera/DisableCameraReceiver;->disableComponent(Landroid/content/Context;Ljava/lang/String;)V

    return-void
.end method
