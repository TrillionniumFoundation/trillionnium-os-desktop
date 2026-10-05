//! Actual fork custody, with no parallel harness threads or simulated PID.
//! Syscalls are test-only. The child explicitly drops its inherited writer,
//! then uses _exit so it cannot run the parent's fixture cleanup.
use hepta_session_core::{
    JournalOpenPolicy as OpenPolicy, ManagedOpenPolicy, ReceiptJournal,
    ReceiptLifecycleState as State,
};
use std::fs;
use std::io::{Read, Write};
use std::os::unix::net::UnixStream;
use std::time::Duration;

#[allow(dead_code)]
#[path = "support/journal_chain_fixture.rs"]
mod fixture;
use fixture::{ID, Temp, event};

fn exercise(managed: bool) {
    let parent = Temp::new();
    let root = parent.path(if managed { "managed" } else { "legacy.journal" });
    let mut writer = if managed {
        ReceiptJournal::create_managed(&root, ID, 1).unwrap()
    } else {
        ReceiptJournal::create(&root, ID, 1).unwrap()
    };
    writer.append(event("prior", State::Requested)).unwrap();
    writer.append(event("prior", State::Interrupted)).unwrap();
    let fact = writer.receipt_fact("prior", [1; 32]).unwrap();
    let before = fs::read(writer.path()).unwrap();
    let lease = parent.path("legacy.journal.writer-lock");
    let lease_before = (!managed).then(|| fs::read(&lease).unwrap());
    let (mut receiver, mut sender) = UnixStream::pair().unwrap();
    // SAFETY: this standalone test main has never started another thread.
    let pid = unsafe { libc::fork() };
    assert!(pid >= 0, "real fork is required, not skipped");
    if pid == 0 {
        drop(receiver);
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            assert!(fact.receipt_id().is_err());
            assert!(fact.request_sha256().is_err());
            assert!(fact.lifecycle().is_err());
            assert!(fact.record_sha256().is_err());
            assert!(!writer.is_managed());
            assert!(!writer.managed_rotation_due());
            assert!(writer.append(event("child", State::Requested)).is_err());
            assert!(writer.inspect().is_err());
            assert!(writer.contains_receipt("prior").is_err());
            assert!(writer.has_unresolved_receipts().is_err());
            assert!(writer.execution_reconciliation_facts().is_err());
            assert!(writer.receipt_fact("prior", [1; 32]).is_err());
            assert!(writer.seal().is_err());
            drop(writer);
            // Child close must preserve the parent's OFD lease. A fresh open
            // must still refuse even in this child after inherited close.
            let reopened = if managed {
                ReceiptJournal::open_managed(&root, ID, ManagedOpenPolicy::STRICT)
            } else {
                ReceiptJournal::open(&root, OpenPolicy::STRICT)
            };
            assert!(reopened.is_err());
        }))
        .is_ok();
        let _ = sender.write_all(&[u8::from(result)]);
        // SAFETY: avoid inherited parent cleanup, and terminate this test child.
        unsafe {
            libc::_exit(if result { 0 } else { 1 });
        }
    }
    drop(sender);
    receiver
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let mut result = [0];
    receiver.read_exact(&mut result).unwrap();
    let mut status = 0;
    // SAFETY: reap exactly the child PID returned by fork.
    assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
    assert_eq!(status, 0);
    assert_eq!(result, [1]);
    assert_eq!(fs::read(writer.path()).unwrap(), before);
    if let Some(bytes) = lease_before {
        assert_eq!(
            fs::read(&lease).unwrap(),
            bytes,
            "child Drop altered the live parent lease"
        );
    }
    assert_eq!(fact.receipt_id().unwrap(), "prior");
    let reopened = if managed {
        ReceiptJournal::open_managed(&root, ID, ManagedOpenPolicy::STRICT)
    } else {
        ReceiptJournal::open(&root, OpenPolicy::STRICT)
    };
    assert!(reopened.is_err(), "parent must remain the sole writer");
    writer
        .append(event("parent-after-fork", State::Requested))
        .unwrap();
    writer
        .append(event("parent-after-fork", State::Interrupted))
        .unwrap();
    assert_eq!(
        writer
            .receipt_fact("parent-after-fork", [1; 32])
            .unwrap()
            .lifecycle()
            .unwrap(),
        State::Interrupted
    );
}

fn main() {
    exercise(false);
    exercise(true);
    println!(
        "actual fork: inherited legacy/managed writes and facts refused; parent sole writer preserved"
    );
}
