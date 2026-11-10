use super::*;
use std::{
    fs::OpenOptions,
    io::{Read, Seek, SeekFrom, Write},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};
use windows_sys::Win32::{
    Foundation::{DUPLICATE_SAME_ACCESS, HANDLE_FLAG_INHERIT},
    System::Pipes::CreatePipe,
};

fn pipe() -> (OwnedHandle, OwnedHandle) {
    let (mut read, mut write) = (null_mut(), null_mut());
    // SAFETY: fresh, non-inheritable anonymous pipe handles for this test only.
    assert_ne!(
        unsafe { CreatePipe(&mut read, &mut write, std::ptr::null(), 0) },
        0
    );
    unsafe {
        (
            OwnedHandle::from_raw_handle(read),
            OwnedHandle::from_raw_handle(write),
        )
    }
}

#[test]
fn invalid_and_duplicate_identifiers_fail_without_adopting_a_source() {
    for ids in [
        InheritedPacketHandles {
            packet_input: 0,
            packet_output: 2,
            fake_ip_journal: 3,
        },
        InheritedPacketHandles {
            packet_input: 1,
            packet_output: 1,
            fake_ip_journal: 3,
        },
        InheritedPacketHandles {
            packet_input: u64::MAX,
            packet_output: 2,
            fake_ip_journal: 3,
        },
    ] {
        assert!(handles(ids).is_err());
    }
}

#[test]
fn distinct_numeric_handles_to_the_same_object_cannot_alias_stdio() {
    let (input, output) = pipe();
    let (other, _other_write) = pipe();
    let mut raw = null_mut();
    // SAFETY: independent alias owner of this test's input, not real stdio.
    assert_ne!(
        unsafe {
            DuplicateHandle(
                GetCurrentProcess(),
                input.as_raw_handle(),
                GetCurrentProcess(),
                &mut raw,
                0,
                0,
                DUPLICATE_SAME_ACCESS,
            )
        },
        0
    );
    let alias = unsafe { OwnedHandle::from_raw_handle(raw) };
    assert_ne!(input.as_raw_handle(), alias.as_raw_handle());
    let resources = [
        input.as_raw_handle(),
        output.as_raw_handle(),
        other.as_raw_handle(),
    ];
    assert!(aliases(&resources, &[alias.as_raw_handle(), null_mut(), null_mut()]).is_err());
    assert!(
        aliases(
            &[
                input.as_raw_handle(),
                alias.as_raw_handle(),
                other.as_raw_handle()
            ],
            &[null_mut(); 3]
        )
        .is_err()
    );
}

#[test]
fn cloned_roles_transfer_pipe_and_journal_data_without_closing_the_originals() {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    let path = std::env::temp_dir().join(format!(
        "swirl-worker-resource-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    struct Remove(std::path::PathBuf);
    impl Drop for Remove {
        fn drop(&mut self) {
            let _ = std::fs::remove_file(&self.0);
        }
    }
    let _remove = Remove(path.clone());
    let mut journal = OpenOptions::new()
        .create_new(true)
        .read(true)
        .write(true)
        .open(path)
        .unwrap();
    let (input, producer) = pipe();
    let (consumer, output) = pipe();
    let mut files = clone_inherited_packet_resources(InheritedPacketHandles {
        packet_input: input.as_raw_handle() as u64,
        packet_output: output.as_raw_handle() as u64,
        fake_ip_journal: journal.as_raw_handle() as u64,
    })
    .unwrap();
    for file in [
        &files.packet_input,
        &files.packet_output,
        &files.fake_ip_journal,
    ] {
        let mut flags = 0;
        assert_ne!(
            unsafe { GetHandleInformation(file.as_raw_handle(), &mut flags) },
            0
        );
        assert_eq!(flags & HANDLE_FLAG_INHERIT, 0);
    }
    File::from(producer).write_all(b"incoming").unwrap();
    let mut received = [0; 8];
    files.packet_input.read_exact(&mut received).unwrap();
    assert_eq!(&received, b"incoming");
    files.packet_output.write_all(b"reply").unwrap();
    let mut reply = [0; 5];
    File::from(consumer).read_exact(&mut reply).unwrap();
    assert_eq!(&reply, b"reply");
    files.fake_ip_journal.write_all(b"record\n").unwrap();
    files.fake_ip_journal.sync_all().unwrap();
    drop(files);
    kind(input.as_raw_handle(), FILE_TYPE_PIPE).unwrap();
    kind(output.as_raw_handle(), FILE_TYPE_PIPE).unwrap();
    journal.seek(SeekFrom::Start(0)).unwrap();
    let mut record = String::new();
    journal.read_to_string(&mut record).unwrap();
    assert_eq!(record, "record\n");
}
