.class public final Lorg/droidloom/qa/editorcontract/EditorContractActivity;
.super Landroid/app/Activity;
.source "EditorContractActivity.java"


# annotations
.annotation system Ldalvik/annotation/MemberClasses;
    value = {
        Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;
    }
.end annotation


# static fields
.field private static final FIELD_ID:I = 0x100901

.field private static final MAX_BYTES:I = 0x10000

.field private static final MAX_EVENTS:I = 0x60


# instance fields
.field private connections:I

.field private createdElapsed:J

.field private droppedEvents:I

.field private editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

.field private editorActions:I

.field private final events:Lorg/json/JSONArray;

.field private evidence:Landroid/util/AtomicFile;

.field private failed:Z

.field private runId:Ljava/lang/String;


# direct methods
.method public constructor <init>()V
    .registers 2

    .line 24
    invoke-direct {p0}, Landroid/app/Activity;-><init>()V

    .line 28
    new-instance v0, Lorg/json/JSONArray;

    invoke-direct {v0}, Lorg/json/JSONArray;-><init>()V

    iput-object v0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->events:Lorg/json/JSONArray;

    return-void
.end method

.method static synthetic access$000(Lorg/droidloom/qa/editorcontract/EditorContractActivity;Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V
    .registers 5

    .line 24
    invoke-direct {p0, p1, p2, p3, p4}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V

    return-void
.end method

.method static synthetic access$108(Lorg/droidloom/qa/editorcontract/EditorContractActivity;)I
    .registers 3

    .line 24
    iget v0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->connections:I

    add-int/lit8 v1, v0, 0x1

    iput v1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->connections:I

    return v0
.end method

.method static synthetic access$200(Ljava/lang/String;Z)Lorg/json/JSONObject;
    .registers 2

    .line 24
    invoke-static {p0, p1}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->detail(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p0

    return-object p0
.end method

.method private static detail(Ljava/lang/String;Z)Lorg/json/JSONObject;
    .registers 3

    .line 142
    :try_start_0
    new-instance v0, Lorg/json/JSONObject;

    invoke-direct {v0}, Lorg/json/JSONObject;-><init>()V

    invoke-virtual {v0, p0, p1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p0
    :try_end_9
    .catch Ljava/lang/Exception; {:try_start_0 .. :try_end_9} :catch_a

    return-object p0

    :catch_a
    move-exception p0

    .line 143
    new-instance p1, Ljava/lang/IllegalStateException;

    invoke-direct {p1, p0}, Ljava/lang/IllegalStateException;-><init>(Ljava/lang/Throwable;)V

    throw p1
.end method

.method private static key(Landroid/view/KeyEvent;)Lorg/json/JSONObject;
    .registers 5
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Ljava/lang/Exception;
        }
    .end annotation

    if-nez p0, :cond_4

    const/4 p0, 0x0

    return-object p0

    .line 40
    :cond_4
    new-instance v0, Lorg/json/JSONObject;

    invoke-direct {v0}, Lorg/json/JSONObject;-><init>()V

    const-string v1, "action"

    invoke-virtual {p0}, Landroid/view/KeyEvent;->getAction()I

    move-result v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "key_code"

    .line 41
    invoke-virtual {p0}, Landroid/view/KeyEvent;->getKeyCode()I

    move-result v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "source"

    invoke-virtual {p0}, Landroid/view/KeyEvent;->getSource()I

    move-result v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "device_id"

    .line 42
    invoke-virtual {p0}, Landroid/view/KeyEvent;->getDeviceId()I

    move-result v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "scan_code"

    invoke-virtual {p0}, Landroid/view/KeyEvent;->getScanCode()I

    move-result v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "repeat_count"

    .line 43
    invoke-virtual {p0}, Landroid/view/KeyEvent;->getRepeatCount()I

    move-result v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "meta_state"

    invoke-virtual {p0}, Landroid/view/KeyEvent;->getMetaState()I

    move-result v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "flags"

    .line 44
    invoke-virtual {p0}, Landroid/view/KeyEvent;->getFlags()I

    move-result v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "canceled"

    invoke-virtual {p0}, Landroid/view/KeyEvent;->isCanceled()Z

    move-result v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "event_time_ms"

    .line 45
    invoke-virtual {p0}, Landroid/view/KeyEvent;->getEventTime()J

    move-result-wide v2

    invoke-virtual {v0, v1, v2, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;J)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "down_time_ms"

    invoke-virtual {p0}, Landroid/view/KeyEvent;->getDownTime()J

    move-result-wide v2

    invoke-virtual {v0, v1, v2, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;J)Lorg/json/JSONObject;

    move-result-object p0

    return-object p0
.end method

.method private declared-synchronized record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V
    .registers 11

    monitor-enter p0

    .line 49
    :try_start_1
    iget-object v0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->evidence:Landroid/util/AtomicFile;

    if-eqz v0, :cond_19f

    iget-boolean v0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->failed:Z
    :try_end_7
    .catchall {:try_start_1 .. :try_end_7} :catchall_1a3

    if-nez v0, :cond_19f

    const/4 v0, 0x1

    const/4 v1, 0x0

    .line 52
    :try_start_b
    iget-object v2, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->events:Lorg/json/JSONArray;

    invoke-virtual {v2}, Lorg/json/JSONArray;->length()I

    move-result v2

    const/16 v3, 0x60

    if-ge v2, v3, :cond_73

    .line 53
    new-instance v2, Lorg/json/JSONObject;

    invoke-direct {v2}, Lorg/json/JSONObject;-><init>()V

    const-string v4, "sequence"

    iget-object v5, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->events:Lorg/json/JSONArray;

    invoke-virtual {v5}, Lorg/json/JSONArray;->length()I

    move-result v5

    add-int/2addr v5, v0

    invoke-virtual {v2, v4, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v2

    const-string v4, "kind"

    .line 54
    invoke-virtual {v2, v4, p1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object p1

    const-string v2, "elapsed_ns"

    invoke-static {}, Landroid/os/SystemClock;->elapsedRealtimeNanos()J

    move-result-wide v4

    invoke-virtual {p1, v2, v4, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;J)Lorg/json/JSONObject;

    move-result-object p1

    const-string v2, "uptime_ms"

    .line 55
    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v4

    invoke-virtual {p1, v2, v4, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;J)Lorg/json/JSONObject;

    move-result-object p1

    const-string v2, "tid"

    invoke-static {}, Landroid/os/Process;->myTid()I

    move-result v4

    invoke-virtual {p1, v2, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string v2, "action_id"

    .line 56
    invoke-virtual {p1, v2, p3}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string p3, "key_event"

    if-nez p2, :cond_58

    sget-object p2, Lorg/json/JSONObject;->NULL:Ljava/lang/Object;

    goto :goto_5c

    :cond_58
    invoke-static {p2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->key(Landroid/view/KeyEvent;)Lorg/json/JSONObject;

    move-result-object p2

    :goto_5c
    invoke-virtual {p1, p3, p2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "details"

    if-nez p4, :cond_69

    .line 57
    new-instance p4, Lorg/json/JSONObject;

    invoke-direct {p4}, Lorg/json/JSONObject;-><init>()V

    :cond_69
    invoke-virtual {p1, p2, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object p1

    .line 58
    iget-object p2, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->events:Lorg/json/JSONArray;

    invoke-virtual {p2, p1}, Lorg/json/JSONArray;->put(Ljava/lang/Object;)Lorg/json/JSONArray;

    goto :goto_7f

    .line 60
    :cond_73
    iget p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->droppedEvents:I

    add-int/2addr p1, v0

    const p2, 0xf4240

    invoke-static {p1, p2}, Ljava/lang/Math;->min(II)I

    move-result p1

    iput p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->droppedEvents:I

    .line 62
    :goto_7f
    new-instance p1, Lorg/json/JSONObject;

    invoke-direct {p1}, Lorg/json/JSONObject;-><init>()V

    const-string p2, "schema"

    const-string p3, "p4-owned-editor-contract-v1"

    invoke-virtual {p1, p2, p3}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "run_id"

    iget-object p3, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->runId:Ljava/lang/String;

    .line 63
    invoke-virtual {p1, p2, p3}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "package"

    invoke-virtual {p0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->getPackageName()Ljava/lang/String;

    move-result-object p3

    invoke-virtual {p1, p2, p3}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "uid"

    .line 64
    invoke-static {}, Landroid/os/Process;->myUid()I

    move-result p3

    invoke-virtual {p1, p2, p3}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "pid"

    invoke-static {}, Landroid/os/Process;->myPid()I

    move-result p3

    invoke-virtual {p1, p2, p3}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "collection_only"

    .line 65
    invoke-virtual {p1, p2, v0}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "created_elapsed_ns"

    iget-wide p3, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->createdElapsed:J

    invoke-virtual {p1, p2, p3, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;J)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "updated_elapsed_ns"

    .line 66
    invoke-static {}, Landroid/os/SystemClock;->elapsedRealtimeNanos()J

    move-result-wide p3

    invoke-virtual {p1, p2, p3, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;J)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "max_events"

    .line 67
    invoke-virtual {p1, p2, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "max_bytes"

    const/high16 p3, 0x10000

    invoke-virtual {p1, p2, p3}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "dropped_events"

    iget p4, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->droppedEvents:I

    .line 68
    invoke-virtual {p1, p2, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "editor_action_count"

    iget p4, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editorActions:I

    invoke-virtual {p1, p2, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "input_connection_count"

    iget p4, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->connections:I

    .line 69
    invoke-virtual {p1, p2, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "field_id"

    const p4, 0x100901

    invoke-virtual {p1, p2, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "single_line"

    .line 70
    invoke-virtual {p1, p2, v0}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "advertised_action"

    const/4 p4, 0x3

    invoke-virtual {p1, p2, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "window_focused"

    .line 71
    invoke-virtual {p0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->hasWindowFocus()Z

    move-result p4

    invoke-virtual {p1, p2, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "editor_focused"

    iget-object p4, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    const/4 v2, 0x0

    if-eqz p4, :cond_11f

    .line 72
    invoke-virtual {p4}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->hasFocus()Z

    move-result p4

    if-eqz p4, :cond_11f

    move p4, v0

    goto :goto_120

    :cond_11f
    move p4, v2

    :goto_120
    invoke-virtual {p1, p2, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "text_length"

    .line 73
    iget-object p4, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    if-nez p4, :cond_12c

    move p4, v2

    goto :goto_130

    :cond_12c
    invoke-virtual {p4}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->length()I

    move-result p4

    :goto_130
    invoke-virtual {p1, p2, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "ready"

    iget-object p4, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    if-eqz p4, :cond_14b

    .line 74
    invoke-virtual {p4}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->hasFocus()Z

    move-result p4

    if-eqz p4, :cond_14b

    invoke-virtual {p0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->hasWindowFocus()Z

    move-result p4

    if-eqz p4, :cond_14b

    iget p4, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->connections:I

    if-lez p4, :cond_14b

    move v2, v0

    :cond_14b
    invoke-virtual {p1, p2, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "events"

    iget-object p4, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->events:Lorg/json/JSONArray;

    .line 75
    invoke-virtual {p1, p2, p4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object p1

    .line 76
    new-instance p2, Ljava/lang/StringBuilder;

    invoke-direct {p2}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {p1}, Lorg/json/JSONObject;->toString()Ljava/lang/String;

    move-result-object p1

    invoke-virtual {p2, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string p1, "\n"

    invoke-virtual {p2, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {p2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object p1

    sget-object p2, Ljava/nio/charset/StandardCharsets;->UTF_8:Ljava/nio/charset/Charset;

    invoke-virtual {p1, p2}, Ljava/lang/String;->getBytes(Ljava/nio/charset/Charset;)[B

    move-result-object p1

    .line 77
    array-length p2, p1

    if-gt p2, p3, :cond_185

    .line 78
    iget-object p2, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->evidence:Landroid/util/AtomicFile;

    invoke-virtual {p2}, Landroid/util/AtomicFile;->startWrite()Ljava/io/FileOutputStream;

    move-result-object v1

    .line 79
    invoke-virtual {v1, p1}, Ljava/io/FileOutputStream;->write([B)V

    .line 80
    iget-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->evidence:Landroid/util/AtomicFile;

    invoke-virtual {p1, v1}, Landroid/util/AtomicFile;->finishWrite(Ljava/io/FileOutputStream;)V
    :try_end_183
    .catch Ljava/lang/Exception; {:try_start_b .. :try_end_183} :catch_18d
    .catchall {:try_start_b .. :try_end_183} :catchall_1a3

    .line 88
    monitor-exit p0

    return-void

    .line 77
    :cond_185
    :try_start_185
    new-instance p1, Ljava/lang/Exception;

    const-string p2, "bounded_evidence_limit"

    invoke-direct {p1, p2}, Ljava/lang/Exception;-><init>(Ljava/lang/String;)V

    throw p1
    :try_end_18d
    .catch Ljava/lang/Exception; {:try_start_185 .. :try_end_18d} :catch_18d
    .catchall {:try_start_185 .. :try_end_18d} :catchall_1a3

    :catch_18d
    move-exception p1

    if-eqz v1, :cond_195

    .line 83
    :try_start_190
    iget-object p2, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->evidence:Landroid/util/AtomicFile;

    invoke-virtual {p2, v1}, Landroid/util/AtomicFile;->failWrite(Ljava/io/FileOutputStream;)V

    .line 84
    :cond_195
    iput-boolean v0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->failed:Z

    .line 86
    new-instance p2, Ljava/lang/IllegalStateException;

    const-string p3, "owned_editor_evidence_failure"

    invoke-direct {p2, p3, p1}, Ljava/lang/IllegalStateException;-><init>(Ljava/lang/String;Ljava/lang/Throwable;)V

    throw p2
    :try_end_19f
    .catchall {:try_start_190 .. :try_end_19f} :catchall_1a3

    .line 49
    :cond_19f
    monitor-exit p0

    return-void

    :goto_1a1
    :try_start_1a1
    monitor-exit p0
    :try_end_1a2
    .catchall {:try_start_1a1 .. :try_end_1a2} :catchall_1a3

    throw p1

    :catchall_1a3
    move-exception p1

    goto :goto_1a1
.end method


# virtual methods
.method synthetic lambda$onCreate$0$org-droidloom-qa-editorcontract-EditorContractActivity(Landroid/widget/TextView;ILandroid/view/KeyEvent;)Z
    .registers 6

    .line 128
    iget p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editorActions:I

    const/4 v0, 0x1

    add-int/2addr p1, v0

    iput p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editorActions:I

    .line 129
    const-string p1, "editor_action"

    const/4 v1, 0x0

    invoke-direct {p0, p1, p3, p2, v1}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V

    return v0
.end method

.method synthetic lambda$onCreate$1$org-droidloom-qa-editorcontract-EditorContractActivity(Landroid/view/View;Z)V
    .registers 5

    .line 133
    const-string p1, "focused"

    invoke-static {p1, p2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->detail(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p1

    const-string p2, "editor_focus"

    const/4 v0, 0x0

    const/4 v1, -0x1

    invoke-direct {p0, p2, v0, v1, p1}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V

    return-void
.end method

.method synthetic lambda$onCreate$2$org-droidloom-qa-editorcontract-EditorContractActivity()V
    .registers 4

    .line 0
    const/4 v0, 0x0

    const/4 v1, -0x1

    .line 138
    const-string v2, "layout_ready"

    invoke-direct {p0, v2, v0, v1, v0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V

    return-void
.end method

.method public onCreate(Landroid/os/Bundle;)V
    .registers 7

    .line 91
    invoke-super {p0, p1}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V

    .line 92
    new-instance p1, Landroid/widget/TextView;

    invoke-direct {p1, p0}, Landroid/widget/TextView;-><init>(Landroid/content/Context;)V

    .line 93
    const-string v0, "Owned editor contract: waiting for two controlled Enter events"

    invoke-virtual {p1, v0}, Landroid/widget/TextView;->setText(Ljava/lang/CharSequence;)V

    .line 94
    invoke-virtual {p0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->getIntent()Landroid/content/Intent;

    move-result-object v0

    const-string v1, "run_id"

    invoke-virtual {v0, v1}, Landroid/content/Intent;->getStringExtra(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    iput-object v0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->runId:Ljava/lang/String;

    if-eqz v0, :cond_148

    .line 95
    const-string v1, "[A-Za-z0-9_]{1,64}"

    invoke-virtual {v0, v1}, Ljava/lang/String;->matches(Ljava/lang/String;)Z

    move-result v0

    if-eqz v0, :cond_148

    .line 101
    :try_start_23
    new-instance v0, Ljava/io/File;

    invoke-virtual {p0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->getFilesDir()Ljava/io/File;

    move-result-object v1

    const-string v2, "editor-contract-v1"

    invoke-direct {v0, v1, v2}, Ljava/io/File;-><init>(Ljava/io/File;Ljava/lang/String;)V

    .line 102
    invoke-virtual {v0}, Ljava/io/File;->isDirectory()Z

    move-result v1

    if-nez v1, :cond_42

    invoke-virtual {v0}, Ljava/io/File;->mkdirs()Z

    move-result v1

    if-nez v1, :cond_42

    new-instance v0, Ljava/lang/Exception;

    const-string v1, "evidence_directory"

    invoke-direct {v0, v1}, Ljava/lang/Exception;-><init>(Ljava/lang/String;)V

    throw v0

    .line 103
    :cond_42
    new-instance v1, Ljava/io/File;

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    iget-object v3, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->runId:Ljava/lang/String;

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v3, ".json"

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-direct {v1, v0, v2}, Ljava/io/File;-><init>(Ljava/io/File;Ljava/lang/String;)V

    .line 104
    invoke-virtual {v1}, Ljava/io/File;->exists()Z

    move-result v2

    if-nez v2, :cond_137

    new-instance v2, Ljava/io/File;

    new-instance v3, Ljava/lang/StringBuilder;

    invoke-direct {v3}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {v3, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    const-string v4, ".bak"

    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v3

    invoke-direct {v2, v3}, Ljava/io/File;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2}, Ljava/io/File;->exists()Z

    move-result v2

    if-nez v2, :cond_137

    new-instance v2, Ljava/io/File;

    new-instance v3, Ljava/lang/StringBuilder;

    invoke-direct {v3}, Ljava/lang/StringBuilder;-><init>()V

    invoke-virtual {v3, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;

    const-string v4, ".new"

    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v3

    invoke-direct {v2, v3}, Ljava/io/File;-><init>(Ljava/lang/String;)V

    invoke-virtual {v2}, Ljava/io/File;->exists()Z

    move-result v2

    if-nez v2, :cond_137

    new-instance v2, Ljava/io/File;

    new-instance v3, Ljava/lang/StringBuilder;

    invoke-direct {v3}, Ljava/lang/StringBuilder;-><init>()V

    iget-object v4, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->runId:Ljava/lang/String;

    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    const-string v4, ".claim"

    invoke-virtual {v3, v4}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v3}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v3

    invoke-direct {v2, v0, v3}, Ljava/io/File;-><init>(Ljava/io/File;Ljava/lang/String;)V

    .line 105
    invoke-virtual {v2}, Ljava/io/File;->createNewFile()Z

    move-result v0

    if-eqz v0, :cond_137

    .line 108
    invoke-static {}, Landroid/os/SystemClock;->elapsedRealtimeNanos()J

    move-result-wide v2

    iput-wide v2, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->createdElapsed:J

    .line 109
    new-instance v0, Landroid/util/AtomicFile;

    invoke-direct {v0, v1}, Landroid/util/AtomicFile;-><init>(Ljava/io/File;)V

    iput-object v0, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->evidence:Landroid/util/AtomicFile;

    .line 110
    const-string v0, "created"

    const/4 v1, -0x1

    const/4 v2, 0x0

    invoke-direct {p0, v0, v2, v1, v2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V
    :try_end_ca
    .catch Ljava/lang/Exception; {:try_start_23 .. :try_end_ca} :catch_13f

    .line 116
    new-instance v0, Landroid/widget/LinearLayout;

    invoke-direct {v0, p0}, Landroid/widget/LinearLayout;-><init>(Landroid/content/Context;)V

    const/4 v2, 0x1

    .line 117
    invoke-virtual {v0, v2}, Landroid/widget/LinearLayout;->setOrientation(I)V

    const/16 v3, 0x18

    .line 118
    invoke-virtual {v0, v3, v3, v3, v3}, Landroid/widget/LinearLayout;->setPadding(IIII)V

    .line 119
    invoke-virtual {v0, p1}, Landroid/widget/LinearLayout;->addView(Landroid/view/View;)V

    .line 120
    new-instance p1, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    invoke-direct {p1, p0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;-><init>(Lorg/droidloom/qa/editorcontract/EditorContractActivity;)V

    iput-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    const v3, 0x100901

    .line 121
    invoke-virtual {p1, v3}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->setId(I)V

    .line 122
    iget-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    const-string v3, "Owned editor contract"

    invoke-virtual {p1, v3}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->setHint(Ljava/lang/CharSequence;)V

    .line 123
    iget-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    invoke-virtual {p1, v2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->setInputType(I)V

    .line 124
    iget-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    invoke-virtual {p1, v2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->setSingleLine(Z)V

    .line 125
    iget-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    const/4 v2, 0x3

    invoke-virtual {p1, v2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->setImeOptions(I)V

    .line 126
    iget-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    const/4 v2, 0x0

    invoke-virtual {p1, v2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->setSaveEnabled(Z)V

    .line 127
    iget-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    new-instance v2, Lorg/droidloom/qa/editorcontract/EditorContractActivity$0;

    invoke-direct {v2, p0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$0;-><init>(Lorg/droidloom/qa/editorcontract/EditorContractActivity;)V

    invoke-virtual {p1, v2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->setOnEditorActionListener(Landroid/widget/TextView$OnEditorActionListener;)V

    .line 133
    iget-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    new-instance v2, Lorg/droidloom/qa/editorcontract/EditorContractActivity$1;

    invoke-direct {v2, p0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$1;-><init>(Lorg/droidloom/qa/editorcontract/EditorContractActivity;)V

    invoke-virtual {p1, v2}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->setOnFocusChangeListener(Landroid/view/View$OnFocusChangeListener;)V

    .line 134
    iget-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    new-instance v2, Landroid/widget/LinearLayout$LayoutParams;

    const/4 v3, -0x2

    invoke-direct {v2, v1, v3}, Landroid/widget/LinearLayout$LayoutParams;-><init>(II)V

    invoke-virtual {v0, p1, v2}, Landroid/widget/LinearLayout;->addView(Landroid/view/View;Landroid/view/ViewGroup$LayoutParams;)V

    .line 136
    invoke-virtual {p0, v0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->setContentView(Landroid/view/View;)V

    .line 137
    iget-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    invoke-virtual {p1}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->requestFocus()Z

    .line 138
    iget-object p1, p0, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->editor:Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;

    new-instance v0, Lorg/droidloom/qa/editorcontract/EditorContractActivity$2;

    invoke-direct {v0, p0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$2;-><init>(Lorg/droidloom/qa/editorcontract/EditorContractActivity;)V

    invoke-virtual {p1, v0}, Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;->post(Ljava/lang/Runnable;)Z

    return-void

    .line 106
    :cond_137
    :try_start_137
    new-instance v0, Ljava/lang/Exception;

    const-string v1, "run_identifier_already_used"

    invoke-direct {v0, v1}, Ljava/lang/Exception;-><init>(Ljava/lang/String;)V

    throw v0
    :try_end_13f
    .catch Ljava/lang/Exception; {:try_start_137 .. :try_end_13f} :catch_13f

    .line 112
    :catch_13f
    const-string v0, "Setup did not complete; do not retry this run identifier"

    invoke-virtual {p1, v0}, Landroid/widget/TextView;->setText(Ljava/lang/CharSequence;)V

    .line 113
    invoke-virtual {p0, p1}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->setContentView(Landroid/view/View;)V

    return-void

    .line 96
    :cond_148
    const-string v0, "A unique run identifier is required"

    invoke-virtual {p1, v0}, Landroid/widget/TextView;->setText(Ljava/lang/CharSequence;)V

    .line 97
    invoke-virtual {p0, p1}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->setContentView(Landroid/view/View;)V

    return-void
.end method

.method public onWindowFocusChanged(Z)V
    .registers 5

    .line 147
    invoke-super {p0, p1}, Landroid/app/Activity;->onWindowFocusChanged(Z)V

    .line 148
    const-string v0, "focused"

    invoke-static {v0, p1}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->detail(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p1

    const-string v0, "window_focus"

    const/4 v1, 0x0

    const/4 v2, -0x1

    invoke-direct {p0, v0, v1, v2, p1}, Lorg/droidloom/qa/editorcontract/EditorContractActivity;->record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V

    return-void
.end method
