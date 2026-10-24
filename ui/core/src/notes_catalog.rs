//! Read-only selection of the existing application checkpoints. This is not
//! another document or operation store; all content remains in document.json.

use super::*;
use crate::notes::sha256_hex;
use std::ffi::CStr;
use std::time::UNIX_EPOCH;

const MAX_DIRECTORY_ENTRIES: usize = 1024;

/// A historical text selection, never an effect target grant. The complete
/// snapshot digest fences changes between listing and explicit reopening.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SavedNote {
    pub target: NotesTargetIdentity,
    pub revision: u64,
    pub checkpoint_sha256: String,
    pub preview: String,
    pub modified_unix_ms: u64,
}

#[derive(Clone, Debug, Default)]
pub struct SavedNotes {
    pub entries: Vec<SavedNote>,
    /// Live/locked, corrupt or custody-invalid entries are never presented as
    /// safely recoverable. The caller can report their count without opening
    /// arbitrary files or discarding them.
    pub unavailable: usize,
}

pub(super) struct SavedText {
    pub reference: SavedNote,
    pub text: String,
    // Hold the original incarnation lock until the new local save completes.
    _lock: File,
}

pub(super) fn read(root: &File, target: &NotesTargetIdentity) -> io::Result<SavedText> {
    let directory = open_incarnation(root, target, false)?;
    // Unlike recovery startup, ordinary selection never creates a missing lock.
    let lock = open_file(&directory, "lock", libc::O_RDWR)?;
    if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let file = open_file(&directory, "document.json", libc::O_RDONLY)?;
    let modified_unix_ms = file
        .metadata()?
        .modified()?
        .duration_since(UNIX_EPOCH)
        .ok()
        .and_then(|value| u64::try_from(value.as_millis()).ok())
        .unwrap_or(0);
    let mut raw = Vec::new();
    file.take(MAX_CHECKPOINT_BYTES + 1).read_to_end(&mut raw)?;
    let document = NotesDocument::restore_checkpoint(&raw, target).map_err(protocol_error)?;
    let preview: String = document
        .text()
        .chars()
        .map(|character| {
            if character.is_whitespace() {
                ' '
            } else {
                character
            }
        })
        .filter(|character| {
            !character.is_control()
                && !matches!(*character as u32, 0x200e..=0x200f | 0x202a..=0x202e | 0x2066..=0x2069)
        })
        .take(48)
        .collect();
    Ok(SavedText {
        reference: SavedNote {
            target: target.clone(),
            revision: document.revision(),
            checkpoint_sha256: sha256_hex(&raw),
            preview,
            modified_unix_ms,
        },
        text: document.text().to_owned(),
        _lock: lock,
    })
}

pub(super) fn list(root: &File, current: &NotesTargetIdentity) -> io::Result<SavedNotes> {
    let mut result = SavedNotes::default();
    for name in directory_names(root)? {
        let Some(target) = target_from_name(&name) else {
            continue;
        };
        if &target == current {
            continue;
        }
        match read(root, &target) {
            Ok(saved) if saved.reference.revision > 0 => result.entries.push(saved.reference),
            Ok(_) => {}
            Err(_) => result.unavailable += 1,
        }
    }
    result.entries.sort_by(|left, right| {
        right
            .modified_unix_ms
            .cmp(&left.modified_unix_ms)
            .then_with(|| {
                left.target
                    .destination_id()
                    .cmp(&right.target.destination_id())
            })
    });
    Ok(result)
}

fn target_from_name(name: &str) -> Option<NotesTargetIdentity> {
    let mut parts = name.split('-');
    let session_instance = parts.next()?.to_owned();
    let task = parts.next()?;
    let incarnation = parts.next()?.to_owned();
    if parts.next().is_some() {
        return None;
    }
    let target = NotesTargetIdentity {
        session_instance,
        task_id: task.parse().ok()?,
        incarnation,
    };
    // Reject alternate spellings rather than silently reading another name.
    if target.task_id.to_string() != task || target.validate().is_err() {
        return None;
    }
    Some(target)
}

struct Directory(*mut libc::DIR);

impl Drop for Directory {
    fn drop(&mut self) {
        unsafe { libc::closedir(self.0) };
    }
}

fn directory_names(root: &File) -> io::Result<Vec<String>> {
    // openat(".") creates an independent directory cursor pinned to the same
    // root inode. dup alone would share its offset across subsequent refreshes.
    let fd = unsafe {
        libc::openat(
            root.as_raw_fd(),
            c".".as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    let pointer = unsafe { libc::fdopendir(fd) };
    if pointer.is_null() {
        let error = io::Error::last_os_error();
        unsafe { libc::close(fd) };
        return Err(error);
    }
    let directory = Directory(pointer);
    let mut names = Vec::new();
    let mut visited = 0;
    loop {
        unsafe { *libc::__errno_location() = 0 };
        let entry = unsafe { libc::readdir(directory.0) };
        if entry.is_null() {
            let error = io::Error::last_os_error();
            return if error.raw_os_error() == Some(0) {
                Ok(names)
            } else {
                Err(error)
            };
        }
        // readdir guarantees the name is NUL terminated and valid until the
        // next call. Copy it before advancing; no d_type/inode claim is trusted.
        let name = unsafe { CStr::from_ptr((*entry).d_name.as_ptr()) }.to_bytes();
        if matches!(name, b"." | b"..") {
            continue;
        }
        visited += 1;
        if visited > MAX_DIRECTORY_ENTRIES {
            return Err(io::Error::other(
                "saved Notes directory exceeds the 1024-entry bound",
            ));
        }
        if let Ok(name) = std::str::from_utf8(name) {
            names.push(name.to_owned());
        }
    }
}
