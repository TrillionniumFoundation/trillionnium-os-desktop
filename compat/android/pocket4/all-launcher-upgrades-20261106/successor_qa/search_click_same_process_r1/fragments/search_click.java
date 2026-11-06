    // This new operation is only for the observed Beike search button.
    // The old act() implementation and its old cross-process comparison remain unchanged.
    static final String SEARCH_RESOURCE = "com.lianjia.beike:id/tv_nav_right_search_text";
    static final String SEARCH_CLASS = "android.widget.TextView";
    static final String SEARCH_TEXT = "\u641c\u7d22";
    // Two complete captures plus the existing result metadata must fit MAX_RESULT.
    // This is a narrower bound for the new operation, not a larger old result budget.
    static final int MAX_SEARCH_CAPTURE = (MAX_RESULT - 65536) / 2;

    static JSONObject fixedSearchNode(JSONObject inspection) throws Exception {
        need(inspection.getBoolean("complete") && "visible-non-password-subtrees".equals(inspection.getString("traversal")),
            "SEARCH_COMPLETE_TREE_REQUIRED");
        JSONObject window = inspection.getJSONObject("window");
        JSONArray nodes = inspection.getJSONArray("nodes");
        need(PACKAGE.equals(window.getString("package")) && integer(window,"display") == 0
            && integer(window,"type") == 1 && window.getBoolean("focused")
            && hashJson(window).equals(inspection.getString("window_sha256"))
            && 0 < nodes.length() && nodes.length() <= MAX_NODES
            && hashJson(nodes).equals(inspection.getString("tree_sha256")), "SEARCH_COMPLETE_TREE_WINDOW_HASH");
        JSONObject selected = null; int matches = 0;
        for (int i = 0; i < nodes.length(); i++) {
            JSONObject row = nodes.getJSONObject(i);
            if (row.getBoolean("visible") && !row.getBoolean("password") && row.getBoolean("enabled")
                && row.getBoolean("clickable") && SEARCH_RESOURCE.equals(row.getString("resource_id"))
                && SEARCH_CLASS.equals(row.getString("class")) && SEARCH_TEXT.equals(row.getString("text"))
                && !row.getBoolean("resource_id_truncated") && !row.getBoolean("class_truncated")
                && !row.getBoolean("text_truncated")) {
                need(PACKAGE.equals(row.getString("package")), "SEARCH_TARGET_PACKAGE_CHANGED");
                selected = row; matches++;
            }
        }
        need(matches == 1, "ONE_EXACT_ELIGIBLE_BEIKE_SEARCH_REQUIRED");
        return selected;
    }

    Capture searchCapture(String path, String purpose, int index, JSONObject[] captured) throws Exception {
        Capture value = inspect(path, purpose);
        captured[index] = value.json;
        try {
            need(canonical(value.json).getBytes(StandardCharsets.UTF_8).length <= MAX_SEARCH_CAPTURE,
                "SEARCH_PAIRED_DIAGNOSTIC_CAPTURE_BOUND");
            return value;
        } catch (Exception primary) {
            try { value.close(); } catch (Exception secondary) { primary.addSuppressed(secondary); }
            throw primary;
        }
    }

    JSONObject searchPrivateDiagnostic(JSONObject[] captured, JSONObject refreshed, Exception error) throws Exception {
        int last = -1;
        for (int i = 0; i < captured.length; i++) if (captured[i] != null) last = i;
        JSONObject diagnostic = new JSONObject().put("schema", 1).put("private_UI_evidence", true)
            .put("reason", errorCode(error)).put("captured_before_dispatch", !actionAttempted)
            .put("current_post_action_state_proven", false).put("original_result_budget", MAX_RESULT)
            .put("pair_capture_budget", MAX_SEARCH_CAPTURE).put("selection_full_omitted_for_result_budget", false);
        JSONArray records = new JSONArray();
        String[] roles = new String[]{"selection", "target", "final"};
        if (last >= 0) {
            // Keep the complete last capture even when a size gate rejected it.
            // Never truncate a tree, remove a dynamic node, or invent a failed capture.
            int lastBytes = canonical(captured[last]).getBytes(StandardCharsets.UTF_8).length;
            if (last > 0 && captured[0] != null) {
                int firstBytes = canonical(captured[0]).getBytes(StandardCharsets.UTF_8).length;
                boolean fits = firstBytes <= MAX_SEARCH_CAPTURE && lastBytes <= MAX_SEARCH_CAPTURE;
                if (fits) records.put(new JSONObject().put("role", "selection").put("inspection", captured[0]));
                else diagnostic.put("selection_full_omitted_for_result_budget", true)
                    .put("selection_binding", playerCaptureBindingJson(captured[0]));
            }
            records.put(new JSONObject().put("role", roles[last]).put("inspection", captured[last]));
        }
        diagnostic.put("complete_captures", records).put("complete_capture_available", last >= 0);
        if (refreshed != null) diagnostic.put("refreshed_target_node", refreshed);
        return diagnostic;
    }

    static JSONObject playerCaptureBindingJson(JSONObject captured) throws Exception {
        return new JSONObject().put("tree_sha256", captured.getString("tree_sha256"))
            .put("window_sha256", captured.getString("window_sha256"))
            .put("connection_scoped_window_id", integer(captured,"connection_scoped_window_id"))
            .put("observed_elapsed_ms", integer(captured,"observed_elapsed_ms"));
    }

    void searchClick(final JSONObject request, final JSONObject result) throws Exception {
        final String priorNonce = string(request,"inspection_nonce",32);
        final String priorHash = string(request,"inspection_sha256",64);
        need(!priorNonce.equals(string(request,"nonce",32)) && priorHash.matches("[0-9a-f]{64}"),
            "SEARCH_DISTINCT_PRIOR_NONCE_AND_HASH");
        byte[] previousRaw = readInspection(priorNonce);
        need(hash(previousRaw).equals(priorHash), "SEARCH_PRIOR_BYTES_CHANGED");
        JSONObject previous = new JSONObject(new String(previousRaw,StandardCharsets.UTF_8));
        need(PROTOCOL.equals(previous.getString("protocol")) && "inspect".equals(previous.getString("op"))
            && priorNonce.equals(previous.getString("nonce")) && previous.getBoolean("ok")
            && previous.getBoolean("claim_persistence_completed") && previous.getBoolean("helper_work_completed")
            && !previous.getBoolean("action_attempted") && previous.getJSONObject("restoration").getBoolean("service_info_verified"),
            "SEARCH_SUCCESSFUL_RESTORED_CONTEXT_REQUIRED");
        need(canonical(previous.getJSONObject("host_scope_attestation")).equals(canonical(request.getJSONObject("scope"))),
            "SEARCH_PRIOR_HOST_SCOPE_CHANGED");
        final JSONObject prior = previous.getJSONObject("inspection");
        long priorAge = SystemClock.elapsedRealtime() - integer(prior,"observed_elapsed_ms");
        need(priorAge >= 0 && priorAge <= MAX_INSPECTION_AGE_MS, "SEARCH_PRIOR_INSPECTION_TOO_OLD");
        JSONObject priorNode = fixedSearchNode(prior);
        final String path = string(request,"node_path",160), nodeHash = string(request,"node_sha256",64);
        need(path.matches("0(?:/[0-9]{1,2}){0,32}") && nodeHash.matches("[0-9a-f]{64}")
            && path.equals(priorNode.getString("path")) && nodeHash.equals(priorNode.getString("node_sha256")),
            "SEARCH_PRIOR_EXACT_NODE_BINDING");
        final JSONObject[] captured = new JSONObject[3];
        final JSONObject[] refreshed = new JSONObject[1];
        final Capture[] currentTarget = new Capture[1];
        result.put("inspection_nonce", priorNonce).put("inspection_sha256", priorHash)
            .put("prior_whole_tree_is_context_only", true).put("prior_target_and_window_still_required", true)
            .put("prior_window_sha256", prior.getString("window_sha256"))
            .put("atomic_android_transaction", false).put("search_contract", "fixed-beike-search-three-capture-v1");
        try {
            // Original bounded event-quiet gate, once, before the new selection capture.
            waitForInspectionIdle();
            PlayerButtonTransaction.run(new PlayerButtonTransaction.Backend<Capture,JSONObject>() {
                @Override public Capture inspectSelection() throws Exception {
                    return searchCapture(null,"search_selection",0,captured);
                }
                @Override public JSONObject selectCurrent(Capture first) throws Exception {
                    JSONObject selected = fixedSearchNode(first.json);
                    need(path.equals(selected.getString("path")) && nodeHash.equals(selected.getString("node_sha256")),
                        "SEARCH_OBSERVED_TARGET_IDENTITY_CHANGED");
                    need(first.json.getString("window_sha256").equals(prior.getString("window_sha256"))
                        && canonical(first.json.getJSONObject("window")).equals(canonical(prior.getJSONObject("window"))),
                        "SEARCH_PRIOR_STABLE_WINDOW_CHANGED");
                    return selected;
                }
                @Override public Capture inspectTarget(JSONObject selected) throws Exception {
                    Capture current = searchCapture(path,"action_target",1,captured);
                    currentTarget[0] = current; return current;
                }
                @Override public void requireSameWholeTreeAndWindow(Capture first,Capture target) throws Exception {
                    need(first.windowId == target.windowId
                        && first.json.getString("tree_sha256").equals(target.json.getString("tree_sha256"))
                        && first.json.getString("window_sha256").equals(target.json.getString("window_sha256")),
                        "SEARCH_CURRENT_TREE_OR_WINDOW_CHANGED");
                }
                void refreshExact(Capture current) throws Exception {
                    need(current != null && current.target != null && current.target.refresh(), "TARGET_REFRESH_FAILED");
                    refreshed[0] = node(current.target,path);
                    need(hashJson(refreshed[0]).equals(nodeHash), "TARGET_CHANGED_BEFORE_ACTION");
                    need(current.target.getWindowId() == current.windowId && current.target.isEnabled()
                        && current.target.isVisibleToUser() && !current.target.isPassword()
                        && current.target.isClickable(), "ACTION_TARGET_NOT_ELIGIBLE");
                }
                @Override public void requireRefreshedTarget(Capture target,JSONObject selected) throws Exception {
                    refreshExact(target);
                }
                @Override public Capture inspectFinal() throws Exception {
                    return searchCapture(null,"action_final_window",2,captured);
                }
                @Override public void requireFinalWholeTreeAndWindow(Capture target,Capture last) throws Exception {
                    need(last.windowId == target.windowId
                        && last.json.getString("tree_sha256").equals(target.json.getString("tree_sha256"))
                        && last.json.getString("window_sha256").equals(target.json.getString("window_sha256")),
                        "FOCUS_CHANGED_BEFORE_ACTION");
                }
                @Override public void bindEvidence(Capture first,Capture target,Capture last,JSONObject selected) throws Exception {
                    result.put("search_selection",first.json).put("search_selection_sha256",hashJson(first.json))
                        .put("target_node_path",path).put("target_node_sha256",nodeHash)
                        .put("action_window",target.json.getJSONObject("window"))
                        .put("connection_scoped_window_id",target.windowId)
                        .put("search_capture_bindings",new JSONArray().put(playerCaptureBinding(first))
                            .put(playerCaptureBinding(target)).put(playerCaptureBinding(last)))
                        .put("same_connection_full_tree_rechecks",2);
                }
                @Override public long selectedAt(Capture first) throws Exception { return integer(first.json,"observed_elapsed_ms"); }
                @Override public long now() { return SystemClock.elapsedRealtime(); }
                @Override public void beforeAction(long admitted,long age) throws Exception {
                    timeBound(); refreshExact(currentTarget[0]);
                    long actual = SystemClock.elapsedRealtime(), actualAge = actual - integer(captured[0],"observed_elapsed_ms");
                    need(actual >= admitted && actualAge >= 0 && actualAge <= PlayerButtonTransaction.MAX_SELECTION_AGE_MS,
                        "SEARCH_SELECTION_TOO_OLD_AFTER_FINAL_REFRESH");
                    timeBound();
                    result.put("search_action_admitted_elapsed_ms",actual).put("search_selection_age_ms",actualAge)
                        .put("search_selection_age_limit_ms",PlayerButtonTransaction.MAX_SELECTION_AGE_MS)
                        .put("target_refresh_count",2);
                }
                @Override public boolean clickOnce(Capture target) throws Exception {
                    actionAttempted = true;
                    boolean acknowledged = target.target.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    result.put("node_action","ACTION_CLICK").put("node_action_returned",acknowledged);
                    return acknowledged;
                }
                @Override public void close(Capture value) { value.close(); }
            });
        } catch (Exception primary) {
            // Preserve the original failure. No retry or action is issued by diagnostics.
            result.remove("search_selection");
            try { result.put("search_private_diagnostic",searchPrivateDiagnostic(captured,refreshed[0],primary)); }
            catch (Exception secondary) {
                primary.addSuppressed(secondary);
                result.put("search_diagnostic_error",errorCode(secondary));
            }
            throw primary;
        }
    }
