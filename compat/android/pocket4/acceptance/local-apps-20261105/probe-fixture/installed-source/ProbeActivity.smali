.class public final Llocal/pocket4/fixture/ProbeActivity;
.super Landroid/app/Activity;
.source "ProbeActivity.java"


# direct methods
.method public constructor <init>()V
    .registers 1

    .line 8
    invoke-direct {p0}, Landroid/app/Activity;-><init>()V

    return-void
.end method


# virtual methods
.method public onCreate(Landroid/os/Bundle;)V
    .registers 6

    .line 10
    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V

    .line 11
    new-instance p1, Landroid/widget/LinearLayout;

    invoke-direct {p1, p0}, Landroid/widget/LinearLayout;-><init>(Landroid/content/Context;)V

    const/4 v0, 0x1

    invoke-virtual {p1, v0}, Landroid/widget/LinearLayout;->setOrientation(I)V

    .line 12
    const/16 v0, 0x18

    invoke-virtual {p1, v0, v0, v0, v0}, Landroid/widget/LinearLayout;->setPadding(IIII)V

    .line 13
    new-instance v0, Landroid/widget/TextView;

    invoke-direct {v0, p0}, Landroid/widget/TextView;-><init>(Landroid/content/Context;)V

    const-string v1, "\u672c\u5730 Android \u64cd\u4f5c\u9a8c\u8bc1"

    invoke-virtual {v0, v1}, Landroid/widget/TextView;->setText(Ljava/lang/CharSequence;)V

    invoke-virtual {p1, v0}, Landroid/widget/LinearLayout;->addView(Landroid/view/View;)V

    .line 14
    new-instance v0, Landroid/widget/EditText;

    invoke-direct {v0, p0}, Landroid/widget/EditText;-><init>(Landroid/content/Context;)V

    const/high16 v1, 0x7f020000

    invoke-virtual {v0, v1}, Landroid/widget/EditText;->setId(I)V

    .line 15
    const-string v1, "\u4e2d\u6587\u4e0e Unicode \u8f93\u5165"

    invoke-virtual {v0, v1}, Landroid/widget/EditText;->setHint(Ljava/lang/CharSequence;)V

    invoke-virtual {p1, v0}, Landroid/widget/LinearLayout;->addView(Landroid/view/View;)V

    .line 16
    new-instance v1, Landroid/widget/EditText;

    invoke-direct {v1, p0}, Landroid/widget/EditText;-><init>(Landroid/content/Context;)V

    const v2, 0x7f020001

    invoke-virtual {v1, v2}, Landroid/widget/EditText;->setId(I)V

    .line 17
    const-string v2, "\u7b2c\u4e8c\u4e2a\u8f93\u5165\u6846\uff1a\u9a8c\u8bc1\u6b67\u4e49\u62d2\u7edd"

    invoke-virtual {v1, v2}, Landroid/widget/EditText;->setHint(Ljava/lang/CharSequence;)V

    invoke-virtual {p1, v1}, Landroid/widget/LinearLayout;->addView(Landroid/view/View;)V

    .line 18
    new-instance v1, Landroid/widget/TextView;

    invoke-direct {v1, p0}, Landroid/widget/TextView;-><init>(Landroid/content/Context;)V

    const v2, 0x7f020003

    invoke-virtual {v1, v2}, Landroid/widget/TextView;->setId(I)V

    const-string v2, "\u5c1a\u672a\u70b9\u51fb"

    invoke-virtual {v1, v2}, Landroid/widget/TextView;->setText(Ljava/lang/CharSequence;)V

    .line 19
    new-instance v2, Landroid/widget/Button;

    invoke-direct {v2, p0}, Landroid/widget/Button;-><init>(Landroid/content/Context;)V

    const v3, 0x7f020002

    invoke-virtual {v2, v3}, Landroid/widget/Button;->setId(I)V

    const-string v3, "\u786e\u8ba4\u6d4b\u8bd5"

    invoke-virtual {v2, v3}, Landroid/widget/Button;->setText(Ljava/lang/CharSequence;)V

    .line 20
    new-instance v3, Llocal/pocket4/fixture/ProbeActivity$1;

    invoke-direct {v3, p0, v1, v0}, Llocal/pocket4/fixture/ProbeActivity$1;-><init>(Llocal/pocket4/fixture/ProbeActivity;Landroid/widget/TextView;Landroid/widget/EditText;)V

    invoke-virtual {v2, v3}, Landroid/widget/Button;->setOnClickListener(Landroid/view/View$OnClickListener;)V

    .line 23
    invoke-virtual {p1, v2}, Landroid/widget/LinearLayout;->addView(Landroid/view/View;)V

    invoke-virtual {p1, v1}, Landroid/widget/LinearLayout;->addView(Landroid/view/View;)V

    invoke-virtual {p0, p1}, Llocal/pocket4/fixture/ProbeActivity;->setContentView(Landroid/view/View;)V

    .line 24
    return-void
.end method
