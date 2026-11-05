.class public final Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;
.super Ljava/lang/Object;
.source "go/retraceme 9af01222c9f0ce13808ff8a71a2aad063a10a8b4d085240df3537e8ca2c7d173"

# interfaces
.implements Landroid/preference/Preference$OnPreferenceClickListener;


# instance fields
.field public final synthetic $r8$classId:I

.field public synthetic this$0:Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;


# direct methods
.method public synthetic constructor <init>(I)V
    .registers 2

    iput p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;->$r8$classId:I

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method


# virtual methods
.method public final onPreferenceClick(Landroid/preference/Preference;)Z
    .registers 3

    iget p1, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;->$r8$classId:I

    const/4 v0, 0x0

    packed-switch p1, :pswitch_data_36

    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;->this$0:Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p0

    invoke-static {p0}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object p0

    sget-object p1, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {p0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    return v0

    :pswitch_16
    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;->this$0:Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p0

    invoke-static {p0}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object p0

    sget-object p1, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {p0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    return v0

    :pswitch_26
    iget-object p0, p0, Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment$1;->this$0:Lcom/android/dialer/voicemail/settings/VoicemailSettingsFragment;

    invoke-virtual {p0}, Landroid/preference/PreferenceFragment;->getContext()Landroid/content/Context;

    move-result-object p0

    invoke-static {p0}, Lcom/android/dialer/logging/Logger;->get(Landroid/content/Context;)Lcom/android/dialer/logging/LoggingBindingsStub;

    move-result-object p0

    sget-object p1, Lcom/android/dialer/logging/DialerImpression$Type;->UNKNOWN_AOSP_EVENT_TYPE:Lcom/android/dialer/logging/DialerImpression$Type;

    invoke-virtual {p0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    return v0

    :pswitch_data_36
    .packed-switch 0x0
        :pswitch_26
        :pswitch_16
    .end packed-switch
.end method
