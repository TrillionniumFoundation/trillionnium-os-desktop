.class public final Llocal/pocket4/actions/v2/ActionRunner;
.super Landroid/app/Instrumentation;
.source "ActionRunner.java"


# instance fields
.field private actionAttempted:Z

.field private arguments:Landroid/os/Bundle;

.field private manager:Landroid/view/accessibility/AccessibilityManager;

.field private nullChildren:I

.field private final retained:Ljava/util/List;
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "Ljava/util/List<",
            "Landroid/view/accessibility/AccessibilityNodeInfo;",
            ">;"
        }
    .end annotation
.end field

.field private final retainedWindows:Ljava/util/List;
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "Ljava/util/List<",
            "Landroid/view/accessibility/AccessibilityWindowInfo;",
            ">;"
        }
    .end annotation
.end field

.field private truncated:Z

.field private ui:Landroid/app/UiAutomation;

.field private visible:I

.field private visited:I


# direct methods
.method public constructor <init>()V
    .registers 2

    .line 22
    invoke-direct {p0}, Landroid/app/Instrumentation;-><init>()V

    .line 25
    new-instance v0, Ljava/util/ArrayList;

    invoke-direct {v0}, Ljava/util/ArrayList;-><init>()V

    iput-object v0, p0, Llocal/pocket4/actions/v2/ActionRunner;->retained:Ljava/util/List;

    .line 26
    new-instance v0, Ljava/util/ArrayList;

    invoke-direct {v0}, Ljava/util/ArrayList;-><init>()V

    iput-object v0, p0, Llocal/pocket4/actions/v2/ActionRunner;->retainedWindows:Ljava/util/List;

    return-void
.end method

.method private static bounds(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONArray;
    .registers 5
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Ljava/lang/Exception;
        }
    .end annotation

    .line 35
    new-instance v0, Landroid/graphics/Rect;

    invoke-direct {v0}, Landroid/graphics/Rect;-><init>()V

    invoke-virtual {p0, v0}, Landroid/view/accessibility/AccessibilityNodeInfo;->getBoundsInScreen(Landroid/graphics/Rect;)V

    new-instance p0, Lorg/json/JSONArray;

    iget v1, v0, Landroid/graphics/Rect;->left:I

    iget v2, v0, Landroid/graphics/Rect;->top:I

    iget v3, v0, Landroid/graphics/Rect;->right:I

    iget v0, v0, Landroid/graphics/Rect;->bottom:I

    filled-new-array {v1, v2, v3, v0}, [I

    move-result-object v0

    invoke-direct {p0, v0}, Lorg/json/JSONArray;-><init>(Ljava/lang/Object;)V

    return-object p0
.end method

.method private collect(Landroid/view/accessibility/AccessibilityNodeInfo;Ljava/util/List;IZ)V
    .registers 11
    .annotation system Ldalvik/annotation/Signature;
        value = {
            "(",
            "Landroid/view/accessibility/AccessibilityNodeInfo;",
            "Ljava/util/List<",
            "Landroid/view/accessibility/AccessibilityNodeInfo;",
            ">;IZ)V"
        }
    .end annotation

    .line 59
    const/4 v0, 0x1

    if-nez p1, :cond_9

    iget p1, p0, Llocal/pocket4/actions/v2/ActionRunner;->nullChildren:I

    add-int/2addr p1, v0

    iput p1, p0, Llocal/pocket4/actions/v2/ActionRunner;->nullChildren:I

    return-void

    :cond_9
    iget-object v1, p0, Llocal/pocket4/actions/v2/ActionRunner;->retained:Ljava/util/List;

    invoke-interface {v1, p1}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    .line 60
    const/16 v1, 0x64

    if-ge p3, v1, :cond_50

    iget v1, p0, Llocal/pocket4/actions/v2/ActionRunner;->visited:I

    const/16 v2, 0x7d0

    if-lt v1, v2, :cond_19

    goto :goto_50

    :cond_19
    iget v1, p0, Llocal/pocket4/actions/v2/ActionRunner;->visited:I

    add-int/2addr v1, v0

    iput v1, p0, Llocal/pocket4/actions/v2/ActionRunner;->visited:I

    .line 61
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isVisibleToUser()Z

    move-result v1

    if-eqz v1, :cond_2d

    iget v1, p0, Llocal/pocket4/actions/v2/ActionRunner;->visible:I

    add-int/2addr v1, v0

    iput v1, p0, Llocal/pocket4/actions/v2/ActionRunner;->visible:I

    :goto_29
    invoke-interface {p2, p1}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    goto :goto_30

    :cond_2d
    if-eqz p4, :cond_30

    goto :goto_29

    .line 62
    :cond_30
    :goto_30
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getChildCount()I

    move-result v1

    if-le v1, v2, :cond_39

    iput-boolean v0, p0, Llocal/pocket4/actions/v2/ActionRunner;->truncated:Z

    return-void

    .line 63
    :cond_39
    const/4 v3, 0x0

    :goto_3a
    if-ge v3, v1, :cond_4f

    iget v4, p0, Llocal/pocket4/actions/v2/ActionRunner;->visited:I

    if-lt v4, v2, :cond_43

    iput-boolean v0, p0, Llocal/pocket4/actions/v2/ActionRunner;->truncated:Z

    goto :goto_4f

    :cond_43
    invoke-virtual {p1, v3}, Landroid/view/accessibility/AccessibilityNodeInfo;->getChild(I)Landroid/view/accessibility/AccessibilityNodeInfo;

    move-result-object v4

    add-int/lit8 v5, p3, 0x1

    invoke-direct {p0, v4, p2, v5, p4}, Llocal/pocket4/actions/v2/ActionRunner;->collect(Landroid/view/accessibility/AccessibilityNodeInfo;Ljava/util/List;IZ)V

    add-int/lit8 v3, v3, 0x1

    goto :goto_3a

    .line 64
    :cond_4f
    :goto_4f
    return-void

    .line 60
    :cond_50
    :goto_50
    iput-boolean v0, p0, Llocal/pocket4/actions/v2/ActionRunner;->truncated:Z

    return-void
.end method

.method private describe(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONObject;
    .registers 9
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Ljava/lang/Exception;
        }
    .end annotation

    .line 45
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isPassword()Z

    move-result v0

    new-instance v1, Landroid/graphics/Rect;

    invoke-direct {v1}, Landroid/graphics/Rect;-><init>()V

    invoke-virtual {p1, v1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getBoundsInScreen(Landroid/graphics/Rect;)V

    .line 46
    new-instance v2, Lorg/json/JSONArray;

    invoke-direct {v2}, Lorg/json/JSONArray;-><init>()V

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getActionList()Ljava/util/List;

    move-result-object v3

    invoke-interface {v3}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v3

    :goto_19
    invoke-interface {v3}, Ljava/util/Iterator;->hasNext()Z

    move-result v4

    if-eqz v4, :cond_2d

    invoke-interface {v3}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v4

    check-cast v4, Landroid/view/accessibility/AccessibilityNodeInfo$AccessibilityAction;

    invoke-virtual {v4}, Landroid/view/accessibility/AccessibilityNodeInfo$AccessibilityAction;->getId()I

    move-result v4

    invoke-virtual {v2, v4}, Lorg/json/JSONArray;->put(I)Lorg/json/JSONArray;

    goto :goto_19

    .line 47
    :cond_2d
    new-instance v3, Lorg/json/JSONObject;

    invoke-direct {v3}, Lorg/json/JSONObject;-><init>()V

    const-string v4, ""

    if-eqz v0, :cond_38

    move-object v5, v4

    goto :goto_40

    :cond_38
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getText()Ljava/lang/CharSequence;

    move-result-object v5

    invoke-static {v5}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v5

    :goto_40
    const-string v6, "text"

    invoke-virtual {v3, v6, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    if-eqz v0, :cond_4a

    move-object v5, v4

    goto :goto_52

    :cond_4a
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getHintText()Ljava/lang/CharSequence;

    move-result-object v5

    invoke-static {v5}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v5

    :goto_52
    const-string v6, "hint"

    invoke-virtual {v3, v6, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    .line 48
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isShowingHintText()Z

    move-result v5

    const-string v6, "showing-hint"

    invoke-virtual {v3, v6, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v3

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isEditable()Z

    move-result v5

    if-eqz v5, :cond_6f

    if-nez v0, :cond_6f

    invoke-static {p1}, Llocal/pocket4/actions/v2/ActionRunner;->editableValue(Landroid/view/accessibility/AccessibilityNodeInfo;)Ljava/lang/String;

    move-result-object v5

    goto :goto_71

    :cond_6f
    sget-object v5, Lorg/json/JSONObject;->NULL:Ljava/lang/Object;

    :goto_71
    const-string v6, "value"

    invoke-virtual {v3, v6, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    .line 49
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getViewIdResourceName()Ljava/lang/String;

    move-result-object v5

    invoke-static {v5}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v5

    const-string v6, "resource-id"

    invoke-virtual {v3, v6, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    if-eqz v0, :cond_88

    goto :goto_90

    :cond_88
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getContentDescription()Ljava/lang/CharSequence;

    move-result-object v4

    invoke-static {v4}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v4

    :goto_90
    const-string v5, "content-desc"

    invoke-virtual {v3, v5, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    .line 50
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getPackageName()Ljava/lang/CharSequence;

    move-result-object v4

    invoke-static {v4}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v4

    const-string v5, "package"

    invoke-virtual {v3, v5, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getClassName()Ljava/lang/CharSequence;

    move-result-object v4

    invoke-static {v4}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v4

    const-string v5, "class"

    invoke-virtual {v3, v5, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    const-string v4, "window_id"

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getWindowId()I

    move-result v5

    invoke-virtual {v3, v4, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v3

    .line 51
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isEnabled()Z

    move-result v4

    const-string v5, "enabled"

    invoke-virtual {v3, v5, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v3

    const-string v4, "focused"

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isFocused()Z

    move-result v5

    invoke-virtual {v3, v4, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v3

    const-string v4, "editable"

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isEditable()Z

    move-result v5

    invoke-virtual {v3, v4, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v3

    .line 52
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isClickable()Z

    move-result v4

    const-string v5, "clickable"

    invoke-virtual {v3, v5, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v3

    const-string v4, "password"

    invoke-virtual {v3, v4, v0}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    const-string v3, "visible"

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isVisibleToUser()Z

    move-result v4

    invoke-virtual {v0, v3, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    .line 53
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isScrollable()Z

    move-result v3

    const-string v4, "scrollable"

    invoke-virtual {v0, v4, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    const-string v3, "selected"

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isSelected()Z

    move-result v4

    invoke-virtual {v0, v3, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    const-string v3, "checked"

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isChecked()Z

    move-result v4

    invoke-virtual {v0, v3, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    .line 54
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isImportantForAccessibility()Z

    move-result v3

    const-string v4, "important_for_accessibility"

    invoke-virtual {v0, v4, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    const-string v3, "supported_actions"

    invoke-virtual {v0, v3, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v0

    .line 55
    invoke-static {p1}, Llocal/pocket4/actions/v2/ActionRunner;->bounds(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONArray;

    move-result-object p1

    const-string v2, "bounds_array"

    invoke-virtual {v0, v2, p1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object p1

    new-instance v0, Ljava/lang/StringBuilder;

    invoke-direct {v0}, Ljava/lang/StringBuilder;-><init>()V

    const-string v2, "["

    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v0

    iget v2, v1, Landroid/graphics/Rect;->left:I

    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v0

    const-string v2, ","

    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v0

    iget v3, v1, Landroid/graphics/Rect;->top:I

    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v0

    const-string v3, "]["

    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v0

    iget v3, v1, Landroid/graphics/Rect;->right:I

    invoke-virtual {v0, v3}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v0

    invoke-virtual {v0, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v0

    iget v1, v1, Landroid/graphics/Rect;->bottom:I

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v0

    const-string v1, "]"

    invoke-virtual {v0, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v0

    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v0

    const-string v1, "bounds"

    invoke-virtual {p1, v1, v0}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object p1

    .line 56
    const-string v0, "source"

    const-string v1, "native_accessibility"

    invoke-virtual {p1, v0, v1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object p1

    .line 47
    return-object p1
.end method

.method private static editableValue(Landroid/view/accessibility/AccessibilityNodeInfo;)Ljava/lang/String;
    .registers 2

    .line 37
    invoke-virtual {p0}, Landroid/view/accessibility/AccessibilityNodeInfo;->isShowingHintText()Z

    move-result v0

    if-eqz v0, :cond_9

    const-string p0, ""

    goto :goto_11

    :cond_9
    invoke-virtual {p0}, Landroid/view/accessibility/AccessibilityNodeInfo;->getText()Ljava/lang/CharSequence;

    move-result-object p0

    invoke-static {p0}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object p0

    :goto_11
    return-object p0
.end method

.method private execute(Lorg/json/JSONObject;)Lorg/json/JSONObject;
    .registers 30
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Ljava/lang/Exception;
        }
    .end annotation

    .line 107
    move-object/from16 v0, p0

    move-object/from16 v1, p1

    const-string v2, "op"

    invoke-virtual {v1, v2}, Lorg/json/JSONObject;->getString(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2

    const-string v9, "scroll-forward"

    const-string v10, "scroll-backward"

    const-string v3, "meta"

    const-string v4, "dump"

    const-string v5, "find"

    const-string v6, "click"

    const-string v7, "set-text"

    const-string v8, "type-text"

    filled-new-array/range {v3 .. v10}, [Ljava/lang/String;

    move-result-object v3

    invoke-static {v3}, Ljava/util/Arrays;->asList([Ljava/lang/Object;)Ljava/util/List;

    move-result-object v3

    invoke-interface {v3, v2}, Ljava/util/List;->contains(Ljava/lang/Object;)Z

    move-result v3

    const-string v4, "UNSUPPORTED_UI_ACTION"

    invoke-static {v3, v4}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 108
    const-string v3, "display"

    const/4 v4, 0x0

    invoke-virtual {v1, v3, v4}, Lorg/json/JSONObject;->optInt(Ljava/lang/String;I)I

    move-result v3

    if-nez v3, :cond_36

    const/4 v6, 0x1

    goto :goto_37

    :cond_36
    move v6, v4

    :goto_37
    const-string v7, "ONLY_DEFAULT_DISPLAY_SUPPORTED"

    invoke-static {v6, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 109
    iget-object v6, v0, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v6}, Landroid/app/UiAutomation;->clearCache()Z

    iget-object v6, v0, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v6}, Landroid/app/UiAutomation;->getWindowsOnAllDisplays()Landroid/util/SparseArray;

    move-result-object v6

    .line 110
    new-instance v7, Lorg/json/JSONArray;

    invoke-direct {v7}, Lorg/json/JSONArray;-><init>()V

    .line 111
    invoke-virtual {v6, v3}, Landroid/util/SparseArray;->get(I)Ljava/lang/Object;

    move-result-object v6

    check-cast v6, Ljava/util/List;

    .line 112
    const-string v8, "root"

    const-string v9, "bounds"

    const-string v10, "display_id"

    const-string v11, "focused"

    if-eqz v6, :cond_10d

    invoke-interface {v6}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v6

    move v13, v4

    const/4 v14, 0x0

    const/4 v15, 0x0

    :goto_63
    invoke-interface {v6}, Ljava/util/Iterator;->hasNext()Z

    move-result v16

    if-eqz v16, :cond_106

    invoke-interface {v6}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v16

    move-object/from16 v12, v16

    check-cast v12, Landroid/view/accessibility/AccessibilityWindowInfo;

    iget-object v4, v0, Llocal/pocket4/actions/v2/ActionRunner;->retainedWindows:Ljava/util/List;

    invoke-interface {v4, v12}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    new-instance v4, Landroid/graphics/Rect;

    invoke-direct {v4}, Landroid/graphics/Rect;-><init>()V

    invoke-virtual {v12, v4}, Landroid/view/accessibility/AccessibilityWindowInfo;->getBoundsInScreen(Landroid/graphics/Rect;)V

    .line 113
    invoke-virtual {v12}, Landroid/view/accessibility/AccessibilityWindowInfo;->getRoot()Landroid/view/accessibility/AccessibilityNodeInfo;

    move-result-object v5

    if-eqz v5, :cond_8c

    move-object/from16 v19, v6

    iget-object v6, v0, Llocal/pocket4/actions/v2/ActionRunner;->retained:Ljava/util/List;

    invoke-interface {v6, v5}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    goto :goto_8e

    :cond_8c
    move-object/from16 v19, v6

    .line 114
    :goto_8e
    new-instance v6, Lorg/json/JSONObject;

    invoke-direct {v6}, Lorg/json/JSONObject;-><init>()V

    move-object/from16 v20, v12

    const-string v12, "window_id"

    move/from16 v21, v13

    invoke-virtual/range {v20 .. v20}, Landroid/view/accessibility/AccessibilityWindowInfo;->getId()I

    move-result v13

    invoke-virtual {v6, v12, v13}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v6

    invoke-virtual/range {v20 .. v20}, Landroid/view/accessibility/AccessibilityWindowInfo;->getDisplayId()I

    move-result v12

    invoke-virtual {v6, v10, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v6

    .line 115
    invoke-virtual/range {v20 .. v20}, Landroid/view/accessibility/AccessibilityWindowInfo;->isActive()Z

    move-result v12

    const-string v13, "active"

    invoke-virtual {v6, v13, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v6

    invoke-virtual/range {v20 .. v20}, Landroid/view/accessibility/AccessibilityWindowInfo;->isFocused()Z

    move-result v12

    invoke-virtual {v6, v11, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v6

    const-string v12, "type"

    invoke-virtual/range {v20 .. v20}, Landroid/view/accessibility/AccessibilityWindowInfo;->getType()I

    move-result v13

    invoke-virtual {v6, v12, v13}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v6

    new-instance v12, Lorg/json/JSONArray;

    iget v13, v4, Landroid/graphics/Rect;->left:I

    move-object/from16 v22, v14

    iget v14, v4, Landroid/graphics/Rect;->top:I

    move-object/from16 v23, v15

    iget v15, v4, Landroid/graphics/Rect;->right:I

    iget v4, v4, Landroid/graphics/Rect;->bottom:I

    filled-new-array {v13, v14, v15, v4}, [I

    move-result-object v4

    invoke-direct {v12, v4}, Lorg/json/JSONArray;-><init>(Ljava/lang/Object;)V

    .line 116
    invoke-virtual {v6, v9, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v4

    invoke-direct {v0, v5}, Llocal/pocket4/actions/v2/ActionRunner;->rootMeta(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONObject;

    move-result-object v6

    invoke-virtual {v4, v8, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v4

    invoke-virtual {v7, v4}, Lorg/json/JSONArray;->put(Ljava/lang/Object;)Lorg/json/JSONArray;

    .line 117
    invoke-virtual/range {v20 .. v20}, Landroid/view/accessibility/AccessibilityWindowInfo;->getType()I

    move-result v6

    const/4 v12, 0x1

    if-ne v6, v12, :cond_fb

    invoke-virtual/range {v20 .. v20}, Landroid/view/accessibility/AccessibilityWindowInfo;->isFocused()Z

    move-result v6

    if-eqz v6, :cond_fb

    add-int/lit8 v13, v21, 0x1

    move-object v15, v4

    move-object v14, v5

    goto :goto_101

    .line 118
    :cond_fb
    move/from16 v13, v21

    move-object/from16 v14, v22

    move-object/from16 v15, v23

    :goto_101
    move-object/from16 v6, v19

    const/4 v4, 0x0

    goto/16 :goto_63

    .line 112
    :cond_106
    move/from16 v21, v13

    move-object/from16 v22, v14

    move-object/from16 v23, v15

    goto :goto_110

    :cond_10d
    const/4 v13, 0x0

    const/4 v14, 0x0

    const/4 v15, 0x0

    .line 120
    :goto_110
    const-string v4, "meta"

    if-nez v13, :cond_127

    invoke-virtual {v2, v4}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v5

    if-nez v5, :cond_127

    iget-object v5, v0, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v5}, Landroid/app/UiAutomation;->getRootInActiveWindow()Landroid/view/accessibility/AccessibilityNodeInfo;

    move-result-object v14

    if-eqz v14, :cond_127

    iget-object v5, v0, Llocal/pocket4/actions/v2/ActionRunner;->retained:Ljava/util/List;

    invoke-interface {v5, v14}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    .line 121
    :cond_127
    const/4 v12, 0x1

    if-gt v13, v12, :cond_12c

    const/4 v5, 0x1

    goto :goto_12d

    :cond_12c
    const/4 v5, 0x0

    :goto_12d
    const-string v6, "AMBIGUOUS_FOCUSED_WINDOW"

    invoke-static {v5, v6}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 122
    const-string v5, "expected_package"

    const-string v6, ""

    invoke-virtual {v1, v5, v6}, Lorg/json/JSONObject;->optString(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v5

    .line 123
    invoke-virtual {v5}, Ljava/lang/String;->isEmpty()Z

    move-result v6

    if-nez v6, :cond_158

    if-eqz v14, :cond_152

    invoke-virtual {v14}, Landroid/view/accessibility/AccessibilityNodeInfo;->getPackageName()Ljava/lang/CharSequence;

    move-result-object v6

    invoke-static {v6}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v6

    invoke-virtual {v5, v6}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v5

    if-eqz v5, :cond_152

    const/4 v5, 0x1

    goto :goto_153

    :cond_152
    const/4 v5, 0x0

    :goto_153
    const-string v6, "FOREGROUND_PACKAGE_MISMATCH"

    invoke-static {v5, v6}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 124
    :cond_158
    new-instance v5, Lorg/json/JSONObject;

    invoke-direct {v5}, Lorg/json/JSONObject;-><init>()V

    invoke-virtual {v5, v10, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v5

    if-nez v15, :cond_166

    sget-object v6, Lorg/json/JSONObject;->NULL:Ljava/lang/Object;

    goto :goto_167

    :cond_166
    move-object v6, v15

    :goto_167
    const-string v10, "selected_window"

    invoke-virtual {v5, v10, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v5

    .line 125
    const-string v6, "windows"

    invoke-virtual {v5, v6, v7}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v5

    invoke-direct {v0, v14}, Llocal/pocket4/actions/v2/ActionRunner;->rootMeta(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONObject;

    move-result-object v6

    invoke-virtual {v5, v8, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v5

    iget-object v6, v0, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v6}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v6

    iget v6, v6, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    const-string v7, "flags"

    invoke-virtual {v5, v7, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v5

    iget-object v6, v0, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    .line 126
    invoke-virtual {v6}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v6

    invoke-virtual {v6}, Landroid/accessibilityservice/AccessibilityServiceInfo;->getCapabilities()I

    move-result v6

    const-string v7, "capabilities"

    invoke-virtual {v5, v7, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v5

    iget-object v6, v0, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v6}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v6

    invoke-virtual {v6}, Landroid/accessibilityservice/AccessibilityServiceInfo;->isAccessibilityTool()Z

    move-result v6

    const-string v7, "is_accessibility_tool"

    invoke-virtual {v5, v7, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v5

    iget-object v6, v0, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    .line 127
    invoke-virtual {v6}, Landroid/view/accessibility/AccessibilityManager;->isEnabled()Z

    move-result v6

    const-string v7, "accessibility_enabled"

    invoke-virtual {v5, v7, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v5

    iget-object v6, v0, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    invoke-virtual {v6}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v6

    const-string v7, "touch_exploration_enabled"

    invoke-virtual {v5, v7, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v5

    .line 128
    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v6

    const-string v8, "uptime_ms"

    invoke-virtual {v5, v8, v6, v7}, Lorg/json/JSONObject;->put(Ljava/lang/String;J)Lorg/json/JSONObject;

    move-result-object v5

    .line 129
    invoke-virtual {v2, v4}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v4

    const-string v6, "window_context"

    const-string v7, "ok"

    if-eqz v4, :cond_1e4

    new-instance v1, Lorg/json/JSONObject;

    invoke-direct {v1}, Lorg/json/JSONObject;-><init>()V

    const/4 v12, 0x1

    invoke-virtual {v1, v7, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v1

    invoke-virtual {v1, v6, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    return-object v1

    .line 130
    :cond_1e4
    if-eqz v14, :cond_1e8

    const/4 v4, 0x1

    goto :goto_1e9

    :cond_1e8
    const/4 v4, 0x0

    :goto_1e9
    const-string v8, "NO_ACTIVE_WINDOW"

    invoke-static {v4, v8}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    new-instance v4, Ljava/util/ArrayList;

    invoke-direct {v4}, Ljava/util/ArrayList;-><init>()V

    .line 131
    const-string v8, "include_invisible"

    const/4 v10, 0x0

    invoke-virtual {v1, v8, v10}, Lorg/json/JSONObject;->optBoolean(Ljava/lang/String;Z)Z

    move-result v8

    invoke-direct {v0, v14, v4, v10, v8}, Llocal/pocket4/actions/v2/ActionRunner;->collect(Landroid/view/accessibility/AccessibilityNodeInfo;Ljava/util/List;IZ)V

    .line 132
    const-string v8, "visited_count"

    iget v10, v0, Llocal/pocket4/actions/v2/ActionRunner;->visited:I

    invoke-virtual {v5, v8, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v8

    const-string v10, "visible_count"

    iget v12, v0, Llocal/pocket4/actions/v2/ActionRunner;->visible:I

    invoke-virtual {v8, v10, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v8

    const-string v10, "null_child_count"

    iget v12, v0, Llocal/pocket4/actions/v2/ActionRunner;->nullChildren:I

    invoke-virtual {v8, v10, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v8

    iget-boolean v10, v0, Llocal/pocket4/actions/v2/ActionRunner;->truncated:Z

    const-string v12, "truncated"

    invoke-virtual {v8, v12, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    .line 133
    iget v8, v0, Llocal/pocket4/actions/v2/ActionRunner;->visited:I

    const/4 v10, 0x1

    if-ne v8, v10, :cond_237

    invoke-virtual {v14}, Landroid/view/accessibility/AccessibilityNodeInfo;->getChildCount()I

    move-result v8

    if-nez v8, :cond_237

    invoke-virtual {v14}, Landroid/view/accessibility/AccessibilityNodeInfo;->getClassName()Ljava/lang/CharSequence;

    move-result-object v8

    invoke-static {v8}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v8

    invoke-virtual {v8}, Ljava/lang/String;->isEmpty()Z

    move-result v8

    if-eqz v8, :cond_237

    const/4 v8, 0x1

    goto :goto_238

    :cond_237
    const/4 v8, 0x0

    .line 134
    :goto_238
    iget v10, v0, Llocal/pocket4/actions/v2/ActionRunner;->visible:I

    if-lez v10, :cond_248

    if-nez v8, :cond_248

    iget-boolean v10, v0, Llocal/pocket4/actions/v2/ActionRunner;->truncated:Z

    if-nez v10, :cond_248

    iget v10, v0, Llocal/pocket4/actions/v2/ActionRunner;->nullChildren:I

    if-nez v10, :cond_248

    const/4 v10, 0x1

    goto :goto_249

    :cond_248
    const/4 v10, 0x0

    :goto_249
    const-string v13, "semantic_controls_available"

    invoke-virtual {v5, v13, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v10

    iget-boolean v13, v0, Llocal/pocket4/actions/v2/ActionRunner;->truncated:Z

    if-nez v13, :cond_259

    iget v13, v0, Llocal/pocket4/actions/v2/ActionRunner;->nullChildren:I

    if-nez v13, :cond_259

    const/4 v13, 0x1

    goto :goto_25a

    :cond_259
    const/4 v13, 0x0

    .line 135
    :goto_25a
    move-object/from16 v19, v4

    const-string v4, "snapshot_complete"

    invoke-virtual {v10, v4, v13}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v4

    .line 136
    iget v10, v0, Llocal/pocket4/actions/v2/ActionRunner;->nullChildren:I

    if-lez v10, :cond_269

    const-string v12, "incomplete"

    goto :goto_27c

    :cond_269
    iget-boolean v10, v0, Llocal/pocket4/actions/v2/ActionRunner;->truncated:Z

    if-eqz v10, :cond_26e

    goto :goto_27c

    :cond_26e
    if-eqz v8, :cond_273

    const-string v12, "app_exposed_empty_root"

    goto :goto_27c

    :cond_273
    iget v8, v0, Llocal/pocket4/actions/v2/ActionRunner;->visible:I

    if-nez v8, :cond_27a

    const-string v12, "no_visible_nodes"

    goto :goto_27c

    :cond_27a
    const-string v12, "available"

    :goto_27c
    const-string v8, "tree_status"

    invoke-virtual {v4, v8, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    .line 137
    const-string v4, "dump"

    invoke-virtual {v2, v4}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v4

    if-eqz v4, :cond_2bb

    new-instance v1, Lorg/json/JSONArray;

    invoke-direct {v1}, Lorg/json/JSONArray;-><init>()V

    invoke-interface/range {v19 .. v19}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v2

    :goto_292
    invoke-interface {v2}, Ljava/util/Iterator;->hasNext()Z

    move-result v3

    if-eqz v3, :cond_2a6

    invoke-interface {v2}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v3

    check-cast v3, Landroid/view/accessibility/AccessibilityNodeInfo;

    invoke-direct {v0, v3}, Llocal/pocket4/actions/v2/ActionRunner;->describe(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONObject;

    move-result-object v3

    invoke-virtual {v1, v3}, Lorg/json/JSONArray;->put(Ljava/lang/Object;)Lorg/json/JSONArray;

    goto :goto_292

    .line 138
    :cond_2a6
    new-instance v2, Lorg/json/JSONObject;

    invoke-direct {v2}, Lorg/json/JSONObject;-><init>()V

    const/4 v12, 0x1

    invoke-virtual {v2, v7, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v2

    const-string v3, "nodes"

    invoke-virtual {v2, v3, v1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    invoke-virtual {v1, v6, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    return-object v1

    .line 139
    :cond_2bb
    const-string v4, "selector"

    invoke-virtual {v1, v4}, Lorg/json/JSONObject;->optJSONObject(Ljava/lang/String;)Lorg/json/JSONObject;

    move-result-object v4

    .line 140
    const-string v8, "type-text"

    invoke-virtual {v2, v8}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v10

    const-string v12, "set-text"

    const-string v13, "editable"

    if-nez v10, :cond_2de

    invoke-virtual {v2, v12}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v10

    if-eqz v10, :cond_2dc

    if-eqz v4, :cond_2de

    invoke-virtual {v4}, Lorg/json/JSONObject;->length()I

    move-result v10

    if-nez v10, :cond_2dc

    goto :goto_2de

    .line 141
    :cond_2dc
    const/4 v10, 0x1

    goto :goto_2ec

    .line 140
    :cond_2de
    :goto_2de
    new-instance v4, Lorg/json/JSONObject;

    invoke-direct {v4}, Lorg/json/JSONObject;-><init>()V

    const/4 v10, 0x1

    invoke-virtual {v4, v11, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v4

    invoke-virtual {v4, v13, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v4

    .line 141
    :goto_2ec
    invoke-virtual {v2, v12}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v12

    const-string v10, "package"

    if-eqz v12, :cond_30d

    if-eqz v4, :cond_30d

    invoke-virtual {v4}, Lorg/json/JSONObject;->length()I

    move-result v12

    move-object/from16 v20, v14

    const/4 v14, 0x1

    if-ne v12, v14, :cond_30f

    invoke-virtual {v4, v10}, Lorg/json/JSONObject;->has(Ljava/lang/String;)Z

    move-result v12

    if-eqz v12, :cond_30f

    invoke-virtual {v4, v11, v14}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v11

    invoke-virtual {v11, v13, v14}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    goto :goto_30f

    :cond_30d
    move-object/from16 v20, v14

    .line 142
    :cond_30f
    :goto_30f
    const-string v11, "scroll-forward"

    invoke-virtual {v2, v11}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v12

    if-nez v12, :cond_322

    const-string v12, "scroll-backward"

    invoke-virtual {v2, v12}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v12

    if-eqz v12, :cond_320

    goto :goto_322

    :cond_320
    const/4 v12, 0x0

    goto :goto_323

    :cond_322
    :goto_322
    const/4 v12, 0x1

    .line 143
    :goto_323
    const-string v13, "index"

    if-eqz v12, :cond_364

    .line 144
    invoke-virtual {v1, v13}, Lorg/json/JSONObject;->has(Ljava/lang/String;)Z

    move-result v14

    const/16 v18, 0x1

    xor-int/lit8 v14, v14, 0x1

    move/from16 v21, v12

    const-string v12, "SCROLL_REQUIRES_UNIQUE_SELECTOR"

    invoke-static {v14, v12}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 145
    const-string v12, "scrollable"

    if-eqz v4, :cond_357

    invoke-virtual {v4}, Lorg/json/JSONObject;->length()I

    move-result v14

    if-nez v14, :cond_344

    move-object/from16 v22, v8

    const/4 v8, 0x1

    goto :goto_35a

    .line 146
    :cond_344
    invoke-virtual {v4}, Lorg/json/JSONObject;->length()I

    move-result v14

    move-object/from16 v22, v8

    const/4 v8, 0x1

    if-ne v14, v8, :cond_368

    invoke-virtual {v4, v10}, Lorg/json/JSONObject;->has(Ljava/lang/String;)Z

    move-result v10

    if-eqz v10, :cond_368

    invoke-virtual {v4, v12, v8}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    goto :goto_368

    .line 145
    :cond_357
    move-object/from16 v22, v8

    const/4 v8, 0x1

    :goto_35a
    new-instance v4, Lorg/json/JSONObject;

    invoke-direct {v4}, Lorg/json/JSONObject;-><init>()V

    invoke-virtual {v4, v12, v8}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v4

    goto :goto_368

    .line 143
    :cond_364
    move-object/from16 v22, v8

    move/from16 v21, v12

    .line 148
    :cond_368
    :goto_368
    if-eqz v4, :cond_372

    invoke-virtual {v4}, Lorg/json/JSONObject;->length()I

    move-result v8

    if-lez v8, :cond_372

    const/4 v8, 0x1

    goto :goto_373

    :cond_372
    const/4 v8, 0x0

    :goto_373
    const-string v10, "SELECTOR_REQUIRED"

    invoke-static {v8, v10}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    new-instance v8, Ljava/util/ArrayList;

    invoke-direct {v8}, Ljava/util/ArrayList;-><init>()V

    .line 149
    invoke-interface/range {v19 .. v19}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v10

    :cond_381
    :goto_381
    invoke-interface {v10}, Ljava/util/Iterator;->hasNext()Z

    move-result v12

    if-eqz v12, :cond_397

    invoke-interface {v10}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v12

    check-cast v12, Landroid/view/accessibility/AccessibilityNodeInfo;

    invoke-direct {v0, v12, v4}, Llocal/pocket4/actions/v2/ActionRunner;->matches(Landroid/view/accessibility/AccessibilityNodeInfo;Lorg/json/JSONObject;)Z

    move-result v14

    if-eqz v14, :cond_381

    invoke-interface {v8, v12}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    goto :goto_381

    .line 150
    :cond_397
    const-string v10, "find"

    invoke-virtual {v2, v10}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v10

    if-eqz v10, :cond_3db

    new-instance v1, Lorg/json/JSONArray;

    invoke-direct {v1}, Lorg/json/JSONArray;-><init>()V

    invoke-interface {v8}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v2

    :goto_3a8
    invoke-interface {v2}, Ljava/util/Iterator;->hasNext()Z

    move-result v3

    if-eqz v3, :cond_3bc

    invoke-interface {v2}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v3

    check-cast v3, Landroid/view/accessibility/AccessibilityNodeInfo;

    invoke-direct {v0, v3}, Llocal/pocket4/actions/v2/ActionRunner;->describe(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONObject;

    move-result-object v3

    invoke-virtual {v1, v3}, Lorg/json/JSONArray;->put(Ljava/lang/Object;)Lorg/json/JSONArray;

    goto :goto_3a8

    .line 151
    :cond_3bc
    new-instance v2, Lorg/json/JSONObject;

    invoke-direct {v2}, Lorg/json/JSONObject;-><init>()V

    const/4 v12, 0x1

    invoke-virtual {v2, v7, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v2

    const-string v3, "count"

    invoke-interface {v8}, Ljava/util/List;->size()I

    move-result v4

    invoke-virtual {v2, v3, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v2

    const-string v3, "matches"

    invoke-virtual {v2, v3, v1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    invoke-virtual {v1, v6, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    return-object v1

    .line 152
    :cond_3db
    iget-boolean v5, v0, Llocal/pocket4/actions/v2/ActionRunner;->truncated:Z

    if-nez v5, :cond_3e5

    iget v5, v0, Llocal/pocket4/actions/v2/ActionRunner;->nullChildren:I

    if-nez v5, :cond_3e5

    const/4 v5, 0x1

    goto :goto_3e6

    :cond_3e5
    const/4 v5, 0x0

    :goto_3e6
    const-string v6, "INCOMPLETE_TREE_NO_ACTION_TAKEN"

    invoke-static {v5, v6}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    invoke-interface {v8}, Ljava/util/List;->isEmpty()Z

    move-result v5

    const/4 v12, 0x1

    xor-int/2addr v5, v12

    const-string v10, "NO_MATCH"

    invoke-static {v5, v10}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 153
    invoke-virtual {v1, v13}, Lorg/json/JSONObject;->has(Ljava/lang/String;)Z

    move-result v5

    if-nez v5, :cond_405

    invoke-interface {v8}, Ljava/util/List;->size()I

    move-result v5

    if-ne v5, v12, :cond_403

    goto :goto_405

    :cond_403
    const/4 v5, 0x0

    goto :goto_406

    :cond_405
    :goto_405
    const/4 v5, 0x1

    :goto_406
    const-string v10, "AMBIGUOUS_MATCH"

    invoke-static {v5, v10}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    const/4 v10, 0x0

    invoke-virtual {v1, v13, v10}, Lorg/json/JSONObject;->optInt(Ljava/lang/String;I)I

    move-result v5

    .line 154
    if-ltz v5, :cond_41a

    invoke-interface {v8}, Ljava/util/List;->size()I

    move-result v10

    if-ge v5, v10, :cond_41a

    const/4 v10, 0x1

    goto :goto_41b

    :cond_41a
    const/4 v10, 0x0

    :goto_41b
    const-string v12, "INDEX_OUT_OF_RANGE"

    invoke-static {v10, v12}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    invoke-interface {v8, v5}, Ljava/util/List;->get(I)Ljava/lang/Object;

    move-result-object v10

    check-cast v10, Landroid/view/accessibility/AccessibilityNodeInfo;

    .line 155
    invoke-direct {v0, v10}, Llocal/pocket4/actions/v2/ActionRunner;->identity(Landroid/view/accessibility/AccessibilityNodeInfo;)Ljava/lang/String;

    move-result-object v10

    invoke-interface {v8}, Ljava/util/List;->size()I

    move-result v8

    invoke-virtual/range {v20 .. v20}, Landroid/view/accessibility/AccessibilityNodeInfo;->getWindowId()I

    move-result v12

    invoke-virtual/range {v20 .. v20}, Landroid/view/accessibility/AccessibilityNodeInfo;->getPackageName()Ljava/lang/CharSequence;

    move-result-object v14

    invoke-static {v14}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v14

    .line 156
    move-object/from16 v19, v7

    iget-object v7, v0, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v7}, Landroid/app/UiAutomation;->clearCache()Z

    .line 157
    iget-object v7, v0, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v7}, Landroid/app/UiAutomation;->getWindows()Ljava/util/List;

    move-result-object v7

    invoke-interface {v7}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v7

    move-object/from16 v20, v7

    move-object/from16 v17, v11

    const/4 v7, 0x0

    const/4 v11, 0x0

    :goto_451
    invoke-interface/range {v20 .. v20}, Ljava/util/Iterator;->hasNext()Z

    move-result v23

    move-object/from16 v24, v2

    const-string v2, "WINDOW_CHANGED_NO_ACTION_TAKEN"

    if-eqz v23, :cond_4eb

    invoke-interface/range {v20 .. v20}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v23

    move-object/from16 v25, v10

    move-object/from16 v10, v23

    check-cast v10, Landroid/view/accessibility/AccessibilityWindowInfo;

    move/from16 v23, v5

    iget-object v5, v0, Llocal/pocket4/actions/v2/ActionRunner;->retainedWindows:Ljava/util/List;

    invoke-interface {v5, v10}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    .line 158
    invoke-virtual {v10}, Landroid/view/accessibility/AccessibilityWindowInfo;->getDisplayId()I

    move-result v5

    if-ne v5, v3, :cond_4db

    invoke-virtual {v10}, Landroid/view/accessibility/AccessibilityWindowInfo;->getType()I

    move-result v5

    move/from16 v26, v3

    const/4 v3, 0x1

    if-ne v5, v3, :cond_4dd

    invoke-virtual {v10}, Landroid/view/accessibility/AccessibilityWindowInfo;->isFocused()Z

    move-result v3

    if-eqz v3, :cond_4dd

    .line 159
    add-int/lit8 v11, v11, 0x1

    invoke-virtual {v10}, Landroid/view/accessibility/AccessibilityWindowInfo;->getId()I

    move-result v3

    if-ne v3, v12, :cond_48b

    const/4 v3, 0x1

    goto :goto_48c

    :cond_48b
    const/4 v3, 0x0

    :goto_48c
    invoke-static {v3, v2}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 160
    if-eqz v15, :cond_4cc

    new-instance v2, Landroid/graphics/Rect;

    invoke-direct {v2}, Landroid/graphics/Rect;-><init>()V

    invoke-virtual {v10, v2}, Landroid/view/accessibility/AccessibilityWindowInfo;->getBoundsInScreen(Landroid/graphics/Rect;)V

    invoke-virtual {v15, v9}, Lorg/json/JSONObject;->getJSONArray(Ljava/lang/String;)Lorg/json/JSONArray;

    move-result-object v3

    .line 161
    iget v5, v2, Landroid/graphics/Rect;->left:I

    move-object/from16 v27, v9

    const/4 v7, 0x0

    invoke-virtual {v3, v7}, Lorg/json/JSONArray;->getInt(I)I

    move-result v9

    if-ne v5, v9, :cond_4c5

    iget v5, v2, Landroid/graphics/Rect;->top:I

    const/4 v7, 0x1

    invoke-virtual {v3, v7}, Lorg/json/JSONArray;->getInt(I)I

    move-result v9

    if-ne v5, v9, :cond_4c5

    iget v5, v2, Landroid/graphics/Rect;->right:I

    .line 162
    const/4 v7, 0x2

    invoke-virtual {v3, v7}, Lorg/json/JSONArray;->getInt(I)I

    move-result v7

    if-ne v5, v7, :cond_4c5

    iget v2, v2, Landroid/graphics/Rect;->bottom:I

    const/4 v5, 0x3

    invoke-virtual {v3, v5}, Lorg/json/JSONArray;->getInt(I)I

    move-result v3

    if-ne v2, v3, :cond_4c5

    const/4 v2, 0x1

    goto :goto_4c6

    :cond_4c5
    const/4 v2, 0x0

    .line 161
    :goto_4c6
    const-string v3, "WINDOW_BOUNDS_CHANGED_NO_ACTION_TAKEN"

    invoke-static {v2, v3}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    goto :goto_4ce

    .line 160
    :cond_4cc
    move-object/from16 v27, v9

    .line 163
    :goto_4ce
    invoke-virtual {v10}, Landroid/view/accessibility/AccessibilityWindowInfo;->getRoot()Landroid/view/accessibility/AccessibilityNodeInfo;

    move-result-object v2

    if-eqz v2, :cond_4d9

    iget-object v3, v0, Llocal/pocket4/actions/v2/ActionRunner;->retained:Ljava/util/List;

    invoke-interface {v3, v2}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    :cond_4d9
    move-object v7, v2

    goto :goto_4df

    .line 158
    :cond_4db
    move/from16 v26, v3

    :cond_4dd
    move-object/from16 v27, v9

    .line 163
    :goto_4df
    move/from16 v5, v23

    move-object/from16 v2, v24

    move-object/from16 v10, v25

    move/from16 v3, v26

    move-object/from16 v9, v27

    goto/16 :goto_451

    .line 164
    :cond_4eb
    move/from16 v23, v5

    move-object/from16 v25, v10

    const/4 v12, 0x1

    if-ne v11, v12, :cond_504

    if-eqz v7, :cond_504

    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo;->getPackageName()Ljava/lang/CharSequence;

    move-result-object v3

    invoke-static {v3}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v3

    invoke-virtual {v3, v14}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-eqz v3, :cond_504

    const/4 v3, 0x1

    goto :goto_505

    :cond_504
    const/4 v3, 0x0

    :goto_505
    invoke-static {v3, v2}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 165
    const/4 v10, 0x0

    iput v10, v0, Llocal/pocket4/actions/v2/ActionRunner;->nullChildren:I

    iput v10, v0, Llocal/pocket4/actions/v2/ActionRunner;->visible:I

    iput v10, v0, Llocal/pocket4/actions/v2/ActionRunner;->visited:I

    iput-boolean v10, v0, Llocal/pocket4/actions/v2/ActionRunner;->truncated:Z

    new-instance v2, Ljava/util/ArrayList;

    invoke-direct {v2}, Ljava/util/ArrayList;-><init>()V

    invoke-direct {v0, v7, v2, v10, v10}, Llocal/pocket4/actions/v2/ActionRunner;->collect(Landroid/view/accessibility/AccessibilityNodeInfo;Ljava/util/List;IZ)V

    .line 166
    iget-boolean v3, v0, Llocal/pocket4/actions/v2/ActionRunner;->truncated:Z

    if-nez v3, :cond_523

    iget v3, v0, Llocal/pocket4/actions/v2/ActionRunner;->nullChildren:I

    if-nez v3, :cond_523

    const/4 v3, 0x1

    goto :goto_524

    :cond_523
    const/4 v3, 0x0

    :goto_524
    invoke-static {v3, v6}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    new-instance v3, Ljava/util/ArrayList;

    invoke-direct {v3}, Ljava/util/ArrayList;-><init>()V

    .line 167
    invoke-interface {v2}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v2

    :cond_530
    :goto_530
    invoke-interface {v2}, Ljava/util/Iterator;->hasNext()Z

    move-result v5

    if-eqz v5, :cond_546

    invoke-interface {v2}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v5

    check-cast v5, Landroid/view/accessibility/AccessibilityNodeInfo;

    invoke-direct {v0, v5, v4}, Llocal/pocket4/actions/v2/ActionRunner;->matches(Landroid/view/accessibility/AccessibilityNodeInfo;Lorg/json/JSONObject;)Z

    move-result v6

    if-eqz v6, :cond_530

    invoke-interface {v3, v5}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    goto :goto_530

    .line 168
    :cond_546
    invoke-interface {v3}, Ljava/util/List;->isEmpty()Z

    move-result v2

    const/4 v12, 0x1

    xor-int/2addr v2, v12

    const-string v5, "TARGET_CHANGED_NO_ACTION_TAKEN"

    invoke-static {v2, v5}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 169
    invoke-virtual {v1, v13}, Lorg/json/JSONObject;->has(Ljava/lang/String;)Z

    move-result v2

    if-nez v2, :cond_568

    invoke-interface {v3}, Ljava/util/List;->size()I

    move-result v2

    if-ne v2, v12, :cond_55f

    const/4 v2, 0x1

    goto :goto_560

    :cond_55f
    const/4 v2, 0x0

    :goto_560
    const-string v6, "AMBIGUOUS_MATCH_NO_ACTION_TAKEN"

    invoke-static {v2, v6}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    move/from16 v6, v23

    goto :goto_580

    .line 170
    :cond_568
    invoke-interface {v3}, Ljava/util/List;->size()I

    move-result v2

    if-ne v2, v8, :cond_578

    invoke-interface {v3}, Ljava/util/List;->size()I

    move-result v2

    move/from16 v6, v23

    if-ge v6, v2, :cond_57a

    const/4 v2, 0x1

    goto :goto_57b

    :cond_578
    move/from16 v6, v23

    :cond_57a
    const/4 v2, 0x0

    :goto_57b
    const-string v7, "MATCH_SET_CHANGED_NO_ACTION_TAKEN"

    invoke-static {v2, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 171
    :goto_580
    invoke-interface {v3, v6}, Ljava/util/List;->get(I)Ljava/lang/Object;

    move-result-object v2

    check-cast v2, Landroid/view/accessibility/AccessibilityNodeInfo;

    invoke-direct {v0, v2}, Llocal/pocket4/actions/v2/ActionRunner;->identity(Landroid/view/accessibility/AccessibilityNodeInfo;)Ljava/lang/String;

    move-result-object v3

    move-object/from16 v6, v25

    invoke-virtual {v3, v6}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    invoke-static {v3, v5}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 172
    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->refresh()Z

    move-result v3

    if-eqz v3, :cond_5a1

    invoke-direct {v0, v2, v4}, Llocal/pocket4/actions/v2/ActionRunner;->matches(Landroid/view/accessibility/AccessibilityNodeInfo;Lorg/json/JSONObject;)Z

    move-result v3

    if-eqz v3, :cond_5a1

    const/4 v3, 0x1

    goto :goto_5a2

    :cond_5a1
    const/4 v3, 0x0

    :goto_5a2
    invoke-static {v3, v5}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 173
    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->isVisibleToUser()Z

    move-result v3

    if-eqz v3, :cond_5b3

    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->isEnabled()Z

    move-result v3

    if-eqz v3, :cond_5b3

    const/4 v3, 0x1

    goto :goto_5b4

    :cond_5b3
    const/4 v3, 0x0

    :goto_5b4
    const-string v4, "TARGET_NOT_VISIBLE_OR_ENABLED"

    invoke-static {v3, v4}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 174
    const-string v3, "click"

    move-object/from16 v4, v24

    invoke-virtual {v4, v3}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-eqz v3, :cond_5f1

    .line 175
    const-string v3, "method"

    const-string v5, "accessibility"

    invoke-virtual {v1, v3, v5}, Lorg/json/JSONObject;->optString(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v3

    const-string v5, "accessibility"

    invoke-virtual {v3, v5}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v5

    if-nez v5, :cond_5de

    const-string v5, "mouse"

    invoke-virtual {v3, v5}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v5

    if-eqz v5, :cond_5dc

    goto :goto_5de

    :cond_5dc
    const/4 v5, 0x0

    goto :goto_5df

    :cond_5de
    :goto_5de
    const/4 v5, 0x1

    :goto_5df
    const-string v6, "INVALID_CLICK_METHOD"

    invoke-static {v5, v6}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 176
    const-string v5, "mouse"

    invoke-virtual {v3, v5}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-eqz v3, :cond_5f1

    invoke-direct {v0, v2, v15}, Llocal/pocket4/actions/v2/ActionRunner;->mouseClick(Landroid/view/accessibility/AccessibilityNodeInfo;Lorg/json/JSONObject;)Lorg/json/JSONObject;

    move-result-object v1

    return-object v1

    .line 178
    :cond_5f1
    const-string v3, "performed"

    if-eqz v21, :cond_666

    .line 179
    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->isScrollable()Z

    move-result v1

    const-string v5, "TARGET_NOT_SCROLLABLE"

    invoke-static {v1, v5}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    move-object/from16 v1, v17

    invoke-virtual {v4, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_609

    const/16 v1, 0x1000

    goto :goto_60b

    :cond_609
    const/16 v1, 0x2000

    .line 180
    :goto_60b
    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->getActionList()Ljava/util/List;

    move-result-object v5

    invoke-interface {v5}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v5

    const/4 v6, 0x0

    :cond_614
    :goto_614
    invoke-interface {v5}, Ljava/util/Iterator;->hasNext()Z

    move-result v7

    if-eqz v7, :cond_628

    invoke-interface {v5}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v7

    check-cast v7, Landroid/view/accessibility/AccessibilityNodeInfo$AccessibilityAction;

    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo$AccessibilityAction;->getId()I

    move-result v7

    if-ne v7, v1, :cond_614

    const/4 v6, 0x1

    goto :goto_614

    .line 181
    :cond_628
    const-string v5, "SCROLL_ACTION_NOT_SUPPORTED"

    invoke-static {v6, v5}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    invoke-direct {v0, v2}, Llocal/pocket4/actions/v2/ActionRunner;->describe(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONObject;

    move-result-object v5

    const/4 v12, 0x1

    iput-boolean v12, v0, Llocal/pocket4/actions/v2/ActionRunner;->actionAttempted:Z

    .line 182
    invoke-virtual {v2, v1}, Landroid/view/accessibility/AccessibilityNodeInfo;->performAction(I)Z

    move-result v1

    const-string v2, "SCROLL_REJECTED"

    invoke-static {v1, v2}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 183
    new-instance v1, Lorg/json/JSONObject;

    invoke-direct {v1}, Lorg/json/JSONObject;-><init>()V

    move-object/from16 v6, v19

    invoke-virtual {v1, v6, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v1

    invoke-virtual {v1, v3, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    const-string v2, "target"

    invoke-virtual {v1, v2, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    const-string v2, "actual_target"

    invoke-virtual {v1, v2, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    .line 184
    const-string v2, "visual_verified"

    const/4 v10, 0x0

    invoke-virtual {v1, v2, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v1

    const-string v2, "business_success_verified"

    invoke-virtual {v1, v2, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v1

    .line 183
    return-object v1

    .line 186
    :cond_666
    move-object/from16 v6, v19

    const-string v5, "click"

    invoke-virtual {v4, v5}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v5

    if-eqz v5, :cond_71a

    invoke-direct {v0, v2}, Llocal/pocket4/actions/v2/ActionRunner;->describe(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONObject;

    move-result-object v1

    move-object v7, v2

    const/4 v5, 0x0

    .line 187
    :goto_676
    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo;->isClickable()Z

    move-result v8

    if-nez v8, :cond_6c7

    add-int/lit8 v8, v5, 0x1

    const/16 v9, 0x64

    if-ge v5, v9, :cond_684

    const/4 v5, 0x1

    goto :goto_685

    :cond_684
    const/4 v5, 0x0

    :goto_685
    const-string v9, "CLICK_ANCESTOR_LIMIT"

    invoke-static {v5, v9}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo;->getParent()Landroid/view/accessibility/AccessibilityNodeInfo;

    move-result-object v7

    .line 188
    if-eqz v7, :cond_692

    const/4 v5, 0x1

    goto :goto_693

    :cond_692
    const/4 v5, 0x0

    :goto_693
    const-string v9, "TARGET_NOT_CLICKABLE"

    invoke-static {v5, v9}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    iget-object v5, v0, Llocal/pocket4/actions/v2/ActionRunner;->retained:Ljava/util/List;

    invoke-interface {v5, v7}, Ljava/util/List;->add(Ljava/lang/Object;)Z

    .line 189
    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo;->getWindowId()I

    move-result v5

    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->getWindowId()I

    move-result v9

    if-ne v5, v9, :cond_6bf

    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo;->getPackageName()Ljava/lang/CharSequence;

    move-result-object v5

    invoke-static {v5}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v5

    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->getPackageName()Ljava/lang/CharSequence;

    move-result-object v9

    invoke-static {v9}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v9

    invoke-virtual {v5, v9}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v5

    if-eqz v5, :cond_6bf

    const/4 v5, 0x1

    goto :goto_6c0

    :cond_6bf
    const/4 v5, 0x0

    :goto_6c0
    const-string v9, "ANCESTOR_SCOPE_MISMATCH"

    invoke-static {v5, v9}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    move v5, v8

    goto :goto_676

    .line 190
    :cond_6c7
    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo;->refresh()Z

    move-result v2

    if-eqz v2, :cond_6db

    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo;->isVisibleToUser()Z

    move-result v2

    if-eqz v2, :cond_6db

    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo;->isEnabled()Z

    move-result v2

    if-eqz v2, :cond_6db

    const/4 v2, 0x1

    goto :goto_6dc

    :cond_6db
    const/4 v2, 0x0

    :goto_6dc
    const-string v5, "CLICK_ANCESTOR_CHANGED"

    invoke-static {v2, v5}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 191
    invoke-direct {v0, v7}, Llocal/pocket4/actions/v2/ActionRunner;->describe(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONObject;

    move-result-object v2

    const/4 v12, 0x1

    iput-boolean v12, v0, Llocal/pocket4/actions/v2/ActionRunner;->actionAttempted:Z

    const/16 v5, 0x10

    invoke-virtual {v7, v5}, Landroid/view/accessibility/AccessibilityNodeInfo;->performAction(I)Z

    move-result v5

    const-string v7, "CLICK_REJECTED"

    invoke-static {v5, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 192
    new-instance v5, Lorg/json/JSONObject;

    invoke-direct {v5}, Lorg/json/JSONObject;-><init>()V

    invoke-virtual {v5, v6, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v5

    invoke-virtual {v5, v3, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    const-string v4, "target"

    invoke-virtual {v3, v4, v1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    const-string v3, "actual_target"

    invoke-virtual {v1, v3, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    .line 193
    const-string v2, "visual_verified"

    const/4 v10, 0x0

    invoke-virtual {v1, v2, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v1

    const-string v2, "business_success_verified"

    invoke-virtual {v1, v2, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v1

    .line 192
    return-object v1

    .line 194
    :cond_71a
    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->isEditable()Z

    move-result v5

    const-string v7, "TARGET_NOT_EDITABLE"

    invoke-static {v5, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    const-string v5, "value"

    invoke-virtual {v1, v5}, Lorg/json/JSONObject;->getString(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v1

    .line 195
    move-object/from16 v5, v22

    invoke-virtual {v4, v5}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v5

    if-eqz v5, :cond_753

    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->isPassword()Z

    move-result v5

    const/16 v18, 0x1

    xor-int/lit8 v5, v5, 0x1

    const-string v7, "CANNOT_APPEND_TO_MASKED_PASSWORD"

    invoke-static {v5, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    new-instance v5, Ljava/lang/StringBuilder;

    invoke-direct {v5}, Ljava/lang/StringBuilder;-><init>()V

    invoke-static {v2}, Llocal/pocket4/actions/v2/ActionRunner;->editableValue(Landroid/view/accessibility/AccessibilityNodeInfo;)Ljava/lang/String;

    move-result-object v7

    invoke-virtual {v5, v7}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v5

    invoke-virtual {v5, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    .line 196
    :cond_753
    sget-object v5, Ljava/nio/charset/StandardCharsets;->UTF_8:Ljava/nio/charset/Charset;

    invoke-virtual {v1, v5}, Ljava/lang/String;->getBytes(Ljava/nio/charset/Charset;)[B

    move-result-object v5

    array-length v5, v5

    const/16 v7, 0x1000

    if-gt v5, v7, :cond_760

    const/4 v5, 0x1

    goto :goto_761

    :cond_760
    const/4 v5, 0x0

    :goto_761
    const-string v7, "TEXT_TOO_LARGE"

    invoke-static {v5, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 197
    new-instance v5, Landroid/os/Bundle;

    invoke-direct {v5}, Landroid/os/Bundle;-><init>()V

    const-string v7, "ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE"

    invoke-virtual {v5, v7, v1}, Landroid/os/Bundle;->putCharSequence(Ljava/lang/String;Ljava/lang/CharSequence;)V

    .line 198
    const/4 v12, 0x1

    iput-boolean v12, v0, Llocal/pocket4/actions/v2/ActionRunner;->actionAttempted:Z

    const/high16 v7, 0x200000

    invoke-virtual {v2, v7, v5}, Landroid/view/accessibility/AccessibilityNodeInfo;->performAction(ILandroid/os/Bundle;)Z

    move-result v5

    const-string v7, "SET_TEXT_REJECTED"

    invoke-static {v5, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 199
    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->isPassword()Z

    move-result v5

    const/4 v10, 0x0

    if-nez v5, :cond_7aa

    :goto_785
    const/16 v5, 0x14

    if-ge v10, v5, :cond_7a3

    const-wide/16 v7, 0x32

    invoke-static {v7, v8}, Landroid/os/SystemClock;->sleep(J)V

    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->refresh()Z

    move-result v5

    if-eqz v5, :cond_7a0

    invoke-static {v2}, Llocal/pocket4/actions/v2/ActionRunner;->editableValue(Landroid/view/accessibility/AccessibilityNodeInfo;)Ljava/lang/String;

    move-result-object v5

    invoke-virtual {v5, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v5

    if-eqz v5, :cond_7a0

    const/4 v12, 0x1

    goto :goto_7a4

    :cond_7a0
    add-int/lit8 v10, v10, 0x1

    goto :goto_785

    :cond_7a3
    const/4 v12, 0x0

    .line 200
    :goto_7a4
    const-string v5, "TEXT_READBACK_MISMATCH_ACTION_MAY_HAVE_OCCURRED"

    invoke-static {v12, v5}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    move v10, v12

    .line 201
    :cond_7aa
    new-instance v5, Lorg/json/JSONObject;

    invoke-direct {v5}, Lorg/json/JSONObject;-><init>()V

    const/4 v12, 0x1

    invoke-virtual {v5, v6, v12}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v5

    invoke-virtual {v5, v3, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    invoke-virtual {v1}, Ljava/lang/String;->length()I

    move-result v4

    const/4 v7, 0x0

    invoke-virtual {v1, v7, v4}, Ljava/lang/String;->codePointCount(II)I

    move-result v1

    const-string v4, "characters"

    invoke-virtual {v3, v4, v1}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v1

    .line 202
    const-string v3, "readback_verified"

    invoke-virtual {v1, v3, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v1

    const-string v3, "password"

    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->isPassword()Z

    move-result v2

    invoke-virtual {v1, v3, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v1

    .line 201
    return-object v1
.end method

.method private identity(Landroid/view/accessibility/AccessibilityNodeInfo;)Ljava/lang/String;
    .registers 7
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Ljava/lang/Exception;
        }
    .end annotation

    .line 81
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isPassword()Z

    move-result v0

    new-instance v1, Lorg/json/JSONObject;

    invoke-direct {v1}, Lorg/json/JSONObject;-><init>()V

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getPackageName()Ljava/lang/CharSequence;

    move-result-object v2

    invoke-static {v2}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v2

    const-string v3, "package"

    invoke-virtual {v1, v3, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    const-string v2, "window"

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getWindowId()I

    move-result v3

    invoke-virtual {v1, v2, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v1

    .line 82
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getClassName()Ljava/lang/CharSequence;

    move-result-object v2

    invoke-static {v2}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v2

    const-string v3, "class"

    invoke-virtual {v1, v3, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getViewIdResourceName()Ljava/lang/String;

    move-result-object v2

    invoke-static {v2}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v2

    const-string v3, "id"

    invoke-virtual {v1, v3, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    const-string v2, "bounds"

    invoke-static {p1}, Llocal/pocket4/actions/v2/ActionRunner;->bounds(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONArray;

    move-result-object v3

    invoke-virtual {v1, v2, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    .line 83
    const-string v2, ""

    if-eqz v0, :cond_4d

    move-object v3, v2

    goto :goto_55

    :cond_4d
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getText()Ljava/lang/CharSequence;

    move-result-object v3

    invoke-static {v3}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v3

    :goto_55
    const-string v4, "text"

    invoke-virtual {v1, v4, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    if-eqz v0, :cond_5e

    goto :goto_66

    :cond_5e
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getContentDescription()Ljava/lang/CharSequence;

    move-result-object v2

    invoke-static {v2}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v2

    :goto_66
    const-string v3, "desc"

    invoke-virtual {v1, v3, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v1

    .line 84
    const-string v2, "password"

    invoke-virtual {v1, v2, v0}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "editable"

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isEditable()Z

    move-result v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "clickable"

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isClickable()Z

    move-result p1

    invoke-virtual {v0, v1, p1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p1

    invoke-virtual {p1}, Lorg/json/JSONObject;->toString()Ljava/lang/String;

    move-result-object p1

    .line 81
    return-object p1
.end method

.method private matches(Landroid/view/accessibility/AccessibilityNodeInfo;Lorg/json/JSONObject;)Z
    .registers 9
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Ljava/lang/Exception;
        }
    .end annotation

    .line 66
    invoke-virtual {p2}, Lorg/json/JSONObject;->keys()Ljava/util/Iterator;

    move-result-object v0

    :cond_4
    :goto_4
    invoke-interface {v0}, Ljava/util/Iterator;->hasNext()Z

    move-result v1

    const/4 v2, 0x1

    if-eqz v1, :cond_140

    invoke-interface {v0}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v1

    check-cast v1, Ljava/lang/String;

    invoke-virtual {p2, v1}, Lorg/json/JSONObject;->get(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object v3

    invoke-static {v3}, Ljava/lang/String;->valueOf(Ljava/lang/Object;)Ljava/lang/String;

    move-result-object v3

    .line 67
    invoke-virtual {v1}, Ljava/lang/String;->hashCode()I

    move-result v4

    const/4 v5, 0x0

    sparse-switch v4, :sswitch_data_142

    :cond_21
    goto/16 :goto_ac

    :sswitch_23
    const-string v2, "editable"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    const/4 v2, 0x7

    goto/16 :goto_ad

    :sswitch_2e
    const-string v2, "selected"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    const/16 v2, 0xb

    goto/16 :goto_ad

    :sswitch_3a
    const-string v2, "checked"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    const/16 v2, 0xc

    goto/16 :goto_ad

    :sswitch_46
    const-string v2, "class"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    const/4 v2, 0x4

    goto :goto_ad

    :sswitch_50
    const-string v2, "scrollable"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    const/16 v2, 0xa

    goto :goto_ad

    :sswitch_5b
    const-string v2, "text"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    move v2, v5

    goto :goto_ad

    :sswitch_65
    const-string v2, "desc"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    const/4 v2, 0x3

    goto :goto_ad

    :sswitch_6f
    const-string v2, "id"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    const/4 v2, 0x2

    goto :goto_ad

    :sswitch_79
    const-string v4, "contains"

    invoke-virtual {v1, v4}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    goto :goto_ad

    :sswitch_82
    const-string v2, "focused"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    const/4 v2, 0x6

    goto :goto_ad

    :sswitch_8c
    const-string v2, "package"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    const/4 v2, 0x5

    goto :goto_ad

    :sswitch_96
    const-string v2, "enabled"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    const/16 v2, 0x8

    goto :goto_ad

    :sswitch_a1
    const-string v2, "clickable"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :cond_21

    const/16 v2, 0x9

    goto :goto_ad

    :goto_ac
    const/4 v2, -0x1

    :goto_ad
    packed-switch v2, :pswitch_data_178

    .line 76
    new-instance p1, Ljava/lang/IllegalArgumentException;

    const-string p2, "UNKNOWN_SELECTOR"

    invoke-direct {p1, p2}, Ljava/lang/IllegalArgumentException;-><init>(Ljava/lang/String;)V

    throw p1

    :pswitch_b8
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isChecked()Z

    move-result v1

    invoke-static {v1}, Ljava/lang/String;->valueOf(Z)Ljava/lang/String;

    move-result-object v1

    goto/16 :goto_137

    .line 75
    :pswitch_c2
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isSelected()Z

    move-result v1

    goto :goto_cb

    :pswitch_c7
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isScrollable()Z

    move-result v1

    :goto_cb
    invoke-static {v1}, Ljava/lang/String;->valueOf(Z)Ljava/lang/String;

    move-result-object v1

    goto :goto_137

    .line 74
    :pswitch_d0
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isClickable()Z

    move-result v1

    goto :goto_d9

    :pswitch_d5
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isEnabled()Z

    move-result v1

    :goto_d9
    invoke-static {v1}, Ljava/lang/String;->valueOf(Z)Ljava/lang/String;

    move-result-object v1

    goto :goto_137

    .line 73
    :pswitch_de
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isEditable()Z

    move-result v1

    goto :goto_e7

    :pswitch_e3
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isFocused()Z

    move-result v1

    :goto_e7
    invoke-static {v1}, Ljava/lang/String;->valueOf(Z)Ljava/lang/String;

    move-result-object v1

    goto :goto_137

    .line 72
    :pswitch_ec
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getPackageName()Ljava/lang/CharSequence;

    move-result-object v1

    goto :goto_f5

    :pswitch_f1
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getClassName()Ljava/lang/CharSequence;

    move-result-object v1

    :goto_f5
    invoke-static {v1}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v1

    goto :goto_137

    .line 71
    :pswitch_fa
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isPassword()Z

    move-result v1

    if-eqz v1, :cond_101

    return v5

    :cond_101
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getContentDescription()Ljava/lang/CharSequence;

    move-result-object v1

    invoke-static {v1}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v1

    goto :goto_137

    .line 70
    :pswitch_10a
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getViewIdResourceName()Ljava/lang/String;

    move-result-object v1

    invoke-static {v1}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v1

    goto :goto_137

    .line 69
    :pswitch_113
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isPassword()Z

    move-result v1

    if-nez v1, :cond_127

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getText()Ljava/lang/CharSequence;

    move-result-object v1

    invoke-static {v1}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v1

    invoke-virtual {v1, v3}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v1

    if-nez v1, :cond_4

    :cond_127
    return v5

    .line 68
    :pswitch_128
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isPassword()Z

    move-result v1

    if-eqz v1, :cond_12f

    return v5

    :cond_12f
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getText()Ljava/lang/CharSequence;

    move-result-object v1

    invoke-static {v1}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v1

    .line 77
    :goto_137
    invoke-virtual {v1, v3}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-nez v1, :cond_13e

    return v5

    .line 78
    :cond_13e
    goto/16 :goto_4

    :cond_140
    return v2

    nop

    :sswitch_data_142
    .sparse-switch
        -0x751aa91e -> :sswitch_a1
        -0x5ff074bf -> :sswitch_96
        -0x301acbba -> :sswitch_8c
        -0x29307489 -> :sswitch_82
        -0x21d289e1 -> :sswitch_79
        0xd1b -> :sswitch_6f
        0x2efe91 -> :sswitch_65
        0x36452d -> :sswitch_5b
        0x3f94da7 -> :sswitch_50
        0x5a5a978 -> :sswitch_46
        0x2c3ecfa7 -> :sswitch_3a
        0x4705f29b -> :sswitch_2e
        0x5f82ee64 -> :sswitch_23
    .end sparse-switch

    :pswitch_data_178
    .packed-switch 0x0
        :pswitch_128
        :pswitch_113
        :pswitch_10a
        :pswitch_fa
        :pswitch_f1
        :pswitch_ec
        :pswitch_e3
        :pswitch_de
        :pswitch_d5
        :pswitch_d0
        :pswitch_c7
        :pswitch_c2
        :pswitch_b8
    .end packed-switch
.end method

.method private mouseClick(Landroid/view/accessibility/AccessibilityNodeInfo;Lorg/json/JSONObject;)Lorg/json/JSONObject;
    .registers 28
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Ljava/lang/Exception;
        }
    .end annotation

    .line 87
    move-object/from16 v1, p0

    move-object/from16 v0, p2

    new-instance v2, Landroid/graphics/Rect;

    invoke-direct {v2}, Landroid/graphics/Rect;-><init>()V

    move-object/from16 v3, p1

    invoke-virtual {v3, v2}, Landroid/view/accessibility/AccessibilityNodeInfo;->getBoundsInScreen(Landroid/graphics/Rect;)V

    invoke-virtual {v2}, Landroid/graphics/Rect;->width()I

    move-result v4

    const/4 v5, 0x0

    const/4 v6, 0x1

    if-lez v4, :cond_1e

    invoke-virtual {v2}, Landroid/graphics/Rect;->height()I

    move-result v4

    if-lez v4, :cond_1e

    move v4, v6

    goto :goto_1f

    :cond_1e
    move v4, v5

    :goto_1f
    const-string v7, "TARGET_HAS_NO_SCREEN_BOUNDS"

    invoke-static {v4, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 88
    invoke-virtual {v2}, Landroid/graphics/Rect;->centerX()I

    move-result v4

    invoke-virtual {v2}, Landroid/graphics/Rect;->centerY()I

    move-result v2

    if-eqz v0, :cond_30

    move v7, v6

    goto :goto_31

    :cond_30
    move v7, v5

    :goto_31
    const-string v8, "NO_VERIFIED_FOCUSED_APPLICATION_WINDOW"

    invoke-static {v7, v8}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    const-string v7, "bounds"

    invoke-virtual {v0, v7}, Lorg/json/JSONObject;->getJSONArray(Ljava/lang/String;)Lorg/json/JSONArray;

    move-result-object v0

    .line 89
    invoke-virtual {v0, v5}, Lorg/json/JSONArray;->getInt(I)I

    move-result v7

    const/4 v8, 0x3

    if-lt v4, v7, :cond_58

    invoke-virtual {v0, v6}, Lorg/json/JSONArray;->getInt(I)I

    move-result v7

    if-lt v2, v7, :cond_58

    const/4 v7, 0x2

    invoke-virtual {v0, v7}, Lorg/json/JSONArray;->getInt(I)I

    move-result v7

    if-ge v4, v7, :cond_58

    invoke-virtual {v0, v8}, Lorg/json/JSONArray;->getInt(I)I

    move-result v0

    if-ge v2, v0, :cond_58

    move v0, v6

    goto :goto_59

    :cond_58
    move v0, v5

    :goto_59
    const-string v7, "MOUSE_TARGET_OUTSIDE_WINDOW"

    invoke-static {v0, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 90
    new-instance v0, Landroid/view/MotionEvent$PointerProperties;

    invoke-direct {v0}, Landroid/view/MotionEvent$PointerProperties;-><init>()V

    iput v5, v0, Landroid/view/MotionEvent$PointerProperties;->id:I

    iput v8, v0, Landroid/view/MotionEvent$PointerProperties;->toolType:I

    .line 91
    new-instance v7, Landroid/view/MotionEvent$PointerCoords;

    invoke-direct {v7}, Landroid/view/MotionEvent$PointerCoords;-><init>()V

    int-to-float v8, v4

    iput v8, v7, Landroid/view/MotionEvent$PointerCoords;->x:F

    int-to-float v8, v2

    iput v8, v7, Landroid/view/MotionEvent$PointerCoords;->y:F

    const/high16 v8, 0x3f800000    # 1.0f

    iput v8, v7, Landroid/view/MotionEvent$PointerCoords;->pressure:F

    iput v8, v7, Landroid/view/MotionEvent$PointerCoords;->size:F

    .line 92
    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v9

    .line 94
    new-array v15, v6, [Landroid/view/MotionEvent$PointerProperties;

    aput-object v0, v15, v5

    new-array v8, v6, [Landroid/view/MotionEvent$PointerCoords;

    aput-object v7, v8, v5

    const/16 v23, 0x2002

    const/16 v24, 0x0

    const/4 v13, 0x0

    const/4 v14, 0x1

    const/16 v17, 0x0

    const/16 v18, 0x1

    const/high16 v19, 0x3f800000    # 1.0f

    const/high16 v20, 0x3f800000    # 1.0f

    const/16 v21, 0x0

    const/16 v22, 0x0

    move-wide v11, v9

    move-object/from16 v16, v8

    invoke-static/range {v9 .. v24}, Landroid/view/MotionEvent;->obtain(JJII[Landroid/view/MotionEvent$PointerProperties;[Landroid/view/MotionEvent$PointerCoords;IIFFIIII)Landroid/view/MotionEvent;

    move-result-object v8

    .line 96
    const/4 v11, 0x0

    iput v11, v7, Landroid/view/MotionEvent$PointerCoords;->pressure:F

    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v11

    new-array v15, v6, [Landroid/view/MotionEvent$PointerProperties;

    aput-object v0, v15, v5

    new-array v0, v6, [Landroid/view/MotionEvent$PointerCoords;

    aput-object v7, v0, v5

    const/4 v13, 0x1

    const/16 v18, 0x0

    move-object/from16 v16, v0

    invoke-static/range {v9 .. v24}, Landroid/view/MotionEvent;->obtain(JJII[Landroid/view/MotionEvent$PointerProperties;[Landroid/view/MotionEvent$PointerCoords;IIFFIIII)Landroid/view/MotionEvent;

    move-result-object v7

    .line 98
    iput-boolean v6, v1, Llocal/pocket4/actions/v2/ActionRunner;->actionAttempted:Z

    .line 99
    :try_start_b7
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v0, v8, v6}, Landroid/app/UiAutomation;->injectInputEvent(Landroid/view/InputEvent;Z)Z

    move-result v0
    :try_end_bd
    .catchall {:try_start_b7 .. :try_end_bd} :catchall_124

    :try_start_bd
    iget-object v9, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v9, v7, v6}, Landroid/app/UiAutomation;->injectInputEvent(Landroid/view/InputEvent;Z)Z

    move-result v9
    :try_end_c3
    .catchall {:try_start_bd .. :try_end_c3} :catchall_12b

    .line 100
    invoke-virtual {v8}, Landroid/view/MotionEvent;->recycle()V

    invoke-virtual {v7}, Landroid/view/MotionEvent;->recycle()V

    .line 101
    if-eqz v0, :cond_cf

    if-eqz v9, :cond_cf

    move v0, v6

    goto :goto_d0

    :cond_cf
    move v0, v5

    :goto_d0
    const-string v7, "MOUSE_INPUT_REJECTED"

    invoke-static {v0, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    invoke-direct/range {p0 .. p1}, Llocal/pocket4/actions/v2/ActionRunner;->describe(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONObject;

    move-result-object v0

    .line 102
    new-instance v3, Lorg/json/JSONObject;

    invoke-direct {v3}, Lorg/json/JSONObject;-><init>()V

    const-string v7, "ok"

    invoke-virtual {v3, v7, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v3

    const-string v6, "performed"

    const-string v7, "click"

    invoke-virtual {v3, v6, v7}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    const-string v6, "method"

    const-string v7, "mouse"

    invoke-virtual {v3, v6, v7}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    const-string v6, "source"

    const-string v7, "native_bounds_mouse"

    invoke-virtual {v3, v6, v7}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v3

    new-instance v6, Lorg/json/JSONArray;

    filled-new-array {v4, v2}, [I

    move-result-object v2

    invoke-direct {v6, v2}, Lorg/json/JSONArray;-><init>(Ljava/lang/Object;)V

    .line 103
    const-string v2, "coordinates"

    invoke-virtual {v3, v2, v6}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v2

    const-string v3, "target"

    invoke-virtual {v2, v3, v0}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v2

    const-string v3, "actual_target"

    invoke-virtual {v2, v3, v0}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v0

    .line 104
    const-string v2, "visual_verified"

    invoke-virtual {v0, v2, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    const-string v2, "business_success_verified"

    invoke-virtual {v0, v2, v5}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    .line 102
    return-object v0

    .line 99
    :catchall_124
    move-exception v0

    :try_start_125
    iget-object v2, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v2, v7, v6}, Landroid/app/UiAutomation;->injectInputEvent(Landroid/view/InputEvent;Z)Z

    throw v0
    :try_end_12b
    .catchall {:try_start_125 .. :try_end_12b} :catchall_12b

    .line 100
    :catchall_12b
    move-exception v0

    invoke-virtual {v8}, Landroid/view/MotionEvent;->recycle()V

    invoke-virtual {v7}, Landroid/view/MotionEvent;->recycle()V

    throw v0
.end method

.method private static require(ZLjava/lang/String;)V
    .registers 2

    .line 33
    if-eqz p0, :cond_3

    return-void

    :cond_3
    new-instance p0, Ljava/lang/IllegalArgumentException;

    invoke-direct {p0, p1}, Ljava/lang/IllegalArgumentException;-><init>(Ljava/lang/String;)V

    throw p0
.end method

.method private rootMeta(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONObject;
    .registers 5
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Ljava/lang/Exception;
        }
    .end annotation

    .line 39
    const-string v0, "present"

    if-nez p1, :cond_f

    new-instance p1, Lorg/json/JSONObject;

    invoke-direct {p1}, Lorg/json/JSONObject;-><init>()V

    const/4 v1, 0x0

    invoke-virtual {p1, v0, v1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object p1

    return-object p1

    .line 40
    :cond_f
    new-instance v1, Lorg/json/JSONObject;

    invoke-direct {v1}, Lorg/json/JSONObject;-><init>()V

    const/4 v2, 0x1

    invoke-virtual {v1, v0, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getPackageName()Ljava/lang/CharSequence;

    move-result-object v1

    invoke-static {v1}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v1

    const-string v2, "package"

    invoke-virtual {v0, v2, v1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v0

    .line 41
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getClassName()Ljava/lang/CharSequence;

    move-result-object v1

    invoke-static {v1}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v1

    const-string v2, "class"

    invoke-virtual {v0, v2, v1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "window_id"

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getWindowId()I

    move-result v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "bounds"

    invoke-static {p1}, Llocal/pocket4/actions/v2/ActionRunner;->bounds(Landroid/view/accessibility/AccessibilityNodeInfo;)Lorg/json/JSONArray;

    move-result-object v2

    invoke-virtual {v0, v1, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v0

    .line 42
    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->isVisibleToUser()Z

    move-result v1

    const-string v2, "visible"

    invoke-virtual {v0, v2, v1}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    const-string v1, "child_count"

    invoke-virtual {p1}, Landroid/view/accessibility/AccessibilityNodeInfo;->getChildCount()I

    move-result p1

    invoke-virtual {v0, v1, p1}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object p1

    .line 40
    return-object p1
.end method

.method private static str(Ljava/lang/CharSequence;)Ljava/lang/String;
    .registers 1

    .line 32
    if-nez p0, :cond_5

    const-string p0, ""

    goto :goto_9

    :cond_5
    invoke-interface {p0}, Ljava/lang/CharSequence;->toString()Ljava/lang/String;

    move-result-object p0

    :goto_9
    return-object p0
.end method


# virtual methods
.method public onCreate(Landroid/os/Bundle;)V
    .registers 2

    .line 31
    invoke-super {p0, p1}, Landroid/app/Instrumentation;->onCreate(Landroid/os/Bundle;)V

    iput-object p1, p0, Llocal/pocket4/actions/v2/ActionRunner;->arguments:Landroid/os/Bundle;

    invoke-virtual {p0}, Llocal/pocket4/actions/v2/ActionRunner;->start()V

    return-void
.end method

.method public onStart()V
    .registers 24

    .line 204
    move-object/from16 v1, p0

    const-string v0, ""

    const-string v2, "touch_exploration_after"

    const-string v3, "restored_flags"

    const-string v4, "accessibility_mode"

    const-string v5, "accessibility_mode_restoration_verified"

    new-instance v6, Lorg/json/JSONObject;

    invoke-direct {v6}, Lorg/json/JSONObject;-><init>()V

    .line 205
    const-string v7, "none"

    .line 206
    const/4 v13, 0x1

    const/4 v14, 0x0

    :try_start_15
    iget-object v15, v1, Llocal/pocket4/actions/v2/ActionRunner;->arguments:Landroid/os/Bundle;
    :try_end_17
    .catchall {:try_start_15 .. :try_end_17} :catchall_238

    const-wide/16 v16, 0x32

    :try_start_19
    const-string v9, "request"

    invoke-virtual {v15, v9, v0}, Landroid/os/Bundle;->getString(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v9

    invoke-virtual {v9}, Ljava/lang/String;->length()I

    move-result v10

    const v15, 0x15f90

    if-gt v10, v15, :cond_2a

    move v10, v13

    goto :goto_2b

    :cond_2a
    move v10, v14

    :goto_2b
    const-string v15, "REQUEST_TOO_LARGE"

    invoke-static {v10, v15}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 207
    new-instance v10, Lorg/json/JSONObject;

    new-instance v15, Ljava/lang/String;

    invoke-static {v9, v14}, Landroid/util/Base64;->decode(Ljava/lang/String;I)[B

    move-result-object v9
    :try_end_38
    .catchall {:try_start_19 .. :try_end_38} :catchall_236

    const/16 v18, 0x2

    :try_start_3a
    sget-object v8, Ljava/nio/charset/StandardCharsets;->UTF_8:Ljava/nio/charset/Charset;

    invoke-direct {v15, v9, v8}, Ljava/lang/String;-><init>([BLjava/nio/charset/Charset;)V

    invoke-direct {v10, v15}, Lorg/json/JSONObject;-><init>(Ljava/lang/String;)V

    .line 208
    invoke-virtual {v1, v13}, Llocal/pocket4/actions/v2/ActionRunner;->getUiAutomation(I)Landroid/app/UiAutomation;

    move-result-object v8

    iput-object v8, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    iget-object v8, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v8}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v8

    .line 209
    invoke-virtual {v1}, Llocal/pocket4/actions/v2/ActionRunner;->getContext()Landroid/content/Context;

    move-result-object v9

    const-string v15, "accessibility"

    invoke-virtual {v9, v15}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;

    move-result-object v9

    check-cast v9, Landroid/view/accessibility/AccessibilityManager;

    iput-object v9, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    .line 210
    iget v9, v8, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I
    :try_end_5e
    .catchall {:try_start_3a .. :try_end_5e} :catchall_234

    :try_start_5e
    iget-object v15, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    invoke-virtual {v15}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v15
    :try_end_64
    .catchall {:try_start_5e .. :try_end_64} :catchall_230

    .line 211
    :try_start_64
    iget v13, v8, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    or-int/lit8 v13, v13, 0x52

    iput v13, v8, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    .line 212
    const-string v13, "accessibilityMode"

    invoke-virtual {v10, v4, v7}, Lorg/json/JSONObject;->optString(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v14

    invoke-virtual {v10, v13, v14}, Lorg/json/JSONObject;->optString(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v13
    :try_end_74
    .catchall {:try_start_64 .. :try_end_74} :catchall_22c

    :try_start_74
    invoke-virtual {v13, v7}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v7
    :try_end_78
    .catchall {:try_start_74 .. :try_end_78} :catchall_22a

    const-string v14, "touch-exploration"

    if-nez v7, :cond_85

    :try_start_7c
    invoke-virtual {v13, v14}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v7

    if-eqz v7, :cond_83

    goto :goto_85

    :cond_83
    const/4 v7, 0x0

    goto :goto_86

    :cond_85
    :goto_85
    const/4 v7, 0x1

    :goto_86
    const-string v11, "INVALID_ACCESSIBILITY_MODE"

    invoke-static {v7, v11}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 213
    invoke-virtual {v13, v14}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v7
    :try_end_8f
    .catchall {:try_start_7c .. :try_end_8f} :catchall_22a

    const-string v11, "com.tencent.mm"

    if-eqz v7, :cond_e4

    .line 214
    :try_start_93
    const-string v7, "expected_package"

    invoke-virtual {v10, v7, v0}, Lorg/json/JSONObject;->optString(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    invoke-virtual {v0, v11}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v0

    const-string v7, "TOUCH_EXPLORATION_REQUIRES_EXPLICIT_WECHAT_SCOPE"

    invoke-static {v0, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 215
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v0}, Landroid/app/UiAutomation;->getRootInActiveWindow()Landroid/view/accessibility/AccessibilityNodeInfo;

    move-result-object v7
    :try_end_a8
    .catchall {:try_start_93 .. :try_end_a8} :catchall_22a

    .line 216
    if-eqz v7, :cond_bc

    :try_start_aa
    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo;->getPackageName()Ljava/lang/CharSequence;

    move-result-object v0

    invoke-static {v0}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v0

    invoke-virtual {v0, v11}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_bc

    const/4 v0, 0x1

    goto :goto_bd

    .line 217
    :catchall_ba
    move-exception v0

    goto :goto_de

    .line 216
    :cond_bc
    const/4 v0, 0x0

    :goto_bd
    const-string v12, "FOREGROUND_PACKAGE_MISMATCH"

    invoke-static {v0, v12}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V
    :try_end_c2
    .catchall {:try_start_aa .. :try_end_c2} :catchall_ba

    .line 217
    if-eqz v7, :cond_c7

    :try_start_c4
    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo;->recycle()V

    .line 218
    :cond_c7
    invoke-virtual {v8}, Landroid/accessibilityservice/AccessibilityServiceInfo;->getCapabilities()I

    move-result v0

    and-int/lit8 v0, v0, 0x2

    if-eqz v0, :cond_d1

    const/4 v0, 0x1

    goto :goto_d2

    :cond_d1
    const/4 v0, 0x0

    :goto_d2
    const-string v7, "TOUCH_EXPLORATION_CAPABILITY_MISSING"

    invoke-static {v0, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    .line 219
    iget v0, v8, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    or-int/lit8 v0, v0, 0x4

    iput v0, v8, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    goto :goto_e4

    .line 217
    :goto_de
    if-eqz v7, :cond_e3

    invoke-virtual {v7}, Landroid/view/accessibility/AccessibilityNodeInfo;->recycle()V

    :cond_e3
    throw v0

    .line 221
    :cond_e4
    :goto_e4
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v0, v8}, Landroid/app/UiAutomation;->setServiceInfo(Landroid/accessibilityservice/AccessibilityServiceInfo;)V

    .line 222
    invoke-virtual {v13, v14}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :cond_171

    .line 223
    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v7

    const-wide/32 v21, 0x9470

    add-long v7, v7, v21

    .line 224
    :cond_f8
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v0}, Landroid/app/UiAutomation;->clearCache()Z

    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v0}, Landroid/app/UiAutomation;->getRootInActiveWindow()Landroid/view/accessibility/AccessibilityNodeInfo;

    move-result-object v12
    :try_end_103
    .catchall {:try_start_c4 .. :try_end_103} :catchall_22a

    .line 225
    :try_start_103
    new-instance v0, Landroid/graphics/Rect;

    invoke-direct {v0}, Landroid/graphics/Rect;-><init>()V

    if-eqz v12, :cond_10d

    invoke-virtual {v12, v0}, Landroid/view/accessibility/AccessibilityNodeInfo;->getBoundsInScreen(Landroid/graphics/Rect;)V

    .line 226
    :cond_10d
    iget-object v14, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    invoke-virtual {v14}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v14

    if-eqz v14, :cond_14d

    if-eqz v12, :cond_14d

    invoke-virtual {v12}, Landroid/view/accessibility/AccessibilityNodeInfo;->getPackageName()Ljava/lang/CharSequence;

    move-result-object v14

    invoke-static {v14}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v14

    invoke-virtual {v14, v11}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v14

    if-eqz v14, :cond_14d

    .line 227
    invoke-virtual {v12}, Landroid/view/accessibility/AccessibilityNodeInfo;->getClassName()Ljava/lang/CharSequence;

    move-result-object v14

    invoke-static {v14}, Llocal/pocket4/actions/v2/ActionRunner;->str(Ljava/lang/CharSequence;)Ljava/lang/String;

    move-result-object v14

    invoke-virtual {v14}, Ljava/lang/String;->isEmpty()Z

    move-result v14

    if-nez v14, :cond_14d

    invoke-virtual {v12}, Landroid/view/accessibility/AccessibilityNodeInfo;->getChildCount()I

    move-result v14

    if-lez v14, :cond_14d

    invoke-virtual {v12}, Landroid/view/accessibility/AccessibilityNodeInfo;->isVisibleToUser()Z

    move-result v14

    if-eqz v14, :cond_14d

    .line 228
    invoke-virtual {v0}, Landroid/graphics/Rect;->width()I

    move-result v14

    if-lez v14, :cond_14d

    invoke-virtual {v0}, Landroid/graphics/Rect;->height()I

    move-result v0
    :try_end_149
    .catchall {:try_start_103 .. :try_end_149} :catchall_16a

    if-lez v0, :cond_14d

    const/4 v0, 0x1

    goto :goto_14e

    :cond_14d
    const/4 v0, 0x0

    .line 229
    :goto_14e
    if-eqz v12, :cond_153

    :try_start_150
    invoke-virtual {v12}, Landroid/view/accessibility/AccessibilityNodeInfo;->recycle()V

    :cond_153
    if-nez v0, :cond_15a

    const-wide/16 v21, 0x1f4

    invoke-static/range {v21 .. v22}, Landroid/os/SystemClock;->sleep(J)V

    :cond_15a
    if-nez v0, :cond_164

    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v21

    cmp-long v12, v21, v7

    if-ltz v12, :cond_f8

    .line 230
    :cond_164
    const-string v7, "ACCESSIBILITY_TREE_NOT_READY_NO_ACTION_TAKEN"

    invoke-static {v0, v7}, Llocal/pocket4/actions/v2/ActionRunner;->require(ZLjava/lang/String;)V

    goto :goto_171

    .line 229
    :catchall_16a
    move-exception v0

    if-eqz v12, :cond_170

    invoke-virtual {v12}, Landroid/view/accessibility/AccessibilityNodeInfo;->recycle()V

    :cond_170
    throw v0
    :try_end_171
    .catchall {:try_start_150 .. :try_end_171} :catchall_22a

    .line 232
    :cond_171
    :goto_171
    :try_start_171
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    const-wide/16 v7, 0x64

    const-wide/16 v11, 0x3e8

    invoke-virtual {v0, v7, v8, v11, v12}, Landroid/app/UiAutomation;->waitForIdle(JJ)V
    :try_end_17a
    .catch Ljava/util/concurrent/TimeoutException; {:try_start_171 .. :try_end_17a} :catch_17b
    .catchall {:try_start_171 .. :try_end_17a} :catchall_22a

    goto :goto_17c

    :catch_17b
    move-exception v0

    :goto_17c
    :try_start_17c
    invoke-direct {v1, v10}, Llocal/pocket4/actions/v2/ActionRunner;->execute(Lorg/json/JSONObject;)Lorg/json/JSONObject;

    move-result-object v6
    :try_end_180
    .catchall {:try_start_17c .. :try_end_180} :catchall_22a

    .line 237
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    if-eqz v0, :cond_1e8

    .line 238
    :try_start_184
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v0}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v0

    iput v9, v0, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    iget-object v7, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v7, v0}, Landroid/app/UiAutomation;->setServiceInfo(Landroid/accessibilityservice/AccessibilityServiceInfo;)V

    .line 239
    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v7

    const-wide/16 v19, 0x3e8

    add-long v7, v7, v19

    :goto_199
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    invoke-virtual {v0}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v0

    if-eq v0, v15, :cond_1ad

    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v10

    cmp-long v0, v10, v7

    if-gez v0, :cond_1ad

    invoke-static/range {v16 .. v17}, Landroid/os/SystemClock;->sleep(J)V

    goto :goto_199

    .line 240
    :cond_1ad
    invoke-virtual {v6, v4, v13}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v0

    iget-object v4, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v4}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v4

    iget v4, v4, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    invoke-virtual {v0, v3, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    iget-object v3, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    .line 241
    invoke-virtual {v3}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v3

    invoke-virtual {v0, v2, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    iget-object v2, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    .line 242
    invoke-virtual {v2}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v2

    iget v2, v2, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    if-ne v2, v9, :cond_1db

    iget-object v2, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v2

    if-ne v2, v15, :cond_1db

    const/4 v13, 0x1

    goto :goto_1dc

    :cond_1db
    const/4 v13, 0x0

    :goto_1dc
    invoke-virtual {v0, v5, v13}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;
    :try_end_1df
    .catch Ljava/lang/Exception; {:try_start_184 .. :try_end_1df} :catch_1e0

    goto :goto_1e7

    .line 243
    :catch_1e0
    move-exception v0

    const/4 v2, 0x0

    :try_start_1e2
    invoke-virtual {v6, v5, v2}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;
    :try_end_1e5
    .catch Ljava/lang/Exception; {:try_start_1e2 .. :try_end_1e5} :catch_1e6

    goto :goto_1e7

    :catch_1e6
    move-exception v0

    :goto_1e7
    nop

    .line 244
    :cond_1e8
    new-instance v0, Ljava/util/IdentityHashMap;

    invoke-direct {v0}, Ljava/util/IdentityHashMap;-><init>()V

    invoke-static {v0}, Ljava/util/Collections;->newSetFromMap(Ljava/util/Map;)Ljava/util/Set;

    move-result-object v2

    .line 245
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->retained:Ljava/util/List;

    invoke-interface {v0}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v3

    :cond_1f7
    :goto_1f7
    invoke-interface {v3}, Ljava/util/Iterator;->hasNext()Z

    move-result v0

    if-eqz v0, :cond_20f

    invoke-interface {v3}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/view/accessibility/AccessibilityNodeInfo;

    invoke-interface {v2, v0}, Ljava/util/Set;->add(Ljava/lang/Object;)Z

    move-result v4

    if-eqz v4, :cond_1f7

    :try_start_209
    invoke-virtual {v0}, Landroid/view/accessibility/AccessibilityNodeInfo;->recycle()V
    :try_end_20c
    .catch Ljava/lang/Exception; {:try_start_209 .. :try_end_20c} :catch_20d

    goto :goto_1f7

    :catch_20d
    move-exception v0

    goto :goto_1f7

    .line 246
    :cond_20f
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->retainedWindows:Ljava/util/List;

    invoke-interface {v0}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v2

    :goto_215
    invoke-interface {v2}, Ljava/util/Iterator;->hasNext()Z

    move-result v0

    if-eqz v0, :cond_227

    invoke-interface {v2}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/view/accessibility/AccessibilityWindowInfo;

    :try_start_221
    invoke-virtual {v0}, Landroid/view/accessibility/AccessibilityWindowInfo;->recycle()V
    :try_end_224
    .catch Ljava/lang/Exception; {:try_start_221 .. :try_end_224} :catch_225

    goto :goto_215

    :catch_225
    move-exception v0

    goto :goto_215

    :cond_227
    const/4 v14, -0x1

    goto/16 :goto_31d

    .line 233
    :catchall_22a
    move-exception v0

    goto :goto_22e

    :catchall_22c
    move-exception v0

    move-object v13, v7

    :goto_22e
    const/4 v7, 0x1

    goto :goto_241

    :catchall_230
    move-exception v0

    move-object v13, v7

    const/4 v7, 0x0

    goto :goto_240

    :catchall_234
    move-exception v0

    goto :goto_23d

    :catchall_236
    move-exception v0

    goto :goto_23b

    :catchall_238
    move-exception v0

    const-wide/16 v16, 0x32

    :goto_23b
    const/16 v18, 0x2

    :goto_23d
    move-object v13, v7

    const/4 v7, 0x0

    const/4 v9, 0x0

    :goto_240
    const/4 v15, 0x0

    :goto_241
    :try_start_241
    new-instance v8, Lorg/json/JSONObject;

    invoke-direct {v8}, Lorg/json/JSONObject;-><init>()V
    :try_end_246
    .catchall {:try_start_241 .. :try_end_246} :catchall_33b

    .line 234
    :try_start_246
    instance-of v6, v0, Ljava/lang/IllegalArgumentException;

    if-eqz v6, :cond_24f

    invoke-virtual {v0}, Ljava/lang/Throwable;->getMessage()Ljava/lang/String;

    move-result-object v0

    goto :goto_251

    :cond_24f
    const-string v0, "UI_RUNNER_ERROR"

    .line 235
    :goto_251
    const-string v6, "ok"

    const/4 v10, 0x0

    invoke-virtual {v8, v6, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v6

    const-string v10, "error"

    invoke-virtual {v6, v10, v0}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v0

    const-string v6, "automatic_retry"

    const/4 v10, 0x0

    invoke-virtual {v0, v6, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    const-string v6, "outcome_unknown"

    iget-boolean v10, v1, Llocal/pocket4/actions/v2/ActionRunner;->actionAttempted:Z

    invoke-virtual {v0, v6, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;
    :try_end_26c
    .catch Ljava/lang/Exception; {:try_start_246 .. :try_end_26c} :catch_270
    .catchall {:try_start_246 .. :try_end_26c} :catchall_26d

    goto :goto_271

    .line 237
    :catchall_26d
    move-exception v0

    goto/16 :goto_33d

    .line 236
    :catch_270
    move-exception v0

    :goto_271
    nop

    .line 237
    if-eqz v7, :cond_2dc

    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    if-eqz v0, :cond_2dc

    .line 238
    :try_start_278
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v0}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v0

    iput v9, v0, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    iget-object v6, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v6, v0}, Landroid/app/UiAutomation;->setServiceInfo(Landroid/accessibilityservice/AccessibilityServiceInfo;)V

    .line 239
    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v6

    const-wide/16 v19, 0x3e8

    add-long v6, v6, v19

    :goto_28d
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    invoke-virtual {v0}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v0

    if-eq v0, v15, :cond_2a1

    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v10

    cmp-long v0, v10, v6

    if-gez v0, :cond_2a1

    invoke-static/range {v16 .. v17}, Landroid/os/SystemClock;->sleep(J)V

    goto :goto_28d

    .line 240
    :cond_2a1
    invoke-virtual {v8, v4, v13}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v0

    iget-object v4, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v4}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v4

    iget v4, v4, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    invoke-virtual {v0, v3, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    iget-object v3, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    .line 241
    invoke-virtual {v3}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v3

    invoke-virtual {v0, v2, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    iget-object v2, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    .line 242
    invoke-virtual {v2}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v2

    iget v2, v2, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    if-ne v2, v9, :cond_2cf

    iget-object v2, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v2

    if-ne v2, v15, :cond_2cf

    const/4 v13, 0x1

    goto :goto_2d0

    :cond_2cf
    const/4 v13, 0x0

    :goto_2d0
    invoke-virtual {v0, v5, v13}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;
    :try_end_2d3
    .catch Ljava/lang/Exception; {:try_start_278 .. :try_end_2d3} :catch_2d4

    goto :goto_2db

    .line 243
    :catch_2d4
    move-exception v0

    const/4 v10, 0x0

    :try_start_2d6
    invoke-virtual {v8, v5, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;
    :try_end_2d9
    .catch Ljava/lang/Exception; {:try_start_2d6 .. :try_end_2d9} :catch_2da

    goto :goto_2db

    :catch_2da
    move-exception v0

    :goto_2db
    nop

    .line 244
    :cond_2dc
    new-instance v0, Ljava/util/IdentityHashMap;

    invoke-direct {v0}, Ljava/util/IdentityHashMap;-><init>()V

    invoke-static {v0}, Ljava/util/Collections;->newSetFromMap(Ljava/util/Map;)Ljava/util/Set;

    move-result-object v2

    .line 245
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->retained:Ljava/util/List;

    invoke-interface {v0}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v3

    :cond_2eb
    :goto_2eb
    invoke-interface {v3}, Ljava/util/Iterator;->hasNext()Z

    move-result v0

    if-eqz v0, :cond_303

    invoke-interface {v3}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/view/accessibility/AccessibilityNodeInfo;

    invoke-interface {v2, v0}, Ljava/util/Set;->add(Ljava/lang/Object;)Z

    move-result v4

    if-eqz v4, :cond_2eb

    :try_start_2fd
    invoke-virtual {v0}, Landroid/view/accessibility/AccessibilityNodeInfo;->recycle()V
    :try_end_300
    .catch Ljava/lang/Exception; {:try_start_2fd .. :try_end_300} :catch_301

    goto :goto_2eb

    :catch_301
    move-exception v0

    goto :goto_2eb

    .line 246
    :cond_303
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->retainedWindows:Ljava/util/List;

    invoke-interface {v0}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v2

    :goto_309
    invoke-interface {v2}, Ljava/util/Iterator;->hasNext()Z

    move-result v0

    if-eqz v0, :cond_31b

    invoke-interface {v2}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/view/accessibility/AccessibilityWindowInfo;

    :try_start_315
    invoke-virtual {v0}, Landroid/view/accessibility/AccessibilityWindowInfo;->recycle()V
    :try_end_318
    .catch Ljava/lang/Exception; {:try_start_315 .. :try_end_318} :catch_319

    goto :goto_309

    :catch_319
    move-exception v0

    goto :goto_309

    :cond_31b
    move-object v6, v8

    const/4 v14, 0x0

    .line 247
    :goto_31d
    new-instance v0, Landroid/os/Bundle;

    invoke-direct {v0}, Landroid/os/Bundle;-><init>()V

    invoke-virtual {v6}, Lorg/json/JSONObject;->toString()Ljava/lang/String;

    move-result-object v2

    sget-object v3, Ljava/nio/charset/StandardCharsets;->UTF_8:Ljava/nio/charset/Charset;

    invoke-virtual {v2, v3}, Ljava/lang/String;->getBytes(Ljava/nio/charset/Charset;)[B

    move-result-object v2

    move/from16 v3, v18

    invoke-static {v2, v3}, Landroid/util/Base64;->encodeToString([BI)Ljava/lang/String;

    move-result-object v2

    const-string v3, "sidecar_result_base64"

    invoke-virtual {v0, v3, v2}, Landroid/os/Bundle;->putString(Ljava/lang/String;Ljava/lang/String;)V

    invoke-virtual {v1, v14, v0}, Llocal/pocket4/actions/v2/ActionRunner;->finish(ILandroid/os/Bundle;)V

    .line 248
    return-void

    .line 237
    :catchall_33b
    move-exception v0

    move-object v8, v6

    :goto_33d
    move-object v6, v0

    if-eqz v7, :cond_3a8

    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    if-eqz v0, :cond_3a8

    .line 238
    :try_start_344
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v0}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v0

    iput v9, v0, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    iget-object v7, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v7, v0}, Landroid/app/UiAutomation;->setServiceInfo(Landroid/accessibilityservice/AccessibilityServiceInfo;)V

    .line 239
    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v10

    const-wide/16 v19, 0x3e8

    add-long v10, v10, v19

    :goto_359
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    invoke-virtual {v0}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v0

    if-eq v0, v15, :cond_36d

    invoke-static {}, Landroid/os/SystemClock;->uptimeMillis()J

    move-result-wide v19

    cmp-long v0, v19, v10

    if-gez v0, :cond_36d

    invoke-static/range {v16 .. v17}, Landroid/os/SystemClock;->sleep(J)V

    goto :goto_359

    .line 240
    :cond_36d
    invoke-virtual {v8, v4, v13}, Lorg/json/JSONObject;->put(Ljava/lang/String;Ljava/lang/Object;)Lorg/json/JSONObject;

    move-result-object v0

    iget-object v4, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    invoke-virtual {v4}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v4

    iget v4, v4, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    invoke-virtual {v0, v3, v4}, Lorg/json/JSONObject;->put(Ljava/lang/String;I)Lorg/json/JSONObject;

    move-result-object v0

    iget-object v3, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    .line 241
    invoke-virtual {v3}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v3

    invoke-virtual {v0, v2, v3}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;

    move-result-object v0

    iget-object v2, v1, Llocal/pocket4/actions/v2/ActionRunner;->ui:Landroid/app/UiAutomation;

    .line 242
    invoke-virtual {v2}, Landroid/app/UiAutomation;->getServiceInfo()Landroid/accessibilityservice/AccessibilityServiceInfo;

    move-result-object v2

    iget v2, v2, Landroid/accessibilityservice/AccessibilityServiceInfo;->flags:I

    if-ne v2, v9, :cond_39b

    iget-object v2, v1, Llocal/pocket4/actions/v2/ActionRunner;->manager:Landroid/view/accessibility/AccessibilityManager;

    invoke-virtual {v2}, Landroid/view/accessibility/AccessibilityManager;->isTouchExplorationEnabled()Z

    move-result v2

    if-ne v2, v15, :cond_39b

    const/4 v13, 0x1

    goto :goto_39c

    :cond_39b
    const/4 v13, 0x0

    :goto_39c
    invoke-virtual {v0, v5, v13}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;
    :try_end_39f
    .catch Ljava/lang/Exception; {:try_start_344 .. :try_end_39f} :catch_3a0

    goto :goto_3a7

    .line 243
    :catch_3a0
    move-exception v0

    const/4 v10, 0x0

    :try_start_3a2
    invoke-virtual {v8, v5, v10}, Lorg/json/JSONObject;->put(Ljava/lang/String;Z)Lorg/json/JSONObject;
    :try_end_3a5
    .catch Ljava/lang/Exception; {:try_start_3a2 .. :try_end_3a5} :catch_3a6

    goto :goto_3a7

    :catch_3a6
    move-exception v0

    :goto_3a7
    nop

    .line 244
    :cond_3a8
    new-instance v0, Ljava/util/IdentityHashMap;

    invoke-direct {v0}, Ljava/util/IdentityHashMap;-><init>()V

    invoke-static {v0}, Ljava/util/Collections;->newSetFromMap(Ljava/util/Map;)Ljava/util/Set;

    move-result-object v2

    .line 245
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->retained:Ljava/util/List;

    invoke-interface {v0}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v3

    :cond_3b7
    :goto_3b7
    invoke-interface {v3}, Ljava/util/Iterator;->hasNext()Z

    move-result v0

    if-eqz v0, :cond_3cf

    invoke-interface {v3}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/view/accessibility/AccessibilityNodeInfo;

    invoke-interface {v2, v0}, Ljava/util/Set;->add(Ljava/lang/Object;)Z

    move-result v4

    if-eqz v4, :cond_3b7

    :try_start_3c9
    invoke-virtual {v0}, Landroid/view/accessibility/AccessibilityNodeInfo;->recycle()V
    :try_end_3cc
    .catch Ljava/lang/Exception; {:try_start_3c9 .. :try_end_3cc} :catch_3cd

    goto :goto_3b7

    :catch_3cd
    move-exception v0

    goto :goto_3b7

    .line 246
    :cond_3cf
    iget-object v0, v1, Llocal/pocket4/actions/v2/ActionRunner;->retainedWindows:Ljava/util/List;

    invoke-interface {v0}, Ljava/util/List;->iterator()Ljava/util/Iterator;

    move-result-object v2

    :goto_3d5
    invoke-interface {v2}, Ljava/util/Iterator;->hasNext()Z

    move-result v0

    if-eqz v0, :cond_3e7

    invoke-interface {v2}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v0

    check-cast v0, Landroid/view/accessibility/AccessibilityWindowInfo;

    :try_start_3e1
    invoke-virtual {v0}, Landroid/view/accessibility/AccessibilityWindowInfo;->recycle()V
    :try_end_3e4
    .catch Ljava/lang/Exception; {:try_start_3e1 .. :try_end_3e4} :catch_3e5

    goto :goto_3d5

    :catch_3e5
    move-exception v0

    goto :goto_3d5

    :cond_3e7
    throw v6
.end method
