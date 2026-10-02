// TrillionniumOS S08 exact-pin qualification server.
// The original perform_retained_action corpus remains unchanged in S07; this adapter uses its checked successor. This code is appended to
// Servo's existing accessibility integration test after the reviewed S07
// retained-node patch has been applied. It is inert in ordinary Servo tests.
#[test]
fn test_trillionnium_s08_mailbox_server() {
    let Some(mailbox) = std::env::var_os("HEPTA_S08_MAILBOX") else {
        return;
    };
    let mailbox = std::path::PathBuf::from(mailbox);
    assert!(
        mailbox.is_absolute(),
        "qualification mailbox must be absolute"
    );
    std::fs::create_dir_all(&mailbox).expect("create qualification mailbox");

    let initial = "data:text/html,<!doctype html><h1>Trillionnium S08 ready</h1>";
    let (servo_test, delegate, webview, mut tree) = build_webview_and_tree(initial);
    let mut current_url = webview
        .url()
        .map(|value| value.to_string())
        .unwrap_or_else(|| initial.to_owned());
    let mut retained: Option<(ActionRequest, servo::AccessibilitySemanticExpectation)> = None;
    let mut click_count = 0_u64;
    let mut navigation_count = 0_u64;
    let mut command_count = 0_usize;

    s08_write_atomic(&mailbox.join("servo-ready"), "ready=1\n")
        .expect("publish exact-pin Servo readiness");

    loop {
        let sequence = command_count + 1;
        let command_path = mailbox.join(format!("command-{sequence:04}.kv"));
        let fields = s08_wait_record(&servo_test, &command_path)
            .unwrap_or_else(|error| panic!("wait for product command {sequence}: {error}"));
        std::fs::remove_file(&command_path).expect("remove consumed product command");
        assert_eq!(s08_field(&fields, "version").expect("command version"), "1");
        assert_eq!(
            s08_field(&fields, "sequence").expect("command sequence"),
            sequence.to_string()
        );
        let request_id = s08_field(&fields, "request_id")
            .expect("command request id")
            .to_owned();
        let kind = s08_field(&fields, "kind").expect("command kind");
        let mut response = std::collections::BTreeMap::<String, String>::new();
        response.insert("status".to_owned(), "ok".to_owned());
        response.insert("sequence".to_owned(), sequence.to_string());
        response.insert("request_id".to_owned(), request_id);

        match kind {
            "health" => {
                response.insert("real_servo".to_owned(), "true".to_owned());
                response.insert("servo_commit_bound".to_owned(), "true".to_owned());
                // Health is unbound. Never expose or bind the bootstrap data URL
                // as the BrowserActor's current page identity.
            }
            "create" => {
                retained = None;
                click_count = 0;
                response.insert("real_servo".to_owned(), "true".to_owned());
                response.insert("current_url".to_owned(), "about:blank".to_owned());
            }
            "navigate" => {
                let raw = s08_field(&fields, "url").expect("navigation URL");
                assert!(
                    raw.starts_with("http://127.0.0.1:"),
                    "S08 accepts only the loopback qualification fixture"
                );
                let url = Url::parse(raw).expect("parse bounded fixture URL");
                delegate.reset();
                let load_webview = webview.clone();
                webview.load(url.clone());
                servo_test.spin(move || {
                    load_webview.url() != Some(url.clone())
                        || load_webview.load_status() != LoadStatus::Complete
                });
                tree = build_tree(wait_for_min_updates(&servo_test, delegate.clone(), 2));
                current_url = webview
                    .url()
                    .map(|value| value.to_string())
                    .expect("navigated WebView URL");
                assert_eq!(current_url, raw);
                retained = None;
                click_count = 0;
                navigation_count += 1;
                let button = find_labeled_node(&tree, Role::Button, "Action target");
                assert!(button.data().supports_action(Action::Click));
                response.insert("current_url".to_owned(), current_url.clone());
                response.insert(
                    "servo_navigation_count".to_owned(),
                    navigation_count.to_string(),
                );
            }
            "observe" => {
                assert!(
                    s08_field(&fields, "observation_fields")
                        .expect("observation fields")
                        .split(',')
                        .any(|value| value == "role")
                );
                let button = find_labeled_node(&tree, Role::Button, "Action target");
                assert!(button.data().supports_action(Action::Click));
                let expected = s08_semantic_expectation(&servo_test, &webview, button)
                    .expect("current retained metadata must fit the semantic schema");
                retained = Some((action_request(button, Action::Click, None), expected));
                response.insert("current_url".to_owned(), current_url.clone());
                response.insert(
                    "target_frame_id".to_owned(),
                    expected.tree_id().0.to_string(),
                );
                response.insert(
                    "target_backend_node_key".to_owned(),
                    s08_node_key(expected.node_id()),
                );
                response.insert(
                    "target_role".to_owned(),
                    match expected.role() {
                        Role::Button => "button".to_owned(),
                        _ => panic!("unsupported observed role"),
                    },
                );
                response.insert(
                    "target_accessible_name_sha256".to_owned(),
                    s08_digest_hex(expected.accessible_name_sha256()),
                );
                response.insert(
                    "target_structural_fingerprint".to_owned(),
                    s08_digest_hex(expected.structural_fingerprint()),
                );
            }
            "wait" => {
                assert_eq!(
                    s08_field(&fields, "wait_type").expect("wait type"),
                    "element_present"
                );
                assert_eq!(
                    s08_field(&fields, "target_frame_id").expect("wait frame"),
                    retained
                        .as_ref()
                        .expect("retained metadata")
                        .1
                        .tree_id()
                        .0
                        .to_string()
                );
                assert_eq!(
                    s08_field(&fields, "target_backend_node_key").expect("wait target"),
                    s08_node_key(retained.as_ref().expect("retained metadata").1.node_id())
                );
                let button = find_labeled_node(&tree, Role::Button, "Action target");
                assert!(button.data().supports_action(Action::Click));
                response.insert("element_present".to_owned(), "true".to_owned());
                response.insert("current_url".to_owned(), current_url.clone());
            }
            "act" => {
                assert_eq!(s08_field(&fields, "action").expect("action"), "click");
                assert_eq!(
                    s08_field(&fields, "target_frame_id").expect("act frame"),
                    retained
                        .as_ref()
                        .expect("retained metadata")
                        .1
                        .tree_id()
                        .0
                        .to_string()
                );
                assert_eq!(
                    s08_field(&fields, "target_backend_node_key").expect("act target"),
                    s08_node_key(retained.as_ref().expect("retained metadata").1.node_id())
                );
                assert_eq!(
                    s08_field(&fields, "target_role").expect("act role"),
                    "button"
                );
                assert_eq!(
                    s08_field(&fields, "target_accessible_name_sha256").expect("act name digest"),
                    s08_digest_hex(
                        retained
                            .as_ref()
                            .expect("retained metadata")
                            .1
                            .accessible_name_sha256()
                    )
                );
                assert_eq!(
                    s08_field(&fields, "target_structural_fingerprint")
                        .expect("act structural digest"),
                    s08_digest_hex(
                        retained
                            .as_ref()
                            .expect("retained metadata")
                            .1
                            .structural_fingerprint()
                    )
                );
                let (request, expected) =
                    retained.take().expect("observe must retain one Servo node");
                assert_eq!(
                    s08_perform_checked_action(&servo_test, &webview, request, expected),
                    AccessibilityActionResult::Dispatched
                );
                apply_updates(
                    &mut tree,
                    wait_for_min_updates(&servo_test, delegate.clone(), 1),
                );
                let count = find_labeled_node(&tree, Role::Heading, "Click count 1");
                assert_eq!(count.label().as_deref(), Some("Click count 1"));
                assert!(
                    find_optional_labeled_node(&tree, Role::Heading, "Click count 2").is_none(),
                    "one BrowserActor command must not dispatch twice"
                );
                click_count = 1;
                response.insert("click_count".to_owned(), click_count.to_string());
                response.insert("current_url".to_owned(), current_url.clone());
            }
            "snapshot" => {
                if click_count == 1 {
                    let count = find_labeled_node(&tree, Role::Heading, "Click count 1");
                    assert_eq!(count.label().as_deref(), Some("Click count 1"));
                }
                response.insert("click_count".to_owned(), click_count.to_string());
                response.insert("current_url".to_owned(), current_url.clone());
                response.insert("real_servo".to_owned(), "true".to_owned());
            }
            "close" => {
                retained = None;
                response.insert("closed".to_owned(), "true".to_owned());
                response.insert("current_url".to_owned(), current_url.clone());
            }
            other => panic!("unsupported S08 mailbox operation {other:?}"),
        }

        let response_path = mailbox.join(format!("response-{sequence:04}.kv"));
        s08_write_response(&response_path, &response).expect("publish Servo response");
        command_count = sequence;
        if kind == "close" {
            break;
        }
    }

    assert_eq!(command_count, 9);
    assert_eq!(navigation_count, 2);
    assert_eq!(
        click_count, 0,
        "second navigation must replace the clicked document"
    );
    let result = format!(
        concat!(
            "{{\n",
            "  \"schema\": \"trillionnium.desktop.s08-servo-host-result.v1\",\n",
            "  \"status\": \"PASS_EXACT_PIN_REAL_SERVO\",\n",
            "  \"servo_commands\": {},\n",
            "  \"servo_navigation_count\": {},\n",
            "  \"retained_node_click_dispatched_exactly_once\": true,\n",
            "  \"external_navigation_enabled\": false,\n",
            "  \"installed_image_proven\": false,\n",
            "  \"physical_hardware_proven\": false,\n",
            "  \"release_proven\": false\n",
            "}}\n"
        ),
        command_count, navigation_count,
    );
    s08_write_atomic(&mailbox.join("s08-servo-result.json"), &result)
        .expect("write exact-pin Servo result");
}

fn s08_digest_hex(value: [u8; 32]) -> String {
    value.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn s08_node_key(value: NodeId) -> String {
    format!("accesskit-node-{:016x}", value.0)
}

fn s08_semantic_expectation(
    servo_test: &ServoTest,
    webview: &servo::WebView,
    target: accesskit_consumer::Node<'_>,
) -> Option<servo::AccessibilitySemanticExpectation> {
    let (node_id, tree_id) = target.locate();
    if webview.active_document_accesskit_tree_id()? != tree_id {
        return None;
    }
    let responses = Arc::new(Mutex::new(Vec::new()));
    let captured = responses.clone();
    let callback = GenericCallback::new(move |result| {
        captured
            .lock()
            .expect("observation callback mutex")
            .push(result.expect("observation callback transport"));
    })
    .expect("observation callback");
    webview.observe_accessibility_semantics(tree_id, node_id, callback);
    let pending = responses.clone();
    servo_test.spin(move || {
        pending
            .lock()
            .expect("observation callback mutex")
            .is_empty()
    });
    for _ in 0..8 {
        servo_test.servo.spin_event_loop();
    }
    let results = responses.lock().expect("observation callback mutex");
    assert_eq!(results.len(), 1, "read-only observation must complete once");
    match results[0] {
        servo::AccessibilitySemanticObservationResult::Observed(current) => {
            assert_eq!(current.tree_id(), tree_id);
            assert_eq!(current.node_id(), node_id);
            Some(current)
        }
        servo::AccessibilitySemanticObservationResult::Refused(_) => None,
    }
}

fn s08_perform_checked_action(
    servo_test: &ServoTest,
    webview: &servo::WebView,
    request: ActionRequest,
    expected: servo::AccessibilitySemanticExpectation,
) -> AccessibilityActionResult {
    let responses = Arc::new(Mutex::new(Vec::new()));
    let captured = responses.clone();
    let callback = GenericCallback::new(move |result| {
        captured
            .lock()
            .expect("semantic callback mutex")
            .push(result.expect("semantic callback transport"));
    })
    .expect("semantic callback");
    webview.perform_checked_accessibility_action(request, expected, callback);
    let pending = responses.clone();
    servo_test.spin(move || pending.lock().expect("semantic callback mutex").is_empty());
    for _ in 0..8 {
        servo_test.servo.spin_event_loop();
    }
    let results = responses.lock().expect("semantic callback mutex");
    assert_eq!(results.len(), 1, "checked action must complete once");
    results[0]
}

// Real Servo corpus: page-side mutation is test stimulus, never action fallback.
// The final checked click uses the retained AccessKit identity and expected metadata only.
#[test]
fn test_trillionnium_s08_semantic_custody() {
    let Some(output) = std::env::var_os("HEPTA_S08_SEMANTIC_RESULTS") else {
        return;
    };
    let output = std::path::PathBuf::from(output);
    assert!(output.is_absolute());
    let cases = [
        (
            "same_node_label",
            "target.textContent='Changed target'",
            AccessibilityActionResult::TargetSemanticMismatch,
        ),
        (
            "same_node_role",
            "target.setAttribute('role','heading')",
            AccessibilityActionResult::TargetSemanticMismatch,
        ),
        (
            "same_node_ancestry",
            "document.getElementById('other').appendChild(target)",
            AccessibilityActionResult::TargetSemanticMismatch,
        ),
        (
            "replacement",
            "target.replaceWith(target.cloneNode(true))",
            AccessibilityActionResult::StaleNode,
        ),
        (
            "disabled",
            "target.disabled=true",
            AccessibilityActionResult::TargetDisabled,
        ),
        (
            "hidden",
            "target.style.display='none'",
            AccessibilityActionResult::TargetNotRendered,
        ),
    ];
    let mut completed = Vec::new();
    for (name, mutation, expected_result) in cases {
        let url = r#"data:text/html,<!doctype html>
            <main><button id='target' onclick='document.getElementById("count").textContent="Semantic click count 1"'>Action target</button></main>
            <aside id='other'></aside><h1 id='count'>Semantic click count 0</h1>
            <h2 id='marker'>Mutation pending</h2>"#;
        let (servo_test, delegate, webview, mut tree) = build_webview_and_tree(url);
        let target = find_labeled_node(&tree, Role::Button, "Action target");
        let original_location = target.locate();
        let expected =
            s08_semantic_expectation(&servo_test, &webview, target).expect("actual metadata");
        let request = action_request(target, Action::Click, None);
        let stimulus = format!(
            "let target=document.getElementById('target'); {mutation}; document.getElementById('marker').textContent='Mutation done';"
        );
        let _ = evaluate_javascript(&servo_test, webview.clone(), &stimulus);
        // Do not refresh the consumer expectation. Script must reflow and remeasure itself.
        let result = s08_perform_checked_action(&servo_test, &webview, request, expected);
        assert_eq!(result, expected_result, "typed semantic refusal");
        apply_updates(
            &mut tree,
            wait_for_min_updates(&servo_test, delegate.clone(), 1),
        );
        let root = assert_tree_structure_and_get_root_web_area(&tree);
        if name.starts_with("same_node_") {
            assert!(
                find_first_matching_node(root, |node| node.locate() == original_location).is_some(),
                "mutation must preserve actual retained node identity"
            );
        }
        assert_eq!(
            find_labeled_node(&tree, Role::Heading, "Semantic click count 0")
                .label()
                .as_deref(),
            Some("Semantic click count 0")
        );
        assert!(
            find_optional_labeled_node(&tree, Role::Heading, "Semantic click count 1").is_none(),
            "refused action must dispatch zero clicks"
        );
        assert!(
            matches!(
                evaluate_javascript(
                    &servo_test,
                    webview.clone(),
                    "document.getElementById('count').textContent === 'Semantic click count 0'"
                ),
                Ok(servo::JSValue::Boolean(true))
            ),
            "real refused target DOM click counter must be zero"
        );
        completed.push(format!(
            "{{\"case\":\"{name}\",\"refusal\":\"{result:?}\",\"dom_click_count\":0}}"
        ));
    }

    // A retained typed expectation with a stale epoch is refused on the real final script path.
    let (servo_test, _delegate, webview, tree) = build_webview_and_tree(
        "data:text/html,<!doctype html><button onclick='document.getElementById(\"count\").textContent=\"Epoch click count 1\"'>Epoch target</button><h1 id='count'>Epoch click count 0</h1>",
    );
    let target = find_labeled_node(&tree, Role::Button, "Epoch target");
    let actual =
        s08_semantic_expectation(&servo_test, &webview, target).expect("actual epoch observation");
    let mut stale_builder = servo::AccessibilitySemanticBuilder::new(
        actual.tree_id(),
        actual
            .epoch()
            .checked_sub(1)
            .expect("actual loaded document has advanced its epoch"),
    );
    let mut current = target;
    loop {
        let (id, tree_id) = current.locate();
        if tree_id != actual.tree_id() {
            break;
        }
        assert!(stale_builder.push(id, current.data()));
        current = current.parent().expect("actual grafted ancestry");
    }
    let stale = stale_builder
        .finish()
        .expect("fixed-size stale expectation");
    assert_eq!(
        s08_perform_checked_action(
            &servo_test,
            &webview,
            action_request(target, Action::Click, None),
            stale
        ),
        AccessibilityActionResult::TargetSemanticMismatch
    );
    let unchanged = evaluate_javascript(
        &servo_test,
        webview.clone(),
        "document.getElementById('count').textContent === 'Epoch click count 0'",
    );
    assert!(
        matches!(unchanged, Ok(servo::JSValue::Boolean(true))),
        "real DOM must retain zero epoch clicks"
    );
    completed.push("{\"case\":\"stale_epoch_expectation\",\"refusal\":\"TargetSemanticMismatch\",\"dom_click_count\":0}".to_owned());
    let result = format!(
        "{{\"schema\":\"trillionnium.desktop.s08-semantic-result.v1\",\"servo_commit\":\"670ae8a70801b162e186f81cbb5bdd2d59c39108\",\"case_count\":7,\"cases\":[{}],\"final_same_script_task_check\":true,\"installed_image_proven\":false,\"final_peer_control_custody_proven\":false}}\n",
        completed.join(",")
    );
    s08_write_atomic(&output, &result).expect("write bounded semantic corpus result");
}

fn s08_wait_record(
    servo_test: &ServoTest,
    path: &std::path::Path,
) -> Result<std::collections::BTreeMap<String, String>, String> {
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(120);
    loop {
        if path.is_file() {
            return s08_parse_record(path);
        }
        if std::time::Instant::now() >= deadline {
            return Err(format!("mailbox timeout at {}", path.display()));
        }
        servo_test.servo.spin_event_loop();
        std::thread::sleep(std::time::Duration::from_millis(2));
    }
}

fn s08_parse_record(
    path: &std::path::Path,
) -> Result<std::collections::BTreeMap<String, String>, String> {
    let text = std::fs::read_to_string(path)
        .map_err(|error| format!("read {}: {error}", path.display()))?;
    if text.len() > 32 * 1024 {
        return Err("mailbox command exceeds 32 KiB".to_owned());
    }
    let mut fields = std::collections::BTreeMap::new();
    for line in text.lines() {
        let (key, value) = line
            .split_once('=')
            .ok_or_else(|| format!("mailbox line has no separator: {line:?}"))?;
        if key.is_empty()
            || key.len() > 64
            || !key
                .bytes()
                .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
        {
            return Err(format!("invalid mailbox key {key:?}"));
        }
        if value.len() > 8 * 1024 || value.chars().any(char::is_control) {
            return Err(format!("invalid mailbox value for {key}"));
        }
        if fields.insert(key.to_owned(), value.to_owned()).is_some() {
            return Err(format!("duplicate mailbox key {key}"));
        }
    }
    Ok(fields)
}

fn s08_field<'a>(
    fields: &'a std::collections::BTreeMap<String, String>,
    key: &str,
) -> Result<&'a str, String> {
    fields
        .get(key)
        .map(String::as_str)
        .ok_or_else(|| format!("mailbox record lacks {key}"))
}

fn s08_write_response(
    path: &std::path::Path,
    fields: &std::collections::BTreeMap<String, String>,
) -> Result<(), String> {
    let mut text = String::new();
    for (key, value) in fields {
        if key.is_empty()
            || value
                .chars()
                .any(|character| matches!(character, '\n' | '\r' | '='))
        {
            return Err(format!("invalid response field {key:?}"));
        }
        text.push_str(key);
        text.push('=');
        text.push_str(value);
        text.push('\n');
    }
    s08_write_atomic(path, &text)
}

fn s08_write_atomic(path: &std::path::Path, content: &str) -> Result<(), String> {
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or("mailbox path has no UTF-8 file name")?;
    let temporary = path.with_file_name(format!(".{file_name}.{}.tmp", std::process::id()));
    std::fs::write(&temporary, content)
        .map_err(|error| format!("write {}: {error}", temporary.display()))?;
    std::fs::rename(&temporary, path)
        .map_err(|error| format!("publish {}: {error}", path.display()))
}
