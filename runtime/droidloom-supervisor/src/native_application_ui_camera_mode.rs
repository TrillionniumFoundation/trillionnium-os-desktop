//! Source-bound Camera Photo preparation on the admitted working copy.
//!
//! Numeric module zero is established by the selected APK's actual Photo menu
//! callback and its completed menu transition. The Photo icon alone is not
//! evidence: the same APK renders that icon for capture-intent module six.
//! This preparation deliberately precedes the media/business preimage. It does
//! not read private preferences or claim restoration of their original values.
use super::{
    CAMERA, HeldRecord, NativeUiSession, Rect, RetainedScopedWindowPixels, SHUTTER,
    ScopedWindowPixels, Subject, before, need, wire,
};
use crate::control::{NativeApplicationInspector, application_probe::ApplicationInspection};
use serde::Serialize;
use serde_json::{Value, json};
use std::time::{Duration, Instant};

const APK_BYTES: u64 = 7_709_134;
const APK_SHA256: &str = "24632b0e1a1c22741177583b0dfd4a3fa71ff9b1d1b72af60a3d7cf373c7e61f";
const APK_VERSION: u64 = 20_002_000;
const DEX_SHA256: &str = "4eddb6e52ee5f7b6d3674627ce4fb2901e282bfd716407bbfe503e8ee039f4f6";
const SOURCE_METHOD_INDEX_SHA256: &str =
    "34ce94c16839660656bfc6aec0c0af0f5869ad683d695994ba567b8116a5bf53";
const LIST_ROOT: &str = "com.android.camera2:id/mode_list_layout";
const LIST: &str = "com.android.camera2:id/mode_list";
const LABEL: &str = "com.android.camera2:id/selector_text";
const ICON: &str = "com.android.camera2:id/selector_icon";
// The selected APK's strings, not a locale-dependent caller declaration.
const LABELS: [(&str, &str, &str, &str); 3] = [
    (
        "Camera",
        "Switch to Camera Mode",
        "Video",
        "Switch to Video Camera",
    ),
    ("相机", "切换到相机模式", "视频", "切换到摄像机模式"),
    ("相機", "切換至相機模式", "影片", "切換至攝影機"),
];
// At most five complete dumps, one MENU with its two task bookends, one actual
// Photo click with its two bookends, two scoped PNGs, and bounded local work.
// Every underlying operation still uses the same original session cutoff.
pub(super) const PREPARATION_SECONDS: u64 =
    5 * (70 + 2 * 15) + (15 + 2 * 15) + (70 + 2 * 15) + 2 * 110 + 30;

fn selected_application(application: &ApplicationInspection) -> Result<(), String> {
    need(
        application.package == CAMERA
            && application.user == 0
            && application.version_code == APK_VERSION
            && application.apks.len() == 1
            && application.apks[0].bytes == APK_BYTES
            && application.apks[0].sha256 == APK_SHA256,
        "Camera Photo preparation requires the actual complete source-admitted Camera APK",
    )
}

#[derive(Debug, Eq, PartialEq, Serialize)]
struct View {
    window_id: i64,
    bounds: Rect,
}
#[derive(Debug, Eq, PartialEq, Serialize)]
struct Control {
    window_id: i64,
    class: String,
    resource_id: String,
    description: String,
    text: String,
    bounds: Rect,
    clickable: bool,
}
#[derive(Debug, Eq, PartialEq, Serialize)]
struct Menu {
    view: View,
    photo: Control,
    video: Control,
    photo_label: Control,
    video_label: Control,
}
#[derive(Debug, Eq, PartialEq, Serialize)]
struct Completed {
    view: View,
    shutter: Control,
}
fn inside(inner: &Rect, outer: &Rect) -> bool {
    inner.left >= outer.left
        && inner.top >= outer.top
        && inner.right <= outer.right
        && inner.bottom <= outer.bottom
}
fn disjoint(a: &Rect, b: &Rect) -> bool {
    a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top
}
fn view(body: &Value) -> Result<View, String> {
    let c = &body["window_context"];
    let w = &c["selected_window"];
    let window_id = w["window_id"]
        .as_i64()
        .filter(|v| *v >= 0)
        .ok_or("Camera mode selected window absent")?;
    let nodes = body["nodes"]
        .as_array()
        .ok_or("Camera mode complete dump absent")?;
    need(
        c["display_id"] == 0
            && w["display_id"] == 0
            && w["type"] == 1
            && w["focused"] == true
            && w["root"]["package"] == CAMERA
            && c["root"]["package"] == CAMERA
            && w["root"]["window_id"] == window_id
            && c["root"]["window_id"] == window_id
            && c["snapshot_complete"] == true
            && c["truncated"] == false
            && c["null_child_count"] == 0
            && c["semantic_controls_available"] == true
            && c["tree_status"] == "available"
            && !nodes.is_empty()
            && nodes.len() <= 2_000
            && c["visible_count"].as_u64() == Some(nodes.len() as u64),
        "Camera mode requires the actual complete focused target tree on display zero",
    )?;
    Ok(View {
        window_id,
        bounds: Rect::parse(&w["bounds"])?,
    })
}
fn control(value: &Value, v: &View, clickable: bool) -> Result<Control, String> {
    let text = |key: &str, limit: usize| -> Result<String, String> {
        value[key]
            .as_str()
            .filter(|s| s.len() <= limit)
            .map(str::to_owned)
            .ok_or_else(|| format!("Camera mode control {key} missing or oversized"))
    };
    need(
        value["package"] == CAMERA
            && value["window_id"] == v.window_id
            && value["visible"] == true
            && value["enabled"] == true
            && value["clickable"].is_boolean()
            && (!clickable || value["clickable"] == true),
        "Camera mode control is not an enabled visible target in the same actual window",
    )?;
    let bounds = Rect::parse(&value["bounds_array"])?;
    need(
        inside(&bounds, &v.bounds),
        "Camera mode control escapes the actual window",
    )?;
    let class = text("class", 256)?;
    need(!class.is_empty(), "Camera mode accessibility class absent")?;
    Ok(Control {
        window_id: v.window_id,
        class,
        resource_id: text("resource-id", 256)?,
        description: text("content-desc", 512)?,
        text: text("text", 512)?,
        bounds,
        clickable: value["clickable"] == true,
    })
}
fn one<'a>(nodes: &'a [Value], predicate: impl Fn(&Value) -> bool) -> Result<&'a Value, String> {
    let mut matching = nodes.iter().filter(|node| predicate(node));
    let first = matching.next().ok_or("Camera mode exact control absent")?;
    need(
        matching.next().is_none(),
        "Camera mode exact control is ambiguous",
    )?;
    Ok(first)
}
fn menu_marker(node: &Value) -> bool {
    [LIST_ROOT, LIST, LABEL, ICON]
        .iter()
        .any(|id| node["resource-id"] == *id)
        || LABELS
            .iter()
            .any(|(_, p, _, v)| node["content-desc"] == *p || node["content-desc"] == *v)
}
fn menu(body: &Value) -> Result<Option<Menu>, String> {
    let v = view(body)?;
    let nodes = body["nodes"].as_array().ok_or("Camera mode nodes absent")?;
    if !nodes.iter().any(menu_marker) {
        return Ok(None);
    }
    // A partly rendered/unknown drawer is not treated as a closed drawer.
    let root = control(one(nodes, |n| n["resource-id"] == LIST_ROOT)?, &v, false)?;
    let list = control(one(nodes, |n| n["resource-id"] == LIST)?, &v, false)?;
    need(
        inside(&list.bounds, &root.bounds),
        "Camera mode list/root bounds differ",
    )?;
    let mut language = None;
    for labels in LABELS {
        if nodes.iter().any(|n| n["content-desc"] == labels.1) {
            need(
                language.is_none(),
                "Camera mode mixes multiple selected resource languages",
            )?;
            language = Some(labels);
        }
    }
    let (photo_text, photo_desc, video_text, video_desc) =
        language.ok_or("Camera Photo row is outside the fixed selected resource strings")?;
    let photo = control(one(nodes, |n| n["content-desc"] == photo_desc)?, &v, true)?;
    let video = control(one(nodes, |n| n["content-desc"] == video_desc)?, &v, true)?;
    need(
        photo.resource_id.is_empty()
            && video.resource_id.is_empty()
            && inside(&photo.bounds, &list.bounds)
            && inside(&video.bounds, &list.bounds)
            && disjoint(&photo.bounds, &video.bounds)
            && photo.class == video.class
            && nodes
                .iter()
                .filter(|n| {
                    LABELS
                        .iter()
                        .any(|(_, p, _, q)| n["content-desc"] == *p || n["content-desc"] == *q)
                })
                .count()
                == 2,
        "Camera Photo/Video rows are not the two distinct actual selected mode rows",
    )?;
    let labels: Vec<_> = nodes.iter().filter(|n| n["resource-id"] == LABEL).collect();
    need(
        labels.len() == 2,
        "Camera mode selected label count differs",
    )?;
    let photo_label = control(
        one(nodes, |n| {
            n["resource-id"] == LABEL && n["text"] == photo_text
        })?,
        &v,
        false,
    )?;
    let video_label = control(
        one(nodes, |n| {
            n["resource-id"] == LABEL && n["text"] == video_text
        })?,
        &v,
        false,
    )?;
    need(
        inside(&photo_label.bounds, &photo.bounds) && inside(&video_label.bounds, &video.bounds),
        "Camera mode labels do not belong to their actual selected rows",
    )?;
    Ok(Some(Menu {
        view: v,
        photo,
        video,
        photo_label,
        video_label,
    }))
}
fn completed(body: &Value) -> Result<Completed, String> {
    let v = view(body)?;
    let nodes = body["nodes"]
        .as_array()
        .ok_or("Camera completed nodes absent")?;
    need(
        !nodes.iter().any(menu_marker),
        "Camera mode selection has not completed hiding the menu",
    )?;
    let shutter = control(one(nodes, |n| n["resource-id"] == SHUTTER)?, &v, true)?;
    Ok(Completed { view: v, shutter })
}
fn clicked(body: &Value, selected: &Menu) -> Result<(), String> {
    need(
        body["performed"] == "click"
            && body["visual_verified"] == false
            && body["business_success_verified"] == false,
        "Camera Photo selection is not the actual normal click receipt",
    )?;
    // The helper may otherwise choose a clickable ancestor. Here both target
    // and actual target must be the observed source-owned Photo row itself.
    need(
        control(&body["target"], &selected.view, true)? == selected.photo
            && control(&body["actual_target"], &selected.view, true)? == selected.photo,
        "Camera Photo click selected another row, ancestor, window or bounds",
    )
}
fn rendered_region(
    width: u32,
    height: u32,
    rgb: &[u8],
    window: &Rect,
    rect: &Rect,
) -> Result<(), String> {
    need(
        width as usize == window.width()
            && height as usize == window.height()
            && rgb.len() == width as usize * height as usize * 3
            && inside(rect, window),
        "Camera mode raster and observed control bounds differ",
    )?;
    let x0 = (rect.left - window.left) as usize;
    let y0 = (rect.top - window.top) as usize;
    let first = &rgb[(y0 * width as usize + x0) * 3..][..3];
    let mut differs = false;
    let mut nonblack = false;
    for y in y0..y0 + rect.height() {
        for x in x0..x0 + rect.width() {
            let pixel = &rgb[(y * width as usize + x) * 3..][..3];
            differs |= pixel != first;
            nonblack |= pixel.iter().any(|v| *v != 0);
        }
    }
    // This proves only that the actual control region was rendered. Numeric
    // mode zero comes from the source-bound actual selection/completion chain.
    need(
        differs && nonblack,
        "Camera mode control region is blank or uniform",
    )
}
fn rendered(pixels: &ScopedWindowPixels, v: &View, controls: &[&Control]) -> Result<(), String> {
    pixels.verify_retained()?;
    need(
        pixels.window.package == CAMERA
            && pixels.window.display == 0
            && pixels.window.bounds == v.bounds,
        "Camera mode PNG and native selected window differ",
    )?;
    for item in controls {
        rendered_region(
            pixels.width,
            pixels.height,
            &pixels.rgb,
            &v.bounds,
            &item.bounds,
        )?;
    }
    Ok(())
}
fn record(
    session: &NativeUiSession<'_, '_>,
    name: &str,
    value: &Value,
) -> Result<HeldRecord, String> {
    let bytes = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    need(
        bytes.len() <= wire::WIRE_REPLY_BYTES,
        "Camera mode actual helper record exceeds its normal bound",
    )?;
    HeldRecord::create(session, name, &bytes)
}

/// Private, non-serializable preparation. Only the real owned session below
/// constructs it; comparison JSON cannot recreate its live origin or held FDs.
pub(super) struct CameraPhotoPreparation {
    subject: Subject,
    original_work_end: Instant,
    started_at: Instant,
    completed_at: Instant,
    menu: Menu,
    completed: Completed,
    menu_key_sent: bool,
    menu_pixels: RetainedScopedWindowPixels,
    completed_pixels: RetainedScopedWindowPixels,
    records: Vec<HeldRecord>,
}
impl CameraPhotoPreparation {
    pub(super) fn verify(&self) -> Result<(), String> {
        selected_application(&self.subject.application)?;
        need(
            self.subject
                .main
                .persistent_data
                .original_copy_origin
                .is_some()
                && self.started_at < self.completed_at
                && self.completed_at < self.original_work_end
                && self.completed_at.duration_since(self.started_at)
                    <= Duration::from_secs(PREPARATION_SECONDS)
                && self.menu.view == self.completed.view
                && self.menu_pixels.window == self.completed_pixels.window
                && self.records.len() == if self.menu_key_sent { 8 } else { 7 },
            "Camera preparation source, interval, same-window or fixed operation history changed",
        )?;
        self.menu_pixels.verify_retained()?;
        self.completed_pixels.verify_retained()?;
        for item in &self.records {
            item.verify()?;
        }
        Ok(())
    }
    pub(super) fn require_session(&self, session: &NativeUiSession<'_, '_>) -> Result<(), String> {
        self.verify()?;
        self.subject.require(session)?;
        need(
            self.original_work_end == session.work_end,
            "Camera preparation was moved to another session work cutoff",
        )
    }
    pub(super) fn require_transcript(
        &self,
        transcript: &super::super::NativeUiTranscript,
    ) -> Result<(), String> {
        self.verify()?;
        self.subject.require_transcript(transcript)?;
        self.menu_pixels.require_transcript(transcript)?;
        self.completed_pixels.require_transcript(transcript)?;
        need(
            transcript.opened_at <= self.started_at
                && self.completed_at <= transcript.finished_at
                && self.original_work_end <= transcript.original_end,
            "Camera preparation is outside its actual finished session",
        )
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        self.verify()?;
        Ok(json!({
            "schema":"droidloom.native-camera-photo-preparation.v1",
            "subject":self.subject.comparison(),
            "selected_apk":{"bytes":APK_BYTES,"sha256":APK_SHA256,"version_code":APK_VERSION,
                "classes_dex_sha256":DEX_SHA256,"mode_method_index_sha256":SOURCE_METHOD_INDEX_SHA256},
            "photo_row":self.menu.photo,"completed_shutter":self.completed.shutter,
            "menu_key_sent":self.menu_key_sent,"photo_click_count":1,
            "complete_dump_count":if self.menu_key_sent { 5 } else { 4 },
            "menu_pixels":self.menu_pixels.comparison()?,
            "completed_pixels":self.completed_pixels.comparison()?,
            "preparation_elapsed_millis":self.completed_at.duration_since(self.started_at).as_millis(),
            "held_records":self.records.iter().map(|v| json!({"name":v.name.to_string_lossy(),
                "bytes":v.identity.bytes,"sha256":v.sha256})).collect::<Vec<_>>(),
            "prepared_photo_module":0,
            "preparation_target":"admitted_working_copy",
            "business_preimage_follows_preparation":true,
            "original_private_preferences_read":false,
            "original_internal_mode_or_last_used_restoration_claimed":false,
            "prepared_mode_baseline_preserved_by_photo_case":false,
            "whole_photo_business_accepted":false,"comparison_only":true
        }))
    }
}

impl NativeUiSession<'_, '_> {
    fn camera_mode_dump(
        &mut self,
        inspector: &NativeApplicationInspector,
        records: &mut Vec<HeldRecord>,
        ordinal: &mut usize,
    ) -> Result<wire::Reply, String> {
        need(
            *ordinal < 5,
            "Camera mode fixed complete dump count exceeded",
        )?;
        let reply = self.dump(inspector)?;
        records.push(record(
            self,
            &format!("CAMERA-MODE-READ-{:02}.json", *ordinal),
            reply.body(),
        )?);
        *ordinal += 1;
        Ok(reply)
    }
    pub(super) fn prepare_camera_photo(
        &mut self,
        inspector: &NativeApplicationInspector,
    ) -> Result<CameraPhotoPreparation, String> {
        let started_at = Instant::now();
        self.guard(inspector, self.work_end)?;
        selected_application(self.baseline.application())?;
        need(
            self.baseline
                .main()
                .facts()
                .persistent_data
                .original_copy_origin
                .is_some(),
            "Camera mode preparation requires admitted working-copy lineage",
        )?;
        let subject = Subject::capture(self)?;
        // This create-only intent prevents a second preparation/mutation attempt.
        let mut records = vec![record(
            self,
            "CAMERA-PHOTO-PREPARATION-INTENT.json",
            &json!({
                "schema":"droidloom.native-camera-photo-preparation-intent.v1",
                "subject":subject.comparison(),"selected_apk_sha256":APK_SHA256,
                "target_mode":0,"automatic_retry":false,
                "intentional_working_copy_preparation":true,
                "original_mode_restore_claimed":false,"business_accepted":false
            }),
        )?];
        let mut ordinal = 0;
        let initial = self.camera_mode_dump(inspector, &mut records, &mut ordinal)?;
        let (selected, menu_key_sent) = match menu(initial.body())? {
            Some(found) => (found, false),
            None => {
                // An already-open drawer must never be toggled closed by MENU.
                // Only the actual normal Camera surface permits this one key.
                completed(initial.body())?;
                self.owned_task(inspector, self.work_end)?;
                self.run(
                    inspector,
                    "camera-open-photo-mode-menu",
                    ["/system/bin/input", "keyevent", "82"]
                        .map(str::to_owned)
                        .to_vec(),
                    true,
                    true,
                    Duration::from_secs(15),
                    super::super::super::NativeUiOutput::Small,
                    self.work_end,
                )?;
                self.owned_task(inspector, self.work_end)?;
                let opened = self.camera_mode_dump(inspector, &mut records, &mut ordinal)?;
                (
                    menu(opened.body())?
                        .ok_or("Camera MENU did not expose the fixed Photo/Video rows")?,
                    true,
                )
            }
        };
        let menu_pixels = self.scoped_window_pixels(inspector)?;
        rendered(
            &menu_pixels,
            &selected.view,
            &[&selected.photo, &selected.video],
        )?;
        let before_click = self.camera_mode_dump(inspector, &mut records, &mut ordinal)?;
        need(
            menu(before_click.body())?.as_ref() == Some(&selected),
            "Camera actual menu changed across its scoped PNG",
        )?;
        let menu_pixels = menu_pixels.into_retained()?;
        let selector = wire::Selector::description(&selected.photo.description)
            .map_err(|e| e.to_string())?
            .enabled();
        let clicked_reply = self.click(inspector, selector)?;
        clicked(clicked_reply.body(), &selected)?;
        records.push(record(
            self,
            "CAMERA-MODE-PHOTO-CLICK.json",
            clicked_reply.body(),
        )?);
        // One bounded settling allowance, not a successful-mode inference or an
        // automatic second click. The two complete actual observations below
        // must establish that the source-owned asynchronous transition ended.
        let pause = Duration::from_secs(2);
        need(
            self.work_end.saturating_duration_since(Instant::now()) > pause,
            "Camera mode completion has no time left in its original window",
        )?;
        std::thread::sleep(pause);
        self.guard(inspector, self.work_end)?;
        let first_completed = self.camera_mode_dump(inspector, &mut records, &mut ordinal)?;
        let completed = completed(first_completed.body())?;
        need(
            completed.view == selected.view,
            "Camera mode transition changed its actual selected window",
        )?;
        let completed_pixels = self.scoped_window_pixels(inspector)?;
        rendered(&completed_pixels, &completed.view, &[&completed.shutter])?;
        need(
            menu_pixels.window == completed_pixels.window,
            "Camera mode preparation changed its WindowManager token/activity/bounds",
        )?;
        let last_completed = self.camera_mode_dump(inspector, &mut records, &mut ordinal)?;
        need(
            self::completed(last_completed.body())? == completed,
            "Camera completed surface changed across its scoped PNG",
        )?;
        let completed_pixels = completed_pixels.into_retained()?;
        self.guard(inspector, self.work_end)?;
        let completed_at = Instant::now();
        need(
            completed_at.duration_since(started_at) <= Duration::from_secs(PREPARATION_SECONDS),
            "Camera mode preparation exceeded its fixed original allocation",
        )?;
        records.push(record(self, "CAMERA-PHOTO-PREPARATION.json", &json!({
            "schema":"droidloom.native-camera-photo-preparation-completed.v1",
            "subject":subject.comparison(),"target_mode":0,
            "menu_key_sent":menu_key_sent,"complete_dump_count":ordinal,"photo_click_count":1,
            "menu":selected,"completed":completed,
            "menu_png_sha256":menu_pixels.png.sha256,"completed_png_sha256":completed_pixels.png.sha256,
            "mode_source_index_sha256":SOURCE_METHOD_INDEX_SHA256,
            "original_private_preferences_read":false,
            "original_internal_mode_or_last_used_restoration_claimed":false,
            "preparation_precedes_media_preimage":true,"business_accepted":false
        }))?);
        let result = CameraPhotoPreparation {
            subject,
            original_work_end: self.work_end,
            started_at,
            completed_at,
            menu: selected,
            completed,
            menu_key_sent,
            menu_pixels,
            completed_pixels,
            records,
        };
        result.require_session(self)?;
        before(self.work_end)?;
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn node(id: &str, desc: &str, text: &str, bounds: [u32; 4], click: bool) -> Value {
        json!({"package":CAMERA,"window_id":7,"class":"android.widget.FrameLayout",
            "resource-id":id,"content-desc":desc,"text":text,"bounds_array":bounds,
            "enabled":true,"visible":true,"clickable":click})
    }
    fn body(nodes: Vec<Value>) -> Value {
        let root = json!({"package":CAMERA,"window_id":7});
        json!({"nodes":nodes,"window_context":{"display_id":0,
            "selected_window":{"display_id":0,"type":1,"focused":true,"window_id":7,
                "bounds":[0,0,320,480],"root":root},
            "root":root,"snapshot_complete":true,"truncated":false,"null_child_count":0,
            "semantic_controls_available":true,"tree_status":"available","visible_count":nodes.len()}})
    }
    fn menu_body() -> Value {
        body(vec![
            node(LIST_ROOT, "", "", [0, 0, 320, 480], false),
            node(LIST, "", "", [0, 50, 320, 250], false),
            node("", "Switch to Camera Mode", "", [0, 50, 320, 150], true),
            node("", "Switch to Video Camera", "", [0, 150, 320, 250], true),
            node(LABEL, "", "Camera", [64, 55, 300, 145], false),
            node(LABEL, "", "Video", [64, 155, 300, 245], false),
        ])
    }
    fn closed_body() -> Value {
        body(vec![node(
            SHUTTER,
            "Shutter",
            "",
            [120, 380, 200, 460],
            true,
        )])
    }
    fn append(body: &mut Value, node: Value) {
        let list = body["nodes"].as_array_mut().unwrap();
        list.push(node);
        let len = list.len();
        body["window_context"]["visible_count"] = json!(len);
    }
    #[test]
    fn native_camera_mode_requires_unique_source_rows_and_exact_language_labels() {
        assert!(menu(&menu_body()).unwrap().is_some());
        assert!(menu(&closed_body()).unwrap().is_none());
        let mut duplicate = menu_body();
        append(
            &mut duplicate,
            node("", "Switch to Camera Mode", "", [0, 250, 320, 350], true),
        );
        assert!(menu(&duplicate).is_err());
        let mut foreign = menu_body();
        foreign["nodes"][2]["package"] = json!("com.android.settings");
        assert!(menu(&foreign).is_err());
        let mut mismatch = menu_body();
        mismatch["nodes"][4]["text"] = json!("Video");
        assert!(menu(&mismatch).is_err());
        let mut window = menu_body();
        window["nodes"][2]["window_id"] = json!(8);
        assert!(menu(&window).is_err());
        let mut partial = menu_body();
        partial["window_context"]["truncated"] = json!(true);
        assert!(menu(&partial).is_err());
    }
    #[test]
    fn native_camera_mode_click_cannot_substitute_a_clickable_ancestor_or_another_row() {
        let source = menu_body();
        let selected = menu(&source).unwrap().unwrap();
        let target = source["nodes"][2].clone();
        let good = json!({"performed":"click","visual_verified":false,"business_success_verified":false,
            "target":target,"actual_target":target});
        assert!(clicked(&good, &selected).is_ok());
        let mut ancestor = good.clone();
        ancestor["actual_target"]["bounds_array"] = json!([0, 0, 320, 480]);
        assert!(clicked(&ancestor, &selected).is_err());
        let mut other = good.clone();
        other["actual_target"] = source["nodes"][3].clone();
        assert!(clicked(&other, &selected).is_err());
        let mut foreign = good.clone();
        foreign["target"]["window_id"] = json!(8);
        assert!(clicked(&foreign, &selected).is_err());
    }
    #[test]
    fn native_camera_mode_completion_requires_a_closed_menu_and_actual_shutter() {
        assert!(completed(&closed_body()).is_ok());
        assert!(completed(&menu_body()).is_err());
        let mut still_open = closed_body();
        append(
            &mut still_open,
            node(LIST_ROOT, "", "", [0, 0, 320, 480], false),
        );
        assert!(completed(&still_open).is_err());
        let mut disabled = closed_body();
        disabled["nodes"][0]["enabled"] = json!(false);
        assert!(completed(&disabled).is_err());
        let mut duplicate = closed_body();
        append(&mut duplicate, node(SHUTTER, "", "", [0, 0, 80, 80], true));
        assert!(completed(&duplicate).is_err());
    }
    #[test]
    fn native_camera_mode_rendering_checks_only_owned_actual_control_regions() {
        let window = Rect {
            left: 10,
            top: 20,
            right: 14,
            bottom: 24,
        };
        let region = Rect {
            left: 11,
            top: 21,
            right: 13,
            bottom: 23,
        };
        let mut rgb = vec![20u8; 4 * 4 * 3];
        rgb[(1 * 4 + 1) * 3] = 255;
        assert!(rendered_region(4, 4, &rgb, &window, &region).is_ok());
        assert!(rendered_region(4, 4, &vec![0; 48], &window, &region).is_err());
        assert!(rendered_region(4, 4, &vec![20; 48], &window, &region).is_err());
        assert!(
            rendered_region(
                4,
                4,
                &rgb,
                &window,
                &Rect {
                    left: 9,
                    top: 20,
                    right: 11,
                    bottom: 22
                }
            )
            .is_err()
        );
        assert!(rendered_region(4, 4, &rgb[..47], &window, &region).is_err());
        assert_eq!(PREPARATION_SECONDS, 895);
    }
}
