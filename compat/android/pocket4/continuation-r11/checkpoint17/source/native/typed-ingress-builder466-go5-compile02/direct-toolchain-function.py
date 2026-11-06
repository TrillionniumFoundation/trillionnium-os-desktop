def toolchain(report, base_env):
    observation,observation_pin=pinned_packet('rust193-tools-recheck-read03-result.json',OBSERVATION)
    actual=json.loads(observation)
    require(actual['state']=='PASS_FIXED_TOOL_OBSERVATION_NOT_EXECUTION_APPROVAL' and
            actual['complete'] is True and actual['repository_channel']==TOOLCHAIN and
            actual['repository_toolchain']['sha256']=='8bc51ecab82415fddd8489604f2424e137d71856e7f65cbdcfaa48850d794b46' and
            actual['all_observed_tool_contents_and_aliases_unchanged_after'] is True and
            actual['owned_resource_gate']['pass'] is True and actual['first_error'] is None and
            not actual['secondary_errors'] and actual['commands_executed']==0 and actual['tool_execution'] is False,
            'fixed installed toolchain reobservation is not complete')
    previous,previous_pin=pinned_packet('prior-compile01-failure.json',
            '44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3')
    failed=json.loads(previous)
    require(previous_pin['bytes']==7681 and actual['actual_build_failure']==
                {'bytes':previous_pin['bytes'],'sha256':previous_pin['sha256']} and
            failed['state']=='FAIL' and failed['commands']==[] and
            failed['error']=="RuntimeError('observed tool changed before compilation: /home/alex/.cargo/bin/rustup')" and
            not failed['cleanup']['errors'] and not failed['cleanup']['remaining'] and
            not failed['cleanup']['forced_cleanup'],
            'prior compile01 failure authority differs')
    observed={r['requested_path']:r for r in actual['tools']}
    proxy='/home/alex/.cargo/bin/rustup'
    require(len(observed)==len(actual['tools'])==12 and proxy in observed and
            actual['changed_tools']==[{'changed_admission_fields':['sha256','bytes'],
                'original_object_metadata_equal':False,'path':proxy}],
            'reobservation is not the exact single proxy-content change')
    require(all(row['error'] is None and row['content_read'] is True and
                row['resolution_changed'] is False and
                row['held_before']==row['held_after']==row['resolved_named_after'] and
                row['requested_named_before']==row['requested_named_after'] and
                row['requested_link_text_before']==row['requested_link_text_after']
                for row in actual['tools']),
            'fixed observed tool closure changed during reobservation')
    expected={path:row for path,row in observed.items() if path!=proxy}
    require(len(expected)==11 and all(row['compilation_admission_fields_equal'] is True and
                row['changed_compilation_admission_fields']==[] and
                row['original_object_metadata_equal'] is True for row in expected.values()),
            'a directly used tool differs from the original installed authority')
    require(not any(name.startswith('RUSTUP') for name in base_env) and
            all(name not in base_env for name in ('LD_PRELOAD','LD_LIBRARY_PATH','RUSTC_BOOTSTRAP')) and
            base_env['PATH']=='/usr/bin:/bin' and
            base_env['RUSTC']==str(RUST_SYSROOT/'bin/rustc') and
            base_env['RUSTDOC']==str(RUST_SYSROOT/'bin/rustdoc'),
            'direct toolchain environment contains a proxy selection or inherited override')
    real_directory(RUST_SYSROOT)
    allowed=[Path('/usr/bin'),Path('/usr/lib'),RUST_SYSROOT]
    rows=[]
    for path,wanted in expected.items():
        row=pin_resolved(Path(path),allowed)
        require(row['sha256']==wanted['sha256'] and row['bytes']==wanted['bytes'] and
                row['resolved_path']==wanted['resolved_path'],
                'observed direct tool changed before compilation: '+path)
        rows.append(row)
    selected={name:RUST_SYSROOT/'bin'/name for name in ['cargo','rustc','rustdoc']}
    for name in ['cargo','rustc']:
        path=selected[name]
        require(str(path) in expected and path.resolve(strict=True)==path and
                expected[str(path)]['resolved_path']==str(path),
                'direct compiler path differs from the fixed Rust 1.93 authority: '+name)
    # No doctest is requested. Bind the absolute RUSTDOC path to the same
    # installed sysroot closure now and recheck it with all other tool inputs.
    # Its bytes were not included in the old read02/read03 observation.
    rustdoc=pin_resolved(selected['rustdoc'],allowed)
    require(rustdoc['resolved_path']==str(selected['rustdoc']) and
            stat.S_ISREG(rustdoc['identity'][2]) and rustdoc['identity'][2]&0o111,
            'fixed sysroot rustdoc is aliased or not an executable regular file')
    rows.append(rustdoc)
    sysroot=RUST_SYSROOT
    require(selected['cargo'].parent.parent==selected['rustc'].parent.parent==sysroot,
            'cargo/rustc toolchain mismatch')
    cargo_version=command([str(selected['cargo']),'--version'],COPIED,base_env,'cargo-version',report['commands'],10).decode()
    rustc_version=command([str(selected['rustc']),'-vV'],COPIED,base_env,'rustc-version',report['commands'],10).decode()
    require(cargo_version.startswith('cargo '+TOOLCHAIN+' ') and '\nrelease: '+TOOLCHAIN+'\n' in rustc_version,
            'actual toolchain version differs from repository pin')
    for path in [Path('/usr/bin/git'),Path('/usr/bin/ninja'),Path('/usr/bin/cp'),Path('/usr/bin/ldd')]:
        rows.append(pin_resolved(path,allowed))
    library_rows=regular_tree(sysroot/'lib/rustlib/x86_64-unknown-linux-gnu/lib',512,1536*1024*1024)
    for row in library_rows.values():
        row.update({'requested_path':row['path'],'resolved_path':row['path']})
        rows.append(row)
    for path in sorted((sysroot/'lib').glob('*.so*')):
        rows.append(pin_resolved(path,allowed))
    linked=set()
    for index,path in enumerate([selected['cargo'],selected['rustc'],Path('/usr/bin/cc'),Path('/usr/bin/ld'),
                                Path('/usr/bin/git'),Path('/usr/bin/ninja'),selected['rustdoc']]):
        raw=command(['/usr/bin/ldd',str(path)],COPIED,base_env,'linked-libraries-'+str(index),report['commands'],10).decode()
        require('not found' not in raw,'tool runtime library missing')
        for line in raw.splitlines():
            match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
            if match:
                linked.add(match.group(1))
    for name in sorted(linked):
        rows.append(pin_resolved(Path(name),allowed+[Path('/usr/lib'),Path('/lib')]))
    unique={row['requested_path']:row for row in rows}
    require(proxy not in unique,'unused rustup proxy was retained as a compilation input')
    report['actual_tool_reobservation']=observation_pin
    report['prior_compile01_failure_authority']=previous_pin
    report['unused_proxy_observation']={key:observed[proxy][key] for key in
            ['requested_path','resolved_path','bytes','sha256','changed_compilation_admission_fields']}
    report['actual_toolchain']={'repository_version':TOOLCHAIN,'cargo':str(selected['cargo']),
            'rustc':str(selected['rustc']),'rustdoc':str(selected['rustdoc']),
            'cargo_version':cargo_version,'rustc_verbose_version':rustc_version,
            'selection':'explicit observed installed 1.93 cargo/rustc paths; no rustup command',
            'selection_installs_or_updates':False,'global_stable_1_95_not_used':True,
            'rustup_proxy_executed':False,'rustup_proxy_is_compilation_input':False,
            'rustup_proxy_changed_bytes_approved_for_execution':False,
            'rustdoc_observed_with_sysroot_closure_this_attempt':rustdoc,
            'rustdoc_old_hash_prequalified':False,'doctests_requested':False}
    return selected,list(unique.values())
