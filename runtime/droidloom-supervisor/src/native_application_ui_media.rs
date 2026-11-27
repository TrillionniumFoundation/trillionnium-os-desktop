//! Fixed Camera/window observations borrowed from the live native UI owner.
//!
//! Only this child of NativeUiSession can execute the literal operations below.
//! The returned objects contain actual decoded observations, not business gates.
//! In particular JPEG validity does not establish that its scene matches the
//! preview, and a screenshot does not establish video/audio or recovery.
use super::{Identity, NativeUiSession, before, need};
use crate::control::NativeApplicationInspector;
use crate::control::application_probe::ApplicationInspection;
use crate::main_custody::RuntimeMainCustody;
use crate::native_application_ui_protocol as wire;
use flate2::bufread::ZlibDecoder;
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::CString;
use std::fs::File;
use std::io::{Cursor, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::FileExt;
use std::time::{Duration, Instant};
use zune_jpeg::{
    JpegDecoder,
    zune_core::{bytestream::ZCursor, colorspace::ColorSpace, options::DecoderOptions},
};

const CAMERA: &str = "com.android.camera2";
const SHUTTER: &str = "com.android.camera2:id/shutter_button";
const IMAGES: &str = "content://media/external/images/media";
const PREFS: &str =
    "data/user/0/com.android.camera2/shared_prefs/com.android.camera2_preferences.xml";
const MAX_IMAGE: usize = 32 * 1024 * 1024;
const MAX_AXIS: usize = 8192;
const MAX_PIXELS: usize = 32_000_000;
const MAX_MEDIA_TEXT: usize = 4 * 1024 * 1024;
const MAX_MEDIA_ROWS: usize = 65_536;
const MEDIA_FIELDS: [&str; 11] = [
    "_id",
    "_data",
    "_display_name",
    "mime_type",
    "_size",
    "width",
    "height",
    "orientation",
    "date_added",
    "is_pending",
    "owner_package_name",
];

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[derive(Debug, Eq, PartialEq, Serialize)]
struct Rect {
    left: u32,
    top: u32,
    right: u32,
    bottom: u32,
}
impl Rect {
    fn parse(value: &Value) -> Result<Self, String> {
        let a = value
            .as_array()
            .filter(|a| a.len() == 4)
            .ok_or("window bounds absent")?;
        let n = a
            .iter()
            .map(|v| v.as_u64().and_then(|n| u32::try_from(n).ok()))
            .collect::<Option<Vec<_>>>()
            .ok_or("window bounds are negative or nonnumeric")?;
        let result = Self {
            left: n[0],
            top: n[1],
            right: n[2],
            bottom: n[3],
        };
        need(
            result.right > result.left
                && result.bottom > result.top
                && result.right as usize <= MAX_AXIS
                && result.bottom as usize <= MAX_AXIS,
            "window bounds are empty or exceed the fixed display bound",
        )?;
        Ok(result)
    }
    fn width(&self) -> usize {
        (self.right - self.left) as usize
    }
    fn height(&self) -> usize {
        (self.bottom - self.top) as usize
    }
}

#[derive(Debug, Eq, PartialEq, Serialize)]
struct Window {
    package: String,
    activity: String,
    window_manager_token: String,
    display: u32,
    bounds: Rect,
    init_host_pid: u32,
}
fn window(reply: &wire::Reply, wm: &[u8], package: &str, init: u32) -> Result<Window, String> {
    let context = &reply.body()["window_context"];
    let selected = &context["selected_window"];
    need(
        context["display_id"] == 0
            && selected["display_id"] == 0
            && selected["type"] == 1
            && selected["focused"] == true
            && selected["root"]["package"] == package
            && context["root"]["package"] == package,
        "the actual selected window is not the target on display zero",
    )?;
    let bounds = Rect::parse(&selected["bounds"])?;
    let (token, activity) = focused_window(wm, package)?;
    Ok(Window {
        package: package.into(),
        activity,
        window_manager_token: token,
        display: 0,
        bounds,
        init_host_pid: init,
    })
}
fn focused_window(raw: &[u8], package: &str) -> Result<(String, String), String> {
    need(
        !raw.is_empty() && raw.len() <= MAX_MEDIA_TEXT,
        "window-manager output bound",
    )?;
    let text = std::str::from_utf8(raw).map_err(|_| "window-manager output is not UTF-8")?;
    let mut observations = BTreeSet::new();
    for line in text.lines() {
        let Some((_, rest)) = line.split_once("mCurrentFocus=Window{") else {
            continue;
        };
        let (body, tail) = rest
            .split_once('}')
            .ok_or("truncated window-manager focus")?;
        need(
            tail.trim().is_empty(),
            "unknown trailing window-manager focus fields",
        )?;
        let fields: Vec<_> = body.split_whitespace().collect();
        need(
            fields.len() == 3
                && fields[1] == "u0"
                && !fields[0].is_empty()
                && fields[0].len() <= 32
                && fields[0]
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "unknown or foreign-user window-manager focus",
        )?;
        let (actual, activity) = fields[2].split_once('/').ok_or("focus component absent")?;
        need(
            actual == package
                && !activity.is_empty()
                && activity.len() <= 512
                && activity
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._$".contains(&b)),
            "window-manager focus belongs to another package or component",
        )?;
        observations.insert((fields[0].to_owned(), activity.to_owned()));
    }
    need(
        observations.len() == 1,
        "window-manager focus is missing or ambiguous",
    )?;
    Ok(observations.into_iter().next().unwrap())
}

struct Subject {
    application: ApplicationInspection,
    main: RuntimeMainCustody,
    task: u32,
    journal: [u64; 5],
    journal_path: std::path::PathBuf,
}
impl Subject {
    fn capture(session: &NativeUiSession<'_, '_>) -> Result<Self, String> {
        Ok(Self {
            application: session.baseline.application().clone(),
            main: session.baseline.main().facts().clone(),
            task: session
                .task
                .ok_or("native media has no actual owned task")?,
            journal: session.journal.identity,
            journal_path: session.journal.path.clone(),
        })
    }
    fn require(&self, session: &NativeUiSession<'_, '_>) -> Result<(), String> {
        need(
            self.application == *session.baseline.application()
                && self.main == *session.baseline.main().facts()
                && Some(self.task) == session.task
                && self.journal == session.journal.identity
                && self.journal_path == session.journal.path,
            "native media observation belongs to another Main, package, task, or session",
        )
    }
    fn require_transcript(&self, transcript: &super::NativeUiTranscript) -> Result<(), String> {
        need(
            self.application == *transcript.engine().application()
                && self.main == transcript.engine().facts().main
                && self.task == transcript.task()
                && self.journal_path == transcript.journal()
                && self.journal == transcript.journal_custody.identity,
            "native media and transcript differ in complete application, Main, task, or journal",
        )
    }
    fn comparison(&self) -> Value {
        serde_json::json!({"application":self.application,"main":self.main,"task":self.task,
            "same_session_journal_identity":self.journal,"journal":self.journal_path,"comparison_only":true})
    }
}

/// The file is created from actual run() stdout while those bytes remain owned
/// by the normal factory. The same new FD is retained, not reopened as evidence.
struct HeldRecord {
    directory: File,
    directory_identity: [u64; 5],
    file: File,
    name: CString,
    identity: Identity,
    sha256: String,
}
impl HeldRecord {
    fn create(session: &NativeUiSession<'_, '_>, name: &str, bytes: &[u8]) -> Result<Self, String> {
        session.journal.verify()?;
        need(
            !bytes.is_empty()
                && bytes.len() <= MAX_IMAGE
                && !name.is_empty()
                && name
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b)),
            "native media evidence name or byte bound",
        )?;
        let name = CString::new(name).map_err(|_| "native media evidence name")?;
        let raw = unsafe {
            libc::openat(
                session.journal.directory.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDWR | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0o600,
            )
        };
        if raw < 0 {
            return Err(std::io::Error::last_os_error().to_string());
        }
        // SAFETY: openat returned a uniquely owned ordinary descriptor.
        let mut file = unsafe { File::from_raw_fd(raw) };
        file.write_all(bytes)
            .and_then(|_| file.sync_all())
            .and_then(|_| session.journal.directory.sync_all())
            .map_err(|e| e.to_string())?;
        let identity = Identity::of(&file.metadata().map_err(|e| e.to_string())?);
        need(
            identity.mode == libc::S_IFREG | 0o600
                && identity.uid == 0
                && identity.gid == 0
                && identity.links == 1
                && identity.bytes == bytes.len() as u64,
            "native media evidence is not the new root-owned regular file",
        )?;
        let result = Self {
            directory: session
                .journal
                .directory
                .try_clone()
                .map_err(|e| e.to_string())?,
            directory_identity: session.journal.identity,
            file,
            name,
            identity,
            sha256: hash(bytes),
        };
        result.verify()?;
        Ok(result)
    }
    fn verify(&self) -> Result<(), String> {
        need(
            super::directory_identity(&self.directory).map_err(|e| e.to_string())?
                == self.directory_identity
                && Identity::of(&self.file.metadata().map_err(|e| e.to_string())?) == self.identity,
            "held native media evidence changed",
        )?;
        let raw = unsafe {
            libc::openat(
                self.directory.as_raw_fd(),
                self.name.as_ptr(),
                libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if raw < 0 {
            return Err(std::io::Error::last_os_error().to_string());
        }
        // SAFETY: openat returned a uniquely owned descriptor.
        let named = unsafe { File::from_raw_fd(raw) };
        need(
            Identity::of(&named.metadata().map_err(|e| e.to_string())?) == self.identity,
            "native media named evidence was replaced, even if its bytes match",
        )?;
        need(
            hash_file(&self.file, self.identity.bytes)? == self.sha256
                && Identity::of(&self.file.metadata().map_err(|e| e.to_string())?) == self.identity,
            "native media held evidence full digest differs",
        )
    }
}
fn hash_file(file: &File, bytes: u64) -> Result<String, String> {
    need(
        bytes > 0 && bytes <= MAX_IMAGE as u64,
        "native media retained file bound",
    )?;
    let mut hash = Sha256::new();
    let mut offset = 0;
    let mut block = [0_u8; 64 * 1024];
    while offset < bytes {
        let take = (bytes - offset).min(block.len() as u64) as usize;
        let n = file
            .read_at(&mut block[..take], offset)
            .map_err(|e| e.to_string())?;
        need(n != 0, "native media retained file shortened")?;
        hash.update(&block[..n]);
        offset += n as u64;
    }
    let mut extra = [0];
    need(
        file.read_at(&mut extra, offset)
            .map_err(|e| e.to_string())?
            == 0,
        "native media retained file grew",
    )?;
    Ok(format!("{:x}", hash.finalize()))
}

/// Actual display-zero screenshot, cropped using the observed window bounds.
/// No caller rectangle, full desktop pixels, or JSON constructor is exposed.
pub struct ScopedWindowPixels {
    subject: Subject,
    window: Window,
    width: u32,
    height: u32,
    rgb: Vec<u8>,
    pixels_sha256: String,
    png: HeldRecord,
}
impl ScopedWindowPixels {
    /// Consume an actual decoded observation after this case's visual comparisons.
    /// Historical custody keeps the original PNG OFD and complete source digest;
    /// decoded RGB does not accumulate across the fixed thirty-nine app suite.
    pub fn into_retained(self) -> Result<RetainedScopedWindowPixels, String> {
        self.verify_retained()?;
        let Self {
            subject,
            window,
            width,
            height,
            rgb,
            pixels_sha256,
            png,
        } = self;
        drop(rgb);
        Ok(RetainedScopedWindowPixels {
            subject,
            window,
            width,
            height,
            pixels_sha256,
            png,
        })
    }
    pub fn width(&self) -> u32 {
        self.width
    }
    pub fn height(&self) -> u32 {
        self.height
    }
    pub fn rgb(&self) -> &[u8] {
        &self.rgb
    }
    pub fn pixels_sha256(&self) -> &str {
        &self.pixels_sha256
    }
    pub fn verify_retained(&self) -> Result<(), String> {
        self.png.verify()
    }
    /// Match a genuine completed UI transcript; comparison values cannot create either object.
    pub fn require_transcript(&self, transcript: &super::NativeUiTranscript) -> Result<(), String> {
        self.verify_retained()?;
        self.subject.require_transcript(transcript)
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.verify_retained()?;
        Ok(
            serde_json::json!({"schema":"droidloom.native-ui-scoped-pixels.v1",
            "subject":self.subject.comparison(),"window":self.window,"dimensions":[self.width,self.height],
            "rgb_sha256":self.pixels_sha256,"complete_png_sha256":self.png.sha256,
            "full_desktop_pixels_exposed":false,"continuous_window_custody_claimed":false,
            "business_accepted":false}),
        )
    }
}

/// Historical scoped image custody after the case releases its decoded RGB.
/// This retains the actual original PNG descriptor and private decode facts.
/// It cannot be deserialized, cloned, or constructed from caller comparisons.
pub struct RetainedScopedWindowPixels {
    subject: Subject,
    window: Window,
    width: u32,
    height: u32,
    pixels_sha256: String,
    png: HeldRecord,
}
impl RetainedScopedWindowPixels {
    pub fn width(&self) -> u32 {
        self.width
    }
    pub fn height(&self) -> u32 {
        self.height
    }
    pub fn pixels_sha256(&self) -> &str {
        &self.pixels_sha256
    }
    pub fn verify_retained(&self) -> Result<(), String> {
        self.png.verify()
    }
    pub fn require_transcript(&self, transcript: &super::NativeUiTranscript) -> Result<(), String> {
        self.verify_retained()?;
        self.subject.require_transcript(transcript)
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.verify_retained()?;
        Ok(serde_json::json!({
            "schema":"droidloom.native-ui-retained-scoped-pixels.v1",
            "subject":self.subject.comparison(),"window":self.window,
            "dimensions":[self.width,self.height],"rgb_sha256":self.pixels_sha256,
            "complete_png_sha256":self.png.sha256,
            "decoded_pixels_retained":false,"full_desktop_pixels_exposed":false,
            "continuous_window_custody_claimed":false,"business_accepted":false
        }))
    }
}

/// This is only created after one real fixed shutter, its unique new MediaStore
/// row, complete same-FD body reads, and a full bounded RGB JPEG decode.
pub struct CameraPhotoObservation {
    subject: Subject,
    preview: ScopedWindowPixels,
    row: MediaRow,
    before_ids: BTreeSet<u64>,
    guest_shutter_seconds: u64,
    encoded: HeldRecord,
    source: AndroidFile,
    width: u32,
    height: u32,
    rgb: Vec<u8>,
    pixels_sha256: String,
}
impl CameraPhotoObservation {
    pub fn preview(&self) -> &ScopedWindowPixels {
        &self.preview
    }
    pub fn rgb(&self) -> &[u8] {
        &self.rgb
    }
    pub fn width(&self) -> u32 {
        self.width
    }
    pub fn height(&self) -> u32 {
        self.height
    }
    pub fn pixels_sha256(&self) -> &str {
        &self.pixels_sha256
    }
    pub fn verify_retained(&self) -> Result<(), String> {
        self.preview.verify_retained()?;
        self.encoded.verify()?;
        self.source.verify()
    }
    pub fn require_transcript(&self, transcript: &super::NativeUiTranscript) -> Result<(), String> {
        self.verify_retained()?;
        self.preview.require_transcript(transcript)?;
        self.subject.require_transcript(transcript)
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.verify_retained()?;
        Ok(
            serde_json::json!({"schema":"droidloom.native-camera-owned-photo.v1",
            "subject":self.subject.comparison(),"row":self.row,"preexisting_image_ids":self.before_ids,
            "guest_shutter_seconds":self.guest_shutter_seconds,
            "encoded_sha256":self.encoded.sha256,"encoded_bytes":self.encoded.identity.bytes,
            "decoded_dimensions":[self.width,self.height],"rgb_sha256":self.pixels_sha256,
            "one_fixed_shutter":true,"full_jpeg_decoded":true,"preview_scene_match_verified":false,
            "video_audio_playback_verified":false,"recovery_verified":false,"business_accepted":false}),
        )
    }
}

impl NativeUiSession<'_, '_> {
    fn media_text(
        &mut self,
        inspector: &NativeApplicationInspector,
        label: &str,
        argv: Vec<String>,
        shell: bool,
        cap: Duration,
        until: Instant,
    ) -> Result<Vec<u8>, String> {
        let out = self.run(
            inspector,
            label,
            argv,
            shell,
            false,
            cap,
            super::super::NativeUiOutput::Small,
            until.min(self.work_end),
        )?;
        need(
            !out.stdout.is_empty() && out.stdout.len() <= MAX_MEDIA_TEXT,
            "native media fixed text output bound",
        )?;
        Ok(out.stdout)
    }
    fn media_window(&mut self, inspector: &NativeApplicationInspector) -> Result<Window, String> {
        let request =
            wire::Request::new(&self.baseline.application().package, wire::Operation::Meta)
                .map_err(|e| e.to_string())?;
        let output = self.run(
            inspector,
            "scoped-window-meta",
            request.arguments().map_err(|e| e.to_string())?,
            true,
            false,
            Duration::from_secs(15),
            super::super::NativeUiOutput::Helper,
            self.work_end,
        )?;
        let reply = wire::Reply::parse(&request, &output).map_err(|e| {
            self.poisoned = true;
            e.to_string()
        })?;
        let wm = self.media_text(
            inspector,
            "scoped-window-manager",
            ["/system/bin/dumpsys", "window", "displays"]
                .map(str::to_owned)
                .to_vec(),
            false,
            Duration::from_secs(15),
            self.work_end,
        )?;
        window(
            &reply,
            &wm,
            &self.baseline.application().package,
            self.target.expected.init.host_pid,
        )
    }
    pub fn scoped_window_pixels(
        &mut self,
        inspector: &NativeApplicationInspector,
    ) -> Result<ScopedWindowPixels, String> {
        self.owned_task(inspector, self.work_end)?;
        let before_window = self.media_window(inspector)?;
        let output = self.run(
            inspector,
            "scoped-screencap",
            ["/system/bin/screencap", "-p"].map(str::to_owned).to_vec(),
            false,
            false,
            Duration::from_secs(20),
            super::super::NativeUiOutput::Image,
            self.work_end,
        )?;
        let sequence = self.sequence;
        let after_window = self.media_window(inspector)?;
        need(
            before_window == after_window,
            "actual target/WindowManager token/display/bounds changed around screencap",
        )?;
        self.owned_task(inspector, self.work_end)?;
        let (width, height, rgb) =
            decode_png_crop(&output.stdout, &before_window.bounds, self.work_end)?;
        self.guard(inspector, self.work_end)?;
        let png = HeldRecord::create(
            self,
            &format!("{sequence:04}-scoped-source.png"),
            &output.stdout,
        )?;
        let result = ScopedWindowPixels {
            subject: Subject::capture(self)?,
            window: before_window,
            width,
            height,
            pixels_sha256: pixel_hash(width, height, &rgb),
            rgb,
            png,
        };
        result.subject.require(self)?;
        self.journal.json(
            &format!("{sequence:04}-SCOPED-PIXELS.json"),
            &result.comparison()?,
        )?;
        self.guard(inspector, self.work_end)?;
        Ok(result)
    }
    fn camera_ids(
        &mut self,
        inspector: &NativeApplicationInspector,
        until: Instant,
    ) -> Result<BTreeSet<u64>, String> {
        let raw = self.media_text(
            inspector,
            "camera-image-id-set",
            [
                "/system/bin/content",
                "query",
                "--user",
                "0",
                "--uri",
                IMAGES,
                "--projection",
                "_id",
            ]
            .map(str::to_owned)
            .to_vec(),
            false,
            Duration::from_secs(15),
            until,
        )?;
        image_ids(&raw)
    }
    fn camera_row(
        &mut self,
        inspector: &NativeApplicationInspector,
        id: u64,
        seconds: u64,
        until: Instant,
    ) -> Result<Option<MediaRow>, String> {
        let raw = self.media_text(
            inspector,
            "camera-owned-image-row",
            vec![
                "/system/bin/content".into(),
                "query".into(),
                "--user".into(),
                "0".into(),
                "--uri".into(),
                format!("{IMAGES}/{id}"),
                "--projection".into(),
                MEDIA_FIELDS.join(":"),
            ],
            false,
            Duration::from_secs(15),
            until,
        )?;
        image_row(&raw, id, seconds)
    }
    /// One fixed Camera photo attempt. It does not change mode, permission,
    /// account, storage ownership, or an existing image. The intent's exclusive
    /// file is written before the shutter and permanently prevents a retry.
    pub fn capture_camera_photo(
        &mut self,
        inspector: &NativeApplicationInspector,
    ) -> Result<CameraPhotoObservation, String> {
        need(
            self.baseline.application().package == CAMERA,
            "the fixed photo factory only accepts the actual selected Camera",
        )?;
        self.guard(inspector, self.work_end)?;
        let mut prefs = AndroidFile::open(&self.target.root, PREFS, 128 * 1024)?;
        let mode_bytes = prefs.read(128 * 1024, self.work_end)?;
        photo_mode(&mode_bytes)?;
        let prefs_sha = hash(&mode_bytes);
        drop(mode_bytes);
        let selector = wire::Selector::resource_id(SHUTTER)
            .map_err(|e| e.to_string())?
            .enabled();
        let ready = self.find(inspector, selector.clone())?;
        let matches = ready.body()["matches"]
            .as_array()
            .ok_or("camera shutter matches absent")?;
        need(
            matches.len() == 1
                && matches[0]["clickable"] == true
                && matches[0]["visible"] == true
                && matches[0]["package"] == CAMERA,
            "one actual ready Camera shutter required",
        )?;
        let preview = self.scoped_window_pixels(inspector)?;
        let before_ids = self.camera_ids(inspector, self.work_end)?;
        let seconds_raw = self.media_text(
            inspector,
            "camera-shutter-guest-clock",
            ["/system/bin/date", "+%s"].map(str::to_owned).to_vec(),
            false,
            Duration::from_secs(10),
            self.work_end,
        )?;
        let guest_seconds = decimal_line(&seconds_raw)?;
        // A second invocation fails here before any new shutter is attempted.
        self.journal.json(
            "CAMERA-SHUTTER-INTENT.json",
            &serde_json::json!({
            "package":CAMERA,"task":self.task,"selector":SHUTTER,"guest_seconds":guest_seconds,
            "before_ids":before_ids,"photo_mode_preferences_sha256":prefs_sha,
            "automatic_retry":false,"business_accepted":false}),
        )?;
        prefs.verify()?;
        // This is the actual pre-shutter mode observation. The shutter may
        // legitimately update other Camera preferences; no post-action
        // immutability of the whole preferences document is claimed.
        drop(prefs);
        self.click(inspector, selector)?;
        let wait_end = (Instant::now() + Duration::from_secs(30)).min(self.work_end);
        let mut settled = None;
        for _ in 0..40 {
            before(wait_end)?;
            let ids = self.camera_ids(inspector, wait_end)?;
            if let Some(id) = new_image(&before_ids, &ids)? {
                if let Some(row) = self.camera_row(inspector, id, guest_seconds, wait_end)? {
                    settled = Some(row);
                    break;
                }
            }
            before(wait_end)?;
            std::thread::sleep(Duration::from_millis(150));
        }
        let row = settled
            .ok_or("the unique new Camera image did not settle within its original bound")?;
        self.guard(inspector, self.work_end)?;
        let mut source = AndroidFile::open(
            &self.target.root,
            row.path.trim_start_matches('/'),
            MAX_IMAGE,
        )?;
        let raw = source.read(MAX_IMAGE, self.work_end)?;
        need(
            raw.len() as u64 == row.bytes,
            "new Camera file size differs from its actual media row",
        )?;
        let (width, height, rgb) = decode_jpeg(&raw, self.work_end)?;
        need(
            [width, height] == [row.width, row.height]
                || (matches!(row.orientation, 90 | 270)
                    && [height, width] == [row.width, row.height]),
            "fully decoded Camera image dimensions differ from MediaStore",
        )?;
        let final_row = self
            .camera_row(inspector, row.id, guest_seconds, self.work_end)?
            .ok_or("owned Camera image row became pending")?;
        need(
            final_row == row
                && new_image(&before_ids, &self.camera_ids(inspector, self.work_end)?)?
                    == Some(row.id),
            "Camera image row or complete preexisting media set changed",
        )?;
        source.verify()?;
        self.owned_task(inspector, self.work_end)?;
        self.guard(inspector, self.work_end)?;
        let encoded = HeldRecord::create(self, "CAMERA-OWNED-PHOTO.jpg", &raw)?;
        let result = CameraPhotoObservation {
            subject: Subject::capture(self)?,
            preview,
            row,
            before_ids,
            guest_shutter_seconds: guest_seconds,
            encoded,
            source,
            width,
            height,
            pixels_sha256: pixel_hash(width, height, &rgb),
            rgb,
        };
        result.subject.require(self)?;
        self.journal
            .json("CAMERA-OWNED-PHOTO.json", &result.comparison()?)?;
        self.guard(inspector, self.work_end)?;
        Ok(result)
    }
}

#[repr(C)]
struct OpenHow {
    flags: u64,
    mode: u64,
    resolve: u64,
}
/// Fixed root-relative reads may follow ordinary Android /data and /storage
/// symlinks but never leave the retained Android root or follow a magic link.
fn android_open(root: &File, path: &str) -> Result<File, String> {
    need(
        !path.is_empty()
            && !path.starts_with('/')
            && !path
                .split('/')
                .any(|c| c.is_empty() || c == "." || c == ".."),
        "native media root-relative path shape",
    )?;
    let path = CString::new(path).map_err(|_| "native media root-relative path NUL")?;
    let how = OpenHow {
        flags: (libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NONBLOCK) as u64,
        mode: 0,
        resolve: 0x10 | 0x02,
    }; // RESOLVE_IN_ROOT | RESOLVE_NO_MAGICLINKS
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat2,
            root.as_raw_fd(),
            path.as_ptr(),
            &how,
            std::mem::size_of::<OpenHow>(),
        )
    };
    if fd < 0 {
        return Err(std::io::Error::last_os_error().to_string());
    }
    // SAFETY: a successful openat2 returned a uniquely owned descriptor.
    Ok(unsafe { File::from_raw_fd(fd as i32) })
}
struct AndroidFile {
    root: File,
    path: String,
    file: File,
    identity: Identity,
    sha256: Option<String>,
}
impl AndroidFile {
    fn open(root: &File, path: &str, limit: usize) -> Result<Self, String> {
        let file = android_open(root, path)?;
        let identity = Identity::of(&file.metadata().map_err(|e| e.to_string())?);
        need(
            identity.mode & libc::S_IFMT == libc::S_IFREG
                && identity.links == 1
                && identity.bytes > 0
                && identity.bytes <= limit as u64,
            "native media Android input is not one bounded regular file",
        )?;
        Ok(Self {
            root: root.try_clone().map_err(|e| e.to_string())?,
            path: path.into(),
            file,
            identity,
            sha256: None,
        })
    }
    fn read(&mut self, limit: usize, end: Instant) -> Result<Vec<u8>, String> {
        self.verify()?;
        before(end)?;
        need(
            self.identity.bytes <= limit as u64,
            "native media Android read bound",
        )?;
        let mut bytes = vec![0_u8; self.identity.bytes as usize];
        let mut offset = 0;
        while offset < bytes.len() {
            before(end)?;
            let n = self
                .file
                .read_at(&mut bytes[offset..], offset as u64)
                .map_err(|e| e.to_string())?;
            need(n > 0, "native media Android input shortened")?;
            offset += n;
        }
        self.sha256 = Some(hash(&bytes));
        self.verify()?;
        before(end)?;
        Ok(bytes)
    }
    fn verify(&self) -> Result<(), String> {
        let named = android_open(&self.root, &self.path)?;
        need(
            Identity::of(&self.file.metadata().map_err(|e| e.to_string())?) == self.identity
                && Identity::of(&named.metadata().map_err(|e| e.to_string())?) == self.identity,
            "native media Android file changed or was replaced",
        )?;
        if let Some(expected) = &self.sha256 {
            need(
                hash_file(&self.file, self.identity.bytes)? == *expected,
                "native media Android file complete digest differs",
            )?;
        }
        Ok(())
    }
}

fn decimal_line(raw: &[u8]) -> Result<u64, String> {
    let s = std::str::from_utf8(raw).map_err(|_| "guest clock is not UTF-8")?;
    let s = s.strip_suffix('\n').unwrap_or(s);
    need(
        !s.is_empty() && s.len() <= 20 && s.bytes().all(|b| b.is_ascii_digit()),
        "guest clock grammar",
    )?;
    s.parse().map_err(|_| "guest clock overflow".into())
}
fn photo_mode(raw: &[u8]) -> Result<(), String> {
    use quick_xml::{Reader, events::Event};
    need(
        !raw.is_empty() && raw.len() <= 128 * 1024,
        "Camera preferences bound",
    )?;
    let mut reader = Reader::from_reader(raw);
    let mut depth = 0usize;
    let mut root = false;
    let mut selected = false;
    let mut count = 0;
    let mut value = Vec::new();
    let mut events = 0;
    loop {
        events += 1;
        need(events <= 8192, "Camera preference XML event bound")?;
        match reader
            .read_event()
            .map_err(|_| "Camera preferences XML malformed")?
        {
            Event::Start(e) => {
                if depth == 0 {
                    need(
                        !root && e.name().as_ref() == b"map",
                        "Camera preferences require one map",
                    )?;
                    root = true;
                }
                if depth == 1 {
                    let mut name = None;
                    for a in e.attributes() {
                        let a =
                            a.map_err(|_| "Camera preferences duplicate/malformed attribute")?;
                        if a.key.as_ref() == b"name" {
                            need(name.is_none(), "Camera preference duplicate name")?;
                            name = Some(a.value.into_owned());
                        }
                    }
                    if name.as_deref() == Some(b"camera.startup_module".as_slice()) {
                        need(
                            e.name().as_ref() == b"string",
                            "Camera mode is not the source-owned string",
                        )?;
                        count += 1;
                        selected = true;
                    }
                } else if selected {
                    return Err("Camera mode XML has nested content".into());
                }
                depth += 1;
                need(depth <= 16, "Camera preference XML depth")?;
            }
            Event::Empty(e) => {
                need(depth > 0, "Camera preferences missing root")?;
                for a in e.attributes() {
                    let a = a.map_err(|_| "Camera preferences malformed attribute")?;
                    need(
                        !(a.key.as_ref() == b"name"
                            && a.value.as_ref() == b"camera.startup_module"),
                        "Camera mode is empty",
                    )?;
                }
            }
            Event::End(_) => {
                need(depth > 0, "Camera preference unbalanced XML")?;
                if depth == 2 && selected {
                    selected = false;
                }
                depth -= 1;
            }
            Event::Text(t) => {
                if selected {
                    value.extend_from_slice(t.as_ref());
                    need(value.len() <= 16, "Camera mode text bound")?;
                }
            }
            Event::DocType(_) | Event::CData(_) => {
                return Err("Camera mode XML cannot carry declarations or CDATA".into());
            }
            Event::Eof => break,
            _ => {}
        }
    }
    need(
        root && depth == 0 && count == 1 && value == b"0",
        "actual Camera photo mode is not verified; no shutter",
    )
}
fn content_rows<'a>(
    raw: &'a [u8],
    fields: &[&str],
) -> Result<Vec<BTreeMap<String, String>>, String> {
    need(
        !raw.is_empty() && raw.len() <= MAX_MEDIA_TEXT,
        "MediaStore stdout bound",
    )?;
    let text = std::str::from_utf8(raw).map_err(|_| "MediaStore stdout is not UTF-8")?;
    if text.trim() == "No result found." {
        return Ok(Vec::new());
    }
    let mut rows = Vec::new();
    for line in text.lines() {
        need(
            rows.len() < MAX_MEDIA_ROWS && !line.is_empty(),
            "MediaStore complete row bound",
        )?;
        let prefix = format!("Row: {} ", rows.len());
        let body = line
            .strip_prefix(&prefix)
            .ok_or("MediaStore row ordinal/grammar changed")?;
        let mut positions = Vec::new();
        for field in fields {
            let marker = format!("{field}=");
            let found: Vec<_> = body
                .match_indices(&marker)
                .filter(|(i, _)| *i == 0 || body[..*i].ends_with(", "))
                .collect();
            need(found.len() == 1, "MediaStore field missing or duplicated")?;
            positions.push((found[0].0, *field, marker.len()));
        }
        positions.sort_by_key(|p| p.0);
        need(
            positions.first().is_some_and(|p| p.0 == 0),
            "MediaStore unknown leading column",
        )?;
        let mut row = BTreeMap::new();
        for (i, (start, key, n)) in positions.iter().enumerate() {
            let end = positions.get(i + 1).map_or(body.len(), |p| p.0 - 2);
            need(end >= start + n, "MediaStore column boundary invalid")?;
            let value = &body[start + n..end];
            need(
                !value.contains('\0') && !value.contains('\r') && !value.is_empty(),
                "MediaStore field shape",
            )?;
            row.insert((*key).to_owned(), value.to_owned());
        }
        rows.push(row);
    }
    need(
        !rows.is_empty(),
        "MediaStore empty stdout is not a complete empty table",
    )?;
    Ok(rows)
}
fn number(value: &str) -> Result<u64, String> {
    need(
        !value.is_empty() && value.len() <= 20 && value.bytes().all(|b| b.is_ascii_digit()),
        "MediaStore numeric field grammar",
    )?;
    value
        .parse()
        .map_err(|_| "MediaStore numeric field overflow".into())
}
fn image_ids(raw: &[u8]) -> Result<BTreeSet<u64>, String> {
    let mut ids = BTreeSet::new();
    for row in content_rows(raw, &["_id"])? {
        let id = number(&row["_id"])?;
        need(id > 0 && ids.insert(id), "MediaStore ID duplicate or zero")?;
    }
    Ok(ids)
}
fn new_image(before: &BTreeSet<u64>, after: &BTreeSet<u64>) -> Result<Option<u64>, String> {
    need(
        before.is_subset(after),
        "a preexisting MediaStore row disappeared",
    )?;
    let added: Vec<_> = after.difference(before).copied().collect();
    need(
        added.len() <= 1,
        "more than one new MediaStore image; ownership is ambiguous",
    )?;
    Ok(added.first().copied())
}
#[derive(Debug, Eq, PartialEq, Serialize)]
struct MediaRow {
    id: u64,
    path: String,
    name: String,
    bytes: u64,
    width: u32,
    height: u32,
    orientation: u32,
    date_added: u64,
    owner: String,
}
fn image_row(raw: &[u8], id: u64, seconds: u64) -> Result<Option<MediaRow>, String> {
    let rows = content_rows(raw, &MEDIA_FIELDS)?;
    need(
        rows.len() == 1,
        "new MediaStore image row missing or ambiguous",
    )?;
    let r = &rows[0];
    need(
        number(&r["_id"])? == id
            && r["owner_package_name"] == CAMERA
            && number(&r["date_added"])? >= seconds.saturating_sub(3),
        "new Camera image ID/owner/time differs",
    )?;
    let name = r["_data"]
        .strip_prefix("/storage/emulated/0/DCIM/Camera/")
        .ok_or("image outside Camera DCIM")?;
    need(
        !name.is_empty()
            && !name.contains('/')
            && !name.contains('\0')
            && !name.contains('\r')
            && !name.contains('\n')
            && name == r["_display_name"]
            && (name.to_ascii_lowercase().ends_with(".jpg")
                || name.to_ascii_lowercase().ends_with(".jpeg"))
            && r["mime_type"] == "image/jpeg",
        "new Camera filename or media type differs",
    )?;
    let pending = number(&r["is_pending"])?;
    need(pending <= 1, "unknown Camera image pending state")?;
    if pending != 0 || matches!(r["_size"].as_str(), "0" | "NULL" | "null") {
        return Ok(None);
    }
    let bytes = number(&r["_size"])?;
    let width = number(&r["width"])?;
    let height = number(&r["height"])?;
    let orientation = number(&r["orientation"])?;
    need(
        bytes > 0
            && bytes <= MAX_IMAGE as u64
            && width > 0
            && height > 0
            && width <= MAX_AXIS as u64
            && height <= MAX_AXIS as u64
            && width
                .checked_mul(height)
                .is_some_and(|n| n <= MAX_PIXELS as u64)
            && matches!(orientation, 0 | 90 | 180 | 270),
        "new Camera image dimensions/size/orientation bound",
    )?;
    Ok(Some(MediaRow {
        id,
        path: r["_data"].clone(),
        name: r["_display_name"].clone(),
        bytes,
        width: width as u32,
        height: height as u32,
        orientation: orientation as u32,
        date_added: number(&r["date_added"])?,
        owner: r["owner_package_name"].clone(),
    }))
}
fn pixel_hash(width: u32, height: u32, rgb: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update(width.to_be_bytes());
    digest.update(height.to_be_bytes());
    digest.update(rgb);
    format!("{:x}", digest.finalize())
}
fn u32be(raw: &[u8]) -> u32 {
    u32::from_be_bytes(raw.try_into().unwrap())
}
fn decode_png_crop(raw: &[u8], crop: &Rect, end: Instant) -> Result<(u32, u32, Vec<u8>), String> {
    before(end)?;
    need(
        crop.right > crop.left && crop.bottom > crop.top,
        "PNG crop has no positive actual window extent",
    )?;
    need(
        raw.len() >= 45 && raw.len() <= MAX_IMAGE && raw.starts_with(b"\x89PNG\r\n\x1a\n"),
        "complete PNG bound/signature",
    )?;
    let mut cursor = 8;
    let mut dimensions = None;
    let mut compressed = Vec::new();
    let mut data = false;
    let mut data_closed = false;
    let mut ended = false;
    while cursor < raw.len() {
        before(end)?;
        need(raw.len() - cursor >= 12, "truncated PNG chunk")?;
        let len = u32be(&raw[cursor..cursor + 4]) as usize;
        let stop = cursor
            .checked_add(12)
            .and_then(|n| n.checked_add(len))
            .ok_or("PNG chunk overflow")?;
        need(stop <= raw.len(), "truncated PNG chunk payload")?;
        let kind = &raw[cursor + 4..cursor + 8];
        let payload = &raw[cursor + 8..cursor + 8 + len];
        need(
            kind.iter().all(u8::is_ascii_alphabetic) && kind[2].is_ascii_uppercase(),
            "PNG chunk name",
        )?;
        need(
            crc32fast::hash(&raw[cursor + 4..cursor + 8 + len])
                == u32be(&raw[cursor + 8 + len..stop]),
            "PNG chunk CRC differs",
        )?;
        if kind == b"IHDR" {
            need(
                cursor == 8 && len == 13 && dimensions.is_none(),
                "PNG IHDR placement or size",
            )?;
            let width = u32be(&payload[..4]) as usize;
            let height = u32be(&payload[4..8]) as usize;
            let channels = match payload[9] {
                2 => 3usize,
                6 => 4usize,
                _ => return Err("only actual 8-bit RGB/RGBA screencap is supported".into()),
            };
            need(
                width > 0
                    && height > 0
                    && width <= MAX_AXIS
                    && height <= MAX_AXIS
                    && width.checked_mul(height).is_some_and(|n| n <= MAX_PIXELS)
                    && payload[8] == 8
                    && payload[10..13] == [0, 0, 0],
                "PNG dimensions/depth/compression/filter/interlace bound",
            )?;
            need(
                crop.right as usize <= width && crop.bottom as usize <= height,
                "actual window exceeds complete screencap",
            )?;
            dimensions = Some((width, height, channels));
        } else if kind == b"IDAT" {
            need(
                dimensions.is_some() && !data_closed && !ended,
                "PNG noncontiguous or misplaced image data",
            )?;
            need(
                compressed
                    .len()
                    .checked_add(len)
                    .is_some_and(|n| n <= MAX_IMAGE),
                "PNG compressed image bound",
            )?;
            compressed.extend_from_slice(payload);
            data = true;
        } else if kind == b"IEND" {
            need(
                data && len == 0 && stop == raw.len() && !ended,
                "PNG missing image data, trailing bytes, or bad end",
            )?;
            ended = true;
        } else {
            need(
                dimensions.is_some()
                    && kind[0].is_ascii_lowercase()
                    && !matches!(kind, b"acTL" | b"fcTL" | b"fdAT" | b"tRNS"),
                "unsupported PNG critical/animated/transparency chunk",
            )?;
            if data {
                data_closed = true;
            }
        }
        cursor = stop;
    }
    need(
        ended && !compressed.is_empty(),
        "PNG end or compressed image absent",
    )?;
    let (width, height, channels) = dimensions.ok_or("PNG header absent")?;
    let stride = width.checked_mul(channels).ok_or("PNG stride overflow")?;
    let mut previous = vec![0; stride];
    let mut row = vec![0; stride];
    let mut filter = [0];
    let mut decoder = ZlibDecoder::new(Cursor::new(compressed.as_slice()));
    let mut output = Vec::with_capacity(crop.width() * crop.height() * 3);
    for y in 0..height {
        before(end)?;
        decoder
            .read_exact(&mut filter)
            .and_then(|_| decoder.read_exact(&mut row))
            .map_err(|_| "PNG complete zlib row decode failed")?;
        need(filter[0] <= 4, "PNG row filter unknown")?;
        for x in 0..stride {
            let a = if x >= channels { row[x - channels] } else { 0 };
            let b = previous[x];
            let c = if x >= channels {
                previous[x - channels]
            } else {
                0
            };
            let predicted = match filter[0] {
                0 => 0,
                1 => a,
                2 => b,
                3 => ((u16::from(a) + u16::from(b)) / 2) as u8,
                4 => paeth(a, b, c),
                _ => unreachable!(),
            };
            row[x] = row[x].wrapping_add(predicted);
        }
        if y >= crop.top as usize && y < crop.bottom as usize {
            for x in crop.left as usize..crop.right as usize {
                output.extend_from_slice(&row[x * channels..x * channels + 3]);
            }
        }
        std::mem::swap(&mut previous, &mut row);
    }
    let mut extra = [0];
    need(
        decoder
            .read(&mut extra)
            .map_err(|_| "PNG zlib checksum failed")?
            == 0
            && decoder.total_in() == compressed.len() as u64,
        "PNG extra pixels or trailing compressed stream",
    )?;
    before(end)?;
    Ok((crop.width() as u32, crop.height() as u32, output))
}
fn paeth(a: u8, b: u8, c: u8) -> u8 {
    let a = i32::from(a);
    let b = i32::from(b);
    let c = i32::from(c);
    let p = a + b - c;
    let pa = (p - a).abs();
    let pb = (p - b).abs();
    let pc = (p - c).abs();
    if pa <= pb && pa <= pc {
        a as u8
    } else if pb <= pc {
        b as u8
    } else {
        c as u8
    }
}
fn jpeg_complete(raw: &[u8]) -> Result<(), String> {
    need(
        raw.len() >= 4 && raw.len() <= MAX_IMAGE && raw.starts_with(&[0xff, 0xd8]),
        "JPEG complete body/signature bound",
    )?;
    let mut at = 2;
    let mut scans = 0;
    let mut frame = false;
    let mut entropy = false;
    loop {
        need(at < raw.len(), "JPEG ended before EOI")?;
        if entropy {
            while at < raw.len() && raw[at] != 0xff {
                at += 1;
            }
            need(at < raw.len(), "JPEG scan ended before marker")?;
        }
        need(raw[at] == 0xff, "JPEG marker prefix missing")?;
        at += 1;
        while at < raw.len() && raw[at] == 0xff {
            at += 1;
        }
        need(at < raw.len(), "JPEG marker truncated")?;
        let marker = raw[at];
        at += 1;
        if entropy && (marker == 0x00 || (0xd0..=0xd7).contains(&marker)) {
            continue;
        }
        entropy = false;
        if marker == 0xd9 {
            return need(
                frame && scans > 0 && at == raw.len(),
                "JPEG incomplete frame or trailing bytes",
            );
        }
        need(
            !matches!(marker, 0x00 | 0x01 | 0xd8 | 0xd0..=0xd7),
            "JPEG unexpected standalone marker",
        )?;
        need(at + 2 <= raw.len(), "JPEG segment length truncated")?;
        let len = u16::from_be_bytes([raw[at], raw[at + 1]]) as usize;
        need(
            len >= 2 && at.checked_add(len).is_some_and(|end| end <= raw.len()),
            "JPEG segment payload truncated",
        )?;
        if matches!(marker, 0xc0 | 0xc1 | 0xc2) {
            need(!frame, "JPEG contains multiple frames")?;
            frame = true;
        } else if (0xc0..=0xcf).contains(&marker) && !matches!(marker, 0xc4 | 0xc8 | 0xcc) {
            return Err("unsupported JPEG frame coding".into());
        }
        if marker == 0xda {
            scans += 1;
            need(
                frame && scans <= 100,
                "JPEG missing frame or excessive scans",
            )?;
            entropy = true;
        }
        at += len;
    }
}
fn decode_jpeg(raw: &[u8], end: Instant) -> Result<(u32, u32, Vec<u8>), String> {
    before(end)?;
    jpeg_complete(raw)?;
    let options = DecoderOptions::default()
        .set_max_width(MAX_AXIS)
        .set_max_height(MAX_AXIS)
        .set_strict_mode(true)
        .set_use_unsafe(false)
        .jpeg_set_max_scans(100)
        .jpeg_set_out_colorspace(ColorSpace::RGB);
    let mut decoder = JpegDecoder::new_with_options(ZCursor::new(raw), options);
    decoder
        .decode_headers()
        .map_err(|_| "Camera JPEG headers failed the fixed decoder")?;
    let info = decoder.info().ok_or("Camera JPEG dimensions absent")?;
    let (width, height) = (u32::from(info.width), u32::from(info.height));
    let pixels = (width as usize)
        .checked_mul(height as usize)
        .filter(|n| *n > 0 && *n <= MAX_PIXELS)
        .ok_or("Camera JPEG pixel count bound")?;
    need(
        decoder.output_colorspace() == Some(ColorSpace::RGB)
            && decoder.output_buffer_size() == Some(pixels * 3),
        "Camera JPEG decoded RGB shape differs",
    )?;
    before(end)?;
    let rgb = decoder
        .decode()
        .map_err(|_| "Camera JPEG full pixel decode failed")?;
    need(
        rgb.len() == pixels * 3 && decoder.output_colorspace() == Some(ColorSpace::RGB),
        "Camera JPEG decoded frame incomplete",
    )?;
    before(end)?;
    Ok((width, height, rgb))
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::{Compression, write::ZlibEncoder};
    fn end() -> Instant {
        Instant::now() + Duration::from_secs(20)
    }
    fn chunk(out: &mut Vec<u8>, kind: &[u8; 4], body: &[u8]) {
        out.extend_from_slice(&(body.len() as u32).to_be_bytes());
        out.extend_from_slice(kind);
        out.extend_from_slice(body);
        let mut h = crc32fast::Hasher::new();
        h.update(kind);
        h.update(body);
        out.extend_from_slice(&h.finalize().to_be_bytes());
    }
    fn png(width: u32, height: u32, channels: usize, pixels: &[u8], filters: &[u8]) -> Vec<u8> {
        let stride = width as usize * channels;
        let mut raw = Vec::new();
        let zero = vec![0; stride];
        for y in 0..height as usize {
            let row = &pixels[y * stride..(y + 1) * stride];
            let old = if y == 0 {
                zero.as_slice()
            } else {
                &pixels[(y - 1) * stride..y * stride]
            };
            let filter = filters[y];
            raw.push(filter);
            for i in 0..stride {
                let a = if i >= channels { row[i - channels] } else { 0 };
                let b = old[i];
                let c = if i >= channels { old[i - channels] } else { 0 };
                let predict = match filter {
                    0 => 0,
                    1 => a,
                    2 => b,
                    3 => ((u16::from(a) + u16::from(b)) / 2) as u8,
                    4 => paeth(a, b, c),
                    _ => 0,
                };
                raw.push(row[i].wrapping_sub(predict));
            }
        }
        let mut encoder = ZlibEncoder::new(Vec::new(), Compression::default());
        encoder.write_all(&raw).unwrap();
        let z = encoder.finish().unwrap();
        let mut out = b"\x89PNG\r\n\x1a\n".to_vec();
        let mut h = Vec::new();
        h.extend_from_slice(&width.to_be_bytes());
        h.extend_from_slice(&height.to_be_bytes());
        h.extend_from_slice(&[8, if channels == 3 { 2 } else { 6 }, 0, 0, 0]);
        chunk(&mut out, b"IHDR", &h);
        chunk(&mut out, b"IDAT", &z);
        chunk(&mut out, b"IEND", &[]);
        out
    }
    #[test]
    fn native_media_png_decodes_all_five_filters_and_only_actual_window_crop() {
        for channels in [3, 4] {
            let pixels: Vec<_> = (0..3 * 5 * channels).map(|i| (i * 37 + 13) as u8).collect();
            let raw = png(3, 5, channels, &pixels, &[0, 1, 2, 3, 4]);
            let crop = Rect {
                left: 1,
                top: 1,
                right: 3,
                bottom: 4,
            };
            let (w, h, rgb) = decode_png_crop(&raw, &crop, end()).unwrap();
            assert_eq!((w, h), (2, 3));
            let mut expected = Vec::new();
            for y in 1..4 {
                for x in 1..3 {
                    let i = (y * 3 + x) * channels;
                    expected.extend_from_slice(&pixels[i..i + 3]);
                }
            }
            assert_eq!(rgb, expected);
            assert!(
                decode_png_crop(
                    &raw,
                    &Rect {
                        left: 0,
                        top: 0,
                        right: 4,
                        bottom: 5
                    },
                    end()
                )
                .is_err()
            );
        }
    }
    #[test]
    fn native_media_png_rejects_crc_truncation_trailing_pixels_stream_and_unsupported_format() {
        let crop = Rect {
            left: 0,
            top: 0,
            right: 2,
            bottom: 2,
        };
        let raw = png(2, 2, 3, &[30; 12], &[0, 4]);
        let mut crc = raw.clone();
        crc[29] ^= 1;
        assert!(decode_png_crop(&crc, &crop, end()).is_err());
        assert!(decode_png_crop(&raw[..raw.len() - 1], &crop, end()).is_err());
        let mut trailing = raw.clone();
        trailing.push(0);
        assert!(decode_png_crop(&trailing, &crop, end()).is_err());
        let mut interlace = raw.clone();
        interlace[28] = 1;
        let h = crc32fast::hash(&interlace[12..29]);
        interlace[29..33].copy_from_slice(&h.to_be_bytes());
        assert!(decode_png_crop(&interlace, &crop, end()).is_err());
        let mut extra = raw[..33].to_vec();
        let n = u32be(&raw[33..37]) as usize;
        let mut payload = raw[41..41 + n].to_vec();
        payload.extend_from_slice(&[1, 2, 3]);
        chunk(&mut extra, b"IDAT", &payload);
        chunk(&mut extra, b"IEND", &[]);
        assert!(decode_png_crop(&extra, &crop, end()).is_err());
        assert!(decode_png_crop(&raw, &crop, Instant::now() - Duration::from_millis(1)).is_err());
    }
    fn hex(s: &str) -> Vec<u8> {
        (0..s.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap())
            .collect()
    }
    const BASELINE: &str = "ffd8ffe000104a46494600010100000100010000ffdb004300030202020202030202020303030304060404040404080606050609080a0a090809090a0c0f0c0a0b0e0b09090d110d0e0f101011100a0c12131210130f101010ffdb00430103030304030408040408100b090b1010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010ffc00011080003000403011100021101031101ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffc4001f0100030101010101010101010000000000000102030405060708090a0bffc400b51100020102040403040705040400010277000102031104052131061241510761711322328108144291a1b1c109233352f0156272d10a162434e125f11718191a262728292a35363738393a434445464748494a535455565758595a636465666768696a737475767778797a82838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda000c03010002110311003f00f53fd933fe449d77fec316ff00fa68d3ebf983c60df26ffb05a9ff00a9f8e3dfc07fc8c736ff00b0ec67fea4543fffd9";
    const PROGRESSIVE: &str = "ffd8ffe000104a46494600010100000100010000ffdb004300030202020202030202020303030304060404040404080606050609080a0a090809090a0c0f0c0a0b0e0b09090d110d0e0f101011100a0c12131210130f101010ffdb00430103030304030408040408100b090b1010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010101010ffc20011080003000403011100021101031101ffc40014000100000000000000000000000000000006ffc4001501010100000000000000000000000000000407ffda000c03010002100310000001532f7fffc4001510010100000000000000000000000000000634ffda00080101000105022717ffc4001a1100010501000000000000000000000000030002043473b3ffda0008010301013f0105897b9ba397ffc4001a1100000700000000000000000000000000000203064473b3ffda0008010201013f017843a8dbae3fffc40018100002030000000000000000000000000000030273b3ffda0008010100063f027dd1c967ffc40014100100000000000000000000000000000000ffda0008010100013f2162ffda000c03010002000300000010ff00ffc40014110100000000000000000000000000000000ffda0008010301013f1060ffc4001511010100000000000000000000000000000031ffda0008010201013f10a4bfffc40014100100000000000000000000000000000000ffda0008010100013f1052ffd9";
    #[test]
    fn native_media_jpeg_requires_full_baseline_or_progressive_pixel_decode() {
        for sample in [BASELINE, PROGRESSIVE] {
            let raw = hex(sample);
            let (w, h, rgb) = decode_jpeg(&raw, end()).unwrap();
            assert_eq!((w, h, rgb.len()), (4, 3, 36));
            assert!(rgb[0] > 180 && rgb[1] < 70 && rgb[2] < 80);
            assert!(rgb[4] > 180);
            assert!(decode_jpeg(&raw[..raw.len() - 2], end()).is_err());
            let mut trailing = raw.clone();
            trailing.extend_from_slice(b"other");
            assert!(decode_jpeg(&trailing, end()).is_err());
            let mut header_only = raw[..20].to_vec();
            header_only.extend_from_slice(&[0xff, 0xd9]);
            assert!(decode_jpeg(&header_only, end()).is_err());
        }
    }
    #[test]
    fn native_media_window_requires_one_real_target_focus_on_original_user() {
        assert_eq!(focused_window(b"  mCurrentFocus=Window{a1b2 u0 com.android.camera2/com.android.camera.CameraLauncher}\n",CAMERA).unwrap(),
            ("a1b2".into(),"com.android.camera.CameraLauncher".into()));
        for bad in [
            "mCurrentFocus=null\n",
            "mCurrentFocus=Window{a1b2 u10 com.android.camera2/.CameraLauncher}\n",
            "mCurrentFocus=Window{a1b2 u0 com.android.settings/.Settings}\n",
            "mCurrentFocus=Window{a1b2 u0 com.android.camera2/.A}\nmCurrentFocus=Window{b2c3 u0 com.android.camera2/.B}\n",
        ] {
            assert!(focused_window(bad.as_bytes(), CAMERA).is_err());
        }
        assert!(Rect::parse(&serde_json::json!([-1, 0, 10, 10])).is_err());
        assert!(Rect::parse(&serde_json::json!([1, 1, 1, 2])).is_err());
    }
    fn row() -> String {
        "Row: 0 _id=9, _data=/storage/emulated/0/DCIM/Camera/IMG_1.jpg, _display_name=IMG_1.jpg, mime_type=image/jpeg, _size=671, width=4, height=3, orientation=0, date_added=100, is_pending=0, owner_package_name=com.android.camera2\n".into()
    }
    #[test]
    fn native_media_photo_ownership_requires_complete_unique_id_delta_and_actual_row() {
        let ids = image_ids(b"Row: 0 _id=1\nRow: 1 _id=4\n").unwrap();
        let mut after = ids.clone();
        after.insert(9);
        assert_eq!(new_image(&ids, &after).unwrap(), Some(9));
        let parsed = image_row(row().as_bytes(), 9, 100).unwrap().unwrap();
        assert_eq!(parsed.id, 9);
        let mut two = after.clone();
        two.insert(10);
        assert!(new_image(&ids, &two).is_err());
        assert!(new_image(&ids, &BTreeSet::from([4, 9])).is_err());
        for bad in [
            "Row: 0 _id=1\nRow: 1 _id=1\n",
            "Row: 1 _id=1\n",
            "Row: 0 _id=0\n",
            "",
        ] {
            assert!(image_ids(bad.as_bytes()).is_err());
        }
        assert!(image_ids(b"No result found.\n").unwrap().is_empty());
        for (a, b) in [
            (
                "owner_package_name=com.android.camera2",
                "owner_package_name=other",
            ),
            ("DCIM/Camera/IMG_1.jpg", "DCIM/Other/IMG_1.jpg"),
            ("date_added=100", "date_added=90"),
            ("width=4", "width=8193"),
            ("_size=671", "_size=33554433"),
            ("_display_name=IMG_1.jpg", "_display_name=Other.jpg"),
        ] {
            assert!(image_row(row().replace(a, b).as_bytes(), 9, 100).is_err());
        }
        assert!(
            image_row(
                row().replace("is_pending=0", "is_pending=1").as_bytes(),
                9,
                100
            )
            .unwrap()
            .is_none()
        );
    }
    #[test]
    fn native_media_photo_mode_is_fixed_read_only_source_key_and_never_assumed() {
        photo_mode(
            b"<?xml version=\"1.0\"?><map><string name=\"camera.startup_module\">0</string></map>",
        )
        .unwrap();
        for bad in [
            "<map/>",
            "<map><string name=\"camera.startup_module\">1</string></map>",
            "<map><int name=\"camera.startup_module\">0</int></map>",
            "<map><string name=\"camera.startup_module\">0</string><string name=\"camera.startup_module\">0</string></map>",
            "<!DOCTYPE map><map><string name=\"camera.startup_module\">0</string></map>",
        ] {
            assert!(photo_mode(bad.as_bytes()).is_err());
        }
    }
    #[test]
    fn native_media_same_byte_inode_replacement_and_android_root_escape_are_rejected() {
        let dir = tempfile::tempdir().unwrap();
        let root = File::open(dir.path()).unwrap();
        std::fs::write(dir.path().join("owned.jpg"), b"public fixture").unwrap();
        let mut held = AndroidFile::open(&root, "owned.jpg", 128).unwrap();
        held.read(128, end()).unwrap();
        std::fs::write(dir.path().join("replacement"), b"public fixture").unwrap();
        std::fs::rename(dir.path().join("replacement"), dir.path().join("owned.jpg")).unwrap();
        assert!(held.verify().is_err());
        assert!(android_open(&root, "../outside").is_err());
        assert!(android_open(&root, "/etc/passwd").is_err());
    }
}
