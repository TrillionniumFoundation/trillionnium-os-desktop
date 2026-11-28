//! ActivityManager observations for a single, owner-bound Firefox VIEW invocation.
use serde::Serialize;

/// ActivityManager's classification of the process hosting the resolved Activity.
#[derive(Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum ActivityLaunchState {
    /// New Activity process.
    Cold,
    /// Existing process, newly created Activity.
    Warm,
    /// Existing Activity brought to the foreground.
    Hot,
    /// Activity recreated in an existing process.
    Relaunch,
    /// ActivityManager did not classify the launch.
    Unknown,
}

/// A complete Android WaitResult for the Activity, with no Gecko renderer claim.
#[derive(Debug, Serialize)]
pub struct FirefoxActivityStart {
    /// Flattened component reported by ActivityManager.
    pub component: String,
    /// Framework classification, independent of elapsed time.
    pub launch_state: ActivityLaunchState,
    /// Total launch time when supplied by ActivityManager.
    pub total_time_ms: Option<u64>,
    /// Time spent by the shell waiting for the framework.
    pub wait_time_ms: u64,
}

fn millis(field: &str) -> Result<u64, String> {
    if !field.is_empty() && field.bytes().all(|b| b.is_ascii_digit())
        && let Ok(ms) = field.parse::<i64>()
    {
        return Ok(ms as u64);
    }
    Err("invalid ActivityManager elapsed time".into())
}

fn component(value: &str) -> bool {
    let Some(class) = value.strip_prefix("org.mozilla.firefox/") else {
        return false;
    };
    class.strip_prefix('.').unwrap_or(class).split('.').all(|part| {
        let mut chars = part.bytes();
        chars.next().is_some_and(|c| c.is_ascii_alphabetic() || matches!(c, b'_' | b'$'))
            && chars.all(|c| c.is_ascii_alphanumeric() || matches!(c, b'_' | b'$'))
    })
}

/// Parse one `cmd activity start-activity -W` response. Older responses without
/// a launch classification still permit the existing partial invocation report.
pub fn firefox_activity_start(output: &str) -> Result<Option<FirefoxActivityStart>, String> {
    let invalid = "Android did not return one complete, consistent Firefox ActivityManager result";
    let mut lines = output.lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .peekable();
    if let Some(banner) = lines.next_if(|line| line.starts_with("Starting: Intent {")) {
        for field in banner.split_ascii_whitespace() {
            if field.strip_prefix("act=").is_some_and(|v| v != "android.intent.action.VIEW")
                || field.strip_prefix("dat=").is_some_and(|v| !v.starts_with("https:"))
                || field == "cat=[android.intent.category.HOME]"
            {
                return Err(invalid.into());
            }
        }
    }
    let warning = lines.next_if(|line| line.starts_with("Warning: Activity not started"));
    // A retained task can be brought forward after its Activity process died.
    // ActivityMetricsLogger then reports a cold launch despite this warning.
    let task_to_front = Some(
        "Warning: Activity not started, its current task has been brought to the front",
    );
    if lines.next() != Some("Status: ok") {
        return Err(invalid.into());
    }
    let state = lines.next_if(|line| line.starts_with("LaunchState: "))
        .map(|line| match &line["LaunchState: ".len()..] {
            "COLD" if warning.is_none() || warning == task_to_front => Ok(ActivityLaunchState::Cold),
            "WARM" => Ok(ActivityLaunchState::Warm),
            "HOT" => Ok(ActivityLaunchState::Hot),
            "RELAUNCH" => Ok(ActivityLaunchState::Relaunch),
            raw if raw.strip_prefix("UNKNOWN (").and_then(|v| v.strip_suffix(')'))
                .and_then(|v| v.parse::<i32>().ok()).is_some_and(|v| !(1..=4).contains(&v)) =>
                Ok(ActivityLaunchState::Unknown),
            _ => Err(invalid),
        }).transpose()?;
    let activity = lines.next().and_then(|line| line.strip_prefix("Activity: "))
        .filter(|name| component(name)).ok_or(invalid)?;
    if state.is_none() && lines.peek().is_none() {
        return Ok(None);
    }
    if state.is_none()
        && let Some(line) = lines.next_if(|line| line.starts_with("ThisTime: "))
    {
        millis(&line["ThisTime: ".len()..])?;
    }
    let total_time_ms = lines.next_if(|line| line.starts_with("TotalTime: "))
        .map(|line| millis(&line["TotalTime: ".len()..])).transpose()?;
    let Some(wait) = lines.next() else {
        return Ok(None);
    };
    if wait == "Complete" && lines.peek().is_none() {
        return Ok(None);
    }
    let wait_time_ms = millis(wait.strip_prefix("WaitTime: ").ok_or(invalid)?)?;
    match lines.next() {
        None => return Ok(None),
        Some("Complete") if lines.next().is_none() => {}
        _ => return Err(invalid.into()),
    }
    Ok(state.map(|launch_state| FirefoxActivityStart {
        component: activity.into(),
        launch_state,
        total_time_ms,
        wait_time_ms,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    const COLD: &str = "Starting: Intent { act=android.intent.action.VIEW }\nStatus: ok\nLaunchState: COLD\nActivity: org.mozilla.firefox/.HomeActivity\nTotalTime: 80\nWaitTime: 115\nComplete";

    #[test]
    fn complete_activity_results_distinguish_cold_reuse_and_unknown() {
        for (label, expected) in [
            ("COLD", ActivityLaunchState::Cold), ("WARM", ActivityLaunchState::Warm),
            ("HOT", ActivityLaunchState::Hot), ("RELAUNCH", ActivityLaunchState::Relaunch),
            ("UNKNOWN (0)", ActivityLaunchState::Unknown),
        ] {
            let observation = firefox_activity_start(&COLD.replace("COLD", label)).unwrap().unwrap();
            assert_eq!(observation.component, "org.mozilla.firefox/.HomeActivity");
            assert_eq!(observation.launch_state, expected);
            assert_eq!(observation.total_time_ms, Some(80));
            assert_eq!(observation.wait_time_ms, 115);
        }
        let retained_task = COLD.replace("Status:", "Warning: Activity not started, its current task has been brought to the front\nStatus:");
        assert_eq!(firefox_activity_start(&retained_task).unwrap().unwrap().launch_state, ActivityLaunchState::Cold);
        let reused = retained_task.replace("COLD", "HOT").replace("TotalTime: 80\n", "");
        let observation = firefox_activity_start(&reused).unwrap().unwrap();
        assert_eq!(observation.launch_state, ActivityLaunchState::Hot);
        assert_eq!(observation.total_time_ms, None);
    }

    #[test]
    fn legacy_invocation_does_not_supply_launch_state() {
        let minimal = "Status: ok\nActivity: org.mozilla.firefox/.HomeActivity";
        assert!(firefox_activity_start(minimal).unwrap().is_none());
        let older = format!("{minimal}\nThisTime: 15\nTotalTime: 55\nWaitTime: 60\nComplete");
        assert!(firefox_activity_start(&older).unwrap().is_none());
        for absent in ["WaitTime: 115\n", "Complete"] {
            assert!(firefox_activity_start(&COLD.replace(absent, "")).unwrap().is_none());
        }
    }

    #[test]
    fn partial_mixed_foreign_or_contradictory_activity_results_fail() {
        for (from, to) in [
            ("Status: ok", "Status: timeout"),
            ("Status: ok", "Status: timeout\nStatus: ok"),
            ("Status: ok", "Warning: Activity not started, intent has been delivered to currently running top-most instance.\nStatus: ok"),
            ("android.intent.action.VIEW", "android.intent.action.MAIN cat=[android.intent.category.HOME]"),
            ("android.intent.action.VIEW", "android.intent.action.VIEW dat=about:home"),
            ("android.intent.action.VIEW", "android.intent.action.VIEW cat=[android.intent.category.HOME]"),
            ("Status: ok", "Error: Activity not started\nStatus: ok"),
            ("LaunchState: COLD", "LaunchState: WARM\nLaunchState: COLD"),
            ("COLD", "UNKNOWN (1)"),
            ("org.mozilla.firefox/", "org.example/"),
            (".HomeActivity", ""),
            (".HomeActivity", ".HomeActivity/other"),
            ("TotalTime: 80", "Activity: org.example/.Home\nTotalTime: 80"),
            ("TotalTime: 80", "TotalTime: -1"),
            ("WaitTime: 115", "WaitTime: 1e2"),
            ("WaitTime: 115", "WaitTime: 9223372036854775808"),
            ("Complete", "Complete\nStatus: ok"),
        ] {
            assert!(firefox_activity_start(&COLD.replace(from, to)).is_err(), "{from} -> {to}");
        }
    }
}
