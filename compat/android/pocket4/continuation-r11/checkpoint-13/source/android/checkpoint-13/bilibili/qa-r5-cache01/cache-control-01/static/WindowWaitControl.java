
import java.util.*;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;

class WindowWaitControl {
  static long now;
  static final class Build { static final class VERSION { static int SDK_INT=37; } }
  static final class SystemClock { static long elapsedRealtime() { return now; } }
  static final class Rejected extends Exception { Rejected(String s) { super(s); } }
  static void need(boolean v, String code) throws Rejected { if (!v) throw new Rejected(code); }
  static Object copy(Object v) {
    if (v instanceof JSONObject) { JSONObject r = new JSONObject(); for (Map.Entry<String,Object> x : ((JSONObject)v).m.entrySet()) r.put(x.getKey(), copy(x.getValue())); return r; }
    if (v instanceof JSONArray) { JSONArray r = new JSONArray(); for (Object x : ((JSONArray)v).v) r.put(copy(x)); return r; }
    return v;
  }
  static final Map<String,JSONObject> encoded = new HashMap<>();
  static String canonical(Object v) {
    String r;
    if (v instanceof JSONObject) {
      StringJoiner j = new StringJoiner(",", "{", "}");
      for (Map.Entry<String,Object> x : ((JSONObject)v).m.entrySet()) j.add("\""+x.getKey()+"\":"+canonical(x.getValue()));
      r=j.toString(); encoded.put(r,(JSONObject)copy(v));
    } else if (v instanceof JSONArray) {
      StringJoiner j = new StringJoiner(",", "[", "]"); for (Object x : ((JSONArray)v).v) j.add(canonical(x)); r=j.toString();
    } else r=v instanceof String ? "\""+v+"\"" : String.valueOf(v);
    return r;
  }
  static final class JSONObject {
    static final Object NULL=null;
    final Map<String,Object> m = new TreeMap<>();
    JSONObject() {}
    JSONObject(String raw) { m.putAll(((JSONObject)copy(encoded.get(raw))).m); }
    JSONObject put(String k,Object v) { m.put(k,v); return this; }
    long getLong(String k) { return ((Number)m.get(k)).longValue(); }
    JSONArray getJSONArray(String k) { return (JSONArray)m.get(k); }
  }
  static final class JSONArray {
    final List<Object> v = new ArrayList<>(); JSONArray put(Object x) { v.add(x); return this; }
  }
  static final class SparseArray<T> {
    final List<Integer> k = new ArrayList<>(); final List<T> v = new ArrayList<>();
    int size() { return k.size(); } int keyAt(int i) { return k.get(i); } T valueAt(int i) { return v.get(i); }
    void put(int key,T value) { k.add(key);v.add(value); }
  }
  static final class AccessibilityWindowInfo {
    static final int TYPE_APPLICATION=1;
    final int display,id; final boolean focused; boolean closed;
    AccessibilityWindowInfo(int d,int i,boolean f) { display=d;id=i;focused=f; }
    int getDisplayId(){return display;} int getId(){return id;} int getType(){return 1;}
    boolean isFocused(){return focused;} boolean isActive(){return focused;}
    boolean isAccessibilityFocused(){return false;} int getLayer(){return id;}
    void recycle(){if(closed)throw new AssertionError("DOUBLE_RECYCLE");closed=true;}
  }
  static class Harness {
    static final long DEADLINE_MS=8000,WINDOW_WAIT_MS=2000,WINDOW_RECHECK_MS=100;
    static final int MAX_WINDOW_QUERIES=64;
    final long started=0;
    long windowEventSerial;
    JSONObject windowObservation=new JSONObject();
    final List<AccessibilityWindowInfo> allocated=new ArrayList<>();
    final List<Long> waits=new ArrayList<>();
    String mode; int calls,clearCalls; Boolean cachedFocused; Method publicCacheClearMethod;
    final IllegalStateException injected=new IllegalStateException("OWNED_CACHE_FAILURE");
    final AssertionError injectedError=new AssertionError("OWNED_CACHE_ERROR");
    final WaitSeam windowEvents=new WaitSeam(); final UiAutomation automation=new UiAutomation();
    final class WaitSeam { void await(long delay) { if(delay<=0)throw new AssertionError("NONPOSITIVE_WAIT"); waits.add(delay);now+=delay; } }
    public final class UiAutomation {
      public static boolean clearCache() { return true; }
      SparseArray<List<AccessibilityWindowInfo>> getWindowsOnAllDisplays() throws Exception {
        calls++;
        if(mode.equals("query_error") && calls==2)throw injected;
        if(calls==1)now+=2;
        if(mode.equals("cache_latched") && calls==1)windowEventSerial=5;
        if(mode.equals("event_storm"))windowEventSerial++;
        boolean focused=mode.equals("immediate");
        if(mode.equals("cache_latched")) {
          if(cachedFocused==null)cachedFocused=now>=300;
          focused=cachedFocused;
        }
        if(mode.equals("wrong_display"))focused=true;
        int display=mode.equals("wrong_display")?1:0;
        SparseArray<List<AccessibilityWindowInfo>> all=new SparseArray<>();
        List<AccessibilityWindowInfo> rows=new ArrayList<>();
        AccessibilityWindowInfo w=new AccessibilityWindowInfo(display,1303,focused);
        rows.add(w);allocated.add(w);all.put(display,rows);return all;
      }
    }
    void timeBound() throws Exception { need(now-started<=DEADLINE_MS,"OWNED_DEADLINE"); }
    static void recycleWindows(SparseArray<List<AccessibilityWindowInfo>> windows) {
      if(windows==null)return;
      for(int n=0;n<windows.size();n++)for(AccessibilityWindowInfo w:windows.valueAt(n))if(w!=null)w.recycle();
    }
    static final class SelectedWindows {
      final SparseArray<List<AccessibilityWindowInfo>> all; final AccessibilityWindowInfo selected;
      SelectedWindows(SparseArray<List<AccessibilityWindowInfo>> a,AccessibilityWindowInfo s){all=a;selected=s;}
      void close(){recycleWindows(all);}
    }
    SelectedWindows awaitFocusedWindow() throws Exception { throw new AssertionError("ABSTRACT"); }
  }

static final class Old extends Harness {
SelectedWindows awaitFocusedWindow() throws Exception {
        final long began = SystemClock.elapsedRealtime();
        final long deadline = Math.min(started + DEADLINE_MS, began + WINDOW_WAIT_MS);
        windowObservation = new JSONObject().put("requested_display", 0)
            .put("selection", "exact-display-0-focused-application")
            .put("wait_budget_ms", WINDOW_WAIT_MS).put("recheck_max_ms", WINDOW_RECHECK_MS)
            .put("sample_timings", new JSONArray()).put("ready", false);
        int samples = 0;
        for (;;) {
            timeBound(); need(samples < MAX_WINDOW_QUERIES, "WINDOW_QUERY_BOUND");
            final long serial;
            synchronized (windowEvents) { serial = windowEventSerial; }
            SparseArray<List<AccessibilityWindowInfo>> windows = automation.getWindowsOnAllDisplays();
            boolean retained = false;
            try {
                timeBound();
                need(windows != null && windows.size() <= 8, "WINDOW_DISPLAY_BOUND");
                AccessibilityWindowInfo chosen = null;
                JSONArray rows = new JSONArray();
                JSONArray displays = new JSONArray();
                int total = 0;
                for (int n = 0; n < windows.size(); n++) {
                    int display = windows.keyAt(n); List<AccessibilityWindowInfo> values = windows.valueAt(n);
                    need(display >= 0 && values != null && values.size() <= 32, "WINDOW_LIST_BOUND");
                    displays.put(display); total += values.size(); need(total <= 128, "WINDOW_TOTAL_BOUND");
                    for (AccessibilityWindowInfo window : values) {
                        need(window != null && window.getDisplayId() == display, "WINDOW_DISPLAY_ID_MISMATCH");
                        rows.put(new JSONObject().put("display", display).put("id", window.getId())
                            .put("type", window.getType()).put("focused", window.isFocused())
                            .put("active", window.isActive()).put("accessibility_focused", window.isAccessibilityFocused())
                            .put("layer", window.getLayer()));
                        if (display == 0 && window.isFocused() && window.getType() == AccessibilityWindowInfo.TYPE_APPLICATION) {
                            need(chosen == null, "AMBIGUOUS_FOCUSED_APPLICATION_WINDOW"); chosen = window;
                        }
                    }
                }
                JSONObject census = new JSONObject().put("sample", ++samples).put("event_serial", serial)
                    .put("elapsed_ms", SystemClock.elapsedRealtime() - began).put("displays", displays).put("windows", rows);
                JSONObject nextObservation = new JSONObject(canonical(windowObservation));
                if (samples == 1) nextObservation.put("first", census);
                nextObservation.put("last", census).put("samples", samples)
                    .put("waited_ms", SystemClock.elapsedRealtime() - began);
                nextObservation.getJSONArray("sample_timings").put(new JSONObject()
                    .put("sample", samples).put("event_serial", serial)
                    .put("elapsed_ms", census.getLong("elapsed_ms")));
                need(canonical(nextObservation).getBytes(StandardCharsets.UTF_8).length <= 32000, "WINDOW_CENSUS_RESULT_BOUND");
                windowObservation = nextObservation;
                need(SystemClock.elapsedRealtime() <= deadline, "WINDOW_READINESS_DEADLINE");
                if (chosen != null) {
                    windowObservation.put("ready", true).put("selected_display", 0).put("selected_window_id", chosen.getId());
                    retained = true; return new SelectedWindows(windows, chosen);
                }
            } finally { if (!retained) recycleWindows(windows); }
            long remaining = deadline - SystemClock.elapsedRealtime();
            need(remaining > 0, "NO_FOCUSED_APPLICATION_WINDOW");
            // A window event may arrive before the observable window changes.
            // Re-read this condition within the same deadline even if no later
            // event arrives. Events still wake immediately; no action is retried.
            // Serial closes the query/wait gap without holding a lock across IPC.
            synchronized (windowEvents) {
                if (windowEventSerial == serial) windowEvents.await(Math.min(remaining, WINDOW_RECHECK_MS));
            }
            windowObservation.put("waited_ms", SystemClock.elapsedRealtime() - began);
            need(SystemClock.elapsedRealtime() < deadline, "NO_FOCUSED_APPLICATION_WINDOW");
        }
    }
}
static final class New extends Harness {
boolean clearOwnPublicWindowCache() throws Exception {
        // clearCache() is public since API 34. Reflection keeps the pinned
        // compile-SDK-31 input; it does not request a hidden API exemption.
        need(Build.VERSION.SDK_INT >= 34, "PUBLIC_CACHE_API_LEVEL_REQUIRED");
        need(automation != null, "OWN_UI_AUTOMATION_REQUIRED_FOR_CACHE_CLEAR");
        if (publicCacheClearMethod == null) {
            Method method = UiAutomation.class.getMethod("clearCache");
            need(method.getDeclaringClass() == UiAutomation.class
                && method.getReturnType() == boolean.class && method.getParameterTypes().length == 0
                && Modifier.isPublic(method.getModifiers()) && !Modifier.isStatic(method.getModifiers()),
                "EXACT_PUBLIC_CACHE_API_REQUIRED");
            publicCacheClearMethod = method;
        }
        final Object result;
        try { result = publicCacheClearMethod.invoke(automation); }
        catch (InvocationTargetException invocation) {
            Throwable cause = invocation.getCause();
            if (cause instanceof Exception) throw (Exception) cause;
            if (cause instanceof Error) throw (Error) cause;
            throw invocation;
        }
        need(result instanceof Boolean, "PUBLIC_CACHE_BOOLEAN_RESULT_REQUIRED");
        return (Boolean) result;
    }
SelectedWindows awaitFocusedWindow() throws Exception {
        final long began = SystemClock.elapsedRealtime();
        final long deadline = Math.min(started + DEADLINE_MS, began + WINDOW_WAIT_MS);
        windowObservation = new JSONObject().put("requested_display", 0)
            .put("selection", "exact-display-0-focused-application")
            .put("wait_budget_ms", WINDOW_WAIT_MS).put("recheck_max_ms", WINDOW_RECHECK_MS)
            .put("sample_timings", new JSONArray()).put("ready", false)
            .put("cache_api", "android.app.UiAutomation.clearCache()")
            .put("cache_policy", "require_public_own_connection_clear_before_each_query")
            .put("cache_runtime_sdk", Build.VERSION.SDK_INT)
            .put("cache_attempts", 0).put("cache_clears", 0)
            .put("cache_last_result", JSONObject.NULL).put("cache_last_exception", JSONObject.NULL);
        int samples = 0;
        for (;;) {
            timeBound(); need(samples < MAX_WINDOW_QUERIES, "WINDOW_QUERY_BOUND");
            final long serial;
            synchronized (windowEvents) { serial = windowEventSerial; }
            windowObservation.put("cache_attempts", samples + 1)
                .put("cache_last_result", JSONObject.NULL).put("cache_last_exception", JSONObject.NULL);
            final boolean cacheCleared;
            try { cacheCleared = clearOwnPublicWindowCache(); }
            catch (Exception cacheError) {
                windowObservation.put("cache_last_exception", cacheError.getClass().getName());
                throw cacheError;
            }
            catch (Error cacheError) {
                windowObservation.put("cache_last_exception", cacheError.getClass().getName());
                throw cacheError;
            }
            windowObservation.put("cache_last_result", cacheCleared);
            need(cacheCleared, "PUBLIC_CACHE_CLEAR_NOT_CONFIRMED");
            windowObservation.put("cache_clears", samples + 1);
            timeBound();
            need(SystemClock.elapsedRealtime() <= deadline, "WINDOW_READINESS_DEADLINE");
            SparseArray<List<AccessibilityWindowInfo>> windows = automation.getWindowsOnAllDisplays();
            boolean retained = false;
            try {
                timeBound();
                need(windows != null && windows.size() <= 8, "WINDOW_DISPLAY_BOUND");
                AccessibilityWindowInfo chosen = null;
                JSONArray rows = new JSONArray();
                JSONArray displays = new JSONArray();
                int total = 0;
                for (int n = 0; n < windows.size(); n++) {
                    int display = windows.keyAt(n); List<AccessibilityWindowInfo> values = windows.valueAt(n);
                    need(display >= 0 && values != null && values.size() <= 32, "WINDOW_LIST_BOUND");
                    displays.put(display); total += values.size(); need(total <= 128, "WINDOW_TOTAL_BOUND");
                    for (AccessibilityWindowInfo window : values) {
                        need(window != null && window.getDisplayId() == display, "WINDOW_DISPLAY_ID_MISMATCH");
                        rows.put(new JSONObject().put("display", display).put("id", window.getId())
                            .put("type", window.getType()).put("focused", window.isFocused())
                            .put("active", window.isActive()).put("accessibility_focused", window.isAccessibilityFocused())
                            .put("layer", window.getLayer()));
                        if (display == 0 && window.isFocused() && window.getType() == AccessibilityWindowInfo.TYPE_APPLICATION) {
                            need(chosen == null, "AMBIGUOUS_FOCUSED_APPLICATION_WINDOW"); chosen = window;
                        }
                    }
                }
                JSONObject census = new JSONObject().put("sample", ++samples).put("event_serial", serial)
                    .put("elapsed_ms", SystemClock.elapsedRealtime() - began).put("displays", displays).put("windows", rows);
                JSONObject nextObservation = new JSONObject(canonical(windowObservation));
                if (samples == 1) nextObservation.put("first", census);
                nextObservation.put("last", census).put("samples", samples)
                    .put("waited_ms", SystemClock.elapsedRealtime() - began);
                nextObservation.getJSONArray("sample_timings").put(new JSONObject()
                    .put("sample", samples).put("event_serial", serial)
                    .put("elapsed_ms", census.getLong("elapsed_ms")).put("cache_cleared", cacheCleared));
                need(canonical(nextObservation).getBytes(StandardCharsets.UTF_8).length <= 32000, "WINDOW_CENSUS_RESULT_BOUND");
                windowObservation = nextObservation;
                need(SystemClock.elapsedRealtime() <= deadline, "WINDOW_READINESS_DEADLINE");
                if (chosen != null) {
                    windowObservation.put("ready", true).put("selected_display", 0).put("selected_window_id", chosen.getId());
                    retained = true; return new SelectedWindows(windows, chosen);
                }
            } finally { if (!retained) recycleWindows(windows); }
            long remaining = deadline - SystemClock.elapsedRealtime();
            need(remaining > 0, "NO_FOCUSED_APPLICATION_WINDOW");
            // A window event may arrive before the observable window changes.
            // Re-read this condition within the same deadline even if no later
            // event arrives. Events still wake immediately; no action is retried.
            // Serial closes the query/wait gap without holding a lock across IPC.
            synchronized (windowEvents) {
                if (windowEventSerial == serial) windowEvents.await(Math.min(remaining, WINDOW_RECHECK_MS));
            }
            windowObservation.put("waited_ms", SystemClock.elapsedRealtime() - began);
            need(SystemClock.elapsedRealtime() < deadline, "NO_FOCUSED_APPLICATION_WINDOW");
        }
    }
}

  public static void main(String[] args) throws Exception {
    now=0;encoded.clear();Build.VERSION.SDK_INT=37;Harness h=new New();h.mode="immediate";
    Throwable error=null;
    try { h.awaitFocusedWindow(); } catch(Throwable value){error=value;}
    need(error!=null && h.calls==0 && h.clearCalls==0,"UNQUALIFIED_API_INVOKED_OR_QUERIED");
    if(false)need(error instanceof NoSuchMethodException,"NONPUBLIC_API_NOT_REJECTED");
    else need("EXACT_PUBLIC_CACHE_API_REQUIRED".equals(error.getMessage()),"WRONG_SIGNATURE_NOT_REJECTED");
    System.out.println("{\"case\":\"static\",\"status\":\"PASS\",\"cache_calls\":0,\"window_queries\":0}");
  }
}
