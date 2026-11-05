.class public final synthetic Lorg/droidloom/qa/editorcontract/EditorContractActivity$0;
.super Ljava/lang/Object;
.source "D8$$SyntheticClass"

# interfaces
.implements Landroid/widget/TextView$OnEditorActionListener;


# instance fields
.field public final synthetic f$0:Lorg/droidloom/qa/editorcontract/EditorContractActivity;


# direct methods
.method public synthetic constructor <init>(Lorg/droidloom/qa/editorcontract/EditorContractActivity;)V
    .registers 2

    .line 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    iput-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$0;->f$0:Lorg/droidloom/qa/editorcontract/EditorContractActivity;

    return-void
.end method


# virtual methods
.method public final onEditorAction(Landroid/widget/TextView;ILandroid/view/KeyEvent;)Z
    .registers 4

    .line 0
    iget-object p0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$0;->f$0:Lorg/droidloom/qa/editorcontract/EditorContractActivity;

    invoke-virtual {p0, p1, p2, p3}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->lambda$onCreate$0$org-droidloom-qa-editorcontract-EditorContractActivity(Landroid/widget/TextView;ILandroid/view/KeyEvent;)Z

    move-result p0

    return p0
.end method
