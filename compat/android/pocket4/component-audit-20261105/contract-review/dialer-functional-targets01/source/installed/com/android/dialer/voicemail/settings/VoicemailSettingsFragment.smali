.class public Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;
.super Landroid/preference/PreferenceFragment;
.source "go/retraceme 9af01222c9f0ce13808ff8a71a2aad063a10a8b4d085240df3537e8ca2c7d173"

# interfaces
.implements Landroid/preference/Preference$OnPreferenceChangeListener;


# static fields
.field static final SUB_ID_EXTRA:Ljava/lang/String; = "com.android.phone.settings.SubscriptionInfoHelper.SubscriptionId"

.field static final SUB_LABEL_EXTRA:Ljava/lang/String; = "com.android.phone.settings.SubscriptionInfoHelper.SubscriptionLabel"


# instance fields
.field public advancedSettingsPreference:Landroid/preference/PreferenceScreen;

.field public changeGreetingPreference:Landroid/preference/Preference;

.field public donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

.field public phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

.field public transcribeVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

.field public visualVoicemailPreference:Landroid/preference/SwitchPreference;

.field public voicemailAutoArchivePreference:Landroid/preference/SwitchPreference;

.field public voicemailChangePinPreference:Landroid/preference/Preference;

.field public voicemailClient:Lcom/android/voicemail/VoicemailClient;

.field public voicemailNotificationPreference:Landroid/preference/Preference;


# direct methods
.method public constructor <init>()V
    .registers 1

    invoke-direct {p0}, Landroid/preference/PreferenceFragment;-><init>()V

    return-void
.end method


# virtual methods
.method public final onCreate(Landroid/os/Bundle;)V
    .registers 3

    invoke-super {p0, p1}, Landroid/preference/PreferenceFragment;->onCreate(Landroid/os/Bundle;)V

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getArguments()Landroid/os/Bundle;

    move-result-object p1

    const-string v0, "phone_account_handle"

    invoke-virtual {p1, v0}, Landroid/os/Bundle;->getParcelable(Ljava/lang/String;)Landroid/os/Parcelable;

    move-result-object p1

    check-cast p1, Landroid/telecom/PhoneAccountHandle;

    invoke-static {p1}, Lcom/android/dialer/common/Assert;->isNotNull(Ljava/lang/Object;)V

    iput-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p1

    invoke-static {p1}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->get$12(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;

    move-result-object p1

    invoke-virtual {p1}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->getVoicemailClient()Lcom/android/voicemail/VoicemailClient;

    move-result-object p1

    iput-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    return-void
.end method

.method public final onPause()V
    .registers 2

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-interface {v0, p0}, Lcom/android/voicemail/VoicemailClient;->removeActivationStateListener(Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;)V

    invoke-super {p0}, Landroid/preference/PreferenceFragment;->onPause()V

    return-void
.end method

.method public final onPreferenceChange(Landroid/preference/Preference;Ljava/lang/Object;)Z
    .registers 7

    invoke-static {p1}, Ljava/util/Objects;->toString(Ljava/lang/Object;)Ljava/lang/String;

    invoke-static {p2}, Ljava/util/Objects;->toString(Ljava/lang/Object;)Ljava/lang/String;

    invoke-virtual {p1}, Landroid/preference/Preference;->getKey()Ljava/lang/String;

    move-result-object v0

    iget-object v1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->visualVoicemailPreference:Landroid/preference/SwitchPreference;

    invoke-virtual {v1}, Landroid/preference/SwitchPreference;->getKey()Ljava/lang/String;

    move-result-object v1

    invoke-virtual {v0, v1}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v0

    const/4 v1, 0x1

    if-eqz v0, :cond_64

    check-cast p2, Ljava/lang/Boolean;

    invoke-virtual {p2}, Ljava/lang/Boolean;->booleanValue()Z

    move-result p1

    if-nez p1, :cond_60

    const/4 p1, 0x0

    new-array p2, p1, [Ljava/lang/Object;

    const/4 v0, 0x4

    const-string v2, "VmSettingsActivity"

    const-string v3, "showDisableConfirmationDialog"

    invoke-static {v0, v2, v3, p2}, Lcom/android/dialer/common/LogUtil;->println(ILjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V

    new-instance p2, Landroid/app/AlertDialog$Builder;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v0

    invoke-direct {p2, v0}, Landroid/app/AlertDialog$Builder;-><init>(Landroid/content/Context;)V

    const v0, 0x7f1100ff

    invoke-virtual {p2, v0}, Landroid/app/AlertDialog$Builder;->setTitle(I)Landroid/app/AlertDialog$Builder;

    const v0, 0x7f1100fe

    invoke-virtual {p2, v0}, Landroid/app/AlertDialog$Builder;->setMessage(I)Landroid/app/AlertDialog$Builder;

    new-instance v0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$4;

    invoke-direct {v0}, Ljava/lang/Object;-><init>()V

    iput-object p0, v0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$4;->this$0:Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    const p0, 0x7f1100fd

    invoke-virtual {p2, p0, v0}, Landroid/app/AlertDialog$Builder;->setPositiveButton(ILandroid/content/DialogInterface$OnClickListener;)Landroid/app/AlertDialog$Builder;

    new-instance p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$5;

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    const/high16 v0, 0x1040000

    invoke-virtual {p2, v0, p0}, Landroid/app/AlertDialog$Builder;->setNegativeButton(ILandroid/content/DialogInterface$OnClickListener;)Landroid/app/AlertDialog$Builder;

    invoke-virtual {p2, v1}, Landroid/app/AlertDialog$Builder;->setCancelable(Z)Landroid/app/AlertDialog$Builder;

    invoke-virtual {p2}, Landroid/app/AlertDialog$Builder;->show()Landroid/app/AlertDialog;

    return p1

    :cond_60
    invoke-virtual {p0, v1}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->updateVoicemailEnabled(Z)V

    return v1

    :cond_64
    invoke-virtual {p1}, Landroid/preference/Preference;->getKey()Ljava/lang/String;

    move-result-object v0

    iget-object v2, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailAutoArchivePreference:Landroid/preference/SwitchPreference;

    invoke-virtual {v2}, Landroid/preference/SwitchPreference;->getKey()Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v0, v2}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_a7

    check-cast p2, Ljava/lang/Boolean;

    invoke-virtual {p2}, Ljava/lang/Boolean;->booleanValue()Z

    move-result p1

    if-eqz p1, :cond_8a

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p1

    invoke-static {p1}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object p1

    sget-object v0, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    goto :goto_97

    :cond_8a
    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p1

    invoke-static {p1}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object p1

    sget-object v0, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    :goto_97
    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v0

    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-virtual {p2}, Ljava/lang/Boolean;->booleanValue()Z

    move-result p2

    invoke-interface {p1, v0, p0, p2}, Lcom/android/voicemail/VoicemailClient;->setVoicemailArchiveEnabled(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;Z)V

    return v1

    :cond_a7
    invoke-virtual {p1}, Landroid/preference/Preference;->getKey()Ljava/lang/String;

    move-result-object v0

    iget-object v2, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->transcribeVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v2}, Landroid/preference/SwitchPreference;->getKey()Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v0, v2}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_ed

    check-cast p2, Ljava/lang/Boolean;

    invoke-virtual {p2}, Ljava/lang/Boolean;->booleanValue()Z

    move-result p1

    if-eqz p1, :cond_cd

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p1

    invoke-static {p1}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object p1

    sget-object v0, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    goto :goto_da

    :cond_cd
    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p1

    invoke-static {p1}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object p1

    sget-object v0, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    :goto_da
    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v0

    iget-object v2, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-virtual {p2}, Ljava/lang/Boolean;->booleanValue()Z

    move-result p2

    invoke-interface {p1, v0, v2, p2}, Lcom/android/voicemail/VoicemailClient;->setVoicemailTranscriptionEnabled(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;Z)V

    invoke-virtual {p0}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->updateTranscriptionDonationPreference()V

    return v1

    :cond_ed
    invoke-virtual {p1}, Landroid/preference/Preference;->getKey()Ljava/lang/String;

    move-result-object p1

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0}, Landroid/preference/SwitchPreference;->getKey()Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p1, v0}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

    move-result p1

    if-eqz p1, :cond_12f

    check-cast p2, Ljava/lang/Boolean;

    invoke-virtual {p2}, Ljava/lang/Boolean;->booleanValue()Z

    move-result p1

    if-eqz p1, :cond_113

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p1

    invoke-static {p1}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object p1

    sget-object v0, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    goto :goto_120

    :cond_113
    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p1

    invoke-static {p1}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object p1

    sget-object v0, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    :goto_120
    iget-object p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v0

    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-virtual {p2}, Ljava/lang/Boolean;->booleanValue()Z

    move-result p2

    invoke-interface {p1, v0, p0, p2}, Lcom/android/voicemail/VoicemailClient;->setVoicemailDonationEnabled(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;Z)V

    :cond_12f
    return v1
.end method

.method public final onResume()V
    .registers 8

    invoke-super {p0}, Landroid/preference/PreferenceFragment;->onResume()V

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v0

    invoke-static {v0}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object v0

    sget-object v1, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-interface {v0, p0}, Lcom/android/voicemail/VoicemailClient;->addActivationStateListener(Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;)V

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    if-eqz v0, :cond_1e

    invoke-virtual {v0}, Landroid/preference/PreferenceScreen;->removeAll()V

    :cond_1e
    const v0, 0x7f140006

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->addPreferencesFromResource(I)V

    const v0, 0x7f1103e1

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->getString(I)Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->findPreference(Ljava/lang/CharSequence;)Landroid/preference/Preference;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailNotificationPreference:Landroid/preference/Preference;

    const/4 v1, 0x1

    invoke-virtual {v0, v1}, Landroid/preference/Preference;->setOrder(I)V

    const v0, 0x7f1103b0

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->getString(I)Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->findPreference(Ljava/lang/CharSequence;)Landroid/preference/Preference;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->changeGreetingPreference:Landroid/preference/Preference;

    const/16 v2, 0x8

    invoke-virtual {v0, v2}, Landroid/preference/Preference;->setOrder(I)V

    const v0, 0x7f1103ae

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->getString(I)Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->findPreference(Ljava/lang/CharSequence;)Landroid/preference/Preference;

    move-result-object v0

    check-cast v0, Landroid/preference/PreferenceScreen;

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->advancedSettingsPreference:Landroid/preference/PreferenceScreen;

    const/4 v2, 0x7

    invoke-virtual {v0, v2}, Landroid/preference/PreferenceScreen;->setOrder(I)V

    const v0, 0x7f1103f8

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->getString(I)Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->findPreference(Ljava/lang/CharSequence;)Landroid/preference/Preference;

    move-result-object v0

    check-cast v0, Landroid/preference/SwitchPreference;

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->visualVoicemailPreference:Landroid/preference/SwitchPreference;

    const/4 v2, 0x2

    invoke-virtual {v0, v2}, Landroid/preference/SwitchPreference;->setOrder(I)V

    const v0, 0x7f1103f4

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->getString(I)Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->findPreference(Ljava/lang/CharSequence;)Landroid/preference/Preference;

    move-result-object v0

    check-cast v0, Landroid/preference/SwitchPreference;

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailAutoArchivePreference:Landroid/preference/SwitchPreference;

    const/4 v3, 0x6

    invoke-virtual {v0, v3}, Landroid/preference/SwitchPreference;->setOrder(I)V

    const v0, 0x7f1103fa

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->getString(I)Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->findPreference(Ljava/lang/CharSequence;)Landroid/preference/Preference;

    move-result-object v0

    check-cast v0, Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->transcribeVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    const/4 v3, 0x3

    invoke-virtual {v0, v3}, Landroid/preference/SwitchPreference;->setOrder(I)V

    const v0, 0x7f1103f6

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->getString(I)Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->findPreference(Ljava/lang/CharSequence;)Landroid/preference/Preference;

    move-result-object v0

    check-cast v0, Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    const/4 v3, 0x4

    invoke-virtual {v0, v3}, Landroid/preference/SwitchPreference;->setOrder(I)V

    const v0, 0x7f1103b2

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->getString(I)Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p0, v0}, Landroid/preference/PreferenceFragment;->findPreference(Ljava/lang/CharSequence;)Landroid/preference/Preference;

    move-result-object v0

    iput-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailChangePinPreference:Landroid/preference/Preference;

    const/4 v3, 0x5

    invoke-virtual {v0, v3}, Landroid/preference/Preference;->setOrder(I)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v3

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v0, v3, v4}, Lcom/android/voicemail/VoicemailClient;->hasCarrierSupport(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v0

    const/4 v3, 0x0

    if-nez v0, :cond_e5

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->visualVoicemailPreference:Landroid/preference/SwitchPreference;

    invoke-virtual {v0, v4}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailAutoArchivePreference:Landroid/preference/SwitchPreference;

    invoke-virtual {v0, v4}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->transcribeVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0, v4}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0, v4}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailChangePinPreference:Landroid/preference/Preference;

    invoke-virtual {v0, v4}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    goto/16 :goto_1cc

    :cond_e5
    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->visualVoicemailPreference:Landroid/preference/SwitchPreference;

    invoke-virtual {v0, p0}, Landroid/preference/SwitchPreference;->setOnPreferenceChangeListener(Landroid/preference/Preference$OnPreferenceChangeListener;)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->visualVoicemailPreference:Landroid/preference/SwitchPreference;

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v5

    iget-object v6, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v4, v5, v6}, Lcom/android/voicemail/VoicemailClient;->isVoicemailEnabled(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v4

    invoke-virtual {v0, v4}, Landroid/preference/SwitchPreference;->setChecked(Z)V

    invoke-virtual {p0}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->updateVoicemailSummaryMessage()V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v4

    iget-object v5, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v0, v4, v5}, Lcom/android/voicemail/VoicemailClient;->isVoicemailEnabled(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v0

    if-eqz v0, :cond_155

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v4

    iget-object v5, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v0, v4, v5}, Lcom/android/voicemail/VoicemailClient;->isActivated(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v0

    if-nez v0, :cond_11b

    goto :goto_155

    :cond_11b
    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v0

    invoke-static {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->get$12(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;

    move-result-object v0

    invoke-virtual {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->getVoicemailClient()Lcom/android/voicemail/VoicemailClient;

    move-result-object v0

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v4

    invoke-interface {v0, v4}, Lcom/android/voicemail/VoicemailClient;->isVoicemailArchiveAvailable(Landroid/content/Context;)Z

    move-result v0

    if-nez v0, :cond_13b

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailAutoArchivePreference:Landroid/preference/SwitchPreference;

    invoke-virtual {v0, v4}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    goto :goto_151

    :cond_13b
    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailAutoArchivePreference:Landroid/preference/SwitchPreference;

    invoke-virtual {v0, p0}, Landroid/preference/SwitchPreference;->setOnPreferenceChangeListener(Landroid/preference/Preference$OnPreferenceChangeListener;)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailAutoArchivePreference:Landroid/preference/SwitchPreference;

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v5

    iget-object v6, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v4, v5, v6}, Lcom/android/voicemail/VoicemailClient;->isVoicemailArchiveEnabled(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v4

    invoke-virtual {v0, v4}, Landroid/preference/SwitchPreference;->setChecked(Z)V

    :goto_151
    invoke-virtual {p0}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->updateTranscriptionPreferences()V

    goto :goto_170

    :cond_155
    :goto_155
    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->transcribeVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0, v4}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0, v4}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailAutoArchivePreference:Landroid/preference/SwitchPreference;

    invoke-virtual {v0, v4}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    :goto_170
    new-instance v0, Landroid/content/Intent;

    new-instance v4, Landroid/content/Intent;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v5

    const-class v6, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;

    invoke-direct {v4, v5, v6}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    invoke-direct {v0, v4}, Landroid/content/Intent;-><init>(Landroid/content/Intent;)V

    const-string v4, "phone_account_handle"

    iget-object v5, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-virtual {v0, v4, v5}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Landroid/os/Parcelable;)Landroid/content/Intent;

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailChangePinPreference:Landroid/preference/Preference;

    invoke-virtual {v4, v0}, Landroid/preference/Preference;->setIntent(Landroid/content/Intent;)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailChangePinPreference:Landroid/preference/Preference;

    new-instance v4, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;

    invoke-direct {v4, v3}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;-><init>(I)V

    iput-object p0, v4, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;->this$0:Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-virtual {v0, v4}, Landroid/preference/Preference;->setOnPreferenceClickListener(Landroid/preference/Preference$OnPreferenceClickListener;)V

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v0

    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    sget v5, Lcom/android/dialer/voicemail/settings/VoicemailChangePinActivity;->$r8$clinit:I

    invoke-static {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->get$12(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;

    move-result-object v5

    invoke-virtual {v5}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->getVoicemailClient()Lcom/android/voicemail/VoicemailClient;

    move-result-object v5

    invoke-interface {v5, v0, v4}, Lcom/android/voicemail/VoicemailClient;->createPinChanger(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Lcom/android/voicemail/impl/PinChangerImpl;

    move-result-object v0

    invoke-virtual {v0}, Lcom/android/voicemail/impl/PinChangerImpl;->getScrambledPin()Ljava/lang/String;

    move-result-object v0

    if-eqz v0, :cond_1b7

    move v0, v1

    goto :goto_1b8

    :cond_1b7
    move v0, v3

    :goto_1b8
    iget-object v4, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailChangePinPreference:Landroid/preference/Preference;

    if-eqz v0, :cond_1c3

    const v0, 0x7f1103e5

    invoke-virtual {v4, v0}, Landroid/preference/Preference;->setTitle(I)V

    goto :goto_1c9

    :cond_1c3
    const v0, 0x7f1103b5

    invoke-virtual {v4, v0}, Landroid/preference/Preference;->setTitle(I)V

    :goto_1c9
    invoke-virtual {p0}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->updateChangePinPreference()V

    :goto_1cc
    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailNotificationPreference:Landroid/preference/Preference;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v4

    iget-object v5, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-static {v4, v5}, Lcom/android/dialer/notification/NotificationChannelManager;->getVoicemailChannelId(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Ljava/lang/String;

    move-result-object v4

    new-instance v5, Landroid/content/Intent;

    const-string v6, "android.settings.CHANNEL_NOTIFICATION_SETTINGS"

    invoke-direct {v5, v6}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    const-string v6, "android.provider.extra.CHANNEL_ID"

    invoke-virtual {v5, v6, v4}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v4

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v5

    invoke-virtual {v5}, Landroid/content/Context;->getPackageName()Ljava/lang/String;

    move-result-object v5

    const-string v6, "android.provider.extra.APP_PACKAGE"

    invoke-virtual {v4, v6, v5}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/lang/String;)Landroid/content/Intent;

    move-result-object v4

    invoke-virtual {v0, v4}, Landroid/preference/Preference;->setIntent(Landroid/content/Intent;)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailNotificationPreference:Landroid/preference/Preference;

    new-instance v4, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;

    invoke-direct {v4, v1}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;-><init>(I)V

    iput-object p0, v4, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;->this$0:Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-virtual {v0, v4}, Landroid/preference/Preference;->setOnPreferenceClickListener(Landroid/preference/Preference$OnPreferenceClickListener;)V

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v0

    invoke-static {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->get$2(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;

    move-result-object v0

    invoke-virtual {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->getConfigProvider()Lcom/android/dialer/configprovider/SharedPrefConfigProvider;

    move-result-object v0

    const-string v4, "voicemail_change_greeting_enabled"

    invoke-virtual {v0, v4, v3}, Lcom/android/dialer/configprovider/SharedPrefConfigProvider;->getBoolean(Ljava/lang/String;Z)Z

    move-result v0

    if-nez v0, :cond_223

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    iget-object v3, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->changeGreetingPreference:Landroid/preference/Preference;

    invoke-virtual {v0, v3}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    goto :goto_233

    :cond_223
    new-instance v0, Landroid/content/Intent;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v3

    const-class v4, Lcom/android/dialer/voicemail/settings/CurrentVoicemailGreetingActivity;

    invoke-direct {v0, v3, v4}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V

    iget-object v3, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->changeGreetingPreference:Landroid/preference/Preference;

    invoke-virtual {v3, v0}, Landroid/preference/Preference;->setIntent(Landroid/content/Intent;)V

    :goto_233
    new-instance v0, Landroid/content/Intent;

    const-string v3, "android.telephony.action.CONFIGURE_VOICEMAIL"

    invoke-direct {v0, v3}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V

    const-string v3, "android.telephony.extra.HIDE_PUBLIC_SETTINGS"

    invoke-virtual {v0, v3, v1}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Z)Landroid/content/Intent;

    const-string v1, "android.telephony.extra.PHONE_ACCOUNT_HANDLE"

    iget-object v3, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-virtual {v0, v1, v3}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Landroid/os/Parcelable;)Landroid/content/Intent;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v1

    iget-object v3, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-static {v1, v3}, Lcom/android/dialer/telecom/TelecomUtil;->getSubscriptionInfo(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Lcom/google/common/base/Optional;

    move-result-object v1

    invoke-virtual {v1}, Lcom/google/common/base/Optional;->isPresent()Z

    move-result v3

    if-eqz v3, :cond_282

    invoke-virtual {v1}, Lcom/google/common/base/Optional;->get()Ljava/lang/Object;

    move-result-object v1

    check-cast v1, Landroid/telephony/SubscriptionInfo;

    invoke-virtual {v1}, Landroid/telephony/SubscriptionInfo;->getSubscriptionId()I

    move-result v1

    const-string v3, "com.android.phone.settings.SubscriptionInfoHelper.SubscriptionId"

    invoke-virtual {v0, v3, v1}, Landroid/content/Intent;->putExtra(Ljava/lang/String;I)Landroid/content/Intent;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v1

    const-class v3, Landroid/telecom/TelecomManager;

    invoke-virtual {v1, v3}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;

    move-result-object v1

    check-cast v1, Landroid/telecom/TelecomManager;

    iget-object v3, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-virtual {v1, v3}, Landroid/telecom/TelecomManager;->getPhoneAccount(Landroid/telecom/PhoneAccountHandle;)Landroid/telecom/PhoneAccount;

    move-result-object v1

    if-eqz v1, :cond_282

    const-string v3, "com.android.phone.settings.SubscriptionInfoHelper.SubscriptionLabel"

    invoke-virtual {v1}, Landroid/telecom/PhoneAccount;->getLabel()Ljava/lang/CharSequence;

    move-result-object v1

    invoke-virtual {v0, v3, v1}, Landroid/content/Intent;->putExtra(Ljava/lang/String;Ljava/lang/CharSequence;)Landroid/content/Intent;

    :cond_282
    iget-object v1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->advancedSettingsPreference:Landroid/preference/PreferenceScreen;

    invoke-virtual {v1, v0}, Landroid/preference/PreferenceScreen;->setIntent(Landroid/content/Intent;)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->advancedSettingsPreference:Landroid/preference/PreferenceScreen;

    new-instance v1, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;

    invoke-direct {v1, v2}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;-><init>(I)V

    iput-object p0, v1, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;->this$0:Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;

    invoke-static {}, Ljava/lang/invoke/VarHandle;->storeStoreFence()V

    invoke-virtual {v0, v1}, Landroid/preference/PreferenceScreen;->setOnPreferenceClickListener(Landroid/preference/Preference$OnPreferenceClickListener;)V

    return-void
.end method

.method public final updateChangePinPreference()V
    .registers 5

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v1

    iget-object v2, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v0, v1, v2}, Lcom/android/voicemail/VoicemailClient;->isVoicemailEnabled(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v0

    const/4 v1, 0x0

    if-nez v0, :cond_1d

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailChangePinPreference:Landroid/preference/Preference;

    const v2, 0x7f1103b3

    invoke-virtual {v0, v2}, Landroid/preference/Preference;->setSummary(I)V

    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailChangePinPreference:Landroid/preference/Preference;

    invoke-virtual {p0, v1}, Landroid/preference/Preference;->setEnabled(Z)V

    return-void

    :cond_1d
    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v2

    iget-object v3, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v0, v2, v3}, Lcom/android/voicemail/VoicemailClient;->isActivated(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v0

    iget-object v2, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailChangePinPreference:Landroid/preference/Preference;

    if-nez v0, :cond_39

    const v0, 0x7f1103b4

    invoke-virtual {v2, v0}, Landroid/preference/Preference;->setSummary(I)V

    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailChangePinPreference:Landroid/preference/Preference;

    invoke-virtual {p0, v1}, Landroid/preference/Preference;->setEnabled(Z)V

    return-void

    :cond_39
    const/4 v0, 0x0

    invoke-virtual {v2, v0}, Landroid/preference/Preference;->setSummary(Ljava/lang/CharSequence;)V

    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailChangePinPreference:Landroid/preference/Preference;

    const/4 v0, 0x1

    invoke-virtual {p0, v0}, Landroid/preference/Preference;->setEnabled(Z)V

    return-void
.end method

.method public final updateTranscriptionDonationPreference()V
    .registers 8

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v0

    invoke-static {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->get$12(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;

    move-result-object v0

    invoke-virtual {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->getVoicemailClient()Lcom/android/voicemail/VoicemailClient;

    move-result-object v0

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v1

    iget-object v2, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v0, v1, v2}, Lcom/android/voicemail/VoicemailClient;->isVoicemailDonationAvailable(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v0

    if-nez v0, :cond_22

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0, p0}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    return-void

    :cond_22
    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    const/4 v1, 0x1

    invoke-virtual {v0, v1}, Landroid/preference/SwitchPreference;->setEnabled(Z)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    iget-object v1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v2

    iget-object v3, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v1, v2, v3}, Lcom/android/voicemail/VoicemailClient;->isVoicemailDonationEnabled(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v1

    invoke-virtual {v0, v1}, Landroid/preference/SwitchPreference;->setChecked(Z)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0, p0}, Landroid/preference/SwitchPreference;->setOnPreferenceChangeListener(Landroid/preference/Preference$OnPreferenceChangeListener;)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v1

    invoke-virtual {v1}, Landroid/content/Context;->getApplicationContext()Landroid/content/Context;

    move-result-object v1

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v2

    const v3, 0x7f1103b6

    invoke-virtual {v2, v3}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v3

    const v4, 0x7f110186

    invoke-virtual {v3, v4}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v3

    const v4, 0x7f1101a1

    invoke-virtual {v1, v4}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v1

    new-instance v4, Landroid/text/SpannableString;

    filled-new-array {v1}, [Ljava/lang/Object;

    move-result-object v5

    invoke-static {v2, v5}, Ljava/lang/String;->format(Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/String;

    move-result-object v5

    invoke-direct {v4, v5}, Landroid/text/SpannableString;-><init>(Ljava/lang/CharSequence;)V

    invoke-virtual {v4}, Landroid/text/SpannableString;->toString()Ljava/lang/String;

    move-result-object v5

    invoke-virtual {v5, v1}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v5

    const-string v6, "Couldn\'t add learn more link to %s"

    filled-new-array {v2}, [Ljava/lang/Object;

    move-result-object v2

    invoke-static {v5, v6, v2}, Lcom/android/dialer/common/Assert;->checkArgument(ZLjava/lang/String;[Ljava/lang/Object;)V

    invoke-virtual {v4}, Landroid/text/SpannableString;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v2, v1}, Ljava/lang/String;->lastIndexOf(Ljava/lang/String;)I

    move-result v2

    invoke-virtual {v1}, Ljava/lang/String;->length()I

    move-result v1

    add-int/2addr v1, v2

    new-instance v5, Landroid/text/style/TypefaceSpan;

    const-string v6, "sans-serif-medium"

    invoke-direct {v5, v6}, Landroid/text/style/TypefaceSpan;-><init>(Ljava/lang/String;)V

    const/16 v6, 0x12

    invoke-virtual {v4, v5, v2, v1, v6}, Landroid/text/SpannableString;->setSpan(Ljava/lang/Object;III)V

    new-instance v5, Lcom/android/dialer/spannable/UrlSpanWithoutUnderline;

    invoke-direct {v5, v3}, Landroid/text/style/URLSpan;-><init>(Ljava/lang/String;)V

    invoke-virtual {v4, v5, v2, v1, v6}, Landroid/text/SpannableString;->setSpan(Ljava/lang/Object;III)V

    invoke-virtual {v0, v4}, Landroid/preference/SwitchPreference;->setSummary(Ljava/lang/CharSequence;)V

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0, p0}, Landroid/preference/PreferenceScreen;->addPreference(Landroid/preference/Preference;)Z

    return-void
.end method

.method public final updateTranscriptionPreferences()V
    .registers 8

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v0

    invoke-static {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->get$12(Landroid/content/Context;)Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;

    move-result-object v0

    invoke-virtual {v0}, Lcom/android/dialer/binary/aosp/DaggerAospDialerRootComponent$DuoComponentImpl;->getVoicemailClient()Lcom/android/voicemail/VoicemailClient;

    move-result-object v0

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v1

    iget-object v2, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v0, v1, v2}, Lcom/android/voicemail/VoicemailClient;->isVoicemailTranscriptionAvailable(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v0

    if-nez v0, :cond_2b

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    iget-object v1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->transcribeVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0, v1}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->donateTranscribedVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0, p0}, Landroid/preference/PreferenceScreen;->removePreference(Landroid/preference/Preference;)Z

    return-void

    :cond_2b
    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->transcribeVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0, p0}, Landroid/preference/SwitchPreference;->setOnPreferenceChangeListener(Landroid/preference/Preference$OnPreferenceChangeListener;)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->transcribeVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    iget-object v1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v2

    iget-object v3, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v1, v2, v3}, Lcom/android/voicemail/VoicemailClient;->isVoicemailTranscriptionEnabled(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v1

    invoke-virtual {v0, v1}, Landroid/preference/SwitchPreference;->setChecked(Z)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->transcribeVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v1

    invoke-virtual {v1}, Landroid/content/Context;->getApplicationContext()Landroid/content/Context;

    move-result-object v1

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v2

    const v3, 0x7f1103f1

    invoke-virtual {v2, v3}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v2

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v3

    const v4, 0x7f110358

    invoke-virtual {v3, v4}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v3

    const v4, 0x7f1101a1

    invoke-virtual {v1, v4}, Landroid/content/Context;->getString(I)Ljava/lang/String;

    move-result-object v1

    new-instance v4, Landroid/text/SpannableString;

    filled-new-array {v1}, [Ljava/lang/Object;

    move-result-object v5

    invoke-static {v2, v5}, Ljava/lang/String;->format(Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/String;

    move-result-object v5

    invoke-direct {v4, v5}, Landroid/text/SpannableString;-><init>(Ljava/lang/CharSequence;)V

    invoke-virtual {v4}, Landroid/text/SpannableString;->toString()Ljava/lang/String;

    move-result-object v5

    invoke-virtual {v5, v1}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v5

    const-string v6, "Couldn\'t add learn more link to %s"

    filled-new-array {v2}, [Ljava/lang/Object;

    move-result-object v2

    invoke-static {v5, v6, v2}, Lcom/android/dialer/common/Assert;->checkArgument(ZLjava/lang/String;[Ljava/lang/Object;)V

    invoke-virtual {v4}, Landroid/text/SpannableString;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-virtual {v2, v1}, Ljava/lang/String;->lastIndexOf(Ljava/lang/String;)I

    move-result v2

    invoke-virtual {v1}, Ljava/lang/String;->length()I

    move-result v1

    add-int/2addr v1, v2

    new-instance v5, Landroid/text/style/TypefaceSpan;

    const-string v6, "sans-serif-medium"

    invoke-direct {v5, v6}, Landroid/text/style/TypefaceSpan;-><init>(Ljava/lang/String;)V

    const/16 v6, 0x12

    invoke-virtual {v4, v5, v2, v1, v6}, Landroid/text/SpannableString;->setSpan(Ljava/lang/Object;III)V

    new-instance v5, Lcom/android/dialer/spannable/UrlSpanWithoutUnderline;

    invoke-direct {v5, v3}, Landroid/text/style/URLSpan;-><init>(Ljava/lang/String;)V

    invoke-virtual {v4, v5, v2, v1, v6}, Landroid/text/SpannableString;->setSpan(Ljava/lang/Object;III)V

    invoke-virtual {v0, v4}, Landroid/preference/SwitchPreference;->setSummary(Ljava/lang/CharSequence;)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->transcribeVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    const/4 v1, 0x1

    invoke-virtual {v0, v1}, Landroid/preference/SwitchPreference;->setEnabled(Z)V

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getPreferenceScreen()Landroid/preference/PreferenceScreen;

    move-result-object v0

    iget-object v1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->transcribeVoicemailPreference:Lcom/android/dialer/common/preference/SwitchPreferenceWithClickableSummary;

    invoke-virtual {v0, v1}, Landroid/preference/PreferenceScreen;->addPreference(Landroid/preference/Preference;)Z

    invoke-virtual {p0}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->updateTranscriptionDonationPreference()V

    return-void
.end method

.method public final updateVoicemailEnabled(Z)V
    .registers 5

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v1

    iget-object v2, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v0, v1, v2, p1}, Lcom/android/voicemail/VoicemailClient;->setVoicemailEnabled(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;Z)V

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->visualVoicemailPreference:Landroid/preference/SwitchPreference;

    invoke-virtual {v0, p1}, Landroid/preference/SwitchPreference;->setChecked(Z)V

    if-eqz p1, :cond_20

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p1

    invoke-static {p1}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object p1

    sget-object v0, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    goto :goto_2d

    :cond_20
    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p1

    invoke-static {p1}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object p1

    sget-object v0, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {p1}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    :goto_2d
    invoke-virtual {p0}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->updateVoicemailSummaryMessage()V

    invoke-virtual {p0}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->updateTranscriptionPreferences()V

    invoke-virtual {p0}, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->updateChangePinPreference()V

    return-void
.end method

.method public final updateVoicemailSummaryMessage()V
    .registers 4

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v1

    iget-object v2, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v0, v1, v2}, Lcom/android/voicemail/VoicemailClient;->isVoicemailEnabled(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v0

    if-eqz v0, :cond_25

    iget-object v0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->voicemailClient:Lcom/android/voicemail/VoicemailClient;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object v1

    iget-object v2, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->phoneAccountHandle:Landroid/telecom/PhoneAccountHandle;

    invoke-interface {v0, v1, v2}, Lcom/android/voicemail/VoicemailClient;->isActivated(Landroid/content/Context;Landroid/telecom/PhoneAccountHandle;)Z

    move-result v0

    if-nez v0, :cond_25

    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->visualVoicemailPreference:Landroid/preference/SwitchPreference;

    const v0, 0x7f1103ad

    invoke-virtual {p0, v0}, Landroid/preference/SwitchPreference;->setSummary(I)V

    return-void

    :cond_25
    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;->visualVoicemailPreference:Landroid/preference/SwitchPreference;

    const-string v0, ""

    invoke-virtual {p0, v0}, Landroid/preference/SwitchPreference;->setSummary(Ljava/lang/CharSequence;)V

    return-void
.end method
