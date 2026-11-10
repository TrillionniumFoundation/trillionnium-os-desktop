.class Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText$1;
.super Landroid/view/inputmethod/InputConnectionWrapper;
.source "EditorContractActivity.java"


# annotations
.annotation system Ldalvik/annotation/EnclosingMethod;
    value = Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->onCreateInputConnection(Landroid/view/inputmethod/EditorInfo;)Landroid/view/inputmethod/InputConnection;
.end annotation

.annotation system Ldalvik/annotation/InnerClass;
    accessFlags = 0x0
    name = null
.end annotation


# instance fields
.field final synthetic this$1:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;


# direct methods
.method constructor <init>(Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;Landroid/view/inputmethod/InputConnection;Z)V
    .registers 4
    .annotation system Ldalvik/annotation/MethodParameters;
        accessFlags = {
            0x8010,
            0x0,
            0x0
        }
        names = {
            null,
            null,
            null
        }
    .end annotation

    .line 173
    iput-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText$1;->this$1:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    invoke-direct {p0, p2, p3}, Landroid/view/inputmethod/InputConnectionWrapper;-><init>(Landroid/view/inputmethod/InputConnection;Z)V

    return-void
.end method


# virtual methods
.method public performEditorAction(I)Z
    .registers 6

    .line 175
    iget-object v0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText$1;->this$1:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    iget-object v0, v0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->this$0:Lorg/droidloom/qa/editorcontract/EditorContractActivity;

    const-string v1, "input_connection_editor_action"

    const/4 v2, 0x0

    # invokes: Lorg/droidloom/qa/editorcontract/EditorContractActivity;->record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V
    invoke-static {v0, v1, v2, p1, v2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->access$000(Lorg/droidloom/qa/editorcontract/EditorContractActivity;Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V

    .line 176
    invoke-super {p0, p1}, Landroid/view/inputmethod/InputConnectionWrapper;->performEditorAction(I)Z

    move-result v0

    .line 177
    iget-object p0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText$1;->this$1:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    iget-object p0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->this$0:Lorg/droidloom/qa/editorcontract/EditorContractActivity;

    const-string v1, "result"

    # invokes: Lorg/droidloom/qa/editorcontract/EditorContractActivity;->detail(Ljava/lang/String;Z)Lorg/json/JSONObject;
    invoke-static {v1, v0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->access$200(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v1

    const-string v3, "input_connection_editor_action_returned"

    # invokes: Lorg/droidloom/qa/editorcontract/EditorContractActivity;->record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V
    invoke-static {p0, v3, v2, p1, v1}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->access$000(Lorg/droidloom/qa/editorcontract/EditorContractActivity;Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V

    return v0
.end method
