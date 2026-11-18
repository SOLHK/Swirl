use super::open_private_journal;
use std::{
    io::{Read, Seek, SeekFrom, Write},
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static NEXT_PATH: AtomicU64 = AtomicU64::new(0);

struct JournalPath(PathBuf);

impl JournalPath {
    fn new() -> Self {
        Self(std::env::temp_dir().join(format!(
            "swirl-private-journal-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            // Clock precision is platform-dependent; parallel tests can
            // observe the same tick without owning the same fixture path.
            NEXT_PATH.fetch_add(1, Ordering::Relaxed)
        )))
    }
}

impl Drop for JournalPath {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

#[test]
fn private_journal_reopen_preserves_records_and_allows_torn_tail_repair() {
    let path = JournalPath::new();
    {
        let mut journal = open_private_journal(&path.0).unwrap();
        journal.write_all(b"stable\npartial").unwrap();
        journal.sync_all().unwrap();
    }
    let mut journal = open_private_journal(&path.0).unwrap();
    let mut original = Vec::new();
    journal.read_to_end(&mut original).unwrap();
    assert_eq!(original, b"stable\npartial");
    journal.set_len(7).unwrap();
    journal.seek(SeekFrom::Start(0)).unwrap();
    // An accidentally append-only adapter would ignore this cursor position.
    journal.write_all(b"STABLE\n").unwrap();
    journal.seek(SeekFrom::End(0)).unwrap();
    journal.write_all(b"next\n").unwrap();
    journal.sync_all().unwrap();
    drop(journal);
    assert_eq!(std::fs::read(&path.0).unwrap(), b"STABLE\nnext\n");
}

#[test]
fn private_journal_missing_parent_is_not_created_implicitly() {
    let missing = JournalPath::new();
    assert_eq!(
        open_private_journal(&missing.0.join("journal.jsonl"))
            .unwrap_err()
            .kind(),
        std::io::ErrorKind::NotFound
    );
    assert!(!missing.0.exists());
}

#[cfg(unix)]
#[test]
fn private_journal_creation_never_grants_group_other_or_execute_permissions() {
    use std::os::unix::fs::PermissionsExt;
    let path = JournalPath::new();
    let journal = open_private_journal(&path.0).unwrap();
    let mode = journal.metadata().unwrap().permissions().mode() & 0o777;
    // A stricter process umask may remove owner permissions; never add grants
    // beyond 0600, and do not mutate process-wide umask in concurrent tests.
    assert_eq!(mode & !0o600, 0);
}
