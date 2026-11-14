.method private constructor greylist-max-o <init>(Landroid/os/Parcel;)V
    .registers 4
    .param p1, "source"    # Landroid/os/Parcel;

    #@0
    .line 116
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    #@3
    .line 117
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@6
    move-result v0

    #@7
    iput v0, p0, Landroid/app/WaitResult;->result:I

    #@9
    .line 118
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@c
    move-result v0

    #@d
    if-eqz v0, :cond_11

    #@f
    const/4 v0, 0x1

    #@10
    goto :goto_12

    #@11
    :cond_11
    const/4 v0, 0x0

    #@12
    :goto_12
    iput-boolean v0, p0, Landroid/app/WaitResult;->timeout:Z

    #@14
    .line 119
    invoke-static {p1}, Landroid/content/ComponentName;->readFromParcel(Landroid/os/Parcel;)Landroid/content/ComponentName;

    #@17
    move-result-object v0

    #@18
    iput-object v0, p0, Landroid/app/WaitResult;->who:Landroid/content/ComponentName;

    #@1a
    .line 120
    invoke-virtual {p1}, Landroid/os/Parcel;->readLong()J

    #@1d
    move-result-wide v0

    #@1e
    iput-wide v0, p0, Landroid/app/WaitResult;->totalTime:J

    #@20
    .line 121
    invoke-virtual {p1}, Landroid/os/Parcel;->readInt()I

    #@23
    move-result v0

    #@24
    iput v0, p0, Landroid/app/WaitResult;->launchState:I

    #@26
    .line 122
    return-void
.end method
