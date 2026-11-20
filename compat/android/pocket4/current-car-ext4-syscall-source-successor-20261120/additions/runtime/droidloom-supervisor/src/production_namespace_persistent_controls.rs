// Included only inside the existing production_namespace_tree::tests module.
// Production PreparedExecution/IdentityLease/HeldBackings functions are intact.
mod persistent_syscalls {
    use super::*;
    use crate::production_identity::tests::persistent_fixture::{APP, Case, FixtureRun, PersistentFixture, START};
    use crate::production_mounts::persistent_data::private_control::{
        self, ExpectedRetirement, PrivatePersistentData, VerifiedPrivateRetirement,
    };
    use std::os::unix::fs::FileExt;

    type Checked<T> = std::result::Result<T, Box<dyn std::error::Error>>;

    fn need(value: bool, message: &'static str) -> Checked<()> {
        if value { Ok(()) } else { Err(message.into()) }
    }

    fn tree(lease: IdentityLease) -> Checked<IsolatedNamespaces> {
        // Identical original owner pipeline, using fallible calls so the
        // enclosing fixture can retain a concrete failure/cleanup record.
        let mut owner = Owner::spawn(Some(lease), child::Mode::PersistentDataControl)?;
        owner.enter_userns()?;
        let (uids, gids) = owner.install_maps()?;
        owner.mapped_go(uids, gids)?;
        Ok(IsolatedNamespaces::from_mapped(MappedUserNamespace { owner })?)
    }

    #[derive(Clone, Copy)]
    enum Transfer { Correct, Swapped, ClosedWrite }

    fn attach(
        tree: &mut IsolatedNamespaces,
        mut bases: crate::production_mounts::private_control::PrivateControlMounts,
        mut data: PrivatePersistentData,
        stimulus: Transfer,
    ) -> Checked<(ExpectedRetirement, std::result::Result<(), String>)> {
        tree.verify_live_admission()?;
        need(tree.bases.is_none() && tree.persistent_data.is_none() && !tree.base_root_ready
            && tree.retirement.prepared.bases.is_none() && tree.retirement.prepared.persistent_data.is_none(),
            "fresh original private tree only")?;
        let (rights, devices, observed) = {
            let witness = tree.witness()?;
            let base = bases.descriptors_for_transfer(&witness)?;
            let devices = [descriptor_device(base[0])?, descriptor_device(base[1])?];
            let (roots, observed) = data.descriptors(&witness)?;
            let rights = [base[0].try_clone_to_owned()?, base[1].try_clone_to_owned()?,
                roots[0].try_clone_to_owned()?, roots[1].try_clone_to_owned()?];
            (rights, devices, observed)
        };
        // These are actual owner methods after real IDMAP and export. Neither
        // negative is a fabricated receipt or an unowned cleanup request.
        let second = data.descriptors(&tree.witness()?).err().ok_or("second export unexpectedly admitted")?;
        need(second.to_string().contains("exactly one private transfer attempt"), "second transfer must reject at original export state")?;
        let premature = data.try_retire_untransferred().err().ok_or("post-export untransferred retirement unexpectedly admitted")?;
        need(premature.to_string().contains("attempted transfer requires real original tree retirement"),
            "post-export uncertainty must keep all original ownership")?;
        let (data, expected) = data.into_tree_custody()?;
        // Install both real owners before send. Any possible send result must
        // follow the original tree's PIDFD retirement, never a local shortcut.
        tree.retirement.prepared.bases = Some(ResourcePreparation::PrivateControl);
        tree.retirement.prepared.persistent_data = Some(ResourcePreparation::PrivateControl);
        tree.bases = Some(BaseMounts::PrivateControl(bases));
        tree.persistent_data = Some(data);
        let transfer: Result<()> = (|| {
            let init = tree.init.as_mut().ok_or(NamespaceError::Rejected("original PID1 missing"))?;
            if matches!(stimulus, Transfer::ClosedWrite) {
                if unsafe { libc::shutdown(init.control.as_raw_fd(), libc::SHUT_WR) } != 0 {
                    return Err(io::Error::last_os_error().into());
                }
            }
            let packet = Packet::new(init.nonce, Phase::MountPersistentBase, 0, init.parent_pid);
            let data_indices = if matches!(stimulus, Transfer::Swapped) { [3, 2] } else { [2, 3] };
            send_persistent_base_fds(init.control.as_raw_fd(), &packet,
                [rights[0].as_fd(), rights[1].as_fd(), rights[data_indices[0]].as_fd(), rights[data_indices[1]].as_fd()])?;
            init.persistent_roots = Some(observed);
            init.receive_phase(Phase::PersistentRootReady)?;
            init.verify_empty_root_mounts(devices, None, None)?;
            tree.base_devices = Some(devices);
            tree.base_root_ready = true;
            tree.verify_live_admission()?;
            Ok(())
        })();
        drop(rights);
        Ok((expected, transfer.map_err(|error| error.to_string())))
    }

    fn guest_report(init: &TreeChild) -> Checked<child::persistent_control::GuestReport> {
        use child::persistent_control::{GuestReport, REPORT_MAGIC};
        init.verify()?;
        wait_readable(&init.control, &init.pidfd)?;
        let mut body: GuestReport = unsafe { std::mem::zeroed() };
        let mut iov = libc::iovec { iov_base: (&mut body as *mut GuestReport).cast(), iov_len: std::mem::size_of::<GuestReport>() };
        let mut control = [0usize; 16];
        let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
        message.msg_iov = &mut iov; message.msg_iovlen = 1;
        message.msg_control = control.as_mut_ptr().cast(); message.msg_controllen = std::mem::size_of_val(&control);
        let count = unsafe { libc::recvmsg(init.control.as_raw_fd(), &mut message, libc::MSG_CMSG_CLOEXEC) };
        need(count == std::mem::size_of::<GuestReport>() as isize
            && message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) == 0, "whole exact private guest report")?;
        let header = unsafe { libc::CMSG_FIRSTHDR(&message) };
        need(!header.is_null(), "original kernel credentials required on guest report")?;
        let header_ref = unsafe { &*header };
        need(header_ref.cmsg_level == libc::SOL_SOCKET && header_ref.cmsg_type == libc::SCM_CREDENTIALS
            && header_ref.cmsg_len == unsafe { libc::CMSG_LEN(std::mem::size_of::<libc::ucred>() as u32) } as usize
            && unsafe { libc::CMSG_NXTHDR(&message, header) }.is_null(), "one kernel credential and no rights in report")?;
        let creds = unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<libc::ucred>()) };
        need(creds.pid == init.identity.pid as i32 && creds.uid == init.uids.start && creds.gid == init.gids.start,
            "same actual original PID1 report sender")?;
        need(body.magic == REPORT_MAGIC && body.nonce == init.nonce && body.writer_pid > 1
            && body.writer_exit == 0 && body.writer_pidfd_inode != 0, "same actual fixed guest writer and original pidfd reap")?;
        for (index, node) in body.files.iter().enumerate() {
            let uid = if index % 2 == 0 { 0 } else { APP };
            let bytes = if index % 2 == 0 { b"fixture-root-zero\n".len() } else { b"fixture-guest-10061\n".len() };
            need(node.device != 0 && node.inode != 0 && node.links == 1 && node.uid == uid && node.gid == uid
                && node.bytes == bytes as u64 && node.mode == libc::S_IFREG | 0o600 && node.reserved == 0,
                "exact actual guest ownership and content shape")?;
        }
        init.verify()?;
        Ok(body)
    }

    fn open_file(parent: &File, name: &std::ffi::CStr, directory: bool) -> Checked<File> {
        let flags = libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | if directory { libc::O_DIRECTORY } else { 0 };
        let raw = unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags) };
        if raw < 0 { return Err(io::Error::last_os_error().into()); }
        Ok(unsafe { File::from_raw_fd(raw) })
    }

    fn probe(tree: &IsolatedNamespaces) -> Checked<serde_json::Value> {
        tree.verify()?;
        let init = tree.init.as_ref().ok_or("actual PID1 absent")?;
        send_packet(init.control.as_raw_fd(), &Packet::new(init.nonce, Phase::ProbePersistentData, 0, init.parent_pid))?;
        init.receive_phase(Phase::PersistentDataChecked)?;
        let guest = guest_report(init)?;
        let root = held_child_root(init)?;
        let mut rows = Vec::new();
        for (role, name) in [c"data", c"metadata"].into_iter().enumerate() {
            let directory = root_subdirectory(&root, name)?;
            let root_file = open_file(&directory, c"root-seed", false)?;
            let app_directory = open_file(&directory, c"private-app", true)?;
            let app_file = open_file(&app_directory, c"app-probe", false)?;
            for (offset, file) in [root_file, app_file].into_iter().enumerate() {
                let expected = guest.files[role * 2 + offset];
                let metadata = file.metadata()?;
                need(metadata.dev() == expected.device && metadata.ino() == expected.inode && metadata.len() == expected.bytes
                    && metadata.nlink() == expected.links && metadata.mode() == expected.mode
                    && metadata.uid() == START + expected.uid && metadata.gid() == START + expected.gid,
                    "same actual guest inode must show its mapped host UID/GID")?;
                let payload: &[u8] = if offset == 0 { b"fixture-root-zero\n" } else { b"fixture-guest-10061\n" };
                let mut body = vec![0; payload.len()]; file.read_exact_at(&mut body, 0)?;
                need(body == payload, "same actual mapped-host contents")?;
                rows.push(serde_json::json!({"role":role,"file":offset,"device":metadata.dev(),"inode":metadata.ino(),
                    "guest_uid":expected.uid,"guest_gid":expected.gid,"host_uid":metadata.uid(),"host_gid":metadata.gid(),
                    "bytes":metadata.len(),"mode":metadata.mode()}));
            }
        }
        tree.verify()?;
        Ok(serde_json::json!({"files":rows,"writer_pid_in_owned_namespace":guest.writer_pid,
            "writer_original_pidfd_inode":guest.writer_pidfd_inode,"writer_exit":guest.writer_exit,
            "original_PID1_unchanged":true,"actual_fixed_probe_passed":true}))
    }

    fn finish_tree(tree: IsolatedNamespaces, expected: ExpectedRetirement) -> Checked<VerifiedPrivateRetirement> {
        let exit = tree.retire()?;
        need(exit.init.reason == libc::CLD_EXITED && exit.init.status == 0
            && exit.keeper.reason == libc::CLD_EXITED && exit.keeper.status == 0,
            "both original owned private actors actually exited and reaped")?;
        need(exit.resources.prepared.bases == Some(ResourcePreparation::PrivateControl)
            && exit.resources.prepared.persistent_data == Some(ResourcePreparation::PrivateControl)
            && exit.verify_package_retirement().is_err(), "private fixture cannot qualify an admitted package")?;
        let actual = exit.resources.persistent_data.as_ref().ok_or("actual persistent retirement absent")?;
        Ok(expected.finish(actual)?)
    }

    fn normal_and_foreign(run: &FixtureRun, results: &mut Vec<serde_json::Value>) -> Checked<()> {
        let fixture = run.case(Case::Positive)?;
        let mut original = tree(fixture.reserve()?)?;
        let data = PrivatePersistentData::prepare(&fixture, &original.witness()?)?;
        let detached = data.observation()?;
        let foreign = run.case(Case::Foreign)?;
        let foreign_tree = tree(foreign.reserve()?)?;
        let witness = foreign_tree.witness()?;
        let wrong = data.verify(&witness).err().ok_or("foreign actual equal-map namespace admitted")?;
        need(wrong.to_string().contains("same actual private namespace"), "foreign namespace must fail the actual identity comparison")?;
        let wrong_source = original.witness()?.identity_lease()?.broker_verify_backing(&foreign.files()[0], &fixture.files()[1]);
        need(wrong_source.is_err(), "actual foreign source inode must fail the original lease")?;
        let wrong_roles = original.witness()?.identity_lease()?.broker_verify_backing(&fixture.files()[1], &fixture.files()[0]);
        need(wrong_roles.is_err(), "actual swapped reserved inode roles must fail")?;
        let same_inode = original.witness()?.identity_lease()?.broker_verify_backing(&fixture.files()[0], &fixture.files()[0]);
        need(same_inode.is_err(), "actual aliased inode roles must fail")?;
        let unbound = private_control::header_only(&foreign, &witness)?;
        drop(witness);
        let exit = foreign_tree.retire()?;
        need(exit.init.status == 0 && exit.keeper.status == 0 && foreign.lease_available()?, "foreign private owner actually retired")?;
        foreign.remove_retired_images(&unbound)?;
        results.push(serde_json::json!({"case":"foreign-namespace-and-source","actual_equal_numeric_maps":true,
            "different_held_userns_rejected":wrong.to_string(),"foreign_inode_rejected":true,
            "swapped_reserved_roles_rejected":true,"same_inode_roles_rejected":true,"retired":unbound.observation()}));
        let bases = crate::production_mounts::private_control::prepare_persistent_fixture_bases(&original.witness()?, &fixture)?;
        let (expected, transfer) = attach(&mut original, bases, data, Transfer::Correct)?;
        transfer.map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;
        let observed = probe(&original)?;
        let retired = finish_tree(original, expected)?;
        need(fixture.lease_available()?, "writable owner original reservation finally released")?;
        let writable_retirement = retired.observation();
        let (disk, final_retirement) = private_control::readonly_disk_observation(&fixture, retired)?;
        fixture.remove_retired_images(&final_retirement)?;
        results.push(serde_json::json!({"case":"positive","detached":detached,"guest_and_host":observed,
            "writable_retirement":writable_retirement,"readonly_disk":disk,"final_retirement":final_retirement.observation(),
            "own_images_unlinked_after_actual_unbind":true}));
        run.verify(true)?;
        Ok(())
    }

    fn dirty(run: &FixtureRun, results: &mut Vec<serde_json::Value>) -> Checked<()> {
        let fixture = run.case(Case::Dirty)?;
        let mut header = [0u8; 1024]; fixture.files()[0].read_exact_at(&mut header, 1024)?;
        header[0x3a..0x3c].copy_from_slice(&3u16.to_le_bytes());
        let mut crc = u32::MAX;
        for byte in &header[..0x3fc] {
            crc ^= u32::from(*byte);
            for _ in 0..8 { crc = (crc >> 1) ^ (0x82f6_3b78 & 0u32.wrapping_sub(crc & 1)); }
        }
        header[0x3fc..].copy_from_slice(&crc.to_le_bytes());
        fixture.files()[0].write_all_at(&header, 1024)?; fixture.files()[0].sync_all()?;
        let before = crate::production_identity::tests::persistent_fixture::digest(&fixture.files()[0])?;
        let original = tree(fixture.reserve()?)?;
        let (error, proof) = private_control::header_rejection(&fixture, &original.witness()?)?;
        need(error.contains("original ext4 must be clean with an internal journal and no pending recovery"),
            "real valid-checksum dirty image must fail the intended readonly journal gate")?;
        need(crate::production_identity::tests::persistent_fixture::digest(&fixture.files()[0])? == before,
            "complete dirty fixture unchanged by rejection")?;
        let exit = original.retire()?;
        need(exit.init.status == 0 && exit.keeper.status == 0, "dirty control's original actors reaped")?;
        fixture.remove_retired_images(&proof)?;
        results.push(serde_json::json!({"case":"dirty-checksummed-ext4","error":error,
            "whole_dirty_before_and_after_sha256":before,"no_loop_allocator_reached":true,"no_journal_replay":true}));
        run.verify(true)?;
        Ok(())
    }

    fn transfer_negative(run: &FixtureRun, stimulus: Transfer, results: &mut Vec<serde_json::Value>) -> Checked<()> {
        let case = if matches!(stimulus, Transfer::Swapped) { Case::Swapped } else { Case::SendUnknown };
        let fixture = run.case(case)?;
        let mut original = tree(fixture.reserve()?)?;
        let data = PrivatePersistentData::prepare(&fixture, &original.witness()?)?;
        let bases = crate::production_mounts::private_control::prepare_persistent_fixture_bases(&original.witness()?, &fixture)?;
        let (expected, transfer) = attach(&mut original, bases, data, stimulus)?;
        let error = transfer.err().ok_or("negative actual transfer unexpectedly succeeded")?;
        if matches!(stimulus, Transfer::Swapped) {
            need(error.contains("same actual mapped writable") || error.contains("persistent data mount graph"),
                "swapped roots must fail actual selected root/graph binding")?;
        } else {
            need(error.contains("Broken pipe") || error.contains("os error 32"), "closed original sender must report real EPIPE")?;
        }
        need(!fixture.lease_available()? && original.persistent_data.is_some() && original.bases.is_some(),
            "send/graph uncertainty retains both actual owners and original lease")?;
        let proof = finish_tree(original, expected)?;
        fixture.remove_retired_images(&proof)?;
        results.push(serde_json::json!({"case":if matches!(stimulus, Transfer::Swapped) {"swapped-four-FD-roles"} else {"attempted-send-unknown"},
            "actual_error":error,"pretransfer_cleanup_rejected":true,"second_export_rejected":true,
            "original_tree_retirement":proof.observation(),"own_images_unlinked_after_actual_unbind":true}));
        run.verify(true)?;
        Ok(())
    }

    fn held_cleanup(run: &FixtureRun, results: &mut Vec<serde_json::Value>) -> Checked<()> {
        let fixture = run.case(Case::CleanupHeld)?;
        let original = tree(fixture.reserve()?)?;
        let mut data = PrivatePersistentData::prepare(&fixture, &original.witness()?)?;
        let retained_mount = data.duplicate_data_mount()?;
        let error = data.try_retire_untransferred().err().ok_or("live retained mount did not prevent actual loop retirement")?;
        need(error.to_string().contains("owned loop still has kernel references"), "real retained mount must reach exact loop Busy")?;
        need(!fixture.lease_available()?, "failed cleanup keeps original reservation OFD")?;
        drop(retained_mount);
        // One explicit continuation after this exact holder was closed; there
        // is no retry of a send, unknown actor or unowned loop.
        let proof = data.try_retire_untransferred()?;
        let exit = original.retire()?;
        need(exit.init.status == 0 && exit.keeper.status == 0, "cleanup control owned actors reaped")?;
        fixture.remove_retired_images(&proof)?;
        results.push(serde_json::json!({"case":"actual-live-mount-holder","actual_error":error.to_string(),
            "retained_original_lease":true,"same_holder_closed_then_owned_ENXIO":proof.observation()}));
        run.verify(true)?;
        Ok(())
    }

    #[test]
    #[ignore = "requires separately reviewed disposable root syscall fixture; never run during cargo tests"]
    fn privileged_private_persistent_data_syscall_controls() -> Checked<()> {
        let run = FixtureRun::create()?;
        let mut results = Vec::new();
        let outcome: Checked<()> = (|| {
            normal_and_foreign(&run, &mut results)?;
            dirty(&run, &mut results)?;
            transfer_negative(&run, Transfer::Swapped, &mut results)?;
            transfer_negative(&run, Transfer::ClosedWrite, &mut results)?;
            held_cleanup(&run, &mut results)?;
            run.verify(true)?;
            Ok(())
        })();
        let final_check = run.verify(true);
        let error = outcome.as_ref().err().map(ToString::to_string);
        let cleanup_error = final_check.as_ref().err().map(ToString::to_string);
        run.report(&serde_json::json!({"schema":"p4-disposable-persistent-data-actual-syscall-controls-v1",
            "passed":outcome.is_ok() && final_check.is_ok(),"cases":results,"error":error,"final_bookend_error":cleanup_error,
            "no_automatic_rerun":true,"Main_qualified":false,"original_data_continuity_qualified":false}))?;
        final_check?;
        outcome
    }
}
