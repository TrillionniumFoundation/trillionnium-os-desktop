.class final Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;
.super Landroid/widget/EditText;
.source "EditorContractActivity.java"


# annotations
.annotation system Ldalvik/annotation/EnclosingClass;
    value = Lorg/droidloom/qa/editorcontract/EditorContractActivity;
.end annotation

.annotation system Ldalvik/annotation/InnerClass;
    accessFlags = 0x12
    name = "ContractEditText"
.end annotation


# instance fields
.field final synthetic this$0:Lorg/droidloom/qa/editorcontract/EditorContractActivity;


# direct methods
.method constructor <init>(Lorg/droidloom/qa/editorcontract/EditorContractActivity;)V
    .registers 2
    .annotation system Ldalvik/annotation/MethodParameters;
        accessFlags = {
            0x1010
        }
        names = {
            null
        }
    .end annotation

    .line 152
    iput-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->this$0:Lorg/droidloom/qa/editorcontract/EditorContractActivity;

    invoke-direct {p0, p1}, Landroid/widget/EditText;-><init>(Landroid/content/Context;)V

    return-void
.end method


# virtual methods
.method public dispatchKeyEvent(Landroid/view/KeyEvent;)Z
    .registers 6

    .line 160
    iget-object v0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->this$0:Lorg/droidloom/qa/editorcontract/EditorContractActivity;

    const/4 v1, -0x1

    const/4 v2, 0x0

    const-string v3, "post_ime_key"

    # invokes: Lorg/droidloom/qa/editorcontract/EditorContractActivity;->record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V
    invoke-static {v0, v3, p1, v1, v2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->access$000(Lorg/droidloom/qa/editorcontract/EditorContractActivity;Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V

    .line 161
    invoke-super {p0, p1}, Landroid/widget/EditText;->dispatchKeyEvent(Landroid/view/KeyEvent;)Z

    move-result p0

    return p0
.end method

.method public onCreateInputConnection(Landroid/view/inputmethod/EditorInfo;)Landroid/view/inputmethod/InputConnection;
    .registers 9

    .line 165
    invoke-super {p0, p1}, Landroid/widget/EditText;->onCreateInputConnection(Landroid/view/inputmethod/EditorInfo;)Landroid/view/inputmethod/InputConnection;

    move-result-object v0

    .line 166
    iget-object v1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->this$0:Lorg/droidloom/qa/editorcontract/EditorContractActivity;

    # operator++ for: Lorg/droidloom/qa/editorcontract/EditorContractActivity;->connections:I
    invoke-static {v1}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->access$108(Lorg/droidloom/qa/editorcontract/EditorContractActivity;)I

    .line 168
    :try_start_9
    iget-object v1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->this$0:Lorg/droidloom/qa/editorcontract/EditorContractActivity;

    const-string v2, "input_connection_created"

    iget v3, p1, Landroid/view/inputmethod/EditorInfo;->imeOptions:I

    and-int/lit16 v3, v3, 0xff

    new-instance v4, Lorg/json/JSONObject;

    invoke-direct {v4}, Lorg/json/JSONObject;-><init>()V

    const-string v5, "input_type"

    iget v6, p1, Landroid/view/inputmethod/EditorInfo;->inputType:I

    .line 169
    invoke-virtual {v4, v5, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v4

    const-string v5, "ime_options"

    iget v6, p1, Landroid/view/inputmethod/EditorInfo;->imeOptions:I

    invoke-virtual {v4, v5, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v4

    const-string v5, "field_id"

    iget p1, p1, Landroid/view/inputmethod/EditorInfo;->fieldId:I

    .line 170
    invoke-virtual {v4, v5, p1}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string v4, "target_present"

    const/4 v5, 0x0

    if-eqz v0, :cond_35

    const/4 v6, 0x1

    goto :goto_36

    :cond_35
    move v6, v5

    :goto_36
    invoke-virtual {p1, v4, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p1

    const/4 v4, 0x0

    .line 168
    # invokes: Lorg/droidloom/qa/editorcontract/EditorContractActivity;->record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V
    invoke-static {v1, v2, v4, v3, p1}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->access$000(Lorg/droidloom/qa/editorcontract/EditorContractActivity;Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V
    :try_end_3e
    .catch Ljava/lang/Exception; {:try_start_9 .. :try_end_3e} :catch_47

    if-nez v0, :cond_41

    return-object v4

    .line 173
    :cond_41
    new-instance p1, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText$1;

    invoke-direct {p1, p0, v0, v5}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText$1;-><init>(Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;Landroid/view/inputmethod/InputConnection;Z)V

    return-object p1

    :catch_47
    move-exception p0

    .line 171
    new-instance p1, Ljava/lang/IllegalStateException;

    invoke-direct {p1, p0}, Ljava/lang/IllegalStateException;-><init>(Ljava/lang/Throwable;)V

    throw p1
.end method

.method public onKeyPreIme(ILandroid/view/KeyEvent;)Z
    .registers 7

    .line 155
    iget-object v0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->this$0:Lorg/droidloom/qa/editorcontract/EditorContractActivity;

    const/4 v1, -0x1

    const/4 v2, 0x0

    const-string v3, "pre_ime_key"

    # invokes: Lorg/droidloom/qa/editorcontract/EditorContractActivity;->record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V
    invoke-static {v0, v3, p2, v1, v2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->access$000(Lorg/droidloom/qa/editorcontract/EditorContractActivity;Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V

    .line 156
    invoke-super {p0, p1, p2}, Landroid/widget/EditText;->onKeyPreIme(ILandroid/view/KeyEvent;)Z

    move-result p0

    return p0
.end method
