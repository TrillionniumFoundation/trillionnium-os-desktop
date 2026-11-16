.method public constructor whitelist <init>(Ljava/lang/String;Landroid/net/Uri;)V
    .registers 4
    .param p1, "action"    # Ljava/lang/String;
    .param p2, "uri"    # Landroid/net/Uri;

    #@0
    .line 8172
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    #@3
    .line 8029
    const/4 v0, -0x2

    #@4
    iput v0, p0, Landroid/content/Intent;->mContentUserHint:I

    #@6
    .line 8173
    invoke-virtual {p0, p1}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    #@9
    .line 8174
    iput-object p2, p0, Landroid/content/Intent;->mData:Landroid/net/Uri;

    #@b
    .line 8175
    return-void
.end method
