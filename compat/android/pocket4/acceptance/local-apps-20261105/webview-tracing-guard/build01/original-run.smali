.method public run()V
    .registers 3

    .line 216
    new-instance v0, Landroid/app/AlertDialog$Builder;

    iget-object v1, p0, Lorg/chromium/webview_shell/WebViewBrowserActivity$TracingLogger$1;->this$0:Lorg/chromium/webview_shell/WebViewBrowserActivity$TracingLogger;

    invoke-static {v1}, Lorg/chromium/webview_shell/WebViewBrowserActivity$TracingLogger;->-$$Nest$fgetmActivity(Lorg/chromium/webview_shell/WebViewBrowserActivity$TracingLogger;)Landroid/app/Activity;

    move-result-object v1

    invoke-direct {v0, v1}, Landroid/app/AlertDialog$Builder;-><init>(Landroid/content/Context;)V

    const-string v1, "Tracing API"

    .line 217
    invoke-virtual {v0, v1}, Landroid/app/AlertDialog$Builder;->setTitle(Ljava/lang/CharSequence;)Landroid/app/AlertDialog$Builder;

    move-result-object v0

    iget-object p0, p0, Lorg/chromium/webview_shell/WebViewBrowserActivity$TracingLogger$1;->val$info:Ljava/lang/StringBuilder;

    .line 218
    invoke-virtual {v0, p0}, Landroid/app/AlertDialog$Builder;->setMessage(Ljava/lang/CharSequence;)Landroid/app/AlertDialog$Builder;

    move-result-object p0

    const-string v0, " OK "

    const/4 v1, 0x0

    .line 219
    invoke-virtual {p0, v0, v1}, Landroid/app/AlertDialog$Builder;->setNeutralButton(Ljava/lang/CharSequence;Landroid/content/DialogInterface$OnClickListener;)Landroid/app/AlertDialog$Builder;

    move-result-object p0

    .line 220
    invoke-virtual {p0}, Landroid/app/AlertDialog$Builder;->create()Landroid/app/AlertDialog;

    move-result-object p0

    .line 221
    invoke-virtual {p0}, Landroid/app/AlertDialog;->show()V

    return-void
.end method
