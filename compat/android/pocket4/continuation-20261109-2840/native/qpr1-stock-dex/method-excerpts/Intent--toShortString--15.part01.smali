.method public final greylist-max-o toShortString(ZZZZ)Ljava/lang/String;
    .registers 13
    .param p1, "secure"    # Z
    .param p2, "comp"    # Z
    .param p3, "extras"    # Z
    .param p4, "clip"    # Z

    #@0
    .line 12045
    new-instance v0, Ljava/lang/StringBuilder;

    #@2
    const/16 v1, 0x80

    #@4
    invoke-direct {v0, v1}, Ljava/lang/StringBuilder;-><init>(I)V

    #@7
    move-object v3, v0

    #@8
    .line 12046
    .local v3, "b":Ljava/lang/StringBuilder;
    move-object v2, p0

    #@9
    move v4, p1

    #@a
    move v5, p2

    #@b
    move v6, p3

    #@c
    move v7, p4

    #@d
    .end local p1    # "secure":Z
    .end local p2    # "comp":Z
    .end local p3    # "extras":Z
    .end local p4    # "clip":Z
    .local v4, "secure":Z
    .local v5, "comp":Z
    .local v6, "extras":Z
    .local v7, "clip":Z
    invoke-virtual/range {v2 .. v7}, Landroid/content/Intent;->toShortString(Ljava/lang/StringBuilder;ZZZZ)V

    #@10
    .line 12047
    invoke-virtual {v3}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    #@13
    move-result-object p1

    #@14
    return-object p1
.end method
