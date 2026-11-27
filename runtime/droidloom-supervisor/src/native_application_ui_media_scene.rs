//! One actual Camera shutter followed by bounded matching of its decoded scene.
//!
//! The inputs come only from the same live NativeUiSession media factories.
//! This module does not accept caller images, rectangles, thresholds, or pass
//! maps. The result remains a point observation until the owning application
//! case also completes its actual normal close/reopen and source bookends.
use super::{
    CameraPhotoObservation, HeldRecord, NativeApplicationInspector, NativeUiSession, before, need,
};
use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeSet;
use std::time::Instant;

const REDUCED_AXIS: usize = 96;
const GW: usize = 16;
const GH: usize = 12;
const SAMPLES: usize = GW * GH;
const UNIT: u32 = 4;
const MAX_CANDIDATES: usize = 32_768;
const MIN_WINDOW_AREA_NUMERATOR: u64 = 1;
const MIN_WINDOW_AREA_DENOMINATOR: u64 = 2;
const MIN_PHOTO_AREA: f64 = 0.60;
const MIN_STANDARD_DEVIATION: f64 = 16.0;
const MIN_SECOND_DIFFERENCE: f64 = 4.0;
const MIN_COLOR_BUCKETS: usize = 12;
const MIN_CORRELATION: f64 = 0.97;
const MAX_RGB_ERROR: f64 = 12.0;

/// This can only be returned after the real fixed shutter and actual pixel match.
/// No caller comparison, Clone, Deserialize, or public field constructor exists.
pub struct CameraPhotoSceneObservation {
    photo: CameraPhotoObservation,
    scene: SceneMatch,
    record: HeldRecord,
}
impl CameraPhotoSceneObservation {
    pub fn photo(&self) -> &CameraPhotoObservation {
        &self.photo
    }
    pub fn verify_retained(&self) -> Result<(), String> {
        self.photo.verify_retained()?;
        self.record.verify()
    }
    pub fn require_transcript(
        &self,
        transcript: &super::super::NativeUiTranscript,
    ) -> Result<(), String> {
        self.verify_retained()?;
        self.photo.require_transcript(transcript)
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.verify_retained()?;
        Ok(serde_json::json!({
            "schema":"droidloom.native-camera-scene-observation.v1",
            "photo":self.photo.comparison()?,
            "scene_match":self.scene,
            "actual_prior_window_and_owned_jpeg_compared":true,
            "record_sha256":self.record.sha256,
            "correct_physical_orientation_claimed":false,
            "continuous_scene_or_window_custody_claimed":false,
            "normal_close_reopen_completed_by_this_factory":false,
            "business_accepted":false
        }))
    }
}
impl NativeUiSession<'_, '_> {
    /// The original single-shutter intent remains authoritative. A failed scene
    /// comparison does not authorize a second shutter or delete the owned photo.
    pub fn capture_camera_photo_scene(
        &mut self,
        inspector: &NativeApplicationInspector,
    ) -> Result<CameraPhotoSceneObservation, String> {
        let photo = self.capture_camera_photo(inspector)?;
        self.guard(inspector, self.work_end)?;
        photo.verify_retained()?;
        photo.subject.require(self)?;
        let scene = match_images(
            RawImage::new(
                photo.preview.width(),
                photo.preview.height(),
                photo.preview.rgb(),
            )?,
            RawImage::new(photo.width(), photo.height(), photo.rgb())?,
            self.work_end,
        )?;
        before(self.work_end)?;
        photo.verify_retained()?;
        photo.subject.require(self)?;
        self.guard(inspector, self.work_end)?;
        let bytes = serde_json::to_vec(&scene).map_err(|e| e.to_string())?;
        let record = HeldRecord::create(self, "CAMERA-SCENE-MATCH.json", &bytes)?;
        let result = CameraPhotoSceneObservation {
            photo,
            scene,
            record,
        };
        result.verify_retained()?;
        self.guard(inspector, self.work_end)?;
        Ok(result)
    }
}

#[derive(Clone, Copy)]
struct RawImage<'a> {
    width: usize,
    height: usize,
    rgb: &'a [u8],
}
impl<'a> RawImage<'a> {
    fn new(width: u32, height: u32, rgb: &'a [u8]) -> Result<Self, String> {
        let (width, height) = (width as usize, height as usize);
        let pixels = width
            .checked_mul(height)
            .ok_or("scene pixel count overflow")?;
        need(
            width >= 32
                && height >= 32
                && width <= super::MAX_AXIS
                && height <= super::MAX_AXIS
                && pixels <= super::MAX_PIXELS
                && pixels.checked_mul(3) == Some(rgb.len()),
            "scene dimensions or complete decoded RGB differ",
        )?;
        Ok(Self { width, height, rgb })
    }
    fn reduce(self, end: Instant) -> Result<Reduced, String> {
        before(end)?;
        let maximum = self.width.max(self.height);
        let width = self.width * REDUCED_AXIS.min(maximum) / maximum;
        let height = self.height * REDUCED_AXIS.min(maximum) / maximum;
        need(
            width >= 24 && height >= 24,
            "scene aspect ratio has insufficient matching area",
        )?;
        let mut sums = vec![[0_u64; 4]; width * height];
        for y in 0..self.height {
            before(end)?;
            let row = y * height / self.height;
            for x in 0..self.width {
                let to = row * width + x * width / self.width;
                let from = (y * self.width + x) * 3;
                for c in 0..3 {
                    sums[to][c] += self.rgb[from + c] as u64;
                }
                sums[to][3] += 1;
            }
        }
        let mut pixels = Vec::with_capacity(width * height);
        for sum in sums {
            need(sum[3] != 0, "scene reduction produced an empty source bin")?;
            pixels.push([
                sum[0] as f64 / sum[3] as f64,
                sum[1] as f64 / sum[3] as f64,
                sum[2] as f64 / sum[3] as f64,
            ]);
        }
        before(end)?;
        let mut integral = vec![[0.0; 3]; (width + 1) * (height + 1)];
        for y in 0..height {
            before(end)?;
            for x in 0..width {
                let i = (y + 1) * (width + 1) + x + 1;
                for c in 0..3 {
                    integral[i][c] =
                        pixels[y * width + x][c] + integral[i - 1][c] + integral[i - width - 1][c]
                            - integral[i - width - 2][c];
                }
            }
        }
        Ok(Reduced {
            width,
            height,
            integral,
        })
    }
}
struct Reduced {
    width: usize,
    height: usize,
    integral: Vec<[f64; 3]>,
}
impl Reduced {
    // Bilinear interpolation of the integral, not of a few point samples,
    // integrates every reduced pixel covered by the candidate rectangle.
    fn integral_at(&self, x: f64, y: f64) -> [f64; 3] {
        let x = x.clamp(0.0, self.width as f64);
        let y = y.clamp(0.0, self.height as f64);
        let x0 = x.floor() as usize;
        let y0 = y.floor() as usize;
        let x1 = (x0 + 1).min(self.width);
        let y1 = (y0 + 1).min(self.height);
        let dx = x - x0 as f64;
        let dy = y - y0 as f64;
        let stride = self.width + 1;
        let mut out = [0.0; 3];
        for c in 0..3 {
            out[c] = self.integral[y0 * stride + x0][c] * (1.0 - dx) * (1.0 - dy)
                + self.integral[y0 * stride + x1][c] * dx * (1.0 - dy)
                + self.integral[y1 * stride + x0][c] * (1.0 - dx) * dy
                + self.integral[y1 * stride + x1][c] * dx * dy;
        }
        out
    }
    fn mean_box(&self, x0: f64, y0: f64, x1: f64, y1: f64) -> [f64; 3] {
        let a = self.integral_at(x0, y0);
        let b = self.integral_at(x1, y0);
        let c = self.integral_at(x0, y1);
        let d = self.integral_at(x1, y1);
        let area = (x1 - x0) * (y1 - y0);
        let mut out = [0.0; 3];
        for channel in 0..3 {
            out[channel] = (d[channel] - b[channel] - c[channel] + a[channel]) / area;
        }
        out
    }
    fn dimensions(&self, turns: u8) -> (usize, usize) {
        if turns % 2 == 0 {
            (self.width, self.height)
        } else {
            (self.height, self.width)
        }
    }
    fn oriented_box(&self, x0: f64, y0: f64, x1: f64, y1: f64, turns: u8) -> [f64; 3] {
        let w = self.width as f64;
        let h = self.height as f64;
        match turns {
            0 => self.mean_box(x0, y0, x1, y1),
            1 => self.mean_box(y0, h - x1, y1, h - x0),
            2 => self.mean_box(w - x1, h - y1, w - x0, h - y0),
            3 => self.mean_box(w - y1, x0, w - y0, x1),
            _ => unreachable!("only the fixed four rotations are generated"),
        }
    }
}

#[derive(Clone, Copy, Eq, PartialEq, Serialize)]
struct Rect {
    left_quarters: u32,
    top_quarters: u32,
    width_quarters: u32,
    height_quarters: u32,
}
impl Rect {
    fn fits(self, image: &Reduced) -> bool {
        let w = image.width as u32 * UNIT;
        let h = image.height as u32 * UNIT;
        self.width_quarters >= 16 * UNIT
            && self.height_quarters >= 16 * UNIT
            && self
                .left_quarters
                .checked_add(self.width_quarters)
                .is_some_and(|n| n <= w)
            && self
                .top_quarters
                .checked_add(self.height_quarters)
                .is_some_and(|n| n <= h)
            && self.width_quarters as u64
                * self.height_quarters as u64
                * MIN_WINDOW_AREA_DENOMINATOR
                >= w as u64 * h as u64 * MIN_WINDOW_AREA_NUMERATOR
    }
    fn shifted(self, dx: i32, dy: i32, dw: i32, dh: i32) -> Option<Self> {
        Some(Self {
            left_quarters: self.left_quarters.checked_add_signed(dx)?,
            top_quarters: self.top_quarters.checked_add_signed(dy)?,
            width_quarters: self.width_quarters.checked_add_signed(dw)?,
            height_quarters: self.height_quarters.checked_add_signed(dh)?,
        })
    }
    fn same_area(self, other: Self) -> bool {
        let left = self.left_quarters.max(other.left_quarters);
        let top = self.top_quarters.max(other.top_quarters);
        let right = (self.left_quarters + self.width_quarters)
            .min(other.left_quarters + other.width_quarters);
        let bottom = (self.top_quarters + self.height_quarters)
            .min(other.top_quarters + other.height_quarters);
        let intersection = right.saturating_sub(left) as u64 * bottom.saturating_sub(top) as u64;
        // Every candidate already matched the same actual photo's centered
        // crop. An accepted nested crop is not a second displayed copy.
        // Compare shared coverage of the smaller region; disjoint copies
        // still have zero intersection and remain ambiguous.
        let smaller = (self.width_quarters as u64 * self.height_quarters as u64)
            .min(other.width_quarters as u64 * other.height_quarters as u64);
        intersection * 100 >= smaller * 65
    }
}
#[derive(Clone, Copy, Serialize)]
struct PhotoCrop {
    left: f64,
    top: f64,
    width: f64,
    height: f64,
}
fn photo_crop(photo: &Reduced, rect: Rect, turns: u8) -> Option<(PhotoCrop, f64)> {
    let (w, h) = photo.dimensions(turns);
    let aspect = rect.width_quarters as f64 / rect.height_quarters as f64;
    let (width, height) = if w as f64 / h as f64 > aspect {
        (h as f64 * aspect, h as f64)
    } else {
        (w as f64, w as f64 / aspect)
    };
    let retained = width * height / (w * h) as f64;
    (retained >= MIN_PHOTO_AREA).then_some((
        PhotoCrop {
            left: (w as f64 - width) / 2.0,
            top: (h as f64 - height) / 2.0,
            width,
            height,
        },
        retained,
    ))
}
#[derive(Clone, Copy)]
struct Candidate {
    rect: Rect,
    turns: u8,
    crop: PhotoCrop,
    photo_area: f64,
    correlation: f64,
    rgb_error: f64,
    photo_std: f64,
    window_std: f64,
    texture: f64,
    colors: usize,
}
impl Candidate {
    fn score(self) -> f64 {
        self.correlation - self.rgb_error / 255.0 * 0.25
    }
    fn covered_area(self) -> f64 {
        self.photo_area * self.rect.width_quarters as f64 * self.rect.height_quarters as f64
    }
    fn accepted(self) -> bool {
        self.correlation >= MIN_CORRELATION
            && self.rgb_error <= MAX_RGB_ERROR
            && self.photo_std >= MIN_STANDARD_DEVIATION
            && self.window_std >= MIN_STANDARD_DEVIATION
            && self.texture >= MIN_SECOND_DIFFERENCE
            && self.colors >= MIN_COLOR_BUCKETS
    }
}
fn luma(rgb: [f64; 3]) -> f64 {
    (77.0 * rgb[0] + 150.0 * rgb[1] + 29.0 * rgb[2]) / 256.0
}
fn evaluate(
    window: &Reduced,
    photo: &Reduced,
    rect: Rect,
    turns: u8,
    count: &mut usize,
    end: Instant,
) -> Result<Option<Candidate>, String> {
    if !rect.fits(window) {
        return Ok(None);
    }
    let Some((crop, photo_area)) = photo_crop(photo, rect, turns) else {
        return Ok(None);
    };
    *count += 1;
    need(
        *count <= MAX_CANDIDATES,
        "scene matching exceeded its fixed candidate bound",
    )?;
    if *count % 32 == 0 {
        before(end)?;
    }
    let mut a = [0.0; SAMPLES];
    let mut b = [0.0; SAMPLES];
    let mut rgb_error = 0.0;
    let mut colors = BTreeSet::new();
    for gy in 0..GH {
        for gx in 0..GW {
            let fx0 = gx as f64 / GW as f64;
            let fy0 = gy as f64 / GH as f64;
            let fx1 = (gx + 1) as f64 / GW as f64;
            let fy1 = (gy + 1) as f64 / GH as f64;
            let p = photo.oriented_box(
                crop.left + fx0 * crop.width,
                crop.top + fy0 * crop.height,
                crop.left + fx1 * crop.width,
                crop.top + fy1 * crop.height,
                turns,
            );
            let w = window.mean_box(
                (rect.left_quarters as f64 + fx0 * rect.width_quarters as f64) / UNIT as f64,
                (rect.top_quarters as f64 + fy0 * rect.height_quarters as f64) / UNIT as f64,
                (rect.left_quarters as f64 + fx1 * rect.width_quarters as f64) / UNIT as f64,
                (rect.top_quarters as f64 + fy1 * rect.height_quarters as f64) / UNIT as f64,
            );
            let index = gy * GW + gx;
            a[index] = luma(p);
            b[index] = luma(w);
            let mut bucket = 0_u16;
            for c in 0..3 {
                rgb_error += (p[c] - w[c]).abs();
                bucket = (bucket << 4) | ((p[c].clamp(0.0, 255.0) as u16) >> 4);
            }
            colors.insert(bucket);
        }
    }
    let am = a.iter().sum::<f64>() / SAMPLES as f64;
    let bm = b.iter().sum::<f64>() / SAMPLES as f64;
    let av = a.iter().map(|v| (v - am) * (v - am)).sum::<f64>() / SAMPLES as f64;
    let bv = b.iter().map(|v| (v - bm) * (v - bm)).sum::<f64>() / SAMPLES as f64;
    if av < MIN_STANDARD_DEVIATION.powi(2) || bv < MIN_STANDARD_DEVIATION.powi(2) {
        return Ok(None);
    }
    let covariance = a
        .iter()
        .zip(&b)
        .map(|(a, b)| (a - am) * (b - bm))
        .sum::<f64>()
        / SAMPLES as f64;
    let correlation = (covariance / (av * bv).sqrt()).clamp(-1.0, 1.0);
    let mut texture = 0.0;
    let mut edges = 0;
    for y in 0..GH {
        for x in 1..GW - 1 {
            texture += (a[y * GW + x - 1] - 2.0 * a[y * GW + x] + a[y * GW + x + 1]).abs();
            edges += 1;
        }
    }
    for y in 1..GH - 1 {
        for x in 0..GW {
            texture += (a[(y - 1) * GW + x] - 2.0 * a[y * GW + x] + a[(y + 1) * GW + x]).abs();
            edges += 1;
        }
    }
    Ok(Some(Candidate {
        rect,
        turns,
        crop,
        photo_area,
        correlation,
        rgb_error: rgb_error / (SAMPLES * 3) as f64,
        photo_std: av.sqrt(),
        window_std: bv.sqrt(),
        texture: texture / edges as f64,
        colors: colors.len(),
    }))
}
fn steps(minimum: u32, maximum: u32, step: u32) -> Vec<u32> {
    let mut values = Vec::new();
    let mut current = minimum;
    while current <= maximum {
        values.push(current);
        match current.checked_add(step) {
            Some(n) => current = n,
            None => break,
        }
    }
    if values.last().copied() != Some(maximum) {
        values.push(maximum);
    }
    values
}
#[derive(Serialize)]
struct SceneMatch {
    algorithm: &'static str,
    reduced_window_dimensions: [usize; 2],
    reduced_photo_dimensions: [usize; 2],
    window_match_rectangle: Rect,
    oriented_photo_center_crop: PhotoCrop,
    photograph_quarter_turns: u8,
    photograph_retained_area_millionths: u64,
    luminance_correlation_millionths: i64,
    raw_mean_absolute_rgb_error_milli: u64,
    photo_standard_deviation_milli: u64,
    window_standard_deviation_milli: u64,
    photo_second_difference_milli: u64,
    quantized_photo_colors: usize,
    candidates_evaluated: usize,
    minimum_window_coverage_millionths: u64,
    minimum_photo_coverage_millionths: u64,
    fixed_minimum_luma_correlation_millionths: u64,
    fixed_maximum_mean_rgb_error_milli: u64,
    comparison_grid: [usize; 2],
    complete_reduced_regions_integrated: bool,
    caller_images_or_parameters_admitted: bool,
}
fn match_images(
    window: RawImage<'_>,
    photo: RawImage<'_>,
    end: Instant,
) -> Result<SceneMatch, String> {
    before(end)?;
    let window = window.reduce(end)?;
    let photo = photo.reduce(end)?;
    let mut count = 0;
    let mut candidates = Vec::new();
    let ww = window.width as u32 * UNIT;
    let wh = window.height as u32 * UNIT;
    for turns in 0..4 {
        for width in steps(ww.div_ceil(2), ww, 8 * UNIT) {
            for height in steps(wh.div_ceil(2), wh, 8 * UNIT) {
                for left in steps(0, ww - width, 8 * UNIT) {
                    for top in steps(0, wh - height, 8 * UNIT) {
                        if let Some(c) = evaluate(
                            &window,
                            &photo,
                            Rect {
                                left_quarters: left,
                                top_quarters: top,
                                width_quarters: width,
                                height_quarters: height,
                            },
                            turns,
                            &mut count,
                            end,
                        )? {
                            candidates.push(c);
                        }
                    }
                }
            }
        }
    }
    need(
        !candidates.is_empty(),
        "scene match has no sufficiently textured candidate",
    )?;
    candidates.sort_by(|a, b| b.score().total_cmp(&a.score()));
    let seeds: Vec<_> = candidates.iter().take(8).copied().collect();
    for seed in seeds {
        let mut best = seed;
        for step in [16, 8, 4, 2, 1] {
            let center = best.rect;
            for dx in [-step, 0, step] {
                for dy in [-step, 0, step] {
                    for dw in [-step, 0, step] {
                        for dh in [-step, 0, step] {
                            if let Some(rect) = center.shifted(dx, dy, dw, dh) {
                                if let Some(c) =
                                    evaluate(&window, &photo, rect, seed.turns, &mut count, end)?
                                {
                                    if c.score() > best.score() {
                                        best = c;
                                    }
                                    candidates.push(c);
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    before(end)?;
    candidates.sort_by(|a, b| b.score().total_cmp(&a.score()));
    let best = candidates
        .iter()
        .copied()
        .filter(|c| c.accepted())
        // Thresholds are unchanged. Prefer the greatest actual common
        // coverage, rather than a floating-point score tie on a nested crop.
        .max_by(|a, b| {
            a.covered_area()
                .total_cmp(&b.covered_area())
                .then_with(|| a.score().total_cmp(&b.score()))
        })
        .ok_or("actual photograph does not meet the fixed prior-window visual criteria")?;
    need(
        !candidates.iter().any(|c| {
            c.accepted() && !best.rect.same_area(c.rect) && c.correlation >= best.correlation - 0.03
        }),
        "actual photograph has ambiguous matching regions in the prior window",
    )?;
    before(end)?;
    Ok(SceneMatch {
        algorithm: "droidloom.camera-owned-photo-rgb-match.v1",
        reduced_window_dimensions: [window.width, window.height],
        reduced_photo_dimensions: [photo.width, photo.height],
        window_match_rectangle: best.rect,
        oriented_photo_center_crop: best.crop,
        photograph_quarter_turns: best.turns,
        photograph_retained_area_millionths: (best.photo_area * 1_000_000.0).round() as u64,
        luminance_correlation_millionths: (best.correlation * 1_000_000.0).round() as i64,
        raw_mean_absolute_rgb_error_milli: (best.rgb_error * 1000.0).round() as u64,
        photo_standard_deviation_milli: (best.photo_std * 1000.0).round() as u64,
        window_standard_deviation_milli: (best.window_std * 1000.0).round() as u64,
        photo_second_difference_milli: (best.texture * 1000.0).round() as u64,
        quantized_photo_colors: best.colors,
        candidates_evaluated: count,
        minimum_window_coverage_millionths: 500_000,
        minimum_photo_coverage_millionths: 600_000,
        fixed_minimum_luma_correlation_millionths: 970_000,
        fixed_maximum_mean_rgb_error_milli: 12_000,
        comparison_grid: [GW, GH],
        complete_reduced_regions_integrated: true,
        caller_images_or_parameters_admitted: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    fn deadline() -> Instant {
        Instant::now() + Duration::from_secs(30)
    }
    fn texture(width: usize, height: usize) -> Vec<u8> {
        let mut out = Vec::with_capacity(width * height * 3);
        for y in 0..height {
            for x in 0..width {
                let (x, y) = (x / 8, y / 8);
                out.extend([
                    (35 + (x * 47 + y * 29 + x * y * 13) % 180) as u8,
                    (30 + (x * 31 + y * 61 + x * y * 7) % 190) as u8,
                    (40 + (x * 73 + y * 17 + x * y * 19) % 175) as u8,
                ]);
            }
        }
        out
    }
    fn scale2(bytes: &[u8], width: usize, height: usize) -> Vec<u8> {
        let mut out = vec![0; width * height * 12];
        for y in 0..height * 2 {
            for x in 0..width * 2 {
                let from = ((y / 2) * width + x / 2) * 3;
                let to = (y * width * 2 + x) * 3;
                out[to..to + 3].copy_from_slice(&bytes[from..from + 3]);
            }
        }
        out
    }
    fn window(photo: &[u8], width: usize, height: usize, top: usize) -> Vec<u8> {
        let mut out = vec![7; width * (height + 2 * top) * 3];
        out[top * width * 3..(top + height) * width * 3].copy_from_slice(photo);
        out
    }
    fn rotate_clockwise(photo: &[u8], width: usize, height: usize) -> Vec<u8> {
        let mut out = vec![0; photo.len()];
        for y in 0..height {
            for x in 0..width {
                let from = (y * width + x) * 3;
                let to = (x * height + height - 1 - y) * 3;
                out[to..to + 3].copy_from_slice(&photo[from..from + 3]);
            }
        }
        out
    }

    #[test]
    fn native_camera_scene_matches_large_original_preview_and_complete_photo() {
        let original = texture(96, 64);
        let photo = scale2(&original, 96, 64);
        let mut visible = photo.clone();
        for v in &mut visible {
            *v = v.saturating_add(2);
        }
        let preview = window(&visible, 192, 128, 32);
        let result = match_images(
            RawImage::new(192, 192, &preview).unwrap(),
            RawImage::new(192, 128, &photo).unwrap(),
            deadline(),
        )
        .unwrap();
        assert_eq!(result.photograph_quarter_turns, 0);
        assert!(result.luminance_correlation_millionths >= 970_000);
        assert!(result.raw_mean_absolute_rgb_error_milli <= 3_000);
        assert!(result.photograph_retained_area_millionths >= 990_000);
        assert!(result.candidates_evaluated <= MAX_CANDIDATES);
        assert!(!result.caller_images_or_parameters_admitted);
    }

    #[test]
    fn native_camera_scene_matches_fixed_quarter_turn_without_orientation_credit() {
        let photo = texture(96, 64);
        let preview = window(&photo, 96, 64, 16);
        let encoded_orientation = rotate_clockwise(&photo, 96, 64);
        let result = match_images(
            RawImage::new(96, 96, &preview).unwrap(),
            RawImage::new(64, 96, &encoded_orientation).unwrap(),
            deadline(),
        )
        .unwrap();
        assert_eq!(result.photograph_quarter_turns, 3);
        assert!(result.luminance_correlation_millionths >= 999_000);
        assert!(result.raw_mean_absolute_rgb_error_milli <= 1);
    }

    #[test]
    fn native_camera_scene_rejects_wrong_flat_gradient_and_thumbnail_content() {
        let photo = texture(96, 64);
        let mut wrong = photo.clone();
        for (n, pixel) in wrong.chunks_exact_mut(3).enumerate() {
            pixel.copy_from_slice(&[
                ((n * 37 + 101) % 256) as u8,
                ((n * 53 + 7) % 256) as u8,
                ((n * 97 + 23) % 256) as u8,
            ]);
        }
        let wrong_window = window(&wrong, 96, 64, 16);
        assert!(
            match_images(
                RawImage::new(96, 96, &wrong_window).unwrap(),
                RawImage::new(96, 64, &photo).unwrap(),
                deadline()
            )
            .is_err()
        );
        let flat = vec![110; 96 * 64 * 3];
        let flat_window = window(&flat, 96, 64, 16);
        assert!(
            match_images(
                RawImage::new(96, 96, &flat_window).unwrap(),
                RawImage::new(96, 64, &flat).unwrap(),
                deadline()
            )
            .is_err()
        );
        let mut gradient = Vec::new();
        for _y in 0..64 {
            for x in 0..96 {
                gradient.extend([20 + x as u8 * 2; 3]);
            }
        }
        let gradient_window = window(&gradient, 96, 64, 16);
        assert!(
            match_images(
                RawImage::new(96, 96, &gradient_window).unwrap(),
                RawImage::new(96, 64, &gradient).unwrap(),
                deadline()
            )
            .is_err()
        );
        let mut thumbnail = vec![5; 96 * 96 * 3];
        for y in 0..32 {
            for x in 0..48 {
                let from = (y * 2 * 96 + x * 2) * 3;
                let to = ((y + 32) * 96 + x + 24) * 3;
                thumbnail[to..to + 3].copy_from_slice(&photo[from..from + 3]);
            }
        }
        assert!(
            match_images(
                RawImage::new(96, 96, &thumbnail).unwrap(),
                RawImage::new(96, 64, &photo).unwrap(),
                deadline()
            )
            .is_err()
        );
    }

    #[test]
    fn native_camera_scene_rejects_duplicate_large_regions_and_incomplete_rgb() {
        let photo = texture(96, 64);
        let mut duplicate = vec![0; 192 * 64 * 3];
        for y in 0..64 {
            for half in 0..2 {
                let to = (y * 192 + half * 96) * 3;
                duplicate[to..to + 96 * 3].copy_from_slice(&photo[y * 96 * 3..(y + 1) * 96 * 3]);
            }
        }
        let error = match_images(
            RawImage::new(192, 64, &duplicate).unwrap(),
            RawImage::new(96, 64, &photo).unwrap(),
            deadline(),
        )
        .err()
        .unwrap();
        assert!(error.contains("ambiguous"), "{error}");
        assert!(RawImage::new(96, 64, &photo[..photo.len() - 1]).is_err());
        assert!(RawImage::new(8_193, 64, &photo).is_err());
    }

    #[test]
    fn native_camera_scene_obeys_original_end_and_rejects_blank_search_space() {
        let photo = texture(96, 64);
        let preview = window(&photo, 96, 64, 16);
        assert!(
            match_images(
                RawImage::new(96, 96, &preview).unwrap(),
                RawImage::new(96, 64, &photo).unwrap(),
                Instant::now()
            )
            .is_err()
        );
        let wide = vec![60; 192 * 32 * 3];
        assert!(
            match_images(
                RawImage::new(192, 32, &wide).unwrap(),
                RawImage::new(96, 64, &photo).unwrap(),
                deadline()
            )
            .is_err()
        );
    }
}
