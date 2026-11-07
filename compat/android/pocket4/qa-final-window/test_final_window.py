#!/usr/bin/env python3
"""Compile and execute the exact before/after Java final-window guard.

Only inspect(), Capture/JSONObject storage, the deadline clock, and the eventual
dispatch are local seams. The production predicate, try/finally, Rejected, need,
and actionAttempted assignment are copied unchanged from each pinned Java file.
This is a source-fragment regression, not an APK or Android runtime test.
"""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
RELATIVE = Path('src/org/droidloom/qa/bili/r3/ActionRunner.java')
PREIMAGE_SHA256 = '374c4b3ba1d83a97a376613b2ab2e015006019a61dd36970b27c64693d5bcef5'
OLD = '''                need(finalWindow.windowId == current.windowId && finalWindow.json.getString("tree_sha256").equals(current.json.getString("tree_sha256")), "FOCUS_CHANGED_BEFORE_ACTION");'''
NEW = '''                need(finalWindow.windowId == current.windowId
                     && finalWindow.json.getString("tree_sha256").equals(current.json.getString("tree_sha256"))
                     && finalWindow.json.getString("window_sha256").equals(current.json.getString("window_sha256")), "FOCUS_CHANGED_BEFORE_ACTION");'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + '\n')


def extract(source):
    begin = '            Capture finalWindow = inspect(null, "action_final_window");'
    end = '            timeBound(); actionAttempted = true;'
    assert source.count(begin) == source.count(end) == 1
    start = source.index(begin)
    fragment = source[start:source.index(end, start) + len(end)]
    declaration_start = source.index('    static final class Rejected extends Exception {')
    declaration_end = source.index('    static String hash(byte[] value)', declaration_start)
    declarations = source[declaration_start:declaration_end]
    return declarations, fragment


HARNESS = r'''
import java.util.HashMap;
import java.util.Map;

public final class GuardHarness {
__DECLARATIONS__
    static final String TREE = "__TREE__";
    static final String WINDOW = "__WINDOW__";
    static final String EXPANDED_WINDOW = "__EXPANDED_WINDOW__";
    static final class Json {
        final Map<String,String> values = new HashMap<String,String>();
        String getString(String name) {
            if (!values.containsKey(name)) throw new IllegalStateException("MISSING_" + name);
            return values.get(name);
        }
    }
    static final class Capture {
        int windowId;
        final Json json = new Json();
        int closes;
        Capture(int id, String tree, String window) {
            windowId = id;
            if (tree != null) json.values.put("tree_sha256", tree);
            if (window != null) json.values.put("window_sha256", window);
        }
        void close() { closes++; }
    }
    Capture supplied;
    boolean failInspect, failDeadline, actionAttempted, dispatchMarker;
    int inspectCalls, deadlineCalls;
    Capture inspect(String wanted, String purpose) throws Exception {
        if (wanted != null || !"action_final_window".equals(purpose))
            throw new AssertionError("wrong production inspect arguments");
        inspectCalls++;
        if (failInspect) throw new Rejected("CONTROL_INSPECT_FAILED");
        return supplied;
    }
    void timeBound() throws Exception {
        deadlineCalls++;
        if (failDeadline) throw new Rejected("OWNED_DEADLINE");
    }
    void execute(Capture current) throws Exception {
__FRAGMENT__
        dispatchMarker = true;
    }
    static int failures;
    static void check(String name, int finalId, String finalTree, String finalWindow,
                      boolean inspectFailure, boolean deadlineFailure,
                      String expectedError, int expectedCloses, int expectedDeadlines) {
        GuardHarness host = new GuardHarness();
        Capture current = new Capture(17, TREE, WINDOW);
        host.supplied = new Capture(finalId, finalTree, finalWindow);
        host.failInspect = inspectFailure;
        host.failDeadline = deadlineFailure;
        String error = null;
        try { host.execute(current); }
        catch (Exception failure) { error = failure.getClass().getSimpleName() + ":" + failure.getMessage(); }
        boolean expectedAccepted = expectedError == null;
        boolean ok = java.util.Objects.equals(error, expectedError)
            && host.inspectCalls == 1 && host.supplied.closes == expectedCloses
            && current.closes == 0 && host.deadlineCalls == expectedDeadlines
            && host.actionAttempted == expectedAccepted && host.dispatchMarker == expectedAccepted;
        if (!ok) failures++;
        System.out.println("{\"case\":\"" + name + "\",\"passed\":" + ok
            + ",\"actual_error\":" + (error == null ? "null" : "\"" + error + "\"")
            + ",\"expected_error\":" + (expectedError == null ? "null" : "\"" + expectedError + "\"")
            + ",\"action_attempted_marker\":" + host.actionAttempted
            + ",\"dispatch_marker_reached\":" + host.dispatchMarker
            + ",\"final_capture_closes\":" + host.supplied.closes
            + ",\"current_capture_closes_in_fragment\":" + current.closes
            + ",\"inspect_calls\":" + host.inspectCalls
            + ",\"deadline_calls\":" + host.deadlineCalls + "}");
    }
    public static void main(String[] args) {
        check("unchanged_window_and_tree", 17, TREE, WINDOW, false, false, null, 1, 1);
        check("same_id_tree_changed_window_envelope", 17, TREE, EXPANDED_WINDOW, false, false,
              "Rejected:FOCUS_CHANGED_BEFORE_ACTION", 1, 0);
        check("window_id_changed", 18, TREE, WINDOW, false, false,
              "Rejected:FOCUS_CHANGED_BEFORE_ACTION", 1, 0);
        check("tree_changed", 17, "changed-tree-digest", WINDOW, false, false,
              "Rejected:FOCUS_CHANGED_BEFORE_ACTION", 1, 0);
        check("final_window_digest_missing", 17, TREE, null, false, false,
              "IllegalStateException:MISSING_window_sha256", 1, 0);
        check("final_tree_digest_missing", 17, null, WINDOW, false, false,
              "IllegalStateException:MISSING_tree_sha256", 1, 0);
        check("final_inspection_failure", 17, TREE, WINDOW, true, false,
              "Rejected:CONTROL_INSPECT_FAILED", 0, 0);
        check("deadline_before_dispatch", 17, TREE, WINDOW, false, true,
              "Rejected:OWNED_DEADLINE", 1, 1);
        System.exit(failures == 0 ? 0 : 1);
    }
}
'''


def main():
    evidence = ROOT / 'evidence'
    evidence.mkdir(exist_ok=True)
    java = shutil.which('java')
    assert java is not None, 'Java with jdk.compiler module is required'
    before_raw = (ROOT / 'preimage' / RELATIVE).read_bytes()
    after_raw = (ROOT / 'candidate' / RELATIVE).read_bytes()
    assert sha(before_raw) == PREIMAGE_SHA256
    before, after = before_raw.decode('utf-8'), after_raw.decode('utf-8')
    assert before.count(OLD) == 1 and after == before.replace(OLD, NEW, 1), 'unexpected source delta'
    patch = ''.join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile='a/' + RELATIVE.as_posix(), tofile='b/' + RELATIVE.as_posix()))
    (ROOT / 'final-window-sha256.patch').write_text(patch)
    # The window expands while the unchanged tree still fits inside both bounds.
    # inspect() hashes AccessibilityWindowInfo geometry separately from its tree.
    window = {'package': 'tv.danmaku.bili', 'display': 0, 'type': 1,
              'focused': True, 'bounds': [0, 0, 800, 600]}
    expanded = dict(window, bounds=[0, 0, 1000, 600])
    nodes = [{'path': '0', 'package': 'tv.danmaku.bili', 'bounds': [20, 20, 780, 580],
              'visible': True, 'enabled': True, 'password': False}]
    fixtures = {'window_id': 17, 'tree': nodes, 'window_before': window, 'window_after': expanded,
                'tree_sha256': sha(canonical(nodes)), 'window_before_sha256': sha(canonical(window)),
                'window_after_sha256': sha(canonical(expanded)),
                'real_android_timing_reproduced': False}
    assert fixtures['window_before_sha256'] != fixtures['window_after_sha256']
    save_json(evidence / 'boundary-fixture.json', fixtures)
    results = {}
    for arm, source, source_raw in [('preimage', before, before_raw), ('candidate', after, after_raw)]:
        declarations, fragment = extract(source)
        harness = (HARNESS.replace('__DECLARATIONS__', declarations).replace('__FRAGMENT__', fragment)
            .replace('__TREE__', fixtures['tree_sha256'])
            .replace('__WINDOW__', fixtures['window_before_sha256'])
            .replace('__EXPANDED_WINDOW__', fixtures['window_after_sha256']))
        harness_path = evidence / (arm + '-GuardHarness.java.txt')
        harness_path.write_text(harness)
        with tempfile.TemporaryDirectory(prefix='qa-final-window-') as temporary:
            work = Path(temporary)
            (work / 'GuardHarness.java').write_text(harness)
            compiler_argv = [java, '-Xms16m', '-Xmx128m', '-m', 'jdk.compiler/com.sun.tools.javac.Main',
                             '-encoding', 'UTF-8', '-d', str(work), str(work / 'GuardHarness.java')]
            built = subprocess.run(compiler_argv, capture_output=True, timeout=30, check=False)
            assert built.returncode == 0, built.stderr.decode('utf-8', 'replace')
            ran = subprocess.run([java, '-Xms16m', '-Xmx64m', '-cp', str(work), 'GuardHarness'],
                                 capture_output=True, timeout=30, check=False)
            (evidence / (arm + '.stdout')).write_bytes(ran.stdout)
            (evidence / (arm + '.stderr')).write_bytes(ran.stderr)
            assert ran.stderr == b''
            cases = [json.loads(line) for line in ran.stdout.decode('utf-8').splitlines()]
            assert len(cases) == 8
            results[arm] = {'source_sha256': sha(source_raw), 'source_bytes': len(source_raw),
                            'fragment_sha256': sha(fragment.encode()), 'harness_sha256': sha(harness.encode()),
                            'compiler_returncode': built.returncode, 'test_returncode': ran.returncode,
                            'stdout_sha256': sha(ran.stdout), 'stderr_sha256': sha(ran.stderr),
                            'cases': cases, 'passed': sum(row['passed'] for row in cases), 'total': len(cases)}
    assert results['preimage']['test_returncode'] == 1
    assert [row['case'] for row in results['preimage']['cases'] if not row['passed']] == [
        'same_id_tree_changed_window_envelope', 'final_window_digest_missing']
    assert results['candidate']['test_returncode'] == 0 and results['candidate']['passed'] == 8
    report = {'schema': 1, 'state': 'EXACT_JAVA_FRAGMENT_DIFFERENTIAL_PASS', 'arms': results,
              'only_expected_source_delta': True, 'patch_sha256': sha(patch.encode()),
              'preimage_unchanged': sha((ROOT / 'preimage' / RELATIVE).read_bytes()) == PREIMAGE_SHA256,
              'scope': 'final action-window predicate and its unchanged immediate cleanup/deadline order',
              'test_type': 'compiled production-source fragment with controlled IO seams',
              'actual_Android_actions': 0, 'APK_built': False, 'installed': False,
              'App_production_qualification': False,
              'seams': ['inspect supplies captures or rejection', 'JSON string field storage',
                        'Capture.close counter', 'deadline clock', 'post-guard dispatch marker'],
              'not_claimed': ['complete ActionRunner Android compilation', 'live window geometry race',
                              'whole action method lifecycle', 'current Bili buffering cause',
                              'full App or platform readiness']}
    save_json(evidence / 'result.json', report)
    print(json.dumps({'state': report['state'], 'preimage': '6/8, expected exit 1',
                      'candidate': '8/8, exit 0', 'actual_Android_actions': 0,
                      'App_production_qualification': False}, sort_keys=True))


if __name__ == '__main__':
    main()
