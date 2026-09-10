
// TrillionniumOS S08 exact-pin qualification server. This code is appended to
// Servo's existing accessibility integration test after the reviewed S07
// retained-node patch has been applied. It is inert in ordinary Servo tests.
#[test]
fn test_trillionnium_s08_mailbox_server() {
    let Some(mailbox) = std::env::var_os("HEPTA_S08_MAILBOX") else {
        return;
    };
    let mailbox = std::path::PathBuf::from(mailbox);
    assert!(mailbox.is_absolute(), "qualification mailbox must be absolute");
    std::fs::create_dir_all(&mailbox).expect("create qualification mailbox");

    let initial = "data:text/html,<!doctype html><h1>Trillionnium S08 ready</h1>";
    let (servo_test, delegate, webview, mut tree) = build_webview_and_tree(initial);
    let mut current_url = webview
        .url()
        .map(|value| value.to_string())
        .unwrap_or_else(|| initial.to_owned());
    let mut retained: Option<ActionRequest> = None;
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
        assert_eq!(
            s08_field(&fields, "version").expect("command version"),
            "1"
        );
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
                    load_webview.url() != Some(url.clone()) ||
                        load_webview.load_status() != LoadStatus::Complete
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
                retained = Some(action_request(button, Action::Click, None));
                response.insert("current_url".to_owned(), current_url.clone());
                response.insert("target_frame_id".to_owned(), "main-frame".to_owned());
                response.insert(
                    "target_backend_node_key".to_owned(),
                    "servo-retained-button-1".to_owned(),
                );
                response.insert("target_role".to_owned(), "button".to_owned());
                response.insert(
                    "target_accessible_name_sha256".to_owned(),
                    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                        .to_owned(),
                );
                response.insert(
                    "target_structural_fingerprint".to_owned(),
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                        .to_owned(),
                );
            }
            "wait" => {
                assert_eq!(
                    s08_field(&fields, "wait_type").expect("wait type"),
                    "element_present"
                );
                assert_eq!(
                    s08_field(&fields, "target_frame_id").expect("wait frame"),
                    "main-frame"
                );
                assert_eq!(
                    s08_field(&fields, "target_backend_node_key").expect("wait target"),
                    "servo-retained-button-1"
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
                    "main-frame"
                );
                assert_eq!(
                    s08_field(&fields, "target_backend_node_key").expect("act target"),
                    "servo-retained-button-1"
                );
                assert_eq!(
                    s08_field(&fields, "target_role").expect("act role"),
                    "button"
                );
                assert_eq!(
                    s08_field(&fields, "target_accessible_name_sha256")
                        .expect("act name digest"),
                    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                );
                assert_eq!(
                    s08_field(&fields, "target_structural_fingerprint")
                        .expect("act structural digest"),
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                );
                let request = retained.take().expect("observe must retain one Servo node");
                assert_eq!(
                    perform_retained_action(&servo_test, &webview, request),
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
    assert_eq!(click_count, 0, "second navigation must replace the clicked document");
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
        command_count,
        navigation_count,
    );
    s08_write_atomic(&mailbox.join("s08-servo-result.json"), &result)
        .expect("write exact-pin Servo result");
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
