.class public Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;
.super Landroid/app/Activity;
.source "go/retraceme 9af01222c9f0ce13808ff8a71a2aad063a10a8b4d085240df3537e8ca2c7d173"

# interfaces
.implements Landroid/view/View$OnClickListener;
.implements Landroid/widget/TextView$OnEditorActionListener;
.implements Landroid/text/TextWatcher;


# static fields
.field public static final synthetic $r8$clinit:I


# instance fields
.field public changePinExecutor:Lcom/android/dialer/common/concurrent/DialerExecutor;

.field public errorText:Landroid/widget/TextView;

.field public firstPin:Ljava/lang/String;

.field public final handler:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$ChangePinHandler;

.field public headerText:Landroid/widget/TextView;

.field public hintText:Landroid/widget/TextView;

.field public nextButton:Landroid/widget/Button;

.field public oldPin:Ljava/lang/String;

.field public phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

.field public pinChanger:Lcom/android/voicemail/impl/PinChangerImpl;

.field public pinEntry:Landroid/widget/EditText;

.field public pinMaxLength:I

.field public pinMinLength:I

.field public progressDialog:Landroid/app/ProgressDialog;

.field public uiState:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;


# direct methods
.method public constructor <init>()V
    .registers 3

    invoke-direct {p0}, Landroid/app/Activity;-><init>()V

    sget-object v0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;->Initial:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->uiState:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;

    new-instance v0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$ChangePinHandler;

    new-instance v1, Ljava/lang/ref/WeakReference;

    invoke-direct {v1, p0}, Ljava/lang/ref/WeakReference;-><init>(Ljava/lang/Object;)V

    invoke-direct {v0}, Landroid/os/Handler;-><init>()V

    iput-object v1, v0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$ChangePinHandler;->activityWeakReference:Ljava/lang/ref/WeakReference;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->handler:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$ChangePinHandler;

    return-void
.end method

.method public static access$1100(Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;I)Ljava/lang/CharSequence;
    .registers 3

    packed-switch p1, :pswitch_data_44

    const-string p0, "Unexpected ChangePinResult "

    invoke-static {p1, p0}, Landroid/support/design/widget/BottomSheetBehavior$$ExternalSyntheticOutline0;->m(ILjava/lang/String;)Ljava/lang/String;

    move-result-object p0

    const/4 p1, 0x0

    new-array p1, p1, [Ljava/lang/Object;

    const-string v0, "VmChangePinActivity"

    invoke-static {v0, p0, p1}, Lcom/android/dialer/common/LogUtil;->e(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    const/4 p0, 0x0

    return-object p0

    :pswitch_13
    const p1, 0x7f110394

    invoke-virtual {p0, p1}, Landroid/app/Activity;->getString(I)Ljava/lang/String;

    move-result-object p0

    return-object p0

    :pswitch_1b
    const p1, 0x7f110392

    invoke-virtual {p0, p1}, Landroid/app/Activity;->getString(I)Ljava/lang/String;

    move-result-object p0

    return-object p0

    :pswitch_23
    const p1, 0x7f110393

    invoke-virtual {p0, p1}, Landroid/app/Activity;->getString(I)Ljava/lang/String;

    move-result-object p0

    return-object p0

    :pswitch_2b
    const p1, 0x7f110397

    invoke-virtual {p0, p1}, Landroid/app/Activity;->getString(I)Ljava/lang/String;

    move-result-object p0

    return-object p0

    :pswitch_33
    const p1, 0x7f110395

    invoke-virtual {p0, p1}, Landroid/app/Activity;->getString(I)Ljava/lang/String;

    move-result-object p0

    return-object p0

    :pswitch_3b
    const p1, 0x7f110396

    invoke-virtual {p0, p1}, Landroid/app/Activity;->getString(I)Ljava/lang/String;

    move-result-object p0

    return-object p0

    nop

    :pswitch_data_44
    .packed-switch 0x1
        :pswitch_3b
        :pswitch_33
        :pswitch_2b
        :pswitch_23
        :pswitch_1b
        :pswitch_13
    .end packed-switch
.end method


# virtual methods
.method public final afterTextChanged(Landroid/text/Editable;)V
    .registers 2

    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->uiState:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;

    invoke-virtual {p1, p0}, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;->onInputChanged(Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;)V

    return-void
.end method

.method public final beforeTextChanged(Ljava/lang/CharSequence;III)V
    .registers 5

    return-void
.end method

.method public final onClick(Landroid/view/View;)V
    .registers 4

    invoke-virtual {p1}, Landroid/view/View;->getId()I

    move-result v0

    const v1, 0x7f0901cc

    if-ne v0, v1, :cond_18

    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinEntry:Landroid/widget/EditText;

    invoke-virtual {p1}, Landroid/widget/EditText;->length()I

    move-result p1

    if-nez p1, :cond_12

    goto :goto_24

    :cond_12
    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->uiState:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;

    invoke-virtual {p1, p0}, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;->handleNext(Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;)V

    return-void

    :cond_18
    invoke-virtual {p1}, Landroid/view/View;->getId()I

    move-result p1

    const v0, 0x7f090085

    if-ne p1, v0, :cond_24

    invoke-virtual {p0}, Landroid/app/Activity;->finish()V

    :cond_24
    :goto_24
    return-void
.end method

.method public final onCreate(Landroid/os/Bundle;)V
    .registers 7

    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V

    invoke-virtual {p0}, Landroid/app/Activity;->getIntent()Landroid/content/Intent;

    move-result-object p1

    const-string v0, "phone_account_handle"

    invoke-virtual {p1, v0}, Landroid/content/Intent;->getParcelableExtra(Ljava/lang/String;)Landroid/os/Parcelable;

    move-result-object p1

    check-cast p1, Landroid/telecom/PhoneAccountHandle;

    iput-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-static {p0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->get$12(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;

    move-result-object p1

    invoke-virtual {p1}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->getVoicemailClient()Lcom/android/voicemail/VoicemailClient;

    move-result-object p1

    invoke-virtual {p0}, Landroid/app/Activity;->getApplicationContext()Landroid/content/Context;

    move-result-object v0

    iget-object v1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {p1, v0, v1}, Lcom/android/voicemail/VoicemailClient;->createPinChanger(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Lcom/android/voicemail/impl/PinChangerImpl;

    move-result-object p1

    iput-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinChanger:Lcom/android/voicemail/impl/PinChangerImpl;

    const p1, 0x7f0c00dc

    invoke-virtual {p0, p1}, Landroid/app/Activity;->setContentView(I)V

    const p1, 0x7f1100e6

    invoke-virtual {p0, p1}, Landroid/app/Activity;->setTitle(I)V

    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinChanger:Lcom/android/voicemail/impl/PinChangerImpl;

    new-instance v0, Lcom/android/voicemail/impl/VisualVoicemailPreferences;

    iget-object v1, p1, Lcom/android/voicemail/impl/PinChangerImpl;->context:Landroid/content/Context;

    iget-object p1, p1, Lcom/android/voicemail/impl/PinChangerImpl;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-direct {v0, v1, p1}, Lcom/android/voicemail/impl/VisualVoicemailPreferences;-><init>(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)V

    const-string p1, "pw_len"

    const-string v1, ""

    invoke-virtual {v0, v1, p1}, Lcom/android/dialer/common/PerAccountSharedPreferences;->getValue(Ljava/lang/Object;Ljava/lang/String;)Ljava/lang/Object;

    move-result-object p1

    check-cast p1, Ljava/lang/String;

    const-string v0, "-"

    invoke-virtual {p1, v0}, Ljava/lang/String;->split(Ljava/lang/String;)[Ljava/lang/String;

    move-result-object p1

    array-length v0, p1

    const/4 v1, 0x2

    const/4 v2, 0x1

    const/4 v3, 0x0

    if-ne v0, v1, :cond_5f

    :try_start_52
    aget-object v0, p1, v3

    invoke-static {v0}, Ljava/lang/Integer;->parseInt(Ljava/lang/String;)I

    move-result v0
    :try_end_58
    .catch Ljava/lang/NumberFormatException; {:try_start_52 .. :try_end_58} :catch_5f

    :try_start_58
    aget-object p1, p1, v2

    invoke-static {p1}, Ljava/lang/Integer;->parseInt(Ljava/lang/String;)I

    move-result p1
    :try_end_5e
    .catch Ljava/lang/NumberFormatException; {:try_start_58 .. :try_end_5e} :catch_60

    goto :goto_61

    :catch_5f
    :cond_5f
    move v0, v3

    :catch_60
    move p1, v3

    :goto_61
    iput v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinMinLength:I

    iput p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinMaxLength:I

    const p1, 0x1020002

    invoke-virtual {p0, p1}, Landroid/app/Activity;->findViewById(I)Landroid/view/View;

    move-result-object p1

    const v0, 0x7f090085

    invoke-virtual {p1, v0}, Landroid/view/View;->findViewById(I)Landroid/view/View;

    move-result-object v0

    check-cast v0, Landroid/widget/Button;

    invoke-virtual {v0, p0}, Landroid/widget/Button;->setOnClickListener(Landroid/view/View$OnClickListener;)V

    const v0, 0x7f0901cc

    invoke-virtual {p1, v0}, Landroid/view/View;->findViewById(I)Landroid/view/View;

    move-result-object v0

    check-cast v0, Landroid/widget/Button;

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->nextButton:Landroid/widget/Button;

    invoke-virtual {v0, p0}, Landroid/widget/Button;->setOnClickListener(Landroid/view/View$OnClickListener;)V

    const v0, 0x7f0901eb

    invoke-virtual {p1, v0}, Landroid/view/View;->findViewById(I)Landroid/view/View;

    move-result-object v0

    check-cast v0, Landroid/widget/EditText;

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinEntry:Landroid/widget/EditText;

    invoke-virtual {v0, p0}, Landroid/widget/EditText;->setOnEditorActionListener(Landroid/widget/TextView$OnEditorActionListener;)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinEntry:Landroid/widget/EditText;

    invoke-virtual {v0, p0}, Landroid/widget/EditText;->addTextChangedListener(Landroid/text/TextWatcher;)V

    iget v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinMaxLength:I

    if-eqz v0, :cond_ad

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinEntry:Landroid/widget/EditText;

    new-array v1, v2, [Landroid/text/InputFilter;

    new-instance v2, Landroid/text/InputFilter$LengthFilter;

    iget v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinMaxLength:I

    invoke-direct {v2, v4}, Landroid/text/InputFilter$LengthFilter;-><init>(I)V

    aput-object v2, v1, v3

    invoke-virtual {v0, v1}, Landroid/widget/EditText;->setFilters([Landroid/text/InputFilter;)V

    :cond_ad
    const v0, 0x7f090141

    invoke-virtual {p1, v0}, Landroid/view/View;->findViewById(I)Landroid/view/View;

    move-result-object v0

    check-cast v0, Landroid/widget/TextView;

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->headerText:Landroid/widget/TextView;

    const v0, 0x7f090143

    invoke-virtual {p1, v0}, Landroid/view/View;->findViewById(I)Landroid/view/View;

    move-result-object v0

    check-cast v0, Landroid/widget/TextView;

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->hintText:Landroid/widget/TextView;

    const v0, 0x7f09011f

    invoke-virtual {p1, v0}, Landroid/view/View;->findViewById(I)Landroid/view/View;

    move-result-object p1

    check-cast p1, Landroid/widget/TextView;

    iput-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->errorText:Landroid/widget/TextView;

    invoke-static {p0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$ContactsComponentImpl;->get$1(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$ContactsComponentImpl;

    move-result-object p1

    invoke-virtual {p1}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$ContactsComponentImpl;->dialerExecutorFactory()Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory;

    move-result-object p1

    invoke-virtual {p0}, Landroid/app/Activity;->getFragmentManager()Landroid/app/FragmentManager;

    move-result-object v0

    new-instance v1, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$ChangePinWorker;

    invoke-direct {v1}, Ljava/lang/Object;-><init>()V

    const-string v2, "changePin"

    invoke-virtual {p1, v0, v2, v1}, Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory;->createUiTaskBuilder(Landroid/app/FragmentManager;Ljava/lang/String;Lcom/android/dialer/common/concurrent/DialerExecutor$Worker;)Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory$UiTaskBuilder;

    move-result-object p1

    new-instance v0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$$ExternalSyntheticLambda0;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object p0, v0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$$ExternalSyntheticLambda0;->f$0:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-virtual {p1, v0}, Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory$BaseTaskBuilder;->onSuccess(Lcom/android/dialer/common/concurrent/DialerExecutor$SuccessListener;)V

    new-instance v0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$$ExternalSyntheticLambda0;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object p0, v0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$$ExternalSyntheticLambda0;->f$0:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-virtual {p1, v0}, Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory$BaseTaskBuilder;->onFailure(Lcom/android/dialer/common/concurrent/DialerExecutor$FailureListener;)V

    invoke-virtual {p1}, Lcom/android/dialer/common/concurrent/DefaultDialerExecutorFactory$UiTaskBuilder;->build()Lcom/android/dialer/common/concurrent/DialerExecutor;

    move-result-object p1

    iput-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->changePinExecutor:Lcom/android/dialer/common/concurrent/DialerExecutor;

    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-static {p0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->get$12(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;

    move-result-object v0

    invoke-virtual {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->getVoicemailClient()Lcom/android/voicemail/VoicemailClient;

    move-result-object v0

    invoke-interface {v0, p0, p1}, Lcom/android/voicemail/VoicemailClient;->createPinChanger(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Lcom/android/voicemail/impl/PinChangerImpl;

    move-result-object p1

    invoke-virtual {p1}, Lcom/android/voicemail/impl/PinChangerImpl;->getScrambledPin()Ljava/lang/String;

    move-result-object p1

    if-eqz p1, :cond_127

    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinChanger:Lcom/android/voicemail/impl/PinChangerImpl;

    invoke-virtual {p1}, Lcom/android/voicemail/impl/PinChangerImpl;->getScrambledPin()Ljava/lang/String;

    move-result-object p1

    iput-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->oldPin:Ljava/lang/String;

    sget-object p1, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;->VerifyOldPin:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State$2;

    invoke-virtual {p0, p1}, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->updateState(Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;)V

    goto :goto_12c

    :cond_127
    sget-object p1, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;->EnterOldPin:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State$1;

    invoke-virtual {p0, p1}, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->updateState(Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;)V

    :goto_12c
    return-void
.end method

.method public final onEditorAction(Landroid/widget/TextView;ILandroid/view/KeyEvent;)Z
    .registers 4

    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->nextButton:Landroid/widget/Button;

    invoke-virtual {p1}, Landroid/widget/Button;->isEnabled()Z

    move-result p1

    const/4 p3, 0x1

    if-nez p1, :cond_a

    goto :goto_1d

    :cond_a
    if-eqz p2, :cond_15

    const/4 p1, 0x6

    if-eq p2, p1, :cond_15

    const/4 p1, 0x5

    if-ne p2, p1, :cond_13

    goto :goto_15

    :cond_13
    const/4 p0, 0x0

    return p0

    :cond_15
    :goto_15
    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinEntry:Landroid/widget/EditText;

    invoke-virtual {p1}, Landroid/widget/EditText;->length()I

    move-result p1

    if-nez p1, :cond_1e

    :goto_1d
    return p3

    :cond_1e
    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->uiState:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;

    invoke-virtual {p1, p0}, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;->handleNext(Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;)V

    return p3
.end method

.method public final onOptionsItemSelected(Landroid/view/MenuItem;)Z
    .registers 4

    invoke-interface {p1}, Landroid/view/MenuItem;->getItemId()I

    move-result v0

    const v1, 0x102002c

    if-ne v0, v1, :cond_e

    invoke-virtual {p0}, Landroid/app/Activity;->onBackPressed()V

    const/4 p0, 0x1

    return p0

    :cond_e
    invoke-super {p0, p1}, Landroid/app/Activity;->onOptionsItemSelected(Landroid/view/MenuItem;)Z

    move-result p0

    return p0
.end method

.method public final onResume()V
    .registers 2

    invoke-super {p0}, Landroid/app/Activity;->onResume()V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->uiState:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;

    invoke-virtual {p0, v0}, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->updateState(Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;)V

    return-void
.end method

.method public final onTextChanged(Ljava/lang/CharSequence;III)V
    .registers 5

    return-void
.end method

.method public final processPinChange(Ljava/lang/String;Ljava/lang/String;)V
    .registers 5

    new-instance v0, Landroid/app/ProgressDialog;

    invoke-direct {v0, p0}, Landroid/app/ProgressDialog;-><init>(Landroid/content/Context;)V

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->progressDialog:Landroid/app/ProgressDialog;

    const/4 v1, 0x0

    invoke-virtual {v0, v1}, Landroid/app/ProgressDialog;->setCancelable(Z)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->progressDialog:Landroid/app/ProgressDialog;

    const v1, 0x7f11039a

    invoke-virtual {p0, v1}, Landroid/app/Activity;->getString(I)Ljava/lang/String;

    move-result-object v1

    invoke-virtual {v0, v1}, Landroid/app/ProgressDialog;->setMessage(Ljava/lang/CharSequence;)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->progressDialog:Landroid/app/ProgressDialog;

    invoke-virtual {v0}, Landroid/app/ProgressDialog;->show()V

    new-instance v0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$ChangePinParams;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iget-object v1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinChanger:Lcom/android/voicemail/impl/PinChangerImpl;

    iput-object v1, v0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$ChangePinParams;->pinChanger:Lcom/android/voicemail/impl/PinChangerImpl;

    iput-object p1, v0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$ChangePinParams;->oldPin:Ljava/lang/String;

    iput-object p2, v0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$ChangePinParams;->newPin:Ljava/lang/String;

    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->changePinExecutor:Lcom/android/dialer/common/concurrent/DialerExecutor;

    invoke-interface {p0, v0}, Lcom/android/dialer/common/concurrent/DialerExecutor;->executeSerial(Ljava/lang/Object;)V

    return-void
.end method

.method public final sendResult(I)V
    .registers 7

    const-string v0, "Change PIN result: "

    invoke-static {p1, v0}, Landroid/support/design/widget/BottomSheetBehavior$$ExternalSyntheticOutline0;->m(ILjava/lang/String;)Ljava/lang/String;

    move-result-object v0

    const/4 v1, 0x0

    new-array v2, v1, [Ljava/lang/Object;

    const/4 v3, 0x4

    const-string v4, "VmChangePinActivity"

    invoke-static {v3, v4, v0, v2}, Lcom/android/dialer/common/LogUtil;->println(ILjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->progressDialog:Landroid/app/ProgressDialog;

    invoke-virtual {v0}, Landroid/app/ProgressDialog;->isShowing()Z

    move-result v0

    if-eqz v0, :cond_29

    invoke-virtual {p0}, Landroid/app/Activity;->isDestroyed()Z

    move-result v0

    if-nez v0, :cond_29

    invoke-virtual {p0}, Landroid/app/Activity;->isFinishing()Z

    move-result v0

    if-nez v0, :cond_29

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->progressDialog:Landroid/app/ProgressDialog;

    invoke-virtual {v0}, Landroid/app/ProgressDialog;->dismiss()V

    goto :goto_30

    :cond_29
    const-string v0, "Dialog not visible, not dismissing"

    new-array v2, v1, [Ljava/lang/Object;

    invoke-static {v3, v4, v0, v2}, Lcom/android/dialer/common/LogUtil;->println(ILjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    :goto_30
    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->handler:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$ChangePinHandler;

    const/4 v0, 0x1

    invoke-virtual {p0, v0, p1, v1}, Landroid/os/Handler;->obtainMessage(III)Landroid/os/Message;

    move-result-object p0

    invoke-virtual {p0}, Landroid/os/Message;->sendToTarget()V

    return-void
.end method

.method public final showError(Ljava/lang/CharSequence;Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State$2$1;)V
    .registers 4

    new-instance v0, Landroid/app/AlertDialog$Builder;

    invoke-direct {v0, p0}, Landroid/app/AlertDialog$Builder;-><init>(Landroid/content/Context;)V

    invoke-virtual {v0, p1}, Landroid/app/AlertDialog$Builder;->setMessage(Ljava/lang/CharSequence;)Landroid/app/AlertDialog$Builder;

    move-result-object p0

    const p1, 0x104000a

    const/4 v0, 0x0

    invoke-virtual {p0, p1, v0}, Landroid/app/AlertDialog$Builder;->setPositiveButton(ILandroid/content/DialogInterface$OnClickListener;)Landroid/app/AlertDialog$Builder;

    move-result-object p0

    invoke-virtual {p0, p2}, Landroid/app/AlertDialog$Builder;->setOnDismissListener(Landroid/content/DialogInterface$OnDismissListener;)Landroid/app/AlertDialog$Builder;

    move-result-object p0

    invoke-virtual {p0}, Landroid/app/AlertDialog$Builder;->show()Landroid/app/AlertDialog;

    return-void
.end method

.method public final updateState(Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;)V
    .registers 3

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->uiState:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;

    iput-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->uiState:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;

    if-eq v0, p1, :cond_15

    invoke-virtual {v0, p0}, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;->onLeave(Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;)V

    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->pinEntry:Landroid/widget/EditText;

    const-string v0, ""

    invoke-virtual {p1, v0}, Landroid/widget/EditText;->setText(Ljava/lang/CharSequence;)V

    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->uiState:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;

    invoke-virtual {p1, p0}, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;->onEnter(Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;)V

    :cond_15
    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->uiState:Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;

    invoke-virtual {p1, p0}, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity$State;->onInputChanged(Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;)V

    return-void
.end method
