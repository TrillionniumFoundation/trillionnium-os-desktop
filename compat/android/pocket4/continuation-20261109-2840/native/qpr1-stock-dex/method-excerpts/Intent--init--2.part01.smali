.method public constructor whitelist <init>(Landroid/content/Context;Ljava/lang/Class;)V
    .registers 4
    .param p1, "packageContext"    # Landroid/content/Context;
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "(",
            "Landroid/content/Context;",
            "Ljava/lang/Class<",
            "*>;)V"
        }
    .end annotation

    #@0
    .line 8193
    .local p2, "cls":Ljava/lang/Class;, "Ljava/lang/Class<*>;"
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    #@3
    .line 8029
    const/4 v0, -0x2

    #@4
    iput v0, p0, Landroid/content/Intent;->mContentUserHint:I

    #@6
    .line 8194
    new-instance v0, Landroid/content/ComponentName;

    #@8
    invoke-direct {v0, p1, p2}, Landroid/content/ComponentName;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    #@b
    iput-object v0, p0, Landroid/content/Intent;->mComponent:Landroid/content/ComponentName;

    #@d
    .line 8195
    return-void
.end method
