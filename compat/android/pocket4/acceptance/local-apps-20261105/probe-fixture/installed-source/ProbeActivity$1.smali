.class Llocal/pocket4/fixture/ProbeActivity$1;
.super Ljava/lang/Object;
.source "ProbeActivity.java"

# interfaces
.implements Landroid/view/View$OnClickListener;


# annotations
.annotation system Ldalvik/annotation/EnclosingMethod;
    value = Llocal/pocket4/fixture/ProbeActivity;->onCreate(Landroid/os/Bundle;)V
.end annotation

.annotation system Ldalvik/annotation/InnerClass;
    accessFlags = 0x0
    name = null
.end annotation


# instance fields
.field final synthetic this$0:Llocal/pocket4/fixture/ProbeActivity;

.field final synthetic val$editor:Landroid/widget/EditText;

.field final synthetic val$result:Landroid/widget/TextView;


# direct methods
.method constructor <init>(Llocal/pocket4/fixture/ProbeActivity;Landroid/widget/TextView;Landroid/widget/EditText;)V
    .registers 4
    .annotation system Ldalvik/annotation/MethodParameters;
        accessFlags = {
            0x8010,
            0x1010,
            0x1010
        }
        names = {
            null,
            null,
            null
        }
    .end annotation

    .annotation system Ldalvik/annotation/Signature;
        value = {
            "()V"
        }
    .end annotation

    .line 20
    iput-object p1, p0, Llocal/pocket4/fixture/ProbeActivity$1;->this$0:Llocal/pocket4/fixture/ProbeActivity;

    iput-object p2, p0, Llocal/pocket4/fixture/ProbeActivity$1;->val$result:Landroid/widget/TextView;

    iput-object p3, p0, Llocal/pocket4/fixture/ProbeActivity$1;->val$editor:Landroid/widget/EditText;

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method


# virtual methods
.method public onClick(Landroid/view/View;)V
    .registers 4

    .line 21
    iget-object p1, p0, Llocal/pocket4/fixture/ProbeActivity$1;->val$result:Landroid/widget/TextView;

    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    const-string v1, "\u5df2\u70b9\u51fb\uff1a"

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v0

    iget-object v1, p0, Llocal/pocket4/fixture/ProbeActivity$1;->val$editor:Landroid/widget/EditText;

    invoke-virtual {v1}, Landroid/widget/EditText;->getText()Landroid/text/Editable;

    move-result-object v1

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p1, v0}, Landroid/widget/TextView;->setText(Ljava/lang/CharSequence;)V

    return-void
.end method
