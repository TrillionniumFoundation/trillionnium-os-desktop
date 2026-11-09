.method public constructor whitelist <init>(Ljava/lang/String;)V
    .registers 3
    .param p1, "action"    # Ljava/lang/String;

    #@0
    .line 8152
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    #@3
    .line 8029
    const/4 v0, -0x2

    #@4
    iput v0, p0, Landroid/content/Intent;->mContentUserHint:I

    #@6
    .line 8153
    invoke-virtual {p0, p1}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;

    #@9
    .line 8154
    return-void
.end method
