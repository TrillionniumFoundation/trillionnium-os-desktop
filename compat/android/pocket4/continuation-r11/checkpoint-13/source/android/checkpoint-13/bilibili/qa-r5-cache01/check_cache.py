#!/usr/bin/env python3
"""Actual R4/R5 window methods and R5 public reflection boundary, on owned seams.

The Android UiAutomation implementation, windows, clock, wait primitive and JSON
storage are explicit test doubles. Java reflection itself executes normally.
The cache counterexample is synthetic, shaped by the actual R4 observations;
it does not prove that Pocket4's observed failure was caused by this cache.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import types

HERE=Path(__file__).resolve().parent
OLD=HERE/'references/r4_ActionRunner.java'
NEW=HERE/'source/src/org/droidloom/qa/bili/r5/ActionRunner.java'
OLD_SHA='b23761d82d2bf176b20545ace7798ca81e78c03dc007d8152618a754962926ee'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def extract(source,name):
    start=source.index(name);begin=source.index('{',start);depth=1;end=begin+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]


AUTOMATION=r'''
    public final class UiAutomation {
      public boolean clearCache() {
        clearCalls++;
        if(mode.equals("cache_false"))return false;
        if(mode.equals("cache_exception"))throw injected;
        if(mode.equals("cache_error"))throw injectedError;
        if(mode.equals("cache_late"))now+=2001;
        cachedFocused=null;
        return true;
      }
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
'''

MAIN=r'''
  static int controls;
  static void run(boolean revised,String mode,boolean pass,String message,int sdk) throws Exception {
    now=0;encoded.clear();Build.VERSION.SDK_INT=sdk;
    Harness h=revised?new New():new Old();h.mode=mode;
    boolean success=false;Throwable error=null;
    try { Harness.SelectedWindows selected=h.awaitFocusedWindow();success=true;selected.close(); }
    catch(Throwable value){error=value;}
    need(success==pass && (pass || (error!=null && message.equals(error.getMessage()))),
         "RESULT:"+mode+":"+(error==null?"none":error.toString()));
    for(AccessibilityWindowInfo w:h.allocated)need(w.closed,"WINDOW_LEAK");
    for(long delay:h.waits)need(delay<=100,"WAIT_BOUND_CHANGED");
    if(!revised)need(h.calls==21 && h.clearCalls==0,"OLD_OBSERVATION_PATTERN");
    if(revised && mode.equals("cache_latched"))need(h.calls==5 && h.clearCalls==5 && now==302,"FRESH_QUERY_PATTERN");
    if(revised && (mode.equals("cache_false") || mode.equals("cache_exception") || mode.equals("cache_error") || mode.equals("cache_late")))
      need(h.calls==0 && h.clearCalls==1,"QUERY_AFTER_UNQUALIFIED_CLEAR");
    if(mode.equals("cache_exception") || mode.equals("query_error"))need(error==h.injected,"PRIMARY_EXCEPTION_REPLACED");
    if(mode.equals("cache_error"))need(error==h.injectedError,"PRIMARY_ERROR_REPLACED");
    if(sdk<34)need(h.clearCalls==0 && h.calls==0,"API_LEVEL_GATE_BYPASSED");
    if(mode.equals("query_error"))need(h.calls==2 && h.clearCalls==2,"FAILED_QUERY_RETRIED");
    if(mode.equals("event_storm"))need(h.calls==64 && h.clearCalls==64,"QUERY_LIMIT_CHANGED");
    if(revised && pass) {
      JSONArray rows=h.windowObservation.getJSONArray("sample_timings");
      need(rows.v.size()==h.calls && h.windowObservation.getLong("cache_attempts")==h.calls
          && h.windowObservation.getLong("cache_clears")==h.calls,"CLEAR_QUERY_COUNTS");
      for(Object item:rows.v)need(Boolean.TRUE.equals(((JSONObject)item).m.get("cache_cleared")),"UNCONFIRMED_SAMPLE");
      need(now<=2000,"LATE_READ_ACCEPTED");
    }
    controls++;
    System.out.println("{\"case\":\""+mode+"\",\"revised\":"+revised+",\"expected_met\":true,\"qualified\":"+success
      +",\"window_queries\":"+h.calls+",\"cache_calls\":"+h.clearCalls+",\"elapsed_ms\":"+now
      +",\"observation\":"+canonical(h.windowObservation)+"}");
  }
  public static void main(String[] args) throws Exception {
    run(false,"cache_latched",false,"NO_FOCUSED_APPLICATION_WINDOW",37);
    run(true,"cache_latched",true,null,37);
    run(true,"cache_false",false,"PUBLIC_CACHE_CLEAR_NOT_CONFIRMED",37);
    run(true,"cache_exception",false,"OWNED_CACHE_FAILURE",37);
    run(true,"cache_error",false,"OWNED_CACHE_ERROR",37);
    run(true,"immediate",false,"PUBLIC_CACHE_API_LEVEL_REQUIRED",33);
    run(true,"cache_late",false,"WINDOW_READINESS_DEADLINE",37);
    run(true,"never_ready",false,"NO_FOCUSED_APPLICATION_WINDOW",37);
    run(true,"wrong_display",false,"NO_FOCUSED_APPLICATION_WINDOW",37);
    run(true,"immediate",true,null,37);
    run(true,"event_storm",false,"WINDOW_QUERY_BOUND",37);
    run(true,"query_error",false,"OWNED_CACHE_FAILURE",37);
    System.out.println("{\"controls\":"+controls+",\"status\":\"PASS\",\"Android_or_UI_actions\":0}");
  }
}
'''

BOUNDARY_MAIN=r'''
  public static void main(String[] args) throws Exception {
    now=0;encoded.clear();Build.VERSION.SDK_INT=37;Harness h=new New();h.mode="immediate";
    Throwable error=null;
    try { h.awaitFocusedWindow(); } catch(Throwable value){error=value;}
    need(error!=null && h.calls==0 && h.clearCalls==0,"UNQUALIFIED_API_INVOKED_OR_QUERIED");
    if(EXPECT_MISSING)need(error instanceof NoSuchMethodException,"NONPUBLIC_API_NOT_REJECTED");
    else need("EXACT_PUBLIC_CACHE_API_REQUIRED".equals(error.getMessage()),"WRONG_SIGNATURE_NOT_REJECTED");
    System.out.println("{\"case\":\"BOUNDARY_CASE\",\"status\":\"PASS\",\"cache_calls\":0,\"window_queries\":0}");
  }
}
'''


def main():
    reference=HERE/'references/r4_check_wait.py'
    ref=types.ModuleType('frozen_r4_window_control');ref.__file__=str(reference)
    exec(compile(reference.read_bytes(),str(reference),'exec'),ref.__dict__)
    old,new=OLD.read_bytes(),NEW.read_bytes();assert sha(old)==OLD_SHA
    stubs=ref.STUBS.replace('import java.util.*;','import java.util.*;\nimport java.lang.reflect.*;')
    stubs=stubs.replace('  static long now;','  static long now;\n  static final class Build { static final class VERSION { static int SDK_INT=37; } }')
    stubs=stubs.replace('  static final class JSONObject {','  static final class JSONObject {\n    static final Object NULL=null;')
    stubs=stubs.replace('    String mode; int calls;','    String mode; int calls,clearCalls; Boolean cachedFocused; Method publicCacheClearMethod;\n    final IllegalStateException injected=new IllegalStateException("OWNED_CACHE_FAILURE");\n    final AssertionError injectedError=new AssertionError("OWNED_CACHE_ERROR");')
    stubs=stubs.replace('final EnumerationSeam automation=new EnumerationSeam()','final UiAutomation automation=new UiAutomation()')
    old_enumeration=extract(stubs,'final class EnumerationSeam')
    stubs=stubs.replace(old_enumeration,AUTOMATION.strip())
    bodies=[]
    for raw in (old,new):
        body=extract(raw.decode(),'SelectedWindows awaitFocusedWindow()')
        assert body.count('windowEvents.wait(')==1
        bodies.append(body.replace('windowEvents.wait(','windowEvents.await('))
    public_method=extract(new.decode(),'boolean clearOwnPublicWindowCache()')
    classes='\nstatic final class Old extends Harness {\n'+bodies[0]+'\n}\nstatic final class New extends Harness {\n'+public_method+'\n'+bodies[1]+'\n}\n'
    out=HERE/'cache-control-01';out.mkdir();runs=[]
    variants=[('window',stubs,MAIN)]
    clear_method=extract(stubs,'public boolean clearCache()')
    variants.append(('nonpublic',stubs.replace('public boolean clearCache()','private boolean clearCache()'),BOUNDARY_MAIN.replace('EXPECT_MISSING','true').replace('BOUNDARY_CASE','nonpublic')))
    variants.append(('wrong_return',stubs.replace('public boolean clearCache()','public Object clearCache()'),BOUNDARY_MAIN.replace('EXPECT_MISSING','false').replace('BOUNDARY_CASE','wrong_return')))
    variants.append(('static',stubs.replace(clear_method,'public static boolean clearCache() { return true; }'),BOUNDARY_MAIN.replace('EXPECT_MISSING','false').replace('BOUNDARY_CASE','static')))
    for name,template,main_body in variants:
        directory=out/name;directory.mkdir();path=directory/'WindowWaitControl.java';path.write_text(template+classes+main_body)
        result=subprocess.run(['/usr/bin/java',str(path)],capture_output=True,timeout=30)
        (directory/'stdout.jsonl').write_bytes(result.stdout);(directory/'stderr.txt').write_bytes(result.stderr)
        runs.append({'case':name,'exit_code':result.returncode,'java_sha256':sha(path.read_bytes()),'stdout_sha256':sha(result.stdout),'stderr_sha256':sha(result.stderr)})
        print(name,result.returncode,result.stdout.decode(),result.stderr.decode())
        if result.returncode:break
    report={'schema':1,'state':'PASS' if len(runs)==4 and all(x['exit_code']==0 for x in runs) else 'FAIL','old_sha256':OLD_SHA,'new_sha256':sha(new),
        'runs':runs,'expected_controls':15,'actual_window_method_bodies_extracted':True,'actual_public_reflection_method_extracted':True,
        'method_substitution_only':'Object.wait -> owned fake-clock await',
        'seams':['UiAutomation public API and cache/window enumeration','elapsed clock','condition wait','JSON storage'],
        'Java_reflection_executed':True,'runtime_cache_cause_proven':False,'Android_SDK_compile_performed':False,'Android_or_UI_actions':0}
    (out/'result.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n');print(json.dumps(report))
    assert report['state']=='PASS'


if __name__=='__main__':main()
