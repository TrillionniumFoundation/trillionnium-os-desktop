// Included only in the original cfg(test) private_control module.
// Reuses the same base owner/loop/mount/retirement and typed new fixture.
    pub(crate) fn prepare_persistent_fixture_bases(
        witness: &OwnedNamespaceWitness<'_>,
        data_fixture: &crate::production_identity::tests::persistent_fixture::PersistentFixture<'_>,
    ) -> Result<PrivateControlMounts> {
        require(
            unsafe { libc::getuid() } == 0 && unsafe { libc::geteuid() } == 0,
            "separately reviewed root filesystem control",
        )?;
        witness.revalidate()?;
        require_complete_namespace(witness)?;
        data_fixture.verify_lease(witness.identity_lease()?)?;
        let parent = trusted_directory(data_fixture.path(), 0)?;
        require(
            parent.metadata()?.mode() & 0o777 == 0o700,
            "fixed root-only private fixture parent",
        )?;
        let fixture = tempfile::Builder::new()
            .prefix("base-")
            .tempdir_in(data_fixture.path())?;
        let root = fixture.path();
        let system_tree = root.join("system-tree");
        let vendor_tree = root.join("vendor-tree");
        create_directory(&system_tree)?;
        create_directory(&vendor_tree)?;
        for name in [
            "system",
            "system/product",
            "system/system_ext",
            "vendor",
            "data",
            "metadata",
        ] {
            create_directory(&system_tree.join(name))?;
        }
        create_directory(&vendor_tree.join("etc"))?;
        symlink("/system/product", system_tree.join("product"))?;
        symlink("/system/system_ext", system_tree.join("system_ext"))?;
        write_private(
            &system_tree.join("system/readonly-probe"),
            b"private-system-readonly-probe\n",
            0o666,
        )?;
        write_private(
            &vendor_tree.join("readonly-probe"),
            b"private-vendor-readonly-probe\n",
            0o666,
        )?;
        use crate::production_identity::tests::persistent_fixture::ImageRole;
        let image_parent = trusted_directory(root, 0)?;
        for (role, tree) in [(ImageRole::System, &system_tree), (ImageRole::Vendor, &vendor_tree)] {
            let tree = trusted_directory(tree, 0)?;
            let file = match data_fixture.run().format(data_fixture.path(), &image_parent, role, Some(&tree)) {
                Ok(file) => file,
                Err(error) => {
                    // A formatter may still have unproven process custody.
                    // Preserve every new image and seed name for the outer
                    // owner; TempDir must not unlink a live formatter's inputs.
                    std::mem::forget(fixture);
                    return Err(error.into());
                }
            };
            file.set_permissions(std::fs::Permissions::from_mode(0o400))?;
        }
        let lease = witness.identity_lease()?;
        let open_image = |name: &str| {
            SealedFile::open_guarded(root, name, 0, IMAGE_BYTES, |f| {
                lease.broker_reject_backing_body(f)?;
                Ok(())
            })
        };
        let system = open_image("system.img")?;
        let vendor = open_image("vendor.img")?;
        let digests = [digest(&system)?, digest(&vendor)?];
        for (file, sha) in [(&system, &digests[0]), (&vendor, &digests[1])] {
            file.verify_digest(IMAGE_BYTES, sha)?;
            require(
                Filesystem::detect(&file.file)? == Filesystem::Ext4,
                "actual newly formatted private ext4 required",
            )?;
        }
        let declaration = serde_json::json!({
            "schema":1, "scope":"private_test_ext4_images_only",
            "system":{"bytes":IMAGE_BYTES,"sha256":digests[0]},
            "vendor":{"bytes":IMAGE_BYTES,"sha256":digests[1]},
            "production_authority":false, "Android_exec":false
        });
        write_private(
            &root.join("fixture-manifest.json"),
            &serde_json::to_vec(&declaration)?,
            0o400,
        )?;
        let manifest =
            SealedFile::open_guarded(root, "fixture-manifest.json", 0, MAX_MANIFEST, |f| {
                lease.broker_reject_backing_body(f)?;
                Ok(())
            })?;
        let verification_files = [open_image("system.img")?, open_image("vendor.img")?];
        let cohort = VerifiedCohort {
            system_ext_lib64: None,
            system_ext_readiness: None,
            manifest,
            system,
            vendor,
            system_fs: Filesystem::Ext4,
            vendor_fs: Filesystem::Ext4,
            cohort: lease.broker_cohort().to_owned(),
            host_uid: lease.host_uid(),
        };
        let retention = lease.broker_retain_reservation()?;
        let (uids, gids) = lease.broker_ranges();
        let userns = witness.user_namespace().try_clone()?;
        let meta = userns.metadata()?;
        let mut prepared = PreparedMounts {
            exported: false,
            resources: Some(MountResources {
                engine: None,
                images: Vec::new(),
                cohort,
                userns,
                userns_identity: (meta.dev(), meta.ino()),
                uids,
                gids,
                reservation_retention: retention,
            }),
        };
        // Same actual loop/fsopen/mount_setattr and owned cleanup as production.
        // The separate control type omits only the unavailable production
        // HostAdmission construction; it cannot escape cfg(test).
        let result: Result<()> = (|| {
            let resources = prepared
                .resources
                .as_mut()
                .ok_or(MountError::Rejected("private mount guard absent"))?;
            for role in ["system", "vendor"] {
                resources.matches_witness(witness)?;
                let source = if role == "system" {
                    &resources.cohort.system
                } else {
                    &resources.cohort.vendor
                };
                let binding = LoopBinding::attach(source)?;
                resources.images.push(MountedImage {
                    role,
                    mount: None,
                    binding,
                    fs: Filesystem::Ext4,
                    mount_id: 0,
                });
                let image = resources
                    .images
                    .last_mut()
                    .ok_or(MountError::Rejected("private image absent"))?;
                image.binding.verify()?;
                let mount = detached_mount(
                    &image.binding,
                    Filesystem::Ext4,
                    &resources.userns,
                    uids,
                    gids,
                )?;
                image.mount_id = require_detached(&mount)?;
                image.mount = Some(mount);
                witness.revalidate()?;
            }
            Ok(())
        })();
        if let Err(error) = result {
            // The PreparedMounts destructor attempts checked cleanup and
            // quarantines uncertain kernel resources. Keep their private names.
            std::mem::forget(fixture);
            return Err(error);
        }
        let result = PrivateControlMounts {
            prepared: Some(prepared),
            fixture: Some(fixture),
            verification_files,
            digests,
        };
        result.verify_images_unchanged()?;
        Ok(result)
    }
