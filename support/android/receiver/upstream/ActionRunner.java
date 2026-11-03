package local.pocket4.actions.v2;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Activity;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Base64;
import android.util.SparseArray;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import android.view.accessibility.AccessibilityManager;
import android.view.InputDevice;
import android.view.MotionEvent;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.json.*;

/** Fixed one-shot public accessibility operations. No persistent server or app hooks. */
public final class ActionRunner extends Instrumentation {
  private Bundle arguments;
  private UiAutomation ui;
  private final List<AccessibilityNodeInfo> retained=new ArrayList<>();
  private final List<AccessibilityWindowInfo> retainedWindows=new ArrayList<>();
  private int visited,visible,nullChildren;
  private boolean truncated;
  private boolean actionAttempted;
  private AccessibilityManager manager;
  @Override public void onCreate(Bundle b) { super.onCreate(b); arguments=b; start(); }
  private static String str(CharSequence s) { return s==null?"":s.toString(); }
  private static void require(boolean b,String code) { if(!b) throw new IllegalArgumentException(code); }
  private static JSONArray bounds(AccessibilityNodeInfo n) throws Exception {
    Rect b=new Rect();n.getBoundsInScreen(b);return new JSONArray(new int[]{b.left,b.top,b.right,b.bottom});
  }
  private static String editableValue(AccessibilityNodeInfo n) { return n.isShowingHintText()?"":str(n.getText()); }
  private JSONObject rootMeta(AccessibilityNodeInfo n) throws Exception {
    if(n==null)return new JSONObject().put("present",false);
    return new JSONObject().put("present",true).put("package",str(n.getPackageName()))
      .put("class",str(n.getClassName())).put("window_id",n.getWindowId()).put("bounds",bounds(n))
      .put("visible",n.isVisibleToUser()).put("child_count",n.getChildCount());
  }
  private JSONObject describe(AccessibilityNodeInfo n) throws Exception {
    boolean secret=n.isPassword();Rect b=new Rect();n.getBoundsInScreen(b);
    JSONArray actions=new JSONArray();for(AccessibilityNodeInfo.AccessibilityAction a:n.getActionList())actions.put(a.getId());
    return new JSONObject().put("text",secret?"":str(n.getText())).put("hint",secret?"":str(n.getHintText()))
      .put("showing-hint",n.isShowingHintText()).put("value",n.isEditable()&&!secret?editableValue(n):JSONObject.NULL)
      .put("resource-id",str(n.getViewIdResourceName())).put("content-desc",secret?"":str(n.getContentDescription()))
      .put("package",str(n.getPackageName())).put("class",str(n.getClassName())).put("window_id",n.getWindowId())
      .put("enabled",n.isEnabled()).put("focused",n.isFocused()).put("editable",n.isEditable())
      .put("clickable",n.isClickable()).put("password",secret).put("visible",n.isVisibleToUser())
      .put("scrollable",n.isScrollable()).put("selected",n.isSelected()).put("checked",n.isChecked())
      .put("important_for_accessibility",n.isImportantForAccessibility()).put("supported_actions",actions)
      .put("bounds_array",bounds(n)).put("bounds","["+b.left+","+b.top+"]["+b.right+","+b.bottom+"]")
      .put("source","native_accessibility");
  }
  private void collect(AccessibilityNodeInfo n,List<AccessibilityNodeInfo> out,int depth,boolean includeInvisible) {
    if(n==null){nullChildren++;return;}retained.add(n);
    if(depth>=100||visited>=2000){truncated=true;return;}visited++;
    if(n.isVisibleToUser()){visible++;out.add(n);}else if(includeInvisible)out.add(n);
    int count=n.getChildCount();if(count>2000){truncated=true;return;}
    for(int i=0;i<count;i++){if(visited>=2000){truncated=true;break;}collect(n.getChild(i),out,depth+1,includeInvisible);}
  }
  private boolean matches(AccessibilityNodeInfo n,JSONObject s) throws Exception {
    for(Iterator<String> it=s.keys();it.hasNext();){String k=it.next(),v=String.valueOf(s.get(k)),a;
      switch(k){
        case "text":if(n.isPassword())return false;a=str(n.getText());break;
        case "contains":if(n.isPassword()||!str(n.getText()).contains(v))return false;continue;
        case "id":a=str(n.getViewIdResourceName());break;
        case "desc":if(n.isPassword())return false;a=str(n.getContentDescription());break;
        case "class":a=str(n.getClassName());break;case "package":a=str(n.getPackageName());break;
        case "focused":a=String.valueOf(n.isFocused());break;case "editable":a=String.valueOf(n.isEditable());break;
        case "enabled":a=String.valueOf(n.isEnabled());break;case "clickable":a=String.valueOf(n.isClickable());break;
        case "scrollable":a=String.valueOf(n.isScrollable());break;case "selected":a=String.valueOf(n.isSelected());break;
        case "checked":a=String.valueOf(n.isChecked());break;default:throw new IllegalArgumentException("UNKNOWN_SELECTOR");
      }if(!a.equals(v))return false;
    }return true;
  }
  private String identity(AccessibilityNodeInfo n) throws Exception {
    boolean secret=n.isPassword();return new JSONObject().put("package",str(n.getPackageName())).put("window",n.getWindowId())
      .put("class",str(n.getClassName())).put("id",str(n.getViewIdResourceName())).put("bounds",bounds(n))
      .put("text",secret?"":str(n.getText())).put("desc",secret?"":str(n.getContentDescription()))
      .put("password",secret).put("editable",n.isEditable()).put("clickable",n.isClickable()).toString();
  }
  private JSONObject mouseClick(AccessibilityNodeInfo n,JSONObject window) throws Exception {
    Rect b=new Rect();n.getBoundsInScreen(b);require(b.width()>0&&b.height()>0,"TARGET_HAS_NO_SCREEN_BOUNDS");
    int x=b.centerX(),y=b.centerY();require(window!=null,"NO_VERIFIED_FOCUSED_APPLICATION_WINDOW");JSONArray wb=window.getJSONArray("bounds");
    require(x>=wb.getInt(0)&&y>=wb.getInt(1)&&x<wb.getInt(2)&&y<wb.getInt(3),"MOUSE_TARGET_OUTSIDE_WINDOW");
    MotionEvent.PointerProperties property=new MotionEvent.PointerProperties();property.id=0;property.toolType=MotionEvent.TOOL_TYPE_MOUSE;
    MotionEvent.PointerCoords coords=new MotionEvent.PointerCoords();coords.x=x;coords.y=y;coords.pressure=1;coords.size=1;
    long now=SystemClock.uptimeMillis();
    // The public 14-argument overload uses DEFAULT_DISPLAY (0), verified in pinned framework source.
    MotionEvent down=MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,1,new MotionEvent.PointerProperties[]{property},
      new MotionEvent.PointerCoords[]{coords},0,MotionEvent.BUTTON_PRIMARY,1,1,0,0,InputDevice.SOURCE_MOUSE,0);
    coords.pressure=0;MotionEvent up=MotionEvent.obtain(now,SystemClock.uptimeMillis(),MotionEvent.ACTION_UP,1,
      new MotionEvent.PointerProperties[]{property},new MotionEvent.PointerCoords[]{coords},0,0,1,1,0,0,InputDevice.SOURCE_MOUSE,0);
    boolean pressed=false,released=false;actionAttempted=true;
    try{try{pressed=ui.injectInputEvent(down,true);}finally{released=ui.injectInputEvent(up,true);}}
    finally{down.recycle();up.recycle();}
    require(pressed&&released,"MOUSE_INPUT_REJECTED");JSONObject target=describe(n);
    return new JSONObject().put("ok",true).put("performed","click").put("method","mouse").put("source","native_bounds_mouse")
      .put("coordinates",new JSONArray(new int[]{x,y})).put("target",target).put("actual_target",target)
      .put("visual_verified",false).put("business_success_verified",false);
  }
  private JSONObject execute(JSONObject r) throws Exception {
    String op=r.getString("op");require(Arrays.asList("meta","dump","find","click","set-text","type-text","scroll-forward","scroll-backward").contains(op),"UNSUPPORTED_UI_ACTION");
    int display=r.optInt("display",0);require(display==0,"ONLY_DEFAULT_DISPLAY_SUPPORTED");
    ui.clearCache();SparseArray<List<AccessibilityWindowInfo>> allWindows=ui.getWindowsOnAllDisplays();
    JSONArray windows=new JSONArray();AccessibilityNodeInfo root=null;JSONObject selected=null;int focused=0;
    List<AccessibilityWindowInfo> onDisplay=allWindows.get(display);
    if(onDisplay!=null)for(AccessibilityWindowInfo w:onDisplay){retainedWindows.add(w);Rect b=new Rect();w.getBoundsInScreen(b);
      AccessibilityNodeInfo wr=w.getRoot();if(wr!=null)retained.add(wr);
      JSONObject wm=new JSONObject().put("window_id",w.getId()).put("display_id",w.getDisplayId())
        .put("active",w.isActive()).put("focused",w.isFocused()).put("type",w.getType())
        .put("bounds",new JSONArray(new int[]{b.left,b.top,b.right,b.bottom})).put("root",rootMeta(wr));windows.put(wm);
      if(w.getType()==AccessibilityWindowInfo.TYPE_APPLICATION&&w.isFocused()){focused++;root=wr;selected=wm;}
    }
    // Old active-root operations still work when window enumeration is unavailable.
    if(focused==0&&!op.equals("meta")){root=ui.getRootInActiveWindow();if(root!=null)retained.add(root);}
    require(focused<=1,"AMBIGUOUS_FOCUSED_WINDOW");
    String expected=r.optString("expected_package","");
    if(!expected.isEmpty())require(root!=null&&expected.equals(str(root.getPackageName())),"FOREGROUND_PACKAGE_MISMATCH");
    JSONObject metadata=new JSONObject().put("display_id",display).put("selected_window",selected==null?JSONObject.NULL:selected)
      .put("windows",windows).put("root",rootMeta(root)).put("flags",ui.getServiceInfo().flags)
      .put("capabilities",ui.getServiceInfo().getCapabilities()).put("is_accessibility_tool",ui.getServiceInfo().isAccessibilityTool())
      .put("accessibility_enabled",manager.isEnabled()).put("touch_exploration_enabled",manager.isTouchExplorationEnabled())
      .put("uptime_ms",SystemClock.uptimeMillis());
    if(op.equals("meta"))return new JSONObject().put("ok",true).put("window_context",metadata);
    require(root!=null,"NO_ACTIVE_WINDOW");List<AccessibilityNodeInfo> nodes=new ArrayList<>();
    collect(root,nodes,0,r.optBoolean("include_invisible",false));
    metadata.put("visited_count",visited).put("visible_count",visible).put("null_child_count",nullChildren).put("truncated",truncated);
    boolean placeholder=visited==1&&root.getChildCount()==0&&str(root.getClassName()).isEmpty();
    metadata.put("semantic_controls_available",visible>0&&!placeholder&&!truncated&&nullChildren==0)
      .put("snapshot_complete",!truncated&&nullChildren==0)
      .put("tree_status",nullChildren>0?"incomplete":truncated?"truncated":placeholder?"app_exposed_empty_root":visible==0?"no_visible_nodes":"available");
    if(op.equals("dump")){JSONArray a=new JSONArray();for(AccessibilityNodeInfo n:nodes)a.put(describe(n));
      return new JSONObject().put("ok",true).put("nodes",a).put("window_context",metadata);}
    JSONObject selector=r.optJSONObject("selector");
    if(op.equals("type-text")||(op.equals("set-text")&&(selector==null||selector.length()==0)))selector=new JSONObject().put("focused",true).put("editable",true);
    if(op.equals("set-text")&&selector!=null&&selector.length()==1&&selector.has("package"))selector.put("focused",true).put("editable",true);
    boolean scroll=op.equals("scroll-forward")||op.equals("scroll-backward");
    if(scroll){
      require(!r.has("index"),"SCROLL_REQUIRES_UNIQUE_SELECTOR");
      if(selector==null||selector.length()==0)selector=new JSONObject().put("scrollable",true);
      else if(selector.length()==1&&selector.has("package"))selector.put("scrollable",true);
    }
    require(selector!=null&&selector.length()>0,"SELECTOR_REQUIRED");List<AccessibilityNodeInfo> found=new ArrayList<>();
    for(AccessibilityNodeInfo n:nodes)if(matches(n,selector))found.add(n);
    if(op.equals("find")){JSONArray a=new JSONArray();for(AccessibilityNodeInfo n:found)a.put(describe(n));
      return new JSONObject().put("ok",true).put("count",found.size()).put("matches",a).put("window_context",metadata);}
    require(!truncated&&nullChildren==0,"INCOMPLETE_TREE_NO_ACTION_TAKEN");require(!found.isEmpty(),"NO_MATCH");
    require(r.has("index")||found.size()==1,"AMBIGUOUS_MATCH");int index=r.optInt("index",0);
    require(index>=0&&index<found.size(),"INDEX_OUT_OF_RANGE");AccessibilityNodeInfo n=found.get(index);
    String originalIdentity=identity(n);int originalCount=found.size(),originalWindow=root.getWindowId();String originalPackage=str(root.getPackageName());
    ui.clearCache();AccessibilityNodeInfo freshRoot=null;int freshWindows=0;
    for(AccessibilityWindowInfo w:ui.getWindows()){retainedWindows.add(w);
      if(w.getDisplayId()==display&&w.getType()==AccessibilityWindowInfo.TYPE_APPLICATION&&w.isFocused()){
        freshWindows++;require(w.getId()==originalWindow,"WINDOW_CHANGED_NO_ACTION_TAKEN");
        if(selected!=null){Rect freshBounds=new Rect();w.getBoundsInScreen(freshBounds);JSONArray originalBounds=selected.getJSONArray("bounds");
          require(freshBounds.left==originalBounds.getInt(0)&&freshBounds.top==originalBounds.getInt(1)
            &&freshBounds.right==originalBounds.getInt(2)&&freshBounds.bottom==originalBounds.getInt(3),"WINDOW_BOUNDS_CHANGED_NO_ACTION_TAKEN");}
        freshRoot=w.getRoot();if(freshRoot!=null)retained.add(freshRoot);}}
    require(freshWindows==1&&freshRoot!=null&&str(freshRoot.getPackageName()).equals(originalPackage),"WINDOW_CHANGED_NO_ACTION_TAKEN");
    visited=visible=nullChildren=0;truncated=false;List<AccessibilityNodeInfo> freshNodes=new ArrayList<>();collect(freshRoot,freshNodes,0,false);
    require(!truncated&&nullChildren==0,"INCOMPLETE_TREE_NO_ACTION_TAKEN");List<AccessibilityNodeInfo> freshFound=new ArrayList<>();
    for(AccessibilityNodeInfo candidate:freshNodes)if(matches(candidate,selector))freshFound.add(candidate);
    require(!freshFound.isEmpty(),"TARGET_CHANGED_NO_ACTION_TAKEN");
    if(!r.has("index"))require(freshFound.size()==1,"AMBIGUOUS_MATCH_NO_ACTION_TAKEN");
    else require(freshFound.size()==originalCount&&index<freshFound.size(),"MATCH_SET_CHANGED_NO_ACTION_TAKEN");
    n=freshFound.get(index);require(identity(n).equals(originalIdentity),"TARGET_CHANGED_NO_ACTION_TAKEN");
    require(n.refresh()&&matches(n,selector),"TARGET_CHANGED_NO_ACTION_TAKEN");
    require(n.isVisibleToUser()&&n.isEnabled(),"TARGET_NOT_VISIBLE_OR_ENABLED");
    if(op.equals("click")){
      String method=r.optString("method","accessibility");require(method.equals("accessibility")||method.equals("mouse"),"INVALID_CLICK_METHOD");
      if(method.equals("mouse"))return mouseClick(n,selected);
    }
    if(scroll){
      require(n.isScrollable(),"TARGET_NOT_SCROLLABLE");int action=op.equals("scroll-forward")?AccessibilityNodeInfo.ACTION_SCROLL_FORWARD:AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD;
      boolean supported=false;for(AccessibilityNodeInfo.AccessibilityAction a:n.getActionList())if(a.getId()==action)supported=true;
      require(supported,"SCROLL_ACTION_NOT_SUPPORTED");JSONObject target=describe(n);actionAttempted=true;
      require(n.performAction(action),"SCROLL_REJECTED");
      return new JSONObject().put("ok",true).put("performed",op).put("target",target).put("actual_target",target)
        .put("visual_verified",false).put("business_success_verified",false);
    }
    if(op.equals("click")){JSONObject target=describe(n);AccessibilityNodeInfo actual=n;int depth=0;
      while(!actual.isClickable()){require(depth++<100,"CLICK_ANCESTOR_LIMIT");AccessibilityNodeInfo parent=actual.getParent();
        require(parent!=null,"TARGET_NOT_CLICKABLE");retained.add(parent);
        require(parent.getWindowId()==n.getWindowId()&&str(parent.getPackageName()).equals(str(n.getPackageName())),"ANCESTOR_SCOPE_MISMATCH");actual=parent;}
      require(actual.refresh()&&actual.isVisibleToUser()&&actual.isEnabled(),"CLICK_ANCESTOR_CHANGED");
      JSONObject acted=describe(actual);actionAttempted=true;require(actual.performAction(AccessibilityNodeInfo.ACTION_CLICK),"CLICK_REJECTED");
      return new JSONObject().put("ok",true).put("performed",op).put("target",target).put("actual_target",acted)
        .put("visual_verified",false).put("business_success_verified",false);}
    require(n.isEditable(),"TARGET_NOT_EDITABLE");String value=r.getString("value");
    if(op.equals("type-text")){require(!n.isPassword(),"CANNOT_APPEND_TO_MASKED_PASSWORD");value=editableValue(n)+value;}
    require(value.getBytes(StandardCharsets.UTF_8).length<=4096,"TEXT_TOO_LARGE");
    Bundle b=new Bundle();b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);
    actionAttempted=true;require(n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b),"SET_TEXT_REJECTED");boolean verified=false;
    if(!n.isPassword()){for(int i=0;i<20;i++){SystemClock.sleep(50);if(n.refresh()&&editableValue(n).equals(value)){verified=true;break;}}
      require(verified,"TEXT_READBACK_MISMATCH_ACTION_MAY_HAVE_OCCURRED");}
    return new JSONObject().put("ok",true).put("performed",op).put("characters",value.codePointCount(0,value.length()))
      .put("readback_verified",verified).put("password",n.isPassword());
  }
  @Override public void onStart(){JSONObject result=new JSONObject();int code=Activity.RESULT_OK;
    int originalFlags=0;boolean restore=false,originalTouch=false;String mode="none";
    try{String encoded=arguments.getString("request","");require(encoded.length()<=90000,"REQUEST_TOO_LARGE");
      JSONObject r=new JSONObject(new String(Base64.decode(encoded,Base64.DEFAULT),StandardCharsets.UTF_8));
      ui=getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);AccessibilityServiceInfo info=ui.getServiceInfo();
      manager=(AccessibilityManager)getContext().getSystemService(android.content.Context.ACCESSIBILITY_SERVICE);
      originalFlags=info.flags;originalTouch=manager.isTouchExplorationEnabled();restore=true;
      info.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
      mode=r.optString("accessibilityMode",r.optString("accessibility_mode","none"));require(mode.equals("none")||mode.equals("touch-exploration"),"INVALID_ACCESSIBILITY_MODE");
      if(mode.equals("touch-exploration")){
        require(r.optString("expected_package","").equals("com.tencent.mm"),"TOUCH_EXPLORATION_REQUIRES_EXPLICIT_WECHAT_SCOPE");
        AccessibilityNodeInfo prior=ui.getRootInActiveWindow();try{
          require(prior!=null&&str(prior.getPackageName()).equals("com.tencent.mm"),"FOREGROUND_PACKAGE_MISMATCH");
        }finally{if(prior!=null)prior.recycle();}
        require((info.getCapabilities()&AccessibilityServiceInfo.CAPABILITY_CAN_REQUEST_TOUCH_EXPLORATION)!=0,"TOUCH_EXPLORATION_CAPABILITY_MISSING");
        info.flags|=AccessibilityServiceInfo.FLAG_REQUEST_TOUCH_EXPLORATION_MODE;
      }
      ui.setServiceInfo(info);
      if(mode.equals("touch-exploration")){
        long deadline=SystemClock.uptimeMillis()+38000;boolean ready=false;
        do{ui.clearCache();AccessibilityNodeInfo current=ui.getRootInActiveWindow();try{
          Rect actualBounds=new Rect();if(current!=null)current.getBoundsInScreen(actualBounds);
          ready=manager.isTouchExplorationEnabled()&&current!=null&&str(current.getPackageName()).equals("com.tencent.mm")
            &&!str(current.getClassName()).isEmpty()&&current.getChildCount()>0&&current.isVisibleToUser()
            &&actualBounds.width()>0&&actualBounds.height()>0;
        }finally{if(current!=null)current.recycle();}if(!ready)SystemClock.sleep(500);}while(!ready&&SystemClock.uptimeMillis()<deadline);
        require(ready,"ACCESSIBILITY_TREE_NOT_READY_NO_ACTION_TAKEN");
      }
      try{ui.waitForIdle(100,1000);}catch(java.util.concurrent.TimeoutException ignored){}result=execute(r);
    }catch(Throwable e){code=Activity.RESULT_CANCELED;result=new JSONObject();try{
      String message=e instanceof IllegalArgumentException?e.getMessage():"UI_RUNNER_ERROR";
      result.put("ok",false).put("error",message).put("automatic_retry",false).put("outcome_unknown",actionAttempted);
    }catch(Exception ignored){}}
    finally{if(restore&&ui!=null)try{
        AccessibilityServiceInfo reverted=ui.getServiceInfo();reverted.flags=originalFlags;ui.setServiceInfo(reverted);
        long deadline=SystemClock.uptimeMillis()+1000;while(manager.isTouchExplorationEnabled()!=originalTouch&&SystemClock.uptimeMillis()<deadline)SystemClock.sleep(50);
        result.put("accessibility_mode",mode).put("restored_flags",ui.getServiceInfo().flags)
          .put("touch_exploration_after",manager.isTouchExplorationEnabled())
          .put("accessibility_mode_restoration_verified",ui.getServiceInfo().flags==originalFlags&&manager.isTouchExplorationEnabled()==originalTouch);
      }catch(Exception ignored){try{result.put("accessibility_mode_restoration_verified",false);}catch(Exception ignored2){}}
      Set<AccessibilityNodeInfo> unique=Collections.newSetFromMap(new IdentityHashMap<AccessibilityNodeInfo,Boolean>());
      for(AccessibilityNodeInfo n:retained)if(unique.add(n))try{n.recycle();}catch(Exception ignored){}
      for(AccessibilityWindowInfo w:retainedWindows)try{w.recycle();}catch(Exception ignored){}}
    Bundle out=new Bundle();out.putString("sidecar_result_base64",Base64.encodeToString(result.toString().getBytes(StandardCharsets.UTF_8),Base64.NO_WRAP));finish(code,out);
  }
}
