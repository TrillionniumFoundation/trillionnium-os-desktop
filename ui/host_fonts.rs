//! Shared host font policy for the two native renderers, not the Session ABI.
//!
//! Font bytes come only from host configuration. They are never accepted from
//! a model, Session IPC or Hepta projection. Glyph coverage is a bounded UI
//! sample, not a claim that an input method or all Unicode scripts work.
use ab_glyph::{Font, FontRef};
use eframe::egui;
use std::collections::BTreeSet;
use std::ffi::OsString;
use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};

const FONT_NAME: &str = "trill-host-cjk";
const MAX_FONT_BYTES: u64 = 32 * 1024 * 1024;
pub const CJK_SAMPLE: &str = "你好中文输入法候选词焦点测试笔记本地任务消息想草稿真实应用工作区设置受限终端计算器认证目标适配未装提交观察状态连接离线……、";
const FONT_PATH_ENV: &str = "TRILL_UI_CJK_FONT";
const FONT_INDEX_ENV: &str = "TRILL_UI_CJK_FONT_INDEX";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum FontError {
    InvalidConfiguration,
    Unreadable,
    NotRegularFile,
    TooLarge,
    InvalidFont,
    MissingSampleGlyphs,
    NotFound,
}

impl FontError {
    fn code(self) -> &'static str {
        match self {
            Self::InvalidConfiguration => "invalid_configuration",
            Self::Unreadable => "unreadable",
            Self::NotRegularFile => "not_regular_file",
            Self::TooLarge => "font_too_large",
            Self::InvalidFont => "invalid_font_or_face",
            Self::MissingSampleGlyphs => "missing_sample_glyphs",
            Self::NotFound => "no_usable_host_font",
        }
    }
}

#[derive(Clone, Debug)]
struct FontStatus {
    loaded: bool,
    source: &'static str,
    face: u32,
    bytes: usize,
    error: Option<FontError>,
}

impl FontStatus {
    fn unavailable(error: FontError) -> Self {
        Self {
            loaded: false,
            source: "builtin_only",
            face: 0,
            bytes: 0,
            error: Some(error),
        }
    }

    fn label(&self) -> &'static str {
        if self.loaded {
            "Chinese font: UI sample available in proportional and monospace text"
        } else {
            "Chinese font unavailable: select a host CJK font before judging Chinese rendering"
        }
    }
}

fn explicit_request(
    path: Option<OsString>,
    index: Option<OsString>,
) -> Result<Option<(PathBuf, u32)>, FontError> {
    let Some(path) = path else {
        return if index.is_none() {
            Ok(None)
        } else {
            Err(FontError::InvalidConfiguration)
        };
    };
    let path = PathBuf::from(path);
    if !path.is_absolute() {
        return Err(FontError::InvalidConfiguration);
    }
    let face = match index {
        None => 0,
        Some(value) => value
            .to_str()
            .and_then(|text| text.parse::<u32>().ok())
            .ok_or(FontError::InvalidConfiguration)?,
    };
    Ok(Some((path, face)))
}

fn read_bounded_font(path: &Path) -> Result<Vec<u8>, FontError> {
    // Reject obvious devices/directories/FIFOs before opening, then check the
    // opened file too. These are trusted host configuration paths, not a
    // capability to open arbitrary renderer-supplied files.
    let before = std::fs::metadata(path).map_err(|_| FontError::Unreadable)?;
    if !before.is_file() {
        return Err(FontError::NotRegularFile);
    }
    if before.len() > MAX_FONT_BYTES {
        return Err(FontError::TooLarge);
    }
    let file = File::open(path).map_err(|_| FontError::Unreadable)?;
    let metadata = file.metadata().map_err(|_| FontError::Unreadable)?;
    if !metadata.is_file() {
        return Err(FontError::NotRegularFile);
    }
    if metadata.len() > MAX_FONT_BYTES {
        return Err(FontError::TooLarge);
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    file.take(MAX_FONT_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| FontError::Unreadable)?;
    if bytes.len() as u64 > MAX_FONT_BYTES {
        return Err(FontError::TooLarge);
    }
    Ok(bytes)
}

fn validate_font(bytes: &[u8], index: u32) -> Result<(), FontError> {
    // Use the same fallible parser as egui's font implementation before
    // egui gets the bytes. Invalid files must never reach its panic wrapper.
    let font =
        FontRef::try_from_slice_and_index(bytes, index).map_err(|_| FontError::InvalidFont)?;
    if CJK_SAMPLE
        .chars()
        .any(|character| font.glyph_id(character).0 == 0)
    {
        return Err(FontError::MissingSampleGlyphs);
    }
    Ok(())
}

fn definitions(bytes: Vec<u8>, index: u32) -> egui::FontDefinitions {
    let mut fonts = egui::FontDefinitions::default();
    let mut data = egui::FontData::from_owned(bytes);
    data.index = index;
    fonts.font_data.insert(FONT_NAME.to_owned(), data.into());
    fonts
        .families
        .entry(egui::FontFamily::Proportional)
        .or_default()
        .insert(0, FONT_NAME.to_owned());
    // Keep the ordinary ASCII monospace font. It will fall back to this face
    // for CJK glyphs, including the native app's default TextEdit family.
    fonts
        .families
        .entry(egui::FontFamily::Monospace)
        .or_default()
        .push(FONT_NAME.to_owned());
    fonts
}

fn load(
    path: &Path,
    index: u32,
    source: &'static str,
) -> Result<(egui::FontDefinitions, FontStatus), FontError> {
    let bytes = read_bounded_font(path)?;
    validate_font(&bytes, index)?;
    let status = FontStatus {
        loaded: true,
        source,
        face: index,
        bytes: bytes.len(),
        error: None,
    };
    Ok((definitions(bytes, index), status))
}

/// An explicit override is authoritative. A bad override leaves the built-in
/// fonts active with a visible diagnostic; it cannot silently qualify a
/// different font as the selected file. No font file is copied or installed.
pub fn install(ctx: &egui::Context) {
    let result = match explicit_request(
        std::env::var_os(FONT_PATH_ENV),
        std::env::var_os(FONT_INDEX_ENV),
    ) {
        Err(error) => Err(error),
        Ok(Some((path, index))) => load(&path, index, "explicit"),
        Ok(None) => {
            let mut selected = Err(FontError::NotFound);
            for path in [
                "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
                "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/truetype/arphic/ukai.ttc",
            ] {
                if let Ok(font) = load(Path::new(path), 0, "system_candidate") {
                    selected = Ok(font);
                    break;
                }
            }
            selected
        }
    };
    let status = match result {
        Ok((fonts, status)) => {
            ctx.set_fonts(fonts);
            status
        }
        Err(error) => FontStatus::unavailable(error),
    };
    let sample_glyphs = CJK_SAMPLE.chars().collect::<BTreeSet<_>>().len();
    eprintln!(
        "TRILL_UI_FONT_V1 loaded={} source={} face={} bytes={} sample_glyphs={} error={}",
        status.loaded,
        status.source,
        status.face,
        status.bytes,
        if status.loaded { sample_glyphs } else { 0 },
        status.error.map_or("none", FontError::code),
    );
    ctx.data_mut(|data| data.insert_temp(egui::Id::new(FONT_NAME), status));
}

pub fn status_label(ctx: &egui::Context) -> &'static str {
    ctx.data(|data| data.get_temp::<FontStatus>(egui::Id::new(FONT_NAME)))
        .map_or("Chinese font: not checked", |status| status.label())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

    fn private_test_dir() -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "trill-font-test-{}-{}",
            std::process::id(),
            NEXT_TEMP.fetch_add(1, Ordering::Relaxed),
        ));
        std::fs::create_dir(&path).unwrap();
        path
    }

    #[test]
    fn override_requires_an_absolute_path_and_valid_face_index() {
        assert_eq!(explicit_request(None, None), Ok(None));
        assert_eq!(
            explicit_request(None, Some("1".into())),
            Err(FontError::InvalidConfiguration)
        );
        assert_eq!(
            explicit_request(Some("font.ttf".into()), None),
            Err(FontError::InvalidConfiguration)
        );
        assert_eq!(
            explicit_request(Some("/font.ttc".into()), Some("-1".into())),
            Err(FontError::InvalidConfiguration)
        );
        assert_eq!(
            explicit_request(Some("/font.ttc".into()), Some("2".into())),
            Ok(Some((PathBuf::from("/font.ttc"), 2)))
        );
    }

    #[test]
    fn corrupt_font_and_wrong_face_are_rejected_before_egui() {
        assert_eq!(validate_font(b"not a font", 0), Err(FontError::InvalidFont));
        let defaults = egui::FontDefinitions::default();
        let latin = defaults.font_data["Ubuntu-Light"].font.as_ref();
        assert_eq!(validate_font(latin, 0), Err(FontError::MissingSampleGlyphs));
        assert_eq!(validate_font(latin, u32::MAX), Err(FontError::InvalidFont));
    }

    #[test]
    fn oversized_file_and_directory_are_rejected_without_loading() {
        let directory = private_test_dir();
        assert_eq!(
            read_bounded_font(&directory),
            Err(FontError::NotRegularFile)
        );
        let path = directory.join("oversized.ttf");
        File::create(&path)
            .unwrap()
            .set_len(MAX_FONT_BYTES + 1)
            .unwrap();
        assert_eq!(read_bounded_font(&path), Err(FontError::TooLarge));
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    #[ignore = "requires TRILL_UI_TEST_CJK_FONT to select a real host font"]
    fn selected_real_font_covers_egui_proportional_and_monospace() {
        let path = std::env::var_os("TRILL_UI_TEST_CJK_FONT").expect("explicit test font required");
        let (definitions, _) = load(Path::new(&path), 0, "test").unwrap();
        let fonts = egui::epaint::text::Fonts::new(1.0, 2048, definitions);
        for family in [egui::FontFamily::Proportional, egui::FontFamily::Monospace] {
            assert!(fonts.has_glyphs(&egui::FontId::new(18.0, family), CJK_SAMPLE));
        }
        let raw = read_bounded_font(Path::new(&path)).unwrap();
        let font = FontRef::try_from_slice(&raw).unwrap();
        for character in ['中', '文', '输', '入'] {
            let glyph = font.glyph_id(character).with_scale(20.0);
            let outlined = font
                .outline_glyph(glyph)
                .expect("CJK sample needs drawable outlines");
            let mut ink = 0;
            outlined.draw(|_, _, coverage| {
                if coverage > 0.0 {
                    ink += 1;
                }
            });
            assert!(ink > 0, "CJK glyph must rasterize into actual ink");
        }
    }
}
