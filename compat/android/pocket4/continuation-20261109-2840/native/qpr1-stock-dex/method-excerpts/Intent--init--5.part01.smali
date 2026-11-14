.method protected constructor greylist-max-o <init>(Landroid/os/Parcel;)V
    .registers 3
    .param p1, "in"    # Landroid/os/Parcel;

    #@0
    .line 12868
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    #@3
    .line 8029
    const/4 v0, -0x2

    #@4
    iput v0, p0, Landroid/content/Intent;->mContentUserHint:I

    #@6
    .line 12871
    const/4 v0, 0x2

    #@7
    iput v0, p0, Landroid/content/Intent;->mLocalFlags:I

    #@9
    .line 12872
    invoke-virtual {p0, p1}, Landroid/content/Intent;->readFromParcel(Landroid/os/Parcel;)V

    #@c
    .line 12873
    return-void
.end method
