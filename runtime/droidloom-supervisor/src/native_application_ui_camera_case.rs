//! One fixed photo case: one actual shutter, close, normal reopen, and reread.
//!
//! No caller image, MediaStore ID, path, success map, or fresh deadline can enter
//! this factory. The point observation is kept with both actual finished task
//! transcripts; reopening never creates a second shutter intent.
use super::super::{NativeUiTranscript, RetainedNativeUiTranscript};
use super::scene::RetainedCameraPhotoSceneObservation;
use super::{
    AndroidFile, CameraPhotoSceneObservation, HeldRecord, MAX_IMAGE, MediaRow,
    NativeApplicationInspector, NativeUiSession, RetainedScopedWindowPixels, Subject, before,
    decode_jpeg, hash, need, new_image, pixel_hash,
};
use crate::control::application_probe::ApplicationInspection;
use crate::main_custody::RuntimeMainCustody;
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use serde_json::Value;
use std::time::{Duration, Instant};

// These are the actual fixed normal operation caps, not new relative leases.
// Opening: helper PM 250, three qualification commands 15 each, launcher catalog
// 250, normal launch 250, two task samples 15 each, running Engine 70.
const OPEN_SECONDS: u64 = 250 + 3 * 15 + 250 + 250 + 2 * 15 + 70;
// Existing finish: target PM 250, Main 70, helper PM 250, Engine 70, cleanup 60.
const FINISH_SECONDS: u64 = 250 + 70 + 250 + 70 + 60;
// Fixed find/click each 70+2*15; one seven-command scoped image 110; before IDs
// 15; guest date 10; original bounded settle 30; final row/IDs/task 3*15.
const CAPTURE_SECONDS: u64 = 2 * (70 + 2 * 15) + 110 + 15 + 10 + 30 + 3 * 15;
// Reopen: two ID and two row reads 4*15, two task checks 2*15, one scoped image
// 110. Full JPEG/PNG decode, bounded matching and full-byte sealing use the
// fixed local allowance; no operation may exceed the original absolute cutoff.
const REOBSERVE_SECONDS: u64 = 4 * 15 + 2 * 15 + 110;
const LOCAL_SECONDS: u64 = 120;
const SECOND_SECONDS: u64 = OPEN_SECONDS + REOBSERVE_SECONDS + FINISH_SECONDS + LOCAL_SECONDS;

pub fn camera_photo_case_window_seconds() -> u64 {
    OPEN_SECONDS + CAPTURE_SECONDS + FINISH_SECONDS + LOCAL_SECONDS + SECOND_SECONDS
}

fn first_cutoff(
    now: Instant,
    original_end: Instant,
    baseline_end: Instant,
) -> Result<Instant, String> {
    need(
        original_end <= baseline_end
            && original_end.saturating_duration_since(now)
                <= Duration::from_secs(camera_photo_case_window_seconds()),
        "Camera photo case exceeds its source-owned original window or baseline deadline",
    )?;
    original_end
        .checked_sub(Duration::from_secs(SECOND_SECONDS))
        .filter(|cutoff| *cutoff > now)
        .ok_or_else(|| "Camera photo first-session cutoff is outside the original deadline".into())
}

fn require_distinct_reopen(
    first_task: u32,
    first_journal: &[u64; 5],
    first_path: &std::path::Path,
    second_task: u32,
    second_journal: &[u64; 5],
    second_path: &std::path::Path,
) -> Result<(), String> {
    need(
        first_task != second_task && first_journal != second_journal && first_path != second_path,
        "Camera reopen must be a different actual task and held journal, not a relabeled first session",
    )
}
fn require_original_file(original: &AndroidFile, reopened: &AndroidFile) -> Result<(), String> {
    original.verify()?;
    reopened.verify()?;
    need(
        original.identity == reopened.identity,
        "Camera original JPEG was replaced before reopen",
    )
}

fn require_reopened_subject(first: &Subject, second: &Subject) -> Result<(), String> {
    need(
        first.application.package == super::CAMERA
            && first.application.user == 0
            && first.application == second.application
            && first.main == second.main,
        "Camera reopen requires the same complete application and Main",
    )?;
    require_distinct_reopen(
        first.task,
        &first.journal,
        &first.journal_path,
        second.task,
        &second.journal,
        &second.journal_path,
    )
}

/// Private observation created by reading this case's original held photo again.
/// The new task owns neither a caller-selected row nor a second shutter.
struct ReopenedPhoto {
    subject: Subject,
    row: MediaRow,
    encoded: HeldRecord,
    source: AndroidFile,
    window: RetainedScopedWindowPixels,
    width: u32,
    height: u32,
    pixels_sha256: String,
    record: HeldRecord,
}
impl ReopenedPhoto {
    fn verify(&self, first: &RetainedCameraPhotoSceneObservation) -> Result<(), String> {
        first.verify_retained()?;
        self.encoded.verify()?;
        self.source.verify()?;
        self.window.verify_retained()?;
        self.record.verify()?;
        let photo = first.photo();
        require_reopened_subject(&photo.subject, &self.subject)?;
        need(
            self.row == photo.row
                && self.source.identity == photo.source.identity
                && self.encoded.sha256 == photo.encoded.sha256
                && self.encoded.identity.bytes == photo.encoded.identity.bytes
                && self.width == photo.width
                && self.height == photo.height
                && self.pixels_sha256 == photo.pixels_sha256,
            "Camera reopened row, original inode, complete JPEG or decoded pixels changed",
        )
    }
    fn require_transcript(&self, transcript: &NativeUiTranscript) -> Result<(), String> {
        self.subject.require_transcript(transcript)?;
        self.window.require_transcript(transcript)
    }
    fn comparison(&self) -> Result<Value, String> {
        self.encoded.verify()?;
        self.source.verify()?;
        self.record.verify()?;
        Ok(serde_json::json!({
            "schema":"droidloom.native-camera-reopened-photo.v1",
            "subject":self.subject.comparison(),"row":self.row,
            "encoded_sha256":self.encoded.sha256,"encoded_bytes":self.encoded.identity.bytes,
            "decoded_dimensions":[self.width,self.height],"pixels_sha256":self.pixels_sha256,
            "original_held_inode_reobserved":true,"complete_jpeg_decoded_again":true,
            "second_shutter_executed":false,"reopened_window":self.window.comparison()?,
            "record_sha256":self.record.sha256,"business_accepted":false
        }))
    }
}

impl NativeUiSession<'_, '_> {
    fn reobserve_original_photo(
        &mut self,
        inspector: &NativeApplicationInspector,
        scene: &CameraPhotoSceneObservation,
        closed: &NativeUiTranscript,
    ) -> Result<ReopenedPhoto, String> {
        self.guard(inspector, self.work_end)?;
        scene.require_transcript(closed)?;
        let photo = scene.photo();
        let subject = Subject::capture(self)?;
        require_reopened_subject(&photo.subject, &subject)?;
        self.owned_task(inspector, self.work_end)?;
        need(
            new_image(
                &photo.before_ids,
                &self.camera_ids(inspector, self.work_end)?,
            )? == Some(photo.row.id),
            "Camera complete media set changed before the original photo was reopened",
        )?;
        let row = self
            .camera_row(
                inspector,
                photo.row.id,
                photo.guest_shutter_seconds,
                self.work_end,
            )?
            .ok_or("Camera original photo became pending on reopen")?;
        need(
            row == photo.row,
            "Camera original media row changed on reopen",
        )?;

        // This path comes only from the first source-owned MediaStore difference.
        // Opening it again must reach the same original held inode, not a
        // same-byte replacement. Both descriptors remain in the returned case.
        let mut source = AndroidFile::open(
            &self.target.root,
            row.path.trim_start_matches('/'),
            MAX_IMAGE,
        )?;
        require_original_file(&photo.source, &source)?;
        let raw = source.read(MAX_IMAGE, self.work_end)?;
        need(
            raw.len() as u64 == row.bytes && hash(&raw) == photo.encoded.sha256,
            "Camera original JPEG complete bytes changed after normal close",
        )?;
        let (width, height, rgb) = decode_jpeg(&raw, self.work_end)?;
        let pixels_sha256 = pixel_hash(width, height, &rgb);
        need(
            width == photo.width && height == photo.height && pixels_sha256 == photo.pixels_sha256,
            "Camera original photo decoded differently after normal reopen",
        )?;
        drop(rgb);
        let window = self.scoped_window_pixels(inspector)?.into_retained()?;
        let final_row = self
            .camera_row(
                inspector,
                row.id,
                photo.guest_shutter_seconds,
                self.work_end,
            )?
            .ok_or("Camera original photo became pending during reopen verification")?;
        need(
            final_row == row
                && new_image(
                    &photo.before_ids,
                    &self.camera_ids(inspector, self.work_end)?,
                )? == Some(row.id),
            "Camera row or complete media set changed during reopen verification",
        )?;
        source.verify()?;
        scene.verify_retained()?;
        subject.require(self)?;
        self.owned_task(inspector, self.work_end)?;
        self.guard(inspector, self.work_end)?;
        let encoded = HeldRecord::create(self, "CAMERA-OWNED-PHOTO.jpg", &raw)?;
        drop(raw);
        let record_bytes = serde_json::to_vec(&serde_json::json!({
            "schema":"droidloom.native-camera-reopen-read.v1",
            "original_task":photo.subject.task,"reopened_task":subject.task,
            "original_journal":photo.subject.journal_path,"reopened_journal":subject.journal_path,
            "row":row,"original_inode_unchanged":true,"encoded_sha256":encoded.sha256,
            "decoded_dimensions":[width,height],"pixels_sha256":pixels_sha256,
            "complete_image_id_set_unchanged":true,"second_shutter_executed":false,
            "business_accepted":false
        }))
        .map_err(|e| e.to_string())?;
        let record = HeldRecord::create(self, "CAMERA-REOPEN-READ.json", &record_bytes)?;
        let result = ReopenedPhoto {
            subject,
            row,
            encoded,
            source,
            window,
            width,
            height,
            pixels_sha256,
            record,
        };
        self.guard(inspector, self.work_end)?;
        before(self.work_end)?;
        Ok(result)
    }
}

/// A successful actual two-session case. Construction requires the fixed normal
/// producer below, including both normal close/PM/Main/Engine bookends. History
/// retains original FDs; it does not imply the Camera process stays alive.
pub struct CameraPhotoCaseObservation {
    main: RuntimeMainCustody,
    application: ApplicationInspection,
    scene: RetainedCameraPhotoSceneObservation,
    reopened: ReopenedPhoto,
    first: RetainedNativeUiTranscript,
    second: RetainedNativeUiTranscript,
}
impl CameraPhotoCaseObservation {
    pub fn first(&self) -> &RetainedNativeUiTranscript {
        &self.first
    }
    pub fn reopened(&self) -> &RetainedNativeUiTranscript {
        &self.second
    }
    pub fn require_subject(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
    ) -> Result<(), String> {
        need(
            &self.main == main && &self.application == application,
            "Camera case belongs to another complete subject",
        )?;
        self.first.require_subject(main, application)?;
        self.second.require_subject(main, application)?;
        self.verify_retained()
    }
    pub fn verify_retained(&self) -> Result<(), String> {
        self.first.guard_immutable()?;
        self.second.guard_immutable()?;
        self.scene.verify_retained()?;
        self.scene.require_transcript(self.first.transcript())?;
        self.reopened.require_transcript(self.second.transcript())?;
        self.reopened.verify(&self.scene)
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.verify_retained()?;
        Ok(serde_json::json!({
            "schema":"droidloom.native-camera-photo-case.v1",
            "main":self.main,"application":self.application,
            "original_scene":self.scene.comparison()?,
            "reopened_photo":self.reopened.comparison()?,
            "first_transcript":self.first.comparison()?,
            "second_transcript":self.second.comparison()?,
            "one_fixed_shutter":true,"full_jpeg_decoded":true,
            "actual_prior_window_matches_owned_photo":true,
            "normal_close_reopen_and_final_close_completed":true,
            "same_original_photo_inode_and_full_bytes":true,
            "original_deadline_extended":false,
            "whole_camera_business_accepted":false,
            "camera_video_or_recovery_accepted":false
        }))
    }
}

pub fn run_camera_photo_case(
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    original_end: Instant,
) -> Result<CameraPhotoCaseObservation, String> {
    let first_end = first_cutoff(Instant::now(), original_end, baseline.deadline())?;
    need(
        baseline.application().package == super::CAMERA && baseline.application().user == 0,
        "Camera photo case accepts only the actual selected user-0 Camera",
    )?;
    baseline
        .verify_local(inspector, original_end)
        .map_err(|e| e.to_string())?;
    let main = baseline.main().facts().clone();
    let application = baseline.application().clone();

    let mut first_session = NativeUiSession::open(inspector, baseline, first_end)?;
    let scene = match first_session.capture_camera_photo_scene(inspector) {
        Ok(value) => value,
        Err(error) => return Err(first_session.observation_failure(inspector, error)),
    };
    let first = first_session.finish(inspector)?.into_retained()?;
    scene.require_transcript(first.transcript())?;
    first.require_subject(&main, &application)?;
    before(first_end)?;

    let mut second_session = NativeUiSession::open(inspector, baseline, original_end)?;
    let reopened =
        match second_session.reobserve_original_photo(inspector, &scene, first.transcript()) {
            Ok(value) => value,
            Err(error) => return Err(second_session.observation_failure(inspector, error)),
        };
    let second = second_session.finish(inspector)?.into_retained()?;
    reopened.require_transcript(second.transcript())?;
    second.require_subject(&main, &application)?;

    // Matching and rereading have finished. Keep actual PNG/JPEG/source FDs and
    // hashes without storing two decoded full images for the rest of the suite.
    let scene = scene.into_retained()?;
    let result = CameraPhotoCaseObservation {
        main,
        application,
        scene,
        reopened,
        first,
        second,
    };
    result.verify_retained()?;
    baseline
        .verify_local(inspector, original_end)
        .map_err(|e| e.to_string())?;
    before(original_end)?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_camera_case_budget_reserves_reopen_without_renewing_original_end() {
        let now = Instant::now();
        let end = now + Duration::from_secs(camera_photo_case_window_seconds());
        assert_eq!(camera_photo_case_window_seconds(), 4040);
        assert_eq!(
            first_cutoff(now, end, end).unwrap(),
            end - Duration::from_secs(SECOND_SECONDS)
        );
        assert!(first_cutoff(now, end, end - Duration::from_nanos(1)).is_err());
        // Entry/bookkeeping consumes time after the parent fixed this cutoff.
        // It must not demand a fresh unused window or replace the deadline.
        assert_eq!(
            first_cutoff(now + Duration::from_nanos(1), end, end).unwrap(),
            end - Duration::from_secs(SECOND_SECONDS)
        );
        assert!(
            first_cutoff(
                now,
                end + Duration::from_nanos(1),
                end + Duration::from_nanos(1),
            )
            .is_err()
        );
        assert!(first_cutoff(end - Duration::from_secs(SECOND_SECONDS), end, end).is_err());
        assert!(first_cutoff(end, end, end).is_err());
    }
    #[test]
    fn native_camera_case_reopen_rejects_same_task_path_or_inode_splicing() {
        let first = [10, 20, libc::S_IFDIR as u64 | 0o700, 0, 0];
        let second = [10, 21, libc::S_IFDIR as u64 | 0o700, 0, 0];
        let a = std::path::Path::new("/fixed/actual-first");
        let b = std::path::Path::new("/fixed/actual-second");
        assert!(require_distinct_reopen(51, &first, a, 52, &second, b).is_ok());
        assert!(require_distinct_reopen(51, &first, a, 51, &second, b).is_err());
        assert!(require_distinct_reopen(51, &first, a, 52, &first, b).is_err());
        assert!(require_distinct_reopen(51, &first, a, 52, &second, a).is_err());
    }

    #[test]
    fn native_camera_case_reread_retains_original_file_and_rejects_same_byte_replacement() {
        use std::fs::{self, File};
        use std::time::{SystemTime, UNIX_EPOCH};
        let dir = std::env::temp_dir().join(format!(
            "camera-reopen-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&dir).unwrap();
        let bytes = b"complete owned comparison fixture bytes";
        fs::write(dir.join("owned.jpg"), bytes).unwrap();
        let root = File::open(&dir).unwrap();
        let mut original = AndroidFile::open(&root, "owned.jpg", 1024).unwrap();
        assert_eq!(
            original
                .read(1024, Instant::now() + Duration::from_secs(2))
                .unwrap(),
            bytes
        );
        let mut second = AndroidFile::open(&root, "owned.jpg", 1024).unwrap();
        require_original_file(&original, &second).unwrap();
        assert_eq!(
            second
                .read(1024, Instant::now() + Duration::from_secs(2))
                .unwrap(),
            bytes
        );
        require_original_file(&original, &second).unwrap();
        fs::rename(dir.join("owned.jpg"), dir.join("retired.jpg")).unwrap();
        fs::write(dir.join("owned.jpg"), bytes).unwrap();
        let replacement = AndroidFile::open(&root, "owned.jpg", 1024).unwrap();
        assert_eq!(hash(bytes), hash(&fs::read(dir.join("owned.jpg")).unwrap()));
        assert!(require_original_file(&original, &replacement).is_err());
        assert!(require_original_file(&original, &second).is_err());
        drop((root, original, second, replacement));
        fs::remove_dir_all(dir).unwrap();
    }
}
