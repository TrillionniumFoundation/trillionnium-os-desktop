.method public constructor whitelist <init>(Ljava/lang/String;Landroid/net/Uri;Landroid/content/Context;Ljava/lang/Class;)V
    .registers 6
    .param p1, "action"    # Ljava/lang/String;
    .param p2, "uri"    # Landroid/net/Uri;
    .param p3, "packageContext"    # Landroid/content/Context;
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "(",
            "Ljava/lang/String;",
            "Landroid/net/Uri;",
            "Landroid/content/Context;",
            "Ljava/lang/Class<",
            "*>;)V"
        }
    .end annotation

    #@0
    .line 8221
    .local p4, "cls":Ljava/lang/Class;, "Ljava/lang/Class<*>;"
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    #@3
    .line 8029
    const/4 v0, -0x2

    #@4
    iput v0, p0, Landroid/content/Intent;->mContentUserHint:I

    #@6
    .line 8222
    invoke-virtual {p0, p1}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    #@9
    .line 8223
    iput-object p2, p0, Landroid/content/Intent;->mData:Landroid/net/Uri;

    #@b
    .line 8224
    new-instance v0, Landroid/content/ComponentName;

    #@d
    invoke-direct {v0, p3, p4}, Landroid/content/ComponentName;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    #@10
    iput-object v0, p0, Landroid/content/Intent;->mComponent:Landroid/content/ComponentName;

    #@12
    .line 8225
    return-void
.end method
